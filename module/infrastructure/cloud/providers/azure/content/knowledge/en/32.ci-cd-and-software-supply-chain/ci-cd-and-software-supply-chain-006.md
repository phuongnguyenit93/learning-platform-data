# Scanning Dependencies, Secrets, and Images in Pipelines

## 1. Context and objectives

A CI/CD pipeline can successfully build and deploy an application while still introducing vulnerabilities into runtime. For instance, an API running on Azure Kubernetes Service (AKS) might use an npm library with a disclosed vulnerability, accidentally commit a password, or package an image from an unpatched OS base layer. All three risks travel through the software supply chain: source code, dependencies, the build step, and the deployment artifact.

In the Microsoft Azure ecosystem, pipelines can run on Azure Pipelines or GitHub Actions, store container images in Azure Container Registry (ACR), and deploy to AKS, Azure Container Apps, or App Service. Pre-release security scanning acts as a **quality gate**: a set of conditions forcing the pipeline to halt when detected risk exceeds thresholds.

After this lesson, you will be able to:

- Distinguish scanning **dependencies** (libraries and packages), **secrets** (exposed credentials), and **images** (container artifacts and their dependency layers).
- Choose appropriate scan points across pull requests, builds, pre-ACR push, and post-deployment.
- Write a sample Azure Pipelines YAML workflow with scan steps that block release on critical findings.
- Interpret scan results and handle real vulnerabilities, controlled exceptions, and secret exposure incidents.
- Understand each scanner's limitations, the role of SBOMs, post-release monitoring, and how to harden the pipeline itself.

## 2. Three scan targets, three risk classes

| Target | What the scanner looks for | Typical inputs | Risk if omitted |
| --- | --- | --- | --- |
| **Dependency / SCA** (Software Composition Analysis) | Known vulnerabilities in direct and transitive dependencies, unsafe versions; sometimes license risks | Manifests and lockfiles, e.g., `package.json` + `package-lock.json`, `pom.xml`, Gradle lockfiles, SBOMs | A library enables remote code execution or unauthorized data access |
| **Secret** | API tokens, private keys, passwords, connection strings, or suspicious credential-like strings | Checked-out files, commit diffs, Git history, build configs | Attackers abuse credentials leaked into repositories or artifacts |
| **Container image** | Vulnerabilities in OS packages, runtimes, and app libraries inside the image; some scanners also detect secrets and risky configs | Built OCI/Docker image, image tar, or image in registry | Image ships vulnerabilities even when current app code passed tests |

Dependency scanning and image scanning overlap partially, but neither fully replaces the other. Source scanning focuses on dependency trees and lockfiles; image scanning inspects **what was actually packaged**, including the base image, OS packages, and libraries installed during the build. Secret scanning must happen early enough to prevent granting access or releasing from a commit containing credentials.

Recommended flow diagram:

~~~mermaid
flowchart TD
    A["Commit / pull request"] --> B["Secret scan: diff + working tree"]
    B --> C["Dependency scan: manifest, lockfile, SBOM"]
    C --> D{"Passes quality gate?"}
    D -->|No| X["Stop pipeline, raise actionable findings"]
    D -->|Yes| E["Test, build application"]
    E --> F["Build container image"]
    F --> G["Image scan: OS, libraries, secrets"]
    G --> H{"Passes quality gate?"}
    H -->|No| X
    H -->|Yes| I["Push image to ACR"]
    I --> J["Deploy by image digest"]
    J --> K["Monitor and rescan on new CVEs"]
~~~

Exact ordering varies by tooling and language, yet two principles remain constant: **scan early on pull requests** and **scan the final artifact before release**. Publishing scan findings to a dashboard after an image is already deployed helps monitoring, but is insufficient to block vulnerabilities at release time.

## 3. Dependency scanning: checking the entire library tree

### 3.1 Direct and transitive dependencies

Suppose a Node.js app declares package A, which depends on B. If B has a CVE, reading `package.json` alone misses the risk. A lockfile (like `package-lock.json`) records resolved versions and helps scanners reconstruct the dependency tree. In Java, the same idea applies to Maven/Gradle; use a scanner that understands the resolved dependency graph or an SBOM generated during the build.

Scanning workflow:

1. Check out the exact PR commit, keeping manifest and lockfile in sync; avoid silently auto-updating dependencies during a scan.
2. Run an SCA tool to obtain package name, version, CVE/GHSA/OSV ID, severity, dependency path, and available fixes.
3. Determine whether the app truly uses the affected version, whether scope is production or development, and whether the flaw is exploitable in the current architecture.
4. Upgrade direct dependencies or update transitive dependencies via parent versions or supported patches; regenerate lockfiles and run tests.
5. Rescan the exact artifact slated for release. If an exception is needed, document the vulnerability ID, evidence, approver, and expiration date.

Example for a Node.js project with a committed `package-lock.json`:

~~~bash
# Check dependencies using the package manager itself.
npm audit --audit-level=high

# Scan secrets independently so CVE severity filters do not hide them.
trivy fs --scanners secret --exit-code 1 .

# Scan dependency vulnerabilities at HIGH/CRITICAL threshold.
trivy fs --scanners vuln --severity HIGH,CRITICAL --exit-code 1 .
~~~

A non-zero exit code halts the pipeline when findings exceed the configured threshold. For Maven or Gradle, integrate an appropriate SCA tool such as OWASP Dependency-Check or an SBOM-based scanner. Never assume every scanner resolves transitive dependencies accurately from manifests alone; if lockfiles are absent, rely on build-time dependency resolution or SBOMs.

**Common pitfall:** severity indicates how serious a flaw is, not proof that your app is exploitable. Conversely, the absence of a public exploit does not prove safety. Blocking policies should weigh severity, runtime environment, reachability, available patches, and organizational security requirements.

### 3.2 SBOMs support traceability

An SBOM (Software Bill of Materials) lists components and versions inside an artifact. It helps answer: "Among our running images, which ones contain package X when a new CVE drops?" Example generating a CycloneDX SBOM with Syft:

~~~bash
syft my-app:build-123 -o cyclonedx-json=sbom.json
~~~

An SBOM is a **component inventory**; by itself it does not prove software is safe. You can feed an SBOM into scanners, store it alongside commit, build, and image digest metadata, and rescan whenever vulnerability databases update. Depending on requirements, pipelines may also check licenses, package integrity, artifact signatures, and build provenance; these are complementary controls beyond basic CVE scanning.

## 4. Secret scanning: detect early and treat as an incident

Secrets can hide in `.env` files, YAML, source code, notebooks, test fixtures, Docker build args, logs, or old commits. A token-like string may be a false positive, while a real credential may not match detection patterns. Therefore, secret scanning aids detection rather than guaranteeing 100% recall.

Combine three control layers:

1. **Before pushing code:** use pre-commit hooks and repository push protection where supported so developers are warned immediately when credentials appear.
2. **In pull requests:** scan diffs or the entire working tree; a scanner like Gitleaks can inspect Git history when full commit history is checked out. Trivy can scan current file contents in secret mode.
3. **Outside CI:** rescan repositories and artifacts periodically. A secret committed months ago might never be touched by a new pull request.

Example running a Gitleaks CLI version supporting the `git` subcommand after checking out full history:

~~~bash
gitleaks git --redact --exit-code 1 .
~~~

The `--redact` flag prevents printing sensitive values in reports. In real pipelines, check flags for your **pinned version** and restrict read access to scan logs and artifacts. If a runner uses shallow checkout, Git-history scans can miss older commits; scanning only the working tree misses secrets deleted from the current branch history.

When a real secret is detected, follow this response sequence:

1. **Immediately revoke or rotate** the credential at its issuing provider; assume any exposed credential is compromised.
2. Inspect access logs and anomalous activity during the exposure window; follow incident response procedures.
3. Remove the value from source code, configs, and artifacts; if rewriting Git history is needed, coordinate with repository owners because history rewrites impact clones and branches. **Deleting a commit does not replace revoking the credential.**
4. Re-issue access following least privilege, rescan, and allow the pipeline to proceed only after remediation.

On Azure, prefer **managed identities** or **workload identity federation/OIDC** for supported resources instead of putting long-lived client secrets in repositories. Use Azure Key Vault for required secrets and Azure DevOps service connections or appropriate identity mechanisms to authorize pipelines. Secret variables only mask values in logs in certain cases; they do not prevent malicious pipelines or scripts from stealing credentials.

In particular, never expose ACR credentials or deployment rights to jobs executing untrusted fork pull requests. Login, push, and deploy steps should run only on protected branches or after configured approvals.

## 5. Container image scanning: inspecting the actual deployable artifact

Images contain many components not obvious in the repository: base images, runtimes, OS packages, libraries installed during `docker build`, and files copied in via `COPY`. Image scanners match these components against vulnerability databases. Some tools also check secrets, Dockerfile misconfigurations, or IaC; enable those scanners explicitly rather than assuming a vulnerability scan validates every configuration.

Example:

~~~bash
# Build image from the current Dockerfile.
docker build -t sample-api:build-123 .

# Scan vulnerabilities in the image available in the Docker daemon.
trivy image --scanners vuln --severity HIGH,CRITICAL --exit-code 1 \
  sample-api:build-123

# Scan secrets inside the artifact; do not apply CVE severity filters.
trivy image --scanners secret --exit-code 1 \
  sample-api:build-123
~~~

Questions to answer when triaging findings:

- Is the affected package in the **base image**, OS packages, or application libraries?
- Does a patch exist for the exact distro and package version in use? Distros often backport fixes while keeping parts of an older version string; rely on distro advisories and how your scanner interprets them.
- Does the image include unneeded tools or libraries? Can you switch to multi-stage builds and minimal runtime images?
- Was the image rebuilt from the updated base image and rescanned? Updating `package.json` while deploying an old image solves nothing.

**Tags can change**, whereas digests identify exact image content. After scanning and pushing, record the digest (e.g., `registry.azurecr.io/sample-api@sha256:...`) and deploy that exact verified digest. Never assume `latest` at two points in time refers to the same artifact. For stronger assurance, organizations can add image signing, provenance/attestations, and admission policies before permitting execution.

ACR provides image storage; container vulnerability reporting in Azure can integrate via Microsoft Defender for Cloud / Defender for Containers depending on plan and configuration. **Pre-push scanning and blocking** in CI remains essential when the goal is preventing non-compliant artifacts from being published: post-deployment vulnerability reporting alone is not a quality gate.

## 6. Designing quality gates by lifecycle stage

| Stage | Recommended checks | Action on failure |
| --- | --- | --- |
| Commit / pull request | Secret scan on diffs and files; SCA on manifests/lockfiles; lockfile diff review | Block merge on real secrets or threshold-breaching dependencies; report feedback to PR author |
| Pre-release build | Tests; supplemental SCA from SBOM; post-build image scan | Halt before granting registry/push access if checks fail |
| Release branch | Reconcile commit, artifact, scan reports, exception policy | Push/deploy only gate-passed artifacts on protected branches |
| Post-release | Rescan against new CVE feeds, monitor workloads, inventory by digest | Raise alerts/tickets, prioritize patching and redeployment |

A starter policy might be: **real secret: block immediately**; **HIGH/CRITICAL vulnerability: block before release**; lower severities tracked with remediation SLAs. This is an educational example, not a universal threshold for every system. Apps handling sensitive data or strict compliance may enforce tighter rules. Conversely, false positives or unpatched issues may go through an authorized exception workflow.

Exceptions must never be implemented by disabling all scans or forcing exit code 0 on release branches. Every exception should record at least: vulnerability ID, affected component, temporary justification, compensating controls, owner, and review/expiration date. Scanner failures to fetch databases or analyze artifacts must also be distinguished from "zero vulnerabilities found"; on sensitive release paths, scanner errors should fail closed or route to a defined escalation workflow.

## 7. Practice: Azure Pipelines scanning before pushing to ACR

### 7.1 Assumptions and setup

This example illustrates a Node.js API with a `Dockerfile` and committed `package-lock.json`. The repository defines an `npm test` script. The pipeline runs on an Ubuntu agent with Docker; an ACR exists along with an Azure DevOps Docker registry service connection granted push access. Service connection and registry names below are **sample values** to replace with your own resources.

For readability, the Trivy scanner runs as a separate container while the app image is saved as a tar archive before scanning. This avoids preinstalling the `trivy` CLI on the agent or mounting the Docker socket into the scanner container. In production, select a verified scanner version, **pin by image digest** or equivalent trust mechanism, update regularly, and control agent permissions.

Illustrative Dockerfile (assuming `server.js` exists):

~~~dockerfile
FROM node:22-bookworm-slim
WORKDIR /srv/app
COPY package.json package-lock.json ./
RUN npm ci --omit=dev
COPY . .
USER node
CMD ["node", "server.js"]
~~~

Minimal `.dockerignore` to avoid copying `node_modules` from the agent (which may hold dev dependencies) or sensitive files into the image:

~~~dockerignore
node_modules
.git
.env
.env.*
*.pem
*.key
coverage
~~~

In real projects, pin base images by digest after verification and update digests regularly; expand `.dockerignore` per repo to prevent `COPY`ing credentials or unwanted artifacts into images. Confirm the app runs as non-root and does not require writing to read-only directories.

### 7.2 Pipeline YAML

~~~yaml
# azure-pipelines.yml — example for a repository with Dockerfile and npm test.
trigger:
  - main

# "pr" applies to GitHub/Bitbucket repositories as supported by Azure Pipelines.
# For Azure Repos Git, configure build validation under Branch Policies.
pr:
  - main

pool:
  vmImage: ubuntu-latest

variables:
  trivyImage: 'aquasec/trivy:0.65.0' # Illustrative version; review and pin digest in operations.
  localImage: 'sample-api:$(Build.BuildId)'
  acrLoginServer: 'exampleacr.azurecr.io'

steps:
  - checkout: self
    fetchDepth: 0

  # Scan secrets before running npm scripts and before granting ACR access.
  - bash: |
      set -euo pipefail
      docker run --rm \
        -v "$(Build.SourcesDirectory):/repo:ro" \
        "$(trivyImage)" fs \
        --scanners secret \
        --exit-code 1 \
        /repo
    displayName: 'Scan secrets in repository'

  # Apply HIGH/CRITICAL threshold to vulnerability scan independently.
  - bash: |
      set -euo pipefail
      docker run --rm \
        -v "$(Build.SourcesDirectory):/repo:ro" \
        "$(trivyImage)" fs \
        --scanners vuln \
        --severity HIGH,CRITICAL \
        --exit-code 1 \
        /repo
    displayName: 'Scan dependencies in repository'

  - task: UseNode@1
    inputs:
      version: '22.x'
    displayName: 'Set up Node.js'

  - bash: |
      set -euo pipefail
      npm ci
      npm test
    displayName: 'Install exact lockfile and run tests'

  - bash: |
      set -euo pipefail
      docker build -t "$(localImage)" .
    displayName: 'Build container image'

  # Scan image tar to inspect both base image and packages inside the artifact.
  - bash: |
      set -euo pipefail
      docker save "$(localImage)" -o "$(Agent.TempDirectory)/sample-api.tar"
      docker run --rm \
        -v "$(Agent.TempDirectory):/artifacts:ro" \
        "$(trivyImage)" image \
        --input /artifacts/sample-api.tar \
        --scanners vuln \
        --severity HIGH,CRITICAL \
        --exit-code 1
      docker run --rm \
        -v "$(Agent.TempDirectory):/artifacts:ro" \
        "$(trivyImage)" image \
        --input /artifacts/sample-api.tar \
        --scanners secret \
        --exit-code 1
    displayName: 'Scan image before release'

  # Only main passing all gates may log in to the registry.
  - task: Docker@2
    displayName: 'Log in to ACR after scans pass'
    condition: and(succeeded(), eq(variables['Build.SourceBranch'], 'refs/heads/main'))
    inputs:
      command: login
      containerRegistry: 'acr-service-connection'

  - bash: |
      set -euo pipefail
      docker tag "$(localImage)" \
        "$(acrLoginServer)/sample-api:$(Build.SourceVersion)"
      docker push "$(acrLoginServer)/sample-api:$(Build.SourceVersion)"
    displayName: 'Push verified image to ACR'
    condition: and(succeeded(), eq(variables['Build.SourceBranch'], 'refs/heads/main'))
~~~

**How it works:**

1. Pull requests run only scanning, tests, and build steps. Branch conditions on the last two steps prevent PRs from logging in to ACR or pushing images.
2. The two filesystem scan steps run **secret** and **vuln** separately so the `HIGH,CRITICAL` filter applies only to vulnerabilities; secret findings are evaluated independently. For full commit-history inspection, add Gitleaks (pinned version) while keeping `fetchDepth: 0`. `trivy fs` on the working tree does not equate to scanning full Git history.
3. `trivy image` reads the exact tar archive produced by `docker save`, inspecting packages genuinely inside the image. The scanner exits non-zero on findings above threshold or execution errors, halting downstream steps via `succeeded()`.
4. On `main`, the pipeline logs in and pushes only after all prior steps succeed. The service connection must hold least-privilege ACR permissions; never embed usernames/passwords in YAML.
5. The sample pushes by **commit tag**, improving traceability over `latest`. After pushing, capture and store the image digest from the registry, put that digest into AKS/Container Apps deployment manifests, and archive it alongside the SBOM and scan reports.

This example prioritizes readability and gate flow control. In real pipelines, choose supported scanner versions/digests, verify vulnerability DB network connectivity, store reports where only authorized users can read them, bound artifact retention, and enforce branch protection/reviewers. If using Azure Repos, configure **Branch Policies → Build validation** for pull requests: declaring `pr:` in YAML alone does not create a PR trigger for Azure Repos Git.

### 7.3 Running the pipeline on GitHub Actions

The same principles apply on GitHub Actions: a scan job on `pull_request`, a build/scan job on push to `main`, and a release job holding appropriate permissions depending on the scan job. For dependency changes in pull requests, you can add GitHub's Dependency Review action (when supported by repo/tier):

~~~yaml
name: Review dependencies
on:
  pull_request:

permissions:
  contents: read

jobs:
  dependency-review:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/dependency-review-action@v4
        with:
          fail-on-severity: high
~~~

This snippet covers **PR dependency review only** and does not replace secret scanning or image scanning. In operational workflows, pin third-party actions to verified full commit SHAs, declare minimal `GITHUB_TOKEN` permissions, protect release environments, and use OIDC/workload identity federation for Azure login where supported instead of storing long-lived Azure keys.

## 8. Reading scan results and remediating systematically

Consider three findings in a single run:

| Finding | Proper interpretation | Action |
| --- | --- | --- |
| Transitive library has HIGH GHSA/CVE | Dependency path includes a package in the affected version range | Confirm lockfile and dependency path; upgrade parent package/patch, test, and rescan |
| Suspected API token in config file | Credentials likely entered Git, even if removed in a newer commit | Verify out-of-band, revoke/rotate token, investigate, and rescan; never paste token into tickets |
| OS package in base image has CRITICAL CVE | Updating app code alone may leave that package untouched | Switch to patched base image or rebuild from fixed release, then rescan the new image |

When a scan fails, look beyond the total CVE count. Identify the **artifact**, **package and version**, **advisory source**, **fixed version**, **introduction path**, and **runtime context** of the affected component. For unpatched CVEs, document risk, assess attack-surface reduction or component removal, and schedule updates once fixes arrive.

Commonly misunderstood outcomes:

- **"0 vulnerabilities"** means only that the scanner found nothing within its scope and current database during that run. Check logs to confirm the DB updated cleanly and manifests/images were read properly.
- **Source scanned** does not imply the image is safe, because base image packages do not appear in source.
- **Image scanned** does not prove runtime configs, Key Vault secrets, IAM/RBAC, or network traffic are secure.
- **Secret deleted in a new commit** does not mean the old credential stopped working.
- **CVE with no fix** is not a blanket reason to ignore all CVEs of that severity.

To archive reports for auditing, prefer machine-readable formats (such as JSON/SARIF depending on scanner), strip secret values, tie reports to commit and image digest, and set proper access controls and retention. SBOMs and scan results can be published alongside artifacts, but never upload raw secret matches into a broadly accessible artifact store.

## 9. Hardening the pipeline itself and sustaining detection

A scanner is itself a pipeline dependency. Running a scanning tool from an unvetted image or tag can compromise source code or build credentials. Therefore:

- Pin versions of actions, scanners, and base images; verify publishers, test updates, and avoid floating tags like `latest` in critical pipelines.
- Separate scan jobs on untrusted PRs from jobs holding ACR push or Azure deploy rights. Grant each job, service connection, and runner only necessary permissions.
- Never let Docker builds or pull request scripts access production secrets. Watch out for arbitrary code running in dependency install lifecycle scripts.
- Manage vulnerability databases: track update timestamps, avoid silent fallbacks, and define procedures when scanners lack network connectivity or hold stale DBs.
- Monitor **post-release** vulnerabilities because new CVEs appear after images are built; map running image digests to SBOMs to prioritize patching.
- Maintain an exception process with an owner, expiration date, and evidence; review periodically so allowlists do not grow unchecked.

On Azure, post-deployment image/workload security monitoring can combine Defender for Cloud, Azure Monitor, and operational tooling per configuration. They add lifecycle detection, while the decision gate permitting **artifact release** must be enforced cleanly in CI/CD.

## 10. Practice exercise and self-check

**Exercise:** An API has a `package-lock.json` and a `Dockerfile` using an old base image. On a pull request, the pipeline flags a HIGH dependency. After upgrading the dependency and merging, the image scan flags a CRITICAL CVE in an OS package. Meanwhile, the secret scanner detects a real connection string committed last week.

Propose the remediation order and conditions to permit pushing to ACR. A sound solution:

1. Immediately revoke/rotate the connection string and audit credential usage; remove it from source, artifacts, and history per procedure.
2. Upgrade the dependency and lockfile, run tests, and rescan dependencies on the new commit.
3. Update the base image/OS patches, build a new image, and rescan that image.
4. Open the gate only after the secret is resolved and no unapproved threshold-breaching findings remain; push the scanned image and record its digest/SBOM.
5. Continue monitoring deployed images since new CVEs can be published at any time.

**Self-check questions:**

1. Why can't scanning manifests pre-build replace scanning images post-build?
2. When is full Git history checkout needed for secret scanning, and why is removing a secret in a new commit insufficient?
3. In Azure Pipelines, how do you ensure PRs cannot use ACR image push permissions?
4. Why store image digests and SBOMs rather than just the `latest` tag?
5. When a scanner fails to download its vulnerability database, can you conclude the build is safe?

**Expected outcome:** You can construct a pipeline that detects all three risk classes, blocks before push/deployment, handles urgent secret incidents, and binds scan results to the exact artifact. This forms the foundation for extending into image signing, provenance, admission policies, and end-to-end software supply-chain security on Azure.

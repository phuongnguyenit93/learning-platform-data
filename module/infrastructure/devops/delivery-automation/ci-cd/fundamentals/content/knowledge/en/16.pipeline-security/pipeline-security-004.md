# Controlling Third-Party Actions, Plugins, Images, and Scripts

CI/CD pipelines frequently use many third-party components: GitHub Actions, GitLab CI components, Jenkins plugins, Azure DevOps extensions, container images, build packages, tool installer scripts, and code downloaded at runtime. These components help teams ship faster, but every component introduced into a pipeline can also execute code, read data, or exercise the permissions held by the job.

Therefore, pipeline security is not merely about protecting YAML files or masking secrets. Teams need to know **what code is allowed to run, where the code comes from, which version is used, what privileges it runs with, and how to detect when a vendor or component is compromised**.

This capability belongs to **DEVOPS_CI_CD_FUNDAMENTALS**: building a CI/CD mindset from Git events and pipeline-as-code through builds, testing, artifacts, environments, and quality gates. Controlling third-party actions, plugins, images, and scripts keeps the pipeline's own supply chain manageable and auditable.

## 1. Why Are Third-Party Components a Trust Boundary?

An action, plugin, container image, or script can do far more than its name suggests:

- Read source code and files in the workspace.
- Read environment variables and secrets accessible to the job.
- Make outbound network calls or send data to external services.
- Modify files, alter artifacts, or write data into caches.
- Call CI platform APIs using the token granted to the job.
- Download additional dependencies or scripts at runtime.
- Modify repository state, releases, registries, or environments if permitted.

When a pipeline invokes an action, plugin, or script, the team is delegating a portion of execution privilege to that code. Even a widely used component can suffer an account takeover on its release publisher, a tag overwrite, malicious dependencies, or a new release with altered behavior.

Think of the trust chain as a graph:

~~~mermaid
flowchart TD
    A["Repository and pipeline"] --> B["CI platform / runner"]
    B --> C["Action, plugin, or extension"]
    B --> D["Container image and toolchain"]
    C --> E["Secondary scripts and dependencies"]
    D --> E
    E --> F["Workspace, artifacts, and cache"]
    B --> G["Tokens, secrets, and workload identity"]
    C --> G
    E --> G
    F --> H["Registry and deployment environment"]
~~~

Every node can become an entry point. If an action is compromised and the job holds a repository write token, deployment secrets, or registry access, the impact can extend far beyond the test step the action was meant to perform.

**Principle:** only admit components into the pipeline that are identified, vetted, and version-pinned; restrict job permissions; verify contents before use; and monitor changes throughout the lifecycle.

## 2. Building an Inventory of What the Pipeline Executes

Before controlling components, you must know what the pipeline actually uses. The inventory should cover both directly declared components and indirectly downloaded ones.

| Type | Examples | Information to Record |
| --- | --- | --- |
| CI action | GitHub Action, GitLab CI component | Publisher, source repository, commit/version, permissions, and data accessed |
| Plugin/extension | Jenkins plugin, Azure DevOps extension | Publisher, version, execution permissions, compatibility, and update history |
| Container image | Build image, scanner image, service image | Registry, repository, tag, digest, publisher, and base image |
| Third-party script | CLI install script, deploy helper | Source URL, revision, checksum/signature, permissions, and dependencies |
| Build tool/plugin | Gradle plugin, Maven plugin, npm package | Version, repository, checksum/signature, and lifecycle scripts |
| Reusable workflow/template | Shared workflow or pipeline template | Source repository, pinned revision, maintainer, and permission scope |

Store the inventory in a reviewed repository or configuration management system. For each component, document the business rationale, internal owner, origin, approved version, and update procedure. Unused components should be removed to shrink the attack surface.

Do not inspect only workflow files. Inspect commands in scripts, Dockerfiles, Compose files, build files, plugin configs, and installation commands invoked at runtime. An internal script might download an extra binary from the Internet; that binary is also a pipeline dependency.

## 3. Verifying Sources and Publishers

Before using a component, verify:

- Is the source repository or registry the official origin?
- Is the publishing account/organization verified and trusted by the organization?
- Does the source code have a clear change history, review process, and release workflow?
- Is the released version tied to an identifiable commit/tag or digest?
- Are signatures, checksums, provenance, or attestations available for verification?
- Are there relevant security advisories, CVEs, or supply chain incidents?
- Is there an internal owner responsible for updates and incident response?

Display names, download counts, stars, or marketplace listings are not proof of safety. Popular accounts can be hijacked, official repositories can be compromised, and a new release can introduce new dependencies or behavior.

Prefer official release sources, upstream documentation, publisher-issued signatures or attestations, and verifiable metadata. Where permitted by organizational policy, use an internal proxy/registry to host vetted versions. Proxies help control download sources and availability, but they do not automatically make an untrusted package safe.

### 3.1. Evaluating Permission Scope Before Approval

Read documentation and source code to determine what permissions a component requires:

- Does it need to read the entire repository?
- Does it need to write source, tags, releases, or pull requests?
- Does it need access to secrets or tokens?
- Does it need access to the Docker socket or host filesystem?
- Does it need outbound Internet or internal network connectivity?
- Does it execute arbitrary code derived from user input?

If an action merely uploads a test report yet demands a token with write access to the whole repository, reconsider the choice or build a narrower-scoped upload mechanism. Excessive permissions amplify damage if a component is compromised.

## 4. Pinning Versions with Immutable References

Tags and version names are human-readable, but what they point to can change. Pinning with immutable identifiers ensures the pipeline runs the exact code that was reviewed.

### 4.1. GitHub Actions and Reusable Workflows

In GitHub Actions, referencing an action by a tag like @v4 is convenient, but tags can be moved. For sensitive workflows or strict control requirements, pin actions to a verified full commit SHA:

~~~yaml
steps:
  - name: Checkout source
    uses: actions/checkout@<VERIFIED_FULL_40_HEX_COMMIT_SHA>
~~~

The angle-bracketed string is a placeholder; replace it with the actual verified full commit SHA from the official repository before use. Never treat placeholder text as runnable configuration.

For reusable workflows, also pin repository references by commit SHA when required by policy. Never rely solely on a `main` branch or movable tag for critical release workflows.

SHA pinning prevents a reference from silently switching to another commit, though it does not guarantee the commit itself is safe. You still need to review commit contents, verify sources, and track upstream updates so vulnerable code does not linger.

### 4.2. Container Images

Do not rely on mutable tags like `latest` for builders, scanners, or release images. Pin images by digest:

~~~text
ghcr.io/example-org/build-tool@sha256:<VERIFIED_IMAGE_DIGEST>
~~~

The digest uniquely identifies a specific manifest/image content. Record the registry, repository, digest, platform, and release origin. For multi-architecture images, verify both the image index digest and the corresponding platform manifest.

When an image needs updating, submit a reviewed change to update the digest. Re-run builds, tests, and scans, and verify the provenance of the new image before promoting it into the main pipeline.

### 4.3. Plugins and Extensions

In Jenkins, declare explicit plugin versions in installation configuration, control the update center source, and update via a reviewed process. Do not allow controllers to install arbitrary plugins from unmanaged sources.

In Azure DevOps or other extension platforms, maintain an allowlist of approved extensions, publishers, versions, and integration permissions. Disable or uninstall unused extensions. If a platform auto-updates minor/patch versions, understand that mechanism and apply appropriate testing and change controls.

### 4.4. Scripts and Binaries Downloaded from the Internet

Avoid downloading a script and executing it directly:

~~~bash
curl -fsSL https://example.com/install.sh | bash
~~~

This immediately executes whatever comes back from the network, giving reviewers no chance to inspect the file or verify checksums before execution.

A more controlled approach:

~~~bash
curl --fail --location --silent --show-error \
  https://downloads.example.com/tool/1.4.2/tool-linux-amd64.tar.gz \
  --output tool.tar.gz

printf '%s  %s\n' "$EXPECTED_SHA256" tool.tar.gz | sha256sum --check -
tar -tzf tool.tar.gz
mkdir -p tool-unpacked
tar -xzf tool.tar.gz --no-same-owner -C tool-unpacked
~~~

EXPECTED_SHA256 must come from an independent trusted source or verified signed release metadata. If both the archive and the checksum are fetched from the same unauthenticated endpoint, an attacker controlling that endpoint can swap both. For software supporting digital signatures, prefer verifying signatures using a managed trust root. Before extracting, inspect the archive's path listing for absolute paths or `../` entries that could write files outside the target directory; extract into a dedicated temporary directory and never run binaries before verification.

Pin versions, checksums, or signatures for transitive dependencies installed by scripts as well. A pinned installer that internally downloads the `latest` version of a dependency still introduces non-deterministic inputs.

## 5. Least Privilege for Jobs and Components

An action or script running inside a job can typically exercise whatever permissions the job holds. Reducing job permissions is therefore a vital safeguard even when a component has been reviewed.

Apply least privilege:

- Grant only the read/write permissions each job needs.
- Provide secrets only to the steps that require them.
- Separate build/test jobs from publish/deploy jobs.
- Use short-lived, narrowly scoped tokens.
- Never grant production permissions to jobs executing code from untrusted pull requests.
- Restrict access to registries, cloud accounts, and Kubernetes namespaces.
- Never run runners as administrator/root unless strictly required.

Example of setting default read-only permissions in GitHub Actions:

~~~yaml
permissions:
  contents: read

jobs:
  test:
    permissions:
      contents: read
    runs-on: ubuntu-latest
    steps:
      - name: Checkout
        uses: actions/checkout@<VERIFIED_FULL_40_HEX_COMMIT_SHA>
        with:
          persist-credentials: false
      - name: Run tests
        run: ./scripts/test.sh
~~~

The SHA value in the example is a placeholder and must be replaced with a verified commit. `persist-credentials: false` prevents the checkout action from storing the provisioned Git credential in Git config for subsequent commands after checkout completes, when the job does not need to push or perform authenticated Git operations.

If a job needs to publish packages, create a separate job with write permission only to that registry. If a job needs to generate an attestation via OIDC, grant `id-token: write` only to that job. Do not grant it workflow-wide when other jobs do not need it.

### 5.1. Separating Permissions by Stage

| Job | Required Permissions | Should Not Have |
| --- | --- | --- |
| Pull request test | Read source, run tests | Production secrets, release write access |
| Build/package | Read source, download dependencies, write temporary artifacts | Production deploy permissions |
| Publish artifact | Write to designated registry/repository | Source modification or organization admin permissions |
| Attest/sign | Workload identity to sign the specific artifact | Long-lived private keys stored in workspace |
| Deploy staging | Staging deployment permissions | Production admin permissions |
| Deploy production | Production permissions with approvals and auditing | Broad permissions unrelated to deployment |

Separating jobs does not automatically guarantee security if artifacts or workspaces can be tampered with between jobs. Pass artifacts by digest, verify them before use, and never trust outputs from untrusted jobs without validation.

## 6. Protecting Secrets and Workload Identities

Secrets are commonly used to access registries, cloud providers, signing services, or deployment environments. A third-party component with read access to secrets can exfiltrate them.

Recommended practices:

- Never hardcode secrets in YAML, Dockerfiles, or scripts.
- Use the CI platform's secret store or a dedicated secret manager.
- Pass secrets only to the exact steps that require them.
- Never enable debug modes that dump environments or command lines.
- Never write tokens to logs, artifacts, caches, or provenance.
- Use short-lived credentials instead of long-lived access keys whenever possible.
- Rotate and revoke credentials immediately if exposure is suspected.

Prefer workload identity or OIDC federation when supported by the platform and cloud provider. CI obtains short-lived tokens based on workflow/job identity, while the cloud provider validates issuer, audience, and claims before granting access. This eliminates the need to store long-lived cloud access keys in repository secrets.

OIDC is not automatically secure. Trust policies must be constrained to the appropriate repository, branch, environment, workflow, or subject claim. If a trust policy permits any workflow across an entire organization, a low-trust workflow can obtain a high-privilege identity.

## 7. Preventing Script Injection from Untrusted Data

Pipelines frequently receive data from branch names, pull request titles, commit messages, issue bodies, tags, or user inputs. These values must be treated as untrusted data.

Risky example in GitHub Actions:

~~~yaml
- name: Print pull request title
  run: echo "${{ github.event.pull_request.title }}"
~~~

GitHub Actions expands expressions before the shell runs. If the title contains quotes or shell syntax, the interpolated content can alter the command.

Pass data via an environment variable instead:

~~~yaml
- name: Print pull request title
  env:
    PR_TITLE: ${{ github.event.pull_request.title }}
  shell: bash
  run: |
    printf '%s\n' "$PR_TITLE"
~~~

In this example, the shell reads the variable value already passed into the environment. Quoting `"$PR_TITLE"` prevents word splitting and pathname expansion in Bash. However, the data must still be validated for its usage context: if passed into SQL, URLs, CLI options, or file paths, apply context-appropriate APIs, escaping, and validation. Never use `eval` or concatenate input data into code.

Core principles:

- Keep code fixed in reviewed files; pass inputs strictly as data.
- Validate inputs against allowlists and expected formats.
- Use argument arrays or structured APIs instead of concatenated command strings.
- Use `--` to end option parsing when supported by the tool and data might begin with a hyphen.
- Never execute scripts extracted from comments, PR bodies, or untrusted artifacts.
- Never inject untrusted data into templates evaluated as code.

## 8. Controlling Pull Request and Fork Events

Pull requests from forks or external contributors are sources of untrusted code. Test jobs may need to run that code, but should not receive secrets or write privileges.

For GitHub Actions:

- `pull_request` is usually the right choice for testing PR code with restricted token permissions.
- Set minimal `permissions` and never expose production secrets to jobs testing code from forks.
- Never allow untrusted PRs to write to caches consumed by trusted release jobs without a trust boundary.
- Be cautious with `pull_request_target`: the workflow runs in the target repository context and may hold elevated permissions/secrets. Never check out and execute code from an untrusted PR head inside that workflow.
- If automated labeling or commenting on PRs requires `pull_request_target`, run only code from the trusted base branch, validate all inputs, and restrict token permissions.

A dangerous anti-pattern is using `pull_request_target`, checking out `github.event.pull_request.head.sha`, and running scripts from that checkout alongside a repository write token or secrets. Contributors can alter those scripts to steal the token or secrets.

Other platforms share similar boundaries: pipelines triggered by merge requests, forks, protected branches, and release tags may receive different privileges. Verify the exact context, tokens, and secrets provisioned for each event type.

## 9. Hardening Container Images and Runners

Container images can contain third-party binaries, package managers, entrypoints, and scripts. Even a digest-pinned image can still contain vulnerabilities or run with excessive privileges.

When selecting images:

- Use trusted registries and publishers.
- Pin digests while recording human-readable tags and platforms.
- Inspect Dockerfiles, entrypoints, and layers whenever possible.
- Scan images and monitor advisories after publishing.
- Prefer minimal images to reduce unnecessary packages and shells.
- Generate SBOMs and provenance for critical images.
- Update base images on schedule and in response to relevant advisories.

When running containers:

- Run as a non-root user.
- Use a read-only root filesystem when supported by the workload.
- Drop unnecessary Linux capabilities.
- Enable `no-new-privileges` where appropriate.
- Never mount the Docker socket or host filesystems unless genuinely necessary.
- Enforce CPU, memory, network, and execution time limits.
- Never treat `privileged` mode as the default.

Illustrative example:

~~~bash
docker run --rm \
  --read-only \
  --cap-drop=ALL \
  --security-opt=no-new-privileges \
  --user 10001:10001 \
  --tmpfs /tmp:rw,noexec,nosuid,size=64m \
  ghcr.io/example-org/test-runner@sha256:<VERIFIED_IMAGE_DIGEST>
~~~

The digest in the example is a placeholder and must be replaced with a verified digest. Some workloads need specific capabilities, writable directories, or network endpoints; grant exact requirements and document the rationale rather than enabling full privileges.

Runners are also part of the trust boundary. Runners shared across repositories or jobs of differing trust levels can leak workspaces, caches, or credentials. Use ephemeral runners for sensitive workloads when supported by the platform; isolate runners by trust tier and clean workspaces after each job.

## 10. Governing Plugins and Extensions

Plugins often hold deeper privileges than a script running inside a container. Jenkins plugins can execute inside controller/agent processes and interact directly with Jenkins APIs. CI platform extensions can access repositories, builds, variables, or service connections according to their granted scopes.

A governance process should include:

1. An allowlist of approved plugins/extensions and internal owners.
2. Documented business justification and required permissions for each plugin.
3. Verified release origins and publishers.
4. Pinned versions or controlled update policies.
5. Compatibility testing in a staging environment before production rollout.
6. Monitoring of upstream advisories, CVEs, and notices.
7. A rollback or removal procedure if an update causes issues.
8. Periodic reviews to remove unused plugins.

Never install plugins directly on a production Jenkins controller without review and change control. Protect Jenkins administrative privileges, restrict who can install plugins, and maintain a plugin version inventory for incident investigations.

For GitLab CI components or Azure DevOps extensions, also manage include sources, versions, publishers, and permissions. If a component is referenced by a mutable tag, consider pinning a specific revision or using an internal mirror per policy.

## 11. Updating Components Without Overlooking Risk

Immutable pinning keeps builds from changing unexpectedly, but pinning one version forever traps known vulnerabilities. Therefore, pair pinning with a structured update workflow:

- Monitor upstream releases and security advisories.
- Use automation bots to open pull requests for version/SHA/digest updates where appropriate.
- Review diffs, changelogs, new dependencies, and permission changes.
- Run tests, scans, and provenance checks on the new version.
- Roll out updates in small, reversible batches.
- Enforce remediation SLAs for critical vulnerabilities.
- Record currently deployed versions and update timestamps.

Never auto-update every action, plugin, or image to the latest version in production without testing. Conversely, never defer updates indefinitely simply because SHAs are pinned. Balance per-run immutability with controlled, timely updates.

Dependency changes should be reviewed just like code changes: who published it, what code changed, were new permissions or network calls added, are there new install scripts, and does it affect produced artifacts?

## 12. Responding When a Third-Party Component Is Compromised

If upstream discloses that an action, plugin, image, or package has been compromised, determine whether your pipelines executed the affected version.

Response workflow:

1. **Determine scope:** consult the inventory to identify which repositories, workflows, jobs, runners, and artifacts used that component.
2. **Freeze changes:** block the affected version or digest and halt automated updates from that source.
3. **Isolate:** disable the affected component, runners, or credentials as needed.
4. **Investigate:** inspect logs, network egress, workspaces, caches, token usage, and generated artifacts.
5. **Revoke secrets:** revoke or rotate tokens, signing keys, or credentials that could have been accessed.
6. **Verify artifacts:** identify which digests, provenance records, and releases were created during the exposure window.
7. **Rebuild:** rebuild from verified sources and dependencies on clean builders.
8. **Re-release or roll back:** deploy clean artifacts through the release process.
9. **Document:** preserve the timeline, evidence, decisions, and corrective actions.

Changing the version alone is not enough if runners or secrets may have been compromised. Assess the permissions and credentials the component previously held, and identify which artifacts must be revoked.

## 13. Example of a Controlled GitHub Actions Workflow

The example below illustrates these principles: default read-only permissions, actions pinned by commit SHA, checkout without persisted credentials, and PR titles passed via environment rather than interpolated into shell code. SHAs are placeholders that must be replaced with verified full SHAs before use:

~~~yaml
name: Pull request checks

on:
  pull_request:

permissions:
  contents: read

jobs:
  test:
    runs-on: ubuntu-latest
    permissions:
      contents: read
    steps:
      - name: Checkout
        uses: actions/checkout@<VERIFIED_FULL_40_HEX_COMMIT_SHA>
        with:
          persist-credentials: false

      - name: Inspect pull request title
        env:
          PR_TITLE: ${{ github.event.pull_request.title }}
        shell: bash
        run: |
          printf 'PR title: %s\n' "$PR_TITLE"

      - name: Run tests
        shell: bash
        run: |
          set -euo pipefail
          ./scripts/ci-test.sh
~~~

This workflow needs no secrets to run tests and holds only read access to repository contents. When publishing or deploying is required, create a separate job with narrow permissions, approvals, and an appropriate workload identity. Never expand PR job permissions just to share a single workflow with releases.

## 14. Common Mistakes

| Mistake | Risk | Remediation |
| --- | --- | --- |
| Using actions by mutable tag in sensitive pipelines | Executed code can change without review | Pin full commit SHAs and update via PRs |
| Using `latest` images | Builds may execute different contents across runs | Pin digests and manage updates |
| Downloading scripts and piping straight into a shell | Executes unverified network content | Download, verify checksum/signature, then run |
| Granting every job repository write permissions | Compromised components can alter source/releases | Scope `permissions` per job |
| Giving production secrets to PR jobs | Untrusted code can exfiltrate secrets | Separate jobs, events, and privileged environments |
| Trusting signatures without verifying the signer | Code from unauthorized sources may still be accepted | Verify issuer, identity, and policy |
| Using `privileged` containers and arbitrary Docker socket mounts | Containers can take over the host/runner | Drop capabilities, run non-root, and isolate runners |
| Installing unreviewed plugins | Plugins can run with high CI controller privileges | Allowlist, pin versions, test, and audit |
| Using PR data directly inside scripts | Can cause command injection | Pass via environment, validate, and quote by context |
| Pinning without ever updating | Retains known vulnerable versions | Monitor advisories and run controlled updates |
| Lacking an inventory | Hard to know which pipelines are affected by upstream incidents | Maintain a component and owner inventory |

## 15. Third-Party Component Control Checklist

**Sources and Versions**

- [ ] Inventory maintained for actions, plugins, extensions, images, and scripts.
- [ ] Publishers and source repositories/registries verified.
- [ ] Components pinned by commit SHA, digest, or specific approved version.
- [ ] Checksums, signatures, or provenance verified where supported by the source.
- [ ] Transitive dependencies and installation scripts inspected.

**Permissions and Data**

- [ ] Jobs hold only the minimum required permissions.
- [ ] Secrets are passed only to steps/jobs that need them.
- [ ] Jobs from untrusted forks/PRs receive no production secrets or write permissions.
- [ ] External inputs are passed as data and validated per context.
- [ ] No commands download and immediately execute unverified content.
- [ ] OIDC trust policies are scoped strictly to the right repository/workflow/environment.

**Runners, Containers, and Plugins**

- [ ] Images are digest-pinned and scanned per policy.
- [ ] Containers run non-root, drop capabilities, and enforce resource limits where appropriate.
- [ ] Docker socket and host filesystems are not mounted unless necessary.
- [ ] Runners are isolated by trust level and cleaned between jobs.
- [ ] Plugins/extensions are allowlisted, assigned owners, and scheduled for updates.

**Operations and Response**

- [ ] Review/update process exists for actions, plugins, images, and scripts.
- [ ] Upstream advisories and incidents are monitored.
- [ ] Capability exists to revoke credentials and isolate runners.
- [ ] Inventory supports tracing affected artifacts and releases.
- [ ] Procedures exist to rebuild clean artifacts and roll back when needed.
- [ ] Logs and audit trails are sufficient for investigation.

## Conclusion

Third-party actions, plugins, images, and scripts are all code that the pipeline trusts to execute. Controlling them begins with building an inventory and verifying sources, followed by pinning immutable identifiers, restricting permissions, protecting secrets, isolating runners, and validating inputs. Signatures and digests establish content and publisher identity, but policies are still required to decide which components are permitted to run.

Pinning must go hand in hand with controlled updates. When upstream is compromised, teams need to know where the component is used, which credentials could have been accessed, and which artifacts must be verified or re-released. Maintaining these practices reduces supply chain risk inside the pipeline and keeps the build, test, publish, and deploy flow traceable.

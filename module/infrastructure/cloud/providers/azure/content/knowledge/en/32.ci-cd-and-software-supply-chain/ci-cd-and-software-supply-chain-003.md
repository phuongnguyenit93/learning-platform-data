# GitHub Actions and Deploying Workloads to Azure

A development team building a Spring Boot application receives dozens of pull requests every week. They need to **automatically run tests on PRs, build a traceable artifact, deploy the verified build to staging**, and promote it to production only after approval. The workload may be a Java application running on **Azure App Service**, a container on **Azure Container Apps**, or a service in **Azure Kubernetes Service (AKS)**. The team does not want to store long-lived Azure service principal client secrets in GitHub, nor allow a workflow on any arbitrary branch to modify the entire subscription.

**GitHub Actions** provides a workflow execution engine driven by GitHub events. Combined with **Microsoft Entra workload identity federation via OpenID Connect (OIDC)**, Azure RBAC, GitHub Environments, and an artifact promotion workflow, a team can build CI/CD pipelines **without assigning static Azure passwords to runners**. However, security design matters just as much as YAML: workflows can be abused if GitHub tokens are overly broad, rely on unvetted third-party actions, execute untrusted PR code with deployment permissions, or publish images that can mutate after approval.

This lesson, **"GitHub Actions and Deploying Workloads to Azure,"** belongs to the **CI/CD and Software Supply Chain** chapter in the **CLOUD_PROVIDERS_AZURE** module. It situates GitHub Actions within the broader Azure picture: subscriptions/resource groups, Microsoft Entra ID, virtual networking, compute, container registries, data, monitoring, resource protection, and FinOps.

After this lesson, you will be able to:

- Distinguish **continuous integration, continuous delivery, continuous deployment**, and workload-specific pipelines.
- Read and write a GitHub Actions workflow: `on`, jobs, steps, runners, contexts, permissions, artifacts, caching, environments, and concurrency.
- Set up **GitHub OIDC → Microsoft Entra federated credential → Azure RBAC** scoped to the exact repo/branch/environment without Azure passwords.
- Write a **Maven/Java 21 → Azure App Service** pipeline with testing, independent artifacts, and a staging environment.
- Write a **Docker image → Azure Container Registry (ACR) → Azure Container Apps** pipeline using immutable image digests.
- Decide when to use **AKS/Helm** or **GitOps/Flux** and avoid granting `cluster-admin` to CI.
- Implement release gates, canaries/slots/revisions, rollbacks, migrations, and controlled smoke tests.
- Apply security scanning, SBOM/provenance, GitHub Action pinning, least privilege, secrets hygiene, and branch protection.
- Operate runners, networking, and private endpoints, troubleshoot OIDC/ACR/health errors, measure SLOs, and manage pipeline costs.

> **Scope:** The YAML workflows and Azure commands are **educational examples with placeholders**. No real Azure or GitHub resources were modified while authoring this lesson. GitHub Action major versions, Azure CLI options, and hosting features may change; before real-world adoption, verify action/runtime compatibility, pin commit SHAs for third-party actions, and test in an approved environment.

## 1. From commit to a traceable release

**CI** answers: "Does the source code at this commit compile, pass tests, pass lint, and satisfy security checks?" **CD** answers: "Can the verified artifact be delivered to the target environment safely, repeatably, and recoverably?"

| Concept | Input | Output | Auto-deploys to production? |
|---|---|---|---|
| **CI** | Push/PR, commit SHA | Tests, static analysis, binary/image, reports | No |
| **Continuous delivery** | Verified artifact | Release-ready with an approval gate | Not necessarily |
| **Continuous deployment** | Verified artifact and automated policy | Automated production deployment | Yes, if all gates pass |
| **Release management** | Version/digest, changelog, risk, approvals | Release decision/audit | Can be manual or automated |
| **GitOps** | Approved Git desired state | In-cluster controller reconciles workloads | CI typically only builds and updates Git |

A reliable pipeline requires:

~~~text
Git commit SHA
    ↓
CI: compile → unit/integration tests → security checks
    ↓
Build immutable artifact/image + metadata/SBOM
    ↓
Publish artifact to trusted store/registry
    ↓
Deploy exactly that artifact to staging
    ↓
Health/smoke/security/performance gates
    ↓
Human approval (when required)
    ↓
Promote same artifact digest to production
    ↓
Monitor → rollback/mitigate if SLO breached
~~~

**Never rebuild an image from `main` after staging passes and call it the same release**: dependencies or base images can shift, producing a different binary. Promotion must follow the verified **artifact ID/digest**.

## 2. GitHub Actions: operational model

~~~mermaid
flowchart LR
    DEV[Developer PR/Push] --> GH[GitHub repository and events]
    GH --> WF[Workflow .github/workflows/deploy.yml]
    WF --> CI[CI job on runner]
    CI --> ART[Build artifact / image digest]
    ART --> STG[Staging job with OIDC]
    STG --> APPROVAL[GitHub Environment approval]
    APPROVAL --> PROD[Production job with separate OIDC identity]
    PROD --> AZ[Azure App Service / Container Apps / AKS]
    AZ --> MON[Azure Monitor + smoke checks]
    MON -. Failed health .-> RB[Rollback process]
~~~

### 2.1. Core components

| Component | Meaning | Common risk |
|---|---|---|
| **Workflow** | YAML file in `.github/workflows/` | Overly broad triggers or flawed branch filtering |
| **Event** | `pull_request`, `push`, `workflow_dispatch`, release... | Running untrusted PR code with secrets |
| **Job** | Set of steps on a runner | Assuming shared filesystem/state across jobs |
| **Step** | Runs a shell command or action | Using an action from an untrusted source |
| **Runner** | GitHub-hosted or self-hosted machine running jobs | Network/identity/egress privileges and data leakage |
| **GITHUB_TOKEN** | GitHub token generated per workflow/job | Excess default permissions if undeclared |
| **OIDC token** | Short-lived JWT from GitHub issuer for federation | Unconstrained subject/audience or over-privileged Azure identity |
| **Environment** | Staging/prod, protection rules, environment vars | Missing review gates or reusing staging identity for prod |
| **Artifact** | Build outputs and reports stored across jobs | Building/redeploying different artifacts or retaining too long |
| **Cache** | Data speeding up package managers/builds | Cache poisoning / not a substitute for artifact integrity |
| **Concurrency** | Prevents overlapping deployments to an environment | Accidentally canceling an in-progress production rollout |

### 2.2. Workflows, jobs, and steps

~~~yaml
name: Minimal CI

on:
  pull_request:
    branches: [main]
  push:
    branches: [main]

permissions:
  contents: read

jobs:
  tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Show runtime
        run: java -version
~~~

This sample illustrates **syntax** only; it does not guarantee Java 21 is installed or that tests ran. Note that some YAML 1.1 parsers treat the `on` key specially; GitHub Actions interprets `on` per the workflow schema. Use GitHub Actions-compatible tooling when linting workflows.

### 2.3. Runners do not automatically share filesystems

If the `build` job produces `target/orders-api.jar`, a `deploy` job running on a fresh runner will **not see that file** unless you use `upload-artifact`/`download-artifact` or a registry. Do not rebuild inside the deployment job when the goal is to promote the exact artifact.

~~~text
Job build → actions/upload-artifact → GitHub artifact store
Job deploy → actions/download-artifact → Azure deployment action
~~~

For OCI images, **ACR and image digests** are a better artifact store than passing Docker tarballs between jobs.

### 2.4. GitHub-hosted or self-hosted runners?

**GitHub-hosted:** ephemeral environments managed by GitHub; simple for CI and generally suitable for builds/tests and public Azure endpoints. They **do not have a default private route** to Azure SQL/AKS/private-only apps inside a VNet.

**Self-hosted:** runs inside an organization-managed network and can reach private Azure endpoints, but requires OS patching, workflow isolation, label/permission controls, and workspace cleanup. Never expose trusted runners to arbitrary fork PRs; attackers can exploit network access or residual data.

### 2.5. Workflow files are privileged code

Editing `.github/workflows/deploy.yml` can alter approval conditions, deploy commands, artifact upload paths, or credentials. Enforce branch protection, CODEOWNERS, and dedicated reviews for workflow files. Never grant runners production access simply because a repository is private.

## 3. Events and trigger restrictions

### 3.1. Choosing the right event

| Trigger | When to use | Recommended permissions |
|---|---|---|
| `pull_request` | Build/test PRs, pre-merge checks | Read-only; never deploy production |
| `push` to `main` | Build artifacts/release to staging | Staging OIDC if branch is protected |
| `workflow_dispatch` | Controlled manual runs | Environment approvals/input validation |
| `release` | Deploy a published release | Validate source tag/artifact/digest |
| `schedule` | Security scans/maintenance checks | Minimal GitHub/Azure permissions |
| `workflow_call` | Reviewed reusable workflow | Restrict inputs/secrets/permissions at caller |
| `pull_request_target` | Automation needing base repo context | **Dangerous** if checking out/running untrusted PR code |

### 3.2. Avoid triggering production from untrusted code

A safe pattern:

~~~text
PR from feature/fork:
  tests and static analysis only
  no Azure OIDC/id-token permission
  no production environment access

Protected main:
  CI + staging deployment, staging identity only

Production:
  reviewed environment with separate Azure identity
  deployment restricted by branches/release policy
~~~

With `pull_request_target`, workflows can run with base repository privileges. **Never check out and execute untrusted PR code using a token that holds write permissions or secrets**. Use this event only after reviewing the threat model for every action and checkout step.

### 3.3. Branch filtering, paths, and tags are not authorization

~~~yaml
on:
  push:
    branches: [main]
    paths:
      - 'src/**'
      - 'pom.xml'
      - '.github/workflows/deploy.yml'
~~~

`paths` trims unnecessary builds, yet it does not protect production. Someone with write access to `main` could edit the workflow file to change conditions. **Branch protection and GitHub Environment protection rules**, combined with Entra federated identity subjects, form the required authorization layers.

### 3.4. Concurrency per environment

~~~yaml
concurrency:
  group: staging-deploy
  cancel-in-progress: true
~~~

In staging, canceling older runs when new commits arrive may be desirable. In production, `cancel-in-progress: true` can **abort a rollout or migration mid-flight**. Use separate concurrency groups per environment with verified cancellation policies; never share one group across all environments.

## 4. GitHub → Azure authentication with OIDC, without long-lived secrets

**OpenID Connect federation** lets a GitHub workflow request a **short-lived OIDC JWT**, which Microsoft Entra validates against the **issuer, audience, and subject** of a federated identity credential. Entra issues an access token allowing the workflow to call Azure Resource Manager or authorized targets.

### 4.1. Chain of trust

~~~mermaid
sequenceDiagram
    participant GH as GitHub job
    participant OIDC as GitHub OIDC issuer
    participant ENTRA as Microsoft Entra ID
    participant ARM as Azure Resource Manager
    participant TARGET as Azure workload
    GH->>OIDC: Request job OIDC token (id-token permission)
    OIDC-->>GH: Short-lived signed JWT (repo/environment claims)
    GH->>ENTRA: Exchange JWT for Azure access token
    ENTRA->>ENTRA: Match issuer / audience / subject credential
    ENTRA-->>GH: Scoped Azure access token
    GH->>ARM: Deploy using Azure token
    ARM->>ARM: Enforce Azure RBAC
    ARM->>TARGET: Apply permitted resource operation
~~~

There are **two distinct checks**:

1. **Federated credential** determines which workflow identity can obtain a token for an Azure principal.
2. **Azure RBAC** determines what that principal can do on a specific subscription, resource group, or resource.

A matching federation does not grant deploy permissions; broad Azure RBAC Contributor access does not allow a workflow on an arbitrary branch to mint an OIDC token if the federated credential is tightly scoped.

### 4.2. Key claims

| Claim/field | Illustrative value | Role |
|---|---|---|
| **Issuer** | `https://token.actions.githubusercontent.com` | GitHub JWT issuer |
| **Audience** | `api://AzureADTokenExchange` | Standard Azure token exchange audience |
| **Subject** (environment) | `repo:acme/orders-api:environment:staging` | Workflow job bound to GitHub Environment `staging` |
| **Subject** (branch) | `repo:acme/orders-api:ref:refs/heads/main` | Workflow from `main` branch per subject format |
| **Principal/client ID** | Client ID of Entra app or user-assigned MI | Target identity for token exchange |
| **Tenant ID** | Azure tenant hosting the principal | Authentication boundary |
| **Subscription ID** | Subscription targeted by deployment | Azure management scope, not a credential |

**Crucial note:** If a job declares `environment: staging`, the default subject is typically `repo:ORG/REPO:environment:staging`, **not** the branch subject `ref:refs/heads/main`. Match the subject **precisely** to the workflow and policy; some organizations customize subject claims, so inspect the actual claim issued. **An environment-only subject does not restrict branches** unless environment protection rules do so; configure GitHub Environment branch restrictions and approvals.

### 4.3. Service principal or user-assigned managed identity?

OIDC federation works with either a **Microsoft Entra application/service principal** or a **user-assigned managed identity** in supported configurations:

- **Entra application:** create an app registration/service principal, add a federated credential, and assign Azure RBAC.
- **User-assigned managed identity:** create the identity, add a federated credential, assign Azure RBAC, and reference its client ID.

No client secret is needed with OIDC. A **system-assigned managed identity attached to an App Service or Azure runtime** does not automatically act as the GitHub workflow identity; CI needs a principal with federation configured. The runtime identity used by the app to access Key Vault/SQL/ACR is usually **separate** from the CI deployment identity to limit blast radius.

### 4.4. Conceptual setup flow

1. Create **GitHub Environments `staging`** and **`production`**, configuring required reviewers and deployment branch rules.
2. Create **two separate Azure identities** for staging and prod whenever possible.
3. On each Entra principal, create a federated credential with matching issuer, audience, and **exact Environment subject**.
4. Assign **least-privilege Azure RBAC** for the staging identity on staging resources and the production identity on production resources.
5. Store **client ID, tenant ID, and subscription ID** in GitHub **environment variables** (they are identifiers, not passwords).
6. Use `permissions: id-token: write` and `azure/login@v2` in the workflow to exchange tokens.
7. Test staging and inspect Azure Activity Logs / Entra sign-in logs to confirm permissions stay within scope.
8. Verify that approvals and branch restrictions block token issuance before production workflows run.

### 4.5. Minimal OIDC login YAML

~~~yaml
name: Azure OIDC smoke test

on:
  workflow_dispatch:

permissions:
  contents: read
  id-token: write

jobs:
  azure-whoami:
    runs-on: ubuntu-latest
    environment: staging
    steps:
      - name: Login to Azure
        uses: azure/login@v2
        with:
          client-id: ${{ vars.AZURE_CLIENT_ID }}
          tenant-id: ${{ vars.AZURE_TENANT_ID }}
          subscription-id: ${{ vars.AZURE_SUBSCRIPTION_ID }}
      - name: Confirm authorized scope
        run: |
          az account show --query "{name:name,id:id,tenantId:tenantId}" -o table
~~~

**`id-token: write` allows the workflow to request an OIDC token**; it does not grant Azure Contributor. **`contents: read`** grants the GitHub token read access to check out the repository, not Azure permissions. In production, pin the full commit SHA of `azure/login` and other actions; `@v2` is used here for readability.

### 4.6. Common federation failures

| Symptom | Cause | Fix |
|---|---|---|
| Cannot obtain OIDC token | Missing `id-token: write` | Add permission to the **exact job** logging in |
| Entra token exchange rejected | Issuer/audience/subject mismatch | Align federated credential with job environment/branch |
| Environment `staging` but credential uses branch `main` | GitHub subject is `environment:staging` | Create matching subject and enable environment rules |
| Azure login succeeds, deploy gets 403 | Missing Azure RBAC on target scope | Assign least-privilege role on exact resource |
| Login targets wrong subscription | Wrong GitHub vars/subscription selection | Verify tenant/subscription and resource IDs |
| Production job runs on PR | Missing trigger/job/branch restrictions | Separate CI from deploy with GitHub environment protection |
| Token exfiltrated externally | Untrusted action/script reads OIDC token | Action allowlisting/pinning, permission minimization |

**Never fix a failed federation by creating a client secret and storing it in GitHub Secrets** when the goal is passwordless OIDC; fix the policy, claims, or role assignment first.

## 5. Preparing Azure, GitHub, and permission boundaries

In the lab exercises, assume the team **already has**:

- A GitHub repository containing a Spring Boot/Maven application with a protected `main` branch.
- GitHub Environments `staging` and `production` with appropriate reviewers and branch policies.
- A staging Azure subscription/resource group and a production subscription/resource group (or approved equivalent boundaries).
- Provisioned Azure App Service or Container Apps with functioning Java runtime/container settings and DNS/health checks.
- An ACR instance for image workloads if using Container Apps/AKS.
- Two Microsoft Entra identities with federated credentials **matching each GitHub environment**, with RBAC scoped to each target.
- Read access to Azure Monitor / Application Insights / Activity Log for post-deploy verification.

**This lesson does not require creating new production resources.** If no tenant, subscription, or target app is available—or if you lack IAM permissions—perform the YAML/policy analysis and local unit tests without bypassing reviews via personal subscriptions or unauthorized accounts.

### 5.1. Separate CI principal from runtime identity

~~~mermaid
flowchart LR
    GH[GitHub workflow] -->|OIDC federation| DEPLOY[Deployment identity]
    DEPLOY -->|Azure RBAC scoped to target| ARM[Azure Resource Manager]
    ARM --> APP[App Service/Container App]
    APP -->|Runtime managed identity| KV[Key Vault]
    APP -->|Runtime database identity| DB[Azure SQL/PostgreSQL]
    APP -->|Runtime AcrPull if container| ACR[Azure Container Registry]
~~~

**Never grant the GitHub workflow identity permission to read all Key Vault secrets or query all database tables** just because the runtime application needs them. Deployment identities update resources/revisions; runtime identities access business dependencies; migration identities hold dedicated DDL permissions when required.

### 5.2. RBAC scoping

| Principal | Desired scope | Permissions to evaluate |
|---|---|---|
| GitHub staging deploy | Staging App Service/Container App and deploy dependencies | Built-in/custom role for required deploy operations |
| GitHub production deploy | Production app or scoped resource group | Avoid subscription-wide Contributor unless necessary |
| GitHub image publisher | ACR or specific repository | `AcrPush`/repository Writer per ACR auth mode |
| App Service/Container App runtime | Key Vault, Storage, Azure SQL as needed | `Key Vault Secrets User` / DB grants |
| Container App/AKS image pull identity | ACR | `AcrPull`/repository Reader |
| Database migration job | Target DB schema | DDL permissions per migration plan |
| Observability operator | Azure Monitor/Log Analytics | Read logs/metrics without modifying workloads |

**Azure RBAC Contributor does not automatically grant JDBC `SELECT` on Azure SQL** or PostgreSQL. Likewise, `AcrPull` does not grant image publishing rights.

### 5.3. Read-only Azure CLI example to inspect subscriptions

~~~bash
az account show --query "{name:name,id:id,tenantId:tenantId}" -o table
az resource show \
  --ids "<approved-target-resource-id>" \
  --query "{id:id,type:type,location:location}" \
  -o json
~~~

These commands do not deploy anything; they only confirm the target. Any `az role assignment create` or federation update requires IAM approval. Never copy role names or target resource IDs from staging to production blindly.

### 5.4. GitHub Environments and deployment branches

In repository settings, configure:

~~~text
Environment: staging
  deployment branches: main
  required reviewers: optional depending on team policy
  vars: AZURE_CLIENT_ID, AZURE_TENANT_ID,
        AZURE_SUBSCRIPTION_ID, AZURE_WEBAPP_NAME

Environment: production
  deployment branches: main or approved release tags
  required reviewers: platform/on-call/release owner
  vars: separate production identity and resource identifiers
~~~

**Environment protection capabilities can vary by GitHub plan, repository visibility, and org configuration**; do not assume an unconfigured UI setting acts as a real gate. For production approvals to hold value, verify submitters cannot alter workflows/protection rules or self-approve their own jobs against policy.

### 5.5. GitHub variables and secrets

- **`vars.AZURE_CLIENT_ID`, `vars.AZURE_TENANT_ID`, `vars.AZURE_SUBSCRIPTION_ID`:** non-secret identifiers; still protect write access to prevent misdirected deployments.
- **GitHub Secrets:** use for third-party credentials when OIDC is unavailable; audit, rotate, and restrict read access.
- **GitHub `GITHUB_TOKEN`:** auto-issued per job according to `permissions`; never store manually.
- **Azure managed identities:** no passwords in GitHub; federation issues short-lived tokens.
- **App runtime secrets:** use Key Vault/managed identity or secure secret injection on the hosting service—never bake into JARs or Docker images.

## 6. Designing multi-job pipelines: testing, artifacts, and deployment

### 6.1. Job graph with checkpoints

~~~mermaid
flowchart TB
    PR[Pull Request] --> TEST[Build + unit/integration tests]
    MAIN[Push protected main] --> TEST
    TEST -->|PASS| PKG[Publish immutable build artifact]
    PKG --> STAGING[Deploy staging with staging OIDC]
    STAGING --> SMOKE[Health + API contract smoke tests]
    SMOKE --> APPROVAL[Production Environment approval]
    APPROVAL --> PROD[Deploy same artifact with prod OIDC]
    PROD --> VERIFY[Validate production health/SLO]
    VERIFY -->|FAIL| ROLLBACK[Approved rollback / incident]
~~~

In YAML, use `needs` to declare dependencies. If any upstream job fails, downstream jobs normally do not run; this acts as a **release gate** without writing `if previous.status == failed` shell checks in every step.

### 6.2. Read-only CI for source code

~~~yaml
permissions:
  contents: read

jobs:
  build-and-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '21'
          cache: maven
      - name: Build and verify
        run: mvn --batch-mode --no-transfer-progress clean verify
~~~

**`setup-java cache: maven`** speeds up dependency downloads, **not** reproducible dependency locks or SBOMs. For projects with a Maven Wrapper, prefer a reviewed and checksum-verified `./mvnw`; the example uses runner Maven CLI for readability.

### 6.3. Separating build from deploy

For a Java JAR:

~~~yaml
- uses: actions/upload-artifact@v4
  with:
    name: orders-api-jar
    path: target/orders-api-1.0.0.jar
    if-no-files-found: error
    retention-days: 7
~~~

In the deploy job:

~~~yaml
- uses: actions/download-artifact@v4
  with:
    name: orders-api-jar
    path: dist
~~~

The JAR filename assumes project `orders-api` version `1.0.0` outputs that exact file. If Maven also produces `original-...jar`, use an explicit deterministic output path after packaging—**never deploy a wildcard matching multiple artifacts**. If a build runs on a PR, the artifact is untrusted until reviewed; never promote a PR artifact to production merely by matching its filename.

### 6.4. CI test matrix

For apps targeting PostgreSQL/SQL Server or multiple JDKs:

~~~yaml
strategy:
  fail-fast: false
  matrix:
    java: ['21']
    test-suite: [unit, integration]
~~~

A matrix needs **corresponding commands per `test-suite`**; `mvn verify` does not automatically switch test suites based on matrix names. Integration tests may require Testcontainers/Docker, database secrets, or private Azure networking; separate safe ephemeral PR tests from privileged Azure staging tests.

### 6.5. Never use cache as the production artifact source

Caches optimize dependency/builder reuse and are subject to eviction and misses. Release artifacts require **identity, integrity, and retention**: container images should pin digests; JARs need SHA-256 hashes, commit provenance, and download verification. Cache poisoning can occur across weak trust boundaries, so avoid restoring writable caches from untrusted workflows into privileged builds without controls.

## 7. Complete example: Maven → Azure App Service staging → production

Assume the project has:

~~~text
Repository: acme/orders-api
Protected branch: main
Maven output: target/orders-api-1.0.0.jar
Azure staging App Service: orders-api-staging
Azure production App Service: orders-api-production
Runtime: Java 21, Spring Boot
Environment vars: AZURE_CLIENT_ID, AZURE_TENANT_ID,
                  AZURE_SUBSCRIPTION_ID, AZURE_WEBAPP_NAME
Authentication: GitHub OIDC / separate identities per environment
~~~

**Two separate App Services** illustrate promotion without relying on deployment slots; slot swaps are covered later.

### 7.1. Self-contained workflow for a sample repository

Learners can create `.github/workflows/app-service-release.yml` in their own repository:

~~~yaml
name: Java App Service release

on:
  pull_request:
    branches: [main]
  push:
    branches: [main]
  workflow_dispatch:

permissions:
  contents: read

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout exact source revision
        uses: actions/checkout@v4

      - name: Set up Java 21
        uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '21'
          cache: maven

      - name: Compile and test
        run: mvn --batch-mode --no-transfer-progress clean verify

      - name: Publish verified JAR
        uses: actions/upload-artifact@v4
        with:
          name: orders-api-jar
          path: target/orders-api-1.0.0.jar
          if-no-files-found: error
          retention-days: 7

  deploy-staging:
    if: github.event_name != 'pull_request' && github.ref == 'refs/heads/main'
    needs: build
    runs-on: ubuntu-latest
    environment: staging
    permissions:
      contents: read
      id-token: write
    concurrency:
      group: orders-api-staging
      cancel-in-progress: false
    steps:
      - name: Download the exact build artifact
        uses: actions/download-artifact@v4
        with:
          name: orders-api-jar
          path: dist

      - name: Azure login via OIDC (staging)
        uses: azure/login@v2
        with:
          client-id: ${{ vars.AZURE_CLIENT_ID }}
          tenant-id: ${{ vars.AZURE_TENANT_ID }}
          subscription-id: ${{ vars.AZURE_SUBSCRIPTION_ID }}

      - name: Deploy JAR to staging App Service
        uses: azure/webapps-deploy@v3
        with:
          app-name: ${{ vars.AZURE_WEBAPP_NAME }}
          package: dist/orders-api-1.0.0.jar

      - name: Staging smoke check
        shell: bash
        env:
          APP_HOST: ${{ vars.AZURE_WEBAPP_HOSTNAME }}
        run: |
          test -n "$APP_HOST"
          curl --fail --silent --show-error --retry 4 --retry-delay 5 \
            "https://$APP_HOST/actuator/health/readiness"

  deploy-production:
    if: github.event_name != 'pull_request' && github.ref == 'refs/heads/main'
    needs: deploy-staging
    runs-on: ubuntu-latest
    environment: production
    permissions:
      contents: read
      id-token: write
    concurrency:
      group: orders-api-production
      cancel-in-progress: false
    steps:
      - name: Download the same build artifact
        uses: actions/download-artifact@v4
        with:
          name: orders-api-jar
          path: dist

      - name: Azure login via OIDC (production)
        uses: azure/login@v2
        with:
          client-id: ${{ vars.AZURE_CLIENT_ID }}
          tenant-id: ${{ vars.AZURE_TENANT_ID }}
          subscription-id: ${{ vars.AZURE_SUBSCRIPTION_ID }}

      - name: Deploy the approved JAR to production
        uses: azure/webapps-deploy@v3
        with:
          app-name: ${{ vars.AZURE_WEBAPP_NAME }}
          package: dist/orders-api-1.0.0.jar

      - name: Production smoke check
        shell: bash
        env:
          APP_HOST: ${{ vars.AZURE_WEBAPP_HOSTNAME }}
        run: |
          test -n "$APP_HOST"
          curl --fail --silent --show-error --retry 4 --retry-delay 5 \
            "https://$APP_HOST/actuator/health/readiness"
~~~

**Requirements for this example to actually run:**

1. Both App Services **already exist** with a Java 21 runtime supporting JAR deployment via `azure/webapps-deploy`; do not treat this example as an Azure provisioning script.
2. The Maven project produces `target/orders-api-1.0.0.jar` with a valid Spring Boot entry point.
3. The `staging` and `production` environments declare **matching variables**; the two client IDs/identities must not be shared.
4. Entra federated credentials must match `repo:ORG/REPO:environment:staging` and `...:production`, with environment protection rules restricting branches and reviewers.
5. Identities have sufficient Azure RBAC to deploy without exceeding scope; app runtime identities and DB permissions are configured separately.
6. The `/actuator/health/readiness` endpoint must be **configured, reachable from the runner**, and free of sensitive metadata. Private-only App Services require a private runner/network or internal health checks.
7. `workflow_dispatch` only deploys when the ref is `refs/heads/main`; releasing from tags requires dedicated trigger/ref policies and federation.
8. `@v4`/`@v3`/`@v2` are **illustrative major tags**, insufficient for supply-chain hardening; pin full commit SHAs of trusted actions in real repositories.

### 7.2. Why is this artifact promotion?

~~~text
build job:
  target/orders-api-1.0.0.jar
  → actions/upload-artifact (name: orders-api-jar)

deploy-staging job:
  download name: orders-api-jar
  → deploy JAR to staging
  → smoke passes

deploy-production job:
  download same name: orders-api-jar
  → deploy JAR to production
~~~

The production job **does not re-run Maven**. For stronger release assurance, add SHA-256 digests/signing and verify the artifact comes from the **exact GitHub workflow run that passed CI**, not merely a matching filename. Ensure artifact retention covers approval wait times, or publish to an immutable repository per policy.

### 7.3. Why not put `id-token: write` on every job?

PR CI jobs need no Azure access. Scoping `id-token: write` to **deploy jobs** rather than workflow-wide narrows the surface area where untrusted code or actions could request an OIDC token. Environment restrictions and federated credentials remain mandatory; GitHub token permissions do not replace Entra claims.

### 7.4. Production approval and audit

`environment: production` enables required reviewers when supported by plan/settings. In the sample workflow, approval is requested **before the production job starts** and before `azure/login` for production runs. If the production environment lacks protection rules, the job runs **automatically** right after staging. Verify production release policies **in Settings and via testing**, not merely by reading YAML.

### 7.5. When `workflow_dispatch` takes a release version input

Manual runs can be helpful, but free-form inputs like `resource_group`, `subscription_id`, or `script_to_run` invite target confusion and command injection if interpolated into shell commands. Prefer enumerated choices, protected environments, and existing immutable artifact digests—never let operators pass arbitrary PowerShell/Bash command strings.

## 8. Verifying and rolling back apps on App Service

### 8.1. Successful deploy ≠ healthy app

`azure/webapps-deploy` can finish uploading a package while Spring Boot still fails to start due to:

- Incompatible App Service Java/OS runtime for the JAR.
- Missing environment variables, Key Vault references, or database connections.
- Unfinished migrations or misconfigured database private DNS.
- Wrong startup command/port or blocked health endpoint.
- Slow JVM startup exceeding health probe timeouts.
- A new release spiking HTTP 500s, CPU, or memory.

Pipelines must execute **post-deploy smoke checks** and inspect traces/metrics rather than stopping at a green GitHub job.

### 8.2. Verifying the right release version

A protected `/version` endpoint might report:

~~~json
{
  "service": "orders-api",
  "commitSha": "cafebabe0123",
  "artifactSha256": "<sha256>",
  "buildTimeUtc": "2026-11-20T09:20:00Z",
  "environment": "staging"
}
~~~

Values are **illustrative**. Never expose secrets, tokens, internal database hostnames, or sensitive metadata on a public version endpoint. During production verification, compare the commit/artifact hash against the release manifest rather than checking only `200 OK`.

### 8.3. App Service rollback plan

When using **two independent App Services** as in Section 7:

1. Retain the **last known good JAR** in an artifact repository with sufficient retention.
2. When a production release malfunctions, pause further deployments.
3. Select the approved prior release by **immutable artifact identifier/hash**, without rebuilding `main`.
4. Redeploy the previous JAR using the authorized production identity under approval/break-glass policy.
5. Monitor health, 5xx rates, dependency latency, and business transactions.
6. If the database schema changed incompatibly, **binary rollback may fail**; apply expand/contract migrations or a controlled forward-fix.
7. Record the incident timeline, affected users, evidence, and follow-up improvements.

**A `git revert` is not an instant rollback**: it requires a fresh build/deploy and does not undo database writes that already occurred.

### 8.4. App Service deployment slots

When supported by the App Service plan, **deployment slots** let you stage a version in the same App Service app and then **swap traffic**:

~~~text
App Service production slot: v1 (receives customer traffic)
App Service staging slot:    v2 (smoke/warm-up)
    ↓
Approved slot swap:
production receives v2 after swap process
    ↓
Monitor; swap back only if safe and compatible
~~~

Illustrative Azure CLI command on an **existing lab resource with slots**—do not run without approval:

~~~bash
az webapp deployment slot swap \
  --resource-group "<approved-app-rg>" \
  --name "<approved-app-name>" \
  --slot staging \
  --target-slot production
~~~

**Slot-specific settings** (DB connections, env vars, identities, VNet integration) must be evaluated prior to swapping. "Swapping back" does not undo DB migrations or emitted events. For app slots, scope RBAC to the exact resource/slot rather than granting subscription-wide permissions.

### 8.5. What should smoke tests verify?

| Check | Objective |
|---|---|
| Readiness | Application can serve requests per dependency contracts |
| Version/digest | Matches the exact promoted artifact |
| Authentication | Production endpoints are not accidentally exposed anonymously |
| Read-only API | Business queries succeed within latency bounds |
| Controlled write test | Targets authorized test tenant/data only, with a cleanup plan |
| Database migrations | Schema version is compatible with no startup race conditions |
| Telemetry | Application Insights/Monitor receives fresh logs and traces |
| 5xx, p95, CPU | No regressions or canary alarms |

Never run write-heavy load tests against real production data just to validate a release. For private App Services, runners need a private route or rely on internal/synthetic monitors matching the topology.

## 9. From JAR to container: why Azure Container Registry?

For Azure Container Apps and AKS, the typical deployable artifact is an **OCI image** stored in a registry. Azure Container Registry (ACR) stores image manifests, layers, and tags; deployments reference a specific **image reference**.

### 9.1. Tags and digests

~~~text
Mutable tag (insufficient as a release identity):
  myacr.azurecr.io/orders-api:latest

Commit-based tag (better, still overwritable if registry policy allows):
  myacr.azurecr.io/orders-api:cafebabe0123

Immutable content reference:
  myacr.azurecr.io/orders-api@sha256:<digest>
~~~

The **digest** points to immutable manifest content. For **multi-architecture images**, the image index digest differs from per-platform image digests; choose the digest matching your deployment runtime and registry manifest. Security scans and provenance must bind to the **exact deployed digest**, not just a tag.

### 9.2. Dockerfile for a pre-built Spring Boot JAR

Assuming CI already built `dist/orders-api-1.0.0.jar`:

~~~dockerfile
FROM eclipse-temurin:21-jre-jammy

WORKDIR /app
COPY dist/orders-api-1.0.0.jar /app/orders-api.jar

RUN useradd --system --uid 10001 appuser
USER 10001

EXPOSE 8080
ENTRYPOINT ["java", "-jar", "/app/orders-api.jar"]
~~~

This is a minimal template without a pinned **base image digest**, resource limits, or JVM memory flags. In production:

- Pin trusted base images by digest and apply security updates regularly.
- Scan both JAR dependencies and OS packages in the image.
- Never `COPY .env` or cloud credentials into the image.
- Run non-root with a read-only filesystem if supported by the app.
- Build for the target architecture (`linux/amd64`/`linux/arm64`) required on Azure.
- Inject runtime settings/secrets via the hosting service rather than Docker build args.

### 9.3. CI push identity differs from runtime pull identity

~~~mermaid
flowchart LR
    GH[GitHub build-and-publish job] -->|OIDC| CI[Publisher identity]
    CI -->|ACR push permission| ACR[(Azure Container Registry)]
    ACA[Container App runtime] -->|Managed identity with ACR pull| ACR
    CD[GitHub deploy job] -->|Azure RBAC update app image| ACA
~~~

Maintain **three permission boundaries**: the publisher pushes images, the deployer updates the image config on the Azure resource, and the runtime pulls images. Never distribute ACR Admin credentials everywhere "to keep things simple."

### 9.4. ACR networking and access modes

- If the ACR public endpoint is restricted by firewall/private networking, the build runner needs a valid route.
- GitHub-hosted runners are not inside your corporate VNet by default.
- Container App/AKS runtimes need registry network reachability and a pull identity.
- ACR RBAC can use classic `AcrPush`/`AcrPull` or newer repository-scoped role modes; **do not mix role names without checking the registry's permission mode**.
- CI should not rely on admin credentials in GitHub Secrets when an OIDC/Entra path is supported.

## 10. Complete example: GitHub Actions → ACR → Azure Container Apps

This example takes the **exact tested JAR**, builds an OCI image once, pushes it to ACR with the commit SHA tag, captures the **digest output**, and deploys to staging and production using separate identities.

### 10.1. Configuration prerequisites

~~~text
GitHub environments:
  image-publish:
    OIDC publisher identity; vars ACR_NAME, ACR_LOGIN_SERVER
    AZURE_CLIENT_ID/TENANT_ID/SUBSCRIPTION_ID
  staging:
    separate OIDC deploy identity; vars AZURE_RESOURCE_GROUP,
    AZURE_CONTAINERAPP_NAME, AZURE_CLIENT_ID/TENANT_ID/SUBSCRIPTION_ID
  production:
    separate OIDC deploy identity; same kinds of vars

Azure:
  Existing ACR:       myacr.azurecr.io
  Existing Container Apps: orders-api-staging, orders-api-production
  Runtime registry pull: preconfigured managed identity/permissions
~~~

**If the production Container App uses a different ACR than staging**, a digest from registry A will not automatically exist in registry B. Replicate/import the image **by content digest** and verify identity/provenance before deploying; this sample assumes **one shared trusted registry** across both environments.

### 10.2. Workflow YAML

Learners can create `.github/workflows/container-apps-release.yml` in their own repo:

~~~yaml
name: Container Apps release

on:
  pull_request:
    branches: [main]
  push:
    branches: [main]

permissions:
  contents: read

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '21'
          cache: maven
      - name: Build and verify JAR
        run: mvn --batch-mode --no-transfer-progress clean verify
      - uses: actions/upload-artifact@v4
        with:
          name: orders-api-jar
          path: target/orders-api-1.0.0.jar
          if-no-files-found: error

  publish-image:
    if: github.event_name == 'push' && github.ref == 'refs/heads/main'
    needs: test
    runs-on: ubuntu-latest
    environment: image-publish
    permissions:
      contents: read
      id-token: write
    outputs:
      image_ref: ${{ steps.image-ref.outputs.value }}
    steps:
      - uses: actions/checkout@v4
      - uses: actions/download-artifact@v4
        with:
          name: orders-api-jar
          path: dist
      - uses: docker/setup-buildx-action@v3

      - name: Azure OIDC login for image publishing
        uses: azure/login@v2
        with:
          client-id: ${{ vars.AZURE_CLIENT_ID }}
          tenant-id: ${{ vars.AZURE_TENANT_ID }}
          subscription-id: ${{ vars.AZURE_SUBSCRIPTION_ID }}

      - name: Authenticate Docker to ACR
        shell: bash
        env:
          REGISTRY_NAME: ${{ vars.ACR_NAME }}
        run: az acr login --name "$REGISTRY_NAME"

      - name: Build and push one release image
        id: build
        uses: docker/build-push-action@v6
        with:
          context: .
          push: true
          platforms: linux/amd64
          tags: ${{ vars.ACR_LOGIN_SERVER }}/orders-api:${{ github.sha }}

      - name: Record immutable image reference
        id: image-ref
        shell: bash
        env:
          IMAGE: ${{ vars.ACR_LOGIN_SERVER }}/orders-api@${{ steps.build.outputs.digest }}
        run: |
          test -n "$IMAGE"
          echo "value=$IMAGE" >> "$GITHUB_OUTPUT"

  deploy-staging:
    needs: publish-image
    runs-on: ubuntu-latest
    environment: staging
    permissions:
      contents: read
      id-token: write
    concurrency:
      group: orders-api-containerapp-staging
      cancel-in-progress: false
    steps:
      - uses: azure/login@v2
        with:
          client-id: ${{ vars.AZURE_CLIENT_ID }}
          tenant-id: ${{ vars.AZURE_TENANT_ID }}
          subscription-id: ${{ vars.AZURE_SUBSCRIPTION_ID }}

      - name: Deploy by image digest
        shell: bash
        env:
          RG: ${{ vars.AZURE_RESOURCE_GROUP }}
          APP: ${{ vars.AZURE_CONTAINERAPP_NAME }}
          IMAGE_REF: ${{ needs.publish-image.outputs.image_ref }}
        run: |
          test -n "$IMAGE_REF"
          az containerapp update \
            --resource-group "$RG" \
            --name "$APP" \
            --image "$IMAGE_REF"

      - name: Verify staging revisions
        shell: bash
        env:
          RG: ${{ vars.AZURE_RESOURCE_GROUP }}
          APP: ${{ vars.AZURE_CONTAINERAPP_NAME }}
        run: |
          az containerapp revision list \
            --resource-group "$RG" --name "$APP" -o table

  deploy-production:
    needs: [publish-image, deploy-staging]
    runs-on: ubuntu-latest
    environment: production
    permissions:
      contents: read
      id-token: write
    concurrency:
      group: orders-api-containerapp-production
      cancel-in-progress: false
    steps:
      - uses: azure/login@v2
        with:
          client-id: ${{ vars.AZURE_CLIENT_ID }}
          tenant-id: ${{ vars.AZURE_TENANT_ID }}
          subscription-id: ${{ vars.AZURE_SUBSCRIPTION_ID }}

      - name: Promote exact image digest to production
        shell: bash
        env:
          RG: ${{ vars.AZURE_RESOURCE_GROUP }}
          APP: ${{ vars.AZURE_CONTAINERAPP_NAME }}
          IMAGE_REF: ${{ needs.publish-image.outputs.image_ref }}
        run: |
          test -n "$IMAGE_REF"
          az containerapp update \
            --resource-group "$RG" \
            --name "$APP" \
            --image "$IMAGE_REF"
~~~

### 10.3. Limitations and mandatory production additions

This workflow is an **educational skeleton**, not a complete production pipeline:

1. `Dockerfile` must `COPY dist/orders-api-1.0.0.jar`, and `.dockerignore` must not exclude `dist`.
2. `AZURE_CLIENT_ID`/`TENANT_ID`/`SUBSCRIPTION_ID` differ per environment/identity; environment protection rules restrict publish and prod.
3. The publisher needs ACR push, the deployer needs permission to update the exact Container App, and the runtime identity needs ACR pull. Both **role assignments and registry access** must exist.
4. The Container Apps resource must already have registry/identity, networking, runtime env, and readiness/liveness probes configured; `az containerapp update` does not provision dependencies.
5. The image must support the target architecture `linux/amd64`; if ARM64 is required, build multi-platform and test accordingly.
6. Add **security/SBOM/attestation gates** before publishing; scan source, dependencies, and images and verify the scanned digest.
7. Add **health/smoke/SLO checks** after staging and production; `revision list` only inspects revisions and does not prove the API is healthy.
8. Add a release artifact manifest, image signature/provenance, and rollback plan; validate that the image digest output from `build-push-action` is non-empty.
9. Pin full action commit SHAs in real repos; major tags here only help learners follow the structure.
10. For private ACR, runners need a private network path; never solve firewall errors by enabling the registry admin user.

### 10.4. Why avoid `az acr build` followed by deploying `latest`?

ACR Tasks can build images directly in Azure and are valid when properly architected. In this example, however, we need to **bind the tested image to a content digest**. If a pipeline rebuilds or deploys `latest`, release promotion can point to newer content than the approved commit. `docker/build-push-action` outputs the exact digest; alternatives like `az acr build` must likewise record and validate the digest through supported mechanisms.

### 10.5. Distinguish Azure ARM success from Container Apps revision success

After `az containerapp update`, verify:

- The new revision has the expected name and image digest.
- Replicas start, pull from ACR cleanly, and pass readiness checks.
- If using **multiple revision mode**, which version holds the traffic weights?
- Are app error rate, p95, CPU/memory, and business events within SLO?
- Is migration/backward compatibility handled while two revisions run concurrently?

Never treat exit code 0 from `az containerapp update` as proof that "production is serving traffic cleanly with zero errors."

## 11. Container Apps revisions, traffic splitting, and rollback

**Azure Container Apps** uses the **revision** concept—an immutable snapshot of application-template and configuration properties. Changing the image or revision-scoped properties creates a new revision. Traffic routing differs between **single revision mode** and **multiple revision mode**.

### 11.1. Single revision mode

~~~text
Revision v1 is active.
Deploy image digest v2.
Platform prepares new revision.
Traffic transitions according to revision/readiness behavior.
Observe application health and routing.
~~~

Advantage: simple for applications that do not need concurrent versions. However, it does not guarantee **zero downtime** for every workload: readiness, startup time, scaling, database compatibility, and ingress all matter. If the new revision is unhealthy, inspect rollout state and follow a rollback plan.

### 11.2. Multiple revision mode

~~~mermaid
flowchart LR
    USERS[Client traffic] --> INGRESS[Container Apps ingress]
    INGRESS -->|90%| V1[Revision v1: known good]
    INGRESS -->|10%| V2[Revision v2: canary]
    V1 --> DB[(Shared compatible database)]
    V2 --> DB
    OBS[Monitor errors/latency/business signals] -. metrics .-> V1
    OBS -. metrics .-> V2
~~~

You can deploy v2 and shift **traffic weights** gradually. Keep in mind:

- CLI syntax for adjusting traffic by revision or label depends on version; run `az containerapp ingress traffic set --help` and check real revision names.
- Health/smoke tests must target the specific revision or label, not just the production URL still pointing to v1.
- **Database migrations must be simultaneously compatible with both v1 and v2**.
- If v2 emits modified events, consumers need versioned schemas.
- "Setting v2 traffic to 0%" does not undo requests or data already processed.

### 11.3. Canary promotion plan

| Step | Illustrative v2 share | What to measure |
|---|---:|---|
| Preflight | 0% public | Revision up, image digest, internal smoke |
| Canary | 5% | HTTP 5xx, p95/p99, business validation |
| Pilot | 25% | Resource capacity, dependency errors, telemetry |
| Ramp-up | 50% | Database contention, queue lag, memory |
| Full | 100% | 24h SLO/incident monitoring per policy |

Percentages and windows are **examples**. Never apply fixed thresholds to payment or industrial control systems without SLOs and business owner sign-off.

### 11.4. Container Apps rollback

If revision v2 causes errors:

1. Halt promotion and record the image digest/revision and impacted traffic.
2. In multiple revision mode, shift traffic back to revision v1 **per policy** while v1 remains ready.
3. In single revision mode or if the prior revision is unavailable, redeploy the last-known-good digest.
4. Check image pull/registry reachability and runtime env.
5. Monitor live user traffic and business correctness, not just `revision list`.
6. Assess written data, message schemas, migrations/side effects, and reconciliation needs.
7. Preserve incident evidence and tighten release gates.

**A successful GitHub workflow deploy** and an **active Container App revision** are necessary conditions, not sufficient proof of a healthy business rollout.

## 12. AKS: direct deploy or GitOps?

With AKS, GitHub Actions can:

1. Build, test, and push an image to ACR.
2. **Deploy directly** via Helm/kubectl after valid OIDC Azure login and Kubernetes auth/RBAC.
3. Or follow **GitOps**: CI updates the desired image digest in Git, and Flux/Argo CD inside the cluster reconciles it.

### 12.1. Comparing the two models

| Dimension | GitHub Actions direct Helm deploy | GitOps controller reconciliation |
|---|---|---|
| Actor holding cluster access | GitHub runner / CI principal | Controller inside the cluster |
| Source of truth | CI commands/Helm release history + repo | Git desired state |
| Updating a private cluster | Runner needs network route to AKS API | GitOps controller pulls Git from inside cluster |
| Drift correction | Requires separate check/redeploy | Controller can reconcile automatically |
| Review | Workflow + Helm chart/values | PR into GitOps repo/overlay |
| Rollback | Helm rollback / redeploy digest | Git revert desired state + reconcile |
| Risk | Overly broad cluster permissions on runner | Over-privileged controller/repo or unsafe `prune` config |

**GitOps does not eliminate CI pipelines:** CI still builds, scans, attests images, and promotes digests. The difference lies in **who executes the deployment action**.

### 12.2. Direct Helm deploy: sequence of steps

If an organization chooses direct Helm and **AKS has Microsoft Entra integration/cluster RBAC properly configured**:

~~~text
GitHub job:
  azure/login@v2 with OIDC
     ↓
  az aks get-credentials for allowed cluster
     ↓
  kubelogin / Entra auth plugin when required
     ↓
  helm upgrade --install app with image digest
     ↓
  kubectl rollout status + service smoke checks
~~~

Illustrative commands **to be run only on an authorized lab cluster**, assuming `./charts/orders-api` exists and supports the corresponding values:

~~~bash
az aks get-credentials \
  --resource-group "<approved-aks-resource-group>" \
  --name "<approved-aks-cluster>" \
  --overwrite-existing

# Only when the cluster/runner auth model requires kubelogin.
kubelogin convert-kubeconfig -l azurecli

# Assumes the chart supports image.repository and image.digest.
helm upgrade --install orders-api ./charts/orders-api \
  --namespace orders --create-namespace \
  --set-string image.repository="<acr>.azurecr.io/orders-api" \
  --set-string image.digest="sha256:<approved-digest>" \
  --wait --timeout 10m

kubectl -n orders rollout status deployment/orders-api --timeout=5m
~~~

**Do not use `az aks get-credentials --admin` as a default workaround.** Cluster access has **two layers**: Azure permission to fetch kubeconfig (e.g., AKS Cluster User role) and **Kubernetes RBAC / Azure RBAC for Kubernetes authorization** for namespace/resource actions. Private API servers require a GitHub runner network route/VPN/private runner or choosing GitOps.

### 12.3. Helm values and digests

Charts should support:

~~~yaml
image:
  repository: myacr.azurecr.io/orders-api
  digest: sha256:<approved-digest>

replicaCount: 3

readinessProbe:
  httpGet:
    path: /actuator/health/readiness
    port: 8080
~~~

**This is a hypothetical values file**; Helm and Kubernetes have no built-in magic `image.digest` fields unless chart templates render `image: repo@sha256:...`. Review chart templates to avoid invalid image references or silently deploying stale tags.

### 12.4. GitOps/Flux for AKS

A GitOps repository:

~~~text
gitops/
  clusters/
    staging/
      orders-api/
        kustomization.yaml
        deployment.yaml  # image reference @sha256...
    production/
      orders-api/
        kustomization.yaml
        deployment.yaml
~~~

Post-CI workflow:

1. Record digest, SBOM, and provenance on the release artifact.
2. Open a PR updating the **staging** image digest in the GitOps repo.
3. The GitOps controller in AKS reconciles staging.
4. Combine GitOps health/reconciliation status with business smoke metrics.
5. Open a production promotion PR referencing the **exact same digest**.
6. Review, approve, and merge; the controller reconciles production.
7. Roll back via Git revert to an approved manifest/digest and verify in the cluster.

**Never let GitHub Actions push directly to the production branch using a broad write token bypassing PR protection** if the goal is an approval gate. Controllers need least-privilege namespace scope, secret/certificate management, and careful `prune` policies.

### 12.5. AKS workloads and ACR image pulls

A build identity with push rights does not automatically allow AKS nodes, kubelet, or workloads to pull images. Depending on identity and registry authorization mode, assign `AcrPull` or Repository Reader to the **kubelet identity/managed identity** or supported workload registry integration. Even when an image exists in ACR, `ImagePullBackOff` on a Pod can still result from private registry networking/DNS, invalid manifest references, or missing pull permissions.

### 12.6. Service traffic, migrations, and rollback in AKS

A new deployment can pass readiness yet cause downstream failures. Combine:

- Deployment rolling update `maxSurge`/`maxUnavailable`.
- Readiness, liveness, and startup probes.
- PodDisruptionBudget, HPA, and resource requests/limits.
- Ingress/gateway TLS and smoke tests along the real route.
- Deployment/Helm history or GitOps commit digests.
- Database expand/contract migrations and idempotent events.

Helm rollback does not automatically roll back database schemas or Service Bus messages already sent. For critical apps, use a canary controller, service mesh, or gateway traffic splitting per architecture rather than assuming Kubernetes Deployments give exact percentage-based canaries.

## 13. Azure Functions and non-container workloads

GitHub Actions is not limited to Spring Boot and containers:

| Azure workload | Typical artifact | Reference deploy method |
|---|---|---|
| **App Service (Java/JAR)** | JAR/ZIP build output | `azure/webapps-deploy` or Azure CLI |
| **Azure Container Apps** | ACR image digest | `az containerapp update` / IaC |
| **AKS** | ACR image digest + Helm/GitOps | Helm/kubectl or Flux |
| **Azure Functions** | Function app package/image | `Azure/functions-action` / supported CLI |
| **Static Web Apps** | Built web assets | Azure Static Web Apps action/workflow |
| **Azure VM/VMSS** | Script/package/image | IaC / extensions / approved deployment tooling |

For Azure Functions, build frameworks, hosting plans, trigger definitions, and package deployment differ from App Service Java web apps; **do not copy an `azure/webapps-deploy` workflow verbatim expecting the Functions runtime to discover triggers**. Verify action versions, identity/auth modes, Function app plans, deployment slots, and private networking independently.

### 13.1. Infrastructure deployment differs from application deployment

Pipelines often manage two layers:

~~~text
Infra (Bicep/Terraform):
  subscription/RG/VNet/ACR/App Service/Container App/AKS
  identities/RBAC/diagnostics

Application:
  JAR/image digest
  runtime configuration, deployment/revisions
  health and business checks
~~~

Every code push does not need to create or delete infrastructure. Infra applies need plans, approvals, and strict target isolation; app deploys should target **pre-provisioned resources** with constrained permissions. When using Terraform, protect state backends, locking, and drift; the GitHub OIDC identity for Terraform often differs from the app deployer.

## 14. Software supply chain: from source to trusted artifact

CI/CD is more than `mvn package` and `az ... update`. Attackers can tamper with dependencies, Docker base images, GitHub actions, build scripts, or release tags while the workflow still reports "green."

### 14.1. Pipeline threat model

~~~mermaid
flowchart TD
    S[Git source / PR] --> A[GitHub Actions code and dependencies]
    A --> B[Build tooling / package repositories]
    B --> C[Artifact and OCI image]
    C --> D[ACR / artifact store]
    D --> E[Deploy identity and Azure target]
    E --> F[Runtime + data]
    X[Attacker on fork / action / dependency] -. attempts influence .-> A
    X -. supply chain injection .-> B
    X -. artifact substitution .-> D
    DEF[Review, pinning, scanning, provenance, RBAC, signatures] -. protects .-> A
    DEF -. protects .-> C
    DEF -. protects .-> E
~~~

Complementary control points:

| Stage | Controls |
|---|---|
| **Source** | Protected branches, CODEOWNERS, signed commits if required by policy |
| **Workflow** | Review workflow files, allowlist actions, pin full commit SHAs |
| **Dependencies** | SCA/dependency review, lockfiles/constraints, license policy |
| **Build** | Ephemeral runners, reproducibility/provenance, no secrets in logs |
| **Artifact** | SHA-256/digest, SBOM, signing/attestations |
| **Registry** | Access controls, immutable references, retention, scan results |
| **Deploy** | OIDC least privilege, environment approvals, target allowlists |
| **Runtime** | Managed identities, policy, scanning, detection, rollback |

### 14.2. Pin actions by commit SHA

This lesson uses:

~~~yaml
- uses: actions/checkout@v4
- uses: azure/login@v2
- uses: docker/build-push-action@v6
~~~

These are **illustrative major tags**. In production, replace them with **reviewed full commit SHAs**:

~~~yaml
- uses: actions/checkout@<approved-full-commit-sha>
~~~

**The placeholder above is not runnable as-is.** SHA pinning prevents unexpected code changes compared to mutable tags; you must still monitor vulnerabilities and proactively update pinned SHAs. For third-party actions, review the publisher, source code, permissions, network egress, and secret access. Never pin an unvetted action assuming it is automatically safe.

### 14.3. Dependencies, SCA, and licenses

For Java:

- Manage and review Maven dependencies and BOMs.
- Enable SCA alerts or dependency reviews on PRs per repository policy.
- Never auto-merge major version updates to production without adequate test coverage.
- Generate SBOMs (e.g., CycloneDX/SPDX using approved tooling).
- Scan dependency CVEs and license restrictions against clear thresholds.

**SCA does not replace runtime vulnerability scanning**: a container can harbor vulnerable OS packages even when every JAR dependency is clean.

### 14.4. SBOM and provenance

A release can attach:

~~~json
{
  "service": "orders-api",
  "gitCommit": "cafebabe0123",
  "image": "myacr.azurecr.io/orders-api@sha256:<digest>",
  "sbomFormat": "CycloneDX or SPDX",
  "builder": "reviewed GitHub Actions workflow",
  "tests": ["unit", "integration", "security-scan"],
  "approvedEnvironment": "production"
}
~~~

This is **example release metadata**, not the default structure of formal attestations. Provenance should link **source revision, builder, artifact digest, and signed attestation** using supported tooling. Writing a plain JSON file into Git provides no integrity guarantee if an actor can modify both content and signature.

### 14.5. Artifact attestations and signatures

GitHub and OCI ecosystems provide artifact attestation, signing, and verification capabilities. Before deploying:

1. Generate SBOMs and scan reports for the artifact.
2. Emit provenance/attestation from a trusted pipeline builder.
3. Attach signatures to the **image digest**, not just the tag.
4. Verify signer, issuer, source repo/ref/commit, and artifact digest at the promotion gate.
5. Store evidence in an artifact store/registry/system with appropriate retention.

**Never assume `id-token: write` plus a `cosign sign` command is enough**: OIDC audiences, registry permissions, transparency logs, signer identities, and verification policies must be designed end-to-end. If using GitHub artifact attestations, check current action/API requirements, GitHub permissions, and supported artifact types.

### 14.6. Never run arbitrary scripts from PRs with deployment identities

A shell line like:

~~~bash
curl -fsSL "https://example.invalid/install.sh" | bash
~~~

is a dangerous pattern that **must not be executed**. Remote scripts can change and execute with full runner privileges, even reading OIDC tokens or GitHub secrets. Pin tools and package versions, verify checksums, use approved runner images, and never run code from untrusted branches with privileged tokens.

## 15. Hardening GitHub Actions workflows and GitHub token permissions

### 15.1. Declare explicit `permissions`

A CI-only workflow needs only:

~~~yaml
permissions:
  contents: read
~~~

A job deploying to Azure via OIDC:

~~~yaml
permissions:
  contents: read
  id-token: write
~~~

These permissions apply to **GitHub `GITHUB_TOKEN`/OIDC requests**, not Azure RBAC. If a workflow must create a release, tag, or pull request, grant that permission only on the **exact job that needs it** rather than granting `contents: write` or `pull-requests: write` workflow-wide.

### 15.2. Prevent shell injection from GitHub context

Interpolating PR- or user-controlled strings directly into shell scripts is dangerous:

~~~yaml
# DO NOT USE: PR titles can contain characters that alter shell logic.
- run: echo "PR title: ${{ github.event.pull_request.title }}"
~~~

Bind values to **environment variables** first instead of interpolating into shell source:

~~~yaml
- name: Print PR title safely
  shell: bash
  env:
    PR_TITLE: ${{ github.event.pull_request.title }}
  run: printf 'PR title: %s\n' "$PR_TITLE"
~~~

Still validate and escape inputs when constructing JSON, shell arguments, Terraform variables, image tags, or Azure resource names. Environment variables prevent expressions from turning into shell code, **but do not replace input validation**.

### 15.3. Data and credentials on runners

- Never run `printenv`/`env` or `set -x` where secrets or tokens may be present.
- Never print bearer tokens, ACR credentials, or Key Vault secret values.
- Avoid passing tokens in command-line arguments where process lists or logs might capture them.
- Clear temporary credentials and session contexts after jobs; never pass them to untrusted jobs.
- On self-hosted runners, clean workspaces, build caches, and credentials after runs, preferring ephemeral runners when possible.
- Never pass `.azure/`, privileged kubeconfigs, or connection strings inside job artifacts.

### 15.4. `workflow_run` and artifacts from untrusted workflows

A privileged workflow can trigger via `workflow_run` after a PR workflow finishes. That **does not make the PR's artifact or checkout trustworthy**. If a privileged job downloads an artifact produced by a PR and executes scripts or deploys it, an attacker can control that artifact. Enforce commit/ref checks, provenance, artifact signatures, and policies restricting builds to protected branches.

### 15.5. Reusable workflows and inherited permissions

`workflow_call` helps standardize deployment logic, provided you audit:

- Can callers pass arbitrary **image URIs, subscription IDs, or scripts**?
- Does the called workflow hold broad production permissions?
- How are secrets inherited or forwarded?
- Is the reusable workflow repo/ref SHA-pinned and protected?
- Which job enforces the environment approval?

A reusable "deploy-any-resource" workflow holding tenant-wide Contributor permissions can be riskier than 10 properly scoped separate workflows. Use typed inputs, target allowlists, separate identities, and policy restrictions.

## 16. Securing secrets, configuration, and runtime identities

### 16.1. Distinguish three data categories

| Category | Example | Appropriate management |
|---|---|---|
| **Non-secret configuration** | Environment name, resource group, client ID | GitHub Environment Variables / IaC |
| **Deployment token** | Short-lived OIDC JWT / Azure access token | GitHub OIDC + Entra; never persisted long-term |
| **Runtime secret** | DB password, API token, connection string | Azure Key Vault / managed identity / secret injection |

**Entra client ID, tenant ID, and subscription ID are identifiers**, suitable for `vars` rather than `secrets`, though edit permissions must still be protected. Swapping a client ID can cause **target confusion** or misdirected deployments even without leaking a password.

### 16.2. Runtime Key Vault references

App Service, Container Apps, and AKS offer different mechanisms for accessing Key Vault or injecting secrets. For Spring Boot, use a **runtime managed identity** with appropriate `Key Vault Secrets User`/RBAC scope rather than baking `spring.datasource.password` into a Dockerfile. An App Service Key Vault Reference can surface secret values into app settings, though refresh behavior, identity, and actual network paths must be verified; **a Key Vault Reference does not create a database principal or open a Private Endpoint**.

### 16.3. When are GitHub encrypted secrets still necessary?

External systems lacking federation support may still require secrets. In those cases:

- Choose the narrowest scope: organization, repository, or environment secret.
- Enable required reviewers for the production environment.
- Rotate/revoke periodically, audit access, and block untrusted PR access.
- Never place secrets into caches, artifacts, or logs.
- Rely on masking, but never treat masking as absolute DLP (transformed secrets may bypass masking).
- Migrate to OIDC/short-lived credentials whenever providers add support.

### 16.4. Separate CI secrets from database migrations

CI tests can use local PostgreSQL Testcontainers; production migrations require a dedicated identity and DB grants. Never pass production database passwords into **PR test jobs**, and never grant the runtime database role `DROP TABLE` just because the pipeline uses Flyway.

### 16.5. Secret scanning and incident handling

If a token or client secret is discovered in Git:

1. **Revoke/rotate** the credential at the issuing authority first.
2. Investigate Git history, caches, artifacts, and log exposure.
3. Inspect Azure Activity Logs, Entra sign-ins, and GitHub audit logs for abuse.
4. Scrub the secret from source via an approved process—avoid blind force-pushes that destroy forensic evidence.
5. Migrate to federation or an appropriate secret manager.
6. Add pre-commit/CI secret scanning and tighter repository protections.

Merely deleting the line in a new commit **does not invalidate an exposed secret**.

## 17. GitHub-hosted, self-hosted, and Azure private networking

### 17.1. Why can't hosted runners reach Private Endpoints?

~~~mermaid
flowchart LR
    GH[GitHub-hosted runner public network] -. no default private route .-> PE[Azure Private Endpoint]
    SH[Approved self-hosted/managed runner in VNet] --> VNET[VNet DNS/routing]
    VNET --> PE
    PE --> DB[(Azure SQL/ACR/private AKS API)]
    GH -->|Azure ARM public management endpoint if policy allows| ARM[Azure Resource Manager]
    ARM --> APP[Private workload resources]
~~~

**Management-plane deploys and data-plane health differ:** a GitHub-hosted runner can call Azure Resource Manager to update a Container App image even without a private connection to the app endpoint. However, it **cannot run integration tests against private Azure SQL**, curl internal HTTPS smoke endpoints, or push to a private-only ACR without private connectivity.

### 17.2. Choosing the right runner per job

| Job | Typical runner choice | Conditions |
|---|---|---|
| PR unit tests | GitHub-hosted | No secrets or production network access |
| Maven build + SCA | GitHub-hosted / ephemeral | Package registry access, cache security |
| Push to public ACR endpoint per policy | GitHub-hosted | OIDC + RBAC + allowed network |
| Push to private ACR | Approved VNet-connected runner | Private DNS/routing/registry access |
| Private-only Azure SQL integration tests | VNet runner or test service in Azure | Dedicated DB role/identity |
| Private AKS API server | VNet-connected runner or GitOps | Cluster RBAC and network path |
| Public App Service smoke | GitHub-hosted | Controlled HTTPS endpoint |
| Internal service smoke | Private runner / synthetic monitor | DNS/TLS/trust and least privilege |

### 17.3. Self-hosted runner threat model

Malicious PR code can taint a shared self-hosted runner workspace or steal credentials from subsequent jobs. Mitigations:

- Use **ephemeral runners per job** wherever possible.
- Separate runner groups and labels between untrusted CI and privileged deploys.
- Block fork PRs from triggering privileged runners freely.
- Harden the OS, Docker socket, filesystem, outbound network, and patching cadence.
- Scope runner identities/Azure access per job/environment—never leave perpetual Owner secrets on the host.
- Manage runner registration, revocation, inventory, and log retention.
- Restrict outbound destinations and monitor suspicious behavior without breaking required GitHub/Azure OIDC endpoints.

**Running a GitHub runner inside a Kubernetes Pod is not inherently safe** if the Pod mounts the host Docker socket or holds a privileged service account; evaluate supply-chain and cluster isolation.

### 17.4. Private DNS and identity

A working network path does not replace authentication: ACR push/pull still needs identity roles, Azure SQL still needs database grants, and AKS Kubernetes RBAC still checks permissions. Passing `nslookup` or `nc -vz` does not prove TLS hostname validation or credentials are valid.

### 17.5. Runner cost

GitHub-hosted minutes/concurrency/storage, self-hosted VM/AKS compute, egress, Docker caches, maintenance/patching, and private networking all incur costs. Choose runners based on **reliability, security isolation, and private connectivity**; do not move all unit tests onto self-hosted runners inside a production VNet just because one database integration job needs a private route.

## 18. Release gates and safe deployment strategies

### 18.1. A gate must have verifiable criteria

| Gate | Pass criteria | Failure handling |
|---|---|---|
| **Code review** | Required reviewers/branch protection, CODEOWNERS | Block merge |
| **CI** | Unit/integration tests green, valid artifacts | Block publish/deploy |
| **Security** | CVEs/secrets/license policy satisfied | Block or require timebound owner exception |
| **Artifact provenance** | Digest/signature/source verified | Block promotion |
| **Staging** | Correct revision/artifact deployed, smoke/metrics pass | Block production |
| **Production approval** | Environment reviewer/branch rules satisfied | Wait or reject release |
| **Canary** | Error rate/p95/business SLO within bounds | Roll back / halt traffic |
| **Post-production** | Health, customer metrics, audit events stable | Incident response |

A workflow showing "success" does not prove a release was approved if environment protections are unconfigured. Conversely, a reviewer clicking "Approve" does not replace security scans or health checks.

### 18.2. High-risk changes

- Breaking database schema changes.
- Unversioned message schemas.
- Auth, Key Vault, or VNet changes affecting the whole fleet.
- Container Apps traffic weight or AKS ingress changes.
- Runtime, JDK, or base OS image upgrades.
- CI OIDC federated credential or role assignment edits.
- Terraform/Bicep plans involving resource deletions.

For such changes, mandate **dedicated change reviews, staging validation, and backup/restore or rollback/forward-fix plans**—never rely on auto-deploy simply because unit tests pass.

### 18.3. Migrations must accompany application releases

Suitable sequence for Spring Boot + Azure SQL/PostgreSQL:

~~~text
Schema expand migration (approved, backward-compatible)
    ↓
New app v2 deployed to staging, tested on migrated schema
    ↓
Production migration with separate DDL principal
    ↓
Canary v2 while old v1 still works
    ↓
Full v2 rollout
    ↓
Contract migration removing old columns after safe window
~~~

**Never configure Flyway DDL auto-execution on every App Service/Container Apps replica with database owner credentials** if concurrent startups can lock or collide. If startup migrations are used, verify locking, permissions, and retry policies; in production, prefer a dedicated migration job.

### 18.4. Release freezes and break-glass

During an active incident, rapid rollback may be necessary. Break-glass access requires:

- Predefined principals/roles with audit logging and approval.
- Playbooks to redeploy a **known-good digest**.
- Strict user and time bounds.
- Automatic incident tickets and postmortem reviews.

Never implement break-glass by storing a permanent Azure Owner client secret in GitHub repository secrets.

## 19. Testing CI/CD: from unit tests to end-to-end on Azure

### 19.1. Test pyramid

| Layer | Objective | Execution |
|---|---|---|
| **Lint/config** | Workflow/YAML/Bicep/chart syntax and policy | PR workflow, no Azure write access |
| **Unit** | Java/Node/Python logic, no external dependencies | PR runner |
| **Local integration** | JDBC/Testcontainers, API contracts | PR runner with Docker |
| **Artifact/image** | Build, scan, SBOM, signature/digest | Protected branch |
| **Staging smoke** | TLS/auth, HTTP 2xx, dependencies, API version | Deploy staging + approved network |
| **Staging load/resilience** | p95, retry/backoff, scaling/failover | Controlled Azure staging |
| **Production canary** | Real-traffic errors/latency/business SLO | Limited scope and approval |
| **Post-deploy audit** | Release hash, logs/monitoring/Activity Log | Production observability |

### 19.2. Testing GitHub Actions configuration

On PRs:

1. Validate YAML schema and indentation using GitHub workflow-aware linters.
2. Check `permissions`, triggers, and environment/branch restrictions.
3. Flag unapproved actions or mutable tag references.
4. Check for untrusted GitHub expressions inside `run` blocks.
5. Lint Dockerfiles, IaC, and Helm schemas; check for hardcoded secrets.
6. Verify workflows issue Azure tokens only in deploy jobs.
7. Test release jobs in a lab/sandbox environment before granting production RBAC.

GitHub OIDC cannot be fully simulated locally with a plain shell script because the issuer, claims, and audience belong to a real GitHub job. Use a **minimally privileged staging smoke job** to verify federation.

### 19.3. Post-deploy REST checks

With Spring Boot Actuator readiness enabled:

~~~bash
APP_HOST="<approved-staging-hostname>"

curl --fail --show-error --silent \
  "https://$APP_HOST/actuator/health/readiness"

# If the app exposes a non-sensitive summary endpoint:
curl --fail --show-error --silent \
  "https://$APP_HOST/api/version"
~~~

If endpoints require authentication, use an **approved short-lived test identity/token**—never disable auth to make `curl` work. Never log raw responses that could contain PII.

### 19.4. HTTP 200 is not enough

A container can return 200 while 5% of DB queries fail, a queue consumer stalls, or a circuit breaker serves stale cached data. Verify:

- Image/JAR artifact ID and commit SHA.
- p95/p99 HTTP latency and 5xx rates.
- Database connectivity and transaction integrity.
- Service Bus / Event Hubs consumer lag where applicable.
- Application Insights logs and traces arriving properly.
- Active resource/revision/replica counts and readiness.
- Business KPIs: orders created cleanly without double-charging.

### 19.5. Testing rollbacks

In staging:

1. Release a known-good v1.
2. Deploy v2 containing a harmless simulated fault.
3. Trigger a failed deployment gate or canary halt.
4. Redeploy the v1 digest (or shift traffic back to revision v1).
5. Verify SLOs and data integrity after rollback.
6. Record recovery duration against RTO/RPO targets.

Never simulate faults by dropping production SQL tables or revoking critical Key Vault roles during active operations.

## 20. Observing releases with Azure Monitor and GitHub Actions

A deployment must be observed across **two planes**:

1. **Delivery plane:** which steps the GitHub job ran, which artifact/digest was used, and what commands Azure ARM accepted.
2. **Runtime/business plane:** whether the workload started, handles traffic, processes data, and meets SLOs/SLIs.

~~~mermaid
flowchart LR
    GH[GitHub Actions run] --> LOG[Workflow logs and deployment evidence]
    GH --> ARM[Azure resource update]
    ARM --> ACT[Azure Activity Log]
    ARM --> APP[App Service / Container App / AKS]
    APP --> APM[Application Insights/OpenTelemetry]
    APP --> MET[Azure Monitor metrics and resource logs]
    ACT --> DASH[Release dashboard/runbook]
    APM --> DASH
    MET --> DASH
    LOG --> DASH
~~~

### 20.1. What to record for every release?

~~~json
{
  "service": "orders-api",
  "environment": "production",
  "githubRepository": "acme/orders-api",
  "gitCommit": "cafebabe0123",
  "githubRunId": "123456789",
  "artifact": "myacr.azurecr.io/orders-api@sha256:<digest>",
  "deployedResource": "/subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.App/containerApps/orders-api-production",
  "approvedBy": "reviewed GitHub environment gate",
  "deployedAtUtc": "2026-11-20T09:30:00Z"
}
~~~

This is an **illustrative release evidence schema**. Do not assume GitHub or Container Apps generates this JSON automatically; your pipeline/release system must emit appropriate evidence, and `approvedBy` should come from actual audit data rather than hardcoding `"reviewed"` as proof of approval.

### 20.2. Release health SLOs

| SLI | Example lab threshold | What to measure |
|---|---|---|
| HTTP 5xx | No significant increase over baseline | Request count/denominator and window |
| p95/p99 latency | Below business threshold | Rolling windows with adequate sample size |
| Startup/readiness | Healthy before receiving traffic | Probe status / revision readiness |
| Dependency failures | No spike in DB/Key Vault/Service Bus errors | Traces/errors |
| Queue consumer lag | Within budget | Broker consumer metrics |
| Resource pressure | CPU/RAM/connection pools within headroom | App and DB metrics |
| Business KPI | No increase in duplicate orders/failed payments | Business telemetry |
| Rollback time | Within release RTO | Incident/automation timestamps |

Thresholds **must be tailored per workload**; never treat HTTP 200 alone as sufficient for an order-processing system.

### 20.3. Azure Activity Log and diagnostic settings

Azure Activity Log records **management-plane changes** such as updates to Container Apps, App Services, or RBAC. Resource logs and application traces must be configured separately via Diagnostic settings, Application Insights, or DCRs as appropriate.

Correlation chain needed:

~~~text
GitHub deployment run ID
     ↕ correlate by time/resource/actor
Azure Activity Log resource operation
     ↕ correlate by deployment/revision
Application Insights health and exception traces
     ↕ correlate by business eventId / traceId
Customer-facing SLO and transaction outcome
~~~

**An Azure Activity Log event does not prove every Spring Boot code path succeeded.** End-to-end verification is required.

### 20.4. KQL to inspect post-deploy resource changes

If the workspace is configured to ingest **subscription Activity Logs** into `AzureActivity`:

~~~kusto
AzureActivity
| where TimeGenerated > ago(24h)
| where ResourceGroup =~ "rg-orders-production"
| summarize Changes=count()
    by OperationNameValue, ActivityStatusValue
| order by Changes desc
~~~

Resource group, table, and column names are **examples**—check your actual schema; if Activity Logs are not exported to the workspace, the table will not exist. This KQL counts control-plane operations, **not directly the number of deployments**; a single deployment can emit multiple operations.

### 20.5. KQL for application error rate

With workspace-based Application Insights using `AppRequests` (when that schema is deployed):

~~~kusto
AppRequests
| where TimeGenerated > ago(1h)
| summarize
    Requests=count(),
    Failed=countif(Success == false)
  by bin(TimeGenerated, 5m)
| extend ErrorRatePercent =
    iff(Requests == 0, real(null), 100.0 * Failed / Requests)
| order by TimeGenerated asc
~~~

**Verify exact table and column names in your workspace**; Classic Application Insights and certain data collection routes use tables like `requests`. An interval with zero requests must not be interpreted as "0% errors and healthy service." Combine with synthetic monitors/heartbeats and canary traffic.

### 20.6. GitHub Actions logs must stay clean

Workflows should retain enough log detail to debug failed builds/deploys, while ensuring:

- Never print bearer tokens, client secrets, or SAS/connection strings.
- Never dump environment variables or configs containing credentials.
- Enforce retention limits balancing compliance and cost.
- Retain artifact digests, commits, target resource IDs, and failure reasons.
- Use GitHub Environments/approval audit logs to verify who approved releases.
- For container images, store original build provenance and digests rather than relying on `latest`.

### 20.7. Guarding against "pipeline green, production red"

A deployment job can succeed while tripling p95 latency or triggering DB errors. Without post-deploy gates, production suffers while the GitHub UI shows green. Design the response:

~~~text
Deployed release + 5-minute monitoring window
  → health/SLO within approved threshold?
       ├─ Yes: mark release healthy and continue observation
       └─ No: pause further promotion, notify on-call,
              rollback/traffic shift via approved runbook
~~~

Avoid auto-rolling back on every transient blip during low traffic, which can cause **flapping** between revisions. Choose sensible sampling windows, hysteresis, and an owner.

## 21. Troubleshooting GitHub Actions and Azure deployments

### 21.1. Symptom table

| Symptom | Common cause | Where to check |
|---|---|---|
| Workflow does not run on push | YAML syntax, branch/path filter, workflow disabled | `on` event/ref, GitHub Actions settings |
| PR CI runs without deploying | Intentional skip for non-`main`/untrusted PR | `if`/`needs`, environment policy |
| OIDC token request denied | Missing `id-token: write` | Job permissions |
| Azure login returns federated credential mismatch | Subject/issuer/audience mismatch | Entra credential and GitHub env/ref |
| Azure login succeeds, deploy gets 403 | Principal lacks Azure RBAC on target | Target ARM ID, role scope |
| Staging identity deploys to production | Wrong GitHub vars/identity mapping | Environment vars and Entra RBAC isolation |
| `upload-artifact` finds no files | Different Maven output path/version | `target` manifest, packaging, JAR name |
| Downloaded artifact is empty | Wrong name/job/run context/retention | Artifact metadata and `needs` |
| `webapps-deploy` succeeds, app returns 500 | Runtime/migration/config/port issue | App Service logs, readiness, App Insights |
| ACR Docker login denied | Principal lacks push role or wrong auth mode | ACR RBAC/ABAC, subscription/network |
| Docker build fails on `COPY dist...` | Artifact not downloaded or blocked by `.dockerignore` | Build context paths |
| Image built for wrong CPU arch | Mismatched target platform | Image manifest and workload architecture |
| Container App `ImagePullBackOff`/unhealthy revisions | Pull identity, ACR firewall, or image digest | ACR permissions, runtime logs |
| Container App updates ok, traffic stays on v1 | Multiple revision mode / traffic weights | Revision traffic config |
| Private AKS API timeout | Runner outside VNet or wrong DNS route | Runner placement/private DNS/NSG |
| AKS `kubectl` forbidden | Missing Kubernetes RBAC/Entra mapping | Namespace permissions; avoid `--admin` |
| Production approval does not appear | Environment rules disabled/unsupported | Repository Settings → Environments |
| Entra MI token expires in long job | Token lifetime / missing re-login | Auth step before deploy/reconnect |
| Workflow runs on fork with credentials | Unsafe events/permissions/`pull_request_target` | Trust boundaries and protected envs |
| SLO degrades post-deploy | Application regression or infra issue | Runtime metrics, release artifact/version |
| GitHub deploy cannot reach private ACR | Hosted runner lacks network path | Private runner / VNet route |
| Release tag points to different artifact than staging | Rebuild/push of mutable tag | Digest/provenance/hash comparison |

### 21.2. Ordered runbook

**1. Right workflow and ref?** Inspect repo, `github.ref`, event type, branch protection, and effective workflow YAML.

**2. Right job?** Was it skipped by `if`, did `needs` pass, and was the environment approved?

**3. Secure runner with proper networking?** GitHub-hosted or self-hosted, right architecture, registry/private endpoint reachability?

**4. Did CI actually test?** Maven output, test reports, scan results, artifact paths, and SHA?

**5. Does OIDC match?** Job `id-token: write`, federated credential issuer/audience/subject, and environment claim?

**6. Correct Azure RBAC on target?** Principal ID, subscription, resource group/resource ID, and ACR publisher/deployer/runtime roles?

**7. Exact artifact?** Downloaded JAR from the verified run, image digest matching provenance?

**8. Did Azure apply the change?** App Service version, Container Apps revision, AKS deployment/Flux sync?

**9. Are traffic and runtime healthy?** Readiness, 5xx/p95, dependencies, database migrations, image pulls?

**10. Rollback or forward-fix?** Halt promotion, preserve evidence, restore known-good artifact/digest, and verify business behavior.

### 21.3. Scenario: Azure login says "no matching federated identity"

Suppose the Entra federated credential specifies:

~~~text
repo:acme/orders-api:ref:refs/heads/main
~~~

While the job declares:

~~~yaml
environment: staging
~~~

The default GitHub OIDC subject for an environment job becomes:

~~~text
repo:acme/orders-api:environment:staging
~~~

Because the subjects mismatch, Entra rejects the token exchange. Fix this by creating a **federated credential matching the protected environment** and enforcing deployment branch rules. Never widen to a wildcard subject across all repos/branches just to make it pass.

### 21.4. Scenario: Azure login PASSES, Container Apps update gets 403

OIDC federation issued a valid Azure token, yet the principal lacks `Microsoft.App/containerApps/write` (or the equivalent action) on the target. Verify the principal object ID and minimal Azure RBAC scope. **Never add a GitHub secret holding subscription Owner.**

### 21.5. Scenario: ACR push succeeds, production cannot pull the image

The CI publisher holds push permissions; the runtime Container App or AKS cluster may lack `AcrPull`/repository reader, ACR firewalls/private endpoints may block runtime access, or the image digest/tag is wrong. Inspect **runtime identity and networking**, not just build job logs.

### 21.6. Scenario: Helm release `deployed` yet the site fails

Helm status may show manifests applied while readiness probes, Ingress, or database queries fail. Check `kubectl rollout status`, Pod events, ACR pulls, probes, service selectors, ingress TLS, app traces, and business smoke tests. **Never grant CI `cluster-admin` just to debug a broken deployment.**

### 21.7. Scenario: artifact overwritten

If a pipeline deploys `latest`, another job can push different content to that tag between staging and production. Fix: capture the digest from the image publish job, freeze release metadata, deploy by digest, and verify attestations/signatures. Enforce audit/policies blocking mutable tag promotion.

### 21.8. Scenario: production approval skipped

The workflow has `environment: production`, yet the GitHub Environment **lacks required reviewers**, or branch policies are misconfigured, so the job runs automatically. Fix this in GitHub repository/org settings, not just YAML. Test in a staging/protected sandbox and inspect workflow audit approvals before enabling production pipelines.

### 21.9. Scenario: private network blocks smoke check

Azure ARM deployment succeeds from a GitHub-hosted runner, then `curl https://internal-app...` times out. Never fix this by exposing production publicly. Use a VNet-connected self-hosted/managed runner, internal synthetic tests, or run smoke checks inside an Azure environment with an approved network path; verify DNS, TLS, and identity.

## 22. FinOps: CI/CD and Azure workload costs

### 22.1. Cost categories

| Component | Cost drivers |
|---|---|
| GitHub-hosted runners | Job minutes, runner size/concurrency per plan |
| GitHub artifacts/cache | Storage, retention, and billing per plan |
| Self-hosted runners | VM/AKS/Container compute, disk, patching, networking |
| Maven/package dependencies | Artifact repository storage, bandwidth/caching |
| ACR | Registry SKU, storage, data transfer, security scans |
| App Service | Plan instances, deployment slots, networking |
| Container Apps | vCPU/RAM, requests, revisions/replicas, log ingestion |
| AKS | Nodes, networking, storage, monitoring |
| Azure Monitor | App Insights/Log Analytics ingestion, retention, alerts |
| Databases and messaging | Compute, storage, connections, transactions |
| Private connectivity | NAT/Firewall/VPN/Private Endpoints/DNS charges |
| Security tooling | Scans, signing, attestations, secrets management |

**Current pricing depends on region, plan, date, reserved pricing, and usage**. Never lock in USD/per-run estimates without consulting GitHub billing and Azure Cost Management.

### 22.2. Estimating runner minutes

Suppose:

~~~text
40 PRs per day
CI checks average 6 minutes
22 working days per month
Each PR runs 1 comparable job
~~~

Logical runner time:

\[
40 \times 6 \times 22 = 5{,}280\ \text{runner-minutes/month}.
\]

If a workflow runs **4 parallel matrix jobs** taking 6 minutes each, total billable runner minutes approach **4 × 5,280 = 21,120** under similar assumptions—even though wall-clock time per PR does not quadruple. Billing multipliers depend on runner type and plan; use this calculation for planning only.

### 22.3. Controlled cost optimization

- Use `paths` and concurrency to avoid redundant CI runs without bypassing required security checks.
- Cache Maven/dependencies safely; never cache privileged tokens.
- Separate fast unit jobs from resource-heavy integration tests using sensible gates.
- Use ephemeral runners that shut down automatically when idle.
- Shorten artifact retention when not needed for release evidence or compliance.
- Prune old images/layers only after the **last-known-good rollback window** expires and with approval.
- Right-size Container Apps/AKS/App Service to load; avoid running production-sized infra indefinitely for ephemeral PR environments.
- Watch Log Analytics / App Insights debug volume; never log full HTTP bodies containing PII.
- Review database connection pools × replicas when scaling release workloads.

### 22.4. PR preview environments

Preview environments help UX reviews, but introduce cost and risk:

~~~text
PR opened → ephemeral test app with synthetic data
PR updated → redeploy preview
PR closed/merged → approved cleanup
Budget/quota limits → prevent abandoned environments
~~~

Never grant PR preview environments access to production databases, Key Vaults, or ACR publish identities. When provisioning preview infrastructure automatically, attach PR/owner tags, enforce TTL/cleanup reconciliation, and guard against deleting shared resources.

### 22.5. Cost guardrails

Budget alerts in Azure and GitHub are not always hard stops. Assign an owner to act on overages rather than scripting "auto-delete production resources" on bill spikes. Evaluate **cost per reliable release**: slightly higher testing/security spend is worthwhile if it prevents outages or data loss.

## 23. Case study: Spring Boot orders from commit to Azure Container Apps

### 23.1. Context

A company runs a Java 21/Spring Boot **`orders-api`** service using Azure SQL Database and Service Bus. They deploy containers to Azure Container Apps, store images in ACR, and monitor telemetry with Application Insights/Log Analytics. Security requires **no Azure client secrets stored in GitHub**, mandatory approval for production releases, and commit-level traceability for every image.

Technical requirements:

~~~text
Repository:             acme/orders-api
Protected branch:       main
CI:                     Maven unit + integration tests
Artifact:               orders-api JAR, Docker image digest
Registry:               private ACR with approved runner network path
Staging:                Container App + staging SQL/Service Bus identities
Production:             Container App + production identities
Auth GitHub → Azure:    OIDC federated credentials, separate identities
Release policy:         staging smoke + required prod approval + canary
Monitoring:             Azure Monitor, tracing, rollout dashboard
Failure recovery:       restore last-known-good image digest
~~~

### 23.2. Deployment flow

~~~mermaid
flowchart TB
    PR[PR with source and tests] --> REVIEW[Protected branch, CODEOWNERS, policy]
    REVIEW --> CI[Maven verify + SCA]
    CI --> ART[Upload JAR with commit]
    ART --> PUB[Build image + scan + SBOM/provenance]
    PUB --> ACR[Push ACR, record sha256 digest]
    ACR --> STAGING[Staging Container App revision]
    STAGING --> VERIFY[Smoke + DB/Service Bus tests + SLO]
    VERIFY --> GATE[Production Environment approval]
    GATE --> PROD[Production Container App canary]
    PROD --> FULL[Promote traffic after health gates]
    PROD -. Regression .-> ROLLBACK[Traffic to known-good revision]
~~~

### 23.3. IAM design

| Identity | Scope | Permissions |
|---|---|---|
| `gh-orders-image-publisher` | ACR registry/repo | Push images; cannot modify production apps |
| `gh-orders-staging-deployer` | Staging Container App | Deploy/read staging revisions |
| `gh-orders-production-deployer` | Production Container App | Deploy/read production revisions post-approval |
| `orders-staging-runtime-mi` | Staging ACR/Key Vault/SQL/Service Bus | Pull images, runtime data access |
| `orders-production-runtime-mi` | Production dependencies | Production-scoped; never uses staging MI |
| `orders-migration-principal` | Database schema | DDL migrations on approved runs |

**Never reuse the publisher identity as the runtime database principal.** If CI is compromised, an attacker should only reach limited image publishing or scoped resource updates—never direct read access to all customer data.

### 23.4. Details of release v1

1. Developer opens a PR; GitHub runs CI with `contents: read` and **no** `id-token: write`.
2. CODEOWNERS/reviews and security policies pass; PR merges to `main`.
3. CI builds `orders-api-1.0.0.jar` and saves the artifact with its commit SHA.
4. Publisher job uses Environment `image-publish`, authenticates to Azure via OIDC, pushes to ACR, and captures the digest.
5. Staging job receives the **image digest from the publisher job** without rebuilding.
6. Verify staging readiness, TLS, database identity, and Service Bus synthetic test messages in an isolated environment.
7. GitHub `production` Environment required reviewers approve the release.
8. Production deployer updates the Container App image digest.
9. In multiple revision mode, shift a fraction of traffic and watch HTTP/DB/business SLOs.
10. Record release evidence: commit, run ID, image digest, revisions, approver audit, and timestamps.

### 23.5. Incident: staging OIDC passes while production fails

Symptoms:

~~~text
staging:
  azure/login succeeds
  Container App update succeeds

production:
  azure/login fails token exchange
  no production changes applied
~~~

Root cause: the Entra production credential used subject `repo:acme/orders-api:ref:refs/heads/main`, while the job declaring `environment: production` emitted `repo:acme/orders-api:environment:production`. **Do not fix this with a wildcard subject**. Have IAM create the credential matching the protected environment, verify GitHub branch restrictions, and rerun the approved job.

### 23.6. Incident: image v2 pushed, production stays on v1

Possible causes:

- `deploy-production` was skipped by `if`/`needs` or awaiting approval.
- The job targeted the wrong Container App due to an altered environment variable.
- Digest v2 could not be pulled because the runtime identity lacked ACR permissions.
- Revision v2 started, yet **traffic weights** remained on v1.
- The deployment job updated the wrong resource group or subscription.

Trace from GitHub run → Azure identity → Azure resource/revision → traffic router → app telemetry. Never overwrite `latest` to "force" production to update, as that destroys release identity.

### 23.7. Incident: v2 runs the exact digest yet creates duplicate orders

Staging GET/health smoke tests passed, yet the production canary produced duplicate orders. The cause may be retries after timeouts once Service Bus/SQL transactions already committed, not a registry fault. Actions:

1. Pause promotion and shift traffic back to v1 per runbook.
2. Preserve version/digest info and traces for root-cause analysis.
3. Enforce unique idempotency keys in the database and outbox/consumer deduplication as required.
4. Never delete duplicate rows manually without owner and business reconciliation.
5. Fix the logic, test concurrent retries, and ship v3 with a new digest.

**Binary rollback does not undo data side effects** from requests already handled by v2.

### 23.8. Lessons from the case study

**Release safety is an unbroken chain of conditions**, not a single Deploy button:

~~~text
Protected source
→ trusted build
→ scanned/attested artifact
→ Azure OIDC least privilege
→ staging/runtime checks
→ approved production promotion
→ SLO-backed canary
→ auditable recovery
~~~

## 24. End-to-end lab: GitHub Actions pipeline to Azure

The lab can be practiced at two levels:

- **Lab A — no Azure resources:** inspect workflows, build/test Maven/JAR/Dockerfile in your own repo, analyze OIDC claims and RBAC without deploying.
- **Lab B — authorized Azure lab:** use real staging App Service or Container Apps, dedicated OIDC identities, a reviewed GitHub repo, and approved budgets/quotas.

### 24.1. Preflight checklist

| Requirement | Evidence |
|---|---|
| Repo/branch permissions | Repo URL, branch protection, CODEOWNERS |
| Workflow files reviewed | `.github/workflows/*.yml` PR reviews |
| Appropriate runner | GitHub-hosted or VNet runner per target |
| Maven/JDK | JDK 21 and reproducible Maven verify |
| Artifact | JAR path or Dockerfile/ACR repo |
| GitHub Environments | Staging/prod with proper protection rules |
| OIDC | Entra federated credentials with matching issuer/audience/subjects |
| Azure RBAC | Deploy identity scoped strictly to target |
| Workload | Existing, healthy App Service or Container App |
| Monitoring | Health endpoint/metrics/traces, release runbook |
| Budget | App/registry/runner costs governed |

### 24.2. Lab A — PR CI without Azure permissions

1. Create a feature branch and PR with a small change to a demo application.
2. Write a `pull_request` workflow holding only `contents: read`.
3. Use `actions/setup-java` Java 21 and `mvn verify`.
4. Confirm a test failure blocks artifact publishing.
5. Save the JAR with `upload-artifact` and inspect output metadata.
6. Verify the YAML contains no `AZURE_CLIENT_SECRET` or Azure login on PR jobs.
7. Explain why fork PRs must not run on protected production runners.
8. Review action pinning, dependency scanning, and caching risks.

**Expected outcome:** reproducible CI pass/fail, artifact tied to commit SHA, and zero Azure deployment rights in PR jobs.

### 24.3. Lab B1 — App Service staging

1. Use **read-only** Azure Portal/CLI commands to confirm the staging App Service resource ID and Java runtime.
2. Have IAM create the Entra principal and federated credential with subject `environment:staging`.
3. Assign required deploy RBAC on the **staging app resource** only; never broad production access.
4. Set `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID`, and `AZURE_WEBAPP_NAME` on the `staging` GitHub Environment.
5. Run the OIDC smoke job from Section 4 on the protected branch/environment.
6. Use the App Service workflow from Section 7 and verify the JAR build artifact.
7. Deploy to staging and check App Service logs and the health endpoint.
8. Verify the app commit/version endpoint matches the build run.
9. Inspect Azure Activity Log and Application Insights if configured.
10. Do not run production deployment unless production gates have been reviewed and approved.

### 24.4. Lab B2 — ACR and Container Apps

1. Verify `Dockerfile`, `dist/orders-api-1.0.0.jar`, and target architecture.
2. Have IAM create publisher/deployer identities and federated credentials per environment.
3. Grant ACR push to the publisher and ACR pull to the Container Apps runtime identity.
4. Enable the GitHub `image-publish` environment; ensure registry networking is reachable from the runner.
5. Build and scan the image, push with commit tag, and capture the output image digest.
6. Read back the registry manifest/digest before deploying.
7. Update the staging Container App using `repo@sha256:...`; inspect revision name, image reference, and readiness.
8. Test the API against synthetic dependencies or a staging database.
9. Define production environment approvals and separate identities.
10. With an approved canary, test revision traffic weights, SLOs, and rollback.

### 24.5. Read-only commands to verify Azure targets

~~~bash
az account show \
  --query "{name:name,id:id,tenant:tenantId}" -o table

# App Service, resource already known from Azure/IaC:
az webapp show \
  --resource-group "<approved-rg>" \
  --name "<approved-app-service-name>" \
  --query "{name:name,id:id,state:state,hostNames:hostNames}" -o json

# Container Apps:
az containerapp show \
  --resource-group "<approved-rg>" \
  --name "<approved-containerapp-name>" \
  --query "{id:id,name:name,latestRevisionName:properties.latestRevisionName}" \
  -o json

az containerapp revision list \
  --resource-group "<approved-rg>" \
  --name "<approved-containerapp-name>" -o table
~~~

These **read-only** commands require matching Azure CLI extensions/versions and permissions. Never add `--admin` upon encountering access denied. `latestRevisionName` may not equal the revision receiving 100% of traffic, especially in multiple revision mode.

### 24.6. Minimal test matrix

| Case | Condition | Expected | Evidence |
|---|---|---|---|
| PR1 | Normal PR | CI only; no OIDC Azure deploy | GitHub job permissions |
| PR2 | Unit test fails | No publish or deploy | Job graph |
| AUTH1 | Staging job, valid credential | Azure login succeeds | Azure principal/tenant/scope |
| AUTH2 | Production job without approval | No prod deploy access before gate | Environment audit |
| AUTH3 | Wrong subject | Entra token exchange denied | Federated claim mismatch |
| PERM1 | Staging principal tries modifying prod | Azure RBAC denies | 403 in authorized lab/sandbox |
| ART1 | Staging vs. prod artifact | Identical SHA/digest | Release metadata |
| ACR1 | Publisher pushes with proper role | Registry accepts image | Digest manifest |
| ACR2 | Container App lacks pull role | Revision fails clearly | Runtime/ACR diagnostics |
| NET1 | Hosted runner to private API | Blocked without route | DNS/network evidence |
| APP1 | Staging readiness passes | App serves lab traffic | Health + metrics |
| CAN1 | Canary breaches error threshold | Promotion halts / rolls back | Revision/traffic record |
| DATA1 | Non-backward-compatible schema migration | Gate blocks or forward-fix runs | DB integration tests |
| OBS1 | Production release | Monitor/Activity Log records event | Time/version correlation |

**Permission/network failure tests must run in a lab/sandbox** or via static policy checks—never deliberately break production to prove protections work.

### 24.7. Practicing with synthetic data

Example `/orders` payload in staging accepting synthetic events:

~~~json
{
  "orderId": "LAB-ORDER-001",
  "customerRef": "synthetic-customer",
  "items": [{"sku":"SKU-LAB","quantity":2}],
  "requestedAtUtc": "2026-11-20T09:20:00Z"
}
~~~

Never use real credit cards, production customer IDs, or send external emails/SMS in labs. If a pipeline triggers side effects, require idempotency keys and a cleanup strategy.

### 24.8. When is the lab complete?

The lab passes when:

- PR CI holds no Azure deployment privileges.
- Staging OIDC works and production identities/approvals are independent.
- Build artifacts have verified hashes/digests/commits without rebuilding on promotion.
- Staging App Service or Container App runs the exact release.
- GitHub, ARM, and runtime evidence agree on image or JAR versions.
- Workload health (readiness + API smoke) and post-deploy telemetry are verified.
- A rollback/incident plan is rehearsed with a **known-good artifact**.
- Logs, images, and repos contain no secrets/PII; Azure RBAC and networking are reviewed.
- A cost and cleanup plan exists for lab resources.

## 25. Comprehensive exercises and model answers

### 25.1. Theory and scenario questions

1. Distinguish **continuous integration, continuous delivery, and continuous deployment**.
2. Where do GitHub Actions workflows live in a repository and which events trigger them?
3. What are the differences between a job, step, action, and runner?
4. Why can't a `deploy` job automatically read a JAR built in the `test` job?
5. How do `actions/upload-artifact`/`download-artifact` differ from caching?
6. Why should you never deploy from an untrusted fork PR?
7. Why is combining `pull_request_target` with checking out/running PR code alongside secrets dangerous?
8. How do `GITHUB_TOKEN` permissions differ from Azure RBAC?
9. What does `id-token: write` do and what does it **not** do?
10. State the default issuer, audience, and subject for a job with `environment: staging`.
11. Compare branch subject `ref:refs/heads/main` against environment subject `environment:staging`.
12. If Entra reports a federated credential mismatch, what should you inspect?
13. If Azure login succeeds but deployment returns 403, at which layer is the fault?
14. Why are separate identities needed for staging and production?
15. Does declaring `environment: production` in YAML automatically enforce reviewer approval?
16. Is `vars.AZURE_CLIENT_ID` a secret? Should editing that variable still be protected?
17. List the Maven build/test steps before deploying to App Service.
18. How do you prove production runs the **exact JAR** tested in staging?
19. Does a successful `azure/webapps-deploy` prove the HTTP API is healthy?
20. How do App Service deployment slots aid rollouts/rollbacks, and what do they not roll back?
21. Why is the Docker image tag `latest` dangerous for promotion?
22. Compare a commit SHA tag against an ACR image `sha256` digest.
23. If the publisher has `AcrPush`, can the Container App automatically pull the image?
24. Why can't GitHub-hosted runners typically reach private ACR/AKS endpoints directly?
25. Compare Azure Container Apps single and multiple revision modes.
26. In multiple revision mode, what should you monitor before raising traffic from 10% → 100%?
27. How does direct Helm AKS deployment differ from GitOps/Flux?
28. Why should you not grant `az aks get-credentials --admin` to CI by default?
29. Which supply-chain risks do SBOMs, provenance, and attestations mitigate?
30. Why is pinning full action commit SHAs safer than mutable major tags?
31. What security vulnerability can occur if a PR title is interpolated directly into a Bash `run` block?
32. When a database migration is not backward-compatible, what risk arises from rolling back the JAR/image?
33. Why do production canaries need business KPIs beyond CPU and HTTP 200?
34. Is an Azure ARM 200 OK update sufficient to declare a release successful?
35. Distinguish readiness, liveness, application version/digest, and HTTP error rate.
36. Calculate runner-minutes for 40 PRs/day × 6 minutes × 22 days.
37. How does a 4-job matrix of 6 minutes each multiply runner-minutes?
38. Why does automated cleanup of ephemeral PR environments require resource tags and owner TTLs?
39. When OIDC tokens expire, why should you avoid switching to long-lived Azure client secrets as a quick fix?
40. Design an end-to-end release gate and rollback plan for an order-processing application.

### 25.2. Model answers: OIDC and permissions

**Q9:** `id-token: write` lets the GitHub job **request an OIDC JWT** from GitHub. Entra issues an Azure access token only if the JWT matches a federated credential; Azure RBAC then restricts operations. This permission **does not grant Contributor**.

**Q10:** Typical values:

~~~text
issuer:   https://token.actions.githubusercontent.com
audience: api://AzureADTokenExchange
subject:  repo:acme/orders-api:environment:staging
~~~

The subject must match the **actual repository**, environment, and any custom claims. Enforce environment branch/approval rules because an environment subject does not constrain branches by itself.

**Q12:** Verify repo/branch/environment, exact subject, tenant/client ID, issuer, audience, job `id-token: write`, and federation principal. Never open wildcards or grant subscription Owner.

**Q13:** Missing Azure RBAC action on the target resource scope, wrong resource/subscription ID, or wrong deploy identity. Federation only authenticates—it does not authorize arbitrary ARM actions.

**Q15:** No. Required reviewers and deployment branch rules must be configured **for real** in GitHub Settings under a supported plan. `environment: production` in YAML alone does not enforce approval.

### 25.3. Model answers: artifacts and deployment

**Q18:** Store the JAR binary with SHA-256/commit/run ID; the production job downloads the exact artifact from the **same workflow run** that passed tests and staging smoke checks. Never rebuild or pull a similarly named file from another run.

**Q22:** Commit tags link to source revisions, but can be overwritten if registry policies permit. A `sha256` digest references **content**, making it the reliable choice for deploying an exact image. For multi-arch images, distinguish index vs. platform digests.

**Q23:** No. The runtime needs its own ACR pull permission and registry network path. CI publisher push rights apply only to the publisher principal.

**Q27:** Direct Helm runs from a runner holding cluster access and Kubernetes RBAC; a GitOps controller inside the cluster reconciles desired state from Git. CI still builds, scans, and updates image digests in the GitOps repo.

**Q28:** `--admin` can bypass Entra/Kubernetes least-privilege models and expand CI blast radius; use cluster user credentials with properly scoped namespace authorization instead.

### 25.4. Model answers: security, operations, and cost

**Q30:** Tags like `@v4` can be moved by publishers to newer code; SHA pinning locks a specific commit. Regular security updates and allowlisting remain necessary.

**Q31:** Interpolating a PR title directly into Bash allows special characters to alter shell commands. Bind to `env` and validate/quote data before passing it to commands.

**Q32:** Altered/dropped DB columns can break older binaries; rollbacks do not revert data writes. Use expand/contract migrations and forward-fix/recovery plans.

**Q36:** `40 × 6 × 22 = 5,280` runner-minutes/month assuming one job per PR.

**Q37:** If 4 jobs run 6 minutes each per PR at the same volume, aggregate runner-minutes approach `21,120`, even though PR wall-clock time stays near 6 minutes; verify plan pricing multipliers.

**Q40:** Pipeline: protected source → CI tests → image/JAR digest + SCA/SBOM → OIDC staging deploy → smoke/traces/DB tests → required production approval → canary → SLO observation → traffic rollback / known-good digest and business reconciliation on failure. Never drop databases to roll back.

### 25.5. Rubric

| Criterion | Passing standard |
|---|---|
| **GitHub Actions fundamentals** | Correct triggers, jobs, steps, permissions, artifacts, and environments |
| **Azure OIDC** | Clear explanation of issuer, audience, subject, federated credentials, and RBAC |
| **Security** | PR trust boundaries, token least privilege, SHA-pinned actions, secret hygiene |
| **Artifact promotion** | Same JAR/image digest promoted staging → production with provenance |
| **Azure workload deployment** | App Service / Container Apps / AKS matched appropriately to context |
| **Operations** | Smoke checks, canary, monitoring, rollback, and database compatibility |
| **Networking** | Runner routes for private registries, clusters, and DBs evaluated |
| **FinOps** | Runner minutes, registry/artifact retention, and workload compute accounted for |

## 26. Production checklist: GitHub Actions → Azure

### 26.1. Repository and workflow governance

- [ ] `main`/release branches protected with reviews and required status checks.
- [ ] CODEOWNERS/mandatory reviews for `.github/workflows/**`, Dockerfiles, Terraform/Bicep, and Helm manifests.
- [ ] Workflow triggers match events/refs and never auto-deploy from fork PRs.
- [ ] `pull_request_target` never runs untrusted PR code alongside secrets or writable tokens.
- [ ] `permissions` declared minimally per job; PR CI uses `contents: read` only.
- [ ] `id-token: write` granted only to deploy jobs, not workflow-wide.
- [ ] Actions allowlisted/reviewed and pinned to full immutable commit SHAs.
- [ ] Reusable workflows reviewed with strict input constraints and target allowlists.
- [ ] Concurrency settings never cancel in-progress production releases or migrations.
- [ ] Logs, artifacts, and caches enforce retention/permissions and contain no tokens or PII.

### 26.2. OIDC / Entra / Azure RBAC

- [ ] GitHub Environments `staging`/`production` have tested reviewers and branch rules.
- [ ] Federated credentials' issuer, audience, and subject match actual jobs.
- [ ] Separate identities used for staging, prod, and publisher where feasible.
- [ ] Azure RBAC scoped minimally to target resources/registries—no blanket subscription Contributor.
- [ ] GitHub environment vars contain the exact client, tenant, and subscription IDs.
- [ ] No static Azure client secrets/passwords stored purely for workflow login.
- [ ] CI publisher separated from Azure runtime pull and database identities.
- [ ] Migration principal separated from runtime principal with exact DB grants.
- [ ] Procedures exist to revoke federations, rotate identities, and audit sign-ins.

### 26.3. Builds and artifacts

- [ ] Java/Node/Docker toolchains version-pinned with a build determinism plan.
- [ ] CI covers unit/integration tests, linting, and security checks.
- [ ] Dependency/SCA/license scanning has approved policy exception tracking.
- [ ] Container base images pinned/scanned; SBOM/provenance/signatures generated as required.
- [ ] Artifact hash/digest, commit, and run ID recorded and verified prior to promotion.
- [ ] Production **never rebuilds** artifacts already tested in staging.
- [ ] Docker images pinned by digest, not `latest` or mutable tags.
- [ ] Multi-architecture images match target CPU/OS.
- [ ] No secrets embedded in JARs, images, or CI logs.
- [ ] Last-known-good artifacts retained across the full rollback window.

### 26.4. Azure workloads and networking

- [ ] Target App Service / Container App / AKS already exists and is provisioned via reviewed IaC.
- [ ] OIDC deployment identity holds only required RBAC actions.
- [ ] Private endpoints, ACR, AKS, and SQL have matching runner/VNet/DNS routes.
- [ ] Container runtime image pull identity holds exact ACR pull permissions.
- [ ] Runtime managed identity accesses Key Vault, DB, and Service Bus with least privilege.
- [ ] SSL/TLS, secrets, custom domains, and network ingress/egress comply with policy.
- [ ] Readiness, liveness, and startup probes work without leaking sensitive metadata.
- [ ] Database/schema changes are backward-compatible with rolling revisions.
- [ ] Plans exist for Container Apps traffic weights, AKS rollouts, or App Service slot swaps.

### 26.5. Release gates and observability

- [ ] Staging smoke and contract tests execute over the proper network path.
- [ ] GitHub production required reviewers and protected branch rules are verified.
- [ ] Canary thresholds and rollback triggers bind to HTTP SLOs and business signals.
- [ ] Deployment verification checks the running image/JAR digest and active revision.
- [ ] Azure Monitor / App Insights / Activity Log correlate with GitHub release evidence.
- [ ] Action Groups, on-call rotations, and runbooks match severity levels.
- [ ] Rollout freeze, break-glass, rollback, and data reconciliation plans exist.
- [ ] Audit trails and ownership exist for production deploys, credentials, and policy changes.

### 26.6. Cost and recovery

- [ ] GitHub Actions minutes, concurrency, caches, and artifacts have budgets and retention policies.
- [ ] ACR storage/retention/scan costs, runner VMs, and private networking costs are accounted for.
- [ ] App Service / Container Apps / AKS scaling does not overwhelm database or queue budgets.
- [ ] PR preview resources have owners, TTLs, and cleanup isolated from shared resources.
- [ ] Backups/DR and restore tests satisfy business RPO/RTO targets.
- [ ] Rollback images, charts, and prior revisions are preserved until the safe window closes.
- [ ] Post-release cost reviews trigger action when budgets spike.

## 27. Safe lab cleanup and ownership handoff

After a lab, workloads, runners, ACR, identities, and environments may be **shared resources**. Cleaning up an experiment must never accidentally delete a production App Service, ACR registry, AKS cluster, GitHub Environment, or Entra principal used by other workflows.

### 27.1. Inventory resource layers

~~~text
GitHub:
  repository workflows, environments, variables/secrets, artifacts,
  runners, action permissions, branch protections

Microsoft Entra:
  federated credentials, app registration/user-assigned MI,
  role assignments

Azure:
  resource groups, App Service/slots, Container Apps/revisions,
  AKS, ACR images, Key Vault, SQL/Storage/Service Bus,
  Azure Monitor/Log Analytics and billing
~~~

**Finishing a workflow run does not automatically revoke an Entra federated credential** or role assignment; IAM configurations persist until an owner removes them.

### 27.2. Read-only Azure CLI commands

~~~bash
az account show \
  --query "{name:name,id:id,tenantId:tenantId}" -o table

az resource list \
  --resource-group "<approved-lab-rg>" \
  --output table

az webapp list \
  --resource-group "<approved-lab-rg>" \
  --query "[].{name:name,id:id,state:state}" \
  -o table

az containerapp list \
  --resource-group "<approved-lab-rg>" \
  --query "[].{name:name,id:id}" \
  -o table

az acr repository list \
  --name "<approved-lab-acr-name>" \
  --output table
~~~

These commands read metadata; some require matching Azure CLI extensions and roles. Do not confuse permission to list ACR repositories with permission to delete image manifests.

### 27.3. Cleanup checklist

1. Confirm **subscription, RG, environment, resource IDs**, and owner.
2. Check whether PR preview environments are still used for another team's review or testing.
3. Ensure release evidence, SBOMs, attestations, and logs requiring retention are archived.
4. Disable or delete only approved **lab-only** deployments/configs.
5. Never delete a shared App Service, Container App, AKS cluster, or ACR just to remove one version.
6. Evaluate old Container Apps revisions, ACR images/layers, and PR preview compute **against the rollback window**.
7. Revoke **lab-only** Entra federated credentials and role assignments when no longer needed; never touch shared production identities.
8. Remove unused lab GitHub Environment variables/secrets per approval; leave production branch protection untouched.
9. Check runner VMs, disks, container caches, and GitHub artifacts/retention.
10. Verify Azure Cost Management and GitHub billing show no orphaned lab resources.
11. Record actions taken, approver, and post-cleanup state.

### 27.4. Destructive commands not to run blindly in this lesson

~~~bash
# Commands illustrate risk scope only. DO NOT RUN BLINDLY.

# Deleting a resource group destroys every resource inside it.
# az group delete --name "<approved-lab-rg>" --yes

# Deleting an app/container can drop production traffic immediately.
# az webapp delete --resource-group "<rg>" --name "<app>"
# az containerapp delete --resource-group "<rg>" --name "<app>" --yes

# Deleting ACR images/tags can break rollbacks and offline image pulls.
# az acr repository delete --name "<acr>" --image "orders-api:<tag>" --yes
~~~

**An image not currently serving production traffic may still be needed for rollback** or offline pod restarts. Image cleanup must follow inventory, retention, and approval policies.

### 27.5. Post-cleanup verification

| Item | Required evidence |
|---|---|
| GitHub repo | Branch protection and production environment intact |
| Entra identities | Lab-only federations/roles revoked; production identities untouched |
| ACR | Rollback images intact; only lab tags pruned |
| Azure app workloads | Production versions and traffic remain healthy |
| Databases/queues | No real data deleted by cleanup |
| Monitoring | Logs, alerts, and retention follow policy |
| Billing | No orphaned runner or preview resources |
| Report | Owner, timestamp, and scope of changes recorded |

## 28. References and key takeaways

### 28.1. Official sources to verify before deployment

- [GitHub Actions documentation](https://docs.github.com/actions) — workflows, events, jobs, environments, permissions, and runners.
- [GitHub OpenID Connect with Azure](https://docs.github.com/actions/how-tos/secure-your-work/security-harden-deployments/oidc-in-azure) — OIDC issuer/audience/subject and Azure setup.
- [GitHub security hardening for Actions](https://docs.github.com/actions/security-for-github-actions/security-guides/security-hardening-for-github-actions) — token permissions, untrusted input, third-party actions.
- [GitHub environments for deployment](https://docs.github.com/actions/reference/workflows-and-actions/deployments-and-environments) — required reviewers and deployment branch rules.
- [Azure Login GitHub Action](https://github.com/Azure/login) — `azure/login` OIDC workflow and properties.
- [Azure Web Apps Deploy Action](https://github.com/Azure/webapps-deploy) — package deployment to App Service.
- [Microsoft Entra workload identity federation](https://learn.microsoft.com/entra/workload-id/workload-identity-federation) — federated credential trust.
- [Deploy to Azure App Service](https://learn.microsoft.com/azure/app-service/deploy-github-actions) — App Service/GitHub Actions integration.
- [Azure Container Apps documentation](https://learn.microsoft.com/azure/container-apps/) — revisions, traffic, identities, ACR.
- [Azure Container Registry authentication](https://learn.microsoft.com/azure/container-registry/container-registry-authentication) — registry access models and identities.
- [Azure Kubernetes Service documentation](https://learn.microsoft.com/azure/aks/) — Kubernetes RBAC, workloads, GitOps.
- [Azure Monitor](https://learn.microsoft.com/azure/azure-monitor/) — logs, metrics, alerts, Application Insights.
- [GitHub Docker build-push-action](https://github.com/docker/build-push-action) — building/pushing OCI images and digest outputs.
- [GitHub artifact attestations](https://docs.github.com/actions/concepts/security/artifact-attestations) — provenance, artifact integrity/verification.
- [Microsoft Azure Pricing Calculator](https://azure.microsoft.com/pricing/calculator/) — estimating Azure services by region/tier.

**Currency note:** Action major versions, GitHub OIDC custom subject capabilities, GitHub Environment protections, ACR ABAC roles, Azure CLI options, Container Apps revision behavior, and pricing can change over time. For production, verify **documentation and support matrices at deployment time**, pin tested action/image commits/digests, and rehearse in staging first.

### 28.2. Twelve core takeaways

1. **GitHub Actions orchestrates workflows**, while Azure hosting services own workload runtime and health.
2. **CI and CD have distinct permission boundaries**: PRs only test; protected branches/environments hold deploy rights.
3. **OIDC federation** lets GitHub authenticate to Azure without long-lived client secrets.
4. **Issuer, audience, and subject must match**—notably `environment:staging` differs from `ref:refs/heads/main`.
5. **Least-privilege Azure RBAC** scopes deployers to exact resources; runtime MIs and CI publishers remain separate.
6. **GitHub Environments need real protection rules**; writing `environment: production` in YAML alone does not enforce approvals.
7. **Build once, promote the same artifact**: JAR SHA-256 or OCI digest—never rebuild between staging and prod.
8. **App Service, Container Apps, and AKS release differently**: JARs/slots, revisions/traffic, and Helm/GitOps.
9. **Private networking is its own boundary**: GitHub-hosted runners cannot reach private Azure endpoints by default.
10. **Supply-chain controls matter**: pin actions, scan dependencies/images, emit SBOMs/provenance, and never run untrusted PR scripts with privileged tokens.
11. **Deploy success is not runtime success**: health, SLOs, business metrics, rollbacks, and DB compatibility are mandatory.
12. **FinOps and safe cleanup**: runners, registries, artifacts, preview environments, and monitoring all carry costs and owners.

### 28.3. Conclusion

A reliable **GitHub Actions and Azure workload deployment** workflow does more than build and invoke a deploy command. It must **bind commits to immutable artifacts, protect source code and runners, authenticate to Azure via OIDC under controlled GitHub Environments, assign least-privilege RBAC per task, roll out verified versions across staging and production, validate live health and business outcomes, and provide clear rollback, observability, and cost controls**.

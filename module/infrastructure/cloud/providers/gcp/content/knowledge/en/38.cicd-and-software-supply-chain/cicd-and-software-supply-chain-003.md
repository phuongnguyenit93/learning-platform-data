# Repository Connections and Cloud Build Triggers

A CI/CD pipeline needs to know where the source code lives, how to authenticate with the Git provider, and which events start a build. A repository connection establishes a controlled bridge between Google Cloud and source control systems such as GitHub, GitLab, or Bitbucket. A Cloud Build trigger listens for repository events, selects a build configuration, and starts the pipeline when conditions match.

Within the scope of **CLOUD_PROVIDERS_GCP**, this lesson places repository connections and triggers into the release workflow for applications running on Compute Engine, GKE, Cloud Run, and Google Cloud storage and data services. When connections and triggers are properly designed, teams can automatically test every pull request, package artifacts per commit, control releases by branch or tag, and retain evidence for each build run.

After this lesson, learners will be able to:

- Distinguish between host connections, repository links, and Cloud Build triggers.
- Choose the appropriate connection model between Developer Connect and Cloud Build repositories (2nd gen).
- Understand the status of Cloud Build repositories (1st gen) and Cloud Source Repositories.
- Create triggers for push, tag, pull request, and other events.
- Filter events by branch, tag, pull request, and file path.
- Configure builds with cloudbuild.yaml and use substitutions.
- Grant proper IAM permissions to connection administrators, trigger creators, and build service accounts.
- Protect pipelines from untrusted source code, exposed secrets, and overly broad deployment permissions.
- Monitor builds, troubleshoot connection issues, and test the CI/CD flow from commit to artifact.

## 1. Overview of the Repository Connection and Trigger Flow

Cloud Build cannot automatically read external repositories simply because the Cloud Build API is enabled in a project. You must first establish a connection with the Git provider, link a specific repository, and then create a trigger to map Git events to a build configuration.

~~~mermaid
flowchart LR
    A[Developer pushes or opens pull request] --> B[Git provider]
    B --> C[Repository connection]
    C --> D[Repository link]
    D --> E[Cloud Build trigger]
    E --> F[Build configuration]
    F --> G[Build service account]
    G --> H[Tests and package]
    H --> I[Artifact Registry]
    I --> J[Deploy stage or release workflow]
~~~

Components serve distinct roles:

| Component | Role | Example |
|---|---|---|
| Source provider | Hosts Git repositories and emits events | GitHub, GitLab, Bitbucket |
| Host connection | Connects a Git provider account/organization to Google Cloud | GitHub organization connection |
| Repository link | Links a specific repository belonging to a host connection | Link orders-api repo |
| Cloud Build trigger | Conditions and actions when receiving an event | Push to main runs build |
| Build config | Steps for testing, building, and pushing artifacts | cloudbuild.yaml |
| Build service account | Identity authorized to execute build steps | CI service account |

One host connection can serve multiple repository links. One repository can have multiple triggers, such as a pull request test trigger, a main branch build trigger, and a tag-based release trigger. Name them so operators can identify each trigger's purpose, environment, and repository.

## 2. Choosing How to Connect a Repository

Cloud Build currently supports next-generation connection flows through Developer Connect or Cloud Build repositories (2nd gen). Both allow Cloud Build to build from linked repositories and trigger builds on commits or pull requests. Connection management and some trigger types differ between them.

### 2.1. Developer Connect

Developer Connect provides connections and links to connect Git repositories outside Google Cloud. A connection represents the bridge to the Git provider; a link represents a specific repository selected within that provider.

Cloud Build can use repositories linked via Developer Connect to create triggers. Supported providers for the Cloud Build flow include:

- GitHub and GitHub Enterprise.
- GitLab and GitLab Enterprise Edition.
- Bitbucket Cloud and Bitbucket Data Center.
- Certain Enterprise or private network variants depending on the provider and connection guide.

When creating a repository link, Developer Connect sets up a webhook mechanism for the repository. This allows pushes or pull requests to fire triggers without the connection creator needing to re-authenticate at build time.

Developer Connect fits when an organization wants to manage Git integrations in a shared Google Cloud connectivity layer and use that repository across multiple services supporting Developer Connect.

### 2.2. Cloud Build Repositories (2nd Gen)

Cloud Build repositories (2nd gen) provide host connections and repository links dedicated to Cloud Build. Connections can be created and managed via Console, gcloud, API, or Terraform within the scope of supported providers.

The workflow includes:

1. Create a host connection to the Git provider.
2. Complete authentication or install the integration app according to the provider.
3. Select a repository and create a repository link.
4. Create a trigger referencing the linked repository.
5. Select the build config, region, and service account.

Cloud Build repositories (2nd gen) support GitHub, GitHub Enterprise, GitLab, GitLab Enterprise Edition, Bitbucket Cloud, and Bitbucket Data Center. This model supports triggers on branch push, tag push, and pull request; it also supports manual, Pub/Sub, and webhook triggers.

### 2.3. Comparing the Next-Generation Options

| Capability | Developer Connect repository | Cloud Build repositories (2nd gen) |
|---|---|---|
| Branch push, tag push, and pull request | Yes | Yes |
| Manual trigger | No in Developer Connect flow | Yes |
| Pub/Sub trigger | No in Developer Connect flow | Yes |
| Webhook trigger | No in Developer Connect flow | Yes |
| Manage connections via gcloud | Yes | Yes |
| Create connections with Terraform | Not a supported option in Cloud Build's capability table | Yes for some providers; exceptions include Bitbucket Data Center and Bitbucket Cloud |
| Regional connections and repository links | Yes | Yes |

Choose a model based on how your organization manages Git integrations and which trigger types you need. If you only need builds on push or pull request and want a shared integration layer, Developer Connect is a good fit. If you need to manage connections directly for Cloud Build or also need manual, Pub/Sub, and webhook triggers, evaluate Cloud Build repositories (2nd gen).

### 2.4. Cloud Build Repositories (1st Gen) and Cloud Source Repositories

Cloud Build repositories (1st gen) have been superseded by 2nd gen and are now a legacy option. When designing new architectures, evaluate 2nd gen or Developer Connect first.

Cloud Source Repositories (CSR) also has restrictions on onboarding new customers: since June 17, 2024, organizations that had never used CSR prior to that date cannot enable the API or begin using the service. Organizations already using CSR before this milestone are unaffected by the announced change and may continue using it under current terms.

Therefore:

- Do not design new onboarding guides assuming every project can enable CSR.
- For organizations currently using CSR, plan to maintain or migrate repositories to an appropriate Git provider.
- When encountering older documentation about mirroring GitHub/Bitbucket via CSR, check which legacy flow the document is describing.
- Do not confuse Cloud Build repositories (2nd gen) with Cloud Source Repositories; these are two different product names and connection models.

Google Cloud also offers Secure Source Manager with integrated Cloud Build triggers. This is a separately managed Google Cloud repository option; evaluate its support capabilities and your organization's deployment requirements.

## 3. Preparing Projects, APIs, and Access Permissions

Before creating a connection, determine which project owns the trigger, which region will be used, and which identity will execute the build. The person authorized to connect repositories does not necessarily need permission to deploy to production.

### 3.1. APIs and Projects

APIs commonly needed depending on architecture:

- Cloud Build API to manage triggers and run builds.
- Developer Connect API if using Developer Connect.
- Secret Manager API if connections or builds need secrets.
- Artifact Registry API if the pipeline stores images or packages in Artifact Registry.
- Target service APIs such as Cloud Run, GKE, or Compute Engine if the pipeline deploys.

If connections and triggers reside in different projects, clearly identify the connection-owning project, the build-executing project, and the artifact-storing project. Cross-project IAM configurations must be verified separately.

### 3.2. Connection Administrator Permissions

The person creating a connection needs permissions to manage connections in Google Cloud and appropriate permissions at the Git provider to install/authorize the integration app or select repositories.

Common roles:

| Role | Usage Scope |
|---|---|
| roles/developerconnect.admin | Administer Developer Connect resources, including connections and repository links |
| roles/developerconnect.user | Use connections and interact with repositories per granted permissions |
| roles/cloudbuild.connectionAdmin | Create, update, and delete Cloud Build 2nd gen connections and repositories |
| roles/cloudbuild.connectionViewer | View connections and linked repositories |

The specific role needed depends on the connection model. Do not grant every administrative role simultaneously just so someone can pick a repository.

### 3.3. Trigger Creation Permissions

Trigger administrators need corresponding permissions on Cloud Build. When a trigger uses a user-managed service account, the user creating or updating the trigger also needs permission to impersonate the service account, typically via:

- Cloud Build Editor or a custom role with the required trigger management permissions.
- roles/iam.serviceAccountUser on the selected service account to obtain iam.serviceAccounts.actAs permission.

Permission to create triggers and permission to run builds are two separate concerns. A user may be allowed to configure triggers, while the build service account still needs separate permissions for each action it executes.

### 3.4. Build Service Account Permissions

Create dedicated service accounts for each pipeline group or environment, for example:

- ci-test: read source and run tests.
- ci-build: build images and push them to a specific Artifact Registry repository.
- cd-staging: deploy to staging.
- cd-production: deploy to production after approval.

Grant only the permissions the build genuinely needs. For example, an image-building pipeline may need Artifact Registry Writer on the destination repository; a Cloud Run deployment pipeline needs service deployment permissions and actAs permission on the runtime service account as designed. Never grant Owner or Editor to a build service account just to bypass permission errors.

Cloud Build has changed how default service accounts are selected based on organization configuration. Some projects use the Compute Engine default service account, while others still allow the legacy Cloud Build service account. Therefore, verify the trigger's actual service account and explicitly specify a user-managed service account when clear permission control is required.

When a trigger uses a user-specified service account, configure an appropriate build log storage location, such as Cloud Logging with the corresponding logging option or a user-managed Cloud Storage bucket. Verify that the service account has permission to write logs.

## 4. Creating a Repository Connection

Detailed steps may vary by Git provider, but the core workflow is similar.

### 4.1. Connecting from the Google Cloud Console

1. Select the project that will manage the connection.
2. Open Developer Connect or Cloud Build Repositories depending on the chosen model.
3. Select a region for the host connection.
4. Select the Git provider, such as GitHub or GitLab.
5. Start the authentication/app installation flow guided by Google Cloud.
6. Select the organization or account to connect at the Git provider.
7. Restrict which repositories the app is allowed to access per organization policy.
8. Finish creating the connection and verify its connection status.
9. Select a specific repository to create a repository link.
10. Give the link a clear name and verify the repository can be listed/read.

Connections and links must be created in a supported region. Triggers reference connections/links by location; therefore, choose a consistent region from the start and document it clearly in operational guides.

### 4.2. Connecting with GitHub

For GitHub, a user with organization admin permissions or appropriate privileges can install the Google Cloud-provided GitHub App. During installation, select specific repositories or the entire organization per policy.

Prefer granting the app access only to repositories that need builds. If there are multiple product teams, separate connections or access scopes can be created to limit blast radius if one connection is revoked.

After installing the app:

- Verify the GitHub App is installed on the correct organization.
- Verify the desired repositories are within the app's scope.
- Link the repository into the right Google Cloud project and region.
- Verify that pushes or pull requests can emit events to Cloud Build.

### 4.3. Connecting with GitLab or Bitbucket

GitLab and Bitbucket have their own authorization, app installation, or connection setup steps. For GitLab Enterprise, Bitbucket Data Center, or systems on private networks, verify DNS, firewalls, TLS, connectivity paths, and guides for that exact provider type.

Do not follow a GitHub guide to configure GitLab or Bitbucket just because all three use Git. Token issuance, repository permissions, webhooks, and network scope mechanisms can differ.

### 4.4. Connecting Private Network Repositories

Enterprise repositories may live on private networks or on-premises. Two network paths must be identified:

1. The path for Developer Connect/Cloud Build to connect to the Git host to authenticate, read metadata, and receive events.
2. The path for build workers to reach required private dependencies during builds, such as private package registries, internal artifact stores, or private endpoints.

Cloud Build private pools address the need to run builds in a controlled network and access private resources as designed. A private pool does not automatically establish connectivity to every Git host. Verify repository connectivity requirements and build worker network requirements separately.

## 5. How Cloud Build Triggers Work

A trigger is a configuration linking an event, source code, build config, region, service account, and additional conditions. When a matching event arrives, Cloud Build creates the corresponding build.

### 5.1. Repository Event Trigger Types

| Event Type | When It Runs | Example |
|---|---|---|
| Branch push | New commits pushed to a branch matching filter | Push to main |
| Tag push | New tag pushed matching pattern | v1.4.0 |
| Pull request | Pull request created/updated per provider config | PR targeting main |
| Manual | Operator manually invokes the trigger | Re-run release candidate |
| Pub/Sub | Message published to the selected topic | New image in Artifact Registry |
| Webhook | Webhook endpoint receives matching event | External Git system or tool sends event |
| Scheduled manual | Cloud Scheduler invokes manual trigger on schedule | Periodic verification build |

Not every trigger type is available on every repository connection model. Developer Connect-linked repositories support repository events such as branch push, tag push, and pull request; manual, Pub/Sub, and webhook triggers are capabilities listed for Cloud Build repositories (2nd gen).

### 5.2. Branch and Tag Filters

Triggers can restrict branches or tags using patterns. Examples:

- Branch pattern: main.
- Branch pattern: release/*.
- Tag pattern: v*.
- Tag pattern: v[0-9]* if you want to restrict to a matching tag structure.

Patterns are evaluated using the syntax supported by the trigger UI or API. Test with real branch/tag names, especially when using wildcards or complex expressions.

A production trigger should not run on every branch. Select protected branches with required reviews and merge controls before allowing a trigger to hold deployment permissions.

### 5.3. Pull Request Triggers

Pull request triggers are suitable for running lint, unit tests, dependency checks, trial builds, or code analysis before merging.

Conditions to consider:

- Target branch of the pull request.
- Source repository of the pull request, including forks if permitted by the provider.
- Pull request creation or update events.
- Comment control mechanisms if an authorized repository member must confirm the build.
- Service account permissions and which secrets the build can access.

Builds triggered from pull requests can execute code submitted by the PR author. If the service account has permissions to read secrets or deploy to production, an untrusted PR could attempt to exploit those permissions. Therefore, PR triggers should use a service account with test-only permissions that cannot read production secrets or deploy to production.

With GitHub pull request triggers, comment control can require a repository owner or collaborator to comment `/gcbrun` before the build starts. This is an additional control layer; you still need branch protection and restricted service account permissions.

### 5.4. Filtering by Changed Files

Triggers can use included files and ignored files to limit builds by modified paths. Examples:

- Run only when `services/orders/**` changes.
- Ignore `docs/**` when the pipeline does not need to rebuild the application.
- Run the shared pipeline when `cloudbuild.yaml` or `shared-libraries/**` changes.

When using path filters, account for renamed files, deleted files, or pull requests touching multiple directories. A change in a shared library can affect multiple services even if a service's directory did not change. Overly strict filters can cause triggers to miss important changes.

## 6. Configuring Builds with cloudbuild.yaml

The build config describes the steps Cloud Build executes after a trigger fires. The file is usually placed at the repository root or at a path declared in the trigger.

A build config can include:

- steps: commands or builder containers to run.
- images: images pushed to the registry after a successful build.
- artifacts: configuration for storing other artifacts in supported formats.
- substitutions: variables substituted at build time.
- options: build settings such as logging, machine type, or other options.
- timeout: maximum duration for the build.
- availableSecrets/secretEnv: how secrets from Secret Manager are passed to required steps.

### 6.1. Example: Building and Testing a Java Application

The following example runs Maven tests, packages an image, and pushes it to Artifact Registry. The Artifact Registry repository must be created beforehand; the trigger selects a service account with write permissions to that repository.

~~~yaml
steps:
  - name: maven:3.9-eclipse-temurin-21
    entrypoint: mvn
    args: ["-B", "test"]

  - name: gcr.io/cloud-builders/docker
    args:
      - build
      - -t
      - $_AR_REGION-docker.pkg.dev/$PROJECT_ID/$_AR_REPOSITORY/$_IMAGE:$SHORT_SHA
      - .

images:
  - $_AR_REGION-docker.pkg.dev/$PROJECT_ID/$_AR_REPOSITORY/$_IMAGE:$SHORT_SHA

substitutions:
  _AR_REGION: asia-southeast1
  _AR_REPOSITORY: app-images
  _IMAGE: orders-api

options:
  logging: CLOUD_LOGGING_ONLY

timeout: 1200s
~~~

In this example:

- The Maven step runs tests before building the image.
- The Docker builder packages the source into an image.
- The images field instructs Cloud Build to push the built image to Artifact Registry after steps succeed.
- SHORT_SHA is a default trigger substitution containing the first seven characters of the commit SHA.
- Custom variables begin with an underscore, such as _AR_REGION.
- logging is set to CLOUD_LOGGING_ONLY so build logs flow into Cloud Logging.

This example is a starting configuration; adjust builder images, Java version, Maven wrapper, Dockerfile path, and Artifact Registry names to match your real repository. Do not use this same build config for untrusted PRs if the service account can push release images; use a separate trigger/config for pull request verification.

### 6.2. Build Steps and Execution Order

By default, build steps execute sequentially in list order. When a step fails, the build normally stops and is marked failed. You can use waitFor to allow independent steps to run in parallel.

Example:

~~~yaml
steps:
  - id: unit-tests
    name: maven:3.9-eclipse-temurin-21
    entrypoint: mvn
    args: ["-B", "test"]

  - id: lint
    name: maven:3.9-eclipse-temurin-21
    entrypoint: bash
    args: ["-c", "./scripts/lint.sh"]

  - id: package
    name: maven:3.9-eclipse-temurin-21
    waitFor: ["unit-tests", "lint"]
    entrypoint: mvn
    args: ["-B", "package", "-DskipTests"]
~~~

Here, unit-tests and lint can run in parallel; package waits for both to finish. Avoid parallelizing steps that have data dependencies or modify the same workspace files.

### 6.3. Default Substitutions and User-Defined Substitutions

Cloud Build provides substitutions for builds:

| Variable | Meaning |
|---|---|
| $PROJECT_ID | Project ID |
| $BUILD_ID | Build ID |
| $PROJECT_NUMBER | Project number |
| $LOCATION | Build region |
| $TRIGGER_NAME | Trigger name |
| $COMMIT_SHA | Commit SHA |
| $SHORT_SHA | First seven characters of commit SHA |
| $REPO_NAME | Repository name |
| $REPO_FULL_NAME | Repository name including owner/organization |
| $BRANCH_NAME | Branch name |
| $TAG_NAME | Tag name |
| $REF_NAME | Branch or tag name |

Some variables only have values in matching event types. For example, TAG_NAME is meaningless for builds not triggered by a tag; unavailable variables may be replaced with an empty string.

For pull request triggers, additional variables include:

- $_HEAD_BRANCH: source branch of the pull request.
- $_BASE_BRANCH: target branch.
- $_HEAD_REPO_URL: source repository URL.
- $_PR_NUMBER: pull request number.

User-defined substitutions must begin with an underscore and use uppercase letters, digits, or underscores. Examples: _AR_REGION, _IMAGE_NAME, _DEPLOY_ENV. Use substitutions to reuse build configs across environments, but never put passwords, tokens, or private keys into substitutions because values can appear in configs or logs.

## 7. Creating a Cloud Build Trigger in the Console

UI labels may vary across Console versions, but the general workflow is:

1. Select the project used to manage builds.
2. Open Cloud Build > Triggers.
3. Choose the trigger region.
4. Click Create trigger.
5. Set a name and describe the trigger's purpose.
6. Choose the event: branch push, tag push, or pull request.
7. Select the created repository connection and repository link.
8. Configure branch/tag patterns or the pull request target branch.
9. Add included/ignored files if needed.
10. Select the build config in the repository, such as cloudbuild.yaml.
11. Select the service account running the build.
12. Configure substitutions, approval, or build options if needed.
13. Save the trigger and test with a controlled commit or pull request.

If choosing a trigger in a specific region, ensure the repository connection and link exist in a compatible location. If a private pool is required, configure the pool in the build config or build arguments per Cloud Build guidance.

### 7.1. One Repository, Multiple Triggers

A common organization pattern:

| Trigger | Event | Build Config | Build Permissions |
|---|---|---|---|
| orders-pr-check | Pull request to main | cloudbuild-pr.yaml | Test only and read public dependencies |
| orders-main-build | Push to main | cloudbuild.yaml | Test, build, and push image to Artifact Registry |
| orders-release | Tag v* | cloudbuild-release.yaml | Produce release artifact, wait for approval before deploy |

Separating triggers gives each event type its own permissions and goals. If using a single trigger for all events, carefully control substitutions, conditions, and service accounts so release permissions are never inadvertently granted to PRs.

## 8. Managing Triggers with gcloud and Automation

The gcloud CLI supports listing, viewing, running, and managing Cloud Build triggers. Specific trigger creation syntax varies by repository connection type and provider; use the command group matching your chosen connection type.

List triggers in a region:

~~~bash
gcloud builds triggers list --region=asia-southeast1
~~~

Run a trigger manually on a branch:

~~~bash
gcloud builds triggers run orders-main-build \
  --region=asia-southeast1 \
  --branch=main
~~~

Run a build directly from source in the current directory:

~~~bash
gcloud builds submit \
  --config=cloudbuild.yaml \
  .
~~~

Running a direct build is useful for validating the build config before attaching a trigger. It does not prove that webhooks, branch filters, or repository connections work; perform an additional test using a real Git event.

With Cloud Build repositories (2nd gen), host connections and repository links can be created with gcloud, API, or Terraform depending on the supported provider type. Developer Connect can also be managed via Console/gcloud/API depending on each resource's capabilities. Manage connections and triggers using Infrastructure as Code when an organization needs to replicate configurations across multiple projects or environments.

## 9. Securing Repository Connections and Build Triggers

Triggers can turn source code write access into build execution privileges. If a build service account has deployment permissions, anyone who can push code to a branch that fires the trigger can indirectly cause Cloud Build to execute code with those permissions. This is a critical security boundary.

### 9.1. Protecting Git Provider Access

- Install the Git app only on required organizations/repositories.
- Prefer repository-scoped permissions over org-wide access when unnecessary.
- Use branch protection or rulesets to require reviews and checks before merging.
- Enable MFA/SSO and account offboarding processes for the Git provider.
- Periodically review bot accounts, tokens, and connection permissions.
- Monitor changes to installations, webhooks, and repository access.

### 9.2. Separating Permissions by Stage

Separate test, build, publish, and deploy permissions:

- PR trigger: run tests, lint, scans; no access to production secrets.
- Main trigger: build and push images to staging or the corresponding application repository.
- Release trigger: create release artifacts and require approval before production deployment.
- Deploy service account: only has permissions to update the exact required services/clusters/projects.

Never configure an Owner or Editor service account in a build config. For triggers, the service account configured on the trigger is the identity executing the build; the serviceAccount field in the build config does not override the trigger's service account selection when a trigger invokes a build.

### 9.3. Protecting Against Pull Requests from Forks or External Contributors

Code in a pull request can alter scripts, Dockerfiles, Maven plugins, or tests to read environment variables and exfiltrate data. Therefore:

- Never supply production secrets to PR builds.
- Never use a service account with deploy permissions or access to production data.
- Use comment control or approval for high-risk triggers when supported by the provider.
- Verify repository access controls and merge rules.
- Separate verification builds from release builds.
- Never trust outputs from an unreviewed PR as production artifacts.

### 9.4. Using Secret Manager for Secrets

If a build needs tokens to access package registries or internal services:

1. Store the secret in Secret Manager.
2. Grant Secret Manager Secret Accessor to the build service account on that specific secret.
3. Declare the secret in the build config using the appropriate availableSecrets/secretEnv mechanism.
4. Pass the secret only to steps that genuinely need it.
5. Never echo secrets to stdout/stderr and never put secrets into substitutions.
6. Set rotation schedules and revocation procedures.

For untrusted PRs, do not grant secret read permissions. Only enable secrets in triggers or builds reserved for controlled source code.

### 9.5. Approvals and Separation of Duties

Cloud Build triggers can be configured so builds enter a pending approval state before running. Users with Cloud Build Approver permissions can approve or reject pending builds.

Approvals are valuable for production deployments, data migrations, or high-impact infrastructure changes. Separate the approver from the change author when organizational processes require separation of duties.

## 10. Monitoring Builds and Verifying Trigger Status

After a trigger is created, test each condition one by one:

1. Push a commit to a branch that does not match the filter and confirm the trigger does not run.
2. Push a commit to a matching branch and confirm a build is created.
3. Open a pull request to confirm the right PR trigger fires.
4. Modify a file outside included files to verify path filters.
5. Create a matching tag if a release trigger exists.
6. Inspect build logs, artifacts, and substitutions.
7. Check the service account in build details to confirm the right identity.

In Cloud Build History, inspect:

- Build ID, trigger name, source repository, and commit SHA.
- Event/branch/tag/pull request that caused the build.
- Build config path and substitutions.
- Service account, worker pool, and execution duration.
- Which steps succeeded/failed and their corresponding logs.
- Generated artifacts and storage location in Artifact Registry.

Store build links or commit SHAs in release records to trace from artifacts back to source.

## 11. Troubleshooting: Common Issues

**Repository not visible in the list.** Check whether the connection was created in the right project/region; whether the Git app is installed in the right organization; whether the repository is within the granted scope.

**Cannot create connection.** Check IAM permissions to manage connections, administrative permissions at the Git provider, enabled APIs, completed callback/authentication, and network connectivity to the Git host.

**Trigger does not run after push.** Check branch/tag patterns, region, repository link, webhook deliveries, trigger state, and event type. Ensure the commit was actually pushed to the linked repository.

**Pull request does not trigger build.** Check base branch filter, provider support, fork policy, and comment control. If comment control is enabled, an authorized user must comment the trigger command.

**Trigger fires but build cannot find cloudbuild.yaml.** Check the build config path, filename, case sensitivity, and file location in the commit being built.

**Build fails with permission denied.** Identify the trigger's actual service account; check permissions for Artifact Registry, Cloud Logging, Secret Manager, Cloud Run/GKE, or private pools based on the failing step. Do not grant Owner as a quick workaround.

**Build cannot access private dependencies.** Check private pools, subnets, DNS, firewalls, routes, proxies, and registry permissions. Repository connections do not automatically grant network access to build workers.

**Image builds successfully but is not pushed.** Check the images field, Artifact Registry repository, region, image name, and Artifact Registry Writer permission on the service account.

**PR build unexpectedly reads secrets.** Separate service accounts and build configs for PRs, remove secrets from untrusted triggers, and audit Secret Manager access and build history.

**Build uses an unexpected service account.** Check the service account selected on the trigger. For triggered builds, the selection on the trigger determines the build execution identity; do not rely on serviceAccount inside the build config to change it.

**Trigger is in a different region from the repository connection.** Check locations of the host connection, repository link, and trigger. Recreate or choose consistent regions per product requirements.

## 12. Hands-On Exercise: Creating CI for Pull Requests and Building Images from main

Suppose a GitHub repository contains a Java application named orders-api. Objectives:

- Every pull request to main runs unit tests.
- Upon merge to main, Cloud Build runs tests, builds a container image, and pushes it to Artifact Registry.
- When a release tag is created, a separate pipeline builds the release artifact and requires approval before production deployment.

### Step 1: Create the Connection

1. Select the CI project.
2. Enable the Cloud Build API and Developer Connect API, or use Cloud Build repositories (2nd gen).
3. Create a host connection to GitHub in the chosen region.
4. Install the GitHub App on the organization and grant access only to the orders-api repository.
5. Link the orders-api repository.
6. Verify the repository link is in a ready state.

### Step 2: Create Service Accounts

Create service accounts for each purpose:

- orders-pr-ci: runs tests only, no permission to push production images.
- orders-main-ci: runs tests, builds, and pushes images to the Artifact Registry repository app-images.
- orders-prod-release: used for release/deploy and selected only on triggers with approval.

Grant Artifact Registry Writer to orders-main-ci on the specific image repository. Grant required deployment permissions to orders-prod-release on the exact target service. The trigger creator needs actAs permission on the chosen service account.

### Step 3: Create the PR Trigger

1. Select the linked orders-api repository.
2. Select the pull request event.
3. Set the base branch to main.
4. Select build config cloudbuild-pr.yaml.
5. Select service account orders-pr-ci.
6. Do not grant production secrets or deploy permissions.
7. Open a test pull request and confirm the build only runs tests.

### Step 4: Create the main Trigger

1. Select the branch push event.
2. Set the branch pattern to main.
3. Select build config cloudbuild.yaml.
4. Select service account orders-main-ci.
5. Configure substitutions for Artifact Registry region and image name.
6. Push a commit to main and confirm the image is stored tagged with the commit SHA.

### Step 5: Create the Release Trigger

1. Select the tag push event.
2. Use pattern v*.
3. Select cloudbuild-release.yaml.
4. Select service account orders-prod-release.
5. Enable approval before build/deploy if required by process.
6. Create a test release tag and verify the build enters pending approval.

### Step 6: Verify Evidence

- Pull request build shows test results and cannot read production secrets.
- Main build has commit SHA, image URI, and logs.
- Release build has tag, approver, and deployment history.
- Each build used the right service account.
- Repository connection only has access to necessary repositories.

## 13. Operational Checklist for Repository Connections and Triggers

### Repository Connection

- [ ] Chosen Developer Connect or Cloud Build repositories (2nd gen) based on needs.
- [ ] Connection created in the right project and region.
- [ ] Git provider app has access only to required repositories.
- [ ] Repository link points to the correct organization and repository.
- [ ] Connection administration permissions are restricted by role.
- [ ] Webhook/event delivery and connection status verified.

### Trigger

- [ ] Trigger has a clear name, description, and owner.
- [ ] Region and repository link are compatible.
- [ ] Event type, branch/tag/PR filters are accurate.
- [ ] Included/ignored files do not omit important changes.
- [ ] Build config path exists in the commit being built.
- [ ] PR, main, and release use separate appropriate triggers or permissions.
- [ ] Approval enabled for controlled releases.

### Build Identity and Secrets

- [ ] Trigger selects a service account with least privilege.
- [ ] Trigger administrators have actAs permission on the right service account.
- [ ] Build account only has permissions to read source, write logs, and create required artifacts.
- [ ] PRs from untrusted sources have no production secrets.
- [ ] Secrets are retrieved from Secret Manager and used only in steps that need them.
- [ ] Artifact Registry and deploy targets are scoped by repository/project.

### Monitoring and Testing

- [ ] Tested branch push, tag push, and pull request per configuration.
- [ ] Verified build logs, commit SHA, substitutions, and artifacts.
- [ ] Procedures exist to handle connection, webhook, and permission errors.
- [ ] Owner assigned to periodically audit permissions, tokens, app installations, and triggers.
- [ ] Builds and releases are traceable from commit to artifact and deployment environment.

## 14. Common Mistakes

**Creating a trigger before connecting the repository.** Triggers must reference a valid code source. Complete the host connection and repository link first.

**Using Cloud Source Repositories for new projects.** CSR is no longer available to new customers as of June 2024. Choose an appropriate Git provider or Secure Source Manager.

**Confusing connections with triggers.** A connection only establishes integration with the Git provider; a trigger determines which events start builds.

**Using one service account for all environments.** A test build could inadvertently inherit production deploy permissions. Separate identities by purpose and environment.

**Letting PR builds access secrets.** PR code can execute arbitrary commands. Use a restricted build identity and never supply production secrets to PRs.

**Setting filters too broad.** Every branch or file change can trigger unnecessary builds, increasing cost and pipeline load.

**Setting filters too narrow.** Changes to shared libraries or build configs might fail to trigger necessary pipelines. Check dependency paths.

**Assuming triggers automatically run in the right region.** Connections, repository links, and triggers all have locations. Verify region consistency.

**Failing to verify the default service account.** Default configurations can vary across projects. Verify the actual build identity and narrow permissions.

**Failing to inspect build logs after a trigger fires.** A fired trigger does not mean a successful build. Review steps, permissions, artifacts, and final outcomes.

## 15. Official References

- [Cloud Build repositories](https://cloud.google.com/build/docs/repositories)
- [Cloud Build triggers](https://cloud.google.com/build/docs/triggers)
- [Developer Connect overview](https://cloud.google.com/developer-connect/docs/overview)
- [Git repository connections in Developer Connect](https://cloud.google.com/developer-connect/docs/git-repo-connections)
- [Connect a GitHub repository](https://cloud.google.com/build/docs/automating-builds/github/connect-repo-github)
- [Create and manage build triggers](https://cloud.google.com/build/docs/automating-builds/create-manage-triggers)
- [Substituting variable values](https://cloud.google.com/build/docs/configuring-builds/substitute-variable-values)
- [Run builds with a user-managed service account](https://cloud.google.com/build/docs/securing-builds/configure-user-specified-service-accounts)
- [Default Cloud Build service account](https://cloud.google.com/build/docs/cloud-build-service-account)
- [Cloud Build IAM roles and permissions](https://cloud.google.com/build/docs/iam-roles-permissions)
- [Cloud Source Repositories release notes](https://cloud.google.com/source-repositories/docs/release-notes)

Repository connections establish a controlled link between Git providers and Google Cloud; triggers turn source control events into repeatable builds. When regions, event filters, build configs, service accounts, and secret permissions are clearly designed, Cloud Build can automatically test and package per commit while preserving control, traceability, and release approvals.

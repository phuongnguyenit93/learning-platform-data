# Cloud Build Configs, Build Steps, and Substitutions

Cloud Build automates the process of fetching source code, testing, packaging, and producing artifacts for application delivery. A build config describes the steps to execute, the container image used for each step, execution order, configuration variables, and output artifacts. By understanding this structure, development teams can create pipelines that are readable, reproducible, permission-controlled, and adaptable across environments without duplicating configuration files.

This lesson is part of the **CLOUD_PROVIDERS_GCP** module. The module helps learners explore Google Cloud from project organization, IAM, and VPC to Compute Engine, GKE, Cloud Run, storage services, and databases. Through deployment scenarios, learners know how to select services, secure resources, automate releases, and monitor reliability and cost. Within the scope of this lesson, we focus on Cloud Build configuration, build steps, execution order, substitutions, and how to bring a Java application into a build workflow.

## Objectives

After this lesson, you will be able to:

- Explain the role of Cloud Build and build configs.
- Identify the main fields of a cloudbuild.yaml file.
- Organize build steps, container images, args, env, dir, id, and waitFor.
- Run steps sequentially or in parallel and share artifacts through the workspace.
- Distinguish built-in substitutions from user-defined substitutions.
- Use substitutions for project, region, repository, image tag, and triggers.
- Choose how to handle missing substitutions and escape dollar signs.
- Run manual builds, configure triggers, and inspect results.
- Apply IAM principles, secret management, and software supply chain security.

## 1. Cloud Build in the CI/CD Workflow

Cloud Build is the build execution service on Google Cloud. A build can be started manually from a developer workstation, via a Cloud Build trigger when changes occur in a repository, or through the API. Cloud Build executes the declared steps, stores results, and provides status and logs for the team to inspect.

A common workflow for a Java application:

~~~mermaid
flowchart TD
    A["Commit source code"]
    B["Cloud Build trigger"]
    C["Checkout source"]
    D["Compile and unit tests"]
    E["Build container image"]
    F["Push Artifact Registry"]
    G["Deploy Cloud Run / GKE"]
    H["Post-deploy checks"]
    A --> B --> C --> D --> E --> F --> G --> H
~~~

Cloud Build focuses on executing build steps. The repository holds source code and build configs; Artifact Registry stores container images or packages; Cloud Run, GKE, or Compute Engine runs artifacts after release. Additional services for testing, approvals, secret management, and monitoring can be added depending on the architecture.

### What Is a Build Config?

A build config is a YAML or JSON file that describes a build. The conventional filename is cloudbuild.yaml or cloudbuild.yml. This file declares:

- **steps:** the list of build steps and the container image executing each step.
- **substitutions:** variables used to customize the build.
- **options:** global options such as logging, machine type, and substitution handling.
- **timeout:** maximum duration for the entire build.
- **images:** container images Cloud Build should store/push after building.
- **artifacts:** other artifacts, such as files uploaded to Cloud Storage.
- **availableSecrets:** secrets provided to build steps via Secret Manager.
- **serviceAccount:** build execution identity when using a user-specified service account.

Not every field is required. A minimal build may need only steps; production builds should explicitly declare options affecting permissions, logging, timeout, and artifacts.

## 2. Structure of a Build Step

Each item in the **steps** array describes a container run by Cloud Build. The container image provides the tooling for that step, such as Maven, Docker, gcloud, or a custom team-built image.

Commonly used fields:

| Field | Role | Example |
|---|---|---|
| name | Container image executing the step | maven:3.9-eclipse-temurin-21 |
| id | Identifier name of the step | unit-tests |
| entrypoint | Program executed inside the container | mvn, bash |
| args | Arguments passed to entrypoint or default command | -B test package |
| env | Standard environment variables | APP_ENV=staging |
| secretEnv | Environment variables sourced from availableSecrets | PAYMENT_API_TOKEN |
| dir | Working directory of the step | services/orders |
| waitFor | Steps that must complete before the current step | unit-tests, package |
| timeout | Maximum duration of the step | 300s |
| allowFailure | Allows the build to continue if the step fails | true |
| allowExitCodes | Accepted exit codes | 1, 2 |
| volumes | Mount shared volumes across steps | cache-volume |

### Container Image and Command

The name field specifies an image available in a registry. When a step starts, Cloud Build creates a container from that image and runs entrypoint with args. If entrypoint is omitted, Cloud Build uses the image's default entrypoint.

Example running Maven:

~~~yaml
steps:
  - name: maven:3.9.9-eclipse-temurin-21
    entrypoint: mvn
    args:
      - -B
      - test
      - package
~~~

In the example, the Maven image provides the JDK and Maven; entrypoint is mvn; args instructs it to run tests and package in batch mode. For real projects, choose a specific vetted builder version. You can pin images by digest to reduce the risk of unintended tag changes.

### entrypoint and args

If you need a shell to chain multiple commands, you can use an image containing bash and specify entrypoint:

~~~yaml
steps:
  - name: gcr.io/cloud-builders/gcloud
    entrypoint: bash
    args:
      - -ceu
      - |
        echo "Build started"
        gcloud version
        echo "Build checks completed"
~~~

The -c, -e, and -u options belong to bash: -c executes the command string, -e stops when a command fails, and -u errors on undefined variables. Use pipefail if the script uses shell pipelines and needs to catch errors from upstream commands. Avoid cramming complex command chains into a single args string with unclear quoting; multi-line blocks are easier to read and review.

### env and dir

The env field passes non-secret configuration variables into the step's container. The dir field changes the working directory. If dir is a relative path, it is resolved relative to /workspace.

~~~yaml
steps:
  - name: maven:3.9.9-eclipse-temurin-21
    dir: services/orders
    env:
      - APP_ENV=ci
    entrypoint: mvn
    args:
      - -B
      - test
~~~

Do not put passwords or tokens directly in env in the build config. These values can appear in configuration, change history, or logs if printed.

## 3. Workspace and Sharing Data Between Steps

Each build step runs in its own container. Files in a container's private filesystem are not automatically shared with the next step's container. Cloud Build provides the **/workspace** directory shared across steps within the same build. Source code is placed in workspace, and steps can write or read artifacts there.

Example:

~~~yaml
steps:
  - id: compile
    name: maven:3.9.9-eclipse-temurin-21
    entrypoint: mvn
    args:
      - -B
      - package

  - id: inspect-artifact
    name: gcr.io/cloud-builders/gcloud
    entrypoint: bash
    args:
      - -ceu
      - |
        test -f /workspace/target/app.jar
        ls -lh /workspace/target/app.jar
    waitFor:
      - compile
~~~

This example assumes Maven is configured to produce target/app.jar. If the artifact has a different name, adjust the path or configure finalName in Maven.

If you need to share data outside /workspace, declare a shared volume for the steps that need it. The volume must have the same name and appropriate mount path in participating steps. Do not assume that /tmp or a home directory from one container will exist in another container.

### Avoiding Artifact Overwrites

When multiple steps run in parallel, each step should write to a separate file or directory. If two steps write to the same file, the result can depend on completion order. Only combine or package artifacts after the steps producing the data have finished.

## 4. Execution Order: id and waitFor

Cloud Build executes steps sequentially by default. A step normally waits for preceding steps to finish. The **id** field names a step; **waitFor** explicitly declares which steps the current step must wait for.

Example pipeline with two independent checks and a package step:

~~~yaml
steps:
  - id: unit-tests
    name: maven:3.9.9-eclipse-temurin-21
    entrypoint: mvn
    args:
      - -B
      - test

  - id: static-checks
    name: maven:3.9.9-eclipse-temurin-21
    entrypoint: bash
    args:
      - -ceu
      - |
        echo "Run project static checks here"
    waitFor:
      - "-"

  - id: package
    name: maven:3.9.9-eclipse-temurin-21
    entrypoint: mvn
    args:
      - -B
      - package
      - -DskipTests
    waitFor:
      - unit-tests
      - static-checks
~~~

The special value **-** in waitFor means the step can start as soon as the build begins, without waiting for any other step. In the example, unit-tests and static-checks run in parallel; package waits for both. If a mandatory check fails, the build stops and package is not executed.

Only run independent steps in parallel. If package needs compile output, or integration tests need an initialized database, declare dependencies using waitFor so the build has deterministic ordering.

### allowFailure and allowExitCodes

Some steps may be informational, such as collecting optional reports. **allowFailure: true** lets the build continue when that step fails. **allowExitCodes** allows specifying particular exit codes that are considered acceptable. When using allowExitCodes, the exit code list takes precedence over allowFailure.

Do not enable allowFailure for compilation, mandatory tests, security scans, or steps producing release artifacts. A green build when critical checks have failed defeats the purpose of CI status.

## 5. Built-in Substitutions

A substitution is a variable replaced with a value by Cloud Build before executing build steps. Built-in substitutions provide information about the build, project, or trigger source.

Common built-in substitutions:

| Substitution | Meaning |
|---|---|
| PROJECT_ID | Build project ID |
| PROJECT_NUMBER | Project number |
| BUILD_ID | Unique ID of the build |
| LOCATION | Cloud Build location |
| TRIGGER_NAME | Name of the trigger that started the build |
| REPO_NAME | Source repository name |
| REPO_FULL_NAME | Full repository name if supported by source |
| BRANCH_NAME | Branch name when building from a branch |
| TAG_NAME | Tag name when building from a tag |
| COMMIT_SHA | Commit SHA |
| SHORT_SHA | Short version of the commit SHA |
| REVISION_ID | Revision ID |
| REF_NAME | Source ref name |

Values depend on how the build was started and the repository source. For example, TRIGGER_NAME or BRANCH_NAME may have no value in a manual build not attached to a trigger. Avoid assuming every built-in substitution always has a value in all build types.

### Using Built-in Substitutions

Example tagging a container image with the build ID:

~~~yaml
steps:
  - name: gcr.io/cloud-builders/docker
    args:
      - build
      - -t
      - asia-southeast1-docker.pkg.dev/$PROJECT_ID/containers/orders-api:$BUILD_ID
      - .
~~~

When the build runs, Cloud Build replaces PROJECT_ID and BUILD_ID with their respective values. Tagging with the build ID helps identify the artifact from a specific build run. For builds from source control, SHORT_SHA can be used to link the image to a commit.

## 6. User-Defined Substitutions

When you need to pass service names, regions, repositories, or environments, declare custom substitutions in the **substitutions** field. Custom substitution names must begin with an underscore, followed by uppercase letters, digits, or underscores. For example: _SERVICE, _REGION, _AR_REPOSITORY.

~~~yaml
substitutions:
  _SERVICE: orders-api
  _REGION: asia-southeast1
  _AR_REPOSITORY: containers

steps:
  - name: gcr.io/cloud-builders/gcloud
    args:
      - run
      - services
      - describe
      - $_SERVICE
      - --region=$_REGION
~~~

Cloud Build supports writing $_SERVICE or the equivalent braced form. The braced form is helpful when concatenating a substitution with other characters where variable name boundaries might be ambiguous. Follow a consistent convention across the repository.

### Default Values and Overrides at Build Time

Substitutions can be given defaults in the build config and overridden when running manual builds or configuring triggers. Example:

~~~yaml
substitutions:
  _REGION: asia-southeast1
  _SERVICE: orders-api
  _ENVIRONMENT: staging
~~~

When running a build, different values can be passed for custom substitutions. This allows the same build config to serve multiple environments without duplicating the entire YAML file. However, production environments should have proper triggers, permissions, and approvals; do not let an arbitrary parameter turn a staging build into a production build while bypassing controls.

### SubstitutionOption: MUST_MATCH and ALLOW_LOOSE

A build config can use **options.substitutionOption** to specify how unprovided substitutions are handled:

- **MUST_MATCH:** the build fails if a referenced substitution has no value.
- **ALLOW_LOOSE:** a substitution without a value is replaced with an empty string.

For manual builds, the default is typically MUST_MATCH. For triggered builds, Cloud Build defaults to ALLOW_LOOSE. You can declare it explicitly in options so readers understand the intended behavior.

ALLOW_LOOSE can be convenient when a build config is shared across multiple triggers with different sets of built-in substitutions. However, missing variables replaced by empty strings can produce malformed image names, paths, or commands without failing early. For required values such as region, repository, or service name, validate inputs in a step before using them.

### Dynamic Substitutions

**dynamicSubstitutions** allows one substitution to reference another substitution. For example, a custom substitution can be derived from PROJECT_ID or another custom value. For builds started by triggers, Cloud Build enables dynamic substitutions automatically; for manual builds, explicitly enable it in options if the config uses this feature.

~~~yaml
substitutions:
  _IMAGE_NAME: orders-api
  _IMAGE_PATH: asia-southeast1-docker.pkg.dev/$PROJECT_ID/containers/$_IMAGE_NAME

options:
  dynamicSubstitutions: true
~~~

Use dynamic substitutions when you genuinely need derived values. For simple configurations, declaring each value directly is often easier to read and verify.

## 7. Escaping Dollar Signs and Using Shell Variables

Cloud Build processes substitutions before the shell runs. Therefore, if a script needs to use shell variable syntax, prevent Cloud Build from treating it as a substitution.

Cloud Build uses **$$** to escape a dollar sign and pass a single dollar sign down to the execution step. Example:

~~~yaml
steps:
  - name: bash
    entrypoint: bash
    env:
      - APP_ENV=staging
    args:
      - -ceu
      - |
        echo "Build environment: $$APP_ENV"
        echo "Working directory: $$PWD"
~~~

After substitution processing, bash receives the variables APP_ENV and PWD to expand. Writing a single dollar sign directly before a variable name that is neither a built-in nor a custom substitution may cause Cloud Build to report an invalid substitution error or substitute an unintended value.

Do not confuse:

- **$_REGION:** custom substitution replaced by Cloud Build before running the step.
- **$$APP_ENV:** escaped dollar sign so the shell expands the APP_ENV environment variable.
- **$BUILD_ID:** built-in substitution replaced by Cloud Build before running the step.

For multi-line scripts, verify strings after substitution and quote shell variables carefully. Do not use substitutions to interpolate untrusted data into shell commands; pass values via env or args and validate inputs appropriately.

## 8. Complete Example: Building and Packaging a Java Application

Suppose a repository contains a Java application using Maven, with a Dockerfile at the root directory. Maven is configured to generate **target/app.jar**. The goal is to run tests, build a container image, and push the image to Artifact Registry.

### Dockerfile

~~~dockerfile
FROM eclipse-temurin:21-jre

WORKDIR /app
COPY target/app.jar app.jar

ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

This example Dockerfile uses the Java 21 JRE. For production, pin the base image by version or digest, update periodically, and scan for vulnerabilities before releasing.

### cloudbuild.yaml

~~~yaml
steps:
  - id: unit-tests-and-package
    name: maven:3.9.9-eclipse-temurin-21
    entrypoint: mvn
    args:
      - -B
      - test
      - package

  - id: build-container
    name: gcr.io/cloud-builders/docker
    args:
      - build
      - -t
      - $_AR_HOST/$PROJECT_ID/$_AR_REPOSITORY/$_IMAGE:$BUILD_ID
      - .
    waitFor:
      - unit-tests-and-package

images:
  - $_AR_HOST/$PROJECT_ID/$_AR_REPOSITORY/$_IMAGE:$BUILD_ID

substitutions:
  _AR_HOST: asia-southeast1-docker.pkg.dev
  _AR_REPOSITORY: containers
  _IMAGE: orders-api

options:
  logging: CLOUD_LOGGING_ONLY

timeout: 1200s
~~~

Explanation:

1. The unit-tests-and-package step uses Maven to run tests and create the artifact.
2. The build-container step waits for the Maven step to succeed, then uses the Docker builder to build an image from the Dockerfile.
3. The image is tagged with project, Artifact Registry host, repository, image name, and BUILD_ID.
4. The images field declares the output image for Cloud Build to push after all steps complete.
5. Substitutions provide default host, repository, and image name.
6. logging selects Cloud Logging to store build logs; timeout limits the maximum build duration.

For the example to work, you must create the corresponding Artifact Registry Docker repository, enable required APIs, and grant write permissions to the build service account. The Maven project must produce target/app.jar. If the filename differs, adjust the Dockerfile or Maven finalName.

### Creating the Artifact Registry Repository

Example command to create a Docker repository:

~~~bash
gcloud artifacts repositories create containers \
  --repository-format=docker \
  --location=asia-southeast1 \
  --description="Container images for application builds"
~~~

The project and region must match your deployment target. If the repository already exists, there is no need to recreate it. Repository creation permissions belong to the infrastructure administration team; the build service account only needs permission to write images into the repository.

### Running a Manual Build

~~~bash
gcloud builds submit . \
  --config=cloudbuild.yaml \
  --project=YOUR_PROJECT_ID \
  --region=asia-southeast1
~~~

This command submits the current source along with the build config to Cloud Build. Custom substitutions can be passed when needed:

~~~bash
gcloud builds submit . \
  --config=cloudbuild.yaml \
  --project=YOUR_PROJECT_ID \
  --region=asia-southeast1 \
  --substitutions=_AR_HOST=asia-southeast1-docker.pkg.dev,_AR_REPOSITORY=containers,_IMAGE=orders-api
~~~

Never put passwords, tokens, or keys into --substitutions. Substitutions are configuration data, not a secret storage channel.

### Checking Results

After the build completes:

1. Open Cloud Build History and select the build ID.
2. Inspect the logs of each step to confirm Maven tests and Docker build succeeded.
3. Verify the image status in Artifact Registry.
4. Record the image URI and digest to ensure the exact built artifact is released.
5. If the build failed, identify the first failing step and read its logs; avoid only fixing the final step while ignoring the root error.

## 9. Build Triggers and Source-Based Substitutions

A build trigger automatically starts a build on events from a configured repository or source. Triggers are typically tied to branches, tags, or pull requests. When a trigger fires, Cloud Build can provide built-in substitutions such as BRANCH_NAME, TAG_NAME, COMMIT_SHA, SHORT_SHA, and TRIGGER_NAME.

A typical trigger workflow:

1. Connect the repository to Cloud Build.
2. Create a trigger and select an event, such as push to the main branch.
3. Select the build config in the repository.
4. Choose the trigger region and configure custom substitutions if needed.
5. Assign a build service account with least privilege.
6. Test the trigger with a commit that does not impact production.
7. Inspect logs, artifacts, and build status.

### Distinguishing Triggers for Pull Requests and Main Branches

An organization can use separate triggers:

- Pull request: runs lint, unit tests, dependency checks, and trial builds; do not grant production deploy permissions or unnecessary secrets.
- Main branch: runs full tests, builds images, and deploys to a testing environment.
- Release tag: produces release artifacts, applies explicit versioning, and may require approval before deployment.

Branch- or tag-based substitutions can be used to attach metadata to artifacts. However, do not use branch names as a security boundary. Deployment permissions must be controlled via IAM, trigger policies, approvals, and appropriate service accounts.

### Trigger Substitutions and Missing Values

Triggers can provide event-dependent built-in substitutions. If a build config is shared between manual builds and trigger builds, examine which values are absent in each context. You can set defaults for custom substitutions and validate required fields before executing deployments.

## 10. Using Secret Manager in Build Steps

Builds sometimes need tokens to access private package registries, run scans, or call test services. Never write secrets into build configs, substitutions, Dockerfiles, or echo statements. Retrieve secrets from Secret Manager and grant them only to the step that needs them.

Example secret configuration:

~~~yaml
availableSecrets:
  secretManager:
    - versionName: projects/$PROJECT_ID/secrets/SONAR_TOKEN/versions/latest
      env: SONAR_TOKEN

steps:
  - name: bash
    entrypoint: bash
    secretEnv:
      - SONAR_TOKEN
    args:
      - -ceu
      - |
        test -n "$$SONAR_TOKEN"
        echo "Scanner credential is available"
~~~

The build service account needs permission to access the corresponding secret, typically roles/secretmanager.secretAccessor at the secret level. Secrets are only mapped into steps that declare secretEnv. Do not print secret values to logs and do not pass them on the command line if the tool can accept them via environment variables or another secure mechanism.

Do not supply secrets to builds from untrusted pull requests. A script in the repository could read environment variables and exfiltrate them. Separate triggers, service accounts, and secret scopes based on source code trust levels.

## 11. Build Service Account and IAM

Cloud Build uses identities to access source code, write logs, read secrets, push images, or deploy. Distinguish between the Google-managed Cloud Build service agent and the build service account that steps use to perform actions.

In production, specify a user-specified service account tailored to the workload with least privilege. Example:

| Task | Typically Required Permissions |
|---|---|
| Write logs to Cloud Logging | roles/logging.logWriter |
| Push images to Artifact Registry | roles/artifactregistry.writer on the required repository |
| Read secrets in a build step | roles/secretmanager.secretAccessor on the required secret |
| Write custom metrics if needed by build | Monitoring permissions appropriate for the task |
| Deploy Cloud Run | Service deployment permissions and iam.serviceAccounts.actAs on the appropriate runtime service account |

The exact list depends on configuration, APIs, and target services. Never grant Owner or Editor to a build service account just to work around permission errors. Identify the missing permission and grant the smallest role on the narrowest resource scope.

The build service account and the runtime service account are two distinct identities. The build needs permissions to create and publish artifacts; the running application should only have access to the data and services required by the workload. Do not use the build service account as the runtime identity for the application.

## 12. Build Options, Timeout, and Logging

The **options** field controls how Cloud Build executes the build:

- **logging:** chooses where to store logs, e.g., CLOUD_LOGGING_ONLY.
- **machineType:** selects build machine type when the workload needs non-default resources.
- **diskSizeGb:** configures build disk size when needed.
- **substitutionOption:** MUST_MATCH or ALLOW_LOOSE.
- **dynamicSubstitutions:** enables derived substitutions when needed.
- **pool:** selects a private pool if the build needs a private network environment.

The build-level **timeout** limits total build duration. Step-level timeout can also be declared to bound an individual step. Set limits appropriate for actual test times and load; overly long timeouts delay detection of hung pipelines, while overly short timeouts cause false failures.

### Private Pools

Private pools are useful when builds need access to resources in a private network or require controlled build environments. When using them, design networking, region, IAM, and source/artifact connectivity appropriately. Do not put network credentials or secrets into substitutions.

### Logs and Diagnostics

Cloud Build can write logs to Cloud Logging or a configured storage location. When a build fails, check:

1. Build status and the first step that failed.
2. Exit code and the actual command executed.
3. Whether the builder image exists and can be pulled.
4. Whether the source contains the files or paths expected by the step.
5. Whether substitutions were replaced properly and have values.
6. Whether the build service account has permissions on APIs, repositories, or secrets.
7. Whether timeouts, quotas, private pools, or networking caused interruptions.

Do not handle every failure by increasing permissions or increasing timeouts. Identify the root cause from logs and adjust only the relevant configuration.

## 13. Securing the Software Supply Chain in Cloud Build

The build pipeline is a critical part of the software supply chain. If the build config or builder image is modified without authorization, released artifacts can be compromised even when the application source code has no bugs.

Recommended practices:

- Review changes to cloudbuild.yaml just like application source code.
- Use builder images from trusted sources and pin versions or digests.
- Manage dependencies with lockfiles or fixed versions when the ecosystem supports them.
- Restrict build service account permissions by task.
- Separate untrusted pull request builds from builds holding secrets or deploy permissions.
- Use approvals or separate controls for production releases.
- Store images by digest and link artifacts to commit, build ID, and provenance.
- Scan dependencies, container images, and artifacts according to security policy.
- Prevent build logs from exposing tokens, passwords, private keys, or customer data.
- Monitor changes to triggers, service accounts, repositories, and build configs.

Substitutions enable configuration reuse but are not a security mechanism. Custom substitution values can be viewed in the build config or build metadata; pass only environment names, regions, repositories, versions, and non-sensitive values.

## 14. Common Configuration Errors

| Issue | Cause | Resolution |
|---|---|---|
| Build reports invalid substitution | Malformed variable name or undefined variable | Check built-in and custom substitutions |
| Shell command receives empty string | ALLOW_LOOSE replaces missing variables with empty string | Validate required variables before use |
| Shell reports bad substitution | Both Cloud Build and shell process dollar signs | Escape with $$ when the shell needs to expand the variable |
| Step cannot see artifact | Artifact is inside the container's private filesystem | Write artifacts to /workspace or a shared volume |
| Step runs too early | waitFor does not declare dependency | Use explicit id and waitFor |
| Image fails to push | Wrong registry path or missing permissions | Verify repository, location, and Artifact Registry IAM |
| Build cannot read secret | Missing secret accessor or wrong secretEnv | Grant permission on the needed secret and check env name |
| Build trigger does not fire | Misconfigured event, branch, repository, or region | Check trigger configuration and event |
| Build passes despite check failure | Mandatory step has allowFailure set | Remove allowFailure or adjust allowExitCodes |
| Non-reproducible artifact | Builder/dependency tag changed or unpinned source | Pin versions/digests and record commit |

## 15. Hands-On Exercise: Creating a Cloud Build Pipeline for a Java Service

Suppose a repository contains a Java service named orders-api using Maven and deploying to Cloud Run. Create a pipeline that can run both manually and via triggers.

Steps:

1. Create cloudbuild.yaml with a step running Maven unit tests and package.
2. Add a Docker step to build an image from the Dockerfile.
3. Tag the image with BUILD_ID or SHORT_SHA to link the artifact to the build.
4. Use custom substitutions for Artifact Registry host, repository, image name, and region.
5. Ensure the build step depends on the test step using waitFor.
6. Enable Cloud Logging for the build and set an appropriate timeout.
7. Create the Artifact Registry repository and grant writer permission to the build service account.
8. Run a manual build using gcloud builds submit.
9. Inspect logs, build status, image URI, and digest in Artifact Registry.
10. Create a trigger for pull requests or a test branch.
11. Confirm the trigger has no production permissions and receives no unnecessary secrets.
12. Test changing a substitution to an invalid value and observe the error; then fix it and re-run.
13. Add a container or dependency check step, ensuring a mandatory check failure does not allow the build to report success.

### Completion Criteria

- Build config is valid and readable.
- Steps execute according to declared dependencies.
- Artifact is created and pushed to the correct repository.
- Build ID or commit SHA can be traced back from the image tag.
- No secrets exist in YAML or substitutions.
- Build service account has only necessary permissions.
- Trigger fires on the right events and does not exceed permission scope.

## Checklist Before Taking Cloud Build Config to Production

- [ ] cloudbuild.yaml is reviewed and managed in the repository.
- [ ] Each step uses a trusted builder image with controlled versioning.
- [ ] entrypoint, args, env, and dir are explicitly declared.
- [ ] Shared artifacts are written to /workspace or a shared volume.
- [ ] id and waitFor accurately express dependencies.
- [ ] allowFailure is only used for optional steps.
- [ ] Built-in and custom substitutions are used in appropriate contexts.
- [ ] Required variables are validated before use.
- [ ] Shell variables are escaped with $$ where needed.
- [ ] Secrets are retrieved from Secret Manager and granted only to steps needing them.
- [ ] Build service account has least privilege.
- [ ] Triggers for PRs, branches, and releases have proper permission boundaries.
- [ ] Timeout, logging, and private pools are configured as needed.
- [ ] Artifacts are linked to build ID, commit, and digest.
- [ ] Build logs contain no secrets or sensitive data.

## Self-Check Questions

**1. What is a Cloud Build config used for?**

It describes build steps, execution order, container images, substitutions, options, timeout, and output artifacts.

**2. In what environment does each build step run?**

Each step runs in its own container from the declared image. Steps can share data through /workspace or configured volumes.

**3. What does waitFor do?**

It declares which steps the current step must wait for. The special hyphen value allows a step to start immediately when the build begins.

**4. What format must user-defined substitutions follow?**

Custom substitution names must start with an underscore, such as _REGION or _SERVICE.

**5. When should $$ be used in a build config?**

When escaping a dollar sign so Cloud Build passes the variable down to the shell, where the shell expands the environment variable.

**6. Why should tokens not be stored in substitutions?**

Substitutions are configuration data that can appear in build configs or build metadata; they are not a secret store and do not guarantee protection of sensitive values.

**7. How does a build service account differ from a runtime service account?**

The build service account performs pipeline operations such as reading secrets or pushing images. The runtime service account is the identity the application uses when running and needs separate permissions suited to the workload.

## References

- [Cloud Build overview](https://cloud.google.com/build/docs/overview)
- [Build config file schema](https://cloud.google.com/build/docs/build-config-file-schema)
- [Build steps](https://cloud.google.com/build/docs/configuring-builds/create-basic-configuration)
- [Substituting variable values](https://cloud.google.com/build/docs/configuring-builds/substitute-variable-values)
- [Build request and built-in substitutions](https://cloud.google.com/build/docs/configuring-builds/substitute-variable-values#using_default_substitutions)
- [Configure user-specified service accounts](https://cloud.google.com/build/docs/securing-builds/configure-user-specified-service-accounts)
- [Accessing private data in build steps](https://cloud.google.com/build/docs/securing-builds/use-secrets)
- [Cloud Build triggers](https://cloud.google.com/build/docs/triggers)
- [Cloud Build locations](https://cloud.google.com/build/docs/locations)

## Conclusion

A Cloud Build config describes how an artifact is produced from source code through build steps. Each step runs in its own container image and can use entrypoint, args, env, and dir; steps coordinate via id, waitFor, and workspace. Built-in substitutions provide build context, while custom substitutions enable reusing configurations across multiple projects or environments. Controlling substitutionOption, dynamicSubstitutions, and dollar sign escaping makes pipelines more predictable. Combining least-privilege IAM, Secret Manager, trusted builder images, and traceable artifacts makes Cloud Build a secure and sustainably operable CI/CD foundation.

# Cloud Build Service Accounts and Least Privilege

Cloud Build executes software testing, packaging, and deployment steps on Google Cloud. Every build requires an identity to call APIs, read source code, push images, write logs, or update services. If a build runs with an account that holds Owner or Editor permissions across the entire project, any command executed in the build can leverage that broad scope. A modified build script, malicious dependency, or untrusted pull request can therefore become an access vector into production resources.

Secure design requires identifying the exact service account that executes the build, granting permissions per task, and scoping access to minimal resources. Cloud Build supports default service accounts or organization-specified service accounts. For critical pipelines, create dedicated build identities, separate them from the application's runtime identity, and control who is allowed to instruct Cloud Build to use those identities.

## 1. Distinguishing Identities in Cloud Build

A pipeline can involve multiple principals. They have distinct responsibilities and must not be consolidated into a single shared account:

| Identity | Role | Permissions of Concern |
| --- | --- | --- |
| Person or system starting the build | Calls API to create build or fire trigger | Permission to create builds/triggers and **iam.serviceAccounts.actAs** on the specified service account |
| Cloud Build service agent | Google-managed identity operating Cloud Build in the project | Service role **roles/cloudbuild.serviceAgent**; typically granted when enabling the API |
| Build service account | Identity used by build steps when calling Google Cloud APIs | Permissions to read source, push images, write logs, or deploy per pipeline |
| Runtime service account | Identity used by the application after deployment | Permissions to access data and services needed during runtime operation |
| Target service's service agent | Google-managed identity for services like Cloud Run to perform background work | Required service permissions, e.g., reading images from Artifact Registry in cross-project setups |

The Cloud Build service agent typically has an address of the form **service-PROJECT_NUMBER@gcp-sa-cloudbuild.iam.gserviceaccount.com**. This is a Google-managed service agent, not an account to attach to build steps.

The default build service account may be the legacy Cloud Build service account (**PROJECT_NUMBER@cloudbuild.gserviceaccount.com**) or the Compute Engine default service account (**PROJECT_NUMBER-compute@developer.gserviceaccount.com**), depending on project configuration and history. Do not infer the identity solely from the service name or assume all projects use the same account. Inspect an actual build in Cloud Build or the trigger configuration to confirm the serviceAccount field.

For pipelines requiring deployment permissions, use a user-specified service account named to reflect its purpose, such as **cloud-build-deployer@PROJECT_ID.iam.gserviceaccount.com**. Explicitly specifying the identity makes it easier for teams to review policies, audit logs, and verify pipeline permission scopes.

## 2. Separating the Build Service Account from the Runtime Service Account

The build service account only needs permissions to produce artifacts and deploy the application. The runtime service account needs the permissions the application uses when handling requests. These two identities have different lifecycles and trust levels.

Example for an orders API:

- **cloud-build-deployer**: builds images, pushes images to Artifact Registry, and deploys Cloud Run revisions.
- **orders-runtime**: attached to the Cloud Run service so the application can read secrets and access orders data.
- **cloudbuild service agent**: performs background operations for the Cloud Build service.

If the same service account is shared between build and runtime, the pipeline could inherit read access to production data, while the runtime application could possess permissions to push images or alter services. This expands blast radius if either environment is compromised.

Do not create or upload service account JSON keys into repositories or pipeline secrets just for Cloud Build authentication. Cloud Build can use identities attached directly to builds. When pipelines must run from external CI systems, prefer identity federation mechanisms such as Workload Identity Federation over long-lived keys.

## 3. Choosing Default vs. User-Specified Service Accounts

The default service account is convenient for initial experimentation, but its effective permissions can vary by project configuration, organization policies, and how the default account was granted roles. The default account may also be shared across many other builds or workloads, making per-pipeline least privilege harder to enforce.

A user-specified service account is appropriate when:

- The build needs permissions to deploy to production or access sensitive resources.
- Multiple repositories have different trust levels.
- Permissions for building images, deploying applications, and running tests need to be separated.
- Clear auditing of which pipeline used which principal is required.
- The organization wants to revoke one pipeline's permissions without affecting other builds.

When creating dedicated service accounts, name them by application, environment, and purpose. Avoid generic names like **terraform**, **ci**, or **build** if multiple pipelines carry different permissions. Separate service accounts along trust boundaries, such as test builds from pull requests vs. release builds from protected branches.

Before switching from default to user-specified, list every resource the build currently accesses. Changing the identity can cause the pipeline to lose access to read source, push images, write logs, or deploy. Grant roles based on required operations and test each step in a non-production environment.

## 4. Creating a Dedicated Build Service Account

Example creating a service account dedicated to deploying applications in a project:

~~~bash
gcloud iam service-accounts create cloud-build-deployer \
  --project=PROJECT_ID \
  --display-name="Cloud Build deployer"
~~~

The resulting service account address has the form:

~~~text
cloud-build-deployer@PROJECT_ID.iam.gserviceaccount.com
~~~

The person or system configuring builds/triggers must be allowed to attach this service account. The key permission is **iam.serviceAccounts.actAs**, typically granted via the **roles/iam.serviceAccountUser** role on that exact service account:

~~~bash
gcloud iam service-accounts add-iam-policy-binding \
  cloud-build-deployer@PROJECT_ID.iam.gserviceaccount.com \
  --project=PROJECT_ID \
  --member="user:release-engineer@example.com" \
  --role="roles/iam.serviceAccountUser"
~~~

This example uses an operator as the principal configuring the pipeline. In practice, replace the principal with a trusted group or CI identity. Do not grant **roles/iam.serviceAccountUser** across the entire project if the user only needs to attach one specific build service account.

The actAs permission allows a principal to instruct a service to use the service account. It does not itself grant the permissions that the build service account holds during execution. These two permission layers must be reviewed separately: which identities the initiator may select, and what the selected identity is allowed to do.

## 5. Granting Permissions per Pipeline Task

No single set of roles fits every build. Inventory the actual operations required, then grant roles at the narrowest possible resource scope.

| Task | Applicable Role | Recommended Scope |
| --- | --- | --- |
| Push images to Artifact Registry | **roles/artifactregistry.writer** | Target image repository |
| Write logs to Cloud Logging | **roles/logging.logWriter** | Project running the build |
| Deploy or update Cloud Run service | **roles/run.developer** | Project or appropriate service scope |
| Attach runtime service account to Cloud Run | **roles/iam.serviceAccountUser** | Specific runtime service account |
| Read a secret during build | **roles/secretmanager.secretAccessor** | Specific secret |
| Read objects from input bucket | **roles/storage.objectViewer** | Source bucket |
| Write objects to output bucket | Storage role appropriate for write operations | Destination bucket |

The roles in the table are functional reference options. If a pipeline needs only a small subset of permissions, organizations can build custom roles to constrain exact permissions. Inspect role permissions at deployment time and test with the actual identity; predefined roles may include auxiliary permissions beyond what the name implies.

### Example: Granting Image Push Permissions

If the Artifact Registry repository is named **app-images** in region **asia-southeast1**, writer permission can be granted directly on the repository:

~~~bash
gcloud artifacts repositories add-iam-policy-binding app-images \
  --location=asia-southeast1 \
  --project=PROJECT_ID \
  --member="serviceAccount:cloud-build-deployer@PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/artifactregistry.writer"
~~~

The build service account can push images into this repository. It does not need permission to administer all repositories or delete repositories if the pipeline only pushes.

### Example: Granting Cloud Run Deployment Permissions

If the pipeline creates or updates a Cloud Run service in the project, grant the appropriate deployment role on the project hosting the service:

~~~bash
gcloud projects add-iam-policy-binding PROJECT_ID \
  --member="serviceAccount:cloud-build-deployer@PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/run.developer"
~~~

For Cloud Run to run the application using the runtime service account, the build service account also needs actAs permission on the runtime service account:

~~~bash
gcloud iam service-accounts add-iam-policy-binding \
  orders-runtime@PROJECT_ID.iam.gserviceaccount.com \
  --project=PROJECT_ID \
  --member="serviceAccount:cloud-build-deployer@PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/iam.serviceAccountUser"
~~~

The Cloud Run Developer role and Service Account User permission serve different purposes. The first allows managing services within the granted scope; the second allows attaching the runtime identity to the workload. If the pipeline only updates an existing service, consider scoping permissions at the service level or using a custom role rather than granting project-wide access.

If the image resides in a repository in another project, Cloud Run's image-pulling identity may need **roles/artifactregistry.reader** on that repository. This is usually a permission for the Cloud Run service agent or service-designated principal, not a reason to automatically grant Reader to the build service account.

## 6. Specifying the Service Account in cloudbuild.yaml

The serviceAccount field in the build configuration specifies the identity the build uses. The following example builds an image, pushes it to Artifact Registry, and deploys to Cloud Run:

~~~yaml
serviceAccount: projects/PROJECT_ID/serviceAccounts/cloud-build-deployer@PROJECT_ID.iam.gserviceaccount.com

steps:
  - id: Build image
    name: gcr.io/cloud-builders/docker
    args:
      - build
      - -t
      - asia-southeast1-docker.pkg.dev/$PROJECT_ID/app-images/orders-api:$SHORT_SHA
      - .

  - id: Push image
    name: gcr.io/cloud-builders/docker
    args:
      - push
      - asia-southeast1-docker.pkg.dev/$PROJECT_ID/app-images/orders-api:$SHORT_SHA

  - id: Deploy Cloud Run
    name: gcr.io/google.com/cloudsdktool/cloud-sdk
    entrypoint: gcloud
    args:
      - run
      - deploy
      - orders-api
      - --image
      - asia-southeast1-docker.pkg.dev/$PROJECT_ID/app-images/orders-api:$SHORT_SHA
      - --region
      - asia-southeast1
      - --service-account
      - orders-runtime@$PROJECT_ID.iam.gserviceaccount.com
      - --quiet

images:
  - asia-southeast1-docker.pkg.dev/$PROJECT_ID/app-images/orders-api:$SHORT_SHA

options:
  logging: CLOUD_LOGGING_ONLY
~~~

Replace **PROJECT_ID**, repository, region, and service account names with values from your actual environment. In the example, the build service account pushes the image and deploys; the runtime service account is attached to the Cloud Run application. **CLOUD_LOGGING_ONLY** instructs the build to write logs to Cloud Logging, so the build service account needs **roles/logging.logWriter** on the project.

If using a custom log bucket, configure logsBucket and grant appropriate object write permissions on that exact bucket to the build service account. Do not grant project-wide Storage Admin just to write logs. Without an appropriate log destination when using a user-specified service account, the build may fail to start or fail to write logs as expected.

Builds invoked from the CLI can use this configuration:

~~~bash
gcloud builds submit \
  --project=PROJECT_ID \
  --config=cloudbuild.yaml \
  .
~~~

When using triggers, configure the service account on the trigger or build config according to your workflow. The user creating or updating the trigger must have **iam.serviceAccounts.actAs** on the chosen service account. Verify that actual builds use the intended principal after creating or updating a trigger.

## 7. Scoping Permissions by Pipeline Type

An organization typically has multiple pipeline types with varying trust levels. Using a single build service account with production permissions across all branches increases risk from pull requests, dependencies, and build scripts.

| Pipeline | Permissions to Grant | Permissions to Avoid |
| --- | --- | --- |
| Pull request from untrusted branch or fork | Run tests, lint, and produce temporary artifacts in an isolated environment | Deploy to production, read production secrets, modify IAM |
| Build from protected main branch | Read dependencies, build images, and push to staging repository | Project administration or modifying security policies |
| Approved production release | Push artifacts to release repository and deploy designated service | Accessing runtime business data or managing the entire project |
| Infrastructure management pipeline | Required Terraform permissions on the resource scope managed by the pipeline | Sharing principal with application build pipelines |

Dedicated identities such as **cloud-build-test**, **cloud-build-staging**, and **cloud-build-prod** can be created. Only triggers from protected branches or approved release workflows should use the production service account. When steps have different trust levels, split them into separate builds so each build uses a distinct identity.

All steps within the same build normally share the same build service account. Splitting commands across multiple steps in one YAML file does not create an IAM boundary between steps. If one step runs a script from an untrusted pull request or dependency, that script can exercise the build service account's permissions. Never include untrusted steps in a build that holds production deploy permissions or reads sensitive secrets.

## 8. Secret Manager Access and Auxiliary Resources

Only grant secret read permissions to a build when a build step itself requires the secret, such as retrieving a token for a private registry or accessing a test system. If the secret is only used by the application at runtime, grant access to the runtime service account instead of the build service account.

Example granting read access to a specific secret:

~~~bash
gcloud secrets add-iam-policy-binding test-registry-token \
  --project=PROJECT_ID \
  --member="serviceAccount:cloud-build-deployer@PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"
~~~

For buckets, grant only the required object permissions. A build reading input artifacts may need Storage Object Viewer on that bucket; a build writing outputs needs appropriate write permissions on the destination bucket. Do not grant **roles/storage.admin** at the project level just because a pipeline downloads a file or writes logs.

If the build performs direct encryption or decryption operations with Cloud KMS, grant key-usage roles on that exact CryptoKey. If the target service uses CMEK and its service agent performs cryptographic operations, grant permissions to the service agent per the service's documentation. Do not grant Cloud KMS Admin to a build service account just to push images or deploy applications.

## 9. Build Initiator and actAs Permissions

The permissions of the build initiator differ from the permissions of the build service account. The initiator needs permissions to create builds or manage triggers according to their responsibilities. When a build uses a user-specified service account, that user also needs **iam.serviceAccounts.actAs** on the attached service account.

This establishes an important boundary: anyone with actAs permission on a service account can instruct the service to run workloads under that identity. Therefore:

- Grant actAs only to trusted operators or CI systems.
- Grant it on each specific service account needed, not project-wide unless necessary.
- Separate production service accounts from test service accounts.
- Review permissions to create and edit triggers since triggers can run automatically on repository events.
- Control who can modify cloudbuild.yaml, builder images, substitutions, and triggered sources.

Do not allow every contributor to freely modify production triggers or arbitrarily select highly privileged service accounts. Permission to edit pipeline configs can be equivalent to permission to use whatever identity the pipeline is allowed to attach.

## 10. Checking Permissions and Investigating Build Failures

When a build encounters a permission denial, identify the actual principal in the build details before adding roles. Check:

1. Whether the build uses the default or a user-specified service account.
2. Whether the denied principal is the build service account, Cloud Build service agent, target service's service agent, or the initiator.
3. Which permission is missing and which resource is being accessed.
4. Whether existing roles are bound at the project, folder, organization, repository, bucket, or service account level.
5. Whether IAM conditions, organization policies, VPC Service Controls, or other constraints apply.
6. Whether build logs and Cloud Audit Logs record the method, principal, resource, and denial reason.

Do not resolve errors by immediately granting Owner or Editor. Find the exact missing permission, identify which principal needs it, and grant the narrowest role at the appropriate resource scope. Then re-run the pipeline and confirm the build completes the required actions.

If a build fails to write logs when using a user-specified service account, check the logging option, log bucket, and log-writing permissions. If pushing an image fails, check the Artifact Registry repository, location, and Writer role. If Cloud Run rejects deployment, check service management permissions and actAs permissions on the runtime service account. Each failure belongs to a different permission layer.

## 11. Ongoing Controls and Periodic Reviews

A build service account is part of the software supply chain. When its permissions are abused, attackers can alter artifacts, deploy malicious code, or access resources in the project. Maintain the following practices:

- Use dedicated service accounts per pipeline or trust boundary.
- Avoid creating long-lived keys when attached build identities or Workload Identity Federation can be used.
- Pin critical builder images and dependencies by version or digest where appropriate.
- Protect branches, triggers, build configurations, and release approval workflows.
- Enable and review Cloud Audit Logs for changes to IAM, service accounts, triggers, and deployment resources.
- Periodically audit role bindings and actAs permissions; revoke unneeded bindings.
- Monitor who can modify repositories, trigger configs, and builder images.
- Restrict access to build logs because logs may inadvertently contain sensitive information.
- Verify artifacts were created from trusted sources and builds before production deployment.

When investigating incidents, correlate the build ID, source revision, trigger, build service account, artifact digest, and deployment timestamp. This data links repository changes to running artifacts and services.

## 12. Cloud Build Least-Privilege Design Checklist

Before taking a pipeline to production, confirm:

- The build service account is explicitly specified and not shared with the runtime service account.
- The Cloud Build service agent is properly distinguished and not confused with the build execution identity.
- Initiators or trigger administrators only have build creation and actAs permissions on necessary service accounts.
- Image push permissions are scoped to the target Artifact Registry repository.
- Deployment permissions are scoped to the specific project or service being managed.
- Runtime service account actAs permissions are granted only on the specific runtime identity.
- Secrets and buckets are accessed only when the build genuinely needs them.
- Logging options and log destinations match the user-specified service account.
- Pipelines from untrusted pull requests have no production permissions.
- Steps with differing trust levels are split into separate builds when separate IAM boundaries are needed.
- Cloud Audit Logs, build logs, and artifact metadata are sufficient to trace activity.
- Periodic audits and revocation of IAM bindings are performed.

Least privilege for Cloud Build begins with choosing the right identity for each task. When the initiator, service agents, build service account, and runtime service account are clearly separated, each principal receives only the permissions on the resources it needs. The pipeline can then build and deploy effectively while significantly reducing blast radius if an execution step or credential is compromised.

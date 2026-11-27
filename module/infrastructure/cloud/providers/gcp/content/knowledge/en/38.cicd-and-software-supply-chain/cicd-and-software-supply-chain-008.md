# Cloud Deploy Delivery Pipelines, Targets, and Releases

Cloud Deploy is a managed continuous delivery service on Google Cloud. It orchestrates promoting an application version across environments such as development, staging, and production, while recording releases, rollouts, per-step statuses, and approval results.

In a CI/CD workflow, Cloud Build or another CI system builds and tests the application, packages the image, and pushes it to Artifact Registry. Cloud Deploy takes the source and deployment configuration, renders manifests with Skaffold, creates a release, and deploys that release to targets in pipeline order.

Three core concepts to distinguish:

- **Delivery pipeline** describes the release flow and the sequence of environments.
- **Target** describes a deployment destination, such as a GKE cluster or a Cloud Run region.
- **Release** represents an application version together with prepared deployment configuration and artifacts. When a release is deployed to a target, Cloud Deploy creates a **rollout** to track execution progress.

This lesson guides you through designing pipelines, declaring targets, creating releases, promoting across environments, managing approvals, monitoring rollouts, and operating Cloud Deploy securely for GKE and Cloud Run.

## 1. Architecture and Release Lifecycle

Cloud Deploy separates artifact building from artifact deployment. The CI pipeline is responsible for producing a deployable image, running tests, and storing the image in Artifact Registry. Cloud Deploy uses Skaffold to render and deploy configurations to targets.

~~~mermaid
flowchart TD
    A[Source repository] --> B[Cloud Build or CI]
    B --> C[Build and test]
    C --> D[Artifact Registry image]
    D --> E[Create Cloud Deploy release]
    E --> F[Render with Skaffold]
    F --> G[Delivery pipeline]
    G --> H[Staging target]
    H --> I[Review and approval]
    I --> J[Production target]
    J --> K[Verify rollout and service health]
~~~

Typical release flow:

1. A developer merges changes into the release branch.
2. CI runs tests, scans dependencies, and builds the container image.
3. CI pushes the image to Artifact Registry, ideally referenced by digest.
4. CI or a release operator creates a release in Cloud Deploy.
5. Cloud Deploy renders manifests for the release and corresponding target.
6. The initial rollout deploys the release to the first target in the pipeline.
7. After staging verification, the release is promoted to the next target.
8. Targets requiring approval wait for an approver before deploying.
9. The team monitors the rollout, verifies the application, and records results.

Cloud Deploy manages the deployment process, but does not replace application testing, source control, builds, vulnerability scanning, or artifact governance. Those steps should be completed before creating a release.

## 2. Core Cloud Deploy Objects

| Object | Role | Example |
|---|---|---|
| Delivery pipeline | Describes the target flow and deployment strategy | orders-pipeline |
| Target | Represents an environment or deployment destination | orders-staging, orders-prod |
| Skaffold configuration | Describes how to render manifests and deploy the application | skaffold.yaml |
| Release | Release version created from source and artifacts | orders-v1-8-0 |
| Rollout | An instance of deploying a release to a target | rollout to staging |
| Job | A unit of work within a rollout | render, deploy, verify |
| Phase | Deployment stage of a rollout | canary or stable |
| Approval | Decision allowing a rollout to proceed when required by a target | production approval |

Delivery pipelines and targets are Cloud Deploy configuration resources. Releases and rollouts are runtime objects created during the release process.

One pipeline can deploy to multiple targets. One target can be used in one or multiple pipelines if design and access permissions permit. However, establish clear target naming and boundaries to avoid deploying to the wrong environment.

## 3. Preparing Projects and Services

Before creating a pipeline, identify the project hosting Cloud Deploy, the delivery pipeline region, the Artifact Registry project, and the target project or cluster. Cloud Deploy's control plane has its own region; targets can reside in another project or location if permissions and connectivity are configured appropriately.

Enable required APIs, for example:

~~~bash
gcloud services enable clouddeploy.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  container.googleapis.com \
  --project="PROJECT_ID"
~~~

If deploying to Cloud Run, also enable the Cloud Run API:

~~~bash
gcloud services enable run.googleapis.com \
  --project="PROJECT_ID"
~~~

The operator needs permission to enable service APIs. The project also needs an Artifact Registry repository, a built image, and ready GKE or Cloud Run targets.

### Choosing a Region

Cloud Deploy's region is where pipelines, releases, and rollouts are managed. The target's region is where workloads run. These two values do not have to match, but consider:

- Latency and artifact transfer costs.
- Data residency requirements.
- Connectivity from the deployment environment to targets.
- Organizational policies on allowed regions.
- Availability of Cloud Deploy in the chosen region.

Do not pick a pipeline region out of habit without checking against architecture and organizational policies.

## 4. Declaring a Delivery Pipeline and GKE Targets

Cloud Deploy uses YAML configuration files to define pipelines and targets. The example below creates a pipeline with two targets: staging and production.

~~~yaml
apiVersion: deploy.cloud.google.com/v1
kind: DeliveryPipeline
metadata:
  name: orders-pipeline
description: Deploy orders-api through staging and production
serialPipeline:
  stages:
    - targetId: orders-staging
    - targetId: orders-prod
---
apiVersion: deploy.cloud.google.com/v1
kind: Target
metadata:
  name: orders-staging
description: Staging GKE cluster
gke:
  cluster: projects/PROJECT_ID/locations/asia-southeast1/clusters/orders-staging
---
apiVersion: deploy.cloud.google.com/v1
kind: Target
metadata:
  name: orders-prod
description: Production GKE cluster
requireApproval: true
gke:
  cluster: projects/PROJECT_ID/locations/asia-southeast1/clusters/orders-prod
~~~

In this example:

- `metadata.name` of DeliveryPipeline is the pipeline name.
- `serialPipeline.stages` defines the deployment sequence.
- `targetId` must match the declared target name.
- `gke.cluster` is the full path to the GKE cluster.
- `requireApproval: true` requires approval when rolling out to the production target.

Register the configuration with Cloud Deploy:

~~~bash
gcloud deploy apply \
  --file="clouddeploy.yaml" \
  --region="asia-southeast1" \
  --project="PROJECT_ID"
~~~

Verify registered resources:

~~~bash
gcloud deploy delivery-pipelines list \
  --region="asia-southeast1" \
  --project="PROJECT_ID"

gcloud deploy targets list \
  --region="asia-southeast1" \
  --project="PROJECT_ID"
~~~

If a target resides in another project, confirm permissions for the Cloud Deploy service agent and execution service account in the target project. Specifying the cluster path accurately does not automatically grant permission to deploy to the cluster.

## 5. Declaring Skaffold and Application Manifests

Cloud Deploy uses Skaffold to render manifests and invoke the appropriate deployment tool. Skaffold decouples application configuration from release orchestration.

Example configuration for a GKE application using Kubernetes manifests:

~~~yaml
apiVersion: skaffold/v4beta7
kind: Config
metadata:
  name: orders-api
manifests:
  rawYaml:
    - kubernetes/deployment.yaml
    - kubernetes/service.yaml
deploy:
  kubectl: {}
~~~

The deployment manifest can reference an image placeholder so Cloud Deploy substitutes the image provided when creating the release:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders-api
  namespace: production
spec:
  replicas: 3
  selector:
    matchLabels:
      app: orders-api
  template:
    metadata:
      labels:
        app: orders-api
    spec:
      containers:
        - name: orders-api
          image: orders-api
          ports:
            - containerPort: 8080
~~~

When creating the release, map the image placeholder to the Artifact Registry image. Skaffold renders manifests for the release and records the output for Cloud Deploy to use across rollouts.

With Helm or Kustomize, Skaffold can use the corresponding renderer. Pick one clear mechanism and inspect rendered output before deploying. Do not let critical environment values depend on uncontrolled pipeline variables.

### Per-Target Configuration

Skaffold profiles can customize manifests for staging and production, such as replica count, resources, ingress, or namespace names. The delivery pipeline can bind profiles to stages:

~~~yaml
serialPipeline:
  stages:
    - targetId: orders-staging
      profiles:
        - staging
    - targetId: orders-prod
      profiles:
        - production
~~~

Profiles must be declared in the Skaffold configuration. Avoid letting a production profile accidentally point to a staging project, database, or secret. Review rendered manifests to catch environment misconfigurations.

## 6. Creating a Release and Deploying to the First Target

Once the pipeline, targets, and Skaffold config are registered, create a release from the source directory:

~~~bash
gcloud deploy releases create orders-v1-8-0 \
  --delivery-pipeline="orders-pipeline" \
  --region="asia-southeast1" \
  --source="." \
  --images="orders-api=asia-southeast1-docker.pkg.dev/PROJECT_ID/apps/orders-api@sha256:IMAGE_DIGEST" \
  --project="PROJECT_ID"
~~~

In the example, `orders-api` is the image placeholder name in the manifest; the right-hand side is the image stored in Artifact Registry. Using a digest pins the exact image deployed, preventing a tag from being repointed to different content.

Creating a release normally creates a rollout to the pipeline's first target. Check status:

~~~bash
gcloud deploy releases describe orders-v1-8-0 \
  --delivery-pipeline="orders-pipeline" \
  --region="asia-southeast1" \
  --project="PROJECT_ID"

gcloud deploy rollouts list \
  --delivery-pipeline="orders-pipeline" \
  --release="orders-v1-8-0" \
  --region="asia-southeast1" \
  --project="PROJECT_ID"
~~~

A release stores source information, images, Skaffold configuration, and rendered results. When creating a new release, use a unique name following a versioning or build-number convention. Never reuse a release name to represent different content.

### Render and Deploy

Cloud Deploy splits a rollout into jobs. Render prepares manifests for the target; deploy applies rendered manifests to the destination. Separating these two steps lets teams inspect rendered configurations before the rollout proceeds.

If render succeeds but deploy fails, examine the corresponding job and logs to pinpoint the cause: IAM permissions, cluster connectivity, quotas, invalid manifests, inaccessible image, or invalid resources.

## 7. Promoting Releases Across Targets

After a release deploys successfully to staging and passes verification, promote it to production:

~~~bash
gcloud deploy releases promote \
  --release="orders-v1-8-0" \
  --delivery-pipeline="orders-pipeline" \
  --region="asia-southeast1" \
  --to-target="orders-prod" \
  --project="PROJECT_ID"
~~~

Promoting creates a new rollout to the next target. The release remains the exact same application version; target-specific rendering or profiles produce deployment configurations tailored to the environment.

Before promoting, confirm:

- Smoke tests and integration tests in staging succeeded.
- Image digest matches the verified artifact.
- Database migrations are compatible with both prior and new versions.
- Metrics, logs, and alerts show no signs of degradation.
- Release notes and change requests are complete.
- Production target has adequate capacity and deployment permissions.

Do not promote solely because the staging rollout status is Succeeded. Verify business behavior and critical dependencies.

## 8. Approvals, Rollouts, and Status Monitoring

A target with `requireApproval: true` waits for an approver before the rollout continues. This separates the release creator from the person approving deployments to sensitive environments.

List rollouts:

~~~bash
gcloud deploy rollouts list \
  --delivery-pipeline="orders-pipeline" \
  --release="orders-v1-8-0" \
  --region="asia-southeast1" \
  --project="PROJECT_ID"
~~~

Describe rollout details:

~~~bash
gcloud deploy rollouts describe "ROLLOUT_NAME" \
  --delivery-pipeline="orders-pipeline" \
  --release="orders-v1-8-0" \
  --region="asia-southeast1" \
  --project="PROJECT_ID"
~~~

Approve the production rollout:

~~~bash
gcloud deploy rollouts approve "ROLLOUT_NAME" \
  --delivery-pipeline="orders-pipeline" \
  --release="orders-v1-8-0" \
  --region="asia-southeast1" \
  --approve \
  --project="PROJECT_ID"
~~~

Obtain the rollout name from the actual rollout list or details. Do not guess the rollout name from the release name because names can be auto-generated.

### Statuses to Track

- Pending approval: waiting for an approver.
- In progress: rollout is running jobs or phases.
- Succeeded: deployment steps completed.
- Failed: a job or phase failed.
- Cancelled/abandoned: rollout was cancelled or abandoned operationally.

Displayed status names can depend on rollout state and CLI version. When errors occur, inspect specific jobs, execution logs, and target health rather than looking only at the overall status.

Approval is an accountable decision. Approvers should review the release, target, image digest, test results, policies, and expected impact before authorizing the rollout.

## 9. Progressive Delivery, Canary, and Verification

Shifting all traffic to a new version immediately is not always advisable. Progressive delivery breaks a release into smaller steps to limit impact.

### Canary Deployment

Canary deploys the new version to a subset of workloads or traffic first, observes outcomes, and only then expands. Example:

1. Route 5% of traffic or a small replica group to the new version.
2. Monitor error rate, latency, saturation, and business metrics.
3. Increase to 25% or 50% if metrics meet criteria.
4. Shift full traffic once the canary stabilizes.
5. Halt or roll back to the previous version if SLOs are violated.

Cloud Deploy supports canary strategies for supported runtimes. Exact configuration depends on target type and runtime setup. For GKE, configure service networking or appropriate traffic-splitting mechanisms. Do not assume simply adding percentages to the pipeline will split traffic if the application and cluster are not configured for canary routing.

### Verify Jobs

Verification runs post-deployment checks, such as smoke tests, calling health endpoints, or executing a business query. With Cloud Deploy, verification is configured within supported deployment strategies and runs in an appropriate execution environment.

A verify job should:

- Check health endpoints and readiness.
- Execute a handful of safe business requests.
- Verify database or critical dependency connectivity.
- Inspect error rates and latency within an observation window.
- Return a clear exit status so the rollout proceeds or fails.

Do not use a verify job to execute irreversible data migrations without a separate plan. Verification needs timeouts, least-privilege permissions, and logs free of secrets.

## 10. Cloud Run Targets

Cloud Deploy can also deploy Cloud Run services. A Cloud Run target specifies the location of the Cloud Run resource:

~~~yaml
apiVersion: deploy.cloud.google.com/v1
kind: Target
metadata:
  name: orders-run-prod
description: Production Cloud Run region
requireApproval: true
run:
  location: projects/PROJECT_ID/locations/asia-southeast1
~~~

For Cloud Run, Skaffold uses the Cloud Run deployer and an appropriate service manifest:

~~~yaml
apiVersion: skaffold/v4beta7
kind: Config
metadata:
  name: orders-run
manifests:
  rawYaml:
    - cloudrun/service.yaml
deploy:
  cloudrun: {}
~~~

The Cloud Run service manifest describes the service, container image, port, resources, and service account. Never embed secret values directly in the manifest; reference Secret Manager or an appropriate secret management mechanism.

Cloud Deploy creates rollouts to the Cloud Run target following the pipeline. After deployment, verify the new revision, traffic allocation, startup/readiness, logs, and metrics. When using traffic splitting, verify older revisions are retained so traffic can be shifted back if needed.

### Differences Between GKE and Cloud Run Targets

| Aspect | GKE Target | Cloud Run Target |
|---|---|---|
| Destination | Kubernetes cluster | Cloud Run location |
| Manifest | Kubernetes YAML, Helm, or Kustomize via Skaffold | Cloud Run service manifest |
| Deployment permissions | Cluster access and Kubernetes API permissions | Cloud Run service deployment permissions |
| Verification | Pods, Deployments, Services, ingress, and cluster health | Revisions, traffic, instances, requests, and service health |
| Rollback | Deploy previous manifest/release or adjust rollout | Shift traffic to stable revision or deploy prior release |

## 11. IAM and Deployment Identities

Cloud Deploy uses a Google-managed service agent and an execution identity to render/deploy. Release creators, approvers, and deployment service accounts hold distinct responsibilities.

One separation model:

| Identity | Responsibility |
|---|---|
| CI build identity | Build, test, scan, and push images to Artifact Registry |
| Release creator | Create releases from verified source and images |
| Approver | Approve rollouts to targets requiring approval |
| Cloud Deploy service agent | Execute service operations granted to the service agent |
| Execution service account | Run render/deploy jobs and access targets per configuration |
| Runtime service account | Identity used by the application while running on GKE or Cloud Run |

Common Cloud Deploy IAM roles may include:

- `roles/clouddeploy.releaser`: create releases and perform release operations permitted by the role.
- `roles/clouddeploy.approver`: approve rollouts.
- `roles/clouddeploy.viewer`: view Cloud Deploy resources.
- `roles/clouddeploy.operator`: operational actions permitted by the role.
- `roles/clouddeploy.admin`: broader Cloud Deploy administration.

Check exact permissions in IAM documentation and your project scope. Do not grant Cloud Deploy Admin to every developer just to create releases or view status.

### Permissions at the Target

The execution service account needs corresponding permissions at the target:

- For GKE, cluster access and Kubernetes permissions to apply manifests.
- For Cloud Run, service deployment permissions and permission to use the runtime service account when attaching a service identity.
- For Artifact Registry, read access to images being deployed.
- For Cloud Storage staging buckets, artifact access permissions per configuration.

Separate the execution identity from the runtime identity. The deployment service account holds permissions to update workloads; the runtime service account holds only the permissions the application needs while running. Never use a single project-wide Owner identity for both roles.

## 12. Securing the Software Supply Chain and Artifacts

Cloud Deploy accepts artifacts for deployment, so artifact quality and origin must be controlled before creating a release.

Recommended practices:

- Use image digests instead of mutable tags like `latest`.
- Build images in trusted pipelines and restrict push permissions.
- Scan containers and dependencies for vulnerabilities before release.
- Retain SBOMs and build provenance per organizational policy.
- Verify image origin, commit SHA, and test results.
- Use Binary Authorization on GKE if the architecture requires verifying attestations before workloads are allowed to run.
- Never place credentials or secrets inside image layers.
- Restrict artifact read permissions and retention periods.
- Record release name, digest, commit, pipeline, and deployed target.

A single release can be deployed across multiple targets. Reusing the same image digest ensures staging and production run the exact same binary, while manifests or environment parameters can vary per target.

### Cloud Deploy Deploy Parameters

Deploy parameters can pass configuration values to targets or stages in supported cases. Use them for values like namespace names, replica counts, or non-sensitive endpoints. Never use deploy parameters as a secret store; secrets must be retrieved from Secret Manager or an appropriate secret management system.

## 13. Rollback, Retry, and Handling Failed Rollouts

When a rollout fails, determine which job failed and inspect target state before choosing the next action.

### Diagnostics

Check:

1. Do the release and rollout belong to the right pipeline/target?
2. Did the render job succeed?
3. Did the deploy job fail due to IAM, manifest, quota, or API errors?
4. Does the image digest exist and does the execution identity have permission to pull it?
5. Does the GKE workload show Pod Pending, ImagePullBackOff, CrashLoopBackOff, or readiness failures?
6. Does the Cloud Run revision start and receive traffic?
7. Did the verification job fail due to the application or the test environment?

Use Cloud Deploy rollout details and execution logs to pinpoint the exact error. Inspect Cloud Build logs, Cloud Logging, GKE events, or Cloud Run revision logs as appropriate.

### Retry and Rollback

Retries are appropriate for transient errors once the cause is understood, such as an API timeout or a temporarily unavailable dependency. Do not retry endlessly when manifests are invalid, permissions are missing, or images do not exist.

Rollback is typically performed by redeploying a known-good release or shifting traffic back to a stable revision, depending on the target. With Cloud Deploy, create a rollout to deploy a known-good release to the target needing recovery following your pipeline procedure. Verify image digest, manifest, database compatibility, and traffic after rolling back.

Rolling back a container does not automatically revert database schemas or data written by the newer version. Design database migrations to be backward-compatible, separate destructive migrations from application rollouts, and prepare a separate data recovery plan.

### When Not to Retry?

- Policy or approval gates have not passed.
- Image comes from an untrusted source or has blocked vulnerabilities.
- Manifests rendered to the wrong project/namespace.
- Production target is experiencing a broad outage.
- A data migration may have partially executed.
- Retrying could create duplicate resources or repeat business operations.

In these cases, halt the rollout, record the state, and create a new release after fixing the issue or recovering.

## 14. Hands-On Scenario: Releasing orders-api from Staging to Production

A team has an orders-api application running on GKE. Source is built by Cloud Build, images are stored in Artifact Registry, and Cloud Deploy orchestrates across two targets.

### Step 1 — Prepare the Artifact

CI runs unit tests, integration tests, dependency scans, and container scans. It then builds and pushes the image to Artifact Registry. Record commit SHA, image digest, SBOM, and test results.

### Step 2 — Register the Pipeline

Create `clouddeploy.yaml` with two targets: staging and production. Enable `requireApproval: true` on production. Run `gcloud deploy apply` in the proper Cloud Deploy region.

### Step 3 — Create a Release

~~~bash
gcloud deploy releases create orders-v2-1-0 \
  --delivery-pipeline="orders-pipeline" \
  --region="asia-southeast1" \
  --source="." \
  --images="orders-api=asia-southeast1-docker.pkg.dev/PROJECT_ID/apps/orders-api@sha256:IMAGE_DIGEST" \
  --project="PROJECT_ID"
~~~

Cloud Deploy renders manifests and creates a rollout to the staging target.

### Step 4 — Verify Staging

- Monitor the rollout and deploy job.
- Confirm the Deployment has sufficient Ready replicas.
- Run smoke tests and verify business flows.
- Monitor error rate, p95 latency, and logs.
- Record test results alongside release name and image digest.

### Step 5 — Promote and Approve

~~~bash
gcloud deploy releases promote \
  --release="orders-v2-1-0" \
  --delivery-pipeline="orders-pipeline" \
  --region="asia-southeast1" \
  --to-target="orders-prod" \
  --project="PROJECT_ID"
~~~

While the production rollout waits for approval, the approver reviews the change request, test results, digest, policies, and blast radius. After approval, Cloud Deploy proceeds with deployment.

### Step 6 — Verify Production

Confirm the rollout status is Succeeded, the new revision or Deployment receives traffic, and request success ratio and latency stay within SLOs. If degradation appears, halt further promotion and execute a rollback to a known-good release.

## 15. Cloud Deploy Operational Checklist

### Before Creating a Pipeline

- [ ] Project, region, and environment boundaries identified.
- [ ] Cloud Deploy, Cloud Build, Artifact Registry, and target APIs enabled.
- [ ] Delivery pipeline and target IDs clearly named.
- [ ] GKE cluster or Cloud Run location is accurate.
- [ ] Skaffold config and manifests validated.
- [ ] Execution service account has least privilege.

### Before Creating a Release

- [ ] CI tests and scans succeeded.
- [ ] Image is stored in Artifact Registry.
- [ ] Release uses a verified image digest.
- [ ] Source commit and release name recorded.
- [ ] Rendered manifests contain no secrets or wrong-environment configs.
- [ ] Policy and supply chain checks passed.

### Before Promoting

- [ ] Rollout to previous target succeeded.
- [ ] Smoke tests and integration tests passed.
- [ ] Metrics, logs, and alerts show no anomalies.
- [ ] Database migrations are compatible with currently running versions.
- [ ] Change request and approver are ready.
- [ ] Production target requires approval where needed.

### After Deployment

- [ ] Rollout and job statuses verified.
- [ ] New workload/revision receives traffic properly.
- [ ] SLIs remain within SLOs.
- [ ] Release, image digest, commit, and approval recorded.
- [ ] Stable release available for rollback.
- [ ] IAM, pipeline, and target permissions reviewed periodically.

Cloud Deploy standardizes multi-environment releases using delivery pipelines, targets, releases, and rollouts. When pipelines use immutable artifacts, targets have scoped permissions, approvals are tied to test results, and rollouts are monitored until SLOs stabilize, teams can deploy applications to GKE or Cloud Run consistently, traceably, and recoverably when needed.

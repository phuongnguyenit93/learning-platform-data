# Automated Deployment to Cloud Run and GKE

After Cloud Build tests and builds a container image, the pipeline must deliver that exact artifact to the runtime environment. On Cloud Run, the deployment step creates a new revision of the service; on Google Kubernetes Engine (GKE), the pipeline updates Kubernetes workloads in the cluster. A well-built automated deployment process links source commit, build, image digest, and release, while controlling identities, access permissions, health checks, and rollback capability.

This lesson belongs to the **CLOUD_PROVIDERS_GCP** module. The module helps learners explore Google Cloud from project organization, IAM, and VPC to Compute Engine, GKE, Cloud Run, storage services, and databases. Through deployment scenarios, learners know how to select services, secure resources, automate releases, and monitor reliability and cost. Within this lesson, we focus on building Cloud Build pipelines to deploy Java applications to Cloud Run and GKE, managing environments, post-deployment verification, and recovering when releases encounter issues.

## Objectives

After this lesson, you will be able to:

- Describe the CI/CD flow from commit to deployment on Cloud Run and GKE.
- Distinguish between build service accounts, runtime service accounts, and Kubernetes workload identities.
- Create a Cloud Build pipeline to build, push images, and deploy automatically.
- Use substitutions to select project, region, cluster, service, and image.
- Deploy Cloud Run revisions, control traffic, and verify new revisions.
- Update Kubernetes Deployments on GKE and monitor rollouts.
- Design triggers, approvals, and permission boundaries between staging and production.
- Add smoke tests, health checks, canaries, and rollbacks to the release workflow.
- Trace artifacts via commit SHA, image digest, and build metadata.

## 1. The Big Picture: From Source to Runtime

CI (Continuous Integration) verifies source code changes and produces artifacts. CD (Continuous Delivery or Continuous Deployment) delivers verified artifacts to target environments via a defined process. Cloud Build can perform both: building images, running tests, pushing images to Artifact Registry, and invoking deployment commands to Cloud Run or GKE.

~~~mermaid
flowchart TD
    A["Commit to repository"]
    B["Cloud Build trigger"]
    C["Compile, unit tests, and checks"]
    D["Build container image"]
    E["Push Artifact Registry"]
    F{"Target environment"}
    G["Deploy Cloud Run revision"]
    H["Deploy Kubernetes workload to GKE"]
    I["Smoke test and health checks"]
    J["Monitor metrics, logs, and rollout"]
    A --> B --> C --> D --> E --> F
    F --> G --> I
    F --> H --> I
    I --> J
~~~

Artifact Registry stores images so pipelines and runtimes can reference them. Cloud Run creates new revisions from images; GKE updates Pods via a Kubernetes Deployment or another workload controller. Both platforms should receive the exact same built and tested image, rather than rebuilding from source separately per environment.

### Environments and Release Boundaries

A typical workflow includes:

- **Development:** rapid checks during coding.
- **Staging:** validating images, configuration, integration, and production-like smoke tests.
- **Production:** controlled releases, impact monitoring, and rollback plans.

You can use a single build config with substitutions or separate triggers per environment. However, branch names or substitution values are not security boundaries. Production deployment permissions must be protected by IAM, service accounts, trigger policies, and appropriate approvals.

## 2. Preparing Artifact Registry and Deployment Identities

Before creating the pipeline, identify the project, region, repository, service or cluster, and the service account the build will use. Provision infrastructure resources through your organization's governance processes—never let a production build create projects, clusters, or IAM bindings ad hoc on every run.

### Enabling Required APIs

Example enabling APIs for a test project:

~~~bash
export PROJECT_ID="your-project-id"
export REGION="asia-southeast1"

gcloud config set project "$PROJECT_ID"

gcloud services enable \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  run.googleapis.com \
  container.googleapis.com \
  --project="$PROJECT_ID"
~~~

Enable only APIs for platforms actually in use. If the pipeline only deploys to Cloud Run, there is no need to enable the Kubernetes Engine API for that workflow.

### Creating the Docker Repository

~~~bash
gcloud artifacts repositories create app-images \
  --repository-format=docker \
  --location="$REGION" \
  --description="Container images for application deployments" \
  --project="$PROJECT_ID"
~~~

An Artifact Registry image path has the form:

~~~text
REGION-docker.pkg.dev/PROJECT_ID/REPOSITORY/IMAGE:TAG
~~~

Example:

~~~text
asia-southeast1-docker.pkg.dev/my-project/app-images/orders-api:BUILD_ID
~~~

The build pipeline needs permission to write images to the repository. The runtime needs permission to read images if the repository sits in another project or default settings do not grant access. Never grant project-wide admin rights just to push or pull images.

### Separating Build Identity and Runtime Identity

There are at least two identities to distinguish:

1. **Build service account:** used by Cloud Build to run build steps, push images, and call deployment APIs.
2. **Runtime service account:** used by the Cloud Run service or workload while running to access Secret Manager, databases, Pub/Sub, and other services.

On GKE, there is also the Pod's Kubernetes ServiceAccount identity. If the workload calls Google Cloud APIs, use Workload Identity Federation for GKE to map the Kubernetes ServiceAccount to the appropriate Google Cloud permissions.

Do not use the build service account as the runtime identity. Builds may need deployment or artifact-writing permissions; running applications should hold only minimum business permissions.

## 3. Cloud Build Pipeline: Building One Shared Image

A deployment pipeline should build an image once, push it to Artifact Registry, and use that exact image for target environments. Use BUILD_ID or commit SHA as the tag to identify the build run. For production releases, record the image digest to pinpoint the exact content deployed.

### Example cloudbuild.yaml

Suppose the repository holds a Java Maven application, with a Dockerfile at the root directory and Maven producing target/app.jar.

~~~yaml
substitutions:
  _REGION: asia-southeast1
  _AR_REPOSITORY: app-images
  _IMAGE: orders-api

steps:
  - id: test-and-package
    name: maven:3.9.9-eclipse-temurin-21
    entrypoint: mvn
    args:
      - -B
      - verify

  - id: build-image
    name: gcr.io/cloud-builders/docker
    args:
      - build
      - -t
      - $_REGION-docker.pkg.dev/$PROJECT_ID/$_AR_REPOSITORY/$_IMAGE:$BUILD_ID
      - .
    waitFor:
      - test-and-package

  - id: push-image
    name: gcr.io/cloud-builders/docker
    args:
      - push
      - $_REGION-docker.pkg.dev/$PROJECT_ID/$_AR_REPOSITORY/$_IMAGE:$BUILD_ID
    waitFor:
      - build-image

options:
  logging: CLOUD_LOGGING_ONLY

timeout: 1200s
~~~

In this example:

- Maven runs verify to compile, test, and execute checks configured in the project.
- Docker build builds an image from the Dockerfile after tests pass.
- Docker push uploads the image to Artifact Registry.
- The images field declares the build's output image.
- BUILD_ID creates a distinct tag per build run, avoiding mutable tags like latest as the sole identifier.

The Dockerfile must match the artifact generated by Maven:

~~~dockerfile
FROM eclipse-temurin:21-jre

WORKDIR /app
COPY target/app.jar app.jar

ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

For production, pin the base image by version or digest, scan images and dependencies, and manage the Dockerfile like reviewable source code. Confirm the actual JAR filename or Maven finalName to prevent COPY failures during builds.

### Running the Build

~~~bash
gcloud builds submit . \
  --config=cloudbuild.yaml \
  --project="$PROJECT_ID" \
  --region="$REGION"
~~~

When the build succeeds, record the image URI and digest in build outputs or release metadata. Tags help humans identify versions; digests are immutable identifiers of the image manifest and enable tracing deployed artifacts.

## 4. Automated Deployment to Cloud Run

Cloud Run runs containers as services. Each image deployment or configuration change creates a new revision. Traffic can be routed to the new revision immediately, held at zero traffic for testing, or split by percentage across revisions for progressive verification and rollout.

### Required Permissions

A build service account deploying Cloud Run typically needs:

- Cloud Run service management permissions, typically roles/run.admin at the appropriate scope.
- iam.serviceAccounts.actAs on the runtime service account attached to the service.
- Artifact Registry read or write permissions matching pipeline actions.
- Build log writing permissions if using Cloud Logging.

Exact roles depend on architecture and resource scope. Avoid granting Owner or Editor to the build service account. The application's runtime service account is specified separately and needs no deployment permissions.

### Adding the Cloud Run Deploy Step

After the push-image step, add this step:

~~~yaml
  - id: deploy-cloud-run
    name: gcr.io/google.com/cloudsdktool/google-cloud-cli:stable
    entrypoint: gcloud
    args:
      - run
      - deploy
      - $_SERVICE
      - --image
      - $_REGION-docker.pkg.dev/$PROJECT_ID/$_AR_REPOSITORY/$_IMAGE:$BUILD_ID
      - --region
      - $_REGION
      - --project
      - $PROJECT_ID
      - --platform
      - managed
      - --service-account
      - $_RUNTIME_SERVICE_ACCOUNT
      - --quiet
    waitFor:
      - push-image
~~~

Declare additional build-level substitutions:

~~~yaml
substitutions:
  _REGION: asia-southeast1
  _AR_REPOSITORY: app-images
  _IMAGE: orders-api
  _SERVICE: orders-api
  _RUNTIME_SERVICE_ACCOUNT: orders-runtime@my-project.iam.gserviceaccount.com
~~~

This supplements the pipeline from the previous section. Merge the substitutions fields into one block—do not create two substitutions keys in the same YAML file. Replace project, region, repository, service, and runtime service account with values from your real environment.

The deploy command in this example does not automatically open public access. If the service requires public access, make that an explicit decision and configure IAM invoker per organizational policy. For internal services, keep authentication enforced and configure ingress appropriately.

### Runtime Configuration

Configuration can be declared during deployment:

~~~bash
gcloud run deploy orders-api \
  --image="asia-southeast1-docker.pkg.dev/my-project/app-images/orders-api:BUILD_ID" \
  --region=asia-southeast1 \
  --service-account="orders-runtime@my-project.iam.gserviceaccount.com" \
  --set-env-vars="APP_ENV=production,LOG_LEVEL=INFO" \
  --min=1 \
  --max=20 \
  --concurrency=80
~~~

These values are examples and must be tuned for load, cost, and application behavior. Never pass passwords or tokens via --set-env-vars; use Cloud Run's Secret Manager integration or an appropriate secret retrieval mechanism. Manage configuration per environment so one deployment does not accidentally overwrite essential service settings.

### Verifying the New Revision

After deployment:

~~~bash
gcloud run services describe orders-api \
  --region=asia-southeast1 \
  --format="value(status.latestReadyRevisionName,status.url)"
~~~

You can list revisions:

~~~bash
gcloud run revisions list \
  --service=orders-api \
  --region=asia-southeast1
~~~

Smoke tests should check health endpoints or minimal business flows. If the service requires authentication, use a test identity with invoker permission and obtain an identity token securely. Never disable authentication just to simplify smoke tests. Never declare a deployment successful solely because the gcloud command exited cleanly; confirm the revision is Ready and real requests work.

### Deploying Without Immediate Traffic

For high-risk changes, deploy a new revision without shifting traffic yet:

~~~bash
gcloud run deploy orders-api \
  --image="asia-southeast1-docker.pkg.dev/my-project/app-images/orders-api:BUILD_ID" \
  --region=asia-southeast1 \
  --no-traffic \
  --tag=candidate
~~~

A revision tagged with candidate gets its own URL for testing before receiving live traffic. After smoke tests and metric checks pass, shift traffic using update-traffic:

~~~bash
gcloud run services update-traffic orders-api \
  --region=asia-southeast1 \
  --to-revisions=orders-api-00042-abc=90,orders-api-00043-def=10
~~~

The example routes 90% of traffic to the stable revision and 10% to the new revision. Replace revision names with real values. When ready to send all traffic to the latest ready revision, use --to-latest. Before running the command, inspect the current revision list and traffic split.

### Cloud Run Rollback

If the new revision causes errors, shift traffic back to the prior stable revision:

~~~bash
gcloud run services update-traffic orders-api \
  --region=asia-southeast1 \
  --to-revisions=orders-api-00042-abc=100
~~~

Revision names in the example are illustrative. Retrieve the actual revision from Cloud Run before rolling back. Shifting traffic back does not revert database schema or data changes; evaluate backward compatibility of both application and migrations prior to every release.

## 5. Automated Deployment to Google Kubernetes Engine

GKE runs applications inside Kubernetes clusters. Pipelines typically build and push an image to Artifact Registry, then update manifests or the Deployment image so Kubernetes creates a new ReplicaSet and Pods. The Deployment controller monitors rollout status and maintains the desired replica count.

### Preparing the Cluster and Namespace

The pipeline needs to know the project, cluster, location, and namespace. Clusters can be regional or zonal; pass the right --region or --zone flag when fetching cluster credentials. Namespaces separate workloads by environment or application group, but do not replace IAM and Kubernetes RBAC.

Example creating a namespace:

~~~bash
kubectl create namespace production
~~~

In production environments, namespaces are normally managed via manifests or GitOps rather than created imperatively during every build.

### Kubernetes Manifest

Example Deployment for a Java application:

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
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0
  template:
    metadata:
      labels:
        app: orders-api
    spec:
      serviceAccountName: orders-api
      containers:
        - name: orders-api
          image: REGION-docker.pkg.dev/PROJECT_ID/app-images/orders-api:IMAGE_TAG
          ports:
            - name: http
              containerPort: 8080
          resources:
            requests:
              cpu: 250m
              memory: 512Mi
            limits:
              cpu: "1"
              memory: 1Gi
          startupProbe:
            httpGet:
              path: /actuator/health
              port: http
            periodSeconds: 5
            failureThreshold: 30
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: http
            periodSeconds: 5
            failureThreshold: 3
          livenessProbe:
            httpGet:
              path: /actuator/health/liveness
              port: http
            periodSeconds: 10
            failureThreshold: 3
~~~

This manifest assumes a Spring Boot application exposing those health endpoints on port 8080. If using another framework, replace paths and ports with actual endpoints. The startup probe gives the application time to boot; the readiness probe determines when a Pod receives traffic; the liveness probe detects unhealthy containers so kubelet restarts them.

Requests and limits must be grounded in load testing and real observations. Requests drive scheduling; limits cap container resources. Setting them too low causes throttling or OOMKilled; setting them too high wastes capacity.

### Granting Permissions to the Build Service Account

To deploy to GKE, the build service account needs permission to fetch cluster credentials and interact with the Kubernetes API. An IAM role such as roles/container.developer grants workload management permissions at an appropriate level, though in-cluster Kubernetes RBAC can further constrain allowed actions. Some cluster administration tasks need higher privileges; never grant cluster-admin to an application pipeline if it only needs to update a Deployment in a dedicated namespace.

The build service account also needs permission to push images to Artifact Registry. Runtime Pods use the Kubernetes ServiceAccount orders-api in the example; if the workload calls Google Cloud APIs, configure Workload Identity Federation for GKE so that identity receives only necessary permissions.

### Deploying with the gke-deploy Builder

Cloud Build provides the gke-deploy builder for deploying manifests to GKE. After the image is pushed, add a step:

~~~yaml
  - id: deploy-gke
    name: gcr.io/cloud-builders/gke-deploy
    args:
      - run
      - --filename=k8s/
      - --image=$_REGION-docker.pkg.dev/$PROJECT_ID/$_AR_REPOSITORY/$_IMAGE:$BUILD_ID
      - --location=$_GKE_LOCATION
      - --cluster=$_GKE_CLUSTER
      - --namespace=$_GKE_NAMESPACE
    waitFor:
      - push-image
~~~

Add matching substitutions:

~~~yaml
substitutions:
  _REGION: asia-southeast1
  _AR_REPOSITORY: app-images
  _IMAGE: orders-api
  _GKE_LOCATION: asia-southeast1
  _GKE_CLUSTER: production-cluster
  _GKE_NAMESPACE: production
~~~

This step extends the build/push pipeline from earlier. Merge substitutions into a single block. The k8s/ directory must contain valid manifests. The builder uses the image passed via --image to update the image reference in manifests via gke-deploy's mechanism, then applies them to the cluster.

### Deploying with the kubectl Builder

An alternative is using the kubectl builder when explicit control over Kubernetes commands is desired:

~~~yaml
  - id: apply-manifests
    name: gcr.io/cloud-builders/kubectl
    args:
      - apply
      - -f
      - k8s/
    env:
      - CLOUDSDK_COMPUTE_REGION=asia-southeast1
      - CLOUDSDK_CONTAINER_CLUSTER=production-cluster
    waitFor:
      - push-image
~~~

The builder needs the cluster and location to fetch credentials. This approach applies manifests verbatim; the pipeline must update the image tag or manifest beforehand. You can use substitutions to render manifests or run kubectl set image after applying, while ensuring the Deployment does not run the old image in between the two commands. For simpler pipelines, gke-deploy generally makes binding the built image to manifests cleaner.

Do not use both gke-deploy and kubectl apply on the same manifests without reason, as doing so creates two updates and complicates rollout tracking.

### Monitoring the Rollout and Inspecting Pods

After applying:

~~~bash
kubectl rollout status deployment/orders-api \
  --namespace=production \
  --timeout=5m
~~~

View Pods:

~~~bash
kubectl get pods \
  --namespace=production \
  -l app=orders-api
~~~

Inspect Deployment status:

~~~bash
kubectl describe deployment orders-api \
  --namespace=production
~~~

If the rollout stalls, inspect events, readiness probes, image pulls, resource requests, quotas, node capacity, and container logs. Do not proceed to smoke tests while the rollout is still failing or Pods are not Ready.

### GKE Rollback

Kubernetes Deployments retain rollout history when revision history is preserved. You can roll back to a previous revision:

~~~bash
kubectl rollout history deployment/orders-api \
  --namespace=production

kubectl rollout undo deployment/orders-api \
  --namespace=production
~~~

After rolling back, confirm the rollout finishes and Pods run the right image. Rolling back a Deployment does not automatically undo database migrations or other resource changes applied in the same pipeline. For schema changes, use an expand-and-contract strategy so old and new application versions coexist during transition.

## 6. One Pipeline Deploying to Either Cloud Run or GKE

The exact same image can be released to either platform using substitutions or separate triggers. Do not allow an arbitrary input variable to determine a production target without permission controls.

Example organization:

| Trigger | Source | Build | Deploy Target |
|---|---|---|---|
| Pull request | Feature branch | Test, scan, trial build | No production deployment |
| Merge to main | Main branch | Test, build, push image | Cloud Run staging or GKE staging |
| Release tag | Version tag | Verify artifact and provenance | Production via approval |

You can share one build config with substitutions such as _TARGET, _REGION, _SERVICE, or _GKE_CLUSTER. However, if Cloud Run and GKE have substantially different permissions or procedures, two separate triggers or two configs are usually easier to review and scope.

### Target Validation Example

A shell step can validate required variables before deploying:

~~~yaml
  - id: validate-deploy-input
    name: bash
    entrypoint: bash
    args:
      - -ceu
      - |
        test -n "$_TARGET"
        case "$_TARGET" in
          cloud-run|gke) ;;
          *) echo "Unsupported deployment target" >&2; exit 1 ;;
        esac
    waitFor:
      - push-image
~~~

This example illustrates target validation; escape shell variables if the script uses shell-expanded environment variables. With Cloud Build substitutions, custom values start with an underscore and are replaced before the step runs. Declare explicit defaults or use MUST_MATCH for required variables to avoid empty strings.

## 7. Cloud Build Triggers and Approval Workflows

Cloud Build triggers can fire on branch pushes, tag pushes, or pull requests. For production releases, use a dedicated trigger tied to release tags or a protected release workflow.

A typical workflow:

1. Pull requests run compilation, unit tests, static analysis, and dependency scans.
2. Merging into main builds the image, pushes to Artifact Registry, and deploys to staging.
3. Smoke tests, integration tests, and SLI checks verify staging behavior.
4. A release tag or approval action triggers the production pipeline.
5. The production pipeline deploys the exact image digest verified in staging.
6. After deploying, the pipeline checks the revision or rollout and runs smoke tests.
7. Monitor metrics during an observation window before closing the release.

Cloud Build approvals can require an authorized approver to approve the build before subsequent steps run. Grant approval permissions to the appropriate group and retain logs of release decisions.

Never allow pull requests from forks or untrusted sources to run under a service account with production deploy permissions or secret access. Build scripts can execute arbitrary commands; therefore, source trust level must dictate the build's identity and granted permissions.

## 8. Post-Deployment Verification

A successful deploy command only confirms the API accepted the configuration. It does not prove the application is ready to serve users. Pipelines should include platform-specific verification steps.

### Cloud Run

- New revision is Ready.
- Service URL or internal endpoint is reachable using an appropriate identity.
- Smoke tests return expected responses.
- Logs show no startup errors, missing secrets, or dependency connection failures.
- Request count, error rate, and latency show no abnormal degradation.
- Traffic routes to the expected revision.

### GKE

- Deployment rollout completed.
- Ready replicas match desired replicas.
- No Pods are in CrashLoopBackOff, ImagePullBackOff, or OOMKilled.
- Readiness probes succeed before Pods receive traffic.
- Services and Ingress/Gateway point to the right endpoints.
- Metrics, logs, and events show no abnormal errors.

### Smoke Tests

Example checking a public health endpoint:

~~~bash
curl --fail --silent --show-error \
  "https://orders-api-EXAMPLE.run.app/actuator/health"
~~~

If the endpoint requires authentication, fetch an identity token from a test identity granted invoker permission. Never disable authentication just to make smoke tests simpler. For internal GKE services, run tests from a runner with appropriate network access or use an in-cluster test job.

Smoke tests should check a few critical flows quickly. Deep integration tests, load tests, or data checks should be designed as separate stages to avoid slowing down every deployment unnecessarily.

## 9. Rollout Strategies and Reducing Blast Radius

Not every release should receive 100% of traffic immediately. Choose strategies based on change risk, observability, and data compatibility.

### Cloud Run Revisions and Traffic Splitting

Cloud Run creates an immutable revision for every new configuration deployment. You can:

- Shift all traffic to the new revision.
- Deploy the new revision with --no-traffic to verify first.
- Assign a tag to the candidate revision for a dedicated test URL.
- Split traffic by percentage across revisions.
- Shift traffic back to a stable revision if metrics degrade.

When stepping up traffic, monitor error ratio, latency, saturation, and business metrics. Do not rely solely on a single passing health request.

### GKE Rolling Updates

Kubernetes Deployments support RollingUpdate with maxSurge and maxUnavailable. maxSurge caps how many Pods can exceed the desired replica count during updates; maxUnavailable caps how many Pods can be unavailable. Setting maxUnavailable to 0 keeps full Ready Pod capacity during rollouts provided the cluster has spare capacity and readiness probes reflect true readiness.

Rolling updates replace Pods incrementally, but do not inherently provide weighted traffic splitting between two versions. If traffic-percentage canaries are required, use Gateway, a service mesh, or an appropriate progressive delivery controller and verify actual routing behavior.

### Rollout Halt Criteria

Define signals to pause or roll back beforehand:

- Error rate exceeds threshold over a sustained window.
- P95/P99 latency rises above SLO or established baseline.
- Pods restart repeatedly or revisions fail to become Ready.
- Queue age or backlog grows abnormally.
- Business errors such as payment failures or duplicate order processing increase.
- Smoke tests or synthetic checks fail.

Alerts and rollout gates should rely on user-impacting metrics. High CPU may warrant investigation, but does not always mean a release failed.

## 10. Database Migrations and Backward Compatibility

Application rollbacks are only safe when the prior version can operate against the current data state. If a release drops a column or alters a data type immediately, the old revision may fail to start after rolling back.

Use the expand-and-contract strategy:

1. **Expand:** add new tables, columns, or structures in a way still compatible with the old application.
2. **Deploy compatible code:** release code capable of reading/writing both old and new structures as needed.
3. **Migrate data:** backfill data in batches and verify.
4. **Switch reads/writes:** gradually transition the application to the new structure.
5. **Contract:** drop old structures only after all revisions and consumers have switched over.

Migrations may need to run once as a dedicated step before or after deployment. Never run non-idempotent migrations on every replica startup. Use controlled jobs or stages with logged results and recovery plans.

## 11. Security in the Deployment Pipeline

A pipeline authorized to deploy to production is a privileged component. Protect source code, build configs, images, and execution identities.

- Use separate build service accounts per environment or purpose.
- Grant Cloud Run or GKE deployment permissions at the narrowest scope.
- Restrict iam.serviceAccounts.actAs to authorized runtime service accounts.
- Grant Artifact Registry writer on the repository needing pushes; grant reader to runtime principals as needed.
- Never store credentials in substitutions, Dockerfiles, or source code.
- Read secrets via Secret Manager and supply them only to steps that need them.
- Separate untrusted pull request triggers from release triggers.
- Require approval for production when processes call for manual control.
- Use image digests so staging and production run the exact same artifact.
- Scan images and dependencies, and generate/verify provenance per supply chain policies.
- Record who initiated, approved, and deployed each release.

For GKE, distinguish IAM permissions for cluster access from in-cluster Kubernetes RBAC. A principal may fetch credentials yet still lack permission to create Deployments in a namespace. Grant namespace-scoped Roles and RoleBindings when appropriate, rather than cluster-admin.

## 12. Monitoring Deployments with Cloud Monitoring and Cloud Logging

After every release, correlate the deployment with operational signals:

- Record build ID, commit SHA, image tag, and digest in release metadata.
- Record the Cloud Run revision or GKE workload image version.
- Monitor request count, error rate, latency, and instance/Pod health.
- Monitor CPU, memory, restart count, queue depth, and dependency latency.
- Use structured logs containing service, environment, revision, and trace context.
- Create release dashboards to compare pre- and post-deploy baselines.
- Alert on user-impacting errors rather than only resource utilization states.

During incidents, this context helps identify which release introduced the change, which environments are affected, and whether to roll back. Never include tokens or personal data in build metadata or logs.

## 13. Common Troubleshooting

| Symptom | Possible Cause | How to Check |
|---|---|---|
| Cloud Run deploy gets permission denied | Build service account lacks run.admin or actAs | Check IAM on the service and runtime service account |
| Cloud Run revision fails to become Ready | Container fails to start, wrong port, or missing config | Inspect revision conditions and logs |
| Cloud Run fails to pull image | Wrong image URI or missing Artifact Registry reader | Verify repository location and runtime service agent |
| GKE credential retrieval fails | Wrong project/location/cluster or missing IAM | Verify cluster details and container permissions |
| kubectl apply gets Forbidden | Missing Kubernetes RBAC | Check RoleBindings in the namespace |
| Pod ImagePullBackOff | Wrong image path, tag, or pull permission | Inspect Pod events and image URI |
| Pod CrashLoopBackOff | App startup error or missing configuration | Inspect container logs, secrets, and dependencies |
| Rollout hangs | Readiness probe failing or insufficient capacity | Inspect rollout status, Pod conditions, and events |
| Smoke test returns 401/403 | Endpoint requires authentication | Use a test identity with proper invoker permissions |
| Errors persist after app rollback | Incompatible database migration or side effects | Check schema, data, and dependency states |

Never resolve permission errors by immediately granting Owner or cluster-admin. Identify the exact denied API or Kubernetes resource and grant the needed permission at the narrowest scope.

## 14. Hands-On Exercise: Deploying a Java Service to Cloud Run and GKE

Suppose a repository contains a Java application named orders-api. The team needs to build one image and deploy the same artifact to Cloud Run staging and GKE staging.

Steps:

1. Create an Artifact Registry repository in the chosen region.
2. Create runtime service accounts for Cloud Run and Kubernetes workloads.
3. Create a build service account with properly scoped test/build/push and deploy permissions.
4. Write a Cloud Build config running Maven verify, building a Docker image, and pushing with tag BUILD_ID.
5. Record the image URI and build digest.
6. Add a Cloud Run staging deploy step using gcloud run deploy.
7. Verify the revision is Ready and run smoke tests with an appropriate identity.
8. Prepare a Kubernetes Deployment manifest with resource requests/limits and startup/readiness/liveness probes.
9. Add a gke-deploy or kubectl step to update the workload on the staging cluster.
10. Monitor kubectl rollout status and confirm Ready replicas.
11. Run smoke tests for the GKE service from a network able to reach the endpoint.
12. Simulate an image with a startup failure in a test environment; observe how the revision or rollout fails health checks.
13. Roll back to a stable revision/image and re-verify.
14. Create separate triggers for main and release tags; confirm the production trigger enforces approval and isolated permissions.
15. Confirm Cloud Run and GKE use the exact same tested image digest.

### Completion Criteria

- Build and tests finish before deployment.
- Image is pushed to the right Artifact Registry repository.
- Build ID, commit, and digest are traceable.
- Cloud Run revision is Ready and smoke tests pass.
- GKE rollout completes and Ready replicas match desired count.
- Runtime identity is separate from build identity with least privilege.
- Rollback has been tested in staging.
- Production triggers have explicit permission boundaries and approvals.

## Checklist Before Automating Production Deployments

- [ ] Build creates the artifact once and promotes the same artifact across environments.
- [ ] Image is stored in Artifact Registry with a traceable digest.
- [ ] Build service account and runtime service account are separated.
- [ ] Cloud Run, Artifact Registry, GKE IAM, and Kubernetes RBAC permissions are restricted.
- [ ] Pull request triggers have no production permissions or sensitive secrets.
- [ ] Production releases enforce approval or equivalent control.
- [ ] Cloud Run revisions are verified Ready before shifting traffic.
- [ ] GKE Deployments include readiness probes and rollout status is verified.
- [ ] Smoke tests run using an appropriate identity and network path.
- [ ] Rollouts have halt criteria and rollback procedures.
- [ ] Database migrations stay compatible with prior versions during transitions.
- [ ] Metrics, logs, and traces include revision/image context for investigation.
- [ ] Secrets never appear in build configs, substitutions, or logs.
- [ ] Artifacts, builds, and deployments trace back to source commits.

## Self-Check Questions

**1. Why build an image once and use the same image for staging and production?**

It guarantees the exact tested artifact is the one released and supports traceability via image digest.

**2. How does a build service account differ from a runtime service account?**

The build service account performs build, push, and deploy actions. The runtime service account is the identity used by the running application to access required services.

**3. How do Cloud Run revisions help with rollouts and rollbacks?**

Each revision captures a specific configuration and image version. You can verify a new revision, split traffic by percentage, and shift traffic back to a stable revision.

**4. How do readiness probes in GKE affect rollouts?**

Probes determine whether a Pod is ready to receive traffic. The Deployment controller uses readiness status to orchestrate rolling updates.

**5. Why does obtaining GKE credentials not guarantee you can deploy workloads?**

IAM grants access to the cluster, but Kubernetes RBAC can still deny actions on Deployments or namespaces.

**6. Why might rolling back an application be insufficient after a database migration?**

Schemas or data may have changed in ways incompatible with the prior application version. You need expand-and-contract migrations and a data recovery plan.

**7. What conditions should halt a rollout?**

For example, error rate exceeding thresholds, latency breaching SLOs, revisions failing to become Ready, repeated Pod restarts, abnormal queue backlog growth, or failing smoke tests.

## References

- [Cloud Build: Deploying to Cloud Run](https://cloud.google.com/build/docs/deploying-builds/deploy-cloud-run)
- [Cloud Build: Deploying to GKE](https://cloud.google.com/build/docs/deploying-builds/deploy-gke)
- [Cloud Run: Deploying services](https://cloud.google.com/run/docs/deploying)
- [Cloud Run: Managing revisions and traffic](https://cloud.google.com/run/docs/rollouts-rollbacks-traffic-migration)
- [Cloud Run: Service identity](https://cloud.google.com/run/docs/securing/service-identity)
- [GKE: Deploying applications](https://cloud.google.com/kubernetes-engine/docs/how-to/deploying-workloads)
- [Kubernetes: Deployments](https://kubernetes.io/docs/concepts/workloads/controllers/deployment/)
- [Kubernetes: Configure liveness, readiness and startup probes](https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/)
- [Google Cloud: Workload Identity Federation for GKE](https://cloud.google.com/kubernetes-engine/docs/how-to/workload-identity)
- [Artifact Registry: Configure access control](https://cloud.google.com/artifact-registry/docs/access-control)

## Conclusion

Automated deployment to Cloud Run and GKE requires a traceable chain from source commit to image and runtime. Cloud Build tests, builds, and pushes artifacts; the build service account deploys with least privilege; runtime identities are separated for applications. Cloud Run uses revisions and traffic management for gradual releases, while GKE uses Deployment rollouts, probes, and Kubernetes RBAC to govern workloads. Smoke tests, metrics, logs, traces, and rollback plans verify that releases truly work. Combining immutable artifacts, proper approvals, and post-deploy health checks allows teams to release frequently while keeping risk under control.

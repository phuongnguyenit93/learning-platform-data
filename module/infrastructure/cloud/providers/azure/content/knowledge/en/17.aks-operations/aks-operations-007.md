# Distributing AKS Applications with Helm

## 1. Why Does AKS Need an Application Packaging and Release Mechanism?

When a Java application runs on Azure Kubernetes Service (AKS), a container image alone is not enough. To run reliably, Kubernetes also needs a Deployment, Service, ConfigMap, Secret, ServiceAccount, Ingress, HorizontalPodAutoscaler, and possibly a PodDisruptionBudget or PersistentVolumeClaim.

If teams deploy these components as separate raw YAML files, they quickly run into recurring issues:

- Development, staging, and production environments each require different parameters.
- A single release must synchronize multiple Kubernetes resources.
- Changing an image tag or replica count requires editing several places.
- It is hard to see which release was installed, upgraded, or needs rolling back.
- Teams copy and paste YAML, creating near-duplicate files that are difficult to update consistently.
- CI/CD needs repeatable validation and deployment steps rather than manual ad-hoc commands.

**Helm** is a package manager for Kubernetes applications. Helm lets you bundle the required resources into a **chart**, customize configuration via **values**, render Kubernetes manifests from **templates**, and install/upgrade them as a tracked **release**.

In this module exploring the Microsoft Azure ecosystem, Helm connects AKS operations with **Azure Container Registry (ACR)**, Microsoft Entra ID, managed identities, networking, storage, monitoring, security, and cost control. Helm does not replace Kubernetes or AKS; it helps manage how applications are released onto the cluster.

### Learning Objectives

After this lesson, you will be able to:

1. Distinguish chart, template, values, repository, and release.
2. Understand how Helm interacts with the Kubernetes API on AKS.
3. Build a simple chart for a Java API containing a Deployment, Service, and HPA.
4. Use `helm lint`, `helm template`, and pre-deployment validation checks.
5. Install, upgrade, inspect history, and roll back releases in the right namespace.
6. Manage differences across dev/staging/prod without duplicating entire charts.
7. Connect container images in ACR to AKS with proper authentication.
8. Distribute Helm charts via an OCI registry when needed.
9. Control secrets, Kubernetes permissions, security contexts, and third-party chart risks.
10. Integrate Helm into CI/CD, GitOps, monitoring, and safe release workflows.

## 2. What Helm Is and What It Is Not

Helm is a **package manager for Kubernetes**. From a chart's templates and values, Helm renders manifests, submits them to the Kubernetes API, and tracks release history per Helm's release mechanics.

Helm helps you:

- Share a unified set of Kubernetes resource definitions across multiple environments.
- Parameterize configurable application settings.
- Manage install, upgrade, and rollback operations.
- Share charts as packaged archives or OCI artifacts.
- Run chart validations and test hooks.
- Automate deployments inside pipelines.

Helm **does not**:

- Provision an AKS cluster without external infrastructure tooling/design.
- Build Docker images or ensure images have been pushed to ACR.
- Automatically grant ACR pull rights, workload identity, or Kubernetes RBAC if the chart omits them or the environment is not configured properly.
- Guarantee the application is free of business bugs simply because Helm reports `deployed`.
- Back up or roll back database data.
- Install an ingress controller, certificate manager, or CRDs if an application chart assumes they already exist.
- Make an untrusted chart safe to install.

Think of Helm as the **packaging and release layer for Kubernetes resources**, while AKS manages the cluster and Kubernetes controllers create and reconcile Pods.

## 3. How Helm Works on AKS

~~~mermaid
flowchart LR
    DEV[Source + Dockerfile] --> BUILD[CI build/test]
    BUILD --> ACR[Azure Container Registry - image]
    CHART[Helm chart + values] --> RENDER[Helm renders templates]
    CI[Developer or CI/CD] --> RENDER
    RENDER --> API[AKS Kubernetes API]
    API --> DEP[Deployment / Service / HPA]
    DEP --> PODS[Pods pull image from ACR]
    ACR --> PODS
    API --> HISTORY[Helm release metadata]
    HISTORY --> ROLLBACK[History / Rollback]
~~~

Example deployment flow:

1. CI builds a Java API image and pushes it to ACR under a versioned tag/digest reference.
2. The development team maintains a chart describing the Deployment, Service, resources, and probes.
3. The pipeline selects the values corresponding to staging or production.
4. Helm renders manifests using the environment-specific parameters.
5. Helm submits those manifests to the Kubernetes API using the active identity.
6. Kubernetes creates or updates resources, and the scheduler places Pods onto nodes.
7. Nodes/kubelet pull images from ACR using the configured identity/authorization mechanism.
8. Helm stores release metadata and revisions to support history and rollback.

**Key point:** the permission of the caller running Helm to modify Kubernetes resources and the permission of the node to pull images from ACR are **two separate authentication paths**.

## 4. Chart, Release, Repository, Values, and Templates

| Concept | Meaning | Example |
|---|---|---|
| **Chart** | Package describing Kubernetes resources and metadata to deploy | `orders-api` chart version `0.1.0` |
| **Chart.yaml** | Declares chart name, version, description, dependencies, and metadata | `name: orders-api` |
| **values.yaml** | Default values passed into templates | `replicaCount: 2` |
| **Templates** | Go-template files used to generate manifests | `templates/deployment.yaml` |
| **Release** | A single installed instance of a chart, with a name and revision history | `orders-api` in namespace `orders-prod` |
| **Chart repository** | Distribution host for charts, either an HTTP Helm repo or an OCI registry | `oci://registry.example/helm` |
| **Image repository** | Location storing container images | `acrdemo.azurecr.io/apps/orders-api` |
| **Chart version** | Version of the Helm configuration package | `0.1.0` |
| **App version** | Application version advertised by the chart | `1.4.0` |
| **Release revision** | Counter of install/upgrade/rollback events recorded by Helm | `1, 2, 3...` |

### 4.1. Do Not Confuse Three Types of Versions

A system can simultaneously have:

~~~text
Helm chart version : 0.3.0
Application version: 1.4.2
Image digest       : sha256:<actual-digest>
Release revision   : 7
~~~

They serve distinct purposes:

- **Chart version** changes when chart definitions or packaging change.
- **App version** documents the application version but does not automatically force containers to run that image.
- **Image tag/digest** determines the exact image Kubernetes pulls.
- **Release revision** increments with each release event in Helm history.

A release can be upgraded solely because values changed, even if the chart version stays the same. Conversely, a new chart version does not guarantee Pods run a new image unless the image reference in config actually changes.

### 4.2. One Chart Can Be Installed Multiple Times

Example:

~~~text
Chart: orders-api version 0.3.0

Release: orders-dev     namespace: orders-dev
Release: orders-staging namespace: orders-staging
Release: orders-prod    namespace: orders-prod
~~~

Each release maintains independent state and values. **Release names are scoped per namespace**, though you should still avoid hardcoding fixed Kubernetes resource names that would collide across releases.

## 5. Basic Structure of a Helm Chart

Helm can scaffold a starter structure:

~~~bash
helm create orders-api
~~~

A chart is typically organized as follows:

~~~text
orders-api/
├── Chart.yaml
├── values.yaml
├── values.schema.json
├── .helmignore
├── charts/
└── templates/
    ├── _helpers.tpl
    ├── deployment.yaml
    ├── service.yaml
    ├── hpa.yaml
    ├── ingress.yaml
    ├── serviceaccount.yaml
    ├── NOTES.txt
    └── tests/
        └── test-connection.yaml
~~~

Not every chart needs every file. For example, an internal API may not need an Ingress; an app without autoscaling needs no HPA template.

- **Chart.yaml** defines the package.
- **values.yaml** holds defaults.
- **values.schema.json** validates types and constraints on values when provided.
- **templates/** generates Kubernetes resources.
- **_helpers.tpl** holds named templates for consistent names and labels.
- **charts/** can store packaged subchart dependencies.
- **.helmignore** excludes unnecessary files from the packaged chart.

In the hands-on sections below, the snippets illustrate **files you create in your own project**, not files to write into this learning material repository.

## 6. Writing Chart.yaml

Example metadata for the **orders-api** chart:

~~~yaml
apiVersion: v2
name: orders-api
description: Helm chart for the orders API on AKS
type: application
version: 0.1.0
appVersion: "1.4.0"
~~~

Meaning:

- **apiVersion: v2**: chart format used in modern Helm ecosystems.
- **name**: name of the chart.
- **type: application**: an application chart; `library` charts are used to share template functions.
- **version**: chart version, typically following Semantic Versioning.
- **appVersion**: informational application version treated as metadata by Helm.

**Do not assume `appVersion` automatically updates the `image` field in a Deployment.** It only affects generated manifests if a template explicitly references `.Chart.AppVersion` or corresponding values.

### 6.1. When Should You Bump the Chart Version?

Bump the chart version whenever the published chart contents change—for example, adding a Service, changing probes, updating security defaults, or editing templates. If only environment values change in production without releasing a new chart package, the release revision increments while the chart version can remain unchanged.

In CI/CD, record both the chart package/version and the exact image digest deployed for auditability.

## 7. Writing Reusable values.yaml

Example default values for a Java API listening on port 8080:

~~~yaml
replicaCount: 2

image:
  repository: acrdemoexample.azurecr.io/apps/orders-api
  tag: "1.4.0"
  digest: ""
  pullPolicy: IfNotPresent

service:
  type: ClusterIP
  port: 80
  targetPort: 8080

resources:
  requests:
    cpu: "100m"
    memory: "256Mi"
  limits:
    cpu: "500m"
    memory: "768Mi"

autoscaling:
  enabled: false
  minReplicas: 2
  maxReplicas: 5
  targetCPUUtilizationPercentage: 65

probes:
  readinessPath: /health/ready
  livenessPath: /health/live
  initialDelaySeconds: 10

fullnameOverride: ""
~~~

This is an instructional configuration. **`acrdemoexample.azurecr.io`** is only an illustrative hostname; replace it with a registry containing a real image and proper pull permissions.

Notes:

- **replicaCount** sets replicas when HPA is disabled.
- **image.repository** must be the full repository path for the image.
- **image.tag** is human-readable but can be overwritten if the registry is not locked.
- **image.digest** pins an exact immutable manifest when supplied.
- **service.type: ClusterIP** keeps the Service internal to the cluster.
- **resources.requests** helps the scheduler and HPA make accurate decisions.
- **resources.limits** must be grounded in measurements to avoid CPU throttling or OOM.
- **probes** must match real application endpoints.
- **autoscaling.enabled** controls whether the chart renders an HPA.

**`values.yaml` is not the place for production passwords, connection strings, or private keys.** Values pass through Helm rendering, release history, and diagnostic tools, risking exposure if misused.

## 8. Named Templates: Consistent Naming and Labels

The **templates/_helpers.tpl** file can define named templates:

~~~gotemplate
{{- define "orders-api.name" -}}
{{ .Chart.Name }}
{{- end -}}

{{- define "orders-api.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{ .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else -}}
{{ printf "%s-%s" .Release.Name .Chart.Name | trunc 63 | trimSuffix "-" }}
{{- end -}}
{{- end -}}

{{- define "orders-api.selectorLabels" -}}
app.kubernetes.io/name: {{ include "orders-api.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}
~~~

Named templates ensure uniform resource names and labels. The **`include`** function renders a named template so it can be piped into **`nindent`** (newline and indentation).

**`.Release.Name`** is the release name at install time; **`.Chart.Name`** is the chart name. Combining them prevents two releases in the same namespace from colliding on resource names when the chart is designed consistently.

### 8.1. Why Do Selector Labels Need to Be Stable?

Kubernetes Services select Pods via **selectors**. Deployments also use selectors to track their Pods. If an upgrade alters selectors so they no longer match Pod labels, the app can lose backends or Kubernetes will reject mutating immutable selector fields.

Design selector labels to stay stable—avoid embedding version numbers in selectors if every upgrade bumps that version.

## 9. Deployment Template for a Java API

The **templates/deployment.yaml** file:

~~~gotemplate
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {{ include "orders-api.fullname" . }}
  labels:
    {{- include "orders-api.selectorLabels" . | nindent 4 }}
spec:
  {{- if not .Values.autoscaling.enabled }}
  replicas: {{ .Values.replicaCount }}
  {{- end }}
  selector:
    matchLabels:
      {{- include "orders-api.selectorLabels" . | nindent 6 }}
  template:
    metadata:
      labels:
        {{- include "orders-api.selectorLabels" . | nindent 8 }}
    spec:
      securityContext:
        runAsNonRoot: true
        runAsUser: 10001
        seccompProfile:
          type: RuntimeDefault
      containers:
        - name: orders-api
          image: {{ if .Values.image.digest }}{{ printf "%s@%s" .Values.image.repository .Values.image.digest | quote }}{{ else }}{{ printf "%s:%s" .Values.image.repository (.Values.image.tag | default .Chart.AppVersion) | quote }}{{ end }}
          imagePullPolicy: {{ .Values.image.pullPolicy }}
          securityContext:
            allowPrivilegeEscalation: false
            capabilities:
              drop:
                - ALL
          ports:
            - name: http
              containerPort: {{ .Values.service.targetPort }}
          resources:
            {{- toYaml .Values.resources | nindent 12 }}
          readinessProbe:
            httpGet:
              path: {{ .Values.probes.readinessPath | quote }}
              port: http
            initialDelaySeconds: {{ .Values.probes.initialDelaySeconds }}
            periodSeconds: 10
          livenessProbe:
            httpGet:
              path: {{ .Values.probes.livenessPath | quote }}
              port: http
            initialDelaySeconds: {{ .Values.probes.initialDelaySeconds }}
            periodSeconds: 20
~~~

### 9.1. Explaining Helm Template Syntax

- **{{ ... }}**: Go template expressions evaluated by Helm before sending manifests to Kubernetes.
- **.Values.image.repository**: reads a value from the merged values configuration.
- **.Chart.AppVersion**: reads `appVersion` from `Chart.yaml`.
- **default**: supplies a fallback value when the input is empty in that context.
- **quote**: wraps a value in valid YAML string quotes.
- **toYaml**: serializes a values structure into YAML.
- **nindent**: inserts a newline and indents by the given spaces.
- **if**: conditionally emits configuration blocks.
- **include**: embeds a named template's output.

In this example, when **`image.digest`** is supplied, the Deployment uses **`repository@digest`**; otherwise it uses **`repository:tag`**. This enables digest-pinned production deployments without modifying the Deployment template.

### 9.2. Why Not Always Render `replicas`?

When HPA is enabled, HPA owns the replica count. If the chart repeatedly pushes a fixed number on every upgrade, it can cause unintended replica churn. Thus the template **only renders `replicas` when `autoscaling.enabled = false`**.

When toggling HPA on or off during upgrades, inspect live replica counts and transition steps to prevent unexpected scaling swings.

### 9.3. Container Runtime Privileges

The template sets a non-root UID and drops capabilities. Only enforce this if the container image was built to run under that UID/permission set; if Java needs to write to a restricted path, the container may fail to start.

In production, you can add `readOnlyRootFilesystem` with writable emptyDir volumes where needed, but never flip that flag without testing temp directories, logs, and caches first.

## 10. Service Template

The **templates/service.yaml** file:

~~~gotemplate
apiVersion: v1
kind: Service
metadata:
  name: {{ include "orders-api.fullname" . }}
  labels:
    {{- include "orders-api.selectorLabels" . | nindent 4 }}
spec:
  type: {{ .Values.service.type }}
  selector:
    {{- include "orders-api.selectorLabels" . | nindent 4 }}
  ports:
    - name: http
      port: {{ .Values.service.port }}
      targetPort: http
      protocol: TCP
~~~

The Service uses a selector matching the Pod labels and forwards traffic from Service port 80 to the container port named **`http`** (8080 in this example).

**`ClusterIP`** does not create a public endpoint. It is a sensible default before integrating an ingress controller or dedicated gateway architecture.

If the app requires a LoadBalancer or Ingress, explicitly configure network rules, TLS, and WAF rather than accidentally exposing ports to the Internet simply by switching values from `ClusterIP` to `LoadBalancer`.

## 11. Conditional HPA Template

The **templates/hpa.yaml** file:

~~~gotemplate
{{- if .Values.autoscaling.enabled }}
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: {{ include "orders-api.fullname" . }}
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: {{ include "orders-api.fullname" . }}
  minReplicas: {{ .Values.autoscaling.minReplicas }}
  maxReplicas: {{ .Values.autoscaling.maxReplicas }}
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: {{ .Values.autoscaling.targetCPUUtilizationPercentage }}
{{- end }}
~~~

### 11.1. What Prerequisites Does HPA Need?

- The cluster must provide a working metrics API / metrics source.
- Pods need realistic CPU requests to compute CPU utilization.
- Node pools need enough capacity or node autoscaling enabled.
- The workload must actually be safe to scale horizontally.
- Databases, queues, and downstream services must handle increased Pod concurrency.

**HPA adds Pods; Cluster Autoscaler adds Nodes** when eligible. Helm only creates the HPA resource; it does not guarantee autoscaling actually keeps up with traffic.

### 11.2. What If HPA Is Not Wanted?

Set **`autoscaling.enabled: false`**. The Deployment template then sets replicas from **`replicaCount`**. When turning HPA back on later, check replica transition behavior and min/max bounds.

## 12. Using values.schema.json to Catch Misconfigurations

Helm supports **`values.schema.json`** to validate constraints on values.

Example:

~~~json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "required": ["image", "service", "resources"],
  "properties": {
    "replicaCount": {
      "type": "integer",
      "minimum": 1
    },
    "image": {
      "type": "object",
      "required": ["repository"],
      "properties": {
        "repository": {
          "type": "string",
          "minLength": 1
        },
        "tag": {
          "type": "string"
        },
        "digest": {
          "type": "string"
        }
      }
    },
    "service": {
      "type": "object",
      "properties": {
        "port": {
          "type": "integer",
          "minimum": 1,
          "maximum": 65535
        }
      }
    },
    "resources": {
      "type": "object"
    }
  }
}
~~~

A solid schema catches mistakes like setting **`replicaCount`** to a string, omitting **`image.repository`**, or entering an out-of-range port.

However, a schema does not replace Kubernetes API validation, policy checks, image scanning, or integration tests. Cross-field constraints or complex business rules may require additional validation.

## 13. Rules for Writing Safe, Maintainable Templates

### 13.1. Use `required` When Needed

Example checking image repository:

~~~gotemplate
{{ required "image.repository must be provided" .Values.image.repository }}
~~~

If a chart lacks a mandatory value, rendering fails early with a clear error message.

### 13.2. Be Careful with Whitespace

**`{{-`** and **`-}}`** trim whitespace. Wrong indentation or overly aggressive newline trimming can produce invalid YAML.

Always run **`helm template`** and inspect the rendered output; do not review template source files alone, since Kubernetes receives the **post-render** manifests rather than raw Helm expressions.

### 13.3. Do Not Overuse Conditional Logic

A chart packed with hundreds of flags and tangled branches becomes harder to maintain than plain YAML. Keep options meaningful, and split charts or dependencies when components have independent lifecycles.

### 13.4. Keep Selectors Stable

Fields such as Deployment **`spec.selector`** are immutable. Do not vary selectors with `chartVersion` or `appVersion` expecting `helm upgrade` to smoothly mutate them.

### 13.5. Avoid Unnecessary Randomness or `lookup` Calls

Templates that generate random values or run **`lookup`** against live cluster state at render time make manifests non-reproducible and cause local renders, CI renders, and cluster deployments to diverge.

### 13.6. Never Hardcode Namespaces

Rely on the deployment-time namespace or **`.Release.Namespace`** when genuinely needed. Avoid hardcoding **`metadata.namespace: default`** inside every template, which silently ignores **`--namespace orders-prod`**.

## 14. Managing Configurations Across Dev, Staging, and Production

A single chart can serve multiple environments through values files.

~~~text
charts/orders-api/
├── Chart.yaml
├── values.yaml
├── values-dev.yaml
├── values-staging.yaml
├── values-prod.yaml
└── templates/
~~~

Example **`values-dev.yaml`**:

~~~yaml
replicaCount: 1

image:
  repository: acrdemoexample.azurecr.io/apps/orders-api
  tag: "1.4.0-dev"

resources:
  requests:
    cpu: "50m"
    memory: "128Mi"
  limits:
    cpu: "250m"
    memory: "512Mi"
~~~

Example **`values-prod.yaml`**:

~~~yaml
replicaCount: 3

image:
  repository: acrdemoexample.azurecr.io/apps/orders-api
  tag: "1.4.0"
  digest: "sha256:<actual-image-digest>"

resources:
  requests:
    cpu: "300m"
    memory: "512Mi"
  limits:
    cpu: "1000m"
    memory: "1536Mi"

autoscaling:
  enabled: true
  minReplicas: 3
  maxReplicas: 12
  targetCPUUtilizationPercentage: 65
~~~

In a lab, if you see a placeholder **`sha256:<...>`**, replace it with a real digest or leave `digest` empty, because Kubernetes cannot pull an image with a fake digest.

### 14.1. Values Precedence Order

Helm merges:

1. Defaults in **`values.yaml`**.
2. One or more files passed via **`--values / -f`** in order.
3. Explicit overrides passed via **`--set / --set-string`** and related flags.

Later values files override earlier ones per Helm's merge rules; structured types like lists are replaced rather than appended element-by-element.

Example:

~~~bash
helm template orders-api ./charts/orders-api \
  --namespace orders-prod \
  --values ./charts/orders-api/values.yaml \
  --values ./charts/orders-api/values-prod.yaml \
  --set-string image.tag=1.4.0
~~~

**Never pass passwords via `--set` on the command line**: values can end up in shell history, CI logs, or Helm release metadata.

### 14.2. Do Not Maintain Separate Charts per Environment

Every environment should run the **same template logic** and differ only on legitimate parameters. Manually editing a separate Deployment template in production destroys repeatability and auditability.

## 15. Validating Charts Before Deployment

A chart that renders cleanly is not guaranteed to run healthy Pods. Layer your checks.

### 15.1. Lint

~~~bash
helm lint ./charts/orders-api \
  --values ./charts/orders-api/values-dev.yaml
~~~

**`helm lint`** catches structural chart and template issues. It does not validate full runtime behavior.

### 15.2. Render Manifests

~~~bash
helm template orders-api ./charts/orders-api \
  --namespace orders-dev \
  --values ./charts/orders-api/values-dev.yaml
~~~

This outputs YAML for reviewers or CI to inspect without touching the cluster.

Verify:

- Deployment and Service names.
- Selector labels and Pod labels.
- Container image repository and tag/digest.
- Replicas or HPA settings.
- Ports, resources, and health probes.
- ServiceAccount and security context where used.
- Namespace fields and annotations.
- Environment variables and secret references.

### 15.3. Validate Against Kubernetes APIs or Schemas

Validate rendered manifests with Kubernetes schema validators or a staging cluster on the target API version. A chart rendering valid YAML can still reference a Kubernetes API removed in the target AKS version.

### 15.4. Policy and Security Checks

If your environment enforces Azure Policy, admission controllers, or Kubernetes Pod Security Admission, test against the same policies used in production. A chart should not rely on disabling cluster policies to deploy.

### 15.5. Keep Secrets Out of Debug Output

**`helm template`**, **`helm get values`**, **`helm get manifest`**, CI artifacts, and debug logs can expose sensitive values. Design secure secret delivery rather than treating Helm outputs as harmless artifacts.

## 16. Installing a Release for the First Time on AKS

Assume you have:

- A valid AKS cluster with kubeconfig pointing to the right context.
- An authorized namespace.
- Validated chart and values.
- An existing ACR image that nodes have permission to pull.
- Sufficient Kubernetes RBAC to create the declared resources.

Verify context:

~~~bash
kubectl config current-context
kubectl get nodes
~~~

Install into namespace **`orders-dev`**:

~~~bash
helm install orders-api ./charts/orders-api \
  --namespace orders-dev \
  --create-namespace \
  --values ./charts/orders-api/values-dev.yaml \
  --wait \
  --timeout 10m
~~~

Explanation:

- The first **`orders-api`** is the release name.
- **`./charts/orders-api`** is the chart path.
- **`--namespace orders-dev`** targets the release namespace.
- **`--create-namespace`** creates the namespace if needed and permitted.
- **`--values`** supplies environment configuration.
- **`--wait`** waits for eligible resources to become ready per Helm's readiness logic.
- **`--timeout`** caps the wait duration for the operation.

**Helm reporting success does not prove all business flows work.** Continue checking logs, readiness, database connectivity, and business endpoints.

### 16.1. Inspect the Release

~~~bash
helm list --namespace orders-dev

helm status orders-api --namespace orders-dev

kubectl get deployments,services,pods \
  --namespace orders-dev

kubectl rollout status deployment/orders-api-orders-api \
  --namespace orders-dev
~~~

The Deployment name in the last command reflects the `release-chart` naming helper. If the chart uses **`fullnameOverride`** or another name, use the actual name shown by **`kubectl get deployment`**.

If Pods are unhealthy, inspect events and logs instead of repeatedly re-running install.

## 17. Using `helm upgrade --install` in Pipelines

In automation, a pipeline may not know whether a release already exists. **`upgrade --install`** handles both:

- Release does not exist: performs a fresh install.
- Release already exists: performs an upgrade.

Example:

~~~bash
helm upgrade --install orders-api ./charts/orders-api \
  --namespace orders-dev \
  --create-namespace \
  --values ./charts/orders-api/values-dev.yaml \
  --wait \
  --atomic \
  --timeout 10m
~~~

**`--atomic`** instructs Helm to attempt rolling back the release per supported behavior if install/upgrade fails under tracked conditions. It implies waiting on relevant resources.

**This is not an application-wide ACID transaction.** `--atomic` does not roll back database migrations, undo external changes outside Kubernetes, delete files written to Blob Storage, or guarantee reversing every controller's side effects.

### 17.1. When Should You Avoid Infinite Automated Retries?

If install/upgrade fails due to admission policy, quotas, image pull errors, or invalid manifests, infinite retries only bloat logs and obscure the root cause. The pipeline should halt, preserve evidence, and alert owners to fix configuration.

### 17.2. Timeouts Must Account for Startup

Java apps may take noticeable time for JVM boot, cache warm-up, or database connections. A timeout that is too short marks healthy slow-starting deployments as failed, while an overly long timeout delays failure detection. Measure startup realistically and align with SLOs.

## 18. Upgrading Images and Configuration

Suppose CI just pushed image **`1.4.1`** and updated values. Instead of patching the Deployment directly with `kubectl` behind Helm's back, upgrade via the release:

~~~bash
helm upgrade orders-api ./charts/orders-api \
  --namespace orders-dev \
  --values ./charts/orders-api/values-dev.yaml \
  --set-string image.tag=1.4.1 \
  --wait \
  --atomic \
  --timeout 10m
~~~

For production, pin the **`image.digest`** recorded by the pipeline:

~~~bash
helm upgrade orders-api ./charts/orders-api \
  --namespace orders-prod \
  --values ./charts/orders-api/values-prod.yaml \
  --set-string image.digest="sha256:<actual-digest>" \
  --wait \
  --atomic \
  --timeout 10m
~~~

**Digest strings shown here are placeholders.** Substitute a valid digest from ACR before running.

### 18.1. Why Deploy by Digest?

Mutable tags like **`1.4.1`** can be overwritten to point at a different image if registry or pipeline controls slip. A digest identifies an exact manifest, ensuring staging and production run the exact tested artifact.

### 18.2. Do Not Rebuild Images Between Staging and Production

A second build from the same source can pull a newer base image or transitive dependency. The reliable flow is: **build once → push to ACR → record digest → test in staging → promote the exact same digest to production**.

### 18.3. Data Compatibility During Rolling Updates

During a rolling update, old and new versions coexist. Design database migrations to be backward-compatible across that overlap. Rolling back manifests via Helm does not automatically revert altered schemas or mutated data.

## 19. Release History and Rollback

Helm records release revisions in its configured cluster storage backend. Inspect them with:

~~~bash
helm history orders-api --namespace orders-dev
~~~

Check status:

~~~bash
helm status orders-api --namespace orders-dev
~~~

Check recorded values:

~~~bash
helm get values orders-api \
  --namespace orders-dev \
  --all
~~~

Check manifests recorded by Helm:

~~~bash
helm get manifest orders-api --namespace orders-dev
~~~

**Warning:** commands inspecting values/manifests can expose sensitive contents if insecure secrets were placed in charts. Run and store outputs only in authorized environments.

### 19.1. Rolling Back to a Specific Revision

Suppose revision 3 is the last known-good version:

~~~bash
helm rollback orders-api 3 \
  --namespace orders-dev \
  --wait \
  --timeout 10m
~~~

Then verify:

~~~bash
helm history orders-api --namespace orders-dev
kubectl get pods --namespace orders-dev
~~~

**Rollback creates a new release revision**; it does not decrement the revision counter back to 3. It restores manifest configuration from an earlier revision rather than rewinding time across the cluster, database, or external systems.

### 19.2. What Does Rollback Not Undo?

- Incompatible database schema migrations already applied.
- Modified PersistentVolumes or deleted data.
- Rotated external secrets.
- Changed external API contracts.
- Old images deleted from the registry.
- Resources edited manually outside Helm or contested by another controller.

A sound release plan retains prior images in ACR, uses backward-compatible migrations, and rehearses rollbacks.

## 20. Common Release Statuses

When investigating Helm, you may encounter statuses such as:

| Status | General Meaning | Action Needed |
|---|---|---|
| **deployed** | Revision installed/upgraded successfully according to Helm | Verify live application and health |
| **failed** | A release operation failed | Check error details, events, and resources |
| **pending-install** | Install is currently in progress | Check progress and timeout |
| **pending-upgrade** | Upgrade is currently in progress | Check whether a job is still running or stuck |
| **pending-rollback** | Rollback is in progress | Inspect history and resource state |
| **superseded** | Older revision replaced by a newer one | Useful for historical comparison |
| **uninstalled** | Release was removed while keeping history | Verify whether any leftover resources remain |

Do not manually edit Helm release Secrets/metadata to "unlock" a pending status without understanding the consequences. First check whether another pipeline is concurrently running against the same release, inspect timeouts, and read Kubernetes events.

**Each release should have one coordinated deployment stream**, preventing two pipelines from upgrading the same release/namespace simultaneously.

## 21. Helm Release Metadata and Secret Exposure Risks

Under common default settings, Helm stores release state inside Kubernetes Secrets in the release namespace. Release records can include charts, values, and manifests needed for history and rollbacks.

Therefore:

- Never put production passwords in `values.yaml`.
- Never pass secrets via **`--set`** where they leak into CI logs.
- Never assume Kubernetes Secrets are protected solely because data is Base64-encoded; encryption at rest and RBAC must be configured explicitly.
- Restrict read permissions on Secrets and Helm release metadata per namespace.
- Guard outputs of **`helm get values`**, **`helm get manifest`**, **`helm template`**, and pipeline artifacts.
- Ensure Helm hooks and Jobs never print secrets to logs.

### 21.1. Safer Secret Patterns

Consider:

- **Microsoft Entra Workload ID** so Pods obtain tokens directly for authorized Azure services.
- **Azure Key Vault** with supported integrations such as the Secrets Store CSI Driver.
- External Secrets Operator if approved by the organization with managed CRDs/controllers.
- Kubernetes Secrets provisioned and managed by a dedicated system with proper RBAC/encryption.

Charts can reference an **existing secret name** instead of embedding secret values in templates or values. For example, a Deployment may use:

~~~yaml
env:
  - name: DATABASE_PASSWORD
    valueFrom:
      secretKeyRef:
        name: orders-db-credentials
        key: password
~~~

The snippet above is only an example assuming the Secret already exists. In production, prefer workload identity and passwordless auth wherever data services support it.

## 22. Helm Charts and Kubernetes RBAC

Helm uses the active kubeconfig/context and identity's Kubernetes API permissions. If a chart creates Deployments, Services, Roles, ServiceAccounts, HPAs, or CRDs, the deploying principal must have permissions on those resource types and scopes.

### 22.1. Per-Environment Permissions

A CI service principal or pipeline identity should only be allowed to modify required resources in the target namespace. Do not grant **`cluster-admin`** by default just to make every Helm install succeed.

### 22.2. Risks from Third-Party Charts

An untrusted chart can declare:

- Overbroad `ClusterRole`/`ClusterRoleBinding` grants.
- Privileged containers and `hostPath` mounts.
- ServiceAccounts with powerful tokens/permissions.
- Helm hooks launching Jobs with sensitive commands.
- Cluster-scoped CRDs and controllers.
- Images from unverified registries.

Before installing any third-party chart, audit its provenance, version, license, rendered manifests, RBAC, security context, images, and network requirements.

### 22.3. Namespaces Are Not Absolute Isolation Boundaries

A chart installed in namespace **`orders-prod`** can still create cluster-scoped resources if its templates declare them and the deploying identity has permission. Thus, namespaces are an organizational and RBAC boundary, not an absolute security sandbox.

## 23. ACR Image Authentication and Helm Are Separate Concerns

Two distinct flows exist:

1. **Helm accessing the chart package**, which may live in Git, an HTTP Helm repository, or an OCI registry.
2. **AKS nodes pulling container images**, typically from ACR via kubelet/configured identity.

Even when Helm installs a Deployment cleanly, Pods can hit **`ImagePullBackOff`** if nodes lack ACR permissions or network connectivity.

### 23.1. Using Private ACR for Images

Verify:

- Image reference specifies the exact registry/repository/tag/digest.
- AKS kubelet identity or pull auth mechanism holds **pull** rights under the ACR authorization model.
- Private endpoints, firewalls, DNS, and egress allow image pulls.
- Image architecture/OS matches the target node pool.
- The image digest still exists and was not purged by retention policies.

Example image block in values:

~~~yaml
image:
  repository: acrdemoexample.azurecr.io/apps/orders-api
  tag: "1.4.0"
  digest: ""
~~~

Once CI produces a real digest, deploy using the digest instead of the tag per the Deployment design in Section 9.

### 23.2. Workload Identity Does Not Automatically Grant Image Pull Rights

Workload identity is typically used by code running **inside the Pod** to access Azure Storage, Key Vault, or other APIs. Image pulling occurs during Pod creation and relies on the kubelet/node identity or supported registry authentication. Do not confuse the two identity layers.

## 24. Distributing Helm Charts via OCI Registries and ACR

Charts can also be packaged as artifacts and distributed through an OCI registry such as Azure Container Registry. This is distinct from storing **container images** in ACR repositories, even though both leverage OCI standards.

### 24.1. Packaging a Chart

After validating the chart:

~~~bash
helm lint ./charts/orders-api

helm package ./charts/orders-api \
  --destination ./dist
~~~

Output resembles:

~~~text
dist/orders-api-0.1.0.tgz
~~~

Package name and version come from `Chart.yaml`.

### 24.2. Logging Into an OCI Registry

With ACR and Azure CLI, you can authenticate using a token from your signed-in Azure identity where supported. Bash example:

~~~bash
ACR_NAME="acrdemoexample"

ACR_LOGIN_SERVER="$(az acr show \
  --name "$ACR_NAME" \
  --query loginServer \
  --output tsv)"

az acr login \
  --name "$ACR_NAME" \
  --expose-token \
  --query accessToken \
  --output tsv |
helm registry login "$ACR_LOGIN_SERVER" \
  --username 00000000-0000-0000-0000-000000000000 \
  --password-stdin
~~~

**Never print tokens to logs.** In CI runners or non-interactive pipelines, use an ACR- and Helm-supported login method with appropriate push/pull roles. The zeroed UUID username in the example is a special token-flow username used with Azure CLI access tokens, not a personal admin account.

### 24.3. Pushing the Chart Package

~~~bash
helm push ./dist/orders-api-0.1.0.tgz \
  oci://acrdemoexample.azurecr.io/helm
~~~

With OCI syntax, the push target is the **repository prefix**; Helm derives the chart name and version from the package. The chart lands at the logical reference:

~~~text
oci://acrdemoexample.azurecr.io/helm/orders-api
version: 0.1.0
~~~

### 24.4. Pulling or Installing an OCI Chart

~~~bash
helm pull \
  oci://acrdemoexample.azurecr.io/helm/orders-api \
  --version 0.1.0
~~~

Install directly from the OCI registry if the client has permissions:

~~~bash
helm upgrade --install orders-api \
  oci://acrdemoexample.azurecr.io/helm/orders-api \
  --version 0.1.0 \
  --namespace orders-dev \
  --create-namespace \
  --values ./values-dev.yaml \
  --wait \
  --atomic
~~~

Note that **`--version 0.1.0`** here is the **chart version**, not the container image tag. Values can still specify image `1.4.0` or a separate digest.

### 24.5. Do Not Confuse an OCI Chart with an OCI Docker Image

ACR can store both:

~~~text
Helm chart:
  oci://acrdemoexample.azurecr.io/helm/orders-api --version 0.1.0

Container image:
  acrdemoexample.azurecr.io/apps/orders-api:1.4.0
~~~

**`helm pull`/`helm push`** operate on chart packages; **`docker pull`/`docker push`** operate on container images. AKS nodes do not run a Helm chart as a container.

## 25. Chart Dependencies and Shared Libraries

A chart can declare dependencies in **`Chart.yaml`**, for example:

~~~yaml
apiVersion: v2
name: orders-api
type: application
version: 0.1.0
dependencies:
  - name: redis
    version: "18.x.x"
    repository: "https://charts.example.invalid"
    condition: redis.enabled
~~~

**This is a syntax illustration only.** The URL **`charts.example.invalid`** is not a real repository; replace it with an organization-approved chart source and valid version constraints for your requirements.

Common commands:

~~~bash
helm dependency update ./charts/orders-api

helm dependency build ./charts/orders-api
~~~

Distinguish:

- **`dependency update`** resolves versions against declarations and updates the lock file and downloaded dependencies per Helm behavior.
- **`dependency build`** reconstructs dependencies from the lock file when present, improving repeatability.

Commit **`Chart.lock`** in application repositories to lock dependency versions, while still auditing package sources, digests, and supply-chain trust.

### 25.1. Should You Bundle a Database Inside the API Chart?

An "all-in-one" chart bundling the API, database, cache, and message broker may feel convenient in demos yet creates production hazards:

- Databases have separate upgrade and backup lifecycles from APIs.
- Uninstalling a release can impact stateful resources.
- Data can be lost if storage/PVC retention policies are misunderstood.
- Security boundaries and operational ownership blur together.

For Azure production, strongly consider **managed databases/caches** and pass connection configs to the API rather than running self-managed databases inside application charts without a specific Kubernetes requirement.

### 25.2. Library Charts

Helm supports **library charts** for shared templates and helpers. They help standardize names, labels, and policies, but avoid turning a library chart into an opaque abstraction layer where operators can no longer read the final rendered manifests.

## 26. Helm Hooks, Jobs, and Execution Order

Helm supports **hooks** to run resources at specific release lifecycle points, such as pre/post install or upgrade.

Example annotations on a Kubernetes Job:

~~~yaml
metadata:
  annotations:
    "helm.sh/hook": pre-upgrade
    "helm.sh/hook-weight": "0"
    "helm.sh/hook-delete-policy": before-hook-creation,hook-succeeded
~~~

### 26.1. When Are Hooks Useful?

- A pre-upgrade Job verifying prerequisites.
- A controlled configuration synchronization step.
- An idempotent, backward-compatible migration Job.
- A post-deploy smoke-test Job checking connectivity.

### 26.2. Risks of Hooks

- Hooks can create side effects outside Helm's rollback reach.
- A failed database migration can leave data in an intermediate state.
- Hook resources and deletion histories follow separate rules and are not always managed like standard release resources.
- Hooks may re-execute on pipeline retries.
- A hung `pre-upgrade` hook can stall or fail the entire release.

**Never rely on `--atomic` as a safe rollback for database migration hooks.** Design migrations independently with backups, backward compatibility, and dedicated runbooks.

## 27. Helm Test: Post-Install Verification

Helm provides **`helm test`** via resources annotated with the `test` hook. Example **`templates/tests/test-connection.yaml`**:

~~~gotemplate
apiVersion: v1
kind: Pod
metadata:
  name: {{ include "orders-api.fullname" . }}-test
  annotations:
    "helm.sh/hook": test
    "helm.sh/hook-delete-policy": before-hook-creation,hook-succeeded
spec:
  restartPolicy: Never
  containers:
    - name: wget
      image: busybox:1.36
      command:
        - sh
        - -c
        - >-
          wget -qO- http://{{ include "orders-api.fullname" . }}:{{ .Values.service.port }}/health/ready
~~~

After installing:

~~~bash
helm test orders-api --namespace orders-dev --logs
~~~

The test Pod probes the Service inside the release namespace. It succeeds only if the application exposes the expected endpoint and the cluster can pull the test image.

**An HTTP 200 check does not prove all business logic works.** Run real integration tests against databases, queues, authorization, and critical user flows—ideally in staging before promoting.

### 27.1. Do Not Use Unvetted Test Images

Even test hooks run containers inside your cluster. Pin image tags/digests, set resource requests/limits, and lock down permissions just like any workload when moving from lab to production.

## 28. Helm and Kubernetes Reconciliation: Who Owns Resources?

Helm submits Kubernetes resources; thereafter, **Kubernetes controllers** reconcile the state of Pods, Services, and related objects.

Example:

1. Helm installs a Deployment with `replicas: 3`.
2. Kubernetes creates a ReplicaSet and three Pods.
3. One Pod crashes.
4. Kubernetes recreates or restarts that Pod.
5. Helm does not need to re-run just to heal a crashed Pod.

However, if someone runs **`kubectl edit deployment`** to change an image outside Helm:

- Cluster state diverges from manifests tracked by Helm.
- The next `helm upgrade` may overwrite or trigger unexpected diffs.
- Git/chart values no longer reflect live reality.

This is **configuration drift**. Establish a clear source of truth: charts + values in Git, automated pipelines/GitOps, and restricted ad-hoc write tools.

### 28.1. Avoid Two Systems Managing the Same Resource

If a resource is managed by Chart A while also modified by GitOps or Chart B, two controllers will fight. Define clear ownership, scope, and release rules for every resource.

### 28.2. Resources Created Outside the Chart

Some resources belong under separate governance, such as:

- AKS clusters, VNets, node pools, and ACR via IaC/AKS APIs.
- Ingress controllers or cert-manager via platform charts.
- Databases and Key Vault via Azure resources.
- Namespaces, baseline RBAC, and policies owned by the platform team.
- Applications/APIs owned by application charts.

There is no need to cram every piece of infrastructure into one Helm chart.

## 29. Helm and GitOps

The Helm CLI is commonly used in CI/CD as **push deployment**: a pipeline holds credentials and runs **`helm upgrade`**.

An alternative model is **GitOps**, where an in-cluster controller such as Flux or Argo CD (when deployed and supported) watches Git/OCI sources and reconciles resources onto the cluster.

~~~mermaid
flowchart TD
    COMMIT[Git commit / release approval] --> CONFIG[Chart version + values + image digest]
    CONFIG --> CONTROLLER[GitOps controller on AKS]
    CONTROLLER --> API[Kubernetes API]
    API --> DEPLOY[Deployment / Service / HPA]
    DEPLOY --> OBS[Logs, metrics, and health]
~~~

### 29.1. Value of GitOps

- Git preserves full change history and peer review.
- Multiple environments map cleanly to structured directories/branches.
- Avoids granting direct cluster credentials to external CI runners when using a pull model.
- Detects or remediates configuration drift per policy.

### 29.2. Points to Clarify

- Which controller is authorized to manage the release/resources?
- How are secrets decrypted or injected securely?
- How are chart versions and image digests pinned?
- Are manual approvals required before production?
- For rollback, do teams revert a Git commit, update a version, or run manual Helm commands?
- If both GitOps and Helm CLI interact, which system is the source of truth?

**Do not mix two parallel deployment flows on the same release** without strict ownership rules, because a manual Helm rollback will be overwritten by the GitOps controller syncing back to Git.

## 30. Designing Production Releases on AKS

A quality-gated pipeline flow:

~~~mermaid
flowchart TD
    CODE[Source code] --> BUILD[Build and test application]
    BUILD --> IMAGE[Push image to ACR]
    IMAGE --> DIGEST[Capture image digest]
    CHART[Helm chart + pinned dependencies] --> LINT[Lint / Render / Policy checks]
    DIGEST --> LINT
    LINT --> STAGE[Deploy to staging]
    STAGE --> TEST[Smoke / Integration / E2E tests]
    TEST --> APPROVE{Approved?}
    APPROVE -->|Yes| PROD[Deploy to production]
    APPROVE -->|No| STOP[Halt, fix issues]
    PROD --> WATCH[Observe rollout / SLOs]
    WATCH --> ROLLBACK[Rollback if thresholds breached]
~~~

### 30.1. What Should a Release Record Capture?

| Information | Example |
|---|---|
| Git commit | Application source commit |
| Pipeline run | Build ID |
| Registry/image repository | `acrdemoexample.azurecr.io/apps/orders-api` |
| Image digest | `sha256:...` |
| Helm chart version | `0.1.0` |
| Values revision | Git commit or file hash |
| Target cluster/namespace | `aks-prod` / `orders-prod` |
| Release name/revision | `orders-api` / `7` |
| Approval | Change ticket or release reviewer |

Do not treat **`helm history`** as your sole audit trail. Release history in Helm can be capped or deleted on uninstall, whereas pipelines and Git should retain immutable release records.

### 30.2. Release Gates

Commonly required gates:

- Unit and integration tests pass.
- Container vulnerability scan and policy checks pass.
- Chart lint, template render, and schema validation pass.
- Staging E2E tests pass.
- Authorized production approval recorded.
- Rollout health, error rates, and latency remain within thresholds.
- Previous images/charts remain available for rollback.

## 31. Monitoring After a `helm upgrade`

Immediately after Helm reports success, inspect:

~~~bash
helm status orders-api -n orders-prod
kubectl get deployments,pods,services -n orders-prod
kubectl rollout status deployment/orders-api-orders-api -n orders-prod
kubectl get events -n orders-prod --sort-by=.metadata.creationTimestamp
~~~

If a Pod fails:

~~~bash
kubectl describe pod <pod-name> -n orders-prod
kubectl logs <pod-name> -n orders-prod
~~~

Signals to watch:

- **`ImagePullBackOff`:** image name/tag/digest, ACR auth/networking.
- **`CrashLoopBackOff`:** app startup, secrets/config, dependencies, OOM.
- **`Pending`:** node capacity, resource requests, taints, volumes.
- **`Readiness probe failed`:** wrong endpoint/port or app not ready yet.
- **Rising error rate:** business logic regression even when Pods are Ready.
- **Abnormal HPA behavior:** mis-sized CPU requests/metrics or database bottleneck.

Combine Azure Monitor Container Insights, logs, metrics, dashboards, and alerts per your organization's observability stack. Exact monitoring component names and setup vary by AKS configuration.

## 32. Helm Rollback and Real-World Failure Scenarios

### Scenario A — Image Does Not Exist

**Symptom:** Helm apply succeeds, yet Pods stay unready with `ImagePullBackOff`.

Investigation steps:

1. Check the exact image reference on the Deployment.
2. Cross-check the tag/digest in ACR.
3. Verify pull permissions and egress/DNS.
4. If the image reference is wrong, fix values and upgrade with the valid digest.
5. If needed, roll back to the previous revision while keeping the old image intact.

### Scenario B — Service Returns 503 After Upgrade

Possible causes include failing readiness probes, mismatched selectors, crashing Pods, or database incompatibility. Check EndpointSlices/Service selectors, Pod logs, and metrics. Rolling back app code only helps if dependencies and schemas remain backward-compatible.

### Scenario C — Helm `pending-upgrade`

Check whether another pipeline is running, an earlier operation is still executing, or a run timed out. Never manually edit release storage Secrets without confirming cluster state and supported recovery procedures.

### Scenario D — Helm Rollback Succeeds Yet Application Still Fails

Helm restored previous manifests, but the database schema changed, cache entries mutated, or external files were deleted. Follow application recovery runbooks, inspect data integrity, and validate external dependencies.

### Scenario E — Resources Remain After Uninstall

Some resources have special lifecycles, such as CRDs or resources protected by annotations/policies; hook/controller-created resources may also outlive a release. **`helm uninstall` does not guarantee removing everything associated**, especially persistent data or external resources.

## 33. Uninstalling and Cleaning Up Resources Safely

For lab-only releases:

~~~bash
helm uninstall orders-api \
  --namespace orders-dev
~~~

Verify:

~~~bash
helm list --namespace orders-dev
kubectl get all --namespace orders-dev
~~~

**Run only for lab releases authorized for deletion.** If the app has PVCs, databases, CRDs, shared Secrets, or hook/controller-managed resources, review retention and backups before uninstalling.

Never delete an entire namespace or resource group assuming it only contains that single Helm release without verifying ownership first.

### 33.1. Does `helm uninstall` Delete ACR Images?

No. Helm manages the release's Kubernetes resources; it does not delete container images stored in Azure Container Registry.

### 33.2. Does `helm uninstall` Delete Databases?

That depends on whether the database was deployed as a chart-managed Kubernetes resource (and its storage reclaim policy) versus an independent Azure managed database. In production, never rely on `helm uninstall` for database lifecycle management.

### 33.3. Cleaning Up Chart Caches and Credentials

Local chart caches and registry credentials on developer laptops or CI runners must also follow organizational policies, especially if `helm registry login` persisted credentials.

## 34. Common Mistakes When Using Helm on AKS

- **Treating a chart like a Docker image:** a chart packages Kubernetes configs; an image is the runnable container artifact.
- **Confusing chart version and appVersion:** makes releases hard to audit.
- **Using `latest` in production:** the same tag can resolve to different images over time.
- **Editing Deployments manually after install:** creates configuration drift that gets overwritten on upgrade.
- **Hardcoding namespaces or resource names:** causes collisions across releases.
- **Putting passwords in `values.yaml`:** leaks secrets into Git, Helm metadata, and logs.
- **Running only `helm lint` and deploying straight away:** skips manifest rendering, API compatibility, and policy checks.
- **Treating `--atomic` as a database backup:** rollback only reverts Helm-managed Kubernetes resources.
- **Skipping readiness probes:** Helm may misjudge readiness or miss broken rollouts.
- **Enabling HPA while forcing fixed `replicas` on every upgrade:** causes unnecessary capacity swings.
- **Installing third-party charts with `cluster-admin`:** needlessly expands the blast radius.
- **Neglecting hooks:** hook side effects and Jobs can linger or re-run unexpectedly.
- **Forgetting ACR pull permissions:** Pods fail to pull images even after Helm succeeds.
- **Leaving chart dependencies unpinned:** fresh builds pull unexpected dependency versions.
- **Running both GitOps and `helm upgrade` against the same release:** causes state conflicts.
- **Purging old charts/releases/images too early:** leaves nothing to roll back to.
- **Ignoring logs/compute cost:** replicas scale up without budget alerts.

## 35. Hands-On Lab: Packaging and Releasing an API to AKS

**Context:** your development team has a Java API named `orders-api` with its container image pushed to ACR. Your task is to build a Helm chart, deploy to a test namespace, upgrade, and perform a controlled rollback.

### Part A — Preparation

1. An authorized lab AKS cluster with kubeconfig set to the right context.
2. Kubernetes permissions to create namespaces/Deployments/Services/HPAs as required.
3. A runnable Java API image in an accessible registry; if using private ACR, configure pull permissions beforehand.
4. The API exposes `/health/live` and `/health/ready`, or adjust values/templates to match.
5. An isolated lab environment and budget for required pods/nodes.
6. Compatible Helm CLI and `kubectl` installed.

### Part B — Create the Chart

1. Run **`helm create orders-api`** in your lab project folder.
2. Keep needed files and remove unused starter templates.
3. Update `Chart.yaml` and `values.yaml` per Sections 6 and 7.
4. Author `_helpers.tpl`, `deployment.yaml`, `service.yaml`, and `hpa.yaml` per Sections 8–11.
5. Add `values-dev.yaml` and `values-prod.yaml` per environment requirements.
6. Optionally add `values.schema.json`.

### Part C — Pre-Install Validation

1. Run **`helm lint`**.
2. Run **`helm template`** with `values-dev`.
3. Verify Deployment selectors match Pod labels and Service selectors.
4. Check image references, replicas, requests/limits, probes, and HPA.
5. Verify Kubernetes API versions match your AKS cluster.
6. Ensure zero production secrets appear in rendered manifests.

### Part D — Install

1. Confirm Kubernetes context.
2. Run **`helm upgrade --install`** into namespace **`orders-dev`**.
3. Check status with **`helm status`**, **`helm list`**, and **`kubectl get pods`**.
4. Inspect readiness and logs if the app does not start cleanly.
5. Test via `kubectl port-forward` to the Service or your lab ingress.
6. Record the chart version, image version/digest, and release revision.

### Part E — Upgrade

1. Build a test `1.4.1` image or change a non-sensitive config value.
2. Run **`helm template`** to preview the manifest diff.
3. Execute **`helm upgrade`**.
4. Watch the rolling rollout and new Pods.
5. Verify health, error rates, and functionality.
6. Record the new release revision.

### Part F — Rollback

1. Run **`helm history`** to view earlier revisions.
2. Roll back to the last known-good revision.
3. Verify the Deployment image/config returns to the expected version.
4. Check database state and external side effects if used in the lab.
5. Document outcomes and rollback limitations.

### Part G — Package Chart and Test OCI

If you have an ACR chart repository and permissions:

1. Run **`helm package`** to build the `.tgz` archive.
2. Log in to the registry using an appropriate token flow.
3. Push the chart to the OCI repository.
4. Pull/install via the OCI reference with an **explicit chart version**.
5. Reconcile the running chart version and image digest.

### Part H — Cleanup

1. Verify the release belongs strictly to your lab.
2. Check stateful resources, Secrets, and hook Jobs if any exist.
3. Uninstall the test release if authorized.
4. Delete your isolated namespace/resources only after confirming no shared dependencies remain.
5. Audit costs if the lab provisioned new nodes, Load Balancers, or other Azure services.

**If you do not yet have an AKS cluster or valid ACR image**, you can still complete chart authoring, linting, and template rendering offline. However, never claim install, image pull, or live rollback were verified if you did not execute them on a real cluster.

## 36. Production Helm Deployment Checklist

- [ ] Chart has explicit versioning and accurate metadata.
- [ ] Images are built, tested, scanned, and pinned by digest or immutable tags.
- [ ] Chart dependencies are locked and sources vetted.
- [ ] Per-environment values are cleanly structured without duplicating charts.
- [ ] No secrets appear in charts, values, CI logs, or Helm history.
- [ ] Deployment identity holds only least-privilege Kubernetes permissions.
- [ ] ACR pull identity and networking are verified on AKS nodes.
- [ ] Templates use consistent, stable names, labels, and selectors.
- [ ] Resource requests/limits, probes, and replicas/HPA align with SLOs.
- [ ] Ingress, TLS, NetworkPolicies, and RBAC are reviewed by the platform team.
- [ ] `helm lint`, `template`, schema, and policy checks pass.
- [ ] Runtime, health, and business flows verified in staging.
- [ ] Rolling updates have sufficient capacity, PDBs, and graceful shutdown.
- [ ] Database migrations are backward-compatible and backed up.
- [ ] `helm history`, rollback plan, and prior images/charts are preserved.
- [ ] Hooks, CRDs, and shared resources have clear owners and lifecycles.
- [ ] CI/CD or GitOps serves as the single source of truth for releases.
- [ ] Alerts exist for Pod failures, rollouts, HPA, latency, and error rates.
- [ ] Budgets cover AKS node pools, networking, storage, and monitoring.
- [ ] Runbooks exist for `ImagePullBackOff`, `pending-upgrade`, and failed rollbacks.

## 37. Self-Check Questions

1. What do chart, release, and repository mean in Helm?
2. How do chart version, `appVersion`, image tag/digest, and release revision differ?
3. Why can the same chart be installed multiple times in different namespaces?
4. What is the purpose of `_helpers.tpl` and `selectorLabels`?
5. If `values.yaml` changes without modifying `Chart.yaml`, can the Helm release revision still increment?
6. How does **`helm template`** differ from **`helm install`**?
7. Why should you run `helm lint` and render manifests before deploying to AKS?
8. When HPA is enabled, why shouldn't you force fixed `replicas` on every upgrade?
9. What pipeline scenario does **`helm upgrade --install`** solve?
10. What do **`--wait`** and **`--atomic`** provide, and what are their limits?
11. Can `helm rollback` undo a database migration or deleted Blob files?
12. Why shouldn't production passwords be stored in Helm values?
13. When Pods hit `ImagePullBackOff` after a successful Helm install, which layers should you inspect?
14. When should you push an OCI Helm chart to ACR, and how does it differ from a container image?
15. Why does pinning an image digest ensure staging and production run the exact same artifact?
16. Helm hooks are useful, but what side-effect risks do they introduce?
17. How can a third-party chart grant itself cluster-wide privileges?
18. Why shouldn't both the Helm CLI and a GitOps controller manage the same release without clear ownership?
19. When uninstalling a chart, which resources might still remain?
20. If a release shows status `deployed` yet the API returns 503, how would you investigate?

## 38. Summary

**Helm packages, configures, distributes, and manages application lifecycles on AKS.** A **chart** bundles metadata, templates, and values; a **release** is an installed instance tracked with revision history. Core commands include **`helm lint`**, **`helm template`**, **`helm install`**, **`helm upgrade`**, **`helm history`**, **`helm rollback`**, **`helm test`**, and **`helm uninstall`**.

In the Azure ecosystem, pair Helm with **AKS**, **ACR**, **Microsoft Entra ID/managed identities**, **Key Vault**, **Azure Monitor**, and controlled **CI/CD or GitOps** workflows. Focus on rendering clean manifests, pinning chart/image versions, enforcing least privilege, keeping secrets out of release metadata, designing proper health/rollout/rollback paths, and remembering that Helm rollback **does not replace backups or data recovery**.

A reliable workflow is **build once → push image to ACR → capture digest → lint/render/chart checks → deploy to staging → test → release to production → monitor → execute planned rollback when needed**. Helm makes this repeatable, while real operational quality depends on application architecture, security, data integrity, and live verification on AKS.

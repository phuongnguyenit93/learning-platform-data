# Resource Naming, Labeling, and Deployment Provenance

A serverless application can create many resources: functions, HTTP services, queues, topics, workflows, buckets, databases, service accounts, revisions, and deployment configurations. As resource counts grow, arbitrary naming makes searching, access control, cost allocation, and incident troubleshooting difficult.

A good convention should answer three questions:

1. **What is this resource and which system does it belong to?** Resource names must be short, stable, and recognizable.
2. **Which environment, team, or purpose does the resource serve?** Labels, tags, and annotations provide metadata for filtering, governance, and cost allocation.
3. **Which source code and build is this resource running?** Provenance links a specific source commit, build, artifact, configuration, and deployment.

For Java serverless, consistent conventions must apply to both cloud resources and application metadata. When an invocation fails, operators need to trace from logs and execution IDs back to the function/service, revision, image digest, build, and commit that produced that artifact.

## 1. Distinguishing names, labels, tags, and annotations

These concepts are related but do not replace one another.

| Component | Purpose | Example |
|---|---|---|
| Resource name | Identifies the resource within an API or platform | `orders-api-prod` |
| Label | Structured metadata for classifying, filtering, or selecting resources | `environment=production` |
| Tag | Metadata attached to cloud resources; typically used for classification, policies, or cost allocation | `team=commerce-platform` |
| Annotation | Supplementary metadata, typically for tooling or operational details | git commit, build URL |
| Runtime attribute | Metadata attached to running processes/services for logs, metrics, and traces | `service.version=2.4.1` |
| Release provenance | Evidence linking source, build, artifact, and deployment | commit SHA + image digest + release ID |

Resource names are typically part of an identifier or URL and carry dedicated constraints. Labels/tags can usually change without changing the resource's identity. Annotations store richer metadata, though they are not necessarily usable as selectors or filters across every platform.

For example, in Kubernetes, labels can be used in selectors to match Pods belonging to a Service or Deployment. Annotations hold extra metadata and are not used for standard selectors. Across cloud providers, the naming and capabilities of tags/labels vary by service.

Do not pick one term and assume every platform implements it identically. Distinguish each purpose and verify the schema, limits, and filtering capabilities of the service you use.

## 2. Building a resource naming convention

A common convention combines stable, meaningful segments:

~~~text
<organization>-<system>-<component>-<environment>-<region>
~~~

Examples:

~~~text
acme-orders-api-prod-asia-southeast1
acme-orders-worker-prod-asia-southeast1
acme-orders-events-prod-asia-southeast1
acme-orders-reconcile-job-prod-asia-southeast1
~~~

Not every resource needs all segments. If the project/account or namespace already represents the environment and region, names can be shorter:

~~~text
orders-api
orders-worker
orders-events
orders-reconcile
~~~

The goal is for operators to recognize a resource without guessing. Avoid stuffing all governance metadata into names; labels/tags are better suited for owners, cost centers, data classifications, and management tools.

### 2.1. Practical rules

- Use lowercase letters and hyphens for names requiring portability across platforms.
- Use standardized abbreviations from a shared catalog; avoid inventing variants for the same concept.
- Keep names short; avoid embedding long descriptions or free-form prose.
- Never put passwords, tokens, personal emails, customer IDs, or sensitive data into names.
- Never use individual people's names for long-lived ownership; use team or service account names.
- Never embed code versions into stable service names when the platform already manages revisions/versions separately.
- Never use temporary names like `test2`, `final-new`, or `latest-prod`.
- Verify character rules, length limits, uniqueness scope, and renameability for each resource type.

Some services require globally unique names; others require uniqueness only within a project, account, namespace, or region. Some services disallow renaming after creation. When global uniqueness is required, include a standardized short organization/project identifier.

### 2.2. Avoid encoding too much information into names

Resource names often outlive team structures or cost allocation models. If a name embeds a department name, cost center, or person's name, organizational changes may force recreating resources or living with outdated names.

Let names express the system and role, while volatile information lives in labels/tags. For example, a service can stay named `orders-api` while ownership changes from `team-commerce` to `team-commerce-platform` via a metadata update.

Region can be included in a name when distinguishing same-role resources across regions. If the region is already explicit in the resource path or project, omit repeating it if doing so makes names overly long.

## 3. Naming by serverless resource type

A single system can contain multiple components. Choose consistent nouns and suffixes so operators can tell functions, APIs, workers, and event channels apart.

| Resource type | Name pattern | Example |
|---|---|---|
| HTTP service | system-api-env | orders-api-prod |
| Event consumer | system-worker-env | orders-worker-prod |
| Single-action business function | system-action-env | orders-charge-prod |
| Queue | system-purpose-queue-env | orders-payment-queue-prod |
| Topic/event stream | system-events-env | orders-events-prod |
| Workflow | system-process-workflow-env | orders-fulfillment-workflow-prod |
| Batch job | system-purpose-job-env | orders-reconcile-job-prod |
| Storage bucket | org-system-purpose-env-region | acme-orders-archive-prod-asia-southeast1 |
| Service account | system-component-runtime | orders-worker-runtime |
| Secret reference | system-purpose-env | orders-payment-provider-prod |

These examples are logical templates. Specific platforms have distinct resource types or naming rules. For example, bucket names may require global uniqueness; function names may face length limits; queues may receive platform-appended suffixes. Standardize names at the application layer while respecting each resource API's constraints.

### 3.1. Distinguishing service names from revision names

A service name typically represents a stable application. A revision or version represents a specific deployment.

Example:

~~~text
Service: orders-api-prod
Revision: orders-api-prod-00042
Image: registry.example.com/orders-api@sha256:...
Version: 2.4.1
Commit: 8f31a2c...
~~~

There is no need to create a brand-new service per release if the platform supports revisions or aliases. Keep endpoints stable and use revisions/aliases for traffic shifting, canaries, and rollbacks.

On AWS Lambda, keep the function name stable and use versions and aliases for releases. On Cloud Run or Knative, a stable service gets new revisions on each deploy. On Kubernetes, a Deployment manages ReplicaSets/Pods by template. APIs and terms differ, yet the principle holds: logical service names should not change on every build.

## 4. Environments and deployment scope

Environment names should use a standardized vocabulary, for example:

~~~text
dev
test
staging
prod
~~~

Never mix variants like `production`, `production1`, `live`, `prd`, and `prod` if they denote the same environment. Define a canonical dictionary so pipelines, dashboards, and policies filter consistently.

Environments can be separated using:

- Separate cloud projects or accounts.
- Separate Kubernetes namespaces.
- Separate regions or clusters.
- Resource names with environment suffixes.
- Environment labels/tags.
- Separate IAM boundaries and secret stores.

Do not rely on names to enforce security boundaries. Access control must be enforced via IAM, RBAC, network policies, and resource policies. An `environment=prod` label does not stop a dev workload from accessing production if IAM still permits it.

### 4.1. Promoting across environments

A sound release process builds an artifact once and promotes that same artifact through test, staging, and production. Each environment supplies its own configuration and secrets.

Example:

~~~text
Source commit: 8f31a2c
Build ID: build-20261117-042
Artifact digest: sha256:abc123...
Deploy to test: orders-api-test
Deploy to staging: orders-api-staging
Deploy to prod: orders-api-prod
~~~

Rebuilding separate artifacts per environment makes it hard to prove production runs the exact tested binary. Environment differences belong in deployment configuration—do not alter bytecode or container images without a clear reason.

### 4.2. Ephemeral environments

Preview environments for pull requests can derive names from the PR number or a short ID:

~~~text
orders-api-pr-184
orders-worker-pr-184
~~~

Do not place raw branch names into resource names because branches can contain invalid characters, exceed length limits, or reveal internal information. Use labels to store the PR number, commit, and cleanup expiration.

Ephemeral resources need an owner, expiry/TTL, and cleanup mechanism. Otherwise, preview environments linger after PRs close and continue incurring costs or holding unneeded data.

## 5. Labels and tags for resource governance

Labels/tags should answer operational questions:

- Which system does the resource belong to?
- Which team is accountable?
- Which cost center should bear the cost?
- Which environment does the resource belong to?
- What is the data classification level?
- Was the resource managed via Terraform, CDK, or another tool?
- Is this a production, preview, or batch workload?

A baseline key-value set:

~~~text
system=orders
component=worker
environment=production
team=commerce-platform
cost-center=cc-042
managed-by=terraform
data-classification=internal
~~~

Not every platform allows the same keys or character sets. You may need to normalize to lowercase keys and short values for compatibility across cloud services.

### 5.1. Common Kubernetes label set

Kubernetes recommends standard labels under `app.kubernetes.io`. Example:

~~~yaml
metadata:
  labels:
    app.kubernetes.io/name: orders
    app.kubernetes.io/instance: orders-prod
    app.kubernetes.io/component: worker
    app.kubernetes.io/part-of: commerce-platform
    app.kubernetes.io/managed-by: kustomize
    environment: production
    team: commerce-platform
    cost-center: cc-042
~~~

Common meanings:

- `app.kubernetes.io/name`: application name.
- `app.kubernetes.io/instance`: a deployed instance of the application.
- `app.kubernetes.io/component`: role such as `api`, `worker`, or `scheduler`.
- `app.kubernetes.io/part-of`: larger system the component belongs to.
- `app.kubernetes.io/managed-by`: tool managing the resource.

These labels help tools and operators understand relationships between resources. When using labels in selectors, keep values stable and consistent across Pod templates, Services, and controllers. Never place per-build changing values into selectors.

### 5.2. Cloud provider tags

Cloud providers implement tags/labels differently:

- Google Cloud supports labels on many resource types for filtering and cost allocation on supported services.
- AWS provides resource tags; certain services and billing features require separate activation or configuration to use tags for cost allocation.
- Azure provides tags across many resources; inheritance scope and policy support depend on the resource type.

Never assume every resource supports tags or that every tag automatically appears in billing reports. Check service docs, key/value limits, and account cost-allocation settings.

Labeling policies should be enforced in CI/IaC or admission policies. Production resources missing owner, environment, or cost-center tags can trigger warnings or be blocked from deployment per organizational policy.

## 6. Annotations for deployment metadata

In Kubernetes, annotations fit supplementary information that controllers or operators need to read without using it for Pod selection.

Example:

~~~yaml
metadata:
  annotations:
    deployment.example.com/source-revision: "8f31a2c"
    deployment.example.com/build-id: "build-20261117-042"
    deployment.example.com/release-id: "release-2026-11-17.3"
    deployment.example.com/image-digest: "sha256:abc123..."
    deployment.example.com/pipeline: "ci-main"
~~~

Annotations can hold documentation URLs, commits, build IDs, or deployment details. Avoid putting credentials, private keys, access tokens, or sensitive data in annotations because metadata is broadly readable by users and controllers.

Never use annotations to store business state. Annotations are metadata about the resource; business state belongs in databases, queues, or workflow state stores.

For cloud resources lacking an annotation equivalent, use tags/labels for short metadata and release manifests or deployment systems for detailed records.

## 7. OCI image labels and artifact identification

Container images can carry OCI-standard metadata. Common fields include title, description, source repository, version, revision, created, and license.

Dockerfile example:

~~~dockerfile
FROM eclipse-temurin:21-jre
WORKDIR /app

COPY target/orders-worker.jar /app/app.jar

LABEL org.opencontainers.image.title="orders-worker"
LABEL org.opencontainers.image.description="Java event consumer for orders"
LABEL org.opencontainers.image.version="2.4.1"
LABEL org.opencontainers.image.revision="8f31a2c"
LABEL org.opencontainers.image.source="https://git.example.com/commerce/orders"
LABEL org.opencontainers.image.created="2026-11-17T10:00:00Z"

ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

These labels help registry scanners and operational tools identify images. They do not replace image digests. A tag like `2.4.1` can be overwritten if the registry permits it; a digest uniquely identifies the exact image contents.

Production deployments should reference digests when immutability is required:

~~~text
registry.example.com/commerce/orders-worker@sha256:abc123...
~~~

Using digests pins the exact deployed binary. If tags are used, ensure registry policies block overwrites or pipelines verify which digest a tag resolves to.

## 8. Traceability from source code to runtime

Traceability connects multiple links in a chain:

~~~mermaid
flowchart LR
    A["Source repository"] --> B["Commit SHA"]
    B --> C["CI build"]
    C --> D["Artifact / image digest"]
    D --> E["Release manifest"]
    E --> F["Deployment"]
    F --> G["Cloud resource / revision"]
    G --> H["Invocation / log / trace"]
~~~

Each link needs a queryable identifier:

| Stage | Identifiers to record |
|---|---|
| Source | Repository, commit SHA, branch, or release tag |
| Build | Build ID, pipeline run ID, builder identity, timestamp |
| Artifact | Package version, OCI image digest, SBOM reference |
| Release | Release ID, target environment, config revision |
| Deployment | Deployment ID, actor/service account, timestamp, outcome |
| Runtime | Service/function name, revision/version, region, instance ID |
| Request/event | Request ID, trace ID, event ID, execution ID, correlation ID |

Not every identifier belongs in a label. Commit SHAs or build IDs have high cardinality; they belong in annotations, release records, logs, or deployment metadata rather than metric labels attached to every time series.

### 8.1. Release manifest

A release manifest can record the deployed artifact and configuration:

~~~json
{
  "service": "orders-worker",
  "environment": "production",
  "releaseId": "release-2026-11-17.3",
  "source": {
    "repository": "commerce/orders",
    "commit": "8f31a2c"
  },
  "build": {
    "id": "build-20261117-042",
    "pipeline": "ci-main"
  },
  "artifact": {
    "image": "registry.example.com/commerce/orders-worker",
    "digest": "sha256:abc123..."
  },
  "configuration": {
    "revision": "config-17",
    "secretReferences": [
      "orders/payment-provider"
    ]
  },
  "deployment": {
    "id": "deploy-20261117-003",
    "region": "asia-southeast1"
  }
}
~~~

This is an example structure. Never record secret values in the manifest; store only secret names or version references if traceability is needed. Also avoid recording credentials usable for accessing pipelines or cloud accounts.

Store release manifests in a versioned location with appropriate access controls. During incident investigation, look up the deploy ID from runtime metadata and open the matching manifest to inspect the commit, image digest, and config revision.

### 8.2. SBOM and build provenance

A Software Bill of Materials (SBOM) lists software components inside an artifact. Build provenance records which source, builder, and process produced the artifact.

These two records support:

- Investigating libraries affected by newly disclosed vulnerabilities.
- Verifying artifacts were built from approved repositories and commits.
- Comparing dependencies between two releases.
- Proving a deployed binary is the exact artifact produced by CI.
- Supporting policies that verify signatures and origin before deployment.

Bind SBOM/provenance to the artifact digest. Binding only to a mutable tag creates a weaker link to the specific binary.

## 9. Configuring Java to identify services and deployments

Java applications should separate build metadata from runtime metadata:

- **Build metadata:** application version, commit SHA, build ID, and build timestamp.
- **Deployment metadata:** environment, region, release ID, and config revision.
- **Instance metadata:** instance/pod ID and runtime details supplied by the platform.
- **Request metadata:** request ID, trace ID, event ID, and correlation ID.

Non-sensitive values can be passed via environment variables. Do not create environment-specific variable names like `DB_PASSWORD_PROD` and `DB_PASSWORD_STAGING`. Keep the same configuration key and supply the appropriate value or secret reference per deployment environment.

Java 17 example:

~~~java
public record RuntimeIdentity(
        String serviceName,
        String environment,
        String serviceVersion,
        String commit,
        String buildId,
        String releaseId,
        String region,
        String instanceId) {

    public static RuntimeIdentity fromEnvironment() {
        return new RuntimeIdentity(
                value("APP_NAME", "orders-worker"),
                value("APP_ENV", "unknown"),
                value("APP_VERSION", "unknown"),
                value("GIT_COMMIT", "unknown"),
                value("BUILD_ID", "unknown"),
                value("RELEASE_ID", "unknown"),
                value("CLOUD_REGION", "unknown"),
                value("INSTANCE_ID", "unknown")
        );
    }

    private static String value(String key, String fallback) {
        String value = System.getenv(key);
        return value == null || value.isBlank() ? fallback : value;
    }
}
~~~

Runtime identity keeps logs enriched with consistent metadata. Fallback `"unknown"` values help in local development, while production can strictly require `APP_NAME`, `APP_ENV`, `APP_VERSION`, and `RELEASE_ID` at startup to catch missing configuration.

Never place secrets in `RuntimeIdentity`. Secrets must be read from a secret manager or mounted/injected via platform mechanisms, only where needed, and never serialized into logs.

### 9.1. Spring Boot build information

Spring Boot can generate build information via its Maven/Gradle plugin and expose it through the Actuator Info endpoint when configured. This is useful for inspecting application version/build metadata. However, the info endpoint should not be exposed publicly without controls, as it can reveal commits, dependencies, or deployment details.

Build metadata packaged in the JAR reflects build time. Environment, region, and release ID reflect deploy time. Do not mix the two, since the same image can be deployed across multiple environments.

## 10. Structured logging and correlation IDs

Logs should identify which service, revision, and request occurred where. In serverless, invocations can run across different instances, so you cannot rely on thread names or local files to stitch events together.

A structured log record can include:

~~~json
{
  "timestamp": "2026-11-17T13:20:00Z",
  "severity": "INFO",
  "service.name": "orders-worker",
  "service.version": "2.4.1",
  "deployment.environment.name": "production",
  "deployment.id": "deploy-20261117-003",
  "cloud.region": "asia-southeast1",
  "service.instance.id": "instance-7c91",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "span_id": "00f067aa0ba902b7",
  "correlation_id": "order-1042",
  "event_id": "evt-91f2",
  "message": "Order event processed"
}
~~~

Exact field names depend on your logging backend and OpenTelemetry semantic conventions. Use a consistent schema across services to simplify log queries.

Distinguish between:

- **Request ID:** identifies a single HTTP request or invocation at one layer.
- **Trace ID:** links spans across a distributed trace.
- **Span ID:** identifies a single operation segment within a trace.
- **Event ID:** identifies an event from its source.
- **Correlation ID:** links multiple requests, events, or workflows belonging to the same business process.
- **Execution ID:** identifies a single workflow or batch execution.

Do not use these IDs interchangeably. A single order can span multiple requests, events, and workflow executions while sharing one business correlation ID.

### 10.1. Metadata in OpenTelemetry

An OpenTelemetry `Resource` describes the service/process emitting telemetry. Common attributes include:

~~~text
service.name=orders-worker
service.version=2.4.1
deployment.environment.name=production
cloud.region=asia-southeast1
service.instance.id=instance-7c91
~~~

Resource attributes should be attached once when initializing the telemetry provider. Trace/span attributes add per-request or per-operation context. Never put customer IDs, order IDs, or trace IDs into high-cardinality metric labels; those belong in logs and traces with appropriate access controls.

When the platform already provides trace context via headers or message metadata, propagate that context instead of starting a disconnected new trace. For events, propagate trace context using standards supported by producers and consumers.

## 11. Tracing events and workflows

In asynchronous processing, preserve identifiers end-to-end from producer to consumer:

~~~text
HTTP request
  request_id = req-123
  correlation_id = order-1042
        |
        v
Order service
  event source = /orders/api
  event id = evt-91f2
        |
        v
Broker / queue
        |
        v
Payment worker
  event_id = evt-91f2
  correlation_id = order-1042
        |
        v
Workflow
  execution_id = exec-7a21
  correlation_id = order-1042
~~~

During retries, event IDs and idempotency keys must stay stable. Do not generate a new event ID each time the same logical event is resent. If a new event arises from a business state transition, issue a new ID and link it via the correlation ID.

Logs should contain enough identifiers to trace the entire processing chain without logging entire payloads. For sensitive data, log controlled reference IDs instead of raw contents.

## 12. Using labels for cost allocation and ownership

Labels/tags enable aggregating costs by application, environment, team, or cost center where supported by billing services. A convention could be:

~~~text
system=orders
environment=production
team=commerce-platform
cost-center=cc-042
component=worker
managed-by=terraform
~~~

For reliable cost allocation:

1. Standardize keys/values and catalogs of teams, environments, and cost centers.
2. Apply metadata to all supported resources.
3. Enable cost allocation / tag activation features if required by your cloud provider.
4. Audit resources missing labels or carrying invalid labels.
5. Allocate shared resource costs using documented rules.
6. Monitor unallocated costs and follow up with owners.
7. Never use labels with continuously changing values.

Some costs cannot be attributed directly to a single service, such as shared network egress, cluster nodes, or shared brokers. Allocate them by request count, CPU time, message count, or an agreed ratio. Document the methodology so teams understand the numbers.

### 12.1. Cardinality and metadata limits

Never put per-request changing values into labels/tags:

- `request_id`
- `trace_id`
- `user_id`
- `order_id`
- `timestamp`
- `message_id`
- arbitrary exception text

These values create high cardinality, inflate metric storage costs, or exceed platform label limits. Use logs/traces for per-request detail; labels/tags should hold only a small, stable set of values.

## 13. Managing configuration and secrets per environment

Resource names and labels do not replace runtime configuration. A Java application can run the same image across multiple environments with different configs.

Example configuration variables:

~~~text
APP_NAME=orders-worker
APP_ENV=production
APP_VERSION=2.4.1
GIT_COMMIT=8f31a2c
BUILD_ID=build-20261117-042
RELEASE_ID=release-2026-11-17.3
CLOUD_REGION=asia-southeast1
LOG_LEVEL=INFO
PAYMENT_PROVIDER_SECRET_REF=orders/payment-provider
~~~

These variables are non-sensitive metadata/configuration or secret references. Never put actual secret values into committed `.env` files, image layers, labels, annotations, or command lines that may be persisted in history.

Distinguish between:

- Non-sensitive config: environment variables, config files, or config services.
- Secrets: Secret Manager, cloud secret stores, or protected Kubernetes Secrets.
- Resource metadata: labels/tags/annotations.
- Build metadata: version, commit, and build ID.
- Runtime telemetry: service/resource attributes and trace context.

When configuring secrets by version, record the secret name or version reference in the deployment record. When a secret rotates, you must be able to tell which version workloads use without logging secret contents.

## 14. Enforcing conventions via CI/CD and IaC

Conventions only help when enforced consistently. Add validation to your pipeline:

- Validate resource names against regexes and service limits.
- Verify environments belong to the allowed list.
- Require owner/team, system, and cost-center metadata.
- Verify images are pinned by digest or immutable tags per policy.
- Verify deployment records contain commit and build IDs.
- Block secrets in labels, annotations, Dockerfiles, or logs.
- Verify service accounts and IAM roles obey least privilege.
- Verify ephemeral resources carry expiry/owner metadata.
- Verify selector labels are not unintentionally altered.

Example simple CI policy requiring a metadata set:

~~~yaml
requiredLabels:
  - system
  - environment
  - team
  - cost-center
  - managed-by

allowedEnvironments:
  - dev
  - test
  - staging
  - prod
~~~

This is an illustrative policy, not a tool-specific schema. Enforce it via scripts, policy engines, Terraform validation, Kubernetes admission policies, or platform rules.

IaC should generate resources and metadata from a single standardized variable source. Avoid copy-pasting names across files, which easily introduces mismatches. Use shared modules or templates for similarly structured services while keeping logical names clear per resource.

## 15. Tracing incidents from runtime back to source

When a Java function fails, the traceability workflow should follow this chain:

1. Extract the request ID, trace ID, event ID, or workflow execution ID from the alert/log.
2. Identify the service name, environment, region, and revision/version.
3. Find the corresponding deployment ID or release ID.
4. Open the release manifest to retrieve the image digest, build ID, and commit.
5. Inspect the pipeline run and artifact provenance.
6. Check the config revision and secret references/versions without logging secret values.
7. Compare the current revision with the previous revision to isolate what changed.
8. Check dependencies, IAM, and resource labels to locate the accountable owner.

An incident can stem from code, config, secret rotation, IAM policies, or infrastructure changes. Recording only the application version without the config revision and deployment ID makes it hard to tell new code apart from new configuration.

Rollbacks also need traceability. Reverting to an older image does not automatically revert environment variables, secret versions, or database schemas. Release records should capture enough metadata to know what must roll back alongside the artifact.

## 16. Common mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Every team invents its own naming | Hard to search and automate | Adopt a shared naming convention and glossary |
| Cramming all metadata into resource names | Long, brittle, hard-to-change names | Put owner/environment/cost-center in labels |
| Putting commit SHAs into metric labels | Cardinality explosion | Use annotations, logs, or release records |
| Using `latest` in production | Impossible to know exact running binary | Pin image digests or immutable tags |
| Omitting deployment IDs | Hard to locate the offending deploy | Write release/deployment manifests |
| Using labels as security boundaries | Risk of misconfigured access | Enforce IAM/RBAC/resource policies |
| Putting secrets in annotations or logs | Credential leakage | Store secrets in a secret manager |
| Rebuilding artifacts per environment | Cannot prove the tested artifact shipped | Build once, promote the same digest |
| Missing owner and cost center | Costs are hard to attribute | Require labels/tags via CI policy |
| Using request ID as an event idempotency key | Retries can cause duplicate actions | Use stable event IDs or business keys |

## 17. Deployment checklist

Before promoting a Java serverless resource to production, verify:

1. Resource names follow conventions and obey service limits.
2. Environment and region are represented consistently.
3. Labels/tags include system, component, owner/team, and cost center.
4. Annotations hold only supplementary metadata and zero secrets.
5. Kubernetes selector labels are stable and consistent if used.
6. Images are identified by digest or immutable tags.
7. OCI metadata includes accurate source, version, and revision fields.
8. Build ID, commit SHA, and artifact provenance are recorded.
9. Deployment ID, release ID, and config revision are queryable.
10. Runtime logs include service name/version/environment and correlation IDs.
11. Trace context propagates across HTTP/events/workflows.
12. No high-cardinality IDs are placed in metric labels.
13. Secrets are referenced from a secret manager with least privilege.
14. CI/IaC validates required naming, labels, and metadata.
15. Ephemeral resources have owners and expirations.
16. Alerts can be traced back to deployments and source commits.

## 18. Self-check questions

- How does a resource name differ in purpose from a label or tag?
- When should a Kubernetes annotation be used instead of a label?
- Why should a stable service name be separated from revision/version?
- Why does an environment label not replace an IAM boundary?
- How does an OCI image digest differ from an image tag?
- How does build metadata differ from deployment metadata?
- How do you trace from a log record back to the commit that built the image?
- How do request ID, trace ID, event ID, and correlation ID differ?
- Why should trace IDs or order IDs never be placed in metric labels?
- How do labels support cost allocation and what additional configuration is required?
- Why build an artifact once and promote the exact same artifact across environments?
- What information should a release manifest contain for incident investigation?

Naming, labeling, and deployment provenance are core parts of serverless operational design. Resource names must be stable and recognizable; labels/tags support classification and cost allocation; annotations and release provenance link runtime back to source and artifacts. When Java services emit logs with consistent metadata and pipelines record image digests alongside deployment records, operators can locate the right owner, identify the running version, and trace back the exact change behind an incident.

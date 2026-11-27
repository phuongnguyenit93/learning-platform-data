# Defining Inputs: Artifacts, Configuration, and Target Environments

Automated deployment is only reliable when the pipeline knows precisely **which artifact will be deployed, which configuration accompanies it, and which resources will receive that release**. If any of these three inputs is ambiguous, the pipeline may deploy the wrong image, apply another environment's configuration, or send changes to the wrong cluster.

A deployment request must be described using identifiable and verifiable inputs. Artifacts should be referenced by digest or immutable version; configuration needs a version, scope, and schema; and the target environment must be identified by account, region, cluster, namespace, or corresponding resources. Secrets are referenced through a secret management system and granted by workload identity, without embedding secret values in the deployment configuration package.

## 1. Three Input Groups of a Deployment

A deployment typically has three main input groups:

| Group | Question to Answer | Examples |
|---|---|---|
| Artifact | Which exact deliverable will run? | Container image digest, package version, binary checksum |
| Configuration | Which settings will the deliverable run with? | Config bundle version, Helm values, feature flags |
| Target environment | Where is the deliverable deployed? | Environment, cloud account, region, cluster, namespace |

These three groups are closely related but have different lifecycles. Artifacts are produced during the build process and should remain unchanged when promoted across environments. Configuration typically varies by environment and must be versioned separately. The target defines where deployment occurs and the permissions the pipeline needs.

Beyond these three main groups, a deployment request usually carries metadata and evidence:

- Source code commit SHA.
- Pipeline run ID and build ID.
- Artifact digest and provenance.
- Configuration version and checksum.
- Deployment strategy and rollout parameters.
- Initiating user or workflow.
- Approval record if the environment requires approval.

This metadata helps identify which inputs a deployment used and supports later investigation or rollback.

## 2. Identifying Immutable Artifacts

An artifact is the deliverable produced by the build process: container image, JAR, WAR, package, binary, static bundle, or deployment package. The pipeline needs to identify the exact artifact to be deployed, not just its human-readable name.

An artifact reference should contain:

- Repository or package registry.
- Deliverable name.
- Version or tag for human lookup.
- Digest or checksum to identify content.
- Platform/architecture if the artifact has multiple variants.
- Source code: repository and commit SHA.
- Build run ID and provenance if available.

Example:

~~~yaml
artifact:
  type: container
  repository: registry.example.com/payments/api
  version: "2.8.1"
  digest: "sha256:0123456789abcdef..."
  platform: linux/amd64
  source:
    repository: example/payments
    commit: "a1b2c3d4"
  build:
    runId: "8421"
~~~

The digest in the example is an illustrative value. In an actual deployment, the pipeline must retrieve the digest returned by the registry or build system and verify that the artifact can be fetched by that digest.

### 2.1. Why Tags Are Not Enough

Tags such as **latest**, **stable**, or **2.8.1** are easy to read, but they can be moved to point to different content. If two deployments use the same tag at two different times, they may receive two different artifacts.

For container images, a digest-based reference helps identify the content:

~~~text
registry.example.com/payments/api@sha256:...
~~~

For packages or binary files, an immutable version can be combined with a checksum stored in the release manifest. You should not assume that a filename or version string by itself proves the content has not changed.

A key principle is **build once, promote the same artifact**. The artifact tested in staging must be the artifact deployed to production. If you rebuild from the same source when going to production, the toolchain, dependencies, or build timing may produce a different deliverable.

### 2.2. Verifying Origin and Integrity

Before deploying, the pipeline should verify:

- The artifact exists in an allowed registry.
- The digest matches the value recorded after the build.
- Signatures or provenance are valid if required by policy.
- The artifact was produced from a trusted repository, commit, and workflow.
- Scan results and quality gates are tied to the exact digest.
- The artifact is compatible with the target runtime, architecture, and platform.

An artifact should not be deployed just because it has the right name. An image could be replaced, pulled from an untrusted registry, or fail to be the deliverable that passed testing.

## 3. Identifying Configuration Accompanying the Artifact

Configuration controls how the application behaves in an environment. For example:

- Dependent service endpoints.
- Database or schema names.
- Worker counts, timeouts, and connection limits.
- Log levels and sampling.
- Feature flags.
- Queue, topic, or bucket names.
- Resource requests/limits.
- Ingress, routes, and network policies.

Configuration should be managed separately from the artifact so the same image can run across multiple environments. However, configuration must have clear identifiers so you know which version is used with which artifact.

Example of a configuration reference:

~~~yaml
configuration:
  name: payments-api
  environment: staging
  version: "2026.11.18.3"
  source:
    repository: example/platform-config
    commit: "d4e5f6a7"
  checksum: "sha256:abcdef0123456789..."
~~~

You should not pass only a branch name like **main** as the configuration version. Branch contents can change; pin the commit, immutable tag, or config bundle version so the deployment can be reproduced.

### 3.1. Separating Common and Environment-Specific Configuration

Configuration can be divided into layers:

| Layer | Examples | Management Approach |
|---|---|---|
| Default | Log format, metric names, safe default values | Alongside application code or shared config |
| Service-level | Worker count, retry policy, timeout | Config repository or config bundle |
| Environment-specific | Staging endpoints, region, replica count | Environment-specific configuration |
| Runtime override | Feature flags, controlled operational parameters | Config service or control plane |
| Secret reference | Secret name, version, or resource ID | Secret manager and identity policy |

Environment-specific configuration must be reviewed and have a change history. Avoid letting someone edit values directly in the production UI without an audit trail or control process.

### 3.2. Validating Configuration Schema and Values

Configuration must match the application version. For example, a new version may require additional configuration fields or rename a property. Deploying a new artifact with old configuration may prevent the application from starting or cause incorrect behavior.

You should verify:

- Configuration has valid format and schema.
- All required fields are present.
- Data types and value ranges are valid.
- Endpoints belong to the expected environment.
- Feature flags do not accidentally enable unready features.
- The config version is compatible with the artifact version.
- No plaintext secrets are included.
- The checksum or version matches the approved config.

You can add `schemaVersion` or `minApplicationVersion` fields to describe compatibility. If a configuration change may break backward compatibility, deploy in the appropriate order or use separate config versions per release.

## 4. Distinguishing Configuration from Secrets

A deployment configuration may need information indicating where to retrieve secrets, but it should not contain secret values.

Safer reference example:

~~~yaml
secretReferences:
  - name: DATABASE_PASSWORD
    provider: aws-secrets-manager
    resource: app/staging/payments/database
    version: current
  - name: PAYMENT_API_TOKEN
    provider: vault
    resource: kv/data/staging/payments/provider
    version: "7"
~~~

The resource names and versions in the example are illustrative only. Workload identity or job identity must have permission to read the corresponding secret. Aliases like `current` may point to a new version after rotation; if you need to reproduce a deployment accurately, record the actual version resolved by the secret manager. If the pipeline needs a secret to perform a deployment operation, it should retrieve that secret only in an authorized job and only for the required duration.

Do not put passwords, tokens, private keys, or connection strings containing credentials into config repositories, artifacts, public Helm values, or manifests stored in Git. Do not pass secrets on the command line or write them to logs. Configuration should contain only references; the secret manager is responsible for authentication, authorization, and delivering values.

## 5. Defining the Target Environment Explicitly

Names like **staging** or **production** are useful for humans but may not be sufficient to identify actual resources. One environment can span multiple cloud accounts, subscriptions, projects, regions, clusters, and namespaces.

A deployment target should specify:

- Environment name: dev, test, staging, or production.
- Cloud account, subscription, or project ID.
- Region or zone.
- Cluster or deployment platform.
- Namespace, application, or resource group.
- Service name and deployment slot if applicable.
- Identity/role permitted to deploy.
- Approval, concurrency, and rollout policies.

Example:

~~~yaml
target:
  environment: staging
  cloud:
    provider: aws
    account: "111122223333"
    region: ap-southeast-1
  kubernetes:
    cluster: app-staging
    namespace: payments
  service: payments-api
~~~

You should not infer the target solely from a branch name or a free-form variable entered by the initiator. A branch named **release** does not automatically have permission to deploy to production. The target must be mapped through an allowlist or managed environment configuration, then verified by identity and access permissions.

### 5.1. Separating Targets from Credentials

The target specifies where the pipeline will operate; credentials determine whether the pipeline has permission to operate there. These two must be verified independently.

For example, a target configuration may point to the production cluster, but the job must still be rejected if its identity only has staging permissions. Do not allow an initiator to enter an arbitrary account ID or cluster and then use overly broad credentials to deploy there.

Ideally, each environment has its own role or service account, with permissions scoped strictly to the required resources. Production should have its own approvals and policies if required by the organization.

## 6. Creating a Unified Deployment Descriptor

When artifacts, configs, and targets are managed in separate places, a deployment descriptor can be created to bind them together into a specific deployment request.

Example:

~~~yaml
apiVersion: delivery.example/v1
kind: DeploymentRequest
metadata:
  service: payments-api
  releaseId: payments-2.8.1
  requestedBy: release-workflow

artifact:
  repository: registry.example.com/payments/api
  digest: sha256:0123456789abcdef...
  sourceCommit: a1b2c3d4

configuration:
  bundle: payments-api
  version: "2026.11.18.3"
  checksum: sha256:abcdef0123456789...

target:
  environment: staging
  account: staging-account
  region: ap-southeast-1
  cluster: app-staging
  namespace: payments

deployment:
  strategy: rolling
  timeout: 15m
  expectedReplicas: 3

secretReferences:
  - provider: aws-secrets-manager
    resource: app/staging/payments/database
~~~

This descriptor is a conceptual example, not a standard schema for Kubernetes or a specific CI tool. In a real system, you must define the schema, versioning, validation, and permissions to modify the descriptor.

The descriptor binds the artifact digest, config version, and target into a single record. If any field changes after approval, the deployment request must be re-verified or re-approved according to policy. Do not approve a descriptor and then silently swap the artifact or target right before deploying.

## 7. Validating Inputs Before Making Changes to the Environment

Before running deployment commands with side effects, the pipeline should perform preflight validation. The goal is to catch invalid inputs before modifying the state of the environment.

A preflight check typically validates:

| Group | Checks |
|---|---|
| Artifact | Correct registry, digest exists, signature/provenance passes, scan passes |
| Source | Commit and pipeline run originate from an allowed source |
| Configuration | Valid schema, all required fields present, right environment and checksum |
| Secret references | Resource exists, identity has read permission, valid version |
| Target | Account, region, cluster, namespace are in the allowlist |
| Compatibility | Artifact is compatible with runtime, config, and data schema |
| Authorization | Job identity has the proper permissions; approval is complete |
| Capacity | Sufficient resources for rollout or quota available |
| Concurrency | No conflicting deployment currently running on the same target |

If preflight fails to verify a required condition, the pipeline must stop and state clearly which field is invalid. Do not fall back to **latest**, a default config, or a default target just to push forward.

## 8. Checking Compatibility Between Artifact, Config, and Environment

A valid artifact can still be incompatible with the configuration or target environment.

Common types of incompatibility:

- The artifact requires a newer JDK than the environment's runtime.
- The image only supports ARM architecture, while the cluster only has x64 nodes.
- The config contains a property removed in the new application version.
- The application requires a new database schema, but the migration has not run yet.
- The config points to staging endpoints while the target is production.
- The service requires permissions or an API version not yet supported by the cluster.
- Replica count or resource requests exceed the environment quota.

Compatibility can be described using metadata in the artifact and config:

~~~yaml
compatibility:
  applicationVersion: "2.8.x"
  configSchema: "4"
  runtime:
    java: "21"
  databaseSchema:
    minimum: "18"
    maximum: "20"
~~~

This information is an example only. Metadata should come from the build manifest or a controlled schema, avoiding manual entry for every release. Preflight must compare these requirements against the actual capabilities of the target.

For database migrations, backward compatibility must be considered. A safe rollout can evolve the schema using an expand phase, release an application compatible with both old and new schemas, and only then remove the old structure in a later release.

## 9. Example: Passing Explicit Inputs in a Deployment Pipeline

A deployment workflow should accept an explicit artifact digest, config version, and environment. The GitHub Actions example below illustrates a manually triggered workflow with a declared environment:

~~~yaml
name: Deploy release

on:
  workflow_dispatch:
    inputs:
      artifact_digest:
        description: Immutable image digest
        required: true
        type: string
      config_version:
        description: Approved configuration version
        required: true
        type: string
      target_environment:
        description: Deployment environment
        required: true
        type: environment

permissions:
  contents: read

jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - name: Validate deployment inputs
        env:
          ARTIFACT_DIGEST: ${{ inputs.artifact_digest }}
          CONFIG_VERSION: ${{ inputs.config_version }}
          TARGET_ENVIRONMENT: ${{ inputs.target_environment }}
        run: |
          [[ "$ARTIFACT_DIGEST" =~ ^sha256:[a-f0-9]{64}$ ]]
          [[ "$CONFIG_VERSION" =~ ^[A-Za-z0-9._-]+$ ]]
          [[ "$TARGET_ENVIRONMENT" == "staging" || "$TARGET_ENVIRONMENT" == "production" ]]

  deploy:
    needs: validate
    runs-on: ubuntu-latest
    environment: ${{ inputs.target_environment }}
    permissions:
      contents: read
      id-token: write
    steps:
      - uses: actions/checkout@v4

      - name: Deploy immutable release
        env:
          ARTIFACT_DIGEST: ${{ inputs.artifact_digest }}
          CONFIG_VERSION: ${{ inputs.config_version }}
          TARGET_ENVIRONMENT: ${{ inputs.target_environment }}
        run: |
          ./scripts/deploy.sh --artifact-digest "$ARTIFACT_DIGEST" --config-version "$CONFIG_VERSION" --environment "$TARGET_ENVIRONMENT"
~~~

This example only illustrates how to pass and validate inputs. The `id-token: write` permission is used when the script authenticates to the cloud via OIDC; if the platform uses another workload identity mechanism, grant the corresponding minimal permission. The deploy script must still verify that the digest exists, the config version is approved, and the environment maps to the right account/cluster. String-format validation alone does not prove the artifact is trusted or that the initiator has production permissions.

In a real workflow, you must configure protection rules for the production environment, restrict who can trigger it, and require approval if policy mandates it. Actions used in the workflow must also be pinned and updated according to the organization's security process.

## 10. Never Use Arbitrary Input Data as Commands or Paths

Some inputs come from initiators, pull requests, webhooks, or external systems. They must be treated as untrusted data until verified.

Do not interpolate branch names, release notes, environment names, or config paths directly into shell commands. Instead:

- Validate values against an allowlist and schema.
- Pass data via environment variables or separate arguments.
- Do not use `eval` or construct shell commands from arbitrary strings.
- Normalize and validate paths to prevent path traversal.
- Look up the target from a managed environment catalog.
- Limit input size and data types.
- Record the initiator and input source.

In particular, never let an input arbitrarily select a secret resource or cloud role. The pipeline must map an allowed environment to its corresponding identity and secret scope.

## 11. Tying Approvals to the Exact Set of Inputs

An approval is only meaningful when the approver knows exactly what will be deployed. The approval view should display:

- Artifact name, version, and digest.
- Commit SHA and build run ID.
- Config version and checksum.
- Target environment, account, region, cluster, and namespace.
- Deployment strategy and rollout scope.
- Test, scan, and preflight results.
- Requester and request timestamp.

If the artifact digest, config version, or target changes after approval, it must be re-evaluated and require a new approval when policy dictates. A generic approval for release 2.8.1 is insufficient if multiple images or config bundles share the same name with different contents.

You can generate a fingerprint for the deployment descriptor by hashing a canonicalized representation of critical fields. A fingerprint helps match the approved input set with the input set actually deployed. You must clearly define which fields are included in the fingerprint and canonicalize the data before hashing.

## 12. Recording Inputs for Traceability and Rollback

After deploying, save the deployment descriptor or equivalent record along with the execution result.

Minimum information:

- Actual artifact digest deployed.
- Config version and checksum.
- Target environment and resource identity.
- Deployment revision or release ID.
- Pipeline run ID, commit SHA, and build provenance.
- Approval record.
- Start/end timestamps and rollout result.
- Health check and post-deploy verification results.

When rolling back, do not simply pick a `previous` tag that may have changed. Use the previous deployment record to restore the exact artifact digest and config version that ran stably.

Also distinguish application rollback from data rollback. If a release ran a backward-incompatible database migration, bringing back the old image may not be enough to restore the service. The rollback plan must account for schema, data, and related infrastructure changes.

## 13. Throttling Deployments and Protecting the Target

Two concurrent deployments to the same service can overwrite state or cause an inconsistent rollout. Concurrency must be controlled per target or service.

Measures:

- Use a deployment lock or concurrency group per environment and service.
- Allow only one release to modify the same target at a time if the platform does not support safe coordination.
- Cancel an older run only when cancellation is designed to be safe.
- Use idempotent deployment operations so retries do not create duplicate resources.
- Check current state before applying changes.
- Scope deploy permissions to specific targets.
- Enforce timeouts and stop-rollout mechanisms when health checks fail.

Do not use a single credential with permissions across all clusters just to simplify the pipeline. Separating identities by environment limits the blast radius if a job is compromised or inputs are manipulated.

## 14. End-to-End Example: Deploying a Release to Staging

Suppose the team is releasing version 2.8.1 of the `payments-api` service:

1. The build pipeline produces an image and records its digest, commit SHA, build run ID, and provenance.
2. The image is scanned and tested. The artifact is stored in the registry by digest.
3. The config repository publishes staging bundle version 2026.11.18.3, along with its checksum and config commit.
4. The release descriptor binds the image digest, config version, and staging target.
5. Preflight verifies the image, signature, scan results, config schema, secret references, cluster, and deploy permissions.
6. An authorized approver approves the descriptor if staging requires approval.
7. The pipeline deploys the exact verified image digest and config version.
8. The rollout is monitored; smoke tests and health checks run against the new deployment revision.
9. The pipeline saves the descriptor, deployment result, and post-deploy evidence.
10. After staging passes, the same image digest is promoted to production with separate production configuration and target.

In the production step, the artifact is not rebuilt. Production configuration and secret references change per environment, while the artifact digest remains unchanged. This allows the team to prove that the deliverable tested in staging is the exact deliverable released.

## 15. Deployment Input Checklist

Before running a deployment, verify:

- [ ] Artifact has an immutable repository, version, and digest.
- [ ] Digest is retrieved from the build/publish result and re-verified from the registry.
- [ ] Artifact has origin, signature, or provenance according to policy.
- [ ] Tests and security scans are tied to the exact artifact digest.
- [ ] Configuration has an immutable version or commit and checksum.
- [ ] Configuration matches the schema and is compatible with the artifact.
- [ ] Environment configuration contains no plaintext secrets.
- [ ] Secrets are referenced only via a secret manager with appropriate access policies.
- [ ] Target explicitly specifies environment, account/project, region, cluster, and namespace.
- [ ] Target is mapped from a managed allowlist or environment registry.
- [ ] Job identity only has permissions on the intended target.
- [ ] User or webhook inputs are validated before use.
- [ ] Approval is bound to the exact artifact, config, and target.
- [ ] Concurrency control and timeouts are configured for the deployment.
- [ ] Deployment record captures sufficient inputs and results for traceability.
- [ ] Previous version's artifact and config can be identified for rollback.

Automated deployment begins with a clear input contract. When artifacts are immutably identified, configurations are versioned and compatibility-checked, and targets are verified with appropriate identities and permissions, the pipeline can deploy the right deliverable to the right environment while preserving evidence for every release.

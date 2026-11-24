# Configuration Versioning, Drift Control, and Rollback to a Known-Good Revision in Spring Boot

## 1. Overview

Spring Boot supports Externalized Configuration: application values can come from YAML/properties files, profiles, environment variables, system properties, command-line arguments, Config Data imports, and many other `PropertySource`s. This allows deploying the exact same application artifact across development, staging, and production.

However, letting configuration change independently of source code raises operational questions:

- Which configuration revision was running when an incident occurred?
- Did someone editing a ConfigMap directly cause production to diverge from Git?
- If startup arguments override a timeout, does `application-prod.yml` still reflect the real value?
- When a release causes errors, do we need to roll back the application image, configuration, or both?
- Should a revoked secret ever be restored simply because it appeared in a previous release?

Three capabilities must be built:

1. **Versioning:** configuration changes have commits, reviews, versions, and deterministic artifacts.
2. **Drift control:** detecting when actual state diverges from desired state or has unapproved differences.
3. **Rollback:** restoring a verified app/config combination, not merely changing a version label.

These capabilities belong to deployment and operations workflows. Spring Boot provides binding, precedence, and validation mechanisms, but does not build a complete versioning and rollback workflow on its own.

## 2. Desired, Deployed, and Effective Configuration

Distinguish:

| Concept | Definition | Example |
| --- | --- | --- |
| Desired | Intended, approved configuration | Git commit `abc123` has `timeout=5s` |
| Deployed | Configuration provisioned by the platform for the workload | ConfigMap `catalog-cfg-v17`, Secret reference |
| Effective | Value Spring Boot actually selects after precedence and binding | `timeout=30s` due to CLI override |

Example production file:

~~~yaml
app:
  catalog:
    timeout: 5s
~~~

Yet the process runs with:

~~~bash
java -jar catalog.jar --spring.profiles.active=prod --app.catalog.timeout=30s
~~~

Under standard Spring Boot configuration precedence, the command-line argument beats the Config Data value. A valid file in Git does not mean the effective value matches it.

To control drift, answer all three questions: what Git intends, what the platform provisioned, and what the program bound. Never check by reading only a single YAML file.

## 3. Release Identifiers to Record

A release record should capture at minimum:

- **Application version:** version number or Git commit of the application.
- **Image digest/JAR checksum:** identifies the exact artifact, avoiding reliance on floating tags alone.
- **Configuration Git commit:** reviewed non-secret source state.
- **Config artifact digest:** rendered environment manifests/values.
- **Deployment ID:** pipeline run or rollout execution.
- **Profile:** active profiles.
- **Secret reference/version:** secret identifier, containing no plaintext.
- **Approval/verification evidence:** approver, test results, and post-rollout observations.

Illustrative example:

~~~json
{
  "service": "catalog-api",
  "environment": "production",
  "appVersion": "2.4.1",
  "imageDigest": "sha256:<image-digest>",
  "configRevision": "cfg-17",
  "configGitCommit": "abc123def456",
  "deploymentId": "deploy-1842",
  "secretReference": "catalog-api/production",
  "secretVersion": "approved-current"
}
~~~

One image can run with multiple config revisions. Conversely, a config revision may only be supported starting from a specific app version. Never use a single `serviceVersion` field as a substitute for all of this metadata.

## 4. Versioning Non-Secret Configuration with Git

Settings suitable for Git:

~~~yaml
app:
  catalog:
    connect-timeout: 3s
    read-timeout: 8s
    max-retries: 2
    enabled: true
~~~

Git enables diff reviews, authorship tracking, rollbacks via revert commits, and comparisons across environments.

Never commit real secrets:

~~~yaml
# Unsafe example
spring:
  datasource:
    password: "REAL_PASSWORD"
~~~

Replace with an appropriate secret source:

~~~yaml
spring:
  datasource:
    username: "${DB_USERNAME}"
    password: "${DB_PASSWORD}"
~~~

Placeholders only illustrate referencing. Environment variables are not an absolute secret store; process inspection, crash dumps, or careless logging can expose values. In production, consider a secret manager or mounted secret files with access controls, rotation, and auditing.

If a credential was ever committed, deleting it in a later commit does not remove it from Git history, clones, or backups. Assess exposure risk and revoke/rotate it.

## 5. Reference Configuration Repository Layout

~~~text
deployment-config/
  README.md
  services/
    catalog-api/
      common/
        application.yml
      environments/
        dev/
          application-dev.yml
          deployment.yaml
        staging/
          application-staging.yml
          deployment.yaml
        production/
          application-prod.yml
          deployment.yaml
      schema/
        configuration-guide.md
      releases/
        release-2.4.1.json
  policies/
    reviewers.md
    release-checklist.md
    rollback-runbook.md
~~~

This is a reference layout. With Helm, Kustomize, or a GitOps controller, folder names may differ. The key criteria are:

1. A defined place for per-environment desired state.
2. Changes go through PR/review.
3. No plaintext secrets included.
4. Builds/deployments pin exact commits.
5. Artifacts are traceable and retrievable.
6. Differences across environments can be inspected.
7. A rollback runbook and designated owners exist.

If a pipeline only records "deploy branch main," once the branch advances you cannot reliably reproduce what was deployed without storing the commit SHA.

## 6. Common Configuration and Profile Configuration

`application.yml`:

~~~yaml
spring:
  application:
    name: catalog-api
app:
  catalog:
    connect-timeout: 3s
    read-timeout: 8s
    max-retries: 2
~~~

`application-prod.yml`:

~~~yaml
app:
  catalog:
    read-timeout: 5s
    max-retries: 3
~~~

When the `prod` profile is activated, profile-specific configuration documents override common values per Config Data rules. However, final values can still be overridden by environment, CLI, system properties, or imported configuration.

Therefore, deployment records must specify active profiles, approved external config sources, and which overrides are permitted.

For collections like `List`, do not assume elements from two sources merge item by item. Spring Boot applies merge/replacement rules depending on the target type and property source. If a list is critical configuration, verify the actual bound result.

## 7. Policy on Authoritative Configuration Sources

Suppose Git contains:

~~~properties
app.catalog.max-retries=3
~~~

Environment:

~~~text
APP_CATALOG_MAXRETRIES=6
~~~

CLI:

~~~bash
java -jar catalog.jar --app.catalog.max-retries=1
~~~

In standard setups, the final value is `1`. To avoid losing control:

- Non-secret settings have a single authoritative source.
- Secrets have their own source and rotation workflow.
- CLI/`-D` overrides are used only when authorized.
- Emergency overrides require a ticket, owner, and expiration deadline.
- Do not let multiple teams silently tweak the same property.
- Do not log the entire `Environment` to hunt down overrides.
- In production, use allowlist-based observability for essential effective settings.

Never merge YAML files manually in your head and treat that as effective configuration; follow Spring Boot's rules and verify against the running app version.

## 8. Digests and Revisions Must Be Meaningful

A field:

~~~yaml
app:
  config:
    revision: cfg-17
~~~

helps traceability, but does not prove all configuration belongs to `cfg-17`. An operator might override a timeout via env while the revision string stays unchanged.

A better pipeline:

1. Check out the exact Git commit.
2. Render templates/overlays.
3. Produce an immutable non-secret config artifact.
4. Compute a digest in a defined canonical format.
5. Record the digest in the release record.
6. Compare live manifests against the artifact at deploy time.
7. Verify selected effective settings after binding.

Distinguish:

| Fingerprint | Covers | Limitations |
| --- | --- | --- |
| Raw-file SHA-256 | File bytes | Comments/whitespace also change the hash |
| Rendered-manifest SHA-256 | Rendered manifest artifact | Does not necessarily cover runtime overrides |
| Allowlisted effective settings | Approved subset of observable properties | Does not cover every property |
| Secret version ID | Credential version | Does not expose secret contents |

Never log raw hashes of low-entropy passwords: hashes can help attackers guess values. For credentials, record secret-manager-issued references/versions and restrict access.

## 9. Release Metadata in Kubernetes

Pipeline-approved revisions can be attached to the Pod template:

~~~yaml
spec:
  template:
    metadata:
      annotations:
        example.org/config-revision: "cfg-17"
        example.org/config-commit: "abc123def456"
~~~

Annotations under `example.org` are only examples defined by operations. Kubernetes does not verify that these labels match ConfigMap contents. The release system must tie them to the actual artifact.

Changing the Pod template creates a new Deployment revision and triggers a rollout. However, an annotation does not guarantee the application image, secrets, and ConfigMaps match merely because a version string says so.

For each deployment, store links from the deployment ID to the image digest, config commit, rendered manifest, and test evidence.

## 10. Typed Configuration Schema and Validation

An explicitly typed class helps catch mistakes across revisions.

~~~java
package com.example.catalog.config;

import java.time.Duration;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.catalog")
public record CatalogProperties(
        @NotBlank String baseUrl,
        @NotNull Duration connectTimeout,
        @NotNull Duration readTimeout,
        @Min(0) @Max(10) int maxRetries
) {}
~~~

Registration:

~~~java
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class CatalogApplication {}
~~~

In Spring Boot 3.x, Bean Validation requires a suitable provider, typically supplied by `spring-boot-starter-validation`. Records with a matching constructor are constructor-bound when registered via configuration properties scanning or enabling.

Limitations to understand:

- `@NotBlank` does not verify that the URL has a valid scheme or host.
- `@NotNull Duration` does not require the duration to be greater than 0.
- Primitive `int` defaults to 0 if the field is missing.
- Wrongly typed values fail conversion before validation runs.
- Validators do not replace smoke tests verifying real connectivity.

Still, schemas and validation greatly reduce the risk of deploying a revision with obviously invalid values.

## 11. Pipelines Must Check Multiple Layers

| Layer | Example | Mechanism |
| --- | --- | --- |
| Syntax | Wrong YAML indentation | YAML parser/linter |
| Property names | Typo `max-retrie` | Schema and strict unknown-field check |
| Type conversion | `timeout=tomorrow` | Spring Binder |
| Constraints | `max-retries=-5` | Bean Validation |
| Cross-field | Enabled while missing endpoint | Class-level validator / constructor invariant |
| App/config compatibility | Old app does not understand new key | Version matrix and integration tests |
| Secret references | Secret key does not exist | Authorized deploy-time checks |
| Behavior | Slow/failing upstream | Smoke tests and operational metrics |

With `@ConfigurationProperties`, consider `ignoreUnknownFields=false` to catch unbound properties within a namespace owned by one class. Do not turn on overly broad strict policies across namespaces shared by multiple modules without a complete schema.

A syntactically valid YAML file is not guaranteed to be a runnable configuration.

## 12. What Should a Configuration Pull Request Include?

A diff:

~~~diff
 app:
   catalog:
-    read-timeout: 8s
+    read-timeout: 5s
~~~

The PR should document:

- Reason for the change.
- Affected environments and services.
- Compatible application versions.
- Risks to latency, timeouts, retries, or resources.
- Tests executed.
- Success metrics and rollback thresholds.
- Known-good revision.
- Reviewers and approvers.

A one-line YAML change can bring down an entire service; diff line count does not reflect risk. Settings like timeouts, feature flags, retry budgets, and connection pools require strict release policies.

## 13. Promotion Across Environments

~~~text
Pull request
      |
      v
Lint + schema + policy
      |
      v
Approved commit and config artifact
      |
      v
Development deployment
      |
      v
Staging integration/smoke tests
      |
      v
Production approval
      |
      v
Canary or staged rollout
      |
      v
Verify SLO and effective config
      |
      +--- failure ---> rollback
      |
      v
Mark revision known good
~~~

Staging and production do not need identical values for everything. Endpoints and secrets must differ, and some limits differ intentionally. However, both environments should be generated from approved source revisions and rendering rules.

Avoid testing staging from one commit and then manually editing a separate file to deploy production without re-reviewing and retesting.

## 14. What Is Configuration Drift?

Drift is any unintended divergence between desired state and actual state.

Common forms:

1. **Source drift:** a file on a server was edited while Git stayed unchanged.
2. **Deployment drift:** live manifests differ from approved rendered manifests.
3. **Effective drift:** unplanned env/CLI/system property overrides.
4. **Pod drift:** Pods in the same service are unexpectedly running different image/config revisions.
5. **Secret-reference drift:** workloads point to the wrong secret path or version.
6. **Environment drift:** staging and production differ outside their approved baseline.
7. **Schema drift:** code renamed or changed a field type, yet config was not updated.
8. **Emergency drift:** a direct hotfix in the cluster was never synced back to Git.

Not every difference is bad. Staging using an 8s timeout while production uses 5s can be completely valid if reviewed and recorded in the environment-specific baseline.

## 15. Comparing Desired vs. Live State

~~~text
Git approved config
        |
        v
Render manifest
        |
        +-------------------+
        |                   |
        v                   v
Expected snapshot     Live deployment snapshot
        |                   |
        +---------+---------+
                  |
                  v
          Compare allowlisted fields
                  |
         +--------+--------+
         |                 |
         v                 v
     No drift          Drift detected
                           |
                           v
                    Alert / investigate
~~~

Compare:

- Image digest.
- ConfigMap name/revision/digest.
- Pod template annotations.
- Profiles/allowed environment settings.
- Selected operationally meaningful non-secret fields.
- Secret references/versions, never secret plaintext.
- Deployment revisions and timestamps.

Never dump the full `Environment` over the network for comparison; doing so can expose passwords, tokens, certificates, or connection strings. Property sources that do not support full enumeration can also hide settings from tooling; document the exact scope of checks.

## 16. Detecting and Handling Manual Drift

Example of an operator editing directly:

~~~bash
kubectl edit configmap catalog-config -n production
~~~

This causes live state to diverge from Git. In a GitOps setup, a controller may reconcile the change away; without a controller, drift can persist until the next deployment.

Policies:

- Restrict RBAC for direct edits to production resources.
- Route routine changes through the repository and pipeline.
- Emergency hotfixes require a ticket, justification, owner, and expiration time.
- Fold hotfixes back into Git or remove them once resolved.
- Monitor audit logs and drift alerts.
- Do not treat GitOps "Synced" as proof of right effective values if Spring Boot has other overriding sources.

During incidents, manual overrides may be necessary, but they must never become an invisible configuration source.

## 17. Versioned Kubernetes ConfigMaps

Example non-secret ConfigMap:

~~~yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: catalog-config-v17
  namespace: production
  labels:
    app: catalog-api
    example.org/config-revision: "cfg-17"
data:
  APP_CATALOG_CONNECTTIMEOUT: "3s"
  APP_CATALOG_READTIMEOUT: "5s"
  APP_CATALOG_MAXRETRIES: "3"
~~~

These variables follow Spring Boot canonical naming: dots to `_`, hyphens removed, and uppercase.

A Deployment can reference it with:

~~~yaml
envFrom:
  - configMapRef:
      name: catalog-config-v17
~~~

With `envFrom`, environment is populated when the container starts. **Editing the ConfigMap later does not automatically change the environment of a running process.**

ConfigMaps are not for secrets. Nor are Kubernetes Secrets encrypted securely merely because `data` is Base64-encoded; RBAC, etcd protection, Pod permissions, and secret rotation remain required.

## 18. Volume Config and Spring Boot Reload

Kubernetes can mount ConfigMaps/Secrets as files. Regular volume mounts can receive updates after a sync delay; `subPath` mounts have different update limitations.

Spring Boot can load a config tree:

~~~yaml
spring:
  config:
    import: "optional:configtree:/run/config/"
~~~

However, **changing files after startup does not automatically rebind all `@ConfigurationProperties` beans**. Unless the project designs a refresh mechanism, the most controllable approach is:

1. Create a new config revision.
2. Update the Deployment/Pod template.
3. Roll out new Pods.
4. Verify readiness and smoke tests.
5. Check revision and observable effective values.

Dynamic refresh solutions require dedicated mechanics, consistency tests, and auditing of when changes take effect.

## 19. Versioned ConfigMaps and Immutable Resources

Instead of mutating a single mutable ConfigMap:

~~~text
catalog-config
~~~

you can release:

~~~text
catalog-config-v16
catalog-config-v17
catalog-config-v18
~~~

Advantages: the Pod template references a specific version, reducing silent mutations and keeping old resources available for rollback.

However, you must:

- Retain old resources during the rollback window.
- Never trust the name `v17` while ignoring content digests.
- Have a cleanup/retention policy.
- Control overrides outside ConfigMaps.
- Avoid generating new resources solely to mask broken state management.

Kubernetes provides an `immutable` option for ConfigMaps/Secrets where appropriate. When modifying an immutable object's contents, create a new object and update references rather than patching old data in place.

## 20. Triggering Rollouts with Annotations

Example Pod template:

~~~yaml
spec:
  template:
    metadata:
      annotations:
        example.org/config-digest: "<approved-config-artifact-digest>"
~~~

The pipeline computes the digest and updates it alongside the config revision. Changing the Pod template creates a new ReplicaSet.

However, **annotations do not keep a same-named ConfigMap immutable**. If the ConfigMap is edited while the annotation still reads `cfg-17`, a new Pod can load data no longer belonging to that revision.

For systems requiring strict reproducibility and rollback, versioned resources or content-addressed artifacts are clearer choices.

## 21. Rollout Success Does Not Mean the App Uses the Right Config

The command:

~~~bash
kubectl rollout status deployment/catalog-api -n production
~~~

tracks whether the Deployment rollout reached the desired replica state, but does not prove:

- `spring.profiles.active` is right.
- An environment variable is not overriding a timeout.
- Secret references point to the right version.
- Bean validation satisfied all business rules.
- Remote APIs are working.
- Error rates and latency meet targets.

Therefore, verify Pod image/config references, startup/validation, smoke tests, and operational metrics. Readiness is only one signal in release verification.

## 22. Observing Configuration Without Exposing Secrets

Spring Boot Actuator provides `env` and `configprops`, useful for diagnostics. However, never expose them publicly just to check drift.

Restricted example configuration:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info
  endpoint:
    env:
      show-values: never
    configprops:
      show-values: never
~~~

If a custom diagnostic endpoint is needed, return only allowlisted fields and protect access:

~~~json
{
  "service": "catalog-api",
  "applicationVersion": "2.4.1",
  "configRevision": "cfg-17",
  "profile": "prod",
  "settings": {
    "connectTimeoutSeconds": 3,
    "readTimeoutSeconds": 5,
    "maxRetries": 3
  }
}
~~~

Never return an entire configuration bean containing `apiKey`, and never log `toString()` of a Java record holding credentials. A self-reported version field is only metadata and does not prove no other overrides exist.

## 23. Differences Between Environments

Example:

| Property | Staging | Production | Approved? |
| --- | --- | --- | --- |
| `connect-timeout` | 3s | 3s | Identical |
| `read-timeout` | 8s | 5s | Yes |
| `max-retries` | 2 | 3 | Yes |
| `feature-x-enabled` | true | false | Yes, staged rollout |
| `unknown-flag` | true | true | Needs schema review |

A baseline can record:

~~~yaml
allowed-differences:
  app.catalog.read-timeout:
    staging: 8s
    production: 5s
    reason: "Production latency target"
  app.catalog.max-retries:
    staging: 2
    production: 3
    reason: "Approved retry policy"
~~~

Never compare raw secrets across environments; production and staging require separate credentials. Drift detection must distinguish **intentional** differences from **unapproved** differences.

## 24. "Known Good" Requires Evidence

A `stable` tag does not automatically make a build known good.

Typical criteria:

- Configuration passes syntax/schema checks.
- App artifact and config revision are compatible.
- Secret references are valid.
- Bean Validation and startup succeed.
- Rollout and readiness pass.
- Smoke tests pass.
- Error rate, latency, timeouts, and saturation are within thresholds.
- No unexplained drift exists.
- Timestamp, approver, and artifact IDs are fully recorded.

A release that passed staging is not automatically known good for production if traffic, upstreams, or secrets differ. Release records should tie evidence to the actual environment.

## 25. What to Roll Back When Configuration Causes an Incident?

| Situation | Resolution |
| --- | --- |
| Timeout raised too high | Revert to the appropriate config revision |
| New app requires config field missing from older config | Add the config field or roll both app and config back to a compatible pair |
| New secret has wrong permissions | Fix secret reference/permissions; never restore a weak secret |
| ConfigMap changed, yet Pods did not restart | Roll out Pods referencing the right revision |
| Old config incompatible with DB migration | Execute a dedicated migration/recovery plan |
| Dynamic feature flag changed | Roll back in the flag provider and verify propagation |

Rollback is a **controlled deployment**, not simply copying an old YAML file back. Know the app version, config revision, secret version, and related infrastructure.

## 26. Rollback Runbook

### Step 1 — Record current state

~~~text
Service: catalog-api
Current deployment: deploy-1842
Current configuration: cfg-18
Last known good: deploy-1837 / cfg-17
Symptom: timeout rate exceeds threshold
~~~

These are illustrative IDs.

### Step 2 — Investigate scope

Compare changes across code, config, traffic, secrets, databases, and upstreams. Do not assume root cause merely because an incident happened right after a commit.

### Step 3 — Verify the old revision is still usable

Check app/config compatibility, database migrations, and secret references; credentials revoked due to compromise must never be restored.

### Step 4 — Reverse the change

Create a Git revert commit or redeploy the stored immutable artifact. Never apply an ad-hoc patch inside a container and call the rollback done.

### Step 5 — Roll out and verify

Confirm Pod templates, ConfigMap/Secret references, profiles, image digests, and non-secret effective properties.

### Step 6 — Verify service health

Wait for readiness, run smoke tests, check error rate/latency/timeouts/saturation, and check for remaining drift.

### Step 7 — Audit

Record the new deployment ID, executed steps, approver, outcome, and preventive actions. Do not erase history of the failed release.

## 27. Git Revert vs. Checkout

A change:

~~~diff
-app.catalog.read-timeout=5s
+app.catalog.read-timeout=45s
~~~

Can be reversed with:

~~~bash
git revert <bad-config-commit>
~~~

Revert creates a new commit, preserving the audit trail. If the commit also contained unrelated valid changes, open a PR reversing only the specific fields to restore.

Meanwhile:

~~~bash
git checkout <known-good-commit>
~~~

only updates the local working tree and **does not change production**. You still must render, test, approve, deploy, and verify.

In GitOps, fixing/reverting in Git is more durable than a direct hotfix, though an emergency runbook is still needed if the GitOps system itself is unavailable.

## 28. Limitations of Kubernetes rollout undo

The command:

~~~bash
kubectl rollout undo deployment/catalog-api -n production
~~~

targets the Deployment's Pod template revision history. It **does not restore the contents of ConfigMaps, Secrets, external config services, or databases**.

Example:

1. Pod template references a same-named ConfigMap `catalog-config`.
2. An operator edits the ConfigMap from 5s to 45s.
3. New Pods use 45s.
4. `rollout undo` reverts the Pod template, yet the ConfigMap still contains 45s.

When Pods restart, they can keep picking up 45s.

Versioned ConfigMaps like `catalog-config-v17` let the Pod template revert to the old reference **provided the resource still exists and no other overrides conflict**. Always verify references, resource contents, and effective values.

## 29. Never Restore a Revoked Secret

An older leaked and revoked token might belong to a previous known-good release. Reverting blindly to that exact snapshot can break the application or reintroduce a compromised credential.

You must:

- Separate rollbacks of non-secret settings from credentials.
- Verify secret references/versions are still valid.
- Keep applied security remediations intact.
- If the older app does not support the new auth method, deploy a compatibility fix rather than restoring a compromised credential.
- Log an audit trail of the secret change without exposing values.

**Operational rollback must never accidentally undo a security credential revocation.**

## 30. Database Schemas and Feature Flags

A setting:

~~~yaml
app:
  features:
    new-order-schema: true
~~~

may require a new database schema. If data was already migrated in a backward-incompatible way, flipping the flag back alone will not restore the old behavior. When a rollback window is needed, design migrations using expand–migrate–contract patterns.

Dynamic feature flags may change outside Git. Record provider history, targeting rules, cache/polling intervals, and activation timestamps. Git config commits only describe part of the state.

Do not assume Spring Boot automatically rebinds `@ConfigurationProperties` beans when source files change. If a dedicated refresh mechanism is present, design dedicated tests and audits for it.

## 31. Canarying Configuration Revisions

~~~text
Approve cfg-18
       |
       v
Deploy to a limited canary
       |
       v
Observe latency, errors, retry, saturation
       |
       +--- failure ---> restore cfg-17
       |
       v
Promote progressively
       |
       v
Verify full production and mark known good
~~~

Define upfront:

- Percentage of traffic or canary Pods.
- Comparison metrics and failure thresholds.
- Observation duration suited to traffic volume.
- Who decides to halt/roll back.
- How to distinguish `cfg-17` vs. `cfg-18` Pods.
- How to restore the exact config artifact if it fails.

If Pods share a mutable ConfigMap whose values change unpredictably, the canary no longer represents a consistent snapshot.

## 32. App/Config Compatibility Matrix

Example:

| Application | cfg-16 | cfg-17 | cfg-18 |
| --- | --- | --- | --- |
| 2.3.x | Verified | Needs regression test | Does not understand new field |
| 2.4.0 | Has fallback | Verified | Passed staging |
| 2.4.1 | Has fallback | Known good production | Canarying |

This is an example table. When rolling app 2.4.1 back to 2.3.x, `cfg-18` may no longer be compatible. Select a verified **app/config pair**.

A config schema version helps pipelines check compatibility, but only if CI or startup actually enforces it.

Renaming a property from `retry-count` to `max-retries` requires a migration plan, deprecation window, or backward-compatible binding for rolling upgrades. IDE metadata alone does not automatically translate old names to new names at runtime.

## 33. Testing Configuration with Spring Boot Test

A test using `ApplicationContextRunner`:

~~~java
import java.time.Duration;
import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class CatalogConfigurationTest {

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties(CatalogProperties.class)
    static class TestConfig {}

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withUserConfiguration(TestConfig.class);

    @Test
    void approvedConfigurationCanBind() {
        runner.withPropertyValues(
                "app.catalog.base-url=https://catalog.example.org",
                "app.catalog.connect-timeout=3s",
                "app.catalog.read-timeout=5s",
                "app.catalog.max-retries=3"
        ).run(context -> {
            assertThat(context).hasNotFailed();
            CatalogProperties props =
                    context.getBean(CatalogProperties.class);
            assertThat(props.readTimeout())
                    .isEqualTo(Duration.ofSeconds(5));
        });
    }
}
~~~

This example assumes the class from Section 10 and matching Spring Boot Test/JUnit/AssertJ/validation dependencies. Add a test with `max-retries=99` and assert the context fails due to the constraint.

In real CI, test against the **actual config artifact/overlay to be deployed**, not just literals disconnected from production state.

## 34. Configuration Control Pipeline

A CI/CD workflow:

~~~text
1. Checkout pinned application and config commits
2. Validate YAML/JSON syntax
3. Render environment overlays
4. Scan for plaintext secrets/policy violations
5. Validate schema and required fields
6. Run Binder + Bean Validation tests
7. Check application/config compatibility
8. Produce immutable non-secret config artifact
9. Save digest, approvals and deployment metadata
10. Deploy staging and run smoke/integration tests
11. Approve production
12. Canary/staged rollout
13. Observe metrics and compare revision
14. Mark known good or rollback
~~~

Projects may use GitHub Actions, GitLab CI, Jenkins, Argo CD, Flux, or custom platforms. The specific tool matters less than reproducible artifacts and solid evidence.

Pipelines must never store decrypted secrets in artifacts or logs. PR tests can use dummy credentials, while deploy-time checks verify secret references with restricted permissions.

## 35. Promoting Immutable Artifacts

Anti-pattern:

~~~text
Staging: render branch main on Monday
Production: render branch main on Thursday
~~~

If the branch changed, production no longer runs the exact configuration tested in staging.

Better pattern:

~~~text
Approved commit
       |
       v
Render exact artifact / environment overlay
       |
       v
Store immutable artifact + digest
       |
       +--> staging
       |
       +--> production
~~~

Environment endpoints and secrets can differ. What must stay pinned are source revisions, rendering logic, and approved environment differences. Store a digest per rendered artifact.

## 36. Log Revisions, Not Secrets

Do not do:

~~~java
log.info("Environment: {}", environment);
log.info("Config bean: {}", credentials);
~~~

A Java record's default `toString()` can print tokens and passwords.

You can log metadata:

~~~java
log.info(
        "Release appVersion={} configRevision={} deploymentId={}",
        appVersion,
        configRevision,
        deploymentId
);
~~~

When logging effective values, log only approved non-secret fields:

~~~java
log.info(
        "Catalog readTimeoutSeconds={} maxRetries={}",
        catalogProperties.readTimeout().toSeconds(),
        catalogProperties.maxRetries()
);
~~~

Never use raw secret hashes to compare drift. When tracking which credential is active, log only an authorized reference/version.

## 37. Common Errors

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Git is right yet runtime is wrong | Env/CLI override | Inspect effective sources |
| ConfigMap changed yet old Pods unchanged | Environment loaded at startup | Roll out new Pods |
| Mounted file changed yet bean kept old value | Missing refresh mechanism | Restart or dedicated refresh mechanism |
| `rollout undo` ran yet timeout still wrong | Mutable ConfigMap not reverted | Restore the right resource/reference |
| Unknown which config revision is running | Commits/digests not pinned | Maintain immutable release records |
| Staging passed, production failed | Different overlays/secrets/traffic | Test against baseline |
| Schema valid, yet app still fails | Binding/validation/compatibility | Test app-config pairs |
| False drift alerts | Dynamic fields or intentional differences not filtered | Allowlist and baseline |
| Manual hotfix persists forever | Missing reconciliation/auditing | GitOps and change control |
| Rollback causes auth errors | Old secret was revoked | Use current valid credentials |
| App rollback breaks database | Incompatible migration | Expand–contract/recovery plan |
| Revision label right yet contents wrong | Label decoupled from artifact | Digests and verification |
| Drift check leaks passwords | Dumping configuration beans | Diagnostic allowlist |

## 38. Self-Check Exercises

### Exercise 1

Git `application-prod.yml` sets timeout 5s; CLI passes 20s. Can we conclude the app uses 5s?

**Answer:** no. CLI can override Config Data. Check effective properties.

### Exercise 2

Two Pods share the same image digest, yet one uses `cfg-17` and the other `cfg-18`. Are they running the exact same operational release?

**Answer:** no. Configuration can alter behavior even with an identical binary.

### Exercise 3

A password was committed to Git and then deleted in the next commit. Is that enough?

**Answer:** no. Assess exposure scope and revoke/rotate it because Git history, clones, and backups can still hold the value.

### Exercise 4

A Deployment uses `envFrom` with a ConfigMap. Does editing the ConfigMap automatically update running processes?

**Answer:** no. New Pods are normally needed to pick up updated environment variables.

### Exercise 5

Does `kubectl rollout undo` automatically restore the contents of a same-named ConfigMap that was edited?

**Answer:** no. It primarily reverts the Pod template revision.

### Exercise 6

A Git tag named `stable` has never run in production. Is it automatically production known good?

**Answer:** no. Deployment evidence and operational health are required.

### Exercise 7

Git expects `retries=3`, yet CLI sets `retries=8`. What kind of drift is this?

**Answer:** effective/runtime drift caused by an override outside the desired source.

### Exercise 8

Should you log the SHA-256 hash of a password to check the secret version?

**Answer:** not by default. Hashes of weak secrets can be guessed; use a version or reference ID instead.

### Exercise 9

App 2.3 does not support `cfg-18`, while app 2.4 does. Is rolling the app back to 2.3 while keeping `cfg-18` safe?

**Answer:** only if compatibility was verified. Pick a known-good app/config pair.

### Exercise 10

Staging timeout 8s vs. production 5s—is that necessarily drift?

**Answer:** no, if the difference is approved and documented in the baseline.

### Exercise 11

An old secret was revoked due to compromise, and the previous known-good release used it. Should it be restored?

**Answer:** no. Keep security remediations intact and use a valid new credential.

### Exercise 12

Canary `cfg-18` raises the timeout rate. Outline the steps to handle it.

**Suggested answer:** halt promotion; identify current and known-good revisions; verify compatibility and secrets; restore the right config artifact; roll out; verify effective state, smoke tests, and metrics; document the incident.

## 39. Deployment Checklists

### Before making changes

- [ ] Non-secret configuration is versioned.
- [ ] Secrets are absent from repositories and artifacts.
- [ ] Owners and reviewers are assigned.
- [ ] PR states purpose, risks, and rollback triggers.
- [ ] Schema, validation, and compatible app versions are clear.
- [ ] Override rules are bounded.
- [ ] Environment differences have a documented baseline.

### Before production

- [ ] Application image digest is pinned.
- [ ] Configuration commit/artifact digest is pinned.
- [ ] Exact production overlay is rendered.
- [ ] Secret references are verified without printing values.
- [ ] CI verified syntax, binding, constraints, and compatibility.
- [ ] Staging/canary passed tests.
- [ ] A usable known-good release exists.
- [ ] Approvals and rollback thresholds are in place.

### After deployment

- [ ] Pod image and config references are verified.
- [ ] Readiness and smoke tests pass.
- [ ] Allowed effective values are checked.
- [ ] Errors, timeouts, latency, and resource saturation are monitored.
- [ ] Drift between desired and deployed state is checked.
- [ ] Deployment record and evidence are stored.
- [ ] Emergency overrides are retired or folded back in.

### During rollback

- [ ] Select a verified compatible app/config pair.
- [ ] Never resurrect a secret revoked for security reasons.
- [ ] Restore the exact ConfigMap/Pod template, not just `rollout undo`.
- [ ] Start new Pods when configuration loads at startup.
- [ ] Run smoke tests and verify metrics.
- [ ] Record the incident, approver, and preventive actions.

## 40. Takeaways

- **Versioning:** separate application artifact, config revision, deployment run, and secret version.
- **Drift:** unintended divergence between desired, deployed, and effective state.
- **Spring Boot precedence:** a Git file may not decide the final value if env/CLI or another source overrides it.
- **ConfigMap env:** running processes do not pick up new values automatically when a ConfigMap changes.
- **Mounted files:** updating a file does not mean all Spring Boot beans automatically rebind.
- **Versioned resources:** make rollbacks far more reproducible than mutating a single same-named resource.
- **Rollout undo:** does not restore independent ConfigMaps or Secrets.
- **Known good:** requires verified evidence, not merely a `stable` tag.
- **Rollback:** is a new deployment requiring app/config/schema/secret compatibility checks.
- **Security:** never roll back compromised credentials and never log secrets to check drift.
- **Canary/staged rollout:** catches risk before impacting all of production.
- **Allowlist diagnostics:** inspect safe settings instead of dumping the full `Environment`.
- **Governance:** reviews, promotion, auditing, and drift detection matter more than untracked manual overrides.

## References

- [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html)
- [Spring Boot — Config Data](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.files)
- [Spring Boot — Type-safe Configuration Properties](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties)
- [Spring Boot — Actuator Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html)
- [Kubernetes — ConfigMaps](https://kubernetes.io/docs/concepts/configuration/configmap/)
- [Kubernetes — Secrets](https://kubernetes.io/docs/concepts/configuration/secret/)
- [Kubernetes — Deployments](https://kubernetes.io/docs/concepts/workloads/controllers/deployment/)
- [OWASP — Secrets Management](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html)

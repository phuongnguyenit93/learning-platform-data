# Versioning and Validating Configuration

## Learning Objectives

After completing this lesson, learners can:

- Explain why environment configuration must be versioned as part of the release process.
- Distinguish application configuration, environment-specific configuration, deployment parameters, dynamic configuration, and secrets.
- Design configuration organization with clear data sources, environment separation, and precedence rules.
- Validate configuration using schemas, data types, value ranges, cross-field constraints, and dependency checks.
- Verify configuration before deployment, at application startup, and during runtime operations.
- Detect configuration drift, trace the running revision, and restore configuration when needed.
- Integrate configuration management into CI/CD pipelines with proper evidence and access controls.

## 1. Why Must Configuration Be Managed Like Source Code?

Configuration determines how an application behaves in each environment. The exact same artifact may connect to different databases, use different endpoints, toggle different features, and receive different resource limits depending on configuration.

For instance, an API service may use a local database in development, a dedicated database in integration or staging, and a production database with separate access controls and backup policies. A payment provider may run in sandbox mode during tests while hitting a live endpoint in production. A feature flag may be enabled only for a subset of users during a rollout.

If configuration is edited manually on servers or passed through multiple untracked channels, the team struggles to answer:

- Which configuration is the service currently running?
- Who changed a value and when?
- Was the current value validated before being applied?
- How do staging and production differ?
- Can the previous configuration be restored?
- Does the running configuration match the approved configuration?

Versioning configuration gives every change a history, a review trail, comparability, and recoverability. Validation catches errors before misconfiguration causes runtime incidents.

A principle to uphold:

> Configuration is part of the release state. You must know which version was applied, validate it before use, and maintain traceability and recoverability.

This does not mean every value belongs in Git. Secrets must be managed via a secret manager or an equivalent protective mechanism. What matters is that both regular configuration and secret references remain traceable without exposing sensitive values.

## 2. Distinguishing Configuration Categories

Before choosing storage and versioning strategies, classify configuration by role and sensitivity.

| Category | Examples | Recommended management approach |
|---|---|---|
| Application defaults | Default timeout, default retry count | Store alongside source code or artifact |
| Environment configuration | Database host, endpoints, log level | Config repository, manifests, or environment store |
| Deployment configuration | Replicas, resource limits, ports, volumes | Versioned IaC, Helm values, or manifests |
| Runtime/dynamic configuration | Feature flags, business thresholds, runtime-mutable parameters | Versioned config service or feature management system |
| Secrets | Passwords, API tokens, private keys | Secret manager; never store plaintext in repositories |
| Build configuration | Build parameters, toolchain, packaging profiles | Pipeline as code and governed build configuration |

Further distinguish:

- **Build-time configuration:** used when creating the artifact. Changes may alter artifact contents.
- **Deploy-time configuration:** used when deploying the artifact, such as replicas, ports, or resource limits.
- **Runtime configuration:** read by the application while running, changeable without rebuilding the artifact if supported by the system.

This classification clarifies which changes require a rebuild, which require only a redeployment, and which can be updated dynamically under policy.

## 3. Configuration Needs a Source of Truth and Owners

A system may receive configuration from files in a repository, environment variables, command-line arguments, a secret manager, a config service, Kubernetes ConfigMaps, Helm values, or parameters supplied by the deployment platform.

Without defining which source is authoritative for each field, values can be overridden unpredictably. During incident investigation, an engineer might inspect a Git file while the running application actually receives a value from an environment variable or config service.

Map out configuration ownership:

| Group | Recommended source of truth | Owner |
|---|---|---|
| Application defaults | Configuration file in source | Development team |
| Environment-specific values | Config repository or environment store | Service / platform owner team |
| Infrastructure and deployment | IaC or manifest repository | Platform/DevOps |
| Secrets | Secret manager | Security team or delegated owner |
| Feature flags | Feature management service | Product/service owner |
| Release rules | Policy repository or policy engine | Release/platform governance |

Each configuration field should have a clear owner, especially when it affects security, cost, or business behavior. Avoid situations where multiple teams modify the same value without clear final accountability.

Also define who has read access, who has modification rights, and who is authorized to apply configuration to production. Permission to edit a configuration file and permission to deploy configuration can be separate privileges.

## 4. Organizing Configuration by Environment

Configuration can be organized in several ways:

- A dedicated configuration repository shared across multiple services.
- A configuration directory within each service's repository.
- Helm charts and per-environment values files.
- IaC modules paired with governed input variables.
- A config service serving revisions to applications at runtime.

Whichever option you choose, avoid duplicating entire configurations into nearly identical copies. When a shared value needs updating, editing multiple files invites divergence.

An illustrative layout:

~~~text
config/
├── base/
│   ├── application.yml
│   └── logging.yml
├── environments/
│   ├── dev/
│   │   └── values.yml
│   ├── staging/
│   │   └── values.yml
│   └── production/
│       └── values.yml
├── schema/
│   └── application.schema.json
└── policies/
    └── production-policy.yml
~~~

In this model, `base` holds shared default values; `environments` holds intentional differences; `schema` describes structure and constraints; and `policies` holds additional rules for sensitive environments.

This is only one organizational pattern. Projects may use Helm, Kustomize, Spring profiles, or a config service. What matters is that merge rules and precedence sources are explicitly documented, verifiable, and reproducible.

Never copy real secrets into environment directories. Repositories should contain only reference names or safe placeholders.

## 5. Versioning Configuration

Configuration can be versioned via Git commits, tags, config service revisions, or an immutable configuration artifact.

A configuration version should answer:

- What content changed.
- Who authored and reviewed the change.
- When the change occurred.
- Which services and environments were affected.
- Which schema or policy version validated it.
- Which version is currently deployed.
- Whether rolling back to a previous revision is possible.

### 5.1. Using Git to manage configuration

Git works well for text-based configuration containing no secrets. Routing every change through a pull request provides review, discussion, and history.

A basic workflow:

1. Create a branch for the configuration change.
2. Edit the relevant files.
3. Run formatting, schema validation, and policy checks.
4. Inspect diffs to identify affected environments and services.
5. Obtain owner review.
6. Merge into the governed configuration branch.
7. Pipeline deploys the approved revision.
8. Record the active revision in the target environment.

Never edit production configuration directly on a server and forget to update the repository. Doing so creates drift: actual state diverges from the governed source of truth.

### 5.2. Configuration version and application version

Do not assume the application version represents the configuration version. An artifact can stay unchanged while configuration changes multiple times.

Record separately:

- Application version or artifact digest.
- Configuration revision.
- Deployment manifest revision.
- Secret reference/version metadata.
- Environment revision, if supported by the platform.

This lets investigators determine which application and configuration combination produced the observed behavior.

### 5.3. Immutable configuration and change history

An applied revision should allow retrieving its exact contents. If a config service exposes only current values without revision history, reproducing past states becomes difficult.

For sensitive configuration, store snapshots with secrets stripped or store only version references. Never store plaintext secrets in Git history, build logs, or deployment metadata.

## 6. Precedence Rules When Merging Configuration

An application may receive values from multiple sources. For example:

1. Default values in the application file.
2. Profile-specific configuration files.
3. Environment variables.
4. Command-line arguments.
5. Config service or platform-supplied parameters.

Actual order depends on the framework and how the application is configured. Never assume every platform uses the exact same precedence.

Explicitly define:

- Which source is allowed to override which source.
- Which fields may only change via the config repository.
- Which fields may only be supplied by a secret manager.
- Whether command-line overrides are permitted in production.
- Whether missing values fall back to defaults, raise errors, or block startup.
- How maps, lists, and nested objects are merged.
- How null values or empty strings are handled.

For example, if the base file sets `request-timeout` to 3 seconds, staging sets 5 seconds, and an environment variable sets 10 seconds, the application needs deterministic rules defining which source wins. Otherwise, the same Git file can produce different behavior depending on how it is deployed.

Include a render or resolve configuration step so the pipeline can inspect the final resolved configuration before applying it. Whenever possible, store a fingerprint or revision of the resolved configuration for traceability.

## 7. Multi-Layer Configuration Validation

A YAML or JSON file parsing cleanly does not mean the configuration is valid. Configuration must pass through multiple validation layers.

### 7.1. Syntax validation

Confirm files parse cleanly with no formatting errors:

- Valid YAML/JSON.
- No duplicate keys if parsers could handle them ambiguously.
- Proper character encoding.
- No unexpected structures.
- Templates render into valid output.

Syntax is the first layer, catching only structural formatting errors.

### 7.2. Schema and data type validation

Schemas specify allowed fields, required fields, data types, and nested structures.

For example, a schema might require:

- `port` is an integer between 1 and 65535.
- `replicas` is a positive integer.
- `logLevel` accepts only `DEBUG`, `INFO`, `WARN`, or `ERROR`.
- `database.url` is a URI-formatted string.
- `featureFlags` is a boolean map.
- `timeout` follows a valid duration format.

Schemas catch errors like `replicas` receiving the string `"three"` or misspelled field names.

### 7.3. Value range validation

A correctly typed value can still be invalid.

Examples:

- Timeout equal to 0 or negative.
- Replicas exceeding environment quotas.
- Retry count excessively large.
- Log level outside the allowed list.
- Connection pool larger than resource limits.
- URL pointing to an unauthorized endpoint.

Value ranges must reflect both application logic and target environment capacity.

### 7.4. Cross-field constraint validation

Some values are only valid in combination with other values.

Examples:

- If `tls.enabled` is true, certificate references and trust configuration must exist.
- If `payment.mode` is production, the endpoint must belong to the production allowlist.
- If `autoscaling.enabled` is true, min replicas must not exceed max replicas.
- If a feature requiring a message broker is enabled, broker endpoints and credential references must be configured.
- If automatic migrations are enabled, the database identity must target an allowed environment.

These constraints typically require custom validation logic, as schemas alone cannot express full business relationships.

### 7.5. Semantic and dependency validation

Configuration may be structurally valid yet fail in the real environment.

Examples:

- Database host fails DNS resolution.
- Secret reference does not exist.
- Service account lacks access permissions.
- TLS certificate has expired.
- Endpoint fails to respond.
- Queue or topic has not been created.
- Database schema version is incompatible with the application.

These checks may need to run in a test environment or during a pre-deploy readiness step. Avoid running every live connectivity check while parsing files, as some dependencies may be temporarily unavailable; distinguish configuration errors from infrastructure outages.

### 7.6. Policy validation

Policy validation confirms configuration complies with operational and security requirements.

Examples:

- Production must not enable debug mode.
- Production databases must not use system-wide admin accounts unnecessarily.
- TLS must be enabled for public endpoints.
- Containers must not run privileged unless permitted by policy.
- Resource requests/limits must stay within bounds.
- CORS must not allow wildcards on sensitive APIs.
- Sandbox endpoints must not be used in production.

Policies should be checked automatically in CI with explainable results.

## 8. Example Schema and Valid Configuration

Example application configuration:

~~~yaml
server:
  port: 8080
  shutdown: graceful

application:
  environment: staging
  log-level: INFO

database:
  url: jdbc:postgresql://db-staging.internal:5432/orders
  connection-timeout: 5s
  maximum-pool-size: 20
  credentials:
    secret-reference: orders-db-staging

features:
  checkout-enabled: true
  new-pricing-enabled: false
~~~

Illustrative JSON Schema:

~~~json
{
  "type": "object",
  "required": ["server", "application", "database", "features"],
  "properties": {
    "server": {
      "type": "object",
      "required": ["port"],
      "properties": {
        "port": {
          "type": "integer",
          "minimum": 1,
          "maximum": 65535
        }
      },
      "additionalProperties": false
    },
    "application": {
      "type": "object",
      "required": ["environment", "log-level"],
      "properties": {
        "environment": {
          "enum": ["dev", "staging", "production"]
        },
        "log-level": {
          "enum": ["DEBUG", "INFO", "WARN", "ERROR"]
        }
      }
    },
    "database": {
      "type": "object",
      "required": ["url", "credentials"],
      "properties": {
        "url": {
          "type": "string",
          "minLength": 1
        },
        "credentials": {
          "type": "object",
          "required": ["secret-reference"],
          "properties": {
            "secret-reference": {
              "type": "string",
              "minLength": 1
            }
          }
        }
      }
    },
    "features": {
      "type": "object",
      "additionalProperties": {
        "type": "boolean"
      }
    }
  }
}
~~~

This schema illustrates structure and a subset of constraints only. Real systems should add rules for timeouts, connection pools, URL formats, environment-specific allowed fields, and cross-field rules.

Do not treat a schema as the sole check for endpoints, access permissions, or secrets. Environment-dependent conditions require dedicated validation steps.

## 9. Environment Variables and Their Limitations

Environment variables are a common mechanism for passing configuration to processes or containers. They are convenient because they can vary per environment without modifying source code.

Example:

~~~bash
APP_ENV=staging
SERVER_PORT=8080
LOG_LEVEL=INFO
DATABASE_URL=jdbc:postgresql://db-staging.internal:5432/orders
DATABASE_SECRET_REF=orders-db-staging
~~~

However, environment variables have limitations:

- Most values arrive in the process as strings and must be parsed and validated.
- Variable names can diverge across local, container, and CI if unstandardized.
- Values can leak into logs if scripts dump the full environment.
- Some platforms expose variables through process metadata or deployment specs whose read permissions require restriction.
- Updating environment variables usually requires a restart or rollout for processes to pick up new values.
- Environment variables can be overridden by other configuration sources depending on framework precedence.

Standardize variable names, post-parse data types, default values, and missing-value behavior. For required configuration, the application should fail clearly at startup instead of silently falling back to an unsafe default.

Avoid passing secrets via environment variables when the platform provides better-suited secret mounts or workload identities. If environment variables must carry secrets, understand how processes, runners, and logs handle them.

## 10. Managing Secrets Separately from Regular Configuration

Secrets include passwords, API tokens, private keys, certificate material, and other credentials. These values require stronger protection than non-sensitive configuration.

Recommended practices:

1. Store secrets in a secret manager or approved secure store.
2. Keep only reference names or non-sensitive metadata in repositories.
3. Scope secret access by workload, job, and environment.
4. Use least privilege and short-lived credentials whenever possible.
5. Never write plaintext secrets into logs, artifacts, test reports, or approval snapshots.
6. Maintain rotation and revocation procedures.
7. Track secret versions or metadata when traceability is needed.
8. Never expose production secrets to jobs running untrusted pull requests.

A configuration file might contain:

~~~yaml
database:
  credentials:
    secret-reference: orders-db-production
~~~

The application or deployment platform fetches the value from the secret manager using its granted identity and permissions. This reference pattern allows versioning configuration without placing secrets into Git.

When a secret rotates, define how the application receives the new value: restart, reload, sidecar, volume update, or secret manager API. Never assume every process picks up rotated secrets automatically and immediately.

## 11. Validating Configuration in CI/CD Pipelines

Configuration should be validated before affecting shared environments or production.

A reference pipeline:

~~~mermaid
flowchart TD
    A["Configuration pull request"] --> B["Parse and format check"]
    B --> C["Schema validation"]
    C --> D["Type, range, and cross-field checks"]
    D --> E["Policy validation"]
    E --> F["Resolve environment configuration"]
    F --> G["Render manifest / deployment plan"]
    G --> H["Review diff and impact"]
    H --> I{"Required checks passed?"}
    I -- "No" --> X["Block merge and report errors"]
    I -- "Yes" --> J["Merge revision"]
    J --> K["Deploy to test environment"]
    K --> L["Runtime validation and smoke checks"]
    L --> M{"Behaving properly?"}
    M -- "No" --> N["Stop rollout / restore"]
    M -- "Yes" --> O["Promote revision per policy"]
~~~

Validation steps can include:

| Step | Scope | Evidence |
|---|---|---|
| Parse | Check YAML/JSON/template syntax | Parse result |
| Schema | Check fields, types, and structure | Schema validation report |
| Semantic | Check value ranges and field relationships | Validation result |
| Policy | Check security and operational rules | Policy report |
| Resolve | Merge base, environment, and overrides | Resolved config fingerprint |
| Render | Generate manifests or deployment plans | Rendered output/diff |
| Test | Run tests with intended configuration | Test report |
| Deploy | Apply approved revision | Deployment ID and config revision |
| Verify | Confirm actual configuration and behavior | Runtime config revision, health result |

If configuration is rendered from templates, validate both the templates and the rendered output. A valid template can still produce an invalid manifest when input data is missing or mistyped.

Never let pipelines deploy configuration merely because files parse cleanly. Enforce schemas, policies, and target-environment compatibility checks.

## 12. Validating Configuration at Startup and Runtime

CI validation does not completely replace runtime validation. Final configuration can still be modified by secret managers, environment variables, config services, or deployment platforms.

### 12.1. Startup validation

When the application starts, verify:

- Required fields have values.
- Values match expected types and permitted ranges.
- URIs, durations, and lists parse cleanly.
- Interdependent configuration pairs satisfy constraints.
- Secret references resolve under granted permissions.
- Necessary dependencies are reachable or in a valid state.

If required configuration is invalid, the application should fail fast with a message identifying the failing field or rule. Never log sensitive values.

### 12.2. Readiness and health checks

Not every dependency must connect during config parsing. Readiness checks can verify the application is ready to serve traffic.

Examples:

- Database is reachable and schema is compatible.
- Message broker is accessible.
- Certificates are valid and unexpired.
- Dependency endpoints belong to the allowlist and respond as expected.
- Runtime config revision loaded cleanly.

Health checks should distinguish configuration errors from transient dependency outages to aid diagnostics.

### 12.3. Dynamic configuration

Some values can change while the application runs, such as feature flags or business thresholds. When supporting dynamic configuration, define:

- Which revision the process is actively using.
- Whether configuration applies atomically or piecemeal.
- Whether loading failures preserve the old configuration or halt operation.
- Whether validation runs before applying changes.
- Whether certain fields still require a restart.
- How to observe and revert to the previous revision.

Avoid applying configuration fields piecemeal if intermediate states can violate invariants. Better to resolve and validate the entire new configuration, then switch to the new revision consistently.

## 13. Detecting Configuration Drift

Configuration drift occurs when an environment's actual configuration differs from governed or approved configuration.

Common causes:

- Operators edit settings directly on servers or clusters.
- Another pipeline applies an outdated manifest.
- A config service is updated outside the review process.
- Chart or IaC module defaults change unexpectedly.
- A secret reference switches to a new version.
- An emergency fix is not synced back into the repository.

Drift can cause production to diverge from staging even while running the exact same artifact. During an incident, reproducing behavior becomes difficult.

Drift can be detected by:

1. Resolving desired configuration from the approved revision.
2. Collecting actual state from the environment or config service.
3. Normalizing both configuration sets using the same rules.
4. Comparing fields and fingerprints.
5. Classifying differences by impact severity.
6. Alerting or generating a remediation request.
7. Recording the actor or workload behind the change if platform audit logs provide it.

Do not blindly overwrite every drift instance without classification. Temporary approved emergency changes may exist. Maintain a break-glass process: document the reason, actor, expiration, and require reconciling configuration back to the source of truth.

In GitOps-managed environments, controllers continuously compare desired state against actual state. Reconciliation policies must be clear: auto-remediate drift, alert only, or require operator intervention.

## 14. Promoting Configuration Across Environments

A release flow typically promotes the same artifact across dev, staging, and production. Environment configurations may differ, yet they should be governed and validated under the same contract.

Two common models:

**Single shared revision with environment overlays:** use base configuration plus overlays for dev, staging, and production. The pipeline resolves final configuration for each environment.

**Separate revisions per environment:** each environment maintains its own independently managed and approved revision. This fits when differences or change permissions across environments are substantial.

Whichever model is used, preserve:

- Unified schemas and validation rules.
- Explicitly declared environment differences.
- Dedicated review and protection for production values.
- Artifact identification independent of config revisions.
- Test evidence tied to both artifact and configuration used.
- Traceable promotion or rollback mechanisms for configuration.

Never copy a staging file straight to production and manually tweak a few values on the cluster. Generate production revisions from the governed source, render, and inspect diffs before applying.

## 15. Configuration Rollback and Handling Emergency Changes

Misconfiguration can trigger incidents even when the artifact has not changed. Therefore, rollback is not merely reverting to a previous image.

A configuration recovery plan must identify:

- The most recent known-good configuration revision.
- Which artifact is compatible with that revision.
- Which secret references/versions remain valid.
- Whether irreversible migrations or state changes occurred.
- How to apply the previous revision and verify recovery.
- Who is authorized to execute the rollback.

Not every old configuration is safe to restore. Old credentials may have been revoked; old endpoints may be retired; database schemas may have been upgraded. Verify compatibility before rolling back.

For emergency changes, allow policy-governed break-glass procedures:

1. Identify the incident and minimum required change scope.
2. Record actor, justification, and ticket or incident ID.
3. Apply the change using scoped privileges.
4. Verify behavior and monitor closely.
5. Create an official commit or revision reflecting the modified state.
6. Conduct post-incident review and remove temporary exceptions.

Break-glass should never become a routine configuration channel. If an emergency change is kept, it must be reconciled back into the source of truth to prevent prolonged drift.

## 16. Example Pipeline for Validating and Deploying Configuration

The YAML below illustrates general logic rather than exact syntax for a specific CI/CD platform:

~~~yaml
configuration_pipeline:
  trigger:
    - pull_request
    - merge_to_main

  validate:
    steps:
      - parse_configuration
      - validate_schema
      - validate_types_and_ranges
      - validate_cross_field_constraints
      - validate_environment_policy
      - scan_for_plaintext_secrets

  resolve:
    steps:
      - load_base_configuration
      - load_environment_overlay
      - resolve_allowed_overrides
      - resolve_secret_references
      - create_config_fingerprint

  preview:
    steps:
      - render_deployment_manifest
      - compare_with_current_environment
      - publish_diff_and_validation_report

  deploy:
    requires:
      - validation_passed
      - policy_passed
      - approval_if_required
    steps:
      - apply_versioned_configuration
      - record_config_revision
      - run_startup_and_readiness_checks
      - verify_effective_configuration

  on_failure:
    steps:
      - stop_rollout
      - retain_previous_known_good_revision
      - record_failure_and_changed_fields
~~~

The pipeline must ensure sensitive data never appears in published reports or diffs. Display secret references and version metadata instead of actual values.

If configuration loads from multiple sources, the resolve step must match runtime precedence rules. If the pipeline and the application merge configuration differently, CI validation will not reflect the actual values the application receives.

## 17. Common Anti-Patterns

| Anti-pattern | Risk | Improvement |
|---|---|---|
| Editing directly in production | No history and invites drift | Route changes through governed sources and pipelines |
| Missing schema | Wrong types or missing fields discovered only at runtime | Add schema validation |
| Defaulting on every config error | Application may run with dangerous values | Fail fast on required fields |
| Unclear multiple override sources | Impossible to tell where effective values originate | Define precedence and generate resolve reports |
| Storing plaintext secrets in Git | Credential exposure and difficult revocation | Use secret managers and references |
| Sharing one file across all environments | Misconfigured endpoints or permissions | Use base plus environment overlays |
| Validating only source files | Misses errors introduced after rendering or merging | Validate resolved configuration |
| Not recording config revisions | Hard to reproduce production behavior | Link revisions/fingerprints to deployments |
| Auto-fixing all drift blindly | May overwrite valid emergency fixes | Classify, audit, and reconcile per policy |
| Rolling back image while keeping broken config | Service continues failing | Restore compatible artifact/config pairs |
| Applying dynamic config piecemeal | Inconsistent intermediate states | Validate whole config and apply atomically |

## 18. Configuration Versioning and Validation Checklist

Before applying configuration to shared environments or production, verify:

- [ ] Each configuration category has a clear source of truth and owner.
- [ ] Build-time, deploy-time, and runtime configurations are distinguished.
- [ ] Configuration revisions or fingerprints are traceable.
- [ ] Differences across environments are intentionally declared.
- [ ] Precedence and merge rules are explicitly documented.
- [ ] Configuration is parsed and schema-validated.
- [ ] Data types, value ranges, and cross-field constraints are verified.
- [ ] Production policies are checked automatically.
- [ ] Secrets are absent from Git, logs, and artifacts in plaintext.
- [ ] Secret references and version metadata are securely managed.
- [ ] Resolved/rendered configuration is validated.
- [ ] Startup validation and readiness checks reflect actual runtime conditions.
- [ ] Runtime config revisions are observable.
- [ ] Configuration drift detection and handling exist.
- [ ] Audit trails capture changes and break-glass actions.
- [ ] A known-good revision and compatible rollback plan exist.
- [ ] Artifact digests and config revisions are recorded separately in deployment evidence.

## 19. Self-Assessment Exercise

An API service runs across three environments: dev, staging, and production. The application uses `application.yml`, environment variables, and a config service. During a release:

- Staging runs cleanly, but production fails to connect to the database.
- The Git config file has the right database host, yet an old environment variable still overrides it.
- An operator modified a timeout directly on the cluster during an incident.
- The config service revision was not recorded in the deployment record.
- A secret was recently rotated, yet the application continues holding old connections.

Analyze:

1. Which source is supplying the final database host value?
2. How should precedence across configuration sources be determined and documented?
3. What checks should exist in schema, range, and runtime validation?
4. Why is validating Git files alone insufficient?
5. How should the emergency timeout fix be reconciled back to the source of truth?
6. Which revisions must the deployment record store?
7. What reload or restart mechanisms does secret rotation require?
8. How can drift across Git, the config service, and the cluster be detected?
9. If rollback is needed, how must compatibility across artifact, config revision, and secret version be verified?

A sound design must pinpoint where every final value originates, who owns it, how it was validated, and which revision the application is actually running.

## Conclusion

Versioning configuration lets teams see which changes were reviewed, which revision is running, and how to recover when failures occur. Validation must progress from syntax, schemas, and data types to value ranges, cross-field constraints, dependencies, and environment policies.

In CI/CD, resolve configuration under clear precedence rules, validate rendered output, protect secrets through dedicated mechanisms, and record config revisions alongside artifacts in deployment evidence. When drift is detected, classify and reconcile it per policy; when rolling back, confirm older configuration remains compatible. Together, these practices allow the exact same artifact to run consistently across environments with verifiable, traceable configuration.

# Info Endpoint in Spring Boot

When operating a Spring Boot service, the support team often needs to know which version the application is running, when the artifact was built, which commit was deployed, which team owns the service, and where operational documentation lives. If this information only appears in startup logs or requires accessing individual containers, verifying deployments and handling incidents becomes slow.

The **Info endpoint** in Spring Boot Actuator provides a single access point to publish metadata describing the application. The endpoint is typically accessible at /actuator/info when enabled and exposed over the web. Data can come from Spring Boot-provided InfoContributor beans, build/git metadata generated during the build, or custom contributors.

The Info endpoint serves identification and deployment description; it is not an endpoint for checking request-serving capability. The Health endpoint returns health status from health indicators, whereas the info endpoint returns metadata actively published by the application. Do not include secrets, personal data, credentials, or sensitive runtime data in the info payload.

This lesson belongs to the **Actuator and Management** chapter of the **SPRING_BOOT_OBSERVABILITY** module. The module guides setting up observability for Spring Boot using Micrometer Observation, metrics, logs, and distributed tracing; learning context propagation, tags/cardinality, exporters, sampling, and signal correlation to investigate errors, latency, and application behavior in production environments. This lesson focuses on the Info endpoint, metadata sources, configuration, security, and operational usage.

## Learning Objectives

After this lesson, you will be able to:

1. Explain the purpose of the Actuator Info endpoint.
2. Distinguish info from health, metrics, and env endpoints.
3. Enable and expose the info endpoint via Spring Boot configuration.
4. Provide metadata from build information and Git information.
5. Create a custom InfoContributor for service metadata.
6. Understand management.info.* properties and how to enable contributors.
7. Design a stable, useful payload for deployment identification.
8. Protect the endpoint using exposure policies, authentication, and network controls.
9. Test output, contributors, and behavior when metadata is missing.
10. Integrate the info endpoint into deployment verification and troubleshooting.

## 1. What Is the Info Endpoint?

The Info endpoint is an Actuator endpoint that provides descriptive information about the application. It generally does not perform measurements or dependency checks; its content is supplied by contributors.

Example response:

```json
{
  "app": {
    "name": "checkout-service",
    "description": "Checkout API",
    "version": "2.4.1"
  },
  "build": {
    "artifact": "checkout-service",
    "version": "2.4.1",
    "time": "2026-11-22T02:10:00Z"
  },
  "git": {
    "branch": "release/2.4",
    "commit": {
      "id": "a1b2c3d4",
      "time": "2026-11-22T01:55:00Z"
    }
  }
}
```

This is an illustrative structure. The actual payload depends on enabled contributors and metadata present in the artifact. Not every application has app/build/git sections.

### 1.1. When to Use the Info Endpoint?

- Verifying the running version after a deployment.
- Comparing the built commit against the expected commit.
- Supporting incident triage with stable metadata.
- Exposing service name, documentation links, or approved ownership metadata.
- Automating deployment smoke checks and inventory.

The Info endpoint is useful for metadata with a relatively stable lifecycle. Do not use it to replace metrics, health checks, or business data queries.

### 1.2. Info Is Not Health

| Endpoint | Core Question | Content |
|---|---|---|
| /actuator/info | Which artifact/deployment is this application? | Metadata published by contributors |
| /actuator/health | Is the application healthy and ready? | Health status and components |
| /actuator/metrics | Which quantities can be measured? | Meter names, measurements, and tags |
| /actuator/env | Which property sources/configs are active? | Controlled environment/configuration view |

An application can return info successfully while health is DOWN; conversely, health can be UP even if the info payload is empty. Do not use HTTP 200 from info as a readiness check.

## 2. Enabling Actuator and Exposing the Info Endpoint

You need the Spring Boot Actuator dependency. With Gradle:

```groovy
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-actuator")
}
```

Endpoint availability and web exposure are two distinct concepts. An endpoint must be enabled if previously disabled, and must be exposed over the web if HTTP access is desired.

Example:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info
```

If include is configured elsewhere, merge the list according to application policy. Do not expose every endpoint just to make info work.

Access:

```http
GET /actuator/info
```

Context path, management port, and base path can make the actual URL differ from the example. If the management server uses a separate port, the endpoint will not reside on the main application port.

### 2.1. Enablement and Exposure

Access can be configured individually:

```yaml
management:
  endpoint:
    info:
      access: read-only
```

Property semantics vary across Spring Boot versions. In older versions, endpoint access may be managed via enabled/enabled-by-default. Check the documentation for your exact version. Exposure only determines which transport publishes the endpoint; it does not replace authorization.

### 2.2. Management Port and Base Path

```yaml
management:
  server:
    port: 8081
  endpoints:
    web:
      base-path: /manage
      exposure:
        include: health,info
```

The endpoint is then `/manage/info` on the management port. Separating the port does not protect the endpoint by itself; appropriate firewall/network policies and authentication are still required.

## 3. InfoContributor Architecture

Spring Boot builds the info response from `InfoContributor` beans. Each contributor adds a piece of data to the Info endpoint's builder.

| Source | Content | How Data Is Provided |
|---|---|---|
| Application contributor | Application-defined metadata | Custom bean |
| Build info | Artifact, group, name, version, build time | Build plugin generates build-info.properties |
| Git info | Branch, commit ID/time | Git properties file |
| Environment contributor | Selected properties | management.info.env.* |
| Java/System info | Runtime/build-related data per contributor | Properties per version |

Contributors can be auto-configured when dependencies and metadata resources are present. Inspect the actual response rather than assuming all contributors are always registered.

### 3.1. Aggregating Multiple Contributors

Each contributor writes to its own section/key. Avoid having multiple contributors use the same root key, which causes overwrites or confusing structures. Use clear namespaces such as app, build, git, runtime, or links.

### 3.2. Metadata Should Be Stable

The Info endpoint is often polled by deployment tooling or read manually. Keep key names and semantics stable across releases. If changing the schema, coordinate with consumers and automation.

## 4. Build Information

Spring Boot Maven/Gradle plugins support generating build info during the build; when the file is on the classpath, Actuator can publish the `build` section.

Gradle Kotlin DSL:

```kotlin
springBoot {
    buildInfo()
}
```

Gradle Groovy DSL:

```groovy
springBoot {
    buildInfo()
}
```

Exact syntax depends on the Spring Boot Gradle plugin version and build script. Build info is typically generated into `META-INF/build-info.properties` inside the artifact.

Information usually includes group, artifact, name, version, time, and additional properties configured by the build.

### 4.1. Build Time and Reproducible Builds

Build time is useful for identifying an artifact, but it can make two builds differ even from identical source. For reproducible builds, consider how the plugin generates timestamps and your pipeline policy. Do not use build time as the sole proof of source identity; combine commit ID and artifact digest.

### 4.2. Version from Build Metadata

Prefer the version recorded into the artifact by the build system. Do not infer the version arbitrarily from JAR filenames or environment variables if the pipeline already produces official metadata. If version is undeclared, an unknown value or omitted field may be returned.

## 5. Git Information

Spring Boot build plugins can generate a git properties file from repository metadata, after which `GitInfoContributor` publishes the details. With Gradle, configure a plugin/task to generate git properties based on your build setup. With Maven, Git properties usually require a supporting plugin such as `git-commit-id` plugin.

Git info can include branch, commit.id, commit.time, and author fields depending on configuration.

### 5.1. Full Commit ID or Abbreviated ID?

Full commit IDs identify revisions unambiguously. Abbreviated IDs are easier to read but can become ambiguous in large repositories. Choose a consistent format based on your deployment process.

### 5.2. Do Not Publish Sensitive Git Metadata

There is no need to publish commit author emails, commit messages, remote URLs with embedded credentials, or internal branch names to public users. Only include fields required for deployment verification and restrict the audience.

### 5.3. Git Metadata Does Not Replace Artifact Provenance

A commit ID indicates the source revision recorded in build metadata; it does not cryptographically prove the artifact was built from that source. Combine signed build attestations, SBOMs, artifact digests, and CI provenance when supply-chain verification is needed.

## 6. Environment Information Contributor

Spring Boot can provide `EnvironmentInfoContributor` to include selected properties in the info response. Configuration typically uses the `management.info.env` prefix.

Example:

```yaml
management:
  info:
    env:
      enabled: true
      prefix: "env"
      defaults:
        region: "ap-southeast-1"
        team: "commerce"
```

Property names and defaults support depend on the Spring Boot version. The environment contributor can read properties exposed per version rules; this does not mean the entire environment is exported.

### 6.1. Expose Only Allowlisted Metadata

Do not put all application properties, environment variables, or system properties into info. They can contain passwords, tokens, database URLs, internal hostnames, or secret references.

Prefer a custom InfoContributor with a fixed set of fields. If using the environment contributor, configure a specific allowlist and test that sensitive fields do not appear.

## 7. Creating a Custom InfoContributor

When metadata such as service name, owner team, documentation links, or API compatibility is needed, create an `InfoContributor` bean.

```java
@Component
class ApplicationInfoContributor implements InfoContributor {

    @Override
    public void contribute(Info.Builder builder) {
        builder.withDetail("app", Map.of(
                "name", "checkout-service",
                "description", "Checkout API",
                "owner", "commerce-platform"
        ));
    }
}
```

`Map.of` requires Java 9 or later. The illustrated values can be sourced from configuration/build metadata, exposing only approved fields.

### 7.1. Do Not Add Sensitive Data

Do not include credentials, tokens, private keys, database connection strings, customer data, or request contents in the Info endpoint. Info is often accessed by monitoring, deployment tooling, and multiple operations teams.

### 7.2. Fast Contributors with No Side Effects

`InfoContributor` is invoked when the endpoint builds its response. Do not call databases, remote APIs, or business services inside `contribute()`. Doing so slows the endpoint down and introduces dependency coupling. Metadata should already be available in memory/config/build resources.

### 7.3. Key Naming and Schema

Use meaningful, stable keys with clear namespaces:

```json
{
  "app": {
    "name": "checkout-service",
    "owner": "commerce-platform"
  },
  "links": {
    "runbook": "https://docs.example.invalid/runbooks/checkout"
  }
}
```

The URL is a placeholder. Do not include internal links if the endpoint's audience does not have access to those documents.

## 8. Info Properties and Contributor Configuration

`management.info.*` settings can enable/disable or adjust contributors depending on the Spring Boot version.

```yaml
management:
  info:
    build:
      enabled: true
    git:
      enabled: true
      mode: simple
    env:
      enabled: false
```

Property names, defaults, and git modes depend on version. Some versions support `simple`/`full` modes; `full` can publish more details. Enable only needed sections and understand the output fields.

### 8.1. Configuration from Build Plugins

If `build-info.properties` or `git.properties` is absent from the artifact, the contributor may not produce its section. Inspect the files inside the deployed artifact's JAR/classpath, not just the build script.

### 8.2. Profile-Specific Metadata

Avoid letting the info schema change drastically across profiles. If an environment name like dev/staging/prod is needed, use a standardized field. Do not include profile-specific secrets or all active profiles if doing so could reveal topology.

## 9. Securing the Info Endpoint

The Info endpoint is read-only, yet its metadata can still help an attacker fingerprint the system: version, branch, commit, dependency hints, and internal URLs.

- Expose only required endpoints.
- Apply authentication/authorization if the payload contains internal metadata.
- Restrict network access to the management port.
- Do not publish secrets or sensitive config values.
- Avoid Git details/author emails unless needed.
- Do not include internal runbook links for a public audience.
- Inspect the payload after every contributor change.
- Consider rate limiting and caching where appropriate.

### 9.1. Endpoint Exposure Is Not Authorization

Setting `include=info` only enables web exposure. Spring Security or the management security policy still decides who can call the endpoint. If the application lacks authentication, the endpoint may be public depending on deployment topology.

### 9.2. Separate Management Port

A separate management port separates administrative traffic from application traffic, but does not replace firewalls, Kubernetes NetworkPolicy, ingress rules, or authentication. Do not bind the management interface to a public network without controls.

### 9.3. Be Careful with Version Disclosure

Exact versions are helpful for deployment verification but also assist in fingerprinting the dependency stack. You can publish only the application version to broader audiences while keeping commit details within the management network.

## 10. Info Endpoint in Deployment Verification

Pipelines can call the info endpoint after a rollout and compare `app.name`, `build.version`, `git.commit.id`, environment/region, and artifact build identifiers.

Manual check example:

```bash
curl -sS http://localhost:8080/actuator/info
```

In a pipeline, parse the JSON and compare agreed-upon fields. If there are multiple replicas, query each pod or via service discovery to confirm all instances updated; a load balancer can route multiple requests to the same instance.

### 10.1. Rollout and Mixed Versions

During a rolling deployment, multiple versions can coexist temporarily. The Info endpoint helps distinguish responses from individual replicas if requests target instances directly or if metadata includes a standardized instance identity.

### 10.2. Does Not Replace the Deployment Controller

The endpoint only provides metadata. It does not determine whether a rollout succeeded per policy, does not control traffic, and does not replace readiness/liveness probes. Pipelines must combine health/readiness and replica inventory.

## 11. Testing InfoContributor and the Endpoint

### 11.1. Unit Testing Contributors

Invoke `contribute()` with an appropriate `Info.Builder` and assert the expected keys/values. The test has no side effects and calls no external services.

### 11.2. Integration Testing

Use a Spring Boot test with a web environment and the Actuator endpoint, calling `/actuator/info`. Assert HTTP status per security policy, app/build/git sections when contributors are enabled and metadata is present, custom fields matching the schema, absence of sensitive fields, and that contributors do not overwrite unrelated keys.

### 11.3. Testing the Built Artifact

Git/build metadata may exist in IDE tests yet be missing from the packaged artifact if the build task did not run. Test the final JAR or smoke test the container after build to verify metadata is packaged.

### 11.4. Testing Security

Test anonymous and authenticated requests per policy. Check management port/network routing in staging; a read-only endpoint does not mean public-safe.

## 12. Diagnosing the Info Endpoint

| Symptom | Possible Cause | How to Check |
|---|---|---|
| /actuator/info returns 404 | Endpoint not exposed or different base path/port | Exposure, management port/base path |
| Empty response | No contributors or metadata resources | Build/git files and custom beans |
| Missing build section | build-info.properties not generated/packaged | Build plugin and JAR contents |
| Missing git section | Git metadata task did not run | git.properties in artifact |
| Git section missing fields | Mode/include policy | management.info.git settings/version |
| Custom key not appearing | Bean not scanned or incorrect contribute | Application context and contributor test |
| Key overwritten | Multiple contributors using same key | Namespaces and contributor inventory |
| Endpoint leaks secret | Overly broad environment contributor/custom payload | Allowlist and response security test |
| Info works locally, missing in container | Different artifact or resource excluded | Packaged JAR/container |
| HTTP 401/403 | Security policy requires permissions | Role/authority and management security |
| Pipeline sees old version | Load balancer routes to old replica | Query individual instances/pods and rollout state |

### Investigation Procedure

1. Identify the management port, base path, and web exposure.
2. Check endpoint access/enablement for your Spring Boot version.
3. Call info directly against a single instance.
4. Inspect registered contributor beans.
5. Inspect build-info/git properties in the deployed artifact.
6. Verify `management.info.*` and active profiles.
7. Inspect the response for overwritten or missing keys.
8. Audit the payload for secrets or internal metadata.
9. Check security and network policies.
10. Compare across replicas if a rollout is in progress.

## 13. Anti-Patterns to Avoid

| Anti-Pattern | Consequence | Proper Approach |
|---|---|---|
| Using info endpoint as health check | Metadata does not reflect readiness | Use health/readiness |
| Exposing all Actuator endpoints | Increases attack surface | Allowlist needed endpoints |
| Publishing entire environment | Leaks internal secrets/config | Allowlist or custom contributor |
| Contributor calling database/HTTP | Slow info and dependency coupling | Pre-built/config metadata |
| Publishing commit author email/internal URLs | Leaks internal information | Expose only necessary fields |
| Using build time as sole source identity | Does not verify source/artifact | Commit ID + artifact digest/provenance |
| Assuming every build has git.properties | Payload differs between local and CI | Generate/test metadata in build |
| Key names changing by profile | Breaks automation compatibility | Stable schema |
| Treating separate management port as sufficient security | Endpoint can still be reached | Network policy + authentication |
| Using info to prove all replicas rolled out | Load balancer may repeatedly hit same pod | Check each instance |

## 14. Production Checklist

1. **Purpose:** does the payload contain only application/deployment descriptive metadata?
2. **Enablement:** is the endpoint enabled per version and policy?
3. **Exposure:** is info exposed only over needed transports?
4. **Security:** are authentication/authorization and network controls appropriate?
5. **Build:** is build info generated in the pipeline?
6. **Git:** are required commit ID/branch/time included in the artifact?
7. **Custom contributor:** are keys stable without calling external dependencies?
8. **Environment:** are only approved properties allowlisted?
9. **Secrets:** are passwords, tokens, credentials, and PII absent?
10. **Audience:** is public vs. internal metadata separated?
11. **Schema:** are key names and types stable across releases?
12. **Packaging:** is metadata present in the deployed artifact/container?
13. **Testing:** are unit, integration, packaged artifact, and security tests in place?
14. **Deployment:** does the pipeline compare expected build/commit?
15. **Replicas:** does rollout verification check sufficient instances?
16. **Operations:** does a runbook explain how to read info and handle missing metadata?

## 15. Self-Assessment Questions

**Q1.** What need does the Info endpoint address?

**Hint:** Providing metadata that identifies the running application/artifact/deployment, such as app name, version, build, and commit information.

**Q2.** How does the Info endpoint differ from the Health endpoint?

**Hint:** Info describes metadata; health reports the health status of the application/components.

**Q3.** Why does an endpoint need both enablement and exposure?

**Hint:** Enablement controls whether the endpoint is active; exposure controls whether it is published over web/JMX or another transport.

**Q4.** Where is build info typically generated?

**Hint:** In the build pipeline via the Spring Boot Maven/Gradle plugin and packaged as a metadata resource.

**Q5.** What does Git info help investigate?

**Hint:** Identifying the branch/commit recorded in the running artifact to verify deployments.

**Q6.** Why should you not expose all environment properties?

**Hint:** They can contain secrets, tokens, credentials, and internal topology.

**Q7.** Should a custom InfoContributor call the database?

**Hint:** No. Contributors should be fast, side-effect-free, and rely only on already available metadata.

**Q8.** Why can local build metadata differ from a production container?

**Hint:** Build tasks or resource packaging in the pipeline may omit generating or packaging build-info/git properties.

**Q9.** Does HTTP 200 from the info endpoint prove the service is ready?

**Hint:** No. Use health/readiness checks to assess readiness to serve traffic.

**Q10.** How do you verify every replica has deployed the same version?

**Hint:** Query metadata from each instance/pod or deployment inventory; a load balancer can repeatedly route to the same replica.

## Conclusion

**The Info endpoint provides stable metadata to identify running applications and artifacts.** Spring Boot Actuator can aggregate build information, Git metadata, selected environment properties, and data from custom InfoContributors. Enable and expose the endpoint intentionally, maintain a consistent schema, publish only necessary fields, and protect management access. Use build/commit metadata to assist deployment verification, combined with health/readiness and per-replica checks to confirm rollouts. Contributors should be fast, avoid external dependency calls, and never leak secrets or internal information.
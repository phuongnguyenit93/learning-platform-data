# Upgrade Checklist Based on Dependencies, Configuration, Startup, and Testing

Upgrading Spring Boot is a change that affects multiple layers of an application. A new Boot release can pull in updated versions of Spring Framework, Spring Security, Spring Data, Hibernate, Jackson, Micrometer, the servlet container, and numerous transitive dependencies. At the same time, the Java baseline, default configuration values, property names, auto-configurations, and APIs may also change.

Therefore, an upgrade cannot be evaluated merely by bumping a version in the build file and seeing the project compile. You must verify that the dependency graph is consistent, configuration remains valid, the application context starts cleanly, critical features preserve expected behavior, and the actual packaged artifact runs properly in the deployment environment.

In the **Versioning and Extension** chapter of *Spring Boot Fundamentals*, this lesson presents an upgrade checklist organized across four main axes:

1. **Dependencies:** versions, BOM, release trains, scopes, transitive dependencies, and compatibility.
2. **Configuration:** properties, profiles, security, server, persistence, logging, and changed defaults.
3. **Startup:** component scanning, auto-configuration, bean wiring, migrations, external connections, and lifecycle.
4. **Testing:** compilation, unit, context, integration, regression, packaged artifact, and smoke tests.

The checklist follows the lifecycle of the work: capturing a baseline, planning, updating dependencies, migrating code/config, verifying startup, running tests, packaging, and rolling out safely. You can use it for patch/minor upgrades or when planning a major-version jump; scale verification depth in proportion to the magnitude of change.

## 1. Pre-Upgrade Principles

A thorough upgrade answers four questions:

- **What changed?** Which versions, dependencies, properties, APIs, and defaults changed?
- **What is impacted?** Which modules, services, endpoints, jobs, databases, message consumers, or integrations are affected?
- **What evidence confirms safety?** Which builds, tests, startup logs, dependency reports, artifact smoke tests, and metrics were checked?
- **If something breaks, how do we roll back?** Do old artifacts, schema compatibility, configuration, and the rollout strategy support rollback?

Not every patch upgrade needs a massive migration project. Still, even for small bumps, you should know exact before/after versions and run matching verification checks.

### 1.1. Distinguishing Patch, Minor, and Major Upgrades

Under semantic versioning, version components are commonly written as:

```text
MAJOR.MINOR.PATCH
```

That is a general convention, though you must follow the specific versioning policy of Spring Boot and each dependency:

- **Patch:** usually focuses on bug fixes and security patches; still check release notes and regression tests.
- **Minor:** may add features, change behavior, bump dependency trains, or deprecate APIs.
- **Major:** may introduce breaking changes, raise the Java baseline, change package namespaces, remove old APIs, and overhaul configuration.

Never assume a patch upgrade cannot cause impact. A transitive dependency update, a bug fix, or a subtle runtime behavior change can still affect your application.

### 1.2. Define a Clear Reason for Upgrading

State the objective clearly:

- Patch a security vulnerability.
- Pick up a needed bug fix.
- Adopt a new API or feature.
- Align with a new Java or runtime baseline.
- Move off a version reaching end of support.
- Align with a Spring Cloud release train or integrated library.

The objective helps scope testing. An upgrade addressing a serialization fix needs payload regression tests; a security patch warrants targeted security tests; a Java baseline bump requires verifying build tooling and container runtime images.

### 1.3. Avoid Changing Multiple Axes at Once Unless Necessary

A single PR that bumps Spring Boot, switches Java versions, swaps databases, changes the HTTP client, and refactors modules becomes very hard to bisect when tests fail.

Whenever possible, split changes into reviewable stages:

1. Capture and establish the baseline.
2. Upgrade Spring Boot and its dependency train.
3. Update affected APIs and configuration.
4. Upgrade the Java runtime or underlying platform separately if feasible.
5. Roll out according to the deployment plan.

During a major upgrade, some steps must move together. In that case, document coupling between changes explicitly and retain evidence for each group.

## 2. Checklist 0 — Capture the Pre-Change Baseline

This step establishes your reference point. Without knowing the pre-upgrade state, distinguishing newly introduced bugs from pre-existing behavior becomes difficult.

### 2.1. Record Current Versions

- [ ] Spring Boot version declared in build configuration.
- [ ] Actual resolved Spring Framework version.
- [ ] Java version used for compilation.
- [ ] Java runtime version in deployment environments.
- [ ] Maven/Gradle version and wrapper version.
- [ ] Spring Cloud release train, if used.
- [ ] Spring Security, Spring Data, Hibernate, and key integration versions.
- [ ] Database drivers, servlet container, and messaging clients.
- [ ] Third-party SDKs/API clients affecting startup or request paths.

Do not record only what is written in the build file. Inspect the resolved dependency graph and the actually deployed artifact, since projects can override BOM versions or accidentally deploy stale artifacts.

### 2.2. Record Current Environment

- [ ] Active profiles.
- [ ] Environment variables.
- [ ] Config maps/secrets and configuration sources.
- [ ] JVM flags and memory limits.
- [ ] Server port, context path, and management port.
- [ ] Database and schema versions.
- [ ] Message brokers, caches, object storage, and external service endpoints.
- [ ] Container base image and JRE version.
- [ ] Deployment image digest or build identifier.

Never record raw secrets or credentials in checklist documents. Record only variable names, secret sources, and safe verification procedures.

### 2.3. Record Current Behavior

- [ ] Startup duration and key startup stages.
- [ ] Health and readiness behavior.
- [ ] Endpoint contracts and HTTP status codes.
- [ ] Authentication and authorization behavior.
- [ ] Serialization formats and error payloads.
- [ ] Database migrations and schema state.
- [ ] Scheduled jobs and message consumers.
- [ ] Logging, metrics, tracing, and alert signals.
- [ ] Background tasks and batch jobs.

Select a representative suite of smoke tests covering critical business flows. This becomes your post-upgrade comparison baseline.

### 2.4. Archive Baseline Evidence

| Evidence | Purpose |
| --- | --- |
| Dependency tree / lock state | Know exact pre-upgrade dependency versions |
| Effective POM or Gradle dependency reports | Understand version management and resolution |
| Build and test reports | Know test status prior to changes |
| Startup logs | Reference baseline for bean/configuration warnings |
| OpenAPI / API contract snapshots | Compare HTTP contracts |
| Database migration version | Confirm current schema state |
| Artifact checksum / image digest | Identify the exact running binary/image |
| Runtime metrics baseline | Compare latency, error rate, and resource usage |

Small projects do not necessarily need to archive everything here. Retain the evidence that helps catch regressions in your real system.

## 3. Checklist 1 — Plan the Upgrade

Before modifying versions, identify the target release and impacted dependencies.

### 3.1. Identify the Target Release

- [ ] Pick a concrete Spring Boot target version, never generic “latest.”
- [ ] Confirm the release is published and complies with organizational support policy.
- [ ] Read release notes spanning from current version to target version.
- [ ] Read migration guides across any intermediate major lines.
- [ ] Identify the minimum Java baseline.
- [ ] Identify compatible Maven/Gradle wrapper and plugin versions.
- [ ] Identify the target Spring Framework version managed by Boot.
- [ ] Check the Spring Cloud compatibility matrix if applicable.

When jumping across multiple major releases, never skip migration notes for intermediate major lines. A deprecation may appear in one major release and only be removed in the next.

### 3.2. Inventory High-Risk Dependencies

Prioritize reviewing:

- Overridden Spring Framework modules.
- Spring Security and custom security adapters.
- Spring Data/JPA providers.
- Hibernate extensions and custom dialects.
- Jackson modules and custom serializers.
- Servlet filters and listeners.
- Micrometer registries and tracing bridges.
- Logging bridges and providers.
- HTTP clients and third-party SDKs.
- Database drivers.
- Message broker clients.
- Libraries still using `javax.*` or legacy APIs.

### 3.3. Classify Changes

| Category | Examples | Verification Method |
| --- | --- | --- |
| Build/runtime baseline | Java or Maven/Gradle version | Build in CI and run on the target runtime |
| Dependency changes | Spring Framework, Hibernate, Jackson | Dependency reports, compatibility docs, integration tests |
| API changes | Deprecated or removed methods/annotations | Compilation, Javadoc, source migration |
| Configuration changes | Renamed properties or changed defaults | Binding/context tests and config review |
| Startup changes | Auto-configuration/bean conditions | Context startup tests, condition evaluation report |
| Behavioral changes | Serialization, security, transactions | Regression and integration tests |
| Operational changes | Health/readiness/logging/metrics | Packaged smoke tests and observability checks |

### 3.4. Define Done Criteria

Set concrete acceptance criteria upfront:

- Build succeeds cleanly on the target JDK.
- Dependency graph contains no unintended overrides.
- Critical configuration properties bind accurately.
- Application context boots across supported profiles.
- Unit, integration, and regression tests pass.
- Executable artifact starts up reliably.
- Readiness reports ready only once essential dependencies are healthy.
- API contracts show no unintended changes.
- Rollback strategy aligns with schema and artifact compatibility.

## 4. Checklist 2 — Dependencies and Build System

Dependencies form the foundation of an upgrade. Ensure modules belong to the same release train and no transitive versions introduce binary incompatibility.

### 4.1. Update Spring Boot in a Single Authoritative Source

Maven projects using the Boot parent can declare:

```xml
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.x.y</version>
    <relativePath/>
</parent>
```

Or import the Boot BOM:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-dependencies</artifactId>
            <version>3.x.y</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
```

Gradle can manage the Boot plugin/BOM via plugins, dependency management integration, or native platforms. Follow a single consistent mechanism across the project.

- [ ] Only one explicit target Boot version exists.
- [ ] Version is declared in the right parent, plugin, catalog, or BOM.
- [ ] No starters come from mismatched Boot lines.
- [ ] No Boot autoconfigure/core module is pinned out of alignment accidentally.
- [ ] No multiple competing BOMs override each other without clear resolution understanding.

### 4.2. Audit Spring Framework Overrides

Search for direct declarations such as:

```xml
<dependency>
    <groupId>org.springframework</groupId>
    <artifactId>spring-core</artifactId>
    <version>...</version>
</dependency>
```

A single Spring Framework module pinned outside the release train can trigger `NoSuchMethodError`, `NoClassDefFoundError`, or subtle behavioral incompatibility.

- [ ] Locate all version overrides under `org.springframework`.
- [ ] Verify every override has clear justification and compatibility proof.
- [ ] Remove overrides that are no longer required.
- [ ] When an override is strictly required, inspect related Spring modules and run integration tests.

### 4.3. Inspect the Maven Dependency Tree

Run:

```bash
./mvnw dependency:tree
```

Filter for a dependency:

```bash
./mvnw dependency:tree -Dverbose -Dincludes=org.springframework
```

Inspect the effective POM:

```bash
./mvnw help:effective-pom
```

- [ ] Spring Framework modules resolve to compatible versions.
- [ ] Boot starters align on the same release train.
- [ ] No dependency is accidentally excluded.
- [ ] `provided`, `runtime`, `test`, and `optional` scopes are intentional.
- [ ] Mediated version conflicts have clear explanations.
- [ ] No stale dependency pulls in an incompatible API namespace.

### 4.4. Inspect Gradle Dependency Insight

Inspect the runtime graph:

```bash
./gradlew dependencies --configuration runtimeClasspath
```

Trace why a module version was selected:

```bash
./gradlew dependencyInsight --dependency spring-core --configuration runtimeClasspath
```

Compare compile and test runtime classpaths when needed:

```bash
./gradlew dependencies --configuration compileClasspath
./gradlew dependencies --configuration testRuntimeClasspath
```

- [ ] Selected versions match expectations.
- [ ] Selection reasons and constraints are understood.
- [ ] No force rules mask underlying incompatibilities.
- [ ] Dependency locking is updated per project workflow.
- [ ] Lock state changes are reviewed.

### 4.5. Review Spring Cloud and Other Release Trains

If the application uses Spring Cloud:

- [ ] Identify the release train compatible with target Spring Boot.
- [ ] Update the Spring Cloud BOM per compatibility guidance.
- [ ] Never mix Cloud starters from different release trains.
- [ ] Verify gateway, config client, discovery, circuit breaker, and messaging integrations.
- [ ] Run integration tests for every Cloud flow in use.

For libraries outside the Spring ecosystem:

- [ ] Read the vendor's compatibility matrix.
- [ ] Verify JDK baseline requirements.
- [ ] Verify Jakarta EE namespace support.
- [ ] Inspect transitive dependencies pulled by the SDK.
- [ ] Prefer vendor BOMs when available.

### 4.6. Review Logging and Observability Dependencies

Logging and metrics dependencies can fail subtly when bridges or providers fall out of sync.

- [ ] Only the intended logging backend/provider is present.
- [ ] No duplicate SLF4J providers exist unintentionally.
- [ ] Logging bridges do not form infinite loops.
- [ ] Micrometer registries and tracing bridges match the Boot release.
- [ ] No mixed versions of Micrometer core/observation exist.
- [ ] Metrics/tracing exporters initialize and ship telemetry cleanly.

### 4.7. Verify Java and Build Tooling

- [ ] Update Maven/Gradle wrapper if the target release requires it.
- [ ] Update the Maven compiler plugin or Gradle Java toolchain.
- [ ] Set matching `source`, `target`, or `release` flags.
- [ ] Ensure CI runs the expected JDK.
- [ ] Ensure container runtimes use a compatible JRE/JDK.
- [ ] Verify IDE project SDKs do not mask discrepancies with CI.
- [ ] Confirm annotation processors, Lombok, MapStruct, and compiler plugins are compatible.

Gradle toolchain example:

```groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}
```

This is an example only. Choose the Java version matching your Spring Boot target and application policy.

## 5. Checklist 3 — API, Namespace, and Source Migration

Once the dependency graph is updated, the compiler surfaces incompatible APIs.

### 5.1. Locate Deprecated or Removed APIs

- [ ] Inspect compiler warnings.
- [ ] Identify deprecated API usages.
- [ ] Check `since` and `forRemoval` attributes.
- [ ] Find official replacements in Javadoc and migration guides.
- [ ] Migrate legacy APIs to recommended alternatives.
- [ ] Verify semantic differences in replacement APIs.

Do not mechanically rename methods merely to silence compiler warnings. Replacement APIs may differ in null handling, timeouts, exceptions, lifecycle hooks, or security semantics.

### 5.2. Verify javax to jakarta Migration

When upgrading to Spring Boot lines built on Jakarta EE:

- [ ] Audit `javax.servlet.*` imports.
- [ ] Audit `javax.persistence.*` imports.
- [ ] Audit `javax.validation.*` imports.
- [ ] Check servlet filters, listeners, and container integrations.
- [ ] Check JPA providers and persistence extensions.
- [ ] Check validation providers and custom validators.
- [ ] Upgrade SDKs/plugins that do not yet support Jakarta.
- [ ] Never add both namespaces simultaneously as a blanket workaround.

`javax.*` and `jakarta.*` are distinct packages and types. Simply adding the newer API artifact does not convert a library compiled against the older namespace.

### 5.3. Audit Spring Framework APIs

- [ ] Verify newly adopted classes and methods.
- [ ] Check for removed classes or methods.
- [ ] Inspect constructor and method overload changes.
- [ ] Inspect generic signatures and return types if linkage errors occur.
- [ ] Confirm classes reside in the expected artifacts.
- [ ] Avoid relying on internal packages.

### 5.4. Audit Spring Security APIs

- [ ] Check DSL and configuration APIs for your target version.
- [ ] Review custom filters and filter ordering.
- [ ] Check authentication providers.
- [ ] Review method security annotations.
- [ ] Verify CSRF, CORS, and session behavior.
- [ ] Verify authorization matcher ordering.
- [ ] Write tests covering anonymous, authenticated, permitted, and denied requests.

### 5.5. Audit Spring Data/JPA APIs

- [ ] Check repository interfaces and custom repository implementations.
- [ ] Check derived queries, JPQL, and native queries.
- [ ] Verify transaction behavior.
- [ ] Check entity mappings and attribute converters.
- [ ] Check Hibernate dialect and provider changes.
- [ ] Verify lazy loading and fetch plans.
- [ ] Verify pagination, sorting, and projections.

### 5.6. Audit Serialization and HTTP APIs

- [ ] Check Jackson modules and custom serializers/deserializers.
- [ ] Check naming strategies, date/time formatting, and enum serialization.
- [ ] Check request/response DTO compatibility.
- [ ] Check exception handlers and error response formats.
- [ ] Check HTTP client timeout and retry behavior.
- [ ] Check URI encoding and HTTP header handling.

## 6. Checklist 4 — Configuration and Properties

An application may compile cleanly yet behave differently after an upgrade because a property was renamed, deprecated, changed defaults, or stopped binding.

### 6.1. Audit application.properties / application.yml

- [ ] Find deprecated properties.
- [ ] Find renamed properties or moved prefixes.
- [ ] Find removed properties.
- [ ] Check whether default values changed.
- [ ] Verify property types and formats.
- [ ] Check whether properties depend on classpath conditions or profiles.
- [ ] Remove obsolete unsupported settings.

Do not copy property snippets blindly from migration guides. Cross-check against actual configuration across every profile.

### 6.2. Leverage Configuration Metadata

Spring Boot configuration metadata documents property names, types, descriptions, defaults, and deprecations. Inspect the new dependency version's metadata whenever IDE warnings flag a property.

Metadata aids discovery; reference docs and migration guides remain essential to understand runtime semantics and activation rules.

### 6.3. Verify Profiles and Property Precedence

- [ ] Is the default profile still right?
- [ ] Are production profiles activating as expected?
- [ ] Are `spring.config.import` and config locations still valid?
- [ ] Do environment variables map cleanly to properties?
- [ ] Do command-line args override settings as intended?
- [ ] Do config servers/secret managers supply compatible keys?
- [ ] Do test profiles accidentally hide production misconfigurations?

Document property source precedence in deployment environments. A property correctly set inside YAML can still be overridden by environment variables or command-line flags.

### 6.4. Verify Server and Web Configuration

- [ ] Port, context path, and servlet context path.
- [ ] Forwarded headers and reverse proxy settings.
- [ ] Multipart upload limits and request size caps.
- [ ] Session and cookie settings.
- [ ] Compression and HTTP/2 settings.
- [ ] Error pages and error response structure.
- [ ] CORS rules and allowed origins.
- [ ] Static resources and resource handler mappings.
- [ ] Graceful shutdown behavior.

### 6.5. Verify Management/Actuator Configuration

- [ ] Management port and base path.
- [ ] Endpoint enablement.
- [ ] HTTP/JMX exposure rules.
- [ ] Security rules protecting management endpoints.
- [ ] Health groups and health contributors.
- [ ] Liveness and readiness probes.
- [ ] Metrics registry and exporter settings.
- [ ] Info contributors exposing no sensitive data.

Never assume an existing endpoint is exposed or authorized without checking explicit config.

### 6.6. Verify Datasource and Persistence Settings

- [ ] JDBC URL and driver class.
- [ ] Connection pool settings.
- [ ] Pool sizing and timeouts.
- [ ] Transaction manager selection.
- [ ] Hibernate/JPA properties.
- [ ] Naming strategies and SQL dialects.
- [ ] Schema generation policy.
- [ ] Migration tool configuration.
- [ ] Read/write datasource routing if applicable.

### 6.7. Verify Serialization and Validation Configuration

- [ ] Jackson modules and customizers.
- [ ] Date/time serialization format.
- [ ] Unknown property handling.
- [ ] Enum serialization settings.
- [ ] Validation provider.
- [ ] Message interpolation.
- [ ] Validation groups.
- [ ] Request validation and error formatting.

### 6.8. Verify Logging and Metrics Configuration

- [ ] Logging levels.
- [ ] Log patterns and structured JSON output.
- [ ] File and appender behavior.
- [ ] Correlation and request IDs.
- [ ] Metrics common tags.
- [ ] Exporter endpoints and credentials.
- [ ] Tracing sampling rates.
- [ ] Sensitive data redaction.

## 7. Checklist 5 — Startup and Auto-Configuration

A successful startup is a key prerequisite, though never complete proof that every feature works. Even so, startup tests catch dependency, bean, and configuration failures early.

### 7.1. Verify the Application Context

- [ ] Context boots under production-like configuration.
- [ ] No unexpected `BeanCreationException`.
- [ ] No `UnsatisfiedDependencyException`.
- [ ] No new `NoSuchBeanDefinitionException` or bean ambiguity.
- [ ] No `NoClassDefFoundError` or `NoSuchMethodError`.
- [ ] No static initialization errors.
- [ ] No critical warnings ignored silently.

### 7.2. Inspect Auto-Configuration Conditions

Spring Boot auto-configuration conditions can shift depending on dependencies, classpath contents, or properties.

- [ ] Required auto-configurations match.
- [ ] Unwanted auto-configurations back off cleanly.
- [ ] Conditional beans appear in the right profiles.
- [ ] User-defined beans override defaults per contract.
- [ ] No duplicate beans or unintended fallback/default beans appear.

When startup produces surprises, the condition evaluation report reveals which conditions matched or missed.

### 7.3. Verify Bean Wiring

- [ ] Constructor injection resolves cleanly.
- [ ] Qualifiers still target the right beans.
- [ ] `@Primary` selects the expected candidate.
- [ ] Collection injections receive all intended candidates.
- [ ] `@ConditionalOnMissingBean` backs off cleanly when user beans exist.
- [ ] Optional dependencies are genuinely optional by design.
- [ ] No new circular dependencies were introduced.

Never use lazy initialization or field injection to mask a missing mandatory dependency. Keep required dependencies explicit when fail-fast startup is desired.

### 7.4. Verify Component Scanning and Imports

- [ ] `@SpringBootApplication` base package still encompasses required components.
- [ ] `@Import` and `@ImportAutoConfiguration` remain valid.
- [ ] Configuration classes were not dropped from scanning.
- [ ] Test/demo configurations are not accidentally scanned into production.
- [ ] Auto-configuration exclusions remain necessary and accurately named.

### 7.5. Verify Startup Listeners and Lifecycle

- [ ] `ApplicationRunner` and `CommandLineRunner` execute properly.
- [ ] Event listeners receive expected lifecycle events.
- [ ] Scheduled jobs do not fire prematurely.
- [ ] Background consumers start only after dependencies are ready.
- [ ] Graceful shutdown releases resources cleanly.
- [ ] Startup failures close connections and executors cleanly.

### 7.6. Verify External Dependencies at Startup

- [ ] Database connectivity and schema migrations.
- [ ] Message broker connectivity.
- [ ] Cache connectivity.
- [ ] Config or service discovery server connectivity if used.
- [ ] External HTTP client initialization.
- [ ] TLS certificates and truststores.
- [ ] DNS resolution and service discovery.

Decide explicitly which dependencies must succeed before readiness and which can reconnect asynchronously. Never let an app report ready while an essential dependency is broken.

### 7.7. Verify Health and Readiness

- [ ] Liveness reflects whether the process can keep running.
- [ ] Readiness reflects whether the instance can serve traffic.
- [ ] Health checks avoid expensive work or state-mutating side effects.
- [ ] Startup probes allow adequate time for boot and migrations.
- [ ] Management endpoints are properly secured and exposed.

Liveness and readiness serve distinct roles. Avoid tying liveness to external dependencies if transient outages would trigger perpetual container restarts.

## 8. Checklist 6 — Post-Upgrade Testing

No single test tier proves an upgrade succeeded. Layer tests according to risk.

### 8.1. Compilation and Static Checks

- [ ] Main source compiles cleanly.
- [ ] Test source compiles cleanly.
- [ ] Zero unresolved removed-API references remain.
- [ ] New compiler warnings are reviewed.
- [ ] Annotation processors run cleanly.
- [ ] Static analysis and linters pass.
- [ ] Generated sources are up to date.

### 8.2. Unit Tests

- [ ] Core business rules.
- [ ] Error handling logic.
- [ ] Validation logic.
- [ ] Mapping and serialization logic.
- [ ] Custom converters and formatters.
- [ ] Utilities relying on framework APIs.

Unit tests should stay focused on small isolated logic without booting the entire application context for every unit case.

### 8.3. Context and Startup Tests

- [ ] Application context loads across key profiles.
- [ ] Critical bean counts and types match expectations.
- [ ] Auto-configuration conditions match properly.
- [ ] Configuration properties bind cleanly.
- [ ] Bean selection and qualifiers behave accurately.
- [ ] Missing required dependencies cause startup to fail as intended.
- [ ] No new dependency cycles exist.

### 8.4. Web/API Integration Tests

- [ ] Key endpoints return expected status codes.
- [ ] Request and response schemas preserve contracts.
- [ ] Error payloads preserve contracts.
- [ ] Validation error payloads match expected format.
- [ ] Authentication and authorization rules hold.
- [ ] CORS and CSRF behave properly.
- [ ] Filters and interceptors execute as designed.
- [ ] Multipart and file upload flows work.

### 8.5. Persistence and Database Tests

- [ ] Database migrations run cleanly from supported baseline schemas.
- [ ] Repository queries execute accurately.
- [ ] Transaction commit and rollback semantics hold.
- [ ] Lazy and eager loading behave as expected.
- [ ] Pagination, sorting, and projections work cleanly.
- [ ] Locking and concurrency behavior match expectations.
- [ ] Generated SQL introduces no significant regressions.

When migrations alter schemas, test upgrading from the older schema and verify backward compatibility during rollback windows.

### 8.6. Messaging and Asynchronous Tests

- [ ] Producers emit valid message schemas.
- [ ] Consumers deserialize older and newer messages per contract.
- [ ] Retry and backoff behavior work cleanly.
- [ ] Dead-letter handling behaves properly.
- [ ] Acknowledgement semantics remain intact.
- [ ] Ordering and idempotency guarantees hold.
- [ ] Scheduled tasks and async executors run as expected.

### 8.7. Security Tests

- [ ] Anonymous requests are blocked or permitted as intended.
- [ ] Authenticated requests succeed properly.
- [ ] Role and authority mappings hold.
- [ ] Method security continues enforcing checks.
- [ ] CSRF and CORS policies match design.
- [ ] OAuth2/JWT/Resource Server integrations pass.
- [ ] Password encoders and providers remain compatible.
- [ ] Management endpoints are not unintentionally exposed.

### 8.8. Regression Tests for Behavioral Defaults

Focus on behaviors that can shift even when your source code stays unchanged:

- Jackson serialization defaults.
- Spring MVC content negotiation.
- Validation exception mapping.
- Transaction boundaries.
- Hibernate SQL generation and dialects.
- Security defaults.
- HTTP client timeouts and retries.
- Log formatting.
- Metric names and tags.

### 8.9. Testing the Packaged Artifact

This step is frequently skipped:

- [ ] Build the executable JAR or container image.
- [ ] Verify exact artifact version and build ID.
- [ ] Run `java -jar` or the container image identically to production.
- [ ] Inspect packaged runtime dependencies.
- [ ] Confirm the classpath has no missing or duplicate dependencies.
- [ ] Run smoke tests directly against that packaged artifact.

Tests run inside an IDE or test classpath do not substitute for smoke-testing the final packaged artifact.

## 9. Checklist 7 — Packaging and Deployment

Once tests pass, verify how the application is packaged and operated.

### 9.1. Artifact

- [ ] Artifact is built from a reviewed commit.
- [ ] Build version/commit ID is recorded.
- [ ] Checksum or image digest is captured.
- [ ] Runtime dependencies are bundled in the artifact/image.
- [ ] No stale JARs are copied manually.
- [ ] Base image provides a compatible JRE/JDK.
- [ ] Entrypoint and JVM arguments are accurate.

### 9.2. Containers and Orchestration

- [ ] Container user and permissions are appropriate.
- [ ] Memory and CPU limits are properly sized.
- [ ] JVM container awareness is verified.
- [ ] Health, readiness, and startup probes are configured properly.
- [ ] Graceful shutdown timeout is sufficient.
- [ ] Environment variables and secrets are injected cleanly.
- [ ] The exact verified image digest is deployed.
- [ ] Mutable tags are not relied upon without digest verification.

### 9.3. Database Migration Strategy

- [ ] Backup and restore procedures are confirmed.
- [ ] Migration scripts are reviewed.
- [ ] Migrations are tested against a representative dataset copy.
- [ ] Migration duration and lock impact are estimated.
- [ ] Schema changes remain compatible with the previous app version during rollout if needed.
- [ ] Rollback vs. forward-fix plan is explicitly documented.

Never assume code rollback works if a schema migration dropped or transformed data in ways the previous app version cannot read.

### 9.4. Rollout Strategy

Depending on architecture, choose rolling updates, canary deployments, blue/green deployments, or staged group rollouts.

Before starting rollout:

- [ ] Define health gates.
- [ ] Define traffic and error thresholds.
- [ ] Define observation windows.
- [ ] Identify rollout owners.
- [ ] Stage the previous artifact and rollback configuration.

### 9.5. Post-Deploy Observability

- [ ] Startup success rate.
- [ ] Readiness transitions.
- [ ] HTTP 5xx and overall error rates.
- [ ] p50/p95/p99 latency.
- [ ] JVM memory and GC behavior.
- [ ] CPU utilization and thread counts.
- [ ] Database connection pool saturation.
- [ ] Message consumer lag, retries, and dead letters.
- [ ] Logs free of new linkage or configuration errors.
- [ ] Complete delivery of metrics and traces.

Compare against the pre-upgrade baseline. An application that is “running” while latency doubles or consumer lag climbs steadily is still a failed upgrade.

## 10. Checklist 8 — Rollback and Forward Recovery

Rollback must be planned before deployment, especially when database/schema changes are involved.

### 10.1. Preparing Rollback

- [ ] Retain the previous artifact/image.
- [ ] Retain the previous configuration.
- [ ] Confirm how to restore the prior image digest.
- [ ] Verify schema compatibility with the previous app version.
- [ ] Check message format backward/forward compatibility.
- [ ] Identify any irreversible migrations.
- [ ] Maintain a backup/restore runbook when needed.

### 10.2. Expand-and-Contract for Databases

When a schema change risks breaking the older application version, apply this pattern:

1. **Expand:** add new columns, tables, or indexes while keeping old code running cleanly.
2. Deploy updated code reading and writing compatibly.
3. Migrate/backfill existing data.
4. **Contract:** remove legacy structures only after no old instances remain running and the rollback window has closed.

This is a general pattern; exact mechanics depend on your database engine and migration tooling.

### 10.3. When Rollback Is Unsafe

If a migration has already dropped or destructively altered data, rolling back the application binary can worsen failures. In that case, execute a forward fix or restore data per the pre-agreed plan.

### 10.4. Rehearsing Rollback

In a staging environment:

- [ ] Deploy the target version.
- [ ] Run smoke tests.
- [ ] Roll back to the prior artifact.
- [ ] Confirm the older app still reads current schema and message state.
- [ ] Verify readiness and core business flows.

An untested rollback plan is merely an assumption.

## 11. Focused Checklist for Patch/Minor Upgrades

Patch and minor upgrades have smaller blast radii than major upgrades, yet still require:

- [ ] Read release notes.
- [ ] Review relevant security advisories and bug fixes.
- [ ] Confirm Java/build baselines did not shift unexpectedly.
- [ ] Inspect the dependency tree diff.
- [ ] Check property and default changes if any.
- [ ] Compile and run unit tests.
- [ ] Run context and startup tests.
- [ ] Run regression/integration tests for affected flows.
- [ ] Build and smoke-test the packaged artifact.
- [ ] Monitor metrics and logs post-deploy.

If a patch release fixes a framework bug that your application previously relied upon, update regression tests to lock in the intended post-fix behavior.

## 12. Focused Checklist for Major Upgrades

Major upgrades require deeper review across every layer:

### 12.1. Platform

- [ ] Minimum Java version.
- [ ] Maven/Gradle version.
- [ ] Servlet/Jakarta platform.
- [ ] Container and JRE images.
- [ ] Build plugins and annotation processors.

### 12.2. Dependency Train

- [ ] Spring Framework release line.
- [ ] Spring Cloud release train.
- [ ] Spring Security.
- [ ] Spring Data/JPA/Hibernate.
- [ ] Jackson and serialization modules.
- [ ] Micrometer and observability.
- [ ] Third-party SDK compatibility.

### 12.3. Source Migration

- [ ] Removed APIs.
- [ ] Deprecated APIs.
- [ ] Package namespace transitions.
- [ ] Annotation behavior changes.
- [ ] Security DSL changes.
- [ ] Persistence API changes.

### 12.4. Configuration Migration

- [ ] Renamed or removed properties.
- [ ] Changed defaults.
- [ ] Auto-configuration changes.
- [ ] Management endpoints and exposure.
- [ ] Logging and metrics configuration.
- [ ] Profiles and external configuration.

### 12.5. Runtime Behavior

- [ ] Startup and bean graph.
- [ ] Database schemas and SQL execution.
- [ ] HTTP/API behavior.
- [ ] Security policies.
- [ ] Messaging behavior.
- [ ] Shutdown and lifecycle hooks.
- [ ] Performance and resource consumption.

### 12.6. Deployment

- [ ] Staging rollout.
- [ ] Rollback rehearsal.
- [ ] Observability dashboards.
- [ ] On-call and runbook updates.
- [ ] Production rollout gates.

## 13. Risk-Based Testing Matrix

Not every project needs to run every possible test for every bump. Use this matrix to scope checks based on what changed.

| Change Scope | Minimum Verification to Consider |
| --- | --- |
| Boot patch only | Dependency diff, build, unit/context tests, packaged smoke test |
| Spring Framework API | Compilation, API tests, context startup, web/integration tests |
| Spring Security | Security config tests, authorization regression, CSRF/CORS checks |
| Spring Data/Hibernate | Repository integration, transactions, SQL/schema/migrations |
| Jackson | Serialization contract tests and backward-compatible payloads |
| Java baseline | Toolchain/CI/container builds, runtime smoke, native/reflective integrations |
| Jakarta migration | Compilation, servlet/JPA/validation integrations, third-party SDK checks |
| Actuator/Micrometer | Endpoint security/exposure, health/readiness, metrics/tracing export |
| Database driver | Connections, transactions, prepared statements, failover/timeouts |
| Messaging client | Producers/consumers, retries, acknowledgements, serialization |
| Major upgrade | Critical flows, migration tests, packaged artifact, rollout/rollback rehearsal |

Prioritize testing directly impacted code paths and business flows carrying the highest operational consequence.

## 14. Reading the Dependency Diff After Upgrading

After updating the Boot version, do not inspect only a single changed line in the POM. Compare the full before/after dependency graph.

### 14.1. Questions to Answer

- Which dependencies were added?
- Which dependencies were removed?
- Which artifacts changed major or minor versions?
- Was any dependency bumped unintentionally?
- Are any version overrides now obsolete?
- Did any module resolve from a different BOM?
- Do compile, runtime, and test classpaths differ unexpectedly?

### 14.2. Maven

Generate dependency trees before and after upgrading, save outputs, and diff them. For critical artifacts, filter by group/artifact to trace inclusion paths.

```bash
./mvnw dependency:tree -Dverbose
```

### 14.3. Gradle

Save dependency reports and use `dependencyInsight` on critical modules. If using lockfiles, review lockfile diffs alongside build configuration changes.

### 14.4. Dependency Convergence

You can use Maven Enforcer dependency convergence or Gradle constraints/locking to catch version drift. Those checks detect version conflicts, though they do not guarantee behavioral or binary compatibility on their own.

## 15. Inspecting Configuration Diffs

A practical approach is tracking critical properties in a table:

| Property | Before | After | Source | Verified |
| --- | --- | --- | --- | --- |
| server.port | ... | ... | Environment | [ ] |
| spring.datasource.* | ... | ... | Secret/config store | [ ] |
| spring.jpa.* | ... | ... | Profile config | [ ] |
| management.* | ... | ... | Deployment config | [ ] |
| logging.* | ... | ... | Profile config | [ ] |

Never write raw secret values into tables. Record secret key names, sources, and verification outcomes instead.

### 15.1. Detecting Ignored Properties

Properties that stop binding may not trigger startup failure. To catch them:

- Inspect configuration metadata.
- Read migration guides.
- Test `@ConfigurationProperties` binding explicitly.
- Enable startup validation on mandatory configuration.
- Assert bound values inside context tests.
- Verify live runtime behavior.

### 15.2. Auditing Changed Defaults

When a default changes, consciously choose to:

- Adopt the new default.
- Pin the prior value explicitly.
- Update application code for the new behavior.

Avoid blindly pinning every default; pin only values that constitute operational contracts for your application.

## 16. Making Startup Verification Meaningful

Seeing `Started ...` in logs is useful evidence, yet it never proves all dependencies or code paths work.

### 16.1. Startup Gate

Startup checks should confirm:

- Context boots with zero startup errors.
- Critical beans exist.
- Required properties bind cleanly.
- Expected auto-configurations match.
- Database and messaging dependencies reach healthy states.
- Readiness transitions cleanly.

### 16.2. Do Not Check Process Liveness Alone

A running process does not mean the application is ready. An app can stay up while failing to reach its database, failing to consume messages, or misrouting endpoints.

### 16.3. Keep Health Checks Free of Side Effects

Health checks should be lightweight, strictly time-bounded, and free of data creation or business side effects. For temporarily unavailable external dependencies, readiness is usually more appropriate than liveness.

### 16.4. Verify Startup Under Production-Like Profiles

Context tests using only a `test` profile can miss issues present in `prod`. Establish a safe way to verify production-like configuration without putting production secrets into CI.

## 17. Testing API Contracts After Upgrading

If your app exposes REST APIs, framework upgrades can alter serialization, validation, routing, or error responses.

### 17.1. Contract Checks

- [ ] HTTP methods and paths.
- [ ] Request and response schemas.
- [ ] Required vs. optional fields.
- [ ] HTTP status codes.
- [ ] Error response payloads.
- [ ] Headers and content types.
- [ ] Pagination, filtering, and sorting.
- [ ] Date and time formatting.

### 17.2. Backward Compatibility

When older clients still call your API, check:

- Do newly added fields have safe optional/default handling?
- Were any existing fields renamed or dropped?
- Could new enum values break strict older clients?
- Did date/time serialization formats shift?
- Did error payloads change shape?
- Did authentication or session semantics shift?

### 17.3. OpenAPI Snapshots

Compare before/after OpenAPI specs. Not every diff is a breaking change, yet every diff should be understood and explained.

## 18. Testing Databases and Migrations

Upgrading Spring Boot can upgrade Hibernate, Spring Data, or JDBC drivers—potentially altering SQL generation, dialect selection, transaction semantics, or schema handling.

### 18.1. Schema Migrations

- [ ] Run migrations cleanly from older baseline schema versions.
- [ ] Verify migration ordering.
- [ ] Validate data integrity post-migration.
- [ ] Verify indexes and constraints.
- [ ] Measure execution time and locking impact.
- [ ] Confirm older app instances can coexist during rollout if needed.

### 18.2. ORM Behavior

- [ ] Entity mappings.
- [ ] Lazy proxies.
- [ ] Cascade and orphan removal.
- [ ] Fetch joins and entity graphs.
- [ ] JPQL and native query results.
- [ ] Generated identifiers.
- [ ] Optimistic and pessimistic locking.
- [ ] Transaction rollbacks.

### 18.3. Auditing Generated SQL

For critical queries, capture before/after SQL in tests or staging. Pay close attention to query plans, N+1 regressions, and dialect shifts.

### 18.4. Never Rely on Schema Auto-Update as a Migration Plan

Setting `ddl-auto=update` does not substitute for a reviewed migration strategy. Production schema changes belong in explicit migration tooling paired with rollback/forward-fix plans.

## 19. Testing Messaging and Integrations

Framework and dependency upgrades can impact client libraries, serializers, retry behavior, and consumer lifecycles.

- [ ] Producer message schemas.
- [ ] Consumer deserialization.
- [ ] Compatibility with in-flight messages already sitting in brokers.
- [ ] Retries and backoff policies.
- [ ] Dead-letter queues.
- [ ] Acknowledgements and offset commits.
- [ ] Partitioning and ordering behavior.
- [ ] Idempotency guarantees.
- [ ] Shutdown and consumer group rebalancing.
- [ ] Connection recovery.

When message schemas span multiple services, test new producers against old consumers and vice versa across your supported compatibility window.

## 20. Checking Performance and Resource Usage

Upgrades can shift startup time, memory usage, GC behavior, thread counts, or query performance.

### 20.1. Compare Under Identical Conditions

- [ ] Identical dataset.
- [ ] Identical CPU/memory limits.
- [ ] Identical workload mix.
- [ ] Identical JVM flags.
- [ ] Identical external dependency behavior.
- [ ] Identical warm-up duration.

### 20.2. Metrics to Observe

- Startup duration.
- Heap and non-heap memory usage.
- GC frequency and pause duration.
- CPU utilization.
- Thread counts.
- Request throughput.
- p95/p99 latency.
- Database connection pool metrics.
- Queue depth and consumer lag.
- Error and retry rates.

### 20.3. Never Draw Conclusions from a Single Run

Measure performance across repeatable runs against your baseline. A single uncontrolled run can reflect warm caches, network jitter, or noisy neighbors rather than framework differences.

## 21. Walkthrough Example: Upgrading a Service

Suppose `catalog-service` runs an older Spring Boot release and the team wants to upgrade to a newer release for security patches and an updated web client API.

### Phase A — Baseline

1. Record Boot, Framework, and Java versions.
2. Save the dependency tree.
3. Archive config profiles.
4. Run the current test suite.
5. Capture startup logs, API contracts, and baseline metrics.

### Phase B — Dependency Plan

1. Select the target Boot version.
2. Confirm the Java baseline.
3. Read release notes and migration guides.
4. Check Spring Cloud and third-party vendor compatibility.
5. Update the parent, plugin, or BOM.
6. Remove unnecessary version overrides.
7. Compare before/after dependency graphs.

### Phase C — Source and Config Migration

1. Compile sources and resolve removed/deprecated APIs.
2. Address `javax`/`jakarta` transitions if required by the major release line.
3. Update renamed properties.
4. Verify changed default values.
5. Update security, web, and data configurations as needed.

### Phase D — Startup

1. Run context tests.
2. Inspect the bean graph and auto-configuration report.
3. Boot under a production-like profile.
4. Verify database and messaging connectivity.
5. Verify readiness probes and Actuator security.

### Phase E — Tests

1. Unit tests.
2. Web/API contract tests.
3. Persistence and migration tests.
4. Security tests.
5. Messaging and integration tests.
6. Targeted regression tests for affected features.

### Phase F — Artifact and Rollout

1. Build the executable JAR or container image.
2. Inspect dependency packaging.
3. Run smoke tests on the packaged artifact.
4. Deploy to staging.
5. Inspect metrics and logs.
6. Rehearse rollback.
7. Execute canary or rolling production rollout behind health gates.

## 22. Upgrade Pull Request Review Checklist

Reviewers can use these checkpoints:

### Dependencies

- [ ] Boot version was updated in the single authoritative place.
- [ ] BOM, parent, and plugin versions align cleanly.
- [ ] No Spring module is pinned out of line without justification.
- [ ] Transitive dependency changes and exclusions were reviewed.
- [ ] Spring Cloud and third-party vendor compatibility was verified.
- [ ] Java and build tool versions align.

### Configuration

- [ ] Migration notes were reviewed.
- [ ] Deprecated and removed properties were addressed.
- [ ] Key defaults were verified.
- [ ] Profiles and environment overrides were reviewed.
- [ ] Security and management endpoint exposure was not loosened unintentionally.

### Startup

- [ ] Context startup tests pass.
- [ ] Auto-configuration and bean conditions match expectations.
- [ ] External dependencies and migrations were checked.
- [ ] Readiness and liveness probes behave appropriately.
- [ ] No linkage or circular dependency errors exist.

### Testing

- [ ] Compile and unit tests pass.
- [ ] Context and integration tests pass.
- [ ] API, security, data, and messaging regression tests cover changes.
- [ ] Packaged artifact smoke tests pass.
- [ ] Dependency graph diff was reviewed.

### Operations

- [ ] Artifact/image includes a clear build identifier.
- [ ] Rollout and rollback plans are clear.
- [ ] Schema compatibility was assessed.
- [ ] Dashboards, alerts, and runbooks were updated where needed.

## 23. Reusable Checklist Template for an Upgrade

Use this template to track upgrade progress. Omit inapplicable items, while documenting why any high-risk item is marked N/A.

```markdown
# Spring Boot Upgrade Record

## Target
- Current Spring Boot:
- Target Spring Boot:
- Current Java:
- Target Java:
- Build tool:
- Upgrade reason:
- Target release notes:
- Migration guide:

## Baseline
- [ ] Dependency graph saved
- [ ] Effective POM / Gradle reports saved
- [ ] Active profiles recorded
- [ ] Runtime artifact/build ID recorded
- [ ] Existing tests and smoke tests pass
- [ ] API/configuration/metrics baseline saved

## Dependencies
- [ ] Boot parent/plugin/BOM updated
- [ ] Spring Framework modules aligned
- [ ] Spring Cloud compatibility confirmed
- [ ] Third-party SDK compatibility confirmed
- [ ] Transitive conflicts reviewed
- [ ] Exclusions and scopes reviewed
- [ ] Java/build tool/annotation processors compatible

## Source and configuration
- [ ] Deprecated/removed APIs handled
- [ ] javax/jakarta compatibility confirmed
- [ ] Properties and defaults reviewed
- [ ] Profiles and external config reviewed
- [ ] Security/web/data/Actuator configuration reviewed

## Startup
- [ ] Context starts in required profiles
- [ ] Auto-configuration conditions reviewed
- [ ] Required beans and dependencies available
- [ ] Database migrations/connectivity verified
- [ ] Messaging/external integrations verified
- [ ] Readiness/liveness verified

## Tests
- [ ] Compile and static checks pass
- [ ] Unit tests pass
- [ ] Context tests pass
- [ ] API/contract tests pass
- [ ] Security tests pass
- [ ] Persistence/migration tests pass
- [ ] Messaging/integration tests pass
- [ ] Packaged artifact smoke test passes

## Deployment
- [ ] Artifact/image digest recorded
- [ ] Staging rollout verified
- [ ] Performance/metrics compared
- [ ] Rollback plan reviewed/tested
- [ ] Production rollout gates defined

## Decision
- Known limitations:
- Accepted risks:
- Rollback trigger:
- Owner:
- Review date:
- Final decision:
```

## 24. When Can an Upgrade Be Marked Complete?

Never mark an upgrade complete simply because CI turned green. An upgrade is ready when:

1. **The dependency set is understood and controlled:** target versions are explicit, with no unexpected overrides or conflicts.
2. **Configuration is verified:** key properties bind accurately, profiles/environment precedence is checked, and default shifts are accepted.
3. **Startup is healthy:** contexts register expected beans, auto-configurations match, and required dependencies initialize.
4. **Representative tests pass:** impacted business flows and integrations are thoroughly exercised.
5. **The packaged artifact runs reliably:** verified directly as a packaged JAR/image, not only inside an IDE.
6. **Operations have full visibility:** health probes, logs, metrics, and alerts catch regressions quickly.
7. **Rollback and recovery are planned:** artifacts, schemas, and configurations support recovery if rollout fails.

High-risk changes need staging and canary proof before full rollout. Small patches may follow a leaner checklist when dependency diffs and impact analysis justify it.

## 25. Common Upgrade Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Bump Boot version only and deploy | Misses dependency, config, and API shifts | Work through each checklist layer |
| Follow `latest` docs for an older project | Calls unavailable APIs or uses wrong properties | Match docs and Javadoc to exact release |
| Pin a single Spring module independently | Version skew and linkage errors | Let Boot BOM/release train manage versions |
| Ignore transitive dependencies | Runtime loads incompatible versions | Review dependency trees and compatibility docs |
| Run unit tests only | Misses context and auto-config failures | Add context and integration tests |
| Test only the `dev` profile | Production configs fail at deploy time | Test production-like profiles safely |
| Check only the `Started` log line | Lazy beans, endpoints, or code paths may still fail | Run smoke tests and readiness checks |
| Skip testing the executable JAR | Runtime packaging may miss dependencies | Run the real packaged artifact/image |
| Ignore property defaults | Behavior shifts silently without code changes | Check metadata and migration guides |
| Blindly add dependencies to fix `NoClassDefFoundError` | Introduces conflicts or duplicate classes | Identify the rightful owning artifact first |
| Catch `LinkageError` to keep booting | Hides broken deployments | Fix classpath, versions, and initialization |
| Roll back code without considering schema | Older app fails against altered database | Use expand-and-contract and rehearse rollback |
| Skip metric comparisons | Performance regressions go unnoticed | Compare identical workloads against baseline |

## 26. Summary

A Spring Boot upgrade checklist spans **dependencies, configuration, startup, testing, and deployment**. Each layer answers a distinct question: are dependencies compatible, does the app load intended settings, does the container start cleanly, do tests protect behavior, and does the packaged artifact operate reliably?

Keep these principles front and center:

- Capture a baseline before making changes.
- Select an explicit target release and read release notes/migration guides.
- Manage Spring modules through a consistent Boot BOM/release train.
- Audit dependency graphs, scopes, exclusions, and third-party compatibility.
- Verify Java, build tool, and runtime baselines.
- Audit APIs, namespaces, properties, and behavioral defaults.
- Verify auto-configurations, bean wiring, external dependencies, and readiness.
- Run risk-proportionate unit, context, integration, regression, and packaged artifact tests.
- Prepare rollout gates, observability, and rollback plans before deploying.

An upgrade is justified only when **the dependency graph is controlled, configuration is verified, startup is clean, tests protect behavior, and the packaged artifact is validated in a production-like environment**. This checklist turns version upgrades into evidence-backed, reviewable, recoverable changes.

# Cross-Checking Target Version Documentation, Configuration, and Defaults

Upgrading Spring Cloud alongside Spring Boot is an ecosystem-wide compatibility problem. Changing version numbers in the build file alone is not enough: the Spring Cloud release train must support the target Spring Boot generation, Cloud modules must belong to the same train, underlying libraries and the JDK must meet the new requirements, and properties, auto-configuration, and runtime behavior must be verified against the documentation of the target version itself.

In the `SPRING_CLOUD_CORE` module, this lesson focuses on Spring Cloud Commons, Spring Cloud Context, external configuration, discovery, service registry, and refresh. Because these components are used by many starters and providers, a change in Spring Boot or Spring Framework can affect multiple integrations simultaneously.

The goal is to build an evidence-based process: identify the source and target versions, choose a compatible release train, lock dependencies with a BOM, read migration guides and release notes, compare properties/defaults, verify APIs and auto-configuration, and then confirm via builds, tests, and a controlled rollout. The version numbers in this lesson are examples as of the time of writing; always re-verify the latest matrix and release notes before upgrading a real project.

## 1. Why Cross-Check the Target Version?

Spring Boot manages a set of dependencies tested together. Spring Cloud adds projects for distributed configuration, service discovery, routing, load balancing, circuit breaking, and other patterns. Each Cloud release train is published to be compatible with one or more specific Boot generations.

If the wrong combination is chosen, errors can appear at many stages:

- The build fails to resolve dependencies or plugins.
- The application fails at startup due to the compatibility verifier.
- Binary linkage errors such as `NoSuchMethodError` or `NoClassDefFoundError`.
- Auto-configuration no longer matches because the classpath or conditions changed.
- Old properties are ignored, renamed, or receive new defaults.
- Discovery, registration, refresh, or HTTP clients behave differently than before.
- Integration tests pass, but errors appear only when running on the real JDK, servlet container, or deployment platform.

A solid upgrade must answer four questions:

1. Is the target version within a Spring-supported combination?
2. Is the actual dependency graph consistent with the BOM and runtime requirements?
3. Which configurations and defaults changed, and has the application explicitly verified them?
4. Has critical application behavior been tested on the exact target classpath?

## 2. Priority Order of Reference Documentation

Do not rely on a single overview page to decide the entire migration. Each source answers a different part:

| Source | Read to learn | How to use |
| --- | --- | --- |
| Spring Cloud project compatibility matrix | Which release train supports which Boot generation | Choose the train before editing dependencies |
| Spring Cloud Supported Versions | Whether a train/project is still supported or EOL | Avoid upgrading to a train that is already out of support |
| Target Spring Cloud train release notes | Changes per train and per service release | Read from the source version to the target version |
| Target Spring Boot migration guide | Platform, API, property, and dependency changes | Read for every major/feature release crossed |
| Spring Boot release notes | Defaults, behavior, and bug fixes per release | Determine the impact of patch/minor releases |
| Individual Spring Cloud project docs | Configuration and behavior of Config, Commons, Netflix, Gateway, Kubernetes, etc. | Check the exact modules in use |
| API Javadoc and configuration metadata | Signatures, deprecations, property names/types/defaults | Verify implementation details |
| Build dependency report | Actual resolved versions | Detect overridden or mismatched dependencies |
| Tests and runtime logs | Actual behavior in the application | Confirm the documentation matches the running configuration |

When upgrading across multiple generations, read the guides for the intermediate versions as well. For example, going from Boot 3.2 to Boot 4.1 requires reviewing relevant changes across the intermediate feature/major releases, not just the Boot 4.1 documentation.

Spring Boot places upgrade instructions at the top of its release notes and requires reading any skipped versions as well. Spring Cloud also recommends choosing the release train based on Boot and then using the latest service release of that train. These two principles help prevent missing cumulative changes.

## 3. Choosing a Spring Cloud Release Train Compatible with Spring Boot

### 3.1. Distinguishing Boot Versions and Cloud Release Trains

Spring Boot and Spring Cloud use separate versioning schemes:

- Spring Boot uses lines such as 3.5.x, 4.0.x, or 4.1.x.
- Spring Cloud uses release trains such as 2025.0.x or 2025.1.x, accompanied by a codename.
- Each release train manages the versions of multiple Cloud projects such as Commons, Config, Netflix, Gateway, and Circuit Breaker.

Do not infer compatibility between two versions simply because the year or major numbers look close. Consult the official matrix to determine the relationship.

### 3.2. Example Compatibility Matrix

The following table is a snapshot of the matrix published at the time this lesson was written. It illustrates how to read the table, not a fixed list for future upgrades.

| Spring Cloud release train | Published compatible Spring Boot | Notes |
| --- | --- | --- |
| 2025.1.x (Oakwood) | 4.0.x; 4.1.x from 2025.1.2 | Current line in the matrix at the time of lookup |
| 2025.0.x (Northfields) | 3.5.x | Marked EOL on the matrix at the time of lookup |
| 2024.0.x (Moorgate) | 3.4.x | Marked EOL on the matrix at the time of lookup |
| 2023.0.x (Leyton) | 3.2.x; 3.3.x from 2023.0.2 | Marked EOL on the matrix at the time of lookup |
| 2022.0.x (Kilburn) | 3.0.x; 3.1.x from 2022.0.3 | Marked EOL on the matrix at the time of lookup |

Not every Boot patch/minor is supported from the first patch of a Cloud train. For example, the matrix may note that a train supports Boot 4.1.x starting from a specific service release. Match the minimum required train patch first, then pick the latest supported service release.

If the project requires commercial support or is operating an EOL train, check the current support policies of your organization and vendor. "It builds" does not mean it still receives security patches.

### 3.3. Checking the Support Status of Each Project

A release train is a collection of multiple projects. Support windows for projects within a train can differ; do not treat a train's codename as an indefinite support guarantee.

Check:

- Whether the Spring Boot version in use is still supported.
- Whether the Spring Cloud release train is still within its OSS support window.
- Whether each individual Cloud project used by the application has a supported version.
- Whether external providers such as Eureka, Consul, Kubernetes client, or tracing libraries have their own lifecycle policies.

### 3.4. Do Not Mix Cloud Modules from Multiple Trains

Do not manually declare Commons from one train, Config from another train, and Netflix from a third train just to work around a compile error. These modules can share contracts, auto-configuration, and internal APIs. Use the release train BOM to manage them as a compatible set.

## 4. Locking Dependencies with a BOM

A BOM (Bill of Materials) defines a managed set of versions for dependencies. Spring Boot provides `spring-boot-dependencies`; Spring Cloud provides `spring-cloud-dependencies` for the release train.

### 4.1. Maven with the Spring Boot Parent and Spring Cloud BOM

Illustrative example for a compatible combination published at the time of writing:

```xml
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>4.1.2</version>
    <relativePath/>
</parent>

<properties>
    <java.version>17</java.version>
    <spring-cloud.version>2025.1.4</spring-cloud.version>
</properties>

<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-dependencies</artifactId>
            <version>${spring-cloud.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-config</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-netflix-eureka-client</artifactId>
    </dependency>
</dependencies>
```

Dependencies managed by the BOM do not need individual version declarations. When switching release trains, update the version property and review the resolved dependency graph.

If the project does not use the Spring Boot parent, you can still import the Boot BOM and Cloud BOM in `dependencyManagement`. Check Maven's precedence rules when multiple BOMs manage the same artifact; avoid adding versions directly to dependencies just to mask an unexamined conflict.

### 4.2. Gradle with the Dependency Management Plugin

A common configuration approach:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '4.1.2'
    id 'io.spring.dependency-management' version '1.1.7'
}

dependencyManagement {
    imports {
        mavenBom "org.springframework.cloud:spring-cloud-dependencies:2025.1.4"
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.cloud:spring-cloud-starter-config'
    implementation 'org.springframework.cloud:spring-cloud-starter-netflix-eureka-client'
}
```

When using the dependency management plugin, the Spring Boot plugin integrates dependency management from the Boot BOM. The Cloud BOM adds versions for Cloud modules.

### 4.3. Gradle Native Platform BOM

Gradle can also use native BOM support:

```groovy
dependencies {
    implementation platform('org.springframework.boot:spring-boot-dependencies:4.1.2')
    implementation platform('org.springframework.cloud:spring-cloud-dependencies:2025.1.4')

    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.cloud:spring-cloud-starter-config'
}
```

Choose one clear management approach aligned with your build structure. Avoid importing the same BOM via multiple mechanisms or adding overlapping version constraints unintentionally.

### 4.4. Do Not Arbitrarily Override Core Versions

Spring Boot tests a specific set of dependencies. Overriding Spring Framework, Jackson, Reactor, Netty, Micrometer, or logging libraries can skew the tested combination.

Only override when:

- There is a specific security or bug-fix requirement.
- The replacement version is compatible with the Boot/Cloud versions in use.
- There is a documented reason and an accountable owner.
- There are tests proving the behavior.
- There is a plan to remove the override once the BOM incorporates the appropriate version.

## 5. Inspecting the Actual Dependency Graph

The build file only expresses intent. The dependency resolver tells you which versions actually land on the runtime classpath.

### 5.1. Maven

View the dependency tree:

```bash
mvn dependency:tree
```

View the effective POM:

```bash
mvn help:effective-pom
```

Locate core artifacts:

```bash
mvn dependency:tree -Dincludes=org.springframework,org.springframework.cloud,io.projectreactor,io.micrometer,com.fasterxml.jackson
```

Check whether the versions of Commons, Context, Config, Netflix, and other starters belong to the same release train. Also look for dependency versions declared directly in submodules or internal parent POMs.

### 5.2. Gradle

View the dependency report:

```bash
./gradlew dependencies
```

See why a specific version was selected:

```bash
./gradlew dependencyInsight --dependency spring-cloud-commons --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-framework --configuration runtimeClasspath
```

Do the same for Config, Netflix, Gateway, Reactor, Micrometer, and any provider in use. A dependency can enter transitively through multiple paths; you need to know which rule caused Gradle to choose the final version.

### 5.3. Signs of a Broken Dependency Graph

- Multiple unintended versions within the same Spring Framework family.
- Spring Cloud Commons from a different train than Spring Cloud Config.
- A starter overridden by a version declared in a submodule.
- An older dependency still pulling `javax.*` while the application has moved to the Jakarta namespace.
- A provider library pulling an incompatible Netty/Reactor version.
- The build file looks correct, but the runtime classpath inside the container differs due to packaging or dependency scopes.

Do not inspect only the compile classpath. Check `runtimeClasspath`, the executable jar, or the container image, since errors often surface only when the application runs.

## 6. Cross-Checking Platform Requirements: JDK, Spring Framework, and Jakarta

A compatible release train does not automatically guarantee that every non-Spring dependency is compatible. Read the target Boot migration guide to verify platform baselines.

For example, Spring Boot 4.0 requires Java 17 or higher, Kotlin 2.2 or higher if using Kotlin, Spring Framework 7.x if managing dependencies directly, Jakarta EE 11, and a Servlet 6.1 baseline. If using native images, the migration guide also specifies the corresponding GraalVM baseline. These are requirements for Boot 4.0; do not extrapolate them to every Boot feature release.

Cross-check additionally:

| Item | What to confirm |
| --- | --- |
| JDK | Toolchain, compiler release, runtime image, and CI use the same baseline |
| Kotlin | Kotlin plugin, stdlib, and compiler are compatible with the Boot/Kotlin target |
| Servlet API | Container and dependencies use the right Jakarta Servlet generation |
| Spring Framework | Framework modules match the versions managed by the Boot BOM |
| Servlet container | Tomcat/Jetty/Undertow version is managed by Boot and compatible |
| Reactive stack | Reactor Netty/Reactor Core and clients are compatible |
| Jakarta namespace | No remaining `javax.*` dependencies or imports for APIs moved to `jakarta.*` |
| Native image | GraalVM, AOT processing, and Spring Cloud projects support native image |
| Build plugins | Maven/Gradle, compiler, Surefire/Failsafe, Kotlin plugin, and Docker image |

### 6.1. Checking javax to jakarta

A major platform shift can move APIs from the `javax.*` namespace to `jakarta.*`. Not every `javax` package was moved; for example, certain Java SE APIs retain that namespace. Distinguish Jakarta EE APIs from Java SE packages such as `javax.crypto` or `javax.sql`.

Search for old servlet/JPA/validation imports and dependencies, then update them to the APIs required by the target Boot version. Check whether third-party libraries have Jakarta-compatible releases before upgrading.

## 7. Reading Release Notes by Individual Spring Cloud Project

Spring Cloud Core spans multiple modules. Read the release notes specifically for the starters present in your dependency graph:

| Project | Areas to review |
| --- | --- |
| Spring Cloud Commons | DiscoveryClient, ServiceRegistry, load balancer abstraction, compatibility verifier, common properties |
| Spring Cloud Context | Bootstrap context, refresh scope, environment change, lifecycle events |
| Spring Cloud Config | Config Data import, bootstrap mode, retry, override precedence, encryption |
| Spring Cloud Netflix | Eureka client/server, health propagation, registration lifecycle |
| Spring Cloud Consul | Discovery, health checks, config integration, and watch |
| Spring Cloud Kubernetes | Discovery, ConfigMap/Secret property sources, client library, and service routing |
| Spring Cloud LoadBalancer | Service instance supplier, caching, health checks, retry, and default algorithm |
| Spring Cloud CircuitBreaker | Adapters, factories, fallbacks, time limiters, and implementation versions |
| Spring Cloud OpenFeign | Client configuration, contracts, HTTP clients, and circuit breaker integration |

Do not read every release note and update modules you do not use. Filter by the runtime classpath and the application's actual features.

## 8. Comparing Source and Target Configuration and Properties

### 8.1. Property Names Can Change or Be Removed

A property can keep its name and default, be renamed, be deprecated, be removed, change its data type/format, change its default, or take effect only when a specific starter/classpath condition exists.

Do not search for properties only in YAML files. Properties can come from environment variables, command-line arguments, Config Server, secret sources, `@PropertySource`, or a custom `PropertySource`.

### 8.2. Using Configuration Metadata

Spring Boot/Spring Cloud projects can publish metadata describing property names, data types, defaults, descriptions, deprecation metadata, and replacement suggestions.

Locate `spring-configuration-metadata.json` inside the jars or use IDE metadata support. Compare metadata between the source and target versions to catch renamed or removed keys.

Metadata is a configuration aid, not a substitute for behavioral documentation. The default listed in metadata may not fully describe the runtime value when a property depends on conditions or other beans.

### 8.3. Systematically Comparing Defaults

Create a dedicated table for critical properties:

| Property | Source: actual value | Target: published default | Value chosen by application | Verification evidence |
| --- | --- | --- | --- | --- |
| Config import/fail-fast | Record current mode | Read target Config Client docs | Required/optional per business need | Startup test when Config Server is down |
| Discovery enabled | Record property and classpath | Check Commons/provider docs | Enabled/disabled per service | Context test and registry test |
| Service auto-registration | Record registration lifecycle | Read default and event docs | Automatic/manual | Registration and shutdown test |
| Load balancer cache | Record TTL/implementation | Check target train default | Choose based on freshness and load | Instance update test |
| Refresh behavior | Record current scope/event | Check Context/Config docs | Select refreshable beans | Property update test |
| Actuator exposure | Record currently exposed endpoints | Check Boot endpoint defaults | Minimal allowlist | Security integration test |

Do not fill in guessed values. If the documentation does not publish a default or the default depends on the environment, record "conditional/non-fixed" and verify at runtime.

### 8.4. Bound Values Differ from Default Values

Effective values can come from multiple property sources. To determine the source, use the `env` or `configprops` endpoints in a protected test/admin environment, enable appropriate configuration binding logs, or inspect `Environment` in tests.

Do not dump all properties into production logs because they can contain credentials, tokens, or private endpoints. Log only the necessary keys and sources, and mask sensitive values.

## 9. Using spring-boot-properties-migrator Properly

Spring Boot provides `spring-boot-properties-migrator` to diagnose certain properties that were renamed or removed when upgrading feature releases.

Maven:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-properties-migrator</artifactId>
    <scope>runtime</scope>
</dependency>
```

Gradle:

```groovy
runtimeOnly 'org.springframework.boot:spring-boot-properties-migrator'
```

The migrator can print diagnostics and temporarily map some old properties to new ones at runtime. It is a transitional tool to identify what needs fixing, not a final migration solution.

Notes:

- Run it in a testing or staging environment with controlled logging.
- Read every warning and fix the original configuration files.
- Check Config Server and environment variables as well, not just `application.yml`.
- Properties added late to `Environment`, such as via certain `@PropertySource` declarations, may not be detected by the migrator.
- Once migration is complete, remove the migrator dependency from the project.
- This tool primarily supports Spring Boot properties; it does not automatically handle every Spring Cloud or third-party provider property.

## 10. Checking the Spring Cloud Compatibility Verifier

Spring Cloud Commons includes a compatibility verifier to detect certain Spring Boot combinations not supported by the current release train. This mechanism can halt startup and output a report of incompatible versions.

It can be enabled explicitly in test environments:

```yaml
spring:
  cloud:
    compatibility-verifier:
      enabled: true
```

The property `spring.cloud.compatibility-verifier.compatible-boot-versions` can be used to configure a list of accepted Boot versions when there is a special requirement that has been thoroughly verified.

Do not disable the verifier just to make the application start. If the verifier reports an invalid combination, first check the Boot version, Cloud BOM, and dependency graph. Only alter the compatible version list when your organization has evidence of compatibility, full test coverage, and accepts responsibility for maintaining that combination.

The verifier is a useful guardrail, but it does not replace the compatibility matrix. It does not verify every provider, servlet container, JDK, configuration, or business behavior.

## 11. Cross-Checking Auto-Configuration and Bean Conditions

A dependency upgrade can change the classpath, conditions, or default beans.

For each important integration, check:

- Does the auto-configuration class still exist?
- Have classpath/property/bean conditions changed?
- Which beans are created by default?
- Does `@ConditionalOnMissingBean` now select a different implementation?
- Have bean names, qualifiers, or primary candidates changed?
- Is provider-specific configuration still being imported?
- Are customizers/interceptors/filters attached to clients as before?

Use the condition evaluation report or Actuator `conditions` in a protected environment. Compare the bean inventory between source and target environments to spot missing beans, new beans, or changed implementations.

Do not treat the mere presence of a bean as proof that the integration works. For example, a `DiscoveryClient` bean can exist even when the registry is unreachable; a `LoadBalancerClient` bean can exist even when the service instance list is empty.

## 12. Spring Cloud Core Areas Requiring Deep Inspection

### 12.1. External Configuration and Config Data

Check:

- `spring.config.import` and Config Server locations.
- `optional:`/required behavior and fail-fast.
- Active profiles, application name, and labels.
- Discovery-first lookup if used.
- Retry, timeout, and credentials.
- Property source precedence and override policies.
- Legacy bootstrap mode if the application still uses it.
- Encryption/decryption and secret handling.
- Timing of property source loading relative to bean creation.

A configuration can parse successfully yet fail to load a property source as expected. Tests must confirm the final values in `Environment` and bound beans.

### 12.2. Spring Cloud Context and Refresh

Check:

- Is `@RefreshScope` still applied to the right beans?
- Which beans are refreshed and which retain state?
- Do environment change events trigger the expected behavior?
- Are refresh endpoints/Bus still exposed and properly secured?
- Do beans with resource lifecycles need to close/recreate resources?
- Do client connection pools, caches, and scheduled tasks react properly after refresh?

Do not assume every property can be hot-reloaded. Some settings such as listener ports, server SSL, thread pools, or dependency graphs require restarting/recreating the application rather than refreshing individual beans.

### 12.3. DiscoveryClient and ServiceRegistry

Check:

- Provider starter and API versions.
- Auto-registration enabled/disabled.
- Instance ID, hostname, port, secure flag, and metadata.
- Registration/deregistration events.
- Health propagation and heartbeat.
- Discovery cache/refresh intervals.
- Whether the client handles an empty instance list.
- Whether a registry outage affects startup or only discovery requests.

### 12.4. Service Calls and Load Balancing

Check:

- `RestTemplate`, `WebClient`, Feign, or HTTP interface integration.
- Load-balanced annotations/customizers/interceptors.
- Service ID resolution.
- Retry and circuit breaker integration.
- Timeouts, connection pools, and TLS.
- Error mapping and fallbacks.
- Trace propagation and metrics.

A request may still compile yet no longer pass through the load balancer if a custom client builder or interceptor changed.

### 12.5. Actuator and Observability

Check endpoint IDs, exposure, access policies, health groups, metric names, tags, and registry exporters. A changed default exposure can impact monitoring or security.

Do not broaden endpoint exposure just to make a dashboard work. Update scrapers and security policies according to the required endpoints.

## 13. Comparing Defaults and Behavior with Tests

Documentation tells you the designed defaults; tests tell you which values and behaviors the application is actually receiving.

| Area | Check | Expected evidence |
| --- | --- | --- |
| Dependency | Resolve runtime graph | Modules belong to the same train with no unintended overrides |
| Config binding | Start context with representative config | Properties bind properly, validation passes |
| Config Server | Test remote import and unavailable errors | Required/optional and retry match policy |
| Auto-configuration | Test conditions and bean inventory | Expected beans present, no duplicates |
| Refresh | Change property then trigger refresh | Beans refresh properly and resources do not leak |
| Discovery | Register, query instances, deregister | Metadata and lifecycle are accurate |
| Load balancing | Call service ID with multiple instances | Instance selection and retry match policy |
| Actuator | Call endpoint with appropriate role | Exposure and authorization are correct |
| Web/runtime | Start embedded server on target JDK | Port, TLS, servlet/reactive behavior are correct |
| Shutdown | SIGTERM/graceful close | Request draining and registry cleanup succeed |

### 13.1. Deterministic Configuration Testing

Each test should explicitly declare profiles, properties, and mock dependencies. Avoid depending on a developer machine's environment or a production Config Server.

For property tests, verify the final value via `Environment` or `@ConfigurationProperties` beans. For dynamic endpoints/containers, use an appropriate property supplier and manage the context cache.

### 13.2. Integration-Level Testing Against Real Providers

Mock tests verify the application code's contract, but they do not completely replace integration tests with Eureka, Consul, Config Server, or Kubernetes. Use appropriate containers/test servers to verify provider protocols, metadata, health checks, and lifecycles.

Not every test suite needs to spin up the entire infrastructure. Layer unit, context, contract, and integration tests to keep feedback fast while still verifying critical boundaries.

## 14. Step-by-Step Upgrade Process

### Step 1 — Lock the Source Baseline

Record:

- Spring Boot version and Spring Cloud release train.
- JDK/toolchain and build plugins.
- Spring Cloud starters and providers in use.
- Runtime dependency graph.
- Profile/property sources and deployment configuration.
- Current test suite, startup duration, health, registration, and request metrics.

Save build/test results as a baseline for post-migration comparison.

If the target is Spring Boot 4.0, the migration guide recommends bringing the application to the latest release in the 3.5.x line before starting the major upgrade. This ensures the source baseline receives the latest dependency patches and surfaces existing issues prior to the major jump.

### Step 2 — Choose Target Versions

Check the compatibility matrix and support policy. Pick the release train supporting the target Boot version, then select the latest supported service release. Confirm JDK, Spring Framework, Jakarta, servlet/reactive container, and provider requirements.

### Step 3 — Read Migration Guides and Release Notes

Read in order:

1. Spring Boot migration guides for each major/feature release crossed.
2. Spring Boot release notes for skipped versions.
3. Spring Cloud release notes for the target train.
4. Release notes for each Cloud project in use.
5. Third-party provider migration guides.

Log impacted items as issues/checklists, categorized into build, source code, properties, defaults, behavior, and deployment.

### Step 4 — Update BOM and Build Plugins

Update the Boot plugin/parent, Cloud BOM, and JDK toolchain. Keep Cloud module versions managed by the BOM. Then resolve the dependency graph and fix conflicts with clear root causes.

### Step 5 — Fix Compilation and APIs

Resolve compile errors, deprecated APIs, Jakarta packages, generics/signatures, and client builders. Do not apply bulk search-and-replace changes without understanding semantic changes.

### Step 6 — Migrate Configuration

Compare source/target properties. Use the properties migrator when appropriate, and update local files, environment variables, Config Server, and deployment manifests. Verify runtime defaults and property precedence.

### Step 7 — Test by Feature

Run context tests, integration tests, and contract tests for Config, refresh, discovery, registry, service calls, Actuator, and security. Inspect bean/condition reports whenever differences appear.

### Step 8 — Verify Runtime and Performance

Measure startup time, heap, thread count, connection pools, latency, error rate, retries, discovery cache, and metrics. An upgrade that compiles cleanly can still alter default timeouts or connection behavior.

### Step 9 — Canary and Rollout

Deploy to a small group and monitor registration, health, config version, request distribution, and error rates. Increase batch sizes only when metrics stabilize.

### Step 10 — Remove Migration Tools and Finalize Documentation

Remove the properties migrator, drop temporary overrides, and update runbooks and dependency inventories. Document source/target versions, release train, changed properties, test evidence, and rollback procedures.

## 15. Rollback and Configuration Management During Rollout

Framework upgrades often change both artifacts and configuration. Rolling back only the old image may not be enough if Config Server is already serving new properties that old code does not understand.

Before rollout, prepare:

- Source artifacts/images that remain deployable.
- A remote configuration snapshot or label for the source version.
- Backward-compatible database schemas if schema migrations accompany the upgrade.
- A rollback plan for registry metadata or service registration if formats changed.
- Feature flags to toggle new behavior when appropriate.
- Canary signals and rollout halt thresholds.
- An accountable owner authorized to trigger a rollback.

If configuration changes are not backward-compatible, use versioned config labels or staged property migration: publish configuration understood by both old and new code, roll out the new code, and only remove old keys once the entire fleet has upgraded.

## 16. Common Pitfalls When Cross-Checking Versions

| Symptom | Common cause | Resolution |
| --- | --- | --- |
| Compatibility verifier halts startup | Boot version is outside the Cloud train's supported list | Select the right train or intentionally verify the combination |
| `NoSuchMethodError` | Dependency graph has unsynchronized binary APIs | Inspect runtime dependency tree and BOM |
| `ClassNotFoundException`/`NoClassDefFoundError` | Module was removed, artifact renamed, or dependency missing | Check migration guide and runtime classpath |
| Property no longer has effect | Key was renamed, removed, or property source not loaded | Check metadata, migrator, and `Environment` |
| Auto-configured bean does not appear | Conditions/classpath/defaults changed | Inspect condition report and dependencies |
| Multiple beans for the same interface | New auto-config adds a bean or custom config no longer matches | Check `@Primary`, `@Qualifier`, and conditions |
| Discovery sees no instances | Provider/config/version or metadata changed | Check registration and discovery responses |
| Refresh does not update bean | Scope/lifecycle or property source changed | Test refresh scope and resource recreation |
| HTTP client timeouts/errors increase | Default timeout, pool, TLS, or retry changed | Compare client configs and metrics |
| Actuator endpoint 404/401/403 | Exposure/access/security changed | Check endpoint IDs, allowlist, and security chain |
| Local build passes but CI fails | Different JDK, plugins, caches, or repositories | Lock toolchain and verify dependency resolution in CI |
| Rollback fails | New config/schema is incompatible with old code | Use staged config/schema and preserve a rollback path |

### 16.1. Distinguishing Compile Errors and Linkage Errors

Compile errors usually indicate that source code no longer matches the target API. Linkage errors usually indicate that code compiled against one API, but runtime loaded a different class version.

When encountering a linkage error, do not simply add dependencies at random. Identify which jar provides the class, which dependency path selected that version, and which BOM manages the artifact.

### 16.2. Do Not Disable the Verifier to Hide Dependency Drift

Disabling `spring.cloud.compatibility-verifier.enabled` may bypass a startup check, but it does not fix an incompatibility. If you must disable it in a special environment, document the reason, lock the version graph, and add tests/monitoring proving behavior.

## 17. Hands-On: Upgrading a Catalog Application

Suppose an application currently runs on an older Spring Boot 3.x and an older Spring Cloud release train. The application uses Config Client, Eureka, LoadBalancer, and `@RefreshScope`. The goal is to move to a newer Boot/Cloud combination supported by the official matrix.

### Step 1 — Capture the Baseline

- Save `mvn dependency:tree` or the Gradle dependency report.
- Record JDK and plugin versions.
- Save active profiles/properties.
- Run tests for Config import, refresh, registration, and service calls.
- Record startup time, health, registration status, and request metrics.

### Step 2 — Choose the Train

Consult the Spring Cloud matrix, confirm the target Boot version is supported, and verify the train is still in support. Pick the service release compatible with the needed Boot patch. Do not pick a Cloud version by arbitrarily bumping numbers.

### Step 3 — Update the BOM

Update the Boot parent/plugin and Cloud BOM. Remove direct versions on individual Spring Cloud starters if managed by the BOM. Resolve the dependency graph and verify Commons, Context, Config, and Netflix all belong to the target train.

### Step 4 — Read the Migration Guide

Flag changes across JDK, Spring Framework, Jakarta, properties, and APIs. Review deprecations that already existed in the source version because they may be removed in the target major release.

### Step 5 — Compare Configuration

List properties from `application.yml`, profiles, environment variables, and Config Server. Cross-check against the target version's configuration metadata. Run the properties migrator if this is an appropriate Boot feature release migration; fix the configuration sources and remove the migrator afterward.

### Step 6 — Verify Context and Refresh

Start the context with representative configuration. Confirm `@RefreshScope` beans have the proper scope, refresh events update expected properties, and old resources are closed properly.

### Step 7 — Verify Discovery and Service Calls

Confirm Eureka registration has the correct host/port/metadata, `DiscoveryClient` returns instances, LoadBalancer selects valid instances, and callers preserve defined timeout/retry policies.

### Step 8 — Run Tests and Canary

Run all relevant tests, build the executable artifact, and deploy a canary. Compare startup, health, registration, latency, error rates, and logs before rolling out fleet-wide.

### Step 9 — Finalize Migration

Remove temporary dependencies, drop obsolete properties, update runbooks, and archive the version graph record. Keep the source configuration snapshot during the rollback window.

## 18. Checklist Before Accepting the Target Version

### Compatibility and Support

- [ ] Target Boot version is in the Cloud train's compatibility matrix.
- [ ] The release train and each critical project are still supported.
- [ ] The chosen service release matches the target Boot patch.
- [ ] JDK, Kotlin, Spring Framework, Jakarta, and containers meet requirements.
- [ ] Third-party providers have compatible versions.

### Build and Dependencies

- [ ] Boot BOM/parent/plugin are updated.
- [ ] Cloud BOM is imported once in a consistent dependency management setup.
- [ ] No individual Cloud module versions are pinned when managed by the BOM.
- [ ] Runtime dependency tree has no unintended version skew.
- [ ] Maven/Gradle and compiler plugins are compatible with the target JDK.

### Configuration and Defaults

- [ ] Migration guides and release notes for all skipped versions have been read.
- [ ] Property names, types, defaults, and deprecations have been compared.
- [ ] Config Data/bootstrap, profiles, and precedence have been checked.
- [ ] Discovery/registration/refresh properties have been checked.
- [ ] Properties migrator has been removed after migration.
- [ ] No secrets were logged or exposed while inspecting configuration.

### Behavior and Tests

- [ ] Compatibility verifier is enabled/checked per policy.
- [ ] Auto-configuration conditions and bean inventory are accurate.
- [ ] Config Server and refresh behavior have been tested.
- [ ] Discovery, ServiceRegistry, and load balancing have been tested.
- [ ] HTTP client timeouts/retries/TLS have been verified.
- [ ] Actuator exposure and authorization are correct.
- [ ] Startup, graceful shutdown, and rollback have been tested.

### Rollout

- [ ] Source artifacts and source config snapshots are ready for rollback.
- [ ] Canary has clear halt thresholds.
- [ ] Monitoring dashboards compare version, error rate, latency, and registration.
- [ ] Config/schema migrations are backward-compatible during rollout.
- [ ] Runbooks and dependency inventories have been updated.

### Self-Check Questions

1. Why must the Spring Cloud release train be chosen based on the Spring Boot version?
2. What does the `spring-cloud-dependencies` BOM manage?
3. Why should you not mix Commons and Config from two different release trains?
4. How do the compatibility matrix and the compatibility verifier differ in role?
5. What issues does the runtime dependency tree help detect?
6. Why can a compile-classpath version differ from a runtime issue?
7. Which versions of the Spring Boot migration guide must be read when skipping multiple releases?
8. What does `spring-boot-properties-migrator` help with, and when should it be removed?
9. Why does configuration metadata not replace runtime tests?
10. What behaviors need to be checked when upgrading Spring Cloud Context?
11. Why is successful discovery registration alone insufficient proof that service calls work?
12. How can a rollback fail if Config Server has already served new properties?

**Answer Hints:** (1) Each Cloud train only supports a specific set of Boot generations/patches; (2) It manages the versions of Spring Cloud projects belonging to the train; (3) APIs and auto-configurations across modules may be incompatible; (4) The matrix defines supported combinations, whereas the verifier is a guardrail checking certain conditions at startup; (5) Transitively selected versions, overridden dependencies, and multiple coexisting versions; (6) Runtime may load a different jar than the one used at compile time; (7) Read migration guides/release notes for each major/feature release crossed; (8) Diagnoses and temporarily migrates Boot properties; remove it after updating the original configuration; (9) Metadata does not capture all runtime conditions and property sources; (10) Refresh scope, events, lifecycle, resource recreation, and endpoints/security; (11) Callers also depend on discovery visibility, caching, networking, load balancers, and health states; (12) Old code may not understand new keys or new defaults, so staged/versioned config is required.

## 19. Key Principles to Remember

- Select the Spring Cloud release train using the official compatibility matrix for the target Spring Boot version.
- Check support/EOL status for the train and each project; prefer service releases that are still supported.
- Use the Spring Boot BOM and Spring Cloud release train BOM to manage dependencies consistently.
- Do not mix Cloud modules from multiple trains or override core versions without evidence.
- Read migration guides and release notes for every skipped version.
- Cross-check JDK, Kotlin, Spring Framework, Jakarta, servlet/reactive containers, and third-party providers.
- Compare property names, types, defaults, conditions, and deprecations; do not assume old defaults stay unchanged.
- Use configuration metadata and the properties migrator to help locate changes, then fix the source config and remove temporary tools.
- Treat the compatibility verifier as a guardrail, not as comprehensive proof of compatibility.
- Verify auto-configuration, refresh, discovery, registration, load balancing, Actuator, and security with tests on the target runtime classpath.
- Deploy a canary, monitor behavior, and retain source configuration/artifacts for rollback.
- Document the version graph and test evidence so the next upgrade has a clear baseline.

Cross-checking a target version combines documentation, the dependency graph, and runtime behavior. When the release train, BOM, properties, and auto-configuration are all verified against the same target version, a Spring Cloud upgrade becomes controllable, easy to review, and equipped with a clear rollback path.

## References

- [Spring Cloud — Project, Release Train Compatibility Matrix and BOM Setup](https://spring.io/projects/spring-cloud/)
- [Spring Cloud — Supported Versions and Support Policy](https://github.com/spring-cloud/spring-cloud-release/wiki/Supported-Versions)
- [Spring Boot — Upgrading Guide](https://docs.spring.io/spring-boot/upgrading.html)
- [Spring Boot — Dependency Management with Gradle](https://docs.spring.io/spring-boot/gradle-plugin/managing-dependencies.html)
- [Spring Boot 4.0 Migration Guide](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.0-Migration-Guide)
- [Spring Cloud Commons — Compatibility Verification](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html)
- [Spring Cloud Commons — Configuration Properties](https://docs.spring.io/spring-cloud-commons/reference/configprops.html)
- [Spring Boot — Deprecated Application Properties](https://docs.spring.io/spring-boot/appendix/deprecated-application-properties/)

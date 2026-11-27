# Comparing the Spring Boot, Spring Cloud, and Gateway Matrix Before Upgrading

## 1. Why Compare All Three Versions Together?

A **Spring Cloud Gateway** project does not have just a single framework version. When upgrading, at least three axes must be compatible:

1. **Spring Boot** manages the application foundation, auto-configuration, runtime, dependency versions, and build plugins.
2. **Spring Cloud Release Train** is the BOM that groups compatible versions of Spring Cloud Commons, LoadBalancer, CircuitBreaker, Gateway, Discovery integrations, and related projects.
3. **Spring Cloud Gateway** is a project within the release train, with its own version. Gateway WebFlux, Gateway Web MVC, and Proxy Exchange also have different starters, APIs, and runtimes.

For example, an application currently running Spring Boot 3.5.x and Spring Cloud Gateway 4.3.x cannot simply bump Boot to 4.2.x and keep Gateway 4.3.x out of habit. The new combination must switch to the release train supporting Boot 4.2.x and the corresponding Gateway version. If you pick the wrong combination, errors may surface during dependency resolution, at Spring startup, or only when a request passes through a specific filter.

This article helps you:

- Correctly read the **Spring Boot ↔ Spring Cloud Release Train ↔ Spring Cloud Gateway** matrix.
- Distinguish technical compatibility from the OSS/Enterprise support lifecycle.
- Choose the BOM and starter properly for Maven/Gradle.
- Identify key changes when moving from Gateway 4.x → 5.x and Boot 3.5 → 4.x.
- Plan a phased upgrade with testing and rollback.
- Control Gateway risks: route/filter order, WebFlux/Web MVC, service discovery, forwarded headers, TLS, retry, circuit breaker, response cache, and WebSocket.

> **Data cutoff in this article: November 24, 2026.** Spring Cloud 2026.0.0 was just announced GA on November 20, 2026; Spring Boot 4.2.0 was released on November 19, 2026. Stable versions and support policies may change after this date. Before upgrading production, check the latest Spring Projects, release notes, and security advisories.

## 2. Understanding the Three Version Axes

### 2.1. Spring Boot version

The Spring Boot version determines the runtime foundation and the set of dependencies managed by Boot. Components that directly affect Gateway include:

- Spring Framework and Spring Security.
- Spring WebFlux/Reactor Netty or Spring Web MVC/Servlet container.
- Jackson and HTTP message codecs.
- Micrometer, Actuator, Observation/Tracing.
- Embedded server, TLS/SSL, logging, and configuration binding.

A Boot major/minor upgrade can change packages, starters, properties, or auto-configuration behavior. Therefore, checking only the Gateway version is not enough.

### 2.2. Spring Cloud release train

Spring Cloud uses a **release train version** in `YYYY.N` format, such as `2026.0`, `2025.1`. Each train manages multiple subprojects through the `spring-cloud-dependencies` BOM.

A BOM is a curated catalog of versions tested together by the Spring Cloud team. When importing the BOM, the application does not need to manually pin individual versions of Gateway, LoadBalancer, Discovery Client, or CircuitBreaker.

### 2.3. Spring Cloud Gateway version

Gateway has an independent version, such as `5.1.0`, `5.0.5`, `4.3.5`. A release train can manage a Gateway version number that differs from the train version number:

| Spring Cloud train | Gateway project version in train |
| --- | --- |
| `2026.0.0` | `5.1.0` |
| `2025.1.x` | `5.0.x` |
| `2025.0.x` | `4.3.x` |
| `2024.0.x` | `4.2.x` |
| `2023.0.x` | `4.1.x` |

Do not infer the Gateway version by copying `2026.0` into `2026.0.x`. Always look up the version from the BOM/release notes of the exact train.

## 3. Compatibility Matrix to Use as of November 24, 2026

### 3.1. Main matrix

| Spring Cloud Release Train | Compatible Spring Boot | Gateway project version | Support assessment |
| --- | --- | --- | --- |
| `2026.0.x` (Paddington) | `4.2.x` | `5.1.x` | Latest GA train as of this article |
| `2025.1.x` (Oakwood) | `4.0.x`; `4.1.x` from `2025.1.2` | `5.0.x` | Maintained train |
| `2025.0.x` (Northfields) | `3.5.x` | `4.3.x` | Marked EOL OSS in compatibility table; check Enterprise Support if needed |
| `2024.0.x` (Moorgate) | `3.4.x` | `4.2.x` | EOL OSS |
| `2023.0.x` (Leyton) | `3.2.x`, `3.3.x` from `2023.0.2` | `4.1.x` | EOL OSS |

This table combines information from the Spring Cloud compatibility mapping, release train reference docs, and Gateway releases. An asterisk `*` in the official Spring Cloud compatibility table means the release train has reached **end of life and is no longer supported under OSS**. A version artifact can still exist on Maven Central even though the train no longer receives community patches.

### 3.2. Specific announced versions

| Line | Verified release/version milestone |
| --- | --- |
| Spring Boot `4.2.0` | GA on November 19, 2026 |
| Spring Cloud `2026.0.0` | GA on November 20, 2026; based on Boot `4.2.0` |
| Spring Cloud Gateway `5.1.0` | Included in Spring Cloud `2026.0.0` |
| Spring Cloud `2025.1.5` | Reference docs as of this article; Boot `4.0.10` is listed as the supported Boot version |
| Spring Cloud Gateway `5.0.5` | Release in the Gateway 5.0.x line |
| Spring Cloud `2025.0.3` | Last release train listed in documentation as of this article; Gateway `4.3.5` |
For `2025.1.x`, the Spring Cloud compatibility mapping states that Boot `4.1.x` is supported starting from `2025.1.2`. Do not take a single “Supported Boot Version: 4.0.10” line on a reference page in isolation to conclude `4.1.x` is unsupported; combine the compatibility matrix and patch release notes.

### 3.3. Matrix compatibility does not mean every combination is recommended

There are three independent questions:

| Question | Source to check |
| --- | --- |
| Are Boot and Cloud train compatible? | Spring Cloud compatibility matrix / train reference |
| Is the train still OSS maintained? | Spring Cloud Support and Spring Boot support lifecycle |
| Does the Gateway patch contain the required security fixes? | Gateway release notes and Spring Security Advisories |

For example, `Boot 3.5.x + Cloud 2025.0.x + Gateway 4.3.x` is a compatible combination according to the mapping. However, Cloud `2025.0.x` is already marked EOL OSS in the current table. If a system must stay on Boot 3.5 due to constraints, verify **Enterprise Support** or plan an upgrade; do not treat a successful build as proof that the system still receives OSS patches.

### 3.4. Quick selection guide

- New projects accepting a newer platform: consider Boot `4.2.x` + Cloud `2026.0.x` + Gateway `5.1.x`.
- Projects moving to Boot 4 that do not need 4.2 yet: use train `2025.1.x`, pick a patch compatible with Boot `4.0.x` or `4.1.x`, and Gateway `5.0.x`.
- Projects still on Boot `3.5.x`: the mapping is Cloud `2025.0.x` + Gateway `4.3.x`; check EOL/support status before deciding to stay on it.
- Projects on Boot `3.4.x` or lower: do not start a new upgrade onto an EOL train; plan a roadmap to a still-supported branch.

## 4. Do Not Manage Versions by Pinning Individual Dependencies

### 4.1. Maven: use the Spring Boot parent and Spring Cloud BOM

Baseline example for Boot 4.2.0 + Cloud 2026.0.0 + Gateway Server WebFlux:

~~~xml
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>4.2.0</version>
    <relativePath/>
</parent>

<properties>
    <java.version>17</java.version>
</properties>

<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-dependencies</artifactId>
            <version>2026.0.0</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-gateway-server-webflux</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-loadbalancer</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>
</dependencies>
~~~

The Gateway starter does not need its own version declaration; the BOM manages the versions of Gateway and Spring Cloud modules. If the project needs Eureka/Consul/Kubernetes Discovery Client, add the corresponding starter **without manually pinning a version** when it belongs to the same release train.

If your company uses a corporate parent POM instead of the Spring Boot parent, you can keep the corporate parent and import `spring-boot-dependencies` along with `spring-cloud-dependencies` according to your organization's dependency management rules. Do not import multiple BOMs with conflicting order without knowing which version wins.

### 4.2. Gradle: import the Cloud BOM via platform

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '4.2.0'
}

group = 'example.gateway'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation platform(
        'org.springframework.cloud:spring-cloud-dependencies:2026.0.0'
    )

    implementation 'org.springframework.cloud:spring-cloud-starter-gateway-server-webflux'
    implementation 'org.springframework.cloud:spring-cloud-starter-loadbalancer'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

This is a minimal example. A real project needs to add test dependencies, security/discovery starters, plugins, and build conventions matching the actual runtime. If you use the `io.spring.dependency-management` plugin to import the BOM instead of `platform`, keep one consistent management approach.

### 4.3. What NOT to do

~~~xml
<!-- Don't: manually pin a Gateway version different from the Cloud BOM -->
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-gateway-server-webflux</artifactId>
    <version>4.3.5</version>
</dependency>
~~~

Do not:

- Pin `spring-cloud-gateway-server`, `spring-cloud-commons`, and `spring-cloud-loadbalancer` individually to different lines.
- Override Spring Framework, Reactor Netty, Jackson, or Spring Security just to make compilation errors go away without checking dependency constraints.
- Use snapshots or milestones in production unless there is a policy accepting pre-releases.
- Mix the Gateway WebFlux starter and Gateway Web MVC starter in the same application just to “try both”.
- Keep the old `spring-cloud-starter-parent` as the Spring Cloud management source in new trains; the `2025.1` release notes record that this parent artifact has been removed. Use the Spring Boot parent or Boot's dependency management combined with the Cloud BOM.

## 5. Verify the Dependency Tree Before Upgrading

### 5.1. Maven

~~~bash
mvn help:effective-pom
mvn dependency:tree -Dverbose
mvn dependency:tree -Dincludes=org.springframework.cloud,org.springframework,io.projectreactor,io.netty,com.fasterxml.jackson.core,tools.jackson
~~~

Check:

- Is there exactly one Gateway project version per the BOM?
- Are `spring-cloud-commons` and `spring-cloud-loadbalancer` on the same release train?
- Does the Spring Framework major match Boot?
- Are Reactor/Netty pulled to a mismatched version by an external dependency?
- Do Jackson 2 and Jackson 3 coexist intentionally, or are old dependencies pulling Jackson 2 in?
- Are there version overrides via a corporate BOM, `dependencyManagement`, Maven profiles, or transitive dependencies?

### 5.2. Gradle

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-cloud-gateway
./gradlew dependencyInsight --dependency spring-cloud-commons
./gradlew dependencyInsight --dependency reactor-netty-http
./gradlew dependencyInsight --dependency jackson-databind
~~~

Use `dependencyInsight` to find **what** brings an unwanted version into the graph. Do not just read the dependency list and patch a single version directly.

### 5.3. Check build/runtime requirements

Spring Boot 4.2.0 requires at least Java 17; the system requirements documentation as of this article lists compatibility up to Java 27, Spring Framework 7.1.0 or higher, Maven 3.6.3+, Gradle 8.x (8.14+), or Gradle 9.x. Third-party integrations may require newer Java or build tool versions.

For Spring Boot 4.0, the migration guide also specifies Java 17+, Kotlin 2.2+, and GraalVM Native Image 25+ when using native-image. Check all of:

- Java version on developer machines, CI, and production images.
- Maven/Gradle Wrapper, not just globally installed versions.
- Kotlin/Groovy compilers, annotation processors, and code generators.
- Docker base images, buildpacks, and native-image toolchains.
- Servlet container if choosing Gateway Web MVC.
- TLS provider/certificate store, DNS, and OS packages in the runtime image.

### 5.4. Create a comparable baseline

Before changing versions, record:

~~~text
Baseline:
  Spring Boot:
  Spring Cloud Release Train:
  Spring Cloud Gateway:
  Java:
  Maven/Gradle:
  Gateway runtime: WebFlux / Web MVC
  Discovery client:
  Route count:
  Filter inventory:
  Security configuration:
  TLS/forwarded-header configuration:
  Actuator exposure:
  Build/test result:
  Request throughput and latency:
~~~

Save the dependency tree, redacted startup logs, test reports, and key metrics. Without a baseline, it is hard to tell whether a regression came from dependencies, property migration, or the environment.

## 6. Moving from Boot 3.5 / Gateway 4.3 to Boot 4 / Gateway 5

This is a larger change than a patch upgrade. Spring Boot 4 brings modular design, Spring Framework 7, Jakarta EE 11, and Jackson 3; Spring Cloud 2025.1 has breaking changes to align with this foundation.

### 6.1. Preparation step: update the 3.5 line first

The Spring Boot 4 migration guide recommends upgrading your application to the **latest Spring Boot 3.5.x release** before moving to Boot 4. This lets you resolve deprecated APIs and dependency updates on the old baseline first, reducing the number of variables changing at once during an upgrade.

Before switching:

1. Upgrade Boot 3.5 to the latest patch aligned with your support contract.
2. Use the Boot 3.5-compatible Spring Cloud train to update Gateway 4.3.x to the latest patch in that line.
3. Resolve deprecated methods/properties that emit warnings.
4. Run the full suite of route, filter, security, TLS, discovery, and load tests.
5. Save the dependency tree, test evidence, and rollback artifact.

**Note:** as of this article, Cloud `2025.0.x` is marked EOL OSS. This is a step to stabilize the legacy baseline, not a recommendation to remain on this branch long-term. If extended support is needed, confirm your Enterprise Support entitlement.

### 6.2. Runtime requirements and Jakarta foundation

Spring Boot 4 requires Spring Framework 7 and is based on Jakarta EE 11. For Gateway Server Web MVC, the Servlet baseline is 6.1; check Tomcat/Jetty versions and the deployment container. Undertow support was removed from Spring Boot 4.0 because it did not meet the Servlet 6.1 baseline at release time.

Gateway Server WebFlux has a different runtime: it uses Spring WebFlux/Reactor Netty and **is not deployed as a WAR in a traditional Servlet container**. Do not apply Web MVC Servlet requirements to deduce the WebFlux runtime.

### 6.3. Spring Boot 4 modularization: audit starters

Boot 4 splits modules into smaller pieces and standardizes starter/package names. If an application depends directly on an old jar or relied only on a transitive dependency, add the appropriate new starter/module.

Some representative changes in the migration guide:

| Boot 3.x / old name | Boot 4.x / new direction |
| --- | --- |
| `spring-boot-starter-web` | `spring-boot-starter-webmvc` |
| `spring-boot-starter-oauth2-client` | `spring-boot-starter-security-oauth2-client` |
| `spring-boot-starter-oauth2-resource-server` | `spring-boot-starter-security-oauth2-resource-server` |
| `spring-boot-starter-oauth2-authorization-server` | `spring-boot-starter-security-oauth2-authorization-server` |
| Old monolithic module package | Dedicated module package like `org.springframework.boot.<module>` |

Do not rename Spring Cloud Gateway starters using Boot naming rules. For example, the Gateway Server WebFlux starter remains the Spring Cloud artifact `spring-cloud-starter-gateway-server-webflux`; Boot 4 modularization applies to Spring Boot's own starters and modules.

### 6.4. Jackson 3: check custom filters and serializers

Spring Boot 4 uses Jackson 3 as the preferred JSON library:

- Main groups/packages moved from `com.fasterxml.jackson` to `tools.jackson`.
- `jackson-annotations` keeps the `com.fasterxml.jackson.core` and `com.fasterxml.jackson.annotation` group/package.
- Some classes/customizers were renamed to reflect Jackson 3.
- The Jackson 2 compatibility module `spring-boot-jackson2` can be used temporarily while dependencies are not yet compatible, but this is a transitional option and is marked deprecated.

Gateway custom filters often parse or mutate JSON bodies using `ObjectMapper`, codecs, and message readers/writers. Check:

- Imports of `ObjectMapper`, `JsonNode`, serializers/deserializers.
- Custom `HttpMessageReader`/`HttpMessageWriter`.
- `ModifyRequestBody`/`ModifyResponseBody` rewrite functions.
- Custom error responses/problem details.
- Third-party libraries that only support Jackson 2.
- Tests for body encoding, content type, null handling, date/time, and polymorphic payloads.

Do not add both Jackson 2 and Jackson 3 arbitrarily and assume auto-configuration will pick the right mapper. If both must be maintained, define the mapper/codec and usage boundaries explicitly.

### 6.5. JSpecify nullability and Spring Framework 7

The Spring Cloud 2025.1 release notes highlight breaking changes related to JSpecify nullability and Spring Framework 7. This can expose nullability assumptions in custom code:

- Custom `GatewayFilterFactory` and `GlobalFilter`.
- `RouteDefinitionLocator`, `ServiceInstanceListSupplier`.
- Custom `HttpHeadersFilter`.
- Java/Kotlin interoperability.
- Overridden methods and generic return types.
- Build warnings from static analysis/compiler.

When upgrading, review method signatures and null contracts from the new libraries. Do not blindly suppress warnings; a warning may indicate code that assumed a value was always non-null when the new framework declares it differently.

### 6.6. Configuration properties migrator

Spring Boot 4 may rename or remove properties. `spring-boot-properties-migrator` helps diagnose and temporarily migrate certain properties at startup.

Maven:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-properties-migrator</artifactId>
    <scope>runtime</scope>
</dependency>
~~~

Gradle:

~~~groovy
runtimeOnly 'org.springframework.boot:spring-boot-properties-migrator'
~~~

Use it in a migration/test environment, read all diagnostics, update configuration files to the new names, and then **remove the migrator** from the dependency graph once finished. Do not keep the migrator as a permanent production solution.

### 6.7. Spring Cloud 2025.1: BOM and breaking changes

Train `2025.1` moves to the Spring Framework 7/Boot 4 generation and includes compatibility changes for Jackson 3 and JSpecify. Release notes record that the `spring-cloud-starter-parent` artifact has been removed. Use the Spring Boot parent or Boot dependency management, then import the Cloud BOM.

Do not mix Spring Cloud `2025.0.x` with Boot 4 just because the artifacts happen to resolve; the right train for Boot 4.0/4.1 is `2025.1.x`.

## 7. Spring Cloud Gateway Changes to Audit

### 7.1. Property namespaces moved in the 2025.0 train

Spring Cloud Gateway changed prefixes to reflect specific module/starter names:

| Runtime/module | Old prefix | New prefix |
| --- | --- | --- |
| Gateway Server WebFlux | `spring.cloud.gateway.*` | `spring.cloud.gateway.server.webflux.*` |
| Gateway Server Web MVC | `spring.cloud.gateway.mvc.*` | `spring.cloud.gateway.server.webmvc.*` |
| Proxy Exchange WebFlux | `spring.cloud.gateway.proxy.*` | `spring.cloud.gateway.proxy-exchange.webflux.*` |
| Proxy Exchange Web MVC | `spring.cloud.gateway.proxy.*` | `spring.cloud.gateway.proxy-exchange.webmvc.*` |

Example of an old configuration:

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: orders
          uri: lb://ORDER-SERVICE
          predicates:
            - Path=/api/orders/**
~~~

With Gateway Server WebFlux under the new namespace:

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: orders
              uri: lb://ORDER-SERVICE
              predicates:
                - Path=/api/orders/**
~~~

This is an important change: if you keep the old prefix in a migrated Gateway version, routes may not bind as expected. Migrate all `application.yml` files, profile overlays, Config Server, Helm values, environment variables, ConfigMaps, and tests.

### 7.2. Do not swap WebFlux prefixes to Web MVC by mistake

Gateway Server WebFlux and Gateway Server Web MVC have separate namespaces. Do not take a WebFlux YAML and mechanically replace `webflux` with `webmvc`; the two runtimes differ in APIs, filters, server, and execution model.

Check the starters:

- WebFlux: `spring-cloud-starter-gateway-server-webflux`.
- Web MVC: `spring-cloud-starter-gateway-server-webmvc`.
- Proxy Exchange: the corresponding `spring-cloud-gateway-proxyexchange-*` starters for the release.

Gateway WebFlux is based on Spring WebFlux/Reactor Netty. Gateway Web MVC uses the Spring WebMvc.fn/Servlet stack. Pick one runtime based on your architecture; do not mix starters or assumptions from the two runtimes.

### 7.3. Forwarded headers and trusted proxies

In the fix versions described in the Spring Cloud Gateway release notes, `Forwarded` and `X-Forwarded-*` handling is **disabled by default** to avoid trusting data from untrusted proxies.

If the application needs forwarding metadata, declare trusted proxy identities using a Java regular expression. Gateway Server WebFlux example:

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          trusted-proxies: '^10[.]20[.]0[.](?:10|11)$'
~~~

This is only a regex example for two proxy identities; it is not CIDR and does not replace NetworkPolicy/firewalls. You must verify the exact proxy metadata format in the real environment, sanitize headers at the edge, and block direct access that bypasses ingress.

For Gateway Server Web MVC, properties use a separate namespace per the release docs. Do not put a WebFlux regex into Web MVC and assume it takes effect.

### 7.4. Check filter order after upgrading

Gateway 5.1.0 documents/adds clarifications for the ordering of default filters and route filters. Custom filters that depend on ordering may change behavior after upgrading.

Check:

- `GlobalFilter` order and `Ordered`.
- `default-filters` relative to route-specific filters.
- `NettyRoutingFilter` and the response write stage.
- Security/auth filters before route matching.
- Request body cache/modify and response body rewrite.
- Retry/CircuitBreaker/fallback.
- Custom `HttpHeadersFilter`.
- Filters with side effects or that mutate exchange attributes.

Do not just verify that a filter is called; verify the **order** and the state of the request/response at the moment each filter executes.

### 7.5. Retry, Reactor, and Web MVC

Gateway 5.1 release notes record the migration from Reactor Addons Retry to Framework Core Retry and the addition of MVC WebSocket support. If the project has custom retry logic, check imports/types and retry/caching semantics. For Web MVC, test WebSocket handshake/origin/upgrade against the new runtime; do not assume behavior from WebFlux.

Retries must not multiply attempts across the Gateway filter and LoadBalancer. For POST/payment/order requests, verify idempotency keys and business state before allowing retries.

### 7.6. Security fixes must be part of version selection

Do not pick a version solely because it compiles cleanly. As of this article:

- Gateway `5.0.2` includes the fix for CVE-2026-47825.
- Gateway `5.0.3` fixes CVE-2026-47879 related to SSRF/native file access with gRPC.
- Gateway `5.0.5` includes fixes for CVE-2026-59425, CVE-2026-59426, CVE-2026-59427, and CVE-2026-59428: JsonToGrpc resource leak, LocalResponseCache cross-route leak, caching private/no-store responses, and WebSocket same-origin enforcement.
- Spring Cloud `2026.0.0` includes Gateway `5.1.0` and lists the corresponding security fixes in the release train notes.

This illustrates why you must use the **latest patch within the appropriate train**. Do not pick Gateway `5.0.1` just because it was the first version to build on Boot 4.0; check security advisories, release notes, and the dependency tree before deploying.

## 8. Pre-Upgrade Matrix Selection Workflow

### Step 1 — Record the current state

Collect:

- Spring Boot version.
- Spring Cloud BOM version.
- Actual resolved Gateway artifact version.
- Runtime: WebFlux or Web MVC.
- Java and build tool versions.
- Discovery client, LoadBalancer, CircuitBreaker, Redis/rate limiter.
- Custom filters/predicates and third-party dependencies.
- Config Server/Helm/ConfigMaps/profiles.
- Security advisories and support contract.

### Step 2 — Choose the Boot target first

Choose the Boot version based on runtime, Java, Servlet/Netty, vendor support, and dependency requirements. Then look up the Spring Cloud release train compatible with that Boot version.

Do not start by finding the “latest Gateway” and trying to force it onto the current Boot version.

### Step 3 — Choose the Cloud BOM

Based on the Boot target:

~~~text
Boot 4.2.x       -> Cloud 2026.0.x -> Gateway 5.1.x
Boot 4.0/4.1.x   -> Cloud 2025.1.x -> Gateway 5.0.x
Boot 3.5.x       -> Cloud 2025.0.x -> Gateway 4.3.x (EOL OSS as of this article)
~~~

Use the latest compatible service release of the train. Check release notes to see the exact Gateway version managed by the BOM.

### Step 4 — Check support lifecycle and security

Answer:

- Is the train still OSS supported?
- Is the Boot version maintained by Spring?
- Is there an Enterprise Support contract if needed?
- Does the Gateway patch include relevant CVE fixes?
- Are there third-party dependencies that do not yet support the new Boot/Framework/Jackson major?

If you do not have answers yet, do not select a production target.

### Step 5 — Read migration guides across all three projects

Read:

1. Spring Boot release notes/migration guide.
2. Spring Cloud train release notes.
3. Spring Cloud Gateway release notes.
4. Spring Framework/Spring Security release notes if majors changed.
5. Security advisories related to Gateway, Netty, Reactor, Jackson, and discovery clients.

Do not read only the “What’s New” page; the breaking changes and security fixes determine the risk.

### Step 6 — Resolve BOM and dependency tree

Update the Boot parent/plugin + Cloud BOM, then run the dependency tree. Remove unnecessary version overrides and handle incompatible dependencies.

### Step 7 — Migrate properties/starters and custom code

Audit:

- Gateway property prefixes.
- Starter artifact names.
- Boot property renames/removals.
- Jackson 3, JSpecify, Framework 7.
- Forwarded headers/trusted proxies.
- Custom filters and filter ordering.
- WebSocket, gRPC, body codecs, and native image hints.

### Step 8 — Run behavioral tests, not just compilation

Run unit/integration/security/contract/performance tests. Mandatory tests for Gateway are listed in section 10.

### Step 9 — Canary and rollout

Deploy a canary and observe request success/error rates, p95/p99 latency, route misses, upstream failures, retry counts, circuit breaker state, memory/pool metrics, and security logs.

### Step 10 — Verify rollback

Keep the pre-upgrade image/artifact and configuration. Ensure rolling back does not leave new schema/config/route definitions incompatible with the old version.

## 9. Phased Upgrade Plan

### 9.1. Example from Boot 3.5 / Cloud 2025.0 / Gateway 4.3 to Boot 4.2 / Cloud 2026.0 / Gateway 5.1

You can split the change into stages:

~~~text
Current:
  Boot 3.5.x
  Cloud 2025.0.x
  Gateway 4.3.x

Stabilize current line:
  update to latest compatible patches
  capture dependency/test/metrics baseline

Intermediate Boot 4 line:
  Boot 4.0.x or 4.1.x
  Cloud 2025.1.x
  Gateway 5.0.x
  migrate Boot 4 + Gateway namespace/starter/API changes

Target:
  Boot 4.2.x
  Cloud 2026.0.x
  Gateway 5.1.x
  update security patches and validate behavior again
~~~

Not every project has to deploy to production twice. A project with strong test coverage can attempt upgrading directly to the final combination; however, you should still split **commits/change sets** by layer: dependency baseline, Boot migration, Cloud/Gateway migration, security/config migration. This helps isolate issues and simplifies review.

### 9.2. Do not upgrade unrelated dependencies simultaneously

For example, changing Gateway, Redis, discovery provider, service mesh, database driver, Java runtime, and deployment platform all at once makes root-cause analysis very hard. Prefer groups of changes that can be tested independently; only upgrade dependencies required by the BOM or security fixes.

### 9.3. Update configurations across all sources

A property can exist in multiple places:

~~~text
application.yml
application-prod.yml
Config Server repository
Kubernetes ConfigMap
Helm values
environment variables
CI/CD pipeline
secret/config injection
~~~

Find and update every effective source. If you only update `application.yml` while production Config Server still overrides with the old prefix, routes may not be created.

## 10. Mandatory Test Suite for Spring Cloud Gateway

### 10.1. Routing and paths

- Route IDs and predicates match accurately.
- Host, Path, Method, Header, Query, and Cookie predicates preserve behavior.
- `StripPrefix`, `RewritePath`, `PrefixPath`, and `SetPath` work properly.
- Trailing slash, encoded slash, Unicode, query string, and path traversal cases.
- No-route responses do not turn into another route.

### 10.2. Filter chain

- GlobalFilter order and `Ordered`.
- Default filters versus route filters.
- Request header add/remove/set/map.
- Response header add/remove/dedupe.
- Request/response body rewrite and codecs.
- `DataBuffer` release, backpressure, and cancellation.
- Retry/CircuitBreaker/fallback ordering.
- Filter errors before/after response commit.

### 10.3. Service discovery and load balancing

- Does `lb://SERVICE-ID` select the right instance?
- Empty registry list and unavailable service instances.
- Health/zone/hint/version filters.
- Retrying next instance and retry counts.
- Instance metadata `isSecure`, hostname/port.
- DNS and network policy from Gateway to backend.
- Discovery cache refresh during scaling/deployment.

### 10.4. Security and forwarding

- JWT/OAuth2 authentication and scope authorization.
- `Forwarded`/`X-Forwarded-*` from untrusted clients are not trusted.
- Trusted proxy regex matches the exact format/addresses.
- HSTS, CORS, CSP, cookie attributes, and public redirects.
- Header size, malformed headers, Host poisoning, and request smuggling protections.
- Actuator management endpoints are not publicly exposed.
- CVE fixes in Gateway/Netty/serialization dependencies.

### 10.5. Resilience and HTTP client

- Connect/response/pool acquire timeouts.
- Connection pool active/idle/pending metrics.
- TLS truststore, certificate SAN, SNI, and mTLS.
- Retries do not cause duplicate POST side effects.
- Circuit breaker state/fallback does not fake business success.
- Backend 429/503/504 and `Retry-After`.
- Streaming responses, chunking, gzip, and client cancellation.

### 10.6. Differences between Gateway Web MVC and WebFlux

If the project changes runtime:

| Item | WebFlux | Web MVC |
| --- | --- | --- |
| Programming model | Reactive `ServerWebExchange`/Project Reactor | Servlet/WebMvc.fn |
| HTTP runtime | Reactor Netty | Appropriate Servlet container |
| Filter API | `GlobalFilter`, `GatewayFilter`, `WebFilter` | Handler Filter Functions/Servlet filters |
| Blocking library | Can block the event loop | Better suited for imperative code, though sizing is still required |
| Deployment | Netty runtime; not packaged as a traditional WAR | Can use a Servlet container |

Moving from WebFlux to Web MVC is an **architectural change**, not a one-line starter rename. You must re-check custom filters, security, connection pools, streaming, timeouts, WebSocket, and metrics.

## 11. Post-Upgrade Monitoring

### 11.1. Metrics to compare against baseline

| Metric/behavior | What to detect |
| --- | --- |
| Gateway request count by route | Routes stop matching or become duplicated |
| 4xx/5xx by route/outcome | Status mapping changes |
| Upstream latency p50/p95/p99 | HTTP client or backend regression |
| Retry attempts | Unexpected increase in attempts |
| Circuit breaker open/half-open | Failure threshold/slow calls shifted |
| LoadBalancer selection failures | Empty discovery list or supplier behavior |
| Connection pool pending acquire | Pool saturation |
| JVM heap/direct memory/GC | Buffering/codec/filter changes |
| TLS handshake failures | Truststore/SNI/protocol drift |
| CORS/redirect/auth errors | Browser contract broken |

### 11.2. Logs/traces

Record route ID, outcome, status, latency, upstream attempt count, and error category. Do not log Authorization, cookies, sensitive request bodies, or raw forwarded headers. Tracing helps correlate Gateway and backend, though it does not replace contract tests.

### 11.3. Canary

- Route only a fraction of traffic to the new Gateway.
- Compare p95/p99, 5xx, 429, retries, pool pressure, and backend load.
- Run synthetic requests for login, order creation, upload, streaming, and WebSocket.
- Verify every replica receives the same config and dependency versions.
- Increase traffic percentage after error budget and SLOs do not degrade.

## 12. Rollback and Configuration Compatibility

Rollback is not just reverting the Docker image to an older version.

Before upgrading, check:

- Can the old Boot/Gateway still understand the new config?
- Does Config Server have versioned releases/rollbacks?
- Do dynamic route definitions have new fields or new semantics?
- Did Redis/cache data change serialization/schema?
- Did JWT/session/cookie/forwarded-header policies change?
- Do external clients depend on new statuses/headers/bodies?
- Are database migrations backward-compatible?

With Gateway, pay special attention to route configuration and filter properties: if the new version moved to the `spring.cloud.gateway.server.webflux.*` namespace, the old version may not read the new configuration. Keep a rollback-compatible configuration or prepare two separate manifests, and verify with integration tests.

## 13. Lab Exercise: Build a Reviewable Upgrade Matrix

**Scenario:** A WebFlux Gateway currently uses Boot 3.5.x, Cloud 2025.0.x, and Gateway 4.3.x. The system uses `lb://ORDER-SERVICE`, a Redis rate limiter, JWT Resource Server, custom `GlobalFilter`, forwarded headers via ingress, and Reactor Netty.

### Requirements

1. Record current versions from the dependency tree, not just `pom.xml`.
2. Determine the Boot 4.2.x target and corresponding Cloud train.
3. Determine the Gateway version managed by the target BOM.
4. Check the support lifecycle of both current and target trains.
5. List Boot 4 changes: Java, Framework, Jakarta, modular starters, Jackson 3, property migration.
6. List Gateway changes: property namespaces, forwarded headers, starter/runtime, filter order.
7. Check CVE advisories and choose a patch release.
8. Update Maven or Gradle using the BOM, removing unnecessary version overrides.
9. Run the dependency tree and confirm no Spring Framework/Netty/Jackson conflicts.
10. Run tests for route predicates, filter order, body transformation, and path rewriting.
11. Test JWT/authorization, CORS, cookies, and forwarded proxy trust.
12. Test service discovery, LoadBalancer, Redis rate limiter, and circuit breaker.
13. Test TLS/mTLS, connect/response timeouts, and WebSocket/gRPC if used.
14. Test Actuator exposure and health/readiness.
15. Run a performance baseline/canary and write a rollback plan.

### Deliverable results table

| Item | Current | Target | Evidence | Status |
| --- | --- | --- | --- | --- |
| Boot | 3.5.x | 4.2.x | Effective POM/dependency tree | |
| Cloud train | 2025.0.x | 2026.0.x | BOM version | |
| Gateway | 4.3.x | 5.1.x | Resolved artifact | |
| Java/build tool | | | CI build | |
| Runtime | WebFlux | WebFlux | Startup/runtime test | |
| Gateway properties | old prefix | new prefix | Config binding/startup logs | |
| Forwarded headers | current policy | trusted proxies | Spoofing integration test | |
| Route/filter tests | | | WebTestClient/contract tests | |
| Discovery/LB | | | Mock/registry test | |
| Security/CVEs | | | Advisory checklist | |
| Performance | | | Load test report | |
| Rollback | | | Rollback rehearsal | |

### Acceptance criteria

~~~text
[PASS] Boot, Cloud train, and Gateway belong to the same compatibility line
[PASS] Versions are verified from the BOM/dependency tree
[PASS] Support lifecycle and Enterprise/OSS support are confirmed
[PASS] No unintended old starter/property prefixes remain
[PASS] No conflicting dependency overrides exist
[PASS] Gateway routes, predicates, and filter order are correct
[PASS] Discovery, load balancing, retry, and circuit breaker work properly
[PASS] Forwarded headers trust only designated proxies
[PASS] TLS, CORS, JWT, cookies, and WebSocket/gRPC match contract
[PASS] Security advisories and CVE fixes are addressed
[PASS] Tests, performance baseline, and canary pass
[PASS] Rollback config/image has been rehearsed
~~~

These are lab criteria; fill in the actual project results before production sign-off.

## 14. Checklist Before Selecting Production Versions

- [ ] Identify exact current Spring Boot, Spring Cloud BOM, and Gateway artifacts.
- [ ] Look up the Boot compatibility matrix for the Spring Cloud release train.
- [ ] Confirm the Gateway version belongs to the right train.
- [ ] Check whether the train still has OSS support or requires Enterprise Support.
- [ ] Select the latest compatible patch/service release.
- [ ] Check security advisories for Gateway, Spring Framework, Netty, Reactor, and Jackson.
- [ ] Check Java, Kotlin, Maven/Gradle, GraalVM, and container runtime requirements.
- [ ] Import the BOM instead of pinning individual project versions.
- [ ] Remove unnecessary version overrides.
- [ ] Inspect the dependency tree/effective POM.
- [ ] Read the Boot migration guide, Cloud release notes, and Gateway release notes.
- [ ] Migrate starters/property namespaces as appropriate.
- [ ] Check Jackson 3/JSpecify/Framework 7 when upgrading to Boot 4.
- [ ] Check custom filters and filter order.
- [ ] Check WebFlux vs Web MVC runtime assumptions.
- [ ] Check forwarded headers/trusted proxies and route configuration.
- [ ] Test service discovery, LoadBalancer, Redis, retry, and circuit breaker.
- [ ] Test request/response bodies, streaming, TLS, WebSocket, and gRPC if used.
- [ ] Test Actuator, auth, CORS, cookies, and redirects.
- [ ] Prepare before/after baseline metrics and test reports.
- [ ] Prepare canary, rollback image, and rollback config.

## 15. Summary and References

Before upgrading Spring Cloud Gateway, determine the **Spring Boot version first, select the compatible Spring Cloud Release Train next, and then take the Gateway version managed by the BOM**. Do not treat the version numbers of the three projects as an identical sequence, and do not confuse “dependencies resolve” with “supported”.

As of November 24, 2026, the main paths are Boot `4.2.x` + Cloud `2026.0.x` + Gateway `5.1.x`, or Boot `4.0.x`/`4.1.x` + Cloud `2025.1.x` + Gateway `5.0.x`. Boot `3.5.x` is compatible with Cloud `2025.0.x`/Gateway `4.3.x`, but the `2025.0.x` train is marked EOL OSS in the compatibility table; verify Enterprise Support if you continue maintaining it.

When moving to Boot 4/Gateway 5, check modular starters, Jackson 3, JSpecify, Spring Framework 7, property prefixes, forwarded headers, filter order, and security fixes. Finally, prove behavior via the dependency tree, integration tests, security tests, and canary/rollback rehearsals.

### Official references

- [Spring Cloud — Compatibility Matrix and Release Train Selection Guide](https://spring.io/projects/spring-cloud/).
- [Spring Cloud 2026.0.0 Release Train Reference](https://docs.spring.io/spring-cloud-release/reference/2026.0/index.html).
- [Spring Cloud 2025.1.5 Release Train Reference](https://docs.spring.io/spring-cloud-release/reference/2025.1/index.html).
- [Spring Cloud Supported Versions and support policy](https://github.com/spring-cloud/spring-cloud-release/wiki/Supported-Versions).
- [Spring Cloud 2026.0.0 Release Announcement](https://spring.io/blog/2026/11/20/spring-cloud-2026-0-0-has-been-released/).
- [Spring Cloud 2025.1 Release Notes](https://github.com/spring-cloud/spring-cloud-release/wiki/Spring-Cloud-2025.1-Release-Notes).
- [Spring Cloud 2025.0 Release Notes](https://github.com/spring-cloud/spring-cloud-release/wiki/Spring-Cloud-2025.0-Release-Notes).
- [Spring Cloud Gateway Releases](https://github.com/spring-cloud/spring-cloud-gateway/releases).
- [Spring Cloud Gateway 5.0 — How to Include Gateway Server WebFlux](https://docs.spring.io/spring-cloud-gateway/reference/5.0/spring-cloud-gateway-server-webflux/starter.html).
- [Spring Cloud Gateway 4.3 — How to Include Gateway Server WebFlux](https://docs.spring.io/spring-cloud-gateway/reference/4.3/spring-cloud-gateway-server-webflux/starter.html).
- [Spring Boot 4.0 Migration Guide](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.0-Migration-Guide).
- [Spring Boot 4.2.0 Release Announcement](https://spring.io/blog/2026/11/19/spring-boot-4-2-0-available-now/).
- [Spring Boot 4.2 System Requirements](https://docs.spring.io/spring-boot/system-requirements.html).

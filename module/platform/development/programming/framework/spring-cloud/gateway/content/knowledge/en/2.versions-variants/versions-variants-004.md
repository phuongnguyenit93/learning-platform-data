# Managing Dependencies with BOM and Avoiding Version Mixing in Spring Cloud Gateway

When building **Spring Cloud Gateway** as the entry point for a microservices system, the libraries involved do not operate in isolation: Gateway relies on Spring Boot, Spring Framework, WebFlux, Reactor/Netty, and may combine with Spring Cloud LoadBalancer, service discovery, Circuit Breaker, and Spring Security. If even a single critical library drifts from the jointly tested version set, the application may compile cleanly yet fail at startup or while handling requests.

This lesson focuses on the **BOM (Bill of Materials)**, how to choose a compatible version group, and how to detect and eliminate Spring Cloud Gateway version mixing. The goal is to keep the foundation stable before configuring route predicates, filter chains, path/header transformations, authentication, rate limiting, retries, circuit breakers, TLS, and traffic observability.

## 1. Why Does Gateway Need Coordinated Version Management?

Suppose a Gateway uses:

- Spring Boot for application startup, auto-configuration, and the Spring ecosystem;
- Spring Cloud Gateway for routing and executing the filter chain;
- Spring WebFlux, Reactor, and Reactor Netty for asynchronous HTTP handling;
- Spring Cloud LoadBalancer or a discovery client for forwarding to service instances;
- Spring Cloud Circuit Breaker, Resilience4j, Spring Security, and Micrometer depending on operational needs.

These components call each other's APIs both at startup and at runtime. If a project keeps Spring Cloud Gateway on an older release train while upgrading Spring Boot or Reactor/Netty independently, a method that Gateway expects may have changed its signature or no longer exist.

Some common symptoms:

| Symptom | Dependency-related cause to inspect |
| --- | --- |
| `NoSuchMethodError`, `NoClassDefFoundError`, `ClassNotFoundException` | A library was compiled against an API different from the actual version on the classpath. |
| Bean initialization / auto-configuration failure | Spring Boot, Spring Cloud, or starters do not belong to the same compatible group. |
| Gateway starts up, but `lb://...` routes cannot find instances | Missing LoadBalancer/discovery or misconfigured discovery; this is **not necessarily** a version error. |
| Failures when using filters, circuit breakers, retries, or TLS | Must distinguish business configuration errors from conflicts among Gateway, Spring Cloud, Reactor, Netty, or Resilience4j libraries. |
| Maven/Gradle picks a different version than expected | Manual version declaration, overlapping BOMs, or a transitive dependency pulling in another version. |

Key rule: **choose versions at the platform level, then let the BOM manage most dependencies belonging to that platform**.

## 2. What Is a BOM and What Does It Manage?

A **BOM** is a POM with packaging `pom` containing a set of **dependency management** rules for multiple libraries. It does not add those libraries to the application by itself; it provides default versions when a dependency is actually declared or pulled into the dependency tree.

For a Spring Cloud Gateway project, distinguish two groups:

| Management component | Role |
| --- | --- |
| **Spring Boot dependency management** (via parent/BOM or equivalent Gradle config) | Manages most versions of Spring Framework, Reactor, Netty, Jackson, Micrometer, Spring Security, test libraries, and common libraries integrated by Boot. |
| **`org.springframework.cloud:spring-cloud-dependencies`** | The BOM of a **Spring Cloud release train**, managing compatible versions of Spring Cloud projects including Gateway, LoadBalancer, Circuit Breaker, discovery clients, and related Cloud components. |

For example, when declaring `spring-cloud-starter-gateway` without `<version>`, Maven uses the version determined by the Spring Cloud BOM. Reactor/Netty versions should be governed by Spring Boot dependency management unless the release's official documentation specifies an explicit exception.

A BOM helps **align** versions; it does not automatically guarantee every combination is compatible. Directly declared versions, other dependency-management plugins, BOM import order/precedence, and the build tool's conflict resolution rules can still alter the final resolved version.

### Three Layers to Check

```text
Java runtime / toolchain
        |
        v
Spring Boot version X  -- manages Spring Framework, Reactor, Netty...
        |
        v
Spring Cloud release train Y -- manages Gateway, LoadBalancer, Circuit Breaker...
        |
        v
Application starters -- omit individual versions if managed by BOM
```

Do not infer compatibility just because two dependencies share a similar major number. **Spring Cloud versions use release train identifiers** (such as `2024.0.x`), while Spring Boot uses `3.4.x`, and Gateway itself has its own project version number (such as `4.2.x`).

## 3. Selecting the Spring Boot and Spring Cloud Pair Before Writing Dependencies

Version selection workflow:

1. Identify the Java version available in build and production environments.
2. Choose a Spring Boot line that meets project requirements.
3. Consult the **official Spring Cloud compatibility table** to pick the matching release train.
4. Check the Gateway documentation for that exact release train: starter for **WebFlux** or **Server MVC**, artifact names, and configuration changes.
5. Pick a supported patch release in the same line; update together in a tested batch rather than bumping Gateway/Reactor/Netty individually.

Example of a specific combination used **in this lesson**:

| Component | Example version | Notes |
| --- | --- | --- |
| Java | 17 | Baseline suitable for Spring Boot 3.x; projects may choose a newer Java if supported. |
| Spring Boot | `3.4.4` | Manages the foundational dependency group. |
| Spring Cloud | `2024.0.1` | Release train matching the Boot 3.4.x line. |
| Spring Cloud Gateway | Let the BOM decide | Do not manually insert `4.x.y` into the starter dependency. |

This is an **example for learning syntax**, not advice to use this specific patch version for a new system. When starting or upgrading a project, check the compatibility matrix, support policy, and current patches on [Spring Cloud release trains](https://spring.io/projects/spring-cloud) and [Spring Cloud Gateway documentation](https://docs.spring.io/spring-cloud-gateway/reference/).

**Note on variants:** within the example's release train context, `spring-cloud-starter-gateway` is the **WebFlux**-based Gateway starter. In newer release trains, starter names may change or more clearly distinguish **Gateway Server WebFlux** and **Gateway Server MVC**. Choose one variant according to your version's documentation; do not add both WebFlux and Server MVC starters thinking they act as redundant backups.

## 4. Maven Configuration: Spring Boot Parent and Spring Cloud BOM

Minimal `pom.xml` example for a WebFlux Gateway using the version pair above:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.4.4</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>edge-gateway</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
        <spring-cloud.version>2024.0.1</spring-cloud.version>
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
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-starter-gateway</artifactId>
        </dependency>

        <dependency>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-starter-loadbalancer</artifactId>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

Notice the following points:

- `spring-boot-starter-parent` manages versions for many Spring Boot dependencies; the build plugin also gets sensible defaults.
- `spring-cloud-dependencies` is **imported** under `<dependencyManagement>`, with `<type>pom</type>` and `<scope>import</scope>`. This is the mechanism for bringing the version set into the project, **not** a runnable library placed in `<dependencies>`.
- Spring Cloud starters have **no** `<version>`; the Spring Cloud BOM supplies their versions.
- `spring-cloud-starter-loadbalancer` only adds client-side load balancing. For a `lb://service-name` URI to work, the application also needs a source of service instances, such as a discovery client or appropriate instance configuration.

If an organization uses a custom corporate parent POM instead of `spring-boot-starter-parent`, you must still ensure Spring Boot's dependency management is imported properly and compatibly. Do not assume an internal parent automatically provides both BOMs.

### Inspecting the Versions Maven Actually Selects

Run in the project directory containing `pom.xml`:

```bash
./mvnw help:effective-pom
./mvnw dependency:tree
./mvnw dependency:tree -Dincludes=org.springframework.cloud
```

On Windows you can run `mvnw.cmd` instead. `help:effective-pom` shows the configuration after inheritance and BOM imports; `dependency:tree` shows which dependencies actually enter the classpath. If a library has an unexpected version, trace the direct declaration or transitive path bringing it in.

## 5. Gradle Configuration: Intentionally Importing the Cloud BOM

With Gradle Groovy DSL, a common approach is using the Spring Boot plugin and `io.spring.dependency-management` to import the Spring Cloud BOM:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.4.4'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

ext {
    set('springCloudVersion', '2024.0.1')
}

dependencyManagement {
    imports {
        mavenBom "org.springframework.cloud:spring-cloud-dependencies:${springCloudVersion}"
    }
}

dependencies {
    implementation 'org.springframework.cloud:spring-cloud-starter-gateway'
    implementation 'org.springframework.cloud:spring-cloud-starter-loadbalancer'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

In this configuration, the dependency-management plugin works with the Spring Boot plugin to manage Boot dependencies; the `imports` block declares the release train for Spring Cloud. Starters do not specify individual versions.

Gradle also has native BOM support via `platform(...)`; it can be used when the entire project's version strategy is built around Gradle dependency constraints. Avoid simultaneously mixing the plugin, multiple `platform`/`enforcedPlatform` declarations, and multiple `force` rules for the same library group without clearly understanding precedence: those mechanisms can yield resolution results different from what you expect.

### Inspecting the Versions Gradle Actually Selects

```bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-cloud-gateway --configuration runtimeClasspath
./gradlew dependencyInsight --dependency reactor-core --configuration runtimeClasspath
```

`dependencies` prints the dependency tree; `dependencyInsight` explains why a particular module was chosen, including relevant version constraints or conflicts. On Windows you can run `gradlew.bat`.

## 6. Common Version-Mixing Patterns That Cause Failures

### 6.1. Overriding the Gateway Starter Version

**Avoid:**

```xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-gateway</artifactId>
    <version>4.1.0</version>
</dependency>
```

This snippet can create an incompatible mix if the active release train manages a different version. It is also an easy numbering pitfall: the **starter** and **Gateway core modules** do not necessarily share the release train's version numbering scheme.

**Prefer:**

```xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-gateway</artifactId>
</dependency>
```

For BOM-managed dependencies, omit the version and let the build tool resolve it; then inspect the dependency tree to confirm.

### 6.2. Bumping Reactor, Netty, or Spring Framework Alone

For example, adding `reactor-netty-http` or `spring-webflux` with a pinned version to fix a bug can inadvertently change API/binary contracts that Gateway relies on. These libraries are normally managed by Spring Boot dependency management; prefer upgrading to a **compatible Spring Boot patch release** while reviewing the Spring Cloud BOM.

When forced to apply a specific security patch ahead of the upgrade schedule, document the exception clearly, inspect the dependency tree, test routes/filters/TLS, and plan to hand version control back to the BOM.

### 6.3. Mixing Two Spring Cloud Release Trains

An application using Gateway from release train A while forcing LoadBalancer or Circuit Breaker from release train B can hit API errors even though each library works fine in an isolated project.

**Fix:** pick exactly one Spring Cloud release train per Gateway application and let that BOM manage all Spring Cloud dependencies present in the app. If multiple BOMs overlap, check the effective POM or dependency resolution output to verify precedence rules.

### 6.4. Mixing WebFlux and Server MVC

Gateway WebFlux is built on the reactive model; Gateway Server MVC is built on the servlet stack. Adding both starters, or adding `spring-boot-starter-web` into Gateway WebFlux unintentionally, can cause auto-configuration and HTTP behavior to diverge from expectations.

**Fix:** choose the Gateway variant based on application architecture; verify starter names from the exact version's documentation, and keep web dependencies consistent with the chosen variant.

### 6.5. Overusing Dynamic Versions, SNAPSHOTs, and Overrides

Patterns like `+`, `latest.release`, `-SNAPSHOT`, `resolutionStrategy.force`, or manual version declarations scattered across submodules make builds hard to reproduce. Two builds from the same source may pull different library sets.

For production, use stable releases, lock the Boot/Cloud pair in a centralized place, store lockfiles if your build strategy calls for it, and only upgrade through reviewed changes.

## 7. Workflow for Resolving Version Conflicts

When Gateway fails at startup or on the first request, follow this workflow:

1. **Record the current state:** running Java version, Spring Boot plugin/parent, Spring Cloud BOM, Gateway starter names, dependency overrides, and the first root-cause error in the stack trace.
2. **Check compatibility:** compare the Boot/Cloud pair against the release train documentation. A compatibility error should never be fixed by disabling Spring Cloud's compatibility check.
3. **Inspect the actual classpath:** run `dependency:tree` (Maven) or `dependencyInsight` (Gradle) for the suspected library. Find the path pulling the unwanted version into the application.
4. **Remove unnecessary overrides:** delete explicit versions on Spring Cloud starters and foundational dependencies already managed by the BOM. Fix versions where they are centrally decided (parent/BOM/plugin) instead of patching scattered submodules.
5. **Rebuild and rerun:** verify application startup; test at least one HTTP route, predicate, path/header transformation filter, and enabled runtime features such as `lb://`, circuit breaker, retry, or TLS.
6. **Verify during upgrades:** run integration tests against a mock downstream service, checking HTTP status codes, headers, timeouts, retries, and fallback behavior. Watch logs/metrics to catch failures that only appear under load.

Example scenario:

> A stable running Gateway gets a circuit breaker filter added. A developer inserts the latest version of `spring-cloud-circuitbreaker-reactor-resilience4j` while keeping the old BOM. At startup, the Gateway throws class/method errors in Spring Cloud components.
>
> Resolution: first remove the explicit version on the Circuit Breaker library so it uses the version from the same release train, inspect the dependency tree, and retest. If a required feature only exists in a newer release train, upgrade the **Spring Boot + Spring Cloud pair** together per the compatibility table and rerun route, filter, and fallback tests.

## 8. Paired Upgrades and Regression Testing

To upgrade Gateway from one version set to a new one:

| Phase | Action items | Expected outcome |
| --- | --- | --- |
| Preparation | Read the compatibility matrix, release notes, Java requirements, and Gateway migration guides. | Identify the target Boot/Cloud pair and Gateway variant. |
| Update build | Upgrade Boot parent/plugin, Cloud BOM, and build plugins as needed; remove obsolete version overrides. | The BOM uniformly manages most dependencies. |
| Inspect dependency graph | Check `runtimeClasspath`/Maven dependency tree, especially Spring, Reactor, Netty, Gateway, LoadBalancer, Security, and Circuit Breaker. | No unintended versions pulled out of alignment. |
| Functional tests | Verify route predicates, filter chains, path/header rewrites, auth, rate limits, retries, circuit breakers, and active service discovery. | Request/response behavior matches or changes intentionally. |
| Operational tests | Test TLS, timeouts, connection failures, logs/tracing/metrics, and realistic load. | Solid evidence to deploy, observe, and roll back if needed. |

A minimal Gateway smoke test suite can include:

```text
GET /api/catalog/42
    -> route matches Path predicate
    -> filter modifies/strips prefix and forwards headers as configured
    -> upstream receives exact expected path/headers
    -> Gateway returns expected status, body, and tracing metadata

Upstream returns 5xx or times out
    -> retry/circuit breaker reacts per policy
    -> does not multiply calls unexpectedly
    -> logs and metrics record the failure
```

These tests do not prove every dependency is compatible, but they catch many real-world failures that a `compile` check never covers.

## 9. Self-Check Questions

**Does a BOM automatically download all Gateway dependencies?** No. A BOM declares version management rules; a dependency only enters the classpath when the application declares it or another dependency pulls it in transitively.

**If I already use the Spring Boot parent, do I still need the Spring Cloud BOM?** Yes, when using Spring Cloud dependencies and wanting to manage them by release train. The Spring Boot parent and Spring Cloud BOM manage two related dependency sets with distinct roles.

**Does specifying `<version>` directly on a starter always cause an error?** Not always immediately, but it can override the version aligned by the BOM and introduce upgrade risks.

**Does the application starting up prove the BOM is correct?** Not yet. Compatibility or configuration issues may only surface in routes, filters, `lb://`, TLS connections, retries, or under load.

**Should I disable the Spring Cloud Compatibility Verifier to make the app run?** Do not treat that as a fix. Move to a supported Boot/Cloud pair or thoroughly verify an exception backed by a sound technical reason.

## Conclusion

For Spring Cloud Gateway, **choosing a compatible Spring Boot and Spring Cloud pair, importing the right BOM, and letting starters inherit versions** is the safe and maintainable way to manage dependencies. After every change, inspect the actual resolved dependency tree and run tests through routes, filters, upstreams, and key operational features. A BOM reduces the risk of version mixing; real testing and observability confirm the Gateway behaves correctly in a microservices system.

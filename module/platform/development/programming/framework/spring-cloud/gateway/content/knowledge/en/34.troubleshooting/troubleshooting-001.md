# Application Fails to Start Due to Incompatible Starter, BOM, or Web Stack

## 1. Why Might Spring Cloud Gateway Fail to Start?

**Spring Cloud Gateway** is the API Gateway of the Spring ecosystem: routing requests using **route predicates**, executing the **GatewayFilter/GlobalFilter chain**, transforming paths/headers, performing service discovery, authentication, rate limiting, circuit breaking, retries, TLS, and request observability. The Gateway can only perform those functions when the **starter, Spring Boot, Spring Cloud Release Train, and web runtime** form a compatible dependency set.

Common startup failures do not originate from YAML routes or backends, but from the underlying foundation layer:

- Using **Spring Boot 4.2** with a Spring Cloud Release Train that only supports Boot 4.0/4.1.
- Adding the Spring Cloud BOM but forgetting to add the **Gateway starter**, so dependency versions are managed but Gateway features are absent from the classpath.
- Copying an old starter into a newer Gateway Server project, whereas current documentation uses separate starters for **WebFlux** and **Web MVC**.
- Accidentally bringing both Spring Boot Web and WebFlux into the same application. Spring Boot defaults to **Spring MVC** when both are present, whereas Gateway Server WebFlux requires **WebFlux + Reactor Netty**.
- Another dependency pulls in an incompatible version line of Spring MVC, Tomcat, Reactor Netty, or Spring Framework; the application may fail immediately at startup or throw a class linkage error when the first route executes.
- Deploying Gateway WebFlux as a **WAR** into an external Servlet container such as Tomcat, even though WebFlux Gateway Server requires a Netty runtime and does not support that deployment model.
- Explicitly setting versions on individual Spring Cloud/Spring Framework/Netty modules, accidentally overriding versions managed by the release train BOM.

**Lesson goal:** identify the exact layer causing the failure, prove it with the dependency graph and auto-configuration conditions, choose the right release train/starter/web stack, then make the minimal Maven/Gradle configuration fix and re-verify the runtime classpath.

> **Scope:** this lesson focuses on **Spring Cloud Gateway Server WebFlux** and contrasts it with **Server Web MVC**. Reference versions are updated according to official releases up to **2026-11-24**. Do not apply the version table to milestone/snapshot builds or out-of-scope enterprise support; always verify against the corresponding release train page before upgrading.

## 2. Identify the Correct Gateway Variant Before Fixing Dependencies

Spring Cloud Gateway has variants with different purposes. Do not start by adding a bunch of starters just to "see if it runs".

| Variant | Current Starter | Web Runtime | When to Choose |
|---|---|---|---|
| **Gateway Server WebFlux** | **spring-cloud-starter-gateway-server-webflux** | Spring WebFlux, Project Reactor, Reactor Netty | Reactive API Gateway, streaming, WebSocket, and WebFlux filter chain |
| **Gateway Server Web MVC** | **spring-cloud-starter-gateway-server-webmvc** | Spring WebMvc.fn, Servlet runtime such as Tomcat/Jetty | Servlet/imperative model Gateway |
| **Gateway Proxy Exchange** | Separate Proxy Exchange starters for WebFlux/MVC | WebFlux or MVC | A web application defining custom handlers and using ProxyExchange to proxy; not a full Server Gateway |

### 2.1. Gateway Server WebFlux

Official documentation requires the starter:

```xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-gateway-server-webflux</artifactId>
</dependency>
```

Gateway Server WebFlux is built on **Spring Boot, Spring WebFlux, and Project Reactor**; it requires the Netty runtime provided by Boot/WebFlux. The documentation explicitly states that this variant **does not run in a traditional Servlet container and cannot be packaged as a WAR**.

### 2.2. Gateway Server Web MVC

If the application intentionally uses Servlet/Tomcat/Jetty, the correct starter is:

```xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-gateway-server-webmvc</artifactId>
</dependency>
```

Gateway Server Web MVC is built on **Spring Boot and Spring WebMvc.fn**, working with Servlet runtimes such as Tomcat/Jetty. Reactive libraries or WebFlux-only patterns do not automatically apply to the MVC variant.

### 2.3. Do Not Add Both Starters to One Application as a Fix

```text
Avoid:
  spring-cloud-starter-gateway-server-webflux
  spring-cloud-starter-gateway-server-webmvc

Choose one:
  WebFlux Server -> Netty + WebFlux
  MVC Server    -> Servlet + WebMvc.fn
```

Putting both on the classpath can force Boot to pick one application type and produce an unintended set of auto-configurations. If you genuinely need two Gateways with two runtimes, split them into **two separate applications/deployments** with their own dependencies and configurations.

## 3. Check the Spring Cloud ↔ Spring Boot Matrix

### 3.1. Choose the Release Train According to Spring Boot

Spring Cloud uses a **Release Train** to manage modules of the same generation. The spring-cloud-dependencies BOM is neither the Spring Boot version nor the standalone Gateway version.

| Spring Cloud Release Train | Compatible Spring Boot | Typical Included Gateway Line | Notes |
|---|---|---|---|
| **2026.0.x – Paddington** | **4.2.x** | Gateway 5.1.x | 2026.0.0 GA is based on Boot 4.2.0; Gateway module 5.1.0 |
| **2025.1.x – Oakwood** | 4.0.x; 4.1.x from 2025.1.2 | Gateway 5.0.x | Do not use train versions before 2025.1.2 assuming support for all Boot 4.1.x |
| **2025.0.x – Northfields** | 3.5.x | Gateway 4.3.x | Boot 3.5 line |
| **2024.0.x – Moorgate** | 3.4.x | Gateway 4.2.x | Boot 3.4 line |
| **2023.0.x – Leyton** | 3.2.x; 3.3.x from 2023.0.2 | Gateway 4.1.x | Boot 3.2/3.3 line |
| **2022.0.x – Kilburn** | 3.0.x; 3.1.x from 2022.0.3 | Gateway 4.0.x | Older line; check support status before maintaining |

**How to read the table properly:**

- This table helps choose a **compatible line**, and does not replace the release notes/compatibility verifier of a specific service release.
- Gateway patch versions are managed by the release train BOM. For example, Spring Cloud 2026.0.0 includes Gateway 5.1.0; do not manually pick a different Gateway 5.1.x version from the BOM without reason and testing.
- Spring Cloud 2025.1.2 or later is required to extend support to Boot 4.1.x; the service release milestone matters, not just the 2025.1 number.
- **Compatible does not mean still under OSS support.** Older release trains may have reached end-of-life; check support status before deciding to stay on an older version.
- Do not pair Boot 4.2 with Spring Cloud 2025.1 or Boot 3.5 with Spring Cloud 2026.0 merely because the dependency resolver finds the artifacts on Maven Central.

### 3.2. Current Reference Pairs as of 2026-11-24

```text
Spring Boot 4.2.0
    + Spring Cloud 2026.0.0 (Paddington)
        + Spring Cloud Gateway 5.1.0

Spring Boot 4.0.x / 4.1.x
    + Spring Cloud 2025.1.x (Oakwood; 4.1.x from 2025.1.2)
        + Spring Cloud Gateway 5.0.x

Spring Boot 3.5.x
    + Spring Cloud 2025.0.x (Northfields)
        + Spring Cloud Gateway 4.3.x
```

These are illustrative pairs by release train; use the **latest supported service release** in the chosen line rather than copying patch versions from old examples. The Spring Cloud project page and Spring Cloud Release page are the official sources for verifying compatibility and module versions.

## 4. Correct Starter, Yet the Application Still Has No Gateway?

### 4.1. A BOM Only Manages Versions, It Does Not Add Dependencies

A very common mistake:

```xml
<!-- Importing the BOM only: NO Gateway starter on the classpath yet -->
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
```

dependencyManagement only **manages versions** when dependencies are declared; it does not add those dependencies to the runtime. You must add the starter inside dependencies:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-gateway-server-webflux</artifactId>
    </dependency>
</dependencies>
```

If you only import the BOM without the starter, the Boot application may start up like a normal app but **will not create a Gateway Server**, and will lack the expected route handlers/filters.

### 4.2. Using an Old Artifact from Outdated Documentation

Some older Gateway guides use:

```xml
<artifactId>spring-cloud-starter-gateway</artifactId>
```

Current Gateway Server documentation clearly separates the starters:

- **spring-cloud-starter-gateway-server-webflux**
- **spring-cloud-starter-gateway-server-webmvc**

Do not mix a legacy starter with a new BOM just because the artifact names look similar. When upgrading, read the **How to Include** page for the exact Gateway release; verify that the artifact exists and its version is managed by the BOM.

### 4.3. Confusing the Starter with a Core Module

The coordinates spring-cloud-gateway-server-webflux, spring-cloud-gateway-server-webmvc, and their corresponding starters do not serve the same role. In a standard application, use the **documented starter**, allowing it to pull in the required underlying modules. Do not replace the starter with a standalone core module and expect Boot to auto-configure the full runtime.

## 5. Maven: Proper BOM Configuration and Dependencies Without Explicit Versions

### 5.1. Standard Maven Example: Boot 4.2.0 + Cloud 2026.0.0

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.2.0</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>gateway</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>21</java.version>
        <spring-cloud.version>2026.0.0</spring-cloud.version>
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
            <artifactId>spring-cloud-starter-gateway-server-webflux</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-actuator</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
```

**Important points in the POM:**

1. spring-boot-starter-parent manages Spring Boot/Spring Framework versions and plugin defaults.
2. spring-cloud-dependencies imports the **Release Train BOM** to manage Spring Cloud modules.
3. spring-cloud-starter-gateway-server-webflux **has no explicit version**; the version comes from the BOM.
4. spring-boot-starter-actuator is optional depending on observability needs; it is not required for Gateway routes to work.
5. Do not add spring-boot-starter-web to a WebFlux application just to use annotation controllers. WebFlux also supports annotation-based controllers.

If you use the Spring Boot BOM instead of the Boot parent, you still need to import both the Boot BOM and the Spring Cloud BOM in a clear structure. **Do not import multiple different Spring BOMs and then manually add versions to foundational modules** without understanding dependency management precedence.

### 5.2. Common POM Mistakes

```xml
<!-- WRONG: setting an explicit Gateway version, which may diverge from the Release Train BOM -->
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-gateway-server-webflux</artifactId>
    <version>5.0.5</version>
</dependency>

<!-- WRONG: forcing a standalone Spring Framework version outside the Boot BOM -->
<dependency>
    <groupId>org.springframework</groupId>
    <artifactId>spring-webflux</artifactId>
    <version>7.0.9</version>
</dependency>
```

When using a BOM, avoid manually overriding:

- Spring Cloud Gateway/Commons/LoadBalancer modules.
- Spring Framework spring-core, spring-context, spring-webflux, spring-webmvc.
- Reactor reactor-core, reactor-netty.
- Netty modules.
- Spring Security modules.

If a different patch version is needed for a CVE fix or workaround, you must check the **compatibility matrix of the entire dependency graph**, document the reason clearly, and run integration tests. Never just force a single artifact and hope the binary APIs remain compatible.

### 5.3. BOM Import Order and Explicit Versions

Maven manages dependencies via the effective POM and dependency mediation. When multiple BOMs manage the same artifact, the import order or explicit dependencyManagement entries can alter the final version; a version declared directly on a dependency can also override the version proposed by a BOM.

Practical rules:

1. Choose **one Boot parent/BOM** and **one Spring Cloud release train BOM**.
2. Set the train version in a single property, such as spring-cloud.version.
3. Do not import additional Spring Framework/Reactor/Netty BOMs unless there is clear documentation and justification.
4. Do not declare an explicit version on the Gateway starter.
5. Inspect the **effective POM** and dependency tree instead of guessing from what is visible in pom.xml.

## 6. Gradle: Import the Release Train BOM Once

### 6.1. Gradle Groovy DSL with the Dependency Management Plugin

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '4.2.0'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories {
    mavenCentral()
}

ext {
    set('springCloudVersion', '2026.0.0')
}

dependencyManagement {
    imports {
        mavenBom "org.springframework.cloud:spring-cloud-dependencies:${springCloudVersion}"
    }
}

dependencies {
    implementation 'org.springframework.cloud:spring-cloud-starter-gateway-server-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

### 6.2. Common Gradle Mistakes

- Setting an explicit version on the Gateway starter even though the Spring Cloud BOM is imported.
- Using resolutionStrategy.force to pin spring-webflux, spring-core, Reactor, or Netty.
- A version catalog (libs.versions.toml) holding a different version from the BOM.
- Having multiple platform/BOM imports managing the same dependency without checking dependencyInsight.
- The Gradle daemon running a different JDK than the Java toolchain/compiler, causing the build to succeed while bootRun or the container runtime fails.

Gradle may resolve versions according to its resolution strategy; the final result must be inspected via dependencyInsight rather than inferred from initial declarations.

### 6.3. Equivalent Gradle Kotlin DSL

```kotlin
plugins {
    java
    id("org.springframework.boot") version "4.2.0"
    id("io.spring.dependency-management") version "1.1.7"
}

group = "com.example"
version = "1.0.0"

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories {
    mavenCentral()
}

extra["springCloudVersion"] = "2026.0.0"

dependencyManagement {
    imports {
        mavenBom(
            "org.springframework.cloud:spring-cloud-dependencies:" +
                property("springCloudVersion")
        )
    }
}

dependencies {
    implementation("org.springframework.cloud:spring-cloud-starter-gateway-server-webflux")
    implementation("org.springframework.boot:spring-boot-starter-actuator")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
}
```

Choose **one** DSL (Groovy or Kotlin) and one BOM management approach. Do not copy both into the same build.

## 7. Web Stack Conflict: Boot Selects Spring MVC Instead of WebFlux

### 7.1. Spring Boot's Auto-Detection Rule

Spring Boot detects the application type based on the classpath. When only WebFlux is present, Boot configures a reactive application. When both Spring MVC and Spring WebFlux are present, Boot defaults to **Spring MVC**. This behavior exists because many MVC applications add WebFlux solely to use the reactive WebClient.

```text
spring-cloud-starter-gateway-server-webflux
    -> Spring WebFlux + Reactor Netty

spring-boot-starter-web
    -> Spring MVC + Servlet API + Tomcat (default)

Both present together:
    -> Boot defaults to Spring MVC
    -> Gateway Server WebFlux lacks the proper runtime
```

### 7.2. Which Dependencies Typically Pull In Spring MVC?

| Dependency/Group | Can Pull In | How to Handle with Gateway WebFlux |
|---|---|---|
| spring-boot-starter-web | Spring MVC, embedded Tomcat | Remove from the application if Servlet is not needed |
| spring-boot-starter-tomcat | Servlet container | Do not use as the server for Gateway WebFlux |
| spring-webmvc | Spring MVC APIs/auto-configuration | Find which dependency pulls it in; do not exclude blindly |
| spring-boot-starter-webflux | WebFlux, Reactor Netty server starter per config | Usually already pulled in by the Gateway WebFlux starter |
| spring-boot-starter-reactor-netty | Reactor Netty | Netty runtime is required for Gateway WebFlux |
| spring-cloud-starter-gateway-server-webmvc | Gateway MVC/WebMvc.fn | Use when choosing Servlet Gateway; do not add alongside WebFlux Server |

A library dependency can pull in Spring MVC transitively even when the application POM does not declare it directly. Therefore, inspect the **runtime dependency tree**, not just the direct dependencies section.

### 7.3. Proper Fix When You Want Gateway WebFlux

Remove the MVC/Servlet starter from the Gateway application and keep the WebFlux starter:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-gateway-server-webflux</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>
</dependencies>
```

If an internal library pulls in the MVC starter, trace the dependency path with Maven/Gradle and **fix the offending module** or exclude only the unneeded dependency. Do not exclude entire Spring Framework/Servlet packages indiscriminately, as that can break another library.

### 7.4. Can You Force the Application Type to Reactive?

Spring Boot provides the property:

```yaml
spring:
  main:
    web-application-type: reactive
```

This property can force Boot to create a reactive application context when both MVC and WebFlux are present. It is useful for **verifying a hypothesis** in an application that has a valid reason to keep both APIs. However, for Gateway Server WebFlux:

- Gateway documentation requires the Netty runtime.
- A Servlet dependency remaining on the classpath can still bring along inappropriate auto-configuration, filters, and beans.
- Deploying to an external Servlet container/WAR still does not become a valid WebFlux Gateway just because of this property.

**Root fix:** remove the unneeded MVC/Servlet dependency and let the Gateway WebFlux starter set up the proper runtime. Only keep the reactive override property if the architecture is intentionally designed for it and verified by integration tests.

### 7.5. If the Application Genuinely Needs Servlet/Tomcat

Choose Gateway Server Web MVC:

```xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-gateway-server-webmvc</artifactId>
</dependency>
```

Do not add the Gateway WebFlux starter just to gain extra filter/reactive APIs. Check the Gateway features, Java route/filter APIs, and supported libraries of **Server Web MVC**; not every WebFlux GatewayFilter works as-is in MVC.

## 8. Check Java, Maven/Gradle, and the Actual Runtime

### 8.1. Build JDK and Runtime JDK Can Differ

A project may compile with a newer JDK while the container or IDE runs with an older JDK. Check:

```bash
java -version
mvn -version
./mvnw -version
./gradlew -version
```

These commands show the JVM used by the shell, Maven, and the Gradle daemon. If using a toolchain, check the selected toolchain in the build log as well as the runtime image/container.

### 8.2. Class Version Errors

If the log contains:

```text
UnsupportedClassVersionError
class file version XX.0
runtime only recognizes up to YY.0
```

The class was compiled with a newer Java version than the runtime executing it. Check:

1. Java toolchain in Maven/Gradle.
2. JAVA_HOME in CI, IDE, shell, and container.
3. JRE image in the Dockerfile.
4. Maven compiler release/source/target if overridden.
5. Build caches holding artifacts compiled with another JDK.

Do not just change JAVA_HOME in one terminal and forget to configure the JDK for the IDE or Gradle daemon.

### 8.3. Do Not Confuse Java Version with Spring Version

| Symptom | What to Check |
|---|---|
| UnsupportedClassVersionError | Java runtime is older than the bytecode |
| NoSuchMethodError in Spring | Spring Framework modules have mismatched versions |
| NoClassDefFoundError Reactor/Netty | Runtime dependency missing or excluded |
| Spring Cloud compatibility verifier fails | Boot and Spring Cloud Release Train are incompatible |
| Build tool fails to recognize plugin | Maven/Gradle wrapper, plugin version, and build tool JDK |

Java 21 in the sample POMs is an illustrative toolchain choice; choose a Java version within the requirements of the Spring Boot release you use and keep it consistent across CI and runtime.

## 9. Read Startup Errors Correctly and Map Them to Root Causes

| Log Symptom | Common Cause | Verification Step |
|---|---|---|
| Spring Cloud compatibility verifier reports incompatible Boot version | Wrong Release Train BOM selected | Check the Boot ↔ Cloud matrix; do not disable the verifier to hide the error |
| NoSuchMethodError in org.springframework.* | Spring Framework modules are from different lines | Maven dependency tree / Gradle dependencyInsight; find version overrides |
| NoClassDefFoundError for org.springframework.web.reactive.* | WebFlux missing or excluded | Check Gateway starter and runtimeClasspath |
| NoClassDefFoundError for reactor.netty.http.server.HttpServer | Reactor Netty server runtime missing/excluded | Check WebFlux starter, dependency exclusions, and jar packaging |
| Boot initializes ServletWebServerApplicationContext instead of reactive | spring-boot-starter-web/spring-webmvc is still on the classpath | Find the dependency pulling in MVC; choose the right Gateway flavor |
| Missing ServletWebServerFactory when forcing Servlet | Application type is SERVLET without a matching Servlet server | Choose MVC starter/runtime or remove application type override |
| Gateway is absent while app starts normally | Only BOM imported, Gateway starter not declared | Add the proper starter under dependencies |
| Could not resolve artifact | Wrong group/artifact/version/repository or using milestone without repo | Verify coordinates, Maven Central/repository, and release docs |
| BeanDefinitionOverrideException | Duplicate starter/auto-config or conflicting custom bean | Find bean name and config source; do not enable global overriding immediately |
| NoSuchBeanDefinitionException for reactive server/handler | Web stack or auto-configuration did not run | Check application type and condition report |
| NoSuchMethodError appears only on the first request | Binary version mismatch in a code path not loaded at startup | Dependency graph + real route smoke test |
| App runs in IDE but fails in jar | Runtime packaging/classpath differs from IDE | Check BOOT-INF/lib inside executable jar and java -jar command |
| App runs locally but fails in container | Different JDK/base image, profile, env, or dependency packaging | Compare runtime Java, active profiles, and image artifact |

**Rule:** preserve the **first meaningful exception** and original stack trace. Subsequent errors are often just downstream consequences after the Spring context has already failed. Do not start fixing the last bean in the stack if the real cause is a version mismatch at the top of the log.

## 10. Dependency Graph Diagnostic Workflow

### 10.1. Maven: Inspect the Effective POM and Dependency Tree

Run inside the directory containing the Maven wrapper/POM:

```bash
./mvnw -version

# POM after merging parent, properties, and imported BOMs.
./mvnw help:effective-pom -Doutput=target/effective-pom.xml

# Full runtime/compile dependency tree, including transitive paths.
./mvnw dependency:tree -Dverbose

# Filter Spring Cloud/Spring Boot groups if needed.
./mvnw dependency:tree -Dverbose \
  -Dincludes=org.springframework.cloud:*,org.springframework.boot:*

# Find web stack and Reactor/Netty modules.
./mvnw dependency:tree -Dverbose \
  -Dincludes=org.springframework:*,io.projectreactor:*,io.netty:*
```

**What to look for in the output:**

- Is the right Gateway starter present?
- Is there more than one version of Spring Cloud Gateway/Commons/LoadBalancer?
- Are Spring Boot artifacts on the same version line?
- Are Spring Framework artifacts on the same version line?
- Are both spring-webmvc and spring-webflux present?
- Are reactor-netty-http and the corresponding server runtime present?
- Which dependency pulls in Tomcat/Servlet/MVC?
- Is any dependency marked omitted for conflict with an unwanted version?

The effective POM file is evidence of the **final dependencyManagement**. If a starter in the POM has no version yet the dependency tree resolves a strange version, locate the parent/BOM/property managing it.

### 10.2. Gradle: Use dependencies and dependencyInsight

```bash
./gradlew -version

# Entire runtime classpath.
./gradlew dependencies --configuration runtimeClasspath

# Who pulls in the Gateway WebFlux starter and which version is selected?
./gradlew dependencyInsight \
  --dependency spring-cloud-starter-gateway-server-webflux \
  --configuration runtimeClasspath

# Find what pulls in Spring MVC.
./gradlew dependencyInsight \
  --dependency spring-webmvc \
  --configuration runtimeClasspath

# Find what pulls in Servlet/Tomcat.
./gradlew dependencyInsight \
  --dependency spring-boot-starter-tomcat \
  --configuration runtimeClasspath

# Check Reactor Netty.
./gradlew dependencyInsight \
  --dependency reactor-netty-http \
  --configuration runtimeClasspath
```

Gradle dependencyInsight shows the **selected version**, candidate versions, and dependency path. Fix the dependency path pulling in the conflicting version; avoid adding resolutionStrategy.force before understanding the cause.

### 10.3. Inspect the Executable Jar

When the application runs in the IDE but fails from the jar:

```bash
jar tf target/gateway.jar | grep 'BOOT-INF/lib'

# Filter the web/runtime modules to inspect.
jar tf target/gateway.jar | grep -E \
  'BOOT-INF/lib/(spring-cloud-gateway|spring-boot-starter-web|spring-boot-starter-webflux|spring-webmvc|spring-webflux|reactor-netty|tomcat)'
```

If using PowerShell, you can replace grep with Select-String. For a Boot executable jar, dependencies reside inside BOOT-INF/lib. Inspect the actual deployed jar rather than relying solely on the IDE dependency tree.

### 10.4. Routes Are Not the First Step

If the application cannot even create an ApplicationContext or web server, route predicates, filters, backend DNS, and upstream TLS are **not the first place to investigate**. The sequence should be:

1. Build tool/JDK.
2. BOM/release train.
3. Starter/coordinate.
4. Web application type/runtime.
5. Auto-configuration/context startup.
6. After the app starts: route definitions, filters, upstream connection.

## 11. Use the Condition Evaluation Report to Find Skipped Auto-Configurations

### 11.1. Enable Debug at Runtime

```bash
# Maven Spring Boot plugin
./mvnw spring-boot:run -Dspring-boot.run.arguments=--debug

# Gradle
./gradlew bootRun --args='--debug'

# Executable jar
java -jar target/gateway.jar --debug
```

Spring Boot prints the **Condition Evaluation Report** explaining which auto-configurations matched or did not match. Look for sections related to:

- Gateway Server WebFlux auto-configuration.
- WebFlux/Reactive web server auto-configuration.
- Servlet/MVC auto-configuration.
- Reactor Netty server factory.
- Conditions based on classpath and application type.

### 11.2. How to Read the Report

| Report Shows | Interpretation |
|---|---|
| Gateway WebFlux auto-config did not match due to missing class | Starter/core module is missing or excluded |
| Gateway WebFlux auto-config did not match due to web application type | Boot is running SERVLET/NONE instead of REACTIVE |
| Servlet auto-config matched in an intended WebFlux app | spring-webmvc/starter-web may be on the classpath |
| Reactive server factory missing | Check Reactor Netty starter/runtime and exclusions |
| Gateway auto-config matched but route list is empty | Starter is present; move on to checking route configuration/profile |

**Do not expose all Actuator endpoints just to read the condition report.** Startup debug logs are sufficient in most cases; if using the Actuator conditions endpoint, protect access and never expose it publicly.

### 11.3. Verify Application Type via Configuration

You can temporarily set:

```yaml
spring:
  main:
    web-application-type: reactive
```

If the application starts running when reactive is forced, that is strong evidence that **web stack detection/classpath** is wrong. Then return to the dependency tree and remove the unnecessary Servlet dependency; do not keep the override merely to mask a conflict without verifying Netty/runtime.

## 12. Minimal Application and Smoke Test After Fixing

### 12.1. Minimal Main Class

Gateway Server WebFlux does not need a special annotation to "enable Gateway"; the starter and auto-configuration handle this:

```java
package com.example.gateway;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class GatewayApplication {

    public static void main(String[] args) {
        SpringApplication.run(GatewayApplication.class, args);
    }
}
```

Avoid adding arbitrarily:

```java
@EnableWebMvc
@SpringBootApplication
public class GatewayApplication {
    // Not suitable for Gateway Server WebFlux.
}
```

@EnableWebMvc requests Spring MVC configuration. In a WebFlux Gateway application, this annotation can break the intended web stack. @EnableWebFlux also hands WebFlux configuration control back to the application and may disable some default Boot auto-configurations. Only use it when you genuinely intend to manage the entire web configuration yourself and understand the impact.

### 12.2. Minimal Route Smoke Test

Once the context starts, add a test route pointing to a hypothetical backend:

```yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: startup-smoke
              uri: http://localhost:8081
              predicates:
                - Path=/smoke/**
              filters:
                - StripPrefix=1
```

This route is strictly a **post-startup smoke test** and does not require the backend to be running to create the ApplicationContext. When sending a request, if the backend is not running you may receive 502/503/connection refused; that is an upstream error, no longer a BOM/starter issue.

### 12.3. Test Only Verifying That the Spring Context Starts

```java
package com.example.gateway;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class GatewayApplicationStartupTest {

    @Test
    void applicationContextStarts() {
        // Test passes when the context and reactive server start successfully.
    }
}
```

This test catches many starter/web stack/BOM issues before deployment. However, it does not prove that a route actually proxies traffic or that lazy-loaded dependencies have no errors; add an integration smoke test calling a route once a backend stub is ready.

### 12.4. Re-Run After Fixing Dependencies

```bash
# Maven: verify compile/test/package from a clean state.
./mvnw clean verify

# Gradle: verify compile/test.
./gradlew clean test

# Run the app with the debug report in a sandbox.
./mvnw spring-boot:run -Dspring-boot.run.arguments=--debug
```

Do not wipe the entire Maven/Gradle cache reflexively. Only refresh/update dependencies when there is evidence that cached/repository metadata is stale; if the dependency graph itself is wrong, re-downloading the cache will not fix a version conflict.

## 13. Typical Startup Errors and Step-by-Step Fixes

### 13.1. Compatibility Verifier Reports Incompatible Spring Boot

For example, the log contains something like:

```text
Spring Boot [4.2.0] is not compatible with this Spring Cloud release train
```

Cause: the Spring Cloud BOM in use does not support that Boot line.

**Fix:**

1. Record the exact Boot version in the effective POM/Gradle runtimeClasspath.
2. Identify which Spring Cloud release train BOM is actually being imported.
3. Check the compatibility matrix and service release.
4. Pick a compatible pair, such as Boot 4.2.x + Cloud 2026.0.x or Boot 4.0/4.1 + Cloud 2025.1.x per the support milestone.
5. Let the BOM manage Gateway/Commons/LoadBalancer modules without forcing explicit versions.
6. Run clean verify and a smoke test.

Do not disable the compatibility verifier using:

```yaml
spring:
  cloud:
    compatibility-verifier:
      enabled: false
```

This property may suppress the compatibility warning/check, but it **does not make incompatible binary APIs compatible**. Only use it when the Spring support team or release notes specify a controlled exception, accompanied by thorough testing.

### 13.2. NoSuchMethodError or AbstractMethodError

Example:

```text
java.lang.NoSuchMethodError:
  org.springframework.web.server.ServerWebExchange.someMethod(...)

java.lang.AbstractMethodError:
  Receiver class ... does not define ...
```

This usually indicates that code was compiled against one API version while another version is loaded at runtime. Causes:

- Boot parent/BOM and Cloud BOM belong to different generations.
- A starter has an explicit version declared.
- A library transitively pulls in a different Spring Framework/Reactor/Netty version.
- Gradle force/constraint/version catalog overrides the BOM.
- The fat jar contains different dependencies from the IDE dependency tree.

**How to handle:** find the artifact owning the class in the stack trace, run dependency tree/dependencyInsight, identify the dependency path pulling in the loaded version, then remove the override or upgrade/downgrade the dependency at the proper layer. Do not fix it by appending another dependency of the same class with a newer version at the bottom of the POM.

### 13.3. NoClassDefFoundError for WebFlux or Reactor Netty

Example:

```text
java.lang.NoClassDefFoundError: org/springframework/web/reactive/...
java.lang.NoClassDefFoundError: reactor/netty/http/server/HttpServer
```

Check:

1. The correct Gateway Server WebFlux starter is declared under dependencies.
2. The dependency has the proper runtime/compile scope, not just test scope.
3. No exclusion accidentally strips Spring WebFlux or Reactor Netty.
4. The packaged jar actually includes the required modules in BOOT-INF/lib.
5. The WebFlux Gateway application is not being deployed as a WAR in a Servlet container.

If you need WebClient in an MVC application, adding WebFlux client libraries does not make the application a WebFlux Gateway. Distinguish a **client library** from a **reactive server runtime**.

### 13.4. Boot Selects Servlet Application Context

Symptoms:

- Logs show a Servlet web server/application context.
- The application attempts to initialize a Tomcat/Servlet container.
- Gateway WebFlux auto-configuration does not match due to application type.

**Fix:**

1. Run dependencyInsight for spring-webmvc and spring-boot-starter-web.
2. Locate the direct or transitive dependency pulling in MVC/Tomcat.
3. If MVC is not needed, remove that starter/dependency.
4. Keep the Gateway Server WebFlux starter and Reactor Netty.
5. Only use spring.main.web-application-type=reactive as a diagnostic tool or intentional configuration, never as a substitute for cleaning up the dependency graph.

### 13.5. Embedded Server Factory Not Found

If the log states there is no reactive server factory or Netty server cannot be created:

- Verify the Reactor Netty server dependency is on the runtime classpath.
- Check whether spring-boot-starter-reactor-netty was excluded.
- Check whether a custom server starter replaced the default server.
- Check whether a build profile/container build omitted libraries during packaging.
- Cross-check Boot/Reactor Netty versions against the BOM.

Do not add the Tomcat starter just to "have some server" if the goal is Gateway WebFlux; Gateway requires the Netty runtime.

### 13.6. App Starts but Has No Gateway Routes

This is not necessarily a web stack issue. Check:

1. Is the starter actually on the runtime classpath, or was only the BOM imported?
2. Does the route config use the right prefix for the Gateway release?
3. Does the active profile contain the routes?
4. Is Gateway disabled via a property?
5. Are route definitions supposed to be loaded from Config Server/discovery source?

In newer releases, the Server WebFlux prefix typically starts with spring.cloud.gateway.server.webflux; older lines may use spring.cloud.gateway. Read configuration properties for the **exact version**, and do not mix 4.x and 5.x YAML.

## 14. Diagnostic Runbook from First Error to Fix

### 14.1. Gather Minimum Evidence

Before changing dependencies, record:

- Actual Spring Boot version.
- Actual Spring Cloud Release Train BOM.
- Selected Spring Cloud Gateway module version.
- Maven/Gradle JDK and runtime JDK.
- Web application type: reactive or servlet.
- Runtime server: Reactor Netty or Tomcat/Jetty.
- First stack trace and Condition Evaluation Report.
- Build tool and active profile.

Do not paste all environment variables or secrets into a ticket. Redact credentials/URLs containing tokens and private hostnames when sharing logs.

### 14.2. Sequence of Actions

```text
1. Clarify intent:
   WebFlux Gateway or MVC Gateway?

2. Check compatibility:
   Spring Boot -> Spring Cloud release train -> Gateway module.

3. Check starter:
   right artifact? present on runtimeClasspath? BOM only manages versions?

4. Check web stack:
   WebFlux + Netty? or MVC + Servlet?
   Any unintended spring-webmvc/Tomcat?

5. Check version mediation:
   effective-pom / dependencyInsight / dependency tree.

6. Check runtime artifact:
   executable jar has right libs? right JDK?

7. Fix one root cause at a time:
   do not force versions in bulk.

8. Run clean verify + context startup test.

9. Run route smoke test against a backend stub.

10. Document the verified version pair and dependency policy.
```

### 14.3. Before and After Example

**Before — Boot 4.2 + Cloud 2025.1 + both web stacks:**

```xml
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>4.2.0</version>
</parent>

<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-gateway-server-webflux</artifactId>
    <version>5.0.5</version>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>
```

Issues: Boot 4.2 requires Cloud 2026.0.x; starter 5.0.5 has a forced version belonging to a different Gateway line; the MVC/Servlet starter was added unintentionally.

**After — Boot 4.2 + Cloud 2026.0 + WebFlux Gateway:**

```xml
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>4.2.0</version>
    <relativePath/>
</parent>

<properties>
    <spring-cloud.version>2026.0.0</spring-cloud.version>
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
        <artifactId>spring-cloud-starter-gateway-server-webflux</artifactId>
    </dependency>
</dependencies>
```

Expected result: Cloud BOM manages the matching Gateway 5.1.x; Boot detects the reactive stack; the Netty server starts. You must still inspect the runtime tree and run a smoke test rather than trusting the POM alone.

## 15. Pitfalls When Upgrading from Older Gateway Projects

### 15.1. Changing Only the Spring Boot Version While Keeping the Same Spring Cloud BOM

Spring Boot and Spring Cloud follow corresponding release trains. Upgrading Boot major/minor without upgrading the matching Cloud BOM can cause:

- Compatibility verifier failure immediately at startup.
- Spring Framework binary API mismatch.
- Changed auto-configuration conditions.
- Starter/artifact or package migrations.

Upgrade in release train pairs and read the release notes for **all Spring Cloud modules** in use, not just Gateway.

### 15.2. Copying a Starter from an Old Tutorial

Old tutorials may use spring-cloud-starter-gateway. New Gateway Server documentation uses separate WebFlux/Web MVC starters. Do not mix legacy dependencies with new properties/prefixes.

### 15.3. Keeping spring-boot-starter-web Just to Use Controllers

Spring WebFlux also supports annotation controllers (RestController, GetMapping) and functional endpoints. There is no need to add the MVC starter just to write controllers.

If the service genuinely needs the Servlet model, consider switching the entire Gateway to **Server Web MVC** or separating the API application from the Gateway deployment. Do not force a hybrid runtime without good reason.

### 15.4. Deploying WebFlux Gateway as a WAR

Gateway Server WebFlux requires a Netty runtime and does not run in a traditional Servlet container/WAR. If the organization mandates WAR deployment on Tomcat/Jetty, choose Server Web MVC or another appropriate proxy architecture.

### 15.5. Manually Pinning Reactor/Netty After Seeing a Runtime Error

Spring Cloud Gateway WebFlux relies on Spring Boot, Spring Framework, Reactor, and Netty. Pinning an individual module can create a binary mixture that is hard to diagnose. Trace version conflicts through the dependency graph first, and only override when release notes/support specify the exact version and scope.

## 16. CI Checklist to Prevent Regression

- [ ] Only **one** Gateway Server flavor is present on the runtime classpath.
- [ ] Boot version is within the Spring Cloud Release Train compatibility matrix.
- [ ] Gateway starter matches the flavor and has no explicit version override.
- [ ] BOM imports exactly one release train without arbitrarily mixing other Spring BOMs.
- [ ] No unintended Spring MVC/Tomcat is present in a WebFlux Gateway.
- [ ] Reactor Netty runtime is present when using Gateway Server WebFlux.
- [ ] Java toolchain, Maven/Gradle daemon, and runtime image use compatible JDKs.
- [ ] Dependency tree/dependencyInsight is checked during major/minor upgrades.
- [ ] Effective POM is archived as a CI artifact when needed for auditing.
- [ ] Executable jar contains the proper runtime dependencies.
- [ ] Context startup test runs in CI.
- [ ] Route smoke test confirms proxying works after the context starts.
- [ ] Compatibility verifier is not disabled just to turn the pipeline green.
- [ ] Dedicated checks run against the Docker/production image, not just the IDE classpath.

## 17. Symptoms and Quick Fixes Table

| Symptom | First Check | Quick Fix |
|---|---|---|
| Compatibility verifier fails | Boot version + Cloud BOM | Select a compatible release train |
| No Gateway routes | Is Gateway starter in runtime tree? | Add the right starter, check property prefix/profile |
| Boot chooses Servlet | Is spring-webmvc/Tomcat in runtime? | Remove MVC dependency or choose Gateway MVC |
| No Netty server | Is reactor-netty-http present? | Fix starter/exclusion and runtime packaging |
| NoSuchMethodError | Which Spring Framework/Reactor version is loaded? | Align BOM, remove version override |
| NoClassDefFoundError | Was a module excluded or given wrong scope? | Restore proper runtime dependency |
| BeanDefinitionOverrideException | Duplicate starter/auto-config/bean? | Choose one flavor, resolve specific bean conflict |
| UnsupportedClassVersionError | Build JDK vs runtime JDK | Align toolchain and container JRE |
| Works in IDE, fails java -jar | BOOT-INF/lib and active profile | Inspect packaged jar/runtime config |
| Works locally, fails in container | JDK/image/env/profiles | Compare actual runtime environments |
| Build passes, first request fails | Lazy linkage/classpath conflict | Dependency tree + route integration test |
| Gateway MVC runs but WebFlux filters are missing | Confused the two server flavors | Use APIs/filters matching the variant |

## 18. Self-Check Questions and Answers

**Exercise 1 — Does a BOM automatically add Gateway?** Import spring-cloud-dependencies without declaring a starter. Does the application have a Gateway Server?

**Answer:** no. A BOM only manages versions; you must declare the Gateway starter in dependencies.

**Exercise 2 — Which Cloud train does Boot 4.2.0 use?**

**Answer:** Spring Cloud 2026.0.x (Paddington); 2026.0.0 GA is based on Boot 4.2.0.

**Exercise 3 — From which version can Boot 4.1.x use Cloud 2025.1.x?**

**Answer:** from Spring Cloud 2025.1.2 onward per the release train compatibility notice.

**Exercise 4 — Are the WebFlux and Web MVC starters directly interchangeable?**

**Answer:** no. WebFlux uses Netty/WebFlux/Project Reactor; MVC uses WebMvc.fn and a Servlet runtime.

**Exercise 5 — Does Gateway WebFlux run in a WAR on traditional Tomcat?**

**Answer:** no. Gateway Server WebFlux documentation requires a Netty runtime and does not support traditional Servlet containers/WARs.

**Exercise 6 — Both spring-boot-starter-web and spring-boot-starter-webflux are present. What does Boot choose by default?**

**Answer:** Spring Boot auto-configures Spring MVC by default when both are present. This conflicts with the intent to run Gateway Server WebFlux.

**Exercise 7 — Can spring.main.web-application-type=reactive be set to fix all conflicts?**

**Answer:** no. It can force the application type, but it does not remove Servlet dependencies, does not fix BOM mismatches, and does not guarantee a proper Netty runtime. Fixing the dependency graph is preferred.

**Exercise 8 — What does NoSuchMethodError typically suggest?**

**Answer:** code/runtime binary version mismatch; check the dependency tree and effective POM instead of arbitrarily adding another dependency with the same class.

**Exercise 9 — Does the Gateway starter need an explicit version when the Spring Cloud BOM is imported?**

**Answer:** normally no. Let the BOM manage the versions of the starter and Spring Cloud modules.

**Exercise 10 — Why might the build succeed while the app still fails at runtime?**

**Answer:** the compile classpath can differ from the runtime classpath; there may be lazy linkage, missing Netty runtime, dependency exclusions, a packaged jar differing from the IDE, or an older runtime JDK.

**Exercise 11 — When should Gateway Server Web MVC be used?**

**Answer:** when the architecture intentionally uses a Servlet runtime/Tomcat/Jetty and WebMvc.fn; not as a workaround for a misconfigured WebFlux Gateway.

**Exercise 12 — Should the compatibility verifier be disabled just to get the app to start?**

**Answer:** no. The verifier is warning about a version mismatch; disabling it does not fix binary incompatibility. Choose a compatible release train.

**Exercise 13 — The dependency tree includes spring-webmvc even though the POM does not declare it directly. What should be done?**

**Answer:** use Maven dependency:tree or Gradle dependencyInsight to find the module pulling in Spring MVC, then fix that specific dependency path.

**Exercise 14 — Only actuator and the cloud BOM are present, with no Gateway starter. What happens?**

**Answer:** Boot may start another type of web application, but without the expected Gateway Server auto-configuration/runtime.

**Exercise 15 — Why must the executable jar be tested after IDE context startup passes?**

**Answer:** the packaged jar may omit, add, or change dependencies compared to the IDE classpath; container JDK/profiles can also differ.

**Exercise 16 — Which Cloud train should Spring Boot 3.5.x pair with in the reference table?**

**Answer:** Spring Cloud 2025.0.x (Northfields), with Gateway 4.3.x per the release train.

**Exercise 17 — An old project uses spring-cloud-starter-gateway. Should that exact artifact be copied into Gateway 5.x?**

**Answer:** no. Read the How to Include page for the exact release and select the appropriate Server WebFlux or Server Web MVC starter.

**Exercise 18 — Does passing a context startup test prove that upstream routes work?**

**Answer:** no. An integration smoke test calling the route and verifying the backend stub receives the request is required.

## 19. Official References

- [Spring Cloud Project – Release Train / Spring Boot compatibility](https://spring.io/projects/spring-cloud/): Boot ↔ Cloud matrix and BOM selection guide.
- [Spring Cloud 2026.0.0 release announcement](https://spring.io/blog/2026/11/20/spring-cloud-2026-0-0-has-been-released/): Boot 4.2.0, Gateway 5.1.0, and Maven/Gradle BOM examples.
- [Spring Cloud Release 2026.0.0 reference](https://docs.spring.io/spring-cloud-release/reference/index.html): supported Boot versions and release train module versions.
- [Spring Cloud Gateway Server WebFlux – How to Include](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/starter.html): starter coordinates, WebFlux/Netty runtime, and Servlet/WAR limitations.
- [Spring Cloud Gateway Server Web MVC – How to Include](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webmvc/starter.html): MVC starter, WebMvc.fn, and Servlet runtime.
- [Spring Boot – Reactive Web Applications](https://docs.spring.io/spring-boot/reference/web/reactive.html): behavior when both MVC and WebFlux starters are on the classpath.
- [Maven Dependency Plugin – dependency:tree](https://maven.apache.org/plugins/maven-dependency-plugin/tree-mojo.html): viewing the dependency tree and version mediation.
- [Gradle – Viewing and debugging dependencies](https://docs.gradle.org/current/userguide/viewing_debugging_dependencies.html): dependencies and dependencyInsight.
- [Spring Boot – System Requirements](https://docs.spring.io/spring-boot/system-requirements.html): Java baseline per Spring Boot release.

**Key takeaway:** When Gateway fails to start, identify the **right variant**, choose a **Spring Cloud Release Train compatible with Spring Boot**, use the **right starter**, and let the BOM manage foundational modules. For Gateway Server WebFlux, **WebFlux + Reactor Netty** must be present, without Spring MVC/Servlet runtime accidentally taking over the application type and without WAR deployment. The dependency tree, effective POM, dependencyInsight, and Condition Evaluation Report are your evidence for fixing the root cause; then run both a context startup test and a route smoke test before release.

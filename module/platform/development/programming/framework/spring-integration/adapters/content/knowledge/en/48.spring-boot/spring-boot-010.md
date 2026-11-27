# Checking Dependency Version Compatibility in Spring Boot and Spring Integration Adapters

## 1. Objective: Why Can Correctly Named Dependencies Still Run Wrongly?

In a **Spring Boot** application using **Spring Integration Adapters**, we often combine many components: Spring Framework, Spring Integration Core/Java DSL, File/SFTP/HTTP/JMS/AMQP/Kafka/JDBC adapters, protocol client libraries, Spring Security, messaging systems, databases, and testing tools. Each component has a **version** and **compatibility contract**. If even one library drifts out of alignment with its group, the application can:

- Fail to compile: classes, methods, or overloads changed across a major upgrade.
- Fail to start: `NoClassDefFoundError`, `NoSuchMethodError`, `BeanCreationException`, or auto-configuration errors.
- Start up yet misbehave: mismatched header mappers, changed message converter behavior, producer/consumer schema mismatches, or broker/client incompatibilities.
- Fail only in production: JDK differs from CI, runtime transitive dependencies differ from compile time, or live clients fail TLS/SSH negotiation.
- Carry security vulnerabilities from pinning unmaintained libraries or overriding versions without testing the full graph.
- Lose build reproducibility due to dynamic versions or missing artifact-repository controls.

**Checking dependency version compatibility** is more than glancing at one `<version>` tag in `pom.xml` or `build.gradle.kts`; it means verifying **the entire dependency graph, BOM, tool versions, API/ABI, runtime configuration, protocols, and test scope**.

This lesson belongs to the **Spring Boot** chapter in the **SPRING_INTEGRATION_ADAPTERS** module. Its focus is connecting external systems via inbound/outbound adapters, gateways, pollers, and `MessageChannel`, especially across File, SFTP, HTTP, JMS, AMQP, Kafka, and databases. After this lesson, you will be able to:

1. Identify the mandatory **compatibility axes** when choosing Spring Boot and Spring Integration.
2. Use the **Spring Boot BOM** (Bill of Materials) and, when needed, the **Spring Cloud release train** instead of picking arbitrary versions.
3. Read dependency trees/effective POMs or `dependencyInsight` to spot direct/transitive overrides and conflicts.
4. Design a compile–startup–flow–protocol–security test matrix per adapter.
5. Upgrade dependencies through an evidence-backed workflow with rollbacks and regression checks.

> **Versioning principle:** Examples in this lesson may use an illustrative release such as **Spring Boot 3.5.0** to explain build-file structure; that **is not a claim that it is the latest or universally recommended version at the time you read this**. Check official support matrices, release notes, and supported version lists before picking production versions. This lesson does not invent a "latest" Spring Boot/Spring Integration pair without official verification.

## 2. Compatibility Axes That Must Be Verified Together

An adapter-based system spans multiple constraint layers:

~~~mermaid
flowchart TD
    JDK["JDK / bytecode target"] --> BOOT["Spring Boot release line"]
    BOOT --> FW["Spring Framework"]
    BOOT --> SI["Spring Integration BOM/modules"]
    BOOT --> DEP["Boot-managed dependencies"]
    CLOUD["Spring Cloud release train (if used)"] --> STREAM["Spring Cloud Stream/binders"]
    STREAM --> SI
    SI --> AD["Adapters: File/SFTP/HTTP/JMS/AMQP/Kafka/JDBC"]
    AD --> CLIENT["Protocol clients / serializers / drivers"]
    CLIENT --> INFRA["SFTP server / HTTP API / broker / DB"]
    TEST["JUnit/Mockito/Spring Test/Testcontainers"] --> BOOT
    TEST --> AD
    SEC["Security advisories + vendor support"] --> BOOT
    SEC --> CLIENT
~~~

| Axis | What to verify? | Risk example |
|---|---|---|
| **Java/JDK** | Minimum Java, target bytecode, build/CI/production runtime JDK | Built on newer JDK while server runs older JDK → `UnsupportedClassVersionError` |
| **Spring Boot** | Active release line, support status, matching BOM/plugin | Old parent BOM mixed with newer starters |
| **Spring Framework** | Major/minor supported by that Boot line | Overriding `spring-core` or `spring-messaging` breaks methods |
| **Spring Integration** | Core, DSL, and all adapter modules on one Boot-aligned line | `spring-integration-core` and `spring-integration-sftp` out of sync |
| **Spring Cloud** (optional) | Boot-compatible release train; binders + Stream aligned | Pulling a Kafka binder from another train |
| **HTTP/SFTP/JMS/AMQP/Kafka clients** | APIs, serialization, auth/TLS, broker/server compatibility | Kafka or SSH client missing required classes/transitives |
| **Database driver/ORM** | JDK, DB server, JDBC API, transaction manager | Driver lacks auth protocol or timezone support |
| **Test/runtime** | Test libs aligned with framework; test infra mirrors runtime | Unit tests pass while deployed JDK/broker fails |
| **Security/operations** | CVEs, EOL versions, artifact allowlists, update policies | "Green build" yet dependency flagged critical |

**No single version decides everything.** For example, Java may support your Spring Boot version while the Kafka client remains incompatible with the deployed broker cluster; or the HTTP client works while Spring Integration's outbound gateway API changed across two majors.

## 3. "Compatible" Has at Least Five Levels

Never conclude "compatible" simply because Maven resolved dependencies cleanly.

| Level | Required evidence | What it does NOT prove alone |
|---|---|---|
| **Dependency resolution** | Maven/Gradle resolves versions and artifacts | APIs exist or are vulnerability-free |
| **Compile compatibility** | Main and test sources compile | Startup configuration is valid |
| **Runtime linkage/startup** | `ApplicationContext` starts with zero linkage errors | Adapters work with live servers/brokers |
| **Behavior/protocol compatibility** | Contract tests, send/receive, ACK, serializers, reconnect, transactions | Sufficient performance or zero CVEs |
| **Operational/security compatibility** | Vendor support, JDK/broker matrices, security scans, rollout/rollback | Freedom from every rare prod edge case |

A rigorous version check states **which levels were actually verified**. `mvn dependency:tree` proves resolution; `@SpringBootTest` proves startup/configuration; integration tests with SFTP/Kafka/DB prove protocol boundaries.

## 4. Authoritative Sources for Versions: Prefer BOMs and Official Docs

When selecting versions, consult in order:

1. **Spring Boot Reference / Dependency Versions:** shows managed dependencies, minimum Java, and API/auto-configuration changes.
2. **Spring Integration Reference / Release Notes / Migration Guide:** specifies modules, APIs, endpoint configs, and breaking changes for your Integration version.
3. **Spring Framework Reference:** checks foundational changes in Spring Messaging, JDBC, transactions, Web/HTTP, and JDK baselines.
4. **Spring Cloud Compatibility / Release Train** if using Spring Cloud Stream/binders; never pick trains by guessing similar semver numbers.
5. **Client and target system docs:** Apache MINA SSHD/SFTP server, Kafka client/broker, RabbitMQ/AMQP, JMS provider, JDBC driver/DB, HTTP API/TLS.
6. **Security advisories, support policies, SBOMs, and CI outputs:** catch vulnerable/EOL releases and verify built binaries.
7. **Your project's own dependency graph:** a BOM is only one version-selection mechanism; POM overrides, build plugins, or transitive conflicts can alter final resolution.

Reference URLs (check against your active release line):

- Spring Boot: https://docs.spring.io/spring-boot/reference/
- Spring Boot managed versions: https://docs.spring.io/spring-boot/appendix/dependency-versions/coordinates.html
- Spring Integration: https://docs.spring.io/spring-integration/reference/
- Spring Integration changes: https://github.com/spring-projects/spring-integration/releases
- Spring Cloud: https://spring.io/projects/spring-cloud
- Maven dependency plugin: https://maven.apache.org/plugins/maven-dependency-plugin/
- Gradle dependency resolution: https://docs.gradle.org/current/userguide/viewing_debugging_dependencies.html

**Do not assume** "Spring Integration major $N$ always pairs with Spring Boot major $M$" across every minor/patch and Spring Cloud train. Let the BOM resolve versions, cross-check compatibility/migration guides, and verify with tests.

### 4.1. Why Not Pick Versions by Looking at JAR Filenames?

A JAR filename shows the version of **one** artifact; it hides transitive overrides or a different JAR picked by the classloader at runtime. Select versions by policy first, then inspect the full graph instead of dropping manual JARs into `lib/`.

### 4.2. Should You Always Use Latest?

**Not automatically.** Latest releases bring security fixes and features alongside API, JDK-baseline, or behavioral changes. Pick a **supported release** aligned with your BOM and system policy, apply security patches with testing, and plan major upgrades deliberately.

## 5. How Does the Spring Boot BOM Manage Dependencies?

A **BOM** (Bill of Materials) publishes a curated set of mutually tested versions. In Spring Boot, the central BOM is `spring-boot-dependencies`:

- With **Maven `spring-boot-starter-parent`**, your project inherits dependency management and plugin defaults from the parent.
- Without the parent, **import the Boot BOM** inside `<dependencyManagement>`.
- With **Gradle**, the Spring Boot plugin pairs with `io.spring.dependency-management` or Gradle native `platform(...)` to feed the BOM into resolution.
- A dependency **omitting `<version>`** receives the managed version if covered by active dependency management.
- A dependency with an **explicit version**, rule/constraint, or competing BOM can resolve differently; always inspect the resolved graph.
- A BOM does not add dependencies by itself. It **manages versions of declared dependencies**, never replacing `<dependencies>`.

~~~mermaid
flowchart TD
    POM["pom.xml / build.gradle.kts"] --> BOM["Boot BOM"]
    BOM --> CORE["spring-integration-core"]
    BOM --> FILE["spring-integration-file"]
    BOM --> SFTP["spring-integration-sftp"]
    BOM --> HTTP["spring-integration-http"]
    BOM --> KAFKA["spring-integration-kafka"]
    BOM --> JMS["spring-integration-jms"]
    BOM --> AMQP["spring-integration-amqp"]
    BOM --> JDBC["spring-integration-jdbc"]
    OVERRIDE["Explicit version / other BOM / constraint"] -. "can alter resolved version" .-> CORE
    OVERRIDE -. "can alter" .-> KAFKA
~~~

**BOMs differ from dependency lockfiles.** A BOM defines version-selection rules in the graph; a lockfile (if used) pins resolved versions per build tool. Even with a BOM, adding dependencies or changing plugin/BOM versions alters the graph.

## 6. Maven: Version Management Pattern via Spring Boot Parent

The example below uses **Spring Boot 3.5.0** solely as a **structural illustration** (not claiming it is the latest release). Replace the version with the one chosen by your project team from official sources, while verifying your JDK and required modules.

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="
           http://maven.apache.org/POM/4.0.0
           https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

    <groupId>example.learning</groupId>
    <artifactId>integration-adapters-demo</artifactId>
    <version>1.0.0-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-integration</artifactId>
        </dependency>

        <dependency>
            <groupId>org.springframework.integration</groupId>
            <artifactId>spring-integration-file</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.integration</groupId>
            <artifactId>spring-integration-sftp</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.integration</groupId>
            <artifactId>spring-integration-http</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.integration</groupId>
            <artifactId>spring-integration-jdbc</artifactId>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.integration</groupId>
            <artifactId>spring-integration-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
~~~

**Key checks:**

1. Omit individual versions on `spring-integration-*` modules when a matching BOM manages them.
2. Do not add every adapter blindly: **include only the modules your app uses**. Add Kafka/AMQP/JMS modules only when required by architecture.
3. `java.version` must match your Boot line, toolchain, and runtime JDK; "runs on my laptop" is not proof it runs on the server.
4. `spring-integration-test` must align with your Spring Integration line; never copy test JAR versions from unrelated blogs.
5. This sample omits datasources, credentials, broker configs, custom build plugins, and tests; it is an **educational skeleton**, not production-ready out of the box.

### 6.1. Without `spring-boot-starter-parent`

A project with a corporate parent POM can import the BOM directly:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-dependencies</artifactId>
            <version>3.5.0</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

**This is only the BOM snippet** to place inside a valid POM. Importing the BOM differs from inheriting the Boot parent for plugin/build defaults; configure Maven compiler/test plugins in your corporate parent if absent.

### 6.2. When Should You Set an Explicit Dependency Version?

Only for a documented reason such as an approved security patch, a verified compatibility matrix, or a library **outside the BOM**. Whenever overriding:

- Record the ticket/rationale, before/after versions, and expiration/review date.
- Verify API/binary compatibility across **the entire related dependency group**.
- Run dependency-graph, compile, startup, and adapter integration tests.
- Never slap on an override right before a release without verifying the transitive graph.
- Track newer BOM releases containing the fix so you can return to managed versions.

## 7. Gradle Kotlin DSL: Never Hard-Code Individual Adapter Versions

Equivalent example using the same illustrative Boot 3.5.0 baseline:

~~~kotlin
plugins {
    java
    id("org.springframework.boot") version "3.5.0"
    id("io.spring.dependency-management") version "1.1.7"
}

group = "example.learning"
version = "1.0.0-SNAPSHOT"

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation("org.springframework.boot:spring-boot-starter-integration")
    implementation("org.springframework.integration:spring-integration-file")
    implementation("org.springframework.integration:spring-integration-sftp")
    implementation("org.springframework.integration:spring-integration-http")
    implementation("org.springframework.integration:spring-integration-jdbc")

    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("org.springframework.integration:spring-integration-test")
}

tasks.withType<Test> {
    useJUnitPlatform()
}
~~~

When pairing the Spring Boot Gradle plugin with `io.spring.dependency-management`, Boot's BOM governs resolution. **Avoid mixing competing BOMs or duplicate overrides without understanding resolution rules and precedence.**

Projects using Gradle's native BOM support can use `platform(...)`/`enforcedPlatform(...)` and constraints. Note that **`enforcedPlatform` forces versions across downstream modules**; never abuse it to "silence" conflicts. Choose **one clear version-management strategy** and inspect `runtimeClasspath`.

### 7.1. Gradle Version Catalogs Are Not a Compatibility Guarantee

`libs.versions.toml` centralizes coordinates and versions, yet pinning arbitrary version numbers in a catalog **does not guarantee** Spring Boot, Spring Integration, Kafka clients, and Spring Cloud are compatible. BOMs/constraints and testing remain mandatory.

### 7.2. Are Plugin Versions and Library Versions the Same?

No. Gradle/Maven **plugin** versions govern build/lifecycle tooling; Java **library** versions run at compile/runtime. Verify Gradle wrapper compatibility with the Spring Boot Gradle plugin, plugin JDK requirements, and project toolchains for application bytecode. Never assume "plugin build succeeded" implies runtime compatibility.

## 8. Commands to Inspect Real Resolved Versions (Not Just Build Files)

**These are reference commands for learners to run in permitted repos.** This authoring step **does not execute** Gradle/Maven or project tests.

### 8.1. Maven

~~~powershell
# Print the resolved dependency graph.
mvn dependency:tree

# Filter to Spring Integration only.
mvn dependency:tree -Dincludes=org.springframework.integration

# Filter to Spring Framework, Integration, and Kafka.
mvn dependency:tree -Dincludes=org.springframework:spring-core,org.springframework.integration:spring-integration-core,org.springframework.kafka:spring-kafka

# Export the effective POM (can be large).
mvn help:effective-pom -Doutput=effective-pom.xml

# Print active Java and Maven versions.
mvn --version
~~~

`help:effective-pom` writes `effective-pom.xml` in the working directory, so run it **only where creating diagnostic files is permitted** and clean up afterward. Some goals/plugins download artifacts and require network access. In this text, commands are illustrative only and **are not executed during authoring**.

In the output, inspect the **final resolved version**, nearest-wins / management precedence, and all transitive paths pulling the same artifact. Never grep only `spring-integration-sftp` while ignoring `spring-integration-core` or Spring Framework.

### 8.2. Gradle (PowerShell/Windows)

~~~powershell
# Dependency tree for the runtime classpath.
.\gradlew.bat dependencies --configuration runtimeClasspath

# Why did spring-integration-core resolve to this version?
.\gradlew.bat dependencyInsight --dependency spring-integration-core --configuration runtimeClasspath

# Check Kafka, HTTP, or SSH/SFTP clients similarly.
.\gradlew.bat dependencyInsight --dependency kafka-clients --configuration runtimeClasspath
.\gradlew.bat dependencyInsight --dependency sshd-sftp --configuration runtimeClasspath

# Dependencies present only during tests.
.\gradlew.bat dependencies --configuration testRuntimeClasspath

# Active Gradle/JDK versions.
.\gradlew.bat --version
~~~

`dependencyInsight` explains **why a version won**, including conflict resolution and constraints. Never assume a fixed SFTP artifact name exists in every version; if a project uses another client, query the actual artifact name from the dependency tree.

### 8.3. Comparing Classpaths

| Classpath | How it can differ | Risk |
|---|---|---|
| `compileClasspath` | APIs visible during compilation | Compiles cleanly yet misses classes at runtime |
| `runtimeClasspath` | Actual implementations/clients at runtime | `NoSuchMethodError`, duplicate libraries |
| `testRuntimeClasspath` | Test/JUnit/Mockito/stub servers | Tests pass while test-only JARs mask prod defects |
| Fat JAR / container runtime | Packaged artifact and actual Java runtime | Differs from build classpath or cached layers |
| Server-managed classpath | App server/provider supplies libraries | `javax`/`jakarta` or framework version collisions |

**Compatibility conclusions must reflect the classpath the app actually runs on.** If compile/tests pass yet deployment fails, inspect the packaged artifact, container image, and runtime JDK — not just the POM.

## 9. Debugging Version Conflicts via the Dependency Tree

Suppose an illustrative graph shows:

~~~text
application
  +-- spring-boot-starter-integration
  |    +-- spring-integration-core: VERSION_MANAGED_BY_BOOT
  |
  +-- spring-integration-sftp: VERSION_MANAGED_BY_BOOT
  |    +-- spring-integration-core: same managed line
  |    +-- ssh client library: version managed/resolved
  |
  +-- custom-vendor-sdk: vendor-version
       +-- spring-messaging: different older version (conflict)
~~~

`VERSION_MANAGED_BY_BOOT` and `vendor-version` are **illustrative placeholders**, not literal build output. How to resolve:

1. Check which `spring-messaging` version **actually resolved**, not just what the vendor declared.
2. Check whether the Spring Boot BOM manages that artifact and whether any direct override exists.
3. Verify whether the vendor SDK **officially supports** your project's Spring Framework/Boot version.
4. Use exclusions **only when you know the excluded library is unneeded at runtime** and contracts hold; never strip transitives by guessing.
5. Run compile, startup, and protocol tests to prove the fix; **never trust a tidy dependency tree alone**.
6. If the vendor SDK truly demands an incompatible version, upgrade the SDK, swap clients, isolate behind a service boundary, or plan a migration rather than forcing the BOM to mask the mismatch.

### 9.1. What Makes an Override Dangerous?

~~~xml
<!-- Anti-pattern: arbitrarily pinning core below Boot's release line. -->
<dependency>
    <groupId>org.springframework.integration</groupId>
    <artifactId>spring-integration-core</artifactId>
    <version>AN_UNAPPROVED_VERSION</version>
</dependency>
~~~

Adapter modules depend on core APIs of a matching line; changing core independently triggers linkage errors or subtle behavioral drift during message dispatch. **Never guess version numbers until startup happens to stop crashing.**

### 9.2. Maven and Gradle Use Different Version-Resolution Algorithms

- Maven uses dependency management and nearest-wins mediation by graph depth/order, with explicit rules for direct declarations and conflict ordering.
- Gradle uses conflict resolution, constraints, platforms, and project rules, defaulting to highest-version selection in many conflicts.
- `dependencyManagement` and Gradle `platform` both stabilize versions yet **do not behave identically in every edge case**.

Never rely on oversimplified rules like "highest always wins" or "BOM always overrides everything". **Inspect resolved output** before drawing conclusions.

## 10. Keeping Spring Integration Core and Adapters on the Same Release Line

Spring Integration spans multiple modules. One flow may combine:

| Module | Typical scope |
|---|---|
| `spring-integration-core` | Message channels, endpoints, transformers, routers, filters, aggregators, Java DSL |
| `spring-integration-file` | File inbound/outbound, file filters, file reading/writing |
| `spring-integration-sftp` | SFTP inbound sync, outbound upload, session factories |
| `spring-integration-http` | HTTP inbound/outbound gateways and channel adapters |
| `spring-integration-jms` | JMS inbound/outbound adapters and gateways |
| `spring-integration-amqp` | AMQP/RabbitMQ inbound/outbound integration |
| `spring-integration-kafka` | Kafka adapters and message-driven flows |
| `spring-integration-jdbc` | JDBC inbound polling/outbound, metadata stores |
| `spring-integration-test` | Flow testing helpers, mock endpoints, test utilities |

**Include only the modules you genuinely need**, and let the BOM align their versions whenever managed. Never bump `spring-integration-sftp` alone to a new major just for one API while leaving core/file/http on an older major.

### 10.1. Avoid Outdated Java DSL Artifacts from Old Articles

In modern Spring Integration lines, Java DSL is built directly into the core ecosystem. Old guides may reference a separate DSL artifact from an earlier era. Before adding unfamiliar dependencies, inspect `IntegrationFlow`, builders, and documentation for your exact Spring Integration version. **Never put two generations of DSL/APIs on the same classpath** just to make an old blog snippet compile.

### 10.2. Dependency Management and API Migration Are Separate Steps

A BOM picks JARs compatible with your Boot line. It **does not rewrite your Java code** when interfaces, factory methods, annotations, or overloads change across major versions. Upgrading requires reading migration notes and updating code — especially gateways, pollers, message converters, error handlers, or relocated namespaces.

### 10.3. Running a "Small Flow" Smoke Test After Upgrading Integration

A minimal flow smoke test covers:

~~~mermaid
flowchart LR
    INPUT["MessageChannel"] --> TRANS["Transformer"]
    TRANS --> OUTPUT["QueueChannel"]
    OUTPUT --> ASSERT["JUnit payload/header assertion"]
~~~

Building an `IntegrationFlow`, sending a message with a `correlationId`, and asserting the output catches many wiring and runtime linkage bugs. Still, it **does not replace** real File/SFTP/HTTP/Kafka adapter tests.

## 11. Java, Spring Framework, and the `javax` → `jakarta` Shift

JDK compatibility spans at least three scopes:

1. **Build JDK:** the compiler and Gradle/Maven plugin runtime.
2. **Java toolchain/target:** bytecode target and source API level compiled for the app.
3. **Runtime JDK:** the machine/container running the Spring Boot JAR.

Compiling with a newer JDK to bytecode unsupported by the runtime throws `UnsupportedClassVersionError`. Setting `java.version` or a Gradle toolchain does not replace verifying **the actual container image and production JDK**.

Spring Boot 3 moved APIs such as Servlet/JMS/JPA to **Jakarta EE** (`jakarta.*`) namespaces, whereas legacy systems used `javax.*`. When upgrading from Boot 2 or legacy clients, check:

| Component | What to inspect |
|---|---|
| JMS provider | Do client and API support `jakarta.jms.*` for your Boot/Spring line? |
| Servlet/HTTP | Do filters/servlets use `jakarta.servlet.*` instead of legacy APIs where needed? |
| JPA/validation | Do libraries target the matching namespace/major? |
| Test infrastructure | Are mock servlet/context and embedded servers aligned with Spring Framework? |
| Vendor SDK | Does it bundle old `javax.*` dependencies or framework JARs? |

**Never search-and-replace `javax` with `jakarta` and assume compatibility.** JMS providers, servlet containers, validation providers, and dependent libraries must ship compatible implementations, verified at runtime against the real provider.

### 11.1. Distinguish JDK Support from TLS/Protocol Support

Even a Boot-supported JDK can alter default TLS/SSH algorithms, truststores, security providers, or cipher suites. SFTP and HTTP integrations require handshake tests against realistic test servers, especially after JDK security upgrades. Never "fix" handshake failures by disabling certificate or host-key verification.

## 12. File Adapter: Simple Protocol, Still Version-Coupled

File inbound/outbound relies mainly on Java filesystem APIs and the Spring Integration File module. Notable version changes can affect:

- Filter APIs: pattern filters, accept-once filters, persistent metadata stores.
- File locking/renames/temp files, encoding, line endings, and modification timestamps.
- Default pollers, schedulers, and endpoint lifecycles.
- Header/metadata mapping and payload types (`File`, `String`, `byte[]` post-transform).
- `FileReadingMessageSource`/`FileWritingMessageHandler` or corresponding Java DSL factories.

**Never assume a pattern filter prevents duplicates by itself.** Version upgrades can alter default metadata/restart behavior; verify by testing repeated reads of the same file and endpoint restarts.

Post-upgrade File test checklist:

~~~text
[ ] *.csv files enter the flow with the expected payload
[ ] Non-matching files are skipped by the pattern filter
[ ] Incomplete files are not processed prematurely
[ ] Filename/path headers match contract
[ ] Outbound files have expected names, contents, and permissions
[ ] Duplicates/restarts are handled per metadata store policy
[ ] Poller stop/start triggers no unintended side effects
~~~

## 13. SFTP Adapter: Spring Integration and SSH Client Must Match Generations

SFTP spans multiple layers: Integration adapters, session factories, SSH client libraries, ciphers, and remote servers. Modern Spring Integration lines use **Apache MINA SSHD**; older guides reference JSch and different session types.

**Risks when copying old code:**

- Importing session factory or SSH client classes whose packages/APIs changed.
- Pulling two SSH client stacks simultaneously via stale transitives.
- Host-key/cipher mismatches rejected by the JDK or SSH server.
- Metadata store/filter changes causing files to re-ingest after restarts.
- Local temp suffixes, remote paths, and partial-upload handling drifting from design.
- Tests mocking sessions and missing real TLS/SSH negotiation failures.

Verification steps:

1. Check which `spring-integration-sftp` version your BOM resolved.
2. Inspect the dependency graph of the actual SSH/SFTP library in use (never guess artifact names from old posts).
3. Verify `SessionFactory` and `Session<?>` APIs for your selected version.
4. Test against an SFTP server with trusted host keys and test credentials.
5. Test inbound sync, outbound upload, renames, retries, remote readback, and restarts.
6. Never disable host-key checking just to "turn tests green".

### 13.1. Do Not Compare SSH Client Version Numbers Alone

A "newer" SSH client may fail algorithm negotiation with an older SFTP server; conversely, re-enabling insecure algorithms solely for compatibility can violate security policy. Align against server policies, vendor docs, and organizational security standards.

## 14. HTTP Adapter/Gateway: Spring Web and Related Client APIs

HTTP inbound/outbound depends on Spring Web / HTTP clients, converters, Jackson serialization, and Servlet or Reactive stacks. Depending on Spring Integration version, Java DSL and HTTP clients may use `RestTemplate`, `RestClient`, or WebFlux components; never mix snippets from two different release lines.

| Question | Why does it matter? |
|---|---|
| Does the inbound gateway run on Spring MVC or Reactive? | Web servers, handler adapters, and converters differ |
| Which client instance does the outbound handler actually use? | `MockRestServiceServer`, mock servers, and DI must match |
| Which BOM governs content-type/JSON converters? | Serialization behavior can shift across major upgrades |
| Does the header mapper forward every specified header? | Correlation, auth, tenant, and content-type headers can drift |
| How are 4xx/5xx/timeouts mapped? | Retry rules and response status codes may change |
| Are TLS/truststores and proxies compatible? | In-memory tests miss network handshakes |

A version change can compile cleanly yet **flip status codes, error bodies, or converter behavior in HTTP integration tests**. Run a mock HTTP server testing real requests/responses, URIs, methods, headers, JSON, and negative cases.

### 14.1. Never Upgrade Jackson Individually While Ignoring the BOM

Spring Boot manages serialization libraries as a coordinated set. A vendor SDK pulling another Jackson major causes API clashes or shifts how `Instant`, records, or enums serialize. Never override `jackson-databind` alone to patch a bug without aligning sibling Jackson modules. When a new major is required, evaluate the whole serialization stack and upgrade Boot/SDKs via supported paths.

### 14.2. HTTP Version Compatibility Is Not API Contract Compatibility

Even when the HTTP client connects and receives `200`/`201`, a partner API may change schemas, auth, or idempotency rules. Maintain dedicated **consumer/provider contract tests**; Maven/Gradle cannot detect remote service API changes.

## 15. JMS Adapter: Providers, `jakarta.jms`, and Transaction Semantics

JMS inbound/outbound depends on more than `spring-integration-jms`. It requires a compatible JMS provider client and broker/`ConnectionFactory`.

Dependency snippet **intentionally separating interface and provider**:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.integration</groupId>
        <artifactId>spring-integration-jms</artifactId>
    </dependency>

    <!-- Choose the exact JMS provider or compatible starter
         for your broker; never drop both javax and jakarta
         clients onto the classpath by guesswork. -->
</dependencies>
~~~

**Key checks:**

- Provider supports the JMS/Jakarta API matching your Spring Boot line.
- `ConnectionFactory` initializes cleanly with proper credentials and TLS.
- Message converters and JMS properties map accurately.
- Transaction managers/ACK modes and redelivery follow policy.
- Client/broker compatibility is vendor-verified.

**Classic failure:** an old vendor SDK brings `javax.jms.ConnectionFactory` while modern Spring Integration expects `jakarta.jms.ConnectionFactory`. This cannot be fixed by "adding both APIs": pick a **compatible provider version**.

## 16. AMQP/RabbitMQ: Spring AMQP, Clients, and Brokers

Applications using RabbitMQ typically involve:

- `spring-integration-amqp` for adapters/gateways.
- Spring AMQP, `RabbitTemplate`, listener infrastructure, and RabbitMQ Java client.
- A broker with exchanges, queues, bindings, TLS, and quorum/classic/retry policies.

Illustrative Boot-managed dependencies:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-amqp</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.integration</groupId>
    <artifactId>spring-integration-amqp</artifactId>
</dependency>
~~~

Post-upgrade verification checklist:

| Area | Assertion |
|---|---|
| Listener container | Consumer start/stop, concurrency, and acknowledgments |
| Publisher | Exchanges, routing keys, confirms/returns |
| Converters | JSON/bytes/message headers intact |
| Retry/recovery | Requeue, dead-letter policies, idempotency |
| Network | SSL/auth/reconnect, connection/channel pools |
| Broker server | Client supports active protocol features |

**`Mockito.verify(rabbitTemplate)` does not prove the broker received or routed the message.** Test against a RabbitMQ test container/broker verifying exchanges/bindings, publisher confirms, and consumer side effects.

## 17. Kafka: Check Both Spring Kafka and Kafka Client/Broker

A Spring Integration Kafka flow pulls in:

- `spring-integration-kafka`.
- `spring-kafka` and Kafka Java clients.
- Serializers/deserializers and optional schema tooling.
- Consumer groups, topics/partitions, and transactional/idempotent producers.
- External Kafka brokers running independently of the JVM.

Boot-BOM-managed dependencies example:

~~~xml
<dependency>
    <groupId>org.springframework.integration</groupId>
    <artifactId>spring-integration-kafka</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.kafka</groupId>
    <artifactId>spring-kafka</artifactId>
</dependency>
~~~

If `spring-integration-kafka` already pulls `spring-kafka` transitively, redeclaring it is optional unless your app directly uses Spring Kafka APIs or dependency policy requires explicit direct declarations; **inspect the dependency tree first**.

### 17.1. Kafka Client/Broker Versions Have Their Own Compatibility Rules

Do not assume the Kafka client version must **match the broker version identically**. Published client/broker compatibility ranges exist, yet feature support, message formats, TLS/SASL, API versions, and transaction semantics can differ. **Check Apache Kafka and vendor distribution docs** for real deployments.

### 17.2. Spring Cloud Stream Binders Are Not Always Required

Using Spring Integration Kafka adapters directly **does not require** Spring Cloud Stream. If you do use Stream functions/binders, select a **Spring Cloud release train** compatible with your Spring Boot line and verify dependencies across both ecosystems.

### 17.3. Post-Upgrade Kafka Smoke Test

~~~text
[ ] Producer publishes cleanly to test topic
[ ] Record keys, partitions, headers, and payloads match
[ ] Test consumer group receives and deserializes cleanly
[ ] Offsets/ACKs/commits follow contract
[ ] Retries, DLT, and idempotency work properly
[ ] Broker outage/reconnect behaves as expected
[ ] Zero duplicate side effects when consumer crashes post-processing
~~~

## 18. JDBC/JPA/Database: Drivers and Transaction Managers

JDBC adapters require Spring JDBC, `DataSource`, a DB driver, and a database; JPA also requires a compatible ORM/EntityManager provider.

Minimal purpose-driven dependencies:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-jdbc</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.integration</groupId>
    <artifactId>spring-integration-jdbc</artifactId>
</dependency>

<!-- Add the runtime driver matching your DB;
     let the BOM manage its version if included in the BOM. -->
~~~

Verify:

- The driver supports your DB server, auth, timezones, data types, and runtime JDK.
- Poller and outbound SQL/schemas remain valid.
- `DataSourceTransactionManager`/`JdbcTransactionManager`/JPA transactions align with architecture.
- Connection pools and health checks work after upgrades.
- Locking/isolation and row counts behave per contract.
- Multiple poller instances do not create unintended duplicate side effects.

**Mocking `JdbcTemplate.update(...)` to return `1` does not prove a real transaction committed.** Run realistic DB tests (such as a container running your production DB engine) whenever verifying locks, transactions, SQL dialects, and constraints.

### 18.1. In-Memory Databases Are Not Always Equivalent to Production

H2 helps for fast unit checks, yet its SQL dialect, locking/isolation, timestamps, JSON types, sequences, and constraints differ from PostgreSQL/MySQL/Oracle. For polling adapters and sensitive transactions, **production-like database tests** carry far more weight than an H2 pass.

## 19. Spring Cloud Stream and the Spring Cloud BOM: Add Only When Needed

**Spring Cloud Stream** builds messaging around function bindings and binders, introducing dependencies across Spring Cloud, Spring Boot, Spring Integration, and Kafka/RabbitMQ transports. However, the Spring Integration Adapters module can use **Spring Integration directly** without Spring Cloud Stream.

When a project **genuinely uses Cloud Stream**, align:

1. An approved Spring Boot release line.
2. A Spring Cloud release train **published as compatible with that Boot line**.
3. Stream/binders from that exact train and version level.
4. Matching Java/JDK, brokers/clients, and schema tooling.
5. Current-generation binder tests: use `InputDestination`/`OutputDestination` rather than importing legacy `MessageCollector` test utilities from outdated guides without checking versions.

Pattern for importing the **Cloud BOM** into a Maven project using the Boot parent:

~~~xml
<properties>
    <!-- Replace with a release train verified compatible with Boot. -->
    <spring-cloud.version>APPROVED_CLOUD_TRAIN</spring-cloud.version>
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
~~~

This is a **skeleton** and will not build while `APPROVED_CLOUD_TRAIN` remains a placeholder. Replace it with an officially verified compatible release train and import the Cloud BOM alongside the Boot BOM per official release-train guidance.

**Never disable Spring Cloud's compatibility verifier just to make startup pass.** If the verifier flags a Boot/Cloud mismatch, consult the compatibility matrix; silencing the check never makes binaries or semantics compatible.

### 19.1. Do Not Mix `spring-integration-kafka` and Stream Kafka Binders Blindly

If an app uses both direct Spring Integration Kafka APIs and Cloud Stream binders, clarify:

- Which layer owns `spring-kafka`/Kafka clients.
- Which topic/key/header mappers apply.
- Whether binder retry/error semantics match direct flows.
- That test binders test in-memory bindings only, not live brokers.
- Whether dependency management or auto-configuration conflicts arise.

Unless both are genuinely required, **reducing framework layers** simplifies version checks and operations.

## 20. Test Dependencies Must Also Match the Version Line

A build can **compile the app cleanly yet fail tests at runtime** if test libraries drift:

| Component | Purpose | Failure when misaligned |
|---|---|---|
| `spring-boot-starter-test` | Auto-config tests, Spring Test, JUnit/Mockito per Boot line | Runner, extension, and context-setup failures |
| `spring-integration-test` | `@SpringIntegrationTest`, `MockIntegrationContext`, mock endpoints/triggers | Missing test classes, utilities, or methods |
| JUnit Platform/Jupiter | Test execution | Tests not discovered; launcher API mismatches |
| Mockito/Byte Buddy | Mocking clients and handlers | Mock engine/agent crashes on newer JDKs |
| Testcontainers | SFTP/broker/DB test infrastructure | Docker runtime/client incompatibilities |
| Spring Cloud Stream test binder | Simulated binder tests | Test binder from wrong Stream/Cloud generation |
| `spring-kafka-test` | Embedded Kafka broker/consumer tests | API mismatch with Spring Kafka runtime |
| Reactor Test, Spring Web test | Reactive/HTTP tests | Assertion utilities or runtime class mismatches |

**Rule:** let the Boot/Cloud BOM manage test dependencies wherever possible and match test modules to the runtime line. Never pin arbitrary `mockito-core`/`junit-jupiter` patches solely from IDE prompts. When overriding for a bug/CVE, run the suite **on the production JDK** and check release notes for compatibility.

### 20.1. Distinguish Two Failure Categories

- **Test framework mismatch:** `NoSuchMethodError` inside JUnit/Mockito/Spring Test before business logic runs.
- **Application compatibility regression:** tests run yet fail assertions because newer Spring Integration changed serialization, routing, pollers, or headers.

Read the stack trace to pinpoint which layer threw the error instead of blindly shuffling Spring versions when a test plugin lacks a dependency.

## 21. Dependency Scanning and SBOM: Valid Versions Are Not Automatically Secure

A BOM guarantees compatible versions at release time, yet new CVEs emerge later. Pair compatibility checks with **security posture**:

- Maintain an **SBOM** (e.g., CycloneDX/SPDX per tooling/compliance) for release artifacts.
- Run dependency vulnerability scanners aligned with official advisory feeds.
- Track support/EOL status for Boot, JDKs, integration modules, broker clients, and DB drivers.
- Distinguish **a vulnerable dependency present on the classpath** from runtime exploitability; never ignore critical CVEs just because tests pass.
- Document rationale and verify binary/protocol compatibility for emergency overrides outside the BOM.
- Track upcoming BOM releases to retire temporary overrides.

**Never "fix" every security alert by forcing a transitive dependency onto its latest major** without verifying API compatibility. Safer mitigations include compatible patch releases, line upgrades, library replacements, or tracked compensating controls.

### 21.1. Lockfiles, Reproducible Builds, and Dependency Provenance

BOMs, version catalogs, dependency locking, artifact mirrors, and checksum verification serve complementary roles:

| Mechanism | What it solves |
|---|---|
| BOM | Coordinates compatible library versions |
| Version catalogs/properties | Centralizes coordinates/versions for review |
| Dependency locking | Records resolved versions to prevent silent drift |
| Artifact checksums/provenance | Verifies downloaded artifacts match trusted sources |
| SBOM | Inventories exact packages/versions inside a build |
| Scanners/advisories | Flags versions with disclosed vulnerabilities |
| Build/test pipelines | Verifies actual binaries and runtime behavior |

An app with a BOM and no lockfile can still build reproducibly when versions are pinned and repositories are stable; lockfiles add control, **not replace BOMs**.

## 22. Compatibility Failure Symptoms and Triage

| Symptom | Investigation area | First check |
|---|---|---|
| `UnsupportedClassVersionError` | Runtime Java older than compiled bytecode | `java -version`, `mvn --version` or `gradlew --version`, base image |
| `NoSuchMethodError` / `AbstractMethodError` | ABI mismatch; changed method signature | Resolved runtime classpath, actual loaded JARs |
| `NoClassDefFoundError` / `ClassNotFoundException` | Missing dependency or relocated package | Dependency tree, module scope, namespace |
| `BeanCreationException` | Bean or auto-config failed initialization | First `Caused by`, config properties, provider beans |
| `NoSuchBeanDefinitionException` | Missing bean/auto-config module or unmet condition | Starters, auto-config report, package scan |
| `ClassCastException` | Serializer/converter API or payload mismatch | Message types per channel, converter version |
| HTTP `415`/`406` or broken JSON | Content-type / serialization contract | Header mapper + converter + mock server |
| SFTP session/auth failure | Client/SSH server/cipher/host-key mismatch | Remote host key, algorithm negotiation, client libs |
| JMS `javax`/`jakarta` mismatch | Provider and Boot line from different eras | JMS API package and provider client version |
| AMQP routing/ACK mismatch | Spring AMQP/client/broker config drift | Exchanges/bindings, confirms, listener containers |
| Kafka serialization/offset error | Client/broker/schema/consumer mismatch | Topic/key/headers, serializers, broker tests |
| DB driver auth/SQL error | Driver–server–JDK or SQL dialect mismatch | JDBC driver/version, connection config, DB tests |
| Tests pass in IDE, fail in CI | Differing JDK/cache/toolchain/test env | Wrapper, lockfile, CI runtime, test resources |
| Startup passes yet zero messages flow | Endpoint lifecycle/poller/filter or error channel | `isRunning`, channel wiring, inbound source, logs |

**Investigation rule:** trace the root cause down the exception chain, inspect the actual deployed artifact/classpath, and write a minimal reproducer test. Never randomize version numbers before identifying the colliding relationship.

## 23. Case Study: Boot, Integration, and SFTP Out of Sync in One Project

A team runs a Spring Boot app with File/SFTP and HTTP outbound adapters. After adding a partner library, the build stays green while runtime fails initializing the SFTP outbound handler.

**Initial hypothesis (illustrative):**

~~~text
Application:
  Spring Boot managed dependency line: A

Direct dependencies:
  spring-boot-starter-integration: managed by A
  spring-integration-sftp: explicit version B (different from line A)
  partner-sdk: version C

Resolved graph:
  spring-integration-core: A
  spring-integration-sftp: B
  SSH client implementation: shifted by B/C transitives

Runtime:
  startup/linkage failure or SFTP session failure
~~~

Controlled resolution workflow:

1. **Collect evidence:** Boot version, Java version, present JARs/modules, and the initial stack trace.
2. **Read the dependency tree:** check resolved versions of `spring-integration-core`, `sftp`, and SSH client; never trust the POM alone.
3. **Align with the BOM:** drop the explicit SFTP version if unjustified so Boot manages one consistent set.
4. **Inspect the vendor SDK:** if it drags in an old library or conflicting API, obtain a compatible SDK release; never exclude transitives without knowing who needs them at runtime.
5. **Compile and start:** run unit + context smoke tests verifying `SessionFactory` beans and flow endpoints.
6. **SFTP contract tests:** test uploads/downloads against a test SFTP server verifying host keys, bytes, remote paths, and rename/restart.
7. **HTTP regression tests:** confirm the outbound gateway still maps bodies/headers/timeouts after BOM alignment.
8. **Security scan:** verify settled versions against CVEs and support policies.
9. **Canary deploy/rollback:** roll out carefully while keeping the prior dependency manifest ready to roll back.

**Never conclude** "SFTP B is definitely the bug" before reading the stack trace; host-key, credential, or remote server issues can look similar. This case illustrates **the diagnostic method**, not an observed real-world incident.

## 24. Case Study: Adding Spring Cloud Stream Breaks the Kafka Adapter

Suppose an app already uses `spring-integration-kafka` directly, and someone adds the Cloud Stream Kafka binder without checking the Cloud release train.

Possible symptoms:

- Cloud compatibility verifier warns about Boot/Cloud mismatch.
- Two sets of Kafka producer/consumer configs run simultaneously with conflicting settings.
- Binder tests pass while live broker tests fail on topics/keys/headers/schemas.
- Dependency graph shows multiple constraints/overrides on `spring-kafka` or `kafka-clients`.
- Runtime API errors occur despite clean Maven resolution.

Remediation:

1. Decide whether Cloud Stream is genuinely needed or direct Kafka adapters suffice.
2. If needed, pick the Cloud train matching your Boot line and import its BOM properly.
3. Remove unapproved overrides and verify dependency resolution.
4. Separate in-memory `OutputDestination` tests from real Kafka integration tests.
5. Verify topics/keys/serializers/offsets/ACKs/rebalances/retries and event idempotency.
6. Never disable the compatibility verifier just to silence startup errors.

**Never chase a "warning-free" dependency graph by blindly excluding transitives required by active handlers.** Architectural changes require understanding bean wiring and contracts.

## 25. Compatibility Test Suite for an Adapters Application

Structure verification into quality gates:

~~~mermaid
flowchart TD
    INPUT["BOM + JDK + adapter choices"] --> RES["1. Dependency resolution"]
    RES --> COMP["2. Compile/package"]
    COMP --> START["3. Spring context startup"]
    START --> MSG["4. MessageChannel/flow contract"]
    MSG --> AD["5. Adapter protocol smoke"]
    AD --> FAIL["6. Failure/retry/lifecycle"]
    FAIL --> SEC["7. Security + SBOM scan"]
    SEC --> DEPLOY["8. Canary/rollout evidence"]
~~~

| Gate | Input | Pass criterion |
|---|---|---|
| **1. Resolve** | Effective POM / `dependencyInsight` | No unexpected overrides/duplicates; intentional dependency graph |
| **2. Compile** | Sources/tests and build plugins | Compiles/packages for target JDK with zero API breaks |
| **3. Startup** | `@SpringBootTest` or test profile run | Context starts; adapters, converters, and channels present |
| **4. Message flow** | `Message<?>` with payload/headers | Transformers/routers/gateways/pollers follow contracts |
| **5. Protocol smoke** | Test files, mock HTTP, test SFTP/broker/DB | Target side effects and metadata verified |
| **6. Failure/lifecycle** | Timeouts, disconnects, duplicates, restarts | Retries/ACK/error/recovery/idempotency honor policy |
| **7. Security** | SBOM, vulnerabilities, secret scans | Versions meet policy; findings addressed |
| **8. Rollout** | Final artifact and release notes | Canary deployed/verified; metrics/logs/rollback ready |

Every gate must distinguish **actually executed vs. planned**. While authoring documentation, never mark any unexecuted project gate as PASS.

### 25.1. Network-Free Spring Integration Smoke Test Example

Inside `@SpringBootTest` or a `@SpringJUnitConfig` flow test:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.EnableIntegration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.PollableChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(DependencyCompatibilitySmokeTest.Config.class)
class DependencyCompatibilitySmokeTest {

    @Configuration
    @EnableIntegration
    static class Config {
        @Bean
        MessageChannel adapterInput() {
            return new DirectChannel();
        }

        @Bean
        PollableChannel testOutput() {
            return new QueueChannel();
        }

        @Bean
        IntegrationFlow compatibilityFlow() {
            return IntegrationFlow.from("adapterInput")
                    .<String, String>transform(String::trim)
                    .channel("testOutput")
                    .get();
        }
    }

    @Autowired
    @Qualifier("adapterInput")
    MessageChannel input;

    @Autowired
    @Qualifier("testOutput")
    PollableChannel output;

    @Test
    void canCreateAndDispatchAMessage() {
        Message<String> request = MessageBuilder
                .withPayload("  order-42  ")
                .setHeader("correlationId", "corr-42")
                .build();

        assertTrue(input.send(request));

        Message<?> reply = output.receive(1000);
        assertNotNull(reply);
        assertEquals("order-42", reply.getPayload());
        assertEquals("corr-42",
                reply.getHeaders().get("correlationId"));
    }
}
~~~

This test proves **basic Core/DSL/`MessageChannel` wiring and dispatch work** on the current graph, **not** that File/SFTP/HTTP/Kafka/JMS/AMQP/JDBC modules are protocol-compatible. Each adapter needs at least one dedicated test at its live boundary.

### 25.2. Mandatory Additional Tests per Module

- **File:** create/read real files with `@TempDir`; test filters, metadata, and restarts.
- **SFTP:** test server, host keys, downloads/uploads, reconnects/temp renames.
- **HTTP:** mock server, methods/URIs/bodies/headers, 2xx/4xx/5xx/timeouts.
- **JMS:** test provider, acknowledgments, transactions, redelivery.
- **AMQP:** test RabbitMQ, exchanges/queues, confirms/returns, DLQs.
- **Kafka:** test broker, topics/keys/schemas/offsets/consumer groups/retries.
- **JDBC:** test database, `DataSource`/driver, SQL dialects/transactions, concurrent polling.

## 26. Controlled Release-Based Dependency Upgrade Workflow

### Phase 1 — Freeze the Baseline

Record:

- Java build/runtime, Spring Boot version, resolved Spring Integration versions, and Spring Cloud train if used.
- Maven/Gradle wrapper and plugin versions.
- Container images, client libraries, drivers, and supported broker/server versions.
- Snapshot dependency tree, SBOM, build artifact digest, and current test suite.
- Known issues, baseline latency/retry/error rates, and critical flows.

### Phase 2 — Propose the Target Stack

Pick a **release line** based on support policies, not simply the highest version number. Check JDK baselines, framework majors, Integration release notes, Cloud trains, adapter migrations, and security posture.

### Phase 3 — Upgrade in Order

- For BOM-compatible patches: update the Boot BOM/parent/plugins to the approved release.
- For minor/major upgrades: plan edits to Java source, module APIs, namespaces, config properties, clients/serializers, and test utilities.
- Upgrade the Cloud BOM to the matching release train **only if the project uses Cloud**.
- Drop obsolete explicit overrides; document remaining exceptions strictly where required.
- Resolve unsupported vendor SDKs/clients via updates, replacements, or service boundaries — never force incompatible APIs together.

### Phase 4 — Run Quality Gates

Verify the dependency graph, compile/package, startup, and unit/flow/protocol/negative tests. Pay special attention to **gateway replies/errors, poller lifecycles, SSH/TLS, Kafka schemas/offsets, JMS transactions, AMQP confirms, and DB isolation**.

### Phase 5 — Rollout and Rollback

- Deploy to canary/staging per risk, watching metrics and sanitized logs.
- Keep baseline artifacts and configs ready for fast rollback.
- If schemas/message formats changed, verify rollback compatibility for **both producers and consumers** (forward/backward compatibility).
- Never roll back a critical security patch without a documented risk decision and compensating controls.
- Update SBOMs, dependency inventories, and operational docs.

### 26.1. How to Reduce Risk on Long Migrations

For major upgrades spanning many adapters, upgrade along **independently testable boundaries**: isolate client wrappers, adapter configurations, message DTOs/contracts, and test fixtures. Avoid upgrading every broker/client/provider simultaneously unless urgent, while keeping versions aligned under the BOM.

## 27. CI Automation: Version Verification as a Continuous Control

Build pipelines can enforce:

~~~text
Pull request:
  1. Validate build files (POM/Gradle)
  2. Resolve/check dependency graph
  3. Compile and run unit/flow tests
  4. Run security/SBOM checks
  5. Run protocol contract tests selectively or in CI
  6. Report changed version coordinates and risk
  7. Require code owner/security review for major overrides

Main/release:
  1. Rebuild with controlled JDK/wrapper
  2. Run full adapter integration tests
  3. Verify packaged artifact and SBOM
  4. Stage/canary deployment and monitor
  5. Promote or roll back based on evidence
~~~

Illustrative **reference commands** (not executed during documentation authoring):

~~~powershell
# Maven CI:
mvn -B -ntp clean verify
mvn dependency:tree -Dincludes=org.springframework.integration

# Gradle CI on Windows:
.\gradlew.bat clean test
.\gradlew.bat dependencyInsight --dependency spring-integration-core --configuration runtimeClasspath
~~~

In live CI, add security scanners, integration tests against real test infra, authenticated artifact mirrors/caches, and JDK/container image checks. **Never just grep version strings in POMs**: that misses dependency management, overrides, and runtime classpaths.

### 27.1. Automated Dependency Update Bots

Bots open PRs when Boot/Integration/client releases drop. Never auto-merge **major, framework, or Cloud-train** updates just because dependency resolution passed. Require:

- Before/after version summary and release notes.
- CVE identification if patching vulnerabilities.
- Dependency diff and SBOM inspection.
- Adapter tests covering impacted modules.
- Production rollback plans.

## 28. Decision Matrix: What to Fix When Hitting a Version Conflict?

| Finding | Priority remediation | What NOT to do |
|---|---|---|
| Integration core and adapter on different lines due to explicit version | Remove override, use Boot BOM; check graph/tests | Bump core alone until startup stops failing |
| Vendor SDK pulls an old Spring Framework | Upgrade to compatible SDK, inspect transitives | Blindly exclude all Spring JARs from the vendor |
| Cloud compatibility warning | Pick Cloud train compatible with Boot | Disable verifier and ship anyway |
| JMS client uses legacy namespace | Upgrade provider to API matching Boot line | Put both `javax` and `jakarta` on classpath |
| Kafka broker lacks newer feature | Check client/broker matrix; adjust valid config | Flip incompatible flags without understanding |
| SSH handshake fails after JDK upgrade | Inspect host keys, ciphers, trust, client versions | Disable host-key verification |
| DB tests pass on H2, fail on PostgreSQL | Test against prod-like DB; fix SQL/transactions | Treat in-memory dialect as full proof |
| Test-only version mismatch | Align test dependencies with Boot line | Mass-override runtime libraries |
| CVE in transitive dependency | Pick patched BOM/release; assess risk | Force unverified new major without testing |
| Release artifact differs from CI classpath | Compare JAR/image contents, toolchains, locks | Blame framework before checking artifact |
| Adapter API deprecated/removed | Read migration guide; update code + contract tests | Mix snippets from two major releases |

## 29. Pre-Merge / Pre-Release Compatibility Checklist

- [ ] Spring Boot version and support status selected with clear rationale.
- [ ] Java build/compile/runtime meet minimums and target bytecode.
- [ ] Spring Integration Core and active adapters share one BOM-aligned release line.
- [ ] Zero undocumented or untested explicit version overrides.
- [ ] Spring Cloud train compatibility verified if using Cloud Stream/binders.
- [ ] Direct adapters distinguished from binders, avoiding unneeded dependencies.
- [ ] Only genuinely required adapter modules declared.
- [ ] Dependency tree / effective POM or Gradle `dependencyInsight` / `runtimeClasspath` inspected.
- [ ] Spring Framework, messaging, serialization, and Kafka/AMQP/JMS/SSH/JDBC clients verified.
- [ ] Jakarta/Javax namespaces verified on upgrades from legacy stacks.
- [ ] Maven/Gradle plugin and wrapper versions checked.
- [ ] Unit/flow smoke tests exist for `MessageChannel`/`IntegrationFlow`.
- [ ] Integration tests exist for File, SFTP, HTTP, JMS, AMQP, Kafka, and DB **per active module**.
- [ ] Negative tests cover timeouts, reconnects, retries, duplicates, serialization, and errors.
- [ ] Tested on JDK and protocol infrastructure matching production closely.
- [ ] Security scans, SBOM, support/EOL checks, and CVE remediation plans complete.
- [ ] Artifact/container builds are reproducible with provenance/checksums per process.
- [ ] Dependency diffs, migration notes, and changed config properties reviewed.
- [ ] Release/canary monitoring and rollback plans ready.
- [ ] Sign-off clearly distinguishes which of resolution/compile/startup/protocol/security were actually verified.

## 30. Self-Assessment Scenarios

### Scenario A — "Are All Latest Versions Automatically Compatible?"

**Prompt:** A teammate grabs the newest Spring Boot, newest Spring Integration, and newest Spring Cloud release train and puts them in the POM. Maven resolves dependencies cleanly. Can we merge immediately?

**Answer:** **No.** Various "latests" can belong to incompatible release lines. Verify support matrices, BOM/resolved graphs, JDKs, Cloud trains, API migrations, and compile–startup–protocol tests. Maven resolution **does not prove** binary/runtime compatibility.

### Scenario B — "The BOM Manages Versions, So Why Is the SFTP JAR Different?"

**Prompt:** A POM uses the Boot parent yet sets an explicit version on `spring-integration-sftp` different from Core. The SFTP endpoint fails at runtime. Why?

**Answer:** An explicit version overrides BOM management, splitting Integration across mismatched lines. Inspect the effective POM / dependency tree, compare against the BOM, drop the ungrounded override, and re-verify with SFTP integration tests.

### Scenario C — "Works in IDE, Production Container Throws `UnsupportedClassVersionError`"

**Prompt:** CI/IDE uses a newer JDK while the Docker image runs an older JDK. What must be checked?

**Answer:** Toolchain/target bytecode, container Java version, and Boot/client minimum JDKs. Never check only `java.version` or developer laptops; the live runtime must support the compiled bytecode.

### Scenario D — "JMS Imports `javax.jms.ConnectionFactory` on Boot 3"

**Prompt:** A very old provider library uses `javax.jms` while the app is on Jakarta EE. Should you put both `javax.jms-api` and `jakarta.jms-api` on the classpath?

**Answer:** **Not automatically.** Those two APIs are not interchangeable. Upgrade to a provider client supporting the API required by your Spring Framework/Boot line, then test connections, transactions, redelivery, and code migrations.

### Scenario E — "Kafka Broker Is Version X, Must the Client Be Exact Version X?"

**Prompt:** A developer pins the Kafka client to match the broker version exactly instead of using the Boot BOM version. Is that always right?

**Answer:** **No.** Kafka client/broker compatibility follows feature/protocol matrices rather than identical version numbers. Consult Kafka/vendor docs, Spring Kafka versions, and protocol tests before overriding.

### Scenario F — "Spring Cloud Compatibility Verifier Blocks Startup"

**Prompt:** After adding a Kafka binder, Spring Cloud warns of a Boot/Cloud mismatch. Can we disable the compatibility verifier to deploy?

**Answer:** Silencing the warning **fixes nothing**. Pick a Cloud release train compatible with your Boot line, import the BOM properly, and verify the dependency graph plus binding/broker tests.

### Scenario G — "`NoSuchMethodError` in Spring Messaging"

**Prompt:** The app compiles cleanly yet throws `NoSuchMethodError` from a Spring Messaging class at runtime. What do you do first?

**Answer:** Inspect the actual loaded JARs, `runtimeClasspath`, and dependency graph to find the vendor SDK, explicit override, or packaging issue causing the ABI mismatch. Identify the root cause before changing versions, then rerun startup and flow tests.

### Scenario H — "SFTP Mock Test Is Green Yet Live Handshake Fails After JDK Upgrade"

**Prompt:** A mocked session passes uploads while the test SSH server fails handshakes. What is the takeaway?

**Answer:** Mocks prove handler logic only, never auth/host-key/cipher negotiation. Check SSH client versions, JDK security settings, server policies, and host keys; **never** disable host-key verification to hide the error.

### Scenario I — "All Unit Tests Pass, HTTP Integration Returns `415`"

**Prompt:** After upgrading dependencies, unit transformer tests pass yet the HTTP server returns `415 Unsupported Media Type`. Is Spring Integration Core broken?

**Answer:** Too soon to say. Check content types, HTTP header mappers, message converters/JSON serialization, client configs, and API contracts. In-memory unit tests do not verify headers/bodies serialized onto the wire.

### Scenario J — "Jackson Overridden to Patch a CVE"

**Prompt:** A team bumps one Jackson artifact alone to another major to address a CVE without testing converters. What is the risk?

**Answer:** APIs can skew across Jackson modules, Spring Web/Boot serializers, or JSON formatting behavior. Pick an aligned patch/BOM release, verify the entire serialization graph and schema compatibility, and test HTTP/Kafka/DB flows accordingly.

### Scenario K — "Database Adapter Passes on H2, Fails on PostgreSQL"

**Prompt:** SQL polling works in H2 tests, yet production PostgreSQL hits lock errors and processes records twice.

**Answer:** H2 does not faithfully replicate PostgreSQL dialects, isolation levels, or locking. Test against a production-like DB, verify transaction boundaries, concurrency, and idempotency, and never treat an H2 pass as proof for every DB.

### Scenario L — "Version Bump PR with Zero Evidence"

**Prompt:** A bot opens a Boot patch upgrade PR; the changelog says only "versions updated" with no dependency diff or test evidence. Should it auto-merge?

**Answer:** Never treat that as sufficient evidence. Enforce risk-based policy: resolved graph diffs, security scans, and unit/flow/protocol regression runs. For framework majors or Cloud trains, require migration and rollout review.

### Scenario M — "Maven Dependency Tree Looks Clean, Deploy Still Fails"

**Prompt:** Locally `dependency:tree` shows zero conflicts, yet the containerized app loads an old client.

**Answer:** Inspect the packaged artifact, base image layers, caches, server-managed classpaths, registry digests, and runtime dependencies. A source dependency tree **never replaces** inspecting the deployed JAR/image.

### Scenario N — "Include Only Needed Adapter Modules"

**Prompt:** An app uses only File and HTTP yet its POM declares Integration Kafka, JMS, AMQP, and SFTP "just in case". What is the downside?

**Answer:** Unneeded dependencies bloat update/CVE surface, classpaths, auto-configurations, and testing burden. Add only modules actually used; add new dependencies and contract tests intentionally when adding transports.

### Scenario O — "Is One Smoke Test Enough?"

**Prompt:** A `@SpringJUnitConfig` test wiring `DirectChannel` and a transformer passes after upgrading Integration. Does that prove Kafka/SFTP/HTTP compatibility?

**Answer:** **No.** A smoke test proves core/DSL/wiring in narrow scope only. Adapters also depend on clients, serialization, brokers/servers, TLS/SSH, and lifecycles; protocol integration tests are mandatory before signing off.

## 31. Conclusion

**Checking dependency version compatibility** for **Spring Boot and Spring Integration Adapters** means governing **an entire version ecosystem**, not picking the newest version number on Maven Central. The **Spring Boot BOM** aligns Spring Framework, Spring Integration, and managed libraries; the **Spring Cloud BOM/release train** belongs only where Cloud Stream/binders are used and must align with Boot. Across File, SFTP, HTTP, JMS, AMQP, Kafka, and JDBC, you must also verify **JDKs, providers/clients, brokers/servers, serializers, transactions, security, and connection lifecycles**. A sound workflow verifies **resolved dependency graph → compile → startup → `MessageChannel` flow → adapter protocol/side effects → failure/lifecycle → security/rollout**, documenting clearly what was actually tested. That discipline keeps upgrades controlled, prevents linkage failures, contract drift, and untrusted external access, and preserves safe operations and rollbacks.

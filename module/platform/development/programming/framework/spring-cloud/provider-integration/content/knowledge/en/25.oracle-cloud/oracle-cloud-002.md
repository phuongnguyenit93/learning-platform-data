# Choosing a Compatible Version Before Adding an OCI Starter

Adding an OCI starter to a Spring Boot application may look like simply adding a Maven or Gradle dependency. However, a starter pulls in Spring Boot APIs, Spring Framework, the OCI Java SDK, HTTP clients, Jackson, and other foundational libraries. Choosing the wrong version line can leave the application compiling fine yet failing at startup, missing auto-configured beans, or throwing runtime errors like `NoSuchMethodError` after deployment.

Therefore, before adding `spring-cloud-oci-starter-storage`, `spring-cloud-oci-starter-vault`, or another starter, you need to determine your **current Spring baseline**, the **Spring Cloud OCI release line**, the **OCI SDK version**, and **related Oracle projects**. This lesson presents the workflow for selecting and verifying those versions, using official documentation available as of **24-11-2026** as a reference snapshot.

## 1. Learning Objectives

After this lesson, learners can:

1. Identify the Java, Spring Boot, and Spring Framework versions the application is using.
2. Distinguish the Spring Cloud release train from Spring Cloud Oracle and Spring Cloud OCI.
3. Choose the OCI starter release line matching the Spring Boot major version.
4. Read release notes to see which specific platform a version was built and tested against.
5. Understand why Spring Cloud OCI, Oracle Database starters, the TxEventQ binder, and Spring AI Oracle have independent versions.
6. Choose the right Maven/Gradle coordinates and version management approach.
7. Avoid using the wrong BOM or forcing one single version across every Oracle artifact.
8. Inspect the dependency graph, transitive dependencies, and version conflicts.
9. Verify auto-configuration, compilation, startup, and integration tests.
10. Plan major version upgrades and diagnose compatibility errors.

## 2. Why Choose Versions Before Adding a Starter?

A starter does not stand alone. For example, adding the OCI Object Storage starter can put all of these into the dependency graph:

- Spring Boot starter and auto-configuration.
- Spring Framework APIs.
- Spring Cloud OCI core.
- OCI Java SDK modules.
- HTTP client and TLS implementation.
- Jackson and serialization libraries.
- Logging, metrics, and shared libraries.

An existing application already has dependencies for these components. Maven or Gradle resolves versions via dependency management, constraints, conflict resolution, and declaration order. If a starter requires a newer Spring Framework API while the application runs an older version, compilation or runtime can fail.

A single dependency can alter the entire graph:

~~~mermaid
flowchart TD
    A[Spring Boot application] --> B[Spring Boot dependency management]
    A --> C[Spring Cloud release train BOM if used]
    A --> D[Spring Cloud OCI starter]
    D --> E[Spring Cloud OCI core]
    E --> F[OCI Java SDK]
    D --> G[Spring Framework APIs]
    D --> H[Jackson / HTTP client / logging]
    C --> I[Spring Cloud Stream / Config / Commons]
    B --> J[Spring Boot + Spring Framework versions]
~~~

These version management sources have different scopes. Do not assume a single BOM automatically manages all Oracle dependencies simply because the project name contains "Spring Cloud".

### Common Consequences of Choosing Wrong

| Symptom | Possible Cause |
| --- | --- |
| `UnsupportedClassVersionError` | Java runtime is older than the dependency's bytecode |
| `NoClassDefFoundError` | Missing class or class was excluded from the dependency graph |
| `NoSuchMethodError` | Runtime loads a library version lacking a method required by compiled code |
| `AbstractMethodError` | API/implementation versions are incompatible |
| `ClassNotFoundException` | Missing module or package changed |
| `BeanCreationException` | Auto-configuration or bean depends on incompatible API/config |
| Missing `Storage`/`VaultTemplate` bean | Wrong starter, auto-configuration disabled, missing property, or unmet condition |
| Error when calling OCI API | May be SDK, authentication, IAM, region, or service config; not every error is a version conflict |
| Build succeeds but deploy fails | Tests did not run on the same runtime/configuration or the dependency graph differs across environments |

You cannot fix every error by bumping the starter version. First pinpoint the exact incompatible layer.

## 3. Four Version Axes to Check

### 3.1. Java Runtime and Build Tool

The Java version must satisfy the requirements of Spring Boot and every pulled-in library. For Spring Boot 4.x, the minimum Java baseline is 17. The build tool must also fall within the range supported by Spring Boot.

According to current Spring Boot documentation at the time of writing:

- Spring Boot 4.2.0 requires Java 17 or higher.
- Spring Framework 7.1.0 or higher is the corresponding foundation for Boot 4.2.
- Maven 3.6.3 or higher is supported.
- Gradle 8.x requires at least 8.14; Gradle 9.x is also supported.

These are the requirements for Spring Boot 4.2.0. Check the system requirements of the exact Boot patch your application selects, as version lines may vary.

Check your environment:

~~~bash
java -version
mvn -version
gradle --version
~~~

In CI, check the actual JDK of the build agent and container runtime. A build running on a newer JDK does not prove the production image runs the matching JDK.

### 3.2. Spring Boot and Spring Framework

Spring Boot manages a coordinated set of Spring Framework and foundational libraries. Do not upgrade `spring-core`, `spring-context`, or `spring-web` individually to fix an error without checking Boot compatibility.

For example, Spring Boot 4.1.x and 4.2.x both belong to major 4, yet they can use different Spring Framework minor lines. A library built against Framework 7.0 is not automatically tested with Framework 7.1.

Determine:

- The `org.springframework.boot` version.
- The actual resolved Spring Framework version.
- The project's Java target/release.
- Any other dependency overrides or BOMs that might override Spring Framework.

### 3.3. Spring Cloud Release Train

The Spring Cloud release train is the coordinated version set for Spring Cloud projects such as Spring Cloud Stream, Config, Circuit Breaker, Gateway, or Commons.

It has its own compatibility matrix with Spring Boot. For example, according to the current official table:

| Spring Cloud Release Train | Compatible Spring Boot |
| --- | --- |
| 2025.1.2 and later | 4.0.x and 4.1.x |
| 2025.1.x before 2025.1.2 | 4.0.x |
| 2025.0.x | 3.5.x |
| 2024.0.x | 3.4.x |
| 2023.0.2 and later | 3.2.x and 3.3.x |
| 2022.0.3 and later | 3.0.x and 3.1.x |

Release trains marked with an asterisk on the Spring Cloud page have reached end of OSS support. The compatibility table indicates which version pair has a compatibility relationship; it does not by itself prove that the release train is still supported or suitable for the OCI starter.

If the application only uses Spring Boot and Spring Cloud OCI, you do not need to add the Spring Cloud release train BOM just because the library is named Spring Cloud OCI. Only import the Spring Cloud BOM when the application uses projects belonging to the release train that need management.

### 3.4. Spring Cloud OCI and OCI Java SDK

Spring Cloud OCI has its own release line. The OCI starter in turn pulls in the OCI Java SDK and other libraries.

According to Oracle project information as of 24-11-2026:

- Spring Cloud Oracle 1.x targets Spring Boot 3.
- Spring Cloud Oracle 2.x targets Spring Boot 4 and Spring Framework 7.
- Spring Cloud OCI 2.0.4 is the current published release.
- The 2.0.4 release notes explicitly state that Spring Boot was upgraded to 4.1.1.
- OCI 2.0.4 modules use OCI Java SDK 3.91.1 in the published dependency graph.

This creates an important distinction: **being on the same major version does not mean every minor/patch has been tested**. The 2.x line targets Boot 4, yet release 2.0.4 explicitly notes an updated baseline of Boot 4.1.1. Spring Boot 4.2.0 was just released on 20-11-2026 and requires Spring Framework 7.1.0 or higher. Do not assume Spring Cloud OCI 2.0.4 is verified with Boot 4.2 solely because both are in major 4.

## 4. Reference Version Snapshot as of 24-11-2026

The following table is a snapshot for practicing how to read versions, not a mandatory version set for every application.

| Project/Line | Reference Version | Platform or Scope |
| --- | --- | --- |
| Spring Cloud OCI | 2.0.4 | Spring Boot 4.1.1 per release notes |
| Spring Cloud Oracle 1.x | 1.x line | Spring Boot 3 |
| Spring Cloud Oracle 2.x | 2.x line | Spring Boot 4, Spring Framework 7 |
| Oracle AI Database Spring Boot Starters | 26.3.0 | Database connectivity, UCP, Wallet, AQ/JMS, OKafka, and database features |
| Spring Cloud Stream Binder for TxEventQ | 0.21.0 | Spring Cloud Stream on Oracle AI Database TxEventQ |
| Spring AI Oracle | 2.0.1 | Spring AI 2.0.1; release notes list Spring Boot 4.1.1 |
| OCI Java SDK in OCI 2.0.4 dependency graph | 3.91.1 | Transitive dependency of OCI modules |

These projects have separate versions. Do not define a single `spring-cloud-oracle.version` variable and apply the same value to the OCI starter, database starter, TxEventQ binder, and Spring AI Oracle.

### Choosing Versions by Existing Platform

| Current Platform | Approach |
| --- | --- |
| Spring Boot 3.x | Choose a compatible Spring Cloud Oracle 1.x/OCI starter 1.x; verify the specific patch and 1.x docs |
| Spring Boot 4.0.x | Choose OCI 2.x, verify release notes of the specific OCI patch |
| Spring Boot 4.1.x | OCI 2.0.4 is a reference milestone whose release notes upgrade to Boot 4.1.1; verify exact Boot/Framework patches |
| Spring Boot 4.2.x | Verify whether Oracle has released an OCI version tested/documented for Boot 4.2 and Framework 7.1 before selecting |
| App with Spring Cloud Stream | Choose a Boot-compatible Spring Cloud release train, then verify the TxEventQ binder version separately |
| App with Spring AI | Check the Spring AI version and Spring AI Oracle version independently |

### Do Not Mix 1.x and 2.x in the Same Application

Do not add a 1.x OCI starter to a Boot 4 application or a 2.x starter to a Boot 3 application and expect Maven to resolve it automatically. The two release lines can differ in underlying APIs, Jakarta/Spring Framework baselines, dependency graphs, and auto-configuration.

If you need to upgrade from Boot 3 to Boot 4, treat it as a separate migration: upgrade JDK/build tool, Boot/Framework, Spring Cloud train if present, and then upgrade the OCI starter and related Oracle projects. Run tests after each step to pinpoint any breaking change.

## 5. Distinguishing the Spring Cloud BOM from the OCI Starter Version

This is one of the easiest places to make mistakes when adding dependencies.

### What Does the Spring Cloud BOM Manage?

`org.springframework.cloud:spring-cloud-dependencies` manages versions of artifacts belonging to the Spring Cloud release train. For example, if the application uses Spring Cloud Stream, Config, or Circuit Breaker, the BOM can manage those project versions.

It does not automatically manage `com.oracle.cloud.spring:spring-cloud-oci-starter-storage`.

### What Does the OCI Version Manage?

OCI starters belong to the `com.oracle.cloud.spring` group. The OCI 2.0.4 documentation lists coordinates for starters in the OCI release line. Use the published version for the exact starter and release.

Older 1.x documentation previously described a Spring Cloud OCI BOM. Do not take an old BOM example and assume that artifact/BOM is still the version management mechanism for 2.x. With 2.x releases, if the documentation for your version does not specify a BOM, specify the exact version on the starter or a team-managed internal version catalog.

### Maven Example: Spring Boot 4.1.1 and OCI 2.0.4

The following example illustrates declaring an explicit version for an OCI starter. The Spring Cloud BOM is only needed when the application actually uses Spring Cloud projects.

~~~xml
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>4.1.1</version>
    <relativePath/>
</parent>

<properties>
    <java.version>17</java.version>
    <spring-cloud.version>2025.1.2</spring-cloud.version>
    <spring-cloud-oci.version>2.0.4</spring-cloud-oci.version>
</properties>

<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-dependencies</artifactId>
            <version>2025.1.2</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>com.oracle.cloud.spring</groupId>
        <artifactId>spring-cloud-oci-starter-storage</artifactId>
        <version>2.0.4</version>
    </dependency>
</dependencies>
~~~

If the application does not use Spring Cloud projects, you can omit `spring-cloud-dependencies`. This example does not require importing the Spring Cloud BOM solely to use OCI Storage.

When using multiple OCI starters from the same release, you can declare the version in a property to prevent version drift across starters. What matters is that all OCI starters in one application follow the same verified release line.

### Gradle Example

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '4.1.1'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
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
    implementation 'org.springframework.boot:spring-boot-starter'
    implementation 'com.oracle.cloud.spring:spring-cloud-oci-starter-storage:2.0.4'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

If using Spring Cloud Stream or another Spring Cloud project, add dependency management for the release train matching Boot. Do not use the Spring Cloud train version as the OCI starter version.

### Choose the Starter, Do Not Add Duplicate Implementation Modules

Example for Object Storage:

~~~xml
<dependency>
    <groupId>com.oracle.cloud.spring</groupId>
    <artifactId>spring-cloud-oci-starter-storage</artifactId>
    <version>2.0.4</version>
</dependency>
~~~

The starter already brings in the implementation module and transitive dependencies needed for that integration. Do not manually add `spring-cloud-oci-storage` with the same version unless required by the documentation.

## 6. How to Identify the Right Artifact Before Choosing a Version

Do not search for dependencies solely by the keywords `oracle` or `oci`. First identify the service and programming model:

| Requirement | Artifact Family to Check |
| --- | --- |
| OCI Object Storage | `spring-cloud-oci-starter-storage` |
| OCI Vault | `spring-cloud-oci-starter-vault` |
| OCI Queue | `spring-cloud-oci-starter-queue` |
| OCI Streaming | `spring-cloud-oci-starter-streaming` |
| OCI Functions | `spring-cloud-oci-starter-function` |
| OCI Notifications | `spring-cloud-oci-starter-notification` |
| OCI Logging | `spring-cloud-oci-starter-logging` |
| OCI Autonomous Database lifecycle | `spring-cloud-oci-starter-adb` |
| Oracle AI Database JDBC/UCP | Oracle Database starter family |
| Oracle TxEventQ with JMS | AQ/JMS starter |
| Oracle TxEventQ with Spring Cloud Stream | TxEventQ binder |
| OCI Generative AI via Spring AI | Spring AI Oracle |

These artifacts do not share the same lifecycle or version numbers. Choose the right artifact first, then open the release notes/API docs for that artifact's exact version.

### Starter Version and SDK Version Are Two Separate Things

Applications usually declare an OCI starter. The starter pulls in the matching OCI SDK modules. You do not need to declare each individual OCI SDK artifact if you have no direct usage needs.

If the application uses the OCI SDK directly:

- Check which SDK version the starter already pulls in.
- Use a single compatible SDK version set.
- Avoid having one OCI SDK module on 3.x while another module is forced onto a different version.
- Do not override the SDK just to access a new API without verifying compatibility.
- If an override is necessary, document the reason, check release notes, and run integration tests.

## 7. Step-by-Step Version Selection Workflow

~~~mermaid
flowchart TD
    A[Inspect current build] --> B[Lock Java + Spring Boot]
    B --> C{Other Spring Cloud projects?}
    C -->|Yes| D[Choose Spring Cloud release train]
    C -->|No| E[Skip Spring Cloud BOM]
    D --> F[Choose OCI service starter]
    E --> F
    F --> G[Choose OCI release line matching Boot]
    G --> H[Read changelog and version docs]
    H --> I[Inspect SDK/transitive graph]
    I --> J[Compile + startup + integration tests]
    J --> K{Compatible and tests pass?}
    K -->|Yes| L[Lock versions and deploy to staging]
    K -->|No| M[Adjust the right version layer]
    M --> H
~~~

### Step 1: Record the Baseline

Gather from build files and the resolved dependency graph:

- Java toolchain/source compatibility.
- Spring Boot plugin/parent.
- Actual Spring Framework version.
- Spring Cloud release train if present.
- Spring Cloud Stream/Spring AI versions if present.
- Existing OCI starters or OCI SDK dependencies.
- Overrides for Jackson, Netty, HTTP clients, logging, and test libraries.

Do not only inspect the version declared in `pom.xml` or `build.gradle`; the actual resolved version is what runs in the application.

### Step 2: Lock Boot Major/Minor

Choose the Boot version based on support policy and application baseline. Check the Java runtime and Spring Framework version managed by Boot.

If currently on Boot 3, choose a compatible OCI 1.x line. If on Boot 4, look at the OCI 2.x line. Do not upgrade the Boot major version just to adopt a newer starter if the application is not ready for migration.

### Step 3: Select an OCI Release with Compatibility Evidence

Read:

- Spring Cloud Oracle release notes.
- Version-matched OCI reference docs.
- Project README/release matrix.
- The artifact's POM on Maven Central.
- Sample apps using the same release line.
- Issues/release notes regarding relevant APIs or transitive dependencies.

Look for the exact Boot version the release was built/tested against. If docs only state major compatibility, inspect release notes and CI/test matrices to verify the minor line.

### Step 4: Check Other Spring Cloud Projects

If the application uses Spring Cloud Stream, choose a Boot-compatible release train. Then check the TxEventQ binder version separately. Do not assume the Spring Cloud release train BOM manages Oracle's binder.

If the application uses no other Spring Cloud projects, do not add unnecessary BOMs. Fewer version management sources keep the dependency graph easier to reason about.

### Step 5: Add the Right Starter

Add the minimal service starter for your use case first. Check which core and SDK artifacts the starter pulls in. Do not add the implementation module directly when the starter already provides it.

### Step 6: Inspect the Graph

Use Maven/Gradle dependency reports to see resolved versions. Look for duplicates or unexpected overrides.

### Step 7: Verify Compilation, Startup, and Runtime

Run tests under the same JDK/Boot/OCI release line. Verify auto-configuration and perform a real OCI operation in a test compartment. Successful compilation does not prove authentication, IAM, or service operations work.

### Step 8: Lock and Document the Baseline

Record:

- Java version.
- Spring Boot version.
- Spring Cloud train if used.
- OCI starter version.
- Oracle Database/Binder/Spring AI versions if used.
- Resolved OCI SDK version.
- Dependency tree or SBOM.
- Test results and test environment.

## 8. Inspecting the Dependency Graph with Maven

### View the Dependency Tree

~~~bash
mvn dependency:tree
~~~

Filter key dependencies:

~~~bash
mvn dependency:tree -Dincludes=org.springframework.boot,org.springframework,org.springframework.cloud,com.oracle.cloud.spring,com.oracle.oci.sdk
~~~

View dependencies omitted due to conflicts:

~~~bash
mvn dependency:tree -Dverbose
~~~

Check effective dependency management:

~~~bash
mvn help:effective-pom
~~~

These commands help determine:

- Which OCI starter version is resolved.
- Which OCI SDK modules appear and whether versions are aligned.
- Whether Spring Boot/Framework was overridden.
- Which artifacts the Spring Cloud release train is managing.
- Whether a transitive dependency was resolved to a lower or higher version than expected.

### Enforcer and Convergence

In large projects, Maven Enforcer can detect dependency convergence issues and enforce Java/Maven rules. Do not enable strict rules mechanically if the project has legitimate dependencies requiring multiple versions; handle exceptions with clear justification and review.

Do not use `dependencyManagement` to force all `com.oracle.oci.sdk` artifacts to a newer version without verifying compatibility with the OCI starter.

## 9. Inspecting the Dependency Graph with Gradle

### View All Dependencies

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

### Inspect a Specific Dependency

~~~bash
./gradlew dependencyInsight --dependency spring-cloud-oci --configuration runtimeClasspath
~~~

~~~bash
./gradlew dependencyInsight --dependency oci-java-sdk-common --configuration runtimeClasspath
~~~

~~~bash
./gradlew dependencyInsight --dependency spring-framework --configuration runtimeClasspath
~~~

These commands show which dependency brought a module into the graph and why Gradle chose that version.

### Version Catalog

When multiple modules across an organization use OCI starters, versions can be centralized in a Gradle version catalog. Update the catalog only after verifying compatibility; a catalog does not replace reading release notes.

Do not declare a single shared version catalog alias for OCI, Oracle Database starters, and the TxEventQ binder if they follow different version lines.

## 10. Common Compatibility Errors and How to Resolve Them

### 10.1. NoSuchMethodError

Usually occurs when compile time and runtime use two different versions of the same library. For example, code compiled against a newer Spring Framework or OCI SDK while runtime loads an older version.

How to resolve:

1. Read the class/method in the stack trace.
2. Identify the artifact containing that class.
3. Use `dependency:tree` or `dependencyInsight` to locate all versions.
4. Check whether a BOM/constraint/explicit dependency overrode it.
5. Align on the proper release line rather than randomly adding a jar.

### 10.2. NoClassDefFoundError or ClassNotFoundException

Can happen because a starter is missing, an implementation module is absent from the graph, packages changed across major versions, or the runtime classpath differs from the build classpath.

How to resolve:

- Verify the exact starter artifact.
- Do not just add the core module by guesswork.
- Compare `compileClasspath` and `runtimeClasspath`.
- Inspect the shaded/packaged jar or container image.
- Compare local and CI dependency graphs.

### 10.3. BeanCreationException

A bean may fail to be created due to:

- Incompatible Spring Boot/Framework APIs.
- Misspelled property binding names.
- Authentication provider failing to initialize.
- Missing region/compartment.
- Missing or mismatched transitive dependency.
- Unmet auto-configuration condition.

Read the deepest root cause in the stack trace. Not every `BeanCreationException` is a version issue.

### 10.4. Missing Storage Bean

Check:

1. Is `spring-cloud-oci-starter-storage` declared with the right group/artifact?
2. Is the version on the same release line as Spring Boot?
3. Is the starter present on the runtime classpath?
4. Was auto-configuration excluded?
5. Did an `enabled` property or profile disable the integration?
6. Is there a conflicting custom bean or missing condition?

Use the Actuator conditions report in a controlled debug environment to see which auto-configurations were applied or skipped. Do not expose sensitive endpoints publicly.

### 10.5. OCI SDK or HTTP Client Errors

If the stack trace mentions OCI SDK, Jersey, Netty, Jackson, or TLS:

- Check the actual OCI SDK version.
- Check whether an SDK module was forced to a different version.
- Check HTTP client dependencies and the selected transport.
- Check the Java runtime and TLS provider.
- Verify which version the starter release requires.

Do not add both Jersey and Apache HTTP client just because an old example used one; follow the dependencies and configuration of your running release.

### 10.6. Compilation Succeeds but OCI Calls Return 401/403

This is usually an authentication/authorization or runtime configuration issue, not compile compatibility:

- Verify the authentication mode.
- Verify the workload identity/API key.
- Check region and compartment.
- Check IAM policies and dynamic groups.
- Check network routes, endpoints, and clock skew if using tokens/signatures.

Keep dependency version issues distinct from OCI permission errors.

## 11. Migrating from Spring Boot 3/OCI 1.x to Boot 4/OCI 2.x

A major migration must be planned as a platform change.

### Before Migration

- Record Java, Boot, Framework, and OCI starter baselines.
- Save the dependency tree and test reports.
- Check deprecated APIs.
- Identify which Oracle projects are in use.
- Review OCI 2.x samples/release notes.
- Choose the appropriate target JDK/build tool.
- Check which Spring Cloud release train needs upgrading alongside Boot.

### During Migration

1. Upgrade JDK/build tool if needed.
2. Upgrade Spring Boot and Spring Framework as a supported pair.
3. Upgrade the Spring Cloud release train if the application uses Spring Cloud projects.
4. Upgrade Spring Cloud OCI to a compatible 2.x release.
5. Upgrade database starters, TxEventQ binder, and Spring AI Oracle per their own versions.
6. Update changed packages/APIs/configuration.
7. Inspect the resolved OCI SDK graph.
8. Run compile, unit, integration, and smoke tests.
9. Verify auth, Object Storage, Vault, and messaging in an OCI test compartment.

Do not change every version all at once and only look at the final error. Break changes into groups so root causes are easier to isolate and roll back.

### After Migration

- Lock dependency versions.
- Update the container base image/JDK.
- Save the SBOM.
- Scan for CVEs and check licenses.
- Run tests on a production-like runtime.
- Monitor startup, auth, latency, retries, and resource usage after rollout.
## 12. Independent Dependency Versions Across Oracle Branches

Spring Cloud Oracle is an umbrella project, but its subprojects do not necessarily share the same release version numbers.

| Branch | Snapshot Example Version | What to Check |
| --- | --- | --- |
| Spring Cloud OCI | 2.0.4 | Spring Boot/Framework, OCI SDK, auto-configuration |
| Oracle AI Database starters | 26.3.0 | JDBC/UCP/Wallet, Oracle Database version, Boot compatibility |
| TxEventQ Stream Binder | 0.21.0 | Spring Cloud Stream train, Boot, database connectivity |
| Spring AI Oracle | 2.0.1 | Spring AI API version, Boot, OCI Generative AI |

For instance, `spring-cloud-oci-starter-storage:2.0.4` does not mean the Oracle Database UCP starter must also use `2.0.4`. The two artifacts belong to different projects and version families.

When an application uses multiple branches:

- Read the compatibility guidelines for each branch.
- Check the common Spring Boot baseline.
- Check Spring Cloud Stream/Spring AI versions separately.
- Inspect the combined dependency graph.
- Do not assume the projects were tested together if release notes do not state it.

### Example: An Application Using Multiple Oracle Projects

Suppose Invoice Service needs:

- Oracle AI Database via UCP.
- OCI Object Storage to store PDFs.
- TxEventQ to emit events.
- OCI Vault to read secrets.

The application may require different version families. Verify each starter/binder against the Boot baseline, then inspect the combined graph. If each project works alone yet conflicts when combined, the cause usually lies in shared dependencies such as Spring Framework, Jackson, the OCI SDK, the JDBC driver, or Spring Cloud Stream.

Do not force all artifacts onto the same version number just to make the build file look neater. Use the proper release version for each project.

## 13. Version Alignment and OCI Runtime Configuration

Once versions are compatible, the application still needs correct OCI configuration. This is a separate step from dependency alignment.

### Authentication

Choose authentication by environment:

- FILE for local development.
- Instance Principal for OCI Compute.
- Resource Principal for supported Functions/resources.
- Workload Identity for OKE when federation is configured.
- SIMPLE/API key when allowed by environment and policy.

Do not commit private keys or profile files to the repository.

### Region and Compartment

Verify the resource region and target compartment. An incorrect region configuration can make it look like the starter is broken even when the dependency graph is completely valid.

### IAM Policy

An authenticated identity does not guarantee permission to call services. Grant least-privilege permissions for Object Storage, Vault, Queue, or Streaming per use case.

### Timeout/Retry and Client Lifecycle

The OCI SDK has built-in retry/timeout behavior. Avoid stacking retries across multiple layers without a shared budget. Use auto-configured client beans and do not create a new client per request.

## 14. Compatibility Testing Before Merging

A minimal test suite should verify multiple layers:

| Layer | What to Verify |
| --- | --- |
| Build | Compiles with the right JDK and build tool |
| Dependency graph | No unexpected Spring/OCI SDK version conflicts |
| Context startup | Application context starts cleanly |
| Auto-configuration | Required OCI beans are created |
| Authentication | Workload authenticates using the expected identity |
| IAM | Has right permissions and is not overly broad |
| Service integration | Real operations against test resources succeed |
| Retry/timeout | Transient errors and throttling are handled properly |
| Shutdown | Clients/connections close cleanly |
| Packaging | Container runtime uses the same JDK/dependency graph |

### Context and Auto-Configuration Tests

A test that boots the Spring context helps catch missing classes or unmet bean conditions before deployment:

~~~java
@SpringBootTest
class OciStorageContextTest {

    @Autowired
    ApplicationContext context;

    @Test
    void storageBeanIsConfigured() {
        assertThat(context.getBean(Storage.class)).isNotNull();
    }
}
~~~

This test needs a suitably configured test environment. If auto-configuration requires an OCI identity at startup, use an appropriate test profile/configuration or mock for context tests. Integration tests calling real OCI services still need a test compartment and test identity.

Do not write a context test that only asserts `contextLoads` and treat it as sufficient proof for upload/download or IAM.

### Local Tests Do Not Replace Workload Identity Tests

A FILE profile may work fine on a laptop while production OKE/Compute uses a different identity. Run at least one integration test in a production-like runtime environment to verify principals and IAM policies.

### Service-Specific Testing

For Storage:

- Upload an object.
- Download and verify checksum.
- Verify metadata/content type.
- Test overwrite/conditional writes if required by the use case.

For Vault:

- Read a secret using the test identity.
- Verify access is denied when the policy is missing.
- Test rotation/refresh according to bean lifecycle.

For Queue/Streaming:

- Send and receive messages.
- Test redelivery or checkpoint/replay.
- Verify idempotency and consumer concurrency.

## 15. Version Management in CI/CD

Selected versions should be locked and continuously verified.

- Do not use dynamic versions like `latest.release` in production builds.
- Do not use snapshots outside experimental environments.
- Use Maven/Gradle dependency locking where appropriate.
- Save an SBOM per build.
- Scan for CVEs and track transitive OCI SDK updates.
- Check dependency convergence.
- Run builds with the same JDK/container as production.
- Update versions deliberately via pull requests and tests.
- Document reasons whenever overriding a starter-managed dependency.

A new patch release may update the OCI SDK, Netty, Jackson, or Spring Framework. Read release notes before upgrading, because a patch is not just a changing number.

### Version Catalog and Central Properties

If multiple services share OCI starters, centralizing versions in one place prevents each module from picking a different patch. You can use Maven properties, a Gradle version catalog, or an internal platform BOM.

However, centralization only eliminates version duplication. It does not prove compatibility. Before updating a central property:

1. Verify the release line and compatibility.
2. Review release notes and security updates.
3. Run dependency graph checks.
4. Run tests for affected services.
5. Roll out to canary or staging before production.

### Reproducible Builds

Keep dependency resolution repeatable:

- Pin plugin and dependency versions.
- Do not use version ranges for production dependencies.
- Use dependency locks where appropriate.
- Save SBOMs and build metadata.
- Verify the container image contains the exact JDK.
- Do not let a local Maven cache mask undeclared artifacts.

## 16. Lab Exercise: Choosing the OCI Storage Starter for Invoice Service

**Context:** Invoice Service currently runs Spring Boot 4.1.1 on Java 17 and needs to store PDFs in OCI Object Storage. The application does not yet use Spring Cloud Stream. Your task is to add the OCI Storage starter and prove the version graph is compatible.

### Part A — Determine the Baseline

1. Run `java -version`.
2. Check Maven/Gradle versions.
3. Identify the Spring Boot parent/plugin version.
4. Print the current dependency tree.
5. Verify the actual Spring Framework version.

### Part B — Choose the Starter

1. Choose `com.oracle.cloud.spring:spring-cloud-oci-starter-storage`.
2. Choose the OCI 2.x release line suitable for Boot 4.
3. Use `2.0.4` as the reference snapshot for Boot 4.1.1 per release notes.
4. Do not add the Spring Cloud BOM if there are no other Spring Cloud projects.
5. Do not add the `spring-cloud-oci-storage` implementation module separately when the starter already pulls it in.

### Part C — Inspect the Graph

1. Run `mvn dependency:tree` or Gradle `dependencies`.
2. Verify OCI core and SDK modules belong to the same compatible release.
3. Verify no Spring Framework version was overridden.
4. Save the resolved graph/SBOM.
5. Run compile and tests.

### Part D — Runtime Testing

1. Configure FILE authentication for local testing.
2. Configure region and compartment.
3. Grant least-privilege policies to the test identity.
4. Upload/download a test PDF.
5. Verify checksum and metadata.
6. Run tests in an OCI runtime using the corresponding production principal.

### Part E — Version Upgrade Check

1. Evaluate Boot 4.2.0 without assuming OCI 2.0.4 works out of the box.
2. Read newer Spring Cloud OCI release notes.
3. Verify whether an OCI starter has been built/tested with Boot 4.2 and Framework 7.1.
4. If unconfirmed, keep the tested baseline or run controlled compatibility tests before upgrading.
5. Record the version decision and rationale in the pull request.

### Deliverables

- Table of Java/Boot/Framework/Spring Cloud/OCI SDK versions.
- Dependency declaration for the OCI Storage starter.
- `dependency:tree` or `dependencyInsight` output.
- Proof that the application context creates the `Storage` bean.
- Upload/download integration test.
- Least-privilege IAM policy for the test workload.
- SBOM and dependency vulnerability scan results.
- Notes on compatibility evidence and upgrade decisions.

## 17. Self-Check Questions

1. Why must you identify Java and Spring Boot versions before adding an OCI starter?
2. Which projects does the Spring Cloud release train BOM manage?
3. Why is the Spring Cloud OCI version not the Spring Cloud release train version?
4. Which Spring Boot major versions do Spring Cloud Oracle 1.x and 2.x target?
5. Which specific Spring Boot baseline do the 2.0.4 release notes record?
6. Why shouldn't you assume OCI 2.0.4 is tested and compatible with Boot 4.2?
7. Where does the OCI SDK version in the dependency graph come from?
8. Why shouldn't you force all OCI SDK modules to an arbitrary version?
9. Why do database starters, the TxEventQ binder, and Spring AI Oracle have independent versions?
10. When do you need to import `spring-cloud-dependencies`?
11. Why doesn't a starter require adding the implementation module if it already pulls it transitively?
12. What kind of conflict does `NoSuchMethodError` typically indicate?
13. Does a successful build prove workload identity works?
14. What should you check when auto-configuration fails to create the `Storage` bean?
15. What evidence should be saved before merging a dependency update?

## 18. Key Takeaways

- Choose versions before adding a starter by identifying Java, Spring Boot, Spring Framework, and the OCI release line.
- The Spring Cloud release train and Spring Cloud OCI are two distinct version axes.
- OCI 1.x targets Boot 3; OCI 2.x targets Boot 4 and Spring Framework 7.
- OCI 2.0.4 release notes document upgrading to Spring Boot 4.1.1; do not assume every Boot 4 patch has been tested.
- Spring Boot 4.2.0 requires Spring Framework 7.1+, so verify specific OCI release support before upgrading.
- Oracle Database starters, the TxEventQ binder, and Spring AI Oracle have separate version families.
- Do not use the Spring Cloud BOM as a substitute for OCI starter version management.
- Add only the required service starters; do not add duplicate implementation modules.
- Inspect the resolved dependency graph rather than only reading declared versions.
- Compilation, startup, auto-configuration, and integration tests are separate verification steps.
- Distinguish dependency compatibility errors from OCI authentication, IAM, region, and network errors.
- Lock versions, store SBOMs, and update dependencies deliberately in CI/CD.

## References

- [Spring Cloud Oracle — Project overview](https://oracle.github.io/spring-cloud-oracle/site/docs/intro/)
- [Spring Cloud Oracle — Release notes](https://oracle.github.io/spring-cloud-oracle/site/docs/releases/changelog/)
- [Spring Cloud OCI 2.0.4 — OCI Core](https://oracle.github.io/spring-cloud-oracle/site/docs/oci/core/)
- [Spring Cloud OCI — Configuration properties](https://oracle.github.io/spring-cloud-oracle/site/docs/oci/configuration/)
- [Spring Cloud — Boot compatibility and getting started](https://spring.io/projects/spring-cloud/)
- [Spring Cloud — Supported versions](https://github.com/spring-cloud/spring-cloud-release/wiki/Supported-Versions)
- [Spring Boot 4.2 — System requirements](https://docs.spring.io/spring-boot/system-requirements.html)
- [Spring Boot 4.0 — System requirements](https://docs.spring.io/spring-boot/4.0/system-requirements.html)
- [Spring Cloud Oracle — Archived 1.4.5 documentation](https://oracle.github.io/spring-cloud-oracle/latest/reference/html/index.html)
- [Maven Central — Spring Cloud OCI core 2.0.4](https://central.sonatype.com/artifact/com.oracle.cloud.spring/spring-cloud-oci-core)
- [Maven Central — Spring Cloud OCI Vault 2.0.4](https://central.sonatype.com/artifact/com.oracle.cloud.spring/spring-cloud-oci-vault)
- [Maven Central — Spring Cloud OCI Queue 2.0.4](https://central.sonatype.com/artifact/com.oracle.cloud.spring/spring-cloud-oci-queue)

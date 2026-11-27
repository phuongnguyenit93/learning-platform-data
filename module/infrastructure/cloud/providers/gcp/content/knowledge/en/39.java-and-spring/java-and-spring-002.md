# Google Cloud Libraries BOM and Java Dependency Management

A Java application on Google Cloud often uses multiple client libraries at the same time: Cloud Storage for storing files, Pub/Sub for exchanging events, Secret Manager for retrieving sensitive configuration, BigQuery for analyzing data, and Cloud Logging/Monitoring for observability. These libraries in turn depend on gRPC, Protobuf, Guava, Google Auth Library, GAX, and many foundational components. If each library is picked at an independent version, the application may compile successfully yet fail at runtime due to incompatible JARs.

**Google Cloud Libraries Bill of Materials (BOM)** solves much of the version synchronization problem across Google Cloud Java libraries. A BOM provides a curated set of versions tested to work together. Maven or Gradle reads the BOM during dependency resolution, allowing the application to declare only the direct libraries it uses without manually choosing every version.

This lesson belongs to the **Java and Spring on GCP** chapter of the CLOUD_PROVIDERS_GCP module. Across the journey from projects, IAM, and VPC to Compute Engine, GKE, Cloud Run, storage, databases, deployment, and reliability monitoring, Java dependency management is a fundamental requirement for building, releasing, and operating stable applications.

## Learning Objectives

After this lesson, learners will be able to:

- Explain what a BOM is and how it differs from a dependency, plugin, or starter.
- Use `com.google.cloud:libraries-bom` in Maven and Gradle.
- Distinguish the Google Cloud client libraries BOM from the Spring Boot, Spring Cloud, and Spring Cloud GCP BOMs.
- Manage direct dependencies, transitive dependencies, and dependency scopes.
- Investigate `NoSuchMethodError`, `NoClassDefFoundError`, and Protobuf, gRPC, or Guava conflicts.
- Choose update, verification, and version-pinning practices suitable for production applications.
- Apply these principles to Java/Spring APIs using Cloud Storage, Pub/Sub, or Secret Manager.

## 1. Why Do Multiple Google Cloud Libraries Easily Conflict?

Consider a Java API that needs to read objects from Cloud Storage and publish events through Pub/Sub:

~~~text
orders-api
├── google-cloud-storage
│   ├── google-cloud-core
│   ├── google-auth-library
│   └── related HTTP / gRPC libraries
└── google-cloud-pubsub
    ├── gax
    ├── grpc-java
    ├── protobuf-java
    └── google-auth-library
~~~

This is a conceptual diagram, not the exact dependency tree of a specific release. Actual components depend on versions and build configuration.

Suppose one library calls a newer Protobuf method, while the runtime classpath contains an older Protobuf version. Java may throw:

~~~text
java.lang.NoSuchMethodError: ...
~~~

Another case is when a class that a library was compiled against is missing from the loaded JAR:

~~~text
java.lang.NoClassDefFoundError: ...
~~~

These errors usually stem from **dependency resolution**: Maven or Gradle selects a single final version for the same dependency coordinates, whereas other libraries were released expecting a different API or ABI.

A common scenario is:

1. The application uses a newer Cloud Storage version alongside an older Pub/Sub version.
2. A framework or another library pulls in its own version of Guava/gRPC/Protobuf.
3. The build tool chooses the final version based on dependency resolution rules.
4. A class is missing or a method signature is incompatible at runtime.

A BOM reduces this risk by supplying a set of versions coordinated by the publisher. However, a BOM does not guarantee compatibility with every third-party library, plugin, or runtime outside the application.

## 2. What Is a BOM and What Can It Do?

A **Bill of Materials** in the Maven ecosystem is a POM dedicated to managing dependency versions. It contains `dependencyManagement` declarations for many artifacts. An application imports the BOM to use those managed versions.

For example, a BOM specifies versions for:

- `com.google.cloud:google-cloud-storage`
- `com.google.cloud:google-cloud-pubsub`
- `com.google.cloud:google-cloud-secretmanager`
- Foundational components such as gRPC, Protobuf, Guava, GAX, and Google Auth Library

When an application declares `google-cloud-storage` without specifying a `version`, Maven uses the version managed by the BOM. In Gradle, `platform` introduces the BOM's version constraints into dependency resolution.

| Concept | Function | Automatically adds the library to the app? |
|---|---|---|
| BOM | Manages a coordinated set of dependency versions | No |
| Direct dependency | Library used directly by the application | Yes |
| Transitive dependency | Library required by another dependency | Pulled in via the dependency graph |
| Maven parent POM | Inherits build, plugin, and/or dependency management configuration | Not necessarily |
| Spring Boot starter | Bundle of dependencies serving a capability like web, actuator, or storage | Yes |
| Maven/Gradle plugin | Executes build, test, packaging, and deploy tasks | Unlike runtime dependencies |

A BOM **does not automatically add** Cloud Storage, Pub/Sub, or Secret Manager. Nor does a BOM automatically grant IAM roles, create projects, enable APIs, set up Application Default Credentials, or replace testing.

### Placing the BOM in the Right Section

With Maven, import the BOM inside `dependencyManagement`, then declare the libraries inside `dependencies`. These two sections serve different roles.

With Gradle, add `platform(...)` inside the `dependencies` block, then add `implementation(...)` for the libraries you use. Adding only the platform without specific dependencies will not place any new client libraries on the application's classpath.

## 3. What Does the Google Cloud Libraries BOM Include?

Official coordinates:

~~~text
groupId:    com.google.cloud
artifactId: libraries-bom
type:       pom
~~~

This BOM primarily manages two groups:

1. **Google Cloud Java client libraries** such as Cloud Storage, BigQuery, Pub/Sub, or Secret Manager.
2. **Foundational libraries** used by the client libraries, such as gRPC, Protobuf, Guava, GAX, Google Auth Library, and related HTTP libraries.

Client libraries are released independently, so their individual versions may differ. A BOM version such as `26.90.0` **does not mean** every client library carries version `26.90.0`.

Note: the set of artifacts managed by the BOM changes across releases. Do not assume any Java library starting with `google` is included in the BOM. Check the release artifact table or the effective dependency tree.

### When Should You Use This BOM?

- Plain Java applications using multiple Google Cloud client libraries.
- Spring Boot APIs calling Google Cloud SDKs directly.
- Library modules needing consistent gRPC/Protobuf components.
- Multi-module projects wanting centralized Google Cloud version management.
- Teams needing a repeatable version-upgrade workflow through CI.

You can use the BOM even when an application depends on just one Google Cloud client library. This provides a consistent upgrade path when more services are added later.

### Which Version to Choose

The examples below use **`26.90.0`**, the version shown in the Google Cloud BOM documentation at the time of writing. This is an **illustrative reference**, not a guarantee that it will remain the latest version in the future. When creating a project, confirm supported releases and release notes at:

- https://cloud.google.com/java/docs/bom
- https://github.com/googleapis/java-cloud-bom/releases

Keep the BOM version pinned in source code; upgrade via tested pull requests rather than pulling the latest version automatically on every build.

## 4. Maven Practice: A Java API Using Storage and Pub/Sub

Here is a simple example using Java 17, Maven, and two Google Cloud client libraries.

### Declaring the BOM in pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>example.gcp</groupId>
    <artifactId>orders-api</artifactId>
    <version>1.0.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>com.google.cloud</groupId>
                <artifactId>libraries-bom</artifactId>
                <version>26.90.0</version>
                <type>pom</type>
                <scope>import</scope>
            </dependency>
        </dependencies>
    </dependencyManagement>

    <dependencies>
        <dependency>
            <groupId>com.google.cloud</groupId>
            <artifactId>google-cloud-storage</artifactId>
        </dependency>
        <dependency>
            <groupId>com.google.cloud</groupId>
            <artifactId>google-cloud-pubsub</artifactId>
        </dependency>
    </dependencies>
</project>
~~~

Key details in this configuration:

- `type=pom` and `scope=import` tell Maven this is a BOM imported for version management.
- `dependencyManagement` selects versions without adding JARs to the classpath on its own.
- Both direct dependencies live under `dependencies` and **omit the version**.
- `maven.compiler.release` sets the target Java source/bytecode level and does not replace checking the minimum JDK required by libraries.
- Do not place the BOM inside `dependencies` intending to use it as a runtime JAR.

### Adding a New Service

When the application needs Secret Manager, add:

~~~xml
<dependency>
    <groupId>com.google.cloud</groupId>
    <artifactId>google-cloud-secretmanager</artifactId>
</dependency>
~~~

If that artifact is managed by the BOM release, Maven provides the corresponding version. There is no need to copy a version from an individual SDK page and manually synchronize it with other SDKs.

### Inspecting Which Versions Maven Selected

In the project directory, run:

~~~bash
mvn dependency:tree
~~~

To focus on commonly conflicting groups:

~~~bash
mvn dependency:tree -Dincludes=com.google.cloud,com.google.protobuf,io.grpc,com.google.guava
~~~

To view the effective POM after Maven processes parent inheritance and dependency management:

~~~bash
mvn help:effective-pom
~~~

The output can be lengthy; when investigating an artifact, search for it in both the dependency tree and the managed dependencies section of the effective POM. Do not assume the BOM takes effect solely because `pom.xml` has an import entry: a direct version or another BOM can still influence the final result.

### Effect of dependencyManagement

Suppose the team previously wrote:

~~~xml
<dependency>
    <groupId>com.google.cloud</groupId>
    <artifactId>google-cloud-storage</artifactId>
    <version>CHOSEN_VERSION</version>
</dependency>
~~~

After importing the BOM, remove the `version` line from this dependency. A directly declared version typically takes precedence for that dependency, defeating the benefit of consistent BOM management.

## 5. Gradle Groovy DSL Practice

With Gradle's BOM support, use `platform` inside the dependencies block.

~~~groovy
plugins {
    id 'java'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation platform('com.google.cloud:libraries-bom:26.90.0')

    implementation 'com.google.cloud:google-cloud-storage'
    implementation 'com.google.cloud:google-cloud-pubsub'
    implementation 'com.google.cloud:google-cloud-secretmanager'
}
~~~

The `platform(...)` line brings the BOM constraints into the `implementation` configuration. Direct dependencies omit versions if managed by the BOM.

### Kotlin DSL

Equivalent configuration in `build.gradle.kts`:

~~~kotlin
plugins {
    java
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

dependencies {
    implementation(platform("com.google.cloud:libraries-bom:26.90.0"))

    implementation("com.google.cloud:google-cloud-storage")
    implementation("com.google.cloud:google-cloud-pubsub")
    implementation("com.google.cloud:google-cloud-secretmanager")
}
~~~

### platform vs enforcedPlatform

Gradle supports two important modes:

| Mode | Meaning | When to use |
|---|---|---|
| `platform` | Introduces constraints from the BOM into dependency resolution; still respects other constraints | Default choice for applications |
| `enforcedPlatform` | Forces the versions in the BOM, potentially overriding selections from other dependencies | Consider only after understanding all conflicts |

Do not use `enforcedPlatform` as a first fix for `NoSuchMethodError`. Forcing versions this way can break another library and also propagates to consumers if published from a library. Inspect the dependency tree and find the root cause first.

### Viewing the Dependency Graph in Gradle

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Investigating Protobuf specifically:

~~~bash
./gradlew dependencyInsight --dependency protobuf-java --configuration runtimeClasspath
~~~

Investigating gRPC or Guava:

~~~bash
./gradlew dependencyInsight --dependency grpc-core --configuration runtimeClasspath
./gradlew dependencyInsight --dependency guava --configuration runtimeClasspath
~~~

On Windows, you can use `gradlew.bat` instead of `./gradlew`. The `dependencyInsight` output explains why Gradle chose a version, even when multiple sources impose different constraints.

## 6. How Do Maven and Gradle Resolve Conflicts?

The two build tools use different models, so the same BOM may not produce an identical classpath when multiple frameworks or external libraries are present.

### Maven

Maven uses dependency mediation. For transitive dependencies, the nearest definition rule decides when multiple paths in the dependency tree request different versions. `dependencyManagement` controls versions for matching dependencies. A direct dependency declaring a `version` can override BOM management.

When importing multiple BOMs inside `dependencyManagement`, declaration order can decide the version of overlapping artifacts: the entry imported earlier typically takes precedence for the same artifact unless another configuration overrides it. If using a parent POM, inherited dependency management can also affect the outcome.

Therefore, with Maven, inspect the **effective POM** and **dependency tree** rather than guessing from file order without verification.

### Gradle

Gradle resolves dependencies using a graph and version constraints. `platform` provides constraints, though other dependencies can suggest or require higher versions. `enforcedPlatform` strictly enforces versions and carries broader side effects.

For reproducible builds:

- Commit the Gradle Wrapper.
- Pin platform and plugin versions.
- Consider dependency locking and dependency verification per project policy.
- Inspect `dependencyInsight` in CI when explaining version changes.

### Three Common Reasoning Mistakes

1. **"The BOM is imported, so every JAR is guaranteed compatible."** False when out-of-scope libraries, dependency overrides, or the runtime provide different JARs.
2. **"Adding the BOM automatically gives me the Cloud Storage client."** False: you must add `google-cloud-storage` to dependencies.
3. **"The BOM version is the version of all libraries."** False: the BOM has its own version and manages artifacts with their own individual versions.

## 7. Spring Boot: Three BOM Groups to Distinguish

In a Spring application, three or four different BOMs may appear:

| BOM | Maven coordinates | Scope |
|---|---|---|
| Spring Boot | `org.springframework.boot:spring-boot-dependencies` | Core Spring Boot libraries and foundational dependencies |
| Spring Cloud | `org.springframework.cloud:spring-cloud-dependencies` | Spring Cloud modules by release train |
| Spring Cloud GCP | `com.google.cloud:spring-cloud-gcp-dependencies` | Starters and integration modules connecting Spring with Google Cloud |
| Google Cloud Libraries | `com.google.cloud:libraries-bom` | GCP client libraries and Google foundational libraries |

**Spring Cloud GCP BOM and Google Cloud Libraries BOM are not the same artifact.** One manages starters and integration framework modules; the other manages client SDKs and core dependencies.

### Check Spring Compatibility Before Choosing a BOM

The Spring Cloud GCP line must match Spring Boot and Spring Framework. According to the compatibility matrix published in the Spring Cloud GCP repository:

- Spring Cloud GCP **8.x** is for Spring Boot **4.0.x/4.1.x** and Spring Cloud **2025.1.x**.
- Spring Cloud GCP **7.x** is for Spring Boot **3.5.x** and Spring Cloud **2025.0.x**.
- Spring Cloud GCP **6.x** is for Spring Boot **3.4.x** and Spring Cloud **2024.0.x**.

This is a **major/minor** mapping and does not assert that every patch release is compatible with every custom application dependency. When upgrading, check the official matrix, release notes, and test suite at: https://github.com/GoogleCloudPlatform/spring-cloud-gcp

### Maven Template for Spring Boot + Spring Cloud GCP

The following example focuses on BOMs. Both `SPRING_BOOT_VERSION` and `SPRING_CLOUD_GCP_VERSION` are placeholders: replace them with a compatible release pair before building.

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>SPRING_BOOT_VERSION</version>
        <relativePath/>
    </parent>

    <groupId>example.gcp</groupId>
    <artifactId>orders-spring-api</artifactId>
    <version>1.0.0-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>com.google.cloud</groupId>
                <artifactId>spring-cloud-gcp-dependencies</artifactId>
                <version>SPRING_CLOUD_GCP_VERSION</version>
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
            <groupId>com.google.cloud</groupId>
            <artifactId>spring-cloud-gcp-starter-storage</artifactId>
        </dependency>
        <dependency>
            <groupId>com.google.cloud</groupId>
            <artifactId>spring-cloud-gcp-starter-pubsub</artifactId>
        </dependency>
    </dependencies>
</project>
~~~

The Spring Boot parent manages many foundational libraries and plugins. The Spring Cloud GCP BOM manages the corresponding starters. Inspect the dependency tree of a compatible pairing rather than adding another Google Cloud Libraries BOM out of habit.

If the API directly uses `com.google.cloud:google-cloud-storage` outside the starters, check the SDK version currently managed by Spring Cloud GCP/BOM. Only import `libraries-bom` additionally when there is a specific need and you have analyzed its impact on other dependencies.

### When Combining Multiple BOMs

Importing multiple BOMs can cause version conflicts in shared groups such as gRPC, Protobuf, Guava, Spring, or Netty. A safe workflow:

1. Select Spring Boot and Spring Cloud GCP according to the compatibility matrix.
2. Check which BOM manages each artifact.
3. Add the Google Cloud Libraries BOM only if you need to align SDKs not already resolved properly by the current configuration.
4. Use `mvn help:effective-pom` and `mvn dependency:tree` to inspect actual resolved versions.
5. Run integration tests against the GCP services in use.
6. Only override a dependency for a clear reason, with tests proving it works and a plan to remove the override.

With Gradle, check interactions between `platform(...)`, the Spring Boot plugin, and the dependency-management plugin if used. Do not copy a Maven configuration straight to Gradle assuming precedence order behaves identically.

## 8. Using Client Libraries in Java Code

Once the BOM and dependencies are ready, the application can construct clients normally. Example checking object existence in Cloud Storage:

~~~java
import com.google.cloud.storage.Blob;
import com.google.cloud.storage.BlobId;
import com.google.cloud.storage.Storage;
import com.google.cloud.storage.StorageOptions;

public class StorageExample {
    public static boolean objectExists(String bucket, String objectName) {
        Storage storage = StorageOptions.getDefaultInstance().getService();
        Blob blob = storage.get(BlobId.of(bucket, objectName));
        return blob != null;
    }
}
~~~

`StorageOptions.getDefaultInstance()` typically uses **Application Default Credentials (ADC)**. This is an authentication mechanism, not a BOM feature.

In a development environment:

~~~bash
gcloud auth application-default login
~~~

On Cloud Run, use the service's service account. On GKE, prefer Workload Identity Federation for GKE or a supported workload identity mechanism. Grant least-privilege permissions to the workload identity—such as object read access on the required bucket; never commit service account JSON keys to the repository.

This example illustrates the link between dependencies and runtime: the BOM helps select compatible libraries, while IAM permissions, API enablement, networking, and credentials determine whether API calls succeed.

## 9. Dependency Management in Multi-Module Projects

Suppose a repository has this structure:

~~~text
java-cloud-system/
├── pom.xml                (parent)
├── common-model/
│   └── pom.xml
├── order-service/
│   └── pom.xml
└── billing-worker/
    └── pom.xml
~~~

To prevent each module from picking a different BOM, the parent POM can import one Google Cloud Libraries BOM. Child modules inherit `dependencyManagement` and declare their direct dependencies without repeating versions.

Key snippet in the parent POM:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.google.cloud</groupId>
            <artifactId>libraries-bom</artifactId>
            <version>26.90.0</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

In the `order-service` module:

~~~xml
<dependencies>
    <dependency>
        <groupId>com.google.cloud</groupId>
        <artifactId>google-cloud-storage</artifactId>
    </dependency>
</dependencies>
~~~

Do not add every client library to the parent `dependencies` if only certain modules use them. Doing so puts unnecessary libraries onto the classpath of all modules. Keep version management in the parent, and declare actual dependencies in the modules that use them.

With Gradle multi-project builds, you can create a convention plugin or a shared platform, then apply it to modules needing GCP SDKs. Keep a single point of control for BOM updates; avoid duplicating version strings that can drift apart.

## 10. Investigating Dependency Errors in Practice

### NoSuchMethodError or NoClassDefFoundError

Common symptoms:

~~~text
java.lang.NoSuchMethodError: io.grpc....
java.lang.NoClassDefFoundError: com/google/protobuf/....
~~~

Investigation workflow:

1. Capture the full stack trace and the missing class/method.
2. Identify whether the error occurs in tests, local JVM, Docker, or Cloud Run/GKE runtime.
3. Inspect the dependency tree for the **runtime** configuration.
4. Check for multiple version management sources or pinned direct dependencies.
5. Check BOM release notes and major changes such as Protobuf 4.x.
6. Upgrade the BOM/framework or remove overrides in an isolated test branch.
7. Re-run unit tests, integration tests, and smoke tests.
8. Inspect the actual JARs packaged inside the published image or artifact.

If the application fails only on Hadoop, Spark, or a custom Java server, the runtime classpath may contain Guava, Netty, or Protobuf provided by that platform. An application's BOM does not automatically remove JARs injected by an external runtime.

### Protobuf 3.x and 4.x Conflicts

Google Cloud Libraries BOM releases have introduced changes related to Protobuf 4.x. If the application or a third-party library still relies on older APIs, upgrading the BOM may expose linkage errors.

Read the release notes for the BOM version you are upgrading to and identify libraries depending on Protobuf. Do not immediately force `protobuf-java` back to an older version while keeping newer Google Cloud libraries: that may fix one error while causing another.

### Guava -jre and -android Errors

Guava has artifact variants such as `-jre` and `-android` in the Maven ecosystem. If Java code calls a method available only in the JRE variant, check the actual resolved Guava version and dependency constraints.

Do not apply a Guava override across every project just because older documentation gave `-android` examples. Current BOMs have evolved across releases. Before making adjustments, check the dependency tree and corresponding release notes.

### Build Succeeds but Production Still Fails

Check:

- Whether the runtime JDK matches the major version of the compiled bytecode.
- Whether the Docker image contains the latest dependencies/JARs from the build.
- Whether old JARs exist in an application server or external classpath.
- Whether there are conflicts with `spring-boot-loader`, shading, or assembly.
- Whether CI cached an old artifact or deployed the wrong image tag.
- Whether APIs are enabled and ADC/IAM are correct; `PERMISSION_DENIED` is usually an authorization error, not a BOM issue.

## 11. Inspection Tools and CI Policies

Dependency management requires both pre-build checks and runtime checks.

| Tool | Question answered |
|---|---|
| `mvn dependency:tree` | Which library pulls in a transitive version? |
| `mvn help:effective-pom` | Which version does Maven manage after inheritance/imports? |
| `./gradlew dependencies` | What is the dependency graph of a configuration? |
| `./gradlew dependencyInsight` | Why did Gradle select this version? |
| Maven Enforcer | Are build rules such as upper bounds or dependency convergence violated? |
| Linkage Checker | Are there unresolvable class/method references in the bytecode? |
| SCA/dependency scanning | Are there vulnerability or license alerts to address? |
| Unit/integration/smoke tests | Does the application work with the resolved JARs? |

Google provides the **Linkage Checker Enforcer Rule** to detect certain linkage errors during the build. It is a helpful layer for the gRPC, Protobuf, and Guava ecosystem, though it does not replace integration testing.

Recommended CI stages:

~~~text
Pull request
    |
    v
Dependency resolution
    |
    v
Dependency/tree & policy checks
    |
    v
Compile + unit tests
    |
    v
Linkage/security checks
    |
    v
Integration tests (test project)
    |
    v
Package container / artifact
    |
    v
Smoke test in staging
    |
    v
Review + deploy
~~~

Not every small project needs the full toolset on day one. At minimum, maintain a controlled BOM version, reproducible dependency tree, critical functional tests, and security checks on updates.

## 12. Safe BOM Upgrade Strategy

When a new BOM release arrives, do not change all versions without controls.

1. **Check release notes:** identify major changes in gRPC, Protobuf, Guava, Google Auth Library, and the client libraries in use.
2. **Determine scope:** list apps/modules importing the BOM and other frameworks with their own BOMs.
3. **Bump one BOM version:** create a separate pull request; avoid changing JDK, Spring Boot, or Docker base images simultaneously unless necessary.
4. **Compare dependency trees before and after:** note artifacts bumped in major/minor versions.
5. **Run build and tests:** include unit tests and integration tests for Storage, Pub/Sub, or services actually used.
6. **Check security advisories:** BOM compatibility does not mean every dependency is free of vulnerabilities.
7. **Verify on staging:** run smoke tests and watch for runtime errors, latency, memory, and startup behavior.
8. **Roll out progressively:** use canary or progressive rollouts for high-reliability systems.
9. **Keep a rollback path:** preserve the previous commit and verified image tag.
10. **Update documentation:** record the BOM version, upgrade rationale, notable changes, and test results.

With Spring Boot, always prioritize the **Spring Cloud GCP compatibility matrix**. If a newer Google Cloud Libraries BOM release conflicts with your current framework, it is not necessarily a client library bug. You may need to upgrade the release train together or wait for a supported integration release.

## 13. Practical Scenario: Adding Secret Manager to a Spring API

**Context:** a team operates a Spring Boot API on Cloud Run. The app currently uses the Spring Cloud GCP Storage starter and needs to read a secret from Secret Manager. A developer wants to copy the latest `google-cloud-secretmanager` version into `pom.xml`.

Recommended approach:

1. Verify that the Spring Boot and Spring Cloud GCP versions in use are compatible.
2. Inspect the effective POM to see which BOM already manages the Secret Manager client.
3. If using the corresponding Spring Cloud GCP starter, prefer the starter and version management from the Spring Cloud GCP BOM.
4. If the direct client SDK is needed, declare the artifact and let the appropriate BOM manage its version.
5. Run `dependency:tree` to inspect Guava, Protobuf, and gRPC versions.
6. Use Cloud Run's ADC/service identity; grant IAM Secret Manager Secret Accessor on the specific secret.
7. Test reading the secret in a test project without printing the secret value to logs.
8. Push the change through CI and verify startup after deploying to staging.

**Review question:** if the runtime throws `NoClassDefFoundError` after adding Secret Manager, should you manually add a Protobuf version?

**Resolution:** first inspect the actual classpath and dependency tree, check what the BOM manages, and check whether any override or packaging plugin is pulling in an old JAR. Only change versions based on evidence, accompanied by tests proving the fix. Do not patch it by adding a random JAR.

## 14. Production Readiness Checklist

- [ ] Java/JDK and client library versions meet the application's support requirements.
- [ ] Project imports the Google Cloud BOM or an appropriate framework integration BOM.
- [ ] Direct client libraries do not arbitrarily pin versions if already managed by the BOM.
- [ ] Maven/Gradle dependency tree has been inspected.
- [ ] For Spring Boot, the Spring Cloud GCP compatibility matrix has been confirmed.
- [ ] No Guava, gRPC, Protobuf, or Netty overrides exist without a clear reason.
- [ ] CI builds and runs unit/integration tests for the GCP services used.
- [ ] Dependency vulnerability scanning follows organizational policy.
- [ ] Runtime image/artifact contains the exact tested JARs and JDK.
- [ ] Workload ADC and IAM are configured independently of the BOM.
- [ ] Each BOM upgrade has release notes reviewed, testing, and a rollback plan.
- [ ] No credentials, private keys, or secrets are committed to source code.

## Review Questions

1. Why can an application hit `NoSuchMethodError` even though Maven compiled cleanly?
2. What happens if you add the BOM to `dependencyManagement` without declaring `google-cloud-storage` in `dependencies`?
3. What is the difference between `platform` and `enforcedPlatform` in Gradle?
4. Why should you not automatically use the latest Spring Cloud GCP release with an older Spring Boot version?
5. When a dependency is managed by two BOMs, which command tells you which version Maven selected?
6. Does a BOM resolve `PERMISSION_DENIED` when Cloud Run calls Secret Manager? Why or why not?

## Conclusion

The Google Cloud Libraries BOM helps Java applications use a coordinated set of Google Cloud client libraries and foundational dependencies. The standard approach is importing `com.google.cloud:libraries-bom` in Maven `dependencyManagement` or using Gradle `platform`, then declaring direct client libraries without specifying versions manually.

In Spring Boot, distinguish among the Spring Boot, Spring Cloud, Spring Cloud GCP, and Google Cloud Libraries BOMs. The framework compatibility matrix and actual dependency tree dictate how to combine them. A BOM reduces conflicts, but it does not replace inspecting the classpath, runtime testing, security scanning, managing ADC/IAM, or maintaining a release process with rollback.

By managing dependencies through a single point of control, verifying every upgrade, and limiting overrides, development teams can add GCP services to Java applications while keeping builds and operations predictable.

## References

- [Google Cloud: Use Bill of Materials (BOM) with Cloud Client Libraries for Java](https://cloud.google.com/java/docs/bom)
- [Google Cloud: Set up a Java development environment](https://cloud.google.com/java/docs/setup)
- [Google Cloud: Troubleshoot Cloud Client Libraries for Java](https://cloud.google.com/java/docs/troubleshooting)
- [Google Cloud Libraries BOM repository and release notes](https://github.com/googleapis/java-cloud-bom)
- [Spring Cloud GCP project](https://spring.io/projects/spring-cloud-gcp/)
- [Spring Framework on Google Cloud: Compatibility and BOM](https://github.com/GoogleCloudPlatform/spring-cloud-gcp)
- [Spring Cloud release train](https://spring.io/projects/spring-cloud/)
- [Maven dependency mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html)
- [Gradle: Importing Maven BOMs](https://docs.gradle.org/current/userguide/platforms.html)
- [Cloud Open Source Java: Linkage Checker](https://github.com/GoogleCloudPlatform/cloud-opensource-java)
- [Application Default Credentials](https://cloud.google.com/docs/authentication/application-default-credentials)

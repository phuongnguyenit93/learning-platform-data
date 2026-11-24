# Publishing a Plain Library JAR Instead of Using an Executable JAR as a Dependency

A Spring Boot application is usually packaged as an **executable JAR** to run with `java -jar`. However, that format is unsuitable for use as a regular dependency of another Maven/Gradle application. If a module containing shared code or a custom starter is published as a library, the artifact consumers receive must be a **plain library JAR**.

**Core principle:** a Spring Boot executable JAR places application classes in `BOOT-INF/classes` and nested dependencies in `BOOT-INF/lib`. Standard Java class loaders and Maven consumers do not automatically read these special locations as a library JAR's classpath. A plain library JAR places classes at package paths from the archive root, e.g., `com/example/api/PaymentClient.class`; dependencies are declared in the POM for Maven to resolve.

There are three approaches:

1. **Best:** extract reusable code into a dedicated library module; that module publishes a plain JAR, while the application module produces the executable JAR.
2. **One module needs both artifacts:** keep the plain JAR as the main artifact and attach the executable JAR with a classifier such as `exec`.
3. **Module is strictly a library:** do not run `spring-boot:repackage`; if the execution is inherited from a parent or shared configuration, enable `spring-boot.repackage.skip` for that module.

## 1. Why Is an Executable JAR Not a Library JAR?

A JAR is a ZIP format with structured entries. The difference lies in **how it is packaged and how it is launched**.

### 1.1. Plain Library JAR

A library JAR has a structure roughly like:

```text
shared-api-1.0.0.jar
├── META-INF/
│   ├── MANIFEST.MF
│   └── maven/
├── com/
│   └── example/
│       └── api/
│           ├── PaymentClient.class
│           └── PaymentRequest.class
└── META-INF/
    └── spring/
        └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Classes reside at **the archive root following exact package paths**. When Maven places the JAR onto the compile/runtime classpath, the JVM can locate `com.example.api.PaymentClient` under standard classpath rules.

Library JARs typically **do not embed all dependencies**. Instead, the POM published alongside the artifact describes dependencies, versions, and scopes. Maven consumers read the POM to download required dependencies along the dependency graph. This is the standard model for a Java library.

### 1.2. Spring Boot Executable JAR

When the Maven plugin runs the `repackage` goal, the JAR is transformed into an executable archive. Typical structure:

```text
service-app-1.0.0.jar
├── META-INF/
│   └── MANIFEST.MF
├── org/springframework/boot/loader/...
└── BOOT-INF/
    ├── classes/
    │   └── com/example/app/Application.class
    ├── lib/
    │   ├── spring-boot-*.jar
    │   ├── spring-context-*.jar
    │   └── other-dependency.jar
    └── classpath.idx
```

- `BOOT-INF/classes` holds the application's classes and resources.
- `BOOT-INF/lib` holds dependencies as nested JARs.
- The Boot loader inside the archive knows how to read this special layout and construct the appropriate class loader when running the executable archive.
- The manifest is managed by the plugin, typically with `Main-Class` pointing to Spring Boot's launcher and `Start-Class` pointing to the application's main class.

It can be run with:

```bash
java -jar service-app-1.0.0.jar
```

Yet when another project declares this executable JAR as a regular Maven dependency, Maven only adds that JAR file itself to the classpath. The JVM does not treat `BOOT-INF/classes` as the classpath root, nor does it open every JAR inside `BOOT-INF/lib`. Thus application classes cannot be found the way consumers expect.

**Conclusion:** an executable JAR remains a valid JAR to run via the Boot launcher, yet it lacks the layout of a plain library JAR. Renaming the file or changing `finalName` does not fix the internal layout.

## 2. Recognizing Errors When Mistakenly Using an Executable JAR as a Dependency

Suppose a consumer project declares:

```xml
<dependency>
    <groupId>com.example</groupId>
    <artifactId>shared-api</artifactId>
    <version>1.0.0</version>
</dependency>
```

Maven resolves the dependency successfully, yet consumer code:

```java
import com.example.api.PaymentClient;

public class CheckoutService {
    private final PaymentClient client;

    public CheckoutService(PaymentClient client) {
        this.client = client;
    }
}
```

may hit compile errors such as:

```text
package com.example.api does not exist
cannot find symbol: class PaymentClient
```

Or when the failure appears only at runtime:

```text
java.lang.NoClassDefFoundError: com/example/api/PaymentClient
Caused by: java.lang.ClassNotFoundException: com.example.api.PaymentClient
```

The exact message depends on which parts of the classpath the compiler/runtime saw. The diagnostic signature is that **the artifact resolved, yet classes are not in the location standard classpaths search**.

Common symptoms:

- The dependency appears in `mvn dependency:tree`, yet class imports still fail.
- `jar tf artifact.jar` shows classes sitting under `BOOT-INF/classes`.
- `BOOT-INF/lib` contains nested dependencies, yet consumers do not see them as transitive dependencies.
- Using an executable classifier like `exec` in a dependency declaration even when the classifier-less main artifact is already a plain JAR.
- An application module both holds shared code and gets repackaged; consumer modules depend on the main artifact that was replaced by the executable JAR.

Do not rush to manually add every JAR inside `BOOT-INF/lib` onto the consumer classpath. That bypasses POM metadata, causes version drift, and fails to solve the problem that the module's own classes sit under `BOOT-INF/classes`.

## 3. Recommended Design: Separate the Library Module and Application Module

If code will be used by multiple applications, a multi-module structure keeps artifact boundaries clear:

```text
payment-platform/
├── pom.xml
├── payment-api/
│   ├── pom.xml
│   └── src/main/java/com/example/payment/
│       ├── PaymentClient.java
│       └── PaymentRequest.java
└── checkout-app/
    ├── pom.xml
    └── src/main/java/com/example/checkout/
        └── CheckoutApplication.java
```

- `payment-api` contains interfaces, DTOs, abstractions, or shared code. This module publishes a **plain JAR**.
- `checkout-app` depends on `payment-api` and contains `@SpringBootApplication`, deployment configuration, and the main class.
- Only `checkout-app` applies `spring-boot-maven-plugin` to build an executable JAR.

### 3.1. Parent POM Declaring Modules

Example `payment-platform/pom.xml` using the Spring Boot parent to manage dependency/plugin versions:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>payment-platform</artifactId>
    <version>1.0.0</version>
    <packaging>pom</packaging>

    <modules>
        <module>payment-api</module>
        <module>checkout-app</module>
    </modules>
</project>
```

Version `3.3.13` is chosen as an example aligned with Boot 3.3 documentation; real projects should use an organization-standardized version.

### 3.2. POM of the Library Module

`payment-api/pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>com.example</groupId>
        <artifactId>payment-platform</artifactId>
        <version>1.0.0</version>
    </parent>

    <artifactId>payment-api</artifactId>
    <packaging>jar</packaging>

    <dependencies>
        <!-- Declare only dependencies the API actually needs. -->
    </dependencies>
</project>
```

Maven produces a plain JAR by default in the `package` phase. A library module **does not need** `spring-boot-maven-plugin` or the `repackage` goal. If the repackage plugin is declared in an internal parent POM and inherited by this module, skip it in the module:

```xml
<properties>
    <spring-boot.repackage.skip>true</spring-boot.repackage.skip>
</properties>
```

Or configure `<skip>true</skip>` inside the module's `spring-boot-maven-plugin`. The `spring-boot.repackage.skip` property is the user property of the `repackage` goal. Use this only when the module actually inherits that execution; if the plugin is not applied, there is no need to add skip configuration.

**Note:** merely declaring `spring-boot-starter-parent` does not automatically repackage every JAR. The parent prepares the `repackage` execution for the plugin; the plugin still must be applied by build configuration. Inspect the effective POM to see which modules actually run this goal.

### 3.3. POM of the Application Module

`checkout-app/pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>com.example</groupId>
        <artifactId>payment-platform</artifactId>
        <version>1.0.0</version>
    </parent>

    <artifactId>checkout-app</artifactId>
    <packaging>jar</packaging>

    <dependencies>
        <dependency>
            <groupId>com.example</groupId>
            <artifactId>payment-api</artifactId>
            <version>1.0.0</version>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
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

If the project inherits `spring-boot-starter-parent`, the parent already configures the `repackage` execution; declaring the plugin activates that execution. If only importing the BOM without inheriting the parent, declare the plugin version and the `repackage` goal in an execution per the Maven plugin documentation.

Expected results:

- `payment-api/target/payment-api-1.0.0.jar` is a plain JAR.
- `checkout-app/target/checkout-app-1.0.0.jar` is an executable JAR.
- `checkout-app` consumes `payment-api` via regular dependency coordinates.

Build both modules from the root:

```bash
mvn clean package
```

Install into the local Maven repository only:

```bash
mvn clean install
```

When publishing for other projects, run `mvn deploy` after configuring your organization's repository and credentials. The `payment-api` artifact is published with a POM describing required dependencies; the application's executable artifact is used for deployment and execution.

## 4. One Module Needs to Publish Both a Plain JAR and an Executable JAR

Sometimes code cannot be split immediately, or a module serves both as a reusable artifact and requires a standalone runnable build. With Maven, configure a **classifier for the executable archive** to keep the plain JAR as the main artifact.

Example `pom.xml` when using `spring-boot-starter-parent`:

```xml
<build>
    <plugins>
        <plugin>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-maven-plugin</artifactId>
            <executions>
                <execution>
                    <id>repackage</id>
                    <configuration>
                        <classifier>exec</classifier>
                    </configuration>
                </execution>
            </executions>
        </plugin>
    </plugins>
</build>
```

Here execution id `repackage` is the execution prepared by the Spring Boot parent. We add the classifier configuration to that execution; avoid creating a second duplicate execution.

If **not** using `spring-boot-starter-parent`, declare the goal explicitly:

```xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <version>3.3.13</version>
    <executions>
        <execution>
            <goals>
                <goal>repackage</goal>
            </goals>
            <configuration>
                <classifier>exec</classifier>
            </configuration>
        </execution>
    </executions>
</plugin>
```

The plugin version should align with the project's Spring Boot version; for example `3.3.13` illustrates Boot 3.3. If a BOM manages dependencies yet does not manage plugins, declare the plugin version explicitly.

### 4.1. Generated and Published Artifacts

With `groupId=com.example`, `artifactId=shared-module`, and `version=1.0.0`, two files look like:

```text
target/
├── shared-module-1.0.0.jar
└── shared-module-1.0.0-exec.jar
```

- `shared-module-1.0.0.jar` is the main artifact, preserving the standard library layout.
- `shared-module-1.0.0-exec.jar` is the supplementary artifact, Boot-repackaged to run via `java -jar`.

When running `mvn install` or `mvn deploy`, the plugin attaches the executable archive with classifier `exec` alongside the main artifact. Normal consumer dependencies should reference the **classifier-less** artifact:

```xml
<dependency>
    <groupId>com.example</groupId>
    <artifactId>shared-module</artifactId>
    <version>1.0.0</version>
</dependency>
```

Do not add `<classifier>exec</classifier>` to the dependency if consumers need to use the library's classes. Adding classifier `exec` makes consumers fetch the executable archive and hit the `BOOT-INF/classes` layout problem again.

### 4.2. Choosing `classifier`, `skip`, or `attach=false`?

| Configuration | Behavior | Use when |
| --- | --- | --- |
| No classifier, no skip | `repackage` replaces the main artifact with the executable JAR; the original is typically renamed to `.original` in build output. | Module is published solely to run, not used as a library dependency. |
| `classifier=exec` | Keeps the main artifact as a plain JAR and attaches the executable JAR under classifier `exec`. | Both a dependency JAR and a runnable executable are needed. |
| `skip=true` or `spring-boot.repackage.skip=true` | Skips repackaging; Maven keeps the plain JAR. | Module is strictly a library. |
| `attach=false` | Builds the executable archive locally without attaching it for install/deploy; only the original artifact is installed/published. | Want a local runnable build while publishing only the original JAR. |

`classifier` is the clearest choice when needing to publish **both** artifacts. `skip` fits library modules. `attach=false` is not equivalent to a classifier: the executable archive is never attached to the Maven publication.

## 5. If the Project Uses Gradle

The Spring Boot Gradle plugin provides two tasks with distinct purposes:

- `bootJar` builds the executable JAR.
- `jar` builds the plain JAR.

In Spring Boot Gradle plugin 3.3, when `bootJar` is configured, the `jar` task uses the `plain` classifier by convention to avoid name collisions. If you want the classifier-less artifact to be the plain JAR and the executable JAR to have classifier `exec`, configure:

**Groovy DSL – `build.gradle`:**

```groovy
tasks.named("bootJar") {
    archiveClassifier = "exec"
}

tasks.named("jar") {
    archiveClassifier = ""
}
```

**Kotlin DSL – `build.gradle.kts`:**

```kotlin
import org.springframework.boot.gradle.tasks.bundling.BootJar
import org.gradle.jvm.tasks.Jar

tasks.named<BootJar>("bootJar") {
    archiveClassifier.set("exec")
}

tasks.named<Jar>("jar") {
    archiveClassifier.set("")
}
```

Then the plain JAR artifact keeps the primary name and the executable archive receives the classifier. For a library-only module, you can disable the executable task:

```kotlin
tasks.named<BootJar>("bootJar") {
    enabled = false
}
```

If using `maven-publish`, verify the publication publishes the Java component's artifact and the classifier-less JAR. Do not assume that whatever file appears in `build/libs` is automatically the primary artifact of the publication.

Build and inspect:

```bash
./gradlew clean build
```

Check `build/libs` for file names and run `jar tf` to verify layout. If configuring publications, inspect the generated POM/module metadata and confirm the primary artifact is the plain JAR.

## 6. Verifying Artifacts Before Publishing

Do not check file names alone. Inspect **archive contents**, Maven coordinates, and consumer compilation.

### 6.1. Inspect Structure With `jar tf`

For a library JAR:

```bash
jar tf target/payment-api-1.0.0.jar
```

Output should show class paths at the root, for example:

```text
com/example/payment/PaymentClient.class
com/example/payment/PaymentRequest.class
META-INF/MANIFEST.MF
```

If it is a custom starter, also verify the auto-configuration resource resides at the root:

```text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

For an executable JAR:

```bash
jar tf target/checkout-app-1.0.0.jar
```

Output typically contains entries:

```text
BOOT-INF/classes/com/example/checkout/CheckoutApplication.class
BOOT-INF/lib/spring-boot-*.jar
org/springframework/boot/loader/...
META-INF/MANIFEST.MF
```

If shared classes still sit under `BOOT-INF/classes` in the artifact consumers receive, it is still an executable layout; renaming the file does not turn it into a library JAR.

### 6.2. Check the Maven Dependency Tree

In the consumer, run:

```bash
mvn dependency:tree -Dincludes=com.example:payment-api
```

Confirm the consumer resolves the right `groupId`, `artifactId`, version, and does not accidentally pull the executable classifier. The dependency tree shows which Maven artifact resolved; it does not prove classes inside sit in the right layout, so `jar tf` and compilation checks are still required.

### 6.3. Test With a Real Consumer

Consumer POM:

```xml
<dependency>
    <groupId>com.example</groupId>
    <artifactId>payment-api</artifactId>
    <version>1.0.0</version>
</dependency>
```

Create a class using the API:

```java
package consumer;

import com.example.payment.PaymentClient;
import com.example.payment.PaymentRequest;

public class ConsumerExample {

    public PaymentClient createClient() {
        PaymentRequest request = new PaymentRequest("order-42");
        return new PaymentClient(request);
    }
}
```

This is illustrative; `PaymentClient` and `PaymentRequest` must have matching constructors in the real library.

Run:

```bash
mvn clean test
```

If the consumer compiles cleanly and tests resolve required dependencies via the POM, that is stronger proof than merely seeing files in the build directory. In CI, include a consumer integration test verifying artifacts published to a staging repository or local repository after `mvn install`.

### 6.4. Also Inspect POM Metadata

A plain JAR can still be unusable if the published POM is wrong:

- Dependencies required by the public API must be declared with the proper scope.
- Dependencies used only internally at runtime can have another scope depending on design.
- Optional dependencies should be marked `optional` when the library contract expects consumers to choose themselves.
- Do not publish required dependencies under `test` scope.
- Spring Framework/Spring Boot versions must be compatible with consumers and managed consistently.
- Resources, service loader files, auto-configuration metadata, and licenses must be packaged at standard locations.

Plain JARs do not embed dependencies, so **the POM is part of the distribution contract**. Checking only class files while ignoring the POM misses missing transitive dependency bugs.

## 7. Common Configuration Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Using an executable JAR as the main dependency | Consumers cannot find classes in `BOOT-INF/classes` | Publish a plain JAR; keep executable on a separate classifier or dedicated app module. |
| Repackaging a library module without configuring a classifier | Main artifact replaced by executable; original JAR may become `.original` | Skip repackage or use classifier `exec`. |
| Changing `finalName` without changing layout | File remains an executable JAR | Inspect with `jar tf`; fix repackage/packaging task. |
| Only disabling layered JAR | `BOOT-INF` layout remains | Layering and executable layout are separate features. |
| Using `layout=NONE` to mimic a library | Archive still does not become a plain Maven library with standard classpath layout | Use Maven JAR plugin/default jar task for libraries. |
| Adding classifier `exec` to consumer dependency | Consumer keeps receiving the executable archive | Library dependencies must use the classifier-less artifact. |
| Library module inherits repackage execution from parent | Build may repackage unintentionally or fail looking for a main class | Check effective POM; skip in the library module. |
| Both parent and module declare two repackage executions | May repackage twice or process artifacts unexpectedly | Configure the existing execution or declare a single execution. |
| Publishing a right JAR file yet POM lacks dependencies | Consumers lack dependent classes at compile/runtime | Inspect POM and dependency tree. |
| Gradle publication picks `bootJar` by mistake | Consumers receive the executable archive | Configure classifiers and verify the Java component's artifact. |

## 8. Selection Workflow by Scenario

### Scenario A: Pure Java/Spring Library

- Use standard `jar` packaging.
- Do not apply the `spring-boot-maven-plugin` `repackage` goal.
- Publish the JAR alongside its POM.
- If it is a Spring Boot starter, place auto-configuration imports and metadata at standard JAR locations.
- Test from an independent consumer.

### Scenario B: Application Module With Code to Share

- Extract shared APIs/services into a library module.
- Keep application startup implementation in the app module.
- The app depends on the library via normal Maven coordinates.
- Only the app module is repackaged into an executable JAR.

### Scenario C: Cannot Split Modules Yet, Both Files Needed

- Keep the plain JAR as the main artifact.
- Configure the executable JAR with classifier `exec`.
- Publish both artifacts.
- Consumers use the classifier-less dependency; deployment environments use the `-exec.jar` file.

### Scenario D: Publish Library Only, Repackage Plugin Is Inherited

- Set `spring-boot.repackage.skip=true` for the library module.
- Confirm the output JAR is a normal JAR.
- Do not build an executable artifact for that module.

## 9. Pre-Release Checklist

- [ ] Identify whether the artifact is a **library**, **application**, or needs both.
- [ ] Check effective POM or Gradle task graph to see whether `repackage`/`bootJar` runs.
- [ ] For libraries, classes sit at the JAR root; not under `BOOT-INF/classes`.
- [ ] Library dependencies are declared in POM/module metadata; do not rely on nested JARs.
- [ ] If producing both artifacts, the executable has a separate classifier like `exec`.
- [ ] Consumer dependencies do not declare an executable classifier.
- [ ] Verify auto-configuration imports, service loaders, resources, and metadata if the library needs them.
- [ ] Run `mvn clean verify` or `./gradlew clean build`.
- [ ] Inspect the archive with `jar tf`.
- [ ] Install/publish to a test repository and build an independent consumer.
- [ ] Verify version, POM, dependency scopes, and checksums of published artifacts.

**Takeaway:** executable JARs are optimized to **launch applications via the Boot loader**; plain JARs are optimized to **be placed on classpaths and reused as dependencies**. Separate library modules from application modules whenever possible. If both must be published from one Maven module, use classifier `exec` to keep the main artifact as a plain JAR. Always verify via archive layout, POM, and a real consumer build.

### Official Documentation

- Spring Boot 3.3 — Packaging Executable Archives (Maven): https://docs.spring.io/spring-boot/3.3/maven-plugin/packaging.html
- Spring Boot — How-to: Use a Spring Boot Application as a Dependency: https://docs.spring.io/spring-boot/how-to/build.html
- Spring Boot 3.3 — Packaging Executable Archives (Gradle): https://docs.spring.io/spring-boot/3.3/gradle-plugin/packaging.html
- Spring Boot — Executable JAR Format: https://docs.spring.io/spring-boot/specification/executable-jar/index.html
- Apache Maven — Introduction to the Dependency Mechanism: https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html
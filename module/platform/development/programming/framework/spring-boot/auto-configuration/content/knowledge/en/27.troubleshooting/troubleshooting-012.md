# Different Results Across IDE, Tests, and JAR Due to Classpath or Packaging

**Topic:** Spring Boot Auto Configuration  
**Category:** Troubleshooting  
**Goal:** Diagnose cases where an application behaves differently when clicking Run in an IDE, running tests via Maven/Gradle, or launching from a packaged JAR. This lesson focuses on the dependency graph, per-phase classpaths, duplicate-named resources, profile/working-directory configuration, and standard JAR structure vs. Spring Boot executable JARs.

## 1. Why Can the Exact Same Source Produce Different Outcomes?

A Java application does not run from source code alone. The JVM requires a specific set of classes, resources, dependencies, and configuration at each launch.

For example, an auto-configuration might:

- Run fine when clicking Run in IntelliJ.
- Pass all unit tests.
- Yet create no beans when running `java -jar app.jar`.

This does not necessarily mean the Java logic is wrong. The three environments may be using three different sets of inputs:

| Environment | What is typically used |
| --- | --- |
| IDE Run | Module output directories, IDE-imported dependencies, JDK, and dedicated Run Configuration |
| Maven/Gradle test | Main output + test output + test/runtime dependencies + test resources + test properties |
| Production JAR | Packaged classes/resources + dependencies published or nested inside executable JAR + deployment environment/profiles |

Even a small difference can change the outcome:

- The IDE uses a newer dependency version, whereas the JAR was built with an older version.
- Tests have an optional library supplied by `testImplementation` or Maven `test` scope, while production runtime lacks it.
- `src/test/resources/application.yml` contains a property enabling the feature, whereas the production JAR lacks that property.
- The auto-configuration class is inside the JAR, yet the registration file is missing.
- A shaded JAR keeps only the last `AutoConfiguration.imports` file, dropping entries from other dependencies.
- The application runs from a different directory, so Spring Boot loads an external `application.yml` outside the JAR that differs from what the IDE used.

To find the cause, first determine **which classes, resources, dependency versions, and property sources the JVM actually sees** in each environment.

## 2. Distinguishing Classpath from Spring Environment Configuration

Both issues are often loosely called "classpath", yet they are two distinct layers.

**Classpath** determines which classes and resources the JVM can find. For example:

- Is `com.acme.ReportClient` inside a dependency JAR?
- Is `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` found?
- Do two JARs both contain `com/acme/ReportClient.class`?
- Does `application.yml` come from `target/classes`, `target/test-classes`, or an external JAR?

**Spring Environment** determines which configuration values take effect once configuration sources are loaded. For example:

- Does `acme.report.enabled` come from `application.yml`, an environment variable, or the command line?
- Which profile (`test`, `dev`, or `prod`) is active?
- Does a property in `@DynamicPropertySource` override the config file?
- Does `./config/application.yml` outside the JAR override packaged settings?

A class can load properly while properties differ. Conversely, properties can be right while the auto-configuration class is never found.

Diagnose these two questions separately:

1. Does the JVM see the right classes and resources?
2. Does Spring receive the right properties and conditions to create the beans?

## 3. Three Classpaths to Compare

### 3.1. IDE Run Classpath

When running an application from an IDE, the IDE typically uses module output directories and the dependency graph imported from Maven or Gradle.

For instance, IntelliJ may run with:

```text
module/out/production/classes
module/target/classes
module/build/classes/java/main
dependency-a.jar
dependency-b.jar
```

Exact paths depend on the IDE, build tool, and module configuration. A Run Configuration may also select a module classpath different from the module holding the main class.

Check inside the IDE:

- Do the Project SDK and Module SDK match the expected JDK?
- Does the Run Configuration use the right module/classpath?
- What is the working directory?
- Do environment variables and VM options match production?
- Are active profiles the same?
- Did the IDE reload the Maven/Gradle project after changing dependencies?
- Does the IDE use its own compiler/build or delegate build/run to Maven/Gradle?
- Are generated sources and annotation processing enabled properly?

If the IDE holds a stale dependency model, editing `pom.xml` or `build.gradle` may not immediately update the Run Configuration classpath. Reload the project and inspect the build tool's dependency tree.

### 3.2. Test Classpath

Tests typically have more dependencies and resources than the production application.

In Maven, the test classpath typically includes:

- `target/test-classes`
- `target/classes`
- `compile`, `runtime`, and `test` dependency scopes per Maven rules.
- `provided` dependencies are also present on compile/test classpaths, even though they are absent from the production runtime classpath.

With the Gradle Java plugin, key configurations include:

- `compileClasspath`: dependencies for compiling main sources.
- `runtimeClasspath`: dependencies for running main sources.
- `testCompileClasspath`: dependencies for compiling tests.
- `testRuntimeClasspath`: main/test outputs plus dependencies needed to run tests.

A dependency may exist only in tests:

```xml
<dependency>
    <groupId>org.testcontainers</groupId>
    <artifactId>postgresql</artifactId>
    <scope>test</scope>
</dependency>
```

Or:

```kotlin
dependencies {
    testImplementation("org.testcontainers:postgresql:1.20.4")
}
```

If tests pass solely thanks to a test-only dependency, the production application will not automatically have that dependency.

Test resources can also alter outcomes:

```text
src/main/resources/application.yml
src/test/resources/application.yml
```

Tests can load custom properties, profiles, or mock configurations. Besides resource files, these annotations also alter the Environment:

```java
@SpringBootTest(properties = "acme.report.enabled=true")
@ActiveProfiles("test")
@TestPropertySource(properties = "acme.report.mode=test")
```

`@DynamicPropertySource` can also supply values in tests. Thus, when tests pass yet the JAR fails, compare the real property sources and test dependencies against production runtime.

### 3.3. JAR Runtime Classpath

A plain JAR and a Spring Boot executable JAR have different structures.

A standard library JAR typically contains:

```text
acme-report-autoconfigure.jar
├── com/acme/report/ReportProperties.class
├── com/acme/report/autoconfigure/ReportAutoConfiguration.class
└── META-INF/spring/
    └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Library dependencies are normally fetched separately per POM or Gradle Module Metadata. They are not automatically embedded inside the library JAR.

A Spring Boot executable JAR typically has this structure:

```text
application.jar
├── META-INF/MANIFEST.MF
├── org/springframework/boot/loader/...
└── BOOT-INF/
    ├── classes/
    │   ├── com/acme/Application.class
    │   └── application.yml
    └── lib/
        ├── spring-boot-....jar
        ├── acme-report-autoconfigure-....jar
        └── jackson-databind-....jar
```

Application classes sit in `BOOT-INF/classes`; dependencies sit in `BOOT-INF/lib`. Spring Boot Loader knows how to read nested JARs.

Therefore:

- Launch an executable Boot JAR with `java -jar application.jar`.
- Do not treat an executable Boot JAR like a plain JAR and merely place it on `java -cp application.jar`.
- Plain library JARs are not executable applications and do not necessarily contain a main manifest or packaged dependencies.

Spring Boot documentation clearly describes the nested JAR structure and how Loader reads `BOOT-INF/classes` and `BOOT-INF/lib`.

## 4. Maven: Which Scopes Affect Which Classpaths?

Maven dependency scopes dictate which classpaths a dependency joins and how it propagates transitively.

| Scope | Main compile | Main runtime | Test | Consumer |
| --- | --- | --- | --- | --- |
| `compile` | Yes | Yes | Yes | Propagated |
| `provided` | Yes | No | Yes | Not propagated as normal dependency |
| `runtime` | No | Yes | Yes | Propagated at runtime |
| `test` | No | No | Yes | Not propagated |
| `system` | Yes | Yes | Yes | Relies on local path, discouraged |
| `import` | Not a classpath dependency | No | No | Imports dependency management from BOM |

Example:

```xml
<dependencies>
    <dependency>
        <groupId>com.acme</groupId>
        <artifactId>acme-core</artifactId>
        <version>1.0.0</version>
    </dependency>

    <dependency>
        <groupId>org.postgresql</groupId>
        <artifactId>postgresql</artifactId>
        <scope>runtime</scope>
    </dependency>

    <dependency>
        <groupId>org.junit.jupiter</groupId>
        <artifactId>junit-jupiter</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
```

Common causes of divergence:

- Code imports a class while the dependency has only `runtime` scope: main compilation can fail.
- Code needs a class at runtime while the dependency has only `provided` scope: IDE/tests may work, yet production runtime misses the class unless the container supplies it.
- Tests use a library in `test` scope: tests pass, yet the production JAR excludes that dependency.
- Dependency is marked `optional`: the current module still uses it under its scope, yet consumers do not automatically inherit that transitive dependency.
- Artifact is declared only in `dependencyManagement`: Maven manages versions/configurations, yet does not add the artifact to the classpath unless declared in `dependencies`.

Inspect the dependency tree:

```bash
mvn dependency:tree
```

Inspect runtime dependencies only:

```bash
mvn dependency:tree -Dscope=runtime
```

Trace the origin of a specific library:

```bash
mvn dependency:tree -Dverbose -Dincludes=com.fasterxml.jackson.core:jackson-databind
```

Inspect the POM after inheriting parent and profiles:

```bash
mvn help:effective-pom
```

If a dependency has multiple versions, inspect the dependency tree to see which version Maven selected and which branch introduced it. Never rely on an IDE's dependency list to infer the final JAR's versions.

## 5. Gradle: Distinguishing Dependency Declarations from Resolved Classpaths

With the Java plugin or Java Library plugin, dependencies are typically declared using configurations:

```kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-autoconfigure:3.3.13")
    runtimeOnly("org.postgresql:postgresql:42.7.5")
    testImplementation("org.springframework.boot:spring-boot-starter-test:3.3.13")
}
```

Configurations used for declaring dependencies differ from configurations resolved as classpaths:

| Configuration | Role |
| --- | --- |
| `implementation` | Module's internal compile/runtime dependency |
| `api` | Dependency exposed on the Java library's API |
| `compileOnly` | Present only on the module's compile classpath |
| `runtimeOnly` | Present only on the runtime classpath |
| `testImplementation` | Compile/runtime dependencies for tests |
| `testRuntimeOnly` | Dependencies needed only when running tests |
| `compileClasspath` | Actual artifact set used to compile main |
| `runtimeClasspath` | Actual artifact set used to run main |
| `testCompileClasspath` | Actual artifact set used to compile tests |
| `testRuntimeClasspath` | Actual artifact set used to run tests |

Inspect runtime dependencies:

```bash
./gradlew dependencies --configuration runtimeClasspath
```

Inspect test dependencies:

```bash
./gradlew dependencies --configuration testRuntimeClasspath
```

Find why a version was selected:

```bash
./gradlew dependencyInsight \
    --dependency jackson-databind \
    --configuration runtimeClasspath
```

If a dependency appears only in `testRuntimeClasspath`, do not assume it exists in the packaged application. If a dependency is `compileOnly`, code compiles, yet runtime requires another provider.

For Java Libraries, `api` and `implementation` also affect published consumer metadata. When an issue occurs only in an application depending on the library, inspect `runtimeElements`/`apiElements` or the published POM/Gradle Module Metadata as well.

## 6. Resources Can Differ Even When the Classpath Looks Right

The classpath holds more than `.class` files; it also holds resources such as:

- `application.yml` and `application.properties`.
- `META-INF/spring.factories`.
- `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`.
- `META-INF/spring-configuration-metadata.json`.
- `META-INF/services/...`.
- `logback-spring.xml`.
- Schema files, templates, SQL migrations, or message bundles.

Two JARs can contain resources at the exact same path. `ClassLoader.getResource` returns a single resource, whereas `getResources` lists every matching duplicate resource.

Example:

```java
Enumeration<URL> urls = Thread.currentThread()
        .getContextClassLoader()
        .getResources(
                "META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports"
        );

while (urls.hasMoreElements()) {
    System.out.println(urls.nextElement());
}
```

If multiple JARs supply imports files, verify whether the packaging tool preserves and merges every entry.

### 6.1. Auto-Configuration Class Is in the JAR, Yet Not Loaded

For Spring Boot 2.7 and newer, check:

```text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Each line is a fully qualified class name. For Boot 2.6 and older, check the `EnableAutoConfiguration` key inside `META-INF/spring.factories`.

Boot 2.7 supports both mechanisms; Boot 3 no longer uses the legacy `EnableAutoConfiguration` key to register auto-configurations.

A JAR containing the class:

```text
com/acme/report/autoconfigure/ReportAutoConfiguration.class
```

yet lacking the corresponding imports file is still not enough for Boot to auto-discover that class.

When using Maven Shade or Gradle Shadow, multiple dependencies may contain imports files. The plugin must append/merge the resource to preserve all entries. With Maven Shade, for example:

```xml
<transformer implementation="org.apache.maven.plugins.shade.resource.AppendingTransformer">
    <resource>META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports</resource>
</transformer>
```

With Gradle Shadow:

```groovy
tasks.withType(com.github.jengelman.gradle.plugins.shadow.tasks.ShadowJar).configureEach {
    append("META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports")
}
```

If `spring.factories` is still used, properties files must also be merged cleanly. Inspect the final artifact after shading; inspecting individual dependency JARs prior to shading is insufficient.

### 6.2. IDE Does Not Autocomplete, Yet Runtime Still Works

IDEs may require configuration metadata to suggest properties. The file normally lives at:

```text
META-INF/spring-configuration-metadata.json
```

Metadata is generated by `spring-boot-configuration-processor` or authored manually. If the file is not packaged, the IDE may fail to autocomplete keys even though `@ConfigurationProperties` and Binder still work at runtime.

This is a tooling experience issue; inspect metadata in the JAR and IDE indexing. Never conclude runtime auto-configuration is broken merely because the IDE flags an unresolved property.

## 7. Distinguishing Plain JAR, `jar`, and `bootJar`

In Spring Boot projects, two artifacts are frequently confused:

- `jar`: a standard Java JAR holding the module's classes/resources.
- `bootJar`: an executable Spring Boot application JAR containing Spring Boot Loader and nested dependencies in `BOOT-INF/lib`.

With Gradle, the `bootRun` task runs the application from the build's classpath; it is not a final test of executable JAR packaging. Likewise, running from an IDE normally uses output directories and resolved dependencies rather than reading nested JARs the way `java -jar` does.

With Maven, `spring-boot-maven-plugin` provides the `repackage` goal to create an executable archive. If the plugin does not run or is skipped, the artifact may remain a plain JAR even though sources and tests pass.

Maven plugin example:

```xml
<build>
    <plugins>
        <plugin>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-maven-plugin</artifactId>
            <executions>
                <execution>
                    <goals>
                        <goal>repackage</goal>
                    </goals>
                </execution>
            </executions>
        </plugin>
    </plugins>
</build>
```

With the Gradle Spring Boot plugin, build the executable artifact using:

```bash
./gradlew clean bootJar
```

If the module is an auto-configuration/starter library, normally publish a library JAR containing classes, registration resources, and metadata; do not turn a library module into an executable Boot JAR just to bundle dependencies.

## 8. Inspecting the Contents of the Artifact Actually Executed

After building, inspect the exact JAR file used by the deployment environment.

With Maven:

```bash
mvn clean package
jar tf target/acme-report-app-1.0.0.jar
```

Filter key entries on Linux/macOS:

```bash
jar tf target/acme-report-app-1.0.0.jar |
    grep -E 'BOOT-INF/(classes|lib)/|AutoConfiguration.imports|spring.factories|spring-configuration-metadata.json'
```

On Windows PowerShell:

```powershell
jar tf target/acme-report-app-1.0.0.jar |
    Select-String 'BOOT-INF/(classes|lib)/|AutoConfiguration.imports|spring.factories|spring-configuration-metadata.json'
```

Read the manifest:

```bash
unzip -p target/acme-report-app-1.0.0.jar META-INF/MANIFEST.MF
```

For an executable Boot JAR, expect `BOOT-INF/classes`, `BOOT-INF/lib`, and a manifest with the proper launcher/start class attributes.

With Gradle:

```bash
./gradlew clean bootJar
jar tf build/libs/acme-report-app-1.0.0.jar
```

To read a resource inside the JAR:

```bash
unzip -p target/acme-report-app-1.0.0.jar \
    BOOT-INF/classes/application.yml
```

That path applies only when the resource sits on the application's root classpath and is packaged into `BOOT-INF/classes`. If the resource comes from a nested dependency JAR, locate that dependency inside `BOOT-INF/lib` and inspect that JAR separately after extracting it.

**Always execute the exact artifact you inspected:**

```bash
java -jar target/acme-report-app-1.0.0.jar
```

If production uses a different artifact path, verify the deployed checksum/version or build name. Running the newly built local file does not prove the server is running that same file.

## 9. Using the JVM to Trace Class and Resource Origins

When you suspect a class is loaded from an old JAR or duplicate dependency, print the class origin.

Java 17 example:

```java
package demo;

import java.io.IOException;
import java.net.URL;
import java.security.CodeSource;
import java.util.Enumeration;

public final class ClasspathProbe {

    private ClasspathProbe() {
    }

    public static void main(String[] args) throws IOException {
        describe(ClasspathProbe.class);

        for (String resourceName : args) {
            listResources(resourceName);
        }
    }

    private static void describe(Class<?> type) {
        CodeSource source = type.getProtectionDomain().getCodeSource();
        URL classResource = type.getResource(type.getSimpleName() + ".class");

        System.out.println("class=" + type.getName());
        System.out.println("classLoader=" + type.getClassLoader());
        System.out.println("classResource=" + classResource);
        System.out.println("codeSource="
                + (source == null ? "<unavailable>" : source.getLocation()));
    }

    private static void listResources(String resourceName)
            throws IOException {

        ClassLoader loader =
                Thread.currentThread().getContextClassLoader();

        if (loader == null) {
            loader = ClasspathProbe.class.getClassLoader();
        }

        System.out.println("resource=" + resourceName);

        Enumeration<URL> resources = loader.getResources(resourceName);
        int count = 0;

        while (resources.hasMoreElements()) {
            count++;
            System.out.println("  [" + count + "] " + resources.nextElement());
        }

        if (count == 0) {
            System.out.println("  <not found>");
        }
    }
}
```

Compile and run:

```bash
javac -d out src/main/java/demo/ClasspathProbe.java
java -cp out demo.ClasspathProbe \
    META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports \
    application.yml
```

In a real application, call `describe(ReportService.class)` to see where the class is loaded from. Call `listResources(...)` to enumerate all copies of a resource with the same name.

A few notes:

- `CodeSource` may be `null` for classes from the bootstrap/platform classloader or when the environment omits source info.
- Paths shown inside an executable Boot JAR may be nested JAR URLs rather than plain JAR paths.
- When multiple resources share the same name, inspect the order and contents of every URL.
- The probe reveals class/resource origins; it does not explain which property wins inside the Spring Environment.

On Java 17, you can enable class-loading logs:

```bash
java -Xlog:class+load=info -jar target/acme-report-app-1.0.0.jar
```

Search the log for the class name to see where the JVM loaded it from. Logs can be very long; filter by the suspected package or class.

## 10. Checking JDKs and Bytecode

The IDE may use one JDK, Maven/Gradle may run under another JDK, and production may use a different JRE/JDK.

Compare:

```bash
java -version
javac -version
mvn -version
./gradlew --version
```

Cross-check:

- The JDK used by the IDE Project SDK.
- The JDK running the Maven/Gradle daemon.
- `maven.compiler.release` or Gradle Java toolchain.
- The container/server runtime JDK.
- Bytecode target versions of internal libraries and dependencies.

If code is compiled with a newer JDK yet deployed on an older runtime, the error may be:

```text
UnsupportedClassVersionError
```

If the class is present yet the API is incompatible, you may encounter:

```text
NoSuchMethodError
NoClassDefFoundError
AbstractMethodError
```

These errors typically indicate binary/dependency mismatches or differing classpaths. Inspect actual class and dependency versions before changing source code.

In Maven, configure `maven.compiler.release` or `<release>` to specify the target API/bytecode. In Gradle, use Java toolchains so compiler and test runtimes have explicit configuration.

## 11. External Configuration Outside the JAR and Working Directory

A very common cause is running the exact same JAR from two different working directories.

Spring Boot searches for `application.properties`/`application.yaml` in default locations, including classpath root, classpath `/config`, the current directory, and external `config/` directories. External files can override packaged files.

Example:

```text
deploy/
├── application.jar
└── config/
    └── application-prod.yml
```

Running from the deploy directory may load `config/application-prod.yml`. If the IDE runs from the project directory with a different configuration file, results can differ despite identical source code.

Check:

```java
System.out.println("user.dir=" + System.getProperty("user.dir"));
```

Compare these values:

- Working directory.
- `SPRING_PROFILES_ACTIVE`.
- JVM system properties (`-D...`).
- Environment variables.
- Command-line arguments (`--key=value`).
- `spring.config.location`, `spring.config.additional-location`.
- `spring.config.import`.

Spring Boot's property source order lets environment variables, system properties, command-line arguments, and test-specific properties override file values. Thus, opening `application.yml` alone is not enough to determine the final Environment values.

To reproduce accurately:

```bash
java -jar target/acme-report-app-1.0.0.jar \
    --spring.profiles.active=prod \
    --acme.report.enabled=true
```

Use the exact profiles and arguments used by the real environment. If you need to add config files outside the JAR, pass `spring.config.additional-location`; when using `spring.config.location`, remember it replaces default locations.

## 12. Tests Can Accidentally Mask Production Bugs

### 12.1. Test Dependencies Keep Optional Libraries Present

Suppose an auto-configuration has:

```java
@ConditionalOnClass(name = "com.vendor.client.VendorClient")
```

If the test starter pulls `com.vendor:vendor-client` onto the test classpath, the condition always matches. However, a production consumer not declaring the vendor client may lack the corresponding bean.

Use `FilteredClassLoader` to simulate a classpath missing the dependency:

```java
this.contextRunner
        .withClassLoader(new FilteredClassLoader("com.vendor.client"))
        .run(context -> {
            assertThat(context).hasNotFailed();
            assertThat(context).doesNotHaveBean("vendorService");
        });
```

This test checks both the condition and that the application suffers no linkage errors when the optional class is absent.

### 12.2. Test Properties Differ from Production Properties

A test may enable a feature via:

```java
@SpringBootTest(properties = "acme.report.enabled=true")
```

while production lacks this property. If the condition defaults to `matchIfMissing = false`, auto-configuration will not create the bean in production.

Test all three states per the contract:

- Property missing.
- Property `false`.
- Property `true`.

For tests using profiles, confirm `@ActiveProfiles` and profile-specific files match expectations.

### 12.3. Test Resources Shadow Production Resources

Check whether `src/test/resources` contains files with the same names as `src/main/resources`. Those resources can cause tests to load different configuration.

To verify the registration file, write a test:

```java
@Test
void autoConfigurationImportsResourceIsVisible() throws IOException {
    String resource =
            "META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports";

    Enumeration<URL> urls = getClass()
            .getClassLoader()
            .getResources(resource);

    assertThat(Collections.list(urls)).isNotEmpty();
}
```

This test confirms the resource exists on the test classpath. It does not yet prove the final artifact after Shade/Shadow retains the complete contents. Combine it with inspecting the final JAR and a consumer smoke test.

## 13. Diagnosing with the Condition Evaluation Report

If classes and resources are present yet the bean still does not appear, inspect conditions.

Run:

```bash
java -jar target/acme-report-app-1.0.0.jar --debug
```

Spring Boot prints the Condition Evaluation Report, helping determine:

- Which auto-configurations matched or did not match.
- Whether `@ConditionalOnClass` found the class.
- Which value `@ConditionalOnProperty` read.
- Whether `@ConditionalOnMissingBean` saw an application bean.
- Which condition caused a bean method or configuration class to be skipped.

If the application uses Actuator and exposes the endpoint, `/actuator/conditions` provides the report in JSON format. Secure the endpoint per your application's operational policy.

In tests, use `ConditionEvaluationReportLoggingListener` with `ApplicationContextRunner` to log match/no-match reasons. Use the report to locate the cause, then write assertions verifying actual beans.

Do not assume auto-configuration registration is broken solely because a bean does not appear. The class may have been imported while a condition did not match; the two situations require different fixes.

## 14. Workflow for Comparing IDE, Tests, and JAR

When reproducing a bug, follow the exact same sequence across all three environments:

### Step 1 — Record the Runtime

Collect:

```bash
java -version
mvn -version
./gradlew --version
```

Record the JDK, build tool, active profiles, working directory, JVM arguments, and environment variables.

### Step 2 — Verify the Dependency Graph

Maven:

```bash
mvn dependency:tree -Dscope=runtime
mvn dependency:tree -Dscope=test
```

Gradle:

```bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencies --configuration testRuntimeClasspath
```

Compare resolved versions, especially Spring Boot, Spring Framework, and optional libraries.

### Step 3 — Verify Class and Resource Origins

Use `ClasspathProbe`, `ClassLoader.getResources(...)`, or Java class-loading logs to see where each class/resource loads from.

Check whether registration resources, metadata, and configs collide across multiple JARs.

### Step 4 — Clean Build the Artifact

Maven:

```bash
mvn clean verify
```

Gradle:

```bash
./gradlew clean test bootJar
```

Do not reuse stale outputs from a prior build. For snapshot dependencies or suspected cache issues, refresh only once you confirm an artifact needs re-fetching:

```bash
mvn -U clean verify
./gradlew --refresh-dependencies clean test bootJar
```

### Step 5 — Inspect JAR Contents

```bash
jar tf target/acme-report-app-1.0.0.jar
```

Verify classes, registration files, metadata, and nested dependencies match expectations. When using a shaded JAR, inspect the post-shade artifact.

### Step 6 — Run That Exact Artifact

```bash
java -jar target/acme-report-app-1.0.0.jar --debug
```

Use the same profiles, environment variables, command-line properties, and external configs as the real environment.

### Step 7 — Compare Behavior

Record:

- Whether the bean appears and which implementation is injected.
- Which match/no-match reasons the condition report shows.
- The final property values and their origins.
- Actual class/resource URLs.
- Selected dependency versions.
- Class-loading logs if linkage errors occur.

Only after all inputs match while outcomes still differ should you investigate lifecycle, classloader, or framework-version behavioral differences.

## 15. Symptom and Verification Matrix

| Symptom | Common cause | Verification step |
| --- | --- | --- |
| IDE runs, JAR throws `ClassNotFoundException` | Dependency exists only on IDE/module classpath, absent from runtime artifact | Runtime dependency tree and `BOOT-INF/lib` |
| Tests pass, production lacks bean | Test dependencies/properties/profiles supply extra required conditions | Compare `testRuntimeClasspath` with `runtimeClasspath`; inspect Condition Report |
| JAR contains class, yet auto-configuration does not run | Missing or wrong registration resource | `jar tf`, read `AutoConfiguration.imports`/`spring.factories` |
| Only shaded JAR misses bean | Registration resource was overwritten or unmerged | Compare resources before/after Shade/Shadow |
| IDE lacks property autocomplete, runtime still binds | Missing configuration metadata or IDE has not indexed new dependency | Check `spring-configuration-metadata.json`, reload IDE |
| IDE and JAR read different values | Working directory, profile, or external config differs | `user.dir`, active profiles, property sources |
| `bootRun` passes, yet `java -jar` fails | Difference between resolved classpath and executable archive packaging | Build `bootJar`, check manifest and nested libs, run exact JAR |
| `NoSuchMethodError` only in production | Dependency resolved to different version or old class loaded | Dependency insight/tree and class origin |
| `UnsupportedClassVersionError` | Runtime JDK older than compiled bytecode | `java -version`, compiler release/toolchain |
| Tests see two beans while JAR has one | Test classpath adds extra config/implementation | Compare resources/classpaths and condition report |
| Resource appears multiple times | Multiple JARs share the same resource path | `ClassLoader.getResources(...)` |
| Local JAR works, yet server still fails | Server runs stale artifact or different external config | Verify version/checksum, startup path, and environment |

## 16. Common Mistakes

**Mistake 1 — Checking only `compileClasspath`.**  
Successful compilation does not prove a dependency exists at runtime. Inspect the runtime classpath and packaged artifact.

**Mistake 2 — Assuming passing tests mean the production classpath is right.**  
Tests include extra dependencies, resources, and properties. Compare test runtime against production runtime.

**Mistake 3 — Assuming dependencies in the POM are embedded in a library JAR.**  
The POM describes the dependency graph; plain library JARs do not embed dependencies. Executable Boot JARs have their own packaging structure.

**Mistake 4 — Using `java -cp app.jar` to launch an executable Boot JAR.**  
Nested JARs require Spring Boot Loader. Use `java -jar app.jar`.

**Mistake 5 — Checking only `.class` files.**  
Auto-configuration needs registration resources; IDEs may need metadata; ServiceLoader needs service files. Verify the full resource contract.

**Mistake 6 — Inspecting only the pre-shade JAR.**  
Shade/Shadow can drop or overwrite resources. Inspect the final artifact.

**Mistake 7 — Blaming IDE caches immediately when results diverge.**  
First verify module classpath, JDK, working directory, profiles, and the IDE's imported dependency model.

**Mistake 8 — Catching linkage errors and silently ignoring them.**  
`NoClassDefFoundError` or `NoSuchMethodError` usually signals a dependency mismatch. Preserve the root cause and fix the graph/classpath.

**Mistake 9 — Comparing only `application.yml` files.**  
Final values are also governed by profiles, environment variables, system properties, command-line args, test annotations, and external files outside the JAR.

**Mistake 10 — Using `bootRun` instead of testing the executable JAR.**  
`bootRun` runs off the build's classpath. Build `bootJar`/repackage and execute `java -jar`.

**Mistake 11 — Skipping `clean` between builds.**  
Stale classes/resources can linger in output directories. Run `clean` when investigating packaging bugs or dependency changes.

**Mistake 12 — Changing conditions to mask packaging bugs.**  
If a class/resource is not loaded, tweaking `@ConditionalOnProperty` will not fix registration or classpath. Identify the right layer before editing.

## 17. Pre-Release Checklist

- [ ] IDE, Maven/Gradle, and production use JDKs compatible with target bytecode.
- [ ] Run Configuration selects the right module and working directory.
- [ ] Direct dependencies are declared with proper scopes/configurations.
- [ ] Runtime classpath includes all required dependencies.
- [ ] Test-only dependencies are not mistaken for production dependencies.
- [ ] Test resources and test properties do not mask production failures.
- [ ] Optional dependencies are tested both present and absent.
- [ ] Auto-configuration registration resource exists in the right module/JAR.
- [ ] Configuration metadata exists in the artifact if IDE completion is needed.
- [ ] Duplicate-named resources are checked and properly merged when shading.
- [ ] Plain JARs and executable Boot JARs are clearly distinguished.
- [ ] `jar tf` confirms the final artifact's contents.
- [ ] Artifact was smoke-tested via `java -jar`.
- [ ] Profiles, external config, environment variables, and command-line args are documented.
- [ ] Condition Evaluation Report was inspected whenever bean match/no-match differed from expectations.
- [ ] CI archives dependency trees and test reports for key builds.

## 18. Self-Check Questions

**Question 1.** Why can an application run in the IDE yet report missing classes in the JAR?  
**Answer:** The IDE may include dependencies on the module classpath while the runtime artifact lacks them. Inspect the runtime dependency graph and JAR contents.

**Question 2.** Why can tests pass while an auto-configured bean does not appear in production?  
**Answer:** Tests may rely on test-only dependencies, test resources, profiles, or test properties. Compare the test runtime classpath and property sources against production.

**Question 3.** What does `mvn dependency:tree -Dscope=runtime` verify?  
**Answer:** Dependencies Maven places in the runtime graph and the resolved versions for the application.

**Question 4.** Which Gradle configuration describes the dependency graph for running the main application?  
**Answer:** `runtimeClasspath`; tests use `testRuntimeClasspath`.

**Question 5.** Why does an executable Boot JAR require `java -jar`?  
**Answer:** Dependencies reside in nested `BOOT-INF/lib`; Spring Boot Loader reads the nested JAR structure. Standard `java -cp` does not unpack nested JARs automatically.

**Question 6.** The class is inside the JAR, yet auto-configuration does not load. What should you check?  
**Answer:** The registration resource for your Boot version, the imports/factories path, and whether the resource was lost during shading.

**Question 7.** Why is `getResource(...)` insufficient when suspecting duplicate resources?  
**Answer:** It returns only a single matching URL. `getResources(...)` enumerates all resources at that path to expose duplicates.

**Question 8.** What does it suggest when `bootRun` passes yet `java -jar` fails?  
**Answer:** The build classpath and executable archive differ; inspect packaging, nested dependencies, manifest, and resources inside the final JAR.

**Question 9.** Why can running the same JAR from two directories read different settings?  
**Answer:** Spring Boot searches external config from the working directory and `config/` locations; files outside the JAR can override packaged files.

**Question 10.** What does `NoSuchMethodError` usually suggest?  
**Answer:** The JVM loaded a class version lacking the method the code calls; inspect dependency mediation, class origins, and runtime versions.

## 19. Key Principles to Remember

- IDE Run, test runtime, and executable JARs can use different classpaths.
- Classpath determines which classes/resources are found; Spring Environment determines final configuration values.
- Maven scopes and Gradle configurations alter the dependency graph across compile, runtime, and test.
- Test resources, test dependencies, profiles, and test properties can mask production bugs.
- Library JARs normally do not embed dependencies; executable Boot JARs use `BOOT-INF/classes` and `BOOT-INF/lib`.
- Launch executable Boot JARs with `java -jar`, then inspect that exact artifact.
- Inspect registration resources, metadata, and service files alongside `.class` files.
- Use `ClassLoader.getResources`, class origin, and `-Xlog:class+load=info` to find actual origins.
- Compare working directory, active profiles, environment variables, and external configs.
- Read the dependency tree and Condition Evaluation Report before editing condition logic.

### Official References

- [Apache Maven — Introduction to the Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html)
- [Gradle — Creating Dependency Configurations](https://docs.gradle.org/current/userguide/declaring_configurations.html)
- [Gradle — Dependency Configurations](https://docs.gradle.org/current/userguide/dependency_configurations.html)
- [Spring Boot 3.3 — Nested JARs and Executable Archive Structure](https://docs.spring.io/spring-boot/3.3/specification/executable-jar/nested-jars.html)
- [Spring Boot 3.3 — Externalized Configuration](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html)
- [Spring Boot 3.3 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html)
- [Spring Boot 3.3 — Creating and Testing Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html)

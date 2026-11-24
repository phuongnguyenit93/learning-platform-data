# Publishing Sources, Javadoc, and Appropriate Dependency Metadata

A well-published Java library requires more than a single JAR file containing bytecode. Users need a **sources JAR** so their IDEs can open source code while debugging, a **Javadoc JAR** to look up APIs directly inside the IDE, and accurate **dependency metadata** so Maven/Gradle automatically selects the right transitive libraries, versions, and classpaths. Uploading only a JAR without a POM or declaring wrong dependencies can let consumers download the artifact yet fail builds, hit missing classes at runtime, or be forced to manually declare libraries that the publication ought to describe.

This lesson walks through publishing a Java library with **Maven and Gradle**, generating and attaching **-sources.jar** and **-javadoc.jar**, describing dependencies in **Maven POM** and **Gradle Module Metadata (.module)**, configuring repositories/credentials, publishing internally, and preparing for Maven Central. Examples use **Java 17**, the **greeting-core** library, and the Spring Boot ecosystem as context. The code built here is a standalone Java library to demonstrate publication; an executable Spring Boot application must be packaged under its own rules covered in section 22.

## 1. What Makes Up a Complete Publication?

Suppose the library coordinates are:

```text
com.example.training:greeting-core:1.0.0
```

A Maven-compatible repository typically stores these components:

```text
com/example/training/greeting-core/1.0.0/
├── greeting-core-1.0.0.jar
├── greeting-core-1.0.0.pom
├── greeting-core-1.0.0-sources.jar
├── greeting-core-1.0.0-javadoc.jar
├── greeting-core-1.0.0.jar.sha256
├── greeting-core-1.0.0.pom.sha256
├── greeting-core-1.0.0-sources.jar.sha256
└── greeting-core-1.0.0-javadoc.jar.sha256
```

If the publication was produced by Gradle, the repository may also contain:

```text
greeting-core-1.0.0.module
```

For Maven Central, releases also require checksums and GPG/PGP signatures per Portal requirements; signature files typically carry the .asc extension. An internal repository may enforce different policies, though storing checksums, metadata, and clear build provenance is still recommended.

| Component | What does it contain? | How users benefit |
| --- | --- | --- |
| **Main JAR** | Compiled classes and runtime resources | Compiler/JVM loads the library |
| **POM** | GAV, dependencies, scopes, license, SCM, and Maven metadata | Maven and Gradle when reading Maven metadata |
| **Sources JAR** | Java source code/resources matching the main artifact | IDE opens sources, debugger, and code navigation |
| **Javadoc JAR** | HTML API documentation generated from Javadoc comments | IDE displays API descriptions, users look up docs |
| **Gradle Module Metadata** | Variants, attributes, capabilities, dependencies, and artifacts | Gradle selects appropriate compile/runtime variants |
| **Checksums** | Hash values of artifacts/metadata | Verify downloaded files match exact bytes |
| **PGP signature** | Digital signature bound to published files | Verify publisher/key and integrity |

**The three groups serve distinct purposes:** the main JAR is executable/compilable content, sources/Javadoc are accompanying documentation, and POM/.module are metadata so build tools understand the module. Sources and Javadoc do not replace the POM and are not runtime dependencies.

## 2. Distinguishing Classifiers sources, javadoc, and Dependencies

Maven artifacts are identified by coordinates:

```text
groupId:artifactId:version[:classifier]@extension
```

Examples:

| Artifact | Illustrative coordinate | Meaning |
| --- | --- | --- |
| Main library | com.example.training:greeting-core:1.0.0 | Default artifact, usually bytecode JAR |
| Sources | com.example.training:greeting-core:jar:sources:1.0.0 | JAR containing source code |
| Javadoc | com.example.training:greeting-core:jar:javadoc:1.0.0 | JAR containing HTML Javadoc |

In repository paths, the classifier is appended to the filename after the version:

```text
greeting-core-1.0.0.jar
greeting-core-1.0.0-sources.jar
greeting-core-1.0.0-javadoc.jar
```

**Classifiers do not create an independent module/version.** All three files belong to com.example.training:greeting-core:1.0.0. When a consumer declares a normal dependency, the build tool fetches the main artifact and dependency metadata. IDEs can look up sources/javadoc classifiers by convention or when the user requests downloading them separately.

Never declare sources/Javadoc as runtime dependencies:

```xml
<!-- Do not do this in consumer application dependencies. -->
<dependency>
    <groupId>com.example.training</groupId>
    <artifactId>greeting-core</artifactId>
    <version>1.0.0</version>
    <classifier>sources</classifier>
</dependency>
```

The snippet above instructs Maven to place the source archive on the dependency classpath as a declared artifact; that is not how IDE source attachment should be configured. Use your IDE's download sources/Javadoc feature or suitable plugins/tooling.

## 3. Sources JAR: Must Match the Exact Binary Release

A Sources JAR packages the source code of the **main source set** corresponding to the published binary JAR. Users need version-accurate sources to:
- Read logic when the IDE navigates into library classes.
- Set breakpoints and step through code in the debugger.
- Compare implementations against the API contract.
- Investigate bugs without guessing code from bytecode.

Principles:
1. Sources must come from the **same commit, same GAV, and same release** as the main JAR.
2. Never take sources from a newer branch and attach them to an older artifact version.
3. Never include secrets, environment files, keys, private configs, sensitive generated outputs, or unrelated build files in the archive.
4. If the library uses generated sources, confirm those sources are added to the source set before creating the archive.
5. Do not confuse main sources with test sources. Test sources should only be published under a separate classifier when consumers genuinely need them.
6. If module-info.java, generated annotations, or multi-release source layouts exist, inspect archive contents to ensure users receive the right layout.

A Sources JAR contains no bytecode for the JVM to execute; it is an artifact for developer tooling. An existing sources JAR containing empty folders or mismatched commit sources is still a poor-quality publication.

## 4. Javadoc JAR: Describing the Public API Contract

A Javadoc JAR is an archive containing HTML generated by the Javadoc tool from source code comments/tags. It should help users understand:
- What the class/interface is for.
- What preconditions constructors require.
- What parameters mean and their constraints.
- What semantics return values have.
- What exceptions may be thrown.
- Thread-safety, lifecycle, nullability, or side effects when relevant.
- Since which version an API appeared or changed (@since, @deprecated, @see).

Example of useful comments:

```java
/**
 * Creates a greeting service backed by the supplied logger.
 *
 * @param logger logger used to record greeting operations
 * @throws NullPointerException if {@code logger} is {@code null}
 * @since 1.0
 */
public GreetingService(Logger logger) {
    this.logger = Objects.requireNonNull(logger, "logger");
}

/**
 * Creates a greeting for a non-blank name.
 *
 * @param name person's display name
 * @return greeting text ending with an exclamation mark
 * @throws NullPointerException if {@code name} is {@code null}
 * @throws IllegalArgumentException if {@code name} is blank
 * @since 1.0
 */
public String greet(String name) {
    // implementation
}
```

**Javadoc describes the contract, not just a repetition of the method name.** A comment like "Returns a string" does not help consumers understand formatting, normalization, exceptions, or side effects. For public APIs, prioritize writing docs for packages/classes/public constructors/public methods and use tags accurately.

A Javadoc archive is not a separately published documentation website. IDEs can read HTML inside the JAR; if you want to host a documentation site, that is a separate deliverable usually deployed via a website/site pipeline.

## 5. Dependency Metadata: Why Uploading Only a JAR Is Not Enough

Suppose greeting-core uses SLF4J and Jackson. A consumer declares only:

```xml
<dependency>
    <groupId>com.example.training</groupId>
    <artifactId>greeting-core</artifactId>
    <version>1.0.0</version>
</dependency>
```

The build tool needs to know which modules this library depends on, at which versions, and on which classpaths. If metadata is missing or wrong:
- Compilation can fail because a public method uses a type missing from the compile classpath.
- Runtime can fail with NoClassDefFoundError.
- The dependency tree can end up with two conflicting versions.
- Consumers are forced to manually declare internal dependencies.
- IDEs may misunderstand variants or Java compatibility.

**Accurate metadata is part of the public contract.** When publishing, do not upload only the JAR file; accurately describe the dependency graph and API/runtime components the library requires.

## 6. How Maven POM and Gradle Module Metadata Differ

| Format | Primary tool | Description |
| --- | --- | --- |
| **Maven POM (.pom)** | Maven; Gradle can also read it | GAV, dependencies, scopes, optional/exclusions, dependency management, and project info |
| **Gradle Module Metadata (.module)** | Gradle | Models modules by variants, attributes, capabilities, artifacts, and per-variant dependencies |
| **Repository maven-metadata.xml** | Maven repository clients | Repository/module-level metadata listing versions or snapshot timestamps/build numbers |

Do not confuse the three files:
- A POM is the descriptor for **a single project version** and its dependency graph.
- Gradle .module is a richer descriptor for components/variants.
- maven-metadata.xml is repository-managed metadata supporting version listing/snapshot resolution; it does not replace a POM and is not a project's direct dependency declaration file.

Gradle Module Metadata supports features that a POM cannot express completely, such as rich version constraints, dependency constraints, capabilities, and variant-aware resolution. When Gradle publishes to a Maven-compatible repository, .module is stored **alongside** the POM; Gradle consumers can read .module, while Maven consumers continue using the POM. Never delete the POM just because the project is built with Gradle.

## 7. Dependency Scopes Determine What Metadata Consumers Receive

### 7.1. Maven Scopes

| Scope | On library's compile classpath? | Consumer receives dependency transitively? | Common purpose |
| --- | --- | --- | --- |
| compile | Yes | Yes | Dependency needed to compile and usually needed at runtime |
| provided | Yes, and test | Not via normal transitivity | Provided by container/JDK/runtime environment |
| runtime | Not on main compile; on runtime/test | Yes on runtime classpath | Dependency needed only at runtime |
| test | Test only | No | JUnit, Mockito, test utilities |
| system | Yes via local path | Not via normal repository management | Avoid using for library publications |

If scope is omitted, Maven defaults to compile. Test dependencies should never appear as consumer runtime dependencies. provided is typically used when the runtime environment supplies the dependency; if a consumer lacks that environment, the library may fail at runtime.

Maven does not have api/implementation configurations like the Gradle Java Library Plugin. Compile dependencies are typically listed in the POM and exposed transitively to consumers. If implementation dependencies need to be hidden, design modules/packaging and scopes carefully; do not mechanically switch compile to runtime when library sources still need that dependency to compile.

### 7.2. Gradle api and implementation

When using java-library:
- api: dependency exposed on the consumer's compile classpath because the library's public API depends on its types.
- implementation: dependency needed for internal build/runtime implementation, hidden from the consumer's compile classpath.
- compileOnly: needed at compile time but not supplied as a default runtime dependency; use only when consumer/runtime provides it.
- runtimeOnly: needed at runtime, not at compile time.
- testImplementation: for tests only.

**Important rule:** if a library's public method signature uses a class from a dependency, consumers need that dependency at compile time. In that case Gradle typically requires api. If the dependency is used solely in private implementation, choose implementation.

Never pick implementation merely to make the POM shorter if the public API still exposes that library's types; consumers can fail to compile even though the library builds fine by itself.

## 8. Sample Java 17 Project: greeting-core Library

Uses the same Java sources for both Maven and Gradle. Structure:

```text
greeting-core/
├── pom.xml                         # Maven option
├── settings.gradle                 # Gradle option
├── build.gradle                    # Gradle option
└── src/
    ├── main/java/com/example/greeting/
    │   └── GreetingService.java
    └── test/java/com/example/greeting/
        └── GreetingServiceTest.java
```

groupId and Java package names are not forced to match, though consistent naming conventions make modules easier to find and manage.

### 8.1. Main Library Class

Create src/main/java/com/example/greeting/GreetingService.java:

```java
package com.example.greeting;

import java.util.Map;
import java.util.Objects;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.slf4j.Logger;

/**
 * Creates greeting messages and records each successful operation.
 *
 * <p>The logger is supplied by the consuming application so that the library
 * does not select a logging implementation on the consumer's behalf.
 *
 * @since 1.0
 */
public final class GreetingService {

    private final Logger logger;
    private final ObjectMapper objectMapper = new ObjectMapper();

    /**
     * Creates a service backed by the supplied logger.
     *
     * @param logger logger used to record greeting operations
     * @throws NullPointerException if {@code logger} is {@code null}
     * @since 1.0
     */
    public GreetingService(Logger logger) {
        this.logger = Objects.requireNonNull(logger, "logger");
    }

    /**
     * Creates a greeting for a non-blank name.
     *
     * @param name person's display name
     * @return greeting text ending with an exclamation mark
     * @throws NullPointerException if {@code name} is {@code null}
     * @throws IllegalArgumentException if {@code name} is blank
     * @since 1.0
     */
    public String greet(String name) {
        String normalized = Objects.requireNonNull(name, "name").trim();
        if (normalized.isEmpty()) {
            throw new IllegalArgumentException("name must not be blank");
        }

        String result = "Hello, " + normalized + "!";
        logger.info("Created greeting for {}", normalized);
        return result;
    }

    String toAuditJson(String name) {
        try {
            return objectMapper.writeValueAsString(
                    Map.of("message", greet(name)));
        } catch (JsonProcessingException ex) {
            throw new IllegalStateException("Could not create audit JSON", ex);
        }
    }
}
```

SLF4J Logger appears in the **public constructor**, so it belongs to the library's API. Jackson is used only in a package-private implementation method; library users do not need to reference ObjectMapper directly to use the public API. That is why the Gradle sample declares SLF4J with api and Jackson with implementation.

### 8.2. Unit Test

Create src/test/java/com/example/greeting/GreetingServiceTest.java:

```java
package com.example.greeting;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;
import org.slf4j.LoggerFactory;

class GreetingServiceTest {

    private final GreetingService service = new GreetingService(
            LoggerFactory.getLogger(GreetingServiceTest.class));

    @Test
    void trimsNameAndCreatesGreeting() {
        assertEquals("Hello, Lan!", service.greet("  Lan  "));
    }

    @Test
    void rejectsBlankName() {
        assertThrows(IllegalArgumentException.class,
                () -> service.greet("   "));
    }
}
```

This test does not require a Spring ApplicationContext. If using SLF4J API without a logging provider, test execution may print a provider warning; that does not change the test assertions. In real applications, consumers choose a compatible logging backend such as Logback or Log4j2.

## 9. Complete Maven POM: Metadata and Dependencies

Create pom.xml:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example.training</groupId>
    <artifactId>greeting-core</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <name>Greeting Core</name>
    <description>Reusable Java greeting library for publication examples.</description>
    <url>https://example.invalid/greeting-core</url>

    <licenses>
        <license>
            <name>The Apache License, Version 2.0</name>
            <url>https://www.apache.org/licenses/LICENSE-2.0.txt</url>
            <distribution>repo</distribution>
        </license>
    </licenses>

    <developers>
        <developer>
            <id>example-team</id>
            <name>Example Engineering Team</name>
            <organization>Example Organization</organization>
            <organizationUrl>https://example.invalid</organizationUrl>
        </developer>
    </developers>

    <scm>
        <connection>scm:git:https://example.invalid/example/greeting-core.git</connection>
        <developerConnection>scm:git:ssh://git@example.invalid/example/greeting-core.git</developerConnection>
        <url>https://example.invalid/example/greeting-core</url>
    </scm>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <project.reporting.outputEncoding>UTF-8</project.reporting.outputEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.slf4j</groupId>
            <artifactId>slf4j-api</artifactId>
            <version>2.0.16</version>
        </dependency>

        <dependency>
            <groupId>com.fasterxml.jackson.core</groupId>
            <artifactId>jackson-databind</artifactId>
            <version>2.18.2</version>
        </dependency>

        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.11.4</version>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
                <configuration>
                    <release>17</release>
                </configuration>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.2</version>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-source-plugin</artifactId>
                <version>3.4.0</version>
                <executions>
                    <execution>
                        <id>attach-sources</id>
                        <phase>verify</phase>
                        <goals>
                            <goal>jar-no-fork</goal>
                        </goals>
                    </execution>
                </executions>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-javadoc-plugin</artifactId>
                <version>3.11.3</version>
                <executions>
                    <execution>
                        <id>attach-javadocs</id>
                        <phase>verify</phase>
                        <goals>
                            <goal>jar</goal>
                        </goals>
                    </execution>
                </executions>
            </plugin>
        </plugins>
    </build>
</project>
```

The example.invalid URLs and com.example.training group are **illustrative values**. For real releases, replace them with a namespace owned by your organization and real project URL, license, SCM, and developer details. Never submit dummy metadata to Maven Central.

The POM declares:
- groupId:artifactId:version as the module identity.
- name, description, url, licenses, developers, scm to help users understand origin and usage rights.
- dependencies describing the library's dependency graph.
- scope=test keeping JUnit out of consumers' runtime dependency graph.
- maven.compiler.release=17 pinning the Java API/bytecode target for the example.
- Source/Javadoc plugins generating classifier artifacts and attaching them to the publication.

**The POM is part of the product.** Do not update only the README while forgetting to update the POM when dependencies, license, version, or SCM change.

## 10. Maven Source Plugin: Building -sources.jar

The maven-source-plugin packages main sources and attaches the artifact with classifier sources. Goal jar-no-fork is suitable when bound to the lifecycle because it does not fork another build phase.

Configuration snippet already present in section 9's POM:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-source-plugin</artifactId>
    <version>3.4.0</version>
    <executions>
        <execution>
            <id>attach-sources</id>
            <phase>verify</phase>
            <goals>
                <goal>jar-no-fork</goal>
            </goals>
        </execution>
    </executions>
</plugin>
```

After mvn verify, expected file:

```text
target/greeting-core-1.0.0-sources.jar
```

Can be invoked manually:

```bash
./mvnw source:jar
```

However, a release pipeline should bind the execution to the lifecycle so install/deploy uploads the sources archive alongside the binary. Do not create a source JAR by manually zipping an arbitrary directory; the plugin uses the project's proper source roots and generated sources.

If you want to publish test sources, Maven Source Plugin offers test-jar/test-jar-no-fork, typically with classifier test-sources. Publish them only when consumers genuinely have a use case, such as sharing test fixtures; do not expose all test code publicly by default.

## 11. Maven Javadoc Plugin: Building -javadoc.jar

maven-javadoc-plugin uses the JDK's Javadoc tool to generate HTML and packages it into a JAR with classifier javadoc.

Configuration snippet in section 9's POM:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-javadoc-plugin</artifactId>
    <version>3.11.3</version>
    <executions>
        <execution>
            <id>attach-javadocs</id>
            <phase>verify</phase>
            <goals>
                <goal>jar</goal>
            </goals>
        </execution>
    </executions>
</plugin>
```

Expected artifact:

```text
target/greeting-core-1.0.0-javadoc.jar
```

Run standalone goals when investigating:

```bash
./mvnw javadoc:javadoc
./mvnw javadoc:jar
```

javadoc:javadoc writes HTML output to the Javadoc output directory; javadoc:jar creates the archive for publishing. In multi-module Maven projects, javadoc:aggregate or javadoc:aggregate-jar can produce aggregated documentation; verify each published artifact still carries the right classifier per repository policy.

### 11.1. Fix Javadoc Errors in Source/API

Common causes:
- Public type/method has an invalid Javadoc tag or missing required content.
- @param, @return, @throws do not match the signature.
- The JDK running Javadoc is incompatible with sources/annotation processors.
- Classpath/module path is missing a required dependency.
- Generated sources do not exist yet when the goal runs.
- External links to API docs are blocked or unreachable.

Prioritize fixing comments, dependencies, source generation, and JDK/toolchain. Do not disable all doclint checks just to pass a release without understanding warnings/errors; Javadoc is public API documentation and requires quality control.

## 12. Maven: Building and Inspecting All Three Artifacts

Run from the greeting-core root:

```bash
./mvnw clean verify
```

If Maven Wrapper is not present, use a compatible installed Maven:

```bash
mvn clean verify
```

After success, inspect:

```bash
ls -lh target/greeting-core-1.0.0.jar
ls -lh target/greeting-core-1.0.0-sources.jar
ls -lh target/greeting-core-1.0.0-javadoc.jar
jar tf target/greeting-core-1.0.0-sources.jar
jar tf target/greeting-core-1.0.0-javadoc.jar
```

On Windows PowerShell, you can use:

```powershell
Get-ChildItem .\target\greeting-core-1.0.0*.jar
jar tf .\target\greeting-core-1.0.0-sources.jar
jar tf .\target\greeting-core-1.0.0-javadoc.jar
```

Expected:
- Main JAR contains class com/example/greeting/GreetingService.class.
- Sources JAR contains com/example/greeting/GreetingService.java.
- Javadoc JAR contains index.html and matching package/class documentation.

jar tf only checks that the archive contains entries; to inspect doc contents, extract into a temporary directory and open the HTML. Also verify the JAR did not accidentally include target/, .git/, secrets, or unrelated internal outputs.

## 13. Maven install and deploy Differ

| Command | Destination | Goal |
| --- | --- | --- |
| mvn package | target/ | Compile, test per lifecycle, and build JAR |
| mvn verify | target/ | Run additional checks and build sources/Javadoc per executions |
| mvn install | Local Maven repository, usually ~/.m2/repository | Use the artifact on the current machine |
| mvn deploy | Configured remote repository | Publish artifact/POM/classifiers for other machines to consume |

Test locally:

```bash
./mvnw clean install
```

Afterward, the artifact is installed into the local Maven repository alongside the POM and attached artifacts. Consumer projects on the same machine can declare the GAV dependency without pushing to a server.

**install is not deploy.** Another developer or CI runner does not automatically have artifacts from your local repository. Sharing across an organization requires a remote repository such as Nexus/Artifactory or a Maven-compatible service.

## 14. Maven distributionManagement and Credentials for Internal Repositories

In the POM, configure the deploy destination (replace with your company's real URLs):

```xml
<distributionManagement>
    <repository>
        <id>company-releases</id>
        <name>Company Maven Releases</name>
        <url>https://repo.example.invalid/repository/maven-releases/</url>
    </repository>
    <snapshotRepository>
        <id>company-snapshots</id>
        <name>Company Maven Snapshots</name>
        <url>https://repo.example.invalid/repository/maven-snapshots/</url>
    </snapshotRepository>
</distributionManagement>
```

- repository is the destination for release versions.
- snapshotRepository is the destination for versions ending in -SNAPSHOT.
- id is the key Maven uses to find matching credentials in settings.xml.
- The URLs above use the .invalid domain and **cannot actually be deployed to**; replace them with an authorized internal repository.

Put credentials in ~/.m2/settings.xml or CI secret configuration, never commit them into the POM:

```xml
<settings>
    <servers>
        <server>
            <id>company-releases</id>
            <username>${env.MAVEN_REPO_USER}</username>
            <password>${env.MAVEN_REPO_TOKEN}</password>
        </server>
        <server>
            <id>company-snapshots</id>
            <username>${env.MAVEN_REPO_USER}</username>
            <password>${env.MAVEN_REPO_TOKEN}</password>
        </server>
    </servers>
</settings>
```

id must match each repository in distributionManagement exactly. `MAVEN_REPO_USER` and `MAVEN_REPO_TOKEN` are supplied from the secret store/CI as environment variables; Maven settings interpolate them via `${env.NAME}`. On local machines, use encrypted Maven passwords or an appropriate credential management mechanism. Never store user tokens/passwords in Git, POMs, or build logs.

Once real URLs/credentials are configured:

```bash
./mvnw clean deploy
```

Maven runs phases prior to deploy, then builds and uploads the main JAR, POM, and attached sources/Javadoc classifiers. Verify files in the repository after deploy; a `BUILD SUCCESS` line does not replace verifying that the repository received all artifacts.

## 15. Maven Central: Release Requirements Differ from Internal Repositories

As of the current Central Publisher Portal workflow:
- Release versions must not end with -SNAPSHOT.
- For artifacts with packaging other than pom, main JAR plus -sources.jar and -javadoc.jar are required.
- The POM requires accurate GAV, project name, description, URL, license, developer, and SCM metadata.
- Published files require checksums and GPG/PGP signatures per Portal requirements.
- Published releases cannot be arbitrarily overwritten with different bytes; choose versions carefully.

**Do not assume old OSSRH-style distributionManagement + Maven Deploy Plugin still publishes directly to Central.** Legacy OSSRH reached end-of-life on 2025-06-30. Central Portal uses its own Maven plugin central-publishing-maven-plugin; plugin versions must follow active Portal guidance.

Example Central Publisher Maven Plugin configuration:

```xml
<plugin>
    <groupId>org.sonatype.central</groupId>
    <artifactId>central-publishing-maven-plugin</artifactId>
    <version>0.12.0</version>
    <extensions>true</extensions>
    <configuration>
        <publishingServerId>central</publishingServerId>
        <autoPublish>false</autoPublish>
    </configuration>
</plugin>
```

Add server id central to settings.xml with your **Central Portal user token**. Configure GPG signing so every required artifact is signed; the Central plugin generates checksums by default. The Portal plugin does not write Javadoc for you, generate source JARs automatically, or fill in all POM metadata on your behalf.

With autoPublish=false, upload/validation may complete while still requiring a manual publish action in the Central Portal. Enable auto-publish only after CI verifies coordinates, artifacts, signatures, and release policy.

## 16. Gradle: Enabling Source and Javadoc Variants with Java Library Plugin

Gradle has built-in support for both archives. When using java-library:

```groovy
plugins {
    id 'java-library'
}

java {
    withSourcesJar()
    withJavadocJar()
}
```

These two calls:
- Create the sourcesJar task and sourcesElements variant.
- Create the javadocJar task and javadocElements variant.
- When combined with maven-publish, include both archives in the publication from components.java.

There is no need to write custom ZIP/JAR tasks unless special layout rules apply. Tasks created by the Java plugin already know the project's source sets and Javadoc task.

Inspect tasks:

```bash
./gradlew tasks --all
./gradlew sourcesJar javadocJar
```

With Gradle Wrapper on Windows:

```powershell
.\gradlew.bat sourcesJar javadocJar
```

If a build applies only the java plugin rather than java-library, source/Javadoc archives can still be created; java-library additionally provides api/implementation semantics suitable for reusable libraries.

## 17. Gradle maven-publish: Complete Publication

Illustrative Groovy DSL configuration:

```groovy
plugins {
    id 'java-library'
    id 'maven-publish'
}

group = 'com.example.training'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
    withSourcesJar()
    withJavadocJar()
}

repositories {
    mavenCentral()
}

dependencies {
    api 'org.slf4j:slf4j-api:2.0.16'
    implementation 'com.fasterxml.jackson.core:jackson-databind:2.18.2'
    testImplementation 'org.junit.jupiter:junit-jupiter:5.11.4'
}

tasks.withType(Test).configureEach {
    useJUnitPlatform()
}

publishing {
    publications {
        mavenJava(MavenPublication) {
            from components.java
            pom {
                name = 'Greeting Core'
                description = 'Reusable Java greeting library.'
                url = 'https://example.invalid/greeting-core'
                licenses {
                    license {
                        name = 'The Apache License, Version 2.0'
                        url = 'https://www.apache.org/licenses/LICENSE-2.0.txt'
                    }
                }
                developers {
                    developer {
                        id = 'example-team'
                        name = 'Example Engineering Team'
                    }
                }
                scm {
                    connection = 'scm:git:https://example.invalid/example/greeting-core.git'
                    developerConnection = 'scm:git:ssh://git@example.invalid/example/greeting-core.git'
                    url = 'https://example.invalid/example/greeting-core'
                }
            }
        }
    }
    repositories {
        maven {
            name = 'localBuild'
            url = layout.buildDirectory.dir('repo')
        }
    }
}
```

The URLs and team identity remain illustrative examples. Replace them with real details before a public release.

from components.java is the key step: it pulls the component model provided by the Java Library Plugin, including the main JAR, dependencies/variants, and declared source/Javadoc artifacts. Publishing a standalone JAR file manually may leave metadata missing dependencies or variants.

## 18. Gradle Kotlin DSL

If using build.gradle.kts:

```kotlin
import org.gradle.api.publish.maven.MavenPublication

plugins {
    id("java-library")
    id("maven-publish")
}

group = "com.example.training"
version = "1.0.0"

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
    withSourcesJar()
    withJavadocJar()
}

repositories {
    mavenCentral()
}

dependencies {
    api("org.slf4j:slf4j-api:2.0.16")
    implementation("com.fasterxml.jackson.core:jackson-databind:2.18.2")
    testImplementation("org.junit.jupiter:junit-jupiter:5.11.4")
}

tasks.withType<Test>().configureEach {
    useJUnitPlatform()
}

publishing {
    publications {
        create<MavenPublication>("mavenJava") {
            from(components["java"])
            pom {
                name.set("Greeting Core")
                description.set("Reusable Java greeting library.")
                url.set("https://example.invalid/greeting-core")
            }
        }
    }
    repositories {
        maven {
            name = "localBuild"
            url = uri(layout.buildDirectory.dir("repo"))
        }
    }
}
```

This is the Kotlin DSL alternative to Groovy. Use typed create<MavenPublication>, from(components["java"]), and Property.set; do not mix Groovy syntax into Kotlin.

## 19. Gradle Publish and Checking the Local Repository

Run:

```bash
./gradlew clean test publish
```

Or the specific publication task:

```bash
./gradlew publishMavenJavaPublicationToLocalBuildRepository
```

Demo repository is expected to contain:

```text
build/repo/com/example/training/greeting-core/1.0.0/
├── greeting-core-1.0.0.jar
├── greeting-core-1.0.0.pom
├── greeting-core-1.0.0.module
├── greeting-core-1.0.0-sources.jar
└── greeting-core-1.0.0-javadoc.jar
```

You can publish to ~/.m2/repository with:

```bash
./gradlew publishToMavenLocal
```

mavenLocal() is convenient for testing on a developer machine; it should not be CI's default dependency source because local contents can differ across machines.

## 20. Gradle Remote Repository and Credentials

Configure an internal repository:

```groovy
publishing {
    repositories {
        maven {
            name = 'internal'
            url = uri('https://repo.example.invalid/repository/maven-releases')
            credentials(PasswordCredentials)
        }
    }
}
```

Gradle looks up credentials by repository name: internalUsername and internalPassword in user-level ~/.gradle/gradle.properties or CI secret injection. Never commit tokens. Release and snapshot repositories can be split by version; the example.invalid host is a placeholder to replace with a real URL.

## 21. Gradle Module Metadata and Variants

Since Gradle 6.0, maven-publish can publish Gradle Module Metadata alongside the POM. A Java library typically exposes:
- apiElements for compile-time consumers.
- runtimeElements for runtime consumers.

Metadata can describe org.gradle.usage, org.gradle.category, org.gradle.libraryelements, org.gradle.jvm.version, capabilities, constraints, and variant-specific dependencies.

Gradle consumers can use .module to select the right variant; Maven consumers use the POM. Never edit .module manually: adjust components, attributes, api/implementation, and toolchains in the build script and let Gradle generate metadata.

## 22. Dependency Metadata Must Reflect the Public Contract

In the sample, SLF4J appears in the public constructor, so Gradle uses api. Jackson serves internal implementation only, so Gradle uses implementation. JUnit serves tests only, so testImplementation is used.

Maven has no api/implementation distinction. Compile dependencies are normally published transitively. Maven optional=true means consumers do not pull that dependency automatically; use it only when a feature is genuinely optional. If the library always needs Jackson at runtime yet marks it optional, consumers can hit NoClassDefFoundError.

Use exclusions only when you know the exact transitive dependency to exclude; excluding the wrong dependency can leave consumers missing runtime classes.

## 23. Spring Boot Executable JAR and Reusable Library JAR

Spring Boot repackage produces an executable archive with BOOT-INF/classes and BOOT-INF/lib layout for running with java -jar. This is not an appropriate JAR for a regular Java dependency because application classes sit under BOOT-INF/classes rather than the root classpath.

**Library modules should publish regular/thin JARs** from the Java Library Plugin or Maven JAR lifecycle. If one Maven module needs both a main library JAR and an executable archive, the executable can be attached with classifier exec in the repackage execution:

```xml
<executions>
    <execution>
        <id>repackage</id>
        <configuration>
            <classifier>exec</classifier>
        </configuration>
    </execution>
</executions>
```

If the starter parent already defines a repackage execution, configure that existing execution rather than adding a duplicate. With Gradle, separating the library module and Boot application module is usually cleaner.

## 24. Multi-Module Publication

In Maven multi-module builds:
- The root aggregator usually has packaging=pom.
- Each publishable child module needs a POM, main JAR, sources, and Javadoc.
- Manage plugin versions in the parent while applying executions only to the appropriate modules.
- javadoc:aggregate-jar can be used for aggregated documentation, while still verifying classifiers per artifact per policy.

In Gradle multi-project builds:
- Apply java-library and maven-publish on each library module.
- Configure withSourcesJar/withJavadocJar on components to publish.
- Publications take components.java properly.
- Run task paths like :greeting-core:publish.
- Do not publish an aggregator or convention plugin as a library if it has no matching module artifact.

## 25. Inspecting Metadata and Archives After Publishing

Maven:

```bash
./mvnw help:effective-pom -Doutput=target/effective-pom.xml
./mvnw dependency:tree
jar tf target/greeting-core-1.0.0-sources.jar
jar tf target/greeting-core-1.0.0-javadoc.jar
```

Gradle:

```bash
./gradlew outgoingVariants
./gradlew dependencies
```

Verify the POM has exact GAV, dependencies, scopes, license, SCM; .module has accurate api/runtime variants and attributes; the main JAR has compiled classes; the sources JAR has Java sources from the same commit; and the Javadoc JAR has HTML API docs. Test dependencies must never become consumer runtime dependencies. Never let secrets, .git, build outputs, or unrelated internal files leak into archives.

## 26. Consumer Smoke Test

A publication is only truly verified when another project can resolve it by GAV.

Maven consumer declares the dependency:

```xml
<dependency>
    <groupId>com.example.training</groupId>
    <artifactId>greeting-core</artifactId>
    <version>1.0.0</version>
</dependency>
```

After the library has been mvn installed or deployed, run dependency:tree and mvn test. The consumer does not declare sources/javadoc classifiers.

Gradle consumer:

```groovy
repositories {
    maven {
        url = uri('../greeting-core/build/repo')
    }
    mavenCentral()
}

dependencies {
    implementation 'com.example.training:greeting-core:1.0.0'
}
```

Inspect the compile/runtime graphs:

```bash
./gradlew dependencies --configuration compileClasspath
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency slf4j-api --configuration compileClasspath
./gradlew dependencyInsight --dependency jackson-databind --configuration runtimeClasspath
```

Expect SLF4J on the compile classpath, Jackson in the runtime graph, and JUnit absent from the consumer's runtime. Consumer tests catch bad metadata much better than running tests solely inside the library project.

## 27. Maven Central: Current Requirements and Gradle Limitations

Maven Central requires a release version not ending in -SNAPSHOT; main artifact, POM, sources JAR, Javadoc JAR, POM metadata, checksums, and GPG/PGP signatures. The POM must include GAV, name, description, URL, license, developer, and SCM.

Maven Central now uses the Central Publisher Portal and central-publishing-maven-plugin. The plugin generates checksums but does not automatically generate all sources/Javadoc/signatures/metadata. Legacy OSSRH ended on 2025-06-30. Successful upload/validation does not mean public availability if the Portal requires manual publish confirmation.

**Gradle has an important difference:** current Sonatype documentation notes there is no official Gradle plugin to publish directly to the Central Publisher Portal. maven-publish remains suitable for Nexus/Artifactory/internal Maven repositories and produces POM/.module, whereas publishing to Central requires choosing an appropriate Portal option such as an evaluated community plugin, JReleaser, bundle/API upload, or OSSRH Staging API compatibility. Never assume the default publish task published to Central.

## 28. Signing and Checksums

Checksums detect byte-level file alterations; GPG/PGP signatures bind files to the corresponding private key; SBOMs/provenance add component and build process details. Each serves a distinct role.

The Gradle Signing Plugin can sign publications:

```groovy
plugins {
    id 'java-library'
    id 'maven-publish'
    id 'signing'
}

signing {
    sign publishing.publications.mavenJava
}
```

This is an addition to a build script that already defines the mavenJava publication. Key material must come from a secret manager/CI; never hardcode private keys or passphrases. Verify signatures of the main JAR, POM, sources JAR, Javadoc JAR, and metadata per repository requirements.

## 29. Versioning and Provenance

- 1.0.0-SNAPSHOT: development build, snapshot repository may change.
- 1.0.0: immutable release once public.
- 1.1.0: backward-compatible feature additions per policy.
- 2.0.0: breaking API if following SemVer.

Never let the main JAR come from commit A, sources JAR from commit B, Javadoc from code C, and the POM describe dependencies of version D. A release is **a set of artifacts sharing the same provenance**. Record commit ID, build ID, checksums, and a release manifest for troubleshooting.

## 30. Common Errors

| Symptom | Cause | Fix |
| --- | --- | --- |
| Repository only has main JAR | Plugin did not run or artifact not attached | Bind source:jar-no-fork and javadoc:jar |
| Sources do not match binary | Different commit | Rebuild from same commit/version |
| Javadoc JAR missing packages | Source roots/generated sources unrecognized | Check source sets and lifecycle |
| Javadoc fails | Doclint/tag/JDK/classpath | Fix API docs and toolchain |
| Test dependencies published | Wrong scope/configuration | Maven test or Gradle testImplementation |
| Consumer missing public API type | Dependency given runtime/implementation scope | Correct Maven scope or Gradle api |
| NoClassDefFoundError | Missing runtime dependency or wrong optional flag | Inspect dependency graph |
| .module exists yet Maven ignores it | Maven understands POM only | Verify POM mapping |
| Maven POM missing dependencies | Uploaded standalone JAR or broken POM | Publish accurate POM |
| Duplicate sources/Javadoc classifiers | Plugin attached twice | Remove duplicate execution |
| Central rejects release | Missing docs, metadata, checksum/signature | Check Portal validation |
| Using old OSSRH deploy endpoint | OSSRH has shut down | Migrate to Central Portal |
| Gradle publish succeeds yet missing from Central | Published to another repository | Configure Central Portal separately |
| 401/403 | Wrong credentials/id/namespace | Check settings.xml or Gradle properties |
| Release cannot be overwritten | Repository is immutable | Create a new version |
| Boot fat JAR fails to load as dependency | Classes sit under BOOT-INF/classes | Publish thin JAR; separate executable classifier |

## 31. Pre-Publish Checklist

- [ ] GAV/version/packaging are accurate.
- [ ] Main JAR contains exact classes/resources.
- [ ] Sources JAR is from the same commit as the main JAR.
- [ ] Javadoc JAR contains HTML for public APIs.
- [ ] POM describes exact dependencies/scopes/optional/exclusions.
- [ ] Gradle api is used only for dependencies exposed in the public API.
- [ ] Gradle implementation is used for internal dependencies.
- [ ] Test-only dependencies do not become runtime dependencies.
- [ ] POM contains real name/description/URL/license/developer/SCM.
- [ ] Gradle uses from components.java, withSourcesJar, and withJavadocJar.
- [ ] Multi-module artifacts have accurate classifiers.
- [ ] Do not publish executable Boot fat JARs as main library dependencies.
- [ ] Consumer project resolves GAV and compile/runtime graphs.
- [ ] Checksums/signatures match policy.
- [ ] Credentials reside outside source code with least privilege.
- [ ] Central Portal workflow is verified separately.
- [ ] Release artifacts/provenance are stored for audit/rollback.

**Key takeaway:** the main JAR holds bytecode, **sources/Javadoc JARs** help developers understand and debug APIs, while **POM/Gradle .module** determines how consumers resolve dependency graphs and variants. Generate all of them from the same source commit, test with a consumer project, verify metadata/signatures/checksums, and only then publish.

## Official References

- [Apache Maven — POM Reference](https://maven.apache.org/pom.html)
- [Apache Maven Source Plugin — Usage](https://maven.apache.org/plugins/maven-source-plugin/usage.html)
- [Apache Maven Source Plugin — jar-no-fork](https://maven.apache.org/components/plugins/maven-source-plugin/jar-no-fork-mojo.html)
- [Apache Maven Javadoc Plugin 3.11.3](https://maven.apache.org/plugins-archives/maven-javadoc-plugin-3.11.3/plugin-info.html)
- [Apache Maven — Deployment Transports and Credentials](https://maven.apache.org/guides/mini/guide-deployment-transports.html)
- [Gradle — Java Plugin](https://docs.gradle.org/current/userguide/java_plugin.html)
- [Gradle — Maven Publish Plugin](https://docs.gradle.org/current/userguide/publishing_maven.html)
- [Gradle — Gradle Module Metadata](https://docs.gradle.org/current/userguide/publishing_gradle_module_metadata.html)
- [Gradle — Supported Metadata Formats](https://docs.gradle.org/current/userguide/supported_metadata_formats.html)
- [Gradle — Repository Credentials](https://docs.gradle.org/current/userguide/supported_repository_protocols.html)
- [Spring Boot — Packaging Executable Archives](https://docs.spring.io/spring-boot/maven-plugin/packaging.html)
- [Sonatype Central — Publishing Requirements](https://central.sonatype.org/publish/requirements/)
- [Sonatype Central — Publishing with Maven](https://central.sonatype.org/publish/publish-portal-maven/)
- [Sonatype Central — Publishing with Gradle](https://central.sonatype.org/publish/publish-portal-gradle/)
- [Sonatype Central — OSSRH Sunset](https://central.sonatype.org/publish/publish-gradle/)
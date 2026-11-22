# Gradle Jar task: Packaging a Java Application into a JAR

## 1. What is the Jar task?

`Jar` is a Gradle task used to create a Java Archive (JAR) from compiled classes and resources. A JAR is a ZIP-based archive with a directory structure and metadata following Java platform conventions.

When the Java Plugin or Java Library Plugin is applied, Gradle automatically creates a task named `jar`. This task packages the output of the `main` source set, typically including:

- Compiled `.class` files from `src/main/java`.
- Processed resources from `src/main/resources`.
- The `META-INF/MANIFEST.MF` manifest file.
- `module-info.class` or other metadata if the project is configured accordingly.

`jar` creates an artifact for other Java programs to use or for distribution. The task does not automatically package all libraries in `runtimeClasspath` into the archive. This is an important difference between a regular JAR and a fat/uber JAR.

## 2. Where does the Jar task sit in the build lifecycle?

With the Java Plugin, Gradle creates the following main tasks:

| Task | Purpose |
|---|---|
| `compileJava` | Compiles Java sources of the main source set |
| `processResources` | Copies and processes main resources |
| `classes` | Aggregates the outputs of compilation and resource processing |
| `jar` | Packages the main output into a JAR |
| `assemble` | Builds the main artifacts of the project |
| `build` | Runs verification and packaging steps, including `check` and `assemble` |

`jar` is attached to the `assemble` lifecycle task. Therefore, running `gradle assemble` produces the default JAR. Running `gradle build` also produces the JAR after the required steps complete.

`src/test/java` and `src/test/resources` belong to the test source set. They are not included in the default production JAR. Tests are compiled and executed through separate tasks such as `compileTestJava` and `test`.

Basic flow:

```text
src/main/java       src/main/resources
       |                     |
  compileJava          processResources
       |                     |
       +--------- classes ---+
                    |
                   jar
                    |
             build/libs/*.jar
                    |
                 assemble
                    |
                  build
```

The `jar` task uses the source set output so Gradle knows which task dependencies need to run. When creating a custom Jar task, use `sourceSets.main.output` instead of concatenating the path to the classes directory as a string; this preserves accurate task dependency relationships.

## 3. Structure of a JAR file

You can list the contents of a JAR with:

```bash
jar --list --file build/libs/my-app-1.0.jar
```

Example of a simple JAR:

```text
META-INF/
META-INF/MANIFEST.MF
com/
com/example/
com/example/Main.class
com/example/service/OrderService.class
application.properties
```

Common components:

- `META-INF/MANIFEST.MF`: archive metadata, which can declare the entry point, version, or implementation details.
- `.class`: Java class bytecode.
- Resources: properties files, JSON, XML, templates, images, or data needed at runtime.
- `META-INF/services/`: service provider configuration used with `ServiceLoader`.
- `module-info.class`: module descriptor when the project uses the Java Platform Module System.
- Signature files such as `META-INF/*.SF`, `*.RSA`, or `*.DSA`: present in signed JARs.

Class package names are represented as directory paths. For example, `com.example.Main` resides at `com/example/Main.class`.

Resources in `src/main/resources` are placed into the archive according to their relative path. For example, `src/main/resources/config/app.properties` becomes `config/app.properties`. Resources can be read using `Class.getResourceAsStream` or `ClassLoader.getResourceAsStream`.

## 4. Creating a minimal Java project

Standard project structure:

```text
jar-task-demo/
├── settings.gradle
├── build.gradle
└── src/
    └── main/
        ├── java/
        │   └── demo/
        │       └── Main.java
        └── resources/
            └── app.properties
```

File `settings.gradle`:

```groovy
rootProject.name = 'jar-task-demo'
```

File `build.gradle`:

```groovy
plugins {
    id 'java'
}

group = 'com.example'
version = '1.2.3'

tasks.withType(JavaCompile).configureEach {
    options.release = 17
}
```

`options.release = 17` instructs the compiler to generate bytecode and apply the API surface corresponding to Java 17. In real projects, you can declare a Java toolchain to pin the JDK used for the build; `options.release` and toolchains solve two related but distinct concerns.

## 5. Running and locating the default JAR

Common commands:

```bash
gradle tasks --all
gradle clean
gradle jar
gradle assemble
gradle build
```

After running `gradle jar`, the default artifact is typically located at:

```text
build/libs/jar-task-demo-1.2.3.jar
```

The default filename combines the project name and project version. The default destination directory for JARs is `build/libs`.

Inspect the generated file:

```bash
jar --list --file build/libs/jar-task-demo-1.2.3.jar
```

If the build script, sources, and resources have not changed, Gradle may report the `jar` task as `UP-TO-DATE`. This is normal incremental build behavior.

## 6. Configuring the Jar task

Use `tasks.named` to configure the `jar` task created by the Java Plugin:

```groovy
tasks.named('jar', Jar) {
    archiveBaseName = 'sample-app'

    manifest {
        attributes(
            'Main-Class': 'demo.Main',
            'Implementation-Title': 'Sample App',
            'Implementation-Version': project.version
        )
    }
}
```

In Kotlin DSL:

```kotlin
tasks.named<Jar>("jar") {
    archiveBaseName = "sample-app"

    manifest {
        attributes(
            mapOf(
                "Main-Class" to "demo.Main",
                "Implementation-Title" to "Sample App",
                "Implementation-Version" to project.version
            )
        )
    }
}
```

`tasks.named` configures an existing task without creating a new one. When you need to create another archive, use `tasks.register<Jar>` in Kotlin DSL or `tasks.register('name', Jar)` in Groovy DSL. This is lazy configuration, aligning with Gradle task configuration avoidance.

Do not create another task named `jar` because that name is already used by the Java Plugin.

## 7. Archive naming and location properties

`Jar` inherits properties from `AbstractArchiveTask`. Commonly used properties:

| Property | Meaning |
|---|---|
| `archiveBaseName` | Primary name part of the archive |
| `archiveAppendix` | Additional part after the base name |
| `archiveVersion` | Version part |
| `archiveClassifier` | Label distinguishing artifacts such as `sources`, `javadoc`, or `all` |
| `archiveExtension` | File extension, defaults to `jar` |
| `archiveFileName` | Complete filename |
| `destinationDirectory` | Directory containing the archive |
| `archiveFile` | Provider pointing to the resulting file, read-only |

The default name follows the format:

```text
[baseName]-[appendix]-[version]-[classifier].[extension]
```

Empty parts do not produce extra hyphens. With the Java Plugin, `archiveBaseName` defaults to the project name, `archiveVersion` comes from `project.version`, and `archiveClassifier` is typically empty.

Example:

```groovy
tasks.named('jar', Jar) {
    archiveBaseName = 'orders'
    archiveVersion = '2.4.0'
    archiveClassifier = 'linux'
    destinationDirectory = layout.buildDirectory.dir('release')
}
```

Result:

```text
build/release/orders-2.4.0-linux.jar
```

If you want a fixed name, you can assign `archiveFileName`:

```groovy
tasks.named('jar', Jar) {
    archiveFileName = 'application.jar'
}
```

Setting `archiveFileName` overrides the composition from base name, appendix, version, classifier, and extension. Avoid having multiple tasks write to the same output path. When creating multiple archive variants, use different classifiers.

You can read the output path via a Provider:

```groovy
def jarFile = tasks.named('jar', Jar).flatMap { it.archiveFile }
```

Do not assign directly to `archiveFile` because it is a read-only output provider; configure the naming and directory properties instead.

## 8. Adding Main-Class and manifest attributes

The manifest is located at `META-INF/MANIFEST.MF`. To run a JAR with `java -jar`, you need to declare an entry point:

```groovy
tasks.named('jar', Jar) {
    manifest {
        attributes(
            'Main-Class': 'demo.Main',
            'Implementation-Title': 'Order Service',
            'Implementation-Version': project.version,
            'Automatic-Module-Name': 'com.example.orders'
        )
    }
}
```

`Main-Class` is the fully qualified class name including the package, without the `.class` suffix. That class must have a `public static void main(String[] args)` method and must be inside the JAR or on an accessible classpath.

An illustrative manifest:

```text
Manifest-Version: 1.0
Main-Class: demo.Main
Implementation-Title: Order Service
Implementation-Version: 2.4.0
```

`Implementation-Title` and `Implementation-Version` are metadata describing the artifact. `Automatic-Module-Name` provides a stable module name for a JAR that does not yet have an explicit module descriptor; if `module-info.class` is present, the module descriptor determines the module name.

The manifest also has a `Class-Path` attribute. This value is a list of relative URLs to other JARs according to the manifest specification. It is not automatically generated from Gradle `implementation` dependencies, nor does it mean the dependencies are embedded in the JAR.

Do not write passwords, tokens, private keys, or secrets into the manifest. Manifest contents are distributed with the artifact and can be read by recipients.

## 9. Customizing JAR contents with from, include, exclude, and into

`Jar` is an archive task based on the CopySpec mechanism. You can add multiple file sources:

```groovy
tasks.named('jar', Jar) {
    from(sourceSets.main.output)

    from('src/main/extra') {
        into 'extra'
    }
}
```

Common operations:

- `from`: adds files or directories to the archive.
- `into`: changes the target directory inside the archive.
- `include`: includes only files matching the pattern.
- `exclude`: excludes files matching the pattern.
- `rename`: renames files during copying.
- `filesMatching`: configures specific files matching a pattern.
- `eachFile`: modifies the path or attributes of each file.

Example of including only a subset of files in the archive:

```groovy
tasks.named('jar', Jar) {
    from(sourceSets.main.output)

    include 'demo/**'
    exclude 'demo/internal/**'
    exclude '**/*.bak'
}
```

Example of changing the location of a resource:

```groovy
tasks.named('jar', Jar) {
    from('src/main/resources') {
        into 'config'
        include '**/*.properties'
    }
}
```

If the file was originally at `src/main/resources/app.properties`, the example above places it at `config/app.properties`. Verify the resource path used by your code after changing the archive structure.

`include` and `exclude` use Ant-style patterns. Patterns apply to relative paths within the CopySpec, so inspect the archive contents after configuring rather than relying only on source filenames.

## 10. Creating a custom Jar task

You can create an additional archive for a portion of the output:

```groovy
tasks.register('demoJar', Jar) {
    archiveClassifier = 'demo'

    from sourceSets.main.output

    include 'demo/**'
    exclude 'demo/internal/**'
}
```

This task reuses the output of the main source set, but creates a separate artifact with the `demo` classifier. Because it uses `sourceSets.main.output`, Gradle knows to build the corresponding output before packaging.

If you only want to package a standalone directory of files:

```groovy
tasks.register('configJar', Jar) {
    archiveClassifier = 'config'
    from('src/main/config')
    include '**/*'
}
```

If a task reads files from the build directory using a string path such as `build/classes/java/main`, declare an appropriate dependency on the task that produces that directory. Prefer using an output Provider or source set so Gradle manages this relationship.

## 11. Creating a Sources JAR and Javadoc JAR

The Java Plugin supports two additional artifacts commonly used when publishing libraries:

```groovy
java {
    withSourcesJar()
    withJavadocJar()
}
```

Gradle creates the `sourcesJar` and `javadocJar` tasks. They package production sources and Javadoc respectively. Example:

```text
build/libs/library-1.0-sources.jar
build/libs/library-1.0-javadoc.jar
build/libs/library-1.0.jar
```

A Sources JAR is useful so IDEs can display source code when users open a dependency. A Javadoc JAR contains API documentation generated from sources and Javadoc comments.

Do not manually create a second task with the duplicate name `sourcesJar` or `javadocJar` when these options are enabled. If you need a custom source archive, give it a distinct task name and classifier.

## 12. Handling duplicate entries

Duplicate entries occur when multiple sources place the same path into the archive. For example, two dependencies both contain `META-INF/services/com.example.Plugin` or a resource with the same name.

`duplicatesStrategy` determines how to handle them:

| Strategy | Behavior |
|---|---|
| `INHERIT` | Inherits the strategy from the parent CopySpec |
| `INCLUDE` | Keeps duplicate entries |
| `EXCLUDE` | Skips subsequent duplicates |
| `WARN` | Logs a warning and continues |
| `FAIL` | Fails the build when a duplicate is encountered |

With the Java Plugin, the default for `Jar` is `DuplicatesStrategy.INHERIT`. When building a fat JAR, choose a strategy intentionally:

```groovy
tasks.named('fatJar', Jar) {
    duplicatesStrategy = DuplicatesStrategy.EXCLUDE
}
```

`EXCLUDE` can let the build proceed, but it may silently drop a needed service provider or resource. For libraries or plugins using `ServiceLoader`, merge `META-INF/services` contents in the proper format instead of arbitrarily dropping duplicates.

`FAIL` is suitable when you want to detect conflicts early. Then, handle each duplicate resource by excluding the specific file, changing its path, or merging its contents. Do not use `EXCLUDE` as a way to hide all conflicts.

## 13. Regular JAR vs. fat/uber JAR

The Java Plugin's regular JAR contains the project's own output: production classes and resources. Dependencies declared with `implementation` or `runtimeOnly` are not automatically embedded into that file.

For example, an application depending on an external library:

```groovy
dependencies {
    implementation 'org.apache.commons:commons-lang3:3.17.0'
}
```

`build/libs/app.jar` contains the project's classes, but does not automatically contain Commons Lang classes. When running with `java -jar`, dependencies must be on the runtime classpath or packaged using an appropriate application packaging approach.

A **Fat JAR** (also called an uber JAR) unpacks the contents of dependency JARs and includes them in the same archive. Example:

```groovy
tasks.register('fatJar', Jar) {
    archiveClassifier = 'all'
    duplicatesStrategy = DuplicatesStrategy.EXCLUDE

    manifest {
        attributes('Main-Class': 'demo.Main')
    }

    from sourceSets.main.output

    dependsOn configurations.runtimeClasspath
    from {
        configurations.runtimeClasspath
            .findAll { it.name.endsWith('.jar') }
            .collect { zipTree(it) }
    }
}
```

This snippet takes the application's output and the contents of JARs on the runtime classpath. It is a minimal pattern; real projects need to handle duplicate resources, service descriptors, module metadata, and dependency signatures.

When merging signed dependencies into a new archive, the old signatures are no longer valid for the new contents. Remove old signature metadata and re-sign the final artifact if required by the release process. For service loaders, use a packaging plugin that supports merging service files, such as the Shadow Plugin, or equivalent merge configuration.

Fat JARs can also cause class conflicts if multiple libraries contain the same package/class. When you need to relocate packages, process service resources, and minimize unused dependencies, use a dedicated tool and test the output artifact.

## 14. When to use the Application Plugin instead of a fat JAR?

If the goal is to distribute a Java application along with its runtime libraries, the Gradle Application Plugin is often a clearer choice.

```groovy
plugins {
    id 'application'
}

application {
    mainClass = 'demo.Main'
}
```

The plugin creates a distribution containing the application JAR, dependency JARs, and launch scripts for Unix-like systems and Windows. The `run` task lets you run the application from the build; `installDist` creates an installation directory; `distZip` and `distTar` create distribution archives.

This approach keeps dependencies as separate JARs in a `lib` directory and the script configures the classpath. Operators can replace or inspect individual libraries more easily than with a large fat JAR.

Choose the packaging approach based on your needs:

- Library: regular JAR and dependency metadata for other projects to consume.
- CLI application: Application Plugin for launch scripts and runtime libraries.
- Fat JAR: when the deployment environment requires a single archive and duplicates/signatures/service metadata are handled.
- Servlet-based web application: consider the WAR Plugin; the `war` task creates a web archive structure with `WEB-INF/classes` and `WEB-INF/lib`.

## 15. Creating reproducible archives

Reproducible builds produce byte-for-byte identical archives when given the same inputs and corresponding build conditions. This is useful for CI, artifact auditing, and binary provenance verification.

Starting from Gradle 9.0, archive tasks default to:

- `preserveFileTimestamps = false`: does not preserve source file timestamps in archive entries.
- `reproducibleFileOrder = true`: sorts files in a stable order when packaging.

You can configure this explicitly if the build needs to support older Gradle versions:

```groovy
tasks.withType(AbstractArchiveTask).configureEach {
    preserveFileTimestamps = false
    reproducibleFileOrder = true
}
```

This helps keep archives stable, though it does not guarantee the entire build is always identical. Other factors can still cause different outputs:

- Changing JDK/compiler versions resulting in different bytecode.
- Build scripts embedding timestamps, hostnames, or local machine paths.
- Generated resource contents depending on the environment.
- Unpinned dependency versions or repositories returning different artifacts.
- Manifests containing build numbers or metadata that changes per build.

To achieve reproducible builds, pin the toolchain, lock dependencies where appropriate, avoid unstable metadata, and compare artifact hashes. Do not enable `preserveFileTimestamps = true` just to record source file times; build timestamps should be recorded in build metadata systems if truly needed.

## 16. Incremental build, cache, and output Provider

`Jar` is a task whose inputs and outputs are managed by Gradle. If classes, resources, and task configuration have not changed, Gradle can skip the task because the output is still valid.

- `UP-TO-DATE`: the current output matches the recorded inputs.
- `FROM-CACHE`: the output was restored from the build cache.
- `NO-SOURCE`: there are no matching source inputs.
- `EXECUTED`: the task actually ran in the current build.

When writing a task that depends on a JAR, use a Provider instead of manually concatenating path strings:

```groovy
tasks.register('copyAppJar', Copy) {
    from(tasks.named('jar', Jar).flatMap { it.archiveFile })
    into(layout.buildDirectory.dir('copied'))
}
```

This tells Gradle which task produces the output file and maintains the dependency relationship. Avoid calling `jar.archiveFile.get().asFile` too early during the configuration phase or using `doLast` to create a JAR with shell commands; doing so makes it harder for Gradle to track inputs/outputs and reduces incremental build effectiveness.

## 17. Publishing a JAR via Maven Publish

For libraries, publish the Java component so Gradle generates the appropriate artifact and dependency metadata.

```groovy
plugins {
    id 'java-library'
    id 'maven-publish'
}

group = 'com.example'
version = '1.0.0'

java {
    withSourcesJar()
    withJavadocJar()
}

publishing {
    publications {
        mavenJava(MavenPublication) {
            from components.java
        }
    }
}
```

`from components.java` publishes the Java component along with its related artifacts and metadata. The Sources JAR and Javadoc JAR are added when the corresponding options are enabled.

When creating additional custom classifiers, declare those artifacts in the publication if users need to download them from a Maven repository. Simply creating a file in `build/libs` does not mean the artifact is automatically published.

Use `archiveClassifier` for variants such as `sources`, `javadoc`, or `all` so artifact names are clearly distinguished in the repository. Do not arbitrarily change the classifier of the main artifact, as that can break consumer dependency conventions.

## 18. Modular JAR, multi-release JAR, and signing

### Modular JAR

If a project has `module-info.java` and compiles `module-info.class` at the root of the JAR, the archive is an explicit modular JAR. Inspect the module descriptor:

```bash
jar --describe-module --file build/libs/app.jar
```

Without a module descriptor, a JAR on the module path may be treated as an automatic module based on naming rules. `Automatic-Module-Name` in the manifest can provide a stable name for a JAR that does not yet have `module-info.class`.

### Multi-release JAR

A multi-release JAR can contain different implementations per Java version, placed in directories such as `META-INF/versions/9/`. The manifest must include the attribute:

```text
Multi-Release: true
```

Simply adding files to `META-INF/versions/` without understanding multi-release rules can cause the JVM to not select classes as expected. Use the `--release` option of the `jar` tool or dedicated build configuration, and validate the archive with `jar --validate`.

### Signing

A JAR can be signed with `jarsigner` or the Gradle Signing Plugin. If the archive contents are modified after signing, the signature will no longer verify. Finish packaging, verify, and only sign the final artifact.

Verify the signature:

```bash
jarsigner -verify -verbose -certs build/libs/app.jar
```

## 19. Inspecting JAR contents and runnability

A basic verification checklist:

1. Verify the task succeeded and the artifact exists.
2. List entries with `jar --list`.
3. Inspect the manifest by extracting `META-INF/MANIFEST.MF`.
4. Verify the main class and required resources are in the archive.
5. Run `java -jar` if the JAR has a `Main-Class`.
6. If the JAR is a library, test consuming it from a consumer project.
7. Check dependency metadata and classifiers if preparing to publish.
8. For modular JARs, check with `jar --describe-module`.
9. For multi-release JARs, run `jar --validate`.
10. For signed artifacts, run `jarsigner -verify`.

Useful commands:

```bash
jar --list --file build/libs/app.jar
jar --extract --file build/libs/app.jar META-INF/MANIFEST.MF
java -jar build/libs/app.jar
javap -classpath build/libs/app.jar demo.Main
```

`java -jar` requires `Main-Class` in the manifest and all dependencies satisfied on the runtime classpath. A JAR that is valid as a ZIP file can still fail to run if classes, resources, or dependencies are missing.

## 20. Complete example: creating an executable JAR and custom JAR

This example uses Java 17 source release and Gradle Groovy DSL.

File `build.gradle`:

```groovy
plugins {
    id 'java'
}

group = 'com.example'
version = '1.2.3'

java {
    withSourcesJar()
    withJavadocJar()
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
}

tasks.named('jar', Jar) {
    archiveBaseName = 'sample-app'

    manifest {
        attributes(
            'Main-Class': 'demo.Main',
            'Implementation-Title': 'Sample App',
            'Implementation-Version': project.version
        )
    }
}

tasks.register('demoJar', Jar) {
    archiveClassifier = 'demo'
    from sourceSets.main.output
    include 'demo/**'
    exclude 'demo/internal/**'
}
```

File `src/main/java/demo/Main.java`:

```java
package demo;

import java.io.IOException;
import java.io.InputStream;
import java.util.Properties;

public class Main {
    public static void main(String[] args) throws IOException {
        Properties properties = new Properties();

        try (InputStream input =
                Main.class.getResourceAsStream("/app.properties")) {
            if (input == null) {
                throw new IllegalStateException(
                        "app.properties is missing from the JAR");
            }
            properties.load(input);
        }

        System.out.println(
                "Jar task demo: " + properties.getProperty("message"));
    }
}
```

File `src/main/resources/app.properties`:

```properties
message=hello
```

You can add an internal class to see the effect of exclude:

File `src/main/java/demo/internal/Secret.java`:

```java
package demo.internal;

public class Secret {
}
```

Build the archives:

```bash
gradle clean jar demoJar sourcesJar javadocJar
```

Generated artifacts:

```text
build/libs/sample-app-1.2.3.jar
build/libs/jar-task-demo-1.2.3-demo.jar
build/libs/jar-task-demo-1.2.3-sources.jar
build/libs/jar-task-demo-1.2.3-javadoc.jar
```

Inspect contents and run:

```bash
jar --list --file build/libs/sample-app-1.2.3.jar
java -jar build/libs/sample-app-1.2.3.jar
```

Exact stdout:

```text
Jar task demo: hello
```

The main JAR contains `demo/Main.class`, `demo/internal/Secret.class`, and `app.properties`. The custom `demoJar` only contains paths matching `demo/**` after applying the exclude; `demo/internal/Secret.class` does not appear in this archive.

Manifest of the main JAR:

```text
Manifest-Version: 1.0
Main-Class: demo.Main
Implementation-Title: Sample App
Implementation-Version: 1.2.3
```

This example was built using Gradle 9.2.1 on OpenJDK Zulu 24.0.2; Java sources were compiled with `--release 17`. The `jar`, `demoJar`, `sourcesJar`, and `javadocJar` tasks all completed. `java -jar` printed `Jar task demo: hello`.

## 21. Common errors when working with the Jar task

| Symptom | Common cause | Resolution |
|---|---|---|
| `jar` task not found | Java Plugin or appropriate JVM plugin not applied | Add `plugins { id 'java' }` |
| No JAR after build | Task did not run or source set has no output | Run `gradle jar --info` and inspect the task graph |
| JAR missing resources | Resources placed in the wrong source directory or excluded by include/exclude | Place files in `src/main/resources` and inspect with `jar tf` |
| `no main manifest attribute` | Manifest is missing `Main-Class` | Add `manifest { attributes('Main-Class': '...') }` |
| `Could not find or load main class` | Wrong package/class name or class not in archive | Check manifest and class path inside the JAR |
| `NoClassDefFoundError` | Regular JAR does not contain runtime dependencies | Use runtime classpath, Application Plugin, or fat JAR |
| `File already exists` or duplicate path | Multiple sources contribute the same entry to the archive | Identify duplicate sources and configure an appropriate duplicates strategy |
| Resource unreadable at runtime | Code uses the wrong path or file was not packaged | Use classpath resources and verify entries in the JAR |
| Archive name collision | Multiple tasks share the same destination and filename | Assign a distinct classifier or archiveFileName |
| JAR hash differs between builds | Unstable timestamps, entry order, or build inputs | Use reproducible defaults, pin toolchain, and remove changing metadata |
| Invalid signature | JAR contents modified after signing or fat JAR retained old signatures | Package completely before signing; strip old signatures when merging dependencies |
| ServiceLoader cannot find provider | Service descriptor dropped by duplicate strategy | Merge `META-INF/services` instead of dropping duplicates |
| Task does not re-run | Gradle considers inputs/outputs still up-to-date | Check task inputs, outputs, and build script changes |
| Module fails to resolve | Incorrect module descriptor or module path | Inspect `module-info.class` and `jar --describe-module` |

## 22. Practical workflow when modifying JAR packaging

When a requirement to change packaging arises, follow this order:

1. Determine whether the target artifact is a library JAR, executable JAR, fat JAR, or distribution.
2. Check existing plugins and tasks: `gradle tasks --all`.
3. Identify the source sets/outputs to package.
4. Choose the filename, version, classifier, and destination.
5. Configure the manifest if an entry point or metadata is needed.
6. Include or exclude resources using CopySpec.
7. Check duplicate entries and dependency packaging.
8. Keep the archive reproducible and task inputs/outputs explicit.
9. Build the artifact using the appropriate task.
10. List contents, inspect the manifest, and test running in an environment close to deployment.
11. If publishing, check classifiers, dependency metadata, and signatures.

Do not use a single JAR for every need when artifact structures differ. A library JAR should preserve dependency metadata for consumers to resolve dependencies; a CLI app may need a distribution; a fat JAR needs clear policies for duplicates, service descriptors, and signatures.

## 23. Summary

The Gradle `Jar` task packages production classes and resources into a Java Archive. The Java Plugin provides the `jar` task and wires it to `assemble`. You can customize the manifest, artifact name, classifier, destination, include/exclude rules, and create additional custom Jar tasks.

Key points to remember:

- `jar` packages the output of the main source set by default; test output is not included.
- `archiveBaseName`, `archiveVersion`, `archiveClassifier`, and `destinationDirectory` determine the archive's name and location.
- `manifest` declares `Main-Class` for running with `java -jar`.
- Regular JARs do not automatically embed runtime dependencies.
- `withSourcesJar()` and `withJavadocJar()` create additional artifacts for libraries.
- Use `duplicatesStrategy` intentionally, especially when creating a fat JAR.
- Gradle 9 and later create archives with stable entry ordering and without preserving source file timestamps by default.
- Use the Application Plugin when distributing an app with its dependencies and launch scripts.
- Verify artifacts using `jar --list`, manifest inspection, `java -jar`, and appropriate module/signing tools.
- Configure tasks via the Provider API so Gradle manages dependencies, incremental builds, and caching.

**Official references:**

- [Gradle User Manual — Building Java & JVM Projects](https://docs.gradle.org/current/userguide/building_java_projects.html)
- [Gradle DSL — Jar](https://docs.gradle.org/current/dsl/org.gradle.jvm.tasks.Jar.html)
- [Gradle DSL — AbstractArchiveTask](https://docs.gradle.org/current/dsl/org.gradle.api.tasks.bundling.AbstractArchiveTask.html)
- [Gradle User Manual — Application Plugin](https://docs.gradle.org/current/userguide/application_plugin.html)
- [Gradle User Manual — Java Library Plugin](https://docs.gradle.org/current/userguide/java_library_plugin.html)
- [Gradle User Manual — Maven Publish Plugin](https://docs.gradle.org/current/userguide/publishing_maven.html)
- [Gradle User Manual — Reproducible Archives and Security Best Practices](https://docs.gradle.org/current/userguide/best_practices_security.html)
- [Oracle Java SE 24 — The jar Command](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jar.html)
- [Oracle Java SE 24 — JAR File Specification](https://docs.oracle.com/en/java/javase/24/docs/specs/jar/jar.html)

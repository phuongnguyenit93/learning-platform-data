# Packaging Java Applications with JAR

**JAR (Java Archive)** is a ZIP-based archive format used to package Java classes, resources, metadata, and sometimes dependencies into a distributable artifact. JAR helps bundle application components into a single file with a clear version, making it easy to store in an artifact repository, upload to a server, verify checksums, and deploy via CI/CD.

A JAR file can be a library for other projects to use or an application that can be run with the Java command. To run with `java -jar app.jar`, the JAR must declare an entry point in its manifest using the `Main-Class` attribute, and that class must have a `public static void main(String[] args)` method. However, having `Main-Class` does not mean the JAR contains every library the application needs.

This lesson walks through JAR structure, manual compilation and packaging with JDK 17+, manifests, resources, dependencies, Maven, Gradle, modular JARs, verification, and artifact publishing.

## 1. What Is a JAR and What Is It Used For?

A JAR is an archive file with the `.jar` extension. Structurally, it follows the ZIP format and adds Java conventions such as the `META-INF` directory, a manifest, and module metadata.

JARs are commonly used for three purposes:

- **Library JAR:** contains classes and resources for other applications to declare as a dependency.
- **Executable JAR:** has an entry point to launch with `java -jar app.jar`.
- **Distribution artifact:** a JAR accompanied by libraries, launch scripts, sample configuration files, or documentation in a release directory/ZIP.

A JAR is not a native executable file. The operating system does not run a JAR directly like an EXE file; a Java runtime is required, and it must be launched using the Java launcher.

A JAR can be distributed independently, but the application still needs a compatible Java runtime. If the bytecode is compiled for Java 17, a runtime older than Java 17 cannot run that class directly.

## 2. Internal Structure of a JAR

A typical JAR might contain:

```text
hello.jar
├── META-INF/
│   └── MANIFEST.MF
└── com/
    └── example/
        └── hello/
            └── App.class
```

Meaning:

- `META-INF/MANIFEST.MF`: the primary metadata of the archive, including manifest version, main class, classpath, or build information.
- `com/example/hello/App.class`: bytecode of the Java class belonging to the `com.example.hello` package.
- Resources such as `config/app.properties` or `messages/messages_vi.properties` can reside at other paths within the archive.
- `META-INF/services/` can contain provider declaration files for Java ServiceLoader.
- A modular JAR can contain `module-info.class` at the root of the archive.

Entry paths in a JAR use forward slashes `/` even when built on Windows. Package names map to directories: `com.example.hello` becomes `com/example/hello/`.

A JAR is not required to contain source code. A Source JAR is a separate artifact, usually suffixed with `-sources.jar`; a Javadoc JAR is also typically a separate artifact suffixed with `-javadoc.jar`.

## 3. Common Packaging Types

| Artifact Type | Contents | How to Run/Use |
|---|---|---|
| Library JAR | Library classes and resources | Added to the compile/runtime classpath of another application |
| Thin executable JAR | Application classes and manifest | Run with dependencies provided outside the JAR |
| Fat/Uber JAR | Application classes and dependencies packaged into one archive | Usually run directly with `java -jar` |
| Application distribution | JAR, separate libraries, and launch script | Extract, configure, then run the script or classpath |
| Modular JAR | Classes and `module-info.class` | Run on the module path or used as a module |

There is no single type that fits every project. A library should generally not bundle all of its dependencies into a fat JAR because that easily causes version conflicts with consuming applications. Applications deployed as services can use a fat JAR or a distribution containing separate libraries. CLI tools may need a launch script to configure the JVM and classpath.

## 4. Preparing a Minimal Java Project

Create the structure:

```text
jar-demo/
├── src/
│   └── main/
│       └── java/
│           └── com/
│               └── example/
│                   └── hello/
│                       └── App.java
├── out/
└── dist/
```

File `src/main/java/com/example/hello/App.java`:

```java
package com.example.hello;

public class App {
    public static void main(String[] args) {
        String target = args.length == 0 ? "local" : args[0];

        System.out.println("Hello from executable JAR");
        System.out.println("Target: " + target);
    }
}
```

The class has an explicit package and a valid main method. The fully qualified class name is `com.example.hello.App`. This value will be declared in the manifest.

## 5. Compiling Classes Before Packaging

A JAR contains bytecode, so the source code must be compiled into `.class` files first.

At the project root directory, create the output directories:

```sh
mkdir -p out dist
```

Compile with JDK 17:

```sh
javac --release 17 -d out src/main/java/com/example/hello/App.java
```

Explanation:

- `javac` is the Java compiler.
- `--release 17` compiles targeting the Java 17 language/API; the compiler also checks that APIs belong to Java 17.
- `-d out` specifies the directory for class output.
- Source paths can include multiple Java files if the application has multiple classes.

After this command, the file is created at:

```text
out/
└── com/
    └── example/
        └── hello/
            └── App.class
```

If the project uses multiple source files, you can pass the list of files to `javac` or use a build tool to manage source sets and dependencies. Do not put `.java` files directly into the JAR in place of bytecode if the goal is to run the application.

## 6. Creating an Executable JAR with the jar Tool

The JDK includes the `jar` tool to create, update, list, and inspect archives.

Create a JAR with Main-Class:

```sh
jar --create --file dist/hello.jar --main-class com.example.hello.App -C out .
```

Parameters:

- `--create`: creates a new archive.
- `--file dist/hello.jar`: destination file name.
- `--main-class com.example.hello.App`: writes the startup class into the manifest.
- `-C out .`: changes the working directory of the `jar` tool to `out` and adds all contents of that directory to the archive.

This command generates a manifest automatically. There is no need to create a manifest file manually if you only need a simple `Main-Class`.

Run the application:

```sh
java -jar dist/hello.jar
```

Stdout:

```text
Hello from executable JAR
Target: local
```

Pass an argument:

```sh
java -jar dist/hello.jar production
```

Stdout:

```text
Hello from executable JAR
Target: production
```

Arguments appearing after the JAR name are passed into `main(String[] args)`. When running via a service manager or container, these arguments can be configured in the command/entrypoint.

## 7. Running a JAR and Distinguishing Launcher Commands

There are two common ways to run:

**Run using Main-Class in the manifest:**

```sh
java -jar dist/hello.jar
```

**Run a class using the classpath:**

```sh
java -cp dist/hello.jar com.example.hello.App
```

Differences:

- `java -jar` requires the manifest to have `Main-Class` and uses that class as the entry point.
- `java -cp` or `java --class-path` specifies where the launcher looks for classes; the classpath is followed by the class name to run.
- When using `-jar`, external classpath settings such as `-cp` and the `CLASSPATH` variable are ignored. Additional dependencies must be declared appropriately, such as via manifest `Class-Path` or a fat JAR.
- When running with classpath, the main class must be specified on the command line.

Do not confuse `jar` (the packaging tool) with `java` (the launcher that runs the program).

## 8. Inspecting JAR Contents and Manifest

List entries in the archive:

```sh
jar --list --file dist/hello.jar
```

Sample output:

```text
META-INF/
META-INF/MANIFEST.MF
com/
com/example/
com/example/hello/
com/example/hello/App.class
```

Entry order may vary depending on the tool and how the archive was created. What needs to be confirmed is that the class is at the right package path and the manifest is present.

Read the manifest:

```sh
unzip -p dist/hello.jar META-INF/MANIFEST.MF
```

Or extract the archive to inspect its contents:

```sh
jar --extract --file dist/hello.jar --dir inspect
```

After extracting, inspect `inspect/META-INF/MANIFEST.MF` and the class paths.

You can use `javap` to view bytecode/class signatures:

```sh
javap -classpath dist/hello.jar com.example.hello.App
```

Inspecting the artifact before release helps detect missing classes, wrong packages, missing resources, or an incorrect manifest.

## 9. Creating a Manifest Manually

A manifest is a text file in the Java Manifest format. It is located at `META-INF/MANIFEST.MF` inside the JAR.

Example `manifest.mf` file:

```text
Manifest-Version: 1.0
Main-Class: com.example.hello.App
Implementation-Title: Hello Application
Implementation-Version: 1.0.0

```

The manifest has formatting rules:

- Each attribute has the form `Name: Value`.
- The main section ends with a blank line.
- The file should end with a newline.
- Attribute names and values must conform to the manifest specification.
- Long lines are handled by the `jar` tool according to manifest continuation rules; if creating the file manually, avoid arbitrarily splitting in the middle of an attribute.

Package with the manifest:

```sh
jar --create --file dist/hello.jar --manifest manifest.mf -C out .
```

When the manifest already declares `Main-Class`, you do not need to also pass `--main-class`. Avoid declaring two different `Main-Class` values.

Other metadata attributes such as `Implementation-Title` and `Implementation-Version` help operations tools identify the artifact. Do not put secrets, passwords, or tokens into the manifest because the manifest can be read by anyone who has the JAR file.

## 10. Main-Class and Requirements to Run with java -jar

The `Main-Class` attribute must contain the fully qualified class name, without the `.class` suffix:

```text
Main-Class: com.example.hello.App
```

The specified class must have a valid entry point method, for example:

```java
public static void main(String[] args)
```

If `Main-Class` is missing, the launcher may report:

```text
no main manifest attribute, in dist/hello.jar
```

If the class name is declared incorrectly, the launcher typically reports that it could not find or load the main class. Check:

1. Package name in the source.
2. Class path inside the JAR.
3. `Main-Class` value in the manifest.
4. Whether the class was compiled and packaged.
5. Whether the bytecode is compatible with the Java runtime.

A library JAR does not need a `Main-Class`. Do not add a dummy main class just so every JAR can be run with `java -jar`.

## 11. Packaging Resources

Resources are data the application needs at runtime, such as properties files, templates, schemas, public certificates, images, or message bundles.

With a standard project layout, place resources in:

```text
src/main/resources/
└── config/
    └── app.properties
```

Contents of `src/main/resources/config/app.properties`:

```properties
app.name=Jar Demo
app.environment=local
```

When building manually, copy resources into the output directory before creating the JAR:

```sh
cp -R src/main/resources/. out/
jar --create --file dist/hello.jar --main-class com.example.hello.App -C out .
```

When using Maven or Gradle, the build tool usually copies resources from standard source sets into the output automatically.

Read a resource from the classpath:

```java
import java.io.IOException;
import java.io.InputStream;
import java.util.Properties;

public class ResourceReader {
    public static void main(String[] args) throws IOException {
        Properties properties = new Properties();

        try (InputStream input =
                ResourceReader.class.getResourceAsStream(
                        "/config/app.properties")) {
            if (input == null) {
                throw new IllegalStateException(
                        "Missing resource: config/app.properties");
            }
            properties.load(input);
        }

        System.out.println("app.name=" + properties.getProperty("app.name"));
        System.out.println("app.environment="
                + properties.getProperty("app.environment"));
    }
}
```

Stdout when the resource is packaged properly:

```text
app.name=Jar Demo
app.environment=local
```

Do not use `Path.of("config/app.properties")` to read a resource inside a JAR as if it were a regular file on the filesystem. Use a classpath resource API such as `getResourceAsStream`. If a resource needs to be modified at runtime, store the runtime copy outside the JAR in a dedicated configuration/data directory.

## 12. External Dependencies and Thin JARs

A JAR created from the application's compiled classes usually contains only the project's classes/resources. It does not automatically include libraries used during compilation.

For example, suppose a project uses a logging library or HTTP client. If you only package the application's classes into `app.jar` and run `java -jar app.jar`, the runtime may throw `NoClassDefFoundError` or `ClassNotFoundException` when a dependency class is needed.

A thin JAR is an artifact containing only the application, while dependencies live outside. It can be run with a classpath:

Linux/macOS:

```sh
java -cp "app.jar:lib/*" com.example.hello.App
```

Windows:

```powershell
java -cp "app.jar;lib/*" com.example.hello.App
```

The classpath separator is a colon on Unix-like OSes and a semicolon on Windows. The `lib/*` wildcard is supported by the Java launcher to add JARs in the `lib` directory to the classpath.

When using classpath, specify the main class at the end of the command. Do not use `-jar` in the same command intending to supplement it with `-cp` because external classpaths are ignored when `-jar` is used.

## 13. Manifest Class-Path for Dependencies Outside the JAR

An executable JAR can declare external dependencies using the `Class-Path` attribute in the manifest.

Example layout:

```text
release/
├── app.jar
└── lib/
    ├── commons-text.jar
    └── logging.jar
```

Manifest of `app.jar`:

```text
Manifest-Version: 1.0
Main-Class: com.example.hello.App
Class-Path: lib/commons-text.jar lib/logging.jar

```

The `Class-Path` value consists of URLs relative to the location of the JAR containing the manifest. When moving the entire `release` directory to another machine, preserve the relative structure so the launcher can find the dependencies.

Manifest `Class-Path` does not support classpath wildcards. List the required dependencies in URL format and in the appropriate order.

The advantage is that you can run:

```sh
java -jar release/app.jar
```

The disadvantage is that you must distribute the exact directory structure and dependency list. If a `lib` file is missing or has the wrong version, the application still fails to start.

## 14. Fat JAR or Uber JAR

A Fat JAR (also known as an Uber JAR) packages the application classes together with its dependencies into a single archive. This is a popular choice for small services or applications deployed as a single file.

Advantages:

- Easy to upload and manage a single artifact.
- Simple launch command.
- Less reliance on an external `lib` directory structure.
- Convenient for container images when only a single file needs to be copied.

Disadvantages:

- Larger artifact size.
- Dependencies may have class/resource conflicts.
- Service loader metadata must be merged properly.
- Dependency signatures may become invalid after unpacking/repackaging.
- Upgrading a single dependency usually requires rebuilding the entire fat JAR.
- Fat JARs should not be used as the default for libraries.

Do not simply unpack all dependencies and zip them back together with a basic command without handling duplicate resources, service descriptors, module metadata, and signature files in `META-INF`. Use a dedicated, well-tested plugin.

## 15. Packaging with Maven

Maven uses lifecycles and plugins to compile, test, package, and produce a JAR. With the standard layout, sources live in `src/main/java`, resources in `src/main/resources`, and artifacts are created in `target`.

Minimal `pom.xml` example:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>hello</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
                <configuration>
                    <archive>
                        <manifest>
                            <mainClass>com.example.hello.App</mainClass>
                        </manifest>
                        <manifestEntries>
                            <Implementation-Title>Hello Application</Implementation-Title>
                            <Implementation-Version>1.0.0</Implementation-Version>
                        </manifestEntries>
                    </archive>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

Build the JAR:

```sh
mvn clean package
```

Artifact:

```text
target/hello-1.0.0.jar
```

Run:

```sh
java -jar target/hello-1.0.0.jar
```

The Maven JAR Plugin adds `Main-Class` to the manifest. By default, the JAR does not automatically bundle runtime dependencies inside; Maven manages dependencies on the build classpath. If you need an executable package with dependencies, choose the Maven Shade Plugin or create an appropriate distribution and inspect the result after packaging.

Do not let plugin versions vary across developer machines. Pin plugin versions in the POM or parent build so CI and local builds behave consistently.

## 16. Packaging with Gradle

The Gradle Java Plugin provides the `jar` task. The Application Plugin adds ways to run the application and create a distribution with launch scripts and runtime libraries.

Example `build.gradle.kts`:

```kotlin
plugins {
    application
}

group = "com.example"
version = "1.0.0"

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

application {
    mainClass.set("com.example.hello.App")
}

tasks.jar {
    manifest {
        attributes["Main-Class"] = "com.example.hello.App"
        attributes["Implementation-Version"] = project.version
    }
}
```

Build the JAR:

```sh
./gradlew clean jar
```

The artifact is typically at:

```text
build/libs/<project-name>-1.0.0.jar
```

Run the application using the runtime classpath managed by Gradle:

```sh
./gradlew run --args="production"
```

Create an application distribution:

```sh
./gradlew installDist
./gradlew distZip
```

`installDist` creates a distribution directory containing launch scripts and runtime libraries; `distZip` creates a ZIP distribution. This is often the right choice when an application needs many dependencies without bundling them all into a single fat JAR.

The default `jar` task does not automatically embed all runtime dependencies. If you need a fat JAR in Gradle, you can use a plugin like the Shadow Plugin, pin the plugin version, and verify the resource/service descriptor merge rules.

## 17. Comparing Maven, Gradle, and the jar Tool

| Tool | Best When | Key Points to Remember |
|---|---|---|
| JDK jar tool | Small projects, learning archive structure, or manual packaging | Manually manage compilation, resources, and dependencies |
| Maven JAR Plugin | Projects using the Maven lifecycle | `Main-Class` can be configured in manifest; dependencies are not embedded automatically |
| Gradle Java/Application Plugin | Projects using Gradle needing build/run/distribution tasks | `jar` builds the artifact; Application Plugin provides `installDist`/`distZip` |
| Shade/Shadow plugin | Needing a single fat/uber JAR | Must handle resources, service metadata, and dependency conflicts |
| jpackage | Needing a platform-specific installer or application image | This is a native distribution/installer, not a way to create a JAR |

Choose the tool based on how the project manages dependencies, build lifecycle, and deployment target. Do not mix multiple packaging mechanisms in a single pipeline without defining which artifact is the official output.

## 18. Modular JARs and module-info.java

Starting with the Java Platform Module System, a module can declare its descriptor in a `module-info.java` file. When compiled, `module-info.class` is placed at the root of the output and packaged into the JAR.

Example `src/main/java/module-info.java`:

```java
module com.example.hello {
    exports com.example.hello;
}
```

Compile:

```sh
javac --release 17 -d out src/main/java/module-info.java src/main/java/com/example/hello/App.java
```

Package:

```sh
jar --create --file dist/hello-module.jar --main-class com.example.hello.App -C out .
```

View the module descriptor:

```sh
jar --describe-module --file dist/hello-module.jar
```

You can run the module on the module path:

```sh
java --module-path dist/hello-module.jar --module com.example.hello/com.example.hello.App
```

A modular JAR is still a JAR. The difference is that the module has a name and explicit dependency/export declarations. If running a module without a main class in its descriptor, you can specify the main class using the `module/class` syntax at launch time.

Not every JAR is a named module. A JAR without a module descriptor can be treated as an automatic module on the module path according to module naming rules; the derived name may be unstable if the file name is not carefully managed.

## 19. JAR Signing and Signature Verification

A JAR can be signed using the `jarsigner` tool. Signing lets recipients verify the integrity of signed entries and the signer certificate according to a trust policy.

Example signing command (using a securely provisioned keystore and alias):

```sh
jarsigner -keystore release-keystore.p12 -storetype PKCS12 dist/hello.jar release-key
```

Verify:

```sh
jarsigner -verify -verbose -certs dist/hello.jar
```

The verify command checks entry signatures according to the JAR signing mechanism. To trust the signer's identity, you must also verify the certificate chain, fingerprint, validity period, revocation policy, and trust store according to your organization's procedures.

Do not put keystore passwords in source code or command logs. In CI, use a signing service or secret store, restrict permissions, and audit signing operations.

Signing a JAR modifies the bytes of the archive. If publishing both a checksum and a signature, compute the checksum of the final artifact after the signing step.

## 20. Checking JAR Version and Compatibility

Before releasing, clearly identify:

- The JDK used to compile.
- The Java release/target supported by the bytecode.
- The minimum JRE required to run.
- Dependency versions and runtime scopes.
- Operating system/architecture if the artifact has native components.
- Module path or classpath.
- How configuration and secrets are passed at runtime.

Check the environment's Java versions:

```sh
java --version
javac --version
jar --version
```

If compiling with JDK 21 while targeting release 17, use `--release 17` so the compiler checks Java 17 APIs. Merely setting `-source 17 -target 17` without restricting the API can accidentally reference newer APIs than the target runtime supports.

If a dependency requires a newer Java version than the application's target, the entire application may still fail to run on the older runtime. Verify dependency and bytecode compatibility in release tests.

## 21. Runtime Configuration Considerations

Do not bundle passwords, tokens, database URLs with credentials, or production secrets into a JAR. JARs are often stored in artifact repositories, CI caches, container images, and deployment hosts; many people can download or inspect them.

Runtime configuration should come from:

- Environment variables managed by the deployment platform.
- A secret manager or credential provider.
- External configuration files with appropriate permissions.
- JVM system properties for non-sensitive values.
- A config service with authentication and authorization.

A JAR should be able to run in multiple environments without rebuilding just to change a URL or password. Separating the immutable artifact from environment-specific configuration makes releases easier to test and roll back.

If default resources are included in the JAR, you can allow overriding them with an external configuration file. Precedence rules should be documented, for example: command-line option > environment variable > external config > packaged default.

## 22. Checking a JAR Before Release

A minimal smoke test workflow:

1. Build the artifact from the intended source commit.
2. List contents using `jar --list`.
3. Read the manifest and confirm `Main-Class`/version.
4. Confirm required resources are present in the archive.
5. Run with the exact target Java runtime.
6. Run with representative arguments/configuration.
7. Verify runtime dependencies on a clean machine/fresh container.
8. Verify the signature if the release is signed.
9. Compute the SHA-256 of the final artifact.
10. Store the artifact, checksum, version, and commit metadata.

Do not just run `./gradlew run` or `mvn exec:java` and conclude the JAR runs properly. Those tasks may run classes from the build output and dependency classpath without using the actual published JAR artifact. Run the exact final JAR file or distribution in the smoke test.

## 23. Common JAR Packaging Errors

| Symptom | Common Cause | How to Fix |
|---|---|---|
| no main manifest attribute | Missing `Main-Class` in manifest | Configure `Main-Class` or use `--main-class` |
| Could not find or load main class | Wrong package/class name or missing class entry | Check `jar --list` and the manifest |
| NoClassDefFoundError | Runtime dependency is not on the classpath | Provide `lib`, manifest `Class-Path`, or a fat JAR |
| ClassNotFoundException | Wrong classpath or class name | Check `-cp`, package path, and spelling |
| UnsupportedClassVersionError | Runtime is older than the bytecode target | Use a newer runtime or compile with the appropriate `--release` |
| Resource not found | Resource was not copied into the JAR or path is wrong | Check `src/main/resources` and `jar --list` |
| Runs in IDE but fails via JAR | IDE provides dependencies/resources outside the artifact | Smoke test the artifact in a clean environment |
| Runs with `-cp` but fails with `-jar` | Missing or incorrect manifest `Main-Class`/`Class-Path` | Check the manifest; remember `-jar` ignores external `-cp` |
| Fat JAR ServiceLoader failure | `META-INF/services` was overwritten instead of merged | Configure a transformer/service resource merge |
| Signed JAR fails verification | Archive was modified after signing or signature metadata is invalid | Sign after the final package step and re-verify |
| JAR runs locally but fails in production | Different runtime/configuration/permissions | Check Java version, env, paths, and dependencies |
| Resource readable in IDE but fails after packaging | Code uses a filesystem path for a resource in the archive | Use a classpath resource API |
| JAR missing classes when run on module path | Incorrect module descriptor or module dependency | Check `module-info` and `--describe-module` |

## 24. Sample JAR Release Pipeline

A CI pipeline might consist of these steps:

```text
Checkout commit
      |
      v
Select JDK/toolchain
      |
      v
Compile source and process resources
      |
      v
Run unit/integration tests
      |
      v
Package JAR or distribution
      |
      v
Inspect manifest and archive entries
      |
      v
Smoke test the packaged artifact
      |
      v
Sign artifact (if required)
      |
      v
Calculate checksum
      |
      v
Publish immutable versioned artifact
```

Artifacts should have clear names and versions, for example `orders-service-2.4.0.jar`. Avoid overwriting an already published version; if rebuilding, use a new version/release process or distinguishing metadata.

Store audit information alongside the artifact: source commit, build number, JDK/build tool version, dependency lock/verification state, test results, checksum, and signature/provenance if available.

## 25. Checklist

- [ ] Understand that a JAR is a ZIP archive with Java conventions.
- [ ] Distinguish between library JAR, executable JAR, thin JAR, fat JAR, and distribution.
- [ ] Create a project with a clear package and source layout.
- [ ] Compile with an appropriate JDK and release target.
- [ ] Create the JAR using the `jar` tool or a build tool.
- [ ] Declare `Main-Class` accurately if `java -jar` is needed.
- [ ] Inspect `META-INF/MANIFEST.MF`.
- [ ] Package resources and read them via classpath APIs.
- [ ] Understand that dependencies do not automatically appear in a thin JAR.
- [ ] Choose an appropriate classpath, manifest `Class-Path`, fat JAR, or distribution.
- [ ] Configure Maven/Gradle plugin versions and the Java toolchain.
- [ ] Check `module-info` if using JPMS.
- [ ] Verify the JAR on the target runtime.
- [ ] Smoke test the actual artifact after packaging.
- [ ] Sign the artifact if required by the release policy.
- [ ] Compute the checksum after the signing step.
- [ ] Keep secrets outside the artifact.
- [ ] Store version, commit, and build metadata.

## 26. References

- Oracle Java SE 17 — The jar Command: https://docs.oracle.com/en/java/javase/17/docs/specs/man/jar.html
- Oracle Java SE 17 — The java Command: https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html
- Oracle Java SE 17 — JAR File Specification: https://docs.oracle.com/en/java/javase/17/docs/specs/jar/jar.html
- Oracle Java SE 17 — JAR Manifest: https://docs.oracle.com/en/java/javase/17/docs/specs/jar/jar.html#jar-manifest
- Oracle Java SE 17 — jarsigner: https://docs.oracle.com/en/java/javase/17/docs/specs/man/jarsigner.html
- Apache Maven JAR Plugin — Usage: https://maven.apache.org/plugins/maven-jar-plugin/usage.html
- Gradle User Manual — The Application Plugin: https://docs.gradle.org/current/userguide/application_plugin.html
- Gradle User Manual — Building Java Projects: https://docs.gradle.org/current/userguide/building_java_projects.html

JAR packaging is the step that turns bytecode and resources into an inspectable, distributable, and deployable artifact. Declare the right entry point, verify the manifest and resources, provide dependencies with a clear strategy, and smoke test the actual artifact after packaging. Maven/Gradle help automate the workflow, while checksums, signatures, and metadata make releases traceable and verifiable.
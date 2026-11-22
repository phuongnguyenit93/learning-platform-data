# Plain JAR, Executable JAR, and Launcher Configuration

When migrating a Java application from an older JDK to a newer JDK, a successful compilation does not guarantee that the release can start. The JAR file might be missing `Main-Class`, the runtime libraries might differ from compile time, the wrong JVM version might be selected, the classpath might be configured differently in a container, or the launcher might pass `-D` and `-Xmx` options in the wrong position. An application that runs well in an IDE can still fail when deployed under Linux systemd, a Windows Service, or a clean container.

To handle the problem systematically, you need to distinguish three concepts:

- **Plain JAR (library JAR):** an archive containing Java classes and resources, used as a library or component of an application; it does not necessarily have an entrypoint.
- **Executable JAR:** a JAR with entrypoint metadata, commonly `Main-Class` in the manifest, which can be launched with `java -jar` when dependencies and the runtime are adequately provided.
- **Launcher:** a command, script, or program that selects the Java executable, classpath/module path, JVM options, working directory, environment, and how the process is operated.

In Java Advance Compatibility Migration, all three layers can change when upgrading the JDK, Maven/Gradle, framework, or operating system. The goal is to produce an artifact **with a deterministic structure and explicit dependencies that can run with the target runtime, be monitored, and be rolled back safely**.

## 1. What is a JAR?

A JAR (Java Archive) is an archive based on the ZIP format with conventions tailored for the Java ecosystem. A JAR can contain:

~~~text
catalog-api.jar
├── META-INF/
│   ├── MANIFEST.MF
│   └── services/
│       └── com.acme.spi.CatalogProvider
├── com/
│   └── acme/
│       └── catalog/
│           ├── CatalogClient.class
│           └── CatalogResult.class
└── com/acme/catalog/messages.properties
~~~

- `.class`: compiled bytecode.
- `.properties`, XML, JSON, images, schemas: resources for the application to read.
- `META-INF/MANIFEST.MF`: metadata describing the archive.
- `META-INF/services`: service provider information for the classpath mechanism.
- `module-info.class`: module descriptor for an explicit modular JAR.
- Other signature/metadata entries, depending on packaging.

**The `.jar` extension does not tell you which JDK version created the JAR, whether it has a `main` class, or whether it has bundled all dependent libraries inside.**

You can list the contents of a JAR with:

~~~bash
jar --list --file dist/catalog-api.jar
~~~

With older JDK tools, the traditional syntax is also commonly used:

~~~bash
jar tf dist/catalog-api.jar
~~~

Read the output to verify that classes are placed under the paths corresponding to their packages, resources are packaged, and the manifest is actually in the right location.

## 2. Plain JARs Do Not Need Main-Class

A library containing the class:

~~~java
package com.acme.catalog;

public final class CatalogClient {
    public String findName(String code) {
        return "Product " + code;
    }
}
~~~

has no mandatory reason to have `public static void main(String[] args)`. It is used by another project via a Maven/Gradle dependency or the classpath/module path.

Suppose a JAR has a main class, but its manifest does **not** declare an entrypoint; you can launch that class directly via the classpath:

~~~bash
java -cp dist/app-plain.jar com.acme.app.Main
~~~

Conversely, the command:

~~~bash
java -jar dist/app-plain.jar
~~~

may report:

~~~text
no main manifest attribute, in dist/app-plain.jar
~~~

This is usually a **launch mode** selection error, not an indication that the archive is corrupted. You must distinguish *a JAR that contains a main class* from *a JAR that declares a main class in its manifest*.

## 3. Creating a Plain JAR from Source Code

Source code example:

~~~java
package com.acme.app;

public final class Main {
    public static void main(String[] args) {
        System.out.println("Application started");
        System.out.println("Number of args = " + args.length);
    }
}
~~~

With a modern JDK, you can compile and package it on a Unix-like shell:

~~~bash
mkdir -p build/classes dist

javac -d build/classes \
  src/main/java/com/acme/app/Main.java

jar --create --file dist/app-plain.jar \
  -C build/classes .
~~~

Verify:

~~~bash
jar --list --file dist/app-plain.jar
java -cp dist/app-plain.jar com.acme.app.Main demo
~~~

`-C build/classes .` tells the JAR tool to take contents from the directory containing the compiled classes so that the archive root starts at the package path `com/acme/...`.

Keep in mind:

- The compiler must use an appropriate classpath or module path if the application references other libraries.
- Resources from `src/main/resources` must also be copied to the output before packaging if not using an automated build tool.
- A newer JDK may produce classfiles that do not run on an older JVM if the target is not set properly.
- The example focuses on how packaging works, not replacing Maven/Gradle in a large project.

## 4. Executable JAR and Main-Class

A traditional executable JAR has a manifest declaring:

~~~text
Manifest-Version: 1.0
Main-Class: com.acme.app.Main
~~~

When invoking:

~~~bash
java -jar dist/app.jar
~~~

the Java launcher reads `Main-Class` to select the entrypoint and load related classes. You can create the archive using:

~~~bash
jar --create \
  --file dist/app.jar \
  --main-class com.acme.app.Main \
  -C build/classes .
~~~

Or the traditional `jar` tool syntax:

~~~bash
jar cfe dist/app.jar com.acme.app.Main \
  -C build/classes .
~~~

Then:

~~~bash
java -jar dist/app.jar first second
~~~

For the traditional main model, the class needs a valid entrypoint, typically `public static void main(String[] args)`. Newer launch capabilities in certain Java versions should not be assumed if the project still supports older JDKs.

### 4.1. Main-Class Is a Java Class Name, Not a Path

Correct:

~~~text
Main-Class: com.acme.app.Main
~~~

Wrong:

~~~text
Main-Class: com/acme/app/Main.class
Main-Class: Main.java
Main-Class: dist/app.jar
~~~

If code changes its package while the manifest remains unchanged, `Could not find or load main class` may appear. Check the archive and compiled class names, not just source file names.

### 4.2. Main-Class Does Not Bundle Dependencies

Even when `java -jar` finds the right main class, a call such as `new HttpClientImpl()` can fail because the JAR containing the application does not have the HTTP client library at runtime. In that case, the error belongs to classpath/packaging, not the manifest entrypoint.

## 5. Understanding Manifest Metadata Properly

The manifest is typically located at:

~~~text
META-INF/MANIFEST.MF
~~~

An example:

~~~text
Manifest-Version: 1.0
Main-Class: com.acme.app.Main
Implementation-Title: Order Service
Implementation-Version: 2.0.0
Class-Path: lib/http-client.jar lib/json-codec.jar
~~~

| Attribute | Purpose |
|---|---|
| `Manifest-Version` | Manifest format version |
| `Main-Class` | Entrypoint for `-jar` mode |
| `Class-Path` | Declares additional classpath entries per JAR manifest rules |
| `Implementation-Version` | Release metadata; does not replace dependency versioning |
| `Implementation-Title` | Component name metadata |
| `Automatic-Module-Name` | Sets a stable name for an automatic module when applicable |
| `Multi-Release` | Marks a multi-release JAR per the Java specification |

Some frameworks add their own attributes; for example, Spring Boot uses metadata about the application start class. **Not every attribute present in a manifest is interpreted directly by the JVM launcher**.

### 5.1. Manifest Format Has Specific Rules

A manifest is not an arbitrary text file: attribute syntax, line breaks, continuation lines, and encoding must follow the JAR file specification. When authoring a manifest file, let the build/JAR tool generate the proper structure rather than concatenating strings manually.

Example when you already have a valid custom manifest:

~~~bash
jar --create \
  --file dist/app.jar \
  --manifest custom-manifest.mf \
  -C build/classes .
~~~

After creation, inspect the **manifest inside the output JAR**, because a correct source file does not prove the final packaged artifact has the corresponding content.

## 6. Classpath of a Standard Application

The classpath is the list of locations that the Java launcher and class loaders use to find classes/resources in classpath mode.

Linux/macOS:

~~~bash
java -cp "dist/app.jar:dist/lib/*" \
  com.acme.app.Main
~~~

Windows PowerShell:

~~~powershell
java -cp "dist\app.jar;dist\lib\*" com.acme.app.Main
~~~

Notes:

- On Unix, classpath entries are typically separated by `:`.
- On Windows, they are separated by `;`.
- The wildcard `lib/*` in a command-line classpath can include JARs directly inside that directory according to Java launcher rules.
- Quoting prevents the shell from expanding `*` itself and handles paths with spaces properly.
- Do not rely on wildcard expansion order to pick a dependency version when duplicate classes exist.

### 6.1. Classpath Root Must Be the Correct Directory

If the compiled class is located at:

~~~text
build/classes/com/acme/app/Main.class
~~~

then the correct command when running from the project directory is:

~~~bash
java -cp build/classes com.acme.app.Main
~~~

Do not set `build/classes/com/acme/app` as the root and run `Main` if the class declares `package com.acme.app`.

### 6.2. Compile Classpath Is Not Runtime Classpath

A library can be provided to the compiler yet excluded from runtime due to dependency scope or packaging options. For example, Maven `provided` and Gradle `compileOnly` have different meanings from runtime dependencies.

If compilation succeeds but the Java launcher reports `NoClassDefFoundError`, verify which JARs are actually present at **runtime** and in the right class loader, rather than only checking the IDE dependency list.

## 7. java -jar Does Not Behave Like java -cp

Two typical modes:

~~~bash
java -cp "app.jar:lib/*" com.acme.app.Main
~~~

and:

~~~bash
java -jar app.jar
~~~

differ in how the application classpath and entrypoint are determined. When using `-jar`, do not rely on the `-cp` option or the `CLASSPATH` environment variable to add to the user classpath as in main-class execution mode.

A commonly misleading example:

~~~bash
java -cp "lib/*" -jar app.jar
~~~

This command is not a reliable way to force an executable JAR to use all JARs in `lib/`. Appropriate options include:

1. Run the main class with `-cp` listing runtime dependencies.
2. Declare manifest `Class-Path` in a thin executable JAR when the layout fits.
3. Use a generated launcher/distribution from Maven/Gradle or a framework.
4. Build a shaded/uber JAR or a framework-specific executable archive with a suitable loader.

## 8. Manifest Class-Path for a Thin Executable JAR

Suppose the release layout is:

~~~text
release/
├── app.jar
├── config/
│   └── application.properties
└── lib/
    ├── client-api.jar
    └── json-runtime.jar
~~~

The manifest of `app.jar` can contain:

~~~text
Main-Class: com.acme.app.Main
Class-Path: lib/client-api.jar lib/json-runtime.jar
~~~

Classpath entries in the manifest are typically resolved relative to **the location of the JAR containing the manifest** per JAR specification rules. They do not automatically become paths relative to the shell's current working directory.

Example:

~~~bash
cd /tmp
java -jar /opt/myapp/release/app.jar
~~~

The `lib/client-api.jar` entry is interpreted relative to `/opt/myapp/release/app.jar`, not `/tmp/lib/client-api.jar`.

### 8.1. What Manifest Class-Path Does Not Do

- Does not automatically download Maven dependencies from the internet.
- Does not support classpath wildcards in the same way as `-cp lib/*`.
- Does not turn an artifact into a fat JAR.
- Does not resolve classpath or ClassLoader conflicts.
- Does not guarantee that resource paths inside the application are correct.
- Does not replace module resolution if the application is launched in JPMS mode.

With dozens or hundreds of runtime JARs, a distribution with a launcher script managing the classpath can be easier to maintain than a manually written manifest file.

## 9. Thin JAR, Fat JAR, and Distribution

| Form | Layout | Common Launch Method |
|---|---|---|
| Library JAR | Library classes/resources | Added as an application dependency |
| Thin executable JAR | App classes + Main-Class; external deps | `java -jar` with manifest Class-Path or suitable launcher |
| Classpath distribution | `app.jar` and a separate `lib/` directory | Script running `java -cp ... Main` |
| Shaded/uber JAR | App classes and many dependency classes in one archive | `java -jar` if manifest/merge is correct |
| Spring Boot executable JAR | App classes, nested dependencies, and framework loader | `java -jar` via Spring Boot launcher |
| Modular JAR | Module descriptor + classes | `java --module ...` when running on module path |
| Runtime image | Java runtime and selected modules | Launcher bundled with the image |

**A fat JAR is not a single standard layout.** A shaded JAR merges the contents of JARs into the same archive root; a framework's nested JAR is a different approach with its own loader.

## 10. Benefits and Risks of Shading/Uber JARs

An uber JAR can look like:

~~~text
app-all.jar
├── META-INF/MANIFEST.MF
├── com/acme/app/Main.class
├── org/example/http/Client.class
├── com/fasterxml/.../ObjectMapper.class
└── META-INF/services/...
~~~

Advantage: often convenient to ship without having to carry an entire dependencies directory. However, merge steps can break things:

- **Duplicate classes:** two JARs contain the same binary name.
- **Duplicate resources:** files with the same name overwrite each other.
- **ServiceLoader metadata:** `META-INF/services` loses providers.
- **Signed JAR metadata:** signatures of original archives become invalid when contents change.
- **Module descriptors:** multiple `module-info.class` files cannot be merged into a single valid module by arbitrary copying.
- **Multi-release entries:** JDK-specific versions are dropped or overwritten improperly.
- **Framework discovery:** `spring.factories`, annotation metadata, or resource loaders are lost.
- **License/NOTICE:** dependency copyright information is insufficiently preserved.
- **Native libraries:** extraction and naming collide.

### 10.1. META-INF/services Must Be Merged Properly

Suppose two dependencies contain the same file:

~~~text
META-INF/services/com.acme.spi.ReportFormatter
~~~

Dependency A declares:

~~~text
com.acme.format.CsvFormatter
~~~

Dependency B declares:

~~~text
com.acme.format.JsonFormatter
~~~

If the shaded output keeps only one file, `ServiceLoader` can silently lose a formatter without throwing an immediate error. Maven Shade Plugin has `ServicesResourceTransformer`; Gradle Shadow Plugin has a corresponding service-file merging mechanism. Configure according to the actual plugin version and verify provider discovery at runtime.

### 10.2. Relocation Is a Binary Contract Change

Shading tools can relocate packages to avoid conflicts, but components using reflection, resource paths, serialized class names, or JNI may depend on the original names. Relocation is not unconditionally safe.

If relocation is used, test dynamic class loading, service discovery, and any serialized data surviving from earlier versions.

### 10.3. JAR Signatures

Merging/modifying class files can invalidate signature metadata from the original JARs. Do not carry over old signatures untouched into a modified artifact and assume it is still verified. Release artifact signing and provenance verification workflows must be properly designed; do not work around signature issues by disabling security checks.

## 11. Maven: Adding Main-Class with Maven Jar Plugin

A Maven project typically produces a JAR module using Maven Jar Plugin. If an executable manifest is needed:

~~~xml
<build>
  <plugins>
    <plugin>
      <groupId>org.apache.maven.plugins</groupId>
      <artifactId>maven-jar-plugin</artifactId>
      <version>VERSION_DA_CHON</version>
      <configuration>
        <archive>
          <manifest>
            <mainClass>com.acme.app.Main</mainClass>
          </manifest>
        </archive>
      </configuration>
    </plugin>
  </plugins>
</build>
~~~

`VERSION_DA_CHON` is a placeholder and should be replaced with the plugin version compatible with the project's JDK/Maven. The example illustrates a `pom.xml` snippet, not a complete POM.

~~~bash
./mvnw clean package
java -jar target/app.jar
~~~

The filename `target/app.jar` is illustrative only; check `artifactId`, `version`, and the actual build output configuration.

**Important:** Standard Maven Jar Plugin does not bundle all dependencies into the module JAR. If runtime dependencies are missing, adding `Main-Class` still will not fix the error.

### 11.1. Maven Shade Plugin

If you want a shaded JAR, configure Maven Shade Plugin with transformers for manifest and resource metadata. A typical configuration snippet:

~~~xml
<transformers>
  <transformer
    implementation="org.apache.maven.plugins.shade.resource.ManifestResourceTransformer">
    <mainClass>com.acme.app.Main</mainClass>
  </transformer>
  <transformer
    implementation="org.apache.maven.plugins.shade.resource.ServicesResourceTransformer"/>
</transformers>
~~~

The configuration must be placed within a valid plugin/execution and version. Review duplicate resource handling, JAR signatures, relocation, dependency-reduced POM, and dependency compatibility.

## 12. Gradle: jar and Application Distribution

With Gradle Groovy DSL:

~~~groovy
plugins {
    id 'java'
}

tasks.named('jar') {
    manifest {
        attributes('Main-Class': 'com.acme.app.Main')
    }
}
~~~

This configuration creates a manifest entrypoint for the `jar` task, but it does not automatically pack all runtime dependencies into the archive. That is the difference between **manifest** and **packaging topology**.

### 12.1. Application Plugin

The Gradle Application Plugin supports running the app and creating a distribution with launcher scripts and a libraries directory:

~~~groovy
plugins {
    id 'application'
}

application {
    mainClass = 'com.acme.app.Main'
}
~~~

You can run:

~~~bash
./gradlew run
./gradlew installDist
./gradlew distZip
~~~

The distribution output typically includes a `lib/` directory and scripts under `bin/`. Check the actual output and how your project's plugin/version handles runtime dependencies.

A distribution with a clear launcher classpath is often suitable when the application needs to keep JARs separate or uses custom plugins/module layers.

### 12.2. Gradle Toolchain Differs from User Runtime

~~~groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}
~~~

The toolchain configuration helps Gradle select a JDK for supporting tasks. It does not automatically package JDK 21 with the release. The target machine needs an appropriate runtime or a bundled runtime image.

## 13. Spring Boot Executable JAR Has Its Own Layout

A Spring Boot executable JAR typically has a layout similar to:

~~~text
application.jar
├── META-INF/MANIFEST.MF
├── BOOT-INF/
│   ├── classes/
│   │   └── com/acme/app/Application.class
│   └── lib/
│       ├── spring-*.jar
│       └── other-dependency.jar
└── org/springframework/boot/loader/...
~~~

Dependencies are **nested JARs**, not classes all merged into the root. Spring Boot provides a launcher/loader to read this layout.

The manifest may contain:

~~~text
Main-Class: <spring-boot-launcher-entrypoint>
Start-Class: com.acme.app.Application
~~~

This is an illustration, not a manifest to copy verbatim. Exact loader class names and metadata can change across Spring Boot versions.

### 13.1. Main-Class and Start-Class

- `Main-Class`: the class launched by the Java launcher per the manifest.
- `Start-Class`: framework metadata used to find the application entrypoint.
- `BOOT-INF/classes`: application classes in the typical layout.
- `BOOT-INF/lib`: nested runtime dependencies.

If you run:

~~~bash
java -cp application.jar com.acme.app.Application
~~~

a standard classloader will not treat `BOOT-INF/classes` as the root classpath of a plain JAR. You must use the launcher mechanism supported by that Spring Boot version.

### 13.2. bootJar Differs from jar

In Gradle/Spring Boot, `bootJar` and `jar` can produce two different artifacts. With the Maven Spring Boot plugin, the `repackage` step can produce the executable artifact. If CI mistakenly publishes the plain JAR instead of the Boot executable JAR, runtime may lack dependencies even though both have the `.jar` extension.

When upgrading framework major versions, do not hardcode internal framework loader class names in a Dockerfile or service script when a more stable official launch method exists.

## 14. JPMS: Modular JAR and Module Launch Mode

Since Java 9, JPMS allows explicit named modules with a descriptor:

~~~java
module com.acme.order.app {
    requires java.sql;
    requires com.acme.catalog.api;

    exports com.acme.order.api;
}
~~~

If the artifact is placed on the module path and has an appropriate main class, it can be launched with:

~~~bash
java --module-path "mods:lib" \
  --module com.acme.order.app/com.acme.order.app.Main
~~~

Here `com.acme.order.app` is the **module name**, and `com.acme.order.app.Main` is the **binary class name**.

### 14.1. -jar and --module Are Different

| Mode | How Entrypoint Is Found | Environment |
|---|---|---|
| `java -jar app.jar` | `Main-Class` in manifest | Executable JAR mode |
| `java -cp ... Main` | Main class name specified directly | Classpath |
| `java --module m/p.Main` | Module name and main class | JPMS module path |

A modular JAR can also contain main class metadata, yet the launch mode determines the resolution mechanism. Putting `module-info.class` inside a JAR does not mean it operates as a named module when the JAR is placed on the classpath.

### 14.2. Module Path Is Not Classpath with New Syntax

Named modules have `requires`, `exports`, `opens`, `uses`, and `provides`. You cannot simply move all JARs from `-cp` to `--module-path` and assume all classes will see one another.

You may encounter:

- Module name mismatches.
- Automatic modules from unmodularized JARs.
- Split packages.
- Unexported packages.
- Restricted deep reflection.
- ServiceLoader providers located in another layer.
- A module present on the module path that has not been resolved.

Flags such as `--add-modules`, `--add-reads`, and `--add-opens` should only be used for specific needs and accompanied by a plan to remove the workaround.

## 15. Multi-Release JAR

A multi-release JAR can provide class implementations for different Java runtimes:

~~~text
META-INF/MANIFEST.MF
com/acme/codec/Parser.class
META-INF/versions/11/com/acme/codec/Parser.class
META-INF/versions/17/com/acme/codec/Parser.class
~~~

The manifest declares:

~~~text
Multi-Release: true
~~~

A compatible runtime can select versioned entries according to the specification rules. This feature is useful when a library needs to preserve an older Java baseline while optimizing for newer JDKs.

Packaging risks:

- Base classfiles accidentally compiled with too high a JDK.
- Versioned entries placed at wrong paths.
- Manifest missing `Multi-Release: true`.
- Shading or repackaging stripping metadata.
- API/binary contracts diverging across implementations.
- Not testing on every supported JDK.

Multi-release does not automatically turn arbitrary Java 21 classes into code that runs on Java 8.

## 16. Java Bytecode and UnsupportedClassVersionError

If the build produces bytecode too new for the runtime:

~~~text
java.lang.UnsupportedClassVersionError
~~~

Some classfile major milestones:

| Java release | Major version |
|---|---:|
| Java 8 | 52 |
| Java 11 | 55 |
| Java 17 | 61 |
| Java 21 | 65 |

For example, class major 65 requires a runtime capable of understanding the corresponding classfile format; Java 17 cannot read standard Java 21 classfiles.

You can constrain the compiler target:

~~~bash
javac --release 17 \
  -d build/classes \
  src/main/java/com/acme/app/Main.java
~~~

`--release` controls the Java language/API/classfile target of the sources being compiled. It **does not automatically control the classfile version of third-party dependencies**, does not bundle a JRE, and does not guarantee native library compatibility.

### 16.1. Checking Classfile Version

~~~bash
javap -verbose \
  -classpath dist/app.jar \
  com.acme.app.Main
~~~

The output contains the major version. If the error only occurs when a rarely used feature is invoked, check the class inside that dependency rather than only checking the main class.

## 17. Resource Loading from a JAR

In the project:

~~~text
src/main/
├── java/com/acme/app/Main.java
└── resources/com/acme/app/defaults.properties
~~~

After building, the resource should reside in the JAR at:

~~~text
com/acme/app/defaults.properties
~~~

Read it using the classpath resource API:

~~~java
try (InputStream in =
         Main.class.getResourceAsStream("defaults.properties")) {
    if (in == null) {
        throw new IllegalStateException("Missing defaults.properties");
    }

    Properties props = new Properties();
    props.load(in);
}
~~~

`Class.getResourceAsStream("defaults.properties")` looks up relative to the class's package. A form with a leading `/`, such as `"/com/acme/app/defaults.properties"`, is an absolute resource path according to the Class API.

### 17.1. Do Not Blindly Convert Resources in a JAR to File

Code creating `java.io.File` from `getResource(...).toURI()` may work when the resource is still in an output directory, yet fail once the resource is packaged inside a JAR. A resource inside an archive does not necessarily have a standalone filesystem path.

If you only need to read it, use `getResourceAsStream` or a corresponding resource abstraction. If a library strictly requires a file path, you may have to copy the stream to a temporary file with managed permissions and cleanup.

### 17.2. Resources in Named Modules Have Additional Rules

When moving to JPMS, how `ClassLoader` and `Module` locate certain resources inside a named module can be affected by encapsulation. Do not just look at the JAR entry existing and conclude that every caller outside the module can read the file.

## 18. Working Directory Does Not Automatically Equal the JAR Directory

Code:

~~~java
Path path = Path.of("config/application.properties");
~~~

usually resolves against the process's current working directory. If the user runs:

~~~bash
cd /tmp
java -jar /opt/order/app.jar
~~~

then that relative path does not automatically become `/opt/order/config/application.properties`. This is a very common source of errors after moving from an IDE to systemd or Docker.

How to handle it:

- Define the application configuration path explicitly.
- Pass an absolute path via environment/argument when appropriate.
- Set the working directory in the launcher/service configuration.
- Use classpath resource APIs for resources packaged inside the archive.
- Use filesystem APIs for external configuration files that need to change after deployment.

Do not conflate “resources packaged inside the JAR” with “external configuration sitting next to the JAR”.

## 19. JVM Options Must Be in the Right Position

Traditional syntax:

~~~bash
java [JVM-options] -jar app.jar [application-arguments]
~~~

Example:

~~~bash
java -Xms256m -Xmx1g \
  -Dapp.env=production \
  -Duser.timezone=UTC \
  -jar app.jar \
  --http-port=8080 --worker-mode
~~~

- `-Xmx1g` is the Java heap limit interpreted by the JVM.
- `-Dapp.env=production` is a Java system property.
- `--http-port=8080` and `--worker-mode` after the JAR are application arguments whose meaning is determined by the application/framework.

If you run:

~~~bash
java -jar app.jar -Xmx1g
~~~

then the string `-Xmx1g` after the JAR is no longer a JVM option; it is passed into `main(String[] args)`.

### 19.1. Old JVM Flags May Be Invalid on a Newer JDK

A script written for Java 8 may contain `-XX` options or GC logging syntax that changed in Java 17/21. After migration, startup can fail before the main class is loaded.

Verify with the exact target JDK:

~~~bash
java -version
java --help
java -X
~~~

For advanced flags, follow the JDK vendor/version documentation. Do not add broad `--add-opens` flags merely to suppress warnings if you have not identified which library actually needs that access.

## 20. Launcher Script on Linux/macOS

Example of a relatively simple Bash script where the distribution contains `app.jar` and a `config/` directory:

~~~bash
#!/usr/bin/env bash
set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$APP_DIR"

if [ -n "$JAVA_HOME" ]; then
  JAVA_BIN="$JAVA_HOME/bin/java"
else
  JAVA_BIN="java"
fi

exec "$JAVA_BIN" \
  -Xms256m \
  -Xmx1g \
  -Dapp.config="$APP_DIR/config/application.properties" \
  -jar "$APP_DIR/app.jar" \
  "$@"
~~~

The example assumes `JAVA_HOME` is declared in the environment; with Bash `set -u` enabled, if this variable is completely unset, the direct check can cause an error. In production, you can require `JAVA_HOME` explicitly, or handle an unset variable separately using a shell-safe check. The goal is to illustrate the steps: determining the app directory, selecting the Java executable, setting the working directory, and passing arguments.

Principles:

- Quote paths containing spaces.
- Use `exec` so the Java process replaces the shell where appropriate; this aids signal forwarding.
- Preserve Java's real exit code.
- Do not put secrets into scripts or command lines.
- Ensure execute permissions for the script and read permissions for the JAR/config.
- Check symbolic-link behavior if the launcher is invoked through a symlink.

### 20.1. No Need to Give the JAR an Executable Bit

With:

~~~bash
java -jar app.jar
~~~

the Java launcher opens the JAR file; the JAR does not need an executable bit under shell script rules. Some frameworks support fully executable JARs with a script prefix, but that is a separate packaging mode; not every JAR runs like a native executable.

## 21. PowerShell Launcher on Windows

Example:

~~~powershell
$ErrorActionPreference = 'Stop'

$appDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$jar = Join-Path $appDir 'app.jar'

$javaExe = 'java'
if ($env:JAVA_HOME) {
    $javaExe = Join-Path $env:JAVA_HOME 'bin\java.exe'
}

Set-Location -LiteralPath $appDir

& $javaExe '-Xms256m' '-Xmx1g' '-jar' $jar @args
exit $LASTEXITCODE
~~~

When deploying, pay attention to:

- The classpath separator on Windows is `;`.
- JDK paths under `Program Files` must be quoted properly.
- A Windows service account has a different environment from an interactive user.
- A service wrapper's `WorkingDirectory` may differ from a terminal's.
- Permissions for certificates, logs, and configuration files must be granted explicitly.
- The Windows service manager needs the exit code and recovery policy.

The example PowerShell script is not a full replacement for a service wrapper or installer; it only illustrates how to pin the runtime and arguments.

## 22. systemd Service on Linux

An illustrative unit file:

~~~ini
[Unit]
Description=Order Java Service
After=network.target

[Service]
Type=simple
User=ordersvc
WorkingDirectory=/opt/order
EnvironmentFile=/etc/order/order.env
ExecStart=/opt/order/runtime/bin/java -Xms256m -Xmx1g -jar /opt/order/app.jar
Restart=on-failure

[Install]
WantedBy=multi-user.target
~~~

Adjust account, paths, permissions, exit status policy, and timeouts per project. Do not treat a service running in a developer's login shell as proof that it works under `User=ordersvc`.

Check:

- Java executable from the right JDK.
- JAR file and external libraries are readable.
- Working directory and config paths.
- Log output.
- Graceful shutdown and signal handling.
- Network/database readiness.
- Service restart loops and alerts on startup failure.

If the JDK is bundled in a runtime image, `ExecStart` can point to the Java binary inside that image to avoid depending on the host's global Java installation.

## 23. Containers and Docker ENTRYPOINT

A simple Dockerfile for an executable JAR:

~~~dockerfile
FROM eclipse-temurin:21-jre

WORKDIR /opt/app
COPY build/libs/app.jar /opt/app/app.jar

ENTRYPOINT ["java", "-jar", "/opt/app/app.jar"]
~~~

The image tag is illustrative only; in production, select a version/digest and patches approved by your organization.

Common issues:

- Container has a lower JDK/JRE version than the classfile target.
- Mistakenly copying a thin JAR into the image without dependencies.
- Copying a Spring Boot JAR but using a launch command that does not use the Boot loader.
- `WORKDIR` differs from the local environment.
- Native libraries incompatible with the image's OS/CPU.
- Non-root user permissions.
- Container memory limit incompatible with `-Xmx`.
- Signals not reaching Java because a shell wrapper does not `exec`.

Exec-form `ENTRYPOINT` usually allows the Java process to receive signals more directly than shell-form with an intermediate shell process; the application still needs graceful-shutdown logic.

### 23.1. Do Not Assume the Container Has Every Runtime Support

A minimal runtime image may lack fonts, CA certificates, locale/timezone data, or native libraries that the application needs. For desktop/media/JNI/TLS use cases, verify the corresponding platform dependencies.

## 24. jlink and jpackage Are More Than Ways to Create JARs

`jlink` creates a runtime image from a suitable set of named modules. `jpackage` creates a platform-specific application image or installer for supported application modes.

~~~text
Source + Dependencies
         |
         v
Compile/package artifacts
         |
         +--> JAR + java -jar / -cp
         |
         +--> Named modules -> jlink runtime image
         |
         +--> jpackage application image/installer
~~~

Cases worth considering:

- Desktop applications requiring installation without asking users to install a JDK themselves.
- Wanting to bundle the Java runtime with the app to control its version.
- Requiring a launcher, icon, file associations, or signing/notarization.
- Wanting to create a runtime image from the module graph.

Not all automatic modules can be linked directly with `jlink` like explicit named modules. A legacy app with unmodularized dependencies may have to choose a different packaging approach or handle modularization separately.

## 25. Class Loaders and Duplicate Dependencies

The classpath can contain the same class name across multiple JARs. Search order, class loader delegation, module layers, and framework custom loaders affect which class is actually used.

Example errors:

~~~text
java.lang.NoSuchMethodError
java.lang.ClassNotFoundException
java.lang.NoClassDefFoundError
java.lang.ClassCastException
~~~

A `NoSuchMethodError` can mean the app was compiled against a newer library while runtime loaded an older library with the same class name. Do not fix it by adding a third copy of the dependency to the classpath; identify the source loading the class.

### 25.1. Seeing Where a Class Is Loaded From

On JDKs supporting unified logging:

~~~bash
java -Xlog:class+load=info \
  -jar app.jar
~~~

Logs can become large; enable only in permitted environments/sessions and with bounded storage.

In debugging code:

~~~java
Class<?> type = com.acme.catalog.CatalogClient.class;

System.out.println(type.getClassLoader());
System.out.println(type.getProtectionDomain().getCodeSource());
~~~

Code source may not have a useful URL for every kind of class, yet it is a signal for distinguishing an old JAR from a new JAR.

### 25.2. ServiceLoader and Plugin Class Loaders

If the app has plugin providers in `META-INF/services`, custom loaders, or JPMS module layers, test how providers are discovered after changing packaging. Just because a class exists in the archive does not guarantee `ServiceLoader` using a particular class loader will see that provider.

## 26. Tools for Inspecting Artifacts and Runtime

Some useful commands:

~~~bash
# Identify the actual Java runtime
java -version

# List the archive
jar --list --file dist/app.jar

# Read entrypoint and classfile info
javap -verbose -classpath dist/app.jar com.acme.app.Main

# Analyze dependencies in bytecode
jdeps --summary dist/app.jar

# For modular JARs:
jar --describe-module --file dist/app.jar
~~~

You can extract `META-INF/MANIFEST.MF` into a separate inspection directory:

~~~bash
mkdir -p inspect
cd inspect
jar --extract --file ../dist/app.jar META-INF/MANIFEST.MF
~~~

Paths are examples; make sure `../dist/app.jar` actually exists relative to your directory. Avoid extracting into a production directory because the command can create/overwrite entry files.

`jdeps` analyzes static dependencies; it does not automatically detect every class loaded via reflection, SPI, JNI, or plugin configuration. Therefore, you must combine it with runtime tests.

## 27. Common Errors and Diagnostic Directions

| Symptom | Causes to Consider | First Check |
|---|---|---|
| `no main manifest attribute` | Missing `Main-Class` | Manifest of the exact JAR |
| `Could not find or load main class` | Wrong class name or classpath | Class entries and launch mode |
| `NoClassDefFoundError` | Missing dependency or class init failure | Nested causes, runtime classpath |
| `UnsupportedClassVersionError` | JVM older than bytecode target | `java -version`, `javap` |
| `NoSuchMethodError` | Binary dependency mismatch | Class source and resolved versions |
| `ClassCastException` between same-named types | Different class loader identities | Defining loaders |
| `ServiceConfigurationError` | Provider metadata/load failure | `META-INF/services` and module graph |
| Invalid signature digest | Shading broke old signatures | Packaging/signing |
| `InaccessibleObjectException` | Restricted reflection | JDK/module access and library version |
| `FindException` / `ResolutionException` | Broken module graph | Module path, names, split packages |
| `FileNotFoundException` after deploy | Working directory, resource path | `user.dir`, JAR contents, permissions |
| Native `UnsatisfiedLinkError` | Missing/wrong OS-CPU library | Runtime image, native dependencies |
| App runs locally but fails in systemd | Different service account/env/cwd | Unit, logs, permissions |
| App runs in IDE but fails in container | Different image JDK/JAR variant | Dockerfile, checksums, classpath |
| JVM fails to start | Obsolete JVM flags/invalid syntax | Java options and target version |

The table above is directional only. A class loading error can have multiple causes; read the full stack trace, root causes, and identify the exact artifact being executed.

## 28. Separating Build, Packaging, Launcher, and Runtime Errors

To avoid fixing the wrong layer, classify the issue:

1. **Build:** does the code compile under the selected JDK/toolchain?
2. **Package:** does the output JAR have the right entrypoint, resources, metadata, and deps?
3. **Launch:** are the Java executable, launch mode, options, paths, and arguments right?
4. **Runtime:** are class loading, reflection, TLS, native libraries, and config correct?
5. **Operation:** are service account, health checks, logs, shutdown, restart, and rollback right?

Examples:

- Green build, `java -jar` reports missing manifest: packaging/entrypoint issue.
- Manifest is right but client library is missing: runtime distribution issue.
- Runs in CI, systemd cannot find config file: working directory/config path issue.
- Runs on Java 17, Java 11 reports classfile 61: runtime version issue.
- `UnsatisfiedLinkError` only on Linux AArch64: inspect native artifacts/platform.

## 29. Security and Artifact Provenance

Packaging affects the software supply chain:

- Does the runtime/JDK image have an explicitly chosen version or digest?
- Are dependency and plugin versions managed?
- Does the output JAR have a checksum and corresponding source commit?
- Does shading handle signatures and license metadata properly?
- Does the launcher load external JARs from untrusted sources?
- Are secrets exposed on the command line, in scripts, or in logs?
- Do file permissions protect configuration, key/trust stores, and logs?
- Does CI run the exact published artifact rather than building a different one at deploy time?

A file named `app.jar` does not prove it was built from the expected commit. Release pipelines should record artifact SHA-256 checksums and JDK/Wrapper/build provenance information per policy.

### 29.1. Reproducible Builds

JARs can differ byte-for-byte due to timestamps, entry order, source encoding, JDK, plugins, or different dependencies. Maven/Gradle provide mechanisms to support reproducible archive builds, but they must be configured for the exact version and their output verified.

The Wrapper pins the build tool distribution; it does not automatically pin the JDK, all plugins, or the OS, so it is not sufficient on its own for build reproducibility.

## 30. Logging, Process Lifecycle, and Graceful Shutdown

A production launcher needs to care about more than the entrypoint:

- stdout/stderr are collected and rotated properly.
- The actual exit code is returned to systemd/CI/container.
- The Java process receives SIGTERM and executes shutdown.
- Database connections and broker consumers are closed cleanly.
- Health/readiness probes do not report success too early.
- The service account has the proper filesystem/network permissions.
- Restart loops are not hidden by insufficient monitoring.
- Heap and native memory stay within container limits.

In a Unix shell, using `exec java ...` helps prevent the shell from staying as an intermediate process, yet the application still must implement shutdown logic.

### 30.1. Java Flags in Containers

Do not copy `-Xmx` verbatim from a bare-metal machine into a container with a lower memory limit. When upgrading the JDK, check defaults and ergonomics related to heap/GC. A green startup that gets OOM-killed under real load is not a successful migration result.

## 31. JAR and Launcher Migration Roadmap

### Phase 1 — Baseline

Record:

- Source commit, artifact name, and checksum.
- Build and runtime JDK vendor/version.
- Maven/Gradle Wrapper/plugins.
- Manifest and artifact layout.
- Runtime dependencies, agents, native libraries.
- Actual run commands in IDE, terminal, and service/container.
- JVM args, environment, and external config paths.
- Logs, health, shutdown, and test results.

### Phase 2 — Choose Artifact Type

Decide on one of the models:

- Plain library JAR.
- Thin executable JAR with `Class-Path` manifest.
- Distribution with `lib/` directory + launcher script.
- Uber/shaded JAR.
- Framework-specific executable JAR.
- Modular JAR and module-path launcher.
- Runtime image/installer.

Base the choice on dependencies, platform, tooling, and operations, not on “fat JAR is always best”.

### Phase 3 — Switch JDK/Build Tool

Upgrade Maven/Gradle plugins and JDK target according to the support matrix. Check bytecode target, runtime dependencies, and legacy JVM flags. Avoid changing framework major versions simultaneously if they can be separated.

### Phase 4 — Inspect Actual Output

Inspect manifest, class entries, resources, dependencies, service metadata, and checksum. Do not rely solely on intended configuration in POM/Gradle.

### Phase 5 — Production-Like Run

Run on a clean machine/container using the exact launcher, account, working directory, and runtime version. Exercise API/database/broker/TLS and graceful shutdown.

### Phase 6 — Rollout and Rollback

Roll out via canary or small batches. When rolling back, restore the **exact set of artifact + dependencies + JDK runtime + config/launcher**. If the migration changed database/message/session formats, plan data rollback separately.

## 32. Comprehensive Example: Java 8 Thin JAR to Java 21

Old system:

~~~text
/opt/legacy/
├── service.jar
├── lib/
│   ├── http-client.jar
│   └── json-codec.jar
├── config/
│   └── application.properties
└── start.sh
~~~

Old run command:

~~~bash
java -Xmx512m -cp "service.jar:lib/*" \
  com.acme.service.Main
~~~

The project team wants to create a JAR with `Main-Class` and switch to:

~~~bash
java -jar service.jar
~~~

Without a manifest `Class-Path` and without a new packaging format, the JVM may fail to load `lib/http-client.jar` and `lib/json-codec.jar`. The result is `NoClassDefFoundError` or failures when code calls dependency APIs.

A practical roadmap can be:

1. Confirm the old JAR is a thin JAR and record the complete runtime classpath.
2. Check the manifest, classfile target, and JDK baseline.
3. Cross-check dependency/framework support against JDK 21.
4. Choose to keep the classpath distribution, generate a thin executable manifest with Class-Path, or build a shaded/framework JAR properly.
5. Ensure the build plugin actually produces the chosen artifact type.
6. Test runtime in a directory other than the developer's `user.dir`.
7. Test external configuration, service metadata, and class loading.
8. Run in a container/systemd with the real Java 21 runtime.
9. Monitor startup, health, GC, DB/TLS, and shutdown.
10. Prepare rollback covering the launcher, JAR, `lib` directory, and old JDK.

**You do not need to switch to a fat JAR if a classpath distribution is well managed.** What matters most is that artifact topology and launcher align with each other.

## 33. Common Misconceptions

**“Every JAR can be run with `java -jar`.”** No. A plain JAR used as a dependency may have no entrypoint.

**“Having Main-Class means the JAR already contains dependencies.”** False. The manifest does not automatically bundle libraries.

**“`java -cp lib/* -jar app.jar` will add libraries for an executable JAR.”** Do not rely on this assumption; `-jar` has its own user classpath mechanism.

**“Manifest Class-Path is based on the current working directory.”** Wrong in principle; manifest relative URLs are resolved relative to the JAR.

**“A shaded JAR is always equivalent to all original JARs combined.”** False. You must merge SPI/metadata and handle signatures, duplicate resources, and relocation.

**“A Spring Boot executable JAR is a plain JAR with dependency classes at the root.”** No. It typically has nested JARs and its own loader.

**“A JAR built with JDK 21 will automatically run on Java 17.”** Not if bytecode/APIs/dependencies require a newer runtime.

**“Changing the executable path to the new JDK is enough to migrate.”** No. JVM flags, TLS, classloading, agents, and native dependencies also matter.

**“Running in the IDE proves deployment is correct.”** No. The IDE may configure classpath/JDK/working directory settings that the release lacks.

**“The application starting up means production is ready.”** Not sufficient without testing integrations, health, shutdown, and rollback.

## 34. Pre-Completion Checklist

- [ ] Identified whether the JAR is a library, thin executable, shaded, Spring Boot nested, or modular JAR.
- [ ] Checked the actual manifest inside the output artifact.
- [ ] Confirmed a valid `Main-Class` or framework launcher.
- [ ] Distinguished `Main-Class` from framework-specific metadata like `Start-Class`.
- [ ] Verified bytecode and dependencies are compatible with the target JDK runtime.
- [ ] Know the actual runtime classpath/module path.
- [ ] Checked manifest `Class-Path` and relative locations.
- [ ] Handled service provider metadata, duplicate classes/resources, and signatures when shading.
- [ ] Checked native libraries per OS/CPU.
- [ ] Verified resources are packaged and loaded properly via classloader/module.
- [ ] Distinguished resources inside the JAR from external config files.
- [ ] Checked working directory across terminal, systemd, and containers.
- [ ] Placed JVM options before `-jar` and application arguments in the right position.
- [ ] Audited obsolete flags not supported by the target JDK.
- [ ] Verified the exact Java executable selected by the launcher.
- [ ] Checked Windows/Unix quoting, script permissions, and service account.
- [ ] Checked Docker ENTRYPOINT, runtime image, and non-root permissions.
- [ ] Checked classloaders, SPI, and JPMS if used by the application.
- [ ] Executed clean-machine/production-like smoke tests.
- [ ] Verified logs, health checks, graceful shutdown, and exit codes.
- [ ] Recorded artifact digests and build/runtime metadata.
- [ ] Prepared a rollout/rollback plan covering the JAR as well as dependencies/runtime/config.
- [ ] Separated build, package, launch, and runtime errors when investigating.

## 35. Conclusion

**Plain JAR, executable JAR, and launcher are three layers that cannot be conflated.** A plain JAR is an archive holding classes/resources; an executable JAR declares an entrypoint yet does not automatically bundle dependencies; and the launcher determines the Java runtime, classpath/module path, JVM options, arguments, working directory, and process lifecycle.

In Java Advance Compatibility Migration, you must verify the **final artifact** and the actual launch command. Thin JARs, shaded/uber JARs, Spring Boot nested archives, and modular JARs have different class-loading mechanisms. Changing the JDK or build plugins without reviewing packaging easily creates bugs that only surface in production.

A successful migration means the same application version is reproducibly built, has accurate dependencies/resources, runs on an approved runtime, has appropriate logging/health/shutdown, and has a tested rollback plan. **The destination is not just producing a `.jar` file, but operating the entire Java distribution accurately and safely.**

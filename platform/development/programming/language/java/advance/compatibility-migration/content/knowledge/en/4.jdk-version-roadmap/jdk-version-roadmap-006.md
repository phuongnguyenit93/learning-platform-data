# Upgrading JDK 11 to 17: Internal Packaging and Changed Tooling

Upgrading from JDK 11 to JDK 17 is not merely changing the JDK version in CI or swapping a container base image. Since Java 9, the JDK moved to a modular structure; runtime components, platform libraries, and packaging tools have also changed across releases. Between 11 and 17, several legacy tools were removed, access to JDK internals was tightened, and `jpackage` became a standard tool for creating application installers.

For Java Compatibility Migration, three layers must be inspected simultaneously:

1. **JDK structure and runtime image:** do scripts, plugins, or applications assume the old JDK/JRE directory layout or access internal files directly?
2. **Build and packaging tools:** does the pipeline invoke removed tools, or miss opportunities from the new runtime-image and installer workflows?
3. **Application and dependencies:** are source, bytecode, reflection, native libraries, and class loading compatible with JDK 17?

Both JDK 11 and JDK 17 are LTS releases, yet this upgrade should not be treated as a binary drop-in swap. Identify the exact tools the project invokes, the artifacts the pipeline builds, and the runtime layout the production environment uses.

## 1. Scope of changes from JDK 11 to JDK 17

JDK 17 incorporates cumulative changes from releases 12, 13, 14, 15, 16, and 17. Therefore, an application running cleanly on JDK 11 can still fail when running or packaging on JDK 17 even without source changes.

| Area | Status in JDK 11 | Status in JDK 17 | Impact to inspect |
|---|---|---|---|
| JDK module image | Already uses modular structure since Java 9 | Continues using module image | Scripts must not assume `rt.jar`, `tools.jar`, or a nested JRE folder inside the JDK |
| Access to JDK internals | Strong encapsulation rolled out incrementally; some access still relaxed | Default strong encapsulation broadly enforced per JEP 403 | Reflection or imports of internal packages may fail |
| `jlink` | Available since Java 9 | Continues to be supported | Can build minimal runtime images; must accurately specify modules and service providers |
| `jpackage` | Not yet a standard tool bundled with JDK 11 | Standard tool since JDK 16, included in JDK 17 | Can replace custom scripts assembling runtimes and native installers |
| Pack200 | Already deprecated for removal | Tool and API removed since JDK 14 | Pipelines calling `pack200`, `unpack200`, or `Pack200` no longer run |
| Nashorn JavaScript engine | Already deprecated for removal in JDK 11 | Removed from JDK since JDK 15 | Applications no longer receive the Nashorn engine solely from the JDK |
| RMI Activation | Already deprecated for removal in JDK 11 | Removed since JDK 17 | Code using `java.rmi.activation` needs replacement or redesign |
| Experimental AOT/JIT | Included `jaotc` in some JDK 11 distributions | These experimental tools/compilers removed from JDK 17 | Legacy AOT/native optimization pipelines must be re-evaluated |

Several components had already left the JDK before version 11. For instance, JavaFX is no longer bundled in the JDK starting with Java 11; Java EE/CORBA modules, Java Web Start, and `appletviewer` also departed before that milestone. If an application is actually migrating from JDK 8 or a vendor JDK carrying extra tools, check changes prior to JDK 11 separately to avoid mistaking them for new changes from 11 to 17.

## 2. JDK packaging layout after Java 9

JDK 11 already adopted the Java 9 modular structure. Therefore, when upgrading from 11 to 17, teams are not transitioning for the first time from `rt.jar` to a module image, yet they still need to audit legacy scripts and internal libraries relying on the old layout.

### 2.1. No more `rt.jar` and `tools.jar`

In older JDKs, many platform classes were packaged in `rt.jar`, while compiler/tooling classes and APIs could reside in `tools.jar`. Starting in Java 9, JDK classes are organized into modules inside the runtime image. Those legacy JAR files are no longer the platform packaging mechanism.

Legacy assumptions to search for across scripts, plugins, and code:

```text
$JAVA_HOME/jre/lib/rt.jar
$JAVA_HOME/lib/tools.jar
$JAVA_HOME/jre/bin/java
$JAVA_HOME/jre/bin/keytool
$JAVA_HOME/jre/lib/ext
```

Do not replace these paths with another internal path inside JDK 17. Use supported APIs or tools:

- Run the compiler via a Java toolchain or `javac` from the selected JDK.
- Use `java --list-modules` to inspect available runtime modules.
- Use `jar`, `jmod`, `jdeps`, and `jlink` for corresponding module/JAR operations.
- Use the `jrt:/` filesystem if a tool genuinely needs to traverse module image resources.
- Use `JAVA_HOME` or build-tool-managed toolchains to locate the JDK instead of constructing paths assuming the legacy JDK layout.

### 2.2. Module image and `jrt:/`

Platform modules are stored in the runtime image, typically organized inside the `lib` directory of the JDK/JRE image. List modules with:

```bash
java --list-modules
```

The JDK provides the `jrt:/` filesystem provider to access module image contents. For example, a Java tool can browse this filesystem instead of opening `rt.jar`:

```java
import java.net.URI;
import java.nio.file.FileSystem;
import java.nio.file.FileSystems;
import java.nio.file.Path;

URI uri = URI.create("jrt:/");
try (FileSystem fileSystem = FileSystems.getFileSystem(uri)) {
    Path javaBase = fileSystem.getPath("/modules/java.base");
    System.out.println(javaBase);
}
```

This is the intentional way to access the module image. Most business applications do not need to inspect the JDK image themselves; if a plugin or analysis tool does so, verify its compatibility with JDK 17.

### 2.3. JDK image and runtime image

The JDK is the development kit containing the compiler, debugger, and other tools. A runtime image is the environment needed to execute applications. Since Java 9, custom runtime images containing only needed modules can be created with `jlink`.

Implications for packaging:

- Do not assume a separate JRE subdirectory inside the JDK directory.
- Do not copy the entire JDK to production if the application needs only a runtime.
- Runtime images can be built per application or application group.
- Verify the platform modules the application actually uses, including modules loaded via service providers.
- A runtime image is built for a specific platform/architecture; build and test an image matching the target environment.

Do not delete or modify files directly inside a runtime image after `jlink` generates it. Regenerate the image reproducibly from the module path and build parameters.

### 2.4. Extension and endorsed standards directories

Legacy extension/endorsed standards mechanisms such as `lib/ext`, `java.ext.dirs`, and `java.endorsed.dirs` are no longer modern JDK extension mechanisms. Since Java 9, application libraries must be declared via classpath, module path, or build tool dependency management.

If scripts still copy JARs into a JRE extension folder or pass legacy system properties, replace them with explicit classpath/module-path configuration. Do not attempt to restore the extension mechanism by creating directories matching the old names.

## 3. Strong encapsulation of JDK internals

This is a major-impact change when moving to JDK 17. Internal packages such as `sun.*`, `com.sun.*`, or unexported packages inside JDK modules are not stable public APIs. Some older applications and libraries still access them via reflection or direct imports.

### 3.1. Tightening access over time

Java 9 introduced the module system and encapsulation. In early releases, some legacy packages remained accessible with warnings to aid migration. JDK 16 switched to default strong encapsulation for JDK internal packages; JDK 17 continues that policy under JEP 403.

Consequently, the old option:

```bash
--illegal-access=permit
```

is no longer a way to restore broad access in JDK 17. The `--illegal-access` option no longer opens packages as before and may simply emit a warning that the option was ignored.

### 3.2. Common failure symptoms

When upgrading the JDK, errors may appear such as:

```text
java.lang.reflect.InaccessibleObjectException
```

or:

```text
java.lang.IllegalAccessError
```

The usual cause is a library attempting to access a member or type in a package whose owning module neither opens nor exports it to the calling module.

For example, an old library attempts deep access to an internal field of a JDK class via `setAccessible(true)`. On older JDKs this may have worked under relaxed access; on JDK 17 it can throw `InaccessibleObjectException`.

### 3.3. Distinguishing `--add-exports` and `--add-opens`

These two options serve distinct purposes:

| Option | Purpose | When to use |
|---|---|---|
| `--add-exports` | Grants another module access to public types in an unexported package | Compile or runtime code must reference public types in an internal package |
| `--add-opens` | Opens a package for deep reflection at runtime | Frameworks or libraries must reflect on non-public fields/methods/constructors |

Example opening package `java.base/java.lang` to code on the classpath (unnamed module):

```bash
java --add-opens java.base/java.lang=ALL-UNNAMED -jar app.jar
```

Example exporting a package to a named module:

```bash
javac --add-exports java.base/sun.nio.ch=my.module \
  -d out src/module-info.java src/example/Main.java
```

Module and package names in examples illustrate syntax only. Add flags only after identifying exactly which library needs access and which package is closed.

`--add-reads` can add read edges between modules in special module graph cases. `--patch-module` allows augmenting/replacing module content in intentional development or testing scenarios; it is not a normal migration workaround to hide JDK internal usage.

### 3.4. Long-term remediation

Prioritize in order:

1. Upgrade libraries to versions supporting JDK 17 that no longer access internal packages.
2. Replace internal APIs with supported public APIs, e.g., `java.util.Base64` instead of old internal encoders/decoders.
3. If needed, replace the library with a maintained implementation offering a stable API.
4. Use `--add-opens` or `--add-exports` only as narrowly scoped compatibility measures that are documented with a removal plan.

Do not open packages wholesale to `ALL-UNNAMED` just to make the application start. That widens reflective access for all code on the classpath and raises future upgrade costs.

### 3.5. Finding dependencies on JDK internals

Run `jdeps` on the application JAR and classpath:

```bash
jdeps --jdk-internals --recursive \
  --class-path "lib/*" app.jar
```

Output flags known bytecode references to internal APIs. Read the tool's replacement suggestions as well and pinpoint which library contains each reference.

`jdeps` cannot fully detect reflection constructed from strings, dynamically loaded classes, native code, or configuration-driven behavior. Combine it with source searches, runtime testing, and logs on JDK 17.

## 4. `jlink`: building minimal runtime images

`jlink` has existed since Java 9, so it is present in both JDK 11 and JDK 17. The key in migration is re-verifying the module graph and how the pipeline builds the runtime image, rather than viewing `jlink` as a new tool introduced only in JDK 17.

### 4.1. When should `jlink` be used?

`jlink` fits when you want to package a runtime containing only the modules the application requires. Potential benefits include:

- Reducing runtime image size compared to shipping the entire JDK.
- Controlling precisely which platform modules exist in the execution environment.
- Creating dedicated runtimes per application or application group.
- Reducing drift between test and deployment runtimes if the same image flows across the pipeline.

In exchange, the team must maintain the module list and verify service providers, locales/charsets, security providers, and runtime components the application needs. An overly minimal image can cause the application to fail on lightly tested code paths.

### 4.2. Finding required modules with `jdeps`

For an application JAR and dependent libraries, you can start with:

```bash
jdeps --print-module-deps \
  --ignore-missing-deps \
  --class-path "lib/*" \
  app.jar
```

`jdeps` analyzes static bytecode references and prints the list of required platform modules. `--ignore-missing-deps` helps during initial exploration, yet should not vanish from error investigation: missing dependencies still require explanation.

Static analysis has limits. If the application uses reflection, JDBC drivers, logging providers, serialization providers, or `ServiceLoader`, needed modules may not be fully inferred. You may need to add modules based on test results or use `--bind-services` to include discovered provider modules in the runtime image.

### 4.3. Creating the runtime image

Example creating an image from the JDK module path and application modules:

```bash
jlink \
  --module-path "$JAVA_HOME/jmods:mods" \
  --add-modules com.example.order,java.sql,java.logging \
  --bind-services \
  --output build/order-runtime
```

Module paths and module lists must be adapted to the environment. On Windows, path separators and environment variable syntax differ from POSIX shell examples.

A runtime image can be verified using the executable inside the image itself:

```bash
build/order-runtime/bin/java --list-modules
build/order-runtime/bin/java -jar app.jar
```

In practice, the application JAR and dependencies must be placed appropriately or configured for the launcher to load. Run smoke tests using the generated image, not just the full JDK on a developer machine.

### 4.4. Considerations for `jlink`

- `jlink` creates a runtime image for the platform on which the tool runs; do not use a Linux image as a Windows runtime.
- The module path must supply the required modules. JARs on the classpath do not automatically become linkable modules.
- Some non-modular/automatic-module libraries may need modularization or different packaging before inclusion in a linked image.
- `--bind-services` helps discover service providers on the module path, yet does not detect every plugin loaded by reflection or dynamic configuration.
- Verify providers such as JDBC drivers, logging backends, crypto providers, and locale data if used by the application.
- A runtime image lacks the compiler and full development toolset; do not use it as a build JDK.
- Do not inspect only image size. Verify startup, health checks, business flows, TLS, timezones, charsets, and error handling.

## 5. `jpackage`: packaging applications into native installers

`jpackage` was introduced as an incubator tool in JDK 14 and became a standard tool in JDK 16 (JEP 392). Hence JDK 17 includes `jpackage`, whereas standard JDK 11 lacks it.

`jpackage` creates an OS-specific application image or installer, optionally bundling a dedicated runtime. It suits desktop applications, internal tools installed on user workstations, or certain server applications distributed as native packages.

### 5.1. Output types

Package formats depend on OS and supporting tooling:

| Platform | Common output types | Notes |
|---|---|---|
| Windows | `app-image`, `exe`, `msi` | Native packages require an appropriate Windows packaging toolchain |
| macOS | `app-image`, `dmg`, `pkg` | Installers must be built and tested on macOS; sign/notarize per distribution policy |
| Linux | `app-image`, `deb`, `rpm` | DEB/RPM packages require corresponding packaging tools in the build environment |

`app-image` is an application directory with a launcher and required runtime; it is not a native installer. `exe`, `msi`, `dmg`, `pkg`, `deb`, or `rpm` are OS-specific installers.

### 5.2. Packaging non-modular applications

Applications can continue using traditional classpaths and JARs. Example:

```bash
jpackage \
  --type app-image \
  --name OrderTool \
  --input build/libs \
  --main-jar order-tool.jar \
  --main-class com.example.order.Main \
  --dest build/packages
```

Here, `--input` specifies the directory of JARs to package; `--main-jar` specifies the startup JAR and `--main-class` specifies the main class if the manifest does not supply it. Include runtime dependencies in the input directory in a way the launcher can load.

### 5.3. Packaging modular applications

For applications with module descriptors and a module path, specify the main module:

```bash
jpackage \
  --type app-image \
  --name OrderTool \
  --module-path mods \
  --module com.example.order/com.example.order.Main \
  --dest build/packages
```

For applications needing a custom runtime, create the runtime with `jlink` first and pass it to `jpackage` via `--runtime-image`:

```bash
jpackage \
  --type app-image \
  --name OrderTool \
  --input build/libs \
  --main-jar order-tool.jar \
  --main-class com.example.order.Main \
  --runtime-image build/order-runtime \
  --dest build/packages
```

These two examples show two packaging styles. Choose the one fitting your actual module model; there is no need to convert a classpath application to modular solely to use `jpackage`.

### 5.4. Native tooling and build requirements

`jpackage` builds native packages for the build platform. Installer formats usually require OS-specific tools, such as Windows MSI/EXE toolchains, Linux DEB/RPM tools, or Apple tooling on macOS.

Therefore:

- Split packaging jobs by OS/architecture when releasing across multiple platforms.
- Record native tool versions and signing configurations.
- Do not assume every installer format can be built on every runner.
- Test installers on clean machines or matching VMs, not just running the build directory on a developer workstation.
- On macOS/Windows, verify signing, certificates, notarization, and SmartScreen per distribution policy.
- Check `jpackage --help` from the exact JDK 17 vendor/build in use to confirm supported options.

### 5.5. Launchers and runtime options

`jpackage` can configure launcher names, icons, versions, shortcuts, file associations, and Java runtime options. If an application needs `--add-opens` or system properties, place those options in a controlled launcher configuration instead of relying on manual developer launch commands.

Never embed secrets, tokens, or passwords in launcher options or installers. Sensitive settings must be supplied via a secret store or proper runtime configuration mechanism.

## 6. Tools and components removed between 11 and 17

Older pipelines may still invoke removed tools even when Java application code never references those APIs directly. Inventory shell scripts, Dockerfiles, Gradle tasks, Maven plugins, and release workflows.

### 6.1. Pack200 and Unpack200

Pack200 was once used to compress JARs, particularly in older Java distribution workflows. This technology was deprecated for removal in JDK 11 and removed in JDK 14 under JEP 367. JDK 17 no longer provides:

- The `pack200` and `unpack200` commands.
- The `java.util.jar.Pack200` API and related components.

If a pipeline packs or unpacks artifacts with Pack200, switch to standard JAR/ZIP or modern distribution mechanisms. Do not simply rename `.pack.gz` files to `.jar`; update creation, storage, download, extraction, and checksum verification steps together.

### 6.2. Nashorn JavaScript engine

Nashorn was deprecated for removal in JDK 11 and removed from the JDK in JDK 15 under JEP 372. Therefore, on JDK 17, code looking up the engine may no longer receive a default Nashorn engine:

```java
ScriptEngine engine = new ScriptEngineManager()
        .getEngineByName("nashorn");
```

If the application needs JavaScript scripting, choose a maintained standalone engine or move script logic to another mechanism. Adding a standalone Nashorn artifact can support some cases, yet requires checking version, compatibility, and maintenance status. Do not assume legacy Nashorn scripts run unmodified on another engine due to differences in Java interop, APIs, and semantics.

### 6.3. RMI Activation

RMI Activation was deprecated for removal in JDK 11 and removed in JDK 17 under JEP 407. APIs in `java.rmi.activation` and the `rmid` tool are no longer available as before.

Core RMI was not removed completely. If an application used the activation system to activate remote objects on demand, redesign service lifecycle and startup mechanisms. Depending on architecture, move to service processes managed by systemd, Windows Services, container orchestrators, or the operational platform.

### 6.4. RMI compiler `rmic`

`rmic` was removed prior to JDK 17, starting in JDK 15. Pipelines still calling `rmic` must be updated. Before changing them, determine whether the application uses static stub generation or dynamic stub mechanisms; not every RMI application needs a separate `rmic` step on modern JDKs.

### 6.5. Experimental AOT/JIT compilers

Experimental AOT/JIT tools such as `jaotc` and the experimental JDK Graal JIT compiler were removed in JDK 17 under JEP 410. If a pipeline previously performed ahead-of-time compilation with `jaotc`, identify why it was used, benchmark, and adopt alternative runtime/compiler solutions. Do not treat old AOT outputs as artifacts usable directly on JDK 17.

### 6.6. JavaFX tools and components already outside JDK 11

`javapackager` belonged to the legacy JavaFX toolset and is no longer shipped with JDK 11. JavaFX itself is also no longer bundled in the JDK starting in Java 11. If real migration begins from JDK 8 or a vendor JDK bundling JavaFX, replace JavaFX with standalone dependencies and evaluate `jpackage` for packaging.

Java Web Start (`javaws`), `appletviewer`, and several Java EE/CORBA technologies were also removed in or before JDK 11. These are not changes specific to JDK 17, yet can still appear in legacy scripts, build docs, or inherited installer workflows.

### 6.7. Quick tool checklist

| Tool/API | Change milestone | Action needed for JDK 17 |
|---|---|---|
| `jpackage` | Standardized in JDK 16 | Can build app images/installers; standardize runners per OS |
| `pack200`, `unpack200`, `Pack200` API | Removed in JDK 14 | Replace compression/decompression steps in pipelines |
| Nashorn | Removed from JDK in JDK 15 | Choose standalone JavaScript engine or redesign scripting |
| `rmic` | Removed in JDK 15 | Review RMI stub generation process |
| `jaotc` and experimental JDK Graal JIT | Removed under JEP 410 in JDK 17 | Redesign AOT optimization/packaging if still used |
| RMI Activation / `rmid` | Removed in JDK 17 | Replace activation and lifecycle management |
| `javapackager`/bundled JavaFX | Already absent in JDK 11 | Use standalone JavaFX dependencies and evaluate `jpackage` |

## 7. Changes in organizing JARs, modules, and runtime dependencies

### 7.1. Classpath and module path

Classpath applications remain supported in JDK 17. Converting every application to JPMS is not mandatory. However, to build minimal runtime images with `jlink`, you must understand module graphs and the module path.

Classpath merges classes and resources into an unnamed namespace. The module path provides modules with explicit metadata and access boundaries. A JAR lacking `module-info.class` can be treated as an automatic module in certain module-path scenarios, yet an automatic module does not imply a stable module contract or direct eligibility for linked runtime images.

Decide clearly whether the application uses:

- Traditional classpath with `-cp`/`-classpath`.
- Module path with module descriptors.
- A hybrid model where a modular application calls libraries on the classpath or automatic modules.

Do not mechanically switch `-cp` to `--module-path`. Class loading, module names, access rules, and service discovery can change.

### 7.2. Modular JARs and JMOD

A JAR can contain `module-info.class` declaring module name, dependencies (`requires`), exported packages (`exports`), and services (`uses`/`provides`). Inspect module metadata via:

```bash
jar --describe-module --file build/libs/order-domain.jar
```

JMOD is a module packaging format used during development/linking that can hold native commands, native libraries, configuration, and resources beyond regular JARs. The `jmod` tool creates, describes, and lists JMODs. Most enterprise applications do not need to create JMODs themselves; use them only when specialized module image needs exist.

### 7.3. Multi-release JARs

A multi-release JAR can contain Java-version-specific implementations under `META-INF/versions/<N>`. The JVM selects the class matching the runtime release. When upgrading from 11 to 17, verify whether libraries ship Java 17 implementation branches and whether artifacts are packaged with the `Multi-Release: true` attribute.

You can run `jdeps --multi-release 17` to analyze the branch matching release 17 when auditing dependencies. Do not assume every JAR scanning tool selects the same class branch as the JVM.

### 7.4. Runtime resources and providers

When creating a runtime image, do not rely solely on modules visible in source code. Check runtime resources and providers:

- JDBC drivers and `java.sql`/`java.naming` when needed.
- Logging providers and bridges.
- Security providers, keystores, and truststores.
- Locale, timezone, and charset data.
- XML parsers, transformers, and service providers.
- Native libraries, JNI, and OS-dependent libraries.
- `ServiceLoader` providers and plugins configured outside source.

A runtime image may start cleanly yet fail on rare code paths if a provider or resource is missing. Build representative tests covering those paths.

## 8. Discovery and pre-packaging inspection tools

JDK 17 provides several tools to inspect dependencies and deprecated APIs. Run them on both the baseline artifact and the JDK 17-built artifact.

### 8.1. `jdeps`

Common commands:

```bash
# Inspect module dependencies of the application
jdeps --print-module-deps --class-path "lib/*" app.jar

# Find references to JDK internal APIs
jdeps --jdk-internals --recursive --class-path "lib/*" app.jar

# Inspect dependencies by package
jdeps --summary app.jar
```

`jdeps` performs static bytecode analysis. It does not detect all classes loaded via reflection, plugin names in config, native code, or inter-service communication.

### 8.2. `jdeprscan`

Use `jdeprscan` to scan for deprecated API usage against the target release:

```bash
jdeprscan --release 17 --class-path "lib/*" app.jar
```

Results highlight APIs to migrate before or during the upgrade. Read results alongside JDK 17 API documentation: deprecated does not mean removed, and the tool does not replace compilation/tests to catch all removed APIs.

### 8.3. `jar`, `jmod`, and `java`

Useful commands:

```bash
jar --describe-module --file app.jar
jmod describe java.base.jmod
java --list-modules
java --version
javac --version
```

Run them from the exact `JAVA_HOME` used by the pipeline. If multiple JDKs are installed on a machine, `java --version` in a terminal does not necessarily reflect the JDK used by the Gradle daemon, Maven toolchain, or container build.

### 8.4. Auditing internal APIs and warnings

Search source and scripts for indicators:

```text
sun.*
com.sun.*
--illegal-access
--add-opens
--add-exports
Pack200
pack200
unpack200
nashorn
java.rmi.activation
rmic
rmid
jaotc
javapackager
rt.jar
tools.jar
lib/ext
java.ext.dirs
java.endorsed.dirs
```

These are discovery keywords, not proof that every match is an error. For example, a `com.sun.*` package might belong to a third-party library rather than JDK internals. Identify the owning module and dependency source before changing anything.

## 9. Choosing a packaging strategy

Not every application needs the same package format. The decision depends on deployment model, runtime control, and operational requirements.

| Deployment style | Suggested packaging | What to check |
|---|---|---|
| Containerized server app | JAR/WAR and standard JDK/JRE runtime image in container | Base image, architecture, CA certificates, timezone, native libs, JVM options |
| Server app needing minimal runtime | `jlink` runtime image + application artifact | Module closure, service providers, locales, security providers, and smoke tests |
| Desktop Java | `jpackage` app image or installer | Launcher, icons, signing, native packaging tools, and update strategy |
| Internal CLI tool | JAR + centrally managed runtime or `jpackage` | JDK distribution method, PATH, launcher, config, and logging |
| Modular application | Module path + `jlink`, optionally combined with `jpackage` | `module-info`, `uses/provides`, module graph, and module versions |
| Traditional classpath app | Explicit JAR/dependencies, optionally `jpackage` | Manifest, classpath, packaged dependencies, and runtime image |

### 9.1. Packaging in containers

For server applications, a common pattern builds the artifact with JDK 17 and copies it into a matching runtime image. You can use a vendor-standard runtime image or a `jlink`-built image.

Illustrative multi-stage Dockerfile example:

```dockerfile
FROM eclipse-temurin:17-jdk AS build
WORKDIR /workspace
COPY . .
RUN ./gradlew clean bootJar

FROM eclipse-temurin:17-jre
WORKDIR /app
COPY --from=build /workspace/build/libs/app.jar app.jar
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
```

Image names and tags should be locked down per organization vendor, architecture, and update policy. With a minimal `jlink` runtime image, the final stage can copy that image and a suitable launcher. Check CA certificates, timezone, user permissions, native libraries, and diagnostic tools needed by operations teams.

### 9.2. Packaging desktop or workstation-installed apps

For desktop applications, `jpackage` can generate an app image folder or native installer. Test:

- Installation and uninstallation on clean machines.
- Shortcuts, icons, file associations, and launcher arguments.
- Data write permissions, config locations, and logs.
- Updating/upgrading installers from prior versions.
- Signing and release provenance verification.
- Behavior when the bundled runtime image is updated.

Do not treat `jpackage` returning exit code 0 as proof that the installer works properly. Install and run the actual artifact on the target environment.

## 10. JDK 11 to 17 migration workflow for build and packaging

### Step 1: Freeze the JDK 11 baseline

Record:

- JDK vendor, version, and architecture.
- Gradle/Maven wrapper and plugin versions.
- Compile release, toolchain, and runtime JDK.
- Current artifact: JAR/WAR, container image, installer, or runtime image.
- List of packaging scripts and tools invoked in CI/CD.
- System properties, JVM arguments, and module options in use.

Archive baseline artifacts and build logs for post-migration comparison.

### Step 2: Inventory assumptions about JDK layout

Search for `rt.jar`, `tools.jar`, `jre` directory paths, `lib/ext`, endorsed directories, and code directly reading JDK contents. Distinguish active scripts from obsolete docs or dead code.

Replace internal file access with toolchains or standard tools. Do not recreate legacy directory structures inside JDK 17.

### Step 3: Check removed tools

Search for `pack200`, `unpack200`, `rmic`, `rmid`, `jaotc`, `javapackager` commands and APIs like `Pack200` and `java.rmi.activation`. Inspect scripts outside Java source, Gradle tasks, Maven plugins, Dockerfiles, and release pipelines.

Classify each hit as: actively called, docs only, legacy-environment only, or unused. Replace only active paths and clearly define the replacement functionality.

### Step 4: Analyze dependencies and JDK internals

Run `jdeps --jdk-internals` and `jdeprscan --release 17` on the application artifact and dependencies. Upgrade core libraries to JDK 17-compatible versions. Pay close attention to frameworks, ORMs, bytecode enhancers, mocking libraries, serialization, logging, JDBC drivers, and native libraries.

If `--add-opens`/`--add-exports` remain, record package, target module, requesting library, and rationale. Tie each flag to a specific dependency so it can be removed when that library upgrades.

### Step 5: Upgrade build tools and compiler environments

Verify Gradle/Maven wrapper, plugins, and CI runners support running on JDK 17. Separate the build-running JDK from the compilation toolchain. If Java 11 runtime support must be retained, use the JDK 17 compiler with `--release 11`/equivalent config after verifying build tool and plugin support.

If moving production runtime to Java 17, set compile release and runtime JDK per target policy after assessing source compatibility.

### Step 6: Compile and test on JDK 17

Run a clean build on JDK 17. Categorize failures into:

- Removed APIs or APIs no longer supplied by the JDK.
- Blocked access to JDK internals.
- Dependencies/plugins unsupported on JDK 17.
- Compiler or module graph changes.
- Runtime behavior, serialization, TLS, locale, or native library shifts.

Once building succeeds, run unit tests, integration tests, and startup checks on a real runtime. Tests must cover flows exercising reflection, scripting, RMI, provider discovery, or rare resources if the system uses them.

### Step 7: Redesign packaging

Choose one of the appropriate paths:

- Keep JAR/WAR and run inside a standard JDK 17 runtime image in containers/servers.
- Create a dedicated runtime image via `jlink` if module control and runtime size matter.
- Use `jpackage` to create app images or native installers for desktop/workstation distribution.

Not every app needs both `jlink` and `jpackage`. Choose based on deployment, operations, security, and update requirements.

### Step 8: Test the packaged artifact

Test the artifact in a clean environment without relying on JDKs or libraries cached on the build host. For containers, run the final image; for installers, install and launch on the target OS; for custom runtimes, test using `bin/java` inside the runtime image.

### Step 9: Controlled release with rollback capability

Roll out by application group or environment. Monitor startup, error rates, latency, memory, CPU, TLS/connectivity, and classloading errors. If schemas or contracts changed concurrently, isolate causes clearly during rollback. Record JDK vendor/build, base image digest, dependency lock/resolution, and packaging flags of the released artifact.

## 11. Common errors when upgrading JDK 11 to 17

| Symptom | Possible cause | Remediation path |
|---|---|---|
| `InaccessibleObjectException` | Deep reflection into closed JDK package | Upgrade library; replace API; use narrow `--add-opens` if transitional |
| `IllegalAccessError` | Package not exported by module or changed access rule | Check module/package; consider tightly scoped `--add-exports` |
| `ClassNotFoundException` for Nashorn | Engine no longer bundled in JDK 17 | Add suitable standalone engine or change scripting design |
| `Pack200` or `pack200` not found | API/tool removed from JDK | Replace pipeline step with standard JAR/ZIP |
| `java.rmi.activation` not found | RMI Activation removed in JDK 17 | Redesign activation/lifecycle |
| `rmic` does not exist | Tool removed prior to JDK 17 | Review stub generation needs and RMI mechanism |
| `jlink` reports missing module | Incomplete module path or module list | Run `jdeps`, inspect module descriptors and service providers |
| App runs on full JDK yet fails in custom image | Runtime image lacks module/provider/resource | Check module closure and test with final image |
| `jpackage` fails to build installer | Missing native packaging tool or wrong OS runner | Prepare platform-matching toolchain/runner; check `jpackage --help` |
| Installer builds yet app fails on clean machine | Wrong runtime, config, native library, or launcher | Install and test on clean machine, verify every packaged file |

## 12. Packaging migration completion checklist

Before declaring a pipeline ready for JDK 17, verify:

- [ ] JDK vendor, version, architecture, and build toolchain are documented.
- [ ] No active scripts depend on `rt.jar`, `tools.jar`, nested JRE inside JDK, or `lib/ext`.
- [ ] No packaging step calls Pack200/unpack200.
- [ ] Verified whether the app uses Nashorn, RMI Activation, `rmic`, or `jaotc`.
- [ ] Audited JDK internal access via `jdeps` and runtime testing.
- [ ] Any remaining `--add-opens`/`--add-exports` flags have rationale, owners, and removal plans.
- [ ] Build tool, plugins, and dependencies support JDK 17.
- [ ] Classpath/module-path layout and runtime image strategy are explicitly decided.
- [ ] If using `jlink`, module lists and service providers are verified using the real runtime image.
- [ ] If using `jpackage`, native toolchains, signing, and OS-specific build runners are ready.
- [ ] Final artifact has run in a clean production-equivalent environment.
- [ ] CI stores JDK info, dependencies, image digests, and packaging flags for artifact reproducibility.
- [ ] Rollback plan and post-release monitoring are in place.

## 13. Conclusion

When moving from JDK 11 to 17, audit module image layout, JDK internal access, removed tooling, and how runtime/application packages are built. `jlink` has existed since Java 9 and can construct minimal runtime images; `jpackage` is a key addition since JDK 16 supporting app images and native installers in JDK 17. Meanwhile, Pack200, Nashorn, RMI Activation, and several legacy AOT/RMI tools departed the JDK in releases between 11 and 17.

Start by inventorying active scripts and artifacts, analyze dependencies with `jdeps`/`jdeprscan`, migrate internal access to supported APIs, and pick a fitting packaging strategy. Tests must run against the final runtime image, container, or installer itself; building successfully with a full JDK does not prove the deployed package works properly.

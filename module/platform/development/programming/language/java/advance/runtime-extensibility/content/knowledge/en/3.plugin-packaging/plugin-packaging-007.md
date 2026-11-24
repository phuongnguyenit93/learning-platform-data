# Testing Actual Plugin Packages Instead of Running Only on the IDE Classpath

## 1. The Problem: Working in the IDE Does Not Prove the Artifact Will Work

In a Java application extensible at runtime, plugins are typically distributed as JARs. When running tests in IntelliJ IDEA, Eclipse, or unit test suites, the IDE constructs a classpath from `build/classes`, `target/classes`, `resources`, and resolved dependencies. This environment can **differ drastically from the contents and loading behavior of the final JAR**.

For example, the IDE sees:

```text
app/build/classes/java/main/
plugin/build/classes/java/main/
plugin/build/resources/main/META-INF/services/com.example.spi.Plugin
~/.gradle/caches/.../helper-library.jar
```

Whereas the real application ships two files:

```text
dist/app.jar
dist/plugins/my-plugin.jar
```

A test running on the IDE's classpath can pass even if the release artifact is missing `META-INF/services`, missing runtime libraries, contains old package names after relocation, places dependencies in the wrong location, or is unreadable by the actual classloader.

**The right testing goal:** prove that the bytes of the delivered artifact, under the intended loading configuration and Java runtime, are sufficient to locate, instantiate, and invoke the plugin. This tests the output of the build process, not merely the source code.

## 2. Distinguishing Three Levels of Testing

| Level | Input | What It Proves | What It Does Not Prove |
| --- | --- | --- | --- |
| Unit test | Compiled classes and test dependencies | Isolated logic, input/output handling | Whether the plugin is inside the JAR and discoverable by the host |
| Integration test on dev classpath | Classes and resources built by IDE/Gradle/Maven | API contract and integration in the build environment | Correct archive contents, manifest, plugin paths, and runtime dependencies |
| Artifact smoke/integration test | JAR after `package`/`jar`/`shadowJar` with the deployment launch command | Classes/resources, SPI metadata, loading, and behavior in the real artifact | All production environments, unless relevant configurations are simulated |

These three testing levels complement each other. Do not drop unit tests; simply **add a final-artifact verification step** for capabilities that depend on packaging.

## 3. Defining the Distribution Contract Before Testing

Before writing test commands, determine:

1. **Which artifact is distributed?** Regular JAR, executable/fat JAR, shaded JAR, a set of JARs in `plugins/`, or module JARs on the module path.
2. **Who owns the SPI API?** Does the host provide `com.example.spi.Plugin` or does the plugin package it? If two classloaders load two copies of an identically named class, `not a subtype` or `ClassCastException` errors can occur.
3. **How are plugins discovered?** `ServiceLoader`, class names in a config file, reflection, or a framework-specific registry? Do not check `META-INF/services` if the system does not use SPI.
4. **How are dependencies supplied?** Bundled inside a fat JAR, placed alongside in `lib/`, or provided by the host? `compileOnly`/`provided` dependencies must actually be satisfied by the runtime environment.
5. **Which classloader and runtime are used?** `URLClassLoader`, thread context classloader, application classloader, module layer, Java 17/21, operating system, external plugin paths.

Test results must be tied to **one specific distribution method**. Passing `java -cp "build/classes:..."` must not be taken as proof for `java -jar dist/app.jar`.

## 4. Complete Example: Creating and Testing an Actual Plugin JAR

This example uses Java 17+, a host owning the `ToolPlugin` interface, and a separate plugin loaded via `URLClassLoader`. No Gradle/Maven is needed to see the packaging steps clearly; when using a real build system, replace the JAR creation commands with the artifacts produced by your pipeline.

File structure:

```text
sample/
  api/com/example/spi/ToolPlugin.java
  plugin/com/example/plugins/UppercasePlugin.java
  host/Host.java
  plugin-resources/META-INF/services/com.example.spi.ToolPlugin
```

`api/com/example/spi/ToolPlugin.java`:

```java
package com.example.spi;

public interface ToolPlugin {
    String id();
    String apply(String input);
}
```

`plugin/com/example/plugins/UppercasePlugin.java`:

```java
package com.example.plugins;

import com.example.spi.ToolPlugin;
import java.util.Locale;

public final class UppercasePlugin implements ToolPlugin {
    public UppercasePlugin() {}

    @Override
    public String id() {
        return "uppercase";
    }

    @Override
    public String apply(String input) {
        return input.toUpperCase(Locale.ROOT);
    }
}
```

Contents of `plugin-resources/META-INF/services/com.example.spi.ToolPlugin`:

```text
com.example.plugins.UppercasePlugin
```

`host/Host.java`:

```java
import com.example.spi.ToolPlugin;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.ServiceLoader;

public final class Host {
    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException("Usage: Host <plugin-jar>");
        }

        Path pluginJar = Path.of(args[0]).toAbsolutePath();
        URL url = pluginJar.toUri().toURL();

        // Parent sees ToolPlugin API; child contains implementation and SPI resource.
        try (URLClassLoader loader = new URLClassLoader(
                new URL[] {url}, Host.class.getClassLoader())) {

            ServiceLoader<ToolPlugin> services =
                    ServiceLoader.load(ToolPlugin.class, loader);
            List<ToolPlugin> plugins = new ArrayList<>();
            for (ToolPlugin plugin : services) {
                plugins.add(plugin); // Actually instantiate the provider, not just count metadata.
            }

            if (plugins.size() != 1) {
                throw new AssertionError(
                        "Expected 1 plugin, found " + plugins.size());
            }

            ToolPlugin plugin = plugins.get(0);
            if (!"uppercase".equals(plugin.id())) {
                throw new AssertionError("Unexpected plugin: " + plugin.id());
            }
            String output = plugin.apply("artifact test");
            if (!"ARTIFACT TEST".equals(output)) {
                throw new AssertionError("Unexpected output: " + output);
            }
            System.out.println(plugin.id() + ": " + output);
        }
    }
}
```

Inside the `sample` directory, build **two separate JARs**:

```bash
mkdir -p out/api out/plugin out/host dist
javac -d out/api api/com/example/spi/ToolPlugin.java
javac -cp out/api -d out/plugin plugin/com/example/plugins/UppercasePlugin.java
javac -cp out/api -d out/host host/Host.java
jar --create --file dist/plugin.jar -C out/plugin . -C plugin-resources .
jar --create --file dist/host.jar -C out/api . -C out/host .
java -cp dist/host.jar Host dist/plugin.jar
```

Output:

```text
uppercase: ARTIFACT TEST
```

In Windows PowerShell, `mkdir -p` is Unix shell syntax; you can create directories beforehand with `New-Item -ItemType Directory -Force`. The remaining `javac`, `jar`, and `java` commands have the same meaning.

Key point: the host runs from **`dist/host.jar`** and the plugin is loaded from **`dist/plugin.jar`**; neither `out/plugin` nor `plugin-resources` is placed on the launch command's classpath. If packaged without the resource:

```bash
jar --create --file dist/plugin-broken.jar -C out/plugin .
java -cp dist/host.jar Host dist/plugin-broken.jar
```

The host throws an `AssertionError` with the message `Expected 1 plugin, found 0`. This is the kind of bug that a test running `out/plugin` with `plugin-resources` separately on the classpath would miss.

**Limitation of the example:** `URLClassLoader` here loads a trusted plugin and creates no security boundary. Plugin code runs with the permissions of the host JVM. In systems with untrusted plugins, a dedicated isolation model such as a separate process/container is required; a classloader is not a sandbox. In real applications, restrict the allowed JAR list and shared APIs.

## 5. Inspecting JAR Structure with JDK Tools

### Verifying Entries Actually Exist

```bash
jar --list --file dist/plugin.jar
```

The output should contain at least:

```text
META-INF/
META-INF/MANIFEST.MF
META-INF/services/
META-INF/services/com.example.spi.ToolPlugin
com/
com/example/
com/example/plugins/
com/example/plugins/UppercasePlugin.class
```

The order of entries in the output may vary; **presence and exact paths** are what matter. Case sensitivity and package names in paths are significant.

For real artifacts, verify:

- `META-INF/services/<fully.qualified.ServiceName>` and descriptor contents when using classpath SPI.
- `.class` files for providers, dependencies, and the API if they are meant to be packaged.
- `META-INF/MANIFEST.MF`: `Main-Class`, `Class-Path`, `Multi-Release`, or relevant attributes if the launch mode uses them.
- Configuration/schema/template resources read by the plugin via `getResource`/`getResourceAsStream`.
- Native library paths and signatures if the plugin uses JNI; test on the target OS/architecture.
- `module-info.class` and module descriptors if running on the module path.

A ZIP-valid JAR does not guarantee Java can load the plugin. `jar --describe-module --file dist/plugin.jar` helps inspect module information when applicable; interpret its output according to whether it is a named, automatic, or classpath JAR.

### Inspecting Service Descriptor Contents

In environments with `unzip`:

```bash
unzip -p dist/plugin.jar META-INF/services/com.example.spi.ToolPlugin
```

Expected output:

```text
com.example.plugins.UppercasePlugin
```

Use `jar --extract --file dist/plugin.jar META-INF/services/com.example.spi.ToolPlugin` when extracting with the JDK, but note that extract writes files into the working directory; run it inside a temporary directory.

The descriptor path is based on the **fully qualified binary name of the service interface**, not the artifact name or implementation name. Its contents must point to the provider after relocation/shading, not the pre-relocation class name.

## 6. Runtime Dependencies: Testing a Minimal Environment

A plugin may compile because the IDE or test runner includes supporting libraries that the release JAR does not carry. For example:

```text
plugin.jar
  com/example/plugins/ReportPlugin.class
  META-INF/services/com.example.spi.ToolPlugin

IDE runtime:
  plugin.jar + report-utils.jar

Production:
  plugin.jar             # missing report-utils.jar
```

Depending on where the class is loaded, the runtime may throw `NoClassDefFoundError`, `ClassNotFoundException`, `ServiceConfigurationError`, or a provider initialization error. There is no single exception for every kind of missing dependency.

How to verify:

1. Place output artifacts in a clean distribution directory (`dist/`), without adding `build/classes`, `target/classes`, or libraries incidentally supplied by the IDE.
2. Run the exact production command: `java -cp`, `java -jar`, launcher script, or module path.
3. Place only dependencies **permitted by the distribution contract** on the classpath/module path.
4. Exercise loading, instantiation, and real calls that reach dependent classes; merely seeing the provider name does not prove the entire execution path works.
5. If multiple Java/OS versions are supported, run smoke tests across supported environments in CI.

For thin JARs, dependencies may need to sit alongside the artifact in `lib/`; for fat JARs, verify libraries are merged/embedded according to the launcher's expectations. Do not assume `java -jar` automatically reads every JAR in the same directory. With `java -jar`, external classpaths are handled differently depending on the launcher/manifest; `-cp` on the command line does not override `-jar`'s classpath handling.

## 7. Testing the Exact Classloader and ServiceLoader

`ServiceLoader.load(Service.class)` defaults to the **thread context classloader**; `ServiceLoader.load(Service.class, loader)` uses the supplied loader. Tests run inside an IDE may have a broader context loader than the real runtime. Therefore, smoke tests must invoke it the same way the host does.

Scenarios to test when applicable:

| Scenario | Verification |
| --- | --- |
| Plugin JAR added dynamically | Create a loader pointing directly to the distributed JAR; load through that loader |
| Service API owned by the host | Provider is compatible with **the exact same `Class<?>` service type** used by the host |
| Multiple plugins from multiple JARs | All providers are found without `META-INF/services` overwriting each other |
| Package relocation | Descriptor, provider name, and final bytecode stay synchronized |
| Adding/removing JARs at runtime | Loader lifecycle, `ServiceLoader.reload()` when appropriate; do not expect replacing files to auto-update |
| JPMS named modules | Valid `uses`/`provides` and services discovered in the proper module layer |

Avoid treating a successful `Class.forName("...")` as sufficient: it does not verify whether `ServiceLoader` finds the provider, nor whether the class can be instantiated or fulfill the plugin contract.

### Catching Failures Early

When at least one plugin is required, treat an empty provider list as a **test failure**. `ServiceLoader` returning an empty collection can be valid API behavior, so an assertion matching product requirements is necessary.

If plugins are selected by `id()`, check the **expected set of IDs** rather than just `count()`: the right count can still contain the wrong providers. Invoke an actual operation on each plugin to surface linkage and resource errors that only appear during execution.

## 8. Testing the Exact Build Output with Gradle and Maven

### Gradle

With Gradle, run the build task used for release and then test that task's exact output file:

```bash
./gradlew clean jar
jar --list --file build/libs/your-plugin.jar
```

This example is for projects using the Gradle Wrapper on Unix; on Windows it is `gradlew.bat`. The specific JAR name depends on `archiveBaseName`, version, and classifier. With Shadow, run `shadowJar` and inspect the **Shadow JAR**, not the regular JAR by mistake:

```bash
./gradlew shadowJar
jar --list --file build/libs/your-plugin-all.jar
```

The example `jar` commands use common output names; replace them with the **artifact path actually produced by the task**. Once a task creates a JAR, do not treat `test` results as a substitute for post-packaging smoke tests. Gradle test tasks can use the project's runtimeClasspath, which is broader than the distribution classpath.

### Maven

```bash
mvn clean package
jar --list --file target/your-plugin.jar
```

The output name depends on `artifactId`, `version`, finalName, and Shade/Assembly settings. When using Shade/Assembly, inspect the deployed artifact and avoid mistakenly picking the original JAR. `mvn test` is not equivalent to testing `mvn package`, because resources may be transformed during the package phase.

### CI Rules

Order the pipeline as:

```text
Compile → Unit tests → Package → Inspect artifact → Launch artifact → Assert plugin discovery/behavior → Publish
```

Smoke tests must run **before publishing** and fail with a non-zero exit code. The `Host` example above throws `AssertionError` when providers are missing or wrong, so the `java` command returns non-zero and CI can block publishing.

Especially when steps like `minimize`, shading, relocation, obfuscation, resource filtering, or post-processing exist, the artifact tested must be **the file after the final transformation step**.

## 9. Typical Errors and Diagnostics

| Post-Package Symptom | Evidence to Look For | Resolution |
| --- | --- | --- |
| 0 plugins, though IDE finds them | Descriptor missing or misplaced inside the JAR | Add resource under `META-INF/services/`; check resource processing |
| Some plugins missing after merging JARs | Two dependencies share the same descriptor name and one overwrote the other | Use a service-file merging transformer |
| `ServiceConfigurationError: Provider ... not found` | Descriptor lists old name or provider class is absent from artifact | Synchronize relocation and metadata; check minimizer rules |
| `not a subtype` / `ClassCastException` | SPI API packaged twice or loaded by different loaders | Share the single service API from the host; control parent/child loaders |
| `NoClassDefFoundError` when running provider | Dependency present in IDE but missing in distribution | Bundle the dependency or supply it on the runtime path per contract |
| Resource loading returns `null` | Resource was not copied into JAR or path changed | Check JAR entries and `getResource` paths |
| `java -jar` behaves differently from `java -cp` | Different manifest/launcher/classpath packaging | Run the exact distribution command, verify `Main-Class` and launcher |
| Plugin works on dev machine but fails on Linux | Case sensitivity, paths, permissions, JNI binaries, or encoding | Test in a production-compatible environment |
| JPMS module not discovered | `module-info` or module layer mismatch | Verify `uses`/`provides`, module path, and layer |

Do not fix failures by dumping every IDE dependency onto the production classpath: that hides distribution defects and invites version conflicts.

## 10. Controlling Reproducibility and Artifact Provenance

Another risk is testing a **different file** from the one that gets published. For instance, a pipeline builds multiple variants, tests `plugin.jar`, yet uploads `plugin-all.jar`. To ensure traceability:

- Record the path and SHA-256 of the tested artifact (`sha256sum dist/plugin.jar` or PowerShell `Get-FileHash dist/plugin.jar -Algorithm SHA256`).
- Publish that exact artifact; if it is re-signed, optimized, or repackaged after testing, verify and test the post-transformation artifact.
- Build in a CI environment where Java, dependencies, and build plugin versions are controlled; avoid stale files left over from previous builds.
- For plugins loaded from `plugins/`, verify the distribution directory layout and corresponding configuration/launcher files as well.

Hashes confirm **the exact same bytes** were tested and published; they do not prove the plugin works on their own. Confidence only comes when paired with smoke tests in the right environment.

## 11. Pre-Release Checklist

- [ ] Build using the exact task/profile that produces the release artifact.
- [ ] Open the final JAR and verify required classes, resources, SPI descriptors, and manifest/module metadata are present.
- [ ] Cross-check provider names in service descriptors against the classes actually packaged, including after relocation.
- [ ] Do not let runtime tests silently use `build/classes`, `target/classes`, test dependencies, or an IDE-managed classpath.
- [ ] Run the host/launcher using the supported command and Java version; load the plugin from the exact distributed JAR file.
- [ ] Assert provider count and identities, instantiate providers, and invoke a real operation.
- [ ] Run missing-resource/dependency failure cases where possible to confirm tests catch defects.
- [ ] Test every distributable variant, including regular JAR, shaded JAR, or module JAR per the actual contract.
- [ ] Bind the tested artifact to the published artifact via hash or shared pipeline output.

**Technical conclusion:** testing plugins on the IDE classpath proves code works in a development environment. Only **opening and running the exact packaged artifact** under the true classloader, dependency set, and runtime command proves the distribution can discover, instantiate, and execute plugins as expected.

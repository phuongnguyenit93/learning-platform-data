# Packaging a Runtime with jlink Including Required Tool Modules and Service Binding

A Java application may run fine in development because the machine has a **full JDK**, yet fail when deployed as a **custom runtime image** built with `jlink`. Common symptoms include: `ToolProvider.getSystemJavaCompiler()` returning `null`, missing JShell or a needed tool, `ServiceLoader` finding no providers, or dependent modules missing from the runtime image. The cause is not necessarily a code bug: **the linked image contains only the selected modules plus dependencies and providers pulled in by the resolver at link time**.

This lesson shows how to **choose root modules, retain the right tool modules (`jdk.compiler`, `jdk.jshell`, and related modules), use `--bind-services` to link required providers, verify with a runnable Java 17 program**, and manage image size and compatibility during deployment.

**Core message:** `jlink` is a step that **packages a module graph into a dedicated Java runtime image**, not a command to "copy the whole JDK". `requires` expresses dependencies, while `uses`/`provides` express services; **a module containing an implementation or service provider may be absent from the graph unless selected as a root or added via service binding**.

## 1. How Runtime Image, JDK, JRE, and jlink Differ

| Concept | Meaning |
|---|---|
| **Full JDK** | Development kit containing the JVM, standard modules, and tools like `javac`, `jar`, `jlink`, `jdeps`, `jshell` depending on distribution |
| **Custom runtime image** | Directory containing `bin/java`, JVM libraries, module image, and components chosen by the linker; built via `jlink` |
| **`java.base`** | Foundational module always required by any Java runtime |
| **Application module** | Module defined by the project in `module-info.java`, e.g. `demo.host` |
| **Tool module** | Module providing tool APIs/implementations, e.g. `jdk.compiler` or `jdk.jshell` |
| **Service provider module** | Module declaring `provides Service with Implementation` and discovered via `ServiceLoader` |
| **Module path** | Set of `.jmod` files, modular JARs, or compatible modules searched by `jlink` at link time |
| **Service binding** | Process of adding provider modules for services declared with `uses` by modules in the graph, along with their dependencies |

During the build:

```text
JDK jmods + modular application JARs
                   |
                   v
     --module-path + --add-modules
                   |
           resolve requires
                   |
        (optional --bind-services)
                   |
     find providers via uses/provides
                   |
            resolved graph
                   |
                   v
                 jlink
                   |
                   v
       Custom runtime image/
         bin/java, lib/modules,...
                   |
                   v
       Run java -m module/main
                   |
            Self-test + smoke test
```

`jlink` ships with modern JDKs; typically it links **JDK modules and modular application modules**, refusing to treat a plain JAR with only an automatic module name as a complete explicit module. If a third-party library is only an automatic module or classpath JAR, you must decide how to modularize it or keep it on an external runtime classpath/module path rather than assuming it is a valid link input.

A runtime image built with JDK 24 carries a **JDK 24** runtime, even if application source was compiled with `javac --release 17`. `--release 17` targets class/language/API level; it **does not turn JDK 24's `jlink` into a JDK 17 runtime builder**. To produce a Java 17 runtime image, build with a **JDK 17 toolchain matching the target platform**.

## 2. How jlink Determines Which Modules Enter the Image

A simple command:

```bash
jlink --module-path "$JAVA_HOME/jmods:mlib" \
      --add-modules demo.host \
      --output image
```

This command uses Linux/macOS shell syntax. `mlib` is the directory holding the application's modular JARs; on Windows, the module path separator is a **semicolon**. `demo.host` is the root module; `jlink` follows `requires` clauses in descriptors to pull in needed modules. `java.base` is included automatically by the module system.

**Differences between relationships:**

- `requires some.module;`: a **named dependency** the module system must resolve to build the graph.
- `uses com.example.Service;`: the module declares it **consumes a service**; this does not mean every provider of that service automatically enters the image in default link mode.
- `provides com.example.Service with com.example.Impl;`: a module **supplies a provider**, yet there must be a reason for it to enter the graph: as a root, as a selected dependency, or via service binding.
- `--bind-services`: instructs the linker to include service provider modules and their dependencies from the configuration/module path, which can make the graph and image size **significantly larger**.

### 2.1. Root Modules Must Reflect What Needs to Run

Consider an application composed of:

```text
demo.host
  requires demo.spi
  requires java.compiler
  uses demo.spi.GreetingService

demo.provider
  requires demo.spi
  provides demo.spi.GreetingService with demo.provider.HelloProvider
```

If only `demo.host` is rooted, `demo.spi` and `java.compiler` are pulled in via `requires`, yet `demo.provider` **does not** enter automatically merely because its JAR sits on the module path. With `--bind-services`, the linker sees that `demo.host` uses `demo.spi.GreetingService`, finds `demo.provider`, and includes it in the image.

**Do not blindly enable every module with `ALL-MODULE-PATH`** to fix a missing provider: that defeats minimization and can bundle unwanted code into the image. Start from explicit roots, inspect dependencies, and add tools/providers intentionally.

## 3. Tool Modules to Understand and Include Deliberately

| Module | Primary Role | When to Include in the Image? |
|---|---|---|
| `java.base` | Core Java APIs | Included by the module system; no manual handling needed |
| `java.compiler` | Standard APIs `javax.tools.JavaCompiler`, `ToolProvider`, `DiagnosticCollector` | App performs dynamic compilation or uses compiler SPI/APIs; typically pulled by `requires java.compiler` |
| **`jdk.compiler`** | JDK `javac` implementation, system compiler/provider, and related tools | When the image must **actually compile Java** via `ToolProvider.getSystemJavaCompiler()` or run `javac` |
| **`jdk.jshell`** | JShell API and JDK REPL tool | When the app uses `jdk.jshell.JShell` or needs to distribute JShell capability |
| `java.scripting` | JSR 223 `javax.script` API | When host uses `ScriptEngine`/`Bindings`; **does not** imply a JavaScript engine exists |
| `jdk.jdeps` | Module/dependency analyzer such as `jdeps` | If running analysis tools in that environment; usually needed only in build pipelines |
| `jdk.jlink` | Runtime image linker tool | If running linking operations in that environment; usually needed only in build JDK |
| `jdk.jartool` | JAR manipulation tool such as `jar` | Usually needed only at build stage, not in runtime images |
| `jdk.javadoc` | Javadoc generator tool | Usually needed only in build/docs stages |
| `jdk.zipfs` | FileSystemProvider for ZIP/JAR via NIO FileSystem API | Needed when code calls `FileSystems.newFileSystem` on ZIPs or a dependency requires that provider |

**Distinguish API from implementation:**

```java
import javax.tools.JavaCompiler;
import javax.tools.ToolProvider;

JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
if (compiler == null) {
    throw new IllegalStateException("Compiler implementation is missing");
}
```

This snippet belongs **inside a method**, not as a standalone program. It compiles because the API module `java.compiler` is present, yet `compiler` can still be `null` if the image lacks a matching implementation—typically because `jdk.compiler` is absent. Thus **having `java.compiler` alone is not enough** for runtime Java compilation.

**A note on JShell:** Having `java.compiler` does not imply `jdk.jshell` is present. If the application uses `JShell` statically, the host descriptor needs `requires jdk.jshell;` so the module system pulls it in. If the host uses JShell via configuration/reflection or distributes the JShell tool, add `jdk.jshell` explicitly and test on the real image. In the example below, `jdk.jshell` is added as an optional root and verified via `ModuleLayer.boot().findModule(...)`.

JDK builds/images may provide **launchers** for tool modules (e.g. `bin/javac`, `bin/jshell`); inspect the actual files inside the generated image's `bin` rather than guessing from module names. On the tested JDK 24, including `jdk.compiler` and `jdk.jshell` also produced the corresponding launchers. Do not ship build tools inside production images if the runtime environment does not need them.

### 3.1. java.scripting Does Not Bundle a JavaScript Engine

`ScriptEngineManager` lives in `java.scripting`, yet **the Nashorn JavaScript engine was removed from the JDK in Java 15**. Adding `java.scripting` to a Java 17+ image guarantees only the JSR 223 API; `getEngineByName("JavaScript")` can still return `null`. External engines must be selected, packaged, and configured with host access permissions separately.

Similarly, an externally supplied service provider **does not appear automatically** just because `ServiceLoader` exists in `java.base`. You need both the right provider and proper visibility.

## 4. jlink and Service Binding: What Does --bind-services Mean?

The JPMS provider mechanism uses three pieces:

```java
// module-info.java in the service-consuming module
uses demo.spi.GreetingService;

// module-info.java in the service-providing module
provides demo.spi.GreetingService
        with demo.provider.HelloProvider;
```

These are two **illustrative descriptor directives**, not valid directly inside a Java class body. In real programs, each belongs in its respective module's `module-info.java`.

An application can use:

```java
ServiceLoader<GreetingService> loader =
        ServiceLoader.load(GreetingService.class);

for (GreetingService provider : loader) {
    System.out.println(provider.message());
}
```

This snippet assumes a class importing `java.util.ServiceLoader` and `demo.spi.GreetingService`. For modules linked into the boot layer, the loader finds providers according to module relationships and service visibility.

**Without `--bind-services`:** default linking follows roots and dependencies. A module acting solely as a provider that is neither rooted nor required may **be omitted from the image**, leaving `ServiceLoader` unable to find it.

**With `--bind-services`:** `jlink` adds service provider modules and their needed dependencies from the module path, subject to graph/module visibility. This covers both application providers and standard JDK providers (e.g., providers for tools, locale/crypto/encoding depending on the system). For that very reason, it **does not mean "bind only the exact provider I am thinking of"**: the image may end up containing **more modules than expected**.

### 4.1. When Should You Enable Service Binding?

Enable it when:

- The host uses `ServiceLoader` to discover plugins/providers that are not static dependencies or roots.
- A custom JDK image needs JDK service providers for specific capabilities.
- You control the module path, provider identities, and resulting graph, and accept the larger image size.

Do not enable it indiscriminately when:

- The module path contains experimental, untrusted, or unreleased providers.
- Strict runtime image minimization is required and only a few fixed provider implementations are needed.
- Your architecture intentionally **loads plugins outside the image at runtime**: `--bind-services` runs **at image build time**, not as a replacement for loading new plugins/layers after the JVM starts.

There are two valid options when providers are required:

1. **Explicit provider roots** in `--add-modules` (easy to lock down the exact module set, though you maintain the list).
2. **Using `--bind-services`** so the resolver pulls providers from the module path (flexible, though you must audit the output graph and provider scope).

Either way, **service binding does not decide which provider takes precedence when multiple implementations are available**. The application must define a selection policy by ID/version/priority/capability rather than treating `ServiceLoader` order as a cross-environment business contract.

## 5. Runnable Java 17 Example: Image with Compiler and Service Provider

This example builds three **explicit modules** and creates **two images**:

- Image A: includes `demo.host` and `jdk.compiler`, **without service binding**, and without requesting `jdk.jshell`.
- Image B: includes `demo.host`, `jdk.compiler`, and `jdk.jshell`, **with `--bind-services` enabled**.
- Both use the same three modular JARs on the module path, including `demo.provider.jar`, proving: **having a JAR on the module path does not mean the provider gets linked into the image**.
- The host calls `ToolProvider.getSystemJavaCompiler()` and `ServiceLoader<GreetingService>`, and checks module presence in the boot layer.

### 5.1. Source Structure

```text
project/
  src/
    demo.spi/
      module-info.java
      demo/spi/GreetingService.java
    demo.host/
      module-info.java
      demo/host/Main.java
    demo.provider/
      module-info.java
      demo/provider/HelloProvider.java
```

File `src/demo.spi/module-info.java`:

```java
module demo.spi {
    exports demo.spi;
}
```

File `src/demo.spi/demo/spi/GreetingService.java`:

```java
package demo.spi;

public interface GreetingService {
    String message();
}
```

File `src/demo.host/module-info.java`:

```java
module demo.host {
    requires demo.spi;
    requires java.compiler;
    uses demo.spi.GreetingService;
}
```

File `src/demo.host/demo/host/Main.java`:

```java
package demo.host;

import demo.spi.GreetingService;
import java.util.ServiceLoader;
import javax.tools.ToolProvider;

public final class Main {
    public static void main(String[] args) {
        String message = ServiceLoader.load(GreetingService.class)
                .findFirst()
                .map(GreetingService::message)
                .orElse("none");

        System.out.println("service=" + message);
        System.out.println("compiler="
                + (ToolProvider.getSystemJavaCompiler() != null));
        System.out.println("jdk.compiler="
                + ModuleLayer.boot()
                    .findModule("jdk.compiler").isPresent());
        System.out.println("jdk.jshell="
                + ModuleLayer.boot()
                    .findModule("jdk.jshell").isPresent());
    }
}
```

File `src/demo.provider/module-info.java`:

```java
module demo.provider {
    requires demo.spi;
    provides demo.spi.GreetingService
            with demo.provider.HelloProvider;
}
```

File `src/demo.provider/demo/provider/HelloProvider.java`:

```java
package demo.provider;

import demo.spi.GreetingService;

public final class HelloProvider implements GreetingService {
    @Override
    public String message() {
        return "hello-provider";
    }
}
```

**Why split into three modules?** `demo.spi` holds the shared contract, `demo.host` is the consumer, and `demo.provider` is an implementation with no reverse `requires` from the host. If the host declared `requires demo.provider;`, the example would no longer properly demonstrate service binding.

`ServiceLoader.load(GreetingService.class).findFirst()` is used here only to print **the demo's single provider**. In applications with multiple providers, never pick with `findFirst()` without an ordering policy.

### 5.2. Compiling into Explicit Modules

From the `project` directory, on JDK 17 or newer:

```bash
javac --release 17 --module-source-path src -d out \
      -m demo.host,demo.provider
```

That is a Linux/macOS command; in PowerShell, write it on **one line**:

```powershell
javac --release 17 --module-source-path src -d out -m demo.host,demo.provider
```

`javac` compiles `demo.spi` as a required dependency, so `out` contains all three modules.

Package into modular JARs (`jar` commands run line by line on any OS):

```bash
mkdir -p mlib
jar --create --file mlib/demo.spi.jar -C out/demo.spi .
jar --create --file mlib/demo.host.jar -C out/demo.host .
jar --create --file mlib/demo.provider.jar -C out/demo.provider .
```

On Windows PowerShell, create the directory with:

```powershell
New-Item -ItemType Directory -Force mlib | Out-Null
```

Then run the three `jar --create ...` commands above. This step is critical: `jlink` operates on **explicit module descriptors** inside modular JARs. Do not expect the linker to work with plain JARs lacking `module-info.class` that only infer automatic module names.

### 5.3. Building Both Images on Linux/macOS

With `JAVA_HOME` pointing to a **full JDK** containing `jmods`:

```bash
jlink --module-path "$JAVA_HOME/jmods:mlib" \
      --add-modules demo.host,jdk.compiler \
      --output img-min \
      --strip-debug --no-header-files --no-man-pages

jlink --module-path "$JAVA_HOME/jmods:mlib" \
      --add-modules demo.host,jdk.compiler,jdk.jshell \
      --bind-services \
      --output img-bound \
      --strip-debug --no-header-files --no-man-pages

./img-min/bin/java -m demo.host/demo.host.Main
./img-bound/bin/java -m demo.host/demo.host.Main
```

### 5.4. Building Both Images on Windows PowerShell

The `jmods` directory lives inside the JDK, and modular JARs live in `mlib`. Unlike Unix, Windows uses **`;`** as the module path separator:

```powershell
$modulePath = "$env:JAVA_HOME\jmods;mlib"

jlink --module-path $modulePath --add-modules demo.host,jdk.compiler --output img-min --strip-debug --no-header-files --no-man-pages

jlink --module-path $modulePath --add-modules demo.host,jdk.compiler,jdk.jshell --bind-services --output img-bound --strip-debug --no-header-files --no-man-pages

.\img-min\bin\java.exe -m demo.host/demo.host.Main
.\img-bound\bin\java.exe -m demo.host/demo.host.Main
```

**Execution requirement:** do not merely run `java` from PATH—invoke the exact `bin/java` executable **inside the image**. Otherwise you may accidentally test against the full JDK instead of your custom runtime and fail to notice omitted modules.

### 5.5. Exact Verified Output

Image A **without** service binding:

```text
service=none
compiler=true
jdk.compiler=true
jdk.jshell=false
```

Image B **with** service binding and the JShell module:

```text
service=hello-provider
compiler=true
jdk.compiler=true
jdk.jshell=true
```

These outputs were verified on JDK 24 with Java sources compiled via `--release 17`. The same Java code and `jlink`/JPMS features are supported on JDK 17+, though exact base module names/versions and other runtime policies should be verified against your actual toolchain.

**Result analysis:**

1. `service=none` in image A: `demo.provider.jar` was present on the **link-time module path**, yet `demo.provider` was neither rooted nor pulled via `requires`, so it **does not exist in image A**.
2. `service=hello-provider` in image B: `--bind-services` pulled the provider module into the graph because the consumer has `uses demo.spi.GreetingService;` and the provider has `provides ... with ...;`.
3. `compiler=true` in both: `jdk.compiler` was selected as a root tool module, so `ToolProvider.getSystemJavaCompiler()` finds an implementation.
4. `jdk.compiler=true`: confirms runtime module presence, not merely that host Java sources can import `javax.tools`.
5. `jdk.jshell=false/true`: illustrates that a **tool module outside the host's static dependency graph** will not appear unless explicitly included in the graph.

You can inspect which modules were actually bundled into image B:

```bash
./img-bound/bin/java --list-modules
```

On Windows:

```powershell
.\img-bound\bin\java.exe --list-modules
```

The verified list contains `demo.host`, `demo.spi`, `demo.provider`, `java.compiler`, `jdk.compiler`, and `jdk.jshell`. The actual list includes **many additional JDK modules** due to dependencies and service binding; do not expect only those six modules.

## 6. Verifying Tools Inside the Image: Module Presence Is Not Enough

When a real runtime compiler is needed (e.g., compiling user-entered Java snippets):

1. Run `bin/java --list-modules` to confirm `jdk.compiler` and `java.compiler` are in the image.
2. Invoke `ToolProvider.getSystemJavaCompiler()` **using Java from inside the image**; it must be non-`null`.
3. Compile a small test class with `JavaCompiler` and `DiagnosticCollector` matching the real contract.
4. Verify the output path is writable and `--release` is supported by the runtime compiler.
5. If the application invokes `javac`/`jshell` executables directly, verify launchers in `bin` and run smoke tests.
6. For the JShell API, create a session and evaluate a snippet in the configured environment; seeing `jdk.jshell` in `--list-modules` alone does not guarantee process/remote execution/OS policies fit every application.

**Note on the compiler:** `jdk.compiler` supplies the in-image implementation, yet a Java runtime omitting this module may still have the `java.compiler` API and compile host sources fine at build time. Always test `ToolProvider` **on the shipped image**, not on a developer JDK.

**Note on JShell:** JShell typically needs runtime support to execute snippets and communicate with its execution engine; if a sandbox/container restricts processes or local sockets, it can fail even when linked. Never broaden OS privileges solely to "fix JShell" without evaluating the threat model.

### 6.1. Runtime Tool Modules vs. Build-Stage Tools

If your sole purpose is **packaging the app** before release, `jlink`, `jdeps`, `jar`, and `javadoc` belong in the **build environment**. Production runtime images rarely need `jdk.jlink`, `jdk.jdeps`, `jdk.jartool`, or `jdk.javadoc`.

Only when the product genuinely supports runtime Java compilation or JShell should you bundle those implementations/modules and accept the resulting footprint/attack surface cost. Select **by feature**, never bundling every tool "just in case".

## 7. jdeps, --suggest-providers, and Controlling the Graph

### 7.1. Using jdeps to Find Static Dependencies

In a build pipeline, use `jdeps` to inspect modular JAR dependencies:

```bash
jdeps --module-path mlib --print-module-deps --module demo.host
```

This analysis command runs on the **build JDK**, with `mlib` holding modular JARs. The printed module set reflects static analysis; **it does not automatically capture modules loaded via reflection, `ServiceLoader`, script engines, or dynamic configuration**. It is a good starting point for choosing roots, not proof that a runtime image is complete.

**Workflow for choosing tool modules after jdeps:**

- If code uses `javax.tools.JavaCompiler`, confirm `java.compiler` is in the dependency graph.
- If runtime compiler implementation is required, add `jdk.compiler` to roots or ensure the linker includes it, then verify `getSystemJavaCompiler()`.
- If `jdk.jshell.JShell` is required, confirm the module is added to the image.
- If using `ServiceLoader`, verify `uses`/`provides` and decide how to include providers: explicit roots or `--bind-services`.
- If libraries invoke other JDK service providers via reflection, add corresponding smoke tests (encoding, locale, TLS/crypto, filesystem providers, logging, management) per feature.

### 7.2. --suggest-providers to Explore Providers

Some `jlink` builds provide `--suggest-providers` to list modules supplying a service on the module path:

```bash
jlink --module-path "$JAVA_HOME/jmods:mlib" \
      --suggest-providers demo.spi.GreetingService
```

On Windows, replace `:` in the module path with `;`. This is an **exploratory step in the build pipeline** and does not create an image. `--suggest-providers` helps discover linkable providers, yet **never replaces validation/allowlists** governing which providers are approved for deployment. Always check actual `--list-modules` output after linking.

### 7.3. --launcher for Custom Entry Points

To create an application launcher, `jlink` provides:

```text
--launcher name=module[/mainClass]
```

For the demo module:

```bash
jlink --module-path "$JAVA_HOME/jmods:mlib" \
      --add-modules demo.host,jdk.compiler \
      --launcher greeting=demo.host/demo.host.Main \
      --output img-launcher
```

Then, depending on OS, run `img-launcher/bin/greeting` or `img-launcher\bin\greeting.exe`. `--launcher` **creates an entry point**; it does not pull unlinked provider modules into the graph—root providers or use `--bind-services` as shown above. Do not confuse jlink-generated app launchers with JDK tool executables like `javac` or `jshell`.

## 8. --bind-services Is Not a Runtime Hot-Plug Mechanism After Image Release

This is a critical boundary in **runtime extensibility**.

**Service binding at image build time:**

```text
Build time
  demo.host + demo.provider + JDK modules
      |
      | jlink --bind-services
      v
  Image containing linked modules
      |
      | JVM boots from image
      v
  ServiceLoader finds providers in the available module graph
```

**Plugins added after the JVM is running:**

```text
Runtime
  running image, module graph already defined
      |
      | copy plugin-v2.jar into directory
      v
  New module does NOT enter boot layer automatically
      |
      | ModuleFinder + Configuration.resolve /
      | resolveAndBind + ModuleLayer.defineModules...
      v
  New layer + service loading scoped to that layer/loader
```

`jlink` does not watch plugin directories. Copying/replacing a JAR after packaging **does not re-link `lib/modules`** and does not automatically add providers to the boot layer. For plugins not linked into the image, runtime design must resolve new modules into an appropriate child `ModuleLayer` or load classpath plugins via class loaders/`ServiceLoader` per architecture.

Choose between the two models:

- **Fixed, trusted providers shipped with the product**: link into the image; service binding or explicit roots are clean and easy to test.
- **Providers installed/updated dynamically after release**: keep module paths/plugin artifacts outside the image and build a lifecycle manager to discover, resolve, load, validate, switch, and close them. Never treat `--bind-services` as a hot-reload promise.

Note: **a module inside an image is a linked runtime component**, not a loose JAR swappable by filename. "Deleting/patching" a module inside an image post-link is not a plugin update workflow.

## 9. Packaging for the Right OS and Java Version

`jlink` produces an image tied to the **JDK and target platform**: OS, architecture, native libraries, and launchers. Never build a Windows image, copy it to Linux, and expect it to run.

| Concern | Rule |
|---|---|
| JDK used for linking | Pin vendor, feature version, and update level in CI |
| JDK 17 vs JDK 24 | Use **JDK 17 jlink** for a Java 17 runtime, **JDK 24 jlink** for a Java 24 runtime |
| `javac --release 17` | Sets class/source/API target; **does not** determine the runtime image version |
| OS/CPU | Build with the target JDK toolchain or a verified cross-target pipeline |
| Module path separator | Linux/macOS: `:`; Windows: `;` |
| Input modules | Prefer explicit modular JARs with `module-info.class`; never assume automatic JARs link |
| Artifact integrity | Pin and verify JDK/toolchain, module JARs, and dependencies; store hashes/checksums |
| Native dependencies | Test `java.library.path`, JNI, TLS/SSL, DNS, timezone, and locale if used |
| Production deployment | Ship the **entire image directory** and app resources; invoke `image/bin/java` |
| Runtime flags | Must match module graph and target JDK; `--add-modules` at runtime cannot conjure an unlinked module |

**A small image does not equal a correct image.** QA must run against the newly built image and verify every required runtime feature, not just `java -version`.

### 9.1. Regarding Tool Modules for Runtime Development/Compilation

Before dropping `jdk.compiler` to save space, trace real execution paths: does the app use `ToolProvider`, annotation processing, libraries compiling expressions/DSLs to Java source, script engines, or runtime tests? Some features activate only under rare configurations and won't appear in basic smoke tests.

For tool modules, maintain a specification table:

```text
feature: runtime-compile
requires: java.compiler (API), jdk.compiler (implementation)
probe: ToolProvider.getSystemJavaCompiler() != null

feature: interactive-java
requires: jdk.jshell + dependencies
probe: JShell creation and snippet evaluation

feature: provider-discovery
requires: service interfaces + selected provider modules
probe: ServiceLoader returns expected provider ID
```

These lines are a **conceptual manifest**, not a config file read by `jlink`. Such a manifest keeps features, modules, and smoke tests aligned whenever roots change.

## 10. Image Size, Attack Surface, and Reproducibility

`--strip-debug`, `--no-header-files`, and `--no-man-pages` help strip unnecessary data for distribution, yet **cannot replace choosing the right module graph**.

`--bind-services` can pull in many provider modules. A balanced workflow:

1. Build an image without binding and inspect which services are missing.
2. Determine which services are needed and which providers are actually approved/deployed.
3. Compare an image using explicit provider roots against `--bind-services` with a filtered module path.
4. Compare `--list-modules`, image size, startup time, features, and risks for each option.
5. Lock down an explicit policy: never leave experimental providers or uncontrolled modules on the CI module path.

Distinguish **service binding for packaging** from **selecting a provider at runtime**. If the module path holds two implementations of the same service, binding may link both. Every pipeline should test both the provider inventory and application selection behavior post-build.

A runtime image needs provenance records for reproduction: JDK version, `jlink` options, module path, linked modules, modular JAR build versions, checksums, and smoke test results. This also underpins rollbacks and environment debugging.

## 11. Common Pitfalls and Diagnostics

| Symptom | Typical Root Cause | Fix |
|---|---|---|
| `ToolProvider.getSystemJavaCompiler() == null` | Image has `java.compiler` API only, missing compiler implementation | Root/link `jdk.compiler` and verify on image |
| `ClassNotFoundException` invoking JShell | Missing `jdk.jshell` or broken module visibility | Add/require module, verify layer and loader |
| `ServiceLoader` finds no provider | Provider JAR was on build module path only, never linked | Enable `--bind-services` or explicit provider roots |
| `ServiceConfigurationError` | Invalid descriptor/provider constructor/access/dependency | Check `module-info.java`, provider implementation, and graph |
| Two providers present when only one wanted | `--bind-services` pulled multiple providers | Control module path, use explicit roots, or enforce selector |
| `jlink` rejects automatic module | JAR lacks explicit module descriptor | Convert to modular JAR or keep on external classpath by design |
| Image links yet post-deploy plugin unseen | Confused build-time binding with runtime hot-plug | Build dedicated runtime loader/layer and discovery |
| Works on dev machine, fails on image | Ran `java` from full JDK or missed module/provider | Invoke `image/bin/java` and `--list-modules` |
| Build produces wrong image version | Used unexpected JDK; misunderstood `--release` | Pin image-building JDK, verify `image/bin/java -version` |
| `bin/jshell` fails despite module presence | Incompatible runtime/launcher/OS config or dependency | Test executable and JShell API on actual image |
| JavaScript script engine returns `null` | Confused `java.scripting` with JavaScript engine implementation | Bundle external engine, check JSR 223 providers |
| TLS/locale/ZIP errors on minimal image | Missing service/native provider or omitted module | Verify features, root/bind needed providers |
| Dynamic compile cannot write class files | Read-only output folder or restricted process permissions | Use isolated output dir, least privilege, log diagnostics |
| Image fails on another OS | Native binaries built for wrong OS/arch | Build image for target or use target-specific pipeline |

### 11.1. Minimal Diagnostic Sequence

```text
1. Verify image/bin/java -version
2. image/bin/java --list-modules
3. Check jdk.compiler/jdk.jshell/provider modules
4. Run compiler probe / JShell probe / ServiceLoader probe
5. Compare root modules, module path, and --bind-services
6. Inspect modular JAR artifacts and module-info.java
7. Run tests under the same OS/container/runtime flags as production
```

When a provider is missing, do not "hotfix" production by adding `--add-modules ALL-MODULE-PATH` without review. Identify the **missing service and module** and fix the graph intentionally.

## 12. Testing and Deploying Custom Runtime Images

Tests should cover both **startup capability** and **dynamic features**:

| Test Case | Required Evidence |
|---|---|
| Build application modules | `javac --release 17` succeeds with explicit `module-info.java` |
| Valid modular JARs | `jar --describe-module --file mlib/demo.host.jar` reads descriptor |
| Image without bound services | `service=none` in demo, proving providers do not auto-enter graph |
| Image with service binding | `service=hello-provider` and `demo.provider` present |
| Compiler implementation | `getSystemJavaCompiler()!=null` inside image |
| JShell module | `jdk.jshell` in `--list-modules` and API works if app requires it |
| OS-specific module path | Correct separator, JDK `jmods` matching build |
| No unintended providers | Audit full `--list-modules` and artifact origins |
| Runtime without full JDK installed | App runs using only image and shipped resources |
| Runtime compile feature | Compiles short source, captures diagnostics, verifies class output |
| Dynamic plugin feature | Loads external provider via proper loader/layer without assuming build-time binding |
| Negative testing | Omitting required module/provider yields clear diagnostic errors |
| Multi-OS packaging | Executed in target CI runners/containers/VMs |
| JDK patching | Rebuild image from patched JDK rather than swapping only `java` binary |
| Deployment rollback | Can restore entire image and compatible app artifacts |

**Key checkpoint:** an image that links and passes `java -version` proves only that the JVM boots. It **does not** prove providers, compiler, JShell, or the dynamic plugin manager work. Feature-level probes are the acceptance criteria.

## 13. Checklist for Integrating jlink into CI/CD Pipelines

1. **Pinned toolchain:** use a JDK whose `jmods` match vendor/feature/update and target platform.
2. **Module inventory:** audit `requires`, `uses`, `provides`, reflection, and service providers; treat `jdeps` as advisory, not an exhaustive list of dynamic loading.
3. **Modular artifacts:** compile/package project modules with valid descriptors; verify versions and supply chain.
4. **Intentional roots:** select the host module and only tool modules needed at runtime: `jdk.compiler` for compiler, `jdk.jshell` for JShell, others per feature.
5. **Service binding:** choose between `--bind-services` and explicit provider roots; control the module path and linked provider inventory.
6. **Build image:** run `jlink --module-path ... --add-modules ... --output ...` with size flags where appropriate.
7. **Verify:** run `image/bin/java --list-modules`, compiler probe, `ServiceLoader` provider probe, and JShell probe if needed.
8. **Check isolation:** if executing untrusted scripts/user code, `jlink` is not a sandbox. Enforce OS/container privileges, CPU/RAM/network/filesystem limits, and capability gateways.
9. **Deploy:** ship the whole image, invoke the executable inside the image, and never rely on a pre-installed full JDK on the server.
10. **Maintain:** apply JDK updates by **rebuilding the image**, running regressions, and preserving provenance; audit how `--bind-services` affects module lists across builds.

### Official Java Documentation

- [jlink tool — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jlink.html)
- [Java Platform Module System — JLS/Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ModuleLayer.html)
- [ModuleDescriptor — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/module/ModuleDescriptor.html)
- [ServiceLoader — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html)
- [ToolProvider — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/ToolProvider.html)
- [JShell — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jshell/jdk/jshell/JShell.html)

**Conclusion:** building a custom runtime with `jlink` involves more than picking `java.base` and application modules. For dynamic compilation ensure **`jdk.compiler`**, for JShell ensure **`jdk.jshell`**, and for service-based architectures decide whether to bring **provider modules** into the image via explicit roots or **`--bind-services`**. Testing with `image/bin/java` itself, auditing `--list-modules`, and running real smoke tests keep images lean and functional while avoiding confusion between **build-time provider packaging** and **runtime plugin loading**.

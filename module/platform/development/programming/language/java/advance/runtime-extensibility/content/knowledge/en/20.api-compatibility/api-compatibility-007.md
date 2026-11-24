# Bytecode, Library, and JDK Compatibility When Compiling or Deploying Java Plugins

## 1. The problem to solve

A Java plugin may be developed with one JDK, compiled against one SPI (Service Provider Interface) version, packaged with its dependencies, and then deployed onto a host running a different JDK and libraries. **Installing a JAR or compiling successfully does not prove a plugin can run correctly.** Compatibility must be evaluated across several distinct layers.

Imagine three scenarios:

- A plugin is built as Java 21 bytecode while the host machine runs Java 17: the target JVM does not understand the newer class-file version.
- A plugin is built with `--release 17`, so its bytecode fully fits Java 17, yet the plugin calls a method present only in a newer library version; the host loads an older version: valid bytecode still causes a linkage error.
- Host and plugin compile against the same interface and same JDK, yet two class loaders define two copies of the identically named interface class: type identities do not match, so casting safely is impossible.

To design a runtime extensibility system, always separate at least four questions:

1. **Bytecode:** can the target JVM read the `.class` format?
2. **JDK/platform API:** are the JDK packages, modules, and methods referenced by bytecode present and accessible?
3. **Library/SPI ABI:** does the runtime provide the exact binary contract of the API and libraries the plugin compiled against?
4. **Loading and behavior:** do the class loader/`ModuleLayer` define the right identity and version, and does the plugin satisfy the host's semantics?

Only when all four layers align can the host treat the plugin as a valid candidate for activation. In production, you must also verify artifact provenance, trust boundaries, permissions, and resources; **compatibility does not imply security**.

## 2. Visualizing build time vs runtime

~~~text
BUILD TIME                                      RUNTIME
Plugin source                                  Host application
  |                                               |
  v                                               |-- Runtime JDK / runtime image
javac (toolchain, --release,                  |-- API/SPI actually loaded by host
      compile classpath, module path)              |-- Runtime dependencies
  |                                               |-- ClassLoader / ModuleLayer
  v                                               v
.class + resources --> plugin.jar ------------> Load, verify, link
                                                  |
                                                  v
                                          ServiceLoader / reflection
                                                  |
                                                  v
                                          Create instance, invoke SPI
~~~

The compiler writes symbolic references into bytecode pointing to classes, methods, fields, and descriptors visible at compile time. The JVM must then resolve them to concrete definitions along the class loader/module graph at runtime. Hence **compile classpath** and **runtime classpath/module path** must be managed as related configurations, not two arbitrary sets of JARs.

Record these attributes for every release:

| Component | Key information |
| --- | --- |
| Build JDK | Vendor, version, compiler options, and build tool |
| Target bytecode | Java release, class-file major/minor, preview status |
| Host API/SPI | Interface/binary names, API version/range, checksum |
| Dependencies | Exact versions and dependency graph, including transitives |
| Runtime JDK | Minimum version, actual running build, module availability |
| Loader/layer | Parent loader for SPI, dependency isolation, JPMS configuration |
| Plugin artifact | ID, version, SHA-256, manifest/module descriptor, publisher |
| Contract | Tests for results, errors, thread-safety, lifecycle, data formats |

Do not store a single `"javaVersion: 17"` field and assume it is enough information.

## 3. Class-file version: the most basic compatibility layer

A `.class` file has a **major_version** and **minor_version**. The JVM must support the class-file version before defining and using the class. Common milestones:

| Java release | Major version |
| --- | ---: |
| Java 8 | 52 |
| Java 11 | 55 |
| Java 17 | 61 |
| Java 21 | 65 |
| Java 24 | 68 |
| Java 25 | 69 |

A Java 17 JVM does not support class-file major 65 produced by JDK 21. Attempting to load it usually throws **`UnsupportedClassVersionError`**. Conversely, major 61 classes can load on a Java 17 JVM and newer Java runtimes supporting that format, **yet bytecode loadability does not guarantee correct dependencies or behavior**.

Inspect a class directly:

~~~bash
javap -verbose -classpath plugin.jar com.example.plugin.Provider
~~~

In the output, look for:

~~~text
major version: 61
~~~

**Do not inspect only the main class.** A plugin JAR may contain many classes, bundled dependencies, or multi-release entries, each potentially having a different class-file version. Building on JDK 21 also does not mean every class is automatically major 65 if the compiler is configured for a lower target.

Classes using **preview features** can carry the special minor version **65535**, tied to runtime version rules and `--enable-preview`. Do not rely solely on major version to assess preview support.

## 4. Using `javac --release` properly

The preferred option when targeting Java 17 for a plugin:

~~~bash
javac --release 17 -d out src/com/example/Plugin.java
~~~

**`--release 17`** instructs the compiler to:
- Apply Java 17 language rules.
- Emit class files targeting Java 17, typically major 61.
- Compile code against the **published platform API for release 17**, preventing accidental calls to JDK APIs introduced only in newer versions on the build machine.

Compare with:

~~~bash
# Illustrating the limitation of -source/-target when building on a newer JDK:
javac -source 17 -target 17 -d out src/com/example/Plugin.java
~~~

`-source` and `-target` mainly control language/class targets and **do not lock the platform API set to Java 17**. Source can compile on a newer JDK with `-target 17` even while calling a JDK method added in a later release, then fail when the host actually runs on Java 17.

**`--release` does not constrain third-party JAR APIs.** If a plugin compiles against `library-x` v3 while runtime supplies only `library-x` v2, `javac --release 17` still succeeds because the target JDK API and third-party library APIs are separate concerns.

Do not combine **`--release`** with **`-source`** and **`-target`** in the same invocation. A compiler also supports only certain release targets depending on the actual `javac` version. If a target is no longer supported, choose another toolchain instead of silently dropping `--release`.

For example, a pipeline may use a newer build JDK to produce major 61 classes for a Java 17 runtime. Even then, verify the result on a **real JDK 17** with the exact dependency set; never infer runtime compatibility purely from a successful compile log.

### Maven and Gradle

**Maven `pom.xml` snippet:**

~~~xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
</properties>
~~~

Use an appropriate `maven-compiler-plugin`, pinned toolchain/build versions, and locked dependency versions. This property **does not download the target JDK and does not guarantee library compatibility**.

**Gradle Kotlin DSL snippet:**

~~~kotlin
java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}
tasks.withType<JavaCompile>().configureEach {
    options.release.set(17)
}
~~~

The toolchain selects the compiler; `options.release` sets the target release. Align the target with the **minimum runtime** actually supported by the plugin platform rather than arbitrarily matching the JDK installed on a developer's machine.

## 5. Standard Java APIs vs third-party libraries

**The JDK platform API** is governed by `--release`. **Third-party APIs** are governed by the JARs actually present on the compile classpath or module path. Hence this can happen:

~~~text
Compile:
  JDK 24 + --release 17
  spi-api v2
  json-library v3
  plugin.jar => class major 61

Deploy:
  JDK 17
  spi-api v1
  json-library v2

Result:
  Class-file version: valid
  Binary contract: may be INVALID
~~~

The plugin records method calls the compiler saw in `spi-api` v2. When the target JVM instead has v1 lacking that method, **`NoSuchMethodError`** can appear at the moment the call is resolved. A missing field can likewise trigger **`NoSuchFieldError`**. If a method switched between static and instance, **`IncompatibleClassChangeError`** can occur.

Targeting a lower Java release **does not fix** SPI or dependency ABI mismatches. The host must manage API versions/contracts separately, track the dependency tree, and verify which classes the loader actually uses.

### Direct, transitive, and optional dependencies

- **Direct:** the plugin imports `library-x` v3's API while runtime supplies `library-x` v2; failures usually point directly to missing methods/fields.
- **Transitive:** `library-x` v3 requires `library-y` v4, yet the host forces `library-y` v2. A plugin importing only `x` can still fail inside `y`.
- **Optional:** truly optional only if the code path avoids that dependency or has a fallback; `"optional"` in Maven does not promise every runtime path works without it.
- **Shaded/relocated:** can isolate implementation libraries, yet **never relocate/copy the shared SPI** in a way that gives the plugin a different interface type than the host.
- **JNI/native:** `.dll`/`.so`/`.dylib` depend on OS/CPU/ABI and can break even when Java class files are completely valid.
- **Dynamically referenced:** reflection, `ServiceLoader`, `ResourceBundle`, and class-name strings can require classes/resources invisible to static imports.

For every loaded dependency, verify the **actual compile version**, **actual runtime version**, artifact hash, and class loader/module resolution.

## 6. Source, binary, and behavioral compatibility

Three key concepts:

1. **Source compatibility:** does old plugin source recompile when the host changes the API?
2. **Binary compatibility:** do prebuilt plugins keep linking against the new API without recompiling?
3. **Behavioral compatibility:** after successful linking, do semantics, data, invocation order, concurrency, and exception contracts remain valid?

Never equate the three concepts. Under the Java Language Specification, a change can preserve binaries yet cause source recompilation to fail with an ambiguous overload or pick a different overload; likewise, a change can preserve the binary contract while breaking business behavior.

| SPI/API change | What to watch out for |
| --- | --- |
| Add overload to class/interface | Usually preserves old binaries; source rebuild may choose a different overload |
| Add method to class | Usually binary-compatible for old clients; new clients fail on old libraries if calling that method |
| Add abstract method to interface | May be binary-compatible, yet a new host calling it on an old provider can hit **`AbstractMethodError`** |
| Add default method | Usually binary-compatible; cases exist with default method conflicts at invoke time |
| Remove/rename method called by old binaries | Can throw **`NoSuchMethodError`** |
| Change descriptor via parameter or return type | Effectively equivalent to removing the old method and adding a new one |
| Change static to instance or vice versa | Can throw **`IncompatibleClassChangeError`** |
| Lower public visibility / change module exports | Can throw **`IllegalAccessError`** |
| Remove/change field | Can throw **`NoSuchFieldError`** or related linkage errors |
| Keep method signature yet change behavior | JVM links fine, yet contract tests may fail |
| Change schema/serialization, nullability, threading contract | May run yet violate semantics or corrupt data |

**Compatibility direction is asymmetric:** if API v2 adds a new method, clients compiled earlier can continue running against v2. However, a client compiled against v2 that **calls the new method** cannot automatically run on host v1 lacking that method. Backward compatibility of a new API with old binaries does not imply new binaries are compatible with the old API.

For Java generics, bytecode method descriptors reflect **type erasure**. Changing a generic bound can change the descriptor. Whenever unsure whether a change breaks ABI, compare binary descriptors with **`javap -s`** rather than eyeballing Java source.

## 7. Complete Java 17 example: valid bytecode, incompatible runtime API

This example intentionally creates two versions of interface **`demo.api.Greeting`**:

- **api-v1:** has only `greet()`.
- **api-v2:** keeps `greet()`, adds `static banner()`.
- **PluginGreeting:** compiled against `api-v2`, calls `Greeting.banner()`.
- **Host:** compiled against `api-v1`, uses `ServiceLoader` to obtain the plugin and calls `greet()`.
- **Good runtime:** uses `api-v2` with the same plugin.
- **Failing runtime:** swaps `api-v2` for `api-v1` with the same plugin.

Every class is built with **`--release 17`**, so the bytecode target does not change between the two runtimes. The sole difference is the **loaded API library's binary contract**.

### File layout

~~~text
demo/
├── src/
│   ├── api-v1/demo/api/Greeting.java
│   ├── api-v2/demo/api/Greeting.java
│   ├── plugin/demo/impl/PluginGreeting.java
│   └── host/demo/host/Main.java
├── resources/
│   └── META-INF/services/demo.api.Greeting
└── out/
    ├── api-v1/
    ├── api-v2/
    ├── host/
    ├── plugin/
    └── plugin.jar
~~~

Put **only one** of `api-v1` and `api-v2` on the runtime classpath for each run. Do not place two copies with the same binary name on a single loader and deduce behavior from JAR load order.

### File `src/api-v1/demo/api/Greeting.java`

~~~java
package demo.api;

public interface Greeting {
    String greet(String name);
}
~~~

### File `src/api-v2/demo/api/Greeting.java`

~~~java
package demo.api;

public interface Greeting {
    String greet(String name);
    static String banner() { return "v2"; }
}
~~~

### File `src/plugin/demo/impl/PluginGreeting.java`

~~~java
package demo.impl;

import demo.api.Greeting;

public final class PluginGreeting implements Greeting {
    public PluginGreeting() {}

    @Override public String greet(String name) {
        return Greeting.banner() + ":" + name;
    }
}
~~~

The plugin class is `public`, implements the exact binary name of the SPI, and has a public no-argument constructor. However, `greet()` **depends on `banner()`, which exists only in API v2**.

### File `src/host/demo/host/Main.java`

~~~java
package demo.host;

import demo.api.Greeting;
import java.util.ServiceLoader;

public final class Main {
    public static void main(String[] args) {
        Greeting plugin = ServiceLoader.load(Greeting.class)
                .findFirst().orElseThrow();
        System.out.println("Provider: " + plugin.getClass().getName());
        try {
            System.out.println("Result: " + plugin.greet("Java"));
        } catch (NoSuchMethodError failure) {
            System.out.println("Linkage: " + failure.getClass().getSimpleName());
        }
    }
}
~~~

The host does not know the implementation name at compile time; `ServiceLoader` finds the provider from the service descriptor. Catching `NoSuchMethodError` only serves to **demonstrate a deterministic error** so the program prints testable output. Do not use this pattern to mask `LinkageError`s in production.

### File `resources/META-INF/services/demo.api.Greeting`

~~~text
demo.impl.PluginGreeting
~~~

This is the classpath service configuration file. The filename matches the SPI's binary name, and the line inside is the implementation's binary name.

### Compile and run on Linux/macOS (bash)

From the `demo` directory:

~~~bash
mkdir -p out/api-v1 out/api-v2 out/host out/plugin

javac --release 17 -d out/api-v1 \
  src/api-v1/demo/api/Greeting.java

javac --release 17 -d out/api-v2 \
  src/api-v2/demo/api/Greeting.java

javac --release 17 -cp out/api-v1 -d out/host \
  src/host/demo/host/Main.java

javac --release 17 -cp out/api-v2 -d out/plugin \
  src/plugin/demo/impl/PluginGreeting.java

mkdir -p out/plugin/META-INF/services
cp resources/META-INF/services/demo.api.Greeting \
  out/plugin/META-INF/services/demo.api.Greeting

jar --create --file out/plugin.jar -C out/plugin .

# Case A: runtime has API v2
java -cp "out/api-v2:out/host:out/plugin.jar" demo.host.Main

# Case B: runtime has only API v1
java -cp "out/api-v1:out/host:out/plugin.jar" demo.host.Main
~~~

### Compile and run on Windows PowerShell

~~~powershell
New-Item -ItemType Directory -Force out/api-v1,out/api-v2,out/host,out/plugin | Out-Null

javac --release 17 -d out/api-v1 src/api-v1/demo/api/Greeting.java
javac --release 17 -d out/api-v2 src/api-v2/demo/api/Greeting.java
javac --release 17 -cp out/api-v1 -d out/host src/host/demo/host/Main.java
javac --release 17 -cp out/api-v2 -d out/plugin src/plugin/demo/impl/PluginGreeting.java

New-Item -ItemType Directory -Force out/plugin/META-INF/services | Out-Null
Copy-Item resources/META-INF/services/demo.api.Greeting out/plugin/META-INF/services/demo.api.Greeting

jar --create --file out/plugin.jar -C out/plugin .

java -cp "out/api-v2;out/host;out/plugin.jar" demo.host.Main
java -cp "out/api-v1;out/host;out/plugin.jar" demo.host.Main
~~~

The classpath separator is a colon **:** on Linux/macOS and a semicolon **;** on Windows.

**Output Case A, compatible API v2:**

~~~text
Provider: demo.impl.PluginGreeting
Result: v2:Java
~~~

**Output Case B, API v1 missing method:**

~~~text
Provider: demo.impl.PluginGreeting
Linkage: NoSuchMethodError
~~~

`ServiceLoader` still finds and instantiates the provider in Case B because the constructor and `greet()` interface method resolve. Only when the host calls `greet()` does the JVM encounter the symbolic reference to `Greeting.banner()`, which API v1 lacks. Therefore, **successful discovery and constructor execution are not a complete compatibility test**.

Check the provider's class-file major version:

~~~bash
javap -verbose -classpath out/plugin.jar demo.impl.PluginGreeting
~~~

In the output appears the line:

~~~text
major version: 61
~~~

**Conclusion of the verification:** both runs used the exact same major 61 plugin class; only the runtime API changed. `NoSuchMethodError` is a **library/SPI ABI** error, not a Java 17 class-file target error.

## 8. Distinguishing common errors

| Error | Typical layer | What to check |
| --- | --- | --- |
| **`UnsupportedClassVersionError`** | JVM does not support bytecode/preview target | `java -version`, `javap` major/minor, all JAR dependencies |
| **`NoSuchMethodError`** | Library ABI mismatch | Compile-time method descriptor vs actually loaded class |
| **`NoSuchFieldError`** | Field ABI mismatch | Field version, descriptor, static/instance |
| **`AbstractMethodError`** | Interface/superclass evolution | Whether new method has a valid implementation on old provider |
| **`IncompatibleClassChangeError`** | Changed static/instance or member kind | API binary contract, class hierarchy/default method conflicts |
| **`IllegalAccessError`** | Accessibility / JPMS | `public` visibility, module readability/exports |
| **`NoClassDefFoundError`** | Dependency could not be defined, linkage/init failure | Missing class, class initializer failure, cause chain |
| **`ClassNotFoundException`** | Loader asked to find a class by name | Binary name, loader, classpath/module path |
| **`ClassCastException`** | Wrong type or duplicate SPI identity | Defining class loaders, module identity, API duplication |
| **`ServiceConfigurationError`** | Invalid SPI/provider declaration | `META-INF/services`, `provides`, constructor/provider method, cause |
| **`ResolutionException`** or **`LayerInstantiationException`** | JPMS module graph/layer | Module names, dependencies, split packages |
| Wrong results, wrong schema | Behavioral compatibility | Contract tests, sample data, serialization, concurrency |

Failures can **surface lazily**: a class may already be loaded or a provider instantiated before the JVM needs to resolve all methods/fields. Never run a single smoke test checking "`ServiceLoader.findFirst()` returns non-null" and declare a plugin compatible.

**`NoClassDefFoundError` does not always mean the class file is missing.** It can follow a failure during class initialization; inspect the cause and preceding logs. **`ClassCastException` is not always caused by loaders**, yet when two class names look identical and casting fails, check whether two loaders defined two separate SPI identities.

Catching **`ServiceConfigurationError`** at the discovery boundary can make sense in a plugin system to reject/quarantine broken providers. Never catch and swallow every `Throwable` assuming all JVM errors can safely continue.

## 9. `ClassLoader` and type identity

In Java, type identity depends on **binary name and defining class loader**. Two copies of `demo.api.Greeting` defined by two different loaders are not the same type simply because they share the same package and interface name.

Practical model for plugins on the classpath:

~~~text
Parent/application ClassLoader
  ├── host app
  └── spi-api (one shared copy)
       ^
       |
Child ClassLoader A
  ├── plugin-A.jar
  └── implementation dependencies A

Child ClassLoader B
  ├── plugin-B.jar
  └── implementation dependencies B
~~~

The host should supply the API/SPI from the parent, while plugin loaders are configured to see that **exact same `Class` object of the interface**. When isolating conflicting versions of implementation libraries, child-first strategies can help, yet **never apply child-first indiscriminately to the shared API**.

Things to confirm:
- Which `URLClassLoader` or custom loader is passed to `ServiceLoader.load(Service.class, loader)`?
- Do plugin code and host share the exact same SPI `Class` object?
- When a new module/plugin is installed, does the active loader see the new JAR?
- When replacing plugin v1 with v2, has the old loader already defined the class? If so, you need a new loader and proper transition lifecycle.
- Do references from thread context class loaders, registries, static fields, callbacks, or thread pools pin the old loader?

**`ServiceLoader.reload()` only clears `ServiceLoader`'s cache**; it does not replace already-loaded class bytecode, does not upgrade dependencies, and does not guarantee class unloading. Hot updates are the host's responsibility.

## 10. JPMS: valid class files can still fail the module graph

The Java Platform Module System adds extra requirements:
- **`requires`** and readability between modules.
- **`exports`** for public API packages; **`opens`** for reflection per policy.
- **`uses`** on consumers and **`provides ... with ...`** on providers.
- Actual module path, resolved module graph, custom **`ModuleLayer`**, and class loaders.
- Duplicate module names, split packages, automatic module names, and dependency versions.

Example of three separate module descriptors:

~~~java
// demo.api/module-info.java
module demo.api {
    exports demo.api;
}
~~~

~~~java
// demo.plugin/module-info.java
module demo.plugin {
    requires demo.api;
    provides demo.api.Greeting with demo.impl.PluginGreeting;
}
~~~

~~~java
// demo.host/module-info.java
module demo.host {
    requires demo.api;
    uses demo.api.Greeting;
}
~~~

These three snippets are **separate `module-info.java` files**, not a single standalone Java program. In JPMS, the API module exports the contract package; the provider module may keep its implementation package unexported/unopened while `ServiceLoader` still instantiates the provider validly.

A plugin compiled as valid Java 17 bytecode can still fail if the module does not resolve, the host lacks `uses`, a package is no longer exported, or the module graph is invalid. **The module descriptor is part of the compatibility contract**, not decorative metadata.

If using a new `ModuleLayer` to install plugins, the host must build the configuration/layer and invoke the matching discovery API, e.g., `ServiceLoader.load(layer, Service.class)`. `ServiceLoader` does not create layers or download artifacts from the Internet.

**Changing `requires` or `exports`** can cause prebuilt binaries to throw `IllegalAccessError` or fail module resolution, even if method names and class-file major versions stay unchanged. Run integration tests with the exact module path of the deployment environment.

## 11. Multi-release JARs and JDK versions

A Multi-release JAR (MR-JAR) allows shipping different class implementations depending on the runtime:

~~~text
plugin.jar
├── META-INF/MANIFEST.MF           # Multi-Release: true
├── com/example/Plugin.class       # Base implementation
└── META-INF/versions/17/com/example/Plugin.class
~~~

When the manifest is properly configured, runtimes supporting MR-JARs select the implementation in the highest version directory not exceeding the running Java release. This helps when one artifact must support older runtimes while taking advantage of newer APIs on newer runtimes.

Constraints:
- Base classes must run on the minimum runtime you advertise.
- Classes in `META-INF/versions/17` help only on sufficiently new runtimes; they do not make the entire artifact "automatically run on every Java."
- Public APIs across variants must follow MR-JAR consistency requirements; avoid letting the SPI contract vary unintentionally across JDKs.
- Dependencies and the module graph must still be valid on every runtime.
- When analyzing with **`jdeps`**, pass **`--multi-release`** appropriately for such JARs; remember to test across all supported runtimes.

Do not use MR-JARs if your entire system runs on Java 17 and a single implementation satisfies all requirements.

## 12. Verification tools

| Tool | Purpose | Limitation |
| --- | --- | --- |
| **`java -version`** | Actual runtime JVM | Does not show which library classes were selected |
| **`javac -version`** | Actual compiler | Does not prove target release |
| **`javac --release 17`** | Controls language, class-file, and platform API | Does not lock third-party APIs |
| **`javap -verbose`** | Inspect class major/minor, constant pool | Must inspect all relevant classes |
| **`javap -s`** | Inspect binary descriptors | Does not show which runtime version a loader picks |
| **`jar --list --file ...`** | List classes/resources in artifact | Does not prove provider loads cleanly |
| **`jar --describe-module --file ...`** | Inspect module descriptor/info | Does not prove module resolves in a layer |
| **`jdeps --multi-release 17 ...`** | Static dependency analysis | Does not fully cover reflection, `ServiceLoader`, JNI |
| **`mvn dependency:tree`** | Maven dependency graph | Does not verify runtime assembly is right |
| **`gradle dependencies / dependencyInsight`** | Gradle dependency resolution | Must verify actual runtime classpath |
| **`getClassLoader()/getModule()`** | Runtime identity/class visibility | Does not verify artifact provenance |
| **`CodeSource/ProtectionDomain`** | Hints where a class was loaded from | Can be null; does not replace checksums or signatures |

Runtime inspection snippet:

~~~java
// Illustrative snippet; plugin is an object already obtained by the host.
Class<?> actual = plugin.getClass();
System.out.println("Class: " + actual.getName());
System.out.println("Loader: " + actual.getClassLoader());
System.out.println("Module: " + actual.getModule());
var protectionDomain = actual.getProtectionDomain();
System.out.println("Source: " +
        (protectionDomain == null ? null : protectionDomain.getCodeSource()));
~~~

Do not rely on identical JAR filenames to conclude two files are **the same artifact**. A path may contain a newer file while the JVM already defined classes from an older build; track versions/hashes, loaders, and activation timing.

## 13. Compatibility test matrix

A compatibility matrix may include:

| Runtime | Runtime SPI | Runtime dependencies | Expected verification |
| --- | --- | --- | --- |
| JDK 17 | API v2 | Right library versions | Java 17 plugin discovered, instantiated, and working |
| JDK 21 | API v2 | Right library versions | Regression/integration tests; do not assume automatic compatibility |
| JDK 11 | API v2 | Even with full dependencies | Major 61 plugin class must be rejected before activation |
| JDK 17 | API v1 | Right library versions | Plugin calling v2 `banner()` must be rejected or test reports `NoSuchMethodError` |
| JDK 17 | API v2 | Transitive library too old | Contract/linkage test catches it |
| JDK 17 | API v2 | Two SPI copies in two loaders | Check type identity; cannot cast automatically |
| JDK 17 JPMS | API v2 | Module path missing a module | Check resolution/`uses`/`provides` before activation |
| JDK 17 plugin v1 → v2 | API v2 | New dependency graph | Test new loader, start, traffic shift, stop, rollback |

This is an **illustrative matrix**, not a claim that every scenario is verified by a single test. CI should genuinely run on the advertised **minimum JDK**, primary production JDK, and high-risk library combinations.

Key contract tests:
- Does `ServiceLoader` find the provider and instantiate it?
- Is the instance assignable to the host's exact SPI `Class`?
- Do SPI methods called by the host execute cleanly on runtime dependencies?
- Do return values, exceptions, data schemas, and concurrency match the contract?
- Do other plugins cause dependency conflicts or duplicate classes?
- Is the JPMS layer/module graph configured properly?
- Can a new version start, roll back, and stop the old version cleanly?

Testing only the constructor or health endpoint is insufficient: a broken symbolic method reference can hide on a rarely executed code path.

## 14. Appropriate build and release workflow

A typical workflow includes:

1. **Define minimum runtime:** e.g., Java 17, SPI API version/range, and module/classloader boundaries.
2. **Choose toolchain:** matching compiler version and **`--release`**, locked annotation processors and dependency versions.
3. **Compile/test:** compile plugin, run unit tests, static analysis, and public SPI contract checks.
4. **Verify artifact:** inspect class-file major/minor, manifest, `module-info`, `META-INF/services`, and dependency graph.
5. **Integration test on target runtime:** exact JDK version, API/SPI, dependencies, and loader/layer; verify behavior, not just discovery.
6. **Publish versioned artifact:** plugin version, proper checksums/signatures, build provenance, clear requirements.
7. **Host install-time preflight:** reject target JDK higher than host, missing dependencies, unsupported SPI versions, or invalid module configuration.
8. **Controlled activation:** start provider, check readiness/health, shift traffic if upgrading.
9. **Rollback/retire:** revert to a tested artifact, stop and release resources; use a new loader/layer when bytecode must change.
10. **Observe:** log plugin version, SPI version, JVM, loader, artifact hash, and linkage error causes.

If the host **accepts source and compiles dynamically**, add compiler option policies, diagnostics, caching keyed by source hash + API version + dependency fingerprint, resource limits, access controls, and processor/build-time code handling. Accepting Java source or JARs both carry security risks; compilers and class loaders are not sandboxes.

### Example metadata

~~~text
pluginId: demo-greeting
pluginVersion: 2.0.0
targetJava: 17
spiApiRange: [2.0,3.0)
requiredDependencies: resolved versions + checksums
testedRuntimeJdks: actual CI test results
artifactSha256: actual generated hash
~~~

This is an **application-designed metadata sample**, not syntax automatically understood by the JVM/`ServiceLoader`. Never record a JDK in `testedRuntimeJdks` unless the pipeline genuinely ran tests on that JDK.

## 15. Common mistakes

- **Build JDK = runtime JDK:** compiler version and target release differ; verify both.
- **Assuming major 61 runs everywhere on Java 17:** runtime dependencies, APIs, and behavior can still be incompatible.
- **Using `-target 17` without platform API constraints:** can call newer JDK APIs absent on Java 17.
- **Using `--release 17` and ignoring libraries:** this flag does not check ABIs of Jackson, Guava, JDBC drivers, or custom SPIs.
- **Testing only `ServiceLoader.findFirst()`:** many symbolic references remain uninvoked, delaying linkage errors.
- **Keeping two copies of the SPI in host/plugin:** differing class loader identities break casting and assignability.
- **Installing a plugin by overwriting an already-loaded JAR:** the JVM does not replace class definitions of an existing loader.
- **Ignoring transitive dependencies:** plugin compiles against library v3 while runtime dependency graph picks v1/v2.
- **Treating JPMS like the classpath:** `requires`, `exports`, `uses`/`provides`, and module resolution impose separate constraints.
- **Inferring compatibility from filenames or hand-written manifests:** hashes, classfiles, and runtime tests are far more reliable.
- **Testing only one JVM vendor/version:** the test matrix must reflect every runtime the product commits to supporting.
- **Equating binary compatibility with business correctness:** preserving method descriptors does not guarantee unchanged semantics or data.

## 16. Pre-activation plugin checklist

- [ ] Minimum JVM runtime and supported Java releases are published.
- [ ] Compiler toolchain is controlled and **`--release`** is configured properly.
- [ ] All loadable classes and critical dependencies have compatible class-file major/minor versions.
- [ ] Platform APIs/JDK modules used by the plugin exist on the target runtime.
- [ ] Plugin compiles against the right API/SPI version/range and the host fulfills the exact binary contract.
- [ ] Direct, transitive, and native dependencies have compatible versions/ABIs.
- [ ] Shared API/SPI has one type identity across host and providers; no duplicate definitions across loaders.
- [ ] Under JPMS, module descriptors, readability, exports/opens, uses/provides, and layers are verified.
- [ ] Integration/contract tests ran on the target runtime, covering key SPI methods.
- [ ] Artifact ID/version/hash metadata, build provenance, and pre-activation rejection policy are in place.
- [ ] Rollback/hot-update uses proper loaders/layers and lifecycle management; does not rely on `ServiceLoader.reload()` to swap bytecode.
- [ ] Trust boundaries, code provenance, and resource limits are designed independently of compatibility.

**Conclusion:** When compiling or deploying a plugin, simultaneously verify **bytecode target**, **JDK/platform APIs**, **library and SPI binary contracts**, **class identity/module graph**, and **runtime behavior**. The lab running the exact same Java 17 major 61 plugin while swapping runtime API v2 for v1 triggered `NoSuchMethodError`—proving that supporting the class-file version is only the first verification layer.

## Official Java 17 references

- JLS, Chapter 13 — Binary Compatibility: https://docs.oracle.com/javase/specs/jls/se17/html/jls-13.html
- JVMS, Chapter 4 — Class File Format: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html
- `javac` — `--release` and cross-compilation: https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html
- `jdeps` — dependency analysis: https://docs.oracle.com/en/java/javase/17/docs/specs/man/jdeps.html
- `ServiceLoader` API: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html

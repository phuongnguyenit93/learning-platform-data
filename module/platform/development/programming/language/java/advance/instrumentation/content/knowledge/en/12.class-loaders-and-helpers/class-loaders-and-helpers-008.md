# Dedicated Package Names and Avoiding Accidental Hijacking of Application Classes or Resources

When writing a Java agent, bytecode injected into an application class often needs to call a **helper** to record traces, measure time, or count events. The helper may reside in the agent JAR, in a JAR appended to the bootstrap class loader search, or in another class loader. If the agent uses overly generic package names, puts its own libraries on the application's class search path, or places resources at colliding paths, the JVM may **load the right name but the wrong version or wrong source**, causing linkage errors, misconfiguration, and behavior that is very difficult to diagnose.

**Design principle:** place the agent's classes/helpers in a **dedicated, stable, collision-resistant namespace**, isolate the agent's dependencies, keep any JAR added to bootstrap minimal, and verify both **class names and resource names**. A dedicated package reduces collisions, but it **does not create a security boundary by itself** and does not automatically solve all class loader/module issues.

This article belongs to the **Class loaders and helpers** section of Java Instrumentation. You will understand precisely what “accidental hijacking” of a class/resource means, why delegation causes the error, how to organize JARs/relocate dependencies, how to choose where to place helpers, and how to verify this with a Java 17+ example.

## 1. Distinguishing three concepts: class name, class identity, and resource

### 1.1. A binary class name is not the entire identity

In Java, a class typically has a binary name such as:

```text
com.example.payment.PaymentService
io.mycompany.telemetry.agent.internal.ProbeBridge
org.example.codec.JsonCodec
```

In a class file, those names typically appear as internal names with `/` separators, such as `io/mycompany/telemetry/agent/internal/ProbeBridge`. For ordinary classes, **identity in the JVM also depends on the defining class loader**, not just the name string.

```text
(binary name = "com.example.Plugin")
      +
(defining class loader = Loader-A)
      = Class A

(binary name = "com.example.Plugin")
      +
(defining class loader = Loader-B)
      = Class B (different from Class A)
```

Two different `Class<?>` objects can exist even with the exact same character name. Casting or passing instances across a loader boundary can cause a `ClassCastException`. Conversely, if a loader **delegates to its parent** and receives a class with the same name already defined by the parent, it may not load the class of the same name in its own JAR. This is one way **loading the wrong class** happens.

### 1.2. Resources are looked up only by path, not Java type identity

Resources have names like:

```text
application.properties
logback.xml
META-INF/services/com.example.spi.ParserProvider
com/example/payment/config.json
io/mycompany/telemetry/agent/internal/agent.properties
```

`ClassLoader.getResource(name)` or `getResourceAsStream(name)` looks up resources by a **`/`-separated path**, according to the search order/visibility of the loader/module. A resource has no Java type or check ensuring that “this file belongs to the right helper JAR”.

Two JARs can both contain `application.properties`; the API returns **a resource matching the search path** without knowing which file contains the configuration you “intended”. With the common parent-first mechanism, a resource from the parent can win over the child's resource. In a named module environment, encapsulation rules and search order may differ; you should not make absolute assumptions based on the classpath.

### 1.3. “Same package” is not identical to “already hijacked”

| Phenomenon | Example | What can happen |
|---|---|---|
| Duplicate **binary name** | Both app and agent have `com.example.util.Helper` | Loader uses the app version or agent version unexpectedly |
| Same **package**, different class names | App has `com.example.util.A`, agent has `com.example.util.B` | Split package, sealing, module, and package-private access can cause issues; does not always fail immediately |
| Duplicate **resource path** | Both have `config.properties` | Helper reads the app's config by mistake, or vice versa |
| Duplicate **service descriptor** | Both have `META-INF/services/com.example.Plugin` | Service provider discovery may see unintended providers |
| Duplicate **dependency binary name** | App and agent contain two versions of `org.some.library.Parser` | `NoSuchMethodError`/`LinkageError`, different ABI |
| Two classes with the same name defined by two different loaders | Two plugins have `com.example.Model` | Two separate class identities; casting/linkage between the two sides may fail |
| Helper not visible to target loader | App bytecode calls `io.agent.internal.ProbeBridge` but loader cannot see it | `NoClassDefFoundError`/`ClassNotFoundException` or access error |
| Resources with the same simple name but in **different dedicated namespaces** | `app/config.properties` and `agent/internal/config.properties` | Generally avoids path collisions, easy to verify the source |

**There is no rule that “the longer the package name, the higher priority the JVM gives it”.** A unique name helps avoid collisions; classloader delegation and module visibility determine which class is actually resolved.

## 2. Parent-first delegation and why the wrong class gets picked

`ClassLoader.loadClass` by default checks already-loaded classes, then usually asks the **parent** first, and only then calls `findClass` on the current loader. Custom class loaders can alter this policy, but parent-first is an important model to understand.

```text
          Child Loader
          /          \
      loadClass     getResource
         |               |
         v               v
   ask Parent first   ask Parent first
         |               |
     if not found     if not found
         v               v
   search in child    search in child
```

Suppose:

```text
application.jar:
  com/acme/common/Codec.class         -> APP version
  com/acme/common/config.properties   -> source=APP

agent-helper.jar:
  com/acme/common/Codec.class         -> AGENT version
  com/acme/common/config.properties   -> source=AGENT
```

If the loader trying to look up `com.acme.common.Codec` has a parent that can see the APP version, a normal lookup can return **APP** even though the child carries the AGENT class file. Likewise, `getResource("com/acme/common/config.properties")` can return the APP resource.

**Consequence for the agent:** The helper is compiled against the agent's dependency version, but at runtime it resolves the application's dependency. If an expected method does not exist, you may hit `NoSuchMethodError`. If types have different semantics, the bug can be even more dangerous because it runs without crashing but produces wrong behavior.

### 2.1. Child-first is not a default silver bullet

Some plugin frameworks, application servers, or module systems use a child-first strategy or other policies. In that case, the reverse can happen: application code accidentally receives the agent's class/resource if the agent is placed in its search scope.

Therefore, do not build a solution relying on “the agent will definitely go first” or “the app will definitely go first”. Design so that **there are no colliding names** from the start, then verify the actual classloader at deployment time.

### 2.2. Java package-private and runtime packages

Having the same package prefix does not guarantee two classes are considered to be in the same **runtime package** if they are defined by different loaders (and in modern module contexts there are also runtime module rules). Thus, a helper trying to place itself in an application package to access package-private members may encounter `IllegalAccessError`. Arbitrarily renaming packages can also break access permissions, package sealing, or module boundaries.

**Do not use the trick of “putting the helper in the same package as the app” to bypass access controls.** Choose a valid API/bridge, adjust module reads/opens/exports when permitted, and verify class-loader identity.

## 3. Special risks when appending a JAR to the bootstrap class loader search

Java Instrumentation provides:

```java
void appendToBootstrapClassLoaderSearch(java.util.jar.JarFile jarfile);
void appendToSystemClassLoaderSearch(java.util.jar.JarFile jarfile);
```

These are **APIs called on the agent's `Instrumentation` object**, not a command the JVM automatically runs for every agent JAR. The usage snippet below is illustrative only, not a complete agent:

```java
// inst is the Instrumentation received via premain/agentmain:
try (java.util.jar.JarFile jar =
        new java.util.jar.JarFile("agent-bootstrap-helper.jar")) {
    inst.appendToBootstrapClassLoaderSearch(jar);
}
```

**Lifecycle note:** In a real runtime, do not assume closing the `JarFile` immediately after appending is suitable for all implementations/resource-retention behaviors. Manage `JarFile` and JAR lifecycles according to the documentation/testing of the JVM in use; the code here only introduces the API signature, **and copying and pasting the `try-with-resources` block as a production implementation pattern is not recommended**.

### 3.1. Why does appending to bootstrap easily cause “accidental hijacking”?

Bootstrap is the high-level parent in many delegation chains. If the appended JAR contains a class/resource with the same name as something a lower loader intends to look up, a lookup that misses in an intermediate parent may find the class/resource from the appended JAR. The `Instrumentation.appendToBootstrapClassLoaderSearch` Javadoc **explicitly** warns against including any classes/resources in the JAR other than those intentionally belonging to bootstrap instrumentation.

The documentation gives a scenario where class `C` references a non-public accessor such as `C$1`, but the bootstrap-appended JAR also contains the name `C$1`. Parent delegation may cause `C$1` to be defined by bootstrap instead of `C`'s loader, causing an **`IllegalAccessError`**. One way to avoid this is to use a **unique package name** for instrumentation classes.

```text
App Loader L defines C
  C -> needs C$1 (non-public accessor)
        |
        v
     delegates to bootstrap
        |
    bootstrap-appended JAR also contains C$1
        |
        v
     bootstrap mistakenly defines C$1
        |
        v
     runtime-package/access rules do not match
     -> may throw IllegalAccessError
```

If a helper is placed into the bootstrap search, strive to create a **minimal separate JAR**, containing only the classes and resources truly needed on bootstrap. Do not put the entire agent, common dependencies, root resources, service descriptors, and test applications into it just for build convenience.

### 3.2. Appending to system is different from adding a JAR to every loader

`appendToSystemClassLoaderSearch` adds a JAR to the **system class loader's search path** when this loader supports the required mechanism. It does **not** automatically make every custom loader see the helper, does not guarantee named modules have access, and does not modify the `java.class.path` system property.

A class for which the JVM has already **recorded a failed symbolic reference resolution** is also not necessarily “fixed” by appending a JAR afterward: the Javadoc warns that subsequent resolutions of a failed reference must continue to fail according to JVMS rules. Therefore, you must arrange **helper visibility before instrumented classes attempt to call the helper**, rather than believing you can cure every `NoClassDefFoundError` by appending late.

### 3.3. Bootstrap is not the place to put all dependencies

A good bootstrap helper typically:

- Has a small, stable API using primitives or basic JDK types.
- Does not depend on application classes, ORMs, Jackson/JSON mappers, or the app's logger/HTTP client.
- Does not trigger class loading or network I/O on first invocation.
- Does not include custom `java.*`, `jdk.internal.*`, or `sun.*` packages in the JAR.
- Does not carry generic resources like `logback.xml`, `application.properties`, or unrelated `META-INF/services`.
- Has diagnostic and error-handling mechanisms while avoiding pulling every dependency into bootstrap.

**This reduces risk; it is not an absolute guarantee.** Named modules, class access, unusual loader delegation, and dependency identity still need to be tested.

## 4. Dedicated packages for helpers and resource namespaces

### 4.1. A practical namespace convention

Use a clear reverse-domain and product/agent name:

```text
Recommended:
  io.acme.observability.agent.bootstrap.ProbeBridge
  io.acme.observability.agent.runtime.EventRecorder
  io.acme.observability.agent.internal.BytecodeSupport
  io.acme.observability.agent.shaded.somevendor.Parser

Avoid:
  com.common.Helper
  com.example.util.Logger
  org.objectweb.asm.Helper                 (if defining your own class in a library namespace)
  com.myapp.service.AgentHelper            (collides with application package)
  java.lang.AgentBridge                     (JDK package)
```

These are **naming examples**, not names to use verbatim. A dedicated prefix must be owned by your organization/product or managed internally—do not guess an app's package name and copy it.

You should clearly separate:

1. **Bootstrap bridge**: a small API that bytecode can call from multiple loaders; placed in a minimal bootstrap JAR if truly needed.
2. **Agent runtime**: transformers, configuration, exporters, queues, and management components; kept in an appropriate classloader, not automatically dumped into bootstrap.
3. **Shaded dependencies**: libraries packaged with the agent and relocated when there is a risk of class name collision with the application.
4. **Agent resources**: configuration, service descriptors, and operational resources of the agent in unique paths.

### 4.2. Resource paths must also be dedicated

Dedicated class packages are not enough if the JAR contains generically named resources.

| Dangerous resource if left at root / common path | Organization approach to reduce collisions |
|---|---|
| `application.properties` | `io/acme/observability/agent/internal/agent.properties` |
| `logback.xml` | Do not package by default if the agent does not actively use a dedicated logger config |
| `config.json` | `io/acme/observability/agent/internal/config.json` |
| `schema.json` | `io/acme/observability/agent/internal/schema/v1.json` |
| `META-INF/services/com.some.SPI` | Control service descriptors during build/shade, avoiding unintended providers |
| `META-INF/native-image/...` | Ensure metadata belongs to the right namespace/artifact and is updated after relocation |

Example of accessing a private resource via an explicit path:

```java
// Illustrative code in a helper class with an appropriate loader:
String name = "io/acme/observability/agent/internal/agent.properties";
ClassLoader loader = ProbeBridge.class.getClassLoader();
java.io.InputStream input = (loader == null)
        ? ClassLoader.getSystemResourceAsStream(name)
        : loader.getResourceAsStream(name);
```

This snippet **is not a general strategy for bootstrap**: when `getClassLoader() == null`, `getSystemResourceAsStream` may search a different source than the bootstrap helper and suffer collisions. Do not bring this illustrative snippet into real code without defining an **authoritative resource source**. For a bootstrap helper, it is best **not to need to read separate config on the hot path**; configuration should be passed via a controlled API contract or loaded from an explicit source at the agent runtime layer.

### 4.3. Leading `/` in resource APIs often causes mistakes

```java
// Resource path from root via ClassLoader:
loader.getResource("io/acme/agent/internal/agent.properties");

// Class.getResource: starting with "/" is an absolute path:
ProbeBridge.class.getResource(
        "/io/acme/agent/internal/agent.properties");

// WITHOUT "/", Class.getResource is a path
// relative to the package containing ProbeBridge.
ProbeBridge.class.getResource("agent.properties");
```

These are illustrative snippets; `loader` and `ProbeBridge` must be real variables/classes. Do not call `ClassLoader.getResource("/...")` and expect it to always strip the `/` like `Class.getResource`: the two APIs have different rules.

**Just getting a URL is not enough:** the same path can exist in multiple JARs. When testing, enumerate `loader.getResources(name)` and inspect the list of URLs; in production, however, do not log sensitive URLs indiscriminately.

## 5. Dependency relocation/shading and what not to relocate blindly

If the agent uses a library that is also common in applications, such as a bytecode parser or JSON library, changing only **the helper's** package may still not be enough. Both the agent and the app may need `org.some.library.Parser` at two different versions.

### 5.1. Three basic strategies

| Strategy | Advantages | Limitations |
|---|---|---|
| **Do not bundle** dependency, rely on application library | Small JAR | ABI/version conflict risk, unreliable across many target applications |
| Bundle dependency but **keep original package** | Convenient packaging | Collisions when the class loader prefers another version or package sealing |
| Bundle and **relocate/shade** dependency into agent namespace | Reduces binary-name collisions | Must handle reflection, service descriptors, resources, module/manifest, and packaging tests |

Conceptual example of relocation:

```text
Before:
  org/example/parser/Parser.class
  org/example/parser/Tokenizer.class

After:
  io/acme/observability/agent/shaded/parser/Parser.class
  io/acme/observability/agent/shaded/parser/Tokenizer.class
```

This is a **strategy description**, not an executable build command. With Maven Shade, Gradle Shadow, or equivalent tools, you must configure relocation at the **artifact build stage**—do not rename classes directly in source and assume all resource/reflection references are updated.

### 5.2. Things relocation often misses

- **`META-INF/services/...`**: both the descriptor file name and the provider class names inside may need corresponding transformation. Otherwise, `ServiceLoader` will not find the provider or will find the wrong one.
- **Reflection by string**: `Class.forName("org.example.parser.Parser")` may not be rewritten automatically if the name is in a string not understood by the relocation tool.
- **Config/resource paths**: the class moved packages, but code still looks for the resource at the old path, or the agent still contains generically named resources.
- **JPMS descriptors**: `module-info.class`, `Automatic-Module-Name`, exports/opens/uses/provides must be compatible with the post-build artifact.
- **Serialized class names/JNI/native code**: string-based references and native symbols may depend on old names.
- **Manifest `Premain-Class`/`Agent-Class`**: must point to the right agent entry point after building; if relocation renames the entry class without updating the manifest, the JVM cannot run the agent.
- **Signed JARs**: modifying JAR contents invalidates old signatures/digests; you must use a proper signing/packaging process and not publish artifacts with invalid signature metadata.
- **Licenses and notices**: bundling third-party libraries still carries license/notice obligations depending on the license.

**Shading is not a security boundary.** It reduces class name conflicts, does not prevent arbitrary code from accessing data, and does not automatically grant module read/export permissions.

## 6. Runnable Java 17+ example: a class and a resource “taken first” by the parent

This is a **pure Java class-loader experiment**, no `-javaagent` required. The goal is to observe parent-first lookup directly to see why an agent must use dedicated packages/resources. To study this mechanism, we have two JARs:

- `app.jar`: defines `sample.shared.Marker` and a shared resource.
- `helper.jar`: intentionally has a **colliding class/resource** `sample.shared.Marker`; it also has a helper in a dedicated namespace `io.workshop.telemetry.agent.internal.Helper` and a dedicated private resource.

The `CollisionDemo` program uses two explicit parent/child `URLClassLoader` instances. The experiment demonstrates the lookup behavior; **it does not claim that `URLClassLoader` simulates every custom loader, module loader, or bootstrap append in production**.

### 6.1. Create the file structure

```text
loader-lab/
  src-app/
    sample/shared/Marker.java
  resources-app/
    sample/shared/config.properties
  src-helper/
    sample/shared/Marker.java
    io/workshop/telemetry/agent/internal/Helper.java
  resources-helper/
    sample/shared/config.properties
    io/workshop/telemetry/agent/internal/agent.properties
  src-demo/
    CollisionDemo.java
```

The two `sample/shared/Marker.java` files have the same class name but are **two different source versions**. Compile them separately to create two JARs; do not place them side by side on the same classpath as `CollisionDemo`.

### 6.2. File `src-app/sample/shared/Marker.java`

```java
package sample.shared;

public final class Marker {
    public static String origin() {
        return "APP";
    }
}
```

### 6.3. File `src-helper/sample/shared/Marker.java`

```java
package sample.shared;

public final class Marker {
    public static String origin() {
        return "AGENT";
    }
}
```

This is an **intentional collision created for the experiment**. In a real product, do not package the helper's `sample.shared.Marker` if the application already has a class with the same name.

### 6.4. File `src-helper/io/workshop/telemetry/agent/internal/Helper.java`

```java
package io.workshop.telemetry.agent.internal;

public final class Helper {
    public static String origin() {
        return "AGENT_HELPER";
    }
}
```

This class has a dedicated agent namespace and is **not** in the application's `sample.shared` package. In the experimental loader setup, the child loader can define it without being hijacked by the parent.

### 6.5. The three resource files

`resources-app/sample/shared/config.properties`:

```properties
origin=APP_RESOURCE
```

`resources-helper/sample/shared/config.properties`:

```properties
origin=AGENT_RESOURCE
```

`resources-helper/io/workshop/telemetry/agent/internal/agent.properties`:

```properties
origin=AGENT_PRIVATE_RESOURCE
```

The first two files have the **same resource path** in both JARs. The third file uses a path dedicated to the helper. When writing the files, keep the exact `=` character and paths, and avoid accidentally placing resources directly in the JAR's root directory.

### 6.6. File `src-demo/CollisionDemo.java`

```java
import java.io.InputStream;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;
import java.util.Collections;
import java.util.Properties;

public final class CollisionDemo {
    private static String property(ClassLoader loader, String name)
            throws Exception {
        try (InputStream in = loader.getResourceAsStream(name)) {
            if (in == null) {
                return "MISSING";
            }
            Properties p = new Properties();
            p.load(in);
            return p.getProperty("origin", "MISSING");
        }
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            System.err.println("Usage: CollisionDemo <app.jar> <helper.jar>");
            System.exit(2);
        }

        URL appUrl = Path.of(args[0]).toUri().toURL();
        URL helperUrl = Path.of(args[1]).toUri().toURL();

        try (URLClassLoader appLoader = new URLClassLoader(
                     new URL[] {appUrl},
                     ClassLoader.getPlatformClassLoader());
             URLClassLoader helperLoader = new URLClassLoader(
                     new URL[] {helperUrl},
                     appLoader)) {

            // Parent-first: helperLoader requests the colliding class,
            // but appLoader can already find and define the APP class.
            Class<?> shared = Class.forName(
                    "sample.shared.Marker", true, helperLoader);
            String sharedOrigin =
                    (String) shared.getMethod("origin").invoke(null);
            System.out.println("SHARED_CLASS=" + sharedOrigin);
            System.out.println(
                    "SHARED_CLASS_FROM_PARENT="
                    + (shared.getClassLoader() == appLoader));

            String commonResource = property(
                    helperLoader, "sample/shared/config.properties");
            System.out.println(
                    "SHARED_RESOURCE=" + commonResource);

            int matches = Collections.list(helperLoader.getResources(
                    "sample/shared/config.properties")).size();
            System.out.println(
                    "SHARED_RESOURCE_MATCHES=" + matches);

            // Dedicated namespace: only helper.jar has this class.
            Class<?> helper = Class.forName(
                    "io.workshop.telemetry.agent.internal.Helper",
                    true, helperLoader);
            String helperOrigin =
                    (String) helper.getMethod("origin").invoke(null);
            System.out.println("PRIVATE_CLASS=" + helperOrigin);
            System.out.println(
                    "PRIVATE_CLASS_FROM_CHILD="
                    + (helper.getClassLoader() == helperLoader));

            String privateResource = property(helperLoader,
                    "io/workshop/telemetry/agent/internal/agent.properties");
            System.out.println(
                    "PRIVATE_RESOURCE=" + privateResource);
        }
    }
}
```

**Why use the platform class loader as the parent of `appLoader`?** So we do not accidentally put `app.jar` or `helper.jar` on the system classpath. `appLoader` can see classes in `app.jar`, while `helperLoader` has `appLoader` as its parent. This is a parent-first model **deliberately constructed for testing**, not a prediction of every real application's class loader.

**Why use reflection?** `CollisionDemo` does not compile-time import `sample.shared.Marker` or the helper, so it can be compiled independently and query the configured loader itself to see which class source is resolved at runtime. Checking via `getClassLoader() == appLoader / helperLoader` avoids guessing the class source from its name.

### 6.7. Compile, package JARs, and run on JDK 17+

In a Bash/macOS/Linux shell at `loader-lab`:

```shell
mkdir -p build/app build/helper build/demo

javac -d build/app src-app/sample/shared/Marker.java
javac -d build/helper \
  src-helper/sample/shared/Marker.java \
  src-helper/io/workshop/telemetry/agent/internal/Helper.java
javac -d build/demo src-demo/CollisionDemo.java

cp -R resources-app/. build/app/
cp -R resources-helper/. build/helper/

jar --create --file app.jar -C build/app .
jar --create --file helper.jar -C build/helper .

java -cp build/demo CollisionDemo app.jar helper.jar
```

If running PowerShell on Windows, create directories and copy resources using the equivalent commands:

```powershell
New-Item -ItemType Directory -Force build/app, build/helper, build/demo | Out-Null
javac -d build/app src-app/sample/shared/Marker.java
javac -d build/helper src-helper/sample/shared/Marker.java src-helper/io/workshop/telemetry/agent/internal/Helper.java
javac -d build/demo src-demo/CollisionDemo.java
Copy-Item -Path "resources-app/*" -Destination "build/app" -Recurse -Force
Copy-Item -Path "resources-helper/*" -Destination "build/helper" -Recurse -Force
jar --create --file app.jar -C build/app .
jar --create --file helper.jar -C build/helper .
java -cp build/demo CollisionDemo app.jar helper.jar
```

Running on Windows requires PowerShell with JDK tools on `PATH`. The class/resource strings here do not depend on Windows `\` separators because names inside a JAR always use `/`.

**Expected stdout with these exact two JARs and the demo's class loaders:**

```text
SHARED_CLASS=APP
SHARED_CLASS_FROM_PARENT=true
SHARED_RESOURCE=APP_RESOURCE
SHARED_RESOURCE_MATCHES=2
PRIVATE_CLASS=AGENT_HELPER
PRIVATE_CLASS_FROM_CHILD=true
PRIVATE_RESOURCE=AGENT_PRIVATE_RESOURCE
```

Explanation:

1. `SHARED_CLASS=APP`: `helperLoader` asks its parent first; parent `appLoader` finds the `sample.shared.Marker` version in `app.jar`.
2. `SHARED_CLASS_FROM_PARENT=true`: the loader that actually **defines** the class is `appLoader`, not `helperLoader`.
3. `SHARED_RESOURCE=APP_RESOURCE`: the resource path collides, and `getResourceAsStream` picks the parent's version according to `URLClassLoader`'s default lookup in this test.
4. `SHARED_RESOURCE_MATCHES=2`: `getResources` lists both the app and helper versions in this two-JAR model; getting the **first resource** does not mean that resource belongs to the helper.
5. `PRIVATE_CLASS=AGENT_HELPER` and `PRIVATE_CLASS_FROM_CHILD=true`: the class with a dedicated package is defined from `helper.jar` by the child.
6. `PRIVATE_RESOURCE=AGENT_PRIVATE_RESOURCE`: the helper's private resource has a dedicated path, so it is found accurately in the test environment.

**Limitations of the output:** The result above is a controlled experiment with two `URLClassLoader`s, parent-first, no third JAR, and resources not subject to module encapsulation. In a framework with a child-first loader or named modules, resolution may differ. The goal is to prove that **duplicate naming makes the result loader-dependent**, not to claim the JVM always prefers the app.

### 6.8. Verify JAR contents and resource order

```shell
jar tf app.jar
jar tf helper.jar
```

Both JARs must contain `sample/shared/Marker.class` and `sample/shared/config.properties`. `helper.jar` additionally has `io/workshop/telemetry/agent/internal/Helper.class` and `io/workshop/telemetry/agent/internal/agent.properties`.

For advanced debugging on HotSpot, you can use `-Xlog:class+load=info` when running Java 17+, then filter the class lines belonging to the sample namespaces to see their source:

```shell
java -Xlog:class+load=info -cp build/demo \
  CollisionDemo app.jar helper.jar
```

This command prints **more JVM logs** than the expected stdout, so do not match the entire output line by line; focus on the `SHARED_*`, `PRIVATE_*` lines and class load sources. `-Xlog:class+load` is a diagnostic feature of HotSpot/JVMs supporting unified logging; not every Java implementation is required to have the exact same messages.

## 7. Direct connection to bytecode instrumentation

Suppose a transformer injects the instruction:

```text
invokestatic io/acme/observability/agent/bootstrap/ProbeBridge.onEnter (I)V
```

This is **illustrative bytecode notation**, not standalone compilable Java source. The JVM needs to resolve `ProbeBridge` properly from the linking context of the instrumented class. There are three unavoidable questions:

1. **Which class will resolve the helper?** Which loader defined it? Can its class loader see the bridge package?
2. **If the helper has dependencies, where will the corresponding loader resolve them?** Could it accidentally pick up the application's version?
3. **If the helper reads resources/config, where is that resource located?** Could it pick up a file of the same name from a parent, classpath, or another module?

### 7.1. Minimal bridge architecture pattern

```text
Target class: com.app.OrderService
  |
  | bytecode call (method ID, timestamp, outcome)
  v
io.acme.observability.agent.bootstrap.ProbeBridge
  - few public static methods
  - no dependency on application classes
  - minimal primitive/JDK types only
  |
  | pass bounded data across a stable interface
  v
io.acme.observability.agent.runtime.Recorder
  - queue/batching/exporter
  - agent-specific class loader/context
  - isolated dependencies
```

A bootstrap bridge does not automatically have permission to call `Recorder` in every loader: you must design explicit visibility/registration and verify it before instrumenting targets. With named modules, in addition to class loader visibility there are **module reads/exports/opens**; `Instrumentation.redefineModule` can add relationships when supported, though it is not a substitute for class binary-name correctness.

### 7.2. Which classes should be excluded from the transformer?

- The agent's own bootstrap/runtime helper packages, to avoid the helper instrumenting itself and looping probes.
- Exporter/logger dependencies that the helper calls, if instrumenting them would cause loops or overhead.
- JDK classes and class-loader internals outside the observation scope, where interfering could cause bootstrap/linkage errors.
- Classes belonging to packages known to risk conflicting with the agent or having special policies.

A class name filter is not the entire protection mechanism. When multiple loaders define the same binary name, the transformer also needs **loader identity/module/code source and target policies**, rather than relying solely on `className` for every decision.

## 8. Resources and ServiceLoader: collisions are not limited to .properties files

### 8.1. `META-INF/services`

Java SPI/provider discovery may look up `META-INF/services/<service binary name>`. When an agent bundles service providers and the app also has similar providers, the order and class loader context can affect which provider is discovered. Shading a provider class without updating the descriptor can lead to `ServiceConfigurationError`.

Example:

```text
META-INF/services/com.example.spi.Parser
```

The file contains provider binary class names, not paths to a JAR. If a provider is relocated, both the **class names inside the file** and potentially the **service descriptor name** must match the package/ABI translation. Do not blindly merge two descriptors just to “keep all providers”: doing so can expose unapproved providers to the agent or cause the app to use the wrong SPI.

Some calls to `ServiceLoader.load(service)` use the **thread context class loader**; when you need to select a specific source, use the overload with an explicit loader if appropriate:

```java
// Illustrative snippet, ServiceType and desiredLoader are undefined:
java.util.ServiceLoader<ServiceType> providers =
        java.util.ServiceLoader.load(ServiceType.class, desiredLoader);
```

Do not conclude that TCCL is always the agent's loader: on application/framework threads it may be the app's loader. Also do not mutate the global TCCL inside a probe, as it can affect other libraries.

### 8.2. Root logging resources and configuration discovery

Names like `log4j2.xml`, `logback.xml`, `application.yml`, or `META-INF/services/...` are often auto-discovered by libraries. Accidentally packaging a config file in the agent JAR can affect the application's behavior if the JAR appears on a search path the app uses, even when **no class names collide**.

How to reduce risk: avoid bundling unnecessary root-level configs; only package private resources inside the agent namespace; design explicit configuration loading paths so the agent's logger does not pick up application config files unintentionally.

### 8.3. Named modules and resource encapsulation

In JPMS, resources in a named module can be encapsulated; `ClassLoader.getResource`/`getResources` will not necessarily see package-private resources unless the package is opened appropriately. `Module.getResourceAsStream` and `Class.getResource` have slightly different rules regarding access scope. Therefore, if a resource “is in the JAR but reports MISSING”, you must check **module, package opens, loader, and path**, not just `jar tf`.

## 9. Verification techniques on a real agent

### 9.1. Inspect which binary class was actually resolved

```java
// Diagnostic snippet; clazz is a real Class<?>:
ClassLoader loader = clazz.getClassLoader();
String binaryName = clazz.getName();

java.security.ProtectionDomain pd = clazz.getProtectionDomain();
java.security.CodeSource cs = pd == null ? null : pd.getCodeSource();
java.net.URL location = cs == null ? null : cs.getLocation();
```

- `clazz.getClassLoader() == null` usually indicates the class was defined by the bootstrap loader.
- `clazz.getName()` gives the **binary name**, which is not enough to distinguish two classes with the same name.
- `CodeSource.getLocation()` can help find the source JAR; for bootstrap/generated classes or other policies, it **may be null**. Do not treat that URL as the sole proof of origin.
- If logging inside a transformer, avoid triggering reflection or deep lazy class loading directly inside the callback.

For a transformer, the `loader` and `module` parameters of the Java 9+ callback help identify the target context. However, `loader == null` does not mean the class “belongs to the agent”; it usually refers to bootstrap. Do not guess the owner from a single parameter alone.

### 9.2. Enumerate resource collisions

```java
// Illustrative snippet inside a method with a known loader:
java.util.Enumeration<java.net.URL> found =
        loader.getResources("sample/shared/config.properties");

while (found.hasMoreElements()) {
    System.out.println(found.nextElement());
}
```

In tests you can print URLs, but production logs need redaction because deployment paths can contain internal details. With named modules, results may be restricted by encapsulation rules, so a resource not appearing in the list is not necessarily absent under other access methods.

### 9.3. Scan artifacts before publishing

Before releasing an agent:

```shell
jar tf agent.jar
jar tf bootstrap-helper.jar
```

Check via build script/CI (not just by visual inspection):

- No classes in application packages unless explicitly designed.
- No `com/common`, `org/example/util`, or unintentionally unrelocated library namespaces.
- Bootstrap JAR contains only the **necessary bootstrap bridge**, without bundling exporter/JSON/logger dependencies.
- Root-level resources and `META-INF/services` match an allowlist.
- Manifest `Premain-Class`/`Agent-Class` have the right binary names and matching class entries.
- If shaded, verify names/relocated paths, service descriptors, and license notices.
- If bundling a multi-release JAR, inspect `META-INF/versions/*` and the `Multi-Release: true` manifest attribute to avoid missing class collisions in versioned directories.
- Test at runtime with the **actual JDK, app class loader, framework, and module setup**; do not test only with unit tests on the system classpath.

## 10. Common errors and diagnostic order

| Symptom | Possible cause | How to verify |
|---|---|---|
| `NoSuchMethodError` after adding agent | Runtime picked a colliding class with a different API version | Print binary name, defining loader, CodeSource, `javap -p -s` of both artifacts |
| `ClassCastException: X cannot be cast to X` | Two definitions with the same name but different loaders | Compare `clazz.getClassLoader()`/module, trace object passing path |
| `IllegalAccessError` when calling accessor/helper | Runtime package/loader mismatch; bootstrap may have hijacked a class | Check bootstrap-appended JAR, package-private classes, loader identity |
| `NoClassDefFoundError` for `ProbeBridge` | Target's loader cannot see helper, or reference resolution failed earlier | Check that JAR was appended **before use**, loader/module visibility, Javadoc failed-resolution caching |
| `SecurityException` when loading package | Possible violation of sealed package or restricted package name rules | Check manifest `Sealed`, package definition, where the class is loaded from |
| Agent reads the app's config | Duplicate resource path and parent-first loader | `getResources(name)`, URLs, and actual artifact |
| App uses wrong logging config | Agent packaged a generic root resource | Scan `jar tf` and classloader lookup; move config into a dedicated namespace |
| `ServiceConfigurationError` after shading | Service descriptor/provider name mismatch | Check `META-INF/services`, relocated binary names, and chosen loader |
| Bootstrap helper cannot call app class | Bootstrap cannot see child classes | Separate bridge and runtime; do not add app dependencies to bootstrap |
| System append done yet target still cannot see helper | Target loader/module visibility differs; previously failed resolution | Check delegation path, Module reads/exports, timing of append |
| Class runs but behaves strangely | Same binary name, different implementation, no ABI error | Log loader/source, check checksum/class version; test semantics |
| Tests pass on Java 17 but fail on Java 21 | Different module/runtime/JAR/loader configuration | Test JDK+classloader matrix; verify versioned entries of multi-release JARs |

**Resolution order to follow:**

1. Identify the exact **class name, resource path** being looked up.
2. Check **which JAR actually contains the entry** (`jar tf`); do not look only at source.
3. Identify the **loader/module of the calling class** and its delegation path.
4. Check which **loader/source is actually chosen**, without assuming global child/parent priority.
5. Compare binary API descriptors and package/access rules.
6. For resources, check `getResources` and whether the file is subject to module encapsulation.
7. If caused by a collision, **change the namespace/relocate/rebuild the artifact**—do not arbitrarily force the JVM to prioritize the agent JAR in production.
8. Re-run tests with a freshly started cache/loader; do not rely on late appending after symbolic reference resolution has already failed.

## 11. Important misconceptions

1. **“Once you use a dedicated package name, all class loading problems disappear.”** No. The helper must still be visible to the loader/module of the instrumented bytecode.
2. **“Same binary name guarantees the same Class object.”** Not if the defining loaders differ.
3. **“If the agent JAR contains the class, that class will be used.”** No; parent-first may choose the version from the parent.
4. **“Resources belong to a Java class package, so they cannot collide.”** Resources only have paths; root resources and service descriptors collide very easily.
5. **“Just use child-first for the agent.”** That can cause the agent to hijack app classes in the reverse direction; it is not a default solution.
6. **“Bootstrap is a safe place to put all helpers and libraries.”** False; the Instrumentation Javadoc strictly warns against unintended classes/resources.
7. **“Putting a helper in the application package to call package-private methods always works.”** False: runtime package/module/loader identity and access control may differ.
8. **“Relocating a dependency only requires changing `.class` paths.”** False: reflection strings, resources, SPI, module metadata, manifest, and signatures may all need handling.
9. **“`getResource` always returns the file from the JAR calling the method.”** False: lookup goes through the loader, usually with delegation, and can return a file from the parent.
10. **“`getResources` always follows a single stable global order.”** Not across all loaders/modules; the experimental model has a specific order that should not be overgeneralized.
11. **“`appendToSystemClassLoaderSearch` also updates `java.class.path`.”** No, the Javadoc explicitly states that property is not modified.
12. **“Adding the helper JAR after a `NoClassDefFoundError` will definitely fix it.”** No, the JVM has a rule remembering failed symbolic reference resolutions.
13. **“A unique Java package is also security isolation.”** No: a namespace avoids name collisions, it does not create a sandbox.
14. **“Shorter package names are more convenient, and we can rename them later.”** Injected agent bytecode references binary names; renaming packages requires proper migration/versioning.
15. **“If there are no class collisions, there is no need to check resources.”** False; `application.properties`, `logback.xml`, and `META-INF/services` can still alter behavior.

## 12. Self-check questions

1. **What constitutes class identity?** Binary name and defining loader (along with the associated module/runtime access context).
2. **Why does `child` JAR have `sample.shared.Marker` yet `Class.forName` via child returns APP?** Because `URLClassLoader` delegates to its parent by default; the parent finds the class first.
3. **Is a resource named `sample/shared/config.properties` protected by a Java package namespace?** No. It is just a path looked up by a loader and can exist in multiple JARs.
4. **How does `getResources(name)` differ from `getResource(name)`?** One API enumerates multiple visible matches; the other finds a single match according to the loader/module's policy.
5. **Why must a bootstrap-appended JAR be minimal?** Because colliding entries may be picked by bootstrap first and cause application linkage/access failures.
6. **Does adding a JAR to the system search automatically make it visible to every custom loader?** No; it depends on delegation relationships and module visibility.
7. **Why can `IllegalAccessError` appear if a non-public class is loaded from the wrong loader?** Runtime package/access identity no longer matches even though the textual package name is the same.
8. **If the app and agent use two versions of the same dependency, what is the usual build solution?** Isolate loaders and/or relocate/shade the dependency into the agent namespace, and test the ABI.
9. **When relocating `com.foo.Provider`, what files besides `Provider.class` must be considered?** `META-INF/services`, reflection config, module/manifest/resources, and related dependencies.
10. **Why should `logback.xml` not be left in a bootstrap helper JAR?** It can be discovered by frameworks via classpath/resource search and affect the app.
11. **What proves which JAR a class actually came from?** Defining loader, `CodeSource` if available, class loading diagnostics, and verified artifact metadata.
12. **When `ClassLoader.getResourceAsStream` returns null, does that guarantee the resource is not in the JAR?** No: loader, module encapsulation, path, and access permissions also matter.
13. **Where does `Class.getResource("x.properties")` look?** Relative to the class's package; use `"/path/from/root"` for an absolute resource path.
14. **Is the package `io.acme.agent.internal` a security boundary?** No; it is a namespace convention to avoid name collisions.
15. **Why should a bootstrap helper not directly depend on app libraries?** The bootstrap loader typically cannot see classes defined by child/app loaders, easily causing linkage errors.
16. **In the example collision test, which build directory must be on the runtime classpath?** Only `build/demo`; `app.jar` and `helper.jar` are loaded by two explicit `URLClassLoader` instances.
17. **How is it confirmed that two resource versions are detected in the demo?** `SHARED_RESOURCE_MATCHES=2` from `getResources` and inspecting entries in the JARs.
18. **When should `-Xlog:class+load=info` be used?** When the JVM supports unified logging and you need to observe class load sources; do not treat the full output as a stable API.

## 13. Official references

- [Java SE 21 — ClassLoader](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassLoader.html): `loadClass`, parent-first delegation, `getResource`, `getResources`, package definition, loader identity.
- [Java SE 21 — URLClassLoader](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/URLClassLoader.html): finding classes/resources from URLs/JARs and configuring the parent loader.
- [Java SE 21 — Class](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html): `getClassLoader`, `getResource`, `getResourceAsStream`.
- [Java SE 21 — Instrumentation](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): `appendToBootstrapClassLoaderSearch`, `appendToSystemClassLoaderSearch`, and warnings on class/resource collisions and unresolved symbolic references.
- [Java SE 21 — java.lang.instrument](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/package-summary.html): agent JAR structure, `Premain-Class`, and `Agent-Class`.
- [Java SE 21 — ServiceLoader](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/ServiceLoader.html): `META-INF/services`, provider discovery, and loader selection.
- [Java SE 21 — Module](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Module.html): resource encapsulation and `Module.getResourceAsStream`.
- [Java SE 21 — JAR File Specification](https://docs.oracle.com/en/java/javase/21/docs/specs/jar/jar.html): manifest, package sealing, multi-release JARs, service descriptors.

**Key takeaway:** a good Java agent **does not compete for names** with the application. Place helpers and resources in a dedicated namespace, keep the bootstrap JAR minimal, isolate/relocate dependencies, and always verify **which class is defined by which loader, and which resource is actually read**. No namespace convention can replace testing class-loader/module visibility on the target JVM.

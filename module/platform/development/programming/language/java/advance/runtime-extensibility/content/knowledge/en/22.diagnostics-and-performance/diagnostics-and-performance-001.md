# Recording Plugin Identity, Version, CodeSource, Loader, and Module

## 1. The Diagnostic Problem in Plugin Systems

A Java host may discover two copies of `demo.plugin.GreetingPlugin` from two different JARs and load them into two `ClassLoader` instances. When an old callback continues executing after a hot reload, simply logging `GreetingPlugin failed` is not enough to determine which artifact caused the error.

A proper diagnostic record must combine **the plugin's business identity** with **the actual identity of the class loaded by the JVM**:

- **Plugin ID**: a stable name managed by the host/registry, for example `demo-greeting`.
- **Plugin version**: the deployed version, for example `1.0.0` or `2.0.0`; it must be clear which metadata is the source of truth.
- **CodeSource**: bytecode origin information attached to `ProtectionDomain`, typically containing the JAR or directory URL when a class is loaded from a file.
- **Defining classloader**: the loader object attached to the actual class, including the loader name and a host-managed generation ID.
- **Module**: a class may belong to a named module (JPMS) or the loader's unnamed module; the module layer can also be recorded.

These values do not substitute for one another. `pluginId` and version describe the deployment unit managed by the application. `CodeSource`, `ClassLoader`, and `Module` describe the JVM environment of **one specific class**. A plugin may consist of multiple classes across multiple JARs; those classes do not necessarily share the same CodeSource.

### Example of a Real Architectural Incident

~~~text
Registry: demo-greeting, active=2.0.0, generation=42
JAR v1: plugins/greeting-v1.jar
JAR v2: plugins/greeting-v2.jar

A new request goes through v2.
An old listener that was not unregistered still invokes the v1 instance.
~~~

If the log records `pluginId`, `pluginVersion`, `generation`, class name, CodeSource, and loader identity, we can distinguish whether the incident occurred in v1 or v2. In particular, **identical class names do not imply a single class identity**.

The goal of this lesson is to extract metadata using Java 17 APIs, structure logs cleanly, handle missing/untrusted values, cross-check against release metadata, and test two plugin versions within the same JVM.

## 2. Which Data Source Should Be Used for Each Field?

| Diagnostic Field | Recommended Source | Important Notes |
| --- | --- | --- |
| `pluginId` | Verified plugin registry/descriptor | Do not infer from file name or class name |
| `pluginVersion` | Verified release metadata | A string returned by the plugin itself may not match the registry |
| `deploymentGeneration` | Assigned by the plugin manager on each activation | Used to distinguish multiple loads of the same version |
| `implementationClass` | `plugin.getClass().getName()` | Binary name alone is insufficient to identify a class in the JVM |
| `codeSource` | `type.getProtectionDomain().getCodeSource()` | May be missing; URL does not prove signature/integrity |
| `definingLoader` | `type.getClassLoader()` | May be `null` for bootstrap classes |
| `loaderName` | `definingLoader.getName()` | May be `null` and is not guaranteed to be unique |
| `moduleKind` and `moduleName` | `type.getModule()`, `isNamed()`, `getName()` | Unnamed modules have `getName() == null` |
| `moduleLayer` | `type.getModule().getLayer()` | May be `null`; unnamed modules never belong to a layer |
| `artifactSha256` | Artifact verifier in pipeline/host | Digest of the verified bytes, not derived from URL alone |

The host should record both **expected metadata** from the deployment registry and **observed metadata** on the implementation `Class<?>`. If the values conflict, report a mismatch rather than silently trusting a self-declared version.

For example, the file name `greeting.jar` does not reliably indicate which version it is; the version in `MANIFEST.MF` might be absent, wrong, or unverified. If the registry says `2.0.0` while `plugin.version()` returns `1.0.0`, treat that as an anomaly—do not quietly log the second value as verified release metadata.

## 3. Reading CodeSource from the Actual Class

Typically, code obtains CodeSource via `Class` → `ProtectionDomain` → `CodeSource` → URL:

~~~java
// Illustrative code: the implementation variable is already the plugin's Class<?>.
ProtectionDomain protectionDomain =
        implementation.getProtectionDomain();

CodeSource source = protectionDomain == null
        ? null
        : protectionDomain.getCodeSource();

URL sourceLocation = source == null
        ? null
        : source.getLocation();

String origin = sourceLocation == null
        ? "<unavailable>"
        : sourceLocation.toExternalForm();
~~~

You need to import `java.security.ProtectionDomain`, `java.security.CodeSource`, and `java.net.URL`. This snippet is **not a standalone file**, because `implementation` is supplied by the plugin-loading code.

### What Does CodeSource Actually Tell Us?

`CodeSource` describes origin information attached to a class's protection domain when the loader defined it. For a local plugin JAR loaded via `URLClassLoader`, `getLocation()` is usually the JAR's URL. In other cases it may be a directory, an address using another scheme, or `null`.

Do not infer:

- "Null CodeSource" means suspicious code or a non-existent class. It can be completely valid, especially for classes defined by bootstrap or custom loaders.
- "CodeSource is path A" means the bytes **currently** on disk at A are guaranteed to match the loaded bytecode. The file may have changed afterward.
- "URL has the right name" means the JAR is trustworthy. A file name does not verify signatures, checksums, or publisher policies.
- "CodeSource is a file URL" is always true. Do not force every URL through `Path.of(url.toURI())` if the scheme could be `jrt:` or `https:`.

When logging in production, use `sourceLocation.toExternalForm()` if a URL is needed; also consider sanitizing URLs and masking sensitive parts. Absolute paths may leak usernames, directory structures, or internal mounts; external URLs may contain query parameters or tokens.

### CodeSource and Artifact Verification Are Different

A secure deployment can follow this sequence:

~~~text
Download / discover artifact
  -> verify declared ID and version
  -> compute SHA-256 and verify expected digest / signature
  -> store verified artifact path in registry
  -> create plugin loader
  -> load implementation
  -> observe CodeSource/loader/module
  -> match actual identity against verified entry
~~~

`CodeSource` is **diagnostic information**, not an integrity verification step by itself. If security policy requires identifying the publisher, an appropriate verification mechanism must run before activating plugin code. Log the hash from the actual verification result; if the system has not verified it, omit the hash field or log `null`—never fabricate a placeholder "hash" string.

For a `ClassNotFoundException`, there may not yet be a `Class<?>` object for the failed class from which to read CodeSource. In that case, log the class name, the loader attempted, the expected URL/JAR, and the exception; do not synthesize a fake CodeSource.

## 4. ClassLoader: Loader Name vs. Loader Identity

### 4.1. What Is the Defining Loader?

`Class.getClassLoader()` returns the class's loader or `null` for the bootstrap loader. For most plugins in separate JARs:

~~~java
Class<?> type = plugin.getClass();
ClassLoader definingLoader = type.getClassLoader();
~~~

**This is the actual class's defining loader**, not necessarily the loader object on which `loadClass` was called. Under parent delegation, a child loader may return a class defined by a parent loader.

Two classes with the same name defined by two different defining loaders are two distinct types:

~~~java
// Illustrative code: two Class<?> objects loaded from two generations.
boolean sameBinaryName =
        typeV1.getName().equals(typeV2.getName());
boolean sameIdentity = (typeV1 == typeV2);
boolean sameDefiningLoader =
        (typeV1.getClassLoader() == typeV2.getClassLoader());
~~~

Do not automatically conclude `sameIdentity == false` just because two initial loader variables are different. If both delegate to the same parent that already holds the implementation, they may return the exact same class.

### 4.2. Loader Names May Not Be Unique

Since Java 9, `ClassLoader.getName()` returns a name if the loader was given one, or `null` otherwise. You can create a named `URLClassLoader` on Java 17:

~~~java
// Illustrative code: urls and parentLoader are already initialized.
URLClassLoader loader = new URLClassLoader(
        "demo-greeting-generation-42",
        urls,
        parentLoader
);
~~~

Two classloaders can have **the exact same name**; naming is an operational aid, not an automatic unique key. The host should also assign a `loaderGeneration` or `pluginInstanceId` when creating the loader.

You can use a temporary ID scoped to a single JVM:

~~~java
String identityTag = definingLoader == null
        ? "<bootstrap>"
        : definingLoader.getClass().getName() + "@"
                + Integer.toHexString(
                        System.identityHashCode(definingLoader));
~~~

This is illustrative code, and `identityHashCode` is **not guaranteed to be collision-free**, does not persist across JVM restarts, and is unsuitable as a storage/audit key. For long-term tracing, use a host-generated ID with a clear link to the deployment generation.

### 4.3. Do Not Confuse Defining Loader with TCCL

~~~java
ClassLoader defining = type.getClassLoader();
ClassLoader tccl =
        Thread.currentThread().getContextClassLoader();
~~~

`tccl` is the running thread's **thread context classloader**, which a framework or plugin manager may temporarily swap to locate services/resources. It did not necessarily define `type`. If an old callback still holds the v1 loader's TCCL, record both `definingLoader` and `tccl` in investigative logs; never use TCCL in place of class identity.

In multi-threaded systems, TCCL is also a common source that keeps old loaders alive across reloads. When temporarily setting TCCL, always restore it in a `finally` block on **the same thread** that was modified, and cancel old tasks when stopping a plugin.

## 5. Module: Named, Unnamed, and Layer

Java 9+ includes JPMS. `Class.getModule()` returns a `Module` object; classes on the classpath or loaded via an ordinary `URLClassLoader` belong to the defining loader's **unnamed module**.

~~~java
// Illustrative code: type is Class<?>.
Module module = type.getModule();
boolean named = module.isNamed();
String moduleName =
        named ? module.getName() : "<unnamed>";
ModuleLayer layer = module.getLayer();
~~~

Key points to remember:

- `Module.getName()` is `null` for an unnamed module; **null does not mean the class belongs to no module**.
- `Module.getDescriptor()` is also `null` for an unnamed module; for a named module, the descriptor may contain version metadata, though it is not required.
- `Module.getLayer()` may be `null` if the module does not belong to a layer; unnamed modules always have a `null` layer.
- A named module's name is not necessarily the plugin ID. One plugin may consist of multiple modules; multiple modules may relate to the same plugin deployment.
- With custom module layers, record a **host-managed layer identity/generation** to distinguish load generations. Recording only the module name may be insufficient.
- When diagnosing `IllegalAccessError` or `InaccessibleObjectException`, `requires/reads`, `exports`, and `opens` in the module graph matter more than just seeing the class name.

### Is the Module Descriptor Version the Plugin Version?

Not by default. For example:

~~~java
// Illustrative code: the implementation class already exists.
Module m = implementation.getModule();
String descriptorVersion = m.getDescriptor() == null
        ? "<not-applicable>"
        : m.getDescriptor().version()
                .map(Object::toString)
                .orElse("<unspecified>");
~~~

`ModuleDescriptor.version()` is optional. Similarly, `Package.getImplementationVersion()` can return `null` if the manifest lacks `Implementation-Version` or the package was not provided that metadata. The system must explicitly define whether **the deployment version from the registry** is the source of truth and cross-check it against self-declared versions.

## 6. Complete Java 17 Example: Same Plugin ID, Two JARs, and Two Loaders

We create a shared host-owned API and two implementations sharing the same name `demo.plugin.GreetingPlugin` in v1/v2 JARs. The host loads both using named `URLClassLoader` instances, extracts metadata from the actual classes, and compares class identity.

### 6.1. File Structure

~~~text
plugin-metadata-demo/
  src/
    api/demo/api/Plugin.java
    v1/demo/plugin/GreetingPlugin.java
    v2/demo/plugin/GreetingPlugin.java
    host/demo/host/PluginMetadataDemo.java
  build/                     (created by the compile command)
~~~

The plugin JARs **must not be placed on the application classpath**, otherwise the parent loader may load the implementation first, defeating the demo's purpose of distinguishing two loaders.

### 6.2. API File: src/api/demo/api/Plugin.java

~~~java
package demo.api;

public interface Plugin {
    String id();
    String version();
    String message();
}
~~~

### 6.3. Plugin v1: src/v1/demo/plugin/GreetingPlugin.java

~~~java
package demo.plugin;

import demo.api.Plugin;

public final class GreetingPlugin implements Plugin {
    public GreetingPlugin() {
    }

    @Override
    public String id() {
        return "demo-greeting";
    }

    @Override
    public String version() {
        return "1.0.0";
    }

    @Override
    public String message() {
        return "hello-v1";
    }
}
~~~

### 6.4. Plugin v2: src/v2/demo/plugin/GreetingPlugin.java

~~~java
package demo.plugin;

import demo.api.Plugin;

public final class GreetingPlugin implements Plugin {
    public GreetingPlugin() {
    }

    @Override
    public String id() {
        return "demo-greeting";
    }

    @Override
    public String version() {
        return "2.0.0";
    }

    @Override
    public String message() {
        return "hello-v2";
    }
}
~~~

Both implementations have the same binary name but different bytes and reside in two separate JARs. The `version()` method is an illustrative contract, not yet metadata independently verified by a registry.

### 6.5. Host: src/host/demo/host/PluginMetadataDemo.java

~~~java
package demo.host;

import demo.api.Plugin;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.CodeSource;
import java.security.ProtectionDomain;

public final class PluginMetadataDemo {
    private PluginMetadataDemo() {
    }

    public static void main(String[] args) throws Exception {
        Path v1 = Path.of("build/jars/plugin-v1.jar");
        Path v2 = Path.of("build/jars/plugin-v2.jar");

        if (!Files.isRegularFile(v1) || !Files.isRegularFile(v2)) {
            throw new IllegalStateException("Plugin JAR missing");
        }

        ClassLoader parent =
                PluginMetadataDemo.class.getClassLoader();

        try (URLClassLoader loader1 = new URLClassLoader(
                    "plugin-v1",
                    new URL[]{v1.toUri().toURL()}, parent);
             URLClassLoader loader2 = new URLClassLoader(
                    "plugin-v2",
                    new URL[]{v2.toUri().toURL()}, parent)) {

            Class<?> c1 = Class.forName(
                    "demo.plugin.GreetingPlugin", true, loader1);
            Class<?> c2 = Class.forName(
                    "demo.plugin.GreetingPlugin", true, loader2);

            Plugin p1 = (Plugin) c1
                    .getDeclaredConstructor().newInstance();
            Plugin p2 = (Plugin) c2
                    .getDeclaredConstructor().newInstance();

            show(p1, c1);
            show(p2, c2);

            System.out.println("sameBinaryName="
                    + c1.getName().equals(c2.getName()));
            System.out.println("sameClass=" + (c1 == c2));
            System.out.println("sameDefiningLoader="
                    + (c1.getClassLoader() == c2.getClassLoader()));
            System.out.println("bothImplementHostApi="
                    + (Plugin.class.isAssignableFrom(c1)
                            && Plugin.class.isAssignableFrom(c2)));
        }
    }

    private static void show(Plugin plugin, Class<?> type)
            throws Exception {
        ClassLoader defining = type.getClassLoader();
        Module module = type.getModule();

        ProtectionDomain pd = type.getProtectionDomain();
        CodeSource cs = pd == null ? null : pd.getCodeSource();
        URL url = cs == null ? null : cs.getLocation();

        // In this demo, CodeSource has a file: URL pointing to the JAR.
        String file = url == null ? "<unavailable>"
                : Path.of(url.toURI()).getFileName().toString();

        String loaderName = defining == null
                ? "<bootstrap>"
                : (defining.getName() == null
                        ? "<unnamed-loader>" : defining.getName());

        String moduleName = module.isNamed()
                ? module.getName() : "<unnamed>";

        System.out.println(
                "plugin=" + plugin.id() + "@" + plugin.version());
        System.out.println("codeSourceFile=" + file);
        System.out.println("loaderName=" + loaderName);
        System.out.println("module=" + moduleName);
        System.out.println("message=" + plugin.message());
    }
}
~~~

Because the loaders are created from two `file:` URLs pointing to local JARs, `Path.of(url.toURI())` is valid in this example. A general-purpose logger should use `url.toExternalForm()` or handle schemes and `null` rather than always assuming the URL is a disk path.

### 6.6. Compile and Run Commands

In the `plugin-metadata-demo` directory with JDK 17+, using Bash:

~~~bash
mkdir -p build/api build/v1 build/v2 build/host build/jars

javac --release 17 -encoding UTF-8 \
  -d build/api src/api/demo/api/Plugin.java
jar --create --file build/plugin-api.jar -C build/api .

javac --release 17 -encoding UTF-8 \
  -cp build/plugin-api.jar -d build/v1 \
  src/v1/demo/plugin/GreetingPlugin.java
jar --create --file build/jars/plugin-v1.jar -C build/v1 .

javac --release 17 -encoding UTF-8 \
  -cp build/plugin-api.jar -d build/v2 \
  src/v2/demo/plugin/GreetingPlugin.java
jar --create --file build/jars/plugin-v2.jar -C build/v2 .

javac --release 17 -encoding UTF-8 \
  -cp build/plugin-api.jar -d build/host \
  src/host/demo/host/PluginMetadataDemo.java

java -cp "build/host:build/plugin-api.jar" \
  demo.host.PluginMetadataDemo
~~~

**Exact stdout of the example in the configuration above:**

~~~text
plugin=demo-greeting@1.0.0
codeSourceFile=plugin-v1.jar
loaderName=plugin-v1
module=<unnamed>
message=hello-v1
plugin=demo-greeting@2.0.0
codeSourceFile=plugin-v2.jar
loaderName=plugin-v2
module=<unnamed>
message=hello-v2
sameBinaryName=true
sameClass=false
sameDefiningLoader=false
bothImplementHostApi=true
~~~

When running on Windows PowerShell, use a semicolon in the classpath:

~~~powershell
java -cp "build/host;build/plugin-api.jar" demo.host.PluginMetadataDemo
~~~

The multi-line `javac`/`jar` commands above use backslashes per Bash syntax. In PowerShell, you can write those commands on a single line. To inspect the output JAR files:

~~~bash
jar --list --file build/jars/plugin-v1.jar
jar --list --file build/jars/plugin-v2.jar
~~~

Each JAR must contain `demo/plugin/GreetingPlugin.class`. The host compiles only against `plugin-api.jar`, without containing the implementation on the application classpath. As a result, `loader1` and `loader2` genuinely define two separate copies of the class in the example.

**Interpretation:**

- Same Plugin ID: both belong to the same business unit `demo-greeting`.
- Different Versions: v1 code returns `1.0.0`, v2 code returns `2.0.0`.
- Different CodeSources: the v1 class comes from `plugin-v1.jar`, the v2 class from `plugin-v2.jar`.
- Different Defining Loaders: `plugin-v1` and `plugin-v2`, so `c1 != c2` even though the class names are equal.
- Both Modules are `<unnamed>` because the classes are loaded from classpath entries in `URLClassLoader`, not JPMS named modules.
- Both classes implement the shared `demo.api.Plugin` defined by the host, so the cast succeeds.

The program intentionally keeps both loaders alive simultaneously for comparison. It **does not implement production hot reload**; in a real host, after switching routing you must stop the old instance, cancel callbacks/tasks, close the loader, and remove registry references according to the lifecycle.

## 7. Named Module Example: When the Module Field Actually Changes

A plugin JAR/classpath in `URLClassLoader` normally belongs to an unnamed module, whereas JPMS has named modules with `module-info.java`. Create a second example (independent of the files in section 6):

~~~text
modsrc/
  demo.namedplugin/
    module-info.java
    demo/namedplugin/ModuleProbe.java
~~~

**File `modsrc/demo.namedplugin/module-info.java`:**

~~~java
module demo.namedplugin {
}
~~~

**File `modsrc/demo.namedplugin/demo/namedplugin/ModuleProbe.java`:**

~~~java
package demo.namedplugin;

public final class ModuleProbe {
    private ModuleProbe() {
    }

    public static void main(String[] args) {
        Module module = ModuleProbe.class.getModule();
        System.out.println("named=" + module.isNamed());
        System.out.println("module=" + module.getName());
        System.out.println(
                "bootLayer=" + (module.getLayer() == ModuleLayer.boot()));
    }
}
~~~

Compile and run on JDK 17 using Bash:

~~~bash
mkdir -p build/mods
javac --release 17 -encoding UTF-8 \
  --module-source-path modsrc \
  -d build/mods --module demo.namedplugin

java --module-path build/mods \
  --module demo.namedplugin/demo.namedplugin.ModuleProbe
~~~

Stdout:

~~~text
named=true
module=demo.namedplugin
bootLayer=true
~~~

Because the application is launched via the module launcher with this module as root, the module resides in the boot layer in the example above. In an application creating a custom `ModuleLayer`, the layer field may point to another layer. For an unnamed module, `getLayer()` returns `null`. Module names can also collide across two different layers; to diagnose replacement of named-module plugins, log the module name together with the layer/generation and classloader.

If a named module has a descriptor version, `module.getDescriptor().version()` returns an `Optional`; if no version was assigned, it is empty. Do not assume the module descriptor version is always the plugin's deployment version.

## 8. Designing Structured Logs and Stable IDs

A suggested JSON entry:

~~~json
{
  "event": "plugin.activated",
  "pluginId": "demo-greeting",
  "pluginVersion": "2.0.0",
  "deploymentGeneration": 42,
  "implementationClass": "demo.plugin.GreetingPlugin",
  "codeSource": "file:/app/plugins/plugin-v2.jar",
  "loaderName": "plugin-v2",
  "loaderGeneration": 42,
  "moduleKind": "unnamed",
  "moduleName": null,
  "moduleLayer": null,
  "artifactSha256": null,
  "result": "activated"
}
~~~

This is **illustrative JSON**, not log output emitted by the Java demo. `artifactSha256: null` means no digest was supplied in the example record; a production system must obtain the real value from the artifact verification step and never fabricate a hash. If the version was verified by the registry, you can add `verifiedPluginVersion` alongside the self-reported `Plugin.version()` value to distinguish them.

Events that should be logged:

| Event | When | Useful Fields |
| --- | --- | --- |
| `plugin.discovered` | When an artifact is found | Declared ID/version, scan source, artifact path |
| `plugin.verified` | After checking digest, signature, and policy | Verified ID/version, actual hash, outcome |
| `plugin.loaded` | When the implementation class is loaded by the JVM | Class, defining loader, CodeSource, module |
| `plugin.activated` | When start succeeds and routing switches | ID, version, generation, loader/module |
| `plugin.invocation.failed` | When an invocation fails | Correlation ID, generation, class, exception |
| `plugin.deactivated` | When stopping new requests and shutting down | Old/new generation, reason, in-flight count |
| `plugin.released` | After cleanup/closing loader and dropping registry refs | Cleanup result, close errors, remaining tasks |

`plugin.released` does not mean the JVM has garbage-collected or unloaded all classes. To track class unloading, you need JVM metrics and heap/thread diagnostics rather than inferring it solely from a lifecycle hook result.

### Correlation IDs and Deployment Generations

When hot reloading mid-request, logs should tie the request ID / trace ID to `deploymentGeneration`. A complete record can be traced back across service instance, plugin ID, version, and loader generation without relying on potentially colliding loader names or identity hashes.

Do not use `System.identityHashCode(loader)` as a database key across JVM restarts. One approach is for the host to generate a `serviceInstanceId` at startup and a new `pluginGeneration` on every activation. When running multiple instances or replicas, record the instance/region in accordance with observability and data protection policies.

### Logging Performance

Extracting metadata via reflection and formatting URLs repeatedly on **every** request can increase CPU and log volume. Capture a string snapshot at load/activate time, log compact fields (`pluginId`/`version`/`generation`) on the hot path, and attach CodeSource/module/loader details on errors.

Do not keep a `Map<Class<?>, ...>` or `ClassLoader` in a global cache solely for logging, as it can retain old plugin loaders after stop. The snapshot should contain only plain data (`String`, numbers, enums) and be discarded along with the generation's lifecycle.

## 9. Common Diagnostic Pitfalls

### 9.1. Wrong Loader Selected Due to Parent Delegation

The host may report having loaded the v2 JAR, yet `implementation.getClassLoader()` returns the parent loader containing v1. If the implementation exists on the parent classpath, the child loader can receive the old class. Check the defining loader and CodeSource of **the class actually used**; do not merely print the URL list the plugin manager intended to pass when creating the loader.

### 9.2. Class Name Exists Without a CodeSource

A `ClassNotFoundException` typically occurs before a class object exists. In that case, log the class name, expected JAR/module path, the loader attempting to load it, and the stack trace. If a class exists but its CodeSource is null, display an explicit missing-value marker; do not treat null automatically as a security failure.

### 9.3. Null Module Name Does Not Mean No Module

A class in an unnamed module still belongs to a `Module`. If a logger calls `module.getName().toString()`, it can hit a `NullPointerException`. Use `module.isNamed()` and normalize to a readable label.

### 9.4. Plugin Claims Version A While Registry Says B

Because plugin ID/version can be self-reported by the plugin, cross-check against the deployment registry and hash. Log the mismatch and check whether the class was accidentally loaded from an old artifact. Never arbitrarily pick one version as canonical while an incident is under investigation.

### 9.5. ClassCastException or NoSuchMethodError After Upgrade

Two classes with the same name `demo.api.Plugin` defined by two separate loaders cannot be cast to each other; a method compiled against a newer API may not exist in an older runtime version. Log the defining loader and CodeSource of both the API class and the implementation; check dependency contracts, versions, and ABI.

### 9.6. Old Classes Not Unloaded After Close

`URLClassLoader.close()` closes resources managed by the loader but does not force loaded classes to disappear. Listeners, host static caches, `ServiceLoader`, `Class<?>`, `Method`, TCCL, `ThreadLocal`, and still-running executors can all retain the old loader. Use thread dumps, heap dominators, and JFR/JVM class unloading events to inspect **GC roots** and actual reload counts.

### 9.7. Logging Itself Causes Leaks or Data Exposure

Do not hold plugin instances in MDC or singleton logger contexts beyond the request lifecycle. Context added to MDC must be cleared in a `finally` block. Avoid logging raw URLs containing credentials, query tokens, or private paths; validate/escape externally supplied plugin IDs/versions to prevent log injection. Configure appropriate sampling, retention, and log access permissions.

## 10. Lifecycle Metadata Recording Workflow

A plugin manager can organize steps as follows:

1. **DISCOVER:** receive artifact, read declared metadata; assign `pluginId` and expected version per the registry.
2. **VERIFY:** verify hash/signature and compatibility; assign artifact ID/digest. If verification fails, do not load the plugin.
3. **LOAD:** create loader or module layer; assign generation; load implementation. Obtain the actual `Class` and capture CodeSource, defining loader, and module/layer.
4. **VALIDATE:** verify API contract and expected version; log mismatches if any; do not treat CodeSource as a trust guarantee.
5. **ACTIVATE:** publish routing, log the activation event, and keep the snapshot bound to the lifecycle.
6. **INVOKE:** use correlation ID and paired generation metadata; log details on errors, without serializing every reflection object on each request.
7. **STOP:** block new requests, drain in-flight calls, cancel listeners/timers/executors, and clean up ThreadLocals/TCCL.
8. **RELEASE:** close plugin-owned resources, close `URLClassLoader` if host-owned, and remove registry/cache entries and snapshots. Do not label it "unloaded" until actual JVM evidence confirms it.

This sequence is an organizational model, not a standard Java API. If a system involves state migration or exclusive resources, the cutover order must be adjusted; the invariant is never using metadata from an old loader to validate a new plugin.

## 11. Verification Checklist

- [ ] Managed deployment ID and version exist, not mistakenly derived from class name or JAR path.
- [ ] Each generation is bound to a verified artifact and a specific loader/module layer.
- [ ] CodeSource is retrieved from `Class.getProtectionDomain()` with null handling.
- [ ] `clazz.getClassLoader()` is recorded and defining loader is distinguished from TCCL.
- [ ] `loader.getName()` is logged safely when null and the name is not treated as a unique key.
- [ ] `Module.isNamed()`, `getName()`, and layer/descriptor version are recorded when needed, with null handling.
- [ ] A class name field is included to distinguish implementations sharing the same plugin ID.
- [ ] Events are logged at discovered, verified, loaded, activated, failed, deactivated, and released stages.
- [ ] A correlation ID links each request to the executing version/generation.
- [ ] CodeSource paths/URLs are sanitized so sensitive information is not exposed.
- [ ] Fake hashes are never logged and URLs are not mistaken for trusted signatures.
- [ ] Metadata caches do not retain plugin `Class<?>`/`ClassLoader` references indefinitely.
- [ ] Tested across multiple hot reloads, two loaders with the same binary name, parent delegation, and JPMS named and unnamed modules.

## 12. Self-Check Questions

1. If two loaders define classes with the same binary name, are they the same type? **No.** Check the defining loader and `Class<?>` identity.
2. What does `Class.getClassLoader() == null` mean? Usually that the class was loaded by the bootstrap loader, not that loader data was lost.
3. What does `ClassLoader.getName() == null` mean? The loader may simply be unnamed, which is different from a null loader object.
4. Does a CodeSource pointing to the v2 JAR prove the bytes are safe? **No.** A hash/signature verification policy is required.
5. Why can CodeSource be missing? ProtectionDomain or CodeSource/location may not be provided depending on the loader/runtime.
6. Does `Module.getName() == null` mean there is no module? **No**, it may be an unnamed module.
7. Are versions in `Package.getImplementationVersion()` or `ModuleDescriptor.version()` always the plugin version? **No**, an explicit contract is required.
8. Why is using a loader identity hash as an audit key insufficient? It can collide and does not survive restarts.
9. When v1 is still running after a reload, what should you log first? Plugin ID/version/generation, request ID, implementation class, CodeSource, defining loader, and module.
10. Does calling `URLClassLoader.close()` guarantee the JVM unloads old classes? **No**, references must be cleared and unloading depends on JVM GC.

## 13. Java 17 API References

- [Class.getClassLoader, getModule, getProtectionDomain](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html)
- [ClassLoader.getName](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html)
- [ProtectionDomain.getCodeSource](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/ProtectionDomain.html)
- [CodeSource.getLocation](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/CodeSource.html)
- [Module.getName, isNamed, and getLayer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Module.html)
- [URLClassLoader constructors](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html)

**Conclusion:** A plugin diagnostic record is only meaningful when it connects **host-managed ID and version** with **the CodeSource, defining classloader, and module of the class actually loaded**. By logging per generation with null handling, verified version sources, and correlation IDs, you can trace lingering old plugins, classes accidentally loaded from a parent, module errors, or references retaining loaders. Observed metadata helps explain incidents; it does not replace artifact verification, lifecycle management, or execution security.

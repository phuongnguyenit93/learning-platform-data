# Testing Duplicate Dependency Versions, Duplicate Resources, and Duplicated Contracts

## 1. Goal: Test the Real Package, Not Just Source Code

In a Java plugin system, a clean compile **does not guarantee** that deployed JARs will load the right classes, resources, and SPI interfaces. A plugin may compile against library version A yet encounter version B at runtime. Two JARs may both contain `config/plugin.properties` or `META-INF/services/...`; a shared API may accidentally be packaged a second time inside a plugin. These defects often surface only when the host actually uses its classloaders and post-packaging artifacts.

This lesson focuses on **three distinct conflict categories that must be tested separately**:

1. **Duplicate dependency versions / duplicate classes:** multiple JARs contain the same binary class name, such as `demo.lib.Version`, with differing bytecode or APIs; which version does the loader ultimately pick?
2. **Duplicate resource paths:** multiple JARs contain `config/plugin.properties`, `META-INF/services/demo.api.Codec`, or other configuration metadata; how does fetching *one* resource differ from fetching *all*?
3. **Duplicated contracts (duplicate API/SPI contract):** `demo.api.Codec` exists in both the host and the plugin. If classloaders **define two separate copies**, the provider can become incompatible with the `Codec` type expected by the host, despite having identical package and method names.

These are **defects in class-loading topology and artifact packaging**, not three names for the same bug. You must test JAR structure, runtime outcomes, and the real loading mechanism.

### Same Name Does Not Mean Same Class

The runtime identity of a Java class depends on **both its binary name and the classloader that defined it**. A `demo.api.Codec` defined by the host loader and a `demo.api.Codec` defined by a plugin loader can be **two distinct JVM types**. In that case, a provider class "implementing Codec" is true only for the copy of `Codec` that the provider class itself sees.

Conversely, **a single classloader** defines a class with a given binary name at most once within its namespace. If two JARs containing `demo.lib.Version` sit on the same search path, the classloader normally selects one definition according to its search policy; it **never merges two versions**. Even when execution throws no error, silently picking the wrong version can corrupt business behavior.

## 2. Distinguishing Collision Types

| Symptom | Collision Surface | Possible Manifestation | What to Test |
|---|---|---|---|
| Two copies of `demo.lib.Version` in two JARs | **Class binary name** and classloader | Wrong version chosen, `NoSuchMethodError`, `NoClassDefFoundError`, `AbstractMethodError`, or behavioral drift | Which loader defined the class? Which artifact supplied it? |
| Two `config/plugin.properties` | **Resource path** | Reading wrong config, getting one of many copies, overwritten data in fat JARs | `getResource` vs. `getResources`, content of every URL, and merge policy |
| Two `META-INF/services/demo.api.Codec` | **Service descriptor path** | Missing/duplicate provider names, `ServiceConfigurationError`, unexpected order | Descriptor in each artifact and real `ServiceLoader` result |
| API `demo.api.Codec` in both host and plugin | **Class identity** | `ClassCastException`, "not a subtype", `ServiceConfigurationError` | `hostApi == pluginApi` and `hostApi.isAssignableFrom(providerType)` |
| Duplicate package in JPMS | **Module/package graph** | `ResolutionException`, `LayerInstantiationException`, or broken dependency resolution | Module path, layers, loaders, and split packages |
| Same version with different bytecode/resources | **Artifact integrity** | Runtime diverges from lockfile or signed build | JAR hash, manifest, and actual contents |

Distinguish **severity of duplication**: two JARs both containing `META-INF/MANIFEST.MF` or `META-INF/services/...` is not always a bug. However, **identical resource paths** require an explicit handling policy, testable during merge or load. By contrast, two copies of a **service interface** defined by two different loaders almost always indicate an API boundary bug in an SPI system where host and provider interact directly.

## 3. Duplicate Class Versions: Classloader Analysis

### 3.1. Parent-First, Child-First, and JAR Ordering

A standard `URLClassLoader` uses **parent-first** delegation for class loading: the child loader asks its parent first, then searches its own URLs. When duplicate classes reside **on the search path of a single loader**, URL/classpath order can determine which copy is loaded. With two isolated plugin loaders, each loader can see a different dependency version.

```text
                       Host API loader
                         demo.api.Codec
                        /              \
            PluginLoader A             PluginLoader B
            plugin-a.jar               plugin-b.jar
            demo.lib.Version v1        demo.lib.Version v2
            demo.plugin.CodecPlugin    demo.plugin.CodecPlugin
                 |                           |
         implements host Codec        implements host Codec
```

The critical condition is that both plugins **share a single copy of the `demo.api.Codec` contract from the host**, while each can define its own `demo.lib.Version`. If the host accidentally places `demo.lib.Version` v1 on the parent classpath, parent-first delegation can force **both plugins to use v1**, regardless of v2 being inside B's JAR.

Do not apply the "first JAR wins" rule to **every** custom classloader. Depending on delegation policy, module path, and packaging, the winning class may vary. Tests must use **the exact production loader topology**, not just a flat unit-test classpath.

### 3.2. When Do Failures Surface?

- If v1 and v2 share method signatures but differ in behavior, the program can **run without throwing yet return wrong results**.
- If plugin code was compiled against `Version.newMethod()` while runtime loads an older copy lacking that method, link resolution at the call site can throw `NoSuchMethodError`.
- If a dependency is missing or a required class cannot be located, reflective lookups can fail with `ClassNotFoundException` or JVM linkage can throw `NoClassDefFoundError`.
- If an interface/implementation signature changes incompatibly, `AbstractMethodError` or other linkage/type errors can occur.

**Do not rely on exception messages alone to conclude which JAR caused the fault.** Log `Class.getClassLoader()`, `Class.getModule()`, and, when permitted, `ProtectionDomain.getCodeSource()` to trace the origin. `CodeSource` may be `null` or incomplete in some environments; custom classloaders can also configure it freely.

### 3.3. Build-Time Dependency Resolution Is Not Runtime Resolution

Maven/Gradle typically select dependency versions when resolving build configurations. Yet a plugin manager may dynamically open extra JARs outside the host's dependency graph. Conversely, a plugin may ship a fat/shaded JAR bundling unexpected classes.

Therefore combine **dependency graph**, **JAR contents**, **classloader source**, and **integration tests running the exact artifacts**. Inspecting `mvn dependency:tree` alone does not prove which library version the host's `URLClassLoader` will pick.

## 4. Duplicate Resources: getResource, getResources, and Merging

### 4.1. Resource Files Have No Class Identity

Resources are looked up by **path name**, for example:

```text
config/plugin.properties
META-INF/services/demo.api.Codec
log-config.xml
META-INF/some-framework.index
```

Resources are **not** subtype-checked like classes. If two JARs contain the same path, `ClassLoader.getResource("config/plugin.properties")` returns **one** discovered URL; `getResources("config/plugin.properties")` returns an **Enumeration** of all URLs visible to the loader. With standard `URLClassLoader`, URL ordering determines part of the lookup behavior; with custom loaders, packaging, and delegation, never rely on ordering not guaranteed by the application contract.

To inspect *all* configurations:

```java
// Illustrative snippet inside a method allowing IOException.
Enumeration<URL> urls = loader.getResources("config/plugin.properties");
while (urls.hasMoreElements()) {
    URL url = urls.nextElement();
    System.out.println(url);
}
```

This snippet requires importing `java.net.URL`, `java.util.Enumeration`, and a suitable `loader`. Output URLs depend on machine and paths, so no fixed stdout is shown here. **Printing the URL list** is an important check to distinguish "none found", "only one found", and "multiple found".

### 4.2. Do Not Arbitrarily Merge Every Resource

Some files require **format-aware merging** (for example, multiple `META-INF/services/<service-name>` descriptors). Configuration resources may instead need **priority selection**, fail-fast on duplicates, or namespacing per plugin. There is no universal merge rule for every resource type.

A common trap with **uber/fat JARs**: when a build tool merges multiple JARs into one, two entries sharing a path may be dropped, overwritten, or processed by a special transformer/plugin. Never assume that because two dependencies carry service descriptors, the final JAR retains providers from both. Testing the **final artifact** matters more than testing individual source JARs.

### 4.3. META-INF/services Is a Special Case

To publish SPI on the classpath:

```text
File: META-INF/services/demo.api.Codec
Content:
demo.plugin.CodecPlugin
```

The filename is the **binary name of the service interface**; each valid provider line is the binary name of an implementation class. `ServiceLoader` can read multiple descriptor files of the same name across JARs visible to the loader. Duplicate provider names follow `ServiceLoader` deduplication rules; never rely on that deduplication to mask a packaging bug, especially when two JARs ship **two different classes with the same provider name**.

A valid descriptor file alone does not prove a provider can be instantiated. Wrong classloader, missing classes, invalid constructor/factory, or duplicated service interfaces will fail when `ServiceLoader` is actually iterated.

## 5. Duplicated SPI Contracts: The Most Dangerous Bug When Splitting Loaders

### 5.1. Two Copies of demo.api.Codec Are Not One Contract

Suppose the host defines:

```java
package demo.api;

public interface Codec {
    String id();
}
```

The plugin compiles against the same interface source and also packages `demo/api/Codec.class` inside its own JAR. If the plugin's classloader uses a **child-first policy for package `demo.api`**, it can define its own `Codec` copy. Then:

```text
Host's demo.api.Codec          (host loader)
Plugin's demo.api.Codec        (child-first loader)
              |
     CodecPlugin implements plugin Codec

Host Codec.class.isAssignableFrom(CodecPlugin.class) == false
```

Even though `Codec.class.getName()` and the plugin's copy both return `demo.api.Codec`, **their class identities differ**. `ServiceLoader.load(Codec.class, pluginLoader)` receives the host's service class, encounters a provider that is not a subtype of that class, and throws `ServiceConfigurationError`. A manual cast would throw `ClassCastException`.

**Do not misunderstand:** the physical presence of `Codec.class` in a plugin JAR **does not automatically** cause two copies to be defined. If the loader is parent-first and the parent already loaded `Codec`, the copy inside the plugin JAR may be ignored. Still, packaging duplicates remains a release hazard because loader topology can change and easily trigger incompatibilities. Tests must catch **both duplicate files during packaging** and **duplicate class identities at runtime**.

### 5.2. Contract Packaging Rules

- Keep one stable API/SPI managed by the host or a shared module, such as `demo.api.Codec`.
- Plugins **compile against** the API without bundling a copy into the plugin JAR when the host supplies it.
- Choose delegation policies explicitly: contract packages are typically **parent-first** even when implementation dependencies need child-first.
- Never assume classes with matching names/methods are compatible. Check `==` on `Class<?>`, `isAssignableFrom`, and test real `ServiceLoader` discovery.
- In JPMS, check module readability, exports, package ownership, and layers. Splitting layers does not automatically cure duplicated contracts.

## 6. Complete Java 17+ Example: All Three Collisions in One Run

This example builds **two separate plugin JARs**, each bundling a different version of `demo.lib.Version` while implementing the host-supplied `demo.api.Codec` contract. Each JAR also contains `config/plugin.properties` at the same path to test resource collision.

Next, the example builds **bad-plugin.jar** intentionally bundling `demo/api/Codec.class` and uses a custom classloader that is child-first solely for `demo.api.`. The host proves: a duplicate class file becomes a **duplicate class identity** when the loading policy actually defines the API in the child loader.

### 6.1. Directory Structure

```text
duplicate-demo/
├── api/demo/api/Codec.java
├── lib-v1/demo/lib/Version.java
├── lib-v2/demo/lib/Version.java
├── plugin/demo/plugin/CodecPlugin.java
├── host/Host.java
└── resources/
    ├── a/
    │   ├── config/plugin.properties
    │   └── META-INF/services/demo.api.Codec
    └── b/
        ├── config/plugin.properties
        └── META-INF/services/demo.api.Codec
```

Output directories `out/...` and `jars/...` are created by the build commands in section 6.7; they are not in the initial source tree.

### 6.2. Shared Contract: api/demo/api/Codec.java

```java
package demo.api;

public interface Codec {
    String id();
}
```

**Only one copy** of the API sits on the host's application classpath. Both plugins reference this interface through the parent classloader.

### 6.3. Two Library Versions: Same Binary Name, Different Behavior

**lib-v1/demo/lib/Version.java:**

```java
package demo.lib;

public final class Version {
    private Version() { }

    public static String text() {
        return "v1";
    }
}
```

**lib-v2/demo/lib/Version.java:**

```java
package demo.lib;

public final class Version {
    private Version() { }

    public static String text() {
        return "v2";
    }
}
```

Both produce the exact same `demo/lib/Version.class` path with different `text()` bodies. On a single shared loader, only one definition wins. Across **two separate loaders**, v1 and v2 coexist as intended.

### 6.4. Provider Using Shared API: plugin/demo/plugin/CodecPlugin.java

```java
package demo.plugin;

import demo.api.Codec;
import demo.lib.Version;

public final class CodecPlugin implements Codec {
    public CodecPlugin() {
    }

    @Override
    public String id() {
        return "codec-" + Version.text();
    }
}
```

The provider is compiled against `lib-v1`, while plugin B packages `lib-v2`. Because both versions preserve **the exact same public method signature**, the class links cleanly and runtime output depends on which `Version` the active loader picks.

If v2 changes a signature incompatibly (for example removing `text()`), the test fails with a linkage error when `id()` is called, illustrating the difference between silent wrong behavior and runtime linkage failures.

### 6.5. Two Resource Sets with Colliding Paths

**resources/a/config/plugin.properties:**

```properties
name=A
```

**resources/b/config/plugin.properties:**

```properties
name=B
```

Both JARs include `config/plugin.properties` with different contents. The host calls `getResources` and reads each file to prove **both A and B** are found, rather than observing only the single URL returned by `getResource`.

**resources/a/META-INF/services/demo.api.Codec** and **resources/b/META-INF/services/demo.api.Codec** both contain:

```text
demo.plugin.CodecPlugin
```

Even with the same binary name, the two providers in **two separate loaders** are distinct classes. The test loads `CodecPlugin` from A and B, comparing class identity and service outputs.

### 6.6. Host and Child-First Loader Reproducing a Duplicated Contract

**host/Host.java:**

```java
import demo.api.Codec;
import java.io.InputStream;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Enumeration;
import java.util.List;
import java.util.Properties;
import java.util.ServiceConfigurationError;
import java.util.ServiceLoader;

public final class Host {
    private static URL jar(String filename) throws Exception {
        return Path.of("jars", filename).toAbsolutePath().toUri().toURL();
    }

    private static String providers(ClassLoader loader) {
        List<String> names = new ArrayList<>();
        for (Codec codec : ServiceLoader.load(Codec.class, loader)) {
            names.add(codec.id());
        }
        Collections.sort(names);
        return names.toString();
    }

    private static String version(ClassLoader loader) throws Exception {
        Class<?> type = loader.loadClass("demo.lib.Version");
        return (String) type.getMethod("text").invoke(null);
    }

    private static List<String> resources(ClassLoader loader)
            throws Exception {
        Enumeration<URL> urls =
                loader.getResources("config/plugin.properties");
        List<String> names = new ArrayList<>();

        while (urls.hasMoreElements()) {
            Properties properties = new Properties();
            try (InputStream in = urls.nextElement().openStream()) {
                properties.load(in);
            }
            names.add(properties.getProperty("name"));
        }

        Collections.sort(names);
        return names;
    }

    static final class ChildFirstApiLoader extends URLClassLoader {
        ChildFirstApiLoader(URL url, ClassLoader parent) {
            super(new URL[] {url}, parent);
        }

        @Override
        protected Class<?> loadClass(String name, boolean resolve)
                throws ClassNotFoundException {
            if (!name.startsWith("demo.api.")) {
                return super.loadClass(name, resolve);
            }

            synchronized (getClassLoadingLock(name)) {
                Class<?> type = findLoadedClass(name);
                if (type == null) {
                    try {
                        type = findClass(name);
                    } catch (ClassNotFoundException notInJar) {
                        type = super.loadClass(name, false);
                    }
                }
                if (resolve) {
                    resolveClass(type);
                }
                return type;
            }
        }
    }

    public static void main(String[] args) throws Exception {
        ClassLoader parent = Host.class.getClassLoader();
        URL jarA = jar("plugin-a.jar");
        URL jarB = jar("plugin-b.jar");
        URL badJar = jar("bad-plugin.jar");

        try (URLClassLoader a = new URLClassLoader(
                        new URL[] {jarA}, parent);
             URLClassLoader b = new URLClassLoader(
                        new URL[] {jarB}, parent);
             URLClassLoader combinedA = new URLClassLoader(
                        new URL[] {jarA, jarB}, parent);
             URLClassLoader combinedB = new URLClassLoader(
                        new URL[] {jarB, jarA}, parent);
             ChildFirstApiLoader bad = new ChildFirstApiLoader(
                        badJar, parent)) {

            System.out.println("a=" + providers(a));
            System.out.println("b=" + providers(b));

            Class<?> fromA = a.loadClass("demo.plugin.CodecPlugin");
            Class<?> fromB = b.loadClass("demo.plugin.CodecPlugin");
            System.out.println("provider.class.same=" + (fromA == fromB));

            System.out.println("combined.aFirst=" + version(combinedA));
            System.out.println("combined.bFirst=" + version(combinedB));
            System.out.println("resources=" + resources(combinedA));

            Class<?> duplicateApi = bad.loadClass("demo.api.Codec");
            Class<?> badProvider = bad.loadClass("demo.plugin.CodecPlugin");

            System.out.println("bad.api.same="
                    + (duplicateApi == Codec.class));
            System.out.println("bad.assignable="
                    + Codec.class.isAssignableFrom(badProvider));

            try {
                ServiceLoader.load(Codec.class, bad).findFirst()
                        .orElseThrow();
                System.out.println("bad.spi=found");
            } catch (ServiceConfigurationError error) {
                System.out.println("bad.spi=ServiceConfigurationError");
            }
        }
    }
}
```

Code walkthrough:

- `a` and `b` both **delegate loading `demo.api.Codec` to the host loader**, while defining the plugin and its dependency from their own JARs. Hence `ServiceLoader.load(Codec.class, a/b)` instantiates providers returning `codec-v1` and `codec-v2`.
- `fromA == fromB` is `false` because the two loaders defined two distinct `demo.plugin.CodecPlugin` classes despite identical binary names. This **does not break SPI compatibility** because both implement the host's API.
- `combinedA` orders A then B, while `combinedB` orders B then A. With `URLClassLoader` and this lookup path, `demo.lib.Version` from the first JAR wins: proof that ordering and loading policy must be tested when duplicate dependencies exist.
- `resources(combinedA)` uses `getResources`, reads `name` from **both** resources, and sorts them for deterministic stdout. Do not rely on URL ordering across arbitrary loaders.
- `bad-plugin.jar` also embeds `demo/api/Codec.class`. `ChildFirstApiLoader` prioritizes its own JAR only for `demo.api.` names and delegates all others normally.
- The API copy inside `bad` is not the host's `Codec.class`, so `bad.api.same=false`. The provider defined by `bad` implements **bad's copy of Codec**, making `isAssignableFrom` return false.
- When the host asks `ServiceLoader` for providers of **host `Codec.class`** through `bad`, the provider is not a valid subtype, throwing `ServiceConfigurationError`. We **print only the error type**, avoiding dependence on full messages that vary across JDK versions.

**Note:** this custom child-first loader is an **intentional test fixture** to reproduce duplicated API packaging bugs. Do not treat it as a production classloader or a sandbox. It also never overrides system namespaces like `java.*`.

### 6.7. Compile and Package JARs, PowerShell on JDK 17+

Run from `duplicate-demo` containing the files from section 6.1:

```powershell
New-Item -ItemType Directory -Force -Path out\api,out\v1,out\v2,out\plugin,out\host,jars | Out-Null

javac -d out\api api\demo\api\Codec.java
javac -d out\v1 lib-v1\demo\lib\Version.java
javac -d out\v2 lib-v2\demo\lib\Version.java

javac -cp "out\api;out\v1" -d out\plugin plugin\demo\plugin\CodecPlugin.java
javac -cp out\api -d out\host host\Host.java

jar --create --file jars\plugin-a.jar -C out\plugin . -C out\v1 . -C resources\a .
jar --create --file jars\plugin-b.jar -C out\plugin . -C out\v2 . -C resources\b .
jar --create --file jars\bad-plugin.jar -C out\plugin . -C out\v1 . -C out\api . -C resources\a .

java -cp "out\api;out\host" Host
```

**Important note:** the `-cp` argument to `java` **does not** contain the three plugin JARs. Putting them on the parent classpath would let parent-first delegation pick other copies and invalidate the tests. `Host` explicitly creates `URLClassLoader` instances for the chosen JARs.

Before running, you can inspect `jar --list --file jars\plugin-a.jar` and the other JARs. Notable entries:

```text
plugin-a.jar:
  demo/plugin/CodecPlugin.class
  demo/lib/Version.class
  META-INF/services/demo.api.Codec
  config/plugin.properties

plugin-b.jar:
  demo/plugin/CodecPlugin.class
  demo/lib/Version.class
  META-INF/services/demo.api.Codec
  config/plugin.properties

bad-plugin.jar:
  demo/plugin/CodecPlugin.class
  demo/lib/Version.class
  demo/api/Codec.class                <-- duplicated contract class
  META-INF/services/demo.api.Codec
  config/plugin.properties
```

This block **illustrates the entries that must exist**, not verbatim `jar --list` output: the real command also prints manifest and directory entries.

**Expected stdout of the program:**

```text
a=[codec-v1]
b=[codec-v2]
provider.class.same=false
combined.aFirst=v1
combined.bFirst=v2
resources=[A, B]
bad.api.same=false
bad.assignable=false
bad.spi=ServiceConfigurationError
```

This output is for the **exact files, classpath, and JDK 17+** in the example. It demonstrates all three collision types:

1. **Duplicate versions:** separate loaders allow v1/v2 to coexist; a combined loader lets URL order change which `Version` class is picked.
2. **Duplicate resources:** both A's and B's `config/plugin.properties` are found via `getResources`; calling only `getResource` would return a single URL.
3. **Duplicated contract:** the bad loader defines a separate `Codec` from the host and triggers a subtype failure as soon as `ServiceLoader` inspects the provider.

On macOS/Linux, replace the classpath separator `;` with `:` and use equivalent shell directory commands. The PowerShell commands above are not Bash syntax.

### 6.8. Why Use Both Positive and Negative Tests?

A test confirming only that plugin A runs is insufficient. You must prove **the right library** is loaded, **the full resource set** is discovered, and **bad packaging** is caught.

- **Positive:** `a=[codec-v1]`, `b=[codec-v2]`; both providers are subtypes of the shared API.
- **Order-sensitive:** `combined.aFirst=v1` and `combined.bFirst=v2`; shows duplicate classes change behavior when URL order flips.
- **Resource enumeration:** `resources=[A, B]`; both resources sharing a path are genuinely present.
- **Negative:** bad JAR intentionally bundles duplicate API; verifies `bad.api.same=false`, `bad.assignable=false`, and `ServiceConfigurationError`.

These are **targeted regression tests**. In CI, replace `System.out.println` with assertions and ensure tests run against **real post-build artifacts**, avoiding IDE/classpath unit tests that accidentally behave differently from production.

## 7. Testing SPI Provider Registration and Resource Packaging

### 7.1. Reading Descriptors by Exact Service Class

If the service type is `demo.api.Codec`, the descriptor must be named:

```text
META-INF/services/demo.api.Codec
```

Even a single character off in the path, or using the provider name instead of the service name, will prevent `ServiceLoader` from discovering the provider.

When the service type is a **nested class**, its binary name contains `$`; the filename must follow `Class.getName()`, never arbitrarily `getCanonicalName()`. Construct the path safely with:

```java
// Illustrative snippet in host.
String path = "META-INF/services/" + Codec.class.getName();
Enumeration<URL> descriptors = pluginLoader.getResources(path);
```

`getResources` lists every visible descriptor before invoking `ServiceLoader`. If JARs are merged, verify that the merged list of provider classes remains valid without dropping critical provider lines.

### 7.2. Asserting the Right Provider Is Instantiated

With `ServiceLoader`, merely having a descriptor or `Class.forName` succeed is not enough. Actually **iterate**:

```java
// Illustrative snippet.
List<String> ids = new ArrayList<>();
for (Codec codec : ServiceLoader.load(Codec.class, pluginLoader)) {
    ids.add(codec.id());
}
Collections.sort(ids);
```

`ServiceConfigurationError` can happen right at provider load/instantiation due to a misspelled class name, missing dependency, API identity mismatch, or invalid constructor/factory. For classpath providers, standard lookup expects a valid provider class with a public no-arg constructor. For **named modules** (JPMS), provider declarations and `provider()` factories differ, so tests must use the corresponding module topology.

### 7.3. Identical Provider Names Do Not Imply Identical Bytecode

Two descriptors may both list `demo.plugin.CodecPlugin`, yet two JARs can hold **two classes with the same name and different bytecode**. If loaded into **one loader**, class lookup picks one; `ServiceLoader` handles descriptors by its own rules. If loaded by two separate loaders, two independent classes coexist. Thus tests checking only provider names will miss class-identity/bytecode defects.

## 8. Testing Contract Packaging in CI

### 8.1. Enforcing Which Artifact May Contain the API

In a typical host/plugin architecture:

```text
host / api.jar:
  demo/api/Codec.class

plugin-a.jar:
  demo/plugin/CodecPlugin.class
  demo/lib/Version.class
  META-INF/services/demo.api.Codec
  (does not contain demo/api/Codec.class)
```

If a plugin only **compiles against** a host-provided API, configure the API dependency so it **is not packaged into the shipped artifact**. For example:

- Maven: the API dependency can use `provided` scope if the host guarantees providing the exact API at runtime; verify fat-JAR/shading plugins actually exclude the API from the artifact.
- Gradle Java: `compileOnly` prevents bundling the API into default runtime artifacts when the host supplies it; shadow/fat-JAR plugins and runtime packaging must still be checked separately.
- In JPMS, the API can be a shared module resolved in a parent layer. Never duplicate the API in a way that alters type identity between host and plugin.

**Never assume build scopes automatically guarantee packaging.** A custom build plugin can inadvertently pull API classes into the final JAR. Always inspect actual entries.

### 8.2. Artifact Inspection Commands

In PowerShell:

```powershell
jar --list --file jars\plugin-a.jar
jar --list --file jars\plugin-b.jar
jar --list --file jars\bad-plugin.jar

# Check entries matching binary names and resources of interest:
jar --list --file jars\bad-plugin.jar | Select-String 'demo/api/Codec.class'
jar --list --file jars\plugin-a.jar | Select-String 'META-INF/services/demo.api.Codec'
jar --list --file jars\plugin-b.jar | Select-String 'config/plugin.properties'

Get-FileHash jars\plugin-a.jar -Algorithm SHA256
Get-FileHash jars\plugin-b.jar -Algorithm SHA256
```

`Get-FileHash` confirms the exact bytes of an artifact in a build/deployment, though a hash **does not prove** compatibility or correct behavior. If CI builds a different JAR than the one tested, test results may not protect the actual release.

### 8.3. Dependency Graph: Necessary but Insufficient

Reference commands:

```powershell
# Maven: print resolved dependency tree.
mvn dependency:tree

# Gradle: inspect runtimeClasspath configuration.
./gradlew dependencies --configuration runtimeClasspath

# Gradle: investigate which module version wins on conflict.
./gradlew dependencyInsight --dependency example-library --configuration runtimeClasspath
```

These are **reference commands for Maven/Gradle projects**, not runnable in the plain-`javac` `duplicate-demo` layout. Configuration names may vary in real projects; separate build plugins may use runtime configurations different from the host's. In Maven, plugins can enforce dependency convergence/version upper bounds; in Gradle, use constraints/resolution strategies. Still, a dependency tree **does not prove** what a shadowed/merged JAR contains or which class a production classloader will pick.

### 8.4. Comparing Structure and Behavior

To prevent these failures in CI, maintain at least two test layers:

1. **Static packaging checks:** each artifact contains expected resources/descriptors, omits forbidden API copies, contains no unapproved duplicate classes, and obeys version rules.
2. **Runtime classloader integration:** construct loaders/layers like production, run `ServiceLoader`, assert subtyping, version behavior, and full resource lists.

Running only IDE unit tests puts host and plugins on a shared application classloader that fails to mirror child-first, parent-first, dynamic layers, file watchers, or separate JARs in production.

## 9. Combination Test Matrix Across Plugins

Do not test each plugin only in isolation. Collision bugs often appear when **combining multiple plugins** or changing load order.

| Case | Setup | Expected Outcome to Assert |
|---|---|---|
| **A-only** | Only JAR A, host API | Provider A uses v1 properly |
| **B-only** | Only JAR B, host API | Provider B uses v2 properly |
| **A+B, isolated loaders** | Separate loader per plugin, shared API from parent | Both A and B run and are assignable to host API |
| **A before B, combined loader** | Two URLs ordered A,B | Winning version is known; detect incompatible behavior |
| **B before A, combined loader** | Two URLs ordered B,A | Detect behavioral difference when order swaps |
| **Duplicate resource** | Both A and B have `config/plugin.properties` | Enumerate all sources/contents; never silently pick wrong copy |
| **Duplicate SPI descriptor** | Two descriptors with same service name | Providers match expected list without dropped registrations |
| **Duplicate host API packaged** | Plugin JAR accidentally includes `demo/api/Codec.class` | Static check fails immediately regardless of parent-first masking |
| **Child-first API duplication** | Plugin loader defines API itself | Runtime `Class` identity differs; contract test fails as expected |
| **Missing dependency** | Omit a library used by plugin | Test catches load/link failure with clear context |
| **Binary-incompatible dependency** | Compiled with new method, runtime uses old JAR | Test catches `LinkageError`/`NoSuchMethodError` on the call path |
| **JPMS layer/module path** | Provider resolved in named module/layer | Test uses/provides, readability, layer ancestry, split packages |

During execution, record **JDK version**, OS, JAR list/sha256, classpath/module path, TCCL, delegation policy, loader namespace, and layer topology. Without this metadata, "provider not found" bugs are often hard to reproduce on another machine.

## 10. Relationship to JPMS and ModuleLayer

### 10.1. Same Name, Different Module Is Not Classpath Duplication

JPMS establishes module readability, exports, and package ownership. Two distinct named modules in one layer can be constrained by package rules, especially when mapped to the same loader. Conflicts can cause layer resolution/definition to fail before any plugin code runs.

Never "fix" `ResolutionException` by dumping every module onto the classpath and assuming equivalence. Switching to the unnamed module alters provider discovery and access rules. Runtime tests must mirror **the actual deployment mode**.

### 10.2. Module Dependencies Differ from URLClassLoader Dependencies

On the module path, `module-info.java` declares `requires`, `exports`, `uses`, and `provides`. `ServiceLoader.load(layer, service)` finds providers in that layer and its ancestors, **not in unnamed modules** via that overload. `ServiceLoader.load(service, loader)` searches a different loader scope; thus resource/provider tests must use the exact overload production uses.

If a plugin moves from the classpath to the module path (or becomes an automatic module), re-run the suite: resolution, provider discovery, version conflicts, and packaging can all behave differently. Having `META-INF/services` in a JAR does not guarantee every `ServiceLoader` lookup mode will see it.

## 11. Logging and Diagnostics on Failure

### 11.1. Logging Classloader Identity and Class Origin

In diagnostic code:

```java
// Illustrative snippet within a scope that already has the service Class<?>.
Class<?> type = demo.api.Codec.class;
System.out.println("name=" + type.getName());
System.out.println("loader=" + type.getClassLoader());
System.out.println("module=" + type.getModule());

var pd = type.getProtectionDomain();
if (pd != null && pd.getCodeSource() != null) {
    System.out.println("source=" + pd.getCodeSource().getLocation());
}
```

`ClassLoader.toString()` strings and `CodeSource` URLs vary by JDK and path. Never assert them as fixed stdout; use them for investigation. For custom classloaders, attach a **logical ID** of the plugin/loader in logs rather than printing only random hashes.

### 11.2. Typical Failure Signatures

| Signature | Where to Check First |
|---|---|
| `ClassNotFoundException` | Binary name, JAR URL, parent loader, lookup path |
| `NoClassDefFoundError` | Missing dependent class or prior class-initialization error; inspect `cause` |
| `NoSuchMethodError` | Compiled API vs. actually loaded class version mismatch |
| `ClassCastException` | Two distinct type identities, duplicated loader/API |
| `ServiceConfigurationError` | Descriptor, subtyping, constructor/factory, provider failure |
| Provider "vanishes" after JAR merge | SPI descriptor overwritten or improperly merged |
| Plugin A's config appears in B | Duplicate resource path, wrong loader/resource priority |
| `ResolutionException` / `LayerInstantiationException` | Module graph, readability, dependencies, and package definitions |
| Works alone, fails together | Classpath conflict, loader policy, duplicate resources, static singletons/caches |

Separate **build graph bugs** from **artifact bugs** and **runtime loader bugs**. For instance, `ClassCastException` can arise from a duplicated API even when Maven's dependency graph shows zero version conflicts, because the API class was manually bundled into the plugin JAR.

## 12. Release Policies to Prevent Recurring Failures

**Single source of truth for contracts:** shared API/SPI artifacts should be released with managed versions and explicitly supplied by the host. Plugins should declare supported min/max API versions without re-packaging contract classes when runtime requires unified identity.

**Clear dependency namespaces:** decide which library classes are shared with the host and which are isolated per plugin. Selective child-first loading must **exclude shared API/SPI packages** and core platform namespaces; never apply a single blanket policy carelessly.

**Explicit resource policies:** classify each resource type by whether to pick one copy, merge, or reject duplicates. For `META-INF/services`, fat-JAR builds need tested transformers/mergers; for `config/plugin.properties`, prefer plugin-namespaced paths or transparent priority rules.

**Reproducible artifacts:** record hash/artifact ID, Java version, classpath/module path, and test **the final JAR** before deployment. If plugin JARs can be reloaded while the host runs, test unload/reload lifecycles too; old classloaders can remain pinned by threads, callbacks, or caches.

**Fail-fast on duplicate contracts:** static packaging scans should reject `demo/api/Codec.class` inside plugin artifacts when the host owns the contract. Runtime checks like `Codec.class.isAssignableFrom(providerType)` or `ServiceLoader` are the second line of defense, not an excuse to skip packaging checks.

## 13. Review Questions and Exercises

1. **Why do two JARs containing `demo.lib.Version` not always cause an error?** If two separate loaders define each copy, both can coexist. On one loader, one copy wins and may only surface via behavior/metadata differences or linkage errors.
2. **Why is `getResource` insufficient for testing resource collisions?** Because it returns only one URL; `getResources` reveals multiple copies and lets you inspect every copy's contents.
3. **When does a "duplicate API file" become a "duplicate API class identity"?** When different loaders each define the corresponding API class, not merely when two files exist on disk.
4. **Why can `ClassCastException` happen even when class and interface names are identical?** Because type identity depends on both the defining loader and the binary name, not the name alone.
5. **Why can classpath tests pass while JPMS production fails?** Because module resolution, access checks, layer/provider discovery, and package rules differ.
6. **Why is inspecting the dependency tree insufficient?** It does not always reflect fat/shaded JAR contents or JARs dynamically loaded by the host.
7. **If two `META-INF/services` files of the same name are merged, what should be asserted?** That the resulting descriptor retains all valid providers and `ServiceLoader` actually instantiates them under production topology.
8. **Can changing URL order alter behavior when class versions collide?** Yes in the example's `URLClassLoader` model; that is why both orderings should be tested.
9. **Should every plugin bundle the API JAR "just to be safe"?** No if the system requires the API to be supplied once by the host; duplicating it easily breaks under loader policy changes.

**Exercise A:** rename `Version.text()` in v2 to `Version.label()`, compile the plugin against v2, and run against v1. Observe `NoSuchMethodError` on the call path; record which loader defined `Version`.

**Exercise B:** move `config/plugin.properties` to a plugin-specific path `plugins/a/config.properties` and update readers; compare against allowing duplicate resource paths with `getResources`.

**Exercise C:** remove `demo/api/Codec.class` from the bad JAR and re-run the child-first loader. Explain why the loader must delegate `Codec` lookup to the host when the API copy in the JAR is absent, and predict how `bad.api.same`/`bad.assignable` change.

**Exercise D:** create a CI test running solely against final packaged JARs, printing a table: class/resource name, containing JARs, SHA-256 values, and expected loader. Inject a duplicate API to prove the test fails before release.

## 14. References

- Java SE 17 — `ClassLoader` (`loadClass`, `getResource`, `getResources`): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html
- Java SE 17 — `URLClassLoader`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html
- Java SE 17 — `ServiceLoader`, classpath and named-module providers: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html
- Java SE 17 — `Class` (`getName`, `getClassLoader`, `isAssignableFrom`): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html
- Java SE 17 — `ModuleLayer`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ModuleLayer.html
- Java Virtual Machine Specification 17 — Loading, Linking and Initializing: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html

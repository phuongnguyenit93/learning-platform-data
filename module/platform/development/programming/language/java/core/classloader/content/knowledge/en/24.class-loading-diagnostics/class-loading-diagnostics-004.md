# Listing Duplicate-Named Resources and Determining Selection Order

## 1. Why Does Correct Configuration Still Read the Wrong Data?

In a Java application with multiple JARs, files under the same resource path can exist simultaneously, for example `config/settings.properties`, `log4j2.xml`, `META-INF/services/com.example.Service`, or `sample/diagnostics/order.txt`. A host, a plugin, and two dependency versions may carry **different copies with the same resource name**.

If the code only calls:

~~~java
URL selected = loader.getResource("config/settings.properties");
~~~

then it receives **one URL** or `null`. This **does not mean only one file exists on the classpath**. The loader may have selected the parent's resource before the plugin's file.

To find out how many candidates there are, use:

~~~java
Enumeration<URL> candidates =
        loader.getResources("config/settings.properties");
while (candidates.hasMoreElements()) {
    System.out.println(candidates.nextElement());
}
~~~

**Distinguish four questions:**

1. `getResource(name)` — which URL is the **first selected** resource?
2. `getResources(name)` — what are **all the resources with the same name** visible to the loader, in enumeration order?
3. `findResource(name)` and `findResources(name)` — what does the loader find **within its own sources** without adding the default parent lookup step?
4. `getResourceAsStream(name)` — what are the actual bytes read from the **selected resource**?

This article belongs to the **Diagnostics** category and covers ClassLoader resource lookup logic, how to distinguish parent-first from child-local search, how to identify which JAR is winning, module/resource encapsulation limits, `ServiceLoader`, and strategies for handling duplicate resources. A Java 17+ example is compiled, packaged into JARs, and actually run with 12 lines of verified stdout.

## 2. Resource Path, URL, and Classpath Root

### 2.1. A Resource Name Is Not a Filesystem Path

Resource names use `/` and are interpreted relative to a classpath/resource root:

~~~text
sample/diagnostics/order.txt
META-INF/services/com.example.spi.Processor
com/example/defaults.json
~~~

The same name `sample/diagnostics/order.txt` can have different physical locations:

~~~text
file:/app/classes/sample/diagnostics/order.txt
jar:file:/app/lib/a.jar!/sample/diagnostics/order.txt
jar:file:/app/lib/b.jar!/sample/diagnostics/order.txt
~~~

The paths above only illustrate URLs. `jar:file:...!/` is the URL form pointing to an entry inside a JAR; the `!/` separator is not part of the logical resource name that a caller passes to `getResource`.

Resources can also be exposed through a custom loader, a nested-JAR-aware launcher, or a module runtime image, without necessarily having a regular file `Path`.

### 2.2. Same Name Does Not Mean Same Bytes

Two different URLs may contain two different configuration versions, or two copies with identical content. To know for sure, **read the bytes** or compute a checksum. Comparing URL strings alone is not enough to conclude that two streams are the same.

In a plugin system:

~~~text
Application ClassLoader
  sample/diagnostics/order.txt = HOST

Child URLClassLoader
  URL #1 a.jar
    sample/diagnostics/order.txt = JAR_A
  URL #2 b.jar
    sample/diagnostics/order.txt = JAR_B
~~~

Having three copies with the same name is not a JAR format error. The rules for **selecting one copy**, **reading all**, or **merging** belong to the API and framework consuming the resource.

### 2.3. Duplicate Resources Are Not Duplicate Class Definitions

Multiple JARs containing `config/app.properties` can be completely valid. However, if two JARs both contain `com/example/Foo.class`, the program also faces questions about class identity and which code source was actually defined.

`ClassLoader.getResources("com/example/Foo.class")` can be a diagnostic signal to find duplicate class files, but **it does not guarantee that the exact URL holds the bytes that created the running `Class<?>`**: loaders can transform bytecode, use memory buffers, class caches, or custom module lookups. When debugging classes, combine `clazz.getClassLoader()`, `clazz.getModule()`, and appropriate provenance.

## 3. APIs for Listing and Selecting Resources

### 3.1. `ClassLoader.getResource(String)`

~~~java
URL url = loader.getResource("sample/diagnostics/order.txt");
if (url == null) {
    System.out.println("not found");
} else {
    System.out.println(url);
}
~~~

This is an illustrative snippet using a `loader` variable inside a method. According to the Java SE 21 Javadoc, the default implementation searches **the parent loader first**; if the parent is `null`, it searches the path of the bootstrap/VM built-in loader; only after the parent fails to find it does it call `findResource` on the current loader.

Therefore, a resource in the parent can **shadow** a resource of the same name in the child when calling a single-selection API.

### 3.2. `ClassLoader.getResources(String)`

~~~java
Enumeration<URL> found = loader.getResources(
        "sample/diagnostics/order.txt");
while (found.hasMoreElements()) {
    URL candidate = found.nextElement();
    System.out.println(candidate);
}
~~~

This method declares `throws IOException`. **When no file is found**, it returns an **empty** `Enumeration<URL>`, not `null`.

The default implementation traverses **all URLs from the parent** first, then appends **all URLs from `findResources` on the current loader**. This is the main difference compared to `getResource`: you see the losing candidates in the selection as well.

The Javadoc recommends that custom loaders ensure `getResources`/`getResource` consistency so that the first element of the enumeration corresponds to the URL returned by `getResource`. When a loader overrides both methods with its own strategy, you **must verify** this rather than assuming it is a rule that applies to every custom loader.

### 3.3. `ClassLoader.resources(String)` — Stream Form Since Java 9

~~~java
try (java.util.stream.Stream<URL> stream =
        loader.resources("sample/diagnostics/order.txt")) {
    stream.forEach(System.out::println);
}
~~~

This is a Java 17 snippet inside a method; the default implementation creates a Stream from `getResources`. It is not `Files.walk` and does not automatically list all files on the classpath; it only searches for **the exact name passed**.

### 3.4. `ClassLoader.getResourceAsStream(String)`

~~~java
try (InputStream in =
        loader.getResourceAsStream("sample/diagnostics/order.txt")) {
    if (in == null) {
        System.out.println("not found");
    } else {
        System.out.println(in.readAllBytes().length);
    }
}
~~~

The snippet requires `java.io.InputStream` and IOException handling. This method reads **the single selected copy** following a search order equivalent to `getResource`, without listing duplicates. If you want to inspect the contents of **each copy**, iterate over `getResources` and open `URL.openStream()` inside a `try-with-resources` block.

### 3.5. `findResource` and `findResources`

These are protected hooks that subclasses such as `URLClassLoader` implement to search for resources in their **own** sources:

~~~java
final class InspectableLoader extends URLClassLoader {
    InspectableLoader(URL[] urls, ClassLoader parent) {
        super(urls, parent);
    }

    URL localFirst(String name) {
        return findResource(name);
    }

    Enumeration<URL> localAll(String name) throws IOException {
        return findResources(name);
    }
}
~~~

This is a **snippet class** and requires complete imports. It does not change the resource lookup policy: it only exposes the two hooks to compare against `getResource` and `getResources`.

**Important:** `findResources` does not mean "`getResources` without returning duplicates". It simply does not add the default method's parent lookup step. It can still return multiple URLs if the child has multiple URL roots containing the same name.

### 3.6. Summary Table

| API | Return Value | Default Search Order / Scope | Use When |
|---|---|---|---|
| `getResource(name)` | `URL` or `null` | Parent first, then current loader | Inspecting the selected copy |
| `getResources(name)` | `Enumeration<URL>` | Parent candidates, then local candidates | Listing duplicates |
| `resources(name)` | `Stream<URL>` | Backed by `getResources` | Stream processing |
| `getResourceAsStream(name)` | `InputStream` or `null` | Reads the copy selected by `getResource` | Inspecting consumed bytes |
| `findResource(name)` | Protected `URL`/`null` | Local search | Loader implementation/debugging |
| `findResources(name)` | Protected enumeration | Local search | Debugging child-only candidates |
| `SomeClass.class.getResource(name)` | `URL`/`null` | Relative/absolute + module context | Files colocated with a class |
| `ClassLoader.getSystemResource(name)` | `URL`/`null` | System/built-in path | System resources |

## 4. Which Order Wins in URLClassLoader?

### 4.1. Parent-First Cannot Be Overridden Just by Reordering Child URLs

Suppose:

~~~text
Parent loader:
  order.txt -> HOST

Child loader:
  URL #1: a.jar -> JAR_A
  URL #2: b.jar -> JAR_B
~~~

Result under the default policy:

~~~text
child.getResource(name)  -> HOST
child.getResources(name) -> HOST > JAR_A > JAR_B
child.findResource(name) -> JAR_A
child.findResources(name)-> JAR_A > JAR_B
~~~

If you change the child's URL order to B then A:

~~~text
child.getResource(name)  -> HOST
child.getResources(name) -> HOST > JAR_B > JAR_A
child.findResource(name) -> JAR_B
child.findResources(name)-> JAR_B > JAR_A
~~~

Reason: **the parent already won before the child was even queried** in `getResource`. Changing the URL order only takes effect when lookup reaches the child's local resources.

### 4.2. URL Order Within URLClassLoader Itself Is Contractual

According to the Java SE 21 `URLClassLoader` constructor, URLs are searched **in the order specified**, after searching the parent. In the `URL[] {jarA,jarB}` example, the child-local resource `JAR_A` comes before `JAR_B`; reversing the array reverses their positions.

However, do not assume that every framework classloader follows the same policy. OSGi systems, servlet/container loaders, plugin engines, or Spring Boot launchers may use custom delegation and protocols/packaging.

### 4.3. `parent=null` Does Not Mean "Privilege Isolation" or "No Java API"

A `URLClassLoader` with a `null` parent can still load Java platform classes via the bootstrap/VM built-in search. It simply **does not use the application parent** under that configuration. Do not treat a `null` parent as a security sandbox.

In the experiment, because the bootstrap loader does not contain the demo resource, this loader selects `JAR_A` directly, followed by `JAR_B`.

## 5. Hands-On Java 17+ Program with Verified Output

The example includes four text files, of which only three share the same name. All contents are short labels, which helps demonstrate the order without printing machine-dependent absolute URLs.

### 5.1. Directory Tree

~~~text
demo/
├── src/demo/host/ResourceOrderDemo.java
├── assets/
│   ├── a/sample/diagnostics/order.txt  (JAR_A)
│   └── b/sample/diagnostics/order.txt  (JAR_B)
└── build/
    ├── host/
    │   ├── demo/host/ResourceOrderDemo.class
    │   ├── demo/host/local.txt          (LOCAL)
    │   └── sample/diagnostics/order.txt (HOST)
    ├── a.jar
    └── b.jar
~~~

Resource name being tested: `sample/diagnostics/order.txt`. `local.txt` is only used to demonstrate the relative lookup rule of `Class.getResource`.

### 5.2. File `src/demo/host/ResourceOrderDemo.java`

~~~java
package demo.host;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Enumeration;
import java.util.List;

public class ResourceOrderDemo {
    static final String NAME = "sample/diagnostics/order.txt";

    static String label(URL url) throws IOException {
        if (url == null) return "NONE";
        try (InputStream input = url.openStream();
             BufferedReader reader = new BufferedReader(
                     new InputStreamReader(input, StandardCharsets.UTF_8))) {
            return reader.readLine();
        }
    }

    static String labels(Enumeration<URL> found) throws IOException {
        List<String> result = new ArrayList<>();
        while (found.hasMoreElements()) {
            result.add(label(found.nextElement()));
        }
        return String.join(">", result);
    }

    static final class InspectableLoader extends URLClassLoader {
        InspectableLoader(URL[] urls, ClassLoader parent) {
            super(urls, parent);
        }

        URL localFirst() {
            return findResource(NAME);
        }

        String localAll() throws IOException {
            return labels(findResources(NAME));
        }
    }

    public static void main(String[] args) throws Exception {
        ClassLoader parent = ResourceOrderDemo.class.getClassLoader();
        URL jarA = Path.of("build/a.jar").toUri().toURL();
        URL jarB = Path.of("build/b.jar").toUri().toURL();

        try (InspectableLoader ab = new InspectableLoader(
                     new URL[]{jarA, jarB}, parent);
             InspectableLoader ba = new InspectableLoader(
                     new URL[]{jarB, jarA}, parent);
             InspectableLoader independent = new InspectableLoader(
                     new URL[]{jarA, jarB}, null)) {

            System.out.println("parentFirst="
                    + label(ab.getResource(NAME)));
            System.out.println("allParentFirst="
                    + labels(ab.getResources(NAME)));
            System.out.println("childOnlyFirst="
                    + label(ab.localFirst()));
            System.out.println("childOnlyAll=" + ab.localAll());

            System.out.println("reversedStillParent="
                    + label(ba.getResource(NAME)));
            System.out.println("reversedAll="
                    + labels(ba.getResources(NAME)));

            System.out.println("noAppParentFirst="
                    + label(independent.getResource(NAME)));
            System.out.println("noAppParentAll="
                    + labels(independent.getResources(NAME)));

            System.out.println("absoluteClassResource="
                    + label(ResourceOrderDemo.class
                            .getResource("/" + NAME)));
            System.out.println("relativeClassResource="
                    + label(ResourceOrderDemo.class
                            .getResource("local.txt")));

            System.out.println("missingEnumerationEmpty="
                    + !ab.getResources(
                            "sample/diagnostics/absent.txt")
                             .hasMoreElements());

            try (InputStream stream = ab.getResourceAsStream(NAME)) {
                System.out.println("streamUsesParent="
                        + (stream != null
                           && "HOST".equals(new String(
                              stream.readAllBytes(),
                              StandardCharsets.UTF_8).trim())));
            }
        }
    }
}
~~~

### 5.3. Program Explanation

- `label(url)` opens the exact URL via `openStream`, reads the first line, and closes the stream.
- `labels(enumeration)` iterates through **all** resource candidates, not just the first resource.
- `InspectableLoader` only adds two wrappers to invoke `findResource`/`findResources`; it does not override the parent-first policy.
- `ab` receives URL A before B, with the host application loader as its parent.
- `ba` receives URL B before A, still with the host application loader as its parent.
- `independent` has a `null` parent; bootstrap search still exists, though it does not contain the demo resource.
- `Class.getResource("/" + NAME)` uses root-relative lookup; `getResource("local.txt")` uses package-relative lookup.
- A nonexistent name returns an empty enumeration.
- `getResourceAsStream` is compared directly against the `HOST` content.

We **do not use `getURLs()` to prove which URL actually wins**; `getURLs()` only reveals the local search path. The result of `getResource` and each URL from `getResources` are what show the selected/listed copies.

### 5.4. Linux/macOS: Create Resources, Package JARs, and Run

First save the Java file from section 5.2, then run the following inside the `demo` directory:

~~~sh
mkdir -p src/demo/host
mkdir -p build/host/sample/diagnostics
mkdir -p build/host/demo/host
mkdir -p assets/a/sample/diagnostics
mkdir -p assets/b/sample/diagnostics

printf 'HOST'  > build/host/sample/diagnostics/order.txt
printf 'LOCAL' > build/host/demo/host/local.txt
printf 'JAR_A' > assets/a/sample/diagnostics/order.txt
printf 'JAR_B' > assets/b/sample/diagnostics/order.txt

javac --release 17 -d build/host src/demo/host/ResourceOrderDemo.java
jar --create --file build/a.jar -C assets/a .
jar --create --file build/b.jar -C assets/b .
java -cp build/host demo.host.ResourceOrderDemo
~~~

**Note:** the application classpath only contains `build/host`, not `build/a.jar` or `build/b.jar`. The two JARs are managed by the child loaders and are only supplied via `URL[]`.

### 5.5. Windows PowerShell: Create UTF-8 Files Without BOM

~~~powershell
New-Item -ItemType Directory -Force src/demo/host | Out-Null
New-Item -ItemType Directory -Force build/host/sample/diagnostics | Out-Null
New-Item -ItemType Directory -Force build/host/demo/host | Out-Null
New-Item -ItemType Directory -Force assets/a/sample/diagnostics | Out-Null
New-Item -ItemType Directory -Force assets/b/sample/diagnostics | Out-Null

$enc = [System.Text.UTF8Encoding]::new($false)
[System.IO.File]::WriteAllText("build/host/sample/diagnostics/order.txt", "HOST", $enc)
[System.IO.File]::WriteAllText("build/host/demo/host/local.txt", "LOCAL", $enc)
[System.IO.File]::WriteAllText("assets/a/sample/diagnostics/order.txt", "JAR_A", $enc)
[System.IO.File]::WriteAllText("assets/b/sample/diagnostics/order.txt", "JAR_B", $enc)

javac --release 17 -d build/host src/demo/host/ResourceOrderDemo.java
jar --create --file build/a.jar -C assets/a .
jar --create --file build/b.jar -C assets/b .
java -cp build/host demo.host.ResourceOrderDemo
~~~

Using UTF-8 without BOM avoids having a BOM character in the text content alter the label. The Java program does not need a manifest file with `Main-Class`, because the entry point `demo.host.ResourceOrderDemo` is specified explicitly to `java -cp`.

### 5.6. Exact Verified Stdout

~~~text
parentFirst=HOST
allParentFirst=HOST>JAR_A>JAR_B
childOnlyFirst=JAR_A
childOnlyAll=JAR_A>JAR_B
reversedStillParent=HOST
reversedAll=HOST>JAR_B>JAR_A
noAppParentFirst=JAR_A
noAppParentAll=JAR_A>JAR_B
absoluteClassResource=HOST
relativeClassResource=LOCAL
missingEnumerationEmpty=true
streamUsesParent=true
~~~

This is the stdout of the actual Java program successfully compiled with `javac --release 17`; the test reads resources from the host directory and the two JARs, without relying on guessing the classpath order.

### 5.7. Breakdown of Each Result

| Output | Meaning |
|---|---|
| `parentFirst=HOST` | Parent-first `getResource` selects the application loader's copy |
| `allParentFirst=HOST>JAR_A>JAR_B` | `getResources` appends the child's copies after the parent's |
| `childOnlyFirst=JAR_A` | `findResource` selects A from the local URL list |
| `childOnlyAll=JAR_A>JAR_B` | `findResources` lists local candidates A then B |
| `reversedStillParent=HOST` | Reversing child URLs does not change the winning parent copy |
| `reversedAll=HOST>JAR_B>JAR_A` | Reversing child URLs changes the portion enumerated on the child |
| `noAppParentFirst=JAR_A` | A loader with a `null` parent does not query the application loader |
| `noAppParentAll=JAR_A>JAR_B` | The independent child sees the two JARs in URL order |
| `absoluteClassResource=HOST` | Class-relative API with a leading `/` selects the path from the root |
| `relativeClassResource=LOCAL` | Class-relative lookup prepends the `demo/host/` package |
| `missingEnumerationEmpty=true` | Not found produces an empty enumeration |
| `streamUsesParent=true` | `getResourceAsStream` reads the copy selected by parent-first lookup |

Conclusion from the example: **to know which copy wins, check `getResource`; to find all competing sources, use `getResources`**. Do not assume that reversing child URLs will override a resource in the parent.

## 6. `Class.getResource` and `ClassLoader.getResource` Differ on the Slash

A very common source of bugs is passing the same string to both APIs:

~~~java
Class<?> type = demo.host.ResourceOrderDemo.class;

URL absolute = type.getResource("/sample/diagnostics/order.txt");
URL relative = type.getResource("local.txt");

ClassLoader loader = type.getClassLoader();
URL loaderAbsolute = loader.getResource(
        "sample/diagnostics/order.txt");
~~~

This is a snippet inside a method, not a standalone file.

- `Class.getResource("/x/y")`: with a leading `/`, the class-level API interprets it as an absolute resource name from the root.
- `Class.getResource("local.txt")`: without a `/`, it is interpreted relative to the package of class `demo.host`, becoming `demo/host/local.txt`.
- `ClassLoader.getResource("x/y")`: the resource name is resolved from the root; it does **not** prepend a package and normally **does not take a leading slash**.
- `ClassLoader.getResource("/x/y")`: is not guaranteed to work like `Class.getResource("/x/y")`; avoid confusing the syntax.

When the application uses **named modules**, `Class.getResource` is also tied to the module context and its encapsulation rules, so not every case is equivalent to a loader-wide lookup.

## 7. Resources in JPMS Named Modules: Visibility Limits

### 7.1. A Loader-Wide Search Does Not Always See Every Resource in a Module

The Java SE 21 Javadoc for `ClassLoader.getResource` and `getResources` sets rules for **named modules**. Except for names ending in `.class`, a resource in a package of a named module is only exposed through loader-wide APIs if the package is **opened unconditionally** as required by the API.

This leads to the following possibilities:

- An entry exists in the modular JAR, yet `getResources` does not return a URL because the package is encapsulated.
- A package opened only to a specific target module does not mean a loader-wide API is allowed to expose the resource as an unconditional open.
- `Module.getResourceAsStream` or `SomeClass.class.getResource` has its own access context; consult the corresponding Javadoc.
- "Resource not found via the loader" may be an **encapsulation issue**, not simply a missing file.

### 7.2. Order Across Multiple Modules in the Same Loader May Be Unspecified

The Javadoc explicitly notes that when **multiple named modules are defined in the same ClassLoader** and they contain a resource with the same name, **the search order of the modules is unspecified and can be unpredictable**.

Therefore, do not generalize the `HOST>JAR_A>JAR_B` output of the `URLClassLoader` demo into a guarantee for every `ModuleLayer`.

If an application needs a file belonging to **a specific named module**, use a module-scoped access API or design a unique resource path; do not rely on unstable module enumeration order.

### 7.3. When Diagnosing Modules

Check:

1. Has the module been resolved into the runtime layer?
2. Which modules are defined by the class loader in use?
3. Does the resource reside in a package with the appropriate `opens` or `exports`? `exports` alone does not substitute for `opens` for resource encapsulation.
4. Is the caller using `Class.getResource`, `ClassLoader.getResources`, or `Module.getResourceAsStream`?
5. Do multiple named modules share the same resource path in the same loader?

Remember that `ModuleLayer` and ClassLoader have a mapping relationship, **not a simple linear classpath file list**.

## 8. Duplicate `META-INF/services` and Java ServiceLoader

Example:

~~~text
a.jar:
  META-INF/services/com.example.spi.Processor
    com.vendor.alpha.AlphaProcessor

b.jar:
  META-INF/services/com.example.spi.Processor
    com.vendor.beta.BetaProcessor
~~~

This is a content description, not Java code. Two JARs containing **the same resource name** is normal design for Java SPI.

`ServiceLoader` can read **multiple provider configuration files** corresponding to a service type and discover the declared provider classes. Therefore:

- Do not conclude that only the provider in the first resource will be used.
- Do not arbitrarily delete duplicate-named `META-INF/services` entries when packaging a fat/uber JAR.
- When shading multiple JARs, **merge provider descriptors** using the appropriate build tool or resource transformer.
- Watch out for service class identity: if the host and plugin have two runtime copies of the same interface defined by different loaders, the provider may report a subtype/configuration error.
- If multiple providers exist, the application should have a clear **provider selection policy**; do not treat discovery order as a priority that the framework does not guarantee.

In practice, some resource types must be **merged**, whereas the application's primary configuration should **use a distinct name** or be selected according to a well-founded policy. `getResources` is a discovery tool; how you handle duplicates depends on the resource's semantics.

## 9. Diagnostic Workflow in Real-World Projects

### 9.1. Print the Exact Candidates of the Loader Used at Runtime

~~~java
static void inspect(ClassLoader loader, String name)
        throws IOException {
    URL winner = loader.getResource(name);
    System.out.println("winner=" + winner);

    Enumeration<URL> all = loader.getResources(name);
    int count = 0;
    while (all.hasMoreElements()) {
        URL candidate = all.nextElement();
        System.out.println("candidate[" + count++ + "]=" + candidate);
    }
    System.out.println("count=" + count);
}
~~~

This is a **snippet method** and requires `URL`, `Enumeration`, and `IOException` imports. Call it with **the exact loader used by the failing code**, not necessarily the system ClassLoader.

Three commonly confused loaders:

~~~java
ClassLoader system = ClassLoader.getSystemClassLoader();
ClassLoader context = Thread.currentThread().getContextClassLoader();
ClassLoader defining = SomeType.class.getClassLoader();
~~~

The snippet requires `SomeType` to exist. The TCCL may be changed by the framework per worker or request; a resource lookup via `SomeType.class.getResource` does not automatically mean the TCCL is used. With `ServiceLoader`, the `load(service)` overload typically relies on the TCCL, whereas `load(service, loader)` uses the specified loader.

### 9.2. Read the Contents, Do Not Just Print the URL

~~~java
try (InputStream in = candidate.openStream()) {
    byte[] bytes = in.readAllBytes();
    System.out.println("resourceLength=" + bytes.length);
}
~~~

This snippet assumes a `candidate` URL and exception handling. For configuration files containing credentials, **do not log the entire contents**. If you want to determine whether two candidates have identical bytes, you can compute SHA-256 and compare hashes; do not treat the URL string as a checksum.

For large binary resources, prefer streaming hashing instead of `readAllBytes` to avoid unnecessary allocations.

### 9.3. Inspect the Deployment, Not Just the Build Dependency Graph

Factors that make results differ from the IDE:

- The actual `java -cp` or `java -jar` command, module path, and launcher script.
- The `Class-Path` manifest attribute, external JAR dependencies, and resource roots.
- Gradle/Maven runtime classpath differing from compile/test classpath.
- Wildcards such as `lib/*`: **do not rely on an unguaranteed expansion order**.
- Fat/shaded JARs merging or overwriting files; nested-JAR launchers having their own search semantics.
- Parent/child loader graphs in an application server or plugin container.
- Custom ClassLoader overriding `getResource` or `getResources`.
- In-memory cached configuration, classloader lifecycle, and TCCL on thread pools.
- Module encapsulation, package `opens`, and module layer mapping.

If the resource is only wrong after deployment, print **all candidate URLs directly inside the deployed process** and inspect the JARs containing the entries via:

~~~sh
jar --list --file path/to/app.jar
jar --list --file path/to/dependency.jar
~~~

These are illustrative commands; replace the paths with actual artifacts. The `jar --list` command inspects contents on disk; `getResources` reveals contents **visible to the loader in the running process**. These two sets may differ due to how the application is launched.

### 9.4. Recommended Investigation Order

1. Record the **exact logical resource name**, distinguishing root-slash vs. package-relative.
2. Identify the **loader used by the failing API**: defining, context, system, or a dedicated framework loader.
3. Call `getResource` to print the winning URL.
4. Call `getResources` to list candidates in exact order.
5. Compare the URLs against each candidate's contents, not just the JAR name.
6. Check the parent loader search path and the child's URL order.
7. Cross-check the runtime command, repackaging/shading, module path, and resource access.
8. Check whether the library or configuration framework merges all candidates or only takes one.
9. Fix the issue with a **dedicated resource namespace**, dependency cleanup, a transformer, or explicit URL selection — rather than arbitrarily tweaking order.
10. Retest on the actual release artifact and add a regression test to detect policy-violating duplicates.

### 9.5. Notes on Caching

An application may read a resource once at startup and cache the configuration object. When the file on disk changes, `getResources` may still point to the same URL while the application continues using the stale parsed state. A loader or JAR connection can also have its own caching and lifecycle; check the actual API and launcher configuration.

**Listing URLs does not mean a reload succeeded.** If the code or framework has cached the data, you need a reload mechanism following the framework's contract, or to restart/recreate the loader or process when appropriate.

## 10. Common Errors and Misconceptions

| Symptom | Possible Cause | Check / Resolution |
|---|---|---|
| `getResource` selects HOST copy instead of plugin | Parent-first | Print parent candidates; use a distinct resource name |
| `getResources` returns 3 URLs | Duplicate name in parent and child | Read the contents; do not delete blindly |
| Reordering JAR_A/JAR_B still leaves HOST as winner | Parent already won | Change policy/path, not just child URL order |
| `getResources` misses entry present in modular JAR | Named module encapsulation or unresolved module | Check module `opens`, layer, and API used |
| `Class.getResource("x")` returns null | Relative path gets package prepended | Use `"/x"` for root-absolute lookup |
| `ClassLoader.getResource("/x")` returns null | Leading slash does not match class-relative API behavior | Use `"x"` |
| Two `META-INF/services` with the same name | Multiple valid SPI providers | Merge descriptors / inspect providers |
| `ServiceLoader` reports `not a subtype` | Split API runtime identity across loaders | Share API from parent; inspect Class objects |
| `getResources` empty despite file existing in JAR | Loader cannot see JAR, wrong path, module access, or custom policy | Print loader URLs; inspect archive/module |
| Works in IDE, fails in container | Different classpath/launcher/framework | Print runtime URLs and actual command |
| File changed but config stays the same | Cached parsed config / JAR connection / old loader | Check lifecycle/reload |
| Multiple modules in same loader, order changes | Module search order is not guaranteed | Target a specific module; avoid index-based priority |
| Correct URL found, but content is unexpected | Different deployed artifact/version or duplicate byte content | Hash each candidate |
| `findResources` has fewer entries than `getResources` | Excludes parent | Intended by design |

**Misconceptions to remember:**

1. `getResource` returning a single URL does not prove only one resource exists.
2. `getResources` does not return `null` when a resource is absent; it returns an empty enumeration.
3. `getResourceAsStream` does not automatically merge multiple configuration copies.
4. Default parent-first behavior is not the same as child-first in some frameworks.
5. The child's first URL cannot beat the parent if the parent has already matched.
6. `findResources` does not automatically include the parent in the enumeration.
7. Having the same resource name does not guarantee the same content.
8. `Class.getResource` and `ClassLoader.getResource` do not share the same relative-name rules.
9. A path like `jar:file:...!/entry` is a URL, not the resource name to pass in.
10. A resource in a named module is not always exposed via loader-wide lookup.
11. Order across modules in the same loader is not generally guaranteed.
12. Multiple `META-INF/services` files can be intentional design.
13. `ClassLoader.getSystemClassLoader()` is not necessarily the loader searching for a plugin's resources.
14. Build dependency order does not necessarily match production URL order.
15. URLs containing secrets or credentials should not be written to public logs.
16. A container that changes the launcher can completely change resource order.
17. Having the right resource URL does not mean the framework has parsed and reloaded it.
18. `URLClassLoader.close()` affects lifecycle/resources, but does not automatically reload all configuration.

## 11. Self-Check Questions

1. What return types do `getResource` and `getResources` produce?
2. If the resource does not exist, how does each API respond?
3. Why is `parentFirst=HOST` when the child has both A and B?
4. Why is `allParentFirst=HOST>JAR_A>JAR_B`?
5. Why does the child's `findResources` not list HOST?
6. Which lines in the demo change when reversing the A/B URL order?
7. Does a `null` parent mean there is no Java built-in class loader anymore?
8. Does `getResourceAsStream` read all copies or a single copy?
9. What path does `Class.getResource("local.txt")` construct when the class is in package `demo.host`?
10. Should a name with a leading slash be used with the Class-level or ClassLoader-level API?
11. How do you verify whether two URLs have identical bytes?
12. Should you compare URL strings to verify integrity?
13. How does `ClassLoader.resources(name)` relate to `getResources`?
14. Why should you not rely on classpath wildcard ordering?
15. When are multiple `META-INF/services` files with the same name normal?
16. Does ServiceLoader necessarily read only the first descriptor?
17. How does a named module's `opens` relate to resource lookup?
18. Why can't the ordering from the URLClassLoader demo be generalized to every ModuleLayer?
19. Can the system class loader, TCCL, and defining loader differ?
20. In a container, which values should you log to determine which resource copy wins?
21. Does replacing a JAR on disk guarantee that parsed configuration in memory updates immediately?
22. If a framework merges multiple resources, is the first selection still the sole cause?
23. How do you write a method that prints all candidates without depending on the IDE?
24. When should you use a dedicated path namespace instead of changing URL order?
25. What can cause `getResources` to return empty even when the JAR contains the entry?

**Completion criteria:** create the three copies of `sample/diagnostics/order.txt`, run and explain all 12 lines of Java 17 output; list all duplicate-named URLs yourself, identify the winner and its cause based on parent/child ordering, and recognize the limitations of JPMS, SPI, and custom loaders.

## 12. Official Sources

- [Java SE 21 — ClassLoader](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassLoader.html): resource path names, `getResource`, `getResources`, `findResources`, `resources`.
- [Java SE 21 — URLClassLoader](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/URLClassLoader.html): parent search, order of URLs passed to the constructor, close.
- [Java SE 21 — Class.getResource](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html#getResource(java.lang.String)): relative/absolute names and module context.
- [Java SE 21 — Module.getResourceAsStream](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Module.html#getResourceAsStream(java.lang.String)): module resource encapsulation.
- [Java SE 21 — ServiceLoader](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/ServiceLoader.html): service provider files and discovery.
- [Java SE 21 — Java launcher](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html): classpath and module path when running an application.

**Conclusion:** `getResource` only shows **the selected copy**, whereas `getResources` lets you see **all candidates and the loader's actual order**. You must observe inside the running JVM, with the exact loader, and inspect the byte source of each URL when needed. Do not infer order from filenames or dependency declarations, or assume every loader or JPMS module searches by the same rules.

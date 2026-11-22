# Declaring Providers Using META-INF/services on the Classpath in Java

In Java, a library can publish a **service contract** as an interface/abstract class, while an application or another JAR supplies **provider implementations** that the library does not know at compile time. The **Service Provider Interface (SPI)** mechanism combined with `java.util.ServiceLoader` solves this problem by reading a **text configuration file with an exact name**:

```text
META-INF/services/<fully.qualified.ServiceInterface>
```

For example, the service interface `api.Greeting` can be implemented by `provider.VietnameseGreeting`. The `META-INF/services/api.Greeting` file resides **from the root of a classpath entry or JAR**, containing a single line `provider.VietnameseGreeting`. When application code iterates over `ServiceLoader.load(Greeting.class)` with an appropriate loader, the JVM/ServiceLoader discovers the provider, verifies that it actually implements the shared interface, and instantiates it when needed.

This article belongs to the **Service Loading** group of Java core – classloader. Focus areas: how to declare SPI on the **classpath/unnamed module**, how to determine the correct `META-INF/services` name and location, the `ServiceLoader` and class loader mechanism, a runnable Java 17+ program from a JAR, metadata/constructor/namespace errors, packaging multiple providers, differences from `provides ... with ...` in JPMS, along with a diagnostic workflow.

## 1. Service, provider, and discovery are three distinct roles

We separate the system into three components:

1. **Service contract:** an interface/abstract class that provides a stable API. For example, `api.Greeting` declares `String message()`.
2. **Provider:** a concrete class that fulfills the contract, for example `provider.VietnameseGreeting`. The provider can reside in a JAR added by the application at deployment time rather than being included in the API JAR.
3. **Discovery/consumer:** code that calls `ServiceLoader` to find registered providers, without hard-coding `new VietnameseGreeting()` in the base library.

Diagram:

```text
host-classes/                   plugins/greeting-provider.jar
  api/Greeting.class               provider/VietnameseGreeting.class
  app/Main.class                   META-INF/services/api.Greeting
           |                                     |
           | ServiceLoader.load(Greeting.class)  |
           +-------------------------------------+
                               |
                               v
               ServiceLoader reads service descriptor
                               |
                               v
                     provider.VietnameseGreeting
                               |
                               v
                      implements api.Greeting
                               |
                               v
                     application calls message()
```

**Architectural benefit:** the library/framework depends on the **interface** rather than depending on a concrete implementation. Vendors can add plugins via a properly packaged JAR without forcing the consumer to modify source code to import each provider class.

This mechanism appears across many platforms: JDBC driver discovery, providers for parsers/transformers, logging, serialization, and plugin architectures — however, each framework also has its own policies, so you must not assume that every framework uses `ServiceLoader`.

## 2. Required structure of the META-INF/services file

Given the service interface:

```java
package api;

public interface Greeting {
    String message();
}
```

the service configuration file must reside at the path **relative to the root of the classpath/JAR**:

```text
META-INF/services/api.Greeting
```

Pay attention to every character:

- The directory must be spelled **`META-INF`** (uppercase), followed by **`services`** (lowercase).
- The file name is the **fully qualified binary name of the service**: `api.Greeting`, **not** the provider name, and with no `.txt`/`.properties` extension.
- The content is the **fully qualified binary name of each provider**, one provider per line.
- Class names use dots `.` for packages; do not write the path `provider/VietnameseGreeting.class`.
- The file must be decoded in **UTF-8** per the `ServiceLoader` contract.
- Blank lines and comments starting with `#` are permitted; the portion from the `#` character to the end of the line is a comment; surrounding whitespace is ignored.
- Provider class names must be valid and must not contain spaces/tabs inside the binary name.
- A line contains no `new` syntax, parentheses, equals signs, or method names; only the **provider class name**.

Sample file:

```text
# Providers for api.Greeting
provider.VietnameseGreeting
provider.EnglishGreeting # enabled by default
```

The snippet above assumes **both classes have been compiled, packaged, and satisfy the SPI contract**. If only `VietnameseGreeting.class` exists, declare **a single line** `provider.VietnameseGreeting`. Do not copy the two-line example into an artifact that only has one implementation: `ServiceLoader` may throw a `ServiceConfigurationError` when iterating to the missing provider.

### Service name differs from provider name

Suppose you have:

- Service: `com.acme.spi.Codec`.
- Implementation: `com.vendor.FastCodec`.

The file name must be `META-INF/services/com.acme.spi.Codec`, and the content must include `com.vendor.FastCodec`. Swapping the two names is a common mistake that prevents ServiceLoader from finding the provider or causes it to report a misconfiguration.

### Nested service or provider

If the service is a nested/member interface, for example `com.acme.Api$Extension`, the binary name in the descriptor uses the `$` character:

```text
META-INF/services/com.acme.Api$Extension
```

Similarly, a nested member type provider may require a binary name containing `$`. Only use a provider class that satisfies the instantiation/access rules; a public static member class with a public no-arg constructor can satisfy them, whereas an inner class requiring an enclosing instance is generally unsuitable for traditional classpath-style providers.

## 3. How does ServiceLoader find providers on the classpath?

In the common classpath/unnamed module scenario:

1. The consumer calls `ServiceLoader.load(Greeting.class)` or an overload that accepts an explicit `ClassLoader`.
2. `ServiceLoader` selects the **loader used for discovery** according to the overload's contract.
3. When **iterating** over the service loader begins, the runtime searches for resources named `META-INF/services/api.Greeting` that are visible to the selected loader.
4. The service configuration files are read, provider names are parsed, and provider classes are determined.
5. Providers are verified, for example **whether each is a subtype of the `api.Greeting` used by the consumer**, and whether its constructor is valid.
6. `ServiceLoader` instantiates the provider **when requested by iteration/Provider.get**, after which the consumer calls the service API.
7. Already instantiated/discovered providers may be cached in **the corresponding `ServiceLoader` object**; `reload()` resets that cache per the contract.

Model:

```text
ServiceLoader.load(service)
          |
          | only creates the service loader, does not instantiate all yet
          v
Consumer starts for (Service s : loader)
          |
          v
ClassLoader.getResources("META-INF/services/<service-binary-name>")
          |
          v
Read UTF-8 resource, parse provider names
          |
          v
Load provider class -> check subtype/constructor
          |
          v
Instantiate provider on iterator.next()/Provider.get()
          |
          v
consumer calls method of the shared interface
```

The diagram is a generalized understanding of the classpath provider lookup path; it does not detail every optimization, module provider, or internal caching approach of each JDK. **Key contract:** discovery/instantiation is primarily **lazy**, so configuration errors may only surface **when actually iterating** rather than immediately at the `ServiceLoader.load(...)` call.

### Provider class rules on the classpath

For a provider residing in the **unnamed module/classpath**, the standard approach is:

- The provider is a **public class**, non-abstract, and instantiable.
- The provider **implements/extends** the requested service type, directly or indirectly.
- The provider has a **public no-argument constructor** used to create instances.
- The constructor may execute business logic, so side effects must be considered.
- Dependencies required by the provider must also be present on the appropriate loader/classpath.

`ServiceLoader` has a provider factory form via a **public static `provider()` method** for certain **explicit named module providers**. **Do not use it as a default replacement for the public no-arg constructor of a provider in the unnamed module on the classpath**.

## 4. Complete Java 17+ example: Provider in a separate JAR from the application

We create a host containing the API/consumer and a JAR containing the provider and descriptor. This can be run entirely with JDK 17+ without requiring a framework.

### 4.1 Directory structure

```text
spi-demo/
├── src/
│   ├── api/
│   │   └── Greeting.java
│   └── app/
│       └── Main.java
├── provider-src/
│   └── provider/
│       └── VietnameseGreeting.java
├── host-classes/                         # host class output
├── provider-classes/
│   ├── provider/
│   │   └── VietnameseGreeting.class       # after compilation
│   └── META-INF/
│       └── services/
│           └── api.Greeting               # text file, NO .txt
└── plugins/
    └── greeting-provider.jar              # after the jar step
```

Create the `host-classes`, `provider-classes/META-INF/services`, and `plugins` directories before running the compilation commands. If using an IDE/build tool, you can let it create the corresponding output directories.

### 4.2 Service contract

File `src/api/Greeting.java`:

```java
package api;

public interface Greeting {
    String message();
}
```

This is the shared interface. The consumer and provider **must resolve to the exact same runtime `api.Greeting` class identity**; in this example, both use the API defined by the application/system loader.

### 4.3 Consumer in the host

File `src/app/Main.java`:

```java
package app;

import api.Greeting;
import java.util.ServiceLoader;

public class Main {
    public static void main(String[] args) {
        System.out.println("before load");

        ServiceLoader<Greeting> services =
                ServiceLoader.load(Greeting.class);

        System.out.println("after load");

        int count = 0;
        for (Greeting g : services) {
            System.out.println(g.getClass().getName()
                    + ": " + g.message());
            count++;
        }

        System.out.println("providers=" + count);
    }
}
```

The consumer **does not import `provider.VietnameseGreeting`**. It only knows the interface and loads providers via ServiceLoader. In a typical command-line program, the main thread has a TCCL matching the application/system loader, so `ServiceLoader.load(Greeting.class)` sees the provider JAR on the classpath.

### 4.4 Provider implementation

File `provider-src/provider/VietnameseGreeting.java`:

```java
package provider;

import api.Greeting;

public class VietnameseGreeting implements Greeting {
    public VietnameseGreeting() {
        System.out.println("provider constructor");
    }

    @Override
    public String message() {
        return "Xin chao!";
    }
}
```

Both the provider class and constructor are **public**. The `provider constructor` line helps prove that calling `ServiceLoader.load` does not immediately instantiate the provider; the constructor only prints when the consumer starts iteration.

### 4.5 Provider declaration file

File `provider-classes/META-INF/services/api.Greeting` (UTF-8, **single-line content only**):

```text
provider.VietnameseGreeting
```

Note: this is a file inside the **provider's** output, not a Java file; `javac` **does not automatically generate the descriptor** and does not automatically copy resources either. It must be added manually, via Gradle/Maven resources processing, or through a JAR packaging tool.

### 4.6 Compiling the host, provider, and packaging the JAR

Run from the `spi-demo` directory:

```bash
javac --release 17 -d host-classes src/api/Greeting.java src/app/Main.java
javac --release 17 -cp host-classes -d provider-classes provider-src/provider/VietnameseGreeting.java
jar --create --file plugins/greeting-provider.jar -C provider-classes .
```

Explanation:

1. `javac -d host-classes` creates `api/Greeting.class` and `app/Main.class` under the host root.
2. `javac -cp host-classes` allows the provider to compile because it implements `api.Greeting` from the host.
3. `-d provider-classes` outputs `provider/VietnameseGreeting.class` into a separate output.
4. `jar -C provider-classes .` adds **all contents from the provider-classes root** into the JAR, including `META-INF/services/api.Greeting`. This is the key point; it must not be packaged as `provider-classes/META-INF/services/...` inside the JAR.

Inspect the JAR:

```bash
jar --list --file plugins/greeting-provider.jar
```

Besides the manifest/directories, it must contain at least:

```text
provider/VietnameseGreeting.class
META-INF/services/api.Greeting
```

### 4.7 Running with the provider JAR

**Windows (PowerShell/CMD):**

```bash
java -cp "host-classes;plugins/greeting-provider.jar" app.Main
```

**Linux/macOS:**

```bash
java -cp "host-classes:plugins/greeting-provider.jar" app.Main
```

Stdout verified when compiled with `javac --release 17` and executed with Java:

```text
before load
after load
provider constructor
provider.VietnameseGreeting: Xin chao!
providers=1
```

Why does the order matter?

- `before load` prints **before** creating the `ServiceLoader`.
- `after load` appears **before the constructor**; proving that `ServiceLoader.load` does not immediately instantiate the provider on its own.
- `provider constructor` only appears when the `for` loop starts receiving the provider.
- `provider.VietnameseGreeting: Xin chao!` indicates that the right class was discovered and the interface API was called successfully.
- `providers=1` shows that in the example's classpath there is only one valid provider.

### 4.8 Trying with the provider removed from the classpath

No need to edit or delete files. Re-run **with only the host**:

```bash
java -cp host-classes app.Main
```

Verified stdout:

```text
before load
after load
providers=0
```

**`ServiceLoader.load` does not report an error merely because no provider is present.** It returns a ServiceLoader that yields no elements when iterated. That is the correct behavior and differs from a descriptor containing a wrong/broken provider name, which can throw a `ServiceConfigurationError`.

If `plugins/greeting-provider.jar` is placed on the classpath **without a descriptor**, the `provider.VietnameseGreeting` class can still exist and be invoked via reflection, yet **ServiceLoader does not automatically scan the entire JAR to guess which class implements `Greeting`**. Declaring the provider is an indispensable step in the classpath SPI mechanism.

## 5. Why does placing META-INF/services in the wrong root fail?

The classpath is a collection of **roots**. For a JAR, the root is the top level inside the archive; for a directory, the root is the folder added to `-cp`.

**Correct for a directory:**

```text
provider-classes/
├── provider/VietnameseGreeting.class
└── META-INF/services/api.Greeting
```

When running:

```bash
java -cp "host-classes;provider-classes" app.Main
```

(Windows; on Linux/macOS, change `;` to `:`.)

**Correct for a JAR:**

```text
greeting-provider.jar
├── provider/VietnameseGreeting.class
└── META-INF/services/api.Greeting
```

**Incorrect when accidentally adding an extra directory level:**

```text
greeting-provider.jar
└── provider-classes/
    ├── provider/VietnameseGreeting.class
    └── META-INF/services/api.Greeting
```

If an artifact like the incorrect case is used as a classpath JAR, the actual resource is `provider-classes/META-INF/services/api.Greeting` rather than `META-INF/services/api.Greeting` at the root, so ServiceLoader cannot find the standard descriptor.

Another mistake is when the actual file is `api.Greeting.txt` because the operating system hides the `.txt` extension; `ServiceLoader` only looks for the name **`api.Greeting` verbatim**.

**Diagnostic rule:** before debugging Java code, run `jar --list --file ...` and verify that the descriptor path is at the root, then verify that `provider/...class` and all dependencies are packaged properly.

## 6. Which class loader does ServiceLoader use to find the descriptor?

This is a topic directly tied to **classloaders**:

```java
ServiceLoader<Greeting> services =
        ServiceLoader.load(Greeting.class);
```

According to the Java SE 17 contract, the `load(Class<S>)` overload uses the **thread context class loader (TCCL)**:

```java
ClassLoader tccl =
        Thread.currentThread().getContextClassLoader();

ServiceLoader<Greeting> services =
        ServiceLoader.load(Greeting.class, tccl);
```

The snippet above is **illustrative code**, assuming `Greeting` already exists. Both approaches are equivalent in terms of loader selection at the time the loader is created.

A loader can be selected explicitly:

```java
ClassLoader pluginLoader = /* plugin loader already created */;

ServiceLoader<Greeting> services =
        ServiceLoader.load(Greeting.class, pluginLoader);
```

This is **illustrative code**; an actual value must be declared for `pluginLoader`. This is especially useful when the provider JAR is managed by a child `URLClassLoader`, while the `Greeting` interface resides in the parent loader.

### Common visibility graph

```text
Application/System loader
    ├── api.Greeting
    └── app.Main
          ^
          | parent-first delegation
Plugin URLClassLoader
    ├── provider.VietnameseGreeting
    └── META-INF/services/api.Greeting
```

If the consumer is defined by the parent loader, it cannot automatically see resources/classes located only in the child loader. However, if you use:

```java
ServiceLoader.load(Greeting.class, pluginLoader)
```

then discovery is performed using the plugin loader, which can find the child's descriptor and provider class. The plugin loader needs to delegate **api.Greeting** to the parent so that the provider and consumer use **the same interface runtime type**.

**Do not confuse TCCL with `Class.forName(String)`.** Calling `Class.forName("provider.VietnameseGreeting")` by default uses the **defining loader of the class containing the call site**, and does not automatically choose the TCCL. Therefore, changing the TCCL may allow `ServiceLoader.load` to discover a provider, but it will not necessarily enable a helper in the parent calling `Class.forName(String)` to find the provider class.

### When is it necessary to set the TCCL?

A framework/app server can set a dedicated context loader for the thread executing service discovery:

```java
Thread thread = Thread.currentThread();
ClassLoader previous = thread.getContextClassLoader();

try {
    thread.setContextClassLoader(pluginLoader);
    for (Greeting g : ServiceLoader.load(Greeting.class)) {
        System.out.println(g.message());
    }
} finally {
    thread.setContextClassLoader(previous);
}
```

This is an **illustrative snippet**, assuming `pluginLoader` and `Greeting` exist. The `try/finally` block is critically required when using a thread pool: if plugin A's TCCL is left on a worker thread, request B may discover the wrong provider or keep plugin loader A alive beyond its lifetime.

**Not every API reads the TCCL.** Only use or set the TCCL when the API's contract actually uses it; when a specific loader is available, the `ServiceLoader.load(service, loader)` overload is clearer and easier to control.

## 7. The lazy and caching mechanism of ServiceLoader

In Java 17:

```java
ServiceLoader<Greeting> loader =
        ServiceLoader.load(Greeting.class);
```

this line mainly sets up the discovery object. When iterating:

```java
for (Greeting provider : loader) {
    System.out.println(provider.message());
}
```

`ServiceLoader` discovers and instantiates providers on demand. Some details:

- `iterator()` is **lazy**: there is no need to instantiate every provider up front.
- `iterator.hasNext()` may need to locate/read metadata or load a provider class to know whether another element remains; do not treat it as a completely side-effect-free check.
- `iterator.next()` returns the provider instance and may invoke its constructor; exceptions may only appear here.
- `stream()` returns `Stream<ServiceLoader.Provider<S>>`. `Provider.type()` indicates the provider class; only `Provider.get()` requests an instance (according to the corresponding contract).
- A `ServiceLoader` can **cache** already instantiated providers; subsequent iterations over the same object typically see the cached instances.
- `reload()` clears the cache so subsequent iterations rediscover providers according to the appropriate loader/source; **it does not reload already defined bytecode or update JARs already held by a class loader in an old namespace**.
- `ServiceLoader` is not guaranteed to be **thread-safe** when the same object is shared across multiple threads. Synchronization or creating a separate service loader per scope is needed.

Illustrative code example:

```java
ServiceLoader<Greeting> services =
        ServiceLoader.load(Greeting.class);
for (Greeting g : services) {
    System.out.println(g.getClass().getName());
}
services.reload();
```

This is an **illustrative snippet**, not a complete program. Calling `reload()` is meaningful when the discovery state changes in a way the loader can actually see; it does not “force” a closed `URLClassLoader` to find a new JAR.

### There can be 0, 1, or multiple providers

The `ServiceLoader` contract does not enforce having only a single implementation. If multiple JARs on the classpath contain the same service descriptor, `ServiceLoader` can read multiple configuration resources and return multiple providers. The application must decide the policy: use all of them, pick one based on its own configuration/priority, or report an error if not unique.

Do not assume the order of providers across JARs is a stable business contract. Resource/classpath lookup order can depend on the launcher, build tool, loader policy, and how artifacts are packaged. If priority matters, the application should have explicit provider selection metadata.

## 8. Declaring multiple providers

Suppose there are two actual classes:

- `provider.VietnameseGreeting`
- `provider.EnglishGreeting`

A single descriptor can contain:

```text
# Greeting implementations
provider.VietnameseGreeting
provider.EnglishGreeting
```

Each provider must be a valid, public class that implements `api.Greeting` and has a public zero-argument constructor per the classpath SPI rules.

### Multiple JARs providing the same service

```text
providers-a.jar:
    META-INF/services/api.Greeting
      -> provider.VietnameseGreeting

providers-b.jar:
    META-INF/services/api.Greeting
      -> other.EnglishGreeting
```

If both JARs are on the appropriate classpath, `ServiceLoader` can see both. If **the same provider class name** is repeated multiple times within the same configuration file or across multiple configuration files, ServiceLoader ignores **duplicate provider names** per the specification.

However, a **duplicate binary class name** across two JARs is not a “duplicate descriptor” error: the classpath loader may pick one class definition according to lookup order. When there is a version conflict, the same name `provider.FastCodec` with different bytecode can cause `ServiceLoader` to run the wrong version or encounter a linkage error.

### When creating a fat/uber JAR

Maven Shade, Gradle Shadow, or another packaging tool may **merge multiple provider JARs into a single JAR**. If the tool only copies one `META-INF/services/api.Greeting` file and overwrites the other, **the providers lose their declarations** even though the class files are still retained.

You must use a **merge/transform service descriptor files** feature rather than merely copying class files. If relocating package/class names, you must update **the contents of service descriptors and the service descriptor file names** to match the new binary names.

The final output should be verified using `jar --list` and by inspecting the **contents** of the `META-INF/services/...` file inside the artifact, not just checking the class files. A fat JAR containing multiple provider classes whose descriptor retains only a single line will register only one provider on the classpath SPI path.

## 9. Common errors and frequent error messages

| Symptom | Common cause | Check |
| --- | --- | --- |
| `ServiceLoader` iterates **0 providers** | Missing descriptor in classpath/JAR; wrong resource path; loader cannot see provider JAR | `jar --list`, `getResources`, classpath/TCCL |
| `ServiceConfigurationError: Provider ... not found` | Descriptor lists binary name but class is missing from loader/dependencies | Class name, package, JAR entries, loader |
| `ServiceConfigurationError: ... not a subtype` | Provider does not implement **the exact runtime service interface** or two copies of the interface are defined by two loaders | `isAssignableFrom`, `getClassLoader()` |
| `ServiceConfigurationError: Unable to get public no-arg constructor` | Classpath provider lacks a public no-argument constructor or class cannot be instantiated | Visibility, constructors, abstract class |
| `ServiceConfigurationError` when creating provider | Constructor throws an exception, initialization/linking error, or missing dependency | Stack trace, cause, runtime classpath |
| One provider appears while another does not | Descriptor retains only one entry due to fat JAR merger, or provider fails when iterated | Full contents of `META-INF/services` |
| Works in IDE but not with `java -cp` | IDE added the resource root / runtime JAR, whereas the script did not | Compare classpath, build output roots |
| Provider works with `-cp` but not with `--module-path` | Semantics shifted to named/automatic modules, `uses`/`provides`, resolution, and module layers | Artifact placement and module graph |
| New provider does not appear after hot deploy | Old ClassLoader/old cached ServiceLoader cannot see the new artifact | New loader, `reload()` only when new source is visible, plugin lifecycle |
| `ClassCastException` between API and provider | Two classloaders define duplicate copies of the same-named interface | Shared API parent loader and class identity |

Important: `ServiceConfigurationError` is an **`Error`**, not a checked `Exception` like `ClassNotFoundException`. Provider discovery errors can be thrown from `iterator.hasNext()`, `next()`, or a stream operation. Do not wrap all `ServiceLoader` logic in `catch (ClassNotFoundException)` assuming it will catch every SPI error.

Also do not rely on the exact error message format to determine the root cause; different JDK/module/classloader configurations can produce different messages. Always inspect the **cause** and the actual lookup path.

## 10. Diagnosing whether the descriptor is visible

In a classpath application, you can check the resource name **directly via the loader**:

```java
ClassLoader context =
        Thread.currentThread().getContextClassLoader();

java.util.Enumeration<java.net.URL> descriptors =
        context.getResources("META-INF/services/api.Greeting");

while (descriptors.hasMoreElements()) {
    System.out.println(descriptors.nextElement());
}
```

This is an **illustrative snippet** placed inside a method handling `java.io.IOException`, assuming `context` is non-null. The URL may be `file:/...` or `jar:file:/...!/META-INF/services/api.Greeting`. If there are no results, check the TCCL, classpath, and JAR packaging.

Notes:

- `ClassLoader.getResources(name)` searches for the **resource**; it does not guarantee that the provider class was compiled properly or that its constructor works.
- With Java 9+ named modules, resource encapsulation/exports/opens and lookup rules may differ from the standard classpath path.
- When the context loader is `null`, an alternative loader must be selected **according to the API contract and architecture** before invoking methods on a null reference; `ServiceLoader.load(service)` handles its own loader semantics.
- Finding the descriptor is only the **first step**; you must iterate over `ServiceLoader` to verify the actual provider class.

If you want to debug class identity:

```java
Class<?> providerClass =
        Class.forName("provider.VietnameseGreeting",
                      false, pluginLoader);

System.out.println(Greeting.class.isAssignableFrom(providerClass));
System.out.println(Greeting.class.getClassLoader());
System.out.println(providerClass.getClassLoader());
```

This is **illustrative code**, assuming `Greeting` and `pluginLoader` are already available and the method handles `ClassNotFoundException`. If `isAssignableFrom` returns `false` even though the provider source has `implements Greeting`, suspect that the plugin redefined a separate copy of `api.Greeting` different from the host's.

### A concise debugging workflow

1. **Verify the service binary name.** `Greeting.class.getName()` must be exactly `api.Greeting`, not confused with the provider name.
2. **Verify the descriptor path.** Inside the JAR there must be exactly `META-INF/services/api.Greeting` at the root.
3. **Verify the descriptor contents.** One valid provider binary name per line, UTF-8, with no `.class` suffix or slashes.
4. **Verify the provider bytecode.** `provider/VietnameseGreeting.class` must reside inside the JAR or a classpath root visible to the loader.
5. **Verify visibility/constructor.** Public, concrete class, public no-arg constructor, valid service subtype.
6. **Verify the runtime loader.** `ServiceLoader.load(service)` uses the TCCL; when the plugin is in a child loader, pass the explicit loader.
7. **Verify runtime dependencies.** The provider class may load, yet initialization fails because another library is missing or a static initializer fails.
8. **Verify fat JAR packaging.** Was the service descriptor overwritten by merging/shading?
9. **Verify JPMS mode.** Is the artifact on the classpath/unnamed or module path/automatic/explicit? Provider declaration methods differ.
10. **Try a minimal program.** Run with `-cp` containing the interface, provider JAR, and descriptor to isolate framework errors from SPI metadata errors.

## 11. Distinguishing classpath SPI from JPMS provider declarations

On the **classpath/unnamed module**, providers are typically registered using the file:

```text
META-INF/services/api.Greeting
```

and `ServiceLoader` reads the corresponding resource.

With **explicit named modules** starting in Java 9, service consumption/provider registration is typically described directly in `module-info.java`:

```java
module m.consumer {
    requires m.api;
    uses api.Greeting;
}
```

```java
module m.provider {
    requires m.api;
    provides api.Greeting with provider.VietnameseGreeting;
}
```

These are **two separate illustrative `module-info.java` files**; do not combine two `module` declarations into one file. Module `m.api` must expose the appropriate API package. With a named module, `uses` is generally required for code that directly invokes `ServiceLoader` for the service; `provides ... with ...` is the provider declaration in the module descriptor. A provider in an explicit named module may use a public constructor or a **provider method** depending on API requirements and context.

An **automatic module** is a named module derived from a non-modular JAR on the module path. The `META-INF/services` service configuration files in this JAR can be used by the module finder to generate the appropriate `provides` declarations; automatic modules also have their own readability/exports rules. Do not say that an automatic module is identical to a classpath unnamed module, even if the original JAR content is legacy.

### Brief comparison

| Criterion | Classpath/unnamed module | Explicit named module |
| --- | --- | --- |
| Provider registration | `META-INF/services/<service>` | `provides Service with Provider;` |
| Consumer declares service usage | No `module-info` | `uses Service;` |
| Provider constructor | Public zero-arg constructor per classpath provider form | Also has provider factory method form per the contract |
| Class lookup | Via classpath loader and delegation | Via module resolution, module-to-loader mapping, and service discovery |
| TCCL | `ServiceLoader.load(Class)` uses TCCL | API overloads also have module/service resolution semantics; select the appropriate module/layer |
| Packaging | JAR/classpath root must contain descriptor file | Modular JAR contains `module-info.class`, `provides` metadata |

Do not simultaneously place **duplicate copies of the class** for the same provider on both the classpath and the module path and expect only a single runtime type. The specific loading path, module graph, and class loader can cause the namespace/identity to differ from what you expect.

## 12. ServiceLoader in plugins with dedicated class loaders

Plugin frameworks typically have the service interface defined by the host and the provider defined by the plugin loader:

```text
Host/system loader
  ├── api.Greeting
  └── host.PluginManager
           ^
           |
           | parent delegation
           |
Plugin URLClassLoader
  ├── provider.VietnameseGreeting
  └── META-INF/services/api.Greeting
```

If `PluginManager` code only calls:

```java
ServiceLoader.load(Greeting.class, Greeting.class.getClassLoader())
```

then discovery starts from **the interface's loader**, which is usually the parent/system loader. The parent loader does not by default see descriptors that reside only in the child loader, so it may receive **0 providers**.

To select the right plugin scope, use:

```java
ServiceLoader<Greeting> services =
        ServiceLoader.load(Greeting.class, pluginLoader);
```

The code above is an **illustrative snippet**; `pluginLoader` must be a properly constructed loader for the deployment. The `Greeting` API must be defined by the parent/shared loader so that the host and provider share the same identity. Avoid copying the interface into the child under a child-first policy, which would cause the plugin to define a different `api.Greeting`.

### TCCL and thread pools

A thread pool worker may carry a different TCCL from the thread that called submit. If `ServiceLoader.load(service)` is called inside the worker, verify the TCCL **on the worker itself**. When temporarily changing the context, restore it in `finally`:

```java
Thread worker = Thread.currentThread();
ClassLoader before = worker.getContextClassLoader();
try {
    worker.setContextClassLoader(pluginLoader);
    // ServiceLoader.load(Greeting.class) within this scope.
} finally {
    worker.setContextClassLoader(before);
}
```

This is an **illustrative snippet**, not a standalone runnable file. If the worker retains a TCCL pointing to the plugin loader after the plugin has “undeployed”, it both risks discovering the wrong provider and can keep the class loader alive, causing a metaspace leak.

**`ServiceLoader` is not a sandbox mechanism**. Reading and instantiating a provider means the program can **execute code from the provider's constructor/static initializer**. Only use provider artifacts from trusted sources, verify versions/signatures/dependencies, and apply appropriate isolation measures.

## 13. How to automatically test descriptors in a real project

Whether you use Maven, Gradle, or an IDE, you should have tests that verify the **built artifact** rather than only the source tree.

### 13.1 Checking the resource

```java
var resources = Thread.currentThread()
        .getContextClassLoader()
        .getResources("META-INF/services/api.Greeting");

if (!resources.hasMoreElements()) {
    throw new AssertionError("SPI descriptor missing");
}
```

This is an **illustrative snippet inside a method handling IOException**, assuming the TCCL is appropriate and non-null. This test only ensures that the resource is found; it does not verify that the provider class is valid.

### 13.2 Checking that at least one provider exists

```java
boolean found = ServiceLoader.load(Greeting.class)
        .iterator()
        .hasNext();

if (!found) {
    throw new AssertionError("No Greeting provider discovered");
}
```

This is an **illustrative snippet** in an environment where `Greeting` and an appropriate runtime loader are already present. If metadata is broken, the `hasNext()` operation may throw a `ServiceConfigurationError` rather than simply returning `false`.

### 13.3 Checking class identity and invoking the method

```java
for (Greeting greeting : ServiceLoader.load(Greeting.class)) {
    if (!Greeting.class.isInstance(greeting)) {
        throw new AssertionError("Provider type mismatch");
    }
    System.out.println(greeting.message());
}
```

This is also an **illustrative snippet**. If ServiceLoader has already returned a valid `Greeting` instance, `isInstance` is normally trivially true; the snippet demonstrates the contract criterion in a test. For complex providers, add assertions for the service's actual behavior (result, configuration, lifecycle).

### 13.4 Inspecting the JAR after packaging

Run:

```bash
jar --list --file plugins/greeting-provider.jar
```

Then, if using Maven Shade/Gradle Shadow, inspect the contents of `META-INF/services/api.Greeting` inside the **final artifact**. For multi-JAR providers, ensure that the resources are merged accurately. Do not infer from the existence of `src/main/resources/META-INF/services/...` that it was definitely copied into the final JAR.

## 14. Checklist for getting it right the first time

1. What is the binary name of the **service interface**? In the example: `api.Greeting`.
2. What is the fully qualified binary name of the **provider implementation**? `provider.VietnameseGreeting`.
3. Is the descriptor located at **`META-INF/services/<ServiceBinaryName>`** at the classpath/JAR root?
4. Is the file content UTF-8, one provider name per line, with no extension/path/constructor syntax?
5. Is the provider class public, concrete, implementing the exact runtime service type, and does it have a public no-arg constructor?
6. Is the JAR containing the provider present **on the runtime classpath or the loader actually used for discovery**?
7. If using the TCCL, does the context of **the thread calling ServiceLoader** have the right loader?
8. Do parent/child loaders share **the same interface `Class<?>`**, or is there a duplicate copy of the API in the plugin?
9. Have you **iterated over ServiceLoader**? Having no providers does not necessarily raise an error when merely calling `load`.
10. Does a `ServiceConfigurationError` occur at `iterator`/`stream`? Have you logged the stack/cause?
11. If using a fat JAR, have descriptors from multiple providers been merged?
12. If moving onto the module path, have automatic/explicit modules, `uses`/`provides`, resolution, and access been accounted for?
13. If hot reload is needed, are a new loader/ServiceLoader and properly scoped TCCL/cache/instance cleanup in place?
14. Do you have an integration test that runs against the **packaged artifact** rather than only code in the IDE?

## 15. Self-check with answers

**Question 1.** Which file registers `provider.VietnameseGreeting` as an implementation of `api.Greeting`?

**Answer:** `META-INF/services/api.Greeting`, containing `provider.VietnameseGreeting` on a UTF-8 line.

**Question 2.** If the file is located at `src/META-INF/services/api.Greeting`, but at runtime you only pass `-cp out` and do not copy the file into `out`, will ServiceLoader automatically look inside `src`?

**Answer:** No. The loader only searches for resources within the classpath entries it can see. You must copy the descriptor into the proper output/resource root or package it inside an appropriate JAR.

**Question 3.** Does `ServiceLoader.load(Greeting.class)` always create instances immediately?

**Answer:** No. Service loading is lazy; providers are typically instantiated during iteration or when `Provider.get()` is called. The example proved that `after load` prints before `provider constructor`.

**Question 4.** Can a provider class with a private no-arg constructor be used for SPI on the classpath?

**Answer:** No, not under the standard classpath provider constructor form. The provider needs to be a public class with a public zero-argument constructor and the appropriate subtype.

**Question 5.** If the descriptor writes `provider/VietnameseGreeting.class`, is that valid?

**Answer:** No. The content must be the **binary class name**: `provider.VietnameseGreeting`, not a filesystem/JAR entry path.

**Question 6.** Why might a provider class be on the classpath yet `ServiceLoader` returns 0?

**Answer:** The descriptor might be missing, the descriptor path/name might be wrong, the runtime loader cannot see the descriptor, or the class is located elsewhere; `ServiceLoader` does not automatically scan all classes to find subtypes.

**Question 7.** If the plugin provider exists only in a child loader, but the host calls `ServiceLoader.load(Greeting.class, Greeting.class.getClassLoader())`, what can happen?

**Answer:** If the interface is in the parent/system loader and the descriptor is only in the child, the parent does not search downward into the child, so discovery may fail to find the provider. Pass the explicit child loader or use an appropriate TCCL.

**Question 8.** Why can having the same interface name `api.Greeting` still cause a provider to be reported as not a subtype?

**Answer:** The host and the plugin may have defined **two different runtime interfaces** through two defining class loaders. JVM identity is based on binary name + defining loader; the API must be shared in a parent/shared loader.

**Question 9.** If multiple JARs each contain a descriptor for `api.Greeting`, is it mandatory to pick only the first provider?

**Answer:** No. `ServiceLoader` can discover multiple providers; the consumer must define a selection/usage policy. Avoid relying on classpath order as a stable business priority mechanism.

**Question 10.** Moving a non-modular provider JAR from the classpath to the module path without modifying code — can it still be called an unnamed module?

**Answer:** Not by default. A non-modular JAR on the module path can become an automatic **named** module if resolved; JPMS/service discovery semantics change compared to a classpath unnamed module.

**Question 11.** Why are providers lost in a fat JAR even though their `.class` files still exist?

**Answer:** The build/shading tool may overwrite `META-INF/services` instead of merging descriptors. In that case, ServiceLoader only knows the provider names remaining in the final resource.

**Question 12.** Does `reload()` change the class bytes of an already loaded `provider.VietnameseGreeting` to a new version?

**Answer:** No. `reload()` clears `ServiceLoader`'s cache; class identity/bytecode is still determined by the defining loader. True hot reloading typically requires a new plugin loader, registry/TCCL cleanup, and lifecycle management.

## Conclusion

For SPI on the **classpath**, you simultaneously need the right **service interface**, a **public provider implementation**, the **`META-INF/services/<service-binary-name>` file at the classpath/JAR root**, and the **ClassLoader used for discovery**. `ServiceLoader` relies on these configuration files to find providers lazily, rather than scanning every class in a JAR or automatically bridging downward from a parent loader into every child plugin loader.

To keep the system extensible and easy to debug, keep the shared API in a common loader, ensure descriptors are copied/merged into the final artifact, pass the loader/TCCL according to an explicit contract, and test at least both cases: **with the provider JAR** (one implementation discovered) and **without the JAR** (0 providers, not a broken configuration).

**Official Java 17 documentation:**

- [`java.util.ServiceLoader` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html) — provider configuration files, public no-arg constructor on the classpath, lazy discovery, caching, `load`/`loadInstalled`/`reload`, and `ServiceConfigurationError`.
- [`java.lang.ClassLoader` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html) — parent delegation and resource lookup.
- [`java.lang.Thread` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html) — context class loader.
- [Java SE 17 JAR File Specification](https://docs.oracle.com/en/java/javase/17/docs/specs/jar/jar.html) — JAR entry/root/manifest layout.
- [`java.lang.Module` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Module.html) — module boundaries for SPI on the module path.

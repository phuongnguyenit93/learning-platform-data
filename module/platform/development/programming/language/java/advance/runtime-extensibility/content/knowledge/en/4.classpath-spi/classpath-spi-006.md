# Adding or Removing Provider JARs Without Modifying Host Application Code

## Goal and Scenario

In a runtime-extensible system, a host application may need to support new ways of handling data: format parsers, data converters, report exporters, or service connection adapters. If the host had to import every concrete class and add a conditional branch each time a plugin appeared, we would have to edit, recompile, and re-release host code for a change that belongs to the plugin.

**Java Service Provider Interface (SPI)** solves implementation discovery on the **classpath**: the host depends on a shared interface, while each provider JAR packages an implementation and a service declaration file. When launching the JVM with a different set of provider JARs, the exact same host code can find a different set of implementations via `java.util.ServiceLoader`.

This lesson focuses on **adding or removing provider JARs without modifying host source code**. "At runtime" must be understood accurately: in the standard classpath model, the list of JARs is decided when **launching the Java process**. Dropping another JAR into a directory after the host has already started does not make the application class loader automatically see that JAR; `ServiceLoader.reload()` also does not turn a static classpath into a hot-plug mechanism.

After this lesson, you will be able to:

- Define a shared SPI contract between the host and providers.
- Package each provider into an independent JAR with a `META-INF/services` declaration.
- Launch the **exact same host program** with 0, 1, or multiple providers by changing the plugin directory contents and restarting.
- Distinguish changing the JAR set at deployment from dynamically loading/unloading providers inside a running JVM.
- Verify provider discovery, API compatibility, configuration error handling, and classpath limitations.

## 1. Relationship Between Host, SPI, and Provider JARs

Suppose an application greets users in multiple languages. The host knows only the contract:

~~~java
public interface GreetingService {
    String id();
    String greet(String name);
}
~~~

This is an **abbreviated snippet for explanation**; the next section provides complete code with packages and compile commands. There can be Vietnamese and English providers both implementing `GreetingService`.

~~~text
                 +----------------------+
                 |  host.jar            |
                 |  ServiceLoader       |
                 +-----------+----------+
                             |
                             v
                 +----------------------+
                 |  greeting-api.jar    |
                 |  GreetingService     |
                 +----------------------+
                             ^
           +-----------------+-----------------+
           |                                   |
+----------+-----------+             +---------+------------+
| greeting-vi.jar       |             | greeting-en.jar       |
| VietnameseGreeting    |             | EnglishGreeting       |
| META-INF/services/... |             | META-INF/services/... |
+----------------------+             +----------------------+
~~~

This structure has three distinct roles:

| Component | What Does the Host Know? | How Can It Change? |
| --- | --- | --- |
| **SPI/API JAR** | The `GreetingService` interface and conventions for using it | Changes according to a shared versioning policy |
| **Host JAR** | Service name, how to find providers, and calling interface methods | Does not need editing when adding a compatible implementation |
| **Provider JAR** | Implementation, declaration descriptor, own dependencies if any | Can be added, removed, or replaced in a new deployment |

The host does not instantiate `new VietnameseGreeting()`, does not import `EnglishGreeting`, and does not hardcode a list of provider class names. The set of available providers comes from the JARs actually present on the runtime classpath.

### How ServiceLoader Works on the Classpath

For the service interface `example.spi.GreetingService`, each provider JAR must contain a file at the **exact path**:

~~~text
META-INF/services/example.spi.GreetingService
~~~

The file contents are the fully qualified binary name of the implementation class, one class per line:

~~~text
example.provider.vi.VietnameseGreeting
~~~

When the host calls `ServiceLoader.load(GreetingService.class)`, the SPI mechanism uses the relevant class loader to locate `META-INF/services/example.spi.GreetingService` configuration resources, reads provider class names, and creates instances when iterated. Discovery and instantiation are **lazy**: having a `ServiceLoader` does not mean all providers have already been instantiated. Descriptor or instantiation errors may only surface when iterating over elements.

For traditional classpath providers, the implementation class must be a valid subtype of the service, accessible, and have a public no-argument constructor. The descriptor file **cannot be placed arbitrarily**, and `javac` only compiles `.java` files; when packaging a JAR, the descriptor resource must be included as a separate step. On the JPMS module path, `uses`/`provides` declarations and provider rules differ; the examples in this lesson use **standard classpath and JARs**.

## 2. Complete Example on Java 17

The example requires no Maven, Gradle, or external libraries. You need JDK 17 or higher with the `javac`, `java`, and `jar` commands.

Source file layout under the working directory `spi-demo`:

~~~text
spi-demo/
  src/
    api/example/spi/GreetingService.java
    host/example/host/HostApp.java
    vi/example/provider/vi/VietnameseGreeting.java
    vi/META-INF/services/example.spi.GreetingService
    en/example/provider/en/EnglishGreeting.java
    en/META-INF/services/example.spi.GreetingService
  build/                         (created by the commands below)
~~~

Package names and file paths must match. The file name inside `META-INF/services` is the **fully qualified name of the interface**, not the provider name.

### 2.1. Shared API Contract

File `src/api/example/spi/GreetingService.java`:

~~~java
package example.spi;

/**
 * Minimal contract shared by the host and all providers.
 */
public interface GreetingService {
    /** Provider identifier used for display and recognition. */
    String id();

    /** Builds a greeting for the supplied name. */
    String greet(String name);
}
~~~

The API mentions no provider classes and references no private libraries. `id()` is used for display and deterministic ordering in the demo. A real system needs rules for handling duplicate IDs if IDs are used to select providers; here no extra registry mechanism is needed yet.

### 2.2. Host Using Only SPI and ServiceLoader

File `src/host/example/host/HostApp.java`:

~~~java
package example.host;

import example.spi.GreetingService;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.ServiceLoader;

public final class HostApp {
    private HostApp() {
    }

    public static void main(String[] args) {
        String name = args.length == 0 ? "An" : args[0];

        List<GreetingService> providers = new ArrayList<>();
        ServiceLoader.load(GreetingService.class).forEach(providers::add);

        // Do not rely on the discovery order from the classpath.
        providers.sort(Comparator.comparing(GreetingService::id));

        if (providers.isEmpty()) {
            System.out.println("No providers");
            return;
        }

        for (GreetingService provider : providers) {
            System.out.println(
                    provider.id() + " = " + provider.greet(name));
        }
    }
}
~~~

The key point is that there are **no imports from `example.provider.*`**. The host does not know how many providers exist. Sorting by `id()` in the demo gives deterministic output when adding multiple JARs; the order in which `ServiceLoader` iterates providers should not be treated as a stable business priority order.

The line `forEach(providers::add)` causes `ServiceLoader` to iterate over providers and instantiate them. If a provider cannot be loaded or instantiated, `ServiceConfigurationError` may occur at this moment. In a real application, a fail-fast policy or skipping faulty plugins must be designed explicitly, rather than simply swallowing all errors.

### 2.3. Vietnamese Provider

File `src/vi/example/provider/vi/VietnameseGreeting.java`:

~~~java
package example.provider.vi;

import example.spi.GreetingService;

public final class VietnameseGreeting implements GreetingService {
    public VietnameseGreeting() {
    }

    @Override
    public String id() {
        return "vi";
    }

    @Override
    public String greet(String name) {
        return "Xin chào, " + name + "!";
    }
}
~~~

Create the text file **`src/vi/META-INF/services/example.spi.GreetingService`** with a single line:

~~~text
example.provider.vi.VietnameseGreeting
~~~

The descriptor lives inside the provider JAR, independent of the host. Do not write file paths or unqualified class names into the descriptor contents.

### 2.4. English Provider

File `src/en/example/provider/en/EnglishGreeting.java`:

~~~java
package example.provider.en;

import example.spi.GreetingService;

public final class EnglishGreeting implements GreetingService {
    public EnglishGreeting() {
    }

    @Override
    public String id() {
        return "en";
    }

    @Override
    public String greet(String name) {
        return "Hello, " + name + "!";
    }
}
~~~

Create the file **`src/en/META-INF/services/example.spi.GreetingService`** with a single line:

~~~text
example.provider.en.EnglishGreeting
~~~

Each provider has its own descriptor; both point to `GreetingService` yet register two different classes. The provider JARs do not need to depend directly on each other. If a provider later uses JSON, an HTTP client, or a third-party SDK, those types should remain internal to the implementation and not appear in `GreetingService` signatures.

## 3. Compiling the Host Once and Packaging Two Provider JARs

In the `spi-demo` directory, use Bash on Linux/macOS or a compatible shell. Run after creating all six source/resource files in Section 2:

~~~bash
mkdir -p build/api build/host build/vi build/en build/plugins

# 1. Compile the API and create greeting-api.jar.
javac --release 17 -encoding UTF-8 \
  -d build/api src/api/example/spi/GreetingService.java
jar --create --file build/greeting-api.jar -C build/api .

# 2. Compile the host only against the API, without needing provider classes.
javac --release 17 -encoding UTF-8 \
  -cp build/greeting-api.jar \
  -d build/host src/host/example/host/HostApp.java
jar --create --file build/host.jar -C build/host .

# 3. Compile each provider against the same API.
javac --release 17 -encoding UTF-8 \
  -cp build/greeting-api.jar \
  -d build/vi src/vi/example/provider/vi/VietnameseGreeting.java
jar --create --file build/greeting-vi.jar \
  -C build/vi . -C src/vi META-INF/services

javac --release 17 -encoding UTF-8 \
  -cp build/greeting-api.jar \
  -d build/en src/en/example/provider/en/EnglishGreeting.java
jar --create --file build/greeting-en.jar \
  -C build/en . -C src/en META-INF/services
~~~

The command `jar -C build/vi . -C src/vi META-INF/services` captures both the compiled `.class` files and the SPI declaration directory. The same applies to the English provider. If you only package `.class` files and forget `META-INF/services`, `ServiceLoader` cannot discover the provider even though the implementation exists in the JAR.

You can verify the JAR structure with:

~~~bash
jar --list --file build/greeting-vi.jar
jar --list --file build/greeting-en.jar
~~~

In the output, you must see the `META-INF/services/example.spi.GreetingService` file and the `example/provider/.../*.class` classes. Entry order in the JAR listing does not matter. Before copying JARs into `build/plugins`, that directory is created empty.

## 4. Adding and Removing JARs Without Modifying the Host

The following runs use the **same `build/host.jar` and `build/greeting-api.jar`**. Only the contents of `build/plugins` change. Each `java` command starts a **new** JVM, allowing the launcher to re-evaluate the classpath at startup.

The classpath item `build/plugins/*` is a wildcard expanded by the **Java launcher** to the JARs directly inside the directory. Keep the `*` character inside quotes so the shell does not expand it in an unintended way. The Java launcher does not recursively search subdirectories of `build/plugins`.

### State A: No Provider JARs

~~~bash
java -cp "build/greeting-api.jar:build/host.jar:build/plugins/*" \
  example.host.HostApp
~~~

Output:

~~~text
No providers
~~~

This is a valid outcome for the demo: no JAR provides `GreetingService`, so the host runs and handles an empty list according to its written policy.

### State B: Adding the Vietnamese JAR

~~~bash
cp build/greeting-vi.jar build/plugins/
java -cp "build/greeting-api.jar:build/host.jar:build/plugins/*" \
  example.host.HostApp
~~~

Output:

~~~text
vi = Xin chào, An!
~~~

No need to open `HostApp.java`, call a named factory, or recompile `host.jar`.

### State C: Adding the English JAR While Keeping the Vietnamese JAR

~~~bash
cp build/greeting-en.jar build/plugins/
java -cp "build/greeting-api.jar:build/host.jar:build/plugins/*" \
  example.host.HostApp
~~~

Output:

~~~text
en = Hello, An!
vi = Xin chào, An!
~~~

The host explicitly sorts by ID so the output is consistent. Without `sort`, you should not assert which provider is always printed first when using a wildcard classpath.

### State D: Removing the Vietnamese JAR from the Plugin Directory

~~~bash
rm build/plugins/greeting-vi.jar
java -cp "build/greeting-api.jar:build/host.jar:build/plugins/*" \
  example.host.HostApp
~~~

Output:

~~~text
en = Hello, An!
~~~

Deletion here applies only to the **copy** `build/plugins/greeting-vi.jar` in the demo directory; the compiled `build/greeting-vi.jar` remains available to re-add later. In real deployments, a rollout/rollback step typically moves or replaces JARs and restarts the service in a controlled manner.

### Windows Notes

On Windows, the classpath separator is a **semicolon** `;` instead of a colon `:`. Once the JARs and plugin directory are ready, the PowerShell launch command is:

~~~powershell
java -cp "build/greeting-api.jar;build/host.jar;build/plugins/*" example.host.HostApp
~~~

PowerShell can use `Copy-Item build/greeting-vi.jar build/plugins/` and `Remove-Item -LiteralPath build/plugins/greeting-vi.jar` to add/remove the plugin copy. The Bash compile commands above use `\` for line continuation; in PowerShell, write each `javac`/`jar` command on a single line or use PowerShell's appropriate line-continuation syntax.

## 5. Why Does Adding or Removing JARs Change the Outcome?

Sequence on each startup:

1. The Java launcher receives a classpath containing `greeting-api.jar`, `host.jar`, and JARs matching `build/plugins/*` at launch time.
2. The JVM loads `HostApp` and `GreetingService`. The program calls `ServiceLoader.load(GreetingService.class)` without knowing concrete implementation classes.
3. The class loader locates `META-INF/services/example.spi.GreetingService` resources from visible JARs.
4. `ServiceLoader` reads provider names, loads the required classes, checks service compatibility, and instantiates them per SPI rules during iteration.
5. The host receives objects as type `GreetingService`, sorts by `id()`, calls `greet()`, and prints the results.

When **adding** a compliant JAR before the next launch, steps 1 and 3 gain another descriptor/provider, so the list the host iterates over has an extra element. When **removing** the JAR, that provider's descriptor is no longer visible from the new classpath, so it disappears from the list.

**Note on `ServiceLoader.load`:** the single-argument call uses the thread context class loader per the Java API contract. In a standard launcher example, this loader sees the JARs on the application classpath. When running in an application server, framework, custom class loader, or multi-loader environment, you must choose the right loader or use the `ServiceLoader.load(service, classLoader)` variant when needed; if the descriptor is not visible, the list can be empty even if the JAR exists on disk.

### Things That Do Not Happen Automatically

- Dropping a new JAR into `build/plugins` **while the process is running** does not update the URLs/resources of the already-initialized application class loader.
- `ServiceLoader.reload()` only clears the provider cache of **that existing `ServiceLoader` instance**, so subsequent iterations re-read via the active class loader. If the class loader does not see the new JAR, `reload()` cannot discover the new JAR.
- Deleting or replacing a JAR on disk while the process is running does not guarantee unloading classes, objects, or threads that have already been loaded. The class loader may continue holding old classes, and operating systems differ in how they handle open JAR files.
- Classpath SPI is not a complete plugin lifecycle management system. If true loading/unloading within a single JVM is required, you must design dedicated class loaders, JAR source discovery, cache/reload, resource closing, and corresponding isolation policies. That is more complex than basic classpath SPI.

## 6. Safe Packaging and Deployment

To ensure swapping JARs does not destabilize the host, maintain clear conventions at the host/provider boundary.

### A Single Shared API Copy

Both the host and plugins compile against a compatible `greeting-api.jar`. Do not include another copy of `GreetingService.class` inside a provider JAR, and do not rename/shade the service interface expecting `ServiceLoader` to treat it as the same type. In the JVM, class identity depends on both the class name **and the defining class loader**; two copies of a class with the same name defined by two different loaders can still be incompatible.

Providers should rely on a small, stable contract. Adding abstract methods to the interface, renaming packages, or changing parameter types can break pre-compiled providers when the host calls them. Publish the supported API version range and test the new host against older providers before updating.

### JAR Resources and Configuration

Each provider JAR needs to contain:

- The actual implementation class implementing the SPI.
- The descriptor `META-INF/services/<fully qualified name of service>` containing the exact provider class.
- Required implementation resources, if any.

If a project uses Gradle/Maven, descriptors are normally placed in `src/main/resources/META-INF/services/...` to be packaged into the JAR with resources. If using a build plugin to generate descriptors automatically, inspect the final artifact rather than looking only at source code.

One service can have multiple providers; each JAR has its own descriptor. If multiple JARs use the same class/provider name or share the same business ID, clearly define how duplicates are detected and handled. The demo sorts by ID yet sets **no** anti-duplication policy; a production application should reject duplicate IDs or apply a specific selection policy.

### Dependencies and Shared Classpath Risks

The example uses standard Java, so providers have no external dependencies. For real plugins, copying just `plugin.jar` into a directory does not guarantee dependency classes are present. Package and declare runtime dependencies properly, such as dependency JARs in a `lib/*` directory added to the classpath or controlled packaging.

**A standard classpath does not isolate plugin dependency versions.** Two providers requiring incompatible library versions can collide because they share the same class-loading space. If per-plugin isolation is required, designing custom class loaders/module layers with API-sharing rules is a separate approach, not an automatic capability of `ServiceLoader` on a single classpath.

**Plugins on the classpath execute Java code inside the same JVM with access permissions matching the host process.** Load only trusted JARs and verify build origins and release policies; SPI is not a security sandbox.

### Deployment and Rollback Strategy

For long-lived service updates, you can follow this workflow:

1. Compile and test the new provider against the API version the host is currently using.
2. Verify JAR contents and `META-INF/services`; retain version metadata, release provenance, and checksums if required by deployment procedures.
3. Place JARs to enable into the plugin directory; move JARs to disable out of that directory. Avoid leaving two versions of the same provider side by side unless a naming/ID collision policy exists.
4. Restart the host or launch a new instance with the new classpath; inspect logs of loaded provider IDs.
5. Verify business behavior; on rollback, restore the previous JAR set and restart using the same mechanism.

The host **never changes source code** throughout this entire workflow. The system still needs operational control over versioning and restart timing for updates to take effect.

## 7. Common Errors and How to Identify Root Causes

| Symptom | Possible Cause | How to Check |
| --- | --- | --- |
| JAR exists yet host prints "No providers" | JAR is not on runtime classpath; missing descriptor; wrong descriptor path; context class loader does not see JAR | Print classpath, run `jar --list --file`, verify interface name and loader |
| `ServiceConfigurationError` | Wrong provider name in descriptor, class cannot be loaded, not a subtype, or cannot be instantiated per SPI rules | Read full message and cause; check FQCN, constructor, API version, class loader |
| `NoClassDefFoundError` | Missing dependency class when loading or running the provider | Check runtime dependencies and provider artifact |
| `ClassCastException` or "not a subtype" error | Service API may have been loaded as two distinct class identities or provider violates contract | Check class loaders and avoid packaging duplicate API copies |
| Unexpected provider appears in results | Old JAR left in directory, multiple descriptors found, plugin directory contains duplicate copies | List active JARs, inspect each JAR's descriptor and ID rules |
| Added JAR and called `reload()`, still not seen | Current class loader does not know about the new JAR | Restart JVM with updated classpath or implement an intentional dynamic loader |
| Replaced running JAR yet output stays old | Old classes/provider already loaded and held in cache or application objects | Restart or manage lifecycle/unloading via a dedicated mechanism |

Do not catch all `Throwable`s and keep running as if every provider error were normal. Choose a clear policy: fail early with diagnostics for required services; optional services can be isolated and reported if the system is designed for it.

## 8. Testing to Prove Host Independence from Providers

A minimal test suite should cover the following scenarios, always starting from the **same** host code and artifact:

| JAR Set in `build/plugins` | Expected Result |
| --- | --- |
| Empty | `No providers` |
| Only `greeting-vi.jar` | One line `vi = Xin chào, An!` |
| Only `greeting-en.jar` | One line `en = Hello, An!` |
| Both JARs | Two lines, sorted by ID: `en` then `vi` |
| Remove Vietnamese JAR and restart | Only `en` remains |
| Change descriptor contents to an invalid class name in a separate test build | Detects service loading error, does not silently accept broken provider |
| Provider compiled against an incompatible API | Detected at compile time, linkage time, or during iteration/invocation depending on the change |

To verify true independence, try **compiling the host against only the API JAR**. Do not include implementation JARs on the host's compile classpath. Then test running the same host JAR with various provider sets; if you ever need to edit imports, call concrete constructors, or change `if/else` logic in the host whenever adding a provider, the design has not achieved SPI extensibility.

You can add logging after iteration to record the IDs and classes of selected providers; in production systems, also log version and JAR source if useful for operations. Avoid letting arbitrary iteration order become a business selection rule.

## 9. When to Apply and Limitations to Keep in Mind

**Suitable** when the host has a stable extension point, providers can be packaged independently, and toggling providers by **changing the classpath on the next startup** suffices: parsers, exporters, codecs, connectors, or optional adapters. It is an effective way to decouple host and implementations.

**Insufficient** if requirements demand zero-downtime enabling/disabling of JARs inside an already-running JVM, isolating differing dependency versions, restricting permissions of untrusted plugins, or managing complex lifecycles. Those requirements need additional mechanisms. `ServiceLoader` remains useful even inside a more complex loader architecture, but on its own it does not solve all of those problems.

Practical rule: **the host owns the contract and how services are used; the provider owns the implementation and registration metadata; the set of JARs present on the runtime classpath determines which providers the host can discover**. With that separation, adding or removing a compatible provider is a deployment and restart operation, not a host source-code change.
# How Do the Host Application, Service Contract, and Extensions (Plugins) Relate?

## 1. The Big Picture

A system with runtime extensibility typically has three roles:

- **Host application:** the program that owns the business workflow, UI, data, configuration, and decides when an extension capability is needed.
- **Service contract (SPI):** the public set of types and rules defining what capability a plugin can provide, what the host is allowed to invoke, and what conditions both sides must satisfy.
- **Extension (plugin/service provider):** the component implementing that contract, usually packaged separately, that can add or replace how a feature works without modifying the host's business code.

You can visualize the relationship as:

```text
                       calls via contract
   +------------------+ -------------------> +----------------------+
   | Host application |                      | Service contract     |
   | selects, orchestrates,                  | Formatter (API/SPI)  |
   | manages errors   |                      +-----------+----------+
   +--------+---------+                                  ^
            |                                            | implements
            | discovers, loads, selects                  |
            +------------------------------------> +-----+--------------+
                                                  | Plugin A / Plugin B |
                                                  | concrete impls      |
                                                  +---------------------+
```

The `calls via contract` arrow shows that the host works through a known interface. The plugin **implements** that interface. The **discovery and loading** step is the mechanism the host uses to obtain the implementing object; it can be based on configuration, manual registration, `ServiceLoader`, dependency injection, or a custom plugin manager.

Core point: **the host knows the capability it needs and the contract to follow; the host does not need to know the concrete implementation class name of each plugin in advance**. Therefore, new implementations can be introduced into the system while keeping the service-calling code stable.

## 2. Responsibilities and Boundaries of Each Component

| Component | What does it own? | What should it avoid depending on directly? |
|---|---|---|
| Host | Business flow, plugin selection, configuration, data, error control, and access permissions | Concrete plugin implementation classes when they can be called via the contract |
| Service contract | Operation names, parameter/return types, preconditions, postconditions, exceptions, version compatibility | Internal details or private libraries of a specific plugin |
| Plugin | Specific algorithms/capabilities, its own resources and dependencies, behavior fulfilling the contract | Unexposed internal structures of the host |

**A contract is more than just an `interface`.** For example, a text-conversion service may also need to specify a unique identifier, `null`-value handling, output format, concurrency safety, state, and lifecycle. If both sides match method signatures but interpret semantics differently, the plugin can still cause business errors.

Terminology to distinguish:

- **Service** is an abstract capability described by a type/contract, such as `Formatter`.
- **Provider** is a class/object that implements the service; in Java SPI, providers are typically located via `ServiceLoader`.
- **Plugin** is an extension unit that can be distributed, enabled/disabled, or managed independently. One plugin can provide multiple providers and contain supporting code; not every provider constitutes a full plugin system.
- **API** is the public programming surface; **SPI** (Service Provider Interface) emphasizes the contract intended for third parties to implement. The same Java interface can play both roles in simple examples.

## 3. Dependency Relationships: Who Knows Whom?

A common design extracts the contract into a small library:

```text
             +------------------------+
             | shared-contract.jar    |
             | Formatter, data types  |
             +------------+-----------+
                          ^
                  depends | depends
                 +--------+--------+
                 |                 |
       +---------+------+  +-------+-----------+
       | host.jar       |  | upper-plugin.jar  |
       | only calls     |  | implements        |
       | Formatter      |  | Formatter         |
       +----------------+  +-------------------+
```

At **compile time**, both the host and the plugin know the shared contract, but the host does not need to `import demo.plugin.UpperFormatter`. At **runtime**, the system also needs a way to discover and bind implementations to the contract. Loading a JAR does not automatically turn a class into a plugin; the host must have rules to register/discover and invoke it.

This is an application of **Dependency Inversion**: high-level orchestration code does not depend on the details of concrete algorithms; both sides rely on a stable contract. The host still controls **selecting** the provider, processing order, data passed to the plugin, and behavior when no suitable provider exists.

Practical example: a report-export application has a `ReportExporter` contract. Both the CSV plugin and the JSON plugin implement the contract; the host calls the appropriate provider based on the format chosen by the user. Adding a PDF plugin means adding a new implementation and registration, rather than writing `if/else` branches tightly coupled to a PDF class inside the application core.

## 4. Execution Sequence from Startup to Use

1. **Contract definition:** the host or platform-owning team publishes the service type and compatibility rules.
2. **Implementation:** the plugin author writes a class that fulfills the contract, packaging dependencies and registration metadata.
3. **Plugin deployment:** placing the artifact where the loading mechanism can see it, such as a JAR on the classpath or module path.
4. **Discovery:** the host retrieves the list of providers via `ServiceLoader`, a registry, or another mechanism.
5. **Validation and selection:** the host checks capabilities, configuration, version, and prerequisites before use.
6. **Execution:** the host passes input data according to the contract and handles the provider's output/errors.
7. **Lifecycle management:** if the contract includes initialization, closing, or resource cleanup, the host coordinates those steps.

The three roles above form an **architectural model**. `ServiceLoader` is merely a **provider discovery tool** supplied by Java; it does not by itself solve authorization, process isolation, hot updates, version management, or resource closing.

## 5. Java 17+ Example: Host Calling a Plugin via ServiceLoader

We will build a string-formatting service. The host only knows `Formatter`; the plugin provides uppercase formatting. The example uses the **classpath** to clearly demonstrate compiling both sides separately.

File structure to create:

```text
demo/
├── api/src/demo/spi/Formatter.java
├── host/src/demo/host/Main.java
└── plugin-upper/
    ├── src/demo/plugin/UpperFormatter.java
    └── resources/META-INF/services/demo.spi.Formatter
```

**Contract** — `api/src/demo/spi/Formatter.java`:

```java
package demo.spi;

public interface Formatter {
    String id();
    String format(String value);
}
```

`id()` is the identifier for the host to recognize the capability; `format(String)` is the operation the host is allowed to call. In a real system, you should specify whether `id` must be unique and how abnormal inputs are handled.

**Plugin** — `plugin-upper/src/demo/plugin/UpperFormatter.java`:

```java
package demo.plugin;

import demo.spi.Formatter;
import java.util.Locale;

public final class UpperFormatter implements Formatter {
    public UpperFormatter() {
    }

    @Override
    public String id() {
        return "upper";
    }

    @Override
    public String format(String value) {
        return value.toUpperCase(Locale.ROOT);
    }
}
```

The `UpperFormatter` provider implements the contract and has a public no-argument constructor, matching how Java's `ServiceLoader` instantiates providers on the classpath. `Locale.ROOT` ensures consistent uppercase conversion rather than relying on the machine's default locale.

**Provider registration** — a UTF-8 text file named exactly `plugin-upper/resources/META-INF/services/demo.spi.Formatter`:

```text
demo.plugin.UpperFormatter
```

The **file name** equals the fully qualified name of the service interface; the **content** is the provider class name. When packaging the JAR, the path `META-INF/services/demo.spi.Formatter` must be preserved inside the JAR. This is the bridge enabling `ServiceLoader` to locate the plugin on the classpath; merely implementing `implements Formatter` without the registration file will not auto-discover the provider in this example.

**Host** — `host/src/demo/host/Main.java`:

```java
package demo.host;

import demo.spi.Formatter;
import java.util.ServiceLoader;

public final class Main {
    public static void main(String[] args) {
        int found = 0;

        for (Formatter formatter : ServiceLoader.load(Formatter.class)) {
            System.out.println(
                formatter.id() + " -> " + formatter.format("hello plugin")
            );
            found++;
        }

        if (found == 0) {
            System.out.println("No formatter provider found");
        }
    }
}
```

The host does not `import` the `UpperFormatter` class or call `new UpperFormatter()`. The host requests a service of type `Formatter`, iterates over discovered providers, and invokes them through the same contract.

**Compile and run from the `demo` directory using PowerShell (Windows, JDK 17+):**

```powershell
New-Item -ItemType Directory -Force -Path out\api,out\host,out\plugin | Out-Null

javac -d out\api api\src\demo\spi\Formatter.java
javac -cp out\api -d out\host host\src\demo\host\Main.java
javac -cp out\api -d out\plugin plugin-upper\src\demo\plugin\UpperFormatter.java

Copy-Item -Path plugin-upper\resources\META-INF -Destination out\plugin -Recurse
jar --create --file out\upper.jar -C out\plugin .

java -cp "out\api;out\host;out\upper.jar" demo.host.Main
```

Standard output with exactly one provider:

```text
upper -> HELLO PLUGIN
```

Try running again while **removing the plugin JAR from the classpath**:

```powershell
java -cp "out\api;out\host" demo.host.Main
```

Output:

```text
No formatter provider found
```

On macOS/Linux, replace the classpath separator `;` with `:`; use `/` paths and equivalent directory-creation/copy commands. The Java `javac` and `jar` commands carry the same meaning.

**What the example proves:** the host code remains identical across both runs; the difference comes from whether the provider is deployed and discovered. To add another format, write another provider implementing `Formatter`, register it, and place its JAR in the runtime environment. The host only needs to change if the business requirements for **how** to select plugins change.

## 6. Classpath, JPMS, and Discovery Limits

With Java 9+ and the **Java Platform Module System (JPMS)**, a provider residing in a named module is typically declared via `provides ... with ...`; the service-consuming module declares `uses ...`. Conceptual structure example, **separate from the classpath program in section 5**:

```java
// module-info.java in the contract module
module demo.api {
    exports demo.spi;
}
```

```java
// module-info.java in the host module
module demo.host {
    requires demo.api;
    uses demo.spi.Formatter;
}
```

```java
// module-info.java in the provider module
module demo.upper {
    requires demo.api;
    provides demo.spi.Formatter with demo.plugin.UpperFormatter;
}
```

The `module-info.java` files above illustrate module configuration; to run under JPMS, the code must be organized and recompiled into the corresponding modules and placed on the module path. For providers belonging to an **explicit named module**, the `provides` declaration is the primary registration mechanism; the `META-INF/services` file from the classpath example does not replace that declaration.

Key characteristics of `ServiceLoader` to remember:

- Providers are usually **discovered and instantiated lazily** while iterating the loader, meaning not all plugins are instantiated immediately when `load` is called.
- A `ServiceLoader` instance can cache loaded providers. `reload()` refreshes the loader's cache/lookup; it **does not guarantee** that new JARs are added to the classloader, does not automatically unload already-loaded classes, and does not create a complete hot-reload mechanism.
- Faulty providers, missing classes, wrong types, or instantiation failures can throw `ServiceConfigurationError`. The host needs an appropriate error-reporting and handling strategy.
- When multiple providers exist, you should not assume iteration order equals business priority order. If a single provider must be selected, define identifiers/capabilities, duplicate-detection rules, selection conditions, and a fallback policy.

If requirements call for loading JARs **after the host has started**, replacing plugins without restarting, or isolating library versions, you typically need explicit `ClassLoader`/`ModuleLayer` and lifecycle management, or a suitable plugin framework. Do not assume that having `ServiceLoader` provides safe hot updates.

## 7. Designing Contracts So Plugins Can Last

**Type and semantic stability.** Both sides must use compatible contract versions. Renaming methods, changing return types, or adding abstract methods can make old plugins incompatible. Prefer intentional, versioned changes with compatibility testing; do not treat `default method` as a cure-all for every semantic change.

**Minimize dependency leakage.** Avoid putting internal host types or types from private implementation libraries into service signatures. A small contract with stable data types is easier for external plugins to implement.

**Clearly specify capabilities.** If multiple plugins provide the same service, the host may need an identifier, display name, version, list of supported formats, and operational capabilities. This data should be exposed via a clear contract/metadata; avoid relying on Java class names or accidental classpath order.

**Define control boundaries.** The plugin executes the assigned function; the host decides what data and permissions are passed in, call counts, timeouts, retries, logging, provider selection, and how to handle plugin failures. Do not let a plugin arbitrarily take over the entire business flow simply because it was loaded into the JVM.

**Resource management.** If a plugin opens files, sockets, threads, or connections, the contract should include explicit initialization/closing mechanisms, such as a `close()` method or `AutoCloseable`. The `Formatter` example needs no close step because it holds no resources. The host must determine whether a single instance is shared across multiple threads; concurrency safety must be part of the contract.

**Error control and observability.** Record which provider is running, which version, and which operation failed. A broken plugin should not mislead the host into thinking the entire system has no providers; provider loading errors, initialization errors, and invocation errors are distinct cases.

## 8. Extensibility Does Not Equal Safe Isolation

Java plugins running in the same JVM generally have the ability to execute code with the host process's privileges. `ServiceLoader` **is not a sandbox mechanism**. Only load plugins from trusted sources, and control dependencies and access permissions; if untrusted third-party code must run, consider isolating via separate processes/containers and a dedicated communication protocol.

A classloader establishes a class-loading boundary, but is not inherently a security boundary. Two classes with the same fully qualified name defined by two different classloaders can be **two distinct types** in the JVM; this causes `ClassCastException` if the host and plugin load separate copies of the contract interface itself. A dynamic loading design must ensure both sides see the **same class identity for the service contract**, usually by sharing the API from an appropriate parent classloader.

Plugins can also have conflicting library dependency versions, consume excessive CPU/memory, spawn non-terminating threads, or block I/O. Managing those is the architectural responsibility of the host/plugin manager rather than something an `interface` can protect against on its own.

## 9. Common Design Mistakes

| Symptom | Common Cause | Fix |
|---|---|---|
| Host calls `new ConcretePlugin()` in many places | Core is coupled to concrete implementations | Call through the service type and a provider-selection mechanism |
| Class `implements` the interface but plugin is not discovered | Missing/incorrect `META-INF/services` file or `provides` declaration, or JAR not visible to loader | Verify exact full name, packaging path, and runtime environment |
| Interface change breaks old plugins | Contract changed without a compatibility policy | Manage API versions, test plugins across multiple host versions |
| Picking the first provider found | No business priority rules | Select by ID/config/capability; check for duplicates and missing providers |
| Calling `reload()` expecting full hot-swap | Confusing service rescanning with swapping classloaders and freeing resources | Design dedicated load/unload and lifecycle mechanisms |
| Plugin holds resources after being retired | Contract lacks closing responsibility | Add lifecycle and ownership of closing |
| Believing plugins in the same JVM are safely isolated | Confusing class-loading mechanisms with security boundaries | Use only trusted plugins or move to separate processes |

## 10. Check Your Understanding

1. **Why should the host import `Formatter` instead of `UpperFormatter`?** Because the contract allows swapping implementations while keeping the calling code unchanged.
2. **Can a plugin work if only a JAR containing the implementation class is present?** Not necessarily. The host still needs to discover/register and load the provider via the chosen mechanism.
3. **If `upper.jar` is removed from the example classpath, what changes?** The host still runs but finds no providers, so it prints `No formatter provider found`.
4. **Does adding a plugin automatically resolve priority conflicts?** No. The host needs provider-selection rules if multiple matching results exist.
5. **Does `ServiceLoader` automatically protect the host from malicious plugins or hot-update JARs?** No. Security, version management, lifecycle, and dynamic loading are additional design concerns.

**Mini exercise:** Write an additional `LowerFormatter` that returns lowercase text, place it in a separate JAR, and register it under the same `demo.spi.Formatter` service. Run the host with one or two plugin JARs; observe each discovered provider, then add a selection rule by `id`. This helps clearly see the boundary between a **stable contract**, **multiple implementations**, and **host policy**.

## References

- Java SE 17, `ServiceLoader`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html
- Oracle Java Tutorials, `Creating Extensible Applications`: https://docs.oracle.com/javase/tutorial/ext/basics/spi.html

When reading older Java documentation, note that the extensions directory mechanism in earlier JDK versions is obsolete; the examples above intentionally use Java 17+ classpath/JAR and JPMS.
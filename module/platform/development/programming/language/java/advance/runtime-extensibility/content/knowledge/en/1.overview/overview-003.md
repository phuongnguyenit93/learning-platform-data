# API and SPI: Who Uses the Service and Who Provides It?

In a Java system with runtime extensibility, the application needs to **use a capability** without necessarily knowing **which class provides that capability**. Distinguishing API from SPI clarifies both sides of this contract: service-consuming code (consumer) and service-implementing code (provider).

## 1. Two Perspectives on the Same Service

**API (Application Programming Interface)** is the surface that the calling side invokes to get work done. The API answers: "What can I ask the system to do, what do I pass in, and what do I get back?". It can include interfaces, classes, methods, data types, exceptions, and public behavioral rules.

**SPI (Service Provider Interface)** is the contract that a library or platform publishes so other parties can **implement and register the execution logic**. The SPI answers: "To supply this capability to the system, which extension points must I implement?". A provider is the concrete library/class implementing the SPI; the orchestrating component discovers and calls the provider when needed.

| Perspective | API — Service Consumer | SPI — Service Provider |
|---|---|---|
| Primary audience | Consumer, business application, code calling the library | Author of provider/driver/plugin/adapter |
| Question | "Which function do I call?" | "Which contract must I implement to provide the function?" |
| Dependency direction | Consumer depends on the API contract | Provider depends on the SPI contract, and often related API types |
| Who decides how it executes? | Usually does not need to know the details | Provider implements the actual logic |
| Who calls whom at runtime? | Consumer calls the API | Framework/platform calls the SPI or objects created by the SPI |
| What must stay stable? | Signatures, input/output data, exceptions, semantics for the consumer | Extension points, lifecycle, registration requirements, compatibility for the provider |

**API and SPI are two *roles*, not necessarily two distinct interfaces.** A single interface can serve both as the API called by the application and as the SPI implemented by providers. In larger systems, teams often separate the API facade from the SPI so consumers do not need to know the plugin-loading mechanism.

## 2. Why Separate the Two Sides?

Suppose an application exports reports and must support multiple formats. If business code directly writes `new PdfFormatter()` or `new HtmlFormatter()`, every new format may force the application to change code, recompile, and re-release. An API/SPI design establishes a boundary:

```text
Application (consumer)
    |
    | uses API: Formatters.get("upper").format(text)
    v
Orchestration library / API facade
    |
    | discovers providers and calls SPI contract
    v
FormatterProvider (SPI)
    |
    +--> UppercaseProvider (provider A)
    +--> ...               (provider B can be added later)
```

Changing or adding a provider does not force the consumer to know implementation class names. However, "loading at runtime" **does not mean automatic hot installation**: class loading mechanisms, classpath/module path, and class loader lifecycle still determine when a new provider becomes visible.

## 3. Java 17+ Example: Consumer Calls Only API, Provider Implements SPI

Let us build a simple text-formatting service. The example puts all classes in the same compilation directory for easy execution; in a real project, the API/SPI and each provider should live in separate JARs/modules.

File structure:

```text
src/
├── demo/
│   ├── Main.java
│   ├── api/
│   │   ├── TextFormatter.java
│   │   └── Formatters.java
│   ├── spi/
│   │   └── FormatterProvider.java
│   └── provider/
│       └── UppercaseProvider.java
└── META-INF/
    └── services/
        └── demo.spi.FormatterProvider
```

### 3.1. Public API for the Consumer

File `src/demo/api/TextFormatter.java`:

```java
package demo.api;

@FunctionalInterface
public interface TextFormatter {
    String format(String input);
}
```

File `src/demo/api/Formatters.java`:

```java
package demo.api;

import demo.spi.FormatterProvider;
import java.util.ServiceLoader;

public final class Formatters {
    private Formatters() {}

    public static TextFormatter get(String id) {
        for (FormatterProvider provider : ServiceLoader.load(FormatterProvider.class)) {
            if (provider.id().equals(id)) {
                return provider.create();
            }
        }
        throw new IllegalArgumentException("Unknown format: " + id);
    }
}
```

The consumer sees `TextFormatter` and the `Formatters.get(...)` method; it does not have to instantiate or import provider classes. `Formatters` is the orchestrating class: internally it uses the SPI to select an implementation. In a real application, you need rules for handling duplicate `id`s, priority, configuration, and missing-service cases.

### 3.2. SPI for the Provider Author

File `src/demo/spi/FormatterProvider.java`:

```java
package demo.spi;

import demo.api.TextFormatter;

public interface FormatterProvider {
    String id();
    TextFormatter create();
}
```

This is the extension contract: the provider must declare an identifier and create a formatter conforming to the API. The orchestration library decides *when* to call `id()` and `create()`; the provider decides *how* to create the processing object.

File `src/demo/provider/UppercaseProvider.java`:

```java
package demo.provider;

import demo.api.TextFormatter;
import demo.spi.FormatterProvider;
import java.util.Locale;

public final class UppercaseProvider implements FormatterProvider {
    @Override
    public String id() {
        return "upper";
    }

    @Override
    public TextFormatter create() {
        return input -> input.toUpperCase(Locale.ROOT);
    }
}
```

`UppercaseProvider` **implements the SPI** while returning an object that conforms to the **API**. It uses `Locale.ROOT` so the example produces uppercase output independent of the machine's default locale.

### 3.3. Registering the Provider for `ServiceLoader`

Contents of the **extensionless** file `src/META-INF/services/demo.spi.FormatterProvider`:

```text
demo.provider.UppercaseProvider
```

The file name must match the **fully qualified name of the SPI service type**; each line in the file is the fully qualified name of a provider class. On the classpath, `ServiceLoader` looks up `META-INF/services/<fully-qualified-SPI-name>` resources. The provider class in the example is `public`, has a default public no-argument constructor, and implements the SPI.

### 3.4. Consumer and Test Run

File `src/demo/Main.java`:

```java
package demo;

import demo.api.Formatters;
import demo.api.TextFormatter;

public class Main {
    public static void main(String[] args) {
        TextFormatter formatter = Formatters.get("upper");
        System.out.println(formatter.format("Hello Java"));
    }
}
```

In **PowerShell on Windows**, from the directory containing `src`, run:

```powershell
javac -encoding UTF-8 -d out src/demo/api/TextFormatter.java src/demo/api/Formatters.java src/demo/spi/FormatterProvider.java src/demo/provider/UppercaseProvider.java src/demo/Main.java
New-Item -ItemType Directory -Force out/META-INF/services | Out-Null
Copy-Item src/META-INF/services/demo.spi.FormatterProvider out/META-INF/services/demo.spi.FormatterProvider
java -cp out demo.Main
```

On **Linux/macOS**, replace the two resource directory creation/copy commands with `mkdir -p out/META-INF/services` and `cp src/META-INF/services/demo.spi.FormatterProvider out/META-INF/services/`; the `javac` and `java` commands stay the same.

Output:

```text
HELLO JAVA
```

If you remove the registration file `out/META-INF/services/demo.spi.FormatterProvider` and run again, `ServiceLoader` does not find the provider under the classpath setup in the example; `Formatters.get("upper")` throws `IllegalArgumentException` with the message `Unknown format: upper`. This illustrates that **having the provider class on the classpath is not enough; proper registration is required**.

This example is intentionally simple: all files are compiled together for easy reproduction. When packaging JARs, place `META-INF/services/...` **inside the provider's JAR**; the consumer depends on the API, while the provider JAR is supplied in the runtime environment. When using multiple providers, check for duplicate `id`s instead of silently taking the first provider.

## 4. What Does `ServiceLoader` Do and Not Do?

`java.util.ServiceLoader<S>` is the standard utility for discovering implementations/providers of service type `S`. In the example, the steps are:

1. The library calls `ServiceLoader.load(FormatterProvider.class)`.
2. The loading mechanism looks up available provider declarations via the corresponding class loader/module.
3. During iteration, providers are loaded and instantiated according to `ServiceLoader`'s rules.
4. The library uses the SPI contract to select a provider and supply an API object to the consumer.

Key characteristics to understand clearly:

- **Discovery and instantiation are usually lazy.** Calling `load(...)` does not mean all providers have been instantiated immediately. Do not attach critical side effects to the assumption that "all providers have already run".
- **Discovered/created providers are cached.** `reload()` clears the cache of *that `ServiceLoader` instance* to re-run discovery. It does not automatically load new JARs onto the classpath, create new class loaders, or replace already-loaded Java classes.
- **Visibility scope depends on the class loader/module layer.** `ServiceLoader.load(S.class)` uses the calling thread's context class loader under normal loading; there is an overload taking an explicit class loader. Check where the provider JAR is placed if the service is not found at runtime.
- **Do not rely on provider ordering** unless the application itself has controlled selection rules. Select by `id`, configuration, or defined priority and handle duplicates.
- **A faulty provider can cause discovery to fail** (for example `ServiceConfigurationError` due to a wrong class name, incompatible type, or instantiation failure). Log the cause clearly and decide whether to fail fast or fall back according to business requirements.
- **`ServiceLoader` is not designed to be shared arbitrarily across multiple threads.** For long-lived use in a multithreaded environment, design service initialization, synchronization, and caching in the orchestration layer.

`ServiceLoader` is one option for implementing an SPI, **not the sole definition of an SPI**. Frameworks can register providers using configuration, dependency injection, a factory registry, or a custom plugin mechanism.

### How Does the Classpath Differ from the Java Module System (JPMS)?

In the **classpath** example, the `META-INF/services/...` file is the standard registration method. With **named modules** on the module path, a provider can be declared using `provides ... with ...`, while the module performing the lookup declares `uses ...`. Conceptual example illustrating the relationship (not two complete modules that can be compiled standalone from this snippet alone):

```java
// module-info.java of the module containing the API/SPI and ServiceLoader-calling code
module formatter.core {
    exports demo.api;
    exports demo.spi;
    uses demo.spi.FormatterProvider;
}

// module-info.java of the provider module (in another project/module)
module formatter.upper {
    requires formatter.core;
    provides demo.spi.FormatterProvider with demo.provider.UppercaseProvider;
}
```

In JPMS, you must configure the module path and appropriate module/layer resolution. Do not use both registration methods simultaneously just because "more is better"; determine whether the application runs on the classpath or module path and test that specific mechanism.

## 5. API and SPI in Familiar Libraries

**JDBC** is a classic example. The application uses the `DriverManager.getConnection(...)`, `Connection`, `PreparedStatement`, and `ResultSet` APIs to access databases. Driver vendors implement `java.sql.Driver` and register the driver so the runtime can find it. The application does not have to write communication logic for each database management system. Note that `java.sql.Driver` is the SPI extension point; consumers normally do not instantiate drivers directly by concrete class name.

Similar patterns appear across the Java ecosystem: logging libraries use different implementations, serializer systems can register codecs, and web frameworks have adapters for individual technologies. **Not every library in these categories uses `ServiceLoader`**; inspect the actual contract and registration mechanism of each library.

## 6. Designing the Contract for the Right Side

When writing an **API for consumers**:

- Name operations after business needs: `format`, `save`, `send`, rather than exposing how providers are discovered or concrete class names.
- Specify results, errors, `null` handling, thread safety, and object lifecycles that callers need to know.
- Keep the consumer's dependency on the contract stable; avoid forcing consumers to import `spi`/`internal` packages.

When writing an **SPI for providers**:

- Clearly state the semantics of each method, validity conditions, call order/frequency, thread safety, resource management, and closing methods when needed.
- Document the registration mechanism, constructor/factory requirements, loading behavior, and error reporting for invalid providers.
- Design versioning intentionally: adding an abstract method to an existing SPI can make older providers incompatible; consider default methods, a new interface, or a new contract version when appropriate.
- Separate contract from implementation. Providers should not depend on unexposed internal details of the framework.

In the orchestration layer, clearly define how to choose among multiple providers, handle missing providers, duplicate identifiers, provider initialization errors, and fallback policies. Do not catch all errors and silently ignore them: the system may behave incorrectly without anyone noticing.

## 7. Common Misconceptions

| Misconception | Correct Understanding |
|---|---|
| "API is an interface; SPI is a class." | Both are contract roles. SPI is often an interface/abstract class; an API can consist of multiple types and methods. |
| "Simply writing `implements` means using SPI." | It is only SPI in the extensibility sense when the system publishes an extension point and has a mechanism to accept/invoke providers under a contract. |
| "If the provider JAR is on the machine, `ServiceLoader` finds it automatically." | It must be within the appropriate loading scope, properly registered, and aligned with the classpath/JPMS mechanism. |
| "Calling `reload()` replaces the running provider with a new JAR." | `reload()` refreshes the loader's discovery cache; it does not perform hot-swapping or replace class loaders. |
| "An SPI only needs to compile to be safely compatible." | It must also conform to runtime semantics, lifecycle, exceptions, and contract version. |
| "Dynamically loaded plugins are always safe because they sit behind an SPI." | SPI is an architectural boundary, not a security sandbox. Providers still run with the JVM process's privileges unless an isolated architecture is used. |

## 8. How to Verify Your Understanding

1. **Swap providers:** Create `LowercaseProvider` with `id()` returning `"lower"`, returning a formatter that uses `toLowerCase(Locale.ROOT)`; add that class to `META-INF/services/demo.spi.FormatterProvider`. The consumer only needs to change the `"upper"` argument to `"lower"` to select the behavior.
2. **Missing provider:** Remove the provider registration and observe the error branch. Then decide whether the product requirement is to report an error, use a default configuration, or fall back.
3. **Duplicate providers:** Register two providers with the same `id`. Ask: which one does the example code pick? Why should a real design detect duplicates or have explicit priority rules?
4. **Mark the boundaries:** In the code above, `Main` is the consumer; `Formatters` and `TextFormatter` form the API; `FormatterProvider` is the SPI; `UppercaseProvider` is the provider; the `META-INF/services` file is registration metadata.

**Ask yourself when encountering a new library:** "What surface does business code call?" is the API question. "To write a replacement implementation, which contract must I implement and register?" is the SPI question. Understanding both sides is the foundation for designing Java services capable of swapping providers with minimal changes to consumer code.
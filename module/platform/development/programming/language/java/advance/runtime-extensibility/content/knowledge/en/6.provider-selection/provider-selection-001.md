# Selecting Providers by Identifier, Capability Support, and Explicit Configuration

When a Java application has multiple providers for the same service, **discovering a provider does not mean selecting the right provider**. `ServiceLoader` helps find registered implementations, but it does not decide on the application's behalf which provider fits the current request. Selection should be based on a clear policy: **identifier**, **capability support**, and **explicit configuration**.

This lesson walks from design requirements to a runnable Java 17 program: it has two greeting providers, a provider resolver, and three verification modes. Notably, both providers support Vietnamese, making this a practical example of the **multiple matching providers** scenario.

## 1. From Discovery to Selection: Two Distinct Steps

Consider an application that allows installing multiple implementations of `GreetingProvider`:

```text
                     Runtime classpath
         +----------------+----------------+
         |                |                |
  CasualProvider    FormalProvider   Other providers...
         |                |
         +--------+-------+
                  |
    ServiceLoader<GreetingProvider>
                  |
                  v
       List of available providers
                  |
                  v
          ProviderResolver
         /        |         \
  identifier  supports()  configuration
         \        |         /
                  v
         Selected provider
                  |
                  v
          greet(request)
```

We need to distinguish:

- **Discovery:** identifying present and validly registered providers. On the classpath, `ServiceLoader` uses the `META-INF/services/<fully-qualified-SPI-name>` resource.
- **Selection:** determining which provider should handle **a specific request**. This belongs to the application's policy and is not resolved automatically by `ServiceLoader`.
- **Invocation:** once selected, using the chosen provider to process the request; business errors from the provider must be handled according to the contract rather than arbitrarily failing over to another provider.

If you write `ServiceLoader.load(SPI.class).iterator().next()` to grab the “best provider”, you are inadvertently equating discovery order with priority order. **There is no general guarantee that the first provider is the desired provider.** When JARs, class loaders, or packaging change, behavior may change accordingly.

## 2. Three Selection Criteria

### 2.1. By Stable Identifier (`providerId`)

Each provider publishes a unique identifier, such as `casual`, `formal`, `postgres`, `s3`, or `local`. The application stores the identifier in configuration and then looks up the matching provider.

A good identifier should be:

- Stable enough not to change arbitrarily between releases.
- Distinct from class names and JAR locations, since implementation details can change.
- Subject to a uniqueness rule within **the scope of the registry in use**; duplicate detection must report an error or have a documented conflict-resolution mechanism.
- Following a clear naming convention (for example, lowercase without spaces). The example below uses `casual` and `formal`.

**When to use?** When operators or application configuration require a specific provider, such as requiring a particular driver/adapter. With an exact-selection configuration, **a missing provider or a provider that does not support the request must fail with an error**; silently switching to another provider can alter behavior or violate operational requirements.

### 2.2. By Capability Support (`supports(request)`)

A provider may support a subset of cases rather than every request. The contract can advertise a fixed set of capabilities such as MIME types, versions, algorithms, or protocols, or use a predicate:

```java
boolean supports(GreetingRequest request);
```

This allows the system to filter out providers that do not satisfy the request. For example, one provider supports `en` and `vi`, while another supports only `vi`.

However, **filtering does not equate to unique selection**:

| Supporting providers | Reasonable policy |
|---:|---|
| 0 | Report no matching provider; fall back only if explicitly defined by the product |
| 1 | Select the single provider |
| 2 or more | Apply priority configuration, a published rule, or report ambiguity |

A good `supports` method should be fast, have minimal side effects, and be consistent with actual capability when invoked to process the request. If capability depends on external state (servers, licenses, quotas), a check result at selection time may already be stale at execution time; runtime errors must be handled separately.

### 2.3. By Explicit Configuration

Configuration can come from JVM arguments, `.properties` files, environment variables, or a framework's configuration system. Two meanings must be kept separate:

- **Mandatory assignment (hard pin):** `app.provider=formal` means `formal` must be used. If missing or incompatible, fail.
- **Preference when multiple choices exist (tie-break preference):** `app.prefer=formal` means when multiple providers support the request, prefer `formal` if it is in the matching set. If only one provider matches, use that provider. If multiple providers match and the preference configuration does not match, this example reports a clear error.

This is **a policy designed for the example**; Java does not interpret these two properties by default. A real application may choose different names, but it must document the precedence order and whether each option is mandatory.

## 3. Conflict-Resolution Policy Before Writing Code

We apply the rules in exact order:

1. Load the provider list; check for blank or duplicate IDs. If there are no providers, report an error.
2. If `app.provider` is not `auto`, look up **only the exact specified ID** and then check `supports(request)`. If either fails, report an error; do not fall back.
3. If `app.provider=auto`, filter providers that return `true` from `supports(request)`.
4. If no provider matches, report an error.
5. If only one provider matches, select it.
6. If multiple providers match, use `app.prefer` to resolve. If there is no configuration or the preference does not match, report an ambiguity/invalid-preference error.
7. When `app.provider` already specifies an exact provider, **forbid also** declaring `app.prefer` to prevent self-contradictory configuration.

This policy intentionally does not default to class name, JAR location, or `ServiceLoader` order. If a product truly wants to prioritize by score/cost/reliability, design scoring criteria and tie-breaking rules; do not use discovery order as an implicit priority.

## 4. Java 17 Example: SPI and Two Providers with Overlapping Capabilities

Sample directory:

```text
provider-selection-demo/
├── src/
│   └── demo/
│       ├── GreetingRequest.java
│       ├── GreetingProvider.java
│       ├── CasualProvider.java
│       ├── FormalProvider.java
│       ├── ProviderResolver.java
│       └── Main.java
└── resources/
    └── META-INF/
        └── services/
            └── demo.GreetingProvider
```

The sample runs on the **classpath** without using `module-info.java`. Both providers are placed in the same source directory for easy reproduction; in a real deployment, each provider can be packaged into an independent JAR. The resolver and consumer still depend only on the SPI.

### 4.1. Request Type

File `src/demo/GreetingRequest.java`:

```java
package demo;

public record GreetingRequest(String language, String name) {
    public GreetingRequest {
        if (language == null || language.isBlank()) {
            throw new IllegalArgumentException("language is required");
        }
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("name is required");
        }
    }
}
```

`record` (Java 16+) makes input data explicit. The example only accepts simple language codes `en` and `vi`; in a real multilingual product, agree on a language-code normalization policy (for example `vi-VN`) before capability filtering.

### 4.2. SPI Contract

File `src/demo/GreetingProvider.java`:

```java
package demo;

public interface GreetingProvider {
    String id();

    boolean supports(GreetingRequest request);

    String greet(GreetingRequest request);
}
```

`id()` provides the selection identifier. `supports()` checks request-handling capability. `greet()` is the behavior the end consumer needs.

Semantic contract for the example: `id()` is non-`null` and non-blank; `supports()` causes no side effects and returns a result consistent with whether `greet()` can execute; `greet()` is only called when the request is supported. Java does not automatically enforce these semantics; they must be tested and specified for provider authors.

### 4.3. Casual-Tone Provider

File `src/demo/CasualProvider.java`:

```java
package demo;

public final class CasualProvider implements GreetingProvider {
    @Override
    public String id() {
        return "casual";
    }

    @Override
    public boolean supports(GreetingRequest request) {
        return "en".equals(request.language())
                || "vi".equals(request.language());
    }

    @Override
    public String greet(GreetingRequest request) {
        if (!supports(request)) {
            throw new IllegalArgumentException("Unsupported language");
        }

        if ("vi".equals(request.language())) {
            return "Chào " + request.name() + "!";
        }
        return "Hello, " + request.name() + "!";
    }
}
```

`CasualProvider` supports `en` and `vi`.

### 4.4. Formal-Tone Provider

File `src/demo/FormalProvider.java`:

```java
package demo;

public final class FormalProvider implements GreetingProvider {
    @Override
    public String id() {
        return "formal";
    }

    @Override
    public boolean supports(GreetingRequest request) {
        return "vi".equals(request.language());
    }

    @Override
    public String greet(GreetingRequest request) {
        if (!supports(request)) {
            throw new IllegalArgumentException("Unsupported language");
        }
        return "Kính chào " + request.name() + ".";
    }
}
```

`FormalProvider` supports only `vi`. Both `public` classes have the default public no-argument constructor, matching the provider instantiation requirement for classpath registration used in the example.

Thus:

| Request language | Supporting providers | Meaning |
|---|---|---|
| `en` | `casual` | Only one candidate |
| `vi` | `casual`, `formal` | Two candidates, decision required |
| `fr` | None | Cannot validly auto-select |

### 4.5. Registering Providers for `ServiceLoader`

Contents of `resources/META-INF/services/demo.GreetingProvider`:

```text
demo.CasualProvider
demo.FormalProvider
```

The file name is the fully qualified name of the **service type**. Each line is the fully qualified name of **one provider class**; this is how multiple providers are registered in the same resource. The file must be placed in `out/META-INF/services/demo.GreetingProvider` when running on the classpath.

When packaging multiple JARs, each provider JAR can contain its own file of the same name listing only the providers supplied by that JAR. `ServiceLoader` can discover multiple service resources of the same name from visible classpath elements; there is no need to write a single provider list into the consumer.

## 5. Writing a Resolver with an Explicit Decision Policy

File `src/demo/ProviderResolver.java`:

```java
package demo;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.ServiceLoader;
import java.util.TreeMap;
import java.util.stream.Collectors;

public final class ProviderResolver {
    private final Map<String, GreetingProvider> byId = new TreeMap<>();

    public ProviderResolver() {
        for (GreetingProvider provider
                : ServiceLoader.load(GreetingProvider.class)) {
            String id = provider.id();

            if (id == null || id.isBlank()) {
                throw new IllegalStateException("Provider id is blank");
            }
            if (byId.putIfAbsent(id, provider) != null) {
                throw new IllegalStateException("Duplicate provider id: " + id);
            }
        }

        if (byId.isEmpty()) {
            throw new IllegalStateException("No providers registered");
        }
    }

    public GreetingProvider select(
            GreetingRequest request, String providerId, String preferredId) {

        if (!"auto".equals(providerId)) {
            GreetingProvider selected = byId.get(providerId);

            if (selected == null) {
                throw new IllegalArgumentException(
                        "Unknown provider: " + providerId);
            }
            if (!selected.supports(request)) {
                throw new IllegalArgumentException(
                        "Provider " + providerId
                                + " does not support " + request.language());
            }
            return selected;
        }

        List<GreetingProvider> matches = new ArrayList<>();

        for (GreetingProvider provider : byId.values()) {
            if (provider.supports(request)) {
                matches.add(provider);
            }
        }

        if (matches.isEmpty()) {
            throw new IllegalStateException(
                    "No provider supports language: " + request.language());
        }
        if (matches.size() == 1) {
            return matches.get(0);
        }

        if (preferredId != null && !preferredId.isBlank()) {
            for (GreetingProvider provider : matches) {
                if (preferredId.equals(provider.id())) {
                    return provider;
                }
            }
            throw new IllegalArgumentException(
                    "Preferred provider " + preferredId
                            + " does not support " + request.language());
        }

        String ids = matches.stream()
                .map(GreetingProvider::id)
                .collect(Collectors.joining(", "));
        throw new IllegalStateException(
                "Ambiguous providers for language "
                        + request.language() + ": " + ids);
    }
}
```

Key points of the resolver:

- The `TreeMap` registry stores entries by identifier so it has **a stable order for presenting errors**. We do not rely on the order returned by `ServiceLoader`.
- `putIfAbsent` turns **duplicate IDs into an explicit configuration error**, instead of letting a later-registered provider silently override an earlier one.
- The explicit-ID branch checks `supports()`; knowing the right ID is not enough to conclude that the provider can handle an arbitrary request.
- The `auto` branch inspects every provider, so no candidate is missed just because it appears after another provider in discovery order.
- When two providers support the same request, lacking a tie-breaking rule is treated as **ambiguous**, not an opportunity to pick the first provider.
- `preferredId` is only a **tie-breaker rule** in this example: it is only considered when more than one provider matches. If only one provider matches, the resolver uses that single provider, even if `app.prefer` is set to a different provider. If you want mandatory selection, use `app.provider`.

In a real system, calling `id()` and `supports()` may throw exceptions or be very expensive. If product requirements need handling individual faulty providers, design an error policy with logging/metrics and clear error categorization; do not `catch (Exception)` and silently drop a provider to produce an apparently valid result.

## 6. Consumer Receiving Explicit Configuration from the JVM

File `src/demo/Main.java`:

```java
package demo;

public final class Main {
    public static void main(String[] args) {
        String language = System.getProperty("app.language", "en");
        String providerId = System.getProperty("app.provider", "auto");
        String preferredId = System.getProperty("app.prefer", "");

        if (providerId.isBlank()) {
            throw new IllegalArgumentException("app.provider is blank");
        }
        if (!"auto".equals(providerId) && !preferredId.isBlank()) {
            throw new IllegalArgumentException(
                    "Use either app.provider or app.prefer");
        }

        GreetingRequest request = new GreetingRequest(language, "Linh");
        ProviderResolver resolver = new ProviderResolver();

        GreetingProvider provider =
                resolver.select(request, providerId, preferredId);

        System.out.println("Selected: " + provider.id());
        System.out.println(provider.greet(request));
    }
}
```

`Main` neither imports nor instantiates `CasualProvider` or `FormalProvider`. When running, the application can pass JVM system properties:

- `-Dapp.language=en|vi`: requested language. Default `en`.
- `-Dapp.provider=<id>`: mandatory provider assignment. Default `auto`, meaning select by capability.
- `-Dapp.prefer=<id>`: preference when multiple providers match. Default empty.

**The `-D...` syntax must appear before the `demo.Main` class name** so the JVM picks up the properties. These parameters are provided at **process startup**; modifying an external configuration file does not automatically reload the resolver held in memory.

If using configuration files or environment variables, the startup layer should normalize values into the same `language/providerId/preferredId` trio, determine which source takes higher precedence, and log the effective configuration. This example uses system properties for easy reproduction and does not read files or environment variables by default.

## 7. Compiling and Running on Java 17+

Stand inside the `provider-selection-demo` directory containing the two directories `src` and `resources`. JDK 17+ and a Unicode-capable terminal are required to display Vietnamese text properly.

### Windows PowerShell

```powershell
New-Item -ItemType Directory -Force out/META-INF/services | Out-Null

javac -encoding UTF-8 -d out src/demo/GreetingRequest.java src/demo/GreetingProvider.java src/demo/CasualProvider.java src/demo/FormalProvider.java src/demo/ProviderResolver.java src/demo/Main.java

Copy-Item resources/META-INF/services/demo.GreetingProvider out/META-INF/services/demo.GreetingProvider

java -cp out demo.Main
```

Stdout output:

```text
Selected: casual
Hello, Linh!
```

### Linux/macOS

```bash
mkdir -p out/META-INF/services

javac -encoding UTF-8 -d out src/demo/*.java

cp resources/META-INF/services/demo.GreetingProvider out/META-INF/services/demo.GreetingProvider

java -cp out demo.Main
```

Stdout output is also:

```text
Selected: casual
Hello, Linh!
```

Since `language=en`, only `CasualProvider` supports it, so automatic selection succeeds without a preference configuration.

**Classpath verification note:** compiling only `.class` files is not enough. If you forget to copy `resources/META-INF/services/demo.GreetingProvider` into `out`, `ServiceLoader` will not discover any providers from this example and `ProviderResolver`'s constructor will throw `IllegalStateException: No providers registered` on stderr (along with a stack trace). When running in JARs, the registration resource must reside inside the provider JAR and the necessary JARs must be visible from the active class loader.

## 8. Verifying Each Selection Strategy

The following commands reuse the already compiled code. The `java -cp out` command runs on Windows, Linux, and macOS because the classpath has only one element `out`.

### Case A: selecting by mandatory identifier

```bash
java -Dapp.language=vi -Dapp.provider=casual -cp out demo.Main
```

Stdout:

```text
Selected: casual
Chào Linh!
```

Even though `FormalProvider` also supports `vi`, the configuration **pins** `casual`, so the resolver selects the exact identifier. Load order is not used.

### Case B: selecting by single capability

```bash
java -Dapp.language=en -cp out demo.Main
```

Stdout:

```text
Selected: casual
Hello, Linh!
```

The resolver filters by `supports()`; `FormalProvider` does not support `en`, so only `casual` remains.

### Case C: overlapping capabilities with preference configuration

```bash
java -Dapp.language=vi -Dapp.prefer=formal -cp out demo.Main
```

Stdout:

```text
Selected: formal
Kính chào Linh.
```

Both providers support `vi`; `app.prefer=formal` is an intentional tie-breaker rule, so the result is deterministic.

### Case D: overlapping capabilities without a preference policy

```bash
java -Dapp.language=vi -cp out demo.Main
```

The program fails with `IllegalStateException`. The exception message on stderr is:

```text
Ambiguous providers for language vi: casual, formal
```

The order of the two IDs in the message is stable because the registry is a `TreeMap`. The line above **is not stdout**: the program does not reach the two `println` calls in `Main`; Java also prints the stack trace on stderr.

### Case E: specifying a provider that does not support the request

```bash
java -Dapp.language=en -Dapp.provider=formal -cp out demo.Main
```

Exception message of `IllegalArgumentException`:

```text
Provider formal does not support en
```

It does not automatically switch to `casual`. With mandatory selection, silent fallback defeats the purpose of the configuration.

### Case F: no provider supports the request

```bash
java -Dapp.language=fr -cp out demo.Main
```

Exception message of `IllegalStateException`:

```text
No provider supports language: fr
```

This is the result of the capability filter; it **differs from** the case where no registered providers are found.

### Case G: configured ID does not exist

```bash
java -Dapp.language=vi -Dapp.provider=missing -cp out demo.Main
```

Exception message of `IllegalArgumentException`:

```text
Unknown provider: missing
```

The resolver should not turn a typo in configuration into a random result.

### Case H: contradictory configuration

```bash
java -Dapp.language=vi -Dapp.provider=casual -Dapp.prefer=formal -cp out demo.Main
```

Exception message of `IllegalArgumentException`:

```text
Use either app.provider or app.prefer
```

Failing immediately at the configuration layer prevents cases where different people interpret the precedence of the two options differently.

## 9. Selecting Configuration in Production Systems

A controllable selection flow can be expressed as:

```text
Read and validate configuration
        |
        v
Mandatory providerId present?
   | Yes                    | No (auto)
   v                        v
Look up ID in registry    Filter with supports(request)
   |                        |
   +--> Not found? Error    +--> 0 candidates? Error
   |                        +--> 1 candidate? Select
   +--> Unsupported? Error  +--> N candidates? Check preference
   |                                  |
   v                                  +--> Valid preference? Select
Select exact match                    +--> No? Ambiguity error
```

When mapping to external application configuration, distinguish:

| Operational scenario | Representation | Desired behavior |
|---|---|---|
| Policy requiring a specific provider | `providerId = "formal"` | Fail fast if missing or unsupported |
| Automatic selection because only one implementation supports it | `providerId = "auto"` | Select only when filtering yields a single candidate |
| Multiple implementations support it | `providerId = "auto"`, `preferredId = "formal"` | Select the preferred candidate if it supports the request |
| Ambiguous results unacceptable | `providerId = "auto"` and no preference | Report an error instead of depending on order |
| Fallback to alternative allowed | **Separate** fallback configuration | Attempt fallback only when the error type qualifies and a published rule exists |

Systems with multiple environments (local, staging, production) must clearly log the **effective configuration** and the selected provider identifier. You may log IDs, candidate counts, and selection reasons, but do not log secrets such as tokens, passwords, or full sensitive payloads.

If using dependency injection (for example, an IoC framework), the framework may provide different mechanisms for naming, qualifiers, or bean priority. Even though the mechanism differs, the core problem remains the same: validating candidate eligibility, arbitrating among multiple implementations, and ensuring explicit configuration is respected.

## 10. Hard Parts in Large Systems

### 10.1. Duplicate Identifiers Do Not Equal Overlapping Capabilities

Two providers with the same `id()` represent an **identifier conflict**: the registry cannot know which class the `provider=formal` configuration is meant to point to. Two providers both returning `supports(request)=true` are simply **overlapping capabilities**: this can be valid and resolved by the selection policy.

Do not conflate the two kinds of conflict. The resolver in the example fails early on duplicate IDs, but only reports ambiguity when multiple candidates remain after the capability-filtering step.

### 10.2. When to Use Scores or Priority Levels?

A product may want to consider cost, latency, reachability, version, deployment region, or priority order. In that case, the SPI can be extended to return metadata or a candidate evaluator can be written.

However, it must be decided **upfront**:

- Which criteria are hard constraints (providers that fail them must be excluded)?
- Which criteria are used for ranking and in what comparison order?
- How are ties broken? Is using ID allowed as a secondary rule or must ambiguity be reported?
- Do scores change over time; how long should selections be cached?

Do not replace this with `findFirst()` and call it “highest priority”. `ServiceLoader`'s discovery order is not a quality weight.

### 10.3. Guaranteeing the Contract Between `supports()` and Execution

`supports()` is only a self-declared check by the provider and **does not prove** the request will certainly succeed. Execution can still fail due to network, files, quotas, permissions, or state changes. Specify exceptions, retries, and fallbacks by error type.

Fallback is particularly dangerous when an action has side effects: if the first provider already sent a notification but returned a late error, trying a second provider can send a duplicate. Idempotency or outcome confirmation mechanisms must be designed at the business level, not delegated by default to the SPI.

### 10.4. SPI Versioning and Class Loader Dependencies

If a provider is compiled against a new SPI version while the application runs with an old SPI, you may encounter class-loading errors, `AbstractMethodError`, or semantic violations. Additionally, two different class loaders can load two copies of the same interface name, causing a class to no longer be considered a subtype of the active service type.

You must align the contract version and class loader of the service scope; validate provider metadata at startup. Do not assume that mere presence on the classpath guarantees compatibility.

### 10.5. Discovery Timing and Selection Lifecycle

`ServiceLoader.load(...)` creates a discoverer with a cache of already-iterated providers. It typically loads/instantiates lazily during iteration. `reload()` only refreshes that `ServiceLoader` instance's cache; **it does not automatically add new JARs to the classpath, destroy instances already held by consumers, or hot-swap classes**.

A registry created at startup like `ProviderResolver` in the example is a **snapshot of the providers it discovered**. If the system needs dynamic plugins or hot reload, you must design a dedicated class loader/module layer, instance lifecycle, safe registry updates, and in-flight request handling. `ServiceLoader` does not automatically handle this entire process.

`ServiceLoader` is also not guaranteed to be thread-safe when shared and manipulated directly from multiple threads. For multithreaded applications, you can initialize the registry once, publish it safely, and ensure selected providers satisfy concurrency contracts.

### 10.6. Provider and Configuration Security

Providers typically run with the privileges of the Java application. SPI is a code design boundary, **not a sandbox**. You must control JAR/provider sources, dependencies, and execution permissions; do not allow untrusted users to pick a dangerous provider merely through configuration parameters.

## 11. Common Mistakes and How to Avoid Them

| Mistake | Consequence | Solution |
|---|---|---|
| Choosing `iterator().next()` | Depends on undefined discovery order as policy | Use IDs, capability filtering, or explicit configuration |
| Letting providers assign IDs without duplicate checks | May select the wrong implementation | Build a registry that checks ID uniqueness |
| Checking only ID while skipping `supports` | Calls a provider that cannot handle the request | Check capability even when ID is specified |
| Automatically falling back when mandatory config is wrong | Diverges from operational requirements, hard to observe | Fail and state the required ID/capability |
| All providers support a request, yet picking the first one | Ambiguity is hidden | Have a priority rule or report an error |
| Failing to register `META-INF/services` | `ServiceLoader` fails to find provider classes | Verify resources in the classpath/JAR |
| Changing classpath while JVM runs then calling `reload()` | New providers do not appear as expected | Design a separate dynamic loading mechanism or restart |
| `supports()` mutates state | Filtering results become unpredictable | Use a predicate with stable semantics and minimal side effects |
| Catching all provider errors and ignoring them | Hides configuration and software bugs | Categorize errors, log, and enforce a transparent handling policy |

## 12. Self-Check Exercises

1. **Add a provider with ID `neutral`** supporting `en` and `fr`. Determine the output or error for commands using `app.language=en` and `fr` before and after configuring `app.prefer=neutral`.
2. **Create a duplicate ID:** change `FormalProvider.id()` to `"casual"`. Observe which error `ProviderResolver`'s constructor fails with. Why shouldn't you wait until a specific request occurs to detect this?
3. **Verify hard pin vs. preference distinction:** explain the difference between `-Dapp.language=en -Dapp.provider=formal` and `-Dapp.language=en -Dapp.prefer=formal` under the current policy. One command errors while the other selects the single candidate; does this match the documented semantics?
4. **Reduce configuration mistakes:** add a step to print the list of IDs and advertised capabilities at startup, then check whether printing that information exposes any configuration secrets.
5. **Design a separate fallback:** suppose the selected provider calls an external API and times out. Build a retry/fallback policy solely for read operations, while explaining the risks of repeating write operations.

When implementing a Java extension point, keep the boundary clear: **`ServiceLoader` discovers providers; the application defines the selection policy; providers fulfill the contract**. Select by ID when a specific implementation is mandatory; filter by capability when requests vary per call; use preference configuration or fail intentionally when multiple providers match.
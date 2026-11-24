# Not Exposing Private Dependency Types, Internal Objects, or Plugin Exceptions Through a Java API

## 1. Goal: a stable API boundary between host and plugin

A Java extensibility system allows a **host** to select and invoke a **plugin** through a shared contract. A plugin may contain vendor SDKs, its own library versions, its own class loader, or modules in another `ModuleLayer`. If those implementation details accidentally cross the API boundary, the host is forced to know about them too. Whenever a library is swapped, a plugin changes, or a version is upgraded, you risk breaking host code and other plugins.

Counterexample:

```java
// Bad API illustrative snippet, not a complete program.
import vendor.sdk.VendorRequest;
import vendor.sdk.VendorResult;
import vendor.sdk.VendorException;

public interface BadPlugin {
    VendorResult process(VendorRequest input)
        throws VendorException;
}
```

That contract creates three direct problems:

1. **Private dependency type leakage:** clients must know `VendorRequest` and `VendorResult` just to compile/call. Changing SDKs can force rewriting the host.
2. **Internal object leakage:** `VendorResult` may carry caches, mutable models, sessions, callbacks, or references to a class loader, causing the host to inadvertently retain plugin-owned state.
3. **Exception leakage:** the host must catch `VendorException`; its message/cause/stack trace can contain internal paths, endpoints, or sensitive data, coupling clients to vendor details.

**Design principle:** the public API is owned by the **host or `shared-api` module**, using only **stable shared types** and appropriate JDK types. The plugin uses an *adapter* to translate between the shared contract and its implementation-specific SDK. Vendor exceptions are handled inside the adapter and mapped to **shared contract errors**.

```text
                     SHARED API BOUNDARY
                ┌─────────────────────────────┐
   Host ────────►│ Request / Result / ErrorCode │◄──── Plugin Adapter
                │ public Plugin interface      │          │
                └─────────────────────────────┘          ▼
                        ▲                          Private SDK / JAR
                        │                          - vendor request/model
                        │                          - vendor exception
                        └── only DTOs, shared error codes ─┘
```

Sign of success: **the host compiles with only the shared API and JDK, without needing the vendor JAR**. When a plugin swaps vendor SDKs while preserving API semantics, host code does not have to change.

## 2. Places where dependency types commonly leak

### 2.1. Public/protected signatures

Audit the entire API surface, not just a method's return type:

```java
// All are COUNTEREXAMPLES; Vendor* types are illustrative only.
VendorResult process(VendorRequest input);

List<VendorResult> processAll(List<VendorRequest> inputs);

Optional<VendorSession> openSession(String id);

CompletionStage<VendorResult> processAsync(String input);

void subscribe(Consumer<VendorEvent> listener);

Supplier<? extends VendorSession> newSessionFactory();

<T extends VendorRecord> T map(T source);
```

These patterns also leak through **generic arguments and bounds**. Java type erasure does not remove what the compiler, source clients, and reflection APIs see in generic signatures. Thus, `List<VendorResult>` does not automatically become a stable contract merely because its runtime descriptor is `List`.

Other places to audit: public/protected constructors, fields, getters/setters, record components, annotation types, type parameters, interface default methods, factory return types, callback event types, and public methods on API classes.

**Verification rule:** create a sample application depending only on `shared-api.jar` on the compile classpath; if the compiler asks for `vendor.jar` to use an interface/DTO, a dependency has leaked.

### 2.2. Returning `Object` does not truly hide internal objects

Counterexample:

```java
// Non-standalone illustrative code.
Object execute(Object request);

Map<String, Object> getMetadata();

Object getInternalSession();
```

If the underlying object is actually `vendor.sdk.VendorResult`, the host eventually still has to cast, reflect on, or forward a private object. That also introduces class loader, data ownership, and lifetime risks that the compiler cannot detect.

Nor should you wrap a vendor object inside a shared DTO with an `Object details` field; the declared outer type says nothing about the actual payload. You must audit the **entire object graph**, including elements inside collections, optional values, callback captures, and async completion results.

`Map<String,String>` may fit if the data structure is genuinely a schema-defined key-value map, yet avoid overusing `Map<String,Object>` as an excuse to skip designing typed DTOs. A strong API needs **explicit data semantics**, not vague generic types.

### 2.3. Leakage through exceptions or callbacks

Even an interface without a `throws` clause can let vendor runtime exceptions escape. Callbacks like `Consumer<Throwable>` can also send raw private exceptions to the host. `CompletionStage<Result>` can complete exceptionally with a `CompletionException` wrapping a vendor failure.

Certain types should never cross the boundary simply because the host may retain them long-term: a plugin's `Class<?>`, `ClassLoader`, `MethodHandle`, `Throwable` whose cause is a private exception, internally owned streams/sessions, threads, or callback lambdas bound to a plugin instance. They both leak details and can prevent old class loaders from being garbage-collected after a plugin stops.

## 3. How should a shared API be designed?

### 3.1. Contain only the shared contract

Clean interface example:

```java
package com.example.api;

public interface TextPlugin {
    String id();
    TextResult convert(TextRequest request) throws PluginFailure;
}
```

Shared types can be:

```java
// Illustrative: split public types into separate files in real code.
public record TextRequest(String requestId, String text) {}

public record TextResult(String requestId, String text) {}

public enum FailureCode {
    INVALID_INPUT,
    DEPENDENCY_FAILURE,
    INTERNAL_FAILURE
}
```

These two snippets only aid in reading the contract and are not a complete file set. Section 8 provides a **runnable Java 17+ example** with proper packages and filenames.

**Required characteristics:** contract types are jointly owned, semantics are clear, no vendor models appear in fields, and no plugin-owned sessions/connections are returned. When a plugin upgrades versions, the host can verify compatibility without knowing which vendor sits underneath.

### 3.2. Adapter/anti-corruption layer

```text
 Host TextRequest
         │
         ▼
  Plugin Adapter
  - validate public fields
  - map to private VendorRequest
         │
         ▼
  Private Vendor SDK
  - VendorResponse
  - VendorException
         │
         ▼
  Plugin Adapter
  - map VendorResponse -> TextResult
  - map VendorException -> PluginFailure
         │
         ▼
 Host TextResult or FailureCode
```

**Data conversion** is a real translation step, not just casting or wrapping objects:

- Extract only fields required by the contract, dropping implementation-specific data.
- Convert units, encodings, timezones, and nullable fields per the shared definition.
- Validate value ranges, data sizes, and input/output schemas.
- Copy data needing ownership separation instead of returning references to internal caches.
- Keep vendor dependencies out of public exceptions, DTOs, and events.

The adapter is also the ideal place for version/capability compatibility: the plugin can swap algorithms or vendor SDKs while keeping the contract unchanged.

### 3.3. Records, immutable DTOs, and ownership

Java records describe data concisely, yet **a record is only shallowly immutable** when a component references a mutable object.

```java
// Counterexample: items could be a mutable list owned by the plugin.
public record BadResult(java.util.List<String> items) {}
```

Design with defensive copying:

```java
import java.util.List;

public record GoodResult(List<String> items) {
    public GoodResult {
        items = List.copyOf(items);
    }
}
```

This is a standalone code sample for `GoodResult.java`. `List.copyOf` produces an unmodifiable list and rejects null elements, yet **does not deep-copy** mutable elements. Copy `byte[]` arrays; for `ByteBuffer`, a read-only view does not guarantee backing storage is not mutated through another alias.

If an API must support streaming/handles, explicitly define lifetime, who closes the stream/handle, who handles cancellation, whether the object stays valid after plugin `stop`, and how to prevent clients from pinning old class loaders. Avoid returning raw `Connection`, `VendorSession`, threads, listeners, or vendor caches.

### 3.4. Neutral-typed APIs still need semantics

| Public type | Suitability | Must be specified |
| --- | --- | --- |
| `String`, `int`, `boolean` | Usually good | Encoding, units, limits, nullability |
| Shared public record/class | Good | Versioning, schema, defensive copy |
| `List<SharedDto>` | Good when ownership is clear | Mutable elements, null handling, size |
| `Optional<SharedDto>` | Usable for returns | "Absent" vs "error" |
| `CompletionStage<SharedDto>` | Fits async APIs | Cancellation, threading, error normalization |
| `Map<String,String>` | Fits small schema-backed metadata | Key rules, validation, unknown keys |
| `VendorType` | **No** | Forces host to use private dependency |
| `Object` holding a vendor object | **No** | Loses typing, leaks runtime identity/lifecycle |
| Raw `Throwable`/`ClassLoader` | **Avoid** | Leaks implementation and pins loaders |

You do not need to force every API into primitives; clear shared DTOs are often far better than multiple `String` parameters with ambiguous meaning.

## 4. API dependencies, implementation dependencies, and class loader issues

### 4.1. Dependency graph pointing the right direction

```text
             ┌─────────────────┐
 Host ───────►│ shared-api.jar  │◄────── Plugin Adapter
             └─────────────────┘              │
                                              ▼
                                      vendor-private.jar
                                              │
                                              ▼
                                       vendor dependencies

Undesired:
 shared-api.jar ─────────► vendor-private.jar
 Host source imports ────► vendor.internal.*
 Public method types ────► VendorRequest/VendorResponse/VendorException
```

The host compiles against the shared API; the plugin compiles against the shared API **and** the vendor library. At runtime, the private dependency **must still be present** in the appropriate runtime/module/classloader. "Do not expose the dependency" does not mean "delete the dependency from runtime."

Gradle `implementation` or Maven scopes help keep build dependency graphs clean, yet build keywords **do not guarantee** a contract does not return vendor objects. Inspect both Java signatures and the runtime object graph.

### 4.2. Class identity: same name does not mean same type

In the JVM, a class's identity consists of its **binary class name and its defining class loader**.

```text
Host loader H  : com.example.api.TextPlugin
Plugin loader P: com.example.api.TextPlugin (duplicate copy)
```

Two classes with the same name loaded by different loaders can be incompatible; providers may hit `ServiceConfigurationError`, `ClassCastException`, or linkage errors when the host uses a contract with a different identity.

Best practices:

- Place the shared API in a stable loader/`ModuleLayer` referenced by both host and plugins.
- Do not let a plugin's child-first class loader "shadow" `com.example.api.*` with its own copy of the API.
- Vendor SDKs can be isolated per plugin loader or layer when multiple versions must coexist.
- Always test parent delegation and dependency resolution, not just class/package names.

**Note:** If all JARs are placed on the same classpath, `public` vendor classes may still be reachable. Omitting them from the API is an **architectural constraint**, not a security sandbox or isolation boundary.

### 4.3. JPMS `exports`, `opens`, `provides`

For named modules, descriptors can be defined as (illustrative code):

```java
module com.example.api {
    exports com.example.api;
}
```

```java
module com.example.plugin {
    requires com.example.api;
    provides com.example.api.TextPlugin
        with com.example.plugin.UpperPlugin;
}
```

Host and plugin read the same API module; the plugin does not need `exports com.example.plugin` solely to use `provides` for SPI. Vendor/implementation packages can stay unexported. `opens` enables deep reflective access and should not be applied indiscriminately to every package for framework access.

JPMS enforces **readability/accessibility** within the module model, not OS-level permission sandboxing. An untrusted plugin running inside the same JVM can still cause harm even if its packages are not exported.

### 4.4. Why hiding vendors from the API helps upgrades

If the public interface uses only `TextRequest`/`TextResult`/`PluginFailure`, a plugin can switch from vendor A to vendor B while preserving data meanings and error codes. The host requires no import/catch/cast edits. Even so, **swapping vendors still requires testing** behavior, performance, data formats, concurrency, and runtime compatibility.

If a public method changes a vendor parameter or return type, the Java descriptor may change and old clients hit `NoSuchMethodError`; if a dependent class vanishes, `NoClassDefFoundError` can occur. Generic signature changes can affect source/reflection even when erasure matches. Never equate "compiles cleanly" with "binary and behavioral compatibility."

## 5. Private exceptions must stop inside the plugin

### 5.1. Checked exceptions in signatures are coupling

Counterexample:

```java
// Non-standalone illustrative code.
public interface BadPaymentPlugin {
    Receipt charge(Order order)
        throws vendor.payment.VendorServiceException;
}
```

Callers must have the vendor exception type on hand to compile `catch` blocks. Swapping vendor SDKs can force an API change. Better:

```java
// Types in shared API; illustrative code.
public interface PaymentPlugin {
    PaymentResult charge(PaymentRequest request)
        throws PluginFailure;
}
```

`PluginFailure` is a stable checked exception of the contract and does not inherit from any vendor exception. Include a `FailureCode` so hosts/clients classify semantically instead of parsing messages.

### 5.2. Checked exceptions are not the only ones that leak

Leakage sources can occur even when a signature declares no `throws`:

- `VendorRuntimeException` or `IllegalStateException` carrying internal endpoint/table/key names.
- `CompletionException`/`ExecutionException` wrapping a vendor exception inside a future.
- `InvocationTargetException` from reflection.
- `ServiceConfigurationError` during SPI discovery.
- `NoClassDefFoundError`, `NoSuchMethodError`, `LinkageError` from runtime dependencies.
- Messages/stack traces containing API tokens, usernames, paths, SQL, or request payloads.

Categorize at the boundary:

1. **Contract failures:** the adapter constructs a shared `PluginFailure` with an explicit code.
2. **Unexpected runtime exceptions:** the host handles them at the right boundary, records redacted internal telemetry, and returns an `INTERNAL_FAILURE` code/generic message to clients.
3. **Severe `Error`s:** do not catch every `Throwable` and pretend the system is healthy; have a process-level monitoring/isolation policy.

A `ServiceLoader` finding no providers normally returns `Optional.empty()`. A broken/uninstantiable registered provider can throw `ServiceConfigurationError`; do not collapse both into "no plugin found."

### 5.3. Public error envelope and internal diagnostics

Model:

```text
VendorException("internal-db:443 token=...")
            │ caught inside adapter
            ▼
PluginFailure(code=DEPENDENCY_FAILURE, safe detail)
            │ host uses error code only
            ▼
Public response:
  code=DEPENDENCY_FAILURE
  message="Text service is temporarily unavailable"
  requestId=R1

Internal diagnostics:
  pluginId / instanceId / stage / requestId
  original exception under access control and redaction
```

**Never return raw `Throwable.getMessage()`, stack traces, or `getCause()` to clients.** Keeping a vendor exception as the cause of a public exception lets the host see raw private types via `getCause()` and can accidentally retain old loaders in caches. Retain causes only in access-controlled, redacted internal logging/telemetry; public responses should be DTOs with an error code, safe message, and correlation ID.

**Important:** Even `PluginFailure.getMessage()` produced by a third-party plugin **is not safe by default**. The host should map from a trusted error code to a public message instead of forwarding the provider-supplied message verbatim.

### 5.4. Both sync and async need normalization

For an API:

```java
CompletionStage<TextResult> convertAsync(TextRequest input);
```

this is an illustrative snippet only. If a provider returns a failed future holding a `VendorException`, the error still leaks through the API even though the generic return type is `TextResult`. The plugin must complete failures according to the agreed model—such as shared `PluginFailure` (with the host properly unwrapping `CompletionException`) or `CompletionStage<ResultOrFailure>` carrying a shared error DTO.

For callbacks, avoid `onError(Throwable rawVendorError)` on public boundaries. A shared `PluginErrorEvent(code, requestId, safeMessage)` is easier to version and safer.

### 5.5. Versioning error codes

A shared enum like:

```java
public enum FailureCode {
    INVALID_INPUT,
    DEPENDENCY_FAILURE,
    INTERNAL_FAILURE
}
```

spares the host from knowing vendor exception names. However, when adding enum constants, code with exhaustive `switch` statements compiled against an earlier version may need upgrading; therefore, the version policy must specify how unknown error codes are handled. If a plugin ecosystem needs per-plugin extensible error codes, use namespaced string codes with a registry/schema and default handling. Do not create one public error code per vendor exception class.

## 6. Internal objects, lifecycle, and data compatibility

### 6.1. Ownership beyond Java signatures

An API may look clean when returning `Result`, yet the implementation embeds a `VendorSession` inside the result. The host may keep the result after the plugin stops, keeping sessions, connections, class loaders, or listeners alive past their lifetime.

Rules:

- Plugin inputs/outputs should be independent **snapshots**, immutable whenever feasible.
- Do not return live views of mutable implementation caches/collections.
- Resource handles require shared APIs and explicit `close`/cancellation contracts if they truly must cross the boundary.
- Callbacks/lambdas/streams/publishers must define unsubscribe, backpressure, timeout, and shutdown behavior when the plugin stops.
- Do not let host registries retain raw plugin exceptions, implementation classes, class loaders, `ThreadLocal`s, TCCLs, or callback objects after hot reload.

### 6.2. Compiling is not enough

Compatibility spans multiple layers:

| Layer | Example risk | Verification method |
| --- | --- | --- |
| Source | New signature demands `VendorRequest` | Build host with API JAR only |
| Binary | Changed return/parameter type or removed method | `javap -s`, binary compatibility CI |
| Generic/reflection | Generic `Signature` mentions vendor model | Audit generics, bounds, and annotations |
| Class loader | Two API copies or vendor classes from different loaders | Test SPI/cast/module runtime |
| Behavioral | Changed field semantics, units, nullability | Contract/integration tests |
| Wire/data | Serialized vendor class name in payload | Schema versioning, independent codecs |
| Lifecycle | Host retains vendor handle after plugin stop | Quiesce, close, leak checks |
| Security | Raw exception contains secret | Redaction/negative tests |

`javap -public -s` helps inspect public method descriptors. However, because generics may reside in `Signature` metadata, do not conclude an API is completely clean from erased descriptors alone; inspect signatures/annotations and the compile dependency graph.

### 6.3. Swapping dependencies is an architectural test

Try upgrading a plugin from vendor implementation A to B without editing the shared API or host. If the host still compiles, integration tests pass, no vendor casts exist, and error semantics remain stable, the boundary is working well. If the host must change imports, deserialize vendor objects, or catch new SDK exceptions, implementation details have leaked across the contract.

## 7. Recommended architecture for a plugin system

```text
HOST
 ├─ shared-api.jar  (owner: host/API team)
 ├─ service registry / dispatcher
 ├─ error mapper + public messages
 └─ plugin lifecycle manager
       │
       ├── Plugin A loader/layer
       │     ├─ adapter A implements shared API
       │     └─ vendor A private libraries
       │
       └── Plugin B loader/layer
             ├─ adapter B implements shared API
             └─ vendor B private libraries
```

The host decides contract versions, plugin selection policy, readiness, timeouts, retries, error envelopes, and invocation permissions. The plugin adapter decides how to interact with its SDK; clients never need to know vendor objects. If multiple plugins use different vendor versions, proper loader isolation can separate binary classes, while the shared API maintains a unified identity.

Do not mistake a class loader/module layer for a security sandbox. For untrusted plugins, consider process isolation, OS permissions, resource limits, and neutral protocols rather than running full-privilege code inside the main JVM.

## 8. Runnable Java 17+ example: host compiles without the vendor library

This example uses a **simulated** vendor SDK, so only JDK 17+ is required. The private vendor SDK throws an exception with a simulated internal message. The plugin adapter hides vendor exceptions and types, returning only shared `TextResult` or shared `PluginFailure`. The host never imports implementation or vendor packages.

### 8.1. File layout

```text
demo/
├── src/
│   ├── com/example/api/
│   │   ├── TextRequest.java
│   │   ├── TextResult.java
│   │   ├── FailureCode.java
│   │   ├── PluginFailure.java
│   │   └── TextPlugin.java
│   ├── com/example/host/
│   │   └── Main.java
│   ├── vendor/codec/
│   │   ├── VendorFormatException.java
│   │   └── VendorCodec.java
│   └── plugin/upper/
│       └── UpperPlugin.java
├── resources/
│   └── META-INF/services/com.example.api.TextPlugin
└── build/                       (created on compile)
```

### 8.2. Shared contract

**`src/com/example/api/TextRequest.java`**

```java
package com.example.api;

import java.util.Objects;

public record TextRequest(String requestId, String text) {
    public TextRequest {
        Objects.requireNonNull(requestId, "requestId");
    }
}
```

**`src/com/example/api/TextResult.java`**

```java
package com.example.api;

import java.util.Objects;

public record TextResult(String requestId, String text) {
    public TextResult {
        Objects.requireNonNull(requestId, "requestId");
        Objects.requireNonNull(text, "text");
    }
}
```

**`src/com/example/api/FailureCode.java`**

```java
package com.example.api;

public enum FailureCode {
    INVALID_INPUT,
    DEPENDENCY_FAILURE,
    INTERNAL_FAILURE
}
```

**`src/com/example/api/PluginFailure.java`**

```java
package com.example.api;

import java.util.Objects;

public final class PluginFailure extends Exception {
    private final FailureCode code;

    public PluginFailure(FailureCode code, String internalDetail) {
        super(internalDetail);
        this.code = Objects.requireNonNull(code, "code");
    }

    public FailureCode code() {
        return code;
    }
}
```

**`src/com/example/api/TextPlugin.java`**

```java
package com.example.api;

public interface TextPlugin {
    String id();
    TextResult convert(TextRequest request) throws PluginFailure;
}
```

The shared API uses only `String`, records, an enum, and a shared API exception. `TextRequest.text` may be blank to demonstrate business validation; the implementation returns `INVALID_INPUT`. `PluginFailure.internalDetail` is not client-facing text; the host uses `code()` alone to map public messages.

### 8.3. Simulated private vendor library

**`src/vendor/codec/VendorFormatException.java`**

```java
package vendor.codec;

public final class VendorFormatException extends Exception {
    public VendorFormatException(String message) {
        super(message);
    }
}
```

**`src/vendor/codec/VendorCodec.java`**

```java
package vendor.codec;

import java.util.Locale;

public final class VendorCodec {
    public String toUpper(String input)
            throws VendorFormatException {
        if ("fail".equals(input)) {
            throw new VendorFormatException(
                "endpoint=private.local:443; token=FAKE_SECRET");
        }
        return input.toUpperCase(Locale.ROOT);
    }
}
```

The string `FAKE_SECRET` is used solely to verify error messages do not leak, **not a real credential**. `VendorCodec`/`VendorFormatException` are public so the plugin adapter in another package can call them, yet they are kept out of the contract. On a flat classpath, public vendor classes can still be loaded by the host if deliberately accessed; this example demonstrates an **API boundary**, not runtime security isolation.

### 8.4. Plugin adapter

**`src/plugin/upper/UpperPlugin.java`**

```java
package plugin.upper;

import com.example.api.FailureCode;
import com.example.api.PluginFailure;
import com.example.api.TextPlugin;
import com.example.api.TextRequest;
import com.example.api.TextResult;
import vendor.codec.VendorCodec;
import vendor.codec.VendorFormatException;

public final class UpperPlugin implements TextPlugin {
    private final VendorCodec codec = new VendorCodec();

    public UpperPlugin() {
    }

    @Override
    public String id() {
        return "uppercase";
    }

    @Override
    public TextResult convert(TextRequest request)
            throws PluginFailure {
        if (request == null
                || request.text() == null
                || request.text().isBlank()) {
            throw new PluginFailure(
                FailureCode.INVALID_INPUT, "Invalid text input");
        }
        try {
            String converted = codec.toUpper(request.text());
            return new TextResult(request.requestId(), converted);
        } catch (VendorFormatException vendorError) {
            // Do not return vendorError, do not attach raw message/cause.
            throw new PluginFailure(
                FailureCode.DEPENDENCY_FAILURE,
                "Vendor dependency is unavailable");
        }
    }
}
```

**Key point:** the private `VendorCodec` field and `VendorFormatException` exist only inside the plugin implementation. Public methods defined by `TextPlugin` use shared types exclusively. The host does not need to catch vendor exceptions; if the plugin swaps SDKs, the adapter takes care of mapping errors and DTOs.

### 8.5. Host calling via SPI and normalizing messages

**`src/com/example/host/Main.java`**

```java
package com.example.host;

import com.example.api.FailureCode;
import com.example.api.PluginFailure;
import com.example.api.TextPlugin;
import com.example.api.TextRequest;
import com.example.api.TextResult;
import java.util.ServiceLoader;

public final class Main {
    private static String publicMessage(FailureCode code) {
        return switch (code) {
            case INVALID_INPUT -> "Input text is required";
            case DEPENDENCY_FAILURE ->
                "Text service is temporarily unavailable";
            case INTERNAL_FAILURE -> "Plugin execution failed";
        };
    }

    public static void main(String[] args) {
        if (args.length > 1) {
            System.out.println("Usage: Main [text]");
            return;
        }

        TextPlugin plugin = ServiceLoader.load(TextPlugin.class)
            .findFirst()
            .orElse(null);

        if (plugin == null) {
            System.out.println("NO_PLUGIN");
            return;
        }

        String input = args.length == 0 ? "hello" : args[0];
        TextRequest request = new TextRequest("R1", input);

        try {
            TextResult result = plugin.convert(request);
            System.out.println(
                "OK " + result.requestId() + " " + result.text());
        } catch (PluginFailure error) {
            // Do not output plugin's error.getMessage() to clients.
            System.out.println("ERROR " + error.code()
                + " " + publicMessage(error.code()));
        } catch (RuntimeException unexpected) {
            // Log redacted internal details in production apps.
            System.out.println(
                "ERROR INTERNAL_FAILURE Plugin execution failed");
        }
    }
}
```

The host imports only `com.example.api.*` and `java.util.ServiceLoader`. The host has no source-level dependency on `vendor.codec`, never casts objects to vendor types, and never outputs raw exception details. In larger systems, provider instantiation failures inside `ServiceLoader` must also be handled separately rather than treated as `NO_PLUGIN` when an SPI descriptor or class loading fails.

### 8.6. SPI descriptor

**`resources/META-INF/services/com.example.api.TextPlugin`**

```text
plugin.upper.UpperPlugin
```

The filename matches the fully qualified name of the service interface; its content is the provider class. The file must live inside the plugin JAR at `META-INF/services` for `ServiceLoader` to discover the provider.

### 8.7. Compiling, packaging JARs, and running with Windows PowerShell

Inside directory `demo` with JDK 17+:

```powershell
New-Item -ItemType Directory -Force build/host, build/vendor, build/plugin | Out-Null

# Host compiles with shared API + JDK only, WITHOUT vendor jar.
javac -encoding UTF-8 -d build/host src/com/example/api/*.java src/com/example/host/Main.java

# Vendor private library is compiled/packaged separately.
javac -encoding UTF-8 -d build/vendor src/vendor/codec/VendorFormatException.java src/vendor/codec/VendorCodec.java
jar --create --file build/vendor-private.jar -C build/vendor .

# Provider adapter depends on both API and vendor library.
javac -encoding UTF-8 -cp 'build/host;build/vendor-private.jar' -d build/plugin src/plugin/upper/UpperPlugin.java

# SPI descriptor is packaged inside the plugin JAR.
New-Item -ItemType Directory -Force build/plugin/META-INF/services | Out-Null
Copy-Item resources/META-INF/services/com.example.api.TextPlugin build/plugin/META-INF/services/com.example.api.TextPlugin
jar --create --file build/text-plugin.jar -C build/plugin .

# Runtime has both plugin and private dependency.
java -cp 'build/host;build/text-plugin.jar;build/vendor-private.jar' com.example.host.Main
java -cp 'build/host;build/text-plugin.jar;build/vendor-private.jar' com.example.host.Main '   '
java -cp 'build/host;build/text-plugin.jar;build/vendor-private.jar' com.example.host.Main fail

# Without provider JAR -> no plugin discovered.
java -cp build/host com.example.host.Main
```

**PowerShell/Windows** uses semicolons `;` between classpath entries. **Linux/macOS** uses colons `:` and replaces directory/copy commands with `mkdir -p`/`cp`; e.g., runtime `java -cp 'build/host:build/text-plugin.jar:build/vendor-private.jar' com.example.host.Main`.

The host compile command runs **before** building the vendor library; this directly verifies that the host does not need the private vendor dependency at compile time.

### 8.8. Exact stdout

**Default run** with input `"hello"`:

```text
OK R1 HELLO
```

**Whitespace-only input**:

```text
ERROR INVALID_INPUT Input text is required
```

**Input `"fail"`**, vendor SDK throws private exception:

```text
ERROR DEPENDENCY_FAILURE Text service is temporarily unavailable
```

**Without plugin JAR**:

```text
NO_PLUGIN
```

None of the outputs contain `vendor.codec.VendorFormatException`, `private.local`, or `FAKE_SECRET`. The host maps error codes to public messages chosen by the host itself. If `vendor-private.jar` is removed while leaving the plugin JAR in place, class loading/linking fails; that is a **missing dependency**, not a normal `NO_PLUGIN` case.

### 8.9. What the example demonstrates and what it omits

The example demonstrates that vendor types do not leak through the public API, objects are converted into shared DTOs, vendor exceptions stop at the adapter, and the host compiles without the vendor library. It uses a shared classpath to keep running simple; it does **not** assume classloader isolation, dependency graph isolation, or hot reload.

The sample runs sequentially without managing plugin start/stop lifecycles, timeouts, or concurrency. A production plugin manager must control provider selection, version compatibility, session limits, callback cleanup, and monitoring. Never use class loaders/modules as a sandbox for untrusted code.

## 9. Verifying API boundaries in CI and runtime

### 9.1. Source, bytecode, and dependency checks

- Build the shared API and host **without `vendor-private.jar`** on the compile classpath.
- Use `javap -public -s` or an API/ABI diff tool to catch unwanted types in public method descriptors.
- Audit generic `Signature`s, bounds, annotations, record components, and exception types; JVM erasure does not eliminate source/reflection coupling.
- Enforce rules blocking API packages from importing `vendor.*` or `plugin.internal.*` namespaces.
- Build a fake plugin from the shared API alone, without vendor dependencies.
- Test upgrading a vendor version or swapping vendors and confirm no host code edits are needed.

### 9.2. Runtime and ownership checks

- Run providers through the intended class loader or module layer; verify host/plugin share the **exact same API type identity**.
- Ensure no raw vendor objects appear inside returned DTOs, callbacks, futures, or events.
- Result lists/buffers/arrays must obey copy/immutability policies.
- After plugin stop/hot reload, ensure the host retains no raw `Throwable`, `Class<?>`, callbacks, threads, or plugin handles pinning the old loader.
- When multiple plugins use different vendor versions, test classloader isolation and data exchange via shared DTOs.
- SPI/config provider errors must not be reported as "no provider found" when metadata is actually invalid or runtime dependencies failed.

### 9.3. Testing against error and secret leaks

Inject a synthetic vendor failure containing strings like:

```text
endpoint=internal.example:443 token=FAKE_TOKEN
```

Verify public responses contain no endpoint, token, vendor class name, stack trace, or raw SQL; meanwhile, internal logs must include a request ID and proper access controls. Test all branches: invalid input, vendor checked exception, unexpected runtime exception, async completion failure, callback error, and provider initialization failure.

Separate exceptions **defined by the public contract** from unclassified operational failures. Do not catch every `Throwable` to "ensure stability"; severe JVM errors may render continuing in the same process unsafe.

## 10. Common mistakes and fixes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| `VendorResult method(VendorRequest)` | Host forced to know private SDK | Shared DTO + adapter |
| `throws VendorException` | Host compiles/catches against SDK | Shared `PluginFailure`/error code |
| `Object getState()` returning raw vendor object | Leaks implementation and class loader | Snapshot DTO, never return private handles |
| `List<VendorResult>` | Generic signatures still coupled | `List<SharedResult>` |
| `Map<String,Object>` containing vendor values | Ambiguous contract, runtime casts | Typed DTO/schema |
| Returning `Throwable`/cause/stack trace | Exposes internal data, pins loader | Error DTO + correlation ID, redacted logging |
| Host prints `PluginFailure.getMessage()` | Plugin might supply secrets | Host maps error code to safe message |
| Async future fails with vendor error | Indirect exception leak | Normalize async failures |
| API JAR copied/loaded by plugin loader | Two distinct type identities | Shared API loader/module |
| Returning mutable cache or vendor session | Broken ownership/lifetime, resource leak | Defensive copy or shared closeable facade |
| Assuming private Gradle dependency protects API | Public signatures can still leak | Audit Java API and runtime object graph |
| Assuming JPMS/classloader is a sandbox | Does not restrict process privileges | Process isolation and OS policy when needed |

## 11. Plugin API release checklist

- [ ] API artifact/module owned by host, with clear versioning and semantics.
- [ ] No vendor/private types in public/protected parameters, returns, generics, records, callbacks, annotations, or checked exceptions.
- [ ] Host compiles with shared API + JDK only.
- [ ] Plugin adapter converts exclusively to shared DTOs, never returning raw vendor objects even cast as `Object`.
- [ ] Result/data ownership is explicit; copy mutable values per contract.
- [ ] No internal sessions/connections/classloaders/`Throwable`s returned past plugin lifetime.
- [ ] Vendor exceptions mapped to shared error codes; clients never see internal messages/stacks/causes.
- [ ] Host selects public messages by code; unknown code/versioning rules defined.
- [ ] API type identity synchronized across host and provider loaders/module layers.
- [ ] Vendor runtime dependencies packaged/resolved completely, yet absent from the public API graph.
- [ ] ABI/source compatibility checks, integration tests, leak tests, and error-redaction tests in place.
- [ ] Hot reload cleans up callbacks, streams, threads, exception caches, and provider references.
- [ ] Do not confuse API encapsulation with security sandboxing of untrusted plugins.

**Conclusion:** Keeping the **API strictly composed of shared types**, **returned data free of internal objects**, and **vendor exceptions contained within adapters** is the foundation for upgrading plugins independently, reducing class loader conflicts, and preventing technical information leaks. This separation must be enforced across **source signatures, the runtime object graph, error handling, and lifecycle**—not merely by package names or the `private` keyword.

**Java SE 17 references:** [`ServiceLoader`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html), [`ClassLoader`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html), [`Throwable`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Throwable.html), [`CompletionStage`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletionStage.html), [`List.copyOf`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection)), [`Module`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Module.html).

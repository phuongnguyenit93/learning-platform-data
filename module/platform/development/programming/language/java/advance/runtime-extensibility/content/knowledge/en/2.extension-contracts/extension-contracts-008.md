# Keeping Plugin Contracts Small and Avoiding Exposure of Plugin-Internal Libraries

A runtime extensibility system typically involves two sides released, updated, and loaded into the JVM on different cadences: the **host** (the application providing extension points) and **plugins** (components implementing new capabilities). The mandatory common ground between them is the **extension contract**: a small set of types, behaviors, and rules understood by both host and plugins. If the contract forces the host to know details of each plugin's JSON, HTTP, database, or engine libraries, changing a plugin's implementation can ripple changes into the host and other plugins.

The goal of this article is to design a boundary small enough, with clear data types, so the host invokes plugins through a stable API while each plugin's libraries, configuration, and implementation structure remain behind that boundary.

## 1. Separating the Contract from the Implementation

Suppose the host wants to provide text transformation powered by multiple registered plugins.

| Part | Belongs to shared contract | Belongs to private implementation |
| --- | --- | --- |
| Capability | TextPlugin interface with transform operation | Transformation algorithms, caching, service calls |
| Data | TextRequest, TextResult defined by the API module | ObjectMapper, JsonNode, HTTP clients, vendor DTOs |
| Discovery | Service name and provider loading rules | Internal class names, package layout, and helper libraries |
| Errors | Error conventions the host can handle | Specialized exceptions, stack traces, internal retry logic |
| Versioning | API compatibility level and declared capabilities | Library versions used privately by a plugin |

A **small contract** means focused responsibilities, stability, and direct relevance to the extension point; it does not mean replacing every type with Object or Map<String, Object>. Overly generic types make validation, upgrades, and error diagnosis harder. Conversely, stuffing every capability of a framework into one interface bloats the contract.

### Dependency Leakage Example to Avoid

The snippet below **illustrates a flawed design only**, not a standalone compilable program:

~~~java
// Host public API: design NOT recommended.
public interface TextPlugin {
    com.fasterxml.jackson.databind.JsonNode transform(
            com.vendor.plugin.internal.EngineSession session,
            com.fasterxml.jackson.databind.JsonNode request);
}
~~~

Here, the host and every plugin wanting to use the interface must know types from Jackson and a plugin-internal library. Switching engines, upgrading the JSON library version, or loading multiple library versions in separate classloaders can break API compatibility; the EngineSession class itself has also been turned into part of the public commitment.

A better design converts data **at the boundary**: the host passes a request belonging to the shared API; the plugin translates that request into objects of its chosen library, then translates the result back into the shared response. Never put internal libraries into public parameters, return types, generics, callbacks, events, or exception types.

## 2. Designing a Minimal Yet Meaningful Contract

For the text-transformation example, a standalone **plugin-api** module may need only three types:

~~~java
// src/api/example/ext/api/TextRequest.java
package example.ext.api;

import java.util.Objects;

public record TextRequest(String text) {
    public TextRequest {
        Objects.requireNonNull(text, "text");
    }
}
~~~

~~~java
// src/api/example/ext/api/TextResult.java
package example.ext.api;

import java.util.Objects;

public record TextResult(String text) {
    public TextResult {
        Objects.requireNonNull(text, "text");
    }
}
~~~

~~~java
// src/api/example/ext/api/TextPlugin.java
package example.ext.api;

public interface TextPlugin {
    String id();
    TextResult transform(TextRequest request);
}
~~~

These records carry clear data, use only standard Java, and depend on neither the host framework nor plugin frameworks; checking null at the boundary catches invalid inputs early. They are immutable with respect to the String field. If a request carries a List or Map, specify immutability, perform defensive copying when needed, and document value representation; records **do not automatically make nested collections immutable**.

Two key decisions:

1. The host owns and publishes the contract module. Plugins compile against **a compatible version of that contract**; never copy or bundle a separate copy of TextPlugin into an isolated classloader.
2. Each method reflects a capability that genuinely needs to be shared. Do not hand plugins access to an entire ApplicationContext, DataSource, ClassLoader, or host internals just to perform one small job. If a plugin needs a service from the host, provide a narrow capability interface, such as Clock or a scoped logging port.

Do not add an operation needed by only one plugin into an interface that every plugin is forced to implement. Instead, introduce an **optional capability interface** and let the host check support, rather than piling abstract methods onto the base contract.

## 3. Runnable Java 17 Example: Host Knows Only the API

Example file layout:

~~~text
src/
  api/example/ext/api/
    TextRequest.java
    TextResult.java
    TextPlugin.java
  plugin/example/ext/impl/
    UppercasePlugin.java
  plugin/META-INF/services/
    example.ext.api.TextPlugin
  host/example/ext/host/
    App.java
~~~

The three core API files are the code from Section 2. The plugin provides an implementation and a **private** helper. In a real project, this helper could use a third-party library, yet none of that library's types appear in TextPlugin, TextRequest, or TextResult.

~~~java
// src/plugin/example/ext/impl/UppercasePlugin.java
package example.ext.impl;

import example.ext.api.TextPlugin;
import example.ext.api.TextRequest;
import example.ext.api.TextResult;
import java.util.Locale;

public final class UppercasePlugin implements TextPlugin {
    private final UppercaseEngine engine = new UppercaseEngine();

    public UppercasePlugin() { }

    @Override
    public String id() {
        return "upper";
    }

    @Override
    public TextResult transform(TextRequest request) {
        return new TextResult(engine.apply(request.text()));
    }

    private static final class UppercaseEngine {
        String apply(String input) {
            return input.toUpperCase(Locale.ROOT);
        }
    }
}
~~~

The service descriptor file contains **exactly one line with the fully qualified class name**, not Java code:

~~~text
# src/plugin/META-INF/services/example.ext.api.TextPlugin
example.ext.impl.UppercasePlugin
~~~

The line starting with `#` in the block above is only a note indicating the file path; **the actual file content is solely** example.ext.impl.UppercasePlugin followed by a newline. The descriptor filename must match the binary name of the service interface.

The host locates implementations via ServiceLoader and works only with the API:

~~~java
// src/host/example/ext/host/App.java
package example.ext.host;

import example.ext.api.TextPlugin;
import example.ext.api.TextRequest;
import example.ext.api.TextResult;
import java.util.ServiceLoader;

public final class App {
    public static void main(String[] args) {
        boolean found = false;

        for (TextPlugin plugin : ServiceLoader.load(TextPlugin.class)) {
            found = true;
            TextResult result = plugin.transform(
                    new TextRequest("hello plugin"));
            System.out.println(plugin.id() + " -> " + result.text());
        }

        if (!found) {
            throw new IllegalStateException("No TextPlugin provider found");
        }
    }
}
~~~

From the directory containing src, run the following commands in a Bash-like shell (requires JDK 17 or later):

~~~bash
mkdir -p out/api out/plugin out/host
javac --release 17 -encoding UTF-8 -d out/api src/api/example/ext/api/TextRequest.java src/api/example/ext/api/TextResult.java src/api/example/ext/api/TextPlugin.java
jar --create --file out/plugin-api.jar -C out/api .
javac --release 17 -encoding UTF-8 -cp out/plugin-api.jar -d out/plugin src/plugin/example/ext/impl/UppercasePlugin.java
jar --create --file out/plugin.jar -C out/plugin . -C src/plugin META-INF/services
javac --release 17 -encoding UTF-8 -cp out/plugin-api.jar -d out/host src/host/example/ext/host/App.java
java -cp "out/host:out/plugin-api.jar:out/plugin.jar" example.ext.host.App
~~~

Output when only this provider is present:

~~~text
upper -> HELLO PLUGIN
~~~

On Windows, the classpath separator is a semicolon instead of a colon. Corresponding run command example:

~~~powershell
java -cp "out/host;out/plugin-api.jar;out/plugin.jar" example.ext.host.App
~~~

**What this proves:** the host code imports only the three types in example.ext.api and ServiceLoader; the host never imports UppercasePlugin, UppercaseEngine, or internal processing libraries. A plugin can swap its private engine while preserving the API and contract results. With a single provider, the output above is deterministic; if multiple providers are registered, do not rely on ServiceLoader's default iteration order.

**Limitations of the example:** the JARs share the application classpath, so code can still see each other's public classes at the classpath level. Avoiding references to implementations here is **architectural discipline**, not physical isolation or a security sandbox. When library version isolation is needed, custom classloaders can be used; when modular packaging is needed, JPMS ensures only designated API packages are exported.

## 4. Dependencies and Classloaders: Keeping One Shared API Identity

A sound dependency layout:

~~~text
host ───────────────> plugin-api
                           ^
                           |
plugin-implementation -----+
        |
        +----> plugin's own third-party library
~~~

The host compiles against plugin-api, not against implementations or plugin third-party libraries. The plugin compiles against plugin-api, while implementing algorithms using its own dependencies. In Gradle, declare dependencies by role: libraries serving only the implementation belong in the `implementation` configuration; the shared contract is supplied to both sides per packaging policy, possibly `compileOnly` for plugins when the runtime provides plugin-api. Using `implementation` instead of `api` for an internal library **will not fix a public signature that accidentally exposed a type from that library**: the signature itself must be fixed.

In the JVM, class identity depends on **binary name and defining classloader**. Two classes with the same name example.ext.api.TextPlugin defined by two different classloaders are not the same type. A plugin that repackages a copy of the API or loads the API with its own loader can cause ServiceLoader to report the provider is not a subtype, or cause cast/linkage failures.

When designing a system with custom loaders:

- Share **one API definition** visible to both host and plugins, usually from a parent loader; avoid shading/relocating contract classes into plugin JARs.
- Give each plugin ownership of its implementation and supporting libraries when dependency isolation is needed. Parent-first/child-first rules must be chosen deliberately; prefer sharing API packages from the parent.
- Specify the classloader used for service and resource discovery. `ServiceLoader.load(service)` uses the thread context classloader by default; it must be able to see provider descriptors and the corresponding provider classes.
- Manage the lifecycle of loaders, threads, executors, static references, and resources created by plugins; if unreleased, unloading/reloading can retain old classloaders in memory.

Classloader isolation helps manage dependencies and lifecycle, but **does not create a reliable security boundary for untrusted code** within the same JVM.

With JPMS, the API module only `exports` contract packages; the plugin module can `provides` the service without `exports`ing implementation packages. Illustrative configuration snippet (different from the classpath mechanism in the demo):

~~~java
// module-info.java of the API module
module example.plugin.api {
    exports example.ext.api;
}
~~~

~~~java
// module-info.java of the plugin module
module example.plugin.uppercase {
    requires example.plugin.api;
    provides example.ext.api.TextPlugin
        with example.ext.impl.UppercasePlugin;
}
~~~

~~~java
// module-info.java of the host module
module example.plugin.host {
    requires example.plugin.api;
    uses example.ext.api.TextPlugin;
}
~~~

To run on the module path, you must compile and package according to JPMS rules and place provider modules in an appropriate layer/module path; the three `module-info` snippets above are **not drop-in commands** for the classpath demo. In JPMS, `exports`/`opens` and `ServiceLoader` are separate design choices to evaluate.

## 5. Contract Compatibility Across Multiple Releases

A plugin may have been compiled earlier and only loaded after the host is updated. Therefore consider **source, binary, and semantic compatibility**; do not check only whether new code still compiles.

| Change | Risk | How to handle |
| --- | --- | --- |
| Renaming or changing package, parameter types, or return type of an API method | Can break ABI, causing runtime linkage errors | Keep old API or bump major version with a migration path |
| Adding an abstract method to an interface with existing providers | Older providers may hit AbstractMethodError when invoked by host | Prefer a new capability interface; consider default methods if semantics fit |
| Adding a component to a public record | Changes canonical constructor, potentially breaking old binary clients | Version the DTO or design a controlled extension path |
| Changing behavior of exceptions or return values | Host code may mishandle results even though ABI is unchanged | Document null, error, timeout, retry, and edge-case rules explicitly |
| Upgrading library versions inside an implementation | Usually requires no API edit if no types leaked | Re-test behavior and plugin loader compatibility |

If additional capabilities are needed, define another interface in plugin-api—such as TextPluginMetrics—and let the host use type checks or explicit capability registration. That allows older plugins to continue providing core functionality. Versions/capabilities should follow clear policies: which version ranges the host accepts, when it rejects, and whom it notifies. SemVer is helpful, but never replaces real binary testing.

**Errors and resources are also part of the contract.** Never declare `throws` with an exception type from a plugin-private SDK, and never force the host to inspect an internal exception. Pick shared error types or a boundary exception-translation policy. Specify whether plugins may be invoked concurrently, who owns request/result objects, call deadlines, cancellation rules, and resource closing on unload. Add lifecycle methods only when multiple plugins genuinely need those shared rules.

## 6. Checking the Boundary Before Release

1. **Inspect public signatures:** audit all public/protected methods, constructors, fields, generics, annotations, and exceptions in the plugin-api module. Ensure no packages from implementations, SDKs, ORMs, JSON, HTTP clients, or host internals appear.
2. **Inspect the dependency graph:** the host must compile with only plugin-api, without plugin implementations or plugin-internal JARs. The plugin-api module itself must pull in no implementation libraries. You can run `jdeps --summary out/plugin-api.jar` to audit JAR dependencies.
3. **Verify provider registration:** META-INF/services filename and fully qualified class name match exactly, the provider can be instantiated, and the JAR and resources are actually on the runtime path. For classpath ServiceLoader, the provider needs a suitable implementation class and a public no-arg constructor.
4. **Verify compatibility:** run older providers against the new host within the supported version range, and newer providers against older hosts if compatibility is claimed; test null inputs, errors, timeouts, concurrent calls, and missing providers.
5. **Test with real loaders:** ensure host and plugins share the same API class identity; test two plugins using different versions of an implementation library; test reloading and resource cleanup when unloading is supported.

Diagnostic clues to investigate: ServiceConfigurationError when a service descriptor/provider is invalid or cannot load; NoClassDefFoundError when a runtime dependency is missing; ClassCastException or service-subtype errors when the API is split across loaders; NoSuchMethodError/AbstractMethodError when host and plugin ABIs diverge. Read the full cause chain in the stack trace rather than attributing every failure to a single cause.

## 7. Design Rules You Can Apply Immediately

Before adding a type or method to plugin-api, ask: **does the host genuinely need to know this to use the capability, or does only the plugin need to know it to implement it?** If only the implementation needs it, keep it behind an adapter and translate requests/results at the boundary. Prefer small capability-focused interfaces, stable DTOs free of private-library types, clear versioning, and one shared API class identity. Expand the contract only after checking its impact on already-released plugins.

A well-designed contract lets you swap libraries, change algorithms, or load additional plugins while the host keeps calling the exact same published interface—reducing cross-coupling and making runtime extensibility safer to upgrade.
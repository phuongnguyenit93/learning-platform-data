# JSR 223 and the Boundary Between javax.script and Language Engines

## 1. What Is JSR 223?

**JSR 223 (Scripting for the Java Platform)** defines a standard API for Java applications to discover, configure, and invoke **scripting engines**. The public API resides in the \`javax.script\` package, belonging to the **\`java.scripting\`** module since Java 9.

JSR 223 solves an integration problem: Java code wants to execute scripts without coupling tightly to each engine's proprietary API. It provides a contract for discovering engines, passing variables, calling \`eval\`, receiving results, and handling errors.

It is important to distinguish between:

- **\`javax.script\`**: the Java-side set of interfaces/classes, such as \`ScriptEngineManager\`, \`ScriptEngine\`, \`ScriptEngineFactory\`, \`Bindings\`, \`ScriptContext\`, \`Compilable\`, \`Invocable\`, and \`ScriptException\`.
- **Language engine**: the software that actually parses, compiles/interprets, and executes JavaScript, Groovy, Python, or another language.
- **Script source**: a code snippet in the language the engine understands—not Java code and not automatically part of the JDK.

\`javax.script\` is an **intermediary SPI/API**, not a JavaScript runtime itself. Having the \`java.scripting\` module in the JDK **does not mean** the JDK comes with a built-in engine for every language.

## 2. Architecture and Extension Points

\`\`\`text
Java application / plugin host
          |
          v
ScriptEngineManager  (javax.script)
          |
          +--> ScriptEngineFactory A --> Engine A --> Script
          |
          +--> ScriptEngineFactory B --> Engine B --> Script
          |
          +--> No matching factory --> null / missing-engine message
\`\`\`

The host requests an engine by name or characteristic, for example \`getEngineByName("groovy")\`. \`ScriptEngineManager\` uses the service-provider mechanism to find \`ScriptEngineFactory\` implementations accessible through its class loader. Engine vendors implement that contract and may provide additional proprietary APIs for language handling, classpath, sandboxing, and performance.

Division of responsibilities:

| Part | Responsibility | Not Automatically Guaranteed |
|---|---|---|
| \`ScriptEngineManager\` | Discovers factories, maps names/MIME/extensions, and provides engines | That the engine exists at runtime |
| \`ScriptEngineFactory\` | Describes the engine, supported names/extensions/MIME types, and creates engines | That script code is trustworthy |
| \`ScriptEngine\` | Evaluates scripts via \`eval\`, manages bindings/context | That APIs across all engines are completely identical |
| \`Bindings\` | Holds named values exposed into scope | That objects in bindings are isolated |
| \`ScriptContext\` | Controls scopes, reader/writer/error writer, and attributes for eval | That context is thread-safe or automatically propagated across executors |
| Engine runtime | Implements syntax/semantics of the language | Compatibility with Java/JDK and every library |

This is an extension point for plugin systems: the host can swap the engine installed in the environment while keeping most integration code based on \`javax.script\`. However, configuration, capabilities, and security limits still depend on each engine.

## 3. JSR 223 on Java 17+: Do Not Assume a JavaScript Engine Exists

Previously, some JDK distributions provided **Nashorn** as a JavaScript engine. Nashorn was marked deprecated in JDK 11 and **removed from the JDK starting in JDK 15** (JEP 372). Therefore, in a typical JDK 17 or JDK 21:

\`\`\`java
ScriptEngine engine =
        new ScriptEngineManager().getEngineByName("JavaScript");
\`\`\`

may return **\`null\`** instead of a ready-to-use engine. The \`javax.script\` API is still there; only the implementation needs to be supplied separately.

Third-party engines can integrate with JSR 223 if they provide an appropriate \`ScriptEngineFactory\`. Not every language runtime supports JSR 223 out of the box: some engines only provide their own embedding API (for example, certain polyglot APIs), and version support can vary.

**Operational rule:** check the list of factories actually present on the target runtime; log the engine name, version, and language version; reject or report a clear error when the required engine is absent.

## 4. Runnable Java 17+ Example: Discovering Engines Without External Libraries

Create file **\`ScriptEngineDiscoveryDemo.java\`**:

\`\`\`java
import javax.script.ScriptEngine;
import javax.script.ScriptEngineFactory;
import javax.script.ScriptEngineManager;
import java.util.Comparator;

public class ScriptEngineDiscoveryDemo {
    public static void main(String[] args) {
        ScriptEngineManager manager = new ScriptEngineManager();

        manager.getEngineFactories().stream()
                .sorted(Comparator.comparing(ScriptEngineFactory::getEngineName))
                .forEach(factory -> System.out.println(
                        factory.getEngineName() + " / " +
                        factory.getEngineVersion() + " / " +
                        factory.getLanguageName()));

        ScriptEngine engine = manager.getEngineByName("JavaScript");
        System.out.println("JavaScript engine available: " + (engine != null));
    }
}
\`\`\`

Run:

\`\`\`bash
javac ScriptEngineDiscoveryDemo.java
java ScriptEngineDiscoveryDemo
\`\`\`

When run on JDK 17+ **without an additional scripting engine installed**, stdout is:

\`\`\`text
JavaScript engine available: false
\`\`\`

If the classpath/module path has a registered compatible engine, the program also prints the factory lines beforehand and the result may become \`true\`. The example does not assume that a third-party engine's name is always \`JavaScript\`.

In a named JPMS module using \`javax.script\`, you must declare:

\`\`\`java
module com.example.script.host {
    requires java.scripting;
}
\`\`\`

This is an illustrative descriptor snippet; the actual module name depends on the project.

## 5. Passing Data and Calling eval

Once you have a valid \`ScriptEngine\`, the host can pass data using \`Bindings\`:

\`\`\`java
// Integration snippet; assumes manager found a matching engine.
ScriptEngine engine = manager.getEngineByName("some-language");
if (engine == null) {
    throw new IllegalStateException("Scripting engine is unavailable");
}

Bindings values = engine.createBindings();
values.put("customerName", "Lan");
Object result = engine.eval("expression_using_customerName", values);
\`\`\`

The script string above is only a **syntax placeholder** to indicate the integration point; actual syntax must match the engine's language. \`eval(script, bindings)\` uses bindings for the ENGINE_SCOPE of that execution; this differs from mutating all global variables of the engine.

\`Bindings\` contains **Java object references**; it does not automatically serialize/copy or restrict permissions. Passing an object such as \`databaseClient\` may let the script access more than intended depending on the engine's interop capabilities. For untrusted script code, do not treat bindings as a sandboxing measure; a host access policy and a real isolation model are required.

\`ScriptContext\` has scopes:

- \`ENGINE_SCOPE\`: bindings closest to the engine/eval, typically for dedicated variables.
- \`GLOBAL_SCOPE\`: global bindings if configured, which may be shared across multiple engines/contexts.

Distinguishing scopes is important in multi-tenant execution. Do not share mutable \`Bindings\` across requests unless the engine guarantees appropriate thread safety and the application enforces explicit synchronization/isolation.

## 6. Optional Engine Capabilities

The base contract does not guarantee that an engine supports every feature. Two important interfaces:

**\`Compilable\`** allows pre-compiling a script for repeated use:

\`\`\`java
// Integration snippet: engine is available and script has valid syntax.
if (engine instanceof javax.script.Compilable compilable) {
    javax.script.CompiledScript compiled =
            compilable.compile(script);
    Object result = compiled.eval();
}
\`\`\`

Performance and reusability of \`CompiledScript\` depend on the engine, especially when mutable context/bindings are present.

**\`Invocable\`** provides a way to invoke a function or method defined by the script:

\`\`\`java
// Integration snippet: function "calculate" has been evaluated and exists.
if (engine instanceof javax.script.Invocable invocable) {
    Object value = invocable.invokeFunction("calculate", 5);
}
\`\`\`

Lacking \`Compilable\` or \`Invocable\` is not an engine bug; they are optional capabilities. The host should verify required capabilities at initialization rather than waiting until an actual request to fail.

\`ScriptEngineFactory.getParameter("THREADING")\` can provide information about the engine's threading model under the JSR 223 contract. A \`null\` value must not be interpreted as meaning the engine is thread-safe. Even when an engine advertises concurrency support, the host still needs to understand context state and the Java objects passed in.

## 7. Service Provider Discovery and Class Loaders

A JSR 223 engine typically publishes an implementation of the interface:

\`\`\`java
javax.script.ScriptEngineFactory
\`\`\`

In a classpath JAR, discovery can rely on service provider metadata at:

\`\`\`text
META-INF/services/javax.script.ScriptEngineFactory
\`\`\`

With a named JPMS module, the provider can declare:

\`\`\`java
module com.example.language.engine {
    requires java.scripting;
    provides javax.script.ScriptEngineFactory
        with com.example.language.EngineFactory;
}
\`\`\`

This is an illustrative module descriptor and only compiles when the actual factory class exists. \`ScriptEngineManager\` provides a constructor accepting a \`ClassLoader\` to control discovery scope, but it does not automatically load new JARs that have not been placed into an appropriate class loader/layer.

In a plugin host with multiple class loaders, avoid:

- Engine JAR not lying within the visibility scope of the loader used to create the manager.
- Host and plugin using incompatible bridge APIs/class types due to duplicate dependencies and class identity.
- Plugin loader being retained by an engine instance, script callback, thread, or cached compiled script after a version swap.
- Confusing \`ServiceLoader.load(layer, service)\` with the \`ScriptEngineManager\` API; the manager has no overload directly accepting a \`ModuleLayer\`. If the architecture requires layers, you must design an appropriate discovery/adapter approach and respect JPMS rules.

For dynamic engine replacement, validate the artifact first, create a lifecycle-managed loader/layer, discover the factory, verify capabilities, and only then publish the engine for new requests.

## 8. Practical Boundary Between javax.script and Engines

Treat \`javax.script\` as a **common gateway** and the engine as a **replaceable implementation component**, though the common contract only describes a relatively small set of operations. Parts that commonly depend on the engine include:

| Topic | How Far Does the Common API Support? | Engine-Dependent |
|---|---|---|
| Script parsing | \`eval\` and \`ScriptException\` | Syntax, libraries, semantics |
| Variables | \`Bindings\`, \`ScriptContext\` | How Java values map to script values |
| Compilation | \`Compilable\` if supported | Caching, optimization, lifecycle |
| Function invocation | \`Invocable\` if supported | Parameter mapping and exceptions |
| Threading | Factory metadata on concurrency | Actual thread safety, parallel execution capability |
| Sandbox | No standard cross-engine sandboxing mechanism | Host access, filesystem/network/process permissions |
| Timeout | No universal timeout/cancel contract for all engines | Interruption, resource limits, and quotas |
| Module/classpath | Java-based service discovery | Dependencies, language modules, class loader |

Therefore, two engines that both support JSR 223 are not guaranteed to produce identical results when running an arbitrary script. When switching engines, you must test syntax, language APIs, conversions, exception behavior, security policy, and performance.

## 9. Error Handling Across Each Boundary

A host should classify errors by phase:

1. **Discovery:** no factory with the target name exists, or the provider is misconfigured. \`getEngineByName(...)\` may return \`null\`.
2. **Initialization:** missing engine dependencies, configuration errors, class loading, or service provider failures.
3. **Compilation/parsing:** \`ScriptException\` or language errors when the script has invalid syntax.
4. **Execution:** script runtime errors, invalid data, Java interop issues, or resource exhaustion.
5. **Lifecycle:** script callbacks, threads, resources, or class loaders remaining alive after stopping a plugin.

Do not catch every error and treat it as a “script syntax error”. Engine code may produce side effects before an exception occurs; retries are not automatically safe. Logs should retain engine identity/version, script ID or hash, request ID, and stage; avoid logging scripts containing secrets or sensitive data.

## 10. Safety When Running Scripts in an Application

JSR 223 is a code-execution API. When scripts are supplied by third parties or users, risk depends on the engine's access level:

- **Not sandboxed by default:** JSR 223 has no standard configuration to restrict files, network, reflection, threads, or host objects.
- **Do not expose the entire host object graph:** provide only narrow DTOs/operations, avoiding putting databases/credentials/sessions directly into bindings.
- **Limit resources:** enforce timeouts, memory/CPU quotas, and cancellation actually supported by the engine; for untrusted code, prefer running in a separate process/container.
- **Block unverified code:** verify the source, version, and signature/integrity of the engine; restrict who has permission to load scripts.
- **Manage tenant isolation:** each execution context needs clear ownership. An engine instance may hold global state, so choose an appropriate pooling/per-context isolation model.
- **Observability and rollback:** audit executions, script versions, results, and errors, while avoiding re-executing non-idempotent side effects.

A dedicated class loader or dedicated module layer **cannot replace an OS security boundary** for untrusted code.

## 11. When to Use JSR 223 vs. a Proprietary API?

**Use JSR 223 when:** the host needs simple integration and wants to support multiple engines with compatible implementations; operations are primarily \`eval\`, bindings, and optional compile/invoke; backend replaceability is more valuable than advanced features.

**Use an engine's proprietary API when:** you need deep polyglot interop, precise host access configuration, advanced isolates/contexts, resource limits, or specialized debugging/profiling. In that case, you can design an adapter to keep the application contract stable without forcing every capability into \`ScriptEngine\`.

A commonly useful plugin pattern:

\`\`\`text
Host ScriptExecutor interface
    |
    +--> Jsr223ScriptExecutor
    |       |
    |       +--> ScriptEngine A
    |       +--> ScriptEngine B
    |
    +--> NativeEngineAdapter
            |
            +--> Engine-specific API
\`\`\`

Adapters advertise their actual capabilities for the host to choose from, rather than assuming all engines are alike.

## 12. Common Pitfalls and Checklist

Common misconceptions:

- Thinking Java 17 always has a JavaScript runtime because \`javax.script\` is present.
- Calling \`getEngineByName(...).eval(...)\` without checking for a \`null\` result.
- Treating every engine as thread-safe or assuming every \`Bindings\` instance is self-isolated.
- Believing \`ScriptException\` covers all provider/engine failures.
- Assuming a script runs identically across multiple engines/language versions.
- Putting credentials or high-privilege objects into bindings when running untrusted scripts.
- Not checking \`Compilable\`/\`Invocable\` before casting.
- Not managing class loaders or contexts when hot-reloading scripting plugins.
- Treating \`javax.script\` as a sandbox or assuming it has built-in standard timeouts.

Adoption checklist: identify the required engine; verify discoverability; pin engine/language versions; verify capabilities; clearly define bindings/context and threading; set security boundaries; limit resources; manage lifecycle; test outputs and errors against the actual engine in the target runtime.

**Key takeaway:** \`javax.script\` is Java's **JSR 223 integration API**, whereas an engine is a **language runtime provided by an implementation**. Running scripts requires a compatible engine and an explicit execution policy; the \`java.scripting\` module alone is not enough.

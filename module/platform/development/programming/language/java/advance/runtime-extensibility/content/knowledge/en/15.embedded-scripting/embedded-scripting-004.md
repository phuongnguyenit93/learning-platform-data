# Handling getEngineByName Returning null and Missing Installed Engines

## 1. Understanding the null Result Properly

In JSR 223, \`javax.script.ScriptEngineManager\` is the manager and discovery mechanism for **scripting engines**. The call:

\`\`\`java
ScriptEngine engine =
        new ScriptEngineManager().getEngineByName("JavaScript");
\`\`\`

returns a \`ScriptEngine\` if the manager finds a registered factory supporting the requested name; if none is found, the API **returns \`null\`**. This is a normal outcome of the lookup process, not necessarily an exception or proof that the script itself is faulty.

Distinguish three situations:

1. **No matching engine:** no factory advertising that name was found. \`getEngineByName\` returns \`null\`.
2. **Factory exists but initialization fails:** dependencies, class loading, or factory code fails. An exception or other error may occur depending on the implementation; not every failure should be collapsed into \`null\`.
3. **Engine exists but the script fails to run:** \`eval\` may throw \`ScriptException\`, or runtime execution encounters an error/unsupported capability. This is an execution error, not a discovery error.

If you call \`engine.eval(...)\` immediately after receiving \`null\`, Java will throw a \`NullPointerException\`. Rather than letting a confusing error propagate, the host must check the engine first and return a clear, actionable message.

## 2. Why Might Java 17+ Fail to Find a JavaScript Engine?

The \`java.scripting\` module contains JSR 223 APIs such as \`ScriptEngineManager\`, \`ScriptEngine\`, \`ScriptEngineFactory\`, \`Bindings\`, and \`ScriptException\`; **this module does not mandate or supply a built-in implementation for JavaScript or any other language**.

Important history:

- JDK 8 through JDK 14 shipped the Nashorn JavaScript engine on their respective JDK distributions.
- Nashorn was marked deprecated in JDK 11.
- **Nashorn was removed from the JDK starting in JDK 15** (JEP 372). Therefore, a standard JDK 17 or JDK 21 does not have a pre-installed JSR 223 JavaScript engine simply by virtue of being a JDK.

Names like \`JavaScript\`, \`js\`, or \`ECMAScript\` are **aliases advertised by a factory**. A third-party engine may advertise different aliases or integrate only via its own proprietary API rather than JSR 223. Having the JAR on disk is not enough: the engine must be properly declared and visible to the relevant class loader/module layer.

## 3. Standard Handling Pattern: Check for null Before eval

A simple integration snippet:

\`\`\`java
import javax.script.ScriptEngine;
import javax.script.ScriptEngineManager;
import javax.script.ScriptException;

public class SimpleScriptCall {
    public static void main(String[] args) throws ScriptException {
        ScriptEngineManager manager = new ScriptEngineManager();
        ScriptEngine engine = manager.getEngineByName("JavaScript");

        if (engine == null) {
            System.err.println(
                "JavaScript engine unavailable. Install a compatible JSR 223 engine."
            );
            return;
        }

        Object result = engine.eval("1 + 2");
        System.out.println(result);
    }
}
\`\`\`

Save as **\`SimpleScriptCall.java\`**, run:

\`\`\`bash
javac SimpleScriptCall.java
java SimpleScriptCall
\`\`\`

On JDK 17+ without a JavaScript engine, stderr is:

\`\`\`text
JavaScript engine unavailable. Install a compatible JSR 223 engine.
\`\`\`

The program does not attempt to execute the script when no engine is present. If a compatible engine is present, how \`1 + 2\` is interpreted and the returned value type depend on that engine. This example does not rely on any specific engine and does not claim every environment prints the same result when an engine is installed.

In production applications, replace \`return\` with a **clearly coded configuration error** (for example, \`SCRIPT_ENGINE_UNAVAILABLE\`) or transition the system to a degraded state if scripting is only optional. Do not arbitrarily fall back to another engine with non-equivalent semantics.

## 4. List Actual Factories to Diagnose

Do not guess engine names. List the factories visible to the manager and their supported aliases.

Complete Java 17+ example, file **\`ScriptEngineDiagnostics.java\`**:

\`\`\`java
import javax.script.ScriptEngine;
import javax.script.ScriptEngineFactory;
import javax.script.ScriptEngineManager;
import java.util.Comparator;
import java.util.List;

public final class ScriptEngineDiagnostics {
    private static final String REQUESTED = "JavaScript";

    public static void main(String[] args) {
        ScriptEngineManager manager = new ScriptEngineManager();
        List<ScriptEngineFactory> factories =
                manager.getEngineFactories().stream()
                        .sorted(Comparator.comparing(
                                ScriptEngineFactory::getEngineName))
                        .toList();

        System.out.println("Factory count: " + factories.size());
        for (ScriptEngineFactory factory : factories) {
            System.out.println("Engine: " + factory.getEngineName());
            System.out.println("  Version: " + factory.getEngineVersion());
            System.out.println("  Language: " + factory.getLanguageName());
            System.out.println("  Aliases: " + factory.getNames());
        }

        ScriptEngine engine = manager.getEngineByName(REQUESTED);
        if (engine == null) {
            System.out.println("Lookup JavaScript: unavailable");
        } else {
            ScriptEngineFactory factory = engine.getFactory();
            System.out.println(
                    "Lookup JavaScript: " + factory.getEngineName());
        }
    }
}
\`\`\`

Run:

\`\`\`bash
javac ScriptEngineDiagnostics.java
java ScriptEngineDiagnostics
\`\`\`

On a clean JDK 17+ with no external engine, stdout is:

\`\`\`text
Factory count: 0
Lookup JavaScript: unavailable
\`\`\`

When a JSR 223 engine is installed, the factory count and names/versions depend on the library and environment. Having \`getEngineFactories()\` contain a factory does not guarantee every \`getEngineByName\` call will succeed: match the requested name accurately against \`getNames()\` and check for errors when the factory instantiates the engine.

### Result Interpretation Table

| Result | Most Likely Meaning | Action Needed |
|---|---|---|
| \`Factory count: 0\` | Manager sees no factories | Check runtime dependencies, class loader, and service registration |
| Factory exists, desired alias missing | Lookup name is not advertised | Use an advertised alias, reconfigure the name, avoid guessing |
| Alias exists but engine creation fails | Factory/engine has a runtime issue | Inspect stack trace, dependencies, and compatibility |
| Engine exists, eval fails | Syntax, data, or engine error | Diagnose \`ScriptException\` and root cause separately |
| Works in dev, fails in production | Classpath/module path/packaging differs | Compare actual runtime artifacts and launcher |

## 5. How Is an Engine Installed So the Manager Finds It?

A JSR 223 implementation must supply a \`ScriptEngineFactory\` and publish it via the appropriate provider mechanism.

**On the classpath**, the engine library typically contains:

\`\`\`text
META-INF/services/javax.script.ScriptEngineFactory
\`\`\`

The service file contains the fully qualified name of the factory class. The engine JAR along with its dependencies must be present on the classpath visible to the class loader in use.

**In an explicit module**, the provider can declare it in \`module-info.java\`:

\`\`\`java
module com.example.script.engine {
    requires java.scripting;
    provides javax.script.ScriptEngineFactory
        with com.example.engine.MyEngineFactory;
}
\`\`\`

This is an illustrative descriptor; the actual classes must be implemented to compile and run. The module consuming the API requires \`requires java.scripting;\`.

Some libraries or language engines may **not support JSR 223**, even though they have their own embedding API. Installing a language runtime in general does not guarantee \`ScriptEngineManager\` can see it. Verify the exact engine version's documentation, any JSR 223 bridge artifact (if separate), accompanying dependencies, and supported JDK versions.

**With Gradle/Maven**, adding a dependency to the build is not enough if packaging/runtime drops that dependency. Inspect the actual process classpath, fat JAR shading, \`META-INF/services\` file merging, module-path, and \`jlink\` images. If creating a custom runtime image with \`jlink\`, ensure the API module and provider module are properly included/bound.

## 6. Class Loaders, TCCL, and ServiceLoader

By default, \`ScriptEngineManager()\` uses the class loader attached to the thread context to discover engines via the service provider mechanism. If the host runs inside a container/plugin framework, the thread context class loader (TCCL) may differ from the class loader that loaded the application or the engine JAR.

There is a constructor accepting an explicit loader:

\`\`\`java
ClassLoader engineLoader = /* class loader containing the verified engine */;
ScriptEngineManager manager = new ScriptEngineManager(engineLoader);
\`\`\`

This is an illustrative snippet; the host must construct \`engineLoader\` properly and maintain a valid lifecycle. Using an explicit loader avoids depending on the calling thread's TCCL, though it does not automatically load JARs from arbitrary paths. If an engine JAR is placed into a plugin directory after the process has started, it must be placed into a new loader/layer according to the plugin manager's design; \`getEngineByName\` does not scan filesystem directories on its own.

When troubleshooting discovery errors, record:

- The class loader passed to \`ScriptEngineManager\` and the actual TCCL.
- Location of the engine JAR, its dependencies, and the service provider file.
- Module path and module graph if using JPMS.
- Java/JDK version, engine version, factory aliases, and any package relocation/shading.
- \`ServiceLoader\` error logs or factory initialization failures.

In a module layer environment, do not assume \`ScriptEngineManager\` has an overload accepting a \`ModuleLayer\`; its API only accepts a \`ClassLoader\` or uses the default. Discovery design in JPMS must align with where the engine module is resolved and loaded.

## 7. Do Not Use Engine Name as the Sole Capability Check

An engine's existence alone is not enough to satisfy application needs. After finding one, the host should verify:

1. **Engine/language version:** does it match the stored scripts?
2. **\`Compilable\`:** if scripts must be compiled/cached, does the engine support it?
3. **\`Invocable\`:** if functions must be called after eval, does the engine support it?
4. **Threading:** can instances be shared across requests, or are separate engines/contexts needed?
5. **Host interop and security:** which Java objects can scripts access, and are permissions appropriately restricted?
6. **Resource limits:** are timeouts, cancellation, and memory/CPU bounds available for this specific engine?

Capability check example:

\`\`\`java
// Integration snippet, assuming engine != null.
if (!(engine instanceof javax.script.Compilable)) {
    throw new IllegalStateException("Engine does not support compilation");
}
if (!(engine instanceof javax.script.Invocable)) {
    throw new IllegalStateException("Engine does not support function invocation");
}
\`\`\`

Cast only when the capability is actually implemented. \`ScriptEngineFactory.getParameter("THREADING")\` can indicate the engine's concurrency contract under JSR 223, but you must still evaluate \`Bindings\`, \`ScriptContext\`, and shared Java objects.

## 8. Designing Fail-Fast or Controlled Degradation

Depending on the business role of scripting:

**Required feature:** the host should check for the engine at startup and refuse to mark the application ready if the engine is missing. Emit a message containing the requested name, available engines, and proper installation/configuration steps.

**Optional feature:** disable the related feature and return a clear response such as “Scripting unavailable”, while non-scripting features continue serving normally.

**Multiple supported engines:** fall back only when there is an approved list of alternative engines tested for equivalent semantics. Do not try factories randomly because languages, type conversions, and host access permissions can differ.

Initialization helper pattern with an explicit error:

\`\`\`java
// Integration snippet; caller is responsible for providing manager.
static javax.script.ScriptEngine requireEngine(
        javax.script.ScriptEngineManager manager, String name) {
    javax.script.ScriptEngine engine = manager.getEngineByName(name);
    if (engine == null) {
        throw new IllegalStateException(
                "Required JSR 223 engine is unavailable: " + name);
    }
    return engine;
}
\`\`\`

Separate **missing-engine configuration errors** from **\`ScriptException\` during eval** and dependency/runtime errors. This classification helps operations address the true root cause and avoids retrying an operation that cannot succeed until the engine is installed.

## 9. Checking Packaging and Runtime Environment

An application that runs in an IDE but fails when packaged often has environmental differences:

- The engine JAR is only in development/test dependencies.
- \`META-INF/services/javax.script.ScriptEngineFactory\` was lost or overwritten when building a fat JAR.
- Transitive dependencies of the engine were excluded or hit version conflicts.
- Named modules are not resolved, or module path differs from classpath.
- Custom runtime image is missing modules/providers.
- Class loader isolation or TCCL prevents the manager from seeing the engine.
- JDK version changed: the project relied on Nashorn bundled in an older JDK, while production runs a newer JDK.

A useful diagnostic is running \`ScriptEngineDiagnostics\` **inside the exact process/runtime image** of the application, or integrating an equivalent check into health diagnostics. Inspecting only the build-time dependency tree does not confirm actual runtime discovery.

For plugin hosts, add an automated smoke test: after deploying the final artifact, look up the engine by the desired name, print version metadata, execute a side-effect-free test script, and close/release resources per the engine contract.

## 10. Security: Having an Engine Does Not Mean It Is Safe to eval

Do not automatically download engines from untrusted sources just to stop \`getEngineByName\` from returning \`null\`. Both engines and scripts are executable code. JSR 223 does not provide a uniform sandbox across all engines.

A runtime-extensible application must:

- Verify the provenance, version, and integrity of engine artifacts.
- Restrict who is permitted to install engines and load scripts.
- Never place database clients, credentials, filesystem handles, or high-privilege host objects into \`Bindings\` for untrusted scripts.
- Manage execution timeouts/resources according to engine capabilities; for untrusted scripts, prefer process/container isolation.
- Log engine identity, script ID, results, and errors without leaking sensitive content.
- Have a rollback mechanism and stop accepting requests if a new engine violates the contract.

Separate class loaders and separate module layers help organize code; they are **not a strong enough security boundary** for malicious code inside the same JVM.

## 11. Common Mistakes

- Calling \`engine.eval\` without checking \`engine != null\`.
- Thinking \`java.scripting\` includes a default JavaScript runtime on JDK 17+.
- Changing lookup names randomly without reading \`factory.getNames()\`.
- Installing only the engine JAR while missing dependencies or service registration.
- Testing in an IDE instead of the actual packaged artifact/runtime deployment.
- Failing to recognize differences between classpath, module path, and the manager's class loader.
- Catching \`NullPointerException\` instead of handling a missing engine explicitly.
- Using an engine with an incompatible language/capability as a silent fallback.
- Sharing engines/contexts across threads and tenants without verifying thread safety.
- Treating successful engine discovery as permission to run untrusted scripts.

## 12. Checklist When getEngineByName Returns null

1. Print \`getEngineFactories()\` and each factory's \`getNames()\` list.
2. Check the requested name against advertised aliases.
3. Confirm the right version of the JSR 223 engine bridge is installed in the runtime.
4. Check the JAR, transitive dependencies, and service provider declarations.
5. Verify the manager uses a class loader that can see the engine; inspect TCCL/JPMS.
6. Inspect the final deployment environment (IDE, container, custom runtime).
7. Once an engine is present, verify \`Compilable\`, \`Invocable\`, threading, and required security policies.
8. Choose fail-fast or degraded mode according to how critical the feature is.
9. Add smoke tests and error messages with clear remediation steps.

**Key takeaway:** \`getEngineByName(...) == null\` means **the manager could not find a suitable engine within its current discovery scope**. The proper response is to check factories, aliases, class loaders, and packaging, and then intentionally install a compatible JSR 223 implementation if the feature requires it—never assume an engine is built into the JDK.

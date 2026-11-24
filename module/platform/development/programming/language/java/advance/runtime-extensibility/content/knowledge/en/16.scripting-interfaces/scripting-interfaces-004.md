# Checking Compilable and Reusing CompiledScript with the Corresponding Engine

## 1. Problem: Can Every ScriptEngine Precompile?

In JSR 223 (\`javax.script\`), every \`ScriptEngine\` provides script evaluation via \`eval(...)\`, but **not every engine supports precompilation**. This capability is advertised through the optional \`javax.script.Compilable\` interface.

When a script is executed repeatedly—such as pricing rules, data transformations, or plugin event handlers—repeatedly parsing or preparing the program can waste resources. An engine supporting \`Compilable\` allows creating a \`CompiledScript\` object to re-execute with appropriate \`Bindings\` or \`ScriptContext\` instances.

However, **compiling does not mean compiling Java into a class file**, and not every engine generates machine code. Specifically, how compilation, caching, optimization, and thread safety work is determined by the implementation.

Two main contracts:

\`\`\`java
public interface Compilable {
    CompiledScript compile(String script) throws ScriptException;
    CompiledScript compile(java.io.Reader script) throws ScriptException;
}
\`\`\`

\`\`\`java
public abstract class CompiledScript {
    public abstract Object eval(ScriptContext context) throws ScriptException;
    public Object eval(Bindings bindings) throws ScriptException;
    public Object eval() throws ScriptException;
    public abstract ScriptEngine getEngine();
}
\`\`\`

\`getEngine()\` identifies the engine that created the compiled script object. This is an important relationship: **CompiledScript belongs to the engine that compiled it**, not a universal bytecode format that can be freely moved to another engine.

## 2. Checking Capability Before Casting

The right way to check on Java 17+:

\`\`\`java
ScriptEngine engine = manager.getEngineByName("some-language");

if (engine == null) {
    throw new IllegalStateException("No matching JSR 223 engine");
}

if (!(engine instanceof Compilable compilable)) {
    throw new IllegalStateException("Engine does not implement Compilable");
}

CompiledScript compiled = compilable.compile(scriptSource);
\`\`\`

This snippet is integration code; \`manager\`, \`scriptSource\`, and a compatible engine must be available. There are two distinct failure branches:

- **No engine found**: \`getEngineByName(...)\` returns \`null\`; check dependencies, aliases, service registration, and class loaders.
- **Engine exists but does not support \`Compilable\`**: do not force a cast; you can use \`eval\` directly or reject the feature if compilation is mandatory.

An engine implementing \`Compilable\` can still throw \`ScriptException\` when source code has syntax errors or is rejected by the engine. In addition, implementation or class-loading errors must be recorded separately according to their actual origin.

## 3. Compile Once and Run Many Times

Basic lifecycle:

\`\`\`text
Script source + validated engine
              |
              v
       instanceof Compilable?
          /         \
         no         yes
        |             |
  eval directly    compile(source)
    or reject         |
                      v
                CompiledScript
                   /   |   \
                  v    v    v
               eval  eval  eval
             context A/B/C
\`\`\`

This approach is useful when a relatively stable set of scripts is invoked repeatedly. Its benefit must be measured with benchmarks on the actual engine: compilation can be fast or slow, a compiled object may hold significant state or resources, and some engines already maintain an internal cache during \`eval\`.

Key distinctions to remember:

- **Compile** prepares a re-executable representation of the script.
- **Eval** actually executes the script and may produce side effects.
- **Bindings/ScriptContext** provides inputs, state, and I/O for a given execution.
- **Engine** remains the specific environment and semantics. A compiled script does not live independently of its engine merely because the host holds a reference to it.

## 4. Bindings and ScriptContext on Re-execution

JSR 223 provides three commonly used forms:

\`\`\`java
compiled.eval();
compiled.eval(bindings);
compiled.eval(context);
\`\`\`

Meaning:

1. **\`eval()\`**: executes against the engine's default context, which risks reusing state left behind from a previous run if the engine/context is shared.
2. **\`eval(Bindings)\`**: supplies a dedicated \`ENGINE_SCOPE\` bindings for a single evaluation per the \`CompiledScript\` contract. Suitable when passing different variables across invocations.
3. **\`eval(ScriptContext)\`**: passes a context with scoped bindings and specific \`Reader\`, \`Writer\`, and \`ErrorWriter\`, giving full control over the execution environment.

An integration pattern:

\`\`\`java
// Integration snippet; compiled is created by a compatible engine.
Bindings first = compiled.getEngine().createBindings();
first.put("amount", 10);

Bindings second = compiled.getEngine().createBindings();
second.put("amount", 20);

Object a = compiled.eval(first);
Object b = compiled.eval(second);
\`\`\`

The script must actually use the variable \`amount\` according to the engine language's syntax. There is no universal variable syntax or operation across all languages integrated via JSR 223.

**Bindings do not create a sandbox.** When placing a Java object into bindings, the script can access that object's capabilities according to the engine's interop rules and security policy. Do not share mutable bindings across multiple requests or tenants without controlling concurrency and access rights.

## 5. Complete Java 17+ Example Without External Engine Dependencies

JDK 17 and later do not require a bundled JSR 223 JavaScript engine. To demonstrate the exact compile and eval APIs on any standard JDK 17+ containing the \`java.scripting\` module, the program below creates a minimal engine that **only supports adding two integer variables \`a + b\`**. This is a learning engine, not a JavaScript engine or a general-purpose parser.

Save as **\`CompiledScriptDemo.java\`**:

\`\`\`java
import java.io.Reader;
import java.io.IOException;
import java.util.regex.Pattern;
import javax.script.*;

public class CompiledScriptDemo {
    static final class AddEngine extends AbstractScriptEngine
            implements Compilable {
        private static final Pattern SOURCE =
                Pattern.compile("\\s*a\\s*\\+\\s*b\\s*");

        @Override
        public Object eval(String script, ScriptContext context)
                throws ScriptException {
            return compile(script).eval(context);
        }

        @Override
        public Object eval(Reader reader, ScriptContext context)
                throws ScriptException {
            try {
                StringBuilder source = new StringBuilder();
                char[] buffer = new char[1024];
                int count;
                while ((count = reader.read(buffer)) != -1) {
                    source.append(buffer, 0, count);
                }
                return eval(source.toString(), context);
            } catch (IOException e) {
                throw new ScriptException(e);
            }
        }

        @Override
        public Bindings createBindings() {
            return new SimpleBindings();
        }

        @Override
        public ScriptEngineFactory getFactory() {
            return null; // Do not register a factory: internal example only.
        }

        @Override
        public CompiledScript compile(String script)
                throws ScriptException {
            if (!SOURCE.matcher(script).matches()) {
                throw new ScriptException("Only a + b is supported");
            }
            return new AddCompiledScript(this);
        }

        @Override
        public CompiledScript compile(Reader script)
                throws ScriptException {
            try {
                StringBuilder source = new StringBuilder();
                char[] buffer = new char[1024];
                int count;
                while ((count = script.read(buffer)) != -1) {
                    source.append(buffer, 0, count);
                }
                return compile(source.toString());
            } catch (IOException e) {
                throw new ScriptException(e);
            }
        }
    }

    static final class AddCompiledScript extends CompiledScript {
        private final AddEngine engine;

        AddCompiledScript(AddEngine engine) {
            this.engine = engine;
        }

        @Override
        public Object eval(ScriptContext context) throws ScriptException {
            Object left = context.getAttribute("a");
            Object right = context.getAttribute("b");
            if (!(left instanceof Integer a) ||
                !(right instanceof Integer b)) {
                throw new ScriptException("a and b must be Integer");
            }
            return Math.addExact(a, b);
        }

        @Override
        public ScriptEngine getEngine() {
            return engine;
        }
    }

    public static void main(String[] args) throws ScriptException {
        ScriptEngine engine = new AddEngine();

        if (!(engine instanceof Compilable compilable)) {
            throw new IllegalStateException("Compile not supported");
        }

        CompiledScript compiled = compilable.compile("a + b");
        System.out.println("same engine: " +
                (compiled.getEngine() == engine));

        Bindings first = engine.createBindings();
        first.put("a", 10);
        first.put("b", 5);
        System.out.println("first: " + compiled.eval(first));

        Bindings second = engine.createBindings();
        second.put("a", 7);
        second.put("b", 8);
        System.out.println("second: " + compiled.eval(second));
    }
}
\`\`\`

Run:

\`\`\`bash
javac CompiledScriptDemo.java
java CompiledScriptDemo
\`\`\`

Stdout:

\`\`\`text
same engine: true
first: 15
second: 15
\`\`\`

In this example, \`compile("a + b")\` validates the expression once and returns an object holding a reference to the exact \`AddEngine\`. The two \`eval(Bindings)\` calls use different variable sets with the same compiled logic.

This example only demonstrates the API contract. \`getFactory()\` returns \`null\` because the engine is not published via \`ScriptEngineManager\`; a production engine needs a proper \`ScriptEngineFactory\`, full script language handling, validation, resource lifecycle management, and security.

## 6. Can a CompiledScript Be Used with Another Engine?

**Do not treat \`CompiledScript\` as an engine-neutral artifact.** The \`CompiledScript.getEngine()\` API returns the engine that compiled the script, and \`eval(...)\` is a method on that compiled artifact itself.

Mental model:

\`\`\`text
Engine A --compile--> CompiledScript A --eval(context A)--> result
Engine B --compile--> CompiledScript B --eval(context B)--> result
\`\`\`

There is no standard \`engineB.eval(compiledFromA)\` API. Two engines may have different syntax, data types, namespaces, host interop, and internal representations. Even two instances of **the same implementation** do not inherently share compiled objects: they may hold independent runtime contexts, caches, or bytecode.

Valid reuse generally involves:

- The same \`CompiledScript\` and its corresponding engine.
- Fresh \`Bindings\`/\`ScriptContext\` objects accepted by the engine.
- Unchanged engine and language version context.
- Thread-safety guarantees satisfied per the engine's documentation.
- A compiled object lifetime that does not outlive the engine/plugin lifecycle.

With hot reload, a new engine or class loader must **recompile from source** in the new environment. Do not attempt to carry over references from the old engine into the new runtime.

## 7. Safe Compiled Script Caching

A cache typically requires a composite key:

\`\`\`text
(engine identity/version,
 language version,
 script id + source digest,
 compile options,
 tenant/security scope if it affects compilation)
\`\`\`

If you only use \`scriptId\`, the cache may return an artifact from an older engine version after the host updates a plugin. If the source changes without the ID changing, results will also be wrong. In multi-tenant systems, certain scripts belong only to specific tenants; keys and access permissions must be enforced before returning a compiled artifact.

Necessary policies:

1. **Compile on demand** or warm up approved scripts, avoiding unbounded compilation when users submit arbitrary scripts.
2. **Bounded cache** by entry count, memory footprint, TTL, or appropriate quota. Do not keep every compiled script forever.
3. **Single-flight compile** when multiple requests concurrently ask for an uncached script, ensuring this mechanism cannot deadlock.
4. **Invalidate** when source, engine version, compile options, security policy, or plugin layer changes.
5. **Cleanup** when disabling an engine; clear references to \`CompiledScript\`, \`ScriptEngine\`, \`Bindings\`, and loaders to avoid resource/hot-reload leaks.
6. **Metrics**: compile latency, eval latency, cache hit/miss, parse/runtime errors, and memory usage.

**Do not equate a thread-safe cache with thread-safe eval.** A \`ConcurrentHashMap\` can protect the cache structure, but the retrieved \`CompiledScript\`/engine object may not support concurrent evaluation. Follow the engine's concurrency contract: synchronize calls, create an engine/context per request, or maintain an appropriate instance pool.

## 8. State and Concurrency Issues

There is no universal guarantee that every \`ScriptEngine\` or \`CompiledScript\` from every vendor is thread-safe. Some implementations store variables, functions, compiled state, or global objects inside the engine.

JSR 223 allows an engine to advertise concurrency information via:

\`\`\`java
Object threading =
        engine.getFactory().getParameter("THREADING");
\`\`\`

Conventional values include \`MULTITHREADED\`, \`THREAD-ISOLATED\`, and \`STATELESS\`. If the value is \`null\`, you cannot assume the engine supports concurrent execution. This metadata must be read alongside the actual version's documentation; it is not a substitute for race and state-isolation testing.

If caching a compiled script while running concurrently across multiple requests:

- Isolate \`Bindings\` between requests.
- Do not pass shared mutable Java objects without synchronization.
- Bound the number of parallel \`eval\` calls according to engine capabilities.
- Never share tenant A's context with tenant B.
- Restore thread-local/MDC/context class loader after each plugin call if modified.
- Do not allow timeout/cancellation to terminate a request while the engine continues holding unmanaged resources.

## 9. Stage-by-Stage Error Handling

Clearly separate error categories:

| Stage | Scenario | Handling |
|---|---|---|
| Discovery | \`getEngineByName\` returns \`null\` | Check installed engine, aliases, class loader |
| Capability | Engine is not \`instanceof Compilable\` | Call \`eval\` directly or reject the feature |
| Compilation | \`compile\` throws \`ScriptException\` | Report source/line error; do not cache |
| Evaluation | \`compiled.eval\` fails | Record execution failure; inspect side effects |
| Configuration | Bindings/context missing or wrong type | Validate input before eval |
| Runtime lifecycle | Engine replaced or stopped | Do not use old compiled objects; recompile |

\`ScriptException\` may contain file, line, and column information if provided by the engine. Avoid logging full source code that contains sensitive data or exposing internal stack traces to end users.

For scripts that have side effects, do not blindly retry eval upon an exception: partial work may already have occurred. Apply idempotency and transaction/compensation policies as appropriate.

## 10. Security and Plugin Boundaries

\`Compilable\` is a capability for preparing and running code, **not a sandboxing tool**. Untrusted scripts can still access host objects and resources depending on the engine.

Key principles:

- Verify the origin, version, and integrity of engine/plugin artifacts.
- Restrict script access to Java objects and the file system/network/process via engine mechanisms or OS-level boundaries.
- Never place credentials, \`DataSource\`, database clients, or high-privilege internal services into untrusted \`Bindings\`.
- Limit execution time, resources, and source length; note that an engine does not necessarily support cancellation to stop running code.
- For untrusted code, consider running in a separate process/container with explicit control protocols and timeouts.
- Do not rely solely on a class loader or module layer as a security boundary.

In a plugin host, a script may hold references to engine objects or class loaders; caches and callbacks must be released when the plugin stops.

## 11. Common Pitfalls

- Casting \`(Compilable) engine\` without checking capability first.
- Calling methods on \`null\` because no matching JSR 223 engine exists at runtime.
- Assuming compilation improves performance in every case without benchmarking.
- Sharing a \`CompiledScript\` across different engines or runtime versions.
- Calling \`eval()\` on the default context and accidentally reusing variables from a previous request.
- Reusing the same mutable \`Bindings\` across threads or tenants.
- Caching by script ID while ignoring source hash and engine version.
- Forgetting invalidation/cleanup during plugin hot reload.
- Assuming \`CompiledScript\` is serialized bytecode that can run on another JVM.
- Failing to distinguish compilation errors from execution errors and capability errors.
- Assuming the engine implementation or compiled script automatically guarantees thread safety.

## 12. Adoption Checklist

Before choosing the compiled-script path:

1. Has the corresponding JSR 223 engine been located and checked for \`engine != null\`?
2. Does the engine actually implement \`Compilable\`?
3. Are script source/syntax and dependencies validated at compile time?
4. Does compiling once deliver a measurable real-world performance benefit?
5. Is the compiled object kept together with the engine that created it?
6. Do the \`Bindings\`/\`ScriptContext\` per eval have sufficient data without tenant leakage?
7. Do the engine and compiled script support concurrency for the intended usage?
8. Does the cache have appropriate keys, quotas, invalidation, and cleanup?
9. Are error handling, timeouts, resource limits, and security policies in place for script execution?
10. When replacing a plugin/engine, are old artifacts discarded and sources recompiled?

**Remember:** check \`engine instanceof Compilable\` before compiling; keep \`CompiledScript\` tied to **the engine that created it**; reuse it with appropriate bindings/context and manage thread safety, caching, security, and lifecycle.

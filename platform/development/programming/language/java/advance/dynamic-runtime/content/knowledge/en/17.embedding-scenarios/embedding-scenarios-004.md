# 17.4 Passing Java Data via Bindings, ScriptContext, and Variable Scopes

**Module:** Java Advance - dynamic-runtime  
**Parent Topic:** 17. Embedding Scenarios  
**Focus APIs:** `javax.script.Bindings`, `ScriptContext`, `SimpleBindings`, `SimpleScriptContext`, `ScriptEngine`, `ScriptEngineManager`.  
**Platform:** Java 17 and later (JSR-223 / `java.scripting` module).

## Learning Objectives

When embedding a scripting language into a Java application, it is necessary to pass data from the host into script code, retrieve return results, and control which variables belong only to a single execution and which variables are shared. **`Bindings`** holds name–value pairs; **`ScriptContext`** manages those `Bindings` by scope, along with the script's input/output; **`ScriptEngine`** is the specific execution engine that uses that context to run a language.

After this lesson, you can:

1. Distinguish `Bindings`, `ScriptContext`, `ScriptEngine`, and `ScriptEngineManager`, and understand the flow of passing Java objects into a script and receiving values back.
2. Predict name lookup results when both `ENGINE_SCOPE` and `GLOBAL_SCOPE` define the same variable; understand how a `null` value differs from a non-existent variable.
3. Use `setAttribute`/`getAttribute`/`getAttributesScope`, `getBindings`/`setBindings`, and `removeAttribute` with the right scope.
4. Distinguish `engine.put/get`, `engine.setBindings`, `engine.eval(script, bindings)`, and `engine.eval(script, context)`.
5. Design a dedicated context per request, and know what is actually shared when sharing `GLOBAL_SCOPE` or the same Java object.
6. Use `ScriptEngineManager` to discover providers without assuming Java 17 includes a built-in JavaScript engine.
7. Compile/run Java 17 examples **without an external script engine**, then run the optional example when a JavaScript JSR-223 provider is available.
8. Recognize risks regarding data lifecycle, concurrency, script injection, host object capabilities, and security.

## 1. Four Layers of the Embedded Scripting API

The JDK provides the JSR-223 API in the `java.scripting` module, but **having the API does not mean an execution language is built in**.

| Component | Role | When to use? |
| --- | --- | --- |
| `Bindings` | A `Map<String,Object>` map to associate script names with Java values | Preparing `user`, `config`, `requestId`, callable host objects |
| `ScriptContext` | Groups `Bindings` by scope, controls name lookup, `Reader`/`Writer`/error writer | Each request/session needs an isolated context and output |
| `ScriptEngine` | Executes scripts of a specific language, accepting `ScriptContext` or `Bindings` | `engine.eval(...)`, `engine.put/get(...)` |
| `ScriptEngineManager` | Discovers/instantiates `ScriptEngineFactory` via the provider mechanism, maintains manager global bindings | Selecting an engine by name/extension/MIME type and configuring default sharing |

Data model:

~~~text
Java host
  |
  | new SimpleBindings(), put("user", javaObject)
  v
Bindings: { user -> Java object, locale -> "vi" }
  |
  | ScriptContext.setBindings(bindings, ENGINE_SCOPE)
  | ScriptContext.setBindings(global, GLOBAL_SCOPE)
  v
ScriptContext
  |-- ENGINE_SCOPE (100) : higher priority
  |-- GLOBAL_SCOPE (200) : used only if the previous scope does not declare the name
  |-- Reader / Writer / ErrorWriter
  |
  | engine.eval(scriptText, context)
  v
Specific ScriptEngine provider
  |
  | Script sees variables according to provider conventions
  v
Java Object result or ScriptException
~~~

**Key point:** `Bindings` is not a script itself, `ScriptContext` is not an interpreter, and `ScriptEngineManager` does not run JavaScript either. They are contract/integration layers for engines provided by developers/runtime.

Since Java 15, Nashorn has been removed from the JDK per JEP 372. On standard Java 17, `new ScriptEngineManager().getEngineByName("JavaScript")` **can return `null`** (and usually does if no provider is installed). If GraalJS JSR-223 or a third-party engine is configured, the result will differ. You should not infer whether an engine exists from `java -version` alone; check the providers actually discovered.

## 2. `Bindings` Is a Map with Attribute Names as Keys

`javax.script.Bindings` extends `Map<String,Object>`. A `SimpleBindings` object is the basic way to hold name–value pairs:

~~~java
Bindings values = new SimpleBindings();
values.put("user", "An");
values.put("attempts", 3);
values.put("active", true);
~~~

This snippet needs to be placed in a class with `import javax.script.*;` (or equivalent imports).

Meaning:

- **Keys** are Strings; values are Java `Object`s (which can be `String`, boxed primitives, `List`, `Map`, domain objects, or `null`).
- `Bindings` only holds a **reference** to the Java value; it does not automatically deep-copy/serialize the object. Mutating a mutable object can be observed across multiple contexts if they hold the same reference.
- `SimpleBindings` validates keys according to the contract: do not pass null/empty/non-String in operations that require a key. Do not use a map of untrusted input data as an arbitrary set of variable names without validation.
- `Bindings` does not represent **a scope** on its own. It becomes ENGINE or GLOBAL when attached to a `ScriptContext` via `setBindings`, or supplied to an `eval` overload.
- Whether a script can access a Java object using syntax like `user.name`, call getters, methods, or fields depends on the **language engine** and the provider's host interoperability policy. The API only passes references; it **does not guarantee every engine will interpret every Java object in the same way**.

### 2.1. `put` and `setAttribute`: Two Ways to Manipulate the Same Map

If a context already has `Bindings` attached:

~~~java
Bindings engineValues = context.getBindings(ScriptContext.ENGINE_SCOPE);
engineValues.put("user", "An");
context.setAttribute("user", "Binh", ScriptContext.ENGINE_SCOPE);
~~~

These two operations update the same map. `context.getAttribute("user")` will then return `"Binh"` unless other engine logic intervenes.

This is an illustrative snippet with an already initialized `context`. `setAttribute(name, value, scope)` differs from `getAttribute(name)`: when **writing**, you must specify the scope; when reading without specifying a scope, the context searches in priority order.

### 2.2. Map Identity and Lifecycle

Two contexts may contain:

- Two **separate** `SimpleBindings` for ENGINE_SCOPE: updates in one request do not appear in the other.
- **The same `Bindings` object** in GLOBAL_SCOPE: updates from context A can become visible in context B.
- Two separate maps where each map references **the same mutable object**: even though the key/value maps are separate, the shared object can still be mutated across requests.

Therefore, you must not conclude “each request has a new map, so all state is definitely isolated”. Isolation must consider **scope maps**, the **object graph**, **engine internals**, and concurrency.

## 3. `ScriptContext` and the Two Standard Scopes

`ScriptContext` defines two standard scopes:

| Constant | Value | Typical Meaning |
| --- | ---: | --- |
| `ScriptContext.ENGINE_SCOPE` | **100** | Variables bound to the engine or evaluation context; has **higher lookup priority** |
| `ScriptContext.GLOBAL_SCOPE` | **200** | Default shared variables per context/manager when attached; visible only when no key with the same name exists in ENGINE_SCOPE |

**Ascending** numeric order corresponds to **descending priority**. With `SimpleScriptContext`, `getScopes()` returns the ordered list `[100, 200]`.

~~~text
getAttribute("theme")
   |
   +-- Does ENGINE_SCOPE contain key "theme"?
   |      |
   |      +-- Yes -> return value in ENGINE_SCOPE (including null)
   |
   +-- No -> Does GLOBAL_SCOPE contain key "theme"?
          |
          +-- Yes -> return value in GLOBAL_SCOPE
          +-- No -> null
~~~

`GLOBAL_SCOPE` **does not automatically** mean “global for the entire JVM” or “global for every engine in the process”. It is a namespace **attached** to a `ScriptContext`. When using `ScriptEngineManager`, the manager has shared bindings and normally attaches them to engines that it creates itself. If you create `SimpleScriptContext` manually or call `engine.setContext(...)` yourself, you must manage the global scope yourself.

### 3.1. `getAttribute(name)` and `getAttribute(name, scope)`

~~~java
Object resolved = context.getAttribute("theme");
Object local = context.getAttribute("theme", ScriptContext.ENGINE_SCOPE);
Object shared = context.getAttribute("theme", ScriptContext.GLOBAL_SCOPE);
~~~

- `getAttribute("theme")` returns the value in the **first scope that contains the name**.
- `getAttribute("theme", ENGINE_SCOPE)` reads only that scope's map, without falling back to global.
- `getAttribute("theme", GLOBAL_SCOPE)` reads only global, without being shadowed by local.
- If the key is absent from all scopes, `getAttribute(name)` returns `null`.

### 3.2. Distinguishing a **Key with a Null Value** from a **Missing Key**

A very practical pitfall:

~~~java
context.setAttribute("theme", null, ScriptContext.ENGINE_SCOPE);
Object value = context.getAttribute("theme");
int scope = context.getAttributesScope("theme");
~~~

If GLOBAL_SCOPE contains `"theme"="global"`, the result is still:

~~~text
value == null
scope == 100
~~~

Because `ENGINE_SCOPE` **already declared the name** (even with a null value), global is **shadowed**. When you want global to appear again, you must **remove the key at the higher scope**, not just set it to null:

~~~java
context.removeAttribute("theme", ScriptContext.ENGINE_SCOPE);
Object after = context.getAttribute("theme");  // "global"
~~~

`getAttributesScope(name)` returns the lowest scope number containing that name, or **`-1`** if it is not present in any scope. This is the official way to distinguish between “null value” and “undeclared”.

### 3.3. `getBindings` and `setBindings`

~~~java
Bindings local = new SimpleBindings();
local.put("requestId", "req-1");
context.setBindings(local, ScriptContext.ENGINE_SCOPE);

Bindings global = new SimpleBindings();
global.put("region", "VN");
context.setBindings(global, ScriptContext.GLOBAL_SCOPE);
~~~

- `setBindings` **attaches/replaces the entire map** at that scope; it does not merge keys one by one into the old map.
- Code that still holds a reference to the old map will not automatically see the new map after `setBindings` replaces it.
- With `SimpleScriptContext`, the engine scope needs a suitable `Bindings`; the global scope may be unattached or unset.
- Putting the same `Bindings` into two contexts **intentionally shares the entire map**; no secret copy is made.

**Design rule:** a new request should start with a fresh ENGINE_SCOPE map. Only put values that can truly be shared and match access permissions into GLOBAL_SCOPE.

## 4. `ScriptEngine`: Ways to Pass Data into Script Execution

`ScriptEngine` receives data via its default context or via a context/bindings passed directly for each evaluation.

### 4.1. `engine.put` and `engine.get`

~~~java
engine.put("user", "An");
Object user = engine.get("user");
~~~

- `ScriptEngine`'s `put/get` operates on the **ENGINE_SCOPE bindings of the engine's default context**.
- `engine.put` is convenient for a simple interactive session, but if multiple requests share an engine, state can persist across evaluations.
- `engine.get("user")` is not a command that searches all scopes like `engine.getContext().getAttribute("user")`. A name present only in GLOBAL_SCOPE can still be seen via context lookup, but is not necessarily present in `engine.get`.
- `engine.setBindings(bindings, ENGINE_SCOPE)` replaces **one scope of the default context**; it differs from supplying bindings for a single eval call only.

This snippet assumes a valid `ScriptEngine engine`; JDK 17 does not guarantee a provider exists.

### 4.2. `eval(script)`: Using the Default Context

~~~java
Object result = engine.eval("user");
~~~

This is just an example with an engine that **understands the expression `user`** and has that variable. Script language/syntax is not defined by JSR-223; a different provider may require different syntax.

A call without a context parameter normally uses the engine's default context. If you called `engine.put("user","An")`, the engine can see that value through the bindings of the engine's default context according to provider conventions.

### 4.3. `eval(script, Bindings)`: Replacing ENGINE_SCOPE for **That Evaluation**

~~~java
Bindings request = engine.createBindings();
request.put("user", "Binh");
Object result = engine.eval("user", request);
~~~

`ScriptEngine.eval(String, Bindings)` contract: uses `request` as the **ENGINE_SCOPE for this evaluation**. With the `AbstractScriptEngine` implementation, a temporary `ScriptContext` is created taking ENGINE_SCOPE from the argument, while other scopes, reader, and writers are inherited from the default context.

**Do not confuse with `engine.setBindings(request, ENGINE_SCOPE)`:** the `eval(script, request)` overload does not permanently replace the ENGINE_SCOPE of the engine's default context. However, if the script modifies the `request` map or objects inside the map, that map/object itself remains modified after eval. “Temporary context” does not mean objects are deep-copied or side effects are automatically rolled back.

### 4.4. `eval(script, ScriptContext)`: Passing **Full Scopes and I/O**

~~~java
ScriptContext requestContext = new SimpleScriptContext();
requestContext.setBindings(new SimpleBindings(), ScriptContext.ENGINE_SCOPE);
requestContext.setBindings(new SimpleBindings(), ScriptContext.GLOBAL_SCOPE);
requestContext.setAttribute("user", "An", ScriptContext.ENGINE_SCOPE);
Object result = engine.eval("user", requestContext);
~~~

This way, the caller decides:

- Which ENGINE_SCOPE map is used for the request;
- Which GLOBAL_SCOPE map is visible (can be shared or isolated);
- The script's `Reader` / `Writer` / `ErrorWriter`;
- Context metadata such as `ScriptEngine.FILENAME` or keys according to the provider's contract.

`engine.eval(script, requestContext)` **does not require** calling `engine.setContext(requestContext)` beforehand. You should avoid engine-wide `setContext` if you want per-request isolation and the engine may be reused.

### 4.5. Other Overloads

`ScriptEngine` also has `eval(Reader)`, `eval(Reader, Bindings)`, and `eval(Reader, ScriptContext)`. They differ only in that the **script source** is a `Reader` instead of a String; the rules for scopes and metadata remain corresponding. When using a `Reader`, the host must manage its lifecycle and close the input properly.

An engine may additionally provide `Invocable` to call functions defined in a script, or `Compilable` to cache a compiled script; **not every engine implements these two optional interfaces**. Do not make host code strictly depend on them without checking `instanceof`.

## 5. `ScriptEngineManager`: Global State and Provider Discovery

Use the manager to find an engine:

~~~java
ScriptEngineManager manager = new ScriptEngineManager();
ScriptEngine engine = manager.getEngineByName("JavaScript");
if (engine == null) {
    System.out.println("No JavaScript JSR-223 provider installed");
}
~~~

This is an illustrative Java snippet inside a class that imports `javax.script.*`. Whether the name `"JavaScript"` is recognized by a provider depends on the provider/registration.

`ScriptEngineManager` uses `ServiceLoader` to find `ScriptEngineFactory` on the classpath/module path matching the class loader. You can check:

~~~java
for (ScriptEngineFactory factory : manager.getEngineFactories()) {
    System.out.println(factory.getEngineName() + ": " + factory.getNames());
}
~~~

Do not expect a fixed output, because the list of providers depends on the environment. Verify that the **correct JSR-223 provider artifact** and the engine's runtime dependencies are installed. A language execution library does not necessarily register a `ScriptEngineFactory` per JSR-223 automatically.

### 5.1. Manager Global Is Not Global to Every Manager

~~~java
manager.put("region", "VN");
Bindings global = manager.getBindings();
~~~

Engines created by this manager can receive/globally share those default bindings. However:

- Another `new ScriptEngineManager()` is a different manager and does not automatically inherit the map just created.
- Engines created directly outside a manager or manually created contexts do not automatically belong to the same global map.
- `manager.put` modifies the manager's global map; it is **not** equivalent to `engine.put` (a default ENGINE_SCOPE).
- `manager.getBindings()` returns the **live map**, not an immutable snapshot.
- Global may contain highly privileged objects; do not put sensitive APIs there when not every script created through the manager is trusted.

### 5.2. The Scope Name “GLOBAL” Does Not Create Transactions, a Sandbox, or Thread Safety

GLOBAL_SCOPE is a data-sharing channel; it does not guarantee an atomic snapshot and does not mean scripts run sequentially. If request A and B share a mutable global map, changing `region` or `user` in one request can affect the other request.

You should distinguish:

- **Read-only or immutable** configuration values: can be safer to share, depending on content.
- Mutable objects with shared state: must use synchronization/immutability/copying or partitioning.
- User info, tenant, token, request-private data: put only in the request's scope and verify objects are not shared across tenants.
- `SimpleBindings` uses a regular mutable Map; it is not thread-safe by default.

## 6. Standalone Java 17 Demo: Scope, Shadowing, Null, and Sharing

This example **does not require installing a JavaScript/Groovy/GraalJS engine**. It exercises the data part of JSR-223 directly on `SimpleScriptContext` and `SimpleBindings`. Afterward, there is an `eval` demo if the environment has a provider.

**File:** `BindingsScopeDemo.java`

~~~java
import javax.script.Bindings;
import javax.script.ScriptContext;
import javax.script.ScriptEngineManager;
import javax.script.SimpleBindings;
import javax.script.SimpleScriptContext;

public final class BindingsScopeDemo {
    public static void main(String[] args) {
        Bindings sharedGlobal = new SimpleBindings();
        sharedGlobal.put("language", "vi");
        sharedGlobal.put("theme", "global");

        ScriptContext first = new SimpleScriptContext();
        ScriptContext second = new SimpleScriptContext();
        first.setBindings(sharedGlobal, ScriptContext.GLOBAL_SCOPE);
        second.setBindings(sharedGlobal, ScriptContext.GLOBAL_SCOPE);
        first.setBindings(new SimpleBindings(), ScriptContext.ENGINE_SCOPE);
        second.setBindings(new SimpleBindings(), ScriptContext.ENGINE_SCOPE);

        System.out.println("scopes=" + first.getScopes());
        System.out.println("first.theme.initial=" + first.getAttribute("theme"));
        first.setAttribute("theme", "engine", ScriptContext.ENGINE_SCOPE);
        System.out.println("first.theme.override=" + first.getAttribute("theme"));
        System.out.println("first.theme.scope=" + first.getAttributesScope("theme"));
        System.out.println("second.theme=" + second.getAttribute("theme"));

        first.setAttribute("theme", null, ScriptContext.ENGINE_SCOPE);
        System.out.println("nullShadowsGlobal=" +
                (first.getAttribute("theme") == null
                && first.getAttributesScope("theme") == ScriptContext.ENGINE_SCOPE));
        first.removeAttribute("theme", ScriptContext.ENGINE_SCOPE);
        System.out.println("first.theme.restored=" + first.getAttribute("theme"));

        Bindings firstEngine = first.getBindings(ScriptContext.ENGINE_SCOPE);
        firstEngine.put("user", "An");
        System.out.println("first.user=" + first.getAttribute("user"));
        System.out.println("second.user.scope=" + second.getAttributesScope("user"));
        first.setAttribute("user", "Binh", ScriptContext.ENGINE_SCOPE);
        System.out.println("bindingsAreLive=" + firstEngine.get("user"));
        sharedGlobal.put("language", "en");
        System.out.println("second.language=" + second.getAttribute("language"));
        System.out.println("globalShared=" +
                (first.getBindings(ScriptContext.GLOBAL_SCOPE)
                        == second.getBindings(ScriptContext.GLOBAL_SCOPE)));

        ScriptEngineManager manager = new ScriptEngineManager();
        manager.getBindings().put("app", "demo");
        System.out.println("manager.app=" + manager.getBindings().get("app"));
    }
}
~~~

### 6.1. Running with Java 17+

From the directory containing `BindingsScopeDemo.java`:

~~~bash
javac --release 17 -d out BindingsScopeDemo.java
java -cp out BindingsScopeDemo
~~~

Install JDK 17+; no extra JARs or engine providers are needed. `SimpleScriptContext` and `ScriptEngineManager` are components included in the JDK's `java.scripting` module.

**Exact stdout verified by compiling/running:**

~~~text
scopes=[100, 200]
first.theme.initial=global
first.theme.override=engine
first.theme.scope=100
second.theme=global
nullShadowsGlobal=true
first.theme.restored=global
first.user=An
second.user.scope=-1
bindingsAreLive=Binh
second.language=en
globalShared=true
manager.app=demo
~~~

### 6.2. Step-by-Step Explanation

- `scopes=[100, 200]` confirms the two standard scopes in priority order.
- `first.theme.initial=global` because `first`'s ENGINE_SCOPE has not declared `theme`; lookup falls back to GLOBAL_SCOPE.
- `first.theme.override=engine`: when `first` declares `theme` in ENGINE_SCOPE, that value takes priority over global. `first.theme.scope=100` indicates the first scope containing the key.
- `second.theme=global`: `second`'s ENGINE_SCOPE is an independent map; `first`'s local update does not appear in `second`.
- `nullShadowsGlobal=true`: a binding with a null value still counts as declaring the name in the higher scope. To fall back to global, you must call `removeAttribute`.
- `first.theme.restored=global`: removing the local key makes the global value visible again.
- `first.user=An` and `bindingsAreLive=Binh`: `Bindings` is a live map, not a snapshot of the `getBindings` result.
- `second.user.scope=-1` proves that key `user` is not declared in any scope of the second context.
- `second.language=en` and `globalShared=true`: both contexts were attached to **the same** `Bindings` object, so global updates through that map are seen by context B.
- `manager.app=demo`: `ScriptEngineManager` can still manage global bindings even when the environment has no specific `ScriptEngine` installed.

### 6.3. Changing the Sharing Rule to Experiment

Replace:

~~~java
second.setBindings(sharedGlobal, ScriptContext.GLOBAL_SCOPE);
~~~

with:

~~~java
Bindings isolated = new SimpleBindings();
isolated.put("language", "vi");
isolated.put("theme", "global");
second.setBindings(isolated, ScriptContext.GLOBAL_SCOPE);
~~~

These are **two snippets to swap in the demo file**, not two separate files. Then `globalShared=false`, and after `sharedGlobal.put("language","en")`, `second.language` remains `vi`. This clearly shows that “GLOBAL” is **a map you actively share**, not an automatic VM-wide global area.

## 7. Script Execution Demo When a JSR-223 Provider Is Available

Java 17 does not necessarily have a JavaScript `ScriptEngine` installed. Therefore, this example is written so it **does not throw a NullPointerException when the engine is absent**. Executing the JavaScript expression requires a compatible JSR-223 provider; if no provider is installed, the program simply reports the missing engine.

**File:** `OptionalJavaScriptEngineDemo.java`

~~~java
import javax.script.Bindings;
import javax.script.ScriptContext;
import javax.script.ScriptEngine;
import javax.script.ScriptEngineManager;
import javax.script.ScriptException;
import javax.script.SimpleBindings;
import javax.script.SimpleScriptContext;

public final class OptionalJavaScriptEngineDemo {
    public static void main(String[] args) throws ScriptException {
        ScriptEngineManager manager = new ScriptEngineManager();
        ScriptEngine engine = manager.getEngineByName("JavaScript");
        if (engine == null) {
            System.out.println("no-jsr223-javascript-engine");
            return;
        }

        Bindings global = new SimpleBindings();
        global.put("region", "VN");

        Bindings request = engine.createBindings();
        request.put("user", "An");
        request.put("region", "HCM");

        ScriptContext context = new SimpleScriptContext();
        context.setBindings(global, ScriptContext.GLOBAL_SCOPE);
        context.setBindings(request, ScriptContext.ENGINE_SCOPE);

        Object result = engine.eval("user + ':' + region", context);
        System.out.println("result=" + result);

        Object temporary = engine.eval("user + ':' + region", request);
        System.out.println("temporary=" + temporary);
        System.out.println("persistentUser=" + engine.get("user"));
    }
}
~~~

Compile/run commands:

~~~bash
javac --release 17 -d out OptionalJavaScriptEngineDemo.java
java -cp out OptionalJavaScriptEngineDemo
~~~

**When no JavaScript provider is available**, verified stdout:

~~~text
no-jsr223-javascript-engine
~~~

**When a suitable provider is available**, the remaining branch executes the JavaScript expression `user + ':' + region`. With the bindings attached in the context, the expected result of the first eval is `An:HCM`, because `region="HCM"` in ENGINE_SCOPE shadows `region="VN"` in GLOBAL_SCOPE. The call `eval(..., request)` uses `request` as the ENGINE_SCOPE for that single run without changing the engine's default scope; `engine.get("user")` reads the default ENGINE_SCOPE, not `request`.

**No “exact stdout” is given for the branch with a provider**, because presence, object wrapping, and JS host interop policies can differ. A provider may use an alias name other than `"JavaScript"` or require separate module/classpath configuration. **Compiling** the program does not require a provider; only **executing the script** does.

### 7.1. Distinguishing the Three Evaluation Calls

~~~java
engine.eval(source);           // engine's default ScriptContext
engine.eval(source, bindings); // temporary ENGINE_SCOPE for the evaluation
engine.eval(source, context);  // ScriptContext provided by the caller
~~~

This is a syntax example with `source`/`bindings`/`context` variables already declared, not a standalone program.

| Call | ENGINE_SCOPE Used | GLOBAL_SCOPE & I/O |
| --- | --- | --- |
| `eval(source)` | Map in default context | Per default context |
| `eval(source, bindings)` | `bindings` map for this eval | With `AbstractScriptEngine`, takes remaining scopes/I/O from default context |
| `eval(source, context)` | Map in the `context` passed by caller | Per the `context` passed |

For request isolation, `eval(source, context)` is the clearest choice because the caller decides both local/global and readers/writers. For providers that already have a suitable default scope, `eval(source, bindings)` is a concise option.

## 8. ScriptContext Also Manages Input and Output

`ScriptContext` is not just variable names. It has:

- `getReader()/setReader(Reader)`: input source for the script when supported by the provider.
- `getWriter()/setWriter(Writer)`: where the script can write stdout per provider rules.
- `getErrorWriter()/setErrorWriter(Writer)`: destination for messages/errors explicitly printed by the script.
- `ScriptEngine.FILENAME`: a metadata key that can be useful for the engine to report the source name in diagnostics, depending on the provider.

Example when the host wants to capture output in memory:

~~~java
java.io.StringWriter output = new java.io.StringWriter();
ScriptContext context = new SimpleScriptContext();
context.setWriter(output);
// If the specific engine uses ScriptContext.getWriter():
// engine.eval(scriptText, context);
String collected = output.toString();
~~~

This snippet is **illustrative** with `engine`/`scriptText` undeclared, not a standalone program. Script syntax such as `print(...)`/`console.log(...)` is not standardized by JSR-223; a provider may write to the system console instead of `context.getWriter()` depending on its language API. Do not conclude that `StringWriter` automatically intercepts all stdout, stderr, network access, or logging of Java objects called by the script.

If you want **per-request** Reader/Writer, create a new context and attach dedicated writers. When sharing a writer across multiple engine threads, you must have a synchronization policy or a way to separate results to avoid interleaved output.

## 9. Passing Java Objects into Scripts: Scope Is Not Access Control

### 9.1. What Values Can Be Put into Bindings?

`Bindings` accepts `Object`, so the host can pass things like the following into a script:

~~~java
Bindings bindings = new SimpleBindings();
bindings.put("username", "An");
bindings.put("retryLimit", 3);
bindings.put("tags", java.util.List.of("java", "runtime"));
bindings.put("options", java.util.Map.of("mode", "safe"));
~~~

This is a valid snippet inside a method with corresponding imports. The Java-side map supports these objects, **but how method calls, iteration, and property access work from the script depends on the provider**. For example, `tags.get(0)` is Java syntax; not every scripting language has that exact syntax.

**Use small, immutable, least-privilege data types.** Do not automatically pass an entire `ApplicationContext` container, database connection, class loader, `Runtime`, or a highly privileged service object into a script just because `Bindings` allows it.

### 9.2. Objects Shared by Reference

If the host attaches an `ArrayList` to two contexts, two scripts can see the same list object through bindings even though the two maps are different. When the script engine allows calling Java methods on that object, it can mutate state, leaking data between sessions.

If isolation is needed:

- Create per-request copies of data, especially mutable collections.
- Convert complex objects into DTOs/interfaces exposing only the necessary operations.
- Do not reuse a mutable `Bindings` across multiple requests that do not share the same trust boundary.
- Put in global only values allowed to be shared with all scripts.
- Consider process isolation for untrusted scripts; JSR-223 scopes **are not a security boundary**.

### 9.3. Output and Conversion

`engine.eval(script, context)` returns `Object`; the provider may return a `String`, boxed number, boolean, a wrapper object, or `null`. You should not cast `(String) engine.eval(...)` without knowing the engine contract. Instead, check `instanceof`, validate schema/values, and convert data at the boundary.

Script parser/runtime errors are normally reported by the engine via `ScriptException`. `ScriptException` may include the error location (file/line/column) depending on the provider and how metadata is attached. However, if a Java object called by the script throws a runtime error, how the engine wraps/propagates the exception may differ; inspect the actual cause rather than assuming all errors always have a single type.

## 10. Scopes Do Not Solve Concurrency and Security

### 10.1. Data Races and Engine State

One question has two independent parts:

1. **Which map is used?** ENGINE_SCOPE/GLOBAL_SCOPE in the context, shared or separate.
2. **Who can use the map/engine concurrently?** Multiple threads may modify global at the same time, or the engine may have internal mutable state.

Do not assume `SimpleBindings` is thread-safe. If a provider has `ScriptEngineFactory.getParameter("THREADING")`, read its meaning according to that provider; that value does not make every object inside bindings thread-safe. An engine that allows multithreading does not necessarily allow sharing a request context that is being mutated asynchronously.

A manageable architecture:

~~~text
Shared script source / compiled artifact (if the provider supports it safely)
                   |
           +-------+-------+
           |               |
        Request A        Request B
           |               |
   ENGINE_SCOPE A   ENGINE_SCOPE B
   private objects  private objects
           \               /
            \             /
       GLOBAL_SCOPE: immutable, approved config
~~~

If the same engine instance needs to run concurrently, you must verify the **provider's threading contract**. Many applications choose to pool engine instances/contexts per request to reduce unintended sharing.

### 10.2. Script Injection Differs from Variable Binding

Putting data into `Bindings` is a way to **avoid directly concatenating user data strings into script source**. Do not construct scripts like:

~~~java
String source = "checkUser('" + untrustedUsername + "')";
~~~

This is an **anti-pattern**, assuming `untrustedUsername` is already present. Input containing quotes/script characters can alter the parsed source. Instead, pass the value via bindings and keep the source code fixed:

~~~java
bindings.put("username", untrustedUsername);
Object result = engine.eval("checkUser(username)", bindings);
~~~

This is an illustrative snippet with an engine supporting JavaScript-like syntax, where `bindings` and `untrustedUsername` are already declared. Binding avoids the source-string injection form mentioned above, **it does not automatically make a script safe when the script is allowed to call full-privilege host objects**.

### 10.3. Threat Model

JSR-223 is an integration API, not a sandbox. A provider may allow scripts to call host Java methods, load classes, access files/network, or use reflection depending on configuration. When scripts are **untrusted**:

- Do not put highly privileged objects into bindings, even in GLOBAL_SCOPE.
- Verify the provider's host interop/class access restrictions; sandboxing capabilities vary by engine.
- Enforce time, memory, CPU, and I/O limits at appropriate boundaries; timing out with `Future.cancel` does not guarantee stopping all native/engine computation.
- Have audit logs, validate input/output, and if risk is high, execute scripts in a **privilege-restricted process/container**.
- Do not treat `ScriptContext` as an automatic tenant isolation mechanism.

## 11. Common Errors and How to Diagnose Them

| Symptom | Common Cause | How to Check |
| --- | --- | --- |
| `getEngineByName("JavaScript") == null` | No JSR-223 JavaScript provider discovered | `manager.getEngineFactories()`; check classpath/module path and `ScriptEngineFactory` registration |
| `engine.get("region") == null` but script can read `region` | `region` is in GLOBAL_SCOPE, while `engine.get` reads ENGINE_SCOPE | Use `engine.getContext().getAttribute("region")` |
| Global variable “disappears” when calling script | ENGINE_SCOPE has the same key, even with a null value | `getAttributesScope(name)` and `getBindings(ENGINE_SCOPE).containsKey(name)` |
| `removeAttribute` does not make the variable disappear completely | A value in a lower scope becomes visible again | Check GLOBAL_SCOPE; remove at the right scope if permitted |
| Request B reads request A's user | Reusing a Bindings map or mutable object; default engine context is shared | Allocate separate ENGINE_SCOPE map/engine context, restrict global and object references |
| `eval(script, bindings)` does not change the value seen via `engine.get` | Bindings is only used as ENGINE_SCOPE for that eval | Use `engine.setBindings` when you truly want to replace default, or keep requests separate |
| `ScriptException` due to variable syntax | Script language does not understand the snippet's syntax | Verify engine name/provider and the language's own syntax |
| `ClassCastException` when reading result | Provider returns a different wrapper/number object type | Check runtime type and schema |
| `NullPointerException` when using engine | `getEngineByName` returned null and code called `eval` immediately | Check for null, report missing provider clearly |
| `StringWriter` does not capture all output | Provider uses another console API or host code writes directly to System.out | Check provider docs, do not treat Writer as OS-level redirection |
| Sharing GLOBAL_SCOPE causes race | Mutable SimpleBindings used concurrently | Switch to immutable data, scope per request, use deliberate synchronization |
| Script runs but has overly broad privileges | Dangerous service/reference was put into Bindings | Restrict capabilities/host access, isolate process when needed |
| `Bindings.put` fails on strange keys | Key is null/empty or not a String | Validate variable names, use an explicit allowlist of keys |

### Short Debugging Workflow

1. Confirm the **provider** exists: `getEngineFactories()` list, engine name, classpath/module path.
2. Identify the actual **eval overload**: `eval(script)`, `eval(script, bindings)`, or `eval(script, context)`.
3. Check the maps attached at `ENGINE_SCOPE` and `GLOBAL_SCOPE` (reference identity, key presence).
4. Use `getAttributesScope(name)` to distinguish shadowing and null from a non-existent key.
5. Check whether Java objects in bindings are mutable/shared; validate variable names and access permissions.
6. Check syntax/script exceptions per provider; do not assume every engine uses JavaScript.
7. When scripts run concurrently or are untrusted, check threading, host interop, I/O, timeouts, and isolation independently of scopes.

## 12. Self-Check Exercises

**Exercise 1 — Scope lookup.** Set `GLOBAL_SCOPE.theme="dark"`, `ENGINE_SCOPE.theme="light"`. What does `getAttribute("theme")` return? What does `getAttribute("theme",GLOBAL_SCOPE)` return?

**Exercise 2 — Null shadow.** Replace `ENGINE_SCOPE.theme` with null. Does `getAttribute("theme")` return null or dark? What does `getAttributesScope("theme")` return? What must be done so dark appears again?

**Exercise 3 — Missing variable.** Why does `getAttribute("unknown")==null` not prove the key does not exist? How do you combine `getAttributesScope` or `containsKey` to distinguish?

**Exercise 4 — Context isolation.** Create two `SimpleScriptContext` instances and two local `SimpleBindings`. If both point to the same mutable `ArrayList`, is isolation still complete? Propose a fix.

**Exercise 5 — eval overload.** Suppose default engine scope has `user="A"`, global has `region="VN"`, and request bindings has `user="B"`. Compare the two calls `eval("user + region")` and `eval("user + region", request)` in an engine with corresponding syntax.

**Exercise 6 — Manager global.** Create two separate `ScriptEngineManager` instances, each with its own global bindings. Why can you not infer that manager A's global automatically propagates to manager B?

**Exercise 7 — Provider detection.** Run `OptionalJavaScriptEngineDemo` on JDK17 without a provider installed. Why does the program compile but not run the JavaScript expression? When a provider is installed, how do you check valid engine names?

**Exercise 8 — Output capture.** Call `ScriptContext.setWriter(new StringWriter())`. Why does that operation alone not guarantee that every `System.out.println` called by a Java object from the script is captured?

**Exercise 9 — Security.** An application puts both `DataSource` and `Runtime` into a shared GLOBAL_SCOPE for customer scripts. Identify the risks, how to reduce privileges, and the process boundary needed for untrusted scripts.

**Exercise 10 — Request lifecycle.** Design an `execute(script, requestData)` API using a new `ScriptContext` per request, ENGINE_SCOPE containing input, and GLOBAL_SCOPE containing only immutable configuration; explain how to handle output and exceptions.

## 13. Summary

- **`Bindings`** is a Java name–value map; **`ScriptContext`** attaches those maps to scopes and manages Reader/Writer; **`ScriptEngine`** is the script executor; **`ScriptEngineManager`** handles discovery and default global configuration.
- **`ENGINE_SCOPE=100` takes priority over `GLOBAL_SCOPE=200`.** A key in ENGINE_SCOPE with a null value still shadows global; you must `removeAttribute` to fall back.
- **`getAttributesScope(name)`** tells you where the key is actually declared, returning `-1` if it does not exist; `getAttribute(name)` can return null in both cases.
- **`engine.put/get`** operates on the default ENGINE_SCOPE, whereas **`eval(script, bindings)`** uses Bindings for that single evaluation and **`eval(script, context)`** accepts the full context.
- **GLOBAL_SCOPE is not global to the entire JVM**: the degree of sharing depends on the `Bindings` object you attach and the manager that creates the engine.
- Java 17 has the `java.scripting` API but **does not guarantee a JavaScript engine is available**; you must check `getEngineByName`/`getEngineFactories` and install a JSR-223 provider if needed.
- Bindings pass **references**, not deep copies or a sandbox; you must design per-request isolation, threading, and host-access security separately.

## Official References

- [Java SE 17 — `javax.script.Bindings`](https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/Bindings.html)
- [Java SE 17 — `SimpleBindings`](https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/SimpleBindings.html)
- [Java SE 17 — `ScriptContext`](https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/ScriptContext.html)
- [Java SE 17 — `SimpleScriptContext`](https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/SimpleScriptContext.html)
- [Java SE 17 — `ScriptEngine`](https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/ScriptEngine.html)
- [Java SE 17 — `AbstractScriptEngine`](https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/AbstractScriptEngine.html)
- [Java SE 17 — `ScriptEngineManager`](https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/ScriptEngineManager.html)
- [OpenJDK JEP 372 — Remove the Nashorn JavaScript Engine](https://openjdk.org/jeps/372)

# Passing Data via Bindings and Choosing ENGINE_SCOPE or GLOBAL_SCOPE

## 1. The Problem of Passing Data into Embedded Scripts

In a Java application integrating a scripting language via the **JSR-223 Scripting API** (`javax.script`), host code often needs to provide information to scripts: configuration, user IDs, input data, computation parameters, or an allowed Java service. Interpolating data directly into script text is both hard to maintain and risks syntax errors or injection vulnerabilities if data is untrusted. `Bindings` is the way to pass **name → value** pairs to the engine through an explicit API.

Three objects to distinguish:

- **`Bindings`:** an interface extending `Map<String, Object>` containing name–object pairs; `SimpleBindings` is a simple default implementation.
- **`ScriptContext`:** holds Bindings attached to specific **scopes** along with `Reader`, `Writer`, and `errorWriter` streams for an execution.
- **`ScriptEngine`:** processes code of a scripting language; accesses the context to see values and write results.

An example of passing data into an installed engine:

```java
// Illustrative snippet; assumes engine exists and scriptSource is valid.
Bindings invocation = engine.createBindings();
invocation.put("userId", "u123");
invocation.put("attempt", 3);

Object result = engine.eval(scriptSource, invocation);
```

In this case, `invocation` is the **ENGINE_SCOPE for this eval call**. Java key names may appear as script variables, though how Java variables are accessed or objects are converted depends on the language/`ScriptEngine`.

**JDK 17 note:** Java provides the `javax.script` package, but **does not guarantee a built-in JavaScript engine**. Nashorn was removed from the JDK in Java 15. If `new ScriptEngineManager().getEngineByName("javascript")` returns `null`, the provider is missing—that is not a Bindings error. The runnable example in section 4 uses `SimpleScriptContext` and `SimpleBindings`, requiring no extra engine installation.

## 2. How Do ENGINE_SCOPE and GLOBAL_SCOPE Differ?

`ScriptContext` defines two standard constants:

| Scope | Constant (Value) | Meaning | Suitable Data |
|---|---|---|---|
| **ENGINE_SCOPE** | `ScriptContext.ENGINE_SCOPE` (`100`) | Variable set at the active engine/context level | Per-run inputs, temporary variables, request data |
| **GLOBAL_SCOPE** | `ScriptContext.GLOBAL_SCOPE` (`200`) | Shared variable set when contexts/engines attach the **same Bindings** | Shared configuration, shareable default values |

The name “GLOBAL_SCOPE” is easy to misunderstand. It **does not** create a JVM-wide value table. A `ScriptContext` only sees the global Bindings attached to **that context itself**. `ScriptEngineManager` holds a global Bindings shared across engines created by that manager; two independent managers do not automatically share a map. Only when two contexts receive the same Bindings object via `setBindings(..., GLOBAL_SCOPE)` do they genuinely share that data.

### 2.1. Lookup Order: Engine Takes Precedence Over Global

`ScriptContext` methods behave as follows:

- `getAttribute("key")` searches scopes from lowest numeric value to highest: **ENGINE_SCOPE (100) before GLOBAL_SCOPE (200)**.
- `getAttribute("key", ScriptContext.GLOBAL_SCOPE)` reads only global, unshadowed by engine scope.
- `setAttribute("key", value, ScriptContext.ENGINE_SCOPE)` sets the name in engine scope. Same pattern for GLOBAL_SCOPE.
- `getAttributesScope("key")` returns the scope holding the highest-priority definition of the name, or `-1` if the name is undefined.
- `removeAttribute("key", ScriptContext.ENGINE_SCOPE)` removes only the engine-scope variable; if the name still exists in global scope, a default lookup will see the global entry.

Example with the name `tax` present in both scopes:

```text
ENGINE_SCOPE: tax = 5
GLOBAL_SCOPE: tax = 10

getAttribute("tax")                           -> 5
getAttribute("tax", GLOBAL_SCOPE)             -> 10
getAttributesScope("tax")                     -> 100

After removeAttribute("tax", ENGINE_SCOPE):
getAttribute("tax")                           -> 10
getAttributesScope("tax")                     -> 200
```

**Shadowing is not overwriting global.** The `tax` variable in ENGINE_SCOPE merely shadows the global value during scope-unspecified lookups. Removing the engine entry does not erase `tax` from global.

If a key is stored with value `null`, `getAttribute` still returns `null` even though the name exists. To distinguish “absent” from “present with null value”, use `getAttributesScope` or `containsKey` on the specific Bindings (when non-null); do not rely on `getAttribute(name) == null` alone.

### 2.2. Lifecycle Is Not Determined by Scope Name

- ENGINE_SCOPE in a `ScriptEngine`'s default context can persist across **multiple eval calls** if the engine/context is reused. It is not automatically cleared after each request.
- GLOBAL_SCOPE can be shared if two contexts/engines point to the same global map. Mutations to the map may become visible to all sharers.
- A Bindings whose reference is retained elsewhere can outlive a single script execution.
- There is no thread-safety guarantee simply because data sits in GLOBAL_SCOPE; `SimpleBindings` is typically backed by a `HashMap`.

Therefore, align scope partitioning with the **actual owner and lifetime of the data**, not merely the “engine/global” names.

## 3. Creating Bindings and Attaching Them to ScriptContext

### 3.1. Initializing a Bindings

```java
Bindings local = new SimpleBindings();
local.put("userId", "u123");
local.put("retryCount", 3);
local.put("enabled", Boolean.TRUE);
```

This snippet requires importing `javax.script.Bindings` and `javax.script.SimpleBindings`. Bindings keys must be non-`null`, non-empty strings; invalid keys may throw `NullPointerException` or `IllegalArgumentException`. Values are `Object`, though how they become script-language objects depends on the engine.

### 3.2. Attaching to Both Scopes

```java
ScriptContext context = new SimpleScriptContext();

Bindings engineValues = new SimpleBindings();
engineValues.put("requestId", "req-17");

Bindings globalValues = new SimpleBindings();
globalValues.put("appName", "Portal");

context.setBindings(engineValues, ScriptContext.ENGINE_SCOPE);
context.setBindings(globalValues, ScriptContext.GLOBAL_SCOPE);

System.out.println(context.getAttribute("requestId")); // req-17
System.out.println(context.getAttribute("appName"));   // Portal
```

This is an illustrative snippet that can be placed inside a Java method with `import javax.script.*`. `SimpleScriptContext` already has an ENGINE_SCOPE bindings by default, whereas GLOBAL_SCOPE may default to `null` until set. `setBindings` **attaches a reference to the map**, without copying it.

Do not set `null` as `ENGINE_SCOPE` on `SimpleScriptContext`; this scope must have a valid Bindings. If global scope is not needed yet, GLOBAL_SCOPE can be left unset. To have multiple contexts share values, intentionally share one Bindings object and define its update policy.

### 3.3. setAttribute and getBindings APIs Do Not Conflict

The following two operations both mutate ENGINE_SCOPE of the same context:

```java
context.setAttribute("requestId", "req-17", ScriptContext.ENGINE_SCOPE);
context.getBindings(ScriptContext.ENGINE_SCOPE)
       .put("requestId", "req-17");
```

They differ in syntax, not by maintaining two separate variable tables. When using a `ScriptEngine` based on `AbstractScriptEngine`, the corresponding calls:

```java
engine.put("requestId", "req-17");
engine.getBindings(ScriptContext.ENGINE_SCOPE)
      .put("requestId", "req-17");
engine.getContext()
      .setAttribute("requestId", "req-17", ScriptContext.ENGINE_SCOPE);
```

all target ENGINE_SCOPE in the default context. `AbstractScriptEngine.get(key)` reads ENGINE_SCOPE; if you want to check both engine and global, use `engine.getContext().getAttribute(key)`. Do not treat `engine.get(key)` as an automatic lookup across all scopes without checking the specific engine's contract.

## 4. Complete Java 17 Example Requiring No External Script Engine

This example uses only standard `javax.script` APIs. We create two `SimpleScriptContext` instances with separate ENGINE_SCOPEs and share **the same** Bindings in GLOBAL_SCOPE. Running the program demonstrates the exact precedence order and value sharing.

**File `ScopeDemo.java`:**

```java
import javax.script.Bindings;
import javax.script.ScriptContext;
import javax.script.SimpleBindings;
import javax.script.SimpleScriptContext;

public final class ScopeDemo {
    public static void main(String[] args) {
        Bindings shared = new SimpleBindings();
        shared.put("appName", "Portal");
        shared.put("tax", 10);

        ScriptContext first = new SimpleScriptContext();
        first.setBindings(shared, ScriptContext.GLOBAL_SCOPE);
        first.setAttribute("user", "Lan", ScriptContext.ENGINE_SCOPE);
        first.setAttribute("tax", 5, ScriptContext.ENGINE_SCOPE);

        ScriptContext second = new SimpleScriptContext();
        second.setBindings(shared, ScriptContext.GLOBAL_SCOPE);
        second.setAttribute("user", "Minh", ScriptContext.ENGINE_SCOPE);

        System.out.println("first.user=" + first.getAttribute("user"));
        System.out.println("second.user=" + second.getAttribute("user"));
        System.out.println("first.tax=" + first.getAttribute("tax"));
        System.out.println("second.tax=" + second.getAttribute("tax"));
        System.out.println("first.global.tax=" + first.getAttribute(
                "tax", ScriptContext.GLOBAL_SCOPE));
        System.out.println("tax.scope=" + first.getAttributesScope("tax"));

        first.removeAttribute("tax", ScriptContext.ENGINE_SCOPE);
        System.out.println("first.tax.after=" + first.getAttribute("tax"));
        System.out.println("tax.scope.after=" + first.getAttributesScope("tax"));

        first.setAttribute("appName", "Local", ScriptContext.ENGINE_SCOPE);
        System.out.println("first.appName=" + first.getAttribute("appName"));
        System.out.println("second.appName=" + second.getAttribute("appName"));

        System.out.println("same.global="
                + (first.getBindings(ScriptContext.GLOBAL_SCOPE)
                        == second.getBindings(ScriptContext.GLOBAL_SCOPE)));
        System.out.println("missing.scope="
                + first.getAttributesScope("missing"));
    }
}
```

**Commands to run on JDK 17+** from the directory containing the file:

```powershell
javac ScopeDemo.java
java ScopeDemo
```

**Exact stdout:**

```text
first.user=Lan
second.user=Minh
first.tax=5
second.tax=10
first.global.tax=10
tax.scope=100
first.tax.after=10
tax.scope.after=200
first.appName=Local
second.appName=Portal
same.global=true
missing.scope=-1
```

Step-by-step explanation:

1. The two contexts have separate ENGINE_SCOPEs, so `user` is `Lan` in `first` and `Minh` in `second`.
2. `shared.tax=10` exists in GLOBAL_SCOPE of both. `first` has `tax=5` in ENGINE_SCOPE so that entry takes precedence; `second` sees only `tax=10`.
3. Explicitly requesting global scope still returns `10` even when `first` has an engine entry.
4. `getAttributesScope("tax")` returns `100` before removing the engine entry and `200` after removing it.
5. `first` sets `appName=Local` in ENGINE_SCOPE, while `second` still reads `Portal` from global. That is shadowing, not mutating the shared map.
6. The `==` comparison shows that both contexts share **the exact same global bindings object**, not a copy.
7. `getAttributesScope("missing")` returns `-1` because no scope defines that name.

This is a complete program **demonstrating scope mechanics**, though it does not execute scripts yet. Its advantage is self-verification on Java 17 without depending on engine configuration.

## 5. Connecting to a Real ScriptEngine: Four Options

The snippets in this section are **integration patterns**, not standalone programs. They assume a suitable `ScriptEngine` is already present and a `scriptSource` string is written in the chosen language's syntax. An engine absent from the environment cannot run eval merely by importing `javax.script`.

### 5.1. Passing via engine.put: Default Engine State

```java
ScriptEngineManager manager = new ScriptEngineManager();
ScriptEngine engine = manager.getEngineByName("myLanguage");
if (engine == null) {
    throw new IllegalStateException("No script engine installed");
}

engine.put("userId", "u123");
engine.put("retryCount", 3);
Object result = engine.eval(scriptSource);
```

Import `ScriptEngine`, `ScriptEngineManager`, and handle `ScriptException`. `put` usually writes to default ENGINE_SCOPE, which fits when each engine has an explicitly managed run session. **If the same engine is reused across multiple requests, ENGINE_SCOPE keys can persist across eval calls**. Do not treat ENGINE_SCOPE as “per-request” if the engine itself is shared.

### 5.2. Passing a Dedicated Bindings per eval Call

```java
Bindings invocation = engine.createBindings();
invocation.put("userId", "u123");
invocation.put("retryCount", 3);

Object result = engine.eval(scriptSource, invocation);
```

`eval(String, Bindings)` uses `invocation` as the **ENGINE_SCOPE for that execution**. With `AbstractScriptEngine`, other scopes such as GLOBAL_SCOPE as well as Reader/Writer come from the default context. This approach generally reduces key leakage between runs, yet **does not promise that all internal engine state is isolated**: some implementations hold state outside Bindings.

### 5.3. Passing a Dedicated ScriptContext to Control Both Scopes

```java
ScriptContext execution = new SimpleScriptContext();

Bindings request = engine.createBindings();
request.put("userId", "u123");
execution.setBindings(request, ScriptContext.ENGINE_SCOPE);

Bindings defaults = new SimpleBindings();
defaults.put("appName", "Portal");
execution.setBindings(defaults, ScriptContext.GLOBAL_SCOPE);

java.io.StringWriter writer = new java.io.StringWriter();
execution.setWriter(writer);

Object result = engine.eval(scriptSource, execution);
String textOutput = writer.toString();
```

`eval(String, ScriptContext)` uses **the entire** host-supplied context, allowing separate scopes, input, output, and error writers for a single execution. This fits multi-user/multi-tenant workloads or when capturing output. Some engines have specific rules for writing results/variables; consult the provider documentation.

### 5.4. Using ScriptEngineManager to Share GLOBAL_SCOPE

```java
ScriptEngineManager manager = new ScriptEngineManager();
manager.put("appName", "Portal");
manager.put("build", 17);

ScriptEngine first = manager.getEngineByName("myLanguage");
ScriptEngine second = manager.getEngineByName("myLanguage");
if (first == null || second == null) {
    throw new IllegalStateException("Script engine not installed");
}
first.put("requestId", "req-1");
second.put("requestId", "req-2");
```

`manager.put` adds names to **the manager's global bindings**; engines created by that manager use that global set per the JSR-223 contract. `first.put` and `second.put` write to the separate ENGINE_SCOPE of **each instance**. Hence `requestId` is not shared between the two engines.

If `engine.setBindings(anotherBindings, GLOBAL_SCOPE)` is called, the engine can switch to a different global map and stop sharing the manager's map. Likewise, creating two `ScriptEngineManager` instances does not make them share one common GLOBAL_SCOPE.

## 6. Choosing ENGINE_SCOPE or GLOBAL_SCOPE Based on Data

| Scenario | Choice | Reason |
|---|---|---|
| User ID, request ID, per-task data | **ENGINE_SCOPE** in a new Bindings/context | Reduces risk of previous request data leaking to the next request |
| Computation parameters, per-session feature flags | **ENGINE_SCOPE** | Only meaningful within that specific evaluation scope |
| Shared defaults such as `appName` or `defaultLocale` | **GLOBAL_SCOPE** when sharing is truly needed | Avoids duplicating publicly shareable configuration |
| Defaults overridable per request | Global default + engine override | Lookup rules allow shadowing without mutating the base value |
| Objects exposing Java operations to scripts | Usually ENGINE_SCOPE/dedicated context with restricted API | Avoids sharing state and overly broad privileges |
| Tokens, passwords, admin objects, tenant data | Should not be placed in shared GLOBAL_SCOPE | Reduces data exposure surface and cross-access risk |

**Rule:** use the smallest scope sufficient for the requirement. Writing into GLOBAL_SCOPE is only sensible when **every party sharing the map** is permitted to read and (if the engine allows) modify that value.

A global Bindings is a **mutable** map. Never assume “config” is immutable merely because it sits in GLOBAL_SCOPE. If shared read-only config is needed, the host can build an immutable snapshot, expose only restricted immutable objects/DTOs, or use engine APIs that block updates per application policy.

## 7. Common Points of Confusion

### 7.1. GLOBAL_SCOPE Is Not Guaranteed Visible Everywhere

GLOBAL_SCOPE belongs to a `ScriptContext` or Bindings shared by the host; there is no JVM-wide registry. If the host creates a new `SimpleScriptContext` without calling `setBindings(..., GLOBAL_SCOPE)`, it will not automatically see the globals of other contexts.

### 7.2. Replacing Bindings Differs from Removing One Key

- `context.removeAttribute("x", ENGINE_SCOPE)` removes **one** name from engine scope; the global entry remains untouched.
- `context.setBindings(newBindings, ENGINE_SCOPE)` replaces the **entire** engine map, potentially dropping many other keys.
- `context.setAttribute("x", value, GLOBAL_SCOPE)` updates global on the **current context**, not automatically across independent managers.
- If both scopes contain `x`, a scope-unspecified lookup gets the engine entry; removing the engine entry can “expose” the global entry, changing the visible value.

### 7.3. Java Objects Passed into Scripts Are Not Inherently Safe

`Bindings` is not a sandbox. If the host passes an object with file, network, database, or token-store access directly to an untrusted script, putting it in ENGINE_SCOPE instead of GLOBAL_SCOPE **does not stop the script** from calling whatever methods the engine permits. Restrict the API surface, protect data, define permissions, and consider running untrusted scripts within an appropriate isolation boundary.

### 7.4. Multithreading and Shared State

`SimpleBindings` uses an ordinary map and makes no thread-safety guarantees under concurrent writes. `ScriptEngine` also has its own thread-safety policy (some engines publish concurrency metadata, others do not). Creating **per-request Bindings** is a good step, but if both contexts hold the same mutable object, scripts still share state through that object.

### 7.5. Variable Names and Engine Rules

`Bindings` uses Java string keys, yet a scripting language may have reserved keywords or different identifier rules. Names like `ScriptEngine.ENGINE`, `ScriptEngine.FILENAME`, `ScriptEngine.NAME`, etc., may carry special meaning for certain providers. Use clear variable names that do not collide with internal keys unless specified by the engine documentation.

### 7.6. A null Value Does Not Always Mean Absent

A name can exist in the map with value `null`. When you need to test existence, use `getAttributesScope(name)` or `getBindings(scope).containsKey(name)` when Bindings is present. With `getAttribute(name)` alone, `null` is insufficient to tell.

## 8. Diagnosing Common Errors

| Issue | Common Cause | Check / Fix |
|---|---|---|
| `getEngineByName("javascript")` returns `null` | Engine not installed; JDK 17 does not include Nashorn | Install a compatible JSR-223 provider, check `getEngineFactories()` |
| Script receives an unexpected value | ENGINE_SCOPE variable is shadowing GLOBAL_SCOPE | Print `getAttributesScope` and both `getAttribute(name, scope)` calls |
| Next request sees previous request's values | Engine/default context was reused | Use per-invocation Bindings/context or manage cleanup explicitly |
| Two engines do not see shared global variables | Not sharing the same global map or engine scope was replaced | Check `manager.getBindings()` and `engine.getBindings(GLOBAL_SCOPE)` |
| `IllegalArgumentException`/`NullPointerException` when setting names | Invalid key or invalid scope | Avoid null/empty names; use standard scope constants |
| `ScriptException` during eval | Script syntax/logic or provider error | Inspect message, script source, and `cause` |
| `ClassCastException` when reading result | Returned object type/format differs from host assumption | Check `result` and convert according to engine |
| Inconsistent results under concurrent runs | Bindings or engine has unsafe shared state | Separate contexts/engines, synchronize, or use an executor per contract |
| Global values unexpectedly modified | Mutable map shared across multiple scripts | Restrict write access and share safe snapshots |
| Setting ENGINE_SCOPE bindings to null | Context rejects a null ENGINE_SCOPE | Create a valid Bindings before attaching |

**Do not fix every bug by moving variables to GLOBAL_SCOPE.** Broadening scope only hides state-design flaws and can expose data too widely.

## 9. Self-Check

1. **How does Bindings differ from ScriptContext?** Bindings is a name–value map; ScriptContext attaches maps to scopes and manages I/O.
2. **If `tax` exists in both engine and global, what does `getAttribute("tax")` return?** It returns the ENGINE_SCOPE entry.
3. **Is `getAttribute("tax", GLOBAL_SCOPE)` shadowed by the engine entry?** No; the scope was specified explicitly.
4. **Is GLOBAL_SCOPE a JVM-wide map?** No; it is shared only when contexts/engines intentionally attach the same Bindings.
5. **Which scope does `engine.eval(script, bindings)` put `bindings` in?** ENGINE_SCOPE for that execution.
6. **Why should each request have its own Bindings?** To prevent temporary variables from a prior request from persisting and to reduce state sharing.
7. **Does ENGINE_SCOPE make scripts safer regarding I/O permissions?** No; it is a name-lookup scope, not a security mechanism.
8. **What does `getAttributesScope("unknown")` return when the name is absent?** `-1`.

**Exercise A:** add `shared.put("role", "viewer")` in `ScopeDemo`. Set `first.setAttribute("role", "editor", ENGINE_SCOPE)` and predict the value of `role` in both contexts before and after removing the engine entry.

**Exercise B:** create a third `SimpleScriptContext` without calling `setBindings(shared, GLOBAL_SCOPE)`, then try reading `appName`. Why does it not see `Portal`?

**Exercise C:** once a concrete JSR-223 engine is installed, run `eval(script, bindingsA)` and `eval(script, bindingsB)` sequentially, and test whether the engine retains any state outside Bindings before deploying concurrent execution.

## References

- Java SE 17, `ScriptContext`: https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/ScriptContext.html
- Java SE 17, `SimpleScriptContext`: https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/SimpleScriptContext.html
- Java SE 17, `Bindings`: https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/Bindings.html
- Java SE 17, `SimpleBindings`: https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/SimpleBindings.html
- Java SE 17, `ScriptEngine`: https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/ScriptEngine.html
- Java SE 17, `AbstractScriptEngine`: https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/AbstractScriptEngine.html
- Java SE 17, `ScriptEngineManager`: https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/ScriptEngineManager.html

# Hands-On: Adding Scripted Rules with Isolated `Bindings` and Handling Missing Engines

## 1. Context and Expected Outcomes

Suppose a Java application allows adding **request approval rules** at runtime. Each evaluation has per-user data such as `amount`, `limit`, and `verified`. Operators want to use a script to decide `ALLOW` or `DENY`, swapping rules without changing the service's caller code; at the same time, the system must fail safely when **no script engine is installed**.

The Java Scripting API (JSR 223, `javax.script`, standard module `java.scripting`) provides the necessary building blocks:

- `ScriptEngineManager`: locates or registers a `ScriptEngineFactory`, then creates a `ScriptEngine` by name.
- `ScriptEngine`: executes a script string via `eval(...)`.
- `Bindings`: variable-to-value map supplied to a script; each request can receive **its own separate instance**.
- `ScriptContext`: configures `ENGINE_SCOPE`, `GLOBAL_SCOPE`, and I/O channels.
- `ScriptException`: reports script errors that the caller must classify and handle.

**Key requirement of this exercise:** if no engine is found, the script fails, or the result does not conform to the Boolean contract, **never silently approve the request**. For example, represent outcomes with an enum containing `ALLOW`, `DENY`, `MISSING_ENGINE`, `SCRIPT_ERROR`, and `INVALID_RESULT`; every state other than `ALLOW` **denies authorization** in the business decision.

After this exercise, you will be able to:

1. Register a test engine and verify engine lookup by name.
2. Provide separate `Bindings` for Alice and Bob without one evaluation's state overwriting the other.
3. Add a rule checking the `verified` flag and observe the result change from `ALLOW` to `DENY`.
4. Handle missing engines and invalid scripts using a **fail-closed** policy.
5. Distinguish lookup errors, script compilation/execution errors, wrong result types, and security or concurrency issues.
6. Compile and run a **Java 17** program using only the JDK, with verifiable stdout.

## 2. Important Note About Java 17: Having the API Does Not Mean Having an Engine

`javax.script` is a **standard API**. It does not guarantee that the JVM comes with a built-in engine for JavaScript, Python, or any other language.

In older JDKs, Nashorn was bundled as the JavaScript engine; Nashorn was removed from the JDK in **Java 15**. Therefore, on Java 17, the call:

```java
ScriptEngine engine =
        new ScriptEngineManager().getEngineByName("JavaScript");
```

**can return `null`**, and on a standard Java 17 environment without extra providers installed, you typically have no default JavaScript engine. Never write code assuming `getEngineByName("JavaScript")` will always succeed.

There are two ways to run this hands-on exercise:

- **Approach A (standalone, used in this lesson):** manually register a tiny `ScriptEngineFactory` named `toy-rule` supporting a small set of rule expressions. All examples then run on JDK 17 without downloading dependencies or relying on whatever engine happens to be installed locally.
- **Approach B (real-world deployment):** add the JSR 223 provider for your chosen language to the runtime, verify service registration/class loader visibility, and look up the engine by the name advertised by that provider. You must use **the real engine's syntax**, not assume `toy-rule` strings are JavaScript.

The `toy-rule` engine below is a **minimal interpreter built strictly for learning**. It accepts a few predefined rule strings; it is not a full JavaScript interpreter, does not execute arbitrary expressions, and does not represent a sandbox.

## 3. Problem Design and Data Boundaries

We model each request as follows:

| Property | Java type | Meaning |
|---|---|---|
| `user` | `String` | Name to identify sample data, never used to auto-grant access |
| `amount` | `int` | Requested value |
| `limit` | `int` | Allowed threshold |
| `verified` | `boolean` | Verification status |

Initial rule:

```text
amount <= limit
```

Extended rule requiring verification:

```text
amount <= limit && verified
```

Sample data:

| Request | `amount` | `limit` | `verified` | Rule 1 | Rule 2 |
|---|---:|---:|---|---|---|
| Alice | 80 | 100 | `false` | `ALLOW` | `DENY` |
| Bob | 150 | 100 | `true` | `DENY` | `DENY` |
| Alice after verification | 80 | 100 | `true` | `ALLOW` | `ALLOW` |

The two rules are selected by a **configuration string** passed to `eval`, rather than two separate public Java methods on the host. In a real product, rule IDs, versions, source text, and edit permissions should be stored under strict control; end-user input must never become a script executed with server privileges.

Caller state flow:

```text
                  Read configured engine name / rule
                              |
                              v
                  ScriptEngineManager lookup
                         /          \
                     null          engine found
                      |               |
                      v               v
              MISSING_ENGINE    Create isolated Bindings
                                      |
                                      v
                                 eval(rule)
                               /    |      \
                           error  wrong    Boolean
                             |    result     |
                             v      v        v
                        SCRIPT_ERROR INVALID_RESULT
                                              |
                                       true or false
                                       /           \
                                      v             v
                                    ALLOW          DENY
```

**There is no path from `MISSING_ENGINE`, `SCRIPT_ERROR`, or `INVALID_RESULT` to `ALLOW`**. This is an explicit policy, not an automatic behavior of every script engine.

## 4. What Are Isolated `Bindings` and Why Do We Need Them?

`Bindings` is essentially a `Map<String,Object>` constrained to variable-name keys. If every request calls `engine.put("user", ...)` on a shared engine, variables in the **default `ENGINE_SCOPE`** can be overwritten by one request while another runs.

Example **unsuitable** for multi-user boundaries:

```java
// Illustrative counterexample; assumes "engine" exists.
engine.put("amount", 80);
engine.put("user", "Alice");
engine.eval(rule);

engine.put("amount", 150);
engine.put("user", "Bob");
engine.eval(rule);
```

Here `put(...)` mutates the default `ENGINE_SCOPE`. It does not create a separate session for each execution. If the host retains other state or runs multiple threads concurrently, behavior becomes even more unpredictable.

Separating data per evaluation:

```java
Bindings alice = engine.createBindings();
alice.put("amount", 80);
alice.put("limit", 100);
alice.put("verified", false);

Object result = engine.eval("amount <= limit", alice);
```

With `eval(script, bindings)`, the passed bindings act as **`ENGINE_SCOPE` for that evaluation**; this does not permanently replace the engine's default bindings. However, this overload may still draw other parts from the engine's default context, including **`GLOBAL_SCOPE`**. Hence it does not automatically isolate all state.

In this exercise, we use a more explicit setup:

```java
SimpleScriptContext context = new SimpleScriptContext();
context.setBindings(alice, ScriptContext.ENGINE_SCOPE);
context.setBindings(new SimpleBindings(), ScriptContext.GLOBAL_SCOPE);

Object result = engine.eval("amount <= limit", context);
```

Each request gets both its own `ENGINE_SCOPE` and its own empty `GLOBAL_SCOPE`. Thus we never accidentally share global bindings attached by `ScriptEngineManager` to engines it creates. Isolating `Bindings` still **does not** mean internal engine state or mutable objects placed inside the map are isolated.

## 5. Three Boundaries to Check Before Running Rules

### 5.1. Looking up the right engine by name

```java
ScriptEngine engine = manager.getEngineByName(configuredName);
if (engine == null) {
    return new Outcome(Decision.MISSING_ENGINE, null);
}
```

This is an **excerpt** from the class in section 7. `getEngineByName` returns `null` when no factory is registered or discovered under that name. Any code using the engine must appear **after** the null check; otherwise a `NullPointerException` can occur and obscure the true cause.

Never fall back automatically to an engine of **another language/syntax** when the required engine is missing. If a product has a business fallback, that fallback must be designed and approved separately, never "no engine, so allow".

### 5.2. Results must adhere to the contract

A JSR 223 script engine can return any `Object`: `null`, `String`, `Number`, `Boolean`, or a language-specific type. For authorization rules, **accept only `Boolean`**:

```java
Object raw = engine.eval(rule, context);
if (!(raw instanceof Boolean result)) {
    return new Outcome(Decision.INVALID_RESULT, bindings);
}
return new Outcome(
        result ? Decision.ALLOW : Decision.DENY, bindings);
```

Do not cast blindly to `Boolean`; do not treat `"true"` strings as permission unless the contract explicitly specifies it. Uncontrolled type coercion can cause scripts or different providers to behave unexpectedly.

### 5.3. Script errors are never approval decisions

```java
try {
    Object raw = engine.eval(rule, context);
    // Validate result per the chosen contract.
} catch (ScriptException e) {
    return new Outcome(Decision.SCRIPT_ERROR, bindings);
}
```

This is an **illustration**; the complete program below includes the type check. `ScriptException` signals a script failure and must not be swallowed to return `ALLOW`. In a real application, log **sanitized** `ruleId`, rule version, and request ID, avoiding dumping sensitive `Bindings` data or entire scripts into logs.

Serious failures like `Error`, JVM configuration errors, or provider initialization failures are not necessarily `ScriptException`; manage them at the appropriate worker/supervisor boundary rather than catching `Throwable` and treating it as a valid business decision.

## 6. Exercise Program Architecture

We use a **single source file** `ScriptRuleLab.java` to minimize compilation mistakes. Components inside:

```text
ScriptRuleLab
  |
  +-- Decision enum: ALLOW / DENY / MISSING_ENGINE / ...
  +-- Request record: user / amount / limit / verified
  +-- Outcome record: decision / Bindings
  |
  +-- RuleFactory implements ScriptEngineFactory
  |       |
  |       +-- engine name "toy-rule"
  |       +-- declares THREADING = null
  |       +-- creates RuleEngine
  |
  +-- RuleEngine extends AbstractScriptEngine
  |       |
  |       +-- eval(String, ScriptContext)
  |       +-- eval(Reader, ScriptContext)
  |       +-- createBindings()
  |
  +-- evaluate(manager, name, rule, request)
  |       |
  |       +-- lookup, null guard
  |       +-- request-local Bindings / ScriptContext
  |       +-- Boolean type check
  |       +-- fail-closed status mapping
  |
  +-- main(): test scenarios
```

**Toy engine conventions:**

- `"amount <= limit"` returns Boolean using two Integer variables in context.
- `"amount <= limit && verified"` returns Boolean and requires the `verified` flag.
- `"return text"` intentionally returns a `String` to test `INVALID_RESULT`.
- Any other string throws `ScriptException("Unsupported rule")`.
- When evaluating a Boolean rule, the engine writes `lastDecision` into **`ENGINE_SCOPE` of the passed context**. This measurement demonstrates that state is not mixed between Alice and Bob.

These strings **are not full JavaScript syntax**; we use them as a tiny DSL. To support a general-purpose language, install a real script engine or build a proper parser/evaluator rather than adding more `switch` branches.

## 7. Complete Java 17 Program

Create `ScriptRuleLab.java` with the exact code below. No third-party dependencies are needed; it uses the JDK's `javax.script`.

```java
import java.io.IOException;
import java.io.Reader;
import java.util.List;
import javax.script.AbstractScriptEngine;
import javax.script.Bindings;
import javax.script.ScriptContext;
import javax.script.ScriptEngine;
import javax.script.ScriptEngineFactory;
import javax.script.ScriptEngineManager;
import javax.script.ScriptException;
import javax.script.SimpleBindings;
import javax.script.SimpleScriptContext;

public final class ScriptRuleLab {
    enum Decision { ALLOW, DENY, MISSING_ENGINE, SCRIPT_ERROR, INVALID_RESULT }

    record Request(String user, int amount, int limit, boolean verified) {}
    record Outcome(Decision decision, Bindings bindings) {}

    static final class RuleFactory implements ScriptEngineFactory {
        @Override public String getEngineName() { return "Demo Rule Engine"; }
        @Override public String getEngineVersion() { return "1.0"; }
        @Override public List<String> getExtensions() { return List.of("rule"); }
        @Override public List<String> getMimeTypes() { return List.of("text/x-demo-rule"); }
        @Override public List<String> getNames() { return List.of("toy-rule"); }
        @Override public String getLanguageName() { return "DemoRule"; }
        @Override public String getLanguageVersion() { return "1.0"; }

        @Override
        public Object getParameter(String key) {
            return switch (key) {
                case "THREADING" -> null;
                case ScriptEngine.ENGINE -> getEngineName();
                case ScriptEngine.ENGINE_VERSION -> getEngineVersion();
                case ScriptEngine.LANGUAGE -> getLanguageName();
                case ScriptEngine.LANGUAGE_VERSION -> getLanguageVersion();
                case ScriptEngine.NAME -> "toy-rule";
                default -> null;
            };
        }

        @Override public String getMethodCallSyntax(
                String obj, String method, String... args) {
            throw new UnsupportedOperationException("No method calls");
        }
        @Override public String getOutputStatement(String text) {
            throw new UnsupportedOperationException("No output command");
        }
        @Override public String getProgram(String... statements) {
            return String.join("\n", statements);
        }
        @Override public ScriptEngine getScriptEngine() {
            return new RuleEngine(this);
        }
    }

    static final class RuleEngine extends AbstractScriptEngine {
        private final ScriptEngineFactory factory;
        RuleEngine(ScriptEngineFactory factory) { this.factory = factory; }

        @Override
        public Object eval(String script, ScriptContext context)
                throws ScriptException {
            return switch (script.trim()) {
                case "amount <= limit" -> compare(context, false);
                case "amount <= limit && verified" -> compare(context, true);
                case "return text" -> "not a boolean";
                default -> throw new ScriptException("Unsupported rule");
            };
        }

        private Boolean compare(ScriptContext context, boolean needVerified)
                throws ScriptException {
            Object amount = context.getAttribute("amount");
            Object limit = context.getAttribute("limit");
            Object verified = context.getAttribute("verified");
            if (!(amount instanceof Integer a) ||
                !(limit instanceof Integer max) ||
                !(verified instanceof Boolean approved)) {
                throw new ScriptException("Invalid binding types");
            }
            boolean allow = a <= max && (!needVerified || approved);
            context.setAttribute(
                    "lastDecision", allow, ScriptContext.ENGINE_SCOPE);
            return allow;
        }

        @Override
        public Object eval(Reader reader, ScriptContext context)
                throws ScriptException {
            StringBuilder source = new StringBuilder();
            char[] buffer = new char[1024];
            try {
                int n;
                while ((n = reader.read(buffer)) != -1) {
                    source.append(buffer, 0, n);
                }
            } catch (IOException e) {
                throw new ScriptException(e);
            }
            return eval(source.toString(), context);
        }

        @Override public Bindings createBindings() {
            return new SimpleBindings();
        }
        @Override public ScriptEngineFactory getFactory() {
            return factory;
        }
    }

    static Outcome evaluate(
            ScriptEngineManager manager,
            String engineName,
            String rule,
            Request request) {
        ScriptEngine engine = manager.getEngineByName(engineName);
        if (engine == null) {
            return new Outcome(Decision.MISSING_ENGINE, null);
        }

        Bindings bindings = engine.createBindings();
        bindings.put("user", request.user());
        bindings.put("amount", request.amount());
        bindings.put("limit", request.limit());
        bindings.put("verified", request.verified());

        SimpleScriptContext context = new SimpleScriptContext();
        context.setBindings(bindings, ScriptContext.ENGINE_SCOPE);
        context.setBindings(new SimpleBindings(), ScriptContext.GLOBAL_SCOPE);

        try {
            Object raw = engine.eval(rule, context);
            if (!(raw instanceof Boolean result)) {
                return new Outcome(Decision.INVALID_RESULT, bindings);
            }
            return new Outcome(result ? Decision.ALLOW : Decision.DENY, bindings);
        } catch (ScriptException e) {
            return new Outcome(Decision.SCRIPT_ERROR, bindings);
        }
    }

    public static void main(String[] args) {
        ScriptEngineManager manager = new ScriptEngineManager();
        RuleFactory factory = new RuleFactory();
        manager.registerEngineName("toy-rule", factory);

        Request alice = new Request("Alice", 80, 100, false);
        Request bob = new Request("Bob", 150, 100, true);
        Outcome a = evaluate(manager, "toy-rule", "amount <= limit", alice);
        Outcome b = evaluate(manager, "toy-rule", "amount <= limit", bob);

        System.out.println("Rule 1 / Alice: " + a.decision());
        System.out.println("Rule 1 / Bob: " + b.decision());
        System.out.println("Bindings distinct: " + (a.bindings() != b.bindings()));
        System.out.println("Alice lastDecision: " +
                a.bindings().get("lastDecision"));
        System.out.println("Bob lastDecision: " +
                b.bindings().get("lastDecision"));

        Outcome strict = evaluate(
                manager, "toy-rule", "amount <= limit && verified", alice);
        Outcome confirmed = evaluate(
                manager, "toy-rule", "amount <= limit && verified",
                new Request("Alice", 80, 100, true));
        System.out.println("Rule 2 / Alice unverified: " + strict.decision());
        System.out.println("Rule 2 / Alice verified: " + confirmed.decision());

        Outcome missing = evaluate(
                manager, "__missing_engine_demo_229__", "amount <= limit", alice);
        System.out.println("Missing engine: " + missing.decision());

        Outcome syntax = evaluate(
                manager, "toy-rule", "amount >>> limit", alice);
        System.out.println("Invalid syntax: " + syntax.decision());

        Outcome type = evaluate(
                manager, "toy-rule", "return text", alice);
        System.out.println("Invalid result: " + type.decision());
        System.out.println("Factory THREADING: " +
                factory.getParameter("THREADING"));
    }
}
```

### Purpose of each part

**`RuleFactory`** is a valid JSR 223 factory. It advertises the name `"toy-rule"` along with basic metadata and creates `RuleEngine` instances. We **explicitly** register the engine name via `manager.registerEngineName(...)` instead of waiting for ServiceLoader to discover a plugin on a machine with no provider installed.

**`RuleEngine`** extends `AbstractScriptEngine`. It implements `eval(String, ScriptContext)`, `eval(Reader, ScriptContext)`, `createBindings()`, and `getFactory()`. These are what the example needs to properly demonstrate engine execution through JSR 223. `getParameter("THREADING")` returns `null` because the toy engine **does not claim thread safety for concurrent script execution on the same instance**.

**`evaluate(...)`** always retrieves a fresh engine from the manager, creates fresh `Bindings`, creates a fresh `SimpleScriptContext`, and then evaluates the rule. Thus the example **never shares a single engine instance across concurrent requests**. `Outcome` holds `Bindings` **solely so the exercise can verify state and object identity**; in a production service, never return a mutable request map in a client response.

**`main()`** runs test scenarios in deterministic order to prove both success and failure branches. It does not depend on JavaScript/Nashorn being installed.

## 8. Compiling, Running, and Verifying Stdout

Install JDK 17 or newer, save `ScriptRuleLab.java` in a directory of your choice, and open a terminal in that directory.

### Linux/macOS

```bash
javac --release 17 -encoding UTF-8 ScriptRuleLab.java
java ScriptRuleLab
```

### Windows PowerShell

```powershell
javac --release 17 -encoding UTF-8 ScriptRuleLab.java
java ScriptRuleLab
```

If `javac` is not found, check `PATH`/`JAVA_HOME` and make sure you are using a JDK that includes a compiler. If the code is placed in a named module instead of running on the classpath as here, declare `requires java.scripting;` in `module-info.java`.

**Stdout on a successful run of the program:**

```text
Rule 1 / Alice: ALLOW
Rule 1 / Bob: DENY
Bindings distinct: true
Alice lastDecision: true
Bob lastDecision: false
Rule 2 / Alice unverified: DENY
Rule 2 / Alice verified: ALLOW
Missing engine: MISSING_ENGINE
Invalid syntax: SCRIPT_ERROR
Invalid result: INVALID_RESULT
Factory THREADING: null
```

Output prints no stack traces because the demo converts known script errors into explicit statuses. In an environment where an external provider happens to register the exact dummy name `__missing_engine_demo_229__`, change the "missing" test to an unregistered name; on a normal demo machine, that test name does not exist.

## 9. Walking Through the Results Step by Step

### 9.1. `Rule 1`: adding a basic rule

In `main`:

```java
Outcome a = evaluate(manager, "toy-rule", "amount <= limit", alice);
Outcome b = evaluate(manager, "toy-rule", "amount <= limit", bob);
```

Alice has `80 <= 100`, yielding `ALLOW`. Bob has `150 <= 100` false, yielding `DENY`. Both execute **the same rule source**, but with values inside two different `Bindings`.

When defining rules as application configuration, what changes across deployments is `rule` (the string), while `evaluate(manager, engineName, rule, request)` requires no signature or call-site changes. However, in the toy engine, the supported syntax is finite and hard-coded in the implementation.

### 9.2. Verifying separate `Bindings`

The lines:

```text
Bindings distinct: true
Alice lastDecision: true
Bob lastDecision: false
```

show that `a.bindings()` and `b.bindings()` are **two distinct objects**. The toy engine writes `lastDecision` into `ENGINE_SCOPE` of the corresponding context; Alice holds `true` and Bob holds `false`. It does not write `lastDecision` into the manager's default scope.

Having two separate maps is an important condition, yet **not an absolute guarantee of isolation**:

- If both maps reference the same mutable `ArrayList` or connection, that object's state can still be shared.
- If the engine maintains static fields or global state outside Bindings, creating new bindings will not reset them.
- If the context uses the shared `GLOBAL_SCOPE` from `ScriptEngineManager`, global variables can leak. This exercise assigns a fresh empty `GLOBAL_SCOPE` to each evaluation.

### 9.3. Adding the verification rule

Change the source from:

```text
amount <= limit
```

to:

```text
amount <= limit && verified
```

For unverified Alice (`verified=false`), the outcome changes from `ALLOW` to `DENY`. For the same Alice once verified (`true`), the outcome is `ALLOW`.

That is the goal of "**adding scripted rules**": approval criteria change via **rule source** and input data while the host keeps the `evaluate(...)` interface unchanged. With a real engine that has its own parser/language, scripts can be far more expressive; yet they still require versioning, testing, and edit-permission controls.

### 9.4. Missing engine detected before `eval`

The call:

```java
Outcome missing = evaluate(
        manager, "__missing_engine_demo_229__", "amount <= limit", alice);
```

attempts to look up an engine under an unregistered name. `manager.getEngineByName(...)` returns `null`, so the method returns `MISSING_ENGINE` **before creating Bindings and before running any script**.

This differs from `SCRIPT_ERROR`:

- **`MISSING_ENGINE`:** no provider/engine matches the configured name.
- **`SCRIPT_ERROR`:** an engine was obtained, but the script is unsupported, has syntax errors, or threw `ScriptException` at runtime.

In production, they need different alerts and diagnostic paths. Separating them prevents operators from wasting time debugging a script when an engine dependency is actually missing.

### 9.5. Faulty scripts and wrong result types

The toy engine intentionally recognizes only two Boolean expressions plus one test returning `String`. For `"amount >>> limit"`, it throws `ScriptException`, yielding status `SCRIPT_ERROR`.

For `"return text"`, `eval()` returns `"not a boolean"`, and since the authorization contract **accepts only Boolean**, the status is `INVALID_RESULT`.

An unchecked system might write:

```java
// COUNTEREXAMPLE: breaks contract, risks ClassCastException or logic errors.
boolean allowed = (Boolean) engine.eval(rule, context);
```

Here a syntactically valid script returning a String crashes the program. Checking `instanceof Boolean` ensures only properly typed outcomes map to `ALLOW`/`DENY`.

## 10. Safe Execution Flow for a Request

In a real API, separate `evaluate(...)` from **where the decision is enforced**:

```text
HTTP / Batch / Message Request
           |
           v
   Validate request fields
           |
           v
   Load allowed rule version
           |
           v
   Resolve configured engine
           |
     +-----+--------------------+
     |                          |
   missing                    exists
     |                          |
     v                          v
 MISSING_ENGINE          New Bindings/Context
                                |
                                v
                             eval(...)
                                |
             +------------------+------------------+
             |                  |                  |
          exception          wrong type         Boolean
             |                  |                  |
             v                  v                  v
        SCRIPT_ERROR      INVALID_RESULT    ALLOW / DENY
             |                  |                  |
             +----------+-------+------------------+
                        |
                        v
               Apply default-deny:
               only ALLOW authorizes
                        |
                        v
                Audit safe metadata
```

In a service method outside the demo, enforcement might look like:

```java
boolean approved = outcome.decision() == Decision.ALLOW;
```

This is an **excerpt** within a scope that has `outcome` and `Decision`, not a standalone file. For `MISSING_ENGINE`, `SCRIPT_ERROR`, `INVALID_RESULT`, and `DENY`, `approved` is `false`.

**Fail-closed does not preclude recovery.** You can return an accurate status so operators can fix the dependency/rule, and allow clients to retry once configuration is restored. However, recovery must never turn a technical fault into an unintended business approval.

## 11. What `Bindings` Does and Does Not Isolate

### 11.1. `ENGINE_SCOPE` and `GLOBAL_SCOPE`

`SimpleScriptContext` has two main scopes:

| Scope | What it is for | Risk if shared |
|---|---|---|
| `ENGINE_SCOPE` | Variables for a single eval, session, or engine context | Sharing a default map across requests allows requests to overwrite variables |
| `GLOBAL_SCOPE` | Wider shared variables | Tenant A's data may become visible to tenant B if shared |

In the example, after creating a local map via `engine.createBindings()`, the code attaches:

```java
context.setBindings(bindings, ScriptContext.ENGINE_SCOPE);
context.setBindings(new SimpleBindings(), ScriptContext.GLOBAL_SCOPE);
```

Thus both scopes are **explicitly bounded**. Calling only `engine.eval(rule, bindings)` on an engine with a default context may inherit other parts of that default context, including global scope; you must evaluate this behavior for your specific engine.

When the same variable name exists in both `ENGINE_SCOPE` and `GLOBAL_SCOPE`, scoped lookup typically prefers `ENGINE_SCOPE`. Therefore, accidentally placing a secret in global bindings remains risky: a script can read it whenever it is not shadowed.

### 11.2. A new map is not a deep copy

Illustrative example with mutable data:

```java
List<String> shared = new java.util.ArrayList<>();

Bindings alice = new SimpleBindings();
Bindings bob = new SimpleBindings();
alice.put("items", shared);
bob.put("items", shared);
```

Although `alice != bob`, both maps reference the same `shared` list. An engine capable of calling Java methods on that object can mutate the list seen by the other evaluation.

In a real system, pass only allowed, immutable types or controlled DTOs; never expose connections, credentials, internal registries, or privileged host objects to scripts simply because they run with separate `Bindings`.

### 11.3. Never assume an engine can be shared across threads

`ScriptEngineFactory.getParameter("THREADING")` describes the provider's concurrency guarantee. Values defined by the Java Scripting API are:

| Value | Meaning |
|---|---|
| `null` | Factory does not guarantee thread-safety; never execute scripts concurrently on one engine |
| `"MULTITHREADED"` | Engine supports concurrent script execution; state effects may be visible across threads |
| `"THREAD-ISOLATED"` | Satisfies `MULTITHREADED` and isolates symbols per thread |
| `"STATELESS"` | Satisfies the levels above and scripts do not mutate mappings in `ENGINE_SCOPE` bindings |

Note that `"STATELESS"` does not promise that scripts have no side effects on files, networks, or mutable objects; it pertains strictly to mappings inside the scope.

In the demo, `RuleFactory.getParameter("THREADING") == null`. `evaluate(...)` obtains a new engine per invocation so two concurrent requests never enter **the same** `RuleEngine` instance. Before optimizing with an engine pool or shared engine, evaluate lifecycle, state resets, concurrency, and tenant boundaries.

## 12. Evolving from Toy Rules to a Real Engine

This exercise teaches **JSR 223 and state management**, rather than requiring JavaScript specifically. When adopting an installed engine, the check flow can look like:

```java
ScriptEngineManager manager = new ScriptEngineManager();
ScriptEngine engine = manager.getEngineByName("JavaScript");

if (engine == null) {
    // No matching provider: fail closed / report missing configuration.
} else {
    ScriptEngineFactory factory = engine.getFactory();
    System.out.println(factory.getEngineName());
    System.out.println(factory.getEngineVersion());
    System.out.println(factory.getParameter("THREADING"));
}
```

This is an **illustrative snippet**, not a standalone program. `getEngineByName("JavaScript")` can return `null`; actual names, syntax, and registration depend on the installed provider.

To move to production, follow these steps in order:

1. Select a documented language/engine with JSR 223 integration compatible with your Java version.
2. Install the exact artifact and its dependencies, registering the factory via SPI or a supported configuration mechanism.
3. Verify `getEngineByName(configuredName)` actually returns an engine and log its name/version/provider.
4. Write a small rule in **the language's real syntax** and verify it returns Boolean as contracted.
5. Pass request data via isolated `Bindings` or `ScriptContext`; never build scripts by concatenating raw input.
6. Check `THREADING`, engine reuse safety, state reset behavior, lifetime, and multitenancy policies.
7. Design permission/capability allowlists and process isolation if scripts are untrusted; a custom class loader is not a sandbox.
8. Test `null`, syntax errors, wrong types, timeouts, side effects, and rollbacks.

**Warning:** not all providers share the same `"JavaScript"` name, Boolean representation, or host-object exposure semantics. Never copy `"amount <= limit && verified"` directly into another engine without checking whether it is valid syntax and how that language reads `Bindings`.

## 13. Missing Engine Scenarios in Real Environments

Common causes:

- Running **standard JDK 17** while forgetting to add a third-party script engine.
- Engine JAR is on the compile classpath, but dependencies are missing from the runtime classpath/module path.
- Provider advertises a different name than the configured one.
- `META-INF/services/javax.script.ScriptEngineFactory` or the module `provides` declaration was not packaged properly for the implementation type.
- Engine lives in a class loader or module layer invisible to the current `ScriptEngineManager`.
- Provider fails to initialize due to missing dependencies or version mismatches; this does not always manifest merely as `null`—it may throw during discovery or instantiation.

How to analyze: separate **factory not found** from **factory found but failed to initialize** and **engine failed while running script**. Inspect discovered factories with `manager.getEngineFactories()` when helpful, noting that the discovery list does not necessarily reflect names manually registered on a manager as in the toy example.

If an engine is missing in production, never do this:

```java
// COUNTEREXAMPLE: strictly avoid for authorization rules.
if (engine == null) {
    return true;
}
```

Recommended policy: fail closed, return `MISSING_ENGINE` or an explicit configuration error, alert operators, retain the active rule version, and never mark the request approved.

## 14. Automated Testing and Result Acceptance

A test suite for the rule engine should verify at least:

| Test case | Engine | Script | Data | Expected result |
|---|---|---|---|---|
| Basic allow | `toy-rule` | `amount <= limit` | Alice 80/100 | `ALLOW` |
| Basic deny | `toy-rule` | `amount <= limit` | Bob 150/100 | `DENY` |
| Isolation | `toy-rule` | Same script | Alice/Bob | Distinct `Bindings` references and separate `lastDecision` |
| Rule upgrade, missing verification | `toy-rule` | `amount <= limit && verified` | Alice false | `DENY` |
| Rule upgrade, verified | `toy-rule` | `amount <= limit && verified` | Alice true | `ALLOW` |
| Missing engine | Unregistered name | Any | Alice | `MISSING_ENGINE`, eval not called |
| Invalid syntax | `toy-rule` | `amount >>> limit` | Alice | `SCRIPT_ERROR` |
| Invalid return type | `toy-rule` | `return text` | Alice | `INVALID_RESULT` |
| Factory metadata | `toy-rule` | No eval needed | — | `THREADING=null` |
| Concurrency | Real provider | Multiple requests | Different data | No invalid shared access; honors factory threading contract |

Increase rigor with property-based tests around boundary values:

- `amount == limit` must yield `ALLOW` under `<=` when no extra conditions apply.
- `amount > limit` must yield `DENY`.
- With `&& verified`, **both** conditions must be true.
- Negative inputs, integer overflow, invalid limits, or contract-violating types must be **validated at the request layer** before reaching the script. The demo uses `int` to focus on the API, not to replace business validation.

For a third-party script engine, also test whether variables can be written back to `Bindings` after eval, global-scope variables, and shared Java objects; do not test only Boolean outputs.

## 15. Versioning and Operational Rules

A rule requires a **lifecycle** when used for critical decisions:

```text
Draft rule source
      |
      v
Validate syntax and contract
      |
      v
Test with a set of known requests
      |
      v
Review / approve rule version
      |
      v
Publish version N
      |
      v
Evaluate each request with snapshot of version N
      |
      v
Log rule ID/version + status + duration
```

Avoid mutating a shared rule string "mid-flight" during a request without versioning. When reading rules from a dynamic registry, callers should capture an **immutable snapshot** containing engine name, source text, version, and policy at the start of the request. Logs and debugging can then reproduce exactly which rule version evaluated the request.

Practical safeguards:

- **Fail fast at startup:** verify required engines exist and rule syntax is valid before serving traffic, while still handling missing engines safely at runtime.
- **Fail closed at runtime:** never default to allow when an engine or service errors.
- **Quotas and timeouts:** untrusted scripts can loop infinitely, allocate excessive memory, or block on I/O. `Future.cancel(true)`/`Thread.interrupt()` cannot force uncooperative code to stop; use process/OS boundaries if hard termination is needed.
- **Security:** restrict privileges of host objects passed to scripts; never put secrets in shared bindings; review filesystem, network, and native access.
- **Threading:** never reuse an engine unless its factory guarantees safety or exclusive ownership is enforced; separate `Bindings` alone does not make an engine thread-safe.
- **Data hygiene:** distinguish rule failures, missing providers, and legitimate denials; avoid sending source/bindings that may contain PII into unprotected logs.
- **Safe version transitions:** tag each request with an immutable rule version for auditing; support rollback and account for side effects of already-processed requests.

## 16. Extension Exercises

1. **Add a new rule:** extend the toy engine to support `"amount < limit && verified"`; test that `amount == limit` is denied while `amount < limit` with verified true is allowed.
2. **Add user data:** add a `"country"` key and a rule applying only to certain countries. Decide the policy when the key is missing: `SCRIPT_ERROR`, `DENY`, or a dedicated code? Explain why auto-allowing is wrong.
3. **Prove isolation:** add `context.setAttribute("trace", user, ENGINE_SCOPE)` in the engine; run three interleaved requests and prove each binding map keeps its own trace.
4. **Demonstrate global leak:** temporarily give a `ScriptEngineManager` global bindings containing `"region" = "X"`, remove the isolated `GLOBAL_SCOPE` assignment, and observe the global variable visible across both contexts; then restore safe isolation.
5. **Test missing engine:** replace `"toy-rule"` with an unregistered name and ensure the program returns `MISSING_ENGINE` without entering `createBindings` or `eval`.
6. **Test script error:** change the rule to an unsupported string. Verify `SCRIPT_ERROR` is distinct from `DENY` and still denied by authorization policy.
7. **Test non-Boolean result:** add a branch returning `null`, `Integer`, or `String`; it must return `INVALID_RESULT` without coercing to Boolean.
8. **Use a real engine:** install a JSR 223 provider compatible with Java 17, bind `Bindings` using the language's syntax, evaluate a Boolean rule, and inspect `THREADING`. Keep the `null` check in case the provider is absent.
9. **Dynamic version swap:** store an immutable `RuleSpec(id, version, engineName, source)` record; record the version in audit logs and support rollback after testing.
10. **Separate trust boundary:** assuming rules are submitted by internet users, design a worker process with CPU/RAM quotas, network allowlists, timeouts, and a request/response protocol rather than running inside the host JVM.

## 17. Exercise Completion Checklist

- [ ] Created a `ScriptEngineFactory` named `toy-rule` and registered it with `registerEngineName`.
- [ ] Looked up the engine with `getEngineByName`, **checking for `null` before use**.
- [ ] Created fresh `Bindings` per request via `engine.createBindings()`.
- [ ] Put properly typed `amount`, `limit`, and `verified` values into each map.
- [ ] Used `SimpleScriptContext` with an isolated `ENGINE_SCOPE` and an unshared `GLOBAL_SCOPE`.
- [ ] Only valid Boolean outputs from `eval(...)` map to `ALLOW`/`DENY`.
- [ ] Distinct outcomes exist for `MISSING_ENGINE`, `SCRIPT_ERROR`, and `INVALID_RESULT`.
- [ ] The new rule `amount <= limit && verified` works and changes outcome based on `verified`.
- [ ] Produced the exact 11 lines of stdout in section 8 on JDK 17+.
- [ ] Isolated `Bindings` are not mistaken for a sandbox or thread-safety guarantee.
- [ ] Business decisions grant access **only** when status is `ALLOW`.

**Conclusion:** Adding rules with JSR 223 is more than calling `ScriptEngine.eval`. A sound solution requires **safe engine lookup**, **passing isolated `Bindings` and explicit scopes per evaluation**, **validating the return type**, and **handling missing providers or script failures with a fail-closed policy**. That forms the foundation for scaling a small exercise into a testable, observable, and operable dynamic rule system.
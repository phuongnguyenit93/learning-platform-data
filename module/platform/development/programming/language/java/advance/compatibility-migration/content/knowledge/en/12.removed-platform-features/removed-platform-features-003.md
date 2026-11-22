# Nashorn and choosing a replacement JavaScript runtime

In many long-running Java systems, JavaScript does not appear only in the web frontend. Applications may embed JavaScript to evaluate business rules, transform data, generate report templates, extend functionality with plugins, or run administrator-configured scripts. A large portion of these systems previously relied on **Nashorn**, the JavaScript engine bundled in JDK 8 through JDK 14.

When upgrading the JDK to 15 or higher, Nashorn is no longer distributed with the JDK. Java code using `ScriptEngineManager` to look up an engine named `"nashorn"` may no longer find an engine; code importing Nashorn-specific classes may fail to compile. This is an **API and runtime environment compatibility** issue, not merely a Java version number change.

This lesson explains the Nashorn lifecycle, how to identify legacy dependencies, the difference between the standard `javax.script` API and a specific engine, and compares replacement options such as GraalJS, Rhino, standalone Nashorn, and Node.js. At the end is a migration workflow with Java examples, failure scenarios, and how to verify behavior after upgrading.

## 1. What is Nashorn?

Nashorn is a JavaScript engine previously bundled in the JDK, allowing JavaScript to run inside a Java process. Applications could access the engine through the Java Scripting API (JSR-223), or use Nashorn-specific APIs for deeper interaction with JavaScript objects.

A traditional program using Nashorn looks like this:

```java
import javax.script.ScriptEngine;
import javax.script.ScriptEngineManager;
import javax.script.ScriptException;

public class LegacyScriptDemo {
    public static void main(String[] args) throws ScriptException {
        ScriptEngine engine = new ScriptEngineManager()
                .getEngineByName("nashorn");

        Object value = engine.eval("10 + 20");
        System.out.println(value);
    }
}
```

On a JDK release that includes Nashorn, the example can print `30`. On a newer JDK without a corresponding JavaScript engine, `getEngineByName("nashorn")` returns `null` and calling `engine.eval(...)` throws a `NullPointerException`. The problem occurs because the engine is absent, even though the `javax.script` package still exists.

Nashorn also supported JVM integration utilities:

```javascript
var ArrayList = Java.type("java.util.ArrayList");
var values = new ArrayList();
values.add("alpha");
values.add("beta");
print(values.size());
```

`Java.type` and `print` in the example reflect the Nashorn environment; they are **not** APIs guaranteed to exist in every ECMAScript runtime or in Node.js. When switching engines, JavaScript code may need changes even if the language syntax remains valid.

## 2. Nashorn lifecycle across JDK milestones

Key milestones to remember:

| Version | Nashorn status in the JDK | Migration impact |
|---|---|---|
| JDK 8 | Nashorn was introduced and included in the JDK. | Legacy applications may implicitly depend on the built-in JavaScript engine. |
| JDK 9–10 | Nashorn continued to be bundled. | Accessible via `javax.script` and Nashorn APIs, depending on module configuration. |
| JDK 11 | JEP 335 marked the Nashorn engine, related APIs, and the `jjs` tool as deprecated for removal. | Replacement planning needs to begin. |
| JDK 12–14 | Nashorn remained present but was already scheduled for removal. | Running on these releases does not prove compatibility with JDK 15+. |
| JDK 15 onward | JEP 372 removed the Nashorn engine, its specific APIs, and `jjs` from the JDK. | An external engine, a different script execution solution, or moving logic out of JavaScript is required. |

The JDK modules removed by JEP 372 include `jdk.scripting.nashorn` and `jdk.scripting.nashorn.shell`. The `jjs` command-line tool bundled with Nashorn is also absent from newer JDKs.

**What was not removed:** The Java Scripting API `javax.script` and the `java.scripting` module remain part of the Java platform. A third-party library can supply a `ScriptEngine` implementation via the Service Provider Interface (SPI). Therefore, distinguish **the API for embedding scripts** from **the engine actually executing JavaScript**.

Do not try to solve the issue merely by changing `--release`, `-source`, or `-target` in the compiler. Those options adjust compilation and do not restore Nashorn to the runtime on JDK 15+.

## 3. Distinguishing JSR-223 from the Nashorn API

JSR-223 is the abstraction layer for Java applications to work with a scripting engine. Common types:

- `ScriptEngineManager`: discovers registered engines.
- `ScriptEngineFactory`: describes the name, version, and language supported by an engine.
- `ScriptEngine`: evaluates scripts and manages bindings and contexts.
- `Bindings` and `ScriptContext`: pass variables and configuration into an execution session.
- `Invocable`: invokes functions or methods in a script if supported by the engine.
- `Compilable` and `CompiledScript`: compile/reuse scripts if supported by the implementation.

Software that only uses the types above is usually easier to migrate to another engine than software importing engine-specific APIs such as:

```java
import jdk.nashorn.api.scripting.NashornScriptEngineFactory;
import jdk.nashorn.api.scripting.ScriptObjectMirror;
```

These two classes are Nashorn-specific APIs in older JDKs, not part of JSR-223. When switching engines, there is no guarantee that the new implementation provides equivalent classes or identical data-type conversions.

| Dependency in legacy code | Meaning | Level of adjustment needed |
|---|---|---|
| `javax.script.ScriptEngine` | Standard interface for executing scripts. | Can be kept when the new engine has a JSR-223 adapter. |
| `getEngineByName("nashorn")` | Discovers an engine by its specific name. | Needs engine name/declaration update and engine presence verification. |
| `jdk.nashorn.api.scripting.*` | Depends on the Nashorn implementation in the JDK. | Requires redesigning type conversion and interop. |
| `Java.type`, `Java.extend`, `Packages` | Nashorn-style Java interop. | Requires checking capabilities and access permissions of the replacement engine. |
| `jjs script.js` | Invokes the Nashorn tool via OS command. | Requires replacing the command or implementing a dedicated runner. |

Do not treat compiling cleanly with `java.scripting` as proof that the system has a JavaScript runtime. At runtime, the engine must be present and discoverable on the classpath or module path.

## 4. Identifying Nashorn dependencies before upgrading

Inventory where the program executes or stores scripts:

1. Java code instantiating `ScriptEngineManager` or `NashornScriptEngineFactory`.
2. Spring, workflow engines, rule engines, or libraries configured with `language=javascript`.
3. JavaScript stored in resources directories, databases, object storage, or configuration tables.
4. Build scripts, operational tools, and schedulers invoking `jjs`.
5. Plugins using `Java.type` or scripts accessing Java objects passed by the application.
6. Nashorn-specific APIs, such as `ScriptObjectMirror` or the parser API.
7. Integration points that require running JavaScript without being obvious in Java code.

You can search the source code or use your IDE with keywords such as:

```text
nashorn
jdk.nashorn
ScriptEngineManager
ScriptEngine
Invocable
Compilable
getEngineByName
Java.type
Java.extend
Java.super
Packages
jjs
```

These are inventory suggestions, not an exhaustive list. Scripts generated dynamically from databases, templates, or loaded at runtime may not appear in the repository. To determine actual usage, add controlled logging: which service runs the script, which script ID, frequency, execution duration, and error types.

When running checks on the new JDK, first check which engines are actually registered:

```java
import javax.script.ScriptEngineFactory;
import javax.script.ScriptEngineManager;

public class ListScriptEngines {
    public static void main(String[] args) {
        ScriptEngineManager manager = new ScriptEngineManager();

        for (ScriptEngineFactory factory : manager.getEngineFactories()) {
            System.out.println("Engine: " + factory.getEngineName());
            System.out.println("Language: " + factory.getLanguageName());
            System.out.println("Aliases: " + factory.getNames());
        }
    }
}
```

If no engines are listed, the output will typically print nothing. This does not mean the `javax.script` API was removed; it simply indicates that no provider was found in that runtime environment.

## 5. Why can't every engine be swapped by changing a name string?

JavaScript runtimes can differ across three layers:

**Language layer:** supported ECMAScript version, parsing behavior, built-in objects, module support, and Promise mechanics.

**Java interop layer:** how `Map`, `List`, and POJOs are passed from Java to JS; how Java methods are invoked; return types; overload resolution, arrays, exceptions, and host classes.

**Environment layer:** file/network access permissions, class loaders, threads, `javax.script` compatibility, presence of Node.js APIs, context management, and runtime packaging.

For example, the JavaScript snippet:

```javascript
const Files = Java.type("java.nio.file.Files");
```

may work in an engine that supports Java interop and grants Java class access, but it is not a built-in API syntax in Node.js. Conversely:

```javascript
import { readFile } from "node:fs/promises";
```

is a call to a built-in Node.js module, which does not automatically work inside a JavaScript context embedded in the JVM. Therefore, choosing a runtime must start from **the actual requirements of the scripts**, not just the JavaScript language name.

## 6. Common replacement options

| Option | Execution model | Strengths | Migration notes |
|---|---|---|---|
| **GraalJS with Polyglot API** | JavaScript runs directly inside the JVM via `org.graalvm.polyglot.Context`. | Modern ECMAScript, fine-grained configurable Java interop. | Requires adding dependencies and migrating embedded code away from JSR-223 if adopting the new API. |
| **GraalJS via JSR-223** | External `ScriptEngine` adapter outside the JDK. | Preserves part of the Java architecture using `javax.script`. | Separate adapter module; JS semantic and host access differences still need testing. |
| **Standalone Nashorn** | Nashorn engine packaged as an independent library. | Retains many legacy scripts during the transition period. | Not re-integrated into the JDK; still requires dependency management, maintenance, and a long-term plan. |
| **Rhino** | JavaScript engine written in Java, embedded via its own API or JSR-223 adapter. | Runs inside the JVM; can suit some long-running Java systems. | Verify ECMAScript support level, Java interop, modules, and JDK baseline per version. |
| **Node.js** | JS runtime running in a separate process. | Well suited for JS applications using npm and Node built-ins. | Not an in-JVM engine; requires inter-process communication and deployment management. |
| **Move logic to Java or a DSL** | No JavaScript runtime needed. | Eliminates engine dependency if scripts are few, stable, and pure business logic. | Requires conversion effort and behavioral equivalence testing. |

No single option is always best for every system. If scripts only consist of simple application-controlled expressions, migrating to Java/a DSL may fit well. If modern JavaScript embedded in the JVM with selective Java API calls is needed, GraalJS is a strong candidate to evaluate. If scripts were written for Node.js and rely heavily on npm packages, executing via Node in a separate process is usually more natural.

## 7. GraalJS: replacing embedded JavaScript with the Polyglot API

GraalJS is the JavaScript implementation in the GraalVM ecosystem and can be added to applications running on a compatible JDK via dependencies. Do not assume that installing a new JDK automatically includes a JavaScript engine. With modern GraalJS, the recommended embedding approach is using `org.graalvm.polyglot.Context`.

### 7.1. Configuring Maven dependencies

The following Maven example uses the Community artifact group. Choose a **consistent, tested** version across all dependencies:

```xml
<properties>
    <graaljs.version>25.3.4.1</graaljs.version>
</properties>

<dependencies>
    <dependency>
        <groupId>org.graalvm.polyglot</groupId>
        <artifactId>polyglot</artifactId>
        <version>25.3.4.1</version>
    </dependency>
    <dependency>
        <groupId>org.graalvm.polyglot</groupId>
        <artifactId>js-community</artifactId>
        <version>25.3.4.1</version>
        <type>pom</type>
    </dependency>
</dependencies>
```

`25.3.4.1` here is an example version from the GraalJS guide, **not a fixed requirement** for every project. When deploying, update to the release selected by your organization and verify licensing, JDK requirements, compatibility, and BOM/dependency resolution. The `js` artifact differs from `js-community` in distribution/licensing, so verify which option fits your organization.

### 7.2. Executing simple JavaScript

```java
import org.graalvm.polyglot.Context;
import org.graalvm.polyglot.Value;

public class GraalJsHello {
    public static void main(String[] args) {
        try (Context context = Context.newBuilder("js").build()) {
            Value result = context.eval("js", "21 * 2");
            System.out.println(result.asInt());
        }
    }
}
```

Output:

```text
42
```

`Context` represents the JS execution environment. `try-with-resources` ensures the context is closed after use. The `Value` object wraps a JS value and provides methods to convert to appropriate Java types. Do not retain a `Value` and continue using it after the context has closed.

### 7.3. Passing data from Java to JavaScript

To evaluate rules with input data:

```java
import org.graalvm.polyglot.Context;
import org.graalvm.polyglot.Value;

public class DiscountRule {
    public static void main(String[] args) {
        try (Context context = Context.newBuilder("js").build()) {
            context.getBindings("js").putMember("subtotal", 150.0);
            context.getBindings("js").putMember("discountRate", 0.10);

            Value result = context.eval(
                    "js",
                    "subtotal * (1 - discountRate)");

            System.out.println(result.asDouble());
        }
    }
}
```

Expected output:

```text
135.0
```

This example suits simple arithmetic expressions. In financial applications, control calculation and rounding carefully; do not use `double` for money if business rules require exact decimal precision.

### 7.4. Allowing scripts to call selected Java methods

An important difference from many legacy Nashorn applications is that GraalJS leans toward secure configuration: host interaction is permitted only when explicitly granted. You can expose only a specific method under the `HostAccess.EXPLICIT` policy:

```java
import org.graalvm.polyglot.Context;
import org.graalvm.polyglot.HostAccess;

public class RestrictedInteropDemo {
    public static final class PricingFunctions {
        @HostAccess.Export
        public double applyDiscount(double subtotal, double rate) {
            if (subtotal < 0 || rate < 0 || rate > 1) {
                throw new IllegalArgumentException("Invalid input");
            }
            return subtotal * (1 - rate);
        }
    }

    public static void main(String[] args) {
        try (Context context = Context.newBuilder("js")
                .allowHostAccess(HostAccess.EXPLICIT)
                .allowHostClassLookup(name -> false)
                .build()) {

            context.getBindings("js")
                    .putMember("pricing", new PricingFunctions());

            double result = context.eval(
                    "js",
                    "pricing.applyDiscount(200, 0.15)")
                    .asDouble();

            System.out.println(result);
        }
    }
}
```

Scripts can call only the methods permitted by the host access policy. `@HostAccess.Export` marks the public methods to expose. `allowHostClassLookup(name -> false)` prevents scripts from arbitrarily looking up Java classes via `Java.type`. This is an example of controlling the API surface; when running untrusted scripts, resource limits, time limits, and isolation are still needed.

Do not simply enable `HostAccess.ALL` with a predicate allowing all Java classes just to keep legacy scripts running. That configuration can grant far more access than the business logic requires.

## 8. GraalJS with `ScriptEngine`: a transitional path

If existing Java code makes heavy use of `ScriptEngine`, `Bindings`, or `Invocable`, you can consider GraalJS's JSR-223 adapter. This helps retain part of the Java invocation interface.

**Note:** In recent GraalVM releases, the ScriptEngine adapter is not necessarily bundled with the JDK by default. Declare the `org.graalvm.js:js-scriptengine` dependency and ensure the JavaScript runtime is packaged with the application.

Example additional Maven dependency:

```xml
<dependency>
    <groupId>org.graalvm.js</groupId>
    <artifactId>js-scriptengine</artifactId>
    <version>25.3.4.1</version>
</dependency>
```

This dependency uses the same GraalJS version as the dependencies in the previous section. In JPMS projects, the adapter must appear in the module graph; depending on the configuration, `--add-modules org.graalvm.js.scriptengine` may be required.

Example checking the engine before calling:

```java
import javax.script.ScriptEngine;
import javax.script.ScriptEngineManager;
import javax.script.ScriptException;

public class GraalJsr223Demo {
    public static void main(String[] args) throws ScriptException {
        ScriptEngineManager manager = new ScriptEngineManager();
        ScriptEngine engine = manager.getEngineByName("graal.js");

        if (engine == null) {
            throw new IllegalStateException(
                    "GraalJS ScriptEngine not registered");
        }

        Object value = engine.eval("6 * 7");
        System.out.println(value);
    }
}
```

An engine can be registered under multiple aliases. Always retrieve engine names from `getEngineFactories()` in your application's runtime instead of guessing valid names. If multiple engines register the `"JavaScript"` alias, choose an unambiguous alias to avoid accidentally switching implementations.

**Pros and limitations:** JSR-223 reduces the amount of Java code that must change immediately; however, swapping engines can still alter JS syntax, Java interop, result conversions, and security defaults. GraalJS recommends `Context` when fine-grained configuration control is needed. For new code, consider building an application adapter around `Context` instead of adding further direct dependencies on `ScriptEngine`.

## 9. Migrating from `Invocable` to `Value.execute`

Nashorn with JSR-223 was often used to call a JS function:

```java
import javax.script.Invocable;
import javax.script.ScriptEngine;
import javax.script.ScriptEngineManager;

public class LegacyFunctions {
    public static void main(String[] args) throws Exception {
        ScriptEngine engine = new ScriptEngineManager()
                .getEngineByName("nashorn");

        engine.eval("function multiply(a, b) { return a * b; }");
        Object answer = ((Invocable) engine)
                .invokeFunction("multiply", 6, 7);

        System.out.println(answer);
    }
}
```

With the Polyglot API, a JS function can be retrieved as a `Value` and invoked directly:

```java
import org.graalvm.polyglot.Context;
import org.graalvm.polyglot.Value;

public class PolyglotFunctions {
    public static void main(String[] args) {
        try (Context context = Context.newBuilder("js").build()) {
            context.eval(
                    "js",
                    "function multiply(a, b) { return a * b; }");

            Value fn = context.getBindings("js")
                    .getMember("multiply");

            int answer = fn.execute(6, 7).asInt();
            System.out.println(answer);
        }
    }
}
```

In real systems, handle cases where the function does not exist or cannot be executed, script errors, and result type checks. This invocation style replaces the dependency on `Invocable` with GraalVM's own API; this is an architectural choice that should be wrapped in an adapter layer if the application needs the ability to swap engines later.

## 10. JavaScript and Java interop differences when migrating from Nashorn

Not every Nashorn script is equivalent to a GraalJS script, even though both execute JavaScript. Points to review include:

| Topic | Common in legacy Nashorn scripts | What to check when migrating |
|---|---|---|
| Java class access | `Java.type("java.util.ArrayList")` | GraalJS can support it, but host class lookup must be allowed. |
| Package globals | `java.*`, `javax.*`, `Packages.*` | May require enabling compatibility features or rewriting to `Java.type`. |
| Helper functions | `Java.from`, `Java.to`, `Java.extend` | Check engine version and Java interop configuration; refactoring may be required. |
| Host objects | `ScriptObjectMirror` | Migrate to `Value`/bindings or explicit DTOs. |
| Java overload | Direct calls to overloaded methods | Check conversion rules for numbers, strings, arrays, and overload resolution. |
| Script outputs | `print()`, `load()` functions | Not guaranteed to exist identically across all engines or contexts. |
| Language | Older ECMAScript versions and Nashorn extensions | Run tests for syntax, strict mode, `this`, scope, and `undefined`. |
| Modules and npm | Scripts embedded from resources | Node.js built-in modules such as `fs` or `http` are not automatically present. |

When migrating, separate two kinds of changes:

1. **Standardize scripts to pure ECMAScript:** reduce reliance on `Java.type`, `Packages`, `ScriptObjectMirror`, and engine-specific helpers.
2. **Choose a new host integration:** Java exposes permitted DTOs/operations via bindings or an equivalent API, instead of letting scripts arbitrarily look up and call any Java class.

This separation makes JS logic easier to test and reduces the cost of changing runtimes in future upgrades.

### 10.1. GraalJS's Nashorn compatibility mode

GraalJS provides a Nashorn compatibility mode to support certain Nashorn extensions:

```java
import org.graalvm.polyglot.Context;

public class CompatibilityModeExample {
    public static void main(String[] args) {
        try (Context context = Context.newBuilder("js")
                .allowExperimentalOptions(true)
                .option("js.nashorn-compat", "true")
                .build()) {
            context.eval("js", "print('legacy compatibility')");
        }
    }
}
```

The `js.nashorn-compat` setting is a compatibility option and does not guarantee every Nashorn script will run unmodified. It can enable extra features that weaken secure defaults; review carefully before using it with untrusted scripts. This mode may also adjust the language to an older ECMAScript level; to use newer syntax, check and configure `js.ecmascript-version` appropriately if supported by the engine.

Treat compatibility mode as a **migration bridge**, paired with tests and a plan to phase out Nashorn-specific extensions, rather than a final solution for every project.

## 11. Standalone Nashorn: preserving legacy systems during transition

After the engine was removed from the JDK, the standalone Nashorn project continued to be maintained by the OpenJDK community as a separate library. The well-known artifact is `org.openjdk.nashorn:nashorn-core`; the project declares compatibility with Java 11 and later.

This can be a suitable path when:

- Many legacy scripts depend on `Java.type` or Nashorn-specific behavior.
- A JDK upgrade is needed soon without enough time to rewrite all scripts.
- You want to reduce change scope in one deployment and defer swapping the engine to a subsequent phase.

However, standalone Nashorn **is not the JDK-bundled Nashorn**. The application must declare the library and its transitive dependencies, including the ASM components used by the project; the implementation's classes/modules have different names from the version in older JDKs.

Example Maven dependency declaration (replace `NASHORN_VERSION` with a confirmed compatible version):

```xml
<dependency>
    <groupId>org.openjdk.nashorn</groupId>
    <artifactId>nashorn-core</artifactId>
    <version>NASHORN_VERSION</version>
</dependency>
```

When running on the module path, ensure the `org.openjdk.nashorn` module and its dependent modules resolve properly. If Java code still imports `jdk.nashorn.api.scripting.*`, merely adding the dependency will not bring back the old package; update imports and specific API usages based on the standalone Nashorn documentation.

Do not treat this as a long-term solution simply because the application starts up. Factor in release cadence, bug fixes, security, licensing, ECMAScript support level, and a plan to replace legacy extensions.

## 12. Rhino: a JavaScript engine written in Java

Rhino is a JavaScript engine developed in Java and continues to have standalone releases. It can be embedded in a Java application or used via a JSR-223 adapter if the corresponding dependency is provided.

In some Rhino versions, the JSR-223 engine resides in a separate `rhino-engine` artifact alongside `rhino`. Therefore, adding only the core engine does not guarantee `ScriptEngineManager` will find the JavaScript alias. Check release notes and the dependency graph before deploying.

Modern Rhino supports many newer ECMAScript features, though feature completeness varies by release. Do not assume Rhino always behaves identically to Nashorn, GraalJS, or Node. Rhino also sets per-version JDK baselines: for example, Rhino 1.9 releases require JDK 17 or later to run, whereas older versions have lower requirements.

Areas to test when choosing Rhino:

- The JavaScript syntax subset used by existing scripts.
- How Java objects, arrays, primitives, and exceptions cross the JS/Java boundary.
- Compatibility with the `javax.script` API if host code relies on JSR-223.
- Context/threading strategy in server applications.
- Module/classpath setup, sandbox configuration, and minimum runtime JDK.

Rhino can fit projects requiring an engine implemented in Java. The decision should be based on benchmarks and tests of the system's own scripts, not merely a generic feature comparison table.

## 13. Node.js: running JavaScript in a separate process

Node.js fits when the system must execute scripts designed for Node, use many npm packages, or depend on built-in modules such as `node:fs`, `node:http`, and the event loop.

The architecture then changes:

```text
Java application
      |
      | JSON / HTTP / gRPC / IPC
      v
JavaScript worker (Node.js process)
      |
      +-- npm packages
      +-- Node.js APIs
      +-- async tasks / event loop
```

Java does not call `ScriptEngine.eval(...)` to run JS inside the JVM; instead, Java sends data and receives results over a protocol. A persistent worker, queue, or separate service can be used, depending on load and operational requirements.

Advantages:

- Runs scripts on the true Node.js runtime and its package ecosystem.
- Provides a clear process boundary to limit CPU, memory, and access permissions using OS/container tools.
- Allows upgrading the JS runtime version independently of the JDK if the protocol stays stable.

Costs:

- Must deploy, monitor, and update a second runtime/service.
- Incurs communication latency and serialization overhead.
- Requires managing timeouts, retries, idempotency, ordering, and request correlation.
- Arbitrary Java objects cannot be passed directly Nashorn-style; a DTO/wire format must be designed.

If only short expressions need evaluation, spawning a separate Node process per request can be expensive. If using a long-lived process, manage concurrency, worker failures, and per-request isolation. For untrusted input, apply appropriate container/process isolation and resource limits; do not assume a Node process is a safe sandbox by default.

## 14. Considering replacing JavaScript with Java or a DSL

Not every application with scripts needs to keep a JavaScript engine forever. If scripts only perform predefined calculations or rules, the logic can be moved into Java or an expression-restricted domain-specific language (DSL).

For example, instead of allowing arbitrary configuration:

```javascript
if (cart.total > 1000 && cart.member) {
    cart.discount = 0.1;
}
```

a rule can be represented as data:

```json
{
  "minTotal": 1000,
  "memberRequired": true,
  "discountRate": 0.1
}
```

Java reads the data and evaluates it under controlled logic. This approach reduces the chance of configurators interacting with objects/methods outside the contract. In return, it is less flexible than arbitrary JavaScript and requires converting existing scripts.

This path is worth considering when rules rarely change structure, audit requirements are high, and the JavaScript feature set is far larger than what is actually needed.

## 15. Designing an adapter to reduce engine coupling

An architectural mistake is letting business code call `ScriptEngine` or `Context` directly in dozens of places. When changing engines, every single one of those call sites must be modified.

You can define an internal contract:

```java
import java.util.Map;

public interface RuleRuntime {
    RuleResult evaluate(
            String ruleId,
            String script,
            Map<String, Object> inputs);
}
```

```java
public record RuleResult(boolean matched, String explanation) {
}
```

One implementation can use GraalJS; another can call a Node worker. External callers only see the `RuleRuntime` contract and the return value.

When designing the adapter, specify:

- Accepted language and syntax version.
- Input/output types, and rules for `null`, missing fields, decimals, and date/time.
- How syntax, runtime, resource, and timeout errors are reported.
- Access permissions for host APIs, files, network, and processes.
- Limits on invocation count, time, memory, and script size.
- Context initialization lifecycle, compiled code caching, and thread management.
- Script versioning rules during rolling deployments or rollbacks.

An adapter clarifies which part of the contract belongs to the application and which behavior belongs to the engine. It also allows running both implementations against the same fixture suite to compare migration results.

## 16. Data compatibility points to verify

Changing the JavaScript engine can alter results even when scripts report no errors.

### 16.1. Arithmetic and type conversion

JavaScript Number typically uses IEEE 754 floating-point numbers. When passing `long`, `BigInteger`, or `BigDecimal` from Java into the engine, each implementation can have its own conversion and host interop rules.

For example, Java integers exceeding the exact representation limit of a JavaScript Number can lose precision if coerced to Number. Test boundary values, negative numbers, very large numbers, `NaN`, `Infinity`, and rounding rules. For currency, prefer controlled representations instead of silently converting `BigDecimal` to `double`.

### 16.2. `null`, `undefined`, and missing fields

A Java object with a `null` field differs from a non-existent JS property yielding `undefined`. Host object wrapping and converting results back to Java can differ among Nashorn, GraalJS, and Rhino. Tests must distinguish:

```javascript
const a = { value: null };
const b = {};

console.log(a.value === null);      // true
console.log(b.value === undefined); // true
```

If the system uses script output to write to a database or send messages, clearly define the mapping between missing values and null values.

### 16.3. Date, timezone, and locale

Scripts may call `Date`, convert timestamps, or format according to locale. When upgrading the runtime, check the default timezone, parsing of non-standard strings, ISO-8601 handling, and daylight saving time. Pass timestamps using explicit UTC/epoch representations rather than letting the engine infer them.

### 16.4. Collections, objects, and exceptions

Nashorn-specific `ScriptObjectMirror` is not directly equivalent to `org.graalvm.polyglot.Value` or Rhino's wrappers. If a business API returns a JS object, convert it into an explicit DTO or JSON structure before passing it across other layers.

Exceptions from Java code invoked by a script can also be wrapped differently. Do not depend on specific exception class names or strings when the goal is simply recognizing business errors. Use an explicit error code/contract at the adapter boundary.

## 17. Security when running scripts

A script can be:

- **Trusted:** resides in the source repository and is reviewed like application code.
- **Semi-trusted:** configured by administrators, yet can still be erroneous or abused.
- **Untrusted:** comes from users or external sources outside the application's control.

The level of control must match the script's origin. Do not assume that replacing Nashorn with a newer engine means scripts are safely isolated.

Issues to identify:

1. **Host access:** which Java methods can the script call? Can it look up classes via `Java.type`?
2. **File/network/process:** does the script have permission to read files, open connections, or execute OS commands?
3. **Resources:** how much CPU/memory can an infinite loop or large object allocation consume?
4. **Secrets:** can the script see credentials, environment variables, service tokens, or objects holding sensitive data?
5. **Tenant isolation:** do scripts from two tenants share a context, global variables, or caches?
6. **Audit:** can you identify the script ID, version, deployer, and failure reason?

With GraalJS, use a restricted host access policy, avoid exposing the entire classpath, and do not enable Nashorn compatibility mode without an evaluated need. For truly untrusted scripts, consider process/container-level isolation and enforce time/memory limits, since scripts running in the same JVM still share resources with the application.

Do not rely on Java's legacy `SecurityManager` as the sole sandboxing mechanism; Security Manager policies have changed in newer JDKs. Limits must be verified on the exact target JDK/runtime.

## 18. Engine performance and lifecycle

Depending on the option chosen, starting an engine/context and compiling scripts can carry different costs. Some general principles:

**Do not create contexts indiscriminately for every tiny evaluation:** under high load, initialization overhead can be significant. However, reusing contexts also requires managing state and threading.

**Separate script code from request data:** source or compiled scripts can be cached keyed by script ID/version, without letting one user's request data leak into another request.

**Set timeout and resource limits:** `Future.cancel(true)` or interrupting a Java thread alone does not always guarantee stopping every engine execution path. If strong isolation is required, use a process boundary and worker termination capabilities.

**Measure on realistic workloads:** benchmarking simple addition may not reflect real scripts calling Java methods, parsing JSON, creating objects, or accessing data. Measure startup time, steady-state throughput, P95/P99 latency, memory, and post-warmup performance.

**Manage dependency versions:** the engine runtime and accompanying dependencies must receive security updates alongside the application's release cycle. When upgrading the engine, re-run the script compatibility suite just as when upgrading the JDK.

## 19. Step-by-step Nashorn migration workflow

### Step 1: Identify usage scope

Collect the list of call sites, script IDs, script storage locations, Java objects passed in, engine version, and current JDK runtime. Flag scripts containing Nashorn-specific features or broad host access.

### Step 2: Lock down behavioral contracts

For each critical script, record inputs, outputs, expected errors, side effects, timezone, numeric precision, and execution duration. Save representative scripts/golden fixtures with sensitive information scrubbed.

### Step 3: Choose a replacement runtime

Cross-check requirements for Java interop, ECMAScript, npm packages, isolation, JDK baseline, licensing, and operations. Build a proof-of-concept on a representative script set.

### Step 4: Extract an adapter

Move engine-invoking code into a dedicated module/class. Define inputs and outputs independently of `ScriptObjectMirror`, `Value`, and engine-specific objects.

### Step 5: Run in parallel for comparison

In tests or staging, evaluate the same inputs using both the old and new engines. Compare results **semantically** rather than by raw string comparison if property order, numeric types, or exception representations may differ.

### Step 6: Test security and resource limits

Test scripts with infinite loops, unauthorized class/file access, large inputs, exceptions, `null`, `undefined`, concurrent execution, and provider initialization failures.

### Step 7: Roll out progressively

If the system supports it, shift groups of scripts or a percentage of traffic to the new runtime. Monitor error rates, execution time, memory, output discrepancies, and fallback counts.

### Step 8: Decommission legacy Nashorn dependencies

Once confirmed that no scripts require the old engine, remove dependencies, compatibility flags, engine-specific imports, `jjs` commands, and obsolete configuration. Update documentation on supported JavaScript runtimes.

## 20. Example behavioral compatibility test

Suppose the system has a script calculating a discount rate:

```javascript
function calculateDiscount(subtotal, isMember) {
    if (subtotal >= 1000 && isMember) {
        return 0.10;
    }
    return 0;
}
```

A fixture suite can use:

| Subtotal | Member | Expected result |
|---:|---|---:|
| 999.99 | true | 0 |
| 1000.00 | true | 0.10 |
| 1500.00 | false | 0 |
| 1500.00 | true | 0.10 |

In Java, the adapter can run the script and return a `RuleResult` object or a numeric value per the contract. Tests compare results against fixtures on both the source and target engines. Beyond simple examples, include fixtures for numeric limits, `null`, exceptions, array/object handling, and Nashorn helpers currently in use.

A common migration mistake is writing tests that only verify "the script does not throw an exception". That fails to catch subtle changes in default values, rounding, or Java method overload selection.

## 21. Common errors after upgrading the JDK

### 21.1. `getEngineByName(...)` returns `null`

**Symptom:** code uses `ScriptEngineManager` but no matching provider exists, resulting in a `NullPointerException`.

**Resolution:** check `getEngineFactories()`, add the right engine/adapter dependency, and ensure the classpath/module path reflects the actual environment. Update the engine name to an alias declared by the provider.

### 21.2. `ClassNotFoundException` or `NoClassDefFoundError` for `jdk.nashorn.*`

**Symptom:** Java code imports Nashorn-specific classes from older JDKs.

**Resolution:** replace engine-specific APIs with a modern adapter. If using standalone Nashorn, check the new package/module names and migration notes rather than assuming the old package was restored.

### 21.3. `NoSuchFileException` / `command not found` when invoking `jjs`

**Symptom:** operational scripts still invoke the JDK's bundled Nashorn shell.

**Resolution:** replace the command with a new runner, package the accompanying runtime, and update CI/container images.

### 21.4. `Java is not defined` or unable to access Java classes

**Symptom:** scripts contain `Java.type` or package globals, but the engine lacks Java interop or permission.

**Resolution:** identify actual requirements, use restricted bindings/host APIs, or configure host class lookup within an allowed scope. Avoid granting unrestricted permissions just to get past initial errors.

### 21.5. Scripts work on a developer machine but fail when packaged with JPMS

**Symptom:** the engine is discovered on the classpath but missing after switching to the module path or a custom runtime image.

**Resolution:** check the `java.scripting` module, the engine adapter module, service provider registration, the resolved module graph, and `jlink` arguments if applicable.

### 21.6. Output differs without throwing an exception

**Symptom:** scripts return different values due to numeric coercion, `null`/`undefined` semantics, timezone, or object handling.

**Resolution:** compare golden fixtures against the data contract; fix mapping in the adapter or standardize the JS.

### 21.7. JavaScript runs too long or increases memory usage

**Symptom:** scripts contain non-terminating loops, retain large objects, mis-cache contexts, or repeatedly initialize engines.

**Resolution:** enforce resource budgets, measure on realistic workloads, manage lifecycles, and consider running scripts in a separate process if isolation is required.

## 22. Checklist before releasing the upgrade

- [ ] Located all Nashorn, JSR-223, and `jjs` usages.
- [ ] Identified scripts in repositories, resources, configuration, and databases.
- [ ] Listed Nashorn-specific extensions and Java interop usages.
- [ ] Confirmed the name, version, dependencies, and JDK baseline of the replacement runtime.
- [ ] Confirmed the new runtime is packaged in the artifact/container.
- [ ] Decoupled input/output contracts from the legacy engine's classes.
- [ ] Tested JS results on boundary values and golden fixtures.
- [ ] Verified conversions for `null`, `undefined`, numbers, arrays/objects, and exceptions.
- [ ] Designed an appropriate host access policy and resource limits.
- [ ] Tested concurrency, caching, and context/engine lifecycle.
- [ ] Tested classpath, module path, or custom images matching deployment configuration.
- [ ] Prepared a rollback/fallback plan and post-release monitoring metrics.
- [ ] Planned removal of the legacy engine/compatibility flags at the end of the transition phase.

## References

- [JEP 335 — Deprecate the Nashorn JavaScript Engine](https://openjdk.org/jeps/335): deprecation milestone in JDK 11.
- [JEP 372 — Remove the Nashorn JavaScript Engine](https://openjdk.org/jeps/372): decision to remove Nashorn in JDK 15 and its scope of impact.
- [Oracle JDK 15 Migration Guide](https://docs.oracle.com/en/java/javase/15/migrate/): tool and component changes in JDK 15.
- [Java API — ScriptEngineManager](https://docs.oracle.com/en/java/javase/21/docs/api/java.scripting/javax/script/ScriptEngineManager.html): engine discovery mechanism under JSR-223.
- [GraalJS — Run JavaScript on the JVM](https://www.graalvm.org/latest/reference-manual/js/RunOnJDK/): how to add dependencies and embed GraalJS.
- [GraalJS — Nashorn Migration Guide](https://www.graalvm.org/latest/reference-manual/js/NashornMigrationGuide/): Java interop differences and compatibility mode.
- [GraalJS — ScriptEngine](https://www.graalvm.org/latest/reference-manual/js/ScriptEngine/): the JSR-223 adapter and how to configure it.
- [OpenJDK Standalone Nashorn](https://github.com/openjdk/nashorn): the standalone Nashorn engine project.
- [Mozilla Rhino](https://github.com/mozilla/rhino): JavaScript engine written in Java and release notes.
- [GraalJS — JavaScript Modules and Packages](https://www.graalvm.org/reference-manual/js/NodeJSvsJavaScriptContext/): differences between embedded JavaScript and Node.js.

## Conclusion

Nashorn was once the JavaScript engine bundled in the JDK, but it was deprecated in JDK 11 and removed in JDK 15. Applications can continue using `javax.script` if a compatible engine is added, though retaining the `ScriptEngine` API does not automatically guarantee Nashorn scripts will execute properly. GraalJS with `Context` fits when modern JavaScript embedded in the JVM and controlled Java interop are needed; GraalJS JSR-223 or standalone Nashorn can support the transition phase; Rhino and Node.js fit different runtime and ecosystem requirements. The decision should be based on actual scripts, required Java access, JDK baseline, security, and operational cost, and then confirmed with golden fixtures and testing on real deployment environments.
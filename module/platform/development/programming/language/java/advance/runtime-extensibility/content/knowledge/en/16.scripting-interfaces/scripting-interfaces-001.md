# Type Conversion Between Java and Scripting Languages According to Engine Rules

## 1. Nature of the Java ↔ Script Boundary

In a Java application embedding scripts via JSR 223 (`javax.script`), the Java program passes data into a `ScriptEngine`, lets the script perform computations, and then receives data back. A common misconception is that **JSR 223 does not mandate a universal type conversion table for all languages**. The API only exchanges Java objects through `Bindings`, `ScriptContext`, and the `Object` value returned from `eval`; the specific engine decides how those objects are represented, coerced, converted, and accessed from the scripting language side.

For example, `java.lang.Integer` may be viewed as an integer, a dynamic number, a wrapped Java object (*host object*), or a special value depending on the engine. An array, `List`, `Map`, `null`, or domain object also does not behave uniformly across JavaScript, Python, Groovy, Kotlin scripting, and other runtimes.

### Three Independent Steps

1. **Marshalling into the script**: the host places a Java object into `Bindings`/`ScriptContext`; the engine maps that object to a value visible to the script.
2. **Computation and API calls**: the script may apply numeric coercion rules, property lookup, overload resolution, and its own internal conversions.
3. **Marshalling back to Java**: `ScriptEngine.eval(...)` returns `Object`; the host must check the actual runtime class and convert it to the desired domain type according to a defined contract.

You should not infer a value's type solely from script syntax. Check the engine documentation, specific version, and run compatibility tests before building a stable API.

## 2. What Does JSR 223 Provide and Not Provide?

| Component | JSR 223 Contract | Not Universally Guaranteed |
|---|---|---|
| `ScriptEngine.put(name, Object)` | Places a value into the engine-scope bindings | Which script type the engine exposes the Java object as |
| `Bindings` | Maps a `String` key to a Java value | Automatically converting `Map`, `List`, `record` into native script objects |
| `ScriptContext` | Manages scopes, reader/writer/error writer, and attributes | Security isolation or preventing all side effects |
| `ScriptEngine.eval(source)` | Evaluates a script, returning a Java `Object` or `null` | Numeric results always being `Integer`/`Double` or booleans always being `Boolean` |
| `Invocable.invokeFunction/invokeMethod` | Invokes a function/method if the engine implements `Invocable` | Every engine supporting function invocation or automatically resolving overloads accurately |
| `getInterface(...)` | Optionally maps a script to a Java interface | Every engine supporting it or sharing the same type conversion rules |

JDK 17 includes the `java.scripting` module containing the API, but **does not bundle a JavaScript engine**. Nashorn was removed from the JDK in Java 15. To use JavaScript, Python, or Groovy, a suitable engine must be installed and visible via the module path or class loader. This lesson therefore uses a minimal JSR 223 engine to demonstrate the contract without depending on external libraries.

## 3. Common Type Categories

### 3.1. Numbers: Integer, Long, Double, BigDecimal

An engine may use 64-bit floating-point numbers for all calculations, distinguish integers from floats, use big integers, or return Java wrappers. When returning results to Java, **do not perform a hard cast** without checking first:

```java
Object result = engine.eval("someNumericExpression");
if (!(result instanceof Number number)) {
    throw new IllegalArgumentException("Expected numeric result");
}
double value = number.doubleValue();
```

This is an illustrative snippet and does not run standalone because it requires `engine`. `doubleValue()` can lose precision for `BigDecimal` or very large integers; for monetary values or exact data, use a contract that returns a decimal string or `BigDecimal` when the engine supports it.

Conversion rules should be written down explicitly: what range non-negative integers must fall within, how overflow/underflow is handled, whether `NaN`/`Infinity` are allowed, and when rounding occurs. Do not treat the mere presence of `Number` as sufficient proof that the data is valid.

### 3.2. Strings and Characters

Java `String` is usually easy to pass across the boundary, but an engine may return its own string type. `String.valueOf(result)` only performs a Java `toString()` conversion, **not** a general semantic converter: for `null` it returns the literal string `"null"` rather than representing a missing value; for a complex object it may return a description instead of data.

For public APIs, you should explicitly require `result instanceof String`, or use a designated serializer function (JSON/DTO) instead of calling `toString()` on arbitrary objects.

### 3.3. Boolean, null, missing, and undefined

`null` in Java does not necessarily correspond one-to-one with `null`, `nil`, `None`, or `undefined` in a script. Some languages distinguish between *missing property*, *property with value null*, and *undefined*. At the Java boundary, you must decide whether these states are unified or kept distinct.

Example with bindings:

```java
Bindings bindings = engine.createBindings();
bindings.put("presentButNull", null);
System.out.println(bindings.containsKey("presentButNull")); // true
System.out.println(bindings.containsKey("missing"));        // false
```

This illustrative snippet shows that `Bindings` can distinguish between an existing key with a `null` value and a non-existent key; how the scripting language accesses those two states depends on the engine. Do not use `bindings.get(name) == null` to conclude that a key definitely does not exist.

### 3.4. Collections, Maps, and Objects

A Java `List`/`Map` may be exposed by the engine as a proxy/host object, converted into a script array/object, or only expose a subset of operations. Accessing `map.key` is not necessarily equivalent to `map.get("key")`; whether indexing starts at 0 or 1, iteration order, mutability, and treatment of missing keys all depend on the language.

When transferring data across the engine boundary, a testable approach is to define a DTO with restricted types (string, boolean, number within range, validated list/map, null) or a JSON schema. However, JSON does not automatically preserve `BigDecimal`, date/time, binary data, object identity, or circular references; explicit conventions are needed if those forms are required.

### 3.5. Java Domain Objects

If you place a Java object into bindings, the script engine may allow calling methods or accessing properties according to the engine's reflection or proxy rules. This creates tight coupling to the Java API, overloads, visibility, class loaders, and module accessibility.

For untrusted script sources, never pass objects with powerful system privileges such as `ClassLoader`, `Runtime`, file system handles, credential holders, or administrative services. **A separate class loader is not a security sandbox**.

## 4. Runnable Java 17+ Example Without Third-Party Engines

To focus on rules **determined by the engine**, we write a minimal JSR 223 engine that understands three commands: `echo`, `number`, and `text`. It is not a real-world language; the rules are defined in code so learners can inspect and modify them.

Directory tree:

```text
convert-demo/
└── Demo.java
```

`Demo.java`:

```java
import java.util.Locale;
import javax.script.AbstractScriptEngine;
import javax.script.Bindings;
import javax.script.ScriptContext;
import javax.script.ScriptEngine;
import javax.script.ScriptEngineFactory;
import javax.script.ScriptException;
import javax.script.SimpleBindings;

public final class Demo {
    static final class TinyEngine extends AbstractScriptEngine {
        @Override
        public Object eval(String script, ScriptContext context)
                throws ScriptException {
            String[] parts = script.trim().split("\\s+", 2);
            if (parts.length != 2) {
                throw new ScriptException("Expected command and argument");
            }

            Object value = context.getAttribute(parts[1]);
            if (value == null && context.getAttributesScope(parts[1]) == -1) {
                throw new ScriptException("Unknown name: " + parts[1]);
            }

            return switch (parts[0]) {
                case "echo" -> value;
                case "number" -> toNumber(value);
                case "text" -> value == null ? null : String.valueOf(value);
                default -> throw new ScriptException("Unknown command: " + parts[0]);
            };
        }

        private Number toNumber(Object value) throws ScriptException {
            if (value instanceof Number n) return n;
            if (value instanceof String s) {
                try {
                    return Double.valueOf(s);
                } catch (NumberFormatException ex) {
                    throw new ScriptException("Not numeric: " + s);
                }
            }
            throw new ScriptException("Unsupported conversion");
        }

        @Override
        public Object eval(java.io.Reader reader, ScriptContext context)
                throws ScriptException {
            try {
                StringBuilder b = new StringBuilder();
                char[] buf = new char[512];
                int n;
                while ((n = reader.read(buf)) != -1) b.append(buf, 0, n);
                return eval(b.toString(), context);
            } catch (java.io.IOException ex) {
                throw new ScriptException(ex);
            }
        }

        @Override
        public Bindings createBindings() { return new SimpleBindings(); }

        @Override
        public ScriptEngineFactory getFactory() { return null; }
    }

    public static void main(String[] args) throws Exception {
        ScriptEngine engine = new TinyEngine();
        engine.put("count", Integer.valueOf(42));
        engine.put("decimal", "3.5");
        engine.put("nil", null);

        Object a = engine.eval("echo count");
        Object b = engine.eval("number decimal");
        Object c = engine.eval("text count");
        Object d = engine.eval("echo nil");

        System.out.println(a.getClass().getSimpleName() + ": " + a);
        System.out.println(b.getClass().getSimpleName() + ": " + b);
        System.out.println(c.getClass().getSimpleName() + ": " + c);
        System.out.println("nil is null: " + (d == null));

        try {
            engine.eval("echo missing");
        } catch (ScriptException ex) {
            System.out.println("missing rejected");
        }
    }
}
```

Compile and run with JDK 17+:

```bash
javac -encoding UTF-8 Demo.java
java Demo
```

Exact stdout:

```text
Integer: 42
Double: 3.5
String: 42
nil is null: true
missing rejected
```

**Reading the output:** `echo count` preserves the passed `Integer`; `number decimal` uses the engine's own rule (`Double.valueOf`), so the string `"3.5"` becomes a `Double`; `text count` returns a Java `String`; `echo nil` returns `null`; and the non-existent key `missing` raises an error. This demonstrates that JSR 223 does not enforce the conversion rules above by default: the engine author wrote them explicitly.

**Example limitations:** `getFactory()` returns `null` in the demo engine because it does not use `ScriptEngineManager` and does not publish an SPI provider. An engine intended for real distribution must provide an appropriate `ScriptEngineFactory`. This lesson is only meant to examine `Object`/`Bindings` rules and does not aim to simulate a complete JSR 223 implementation.

## 5. Interacting with a Real Engine: Check Capabilities Before Assuming

In practice, a common pattern is:

```java
ScriptEngine engine = new javax.script.ScriptEngineManager()
        .getEngineByName("some-language");
if (engine == null) {
    throw new IllegalStateException("Script engine is not installed");
}

engine.put("amount", java.math.BigDecimal.valueOf(12.50));
Object result = engine.eval("someExpression");
```

This is an **illustrative snippet** and does not run standalone: the engine name and script expression must be replaced with valid values for an actual provider. Do not assume that `BigDecimal` will become a native numeric primitive. For a plugin host, check `ScriptEngineFactory.getLanguageName()`, version, `getParameter("THREADING")`, and the engine's type conversion documentation.

### 5.1. When to Use Invocable?

Some engines implement `javax.script.Invocable`, allowing the host to call script functions and pass Java arguments through the engine's bridge:

```java
if (engine instanceof javax.script.Invocable invocable) {
    Object result = invocable.invokeFunction("calculate", 10, 20);
}
```

This snippet is not standalone because the `calculate` function must first be defined by the script; `invokeFunction` can throw `NoSuchMethodException` and `ScriptException`. Parameter coercion rules, overloaded method selection, and return value types are still determined by the engine. Do not assume every engine supports `Invocable`.

### 5.2. Converting Data via a Typed Adapter Contract

An adapter layer between the Java domain and the engine prevents type conversion logic from being scattered:

```java
static int requireInt(Object value) {
    if (!(value instanceof Number number)) {
        throw new IllegalArgumentException("Expected Number");
    }
    if (number instanceof java.math.BigInteger bi) return bi.intValueExact();
    if (number instanceof java.math.BigDecimal bd) return bd.intValueExact();
    long l = number.longValue();
    if (l < Integer.MIN_VALUE || l > Integer.MAX_VALUE
            || number.doubleValue() != l) {
        throw new IllegalArgumentException("Not an exact int");
    }
    return (int) l;
}
```

This is an **illustrative utility snippet** for validating the type after receiving a result. For `Double.NaN`, `Infinity`, and extremely large floating-point numbers, checks based on `longValue()` need extra care; critical systems should define detailed rules per numeric class and also check `Double.isFinite(...)`. Do not silently call `intValue()` when exactness is required.

## 6. Key Risks During Type Conversion

| Scenario | Risk | Mitigation |
|---|---|---|
| `Integer` to `Double`/script number | Loss of integer semantics or precision for large numbers | Specify range; use decimal string/`BigDecimal` when needed |
| `BigDecimal` to floating point | Monetary rounding errors | Use a typed adapter; preserve exact decimal representation |
| `null`/`undefined`/missing key | Conflating distinct states | Define a contract distinguishing `containsKey` from a `null` value |
| Java `Map` to script object | Property syntax and mutability depend on the engine | Test the mapping; serialize validated data |
| Date/time | Differing time zone and calendar semantics | Use ISO-8601 with offset/instant and an explicit schema |
| Enum | Engine may use Java object, name, or ordinal | Use enum name and validate against an allowlist |
| Overloaded Java methods | Ambiguous overload resolution | Provide a public API wrapper without complex overloads |
| Different class loaders | Same class name but different runtime identity | Place contract types in a shared loader |
| Script object returned to Java | May be a proxy/value wrapper that is not assignable | Use an engine-specific adapter; check class and lifetime |

### 6.1. Interaction with Class Loaders and ModuleLayer

The engine and host may use different class loaders. If the host passes an instance of `com.example.api.Dto` into a script while the plugin loader has another copy of `Dto` with the same binary name, reflection, proxying, or casting can fail. Use an API JAR defined once in a shared loader, and avoid bundling duplicate contract classes inside the engine JAR.

Named modules are also subject to JPMS readability, `exports`, and `opens` when the engine uses reflection to read Java objects. A public class does not automatically allow the engine to access all private fields. Do not open an entire package just to fix a type conversion error; instead, build a controlled DTO or public façade.

### 6.2. Objects with Mutable State and Lifecycle

Passing a Java `List`, `Map`, or domain object into bindings may give the script a **live reference**. If the script mutates that object, the host may observe the mutation; if the engine copies or converts it, the host may not. Test copy-vs-reference semantics and restrict write permissions.

Script engines are not necessarily thread-safe. Do not share a single engine instance across requests unless the provider guarantees a concurrency model; manage separate bindings per execution, use immutable data, or maintain an instance-per-task depending on the workload.

## 7. Strategy for Designing a Type-Safe Bridge

1. **Define a data schema** between Java and the script (types, nullability, numeric bounds, encoding, nested objects).
2. **Normalize inputs** into verifiable DTOs or primitives/collections; do not pass high-privilege service objects directly.
3. **Select a specific engine and version**, verify its mapping documentation, and record the version in results if behavior changes.
4. **Implement one-way adapters** for `Java→script` and `script→Java`, rather than scattering ad-hoc casts throughout business code.
5. **Handle conversion errors** with meaningful exceptions instead of silently rounding, truncating numbers, or stringifying unexpected values.
6. **Test boundaries** including very large numbers, decimals, `NaN`, `Infinity`, Unicode, null/missing, nested collections, and cyclic objects.
7. **Restrict untrusted scripts** by not exposing sensitive host objects; use process/OS-level isolation when needed.

## 8. Per-Engine Testing Checklist

- [ ] The engine is discovered via the right `ScriptEngineManager`/class loader and its version is recorded.
- [ ] Round-trip tests exist for `String`, `Boolean`, `Integer`, `Long`, `Double`, and `BigDecimal` if supported by the contract.
- [ ] `null`, missing keys, invalid values, and cast errors are thoroughly tested.
- [ ] `List`/`Map` behavior is verified as copy vs. reference, with clear mutability guarantees.
- [ ] The host never assumes a returned `Object` is always a specific Java class.
- [ ] Module exports/opens and class identity are verified when the engine calls Java APIs.
- [ ] There are no unexpected shared mutable bindings across script executions.
- [ ] Scripts have no access to unnecessary host objects.

**Conclusion:** The Java Scripting API provides a mechanism for exchanging Java objects with an engine rather than defining a universal coercion table for all languages. Every Java↔script conversion must be treated as a **contract specific to the engine and engine version**. Normalize data at the boundary, verify actual runtime types on return, handle null and precision explicitly, and test with the real engine before releasing a plugin.

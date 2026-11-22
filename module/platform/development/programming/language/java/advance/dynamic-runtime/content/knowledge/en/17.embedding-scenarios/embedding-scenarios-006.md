# 17.6 Checking `Invocable` Capability, Invoking Functions, and Mapping to Interfaces

## 1. The problem: from an executed script to a typed Java call

When embedding a scripting language into Java, `javax.script.ScriptEngine` is often used to **evaluate a script snippet** via `eval(...)`. However, real-world applications do not just want to run an entire script and receive a generic result. They often need to:

- **Call back a function** already defined by the script, by name and argument list.
- **Invoke a method of a script object** that was created earlier.
- **Map** those functions/methods to a **Java interface**, so application code calls `calculator.add(2, 5)` instead of repeating `invokeFunction("add", 2, 5)`.
- **Detect the engine's actual capability**; not every `ScriptEngine` implements the `Invocable` interface.
- **Report errors of the right class** when the engine does not exist, does not support function invocation, the function does not exist, the script throws an error, or the result is incompatible with Java types.

The main API of this lesson is **`javax.script.Invocable`** (JSR 223, module `java.scripting`). This is an **optional interface** that some `ScriptEngine` implementations implement to allow invoking functions/methods **already executed/defined beforehand** in the engine's environment.

> **Core rule:** Having a `ScriptEngine` does not mean having `Invocable`. You must check `engine instanceof Invocable`; if true, **evaluate/load the script first**, and only then call `invokeFunction`/`invokeMethod` or obtain an adapter via `getInterface`. Java 17+ **no longer includes the built-in Nashorn JavaScript engine**, so you must not assume `getEngineByName("JavaScript")` will return a non-`null` engine.

The lesson provides a **completely self-contained Java 17+ example that can be compiled/run on a standard JDK**. To avoid depending on an external JavaScript installation, the example uses a **small custom engine written as a teaching fixture** that implements `Invocable` and uses a JDK Proxy to demonstrate interface mapping. This fixture is **not** a JavaScript interpreter and does **not** register itself with `ScriptEngineManager`. A separate example for real JavaScript scripts is explicitly noted as **conditional** on having a compatible JSR 223 provider available.

## 2. JSR 223 architecture and the role of `Invocable`

The core types reside in the `javax.script` package:

| API | Responsibility | Things to note |
| --- | --- | --- |
| `ScriptEngineManager` | Finds available `ScriptEngineFactory` instances, creates engines by name/extension/MIME | Does not install engines itself; returns `null` if no matching provider exists |
| `ScriptEngineFactory` | Describes name, version, language, and how to create an engine | An engine may have multiple aliases; check the specific provider |
| `ScriptEngine` | `eval` code, manages `Bindings` and `ScriptContext` | Not required to support calling functions by name |
| `AbstractScriptEngine` | Utility base class for engine authors | Does **not** automatically implement `Invocable` |
| `Invocable` | `invokeFunction`, `invokeMethod`, two `getInterface` overloads | Optional; if an engine does not implement it, do not cast |
| `Compilable` | Optional compilation of scripts into `CompiledScript` | **Independent** of `Invocable`; `Compilable` does not replace `Invocable` |
| `Bindings` | Named variable map between Java and the engine | Do not assume every binding is a script function |
| `ScriptException` | Script evaluation/invocation error | Distinguish from `NoSuchMethodException` from function lookup |

**Typical workflow:**

```text
ScriptEngineManager / registered provider
              |
              v
      ScriptEngine engine
              |
       engine != null ?
          /        \
        no          yes
        |            |
   report missing   engine.eval(source)
     engine               |
                          v
               engine instanceof Invocable ?
                       /          \
                     no            yes
                     |              |
             use eval or            v
            another engine    Invocable inv
                                 |
                 +---------------+---------------+
                 |               |               |
           invokeFunction    invokeMethod      getInterface
           global function    obj method      Java typed view
```

**Distinguishing the two capabilities:** `ScriptEngine.eval("add(2, 5)")` can run even if the engine **does not implement `Invocable`**, because that is script language syntax inside a string. `Invocable.invokeFunction("add", 2, 5)` is a Java API for calling a **prepared function** without reconstructing an expression string. You cannot rely on `eval` being available to cast the engine to `Invocable`.

### 2.1. `Invocable` is not `java.lang.reflect.Method`

The names are similar, but the mechanisms are different:

- `Method.invoke(receiver, args...)` invokes a **Java method** declared in class bytecode.
- `Invocable.invokeFunction(name, args...)` invokes a **global script function** by name within the engine's state.
- `Invocable.invokeMethod(thiz, name, args...)` invokes a **method belonging to a script object** known to the engine.
- `Invocable.getInterface(...)` builds an adapter so Java calls methods of a **declared interface** and forwards them to the script.

`Invocable` **does not compile Java source**, does not add new methods to a Java class, and does not gain access to private Java members merely by implementing this interface.

## 3. Checking that the engine exists and supports `Invocable`

### 3.1. Always check the engine before casting

A control-flow-safe snippet:

```java
import javax.script.Invocable;
import javax.script.ScriptEngine;
import javax.script.ScriptEngineManager;

ScriptEngineManager manager = new ScriptEngineManager();
ScriptEngine engine = manager.getEngineByName("JavaScript");

if (engine == null) {
    System.out.println("No JSR 223 JavaScript engine available.");
} else if (!(engine instanceof Invocable inv)) {
    System.out.println("Engine exists but does not support Invocable.");
} else {
    System.out.println("Invocable can be used with this engine.");
    // Continue to eval the script and invoke defined functions.
}
```

This is a **Java snippet**, not a complete program: the statements must be placed inside a method/class. Its purpose is to illustrate the guard, not to guarantee identical output across every JDK.

Java 17 still provides the `javax.script` API, but **Nashorn was removed from the JDK in Java 15** (JEP 372). A clean JDK 17 installation may contain no engine with the alias `"JavaScript"`, so `getEngineByName` may return `null`. If an application needs JavaScript, add a compatible JSR 223 engine/provider and configure dependencies and class loader/module path according to the provider's documentation.

**Do not use:**

```java
// WRONG if the engine does not exist or does not support Invocable.
Invocable inv = (Invocable) new ScriptEngineManager()
        .getEngineByName("JavaScript");
Object result = inv.invokeFunction("add", 2, 5);
```

When `getEngineByName` returns `null`, casting `null` to `Invocable` still yields `null`, and then calling `inv.invokeFunction` throws a `NullPointerException`. If the engine exists but does not implement `Invocable`, the cast fails with a `ClassCastException`. Both are avoided by separate checks like the pattern above.

### 3.2. Pattern matching keeps the variable properly typed

With Java 17:

```java
if (!(engine instanceof Invocable inv)) {
    throw new IllegalStateException("Engine does not support invoking script functions");
}
Object value = inv.invokeFunction("add", 2, 5);
```

This pattern is a **snippet** assuming `engine` has already been checked for non-null and the script has an `add` function. Using the `instanceof` guard does **not** mean `add` definitely exists: it only confirms **the engine's capability**.

### 3.3. Installed providers can be inspected

To investigate engine availability:

```java
ScriptEngineManager manager = new ScriptEngineManager();
for (javax.script.ScriptEngineFactory factory : manager.getEngineFactories()) {
    System.out.println(factory.getEngineName() + ": " + factory.getNames());
}
```

This is also a **snippet**. Output depends on the `ScriptEngineFactory` implementations discovered in the environment; there is no fixed list for "Java 17". If the desired engine is not found, inspect the provider JAR/module, service registration, class loader, and dependencies rather than guessing engine names.

## 4. `invokeFunction`: invoking a defined global function

Signature:

```java
Object invokeFunction(String name, Object... args)
        throws ScriptException, NoSuchMethodException;
```

A program typically performs:

1. Obtain an available `ScriptEngine` and confirm `Invocable`.
2. Use `engine.eval(...)` to load the script defining the function.
3. Call `inv.invokeFunction("functionName", arg1, arg2, ...)`.
4. Check/convert the returned `Object`, and handle exceptions appropriately.

Conceptual example with an engine that executes JavaScript:

```java
// Snippet; runs only when the engine has a compatible JavaScript provider.
engine.eval("function add(a, b) { return a + b; }");
Invocable inv = (Invocable) engine;  // Only after instanceof has confirmed.
Object result = inv.invokeFunction("add", 2, 5);
```

`result` is `Object` because the Java API **does not know the script function's return type in advance**. A provider may map a numeric result to `Integer`, `Double`, another `Number` type, or a provider-specific wrapper. Do not cast blindly:

```java
// Fragile if the provider returns Double instead of Integer.
Integer exact = (Integer) inv.invokeFunction("add", 2, 5);
```

If the business contract allows taking a number, you can check:

```java
Object raw = inv.invokeFunction("add", 2, 5);
if (!(raw instanceof Number number)) {
    throw new IllegalStateException("add did not return a numeric type.");
}
int result = number.intValue();
```

This is a **snippet**, not a guarantee that every scripting language uses `Number` for all numeric operations. `intValue()` can lose fractional parts or overflow; in a real program, validate the type, value range, and potential precision loss.

### 4.1. A missing function differs from a function that throws an error

- `NoSuchMethodException`: no function found matching the name or compatible argument types.
- `ScriptException`: the engine reports an error during script invocation/execution.
- `NullPointerException`: the passed function name is `null`, per the API contract.
- Other runtime exceptions: may be raised by the implementation, conversion, or Java code interacting with the script.

Do not catch generic `Exception` and return `null` for all cases: a valid script result can be `null`, and hiding the error type prevents callers from knowing whether they need to install a provider, add a function, or fix the script.

### 4.2. A global function is not the same as an object method

`invokeFunction("add", 2, 5)` looks up the function in what the engine considers the **top-level/global** scope. If the script only defines `math.add` as a **method on an object**, `invokeFunction("add", ...)` will not necessarily find it. In that case, use `invokeMethod(scriptObject, "add", ...)` or a global wrapper function exposed by the script.

## 5. `invokeMethod`: invoking a method on a script object

Signature:

```java
Object invokeMethod(Object thiz, String name, Object... args)
        throws ScriptException, NoSuchMethodException;
```

In JSR 223, `thiz` is a **scripting language object** created/returned by a previous evaluation or call, as represented on the Java side by the engine. Conceptual example:

```javascript
// Script evaluated by a compatible JSR 223 JavaScript engine.
var counter = {
    count: 0,
    increment: function (delta) {
        this.count += delta;
        return this.count;
    },
    value: function () {
        return this.count;
    }
};
```

After `engine.eval(...)` runs, the provider's adapter may allow Java to retrieve the object from bindings:

```java
// Snippet: the engine has the "counter" object after eval.
Object scriptCounter = engine.get("counter");
Invocable inv = (Invocable) engine;
Object next = inv.invokeMethod(scriptCounter, "increment", 5);
Object current = inv.invokeMethod(scriptCounter, "value");
```

This is a **provider-dependent snippet**, not a standalone example with standard output. JavaScript naming, object representation, and number conversion must be verified against the actual engine.

### 5.1. `thiz` is not an arbitrary Java receiver

`Invocable.invokeMethod` is **not** defined as "invoke Reflection on any Java Object". According to the Java SE 17 API:

- If `thiz == null`, `IllegalArgumentException` may be thrown.
- If `thiz` does not represent a valid **scripting object** recognized by the engine, `IllegalArgumentException`.
- If the method is missing or no matching argument signature exists, `NoSuchMethodException`.
- If the script method throws an error, `ScriptException`.

Do not pass `SomeJavaClass.class` into `invokeMethod` expecting it to look up a Java static method. This is a **scripting engine** API, not `Method.invoke`.

In this lesson's fixture example, `CounterHost` is an **object designated by the fixture to play the role of a script object**. It illustrates the `thiz` contract and method dispatch; it does **not** mean every real JSR 223 engine must accept any Java `CounterHost`.

### 5.2. Differences between `invokeFunction` and `invokeMethod`

| Intent | API | Main parameters |
| --- | --- | --- |
| Call global function `add(a,b)` | `invokeFunction("add",a,b)` | `name` and `args` |
| Call method `counter.increment(d)` | `invokeMethod(counter,"increment",d)` | `thiz` + `name` + `args` |
| Call Java method `javaObject.apply(x)` via Reflection | `method.invoke(javaObject,x)` | `Method` + Java receiver |
| Run a script source block directly | `engine.eval(scriptText)` | Source + context |
| Use a Java interface for global functions | `getInterface(MyApi.class)` | Java interface `Class<T>` |
| Use a Java interface for a script object | `getInterface(counter,CounterApi.class)` | Script object + Java interface |

This classification helps avoid switching from `invokeFunction` to `invokeMethod` just because both methods contain the word "invoke".

## 6. `getInterface`: mapping scripts to a Java interface

`Invocable` provides **two overloads**:

```java
<T> T getInterface(Class<T> clasz);

<T> T getInterface(Object thiz, Class<T> clasz);
```

In the Java API, the result has type `T`, which is an implementation of the interface that the Java caller can use. The engine decides how to connect method names/signatures to script functions or script object members.

### 6.1. Global functions as a Java interface

Suppose Java has:

```java
public interface MathOps {
    int add(int a, int b);
    int twice(int x);
}
```

And the global script has defined two corresponding functions:

```javascript
function add(a, b) { return a + b; }
function twice(x) { return x * 2; }
```

After `eval` and verifying the engine implements `Invocable`:

```java
MathOps api = inv.getInterface(MathOps.class);
if (api == null) {
    throw new IllegalStateException("Missing functions corresponding to MathOps.");
}
int sum = api.add(3, 4);
```

**Advantages:** Java code calls `api.add(3,4)` with clear Java signatures; there is no need to repeat the string name `"add"` and cast `Object` at every call site.

**Disadvantages and limitations:** the interface must match the script functions that the engine can locate and map. Argument/return conversion, overload support, default methods, generics, checked exceptions, and adapter overhead **depend on the engine**. `getInterface` can return **`null`** when the corresponding functions are unavailable. It does not automatically turn any script into an implementation of an arbitrary interface.

### 6.2. Script object methods as a Java interface

Suppose the script creates a `counter` object with methods `increment(delta)` and `value()`. Java defines:

```java
public interface CounterOps {
    int increment(int delta);
    int value();
}
```

Java uses:

```java
CounterOps api = inv.getInterface(scriptCounter, CounterOps.class);
if (api == null) {
    throw new IllegalStateException("Could not map CounterOps.");
}
int next = api.increment(3);
```

Here the Java methods are mapped **onto the script object `scriptCounter`**, not onto the engine's global functions. Do not omit the `scriptCounter` argument and expect the engine to guess a "current object".

### 6.3. When does it return `null`, and when does it throw an exception?

| Situation | Standard behavior to expect |
| --- | --- |
| Valid interface, all matching functions/methods present | May return an implementation of type `T` |
| Valid interface, but one or more required functions/methods are missing | `getInterface(...)` may return **`null`** |
| `clasz == null` or `clasz` is not an interface | `IllegalArgumentException` |
| For `getInterface(thiz,clasz)`, `thiz==null` or not a valid scripting object | `IllegalArgumentException` |
| After the adapter is created, script changes / error at call time | Depends on engine and interface contract; may throw an exception on call |

Importantly, **`null` from `getInterface` is not equivalent to `NoSuchMethodException` from `invokeFunction`**. One means **an adapter could not be created for the interface**, while the other means **a function could not be invoked by name**.

### 6.4. Is `getInterface` always `java.lang.reflect.Proxy`?

You should not assert that for **every scripting engine**. The API specifies behavior and return types; **it does not require all providers to use the same implementation technique**. A provider may use a JDK Proxy, another adapter mechanism, a custom wrapper, or implementation-specific conversion.

The **custom `MiniEngine`** example in Section 7 **intentionally** uses `Proxy.newProxyInstance` to implement `getInterface` for teaching purposes. That is **the fixture's design choice**, not a mandatory contract of `Invocable`.

## 7. Self-contained Java 17+ example without an external JavaScript engine

### 7.1. Why use a fixture?

Many older tutorials write:

```java
ScriptEngine engine =
        new ScriptEngineManager().getEngineByName("JavaScript");
Invocable inv = (Invocable) engine;
```

and assume a built-in JavaScript script engine is always present in the JDK. This approach is **unreliable on Java 17** because Nashorn was removed from the JDK in Java 15. If a lesson uses JavaScript directly without installing a provider, the example can fail before even testing `Invocable`.

To isolate the concept properly, the following program includes:

- `PlainEngine` extending `AbstractScriptEngine`, **not** implementing `Invocable`.
- `MiniEngine` extending `PlainEngine` and **implementing `Invocable`**; `eval("install")` marks the functions as "loaded".
- `invokeFunction` supports `add`, `twice`, and an `explode` function that intentionally throws `ScriptException`.
- `invokeMethod` supports `increment` and `value` on a `CounterHost` acting as a script object.
- `getInterface(Class<T>)` creates an adapter for `MathOps`.
- `getInterface(Object,Class<T>)` creates an adapter for `CounterOps` with a specific receiver.
- `MissingOps` illustrates an interface **without matching functions**, returning `null`.
- Cases for wrong method name, script error, invalid receiver, and non-interface type are tested.

**Transparent limitations:** `PlainEngine.getFactory()` returns `null` because the example does not register a provider with `ScriptEngineManager`; `MiniEngine` only recognizes the exact keyword `"install"` and **does not parse JavaScript**. The goal is to test the `Invocable` contract with code that has no external engine dependencies.

### 7.2. Complete code: `InvocableApiDemo.java`

Create a file **`InvocableApiDemo.java`** containing:

```java
import java.io.IOException;
import java.io.Reader;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;
import java.util.Objects;
import javax.script.AbstractScriptEngine;
import javax.script.Bindings;
import javax.script.Invocable;
import javax.script.ScriptContext;
import javax.script.ScriptEngine;
import javax.script.ScriptEngineFactory;
import javax.script.ScriptException;
import javax.script.SimpleBindings;

public class InvocableApiDemo {
    public interface MathOps {
        int add(int a, int b);
        int twice(int x);
    }

    public interface CounterOps {
        int increment(int delta);
        int value();
    }

    public interface MissingOps {
        int unavailable();
    }

    static final class CounterHost {
        private int number;

        int increment(int delta) {
            number += delta;
            return number;
        }

        int value() {
            return number;
        }
    }

    // Minimal fixture: NOT a JavaScript interpreter / registered provider.
    static class PlainEngine extends AbstractScriptEngine {
        @Override
        public Object eval(String script, ScriptContext context)
                throws ScriptException {
            return script;
        }

        @Override
        public Object eval(Reader reader, ScriptContext context)
                throws ScriptException {
            StringBuilder result = new StringBuilder();
            char[] buffer = new char[256];
            try {
                int size;
                while ((size = reader.read(buffer)) != -1) {
                    result.append(buffer, 0, size);
                }
            } catch (IOException ex) {
                throw new ScriptException(ex);
            }
            return eval(result.toString(), context);
        }

        @Override
        public Bindings createBindings() {
            return new SimpleBindings();
        }

        @Override
        public ScriptEngineFactory getFactory() {
            return null; // Fixture has no factory for ScriptEngineManager discovery.
        }
    }

    static final class MiniEngine extends PlainEngine implements Invocable {
        private boolean installed;

        @Override
        public Object eval(String script, ScriptContext context)
                throws ScriptException {
            if (!"install".equals(script.trim())) {
                throw new ScriptException("Unsupported fixture script");
            }
            installed = true;
            return "ready";
        }

        private static boolean globalExists(String name) {
            return "add".equals(name) || "twice".equals(name)
                    || "explode".equals(name);
        }

        private static boolean memberExists(String name) {
            return "increment".equals(name) || "value".equals(name);
        }

        @Override
        public Object invokeFunction(String name, Object... args)
                throws ScriptException, NoSuchMethodException {
            Objects.requireNonNull(name, "name");
            if (!installed || !globalExists(name)) {
                throw new NoSuchMethodException(name);
            }
            Object[] actual = args == null ? new Object[0] : args;
            switch (name) {
                case "add":
                    if (actual.length != 2
                            || !(actual[0] instanceof Integer)
                            || !(actual[1] instanceof Integer)) {
                        throw new ScriptException("add needs two integers");
                    }
                    return (int) actual[0] + (int) actual[1];
                case "twice":
                    if (actual.length != 1
                            || !(actual[0] instanceof Integer)) {
                        throw new ScriptException("twice needs one integer");
                    }
                    return (int) actual[0] * 2;
                case "explode":
                    throw new ScriptException("simulated script error");
                default:
                    throw new NoSuchMethodException(name);
            }
        }

        @Override
        public Object invokeMethod(Object thiz, String name, Object... args)
                throws ScriptException, NoSuchMethodException {
            Objects.requireNonNull(name, "name");
            if (!(thiz instanceof CounterHost host)) {
                throw new IllegalArgumentException("not a fixture script object");
            }
            if (!installed || !memberExists(name)) {
                throw new NoSuchMethodException(name);
            }
            Object[] actual = args == null ? new Object[0] : args;
            switch (name) {
                case "increment":
                    if (actual.length != 1
                            || !(actual[0] instanceof Integer)) {
                        throw new ScriptException("increment needs an integer");
                    }
                    return host.increment((int) actual[0]);
                case "value":
                    if (actual.length != 0) {
                        throw new ScriptException("value takes no arguments");
                    }
                    return host.value();
                default:
                    throw new NoSuchMethodException(name);
            }
        }

        @Override
        public <T> T getInterface(Class<T> iface) {
            return adapt(null, iface);
        }

        @Override
        public <T> T getInterface(Object thiz, Class<T> iface) {
            if (!(thiz instanceof CounterHost)) {
                throw new IllegalArgumentException("not a fixture script object");
            }
            return adapt(thiz, iface);
        }

        private <T> T adapt(Object thiz, Class<T> iface) {
            if (iface == null || !iface.isInterface()) {
                throw new IllegalArgumentException("expected an interface");
            }
            if (!installed) {
                return null;
            }
            for (Method method : iface.getMethods()) {
                if (method.getDeclaringClass() == Object.class) continue;
                if (thiz == null ? !globalExists(method.getName())
                        : !memberExists(method.getName())) {
                    return null;
                }
            }

            Object proxy = Proxy.newProxyInstance(
                    iface.getClassLoader(), new Class<?>[]{iface},
                    (receiver, method, args) -> {
                        if (method.getDeclaringClass() == Object.class) {
                            return switch (method.getName()) {
                                case "toString" -> "InvocableFixtureProxy";
                                case "hashCode" ->
                                        System.identityHashCode(receiver);
                                case "equals" -> receiver == args[0];
                                default -> throw new UnsupportedOperationException();
                            };
                        }

                        Object[] values =
                                args == null ? new Object[0] : args;
                        return thiz == null
                                ? invokeFunction(method.getName(), values)
                                : invokeMethod(thiz, method.getName(), values);
                    });
            return iface.cast(proxy);
        }
    }

    public static void main(String[] args) throws Exception {
        ScriptEngine plain = new PlainEngine();
        ScriptEngine engine = new MiniEngine();
        System.out.println("plain Invocable=" + (plain instanceof Invocable));
        System.out.println("mini Invocable=" + (engine instanceof Invocable));

        if (!(engine instanceof Invocable inv)) {
            throw new IllegalStateException("Engine does not implement Invocable");
        }

        System.out.println("interface before eval="
                + (inv.getInterface(MathOps.class) == null));

        System.out.println("eval=" + engine.eval("install"));
        System.out.println("invoke add=" + inv.invokeFunction("add", 2, 5));
        System.out.println("invoke twice=" + inv.invokeFunction("twice", 6));

        try {
            inv.invokeFunction("missing");
        } catch (NoSuchMethodException ex) {
            System.out.println("missing=" + ex.getClass().getSimpleName());
        }

        try {
            inv.invokeFunction("explode");
        } catch (ScriptException ex) {
            System.out.println("script failure=" + ex.getClass().getSimpleName());
        }

        MathOps math = inv.getInterface(MathOps.class);
        System.out.println("global mapping=" + (math != null));
        System.out.println("interface add=" + math.add(3, 4));
        System.out.println("interface twice=" + math.twice(8));
        System.out.println("missing interface="
                + (inv.getInterface(MissingOps.class) == null));

        CounterHost host = new CounterHost();
        System.out.println("method increment="
                + inv.invokeMethod(host, "increment", 5));
        System.out.println("method value="
                + inv.invokeMethod(host, "value"));

        CounterOps counter = inv.getInterface(host, CounterOps.class);
        System.out.println("object mapping=" + (counter != null));
        System.out.println("interface increment=" + counter.increment(3));
        System.out.println("interface value=" + counter.value());

        try {
            inv.invokeMethod(null, "value");
        } catch (IllegalArgumentException ex) {
            System.out.println("invalid receiver="
                    + ex.getClass().getSimpleName());
        }

        try {
            inv.getInterface(String.class);
        } catch (IllegalArgumentException ex) {
            System.out.println("not interface="
                    + ex.getClass().getSimpleName());
        }
    }
}
```

### 7.3. Compile and run

Use **JDK 17 or later** in the directory containing the file:

```bash
javac --release 17 InvocableApiDemo.java
java InvocableApiDemo
```

**Exact verified stdout when run on a JDK with Java 17 APIs:**

```text
plain Invocable=false
mini Invocable=true
interface before eval=true
eval=ready
invoke add=7
invoke twice=12
missing=NoSuchMethodException
script failure=ScriptException
global mapping=true
interface add=7
interface twice=16
missing interface=true
method increment=5
method value=5
object mapping=true
interface increment=8
interface value=8
invalid receiver=IllegalArgumentException
not interface=IllegalArgumentException
```

Both `javac --release 17` and `java` ran with **exit code 0** during verification. The program **does not depend on Nashorn, GraalJS, or any external library**, because `MiniEngine` itself provides the simulated `Invocable` API.

### 7.4. Reading the engine-capability output group

```text
plain Invocable=false
mini Invocable=true
interface before eval=true
eval=ready
```

- `PlainEngine` only has `ScriptEngine`, not `Invocable`. The `instanceof` check returns `false`, so it must not be cast to `Invocable`.
- `MiniEngine` implements `Invocable`, returning `true`; the code keeps `inv` with the exact type.
- Before `eval("install")`, the fixture functions are not ready yet, so `getInterface(MathOps.class)` returns `null`; hence `interface before eval=true`.
- After `eval`, the fixture sets the `installed` flag and returns the string `ready`.

This illustrates that "**engine capability**" differs from "**functions ready in the engine**". `instanceof Invocable` indicates the API is supported; it does not guarantee a script has been evaluated or any function exists.

### 7.5. Reading the function-call and error output group

```text
invoke add=7
invoke twice=12
missing=NoSuchMethodException
script failure=ScriptException
```

`invokeFunction("add",2,5)` finds the "installed" global function `add` and returns `7`. `twice(6)` returns `12`. `invokeFunction("missing")` cannot find the function, so it throws `NoSuchMethodException`. `invokeFunction("explode")` finds the function but intentionally throws `ScriptException`.

**Clear distinction:** "function not found" and "function ran and failed" are not the same exception. In a real engine, `ScriptException` may also contain file name/line/column or a provider-specific cause.

### 7.6. Reading the global interface mapping output group

```text
global mapping=true
interface add=7
interface twice=16
missing interface=true
```

`getInterface(MathOps.class)` succeeds because the fixture sees both `add` and `twice`. Java can call `math.add(3,4)` and `math.twice(8)` via `int`-typed interface methods. `MissingOps` requires `unavailable()`, which the fixture does not have, so `getInterface(MissingOps.class)` returns `null`; the `==null` comparison prints `true`.

In the fixture, the JDK Proxy forwards each interface method to `invokeFunction`, but that is an **implementation decision of `MiniEngine`**. With a real engine, adapter creation timing, overload/argument mapping, and conversions may differ.

### 7.7. Reading the script-object mapping output group

```text
method increment=5
method value=5
object mapping=true
interface increment=8
interface value=8
```

Before obtaining the adapter, Java calls `invokeMethod(host,"increment",5)`, increasing `CounterHost.number` from `0` to `5`; `invokeMethod(host,"value")` returns `5`. `getInterface(host,CounterOps.class)` creates a view bound to **that exact host**; calling `counter.increment(3)` increases it from `5` to `8`, and `counter.value()` returns `8`.

This clearly shows how an **object-bound adapter** differs from a **global adapter**: the target object is a key input. However, `CounterHost` here is only a script object model that the **fixture** explicitly recognizes; in a real JavaScript engine, you must use an object created/returned by the engine.

### 7.8. Reading the invalid-arguments output group

```text
invalid receiver=IllegalArgumentException
not interface=IllegalArgumentException
```

- `invokeMethod(null,"value")` has no valid script object receiver, so the fixture throws `IllegalArgumentException` per the contract's intent.
- `getInterface(String.class)` passes `String`, which is a **class**, not an interface, so it throws `IllegalArgumentException`.

In real code, you also need guards for `engine==null`, `name==null`, and missing functions. These cases must not be conflated with "no adapter available for the interface".

## 8. Conditional example with a real JavaScript engine

This section shows how to use `Invocable` with a provider capable of evaluating JavaScript. **It is not guaranteed to run on a default JDK 17 alone**. Before running, you must install, configure, and verify a **compatible JSR 223 JavaScript engine provider** (for example, a third-party engine providing `ScriptEngineFactory`/`Invocable`).

### 8.1. Preparing the JavaScript

The following script defines global functions and an object:

```javascript
function add(a, b) {
    return a + b;
}

function twice(x) {
    return x * 2;
}

var counter = {
    count: 0,
    increment: function (delta) {
        this.count += delta;
        return this.count;
    },
    value: function () {
        return this.count;
    }
};
```

This is **JavaScript source**, not Java code. It only executes when the installed engine supports the syntax and exposes global functions/objects as shown.

### 8.2. Java code checking the engine before use

```java
import javax.script.Invocable;
import javax.script.ScriptEngine;
import javax.script.ScriptEngineManager;

// Snippet: place inside a method declaring throws Exception.
ScriptEngine engine =
        new ScriptEngineManager().getEngineByName("JavaScript");

if (engine == null) {
    throw new IllegalStateException(
            "No suitable JSR 223 JavaScript provider installed");
}
if (!(engine instanceof Invocable inv)) {
    throw new IllegalStateException(
            "Provider does not support Invocable");
}

engine.eval("""
        function add(a,b) { return a+b; }
        var counter = {
            count: 0,
            increment: function(d) {
                this.count += d;
                return this.count;
            },
            value: function() { return this.count; }
        };
        """);

Object rawSum = inv.invokeFunction("add", 2, 5);
Object scriptCounter = engine.get("counter");
Object rawNext = inv.invokeMethod(
        scriptCounter, "increment", 3);
```

**There is no standard stdout** for this snippet: `rawSum`/`rawNext` may be mapped by the provider to different Java wrapper types, and how `counter` is exposed may vary. This is a **conditional integration pattern**, not a standalone test like `InvocableApiDemo.java`.

After verifying that the engine supports interface mapping:

```java
// Snippet: MathOps/CounterOps are declared Java interfaces.
// Variables inv/scriptCounter come from the snippet above.
MathOps global = inv.getInterface(MathOps.class);
CounterOps bound = inv.getInterface(scriptCounter, CounterOps.class);

if (global == null || bound == null) {
    throw new IllegalStateException(
            "Provider could not map the script functions.");
}

int sum = global.add(2, 5);
int now = bound.increment(3);
```

In particular, check **numeric conversions**. An engine might return `Double` when calling `invokeFunction` yet convert to Java `int` when called through an adapter per the provider's contract. Do not rely on this without verifying it with tests on the actual engine.

### 8.3. What if there is no JavaScript engine?

JSR 223 **is an API**, not a guarantee that every language is pre-installed. Java 17 does not include Nashorn. You can:

- Use another scripting engine that has a suitable `ScriptEngineFactory` and `Invocable`.
- Add a JSR 223-compatible JavaScript dependency/provider according to its documentation.
- If the provider does not implement `Invocable`, consider engine-specific invocation APIs, wrapper functions in `eval`, or choosing another engine.
- If you only need a few configuration rules, use Java functions/strategies or a safe DSL without necessarily embedding an engine.

You should not bring an overly outdated script library into production just to reproduce a Java 8 example without evaluating compatibility, maintenance, security, and module requirements.

## 9. Handling argument types and return values

### 9.1. Java `Object... args` does not dictate every engine's conversion

Both methods use `Object...`:

```java
inv.invokeFunction("add", 2, 5);
inv.invokeMethod(scriptObject, "increment", 3);
```

At the Java call site, primitive `int` is typically boxed into `Integer` before being passed in `Object[]`. **After that**, the engine decides the mapping from Java object to script type according to the provider's documentation. Avoid assuming that `Integer` in Java definitely arrives in the script as an "exact 32-bit integer" across all engines.

For script numbers, dates, arrays, maps, callbacks, or objects, mappings can be provider-specific. Always clarify the data protocol between Java and the script, especially when the application requires monetary precision or a stable schema.

### 9.2. `null` and zero-argument calls

With a Java call:

```java
Object result = inv.invokeFunction("noArg");
```

Java passes an empty varargs array when called normally. If the caller explicitly passes `(Object[]) null`, the implementation may receive a `null` `args` value; do not do this unless the API/provider defines the desired handling.

`MiniEngine` in the example uses:

```java
Object[] actual = args == null ? new Object[0] : args;
```

to ensure the fixture code does not suffer a `NullPointerException`. That is the fixture's choice; it does not mean every `Invocable` provider must handle `null args` the same way.

Additionally, `invokeFunction("f", (Object) null)` passes **a single Java `null` argument**, which differs from passing `null` for **the entire varargs array** via `(Object[])null`. When integrating, test all three cases if needed.

### 9.3. Script results can be `null`

`invokeFunction` and `invokeMethod` return `Object`; a script function may return `null` or its language equivalent. Do not confuse:

- `getInterface(...) == null`: failed to create a Java interface adapter.
- `invokeFunction(...) == null`: the function was invoked and **the return value** is `null` (per provider semantics).
- `engine == null`: no engine was found.
- `ScriptException`: an error occurred during eval/invocation.

All four symptoms must be diagnosed separately to prevent production code from treating every `null` as the same error.

### 9.4. Primitive returns on interfaces

When an interface declares:

```java
public interface MathOps {
    int add(int a, int b);
}
```

the adapter must return a value compatible with Java `int`. If the engine/proxy returns `null` or the wrong wrapper, the call may throw `NullPointerException` or `ClassCastException` during unboxing/casting. With a real provider, conversion rules may support multiple numeric types; test the actual behavior rather than assuming.

### 9.5. Checked exceptions at the adapter layer

`Invocable.invokeFunction` and `invokeMethod` declare the checked exceptions `ScriptException` and `NoSuchMethodException`. However, a Java interface mapped via `getInterface` might **not declare those two exceptions**:

```java
public interface MathOps {
    int add(int a, int b);
}
```

When the script encounters an error beneath the adapter, exception wrapping/translation depends on the provider/proxy implementation and the interface's signature. If the adapter uses a JDK Proxy and the handler throws a checked exception not declared by the interface, the caller may encounter `UndeclaredThrowableException`. Do not write an error handler that only catches `ScriptException` around `math.add(...)` when the interface does not declare it, and assume you have caught every error.

Design options to consider: have the interface declare appropriate exceptions, configure an adapter policy to translate errors into an unchecked domain exception, or use `invokeFunction` directly to preserve `Invocable`'s checked exceptions when detailed diagnostics are needed.

## 10. Structured error handling

| Case | Error/value to recognize | How to handle |
| --- | --- | --- |
| `getEngineByName("JavaScript")` has no provider | `engine == null` | Install/register a provider or disable the feature with a clear message |
| Engine does not implement `Invocable` | `instanceof Invocable == false` | Do not cast; use the provider's API or a suitable engine |
| Script has not been `eval`/loaded yet | No matching function/method | Load the script before calling; check context/bindings |
| Null function/method name passed | `NullPointerException` per API | Validate the name before calling |
| Function name or signature not found | `NoSuchMethodException` | Check namespace, spelling, argument count/types |
| Script method/function throws an error | `ScriptException` on direct call | Read message, cause, and script metadata |
| `invokeMethod` with `thiz==null`/non-script object | `IllegalArgumentException` | Keep the valid object from the engine |
| `getInterface` with a non-interface class | `IllegalArgumentException` | Only pass an interface `Class<T>` |
| Unable to map the interface's methods | `getInterface(...) == null` | Compare method names/signatures and provider support |
| Adapter returns `null` for a Java primitive | Possible `NullPointerException` | Define a clear return/conversion contract |
| JDK Proxy adapter throws undeclared checked exception | Possible `UndeclaredThrowableException` | Review the exception policy |
| Engine cannot find object due to changed context/scope | Missing function/member or engine-specific error | Audit `Bindings` and `ScriptContext` |
| Untrusted script code running in-process | **Security risk** | Isolate/audit; do not treat `ScriptEngine` as a sandbox |

### 10.1. Exception-branching pattern for direct calls

```java
// Snippet, assuming engine/Invocable is ready.
try {
    Object result = inv.invokeFunction("calculate", 2, 5);
    // Validate result against the contract schema.
} catch (NoSuchMethodException ex) {
    // Name or signature mismatch.
} catch (ScriptException ex) {
    // Script runtime error / engine reported error.
}
```

Do not use `catch(Throwable)` and return a default to mask `OutOfMemoryError` or severe VM errors. Applications may add domain-specific error types at service boundaries, but should not lose the cause and diagnostic context.

### 10.2. Distinguishing errors at `eval` vs. errors at `invoke`

A function may be defined successfully yet only throw when executed:

```javascript
function laterFailure() {
    throw new Error("failure while invoking");
}
```

The engine may `eval` successfully because the source is valid; the error only appears upon `invokeFunction("laterFailure")`. Conversely, a syntax error during `eval` can throw `ScriptException` **before any function is registered**.

Therefore, the pipeline should log stages separately:

1. **Engine discovery**.
2. **Capability check (`Invocable`)**.
3. **Script loading / `eval`**.
4. **Function/method lookup and invocation**.
5. **Result/exception conversion**.

Putting everything into a single `catch(Exception)` block makes it difficult to distinguish deployment errors from script business-logic errors.

## 11. Thread safety, scope, lifecycle, and performance

### 11.1. Do not assume an engine is thread-safe

A `ScriptEngine` may hold global variables, script objects, a module cache, or interpreter state. Whether multiple threads can safely share an engine depends on the provider. Some engines expose `"THREADING"` metadata via `ScriptEngineFactory.getParameter(...)`, but that value must be interpreted according to the vendor's documentation; do not assume every engine has the same level of synchronization.

Avoid indiscriminately sharing a stateful script object and interface adapter across concurrent requests. You can:

- Create a **separate engine instance** per stateful request/session.
- Apply synchronization/locks if the provider supports a shared model that is not thread-safe.
- Use an engine pool and per-tenant isolation if performance requires it.
- Limit the number of loaded scripts/objects and manage their lifecycle.

### 11.2. `Bindings` and `ScriptContext` affect where functions are found

When running `eval`, the engine may store state in `ENGINE_SCOPE`/`GLOBAL_SCOPE` and a `ScriptContext`. If you `eval` in one context and then call `invokeFunction` on an engine using a different state/context, the function may not be found. How function objects are stored, their lifetime, and binding rules depend on the engine.

Design explicitly around "which script is loaded into which engine, which context, and which state the adapter is created from". Do not assume a new engine can invoke functions loaded in an old engine just because they share the same language name.

### 11.3. Cost of repeated function calls and interface views

`Invocable` avoids string concatenation and repeated `eval("func(...)")` on every call, and `getInterface` lets Java callers keep a typed API. However, overhead can still exist:

- Name-based dispatch in the interpreter.
- Conversion between Java ↔ script values.
- Argument/return marshalling.
- Adapter/proxy layer when using interface mapping.
- Synchronization if the engine is shared across threads.

Do not claim `getInterface` is always faster than `invokeFunction` or vice versa without benchmarking the specific provider. Measure under your workload with warm-up, realistic data, and representative call counts.

### 11.4. Do not cache adapters indefinitely if script state changes

A `getInterface` adapter may reference the engine, script object, bindings, or class loader. If the script is reloaded or the object context expires, the old adapter may no longer reflect the new state, depending on the provider.

Good management practices:

- Tie the adapter to the **version** of the script/engine and a clear lifecycle.
- Drop references to engines/objects that are no longer used.
- Upon reload, re-test contract methods and create new adapters if needed.
- Ensure updates to shared state are properly synchronized.

## 12. Security when embedding scripts

### 12.1. `ScriptEngine` does not create a sandbox by itself

A script engine running inside the application's JVM may be able to interact with Java host objects, the filesystem, network, processes, or data sources depending on provider configuration. **Do not treat `Invocable`, `getInterface`, or `ScriptEngineManager` as a permission-restriction mechanism**.

If script content comes from untrusted users, consider:

- A **restricted language/DSL** with appropriate AST validation.
- A scripting provider with properly configured host access restrictions.
- Process/container/VM-level isolation with limits on CPU, RAM, time, filesystem, network, and credentials.
- Controls on script count, execution time, recursion, and object lifetime.
- Threat-model evaluation rather than relying on the legacy Java Security Manager as a default safeguard.

Just because `getInterface` makes a script look like a typed Java object does **not** mean the script code is safe or trustworthy.

### 12.2. Do not concatenate input directly into script source when args can be passed

A risky approach:

```java
// ANTI-PATTERN when userInput is untrusted.
engine.eval("perform('" + userInput + "')");
```

A value containing quotes or control characters can break source structure and cause script injection. If the function is already defined and the engine supports `Invocable`, passing data **as arguments** is usually much cleaner:

```java
Object result = inv.invokeFunction("perform", userInput);
```

This does not turn the input into JavaScript source in the call itself. However, the loaded script can still process the input unsafely; validate/escape at downstream layers (SQL, HTML, shell, etc.) and enforce host access policies.

### 12.3. The Java ↔ script boundary needs a data contract

A typed interface view is a Java API, yet underneath it lies scripting logic that can change. You should have:

- Clear method names and input/output schemas.
- Null and numeric-precision policies.
- Timeout/cancellation policies; do not assume `Thread.interrupt` always stops a script.
- Diagnostic logging with context that does not leak secrets.
- Limits on calling host Java APIs from scripts and limits on resource consumption.

## 13. Choosing between `invokeFunction`, `invokeMethod`, and `getInterface`

| Goal | Approach | Reason |
| --- | --- | --- |
| Call a top-level function by name | `invokeFunction(name,args)` | Simple, direct feedback, suits dynamic function names |
| Call a method of a script object | `invokeMethod(thiz,name,args)` | Preserves the receiver/object state |
| Have a stable Java interface mapped to global functions | `getInterface(Api.class)` | Java caller gets a typed API without repeating string function names |
| Have a stable Java interface mapped to a script object | `getInterface(scriptObject,Api.class)` | Creates a typed view bound to the object's state |
| Only need to evaluate a script block and get a result | `ScriptEngine.eval(source)` | Does not require the engine to implement `Invocable` |
| Only have Java methods to call | Reflection/MethodHandle/normal calls | No need to embed scripting |
| Engine does not implement `Invocable` | Engine-specific API or switch provider | Must not cast blindly |
| Script provider has functions not yet loaded | `eval`/load first | Capability check does not guarantee function existence |

### 13.1. Integration pattern with contract checks

```java
// Architectural skeleton snippet, not a standalone program.
ScriptEngine engine = provider.getEngine(); // Provider already configured.
if (engine == null) {
    throw new IllegalStateException("Missing script engine");
}
if (!(engine instanceof Invocable inv)) {
    throw new IllegalStateException("Engine is not Invocable");
}

engine.eval(verifiedScriptSource);
Api api = inv.getInterface(Api.class);
if (api == null) {
    throw new IllegalStateException("Script does not implement Api");
}

// Use api within the lifecycle of the corresponding engine and script.
```

`provider`, `Api`, and `verifiedScriptSource` are **illustrative symbols** to describe application structure, not standalone runnable code. In the main program, all required types/fields are defined.

The benefit of this pattern is **fail fast at the boundary**: it prevents an obscure `ClassCastException` or `NullPointerException` from surfacing after the application has already started handling requests.

## 14. Exercises and self-check questions

**Q1.** You have a `ScriptEngine` from `ScriptEngineManager`. Can you immediately cast it to `Invocable`?  
**Answer:** No. `Invocable` is an optional interface. You must ensure the engine is non-null and `instanceof Invocable` before casting.

**Q2.** Does Java 17 guarantee `getEngineByName("JavaScript")` returns an engine?  
**Answer:** No. Nashorn was removed from the JDK in Java 15. You must install/register a suitable JSR 223 JavaScript provider if you want to use it.

**Q3.** `eval("function add...")` succeeds, but `invokeFunction("multiply",2,3)` cannot find the function. What API error is expected?  
**Answer:** `NoSuchMethodException` if the function name or matching argument types are not found.

**Q4.** `invokeFunction("explode")` finds the function, but the script throws an error. Is it `NoSuchMethodException`?  
**Answer:** No. The engine typically reports `ScriptException` for script execution errors. The `MiniEngine` example intentionally demonstrates these two different exceptions.

**Q5.** To call `counter.increment(3)` on a script object, which API do you use?  
**Answer:** `inv.invokeMethod(scriptCounter,"increment",3)`, where `scriptCounter` must be a valid object recognized by the engine.

**Q6.** Does `invokeFunction("increment",3)` automatically find the method on `scriptCounter`?  
**Answer:** Not guaranteed. `invokeFunction` is for top-level functions. For object-bound methods, use `invokeMethod`.

**Q7.** Java has `MathOps` declaring `add` and `twice`, while the script only has `add`. Will `getInterface(MathOps.class)` definitely succeed?  
**Answer:** No. If the corresponding functions are not available, `getInterface` may return `null`. Check the result before calling.

**Q8.** How do the two `getInterface` overloads differ?  
**Answer:** `getInterface(Class<T>)` maps from **global functions**; `getInterface(Object,Class<T>)` maps from **member functions of the passed script object**.

**Q9.** Is `getInterface(String.class)` valid?  
**Answer:** No. `String.class` is not an interface; the API throws `IllegalArgumentException`.

**Q10.** Is `getInterface(MathOps.class)` returning `null` the same as `invokeFunction("add")` returning `null`?  
**Answer:** No. The former means no adapter could be created; the latter may be a valid function returning a `null` value.

**Q11.** An engine implements `Invocable`, but no script defining functions has been `eval`ed yet. Does `instanceof` returning `true` guarantee `invokeFunction` will succeed?  
**Answer:** No. Capability and loaded state are two different things. You must load/`eval` first and verify the function/method actually exists.

**Q12.** Is `invokeMethod(null,"value")` allowed?  
**Answer:** No. `thiz` must be a valid script object; the API specifies `IllegalArgumentException` when the receiver is `null`/invalid.

**Q13.** Why shouldn't you cast the result of every `invokeFunction("sum")` to `Integer`?  
**Answer:** Java ↔ script numeric mapping is implementation-specific. Some engines return `Double` or other types; check the type/schema and convert explicitly.

**Q14.** An interface returns `int`, but the script returns `null`. What can happen?  
**Answer:** The adapter may throw `NullPointerException` during unboxing (or a conversion error depending on the provider). Define a return-type contract and handle `null`.

**Q15.** Does the Java standard require `getInterface` to be implemented using JDK Proxy?  
**Answer:** No. The API only requires returning a compatible implementation or `null` when unavailable. The lesson's fixture uses Proxy as an example.

**Q16.** An untrusted script runs via `ScriptEngine` in a server JVM. Does `Invocable` isolate access permissions on its own?  
**Answer:** No. You need a threat model, host access restrictions, and proper isolation; a typed interface does not create a sandbox.

**Q17.** Two threads concurrently call methods on a stateful script object. Can you assume this is safe?  
**Answer:** No. Check the provider's thread-safety and limit shared state/context, using a per-session engine or synchronization.

**Q18.** Why is passing `userInput` as `invokeFunction("perform",userInput)` usually better than concatenating it into an `eval(...)` string?  
**Answer:** It avoids turning input data into script source in the call, reducing script injection risks from raw string concatenation, though you still need separate validation and sandboxing/isolation.

## 15. Summary and official documentation

**Remember the four `Invocable` APIs:**

```text
invokeFunction("name", args...)
    -> calls a global function; returns Object

invokeMethod(scriptObject, "name", args...)
    -> calls a method on a script object; returns Object

getInterface(JavaInterface.class)
    -> typed view from global functions; may be null

getInterface(scriptObject, JavaInterface.class)
    -> typed view from an object's methods; may be null
```

**Safe usage checklist:**

1. Look up the engine and confirm `engine != null`.
2. Check `engine instanceof Invocable` before casting.
3. `eval`/load the script into the right engine/context.
4. Call `invokeFunction` or `invokeMethod` depending on **global vs. object-bound**.
5. When a typed Java API is needed, use the right `getInterface` overload, **check for `null`**, and test method mappings.
6. Separate `NoSuchMethodException` from `ScriptException`; do not conflate them with a missing engine or a `null` adapter.
7. Verify return conversions, `null` handling, primitive types, and the interface's exception policy.
8. Manage lifecycle/thread-safety and secure script/host access within the appropriate provider boundaries.

**Official references:**

- [Oracle Java SE 17 — `Invocable`](https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/Invocable.html): the four APIs, `null` values, `NoSuchMethodException`, `ScriptException`, `IllegalArgumentException`.
- [Oracle Java SE 17 — `ScriptEngine`](https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/ScriptEngine.html): `eval`, `get`/`put`, scopes, and context.
- [Oracle Java SE 17 — `ScriptEngineManager`](https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/ScriptEngineManager.html): engine discovery via provider factories and lookup by name/extension/MIME.
- [Oracle Java SE 17 — `AbstractScriptEngine`](https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/AbstractScriptEngine.html): base class used in the fixture.
- [Oracle Java SE 17 — `ScriptException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/ScriptException.html): script evaluation/invocation errors.
- [OpenJDK JEP 372 — Remove the Nashorn JavaScript Engine](https://openjdk.org/jeps/372): Nashorn was removed from the JDK in Java 15; the `javax.script` API remains.

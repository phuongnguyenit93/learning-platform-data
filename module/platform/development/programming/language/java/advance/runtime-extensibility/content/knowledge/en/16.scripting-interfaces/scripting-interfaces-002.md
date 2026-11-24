# Checking Invocable Before Invoking Functions or Methods

## 1. Why Must You Check Invocable?

A Java program can use the Java Scripting API (JSR 223) to interact with a scripting language provided via a **ScriptEngine**. For example, the host loads a script that defines pricing functions, text-processing rules, or methods on a script object, and then wants to invoke those behaviors from Java.

However, **not every ScriptEngine supports calling functions and methods directly by name**. The **javax.script.Invocable** interface is an **optional capability** of a script engine. Therefore, before calling **invokeFunction(...)** or **invokeMethod(...)**, you must verify that the engine is present and **implements Invocable**.

The processing flow should be:

~~~text
ScriptEngineManager
        |
        v
getEngineByName("engine-name")
        |
        +-- null --------> engine not found, report clearly
        |
        v
ScriptEngine engine
        |
        +-- !(engine instanceof Invocable)
        |        |
        |        +-----> engine can eval but does not support Invocable
        |
        v
   Invocable invocable
        |
        v
  engine.eval(script)
        |
        +-- ScriptException -> error reading/running script
        |
        v
  invokeFunction("name", args...)
  or invokeMethod(scriptObject, "name", args...)
        |
        +-- NoSuchMethodException -> no matching function/method found
        +-- ScriptException       -> error invoking script
        |
        v
      Object result
~~~

**Important order:**

1. Look up the engine using **ScriptEngineManager** (or receive a ScriptEngine supplied by dependency injection).
2. Check **engine != null**.
3. Check **engine instanceof Invocable** before casting/invoking.
4. Execute the script via **eval(...)** so that functions and objects are defined in the engine's state.
5. Call **invokeFunction(...)** or **invokeMethod(...)** with the right name and arguments.
6. Handle the **Object** result, exceptions, resources, and state lifecycle.

Do not treat **ScriptEngine.eval(...) working** as proof that **Invocable is definitely supported**: these are two separate interfaces with different responsibilities.

## 2. Distinguishing ScriptEngine and Invocable

| Component | Role | Usage Condition |
|---|---|---|
| **ScriptEngineManager** | Discovers/creates ScriptEngines via available ScriptEngineFactory providers | An engine provider must be visible |
| **ScriptEngine** | Evaluates scripts, manages context/bindings, gets and puts data | Core foundational interface of an engine |
| **Invocable** | Invokes script-defined functions/methods and adapts them to Java interfaces | Only usable when the engine **implements Invocable** |
| **ScriptEngineFactory** | Advertises engine name, language, capabilities, and factory creation | Used when selecting/configuring an engine |
| **ScriptContext / Bindings** | Stores variables and script execution context | Requires understanding scopes when looking up objects/functions |

**Invocable** consists of four groups of operations:

~~~java
// API signatures, illustrative snippet.
Object invokeFunction(String name, Object... args)
        throws ScriptException, NoSuchMethodException;

Object invokeMethod(Object thiz, String name, Object... args)
        throws ScriptException, NoSuchMethodException;

<T> T getInterface(Class<T> clasz);

<T> T getInterface(Object thiz, Class<T> clasz);
~~~

- **invokeFunction** calls a **top-level** function/procedure defined by the script.
- **invokeMethod** calls a **member method** on a script object recognized by the engine; that object is passed via **thiz**.
- **getInterface(Class<T>)** requests a Java interface adapter implemented by script functions in the engine.
- **getInterface(thiz, Class<T>)** requests a Java interface adapter implemented by member methods of a script object.

**getInterface(...)** may return **null** if the engine cannot create the corresponding adapter; an engine implementing Invocable **does not guarantee that every interface can be mapped**. Nor do the two getInterface methods prove that specific functions exist before attempting the mapping.

## 3. Checking null and Invocable Capability Properly

### 3.1. Pattern Using Java 17+

~~~java
// Code snippet: used inside a method handling ScriptException, ...
ScriptEngineManager manager = new ScriptEngineManager();
ScriptEngine engine = manager.getEngineByName("javascript");

if (engine == null) {
    throw new IllegalStateException("No JavaScript ScriptEngine installed");
}

if (!(engine instanceof Invocable invocable)) {
    throw new UnsupportedOperationException(
        "This ScriptEngine does not implement Invocable");
}

// After checking and evaluating the script...
Object value = invocable.invokeFunction("hello", "Java");
~~~

The **instanceof Invocable invocable** syntax is *pattern matching for instanceof*, supported in Java 17. It simultaneously checks the runtime type and binds the **invocable** variable with type Invocable for the subsequent branch.

You can use the Java 8-compatible form:

~~~java
// Illustrative snippet, engine was obtained beforehand and is non-null.
if (!(engine instanceof Invocable)) {
    throw new UnsupportedOperationException("Not invocable");
}
Invocable invocable = (Invocable) engine;
~~~

Both approaches are semantically equivalent when properly guarded. When **engine == null**, the **instanceof** operator always evaluates to **false**, but you should still check for null separately because "no engine found" differs from "engine found but lacks the capability."

### 3.2. Avoiding ClassCastException

~~~java
// WRONG: never assume every ScriptEngine is Invocable.
ScriptEngine engine = new ScriptEngineManager()
        .getEngineByName("some-language");
Invocable inv = (Invocable) engine;
~~~

A direct cast can throw **ClassCastException** if the engine does not implement Invocable. If no engine is found, **inv** can also receive null (casting null does not throw by itself), and calling inv.invokeFunction(...) subsequently leads to a **NullPointerException**.

The right way is to separate three states:

~~~text
engine == null                -> MISSING_ENGINE
engine != null but !Invocable -> UNSUPPORTED_CAPABILITY
engine instanceof Invocable   -> READY_TO_EVAL_AND_INVOKE
~~~

In large applications, these three states should have distinct diagnostic messages and be logged along with the engine name and provider version.

## 4. Special Note on Java 17: The JDK Does Not Guarantee a JavaScript Engine

**javax.script** belongs to the standard **java.scripting** module, but **having the API does not mean an implementation is bundled for every language**.

The Nashorn JavaScript engine shipped with older JDKs was **removed from the JDK starting in Java 15**. Therefore, on many JDK 17 installations, the snippet:

~~~java
ScriptEngine engine = new ScriptEngineManager()
        .getEngineByName("javascript");
~~~

will return **null** if you have not installed/registered an external JavaScript engine. **Do not write a Java 17 lesson or application assuming a default JavaScript engine always exists.**

To diagnose which engines are currently discovered:

~~~java
// Illustrative snippet that runs when java.scripting is present.
ScriptEngineManager manager = new ScriptEngineManager();
for (ScriptEngineFactory factory : manager.getEngineFactories()) {
    System.out.println(
        factory.getEngineName() + " : " + factory.getNames());
}
~~~

The list may be empty or contain multiple factories depending on the runtime and installed libraries. **ScriptEngineManager.getEngineByName(name)** returns **null** if there is no factory for that name. Aliases such as "javascript", "js", or another name depend on the provider's **ScriptEngineFactory.getNames()**; not all engines accept the same aliases.

**How to supply an engine:** add a JSR 223 implementation with a valid **ScriptEngineFactory** to the classpath/module path and resolve dependencies according to that library's official documentation. Do not assume every interpreter or every GraalVM distribution automatically registers a JSR 223 engine and implements Invocable; verify on the actual version. With explicit named modules, pay attention to the module graph, the module providing ScriptEngineFactory, and class loader configuration.

In the standalone example in section 7, we intentionally build a **minimal simulated engine in pure Java** so it runs on JDK 17 without requiring a JavaScript provider; that example accurately demonstrates the **guard → eval → invoke** flow, but **is not a JavaScript interpreter**.

## 5. How Do invokeFunction and invokeMethod Differ?

### 5.1. invokeFunction: Calling a Top-Level Function

Illustrative JavaScript assuming an engine supporting JSR 223 and Invocable:

~~~javascript
function greet(name) {
    return "Hello, " + name;
}
~~~

After running the script above with **engine.eval(...)**:

~~~java
// Code snippet: engine implements Invocable and has evaluated the script.
Object answer = invocable.invokeFunction("greet", "Java");
System.out.println(answer);
~~~

The output **in a compatible JavaScript engine** can be:

~~~text
Hello, Java
~~~

**invokeFunction** takes no target object; the name **greet** must point to a function the engine can invoke in the evaluated state.

### 5.2. invokeMethod: Calling a Member on a Script Object

Illustrative JavaScript script:

~~~javascript
var formatter = {
    prefix: "Hi, ",
    greet: function(name) {
        return this.prefix + name;
    }
};
~~~

Java:

~~~java
// Code snippet: engine has evaluated the JavaScript snippet above.
Object scriptObject = engine.get("formatter");
Object answer = invocable.invokeMethod(
        scriptObject, "greet", "Java");
System.out.println(answer);
~~~

Output when the engine supports this operation:

~~~text
Hi, Java
~~~

The **thiz** argument (the API parameter name) is a **script object recognized by the engine**, not an arbitrary ordinary Java Object. It typically comes from **engine.eval(...)**, **engine.get(...)**, or the return value of a previous script call, depending on the engine. When **thiz == null** or does not represent a valid script object, **invokeMethod** may throw **IllegalArgumentException** per the API contract.

### 5.3. Comparison Table

| Criterion | invokeFunction | invokeMethod |
|---|---|---|
| Target | Top-level function/procedure | Method belonging to a script object |
| Specific parameters | **name** | **thiz**, **name** |
| Must script be evaluated first? | Yes, so the function is defined in the engine | Yes, so the object/method exists |
| Wrong name/signature mismatch | **NoSuchMethodException** | **NoSuchMethodException** |
| Error during script execution | **ScriptException** | **ScriptException** |
| Return type | **Object** | **Object** |
| Number, string, object conversion rules | Engine implementation-dependent | Engine implementation-dependent |

**Choose the API by the nature of the target:** top-level functions use invokeFunction; methods of a script object use invokeMethod. Do not call invokeMethod with a Java-constructed object merely because it happens to have a method with the same name.

## 6. You Must eval Before Invoking, and Checking Invocable Does Not Guarantee a Function Exists

**Invocable is a capability**, not a guarantee that specific functions exist. For example:

~~~java
// Illustrative snippet:
if (engine instanceof Invocable invocable) {
    engine.eval("function add(a, b) { return a + b; }");
    Object sum = invocable.invokeFunction("add", 2, 3);
    // The result may be bridged to Number/Double/Integer depending on the engine.
}
~~~

If the code defining the **add** function has not been evaluated yet, or the script ran in a different state, **invokeFunction("add", ...)** may throw **NoSuchMethodException**. If invoking the function hits a runtime error, it may throw **ScriptException**.

**Proper order:**

1. Verify the engine exists.
2. Verify the engine supports Invocable.
3. Evaluate the exact script into the state you intend to invoke.
4. Retrieve or verify the script object (if calling a method).
5. Invoke and handle the result/exceptions.

**Note on ScriptContext:** When eval uses a custom ScriptContext/Bindings, functions and objects defined inside that context are not guaranteed to be present in the default state used by a subsequent invoke call. Keep the engine/context consistent. How an engine retains functions across eval calls and resolves variables also depends on the language and implementation.

## 7. Complete Java 17 Example: Checking Invocable and Invoking Functions/Methods Without an External Engine

For this example to genuinely compile and run on **plain JDK 17**, the code below creates a **mini engine demonstrating the JSR 223 protocol**, not a real language interpreter. The only script command it accepts is the string **"install"**, which registers a top-level **hello** function and a simulated script object with a **say** method.

The mini engine still follows every API step we are studying:

- **ScriptEngineManager** returns a ScriptEngine from a ScriptEngineFactory.
- The host checks **instanceof Invocable** before invoking.
- **eval("install")** prepares the state.
- **invokeFunction("hello", "Java")** calls the function.
- **invokeMethod(receiver, "say", "Java")** calls the method on the object obtained from the engine.
- Calling a non-existent name throws **NoSuchMethodException**.
- **getInterface(...)** intentionally returns **null** in the demo: Java proxy creation is optional even when Invocable is supported.

### 7.1. InvocableGuardDemo.java

~~~java
import java.io.IOException;
import java.io.Reader;
import java.util.List;
import javax.script.AbstractScriptEngine;
import javax.script.Bindings;
import javax.script.Invocable;
import javax.script.ScriptContext;
import javax.script.ScriptEngine;
import javax.script.ScriptEngineFactory;
import javax.script.ScriptEngineManager;
import javax.script.ScriptException;
import javax.script.SimpleBindings;

public final class InvocableGuardDemo {

    private static final class ScriptObject {
        final String prefix;

        ScriptObject(String prefix) {
            this.prefix = prefix;
        }
    }

    // Minimal engine for demonstrating the contract; NOT JavaScript.
    private static final class TinyEngine
            extends AbstractScriptEngine implements Invocable {

        @Override
        public Object eval(String script, ScriptContext context)
                throws ScriptException {
            if (!"install".equals(script)) {
                throw new ScriptException("Unsupported demo command");
            }
            context.setAttribute(
                    "ready", Boolean.TRUE, ScriptContext.ENGINE_SCOPE);
            context.setAttribute(
                    "receiver",
                    new ScriptObject("Hi, "),
                    ScriptContext.ENGINE_SCOPE);
            return null;
        }

        @Override
        public Object eval(Reader reader, ScriptContext context)
                throws ScriptException {
            try {
                StringBuilder source = new StringBuilder();
                char[] buf = new char[256];
                int n;
                while ((n = reader.read(buf)) != -1) {
                    source.append(buf, 0, n);
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
            return new TinyFactory();
        }

        @Override
        public Object invokeFunction(String name, Object... args)
                throws ScriptException, NoSuchMethodException {
            if (!Boolean.TRUE.equals(
                    get("ready"))) {
                throw new ScriptException("Run eval before invoke");
            }
            if ("hello".equals(name) && args.length == 1) {
                return "Hello, " + args[0];
            }
            throw new NoSuchMethodException(name);
        }

        @Override
        public Object invokeMethod(Object thiz, String name, Object... args)
                throws ScriptException, NoSuchMethodException {
            if (!(thiz instanceof ScriptObject)
                    || thiz != get("receiver")) {
                throw new IllegalArgumentException(
                        "Receiver is not this engine's script object");
            }
            if ("say".equals(name) && args.length == 1) {
                return ((ScriptObject) thiz).prefix + args[0];
            }
            throw new NoSuchMethodException(name);
        }

        @Override
        public <T> T getInterface(Class<T> type) {
            if (type == null || !type.isInterface()) {
                throw new IllegalArgumentException("Not an interface");
            }
            return null; // This demo does not provide a Java interface adapter.
        }

        @Override
        public <T> T getInterface(Object thiz, Class<T> type) {
            if (type == null || !type.isInterface()
                    || thiz != get("receiver")) {
                throw new IllegalArgumentException(
                        "Invalid interface or script receiver");
            }
            return null;
        }
    }

    // Registered manually; no META-INF/services required.
    private static final class TinyFactory implements ScriptEngineFactory {

        @Override
        public String getEngineName() {
            return "TinyDemo";
        }

        @Override
        public String getEngineVersion() {
            return "1.0";
        }

        @Override
        public List<String> getExtensions() {
            return List.of("tiny");
        }

        @Override
        public List<String> getMimeTypes() {
            return List.of("text/x-tiny");
        }

        @Override
        public List<String> getNames() {
            return List.of("tiny");
        }

        @Override
        public String getLanguageName() {
            return "TinyLanguage";
        }

        @Override
        public String getLanguageVersion() {
            return "1.0";
        }

        @Override
        public Object getParameter(String key) {
            if (ScriptEngine.NAME.equals(key)) {
                return "tiny";
            }
            if (ScriptEngine.ENGINE.equals(key)) {
                return "TinyDemo";
            }
            if (ScriptEngine.ENGINE_VERSION.equals(key)) {
                return "1.0";
            }
            if (ScriptEngine.LANGUAGE.equals(key)) {
                return "TinyLanguage";
            }
            if (ScriptEngine.LANGUAGE_VERSION.equals(key)) {
                return "1.0";
            }
            return null;
        }

        @Override
        public String getMethodCallSyntax(
                String obj, String method, String... args) {
            return obj + "." + method
                    + "(" + String.join(", ", args) + ")";
        }

        @Override
        public String getOutputStatement(String toDisplay) {
            return "print(" + toDisplay + ")";
        }

        @Override
        public String getProgram(String... statements) {
            return String.join("\n", statements);
        }

        @Override
        public ScriptEngine getScriptEngine() {
            return new TinyEngine();
        }
    }

    public static void main(String[] args) throws Exception {
        ScriptEngineManager manager = new ScriptEngineManager();

        // Register provider manually so the example runs on plain JDK 17.
        manager.registerEngineName("tiny", new TinyFactory());
        ScriptEngine engine = manager.getEngineByName("tiny");

        if (engine == null) {
            System.out.println("missing engine");
            return;
        }
        if (!(engine instanceof Invocable invocable)) {
            System.out.println("engine is not Invocable");
            return;
        }

        System.out.println("invocable=true");

        // Declare the function and object into TinyEngine's state.
        engine.eval("install");

        System.out.println(
            "function=" + invocable.invokeFunction("hello", "Java"));

        Object receiver = engine.get("receiver");
        System.out.println(
            "method=" + invocable.invokeMethod(
                receiver, "say", "Java"));

        try {
            invocable.invokeFunction("missing");
        } catch (NoSuchMethodException e) {
            System.out.println("missing=NoSuchMethodException");
        }

        Runnable adapter = invocable.getInterface(Runnable.class);
        System.out.println("adapter=" + (adapter != null));
    }
}
~~~

### 7.2. Compile and Run

Save the file as **InvocableGuardDemo.java**. On JDK 17 or later:

~~~bash
javac --release 17 -encoding UTF-8 InvocableGuardDemo.java
java InvocableGuardDemo
~~~

**Fixed deterministic stdout:**

~~~text
invocable=true
function=Hello, Java
method=Hi, Java
missing=NoSuchMethodException
adapter=false
~~~

### 7.3. Explaining the Output

1. **TinyFactory** is registered directly via **registerEngineName("tiny", ...)**. Therefore the example does not need to locate an external JavaScript engine and does not depend on Nashorn being present.
2. **getEngineByName("tiny")** returns **TinyEngine**; this class implements **Invocable**, so the guard passes and prints **invocable=true**.
3. **eval("install")** simulates the script defining a function and object, storing state in ENGINE_SCOPE.
4. **invokeFunction("hello", "Java")** returns the string **Hello, Java**; this is not real JavaScript execution, but the result of the simulated dispatcher.
5. **invokeMethod(receiver, "say", "Java")** requires the object retrieved from the same engine, returning **Hi, Java**.
6. The **missing** function does not exist, so the mini engine throws **NoSuchMethodException**; the program handles it at the script invocation boundary.
7. Even though the mini engine implements Invocable, **getInterface(Runnable.class)** returns null because the demo does not implement a Java adapter, illustrating that proxy creation is a separate unguaranteed capability.

**Intentional limitations of the example:** TinyEngine only accepts the **install** command and uses a Java dispatcher; it has no JavaScript parser, supports no real scripting language, has no security controls, and must not be deployed to production. Its purpose is to provide **a complete standalone Java 17 program** so you can observe the exact data types, API ordering, guards, exceptions, and Invocable results.

## 8. Integration Pattern with a Real JavaScript Engine (Requires a JSR 223 Engine)

Once a **ScriptEngineFactory** for JavaScript is provided and the engine supports Invocable, the following pattern can be applied. This is a **valid Java program**, though the invoke branch only executes if the environment has a compatible engine.

**File RealScriptDemo.java:**

~~~java
import javax.script.Invocable;
import javax.script.ScriptEngine;
import javax.script.ScriptEngineManager;
import javax.script.ScriptException;

public final class RealScriptDemo {
    public static void main(String[] args)
            throws ScriptException, NoSuchMethodException {

        ScriptEngineManager manager = new ScriptEngineManager();
        ScriptEngine engine = manager.getEngineByName("javascript");

        if (engine == null) {
            System.out.println("NO_ENGINE");
            return;
        }

        if (!(engine instanceof Invocable invocable)) {
            System.out.println("NOT_INVOCABLE");
            return;
        }

        engine.eval("""
            function hello(name) {
                return "Hello, " + name;
            }

            var receiver = {
                say: function(name) {
                    return "Hi, " + name;
                }
            };
            """);

        System.out.println(
                invocable.invokeFunction("hello", "Java"));

        Object receiver = engine.get("receiver");
        System.out.println(
                invocable.invokeMethod(receiver, "say", "Java"));
    }
}
~~~

Run:

~~~bash
javac --release 17 -encoding UTF-8 RealScriptDemo.java
java RealScriptDemo
~~~

**Result branches to distinguish:**

- If **no JavaScript ScriptEngineFactory** is visible (typical on plain JDK 17), stdout is **NO_ENGINE**.
- If an engine is selected but **does not implement Invocable**, stdout is **NOT_INVOCABLE**.
- If the engine supports compatible JavaScript, allows defining functions/objects using the syntax above, preserves state, and supports both invocations, the two-line output can be:

~~~text
Hello, Java
Hi, Java
~~~

Do not hardcode the third output scenario as a promise across every engine. Engines can differ in aliases, data conversion, object handling, function scoping, or may not execute all of this syntax. That is precisely why the program checks the engine and capability first; additionally, you must test against the actual chosen engine and version.

**What not to do:** grab a **ScriptEngine engine** variable, evaluate the script, and immediately cast **(Invocable) engine**; even when the script is valid, the engine may not support that optional interface.

## 9. Exceptions and Errors to Handle at Each Layer

| Location | Scenario | Detection / Handling |
|---|---|---|
| **ScriptEngineManager.getEngineByName** | No engine found for the given name/alias | **engine == null**, inspect the factories list |
| **Capability check** | Engine can eval but does not support calling functions/methods | **!(engine instanceof Invocable)**, choose an alternative mechanism |
| **engine.eval(...)** | Syntax error, runtime error, or engine cannot execute script | **ScriptException**, log source/line if available |
| **invokeFunction(name, ...)** | Function or matching signature/arguments not found | **NoSuchMethodException** |
| **invokeMethod(thiz, name, ...)** | Matching method not found on the script object | **NoSuchMethodException** |
| **invokeMethod(thiz, ...)** | thiz is null or not a script object recognized by the engine | **IllegalArgumentException** |
| **invokeFunction/invokeMethod** | Error raised while executing script logic | **ScriptException** |
| **Result from script** | Returned Object cannot be assigned to the expected Java type | Check type before casting/converting |
| **getInterface(...)** | Cannot build an adapter with the matching functions | May return **null** |
| **getInterface(...)** | Class argument is null/not an interface; thiz is invalid | May throw **IllegalArgumentException** per contract |

Example of an error-handling adapter (illustrative Java snippet inside a class importing javax.script.*):

~~~java
static Object invokeSafe(
        ScriptEngine engine, String functionName, Object... arguments)
        throws ScriptException, NoSuchMethodException {

    if (engine == null) {
        throw new IllegalStateException("Script engine unavailable");
    }

    if (!(engine instanceof Invocable invocable)) {
        throw new UnsupportedOperationException(
                "Engine cannot invoke functions");
    }

    // The function must have been defined by the script before this call.
    return invocable.invokeFunction(functionName, arguments);
}
~~~

**This is a method snippet, not a standalone application.** A missing function name is a different error category from an engine lacking Invocable capability. If business code needs to return a categorized result (success/missing function/script error), map each exception to the appropriate result type rather than lumping everything into catch(Exception) and returning null.

Separating **ScriptException** from **NoSuchMethodException** enables accurate logging and feedback:

~~~java
// Illustrative snippet in script-calling code.
try {
    Object value = invocable.invokeFunction("calculate", 10);
    System.out.println(value);
} catch (NoSuchMethodException e) {
    System.err.println("Script function not found: calculate");
} catch (ScriptException e) {
    System.err.println("Script execution failed: " + e.getMessage());
}
~~~

**Note:** Name binding and argument conversion are defined by each engine. Standard Java errors (NullPointerException, IllegalArgumentException, ClassCastException, etc.) can still occur due to flawed integration logic; guards do not make scripting error-free.

## 10. Data Types: Object... Inputs and Object Outputs

**invokeFunction** and **invokeMethod** accept an **Object...** argument list. They rely on the engine to convert Java objects to script values and vice versa. For example, a numeric expression in JavaScript might be bridged to **Double**, **Integer**, **Long**, **BigDecimal**, or an engine-specific wrapper; never infer a concrete Java type from script syntax.

Instead of blind casting:

~~~java
// Wrong if the engine does not return an exact Integer.
Integer count = (Integer) invocable.invokeFunction("count");
~~~

validate the expected contract:

~~~java
// Illustrative snippet; count function is expected to return a numeric result.
Object raw = invocable.invokeFunction("count");

if (!(raw instanceof Number number)) {
    throw new IllegalStateException("count did not return a number");
}

int count = number.intValue();
~~~

If precision or integer bounds matter, **intValue()** can silently truncate decimals or overflow; numeric conversion conventions should be part of the integration contract.

**Varargs can be confusing when passing null.** In Java, **invokeFunction("f", (Object) null)** is a call with one null argument, whereas **invokeFunction("f", (Object[]) null)** passes a null varargs array. Do not treat these two forms as interchangeable if the engine distinguishes argument counts.

When a script object is returned, you sometimes need to pass that exact value back as **thiz** to invokeMethod; do not cast it to a specific Java type unless the engine publishes that wrapper type.

## 11. getInterface Is Another Option, Not a Replacement for Checking Invocable

If a script defines functions matching a Java interface, **Invocable.getInterface** can return an adapter so you can invoke via Java methods instead of string names:

~~~java
// Java interface, illustrative snippet.
public interface Formatter {
    String format(String name);
}
~~~

~~~java
// Illustrative snippet: previously the engine evaluated a script
// defining function format(name).
if (engine instanceof Invocable invocable) {
    Formatter formatter = invocable.getInterface(Formatter.class);

    if (formatter == null) {
        throw new UnsupportedOperationException(
            "No matching Formatter adapter available");
    }

    String result = formatter.format("Java");
}
~~~

The **Formatter** variable exposes methods known statically to Java code; the adapter can help avoid repeating string function names in business calls. However, **getInterface** still belongs to the **Invocable** interface, and **the return value may be null**. Not every engine implements proxying the same way; the specific methods must be defined appropriately by the script.

For a script object with methods, use **getInterface(scriptObject, Formatter.class)** if supported by the engine. The **scriptObject** must belong to the same engine and state. When the class argument is not an interface or the object is invalid, **IllegalArgumentException** may be thrown.

**Do not confuse them:** **instanceof Invocable** checks whether the engine has the capability to *invoke script functions/methods*. **getInterface(...) != null** specifically checks whether the engine can supply *an adapter to a particular Java interface* in its current state.

## 12. Design Mistakes and How to Fix Them

### 12.1. Casting Directly Without Checking

~~~java
// Anti-pattern:
Invocable inv = (Invocable) manager.getEngineByName("javascript");
~~~

**Fix:** obtain ScriptEngine, check for null, use **instanceof Invocable inv**, and only then invoke.

### 12.2. Checking Engine Presence While Skipping Capability Check

~~~java
// Anti-pattern:
if (engine != null) {
    ((Invocable) engine).invokeFunction("run");
}
~~~

**Fix:** check the Invocable interface separately. An engine can evaluate scripts successfully yet still lack the invocation API.

### 12.3. Invoking Before Evaluating the Script

~~~java
// Anti-pattern: function not yet registered in engine state.
invocable.invokeFunction("greet", "Java");
engine.eval("function greet(name) { return name; }");
~~~

**Fix:** eval first, invoke after. Even if source is compiled or preloaded via another mechanism, ensure the function is present in the active engine context.

### 12.4. Confusing Top-Level Functions with Object Methods

~~~java
// Not equivalent:
invocable.invokeFunction("greet", "Java");
invocable.invokeMethod(scriptObject, "greet", "Java");
~~~

These two calls search for functions in different places. If the script defines **formatter.greet**, you need a valid **formatter object** for invokeMethod; if it defines **function greet**, invokeFunction is appropriate.

### 12.5. Assuming getInterface Is Never null

~~~java
// Anti-pattern: may be null.
Formatter formatter = invocable.getInterface(Formatter.class);
formatter.format("Java");
~~~

**Fix:** check **formatter != null** and provide a clear fallback or error when the adapter is unavailable.

### 12.6. Assuming Java 17 Always Has a "javascript" Engine

Since Java 15, Nashorn is no longer bundled with the JDK. On JDK 17, without an external JavaScript provider, **getEngineByName("javascript")** returns null. **Fix:** declare the engine dependency in the runtime, use names from **getEngineFactories()**, validate before use, and provide a clear error path.

### 12.7. Mixing Objects Across Multiple ScriptEngines

A script object from engine A cannot automatically be used as **thiz** for engine B's Invocable. Even if both engines support the same language, wrappers, object identity, and state may differ. **Fix:** keep the engine, ScriptContext, and script objects within the same usage session.

### 12.8. Using a Stateful Engine Concurrently Without Control

An engine instance can hold variables, scopes, bindings, and language state. Do not assume every ScriptEngine is thread-safe. The **THREADING** parameter in ScriptEngineFactory.getParameter(...) supplies information per the provider's contract; read the engine documentation and apply pooling, serialization, or context isolation accordingly. Checking **Invocable** is not a thread-safety check.

## 13. Why Can an Engine or Function "Disappear"?

In plugin/runtime-extensibility applications, Invocable failures are often tied to provider discovery or engine state rather than Java syntax alone.

**Engine not found:** ScriptEngineManager discovers factories via the provider mechanism (ServiceLoader). Classpath, module path, Thread Context ClassLoader, and registration can all affect the factory list. Print **manager.getEngineFactories()** to see which engines are actually visible.

**Engine does not support Invocable:** An interpreter may execute scripts via **eval(...)** without letting the host call functions directly by name or without an object model suitable for member invocation. That is a valid design; the host needs a fallback such as **engine.eval("...")** with appropriate bindings (if allowed by the engine) or a different engine.

**Evaluated but function not visible:** The script may have defined a local function rather than exporting it to global scope; the script ran under a different context; the function was overwritten; or name/arity/type conversion is incompatible. Inspect the script language semantics and exact state instead of assuming every function declaration is top-level.

**invokeMethod rejects the receiver:** The object does not belong to the interpreter, is null, or is no longer retained/recognized by the engine. Reuse the object returned from the same engine/session instead of creating an arbitrary POJO.

**Engine dependencies changed:** Upgrading the JDK, relocating JARs, or changing engine providers can alter aliases, Invocable support, and bridged data types. Re-test integrations instead of assuming JSR 223 guarantees language-specific syntax or semantics.

## 14. Security, Resources, and Practical Limits

**Invocable is not a sandbox.** When calling **eval**, **invokeFunction**, or **invokeMethod**, the host may execute script code directly in-process depending on the engine's permissions and mechanisms. If scripts come from users or untrusted sources, design security boundaries, permissions, and isolation from the start. Specifically:

- Do not expose Java objects containing secrets, database connections, or internal APIs to scripts via bindings unless necessary.
- Do not let scripts freely access host classes or runtime APIs in engines with Java interop without strict controls.
- Define maximum execution time, memory limits, and cancellation policies; the Invocable API **does not provide built-in timeouts**.
- Manage ScriptEngine state and resources: many engines maintain internal caches, threads, or contexts; lifecycle management must follow the implementation's documentation.
- When untrusted code must run, isolate it in a separate process/container or dedicated environment; never assume a class loader or Invocable check provides security.
- Do not log raw script contents containing private data; log the engine name, capability, error, and a trace identifier where appropriate.

In host API design, you can wrap ScriptEngine/Invocable behind a domain interface like **ScriptRunner** so callers do not need to know about individual engines. Inside the adapter, perform the null guard, instanceof guard, eval, and exception mapping in one unified place.

## 15. Essential Tests

### Test 1. Missing ScriptEngine

Simulate **getEngineByName(...)** returning null or run in an environment without a provider: the host must return a **MISSING_ENGINE** status and must not throw NullPointerException from invoking on null. This is a very real scenario with JavaScript on plain JDK 17.

### Test 2. Engine Supports eval but Does Not Implement Invocable

Supply a fake ScriptEngine that only implements eval (not Invocable). The guard must return **UNSUPPORTED_CAPABILITY** or take the appropriate fallback without throwing ClassCastException.

### Test 3. Engine Implements Invocable and Script Defines a Function

Evaluate a valid script and call **invokeFunction**. Verify arguments are passed properly, the result is handled per contract, and no errors occur.

### Test 4. Calling a Member Method on the Correct Script Object

Retrieve the script object from the same engine/session; call **invokeMethod(scriptObject, ...)**. Verify the method name is correct and distinguish it from a top-level function.

### Test 5. Non-Existent Function or Method

Invoke an invalid name or incompatible argument form; verify **NoSuchMethodException** is categorized and reported clearly.

### Test 6. Error Inside the Script

Use a script that intentionally throws an error; verify **ScriptException** is handled and not confused with "engine missing" or "function missing."

### Test 7. getInterface Has No Adapter

Even when Invocable is present, **getInterface** can return null. Test this branch so callers using proxies do not hit NullPointerException.

### Test 8. Engine Versions and State

Run the same test suite across each engine/version the application actually supports. Verify Object bridging, state across repeated evals, resource closing, and thread safety.

## 16. Self-Check Questions

**Question 1.** Is a ScriptEngine that can eval scripts guaranteed to implement Invocable?

**Answer:** No. Invocable is an **optional** interface. You must check **engine instanceof Invocable** before casting/invoking.

**Question 2.** Why check engine for null separately, even though instanceof on null returns false?

**Answer:** Null indicates **no ScriptEngine was found**, which is different from **an engine exists but does not support Invocable**. Separating them aids diagnostics and choosing the right fallback.

**Question 3.** When do you use invokeFunction instead of invokeMethod?

**Answer:** Use invokeFunction for top-level functions; invokeMethod requires a script object (thiz) and the name of a member method on that object.

**Question 4.** Does instanceof Invocable prove the "calculate" function already exists?

**Answer:** No. It only proves the engine supports the invocation API. The function must be defined in state with a matching name and arguments; otherwise NoSuchMethodException may occur.

**Question 5.** If an engine implements Invocable, is getInterface(Formatter.class) guaranteed to return a Formatter?

**Answer:** No. It can return null if the required functions/methods are absent or the engine does not supply an adapter for that interface.

**Question 6.** On JDK 17, is getEngineByName("javascript") always non-null?

**Answer:** No. Nashorn was removed from the JDK starting in Java 15; you must check whether a JavaScript engine provider is installed and discovered.

**Question 7.** Can a script object from engine A be used as thiz for engine B?

**Answer:** There is no guarantee. The object must be recognized by the Invocable of the engine being called; keep to the same engine and state.

## 17. Implementation Checklist

1. **Discover the engine:** verify getEngineByName(...) returns a result; record engine name/version/aliases from ScriptEngineFactory.
2. **Guard capability:** cast/invoke only when **engine instanceof Invocable**.
3. **Prepare state:** evaluate the right script in the right engine/context before invoking.
4. **Pick the right API:** invokeFunction for top-level functions, invokeMethod for members with a genuine script object receiver.
5. **Handle types:** returned **Object** values need contract-based validation/conversion, never blind casts.
6. **Categorize errors:** missing engine, missing Invocable, ScriptException, NoSuchMethodException, invalid receiver, and null getInterface proxy are separate branches.
7. **Control providers:** Java 17 does not bundle Nashorn by default; engine dependencies and names must be managed explicitly.
8. **Manage state/threading:** do not reuse an engine or script object across contexts/threads without an explicit contract.
9. **Security:** do not let untrusted scripts run inside the host JVM without proper isolation.
10. **Testing:** cover null engine, non-Invocable engine, valid function/method calls, missing names, script errors, and differences across engines/versions.

**Final takeaway:** **ScriptEngine** is the script evaluation mechanism; **Invocable** is an optional capability allowing Java to invoke script-defined functions or methods. Before invoking, always confirm **the engine exists**, **implements Invocable**, **the script/state is ready**, and **whether the target is top-level or a member**. Checking capabilities prevents cast errors, but does not replace validating function names, receivers, return values, and exceptions.

### Official Documentation

- Oracle Java SE 17 API — Invocable: https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/Invocable.html
- Oracle Java SE 17 API — ScriptEngine: https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/ScriptEngine.html
- Oracle Java SE 17 API — ScriptEngineManager: https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/ScriptEngineManager.html
- Oracle Java SE 17 API — ScriptEngineFactory: https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/ScriptEngineFactory.html
- Oracle Java SE 17 Migration Guide — Nashorn JavaScript engine removal: https://docs.oracle.com/en/java/javase/17/migrate/removed-tools-and-components.html

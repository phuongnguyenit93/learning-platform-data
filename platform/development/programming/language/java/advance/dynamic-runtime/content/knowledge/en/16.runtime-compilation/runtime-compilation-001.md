# 16.1 When you need `JavaCompiler` instead of reflection or creating a proxy

## 1. Goal: choosing the right tool for runtime changes

In the **Java Advance – dynamic-runtime** module, three API groups that are easily confused are:

- **Reflection** (`java.lang.reflect`): inspects and manipulates **existing classes, constructors, fields, and methods** in loaded or loadable bytecode.
- **JDK dynamic proxy** (`java.lang.reflect.Proxy`, `InvocationHandler`): creates an object implementing **existing interfaces**, then dispatches interface calls to a handler at runtime.
- **JavaCompiler** (`javax.tools.JavaCompiler`, JSR 199): **compiles new Java source at runtime** into `.class` bytecode, which can then be loaded and executed using a class loader.

All three mechanisms support flexible applications, but **they do not solve the same problem**. You do not need a compiler just to invoke a method whose name is unknown beforehand, or to wrap logging around an interface; conversely, Reflection cannot turn a new snippet of Java source into a new bytecode method by itself.

After this lesson, you should be able to answer: *“Do I need to find/call something that already exists, intercept an existing interface, or define a new implementation that has never been compiled?”* At the same time, you will know the workflow for using `ToolProvider.getSystemJavaCompiler()`, `StandardJavaFileManager`, `DiagnosticCollector`, `JavaCompiler.CompilationTask`, `URLClassLoader`, resource management, and security limitations.

> **Quick selection rule:** If the logic already exists as a class/method, prefer Reflection or normal static calls. If you want to wrap an interface with a common policy, consider JDK Proxy. Only choose `JavaCompiler` when you truly need **new Java code**, and the compilation cost, class loader management, and execution risks of that code are acceptable.

## 2. Comparing the nature of the three mechanisms

| Criterion | Reflection | JDK Proxy | `JavaCompiler` |
| --- | --- | --- | --- |
| Primary input | Existing `Class`/`Method`/`Field`/`Constructor` | **Existing interfaces** and `InvocationHandler` | **Java source** along with options/classpath/module path |
| Does it create new implementation bytecode? | No; it looks up and invokes an already-defined member | **Yes**, the JDK generates a proxy class for the interface; however, behavior is determined by the handler | **Yes**, the compiler turns custom source into an actual class |
| Can it add a new Java method body to an already-loaded class? | No | No; the handler handles defined interface methods | It can **compile a new class** with a new method body; it does not patch an already-loaded old class using only the compiler |
| Type seen by the caller | The return type from `Method.invoke` is usually `Object` | The declared interface | The class/interface implemented by the generated code |
| Suitable use cases | Pre-compiled plugins, finding methods by annotation, invoking methods by name | Logging, retry, metrics, authorization, lazy delegation through an interface | Generating specialized code from a trusted schema/DSL, compiling a new Java implementation |
| Runtime build tool dependency | Does not need `jdk.compiler` | Does not need `jdk.compiler` | Needs a compiler provider, usually in the JDK module `jdk.compiler` |
| Cost/runtime | Lookup/Reflection invoke; metadata can be cached | Create proxy once, go through handler on every call | **Compile + store/receive bytecode + load class**, significant cost before invocation |
| Main risks | Access control, wrong method/overload, reflection invocation exception | Recursion in handler, Object methods, interface limitation | Java source injection, diagnostics, classpath, loading, memory/classloader leaks, executing untrusted code |

**Important nuance:** Saying “Proxy does not create a new class” is **wrong**: `Proxy.newProxyInstance` creates or uses a JDK-generated proxy class at runtime. What Proxy **does not do** is compile **arbitrary Java source** or arbitrarily create a subclass of a business class; it generates a shape implementing the specified interfaces and routes calls to the handler.

Similarly, saying “JavaCompiler can modify a method of a running class” is also **wrong**. It creates a new set of `.class` files. The JVM cannot load two different definitions of the same class name with the **same defining class loader**; if you want versioning/hot reload, you need a new class loader, an appropriate framework/instrumentation, or a dedicated deployment mechanism.

## 3. When Reflection is enough: discovering and calling existing code

### 3.1. Reflection does not compile source

A plugin framework has a pre-built implementation:

```java
public final class ExistingRule {
    public int apply(int value) {
        return value * 2;
    }
}
```

If the class or method name comes from configuration, Reflection can be used:

```java
// Illustrative snippet; ExistingRule must exist on the classpath.
Class<?> type = Class.forName("ExistingRule");
Object instance = type.getConstructor().newInstance();
java.lang.reflect.Method method =
        type.getMethod("apply", int.class);
int result = (int) method.invoke(instance, 5);
// result = 10
```

`Class.forName` finds/loads an **existing class**. `getMethod` finds a public member with matching parameters. `Method.invoke` uses the argument values and can perform appropriate boxing/unboxing. No new Java source is compiled at all.

This is the right choice when:

- Multiple pre-built/pre-deployed implementations exist and need to be selected by name.
- A framework scans annotations and then invokes existing methods.
- Objects need to be constructed via a constructor selected at runtime.
- The dynamic input is only **the method name, instance, or data**, not a new method body.

### 3.2. What are the limitations of Reflection?

Reflection **cannot** take the source string `"return amount * 3 + 2;"` and turn it into executable bytecode. Nor can it create a new public method on an already-loaded class using only `getDeclaredMethods` or `Method.invoke`.

Reflection is also constrained by Java access control/JPMS. `getDeclaredMethod` seeing private metadata does not mean having permission to execute it. `setAccessible(true)` can be rejected by strong encapsulation; `privateLookupIn` also requires valid permissions/module openness. `JavaCompiler` is not a way to bypass this barrier — the newly generated class still must obey the same Java rules.

If the number of behavior variants is just a few parameters like `factor=2` or `factor=3`, an implementation that accepts constructor parameters is **simpler and safer than compiling a whole new class**.

## 4. When JDK Proxy is enough: wrapping calls through an interface

Suppose an interface already exists:

```java
interface PriceRule {
    int apply(int amount);
}
```

A real implementation is passed into `InvocationHandler`. The proxy can count invocations, check permissions, log, or forward:

```java
// Illustrative snippet, PriceRule and delegate are already defined.
PriceRule proxy = (PriceRule) java.lang.reflect.Proxy.newProxyInstance(
        PriceRule.class.getClassLoader(),
        new Class<?>[]{PriceRule.class},
        (receiver, method, args) -> {
            System.out.println("called=" + method.getName());
            try {
                return method.invoke(delegate,
                        args == null ? new Object[0] : args);
            } catch (java.lang.reflect.InvocationTargetException ex) {
                throw ex.getCause();
            }
        });
```

When code calls `proxy.apply(5)`, the JDK-generated proxy forwards the call to the handler. The handler then decides whether to return a result or delegate to `delegate`.

**Proxy is suitable when:**

- The caller only needs to work through an existing interface.
- You want to add **before/after behavior** to a call: tracing, metrics, caching, access control, circuit breaker.
- You want to select the delegate at runtime.
- Business variations can be expressed with configuration/strategy/handler without needing a new Java source class.

**Proxy is not suitable when:**

- You must create a **subclass of a concrete class** required by the caller/API; JDK Proxy **does not extend arbitrary classes**.
- You need to generate a set of methods with new names/signatures not present in defined interfaces.
- You want concrete Java code with complex structure that is statically checked by the compiler, rather than a centralized handler interpreting every call.
- An external system requires **a concrete implementation class** with bytecode/annotation structure that a JDK proxy does not provide.

**Nuance:** The handler **can compute new logic itself** (for example returning `amount * 3 + 2`) without a delegate. Therefore, the claim “whenever business logic changes you must use JavaCompiler” is **false**. If the logic is just a small function that can be implemented directly in the handler or strategy, Proxy can be a lighter option.

### 4.1. Limitations of proxy with classes and modules

`Proxy.newProxyInstance` accepts a list of **interfaces**, not regular classes. It creates a proxy class according to the JDK's access/package/module rules. You cannot pass `ArrayList.class` as if it were an interface to intercept.

Each method `equals`, `hashCode`, `toString` under the JDK Proxy mechanism can also go through the handler; handler code using `method.invoke(proxy,args)` to forward can re-enter and recurse. In simple cases, forward to the **real delegate**, while designing a consistent Object methods policy.

Proxy does not automatically make code run with higher privileges: the handler, delegate, reflection, and generated proxy are all subject to JVM access rules. If an interface is not visible from the specified class loader or does not meet proxy conditions, creation will fail.

## 5. When do you actually need `JavaCompiler`?

**`javax.tools.JavaCompiler` is Java's official API for invoking the compiler from Java code.** It belongs to the `java.compiler` module (API), with the compiler implementation usually provided by the JDK in `jdk.compiler`.

Choose runtime compilation when a requirement truly needs **a new Java implementation** and implementing it via strategy/proxy/Reflection becomes poorly suited:

### 5.1. Generating specialized classes from a controlled schema or DSL

A data processing system with a vetted schema can generate specialized Java source:

```java
// Java source generated from VALIDATED configuration, not arbitrary input.
public final class GeneratedPriceRule implements PriceRule {
    @Override public int apply(int amount) {
        return amount * 3 + 2;
    }
}
```

The compiler checks syntax and types, and produces bytecode with a real method body. After loading, the caller can use the generated object like a normal `PriceRule`.

However, **do not compile just because `factor=3`** if `new ExistingRule(3)` already meets the requirement. This example uses a small calculation to illustrate the technical pipeline; in production, the benefit of compilation is clearer when the logic is large, has many branches/schemas, or achieves significant specialization optimization.

### 5.2. Creating an implementation for an interface or a subclass of a non-final class

A complete Java class can be generated:

- `implements ExistingInterface` with new method bodies.
- `extends AccessibleBaseClass` if the base is non-final, has a valid constructor, and does not override final methods.
- Declaring public methods/fields/annotations needed by external tools (within Java compiler, accessibility, and module limits).

JDK Proxy only provides call interception through **interfaces**, not arbitrary concrete subclasses. Reflection only uses pre-existing classes. When a third-party framework requires an implementation/subclass with a **specific shape**, compiling source is a reasonable option.

However, if the primary need is **generating bytecode rather than source**, a library like Byte Buddy/ASM may be more suitable; that is a different approach, with its own maintenance costs and limitations.

### 5.3. Generating code on demand while still using Java's type system

For example:

- An internal rule engine generating code from a parsed and validated AST/DSL, then emitting it.
- Data mappers between frequently changing schemas, where specialized mapping brings clear benefits.
- An application's template compiler generating classes/methods with specific signatures.
- A plugin builder for **trusted source code** that is managed and tested.
- Integrations requiring classes built from a spec/configuration at runtime and loaded after creation.

The valuable point is **a new class with Java source checked by the compiler** and loadable by a class loader, rather than just a lazily invoked method.

### 5.4. When should you *not* use `JavaCompiler`?

Do not use the compiler if you only want to:

- Call an existing method with a configured name → Reflection/MethodHandle.
- Choose among existing strategies → interface + dependency injection/factory.
- Log or delegate calls through an interface → Proxy/decorator.
- Change a simple coefficient or predicate → data/configuration + function.
- Turn an **untrusted** user expression into Java running directly in the same JVM → arbitrary code execution risk, not a sandbox.
- Support a few variants known at build time → compiling ahead of time is usually easier to deploy/test.

## 6. Standard workflow when using JSR 199

The minimal pipeline consists of the following steps:

```text
1. Trusted Java source + valid class name
              |
2. ToolProvider.getSystemJavaCompiler()
              |
3. JavaFileObject(s) + JavaFileManager
              |
4. Diagnostics + compiler options
              |
5. CompilationTask.call()
       /                    \
  false/exception           true
       |                      |
  error messages            .class bytes
                              |
6. ClassLoader loads class + verifies type
                              |
7. Create instance / invoke method / cache result
```

### 6.1. Obtaining the compiler provider

```java
JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
if (compiler == null) {
    throw new IllegalStateException(
            "No system Java compiler; a full JDK is required");
}
```

**Important:** A runnable Java program **does not guarantee** that the runtime image has a compiler provider. With a minimal `jlink` image, a packaged Java environment missing the `jdk.compiler` module, or another runtime configuration, `getSystemJavaCompiler()` can return `null`.

In a named module environment, the `javax.tools` API in the `java.compiler` module must be read by the application module (for example `requires java.compiler;`). The presence of the API **does not by itself prove** that a compiler implementation is present; you must package/resolve the `jdk.compiler` provider or a compatible provider at deployment time.

### 6.2. Preparing the source and file manager

JSR 199 uses `JavaFileObject` to represent source/bytecode units and `JavaFileManager` to manage the corresponding files. The example chooses the easy-to-understand approach of writing temporary source to disk:

```java
Path source = scratch.resolve("GeneratedPriceRule.java");
Files.writeString(source, generatedSource, StandardCharsets.UTF_8);

DiagnosticCollector<JavaFileObject> diagnostics =
        new DiagnosticCollector<>();
try (StandardJavaFileManager fm =
             compiler.getStandardFileManager(
                     diagnostics, null, StandardCharsets.UTF_8)) {
    Iterable<? extends JavaFileObject> units =
            fm.getJavaFileObjectsFromPaths(List.of(source));
    // Call compiler.getTask(...) inside try.
}
```

This is a **snippet**, assuming `scratch`, `generatedSource`, and `compiler` already exist, along with the corresponding imports; the complete program in section 8 declares everything.

Writing to disk is not mandatory: you can implement `SimpleJavaFileObject` to hold source in memory and use `ForwardingJavaFileManager` to keep bytecode in a `ByteArrayOutputStream`. The in-memory approach is useful for systems that compile many times, but is more complex because you must manage output `JavaFileObject`s, class loaders, and resource lifecycles. When first learning, the default file manager + a temporary directory is a good starting point.

### 6.3. Invoking the compiler and handling diagnostics

```java
List<String> options = List.of(
        "-encoding", "UTF-8", "-proc:none",
        "--release", "17",
        "-classpath", System.getProperty("java.class.path"),
        "-d", output.toString());

boolean success = Boolean.TRUE.equals(
        compiler.getTask(
                null, fm, diagnostics, options, null, units).call());
```

This is a **snippet**; the variables are fully declared in the program in section 8.

- `"-d"`: destination directory for `.class` bytecode.
- `"-classpath"`: location to find compiled types, including interfaces/implementations that the generated source needs to see. The example runs on a simple classpath, so it can use `System.getProperty("java.class.path")`.
- `"--release", "17"`: compiles against the corresponding Java 17 API/language if the compiler supports that release; does **not** create a sandbox.
- `"-proc:none"`: disables annotation processing during this compilation; useful when you do not need to run processors that might be discovered from the classpath. It **does not make Java source code safe**.
- `DiagnosticCollector`: collects diagnostics with `kind`, file, line, column, and message. Do not just check `.call()==false` and stay silent.

`CompilationTask.call()` returns a Boolean indicating only whether **compilation** succeeded. Compilation success **does not prove** that class loading succeeds, all dependencies are present, or the method runs the right logic. Separate loading and testing steps are needed.

## 7. Designing an example comparing the three approaches

In the runnable example, we use the same contract:

```java
public interface PriceRule {
    int apply(int amount);
}
```

Three ways produce results:

| Approach | Pre-existing / new code | Invocation | Result for `amount=5` |
| --- | --- | --- | --- |
| Reflection | **Pre-compiled** `ExistingRule(factor=2)` | `Method.invoke(existing,5)` | `10` |
| Proxy | Wraps `ExistingRule(2)` via `PriceRule` | `proxy.apply(5)` (handler intercepts then delegates) | `10` |
| JavaCompiler | `GeneratedPriceRule` **did not exist before the program ran** | `generated.apply(5)` | `17` because `5*3+2=17` |

**Meaning:** Reflection solves **method selection/invocation**, Proxy solves **interception/delegation**, and JavaCompiler solves **creating a new class implementation**. The different outputs (10/17) are an intentional choice of the example, not proof that a proxy cannot create logic on its own.

To avoid ambiguity between two class loaders, the generated class **implements the exact `RuntimeCompilerDecisionDemo.PriceRule` interface** already loaded by the parent class loader. The generated code's loader uses a parent loader that sees that interface. This allows casting the new instance to the same interface class identity.

## 8. Complete and verified Java 17+ example

Save the entire code below as **`RuntimeCompilerDecisionDemo.java`**. The program uses author-defined (trusted) source, creates a temporary directory to compile, loads the new class, runs it, and cleans up files. It also compiles a syntactically invalid source to demonstrate how to retrieve diagnostics.

```java
import java.io.IOException;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Comparator;
import java.util.List;
import javax.tools.Diagnostic;
import javax.tools.DiagnosticCollector;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileObject;
import javax.tools.StandardJavaFileManager;
import javax.tools.ToolProvider;

public class RuntimeCompilerDecisionDemo {
    public interface PriceRule {
        int apply(int amount);
    }

    public static final class ExistingRule implements PriceRule {
        private final int factor;

        public ExistingRule(int factor) {
            this.factor = factor;
        }

        @Override public int apply(int amount) {
            return amount * factor;
        }
    }

    public static void main(String[] args) throws Exception {
        // 1. Reflection: invoke an ALREADY compiled implementation.
        Class<?> known = Class.forName(
                RuntimeCompilerDecisionDemo.ExistingRule.class.getName());
        Object existing = known.getConstructor(int.class).newInstance(2);
        Method apply = known.getMethod("apply", int.class);
        System.out.println("reflection=" + apply.invoke(existing, 5));

        // 2. JDK Proxy: intercept interface, then call existing logic.
        PriceRule delegate = new ExistingRule(2);
        int[] intercepted = {0};
        PriceRule proxy = (PriceRule) Proxy.newProxyInstance(
                PriceRule.class.getClassLoader(),
                new Class<?>[]{PriceRule.class},
                (receiver, method, callArgs) -> {
                    if (method.getDeclaringClass() == Object.class) {
                        return switch (method.getName()) {
                            case "toString" -> "PriceRuleProxy";
                            case "hashCode" -> System.identityHashCode(receiver);
                            case "equals" -> receiver == callArgs[0];
                            default -> throw new UnsupportedOperationException();
                        };
                    }
                    intercepted[0]++;
                    System.out.println("intercepted=" + method.getName());
                    try {
                        return method.invoke(delegate,
                                callArgs == null ? new Object[0] : callArgs);
                    } catch (InvocationTargetException e) {
                        throw e.getCause();
                    }
                });
        System.out.println("proxy=" + proxy.apply(5));
        System.out.println("proxy calls=" + intercepted[0]);

        // 3. JavaCompiler: compile a NEW class not in the initial build.
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        System.out.println("compiler available=" + (compiler != null));
        if (compiler == null) {
            throw new IllegalStateException(
                    "A full JDK with the jdk.compiler module is required");
        }

        Path scratch = Files.createTempDirectory("rule-demo-");
        try {
            Path output = Files.createDirectory(scratch.resolve("classes"));
            Path source = scratch.resolve("GeneratedPriceRule.java");
            Files.writeString(source, """
                    public final class GeneratedPriceRule
                            implements RuntimeCompilerDecisionDemo.PriceRule {
                        @Override public int apply(int amount) {
                            return amount * 3 + 2;
                        }
                    }
                    """, StandardCharsets.UTF_8);

            List<String> options = List.of(
                    "-encoding", "UTF-8", "-proc:none",
                    "--release", "17",
                    "-classpath", System.getProperty("java.class.path"),
                    "-d", output.toString());

            DiagnosticCollector<JavaFileObject> diagnostics =
                    new DiagnosticCollector<>();
            try (StandardJavaFileManager fm =
                         compiler.getStandardFileManager(
                                 diagnostics, null, StandardCharsets.UTF_8)) {
                Iterable<? extends JavaFileObject> units =
                        fm.getJavaFileObjectsFromPaths(List.of(source));
                boolean compiled = Boolean.TRUE.equals(
                        compiler.getTask(null, fm, diagnostics,
                                options, null, units).call());
                System.out.println("compiled=" + compiled);
                if (!compiled) {
                    for (Diagnostic<? extends JavaFileObject> d :
                            diagnostics.getDiagnostics()) {
                        System.err.println(d.getKind()
                                + ": " + d.getMessage(null));
                    }
                    throw new IllegalStateException("Compilation failed");
                }
            }

            try (URLClassLoader loader =
                         new URLClassLoader(new URL[]{output.toUri().toURL()},
                                 PriceRule.class.getClassLoader())) {
                Class<?> generatedType =
                        Class.forName("GeneratedPriceRule", true, loader);
                PriceRule generated =
                        (PriceRule) generatedType.getConstructor().newInstance();
                System.out.println("new class=" + generatedType.getSimpleName());
                System.out.println("generated=" + generated.apply(5));
                System.out.println("same interface="
                        + PriceRule.class.isAssignableFrom(generatedType));
            }

            // Negative control: syntactically invalid Java source is rejected.
            Path invalidSource = scratch.resolve("InvalidPriceRule.java");
            Files.writeString(invalidSource,
                    "public class InvalidPriceRule { syntax error }",
                    StandardCharsets.UTF_8);
            DiagnosticCollector<JavaFileObject> invalidDiagnostics =
                    new DiagnosticCollector<>();
            try (StandardJavaFileManager fm =
                         compiler.getStandardFileManager(
                                 invalidDiagnostics, null, StandardCharsets.UTF_8)) {
                boolean invalidCompiled = Boolean.TRUE.equals(
                        compiler.getTask(
                                null, fm, invalidDiagnostics, options, null,
                                fm.getJavaFileObjectsFromPaths(
                                        List.of(invalidSource))).call());
                boolean hasErrors = invalidDiagnostics.getDiagnostics().stream()
                        .anyMatch(d -> d.getKind() == Diagnostic.Kind.ERROR);
                System.out.println("invalid compiled=" + invalidCompiled);
                System.out.println("diagnostic error=" + hasErrors);
            }
        } finally {
            // Clean up temp files after file managers and class loader are closed.
            try (var paths = Files.walk(scratch)) {
                for (Path p : paths.sorted(Comparator.reverseOrder()).toList()) {
                    Files.deleteIfExists(p);
                }
            }
        }
    }
}
```

### 8.1. Running the program

In the directory containing the file above, JDK 17 or newer is required:

```bash
javac --release 17 RuntimeCompilerDecisionDemo.java
java RuntimeCompilerDecisionDemo
```

**Exact stdout verified in testing on a JDK with a compiler:**

```text
reflection=10
intercepted=apply
proxy=10
proxy calls=1
compiler available=true
compiled=true
new class=GeneratedPriceRule
generated=17
same interface=true
invalid compiled=false
diagnostic error=true
```

In testing, both the initial `javac` command and `java` exited with exit code **0**. The temporary directory was created outside the project and cleaned up before the program finished. If you run on a runtime image **without a compiler provider**, the program will print `compiler available=false` and throw an `IllegalStateException` with a message, instead of silently treating compilation as successful.

### 8.2. Explaining the output and technical boundaries

**`reflection=10`:** `Class.forName` loads/obtains the already-compiled `ExistingRule`, Reflection creates an instance with factor 2 and invokes the `apply(5)` method. No new compiler is involved.

**`intercepted=apply` and `proxy=10`:** JDK Proxy invokes `InvocationHandler` before delegating to `ExistingRule(2)`. The handler counts exactly one `apply` call in a single-threaded scenario. The `int[] intercepted` variable in the example is only for sequential observation, **not** a production thread-safe counter.

**`compiler available=true`:** The JVM is running with a JDK containing a compiler provider. This is an **environment check**, not a guaranteed state in every deployment.

**`compiled=true`:** `JavaCompiler.CompilationTask.call` compiles the `GeneratedPriceRule.java` source into `GeneratedPriceRule.class` inside the temporary `classes` directory. At this point, we only know compilation succeeded, **not** whether calling the class is business-correct.

**`new class=GeneratedPriceRule`, `generated=17`:** `URLClassLoader` sees the output folder, `Class.forName` loads the new class, the public constructor is invoked, and `apply(5)` executes the `5 * 3 + 2` logic.

**`same interface=true`:** The generated class is assignable to `RuntimeCompilerDecisionDemo.PriceRule` because the compiler checked the implementation and the generated class's loader references the same interface from the parent loader. Proper class loader design is critical; two classes with the **same binary name but different defining loaders** can still be two different JVM types.

**`invalid compiled=false` and `diagnostic error=true`:** The test intentionally compiles syntactically invalid source. `CompilationTask.call()` returns `false`; `DiagnosticCollector` receives at least one `ERROR` diagnostic. The example only prints booleans, not error counts or messages, to avoid depending on wording differences across compiler versions.

### 8.3. Why is the source written in the default package?

To keep the example runnable with a single `javac` command without requiring a `src/main/java/...` directory tree, both the outer class `RuntimeCompilerDecisionDemo` and the generated class `GeneratedPriceRule` are in the **default package**. This is a choice for a **laboratory**, not a production architecture pattern.

In a real project:

- Place generated types in an appropriate **named package**, with the corresponding package declaration and source path.
- Do not assume the classloader sees all classes from the unnamed module or module path.
- Do not arbitrarily generate binary names that collide with existing classes.
- Manage class names/versioning/loaders under your system's own namespace.

If generated source needs to use types belonging to named modules, you may need `--module-path`, `--add-modules`, or valid Java compiler/`module-info` configuration, not just `-classpath`.

## 9. Common errors at the compilation step

### 9.1. `getSystemJavaCompiler()==null`

Symptom:

```text
compiler available=false
```

The cause may be an environment containing only runtime components, a custom `jlink` image without `jdk.compiler`, or a compiler provider that cannot be found. Solutions:

- Verify that the deployment has an appropriate compiler provider.
- Use a JDK/runtime image containing `jdk.compiler` if runtime compilation is required.
- If you cannot bring the compiler into production, consider **compiling ahead of time** and deploying classes as plugins.
- In named modules, configure the module graph explicitly for the `java.compiler` API and the corresponding provider.

**Do not** conclude that the Java source is wrong when you have not even obtained the compiler yet. The sample code checks for null **before** any compilation task.

### 9.2. `CompilationTask.call()==false`

A source with syntax errors, missing types, or access violations will cause the compiler to report errors. `DiagnosticCollector` helps retrieve them:

```java
// Snippet used after calling compiler.getTask(...).
for (Diagnostic<? extends JavaFileObject> d :
        diagnostics.getDiagnostics()) {
    System.out.println("kind=" + d.getKind());
    System.out.println("line=" + d.getLineNumber());
    System.out.println("column=" + d.getColumnNumber());
    System.out.println("message=" + d.getMessage(null));
}
```

This is a **snippet** using an existing `diagnostics` variable. You should handle `ERROR`/`WARNING`/`MANDATORY_WARNING` according to policy, preserving file/line information if displaying to developers. When logging in production, avoid putting full source code or secrets into error messages.

**Do not proceed with `Class.forName("Generated...")` when compilation has failed.** It might load an old class of the same name from the classpath and produce misleading results, or throw `ClassNotFoundException`.

### 9.3. Compilation succeeds but loading fails

Common errors:

| Error | Layer | Typical cause |
| --- | --- | --- |
| `ClassNotFoundException` | Load | Loader does not point to the directory with the generated `.class`, wrong binary name/package |
| `NoClassDefFoundError` | Link/load dependencies | Dependent class of the generated code is not present during loading/execution |
| `ClassCastException` | Cast instance | Generated type does not actually implement the exact **class identity** of the interface used by the caller |
| `IllegalAccessException` | Reflection instantiation | Constructor/class is not public or caller lacks sufficient access |
| `NoSuchMethodException` | Reflection instantiation | No public no-arg constructor as expected by the code |
| `LinkageError` | JVM linking | Binary incompatibility, duplicate definition in the same loader, classfile/module inconsistency |
| Exception from generated method | Runtime invocation | Business logic bug, unrelated to whether `CompilationTask.call()` succeeded |

The compiler checks dependencies in the **classpath/module path at compile time**; the JVM checks/loads dependencies in the **loader/module graph at runtime**. Those two environments must be designed to be compatible. Compilation success **does not rule out** runtime linkage errors.

### 9.4. Using the wrong binary name and source filename

A source declaring `public class GeneratedPriceRule` usually needs the file `GeneratedPriceRule.java`; after compilation, the binary name to load is `GeneratedPriceRule` if there is no package, or `com.example.GeneratedPriceRule` if it has `package com.example;`.

Do not pass the file path `classes/GeneratedPriceRule.class` as an argument to `Class.forName`; that API expects a **binary class name**.

### 9.5. Class loader still holds the old version

The same class name loaded by the same defining class loader has only one definition. If version A of `GeneratedPriceRule` has already been loaded, recompiling source A into B and overwriting the file on disk **does not** mean the running class object changes its method body.

One versioning design approach is to use a new loader for version B, swap the reference to the current implementation, and **release references to the old loader** when no longer in use. This is a class-loader isolation strategy, not an automatic feature of `JavaCompiler`.

## 10. Important security risks when compiling at runtime

### 10.1. JavaCompiler is not a sandbox for user code

**Do not use `JavaCompiler` to run arbitrary Java source submitted by untrusted users directly inside the server's JVM.** Loaded and executed code can call filesystem, network, process APIs, thread APIs, or access data that the application has permissions for; building through JSR 199 does not automatically restrict those permissions.

`"-proc:none"` only disables annotation processing in the compilation task. It **does not** verify that the source is safe, does not block class initializers, does not block dangerous instructions when the generated class is executed, and does not create an isolation boundary.

If you need to run user-written code, consider a **true isolated execution environment** with appropriate CPU, RAM, time, filesystem, network, account/privilege limits, and process/container isolation. In-process Java with the server's privileges is **not** a strong enough security measure for arbitrary code.

### 10.2. Source injection from templates

For example, a system concatenates a user string directly into a method body:

```java
// COUNTEREXAMPLE: untrusted input can become Java source.
String generated = "public int apply(int x) { return "
        + userExpression + "; }";
```

The code above is a **contraindicated snippet** if `userExpression` comes from outside without constraints. An attacker can manipulate syntax, inject statements/imports/classes, or produce source with side effects. Even though the compiler reports errors when a payload has invalid syntax, the compiler **does not guarantee that a syntactically valid payload is safe**.

Safer approaches:

1. **Do not** expose a free-form Java source writing surface when unnecessary.
2. Use a **DSL/AST whitelist** with a controlled set of operations, identifiers, and types.
3. Generate source from a valid AST, avoiding raw string concatenation.
4. Reject constructs outside the allowed domain and set resource limits.
5. Only load/run code in an environment with appropriate security policies.
6. Log/record diagnostics according to the principle of avoiding sensitive data exposure.

### 10.3. Annotation processors and the compilation process

Annotation processors can run during the compile step if the environment/options allow it; they are real code, not just metadata. For example, use `-proc:none` to disable processors when not needed.

However, **do not treat `-proc:none` as a sandbox mechanism**: it only addresses one execution source during the build process. Once loaded, the generated class can still perform any behavior permitted by the JVM and environment.

### 10.4. Class loading and conflicting class names

Do not allow untrusted source to choose a `java.*` package, class names colliding with application internals, or loader paths that the system does not control. Parent-first delegation and package/module constraints help mitigate some risks, but **do not** replace allowing only trusted code and configuring isolation.

Beyond security, class name collisions cause inconsistent behavior: a loader may return an already-loaded class from the parent instead of the new class. In that case, the caller thinks it is running the new version while actually running the old version.

## 11. Managing class loaders, resources, and speed

### 11.1. Do not compile on every request unless there is a special reason

Runtime compilation has costs:

- Parsing source and type checking.
- Querying dependencies across classpath/module path.
- Generating bytecode, writing/reading files or byte buffers.
- Defining/linking/verifying the class.
- JIT warm-up and metadata initialization after use begins.

If a rule is called millions of times but only changes on deployment, compiling **once** and caching the object/method handle is usually more sensible than compiling on every request.

A possible strategy is:

```text
Validated input schema/config
        |
        v
Stable key = hash(source + options + dependency version)
        |
        +-- cache hit --> reuse generated instance/class
        |
        +-- cache miss --> compile --> validate --> load --> cache
```

**Do not cache solely by a name like `"GeneratedRule"`** when the source, compiler options, or dependency versions can change. Cache by an explicit identity to avoid using an implementation that does not match the spec.

### 11.2. Do not forget to close resources

In the runnable example:

- `StandardJavaFileManager` uses `try-with-resources`.
- `URLClassLoader` is closed after use.
- Temp files are deleted in `finally`.
- The generated source content is trusted, not based on user data.

In production, **closing `URLClassLoader` does not mean classes are unloaded immediately**. The JVM can only unload classes/loaders when no strong references remain and GC conditions are met. Keeping static caches, `ThreadLocal`, thread context class loaders, scheduled tasks, event listeners, or `MethodHandle`s referencing the generated class can keep the loader alive for a long time. Compiling thousands of versions without lifecycle management can cause metaspace/memory growth.

### 11.3. Creating classes in memory: when is it worth using?

For high compilation volumes, you can implement custom:

- `SimpleJavaFileObject` representing source in RAM.
- `ForwardingJavaFileManager` writing bytecode into a `ByteArrayOutputStream`.
- A class loader calling `defineClass` from bytes.

This avoids filesystem I/O, but increases failure branches and responsibility for managing binary names, dependent classes, resources, class loader identity, and caching. For an occasional build task, a **filesystem-based example** is usually easier to diagnose.

### 11.4. Do not ignore classpath and module path

The simple example program runs on a regular classpath. For JPMS applications:

- A module that wants to **call the `javax.tools` API** usually declares `requires java.compiler;`.
- The compiler provider is usually supplied by `jdk.compiler`; the runtime image/module graph must contain sufficient components.
- Generated classes using types from named modules may need compiler options such as `--module-path`, `--add-modules`, and proper source/package design.
- When loading the generated class, runtime loader/module visibility still needs to be valid; compiler options do not guarantee all module access at runtime.
- `--release 17` sets the API/language target, and does not automatically guarantee that dependent application classes on the classpath are fully compatible with every runtime environment.

## 12. Decision table by real-world requirement

| Real-world requirement | Usually suitable choice | Why |
| --- | --- | --- |
| Read annotations and invoke methods of a pre-compiled plugin | Reflection | Method already exists, just needs discovery and invocation |
| Need to invoke a method by a name selected in configuration | Reflection or MethodHandle | No new Java source |
| Add logging/authorization to a service interface | JDK Proxy or decorator | Intercept calls through an existing interface |
| Select a registered implementation at runtime | Factory/strategy/DI; Reflection can be used to load | No need to generate new bytecode |
| Compile a new implementation with many methods from an internal schema | `JavaCompiler` | Need a new, type-checked Java class |
| Integration API requires a concrete subclass with new code | `JavaCompiler` or bytecode generator | JDK Proxy does not subclass regular classes |
| Simple formula `x*rate+offset`, data changes continuously | Function/config; no compilation needed | Compiler has large unnecessary overhead |
| Source code entered by untrusted users | **Do not run in-process** using only `JavaCompiler` | Compiler is not a sandbox |
| Want to reuse lambda/functional behavior instead of generating source | Lambda, strategy, MethodHandle | Lighter and easier to test |
| Only need an existing type-safe Java API, types known at build time | Normal Java call | Reflection/proxy/compiler may all be overkill |
| Need to rebuild plugins across multiple runtime versions | `JavaCompiler` + loader isolation/caching/versioning | Need to manage lifecycle, dependencies, and class identity |
| Need to add a method to an **already-loaded class** | Not directly solved by the three APIs above | Need to consider instrumentation/hot-swap/new architecture |

### 12.1. Three-question rule

1. **Does the code already exist?** If yes, prefer regular APIs, Reflection, MethodHandle, or a factory to access/dispatch.
2. **Is there a suitable interface for interception/delegation?** If yes, JDK Proxy or decorator is usually enough.
3. **Is a new Java source/bytecode implementation truly needed?** If yes, evaluate `JavaCompiler` along with compiler availability, class loaders, performance, and security.

Merely answering “yes” to question 3 is a **condition to consider the compiler**, not a mandate to use the compiler. Bytecode generation or build-time codegen can be used depending on the problem.

## 13. Anti-patterns and how to fix them

### 13.1. “User tweaks a formula slightly, so recompile the Java class”

If it is just a calculation `amount*factor+offset`, you can use an object holding two parameters:

```java
// Complete class-level Java example without main().
public final class ConfigurablePriceRule {
    private final int factor;
    private final int offset;

    public ConfigurablePriceRule(int factor, int offset) {
        this.factor = factor;
        this.offset = offset;
    }

    public int apply(int amount) {
        return amount * factor + offset;
    }
}
```

This avoids the compiler and classloader completely. Only switch to code generation if benchmarks and schema characteristics show a clear benefit.

### 13.2. “Use Reflection to generate a new body”

Reflection only discovers/calls existing bytecode. If you need a new `public int apply(int){return ...;}` that no class provides yet, there must be an implementation-creation step (compiling source, generating bytecode, or using an appropriate closure/strategy). `Method.invoke` does not accept a Java source string.

### 13.3. “Proxy can replace any class”

JDK Proxy only implements interfaces; passing a non-interface concrete class to `Proxy.newProxyInstance` is wrong. If the caller needs a subtype of a concrete class, consider a compiled public non-final subclass or an appropriate subclass generation tool. You cannot bypass `final` or Java access control.

### 13.4. “Compilation succeeded means the plugin runs safely”

Valid source can still:

- Throw exceptions during execution.
- Call dangerous APIs.
- Fail to find dependencies when loaded in another loader.
- Return incorrect business results.
- Cause memory leaks through loader references.

Compilation tests must be followed by **load tests, type checks, behavior tests, and security boundaries**.

### 13.5. “With the same class name, the JVM automatically updates the class when the .class file changes”

After a loader has defined a class, replacing the file on disk does not automatically change the definition in the JVM. You need an explicit loader/version lifecycle or an architecture that does not rely on hot code replacement.

### 13.6. “Let the compiler find all dependencies on its own”

The compiler uses **configured classpath/module path**, which is not necessarily the same as the class loader that runtime will use. Pass the right options, place generated source in the right package, and verify the class identity of shared interfaces.

### 13.7. “When diagnostics are empty, compilation definitely succeeded”

You must check the Boolean returned by `CompilationTask.call()`; the diagnostic collector is a channel for reporting issues, not a confirmation source replacing the return status. Compilation failures can appear in many forms, including file manager/compiler exceptions. When compilation succeeds, you still need to check class loading and behavior.

## 14. Checklist for deploying `JavaCompiler` at scale

Once you have decided `JavaCompiler` is needed, proceed in order:

1. **Lock down the plugin contract:** interface/abstract base class, method signatures, validation rules, and return types.
2. **Lock down the generation source:** trusted template or AST/DSL whitelist; do not concatenate arbitrary raw input into Java source.
3. **Set stable binary names and packages:** avoid colliding with classes from the parent loader and verify valid source filenames/packages.
4. **Check the compiler provider:** `ToolProvider.getSystemJavaCompiler()`, module/runtime image, and target Java version.
5. **Prepare compiler options:** `-encoding`, `--release`, `-classpath`/`--module-path`, `-d`, and `-proc:none` when annotation processing is not needed.
6. **Collect diagnostics:** `DiagnosticCollector`, record kind/file/line/column/message appropriately, avoid leaking sensitive source.
7. **Check compilation result:** `Boolean.TRUE.equals(task.call())`; stop if false.
8. **Load with an appropriate loader:** parent can see shared interfaces, do not define the same binary name multiple times in the same loader.
9. **Verify type:** `expectedInterface.isAssignableFrom(generatedType)` before casting; invoke a valid constructor.
10. **Test behavior:** happy path, boundaries, exceptions, performance, limit on the number of classes.
11. **Cache with the right key:** source hash + compiler options + dependency/version; bound cache size and lifecycle.
12. **Close/clean up resources:** file manager, classloader, temp files when no longer in use; control strong references.
13. **Set security boundaries:** do not run arbitrary user Java with application privileges; isolate if required.
14. **Monitor operations:** compilation latency, errors by diagnostic kind, loader/metaspace growth, and number of live versions.

Recognize that **`JavaCompiler` is a real compiler**. It does not merely add a bit of overhead to a call: using it turns the runtime application into a system with a **build pipeline, dependency resolution, and class loading** right in production. It is only worth doing when the benefit of generating new code is commensurate.

## 15. Self-check exercises

**Question 1.** A system already has `CreditRule` and `DebitRule` on the classpath. Configuration selects the class name at runtime. Is `JavaCompiler` needed?  
**Answer:** No. Use a factory/DI or Reflection/MethodHandle to select an already-compiled class.

**Question 2.** You want to count the number of calls to `OrderService.submit` through the `OrderService` interface without modifying the implementation. What should you choose?  
**Answer:** JDK Proxy or decorator; `InvocationHandler` intercepts and then delegates. No need to compile new source.

**Question 3.** A framework must generate a class `implements TransformationRule` containing a new method body built from a valid AST. Which API can be used?  
**Answer:** `JavaCompiler` to generate Java source, compile to `.class`, and load; or choose a bytecode generator if appropriate. Validate input and class loader.

**Question 4.** `ToolProvider.getSystemJavaCompiler()` returns `null`. Can `getTask` be called?  
**Answer:** No. A compiler provider is needed, usually from the JDK module `jdk.compiler`; or change the architecture to ahead-of-time build.

**Question 5.** `JavaCompiler` is available, but generated source references `PriceRule` and the compiler cannot find it. Why?  
**Answer:** The compile classpath/module path is missing the dependency/shared interface or the package/visibility is wrong. Configure the class and module search paths.

**Question 6.** `CompilationTask.call()` returns `false`. Should you try to load `GeneratedPriceRule`?  
**Answer:** No. Read diagnostics and fix the source/options; loading immediately may pick up an old class or throw `ClassNotFoundException`.

**Question 7.** A generated class has the same name `com.example.Rule` as a class already loaded by the parent loader. When calling `Class.forName` with a child `URLClassLoader`, will you definitely get the new version?  
**Answer:** No. Parent-first delegation may return the existing class. Proper namespace/versioning/loader design is needed.

**Question 8.** When using `-proc:none`, is it already safe to compile and run Java source submitted by unknown users in the same JVM?  
**Answer:** No. That option only disables annotation processors; compiled source is still arbitrary code with the JVM process's privileges. Isolation and a different security model are needed.

**Question 9.** You want a new implementation that only differs by changing factor 2 to 3. Should you default to compiling a new class?  
**Answer:** No. Constructor parameters/configurable strategy are easier. Compile only when there is a worthwhile specialization reason.

**Question 10.** Why can source compile successfully yet casting the object to the application's interface still fail?  
**Answer:** Class loaders can define **two different classes with the same binary name** for the interface; class identity in the JVM includes the defining loader. Choose a valid shared parent loader for the interface.

**Question 11.** Does JDK Proxy create a new class at runtime?  
**Answer:** Yes. It creates a proxy class implementing interfaces. However, it does not compile arbitrary Java source and does not subclass an arbitrary concrete class.

**Question 12.** How do `java.compiler` and `jdk.compiler` differ?  
**Answer:** `java.compiler` contains the API/tool contracts such as `javax.tools.JavaCompiler`; `jdk.compiler` provides the `javac` implementation in the JDK. Having the API present does not guarantee a working provider in every runtime image.

**Question 13.** After recompiling `GeneratedRule.java`, will a method on an already-loaded instance change behavior immediately?  
**Answer:** No. Replacing the classfile does not change the already-loaded class definition in the same loader. You need a versioning/new-loader architecture or an appropriate instrumentation mechanism.

**Question 14.** Does `URLClassLoader.close()` immediately free the metaspace of generated classes?  
**Answer:** No. Closing releases loader-related resources, but class unloading depends on remaining live references and GC conditions. Manage caches and lifecycles.

## 16. Summary and references

**Selection summary:**

```text
Already have code/class to call?
    |
    +-- Yes --> Static call / Factory / Reflection / MethodHandle
    |
    +-- Want to intercept an interface? --> JDK Proxy / Decorator
    |
    +-- Truly need a new Java class?
            |
            +-- Yes --> JavaCompiler or bytecode generation
            |
            +-- No --> Use data, strategy, function/lambda
```

**Key points to remember:**

- Reflection **does not create new Java method bodies**; it discovers and invokes existing code.
- JDK Proxy **does create a proxy class**, but only implements interfaces and routes calls to `InvocationHandler`; it does not accept arbitrary Java source.
- `JavaCompiler` produces bytecode from new Java source. After compilation, **class loading, type checking, instantiation, and tests** are still required.
- In the JDK, the provider usually comes from `jdk.compiler`; `ToolProvider.getSystemJavaCompiler()` can return `null` if the runtime image lacks a provider.
- `CompilationTask.call()` and `DiagnosticCollector` must be handled explicitly; do not load classes when compilation fails.
- `--release` is not a sandbox, `-proc:none` does not make arbitrary source safe; a class loader boundary is also **not** a security sandbox.
- Compilation cost, class loader identity, and memory management are important architectural factors.
- Choose the compiler based on **the need to create a new implementation**, not just because the system has “runtime” in the feature name.

**Official documentation (Java 17):**

- [`javax.tools.JavaCompiler` — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/JavaCompiler.html): `getTask`, `CompilationTask`, and compiler contracts.
- [`javax.tools.ToolProvider` — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/ToolProvider.html): `getSystemJavaCompiler()`.
- [`javax.tools.DiagnosticCollector` — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/DiagnosticCollector.html): diagnostic warnings/errors.
- [`javax.tools.StandardJavaFileManager` — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/StandardJavaFileManager.html): managing source/output files.
- [`java.lang.reflect.Proxy` — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Proxy.html) and [`InvocationHandler`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/InvocationHandler.html): JDK dynamic proxies.
- [`java.lang.reflect.Method` — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Method.html): reflection invocation.
- [`java.net.URLClassLoader` — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html): loading classes from URLs, closing resources, and class loading limits.
- [`javac` Command — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html): `--release`, `-classpath`, `--module-path`, `-proc:none`, `-d`.

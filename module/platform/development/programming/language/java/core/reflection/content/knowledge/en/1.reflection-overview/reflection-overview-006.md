# When to Use Reflection vs. Direct Calls in Java?

In Java, **direct calls** are the default choice when a program knows the types and APIs it needs at compile time. **Reflection** is the mechanism for inspecting a class's structure and accessing constructors, methods, fields, or annotations **while the program is running** through APIs such as `Class`, `Constructor`, `Method`, and `Field` in `java.lang.reflect`.

Both approaches can produce the same behavior. The decision comes down to **how dynamic the requirement is**: do you genuinely need to discover class names, methods, or metadata at runtime? Reflection solves dynamic problems, but it increases maintenance cost, reduces compile-time type checking, and introduces additional access restrictions.

## 1. Distinguishing the Mechanisms

- **Direct calls:** writing `service.execute()`, `new Service()`, or calling through an interface. The compiler checks that the method exists, that parameter/return types are valid, and that access permissions allow it. IDEs can find references, rename symbols, and refactor more reliably.
- **Reflection:** obtaining a class descriptor (`Class<?>`), looking up a member by name/signature at runtime, and invoking via `Method.invoke(...)` or instantiating via `Constructor.newInstance(...)`. Name and signature mistakes usually surface only at runtime.
- **Polymorphism is not reflection:** `Formatter formatter = ...; formatter.format(text);` is still a regular Java call. The JVM can select the implementation at runtime via virtual dispatch without needing `Method.invoke`.
- **Having a `Class<?>` does not mean you must invoke methods via reflection:** `SomeType.class` and `object.getClass()` only retrieve type information; use only the introspection capabilities you truly need.

A reflective call does not automatically bypass `private` restrictions, Java module boundaries, or access permissions. Access checks still apply.

## 2. Which Approach Fits Which Situation?

| Situation | Preferred Choice | Reason |
| --- | --- | --- |
| Class, constructor, method, and signature are known when writing code | Direct call | Type-safe, easy to refactor, easy to trace call flows |
| Multiple ways to implement the same interface contract | Interface + polymorphism, factory, or dependency injection | Flexibly selects implementations without probing method names |
| Must read annotations, fields, and methods of many previously unknown types | Reflection in the infrastructure/framework layer | Metadata can only be fully determined at runtime |
| Need to load an implementation from configuration or an external plugin | `ServiceLoader` or controlled reflection | The implementation name may be unknown at compile time |
| Want to call a private method from business code or tests | Prefer redesigning API/separating responsibilities | Avoids tight coupling to implementation details and breaking encapsulation |
| Very hot loop calling a method repeatedly | Prefer direct calls after measurement | Avoids lookup/invoke overhead and type conversions |
| Accessing an API of a dependency already referenced in source code | Direct call | Reflection adds fragility without providing dynamic benefit |

**Rule of thumb:** introduce reflection only where the system genuinely has to handle information unknown at compile time; let the rest communicate through explicit types or interfaces.

## 3. Example: Same Call, Two Ways to Execute It

Create the file `CallChoiceDemo.java`:

```java
import java.lang.reflect.Method;

public class CallChoiceDemo {
    public static class GreetingService {
        public String greet(String name) {
            return "Hello, " + name;
        }
    }

    public static void main(String[] args)
            throws ReflectiveOperationException {
        GreetingService service = new GreetingService();

        // Direct call: the compiler knows the type and signature.
        String direct = service.greet("An");

        // Reflection: look up the method by name/signature at runtime.
        Class<?> type = service.getClass();
        Method greetMethod = type.getMethod("greet", String.class);
        Object dynamic = greetMethod.invoke(service, "An");

        System.out.println("Direct: " + direct);
        System.out.println("Reflection: " + dynamic);
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac CallChoiceDemo.java
java CallChoiceDemo
```

Output:

```text
Direct: Hello, An
Reflection: Hello, An
```

Analysis:

1. `service.greet("An")` is checked by the compiler: renaming `greet` without updating the call site produces a compile error.
2. `getMethod("greet", String.class)` finds only a **public method** with the exact `String` parameter signature, including inherited public methods. If the name/signature does not exist, the program receives `NoSuchMethodException` at runtime.
3. `Method.invoke(service, "An")` returns `Object` (or `null` if the method returns `void`). Therefore, the caller may need to check and cast when the result type is known.
4. If code inside `greet` throws an exception, `invoke` wraps that exception in `InvocationTargetException`; inspect `getCause()` to see the original error. Access failures can produce `IllegalAccessException`.

In this example, reflection brings **no benefit**: `GreetingService` and `greet` are clearly known from the start, so a direct call should be used.

## 4. When Reflection Has a Valid Reason: The Class Is Chosen at Runtime

A plugin system might receive an implementation name from configuration while business logic knows only a shared interface. You can use reflection at the **plugin initialization point**, then call directly through the interface afterward.

Create the file `RuntimeFormatterDemo.java`:

```java
import java.util.Locale;

public class RuntimeFormatterDemo {
    public interface Formatter {
        String format(String input);
    }

    public static class UpperFormatter implements Formatter {
        public UpperFormatter() {
        }

        @Override
        public String format(String input) {
            return input.toUpperCase(Locale.ROOT);
        }
    }

    public static void main(String[] args)
            throws ReflectiveOperationException {
        // In a real application, this value may come from trusted configuration.
        String className = System.getProperty(
                "formatter.class", UpperFormatter.class.getName());

        Class<?> rawClass = Class.forName(className);
        Class<? extends Formatter> implementation =
                rawClass.asSubclass(Formatter.class);
        Formatter formatter =
                implementation.getDeclaredConstructor().newInstance();

        // From here on it is normal polymorphism, with no Method.invoke call.
        System.out.println(formatter.format("reflection"));
    }
}
```

Run:

```bash
javac RuntimeFormatterDemo.java
java RuntimeFormatterDemo
```

Output:

```text
REFLECTION
```

Points to understand:

- `Class.forName(className)` loads/finds the class by the name known at runtime (with this form, class initialization may also occur). The class must be on the appropriate classpath/module path.
- `asSubclass(Formatter.class)` verifies that the class is compatible with `Formatter`; if not, `ClassCastException` is thrown.
- `getDeclaredConstructor().newInstance()` requires a suitable no-argument constructor that is accessible from the caller. If missing, `NoSuchMethodException` occurs; if the constructor throws an error, it is wrapped in `InvocationTargetException`.
- Once the `Formatter` is created, calling `formatter.format(...)` through the interface is sufficient. There is no need to keep looking up and invoking the method via reflection on every operation.
- Class names taken from untrusted sources can lead to loading/initializing unintended code. Applications must restrict allowed providers, control dependencies, and never treat interface casting as a security mechanism.

In cases where the system already knows the list of implementations, a **factory/registry** mapping names to `Supplier<Formatter>` is even simpler. If a standard plugin mechanism is needed, **`ServiceLoader<Formatter>`** discovers providers through service configuration without manually wiring class names and constructors in business code. Dependency injection frameworks also typically handle implementation selection better than hand-rolled reflection.

## 5. Situations Where Reflection Is Commonly Used

### Reading Metadata and Building General-Purpose Tools

- Frameworks can scan annotations to configure dependency injection, mapping, serialization, or validation.
- Debuggers, test runners, and API inspection tools can list methods, fields, constructors, and annotations from classes that only appear at runtime.
- General-purpose data conversion libraries may have to handle domain types not explicitly enumerated within the library itself.

For example, a library can iterate over `type.getDeclaredFields()` to read field metadata and decide how to map data. This differs from business logic that already knows `customer.getName()`: in the latter case, a direct getter is the clearer solution.

### Plugins and Extensions

When an implementation is provided by a plugin after compile time, the application may need to load the class, verify its contract, and create an instance at runtime. Reflection is useful **at the integration boundary**, while ongoing operations should go through a defined interface. If the runtime varies method or type names without a common contract, consider an adapter or a stable protocol rather than scattering method-name strings throughout the system.

### Alternatives to Consider Before Using Reflection

- **Interfaces/polymorphism:** instead of branching by class name and invoking methods dynamically.
- **Factories, registries, dependency injection:** instead of constructing objects by class name when the set of implementations can be declared.
- **`ServiceLoader`:** Java's standard provider/plugin mechanism.
- **Compile-time annotation processing:** when metadata/code can be generated early instead of scanning with reflection on every run.
- **`MethodHandle` / `MethodHandles.Lookup`:** a dynamic invocation tool with clearer signature typing in some advanced scenarios; still requires access checks and performance measurement, not a mandatory shortcut.

## 6. Cost, Access Permissions, and Safety

**Type checking and maintenance.** Direct calls let the compiler catch renames or parameter changes early. With `getMethod("save", ...)`, member names as strings are not reliably refactored; errors appear only at runtime. Centralize member-name strings in one place, validate results, and maintain integration tests for dynamic paths.

**Performance.** Reflection carries member-discovery, access-checking, dynamic-invocation, and potential boxing/unboxing costs. Actual overhead depends on the JDK version, code hotness, and JVM optimizations: do not claim every reflective call is slower by a fixed factor. When reflection is unavoidable, **look up `Method`/`Constructor` once and reuse it** where appropriate, avoiding `getMethod` inside loops; use proper benchmarks such as JMH before optimizing sensitive code.

**Public, private, and Java modules.**

- `getMethod(...)` searches public methods; `getDeclaredMethod(...)` searches methods declared directly in that class, including non-public ones, yet **finding one does not mean it can be invoked**.
- `setAccessible(true)`/`trySetAccessible()` can be restricted by access checks and module rules. Java 17+ enforces strong encapsulation on many packages/modules; opening access can fail with `InaccessibleObjectException` or `trySetAccessible()` returning `false`.
- In the Java Platform Module System, `exports` allows using a package's public API under module rules; `opens` supports deep reflection into a package for authorized modules. Open only packages genuinely needed by frameworks and prefer clear public contracts.
- Do not build business functionality that depends on private fields/methods of third-party libraries; they can change without notice.

**Exceptions and diagnostics.** Beyond `NoSuchMethodException`, distinguish `ClassNotFoundException`, `IllegalAccessException`, `InstantiationException`, `InvocationTargetException`, and `ClassCastException` by execution step. When logging `InvocationTargetException`, preserve the original cause. Including the expected class/method/signature in error messages speeds up configuration troubleshooting.

**Safety and deployment.** Never take class/method names directly from untrusted input and execute them arbitrarily. With native image or closed-world code-analysis environments, reflective access may require declaring metadata or registration entries suited to the runtime/framework; verify this at build time and run real tests on the deployment target.

## 7. Decision Workflow

1. **Are the class name and method known at compile time?** Use a direct call.
2. **Do you only need to swap implementations by condition/configuration?** Create an interface + factory/DI/`ServiceLoader`; business calls remain direct through the interface.
3. **Do you need to read structure or annotations of previously unknown types?** Use bounded reflection, isolate dynamic access in an adapter/infrastructure layer, handle errors, and cache metadata if needed.
4. **Must you invoke a method determined at runtime?** Validate the name and signature, check compatibility, handle access/invocation exceptions, and narrow the reflective call site.
5. **Are you opening a private member just "for convenience"?** Re-examine the API boundary or design before resorting to deep reflection.
6. **Suspect performance, encapsulation, or module issues?** Write tests/benchmarks on the actual target runtime and choose the minimum level of dynamism.

### Self-Check on Making the Choice

- Calling `orderService.submit(order)` on a service whose type is already known: **direct call**.
- Selecting a `PaymentProcessor` from available providers: **interface + factory/DI**, no `Method.invoke` needed.
- Writing a library that inspects annotations on application classes unknown to the library at compile time: **reflection is reasonable**.
- Loading an implementation installed after build time: use **`ServiceLoader` or controlled dynamic instantiation**, then call through an interface.
- Wanting to modify a dependency's private field to avoid creating a proper API: **avoid reflection**, prefer proper design/test seams.

**Conclusion:** Reflection is a tool for solving dynamic runtime requirements. Direct calls and polymorphism remain appropriate for most business logic; reflection should sit behind a small boundary with clear validation and error handling.
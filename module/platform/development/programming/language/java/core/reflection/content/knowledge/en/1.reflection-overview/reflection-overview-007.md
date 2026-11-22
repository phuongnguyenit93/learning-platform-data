# An End-to-End Example: Discovering and Using a Previously Unknown Type

In regular Java, we write `new HelloPlugin(...)` and call `plugin.greet(...)` when the source code already knows the class and method. Reflection solves a different scenario: the application receives **a class name as data at runtime**, then inspects that type, creates an object, and invokes a method. The end-to-end example below puts the entire process into a single runnable program.

## 1. Scenario and Processing Flow

Suppose there is a host program that receives the name of an extension component (plugin) from command-line arguments. The host does not know in advance whether `HelloPlugin` or `LoudPlugin` will be chosen; it only knows the **convention**: the selected class must have a `public (String)` constructor and a `public String greet(String)` method.

~~~text
Class name received at runtime (String)
       │
       ▼
Class.forName(...)                 → Class<?>: type descriptor
       │
       ├── getName(), getSuperclass(), getDeclaredFields()
       ├── getAnnotation(...)      → read metadata
       │
       ▼
getConstructor(String.class)       → Constructor<?>
       │
       ▼
newInstance("Hello")               → Object: actual object
       │
       ▼
getMethod("greet", String.class)   → Method
       │
       ▼
invoke(instance, "Lan")            → return result
~~~

Reflection resides in the `java.lang.Class` and `java.lang.reflect` APIs. `Class<?>` is an object describing **a type**, whereas the `Object` returned by `newInstance` is **an instance of that type**. These two concepts are distinct and both are needed in the example.

## 2. Complete Java 17+ Program

Save all of the following content into **`ReflectionWalkthrough.java`**. Both plugins are placed in the same file as `static nested class`es so it runs standalone without external libraries or JARs. This is a simulated plugin environment; in a real application, the selected class may live in a separate dependency.

~~~java
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.reflect.Constructor;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.lang.reflect.Modifier;
import java.util.Locale;

public class ReflectionWalkthrough {
    @Retention(RetentionPolicy.RUNTIME)
    public @interface ComponentInfo {
        String role();
    }

    @ComponentInfo(role = "greeting")
    public static class HelloPlugin {
        private final String prefix;

        public HelloPlugin(String prefix) {
            this.prefix = prefix;
        }

        public String greet(String name) {
            return prefix + ", " + name + "!";
        }
    }

    @ComponentInfo(role = "loud")
    public static class LoudPlugin {
        private final String prefix;

        public LoudPlugin(String prefix) {
            this.prefix = prefix;
        }

        public String greet(String name) {
            return (prefix + ", " + name + "!")
                    .toUpperCase(Locale.ROOT);
        }
    }

    public static void main(String[] args) throws ReflectiveOperationException {
        String className = args.length == 0
                ? "ReflectionWalkthrough$HelloPlugin"
                : args[0];

        Class<?> type = Class.forName(className);
        System.out.println("Class name: " + type.getName());
        System.out.println("Superclass: " + type.getSuperclass().getName());
        System.out.println("Is interface: " + type.isInterface());

        for (Field field : type.getDeclaredFields()) {
            System.out.println("Field: " + Modifier.toString(field.getModifiers())
                    + " " + field.getType().getSimpleName() + " " + field.getName());
        }

        ComponentInfo info = type.getAnnotation(ComponentInfo.class);
        System.out.println("Role: " + (info == null ? "(none)" : info.role()));

        Constructor<?> constructor = type.getConstructor(String.class);
        Object instance = constructor.newInstance("Hello");

        Method method = type.getMethod("greet", String.class);
        System.out.println("Method: " + method.getReturnType().getSimpleName()
                + " " + method.getName() + "(String)");
        Object result = method.invoke(instance, "Lan");
        System.out.println("Result: " + result);
    }
}
~~~

Compile and run in the directory containing the file:

~~~bash
javac -encoding UTF-8 ReflectionWalkthrough.java
java ReflectionWalkthrough
~~~

Output (stdout):

~~~text
Class name: ReflectionWalkthrough$HelloPlugin
Superclass: java.lang.Object
Is interface: false
Field: private final String prefix
Role: greeting
Method: String greet(String)
Result: Hello, Lan!
~~~

Run with the other plugin name:

~~~bash
java 'ReflectionWalkthrough$LoudPlugin'
~~~

Output:

~~~text
Class name: ReflectionWalkthrough$LoudPlugin
Superclass: java.lang.Object
Is interface: false
Field: private final String prefix
Role: loud
Method: String greet(String)
Result: HELLO, LAN!
~~~

**Note on shells:** Single quotes around a name containing `$` are for Bash/Zsh and PowerShell so the nested class name is passed literally to Java (preventing the shell from expanding `$LoudPlugin`). On Windows CMD you can use `java "ReflectionWalkthrough$LoudPlugin"`. If you simply run `java ReflectionWalkthrough`, the program automatically chooses the default plugin.

## 3. Discovering a Type from a Runtime Name

~~~java
String className = args.length == 0
        ? "ReflectionWalkthrough$HelloPlugin"
        : args[0];
Class<?> type = Class.forName(className);
~~~

- `className` is a configuration/input **string**; the host neither calls `new HelloPlugin(...)` nor references `HelloPlugin.class` to decide the plugin.
- `Class.forName(String)` locates the class by its *binary name* via the corresponding class-loading mechanism and, if needed, initializes the class. If not found, it throws `ClassNotFoundException`; static initialization errors can produce `ExceptionInInitializerError`.
- `Class<?>` means "a `Class` object with an unknown type parameter." The `?` does not turn it into an instance; it represents type information at runtime.
- The binary name of the nested class is `ReflectionWalkthrough$HelloPlugin`. For a standalone class in a package, such as `com.example.plugins.HelloPlugin`, use the fully qualified package name rather than the simple name.
- `getName()` gives the binary name; `getSimpleName()` gives the simple name; `getSuperclass()` gives the direct superclass (which may return `null` for `Object`, interfaces, or certain other cases). `isInterface()` distinguishes interfaces from classes.

Key point: **knowing a name to load a class does not mean knowing the class's API at compile time**. The example still requires a constructor/method convention; Reflection does not automatically guess the meaning of every method.

## 4. Reading Metadata Before Using the Class

The loop in the program:

~~~java
for (Field field : type.getDeclaredFields()) {
    System.out.println("Field: " + Modifier.toString(field.getModifiers())
            + " " + field.getType().getSimpleName() + " " + field.getName());
}
~~~

`getDeclaredFields()` returns fields **declared directly** on the class, including `private` ones; it does not mean the host is allowed to access those fields' values. The returned array has no guaranteed order, so if you need a stable list across multiple fields, sort them by name yourself. In this example each plugin has only one field: `private final String prefix`.

Some common discovery operations:

| Need | API | What to Remember |
|---|---|---|
| Check class name/kind | `getName()`, `getSimpleName()`, `isInterface()` | Type metadata |
| Inspect superclass and interfaces | `getSuperclass()`, `getInterfaces()` | Direct inheritance/implementation relationships |
| Inspect fields declared on the class | `getDeclaredFields()` | Includes non-public fields; excludes inherited fields |
| Inspect public methods including inherited | `getMethods()` | Only public methods visible under this API |
| Inspect directly declared methods | `getDeclaredMethods()` | May include private; excludes inherited methods |
| Find a public method by signature | `getMethod("greet", String.class)` | Name + **parameter types**, does not search by return type |
| Find a public constructor | `getConstructor(String.class)` | Signature must match exactly |
| Read a runtime annotation | `getAnnotation(ComponentInfo.class)` | The annotation must be retained at runtime |

Correspondingly, `getDeclaredMethod(...)` and `getDeclaredConstructor(...)` can find directly declared members even when non-public; **finding them does not guarantee permission to invoke them**. Access permissions are still enforced by Java and the module system.

In the example, the annotation `@ComponentInfo(role = "...")` is declared with `@Retention(RetentionPolicy.RUNTIME)` so it can be read at runtime:

~~~java
ComponentInfo info = type.getAnnotation(ComponentInfo.class);
String role = info == null ? "(none)" : info.role();
~~~

If the annotation is absent, `getAnnotation` returns `null`. If retention is only `SOURCE` or `CLASS`, you cannot expect to read that annotation with the Reflection call above. Annotations provide metadata; by themselves they do not instantiate or activate a plugin.

## 5. Creating an Instance via a Constructor Found at Runtime

~~~java
Constructor<?> constructor = type.getConstructor(String.class);
Object instance = constructor.newInstance("Hello");
~~~

`getConstructor(String.class)` finds a **public constructor taking exactly one `String`**. Missing such a constructor throws `NoSuchMethodException`. If looking for a constructor taking `int`, you must use `int.class` (do not substitute `Integer.class` during signature lookup). `newInstance(...)` actually invokes the constructor, which can execute logic and raise errors.

Because `type` is `Class<?>`, the result is stored in `Object`. Java cannot guarantee at compile time that the object has `greet(String)`. The program must check and invoke the method via Reflection. Do not use the legacy `Class.newInstance()`: that API is deprecated, requires a no-argument constructor, and has unclear exception handling; `getDeclaredConstructor().newInstance()` is the proper replacement when a no-argument constructor is needed.

## 6. Finding and Invoking a Method on an Instance

~~~java
Method method = type.getMethod("greet", String.class);
Object result = method.invoke(instance, "Lan");
~~~

Here `getMethod` selects a public method named `greet` with one `String` parameter. Its return type can be read via `method.getReturnType()`. `invoke` requires a **target object** for an instance method; subsequent arguments are passed to the invoked method. The return value is boxed if primitive, or `null` when the method returns `void`. In the example, `result` is actually a `String`; printing with `println` requires no cast.

For `static` methods, the target object passed to `invoke` can be `null`. If the target has the wrong type or arguments are incompatible or have the wrong count, `IllegalArgumentException` may occur; if the method itself throws an exception, `invoke` wraps it in `InvocationTargetException`. To understand the underlying business cause, inspect `getCause()` on this wrapper.

**Important boundary:** `getDeclaredMethod` or `getDeclaredField` can return private members, yet invoking/reading them is not implicitly permitted. Do not add `setAccessible(true)` as a "mandatory step" of Reflection: in applications using the Java Platform Module System (JPMS), opening deep access also depends on whether the package is `opens` to the calling module; even on the classpath, encapsulation boundaries and access permissions must be respected.

## 7. Common Errors and How to Handle Them

| Symptom | Common Cause | How to Handle |
|---|---|---|
| `ClassNotFoundException` | Wrong binary name, missing JAR/module, class loader cannot see the class | Check the name, classpath/module path, and loader |
| `NoSuchMethodException` | Constructor/method does not exist with the exact name, visibility, or parameter type list | Verify the actual API and signature |
| `InstantiationException` | Cannot create an instance, e.g., attempting to instantiate an abstract class | Choose a concrete class with an appropriate constructor |
| `IllegalAccessException` | Member is not accessible from the call site | Design public APIs/module exports; avoid breaking encapsulation |
| `InvocationTargetException` | Code inside the constructor or method threw an error | Inspect `getCause()` and handle the real cause |
| `IllegalArgumentException` | Incompatible target/arguments passed to `invoke`/`newInstance` | Match exact parameter count and types |
| `ExceptionInInitializerError` | Static initialization of the class failed | Check the static initializer and underlying error cause |

The demo program declares `throws ReflectiveOperationException` to keep the learning flow clear; production programs need to catch errors with context, report which plugin failed and why, and handle runtime errors like `ExceptionInInitializerError` appropriately. Never swallow exceptions and continue as if the plugin loaded successfully.

## 8. From Demo to Real-World Design

**When to use Reflection?** DI frameworks, serializers, testing tools, plugin loaders, and code-structure analyzers often need to discover types/annotations/members at runtime. Yet Reflection trades off several benefits: loss of compile-time type checking, fragility from string names/signatures, module access restrictions, and dynamic lookup/call overhead. Do not choose Reflection just to call a class already clearly known in source code.

When a shared Java contract can be defined, a more stable direction for plugins is an interface:

~~~java
public interface GreetingService {
    String greet(String name);
}
~~~

The snippet above is an **illustrative design fragment**, not a standalone runnable program. When a plugin implements `GreetingService`, the host can use `GreetingService.class.isAssignableFrom(type)` to check compatibility before creating an instance, then cast via `GreetingService.class.cast(instance)` and call `service.greet("Lan")` like normal Java. Do not cast directly from a newly loaded object without verifying the interface; having the same method name does not make a class implement an interface. When discovering contract-based providers on the classpath/module path, `ServiceLoader` is usually more suitable than manually storing class names in configuration.

**Safety boundaries:** Only load plugins from trusted sources; `Class.forName` can trigger class initialization and `newInstance`/`invoke` executes real code, not metadata-only inspection. Never take arbitrary class names from untrusted external users and execute them indiscriminately. When checking performance, measure before optimizing; verified `Class`, `Constructor`, or `Method` objects can be cached instead of looked up repeatedly, provided the cache respects class-loader lifecycles.

## 9. Self-Check on This Example

1. Switch the command-line argument between `ReflectionWalkthrough$HelloPlugin` and `ReflectionWalkthrough$LoudPlugin`. Identify which parts of the host stay unchanged and which parts vary by plugin metadata and behavior.
2. Change `getConstructor(String.class)` to `getConstructor()`. Why does it currently throw `NoSuchMethodException`? Add a no-argument constructor to one plugin and try again.
3. Change `getDeclaredFields()` to `getFields()`. Why does the `prefix` field disappear from the output? Explain the difference between "declared" and "public."
4. Remove `@Retention(RetentionPolicy.RUNTIME)` from `ComponentInfo` and observe `getAnnotation(...)`. Look up the default retention and why the host can no longer read the role.
5. Write another plugin with the same public constructor/method and run it using the new binary name; then intentionally rename `greet` to verify the error and how to diagnose it.

**Key takeaway:** Runtime class name → `Class<?>` for discovery → verify signatures/metadata → `Constructor.newInstance` creates an object → `Method.invoke` invokes behavior. Reflection moves type decisions to runtime, so responsibility for contract verification, error handling, and controlling loaded code sources also shifts to runtime.
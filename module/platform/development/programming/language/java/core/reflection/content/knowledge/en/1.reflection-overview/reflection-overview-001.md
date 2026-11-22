# Reflection in Java: What Is It and What Problem Does It Solve?

Reflection is a mechanism that allows a Java program to **inspect the structure of a data type and manipulate certain members of that type while the program is running**. Instead of only directly calling classes and methods explicitly written in source code, a program can look up information from a `Class<?>` object, find constructors/methods/fields by name or characteristics, and then create objects, invoke methods, or access values when appropriate.

This lesson focuses on **why Reflection exists, how to think about it, the basic usage workflow, and the trade-offs involved**. The goal is to understand when a dynamic mechanism is needed; there is no need yet to use Reflection to reach deeply into `private` members.

## 1. The Problem: Source Code Does Not Always Know Every Type in Advance

In regular Java, developers explicitly write types and calls:

```java
Greeter greeter = new Greeter();
String message = greeter.sayHello("An");
```

The compiler checks that `Greeter` exists and has a `sayHello(String)` method. This is the preferred approach because it is clear, type-checked at compile time, and easy to maintain.

However, there are programs that **only know which class to process at runtime**:

- A library that converts objects to JSON needs to know what properties an actual object has.
- A test runner needs to find methods marked with an annotation and invoke each matching method.
- A dependency injection container needs to find constructors or metadata to create and wire objects together.
- A plugin system may receive a class name or configuration chosen by a user after the program has already been compiled.
- A program inspection tool needs to print class, method, or field names without writing custom code for every single class.

For example, when writing a JSON library, the author cannot know in advance all the `Customer`, `Order`, `Product` ... classes that future applications will pass in. Writing `if/else` branches for every class is not feasible. The library needs a general way to **discover the metadata of any supported type** and process it according to rules.

Reflection solves that exact need: **working with program structure when the concrete structure is only determined at runtime**.

## 2. What Is Reflection?

The Reflection API belongs primarily to:

- `java.lang.Class`: the runtime representation of a Java type and the starting point for discovering metadata.
- `java.lang.reflect`: objects describing members of a type, notably `Constructor`, `Method`, `Field`, `Modifier`.
- `java.lang.annotation` and `java.lang.reflect.AnnotatedElement`: support looking up annotations at runtime when annotations are declared with an appropriate retention.

A regular object represents **data/state**, whereas `Class<?>` represents **information about the type** of that object. For example:

```java
String text = "Hello";
Class<?> type = text.getClass();
System.out.println(type.getName()); // java.lang.String
```

Three common ways to obtain a `Class<?>`:

| Way | When to Use | Notes |
| --- | --- | --- |
| `MyType.class` | When the type is known while writing code | No instance needed; the compiler checks the type name |
| `value.getClass()` | When you already have an object and want to know its actual class | `value` must not be `null` |
| `Class.forName("com.example.MyType")` | When you have the class name as a string at runtime | May throw `ClassNotFoundException`; the single-argument variant may trigger class initialization |

Reflection **does not automatically turn an arbitrary string into Java code**, nor does it mean you are always permitted to access all internal members. It provides metadata along with dynamic operations within the limits of access control, the module system, and the runtime environment.

### Relationship Between Classes, Objects, and Metadata

```text
Compiled code + class loaded by ClassLoader
                      |
                      v
                 Class<?>          (type metadata)
                 /   |   \
                /    |    \
         Constructor Method Field  (member descriptors)
                |       |
                v       v
         Create object  Invoke method / read, write field
```

The same class can produce many instances; they have their own state while sharing information about the type definition. `Class<?>` does not hold an independent copy of each instance's data.

## 3. What Steps Does Reflection Follow?

1. **Identify the type to process**: obtain `Class<?>` from `.class`, `getClass()`, or a class name.
2. **Discover metadata**: read the class name, superclass, interfaces, and annotations; find matching constructors, methods, and fields.
3. **Select a member**: for example, choose the method named `sayHello` with exactly one `String` parameter. The name alone may not be enough because Java allows overloading.
4. **Perform dynamic operations if needed**: create an instance with `Constructor.newInstance(...)`, invoke with `Method.invoke(...)`, or read a field with `Field.get(...)`.
5. **Handle runtime risks**: nonexistent names, wrong signatures, wrong receiver object, missing access permissions, exceptions thrown by the invoked code...

Some commonly used methods:

| Need | Example API | Meaning |
| --- | --- | --- |
| Read type name | `clazz.getName()`, `clazz.getSimpleName()` | Full name or simple name |
| Find a public method | `clazz.getMethod(name, parameterTypes...)` | Also searches inherited public methods |
| Inspect directly declared methods | `clazz.getDeclaredMethods()` | Includes non-public methods declared in the class; does not automatically include inherited ones |
| Find a constructor | `clazz.getDeclaredConstructor(parameterTypes...)` | Matching declared constructor |
| Find a field | `clazz.getDeclaredField(name)` | Field declared in the class |
| Inspect runtime annotation | `clazz.getAnnotation(SomeAnnotation.class)` | Reads an annotation with `RetentionPolicy.RUNTIME` if present |

Distinguishing `getMethod` from `getDeclaredMethod`: the first only searches `public` members (including inherited ones), while the second searches members **declared in the current class** regardless of access level, though finding metadata **does not mean** you are permitted to invoke or access it.

## 4. Java 17+ Example: Finding and Invoking a Method at Runtime

Create a file named **`ReflectionIntro.java`**:

```java
import java.lang.reflect.Method;

public class ReflectionIntro {

    public static class Greeter {
        public Greeter() {
        }

        public String sayHello(String name) {
            return "Hello, " + name + "!";
        }
    }

    public static void main(String[] args) throws ReflectiveOperationException {
        // 1. Get metadata of the class to work with.
        Class<?> type = Greeter.class;
        System.out.println("Class: " + type.getSimpleName());

        // 2. Create an object via the no-argument constructor.
        Object instance = type.getDeclaredConstructor().newInstance();

        // 3. Look up the exact public method sayHello(String).
        Method method = type.getMethod("sayHello", String.class);

        // 4. Invoke the method on the newly created object.
        Object result = method.invoke(instance, "An");
        System.out.println("Method: " + method.getName());
        System.out.println("Result: " + result);
    }
}
```

Compile and run (with JDK 17 or later):

```bash
javac ReflectionIntro.java
java ReflectionIntro
```

Expected output:

```text
Class: Greeter
Method: sayHello
Result: Hello, An!
```

**Step-by-step explanation:**

- `Greeter.class` tells the runtime which class it is working with; the variable type is `Class<?>` because this code wants to work with general metadata.
- `getDeclaredConstructor()` finds the no-argument constructor. `newInstance()` creates an actual `Greeter`; the `instance` variable is declared as `Object` because dynamic calls may return various types.
- `getMethod("sayHello", String.class)` finds a `public` method by **name + parameter types**. If the name or signature changes, the lookup will fail at runtime.
- `invoke(instance, "An")` invokes the method on the instance. Because `Method.invoke` returns `Object`, the caller may need to check and cast the result for further use.

Here the compiler **does not need to see the call** `instance.sayHello("An")`. Method resolution is deferred to runtime. However, the example still uses `Greeter.class` for clarity; in a real application, the `type` variable might come from a configuration or plugin and be unknown in the framework's code.

### Comparing Direct Calls with Dynamic Calls

| Criterion | Direct Call | Using Reflection |
| --- | --- | --- |
| Syntax | `greeter.sayHello("An")` | `method.invoke(greeter, "An")` |
| Method selection | The compiler resolves it from source code and declared types | The program looks up `Method` at runtime |
| Wrong name/signature | Usually reported at compile time | May throw an exception at runtime |
| Result type | `String` is already known | The return value from `invoke` is `Object` |
| Handling previously unknown types | Limited by static API design | More flexible thanks to metadata |
| Simplicity, type checking, and optimization | Usually better | More complex and error-prone |

Reflection **complements** regular method calls; it does not make object-oriented design, interfaces, or polymorphism obsolete.

## 5. Five Situations Where Reflection Is Truly Useful

**1. Serialization/deserialization libraries.** A serializer can inspect the fields/getters and annotations of a runtime class to map data. Real-world frameworks may combine Reflection with generated accessors or other optimizations; not every JSON processing step has to use Reflection.

**2. Dependency injection and annotation-based configuration.** A container can discover declared classes/constructors and choose how to instantiate them based on metadata, then resolve dependencies. This structure lets you add new components without writing individual `new` calls inside the container.

**3. Test runners.** JUnit and similar tools can discover test methods through annotations and then execute them within a unified workflow. An annotation that needs to be found directly via Reflection at runtime must be retained at runtime; not all annotations are.

**4. Plugins / extensible configuration systems.** Concrete class names can be read from configuration, loaded, and verified before use. If plugins follow a stable contract, you should continue calling core functionality through an interface; Reflection may only serve the discovery/instantiation step.

**5. Analysis/debugging tools.** A tool can present class names, method/field lists, and annotations to help inspect running code. Listing metadata does not necessarily have to invoke methods or mutate object state.

Common thread: **general-purpose infrastructure code needs to understand data types that it did not know when it was written**.

## 6. Limitations and Trade-offs to Understand from the Start

### Errors Shift from Compile Time to Runtime

With direct calls, the IDE/compiler usually catches nonexistent methods. With Reflection, names are often stored as strings, so `getMethod("syaHello", String.class)` still compiles but will throw `NoSuchMethodException` at runtime.

Errors to distinguish:

- `ClassNotFoundException`: class not found by name in `Class.forName`.
- `NoSuchMethodException` / `NoSuchFieldException`: the looked-up member was not found.
- `IllegalAccessException` or `InaccessibleObjectException`: access permission or strong encapsulation issues depending on the API and timing.
- `IllegalArgumentException`: inappropriate receiver object or invalid number/types of arguments.
- `InvocationTargetException`: the invoked method/constructor **threw an exception**; inspect `getCause()` to see the underlying cause.

The example above declares `throws ReflectiveOperationException` to keep focus on the mechanism rather than production error-handling patterns. In real programs, add exception handling suited to the application's contract and log with context.

### Encapsulation and the Java Module System (JPMS)

Finding a `private` field/method via `getDeclaredField` or `getDeclaredMethod` **does not mean** you may freely access it. `setAccessible(true)` can be rejected, especially for packages that are not `opens` in a named module; do not treat it as a way to bypass all protective boundaries. Applications should prefer `public` APIs and clearly designed contracts. In Java modules, `exports` serves normal API access, whereas `opens` permits deep reflection into the specified package when needed.

### Performance

Metadata lookup, access checks, argument boxing/unboxing, and dynamic invocation can incur overhead compared to direct calls; the JVM does optimize Reflection, but you should not assume all calls are equal. Avoid repeatedly looking up the same `Method` inside a hot loop if metadata can be cached. Only benchmark when there is an actual performance issue; architectural choices should not be based on a single context-free benchmark number.

### Maintainability, Refactoring, and Security

Class/method names as strings are often not thoroughly checked by refactoring tools. Using Reflection on user-supplied data without restricting the allowed list of classes/actions can lead to unintended execution. If you must accept class names from configuration, validate against an allowlist, verify the interface/contract, restrict permissions, and handle errors clearly.

In some closed-world optimization environments (such as native image), dynamically accessed types or members may need to be registered in metadata/build configuration according to the tool in use.

## 7. When Should You Prefer Another Solution?

If the program already knows the types and behaviors from the start, choose **direct calls, interfaces, polymorphism, generics, or factories**. For example, when multiple objects implement `Notifier`, calling `notifier.send(...)` through the interface is simpler and more type-safe than using Reflection to look up a method named `send`.

Use Reflection when there is a **genuine dynamic reason**: discovering previously unknown types/annotations, instantiating from metadata, or building framework/general-purpose tooling. It is usually best to isolate it in an infrastructure layer and expose a strongly typed API to the rest of the application.

A self-check before choosing Reflection:

1. Are the type and method to call already known while writing the code? If yes, a direct call is usually better.
2. Can an interface or factory express the required contract? If yes, prefer that contract.
3. What metadata is actually needed, and is that member public or legitimately opened?
4. How will wrong names, wrong signatures, or missing classes be handled?
5. Can metadata be cached and allowed classes/actions restricted at the runtime boundary?

## 8. Key Takeaways

Reflection gives Java the ability to **introspect metadata and dynamically operate on classes, constructors, methods, and fields at runtime**. It solves the problem where general-purpose libraries/tools must handle types unknown at compile time. The cost is reduced compile-time type checking, additional runtime error handling, and access-control as well as maintainability/performance considerations.

Remember the rule of thumb: **when you only need specific behavior → call directly through a contract; when you need to discover structure dynamically → consider Reflection and tightly control its boundary**.

### Check Your Understanding

- Why can't a JSON library hardcode calls to every class in an application?
- What is the difference between `Greeter.class`, `obj.getClass()`, and `Class.forName(...)`?
- Why must `getMethod("sayHello", String.class)` explicitly specify parameter types?
- Why does finding a `private` field not guarantee that the field can be read?
- In a project with a stable interface, why should you call through the interface after the plugin discovery step?

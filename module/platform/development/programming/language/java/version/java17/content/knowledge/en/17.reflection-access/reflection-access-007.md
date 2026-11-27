# Hidden Classes for Dynamically Generated Code with `Lookup.defineHiddenClass` in Java 17

## 1. What problem do hidden classes solve?

Frameworks, compilers, or runtimes sometimes need to **generate bytecode at runtime** and then define a class to execute it. For example:

- An ORM framework generates adapter or accessor classes to read/write properties.
- A serialization library generates code to convert objects into bytes.
- A dynamic language runtime generates a class implementing a compiled code fragment.
- A proxy framework generates an implementation to connect an interface to runtime logic.

If every generated class were a regular named class, the class loader could end up managing a large number of classes. Such classes are typically just implementation details that do not need to be discovered by binary name from the outside.

Java 15 introduced **hidden classes** via JEP 371. Java 17 includes the stable API `MethodHandles.Lookup.defineHiddenClass` to define this kind of class from class file bytes. A hidden class:

- Is not discoverable by normal name-based class loading mechanisms such as `Class.forName` or `ClassLoader.loadClass`.
- Can be used through its `Class` object, `MethodHandles.Lookup`, and granted method handles.
- Can act as an implementation detail created and unloaded independently of its class loader's lifecycle, depending on definition options.
- Can become a nestmate to access private members of its nest host when `NESTMATE` is specified.

Key takeaway: hidden classes fit dynamically generated code that **does not need to become a publicly named type in the class-loading system**. They are neither a replacement for all regular classes nor a security mechanism for running untrusted bytecode.

## 2. How do hidden classes differ from regular classes?

### 2.1. Regular classes are loaded by name

A regular class has a binary name, such as `com.example.GeneratedTask`. A class loader can look up the class by name if it is defined and accessible:

~~~java
Class<?> type = Class.forName("com.example.GeneratedTask");
~~~

Regular classes fit public data types, library APIs, classes referenced in other bytecode, framework configurations, or types that need to be loaded by name.

### 2.2. Hidden classes are not discoverable by name

A hidden class is defined from bytecode, but the JVM marks it with hidden status. Ordinary class-loading mechanisms cannot find it by binary name like a normal class.

You can check:

~~~java
Class<?> hiddenType = lookup.lookupClass();
System.out.println(hiddenType.isHidden()); // true
~~~

`Class.isHidden()` has existed since Java 15. `Class.getName()` still returns a name for diagnostics, but that name may contain a JVM-generated special suffix. Do not store or use this string as a stable class name for calling `Class.forName`.

A hidden class still has a `Class` object. Applications can use that object to instantiate it, look up constructors/methods, or inspect reflection metadata within granted access permissions. "Hidden" means not discoverable by normal name-based lookup, not unusable.

### 2.3. Comparison with defineClass

`MethodHandles.Lookup` also has `defineClass(byte[])` to define a regular class in the same package/runtime context as the lookup:

| Criterion | `Lookup.defineClass` | `Lookup.defineHiddenClass` |
|---|---|---|
| Class kind | Regular class | Hidden class |
| Discoverable by name | Can be loaded by name via class loader | Not loaded by ordinary name-based mechanisms |
| Stable binary name for referencing | Yes | Should not rely on the JVM-assigned name |
| Purpose | Define a class with normal named identity | Define a dynamically generated implementation class without needing a public name |
| Independent unloading | Follows normal class loader lifecycle | Can unload independently if `STRONG` is not used and no references keep the class alive |
| Nestmate | According to nest attributes in the class file | Can be requested via `NESTMATE` |

If a generated class needs to be referenced by name from other class files, or needs to be registered as an ordinary type, consider `defineClass` or an appropriate class loader instead of a hidden class.

## 3. The Lookup.defineHiddenClass API in Java 17

The primary method has the signature:

~~~java
MethodHandles.Lookup defineHiddenClass(
        byte[] bytes,
        boolean initialize,
        MethodHandles.Lookup.ClassOption... options)
        throws IllegalAccessException;
~~~

Parameters:

| Parameter | Meaning |
|---|---|
| `bytes` | Byte array containing a valid class file for the class to define |
| `initialize` | Whether to require initializing the class immediately upon definition |
| `options` | Options such as `NESTMATE` and `STRONG` |

The return value is a new `Lookup` whose lookup class is the newly defined hidden class. This is important: instead of trying to load the class by name, the caller uses the returned lookup to find constructor, method, or field handles on that hidden class itself.

~~~java
MethodHandles.Lookup hiddenLookup =
        MethodHandles.lookup().defineHiddenClass(
                classFileBytes,
                true,
                MethodHandles.Lookup.ClassOption.NESTMATE);

Class<?> hiddenClass = hiddenLookup.lookupClass();
~~~

### 3.1. Bytecode must belong to the same package as the lookup class

A hidden class is defined in the same runtime package, class loader, module, and protection domain as the lookup class. The class file bytes must describe a class belonging to the **same package** as the lookup class.

For example, if the lookup class is `com.example.RuntimeCompiler`, the class file must have package `com.example`. You cannot use that lookup to arbitrarily define a hidden class in `java.lang` or another package.

This constraint ensures the hidden class shares an appropriate access environment and module context with the lookup. It also means the class loader is chosen indirectly via the lookup; `defineHiddenClass` does not take an arbitrary class loader as a parameter.

### 3.2. The lookup must have full privilege access

`defineHiddenClass` requires a lookup with **full privilege access**. Typically, code calling the API obtains a lookup from `MethodHandles.lookup()` inside a class in the target package:

~~~java
MethodHandles.Lookup lookup = MethodHandles.lookup();
~~~

This lookup represents the calling class's permissions. A `publicLookup()` or a reduced-privilege lookup is not sufficient to define a hidden class.

If a framework wants to define a class in another component's package, it needs an appropriate lookup provided by deliberate design. Do not assume every `privateLookupIn` call yields a full-privilege lookup, especially across module boundaries. Verify lookup permissions and module conditions before calling.

### 3.3. Class file bytes must be valid

The `bytes` array must contain a valid class file with a version compatible with the Java 17 runtime and the proper package. In real-world applications, bytecode is typically produced by:

- ASM.
- Byte Buddy.
- A framework compiler or code generator.
- An application's own compiler/runtime.

`defineHiddenClass` does not generate bytecode from Java source code itself. It takes pre-generated class file bytes and defines the class in the JVM.

## 4. Creating a hidden class and obtaining an instance with MethodHandles

The example below uses a precompiled class file template to illustrate the runtime definition step. In an actual framework, the template-reading part can be replaced by a byte array produced by a bytecode generator; the `defineHiddenClass` call remains the same.

Create `demo/HiddenClassDemo.java`:

~~~java
package demo;

import java.io.IOException;
import java.io.InputStream;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;

public class HiddenClassDemo {
    public interface Task {
        String execute();
    }

    public static void main(String[] args) throws Throwable {
        byte[] classBytes;

        try (InputStream input =
                     HiddenClassDemo.class.getResourceAsStream("GeneratedTask.class")) {
            if (input == null) {
                throw new IOException("GeneratedTask.class not found");
            }
            classBytes = input.readAllBytes();
        }

        MethodHandles.Lookup hiddenLookup =
                MethodHandles.lookup().defineHiddenClass(
                        classBytes,
                        true,
                        MethodHandles.Lookup.ClassOption.NESTMATE);

        Class<?> hiddenType = hiddenLookup.lookupClass();
        System.out.println(hiddenType.isHidden()); // true

        MethodHandle constructor = hiddenLookup.findConstructor(
                hiddenType,
                MethodType.methodType(void.class));

        Task task = (Task) constructor.invoke();
        System.out.println(task.execute());
    }
}

final class GeneratedTask implements HiddenClassDemo.Task {
    public GeneratedTask() {
    }

    @Override
    public String execute() {
        return "Hello from a hidden implementation";
    }
}
~~~

Compile and run:

~~~bash
javac --release 17 -d out demo/HiddenClassDemo.java
java -cp out demo.HiddenClassDemo
~~~

Output:

~~~text
true
Hello from a hidden implementation
~~~

Analysis:

1. The compiler generates `demo/GeneratedTask.class` in the same package as `HiddenClassDemo`.
2. The program reads that bytecode into a `byte[]`. In a framework, this step is typically the output of a code generator.
3. `MethodHandles.lookup()` obtains a lookup with `HiddenClassDemo`'s permissions.
4. `defineHiddenClass` defines a hidden class in the same package/runtime context.
5. `hiddenLookup.lookupClass()` obtains the hidden class's `Class` object.
6. `findConstructor` looks up the constructor through the returned lookup.
7. The instance is used through the `Task` interface, so the rest of the application does not depend on the implementation's name.

The `GeneratedTask` class here serves as a template so the example compiles using only the JDK. In real bytecode generation, a framework produces the byte array instead of reading a template class file.

## 5. The initialize option

The second parameter of `defineHiddenClass` determines when class initialization (`<clinit>`) runs:

~~~java
MethodHandles.Lookup hiddenLookup =
        lookup.defineHiddenClass(classBytes, true);
~~~

- `true`: requires initializing the class during definition before the method returns.
- `false`: defers initialization until the first active use that triggers class initialization according to JVM rules.

Class initialization can run static initializers, assign static fields, and raise errors. If a static initializer throws an exception, initialization can fail and the JVM reports `ExceptionInInitializerError` or a corresponding initialization error.

Choose `true` when the framework wants to detect initialization errors immediately at definition time. Choose `false` when deferring initialization cost until the class is actually used. Either way, do not place critical side effects in static initializers if the framework cannot control when they are triggered.

## 6. ClassOption.NESTMATE

### 6.1. Nest-based access control

Java has a nest mechanism so classes belonging to the same nest can access each other's private members under language and JVM rules. For example, an outer class and nested classes can share a nest host.

When passing `ClassOption.NESTMATE`, the hidden class is defined as a **nestmate of the lookup class**:

~~~java
MethodHandles.Lookup hiddenLookup =
        lookup.defineHiddenClass(
                classBytes,
                true,
                MethodHandles.Lookup.ClassOption.NESTMATE);
~~~

As a result, the hidden class can access private members of the nest host according to nest access rules, and eligible nestmates can also access private members of the hidden class. This is useful when a code generator creates adapters or accessors that need to work with the host class's private state.

### 6.2. Without NESTMATE

If this option is omitted, the hidden class is not added to the lookup class's nest. It does not automatically gain permission to access private members of the calling class merely from being defined by that lookup.

Having a full lookup to define a class does not mean every defined class automatically becomes a nestmate. Permission to define and nest membership are two separate concepts.

### 6.3. NESTMATE does not bypass all access checks

`NESTMATE` only establishes a nest relationship under the JVM mechanism. It does not:

- Allow accessing private members of arbitrary unrelated classes.
- Bypass all module or package constraints.
- Allow a class to arbitrarily change the nest host of an existing class.
- Act as a sandbox or grant privileges to untrusted bytecode.

Hidden classes must still pass the verifier, access checks, and all other JVM rules.

## 7. ClassOption.STRONG and hidden class lifecycle

A key benefit of hidden classes is the ability to be unloaded independently of their class loader when no longer referenced. By default, a hidden class is held weakly by its defining class loader; when no strong reference chain reaches the class, its instances, its lookup, or related method handles, the JVM can reclaim the class.

You can request that the class loader retain a strong reference to the hidden class using `ClassOption.STRONG`:

~~~java
MethodHandles.Lookup hiddenLookup =
        lookup.defineHiddenClass(
                classBytes,
                false,
                MethodHandles.Lookup.ClassOption.STRONG);
~~~

### 7.1. Comparing default and STRONG

| Configuration | Relationship to defining class loader | Lifecycle consequence |
|---|---|---|
| Without `STRONG` | Hidden class is weakly held by loader | Can unload independently when no references keep the class alive |
| With `STRONG` | Hidden class is strongly held by loader | Cannot unload independently before the loader becomes unreachable |

`STRONG` does not make the class loadable by name. It only changes reachability and unloading behavior, not hiddenness.

### 7.2. Cannot rely on GC timing

Eligibility for unloading does not mean the JVM will reclaim the class immediately after a method returns. If the application still retains:

- An instance of the hidden class.
- The `Class` object.
- A `Lookup` or `MethodHandle` referencing the hidden class.
- Callbacks or other objects holding references to the above.

then the hidden class remains reachable. Even when no references remain, the exact timing of garbage collection and class unloading is not guaranteed.

### 7.3. When is STRONG needed?

Only choose `STRONG` when there is a clear lifecycle reason, such as when a framework wants the class to live for the entire lifetime of the class loader. If the goal is generating many temporary implementations and letting them unload independently, the default is usually better.

Do not enable `STRONG` out of habit. If a framework generates thousands of hidden classes and keeps all of them strongly referenced through the loader, the benefit of independent unloading is lost and metaspace usage may grow.

## 8. Combining options

`ClassOption` is an enum with options:

- `NESTMATE`.
- `STRONG`.

They can be combined:

~~~java
MethodHandles.Lookup hiddenLookup =
        lookup.defineHiddenClass(
                classBytes,
                true,
                MethodHandles.Lookup.ClassOption.NESTMATE,
                MethodHandles.Lookup.ClassOption.STRONG);
~~~

In this example, the hidden class is both a nestmate of the lookup class and strongly held by the defining class loader.

There is no special precedence order between these two options; they control two different aspects: nest-based access and reachability/unloading.

## 9. Dynamic bytecode generation in frameworks

`defineHiddenClass` accepts a byte array, so the bytecode generation step belongs to the framework itself:

~~~java
byte[] generatedBytes = bytecodeGenerator.generate(
        packageName,
        implementationName,
        methodDefinitions);

MethodHandles.Lookup hiddenLookup =
        targetLookup.defineHiddenClass(
                generatedBytes,
                false,
                MethodHandles.Lookup.ClassOption.NESTMATE);
~~~

`bytecodeGenerator` here represents ASM, Byte Buddy, or a custom compiler. For the snippet to work:

1. The class file must be valid and have a Java 17-compatible version.
2. The package in the class file must match the lookup class's package.
3. The lookup must have full privilege access.
4. Classes/interfaces referenced by the bytecode must be resolvable from the defining loader/module.
5. The bytecode must pass verification and obey access checks.

A generator must validate bytecode structure, method descriptors, stack map frames, and class versions according to the library used. `defineHiddenClass` does not repair invalid bytecode into valid bytecode.

### 9.1. Using an interface as the boundary

A maintainable design has the hidden class implement a public interface:

~~~java
public interface QueryPlan {
    Object execute(Object input);
}
~~~

The framework defines the hidden implementation and returns `QueryPlan` to the rest of the application. Callers do not need to know the generated class name, cast to an internal implementation, or depend on the hidden class name suffix.

This also separates the stable API from dynamically generated bytecode.

### 9.2. When private access is needed

If the generated implementation needs to access private fields or methods of a host class, the framework can:

1. Obtain an appropriately privileged lookup from the host class.
2. Ensure the class bytes belong to the same package.
3. Define the hidden class with `NESTMATE`.
4. Grant necessary permissions only to trusted code generators.

A full-privilege `Lookup` is a sensitive capability. Do not distribute that lookup to plugins or untrusted code merely for convenience.

## 10. Hidden classes and related APIs

### 10.1. `defineHiddenClass` vs `defineHiddenClassWithClassData`

Java 16 added `Lookup.defineHiddenClassWithClassData` to define a hidden class while attaching class data accessible via the mechanism provided by `MethodHandles.classData`.

This is an advanced API when a framework needs to pass data bound to the generated class instead of creating static fields or embedding all values into bytecode. For foundational use, `defineHiddenClass` is the starting point; only use class data when you have a specific need and read the Java 17 contract carefully.

### 10.2. `LambdaMetafactory`

`LambdaMetafactory` is the public API for creating functional interface implementations from method handles. If the goal is merely creating a lambda or adapter for a functional interface, consider this API before generating class files manually.

~~~java
Function<String, Integer> length = String::length;
System.out.println(length.apply("Java")); // 4
~~~

Not every need for dynamic implementations requires calling `defineHiddenClass` directly. Higher-level APIs such as lambdas, dynamic proxies, or framework proxies may already cover most requirements.

### 10.3. `Proxy`

`java.lang.reflect.Proxy` fits when you need a proxy implementing one or more interfaces and routing calls through an `InvocationHandler`. If you only need to intercept interface method calls, consider Proxy instead of manually generating bytecode and managing hidden classes.

Hidden classes are useful when a framework needs bytecode-level control or specialized implementations that Proxy cannot provide.

## 11. Limitations and when not to use hidden classes

Hidden classes suit internal implementations, but they are not the default choice for every runtime-created class.

Do not use them when:

- The class must be loaded by binary name from configuration or `Class.forName`.
- The class must be directly referenced by name from other class files.
- The class is a public data type needing serialization, plugin discovery, or name-based service registration.
- The caller needs a separate class loader and cannot supply a lookup with a matching defining loader.
- Generated code does not need custom bytecode and can use lambdas, Proxy, or factories.
- Input bytecode is untrusted and the application mistakes hidden classes for a security sandbox.

A hidden class still executes inside the JVM with the permissions of its defining context. It does not isolate file, network, thread, or reflection permissions. If running untrusted code, design proper system-level isolation/security; hidden classes do not replace such mechanisms.

## 12. Common errors when defining hidden classes

### 12.1. Lookup lacks full privilege access

If you use `MethodHandles.publicLookup()` or an under-privileged lookup, `defineHiddenClass` can throw `IllegalAccessException`.

**Resolution:** obtain the lookup from a class in the target package or receive a suitably privileged lookup from the component owning the package. Do not look for ways to escalate privileges arbitrarily.

### 12.2. Package in class file does not match

A class file belonging to `com.example.generated` while the lookup class belongs to `com.example.runtime` will fail the same-package requirement.

**Resolution:** configure the generator to emit the class in the lookup's package, or obtain an appropriate lookup from the package the framework needs.

### 12.3. Assuming hidden classes can be loaded by name

`Class.getName()` does not turn a hidden class into a class loadable by `Class.forName`. Do not use the returned name as a long-term registry key.

**Resolution:** retain the `Class` object, `Lookup`, `MethodHandle`, or the interface implemented by the instance.

### 12.4. Forgetting NESTMATE

A hidden class is not automatically a nestmate of the lookup class. If the bytecode needs to access private members of the nest host, missing `NESTMATE` can cause access errors during linking or execution.

**Resolution:** use `NESTMATE` only when the nest relationship is part of the design and the lookup has appropriate permissions.

### 12.5. Using STRONG without considering unloading

`STRONG` causes the defining loader to hold the hidden class strongly. If classes are created continuously, this choice can prevent independent unloading.

**Resolution:** enable only when the lifecycle requires the class to stay tied to the loader; otherwise, consider the default.

### 12.6. Confusing defineHiddenClass with a bytecode generator

The method takes class file bytes; it does not compile source code or generate method bodies.

**Resolution:** separate bytecode generation from class definition, and verify the generator's output before calling the API.

### 12.7. Treating hidden classes as a sandbox

Hidden classes do not isolate code permissions. They only change discoverability and class lifecycle.

**Resolution:** only define bytecode from trusted sources or apply a separate isolation model.

## 13. Practice exercises

### Exercise 1 — Distinguishing regular and hidden classes

Explain the differences between `Lookup.defineClass` and `Lookup.defineHiddenClass` regarding name discoverability, lifecycle, and how callers retain access.

### Exercise 2 — Reading the example

Run the `HiddenClassDemo` program from section 4. Explain:

1. Why must the class bytes and lookup share the same package?
2. Why is the result of `isHidden()` true?
3. Why can the instance be used through the `Task` interface?
4. Why is it unnecessary to know the runtime name of the hidden class?

### Exercise 3 — Experimenting with initialize

Add a static initializer to `GeneratedTask` to log a message. Run with `initialize = true` and then `false`; observe when the message appears relative to first use of the class.

### Exercise 4 — Comparing NESTMATE

Examine a generated class that needs to call a private method on its nest host. Try defining it with and without `NESTMATE`; explain the nest relationship and access permission requirements. Do not modify bytecode of JDK classes.

### Exercise 5 — STRONG lifecycle

Define a hidden class with and without `STRONG`. Draw a reference diagram among the class loader, Lookup, Class object, and instance. Explain why GC timing cannot be used as a deterministic deadline for testing unloading.

### Exercise 6 — Choosing the right API

For each requirement, choose `defineHiddenClass`, `defineClass`, `Proxy`, or `LambdaMetafactory`:

- An implementation that must be reloaded by name from configuration.
- An adapter for a simple functional interface.
- A proxy intercepting calls on an interface.
- An internal bytecode implementation generated by a framework without needing a public name.

State the rationale and the lookup/package constraints.

## 14. Completion criteria

Learners have mastered this lesson when they can:

1. Explain that a hidden class is a class defined from bytecode that cannot be discovered via standard name-based loading mechanisms.
2. Use `Lookup.defineHiddenClass(byte[], boolean, ClassOption...)` and retrieve the class from `returnedLookup.lookupClass()`.
3. State the requirements for a full-privilege lookup, matching package, and valid class file bytes.
4. Distinguish `initialize = true` and `false`.
5. Explain the effects of `NESTMATE` and `STRONG`.
6. Describe how hidden classes can unload independently under default reachability, while GC/unloading has no guaranteed timing.
7. Use MethodHandles or a shared interface to instantiate and invoke instances without depending on implementation names.
8. Distinguish hidden classes from regular classes, Proxy, and lambda implementations.
9. Identify cases where hidden classes should not be used and avoid treating them as a sandbox.
10. Compile examples with JDK 17 without enabling preview features.

## 15. Official references

- [OpenJDK JEP 371 — Hidden Classes](https://openjdk.org/jeps/371): design goals, hiddenness, nestmates, and unloadability.
- [Java SE 17 API — `MethodHandles.Lookup`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html): requirements for defining hidden classes, initialize, and returned lookups.
- [Java SE 17 API — `MethodHandles.Lookup.ClassOption`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.ClassOption.html): `NESTMATE` and `STRONG`.
- [Java SE 17 API — `Class`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html): API for checking hidden status via `isHidden()`.
- [Java SE 17 API — `MethodHandles.Lookup`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html): API for defining regular classes via `defineClass(byte[])` for comparison.
- [Java SE 17 API — `MethodHandles.classData`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.html): class data API for hidden classes.
- [Java SE 17 API — `LambdaMetafactory`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/LambdaMetafactory.html): creating functional interface implementations from method handles.
- [Java SE 17 API — `Proxy`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Proxy.html): dynamic proxies for interfaces.

**Key takeaway:** `defineHiddenClass` takes generated bytecode, requires a full-privilege lookup in the matching package, and returns a lookup bound to the hidden class. `NESTMATE` controls nest-based private access; `STRONG` controls reachability from the class loader. Use hidden classes for dynamically generated implementations that do not need public names, keep them behind appropriate interfaces/MethodHandles, and manage reference lifetimes intentionally.

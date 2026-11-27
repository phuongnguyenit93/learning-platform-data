# Lifecycle, Name Discoverability, and Purpose of Hidden Classes in Java 17

**Topic:** Java 17  
**Chapter:** Reflection and Access  
**Lesson:** Lifecycle, Name Discoverability, and Purpose of Hidden Classes

A hidden class is a class defined at runtime using the `java.lang.invoke.MethodHandles.Lookup` API, designed for classes that frameworks or runtimes generate from bytecode and do not need to appear as regular classes in a class loader's namespace.

A hidden class can be initialized, instantiated, have its methods invoked via method handles, and join another class's nest. However, it **cannot be found by name through normal class-loading mechanisms** such as `Class.forName()` or `ClassLoader.loadClass()`. This is a key feature that lets frameworks generate temporary implementation classes without polluting the class loader's namespace.

Hidden classes were standardized in Java 15 via JEP 371 and continue to be supported in Java 17. The primary APIs are:

- `MethodHandles.Lookup.defineHiddenClass(...)`: defines a hidden class from bytecode.
- `MethodHandles.Lookup.defineHiddenClassWithClassData(...)`: defines a hidden class and attaches dedicated class data.
- `Class.isHidden()`: checks whether a `Class` object represents a hidden class.
- `MethodHandles.Lookup.lookupClass()`: retrieves the `Class` represented by a lookup object.
- `MethodHandles.Lookup.ClassOption.NESTMATE` and `STRONG`: important options affecting access permissions and lifecycle.

Hidden classes are especially useful for frameworks generating proxies, adapters, accessors, or dynamically generated implementation classes. They are not a way to declare normal classes, not a security mechanism for hiding data, and not a replacement for class loaders or JPMS.

## 1. What is a hidden class?

A regular Java class is defined in source code or bytecode and can be looked up by binary name in a class loader's namespace. For example:

```java
Class<?> type = Class.forName("com.example.User");
```

Or:

```java
Class<?> type = classLoader.loadClass("com.example.User");
```

This mechanism fits application classes, plugins, libraries, and public APIs.

However, frameworks sometimes need to generate new bytecode while a program runs. For example:

- Creating an adapter class to invoke a specific API faster.
- Generating accessors for entity fields or properties.
- Generating an implementation for an interface or a parsed expression.
- Generating classes to support serialization, mapping, or proxying.
- Creating specialized implementation code tailored to runtime data structures.

If every generated class were defined as a regular class, the class loader's namespace could fill up with many named classes, including short-lived ones. This complicates lifecycle management, name collisions, and class unloading.

**Hidden classes** address this set of requirements: a class is defined and used via runtime references, without being registered as a class reloadable by name.

### 1.1. A hidden class is still a real class

A hidden class is not a simulated snippet or a special stand-in object instead of a class. The JVM still defines the class, creates metadata, verifies bytecode, runs class initialization, and can instantiate it.

You can retrieve the `Class<?>` of a hidden class and inspect it:

```java
Class<?> hiddenType = hiddenLookup.lookupClass();

System.out.println(hiddenType.isHidden()); // true
System.out.println(hiddenType.getClassLoader());
System.out.println(hiddenType.getModule());
```

It still has:

- A `Class<?>` object.
- A defining class loader.
- A runtime package and module determined by the defining context.
- Required methods, fields, constructors, and metadata.
- A class lifecycle and eligibility for JVM unloading.

The difference lies in **discoverability and how the class is referenced**. A hidden class is not looked up again by ordinary name in the class loader namespace.

### 1.2. Hidden class is not a source-code modifier

Java has no declaration syntax like:

```java
// This is not valid Java syntax:
hidden class GeneratedAccessor {
}
```

Instead, a framework generates or receives the class bytecode and instructs the JVM to define it via `MethodHandles.Lookup`.

Consequently, hidden classes typically appear in framework, bytecode-generator, or runtime code rather than in ordinary business logic.

## 2. Why cannot a hidden class be looked up by name?

A regular class can be looked up by binary name through a class loader. Hidden classes are designed not to participate in that lookup.

Name-based class-loading APIs such as:

```java
Class.forName("com.example.GeneratedAccessor");
classLoader.loadClass("com.example.GeneratedAccessor");
```

cannot be used to find a defined hidden class. Knowing the original classfile name does not let you load the hidden class by that name either.

Instead, code receives a `Lookup` from the definition operation and obtains `Class<?>` directly:

```java
MethodHandles.Lookup hiddenLookup =
        MethodHandles.lookup().defineHiddenClass(
                classBytes,
                true
        );

Class<?> hiddenType = hiddenLookup.lookupClass();
```

`hiddenLookup` is the reference path returned by the JVM for the newly defined class. From this lookup, the caller can look up appropriate method handles, create instances, or perform operations allowed by access permissions.

### 2.1. The name returned by Class.getName() is not a lookup key

A hidden class still has a displayable name when calling `Class.getName()`. For hidden classes, the name typically consists of the classfile's binary name plus a JVM-generated suffix, e.g.:

```text
com.example.GeneratedAccessor/0x0000000800c02400
```

The suffix is an unidentifiable name generated by the JVM to distinguish classes. Do not rely on this string to:

- Call `Class.forName()`.
- Call `ClassLoader.loadClass()`.
- Store as a stable identifier across runs.
- Construct configuration or plugin names.
- Compare class identity across two JVMs.

That name serves runtime information and diagnostics. The proper way to reference the class is to retain the `Class<?>`, `Lookup`, instance, or `MethodHandle` returned during definition.

### 2.2. A hidden class is observable once you hold a reference

"Hidden" does not mean the class is completely invisible to all tools. If a program already holds its `Class<?>`, instance, or method handle, the program can use those references and inspect its metadata.

Example:

```java
Class<?> type = hiddenLookup.lookupClass();

if (type.isHidden()) {
    System.out.println("This is a hidden class");
}
```

Hidden class names can also appear in stack traces or diagnostic output. Therefore, do not treat hidden classes as a mechanism for hiding secrets or protecting data.

### 2.3. Cannot use a hidden class as a dependency referenced by name

Hidden classes are not designed for other classes to reference by symbolic name in bytecode constant pools like ordinary types. Thus, hidden classes are unsuitable as:

- A superclass or superinterface declared in another class.
- A field, parameter, or return type declared in another class's bytecode.
- A public type in an API that callers need to compile against or load by name.
- An extension point for name-based plugin discovery.

Callers can still interact with instances via `Object`, public interfaces, or method handles. For instance, a framework can hold a method handle to a method in the hidden class without other classes referencing the hidden class's name.

## 3. API for defining hidden classes in Java 17

Hidden classes are defined through `MethodHandles.Lookup`. This API belongs to package `java.lang.invoke`.

### 3.1. Lookup.defineHiddenClass()

Primary API signature:

```java
Lookup defineHiddenClass(
        byte[] bytes,
        boolean initialize,
        Lookup.ClassOption... options
) throws IllegalAccessException
```

Parameter meanings:

| Parameter | Meaning |
|---|---|
| `bytes` | Classfile bytecode to define |
| `initialize` | Whether to initialize the class immediately upon definition |
| `options` | Options such as `NESTMATE` or `STRONG` |

The result is a new `Lookup` whose lookup class is the newly defined hidden class.

Skeleton example:

```java
MethodHandles.Lookup lookup = MethodHandles.lookup();

MethodHandles.Lookup hiddenLookup =
        lookup.defineHiddenClass(
                classBytes,
                true,
                MethodHandles.Lookup.ClassOption.NESTMATE
        );

Class<?> hiddenClass = hiddenLookup.lookupClass();
```

The bytecode must be valid and the classfile must belong to the same package as the lookup class. The lookup used for definition must have full access permissions as required by the API. If access or package conditions are not satisfied, the operation can fail.

### 3.2. Why is MethodHandles.Lookup required?

`Lookup` carries the access context of the code performing the operation. It identifies the calling class, access permissions, and required module context.

This makes sense because the hidden class is defined in the same package and class loader as the lookup class. Defining a class is not a global operation that arbitrary code can perform with arbitrary bytecode.

In a simple example, `MethodHandles.lookup()` creates a lookup reflecting the current class's permissions:

```java
MethodHandles.Lookup lookup = MethodHandles.lookup();
System.out.println(lookup.lookupClass());
```

A framework can receive or create an appropriate lookup from a target class. Obtaining a lookup with private or full privilege access must follow the rules of `MethodHandles` and the module system; privileges cannot be arbitrarily escalated merely by calling an API.

### 3.3. The classfile must share the lookup class's package

`defineHiddenClass()` defines the class in the same package as the lookup class. Therefore, the supplied bytecode must declare the class in the corresponding package.

For example, if the lookup class is in:

```java
package com.example.runtime;
```

then the classfile defining the hidden class must also belong to package `com.example.runtime`. You cannot use a lookup in this package to arbitrarily define a hidden class in another package.

This requirement ties the hidden class to the defining context and permissions of the lookup.

## 4. Hidden class lifecycle: default weak vs STRONG

A major reason to use hidden classes is the ability to unload classes without waiting for the entire defining class loader to be reclaimed.

A hidden class's lifecycle depends on the references keeping it alive and the class definition options.

### 4.1. Default: hidden classes can unload independently of the class loader

If `ClassOption.STRONG` is not specified, the hidden class is held by a weak relationship from its defining class loader. This allows the JVM to unload the hidden class when no required strong references remain, even while its defining class loader is still alive.

Conceptual model:

```text
Defining ClassLoader is still alive
              |
              | weak reference
              v
          Hidden Class
              ^
              |
       strong references
       from Class / instance /
       Lookup / MethodHandle
```

Once strong references to the hidden class and its instances are gone, the class may become eligible for unloading. Unloading is decided by the JVM and garbage collector; applications cannot dictate the exact unloading time.

This is a useful difference from regular classes defined in a class loader: regular classes typically stay tied to their defining loader's lifetime, whereas hidden classes by default can be reclaimed individually when no longer used.

### 4.2. Strong references still keep a hidden class alive

A hidden class does not vanish simply because it cannot be looked up by name. If the application still holds references such as:

- Instances created from the hidden class.
- The hidden class's `Class<?>` object.
- The `MethodHandles.Lookup` returned from the definition operation.
- `MethodHandle` objects pointing to methods of the hidden class.
- Another object or data structure retaining any of the references above.

then the hidden class may still be in use and is not yet eligible for unloading.

Example:

```java
Class<?> hiddenType = hiddenLookup.lookupClass();

Object instance = hiddenType.getDeclaredConstructor().newInstance();

// While still holding instance or hiddenType,
// do not expect the class to be unloaded.
```

Setting variables to `null` does not guarantee immediate unloading either. The JVM must determine that no strong reference paths keep the class or its instances alive, after which class unloading still depends on GC policies and runtime state.

### 4.3. ClassOption.STRONG: tying the hidden class to the class loader's lifecycle

If a hidden class is defined with `STRONG`:

```java
MethodHandles.Lookup hiddenLookup =
        MethodHandles.lookup().defineHiddenClass(
                classBytes,
                true,
                MethodHandles.Lookup.ClassOption.STRONG
        );
```

the hidden class is strongly held by its defining class loader. It will not unload individually just because other references to the class have disappeared; the class loader itself must become unused and eligible for reclamation before the hidden class can be unloaded along with the loader.

Comparison:

| Characteristic | Default (no STRONG) | With `STRONG` |
|---|---|---|
| Relationship from defining loader | Weak reachability | Strong reachability |
| Can unload while loader is alive? | Yes, if no other strong references remain | No |
| Lifecycle close to a regular class? | No, can be shorter than loader | Closer to a loader-bound class |
| Purpose | Dynamically generated classes reclaimable individually | Classes needing to live for the loader's lifetime |

`STRONG` does not mean the class lives forever. When the defining class loader becomes eligible for reclamation, hidden classes held by the loader can also be unloaded.

### 4.4. Cannot rely on garbage collection timing

Class unloading is not a synchronous operation that code can deterministically observe right after a `System.gc()` call. That call is only a GC hint, not a guarantee that classes will be unloaded.

When designing a framework, you should:

- Release references to `Class`, instances, `Lookup`, and `MethodHandle` when no longer used.
- Avoid caching hidden class method handles in unbounded global caches.
- Choose `STRONG` only when the class needs to stay alive for the loader's lifetime.
- Never write business logic that depends on when a class is unloaded.

## 5. The NESTMATE option: hidden classes joining a nest

Java uses the *nest* concept so classes with a trusted private-access relationship can access each other's private members. For example, an outer class and its nested classes normally belong to the same nest.

When defining a hidden class with `ClassOption.NESTMATE`, the hidden class is added to the lookup class's nest. As a result, the hidden class can access private members of the nest host under nest-based access control rules.

```java
MethodHandles.Lookup hiddenLookup =
        MethodHandles.lookup().defineHiddenClass(
                classBytes,
                true,
                MethodHandles.Lookup.ClassOption.NESTMATE
        );
```

This is useful for frameworks generating accessors or implementations that need to interact with a target class's private state.

### 5.1. NESTMATE does not open a package to every module

`NESTMATE` addresses private access relationships within a nest. It does not replace JPMS `exports` or `opens` and does not grant arbitrary permissions across module boundaries.

Access still depends on the lookup and module rules. Do not use `NESTMATE` as a way to fix arbitrary reflection or strong-encapsulation errors.

### 5.2. When is NESTMATE needed?

Choose `NESTMATE` when the generated class needs to access private members of the class owning the lookup, for example:

- Generating accessors for private fields.
- Generating an implementation supporting the target class that needs to call private methods.
- Generating optimized code acting as a trusted member of the nest.

If the hidden class only calls public APIs and does not need the nest host's private privileges, there is no need to enable this option.

## 6. Class initialization and constructors are two separate steps

The `initialize` parameter of `defineHiddenClass()` controls whether the JVM runs class initialization immediately upon definition.

### 6.1. initialize = true

```java
Lookup hiddenLookup = lookup.defineHiddenClass(
        classBytes,
        true
);
```

If the class has a static initializer (`<clinit>`), the JVM performs class initialization according to normal rules before the definition operation finishes.

### 6.2. initialize = false

```java
Lookup hiddenLookup = lookup.defineHiddenClass(
        classBytes,
        false
);
```

The class is defined, but initialization is deferred until an active use of the class requires initialization under JVM class initialization rules.

This parameter does **not** mean an instance constructor is automatically called or an object is created. Defining a class, initializing a class (static initialization), and instantiating an object are three distinct stages.

### 6.3. Creating an instance after definition

From the returned `Lookup`, you can obtain `Class<?>` and then use reflection or method handles according to permissions:

```java
Class<?> hiddenClass = hiddenLookup.lookupClass();

Object instance =
        hiddenClass.getDeclaredConstructor().newInstance();
```

If the hidden class has no constructor accessible in the current context, instantiation can fail. A framework can use `hiddenLookup.findConstructor(...)` to obtain an appropriate method handle instead of relying on reflection.

## 7. Complete example: defining a hidden class from bytecode

The JDK does not provide a high-level API for writing arbitrary bytecode. Frameworks typically use bytecode generators or libraries such as ASM to produce classfiles. To demonstrate the Java 17 API without external libraries, the following example reads bytecode from a class in the same package and defines a hidden class from those bytes.

The example requires two classes in the same package `com.example`. Class `GeneratedTask` serves as the bytecode template:

```java
package com.example;

class GeneratedTask {
    public static String run() {
        return "Hidden implementation executed";
    }
}
```

Demo class:

```java
package com.example;

import java.io.IOException;
import java.io.InputStream;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;

public class HiddenClassDemo {

    static byte[] classBytes(Class<?> type) throws IOException {
        String resourceName = type.getSimpleName() + ".class";

        try (InputStream input =
                     type.getResourceAsStream(resourceName)) {

            if (input == null) {
                throw new IOException("Cannot find " + resourceName);
            }

            return input.readAllBytes();
        }
    }

    public static void main(String[] args) throws Throwable {
        byte[] bytes = classBytes(GeneratedTask.class);

        MethodHandles.Lookup hiddenLookup =
                MethodHandles.lookup().defineHiddenClass(
                        bytes,
                        true,
                        MethodHandles.Lookup.ClassOption.NESTMATE
                );

        Class<?> hiddenClass = hiddenLookup.lookupClass();

        System.out.println("isHidden = " + hiddenClass.isHidden());
        System.out.println("name = " + hiddenClass.getName());

        MethodHandle run = hiddenLookup.findStatic(
                hiddenClass,
                "run",
                MethodType.methodType(String.class)
        );

        String result = (String) run.invokeExact();
        System.out.println(result);
    }
}
```

Compile and run from the appropriate source root:

```bash
javac --release 17 -d out com/example/GeneratedTask.java com/example/HiddenClassDemo.java
java -cp out com.example.HiddenClassDemo
```

Illustrative output:

```text
isHidden = true
name = com.example.GeneratedTask/0x0000000800c02400
Hidden implementation executed
```

The suffix in the name is an example; the JVM may generate a different value on each run.

### 7.1. What happened?

1. `GeneratedTask.class` is read into a byte array.
2. `MethodHandles.lookup()` creates a lookup in package `com.example`.
3. `defineHiddenClass()` defines a hidden class from bytecode in the same package.
4. `lookupClass()` retrieves the `Class<?>` of the hidden class.
5. `isHidden()` confirms the class is a hidden class.
6. `findStatic()` creates a method handle to the `run` method.
7. `invokeExact()` invokes the method without loading the class by name.

The example uses bytecode from a normal class as a template to illustrate the mechanism. In real frameworks, bytecode is typically generated specifically for runtime classes or data; hidden classes are created so that implementation does not need to be registered in the normal class-name namespace.

### 7.2. Why invoke via method handle instead of Class.forName?

Once defined, we already hold the lookup and `Class<?>`. Looking up the method via `hiddenLookup.findStatic(...)` directly uses the permissions and class represented by the lookup.

If you try to look up the class again by the name string from `hiddenClass.getName()`, normal class-loader mechanisms cannot find that hidden class. Therefore, retain the references returned during definition.

## 8. defineHiddenClassWithClassData(): attaching data to a hidden class

Besides bytecode, frameworks sometimes need to attach dedicated data to the generated class, such as configuration, metadata, or information related to code generation.

Java 17 provides `defineHiddenClassWithClassData()` to define a hidden class and attach a class data object:

```java
Lookup defineHiddenClassWithClassData(
        byte[] bytes,
        Object classData,
        boolean initialize,
        Lookup.ClassOption... options
) throws IllegalAccessException
```

This data is associated with the hidden class via the `MethodHandles` class-data mechanism. It is not the same as a normal static field declared in the classfile.

Points to remember:

- Class data is bound to the defined hidden class.
- The class-data access API is designed for lookups with appropriate permissions.
- The data can be a configuration object or metadata needed by the generated bytecode.
- Do not treat class data as persistent storage; its lifetime is tied to the class and its associated references.

This capability is useful when a framework wants to retain runtime implementation data without embedding all values into bytecode as constants.

## 9. What problems do hidden classes solve?

### 9.1. Avoiding polluting the class loader namespace

A framework may generate thousands of specialized implementations over its runtime lifetime. If every class were registered as a normal class, their names and metadata could persist for the lifetime of the loader.

Hidden classes are not looked up by name in the normal namespace. With the weak default, classes can unload individually when unreferenced, even while the class loader remains alive.

### 9.2. Reducing name-collision risk for dynamically generated classes

Normal classes in the same class loader cannot arbitrarily define multiple classes with the same binary name. Hidden classes are not registered in the same name-lookup table, so a framework can define multiple hidden classes from classfiles sharing the same base name within the same loader context.

Their runtime names receive JVM-appended suffixes to distinguish them. Code should not use this name as a business identifier.

### 9.3. Supporting specialized implementations

Frameworks can generate bytecode based on metadata of a class or schema. For example:

- Accessors reading only a specific set of fields.
- Adapters converting a data type to a protocol.
- Implementations for parsed expressions or lambdas.
- Code mapping between objects and database columns.
- Internal proxies generated to optimize a call path.

Hidden classes fit when implementations only need to be retained and used by the framework through runtime references.

### 9.4. Supporting private access via nestmates

With `NESTMATE`, a hidden class can join the lookup class's nest and access private members under nest rules. This lets frameworks generate accessors or adapters that work with a target class without turning all fields public.

This option must be used in the proper context; it is not a general way to grant permissions to other modules.

### 9.5. Lifecycle suited to temporary generated classes

An implementation class generated for a specific data structure or task may no longer need to exist after the task finishes. Hidden classes by default support class unloading independent of the loader once references disappear.

This can reduce class-metadata retention pressure in frameworks that generate many dynamic classes. However, if the framework retains instances, lookups, or method handles in a cache, the hidden class can still live longer.

## 10. How do hidden classes differ from regular classes and anonymous classes?

| Criterion | Regular class | Anonymous/local class | Hidden class |
|---|---|---|---|
| Declared in source code | Yes | Yes | No source modifier; defined from bytecode |
| Found by class loader name | Yes, if defined via normal mechanisms | May have runtime names, but not a stable lookup API | No |
| Has `Class<?>` | Yes | Yes | Yes |
| Can create instances | Yes | Yes | Yes |
| Can invoke methods | Directly or via reflection/handles | Directly or via reflection/handles | Via instance, reflection, or method handles per permissions |
| Can join a nest | Per class/nest rules | Per declaration structure | Can choose `NESTMATE` |
| Unload independently of defining loader | Usually not under standard mechanisms | Not the goal of anonymous/local classes | Yes, weak by default |
| Primary purpose | Models, APIs, stable implementations | Local implementations declared in source | Dynamically generated bytecode implementations without name lookup |

Anonymous classes and local classes are still compiler-generated classes from source code. Hidden classes are classes defined by a runtime API with dedicated discoverability and lifecycle policies.

## 11. Hidden classes are not a security mechanism

The name "hidden" easily creates the impression that the class is protected from all access, but its technical meaning is **not discoverable by name through normal class loaders**.

If a program holds a reference to its `Class<?>`, instance, or method handle, it can still use whatever access permissions allow. Stack traces and diagnostic tools can also show the class's runtime name.

Hidden classes do not:

- Encrypt bytecode.
- Conceal data from callers with runtime access.
- Replace Java or JPMS access control.
- Provide a sandbox for untrusted code.
- Guarantee generated code cannot be observed or analyzed.

If security is needed, use proper access models, module boundaries, authentication, encryption, and sandboxing suited to real requirements. Do not use hidden classes to store secret keys or sensitive data.

## 12. When should you avoid hidden classes?

Hidden classes are a specialized tool. Regular classes are better when an application needs one or more of the following:

- The class must be found by name by other plugins or frameworks.
- The class is a public type in an API.
- The class must appear in configuration by binary name.
- The class needs to be loaded via `ClassLoader.loadClass()`.
- The system needs to scan packages/classpath to discover implementations.
- The class lifecycle should clearly remain tied to the class loader.
- The code does not generate bytecode and has no specialized runtime class-management need.

For example, a plugin configured with:

```text
implementation=com.example.plugins.CsvImporter
```

needs a class that a class loader can locate by name. Hidden classes do not fit that contract.

Similarly, if you only need a lambda, anonymous class, or regular class, use the Java language and standard APIs first. Do not build a bytecode generator and use hidden classes without a real need.

## 13. Common mistakes and misconceptions

### Mistake 1. Thinking hidden classes can be reloaded via Class.forName()

They cannot. Hidden classes are not registered for name lookup in the class loader namespace. Keep the `Lookup`, `Class<?>`, instance, or method handle obtained at definition time.

### Mistake 2. Using Class.getName() as a stable name

Hidden class names have a JVM-generated suffix and are not stable lookup keys. Do not save this name to configuration or a database for later reloading.

### Mistake 3. Thinking hidden classes have no Class<?>

Hidden classes still have `Class<?>`. You can retrieve it via `hiddenLookup.lookupClass()` and check it with `isHidden()`.

### Mistake 4. Thinking hidden classes unload immediately after a method ends

No. A class only becomes eligible for unloading when no strong references keep it or its instances alive; the unloading time is decided by the JVM.

### Mistake 5. Choosing STRONG without considering loader lifetime

`STRONG` keeps the hidden class strongly held by its defining loader. If the loader is long-lived, the hidden class can also be retained longer. Choose the weak default when classes should be reclaimable individually.

### Mistake 6. Assuming NESTMATE opens the entire module

No. `NESTMATE` lets the class join the nest and access private members under nest rules. It does not replace `exports`, `opens`, or module permissions.

### Mistake 7. Defining bytecode in a different package from the lookup class

`defineHiddenClass()` requires the classfile to belong to the same package as the lookup class. Generate bytecode in the right package or use a lookup from a package aligned with your design.

### Mistake 8. Confusing initialize with creating an instance

`initialize = true` runs class initialization, not an instance constructor. Creating an object is a separate step afterward.

### Mistake 9. Keeping method handles in unbounded caches

Method handles can keep a hidden class alive. Global caches need size limits, eviction policies, or lifecycle coupling to the consumer objects.

### Mistake 10. Treating hidden classes as a security layer

Hidden classes only prevent name-based lookup. Given a runtime reference, code can still use the class within granted permissions.

## 14. Decision process for using hidden classes

Before choosing hidden classes, answer these questions:

1. Is the class generated from bytecode at runtime?
2. Does the class need to be discovered again by name or classpath?
3. Does the class serve only as an internal implementation inside a framework/runtime?
4. Does it need access to private members of a target class? If so, is `NESTMATE` appropriate?
5. Should the class unload independently of the class loader? If so, consider the weak default.
6. Does the class need to live for the loader's lifetime? If so, consider `STRONG`.
7. Might the framework retain `Class`, instances, `Lookup`, or `MethodHandle` longer than expected?
8. Do the module and lookup have sufficient permissions to define a class in the target package?

Quick selection table:

| Need | Choice |
|---|---|
| Regular class, needs loading by name | Regular class / class loader |
| Dynamically generated class, no name lookup needed | Hidden class |
| Hidden class needing private access within a nest | Hidden class with `NESTMATE` |
| Hidden class unloadable while loader stays alive | Default hidden class (weak) |
| Hidden class that must live as long as defining loader | Hidden class with `STRONG` |
| Framework needs class data attached to implementation | `defineHiddenClassWithClassData()` |
| Plugin needing discovery by name | Regular class |

## 15. Official references

- [JDK 17 API — MethodHandles.Lookup](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html): `defineHiddenClass`, `defineHiddenClassWithClassData`, `lookupClass`, and class options.
- [JDK 17 API — MethodHandles.Lookup.ClassOption](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.ClassOption.html): `NESTMATE` and `STRONG`.
- [JDK 17 API — Class.isHidden()](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#isHidden()): checking whether a class is a hidden class.
- [JDK 17 API — Class.getName()](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#getName()): how hidden class names are represented.
- [JDK 17 API — MethodHandles](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.html): lookups, method handles, and class data.
- [OpenJDK JEP 371 — Hidden Classes](https://openjdk.org/jeps/371): design goals, discoverability, lifecycle, and hidden class APIs standardized since Java 15.

**Key takeaway:** Hidden classes are defined from bytecode via `MethodHandles.Lookup`, can be used through `Class<?>` and `MethodHandle`, and cannot be looked up again by name via `Class.forName()` or `ClassLoader.loadClass()`. By default, a hidden class can unload independently of its defining loader when no strong references remain; `STRONG` keeps the class alive for the loader's lifetime. Use `NESTMATE` when private access within a nest is needed. Hidden classes are meant for framework-generated dynamic implementations, not public API classes or security mechanisms.

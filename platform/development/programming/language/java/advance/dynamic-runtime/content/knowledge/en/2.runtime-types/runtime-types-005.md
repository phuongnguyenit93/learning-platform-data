# 2.5 Type identity by name and class loader: why the same name can still be different types

**Context:** Java Advance → dynamic-runtime → 2. Runtime types.

When reading source code, we often identify a type by a name such as `com.example.Plugin`. However, in the JVM, knowing only the name is not enough to conclude that two objects have the same type. This is especially important for plugins, application servers, hot reload, frameworks that load classes themselves, and systems using multiple `ClassLoader`s.

## 1. Runtime type identity rules

For a **non-array class or interface**, the Java Virtual Machine Specification (JVMS `5.3) defines a runtime type by a **pair**:

```text
Runtime type identity = (binary name, defining class loader)
```

- **Binary name**: the binary name, for example `com.example.Plugin`, or `com.example.Outer$Inner` for a member class.
- **Defining loader**: the class loader itself that invoked the mechanism to define the type from bytecode (usually via `defineClass`), not necessarily the first loader requested to find that type.
- Two classes with the **same binary name and the same defining loader** are the same runtime type; a single defining loader cannot successfully define two different classes with the same binary name.
- Two classes with the **same binary name but two different defining loaders** are **two different runtime types**, even if the bytecode is identical, with the same version, the same path, or the same JAR.

You can think of it like two people with the same full name but carrying two different identifiers. The name represents part of the information; the defining loader completes the identity of the type.

Example with the name `com.example.Plugin`:

| Type | Binary name | Defining loader | Conclusion |
| --- | --- | --- | --- |
| A | `com.example.Plugin` | loader object L1 | Type A |
| B | `com.example.Plugin` | loader object L2 | Type B, **different from A** if L1 ≠ L2 |
| C | `com.example.Plugin` | the same loader L1 | **Same as Type A** |

Note: distinguish **loader objects**, not just the loader class name. Two instances of the same `URLClassLoader` are still two different defining loaders when each instance defines a class itself.

## 2. Loading, defining loader, and initiating loader

The process by which the JVM handles a type typically consists of **loading → linking → initialization**. During *loading*, when loader L receives a request to load name N, it can:

1. Find the bytecode itself and define N: L is the **defining loader** of N.
2. Delegate to another loader (usually the parent) to define N: L can be an **initiating loader**, while the delegated loader is the **defining loader**.

The common strategy of `ClassLoader.loadClass` is **parent-first delegation**: check if the class is already loaded, ask the parent first, and only then search in the current loader if needed. However, custom loaders can have their own rules; parent-first is the common behavior of the `ClassLoader` mechanism, not the definition of type identity.

```text
Request: load("com.example.Api") on PluginLoader
             |
             v
      PluginLoader (initiating)
             |
       delegate to parent
             v
      AppLoader (defining)
             |
             v
      Class<?> of Api
```

If two child loaders both delegate `com.example.Api` to the same parent, both receive **the same `Class<?>`**. Therefore, the statement "two different loaders always produce two different types" is false: what decides is **the loader that actually defines the type**.

In modern Java, we commonly encounter the bootstrap, platform, application/system loaders, and custom loaders. For many core classes, `Class.getClassLoader()` returns `null` to represent the bootstrap loader; `null` does not mean the class has not been loaded.

## 3. Java 17+ experiment: same bytecode, same name, but different types

Create two files in the **same directory**. Here, classes without a package declaration are used so the example is short and runs standalone; in a real project, you should use packages with clear names.

**File `Sample.java`**

```java
public class Sample {
    public Sample() {
    }

    public String message() {
        return "hello";
    }
}
```

**File `TypeIdentityDemo.java`**

```java
import java.nio.file.Files;
import java.nio.file.Path;

public class TypeIdentityDemo {
    static final class CopyLoader extends ClassLoader {
        CopyLoader() {
            super(ClassLoader.getPlatformClassLoader());
        }

        Class<?> defineCopy(byte[] bytecode) {
            return defineClass("Sample", bytecode, 0, bytecode.length);
        }
    }

    public static void main(String[] args) throws Exception {
        byte[] bytes = Files.readAllBytes(Path.of("Sample.class"));

        CopyLoader loaderA = new CopyLoader();
        CopyLoader loaderB = new CopyLoader();

        Class<?> typeA = loaderA.defineCopy(bytes);
        Class<?> typeB = loaderB.defineCopy(bytes);

        Object a = typeA.getConstructor().newInstance();
        Object b = typeB.getConstructor().newInstance();

        System.out.println("sameName=" + typeA.getName().equals(typeB.getName()));
        System.out.println("sameClass=" + (typeA == typeB));
        System.out.println("sameLoader=" + (typeA.getClassLoader() == typeB.getClassLoader()));
        System.out.println("aAcceptsOwn=" + typeA.isInstance(a));
        System.out.println("aAcceptsB=" + typeA.isInstance(b));
        System.out.println("appAcceptsA=" + Sample.class.isInstance(a));

        try {
            Sample value = (Sample) a;
            System.out.println(value.message());
        } catch (ClassCastException expected) {
            System.out.println("ClassCastException");
        }

        ClassLoader child1 = new ClassLoader(Sample.class.getClassLoader()) {};
        ClassLoader child2 = new ClassLoader(Sample.class.getClassLoader()) {};
        boolean delegatedSame = Class.forName("Sample", false, child1)
                == Class.forName("Sample", false, child2);
        System.out.println("delegatedSame=" + delegatedSame);
    }
}
```

**Compile and run from the directory containing the two files:**

```bash
javac -encoding UTF-8 Sample.java TypeIdentityDemo.java
java TypeIdentityDemo
```

**Expected output:**

```text
sameName=true
sameClass=false
sameLoader=false
aAcceptsOwn=true
aAcceptsB=false
appAcceptsA=false
ClassCastException
delegatedSame=true
```

**Step-by-step explanation:**

1. `javac` produces a single `Sample.class` file. The program reads that exact **single byte array** from the file and passes the same byte array to two `CopyLoader` instances.
2. `loaderA.defineCopy` and `loaderB.defineCopy` create two different `Class<?>` objects. Both classes have the binary name `Sample`, but each class has its own defining loader.
3. `a` is created from `typeA`; `b` is created from `typeB`. Therefore, `typeA.isInstance(a)` is `true`, while `typeA.isInstance(b)` is `false`.
4. The cast `(Sample) a` uses the `Sample` type seen by the **application loader** when compiling and running `TypeIdentityDemo`. That type is not `typeA`, so the JVM throws `ClassCastException`. Having the same name does not create an inheritance relationship or cast compatibility.
5. The two child loaders at the end use the default `loadClass` and both delegate to the application loader. `Class.forName` therefore returns the same `Class<?>` object, so `delegatedSame=true`.

In this example, the `defineCopy` method **deliberately calls `defineClass`** to demonstrate the rule; it is not a complete plugin loader. A loader used in production needs to manage concurrent loading, caching of loaded classes, delegation scope, and proper lifecycle. Do not call `defineClass` a second time with the same binary name in the same defining loader: a duplicate definition operation will fail with `LinkageError`.

## 4. Why can't the JVM treat them as one?

The JVM must guarantee type safety. Two class versions with the same name can have **different** bytecode, fields, methods, business semantics, or access permissions. If they were treated as one just because of the same name, code from one plugin could mistake an object from another plugin for a compatible object.

Looking from type checks:

- `typeA == typeB` or `typeA.equals(typeB)`: `false` when the two `Class` objects are different.
- `typeA.isInstance(objectFromB)`: `false` if B is not a subtype/implementation compatible with A.
- `typeA.isAssignableFrom(typeB)`: `false` if there is no compatible inheritance or interface implementation relationship.
- Casting to a class with the same name but a different runtime identity: usually causes `ClassCastException`.
- Reflection may report an incompatible argument error when an object is created from a class version from another loader; comparing display names in logs is not enough to infer type equality.
- When the JVM must link field/method signatures across loaders and detects a type conflict in a descriptor, it can also raise a `LinkageError` related to **loader constraints** (`5.3.4). Not every loader mismatch manifests as a `ClassCastException`.

An important exception: two classes from different loaders **can still both implement an interface defined in a common parent**. In that case, both objects can be cast to the shared interface, because the interface is a unified runtime type.

## 5. Runtime package, array, and module

**Runtime package** also depends on the loader: from the JVM's perspective, it is identified by **(package name, defining loader)**. Two classes that both declare `package com.example;` but are defined by two separate loaders will belong to **two different runtime packages**. As a result, package-private access permissions (and related access checks) cannot be inferred solely from the package name written in source code. With the Java Platform Module System (JPMS), module readability and exported/open packages are additional access checks; the module name **does not replace** the type identity pair mentioned above.

**Arrays** are a special case: the JVM directly creates array classes when needed, and an array class of a reference type is tied to the defining loader of its element type. Therefore, `Sample[]` created from two `Sample` versions of different loaders are also two incompatible array types. Arrays with primitive elements are not tied to a user-created loader; `int[].class.getClassLoader()` returns `null`. Primitives such as `int.class` and `void.class` are not defined by bytecode via a custom loader like normal classes.

You should not interpret `Class.getName()` of an array as being like the binary name of a normal class: for example, `String[].class.getName()` is `[Ljava.lang.String;`, and `int[].class.getName()` is `[I`.

## 6. Real-world scenarios and design approaches

### Plugins and containers with isolated loaders

An application server or plugin system may use a separate loader for each plugin, version, or hot reload. Two plugins that both bundle `com.example.model.Event` will create two incompatible `Event` types if each loader defines that class itself. Passing an `Event` instance from plugin A to a component expecting plugin B's `Event` easily causes a cast error.

A more stable design is to separate the contract (API) and the implementation:

```text
Application loader
  +-- com.example.api.PluginApi       (shared API: defined once)
        ^
        |
  +-----+---------------------------+
  |                                 |
PluginLoader A                    PluginLoader B
  +-- com.example.a.PluginImpl       +-- com.example.b.PluginImpl
      implements PluginApi               implements PluginApi
```

- Place the **API/interfaces/DTOs that need to be exchanged across boundaries** in the parent or a shared loader; ensure all children delegate that API part to the same defining loader.
- Keep **implementations and private dependencies** in each plugin's loader when isolation is needed. Avoid repackaging the shared API into each plugin and defining it separately.
- When exchanging data between two loader regions that have no shared type, use a neutral format or explicit conversion (for example JSON) with a consistent data contract; do not force blind casts.
- Hot reload creating a new loader usually means **new runtime types**. Old objects do not automatically turn into instances of the new version, even if the class has the same name; a replacement policy and releasing old references are needed.

### Reflection, SPI, and thread context class loader

`Class.forName("com.example.Plugin")` does not automatically guarantee finding the right loader in a plugin system. When you need to choose a loader, use the `Class.forName(name, initialize, loader)` overload or the appropriate framework class-loading API. **The passed-in loader may delegate**, so always verify `result.getClassLoader()` when diagnosing.

Some libraries use the **thread context class loader** via `Thread.currentThread().getContextClassLoader()` to locate providers or resources. The context loader is a **mechanism for choosing where to start searching**, not something that automatically determines the identity of an already-defined class. When temporarily changing the context loader, you must restore it according to the appropriate lifecycle so it does not affect other tasks.

## 7. Diagnostic workflow when encountering duplicate class name errors

When encountering a message like "X cannot be cast to X" or a confusing `ClassCastException`, follow this order:

1. Identify the **two actual `Class<?>` objects** of the source value and the target type, not just the two name strings from the log.
2. Record `getName()`, `getClassLoader()`, `getModule()`, and where the bytecode was loaded from (`getProtectionDomain().getCodeSource()` if available). `CodeSource` or the file path indicates the probable source, **it does not determine** type identity.
3. Compare the class objects using `==`, compare the defining loaders of the two classes, then check `isInstance`/`isAssignableFrom` if appropriate.
4. Trace the delegation path: which loader defines the shared API, and which loader defines the implementation? Was a JAR containing the API copied/shaded into the plugin? Is there a new loader instance after a redeploy?
5. Fix it at the **class-loading boundary and API contract**; do not use reflection or forced casts to hide the incompatibility.

The following observation helper is an **illustrative method**, which can be placed into a Java program being debugged (not a standalone file):

```java
static void describeType(Object object) {
    Class<?> type = object.getClass();
    System.out.println("name   = " + type.getName());
    System.out.println("loader = " + type.getClassLoader());
    System.out.println("module = " + type.getModule());
}
```

With HotSpot/JDK 17+, you can enable class loading logs at runtime:

```bash
java -Xlog:class+load=info TypeIdentityDemo
```

The actual log is multi-line and depends on the JDK version; do not treat the log format string as a stable interface. You can use `jcmd <PID> VM.classloaders` on supported HotSpot/JDKs to inspect the loader hierarchy; this command requires a running process. Class loading logs help with investigation, but **comparing `Class<?>` and defining loaders within the same JVM** remains the most direct verification.

## 8. Common misconceptions

| Misconception | Correction |
| --- | --- |
| "Two classes with the same fully-qualified name are always the same type." | The name is only half of it; there is also the defining loader. |
| "Two byte-for-byte identical `.class` files can be cast to each other." | Identical bytecode does not guarantee runtime type identity. |
| "Two objects of the same `URLClassLoader` class are equivalent." | Two loader **instances** that define independently still create separate types. |
| "Calling load through two child loaders is guaranteed to produce two types." | If both delegate to one parent, they can receive the same `Class<?>`. |
| "`getClassLoader() == null` means the class has no loader." | For many core types, that value represents the bootstrap loader. |
| "Two classes with the same package name always have package-private access to each other." | The runtime package also depends on the defining loader; JPMS has separate checks. |
| "`ClassNotFoundException` and `ClassCastException` are the same problem." | One error is about failing to find/load a type in context, the other is about type incompatibility during a cast; they need to be checked separately. |

## 9. Self-check

1. L1 and L2 both load `org.demo.Api` by delegating to the same parent P, while P is the loader that defines the class. Are the two `Class<?>` results equal? **Yes**: same binary name and same defining loader P.
2. L1 and L2 independently define two versions of `org.demo.Api` from **the exact same byte array**. Are the two results equal? **No**: two different defining loaders.
3. A plugin reloads and creates a new loader while keeping the old class name and bytecode. Can an instance from before the reload be cast to the post-reload version? **You cannot assume it can**; if each loader defines the type itself, they have different runtime identities.
4. Two implementations live in two separate plugin loaders, but both implement the `PluginApi` interface defined by the parent. Can the `PluginApi` type be used to call both? **Yes**, provided each plugin implements the exact **same `Class` of `PluginApi`** and all other access/linking conditions are valid.

**Takeaway:** When asking "Are these two Java classes the same type?", ask **"What is the binary name, and which loader defined each class?"**; when designing plugin boundaries or hot reload, share the API in the same defining loader to avoid breaking type identity.

### Official references

- [JVMS Java SE 21, `5.3 Creation and Loading, `5.3.3 Arrays, `5.3.4 Loading Constraints](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html)
- [Java SE 21 API: `ClassLoader`, `loadClass`, and `defineClass`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassLoader.html)
# Same Class Name Does Not Guarantee Same Class with Different Class Loaders

## 1. The Problem: Identical Names Yet Two Distinct Types to the JVM

In Java, two objects can print the **exact same fully qualified class name** and yet not belong to **the same class at runtime**. This happens when bytecode with the same binary name is **defined by two different class loaders**.

For example, a plugin and the host application both contain the file `com.example.model.Customer.class`. If each side defines its own copy, both objects may report:

```text
com.example.model.Customer
```

via `getClass().getName()`. However:

```java
left.getClass().getName().equals(right.getClass().getName()) // true
left.getClass() == right.getClass()                          // false
```

This is an **illustrative fragment**; two corresponding objects `left` and `right` are required. The reason is that **a `String` name is not a unique identifier of a class**.

The core rule for ordinary reference types in the JVM is: a class is identified by its **binary name** combined with its **defining class loader**. Having the same name with **different defining loaders** makes them two distinct runtime types.

This directly affects `getClass()`, `instanceof`, casting, reflective method calls, overloads accepting specific types, `equals()`, and many collections/APIs that depend on object type.

## 2. Distinguishing Class Name, `Class` Object, and Class Loader

### Binary Name and `Class<?>` Object

`Class.getName()` returns a string describing the binary name of an ordinary class, such as `java.lang.String` or `com.example.Customer`. For nested classes, the binary name contains `$`, such as `Example$Value`.

`Class<?>` is not merely a name string. It is the runtime representation of a concrete type loaded/defined by the JVM. Two classes with the same `getName()` can still be represented by **two separate `Class` objects**.

```java
Class<?> typeA = objectA.getClass();
Class<?> typeB = objectB.getClass();

boolean sameText = typeA.getName().equals(typeB.getName());
boolean sameRuntimeType = typeA == typeB;
```

The variables `objectA`/`objectB` are assumed for this fragment. When you only need to know whether two objects have the **exact same runtime type**, comparing `getClass()` with `==` (or `Class.equals`) is correct. Do not use `getName().equals(...)` as a substitute for type checking.

### What Is a Defining Class Loader?

A `ClassLoader` can locate bytecode and call `defineClass(...)` to create a class in the JVM. **Which loader actually defines the class** is part of the type's identity. Another loader may **request to load** the class and receive the class defined by a parent loader; in that case, the requesting loader is not the defining loader.

```java
ClassLoader definingLoader = typeA.getClassLoader();
```

For classes defined by the bootstrap class loader, `Class.getClassLoader()` typically returns `null`; `null` here does not mean the class is unloaded.

The JVM can also have multiple loaders of the same Java class/type that are **different instances**. Those two instances can define two different runtime copies of a class name.

> Rule to remember: **fully qualified name + defining loader**, not just `.class` filename, package name, JAR path, or module name.

## 3. Why Can Different Class Loaders Load the Same Name?

Java normally uses the **parent delegation** model: a loader asked to load a class first tries via its parent; if the parent has already loaded/defined the appropriate class, child loaders can receive the exact same `Class` object. Therefore, **two different loaders do not automatically mean two different classes**.

Plugin systems, application servers, containers, IDEs, reload tools, or isolated environments can use custom loading strategies. A **child-first loader for a selected set of names** can define its own copy instead of taking the existing one from the parent.

| Scenario | Possible Outcome |
| --- | --- |
| Two child loaders both delegate to the same parent loader that already defined `SharedType` | Receive the **same** `Class` object, no type-identity conflict |
| Two different loaders each call `defineClass` for the same name `PluginType` | Produce **two** distinct `Class` objects |
| A loader that already defined a name tries to define the same name again in that same loader | Cannot create two independent classes with the same name in the **same defining loader**; may throw `LinkageError` |
| Two JAR copies contain the same class name | Nothing conclusive yet without knowing which loader actually defined the class |

Therefore, you should not infer type identity just from seeing two JARs or two `ClassLoader`s. You must observe the **actual `Class<?>` of the object**, along with `getClassLoader()`, in the runtime context.

## 4. Java 17: Demonstrating Two Loaders Defining the Same Bytecode

This example intentionally creates **two custom loader instances**, each independently defining the nested class `ClassLoaderIdentityDemo$Value` from the same `.class` bytecode. Aside from the `Value` class, other names are still delegated to the parent loader. Thus the two `Value` classes are two distinct types, while both can implement **a shared interface** `CodeView` defined by the parent loader.

Create a single file `ClassLoaderIdentityDemo.java` with the following contents:

```java
import java.io.IOException;
import java.io.InputStream;
import java.util.Objects;

public class ClassLoaderIdentityDemo {

    public interface CodeView {
        String code();
    }

    public static class Value implements CodeView {
        private final String code;

        public Value(String code) {
            this.code = Objects.requireNonNull(code);
        }

        @Override
        public String code() {
            return code;
        }

        @Override
        public boolean equals(Object other) {
            if (this == other) {
                return true;
            }
            if (other == null || getClass() != other.getClass()) {
                return false;
            }
            Value that = (Value) other;
            return code.equals(that.code);
        }

        @Override
        public int hashCode() {
            return code.hashCode();
        }
    }

    static class IsolatedValueLoader extends ClassLoader {
        private final String targetName;
        private final byte[] targetBytes;

        IsolatedValueLoader(ClassLoader parent, String targetName,
                            byte[] targetBytes) {
            super(parent);
            this.targetName = targetName;
            this.targetBytes = targetBytes.clone();
        }

        @Override
        protected Class<?> loadClass(String name, boolean resolve)
                throws ClassNotFoundException {
            if (!name.equals(targetName)) {
                return super.loadClass(name, resolve);
            }

            synchronized (getClassLoadingLock(name)) {
                Class<?> loaded = findLoadedClass(name);
                if (loaded == null) {
                    loaded = defineClass(
                            name, targetBytes, 0, targetBytes.length);
                }
                if (resolve) {
                    resolveClass(loaded);
                }
                return loaded;
            }
        }
    }

    public static void main(String[] args) throws Exception {
        String binaryName = Value.class.getName();
        String resourceName = "/" + binaryName.replace('.', '/')
                + ".class";

        byte[] bytes;
        try (InputStream stream =
                ClassLoaderIdentityDemo.class.getResourceAsStream(
                        resourceName)) {
            if (stream == null) {
                throw new IOException("Missing class resource: "
                        + resourceName);
            }
            bytes = stream.readAllBytes();
        }

        ClassLoader parent =
                ClassLoaderIdentityDemo.class.getClassLoader();
        ClassLoader loaderA =
                new IsolatedValueLoader(parent, binaryName, bytes);
        ClassLoader loaderB =
                new IsolatedValueLoader(parent, binaryName, bytes);

        Class<?> typeA = Class.forName(binaryName, true, loaderA);
        Class<?> typeB = Class.forName(binaryName, true, loaderB);
        Object a = typeA.getConstructor(String.class).newInstance("X");
        Object aAgain = typeA.getConstructor(String.class)
                .newInstance("X");
        Object b = typeB.getConstructor(String.class).newInstance("X");
        Value host = new Value("X");

        System.out.println("same binary name: "
                + typeA.getName().equals(typeB.getName()));
        System.out.println("same Class object: " + (typeA == typeB));
        System.out.println("same defining loader: "
                + (typeA.getClassLoader() == typeB.getClassLoader()));
        System.out.println("loader A owns type A: "
                + (typeA.getClassLoader() == loaderA));

        System.out.println("same-loader objects equal: "
                + a.equals(aAgain));
        System.out.println("cross-loader objects equal: "
                + a.equals(b));
        System.out.println("same hash allowed: "
                + (a.hashCode() == b.hashCode()));
        System.out.println("a instanceof host Value: "
                + (a instanceof Value));
        System.out.println("a implements shared CodeView: "
                + (a instanceof CodeView));
        System.out.println("shared interface call: "
                + ((CodeView) a).code());
        System.out.println("host equals a: " + host.equals(a));

        try {
            Value impossible = (Value) a;
            System.out.println(impossible.code());
        } catch (ClassCastException e) {
            System.out.println("host Value cast failed: true");
        }
    }
}
```

Compile and run in the same directory using JDK 17 or higher:

```bash
javac ClassLoaderIdentityDemo.java
java ClassLoaderIdentityDemo
```

Note: you must keep the `ClassLoaderIdentityDemo.class`, `ClassLoaderIdentityDemo$Value.class`, and `ClassLoaderIdentityDemo$CodeView.class` files produced by `javac` on the classpath at runtime. The program reads the bytes of the nested `Value` class via a class resource, and does **not** depend on any absolute directory path on disk.

Output:

```text
same binary name: true
same Class object: false
same defining loader: false
loader A owns type A: true
same-loader objects equal: true
cross-loader objects equal: false
same hash allowed: true
a instanceof host Value: false
a implements shared CodeView: true
shared interface call: X
host equals a: false
host Value cast failed: true
```

### What Happened?

1. `Class.forName(binaryName, true, loaderA)` requests loading the name through `loaderA`. Because the loader handles **only** `Value` itself, it calls `defineClass` for that name. `loaderB` does the same, creating another definition.
2. Both `typeA.getName()` and `typeB.getName()` have the same string name `ClassLoaderIdentityDemo$Value`, so "same binary name" is `true`.
3. `typeA == typeB` is `false` and their defining loaders differ as well. Even though the bytes are identical, the classes in the JVM are distinct because their defining loaders differ.
4. `a` and `aAgain` are both created from `typeA`. `Value.equals` sees the same class and the same `code = "X"`, so it returns `true`.
5. `a.equals(b)` returns `false`: object `b` belongs to the definition created by `loaderB`. The condition `getClass() != other.getClass()` blocks casting to `a`'s `Value` type.
6. `a.hashCode() == b.hashCode()` is `true` because both hash the string `"X"`; this **does not prove the two objects are equal**. The hash contract only mandates the direction `equals() == true => same hashCode()`.
7. `a instanceof Value` is `false` because `Value` on the right-hand side is compiled referencing the **application loader's** version. This is a runtime type check, not a string-name comparison.
8. `a instanceof CodeView` is `true` because both versions of `Value` reference the single `CodeView` defined by the parent. Casting to the shared interface works and calling `code()` returns `"X"`.
9. Casting `a` to the application's `Value` throws `ClassCastException`. The program prints a fixed line in `catch` rather than the full exception message because how loaders are formatted in the exception may depend on the JVM version.

**The sole purpose of the custom loader is to illustrate type identity.** This is not a complete plugin class loader: production systems must also manage name scopes, resources, security, reference unloading, caching, and many other compatibility issues. Parent delegation should not be replaced indiscriminately for every class.

## 5. Why Do `getClass()` and `instanceof` React Differently from Name Comparison?

### `getClass()` Shows the True Runtime Type

`getClass()` returns the exact `Class` object representing the instance's actual type. When checking with:

```java
if (other == null || getClass() != other.getClass()) {
    return false;
}
```

an **exact-class** `equals` implementation rejects objects defined by another loader, even when data fields and class names are identical.

That fits many **value classes that do not support cross-class equality**. Yet `getClass()` is not a mandatory condition for every `equals`: interface-contract types such as `List`/`Set`/`Map` can define equality across implementing classes. Choose the strategy based on **logical identity**, rather than applying a single formula across all of Java.

### `instanceof` Uses Type Relationships, Not Names

`obj instanceof SomeType` is true only when `obj`'s runtime type is `SomeType` or a compatible subtype/implementation of **the exact `Class` object corresponding to `SomeType`**. Sharing the same `getName()` does not create an inheritance relationship.

```java
boolean exactType = obj.getClass() == SomeType.class;
boolean compatible = obj instanceof SomeType;
```

The fragment assumes `obj` is non-null and `SomeType` is in compile-time scope. The first check requires the **exact runtime class**; the second allows valid subclasses/implementations. Neither matches by text name.

In the example, `loaderA`'s `Value` is **not** a subclass of the application loader's `Value`, so `instanceof Value` fails. Yet both can implement the shared-loaded `CodeView`, so `instanceof CodeView` succeeds.

## 6. Confusing `ClassCastException`: "cannot cast X to X"?

This is a common symptom in plugin environments or application servers. An error message may look like:

```text
class com.example.Customer cannot be cast to class com.example.Customer
```

Additional JVM details may mention the actual modules and loaders. The crucial point is that **two identically displayed names do not necessarily describe the same runtime type**.

When encountering this issue, do not compare only `getName()`. Collect per object:

```java
Class<?> c = value.getClass();
System.out.println("type=" + c.getName());
System.out.println("loader=" + c.getClassLoader());
System.out.println("module=" + c.getModule());
```

This is a diagnostic fragment assuming `value` is non-null. Be careful when putting this information into production logs (do not expose classpath, deployment structure, or sensitive data through public messages).

**Investigation tip:** compare the two `Class` objects themselves, use `getClassLoader()` to observe the defining loader, and then determine the loading path that was taken. A loader's `toString()` string is auxiliary info; do not use it as proof of loader object identity.

## 7. Must Two Sides Share the Same Loader to Communicate?

No. Two plugins with their own internal classes can still collaborate through a **shared API** defined by the same parent loader. The illustration in Section 4 is `CodeView`:

- `CodeView` is loaded/defined by the shared parent loader.
- Both `loaderA`'s `Value` and `loaderB`'s `Value` implement **the exact same runtime `CodeView`**.
- You can accept them as `CodeView` and call `code()` without casting to the other plugin's `Value`.

A typical system design places API interfaces, shared DTOs, or message types in a parent classpath/module layer visible to all plugins. Plugin-specific implementation types stay internal and do not leak across boundaries. When passing data without sharing implementation classes, you can use stable interfaces, primitives/`String`, or a serialization format with a clear schema.

**Note:** Two interfaces simply having the same name is not enough. If each loader also defines its own `com.example.Api`, they are once again **two different runtime interfaces**, and casting to the interface on the other side still fails. You must truly share **the same runtime definition of the API**, not just copy source code/JARs.

## 8. Class Loaders, `equals()`, and `hashCode()`

There are two designs to distinguish:

### Equality by Actual Type

A value class can require `getClass() == other.getClass()` before comparing fields. As in the example, instances with the same name in different loaders are not considered equal; this avoids unsafe casts and matches type identity.

### Equality by a Shared Interface

An API can define an equality relation across implementations, but great care is required: both sides must uphold **symmetry, transitivity, consistency, and `hashCode()`**.

For example, if one side compares using `getClass()` and the other compares solely by `CodeView.code()`, the following can occur:

```text
a.equals(b) = false
b.equals(a) = true
```

That violates **`equals` symmetry**. If logical data needs to be compared across plugins, a safer approach is usually to extract a **shared immutable key** or compare values from the shared API using a separate comparator/method, rather than requiring two implementation classes to write cross-loader-compatible `equals`.

Do not write code like:

```java
// WRONG ABOUT TYPE IDENTITY CHECKING:
if (other.getClass().getName().equals(getClass().getName())) {
    // Casting to the current class is NOT safe.
}
```

This is **a fragment intentionally illustrating a bug**; it also lacks a null check. Matching names does not prove castability, does not prove identical field layouts, and does not allow treating the objects as the same type.

Regarding `hashCode`, two objects from different class loaders can share the same hash even when `equals` differs. There is no requirement that "different classes must have different hashes". Only when two objects **are allowed to be equal under the contract** are equal hashes required.

## 9. Distinguishing Class Loaders from Packages, JARs, and Java Modules

Do not confuse these concepts:

| Concept | Meaning | Sufficient to Identify Runtime `Class`? |
| --- | --- | --- |
| Class/package name | Identifier string in bytecode | **No**, defining loader also matters |
| File/JAR name | Container holding resources or bytecode | **No**, one JAR can be used by multiple loaders |
| Class loader | Object participating in loading/defining classes | Combined with class name to identify an ordinary runtime type |
| Java Platform Module System (JPMS) | Describes modules, readability, exported/opened packages | Affects accessibility/lookup, but does not replace checking `Class` identity and defining loader |

In modular applications, the module associated with a class can be inspected with `Class.getModule()`. Do not infer that the same module name or same package name guarantees the same `Class`. Conversely, seeing different modules is not yet a complete explanation for a `ClassCastException` without checking the actual loader/type.

### `Class.forName` Does Not Always Create a New Class

`Class.forName(name)` typically uses the caller's associated loader. `Class.forName(name, initialize, loader)` lets you specify the loader asked to load the class. However, the specified loader **can delegate**, returning a class defined by the parent; it does not automatically create a second copy.

The example above only created two copies because `IsolatedValueLoader.loadClass` intentionally **called `defineClass` itself for the target name**. For other names, the loader still used `super.loadClass` and normal delegation.

## 10. Implications for Reflection, Collections, and Plugin Architecture

### Does Reflection Need the Exact `Class` Object?

Yes. When looking up constructors/methods with specific parameter types, Java reflection works with **runtime types**, not just name strings. If an API expects `com.example.Customer` defined by a parent loader while a caller supplies a same-named `Customer` defined by an isolated plugin loader, casting or finding a method with that parameter type can fail.

Messages like `NoSuchMethodException`, `IllegalArgumentException` when passing reflective arguments, or `ClassCastException` can be symptoms of a **runtime type mismatch**. Do not try to work around it by comparing class names and forcing a cast.

### Do Collections Automatically Merge Two Classes with the Same Name?

No. `HashSet` and `HashMap` use `equals()`/`hashCode()` of elements or keys; if those methods distinguish class loaders, two values with the same name and data can be treated as two separate keys.

If you want to use keys across class-loader boundaries, use a key type from the shared API (such as `String`, `UUID`, or a commonly defined immutable DTO). Ensure `equals` and `hashCode` of the key type are consistent, rather than depending on implementation class names.

### Class Loaders and Plugin Unloading

Live references to objects, `Class<?>`, loaders, thread context class loaders, static caches, or registries can keep a class loader and its classes reachable, preventing the system from unloading old plugin versions. When designing hot reload/unload, manage lifecycles and clear references holding the loader. This is an additional operational note, not a criterion for equality.

## 11. Diagnostic Workflow for "Same Name Yet Cast Fails"

1. **Obtain both exact objects/types:** the actual object and the target type of the cast or method parameter.
2. **Print `getName()`:** verify whether the binary names match.
3. **Compare `Class` objects directly:** `actualType == expectedType` and, if inheritance is involved, `expectedType.isAssignableFrom(actualType)`.
4. **Inspect `getClassLoader()` and `getModule()`:** record the defining loader, module, and classpath context as needed.
5. **Check the loading path:** parent delegation vs. custom loader, duplicate JARs, or whether a plugin also packaged the shared API.
6. **Check the API boundary:** whether an implementation type is being passed across an interface/DTO loaded twice separately.
7. **Fix in the class-loading architecture:** share the API properly in a common loader, avoid bundling duplicate copies of shared classes inside each plugin, or convert data into intermediate values with a clear schema.
8. **Recheck both casts and `equals`/`hashCode`:** if loading policy or key types change, collections, reflection, and integration tests must align.

Type-compatibility diagnostic fragment:

```java
Class<?> actual = value.getClass();
Class<?> required = SomeApiType.class;

System.out.println(actual.getName());
System.out.println(required.getName());
System.out.println(actual == required);
System.out.println(required.isAssignableFrom(actual));
```

This is an illustrative snippet; `value` and `SomeApiType` must exist in the calling code. `isAssignableFrom` determines type assignability according to the runtime type hierarchy, not just class names.

## 12. Knowledge Self-Check

**Question 1.** Two `Class<?>` objects have the same `getName()`, yet `getClassLoader()` returns two different instances. Can we conclude their `Class` objects are equal?

**Answer:** No. If those are two actual different **defining loaders** for the same class name, they are two separate runtime types. If you only know that two loaders were used to **request loading**, both might delegate to the same parent-defined class, so you must inspect the returned `Class<?>`.

**Question 2.** Why can two plugins share an interface yet be unable to cast directly to each other's implementation?

**Answer:** The same interface **defined by a common loader** is a single runtime type; each implementation can still be a separate type defined by its plugin loader. Casting to the shared interface is valid; casting to the other copy's implementation is invalid.

**Question 3.** Is `getClass().getName().equals(...)` a safe replacement for `getClass() == ...` in `equals()`?

**Answer:** No. Name strings can match while types belong to different loaders; using the name can allow an unsafe cast branch, altering semantics and causing `ClassCastException`.

**Question 4.** Can two unequal objects have the same `hashCode()`?

**Answer:** Yes. Collisions are normal and do not violate the contract. Equal hashes are only mandatory when `equals()` returns `true`.

**Question 5.** Do `Class.forName(name, true, loaderA)` and the same call with `loaderB` always return two different classes?

**Answer:** No. If both loaders delegate to the same defining loader, they can return the exact same `Class` object. You must look at how the loaders are implemented.

## Key Takeaway

**A class's identity in the JVM is not determined by name alone.** For ordinary reference classes, the binary name combined with the **defining class loader** determines the runtime type. Thus same-named classes from different loaders may fail to cast to one another, fail `instanceof`, and yield two distinct `Class` objects from `getClass()`. To avoid bugs in plugin/module systems, share common APIs through a unified runtime definition, inspect `Class<?>` and the defining loader rather than comparing names alone, and separate business equality relations from implementation identification.
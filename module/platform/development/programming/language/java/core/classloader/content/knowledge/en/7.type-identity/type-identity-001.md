# Class Identity by Binary Name and Defining Loader

> **Topic:** Java Core → ClassLoader → Type Identity. In the JVM, the class name is only **half** of the runtime type identity: for ordinary classes/interfaces, the JVM distinguishes them by the pair **(binary name, defining class loader)**. This is the basis for understanding why the same `.class` file loaded through two loaders can produce two incompatible types.

## 1. Why can the same class name still be two different types?

Suppose both plugins contain the `demo/Token.class` file compiled from the same Java source:

```java
package demo;
public class Token {
    public String value() { return "ok"; }
}
```

You have two `Class<?>` instances, called `a` and `b`, that both return `"demo.Token"` when calling `getName()`. That information alone is **not enough to assert `a == b`**.

According to the JVM Specification `5.3`, once created, a class or interface (other than an array) is identified by:

```text
Runtime type identity = (binary name, defining class loader)

("demo.Token", loader A) != ("demo.Token", loader B)
("demo.Token", loader A) == ("demo.Token", loader A)
```

The two lines of notation above express the **type identity** rule, not standalone runnable Java expressions. When different loaders **actually define** the same binary name, the JVM creates two different runtime types, even though the `.class` bytes may be identical, the JAR path is the same, and the Java source is the same.

Therefore:

- `a.getName().equals(b.getName())` can be `true`.
- `a == b`, `a.equals(b)` can be `false` (for `Class`, `equals` uses object identity).
- An object created from `a` is typically not accepted by `b.cast(object)`.
- `a.getClassLoader()` and `b.getClassLoader()` indicate the **defining loader** of each type, not merely "the loader that was called to find the class".

This is not an error caused by two classes being in different packages. **Even when both the package and binary name are identical**, a different defining loader still creates a difference in runtime type.

## 2. Binary name: the name component in the identity pair

*Binary name* is the name the JVM uses to identify ordinary classes/interfaces according to JLS `13.1` rules:

| Java Declaration | Binary Name | Notes |
| --- | --- | --- |
| `package demo; class Token {}` | `demo.Token` | Top-level class. |
| `package demo; class Outer { static class Inner {} }` | `demo.Outer$Inner` | Member class uses `$`. |
| `java.util.Map.Entry` | `java.util.Map$Entry` | In source code it is a member type name, while the binary name contains `$`. |
| Local/anonymous class | Usually has `$` and compiler-generated digits | Do not hardcode compiler-generated sequence numbers. |

Distinguishing the three name forms:

```text
Canonical Java name: demo.Outer.Inner
Binary name:         demo.Outer$Inner
JVM internal name:   demo/Outer$Inner
```

`Class.getName()` returns the binary name for **ordinary non-array, non-hidden reference classes/interfaces**. `Class.forName("demo.Outer$Inner")` or `loader.loadClass("demo.Outer$Inner")` looks up the member class by its binary name; the canonical string `"demo.Outer.Inner"` does not substitute for the binary name in that case.

**Scope:** arrays, primitives/void, and hidden classes have their own representations/semantics in the `Class` API. This article focuses on the identity of ordinary classes/interfaces; section 8 explains arrays and primitives to avoid incorrect generalizations.

## 3. Defining loader differs from initiating loader

When the JVM needs to create a type named `N`, it may ask a loader `L1` to find the class. This loader can:

1. **Define it itself:** read/generate the bytes and call `defineClass(...)`. In that case, `L1` is the *defining loader* of the new class.
2. **Delegate:** call another loader `L2` to load the name `N`. If `L2` is the one that actually calls `defineClass`, then `L2` is the *defining loader*, while `L1` only initiates loading through delegation.

The JVMS uses the terminology:

- **Defining loader:** the loader that **directly defines** the class/interface from its binary representation.
- **Initiating loader:** the loader that the JVM records as having **initiated** the corresponding class-loading process, either directly or through delegation.

Delegation example:

```text
Application requests "demo.Token" through pluginChild
                         |
                         v
               pluginChild.loadClass(...)
                         |
                         | parent delegation
                         v
                sharedParent.loadClass(...)
                         |
                         | reads Token.class + defineClass(...)
                         v
                   Class<demo.Token>
                   defining loader = sharedParent

pluginChild: initiating loader (may return Class defined by parent)
sharedParent: defining loader (also initiating loader)
```

Within the JVM model, loaders participating in the middle of a delegation chain **are not necessarily all recorded as initiating loaders**; do not treat "having `loadClass` called" as 100% synonymous with the JVM marking it as an initiating loader. You need to look at the runtime outcome and the rules in JVMS `5.3`.

For a `Class<?> c` instance:

```java
ClassLoader definingLoader = c.getClassLoader();
```

`getClassLoader()` returns the loader that **defines** the class, or `null` for a class defined by the bootstrap loader. It does not return a "most recently requested loader". If you query two child loaders and both delegate to a shared parent, you may get back **the exact same `Class<?>`**, because the defining loader does not change.

### Parent relationship does not directly determine type identity

`loader.getParent()` indicates the parent in the typical delegation tree; **parent loader and defining loader are not synonyms**. Only when a loader actually defines the class does the identity carry that loader. Parent-first is the common strategy of the default `ClassLoader.loadClass` and `URLClassLoader`, but custom class loaders may organize delegation differently with a clear purpose.

## 4. Proof with Java 17+: two URLClassLoader instances loading the same bytes

The experiment places the plugin class in a directory **not on the startup application's classpath**, then creates two independent loaders reading that same directory. To keep the example clear, both loaders use the platform loader as their parent; the plugin only requires standard Java APIs.

Create the structure:

```text
plugin-src/demo/Token.java
app-src/IdentityDemo.java
plugin-classes/    (generated by javac)
app-classes/       (generated by javac)
```

**File `plugin-src/demo/Token.java`:**

```java
package demo;

public class Token {
    public String value() {
        return "ok";
    }
}
```

**File `app-src/IdentityDemo.java`:**

```java
import java.lang.reflect.Array;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;

public class IdentityDemo {
    public static void main(String[] args) throws Exception {
        URL[] urls = {
                Path.of("plugin-classes").toAbsolutePath().toUri().toURL()
        };
        ClassLoader platform = ClassLoader.getPlatformClassLoader();

        try (URLClassLoader first = new URLClassLoader(urls, platform);
             URLClassLoader second = new URLClassLoader(urls, platform);
             URLClassLoader delegated = new URLClassLoader(new URL[0], first)) {

            Class<?> a = Class.forName("demo.Token", false, first);
            Class<?> b = Class.forName("demo.Token", false, second);
            Class<?> c = Class.forName("demo.Token", false, delegated);

            Object value = a.getDeclaredConstructor().newInstance();

            System.out.println("same binary name: "
                    + a.getName().equals(b.getName()));
            System.out.println("same Class: " + (a == b));
            System.out.println("distinct defining loaders: "
                    + (a.getClassLoader() != b.getClassLoader()));
            System.out.println("same loader returns same Class: "
                    + (a == Class.forName("demo.Token", false, first)));
            System.out.println("first accepts object: " + a.isInstance(value));
            System.out.println("second accepts object: " + b.isInstance(value));
            System.out.println("delegation returns first Class: " + (c == a));
            System.out.println("delegated is defining loader: "
                    + (c.getClassLoader() == delegated));
            System.out.println("array classes identical: "
                    + (Array.newInstance(a, 0).getClass()
                    == Array.newInstance(b, 0).getClass()));
            System.out.println("array loader first: "
                    + (Array.newInstance(a, 0).getClass().getClassLoader()
                    == first));

            try {
                b.cast(value);
                System.out.println("unexpected cast success");
            } catch (ClassCastException expected) {
                System.out.println("cross-loader cast: ClassCastException");
            }
        }
    }
}
```

Compile from the **parent directory** containing the two source directories:

```bash
javac -d plugin-classes plugin-src/demo/Token.java
javac -d app-classes app-src/IdentityDemo.java
java -cp app-classes IdentityDemo
```

Verified stdout on OpenJDK 21:

```text
same binary name: true
same Class: false
distinct defining loaders: true
same loader returns same Class: true
first accepts object: true
second accepts object: false
delegation returns first Class: true
delegated is defining loader: false
array classes identical: false
array loader first: true
cross-loader cast: ClassCastException
```

### Explanation of each result

1. `first` and `second` receive **the same `URL[]` and read the same bytes**; however, they are **two distinct loader objects**. Both define `demo.Token` themselves, creating two different runtime types.
2. `getName()` only checks the **binary name**, so it is `true`; `a == b` is `false` because the defining loaders differ.
3. Calling `Class.forName("demo.Token", false, first)` again returns the same `Class<?> a`. A properly operating loader does not create a second definition with the same binary name.
4. `a.isInstance(value)` is `true` while `b.isInstance(value)` is `false`; `b`'s `Class.cast` throws `ClassCastException`. **An object from one definition is not automatically an instance of the same-named definition in another loader**.
5. `delegated` has an empty URL array and its parent is `first`. When looking up `demo.Token`, it delegates to `first` and receives `a` itself. Therefore `c == a` is `true` while `c.getClassLoader() == delegated` is `false`: **initiating does not have to be defining**.
6. The two `demo.Token[]` types are also different; an array class has its identity tied to its **element type**. `Array.newInstance(a, 0)` creates an array whose defining loader is reflected as `first`.
7. `URLClassLoader` implements `AutoCloseable`, so it can be closed with try-with-resources. `close()` closes the resources opened by the loader; it **does not force the JVM to immediately unload** the classes that have already been defined.

Note that the experiment only loads the plugin via URLClassLoader at `plugin-classes`; do not add `plugin-classes` to `-cp`. If the class is visible to the parent first, parent-first delegation may return the class defined by the parent and cause the experiment to no longer demonstrate two different defining loaders.

## 5. Practical consequences: why do cast and instanceof fail?

Casting checks the **relationship between runtime types**, not the class name string. In the previous experiment, `a.isInstance(value)` is `true`, whereas `b.isInstance(value)` is `false` and `b.cast(value)` throws `ClassCastException`: both `a` and `b` bear the name `demo.Token` but are defined by two different loaders.

In plugin applications, a similar error occurs when both the host and the plugin package and **independently define** two copies of `api.Plugin`. Even though the plugin source states `implements api.Plugin`, the object only implements the version of the interface that its own loader linked against. Both sides need to share **the same `Class<?>` of the API contract** from a shared loader, or transfer data through a neutral protocol if isolation is intentional. The article on `ClassCastException` analyzes the stack trace and specific remediation procedures.

## 6. Runtime packages and access permissions also depend on the defining loader

A runtime package is identified by **(package name, defining loader)**. Two classes that both declare `package com.acme;` yet are defined by loaders A and B reside in **two different runtime packages**. Because of this, package-private does not automatically permit cross-access; when the JVM checks a symbolic reference, invalid access can lead to an `IllegalAccessError`.

`protected`, nestmates, and JPMS also have their own access rules. A module's `exports`/`opens` does not replace the same-runtime-package condition. The articles on runtime packages and package-private access carry out detailed access experiments.

## 7. How do defining loader and initiating loader affect linkage?

The JVM uses **loading constraints** to preserve type safety when linking fields, methods, overrides, or interfaces across loaders. For example, if two sides both use the name `com.acme.Message` in a method descriptor, yet each side's loader maps that name to a different `Class<?>`, this can violate a constraint and cause a `LinkageError`.

Distinguish three cases: two definitions with the same name **can coexist** when agreement is not yet required; a **wrong cast** usually reports `ClassCastException`; and **linking that requires the same type but is inconsistent** can report a loading constraint violation. The article on loading constraints goes deeper into the imposition conditions and verification timing.

## 8. Special cases: arrays, primitives, and bootstrap

For **arrays**, the JVM creates the array class when needed. `getClassLoader()` on an array of reference elements reflects the defining loader of its underlying element type; a primitive array has loader `null`. Therefore, two `demo.Token` classes with different identities produce two `demo.Token[]` types with different identities, even though the array names are identical.

The `Class<?>` objects for primitives and `void` (`int.class`, `void.class`) are provided by the JVM via a separate mechanism; you cannot use `loadClass("int")` to load them from a class file. Array descriptors, hidden classes, and special types require applying their corresponding rules rather than rigidly extrapolating from the binary name + defining loader pair of ordinary classes/interfaces.

## 9. Debugging pitfalls and how to verify them yourself

### Pitfall 1: Assuming logging only getName() is enough

Two `Class<?>` instances can have the same `getName()` while having different defining loaders. Log **both pieces of information** and check actual identity:

```java
// Place inside a method receiving two variables Class<?> left, right:
System.out.println("left name = " + left.getName());
System.out.println("right name = " + right.getName());
System.out.println("same class object = " + (left == right));
System.out.println("left defining loader = " + left.getClassLoader());
System.out.println("right defining loader = " + right.getClassLoader());
```

This is an illustrative snippet; `left` and `right` must come from the calling code. `ClassLoader.toString()` only assists with debugging, and is **not a durable identifier** to store in a database. `System.identityHashCode(loader)` likewise only provides a hash for observation; it can collide between two different objects, so it does not replace an `==` comparison.

### Pitfall 2: Thinking two URLClassLoaders pointing to the same JAR yield the same class

Two different loaders with the same `URL` can still define two separate classes. Only when **both requests are delegated to the same defining loader** do you get back the same class identity. File path, bytecode checksum, package, and `Class.getName()` do not by themselves determine identity.

### Pitfall 3: Using Class.forName without explicitly choosing the loader

`Class.forName(String)` uses the caller's loader rule; `Class.forName(String, boolean, ClassLoader)` lets you pass a specific loader. In plugins/containers, choosing the wrong loader easily causes `ClassNotFoundException` or creates/retrieves the wrong type with the same name.

`Thread.currentThread().getContextClassLoader()` (TCCL) is another loader mechanism, useful for SPIs/frameworks, but that **does not mean** it is always the defining loader of a class. To know which loader defined a class, use `clazz.getClassLoader()`.

### Pitfall 4: Trying to cast "the same interface source" between two loaders

If the host and plugin have two class copies of the same API, modifying the classpath configuration randomly does not guarantee unifying their identity. You should place the **common API in a shared loader**, avoid putting copies of the API into a private/plugin namespace, and check parent delegation.

### Pitfall 5: Thinking closing a loader makes classes immediately disappear

Closing a `URLClassLoader` does not reset the `Class<?>` instances or objects that have already been created. A thread context loader, cache, static field, thread, or hook may hold a strong reference, preventing the loader from being reclaimed yet.

## 10. Workflow for resolving loader conflicts in real projects

1. **Identify the two conflicting types.** From the `ClassCastException`, `LinkageError`, or plugin/container information, obtain both `Class<?>` instances if possible and compare `getName()`, `==`, and `getClassLoader()`.
2. **Find the definition source**: JAR/module paths, dependency graph, resource loading paths; check whether the host and plugin bundle duplicate APIs. `clazz.getProtectionDomain().getCodeSource()` can help, though it can also be `null` and does not determine class identity.
3. **Map out the actual delegation topology:** who calls `loadClass`, who the parent is, each loader's parent-first/child-first policy, and which loader actually calls `defineClass` for which class.
4. **Identify the types that need to be shared** across boundaries: interfaces, DTOs, exceptions, and return/parameter types in methods. Designate a single shared definition with a single shared loader.
5. **Ensure consistent bytecode/dependencies:** upgrade API versions, avoid silently creating duplicate copies, and check module readability/exports/opens when using JPMS.
6. **Reproduce with a small example** like `IdentityDemo` to prove exactly which (name, loader) pair differs. Do not guess from the class name printed in the error message.
7. **Re-verify using object identity and type checks**, then review class lifecycle/unloading if reload/hot deploy is involved.

On HotSpot, class-loading logs can help:

```bash
java -Xlog:class+load=info -cp app-classes IdentityDemo
```

The class-loading log lines show the loading process and class source at the current logging level; this is supplementary data and does not replace comparing `Class<?>` and defining loaders inside the app. Observability varies across JVMs/versions.

## 11. Self-check

1. **Are two `Class<?>` instances returning the same `"com.acme.Plugin"` from `getName()` necessarily equal?** No. They only share the same binary name; their defining loaders may differ.
2. **A child loader calls `parent.loadClass("demo.Token")` and returns the exact `Class<?>` object of the parent. Who is the defining loader?** The parent (if the parent directly defined the class). The child may be an initiating loader, but it is not the defining loader.
3. **If two child loaders both delegate a class to a common parent, can they return the same class?** Yes, if both return the class that was defined by the parent.
4. **If two loaders read the exact same byte-for-byte `Token.class` yet each calls `defineClass` itself, what is `a == b`?** `false`.
5. **Why does `Class.cast` throw `ClassCastException` even when both names are identical?** Because type checking uses runtime identity; a matching binary name is not enough.
6. **Do two classes in the same `package com.acme;` from two defining loaders belong to the same runtime package?** No; a runtime package is distinguished by both the package name and the defining loader.
7. **Does `Class.getClassLoader() == null` for `String.class` mean it has not been loaded yet?** No; that indicates the bootstrap loader.
8. **Do two classes with the same name necessarily cause `LinkageError` immediately?** No; they can coexist in different loaders. A loading constraint violation, repeated definition in the same loader, or an invalid usage operation causes an error depending on the case.
9. **Do two arrays whose element types are defined by different loaders have the same type?** No; the JVM ties array identity to the component type and its corresponding loader.

## 12. Authoritative references

- [JVMS `5.3` — Creation and Loading](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html#jvms-5.3): distinguishes defining/initiating loaders and defines runtime identity by the (binary name, defining loader) pair.
- [JVMS `5.3.3` — Creating Array Classes](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html#jvms-5.3.3): array classes are created by the JVM and use the defining loader of their component type.
- [JVMS `5.3.4` — Loading Constraints](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html#jvms-5.3.4): maintains type safety when linking across multiple loaders.
- [JLS `13.1` — The Form of a Binary](https://docs.oracle.com/javase/specs/jls/se21/html/jls-13.html#jls-13.1): binary name rules.
- [Java SE 21 `ClassLoader` API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassLoader.html): `loadClass`, `defineClass`, delegation, defining loader, and array classes.
- [Java SE 21 `Class` API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html): `getName`, `getClassLoader`, `isInstance`, and `cast`.
- [Java SE 21 `URLClassLoader` API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/URLClassLoader.html): URL-based loading, parent delegation, and `close`.

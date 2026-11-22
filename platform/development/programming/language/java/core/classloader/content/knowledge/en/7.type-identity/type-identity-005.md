# A runtime package is determined by the package name and class loader

In Java, two classes that both declare `package demo;` do not necessarily belong to the **same runtime package**. According to the *Java Virtual Machine Specification* (JVMS), the runtime package of a class or interface is determined by its **package name and defining class loader** (the loader that actually defines the class). Therefore, if two different loaders define classes with the exact same package name, they still belong to **two different runtime packages**.

This rule is critical for `classloader` design, plugins, application servers, bytecode generation, and libraries that use multiple dependency versions, because it directly affects **package-private** access, class identity, and runtime linkage errors.

## 1. Distinguishing source package and runtime package

In Java source code, the declaration:

```java
package com.example.domain;
```

specifies the package name `com.example.domain`. In ordinary programming, files in the same package can access each other's package-private members if other conditions are also met.

However, the JVM must handle classes that may be defined by multiple class loaders. As a result, it needs to know not only the package name, but also the loader that defined the class:

```text
Runtime package identity =
    (package name, defining class loader)
```

For example:

```text
Class A:
  binary name       = demo.One
  package name      = demo
  defining loader   = Loader-Parent

Class B:
  binary name       = demo.Two
  package name      = demo
  defining loader   = Loader-Child

Runtime package A = (demo, Loader-Parent)
Runtime package B = (demo, Loader-Child)

Conclusion: runtime package A != runtime package B
```

Even though both have the `package demo;` statement, they are **not** considered by the JVM to be in the same runtime package.

Conversely, if both classes are **defined by the same loader**, they share the same package name and the same runtime package, even if their source files reside in two different project directories or two different JARs. Sharing a package within the same loader may still be further constrained by sealing rules, modules, and environment configuration; it does not mean those rules can be bypassed.

### Three concepts to keep distinct

| Concept | Identity / how it is determined | Example |
|---|---|---|
| **Binary name** | Binary name of the class/interface | `demo.One` |
| **Runtime class** | `(binary name, defining loader)` | `(demo.One, Loader-A)` |
| **Runtime package** | `(package name, defining loader)` | `(demo, Loader-A)` |

An important distinction: two classes with **different names**, such as `demo.One` and `demo.Two`, can share the same runtime package if they have the same defining loader; two classes with the **same name**, such as `demo.One` defined by two different loaders, are both two different runtime classes and belong to two different runtime packages.

## 2. Defining loader vs. initiating loader

When calling:

```java
Class<?> type = childLoader.loadClass("demo.One");
```

you cannot immediately infer that `childLoader` is the defining loader of `type`.

By default, `ClassLoader.loadClass` uses **parent delegation**: it checks for an already-loaded class, delegates to the parent first, and only calls `findClass` on the child if the parent cannot load it. Thus:

```text
childLoader.loadClass("demo.One")
        |
        v
parentLoader.loadClass("demo.One")
        |
        +--> if parent finds it:
              type.getClassLoader() == parentLoader
              child is only an initiating loader that can recognize the type
```

In the JVMS:

- **Defining loader** is the loader used to actually define the runtime class, for example via `defineClass`.
- **Initiating loader** is the loader that initiated loading a class through delegation or was recorded by the JVM during loading. A loader can be an initiating loader of a class defined by another loader.
- Runtime class and runtime package identity are based on the **defining loader**, not on whichever loader object happened to be called in a `loadClass` expression.

Useful inspection APIs:

```java
ClassLoader definingLoader = someType.getClassLoader();
String packageName = someType.getPackageName();
```

These are illustrative statements assuming you already have a `someType` variable of type `Class<?>`. `getClassLoader()` may return `null` when the JVM represents the bootstrap loader. `getPackageName()` returns the **package name string**, not the full runtime package identity.

If you need to compare two loaded classes:

```java
boolean sameRuntimePackage =
        first.getPackageName().equals(second.getPackageName())
        && first.getClassLoader() == second.getClassLoader();
```

This is an illustrative comparison for **ordinary classes/interfaces** when both `first` and `second` are non-null. For array classes or other special types, you must consider the JVM rules specific to those types; do not mechanically apply every inference about package-private access of an ordinary class.

## 3. Why does the runtime package affect access control?

Java has four commonly taught access levels: `public`, `protected`, *package-private* (no explicit modifier), and `private`.

An ordinary **package-private** method or field can only be accessed from code in the **same runtime package**. Therefore, having the **same source package name** is not enough.

Example of Java code that is valid when compiled in the same package:

```java
package demo;

public class PackageApi {
    static String secret() {
        return "private-to-package";
    }
}
```

```java
package demo;

public class PackageClient {
    public static String callSecret() {
        return PackageApi.secret();
    }
}
```

At compile time, the compiler sees that both classes are in package `demo` and allows calling `secret()`. At runtime, however, if `PackageClient` is defined by a child loader while `PackageApi` is defined by the parent loader, the JVM sees:

```text
PackageClient:
    runtime package = (demo, ChildLoader)

PackageApi:
    runtime package = (demo, ParentLoader)

PackageClient.callSecret()
        |
        | invokes PackageApi.secret()  [package-private]
        v
    IllegalAccessError
```

`IllegalAccessError` is a `LinkageError`: a JVM-level access check failure, which may appear only when the symbolic method reference is resolved or when the JVM performs the relevant access check. This differs from the compile-time error `'secret() is not public'` when source code is in different packages.

### Comparison table of scenarios

| Source and runtime | Same runtime package? | Package-private access |
|---|---|---|
| Two classes `demo.A`, `demo.B` defined by the same defining loader | Yes | May be accessed according to package-private rules |
| Two classes `demo.A`, `demo.B` defined by two different defining loaders | No | Denied unless another valid access mechanism applies |
| Two classes with different package names in the same loader | No | No package-private access |
| Child calls `loadClass`, but parent actually defines both classes in the same package | Yes | Still belongs to the parent's single runtime package |
| Two classes in different loaders interacting via a `public` member of a `public` class with valid module access | No | Public API is accessible without needing the same runtime package |

The word **“may”** here is intentional: package-private access must still be checked against the specific class/member and related access rules; not every member or every module is automatically accessible just because the package name matches.

## 4. Java 17+ demo: same package name, but IllegalAccessError

The following example **compiles with Java 17** and intentionally creates two different runtime packages. The child loader loads only `demo.PackageClient` in a child-first manner; `demo.PackageApi` is still loaded by the parent loader. Result: the `public` API call succeeds, while the package-private method call is rejected by the JVM.

Source structure:

```text
src/
└── demo/
    ├── PackageApi.java
    ├── PackageClient.java
    └── RuntimePackageDemo.java
```

**File `src/demo/PackageApi.java`:**

```java
package demo;

public class PackageApi {
    static String secret() {
        return "private-to-package";
    }

    public static String open() {
        return "public-api";
    }
}
```

**File `src/demo/PackageClient.java`:**

```java
package demo;

public class PackageClient {
    public static String callSecret() {
        return PackageApi.secret();
    }

    public static String callPublic() {
        return PackageApi.open();
    }
}
```

**File `src/demo/RuntimePackageDemo.java`:**

```java
package demo;

import java.io.InputStream;
import java.lang.reflect.InvocationTargetException;

public class RuntimePackageDemo {
    static class ChildFirstClientLoader extends ClassLoader {
        ChildFirstClientLoader(ClassLoader parent) {
            super(parent);
        }

        @Override
        protected Class<?> loadClass(String name, boolean resolve)
                throws ClassNotFoundException {
            // Change the loading strategy only for this single test class.
            if (!"demo.PackageClient".equals(name)) {
                return super.loadClass(name, resolve);
            }

            synchronized (getClassLoadingLock(name)) {
                Class<?> type = findLoadedClass(name);
                if (type == null) {
                    type = findClass(name);
                }
                if (resolve) {
                    resolveClass(type);
                }
                return type;
            }
        }

        @Override
        protected Class<?> findClass(String name)
                throws ClassNotFoundException {
            String path = name.replace('.', '/') + ".class";

            // Read the test class bytes from the parent classpath.
            try (InputStream input =
                    getParent().getResourceAsStream(path)) {
                if (input == null) {
                    throw new ClassNotFoundException(name);
                }

                byte[] bytes = input.readAllBytes();
                return defineClass(name, bytes, 0, bytes.length);
            } catch (java.io.IOException ex) {
                throw new ClassNotFoundException(name, ex);
            }
        }
    }

    public static void main(String[] args) throws Exception {
        ClassLoader parent = RuntimePackageDemo.class.getClassLoader();
        Class<?> original = PackageClient.class;

        Class<?> child = new ChildFirstClientLoader(parent)
                .loadClass("demo.PackageClient");

        System.out.println("Same binary name: "
                + original.getName().equals(child.getName()));
        System.out.println("Same defining loader: "
                + (original.getClassLoader() == child.getClassLoader()));

        System.out.println("Parent public: "
                + PackageClient.callPublic());
        System.out.println("Child public: "
                + child.getMethod("callPublic").invoke(null));

        try {
            System.out.println(
                    child.getMethod("callSecret").invoke(null));
        } catch (InvocationTargetException ex) {
            System.out.println("Child package-private: "
                    + ex.getCause().getClass().getSimpleName());
        }
    }
}
```

Compile and run from the directory containing `src` using JDK 17+:

```bash
javac --release 17 -d out src/demo/PackageApi.java src/demo/PackageClient.java src/demo/RuntimePackageDemo.java
java -cp out demo.RuntimePackageDemo
```

Output:

```text
Same binary name: true
Same defining loader: false
Parent public: public-api
Child public: public-api
Child package-private: IllegalAccessError
```

**Why does this happen?**

1. `PackageClient.class` from the application loader is referenced directly in `main`, creating a runtime class defined by the parent loader.
2. `ChildFirstClientLoader` intentionally calls `defineClass("demo.PackageClient", bytes)` itself. The JVM allows two runtime classes with the same binary name to coexist because their defining loaders are different.
3. When the child's `PackageClient` calls `PackageApi.open()`, the normal loading path delegates to the parent and obtains `PackageApi` from the parent. The `open()` method is `public`, so the call is valid in this classpath example.
4. When the child's version calls `PackageApi.secret()`, the bytecode references a method without `public`, `protected`, or `private` modifiers—that is, **package-private**. The two classes have different defining loaders, so they belong to two different runtime packages despite sharing the name `demo`. The JVM throws `IllegalAccessError`.
5. Reflection `Method.invoke` wraps any throwable thrown by the invoked method in `InvocationTargetException`. The example retrieves `ex.getCause()` to print the underlying `IllegalAccessError`.

This is an **experimental loader**, not a production class loader implementation. It re-reads bytecode from the parent's resources and deliberately alters the policy for a single binary name; a real plugin system must handle namespace isolation, dependency resolution, package sealing, module boundaries, and loader lifecycle.

**Note:** Do not change `PackageApi.secret()` to `public` during your first run, as that removes the condition you want to observe. You can make that change **after** seeing the error to compare: still different runtime packages, but public access becomes valid.

## 5. How can different runtime packages still communicate?

Being in different runtime packages does not forbid all interaction. What it changes in this example is the **access check for package-private members**.

A clean boundary between an application and a plugin typically looks like this:

```text
Parent/App ClassLoader
    ├── shared.api.Plugin          (public interface)
    └── shared.api.Message         (public DTO/contract)
              ^
              | delegation for shared APIs
              |
Child/Plugin ClassLoader
    ├── plugin.impl.ExamplePlugin  (private implementation)
    └── plugin.libs.*              (own dependencies if configured)
```

The plugin loader **delegates to the parent** for `shared.api.Plugin` and `shared.api.Message`. Thus, the application and the plugin work with the exact same runtime types for the shared API. Implementation code in the child can communicate through the interface's public methods, and the application does not need to access the plugin's package-private internals.

A shared interface:

```java
package shared.api;

public interface Plugin {
    String run(String input);
}
```

This is an **illustrative API snippet**, without a `main` method. In real usage, compile the API into a dependency that the parent loader can define, and ensure the child delegates to the parent for the API namespace. You must also account for module access rules when using named modules.

If both loaders **separately define** `shared.api.Plugin`, having the same name is still not enough: they are two distinct runtime interfaces, and a plugin object may fail to cast to the interface expected by the application.

## 6. Related access control rules

The runtime package is part of the access control mechanism; keep the following cases distinct:

### 6.1. Non-`public` top-level classes

For example:

```java
package demo;

class Helper {
}
```

`Helper` is a **package-private top-level class**. A class in a different runtime package does not have direct access to this type merely because it has the same package name string. The JVM may throw `IllegalAccessError` when attempting to resolve an invalid reference.

### 6.2. Package-private fields and methods

Members declared without an access modifier generally have **package access**. The Java compiler checks this against the source package; the JVM checks it in the context of runtime types and runtime packages.

For example:

```java
package demo;

public class Holder {
    static int count = 1;
    static int readCount() {
        return count;
    }
}
```

If the caller is defined by a different loader, having the same `package demo;` in source code does not guarantee that calling `Holder.readCount()` across runtime linkage will be permitted.

### 6.3. `protected` and `private`

- `protected` has access rules when in the same runtime package **or** through a subclass relationship under specific conditions; it should not be oversimplified as "every subclass can always access every protected member on any receiver."
- `private` depends on class/nestmate ownership and JVM access mechanisms; **being in the same runtime package is not sufficient** to access a private member.
- `public` generally does not require the same runtime package, though it is still subject to module accessibility and other validity rules.

Therefore, avoid assuming that knowing the runtime package allows you to ignore other checks regarding subclasses, declaring classes, modules, or bytecode instructions.

## 7. Does the Java 9+ module system change the formula?

**It does not change the core JVMS runtime package formula:** package name plus defining loader still determines the runtime package identity of an ordinary class or interface. The Java Platform Module System (JPMS) adds **module membership** and **module readability/exports/opens** to the access model.

Consider two classes with the same package name in two loaders:

```text
Loader A defines com.acme.One
Loader B defines com.acme.Two
```

They are not in the same runtime package, even if the modules involved both `exports com.acme`. Conversely, two classes in the same runtime package do not imply that every reflective interaction or type access in named modules is always permitted.

Concepts to distinguish:

| Concept | What does it ask? |
|---|---|
| Runtime package | Which package name does the class belong to, **and which defining loader defined it**? |
| Runtime module | Which runtime module (`Class.getModule()`) does the class belong to? |
| Module reads | Does the caller's module read the target type's module? |
| Exports | Is the package exported to the module that needs to access public types? |
| Opens | Is deep reflection permitted in accordance with the applicable rules? |

The experimental example above runs on the **classpath**, so application classes live in the unnamed module. This isolates the runtime-package/loader effect for learning purposes; it does not mean JPMS can be ignored when an application uses the module path.

With named modules, split-package configurations and assigning packages to loaders are subject to additional constraints. Do not use the "two loaders declaring the same package" experiment as advice to cram conflicting modules into a single class loader.

## 8. Do not confuse runtime package with Package metadata or JAR layout

There are several ways to observe a package name, none of which alone determines access rights:

- `type.getPackageName()` returns the **package name**, such as `demo`. Two different runtime packages can still return the same string.
- `type.getPackage()` returns `java.lang.Package` metadata when applicable, which may contain annotations, specification/implementation versions, or sealing information. The `Package` object does not replace the JVMS definition of runtime-package identity.
- The resource path `demo/PackageApi.class` represents file/JAR layout. Two loaders can read the exact same bytecode entry and still define **two runtime classes**.
- `Class.getProtectionDomain()` describes protection domain information related to code source and runtime permissions; it is not part of the runtime package identity pair.
- `type.getClassLoader()` is a useful way to inspect the defining loader; when it returns `null`, the Java API uses that convention to represent the bootstrap loader.

**Package sealing** is a separate constraint that can be applied by a class loader or JAR manifest to control where classes in a package may be defined from. It does not automatically make classes with different defining loaders belong to the same runtime package. Nor is a sealing error the same as a package-private `IllegalAccessError`.

## 9. Common real-world scenarios

### 9.1. A plugin accidentally bundles a copy of the shared API

The application has `com.app.spi.Plugin` defined by the app loader, but the plugin JAR also packages a class of the same name, and a child-first loader defines its own copy. When code attempts to cast the implementation to the application's `com.app.spi.Plugin`, it may fail with `ClassCastException` or a linkage error due to loader constraints.

**Resolution:** Place shared SPI/DTO contracts in the parent loader, configure delegation for their namespace, and isolate only the implementation or required dependencies.

### 9.2. A framework generates a proxy in the wrong loader

Generated or proxy code may need to access a package-private constructor, type, or method. If the proxy is defined in a different loader even with the same package name, the call can fail with `IllegalAccessError`. Frameworks often need an appropriate class-definition mechanism to preserve runtime package/nest/module access where permitted.

**Resolution:** Identify which loader actually defines the proxy class, which member was denied, and what the library's access requirements are. Do not work around it by blindly opening entire modules or changing every method to `public` if that violates the contract.

### 9.3. Seeing "same package" yet Java still denies access

Check the defining loader, package name, module, exports/opens, class access modifiers, and the symbolic references used in bytecode.

**Resolution:** Distinguish whether the error stems from a *runtime package mismatch*, *module access*, or *binary incompatibility*. The three issues can have related symptoms but require different fixes.

### 9.4. Hot reload creates classes with the same name

Reloading through a new defining loader creates **new** runtime classes, even if the source code and package name have not changed. Old instances and new classes are not naturally compatible. Static state, package access, and type casting are tied to the exact class identity.

**Resolution:** Manage loader lifecycles cleanly, avoid mixing instances from old and new generations in the same internal APIs, and use stable shared public contracts when communicating across boundaries.

## 10. How to diagnose an IllegalAccessError across loaders

When logs report an access error even though both source classes declare the same package:

1. Note the **accessing class**, the class declaring the target member, and the method/field name in the stack trace.
2. Print `getName()`, `getPackageName()`, and `getClassLoader()` for both corresponding `Class<?>` objects. What matters is the **defining loader**, not just the loader that called `loadClass`.
3. Check whether the member is `public`, `protected`, `private`, or package-private, and whether the target declaring class itself is `public`.
4. Inspect the actual class loader policy (`loadClass` overrides, parent-first/child-first) and check for duplicate API classes across JARs.
5. If using JPMS, check module ownership, `exports`/`opens`, and related access rules.
6. Verify the actual deployment: class version, binary name, shaded JARs, generated classes, or proxy bytecode—do not look only at the current source code.
7. Fix the placement/delegation or the API boundary: use a shared loader for shared contracts, or use a valid public API if communicating across runtime packages is actually intended.

You can use the following helper in a program that already holds two `Class<?>` objects:

```java
static void inspect(Class<?> type) {
    System.out.println("name=" + type.getName());
    System.out.println("package=" + type.getPackageName());
    System.out.println("loader=" + type.getClassLoader());
    System.out.println("module=" + type.getModule());
}
```

This is an **illustrative method**, not a standalone program. The printed strings for loader/module depend on environment configuration; do not hardcode them. When duplicate binary names are involved, also print `System.identityHashCode(type)` or compare `Class<?>` references directly if you need to check object identity within a single JVM.

## 11. Knowledge check

**Q1.** Two classes both have `package demo;`, one defined by loader A and one defined by loader B. Do they belong to the same runtime package?

**Answer:** No. Runtime package identity is `(package name, defining loader)`; because their defining loaders differ, their runtime packages differ.

**Q2.** A child loader calls `loadClass("demo.Api")`, but the parent already has `demo.Api`, and the child inherits parent-first delegation. Which loader's runtime package does this class belong to?

**Answer:** If the parent is the actual defining loader, the runtime package is based on the parent, even though the initial call went through the child.

**Q3.** The compiler allows calling a package-private method from a class in the same source package. Will the JVM definitely allow it at runtime?

**Answer:** No. If the classes are defined by different loaders, the JVM may throw `IllegalAccessError`.

**Q4.** Can `type.getPackageName()` be used to check whether two classes share the same runtime package?

**Answer:** It is not sufficient. You must also check the defining loader; for ordinary classes, you can compare both the package name string and `getClassLoader()`.

**Q5.** Are two classes with the same binary name defined by two different loaders the same type?

**Answer:** No. Runtime class identity is `(binary name, defining loader)`. They also have different runtime packages because their defining loaders differ.

**Q6.** When you want a plugin and an application to share the same interface, where should you place the interface?

**Answer:** In a dependency that the shared/parent loader can define, and ensure the plugin loader delegates that API namespace so both use the exact same runtime type.

**Q7.** Can a module `exports` directive turn two different runtime packages into a single runtime package?

**Answer:** No. Module rules are an additional layer of accessibility; they do not change the `(package name, defining loader)` pair.

## 12. Authoritative references

- *Java Virtual Machine Specification* `5.3`, “Creation of Classes and Interfaces”: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.3
- *Java Virtual Machine Specification* `5.4.4`, “Access Control”: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.4.4
- Java SE 17 API, `ClassLoader` and delegation: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html
- Java SE 17 API, `Class` (`getPackageName`, `getClassLoader`, and `getModule`): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html

**Takeaway:** The package name in `package ...;` is syntactic information; according to the JVM, a runtime package also depends on the **defining class loader**. This is why two classes with the same package name sometimes cannot access each other's package-private members, and why class loaders and shared APIs must be placed properly in plugin and modular architectures.

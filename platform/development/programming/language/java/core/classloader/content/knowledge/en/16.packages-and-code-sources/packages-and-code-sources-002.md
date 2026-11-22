# Packages with the Same Name Across Multiple ClassLoaders: Runtime Identity and Access Restrictions

## 1. The Problem: Same Package Name Does Not Guarantee the Same Package in the JVM

In Java source code, two classes both declare:

```java
package demo.shared;
```

We often call them “the same package”. This is true when referring to the **package name at the source-syntax level**. However, at runtime, Java also considers the **ClassLoader that defined** each class. If `demo.shared.A` is defined by loader L1 while `demo.shared.B` is defined by loader L2, they **are not in the same runtime package**, even though the `demo.shared` string is completely identical.

This is the foundation for understanding many real-world issues:

- Why does code **compile** with `package-private` access, yet encounter `IllegalAccessError` at runtime?
- Why do two libraries in two plugins with the same package still not “share internals” like two classes defined by a single loader?
- Why can two classes with the same **binary name** but different loaders not be cast to one another?
- Why are `Package.getName()` or `Class.getPackageName()` insufficient to conclude that two classes have the same access rights?
- How do parent delegation, package sealing, signers, and JPMS affect package partitioning?

The core rule according to the Java Virtual Machine Specification (JVMS):

> **A runtime package is determined by the pair (package name, defining class loader).**

Therefore, the same package name with different defining loaders constitutes **two different runtime packages**. Conversely, two classes with the same package name defined by **the same defining loader** belong to the same runtime package under the JVMS definition; related module constraints, bytecode verification, and access rights must still be considered.

## 2. Source Package, Binary Name, and Runtime Package

Consider two example classes (these are **two separate files**, not a single standalone runnable file):

```java
// src/alpha/demo/shared/Alpha.java
package demo.shared;

public class Alpha {
    static String internal() {
        return "alpha";
    }
}
```

```java
// src/beta/demo/shared/Beta.java
package demo.shared;

public class Beta {
    public String message() {
        return "beta";
    }
}
```

Both have the `package demo.shared;` declaration. Their binary name identifiers are:

- `demo.shared.Alpha`
- `demo.shared.Beta`

If defined by:

```text
L1 defines: demo.shared.Alpha
L2 defines: demo.shared.Beta
```

then the JVM considers:

```text
Runtime package of Alpha = ("demo.shared", L1)
Runtime package of Beta  = ("demo.shared", L2)
```

If `L1 != L2` by loader identity, then **the two pairs are different**.

Important note: `Thread.currentThread().getContextClassLoader()`, the loader initially invoked via `loadClass`, and the **defining loader** do not always coincide. When determining the runtime package, you must use the **loader that actually defines the class**, obtained via `SomeClass.class.getClassLoader()`, not just any loader present on the call stack.

### Three Levels of Identity to Distinguish

| Level | What is it based on? | Example |
| --- | --- | --- |
| Source package | String in the `package` declaration | `demo.shared` |
| Runtime package | **Package name + defining loader** | `("demo.shared", PluginLoaderA)` |
| Runtime class/interface | **Binary name + defining loader** | `("demo.shared.Service", PluginLoaderA)` |

Two classes can be **different runtime classes** yet share **the same runtime package** if they have the same loader and the same package name. Two classes can also have **the same package name** yet belong to **different runtime packages** if their loaders differ.

## 3. Package-Private and Protected: Immediate Consequences

Java has access levels: `public`, `protected`, package-private (no modifier declared), and `private`.

When the compiler sees two source classes that both declare `package demo.shared;`, it can allow one class to call a **package-private** member of the other class, if the other compile-time rules are met. However, the runtime must enforce access control based on the **runtime package**.

Suppose:

```java
// Compiled for package demo.shared
package demo.shared;

class Secret {
    static String reveal() {
        return "secret";
    }
}
```

```java
package demo.shared;

public class Caller {
    public static String read() {
        return Secret.reveal();
    }
}
```

If `Caller` and `Secret` are both defined by an appropriate loader, the call to the package-private method can be valid. However, if:

- Loader **Parent** defines `demo.shared.Secret`;
- Loader **Child** defines `demo.shared.Caller`;
- Child delegates the lookup of `Secret` to Parent;

then at runtime, the caller and target **have different runtime packages**, so accessing the package-private `Secret` class is prohibited. The JVM may report:

```text
java.lang.IllegalAccessError
```

The key point: **source paths and the compiler's package name checks do not make the final decision on runtime access** when class loaders split a package into different runtime packages.

**For `protected`:** in addition to valid access cases via inheritance and receiver relationships according to Java/JVM rules, “same-package” access also requires the same runtime package, not just the same package string. Do not conclude that all `protected` calls across two loaders are prohibited: you must fully evaluate the subclass relationship, the call site, and the member kind.

**For `public`:** the accessibility of a public class/member may allow access across packages and loaders, but module exports/readability, type identity, linkage, method signatures, and other rules still apply.

## 4. Parent Delegation Does Not “Merge” Two Runtime Packages

A common model:

```text
Host/Application ClassLoader
       ├── demo.shared.Secret
       └── demo.api.Plugin          (shared SPI)
                 ▲
                 │ parent delegation
       Plugin ClassLoader
       ├── demo.shared.Caller
       └── plugin.impl.MyPlugin
```

When the plugin loader receives a `loadClass("demo.shared.Secret")` request, it can ask the parent; the parent returns the defined class. However, when the plugin loader itself defines `demo.shared.Caller` from bytecode in its own JAR, the two classes do not become the same runtime package just because the parent loader and child loader **have a parent–child relationship**.

There is no rule that “two related loaders are treated as one package”. The requirement is that **the defining loader must be the exact same object**.

Similarly, if the parent has already defined both `Secret` and `Caller`, and the child simply delegates both, then both **remain in the same runtime package in Parent**, because the child creates no new definition. Check `Class.getClassLoader()` on the actual result rather than inferring from the invoked object.

| Scenario | Defining loaders of class A and B | Same runtime package if package name matches? |
| --- | --- | --- |
| Both classes defined by parent, child only delegates | Parent + Parent | Yes |
| One class in parent, one class defined by child | Parent + Child | No |
| Both classes defined by one plugin loader | Plugin + Plugin | Yes |
| Two independent plugin loaders both define package `com.foo` | Plugin A + Plugin B | No |
| Two loaders both load `java.lang.String` via delegation | Bootstrap + Bootstrap | Yes for the class defined by bootstrap |
| Two classes in named modules | Must consider defining loader and JPMS model | Do not infer solely from package name; named modules have their own constraints |

## 5. Complete Java 17 Example: Compiles Successfully, Runtime Access Denied

The experiment below **self-generates** bytecode in two separate directories, creates Parent and Child loaders, and then attempts to access a package-private class. The program also uses a third loader to demonstrate **the same binary name and the same bytecode, yet two independent runtime classes**.

The experiment does not require Maven, Gradle, external JARs, or network access; it only needs **JDK 17+** with `javax.tools.JavaCompiler`.

### 5.1. The RuntimePackageDemo.java Program

Save the exact following code to the file `RuntimePackageDemo.java`:

```java
import java.lang.reflect.InvocationTargetException;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Comparator;
import java.util.stream.Stream;
import javax.tools.JavaCompiler;
import javax.tools.ToolProvider;

public class RuntimePackageDemo {
    public static void main(String[] args) throws Exception {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException("Run with a full JDK");
        }
        Path root = Files.createTempDirectory("runtime-package-");
        try {
            Path parentSource = root.resolve("srcParent/demo/shared/Secret.java");
            Path callerSource = root.resolve("srcChild/demo/shared/Caller.java");
            Path tokenSource = root.resolve("srcChild/demo/shared/Token.java");
            Path parentClasses = root.resolve("parentClasses");
            Path childClasses = root.resolve("childClasses");
            Files.createDirectories(parentSource.getParent());
            Files.createDirectories(callerSource.getParent());
            Files.createDirectories(parentClasses);
            Files.createDirectories(childClasses);

            Files.writeString(parentSource, """
                    package demo.shared;
                    class Secret {
                        static String reveal() {
                            return "secret";
                        }
                    }
                    """);
            Files.writeString(callerSource, """
                    package demo.shared;
                    public class Caller {
                        public static String read() {
                            return Secret.reveal();
                        }
                    }
                    """);
            Files.writeString(tokenSource, """
                    package demo.shared;
                    public final class Token {}
                    """);

            int parentExit = compiler.run(null, null, null,
                    "--release", "17", "-d", parentClasses.toString(),
                    parentSource.toString());
            int childExit = compiler.run(null, null, null,
                    "--release", "17", "-classpath", parentClasses.toString(),
                    "-d", childClasses.toString(),
                    callerSource.toString(), tokenSource.toString());
            if (parentExit != 0 || childExit != 0) {
                throw new IllegalStateException("Compilation failed");
            }

            URL parentUrl = parentClasses.toUri().toURL();
            URL childUrl = childClasses.toUri().toURL();
            ClassLoader platform = ClassLoader.getPlatformClassLoader();
            try (URLClassLoader parent = new URLClassLoader(
                        new URL[]{parentUrl}, platform);
                 URLClassLoader child = new URLClassLoader(
                        new URL[]{childUrl}, parent);
                 URLClassLoader sibling = new URLClassLoader(
                        new URL[]{childUrl}, platform)) {

                Class<?> secret = parent.loadClass("demo.shared.Secret");
                Class<?> caller = child.loadClass("demo.shared.Caller");
                Class<?> token1 = child.loadClass("demo.shared.Token");
                Class<?> token2 = sibling.loadClass("demo.shared.Token");

                System.out.println("samePackageName="
                        + secret.getPackageName().equals(caller.getPackageName()));
                System.out.println("differentDefiningLoaders="
                        + (secret.getClassLoader() != caller.getClassLoader()));
                System.out.println("callerDefinedByChild="
                        + (caller.getClassLoader() == child));
                System.out.println("sameBinaryName="
                        + token1.getName().equals(token2.getName()));
                System.out.println("sameRuntimeClass=" + (token1 == token2));

                try {
                    caller.getMethod("read").invoke(null);
                    System.out.println("access=allowed");
                } catch (InvocationTargetException error) {
                    System.out.println("access="
                            + error.getCause().getClass().getSimpleName());
                }
                System.out.println("bootstrap="
                        + (child.loadClass("java.lang.String")
                                .getClassLoader() == null));
            }
        } finally {
            try (Stream<Path> paths = Files.walk(root)) {
                for (Path path : paths.sorted(Comparator.reverseOrder()).toList()) {
                    Files.deleteIfExists(path);
                }
            }
        }
    }
}
```

Commands to compile and run:

```bash
javac RuntimePackageDemo.java
java RuntimePackageDemo
```

Deterministic stdout on JDK 17+ with a full compiler, without unusual environment interference:

```text
samePackageName=true
differentDefiningLoaders=true
callerDefinedByChild=true
sameBinaryName=true
sameRuntimeClass=false
access=IllegalAccessError
bootstrap=true
```

### 5.2. What Does Each Line Tell Us?

**`samePackageName=true`:** classes `Secret` and `Caller` both report their package name as `demo.shared`. This is a **string** comparison, not a runtime package comparison.

**`differentDefiningLoaders=true`:** `Secret` is defined by the `parent` loader; `Caller` is defined by the `child` loader. The two classes are in different runtime packages even though they share the same name.

**`callerDefinedByChild=true`:** the child loader asks the parent according to the parent-first policy; the parent does not have `Caller`, so the child finds `Caller.class` in its own URL and defines it itself.

**`sameBinaryName=true` and `sameRuntimeClass=false`:** both the child and sibling loaders define `demo.shared.Token` themselves from the same directory containing bytecode. They are not the same runtime class because their **defining loaders differ**.

**`access=IllegalAccessError`:** `Caller.read()` was accepted by the compiler when compiling with `Secret.class` on the compile classpath. However, at runtime, this method attempts to access the package-private `Secret` defined by the parent loader, while `Caller` is defined by the child. The JVM denies access. Reflection is merely how the program explicitly invokes the public method `Caller.read()` and observes the original exception via `InvocationTargetException.getCause()`; the cause is still the **JVM rules on runtime packages**, not that using reflection changes access rights.

**`bootstrap=true`:** even though requested through the child loader, `java.lang.String` is defined by the bootstrap loader, so `getClassLoader() == null`.

### 5.3. Why Must Parent Be Compiled First?

When compiling `Caller.java`, the compiler is passed:

```text
-classpath <parentClasses>
```

Thanks to this, `javac` sees `Secret.class` in the same **source package name** and accepts the package-private call. However, the compiler does not decide which defining loader each class will be placed in at runtime. At runtime, the experiment's URL array and parent–child relationship create a different boundary.

This is a classic example of the rule: **source-level accessibility and runtime accessibility must be consistent with how classes are assigned to loaders**.

### 5.4. What If Both Classes Are Defined by the Same Loader?

If you place `Secret.class` and `Caller.class` into **the same classpath root** of one loader and let that loader define both, then the “same runtime package” condition is met. When there are no other errors, the package-private call can succeed.

If the parent already provides **both** `Secret` and `Caller`, then the child delegates both and still shares the parent's runtime package.

You should not fix the error by “adding another copy of Secret to Child” without understanding binary identity: parent-first may still pick the copy in Parent first; child-first may cause two independent copies of `Secret` to appear, causing errors when passing data across shared APIs.

## 6. Same Package Name Does Not Mean Classes Can Be Cast to One Another

The **runtime class identity** rule is even stronger than the runtime package rule: a runtime class is identified by the pair **(binary name, defining loader)**.

```text
("demo.shared.Token", ChildLoader)   !=
("demo.shared.Token", SiblingLoader)
```

Even when both classes are created from **the same byte array**:

- `token1.getName().equals(token2.getName())` is `true`;
- `token1 == token2` is `false`;
- Instances from these two runtime classes cannot be treated as the same class by casting to the other class;
- `Class.isInstance` or `isAssignableFrom` on each definition helps verify the true runtime type relationship;
- Shared parent interfaces/APIs can form a valid bridge if **both** implementations implement **the exact same host interface definition**.

An error message like “`demo.shared.Token cannot be cast to demo.shared.Token`” can be the consequence of two independent loaders defining the same binary name. Looking at the string name in a stack trace is not enough; you must inspect the class loaders.

### Runtime Package Differs from Class Loader “Visibility”

- A loader can load a parent's class through delegation, yet **does not become the defining loader** of that class.
- A class can see public APIs from the parent even if they are in different runtime packages.
- Package-private access rights are **not** granted merely because the child “sees” the parent's class.
- Two loaders that load the same JAR file but define classes separately still have separate runtime types and runtime packages.

## 7. Inspecting Packages with the Class API: Using the Right Information

Some APIs can easily cause confusion:

| API | What does it tell you? | What does it NOT guarantee? |
| --- | --- | --- |
| `clazz.getPackageName()` | The class's package name as a string | Does not confirm two classes are in the same runtime package |
| `clazz.getPackage()` | The `Package` object describing the package associated with the class | Does not replace the runtime package rule in the JVMS |
| `clazz.getClassLoader()` | The **defining loader** of the class; `null` for bootstrap | Does not reveal every initiating loader that ever requested the class |
| `loader.getDefinedPackage(name)` | The `Package` defined by **that loader** for the package name, if present | Does not redefine classes, nor report all packages across all loaders |
| `loader.getDefinedPackages()` | The `Package` objects defined by that loader | Does not automatically scan all parent/sibling loaders |
| `clazz.getModule()` | The runtime module of the class | Does not replace defining-loader identity or all access checks |
| `clazz.getProtectionDomain()` | The protection domain if queryable | Does not determine whether two classes are in the same runtime package |
| `clazz.getSigners()` | Signer information of the class if present | Does not allow “sharing” package-private across loaders |

Do not write:

```java
boolean sameRuntimePackage =
        a.getPackageName().equals(b.getPackageName());
```

and then treat a `true` result as sufficient proof. This is **flawed reasoning** if `a` and `b` have different defining loaders.

For two classes that do not fall under special cases such as arrays or primitives, the JVMS rule for identifying a runtime package checks the **package name** and **defining loader**. Example snippet when you already have two `Class<?> a,b` objects:

```java
boolean sameRuntimePackage =
        a.getPackageName().equals(b.getPackageName())
        && a.getClassLoader() == b.getClassLoader();
```

This is a snippet, not a standalone program. If used to infer **access rights to a specific member**, you must also evaluate modifiers, access context, subclass rules, and module access, not just these two conditions.

In particular, a child loader's `getDefinedPackage` **does not list all** packages of the parent. Not seeing a package in the “defined here” list does not mean the child loader cannot load the corresponding class via delegation.

## 8. Package Sealing and Different JARs

Some JARs declare package metadata in `META-INF/MANIFEST.MF`. The **Sealed** attribute specifies that a package is sealed to a specific code source URL. When a loader attempts to define classes into the same package from sources that do not conform to the sealing policy, the runtime/loader may reject it.

Illustrative manifest example:

```text
Manifest-Version: 1.0
Name: demo/shared/
Sealed: true
```

Within the scope of a loader that enforces manifest sealing, this means classes of the sealed package must originate from a matching code source. If the loader finds `demo.shared.A` from JAR1, and then finds `demo.shared.B` from another JAR2, a **sealing violation** may occur.

However, it is important to distinguish:

1. **Runtime package identity:** determined by the package name and defining loader.
2. **Sealing policy:** controls the set of URLs/code sources allowed to contribute classes to a package within the same loader; depends on the loader/JAR manifest implementation.
3. **Module encapsulation:** controls reading/exporting/opening packages in JPMS; it is not a form of sealing.

Two independent loaders can **define packages with the same name** without automatically forming a single shared sealed package. Sealing does not cause two defining loaders to automatically grant each other package-private access.

### Using definePackage with a Custom ClassLoader

`ClassLoader.definePackage(...)` allows defining a `Package` object containing specification/implementation metadata and a sealing URL depending on the API overload. It does **not** create new classes, does not grant package-private access across loaders, and does not automatically merge another loader's package.

If a custom loader loads classes from multiple sources, package metadata, signers/certificates, and protection domains must be designed consistently. Within a single defining loader, classes in the same package must comply with signer/certificate constraints when applicable; violations can throw a `SecurityException` or corresponding error.

**Do not treat** calling `definePackage("demo.shared", ...)` on L2 as a way to “import” L1's runtime package into L2. The two loaders remain independent.

## 9. Java Platform Module System (JPMS): Split Packages and Modules

Since Java 9, a class also belongs to a runtime module. When using **named modules**, the JVM/module layer and loaders also enforce:

- **Readability:** whether the calling module reads the module containing the target type.
- **Exports:** whether the public package is exported by its containing module to the consuming module.
- **Opens:** reflective access permissions to the package according to module rules.
- **Package/module mapping:** restricts overlapping packages across named modules, especially if the same class loader needs to define them.
- **Unnamed module:** classes defined on the regular classpath belong to the unnamed module corresponding to their loader; it is not equivalent to a named module declared in `module-info.java`.

A class with the `public` access modifier can still be inaccessible from another module if the named module's package has not been properly exported. Conversely, two classes with the same package name string defined by two different loaders are still **not** treated as a single runtime package merely because their module configurations are related.

### Do Not Use the Module Path as a “Fix” for ClassLoader Boundaries

If a plugin project encounters `IllegalAccessError` due to package-private access between parent and child, moving JARs onto the module path does not automatically give the two classes the same defining loader. In fact, named modules may add further encapsulation checks and detect split packages.

When deciding whether to use JPMS, you need to clearly determine who owns each package, which module defines the API/SPI, which modules need `requires`, and which packages need `exports`/`opens`.

### Do Runtime Packages and Module Organization Serve the Same Purpose?

They serve different roles:

| Mechanism | Scope |
| --- | --- |
| Source package | Organizing source/binary names |
| Runtime package | Access control/package identity based on name + defining loader |
| Named module | Module resolution, readability, and encapsulation boundaries |
| ClassLoader | Where classes are located/loaded/defined and runtime type identity |

A successful design usually **unifies** the four levels, rather than assuming one level automatically replaces another.

## 10. Plugins, Containers, and Multiple Library Versions

A plugin architecture typically looks like:

```text
Host ClassLoader
   ├── com.company.spi.Plugin
   ├── com.company.spi.Request
   └── com.company.spi.Response
           ^
           |
     PluginLoader A
       ├── plugin.alpha.Handler
       └── thirdparty.lib.Utility (version A)

     PluginLoader B
       ├── plugin.beta.Handler
       └── thirdparty.lib.Utility (version B)
```

Sound structuring practices:

1. **Place shared APIs/SPIs and DTOs in the host/parent**, and have plugin loaders delegate so they receive the exact same runtime types.
2. **Isolate implementations and unshared dependencies** per plugin loader if the architecture requires multiple library versions to coexist.
3. **Do not rely on package-private access across loaders**, even when the package strings match.
4. **Do not pass internal classes across the boundary** if the host cannot use the exact class identity; use public interfaces/SPIs, adapters, or serialization contracts.
5. **Avoid split packages between host and plugin JARs** if internal classes call package-private members on each other directly.
6. **Control delegation for critical API packages**, avoiding custom child-first loaders creating a separate copy of `com.company.spi.Plugin` and causing `ClassCastException` when the host casts.
7. **Distinguish ClassLoader from classpath:** the same JAR path does not mean the same runtime type if defined by two separate loaders.

When you need to “share internal code” between two plugins, more sustainable options are placing an appropriate public API in a shared loader, extracting a shared library with a public boundary, or letting the exact same loader define the classes that require package-private access (after evaluating namespace and maintenance constraints).

### Same Package, Two Dependency Versions

For example, suppose there are two versions of `com.vendor.json.Parser` in Plugin A and Plugin B. If each plugin defines its own version, they are not the same runtime class. If the parent has already loaded a Parser version and the plugins remain parent-first, both may unintentionally use **the same** Parser from the parent instead of their own.

Check:

```java
System.out.println(parserType.getName());
System.out.println(parserType.getClassLoader());
```

This is a snippet, assuming `parserType` is a `Class<?>` already obtained by the application. If you need the code source, you can check `ProtectionDomain/CodeSource` when the value exists. Do not only compare the version written in the JAR filename.

## 11. Easily Confused Errors When Two Loaders Share a Package Name

| Symptom | Reason to consider | First check |
| --- | --- | --- |
| `IllegalAccessError` even though code compiles | Package-private/protected across two different runtime packages | Actual defining loaders of caller and target |
| `ClassCastException` with two identical class names | Same binary name but different defining loaders | `Class<?> ==`, loader identity |
| `LinkageError` regarding loading constraints | JVM requires a consistent type name across loaders at linkage points | Classes in method descriptors, loader graph |
| `SecurityException` regarding signers/certificates | Classes in the same package and loader have inconsistent signer policies | Source JAR, signatures, and package metadata |
| `SecurityException: sealing violation` | Sealed package mixes different URL/JAR sources | Manifest sealing and code source |
| `ClassNotFoundException` when loading in child | Child/parent cannot see the required definition | Binary name, parent chain, bytecode source |
| `NoClassDefFoundError` at runtime | Missing dependency, wrong name, or failed initialization state | Cause message, classpath/dependency graph |
| `NoSuchMethodError` | Runtime loaded a different API version than compile-time | Signatures and the selected class definition |
| `InaccessibleObjectException` during reflection | JPMS `opens` rules or access context | Module containing the class, caller module |
| `IllegalAccessException` from reflection | Reflection API denies access according to access checks | Member modifier, caller/module, access mode |

**Specifically:** `IllegalAccessError` is a subtype of `IncompatibleClassChangeError` (under `LinkageError`), indicating invalid runtime access. This differs from `IllegalAccessException`, which is a checked exception that reflection can throw when the reflection API denies access. The experiment in section 5 catches `InvocationTargetException` because the invoked public method **had already begun executing**, and then the JVM detected the issue at the call to the other class.

A program can fail even during linking depending on class verification/resolution; do not assume every package-private error will appear at the exact same method call line across every JVM. The goal is to understand loader boundaries, not rely on exact stack trace locations.

## 12. How to Debug Properly: Log Name, Defining Loader, Module, and Code Source

When encountering a duplicate package name issue, compare **two specific Class objects**: the caller and the target.

Place the following helper method in a Java class:

```java
static void inspect(Class<?> type) {
    System.out.println("name=" + type.getName());
    System.out.println("package=" + type.getPackageName());
    System.out.println("loader=" + type.getClassLoader());
    System.out.println("module=" + type.getModule());
    java.security.ProtectionDomain domain = type.getProtectionDomain();
    java.security.CodeSource source =
            domain == null ? null : domain.getCodeSource();
    System.out.println("codeSource="
            + (source == null ? "<unknown>" : source.getLocation()));
}
```

This is an **illustrative method**, not a standalone program with `main`. In restricted environments, some security/protection information may be unavailable; `CodeSource == null` does not prove that a class was loaded incorrectly.

Procedure:

1. Identify the **binary name** of the caller and target involved in the error.
2. Obtain the **Class<?> of each side** if possible; do not use `Class.forName` with an arbitrary loader and assume it is the class that caused the error.
3. Print `getPackageName()` and **`getClassLoader()` for both**.
4. If binary names or package names match while loaders differ, examine split runtime package/type identity.
5. If the loader is the same yet `IllegalAccessError` still occurs, check modifiers, static/instance, superclass, interfaces, module, and binary incompatibility.
6. If different JARs are involved, check manifest sealing, certificates/signers, and duplicate classes with the same binary name.
7. If the system uses named modules, check exports/opens/readability and the class's module source.
8. If plugins are involved, determine the parent-first/child-first policy and the actual path the class took.

### Supporting JDK Tools

```bash
jar tf plugins/plugin-a.jar
jar tf plugins/plugin-b.jar
javap -classpath plugins/plugin-a.jar -p demo.shared.Secret
java -Xlog:class+load=info -cp "app/classes:lib/*" com.example.Main
```

These are **illustrative** commands; filenames and class names must be replaced with actual values. The `-cp` option uses `:` for Linux/macOS; Windows uses `;`. `jar tf` confirms which entries exist in the JAR; `javap -p` shows access modifiers/method signatures; unified class-load logging helps show where the bytecode comes from.

For classes defined by a custom loader directly from memory/database, the `CodeSource` origin may not be a file/JAR URL; log the loader identity and a reliable bytecode source where `defineClass` occurs.

## 13. Common Misconceptions

**“Two Java files have `package demo.shared;`, so they can always use package-private access.”** False. A runtime package depends on the defining loader.

**“Parent and child are related, so they are considered the same package.”** False. Different defining loaders mean different runtime packages, even if delegation occurs between them.

**“If Package.getName() is the same, access rights are the same.”** False. That does not account for the loader and other access rules.

**“When the child calls `parent.loadClass`, the returned class belongs to the child's package.”** False. The defining loader is still the parent.

**“Two classes with the same binary name in two loaders are the same type because the bytecode is identical.”** False. Runtime class identity also includes the defining loader.

**“Simply making a class `public` lets all package-private members be called.”** False. Public class and member access are two separate checks; named modules also have encapsulation boundaries.

**“A sealed package causes two loaders with the same package name to share internal access.”** False. Sealing is a source/package constraint; it does not merge defining loaders.

**“Calling `definePackage` on two loaders with the same package name will merge classes.”** False. The API manages the package metadata of the corresponding loader; it does not change class identity.

**“JPMS can bypass the runtime package rule.”** False. Module rules supplement access control; they do not automatically grant package-private access across defining loaders.

**“A `ClassCastException` must be caused by package-private access.”** Insufficient evidence. A broken type identity is a class identity issue, not directly a package-private access modifier issue.

## 14. Self-Check Exercises

**Question 1.** `demo.shared.A` is defined by L1 and `demo.shared.B` is defined by L2. Do the two classes share the same runtime package?

**Answer:** No, if L1 and L2 are two different loader objects, even though the package name string is identical.

**Question 2.** Child calls `loadClass("demo.shared.A")` and receives a class defined by Parent. Which loader is the defining loader?

**Answer:** Parent. Having Child initiate the request does not change the class's runtime package.

**Question 3.** Why does the compiler allow `Caller` to call package-private `Secret.reveal()`, yet the runtime reports `IllegalAccessError`?

**Answer:** The compiler sees two source types with the same package name in the compile graph; at runtime, however, `Caller` is defined by Child and `Secret` is defined by Parent. They belong to different runtime packages, and the JVM denies package-private access.

**Question 4.** Two independent `URLClassLoader` instances read the same `demo.shared.Token.class`. Will comparing their `Class<?>` objects be equal?

**Answer:** No, if each loader defines the class itself. The same binary name/bytecode with different defining loaders means two runtime classes.

**Question 5.** When module A `exports demo.shared`, can a class with the same package name in a different loader automatically call `private` or package-private members?

**Answer:** No. `exports` governs accessibility of public types/members under module rules; it does not grant private/package-private access across loaders.

**Question 6.** Why can a sealed package cause an error when JAR1 and JAR2 provide two different classes in the same package?

**Answer:** Sealing places a source constraint on the classes in a package managed by a loader. If the loader mixes sources that do not match the seal base URL, a sealing violation can occur.

**Question 7.** What minimum information needs to be logged to determine whether two classes share the same runtime package?

**Answer:** The package name and defining loader of **each** actual `Class<?>` object. For a complete diagnosis, you can also include the module, code source, method modifiers, and dependency version.

**Question 8.** A plugin system needs to exchange messages between A and B, but each plugin has its own loader. Which design should be chosen?

**Answer:** Place an appropriate public SPI/DTO in the shared host loader so plugins delegate to it; avoid relying on package-private access between the two loaders.

## 15. Safe Implementation Checklist for Package Identity

- [ ] Identify the actual defining loaders of the classes used in the same package name.
- [ ] Do not mix classes that require package-private access across different loaders.
- [ ] Shared APIs/SPIs must have **a single shared runtime definition**, typically from the host/parent.
- [ ] When isolating dependencies, check whether classes with the same binary name can appear across multiple defining loaders.
- [ ] Clearly document which package namespaces belong to the host and which belong to each plugin.
- [ ] Check the parent-first/child-first policy before concluding which JAR wins.
- [ ] Consider sealing, signers, and protection domains when loading multiple JARs into a single loader.
- [ ] For named modules, check the module graph and `exports`/`opens`.
- [ ] Verify binary compatibility and access rights when building under one loader layout but running under another.
- [ ] Test in practice with the exact artifacts, loader tree, and runtime JDK of the deployment environment.
- [ ] When an error occurs, print the package name, loader, module, and code source of **both caller and target**.
- [ ] Do not use `Class.getPackageName()` or the JAR path alone to infer runtime package identity.

## 16. Conclusion and Authoritative References

**Having the same package name in source code does not guarantee the same runtime package.** The JVM determines a runtime package by **the package name together with the defining ClassLoader**. This rule explains why package-private access can be blocked even though the compiler accepted it, why two runtime classes with the same name cannot be cast to each other when defined by different loaders, and why a plugin architecture needs a clear shared API/SPI boundary.

When investigating an error, do not only ask “what package do the two classes declare?”; ask **“which loader actually defined each class?”**, and then check member access, type relationships, module visibility, sealing, and dependency compatibility.

Official references:

- JVMS 17 §5.3, *Creation of Classes and Interfaces* (defining loader and runtime class identity): https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.3
- JVMS 17 §5.4.4, *Access Control*: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.4.4
- JLS 17 §6.6, *Access Control*: https://docs.oracle.com/javase/specs/jls/se17/html/jls-6.html#jls-6.6
- Java SE 17 `Class` API: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html
- Java SE 17 `ClassLoader` API, `definePackage` and `getDefinedPackage`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html
- Java SE 17 `Package` API: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Package.html

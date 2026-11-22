# Class Definition Restrictions in the java.* Package — Java ClassLoader

Java allows applications to write custom `ClassLoader` implementations to load bytecode from JARs, directories, memory, or custom sources. However, the ability to **define a new class** is not unlimited: an ordinary custom/application class loader **cannot define a class whose binary name begins with `java.`**. If `ClassLoader.defineClass(...)` is called with a name such as `java.demo.Reserved`, the JVM/JDK enforces a special restriction and throws a **`SecurityException`**.

The rule in **Java SE 17 API, `ClassLoader#defineClass`** is stated more precisely: a name beginning with `java.` can only be defined by the **platform class loader or its ancestor loaders**. This is **not** a privilege granted to any `ClassLoader` subclass merely because it delegates to the platform loader.

This lesson focuses on the difference between **loading/delegating an existing platform class** and **defining a new class in the `java.*` namespace**, why the JVM protects that namespace, how to diagnose the error, related restrictions, and safe package/class loader design.

## 1. Two Easily Confused Actions: loadClass and defineClass

Suppose you have a custom loader:

```java
ClassLoader child = new ClassLoader(
        ClassLoader.getSystemClassLoader()) {
};
Class<?> stringType = child.loadClass("java.lang.String");
```

This is **valid**. The child requests `java.lang.String` and, by default, delegates up to its parent and then to the appropriate platform loaders. It receives the `Class<?>` object corresponding to the `String` class already defined by the runtime, **rather than creating a second copy of `java.lang.String`**.

In contrast, code inside a subclass:

```java
return defineClass("java.demo.Reserved", bytes, 0, bytes.length);
```

is asking **that subclass itself to define a class** in the `java.` namespace. On a normal application/custom loader, the request is rejected with a `SecurityException`, even if `bytes` is a valid class file.

| Action | Meaning | Typical Result with JDK Classes |
|---|---|---|
| `child.loadClass("java.lang.String")` | Requests class lookup, potentially delegating to parent | Succeeds, returns the platform class |
| `Class.forName("java.lang.String")` | Looks up the class using the caller's defining loader and requests initialization | Succeeds in an appropriate runtime |
| `String.class` | Class literal referencing a class already known to the JVM | Valid |
| `child.defineClass("java.demo.Reserved", bytes, ...)` in a subclass | Child **defines** a class itself in the `java.` namespace | `SecurityException` |
| `child.getResource("java/lang/String.class")` | Looks up resource/class bytes, not a runtime class definition | May return a URL if the resource is provided and module rules allow |

**Rule of thumb:** `loadClass` can return a class defined by **another loader**. Simply calling `loadClass` on a child does not prove the child is the *defining loader*. Verify with `clazz.getClassLoader()` and understand the parent delegation mechanism.

## 2. Exact Protection Rules of defineClass

Common overloads:

```java
protected final Class<?> defineClass(
        String name, byte[] b, int off, int len);

protected final Class<?> defineClass(
        String name, byte[] b, int off, int len,
        java.security.ProtectionDomain domain);
```

These are **illustrative API signatures**, not a standalone program. When a custom loader uses `defineClass` to define an ordinary class, Java SE 17 imposes the following conditions:

1. `name` is the expected **binary name**, for example `com.example.Widget`; not `com/example/Widget.class`.
2. The bytes must have a valid class file format, with offset/length within bounds.
3. When `name` is non-`null`, the name declared in the bytecode must match the passed name; otherwise, `NoClassDefFoundError` may be thrown.
4. A package may be subject to consistency rules for **signer certificates** among classes defined by the same loader.
5. **Specifically for `java.`:** a loader that is **not the platform loader or one of its ancestors** may not define a class whose name starts with `java.`; a `SecurityException` may be thrown.

This rule is published directly in the Javadoc, **not merely an implicit convention saying "don't use that name."**

### Name Prefix Checking Rule

The prohibited form is a name beginning with **`java.`** with a dot immediately following `java`:

```text
java.lang.String         -> protected namespace
java.util.List           -> protected namespace
java.demo.Reserved       -> protected namespace

com.example.MyClass      -> does not fall under the java.* rule
org.acme.plugin.Tool     -> does not fall under the java.* rule
myjava.demo.Widget       -> does not fall under the java.* rule
javax.example.Widget     -> not automatically governed by this java.* rule
jdk.example.Widget       -> not automatically governed by this java.* rule
```

The last `javax.*` and `jdk.*` lines are **not recommendations to place application classes there**. Other JDK packages/modules can still be protected by **separate mechanisms** (module/package conflicts, accessibility, class identity, vendor policies). For new applications, choose a package belonging to your own domain/organization, such as `com.acme.project`.

**Do not equate** the `java.*` restriction with Java prohibiting every class that starts with the letters `java` in any context; the issue is the designated namespace and how the runtime defines classes.

## 3. Why Does Java Need to Restrict the java.* Namespace?

A key goal is to protect the **integrity of core platform types and APIs** that the entire Java runtime depends on.

For example, if a plugin could secretly define its own `java.lang.String` under the same name:

- `Object`, `String`, `Class`, `Throwable`, or standard APIs could suffer from namespace confusion and type compatibility issues.
- Code could mistake a spoofed class for a platform class simply because they share the **same binary name**.
- Internal assumptions of bytecode, linking, serialization, reflection, or frameworks could become unreliable.
- A system or plugin could deceive other code using a namespace name that carries platform-level meaning.

Java uses multiple mechanisms together: namespace restriction in `defineClass`, loader hierarchy, type identity, bytecode verifier, linking constraints, module ownership/access, and other checks. **The `java.*` restriction is one specific safeguard** — not a complete description of the JVM security model.

### Same Name Does Not Mean Same Runtime Type

For ordinary classes:

```text
Runtime class identity =
    (binary name, defining class loader)
```

If two different loaders each define `com.acme.User`, they create two distinct runtime classes even if the source/bytecode is identical. For `java.lang.String`, allowing applications to define duplicate copies under the same name would pose a particularly severe risk. Therefore, the JDK restricts the set of loaders permitted for names starting with `java.` very narrowly.

**Distinction:** Parent-first delegation helps a child **share platform classes**; the `defineClass` restriction prevents a child from arbitrarily creating **new classes impersonating the platform namespace**. The two mechanisms complement each other, but they are **not the same**.

## 4. Java 17+ Demo: Ordinary Classes Can Be Defined; java.* Is Rejected

The demo below compiles **two valid class files**:

- `sample.Allowed`: a class with an ordinary name for the custom loader to define successfully.
- `java.demo.Reserved`: a test class **in the protected namespace**, solely to demonstrate that a custom loader is not permitted to define it. **Do not deploy real application code in this package.**

The main program reads bytes from disk, calls `defineClass` for both names, and contrasts them with `loadClass("java.lang.String")`.

Directory structure:

```text
guard-demo/
├── src/
│   ├── sample/
│   │   └── Allowed.java
│   ├── java/
│   │   └── demo/
│   │       └── Reserved.java
│   └── GuardDemo.java
└── out/
```

### 4.1. Ordinary Class

File **`src/sample/Allowed.java`**:

```java
package sample;

public final class Allowed {
    public static String value() {
        return "allowed";
    }
}
```

### 4.2. Test Class Named java.*

File **`src/java/demo/Reserved.java`**:

```java
package java.demo;

public final class Reserved {
    public static String value() {
        return "reserved";
    }
}
```

This file serves as a **bytecode compilation test**; it must not be used as a real runtime library. Under some compiler/module configurations, declaring packages that collide with JDK modules may be blocked at compile time. In this lesson, `java.demo` is a test name not belonging to a standard platform module, and the command below was tested with `javac --release 17` on JDK 21.

### 4.3. Main Loader and Exception Check

File **`src/GuardDemo.java`**:

```java
import java.nio.file.Files;
import java.nio.file.Path;

public final class GuardDemo {
    static final class ByteLoader extends ClassLoader {
        ByteLoader(ClassLoader parent) {
            super(parent);
        }

        Class<?> define(String name, byte[] bytes) {
            return defineClass(name, bytes, 0, bytes.length);
        }
    }

    public static void main(String[] args) throws Exception {
        ByteLoader loader = new ByteLoader(
                GuardDemo.class.getClassLoader());

        byte[] allowed = Files.readAllBytes(
                Path.of(args[0], "sample", "Allowed.class"));

        Class<?> ordinary =
                loader.define("sample.Allowed", allowed);

        System.out.println("Normal definition: "
                + ordinary.getName());
        System.out.println("Custom defining loader: "
                + (ordinary.getClassLoader() == loader));

        Class<?> core = loader.loadClass("java.lang.String");
        System.out.println("Delegated String: "
                + (core == String.class));
        System.out.println("String bootstrap: "
                + (core.getClassLoader() == null));

        byte[] reserved = Files.readAllBytes(
                Path.of(args[0], "java", "demo", "Reserved.class"));

        try {
            loader.define("java.demo.Reserved", reserved);
            System.out.println("Unexpected reserved definition");
        } catch (SecurityException expected) {
            System.out.println(
                    "Reserved definition: SecurityException");
        }
    }
}
```

`ByteLoader` subclasses `ClassLoader` solely to gain access to the protected `defineClass` method. The `define` method has package-private access and is called by `GuardDemo` from the same top-level/nest context; since they are in the same source file, the example is valid.

### 4.4. Running on Java 17+

From the `guard-demo` directory, using JDK 17+:

```bash
mkdir -p out

javac --release 17 -d out \
  src/sample/Allowed.java \
  src/java/demo/Reserved.java \
  src/GuardDemo.java

java -cp out GuardDemo out
```

In **PowerShell**, create the `out` directory and run the single-line commands:

```powershell
New-Item -ItemType Directory -Force -Path out | Out-Null
javac --release 17 -d out src/sample/Allowed.java src/java/demo/Reserved.java src/GuardDemo.java
java -cp out GuardDemo out
```

**Output verified using OpenJDK 21 targeting `--release 17`:**

```text
Normal definition: sample.Allowed
Custom defining loader: true
Delegated String: true
String bootstrap: true
Reserved definition: SecurityException
```

### 4.5. Exact Explanation of the Output

1. **Normal definition:** `ByteLoader#define("sample.Allowed", bytes)` is permitted because the name is in an application namespace, the class file is valid, and this loader has not already defined that name.
2. **Custom defining loader:** `ordinary.getClassLoader() == loader` is `true`. This proves the class `sample.Allowed` was defined by the custom loader itself, rather than merely initiating a load and delegating.
3. **Delegated String:** `loader.loadClass("java.lang.String")` inherits the default parent-delegation behavior. The loader finds `String` through the parent/bootstrap path instead of calling `defineClass` to create its own copy.
4. **String bootstrap:** in a standard JDK, the defining loader of `java.lang.String` is the bootstrap loader; `getClassLoader()` returns `null` in this case.
5. **Reserved definition:** the bytes of `java.demo.Reserved` exist and the passed name **matches the binary name** in the class file, yet the custom application loader is still blocked by the `java.*` rule; `defineClass` throws `SecurityException`.

All fixed stdout lines above match the standard JDK environment described in the test. Non-standard Java runtimes or custom VMs may have different implementation details; in production code, always rely on the Java SE contract rather than comparing exception message strings verbatim.

**Do not run `java -cp out java.demo.Reserved` to "execute" the protected class**: aside from launcher/class-loading issues, the test class also **has no `main` method**. Its sole purpose is to demonstrate `defineClass` on a custom loader.

## 5. Successful Compilation Does Not Mean the Class Can Run

This is a common source of confusion:

```text
.java source
    |
    v
javac --release 17
    |
    +--> produces .class with binary name java.demo.Reserved
    |
    v
application runtime loader
    |
    +--> defineClass("java.demo.Reserved", bytes, ...)
                |
                v
         SecurityException
```

`javac` is the step that **compiles source into a class file**, whereas `defineClass` is the runtime step that **defines the class in a loader**. The compiler may accept source that is syntactically valid, while the JVM/JDK still enforces independent runtime restrictions. Packages belonging to a named module may also be rejected earlier by the compiler or module tools; you should not assume that **every** `package java.*` compiles under every configuration.

### Why Simply Moving the Class File Into Another JAR Is Not Enough

Putting `java/demo/Reserved.class` into a JAR added to the classpath **does not grant defining-loader privileges**:

```text
app.jar / plugin.jar
    └── java/demo/Reserved.class

Application/Custom ClassLoader
    └── attempt define java.demo.Reserved
            └── SecurityException
```

The resource can exist inside the JAR, but being able to locate the bytes and having permission to define a runtime class are two separate conditions.

## 6. Distinguishing Permitted Loaders from Application Loaders

The Java SE 17 Javadoc states: if the binary name starts with `java.`, class definition can only be performed by **the platform class loader or its ancestor loaders**.

In a typical JDK 17 hierarchy:

```text
Application/System loader
       |
       v parent
Platform loader
       |
       v parent
Bootstrap loader (getClassLoader() is typically null)
```

- **Bootstrap loader** handles many essential classes such as `java.lang.String` and `java.lang.Object`.
- **Platform loader** is responsible for the set of platform classes/modules assigned to it by the JDK.
- **Application loader** loads application code on the normal classpath/module configuration.

Saying **"only the bootstrap loader has permission for all of `java.*`"** is **inaccurate** according to the Java 17 Javadoc wording, because **the platform loader or its ancestors** are also included in the permitted rule. However, this **does not allow an application to create a subclass whose parent is the platform loader and inherit permission to define `java.*`**. The newly created loader is a **child**, not the platform loader or one of its ancestors.

Even though a class is **defined by the platform loader**, that does not mean an application is allowed to call `protected defineClass` on the platform loader instance. Protected access rules, module/package access, and runtime safeguards still apply.

### Calling Loader vs. Defining Loader

Consider:

```java
ClassLoader app = ClassLoader.getSystemClassLoader();
Class<?> stringType = app.loadClass("java.lang.String");
```

This is a syntactically complete snippet inside a method. `app` initiates the class request, but `stringType.getClassLoader()` on a standard JDK returns `null` (bootstrap). Runtime class identity is tied to the loader that **defined** it, not the `app` variable.

Do not conclude that `String` was defined by the application just because `app.loadClass` returned successfully.

## 7. The java.* Restriction Is Not the Only Package Protection

Beyond checking the `java.` prefix, class definition is subject to many other constraints:

| Mechanism | What Does It Protect? | Possible Error / Symptom |
|---|---|---|
| **Reserved `java.*` namespace** | Prevents loaders other than platform/ancestors from defining `java.*` classes | `SecurityException` |
| **Class binary name match** | Ensures the name passed to `defineClass` matches the bytes | `NoClassDefFoundError` |
| **Class-file validation** | Ensures valid class file format and version | `ClassFormatError`, `UnsupportedClassVersionError` |
| **Bytecode verification** | Enforces stack, type, control-flow rules, etc. | `VerifyError` |
| **Package signer consistency** | Ensures classes in the same package of a loader have matching signer certificates | `SecurityException` |
| **Runtime package identity** | Package-private access depends on package name **and defining loader** | Possible `IllegalAccessError` |
| **Loading constraints** | Maintains type identity consistency across cross-loader signatures/relationships | `LinkageError` |
| **JPMS module rules** | Enforces module membership, readability, exports/opens | Access/linking errors or build/module resolution errors |
| **Package sealing when applied by loader/JAR** | Enforces code-source consistency for sealed packages | Loader/tool-specific sealing error |

Do not classify every `SecurityException` as "hit `java.*`." For example, a signer certificate mismatch uses the **same exception class** but has a different root cause.

Likewise, do not treat `ClassNotFoundException` as synonymous with `SecurityException`: the former means the definition **could not be found** via lookup, while the latter (in this context) means the loader is **not permitted to define** a class in a reserved namespace.

## 8. Why definePackage Does Not Bypass the Restriction

`ClassLoader#definePackage` manages a loader's **package metadata**, such as specification title, implementation version, vendor, sealing URL, and related attributes.

Abstract example:

```java
definePackage(
        "com.acme.plugin",
        "Plugin API", "1.0", "Acme",
        "Plugin Runtime", "1.0", "Acme",
        null);
```

This is an illustrative snippet inside a `ClassLoader` subclass, not a standalone program.

**Defining package metadata** is a different operation from **defining a runtime class**. You cannot assume that calling `definePackage("java.demo", ...)` grants a custom loader permission to call `defineClass("java.demo.Reserved", ...)`. `ClassLoader#defineClass` still performs its namespace checks.

A Java package is not a "global folder" either. In the JVM, a class's **runtime package** is generally determined by:

```text
(package name, defining class loader)
```

Two classes in the same `package com.acme;` defined by different loaders do not automatically share package-private access. This is another reason to avoid arbitrarily repackaging core or shared classes across multiple loaders.

## 9. Named Modules, the JDK Runtime Image, and java.* Packages

Since Java 9, the JDK uses the **Java Platform Module System (JPMS)**, with modules such as `java.base`, `java.logging`, and `java.sql`. Some APIs with `java.*` packages are assigned to different platform modules and loaders depending on the runtime configuration.

Points to distinguish:

- **`package java.*`**: a namespace prefix at the Java binary name level.
- **`module java.base`**: a named module in Java's module system.
- **`java.*` class-definition restriction**: the `defineClass` check based on permitted loaders.
- **Module accessibility**: whether a class/module can be read or accessed via `requires`, `exports`, `opens`, and related rules.
- **Runtime image resource `jrt:`**: how modern JDKs expose certain module resources, not as ordinary `File` objects.

These mechanisms are related but **do not replace one another**. For example, using a launcher option to open a package for reflection (when valid) does not mean an application suddenly gains permission to **define new classes in `java.*` with its own loader**.

If you need to extend Java functionality, choose your own application package and documented API/plugin extension points. If you need to adjust JDK behavior in controlled testing, that is a specialized topic involving tools/modules/instrumentation with its own constraints; **you should not treat defining extra classes in `java.*` via an application loader as a solution**.

### Do Not Conflate java.*, javax.*, and jdk.*

Some standard APIs use `javax.*`, while some JDK implementation APIs use `jdk.*` or `sun.*`. The `defineClass` rule specifically for names starting with **`java.`** is explicitly documented; you should not assume that exact same check applies to every other package based solely on prefix.

However, **do not place new application code under `javax.*`, `jdk.*`, or `sun.*`** to "avoid the `java.*` rule": those namespaces may be owned by the platform/frameworks or constrained by modules, and bypassing one check does not create a compatible or stable contract.

## 10. Parent Delegation and Protecting Core Classes

`ClassLoader.loadClass` operates parent-first by default:

```text
ChildLoader.loadClass("java.lang.String")
    |
    +-- check if class is already recorded by this loader
    |
    +-- ask parent loader
          |
          +-- continue up to platform/bootstrap
          |
          +-- String already exists in runtime
    |
    +-- return Class<?> of String from runtime
```

For JDK classes, this is **by design**: all modules, application components, and plugins share the core runtime types they need to interoperate.

A **child-first** loader written for plugins may intentionally prioritize loading `com.acme.private.*` itself, but it should **keep parent-first delegation** for runtime/platform types and shared APIs.

Conceptual policy example:

```text
java.*                         -> parent/platform only
javax.* / jdk.* / sun.*        -> per appropriate contract/runtime/module
shared.api.*                   -> parent first
plugins.acme.internal.*        -> child first if isolation is truly needed
other names                    -> parent first by default
```

This is an **illustrative architectural policy**, not complete code or an exhaustive rule table for all packages. On Java 17+, a child should never define `java.*` even under a child-first policy; it is better to separate responsibilities clearly from the design stage.

## 11. What Happens When Attempting to Bypass the Rule with a Custom Loader?

A loader can override `loadClass` or `findClass` and read bytes from any source. However, if it ultimately wants to turn those bytes into an ordinary runtime class, it must still use a **class-definition** mechanism subject to JVM/JDK rules, including the namespace restriction.

Pseudocode example:

```text
findClass("java.demo.Reserved"):
    bytes = read("java/demo/Reserved.class")
    return defineClass("java.demo.Reserved", bytes, 0, bytes.length)

Result with an ordinary application-defined loader:
    SecurityException
```

Do not catch `SecurityException` and pretend it simply means "class not found in file." Handle and log the real cause. If a specialized loader needs a parent fallback, falling back is only valid when the parent actually provides a **known standard class** — not to search for a custom `java.*` replacement.

Uncontrolled workarounds can also produce systems that are hard to test, incompatible across JDK releases, or violate platform safety assumptions. The sound design is to **rename the application class's package** and use standard Java APIs, rather than trying to make an application loader own a platform namespace.

### Why Does the Exception Not Depend on SecurityManager?

The name `SecurityException` may lead learners to think the error only occurs when a `SecurityManager` is enabled. In the case of `ClassLoader#defineClass`, **the `java.*` package rule is enforced directly** by the API/implementation. No application-installed `SecurityManager` is required for this exception to be thrown.

This is an important distinction in modern Java, where the traditional `SecurityManager` model has been restricted/deprecated and should not be relied upon as a general plugin sandboxing tool.

## 12. Common Errors and How to Diagnose Them

### 12.1. "Prohibited package name: java.demo"

An exception may include a message similar to:

```text
java.lang.SecurityException: Prohibited package name: java.demo
```

This is a **common message pattern**, not a contract for string parsing; the exact wording may vary by JDK. Check:

1. What `name` is being passed to `defineClass`?
2. Does it start with `java.`?
3. Which loader is actually calling `defineClass`?
4. Are you **defining a class yourself** or only calling `loadClass` to use a platform class?
5. Was a class file accidentally placed into a `java.*` package by a code generator, bytecode rewriting, or shading/relocation configuration?

**Fix:** use an application-owned package, such as `com.example.plugin`. Do not use a custom loader to define classes in a reserved namespace.

### 12.2. "The class file exists, yet it still cannot be loaded"

Having `java/demo/Reserved.class` on the classpath or in a JAR does not mean an application loader is allowed to define it. Finding a resource with `getResource` and defining a class with `defineClass` are two different operations.

If the class belongs to a named JDK module or runtime image, use the appropriate module/public API instead of copying the file and redefining it from an application loader.

### 12.3. "I already overrode loadClass—why is it still blocked?"

Because `loadClass` is the **lookup and selection** strategy, whereas `defineClass` enforces the **namespace constraint**. Changing parent/child order does not grant permission to define restricted names.

If you only want to use `java.lang.String`, delegate to the parent. If you want to implement custom application logic, put the class in your own package.

### 12.4. "SecurityException" without a java.* name

Another cause in `defineClass` can be an inconsistent signer certificate set within a package, or another environment policy. Inspect the full stack trace and cause; do not blindly rename packages when the real issue is code signing or sealing.

### 12.5. "java.lang.String cannot be cast to java.lang.String"

A same-name/failed-cast message (typically seen with application classes, not standard `String`) can occur when **two defining loaders** create two distinct runtime types. However, the protected `java.*` namespace usually blocks spoofed types before class creation, so distinguish library class-identity bugs from prohibited `java.*` package errors.

### 12.6. Can I use a name like javafoo.*?

Strictly speaking, the `name.startsWith("java.")` check does not treat `javafoo.*` as `java.*`. However, choosing package names easily confused with the JDK is poor for maintainability. Application packages should use reverse-domain naming, such as `org.example.learning`.

## 13. Comparison with Other Protection Constraints

| Scenario | Primary Issue | Appropriate Adjustment |
|---|---|---|
| Plugin defines `java.demo.Plugin` via a custom loader | Reserved `java.*` namespace | Rename to `com.acme.plugin.Plugin` |
| Two plugins each define their own copy of `shared.api.Plugin` | Different runtime type identities | Place shared API in the parent and delegate |
| Plugin uses `package demo;` but cannot access a package-private method in the app | Runtime package = package name + defining loader | Use a public API or share the same loader |
| Valid class, but bytes differ from `defineClass(name, ...)` | Binary name mismatch | Align the passed name and source bytes |
| Class file compiled with a newer JDK than the runtime | Version mismatch | Use a matching JDK or `javac --release` |
| Provider class not found due to loader/plugin classpath | Lookup/source configuration | Configure the right loader/classpath/module layer |
| Module does not `exports`/`opens` the required package | JPMS access rule | Design valid module descriptors and access |
| Static class initializer throws an error | Initialization failure | Fix the initializer cause, not just the loader |

Note: **changing the package to avoid the `java.*` restriction only solves the prohibited naming issue**; it will not fix other type, dependency, module, or bytecode errors if they also exist.

## 14. Library and Plugin Design Rules to Avoid Namespace Conflicts

1. **Use a namespace you own:** `com.yourcompany.project` or `org.yourteam.module`.
2. **Never create application classes in `java.*`**, including generated test classes or transformed sources.
3. **Use public JDK APIs** to interact with the platform; avoid mimicking standard classes with matching binary names.
4. **Preserve parent delegation** for platform types and shared contracts unless there is a rigorously tested architectural reason.
5. **Override `findClass` first**; only override `loadClass` when special namespace isolation is required and you fully understand locking and linking.
6. **Place shared APIs in a common loader**, so host and plugins communicate through a single runtime interface.
7. **Do not confuse compile-time with runtime:** the JVM loader may enforce checks that `javac` does not trigger for a given source setup.
8. **Inspect generated/relocated bytecode names** in build outputs/JARs; do not look only at source names.
9. **Do not treat ClassLoader as a sandbox:** untrusted code should be isolated using proper OS/process/container security mechanisms.
10. **Test on the actual target JDK** used in production, including Java version, module path, custom loaders, and bytecode generators.

### What Should Be Logged When Building a Custom Loader?

For errors of this kind, logs should include:

```text
requested binary name
loader implementation/class
defining/parent loader identity
bytecode source (JAR/URI/provider)
root exception class and cause
JDK version and module context (if relevant)
```

Avoid logging full bytecode or paths containing sensitive data. The `SecurityException` message and package name are usually enough to identify a `java.*` error, but traces remain useful when multiple loaders are involved.

## 15. Self-Check Questions

**1. Is `child.loadClass("java.lang.String")` prohibited like `child.defineClass("java.lang.String", ...)`?** No. `loadClass` delegates to the parent by default and can return an existing class; `defineClass` attempts to create a new runtime class.

**2. Since `java.demo.Reserved` is not in the standard JDK, can an application loader define it?** No, under the `defineClass` rule: a name starting with `java.` is the restricting factor, not merely whether the JDK already uses that name.

**3. Does the Java SE 17 Javadoc say "only the bootstrap loader"?** Not quite. It states **the platform class loader or its ancestors**. An application/custom child loader does not receive that privilege.

**4. Does changing a custom loader's parent to the platform loader allow the child to call `defineClass("java.demo.Reserved", ...)`?** No. The child is neither the platform loader nor one of its ancestors.

**5. Does successfully compiling a class in `java.demo` guarantee it can run from the classpath?** No. Compilation and runtime definition are two separate steps with different checks.

**6. Does `getResource("java/demo/Reserved.class")` finding bytecode mean the loader can define the class?** No. URL/resource lookup does not grant permission to define a runtime class.

**7. Why might a `SecurityException` not be related to `java.*`?** `defineClass` also checks signer certificate consistency within the same package, and the environment may enforce other rules.

**8. Does `definePackage("java.demo", ...)` grant permission to `defineClass` a class named `java.demo.Reserved`?** No. Package metadata and class-definition restrictions are independent concerns.

**9. Should you rename `java.demo.Widget` to `javax.demo.Widget` to bypass `java.*`?** No. Place your code in your own namespace, as other platform packages also have ownership and constraints.

**10. What is the basic solution for loading a plugin implementation from bytes?** Place the class in an application package, keep the shared API in the parent, override `findClass` in the custom loader, call `defineClass` with the matching binary name and valid bytes, and respect module/package constraints.

## 16. Official References

- **Java SE 17 API — `ClassLoader`**, especially `defineClass(String, byte[], int, int)` and the overload taking `ProtectionDomain` (`java.*` definition and `SecurityException`): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html
- **Java SE 17 API — `Class#getClassLoader`** (defining loader and bootstrap `null`): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html
- **JVMS §5.3 — Creation of Classes and Interfaces** (class identity: binary name + defining loader): https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.3
- **JVMS §5.4 — Linking, Verification and Access Control** (additional runtime checks): https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.4
- **JLS §7 — Packages and Modules** (Java packages and JPMS concepts): https://docs.oracle.com/javase/specs/jls/se17/html/jls-7.html

**Key takeaway:** **Applications may use `java.*` classes by letting the appropriate platform loader provide them, but custom/application loaders must not define `java.*` classes themselves.** Distinguish `loadClass` from `defineClass`, use an application-owned package, and design clear parent delegation and shared APIs instead of attempting to recreate platform classes or namespaces.

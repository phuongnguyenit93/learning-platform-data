# LinkageError Due to Duplicate Class Definition or Loading Constraint Violation

## 1. The Problem: Same Class Name, Yet the JVM Cannot Link

In Java systems using a **custom ClassLoader**, plugins, application servers, or hot reload, you may encounter the message:

~~~text
java.lang.LinkageError: loader ... attempted duplicate class definition
~~~

or:

~~~text
java.lang.LinkageError: loader constraint violation ...
~~~

Both can be related to class loading, but **they have different causes and different resolutions**:

- **Duplicate class definition:** The JVM detects that a loader attempts to recreate a class with the same binary name for which it has already been recorded as an initiating loader or has already defined. A ClassLoader cannot arbitrarily call defineClass a second time to overwrite the same class.
- **Loading constraint violation:** During the linking of related types across multiple loaders, the JVM requires a type name in a method/field descriptor to refer to **the same runtime Class** under specific loaders. If in practice two loaders have used **two different Classes** for that name, the JVM throws LinkageError to maintain type safety.

**Important:** The JVM completely allows **two different ClassLoaders to define two classes with the same binary name** in valid isolation scenarios. Name duplication between two loaders **is not a LinkageError by itself**. The error only occurs when violating the defining/initiating loader rule or a **mandatory type identity constraint**.

This article includes two Java 17+ examples verified with OpenJDK 21, error reproduction steps, how to read stack traces, and practical remediation approaches.

## 2. Distinguishing Defining Loader and Initiating Loader

### 2.1 Defining loader

A **defining loader** is the loader that actually defined the runtime class from a valid representation (for example, calling defineClass). For ordinary classes, **(binary name, defining loader)** determines the runtime type identity:

~~~text
("plugin.Item", LoaderA) != ("plugin.Item", LoaderB)
~~~

Two classes with the same source code and the same name are still distinct types if their defining loaders differ.

### 2.2 Initiating loader

An **initiating loader** is a loader that the JVM records as having initiated the request to load a class; it may not be the defining loader.

Example:

~~~text
ChildLoader.loadClass("api.Service")
     |
     +-- asks ParentLoader
              |
              +-- parent defines api.Service
     |
     +-- child gets back parent's Class
~~~

In this scenario:

- **ParentLoader** is the defining loader of api.Service.
- **ChildLoader** may be recorded by the JVM as an initiating loader of the same class defined by the parent.
- The child's **findLoadedClass("api.Service")** may see the Class as already initiated in the child, even though that Class's defining loader is the parent.

This is why a custom loader should not arbitrarily call **defineClass** on its own after delegating that name to its parent.

### 2.3 Cannot Arbitrarily Redefine Within the Same Loader

According to JVMS §5.3.5, if the JVM has recorded loader L as an initiating loader for name N, requesting to create a new definition of that name with L is invalid and causes a **LinkageError**.

More commonly encountered in practice: a loader **calls defineClass twice** with the same binary name. This is invalid behavior even when the two byte arrays are completely identical.

~~~text
Loader L
  defineClass("demo.Token", bytesV1) -> succeeds
  defineClass("demo.Token", bytesV1) -> LinkageError
  defineClass("demo.Token", bytesV2) -> LinkageError

Completely new Loader L2
  defineClass("demo.Token", bytesV2) -> can succeed
~~~

There is no automatic “overwrite class” mechanism in **ClassLoader.defineClass**. To update the method body of the same already-loaded class, there is the **java.lang.instrument.Instrumentation.redefineClasses/retransformClasses** mechanism with its own limitations. If you want a new runtime type version, create a new loader and manage the transition/lifecycle.

## 3. LinkageError Is a Family of Errors, Not All Are Duplicates

**java.lang.LinkageError** is an Error, not a checked exception. Related types include:

| Error type | Symptom | Cause category |
| --- | --- | --- |
| Direct **LinkageError**, message attempted duplicate class definition | The same loader tries to redefine an already-known name | Duplicate definition |
| Direct **LinkageError**, message loader constraint violation | Two loaders must agree on the runtime Class in a type descriptor but do not | Loading constraint |
| **NoClassDefFoundError** | The JVM needs a class, but its definition cannot be used/found or its initialization previously failed | Loading/linking/initialization |
| **ClassFormatError** | Bytes are not a valid class file | Format |
| **UnsupportedClassVersionError** | Class-file version is not supported by the JVM | Version |
| **VerifyError** | Bytecode does not satisfy the verifier | Verification |
| **NoSuchMethodError / NoSuchFieldError** | Bytecode references a member that does not exist in the runtime definition | Binary incompatibility |
| **IncompatibleClassChangeError** and subclasses | Used type/member does not match the expected binary relationship | Binary incompatibility |

**ClassNotFoundException** is not a LinkageError: it is a checked exception that lookup APIs such as loadClass may throw when a class cannot be found by name.

**ClassCastException** is also not a LinkageError: it is a RuntimeException when an invalid cast occurs. Two loaders can define two types with the same name **validly**, and then the application throws ClassCastException when attempting to cast an instance between two Classes with different identities, without any loading constraint violation.

**Do not fix based on the generic exception name.** Read **the actual exception class, full message, cause, timing of the error, and loader ownership path**.

## 4. Java 17+ Example #1: Duplicate Definition Within the Same Loader

### 4.1 Directory Structure

~~~text
project/
├── dup-src/
│   └── demo/
│       └── Token.java
└── src/
    └── DuplicateDemo.java
~~~

**dup-src/demo/Token.java**:

~~~java
package demo;

public class Token {
    public String value() {
        return "token";
    }
}
~~~

**src/DuplicateDemo.java**:

~~~java
import java.nio.file.Files;
import java.nio.file.Path;

public class DuplicateDemo {
    static class OnceLoader extends ClassLoader {
        OnceLoader(ClassLoader parent) {
            super(parent);
        }

        Class<?> define(String name, byte[] bytes) {
            return defineClass(name, bytes, 0, bytes.length);
        }
    }

    public static void main(String[] args) throws Exception {
        byte[] bytes = Files.readAllBytes(
                Path.of("dup-out/demo/Token.class"));

        OnceLoader loader = new OnceLoader(
                ClassLoader.getPlatformClassLoader());

        Class<?> first = loader.define("demo.Token", bytes);

        System.out.println("first = " + first.getName());
        System.out.println("defined by loader = "
                + (first.getClassLoader() == loader));

        try {
            loader.define("demo.Token", bytes);
            System.out.println("unexpected");
        } catch (LinkageError error) {
            System.out.println("second = "
                    + error.getClass().getSimpleName());
        }

        OnceLoader secondLoader = new OnceLoader(
                ClassLoader.getPlatformClassLoader());

        Class<?> second =
                secondLoader.define("demo.Token", bytes);

        System.out.println("other loader succeeds = "
                + (first != second));
    }
}
~~~

### 4.2 Compiling and Running

From the **project** directory:

~~~bash
javac -d dup-out dup-src/demo/Token.java
javac -d demo-out src/DuplicateDemo.java
java -cp demo-out DuplicateDemo
~~~

Windows PowerShell uses the exact same commands above because each classpath has only one entry.

**Actual stdout run on OpenJDK 21:**

~~~text
first = demo.Token
defined by loader = true
second = LinkageError
other loader succeeds = true
~~~

### 4.3 Why Does the Second Attempt Fail?

The first **loader.define("demo.Token", bytes)** call creates a runtime Class defined by **loader**. The second time, the same loader object requests defineClass with the same name; the JVM rejects creating a duplicate definition and throws LinkageError.

In the example, the catch block only prints **the error type name**, not the full message, because **the specific message contains the loader name and its format varies across JVMs**.

**Key observation:** Creating a new **secondLoader** and defining the same bytes succeeds. **first != second** is true. Having **two loaders define the same name is valid** as long as there is no constraint requiring them to match within a linking relationship.

This is an example of the difference between “duplicate within the same loader” and “duplicate across multiple loaders”.

### 4.4 Does This Example Intentionally Bypass the Default loadClass?

Yes. The **define** method is a direct wrapper around protected defineClass to demonstrate the error. This is **not a production loader design**.

A normal loader should let **ClassLoader.loadClass** handle caching/delegation and override **findClass** to read its own bytes. When a custom policy is needed, the following logic must still be preserved:

~~~text
getClassLoadingLock(name)
    |
    v
findLoadedClass(name)
    |
    v
parent delegation or appropriate custom route
    |
    v
findClass(name) when a new definition is genuinely needed
    |
    v
resolveClass if resolve=true
~~~

If defineClass is called repeatedly within the same loader because a file on disk has changed, the right approach is not to “swallow LinkageError and retry”, but to recognize that **the Class already exists**, or create a new loader for a separate deployment.

## 5. What Is a Loading Constraint Really?

### 5.1 The Type Safety Problem Across Multiple Loaders

Suppose class A from loader L1 invokes a method on class B from loader L2, and the method signature has the type **api.Payload**:

~~~java
api.Payload echo(api.Payload value)
~~~

A single runtime name **api.Payload** can point to different Classes if loader L1 and loader L2 obtain bytecode from separate sources.

When linking a method/field reference across this boundary, the JVM must ensure that **api.Payload in the descriptor refers to the same runtime type** across the relevant loaders. Otherwise, a runtime method call could assume the parameter/return value is compatible merely because the name matches in the constant pool, when in fact it is not the same Class.

### 5.2 JVMS §5.3.4 Notation

The JVMS describes loading constraints in the form:

~~~text
N^L1 = N^L2
~~~

Read as: **type name N initiated by loader L1 and loader L2 must denote the same Class** when that constraint applies.

Important points:

- This is a **type identity constraint**, not a directive that the JVM must use a single loader for the entire program.
- The JVMS imposes constraints at specific points during **preparation/resolution/lookup and method overriding**.
- Type names in **method descriptors** (parameters and return) and **field descriptors** may participate.
- For array reference types, the JVM checks the element type according to the applicable rules.
- When a constraint exists and two loaders have been recorded as initiating **two different Classes** for the same name N, the JVM throws **LinkageError**.
- A constraint can be imposed **before** both names are actually resolved in both loaders; a violation may surface later when one of the names is initiated.
- The JVM is not required to throw the error immediately at the **defineClass** line of the first class; the error may appear when preparation, linking, or resolution takes place.

### 5.3 Violation Conditions According to the Specification

According to JVMS §5.3.4, a loading constraint is violated when the required conditions are simultaneously satisfied:

1. There is an initiating loader L recorded by the JVM for Class C with name N.
2. There is an initiating loader L' recorded by the JVM for Class C' also with name N.
3. The set of loading constraints (and the transitive equivalence relation derived from it) requires **N^L = N^L'**.
4. Yet **C != C'**.

**It is not sufficient** to have only conditions 1, 2, and 4. There must be **condition 3: a constraint requiring type identity**.

### 5.4 What Creates a Loading Constraint?

Examples from the JVMS:

- A method override between a subclass/superclass or an interface implementation whose descriptor contains reference types.
- Resolution of a field reference crossing class boundaries with a field descriptor containing a reference type.
- Resolution of method/interface method references with reference-type parameters or return types.
- Corresponding linking steps that require symbolic references to denote the same runtime type.

It should not be assumed that every method whose signature contains a plugin-specific class causes a constraint violation. If all participants use **the same shared API Class** via delegation, the constraints are satisfied.

## 6. Java 17+ Example #2: Reproducing a Loader Constraint Violation

### 6.1 Model: Shared Interface on Host, Separate Payload in Child

This example intentionally creates an **unsafe** scenario:

- The parent/application loader defines **api.Api** and **api.Payload**.
- The child loader defines **another api.Payload** of its own with the **same binary name**.
- The child also defines **impl.Impl implements api.Api**. The implementing method has a descriptor containing api.Payload.
- When the JVM prepares to link the interface method table for Impl, it detects that **the child's api.Payload differs from the parent's api.Payload** in a signature that must match.

~~~text
AppLoader:
    api.Api
       method api.Payload echo(api.Payload)
    api.Payload   <-- Class P1

BytesLoader child:
    api.Payload   <-- Class P2, P2 != P1
    impl.Impl implements AppLoader's api.Api

Method echo(Payload) across the interface boundary:
    Payload^AppLoader = Payload^BytesLoader
                  but P1 != P2
         => loader constraint violation
~~~

### 6.2 Directory Structure

~~~text
project/
├── host-src/
│   └── api/
│       ├── Api.java
│       └── Payload.java
├── child-src/
│   ├── api/
│   │   └── Payload.java
│   └── impl/
│       └── Impl.java
└── src/
    └── ConstraintDemo.java
~~~

**host-src/api/Payload.java**:

~~~java
package api;

public class Payload {
    public String source() {
        return "host";
    }
}
~~~

**host-src/api/Api.java**:

~~~java
package api;

public interface Api {
    Payload echo(Payload p);
}
~~~

**child-src/api/Payload.java**:

~~~java
package api;

public class Payload {
    public String source() {
        return "child";
    }
}
~~~

**child-src/impl/Impl.java**:

~~~java
package impl;

import api.Api;
import api.Payload;

public class Impl implements Api {
    @Override
    public Payload echo(Payload p) {
        return p;
    }
}
~~~

The two **api/Payload.java** files have the same binary name but belong to **two different source roots**; do not compile them together into a single output folder.

### 6.3 Launcher ConstraintDemo.java

**src/ConstraintDemo.java**:

~~~java
import java.nio.file.Files;
import java.nio.file.Path;
import api.Api;
import api.Payload;

public class ConstraintDemo {
    static final class BytesLoader extends ClassLoader {
        BytesLoader(ClassLoader parent) {
            super(parent);
        }

        Class<?> defineLocal(String name, Path file)
                throws Exception {
            byte[] bytes = Files.readAllBytes(file);
            return defineClass(name, bytes, 0, bytes.length);
        }
    }

    public static void main(String[] args) throws Exception {
        System.out.println("parent Payload = "
                + Payload.class.getName());
        System.out.println("shared API from parent = "
                + (Api.class.getClassLoader()
                   == ClassLoader.getSystemClassLoader()));

        BytesLoader child = new BytesLoader(
                ClassLoader.getSystemClassLoader());

        Class<?> local = child.defineLocal(
                "api.Payload",
                Path.of("child-out/api/Payload.class"));

        System.out.println("same payload Class = "
                + (local == Payload.class));

        try {
            Class<?> impl = child.defineLocal(
                    "impl.Impl",
                    Path.of("child-out/impl/Impl.class"));

            System.out.println("impl defined = "
                    + impl.getName());

            Object obj = impl.getConstructor().newInstance();

            System.out.println("created = "
                    + obj.getClass().getName());
            System.out.println("invoked = "
                    + ((Api) obj).echo(new Payload()).source());

        } catch (LinkageError error) {
            System.out.println("error type = "
                    + error.getClass().getSimpleName());
            System.out.println("mentions constraint = "
                    + error.getMessage().contains("loader constraint"));
            System.out.println("error message = "
                    + error.getMessage());
        }

        // Fix: the new loader does NOT define api.Payload
        BytesLoader safe = new BytesLoader(
                ClassLoader.getSystemClassLoader());

        Class<?> impl2 = safe.defineLocal(
                "impl.Impl",
                Path.of("child-out/impl/Impl.class"));

        Api ok = (Api) impl2.getConstructor().newInstance();

        System.out.println("shared payload works = "
                + ok.echo(new Payload()).source());
    }
}
~~~

**defineLocal** intentionally calls defineClass directly to force the child to additionally define api.Payload and trigger the conflict. This is a diagnostic fixture, not a loader that should be used in production.

### 6.4 Compiling in the Correct Order

From the **project** directory, run each command:

~~~bash
javac -d host-out host-src/api/Payload.java host-src/api/Api.java

javac -cp host-out -d child-out child-src/impl/Impl.java

javac -d child-out child-src/api/Payload.java

javac -cp host-out -d demo-out src/ConstraintDemo.java

java -cp demo-out:host-out ConstraintDemo
~~~

**Why compile Impl before the child's separate Payload file?** Because **impl.Impl** must be compiled against the host's **api.Api** and **api.Payload** so that the method descriptor matches the shared interface. We only create another **api.Payload** in child-out afterward to intentionally break identity at runtime.

On Windows PowerShell, replace the last command with:

~~~powershell
java -cp "demo-out;host-out" ConstraintDemo
~~~

The javac commands using **-cp host-out** have only one entry, so they are identical on both operating systems.

### 6.5 Verified Stdout on OpenJDK 21

The output has been verified; the **error message** line depends on the specific loader name/hash and is therefore omitted from the fixed sample:

~~~text
parent Payload = api.Payload
shared API from parent = true
same payload Class = false
impl defined = impl.Impl
error type = LinkageError
mentions constraint = true
shared payload works = host
~~~

In the actual program, **between the mentions constraint and shared payload works lines, there is also the line**:

~~~text
error message = loader constraint violation in interface itable initialization ...
~~~

That is an **illustrative line showing the message format**, not an immutable verbatim string. The JVM may append the identity/address of the ClassLoaders, module names, and the method descriptor. **Do not test against the entire error message string**; if you need to check the error type, use the exception class and match the meaning of the message/stack trace.

Notably, the **created = ...** line is not printed in the failing run on OpenJDK 21 because the linking required during instantiation throws LinkageError beforehand.

### 6.6 Why Does the Error Appear After the “impl defined” Line?

When **child.defineLocal("impl.Impl", ...)** returns, the class has been created, yet the JVM may not have completed the specific linking/resolution steps that trigger constraint checking. The reflective instantiation call advances the JVM to **interface itable initialization**, where the JVM detects the incompatible signature.

**This is an important characteristic of LinkageError:** You should not assert that the error must appear immediately when calling defineClass, immediately when calling loadClass, or immediately when the method is invoked. The JVMS specifies the points at which constraints are checked; the exact stack frame and timing depend on the resolution type and JVM.

### 6.7 Why Does the Safe Version Work?

The **safe** loader only defines **impl.Impl** itself and does **not** define api.Payload itself. When it needs api.Api and api.Payload, it uses normal parent delegation. Therefore, the parent's **Api.echo(Payload)** method and the child's implementing method both refer to **the exact same parent api.Payload Class**.

The code:

~~~java
Api ok = (Api) impl2.getConstructor().newInstance();
System.out.println(ok.echo(new Payload()).source());
~~~

runs and returns **host**. This proves that the solution is **sharing API types through a single unified loader**, rather than renaming the method or catching and ignoring LinkageError.

## 7. A Subtle Distinction: The JVM Allows Isolation While Protecting Boundaries

A valid plugin system:

~~~text
PluginLoaderA: plugin.internal.Cache
PluginLoaderB: plugin.internal.Cache
~~~

Two classes with the same binary name but different definitions **can coexist** as long as there is no constraint forcing them to be the same type.

The problem arises when communicating across two loaders via a type that must match:

~~~text
Host interface:
    SharedResult execute(SharedInput arg)

Plugin implements:
    SharedResult execute(SharedInput arg)

If the host and plugin use the same SharedInput/SharedResult Class
    -> loading constraints are satisfied

If the plugin defines its own SharedInput/SharedResult with the same name
    -> a loading constraint violation may occur at the linkage boundary
~~~

**Rule of thumb:** Place **service interfaces, DTOs, callback types, and shared API dependencies** in the parent/shared loader. Isolate only implementation packages. A plugin runtime can still use child-first for its own implementation, but avoid child-first on **api.*** if those are types the host passes across method signatures.

### 7.1 Having the Same Binary Name Is Never Enough for Casting

Given:

~~~java
Class<?> a = loaderA.loadClass("plugin.Item");
Class<?> b = loaderB.loadClass("plugin.Item");

System.out.println(a.getName().equals(b.getName())); // true
System.out.println(a == b);                           // false
~~~

This snippet assumes both loaders actually define the class themselves and do not delegate to the same parent Class.

If you create an instance of a and try to cast it to type b, you may encounter a **ClassCastException**. This is a **runtime cast identity mismatch**, not necessarily a loader constraint violation. Distinguish them by error type and code path.

### 7.2 Runtime Packages Also Differ by Defining Loader

Even when two classes declare the same:

~~~java
package plugin.internal;
~~~

if they are defined by two different loaders, they do not automatically belong to the same **runtime package** for package-private access. When code needs to access a package-private member, an **IllegalAccessError** may occur if the bytecode links to a class in a different runtime package, even though the source text specifies the same package.

Do not fix this by changing package names indiscriminately; you must understand class identity, package/module access, and loader mapping.

## 8. Practical Causes of Duplicate Definition

### 8.1 findClass Is Called Directly Instead of loadClass

~~~java
// Wrong approach if a class with the same name is already loaded:
Class<?> c = customLoader.findClass("plugin.Service");
~~~

In normal applications, **findClass is protected** and should only be called within an appropriate loadClass algorithm. If a subclass exposes a public wrapper to call findClass/defineClass multiple times, the JVM may see the same name being defined again.

### 8.2 Overriding loadClass Without findLoadedClass

Unsafe example:

~~~java
@Override
protected Class<?> loadClass(String name, boolean resolve)
        throws ClassNotFoundException {
    return findClass(name);
}
~~~

This is an **anti-example** snippet inside a subclass, not for production use. It breaks parent delegation, caching, the resolve flag, and locking. Each load call risks calling defineClass yet again.

### 8.3 Contention Between Multiple Threads

If two threads simultaneously request a class name, code doing:

~~~text
Thread A: class not yet present -> reads bytes
Thread B: class not yet present -> reads bytes
Thread A: defineClass succeeds
Thread B: defineClass again -> LinkageError
~~~

is a classic race. Locking is needed across the entire **check → load → define** cycle, rather than synchronizing individual steps separately.

### 8.4 Replacing a JAR on Disk and Calling defineClass Again

The JVM does not automatically update an already-defined class when .class/.jar files change. A live loader is not a container that can “overwrite” class definitions.

To upgrade an implementation version, create a new loader and manage the old loader lifecycle, or use instrumentation within its allowed limits.

### 8.5 Plugin Registered Multiple Times in the Same Loader

A plugin engine may retry initialization or run two callbacks concurrently, both entering the same defineClass(name) logic. If ownership is unclear, a Class gets defined from multiple call paths.

**Solution:** Make a single component responsible for loading each binary name; use findLoadedClass properly with synchronization; avoid caching bytes as if that were equivalent to caching the Class object.

## 9. Practical Causes of Loading Constraint Violations

### 9.1 Overly Broad Child-First Delegation

If child-first also applies to the **host API package**, the plugin loader may redefine **api.Event**, **api.Result**, **api.Context**, and types appearing in method signatures of host interfaces.

The JVM may accept some classes first, and then detect the constraint when linking interface implementations, method resolution, or field access.

**Solution:** Parent-first for shared packages; selective child-first for implementations, such as **plugin.internal.***.

### 9.2 Duplicate Packaged Dependency Libraries

Both the host and the plugin include a copy of the library **lib.model.Dto** in their own classpath/JAR. If this class appears in a public API signature, having the plugin define its own copy can cause an identity mismatch.

**Solution:** A single copy of the shared dependency in a shared loader, or design the boundary not to directly pass objects belonging to isolated classes.

### 9.3 Replacing Implementation Classes While Forgetting the Shared Interface

The host casts a plugin implementation to the **api.Service** interface defined by the host, but the plugin has its own copy of api.Service. The error can be a **ClassCastException** or a related linkage error, depending on the timing and the relationships the JVM must resolve.

**Solution:** Use a single **shared api.Service Class** and keep the plugin's implementation in its own loader.

### 9.4 Customizing the Loader Graph Into Cycles or Inconsistent Lookups

Some frameworks have peer delegation, classloader-per-tenant, or module layer mappings. If lookup paths select different Classes for the same API name in places that must satisfy a type descriptor, the JVM will impose constraints and may detect a conflict.

**Solution:** Establish consistent package ownership and avoid having multiple sources define the same shared type independently. Do not try to disable JVM checks.

### 9.5 Reflection and Service Loading Do Not Fix Type Identity

**Thread Context ClassLoader**, **Class.forName**, and **ServiceLoader** can locate provider classes through another loader. However, merely switching the TCCL does not make separate API Class definitions from the host and plugin become one.

When debugging, inspect **serviceType.getClassLoader()**, **providerClass.getClassLoader()**, and API dependency classes. Explicitly adjust the loader of shared contracts.

## 10. Writing a Proper ClassLoader to Avoid Both Error Categories

### 10.1 Parent-First Pattern: Override Only findClass

For a custom bytecode source, you should start with:

~~~java
public final class PluginLoader extends ClassLoader {
    private final java.nio.file.Path root;

    public PluginLoader(ClassLoader parent,
                        java.nio.file.Path root) {
        super(parent);
        this.root = root;
    }

    @Override
    protected Class<?> findClass(String name)
            throws ClassNotFoundException {

        if (!name.startsWith("plugin.internal.")) {
            throw new ClassNotFoundException(name);
        }

        java.nio.file.Path file = root.resolve(
                name.replace('.', '/') + ".class");

        try {
            byte[] bytes = java.nio.file.Files.readAllBytes(file);
            return defineClass(name, bytes, 0, bytes.length);
        } catch (java.io.IOException ex) {
            throw new ClassNotFoundException(name, ex);
        }
    }
}
~~~

This is **a complete class snippet to illustrate the hook**, not a full main program. Path/name inputs in a production loader must be validated against path traversal, byte size, package restrictions, and untrusted sources.

**Benefit:** The default ClassLoader.loadClass algorithm already handles **getClassLoadingLock, findLoadedClass, parent-first, findClass, resolveClass**. Shared API packages are typically provided by the parent, avoiding redefinition in the child.

**Limitation:** If the parent also has an implementation class where the plugin must prioritize its own copy, findClass alone cannot change the delegation order. In that case, consider intentional package-based selective child-first delegation.

### 10.2 Selective Child-First Must Preserve Caching and Locking

Conceptual pattern:

~~~java
@Override
protected Class<?> loadClass(String name, boolean resolve)
        throws ClassNotFoundException {

    if (!name.startsWith("plugin.internal.")) {
        return super.loadClass(name, resolve);
    }

    synchronized (getClassLoadingLock(name)) {
        Class<?> c = findLoadedClass(name);

        if (c == null) {
            try {
                c = findClass(name);
            } catch (ClassNotFoundException absent) {
                c = super.loadClass(name, false);
            }
        }

        if (resolve) {
            resolveClass(c);
        }
        return c;
    }
}
~~~

This snippet is a **method inside a ClassLoader subclass that has an appropriate findClass**, not a standalone program.

It ensures these important elements:

- Shared APIs are not loaded child-first due to the restricted prefix.
- **findLoadedClass** avoids duplicate definitions that have already been initiated.
- **getClassLoadingLock(name)** manages concurrent requests.
- **findClass** is used for internal classes.
- Only falls back when not found via **ClassNotFoundException**; does not catch/swallow **LinkageError**.
- **resolveClass** is called when resolve=true.

Do not expand the child-first condition to **java.*** or arbitrary application packages without designing type boundaries, sealing, and module rules. Furthermore, this code is not a security sandbox.

### 10.3 Parallel-Capable Loaders

The JDK provides **registerAsParallelCapable()** and **getClassLoadingLock(name)** to support parallel loading of different class names.

If a subclass has not registered as parallel capable according to the API rules, the lock may be the loader object itself, reducing concurrency while preserving correctness as long as the algorithm uses the lock properly.

If a runtime has a non-tree loader graph or multiple cross-calling loaders, **loading deadlock** must be analyzed; removing synchronized to “avoid contention” can cause much more severe race conditions or duplicate definitions.

## 11. Diagnosing from Stack Traces: What to Look At?

### 11.1 Locate Loader Identity Information

A loader constraint error may mention:

~~~text
loader constraint violation ...
class loader X for class/interface A ...
class loader Y for class/interface B ...
different Class objects for type api.Payload ...
~~~

The JVM message typically includes **module**, **unnamed module**, **parent loader**, and the relevant class or method name. Do not omit this part when filing an issue or report.

A custom loader should have a useful **name/identifier** for debugging. In Java 9+, several ClassLoader constructors support a name; or override toString in a controlled way to distinguish plugin versions.

### 11.2 Print Classes and Defining Loaders

Inside a method with variables clazzA, clazzB:

~~~java
System.out.println(clazzA.getName());
System.out.println(clazzA.getClassLoader());
System.out.println(clazzA.getModule());

System.out.println(clazzB.getName());
System.out.println(clazzB.getClassLoader());
System.out.println(clazzB.getModule());

System.out.println(clazzA == clazzB);
~~~

This is an illustrative snippet requiring two Class objects. **Class.getClassLoader() may return null** for classes defined by the bootstrap loader; do not call .toString() directly without a null check.

**Do not compare only string names.** Two Classes with the same getName() but different Class objects indicate different defining loaders or identities.

### 11.3 Check Whether Class Files Actually Come from the Expected Source

With the JDK toolchain:

~~~bash
javap -verbose -classpath host-out api.Payload
javap -verbose -classpath child-out api.Payload
~~~

These two commands display classfile information from **two artifact roots**; they do not prove which source the JVM chose at runtime. Combine them with **getClassLoader()**, logs, and loader code.

Inspect an archive:

~~~bash
jar --list --file plugin.jar
~~~

If the same API class appears in both the host JAR and the plugin JAR, that is a signal to evaluate package ownership, not automatic proof that it causes a LinkageError.

### 11.4 JVM Unified Logging

On HotSpot/JVMs that support it:

~~~bash
java -Xlog:class+load=info -cp demo-out:host-out ConstraintDemo
java -Xlog:help
~~~

On Windows, replace the classpath separator with **;**. Class loading logging can help reveal which class was loaded, from which source, and at what stage, though the level of detail depends on the JVM/version. Do not infer the initiating loader solely from a generic log line; examine the stack trace and Class objects.

### 11.5 Thread Dumps When Errors Occur Under Concurrency

If duplication is caused by a race condition, the error may only appear under load. Check:

- Are multiple threads entering **findClass/defineClass** with the same name?
- Does the custom **loadClass** synchronize on **getClassLoadingLock(name)**?
- Is **findLoadedClass** called under the lock?
- Is the loader parallel capable?
- Is a class being loaded concurrently from multiple different call paths?
- Is there a parent/child/peer delegation cycle causing a deadlock?

Do not use try/catch on LinkageError to mask a race condition. It is a design symptom that must be fixed.

## 12. Interpreting When a Loader Constraint Violation Is Thrown

The JVMS allows the JVM to defer certain resolution steps. Therefore:

~~~text
child.defineClass("impl.Impl", bytes)
          |
          v
Class object is created successfully
          |
          v
Reflection newInstance / method resolution
          |
          v
JVM links interface/superclass method
          |
          v
Detects api.Payload^AppLoader != api.Payload^ChildLoader
          |
          v
LinkageError: loader constraint violation
~~~

Example 2 observes this exact scenario on OpenJDK 21.

Some programs may throw earlier, for example during preparation, or later when the relevant symbolic reference is resolved. When the error appears on the **newInstance()** line, it does not mean Impl's Java constructor is the direct cause. The JVM may be performing a required linking step **before the constructor executes**.

**Do not draw conclusions based on the exact line number.** Use the stack trace, classloader ownership, class signature, and JVMS loading constraint rules as your basis.

## 13. Common Wrong Solutions

### 13.1 Catching LinkageError and Using Another Class

You should not do this as normal control flow:

~~~java
try {
    return customLoader.loadClass(name);
} catch (LinkageError ignored) {
    return parent.loadClass(name);
}
~~~

This is an **anti-example** snippet with hypothetical customLoader/name/parent variables. If the JVM has already established a loading constraint or encountered a duplicate definition, ignoring the error and returning another Class can make application state/type consistency unpredictable.

**Better:** design delegation before defining classes. Fallback should only handle **ClassNotFoundException** according to policy, and should not treat LinkageError as “class not found”.

### 13.2 Renaming the Binary Name While Keeping the Old Shared Signature

Renaming the child's **api.Payload** to another name may avoid the name collision, but if the plugin still must implement the host's **Api.echo(api.Payload)**, the signature must use **the host's api.Payload itself**. You cannot fix a type mismatch simply by renaming the implementation or forcing an unchecked cast.

### 13.3 Changing the TCCL and Expecting It to Fix Class Identity

**Thread Context ClassLoader** only changes the lookup context for APIs that use it. It does not turn two runtime Class objects into one Class. You need to inspect the actual **defining loader** and the type boundary.

### 13.4 Deleting a Class File from a JAR After the Class Is Loaded

Modifying an artifact on disk does not destroy an already-existing Class object, nor does it reset initiated-loader records. When you need to upgrade a plugin, create a new loader and transition its lifecycle rather than expecting the JVM to forget the old definition on its own.

### 13.5 Removing Locking to “Eliminate Race-Induced LinkageError”

Doing so actually increases the probability of duplicate definition. You need atomicity across **check/load/define** via proper locking and must avoid invoking defineClass for the same name from multiple code paths.

### 13.6 Strict Parent-First for All Packages Without Understanding Versions

Parent-first is a good default for **shared APIs**, but if the parent and child have implementations with the same name and require isolation, parent-first may return the wrong version. Use **selective child-first for internal packages**, and parent-first for shared contracts.

## 14. Troubleshooting Checklist for Plugin Systems

When you encounter a ClassLoader-related LinkageError, check in this order:

1. **Read the exact exception class and message.** Classify it as duplicate definition or loading constraint; do not confuse it with ClassCastException.
2. **Record the binary name and loaders mentioned.** Include plugin version, module, and parent chain.
3. **If duplicate:** find where defineClass is called repeatedly; check whether custom loadClass uses findLoadedClass and a loading lock.
4. **If constraint:** find the method/field descriptor containing the type named by the JVM (for example, api.Payload).
5. Confirm whether the host and plugin are using **the same or different Class objects** for that shared type.
6. Check the JAR/dependency graph for two copies of the shared API/DTO being packaged into the child.
7. Choose one loader as the **owner** of shared contracts; have the child delegate properly to that owner.
8. If isolation is needed, restrict child-first to internal implementation packages.
9. Check package-private types, module exports/opens, and loader constraints at the boundary.
10. Rebuild artifacts with the proper classpath/module-path structure; do not just fix loader code while leaving duplicate dependencies behind.
11. Test concurrency and multiple hot-redeploy cycles; verify that old loaders are unregistered and not retained by threads/caches.
12. Keep a regression test checking **a == b** for types that must be shared and **a != b** for expected isolated implementations.

### 14.1 Signs of a Correct Fix

A properly configured host/plugin system typically has:

~~~text
Host loader
   |
   +-- api.Service
   +-- api.Payload
   |
   +-- Plugin loader
           |
           +-- plugin.internal.PluginImpl
           |
           +-- when needing api.Service/api.Payload:
               delegate to Host loader
~~~

The **Api.echo(Payload)** method signature on the host and the plugin implementation both see the api.Payload Class defined by the host. Thus, loading constraints are satisfied.

Other implementation packages can still be defined separately by the plugin loader. This is a design that enables intentional isolation **without breaking type safety**.

## 15. Comparing with Similar-Looking Errors

### 15.1 Duplicate LinkageError vs. ClassCircularityError

**ClassCircularityError** occurs when the JVM detects a cycle in the class hierarchy, such as a class attempting to inherit from itself via invalid bytecode. It belongs to the LinkageError family, yet it is **not a duplicate definition**.

### 15.2 NoSuchMethodError After Replacing a JAR

This is usually a binary compatibility issue: the compile-time API and runtime API do not match. It may involve classpath/classloader selection, though it does not mean the JVM imposed a loading constraint and found two different Classes.

### 15.3 NoClassDefFoundError and ClassNotFoundException

**ClassNotFoundException** is a checked exception from an explicit lookup; **NoClassDefFoundError** can occur when the JVM needs a class during linking/runtime execution whose definition is unavailable or whose initialization previously failed. A missing class can also stem from loader policy, so read the cause instead of assuming “duplicate class”.

### 15.4 ClassCastException: Same Name, Different Loader

~~~text
class plugin.Dto cannot be cast to class plugin.Dto
~~~

Two identical names can appear, yet the message usually includes loader/module details. This is a type mismatch at cast time, not necessarily a loader constraint violation. Inspect using **getClassLoader** and Class identity.

### 15.5 IllegalAccessError with the Same Package

Two classes with the same source package defined by different loaders may not belong to the same runtime package. Package-private access can fail. This is a runtime package/module access issue, not an attempted duplicate definition.

## 16. Self-Check Questions

**Question 1.** Loader L calls defineClass("demo.Token", bytes) twice. Is the second call treated as updating the old class?

**Answer:** No. That is a duplicate definition and can throw LinkageError. If you want a new version, you need a new loader or instrumentation within its specific limits.

**Question 2.** Loaders L1 and L2 both define demo.Token. Does that fact alone necessarily cause an error?

**Answer:** No. Two different runtime Classes can coexist as long as there is no constraint requiring them to match.

**Question 3.** Are the defining loader and the initiating loader always the same?

**Answer:** No. A child can initiate a class defined by the parent through delegation.

**Question 4.** Does the loading constraint notation N^L1=N^L2 require all classes in both loaders to be the same?

**Answer:** No. It constrains a specific type name N in the linking relationships enforced by the JVM.

**Question 5.** Why can the interface Api.echo(api.Payload) trigger a constraint when Impl is in the child loader?

**Answer:** The JVM requires the api.Payload type in the method descriptor to have a consistent identity between the interface and the implementation. If the child uses its own separate api.Payload Class, the constraint can be violated.

**Question 6.** Is LinkageError always thrown immediately at defineClass?

**Answer:** No. In some cases, the error appears during preparation/resolution or a subsequent corresponding linking step. Example 2 observes the error during instantiation.

**Question 7.** Why does the safe version of Example 2 work?

**Answer:** The safe loader does not define its own api.Payload; it uses the same shared Payload Class from the parent.

**Question 8.** Should you catch LinkageError and fall back to the parent like ClassNotFoundException?

**Answer:** No. LinkageError indicates a linking/consistency error; you need to fix the classloader policy, duplicate definitions, or artifacts.

**Question 9.** If a.getName().equals(b.getName()) is true while a==b is false, is this directly a loading constraint violation?

**Answer:** Not yet. That only shows two different Class identities. A loading constraint violation also requires a JVM constraint demanding that they match.

**Question 10.** Which loader should define API interfaces and DTOs used between the host and plugins?

**Answer:** Typically a parent/shared loader used by both; internal implementations are defined separately by the plugin loader.

**Question 11.** A duplicate definition race typically stems from missing which mechanisms?

**Answer:** Missing coordination of findLoadedClass and getClassLoadingLock(name) across the entire check/load/define path.

**Question 12.** Why can replacing a classpath JAR without creating a new loader still yield the old version?

**Answer:** The class has already been defined/initiated by the JVM; loadClass may return the old Class. The JVM does not automatically redefine it when the file on disk changes.

## 17. Summary

~~~text
A class name N is requested
       |
       v
Same loader attempts to redefine an already-known N?
       |
       +-- Yes -> LinkageError (duplicate definition)
       |
       +-- No
             |
             v
Two loaders have two different Classes for N?
             |
             +-- Yes, but no constraint
             |        -> can be valid (loader isolation)
             |
             +-- Yes, and the JVM requires N^L1 = N^L2
                      -> LinkageError (constraint violation)
~~~

**Three most important principles:**

1. **Duplicate definition within the same loader is not reloading**; preserve caching/locking and create a new loader if a new runtime version is needed.
2. **Two loaders having the same class name is not wrong by itself**; it becomes wrong when the JVM requires types across a method/field boundary to match while they have different Class identities.
3. **Share APIs/DTOs from a stable defining loader**, while implementations can be isolated per loader; verify using the Class object and defining loader, not just string names.

### Authoritative References for Further Reading

- JVMS Java SE 21 **§5.3.4 Loading Constraints**: https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html#jvms-5.3.4
- JVMS Java SE 21 **§5.3.5 Deriving a Class from a class File Representation**: https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html#jvms-5.3.5
- JVMS Java SE 21 **§5.4.2 Preparation and §5.4.3 Resolution**: https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html#jvms-5.4
- JLS Java SE 21 **§12.2 Loading of Classes and Interfaces**: https://docs.oracle.com/javase/specs/jls/se21/html/jls-12.html#jls-12.2
- ClassLoader Java SE 21 API: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassLoader.html
- LinkageError Java SE 21 API: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/LinkageError.html

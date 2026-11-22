# Verifying package-private Access When Using Two ClassLoaders in Java

## 1. The Problem: Same Package Name Does Not Necessarily Mean Same Access

Java allows types in the same package to use each other's **package-private** members. A field, method, or constructor declared without `public`, `protected`, or `private` has package-private access (also known as *package access*). A top-level class without `public` also has only package access.

Example:

```java
package p;

public final class Gate {
    static String secret() {
        return "package ok";
    }
}
```

Another class with `package p;` can normally call `Gate.secret()` at compile time. However, when separating the classes into **two defining ClassLoaders**, the JVM may reject that operation even though **the package name has not changed**.

According to **JVMS 17 `5.3**, a runtime package is determined by **package name and defining ClassLoader**. Two ordinary classes with the same name `p` defined by two different loaders belong to **two different runtime packages**.

This is a common pitfall in plugin architectures, servlet containers, test runners, and custom class loading:
- Maven/Gradle/IDE compiles cleanly because the source classes are in the same `package p`.
- After deployment, class A is defined by the parent loader, and class B is defined by the plugin/child loader.
- A call to a package-private method from B to A is no longer valid at runtime.
- The JVM throws **`IllegalAccessError`**, not `ClassNotFoundException`.

This lesson shows how to verify **each link in the chain**, with a runnable Java 17+ program and deterministic stdout.

## 2. Distinguishing Compile-Time Package and Runtime Package

### 2.1. When the Java Compiler Checks the Source

Two source files:

```java
// File p/Gate.java
package p;

public class Gate {
    static String secret() {
        return "package ok";
    }
}
```

```java
// File p/Caller.java
package p;

public class Caller {
    public static String call() {
        return Gate.secret();
    }
}
```

Both are seen by the compiler as belonging to package `p`. When compiled in an appropriate module/source context, `Gate.secret()` is allowed because Caller is in the same package.

The compiler emits a symbolic reference to the method `p/Gate.secret:()Ljava/lang/String;` in Caller's bytecode. This reference **does not yet point directly to a fixed Class object in the JVM that runs later**.

### 2.2. When the JVM Resolves the Reference

At runtime, the JVM determines:
- Which loader defines the runtime class `p.Caller`?
- Which loader finds/defines `p.Gate`?
- Do the two runtime classes belong to **the same runtime package**?
- What access flags does the method `secret()` have?
- In named modules, do readability/exports also affect public types?

If Caller and Gate are in two different defining loaders, simply having the same textual package name `"p"` is **not enough** to grant package-private access.

### 2.3. Diagram of the Two States

```text
Case A: same defining loader
  SharedLoader
    ├── p.Gate   (package p, loader SharedLoader)
    └── p.Caller (package p, loader SharedLoader)
  Caller.call() → Gate.secret() → OK

Case B: two defining loaders
  GateLoader
    └── p.Gate   (package p, loader GateLoader)
         ▲
         │ parent delegation
  CallerLoader
    └── p.Caller (package p, loader CallerLoader)
  Caller.call() → Gate.secret() → IllegalAccessError
```

**Definition of type identity:** a runtime class is typically identified by **binary name + defining loader**. A runtime package uses **package name + defining loader**. The two rules are related but must not be conflated into one.

## 3. The Initiating Loader Is Not Necessarily the Defining Loader

`ClassLoader.loadClass("p.Gate")` can be called on `CallerLoader`, yet the actual result is defined by `GateLoader` (parent).

Example:

```text
CallerLoader.loadClass("p.Gate")
     │
     ├── findLoadedClass("p.Gate") not found
     │
     ▼
GateLoader.loadClass("p.Gate")
     │
     └── GateLoader.findClass → defineClass
               │
               ▼
         Returns GateLoader's Class<?>
```

Therefore:
- **Initiating loader:** the loader used to initiate or record the load request.
- **Defining loader:** the loader that actually defines the runtime class.
- `Class.getClassLoader()` returns **the defining loader**.
- Calling `loadClass` on a child loader does not turn every class it returns into a class defined by that child loader.

This explains why `CallerLoader` finds `Gate` normally while having **no** package-private access to `Gate`.

## 4. A Java 17+ Program That Reproduces the Exact Error

The experiment will produce **a single set of bytecode** for `Gate` and `Caller`, and then run two different loader configurations. We do not change the source/bytecode between the two configurations. Thus, the observed difference comes from **the defining ClassLoader identity**.

### 4.1. Directory Structure

```text
package-access-demo/
├── src/
│   └── p/
│       ├── Gate.java
│       └── Caller.java
├── Host.java
├── compiled/
│   └── p/
│       ├── Gate.class
│       └── Caller.class
└── host-out/
    └── Host.class
```

Initially, you only need to create `src/p/Gate.java`, `src/p/Caller.java`, and `Host.java`. The output directories will be created by the compiler when running the commands at the end of the lesson.

### 4.2. File `src/p/Gate.java`

```java
package p;

public final class Gate {
    static String secret() {
        return "package ok";
    }
}
```

`Gate` is a public class. The `secret` method itself has no access modifier, meaning it is **package-private**.

### 4.3. File `src/p/Caller.java`

```java
package p;

public final class Caller {
    public static String call() {
        return Gate.secret();
    }
}
```

`Caller.call()` is the public entry point for the host to invoke via reflection. The package-private access occurs **inside Caller's method bytecode**.

### 4.4. File `Host.java` — Complete Source

```java
import java.io.IOException;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Set;

public final class Host {
    static final class DiskLoader extends ClassLoader {
        private final Path root;
        private final Set<String> owned;

        DiskLoader(Path root, ClassLoader parent,
                   Set<String> owned) {
            super(parent);
            this.root = root;
            this.owned = owned;
        }

        @Override
        protected Class<?> loadClass(String name, boolean resolve)
                throws ClassNotFoundException {
            synchronized (getClassLoadingLock(name)) {
                Class<?> result = findLoadedClass(name);
                if (result == null) {
                    result = owned.contains(name)
                            ? findClass(name)
                            : super.loadClass(name, false);
                }
                if (resolve) {
                    resolveClass(result);
                }
                return result;
            }
        }

        @Override
        protected Class<?> findClass(String name)
                throws ClassNotFoundException {
            if (!owned.contains(name)) {
                throw new ClassNotFoundException(name);
            }

            Path file = root.resolve(
                    name.replace('.', '/') + ".class");
            try {
                byte[] bytes = Files.readAllBytes(file);
                return defineClass(name, bytes, 0, bytes.length);
            } catch (IOException error) {
                throw new ClassNotFoundException(name, error);
            }
        }
    }

    public static void main(String[] args) throws Exception {
        Path root = Path.of("compiled");

        // Configuration A: the same loader defines both classes.
        DiskLoader shared = new DiskLoader(
                root,
                Host.class.getClassLoader(),
                Set.of("p.Gate", "p.Caller"));

        Class<?> goodCaller = shared.loadClass("p.Caller");
        Class<?> goodGate = shared.loadClass("p.Gate");

        System.out.println("same-loader class access: "
                + goodCaller.getMethod("call").invoke(null));
        System.out.println("same-loader defining identity: "
                + (goodCaller.getClassLoader()
                   == goodGate.getClassLoader()));

        // Configuration B: parent defines Gate,
        // child defines Caller.
        DiskLoader gateLoader = new DiskLoader(
                root,
                Host.class.getClassLoader(),
                Set.of("p.Gate"));

        DiskLoader callerLoader = new DiskLoader(
                root,
                gateLoader,
                Set.of("p.Caller"));

        Class<?> gate = gateLoader.loadClass("p.Gate");
        Class<?> caller = callerLoader.loadClass("p.Caller");

        System.out.println("same package text: "
                + gate.getPackageName().equals(
                        caller.getPackageName()));
        System.out.println("same defining loader: "
                + (gate.getClassLoader()
                   == caller.getClassLoader()));
        System.out.println("same runtime class Gate: "
                + (gate == goodGate));

        try {
            System.out.println("cross-loader call: "
                    + caller.getMethod("call").invoke(null));
        } catch (InvocationTargetException error) {
            // Method.invoke wraps exceptions thrown by the target method.
            if (error.getCause() instanceof IllegalAccessError) {
                System.out.println(
                        "cross-loader call: IllegalAccessError");
            } else {
                throw error;
            }
        } catch (IllegalAccessError error) {
            System.out.println(
                    "cross-loader call: IllegalAccessError");
        }

        // Reflection from Host outside package p:
        Method secret = gate.getDeclaredMethod("secret");
        try {
            secret.invoke(null);
            System.out.println(
                    "host reflection: unexpectedly allowed");
        } catch (IllegalAccessException error) {
            System.out.println(
                    "host reflection: IllegalAccessException");
        }
    }
}
```

### 4.5. Compiling and Running

In the `package-access-demo` directory on Bash/Linux/macOS:

```bash
mkdir -p compiled host-out
javac --release 17 -d compiled src/p/Gate.java src/p/Caller.java
javac --release 17 -d host-out Host.java
java -cp host-out Host
```

On Windows PowerShell:

```powershell
New-Item -ItemType Directory -Force compiled,host-out | Out-Null
javac --release 17 -d compiled src/p/Gate.java src/p/Caller.java
javac --release 17 -d host-out Host.java
java -cp host-out Host
```

**Important:** Only put `host-out` on the host application classpath. Do **not** add `compiled` to `-cp`; otherwise, the application parent loader may load Gate/Caller itself before the custom loader and accidentally break the experiment's premise.

`--release 17` selects the Java 17 class-file version/API target; the program can run on a compatible JDK 17+.

### 4.6. Verified Stdout

```text
same-loader class access: package ok
same-loader defining identity: true
same package text: true
same defining loader: false
same runtime class Gate: false
cross-loader call: IllegalAccessError
host reflection: IllegalAccessException
```

The experiment was compiled with `javac --release 17` and run on OpenJDK 21. The printed lines are values/error types and do not depend on detailed messages that may vary across JVM implementations.

## 5. Why Does Configuration A Succeed?

In configuration A:

```java
DiskLoader shared = new DiskLoader(
        root,
        Host.class.getClassLoader(),
        Set.of("p.Gate", "p.Caller"));
```

`shared` defines both binary names itself. The JVM sees:
- `p.Gate` belongs to package `p` defined by `shared`.
- `p.Caller` also belongs to package `p` defined by `shared`.
- Both have the same **runtime package (p, shared)**.
- `Caller.call()` is allowed to reference the package-private method `Gate.secret()`.

Result:

```text
same-loader class access: package ok
same-loader defining identity: true
```

Host **does not call `Gate.secret` directly**. Host calls the `public Caller.call` method, and the JVM executes bytecode inside Caller — where runtime package access is valid.

The difference is very important: if Host directly reflectively invokes `Gate.secret` without an access override, the reflective caller is Host (outside the package), so it is rejected.

## 6. Why Does Configuration B Throw IllegalAccessError?

In configuration B:

```java
DiskLoader gateLoader = new DiskLoader(
        root,
        Host.class.getClassLoader(),
        Set.of("p.Gate"));

DiskLoader callerLoader = new DiskLoader(
        root,
        gateLoader,
        Set.of("p.Caller"));
```

`callerLoader` owns `p.Caller`, while `p.Gate` is defined by the parent `gateLoader`. When Caller needs to reference Gate, Caller's loader can delegate up to gateLoader, so **class lookup succeeds**.

However, access checking is different from class lookup:
- `gate.getPackageName()` = `"p"`.
- `caller.getPackageName()` = `"p"`.
- `gate.getClassLoader() != caller.getClassLoader()`.
- Thus, **they are two different runtime packages**.
- `Gate.secret()` is still package-private.
- When the JVM resolves/accesses the method reference, Caller does not have permission to call it.

Result:

```text
same package text: true
same defining loader: false
same runtime class Gate: false
cross-loader call: IllegalAccessError
```

**The error condition is not corrupted bytes**. The two source files/bytecode are identical to configuration A, and the JVM found both. The difference is **who defines each class**.

`IllegalAccessError` is a subclass of `IncompatibleClassChangeError` and then `LinkageError`. It is not a checked exception that ordinary business code can handle like invalid input data.

## 7. Two Different Access Errors: IllegalAccessError and IllegalAccessException

The final section of the program prints:

```text
host reflection: IllegalAccessException
```

Here, Host retrieves the method via reflection:

```java
Method secret = gate.getDeclaredMethod("secret");
secret.invoke(null);
```

`getDeclaredMethod` can find the method description, including non-public members. However, `Method.invoke` performs a **reflection access check against the reflective caller**. Host does not belong to Gate's runtime package, so invoking it without an override causes a **checked `IllegalAccessException`**.

Distinction:

| Error | Mechanism | Example |
|---|---|---|
| `IllegalAccessError` | JVM linkage/bytecode member or type access | Cross-loader Caller calls Gate.secret |
| `IllegalAccessException` | Reflective invocation from a caller without access | Host calls Method.invoke without an override |
| `InaccessibleObjectException` | `AccessibleObject.setAccessible` rejected, typically due to JPMS encapsulation | Deep reflection from a module without opens |
| `ClassCastException` | Runtime object is not assignable to the target type | Two copies of api.Service with different defining loaders |
| `ClassNotFoundException` | Loader lookup does not find the binary name | Directory/JAR does not contain the class |

If reflecting on a **public** method of a **public class** with appropriate module access, reflection can usually invoke it from code outside the package. However, `getDeclaredMethod` “finding metadata” does not turn a package-private method into a public one.

### Why Does the Demo Catch InvocationTargetException?

`Method.invoke` can **wrap exceptions thrown by the target method** in an `InvocationTargetException`. When `Caller.call()` executes and throws `IllegalAccessError`, Host may receive the wrapper and must inspect `getCause()`. Because the timing of resolution/linking can vary, the program also catches `IllegalAccessError` directly in the test block.

**Do not turn every InvocationTargetException into IllegalAccessError.** You must inspect the actual cause and preserve other errors, as the program does.

## 8. Can You Use trySetAccessible to “Fix” This?

For the **unnamed modules** in this classpath example, a reflective caller can enable an access override on the package-private method:

```java
// Snippet, after the gate variable already exists.
Method secret = gate.getDeclaredMethod("secret");
boolean allowed = secret.trySetAccessible();

System.out.println("reflective override: " + allowed);

if (allowed) {
    System.out.println("reflected value: "
            + secret.invoke(null));
}
```

In a fixture belonging to unnamed modules and with appropriate access permissions, the expected output is:

```text
reflective override: true
reflected value: package ok
```

**However, this is not a fix for direct bytecode access**:
- `trySetAccessible` changes the accessibility of the **reflection operation** through that specific `Method`.
- It does not change the defining ClassLoader of Gate/Caller.
- It does not change the method access flags in bytecode.
- It does not turn two different runtime packages into one.
- `Caller.call()` still calls `invokestatic p/Gate.secret` invalidly in the split-loader configuration.

With **named modules**, deep reflection is also subject to `opens` directives and module access rules, so `trySetAccessible()` may return `false`. `setAccessible(true)` may throw `InaccessibleObjectException`.

**Do not treat opening reflection as a way to design a plugin boundary.** If the host and plugin need to communicate, you should use a public shared API rather than relying on reflective overrides.

## 9. What Changes If Gate.secret Is public?

Keep class Gate `public`, but change the method to:

```java
package p;

public final class Gate {
    public static String secret() {
        return "public API";
    }
}
```

In the demo's **unnamed-module classpath model**, a caller in a different runtime package can still invoke a public method on a public class if no other access conditions prevent it.

After modifying the source:
1. Recompile Gate/Caller for the right target.
2. Create a **new JVM or loader** to avoid reusing the already-defined old runtime class.
3. Re-run both cases and confirm that the method is actually public in the target artifact.

If the framework internals do not want the method exposed publicly, **do not arbitrarily change all package-private members to public**. A better design:
- keep the group of cooperating implementation classes in **the same defining loader**;
- create a small **public facade/interface** at the host/plugin boundary;
- place the shared API in the parent/common loader or a shared module.

### Access Rights by Configuration

| Configuration | Package-private method via direct bytecode | Public method on a public class |
|---|---|---|
| Same package name, same defining loader | Valid under package access | Valid if not blocked by other conditions |
| Same package name, different defining loaders | Not granted solely by package name | Can be valid if class/member/module access permits |
| Different package name, same loader | No package-private access | Can be valid |
| Child sees parent class via delegation | Does not become the same runtime package if defining loaders differ | A public API is the appropriate sharing mechanism |
| Named modules/ModuleLayers | Must also consider module graph/runtime package | Must also consider readability/exports |

## 10. Package-Private Top-Level Types Are Also Affected

A more severe case is when the class `Helper` itself is package-private:

```java
package p;

final class Helper {
    static String value() {
        return "internal";
    }
}
```

Another class in the package:

```java
package p;

public final class Entry {
    public static String run() {
        return Helper.value();
    }
}
```

These are **two illustrative source files**, not a standalone runnable project in this section. The compiler can allow `Entry` to access `Helper` if the sources belong to the same package.

However, if at runtime `Helper` is defined by Loader-A and `Entry` is defined by Loader-B, the JVM can block access to **the `Helper` type itself** due to package-private type access, before even checking the method inside.

The main case intentionally uses **public class Gate, package-private method secret** to illustrate a separate **member access** error without mixing in the access rights of the class declaration.

## 11. Class.getPackageName and Package Objects Can Be Misleading

`Class.getPackageName()` returns the package name string, which does not contain the defining loader identity. Therefore:

```java
boolean sameText =
        gate.getPackageName().equals(caller.getPackageName());
```

`sameText` is `true` in case B, yet Java still rejects the package-private call.

`java.lang.Package` is metadata about a package:
- `Class.getPackage()` returns the Package information corresponding to the class.
- `ClassLoader.getDefinedPackage(name)` looks up a package defined by that loader itself.
- `ClassLoader.getPackage(name)` has been deprecated since Java 9 and can search through the parent loader; using it to infer package-private access is very error-prone.

**Runtime package identity** must not be inferred solely from `Package.getName()`, `Package.isSealed()`, or annotations. You should take the two `Class<?>` instances and check **package name + defining loader**.

Nor should `CodeSource` alone be used:
- Two loaders can read **the same .class file** on disk yet produce two different runtime classes.
- Custom `defineClass` can attach a null/unhelpful CodeSource.
- A Java agent can transform bytes, causing the source URL and final bytes to differ.

`CodeSource` is useful for tracing an artifact, but **it does not replace ClassLoader identity**.

## 12. ClassCastException Also Involves Two Loaders, but Is a Different Error

Suppose the host and plugin each separately define an interface with the same binary name:

```text
HostLoader
  └── api.Service [Class A]

PluginLoader
  ├── api.Service [Class B]
  └── plugin.Impl implements Class B
```

The host wants to cast the `plugin.Impl` object to the host's `api.Service` (Class A). The two runtime interfaces have the same name but different defining loaders, so **they are not the same type**. The cast can throw `ClassCastException`.

This is **not** the package-private error of `Gate.secret`. Distinguish:
- **`IllegalAccessError`:** invalid type/member access rights.
- **`ClassCastException`:** the object does not belong to the runtime target type.
- **`NoSuchMethodError`:** the caller compiled a method reference, but the runtime class has no matching method signature.

All three errors can appear when the loader topology changes, but their fixes are not the same.

## 13. Designing a Shared API for Plugins

Preferred architecture:

```text
          Common Parent ClassLoader
                  │
                  └── api.PluginService
                      public interface
                         ▲
                         │ implements
            ┌────────────┴────────────┐
            │                         │
       PluginLoader-A             PluginLoader-B
       plugin.AImpl               plugin.BImpl
       plugin internals           plugin internals
```

The service contract can be:

```java
package api;

public interface PluginService {
    String execute();
}
```

This is an illustrative `api/PluginService.java` file; it is compilable but has no main method. The host and plugin must use **the same runtime Class<?> of this interface**, defined by the parent/common loader.

For each plugin:
- Implementation classes and package-private helpers should be in the same defining loader if they need package access.
- Cross-loader communication must go through public shared types/contracts or intermediate data.
- Avoid letting the child plugin redefine host API packages.
- If using child-first loading to isolate dependencies, ensure shared API namespaces are properly delegated to the parent.
- Pay attention to the method signatures of the shared API: DTO/exception types can also be duplicately defined in another loader, causing identity problems.
- Test the plugin in the real loader architecture, not just with a flat IDE classpath.

## 14. Why Does Child-First Easily Create a “Split Runtime Package”?

A custom child-first loader may prioritize class files in the plugin JAR:
- `p.Caller` is in the plugin → child defines it itself.
- `p.Gate` is not in the plugin → child delegates to the parent.
- Both classes share package `p` in source → but have different runtime packages.

Some frameworks have parent-first exceptions for platform APIs while remaining local-first for application classes. Each container/plugin framework has its own rules. You must not assume that every loader performs standard parent-first delegation across all namespaces.

**Prevention:** Do not split half of a group of internal classes between parent and child and expect package-private access. Choose a consistent loader owner for that group or properly publicize the extension boundary.

Changes such as:
- moving a JAR between common/lib and plugin/lib;
- shadowing a host package;
- upgrading the application server;
- switching a test runner from a single loader to multiple loaders;
- creating a new ModuleLayer;

all require regression testing for runtime class identity and access.

## 15. JPMS Adds Access Rules but Does Not Eliminate Runtime Packages

Java 9+ has named modules:
- `requires` / readability;
- `exports` for normal API access;
- `opens` for runtime deep reflection;
- `ModuleLayer` and module-to-loader mapping.

**Exports do not make package-private members public.** **Opens do not legitimize direct bytecode invocation from a class in a different runtime package.**

Example descriptors:

```java
module app.api {
    exports app.api;
}
```

```java
module app.plugin {
    requires app.api;
    provides app.api.Service with app.plugin.Impl;
}
```

These are **two illustrative descriptors**; `app.api.Service` and `app.plugin.Impl` must actually exist when placed into a complete project. The plugin can provide an implementation via `ServiceLoader` without exporting the entire implementation package to consumers.

With named modules, you also need to verify module access conditions for public types. However, **even if package `p` is exported, classes in two different defining loaders still cannot access each other's package-private members merely by sharing the name `p`**.

In particular, `--add-opens` is a scoped solution for deep reflection when appropriate, not a “fix” for a cross-loader package-private symbolic `invokestatic`.

## 16. Debugging the Issue Properly in Containers, Test Runners, and Plugin Hosts

Practical checklist:

1. **Record the original error**, including which class called which member, not just a “plugin failed” line.
2. **Read the cause chain**. If calling via `Method.invoke`, distinguish between a direct error and `InvocationTargetException.getCause()`.
3. **Obtain the `Class<?>` of the caller and target** from the right loader context if possible.
4. **Print the package name** using `getPackageName()`.
5. **Print the defining loaders** using `getClassLoader()` and compare identity with `==`.
6. **Inspect the parent delegation graph** and where both classes are defined, not just where the caller invokes `loadClass`.
7. **Inspect the actual class file** with `javap -p -c`; determine whether the method/field has package access or public/protected/private.
8. **Check for a binary API mismatch** if you see `NoSuchMethodError` instead of `IllegalAccessError`.
9. **Check JPMS** if the classes are in named modules or reflection is rejected due to opens/exports.
10. **Check test/prod classpaths** and how the host/container provides shared classes outside the plugin.
11. **Create a new loader/JVM for testing** to avoid cached class definitions.
12. **Choose to fix either the API or loader placement**, then run integration tests against the actual architecture.

### Standalone ClassLoader Probe

```java
public final class PackageProbe {
    private PackageProbe() {}

    public static void print(String name, Class<?> type) {
        System.out.println(name + " class=" + type.getName());
        System.out.println(name + " package="
                + type.getPackageName());
        System.out.println(name + " defining loader="
                + type.getClassLoader());
        System.out.println(name + " module="
                + type.getModule());
    }
}
```

This is a compilable `PackageProbe.java` file **without a main method**; integrate it into host/test code. The loader/module string values are runtime data, so there is **no fixed stdout**.

### Inspecting Bytecode

After running the example in section 4:

```bash
javap -p -c -classpath compiled p.Gate
javap -p -c -classpath compiled p.Caller
```

- `-p` displays non-public members.
- `-c` displays instructions.
- You can see that `Caller.call` contains `invokestatic` to `Gate.secret`.
- Running `javap` on output files confirms the **bytecode on disk**; it does not by itself tell you which defining loader the JVM process is using.

## 17. Why Is Package Sealing Not the Solution?

A JAR manifest can **seal a package**, making class definitions in that package adhere to code source constraints within a single loader. Package sealing and package-private access are two different concepts.

Do not infer from:
- `Package.isSealed() == true`;
- the same package name;
- the same JAR filename;
- the same CodeSource URL;

that two classes belong to the same runtime package if **their defining loaders differ**.

A sealing violation has its own error, but it does not merge two runtime packages into one and does not elevate package-private access.

## 18. Common Misconceptions

| Misconception | Reality |
|---|---|
| If two classes have the same `package p;`, they must be in the same runtime package | They must have the same defining loader (per JVMS `5.3) |
| If the code compiles, package-private is guaranteed to work at runtime | Deployment can change loader boundaries |
| The child loader found the parent's class, so that class belongs to the child | The parent can still be the defining loader |
| Having the same `getPackageName` is sufficient | Defining loaders must be compared |
| Two class files with identical bytes mean the same runtime Class | No, if defined by two independent loaders |
| `ClassLoader.getPackage(name)` is enough to confirm package-private | It may find Package metadata from the parent; it does not determine the runtime package |
| Same `CodeSource` means the same runtime class | No; type identity depends on the loader |
| `setAccessible(true)` fixes all package-private errors | It only affects reflection access subject to conditions |
| `--add-opens` fixes direct package-private bytecode access | No |
| Switching child-first to parent-first is always safe | Shared APIs, versions, and classpaths must be checked |
| `IllegalAccessException` and `IllegalAccessError` are the same | A reflection checked exception differs from a linkage Error |
| A two-loader `ClassCastException` is the same as a package-private error | Different: type assignability versus member access |
| JPMS exports make everything in a package public | It does not turn non-public members into public ones |
| Replacing a JAR on disk makes the JVM immediately use the new classes | Already-loaded runtime classes usually require a new loader/process |
| Placing plugin internals in the same package name as the host allows accessing host internals | Not if defining loaders differ, plus module constraints apply |

## 19. Self-Check Questions

1. **Which modifier does package-private require?** Declare without `public`, `protected`, or `private`.
2. **Is the `package p;` declaration enough to determine runtime package identity?** No.
3. **How does the JVMS define a runtime package?** By package name and defining ClassLoader.
4. **Is the defining loader always the loader on which the client calls `loadClass`?** No.
5. **Do two different loaders reading the same bytecode produce the same runtime class?** No, if each loader defines it itself.
6. **Why can configuration A call `Gate.secret`?** Gate and Caller belong to the same runtime package defined by the shared loader.
7. **Why is configuration B rejected?** Gate and Caller are defined by two different loaders; package-private is not accessible.
8. **What error occurs in Caller.call in configuration B?** `IllegalAccessError`.
9. **What error occurs when Host reflectively invokes `secret` without an override?** `IllegalAccessException`.
10. **What errors can `InvocationTargetException` wrap?** Any Throwable thrown by the target method, including `IllegalAccessError` in the illustrated scenario.
11. **Does `trySetAccessible` change JVM package identity?** No.
12. **Does opening a module with `opens` make a direct cross-loader package-private call valid?** No.
13. **What if `Class.getPackageName()` is equal for two classes whose loaders differ?** They are still in different runtime packages.
14. **Can a package-private top-level class be subject to an access check from another loader?** Yes.
15. **When Gate.secret is changed to public, is the unnamed-module model still blocked by package-private?** No, provided other access conditions are satisfied.
16. **Where should a public interface shared between host and plugin be placed?** In a stable shared parent loader/module.
17. **Why is Host run with only `-cp host-out`?** To prevent the parent from defining the target classes from compiled.
18. **To diagnose a runtime package issue, what should be printed?** Class name, package name, defining loader, module, and source if available.
19. **Does package sealing merge two loaders?** No.
20. **If compilation passes but runtime throws IllegalAccessError, what should be checked first?** Member flags, caller/target defining loaders, loader topology, and module rules.

## 20. Official References

- [JVMS 17 5.3 — Creation and Loading](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.3): defining/initiating loader, runtime class identity, **runtime package**.
- [JVMS 17 5.4.4 — Access Control](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.4.4): JVM checks during resolution of classes/members.
- [JLS 17 6.6 — Access Control](https://docs.oracle.com/javase/specs/jls/se17/html/jls-6.html#jls-6.6): package-private, protected, public, and private in Java source.
- [Java SE 17 ClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html): `loadClass`, `findClass`, `defineClass`, and `getDefinedPackage`.
- [Java SE 17 Class](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html): `getPackageName`, `getClassLoader`, and `getModule`.
- [Java SE 17 IllegalAccessError](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/IllegalAccessError.html): member/type access error at linkage/runtime.
- [Java SE 17 Method](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Method.html): `invoke` and InvocationTargetException.
- [Java SE 17 AccessibleObject](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AccessibleObject.html): `canAccess`, `trySetAccessible`, and reflection access rules.
- [Java SE 17 Module](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Module.html): module readability, exports, and opens.

**Conclusion:** When Java code uses package-private access, **having the same package name in source is not enough**. Two classes must belong to **the same runtime package**, meaning they share the corresponding package name and defining ClassLoader. In the example, **same loader → succeeds**, while **splitting Gate and Caller across parent/child defining loaders → IllegalAccessError**. To design reliable plugins/containers, place internal classes that need package access in **the same loader**, and communicate through a **public shared API** across loader boundaries.

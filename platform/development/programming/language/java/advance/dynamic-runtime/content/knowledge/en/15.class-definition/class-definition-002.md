# 15.2 `Lookup.defineClass` and Its Relationship with the Package, Class Loader, and Module of the Lookup Class

`MethodHandles.Lookup.defineClass(byte[] bytes)` (Java 9+) uses a `Lookup` with appropriate permissions to **define and link a class or interface from bytecode**, according to **the context of the lookup class**. This API does not take an arbitrary `ClassLoader` or `Module` parameter: the defined class will belong to **the same defining class loader, the same runtime package, and the same protection domain** as `lookup.lookupClass()`. In Java with the module system (JPMS), the result also resides in **the corresponding module of the lookup class**. The bytecode must declare a class/interface name in **the same package** as the lookup class, and `lookup.lookupModes()` must have the `PACKAGE` bit.

The key point: **the class bytes provide the class definition, while `Lookup` provides the privileged context to place that class into the runtime**. Writing an arbitrary `package` in a `.java` file or placing a `.class` in an arbitrary directory does **not** make `defineClass` move the class to a new package/module/class loader at will.

This lesson belongs to group **15. Class Definition**, focusing on the question: why `Lookup.defineClass` constrains the package, defining loader, and module of the `lookup class`, along with how to use this API validly, verifiable with Java 17+.

After studying, you can:

- Accurately interpret the contract of `Lookup.defineClass(byte[])` and `Lookup.PACKAGE` permissions.
- Distinguish **package name in bytecode** from **runtime package**, class identity, class loader, and module.
- Understand how `MethodHandles.lookup()`, `publicLookup()`, `dropLookupMode`, `Lookup.in`, and `privateLookupIn` relate to class-defining permissions.
- Prove that the new class shares the same loader/package/module/protection domain as the lookup class, even with a **named module**.
- Explain that `defineClass` **does not run the static initializer**; class creation and class initialization are two different phases.
- Analyze wrong-package errors, missing PACKAGE mode, duplicate definition, invalid bytecode, and class-loading conflicts.
- Understand the intentional exception: `privateLookupIn` can create a lookup in the target package/module **when JPMS allows**, not bypassing JPMS.
- Compare `Lookup.defineClass`, `ClassLoader.defineClass`, and `Lookup.defineHiddenClass`; choose the appropriate API.
- Run three standalone examples: classpath, a single named module, and two named modules with `opens`.

## 1. Exact Contract of `Lookup.defineClass`

API:

```java
public Class<?> defineClass(byte[] bytes)
        throws IllegalAccessException
```

`bytes` must be the contents of **a valid class file** according to the Java Virtual Machine Specification. The method defines and links a class/interface from bytecode and returns the `Class<?>` object of the newly defined class.

There are four constraints to check together (along with permissions and initialization):

| Component | Determining source | Requirement / result |
| --- | --- | --- |
| **Package name in bytecode** | `this_class` of the class file | Must have the same package name as `lookup.lookupClass()` |
| **Defining class loader** | `lookup.lookupClass().getClassLoader()` | The new class is defined by **the same loader** |
| **Runtime package and module** | Runtime context of the lookup class | Same runtime package and same corresponding module; cannot move the class to another module arbitrarily |
| **Protection domain** | `lookup.lookupClass().getProtectionDomain()` | The new class uses **the same protection domain** per the API contract |
| **Creation permission** | `lookup.lookupModes()` | Must have `MethodHandles.Lookup.PACKAGE` |
| **Initialization (`<clinit>`)** | JVM initialization rules | `defineClass` **does not run the static initializer** |

Treat `Lookup` as a **capability** bound to a location and a set of permissions. From the same `byte[]`, calling `lookupA.defineClass(bytes)` and `lookupB.defineClass(bytes)` is **not equivalent** if the lookup classes differ in loader, package, module, or access permissions.

### 1.1. Mental Formula

```text
Class file bytes
    - binary class name: p.q.Generated
    - methods, fields, superclass, interfaces, attributes
                   |
                   v
        Lookup.defineClass(bytes)
                   |
        +----------+-----------+
        |                      |
    Lookup identity        Lookup permissions
    - lookupClass()        - PACKAGE required
    - its class loader     - restricted modes matter
    - its runtime package
    - its module
    - its protection domain
                   |
                   v
    Defined class with same context
    (not an arbitrary new loader/module/package)
```

If the bytes specify `p.q.Generated` while `lookup.lookupClass()` is in package `x.y`, the method does **not** define the class into `p.q` and "fix the lookup itself": it rejects with `IllegalArgumentException` due to package mismatch.

If the bytes specify the right package while the lookup lacks `PACKAGE`, the result is `IllegalAccessException`. The two errors are different: **the package constraint of the target class** differs from **the permission of the requester**.

### 1.2. The API Does Not Select a Package via a Parameter

The signature only has `byte[]`; there is no `String packageName`, `ClassLoader loader`, or `Module destination`. That is a clear difference from custom class-loading APIs.

Illustrative example:

```java
// In a class in package demo.app:
MethodHandles.Lookup lookup = MethodHandles.lookup();
Class<?> c = lookup.defineClass(bytes);
```

In this example `c` must be defined in package `demo.app`, if it succeeds. The fact that the caller receives a `byte[]` from the `other` directory, HTTP, or a database does **not** change the condition: only the class file contents and the lookup context decide. The snippet is illustrative and needs imports, the `bytes` variable, and checked exception handling.

## 2. `lookupClass()` Is Not Necessarily "The Class Containing the Source Line" Forever

`MethodHandles.lookup()` is a caller-sensitive factory that creates a lookup with permissions according to **the class that calls it**. Inside a method of `demo.app.Host`:

```java
MethodHandles.Lookup lookup = MethodHandles.lookup();
System.out.println(lookup.lookupClass()); // class demo.app.Host
```

A lookup can be **transferred/restricted** by other APIs such as `lookup.in(SomeClass.class)` or `MethodHandles.privateLookupIn(SomeClass.class, lookup)`. After that, `lookup.lookupClass()` can change, and permissions can also be reduced or conditionally granted. When using `defineClass`, what matters is **the actual lookup class of the Lookup object at the time of the call**, not the class in source code that happens to hold the lookup variable.

A conceptual example:

```java
// Two illustrative lines, assuming hostLookup was created in Host:
Class<?> effectiveContext = hostLookup.lookupClass();
int modes = hostLookup.lookupModes();
```

If a lookup object is passed through a framework, plugin, or helper, you cannot deduce where the new class will reside merely by looking at the helper class. You need to determine `effectiveContext`, the defining loader, package, module, and `modes`.

### 2.1. Why Is `Lookup.PACKAGE` Required?

The new class is defined in the same runtime package as the lookup class. Thus, it can use **package-private members** that Java allows classes in the same runtime package to access. If the API allowed a lookup with only `PUBLIC` to create a class in a package it has no permission for, a caller could generate a new class to access package-private members unintendedly.

The `PACKAGE` bit acts as confirmation that the lookup came from, or was validly delegated to, a context with package access permission. This is an **access control rule**, not merely a flag for performance.

Check:

```java
MethodHandles.Lookup lookup = MethodHandles.lookup();
boolean hasPackageAccess =
        (lookup.lookupModes() & MethodHandles.Lookup.PACKAGE) != 0;
```

The illustrative snippet assumes appropriate imports. Use the `&` operator to check the bit; do not assume every `Lookup` has full modes.

### 2.2. `publicLookup()` Is Not Enough

`MethodHandles.publicLookup()` is primarily for looking up public members under Java module/export restrictions. It **does not have `PACKAGE` access**, so it cannot be used to define a class via `defineClass`:

```java
// Illustrative with valid class file bytes:
MethodHandles.publicLookup().defineClass(bytes);
// IllegalAccessException
```

Do not try to work around this by making the defined class `public`. `public` is a class modifier; `PACKAGE` here is a **permission of the Lookup**—two different things.

### 2.3. `dropLookupMode(PACKAGE)` Removes the Permission

`Lookup.dropLookupMode` creates a lookup with restricted permissions. If `PACKAGE` is dropped, it can no longer be used to `defineClass` in the old package:

```java
MethodHandles.Lookup restricted =
        lookup.dropLookupMode(MethodHandles.Lookup.PACKAGE);
restricted.defineClass(bytes); // IllegalAccessException
```

The illustrative snippet assumes `lookup` and `bytes` exist. When dropping `PACKAGE`, dependent modes may also be removed per Lookup rules; do not treat the API as "just flipping an arbitrary bit" while ignoring the permission structure. This is a clear example of **the lookup class remaining the same while the ability to define a class is lost**.

## 3. A Runtime Package Differs from a Mere `package` String

In Java source:

```java
package demo.app;
```

this is the language-level package name. At runtime, class identity and package relationships also involve the **defining class loader** and module. Two classes with the same package name string defined by **two different class loaders** are not automatically considered in the same runtime package for accessing package-private members.

Distinguish between:

- **Binary name:** e.g., `demo.app.Generated`, encoded into `this_class` of the class file.
- **Defining loader:** the `ClassLoader` that actually defines the class, not necessarily the same as where the file bytes are stored on disk.
- **Module:** `Class.getModule()` indicates the runtime module owning that class.
- **Runtime package:** the package relationship at runtime bound to class identity/module/loader, which cannot be created simply by placing two files in the same directory.
- **Protection domain:** the object describing the security context of the class; `Lookup.defineClass` uses the domain of the lookup class.

Therefore, "placing the class file in the same package folder" is not enough to guarantee the class is defined in the right place. Directories are just a way to organize **inputs**; `Lookup` and the class-loading context determine the **runtime output** location.

### 3.1. Class Identity: Name and Loader

The JVM identifies a class not only by the `Class.getName()` string, but also by its **defining loader**. Two classes with the same binary name defined by **two different class loaders** are two different classes; they cannot be cast to each other as the same type.

Conversely, within **the same defining loader**, defining **the same binary name** a second time usually results in `LinkageError` due to duplicate class definition. `Lookup.defineClass` is **not** a mechanism for reloading the same class name in-place. To get a new version in a similar loader, consider a new class name or a new-generation class loader according to your designed architecture; do not redefine bytecode into the same name/loader by calling the API again.

### 3.2. Same Defining Loader Does Not Mean Bytes Must Be on the Classpath

`defineClass(bytes)` takes `byte[]` content supplied by the caller. The bytes may be produced by a compiler run beforehand, a generator, or another data source. You do not need to put `Generated.class` on the runtime classpath for a lookup to define it; you only need valid bytes and for the class's dependencies to be resolvable in the corresponding class-loading context.

The example in this lesson will intentionally leave `Generated.class` **outside the runtime classpath**, read the bytes via `Files.readAllBytes`, and then define it using the lookup of a class on the runtime classpath. This shows that **where bytes are stored** and **the defining loader of the resulting class** are two independent concepts.

### 3.3. Same Loader Does Not Automatically Create a New Module

In a normal classpath application, the lookup class usually resides in an **unnamed module** of that loader, and the new class belongs to that same unnamed module. With a named module, the lookup class resides in a **named module** already created by the module system; `defineClass` adds the class to **the lookup class's module**, without creating a new module.

A named module does not appear automatically just because the bytes declare a new package, and `defineClass` is not an API that reads `module-info.class` to create arbitrary modules. To create a new module/layer with an independent lifecycle, use module layer design, loaders, and dedicated APIs.

## 4. Definition and Initialization: Two Different Steps

The specification states that `Lookup.defineClass` **creates and links the class**, but **does not run the class initializer** `<clinit>`. This is an important distinction when debugging:

```text
read .class bytes
      |
      v
lookup.defineClass(bytes)
      |
      +--> Class<?> already exists
      +--> verification / linking per JVM
      +--> static initializer has NOT run automatically just from defineClass
      |
      v
an active use of the class
      |
      +--> JVM initialization (if not yet run)
      +--> run static initializer / static field initializers
      |
      v
execute invoked logic
```

A class with a static block:

```java
static {
    System.out.println("Generated.<clinit>");
}
```

will **not** print this line merely from `lookup.defineClass(bytes)`; however, invoking a static method for the first time via `MethodHandle` or reflection can cause the JVM to initialize the class before running the method.

Distinguish:

- **Load/define:** creates the runtime object representing the class, placing the class in the appropriate loader and module.
- **Link:** verification, preparation, and resolution steps per JVMS; some symbolic references may be resolved lazily.
- **Initialize:** executes `<clinit>` according to active-use rules.

`defineClass` does not guarantee that all dependencies will be resolved and all errors will appear during this call: some linkage or initialization errors may surface when the class is used. It also **does not** call a constructor or create an object instance of the new class.

## 5. Complete Example 1 — Classpath, Same Package, Loader, Module, Domain

The first example uses three Java files: a host class `LookupDefineClassDemo`, a class to be defined `Generated`, and a class intentionally in **the wrong package** `WrongPackage`.

After compiling, the program puts only `LookupDefineClassDemo.class` and `PackagePeer.class` onto the runtime classpath; the `Generated` class is loaded from a byte array. `PackagePeer` has a **package-private** method to prove the new class is defined in the right runtime package and can access it validly.

### 5.1. Directory Structure Before Running

```text
src/
  sample/dynamic/
    LookupDefineClassDemo.java
    Generated.java
  other/
    WrongPackage.java

build/       # compiler output; contains all classes
runtime/     # runtime classpath; contains only host and PackagePeer
```

### 5.2. File `src/sample/dynamic/LookupDefineClassDemo.java`

```java
package sample.dynamic;

import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.nio.file.Files;
import java.nio.file.Path;

public class LookupDefineClassDemo {
    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup lookup = MethodHandles.lookup();
        byte[] bytes = Files.readAllBytes(Path.of(args[0]));
        byte[] otherPackage = Files.readAllBytes(Path.of(args[1]));

        System.out.println("lookup class: " + lookup.lookupClass().getSimpleName());
        System.out.println("PACKAGE mode: "
                + ((lookup.lookupModes() & MethodHandles.Lookup.PACKAGE) != 0));

        Class<?> generated = lookup.defineClass(bytes);
        System.out.println("defined name: " + generated.getName());
        System.out.println("same loader: "
                + (generated.getClassLoader() == lookup.lookupClass().getClassLoader()));
        System.out.println("same runtime package: "
                + generated.getPackageName().equals(lookup.lookupClass().getPackageName()));
        System.out.println("same module: "
                + (generated.getModule() == lookup.lookupClass().getModule()));
        System.out.println("module named: " + generated.getModule().isNamed());
        System.out.println("same protection domain: "
                + (generated.getProtectionDomain()
                == lookup.lookupClass().getProtectionDomain()));
        System.out.println("class defined but not initialized");

        MethodHandle mh = lookup.findStatic(
                generated, "message", MethodType.methodType(String.class));
        System.out.println("message: " + (String) mh.invokeExact());

        try {
            lookup.defineClass(otherPackage);
        } catch (IllegalArgumentException e) {
            System.out.println("other package: IllegalArgumentException");
        }

        try {
            lookup.dropLookupMode(MethodHandles.Lookup.PACKAGE)
                    .defineClass(otherPackage);
        } catch (IllegalAccessException e) {
            System.out.println("without PACKAGE: IllegalAccessException");
        }

        try {
            MethodHandles.publicLookup().defineClass(bytes);
        } catch (IllegalAccessException e) {
            System.out.println("public lookup: IllegalAccessException");
        }

        try {
            lookup.defineClass(bytes);
        } catch (LinkageError e) {
            System.out.println("duplicate definition: "
                    + e.getClass().getSimpleName());
        }
    }
}

class PackagePeer {
    static String secret() {
        return "same-runtime-package";
    }
}
```

### 5.3. File `src/sample/dynamic/Generated.java`

```java
package sample.dynamic;

public class Generated {
    static {
        System.out.println("Generated.<clinit>");
    }

    public static String message() {
        return PackagePeer.secret();
    }
}
```

`PackagePeer.secret()` has package-private access. `Generated.message()` can call it when **defined in the same runtime package** as `PackagePeer`, not just because the two files share the same package name in source code.

### 5.4. File `src/other/WrongPackage.java`

```java
package other;

public class WrongPackage {}
```

This file has completely valid bytes but declares package `other`, different from `sample.dynamic` of the lookup class. Calling `lookup.defineClass` with those bytes will throw `IllegalArgumentException` — this is a package-constraint test, not a corrupt-class-file test.

### 5.5. Compile and Prepare Runtime (Bash Shell)

Run from the directory containing `src`:

```bash
javac --release 17 -d build \
  src/sample/dynamic/LookupDefineClassDemo.java \
  src/sample/dynamic/Generated.java \
  src/other/WrongPackage.java

mkdir -p runtime/sample/dynamic
cp build/sample/dynamic/LookupDefineClassDemo.class runtime/sample/dynamic/
cp build/sample/dynamic/PackagePeer.class runtime/sample/dynamic/

java -cp runtime sample.dynamic.LookupDefineClassDemo \
  build/sample/dynamic/Generated.class \
  build/other/WrongPackage.class
```

Note: the runtime classpath **only has the `runtime` directory**, not `build`. `Generated.class` is passed as **a path to read bytes from**, not placed on the classpath. Do not put `Generated.class` into `runtime` before running: the example wants to control the exact moment the class is defined using `lookup.defineClass`.

If running in **PowerShell on Windows**, replace `mkdir -p`/`cp` with:

```powershell
New-Item -ItemType Directory -Force runtime/sample/dynamic
Copy-Item build/sample/dynamic/LookupDefineClassDemo.class runtime/sample/dynamic/
Copy-Item build/sample/dynamic/PackagePeer.class runtime/sample/dynamic/
java -cp runtime sample.dynamic.LookupDefineClassDemo build/sample/dynamic/Generated.class build/other/WrongPackage.class
```

The three PowerShell lines only replace the runtime preparation/invocation part; the `javac --release 17 -d build ...` command is still used similarly, but written on a single line or continued according to PowerShell syntax.

### 5.6. Verified Stdout

```text
lookup class: LookupDefineClassDemo
PACKAGE mode: true
defined name: sample.dynamic.Generated
same loader: true
same runtime package: true
same module: true
module named: false
same protection domain: true
class defined but not initialized
Generated.<clinit>
message: same-runtime-package
other package: IllegalArgumentException
without PACKAGE: IllegalAccessException
public lookup: IllegalAccessException
duplicate definition: LinkageError
```

### 5.7. Result Analysis

1. `MethodHandles.lookup()` is called inside `LookupDefineClassDemo`, so `lookup.lookupClass()` is this very class. The Lookup has `PACKAGE`.
2. `defineClass(bytes)` succeeds because `Generated` also declares `package sample.dynamic`, and the caller has package permission.
3. The new class has **the same defining loader** and **the same runtime package** as the lookup class. The test output also confirms **the same module** and **the same protection domain**.
4. `module named: false` is because the program runs on the **classpath**, where application classes belong to the corresponding unnamed module.
5. The string `class defined but not initialized` appears **before** `Generated.<clinit>`. When preparing to invoke the static method `message`, the JVM runs the class initializer, then prints the result.
6. `Generated.message()` calls `PackagePeer.secret()` successfully, proving the package-private relationship when defined in the right runtime package.
7. The bytes of `other.WrongPackage` have a different package, resulting in `IllegalArgumentException`.
8. `dropLookupMode(PACKAGE)` causes the lookup to lose class-defining permission; `publicLookup()` also lacks that permission. Both throw `IllegalAccessException` in the example.
9. Calling `defineClass(bytes)` **a second time** with the same binary name and defining loader throws `LinkageError`, rather than overwriting the existing class.

Do not use a **single** `Class.getPackageName().equals(...)` check as proof that two classes share the same runtime package. In the example, the conclusion is based on **same package name + same defining loader + same module** and the official contract of `defineClass`.

## 6. Common Errors of `defineClass`

According to the Java 17 API, the main cases:

| Exception/Error | Phase/source | Example cause |
| --- | --- | --- |
| `IllegalAccessException` | `Lookup` permission check | `Lookup` lacks `PACKAGE` |
| `IllegalArgumentException` | Class type/package validity check | Bytes describe a class in **another package**, or not an accepted class/interface (e.g., `ACC_MODULE`) |
| `ClassFormatError` | Class file structure parsing | Bytes are not a valid classfile structure |
| `VerifyError` | Verification | Bytecode does not satisfy verifier rules |
| `LinkageError` | Linking/class definition | Duplicate binary name in the same defining loader, or other linking error |
| `NullPointerException` | Input data | Passing `null` instead of `byte[]` |
| `SecurityException` | Legacy Security Manager (if present) | Security Manager denies the requested permission under conditions specified by the API |
| `ExceptionInInitializerError` | **Later**, when the class is initialized | Static initializer of the new class throws an error |

Two important nuances:

- `defineClass` does **not** take a checked `ClassNotFoundException` for the new class's own name, because the caller is supplying the bytecode to define it. However, the new class may need dependencies; errors resolving the superclass, interfaces, method signatures, or symbolic references can occur during definition/linking or usage, depending on the circumstances.
- `ClassFormatError`, `VerifyError`, and `LinkageError` are **`Error`s**, not checked `Exception`s. Catching `Exception` is not guaranteed to catch them. Production code should establish handling boundaries/restrict accepting untrusted bytecode, and avoid swallowing Errors and continuing in an unknown state.

### 6.1. When Missing PACKAGE, How Does the Error Differ from Wrong Package?

Two independent causes:

```text
Lookup has PACKAGE?            no  -> IllegalAccessException
         |
        yes
         |
Bytes in same package?         no  -> IllegalArgumentException
         |
        yes
         |
Class file and linking valid?  no  -> ClassFormatError/VerifyError/LinkageError...
         |
        yes
         |
     Class<?> result
```

This is a **diagnostic model**, not an assertion that the JVM must perform all checks in that exact simulated order in every case. The focus is **distinguishing error types** and not trying to "fix" `IllegalAccessException` by altering bytes without understanding lookup modes.

### 6.2. Duplicate Definition Is Not Reloading

If the loader has already defined `sample.dynamic.Generated`, calling `lookup.defineClass(bytes)` again with the same name/loader can throw `LinkageError`. Changing the bytes to a different code version does **not** allow redefining that class in the same loader via `defineClass`.

To run two versions of the same binary name, one technique is using **two different defining class loaders** with specific isolation boundaries, though class identity will then differ; interfaces/serialization/casts/module layers must be managed properly. Mechanisms like Instrumentation class redefinition are also different APIs, not the `Lookup.defineClass` operation.

## 7. Module of the Lookup Class: Unnamed and Named

For the Java 9+ module system, `Class.getModule()` is a direct check of which module a class belongs to.

### 7.1. On the Classpath: Unnamed Module

In the first example, `LookupDefineClassDemo` runs from `runtime` on the classpath. `Generated`, defined via Host's lookup, therefore belongs to **the same unnamed module**. Result:

```text
same module: true
module named: false
```

This does **not** turn all classpath classes into a single global module: an unnamed module is bound to a class loader. With different class loaders, different unnamed modules/class spaces can coexist.

### 7.2. In a Named Module: Do Not Manually Add `module-info` to Bytes

If the lookup class is in named module `m.runtime`, a new class defined from bytes with the same package and loader will reside in **`m.runtime`**. It does **not** become an unnamed-module class just because the bytes were read from a path outside the module path.

To prove this, the second example will have a named module that does not `exports` the package; Host and Generated can still interact via a package-private class because they are in **the same runtime package within the same module**. Publicly exporting to the outside is not a condition for code **internal** to the module to define a class using a lookup with PACKAGE access.

### 7.3. `exports` Differs from `opens`

- `exports p.foo;` or `exports p.foo to m.bar;` primarily grants **access to public types/members at compile/link time** from other modules.
- `opens p.foo;` or `opens p.foo to m.bar;` allows **deep reflection / private lookup** to the authorized target, under the corresponding JPMS conditions.
- If you only need `MethodHandles.lookup()` right inside a package of the module itself, there is no need to open that package externally to use `defineClass` into **that same package/module**.
- If code in module A wants to obtain **a private lookup of a class in module B**, it must satisfy `privateLookupIn` conditions, including the caller lookup's permissions and the target package being appropriately opened. `exports` alone does not guarantee enough to obtain private access.

**Key takeaway:** You do not have a `Module target` parameter in `defineClass`. To define into a target module in a permitted way, you need **a Lookup that actually has a lookup class in the target package/module** and has `PACKAGE` mode. You cannot just write the target package into the bytes and use an arbitrary lookup from another module.

## 8. Complete Example 2 — Defining a Class in a Named Module

We use module `m.runtime`, package `sample.runtime`. Class `ModuleGenerated` is compiled together with the module to get valid class bytes, but `ModuleGenerated.class` is **not** placed in the runtime module directory. The program reads the bytes and defines it via `ModuleDefineDemo`'s lookup.

### 8.1. Directory Structure

```text
src/
  m.runtime/
    module-info.java
    sample/runtime/
      ModuleDefineDemo.java
      ModuleGenerated.java

build/
  m.runtime/
    module-info.class
    sample/runtime/
      ModuleDefineDemo.class
      PackageAccess.class
      ModuleGenerated.class

runtime/
  m.runtime/
    module-info.class
    sample/runtime/
      ModuleDefineDemo.class
      PackageAccess.class
```

### 8.2. File `src/m.runtime/module-info.java`

```java
module m.runtime {
}
```

The module declares neither `exports` nor `opens` because the main running class and the new class belong to the same module. This illustrates that **internal class definition** does not require opening the package externally.

### 8.3. File `src/m.runtime/sample/runtime/ModuleDefineDemo.java`

```java
package sample.runtime;

import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.nio.file.Files;
import java.nio.file.Path;

public class ModuleDefineDemo {
    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup lookup = MethodHandles.lookup();
        byte[] bytes = Files.readAllBytes(Path.of(args[0]));
        Class<?> defined = lookup.defineClass(bytes);
        System.out.println("module named: " + defined.getModule().isNamed());
        System.out.println("same module: "
                + (defined.getModule() == ModuleDefineDemo.class.getModule()));
        System.out.println("same loader: "
                + (defined.getClassLoader() == ModuleDefineDemo.class.getClassLoader()));
        System.out.println("same package: "
                + defined.getPackageName().equals(
                ModuleDefineDemo.class.getPackageName()));
        MethodHandle call = lookup.findStatic(
                defined, "read", MethodType.methodType(String.class));
        System.out.println("value: " + (String) call.invokeExact());
    }
}

class PackageAccess {
    static String message() {
        return "named-module-package-access";
    }
}
```

### 8.4. File `src/m.runtime/sample/runtime/ModuleGenerated.java`

```java
package sample.runtime;

public class ModuleGenerated {
    public static String read() {
        return PackageAccess.message();
    }
}
```

### 8.5. Compile and Run

Run from the directory containing `src` in Bash:

```bash
javac --release 17 \
  -d build \
  --module-source-path src \
  -m m.runtime

mkdir -p runtime/m.runtime/sample/runtime
cp build/m.runtime/module-info.class runtime/m.runtime/
cp build/m.runtime/sample/runtime/ModuleDefineDemo.class runtime/m.runtime/sample/runtime/
cp build/m.runtime/sample/runtime/PackageAccess.class runtime/m.runtime/sample/runtime/

java --module-path runtime \
  --module m.runtime/sample.runtime.ModuleDefineDemo \
  build/m.runtime/sample/runtime/ModuleGenerated.class
```

In Windows PowerShell, use `New-Item -ItemType Directory -Force` and `Copy-Item` equivalents to prepare the files at the right paths; the command `java --module-path runtime --module m.runtime/sample.runtime.ModuleDefineDemo build/m.runtime/sample/runtime/ModuleGenerated.class` can be written on one line.

**Verified stdout:**

```text
module named: true
same module: true
same loader: true
same package: true
value: named-module-package-access
```

The program proves:

1. `ModuleDefineDemo` belongs to named module `m.runtime`, and the lookup is created right inside that class.
2. `lookup.defineClass(bytes)` defines `ModuleGenerated` in **the same named module**, not an unnamed module.
3. `getClassLoader()` is the same; `getPackageName()` is the same.
4. `ModuleGenerated.read()` calls `PackageAccess.message()` even though the method is package-private, because the module/package/loader match.
5. The module does not need to `exports` the package externally just to define a class into its own internal package.

An important point: `ModuleGenerated.class` exists in `build` only to read its bytes; it is **intentionally not copied into `runtime`** to prevent the class from being loaded beforehand and causing a duplicate definition.

## 9. `privateLookupIn`: Can Transfer to the Right Context When the Module Allows

Not every `defineClass` call has to be written in the source of the target package. For example, a framework in module `m.tool` may be **granted deep access** to a package in module `m.target`. In that case, `MethodHandles.privateLookupIn(Anchor.class, callerLookup)` can return a new `Lookup` with **lookup class `Anchor` of the target module** and `PACKAGE` access, and then `defineClass` is called on the new lookup.

Important: this is **changing the Lookup context via a permission-controlled API**, not an arbitrary module-selection parameter of `defineClass`. If the target module does not open the appropriate package, or the caller lookup lacks permission, `privateLookupIn` fails; you cannot bypass it merely by passing bytes.

In the case of crossing to another module, the new lookup may **lose `MODULE` access** while keeping **`PACKAGE`** and other permissions within the allowed scope. These are two separate bits; `defineClass` requires `PACKAGE`, **not directly `MODULE`**.

### 9.1. Complete Example 3 — Two Named Modules with Intentional `opens`

File structure:

```text
src/
  m.tool/
    module-info.java
    tool/CrossModuleDemo.java
  m.target/
    module-info.java
    p/target/Anchor.java
    p/target/GeneratedPlugin.java

build/     # all compiled output
runtime/   # only module-info, tool, Anchor, and PackagePeer
```

#### File `src/m.tool/module-info.java`

```java
module m.tool {
    requires m.target;
}
```

#### File `src/m.target/module-info.java`

```java
module m.target {
    opens p.target to m.tool;
}
```

`opens p.target to m.tool` is an **intentional permission** for module `m.tool`; it does not expose the package to all other modules. At the same time `m.tool` reads `m.target` via `requires`.

#### File `src/m.target/p/target/Anchor.java`

```java
package p.target;

public class Anchor {}

class PackagePeer {
    static String value() {
        return "package-opened";
    }
}
```

#### File `src/m.target/p/target/GeneratedPlugin.java`

```java
package p.target;

public class GeneratedPlugin {
    public static String answer() {
        return PackagePeer.value();
    }
}
```

#### File `src/m.tool/tool/CrossModuleDemo.java`

```java
package tool;

import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.nio.file.Files;
import java.nio.file.Path;

public class CrossModuleDemo {
    public static void main(String[] args) throws Throwable {
        Class<?> anchor = Class.forName("p.target.Anchor");
        MethodHandles.Lookup lookup =
                MethodHandles.privateLookupIn(anchor, MethodHandles.lookup());
        System.out.println("lookup class: " + lookup.lookupClass().getName());
        System.out.println("PACKAGE mode: "
                + ((lookup.lookupModes() & MethodHandles.Lookup.PACKAGE) != 0));
        System.out.println("MODULE mode: "
                + ((lookup.lookupModes() & MethodHandles.Lookup.MODULE) != 0));

        Class<?> generated = lookup.defineClass(Files.readAllBytes(Path.of(args[0])));
        System.out.println("same target module: "
                + (generated.getModule() == anchor.getModule()));
        System.out.println("same loader: "
                + (generated.getClassLoader() == anchor.getClassLoader()));
        System.out.println("caller module different: "
                + (generated.getModule() != CrossModuleDemo.class.getModule()));

        MethodHandle mh = lookup.findStatic(
                generated, "answer", MethodType.methodType(String.class));
        System.out.println("answer: " + (String) mh.invokeExact());
    }
}
```

### 9.2. Compile and Run

From the directory containing `src`, in Bash:

```bash
javac --release 17 \
  -d build \
  --module-source-path src \
  -m m.tool,m.target

mkdir -p runtime/m.tool/tool
mkdir -p runtime/m.target/p/target

cp build/m.tool/module-info.class runtime/m.tool/
cp build/m.tool/tool/CrossModuleDemo.class runtime/m.tool/tool/

cp build/m.target/module-info.class runtime/m.target/
cp build/m.target/p/target/Anchor.class runtime/m.target/p/target/
cp build/m.target/p/target/PackagePeer.class runtime/m.target/p/target/

java --module-path runtime \
  --module m.tool/tool.CrossModuleDemo \
  build/m.target/p/target/GeneratedPlugin.class
```

In PowerShell, replace `mkdir -p` with `New-Item -ItemType Directory -Force` and `cp` with `Copy-Item` as in the previous example. Do not copy `GeneratedPlugin.class` into `runtime` before running.

**Verified stdout:**

```text
lookup class: p.target.Anchor
PACKAGE mode: true
MODULE mode: false
same target module: true
same loader: true
caller module different: true
answer: package-opened
```

### 9.3. Why Is the Output Above Not Contradictory?

The location of the source line calling `defineClass` is in `tool.CrossModuleDemo` of `m.tool`, but the `lookup` object used **no longer** has lookup class `tool.CrossModuleDemo`. `privateLookupIn` created a new lookup with **lookup class `p.target.Anchor`** in `m.target`, with `PACKAGE` access conditionally granted.

Therefore, when `lookup.defineClass(bytes)` runs:

- The target package is `p.target`, because that is the package of `lookup.lookupClass()`.
- The defining loader is the loader of `p.target.Anchor`.
- The module of the new class is **`m.target`**, the same module as `Anchor`, **not** the module of the class holding the lookup variable (`m.tool`).
- `MODULE mode: false` illustrates the permission restriction when a lookup crosses a module boundary; yet `PACKAGE mode: true` is still sufficient for `defineClass`.
- `GeneratedPlugin.answer()` can access `PackagePeer.value()` because the new class is truly in the same runtime package as `Anchor`/`PackagePeer`.

If you remove `opens p.target to m.tool` in `m.target`'s `module-info.java` and rebuild, `privateLookupIn` may throw `IllegalAccessException` because the package is not opened to `m.tool`. There is **no** default fallback to "try public lookup and still define the class"; that is an access denial per JPMS.

### 9.4. Do Not Use `Lookup.in` to Escalate Permissions Illegally

`lookup.in(Other.class)` switches the lookup class but **does not escalate permissions**; it can drop `PACKAGE` when changing packages and drop `MODULE` when changing modules. If you are holding a lookup with only public access in module A, calling `in(Anchor.class)` does not automatically grant permission to define a class in a private package of module B.

`privateLookupIn` does not unconditionally escalate permissions either: the caller must have appropriate permissions (including `PRIVATE` and `MODULE` in the requesting context), and JPMS must allow deep access to the target package. The two-module example succeeds solely thanks to **the explicit `opens` configuration**.

## 10. Comparing `Lookup.defineClass`, `ClassLoader.defineClass`, and `defineHiddenClass`

| Criterion | `Lookup.defineClass(bytes)` | `ClassLoader.defineClass(...)` | `Lookup.defineHiddenClass(...)` |
| --- | --- | --- | --- |
| Task | Defines an **ordinary** class/interface from bytes | Defines a class using a specific loader | Defines a **hidden class** without a normal binary name for external linking |
| Who determines the defining loader? | Loader of the **lookup class** | The `ClassLoader` object performing the define (per API/caller) | Bound to the lookup context, with its own rules |
| Package restriction? | **Must be in the same package** as the lookup class | Per how the loader/module is configured and ClassLoader rules | Hidden classes also have a package constraint with the lookup class |
| Requires PACKAGE mode? | **Yes** | Does not use `Lookup` modes that way | Requires **full privilege access**, not just PACKAGE |
| Returns | `Class<?>` | `Class<?>` | `Lookup` on the hidden class |
| Can the class name be referenced normally? | Yes, per ordinary class rules | Yes, per ordinary class rules | Not like a normal named class |
| Automatically runs `<clinit>` on define? | **No** | Does not run automatically just from defining | The API has an `initialize` parameter deciding initialization |
| Typical use case | Trusted framework adding a class into an existing package/module | Class loader / plugin isolation system with its own loader architecture | Lambdas/runtime code generated as implementation details, when hidden semantics fit |

**Do not confuse:** `ClassLoader.defineClass` is also subject to package/module/protection domain rules, classfile verification, and security. It is not an API "allowed to define any class into any module" just because the author can subclass `ClassLoader`.

### 10.1. When to Use an Ordinary Defined Class?

Use `Lookup.defineClass` when you need a new **ordinary, named class** in the same runtime package/module as the lookup class, usable under normal Java rules. For example, a framework generating accessor/helper bytecode to validly access package-private APIs of its own trusted package.

If the new class is defined with a valid public name, it carries a normal binary name and normal class identity. Ensure **no name collision** with existing classes in the defining loader.

### 10.2. When to Use a Hidden Class?

`Lookup.defineHiddenClass` fits runtime-generated implementations that do not need a normal binary name for other classes to link against directly. It has its own rules for nest membership, lifetime, and initialization; it returns a `Lookup` on the hidden class. Hidden classes do not become ordinary classes discoverable by name via `Class.forName`.

Do not use `defineClass` just because you want to make code "hidden"; ordinary classes and hidden classes have different contracts. Conversely, do not use a hidden class when you need a named public API class for client code to reference like a normal class.

### 10.3. This API Is Not Synonymous with `Class.forName` or Reflection

- `Class.forName(name)` finds/loads a class by name in the class-loading context and may initialize depending on the overload; it **does not** take bytes to define a new class.
- `Class.getDeclaredMethod` or `MethodHandles.lookup().findStatic` looks up members on **an already existing class**.
- `Lookup.defineClass` takes bytecode and creates **a new class** if valid, and then you can use Reflection/MethodHandle to invoke that class's members.

A common mistake is defining a class and then calling `Class.forName` with a different loader, leading to `ClassNotFoundException` or a class identity mismatch. In a framework, it is best to keep and immediately use the `Class<?>` returned by `defineClass`, or pass the exact loader/module context to the next step.

## 11. Do Not Mistake "Same Package" for Same Nest

Two classes in the same runtime package can access **package-private** members, but that does not make them **nestmates** able to access each other's **private members**.

Example:

```java
package sample.dynamic;

class Host {
    private static int secret = 7;
    static int shared = 8;
}
```

Another class defined in the same package/loader/module can access `Host.shared` via package-private access, but **is not automatically allowed to access `Host.secret`**. Private access requires appropriate nest membership/access conditions and other Java rules.

Notes when generating classfiles dynamically:

- Declaring the same `package` does not automatically create `NestHost`/`NestMembers` relationships.
- `Lookup.defineClass` does not automatically attach the new class to the lookup class's nest.
- `defineHiddenClass` has `ClassOption.NESTMATE` in permitted cases; that is a different API/contract and should not be generalized to ordinary `defineClass`.
- If a framework needs private access, prefer official APIs and proper module/access design, rather than assuming a new class in the same package can read every private field.

## 12. Name, Loader, Module, and Package: Comparison Cases

| Scenario | Class bytes | Lookup context | Expected result |
| --- | --- | --- | --- |
| Classpath host in `a.b`; bytes `a.b.Generator`; lookup has PACKAGE | `a.b.Generator` | Unnamed module of Host loader | Defined in the same loader/unnamed module/package |
| Named-module host in `m.core/a.b`; bytes `a.b.Generator` | `a.b.Generator` | Host's lookup in `m.core` | Defined in `m.core`, no need to exports package externally |
| Host in `a.b`; bytes `x.y.Generator` | `x.y.Generator` | Lookup still in `a.b` | `IllegalArgumentException` due to different package |
| Host in `a.b`; bytes `a.b.Generator` | `a.b.Generator` | `publicLookup()` | `IllegalAccessException` due to missing PACKAGE |
| Host in `a.b`; bytes `a.b.Generator` | `a.b.Generator` | `lookup.dropLookupMode(PACKAGE)` | `IllegalAccessException` |
| Bytes with a name already defined in the same loader | `a.b.Generator` | Privileged lookup | `LinkageError` due to duplicate definition |
| Tool module A has private lookup into class Anchor in module B, B opens package with right permission | `p.b.Generator` | Lookup **of Anchor** in B, with PACKAGE | Defined in Anchor's module/loader/package |
| Tool module A only has public lookup into class B | `p.b.Generator` | Lookup lacks PACKAGE | Not allowed to defineClass |
| Invalid/corrupt bytes | Not a valid classfile | Privileged lookup | Possibly `ClassFormatError` or verifier/linker errors |

The table is a guide to typical cases; the specific error result when multiple conditions fail simultaneously depends on which condition is checked first and the JVM processing phase. For intentional tests, isolate **one cause** per test so the message is clear.

## 13. Access Permissions and Security

`Lookup.defineClass` is a high-impact capability: it creates a new class **inside the runtime package of the lookup class**, able to access package-private members per JVM rules. Therefore:

1. **Do not leak a Lookup with PACKAGE access** to untrusted code if creating classes in that package is not permitted.
2. Do not accept bytes from an untrusted source and define them directly without appropriate sandbox/process isolation. A valid classfile can contain static initializers, method bodies, or references that cause side effects when initialized/invoked.
3. Check signatures, origin, version, and policy if the framework receives generated bytecode externally. `ClassFormatError`/`VerifyError` only filter out **invalid** bytecode; a valid class can still perform dangerous behavior.
4. With JPMS, grant `opens` for the needed package/module. Do not open an entire module or use sweeping deep-access JVM flags just to bypass permission design.
5. The `ProtectionDomain` of the new class follows **the lookup class**; do not assume defining from a plugin's bytes means using the protection domain of a separate plugin source. This is even more important in systems with policies or class-loading isolation.
6. Do not rely on the Security Manager as a modern sandbox: the Java Security Manager is deprecated in modern JDKs. Choose an isolation/security architecture suited to the actual runtime environment.

An accurate answer to "how to define a class into someone else's private package?" is: only when you have a **validly granted Lookup** for that package; otherwise, use a public API, an SPI, or a module/package design that intentionally allows extension.

## 14. Class Initialization, Delayed Errors, and Lifecycle

### 14.1. `defineClass` Does Not Run `<clinit>` but Can Trigger Linking Events

Calling `defineClass` can trigger verification, preparation, linking, loading of related types, and corresponding errors. However, this method **does not run the static initializer of the new class**. When the class is first used per initialization rules, the JVM runs `<clinit>` if needed.

If the static block throws an error, the error may appear **after `defineClass` has returned successfully**, for example during the first static method call. Do not test success merely by `Class<?> c = lookup.defineClass(bytes)` and concluding "initialized, all methods are callable."

### 14.2. The New Class Does Not Automatically Create an Instance

The returned `Class<?>` is a metadata/runtime class object; `defineClass` does not call a constructor. If you need to create an object, you must use a valid constructor:

```java
// Illustrative snippet: dynamicClass is a defined Class<?>.
Object instance = dynamicClass.getConstructor().newInstance();
```

This snippet only works when the class has a **public no-arg constructor** and the caller has access permission. Checked/reflection exceptions also need handling. If the constructor does not exist or is not public, use an appropriate declared constructor/Lookup and valid permissions; do not infer that `defineClass` automatically grants permission to call constructors.

### 14.3. Ordinary Classes Are Usually Not Unloaded Individually

An ordinary class typically persists as long as its defining loader and related references remain reachable per runtime rules. You cannot "delete" an individual class and redefine the same binary name into the same loader using `defineClass` alone. To manage unloadability for multiple versions, design class loader lifecycles from the start or look into hidden classes if appropriate for the purpose.

### 14.4. Race When Two Threads Define the Same Class Name

If two threads simultaneously try to call `defineClass` with bytes having the same binary name and the same defining loader, do not assume both will succeed and the JVM will return a single `Class<?>`. Class identity and duplicate definition constraints still apply; one definition may fail because the class was already defined.

Class-generating libraries should use a **naming strategy**, coordination, and cache Class objects by loader/context to avoid races. If choosing to reuse an existing class, build a dedicated API to find and check that class by the exact loader; `defineClass` is not `computeIfAbsent` for class definitions.

## 15. `Lookup.defineClass` Debugging Workflow

When an error occurs in a runtime framework, use the checklist in order:

### Step 1 — Determine the Lookup Context

```java
// Illustrative snippet where the lookup variable is available:
Class<?> lc = lookup.lookupClass();
System.out.println("lookupClass = " + lc.getName());
System.out.println("loader = " + lc.getClassLoader());
System.out.println("module = " + lc.getModule());
System.out.println("package = " + lc.getPackageName());
System.out.println("modes = " + lookup.lookupModes());
System.out.println("has PACKAGE = "
        + ((lookup.lookupModes() & MethodHandles.Lookup.PACKAGE) != 0));
```

Do not log raw bytecode or plugin secrets unnecessarily; logs should provide enough context to diagnose without exposing sensitive data.

### Step 2 — Inspect the Classfile Bytes, Do Not Guess from the Filename

Run a tool such as:

```bash
javap -v -classpath build sample.dynamic.Generated
```

Check the binary name, classfile major version, and constant-pool references. In a classfile, `this_class` determines the class name, not the path where the bytes were loaded from. A file named `Generated.class` could contain a different class; `defineClass` relies on **the actual bytes**.

### Step 3 — Compare Package and Loader

Ensure the package in the bytes **equals** the package of `lookup.lookupClass()`; the result has the same defining loader. If you want to use a different class loader, you need to change the design rather than trying to force a `Lookup` belonging to loader A to define a class into loader B via a nonexistent parameter.

### Step 4 — Check PACKAGE Access

For `IllegalAccessException`, inspect `lookup.lookupModes()`. `publicLookup()` and lookups with PACKAGE dropped are insufficient. If the code used `Lookup.in` to switch class/package, PACKAGE capability may have been reduced. If using `privateLookupIn`, check caller access and `opens` of the target module.

### Step 5 — Check JPMS and the Target Module

Run `lookup.lookupClass().getModule()`. If the new class has the package name of module B while the lookup class is in module A, the code is missing a step to **provide a lookup with the right context**, not just missing a parameter for `defineClass`.

With named modules, check `module-info.java` or the runtime descriptor: which module `requires` which module, which package `exports` for compile access, and which package `opens` for deep lookup. In cases where you only need to define internally within the same module, external `opens` is not a requirement.

### Step 6 — Check Duplicate Name and Lifecycle

If `LinkageError` mentions duplicate definition, identify the binary name + defining loader and see if that class was already defined earlier. Do not retry the exact same bytes into the same loader as a workaround.

### Step 7 — Distinguish Define, Link, Initialize, and Invoke Errors

- Define/verify/link: `ClassFormatError`, `VerifyError`, `LinkageError`.
- Lookup permission/package: `IllegalAccessException` or `IllegalArgumentException`.
- Initialize: `ExceptionInInitializerError` or appropriate initialization error, which can occur after successful definition.
- Method lookup/invoke: `NoSuchMethodException`, `WrongMethodTypeException`, target exceptions, or reflection wrappers depending on the API used.

Do not lump everything together as "class loader failed" and ignore the actual phase.

## 16. When Should This API Be Used in an Application?

**Appropriate cases:**

- A trusted framework creates an ordinary helper class belonging to **the same runtime package/module** to validly access package-private APIs.
- A runtime or tooling generates bytecode from a controlled compiler/generator and places it into a package permitted by the owner.
- A system uses `privateLookupIn` validly **granted `opens`** by the target module and needs to define a new class in the target package/module.

**Inappropriate cases:**

- Creating an isolated plugin sandbox with its own class loader: look at custom `ClassLoader`, module layers, and process isolation.
- Wanting to reload an existing ordinary class with the same name/loader: `defineClass` does not allow overwriting.
- Wanting a hidden implementation class without a normal name: look at `defineHiddenClass` with its own permissions and lifetime.
- Only needing to invoke methods/constructors dynamically on an existing class: use `MethodHandle` or Reflection, no need to create a new class.
- Wanting to bypass JPMS limits or private access of another module: `defineClass` is not a bypass tool.

### 16.1. Safer Bytecode Generation Design

Once you have decided to use `defineClass`:

1. Assign a **unique binary name** per defining loader and lifecycle.
2. Generate bytecode targeting a classfile version supported by the runtime; for Java 17, for example, use `javac --release 17`.
3. Check the package/class name **before** calling `defineClass` and keep the lookup in the right context.
4. Cache the defined `Class<?>` if reuse is needed; do not call define again with bytes for the same name/loader.
5. Consider exception boundaries: Errors from the verifier/linker differ from checked lookup errors.
6. Keep lookups with PACKAGE access within trusted boundaries; do not share them with untrusted plugins.
7. Test on **both classpath and module path** when the framework is allowed to run in both environments.
8. Test the scenario where a module does not `opens` to ensure the system denies deep access as designed.

## 17. Common Misconceptions

**1. "`defineClass` automatically chooses the class loader based on where the bytes file is stored."** False. The defining loader is the loader of **the lookup class**, not the file path.

**2. "As long as the bytes have `package p.q`, a lookup in any package can define it."** False. The package in the bytes must match the lookup class's package; a mismatch throws `IllegalArgumentException`.

**3. "`publicLookup` can define public classes."** False. The `public` modifier does not substitute for `Lookup.PACKAGE`; `publicLookup` lacks this permission.

**4. "`Lookup.in` switching to another class/package automatically increases permissions."** False. `Lookup.in` does not escalate permissions and can drop PACKAGE/MODULE.

**5. "`privateLookupIn` ignores JPMS `opens`."** False. It requires corresponding caller access and module openness conditions. The two-module example succeeds **because of** `opens p.target to m.tool`.

**6. "The new class will go into the module of the calling Java code."** Not necessarily. It goes into the module of **the lookup class** of the Lookup being used, as shown in the CrossModuleDemo example.

**7. "The new class is always in the unnamed module."** False. A named-module lookup defines the class into that named module.

**8. "`defineClass` immediately initializes the new class."** False. It does not run `<clinit>`; initialization may happen upon subsequent active use.

**9. "`defineClass` pre-creates an object instance."** False. It returns `Class<?>`; constructors are called separately when needed.

**10. "Same package name means same runtime package."** False if the defining loader/module differs; you must compare the actual runtime context.

**11. "A new class in the same package can read every private member of Host."** False. Package-private differs from private; nest membership does not appear automatically.

**12. "You can redefine the same name/loader by calling `defineClass` one more time."** False. Duplicate definition leads to `LinkageError`.

**13. "If `defineClass` succeeded, every method is callable."** False. Initialization and lazy resolution can still raise errors later.

**14. "`Lookup.defineHiddenClass` and `defineClass` only differ in method name."** False. Hidden classes have their own naming/discoverability, initialization, access, and lifetime semantics.

**15. "`exports` and `opens` are equivalent."** False. Public type/method accessibility and deep private lookup are two different kinds of permission.

**16. "`ProtectionDomain` of a generated class defaults to where the bytes came from."** False for `Lookup.defineClass`: the domain is based on the lookup class per the API.

**17. "No need to manage class name collisions when multiple threads generate classes."** False. Duplicate names in the same defining loader are still a conflict; coordination and naming are required.

## 18. Self-Check Questions and Answers

**Q1.** `lookup.lookupClass()` is in package `app.core`; the bytes specify `plugin.impl.Proxy`. Can `lookup.defineClass(bytes)` be called successfully?

**Answer:** No under the standard contract, because the packages differ. `defineClass` requires the binary name in the bytes to be in the same package as the lookup class; if the lookup has PACKAGE but the bytes' package is wrong, it throws `IllegalArgumentException`.

**Q2.** `lookup` has `PUBLIC` but not `PACKAGE`; the class bytes belong to the right package. Result?

**Answer:** `IllegalAccessException` because PACKAGE permission is required. Having the right package name does not substitute for the access mode.

**Q3.** Code in module A receives a `Lookup` whose lookup class is in module B with PACKAGE access, then calls `defineClass`. Which module is the new class in?

**Answer:** Module **B**, because the context is determined by **the lookup class** of the Lookup object itself, not the class containing the Java source line calling the method.

**Q4.** Why can `Generated.class` be defined even when it is not on the runtime classpath?

**Answer:** The caller reads the bytes with `Files.readAllBytes` and supplies them to `lookup.defineClass`. The defining loader comes from the lookup class; the path of the bytes does not determine runtime class identity.

**Q5.** `Generated` and `Host` have the same package name but different defining class loaders. Do they automatically access each other's package-private members?

**Answer:** No. Runtime package/access is also bound by classloader/module; having the same name in source is not enough.

**Q6.** Calling `defineClass` on a class whose static initializer prints a line, without invoking any method yet. Has that line been printed?

**Answer:** Not just from `defineClass`, because the API does not run the initializer. A subsequent active use can trigger initialization.

**Q7.** Redefining the same bytes with the same binary name into the same loader will hot-reload it?

**Answer:** No. Defining a duplicate name/loader is rejected by linkage rules, typically with `LinkageError`. A different versioning/class-loader architecture is needed.

**Q8.** When using `privateLookupIn` into another module, the new lookup loses `MODULE` but retains `PACKAGE`. Can `defineClass` be used?

**Answer:** Yes, **if** the new lookup was validly granted and the bytes are in the lookup class's package. `defineClass` requires PACKAGE; it does not separately require MODULE. Losing MODULE does not automatically mean losing PACKAGE.

**Q9.** Why can `m.runtime` in the named-module example still call a package-private method from the generated class without `exports`?

**Answer:** Both classes are in the same runtime package/module and loader. `exports` is for public access use cases **from other modules**; you do not need to export a package externally for internal classes to access each other under Java package rules.

**Q10.** Are `Lookup.in(Anchor.class)` and `privateLookupIn(Anchor.class, callerLookup)` identical in permissions?

**Answer:** No. `Lookup.in` does not escalate permissions and can drop PACKAGE/PRIVATE/MODULE; `privateLookupIn` can create a lookup with private/package access in the target context if caller and JPMS `opens` conditions are satisfied.

**Q11.** A valid classfile contains a method body that accesses sensitive data. Will the class verifier block it because the method does something dangerous?

**Answer:** You cannot rely on the verifier as a business-logic sandbox. The verifier checks bytecode validity and type safety; the class can perform authorized actions when initialized/invoked. Separate security boundaries are needed.

**Q12.** When to choose `ClassLoader.defineClass` instead of `Lookup.defineClass`?

**Answer:** When you actively manage a separate defining loader/lifecycle, such as plugin isolation, and need a custom class-loading architecture. `Lookup.defineClass` is more suitable when you want to add a class into **the exact package/module/loader of an existing lookup class**.

**Q13.** When to choose `defineHiddenClass`?

**Answer:** When you need a dynamically generated implementation class without a normal binary name for clients to link against directly; it must follow full-privilege constraints and hidden-class semantics.

**Q14.** Is a new class in the same package as Host automatically a nestmate of Host?

**Answer:** No. Package membership differs from nest membership; defining an ordinary class with `Lookup.defineClass` does not automatically grant private nest access.

**Q15.** A class is defined successfully, yet calling a static method throws `ExceptionInInitializerError`. Why is this not contradictory?

**Answer:** Define/link and initialize are different phases. `defineClass` does not run `<clinit>`; a subsequent active use initializes the class and can fail.

**Q16.** To properly diagnose the three main constraints, what should be printed?

**Answer:** `lookup.lookupClass().getName()`, `getPackageName()`, `getClassLoader()`, `getModule()`, and `lookup.lookupModes()`; also inspect the class binary name and classfile validity from the bytes.

## 19. Standard References

- **Java SE 17 — `MethodHandles.Lookup.defineClass`:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html — specification on same loader/runtime package/protection domain, PACKAGE access, class initialization, thrown exceptions.
- **Java SE 17 — `MethodHandles.privateLookupIn`:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.html — conditions to obtain a lookup in the target class/package/module.
- **Java SE 17 — `ClassLoader`:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html — defining loader, loading, and defineClass API.
- **Java SE 17 — `Class`:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html — `getName`, `getModule`, `getClassLoader`, reflection.
- **Java SE 17 — `Module`:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Module.html — runtime module identity, exports/opens.
- **Java SE 17 — `MethodHandle`:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandle.html — typed invocation after defining a class.
- **Java Virtual Machine Specification 17 — Chapter 5:** https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html — loading, linking, resolution, and initialization.
- **Java Language Specification 17 — Chapter 12:** https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html — execution and class initialization.
- **Java Virtual Machine Specification 17 — Chapter 4:** https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html — `ClassFile`, constant pool, `this_class`, and classfile versions.

**Conclusion:** `Lookup.defineClass` does not merely "load a byte array." It defines an ordinary class with **the package, defining class loader, module, and protection domain belonging to the lookup class context**, under the control of `Lookup.PACKAGE` permission. Choosing a different context requires **a valid Lookup in that context**, not just changing the package name in the bytes. Distinguishing the define/link/initialize phases, managing duplicate names, and respecting JPMS are the keys to building correct and safe runtime code generation.
# 15.4 Full-privilege Lookup Access and Controlling the initialize Flag

Java allows a framework to create a class directly from bytecode at runtime using `MethodHandles.Lookup`. However, **defining a hidden class** in the caller's module is not an operation that every `Lookup` is permitted to perform: `Lookup.defineHiddenClass(...)` and `defineHiddenClassWithClassData(...)` require **full-privilege access**. At the same time, the `boolean initialize` argument lets you decide whether to **initialize the class immediately upon definition** or defer it to a later active operation.

The two issues must be thought of **independently**:

1. **Who has the right to introduce a new class into this runtime package/module?** This is a matter of identity, access privileges, and `Lookup` limits.
2. **When are the static initializers and static field initializers of the new class run?** This is a matter of the *class initialization* lifecycle, not access privileges.

This lesson belongs to topic **15. Class Definition**, applicable to Java 17+. The content covers `hasFullPrivilegeAccess()`, `lookupModes()`, `PRIVATE`/`MODULE`/`ORIGINAL`, `defineHiddenClass`, `defineHiddenClassWithClassData`, comparison with `defineClass`, the `initialize` flag, `ensureInitialized`, `NESTMATE`/`STRONG` options, module rules, errors, and security. Three Java 17 examples can be compiled and run; each example has verified output.

## 1. The Lookup Model: Identity and Privileges Are Two Different Things

`java.lang.invoke.MethodHandles.Lookup` is an object carrying an **access-checking context**. It contains information about `lookupClass()` (the class on whose behalf we perform lookups) along with *lookup modes*. `Lookup` should not be understood as an “unrestricted Reflection tool” or merely another way to call `Class.forName`.

`MethodHandles.lookup()` is a **caller-sensitive** method: whichever class it is called from, the newly created Lookup carries that class's context. If a utility function located in `FrameworkHelper` calls `MethodHandles.lookup()` itself, it obtains a Lookup for **FrameworkHelper**, and does not automatically gain the privileges of every application class passed in as an argument.

Some access bits in Java 17:

| Mode | Primary Meaning |
| --- | --- |
| `PUBLIC` | Public access according to module rules and visibility |
| `PACKAGE` | Package-private access within a valid runtime package |
| `PROTECTED` | Protected access privileges according to the lookup class's conditions |
| `PRIVATE` | Private access privileges (including nestmates by contract) |
| `MODULE` | Evidence that the lookup carries privileges within the lookup class's module |
| `ORIGINAL` | Original lookup created by the actual caller or bootstrap invoked by the VM; adds certain special privileges |
| `UNCONDITIONAL` | Type of public access privilege independent of normal readability, such as `publicLookup()` |

`lookupModes()` returns a **bitmask**, not a priority order. Therefore, to check for `PRIVATE` or `MODULE`:

```java
MethodHandles.Lookup l = MethodHandles.lookup();
boolean hasPrivate = (l.lookupModes() & MethodHandles.Lookup.PRIVATE) != 0;
boolean hasModule = (l.lookupModes() & MethodHandles.Lookup.MODULE) != 0;
boolean full = l.hasFullPrivilegeAccess();
```

This is an illustrative snippet requiring `import java.lang.invoke.MethodHandles`. In Java 17, **full-privilege access = having both `PRIVATE` and `MODULE`**, not “having `PRIVATE` alone”. Use `hasFullPrivilegeAccess()` instead of checking only a single bit, or using `hasPrivateAccess()` which has been deprecated since Java 14.

### 1.1. Full Privilege Does Not Mean ORIGINAL

`ORIGINAL` distinguishes a lookup that originates directly from the caller class or bootstrap invoked by the VM. It is important for operations sensitive to caller identity or retrieving *class data*; it should not be confused with the `PRIVATE` + `MODULE` pair.

- `MethodHandles.lookup()` in the caller class itself usually has `ORIGINAL` **and** full privilege.
- `MethodHandles.privateLookupIn(Target.class, callerLookup)` within the **same module** can create a Lookup with full privilege on Target but **without `ORIGINAL`**.
- `defineHiddenClass(...)` returns a new Lookup on the hidden class, having full privilege **and `ORIGINAL`** according to the specification.
- Do not conclude that having `ORIGINAL` alone allows calling `defineHiddenClass`; the API requires **full privilege**. Conversely, an API like `MethodHandles.classData` requires **`ORIGINAL`** on the passed-in Lookup.

This is why `hasFullPrivilegeAccess()` and the `ORIGINAL` bit check are not interchangeable.

### 1.2. How a Lookup Loses or Changes Privileges

| Way to Create/Transfer Lookup | Expected Access Privileges |
| --- | --- |
| `MethodHandles.lookup()` | Full privilege corresponding to the **actual caller** |
| `MethodHandles.publicLookup()` | Minimal public privileges, **not** full privilege |
| `lookup.dropLookupMode(Lookup.PRIVATE)` | Drops PRIVATE, therefore **not** full privilege |
| `lookup.in(AnotherClass.class)` | Transfers lookup class; privileges **cannot be elevated**, and may lose ORIGINAL/PRIVATE/PACKAGE/MODULE depending on the relationship |
| `MethodHandles.privateLookupIn(T, lookup)` same module | If conditions are valid, grants full privilege on T, usually without ORIGINAL |
| `privateLookupIn` across two different modules | May have PRIVATE on T if the package is validly opened, but loses MODULE so **not** full privilege |

**Special warning for plugins:** `privateLookupIn` does not “elevate every lookup from outside the module to full privilege”. For a target in another module, even if the package is `opens` to the caller's module, the resulting Lookup **loses `MODULE`**. It can access private members according to granted privileges, but does not satisfy the `defineHiddenClass` condition on the target. To define a hidden class in a plugin's module, design a **helper entry point inside that module itself** so a trusted class of the plugin creates/provides an appropriate Lookup; do not pass arbitrary privileges to untrusted callers.

## 2. Three Class-Definition APIs and Privilege Requirements

| API | Lookup Requirement | Result | Has `initialize` Parameter? |
| --- | --- | --- | --- |
| `lookup.defineClass(bytes)` | Requires `PACKAGE` | `Class<?>` of a **normally named class** | **No**; this method does not run `<clinit>` |
| `lookup.defineHiddenClass(bytes, initialize, options...)` | Requires **full privilege (`PRIVATE` + `MODULE`)** | `Lookup` on the new **hidden class** | **Yes** |
| `lookup.defineHiddenClassWithClassData(bytes, classData, initialize, options...)` | Requires **full privilege** | `Lookup` on a hidden class with attached class data | **Yes** |

All of the above methods require valid class file bytecode, and **the class in the bytes must be in the same runtime package** as the appropriate lookup class. For a hidden class, the runtime package/module/protection domain is established based on the lookup class by the API definition. You cannot use `publicLookup()` to inject arbitrary classes into `java.base` or an unrelated package.

### 2.1. Why Does defineClass Only Need PACKAGE?

`defineClass(byte[])` creates a normally named class in the same runtime package and class loader as the lookup class, in a manner similar to `ClassLoader.defineClass`. The `PACKAGE` privilege proves that the Lookup was granted to a caller with the proper relationship to that package. A Lookup that no longer has PRIVATE but still has PACKAGE **can still call `defineClass`**, as shown in the example in section 5.

Conversely, `defineHiddenClass` places the new class into the same **module** as the lookup class, returning a Lookup with very strong privileges on that class. The JDK requires the caller to have both PRIVATE and MODULE, and does not allow relying solely on PACKAGE.

### 2.2. How Is a Hidden Class Different from a Regular Class?

A hidden class is created by the JVM without going through `ClassLoader.defineClass` in the normal naming way. When inspected:

- `hiddenClass.isHidden()` is `true`.
- `hiddenClass.getName()` has a special suffix (usually containing `/` and a VM identifier), and **is not a stable binary class name**. Do not save this result to call `Class.forName` again.
- `Class.forName`, `ClassLoader.loadClass`, and `Lookup.findClass(String)` cannot be used to find a hidden class by its generated name.
- Each valid `defineHiddenClass` call from the same bytes creates **a separate `Class<?>`**; their static state and initialization history are not a shared singleton per byte array.
- A hidden class is not permitted to be referenced from another class's constant pool as a supertype or field descriptor with a normal binary name.
- By default, a hidden class can be unloaded independently of the lifetime of the class loader marked as its defining loader, if no references remain that need to keep it alive. `ClassOption.STRONG` changes this policy.

The file name `HiddenPayload.class` is only the **source of bytes** in the example; the class name `HiddenPayload` in the original source does not mean the JVM will use that name as a named class after creating the hidden variant.

## 3. Two Phases Not to Be Confused: define/link and initialize

Java distinguishes between **loading/derivation**, **linking**, and **initialization**. A class file may already be loaded/verified/linked while the body of `static { ... }` and static field initializers have not yet run.

With `Lookup.defineHiddenClass(bytes, initialize, ...)`:

- `initialize = true`: The JVM defines, links, **and initializes** the hidden class before the method returns successfully. If `<clinit>` has side effects, those side effects can occur **right inside the defineHiddenClass call**.
- `initialize = false`: The JVM defines and links, but **does not actively initialize the class at that time**. Initialization may take place on a subsequent *active use*.
- There is no `initialize=false` API for `Lookup.defineClass(byte[])`; that API **does not run the class initializer**.
- Having a created `Class<?>` or `Lookup` does not mean the class initializer has run.

**`false` defers initialization, it does not permanently disable `<clinit>`.** When calling a static method, accessing a non-compile-time-constant static field under active-use rules, creating an instance, or calling `Lookup.ensureInitialized(cls)`, the class can be initialized.

Diagram:

```text
class bytes (valid format and package)
       |
       v
defineHiddenClass(bytes, false)
       |
       +-- creates hidden Class, linked
       +-- returns Lookup (full privilege + original)
       +-- has not actively run <clinit>
       |
       v  later:
ensureInitialized(hiddenClass)
or a valid active use
       |
       v
<clinit> is executed once for that Class
       |
       v
static method/field/instance continues operating
```

### 3.1. Which Operations Should Not Initialize by Default?

Some operations that only inspect or link **do not necessarily** trigger initialization, such as obtaining `Class<?>`, reading `isHidden()`, `getName()`, `getDeclaredMethods()`, or looking up a MethodHandle with `Lookup.findStatic(...)`. When **invoking** a method handle pointing to an uninitialized static method, the JVM must ensure initialization according to active-use rules.

This point is very useful when a framework wants to:

1. read metadata, check types, and prepare call sites;
2. wire up adapters or registries without causing premature side effects;
3. initialize only after all validation steps have succeeded.

However, a metadata step might indirectly trigger another class; and calling a helper with static logic during validation could cause **the hidden class itself** to initialize. Design must rely on actual active-use rules, not on guessing just because the keyword “lookup” is present.

### 3.2. ensureInitialized Is Clearer Than a Side-Effect-Triggering Trick

`Lookup.ensureInitialized(Class<?>)` ensures that the class is initialized if it has not been yet, subject to the Lookup's **accessClass** privilege constraints for the target class. It returns the initialized `Class<?>`.

```java
Class<?> c = hiddenLookup.lookupClass();
hiddenLookup.ensureInitialized(c);
```

This is an illustrative snippet, not a standalone program. Using the `hiddenLookup` returned by `defineHiddenClass` is the natural way to have appropriate access rights to the hidden class. The API may throw `IllegalAccessException` if the target is not accessible; if initialization fails, you may see `ExceptionInInitializerError` or related linking/initialization errors.

There is **no** public `Class.isInitialized()` in the standard Java API to immediately read “whether it is initialized”. Do not use a static method call as a “check” and forget that it can itself trigger initialization.

## 4. Complete Java 17+ Example: Full Privilege, Lazy/Eager Hidden Class, and NESTMATE

The example consists of **two files in the same package**. To create the hidden class, we compile `HiddenPayload.java` into a valid class file, and then `HiddenClassInitDemo` **reads the bytes** via a resource stream. Reading `.class` via a stream does not execute the payload's `<clinit>`. No external bytecode library is used.

Create the directory `runtime/lesson/` and the file **`runtime/lesson/HiddenPayload.java`**:

```java
package runtime.lesson;

import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;

final class HiddenPayload {
    static {
        System.out.println("Payload.<clinit>");
    }

    static int answer() {
        return 42;
    }

    static String hostSecret() throws Throwable {
        MethodHandle m = MethodHandles.lookup().findStatic(
                HiddenClassInitDemo.class,
                "secret",
                MethodType.methodType(String.class));
        return (String) m.invokeExact();
    }
}
```

This file **has no public class** and is compiled together with the host file. `hostSecret()` uses a MethodHandle to test the privilege to call the host's `private static` method at runtime; when it is defined as a hidden **nestmate**, private access within the same nest can be used. We do not use `HiddenPayload` source code to directly call `HiddenClassInitDemo.secret()` because the compiler of the two original classes does not treat them as nestmates.

File **`runtime/lesson/HiddenClassInitDemo.java`**:

```java
package runtime.lesson;

import java.io.InputStream;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;

public class HiddenClassInitDemo {
    private static String secret() {
        return "host-secret";
    }

    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup host = MethodHandles.lookup();
        byte[] bytes;
        try (InputStream in = HiddenClassInitDemo.class
                .getResourceAsStream("HiddenPayload.class")) {
            if (in == null) {
                throw new IllegalStateException("HiddenPayload.class not found");
            }
            bytes = in.readAllBytes();
        }

        System.out.println("hostFull=" + host.hasFullPrivilegeAccess());

        MethodHandles.Lookup lazy = host.defineHiddenClass(
                bytes, false, MethodHandles.Lookup.ClassOption.NESTMATE);
        Class<?> cls = lazy.lookupClass();

        System.out.println("lazyHidden=" + cls.isHidden());
        System.out.println("returnedFull=" + lazy.hasFullPrivilegeAccess());
        System.out.println("nestmate="
                + (cls.getNestHost() == HiddenClassInitDemo.class));
        System.out.println("after define(false)");

        MethodHandle answer = lazy.findStatic(
                cls, "answer", MethodType.methodType(int.class));
        System.out.println("after findStatic");

        lazy.ensureInitialized(cls);
        System.out.println("answer=" + (int) answer.invokeExact());

        MethodHandle reveal = lazy.findStatic(
                cls, "hostSecret", MethodType.methodType(String.class));
        System.out.println("secret=" + (String) reveal.invokeExact());

        MethodHandles.Lookup eager = host.defineHiddenClass(bytes, true);
        System.out.println("after define(true)");
        System.out.println("eagerHidden=" + eager.lookupClass().isHidden());

        MethodHandles.Lookup restricted =
                host.dropLookupMode(MethodHandles.Lookup.PRIVATE);
        System.out.println("restrictedFull="
                + restricted.hasFullPrivilegeAccess());
        try {
            restricted.defineHiddenClass(bytes, false);
        } catch (IllegalAccessException e) {
            System.out.println("restricted=" + e.getClass().getSimpleName());
        }
    }
}
```

Compile the two files from the parent directory containing `runtime/lesson/` and run with Java 17+:

```bash
javac --release 17 -d out runtime/lesson/HiddenPayload.java runtime/lesson/HiddenClassInitDemo.java
java -cp out runtime.lesson.HiddenClassInitDemo
```

Verified `stdout`:

```text
hostFull=true
lazyHidden=true
returnedFull=true
nestmate=true
after define(false)
after findStatic
Payload.<clinit>
answer=42
secret=host-secret
Payload.<clinit>
after define(true)
eagerHidden=true
restrictedFull=false
restricted=IllegalAccessException
```

### 4.1. Exact Analysis of the Output Order

1. `hostFull=true`: `MethodHandles.lookup()` inside `HiddenClassInitDemo` has full privilege for the caller itself.
2. `lazyHidden=true`: the bytes have been defined as a new hidden class, not a normally named class.
3. `returnedFull=true`: the Lookup from `defineHiddenClass` has full privilege on the created hidden class.
4. `nestmate=true`: the `NESTMATE` flag attaches the hidden class to the nest host of the lookup class.
5. After `after define(false)` and `after findStatic`, there is **no** `Payload.<clinit>` line yet: merely defining and finding a MethodHandle does not initialize the payload.
6. `lazy.ensureInitialized(cls)` actively runs `<clinit>` of the first hidden class. Afterwards, calling `answer()` returns `42` without running the initializer a second time.
7. `hostSecret()` can use `MethodHandles.lookup()` from inside the `NESTMATE`-attached hidden class to find the host's private method; the `host-secret` result proves nestmate privileges are applied.
8. The `host.defineHiddenClass(bytes, true)` call creates a **new hidden class** from the same bytes. Because initialize is true, the **second** `Payload.<clinit>` line appears before `after define(true)`. This is not re-initializing the first class.
9. After `dropLookupMode(PRIVATE)`, `restrictedFull=false` and `defineHiddenClass` is rejected with `IllegalAccessException`.

**Do not copy a hidden class name string and then use `Class.forName` to look it up again.** Keep the appropriate `Class<?>`, `Lookup`, or `MethodHandle` reference for the lifetime the framework needs; at the same time, control caches so hidden classes are not kept alive unintentionally forever.

### 4.2. Why Is NESTMATE Important?

`ClassOption.NESTMATE` adds the hidden class to the lookup class's nest, enabling the same private access rules among nestmates. It is **not required** when only creating a hidden class with its own public/package-private methods. If `NESTMATE` is omitted in the program above, the hidden class normally has itself as its nest host; the call to find private `HiddenClassInitDemo.secret` from inside `HiddenPayload.hostSecret` no longer satisfies the private nestmate condition.

**Do not confuse `NESTMATE` with `STRONG`**: one flag governs nest/access relationships; the other governs lifetime/unloading with the defining loader. They can be combined when needed, and both are `ClassOption` values passed via varargs `options`.

## 5. Complete Example: defineClass Only Needs PACKAGE and Does Not Run <clinit>

To distinguish **PACKAGE** privilege from full privilege, create two other files (still in package `runtime.lesson`). This example intentionally **drops PRIVATE**, then uses `defineClass` to define a **named class**. Because the class has a normal name, defining **the same name a second time** in the same loader will cause an error.

File **`runtime/lesson/NamedPayload.java`**:

```java
package runtime.lesson;

final class NamedPayload {
    static {
        System.out.println("NamedPayload.<clinit>");
    }

    static String ping() {
        return "named";
    }
}
```

File **`runtime/lesson/NamedClassDemo.java`**:

```java
package runtime.lesson;

import java.io.InputStream;
import java.lang.invoke.MethodHandles;

public class NamedClassDemo {
    public static void main(String[] args) throws Exception {
        MethodHandles.Lookup packageLookup = MethodHandles.lookup()
                .dropLookupMode(MethodHandles.Lookup.PRIVATE);

        byte[] bytes;
        try (InputStream in = NamedClassDemo.class
                .getResourceAsStream("NamedPayload.class")) {
            if (in == null) {
                throw new IllegalStateException("NamedPayload.class not found");
            }
            bytes = in.readAllBytes();
        }

        System.out.println("packageAccess="
                + ((packageLookup.lookupModes()
                  & MethodHandles.Lookup.PACKAGE) != 0));
        System.out.println("full=" + packageLookup.hasFullPrivilegeAccess());

        Class<?> named = packageLookup.defineClass(bytes);
        System.out.println("namedHidden=" + named.isHidden());
        System.out.println("after defineClass");

        packageLookup.ensureInitialized(named);
        System.out.println("after ensureInitialized");

        try {
            packageLookup.defineClass(bytes);
        } catch (LinkageError e) {
            System.out.println("duplicate=" + e.getClass().getSimpleName());
        }
    }
}
```

Compile and run in a fresh JVM/process:

```bash
javac --release 17 -d out runtime/lesson/NamedPayload.java runtime/lesson/NamedClassDemo.java
java -cp out runtime.lesson.NamedClassDemo
```

`stdout`:

```text
packageAccess=true
full=false
namedHidden=false
after defineClass
NamedPayload.<clinit>
after ensureInitialized
duplicate=LinkageError
```

**Explanation:**

- `dropLookupMode(PRIVATE)` removes full privilege but keeps `PACKAGE` in this example. That is sufficient for `defineClass`; it is not sufficient for `defineHiddenClass`.
- `namedHidden=false` because this is a regular class with a binary name in the runtime package.
- `after defineClass` appears **before** `NamedPayload.<clinit>`: `defineClass` does not initialize.
- `ensureInitialized(named)` actively runs the static initializer once.
- Calling `defineClass` with bytes bearing the **same binary name** again on the same loader causes `LinkageError`; conversely, hidden classes have unique JVM-generated suffix names, which is why the example in section 4 can define two hidden classes from the same bytes.

**Test condition:** the `NamedPayload.class` file must exist for the host to read the bytes, but there must not be an execution path that has already actively loaded/defined the same name in the process before `defineClass` runs. Therefore, run `NamedClassDemo` with the `java` command above in a separate process, without calling `NamedPayload.ping()` beforehand.

## 6. defineHiddenClassWithClassData Also Requires Full Privilege and the Same initialize Flag

`Lookup.defineHiddenClassWithClassData(bytes, classData, initialize, options...)` is the variant that defines a hidden class **along with a class data object**. It has the same full-privilege requirement and `initialize` flag as `defineHiddenClass`, but the runtime associates the provided object with the hidden class via the class data mechanism. The API has existed since **Java 16**.

Class data is suitable when a runtime linker wants to provide metadata, a `MethodHandle`, configuration, or a list of values to a hidden class without creating a public static field or placing data into the constant pool as literals. The `classData` object can be a single object or a `List`. Use immutable data whenever possible; a mutable object modified concurrently can make behavior hard to predict.

To read class data, the JDK provides:

- `MethodHandles.classData(lookup, "_", T.class)` to retrieve the entire object.
- `MethodHandles.classDataAt(lookup, "_", T.class, index)` to retrieve an element if class data is a `List`.

**An easily overlooked limitation:** reading class data requires a Lookup with the `ORIGINAL` bit, not just PRIVATE/MODULE. Both `classData` and `classDataAt` can also **actively initialize the lookup class if it has not been initialized yet**; thus the `initialize=false` flag does not mean the class-data reading API will never run `<clinit>`.

### 6.1. Java 17+ Example: Accessing Class Data and Initialization Timing

File **`runtime/lesson/DataCarrier.java`**:

```java
package runtime.lesson;

import java.lang.invoke.MethodHandles;

final class DataCarrier {
    static {
        System.out.println("DataCarrier.<clinit>");
    }

    static String read() throws IllegalAccessException {
        return MethodHandles.classData(
                MethodHandles.lookup(), "_", String.class);
    }
}
```

File **`runtime/lesson/HiddenClassDataDemo.java`**:

```java
package runtime.lesson;

import java.io.InputStream;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;

public class HiddenClassDataDemo {
    public static void main(String[] args) throws Throwable {
        byte[] bytes;
        try (InputStream in = HiddenClassDataDemo.class
                .getResourceAsStream("DataCarrier.class")) {
            if (in == null) {
                throw new IllegalStateException("DataCarrier.class not found");
            }
            bytes = in.readAllBytes();
        }

        MethodHandles.Lookup newLookup = MethodHandles.lookup()
                .defineHiddenClassWithClassData(
                        bytes, "config-v1", false);

        System.out.println("full=" + newLookup.hasFullPrivilegeAccess());
        System.out.println("original="
                + ((newLookup.lookupModes()
                  & MethodHandles.Lookup.ORIGINAL) != 0));
        System.out.println("after defineWithClassData(false)");

        MethodHandle read = newLookup.findStatic(newLookup.lookupClass(),
                "read", MethodType.methodType(String.class));
        System.out.println("after findStatic");

        System.out.println("data="
                + MethodHandles.classData(newLookup, "_", String.class));
        System.out.println("viaMethod=" + (String) read.invokeExact());
    }
}
```

```bash
javac --release 17 -d out runtime/lesson/DataCarrier.java runtime/lesson/HiddenClassDataDemo.java
java -cp out runtime.lesson.HiddenClassDataDemo
```

`stdout`:

```text
full=true
original=true
after defineWithClassData(false)
after findStatic
DataCarrier.<clinit>
data=config-v1
viaMethod=config-v1
```

The `DataCarrier.<clinit>` line runs when the host calls `MethodHandles.classData(newLookup,"_",String.class)`, even though the hidden class was previously defined with `initialize=false`. Calling `read.invokeExact()` afterwards **does not re-run the initializer** and still returns the right class data.

**Do not confuse the factory's initialize flag with immutability of class data**: `initialize=false` does not “freeze” the data object or isolate it from other threads. If passing a `List`, consider `List.of(...)` or an immutable snapshot; do not use a mutable array shared with untrusted code without protection.

## 7. Relationship with Modules and privateLookupIn

In the JPMS system, the notion of “same package” is not enough if the **runtime module** or loader differs. The specification requirement of `defineHiddenClass` is that the bytes must define a class whose **package matches the lookup class**; the hidden class will reside in the same runtime package/module/protection domain as the lookup class without automatically entering another module.

### 7.1. Transferring Lookup to Another Class in the Same Module

When `hostLookup = MethodHandles.lookup()` has full privilege, `MethodHandles.privateLookupIn(Target.class, hostLookup)` (if valid) can grant a Lookup with full privilege on the target in the same module. From there, you can define a hidden class whose bytes match Target's package.

```java
MethodHandles.Lookup onTarget =
        MethodHandles.privateLookupIn(Target.class, MethodHandles.lookup());

if (!onTarget.hasFullPrivilegeAccess()) {
    throw new IllegalStateException("Need full privilege");
}

MethodHandles.Lookup hidden =
        onTarget.defineHiddenClass(classBytes, false);
```

This snippet is an **illustrative pattern**, assuming `Target` and `classBytes` are validly supplied; it is not a standalone program. Do not use it to bypass module boundaries by default.

### 7.2. Cross-Module Deep Reflection Does Not Automatically Equal Define Privilege

Suppose framework code in module `framework.core` tries to access a type belonging to `plugin.module`:

- The framework must be able to read the target module; the target module must `opens` the appropriate package to the framework module for `privateLookupIn` to be valid.
- The resulting Lookup in a **different** module may carry `PRIVATE` but **loses `MODULE`**, because it still records `previousLookupClass()` to check cross-module access.
- `hasFullPrivilegeAccess()` is then `false`, and `defineHiddenClass` will reject with `IllegalAccessException`.
- Using `--add-opens` or editing `module-info.java` may allow **deep reflection**, but does not make a Lookup “full privilege” in the target module.

This is an intentional security boundary. The proper architectural direction is: the module/plugin owning the package provides **a trusted factory** that performs class definition inside that module itself and returns a minimal interface/handle to the consuming software, rather than handing a raw full-privilege Lookup to a third party.

### 7.3. Do Not Rely on Module and Package Names as Strings

If the bytes define a class with a different package from the lookup class, `defineHiddenClass` may throw `IllegalArgumentException`. If the bytes are corrupted or not a valid class file, you may see `ClassFormatError` or `VerifyError`. If the class file version is newer than the JVM supports, you may see `UnsupportedClassVersionError`. Check the **actual Class<?>/Module/ClassLoader**, not just string-based binary name comparisons, before feeding a bytecode generator into the pipeline.

## 8. initialize=true Is Not a “Side-Effect-Free” Step

Class initialization can run:

- Static field initializers (except compile-time constants under the relevant rules).
- The `static { ... }` body.
- Helpers called from static initializers.
- Side effects such as I/O, thread creation, registry registration, loading configuration, or throwing exceptions.

If a framework is creating a class from external data, `initialize=true` means it can run **the newly created class's code right inside the define call**. It must not be treated as an operation that merely “registers metadata”.

### 8.1. When to Choose initialize=true?

Choose true when:

- Class bytes and `<clinit>` code are trusted and validated.
- Static state needs to be ready immediately after the define method returns.
- Initialization errors can be handled at class-creation time.
- Initialization order among multiple dependent classes has been designed.

Choose false when:

- You want to separate the define/link/metadata-validation step from executing the initializer.
- You want to create multiple hidden classes and then decide which class to use.
- You want to defer initialization cost and side effects until the target actually needs to be called.
- There is a clear lifecycle to call `ensureInitialized` or rely on a subsequent valid active use.

**However**, initialize=false **is not a sandbox**. Once a caller invokes a static method or an API that triggers initialization, the `<clinit>` code still runs with that class's normal privileges. If the bytes are untrusted, you must evaluate/isolate the byte source according to security policy before defining, rather than merely passing false.

### 8.2. Side Effects and Thread Contention

The JVM coordinates initialization of **each Class object** according to JLS/JVMS rules. If two threads simultaneously active-use a hidden class, it does not mean both are allowed to run `<clinit>` in parallel for the same Class: initialization is coordinated. But if you call `defineHiddenClass` **twice** with the same bytes, you get two independent Class objects; **each class** can have its own `<clinit>`.

This is very important for frameworks:

- Do not put a global business registration in a static initializer and assume it “runs only once per bytes”.
- If two hidden classes with different identities are created, registration may be duplicated.
- If `<clinit>` has side effects outside the JVM, pay attention to idempotency and ownership, even when only a single thread is operating.
- Do not use `initialize=false` as a way to avoid deadlocks if the program later has a class initialization cycle; analyze dependencies and locks at active-use sites.

## 9. ClassOption.NESTMATE, STRONG, and Lifetime

Two `Lookup.ClassOption` values relate to hidden class definition:

| Flag | Effect | What It Does Not Automatically Provide |
| --- | --- | --- |
| `NESTMATE` | Attaches the hidden class to the lookup class's nest; allows accessing private members of nestmates as specified | Does not turn the class into a public API; does not automatically manage class initialization |
| `STRONG` | Creates an unloading relationship with the defining class loader like a normally named class | Does not force immediate initialization; does not elevate Lookup privileges; does not guarantee being memory-leak-free |

By default **without STRONG**, a hidden class can be unloaded even while the defining loader remains reachable, if no references remain that keep the hidden class alive. If `STRONG` is added, the hidden class usually only unloads together when the defining loader is no longer reachable; in applications that generate thousands of dynamic classes, keeping too many strong hidden classes can increase metaspace pressure.

A method handle, `Class<?>`, Lookup, or object instantiated from the hidden class can keep the class reachable. Global caches holding these objects can keep the class loader and class alive longer than expected. Use lifecycle-bound caches, weak references, or `ClassValue` where appropriate, and verify actual unloading conditions. **Do not rely on GC order/timing to guarantee logic.**

### 9.1. Private Access Among Nestmates Does Not Automatically Permit Everything

In the example in section 4, the hidden `HiddenPayload` is defined with NESTMATE and can use its own Lookup to find `HiddenClassInitDemo`'s private method. But a regular class in another package, or untrusted plugin code, cannot be treated as a nestmate just because it holds a similar name string.

NESTMATE is a decision to **elevate access capabilities within the nest**, so it should only be applied to trusted bytes. If only a public API is desired, you can omit NESTMATE and return a handle/instance with a restricted interface, without sharing a full Lookup.

## 10. Security: Lookup Is a Capability That Must Be Controlled

Handing a full-privilege `Lookup` to untrusted code is like granting the ability to operate on private members accessible to that Lookup and even define hidden classes in the corresponding module. A framework should not:

- Store an intact `MethodHandles.lookup()` in a public registry that any plugin can retrieve.
- Pass a full-privilege Lookup from a trusted bootstrap directly into third-party callbacks when only invoking a selected method is needed.
- Call `defineHiddenClass(userSuppliedBytes, true)` on unverified bytes hoping the JVM package check is enough to act as a sandbox.
- Use `setAccessible(true)` or `--add-opens` as a “solution” for lacking full privilege while bypassing module policy.
- Allow arbitrary code to provide static initialization with side effects in the same module environment as trusted core components.

**Principle of least privilege:** if a framework user only needs to run an implementation, return a specific `MethodHandle`, a functional interface, or a restricted service object. Do not also grant the right to create arbitrary new methods/classes. If a Lookup must be handed over, consider `dropLookupMode` for tasks that only look up package/public members; note clearly that **once a mode is dropped, privileges cannot be restored from that downgraded Lookup**.

### 10.1. Controlling Bytecode Sources and Errors

Before defining a class:

1. Verify the source of bytes (trusted code generator, checksum/signature, policy allowlist).
2. Verify the JVM-supported class file version and expected runtime package.
3. Know clearly which class/module the Lookup originates from, and whether it has full privilege or only PACKAGE.
4. Check the `initialize` flag and any static initializers that may run.
5. Choose `NESTMATE`/`STRONG` based on proven need, not indiscriminately.
6. Categorize errors: `IllegalAccessException`, `IllegalArgumentException`, `ClassFormatError`, `VerifyError`, `UnsupportedClassVersionError`, and other `LinkageError`s.
7. Manage lifecycle, caches, resources, and cleanup if initialization partially succeeds and then fails.

Generally, completely verifying class bytes before execution is a hard problem; a valid class can still execute undesirable behavior. Do not treat the JVM verifier or package checks as a standalone sandbox policy.

## 11. Common Errors and How to Analyze Them

| Error/Symptom | Common Cause | How to Handle |
| --- | --- | --- |
| `IllegalAccessException` at `defineHiddenClass` | Lookup does not have both PRIVATE and MODULE | Call `hasFullPrivilegeAccess()`; only obtain a trusted Lookup in the right module |
| `defineClass` succeeds but `defineHiddenClass` fails | Lookup has PACKAGE but not full privilege | Distinguish the two privilege levels; do not infer hidden privilege from named privilege |
| `privateLookupIn` across another module still cannot define a hidden class | MODULE is dropped during cross-module teleport | Have a trusted factory inside the target module perform the define |
| `ClassFormatError` | Bytes are not a valid class file | Check the generator and class file structure |
| `UnsupportedClassVersionError` | Class file major/minor version is incompatible with the JVM | Compile with the right `--release 17` or use a supporting JVM |
| `IllegalArgumentException` | Package in bytes differs from lookup class, or invalid input | Verify internal class name/runtime package before defining |
| `VerifyError` / `LinkageError` | Bytecode is invalid with respect to the type system or linking error | Use verifier, bytecode QA, and check dependencies |
| No `<clinit>` seen after `initialize=false` | Class is only defined/linked, not yet active-used | Call `ensureInitialized` when ready for side effects |
| `<clinit>` runs inside `defineHiddenClass(true)` | This is the exact meaning of the true flag | Use false if you want to separate timing, and do not forget active use afterwards |
| `<clinit>` runs when reading class data | `MethodHandles.classData` actively initializes the lookup class | Account for initialization triggers in the class-data design |
| Hidden class cannot be found with `Class.forName` | Hidden class has no normal binary name | Keep the returned `Class<?>` or `MethodHandle` |
| `<clinit>` seen running twice from the same bytes | Two separate hidden Class objects were defined | Do not confuse per-class initialization with per-source-file |
| `ExceptionInInitializerError` at active-use site | Static initializer throws an exception when running | Handle the root cause; do not assume the class can safely retry initialization |
| `NoClassDefFoundError` on subsequent attempts | The class previously failed initialization and is in an erroneous state | Fix the source error, use a new class/class loader under a valid lifecycle |
| Class is kept alive too long | `STRONG`, `Class`, Lookup, or MH cache holds references | Build lifecycle-aware caches, test metaspace/class unloading |
| `MethodHandles.lookup()` from a helper has the wrong privileges | Lookup is created for the **helper caller**, not the target class | Place the trusted factory in the right module/class or use valid `privateLookupIn` |

### 11.1. Separating Three Error Categories by Phase

**Definition/linking phase:** invalid class bytes, wrong package, missing lookup privilege, unable to link dependencies. Errors usually arise right inside the `defineHiddenClass` or `defineClass` call.

**Initialization phase:** static initializer or static field initializer runs and may throw an exception; with `initialize=true` this error usually surfaces at the define method. With `false`, the error may only appear when calling `ensureInitialized`, a static method, or another active use.

**Execution phase:** code inside the target method throws an exception, even after the class has initialized. Do not equate a method body error with a class initialization error. A MethodHandle when invoked can also throw `WrongMethodTypeException` due to a call-site signature mismatch, unrelated to the `initialize` flag.

## 12. Practical Workflow for Bytecode-Generating Frameworks

When designing runtime code generation or dynamic proxies using hidden classes, apply this pipeline:

```text
[1] Trusted source/generator produces classfile bytes
     |
[2] Check package/module/name, version, policy
     |
[3] Obtain Lookup from the right caller; check hasFullPrivilegeAccess
     |
[4] Choose flags: NESTMATE? STRONG? classData?
     |
[5] Choose initialize:
       false -> want to link and validate/prepare first
       true  -> accept static initializer running immediately
     |
[6] defineHiddenClass / defineHiddenClassWithClassData
     |
[7] Receive hidden Lookup; get hiddenClass = lookupClass()
     |
[8] Obtain method handles, verify MethodType, privileges
     |
[9] When ready: ensureInitialized or active use
     |
[10] Hand out minimal API/handle, do not expose full Lookup
     |
[11] Monitor lifetime, caches, cleanup, and init errors
```

A clear validation skeleton:

```java
static MethodHandles.Lookup defineTrustedHidden(
        byte[] classBytes,
        MethodHandles.Lookup host,
        boolean initialize) throws IllegalAccessException {

    if (!host.hasFullPrivilegeAccess()) {
        throw new IllegalAccessException("Full privilege required");
    }
    // Only pass bytes whose source and package have been verified as appropriate.
    return host.defineHiddenClass(classBytes, initialize);
}
```

This is an **illustrative method** requiring `MethodHandles` to be imported; it is not a runnable application on its own and does not replace bytecode validation. In particular, `hasFullPrivilegeAccess()` is a privilege check, **not a check that the byte contents are safe**.

When you only need to create a named class without needing private/module privileges, a `Lookup` with PACKAGE may be appropriate for `defineClass`; do not force yourself to use a hidden class when the system actually needs `Class.forName` by a stable name.

## 13. Self-Check Exercises

**Exercise 1 — full privilege condition.** A Lookup has `PRIVATE` but has had `MODULE` dropped. Can it be used for `defineHiddenClass`?

**Answer:** No. Full privilege on Java 17 requires both `PRIVATE` and `MODULE`; if either is missing, `hasFullPrivilegeAccess()` is false.

**Exercise 2 — named class privileges.** A Lookup has `PACKAGE` and `MODULE` but does not have `PRIVATE`. How do `defineClass(bytes)` and `defineHiddenClass(bytes,false)` differ?

**Answer:** When the bytes are valid and in the same package, `defineClass` can succeed because it only needs PACKAGE; `defineHiddenClass` fails because it lacks full privilege.

**Exercise 3 — when does the initializer run?** `hiddenLookup = host.defineHiddenClass(bytes,false)`; then `hiddenLookup.findStatic(cls,"run",methodType(void.class))` is called but not yet invoked. Can we assert that `<clinit>` has already run?

**Answer:** We cannot assert it has run just because a MethodHandle was created. In the runnable example, `findStatic` does not initialize; the initializer runs on `ensureInitialized` or when a static invocation creates an active use.

**Exercise 4 — two hidden classes.** `defineHiddenClass(bytes,true)` is called twice in one JVM with the same bytes whose static initializer increments a global counter. Can the counter be seen incrementing twice?

**Answer:** Yes, because the two calls create **two different hidden Classes**, each running its own initializer. Each class initializing once does not mean each byte array is initialized only once.

**Exercise 5 — ORIGINAL.** `privateLookupIn(Target.class, caller)` within the same module returns a Lookup with full privilege but usually without ORIGINAL. What happens when using that Lookup to call `defineHiddenClass`? Can it be used as an argument to `MethodHandles.classData` equivalently to the Lookup on the created hidden class?

**Answer:** Full privilege is sufficient for `defineHiddenClass` if the bytes have the right package and other conditions are valid. However, `MethodHandles.classData` requires ORIGINAL on the passed-in Lookup; so do not replace the hidden class's Lookup with another Lookup that lacks ORIGINAL.

**Exercise 6 — cross-module.** A framework opens a plugin's package with `opens` and successfully calls `privateLookupIn(Plugin.class, frameworkLookup)`. Why can `defineHiddenClass` still throw IllegalAccessException?

**Answer:** A Lookup teleported to another module **loses MODULE mode**, so it does not have full privilege. The framework needs a trusted factory mechanism inside the target module.

**Exercise 7 — finding a hidden class.** Why is `Class.forName(hiddenClass.getName())` not a reliable way to look up the class again?

**Answer:** A hidden class does not have a normal binary name for a class loader to look up by name; use the returned `Class<?>` and Lookup/MethodHandle.

**Exercise 8 — STRONG.** Does enabling `ClassOption.STRONG` cause the class to be automatically initialized?

**Answer:** No. STRONG relates to unloading/lifetime. Initialization timing is still controlled by the `initialize` boolean and active use.

**Exercise 9 — security.** Is passing a full-privilege Lookup and user-supplied bytes to `defineHiddenClass(bytes,false)` safe solely because of false?

**Answer:** No. False only defers initializers; the class can be initialized on active use, and the hidden class still has privileges in the module/package under Java mechanisms. You must verify the byte source, scope of granted privileges, and code execution policy.

## 14. Official Documentation

- [Oracle JDK 17 — `MethodHandles.Lookup`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html): `hasFullPrivilegeAccess`, `lookupModes`, `defineClass`, `defineHiddenClass`, `defineHiddenClassWithClassData`, `ensureInitialized`, `dropLookupMode`.
- [Oracle JDK 17 — `MethodHandles.Lookup.ClassOption`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.ClassOption.html): `NESTMATE` and `STRONG`.
- [Oracle JDK 17 — `MethodHandles`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.html): `lookup`, `publicLookup`, `privateLookupIn`, `classData`, `classDataAt`.
- [Java Language Specification SE 17 `12.4](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.4): initialization of classes and interfaces, active use, initialization errors.
- [Java Virtual Machine Specification SE 17 `5.3.5](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.3.5): deriving a class from its class file representation.
- [Java Virtual Machine Specification SE 17 `5.5](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.5): initialization at the JVM level.
- [Oracle JDK 17 — `Class.isHidden`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#isHidden()): identifying a hidden class.

**Key takeaway:** `defineHiddenClass` and `defineHiddenClassWithClassData` require a **full-privilege = PRIVATE + MODULE** Lookup; `defineClass` only requires **PACKAGE**. `initialize=true` executes `<clinit>` before define returns; `false` only **defers**, not prevents, initialization upon active use or when calling `ensureInitialized`/APIs that require it. Always separate the concerns of **class-definition privilege**, **initializer execution timing**, and **hidden class lifetime** — and never expose a full Lookup when a narrowly scoped handle is sufficient.

# `InaccessibleObjectException` and Why Access Cannot Be Opened in Java Reflection

A reflection snippet may find a `Field`, `Method`, or `Constructor`, yet fail immediately at `setAccessible(true)`:

```text
java.lang.reflect.InaccessibleObjectException:
  Unable to make ... accessible:
  module java.base does not "opens java.lang" to unnamed module ...
```

This is usually a sign of **strong encapsulation between modules**, especially when a library attempts to deep-reflect into a `private` member of the JDK or another *named module*. You must distinguish three things: **finding a declaration**, **being permitted to bypass Java language access checks**, and **actually reading/writing/invoking the member**. Finding a field with `getDeclaredField()` does not grant permission to read that field.

This lesson covers the semantics of `InaccessibleObjectException` in Java 17+, how `exports` and `opens` in the Java Platform Module System (JPMS) affect reflection, a diagnostic workflow, fixing it properly in `module-info.java`, and using `--add-opens` narrowly.

## 1. When Does `InaccessibleObjectException` Appear?

`java.lang.reflect.InaccessibleObjectException` is an **unchecked exception** (extending `RuntimeException`). It indicates that the program **cannot request bypassing Java language access checks** for a reflection object, typically with `AccessibleObject.setAccessible(true)`. The objects involved include:

| Object | API That Typically Triggers the Error | Definition of What It Wants to Do |
| --- | --- | --- |
| `Field` | `field.setAccessible(true)` | Request permission to read/write the field even though normal access checks would block it |
| `Method` | `method.setAccessible(true)` | Request permission to invoke the method bypassing normal access checks |
| `Constructor<?>` | `constructor.setAccessible(true)` | Request permission to invoke the constructor bypassing normal access checks |
| Array `AccessibleObject[]` | `AccessibleObject.setAccessible(array, true)` | Request suppressing access checks for each element |

In particular, *this exception does not mean the field or method does not exist*. For example, `String.class.getDeclaredField("value")` can find the internal `private` field, yet `setAccessible(true)` does not necessarily succeed.

### Three APIs, Three Different Questions

- `getDeclaredField("x")`, `getDeclaredMethod(...)`: **is there such a declaration?** Usually returns metadata without granting permission to operate on the member.
- `canAccess(receiver)`: **given the current caller and receiver, does the reflective operation pass access checks?** May return `true` if the member is already accessible or check suppression has been enabled.
- `trySetAccessible()`: **attempt to request suppressing Java language access checks**; returns `true` when it succeeds, `false` when access cannot be enabled under the API's permission rules (another error such as `SecurityException` may still occur in environments enforcing a security policy).
- `setAccessible(true)`: makes the same request as `trySetAccessible()`, but can **throw `InaccessibleObjectException`** when access cannot be enabled.

The accessibility flag on an `AccessibleObject` is a reflection mechanism; it **does not change** the original modifier of the class, field, or method. `private` remains `private`. `setAccessible(false)` simply re-enables normal access checks for that reflection object.

## 2. Root Cause: Missing Package Open Permission for the Right Caller

JPMS (Java 9+) adds boundaries between named modules on top of the language's `public`/`private` rules. `requires` establishes module readability, `exports` grants permission to use public APIs, and `opens` allows requesting to bypass Java access checks when Reflection needs deep access. **`InaccessibleObjectException` arises at the step of requesting access**, not because a field disappeared.

| Package Policy in Named Module | Public API from Another Module | `setAccessible(true)` on a Private Member from Another Module |
| --- | --- | --- |
| Neither `exports` nor `opens` | Not permitted via normal Java access | Blocked unless another valid permission exists |
| Only `exports p` (optionally `to m`) | Yes, for permitted callers and valid visibility | `exports` is not enough |
| Only `opens p` (optionally `to m`) | Does not automatically grant `import` at compile time | Can succeed for the caller module to which it is opened |
| Both `exports` and `opens` | Public API permission and deep reflection within the granted scope | Can succeed |

If you own module `com.example.domain`, you can `exports com.example.domain.api;` for the official API and `opens com.example.domain.model to com.example.serializer;` for a serializer that must read private members. If you choose `open module`, every package will be opened for Reflection; inside the body of an `open module`, do not add per-package `opens`.

### Why Does This Error Appear Frequently Starting in Java 17?

Earlier JDK versions had compatibility mechanisms allowing many libraries to keep reflecting into JDK internals. Since **Java 17 (JEP 403)**, strong encapsulation of internal JDK APIs is the default behavior and the legacy `--illegal-access` option no longer re-enables the old broadened-access mechanism. Libraries that still call `setAccessible(true)` on fields/methods in unopened JDK packages can hit `InaccessibleObjectException`.

For example, `java.lang` belongs to module `java.base`. This module has widely used public APIs, yet seeing class `java.lang.String` **does not** grant permission to read `String`'s `private` fields. Even when using `String` normally, deep reflection into its internal structure can be blocked.

## 3. Runnable Java 17+ Example to Reproduce the Error

Save the following as `DeepReflectionDemo.java`. The example intentionally tries to access an internal field of `String` to observe the difference between **finding the declaration** and **being allowed to open access**. The program only tests metadata/accessibility and does not read or modify `String`'s field value.

```java
import java.lang.reflect.Field;
import java.lang.reflect.InaccessibleObjectException;
import java.lang.reflect.Modifier;

public class DeepReflectionDemo {
    public static void main(String[] args) throws Exception {
        Class<?> owner = String.class;
        Field field = owner.getDeclaredField("value");
        String receiver = "hello";

        System.out.println("module: " + owner.getModule().getName());
        System.out.println("field private: "
                + Modifier.isPrivate(field.getModifiers()));
        System.out.println("canAccess before: "
                + field.canAccess(receiver));

        boolean opened = field.trySetAccessible();
        System.out.println("trySetAccessible: " + opened);

        try {
            field.setAccessible(true);
            System.out.println("setAccessible: OK");
        } catch (InaccessibleObjectException ex) {
            System.out.println("setAccessible: InaccessibleObjectException");
        }

        System.out.println("canAccess after: "
                + field.canAccess(receiver));
    }
}
```

Compile and run normally:

```bash
javac DeepReflectionDemo.java
java DeepReflectionDemo
```

Without permission opening package `java.lang` to code in the *unnamed module* (classpath), typical output on Java 17+ is:

```text
module: java.base
field private: true
canAccess before: false
trySetAccessible: false
setAccessible: InaccessibleObjectException
canAccess after: false
```

- `getDeclaredField("value")` succeeds because the API allows viewing declaration metadata.
- `trySetAccessible()` returns `false`: no permission to suppress access checks on the private field in that JDK package.
- `setAccessible(true)` makes the same permission request and throws the exception. This is the failure point simulated in this lesson.

Run the same class again **with just that one package opened**:

```bash
java --add-opens java.base/java.lang=ALL-UNNAMED DeepReflectionDemo
```

Expected output:

```text
module: java.base
field private: true
canAccess before: false
trySetAccessible: true
setAccessible: OK
canAccess after: true
```

This option opens `java.lang` of module `java.base` to all *unnamed modules*, including the classpath code of the example. That allows suppressing checks at runtime; **it does not make the field public** and does not alter `getModifiers()`. Avoid depending directly on `String.value` in real application code: JDK internal structure is not a stable public contract.

## 4. Separating Four Commonly Confused Causes

### 4.1. Package in Another Module Is Not `opens`-ed

Symptom: the source module and package name appear in the message, for instance:

```text
module com.example.domain does not "opens com.example.domain.model"
to module com.example.serializer
```

This is a **package-opening** error. Fix it in the module that owns the data if possible, e.g., `opens com.example.domain.model to com.example.serializer;`. Do not try to fix it in the calling module by writing `opens` for a package it does not own.

### 4.2. Package Is `exports`-ed but Not `opens`-ed

A `public` method of a `public` class can be called normally from a module with read/export permission; at the same time, `private` fields of that very class remain inaccessible to deep access. JSON, ORM, and dependency injection frameworks that need to instantiate/populate fields via reflection can encounter this case.

Fix according to actual need: public API → `exports`; private runtime access by a framework → appropriate `opens`. Both can be used if both needs coexist.

### 4.3. Code Lacks Normal Java Access Permission

A `private` field or package-private method from another package/caller can cause `IllegalAccessException` when **reading/writing/invoking without suppressing access checks**. This case does not inherently equate to `InaccessibleObjectException`.

For example, `field.get(receiver)` can throw `IllegalAccessException` while checks are active. Meanwhile, `field.setAccessible(true)` is the request to suppress checks; if the module blocks that request, `InaccessibleObjectException` appears.

### 4.4. Running via Classpath, Module Path, or Different Environments

In an unnamed module (classpath code), a named module typically sees the target caller as `ALL-UNNAMED` in `--add-opens` configuration. With a named module, the target must be the **exact module name**, such as `com.example.serializer`. Therefore, a command that works in an IDE yet fails in production can result from differing JVM flags, module path, module descriptors, or packaging.

Remember that build configuration or `javac` arguments are not necessarily the arguments of the running JVM. Deep reflection permission must be granted in the **runtime process** actually experiencing the error.

## 5. Choosing the Fix: `module-info.java` or a Runtime Flag?

When you **own the target module**, the clearest approach is to declare the required reflection contract in `module-info.java`. For example, a domain module:

```java
module com.example.domain {
    exports com.example.domain.api;
    opens com.example.domain.model to com.example.mapper;
}
```

Explanation: `com.example.mapper` is a **module name**, not a package name or class name. If your project uses a framework packaged as a named module, open to the **module name the framework actually uses**. Do not blindly guess this name from a Maven artifact: an automatic module name and declared module name can differ from the artifact filename.

When you **do not own the target module**, you can use the narrowest runtime option for a specific compatibility issue:

```bash
java --add-opens com.example.domain/com.example.domain.model=com.example.mapper \
     --module-path mods \
     --module com.example.app/com.example.app.Main
```

The trailing `\` in the example is line continuation for POSIX-style shells; in Windows PowerShell, write the command on one line or use PowerShell's line-continuation syntax. The module/package names here are **structural examples**, to be used only after substituting the real names in your application.

For applications on the classpath:

```bash
java --add-opens java.base/java.lang=ALL-UNNAMED -cp app.jar com.example.Main
```

Option syntax:

```text
--add-opens SOURCE_MODULE/PACKAGE=TARGET_MODULE
```

When there are multiple targets, you can specify them per your JVM/version documentation; usually only the framework/caller module actually using it is needed, or `ALL-UNNAMED` if the library sits on the classpath. **Open only the packages genuinely needed**, because each `--add-opens` widens the scope of code able to use reflection to bypass access checks in that package.

### How Does `--add-opens` Differ from `--add-exports`?

| Option | Primary Purpose | Does It Automatically Allow Suppressing Private Access? |
| --- | --- | --- |
| `--add-exports source/pkg=target` | Grants additional access to public types of a package | No |
| `--add-opens source/pkg=target` | Opens a package for reflection at runtime | Possible, per `AccessibleObject` rules |

**Do not substitute `--add-exports` for `--add-opens`** when the issue is `setAccessible(true)` on a `private` field. Conversely, when a program needs to *compile/import* a public class from an unexported module, you may need to resolve exports; `--add-opens` does not make compile-time imports valid.

Better yet, if an official public API exists, use the public API or an updated library version to avoid internal access. Compatibility flags should be treated as a controlled measure, especially when a library touches multiple internal JDK packages.

## 6. Workflow for Reading Stack Traces to Find the Right Package and Module

A typical stack trace usually has a message containing:

```text
Unable to make <member> accessible:
module <source-module> does not "opens <source-package>"
to <caller-module>
```

Extract four exact facts: **accessed member**, **source module**, **source package**, and **caller module**. For example: `java.lang.String.value`, `java.base`, `java.lang`, and `unnamed module`. When the message says `to unnamed module`, the runtime fix usually needs `ALL-UNNAMED`; when it says `to module com.example.mapper`, target that exact named module.

You can inspect metadata at runtime:

```java
Class<?> type = String.class;

Module sourceModule = type.getModule();
String packageName = type.getPackageName();
Module callerModule = DeepReflectionDemo.class.getModule();

System.out.println(sourceModule.getName());
System.out.println(packageName);
System.out.println(callerModule.isNamed());
System.out.println(sourceModule.isOpen(packageName, callerModule));
```

This is an **illustrative snippet used inside `DeepReflectionDemo`**, not a new standalone program. For the classpath example where `java.lang` is not opened, `callerModule.isNamed()` is `false` and `sourceModule.isOpen("java.lang", callerModule)` is `false`. When `--add-opens java.base/java.lang=ALL-UNNAMED` is added, `isOpen(packageName, callerModule)` returns `true`.

If an application is split across multiple class loaders/module layers or multiple Java processes, check the exact JVM process throwing the exception. Flags set on a different process will not resolve the error.

## 7. `canAccess()` and `trySetAccessible()`: Safe Usage

Instead of always calling `setAccessible(true)` and letting the exception propagate up to the application layer, a library can proactively probe accessibility:

```java
import java.lang.reflect.Field;

public final class SafeFieldRead {
    public static Object read(Field field, Object receiver)
            throws IllegalAccessException {
        if (!field.canAccess(receiver) && !field.trySetAccessible()) {
            throw new IllegalStateException(
                    "Cannot open reflection for "
                    + field.getDeclaringClass().getName()
                    + "." + field.getName());
        }
        return field.get(receiver);
    }
}
```

This is a **syntactically standalone utility class**; it does not include `main`. `receiver` must be valid for the field: an instance field requires an object of the declaring class or a compatible subtype; a static field uses `null`. Passing the wrong receiver can cause `IllegalArgumentException`. `trySetAccessible()` returns `false` when access cannot be opened due to JPMS rules; not every access failure turns into `false`.

Design note: if building a library targeting Java 17+, do not catch `InaccessibleObjectException` and pretend reading the field succeeded. Provide a diagnostic message naming the module/package along with options for a public API, intentional `opens`, or updating the library.

For modern frameworks, structured alternatives such as constructor injection, valid accessors, factory methods, `MethodHandles.privateLookupIn` (if module conditions permit), or supported serialization configuration are more sustainable than depending on internal JDK `private` fields. **`privateLookupIn` is not a backdoor to bypass unopened packages either**, since it is governed by its own access/module rules.

## 8. Distinguishing from Other Reflection Exceptions

| Error Type | Where It Usually Happens | Practical Meaning |
| --- | --- | --- |
| `NoSuchFieldException` / `NoSuchMethodException` | `getDeclaredField` / `getDeclaredMethod` | Name/signature could not be found within the search API's scope |
| `IllegalAccessException` | `Field.get/set`, `Method.invoke`, or constructor invocation | Access checks were not satisfied when performing the operation |
| `InaccessibleObjectException` | `setAccessible(true)` | Cannot enable suppressing Java access checks, usually because the package/module is not `opens`-ed |
| `InvocationTargetException` | `Method.invoke` or `Constructor.newInstance` | The invoked method/constructor body threw an exception; inspect `getCause()` |
| `IllegalArgumentException` | `Field.get/set`, `canAccess`, `Method.invoke`... | Invalid argument/receiver/type |
| `SecurityException` | When a security environment enforces corresponding controls | A runtime policy may reject the operation independently of JPMS `opens` |

Distinguishing keywords:

- **Lookup failure:** wrong member name, signature, or search scope.
- **Access check failure:** the member exists, yet cannot be operated on yet.
- **Suppress failure:** cannot enable bypassing access checks ⇒ the `InaccessibleObjectException` case.
- **Target exception:** the method already ran; the error originated from target code, not from opening permissions.

Diagnosing the right error category prevents wrong fixes like "add `--add-opens`" for `NoSuchFieldException` or editing `getDeclaredMethod` when the module's package is actually closed.

## 9. Common Configuration Mistakes

**Mistake A — Using `exports` instead of `opens`.** Adding `exports p` only enables using public APIs; it does not grant `private` access via `setAccessible(true)` to external modules. You need `opens p to framework.module` if the framework genuinely has a legitimate deep reflection requirement.

**Mistake B — Opening the wrong side.** The `opens` directive goes in the module **that owns the reflected package**, not in the caller module. If the stack trace says `module java.base does not "opens java.lang"`, editing the application's `module-info.java` to `opens com.example.app` does not solve anything for `java.lang`.

**Mistake C — Using the wrong target.** `ALL-UNNAMED` covers unnamed modules on the classpath; a library already inside a named module needs permission directed to its actual module name. The exception message is a more reliable clue than guessing from a JAR name.

**Mistake D — Setting the flag at build time instead of runtime.** `--add-opens` must be applied to the exact JVM performing reflection. IDE Run Configurations, `java` commands, Gradle Test forks, containers, and production servers can have different JVM args. Avoid the "already added the flag" trap when it was added to the wrong JVM.

**Mistake E — Using `--illegal-access=permit` from outdated guides.** Since Java 17 this option is obsolete and no longer restores JDK package-opening permissions like the earlier compatibility mechanism. Update the library or supply targeted `--add-opens` if genuinely needed.

**Mistake F — Opening all JDK packages to silence logs.** That both widens runtime permissions unnecessarily and hides reliance on unstable internal APIs. Open only verified packages and track why the library still requires that access.

**Mistake G — Thinking a `public` member is always enough.** A public method inside a class/package/module not appropriately exposed can still be inaccessible. You must consider the accessibility of the declaring class, package/module, and caller.

## 10. Step-by-Step Troubleshooting Workflow

1. **Identify where the error is thrown.** Is it `setAccessible`, `trySetAccessible`, `getDeclaredXxx`, or `invoke`? Merely reading "reflection failed" is not enough.
2. **Read the exact message.** Note the source module, package, caller, and member. If there is no JPMS message, check other possibilities.
3. **Determine how it runs.** Does the caller code belong to an unnamed module on the classpath or a named module on the module path? Which exact JVM/process is throwing the error?
4. **Verify the intent.** Does the framework truly need private fields/methods, or can it call a public API or upgrade to a Java 17+ compatible version?
5. **If you own the source module**, open the smallest package to the exact target module with `opens ... to ...`. If consumers are in unnamed modules and must be supported, consider a broader opens policy deliberately.
6. **If you do not own the source module**, use a library version supporting the current JDK; only when necessary add `--add-opens source/pkg=target` to the right runtime.
7. **Rerun real tests** on the same JDK, runtime args, and packaging as production; verify `InaccessibleObjectException` is gone and functional behavior remains correct.

### Self-Check Questions

**1.** Why can `getDeclaredField("value")` succeed while `setAccessible(true)` fails?  
Because finding metadata does not mean having permission to suppress access checks across module boundaries.

**2.** Is `exports com.example.model;` enough for a framework to read private fields via reflection?  
No. When the caller is in another module, `opens com.example.model to framework.module;` or equivalent runtime permission is usually needed.

**3.** What does `--add-opens java.base/java.lang=ALL-UNNAMED` affect?  
It opens **package `java.lang`** of **module `java.base`** for deep reflection from **unnamed modules** in the JVM runtime carrying that flag; it does not make `String.value` public and does not enable arbitrary compile-time imports from JDK internals.

**4.** When `Method.invoke(...)` throws `InvocationTargetException`, should you default to adding `--add-opens`?  
No. Inspect `getCause()` because the target method already ran and threw its own error; only add opens when there is actual evidence of a JPMS-related error.

## Takeaways

- `InaccessibleObjectException` usually reports **inability to enable access-check suppression**; it does not mean `NoSuchFieldException` or `IllegalAccessException`.
- **`exports` is for public APIs**, **`opens` is for runtime deep reflection**, with the ability to specify target modules.
- **`trySetAccessible()`** lets you check whether opening permission succeeds without always receiving `InaccessibleObjectException`; **`canAccess()`** answers about access with the actual caller/receiver.
- On Java 17+, strong encapsulation protects most JDK internals. Prefer public APIs/compatible libraries; if you must open a package, open only the exact source/target and exact JVM.

Clearly understanding the three layers **find declaration → request check suppression → execute access** is the key to explaining and properly fixing the root cause of `InaccessibleObjectException`.

# IllegalAccessError, IllegalAccessException, and InaccessibleObjectException in Java ClassLoader

## 1. Three Different Errors Despite Very Similar Names

When Java works with `ClassLoader`, reflection, and JPMS, a program can encounter errors that all contain the phrase “Illegal Access” yet arise from different mechanisms:

- **`java.lang.IllegalAccessError`**: an error thrown when **the JVM links/resolves or uses a symbolic reference** to a class, field, or method that the caller is not permitted to access. This is an `Error` under the `LinkageError` branch; it typically appears if a class was compiled with one version of an API but runs with a version whose visibility changed incompatibly.
- **`java.lang.IllegalAccessException`**: a **checked exception**, typically occurring when code uses `Method.invoke`, `Field.get`, `Field.set`, or `Constructor.newInstance` while Java reflection access checks remain in effect and the caller does not have permission to access the member.
- **`java.lang.reflect.InaccessibleObjectException`**: an **unchecked exception** that occurs when code **attempts to suppress access checks** via `setAccessible(true)` but is not permitted to do so, especially when a named module does not open the package to the caller in Java 9+.

You should not conclude “just call `setAccessible(true)`” whenever you see one of these three errors. With `IllegalAccessError`, the issue is usually **binary compatibility or JVM access linkage**. With `IllegalAccessException`, you need to inspect the caller/member and the reflection operations. With `InaccessibleObjectException`, you need to check **the module's package-opening permissions** and whether deep reflection is truly necessary.

~~~text
                 ACCESS OPERATION
                        |
      +-----------------+------------------+
      |                 |                  |
      v                 v                  v
 bytecode call     Method.invoke      setAccessible(true)
 getfield / etc.   Field.get ...           |
      |                 |                  |
  access check     access checks       suppressed?
      |                 |                  |
 illegal          illegal                 no
      |                 |                  |
      v                 v                  v
 IllegalAccessError  IllegalAccessException  InaccessibleObjectException
~~~

The diagram only illustrates typical causes, not every possible error. For example, if a method is invoked successfully via reflection but its body throws an exception, reflection may wrap the cause in `InvocationTargetException`, rather than automatically throwing `IllegalAccessException`.

## 2. Comparison by Error Class, Timing, and Fix

| Characteristic | IllegalAccessError | IllegalAccessException | InaccessibleObjectException |
| --- | --- | --- | --- |
| Package | `java.lang` | `java.lang` | `java.lang.reflect` |
| Inheritance | `Error → LinkageError → IncompatibleClassChangeError` | `Exception → ReflectiveOperationException` | `RuntimeException` |
| Checked exception? | No | Yes | No |
| Common API/context | `invokevirtual`, `invokestatic`, symbolic class/field/method access | `Method.invoke`, `Field.get`, `Constructor.newInstance` | `AccessibleObject.setAccessible(true)` |
| Common cause | Runtime binary no longer permits the compiled direct access | Reflection caller lacks permission for a private/package-private member | JPMS package lacks `opens` to the caller |
| Caught by `catch (Exception)`? | No | Yes | Yes |
| Root fix | Align JAR versions, visibility, exports, and class loader | Public API or reflection with valid permissions | Public API, appropriate `opens`, library/JDK compatibility |
| Always fixed by `--add-opens`? | No | Not for every case | Can help specifically when the cause is an unopened JPMS package |

**Be careful with the inheritance hierarchy order:** `IllegalAccessError` directly extends `IncompatibleClassChangeError`, which extends `LinkageError`, and then `Error`. `IllegalAccessException` is not in the same branch despite having a very similar name.

## 3. Access Modifiers and Access Control in the JVM

Java has four common visibility levels:

- `public`: the class/member can be accessed when the declaring type, module, and caller satisfy the relevant rules.
- `protected`: in addition to the same package, it also has access based on subclass relationships with specific JVM constraints.
- **Package-private** (no modifier specified): within the same **runtime package**.
- `private`: narrow access governed by class/nestmate rules, not simply by sharing the same package.

Example:

~~~java
package demo;

class HiddenClass {
    public static void run() {
        System.out.println("running");
    }
}
~~~

This is **illustrative code**, without a main method. Method `run` is public, whereas class `HiddenClass` is package-private. A caller in another package cannot access that method by default.

With a named module, you must also consider:

1. Does the caller module **read** the module containing the target?
2. Does the target package have **exports** to the caller for using the public API?
3. If you want deep reflection, does the target package have **opens** to the caller?
4. Does the declaring class/member actually satisfy Java language access rules?
5. When custom loaders are involved, do the caller and target belong to the exact same **runtime package**?

Two classes that both write `package demo;` in Java source are **not necessarily** in the same runtime package if their two defining class loaders are different. `getPackageName()` only gives the string name; it does not prove package-private access across loaders.

## 4. IllegalAccessError: Direct JVM Access Failure

According to the Java SE 17 API, `IllegalAccessError` is thrown when an application attempts to access or modify a field, or to call a method that it does not have access to. The Java compiler normally catches this error if all source code is compiled against the same API definition. Therefore, at runtime, this symptom usually suggests that **the runtime class definition differs from the compile-time definition**.

Example of an incompatible change:

~~~text
At compile time:
  api.Library.greet() is public static

At runtime:
  api.Library.greet() is static, package-private

client.Main still contains bytecode calling api.Library.greet()
=> JVM denies call permission => IllegalAccessError
~~~

Situations that can cause this:

- A public API method has its visibility reduced in a new library version.
- A public class is changed to package-private at runtime.
- A module does not export the package to the caller even though the bytecode has a direct reference.
- A dependency JAR of the wrong version appears ahead of the intended version on the classpath.
- A plugin loader or hot reload picks up a different class from the one the compiler previously used.
- Two classes with the same source package are **defined by different loaders**, losing package-private access.
- Bytecode weaving/shading/instrumentation creates a reference rejected by the JVM.

Because this is an `Error` in the **binary linkage** branch, catching it and continuing to run as if nothing happened is usually the wrong approach. You need to fix the dependency graph, module ownership, source/API compatibility, or class loader routing.

## 5. Complete Java 17+ Example: Reproducing IllegalAccessError

This example builds a client that runs normally with library v1, and then **replaces only the library class** with v2 without recompiling the client.

### 5.1. Directory Structure

~~~text
linkage-demo/
├── v1-src/
│   └── api/
│       └── Library.java
├── v2-src/
│   └── api/
│       └── Library.java
└── client-src/
    └── client/
        └── Main.java
~~~

### 5.2. File v1-src/api/Library.java

~~~java
package api;

public class Library {
    public static String greet() {
        return "hello";
    }
}
~~~

### 5.3. File v2-src/api/Library.java

~~~java
package api;

public class Library {
    static String greet() { // No longer public
        return "hello";
    }
}
~~~

### 5.4. File client-src/client/Main.java

~~~java
package client;

import api.Library;

public class Main {
    public static void main(String[] args) {
        try {
            System.out.println("call: " + Library.greet());
        } catch (IllegalAccessError expected) {
            System.out.println("call: IllegalAccessError");
        }
    }
}
~~~

### 5.5. Running v1

From inside the `linkage-demo` directory, using JDK 17 or later:

~~~bash
javac --release 17 -d out v1-src/api/Library.java client-src/client/Main.java
java -cp out client.Main
~~~

Stdout:

~~~text
call: hello
~~~

### 5.6. Replacing Only the Library with v2, Keeping Main.class Unchanged

~~~bash
javac --release 17 -d out v2-src/api/Library.java
java -cp out client.Main
~~~

Stdout:

~~~text
call: IllegalAccessError
~~~

**Explanation:** `client.Main.class` still references `api.Library.greet()Ljava/lang/String;` via the `invokestatic` instruction. When the JVM runs in a **new process** with v2's `Library.class`, the method still has that name/descriptor but has become package-private; `client.Main` is in a different package, so it does not have permission to call it. If `Main.java` is recompiled directly against v2, the compiler will report the access problem beforehand. We intentionally keep the old client bytecode to demonstrate **runtime binary incompatibility**.

This is not `IllegalAccessException` because there is no `Method.invoke`, and it is not `InaccessibleObjectException` because there is no `setAccessible(true)`.

## 6. IllegalAccessException: Reflection Access Check

When using `java.lang.reflect.Method`, `Field`, or `Constructor`, Java reflection must verify whether the caller is allowed to access the member. `IllegalAccessException` is a **checked exception** describing the case where a reflection operation lacks permission.

Common APIs:

~~~java
Method method = SomeClass.class.getDeclaredMethod("secret");
method.invoke(null);
~~~

This is **illustrative code** assuming `SomeClass` has a static method `secret`. `getDeclaredMethod` can locate **private method metadata**, yet `invoke` can still throw `IllegalAccessException` when access checks are enabled.

Distinctions:

- `Class.getDeclaredMethod`: finds a method declared in the class, including private ones, without granting permission to invoke it.
- `Method.invoke`: enforces Java access checks unless suppression has been allowed, and may throw `IllegalAccessException`.
- `Field.get/set`: checks on fields can also produce `IllegalAccessException`.
- `Constructor.newInstance`: a constructor that is not accessible from the caller can cause `IllegalAccessException`.
- `MethodHandles.Lookup.findVirtual`, `findStatic`, and `privateLookupIn` have MethodHandles access rules; they can also throw `IllegalAccessException`, though **not on the same call path** as `Method.invoke`.

If the method is actually invoked and **its body throws an exception**, `Method.invoke` normally wraps it in **`InvocationTargetException`**. You should inspect `getCause()` before saying the error is due to reflection access.

## 7. Complete Java 17+ Example: IllegalAccessException Then Enabling Access

Create the file **ReflectionDemo.java**:

~~~java
import java.lang.reflect.Method;

class Vault {
    private static String secret() {
        return "private-data";
    }
}

public class ReflectionDemo {
    public static void main(String[] args) throws Exception {
        Method method = Vault.class.getDeclaredMethod("secret");

        try {
            method.invoke(null);
            System.out.println("invoke without override: allowed");
        } catch (IllegalAccessException expected) {
            System.out.println(
                    "invoke without override: IllegalAccessException");
        }

        System.out.println("trySetAccessible: "
                + method.trySetAccessible());
        System.out.println("private result: "
                + method.invoke(null));
    }
}
~~~

Compile and run:

~~~bash
javac --release 17 ReflectionDemo.java
java ReflectionDemo
~~~

Exact stdout:

~~~text
invoke without override: IllegalAccessException
trySetAccessible: true
private result: private-data
~~~

**Explanation:**

1. `Vault.secret()` is private. `ReflectionDemo` is a different top-level class, not a nestmate permitted to access that private member.
2. `getDeclaredMethod` can still locate the method metadata.
3. The first `invoke(null)` encounters the access check and throws `IllegalAccessException`.
4. Because `Vault` and `ReflectionDemo` are in the same unnamed module, `trySetAccessible()` is allowed to return true according to `AccessibleObject` rules.
5. The subsequent `invoke` uses the enabled accessible flag and succeeds.

**Do not assume that trySetAccessible is always true.** When the target resides in another named module and the package is not open, suppression may be denied, as shown in the next example.

## 8. InaccessibleObjectException: setAccessible(true) Denied

In Java 9+, **`InaccessibleObjectException` extends `RuntimeException`**. The typical error occurs when:

~~~java
Method method = targetClass.getDeclaredMethod("hidden");
method.setAccessible(true);
~~~

This is an **illustrative snippet**. The caller wants to disable Java language access checks, but the module containing the declaring class has not opened the package to the caller's module. `setAccessible(true)` throws `InaccessibleObjectException` right at the request to enable access.

Side by side:

| API call | Related error type |
| --- | --- |
| `method.invoke(obj)` while the access check is enabled | `IllegalAccessException` |
| `method.setAccessible(true)` when suppression is not permitted | `InaccessibleObjectException` |
| `method.trySetAccessible()` when suppression is not permitted | Returns `false` per the normal contract |
| `method.invoke(obj)` after valid suppression is enabled | Can execute the method; the body may throw its own exception |

`trySetAccessible` is a graceful way to check, **not a backdoor** to bypass JPMS. If it returns false, the application still needs to choose another public API or adjust module ownership appropriately.

One note: for certain public members in exported public classes, `setAccessible(true)` may still be allowed under JDK conditions — **not every setAccessible call on a named module's member throws**. The common issue is **private/protected/package-private members in another module whose package is not open**.

## 9. Exports, Opens, Requires: Three Things Not to Conflate

JPMS (Java 9+) has named modules and the `module-info.java` descriptor.

~~~java
module library.mod {
    exports sample.lib;
}
~~~

This descriptor allows code in modules that read `library.mod` to use the **public types of package `sample.lib`** according to Java access rules. However, `exports` **does not grant deep reflection by default** to private fields/methods.

Comparison:

| Declaration | Primary effect |
| --- | --- |
| `requires library.mod;` | The consumer module can read the library module |
| `exports sample.lib;` | The package exposes its public API to any module that reads it |
| `exports sample.lib to app.mod;` | The public API is exported only to app.mod and the explicitly listed targets |
| `opens sample.lib;` | Opens the package for deep reflection from other modules |
| `opens sample.lib to app.mod;` | Opens deep reflection only to app.mod |
| `open module library.mod { ... }` | Opens the module's packages according to open module rules |

**A package that has exports is not necessarily open.** Therefore, code can compile and call `SecretBox.publicMessage()` normally, yet calling `setAccessible(true)` on `SecretBox.secretMessage()` is still denied.

The launcher has two corresponding options:

~~~text
--add-exports library.mod/sample.lib=app.mod
--add-opens library.mod/sample.lib=app.mod
~~~

`--add-exports` is used for access to the **public API** under module rules; `--add-opens` grants **deep reflection** permission to the specified caller module. You should not use `--add-opens` as a “universal fix for every IllegalAccessError” because it does not turn a private member into public in bytecode and does not fix version mismatches.

## 10. Complete Java 17+ Example: An Exported Package Still Blocks Deep Reflection

This named-modules experiment shows that **the same private method** causes `IllegalAccessException` when called via `invoke`, and `InaccessibleObjectException` when trying to enable accessibility.

### 10.1. Directory Structure

~~~text
jpms-access-demo/
└── src/
    ├── library.mod/
    │   ├── module-info.java
    │   └── sample/
    │       └── lib/
    │           └── SecretBox.java
    └── app.mod/
        ├── module-info.java
        └── sample/
            └── app/
                └── Main.java
~~~

### 10.2. src/library.mod/module-info.java

~~~java
module library.mod {
    exports sample.lib;
}
~~~

### 10.3. src/library.mod/sample/lib/SecretBox.java

~~~java
package sample.lib;

public class SecretBox {
    public static String publicMessage() {
        return "public";
    }

    private static String secretMessage() {
        return "private";
    }
}
~~~

### 10.4. src/app.mod/module-info.java

~~~java
module app.mod {
    requires library.mod;
}
~~~

### 10.5. src/app.mod/sample/app/Main.java

~~~java
package sample.app;

import java.lang.reflect.Method;
import java.lang.reflect.InaccessibleObjectException;
import sample.lib.SecretBox;

public class Main {
    public static void main(String[] args) throws Exception {
        System.out.println("public call: "
                + SecretBox.publicMessage());

        Method method = SecretBox.class
                .getDeclaredMethod("secretMessage");

        try {
            method.invoke(null);
            System.out.println("invoke private: allowed");
        } catch (IllegalAccessException expected) {
            System.out.println(
                    "invoke private: IllegalAccessException");
        }

        try {
            method.setAccessible(true);
            System.out.println("setAccessible: enabled");
            System.out.println("private result: "
                    + method.invoke(null));
        } catch (InaccessibleObjectException expected) {
            System.out.println(
                    "setAccessible: InaccessibleObjectException");
        }
    }
}
~~~

### 10.6. Compiling and Running Normally

From inside `jpms-access-demo` and using JDK 17+:

~~~bash
javac --release 17 --module-source-path src -d mods -m library.mod,app.mod
java --module-path mods --module app.mod/sample.app.Main
~~~

Exact stdout:

~~~text
public call: public
invoke private: IllegalAccessException
setAccessible: InaccessibleObjectException
~~~

**Why?** `app.mod` requires `library.mod` and package `sample.lib` is exported, so the direct public call is allowed. `Method.invoke` on the private method is blocked by access checks. `setAccessible(true)` tries to suppress checks, but the package does not have `opens` to app.mod yet, so it reports `InaccessibleObjectException`.

### 10.7. Running Again with Narrow Package Opening for app.mod

~~~bash
java --add-opens library.mod/sample.lib=app.mod --module-path mods --module app.mod/sample.app.Main
~~~

Exact stdout:

~~~text
public call: public
invoke private: IllegalAccessException
setAccessible: enabled
private result: private
~~~

**Key point to understand:** `--add-opens` allows the `setAccessible(true)` request to succeed. It **does not automatically disable access checks** for the first `invoke` call, because the code calls `invoke` **before setAccessible**.

If you own the library module, a narrow declaration variant in the descriptor instead of a launcher flag is:

~~~java
module library.mod {
    exports sample.lib;
    opens sample.lib to app.mod;
}
~~~

This is an **alternative descriptor for illustration**, and must not be used simultaneously with the old descriptor. Open a package only when the application has a genuine reason to need deep reflection; package privacy is part of the internal design contract.

## 11. ClassLoader and Package-Private Access Errors

With custom class loaders, “same package in source” can be misleading:

~~~text
Source of Host.class:    package tools;
Source of Helper.class:  package tools;

Host.class  -> defined by HostLoader
Helper.class -> defined by PluginLoader

Same package name?        Yes
Same runtime package?     Not by default
Package-private access?   Not just from matching names
~~~

According to the JVM, runtime class identity depends on **binary name and defining loader**, while a runtime package is tied to the package name and defining loader. Therefore, package-private access in bytecode can fail when an application server or plugin framework splits two classes from the same source package into different loaders.

In Java 9+, module ownership and access rules must also be considered; the loader is part of the story, not the whole picture.

To reduce errors:

- Place **shared API/DTO/annotation/exception types** in a common parent loader/module.
- Do not unconditionally apply child-first loading to packages containing classes that require the same runtime package access.
- Avoid copying JARs containing shared APIs into a plugin fat JAR if the loader might redefine those types.
- Print `clazz.getClassLoader()`, `clazz.getModule()`, and `clazz.getPackageName()` to observe the actual state.
- Do not assume that setting `setAccessible(true)` on a Method grants **direct bytecode** calls package-private access; those are two different access paths.

A diagnostic helper:

~~~java
static void describe(Class<?> c) {
    System.out.println("name=" + c.getName());
    System.out.println("loader=" + c.getClassLoader());
    System.out.println("module=" + c.getModule());
}
~~~

This is an **illustrative snippet inside a Java class**. It does not check the full module graph on its own, but it helps identify classes with the same name and different defining loaders.

## 12. Inspecting Runtime Module Access Instead of Guessing

The Java 17 Module API lets you observe:

~~~java
Module caller = Caller.class.getModule();
Module target = Target.class.getModule();

System.out.println("canRead: "
        + caller.canRead(target));
System.out.println("exported: "
        + target.isExported(Target.class.getPackageName(), caller));
System.out.println("opened: "
        + target.isOpen(Target.class.getPackageName(), caller));
~~~

This is **illustrative code** with two defined classes. It helps distinguish:

- `canRead`: does the caller module read the target module?
- `isExported`: is the package exported to the caller?
- `isOpen`: is the package opened to the caller?

Even when `isOpen` is true, normal Java source code is still not free to call a private method. **Open enables reflective suppression according to the rules**; it does not change the member's Java visibility in source code.

Some reflection APIs have special caller-module readability rules (for example, `AccessibleObject` assumes readability in certain access checks); do not conclude that `canRead(false)` will always cause `Method.invoke` to report one exact exception type without considering the specific API.

## 13. Related Error Classes with Different Meanings

| Error | Common meaning |
| --- | --- |
| `ClassNotFoundException` | The queried loader could not find the class by its binary name |
| `NoClassDefFoundError` | The JVM could not obtain a required definition, or the class failed during initialization |
| `NoSuchMethodError` | Bytecode expects a method name/descriptor, but the runtime definition lacks it |
| `NoSuchFieldError` | Same, for a field |
| `IllegalAccessError` | The reference exists, but the caller lacks permission to access it according to the JVM |
| `IllegalAccessException` | Reflection/method-handle lookup was denied by an access check |
| `InaccessibleObjectException` | The request to enable reflective access suppression was denied |
| `ClassCastException` | An object is incompatible with the runtime type; may involve duplicate loaders |
| `InvocationTargetException` | Wrapper when a method invoked via reflection throws an exception itself |
| `ExceptionInInitializerError` | Class static initialization failed |
| `LinkageError` | Group of linking errors, of which `IllegalAccessError` is a subclass |
| `SecurityException` | Access was blocked by a configured runtime security mechanism |

You should not change the exception name by catching and rethrowing arbitrarily. When wrapping errors in a framework, preserve the cause/stack trace to distinguish **missing symbol, wrong loader, access violation, deep reflection denied**.

## 14. Common Mistakes When Fixing These Errors

### Mistake 1: “Adding setAccessible(true) Will Fix IllegalAccessError”

Wrong. Direct bytecode access does not go through the Method object whose accessible flag you just changed. If the runtime API has reduced visibility, you need to fix the dependency or recompile the client against the new contract.

### Mistake 2: “exports Opens Private Fields”

Wrong. Exports exposes the public API under module access. Deep reflection on a private member from another module usually requires `opens`, not just `exports`.

### Mistake 3: “trySetAccessible Returning false Means the JVM Has a Bug”

No. False is a valid result when suppressing checks is not permitted. You can fall back to a public API or report a clear configuration error.

### Mistake 4: “Having the Same Package Text Grants Package-Private Access”

Wrong in environments with different defining loaders. Check the actual runtime package and loader graph.

### Mistake 5: “Every Error During Method.invoke Is IllegalAccessException”

Wrong. If the target method is called and its body throws an exception, the wrapper is `InvocationTargetException`; if arguments are wrong, it may be `IllegalArgumentException`; a null receiver for an instance method may throw `NullPointerException`, and so on.

### Mistake 6: “Just Add --add-opens for the Entire JDK and You Are Done”

Not recommended. Broadening reflection access increases dependence on internal implementations and weakens encapsulation boundaries. Prioritize updating libraries and using public APIs; if migration requires it, grant narrow access to the exact module/package.

### Mistake 7: “IllegalAccessError Should Be Caught with catch (Exception)”

`IllegalAccessError` extends `Error`, not `Exception`. A `catch` of type `Exception` will not catch it. Catching the specific Error type in tests or at a plugin boundary for logging can be reasonable; catching should not be treated as a deployment fix.

## 15. Investigation Workflow in Real-World Applications

1. **Read the full exception name and the first stack trace line**: is it direct bytecode access, Method.invoke, or AccessibleObject.setAccessible?
2. **Capture the actual launch command**: `-cp`, `--module-path`, `--module`, `--add-exports`, `--add-opens`, and plugin class loaders.
3. **Inspect the classfile actually loaded by the JVM**: which JAR version, which class loader, which module?
4. **Compare compile-time and runtime dependencies**: has an API changed its access modifiers?
5. **If IllegalAccessError**, check symbolic method/field access, class/interface visibility, runtime package identity, and exported packages.
6. **If IllegalAccessException**, check the declaring class/member modifiers and the caller of the reflection operation.
7. **If InaccessibleObjectException**, locate the package/module that the framework is trying to open; determine whether the owner has `opens` to the caller.
8. **Distinguish access errors from missing methods/fields**: `NoSuchMethodError` and `NoSuchFieldError` require fixing binary versions/signatures.
9. **If reflection is necessary**, prefer a public accessor, `trySetAccessible` to detect graceful failure, and narrow module opening if truly needed.
10. **Retest in the exact runtime environment**, not only in an IDE with a different classpath.

Some helpful commands:

~~~bash
jar --list --file library.jar
javap -classpath library.jar -p api.Library
javap -classpath out -c -p client.Main
~~~

The commands are **examples**, assuming actual JARs/classes exist. `javap -p` inspects private/package-private members in the runtime classfile, and `javap -c` inspects the compiled bytecode callsite. Do not rely solely on the latest source code without checking the **actual running artifact**.

When running OpenJDK/HotSpot, you can enable class loading logs:

~~~bash
java -Xlog:class+load=info -cp out client.Main
~~~

Output logs depend on the JDK/JVM and can be very long, so there is no single fixed transcript.

## 16. Strong Encapsulation When Migrating from Java 8 to Java 17

A common scenario: an older framework calls `setAccessible(true)` on private fields belonging to JDK classes. In Java 8, JPMS did not yet exist. Starting in Java 9, JDK packages were organized into named modules; during the transition period, there were compatibility options.

**Java 17 strongly encapsulates JDK internals by default**. Therefore, reflecting into private members of `java.base` (such as internals of `java.lang.String`) can report `InaccessibleObjectException` if the package is not appropriately opened. For classpath applications, a flag that may appear in migration logs is:

~~~bash
java --add-opens java.base/java.lang=ALL-UNNAMED -cp app.jar main.Main
~~~

This is only a **syntax illustration** requiring an actual artifact/main class; enabling it broadly is not recommended when a public API alternative exists. `ALL-UNNAMED` refers to unnamed modules. If the caller is a **named module**, you should choose the exact permitted target module name.

`--illegal-access` used to assist migration in earlier JDK releases, but in **Java 17** there is no longer an effective way to use it to enable deep reflection by default; do not rely on it to fix newer systems.

## 17. Recommended Test Matrix for Libraries and Plugin Frameworks

| Test scenario | Outcome to observe |
| --- | --- |
| Client compiled against public API v1, run with v1 | Call succeeds |
| Keep Client.class v1, replace Library.class v2 with reduced visibility | `IllegalAccessError` |
| Reflection calls a private method before suppressing access | `IllegalAccessException` |
| Reflection within the same module, valid trySetAccessible | Returns true; invoke can succeed |
| Named module exports without opens, calling private via invoke | `IllegalAccessException` |
| Named module exports without opens, calling setAccessible(true) | `InaccessibleObjectException` |
| Open package to the target module then call setAccessible | Succeeds; subsequent invoke works |
| Two classes in the same source package with different defining loaders | Does not automatically grant package-private access |
| Plugin fat JAR containing duplicated shared API | Check correct defining loader and identity |
| Runtime uses a different module path from the IDE | Check exports/opens/readability and launcher arguments |
| Framework reflects into JDK internals on Java 17 | Evaluate public API or narrow migration flag |
| Method body throws an exception via Method.invoke | `InvocationTargetException.getCause()` preserves the actual error |

These tests help distinguish **linkage errors, reflection access errors, and JPMS encapsulation errors** instead of blindly patching an exception message.

## 18. Self-Check

**1. Is `IllegalAccessError` a checked exception?** No; it is an Error under the IncompatibleClassChangeError/LinkageError branch.

**2. Why does code run with lib v1 yet fail when only swapping in lib v2?** The client bytecode was compiled against the v1 access contract, whereas the v2 runtime definition has incompatible visibility.

**3. Which APIs does `IllegalAccessException` commonly come from?** Method.invoke, Field.get/set, Constructor.newInstance, and certain corresponding lookup APIs when the caller lacks permission.

**4. Where does `InaccessibleObjectException` typically occur?** In AccessibleObject.setAccessible(true) when suppression is denied, for example when a named module package does not have opens to the caller.

**5. Does `getDeclaredMethod` finding a private method mean it can be invoked?** No; metadata lookup and invocation access are two different operations.

**6. Does `trySetAccessible()` returning false help bypass access checks?** No. False indicates that suppression is not permitted.

**7. Is `exports p` enough to call a private method in p via deep reflection?** Normally no; appropriate opens is required, or the caller must have valid permissions according to API rules.

**8. Does `--add-opens` automatically fix an IllegalAccessError caused by a direct call to a package-private method?** No; it does not turn private/package-private into public for direct bytecode access.

**9. Are two Classes in the same source package defined by two different loaders automatically in the same runtime package?** No.

**10. How does InvocationTargetException differ from IllegalAccessException?** The former wraps an exception thrown **inside the invoked method**; the latter prevents invocation because the caller lacks permission.

**11. If you encounter an access error when running on Java 17 that did not happen on Java 8, what should you check?** JPMS strong encapsulation, opens/exports, the JDK runtime, and framework reflection into JDK internals.

**12. Does `catch (Exception)` catch IllegalAccessError?** No, because IllegalAccessError is an Error.

**13. When a class has a public method but the top-level class is package-private, can a caller in another package always call it?** No; access to the declaring class is also checked.

**14. Should you open every package to all unnamed modules for debugging convenience?** No; update the code/library, choose a public API, and open only the necessary scope.

**15. What should you identify in a stack trace involving a custom class loader?** The binary caller/target, defining loaders, module membership, dependency versions, and runtime package identity.

## 19. Standard References

- Java 17, **IllegalAccessError**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/IllegalAccessError.html
- Java 17, **IllegalAccessException**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/IllegalAccessException.html
- Java 17, **InaccessibleObjectException**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/InaccessibleObjectException.html
- Java 17, **AccessibleObject** — `setAccessible`, `trySetAccessible`, `canAccess`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AccessibleObject.html
- Java 17, **Method** — `invoke` and checked access errors: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Method.html
- Java 17, **Module** — readability, exported/open packages: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Module.html
- Java 17, **ClassLoader** — defining loaders and delegation: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html
- JLS 17 `6.6 — Access Control: https://docs.oracle.com/javase/specs/jls/se17/html/jls-6.html#jls-6.6
- JVMS 17 `5.4.4 — Access Control: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.4.4
- JLS 17 `13 — Binary Compatibility: https://docs.oracle.com/javase/specs/jls/se17/html/jls-13.html
- Oracle JDK 17 Migration Guide — Strong Encapsulation: https://docs.oracle.com/en/java/javase/17/migrate/migrating-jdk-8-later-jdk-releases.html

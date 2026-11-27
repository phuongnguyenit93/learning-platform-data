# privateLookupIn and Readability / Package-Opening Conditions in Java 17

**Topic:** Java 17 → Reflection and Access  
**Focus:** Using `MethodHandles.privateLookupIn` to create a `Lookup` with private access to a target class; understanding why the caller module must read the target module, why the target package must be opened, and how to configure `module-info.java` or launcher options to grant the proper permissions.

Since Java 9, the Java Platform Module System (JPMS) controls which modules read which modules and which packages are exported or opened. Java 17 continues to enforce strong encapsulation: external code is not granted deep access to non-public members of another module by default.

`MethodHandles.privateLookupIn(targetClass, callerLookup)` is the standard API for creating a `MethodHandles.Lookup` on a target class that can access private members when lookup permission and module conditions are satisfied. This API was introduced in Java 9, continues to apply in Java 17, and requires no preview flags.

Core points of this lesson:

- `exports` permits ordinary access to public types in a package.
- `opens` permits deep reflection into types and members in a package.
- For two different modules, the caller's module must **read** the module containing the target class; the target module must **open the package containing the target class** to the caller's module.
- The passed `Lookup` object must have both `PRIVATE` and `MODULE` permissions, i.e., full privilege access.

## 1. What is MethodHandles.Lookup?

`MethodHandles.Lookup` is an object representing the **access permissions** of a Java class. It is used to look up and create `MethodHandle` or `VarHandle` instances for methods, constructors, and fields.

Example:

~~~java
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodHandles.Lookup;

public class LookupIntro {
    public static void main(String[] args) {
        Lookup lookup = MethodHandles.lookup();

        System.out.println(lookup.lookupClass());
        System.out.println(lookup.lookupModes());
    }
}
~~~

`MethodHandles.lookup()` is a caller-sensitive method. The returned object represents the class that actually calls this method. When invoked directly inside `LookupIntro`, `lookup.lookupClass()` is `LookupIntro.class`.

A `Lookup` is not a global access right. It is bound to a specific class and can only create method handles for members that the class is permitted to access under its current access modes.

### 1.1. Important lookup modes

`Lookup.lookupModes()` returns a bit mask representing the permissions the lookup currently holds.

| Mode | Meaning |
| --- | --- |
| `PUBLIC` | Access public members according to module rules. |
| `PRIVATE` | Access private members of the lookup class and appropriate nestmates. |
| `PROTECTED` | Access protected members according to Java rules. |
| `PACKAGE` | Access package-private members within the appropriate runtime package. |
| `MODULE` | Confirms the lookup was created in the lookup class's module; supports cross-module permission checks. |
| `ORIGINAL` | Original lookup created by the VM for the caller; has certain special capabilities. |
| `UNCONDITIONAL` | Mode of a public lookup, allowing access to unconditionally exported public APIs without relying on normal readability. |

A fresh lookup obtained from `MethodHandles.lookup()` in normal Java code has the full set of modes appropriate for the caller class, including `PRIVATE` and `MODULE`. Conversely, `MethodHandles.publicLookup()` only has minimal public access; it is insufficient for calling `privateLookupIn`.

You can check the two required permissions:

~~~java
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodHandles.Lookup;

Lookup lookup = MethodHandles.lookup();

boolean hasPrivate =
    (lookup.lookupModes() & Lookup.PRIVATE) != 0;
boolean hasModule =
    (lookup.lookupModes() & Lookup.MODULE) != 0;

System.out.println("PRIVATE: " + hasPrivate);
System.out.println("MODULE:  " + hasModule);
~~~

To call `privateLookupIn`, both values must be `true`. Java 17 also has the `lookup.hasFullPrivilegeAccess()` method to check the full privilege access condition directly.

### 1.2. Lookup is a capability

A `Lookup` with private access can create method handles that access private members. Once a method handle has been successfully created, invoking the handle does not repeat all the access checks performed at handle creation time.

Therefore, do not casually share a high-privilege `Lookup` or a private-access method handle with untrusted code. The recipient can use that capability to perform operations that the code creating the handle was permitted to do.

## 2. What is privateLookupIn used for?

Syntax:

~~~java
MethodHandles.Lookup privateLookup =
    MethodHandles.privateLookupIn(Target.class, callerLookup);
~~~

The method returns a new `Lookup` whose lookup class is `Target`. When access conditions are satisfied, the new lookup has private permission to create handles for private fields, methods, or constructors of the target class and eligible nestmates.

Example target class:

~~~java
package example;

public class Secret {
    private String message = "hidden";

    private String reveal() {
        return "message=" + message;
    }
}
~~~

If the caller has appropriate permissions:

~~~java
MethodHandles.Lookup privateLookup =
    MethodHandles.privateLookupIn(
        Secret.class,
        MethodHandles.lookup()
    );
~~~

`privateLookup` can be used to create a `VarHandle` for a private field or a `MethodHandle` for a private method. Obtaining the lookup does not automatically invoke methods or modify fields; the application must still create handles and explicitly execute operations.

### 2.1. Difference from Lookup.in

`Lookup.in(Target.class)` and `MethodHandles.privateLookupIn(Target.class, lookup)` are not the same:

| API | Purpose | Can increase private permissions? |
| --- | --- | --- |
| `lookup.in(Target.class)` | Switches the lookup class to another class, retaining at most the permissions the old lookup can still carry. | No. Permissions are only kept or reduced. |
| `MethodHandles.privateLookupIn(Target.class, lookup)` | Creates a lookup with private access to target after checking deep reflection and module conditions. | Yes, if the caller has sufficient permissions and the module/package permits. |

`Lookup.in` is not a way to bypass module access. If the target package is not open and the caller lacks the required permissions, changing the lookup class with `in` does not grant private access.

## 3. Required conditions to call privateLookupIn

According to the Java SE 17 API, the method checks the following conditions.

### 3.1. Caller lookup must have full privilege access

`callerLookup` must have both modes:

- `PRIVATE`: proves the caller lookup has private access for its lookup class.
- `MODULE`: proves the lookup was created in the lookup class's module, so Java can identify the caller module when checking readability and opens.

A lookup with only public access does not meet the requirement:

~~~java
MethodHandles.Lookup weakLookup = MethodHandles.publicLookup();

// Lacks PRIVATE and MODULE permissions.
// MethodHandles.privateLookupIn(Secret.class, weakLookup);
~~~

Normally, obtain the root lookup inside the framework class performing the operation:

~~~java
MethodHandles.Lookup callerLookup = MethodHandles.lookup();
~~~

If passing a lookup from a helper class, the caller module evaluated is the module containing **the passed object's lookup class**, not necessarily the module of the class calling the helper. Check the origin of the lookup rather than looking only at where `privateLookupIn` is invoked.

### 3.2. Target must be a valid class

`targetClass` must be an actual class. You cannot pass:

- Primitive types such as `int.class`.
- `void.class`.
- An array class such as `String[].class`.

These cases cause `IllegalArgumentException`. If either argument is `null`, the method throws `NullPointerException`.

### 3.3. If caller and target are in the same module

Let `M1` be the caller lookup's module and `M2` be the target class's module.

If `M1 == M2`, having a caller lookup with full privilege access satisfies the module condition. No separate `opens` declaration is needed for the target package, because caller and target reside in the same module.

~~~java
MethodHandles.Lookup privateLookup =
    MethodHandles.privateLookupIn(
        AnotherClassInSameModule.class,
        MethodHandles.lookup()
    );
~~~

Normal Java access rules still apply to obtaining the `Class` object and other lookup constraints, but there is no cross-module readability or package-openness check.

### 3.4. If caller and target are in different modules

When `M1 != M2`, **both** additional conditions are required:

1. `M1 reads M2`: the module containing the caller lookup must read the module containing the target class.
2. `M2 opens package(Target) to M1`: the module containing the target class must open the package containing the target to the caller module.

You can visualize it as:

~~~text
Module M1 (caller)                     Module M2 (target)
------------------                     ------------------
Framework / Inspector                  Model / Secret
        |                                      |
        |  1. M1 reads M2                      |
        |------------------------------------->|
        |                                      |
        |  2. M2 opens target package to M1    |
        |<-------------------------------------|
        |                                      |
        +---- privateLookupIn(Target.class) ---+
                       |
                       v
            Lookup with PRIVATE access
            on class Target
~~~

If either condition is missing, `privateLookupIn` throws `IllegalAccessException`.

## 4. Readability: the caller module must read the target module

In the caller's module descriptor, the `requires` directive typically establishes the reads relationship:

~~~java
module com.example.framework {
    requires com.example.model;
}
~~~

Here `com.example.framework` is `M1` and `com.example.model` is `M2`. The framework module reads the model module.

You can verify at runtime:

~~~java
Module callerModule = Inspector.class.getModule();
Module targetModule = Secret.class.getModule();

System.out.println(callerModule.canRead(targetModule));
~~~

The result must be `true` to satisfy the readability condition when the two modules differ.

### 4.1. Readability is not package openness

`requires` only handles module readability. It **does not open packages** and does not grant private access.

Example:

~~~java
module com.example.framework {
    requires com.example.model;
}
~~~

If the model module does not open the package containing `Secret` to the framework, `privateLookupIn` still fails even though `canRead` returns `true`.

Do not confuse:

- `requires` / `canRead`: does the caller read the target module?
- `exports` / `isExported`: is the package exported for ordinary access?
- `opens` / `isOpen`: is the package opened for deep reflection?

These are three related questions, but they do not substitute for one another.

### 4.2. Unnamed module

Code running on the classpath belongs to the unnamed module of its class loader. Per the `Module.canRead` API, the unnamed module reads all modules. However, if the target resides in a named module, the target package must still be opened to the unnamed module to perform cross-module deep reflection.

When opening from the launcher for classpath code, the target module typically uses `ALL-UNNAMED` in `--add-opens`.

## 5. Opens: the target module must open the package containing target

The `opens` directive in `module-info.java` allows other modules to perform deep reflection into the types and members of the opened package.

Target module example:

~~~java
module com.example.model {
    opens com.example.model.internal to com.example.framework;
}
~~~

This directive states that module `com.example.model` opens package `com.example.model.internal` to module `com.example.framework`.

If the target class is in another package, that exact package must be opened. Opening a package does not automatically open subpackages.

### 5.1. Qualified opens and unqualified opens

Two common forms:

**Opening to a specific module:**

~~~java
opens com.example.model.internal to com.example.framework;
~~~

This is `qualified opens`. Only the listed module receives deep reflection permission via this directive.

**Opening to all modules:**

~~~java
opens com.example.model.internal;
~~~

This is `unqualified opens`. The package is opened to all other modules. Its scope is broader, so if only one framework needs access, qualified opens is usually better.

### 5.2. Open module

You can declare:

~~~java
open module com.example.model {
}
~~~

An `open module` opens all packages of the module for deep reflection at runtime. Individual `opens` directives are not required.

Do not use `open module` just to solve a single private access case if you can open the specific package to the specific module. Opening the whole module makes the access scope broader than necessary.

### 5.3. Opens does not replace exports

`opens` serves runtime reflective access; it does not grant ordinary source-level access to the package's public types for code in another module.

If the caller needs to write `Secret.class` or import the public class `Secret` in source code, the package usually must also be exported to the caller:

~~~java
module com.example.model {
    exports com.example.model.domain to com.example.framework;
    opens com.example.model.domain to com.example.framework;
}
~~~

The two directives have distinct purposes:

- `exports` allows the caller to reference public APIs in the package.
- `opens` allows the caller to perform deep reflection into private members of classes in the package.

In another design, a framework might receive `Class<?>` from a plugin mechanism or load classes by name without directly importing the target type. In that case, exporting the package solely for a source-level reference is not necessary, though the package-opening requirement for deep reflection must still be satisfied.

## 6. Complete example with two named modules

This example has two modules:

- `com.example.model` contains a class with private fields and methods.
- `com.example.framework` reads the model module, has access to the public class, and has the package opened for private lookup.

### 6.1. Directory structure

~~~text
src/
  com.example.model/
    module-info.java
    com/example/model/domain/Secret.java
  com.example.framework/
    module-info.java
    com/example/framework/Inspector.java
~~~

### 6.2. The model module

File `src/com.example.model/module-info.java`:

~~~java
module com.example.model {
    exports com.example.model.domain to com.example.framework;
    opens com.example.model.domain to com.example.framework;
}
~~~

File `src/com.example.model/com/example/model/domain/Secret.java`:

~~~java
package com.example.model.domain;

public final class Secret {
    private String message = "classified";

    public Secret() {
    }

    private String reveal() {
        return "message=" + message;
    }
}
~~~

The `Secret` class and its public constructor are exported selectively to the framework so framework code can reference the type and instantiate it. The `message` field and `reveal()` method remain private. The `opens` directive lets the framework perform deep reflection on the package.

### 6.3. The framework module

File `src/com.example.framework/module-info.java`:

~~~java
module com.example.framework {
    requires com.example.model;
}
~~~

File `src/com.example.framework/com/example/framework/Inspector.java`:

~~~java
package com.example.framework;

import com.example.model.domain.Secret;

import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodHandles.Lookup;
import java.lang.invoke.VarHandle;
import java.lang.reflect.Method;

public class Inspector {
    public static void main(String[] args) throws Throwable {
        Secret secret = new Secret();

        // Lookup created inside module com.example.framework.
        Lookup callerLookup = MethodHandles.lookup();

        // Create a private lookup on a class in module com.example.model.
        Lookup privateLookup =
            MethodHandles.privateLookupIn(Secret.class, callerLookup);

        // Access private field using VarHandle.
        VarHandle messageHandle = privateLookup.findVarHandle(
            Secret.class,
            "message",
            String.class
        );

        System.out.println(messageHandle.get(secret));
        messageHandle.set(secret, "updated");

        // Create a MethodHandle from a private method found via reflection.
        Method revealMethod = Secret.class.getDeclaredMethod("reveal");
        MethodHandle revealHandle =
            privateLookup.unreflect(revealMethod);

        System.out.println((String) revealHandle.invoke(secret));
    }
}
~~~

### 6.4. Compile and run

From the root directory of the example:

~~~shell
javac --module-source-path src -d out -m com.example.model,com.example.framework
java --module-path out -m com.example.framework/com.example.framework.Inspector
~~~

Output:

~~~text
classified
message=updated
~~~

Explanation:

1. `requires com.example.model` creates readability from framework to model.
2. `exports ... to com.example.framework` lets the framework reference the public class `Secret` in source code.
3. `opens ... to com.example.framework` allows deep reflection and `privateLookupIn` to access private members.
4. `MethodHandles.lookup()` is called from `Inspector`, so the lookup class belongs to the framework module and has full privilege access.
5. `privateLookupIn` creates a lookup on `Secret`; that lookup is used to find the `VarHandle` and `MethodHandle`.

If you remove the `opens` directive while keeping `requires` and `exports`, the code can still compile, but the `privateLookupIn` call throws `IllegalAccessException` at runtime. This shows that exporting a public package is not enough for private access.

## 7. Using --add-opens when you cannot edit the module descriptor

Sometimes the target module belongs to a third-party library or the JDK, and the development team cannot change that module's `module-info.java`. The Java launcher supports the `--add-opens` option:

~~~shell
java --add-opens source.module/package.name=target.module ...
~~~

For the two modules above, opens can be granted from the command line:

~~~shell
java --add-opens com.example.model/com.example.model.domain=com.example.framework --module-path out -m com.example.framework/com.example.framework.Inspector
~~~

At that point, the `opens` directive in the model module's descriptor can be removed to test the permission granted from the launcher. The framework module still needs to read the model module, for instance via `requires com.example.model`.

### 7.1. Opening to the classpath: ALL-UNNAMED

If the caller runs on the classpath, the caller code belongs to the unnamed module. Syntax:

~~~shell
java --add-opens java.base/java.lang=ALL-UNNAMED -jar app.jar
~~~

The example above opens package `java.lang` of module `java.base` to all unnamed modules. This is a fairly broad permission; only use it when you have identified which library needs access and have a clear migration plan.

### 7.2. --add-opens is not a long-term substitute

`--add-opens` is a runtime package-opening configuration. It does not:

- Turn private members into public members.
- Change Java's source-level access control.
- Turn internal APIs into supported APIs.
- Replace module readability if the caller module does not already read the target module.
- Fix code calling `privateLookupIn` with an insufficiently privileged lookup.

If you can edit the descriptor of the module owning the package, qualified `opens` usually expresses the contract more clearly. If the dependency comes from an external library, upgrade the library or work with the vendor to reduce the need to open packages.

## 8. What happens to the returned Lookup?

The permissions of the returned lookup depend on whether caller and target are in the same module.

| Case | Returned lookup |
| --- | --- |
| Target in same module as caller | Lookup on target has full privilege access. |
| Target in different module, readability and opens satisfied | Lookup on target has private access, but lacks `MODULE` mode; it remembers the original lookup class as the previous lookup class. |

### 8.1. Cross-module lookup loses the MODULE mode

When `M1 != M2`, the returned lookup no longer has `MODULE` access. This has security significance: a lookup that has crossed into another module cannot continue to be used as an originating lookup to request deep reflection into a third module.

Example:

~~~java
Lookup original = MethodHandles.lookup();

Lookup targetLookup =
    MethodHandles.privateLookupIn(Target.class, original);

System.out.println(targetLookup.lookupClass());
System.out.println(targetLookup.lookupModes());
System.out.println(targetLookup.hasFullPrivilegeAccess());
~~~

If `Target` is in another module, `lookupClass()` is `Target.class`; the lookup has private access, yet `hasFullPrivilegeAccess()` returns `false` because module access is gone.

### 8.2. Cannot use a cross-module lookup as caller for arbitrary chained privateLookupIn

Because a cross-module lookup has lost its `MODULE` mode, it no longer satisfies the full-privilege requirement for a subsequent `privateLookupIn` call.

If a framework needs private access across multiple different modules, each call must use an originating full-privilege lookup from an appropriate caller module, and the target module must open its package to that module. Do not pass around a cross-module lookup expecting it to transitively grant access to arbitrary modules.

### 8.3. Checking lookup modes in practice

~~~java
static void printLookupInfo(MethodHandles.Lookup lookup) {
    System.out.println("Lookup class: " + lookup.lookupClass().getName());
    System.out.println("Modes: " + lookup.lookupModes());
    System.out.println(
        "Full privilege: " + lookup.hasFullPrivilegeAccess()
    );
}
~~~

Use this information when debugging access permissions. A lookup may be able to create method handles for certain members while lacking sufficient privileges to perform another lookup hop.

## 9. Inspecting modules and packages with the Module API

Java provides runtime APIs to inspect module relationships:

~~~java
Module callerModule = Inspector.class.getModule();
Module targetModule = Secret.class.getModule();
String targetPackage = Secret.class.getPackageName();

System.out.println("Caller reads target: "
    + callerModule.canRead(targetModule));

System.out.println("Target opens package to caller: "
    + targetModule.isOpen(targetPackage, callerModule));

System.out.println("Target exports package to caller: "
    + targetModule.isExported(targetPackage, callerModule));
~~~

These checks help locate configuration issues:

- `canRead` checks readability.
- `isOpen(package, otherModule)` checks whether the package is open to the caller module.
- `isExported(package, otherModule)` checks whether the package is exported to the caller module.

Note: a package opened to another module is considered exported to that module at runtime under the `Module.isExported` contract. However, this does not mean `opens` and `exports` directives serve the same purpose in a module descriptor.

## 10. privateLookupIn and Core Reflection

`privateLookupIn` belongs to the Method Handles API. It is not a syntactic replacement for `Field.setAccessible(true)` or `Method.setAccessible(true)` in every situation.

| Mechanism | Output | How to use |
| --- | --- | --- |
| Core Reflection: `Field`, `Method`, `Constructor` | Reflection objects representing members | Call `trySetAccessible()`/`setAccessible(true)` when permitted, then use `get`, `set`, `invoke`, or `newInstance` respectively. |
| Method Handles: `privateLookupIn` | A privileged `Lookup` on target | Create `MethodHandle` or `VarHandle` for specific operations. |

Both mechanisms are subject to module control when performing deep access across module boundaries. `opens` is a critical condition for deep reflection; exporting a package alone does not grant private access.

Method Handles fit when you want a strongly typed handle and intend to reuse it. Core Reflection fits when working with traditional reflection metadata. Do not pick one API simply thinking it bypasses the module system.

## 11. Common errors and how to diagnose them

### 11.1. IllegalAccessException when calling privateLookupIn

Common causes:

- Caller lookup lacks `PRIVATE`.
- Caller lookup lacks `MODULE`.
- Caller module does not read target module.
- Target module does not open the package containing the target class to the caller module.

Check:

~~~java
Lookup caller = MethodHandles.lookup();
Module source = caller.lookupClass().getModule();
Module target = Target.class.getModule();
String packageName = Target.class.getPackageName();

System.out.println(caller.hasFullPrivilegeAccess());
System.out.println(source.canRead(target));
System.out.println(target.isOpen(packageName, source));
~~~

If target is in the same module as caller, cross-module read/open checks are unnecessary; focus on checking full privilege access and a valid target class.

### 11.2. Module is readable, but package is not open

For example, the framework module has:

~~~java
requires com.example.model;
~~~

but the model module only has:

~~~java
exports com.example.model.domain to com.example.framework;
~~~

The framework can use the package's public API, but cannot use `privateLookupIn` to access private fields/methods in that package. You need to add:

~~~java
opens com.example.model.domain to com.example.framework;
~~~

or grant the appropriate opens via the launcher for temporary runtime configuration.

### 11.3. Lookup obtained from publicLookup

The following does not meet the conditions:

~~~java
Lookup caller = MethodHandles.publicLookup();
Lookup privateLookup =
    MethodHandles.privateLookupIn(Target.class, caller);
~~~

`publicLookup` only has minimal public access. Create the root lookup in a trusted caller class using `MethodHandles.lookup()`.

### 11.4. Using Lookup.in and expecting private access

~~~java
Lookup lookup = MethodHandles.lookup().in(Target.class);
~~~

This is not a deep-reflection request. `in` does not escalate permissions; it can drop access modes when the lookup class changes package, nest, or module.

### 11.5. Package opened to the wrong module

The directive:

~~~java
opens com.example.model.internal to com.example.other;
~~~

does not open the package to `com.example.framework`. The target module name must match the module containing the actual lookup class. If a framework is split into multiple modules or the lookup is created in a helper module, verify which module actually owns the lookup.

### 11.6. Target class inaccessible from source

A package with `opens` only and no `exports` does not allow code in another module to import public classes from that package as a normal API. If caller code needs to write `Target.class`, the package must also be appropriately exported; otherwise, the `Class<?>` must be obtained through another explicitly designed loading/lookup mechanism.

## 12. Summary table of access conditions

| Caller lookup | Module relationship | Readability | Package opens | Outcome |
| --- | --- | --- | --- | --- |
| Has PRIVATE + MODULE | Same module | No cross-module check needed | No separate opens needed | Can create private lookup. |
| Has PRIVATE + MODULE | Different module | Yes | Yes, for the exact caller module | Can create private lookup. |
| Has PRIVATE + MODULE | Different module | No | Yes | Fails: missing readability. |
| Has PRIVATE + MODULE | Different module | Yes | No | Fails: package not opened. |
| PUBLIC only | Same or different module | Any | Any | Fails: caller lookup lacks full privilege access. |
| Has PRIVATE but lacks MODULE | Different module | Yes | Yes | Fails: caller lookup lacks full privilege access. |

When the two modules differ, **both** readability and package openness must be satisfied simultaneously. Neither condition substitutes for the other.

## 13. When to use opens, when to use exports?

| Need | Suitable directive |
| --- | --- |
| Other modules need to use public classes/members in a package | `exports` |
| Framework needs access to private fields/methods via reflection or Method Handles | `opens` |
| Need both importing public types and deep reflection on private members | `exports` and `opens` |
| Only one framework should be allowed deep reflection | Qualified `opens package to framework.module` |
| Framework runs on classpath, in the unnamed module | Can use `opens` to unnamed module or `--add-opens ...=ALL-UNNAMED` |
| All packages of the module need to be opened for reflection | `open module`, only when that broad scope is genuinely required |

Prefer opening only the needed packages and consuming modules. Opening an entire module or using `ALL-UNNAMED` can grant permissions to more code than necessary.

## 14. Launcher configuration example when target module is not under your control

Suppose library `com.vendor.model` contains package `com.vendor.model.internal`. Application module `com.example.app` needs to access private members in that package.

If the application already declares:

~~~java
module com.example.app {
    requires com.vendor.model;
}
~~~

You can try granting opens at runtime:

~~~shell
java --add-opens com.vendor.model/com.vendor.model.internal=com.example.app --module-path "mods;lib" -m com.example.app/com.example.app.Main
~~~

If the application runs on the classpath:

~~~shell
java --add-opens com.vendor.model/com.vendor.model.internal=ALL-UNNAMED -cp "app.jar;lib/*" com.example.app.Main
~~~

This configures runtime access for a specific package. Document clearly which library requires that permission, because depending on a library's private internals carries risk when the library is upgraded.

If the actual error is missing readability in a named module and you cannot edit the module descriptor, you can consider `--add-reads caller=target` during a transition period. However, if the application is under your control, declaring `requires` in the module descriptor expresses dependencies clearly and is easier to maintain.

## 15. Common mistakes

| Mistake | Cause | How to handle |
| --- | --- | --- |
| Declaring only `requires` and calling `privateLookupIn` | Readability does not open packages. | Add qualified `opens` on the target module. |
| Declaring only `exports` | Export is for public APIs, not deep reflection on private members. | Use `opens` for packages needing deep access. |
| Using `publicLookup()` as caller | Lacks PRIVATE and MODULE modes. | Obtain root lookup in caller class via `MethodHandles.lookup()`. |
| Using `Lookup.in` to request private permissions | `in` does not escalate lookup privileges. | Use `privateLookupIn` when all conditions are satisfied. |
| Opening package to the wrong module | Target module opens to the wrong consumer module. | Open the package to the module containing the actual lookup class. |
| Opening the entire module for one package | Deep reflection scope is too broad. | Use qualified `opens` for the specific package. |
| Thinking opening a package allows importing public classes | `opens` is a runtime deep reflection permission. | Export the package if source code needs to reference public types. |
| Using a cross-module lookup to open a third module | Returned lookup no longer has MODULE mode. | Create a proper originating lookup from a caller module with full privilege. |
| Sharing a private lookup with every plugin | Lookup is a capability that can create private-access handles. | Grant only to trusted code and restrict shared APIs. |
| Ignoring IllegalAccessException | Error indicates genuinely missing permissions. | Verify full privilege, canRead, and isOpen. |

## 16. Frequently asked questions

**Which Java version introduced `privateLookupIn`?**  
The API has existed since Java 9 and is used normally in Java 17.

**Are both `requires` and `opens` needed?**  
When caller and target are in two different named modules, both readability from caller to target and opens from target to caller are required. `requires` typically establishes readability; `opens` enables deep reflection.

**Is `exports` enough to read private fields?**  
No. `exports` grants ordinary access to public APIs; private access requires the package to be opened to the caller.

**Can `privateLookupIn` be called with `publicLookup()`?**  
No. The caller lookup must have both `PRIVATE` and `MODULE` access.

**Does the target class have to be public?**  
`privateLookupIn` itself does not require the target class to be public under the described module rules. However, if the caller wants to reference `Target.class` directly in source code of another module, the package/type must be accessible at compile time, typically via `exports`. If the package is only opened, another appropriate mechanism to obtain `Class<?>` is needed.

**If both classes are in the same module, is opens needed?**  
No cross-module opens is needed. The caller lookup must still have full privilege access.

**Can the returned lookup be used to call privateLookupIn for another module?**  
A lookup produced across modules lacks the `MODULE` mode, so it does not qualify as a caller for another `privateLookupIn` call.

**Can `--add-opens` fix a missing `requires`?**  
No. `--add-opens` opens packages; readability is a separate condition. For named modules, a corresponding reads relationship is required.

**Should an entire module be opened with `open module`?**  
Only when the design genuinely requires deep reflection across all packages. Usually, use qualified opens for the specific package and consuming module.

**Does `privateLookupIn` invoke private methods itself?**  
No. It creates a privileged `Lookup`. You then use that lookup to create a `MethodHandle` or `VarHandle` before invoking, reading, or writing.

## 17. Official references

- [Java SE 17 API — MethodHandles.privateLookupIn](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.html#privateLookupIn(java.lang.Class,java.lang.invoke.MethodHandles.Lookup)): conditions for full privilege, readability, opens, and access modes of the returned lookup.
- [Java SE 17 API — MethodHandles.Lookup](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html): lookup modes, full privilege access, cross-module lookups, and method-handle creation methods.
- [Java SE 17 API — Module](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Module.html): `canRead`, `isOpen`, `isExported`, `addOpens`, and module relationships.
- [Java SE 17 API — ModuleDescriptor](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/module/ModuleDescriptor.html): descriptions of `requires`, `exports`, `opens`, and open modules.
- [JEP 261 — Module System](https://openjdk.org/jeps/261): module system design, exports, opens, and cross-module access permissions.
- [JEP 403 — Strongly Encapsulate JDK Internals](https://openjdk.org/jeps/403): context for strong encapsulation enforced in Java 17.
- [The java Command — Java SE 17 Tool Specifications](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): launcher syntax for `--add-opens` and `--add-reads`.

**Practical rule:** Use `MethodHandles.privateLookupIn` when you genuinely need to create a private-access method handle or var handle. The caller lookup must have `PRIVATE` and `MODULE`; if the target is in another module, the caller must read that module and the target package must be opened to the caller. Use qualified `opens` to limit permissions, and only add `exports` when the caller needs ordinary access to public types.

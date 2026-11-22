# Class.forName(Module, name) and When a Class Is Not Found

## 1. Problem to Solve

In Java 9+ (including Java 17 and Java 21), in addition to the familiar overloads of `Class.forName`, Java provides:

~~~java
public static Class<?> forName(Module module, String name)
~~~

This is an API for **looking up a class within a specific `Module`**, suitable when an application needs to work with the **Java Platform Module System (JPMS)**. It has two differences that are especially easy to confuse:

- **Class not found in the specified module → returns `null`.** This is **not** the usual path that throws `ClassNotFoundException` like `Class.forName(String)` or `Class.forName(String, boolean, ClassLoader)`.
- **Does not automatically link or initialize the class.** According to this overload's contract, the method attempts to **locate/load** the class or interface, **without linking the class and without running the class initializer**.

Besides the case where no class definition actually exists, `null` can also be returned when the class name belongs to **another module**, even in cases where the requested module's loader can load that class. Therefore, from `result == null`, you **cannot uniquely infer** that the bytecode or JAR is missing.

### What You Will Learn

1. Understand the exact meaning of the two parameters `Module module` and `String name`.
2. Distinguish between the **right module**, the **wrong module**, and **no class with that name**.
3. Handle `null` safely, avoiding a `NullPointerException` caused by immediately calling a method on the result.
4. Distinguish the `Module`-based overload from the name- and `ClassLoader`-based overloads.
5. Explain why finding a `Class<?>` **does not prove** that the class has been linked, initialized, or permitted to be accessed.
6. Compile and run a Java 17+ JPMS example verifying all four cases: found, missing name, wrong module, and not triggering initialization.

## 2. Meaning of the API and Its Parameters

~~~java
Class<?> result = Class.forName(module, "com.example.MyService");
~~~

- `module` is a **`java.lang.Module` object**, not a module name as a `String`. It can be obtained from `SomeClass.class.getModule()` or from `ModuleLayer.findModule(...)` after the module has been resolved.
- `name` is the **binary name** of the class/interface to look up, for example `"java.lang.String"` or `"com.example.Outer$Inner"` for a nested class.
- The result is of type `Class<?>` if the name belongs to a class inside the requested module and locating/loading it succeeds.
- The result is `null` if **the class cannot be found in the specified module**.
- The method was introduced in **Java 9**.

Understand "looking up in a module" as **the boundary that determines the return value**; a single loader can define multiple named modules, or one named module and one unnamed module. Merely passing the right loader is not enough to determine which module a class belongs to.

### Module, Package, ClassLoader, and Class Are Four Different Things

~~~text
ModuleLayer
  └── Module "shop.api"
       ├── package "shop.api"
       │    └── class "shop.api.Service"
       └── maps to a defining ClassLoader

Class.forName(module, "shop.api.Service")
    │
    ├── class definition belongs to the right module?  -> Class<?>
    └── no class in the right module?                  -> null
~~~

A `Module` with a name is a **named module**. An ordinary class on the classpath belongs to the **unnamed module** of its defining loader. The API takes the `Module` object itself and applies to the matching module, rather than just taking a module name on the module path.

With a named module, start from the actual information:

~~~java
Module actual = SomeType.class.getModule();
System.out.println(actual.getName());  // module name, or null if unnamed
System.out.println(actual.isNamed());   // true for a named module
~~~

The two lines are **illustrative code inside a method**; not yet a standalone runnable program.

## 3. Cases That Return `null`

### 3.1. The Class Name Actually Does Not Exist in the Module

~~~java
Module base = String.class.getModule(); // java.base

Class<?> missing =
        Class.forName(base, "java.lang.NoSuchType");

System.out.println(missing == null);    // true
~~~

This differs from:

~~~java
Class.forName("java.lang.NoSuchType");
~~~

The single-parameter overload above will throw `ClassNotFoundException` (if there is no class with that name and no other error occurs).

When using the module-based overload, **`null` is a valid return value to handle**, not an exception to catch.

### 3.2. The Class Exists but Resides in Another Module

Example:

~~~java
Module base = String.class.getModule(); // java.base
Class<?> other = Class.forName(
        base, "java.util.logging.Logger");
System.out.println(other == null); // true
~~~

`java.util.logging.Logger` is a real class, but it belongs to **module `java.logging`**, not `java.base`. Therefore, the result is `null` in the standard Java configuration of the example.

If you pass the right module:

~~~java
Module logging = java.util.logging.Logger.class.getModule();
Class<?> found = Class.forName(
        logging, "java.util.logging.Logger");
System.out.println(found == java.util.logging.Logger.class); // true
~~~

**A subtle point of the contract:** if the ClassLoader assigned to module `M` also defines other modules, the method may **successfully load** a class in another module and still return `null` because that class **does not belong to `M`**. A `null` result does not necessarily mean the loader could not find the bytecode.

Therefore, you should not use:

~~~java
if (Class.forName(requestedModule, name) == null) {
    // NOT sufficient evidence to assert "JAR does not exist"
}
~~~

The snippet above is an example of **invalid reasoning**, not a standalone program. You must verify the right module, binary name, module resolution, and class sources before drawing a conclusion.

### 3.3. Name Not in the Expected Format or Not a Supported Class

The API requires the **binary name** of a class/interface, not a file path, not a package name, and it does not support array types.

| `name` | Remarks |
|---|---|
| `"java.lang.String"` | Valid binary name for the `String` class; must be paired with the `java.base` module |
| `"java.util.Map$Entry"` | Binary name of the nested interface `Entry` |
| `"java.util.Map.Entry"` | Nested source/canonical name, **not** the correct binary name of `Entry` |
| `"java/lang/String.class"` | Class resource path, not a binary name |
| `"[Ljava.lang.String;"` | Descriptor/array name; the `Module` overload **does not support array types** |
| `"int"` or `"void"` | Do not use this API to obtain primitive/void `Class` objects |

To obtain the `Class` of a primitive/void type, use `int.class` or `void.class`. To obtain the class of an array, use `String[].class` or a loader-based API that supports array-name syntax. You should not treat `Class.forName(module, "[Ljava.lang.String;")` as a valid alternative API for array classes.

### 3.4. When the Module Has Not Been Resolved

A modular JAR present on `--module-path` is not necessarily **resolved** into the boot layer or a custom layer. If you do not yet have the corresponding `Module` object, the issue to solve first is **module resolution**, not calling `Class.forName(module, name)`.

Example of checking whether a module was selected:

~~~java
Module module = ModuleLayer.boot()
        .findModule("shop.api")
        .orElse(null);
~~~

If `module == null`, that indicates **the module was not found by name within the scope of this layer lookup**. It does not prove that the `shop.api` JAR does not exist on disk. You need to check the module path, root modules, `requires`, and `Configuration`.

**Important:** do not call `Class.forName(null, name)`. The module-based overload will throw a `NullPointerException` if `module` or `name` is `null`.

## 4. No Linking and No Initialization: Exact Meaning

### 4.1. Distinguishing the Phases

- **Loading:** finding and defining the runtime representation of a class/interface.
- **Linking:** verification, preparation, and resolution as specified by the JVM.
- **Initialization:** running the class initializer, including the corresponding `static` expressions and blocks.

According to the Java SE 17/21 `Class` Javadoc, the overload:

~~~java
Class.forName(module, binaryName)
~~~

**attempts to locate/load**, **does not link**, and **does not run the class initializer**. This is a statement about the **method's contract**; it is not a guarantee that the class has never been processed further by the JVM due to other independent operations.

Comparing the overloads:

| API | Requested Scope | When Not Found | Linking and Initialization |
|---|---|---|---|
| `Class.forName(Module, String)` | Class **belonging to the specified module** | **Returns `null`** | Does not automatically link, does not run initializer |
| `Class.forName(String)` | According to the caller's defining loader in typical cases | **`ClassNotFoundException`** | Requests initialization if needed; entails linking |
| `Class.forName(String, false, ClassLoader)` | According to the specified loader | **`ClassNotFoundException`** | Does not request initialization; may still load/link per the overload's contract |
| `Class.forName(String, true, ClassLoader)` | According to the specified loader | **`ClassNotFoundException`** | Requests initialization |
| `MyType.class` | Class literal of a compile-time known type | No "not found" path like APIs taking a String name | Does not automatically request initialization of `MyType` |

**Do not overgeneralize:** "`Class.forName(Module,String)` does not link" does not mean every `Class.forName` overload skips linking. You must read the exact documentation section for the overload you are using.

### 4.2. Why Doesn't `static` Run?

~~~java
class InitMarker {
    static {
        System.out.println("INITIALIZED");
    }
}
~~~

If a call to `Class.forName(module, "some.package.InitMarker")` returns a `Class<?>`, that call alone **does not** cause the line `INITIALIZED` to be printed. If subsequent code **reads a nonconstant static field**, **calls a static method**, or **creates an instance** of the uninitialized class, the `static` block can run at that later point.

**Inference warning:** not seeing `INITIALIZED` does not prove the class has not been loaded. Conversely, having a `Class<?>` does not mean the initializer has run. The standalone example in Section 6 is designed to observe this ordering.

## 5. "Returning null" Does Not Mean All Failures Are Turned Into null

This is an important distinction to make when writing accurate production code. `Class.forName(Module, String)` returns `null` **when the requested class cannot be found**. However, the Javadoc also specifies distinct exceptions/errors:

| Situation | Behavior |
|---|---|
| Class/interface not found in the right module | `null` |
| A class with the same name is loaded by the loader but belongs to another module | `null` |
| Parameter `module == null` or `name == null` | `NullPointerException` |
| Failure related to class loading/linkage per the API contract | May throw `LinkageError` |
| Access denied by a security check mechanism (when applicable) | May throw `SecurityException` |

Therefore, the following handling is **wrong** because it assumes every failure produces `null`:

~~~java
Class<?> result = Class.forName(module, name);
if (result == null) {
    System.out.println("Everything that can go wrong happened here");
}
~~~

In a real application:

1. **Validate the inputs** `module` and `name` according to the application contract.
2. **Handle `null`** as the case where the class was not found in the specified module.
3. **Do not swallow `LinkageError`** or system errors arbitrarily; log the details and handle them under a separate policy since they represent a different category of failure.
4. If a security policy applies, do not conflate `SecurityException` with "the module does not have the class".

The table above describes **behavior defined by the Javadoc**; an application will not necessarily encounter all of those cases during normal runtime.

## 6. Standalone Runnable Java 17+ Example: Found, Not Found, Wrong Module, Not Yet Initialized

We create a **named module `lookup.demo`** containing a `Target` class with a `static` block that prints a message. The program attempts to look up `Target` in the right module, look up a nonexistent class, look up a class belonging to another module, and only at the end explicitly triggers initialization of `Target`.

### 6.1. Directory Tree

~~~text
project/
  src/
    lookup.demo/
      module-info.java
      lesson/
        lookup/
          Main.java
          Target.java
  mods/
    lookup.demo/           # output directory after compilation
~~~

### 6.2. File `src/lookup.demo/module-info.java`

~~~java
module lookup.demo {
    requires java.logging;
}
~~~

The `lookup.demo` module declares the `requires java.logging;` dependency so that the compiler and runtime can reference `java.util.logging.Logger`. This module **does not export** the `lesson.lookup` package; in practice, it is still possible to obtain the `Class<?>` of a class in the module, because the `forName(Module,String)` overload does not check the caller's accessibility to the class.

### 6.3. File `src/lookup.demo/lesson/lookup/Target.java`

~~~java
package lesson.lookup;

final class Target {
    static {
        System.out.println("TARGET_INITIALIZED");
    }

    static int VALUE = 7;
}
~~~

`Target` is a **package-private** class. The `VALUE` field is `static` and not `final`, so reading it for the first time will trigger initialization of `Target` if it has not yet occurred. The `static` block is used to observe when initialization happens.

### 6.4. File `src/lookup.demo/lesson/lookup/Main.java`

~~~java
package lesson.lookup;

public class Main {
    public static void main(String[] args) {
        Module own = Main.class.getModule();
        Module logging = java.util.logging.Logger.class.getModule();

        System.out.println("module=" + own.getName());

        System.out.println("found="
                + (Class.forName(own, "lesson.lookup.Target") == Target.class));

        System.out.println("missing="
                + (Class.forName(own, "lesson.lookup.Missing") == null));

        System.out.println("wrongModule="
                + (Class.forName(own, "java.util.logging.Logger") == null));

        System.out.println("correctModule="
                + (Class.forName(logging, "java.util.logging.Logger")
                    == java.util.logging.Logger.class));

        System.out.println("arrayUnsupported="
                + (Class.forName(own, "[Llesson.lookup.Target;") == null));

        System.out.println("beforeInitializer");
        System.out.println("value=" + Target.VALUE);
    }
}
~~~

### 6.5. Compiling and Running

From the `project` directory, using JDK 17 or later:

~~~sh
javac --release 17 -d mods/lookup.demo src/lookup.demo/module-info.java src/lookup.demo/lesson/lookup/Main.java src/lookup.demo/lesson/lookup/Target.java
java --module-path mods -m lookup.demo/lesson.lookup.Main
~~~

The commands above compile into an unpacked module (exploded module) in `mods/lookup.demo`, then launch the `lesson.lookup.Main` class belonging to the `lookup.demo` module. Gradle or Maven is not required.

**Exact stdout:**

~~~text
module=lookup.demo
found=true
missing=true
wrongModule=true
correctModule=true
arrayUnsupported=true
beforeInitializer
TARGET_INITIALIZED
value=7
~~~

### 6.6. Reading the Output in Order

| Line | Cause | Conclusion |
|---|---|---|
| `module=lookup.demo` | `Main.class.getModule()` | The current module is named `lookup.demo` |
| `found=true` | Look up `Target` in the right module; compare with `Target.class` | Obtains the `Class<?>` from the right module, yet `Target` has not had its initializer run by this operation |
| `missing=true` | `lesson.lookup.Missing` does not exist in the module | The result is `null`, not `ClassNotFoundException` |
| `wrongModule=true` | `Logger` belongs to `java.logging`, not `lookup.demo` | The class **actually exists** but the requested module is wrong, so it still returns `null` |
| `correctModule=true` | Obtain `Logger`'s module and look it up again | The right module returns the right `Class<?>` |
| `arrayUnsupported=true` | Pass the array type name `[Llesson.lookup.Target;` | The module-based overload does not support array classes |
| `beforeInitializer` | Observation marker | No `TARGET_INITIALIZED` line has appeared yet |
| `TARGET_INITIALIZED` | Read nonconstant `Target.VALUE` | Only now does initialization of `Target` take place |
| `value=7` | Value of the field after initialization | Confirms valid access to the value |

**Notably:** the `Target` class is not `public`, yet the method still returns its `Class<?>`. This shows that **locating metadata** does not automatically determine accessibility of a member/class from arbitrary callers. Reflection and access across named module boundaries also have their own rules.

### 6.7. Modification Exercises

1. Change `"lesson.lookup.Target"` to `"lesson.lookup.NoTarget"` in the first lookup: `Class.forName(own, ...)` returns `null`, while the comparison with `Target.class` remains valid.
2. Change `own` in the `Target` lookup to `logging`: you get `null` even though the `Target` name and bytecode are valid, because the wrong module was specified.
3. Remove the line `System.out.println("value=" + Target.VALUE);`: if there is no other active use, the `TARGET_INITIALIZED` line **does not appear**.
4. Switch the overload to `Class.forName("lesson.lookup.Target")` before the `beforeInitializer` line: the single-parameter overload will request initialization; the `TARGET_INITIALIZED` line will appear earlier.
5. Run the test in a **fresh JVM** after each variation, because the initializer runs only once per initialized class definition.

## 7. Comparing with `Class.forName(String, boolean, ClassLoader)`

If the code only has a `ClassLoader` instead of a `Module`:

~~~java
ClassLoader loader = Main.class.getClassLoader();
Class<?> found = Class.forName(
        "lesson.lookup.Target", false, loader);
~~~

The snippet above is **illustrative code** inside the `lookup.demo` module, with `Main` belonging to that module.

Key differences to understand:

- **The loader-based overload** `Class.forName(name, false, loader)` looks up via the loader. If not found, it throws **`ClassNotFoundException`**, which must be caught or declared with `throws`.
- **The module-based overload** `Class.forName(module, name)` looks up a class in the right module and returns **`null`** if that class does not exist in the module. It does not declare `ClassNotFoundException` in its signature.
- **The loader-based overload** has a boolean `initialize` parameter to choose whether to request initialization; **the module-based overload has no boolean parameter** and by contract **does not initialize**.
- **The module-based overload** also has a limitation regarding array classes; the loader-based overload supports array name forms documented by the API.
- A loader that defines multiple named modules may return a class looked up with the **loader-based overload**, whereas the **module-based overload** returns `null` if the class is in a different module.

### Code Pattern for Safe Result Handling

In a flow that needs to look up an optional class in an already resolved module:

~~~java
static Class<?> findOptionalClass(Module module, String binaryName) {
    java.util.Objects.requireNonNull(module, "module");
    java.util.Objects.requireNonNull(binaryName, "binaryName");
    return Class.forName(module, binaryName);
}
~~~

This is an **illustrative method** that can be placed in a utility class. The caller handles the result:

~~~java
Class<?> type = findOptionalClass(module, "com.example.Plugin");
if (type == null) {
    System.out.println("Module này không cung cấp lớp yêu cầu");
} else {
    System.out.println(type.getName());
}
~~~

This pattern does not automatically create an instance and does not guarantee reflective access rights. If the class needs to be instantiated/invoked, the next steps must separately consider: constructors, JPMS access permissions, exceptions thrown by the initializer, and validity of the shared API.

**Do not treat `null` as proof of a "missing file".** In debugging tools, you should also log `module.getName()` or an appropriate module identifier, `binaryName`, the relevant layer/loader, and the list of resolved modules (if available).

## 8. Common Mistakes and Misconceptions

### "`forName` always throws `ClassNotFoundException` when a class is not found."

False. Only the name/loader overloads have a contract to throw that checked exception when a class is not found. **The `(Module,String)` overload returns `null`** when the class is not found in the specified module.

### "If a class with that name exists somewhere on the classpath/module path, the overload must return a Class."

False. The specified module is an essential part of the lookup. A class belonging to another module can cause the result to be `null` even though the bytecode exists.

### "Since it does not throw `ClassNotFoundException`, no other exceptions can occur."

False. `NullPointerException` for null arguments, `LinkageError` in loading/linkage failure cases, and `SecurityException` when relevant security conditions are not met can still occur according to the Javadoc.

### "Receiving a `Class<?>` means the class has already run `static {}`."

False. `Class.forName(Module,String)` does not trigger the initializer. To verify this, place a log statement in a `static` block and perform an active-use operation afterward.

### "This API is identical to `Class.forName(name, false, loader)` in every respect."

False. They differ in **unit of scope** (module vs. loader), **result when the class is missing** (null vs. checked exception), **linking**, and **array type support**.

### "Using `com.example.Outer.Inner` is the correct name for a nested class."

Typically false for an actual nested class. The binary name must use `$`, for example `com.example.Outer$Inner`. `.` separates packages and the top-level class name; it does not replace the binary name rule for nested classes.

### "If `Class.forName(module, name)` returns a Class, the caller is guaranteed to have access to the class/methods."

False. The Javadoc explicitly states that this overload **does not check class accessibility with respect to the caller**. `exports`, `opens`, readability, Java visibility rules, and reflection checks can affect subsequent usage.

### "Specifying a named `Module` automatically resolves all JARs on the module path."

False. A `Module` object is bound to a module already represented in the corresponding runtime configuration. Module resolution/layer construction happens as a separate step; `Class.forName` does not replace that process.

### "Returning `null` definitely means no class was loaded."

False. A module's loader can load a class belonging to another module and the overload will still return `null` because the class does not belong to the requested module. You must distinguish between the lookup/loading effect and the condition that the result matches the right module.

## 9. Diagnostic Procedure When the Result Is `null`

When you encounter `Class<?> candidate = Class.forName(module, name);` and `candidate == null`:

1. **Check `name`:** is it the right binary name, with the right casing and nested-class `$`? Did you accidentally pass an array descriptor or a `.class` path?
2. **Check the actual `module`:** print `module.getName()` and `module.isNamed()`; if the module was obtained from `Class.getModule()`, ensure it is the right "anchor" class for the context.
3. **Check which module the class belongs to:** for a class already known to the application, inspect `KnownType.class.getModule()`; for a plugin/dynamic module, check the descriptor, packages, and module source.
4. **Check resolution:** has the named module been resolved in the boot layer or the appropriate child `ModuleLayer`? Having the file on the module path is not enough.
5. **Check loader mapping:** inspect `module.getClassLoader()`, or `ModuleLayer.findLoader(name)` if appropriate; distinguish which modules are defined by which loader.
6. **If the lookup succeeds but you cannot invoke a member:** check Java visibility, readability, `exports`/`opens`, and reflection conditions, rather than changing the lookup that already succeeded.
7. **If an error is actually thrown:** record the original exception/error/cause; do not force every failure into the `null` branch.

### Symptom Comparison

| Symptom | First Direction to Check |
|---|---|
| `Class.forName(module, name) == null` | Name, right module, module resolution; do not immediately conclude a missing JAR |
| `Class.forName(name)` throws `ClassNotFoundException` | Loader performing the lookup, binary name, classpath/module path |
| `NullPointerException` from the module-based overload | Was `module` or `name` passed as null? |
| `LinkageError` | Class-file/definition/dependency and linkage errors; log the actual cause |
| Found `Class<?>` but subsequent operation fails with an access error | JPMS `requires`/`exports`/`opens` rules and Java access rules |
| Obtained `Class<?>` but no `static` log appears | This is normal: the module-based overload does not initialize |
| Plugin finds a class with the same name but wrong type/loader | Defining loader, module membership, and runtime type identity |

## 10. Self-Check Questions

1. Which Java version introduced `Class.forName(Module,String)`? What do its two parameters mean?
2. If the class is not in the passed-in module, what is the default result?
3. Does `Class.forName(module, "foo.Bar") == null` prove that the JAR containing `foo.Bar` does not exist? Why or why not?
4. Distinguish `ClassNotFoundException` and the `null` return value across the two `Class.forName` overloads.
5. Why does `Class.forName(module, name)` returning a `Class<?>` not prove that the class has undergone initialization?
6. According to the Javadoc, does this overload automatically link the class? Is the `Class.forName(name, false, loader)` overload identical in that respect?
7. In the `lookup.demo` example, why is `wrongModule=true` while `correctModule=true`?
8. Why is `Class.forName(own, "[Llesson.lookup.Target;")` not a supported way to obtain an array class?
9. Why can `Class<?>` still be obtained from the module-based method even though `Target` is package-private?
10. If you pass `null` as `Module` or `name`, does the API return null or throw an error—and which kind?
11. When might `SecurityException` or `LinkageError` be a separate diagnostic path instead of handling the null branch?
12. If a class belongs to another module defined by the same loader, can the module-based overload return null?

**Completion criteria:** run the Java 17+ example successfully, fully explain the eight stdout lines, distinguish the "missing class" case from the "class belongs to another module" case, and properly handle the two result categories **`Class<?>` or `null`** along with the distinct documented errors.

## 11. Official Documentation

- [Java SE 21 — `Class.forName(Module, String)`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html#forName(java.lang.Module,java.lang.String)): primary source on module scope, `null`, linking, initialization, array types, and exceptions.
- [Java SE 17 — `Class` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html): overload behavior already present in Java 17.
- [Java SE 21 — `Module`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Module.html): identifying named/unnamed modules, loader, and layer.
- [Java SE 21 — `ModuleLayer`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ModuleLayer.html): module resolution context, finding modules, and loader mapping.
- [JVM Specification 21 — Chapter 5](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html): loading/linking/initialization fundamentals when deep error analysis is needed.

The examples use APIs suitable for Java 17 and later and intentionally separate the module-based class lookup step from the explicit initialization step.

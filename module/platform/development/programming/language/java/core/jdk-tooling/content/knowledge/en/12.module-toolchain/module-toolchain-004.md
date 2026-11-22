# The opens Directive in the Java Module System

In the Java Platform Module System (JPMS), introduced in Java 9, a module can restrict which packages other modules are allowed to use. The **`opens`** directive in `module-info.java` allows a package to be opened so that other modules can perform reflection on it, including *deep reflection* into non-public members such as private fields or methods.

`opens` is typically needed by frameworks or libraries that use reflection to map objects, read annotations, create proxies, or access private fields. It controls reflective access at the module level; it does not turn private members into public ones and does not grant direct access in source code.

## 1. Why Does JPMS Need opens?

Before Java 9, applications typically ran on the classpath, and many libraries could use reflection to deeply access classes in other libraries. JPMS introduced module boundaries to enforce encapsulation and control package access.

When a module does not open a package, other modules may still see and use exported public types, but they are not necessarily allowed to bypass access checks to read or modify private members using reflection.

For example, a framework might need to:

- Read private fields to map data from a database into an object.
- Invoke non-public constructors or methods to instantiate objects.
- Inspect annotations and metadata on internal members.
- Create proxies or perform dependency injection via reflection.

The `opens` directive lets the module owner decide which packages can be deeply accessed via reflection and which modules are permitted to do so.

## 2. Differences Between exports and opens

Both directives reference packages, but they serve different purposes.

| Criterion | `exports` | `opens` |
| --- | --- | --- |
| Purpose | Exposes a package's public API to other modules | Allows deep reflective access to a package |
| Regular source code access | Allows modules to read the package and use eligible public types | Does not grant compile-time access |
| Reflection on public API | Can be used under standard access rules | Not required if only accessing already-exported public APIs |
| Reflection on private members | Does not by itself allow deep reflection | Allows deep access for modules to which the package is opened |
| When applied | Compile time and runtime | Runtime |
| Can restrict target modules | Yes, via qualified exports | Yes, via qualified opens |

Example:

```java
module com.example.model {
    exports com.example.model;
    opens com.example.model to com.example.reflector;
}
```

- `exports com.example.model;` allows other modules to use the public API in the `com.example.model` package.
- `opens com.example.model to com.example.reflector;` allows the `com.example.reflector` module to perform deep reflection on that package, including private members.

A package can be exported, opened, both, or neither, depending on the module design.

**Key takeaway:** `opens` does not replace `exports`. If source code in another module needs to import and call a public class in a package, that package still needs to be exported or accessed through an appropriate module mechanism.

## 3. Syntax of the opens Directive

There are two basic forms.

### Opening a Package to All Modules

```java
opens com.example.model;
```

This is an *unqualified opens*. The package is opened so that all other modules can perform deep reflection on it.

This form is convenient when a package needs to be accessed via reflection by many different frameworks or modules, though it grants a broader access scope.

### Opening a Package Only to Specified Modules

```java
opens com.example.model to com.example.reflector;
```

This is a *qualified opens*. Only the module named `com.example.reflector` is granted deep reflection access to the `com.example.model` package.

Multiple target modules can be specified:

```java
opens com.example.model to
    com.example.reflector,
    com.example.persistence;
```

Prefer qualified opens when you know exactly which modules need reflection. This limits the exposed surface area and makes module relationships explicit.

## 4. Opening an Entire Module with open module

In addition to opening individual packages, a module descriptor can declare:

```java
open module com.example.model {
    exports com.example.model;
}
```

An *open module* opens all packages in the module for deep reflection from other modules at runtime.

Keep in mind:

- `open module` applies to every package in the module.
- Directives such as `requires` and `exports` can still be declared inside an open module.
- Separate `opens` directives cannot be declared inside an open module.
- An open module does not mean all packages are exported for other source code to import public types.

Use `open module` only when you genuinely need to open the entire module for reflection. If only a few packages need to be accessed by a framework, opening individual packages provides a clearer scope.

## 5. Complete Example: Reflecting on a Private Field Between Two Modules

The following example creates two Java 17 modules:

- `com.example.model`: provides a `Secret` class with a private field.
- `com.example.reflector`: uses reflection to read the private field of `Secret`.

Project structure:

```text
project/
  src/
    com.example.model/
      module-info.java
      com/example/model/Secret.java
    com.example.reflector/
      module-info.java
      com/example/reflector/Main.java
```

### Step 1: Declare the Module Containing the Data Class

File **`src/com.example.model/module-info.java`**:

```java
module com.example.model {
    exports com.example.model;
    opens com.example.model to com.example.reflector;
}
```

The package is exported so the reflector module can import the public class. The package is also specifically opened to the reflector module so reflection can access the private field.

### Step 2: Create the Class with a Private Field

File **`src/com.example.model/com/example/model/Secret.java`**:

```java
package com.example.model;

public final class Secret {
    private final String token = "module-secret";

    public Secret() {
    }
}
```

The `token` field remains private and final. The `opens` directive only allows the specified module to perform deep reflection on the package containing this class.

### Step 3: Declare the Module Using Reflection

File **`src/com.example.reflector/module-info.java`**:

```java
module com.example.reflector {
    requires com.example.model;
}
```

The `requires` directive creates a compile-time dependency between the reflector module and the model module. Because the `com.example.model` package is exported, the reflector source code can import the `Secret` class.

### Step 4: Write the Reflection Program

File **`src/com.example.reflector/com/example/reflector/Main.java`**:

```java
package com.example.reflector;

import com.example.model.Secret;
import java.lang.reflect.Field;

public class Main {
    public static void main(String[] args) throws ReflectiveOperationException {
        Secret secret = new Secret();

        Field tokenField = Secret.class.getDeclaredField("token");
        tokenField.setAccessible(true);

        System.out.println("private token=" + tokenField.get(secret));
    }
}
```

Explanation:

1. Create a `Secret` instance.
2. `getDeclaredField("token")` retrieves the metadata of the field declared directly in the class, including private fields.
3. `setAccessible(true)` asks reflection to bypass standard Java access checks for this reflective operation.
4. `field.get(secret)` reads the field value from the object.

### Step 5: Compile Both Modules

Run from the `project` root directory:

**Windows PowerShell:**

```powershell
New-Item -ItemType Directory -Force mods | Out-Null
javac -d mods --module-source-path src -m com.example.model,com.example.reflector
```

**macOS/Linux:**

```bash
mkdir -p mods
javac -d mods --module-source-path src -m com.example.model,com.example.reflector
```

After compiling, the output structure is:

```text
mods/
  com.example.model/
    module-info.class
    com/example/model/Secret.class
  com.example.reflector/
    module-info.class
    com/example/reflector/Main.class
```

### Step 6: Run the Reflector Module

Run:

```bash
java --module-path mods -m com.example.reflector/com.example.reflector.Main
```

Output:

```text
private token=module-secret
```

This succeeds because the `com.example.model` package is opened to the `com.example.reflector` module. The source code still keeps the `token` field private; only reflective operations are granted deep access.

## 6. What Happens Without opens?

If the model module only declares:

```java
module com.example.model {
    exports com.example.model;
}
```

The reflector source code can still compile because the package is exported and the `Secret` class is public. However, at runtime, the call:

```java
tokenField.setAccessible(true);
```

cannot bypass access checks because the package is not opened to the reflector module.

On Java 17, this operation typically throws `java.lang.reflect.InaccessibleObjectException`. The exact message depends on the module and package names, but the root cause is that the source module has not opened the package to the calling module.

You can use `trySetAccessible()` to check beforehand:

```java
if (tokenField.trySetAccessible()) {
    System.out.println(tokenField.get(secret));
} else {
    System.out.println("Deep reflection is not allowed");
}
```

- Returns `true`: deep access has been enabled for the reflective object.
- Returns `false`: deep access cannot be enabled under the current configuration.
- If `setAccessible(true)` is used and the module has not opened the package, Java may throw `InaccessibleObjectException`.

`trySetAccessible()` and `setAccessible(true)` do not modify the module descriptor or access modifiers. They only request reflective access for the corresponding `Field`, `Method`, or `Constructor` object.

## 7. Using --add-opens at Application Startup

If you cannot modify the `module-info.java` of the source module, the Java launcher provides the `--add-opens` runtime option.

Syntax:

```text
--add-opens source.module/package=target.module
```

Where:

- `source.module`: the module containing the package to open.
- `package`: the package to allow deep reflection on.
- `target.module`: the module granted access.

In the example above, if `com.example.model` does not declare an `opens` directive, you can run:

```bash
java --module-path mods --add-opens com.example.model/com.example.model=com.example.reflector -m com.example.reflector/com.example.reflector.Main
```

Output:

```text
private token=module-secret
```

The `--add-opens` option adds package-opening permission at runtime for that launch. It is useful when integrating legacy libraries or frameworks that lack proper module configuration.

### Opening a Package to Code on the Classpath

Code running on the classpath belongs to the unnamed module. You can open a package to unnamed modules with:

```bash
java --module-path mods --add-opens com.example.model/com.example.model=ALL-UNNAMED -cp app.jar app.LegacyMain
```

`ALL-UNNAMED` represents all unnamed modules. This option should only be used when the application actually runs code on the classpath that requires reflection.

Avoid opening all packages of multiple modules to `ALL-UNNAMED` if only one specific framework or library needs that permission. Restrict the source module, package, and target recipient.

## 8. Differences Between opens in module-info and --add-opens

| Criterion | `opens` directive | `--add-opens` option |
| --- | --- | --- |
| Where declared | `module-info.java` | Java launcher command line |
| Timing | Part of the module descriptor, applied when the module is loaded | Runtime for that specific launch |
| Scope | A package, either qualified or unqualified | A package of a source module for a target module |
| Purpose | Designing reflective access as part of the module | Adding open permissions at runtime without modifying the module descriptor |
| Best suited for | Modules intentionally supporting frameworks/reflection | Legacy integration or deployment configuration workarounds |

Prefer declaring `opens` in the module descriptor when reflective access is an intentional part of the module design. Use `--add-opens` when runtime configuration is needed, such as running legacy libraries or testing an application whose module descriptor cannot yet be modified.

## 9. opens Does Not Change Access Modifiers

Suppose a class has:

```java
private String token;
```

Even when the package is opened, the field still has the `private` access flag in the class file. The `opens` directive does not change:

- The `private`, `protected`, or `public` keywords in source code.
- Access flags in the class file.
- The ability to directly call private methods from another module's source code.
- Inheritance relationships or class visibility.

Source code in another module still cannot write:

```java
secret.token = "changed"; // Invalid: token is private
```

To interact with private members, code must use reflection and the module must open the package to the calling module. Reflection is still subject to Java's restrictions, such as special constraints on final fields and unmodifiable objects.

## 10. opens Is Not the Same as requires or exports

A module descriptor can contain several different directives:

```java
module com.example.application {
    requires com.example.model;
}
```

- `requires` declares a module dependency so the current module can read that module.
- `exports` exposes a package so other modules can use its public API.
- `opens` allows other modules to perform deep reflection on a package.

These directives do not replace one another. For example, the reflector module needs `requires com.example.model` to compile when importing the `Secret` class; the model module needs `exports com.example.model` to expose that class; and it needs `opens` if the reflector must access private fields via reflection.

## 11. Choosing Qualified opens or Unqualified opens?

Choose the smallest scope that meets your requirements.

**Use qualified opens when:**

- Only one specific framework or module needs reflection.
- You want to make explicit which modules are granted deep access.
- You want to minimize the exposed package surface.

Example:

```java
opens com.example.persistence.model to
    org.example.orm,
    com.example.json;
```

**Use unqualified opens when:**

- The package must support multiple modules that cannot be listed in advance.
- The library design intentionally allows any module to perform reflection on the package.
- The broader scope has been evaluated and accepted.

Example:

```java
opens com.example.dto;
```

**Use open module when:**

- Nearly every package in the module needs deep reflective access.
- The module is designed as a data-holding area for a framework.
- Opening all packages is intentional and has been evaluated.

Avoid using `open module` just to fix a single reflection error. Opening the specific package is usually easier to maintain and control.

## 12. Common Errors

| Symptom | Common Cause | Resolution |
| --- | --- | --- |
| `InaccessibleObjectException` | Package is not opened to the module calling reflection | Add a qualified `opens` or configure `--add-opens` |
| `trySetAccessible()` returns `false` | Source module does not open the package to the target module | Verify the module and package names in the directive |
| Cannot import public class despite `opens` | `opens` does not grant compile-time access | Add `exports` if the public API is needed |
| Added `opens` but still failing | Opened the wrong package or wrong target module | Check the declared package and actual module name |
| Error only appears when running from an IDE | IDE uses a different launcher/module path configuration | Add the VM option to the IDE run configuration |
| Legacy framework fails on Java 17 | Framework uses deep reflection on an unopened package | Upgrade the framework or open the required package to the needed module |
| Opened package to unnamed module but still failing | Application runs as a named module or target is incorrect | Use the target module name or `ALL-UNNAMED` matching how the app is launched |

When diagnosing, read the full error message. It typically identifies the source module, the closed package, and the target module that needs permission.

## 13. Security and Maintenance Best Practices

- Open only the packages that genuinely require reflection.
- Prefer qualified opens to restrict which modules receive access.
- Keep public APIs separate from internal packages that require deep reflection.
- Do not open an entire module just to resolve an error in a single package.
- Avoid global `--add-opens` or opening many packages to `ALL-UNNAMED`.
- When possible, upgrade frameworks to support JPMS instead of maintaining numerous runtime flags.
- Verify the module path and actual module names in production environments.
- Do not treat `opens` as a secret-protection mechanism. Any code granted reflection access can still read internal data within the opened package.
- When modifying a module descriptor, re-run integration tests to catch frameworks or libraries that depend on reflection.

## 14. Key Takeaways

- `opens` is a JPMS directive that enables deep reflection on a package.
- `opens package;` opens the package to all modules.
- `opens package to module.name;` opens the package only to the specified module.
- `open module` opens all packages in the module for reflection at runtime.
- `exports` allows standard public API access; `opens` allows deep reflection.
- `--add-opens source.module/package=target.module` grants package-opening permission at runtime.
- `ALL-UNNAMED` represents code running on the classpath.
- `opens` does not change access modifiers and does not allow calling private members directly from source code.

Understanding `opens` lets you design modules that work smoothly with reflection-based frameworks, resolve `InaccessibleObjectException` errors, and still limit internal access to only what is necessary.

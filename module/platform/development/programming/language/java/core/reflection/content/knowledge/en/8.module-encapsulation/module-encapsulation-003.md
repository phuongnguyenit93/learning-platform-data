# How Does Public Reflection Differ from Deep Reflection in Java?

In Java Reflection, **looking up metadata** (`getMethod`, `getDeclaredMethod`) and **actually accessing a member** (`invoke`, `Field.get`, `Constructor.newInstance`) are two separate steps. This lesson distinguishes **public reflection**—using public APIs that the caller already has permission to access—from **deep reflection**—operations that need to bypass Java access checks using `trySetAccessible()` or `setAccessible(true)`.

With named modules, public APIs used across modules typically require `exports`; accessing private members of another module typically requires the package to be `opens`-ed to the caller. These are two ways of using Reflection, not two `Class` types or two separate API libraries. A Java 17+ example will show how the same program's output changes when package-opening permission is added.

## 1. Three Layers of Questions to Separate

When a framework wants to invoke `Person.secret()` or read `Person.name`, answer in this exact order:

1. **Can the member be found?** `getMethod("name")` finds a public method; `getDeclaredMethod("secret")` finds a directly declared method, including private ones.
2. **Is the caller permitted to access the member via Reflection?** `public`/`private` visibility rules, class/package relationships, and JPMS `exports`/`opens` determine this.
3. **Does the actual usage succeed?** `Method.invoke`, `Field.get`, `Field.set`, and `Constructor.newInstance` can still fail due to the receiver, arguments, object state, or exceptions inside the invoked code.

Example:

```java
Method method = type.getDeclaredMethod("secret");
```

The statement above only looks up metadata. If `secret` is private and the caller is in another module, `method.invoke(object)` is not necessarily permitted. You must check whether the package has been `opens`-ed and whether the caller has validly enabled reflective access.

**Remember:** `public` is the access level of the class/member, whereas `exports`/`opens` are **package relationships between modules**. A `public` method in a `public` class of an unexported package can still be uncallable from another module via public reflection.

## 2. Direct Comparison

| Aspect | Public reflection | Deep reflection |
|---|---|---|
| Purpose | Use public APIs via runtime metadata | Access members or types not permitted under normal Java access checks |
| Typical lookup APIs | `getMethod`, `getField`, `getConstructor` | `getDeclaredMethod`, `getDeclaredField`, `getDeclaredConstructor` |
| Can it see private metadata? | `get...` APIs do not return private members | `getDeclared...` APIs can return private metadata; **lookup alone is not enough to access** |
| Suppress Java access checks? | Not needed for valid public APIs and exported packages | Must request via `trySetAccessible()` or `setAccessible(true)` when normal access checks disallow it |
| Named module providing the package | Typically uses `exports package.name` or `exports package.name to caller.module` | Typically uses `opens package.name` or `opens package.name to caller.module` |
| Allows importing classes from another module at compile time? | `exports` allows using public types when appropriate module readability exists | `opens` alone does not turn a package into an importable API like `exports` |
| Design risk | Depends on the public API contract | Depends on internal details and can break encapsulation |

The table describes typical scenarios **between named modules**. There are exceptions in the `AccessibleObject` rules for the same module, already open packages, or certain public/protected static members with an appropriate subclass relationship. Do not assume that seeing `private` always means you must edit `module-info.java`: if the caller and target class are in the **same module**, requesting reflective access can be valid even if the package is not `opens`-ed externally.

## 3. Metadata Lookup Does Not Mean Permission to Call

Lookup APIs on a `Class<?>` object:

```java
// The snippets below are illustrative examples, assuming Sample.class exists.
Method publicMethod = Sample.class.getMethod("execute");
Method declaredMethod = Sample.class.getDeclaredMethod("internal");
Field declaredField = Sample.class.getDeclaredField("state");
Constructor<Sample> ctor = Sample.class.getDeclaredConstructor();
```

Distinctions:

- `getMethod`, `getField`, and `getConstructor` find only **public** members under their respective rules; for methods/fields this may include inherited members, whereas constructors are not inherited.
- `getDeclaredMethod`, `getDeclaredField`, and `getDeclaredConstructor` look up members **declared directly** on the class, including both public and non-public ones; they do not automatically walk superclasses.
- `getDeclaredMethods()` or `getDeclaredFields()` can list metadata of private members without granting permission to invoke/read them. **You do not need `opens` just to use `getDeclaredMethod` to find a method name** in typical illustrative cases.
- `Method.invoke`, `Field.get`/`set`, and `Constructor.newInstance` perform the actual action, applying access rules and other conditions.

A simple example if all code resides in an ordinary application package:

```java
class Example {
    private String secret() {
        return "secret-data";
    }
}
```

```java
Method m = Example.class.getDeclaredMethod("secret");
// Already have metadata for secret; no permission yet to call the private method from elsewhere.
// You can try m.trySetAccessible(), if the class/module relationship permits it.
// Only after permission is valid should you use m.invoke(instance).
```

These two snippets are **semantic illustrations**, not a standalone program with `main` and imports. The next section has a complete example that compiles and runs.

## 4. JPMS: Why Does `exports` Differ from `opens`?

Since Java 9, `module-info.java` lets a named module explicitly declare which packages are APIs and which packages are opened for reflective access.

Suppose module `demo.target` owns package `demo.api`, and module `demo.client` contains the caller.

### `exports`: API Used from Another Module

```java
module demo.target {
    exports demo.api;
}
```

With this declaration, `demo.api` is **exported** to every module that reads `demo.target`. If `demo.api.Person` is a public class and `displayName()` is a public method, `demo.client` can import/use that class and call the public method. Reflection invoking `displayName()` under normal access checks is also valid.

`exports` **does not grant permission** to access private fields/methods with `setAccessible(true)` from another module. Exporting also does not make package-private/protected members automatically become public.

You can restrict the API to a single module:

```java
module demo.target {
    exports demo.api to demo.client;
}
```

### `opens`: Allowing Deep Reflection at Runtime

```java
module demo.target {
    exports demo.api;
    opens demo.api to demo.client;
}
```

Then `demo.client` can continue using the public API while also having permission to **request suppressing Java language access checks via Reflection** for members in package `demo.api` under JPMS rules. Using `opens ... to ...` narrows the recipient better than opening the package to all modules.

If you declare only:

```java
module demo.target {
    opens demo.api to demo.client;
}
```

the package is opened for Reflection from `demo.client`, yet **is not exported** as a public API for `demo.client` to import `demo.api.Person` in regular Java source. Frameworks can still use runtime metadata by class name and reflective access when appropriate conditions hold.

There are also two broader forms:

- `opens demo.api;`: opens the package for deep reflection from **every module**.
- `open module demo.target { ... }`: opens **all packages of the entire module** for Reflection. Avoid using this just to satisfy a single package's need.

| Declaration in Target Module | Public API for Caller in Another Module | Deep Reflection from Caller in Another Module |
|---|---|---|
| Neither `exports` nor `opens` | Not accessible as an exported public API | Restricted by encapsulation |
| `exports demo.api;` | Yes, with public class/members and proper readability | Does not grant permission into private members |
| `opens demo.api;` | Does not create permission to import public API via `opens` alone | Permitted to request suppressing access checks |
| `exports demo.api;` and `opens demo.api;` | Yes | Yes |
| `exports demo.api to demo.client;` and `opens demo.api to demo.client;` | Yes, for `demo.client` | Yes, for `demo.client` |

In the table, "has deep reflection" means **opening the ability to satisfy requests to suppress access checks** in core Reflection; code can still be constrained by member behavior, object types, non-modifiable `final` fields depending on the case, and runtime exceptions.

## 5. Java 17+ Experiment: Same Source, Two Outcomes Based on Module Permissions

Create the file layout:

```text
reflection-demo/
└── src/
    ├── demo.target/
    │   ├── module-info.java
    │   └── demo/api/Person.java
    └── demo.client/
        ├── module-info.java
        └── demo/app/Main.java
```

**File `src/demo.target/module-info.java`:**

```java
module demo.target {
    exports demo.api;
}
```

**File `src/demo.target/demo/api/Person.java`:**

```java
package demo.api;

public class Person {
    private final String name;

    public Person(String name) {
        this.name = name;
    }

    public String displayName() {
        return name;
    }

    private String internalId() {
        return "id-" + name;
    }
}
```

**File `src/demo.client/module-info.java`:**

```java
module demo.client {
    requires demo.target;
}
```

**File `src/demo.client/demo/app/Main.java`:**

```java
package demo.app;

import demo.api.Person;
import java.lang.reflect.Method;

public class Main {
    public static void main(String[] args) throws ReflectiveOperationException {
        Module target = Person.class.getModule();
        Module caller = Main.class.getModule();

        System.out.println("exported: " + target.isExported("demo.api", caller));
        System.out.println("opened: " + target.isOpen("demo.api", caller));

        Person person = new Person("Lan");

        Method publicMethod = Person.class.getMethod("displayName");
        System.out.println("public method: " + publicMethod.invoke(person));

        Method privateMethod = Person.class.getDeclaredMethod("internalId");
        System.out.println("private metadata: " + privateMethod.getName());

        boolean deepAllowed = privateMethod.trySetAccessible();
        System.out.println("deep allowed: " + deepAllowed);

        if (deepAllowed) {
            System.out.println("private method: " + privateMethod.invoke(person));
        }
    }
}
```

**Compile the two named modules with JDK 17+** (from inside `reflection-demo`):

```bash
javac -d out --module-source-path src -m demo.target,demo.client
```

### Run 1: `exports` Only, No `opens`

```bash
java --module-path out -m demo.client/demo.app.Main
```

Exact stdout:

```text
exported: true
opened: false
public method: Lan
private metadata: internalId
deep allowed: false
```

Explanation:

1. `demo.target` exports `demo.api` to `demo.client`; Java source can import `Person` and invoke the public API via `Method.invoke` successfully.
2. `getDeclaredMethod("internalId")` **still finds the private method's metadata**.
3. `trySetAccessible()` returns `false` because the package is not opened to the calling module, so the code does not enter the branch invoking `internalId()`. This demonstrates the difference between metadata discovery and deep access.

### Run 2: Open the Package at Runtime Without Editing Source

Run with the JVM argument `--add-opens`:

```bash
java --module-path out --add-opens demo.target/demo.api=demo.client -m demo.client/demo.app.Main
```

Exact stdout:

```text
exported: true
opened: true
public method: Lan
private metadata: internalId
deep allowed: true
private method: id-Lan
```

The `--add-opens demo.target/demo.api=demo.client` flag grants permission to open the **target module**'s package to the **caller module** for this run. No changes to `Person`, `Main`, or recompilation are needed to observe the difference. This is a **runtime access permission**, not permission to import additional classes during compilation.

### Equivalent Approach Using `module-info.java`

Replace the contents of `src/demo.target/module-info.java` with:

```java
module demo.target {
    exports demo.api;
    opens demo.api to demo.client;
}
```

Recompile:

```bash
javac -d out --module-source-path src -m demo.target,demo.client
java --module-path out -m demo.client/demo.app.Main
```

No `--add-opens` is needed on this run; stdout matches **Run 2**. For applications with a clear module structure, `opens ... to ...` for a specific framework is usually easier to audit than overly broad permissions applied unnecessarily.

**Note:** `--add-opens` must be passed to the JVM **before** `-m` in the example. The `demo.target/demo.api` part is `module/package`, and to the right of `=` is the module receiving the open permission. The `out` directory path holds the compiled modules.

## 6. `trySetAccessible`, `setAccessible`, and `canAccess`

`Field`, `Method`, and `Constructor` inherit from `java.lang.reflect.AccessibleObject`; typical APIs are:

```java
boolean ok = member.trySetAccessible();
member.setAccessible(true);
boolean canUse = member.canAccess(receiver);
```

These lines are **illustrative API options**, not a snippet meant to be called consecutively. `member` is an actual `AccessibleObject` of type `Field`, `Method`, or `Constructor`; the receiver depends on the member kind.

- `trySetAccessible()`: attempts to enable **suppress Java language access checks**. Returns `true` if allowed; returns `false` if it cannot be enabled under those constraints. Suitable for frameworks that want to support various module configurations without throwing an exception when deep access is blocked.
- `setAccessible(true)`: requests enabling this mode; can throw **`InaccessibleObjectException`** if it cannot be enabled due to module encapsulation. In legacy setups or when access is open, the call can succeed.
- `canAccess(receiver)`: checks current permission on the member for the caller at call time; this is a query and **does not open** permission by itself. For instance fields/methods, `receiver` must be a valid object instance. For static fields/methods and constructors, receiver must be `null`.

The phrase "suppress Java language access checks" does not mean disabling every JVM safeguard. Some `final` fields belong to the **non-modifiable final fields** category (such as record components or hidden-class final fields) and cannot be written via core Reflection even after `setAccessible(true)` succeeds; other runtime constraints also remain.

### Handling Failures in Practice

When a framework intentionally supports private members:

```java
Method internal = Person.class.getDeclaredMethod("internalId");
if (!internal.trySetAccessible()) {
    throw new IllegalStateException(
            "Module demo.target must open demo.api to demo.client");
}
Object result = internal.invoke(new Person("Lan"));
```

This is an **illustrative snippet** placed inside module `demo.client` of the experiment, not a standalone runnable file. Valid `opens` permission must be provided before calling. In a real-world library, the error message should describe the target module, package, and caller module obtained from `Class.getModule()`, avoiding hard-coding when the library supports multiple modules.

Do not call `setAccessible(true)` in bulk on every field/method "just in case": requesting access to internal details should have a clear purpose, narrow permissions, and explicit error handling.

## 7. Public Members in an Unexported Package Can Still Be Blocked

Consider `demo.target` adding package `demo.hidden`, while `module-info.java` exports only `demo.api`:

```java
module demo.target {
    exports demo.api;
}
```

Inside `demo.hidden` sits `public class HiddenApi` with `public static String status()`. Even though both the class and method are declared `public`, module `demo.client` **cannot import `demo.hidden.HiddenApi` as a valid public API**, because the package is not exported to it.

If the program obtains the `Class` object of `HiddenApi` through a valid runtime path, `getMethod("status")` can still find metadata. However, calling it via `Method.invoke` under normal Java access checks **is not automatically permitted**. This is why you must never equate "the method is declared public" with "the calling module has permission to call that method".

Two frequently confused JVM options:

```bash
# Grant public access to the unexported package for demo.client:
--add-exports demo.target/demo.hidden=demo.client

# Open the package for deep reflection from demo.client:
--add-opens demo.target/demo.hidden=demo.client
```

These two lines are **illustrative JVM options**, not standalone shell commands. `--add-exports` addresses access to a package's public API when the target module has not exported it; by itself it does not grant permission to access private members via deep reflection. `--add-opens` grants deep reflective access to the package. Choose the right one for the goal, preferring explicit module declarations or public APIs rather than broadening permissions arbitrarily.

## 8. Impact of Classpath, Unnamed Modules, and Frameworks

A Java application can use both the **module path** and the **classpath**:

- Classes loaded from the regular classpath belong to an **unnamed module**; packages of an unnamed module are exported and opened for compatibility.
- An **open module** allows reflective access into packages within its module according to JPMS rules.
- In a **regular named module**, packages are not automatically exported/opened to other modules. Moving code that was running on the classpath into a named module can cause frameworks that used to access private members to fail with `InaccessibleObjectException`.

Examples:

- **JSON serialization / ORM**: frameworks often look up non-public fields or constructors and may need deep reflection permission. If module `app.model` manages entity classes, you can use `opens app.model.entity to some.framework.module;` naming the actual framework module.
- **Dependency injection**: if the container calls a public constructor from an exported package, public reflection may suffice. If the container needs private field injection or access to non-public constructors, package-opening permission must be considered.
- **Introspection tools**: if they only list method names, parameter types, or annotation metadata, opening private access may not be needed. Do not open a package merely because `getDeclaredMethods()` is used.
- **API clients**: for public interfaces/service APIs, `exports` and `getMethod` are the natural choice, reducing reliance on implementation details.

**The framework's module name must be exact.** Qualified `opens ... to framework.module` takes effect only for the module named accurately. For frameworks running in the unnamed module, some launcher configurations need `ALL-UNNAMED`, such as `--add-opens my.module/my.pkg=ALL-UNNAMED`; this is a runtime choice for legacy tooling, not a default to apply to every module.

Besides core Reflection, `MethodHandles.privateLookupIn` is also a deep-access mechanism under appropriate module conditions; it **does not let you bypass** another module's `opens` requirement.

## 9. Common Errors

| Symptom | Typical Cause | Resolution |
|---|---|---|
| `NoSuchMethodException` when calling `getMethod` | Method is not public, wrong name/parameter signature, or does not exist | Verify exact name and parameter types; use `getDeclaredMethod` if metadata for a directly declared method is needed |
| `NoSuchFieldException` when calling `getField` | Field is not public or does not exist with that name | Check the actual field and consider `getDeclaredField` |
| `IllegalAccessException` at `Method.invoke` or `Field.get` | Caller lacks access permission under visibility and/or module encapsulation | Check `public` class/member, package export, or valid deep reflection permission |
| `InaccessibleObjectException` at `setAccessible(true)` | Target module does not open the package to the caller | Use `opens ... to ...` or targeted `--add-opens`; prefer a public API when possible |
| `trySetAccessible()` returns `false` | Cannot enable suppression under module/encapsulation rules | Choose a public API or configure `opens` for the right module; handle fallbacks transparently |
| `InvocationTargetException` after invoke is allowed | The **invoked code** threw an exception | Inspect `getCause()`; this is an error during method/constructor execution, not evidence of missing `opens` |
| Compiler reports package is not visible | Missing `requires`, package not exported, or mismatched module graph | Check `requires` on caller, `exports` on target, and module path |
| Works on classpath but fails when moved to module path | Strong encapsulation of named modules | Identify public/deep needs and declare minimal-scope exports/opens |

In Java 17+, do not rely on unauthorized access mechanisms into JDK internals as in some older Java runtimes. Strong encapsulation rules are enforced; migrating older frameworks should prioritize updating libraries and configuring properly scoped modules.

## 10. Misconceptions to Avoid

1. **"`getDeclaredMethod` is already deep reflection."** Incorrect: it only retrieves metadata; deep access must pass access permission constraints through valid mechanisms when needed.
2. **"If a class and method are public, any module can call them."** False if the package is not appropriately exported between named modules.
3. **"`exports` allows opening private members."** False: export serves public APIs; `opens` is for deep runtime reflective access.
4. **"`opens` and `exports` are equivalent."** False: `opens` does not automatically allow Java source in another module to import public types like an exported package.
5. **"`setAccessible(true)` always succeeds."** False: it can throw `InaccessibleObjectException` when the module/package is not appropriately opened.
6. **"`trySetAccessible()` returning false means the member does not exist."** False: metadata was already found, but permission to suppress access checks could not be enabled.
7. **"Method.invoke throwing `InvocationTargetException` proves it was blocked by modules."** False: this exception wraps an error thrown inside the method/constructor that ran.
8. **"An open package must be opened to everyone."** False: qualified `opens pkg to specific.module` lets you restrict permission.
9. **"Reflection that only reads metadata also needs `--add-opens`."** Not by default: distinguish metadata introspection from deep access before granting additional permissions.
10. **"Opening a package means frameworks can write every final field."** False: many JVM restrictions remain in effect.

## 11. Self-Check

**Question 1.** Module `catalog.core` exports `catalog.api`, which contains `public class Item` and `public String code()`. Module `catalog.client` requires `catalog.core`. Can public reflection invoke `code()`?

**Answer:** Yes, provided the class/member are validly public and the package is exported to the caller. `Item.class.getMethod("code")` returns the `Method`; `invoke` with a valid instance can run without opening the package for deep reflection.

**Question 2.** The same `Item` class has field `private String internalKey`. `getDeclaredField("internalKey")` succeeds, yet `trySetAccessible()` returns false. What does that tell you?

**Answer:** The program found the metadata, yet lacks permission to enable suppressing access checks in the current class/module relationship. With two named modules, check `opens catalog.api to catalog.client` if deep reflection is genuinely required.

**Question 3.** Is adding `exports catalog.api;` enough for the client to read a private field via `Field.get` after `setAccessible(true)`?

**Answer:** No. For a caller in another module, `exports` does not replace `opens`; configure appropriate package opening or design an alternative public API.

**Question 4.** If you only want to list the names of directly declared methods, do you need to call `setAccessible(true)` on every method?

**Answer:** No. `getDeclaredMethods()` returns metadata; reading names via `Method.getName()` is neither executing methods nor bypassing access checks.

**Question 5.** Why can `--add-opens target.module/p=caller.module` resolve a deep reflection error at runtime yet still not allow `import p.SomeType;` in source code to compile?

**Answer:** `--add-opens` is a runtime reflective access permission, different from exposing a public API via `exports`. Compile-time visibility requires the corresponding module graph configuration and exported package.

## Official Documentation

- Java SE API — `java.lang.reflect.AccessibleObject`: `trySetAccessible`, `setAccessible`, `canAccess`, inter-module access rules.
- Java SE API — `java.lang.Class`: `getMethod`, `getDeclaredMethod`, `getField`, `getDeclaredField`, and `getModule`.
- Java SE API — `java.lang.Module`: `isExported`, `isOpen`, and package access relationships.
- Java Language Specification — Chapter 7 and sections on modules, packages, and access control.
- Java Platform Module System (`java` launcher, `javac`) — `--module-path`, `--module-source-path`, `--add-exports`, `--add-opens` options.

**Takeaway:** Public reflection uses **public APIs** that the caller is permitted to access; deep reflection requires **deep access into implementation internals** and may need to suppress access checks. In JPMS, `exports` exposes public APIs, while `opens` grants runtime Reflection permission. Finding a `Method`/`Field` does not mean you are already permitted to invoke or read it.

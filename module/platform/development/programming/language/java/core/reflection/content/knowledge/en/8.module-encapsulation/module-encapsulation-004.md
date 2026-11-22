# Java Reflection and JPMS: Access Conditions When Caller and Target Class Are in the Same Module

In Java 9+ (including Java 17 and 21), **JPMS — Java Platform Module System** introduces boundaries between modules. However, when the class **actually performing Reflection** (*caller*) and the class **declaring the member to access** reside in **the same module**, checking and enabling Reflection access follow more permissive rules than crossing a module boundary. It is important not to equate *same module* with *having direct access to every `private` member*.

Core takeaways:

- **Looking up metadata** via `getDeclaredField()`, `getDeclaredMethod()`, or `getDeclaredConstructor()` is the member-discovery step; finding a `private` member does not mean you can immediately read or invoke it.
- **Regular Java access** still obeys `public`, `protected`, package-private, and `private`. Two different classes in the same module are not automatically treated as being in the same package or same nest.
- With Reflection, if **the caller and the member's declaring class are in the same module**, `AccessibleObject#trySetAccessible()` can enable suppressing Java access checks for that member; `setAccessible(true)` is also permitted under JPMS's *same module* condition. Operations after enabling access must still follow specific restrictions, such as limits on modifying `final`.
- You do not need to declare `exports` or `opens` **just to support internal access within the same module**. Those two directives primarily control how packages are used from **other modules**.

This lesson clarifies the scope of "same module", the two layers of access checks, how to verify using Java code with `module-info.java`, and common mistakes when building Reflection utilities.

## 1. What Do "Caller" and "Same Module" Mean Exactly?

A module is a unit packaging multiple packages. Named modules are declared with `module-info.java`; code on the classpath typically belongs to an **unnamed module** tied to a class loader.

In the context of Reflection:

- **Target/declarer** is the class or interface that actually **declares** the field, method, or constructor to operate on; see `member.getDeclaringClass()`.
- **Caller** is the class whose code **actually calls** the Reflection access-check/enabling API, such as `trySetAccessible()`. Do not assume the caller is the application-layer class that initiated a request.
- To check whether two classes belong to **the exact same module object**, compare `Class#getModule()` using `==`.

Example:

~~~java
boolean sameModule = Caller.class.getModule()
        == Target.class.getModule();
~~~

The snippet above is **illustrative code**, where `Caller` and `Target` are two classes defined in the application. Comparing modules by **identity** is better than comparing strings from `Module#getName()`: unnamed modules have a `null` name, and having the same module name is not enough to prove two classes belong to the same module object across different class loader/layer environments.

**Regarding unnamed modules:** do not conclude that all classes across all class loaders share the same unnamed module. Each class loader has its own unnamed module. Always inspect the actual `Module` object when classes are loaded dynamically or when an application uses multiple class loaders.

## 2. Separating Three Questions About Access Permissions

There are three independent questions:

| Question | Related API or Rule | When Two Classes Are in the Same Module |
| --- | --- | --- |
| **Is the member's metadata found?** | `Class#getDeclaredField`, `getDeclaredMethod`, `getDeclaredConstructor` | Can find even directly declared `private` members, if name/signature match |
| **Can the member be used under current access checks?** | Java rules `public`/`protected`/package-private/`private`, `canAccess(receiver)` | Must still satisfy normal permissions, unless access-check suppression has been enabled |
| **Can Java access-check suppression be enabled via Reflection?** | `trySetAccessible()`, `setAccessible(true)` | The *declaring class in same module as caller* condition permits enabling access; package `opens` is not required |

Example: `app.Main` and `model.Vault` may be in the same module, yet in **two different packages**. If `Vault` has field `private String token`, `Vault.class.getDeclaredField("token")` still returns the `Field`. However, `field.canAccess(vault)` typically returns `false` before enabling access because `Main` is not a class/nest allowed to access `Vault`'s `private` members. Once `field.trySetAccessible()` succeeds, `field.get(vault)` can read the value.

### Normal Java Rules Still Apply

- `public`: pay attention to the access level of **both the declaring class and the member**; a package not having `exports` does not forbid code in the **same module** from accessing valid `public` declarations.
- `protected`: permitted under same-package or inheritance rules, with additional conditions for cross-package access. Merely being in the "same module" is not enough.
- Package-private (no modifier): two classes in **different packages** do not automatically gain access to each other, even if they belong to the same module.
- `private`: follows Java's class/nest rules. Two top-level classes not in the same nest do not gain direct access to each other's `private` members just by being in the same module.

**Same module does not mean same package**, nor does it make a `private` access in source code valid. When deep access via Reflection is truly needed, enabling access is an **explicit step**.

## 3. Inside a Named Module: No Need for `exports` and `opens`

Suppose a project has the structure:

~~~text
src/
└── demo.same/
    ├── module-info.java
    └── lesson/
        ├── app/
        │   └── Main.java
        └── domain/
            └── Vault.java
~~~

All `.java` files belong to **the same named module** `demo.same`, even though they are split into two packages `lesson.app` and `lesson.domain`.

Contents of `src/demo.same/module-info.java`:

~~~java
module demo.same {
}
~~~

This module **does not declare** `exports lesson.domain;` or `opens lesson.domain;`. For code inside `demo.same`, that neither prevents valid `public` Java access from another package in the same module, nor prevents enabling deep access via Reflection when the *same module* condition is met.

### Target Class `Vault`

File **`src/demo.same/lesson/domain/Vault.java`**:

~~~java
package lesson.domain;

public final class Vault {
    private String token;

    private Vault(String token) {
        this.token = token;
    }

    public static Vault create() {
        return new Vault("initial");
    }

    public String status() {
        return "ready";
    }

    private String reveal(String prefix) {
        return prefix + token;
    }
}
~~~

Here `Vault` is a `public` class so `lesson.app.Main` can use it directly from **another package in the same module**. However, constructor `Vault(String)`, field `token`, and method `reveal(String)` are `private`; `Main` cannot call or read those members directly with normal Java syntax.

### Caller Performing Reflection

File **`src/demo.same/lesson/app/Main.java`**:

~~~java
package lesson.app;

import java.lang.reflect.Constructor;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import lesson.domain.Vault;

public class Main {
    public static void main(String[] args) throws ReflectiveOperationException {
        System.out.println("Same module: "
                + (Main.class.getModule() == Vault.class.getModule()));
        Vault vault = Vault.create();
        System.out.println("Public access: " + vault.status());

        Field token = Vault.class.getDeclaredField("token");
        System.out.println("Field before: " + token.canAccess(vault));
        System.out.println("Field override: " + token.trySetAccessible());
        System.out.println("Field after: " + token.canAccess(vault));
        System.out.println("Field value: " + token.get(vault));

        Method reveal = Vault.class.getDeclaredMethod("reveal", String.class);
        System.out.println("Method override: " + reveal.trySetAccessible());
        System.out.println("Result: " + reveal.invoke(vault, "value="));

        Constructor<Vault> ctor = Vault.class.getDeclaredConstructor(String.class);
        System.out.println("Constructor before: " + ctor.canAccess(null));
        System.out.println("Constructor override: " + ctor.trySetAccessible());
        Vault created = ctor.newInstance("custom");
        System.out.println("Constructed: " + reveal.invoke(created, "value="));
    }
}
~~~

Run from the project directory using **JDK 17+**:

~~~bash
javac --module-source-path src -d out -m demo.same
java --module-path out --module demo.same/lesson.app.Main
~~~

**Verified stdout:**

~~~text
Same module: true
Public access: ready
Field before: false
Field override: true
Field after: true
Field value: initial
Method override: true
Result: value=initial
Constructor before: false
Constructor override: true
Constructed: value=custom
~~~

### Reading the Output Step by Step

1. Comparing `Main.class.getModule() == Vault.class.getModule()` returns `true`: this is a single named module; do not guess based on package names.
2. `Vault.create()` and `vault.status()` are `public` APIs and can be called directly from `lesson.app` even though `module-info.java` has no `exports`. Both packages are internal to the same module.
3. `getDeclaredField("token")` finds the `private` field metadata. `token.canAccess(vault)` returns `false` for caller `Main` because normal Java access does not allow reading that `private` field.
4. `token.trySetAccessible()` returns `true` because the calling class and declaring class are in the same module. Afterward `canAccess` is `true` and `get(vault)` returns `"initial"`.
5. `getDeclaredMethod("reveal", String.class)` looks up the right private method. After enabling access, `invoke(vault, "value=")` returns `"value=initial"`.
6. `getDeclaredConstructor(String.class)` looks up the right private constructor. `ctor.canAccess(null)` is initially `false`; once access is enabled, `newInstance("custom")` creates a new object.
7. `reveal.invoke(created, "value=")` returns `"value=custom"`, proving the object created through this constructor has its own state.

All three cases—`Field`, `Method`, and `Constructor`—are **looked up first**, then access is enabled before using the Reflection object. The example uses `trySetAccessible()` explicitly so the permission-check step is not hidden.

## 4. Why Are `exports`/`opens` Not Needed in the Example Above?

JPMS uses two directives with distinct purposes:

| `module-info.java` Directive | Typical Purpose | Required for a Same-Module Caller? |
| --- | --- | --- |
| `exports lesson.domain;` | Let other modules use the package's `public` API via normal Java access | **No** |
| `opens lesson.domain;` | Let other modules perform deep Reflection on members when other conditions fit | **No** |
| `opens lesson.domain to some.framework;` | Specify which external module has deep reflection permission into that package | **No** |
| Neither directive declared | Package is closed to external modules along the corresponding boundaries | Code in the **same module** still follows the rules in this lesson |

The same-module condition is an independent permission branch in the documentation of `AccessibleObject#setAccessible` and `trySetAccessible`. A framework in **another module** does not automatically inherit this permission simply because it receives a `Class` or `Field` object passed from code in the target module.

**Do not add `opens` for an entire module** just to let internal code use Reflection. Opening a package is an architectural decision affecting other modules and is unnecessary in a *same module* scenario.

## 5. `canAccess`, `trySetAccessible`, and `setAccessible`

`Field`, `Method`, and `Constructor` all inherit from `AccessibleObject`.

### `canAccess(Object obj)`

Checks whether the member is accessible in its current state to the invoking caller. The `obj` argument must match the member kind:

- **Instance** field or method: pass the instance holding the member, e.g., `field.canAccess(vault)`.
- **Static** field or method: pass `null`.
- Constructor: pass `null`, e.g., `ctor.canAccess(null)`.

An invalid argument can cause `IllegalArgumentException`; do not pass `canAccess(null)` for an instance field/method just to ask "do I have permission?".

### `trySetAccessible()`

Attempts to enable suppressing Java access checks on the Reflection object. When the caller and declaring class are in the **same module**, JPMS's same-module condition allows this operation. The method returns a `boolean` indicating whether enabling succeeded, so library code should check the return value rather than ignoring it.

~~~java
if (!member.trySetAccessible()) {
    throw new IllegalStateException("Cannot enable reflective access");
}
~~~

The snippet above is **illustrative code**, where `member` is a valid `AccessibleObject`. In this lesson's scenario it succeeds because caller and target are in the same module; in general-purpose designs you must still handle rejection, especially when module boundaries or caller locations change.

### `setAccessible(true)`

Also requests suppressing Java access checks, but when the request is not permitted, `setAccessible(true)` can throw `java.lang.reflect.InaccessibleObjectException`. `trySetAccessible()` is often more convenient if you want to check accessibility without exception handling when JPMS denies access. `setAccessible(false)` resets the flag to its default state.

**Note:** the flag is toggled on **a specific `Field`/`Method`/`Constructor` object**; it does not alter modifiers in a `private` declaration, does not turn a class into `public`, does not edit `module-info.java`, and does not automatically unlock all other Reflection objects.

## 6. What Is Permitted and What Remains Restricted?

| Scenario | What About Same Module? | Explanation |
| --- | --- | --- |
| `public` class and `public` member in two different packages | Accessible normally under Java rules | `exports` is not required between packages **internal to a module** |
| `private` field/method/constructor declared in another class | No direct access just for being in the same module | Can be found via `getDeclared...` and enabled for Reflection |
| Package-private class in another package | Java code outside the package cannot directly refer to it by class name normally | Reflection can find it by name at runtime and open deep access when *same module* holds |
| `protected` member in another package | Java `protected` rules still apply | Same module does not replace inheritance/receiver rules |
| `final` field | Can be granted deep read access; modifying values has separate restrictions | In particular, `static final` fields, record `final` fields, and hidden class `final` fields cannot be written via `setAccessible(true)` alone |
| `static` member | Lookup/enabling still follows the rules above | Check/invoke operations use `null` receiver when required by the API |
| A utility performing Reflection from another module | Must evaluate **the module of the utility actually making the call** | Originating a request from the target module is not enough to give the utility same-module permission |

For `final` fields, do not treat a successful `trySetAccessible()` as a guarantee that `Field#set` will be able to write. Java documentation distinguishes **read** permission from the ability to **write** non-modifiable final fields; additionally, mutating final fields via Reflection can violate optimization assumptions and object immutability.

### Package-Private Class in Another Package of the Same Module

Suppose `lesson.domain.Internal` is a **package-private top-level class**. Code in `lesson.app` cannot `import lesson.domain.Internal;` and use that type directly. However, a Reflection utility running in the same module can look up the class by its runtime name, obtain `Class<?>`, read metadata, and evaluate appropriate access permissions. You should not treat Reflection permissions as an excuse to skip clear API design when only `public` data is needed.

## 7. Pay Attention to the Module Where the API Is Called, Not Just the Business Flow

Consider an application in module `business.app`:

~~~text
business.app
  ├── business.Secret
  └── business.Main
reflection.helper
  └── helper.Accessor
~~~

If `business.Main` directly calls `field.trySetAccessible()` on a field of `business.Secret`, the module condition can be *same module*. However, if `Main` passes the `Field` object to `helper.Accessor` and **`Accessor` itself** calls `trySetAccessible()`, the caller is now in `reflection.helper`. Permission is evaluated against the caller's module at the call site; if the target package is not opened appropriately, the deep reflection request may be rejected.

The architectural example above only illustrates the distinction, not a standalone runnable program. When using serialization libraries, dependency injection, mappers, or test frameworks, identify **which class in which module actually makes the Reflection call**. That is why code that works when written directly inside an application module can fail when moved into a helper library in another module.

## 8. Common Mistakes

1. **Equating "same module" with "same package".** JPMS does not change package-private scope or `protected` rules. Two internal packages are still two different packages.
2. **Assuming `getDeclaredField()` returning a `Field` means it is already readable.** A successful lookup only confirms metadata exists; you must check `canAccess` or validly enable access before calling `get`/`set`.
3. **Assuming `getDeclaredMethod()` automatically finds inherited methods.** "Declared" APIs find members declared by the class itself; if you need an inherited `public` method, consider `getMethod()`. This is independent of JPMS.
4. **Adding `exports` or `opens` just because there are two packages in the same module.** Within the same module, internal source access and Reflection's same-module branch have their own rules.
5. **Comparing `Module#getName()` instead of `Module` objects.** For unnamed modules, `getName()` can be `null` for many distinct modules. Use `==` if the goal is to verify exact same-module identity.
6. **Ignoring the return value of `trySetAccessible()`.** The method returns a `boolean`, and changing modules, relocating a helper, or using another module can make the request no longer eligible.
7. **Passing the wrong receiver to `canAccess`.** Constructors and static members require `null`; instance members require an instance object of the proper type.
8. **Assuming enabling access lets you modify `static final`.** Reflection does not turn every immutable field into a writable one; non-modifiable final restrictions still hold.
9. **Relying on `--add-opens` to run a same-module example.** The example in this lesson does not need that flag; if you have to open a package, recheck which module holds the actual caller and the application boundaries.

## 9. Self-Check

**Question 1.** In named module `demo.same`, can `lesson.app.Main` call `public static Vault.create()` from `lesson.domain.Vault` when `module-info.java` lacks `exports lesson.domain;`?

**Answer:** Yes, if `Vault` and the method are `public` and both packages are in the same module. `exports` pertains primarily to access from other modules.

**Question 2.** If `token` is `private`, why does `getDeclaredField("token")` find it while `field.canAccess(vault)` initially returns `false`?

**Answer:** The lookup returns metadata even for directly declared private members; `canAccess` checks usage permission under Java rules and current accessibility state. `Main` is a different class and lacks normal private access to `Vault`.

**Question 3.** When `Main` and `Vault` are in the same module, what can `trySetAccessible()` return on a private field?

**Answer:** Under the normal conditions of the example, it returns `true` via the same-module permission branch. Afterward it can be read via `Field#get`; do not infer that every write to a final field is also valid.

**Question 4.** If a helper in another module executes `trySetAccessible()`, is it still "same-module" because `Main` called the helper?

**Answer:** No. The condition checks whether the class **executing the call** is in the same module as the declaring class. The helper in the other module must be evaluated under the corresponding JPMS rules.

**Question 5.** How can you accurately check if two classes are in the same module?

**Answer:** `First.class.getModule() == Second.class.getModule()`. Do not merely compare module names, especially with unnamed modules and multiple class loaders.

**Takeaway:** *Same module* unlocks Reflection's ability to bypass Java access checks on members of that module, yet **does not erase `private`/`protected`/package-private rules in Java source**. The proper flow is to verify the caller's module, locate the member by name/signature, check access status, enable permission only when truly needed and permitted, and then read/invoke/instantiate.

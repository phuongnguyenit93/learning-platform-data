# public, protected, private, and package-private in Java Reflection

## 1. Goal and context

When using Java Reflection to inspect a class at runtime, two questions must be kept separate:

1. **What access level is the member declared with?** Read the flags of the class, method, field, or constructor via `getModifiers()` and `java.lang.reflect.Modifier`.
2. **Can the current code use that member?** Java's access rules are still checked when invoking a method, reading/writing a field, or instantiating an object via reflection. Finding a member does not automatically grant permission to use it.

For example, `getDeclaredMethod("secretCode")` can find a `private` method; calling `Method.invoke(...)` from an external class can still throw `IllegalAccessException`.

This lesson focuses on the **four access levels**, how to read them via reflection, the difference between the `get...` and `getDeclared...` member-lookup APIs, and the limits of overriding access checks. Other flags such as `static`, `final`, and `abstract` are mentioned only when needed to distinguish them from access modifiers.

## 2. Java language access rules

| Access level | Declaration | Who can access under language rules? |
| --- | --- | --- |
| `public` | Has the `public` keyword | Code in any package, provided the declaring type itself is also accessible; modules may add `exports` boundaries. |
| `protected` | Has the `protected` keyword | Code in the same package; outside the package, subclass code is permitted under the conditions of the `protected` rule, including restrictions on the receiver object for instance members. |
| package-private | **No** access keyword written | Code in the same package. "Default access" is sometimes used to refer to this level, though no `package-private` keyword exists in Java. |
| `private` | Has the `private` keyword | Only within the declaring type and nested types that have corresponding access under Java rules. |

Common points of confusion:

- **Same package does not mean any arbitrary directory:** a package is defined by the `package` declaration; `com.example` and `com.example.internal` are two different packages.
- **`protected` does not mean all code outside the package can use it:** the inheritance relationship and the type of the expression referencing the object can both affect access rights.
- **`private` does not mean reflection cannot see it:** Reflection can read declaration information; performing the operation is a separate step.
- **Both the class's and the member's access levels apply:** a `public` method inside a package-private top-level type does not automatically make that type public to code in another package.
- Top-level types can only be declared `public` or package-private. Member types nested inside another type can be declared `protected` or `private`; local classes and anonymous classes have their own rules.

## 3. Reading access levels with Modifier

`Class<?>`, `Method`, `Field`, and `Constructor<?>` all provide `getModifiers()`, which returns an **`int` bit mask**. Use the bit-checking methods instead of comparing the flag number to a single constant:

~~~java
int flags = method.getModifiers();

if (Modifier.isPublic(flags)) {
    // public
} else if (Modifier.isProtected(flags)) {
    // protected
} else if (Modifier.isPrivate(flags)) {
    // private
} else {
    // package-private for a method's access modifier
}
~~~

The snippet above is illustrative code in a context that already has a `method` variable and imports `java.lang.reflect.Modifier`; the complete program is in section 5.

- `Modifier.isPublic(flags)`, `isProtected(flags)`, and `isPrivate(flags)` accurately check each access bit.
- **There is no `Modifier.isPackagePrivate(...)`.** For a method/field/constructor/class whose access level is being inspected, package-private means *none of the three bits* `public`, `protected`, `private` are set.
- `Modifier.toString(flags)` renders the string of keywords carried by the mask. If it is only package-private and has no other flags, the string may be empty (`""`). If there are `static` or `final` flags, the string may contain those words; therefore do not conclude that only an empty `toString(flags)` means package-private.
- `flags == Modifier.PUBLIC` is error-prone: a `public static` method has both the `PUBLIC` and `STATIC` bits; use `Modifier.isPublic(flags)`.

Example:

~~~java
Method method = SomeClass.class.getDeclaredMethod("run");
System.out.println(Modifier.toString(method.getModifiers()));
~~~

This is also illustrative code, assuming `SomeClass` declares a no-argument `run()`. If the method is declared `public static void run()`, the printed string is `public static`. Do not rely on the element order of `getDeclaredMethods()` when generating reports; the API does not guarantee ordering.

## 4. Finding a member vs being permitted to access it

| `Class` API | Members that can be found | Inheritance scope |
| --- | --- | --- |
| `getMethod(name, parameterTypes...)` / `getMethods()` | `public` methods | Includes inherited public methods per API rules |
| `getDeclaredMethod(name, parameterTypes...)` / `getDeclaredMethods()` | All access levels, provided declared in that class/interface itself | Does not search superclasses automatically |
| `getField(name)` / `getFields()` | `public` fields | Accounts for inherited public fields |
| `getDeclaredField(name)` / `getDeclaredFields()` | All access levels of directly declared fields | Does not search superclasses |
| `getConstructor(parameterTypes...)` / `getConstructors()` | `public` constructors | Constructors are not inherited |
| `getDeclaredConstructor(parameterTypes...)` / `getDeclaredConstructors()` | Directly declared constructors, all access levels | Constructors are not inherited |

For example: for a `private void check()` method, `getDeclaredMethod("check")` can return the `Method`, whereas `getMethod("check")` throws `NoSuchMethodException`. A *not found* exception (`NoSuchMethodException`) is different from a *not permitted to invoke* exception (`IllegalAccessException`).

A method signature also includes its parameter type list: if there is `void check(String value)`, you need to call `getDeclaredMethod("check", String.class)`; passing only `"check"` will not find the one-parameter method. For overloaded methods, always pass the exact parameter types.

After finding a `Method`, `Field`, or `Constructor`, Java still checks validity when calling `invoke(...)`, `get(...)`, `set(...)`, or `newInstance(...)`. Reading metadata is not the same as permission to invoke/read/write.

## 5. Runnable Java 17 program: reading and attempting access across all four levels

We place the class containing the members in package `lesson.api`, and the reflection code in package `lesson.client` to clearly see crossing package boundaries.

**File 1 — `src/lesson/api/MemberBox.java`:**

~~~java
package lesson.api;

public class MemberBox {
    public String publicCode() { return "public value"; }
    protected String protectedCode() { return "protected value"; }
    String packageCode() { return "package value"; }
    private String secretCode() { return "private value"; }
}
~~~

**File 2 — `src/lesson/client/ReflectAccess.java`:**

~~~java
package lesson.client;

import java.lang.reflect.Method;
import java.lang.reflect.Modifier;
import lesson.api.MemberBox;

public class ReflectAccess {
    public static void main(String[] args) throws Exception {
        Class<MemberBox> type = MemberBox.class;
        for (String name : new String[] {
                "publicCode", "protectedCode", "packageCode", "secretCode" }) {
            Method method = type.getDeclaredMethod(name);
            System.out.println(name + ": " + visibility(method.getModifiers()));
        }

        System.out.println("getMethod(publicCode): "
                + type.getMethod("publicCode").getName());
        try {
            type.getMethod("secretCode");
        } catch (NoSuchMethodException ex) {
            System.out.println("getMethod(secretCode): not found");
        }

        MemberBox box = new MemberBox();
        Method secret = type.getDeclaredMethod("secretCode");
        try {
            secret.invoke(box);
        } catch (IllegalAccessException ex) {
            System.out.println("invoke before override: IllegalAccessException");
        }
        boolean opened = secret.trySetAccessible();
        System.out.println("trySetAccessible(secretCode): " + opened);
        if (opened) {
            System.out.println("invoke after override: " + secret.invoke(box));
        }
    }

    private static String visibility(int flags) {
        if (Modifier.isPublic(flags)) return "public";
        if (Modifier.isProtected(flags)) return "protected";
        if (Modifier.isPrivate(flags)) return "private";
        return "package-private";
    }
}
~~~

**Compile and run from the directory containing `src/` (Java 17 or later, using classpath):**

~~~bash
mkdir -p out
javac --release 17 -d out src/lesson/api/MemberBox.java src/lesson/client/ReflectAccess.java
java -cp out lesson.client.ReflectAccess
~~~

On PowerShell, you can replace `mkdir -p out` with `New-Item -ItemType Directory -Force out`. The `out` directory contains `.class` files matching the package structure.

**Exact stdout in the classpath example above:**

~~~text
publicCode: public
protectedCode: protected
packageCode: package-private
secretCode: private
getMethod(publicCode): publicCode
getMethod(secretCode): not found
invoke before override: IllegalAccessException
trySetAccessible(secretCode): true
invoke after override: private value
~~~

**Output explanation:**

1. `getDeclaredMethod` retrieves all four declarations, so we can read all four levels using `getModifiers()`.
2. `getMethod("publicCode")` finds the public member; `getMethod("secretCode")` does not find the private member and throws `NoSuchMethodException`.
3. `ReflectAccess` is in a different package and is outside the scope permitted to access `private secretCode()`; the initial `invoke` call throws `IllegalAccessException`.
4. `trySetAccessible()` returns `true` here because both classes are code on the classpath, belong to the unnamed module, and have no module barrier blocking deep reflection. Once successful, the same `Method` object can be invoked via `invoke`. This is **not guaranteed** to succeed for every class in a named module or another library.

If you want to test `protectedCode` or `packageCode`, change the name when calling `getDeclaredMethod`. From `lesson.client.ReflectAccess`, a normal `invoke` call is also access-checked; having metadata does not make the code a subclass or in the same package.

## 6. `canAccess`, `trySetAccessible`, and the module system

Java provides three common operations on reflective objects:

- `method.canAccess(receiver)`: asks whether at that moment the current caller can access via this `Method` object; use an instance of the right type as `receiver` for instance methods, or `null` for static methods. For fields or constructors, the receiver argument must also match the corresponding API contract.
- `method.trySetAccessible()`: **attempts** to suppress Java language access checks for the reflection object; returns `true` if successful and `false` when access cannot be enabled due to access restrictions. In some situations a security exception may occur.
- `method.setAccessible(true)`: requests disabling access checks; if a module barrier disallows it, it may throw `java.lang.reflect.InaccessibleObjectException`.

Since Java 9, JPMS (Java Platform Module System) distinguishes:

| Module declaration | Practical meaning |
| --- | --- |
| `exports p;` | Allows other modules to use `public` types and accessible `public` members of package `p` via normal APIs; does not by default allow reflection to open private members. |
| `opens p;` | Allows deep reflection access into package `p` under the package-opening mechanism, including non-public members when the operation is valid. |
| Neither `exports` nor `opens` | Code in other modules is generally more restricted, even if reflection can see member names. |

A package can be targetedly opened at runtime for diagnostics, e.g. depending on configuration: `--add-opens java.base/java.lang=ALL-UNNAMED`. This is a powerful permission mechanism; you should not add it broadly or rely on it as normal API design. For code in different named modules, the result of `trySetAccessible()` depends on module relationships, packages, and actual open permissions.

**Do not confuse `AccessibleObject` with changing the declaration:** calling `trySetAccessible` does not turn a private method into a public one in the class file. `method.getModifiers()` still reports `private`. It only affects access checks on the adjusted reflection object within permitted bounds. Other restrictions, such as the immutability of certain `final` fields, still remain.

## 7. Common mistakes and how to handle them

| Misconception / error | Why it is wrong | What to do |
| --- | --- | --- |
| `getMethods()` returns every method | It only selects public methods per the API rules | Use `getDeclaredMethods()` when you need to inspect non-public declarations, and traverse superclasses separately if needed |
| `getDeclaredMethods()` includes superclass declarations | It only returns methods declared in the queried class/interface itself | Traverse `getSuperclass()` and `getDeclaredMethods()` at each level if that is the goal |
| Finding a `Method` means you can invoke it | Discovering metadata and having execution permission are two different steps | Distinguish `NoSuchMethodException`, `IllegalAccessException`, and `InvocationTargetException` |
| `Modifier.toString(flags).isEmpty()` is the only way to detect package-private | A package-private declaration can still carry flags like `static` or `final` | Check that all three bits `public/protected/private` are absent |
| `flags == Modifier.PUBLIC` identifies every public method | A method can simultaneously be `public static` or `public final` | Use `Modifier.isPublic(flags)` |
| `protected` is always accessible from another package if a subclass exists somewhere | The access rule is based on the access site and the receiver object, not just the existence of a subclass | Check the package/inheritance context of the caller itself |
| `setAccessible(true)` always succeeds | A module may not open the package to the caller | Prefer public APIs; if needed, design `opens` deliberately and handle failure |
| `private` is "absolute data security" | Modifiers are primarily language-level API encapsulation boundaries, not a security mechanism across all runtime environments | Use appropriate security mechanisms for sensitive data while maintaining good encapsulation |

When looking up methods on an inheritance hierarchy, distinguish `getMethod` (which can find inherited public methods) from `getDeclaredMethod` (which only finds direct declarations). When printing lists from `getDeclaredMethods()`, sort by name/signature if deterministic output is needed because reflection array order is not guaranteed.

## 8. Self-check exercises

1. Add `public static String sharedCode()` to `MemberBox`. Predict the results of `Modifier.isPublic(method.getModifiers())` and `Modifier.toString(method.getModifiers())`. **Answer:** `true`; the string contains `public static`.
2. Add `private MemberBox(int seed)` alongside a no-arg constructor explicitly declared as public. How do `getConstructor(int.class)` and `getDeclaredConstructor(int.class)` differ? **Answer:** The first API throws `NoSuchMethodException`, while the second finds the private constructor, though invoking it still requires checking access rights.
3. Move `ReflectAccess` into package `lesson.api`. For `packageCode()`, is `invoke` permitted? **Answer:** permitted if the calling class is indeed in the same package and receives a valid object; for `private`, the private boundary still applies.
4. Move `MemberBox` into a named module with an unopened package. Can you conclude that `trySetAccessible()` will definitely return `true` as in the classpath example? **Answer:** no; it depends on whether the package is opened to the caller's module.

**Key takeaway:** Reflection can *observe* access levels via `getModifiers()`, but actual operations must still pass Java's access checks and module boundaries. Choose `getDeclared...` to inspect internal declarations, `get...` to find appropriate public members, and only request deep access when truly necessary.

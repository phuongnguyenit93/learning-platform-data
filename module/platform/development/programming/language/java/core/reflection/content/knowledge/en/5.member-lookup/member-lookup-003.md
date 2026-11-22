# Java Reflection: Member Lookup with `getDeclaredField()`, `getDeclaredMethod()`, and `getDeclaredConstructor()`

Once you have a `Class<?>` object, Reflection lets you look up the exact **field**, **method**, and **constructor** **declared directly** in that type. The three methods `getDeclaredField()`, `getDeclaredMethod()`, and `getDeclaredConstructor()` are the primary tools for this job. They can find `private`, `protected`, package-private, and `public` members alike, but **finding a member does not automatically allow reading, invoking, or instantiating through that member**.

This lesson focuses on looking up members by name/signature, the difference between declared members and inherited members, how to handle exact method signatures, return values, exceptions, and access permissions when using the found Reflection objects.

## 1. From `Class<?>` to the Three Member Kinds

The three APIs reside on `java.lang.Class`:

| API | Returned Object | Lookup Condition | Excludes |
| --- | --- | --- | --- |
| `getDeclaredField(String name)` | `Field` | Field named `name`, declared directly in the class/interface under inspection | Fields only inherited from a superclass |
| `getDeclaredMethod(String name, Class<?>... parameterTypes)` | `Method` | Directly declared method, matching name and exact **parameter type sequence** | Methods only inherited; methods with the same name but different parameter types/count |
| `getDeclaredConstructor(Class<?>... parameterTypes)` | `Constructor<T>` | Constructor declared by the class, with the requested parameter type sequence | Superclass constructors; constructors with a different signature |

Typical syntax:

~~~java
Class<?> type = Example.class;

Field field = type.getDeclaredField("value");
Method method = type.getDeclaredMethod("convert", String.class, int.class);
Constructor<?> constructor = type.getDeclaredConstructor(String.class);
~~~

This is an **API illustrative snippet**; it only works when the `Example` class actually has the corresponding declarations. If the member is not found, the method throws a checked exception (`NoSuchFieldException` or `NoSuchMethodException`).

The word *declared* carries two meanings to remember:

1. **Does not filter by access level:** `private` members can still be found as `Field`, `Method`, or `Constructor`.
2. **Inspects only direct declarations:** fields and methods located in a superclass do not appear when calling `getDeclaredField`/`getDeclaredMethod` on a subclass. Constructors are never inherited anyway.

The plural forms are `getDeclaredFields()`, `getDeclaredMethods()`, `getDeclaredConstructors()`. They are used to discover all declared members; when the name/signature is already known, use the singular APIs to target the exact member. The order of elements in the resulting `getDeclared*()` plural arrays is not guaranteed.

## 2. `getDeclaredField(String name)`: Finding a Field by Name

`getDeclaredField("code")` looks up the field named `code` directly on the `Class` object under inspection. It returns `java.lang.reflect.Field`, from which metadata can be read:

- `field.getName()`: field name.
- `field.getType()`: runtime type of the field as a `Class<?>`.
- `field.getGenericType()`: metadata of the generic type when available.
- `field.getDeclaringClass()`: class/interface that actually declares the field.
- `field.getModifiers()`: access flags and modifiers; use `Modifier.isPrivate(...)`, `Modifier.isStatic(...)` when needed.
- `field.get(target)` or methods like `field.getInt(target)`: read the value **after satisfying access rules**.

Fields do not have parameter lists or overloads by signature. A Java class cannot declare two fields with the same name in the same valid class declaration; however, a subclass can **hide** a field of the same name in the superclass. In that case `Child.class.getDeclaredField("code")` finds `Child`'s field, while `Parent.class.getDeclaredField("code")` finds `Parent`'s field if each class declares that field itself.

**Common mistake:** assuming `Child.class.getDeclaredField("inherited")` finds a field of `Parent`. That request is outside the *declared* scope. If the field is `public`, `Child.class.getField("inherited")` can find the inherited field; if it is not public, you must traverse `getSuperclass()` according to your business requirements and then look up on the declaring class.

## 3. `getDeclaredMethod(String name, Class<?>... parameterTypes)`: Name + Parameter Signature

To find a specific method, pass the method name and the `Class<?>` objects representing the **declared parameter types in exact order**:

~~~java
type.getDeclaredMethod("save", String.class, int.class);
type.getDeclaredMethod("refresh"); // Method with no parameters
~~~

Important rules:

- Distinguish **parameter count and order**: `save(String,int)` differs from `save(int,String)`.
- Distinguish **primitives and wrappers**: `int.class` differs from `Integer.class`.
- Distinguish **arrays and elements**: `String[].class` differs from `String.class`.
- A `String... values` parameter in source code is represented as `String[]` in the Reflection signature; during lookup you must use `String[].class`, not pass multiple `String.class` arguments.
- Automatic *autoboxing*, *widening* (`int` to `long`), or type conversion is not applied during **lookup**. Those rules of normal Java calls are not used to search for methods here.
- For generic parameters such as `List<String>`, the runtime signature undergoes *type erasure*: look up with `List.class`. Use `getGenericParameterTypes()` on `Method` if you need to analyze generic metadata.
- **Do not pass the return type** to `getDeclaredMethod`. The API accepts the name and parameter types; after obtaining `Method`, read `method.getReturnType()` or `getGenericReturnType()` to inspect the result type. Bytecode may contain bridge/synthetic methods; you should not assume the `getDeclaredMethods()` list contains only methods hand-written in source code.

If two overloads are `parse(String)` and `parse(int)`, the name is the same, but arguments `String.class` and `int.class` select the right method. `static` methods are looked up the same way, and you can then check `Modifier.isStatic(method.getModifiers())`.

## 4. `getDeclaredConstructor(Class<?>... parameterTypes)`: Constructor Lookup

Constructors do not have a separate method name in this call: only the constructor's parameter type list needs to be passed.

~~~java
Constructor<?> noArg = type.getDeclaredConstructor();
Constructor<?> withName = type.getDeclaredConstructor(String.class);
~~~

`getDeclaredConstructor()` with no arguments requires a **genuinely parameterless constructor**; it does not mean "get any constructor" or "generate a default constructor". If the class only declares `Example(String)`, calling `getDeclaredConstructor()` will throw `NoSuchMethodException`. If Java automatically generates a default constructor, that constructor can be found when the signature matches.

Unlike methods/fields, constructors **are not inherited**. Therefore both `getDeclaredConstructor` and `getConstructor` apply only to constructors of the class under inspection itself; the major difference is that `getConstructor` finds only `public` constructors, whereas `getDeclaredConstructor` can find non-`public` constructors.

Some cases to know:

- An `abstract` class still has constructors for subclasses to call via `super(...)`, but cannot be instantiated directly via `Constructor#newInstance`.
- A **non-`static`** member class may have a hidden parameter representing the enclosing class instance. For example, source constructor `Outer.Inner(int)` often appears in Reflection with parameters `Outer.class, int.class`. When an expected signature is not found, inspect `getParameterTypes()` of the declared constructors.
- Enums and some compiler-generated classes have special constructor details; do not assume every runtime signature matches source code identically.

## 5. Complete Example: How Does Declared Differ from Inherited?

Create the file **`DeclaredLookupDemo.java`**. Within this same file, only `DeclaredLookupDemo` is a `public` class; the two helper classes use distinct names to avoid package structure dependencies:

~~~java
import java.lang.reflect.Constructor;
import java.lang.reflect.Field;
import java.lang.reflect.Method;

class LookupParent {
    public String inheritedField = "parent";

    public void inheritedMethod() {
    }
}

class LookupChild extends LookupParent {
    private String code;

    private LookupChild(String code) {
        this.code = code;
    }

    private String convert(String input) {
        return input.toUpperCase();
    }

    public int convert(int number) {
        return number * 2;
    }
}

public class DeclaredLookupDemo {
    public static void main(String[] args) throws ReflectiveOperationException {
        Class<LookupChild> type = LookupChild.class;

        Field field = type.getDeclaredField("code");
        Method stringMethod = type.getDeclaredMethod("convert", String.class);
        Method intMethod = type.getDeclaredMethod("convert", int.class);
        Constructor<LookupChild> constructor =
                type.getDeclaredConstructor(String.class);

        System.out.println("Field: " + field.getName()
                + " -> " + field.getType().getSimpleName());
        System.out.println("Method 1: " + stringMethod.getName()
                + "(String) -> " + stringMethod.getReturnType().getSimpleName());
        System.out.println("Method 2: " + intMethod.getName()
                + "(int) -> " + intMethod.getReturnType().getSimpleName());
        System.out.println("Constructor: "
                + constructor.getDeclaringClass().getSimpleName()
                + "(String)");

        try {
            type.getDeclaredField("inheritedField");
        } catch (NoSuchFieldException expected) {
            System.out.println("Declared inheritedField: not found");
        }

        System.out.println("Public inherited field: "
                + type.getField("inheritedField")
                        .getDeclaringClass().getSimpleName());

        try {
            type.getDeclaredMethod("inheritedMethod");
        } catch (NoSuchMethodException expected) {
            System.out.println("Declared inheritedMethod: not found");
        }

        System.out.println("Public inherited method: "
                + type.getMethod("inheritedMethod")
                        .getDeclaringClass().getSimpleName());
    }
}
~~~

Run with JDK 17 or later:

~~~bash
javac DeclaredLookupDemo.java
java DeclaredLookupDemo
~~~

**Stdout:**

~~~text
Field: code -> String
Method 1: convert(String) -> String
Method 2: convert(int) -> int
Constructor: LookupChild(String)
Declared inheritedField: not found
Public inherited field: LookupParent
Declared inheritedMethod: not found
Public inherited method: LookupParent
~~~

Why are the results as shown above?

1. `code`, the two `convert` overloads, and the constructor `LookupChild(String)` are all **declared directly** in `LookupChild`, so the three `getDeclared...` APIs find them whether `private` or `public`.
2. `inheritedField` and `inheritedMethod` are **declared only in `LookupParent`**; looking them up with `getDeclared...` on `LookupChild` fails.
3. Both inherited members are `public`, so `getField`/`getMethod` on `LookupChild` returns the member with `getDeclaringClass() == LookupParent.class`.

Note: this example **only looks up and prints metadata**; it does not read field `code` directly, does not invoke `convert`, and does not create `LookupChild` from the private constructor. This is the important boundary between *lookup* and *access*.

## 6. Lookup Does Not Mean Access Permission: `trySetAccessible()`

A `Field`, `Method`, or `Constructor` found via `getDeclared...` is still subject to access rules when using `Field#get`/`set`, `Method#invoke`, or `Constructor#newInstance`. For members not accessible from the calling code, some operations may throw `IllegalAccessException` if appropriate permission has not been granted.

The base class `AccessibleObject` provides:

- `canAccess(target)`: checks current access permission for the member; pass the target object for instance members, `null` for static members and constructors.
- `trySetAccessible()`: attempts to enable bypassing Java access checks and returns `true` if successful, `false` if it cannot be granted. This attempt is **not guaranteed to succeed**.
- `setAccessible(true)`: requests enabling bypassing checks; may throw `InaccessibleObjectException` in cases where Java modules do not permit it.

The following example runs as an application without a `module-info.java` declaration (unnamed module), so the application code in the example can deep-access its own classes. Create the file **`DeclaredAccessDemo.java`**:

~~~java
import java.lang.reflect.Constructor;
import java.lang.reflect.Field;
import java.lang.reflect.Method;

class SecretBox {
    private String value;

    private SecretBox(String value) {
        this.value = value;
    }

    private String reveal(String suffix) {
        return value + suffix;
    }
}

public class DeclaredAccessDemo {
    public static void main(String[] args) throws ReflectiveOperationException {
        Class<SecretBox> type = SecretBox.class;

        Constructor<SecretBox> constructor =
                type.getDeclaredConstructor(String.class);
        System.out.println("Constructor access: "
                + constructor.trySetAccessible());

        SecretBox box = constructor.newInstance("data");

        Field field = type.getDeclaredField("value");
        System.out.println("Field access: " + field.trySetAccessible());
        System.out.println("Field value: " + field.get(box));

        Method method = type.getDeclaredMethod("reveal", String.class);
        System.out.println("Method access: " + method.trySetAccessible());
        System.out.println("Method result: " + method.invoke(box, "!"));
    }
}
~~~

~~~bash
javac DeclaredAccessDemo.java
java DeclaredAccessDemo
~~~

**Stdout under the stated running conditions:**

~~~text
Constructor access: true
Field access: true
Field value: data
Method access: true
Method result: data!
~~~

**Execution flow explanation:**

1. Find the private constructor matching `String.class` and call `trySetAccessible()` before `newInstance("data")`.
2. Find the private field `value`, attempt to grant access, then read using `field.get(box)`.
3. Find the private method `reveal(String)`, attempt to grant access, then call `method.invoke(box, "!")`. The return type is `Object`; here the resulting string is `data!`.

In real programs, you must **check** the result of `trySetAccessible()` before operating. If it returns `false`, do not assume the operation will succeed. Avoid opening reflective access for untrusted data and unnecessary cases; prefer `public` APIs whenever possible.

### Java Platform Module System (JPMS) Since Java 9

Reflection access is also restricted by module boundaries. A package declared with `exports` usually allows modules to read `public` members under normal access rules; to perform **deep reflection** on non-`public` members in another module, the package must usually be properly `opens` to the module performing Reflection (or have an equivalent permission mechanism). `getDeclaredMethod()` can still return metadata, while `trySetAccessible()` may return `false`, and `setAccessible(true)` may throw `InaccessibleObjectException`. Do not use `--add-opens` as a default workaround for application code; opening packages requires explicit decisions at module boundaries.

## 7. Exact Signature Example: Varargs, Primitive/Wrapper, Generic Erasure

Create the file **`ExactSignatureDemo.java`**:

~~~java
import java.lang.reflect.Method;
import java.util.List;

class SignatureTarget {
    private void run(int count, String... tags) {
    }

    private void accept(List<String> values) {
    }
}

public class ExactSignatureDemo {
    public static void main(String[] args) throws NoSuchMethodException {
        Class<SignatureTarget> type = SignatureTarget.class;

        Method run = type.getDeclaredMethod(
                "run", int.class, String[].class);
        Method accept = type.getDeclaredMethod("accept", List.class);

        System.out.println("Found: " + run.getName());
        System.out.println("Varargs: " + run.isVarArgs());
        System.out.println("Generic erased parameter: "
                + accept.getParameterTypes()[0].getName());

        try {
            type.getDeclaredMethod("run", Integer.class, String[].class);
        } catch (NoSuchMethodException expected) {
            System.out.println("Integer.class instead of int.class: not found");
        }
    }
}
~~~

~~~bash
javac ExactSignatureDemo.java
java ExactSignatureDemo
~~~

**Stdout:**

~~~text
Found: run
Varargs: true
Generic erased parameter: java.util.List
Integer.class instead of int.class: not found
~~~

This shows that `String...` is `String[]` in the Reflection signature; `int.class` is not equivalent to `Integer.class` when **looking up a method**; and `List<String>` uses `List.class` after type erasure. If the declared `List<String>` parameter is needed, you can continue reading `accept.getGenericParameterTypes()`.

Overloads are not evaluated based on convertibility at the call site. For example, Java code may select an overload by converting `int` to `long`, yet `getDeclaredMethod("run", long.class, ...)` **does not** find `run(int, ...)`.

## 8. Identifying the Right Declaring Class When Walking Up the Hierarchy

When `Child.class.getDeclaredField("id")` fails to find a field located in `Parent`, switching to `getField("id")` only solves it if that field is `public`. For non-public fields, look up on the exact declaring type such as `Parent.class.getDeclaredField("id")` or walk `getSuperclass()` manually according to business policy. The same distinction applies to methods, while constructors are not inherited.

If a subclass hides a field of the same name in a superclass, both `Field` objects exist separately; use `getDeclaringClass()` to identify the owner. Finding metadata still does not guarantee permission to read/write/invoke: check access permissions as in section 6. Multi-level traversal and conflict resolution are developed further in the lesson on building a cross-hierarchy lookup policy.

## 9. Exceptions and Error Handling Workflow

| Operation | Situation | What to Handle |
| --- | --- | --- |
| `getDeclaredField("x")` | No field named `x` directly on the type | `NoSuchFieldException` (checked) |
| `getDeclaredMethod("m", ...)` | Wrong name or wrong parameter types/count/order | `NoSuchMethodException` (checked) |
| `getDeclaredConstructor(...)` | No constructor with exact signature | `NoSuchMethodException` (checked) |
| `Field#get`, `Method#invoke`, `Constructor#newInstance` | No access permission for member | Possibly `IllegalAccessException` |
| `Method#invoke` | The invoked method itself throws an exception | `InvocationTargetException` wraps the original exception; use `getCause()` |
| `Constructor#newInstance` | Constructor runs and throws an exception | `InvocationTargetException` wraps the original exception |
| `setAccessible(true)` | JPMS or other restriction denies opening access | Possibly `InaccessibleObjectException` (runtime) |

Signature mismatch errors should usually be handled at the **lookup step**, rather than only catching a generic exception after calling. For example:

~~~java
try {
    Method method = type.getDeclaredMethod("process", String.class);
    // Check modifiers, access permissions, return type before invoking.
} catch (NoSuchMethodException e) {
    // Name "process" or signature (String) is not declared on type.
}
~~~

The snippet above assumes `type` is a valid `Class<?>`. In large programs, error messages should clearly log the class name, member name, and parameter type list (carefully avoiding logging secret data); this helps distinguish "not found" from "found but insufficient permissions".

### Checklist When Lookup Fails

1. **Is it the right `Class<?>`?** `getDeclared...` does not automatically climb to the superclass.
2. **Are spelling and case correct?** Member names are case-sensitive.
3. **Are parameter count, order, and types exact?** `int.class`, `Integer.class`, `String.class`, and `String[].class` are different types.
4. **Does a no-arg constructor actually exist?** `getDeclaredConstructor()` does not create a new constructor.
5. **Does a non-`static` nested class have an enclosing-class parameter?** Inspect `getDeclaredConstructors()` and `getParameterTypes()`.
6. **Is a generic type erased?** `List<String>` in runtime parameters corresponds to `List.class`.
7. **Found but unusable?** Check `canAccess`, `trySetAccessible`, module boundaries, and exceptions during `invoke`/`newInstance`.

## 10. Extension: Metadata and Compiler-Generated Members

The found objects continue to provide useful information:

- `Field#getDeclaringClass()`, `Method#getDeclaringClass()`, and `Constructor#getDeclaringClass()` identify the declaring class/interface.
- `Method#getParameterTypes()` and `Constructor#getParameterTypes()` return the `Class<?>` sequence of the runtime signature. `getGenericParameterTypes()` provides `Type[]` to inspect generic metadata.
- `Method#isBridge()` identifies compiler-generated bridge methods for certain generic/override cases; `Member#isSynthetic()` can help identify compiler-generated members. Do not infer that every member appearing in Reflection is a hand-written source declaration.
- `Modifier.toString(member.getModifiers())` gives a modifier description. For example `private static`, `public final`; you should not check modifiers using string comparisons when you only need to test a specific flag.

For metadata-reading frameworks, a clear workflow is: determine `Class<?>` → choose `getDeclared...` or `get...` by scope → use exact name/signature → check types and modifiers → check access permissions → only then operate on values or invoke the member. Do not add `setAccessible(true)` everywhere by default; this operation may fail or be disallowed by module boundaries.

## 11. Self-Check Comprehension

**Question 1.** Class `Child` inherits `public void ping()` from `Parent` without overriding it. Does `Child.class.getDeclaredMethod("ping")` succeed?

**Answer:** No; it throws `NoSuchMethodException`. `Child.class.getMethod("ping")` can find the inherited `public` method.

**Question 2.** Why does `getDeclaredMethod("send", Integer.class)` fail to find a method declared as `send(int)`?

**Answer:** Lookup matches parameter `Class<?>` objects exactly without applying autoboxing; `int.class` must be passed.

**Question 3.** If a class only has the constructor `private Item(String)`, which method finds this constructor?

**Answer:** `Item.class.getDeclaredConstructor(String.class)`. `getConstructor(String.class)` requires a `public` constructor; `getDeclaredConstructor()` requires no parameters.

**Question 4.** Once a `private Field` is found with `getDeclaredField`, can its value always be read immediately?

**Answer:** Not necessarily. Reflection lookup returns metadata; reading the field still involves access rules and JPMS. Only try `trySetAccessible()` when genuinely necessary and handle the case where it is denied.

**Question 5.** With what arguments is a method declared as `void add(String... tags)` looked up?

**Answer:** `type.getDeclaredMethod("add", String[].class)` because varargs is represented as one array-type parameter in the runtime signature.

**Takeaway:** the three `getDeclared...` APIs answer the question *"What members are declared directly on this type?"*. Accuracy lies in the field name, the method name plus parameter type list, or the constructor parameter type list. After lookup, check metadata and access permissions before working with values or executing the member.
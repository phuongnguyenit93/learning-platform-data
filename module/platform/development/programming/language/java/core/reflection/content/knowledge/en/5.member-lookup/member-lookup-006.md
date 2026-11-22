# Member Lookup by Exact Name and Parameter Types in Java Reflection

Using Reflection, a program can find a method (`Method`), constructor (`Constructor`), or field (`Field`) from a `Class<?>` object at runtime. The key to **exact lookup** is passing the exact member name, the exact number and order of parameter types, while choosing the API that matches the visibility scope. Java Reflection **does not automatically select an overload the way the Java compiler does during a method call**.

## 1. Which APIs Use Name and Parameter Types?

| Member to Find | Only `public` (including inherited when applicable) | Only members declared directly in the class (all access levels) | Lookup Criteria |
| --- | --- | --- | --- |
| Method | `getMethod(String name, Class<?>... parameterTypes)` | `getDeclaredMethod(String name, Class<?>... parameterTypes)` | Name + parameter type list |
| Constructor | `getConstructor(Class<?>... parameterTypes)` | `getDeclaredConstructor(Class<?>... parameterTypes)` | Parameter type list; no name passed |
| Field | `getField(String name)` | `getDeclaredField(String name)` | Field name only; no parameter types passed |

For example, if `UserService` declares `public User find(String key, int limit)`:

```java
Method method = UserService.class.getMethod(
        "find", String.class, int.class);
```

The two `Class` objects in the list must match the types of the first and second parameters **exactly**. The values passed are objects describing types (e.g., `int.class`), not actual argument values (e.g., `42`). When a method has no parameters, `getMethod("name")` suffices.

## 2. Method Matching Conditions

A `getMethod` or `getDeclaredMethod` call matches only when all of the following conditions hold simultaneously:

1. **Exact name match:** `"find"` differs from `"Find"`; names are case-sensitive.
2. **Exact parameter count:** `find(String)` differs from `find(String, int)`.
3. **Exact order:** `find(String, int)` differs from `find(int, String)`.
4. **Exact `Class` for each type:** `int.class` differs from `Integer.class`; `long.class` differs from `int.class`; `Object.class` differs from `String.class`. There is no automatic boxing/unboxing, numeric widening, or parent–child relationship matching **at the lookup step**.
5. **Matching API scope:** `getMethod` only finds eligible `public` methods, including inherited public methods; `getDeclaredMethod` finds methods declared by that class itself, including `private`, but **does not find methods that are only inherited**.

The name and parameter types form the lookup key; **the return type is not passed** to `getMethod`. After finding it, use `method.getReturnType()` to inspect the return type if needed. Similarly, modifiers such as `static`, `final`, or annotations are not part of the lookup parameters; inspect them afterward via `getModifiers()`, `Modifier`, or `getAnnotations()`.

For example, given the signature `void process(int id, String name)`:

| Call | Result |
| --- | --- |
| `getMethod("process", int.class, String.class)` | Matches if the method is `public` within the search scope |
| `getMethod("process", String.class, int.class)` | `NoSuchMethodException`: wrong order |
| `getMethod("process", Integer.class, String.class)` | `NoSuchMethodException`: `Integer` is not `int` |
| `getMethod("process", int.class)` | `NoSuchMethodException`: missing one parameter |
| `getMethod("Process", int.class, String.class)` | `NoSuchMethodException`: wrong name |

Note: when **invoking** a found `Method` via `invoke`, Java may perform certain argument value conversions according to Reflection's own rules. That does not cause `getMethod` to accept approximate signatures.

## 3. Standalone Java 17+ Example

Save all the code below into the file `ExactMemberLookupDemo.java`:

```java
import java.lang.reflect.Method;
import java.lang.reflect.Modifier;
import java.util.Arrays;
import java.util.List;

public class ExactMemberLookupDemo {
    public static class Parent {
        public String inherited(String value) {
            return "parent:" + value;
        }

        public String code = "P";
    }

    public static class Example extends Parent {
        public Example() {}

        private Example(int size) {}

        public String combine(String text, int count) {
            return text + "-" + count;
        }

        public String combine(int value) {
            return "#" + value;
        }

        private void internal(long id) {}

        public void publish(String... labels) {}

        public void save(List<String> names) {}

        private String token = "secret";
    }

    public static void main(String[] args) throws Exception {
        Class<Example> type = Example.class;
        Example example = new Example();

        Method exact = type.getMethod(
                "combine", String.class, int.class);
        System.out.println("exact=" + exact.getName()
                + Arrays.toString(exact.getParameterTypes()));
        System.out.println("invoke=" + exact.invoke(example, "A", 2));
        System.out.println("overload=" + type.getMethod(
                "combine", int.class).invoke(example, 7));

        System.out.println("inherited=" + type.getMethod(
                "inherited", String.class)
                .getDeclaringClass().getSimpleName());
        System.out.println("declaredPrivate=" + Modifier.isPrivate(
                type.getDeclaredMethod(
                        "internal", long.class).getModifiers()));

        System.out.println("varargs=" + type.getMethod(
                "publish", String[].class)
                .getParameterTypes()[0].getTypeName());
        System.out.println("erased=" + type.getMethod(
                "save", List.class).getName());

        System.out.println("ctorPublic=" + type.getConstructor()
                .getParameterCount());
        System.out.println("ctorPrivate=" + Modifier.isPrivate(
                type.getDeclaredConstructor(int.class).getModifiers()));

        System.out.println("fieldInherited=" + type.getField("code")
                .getDeclaringClass().getSimpleName());
        System.out.println("fieldPrivate=" + Modifier.isPrivate(
                type.getDeclaredField("token").getModifiers()));

        try {
            type.getMethod("combine", String.class, Integer.class);
        } catch (NoSuchMethodException e) {
            System.out.println("wrapperMismatch=NoSuchMethodException");
        }

        try {
            type.getDeclaredMethod("inherited", String.class);
        } catch (NoSuchMethodException e) {
            System.out.println("declaredNotInherited=NoSuchMethodException");
        }
    }
}
```

Compile and run from the directory containing the file:

```bash
javac ExactMemberLookupDemo.java
java ExactMemberLookupDemo
```

Expected output:

```text
exact=combine[class java.lang.String, int]
invoke=A-2
overload=#7
inherited=Parent
declaredPrivate=true
varargs=java.lang.String[]
erased=save
ctorPublic=0
ctorPrivate=true
fieldInherited=Parent
fieldPrivate=true
wrapperMismatch=NoSuchMethodException
declaredNotInherited=NoSuchMethodException
```

Interpretation: `combine` has two overloads, so the `Class` list identifies the exact overload to find. The `inherited` method is inherited from `Parent`, so `getMethod` finds it while `Example.class.getDeclaredMethod` does not. Constructor `Example(int)` and method `internal(long)` are `private`, yet their **metadata can still be found** via `getDeclared...` APIs. `code` is an inherited `public` field, whereas `token` is declared `private` directly inside `Example`.

## 4. Parameter Types That Commonly Cause Confusion

### Primitives and Wrappers

`int.class` is the `Class` object for primitive `int`; `Integer.class` is the `Class` object for the wrapper class `java.lang.Integer`. They differ even when a regular Java call can autobox:

```java
// Declared method: void setCount(int count)
type.getMethod("setCount", int.class);      // Correct if public.
type.getMethod("setCount", Integer.class);  // NoSuchMethodException.
```

Similarly, `byte`, `short`, `int`, `long`, `float`, and `double` are not interchangeable during lookup. `Object.class` also cannot substitute for `String.class` merely because `String` is a subtype of `Object`.

### Arrays and Varargs

At the signature level, a parameter declared `String... names` has actual type `String[]`; a method `process(int[] values)` has parameter `int[].class`:

```java
getMethod("publish", String[].class); // public void publish(String... labels)
getMethod("sum", int[].class);        // public int sum(int[] values)
```

This is a signature illustration, not a standalone program: the two corresponding methods must exist on the `Class` being looked up. `getMethod("publish", String.class)` does not match varargs; Reflection does not expand or group parameter types at the lookup step.

### Generics and Type Erasure

Java usually erases generic type arguments in runtime method signatures. For `void save(List<String> names)`, you must look up with `List.class`; there is **no** `List<String>.class` syntax:

```java
Method save = Example.class.getMethod("save", List.class);
```

`save.getParameterTypes()` returns the erased types; `save.getGenericParameterTypes()` can provide additional generic information stored in metadata. For a type variable like `T`, the type used for lookup is the erased type (usually `Object` or the first bound).

### Classes Loaded by Different ClassLoaders

Two classes with the same fully qualified name defined by two different class loaders can be **two distinct runtime types**. Because parameter type matching relies on `Class` identity, merely comparing names from `getName()` is not enough to guarantee the signature will match.

## 5. Public, Declared, Inheritance, and Access Permissions

`getMethod` and `getField` inspect `public` members, including inherited public members per Java rules. `getDeclaredMethod` and `getDeclaredField` inspect members declared directly in the class of the `Class` object held, regardless of `public`, `protected`, package-private, or `private`; they **do not walk up to the superclass**. If you want to find a `private` member declared in a superclass, you must obtain that superclass's `Class` (or traverse the `getSuperclass()` chain yourself when the problem requires it).

Constructors are not inherited. `getConstructor(int.class)` requires a `public` constructor with exactly one `int` parameter; `getDeclaredConstructor(int.class)` checks constructors declared by the class at any access level. Do not pass the class name when looking up a constructor. A default constructor does not always exist: once a class declares another constructor, Java does not auto-generate a no-arg constructor.

**Being able to look up does not mean being able to invoke or read/write.** For example, finding a `private Method` via `getDeclaredMethod` does not automatically grant permission to call `method.invoke(...)`. Java may throw `IllegalAccessException` upon access; `setAccessible(true)` can also be denied, especially across module boundaries (e.g., `InaccessibleObjectException`). Do not overuse opening access to mask an inappropriate API design.

## 6. Error Handling and Inspecting Actual Signatures

Single-member lookup APIs do not return `null` when not found:

- `getMethod`, `getDeclaredMethod`, `getConstructor`, and `getDeclaredConstructor` throw `NoSuchMethodException`.
- `getField` and `getDeclaredField` throw `NoSuchFieldException`.
- Certain invalid inputs (e.g., `null` name or a `null` parameter type element) may cause `NullPointerException`; validate inputs before dynamic lookup.
- Security or module restrictions can cause other errors when finding or using members; inspect the actual exception type.

If you receive `NoSuchMethodException`, check step by step: is the `Class` object being looked up correct; are the characters/case of the name exact; are count, order, and each type exact; have primitive/wrapper, array/varargs, and erasure been distinguished; and finally was `getMethod` vs `getDeclaredMethod` chosen properly. When diagnosing, you can list signatures from the target class itself:

```java
for (Method method : Example.class.getDeclaredMethods()) {
    System.out.println(method.getName()
            + Arrays.toString(method.getParameterTypes()));
}
```

The snippet above is illustrative code placed inside `main` of the example and uses `java.lang.reflect.Method` along with `java.util.Arrays`. The order returned by `getDeclaredMethods()` is **not guaranteed**, so do not rely on the printed order for logic or tests. Compiler-generated `synthetic` or `bridge` methods may appear in the results; inspect `isSynthetic()` and `isBridge()` to understand them. When working with special bytecode having multiple methods with the same name and parameters but different return types, do not assume the single-method lookup API filters by return type because the API accepts no such criterion.

## 7. Practical Scenarios and Rules to Remember

Suppose a framework reads a method name and parameter types from configuration, such as `run(String, int)`. A reliable workflow is to resolve **each type name** to the right `Class` object (primitives must be handled specially), decide whether to search `public` or directly declared members, call `getMethod("run", String.class, int.class)`, and only afterward check the return type, modifiers, and access permissions, then perform `invoke` if allowed. If obtaining types via `args[i].getClass()`, be careful: an `Integer` value is not equivalent to a declared `int` parameter; a `null` value also has no `getClass()`. Configuration should describe the **declared signature**, not guess signatures from passed-in values.

Remember three core rules: **method = exact name + parameter type sequence; constructor = exact parameter type sequence; field = exact name**. Then choose the right `public`/`declared` scope and separate the **member lookup** step from the **member access or invocation** step.
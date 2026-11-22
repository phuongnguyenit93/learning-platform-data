# 2.6. Checking `isInstance`, `isAssignableFrom`, `cast`, and `asSubclass`

In Java, a value has a **declared type** at compile time, but the object that the variable references has an **actual runtime type**. When the type is only known through configuration, class names, plugins, or reflection APIs, four methods of `java.lang.Class` help perform checks and conversions in a controlled manner:

- `isInstance(Object)`: does this object belong to the type under consideration?
- `isAssignableFrom(Class<?>)`: can a source class/type be assigned to the target type?
- `cast(Object)`: checks and returns the object typed as a `Class<T>`.
- `asSubclass(Class<U>)`: checks and narrows a **`Class` object** to a subtype of `U`.

The key point is **distinguishing an object from a type descriptor** and **reading the check direction correctly**. The examples below use Java 17 or later.

## 1. Foundation: `Object`, `Class<?>`, and type relationships

Consider the code snippet:

```java
Object value = Integer.valueOf(42);
Class<?> actualType = value.getClass(); // java.lang.Integer
Class<?> declaredTarget = Number.class;
```

The variable `value` has the declared type `Object`, but the actual object is `Integer`, which inherits from `Number`. `actualType` is a **class token**: a `Class` object describing the runtime type, not an `Integer` instance.

- For an **object**, ask `Number.class.isInstance(value)`.
- For **two types**, ask `Number.class.isAssignableFrom(Integer.class)`.
- To obtain a `Number` reference from `Object`, use `Number.class.cast(value)`.
- When you have a dynamically loaded `Class<?>` and need to ensure it implements an interface, use `raw.asSubclass(Interface.class)`.

`Class<?>` means "known to be a `Class`, but its exact type is not yet known". `Class<T>` also preserves type relationships at compile time, such as `Class<Number>`, and supports returning `T` from `cast`. All of these checks follow **JVM type identity**, including the class loader; two classes with the same name but loaded by incompatible class loaders are not automatically the same type.

## 2. Quick comparison of the four APIs

| Method | Called on | Argument | Result | Incompatible |
| --- | --- | --- | --- | --- |
| `type.isInstance(value)` | `Class<?>` describing target type | An object | `boolean` | `false` |
| `target.isAssignableFrom(source)` | `Class<?>` target type | `Class<?>` source type | `boolean` | `false` |
| `type.cast(value)` | `Class<T>` desired type | An object | `T` (same object) | `ClassCastException` |
| `raw.asSubclass(parent)` | `Class<?>` found type | `Class<U>` parent/bound type | `Class<? extends U>` | `ClassCastException` |

For `null`: `isInstance(null)` is always `false`; `cast(null)` returns `null`. `isAssignableFrom(null)` and `asSubclass(null)` throw `NullPointerException` because a valid `Class` object is required. Calling any method through a `Class` variable that is currently `null` also causes `NullPointerException`.

## 3. `isInstance` — asking about an object

API signature (abbreviated, not a standalone program):

```java
boolean isInstance(Object obj)
```

For reference classes or interfaces, this is a runtime type check similar to `obj instanceof SomeType`, except **the target type can be held in a `Class<?>` variable**:

```java
Object data = "Java";
Class<?> expected = CharSequence.class; // can be chosen at runtime

System.out.println(expected.isInstance(data));       // true
System.out.println(Number.class.isInstance(data));   // false
System.out.println(String.class.isInstance(null));   // false
System.out.println(int.class.isInstance(42));         // false
```

`CharSequence` is an interface implemented by `String`, so the first result is `true`. In the last line, `42` is **autoboxed** into `Integer` when passed to the `Object` parameter; `int.class` describes the primitive type, not `Integer.class`. Therefore, the result is still `false`. `isInstance` does not perform primitive conversions or unboxing.

Use `isInstance` when you have an **object to check** and the **expected type is decided dynamically**. If the type name is known directly in the source code, `instanceof` (including pattern matching since Java 16) is usually more readable:

```java
if (data instanceof String text) {
    System.out.println(text.length());
}
```

`isInstance` only returns a `boolean`; it does not provide a narrowed-type variable like the pattern variable `text`.

## 4. `isAssignableFrom` — asking about two types and assignment direction

API signature (abbreviated, not a standalone program):

```java
boolean isAssignableFrom(Class<?> cls)
```

Read from left to right as: **"Can the type on the left receive a value of the type on the right?"** You can remember this with an illustrative assignment:

```java
// target.isAssignableFrom(source) checks a relationship similar to:
// Target target = sourceValue;   // sourceValue has type Source
Number.class.isAssignableFrom(Integer.class); // true
Integer.class.isAssignableFrom(Number.class); // false
```

The `source` argument can be `target` itself, a subclass, a class implementing an interface, or an array type assignable according to Java's rules:

| Expression | Result | Why |
| --- | --- | --- |
| `Object.class.isAssignableFrom(String.class)` | `true` | `String` is an `Object` |
| `CharSequence.class.isAssignableFrom(String.class)` | `true` | `String` implements `CharSequence` |
| `String.class.isAssignableFrom(CharSequence.class)` | `false` | Not every `CharSequence` is a `String` |
| `Number.class.isAssignableFrom(Number.class)` | `true` | Identical types |
| `Number.class.isAssignableFrom(int.class)` | `false` | Does not autobox `int` to `Integer` |
| `int.class.isAssignableFrom(int.class)` | `true` | Same primitive type |
| `Number[].class.isAssignableFrom(Integer[].class)` | `true` | Reference arrays are covariant |
| `Object[].class.isAssignableFrom(int[].class)` | `false` | `int[]` is not a reference array `Object[]` |
| `Object.class.isAssignableFrom(int[].class)` | `true` | Every array itself is an object |

**Note on arrays:** The fact that `Number[]` accepts `Integer[]` does not guarantee every element write will succeed. For example, `Number[] xs = new Integer[1]; xs[0] = 3.14;` compiles but throws `ArrayStoreException` at runtime. Primitive arrays such as `int[]` are still objects (`Object`, `Cloneable`, `Serializable`), yet they are not `Object[]`.

`isAssignableFrom` checks reference type relationships and primitive type identity; it **does not** consider primitive widening (`int` to `long`), boxing/unboxing, or explicit cast conversions. The most common mistake is reversing the two sides: `Integer.class.isAssignableFrom(Number.class)` checks the opposite direction and must be `false`.

## 5. `cast` — checking an object and receiving type `T`

API signature (abbreviated, not a standalone program):

```java
T cast(Object obj)
```

`cast` performs a runtime type check and returns **the same object passed in**, typed as `T` associated with the class token. It does not create a new object, does not convert numbers, and does not automatically parse strings:

```java
Object raw = Integer.valueOf(42);
Number number = Number.class.cast(raw); // OK, the return type is Number
System.out.println(number.intValue()); // 42

String nothing = String.class.cast(null); // valid: nothing == null
// String text = String.class.cast(raw); // ClassCastException at runtime
```

A convenient pattern for APIs reading dynamic data:

```java
static <T> T checkedValue(Class<T> expected, Object value) {
    return expected.cast(value);
}

// How to call:
// Integer count = checkedValue(Integer.class, someObject);
```

There is no need for an unchecked cast `(T) value`. The compiler infers `T` from `Class<T>`, while the JVM checks the object in `cast`. The `obj == null` case is allowed: if the application requires a non-`null` value, additionally check `Objects.requireNonNull(obj)`.

`Class.cast` is primarily intended for reference types: `int.class.cast(Integer.valueOf(1))` throws `ClassCastException`, because primitive classes have no matching object instances. `Integer.class.cast(Integer.valueOf(1))` is what is valid. A `ClassCastException` thrown from `cast` is a clear signal that the input data does not satisfy the expected type contract.

## 6. `asSubclass` — narrowing the class token of a dynamically loaded class

API signature (abbreviated, not a standalone program):

```java
<U> Class<? extends U> asSubclass(Class<U> clazz)
```

This is a check for a **`Class` object**, not for an instance. If the type represented by `raw` is `U` itself or a subclass/implementing type of `U`, the result is a class token of type `Class<? extends U>`. Otherwise, it throws `ClassCastException`:

```java
Class<?> raw = StringBuilder.class;

Class<? extends CharSequence> valid =
        raw.asSubclass(CharSequence.class);    // OK

// raw.asSubclass(Number.class);               // ClassCastException
```

The compatibility condition can be thought of as roughly `Parent.class.isAssignableFrom(raw)`, except `asSubclass` **both verifies and returns a generically bounded class token**, so you can continue calling APIs such as `getDeclaredConstructor()` and create an instance with a clear parent type. It does not create an instance itself, does not prove a constructor exists or is accessible, and does not guarantee the class is not abstract.

A typical application is loading plugins/handlers from a class name: `Class.forName(name)` initially only gives `Class<?>`, after which `raw.asSubclass(Handler.class)` helps reject classes that do not implement `Handler` right at the loading boundary. When you need to check without throwing an error, use `Handler.class.isAssignableFrom(raw)`.

## 7. Complete example running on Java 17+

Save with the exact file name `RuntimeTypeChecks.java`:

```java
import java.util.Objects;

public class RuntimeTypeChecks {
    interface Handler {
        String handle();
    }

    public static final class HelloHandler implements Handler {
        public HelloHandler() {}

        @Override
        public String handle() {
            return "hello";
        }
    }

    static <T> T requireType(Class<T> expected, Object value) {
        Objects.requireNonNull(expected, "expected");
        return expected.cast(value);
    }

    static Handler loadHandler(String binaryName)
            throws ReflectiveOperationException {
        Class<?> raw = Class.forName(binaryName);
        Class<? extends Handler> type = raw.asSubclass(Handler.class);
        return type.getDeclaredConstructor().newInstance();
    }

    public static void main(String[] args)
            throws ReflectiveOperationException {
        Object value = Integer.valueOf(42);

        System.out.println(Number.class.isInstance(value));
        System.out.println(String.class.isInstance(value));
        System.out.println(Number.class.isInstance(null));

        System.out.println(Number.class.isAssignableFrom(Integer.class));
        System.out.println(Integer.class.isAssignableFrom(Number.class));
        System.out.println(int.class.isAssignableFrom(Integer.class));

        Number number = requireType(Number.class, value);
        System.out.println(number.intValue());
        System.out.println(String.class.cast(null) == null);

        try {
            String.class.cast(value);
        } catch (ClassCastException expected) {
            System.out.println("cast: ClassCastException");
        }

        Handler handler = loadHandler(HelloHandler.class.getName());
        System.out.println(handler.handle());

        try {
            String.class.asSubclass(Handler.class);
        } catch (ClassCastException expected) {
            System.out.println("asSubclass: ClassCastException");
        }

        System.out.println(Number[].class.isAssignableFrom(Integer[].class));
        System.out.println(Object.class.isAssignableFrom(int[].class));
        System.out.println(Object[].class.isAssignableFrom(int[].class));
    }
}
```

Compile/run in the directory containing the file:

```bash
javac --release 17 RuntimeTypeChecks.java
java RuntimeTypeChecks
```

Exact `stdout` output (excluding command lines):

```text
true
false
false
true
false
false
42
true
cast: ClassCastException
hello
asSubclass: ClassCastException
true
true
false
```

**Execution flow explanation:**

1. The first three lines use **instances**: `Integer` is a `Number`, not a `String`; `null` is not an instance of any class.
2. The next three lines use **class tokens** in the target ← source direction: `Number` accepts `Integer`; the reverse direction and primitive versus wrapper are both invalid.
3. `requireType` returns a `Number` holding the value `42`; `cast(null)` returns `null`. Attempting to cast `Integer` to `String` causes a `ClassCastException`, which is intentionally caught.
4. `Class.forName` finds the nested class `HelloHandler` by the binary name provided by `getName()`; `asSubclass(Handler.class)` verifies the contract, and the constructor creates a new object, so `handle()` prints `hello`.
5. `String` does not implement `Handler`, so `asSubclass` throws `ClassCastException`. The last three lines confirm the rules for reference arrays, `Object`, and primitive arrays.

The example uses a public constructor to illustrate the minimal path. In a real plugin system, instantiation can fail if the class is abstract, the constructor does not exist/is not accessible, the constructor throws an error, or the class loader cannot see dependencies.

## 8. Workflow when checking dynamic data

**Case A — Having an object from an API, needing to check and then use it:** With `Object payload` and a `Class<T> expected` determined by configuration, use `expected.isInstance(payload)` if you want to branch lightly; use `expected.cast(payload)` if the contract requires that type and you want to receive `T` directly. Before using `cast`, you can handle `null` separately according to business rules. There is no need to call `getClass()` just to call `isInstance`.

**Case B — Examining two class tokens:** With `Class<?> source` and `Class<?> target`, write `target.isAssignableFrom(source)`. For example, a handler registry wants to filter classes implementing `Handler` with `Handler.class.isAssignableFrom(candidate)`. If you need to represent the result as a type usable in generic APIs, switch to `candidate.asSubclass(Handler.class)`.

**Case C — Loading a class by configured name:** Choose the appropriate class loader, load the binary name, check `asSubclass`, and only then check instantiation/constructor capability. For class names from external sources, only accept an allowlisted set of classes, and pay attention to class initialization side effects, module access permissions, and reflection errors. `Class.forName(name)` can trigger class initialization; if you need to defer it, consider the `Class.forName(name, false, loader)` form.

**Case D — Parameterized generic types:** `List.class.isInstance(List.of(123))` is `true`, but that **does not prove** the list is `List<String>`. Due to *type erasure*, the four APIs do not check the `String` type argument in `List<String>`. When you need to validate contents, iterate and check each element (or use a schema/type token checking mechanism with appropriate generic information); do not treat `List.class.cast(...)` as a guarantee of generic safety.

## 9. Common errors and how to diagnose them

| Error | Symptom | How to fix |
| --- | --- | --- |
| Reversing `isAssignableFrom` | `Integer.class.isAssignableFrom(Number.class)` unexpectedly returns `false` | Put the **target type on the left**, source on the right |
| Confusing `isInstance` with `isAssignableFrom` | Passing an object to an API expecting `Class` or vice versa | Determine whether you are checking a **value** or a **type descriptor** |
| Expecting primitive autoboxing | `int.class.isInstance(1)` or `int.class.cast(1)` does not behave like `Integer.class` | Use the wrapper `Integer.class` for objects |
| Using `cast` to transform data | Expecting `String.class.cast(42)` to become `"42"` | Use an intentional conversion such as `String.valueOf(42)` |
| Believing `asSubclass` guarantees object creation | Class is valid but constructor fails or does not exist | Check abstract/constructor/access and handle exceptions |
| Believing checking `List.class` validates `List<String>` | Elements of another type only cause errors when used | Validate each element and limit unchecked casts |
| Mistaking classes with the same name for the same type | `isAssignableFrom` fails between two class loaders | Check the class loader and actual class identity |
| Checking `isInstance` and then casting a changed object | The check result no longer matches the object used later | Keep the same reference and use `expected.cast(value)` at the usage boundary |

Avoid using exceptions as normal control flow when you only want to know `true/false`: choose `isInstance` or `isAssignableFrom`. Conversely, `cast` and `asSubclass` are the right choices when a type contract violation must be reported immediately.

## 10. Self-check

Predict before running:

```java
System.out.println(CharSequence.class.isAssignableFrom(String.class));
System.out.println(String.class.isInstance(null));
System.out.println(Object[].class.isInstance(new int[] {1, 2}));
System.out.println(Cloneable.class.isAssignableFrom(int[].class));
```

The answers in order are `true`, `false`, `false`, `true`. Explanation: `String` implements `CharSequence`; `null` is not an instance; `int[]` is not `Object[]`, but every Java array implements `Cloneable`.

**Remember:** `isInstance` and `cast` take an **object**; `isAssignableFrom` and `asSubclass` work with **class tokens**. When checking two types, `Target.class.isAssignableFrom(Source.class)` reads as "target can receive source"; when you need a type-bounded class token, use `raw.asSubclass(Target.class)`.

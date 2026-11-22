# The `?` Sign Represents an Unknown Type in Java Generics

## 1. What does `?` say about the data type?

In Java Generics, `?` is a **wildcard** (a placeholder symbol for a type argument). When written without a bound like `List<?>`, it is called an **unbounded wildcard**. The `?` means: *there is some concrete element type, but at this point of use we do not know what that type is*.

```java
List<String> strings = new ArrayList<>();
List<Integer> integers = new ArrayList<>();

List<?> first = strings;   // The actual element type of the list is String
List<?> second = integers; // The actual element type of the list is Integer
```

Both `first` and `second` have the declared type `List<?>`, but they reference lists with different type parameters. For `first`, the hidden type behind the question mark is `String`; for `second`, the hidden type is `Integer`. The compiler **does not allow code using a `List<?>` variable to arbitrarily assume** it is `String` or `Integer`.

More precisely, `List<?>` describes “a `List<T>` with some unknown `T`”, not “a list that can freely change between all element types”. Java enforces this safety in type checking at *compile time*.

Note: `?` is not the name of a class, an independent data type, a `null` value, or “any value” in the sense that anything can be written into it. It is syntax indicating **an unspecified type argument**.

## 2. Why do we need to represent an unknown type?

Suppose we need a method that only prints elements, regardless of whether the list contains strings, numbers, or other objects. The method does not need to add elements, nor does it need to preserve a concrete type when returning a result.

```java
static void printAll(List<?> items) {
    for (Object item : items) {
        System.out.println(item);
    }
}
```

This method can accept `List<String>`, `List<Integer>`, `List<Customer>`, or `List<Object>`. Declaring `List<?>` accurately expresses the intent that the algorithm **does not depend on the type parameter `E`** of `List<E>`.

If we declare the parameter as `List<Object>`, we cannot pass `List<String>` directly: generics in Java are **invariant**. If we declare a raw `List`, we lose type-argument safety checks and easily introduce `unchecked` operations. A wildcard both allows accepting lists with many different type parameters and maintains the necessary operation restrictions.

## 3. Understanding `?` through assignment

The following example illustrates valid assignments:

```java
List<String> names = new ArrayList<>(List.of("Lan", "Minh"));
List<Integer> ages = new ArrayList<>(List.of(20, 25));
List<Object> mixed = new ArrayList<>(List.of("Java", 21));

List<?> unknownNames = names; // Valid
List<?> unknownAges = ages;   // Valid
List<?> unknownMixed = mixed; // Valid
```

Those assignments do not create copies of the lists. `unknownNames` and `names` point to **the same object**. The wildcard only changes the type information that code is allowed to rely on through the new variable.

The following two assignments **do not compile**:

```java
List<String> names = new ArrayList<>();
List<?> anyNames = names;

// List<Object> objects = names;     // Error: List<String> is not List<Object>
// List<String> recovered = anyNames; // Error: ? is not guaranteed to be String
```

The compiler accepts `List<String>` as `List<?>` because it does not need to know `String` specifically to perform general operations. However, the reverse direction requires proof that the hidden type is `String`; knowing only `?` is not enough.

Do not equate “**accepting** a list of any element type” with “**allowing adding** any kind of element to the list”.

## 4. Reading data through `List<?>`: what do we know?

`List<E>.get(int)` normally returns `E`. When a variable has type `List<?>`, the compiler keeps `E` as a hidden type, but every element of a reference type can be viewed as type `Object`. Therefore:

```java
List<String> names = List.of("Lan", "Minh");
List<?> items = names;

Object first = items.get(0);     // Valid
int count = items.size();        // Valid
boolean found = items.contains("Lan"); // Valid: contains accepts Object

// String text = items.get(0);  // Error: compiler does not know ? is String
```

Each element can be processed using a type check when genuinely needed:

```java
for (Object element : items) {
    if (element instanceof String text) {
        System.out.println(text.toUpperCase());
    }
}
```

The expression `element instanceof String` checks the object **at runtime**. It does not turn the entire `List<?>` into `List<String>`: the list may contain other element types in other contexts.

Operations that do not depend on the type parameter, such as `size()`, `isEmpty()`, `iterator()`, `contains(Object)`, and `toString()`, remain usable. With `iterator()`, each element can be received via an `Object` variable or handled using the hidden type parameter inside a helper generic method.

## 5. Why can't an arbitrary element be added?

Imagine the compiler allowed the following code:

```java
List<String> names = new ArrayList<>(List.of("Lan"));
List<?> items = names;

// items.add(123); // Forbidden at compile time
```

If `items.add(123)` were allowed, `names` itself would contain an `Integer` despite promising to be a `List<String>`. Subsequent reads expecting `String` could encounter a `ClassCastException`. **Refusing to add values of a concrete type** protects the promise of the original list.

In principle, with `List<?>`:

- `items.add("text")`: does not compile because `?` could be `Integer`.
- `items.add(123)`: does not compile because `?` could be `String`.
- `items.set(0, "text")`: does not compile because the required type to assign is unknown.
- `items.add(null)`: **compiles**, because `null` is assignable to any reference type.

Example with a mutable list:

```java
List<String> names = new ArrayList<>(List.of("Lan"));
List<?> unknown = names;
unknown.add(null);              // Allowed at the type-checking level
System.out.println(names);     // [Lan, null]
```

The fact that `add(null)` compiles **does not guarantee every list allows adding null**: `List.of(...)` creates an unmodifiable list; some implementations also have their own rules regarding null. In those cases, the mutating call may throw an exception. Type-checking rules and an implementation's mutability are two separate issues.

## 6. Unbounded wildcard does not make a list immutable

`List<?>` forbids adding a non-null value of an arbitrary type, but **does not forbid all modifications**. Methods that do not require supplying an element of the hidden type, such as `clear()`, `remove(Object)`, and `remove(int)`, remain valid at compile time:

```java
List<String> names = new ArrayList<>(List.of("Lan", "Minh"));
List<?> view = names;
view.remove("Lan");
System.out.println(names); // [Minh]
```

Both variables point to the same `ArrayList`; the wildcard does not automatically create a copy. **Type-valid does not mean runnable:** `List.of(...)` does not support modification and can throw `UnsupportedOperationException`. If the caller truly must not be allowed to modify the data, an appropriate unmodifiable view/snapshot must be provided instead of relying solely on a wildcard.

## 7. Complete Java 17 illustration

Create the file `UnknownWildcardDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;

public class UnknownWildcardDemo {
    static void printAll(List<?> values) {
        for (Object value : values) {
            System.out.println("Value: " + value);
        }
    }

    static void swapFirstTwo(List<?> values) {
        swapCaptured(values);
    }

    private static <T> void swapCaptured(List<T> values) {
        if (values.size() < 2) {
            return;
        }
        T first = values.get(0);
        values.set(0, values.get(1));
        values.set(1, first);
    }

    public static void main(String[] args) {
        List<String> names = new ArrayList<>(List.of("Lan", "Minh"));
        List<Integer> numbers = new ArrayList<>(List.of(3, 5));

        printAll(names);
        printAll(numbers);

        List<?> unknown = names;
        Object first = unknown.get(0);
        System.out.println("First: " + first);

        swapFirstTwo(unknown);
        System.out.println("After swap: " + names);

        unknown.add(null);
        System.out.println("After null: " + names);

        Object payload = numbers;
        if (payload instanceof List<?> found) {
            System.out.println("Size: " + found.size());
        }
    }
}
```

Compile and run from the directory containing the file:

```bash
javac UnknownWildcardDemo.java
java UnknownWildcardDemo
```

**Exact stdout:**

```text
Value: Lan
Value: Minh
Value: 3
Value: 5
First: Lan
After swap: [Minh, Lan]
After null: [Minh, Lan, null]
Size: 2
```

Mechanism explanation:

1. `printAll` only reads elements through type `Object`, so it can accept a list containing `String` or `Integer`.
2. `unknown` points to the same object as `names`: the results of swapping and adding null through `unknown` are both visible when printing `names`.
3. `swapFirstTwo` preserves the `List<?>` declaration for the caller, then uses `swapCaptured` so the compiler assigns a consistent type name `T` to the hidden type argument; this approach **does not introduce foreign element types into the list**.
4. `instanceof List<?>` is valid because this is a runtime-checkable form verifying that `payload` is a `List`; that condition **does not determine** the concrete element type.

The example uses `ArrayList` because the list supports `set` and `add(null)`. If `names` is replaced with `List.of("Lan", "Minh")`, the code still satisfies many static type conditions, but `set` or `add` may throw `UnsupportedOperationException`.

## 8. Wildcard capture: when you need to work with the hidden type

Within a generic expression, the compiler can temporarily assign an internal symbol such as `CAP#1` to represent the type hidden by `?`. This is *wildcard capture*. Some operations that retrieve an element and put it back into the list can be difficult to type-check if code works directly with `List<?>`:

```java
static void putFirstBack(List<?> items) {
    // items.set(0, items.get(0)); // May report a capture type error
}
```

Use a helper with an explicit type parameter:

```java
static void putFirstBack(List<?> items) {
    putFirstBackCaptured(items);
}

private static <T> void putFirstBackCaptured(List<T> items) {
    if (!items.isEmpty()) {
        T first = items.get(0);
        items.set(0, first);
    }
}
```

Because `items.get(0)` and `items.set(0, first)` both use the same `T`, the compiler can prove that the retrieved value is compatible with the target write position. Note: the helper can mutate data, but only places back an element of **the same type `T`**; the helper does not grant permission to add an arbitrary value such as `Integer` into a `List<String>`. Both snippets above are **method illustration snippets**, not two methods placed in the same class; to run it, choose the version with the helper.

### Two question marks do not implicitly refer to the same type

```java
static void inspectPair(List<?> left, List<?> right) {
    Object first = left.get(0);
    Object second = right.get(0);
    System.out.println(first + " / " + second);

    // right.set(0, left.get(0)); // Unsafe: the two ? may have different types
}
```

`left` could be `List<String>`, while `right` could be `List<Integer>`. Even though both have type `List<?>`, we have **no proof** that the two hidden type parameters are the same.

If you need to constrain two lists to have the same element type, use a named type parameter:

```java
static <T> void copyFirst(List<? extends T> source, List<? super T> target) {
    if (!source.isEmpty() && !target.isEmpty()) {
        target.set(0, source.get(0));
    }
}
```

For example, `List<String>` as source and `List<Object>` as target will be valid. The `extends/super` bounds here go beyond unbounded wildcards, but illustrate why a shared symbol `T` allows the compiler to control relationships across multiple positions.

## 9. Where does `?` appear, and what is it not?

The question mark appears in the **type argument** position of a generic type when the specific argument does not need to be known:

```java
List<?> unknownElements;
Set<?> unknownMembers;
Map<?, ?> unknownKeysAndValues;
Class<?> unknownClass;
```

For example, `Map<?, ?>` does not know the key type and value type; one can read through `Object` and call general lookup methods, but cannot arbitrarily `put` non-null key/value pairs because the hidden types are unspecified. `Class<?>` represents a `Class` object for some unknown type, useful for reflection APIs that only need to work with a `Class` object.

Conversely, the following ways of writing are **not valid Java declarations**:

```java
// class Box<?> { }             // Cannot use ? to declare a type parameter
// List<?> list = new ArrayList<?>(); // Cannot use a wildcard when creating an object
// <?> void process() { }        // Cannot use ? to declare a method type parameter
```

When defining a generic class or method, you need a **named type parameter** such as `T` or `E`. When creating an object, use an actual type or the diamond `<>` for the compiler to infer:

```java
List<?> view = new ArrayList<String>(); // Valid
List<?> inferred = new ArrayList<>();    // Valid; compiler infers the type argument
```

Another point is that generics in Java use *type erasure*: runtime does not retain `String` or `Integer` as an element check inside an `ArrayList` object. Therefore:

```java
Object input = List.of("x");
boolean isList = input instanceof List<?>; // Valid: checks whether it is a List
// boolean isStrings = input instanceof List<String>; // Invalid
```

`instanceof List<?>` does not prove that the elements all have any concrete type. It only confirms that the object has type `List` at runtime; the type parameter remains unknown.

## 10. When should you write `List<?>`, and when should you use `<T>`?

Use `List<?>` when what you truly want to say is **“the element type is irrelevant to what I am doing”**:

```java
static boolean hasAnyElement(List<?> values) {
    return !values.isEmpty();
}

static void describe(List<?> values) {
    System.out.println("Count = " + values.size());
}
```

Use a named type parameter `<T>` when you need to **propagate type information** between parameters and the return value, or between multiple parameters:

```java
static <T> T firstOrNull(List<T> values) {
    return values.isEmpty() ? null : values.get(0);
}
```

With `List<String>`, calling `firstOrNull` returns static type `String`; with `List<Integer>`, the result has static type `Integer`. If we change the parameter to `List<?>` and the return type to `Object`, the API loses that useful type relationship.

In general, if the caller needs to pass any list so the API can only read/count/print, `List<?>` is a concise and safe contract. If the algorithm needs to receive and return **the same element type**, `<T>` expresses the relationship more clearly. If it needs to **add values belonging to a defined family of types**, a bounded wildcard like `? super T` may be more suitable; that is a different requirement from “not knowing what type it is”.

## 11. Common misconceptions

| Misconception | What is true |
|---|---|
| “`?` means `Object`.” | `?` is an unknown type parameter; `Object` is a specific type. |
| “`List<?>` can hold anything.” | It can **reference** many kinds of `List<T>`, but you cannot arbitrarily add to a referenced list. |
| “Because you cannot add to it, `List<?>` is immutable.” | You can still call `clear`, `remove`, and `add(null)` when the implementation supports them. |
| “Two `List<?>` variables certainly have the same element type.” | Each question mark may represent a different hidden type. |
| “`instanceof List<?>` proves the element type.” | It only checks that the object is a `List` at runtime. |
| “To read `String`, cast `List<?>` to `List<String>`.” | Casting does not automatically check each element; use type evidence in the API or check each object when needed. |
| “Using raw `List` is just as safe as a wildcard.” | Raw types bypass type-argument checking and risk causing heap pollution. |

## 12. Self-check and answers

Given the code snippet:

```java
List<Integer> numbers = new ArrayList<>(List.of(10, 20));
List<?> unknown = numbers;
```

Answer these yourself before looking at the solutions:

1. Can `unknown.get(0)` be assigned directly to an `Integer` variable, or can it only be safely assigned to `Object`?
2. Does `unknown.add(30)` compile, even though the real list is `List<Integer>`?
3. Does `unknown.add(null)` compile, and here does it modify `numbers`?
4. Does `unknown.remove(0)` compile? In `List`, which overload is chosen when passing the integer `0`?
5. Can we replace the parameter of `printAll(List<?>)` with `List<Object>` and still pass `List<Integer>` into it?

**Answers:** (1) Only safely assignable to `Object` because the compiler only knows `?`; (2) No, because the static type does not allow writing `Integer` into the hidden type; (3) Yes, and `ArrayList` accepts null so `numbers` receives an additional null element; (4) Yes, `remove(int index)` is chosen and removes the element at index 0 if present, not the `Integer.valueOf(0)` object; (5) No, because `List<Integer>` is not `List<Object>`.

## 13. Remembering the essence of unbounded wildcard

**`?` means “an unknown type”, not “an arbitrary type allowed to be written to”.** `List<?>` lets code work with a list without needing to know its type argument, as long as the operations do not require arbitrarily supplying elements of the hidden type. Reading elements as `Object` is safe; adding a random `String` or `Integer` value is not. When you need to link the same hidden type across multiple operations, use wildcard capture via a helper with parameter `<T>`.
# Distinguishing `List<Object>`, `List<?>`, and Raw `List`

In Java Generics, all three declarations relate to `java.util.List`, yet they express **three different type contracts**. The key is distinguishing: (1) a list declared to hold elements of type `Object`; (2) a list whose element type is **unknown**; and (3) a list that has **bypassed type argument checking**. Looking similar in syntax does not mean they provide the same level of safety.

## 1. What Do the Three Declarations Mean?

```java
List<Object> objects; // A list whose element type is explicitly Object
List<?> unknown;       // A list with some element type, unknown which one
List raw;              // Raw type: omits the type parameter of List<E>
```

- **`List<Object>`**: `E` is `Object`. You can insert `String`, `Integer`, or another object because all of them are objects assignable to `Object`. When reading, the returned static type is `Object`.
- **`List<?>`**: there is an actual type parameter, but the code using the list **does not know** whether that parameter is `String`, `Integer`, or some other type. The `?` symbol is an *unbounded wildcard*. When reading an element, the safest result is `Object`; when adding an ordinary element, the compiler must reject it because it does not know whether the element matches the type.
- **Raw `List`**: the form without `<...>`, existing mainly for compatibility with pre-Generics code. The compiler allows many calls operating with `Object` without protecting type arguments; unsafe operations typically produce an `unchecked` warning. This is **not** an equivalent representation of `List<?>`.

`Object` in `List<Object>` is **a concrete type**, whereas `?` in `List<?>` is **an unknown type**. This difference determines which assignments and operations are allowed.

## 2. Why Is `List<String>` Not a `List<Object>`?

Suppose there is a list intended only for strings:

```java
List<String> names = new ArrayList<>();
names.add("An");
```

Even though `String` is a subtype of `Object`, Java Generics are **invariant**: from `String extends Object` one cannot infer `List<String> extends List<Object>`. The following snippet intentionally does not compile:

```java
List<String> names = new ArrayList<>();
List<Object> objects = names; // COMPILE ERROR: incompatible types
objects.add(123);             // If allowed, a String list would hold an Integer!
```

If that assignment were valid, a user of `objects` could add an `Integer` and violate the guarantee relied upon by users of `names`. Invariance prevents this at compile time.

There are two valid options with different meanings:

```java
List<String> names = new ArrayList<>(List.of("An", "Binh"));

List<?> view = names;                       // Same List object, merely viewed through a wildcard
List<Object> copy = new ArrayList<>(names); // Creates a NEW List<Object> containing copied elements
copy.add(123);                              // Valid, does not modify names
```

The constructor `ArrayList(Collection<? extends E>)` allows copying `String` elements into a new `ArrayList<Object>`. Unlike `view`, `copy` is **not an alias** of the original list; both can still hold references to the same element objects if the elements are mutable objects.

## 3. Comparing Assignment, Reading, and Writing

| Question | `List<Object>` | `List<?>` | Raw `List` |
|---|---|---|---|
| Directly assign a `List<String>` variable? | **No**; Generics are invariant | **Yes** | **Yes**, but loses type argument information |
| Static type when calling `get(0)`? | `Object` | `Object` | `Object` |
| `add("text")` or `add(123)`? | **Yes** | **No** | **Yes**, unsafe raw operation may trigger an `unchecked` warning |
| `add(null)`? | Yes | Yes | Yes |
| `set(0, "text")`? | Yes | No | Yes, may trigger a warning |
| Prevents writing wrong element type to the referenced list? | Yes, per the list's `Object` type | Yes, for element values of unknown type | **No** |
| Appropriate purpose | Need to store multiple kinds of objects in one list | Only need to process any list regardless of element type | Interacting with legacy code/APIs that do not declare Generics |

**Important note:** the `add` / `set` restriction of `List<?>` **does not mean the list is completely immutable**. Operations that do not require supplying a value of type `E`, such as `clear()`, `remove(Object)`, or `remove(int)`, can still modify the list. `add(null)` is allowed at the type-checking level because `null` is assignable to every reference type; however, an unmodifiable list created by `List.of(...)` or `Collections.unmodifiableList(...)` can still throw `UnsupportedOperationException` when a mutating method is called. Distinguish **compile-time type validity** from **the actual mutability of the object**.

## 4. Runnable Java 17 Example: How Raw Types Break the Contract

Create the file `ListTypeRelationsDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;

public class ListTypeRelationsDemo {
    public static void main(String[] args) {
        List<Object> objects = new ArrayList<>();
        objects.add("Java");
        objects.add(17);
        System.out.println("Objects: " + objects);

        List<String> words = new ArrayList<>(List.of("alpha", "beta"));

        List<?> unknown = words;
        Object first = unknown.get(0);
        System.out.println("Unknown first: " + first);
        unknown.add(null);
        System.out.println("Unknown after null: " + words);

        List raw = words;
        raw.set(1, 99);
        System.out.println("Raw second: " + raw.get(1));

        try {
            String second = words.get(1);
            System.out.println("Typed second: " + second);
        } catch (ClassCastException ex) {
            System.out.println("Typed second: ClassCastException");
        }
    }
}
```

Compile and run:

```bash
javac -Xlint:rawtypes,unchecked ListTypeRelationsDemo.java
java ListTypeRelationsDemo
```

**Stdout** (excluding compiler warnings on stderr):

```text
Objects: [Java, 17]
Unknown first: alpha
Unknown after null: [alpha, beta, null]
Raw second: 99
Typed second: ClassCastException
```

Step-by-step explanation:

1. `objects` is `List<Object>`: both `String` and `Integer` fit `Object`; there is no type contract violation.
2. `unknown` is `List<?>` pointing to `words`. Elements can be read as `Object`, yet you **cannot** write `unknown.add(99)` or `unknown.add("gamma")` because the real element type is unknown. `unknown.add(null)` compiles, and here `ArrayList` allows adding it.
3. `raw` also points to **`words` itself**. `raw.set(1, 99)` bypasses the `String` parameter check, causing the list to actually hold an `Integer` in the second position. When `words.get(1)` is assigned to `String`, the compiler has inserted the appropriate cast; at runtime, converting `Integer` to `String` fails and throws `ClassCastException`.
4. With `-Xlint:rawtypes,unchecked`, `javac` warns where a raw type and an unchecked call are used. Line numbers and warning text depend on the version and code position; warnings **do not prevent the program from running** unless warnings are configured as errors.

The danger of raw types is that the failure can surface **late** at a read site completely separate from the invalid write. The condition where data inside a generic structure no longer satisfies its promised type parameter is called *heap pollution*. Raw types are a common source of this issue.

## 5. What Does `List<?>` Protect and Where Are Its Limits?

When writing `List<?> values = someList;`, we accept that `values` may be referencing a `List<String>`, `List<Integer>`, or any `List<E>`. Therefore:

```java
List<Integer> numbers = new ArrayList<>(List.of(10, 20));
List<?> values = numbers;

Object value = values.get(0); // Valid: readable as Object
int count = values.size();     // Valid: does not depend on E
boolean hasTen = values.contains(10); // Valid: contains accepts Object

// values.add(30);        // Does not compile
// values.set(0, 30);     // Does not compile
values.add(null);        // Type-valid, though it mutates numbers
```

Why is `values.add(30)` rejected even though this example knows `numbers` is a `List<Integer>`? Because the compiler evaluates the **static type `List<?>` of the variable `values`**. The method accepts an element of the hidden type inside `?`, whereas `30` is only known to be `Integer`, not proven to fit every possible hidden type.

You cannot "replace the question mark with Object" just to add values:

```java
List<?> wildcard = new ArrayList<String>();
// List<Object> wrong = wildcard; // COMPILE ERROR
```

The fact that `wildcard.get(0)` has type `Object` only means every readable element is an object; it does **not** make the element type accepted by the list become `Object`.

### Wildcard Capture: Safe Mutation While Preserving the Element Type

There are cases where existing elements need to be swapped without inserting an external value. We can use a helper generic method so the compiler "captures" the hidden type of `?` as `T`.

File `WildcardCaptureDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;

public class WildcardCaptureDemo {
    public static void main(String[] args) {
        List<String> labels = new ArrayList<>(List.of("first", "second"));
        swapFirstTwo(labels);
        System.out.println(labels);
    }

    static void swapFirstTwo(List<?> input) {
        swapCaptured(input);
    }

    private static <T> void swapCaptured(List<T> items) {
        if (items.size() < 2) {
            return;
        }
        T first = items.get(0);
        items.set(0, items.get(1));
        items.set(1, first);
    }
}
```

Run `javac WildcardCaptureDemo.java` then `java WildcardCaptureDemo`; stdout:

```text
[second, first]
```

In `swapCaptured`, both the read value and the write slot have the same type `T`, so it is valid. No raw types or casts are needed. This pattern guarantees only **type safety**; `set` can still throw `UnsupportedOperationException` if the passed-in list does not permit modification.

## 6. Choosing Parameter Types for Methods/APIs

### Only Need to Inspect or Handle Generally: Use `List<?>`

```java
static void printElements(List<?> elements) {
    for (Object element : elements) {
        System.out.println(element);
    }
}
```

`printElements` accepts `List<String>`, `List<Integer>`, `List<Object>`, etc., because it does not need to know or supply elements of type `E`. This is the right design when the API has no need to relate or write a specific element type.

### Genuinely Need to Put All Kinds of Objects into the Same List: Use `List<Object>`

```java
static void recordEvent(List<Object> events, Object event) {
    events.add(event);
}
```

This API makes sense when the caller **deliberately owns** a list with element type `Object`, allowing mixed data. A `List<String>` cannot be passed in because the method has the right to add any `Object`. If the data must share a uniform type, use a dedicated type parameter like `<T>` instead of defaulting to `Object`.

### Need to Maintain a Relationship Between Input and Output: Use a Type Parameter

```java
static <T> T firstOrNull(List<T> items) {
    return items.isEmpty() ? null : items.get(0);
}
```

When called with `List<String>`, the result has type `String`; with `List<Integer>`, the result has type `Integer`. For an operation that only needs to print elements, `List<?>` is easier to read; for an operation that must **preserve the type relationship `T`**, a generic method is the clearer solution.

### When Bounded Flexible Read/Write Is Required

`List<? extends Number>` accepts lists whose element type is `Number` or a subtype, suitable for **reading values as `Number`**; an arbitrary `Integer` cannot be added to a list of an unknown subtype. `List<? super Integer>` accepts `List<Integer>`, `List<Number>`, or `List<Object>` and **adds `Integer`**; values read back are guaranteed only as `Object`. These are bounded wildcards, extending the problem space without changing the fundamental distinction among the three declarations under consideration. The PECS (*Producer Extends, Consumer Super*) mnemonic helps choose wildcards when specific type relationships are required.

## 7. Raw `List`: When It Exists and How to Cross the Boundary Safely

Raw types are commonly encountered when working with legacy APIs written before Java 5 or untyped libraries. The following example **intentionally illustrates an unsafe operation** and should not be used as a pattern for new APIs:

```java
List raw = new ArrayList();
raw.add("ok");
raw.add(42);

List<String> assumedStrings = raw; // Unchecked conversion: compiler cannot verify
// String second = assumedStrings.get(1); // Can throw ClassCastException
```

This situation has **two** risk points: calling `add` on a raw `List` skips type argument checking, and converting a raw `List` to `List<String>` creates a type promise that the compiler cannot verify. Casting to `List<String>` also **does not** validate each element due to *type erasure* (generic arguments are not retained as a whole-contents check at runtime).

A proper way to handle an untrusted list is to **view the data through `List<?>`, validate each element, and copy into a typed list**:

```java
import java.util.ArrayList;
import java.util.List;

public class LegacyListValidationDemo {
    static List<String> validatedStrings(List<?> input) {
        List<String> result = new ArrayList<>();
        for (Object value : input) {
            if (!(value instanceof String text)) {
                throw new IllegalArgumentException("Expected String element");
            }
            result.add(text);
        }
        return result;
    }

    public static void main(String[] args) {
        List<?> legacyData = List.of("one", "two");
        List<String> safe = validatedStrings(legacyData);
        System.out.println(safe);
    }
}
```

Compile with `javac LegacyListValidationDemo.java` and run `java LegacyListValidationDemo`; stdout:

```text
[one, two]
```

The method above deliberately **rejects `null`** because `null instanceof String` is `false`. If business requirements allow null elements, handle that rule explicitly. `result` is a new list validated element by element; if someone later mutates `input`, no mistyped element enters `result` through a list alias.

When forced to handle a raw type at a compatibility boundary, isolate the raw/unchecked usage to as small a region as possible, inspect the data before promoting it to a typed structure, and only use `@SuppressWarnings("unchecked")` if there is a concrete reason proving the operation is safe. That annotation **only suppresses warnings** and adds no runtime check.

## 8. Common Misconceptions

1. **"`String` extends `Object`, so `List<String>` extends `List<Object>`."** False: element inheritance does not automatically carry over to `List<E>`; Generics are invariant.
2. **"`List<?>` is the same as `List<Object>`."** False: `?` is an unknown type parameter, not another name for `Object`. Both can be read as `Object`, yet they differ in write permissions and assignment rules.
3. **"Wildcards prevent modifying the list."** False: `add(null)`, `clear()`, `remove(...)`, and operations that do not require a value of the hidden type can be type-valid. Actual mutability is decided by the implementation.
4. **"Raw types and wildcards both accept any list, so they are equivalent."** False: both can accept `List<String>`, yet a raw type permits unchecked add/set calls, whereas a wildcard keeps the compile-time safety barrier intact.
5. **"Unchecked warnings are fine because the code compiles."** False: warnings mark places where the compiler cannot prove type safety; errors can surface at another read site as `ClassCastException`.
6. **"`(List<String>) raw` will verify every element is a `String`."** False: due to type erasure, casting a list does not automatically inspect its elements. To be sure, you must validate the data or rely on a trustworthy source contract.
7. **"Using `List<Object>` on every parameter makes an API more flexible."** False: that parameter rejects `List<String>` and `List<Integer>`. If only reading generically, `List<?>` is usually more flexible and safer.

## 9. Self-Check Exercise

Suppose:

```java
List<Integer> nums = new ArrayList<>(List.of(1, 2));
List<?> a = nums;
List raw = nums;
List<Object> b = new ArrayList<>(nums);
```

Predict:

- What static types do `a.get(0)` and `b.get(0)` have?
- Does `a.add(3)` compile? Does `b.add("x")` compile?
- Does `raw.add("x")` compile, and what is the risk?
- Does `b.add("x")` mutate `nums`?

**Answer:** Both `get(0)` calls have static type `Object`; `a.add(3)` does not compile due to the hidden type, while `b.add("x")` is valid. `raw.add("x")` compiles, yet may trigger an `unchecked` warning and pollute `nums`, causing readers through `List<Integer>` to hit a runtime cast error. Mutating `b` does not change `nums` because `new ArrayList<>(nums)` created a new list.

## 10. Quick Selection Rules

- Use **`List<Object>`** when you want **a list genuinely permitted to hold multiple object types** and accept reading via `Object`.
- Use **`List<?>`** when you need to **accept/view a list of any element type**, without needing to insert a value of a specific type into the list. If you need to preserve type relationships across multiple values, consider a `<T>` method or a bounded wildcard.
- Avoid creating new APIs with **raw `List`**. Keep it only at genuinely necessary legacy integration boundaries, handle warnings deliberately, and validate data before lifting it into a trustworthy `List<T>`.

A quick litmus test when unsure is to ask: **"Am I allowed to add an arbitrary `Object` value into this list?"** If yes, `List<Object>` expresses the right contract. If you do not know what type the list holds and only need general operations, `List<?>` safely expresses that lack of information. Raw `List` strips away the protection Generics were designed to provide.
# Why Is `List<?>` Different from `List<Object>` in Java Generics?

The following two declarations look similar because every Java object can be viewed as an `Object`, but they express **two completely different type contracts**:

~~~java
List<?> unknownElements;
List<Object> objectElements;
~~~

- **`List<?>`**: a list that has **some concrete element type, yet we do not know what that type is**. It could be `List<String>`, `List<Integer>`, `List<Object>`, or another parameterized type. We can read elements as `Object`, but cannot arbitrarily add non-`null` elements because we do not know what type the underlying list accepts.
- **`List<Object>`**: a list whose **type argument is specifically `Object`**. We can add `String`, `Integer`, `Boolean`, and any other reference value because all of them are assignable to `Object`. However, we cannot directly assign `List<String>` or `List<Integer>` to a `List<Object>` variable.

Core distinction: **“being able to read an element as `Object`” does not mean “being allowed to write any `Object` into the list.”** The read-side type and the write contract are two different matters.

## 1. Understanding `?` and the name `Object` accurately

In `List<?>`, `?` is an **unbounded wildcard**: the compiler knows this is a `List` with a type parameter, but does not know what type that parameter is. For example:

~~~java
List<String> names = new ArrayList<>();
List<Integer> ages = new ArrayList<>();

List<?> first = names; // Valid.
List<?> second = ages; // Valid.
~~~

Each list keeps its original type argument. A wildcard **does not convert** `List<String>` into `List<Object>` and does not alter the collection's data. A `List<?>` variable only provides a **restricted view** of the collection.

In `List<Object>`, `Object` is a **specific type argument**, just as `String` or `Integer` are specific type arguments. Because ordinary generic classes/interfaces in Java are **invariant** in their type arguments, the following assignment is rejected:

~~~java
List<String> names = new ArrayList<>();
List<Object> objects = names; // COMPILE ERROR.
~~~

This example **intentionally does not compile**. Reason: if the assignment were allowed, we could call `objects.add(123)`, thereby inserting an `Integer` into a list that promises to hold only `String`.

The statement “every `String` is an `Object`” remains true; what is false is concluding “every `List<String>` is a `List<Object>`”.

## 2. Direct comparison of assignment, reading, and writing

| Characteristic | `List<?>` | `List<Object>` |
| --- | --- | --- |
| Meaning | List with an **unknown element type** | List with element type **specifically `Object`** |
| Accepts `List<String>` | Yes | No |
| Accepts `List<Integer>` | Yes | No |
| Accepts `List<Object>` | Yes | Yes |
| Static type of `get(index)` under normal assignment | `Object` | `Object` |
| `add("Java")` | Does not compile | Compiles |
| `add(123)` | Does not compile | Compiles (autoboxing to `Integer`) |
| `add(new Object())` | Does not compile | Compiles |
| `add(null)` | Compiles; actual collection may reject at runtime | Compiles; actual collection may reject at runtime |
| `size()`, `isEmpty()`, `contains(Object)` | Usable | Usable |
| `clear()`, `remove(index)` | Compiles; executability depends on collection | Compiles; executability depends on collection |
| Used as parameter accepting any list | Usually appropriate | Only accepts lists with type argument `Object` |

The comparison table describes **compile-time type checking**. Even if a call to `add` or `clear` compiles, the actual list may not permit modification (for example `List.of(...)`) and throw `UnsupportedOperationException` at runtime. Some collections also disallow `null`.

### Why do both return `Object` when reading?

`Object` is a supertype of all Java reference types. With `List<?>`, the actual element could be `String`, `Integer`, or any other type, so the compiler only guarantees the common bound `Object`. With `List<Object>`, `Object` is itself the declared element type.

~~~java
List<String> names = new ArrayList<>(List.of("An"));
List<?> unknown = names;

Object a = unknown.get(0); // Valid.
String b = names.get(0);   // Valid thanks to the original List<String> reference.

// String c = unknown.get(0); // ERROR: only Object is guaranteed.
~~~

The physical value is still the same `String` object; only the **static type promised by the compiler** differs. You can check with `instanceof` or perform a deliberate cast, but in that case you must handle situations where the actual type does not match.

## 3. Runnable program: an API accepting any list, a list holding multiple object types

Create the file **`UnknownVsObjectDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class UnknownVsObjectDemo {
    private static void printItems(List<?> items) {
        for (Object item : items) {
            System.out.println("item: " + item);
        }
    }

    public static void main(String[] args) {
        List<String> names = new ArrayList<>(List.of("Ada", "Lin"));
        List<Integer> ids = new ArrayList<>(List.of(7, 9));

        List<?> unknown = names;
        List<Object> objects = new ArrayList<>();

        objects.add("Ada");
        objects.add(7);
        objects.add(true);

        System.out.println("first = " + unknown.get(0));
        System.out.println("objects = " + objects);

        printItems(names);
        printItems(ids);

        unknown = ids;
        System.out.println("new first = " + unknown.get(0));
    }
}
~~~

Compile and run with **JDK 17 or later**:

~~~bash
javac UnknownVsObjectDemo.java
java UnknownVsObjectDemo
~~~

Exact stdout:

~~~text
first = Ada
objects = [Ada, 7, true]
item: Ada
item: Lin
item: 7
item: 9
new first = 7
~~~

Result analysis:

1. `unknown` initially views a `List<String>`. When calling `get(0)`, the static type is `Object` while the actual object is the string `"Ada"`.
2. `objects` is actually a `List<Object>`. It is allowed to hold a string, an `Integer`, and a `Boolean` at the same time.
3. `printItems(List<?>)` accepts both `List<String>` and `List<Integer>` without needing raw types or unchecked casts. Because it only reads and prints elements as `Object`, it does not need to know the concrete type argument.
4. After assigning `unknown = ids`, the wildcard variable views the integer list. This operation is valid because `List<?>` can reference lists of different types **at different times**.

Note: each collection object still has one element type matching its original reference in the program. Reassigning the `unknown` variable to another list **does not transform one list into another kind of list**.

## 4. Why can't `List<?>` add `Object`?

Consider:

~~~java
List<String> words = new ArrayList<>(List.of("one", "two"));
List<?> unknown = words;

Object newItem = Integer.valueOf(3);

// unknown.add(newItem); // COMPILE ERROR.
// unknown.add("three"); // ALSO A COMPILE ERROR.
~~~

The compiler sees `List<?>` and understands that the wildcard represents **an unknown concrete type**. That type might be `String`, as in the example; or it might be `Integer`. If it accepted any `Object`, Java would accidentally allow inserting an `Integer` into a `List<String>`. If it only allowed adding `String`, Java could fail when the variable points to a `List<Integer>`.

Therefore, **a `List<?>` variable does not allow adding a value of a concrete reference type**. This is completely different from `List<Object>`:

~~~java
List<Object> objects = new ArrayList<>();
objects.add("three");
objects.add(Integer.valueOf(3));
objects.add(new Object()); // All three calls are valid.
~~~

### Special case: `null`

~~~java
List<String> words = new ArrayList<>();
List<?> unknown = words;

unknown.add(null); // Compiles.
System.out.println(words); // [null]
~~~

`null` is a value compatible with every reference type, so the compiler allows adding it through a wildcard. However, this **does not mean every collection accepts `null`**: for example, lists from `List.of(...)` do not allow adding elements, and many collections forbid `null`. Code can compile and still throw an exception at runtime.

You should not treat the ability to call `add(null)` as a reason to use `List<?>` for storing data. The main purpose of a wildcard is to avoid making wrong assumptions about the element type.

## 5. `List<?>` is neither `List<Object>` nor raw `List`

Three easily confused declaration forms:

~~~java
List<?> unknown;        // Generic; an element type exists but is unspecified.
List<Object> objects;   // Generic; the type argument is specified as Object.
List raw;               // Raw type; omits generic parameter in the declaration.
~~~

With `List<?>`, the compiler preserves the information “this is a list with a consistent but unknown element type”. Therefore, it prevents an unsafe call like `add(42)`.

With raw `List`, some write operations **compile with an unchecked warning**, which can cause errors when reading:

~~~java
List<String> names = new ArrayList<>();
List raw = names;
raw.add(42); // Unchecked warning: can pollute the List<String> type.
~~~

This is a **code snippet illustrating a hazard**, not a recommended design. When `names.get(0)` is assigned to a `String` variable, the runtime can throw `ClassCastException` because the actual element is an `Integer`. Using `List<?>` to declare a read-only parameter is far safer than raw `List`.

Do not think of `List<?>` as a shorthand for `List<Object>`; the two types have different write permissions. Nor should you treat a wildcard as disabling type checking; its goal is to **preserve type checking without needing to know a specific type argument**.

## 6. Differences in write operations do not mean immutability

`List<?>` restricts the type of **new values** inserted into the list; it is not an immutable interface. For instance, if the backing list is modifiable, `remove(int)`, `remove(Object)`, and `clear()` can still change the contents through the wildcard alias. Meanwhile, `List<Object>` is also allowed to `add` a reference of type `Object`.

```java
List<String> words = new ArrayList<>(List.of("A", "B"));
List<?> unknown = words;
Object removed = unknown.remove(0);
System.out.println(removed + " -> " + words); // A -> [B]
```

The difference between the two contracts remains **unknown type argument** versus **exact `Object` type argument**. The fact that a `remove` call compiles does not guarantee it always succeeds: `List.of` forbids modification, `Arrays.asList` has fixed size, whereas `ArrayList` supports removal. That is a property of the implementation, not a consequence of the wildcard.

## 7. Wildcard capture: why can we still swap two elements in `List<?>`?

At first glance, without knowing the type `?`, we cannot call `set(index, newValue)` with an arbitrary `Object`. But we can rely on **a generic method to capture the hidden type** and operate on elements **already retrieved from that very list**.

Create the file **`WildcardCaptureDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class WildcardCaptureDemo {
    static void swapFirstTwo(List<?> values) {
        if (values.size() < 2) {
            return;
        }
        swapCaptured(values, 0, 1);
    }

    private static <T> void swapCaptured(List<T> values, int i, int j) {
        T first = values.get(i);
        values.set(i, values.get(j));
        values.set(j, first);
    }

    public static void main(String[] args) {
        List<String> letters =
                new ArrayList<>(List.of("A", "B", "C"));
        List<Integer> numbers =
                new ArrayList<>(List.of(10, 20));

        swapFirstTwo(letters);
        swapFirstTwo(numbers);

        System.out.println(letters);
        System.out.println(numbers);
    }
}
~~~

Compile and run:

~~~bash
javac WildcardCaptureDemo.java
java WildcardCaptureDemo
~~~

Stdout:

~~~text
[B, A, C]
[20, 10]
~~~

Step-by-step explanation:

1. `swapFirstTwo` takes `List<?>`, so it can be called with `List<String>` and `List<Integer>`.
2. When passing `values` to `swapCaptured`, the compiler uses **capture conversion** to treat the wildcard as a temporary consistent type, denoted `T` in the target method.
3. Both the element read out and the position written back have type `T`. Thus, the swap operation **does not create elements of a different type** from the original collection.
4. No cast from `Object` to `String`, no raw type, no `@SuppressWarnings("unchecked")` needed.

The standard library already provides `Collections.swap(List<?>, int, int)` with a similar idea. This example makes clear: wildcards **do not forbid every mutation**, rather they forbid writes whose type safety cannot be proven.

## 8. When should an API accept `List<?>`, and when should it accept `List<Object>`?

### 8.1. Only need to process elements as `Object`: choose `List<?>`

For example, methods that count, iterate/print, check emptiness, or log without needing to know the element type:

~~~java
static void describe(List<?> items) {
    System.out.println("Count: " + items.size());
    for (Object item : items) {
        System.out.println(item);
    }
}
~~~

This is an **illustrative method**, which must be placed in a class with `java.util.List` imported. It accepts `List<String>`, `List<Integer>`, `List<Object>`, and other list types.

If you replace the parameter with `List<Object>`, a caller passing `List<String>` will hit a compile-time error even though the method body only reads. The `List<Object>` contract has **unintentionally required more specificity than the API actually needs**.

### 8.2. Need to add arbitrary `Object` values: choose `List<Object>`

~~~java
static void appendMixedValues(List<Object> destination) {
    destination.add("created");
    destination.add(2026);
    destination.add(Boolean.TRUE);
}
~~~

This is also a **method to be placed in a class**. It has permission to add values of many different kinds because the caller must supply specifically a `List<Object>`:

~~~java
List<Object> destination = new ArrayList<>();
appendMixedValues(destination); // Valid.

// List<String> names = new ArrayList<>();
// appendMixedValues(names); // COMPILE ERROR.
~~~

If replaced with `List<?>`, the method body would not be allowed to call `add("created")` because it does not know what kind of list the caller passed in.

### 8.3. Need to store all elements from a specific list into a new `List<Object>`

Due to generic invariance, the following snippet is invalid:

~~~java
List<String> words = new ArrayList<>(List.of("A", "B"));
// List<Object> direct = words; // COMPILE ERROR.
~~~

But you can **copy**:

~~~java
List<String> words = new ArrayList<>(List.of("A", "B"));
List<Object> copied = new ArrayList<>(words);

copied.add(42);               // Valid for the new list.
System.out.println(words);    // [A, B]
System.out.println(copied);   // [A, B, 42]
~~~

This is a **snippet to place in a class**, with `java.util.List` and `java.util.ArrayList` imported. The `ArrayList` constructor takes `Collection<? extends E>`; for a destination with `E = Object`, a `Collection<String>` supplies valid elements. Two separate collections can share **element objects** without sharing list structure; adding an element to `copied` does not add it to `words`.

If you need to “view” any list, use `List<?>`. If you genuinely need to **store mixed kinds of objects** under a broad element type, create a `List<Object>` explicitly.

## 9. Relationship to `? extends Object` and other generics

The default bound of an unbounded wildcard is `Object` (for reference types). In ordinary contexts, `List<?>` carries an equivalent meaning to `List<? extends Object>`. However, they are **not equivalent to `List<Object>`**.

~~~java
List<String> words = new ArrayList<>();

List<?> first = words;                 // Valid.
List<? extends Object> second = words; // Valid.
// List<Object> third = words;         // ERROR.
~~~

The difference comes from **wildcards allowing many concrete type arguments**, whereas `Object` is an **exact type argument**.

The rule also appears in other generics:

~~~java
Set<String> names = new HashSet<>();
Set<?> unknownSet = names; // Valid.
// Set<Object> objectSet = names; // ERROR.

Map<String, Integer> scores = new HashMap<>();
Map<?, ?> unknownMap = scores; // Valid.
// Map<Object, Object> objectMap = scores; // ERROR.
~~~

This is **illustrative code that requires importing `java.util.*` and placing inside a class**. `Map<?, ?>` allows iterating entries viewed as `Object` for both key and value, but does not allow arbitrarily inserting a new key/value pair of unknown types (aside from special cases involving `null`). The type-safety rule is the same mechanism.

### Cannot overload solely with `List<?>` and `List<Object>`

Although the two types have different meanings at compile time, we **cannot** write both of the following overloads together in the same class:

~~~java
void handle(List<?> values) {}
void handle(List<Object> values) {} // ERROR: name clash due to same erasure.
~~~

This example **intentionally does not compile**. Both signatures have their generic arguments erased to the same form `handle(List)` when **type erasure** is applied. Thus, the difference in their assignability/writability is real in Java source, but not enough to distinguish two overloads in bytecode.

### Type checking with `instanceof`

`List<?>` is a usable form in an `instanceof` check, whereas checking a specific `Object` argument is not:

~~~java
Object value = List.of("x", "y");

if (value instanceof List<?> items) {
    System.out.println(items.size());
}

// if (value instanceof List<Object>) { ... } // COMPILE ERROR.
~~~

This is **illustrative code that requires importing `java.util.List` and placing inside a class**. At runtime it only knows for sure that the object is a `List`, and cannot assert that the list's concrete generic type argument is `Object`.

## 10. Common mistakes and how to recognize them

**Mistake 1 — Thinking `List<?>` is shorthand for `List<Object>`.** Wrong: `List<?>` accepts `List<String>`; `List<Object>` does not. Assignability and write capabilities differ.

**Mistake 2 — Using `List<Object>` as a parameter just to print any list.** The method will needlessly reject `List<String>` and `List<Integer>`. If you only read as `Object`, use `List<?>`.

**Mistake 3 — Thinking that because `get()` returns `Object`, `add(new Object())` must be valid.** Incorrect: reading with a wide type does not prove the actual list accepts adding an arbitrary `Object`.

**Mistake 4 — Thinking `List<?>` is immutable.** Wrong: removal, clearing, and swapping via a generic helper can be valid. Modifiability depends on the actual collection object.

**Mistake 5 — Using raw `List` to “solve” a compiler error.** Raw types can allow adding wrong elements with an unchecked warning and later cause `ClassCastException`. Wildcards and purpose-fit generic parameters are safer.

**Mistake 6 — Casting `List<?>` to `List<Object>` in order to call `add`.** The actual type might be `List<String>`; an unchecked cast can cause heap pollution. Never treat casting as a valid way to upgrade write permissions.

**Mistake 7 — Confusing copying with reference assignment.** `new ArrayList<Object>(aStringList)` creates a new collection, to which arbitrary `Object`s can be added. `List<Object> objects = aStringList` is an assignment of the same object with an incompatible type, so it is forbidden.

## 11. Self-check

Given:

~~~java
List<String> names = new ArrayList<>(List.of("A", "B"));
List<?> unknown = names;
List<Object> objects = new ArrayList<>();
~~~

Determine true/false for each statement regarding **compilability**:

1. `Object x = unknown.get(0);`
2. `String s = unknown.get(0);`
3. `unknown.add("C");`
4. `unknown.add(null);`
5. `objects.add("C");`
6. `List<Object> direct = names;`
7. `List<?> other = objects;`
8. `objects.add(unknown.get(0));`
9. `unknown.clear();`
10. `List<Object> copy = new ArrayList<>(names);`

**Answers:**

| Question | Compiles? | Explanation |
| --- | --- | --- |
| 1 | Yes | `get` from wildcard can be used as `Object` |
| 2 | No | Static type of `get` is not guaranteed to be `String` |
| 3 | No | The element type hidden behind the wildcard is unknown |
| 4 | Yes | `null` is compatible with every reference type; runtime depends on collection |
| 5 | Yes | `String` is a subtype of `Object` |
| 6 | No | Generic invariance; `List<String>` is not `List<Object>` |
| 7 | Yes | `List<?>` can accept `List<Object>` |
| 8 | Yes | The element `unknown.get(0)` is used as `Object`, matching the target |
| 9 | Yes | `clear()` does not require knowing the element type; runtime depends on collection |
| 10 | Yes | Copies elements into a new `ArrayList<Object>` |

The non-compiling expressions in the exercise are for analysis only; do not put them verbatim into a runnable program.

## 12. Conclusion

**`List<?>` denotes “a list of some element type”**, whereas **`List<Object>` denotes “a list with the exact type argument `Object`”**. Both allow reading elements as type `Object`, but only `List<Object>` allows writing arbitrary `Object` values. An unbounded wildcard accepts many different lists while still blocking unsafe writes. When designing an API that only needs to observe elements, `List<?>` is usually the right signature; when you genuinely need to add multiple kinds of objects into a list, use `List<Object>` or create a new list with the appropriate type argument.
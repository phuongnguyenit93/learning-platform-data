# Reading Values from an Unbounded Wildcard (`?`) in Java Generics

In Java Generics, the declaration `List<?>` means **a list that has a concrete element type, yet that type is unknown at the point of use**. That list could actually be `List<String>`, `List<Integer>`, `List<Customer>`, or another parameterized type. Java allows reading elements from `List<?>`, but the most general safe static type the program receives when reading is **`Object`**.

Foundational rule:

> From `List<?>`, elements can be read as `Object`; you cannot arbitrarily assume an element is `String`, `Integer`, or any concrete type. To use APIs specific to the element type, you must check the type at runtime or use a generic signature that carries better type information.

This lesson focuses on **reading** operations from an unbounded wildcard, understanding the result type, loops, safe data-retrieval operations, common limitations, and how to design methods accepting `?`.

## 1. The exact meaning of `List<?>`

Consider two lists:

```java
List<String> names = List.of("An", "Binh");
List<Integer> ages = List.of(20, 21);
```

Both can be referenced via `List<?>`:

```java
List<?> first = names; // Valid.
List<?> second = ages; // Valid.
```

The `?` sign is an **unbounded wildcard**. It represents an unspecified type argument. `List<?>` is not a “typeless” list, nor is it a list whose element type is `Object`; each list object still obeys the element type in its own declaration.

Comparison:

| Declaration | Directly accepts `List<String>`? | Read type from `get` | Meaning |
| --- | --- | --- | --- |
| `List<String>` | Yes | `String` | Elements are known to be `String` |
| `List<Object>` | No | `Object` | List declared to contain `Object`; reference types can be added |
| `List<?>` | Yes | `Object` | Has an unknown element type; safest to read as `Object` |
| Raw `List` | Usable, but loses generic checking | `Object` | Bypasses type-checking info; easily produces `unchecked` warnings |

Easy-to-miss point: although both `List<Object>` and `List<?>` allow assigning retrieved values to an `Object` variable, they **differ when accepting arguments and writing elements**. `List<String>` cannot be assigned to `List<Object>` because Java generics are invariant in their type arguments; however, it can be assigned to `List<?>`.

## 2. Reading with `get(index)`: the safe result is `Object`

With a `List<?> items` variable, the expression `items.get(index)` has a type treated by the compiler as an unknown **capture** type, often described in error messages with notation like `CAP#1`. Because this type is unknown yet is a reference type with a default upper bound of `Object`, the result can be assigned to an `Object` variable:

```java
List<?> items = List.of("Java", "Generics");

Object value = items.get(0); // Valid.
System.out.println(value);   // Java

// String text = items.get(0); // Does not compile:
// the compiler cannot prove the element type is String.
```

In terms of type inference, you can visualize:

```text
List<?> items
    |
    | get(0)
    v
element of type CAP#1 (actual type unknown)
    |
    | safe reference widening to Object
    v
Object value
```

This holds even when the author knows the actual object was created from `List.of("Java", "Generics")`. A variable already declared as `List<?>` no longer provides a `String` type guarantee at the `get` call site. The compiler relies on the **static type of the expression**, rather than inferring the type argument backward from a value previously assigned to the variable.

Several other limitations still apply even when the read operation is valid:

- `get(0)` on an empty list throws `IndexOutOfBoundsException`.
- If a list implementation allows `null` elements, `get` may return `null`; check before calling methods on the value.
- Reading via `List<?>` does not alter, convert, or copy the element object; the `Object` result still references the same object.
- You cannot assume the static reference type `Object` contains any methods specific to the element type.

## 3. Complete Java 17 example: reading multiple list types

Save the following program as `UnboundedReadDemo.java`:

```java
import java.util.List;

public class UnboundedReadDemo {
    static void printElements(List<?> items) {
        System.out.println("size=" + items.size());

        for (int i = 0; i < items.size(); i++) {
            Object element = items.get(i);
            String type = element == null
                    ? "null"
                    : element.getClass().getSimpleName();

            System.out.println(i + ": " + element + " (" + type + ")");
        }
    }

    public static void main(String[] args) {
        List<String> words = List.of("Java", "API");
        List<Integer> numbers = List.of(10, 20);

        printElements(words);
        printElements(numbers);
    }
}
```

Compile and run with Java 17 or later:

```bash
javac UnboundedReadDemo.java
java UnboundedReadDemo
```

Result:

```text
size=2
0: Java (String)
1: API (String)
size=2
0: 10 (Integer)
1: 20 (Integer)
```

The method `printElements(List<?> items)` does not need to know what type the list contains in order to count elements, access by index, and print a representation of each object. The `getClass()` call in the example is only used to **observe the runtime type** of a non-`null` element. That information does not change the static type of `items` from `List<?>` to `List<String>` or `List<Integer>`.

This is a typical situation where an unbounded wildcard should be used: the algorithm works uniformly across all objects and does not need to invoke a specialized method of the element type.

## 4. Reading with enhanced `for`, iterator, stream, and array

You do not necessarily have to use indices. `List<?>` implements `Iterable<?>`, so it can be iterated like this:

```java
static void printEach(List<?> items) {
    for (Object item : items) {
        System.out.println(item);
    }
}
```

With an iterator, the result type is also unknown:

```java
Iterator<?> it = items.iterator();
while (it.hasNext()) {
    Object item = it.next();
    System.out.println(item);
}
```

The two snippets above illustrate **method bodies**, not standalone programs. The snippet using `Iterator<?>` requires `import java.util.Iterator;` and `items` must be an already-declared `List<?>`.

Similarly:

```java
Stream<?> stream = items.stream();
Object[] array = items.toArray();
```

This snippet requires `import java.util.stream.Stream;`. `Stream<?>` can be traversed as type `Object`; parameterless `toArray()` returns `Object[]`. If you want elements of type `String` or `Number`, you must have type grounds first before converting or applying a bounded signature.

**Technical note:** `Iterable<?>`, `Iterator<?>`, `Stream<?>`, and `List<?>` are separate generic types; the compiler checks each expression against the corresponding method signature. Together they reflect one principle: reading values belonging to an unspecified type argument remains safe when viewing the value as `Object`.

## 5. What if you want to use methods specific to the element type?

Because `Object` does not have methods like `String.toUpperCase()` or `Number.doubleValue()`, the following snippet does not compile:

```java
List<?> items = List.of("java");

// items.get(0).toUpperCase(); // Does not compile.
// String text = items.get(0);  // Does not compile.
```

There are two solutions, depending on the business semantics.

### 5.1. Runtime type checking with `instanceof`

If the data genuinely can have different types and needs per-type handling, use a type check before invoking methods. Java 17 supports pattern matching for `instanceof`:

Save as `SafeWildcardRead.java`:

```java
import java.util.List;

public class SafeWildcardRead {
    static void describeFirst(List<?> items) {
        if (items.isEmpty()) {
            System.out.println("empty");
            return;
        }

        Object first = items.get(0);

        if (first instanceof String text) {
            System.out.println("text: " + text.toUpperCase());
        } else if (first instanceof Number number) {
            System.out.println("number: " + number.doubleValue());
        } else if (first == null) {
            System.out.println("null");
        } else {
            System.out.println("other: " + first.getClass().getSimpleName());
        }
    }

    public static void main(String[] args) {
        describeFirst(List.of("java"));
        describeFirst(List.of(7));
        describeFirst(List.of());
    }
}
```

```bash
javac SafeWildcardRead.java
java SafeWildcardRead
```

Result:

```text
text: JAVA
number: 7.0
empty
```

The `instanceof String text` branch guarantees that inside that branch, **the variable `text`** has type `String`. That does not cause the entire `items` list to be inferred as `List<String>`: there may be elements of other types at other indices, especially when sources are passed through different types.

If an explicit cast is unavoidable, such as `String text = (String) items.get(0);`, remember that casts are only verified at runtime and may throw `ClassCastException`. Do not use casting merely to hide a lack of type information.

### 5.2. Using a bounded wildcard if the business logic needs a specific family of types

If the method needs to read numbers for calculation, a better signature is `List<? extends Number>`:

```java
static double sum(List<? extends Number> numbers) {
    double total = 0;
    for (Number number : numbers) {
        total += number.doubleValue();
    }
    return total;
}
```

Now the compiler guarantees every element read out can be viewed as `Number`. The method accepts `List<Integer>`, `List<Double>`, and `List<Number>` without needing an `instanceof Number` check for each element. Conversely, `List<?>` is for cases where the algorithm **does not need** to know any specific properties beyond what `Object` provides.

You can keep the differences in mind:

| Parameter type | What does the compiler know when reading? | Can call directly |
| --- | --- | --- |
| `List<?>` | Element is an unknown reference type | `Object` methods |
| `List<? extends Number>` | Element is `Number` or a subtype | `doubleValue()`, `intValue()`, etc. |
| `List<? super Integer>` | Element belongs to an unknown supertype of `Integer` | When reading, only `Object` is guaranteed |
| `List<String>` | Element is `String` | `length()`, `toUpperCase()`, etc. |

`? super Integer` allows **writing** `Integer` but does not help read values of type `Integer`. The lower bound only guarantees the destination accepts `Integer`; the actual list could also be `List<Object>`.

## 6. Example with `Map<?, ?>`: reading both key and value as `Object`

With `Map<K, V>`, the two type arguments are independent. `Map<?, ?>` indicates that both the key type and the value type are unknown. We can read from the map, yet cannot automatically conclude the key is `Integer` or the value is `String`.

Save as `UnknownMapRead.java`:

```java
import java.util.Map;

public class UnknownMapRead {
    static void printEntries(Map<?, ?> map) {
        for (Map.Entry<?, ?> entry : map.entrySet()) {
            Object key = entry.getKey();
            Object value = entry.getValue();
            System.out.println(key + " -> " + value);
        }
    }

    public static void main(String[] args) {
        Map<Integer, String> labels = Map.of(7, "seven");
        printEntries(labels);

        Map<?, ?> unknown = labels;
        Object value = unknown.get(7);
        System.out.println("lookup: " + value);
    }
}
```

```bash
javac UnknownMapRead.java
java UnknownMapRead
```

Result:

```text
7 -> seven
lookup: seven
```

In `Map<?, ?>`, `get(Object key)` **accepts a parameter of type `Object`** per `Map`'s contract, so it can be called with a key object even though the generic key type is unknown. However, the retrieved result is still only guaranteed to be assignable to `Object`. `Map.Entry<?, ?>.getKey()` and `getValue()` follow the same rule.

If you want to preserve the static types of keys and values for specialized operations, use `Map<K,V>` or appropriate wildcard bounds instead of arbitrary casts.

## 7. Where does `?` differ from `Object` when reading?

Consider:

```java
List<String> names = List.of("Lan", "Mai");
List<?> unknown = names;
Object first = unknown.get(0); // Valid.

// List<Object> objects = names; // Does not compile.
```

The result from `unknown.get(0)` can be stored in `Object`, yet **there is no implicit conversion from `List<?>` to `List<Object>`**.

The reason is that a `List<Object>` variable allows adding any `Object` (if the list supports modification); if it pointed to `List<String>`, adding an `Integer` would break the element contract. Conversely, `List<?>` enforces operation limits that prevent adding an arbitrary element merely based on being able to read type `Object`.

Try comparing the following calls in a context with a modifiable list:

```java
List<String> strings = new ArrayList<>();
List<?> unknown = strings;
Object value = "hello";

unknown.size();       // Valid.
unknown.contains(value); // Valid: contains accepts Object.
unknown.getClass();   // Valid: method of Object.

// unknown.add(value); // Does not compile.
// unknown.add("hi");  // Does not compile.
```

The illustration above requires `import java.util.ArrayList;` and `import java.util.List;`.

**Being able to read an element does not mean having the right to write that very element back as type `Object`**. Reading and writing require different type guarantees.

## 8. Can you read an element and put it back into the same list?

This is a case that easily causes confusion with *wildcard capture*:

```java
static void replaceFirstWithSecond(List<?> items) {
    // items.set(0, items.get(1)); // Does not compile.
}
```

Even though `items.get(1)` reads from the exact same list, the static type the compiler processes at the `set` call still needs an argument compatible with the captured unknown element type. You cannot simply treat the result of the `get` call as an `Object` and pass it into `set`.

When you need to use **the same element type `T`** throughout an operation, use a generic method so the compiler gives a name to the captured type:

Save as `WildcardCaptureDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;

public class WildcardCaptureDemo {
    static void swapFirstTwo(List<?> items) {
        if (items.size() < 2) {
            return;
        }
        swapCaptured(items);
    }

    private static <T> void swapCaptured(List<T> items) {
        T first = items.get(0);
        items.set(0, items.get(1));
        items.set(1, first);
    }

    public static void main(String[] args) {
        List<String> words = new ArrayList<>(List.of("before", "after"));
        swapFirstTwo(words);
        System.out.println(words);

        List<Integer> numbers = new ArrayList<>(List.of(1, 2));
        swapFirstTwo(numbers);
        System.out.println(numbers);
    }
}
```

```bash
javac WildcardCaptureDemo.java
java WildcardCaptureDemo
```

Result:

```text
[after, before]
[2, 1]
```

The outer method accepts any `List<?>`. The `swapCaptured` method binds every read and write inside its body to the same type parameter `T`, so transferring elements from one position to another is type-safe. In the standard library, `Collections.swap(List<?>, int, int)` provides corresponding swap functionality; the example above helps explain why a generic method supports captured-type cases that direct code rejects.

Note that `set` may throw `UnsupportedOperationException` if the list does not support modification; the example uses `ArrayList` to ensure the list can be updated.

## 9. Checking and traversing contents without knowing the type argument

Some operations do not require a concrete element type, so they can be implemented generally via `List<?>`:

```java
static boolean hasAnyItem(List<?> items) {
    return !items.isEmpty();
}

static Object firstOrNull(List<?> items) {
    return items.isEmpty() ? null : items.get(0);
}

static void logObjects(List<?> items) {
    for (Object item : items) {
        System.out.println(item);
    }
}
```

These are illustrative methods; to compile them together, place them in a class with `import java.util.List;`. Here:

- `isEmpty()` and `size()` do not depend on the type argument.
- `get(0)` and the loop read out `Object`.
- `contains(Object)`, `indexOf(Object)`, and `lastIndexOf(Object)` accept an `Object` argument, so they can be called without knowing the generic type.

`List<?>` is usually suitable for APIs that check, display, count elements, log, or inspect data structures when specialized methods on individual elements are not required.

With a completely unknown type, handling as `Object` is safe with respect to the **type system**, but does not automatically guarantee every business operation succeeds: element methods may throw exceptions; `toString()` may contain sensitive information, or the list may be modified during traversal. Use only the data you truly need to process.

## 10. Reading through a wildcard does not guarantee an immutable list

A **read-only** method should choose `List<?>` when no concrete type argument is needed, but that signature does not stop others from modifying the backing list; `clear()` or `remove(Object)` themselves can also be called through the wildcard.

```java
List<String> source = new ArrayList<>(List.of("A", "B"));
List<?> view = source;
Object first = view.get(0);
view.clear();
System.out.println(first + " / " + source); // A / []
```

The example uses a modifiable `ArrayList`. With `List.of(...)`, the `clear()` operation will not be supported. If you need a snapshot that disallows structural modification, consider `List.copyOf(source)` (which does not accept null elements); do not confuse immutability guarantees with wildcard types or thread-safety.

## 11. Unbounded wildcard and generic method: choosing by reading needs

A method that only needs to read as type `Object` can accept `List<?>` directly:

```java
static void display(List<?> items) {
    for (Object item : items) {
        System.out.println(item);
    }
}
```

There is no need to introduce a type parameter `<T>` just to rewrite it as:

```java
static <T> void displayGeneric(List<T> items) {
    for (T item : items) {
        System.out.println(item);
    }
}
```

Both examples handle `List<String>` and `List<Integer>`. When `T` appears only once in the signature and there is no relationship between parameters, `List<?>` usually expresses the intent more simply.

However, `<T>` is useful when the type needs to be **preserved and connected** through the return value or multiple parameters:

```java
static <T> T first(List<T> items) {
    return items.get(0);
}
```

With:

```java
List<String> words = List.of("hello");
String word = first(words); // Compiler infers T as String.
```

If replaced with a method returning `Object`:

```java
static Object firstUnknown(List<?> items) {
    return items.get(0);
}
```

then:

```java
Object value = firstUnknown(words); // Valid.
// String word = firstUnknown(words); // Does not compile.
```

There is nothing “wrong” with the `firstUnknown` method: it simply provides a weaker contract. Choose `List<?>` when only a general object is needed; choose `<T>` when the caller needs to preserve the exact type of the read element.

## 12. Issues with `null`, empty lists, and safety when reading

Reading data from `List<?>` still requires checking ordinary runtime conditions.

**Empty list:** `items.get(0)` throws `IndexOutOfBoundsException` if `items.isEmpty()` is `true`. Wildcards do not guarantee element count.

**`null` elements:** a mutable list can contain `null`. When reading into `Object`, you must still check for `null` before calling `getClass()`, `toString()`, or other methods. `List.of(...)` since Java 9 does not accept `null`, but that is only true for that way of creating a list.

**Unmodifiable lists:** `List.of(...)` creates an unmodifiable list; this is independent of the wildcard type. Reading may succeed, whereas `clear` or `set` will throw `UnsupportedOperationException`.

**Multithreading:** the `List<?>` type does not inherently guarantee thread safety. If the list is modified concurrently, the outcome of reading or iterating depends on the implementation's contract and synchronization approach. Do not infer that “reading only through a wildcard” is a synchronization mechanism.

**Runtime type errors:** reading into `Object` does not perform a downcast to a concrete class. `ClassCastException` usually arises when subsequent code makes an invalid cast, or when the program previously broke generic guarantees via raw types/unchecked conversions.

## 13. Quick-check questions

**Question 1.** With `List<?> items`, which statement is definitely type-valid?

```java
Object a = items.get(0);
// String b = items.get(0);
// Integer c = items.get(0);
```

**Answer:** only the first line. The next two lines require the compiler to know the concrete element type, yet `?` does not provide that information. The first line can still fail at runtime if the list is empty.

**Question 2.** Why can we write `for (Object value : items)`?

**Answer:** every element of a `List<?>` is an object of some unknown reference type, so viewing each element as `Object` is safe.

**Question 3.** Are `List<?>` and `List<Object>` identical?

**Answer:** no. Both read out `Object`, but `List<?>` directly accepts a list parameterized with any type, whereas `List<Object>` only accepts lists whose type argument matches `Object` under generic inheritance rules.

**Question 4.** If you need to call `Number.doubleValue()` on every element, should you accept `List<?>` or `List<? extends Number>`?

**Answer:** `List<? extends Number>`. The compiler then knows each element read out can be viewed as `Number`, so calling `doubleValue()` is safe without casting.

**Question 5.** If you need to return the exact type of the first element to the caller, which signature is more appropriate?

```java
static <T> T first(List<T> source)
```

**Answer:** this generic method preserves the relationship between the element type of `source` and the return type `T`, whereas `Object first(List<?> source)` only provides a general type.

## 14. Summary for application

- `?` represents an unknown type argument; **reading from `List<?>` guarantees assignability to `Object`**.
- `get`, `for` loops, and `Iterator<?>` all allow retrieving values as type `Object`; check for emptiness and `null` as usual.
- Never automatically treat a read result as `String`, `Integer`, or another concrete class. Use `instanceof` if the data is genuinely heterogeneous and needs runtime branching.
- When an algorithm needs a specific family of types, such as `Number`, use `? extends Number` to enrich type information on the read result.
- When you need to preserve the exact element type from input to output, use a type parameter `<T>`; when you need to handle any element as `Object`, `List<?>` is usually sufficient.
- Unbounded wildcards **do not turn a collection into immutable**, do not guarantee thread-safety, and do not permit arbitrarily adding elements just because an `Object` can be read.

Asking the question “**After reading an element out, what does the algorithm need to know about it?**” will help you choose accurately between `List<?>`, bounded wildcards, and generic methods.
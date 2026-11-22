# Generics in `Collection<E>` and `Map<K,V>`

## 1. Why Do Collections Need Generics?

Suppose a group of data is used to store people's names. The processing code expects each element to be a string so it can call `length()` or `toUpperCase()`. If that group accepts integers mixed in, errors might only appear when reading and casting.

Generics help express **data type** constraints right in the declaration:

```java
// Illustrative snippet inside a method; requires import java.util.*.
Collection<String> names = new ArrayList<>();
names.add("Lan");
// names.add(123); // Does not compile: Integer does not match String.

String first = names.iterator().next(); // No manual casting needed.
```

For maps, we need to express both sides of a mapping:

```java
// Illustrative snippet inside a method; requires import java.util.*.
Map<String, Integer> stock = new HashMap<>();
stock.put("BOOK", 10);
// stock.put(123, 10);     // Wrong key type.
// stock.put("PEN", "ten"); // Wrong value type.

Integer quantity = stock.get("BOOK");
```

Generics allow using the same collection API for many kinds of data, while the compiler checks the consistency of each usage.

In this lesson, distinguish between:

- Type parameter: a symbol in a generic declaration, such as `E`, `K`, `V`.
- Type argument: the actual type passed when using it, such as `String`, `Integer`.
- Parameterized type: the entire type such as `Collection<String>`.
- Implementation object: for instance, an `ArrayList<String>` or `HashMap<String, Integer>`.

This lesson uses Java 17 and focuses on generics in collections and maps; it does not require building a custom data structure library.

## 2. Reading E, K, and V with Their Proper Meanings

### 2.1. E Is the Element Type

In the name `Collection<E>`, `E` is commonly understood as "element". When `E` is replaced with `String`, element-related operations are checked against the corresponding type.

Examples of API signatures, simplified for readability:

```java
// Signature sketch, not a standalone program.
interface Collection<E> extends Iterable<E> {
    boolean add(E element);
    Iterator<E> iterator();
}
```

With `Collection<String>`:

- `add` accepts a reference compatible with `String`.
- `iterator` returns `Iterator<String>`.
- `next` on the iterator returns type `String` at a type-checked call site.

`List<E>`, `Set<E>`, `Queue<E>`, and related implementations continue propagating the element type through the API hierarchy. [Collection API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collection.html)

### 2.2. K and V Are Two Independent Parameters

In `Map<K, V>`:

- `K`: key type.
- `V`: value type.

`Map<String, Integer>` expresses "looking up an `Integer` value using a `String` key". Keys and values do not have to be of the same type. You can use `Map<String, String>` if both sides are strings; that is a specific choice, not a limitation of `Map`.

Some signatures:

```java
// Signature sketch, not a complete Map declaration.
V put(K key, V value);
V get(Object key);
Set<K> keySet();
Collection<V> values();
Set<Map.Entry<K, V>> entrySet();
```

`put` uses `K` and `V` to check the data being inserted. `get` returns `V`, but the query argument is `Object`. Do not mentally rewrite the signature as `get(K)`. [Map API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html)

### 2.3. The Letters E, K, V Are Naming Conventions

These letters are not keywords with special powers. They are type parameter names within the scope of a declaration. `T` is also commonly used for a general type.

Do not write `Collection<E>` in client code if `E` has not been declared in the enclosing scope. In normal usage, pass an actual type:

```java
Collection<String> words = new ArrayList<>();
Map<Long, String> userNames = new HashMap<>();
```

The two lines above are illustrative declarations inside a method or field and require importing the types in `java.util`.

See [Generic Types](https://docs.oracle.com/javase/tutorial/java/generics/types.html) to compare type parameters with type arguments.

## 3. Element Type and Implementation Class Are Two Separate Decisions

```java
// Illustrative snippet inside a method; requires import java.util.*.
List<String> first = new ArrayList<>();
List<String> second = new LinkedList<>();
```

The two objects have different implementation classes but are both viewed through the `List<String>` contract.

- `List` expresses a list and the API being used.
- `String` expresses the element type.
- `ArrayList` or `LinkedList` determines the implementation details and many runtime characteristics.

Changing the implementation class does not automatically change the elements from `String` to another type. Changing the type argument is also not merely changing the storage mechanism: `List<String>` and `List<Integer>` are two distinct parameterized types at compile-time type checking.

Similarly:

```java
// Illustrative snippet inside a method; requires import java.util.*.
Map<String, Integer> counts = new LinkedHashMap<>();
```

`Map` defines the key–value model; `String, Integer` define the two data types; `LinkedHashMap` further determines characteristics such as insertion-order iteration in its default configuration.

Generics do not automatically specify uniqueness, ordering, mutability, or thread safety. Those properties must still be read from the interface contract, the implementation, and how the object is created.

## 4. The Diamond Operator and Type Inference

### 4.1. No Need to Repeat Type Arguments on Both Sides

```java
// Illustrative snippet inside a method; requires import java.util.*.
List<String> names = new ArrayList<>();
Map<String, Integer> counts = new HashMap<>();
```

`<>` is called the diamond. The compiler infers the type arguments for the constructor from the context.

It can be written more verbosely:

```java
List<String> names = new ArrayList<String>();
```

However, in this situation, the `String` on the right-hand side is unnecessary repetition. The diamond does not disable generics and does not lose type checking.

### 4.2. var Does Not Infer from Subsequent Additions

```java
// Illustrative snippet inside a method; requires import java.util.*.
var values = new ArrayList<>();
values.add("text");
values.add(99);

System.out.println(values); // [text, 99]
```

Here there is no target type `List<String>`, and the constructor takes no arguments that help constrain the type. The inferred result is `ArrayList<Object>`. Adding `"text"` afterward does not turn the variable into an `ArrayList<String>`.

If you want the elements to be strings:

```java
// Two illustrative declaration choices; requires import java.util.*.
List<String> explicitContract = new ArrayList<>();
var explicitArgument = new ArrayList<String>();
```

`var` is still static type inference for local variables; it does not mean the variable dynamically accepts any type. [Local Variable Type Inference](https://docs.oracle.com/en/java/javase/17/language/local-variable-type-inference.html)

Carefully read the target type, constructor arguments, and type arguments before concluding what the compiler has inferred.

## 5. Reference Types, Boxing, and Null

Generic type arguments must be reference types. Do not write:

```java
// Intentionally non-compiling example.
// Collection<int> numbers;
// Map<String, double> prices;
```

Use wrapper classes:

```java
// Illustrative snippet inside a method; requires import java.util.*.
Collection<Integer> numbers = new ArrayList<>();
numbers.add(10); // Autoboxing int to Integer.

Integer boxed = numbers.iterator().next();
int primitive = boxed; // Unboxing Integer to int.
```

Type arguments can also be array types or other parameterized types, because they are reference types. For example, `List<int[]>` is valid; `int[]` is a reference array type, distinct from the primitive type `int`.

Generics do not encode a non-`null` guarantee in standard Java:

- `Collection<String>` can accept `null` from a type-checking standpoint.
- An implementation may or may not allow `null`.
- Unboxing a `null` `Integer` causes a `NullPointerException`.
- A `null` value does not become a `String` or `Integer` object.

See [Restrictions on Generics](https://docs.oracle.com/javase/tutorial/java/generics/restrictions.html) regarding the limitation on primitive type arguments. The policy for accepting specific values remains a separate layer of the contract.

## 6. Why Is `Collection<Integer>` Not a `Collection<Number>`?

`Integer` is a subtype of `Number`, but that relationship does not automatically propagate into type parameters:

```java
// Illustrative snippet inside a method; requires import java.util.*.
Collection<Integer> integers = new ArrayList<>();
// Collection<Number> numbers = integers; // Does not compile.
```

If this assignment were allowed, code acting through the `numbers` variable could add a `Double` to the very same object. When other code reads that collection expecting it to contain only `Integer` elements, the original assumption is broken.

That is why these type parameters are invariant (invariance). Do not use type casts to bypass the error and assume the data is safe.

What remains valid is an inheritance relationship that preserves the same type argument:

```java
// Illustrative snippet inside a method; requires import java.util.*.
ArrayList<Integer> implementation = new ArrayList<>();
List<Integer> list = implementation;
Collection<Integer> collection = list;
```

All these variables hold the same element type `Integer`.

The rule also applies independently to both sides of a map:

```java
// Illustrative snippet inside a method; requires import java.util.*.
Map<String, Integer> source = new HashMap<>();
// Map<Object, Number> target = source; // Does not compile.

Map<Object, Number> copy = new HashMap<>();
copy.putAll(source); // Copies data into a different object with compatible types.
```

Assigning a reference and copying elements are not the same action. `putAll` is designed to accept a source whose keys and values are compatible subtypes. [Generics, Inheritance, and Subtypes](https://docs.oracle.com/javase/tutorial/java/generics/inheritance.html)

## 7. `Collection<Object>`, `Collection<?>`, and Raw Collection

These three forms are not equivalent:

| Type | Meaning | Reading elements | Adding non-null elements |
| --- | --- | --- | --- |
| `Collection<Object>` | A collection whose element type is `Object` | Receives `Object` | Can add references of types compatible with `Object` if the object supports it |
| `Collection<?>` | A collection of an unknown type | Receives `Object` | Cannot directly add a specific type because the actual type is unknown |
| Raw `Collection` | Omits type arguments for legacy code interoperability | Receives `Object` | Can produce unchecked calls, losing type safety guarantees |

`Collection<Object>` is not "a variable that accepts any collection". It cannot be assigned from `Collection<String>` due to invariance.

`Collection<?>` can reference a `Collection<String>` or `Collection<Integer>` to perform operations that do not need to know the specific element type:

```java
// Method declaration snippet; requires import java.util.Collection.
static void printElements(Collection<?> values) {
    for (Object value : values) {
        System.out.println(value);
    }
}
```

You cannot call `values.add("A")` inside that method, because `values` might actually be a collection of `Integer`.

However, `?` does not automatically create an immutable view. Operations such as `clear` or `remove(Object)` can still be called if the underlying object supports them. `add(null)` may be valid from a type perspective, though the object's `null` policy might still reject it. Do not use a wildcard as a synonym for "unmodifiable".

Refer to [Wildcards](https://docs.oracle.com/javase/tutorial/java/generics/wildcards.html).

## 8. Wildcards When Reading from a Source and Writing to a Destination

### 8.1. extends: Accepting a Source of an Unknown Subtype

A summation function does not need to modify elements into another type; it only needs to read each element as a `Number`:

```java
// Method declaration snippet; requires import java.util.Collection.
static double sum(Collection<? extends Number> values) {
    double total = 0;
    for (Number value : values) {
        total += value.doubleValue();
    }
    return total;
}
```

You can pass `Collection<Integer>`, `Collection<Double>`, or `Collection<Number>`. The contract of this example requires the source and its elements to be non-`null`.

Do not add a `Double` to `values`: the actual type might be `Integer`. `? extends Number` means "some specific unknown type that is `Number` or a subtype of `Number`", not "every kind of `Number` can be written into here". [Upper Bounded Wildcards](https://docs.oracle.com/javase/tutorial/java/generics/upperBounded.html)

### 8.2. super: Accepting a Destination Capable of Holding the Type to Be Written

```java
// Method declaration snippet; requires import java.util.Collection.
static void appendIntegers(Collection<? super Integer> destination) {
    destination.add(10);
    destination.add(20);
}
```

The function can accept `Collection<Integer>`, `Collection<Number>`, or `Collection<Object>`. All three can hold the added `Integer` elements, provided the object supports the operation and any other constraints.

When reading through the `destination` variable, the generally safe type is `Object`. You cannot assert that every existing element is an `Integer`: a `Collection<Number>` might already contain a `Double`. [Lower Bounded Wildcards](https://docs.oracle.com/javase/tutorial/java/generics/lowerBounded.html)

### 8.3. Apply Just Enough

A common mnemonic rule is PECS: a source that produces elements uses `extends`, and a destination that consumes elements uses `super`.

It guides parameter design; it is not a mandate that every variable or return value must use a wildcard. An API returning `List<String>` is generally easier to use than one returning `List<? extends String>` without a specific reason.

Wildcards resolve type relationships at call sites. They do not automatically grant modification rights, remove `null` restrictions, or make operations atomic.

## 9. Generic Methods Link Types Between Input and Result

If you need to preserve a type relationship, you can declare a method-level type parameter:

```java
// Method declaration snippet; requires import java.util.*.
static <T> List<T> copyOfElements(Collection<? extends T> source) {
    return new ArrayList<>(source);
}
```

Reading from left to right:

- `<T>` declares the method's own type parameter.
- `List<T>` is the return type.
- The source supplies elements of type `T` or a subtype of `T`.
- The result is a new list capable of holding `T`.

Example:

```java
// Illustrative snippet inside a method, assuming copyOfElements is declared.
Collection<Integer> source = List.of(1, 2, 3);
List<Number> result = copyOfElements(source);
result.add(2.5);
```

The target context contributes to inferring the type `T` as `Number`. The `Integer` source is compatible, and the new list holds those element references. Adding a `Double` to `result` does not modify the source collection.

Each call does not generate a separate class or a separate runtime method copy for `Integer` and `Number`. This is a compile-time type-checking and type-inference mechanism for generic code.

See [Generic Methods](https://docs.oracle.com/javase/tutorial/java/generics/methods.html).

## 10. Generics in Map Views

Given `Map<String, Integer> counts`:

```java
// Illustrative snippet inside a method; requires import java.util.*.
Set<String> keys = counts.keySet();
Collection<Integer> values = counts.values();
Set<Map.Entry<String, Integer>> entries = counts.entrySet();
```

The three return types express three perspectives:

- `keySet`: unique keys according to the map contract.
- `values`: values may be duplicated, so it is not `Set<V>`.
- `entrySet`: entries holding both key and value with their exact respective types.

Iterating over entries:

```java
// Illustrative snippet assuming counts is already initialized.
for (Map.Entry<String, Integer> entry : counts.entrySet()) {
    String word = entry.getKey();
    Integer count = entry.getValue();
    System.out.println(word + "=" + count);
}
```

`Map.Entry<K, V>` continues carrying the map's type relationship. There is no need to cast the result of `getKey` to `String` or `getValue` to `Integer`. [Map.Entry API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.Entry.html)

These views are backed by the source map and are not independent copies by default. Generics describe element types; they do not change the backing-map–view relationship or the level of support for mutation operations.

### What Does It Mean That get Accepts Object?

```java
// Illustrative snippet inside a method; requires import java.util.*.
Map<String, Integer> values = new HashMap<>();
values.put("A", 1);

Integer found = values.get("A"); // 1
Integer absent = values.get(123); // null with HashMap in this example.
```

The fact that `get(123)` compiles does not make `123` a valid key to `put` into a `Map<String, Integer>`. Querying and inserting data have different signatures. Another implementation may impose different constraints or throw exceptions for query arguments.

`get` can return `null` when a key is missing; some maps also permit `null` values. Therefore, assigning directly to an `int` can cause a `NullPointerException` during unboxing. The type `V` does not eliminate the possibility of a missing result.

## 11. Nested Types: Read from Outside In

```java
// Illustrative snippet inside a method; requires import java.util.*.
Map<String, List<Integer>> scores = new LinkedHashMap<>();
scores.put("An", List.of(8, 9));

List<Integer> studentScores = scores.get("An");
Integer first = studentScores.get(0);
```

Meaning:

1. The map has `String` keys.
2. Each value is a `List<Integer>`.
3. Each element inside the list is an `Integer`.

You cannot write `scores.put("An", 8)`: the value must be an entire list. Nor can you use a `List<String>` as the value.

Each layer has its own contract. A mutable map does not mean the value list is mutable; here `List.of` does not support adding elements. A missing key in the map can also cause `scores.get(...)` to return `null` before reaching any list operation.

When a nested declaration becomes too long or hard to connect to domain meaning, consider creating a named data type, such as a student score record. Do not use `Map<String, Object>` to avoid design and then scatter type casts throughout the application.

## 12. Raw Types, Type Erasure, and Runtime Limitations

### 12.1. Raw Types Weaken Type Checking

```java
// Intentionally unsafe illustration inside a method.
// Requires import java.util.*; produces raw/unchecked warnings.
List<String> words = new ArrayList<>();
List raw = words;
raw.add(123);

// String first = words.get(0); // ClassCastException when reading as String.
```

The failure can occur far from where the bad data was inserted. Using generics consistently brings errors closer to where the code is written.

Do not change `List<String>` to a raw `List` just so a method can accept various kinds of lists. Use type parameters or wildcards appropriately. [Raw Types](https://docs.oracle.com/javase/tutorial/java/generics/rawTypes.html)

### 12.2. There Is Not a Separate ArrayList Class for Each Type Argument

```java
// Illustrative snippet inside a method; requires import java.util.*.
List<String> words = new ArrayList<>();
List<Integer> numbers = new ArrayList<>();

System.out.println(words.getClass().equals(numbers.getClass())); // true
```

Under type erasure, these usages rely on the same runtime class. The compiler checks generic constraints and inserts necessary casts where appropriate.

That does not mean all generic information is erased from every piece of metadata or that generics "do nothing". It means an ordinary `ArrayList` instance does not carry a separate runtime class proving whether its element type parameter is `String` or `Integer`. [Type Erasure](https://docs.oracle.com/javase/tutorial/java/generics/erasure.html)

### 12.3. Checking Structure Differs from Checking Individual Elements

Given an unknown source declared as `Object`:

```java
// Illustrative snippet inside a method; requires import java.util.*.
Object candidate = List.of("A", "B");

if (candidate instanceof List<?> values) {
    for (Object value : values) {
        System.out.println(value);
    }
}
// candidate instanceof List<String> cannot be used to prove
// that an arbitrary Object is a list containing only Strings.
```

`instanceof List<?>` checks that this is an object belonging to the list family; it does not verify that all its contents are `String`. If data comes from an external source, you must inspect and convert each element to build a result with the desired contract.

Similarly, do not create arrays using `new List<String>[10]`. Limitations related to types that are not fully represented at runtime are explained in [Non-Reifiable Types](https://docs.oracle.com/javase/tutorial/java/generics/nonReifiableVarargsType.html).

This lesson does not use unchecked casts as a way to "verify" data: casting does not iterate through elements to make the data safe.

## 13. Complete Program

Save as `GenericCollectionMapDemo.java`.

```java
import java.util.ArrayList;
import java.util.Collection;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public final class GenericCollectionMapDemo {
    private static <T> List<T> copyOfElements(
            Collection<? extends T> source) {
        return new ArrayList<>(source);
    }

    private static void appendIntegers(
            Collection<? super Integer> destination) {
        destination.add(10);
        destination.add(20);
    }

    private static double sum(Collection<? extends Number> values) {
        double total = 0;
        for (Number value : values) {
            total += value.doubleValue();
        }
        return total;
    }

    private static Map<String, Integer> countWords(
            Collection<String> words) {
        Map<String, Integer> counts = new LinkedHashMap<>();
        for (String word : words) {
            counts.merge(word, 1, Integer::sum);
        }
        return counts;
    }

    public static void main(String[] args) {
        Collection<String> words =
                new ArrayList<>(List.of("java", "map", "java"));
        String first = words.iterator().next();
        System.out.println("First word: " + first);

        Map<String, Integer> counts = countWords(words);
        System.out.println("Counts: " + counts);
        for (Map.Entry<String, Integer> entry : counts.entrySet()) {
            System.out.println(entry.getKey() + "=" + entry.getValue());
        }
        System.out.println("Keys: " + counts.keySet());
        System.out.println("Values: " + counts.values());

        Collection<Integer> integers = List.of(1, 2, 3);
        List<Number> numbers = copyOfElements(integers);
        numbers.add(2.5);
        System.out.println("Numbers: " + numbers);
        System.out.println("Sum: " + sum(numbers));

        List<Object> destination = new ArrayList<>();
        appendIntegers(destination);
        System.out.println("Destination: " + destination);

        Map<String, List<Integer>> scores = new LinkedHashMap<>();
        scores.put("An", List.of(8, 9));
        scores.put("Binh", List.of(7, 10));
        System.out.println("Nested: " + scores);
        int firstScore = scores.get("An").get(0);
        System.out.println("First score of An: " + firstScore);

        var inferredObjects = new ArrayList<>();
        inferredObjects.add("text");
        inferredObjects.add(99);
        System.out.println("Diamond with var: " + inferredObjects);

        List<String> strings = new ArrayList<>();
        List<Integer> otherIntegers = new ArrayList<>();
        System.out.println("Same runtime class: "
                + strings.getClass().equals(otherIntegers.getClass()));

        Collection<?> unknown = List.of("A", "B");
        for (Object value : unknown) {
            System.out.println("Unknown element: " + value);
        }
    }
}
```

Compile and run:

```shell
javac --release 17 -encoding UTF-8 -Xlint:unchecked GenericCollectionMapDemo.java
java GenericCollectionMapDemo
```

The code has been verified with `--release 17` on a newer JDK with no unchecked warnings. The intentionally non-compiling or raw-type snippets from the explanatory sections are not included in this program.

Stdout:

```text
First word: java
Counts: {java=2, map=1}
java=2
map=1
Keys: [java, map]
Values: [2, 1]
Numbers: [1, 2, 3, 2.5]
Sum: 8.5
Destination: [10, 20]
Nested: {An=[8, 9], Binh=[7, 10]}
First score of An: 8
Diamond with var: [text, 99]
Same runtime class: true
Unknown element: A
Unknown element: B
```

### Output Explanation

- `Collection<String>` makes the iterator return `String` without manual casting.
- The counting function uses `Map<String, Integer>`: the word is the key, and the occurrence count is the value.
- `merge(word, 1, Integer::sum)` sets `1` if no value exists yet; if a matching value already exists in this example, it adds `1`. The result is `java=2` and `map=1`.
- `entrySet`, `keySet`, and `values` expose the map's exact data types outward.
- `copyOfElements` creates a new `Number` list from an `Integer` source. After adding `2.5`, the sum is `8.5`.
- The `List<Object>` destination receives `Integer` elements from a function taking a `? super Integer` parameter.
- The nested map holds lists of scores; two `get` calls traverse two type layers.
- `var` combined with `new ArrayList<>()` in this context produces `ArrayList<Object>`, so it holds both a string and a number.
- Two differently parameterized `ArrayList` instances still share the same runtime class.
- `Collection<?>` allows iterating over elements as `Object` without knowing the specific type argument.

The program uses `LinkedHashMap` so that the insertion-based output order is predictable for comparison; it does not rely on the unguaranteed ordering of `HashMap`. [LinkedHashMap API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedHashMap.html)

## 14. What Generics Do Not Automatically Guarantee

| Expectation | Guaranteed by generics alone? | What else is needed? |
| --- | --- | --- |
| Elements match the declared type across type-checked calls | Yes, within the program's type system rules | Avoid raw types and unsafe unchecked casts |
| Elements are non-`null` | No | Input policies and validation checks |
| Collection is mutable | No | Object/factory contract |
| Elements are unique | No | Choose a `Set` model or domain rules |
| Stable iteration order | No | Interface/implementation with appropriate guarantees |
| Thread-safe concurrent access | No | Synchronization and suitable concurrent data structures |
| Elements are mutually comparable | Not merely by sharing a supertype | `Comparable` or an appropriate comparator |
| Valid domain/business values | No | Domain types and validation |
| Deep copy | No | Separate element-copying design |
| External data verified after a single cast | No | Deliberate element-by-element inspection/conversion |

Generics are an important layer of assurance, but they do not replace the entire data contract.

## 15. Common Mistakes

| Mistake | Why it fails | How to fix |
| --- | --- | --- |
| Writing `Collection<E>` when `E` is undeclared | `E` does not exist automatically | Pass an actual type or declare a type parameter |
| Writing `List<int>` | Generics do not accept primitive types | Use `Integer` |
| Assigning `List<Integer>` to `List<Number>` | Type parameters are invariant | Use a wildcard or create a suitably typed copy |
| Using `Collection<Object>` to accept any collection | Does not accept `Collection<String>` | Use `Collection<?>` if you only need to observe |
| Using a raw `Map` to dodge type errors | Loses key–value type association | Declare an appropriate `Map<K, V>` |
| Assuming `? extends Number` allows adding any `Number` | The actual type may be narrower | Use it as a read-only `Number` source; choose `super` for a destination |
| Assuming `? super Integer` reads back guaranteed `Integer` elements | The collection may hold elements of a supertype | Read as `Object` unless another guarantee exists |
| Believing `?` makes a collection immutable | Wildcards do not block all mutating operations | Control mutability through a dedicated contract |
| Using `var x = new ArrayList<>()` and expecting `String` | No constraining context is present | Specify the type argument or target type |
| Assuming `get(123)` compiling means `123` is a valid key for `put` | The query signature takes `Object` | Distinguish query APIs from insertion APIs |
| Using a cast to prove every element has the right type | A cast does not inspect individual elements | Validate/convert at the source boundary |

## 16. Self-Check and Practice

### Questions

1. In `Collection<String>`, which part is the type parameter and which is the type argument?
2. In `Map<String, List<Integer>>`, what are the key type and value type?
3. Why cannot `Collection<Integer>` be assigned directly to `Collection<Number>`?
4. How does `Collection<Object>` differ from `Collection<?>` in terms of assignability and adding elements?
5. When should you use `? extends Number`, and when should you use `? super Integer`?
6. What type is inferred for `var x = new ArrayList<>();` when no additional context is provided?
7. Why can `Map.get` accept an argument of a type other than `K` and still compile?
8. Does `List<String>` guarantee that it contains no `null` elements and is mutable?
9. Why can raw types cause errors to surface late?
10. Do two `ArrayList` instances with different type arguments require different runtime classes?

### Exercises

- Add an ill-typed call to the complete program, compile it, and explain the compiler error before removing the call.
- Write a function that prints all elements using `Collection<?>`; test it with a list of strings and a set of integers.
- Pass a `List<Integer>` and then a `List<Double>` to the `sum` function without changing its signature.
- Pass a `List<Integer>`, `List<Number>`, and `List<Object>` to `appendIntegers`; explain why all three are type-compatible.
- Write a map-copying function with the signature `static <K, V> Map<K, V> copyMap(Map<? extends K, ? extends V> source)` that returns a new `LinkedHashMap`.
- Create a `Map<String, List<Integer>>` for two students and iterate through it using `Map.Entry` without type casting.
- Enable `-Xlint:unchecked` in a raw-type experiment, identify the boundary generating the warning, and fix it so no warning remains.

### Reference Hints

1. `E` is the type parameter in the `Collection<E>` declaration; `String` is the type argument supplied at the point of use.
2. Key type is `String`, value type is `List<Integer>`; inside the list, the element type is `Integer`.
3. If assignment were allowed, code could insert a `Number` subtype other than `Integer` into the same underlying object.
4. `Collection<Object>` holds `Object` elements, whereas `Collection<?>` observes an unknown type; they are not the same type.
5. Use `extends` for a source to be read as `Number`; use `super` for a destination that needs to accept `Integer`.
6. `ArrayList<Object>`.
7. The signature is `get(Object)`; that does not change the key type required by `put`.
8. No; those belong to separate contract properties.
9. Bypassing type checks allows incompatible elements to slip in and only be caught later when read.
10. No; these type arguments are handled through type erasure.

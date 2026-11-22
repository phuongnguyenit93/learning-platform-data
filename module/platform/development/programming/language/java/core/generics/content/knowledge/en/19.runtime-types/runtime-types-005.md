# `instanceof` with `List<?>` and valid parameterized type cases in Java Generics

## 1. The problem: why is `instanceof List<?>` valid while `instanceof List<String>` is usually rejected?

`instanceof` is a Java operator used to ask whether a **non-null** reference can be viewed as a specified type at runtime:

~~~java
Object value = List.of("Java", "Kotlin");

System.out.println(value instanceof List);     // true
System.out.println(value instanceof List<?>);  // true

// System.out.println(value instanceof List<String>); // Does not compile.
~~~

When an object is created from `ArrayList<String>` or `List.of("Java")`, the JVM still does not retain the full type arguments of a collection object to inspect all elements. Because of how Java generics are implemented via **type erasure**, the runtime can check whether the object implements `List`, yet it cannot reliably distinguish `List<String>` from `List<Integer>` solely by a runtime check on that object.

`List<?>` is a particularly useful case: it is a **parameterized type with an unbounded wildcard**. It is considered a **reifiable type** under language rules, meaning it can appear on the RHS of `instanceof` from an `Object` expression. However, `?` means "unknown element type," **not** "all elements have been checked and are valid `String`s."

This lesson explains:
- Which types can be used in `instanceof`.
- Why `List<?>`, `Map<?, ?>`, `Class<?>`, and `List<?>[]` can be valid.
- Why `Object instanceof List<String>` is invalid.
- An important exception from Java 16 onward: **some concrete parameterized types are also allowed** when the static type of the left-hand expression guarantees an appropriate casting conversion.
- Pattern matching for `instanceof` in Java 17.
- How to **check each element** if business logic genuinely requires `List<String>`, including nested structures.

## 2. Type erasure and runtime checking limits

Suppose two variables:

~~~java
List<String> words = new ArrayList<>();
List<Integer> numbers = new ArrayList<>();
~~~

At compile time, `List<String>` and `List<Integer>` are two distinct parameterized types. The compiler prevents calls like `words.add(123)`; thanks to this, normal properly generic code does not need manual casts when reading.

However, the `ArrayList` objects of the two variables are not completely different specialized runtime classes per `T`. With the declarations above:

~~~java
System.out.println(words.getClass() == numbers.getClass()); // true
~~~

Having the same runtime class does not mean having the same compile-time element type. The JVM has no general `instanceof List<String>` mechanism that iterates through all elements and proves they are `String`.

**Two very different questions:**

1. "Is the object a `List`?" — `instanceof List<?>` can check this.
2. "Is every element in the `List` actually a `String`?" — requires checking elements or relying on an API with a trustworthy type invariant.

Example:

~~~java
Object mixed = List.of("Java", 7);
boolean isList = mixed instanceof List<?>; // true.
~~~

`mixed` contains both `String` and `Integer` yet is still a `List`, so the `true` result is accurate. If code looks only at `isList` and casts the whole data into `List<String>`, it has drawn a conclusion not supported by the check.

## 3. What does reifiable type mean in this context?

In the Java Language Specification, a **reifiable** type is a type that has sufficient representation needed at runtime under language rules. Important groups when learning `instanceof`:

- Primitive types (not a reference type on the RHS of `instanceof` in Java 17; do not write `value instanceof int`).
- Non-generic classes/interfaces such as `String`, `Number`, or `Runnable`.
- Raw types of a generic class/interface such as `List`, `Map`, or `ArrayList`.
- Parameterized types where **all type arguments are unbounded wildcards**, such as `List<?>` and `Map<?, ?>`.
- Arrays with a reifiable element type, such as `String[]` or `List<?>[]`.

For the `instanceof` operator on an `Object` reference, common practical RHS types are:

~~~java
Object input = List.of("A");

boolean a = input instanceof List;             // Valid: raw List.
boolean b = input instanceof List<?>;          // Valid: unbounded wildcard.
boolean c = input instanceof ArrayList<?>;     // Syntactically valid; result depends on runtime class.
boolean d = input instanceof Map<?, ?>;        // Valid: both arguments are wildcards.
boolean e = input instanceof Class<?>;         // Valid: Class<T> with wildcard.
boolean f = input instanceof List<?>[];        // Valid: array of reifiable component type.
~~~

These are **compile-time valid checks**, not meaning all of them return `true`. With `input` being `List.of("A")`, `input instanceof ArrayList<?>` is typically `false`, because the `List.of` API does not promise to return a concrete `ArrayList`. `input instanceof Map<?, ?>` and `input instanceof List<?>[]` are also `false`.

`List<?>` is a parameterized type, **not a raw type**. If you only need to know that an object is a `List` and then read elements as `Object`, `List<?>` usually communicates intent better than raw `List`.

### Parameterized types that are non-reifiable in the standard sense

Examples:

~~~java
List<String>
List<Integer>
Map<String, Integer>
List<? extends Number>
Map<String, List<Integer>>
~~~

These types contain one or more concrete type arguments or bounded wildcards other than unbounded wildcards. They do not provide a general runtime check from `Object`. Therefore, the lines below **intentionally do not compile on Java 17**:

~~~java
Object value = List.of("Java");

// boolean a = value instanceof List<String>;
// boolean b = value instanceof Map<String, Integer>;
// boolean c = value instanceof List<? extends Number>;
~~~

Do not fix this by casting `(List<String>) value` before checking, because an unchecked cast does not validate all elements; it only moves the risk into an exception at the element-use site.

## 4. Table distinguishing `instanceof` RHS cases

| Check (assuming `Object value`) | Valid in Java 17? | What is actually checked |
| --- | --- | --- |
| `value instanceof String` | Yes | Object is `String` or a subtype of `String` (`String` is actually `final`). |
| `value instanceof List` | Yes | Object implements `List`; raw type loses generic expressiveness. |
| `value instanceof List<?>` | Yes | Object implements `List`, element type unknown. |
| `value instanceof ArrayList<?>` | Yes | Runtime class matches `ArrayList`, element type unknown. |
| `value instanceof Map<?, ?>` | Yes | Object implements `Map`, key/value types unknown. |
| `value instanceof Class<?>` | Yes | Object is a `Class` object, `T` unknown. |
| `value instanceof List<?>[]` | Yes | Object is an array whose runtime component matches `List`; does not check elements of each `List`. |
| `value instanceof List<String>` | No | Cannot verify the `String` argument via an `Object`. |
| `value instanceof Map<String, Integer>` | No | Cannot verify generic key/value via `Object`. |
| `value instanceof List<? extends Number>` | No | No direct runtime check for that generic bound via `Object`. |

The table above intentionally keeps **the LHS static type as `Object`**. If the LHS already has a concrete parameterized type, syntactic validity may differ under `casting conversion` rules; see the next section.

## 5. Important exception: concrete parameterized types are sometimes valid with `instanceof`

You should not learn an absolute rule that **"`instanceof List<String>` is always illegal."**

Since **Java 16**, the old restriction forcing the RHS type of `instanceof` to always be reifiable was relaxed when the source type can be converted to the target type by a valid **casting conversion**. This matters when the LHS already has a sufficiently concrete generic type.

Example that **compiles with Java 17**:

~~~java
List<String> known = new ArrayList<>(List.of("Java"));

boolean sameType = known instanceof List<String>;
boolean concrete = known instanceof ArrayList<String>;
~~~

In this situation, the compiler **already knows** the variable `known` is `List<String>`. Checking `ArrayList<String>` tests whether the runtime object belongs to the matching `ArrayList` class; the `String` type argument is already guaranteed at compile time on the source reference by the normal type system.

The pattern matching form is also valid because a `List<String>` source is not necessarily an `ArrayList<String>`:

~~~java
if (known instanceof ArrayList<String> actual) {
    System.out.println(actual.get(0)); // Java.
}
~~~

Core points:

- The compiler uses the **LHS static type** to decide whether an appropriate casting conversion exists to the RHS type.
- The runtime still primarily checks the raw class/interface of the object.
- The check **does not re-verify type arguments** from object contents. If the collection has been polluted by raw/unchecked operations, `instanceof ArrayList<String>` can still be `true` while reading a `String` element throws `ClassCastException`.

### Why is `Object instanceof List<String>` still wrong?

~~~java
Object unknown = new ArrayList<String>();

// boolean bad = unknown instanceof List<String>; // Does not compile.
boolean good = unknown instanceof List<?>;        // Valid.
~~~

Even though the author sees that the initializer contains `String`, **the static type of `unknown` is `Object`**. The compiler does not use memory of the initializer to prove the safety of a `List<String>` check at a later use of the variable. It only has `Object` information and cannot allow checking the `String` argument as a general runtime test.

Similarly:

~~~java
List<?> unknownElement = new ArrayList<String>();

// boolean bad = unknownElement instanceof ArrayList<String>; // Does not compile.
boolean good = unknownElement instanceof ArrayList<?>;        // Valid.
~~~

The wildcard indicates the element is undetermined; the compiler cannot conclude the type parameter is `String` solely from the type `List<?>`.

**Identification procedure:** before asking "is the RHS type valid with `instanceof`?", inspect **both the RHS type and the static type of the LHS expression**. If the LHS is `Object`, prefer a reifiable RHS; if the LHS already has concrete generic parameters, Java 16+ may permit a compatible parameterized RHS.

## 6. Pattern matching for `instanceof` in Java 17

Java 17 supports writing:

~~~java
Object input = List.of("A", "B");

if (input instanceof List<?> list) {
    System.out.println(list.size());
    Object first = list.get(0);
}
~~~

Here the compiler simultaneously:
1. Checks whether `input` is a `List`.
2. Binds the new variable `list` in the branch where the pattern matches.
3. Assigns static type `List<?>` to `list`.

There is no need to write the older form:

~~~java
if (input instanceof List<?>) {
    List<?> list = (List<?>) input;
    System.out.println(list.size());
}
~~~

Both are valid, yet pattern matching is cleaner and scopes the variable more sensibly.

### Scope of the pattern variable and short-circuiting

~~~java
Object input = List.of("A", "B");

if (input instanceof List<?> list && !list.isEmpty()) {
    System.out.println(list.get(0));
}
~~~

`list` can only be used in branches where the pattern match succeeded, and `&&` uses short-circuit evaluation so the second part is evaluated when `list` already has a valid value.

You cannot use the pattern variable where the compiler cannot prove it has been initialized:

~~~java
// if (input instanceof List<?> list || list.isEmpty()) { }
// Does not compile: on the RHS of ||, list is not definitely assigned.
~~~

### An always-true pattern can be rejected

In Java 17:

~~~java
List<String> already = List.of("Java");

// if (already instanceof List<String> same) { }
// Java 17 error: this pattern is an unconditional pattern.
~~~

The error above is **different in nature** from `Object instanceof List<String>`. The source type `List<String>` is already a subtype of the pattern type `List<String>`, making the pattern an impermissible form in `instanceof` at source level 17. Conversely, the traditional boolean expression check `already instanceof List<String>` can be valid when casting conversion rules are satisfied.

A useful pattern is checking a **not-yet-guaranteed subtype**:

~~~java
List<String> already = new ArrayList<>();

if (already instanceof ArrayList<String> array) {
    System.out.println(array.size());
}
~~~

This situation is valid because not every `List<String>` is an `ArrayList<String>`. Note that Java in later versions may evolve pattern rules; this lesson targets Java 17+ programs and explicitly notes source-level 17 constraints.

## 7. What does `List<?>` allow reading and what writes does it block?

After succeeding with:

~~~java
Object candidate = List.of("Java", 5);

if (candidate instanceof List<?> list) {
    Object first = list.get(0); // Valid.
    int count = list.size();     // Valid.

    // list.add("Kotlin");       // Does not compile.
}
~~~

With `List<?>`, the compiler knows the list has **some element type**, yet does not know what exact type it is. Thus elements can be safely read as `Object`; conversely, adding an arbitrary `String` could violate an element type that is actually `Integer` in another object.

Do not confuse with:

~~~java
List<Object> objects = new ArrayList<>();
objects.add("Java");
objects.add(5);
~~~

`List<Object>` is a parameterized type with `E` equal to `Object`, whereas `List<?>` holds an unspecified type argument. Because generics are invariant, a `List<String>` cannot be assigned directly to `List<Object>` yet can be assigned to `List<?>`:

~~~java
List<String> words = List.of("A");

// List<Object> wrong = words; // Does not compile.
List<?> safeView = words;       // Valid.
~~~

`list.add(null)` may be valid by **static type** for a wildcard yet is not guaranteed to succeed at runtime: `List.of` forbids modification, and many collections have their own null policy. This lesson avoids write operations on structures with unknown type arguments.

## 8. After `instanceof List<?>`, how to produce a verified `List<T>`

A pattern `candidate instanceof List<?> input` only checks **the container**. If an API genuinely needs `List<String>`, it must check the elements and build a new typed result, rather than performing an unchecked cast on the entire list.

With a class token `Class<T>`: (1) confirm the object is `List<?>`; (2) iterate over each `Object` and require `elementType.isInstance(item)`; (3) use `elementType.cast(item)` to place valid values into a new `ArrayList<T>`; (4) if using `List.copyOf`, clearly document the policy of **disallowing null** and returning an unmodifiable result list.

For example, `checkedList(List.of("A","B"), String.class)` produces a `String`-typed result, while `List.of("A", 1)` must be rejected even though it matches `instanceof List<?>`. The `checkedList` method is fully implemented and runs standalone in the program immediately below. The dedicated lesson on validating **every element** covers vacuous truth, null, domain rules, and concurrent mutation in greater depth.

## 9. Nested generics must be checked layer by layer

To accept `Map<String, List<Integer>>` from `Object`, `candidate instanceof Map<?, ?>` is only the first check. You must check that **every key** is `String`, **every value** is `List<?>`, and **every element** of each sublist is `Integer`. A new typed result is constructed once all data layers match; `(Map<String,List<Integer>>) candidate` cannot be used as a validator.

The complete program below implements `checkedScores` and asserts `nestedOdd=[1, 3]`. Creating a copy avoids sharing mutable collection structure with the source, though it does not automatically deep-copy elements nor substitute for consistency requirements when the source is mutated concurrently.


## 10. Complete Java 17+ program, compilable and runnable

Save file **InstanceofGenericsDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

public class InstanceofGenericsDemo {
    static <T> List<T> checkedList(
            Object candidate, Class<T> elementType) {

        if (!(candidate instanceof List<?> input)) {
            throw new IllegalArgumentException("List required");
        }

        List<T> result = new ArrayList<>();

        for (Object item : input) {
            if (!elementType.isInstance(item)) {
                throw new IllegalArgumentException("Unexpected element");
            }
            result.add(elementType.cast(item));
        }

        return List.copyOf(result);
    }

    static Map<String, List<Integer>> checkedScores(Object candidate) {
        if (!(candidate instanceof Map<?, ?> input)) {
            throw new IllegalArgumentException("Map required");
        }

        Map<String, List<Integer>> result = new HashMap<>();

        for (Map.Entry<?, ?> entry : input.entrySet()) {
            if (!(entry.getKey() instanceof String key)) {
                throw new IllegalArgumentException("String key required");
            }

            result.put(
                    key,
                    checkedList(entry.getValue(), Integer.class)
            );
        }

        return Map.copyOf(result);
    }

    public static void main(String[] args) {
        Object unknown = List.of("Java", 7);

        System.out.println(
                "listWildcard=" + (unknown instanceof List<?>)
        );
        System.out.println(
                "mapWildcard=" + (unknown instanceof Map<?, ?>)
        );
        System.out.println(
                "nullMatch=" + (((Object) null) instanceof List<?>)
        );

        if (unknown instanceof List<?> list) {
            System.out.println("size=" + list.size());
            System.out.println("first=" + list.get(0));
        }

        List<String> known =
                new ArrayList<>(List.of("Java"));

        // Java 16+: valid because LHS already has generic type String.
        System.out.println(
                "knownSubtype=" +
                (known instanceof ArrayList<String>)
        );

        if (known instanceof ArrayList<String> array) {
            System.out.println("patternFirst=" + array.get(0));
        }

        Object arrayCandidate = new List<?>[] {
                List.of("x"), List.of(4)
        };
        System.out.println(
                "wildcardArray=" +
                (arrayCandidate instanceof List<?>[])
        );

        System.out.println(
                "classWildcard=" +
                (String.class instanceof Class<?>)
        );

        System.out.println(
                "validated=" +
                checkedList(List.of("A", "B"), String.class)
        );

        try {
            checkedList(unknown, String.class);
        } catch (IllegalArgumentException error) {
            System.out.println("invalid=IllegalArgumentException");
        }

        Map<String, List<Integer>> scores =
                checkedScores(
                        Map.of(
                                "odd", List.of(1, 3),
                                "even", List.of(2, 4)
                        )
                );
        System.out.println("nestedOdd=" + scores.get("odd"));

        // The following raw operation intentionally pollutes the data of List<String>.
        List raw = known;
        raw.add(42);

        // instanceof does not verify the String type argument at runtime.
        System.out.println(
                "stillArrayList=" +
                (known instanceof ArrayList<String>)
        );

        try {
            String bad = known.get(1);
            System.out.println(bad);
        } catch (ClassCastException error) {
            System.out.println("polluted=ClassCastException");
        }
    }
}
~~~

Compile at Java 17 language level using a JDK supporting `--release 17`:

~~~bash
javac --release 17 -Xlint:unchecked InstanceofGenericsDemo.java
java InstanceofGenericsDemo
~~~

The compiler emits an **unchecked warning** at `raw.add(42)` because of the call on raw `List`. This is a compilation warning, not program stdout.

Exact stdout:

~~~text
listWildcard=true
mapWildcard=false
nullMatch=false
size=2
first=Java
knownSubtype=true
patternFirst=Java
wildcardArray=true
classWildcard=true
validated=[A, B]
invalid=IllegalArgumentException
nestedOdd=[1, 3]
stillArrayList=true
polluted=ClassCastException
~~~

### Analyzing the key lines

**`listWildcard=true`:** the input is a `List`, regardless of containing both `String` and `Integer`. The type `List<?>` accepts any element kind without validating a specific type.

**`mapWildcard=false`:** this object is a `List`, not a `Map`. The syntactic validity of `Map<?, ?>` does not force a `true` result.

**`nullMatch=false`:** `instanceof` on `null` always returns `false` in these examples; checking does not throw `NullPointerException` merely for a null reference.

**`knownSubtype=true` and `patternFirst=Java`:** the variable has type `List<String>`, while the runtime object is an `ArrayList`. Java 17 permits checking `ArrayList<String>` under casting conversion rules.

**`wildcardArray=true`:** the JVM checks the array structure for a `List`-compatible component type; it does not validate the generic element type inside each `List` of the array.

**`validated=[A, B]`:** the actual data-checking function accepts only `String` elements and builds a new list.

**`invalid=IllegalArgumentException`:** `unknown` contains an `Integer`, so the validator rejects it; `instanceof List<?>` still succeeded in the earlier step.

**`nestedOdd=[1, 3]`:** the nested validator checks the `Map`, `String` keys, `List`s, and each `Integer` before producing a typed value.

**`stillArrayList=true` yet `polluted=ClassCastException`:** the raw alias inserted an `Integer` into an `ArrayList` held via `List<String>`. `instanceof ArrayList<String>` does not detect the wrong element; the error surfaces when reading as `String` and the runtime cast check fails. This demonstrates that checking a runtime class is not equivalent to validating generic arguments.

## 11. Arrays of wildcard-parameterized types

A frequently overlooked case:

~~~java
List<?>[] lists = new List<?>[2];
lists[0] = List.of("A");
lists[1] = List.of(123);

Object value = lists;
boolean isListArray = value instanceof List<?>[]; // true.
~~~

`List<?>` is reifiable according to the language, so the array `List<?>[]` is valid. The runtime checks that the array has a component type compatible with `List`; it **does not** prove that elements of each individual list have a concrete type argument.

Conversely, you cannot directly create an array of a concrete generic type:

~~~java
// List<String>[] illegal = new List<String>[2];
// Error: generic array creation.
~~~

And when the LHS has type `Object`, `value instanceof List<String>[]` cannot be used as a way to verify an array of string lists.

Arrays in Java carry runtime component type information and can perform `ArrayStoreException` checks, whereas generics use erasure. `List<?>[]` combines both mechanisms yet does not overcome the deep-checking limit of generic arguments.

If an array is unnecessary, many modern APIs are cleaner and more consistent when using `List<List<?>>` or an appropriate generic structure instead of generic arrays.

## 12. How do raw `List` and `List<?>` differ in `instanceof`?

Both checks below can recognize an object implementing `List`:

~~~java
Object input = List.of("Java");

boolean rawCheck = input instanceof List;
boolean wildcardCheck = input instanceof List<?>;
~~~

The notable difference lies in **type expressiveness** and behavior as you continue using the result:

~~~java
if (input instanceof List<?> list) {
    Object element = list.get(0);
    // list.add("new"); // Blocked by the compiler.
}
~~~

`List<?>` retains the information that the list has an unknown element type. If you cast to raw `List` and then call `add`, code can lose generic checking and emit unchecked warnings.

~~~java
if (input instanceof List) {
    List raw = (List) input;
    // raw.add(42); // May emit an unchecked warning and cause heap pollution.
}
~~~

`instanceof List` itself is not always an error or guaranteed to emit a warning. The issue is that using **raw types** in new code does not provide generic safety the way wildcards do.

With Java 17, the usual recommendation is `instanceof List<?> list` for recognizing a collection of unknown element type, followed by validating each element if the domain requires a specific kind.

## 13. Other valid and invalid cases

### 13.1. Multiple unbounded wildcards

~~~java
Object value = Map.of("one", 1);

if (value instanceof Map<?, ?> map) {
    System.out.println(map.size());
}
~~~

`Map<?, ?>` is valid because both the key type and value type are unspecified. However, `Map<String, ?>` from an `Object` variable is not automatically accepted as a `String` check for keys.

### 13.2. Checking `Optional<?>` and `Class<?>`

~~~java
Object maybe = java.util.Optional.of("Java");
boolean optional = maybe instanceof java.util.Optional<?>;

Object classObject = String.class;
boolean classToken = classObject instanceof Class<?>;
~~~

The checks above are valid; with `Optional<?>` you cannot conclude the inner value is `String`, just as with `Class<?>` there is no concrete type parameter `T`.

### 13.3. `instanceof` does not accept primitives on the RHS in Java 17

~~~java
Object value = Integer.valueOf(3);

boolean boxed = value instanceof Integer; // Valid.
// boolean primitive = value instanceof int; // Does not compile in Java 17.
~~~

Generic type arguments also cannot be replaced with primitives:

~~~java
// List<int> invalid; // Invalid: type argument requires a reference type.
List<Integer> valid = List.of(1, 2, 3);
~~~

### 13.4. Even a known type cannot arbitrarily check any parameter

~~~java
List<String> known = List.of("Java");

// boolean wrong = known instanceof ArrayList<Integer>;
// No suitable casting conversion between String and Integer arguments.
boolean possible = known instanceof ArrayList<String>;
~~~

The Java 16+ relaxation **does not mean** every parameterized RHS is valid. The type system still examines cast compatibility between LHS and RHS.

## 14. Compiler errors to distinguish

**Error 1 — cannot check type argument from `Object`**

~~~java
Object object = List.of("Java");
// boolean invalid = object instanceof List<String>;
~~~

The Java 17 compiler may report:

~~~text
Object cannot be safely cast to List<String>
~~~

Reason: there is no suitable casting conversion to make checking the `String` argument safe from `Object`.

**Error 2 — source `List<?>` yet target wants `String`**

~~~java
List<?> unknown = List.of("Java");
// boolean invalid = unknown instanceof ArrayList<String>;
~~~

The compiler does not know whether the wildcard is actually `String`; from `List<?>` there is no safety proof for the concrete parameterized type `ArrayList<String>`.

**Error 3 — pattern adds no meaningful type check in Java 17**

~~~java
List<String> known = List.of("Java");
// if (known instanceof List<String> same) { }
// Java 17 reports an error because the pattern is always true by static type.
~~~

Do not confuse this with the traditional boolean operator form, which may be permitted. For example, `known instanceof ArrayList<String> array` is a meaningful pattern because only some `List`s are `ArrayList`s.

**Error 4 — believing `instanceof List<?>` proves elements are `String`**

~~~java
Object input = List.of("Java", 7);

if (input instanceof List<?> list) {
    // String first = (String) list.get(1); // Runtime ClassCastException.
}
~~~

A validator is needed when guaranteeing element types, not just a cast.

**Error 5 — using `instanceof Map<?,?>` and casting straight to `Map<String,List<Integer>>`**

~~~java
Object input = Map.of("scores", List.of("wrong"));

if (input instanceof Map<?, ?> map) {
    // The unchecked cast below does not deep-check:
//  Map<String, List<Integer>> invalid =
//          (Map<String, List<Integer>>) map;
}
~~~

The `Map` itself exists, yet the generic key/value types have not been checked. Check keys and sublists and build a typed structure.

## 15. Decision workflow when writing `instanceof` with generics

1. **Note the static type of the LHS.** If it is `Object`, do not infer type arguments from the runtime object.
2. **Identify the checking goal.** Are you only asking "is this a List?" or must you confirm every element is `String`?
3. **For `Object` and collections with unknown type arguments**, use `List<?>` or `Map<?, ?>`.
4. **If the LHS already has a parameterized type**, check whether the RHS type has a valid casting conversion; Java 16+ may permit checking concrete parameters in this context.
5. **If you want a binding pattern**, also check the source version's flow scoping and unconditional pattern rules. On Java 17, a pattern where the source type is already a subtype of the pattern type may be rejected.
6. **Do not treat `instanceof` as a general validator for nested generics.** To ensure `List<String>` or `Map<String,List<Integer>>` is truly clean, validate each layer/element.
7. **Use safe APIs and make copies** when receiving data from untrusted boundaries. Minimize raw types, unchecked casts, and mutable aliases.
8. **Verify with the target compiler**, e.g. `javac --release 17`, instead of inferring from code running on a different JDK version.

A maintenance note: pattern matching syntax and rules for unconditional patterns change across Java versions. This lesson uses Java 17 as the baseline for runnable examples; when applying on newer JDKs, check diagnostics under the corresponding `--release` or `--source`.

## 16. Self-check questions

**Question 1.** `Object value` holds a `List<String>`. Can you write `value instanceof List<String>`?

**Answer:** No in Java 17. The static type `Object` provides no information to check the `String` argument via a runtime test. Use `value instanceof List<?>` and validate each element if needed.

**Question 2.** Does `value instanceof List<?>` returning `true` prove all elements are `String`?

**Answer:** No. It only checks that the runtime object implements `List`; the `List` can contain `String`, `Integer`, or other data.

**Question 3.** Why can `List<String> known` use `known instanceof ArrayList<String>`?

**Answer:** Since Java 16, `instanceof` can use a non-reifiable parameterized type when the LHS static type permits an appropriate casting conversion to the RHS. The `String` type is already described by the `List<String>` reference, while the runtime checks whether the object is an `ArrayList`.

**Question 4.** If `known instanceof ArrayList<String>` is `true`, does it detect an `Integer` inserted through a raw alias?

**Answer:** No. The runtime test does not validate individual element types. Reading a polluted element as `String` can throw `ClassCastException`.

**Question 5.** Does `Map<?, ?>` automatically prove the map contains `String` keys and `List<Integer>` values?

**Answer:** No. You must check the entries, keys, `List`s, and `Integer`s inside.

**Question 6.** Can you use `value instanceof List<?>[]` from `Object`?

**Answer:** Yes. An array with component type `List<?>` is reifiable, yet the runtime does not check the element types inside each `List` in the array.

**Question 7.** Why is `if (known instanceof List<String> same)` rejected in Java 17 when `known` is already `List<String>`?

**Answer:** It is an unconditional type pattern according to static types; Java 17 pattern matching rules reject it. This error differs from being unable to safely cast from `Object` to `List<String>`.

**Question 8.** How do `List<?>` and raw `List` differ after an `instanceof` check?

**Answer:** Both can check the same runtime `List`, yet `List<?>` preserves the notion of an unknown element type and blocks arbitrary writes; raw `List` drops type arguments and easily leads to unchecked operations.

**Question 9.** What is a reliable way to accept `Object` data and produce a `List<String>` free of wrong-typed elements?

**Answer:** Use `instanceof List<?>`, iterate through each element checking `String.class.isInstance`, copy valid elements into a `List<String>`, and define a clear null/mutation policy.

## 17. Takeaways

**`instanceof List<?>` is valid and useful** because it checks for a runtime `List` without promising anything about element types. `List<String>` is not a general runtime test from `Object`.

However, **Java 16+ does not forbid every parameterized RHS**: when the LHS already has a suitable generic type, checks like `List<String> x; x instanceof ArrayList<String>` can compile. The compiler uses the expression's static type to evaluate casting conversion, yet the runtime still does not validate the contents of generic arguments.

To prove multi-layered data genuinely conforms to `List<String>` or `Map<String,List<Integer>>`, you must **validate each element and build a clearly typed result**. Distinguishing the three layers — **static type**, **runtime `instanceof` condition**, and **content validation** — is the key to using generics safely.
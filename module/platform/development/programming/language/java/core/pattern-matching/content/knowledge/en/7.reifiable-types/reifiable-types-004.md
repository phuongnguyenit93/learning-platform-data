# How Type Erasure Affects Patterns in Java

## 1. The Problem: Why Can We Check List<?> Directly from Object, but Not List<String>?

Java supports generics such as `List<String>`, `List<Integer>`, and `Box<T>` for type-safety checking at **compile time**. However, due to the **type erasure** mechanism, most generic type arguments (such as `String` in `List<String>`) do not exist as separate information for the JVM to distinguish different instances of the same generic class at runtime.

Therefore, for a value with static type `Object`:

~~~java
if (value instanceof List<?> items) {
    System.out.println(items.size());
}
~~~

is a valid check; whereas:

~~~java
if (value instanceof List<String> strings) { // COMPILE ERROR
    System.out.println(strings.size());
}
~~~

is rejected. The reason is not simply that "all generic patterns are forbidden": Java checks **cast compatibility at compile time** and the degree to which it can be verified at runtime. In a static type context that is specific enough, `instanceof ArrayList<String>` can still be valid.

This lesson explains:

- Which information type erasure removes and which information it retains.
- What a **reifiable type** is, and why `List<?>` works in pattern matching.
- Why `List<String>` is not automatically verified by `instanceof`, and when a pattern with concrete type arguments still compiles.
- Why pattern matching does not replace checking individual elements of a collection.
- How generic record pattern inference in Java 21 works without restoring erased type information.
- How to use `Class<T>` when runtime type checking is genuinely needed.

The main examples use **Java 17** for `instanceof` patterns; the `switch` and generic record pattern examples require **Java 21**.

## 2. How Does Type Erasure Work?

According to the Java Language Specification (JLS) `4.6, type erasure maps a type with generic information to a type without generic parameters or type variables:

- `List<String>` and `List<Integer>` both have erasure `List`.
- `ArrayList<String>` and `ArrayList<Integer>` both have erasure `ArrayList`.
- For `class Box<T>`, the type variable `T` is erased to the erasure of its **leftmost bound**; if no explicit bound is declared, the default bound is `Object`.
- For example, `<T extends Number>` has erasure `Number` for `T`.

The compiler still uses the full `List<String>` and `List<Integer>` types to catch many errors **before running**. At runtime, the JVM typically sees objects belonging to the same implementation class `ArrayList`, without knowing that one instance was declared as `ArrayList<String>` and the other as `ArrayList<Integer>`.

Therefore:

~~~java
ArrayList<String> words = new ArrayList<>(List.of("a"));
ArrayList<Integer> numbers = new ArrayList<>(List.of(1));
System.out.println(words.getClass().equals(numbers.getClass()));
~~~

prints `true`. This snippet requires `import java.util.ArrayList;` and `import java.util.List;` and is run in full in the next section.

**Type erasure does not erase the runtime class of an object.** The virtual machine still distinguishes an `ArrayList` from a `LinkedList`, a `String` from an `Integer`, and can still check `instanceof List<?>`. What is missing is runtime proof for the exact type argument such as `String` of a `List`.

The compiler may insert additional casts at certain places where generic values are read; a `ClassCastException` may occur when reading an element of the wrong type. That **does not turn** an `instanceof List<?>` check into a step that traverses and validates every element.

## 3. Reifiable Types: Which Types Can Be Checked at Runtime?

JLS `4.7 calls types that have all the necessary information available at runtime **reifiable types**.

Some important cases:

| Type | Reifiable? | Meaning for Patterns |
| --- | --- | --- |
| `String`, `Integer`, `Number` | Yes | The JVM can check the class or inheritance/interface relationship |
| `List<?>` | Yes | Can check whether the object implements `List`; does not verify the element type |
| `Map<?, ?>` | Yes | Can identify `Map`; does not verify the key or value types |
| `List` (raw type) | Yes | Can be checked, but using raw types loses many compile-time guarantees |
| `List<String>` | No | Cannot verify the `String` type argument from an arbitrary `Object` value |
| `List<? extends Number>` | No | A bounded wildcard is not the same as an unbounded wildcard `?` |
| `String[]` | Yes | The `String` component type of the array remains checkable at runtime |
| `List<?>[]` | Yes | The array elements have reifiable type `List<?>`; the element type inside each list is still unverified |

For a *parameterized type*, the typical reifiable case is when **all type arguments are unbounded wildcards** `?`. `List<?>` says "a list with elements of some type", not "a list of Strings".

Note on `null`:

~~~java
Object value = null;
boolean ok = value instanceof List<?> items; // false
~~~

The type pattern `List<?>` does not match `null`. Conversely, a `List<?>` itself can contain `null` elements if the way the list was created allows it; when iterating over elements, that case should be handled according to business logic.

## 4. Runnable Example on Java 17: List<?> and Checking Each Element

The complete program below checks the **collection** with `List<?>`, then checks each **element** with a type pattern `String text`.

Save as `ReifiablePatternDemo.java`:

~~~java
import java.util.ArrayList;
import java.util.List;

public class ReifiablePatternDemo {
    static void inspect(Object value) {
        if (value instanceof List<?> items) {
            System.out.println("LIST size=" + items.size());
            for (Object element : items) {
                if (element instanceof String text) {
                    System.out.println("STRING=" + text.toUpperCase());
                } else {
                    System.out.println("OTHER=" + element);
                }
            }
        } else {
            System.out.println("NOT_LIST");
        }
    }

    public static void main(String[] args) {
        inspect(List.of("java", 12, "patterns"));
        inspect("hello");
        ArrayList<String> words = new ArrayList<>(List.of("a"));
        ArrayList<Integer> numbers = new ArrayList<>(List.of(1));
        System.out.println("SAME_CLASS=" +
            words.getClass().equals(numbers.getClass()));
    }
}
~~~

Run:

~~~bash
javac --release 17 ReifiablePatternDemo.java
java ReifiablePatternDemo
~~~

Output:

~~~text
LIST size=3
STRING=JAVA
OTHER=12
STRING=PATTERNS
NOT_LIST
SAME_CLASS=true
~~~

Key takeaways:

1. `value instanceof List<?> items` checks whether the object is a `List` and binds the variable `items`. It **does not** guarantee that every element is a `String`.
2. When iterating over `List<?>`, each element value is read as `Object`. We use `element instanceof String text` to be certain that the element is a `String` so we can call `toUpperCase()`.
3. The value `12` is an `Integer`, so it enters the `OTHER` branch.
4. `"hello"` is a `String`, not a `List`, so it prints `NOT_LIST`.
5. Two `ArrayList` instances with different generic type arguments produce the same runtime class. This illustrates type erasure.

If the goal is "a list containing only Strings", the program needs to add a rule to validate the elements, such as **all elements are Strings**, instead of only checking `List<?>`.

## 5. Why Is Object instanceof List<String> Rejected?

This is a method that **intentionally does not compile** on Java 17/21:

~~~java
import java.util.List;

class BadObjectListString {
    static boolean test(Object value) {
        return value instanceof List<String> strings;
    }
}
~~~

Running `javac --release 17 BadObjectListString.java` produces a typical error:

~~~text
error: Object cannot be safely cast to List<String>
~~~

`Object` does not provide the generic information needed for the compiler to allow a check targeting `List<String>` without performing an *unchecked conversion*. Due to type erasure, at runtime there is no separate "`List<String>` type" to check with `instanceof`.

Commonly used approach:

~~~java
if (value instanceof List<?> items) {
    // items is List<?>; check elements when needed
}
~~~

This is an **illustrative snippet** placed inside a method that has a variable `value` of type `Object`. You can iterate over `items` and use `instanceof String text` on each element; or pass `items` to a business validation function.

Do not "fix" it with a raw type just to make casting easier:

~~~java
if (value instanceof List items) {
    // Discards generic information; easily leads to unchecked operations
}
~~~

Raw types are permitted by the language, but `List<?>` usually expresses the intent more accurately and preserves compile-time guardrails against many element-adding operations.

## 6. Important Exception: Some Generic Type Patterns with Concrete Arguments Are Still Valid

Do not conclude that "`instanceof` can only be used with reifiable types". Since Java 16, pattern matching for `instanceof` allows **certain** non-reifiable parameterized types, provided the static type of the expression guarantees that the check is valid under the *checked cast conversion* rules.

Consider the following Java 17 program:

Save as `StaticGenericPatternDemo.java`:

~~~java
import java.util.ArrayList;
import java.util.List;

public class StaticGenericPatternDemo {
    static String inspect(List<String> input) {
        if (input instanceof ArrayList<String> items) {
            return "ARRAY_LIST=" + items.get(0).toUpperCase();
        }
        return "OTHER_LIST=" + input.size();
    }

    public static void main(String[] args) {
        System.out.println(inspect(
            new ArrayList<>(List.of("java"))
        ));
        System.out.println(inspect(List.of("java")));
    }
}
~~~

~~~bash
javac --release 17 StaticGenericPatternDemo.java
java StaticGenericPatternDemo
~~~

Output:

~~~text
ARRAY_LIST=JAVA
OTHER_LIST=1
~~~

Why does this compile?

- The **static** type of `input` is `List<String>`, not `Object`.
- The pattern `ArrayList<String> items` checks whether the object is an `ArrayList`. At compile time, Java already knows the type argument is compatible from `List<String>`.
- At runtime, the check still only verifies the matching class `ArrayList`; **it does not traverse elements to prove every element is a String**.
- In the matching branch, `items` has static type `ArrayList<String>`, so the compiler allows calling `items.get(0).toUpperCase()`.

Conversely, if the parameter is only `Object input`, the pattern `ArrayList<String> items` generally does not satisfy the checked cast requirement because the necessary generic information is missing. Therefore, you must distinguish **the static type of the expression**, **the target type of the pattern**, and **the runtime condition**.

How to remember:

| Expression with static type | Pattern to test | Valid? |
| --- | --- | --- |
| `Object` | `List<?> items` | Yes |
| `Object` | `List<String> items` | No |
| `List<String>` | `ArrayList<String> items` | Yes |
| `Object` | `String text` | Yes |
| `Object` | `List raw` | Syntactically yes, but raw types should be restricted |

A type pattern can be valid even when the target type is not reifiable, as long as the compiler can prove appropriate safety based on the static type context. **This does not mean runtime has a generic type token.**

## 7. Heap Pollution Shows Patterns Do Not Validate Elements

*Heap pollution* is a situation where a variable of a parameterized type can refer to data that violates its type expectations, usually due to raw types or unchecked operations. Here is an example that **intentionally creates invalid data** to understand runtime limitations.

Save as `ErasurePollutionDemo.java`:

~~~java
import java.util.ArrayList;
import java.util.List;

public class ErasurePollutionDemo {
    @SuppressWarnings({"rawtypes", "unchecked"})
    static List<String> pollutedList() {
        List raw = new ArrayList<String>();
        raw.add(42);
        return raw;
    }

    public static void main(String[] args) {
        List<String> input = pollutedList();
        if (input instanceof ArrayList<String> items) {
            System.out.println("PATTERN_MATCH=" + items.size());
            try {
                String first = items.get(0);
                System.out.println(first);
            } catch (ClassCastException ex) {
                System.out.println("ELEMENT_CAST_FAILED");
            }
        }
    }
}
~~~

~~~bash
javac --release 17 ErasurePollutionDemo.java
java ErasurePollutionDemo
~~~

Output:

~~~text
PATTERN_MATCH=1
ELEMENT_CAST_FAILED
~~~

Explanation:

- The raw type in `pollutedList` allowed inserting `Integer 42` into an `ArrayList` that the rest of the code sees as `List<String>`. The `@SuppressWarnings` annotation only hides warnings in the code that intentionally creates bad data; it does not make the data type-correct.
- `input instanceof ArrayList<String> items` is valid given the static type `List<String>` and matches the runtime class `ArrayList`.
- When reading the first element into the variable `String first`, the JVM must enforce the `String` assumption, so the implicit cast fails with `ClassCastException`.
- The result proves that **pattern matching does not perform deep checking of generic contents**.

In real applications, avoid raw types and unchecked casts whenever possible. If receiving data from untrusted APIs, untyped collections, or objects passed in by external libraries, validate the data before using it as a specifically typed collection.

## 8. A Type Variable T Is Not a Runtime Pattern

Consider a generic method:

~~~java
static <T> boolean test(Object value) {
    return value instanceof T; // COMPILE ERROR
}
~~~

This snippet **intentionally does not compile**: `T` is a type variable, and at runtime there is no direct check for "whether a value is T" from an arbitrary `Object`. With `javac --release 17`, the error typically reads:

~~~text
error: Object cannot be safely cast to T
~~~

The same issue appears when trying to use `T.class` in a generic method: there is no class literal representing a non-reified type variable.

With `<T extends Number>`, the erasure of `T` is `Number`; however, checking "this is a Number" does not prove "this is specifically T" (it could be `Integer` or `Double`). You must not treat a type bound as a preserved runtime generic type argument.

If you need dynamic type checking with a concrete identity, pass a `Class<T>` object to the method as shown in the next section.

## 9. Using Class<T> When You Need to Check Elements by Concrete Runtime Type

`Class<T>` carries a **class token** supplied by the caller, such as `String.class` or `Integer.class`. This allows the program to check each value with `isInstance` and convert with `cast` with a controlled static type.

Save as `ClassTokenDemo.java`:

~~~java
import java.util.ArrayList;
import java.util.List;

public class ClassTokenDemo {
    static <T> List<T> matchingElements(
        List<?> source, Class<T> elementType
    ) {
        List<T> result = new ArrayList<>();
        for (Object element : source) {
            if (elementType.isInstance(element)) {
                result.add(elementType.cast(element));
            }
        }
        return result;
    }

    public static void main(String[] args) {
        List<?> values = List.of("a", 42, "b");
        System.out.println(matchingElements(values, String.class));
        System.out.println(matchingElements(values, Integer.class));
    }
}
~~~

~~~bash
javac --release 17 ClassTokenDemo.java
java ClassTokenDemo
~~~

Output:

~~~text
[a, b]
[42]
~~~

Here `String.class` actually exists at runtime and identifies `String`; `Integer.class` identifies `Integer`. The function returns a list containing **only the elements matching** the requested type. If you need to *reject* the entire list when a mismatched element is present rather than filtering, throw an exception when encountering an invalid value.

Limitation to remember: `Class<T>` represents a matching runtime class, but you cannot write `List<String>.class` to carry full generic type arguments. If you must express nested generic structures, you need to build a specific validation mechanism (or a type token from an appropriate library), because `Class<List<String>>` does not come automatically from `List.class`.

## 10. Pattern Matching for switch Is Also Subject to Erasure Limits (Java 21+)

Pattern matching in `switch` was finalized in Java 21. Case patterns must also be **applicable** to the static type of the selector.

The complete program below identifies a list without pretending to know the element type. Save as `SwitchErasureDemo.java`:

~~~java
import java.util.List;

public class SwitchErasureDemo {
    static String describe(Object value) {
        return switch (value) {
            case null -> "NULL";
            case List<?> items -> "LIST=" + items.size();
            default -> "OTHER";
        };
    }

    public static void main(String[] args) {
        System.out.println(describe(List.of("a", 1, "b")));
        System.out.println(describe("hello"));
        System.out.println(describe(null));
    }
}
~~~

~~~bash
javac --release 21 SwitchErasureDemo.java
java SwitchErasureDemo
~~~

Output:

~~~text
LIST=3
OTHER
NULL
~~~

`case List<?> items` is valid for an `Object` selector because the pattern has a reifiable type and the JVM can check the collection. In this branch, `items` remains `List<?>`; Java **does not** infer that any element is a `String`.

The following code **intentionally does not compile** if the selector has type `Object`:

~~~java
static int invalid(Object value) {
    return switch (value) {
        case List<String> words -> words.size(); // COMPILE ERROR
        default -> 0;
    };
}
~~~

The error is similar to `instanceof`: the compiler cannot perform a safe check to `List<String>` from `Object`. When you want to classify list contents, use `case List<?> items` and then check the elements or call a validation function.

The `switch` pattern and record pattern features used here require **Java 21+**; `instanceof String text` and `instanceof List<?> items` alone have been stable since Java 16.

## 11. Generic Record Patterns: Type Inference Relies on Static Types, Not Restoring Erased Type Arguments

Java 21 added finalized record patterns, allowing deconstruction of a record's data during pattern matching. With a generic record:

~~~java
record Box<T>(T payload) {}
~~~

the pattern `Box(var item)` extracts the `payload` component. The type of `item` is **inferred by the compiler from the static type information** available at the check site, not by reading generic arguments from the runtime object.

Complete program `GenericRecordPatternDemo.java`:

~~~java
record Box<T>(T payload) {}

public class GenericRecordPatternDemo {
    static String known(Box<String> box) {
        if (box instanceof Box(var item)) {
            return "KNOWN=" + item.toUpperCase();
        }
        return "OTHER";
    }

    static String unknown(Object value) {
        if (value instanceof Box(var item)) {
            if (item instanceof String text) {
                return "STRING=" + text.toUpperCase();
            }
            return "PAYLOAD=" + item;
        }
        return "NOT_BOX";
    }

    public static void main(String[] args) {
        System.out.println(known(new Box<>("java")));
        System.out.println(unknown(new Box<>(42)));
        System.out.println(unknown(new Box<>("java")));
        System.out.println(unknown("hello"));
    }
}
~~~

~~~bash
javac --release 21 GenericRecordPatternDemo.java
java GenericRecordPatternDemo
~~~

Output:

~~~text
KNOWN=JAVA
PAYLOAD=42
STRING=JAVA
NOT_BOX
~~~

Analysis:

- With `known(Box<String> box)`, the compiler sees the parameterized type `Box<String>`, so `Box(var item)` infers `item` as `String`. Calling `toUpperCase()` is valid.
- With `unknown(Object value)`, the outer type pattern recognizes an instance of `Box`, but `value` does not carry sufficiently specific static generic information. `item` is inferred as `Object`; therefore, to use `String`-specific operations, you must follow up with `item instanceof String text`.
- There is no step that "automatically rediscovers T at runtime". For the value `new Box<>(42)`, the runtime component is `Integer`, but the compiler still views `item` as `Object` in the `unknown` branch.

Record patterns also do not allow unchecked generic tests. The following snippet **intentionally does not compile** on Java 21:

~~~java
record Container<T>(T value) {}

static boolean invalid(Container raw) {
    return raw instanceof Container<String>(var item);
}
~~~

This is an illustrative snippet consisting of a record declaration and a method that need to be placed inside a class. `raw` only has the raw type `Container`; the compiler cannot prove a checked cast to `Container<String>`. Typical error:

~~~text
error: Container cannot be safely cast to Container<String>
~~~

To use generic record patterns safely, preserve generic information in parameter declarations and data from the start, or use a pattern that does not require a concrete type argument and then validate the component.

## 12. Summary of Typical Scenarios

| What you want to check | Solution | Does it verify generic contents at runtime? |
| --- | --- | --- |
| Is the object a list? | `value instanceof List<?> items` | No |
| Is the object a String? | `value instanceof String text` | Yes, for this object itself |
| Does a List<?> contain only Strings? | Iterate over elements and check each element with `instanceof String` | Yes, if all are checked against the defined criterion |
| Does a List<String> have an ArrayList implementation? | `input instanceof ArrayList<String> items` with `input` having static type `List<String>` | Only identifies the implementation class; does not deeply check generics |
| Want to extract elements belonging to a passed-in Class<T> | `elementType.isInstance(...)` and `elementType.cast(...)` | Yes, for the runtime class represented by the token |
| Generic record pattern on Box<String> | `box instanceof Box(var item)` | Compiler infers `String` from the static type; does not check the runtime generic argument |
| Generic record pattern on Object | `value instanceof Box(var item)` | Matches Box; component may have static type `Object` |

The *checked cast* and applicability rules apply according to the Java Language Specification of the version being compiled. When porting code between versions, use `javac --release 17` or `--release 21` to verify the exact syntax and allowed APIs.

## 13. Common Mistakes

1. **Assuming every `List<String>` leaves a String type trace at runtime.** Type erasure means an `ArrayList` object does not carry a separate identifier for each type argument.
2. **Assuming `List<?>` is `List<String>`.** `?` means the element type is unknown; only operations valid for an unknown type are permitted.
3. **Assuming a type pattern must always be reifiable.** A pattern like `ArrayList<String>` can be used when the expression has static type `List<String>` and the checked cast is valid.
4. **Using raw types and then trusting generic casts.** Raw operations can cause heap pollution; a pattern matching the runtime class still does not guarantee element types.
5. **Using type variable `T` in `instanceof` as a runtime class.** A type variable does not carry a class token on its own; pass `Class<T>` when you genuinely need to identify a concrete class.
6. **Believing generic record patterns infer T from runtime contents.** Type inference relies on the type of the expression and compile-time constraints.
7. **Using `case List<String>` in switch(Object).** An `Object` selector does not provide a safe checked cast to that parameterized type.
8. **Forgetting `null`.** `null instanceof List<?>` is `false`. With switch patterns, use `case null` when you want to handle this case explicitly.
9. **Equating a pattern match with valid business data.** For example, a `List<?>` may contain unexpected types, `null`, or data that fails application conditions. Separate validation is required.

## 14. Exercises and Answers

### Exercise 1 — Identifying Reifiable Types

Among `List<?>`, `List<String>`, `String[]`, `Map<?, ?>`, and `List<? extends Number>`, which types are reifiable?

**Answer:** `List<?>`, `String[]`, and `Map<?, ?>`. `List<String>` and `List<? extends Number>` are not reifiable because their type arguments are not all unbounded wildcards.

### Exercise 2 — Predicting Compilation

~~~java
Object a = new ArrayList<String>();
List<String> b = new ArrayList<>();

boolean ok1 = a instanceof List<?> items;
boolean ok2 = a instanceof List<String> words;
boolean ok3 = b instanceof ArrayList<String> array;
~~~

Assume `java.util.List` and `java.util.ArrayList` have been imported. Which statement is rejected in Java 17?

**Answer:** `ok2` is rejected because `a` only has static type `Object`, which has no valid checked cast to `List<String>`. `ok1` is valid because `List<?>` is reifiable; `ok3` is valid because of the static type `List<String>` of `b`. This is a Java snippet that needs to be placed inside a method or block.

### Exercise 3 — Proving Runtime Does Not Check Elements

If a list has `42` added via a raw type and is then assigned back to a `List<String>` variable, why can `instanceof ArrayList<String>` return `true` while `String s = list.get(0)` throws `ClassCastException`?

**Answer:** The pattern checks the runtime class `ArrayList` on a conversion permitted by the compiler based on static types. Only when reading the element into `String` does the runtime cast see that the actual value is `Integer`.

### Exercise 4 — Generic Records

Given `record Box<T>(T payload) {}`, determine the type of `item` in both cases:

~~~java
// Java 21+, placed inside appropriate methods:
Box<String> known = new Box<>("hi");
Object unknown = new Box<>("hi");

if (known instanceof Box(var item)) {
    System.out.println(item.toUpperCase());
}

if (unknown instanceof Box(var item)) {
    System.out.println(item);
}
~~~

**Answer:** In the first branch, `item` has static type `String`. In the second branch, `item` has static type `Object`. Both may hold the same runtime value `"hi"`, but the range of methods allowed to be called differs due to compile-time information.

### Exercise 5 — Safe API Design

You receive `Object rawInput` that may contain a `List` of `String`s, integers, or other objects. You need to extract the strings and convert them to uppercase. Would you use `instanceof List<String>` or `List<?>`?

**Answer:** Use `rawInput instanceof List<?> items`, then iterate over each `Object element`, apply `element instanceof String text`, and call `text.toUpperCase()` on matching elements. This avoids requiring an impossible generic check and is explicit about skipping or handling elements of other types.

## 15. Guiding Principles

**Type erasure retains enough information to identify runtime classes/interfaces, but generally does not retain the type arguments of a generic instance.** Therefore:

- Pattern matching **does not solve** the limitations of erasure on its own.
- `List<?>` answers the question "is this a List?".
- `List<String>` is a strong compile-time constraint; from an arbitrary `Object`, it cannot be fully verified with a single pattern.
- Some parameterized patterns like `ArrayList<String>` are still valid thanks to **static type** information on the expression side; they do not run element-by-element checks.
- When you need to guarantee the inner data types, you must validate the components or accept appropriate runtime type information (such as `Class<T>` for the element class).

### Specification Sources

- JLS Java SE 21 `4.6 — Type Erasure: https://docs.oracle.com/javase/specs/jls/se21/html/jls-4.html#jls-4.6
- JLS Java SE 21 `4.7 — Reifiable Types: https://docs.oracle.com/javase/specs/jls/se21/html/jls-4.html#jls-4.7
- JLS Java SE 21 `15.20.2 — The instanceof Operator: https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.20.2
- Oracle Java 21 — Record Patterns, Generic Records: https://docs.oracle.com/en/java/javase/21/language/record-patterns.html

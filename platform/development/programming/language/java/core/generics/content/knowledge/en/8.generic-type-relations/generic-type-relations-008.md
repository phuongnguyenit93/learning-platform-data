# Separating Subtyping from Casts and Unchecked Conversions in Java Generics

## 1. Why Must These Three Concepts Be Distinguished?

When reading generics code, it is very easy to mistakenly conclude that "can be assigned" or "can be cast" means "is a subtype." Java uses **three mechanisms with distinct meanings**:

1. **Subtyping:** a relationship between *types* defined by the type system, commonly denoted `S <: T` ("`S` is a subtype of `T`"). This relationship allows an expression of type `S` to be used where `T` is accepted.
2. **Cast:** explicit syntax `(T) expression` requesting that the expression's value be viewed as type `T`. A cast can be syntactically valid yet fail at runtime; being able to cast **does not prove** `S <: T`.
3. **Unchecked conversion:** Java permits certain conversions from a **raw type** to a **parameterized type** without being able to fully verify the type arguments. The conversion can occur implicitly in an assignment or method call and typically emits an `[unchecked]` warning.

There is also an **unchecked cast**: an *explicit* cast to a parameterized type whose type arguments cannot be fully checked at runtime. "Unchecked conversion" and "unchecked cast" are related, yet **they are not the same operation**.

The goal is to look at a line of Java and answer accurately: is it relying on subtyping, requesting a runtime-checked cast, or accepting an operation that cannot be fully verified?

## 2. Concept Map

| Example | Primary classification | Compiler handling | What can runtime verify? |
| --- | --- | --- | --- |
| `String text = "Java"; Object x = text;` | Subtyping `String <: Object` and widening reference conversion | Valid, no unchecked warning | No downcast check needed. |
| `List<String> a = new ArrayList<>(); Collection<String> b = a;` | Subtyping `List<String> <: Collection<String>` | Valid, no unchecked warning | Reference stays unchanged. |
| `List<Integer> a = List.of(1); List<? extends Number> b = a;` | Subtyping via wildcard/type-argument containment | Valid, no unchecked warning | No runtime check of type arguments needed. |
| `Object x = "Java"; String s = (String) x;` | Checked reference cast | Valid | Checks that the object is actually a `String`. |
| `List raw = new ArrayList<Integer>(); List<String> b = raw;` | Unchecked conversion (implicit assignment) | Unchecked conversion warning | Does not verify elements are `String`. |
| `Object x = List.of(1); List<String> b = (List<String>) x;` | Unchecked cast (explicit cast) | Unchecked cast warning | Can check the object is a `List`, yet cannot check `String` in `List<String>`. |

**Do not equate "has a conversion" with "is a subtype."** Variable assignment can be accepted via widening conversion or, in the special case of generics with raw types, unchecked conversion. A casting context allows additional conversions that require an explicit cast. Subtyping itself does not change because a cast syntax appears.

## 3. Subtyping with Generic Types: Invariance

In Java, `Integer <: Number`, yet **`List<Integer>` is not a subtype of `List<Number>`**. This is the invariance of concrete type arguments in a generic type like `List<E>`.

Illustrative example that **does not compile**:

~~~java
List<Integer> integers = new ArrayList<>();
List<Number> numbers = integers; // Compile ERROR: incompatible types
~~~

Why must this be forbidden? If assignable, a user of the `numbers` variable could call `numbers.add(3.14)` (a `Double`) and inadvertently insert a `Double` into a list originally declared as `List<Integer>`. The type system prevents that at compile time.

### 3.1. Two Valid Subtyping Paths Often Overlooked

**First, inheritance relationships of the *generic declaration* are preserved when type arguments match:**

~~~java
ArrayList<String> arrayList = new ArrayList<>();
List<String> list = arrayList;
Collection<String> collection = list;
Iterable<String> iterable = collection;
~~~

`ArrayList<String> <: List<String> <: Collection<String> <: Iterable<String>` are valid relationships. There are no unchecked warnings and no data copying.

**Second, wildcards create a more abstract target type:**

~~~java
List<Integer> integers = List.of(10, 20);
List<? extends Number> numericView = integers;
List<?> unknownView = integers;

Number first = numericView.get(0);
Object another = unknownView.get(1);
~~~

`List<Integer>` can be viewed as `List<? extends Number>` and `List<?>` under the JLS type-argument containment rules. This is a safe conversion grounded in the type system, not an unchecked conversion.

- `List<? extends Number>`: each element can be read as `Number`, yet you cannot arbitrarily `add(Integer)` or `add(Double)` because the concrete element type could be another subtype of `Number`.
- `List<? super Integer>`: can `add(Integer)`; when reading, only `Object` is guaranteed.
- `List<?>`: can be read as `Object`; cannot add a value other than `null` when the element type is unknown.

This is the principle commonly called **PECS**: producer → `extends`, consumer → `super`. PECS helps describe APIs without unsafe casts.

### 3.2. Need an Actual `Number` List? Create a Properly Typed Copy

~~~java
List<Integer> integers = List.of(10, 20);
List<Number> numbers = new ArrayList<>(integers);
numbers.add(2.5); // Valid: numbers is a separate list holding Number
~~~

The constructor `ArrayList(Collection<? extends E>)` accepts a collection containing elements of a subtype of `E`. This snippet **creates a new list**; it never turns the original `List<Integer>` into a subtype of `List<Number>`.

## 4. Checked Casts: Syntactic Validity Does Not Mean Runtime Safety

Example:

~~~java
Object value = "Java";
String text = (String) value; // Cast succeeds

Object another = Integer.valueOf(42);
String wrong = (String) another; // ClassCastException on this line
~~~

For a cast from `Object` to a non-parameterized type like `String`, the JVM checks the actual object type. The compiler accepts both cast syntaxes; success or failure depends on the value at runtime.

Points to remember:

- A cast does not create a new object and does not convert an `Integer` into a `String`; it merely requires the reference to satisfy the target type.
- `(String) value` is a checked reference cast. When the object does not match, runtime throws `ClassCastException`.
- Casting `null` to a valid reference type yields `null` and does not throw `ClassCastException` at the cast step; dereferencing it later can still throw `NullPointerException`.
- Not every cast is permitted by the compiler. For instance, converting between two clearly incompatible types can be flagged as an error right at compile time.

**Therefore, "the compiler allows casting `(T) x`" does not establish a `type(x) <: T` relationship.**

## 5. Unchecked Conversion: Implicit Conversion from a Raw Type

A **raw type** is the use of a generic name without supplying type arguments, such as `List` instead of `List<String>`. Java supports raw types for compatibility with older programs/libraries, yet this loses element type information.

~~~java
List<Integer> integers = new ArrayList<>(List.of(10));
List raw = integers;             // Loses type argument information in the raw expression.
List<String> strings = raw;      // UNCHECKED CONVERSION, no cast syntax needed.
~~~

Running `javac -Xlint:unchecked` will point out an **unchecked conversion** on the last assignment. The compiler cannot prove `raw` contains only `String`, yet allows the assignment to support legacy code.

The line `List raw = integers;` does not require an unchecked conversion: parameterizations of `List` can be used as raw `List`. The danger arises when treating raw `List` as `List<String>`, or when writing/reading elements through a raw API.

Method calls can also trigger an unchecked conversion if a raw argument is passed to the corresponding generic parameter:

~~~java
static void printStrings(List<String> items) {
    for (String item : items) {
        System.out.println(item);
    }
}

// At the call site:
List raw = List.of(1, 2);
printStrings(raw); // Unchecked conversion warning; may fail when using elements.
~~~

The second snippet only illustrates a call, not a standalone program. You should not "fix" an unchecked warning by dropping type arguments altogether or using raw types across the entire system.

## 6. Unchecked Cast: Has the `(T)` Operator Yet Cannot Fully Check Generic Arguments

Example:

~~~java
Object value = List.of(10, 20);
List<String> strings = (List<String>) value; // UNCHECKED CAST
~~~

`value` is holding a `List<Integer>`. After type erasure, the runtime knows this is an implementation of `List`, yet **has no runtime evidence to confirm the elements are `String`**. Therefore, the cast can pass the runtime check for `List`, while `ClassCastException` occurs when reading an element as `String`.

The following two lines **differ in syntax and warning kind**:

~~~java
List raw = List.of(1, 2);
List<String> viaConversion = raw;                 // Unchecked conversion
List<String> viaCast = (List<String>) (Object) raw; // Unchecked cast
~~~

A cast does not "sanitize" data or prove a new subtyping relationship. It can make bugs harder to spot because execution continues until the moment an incompatible element is read or written.

### 6.1. Type Erasure and Reifiable Types

In Java generics, type arguments like `String` or `Integer` are generally erased in the runtime representation of generic classes. The two objects `new ArrayList<String>()` and `new ArrayList<Integer>()` both have runtime class `ArrayList`.

~~~java
Object unknown = List.of("a", "b");

boolean isList = unknown instanceof List<?>; // Valid.
List<?> view = (List<?>) unknown;             // Can check List at runtime.
~~~

Conversely, the following syntax is **invalid**:

~~~java
// INVALID: List<String> is not a reifiable type usable with instanceof.
if (unknown instanceof List<String>) {
    System.out.println("strings");
}
~~~

`List<?>` is reifiable according to the JLS, because it uses only an unbounded wildcard; that **does not** guarantee all elements belong to any specific type. If you need a real `List<String>`, check each element or construct the collection safely from an already-typed source.

### 6.2. Heap Pollution: Cause and Timing of Failure

**Heap pollution** occurs when a variable declared with a parameterized type refers to actual data that does not match that type. It can be introduced via raw types, unchecked conversions/casts, certain array operations with generic varargs, or other unsafe mechanisms.

~~~java
List<Integer> integers = new ArrayList<>(List.of(10));
List raw = integers;
List<String> strings = raw; // Unchecked warning; heap pollution risk already present.
String first = strings.get(0); // ClassCastException when using Integer as String.
~~~

The compiler inserts the necessary check/cast where the result of `get(0)` is used to satisfy `String`. Failing here does not mean `List<Integer>` was ever a subtype of `List<String>`. Rather, the unchecked conversion **bypassed part of the static guarantee** and pushed the error to runtime.

An unchecked warning does not guarantee a failure will occur; if the raw data happens to contain the expected values, the program may run. Yet the compiler cannot prove that from the declared types.

## 7. Compilable and Runnable Java 17+ Example

Create the file **GenericRelationsDemo.java** with the following contents:

~~~java
import java.util.ArrayList;
import java.util.List;

public class GenericRelationsDemo {
    public static void main(String[] args) {
        List<Integer> integers = new ArrayList<>(List.of(10, 20));
        List<? extends Number> readable = integers;
        List<?> anything = integers;
        System.out.println("subtype: " + readable.get(0));
        System.out.println("unknown: " + anything.get(1));

        List<Number> copied = new ArrayList<>(integers);
        copied.add(2.5);
        System.out.println("copy: " + copied);

        Object value = "Java";
        String text = (String) value;
        System.out.println("checked cast: " + text);

        try {
            String bad = (String) (Object) 42;
            System.out.println(bad);
        } catch (ClassCastException e) {
            System.out.println("checked cast: failed");
        }

        List raw = integers;
        List<String> assumedStrings = raw;
        try {
            System.out.println(assumedStrings.get(0).length());
        } catch (ClassCastException e) {
            System.out.println("unchecked conversion: failed on element read");
        }

        Object unknown = new ArrayList<>(List.of(1, 2));
        List<String> claimedStrings = (List<String>) unknown;
        try {
            System.out.println(claimedStrings.get(0).length());
        } catch (ClassCastException e) {
            System.out.println("unchecked cast: failed on element read");
        }
        System.out.println("reifiable test: " + (unknown instanceof List<?>));
    }
}
~~~

Compile and run:

~~~bash
javac --release 17 -Xlint:unchecked GenericRelationsDemo.java
java GenericRelationsDemo
~~~

The `javac` command **succeeds** yet prints two warnings to stderr:

- `unchecked conversion` at `List<String> assumedStrings = raw;`.
- `unchecked cast` at `List<String> claimedStrings = (List<String>) unknown;`.

Ignoring path/filename locations in stderr, these two warnings have different content. The program still runs and prints **exact** stdout:

~~~text
subtype: 10
unknown: 20
copy: [10, 20, 2.5]
checked cast: Java
checked cast: failed
unchecked conversion: failed on element read
unchecked cast: failed on element read
reifiable test: true
~~~

Explanation of key points: the two assignments to wildcards are safely accepted by the type system; the `List<Number>` copy can receive `Double`; the cast from `Object` to `String` is checked; the two unsafe generic operations do not fail right when assigning/casting to `List<String>`, but fail when runtime has to use an `Integer` element as `String`.

## 8. Designing APIs to Avoid Unchecked Conversions and Unchecked Casts

### 8.1. Expressing Exact Requirements with Wildcards

If only reading numbers, use `List<? extends Number>` instead of `List<Number>`:

~~~java
static double sum(List<? extends Number> values) {
    double result = 0.0;
    for (Number value : values) {
        result += value.doubleValue();
    }
    return result;
}

// sum(List.of(1, 2, 3)) is valid with List<Integer>.
~~~

If adding integers into a container, use `List<? super Integer>`:

~~~java
static void addDefaults(List<? super Integer> target) {
    target.add(10);
    target.add(20);
}
~~~

You can pass `List<Integer>`, `List<Number>`, or `List<Object>` to `addDefaults`. This is a valid type relationship requiring no unchecked cast.

### 8.2. Need to Validate Data of Unknown Type? Check Every Element

~~~java
static List<String> requireStrings(List<?> source) {
    List<String> copy = new ArrayList<>();
    for (Object element : source) {
        copy.add(String.class.cast(element));
    }
    return copy;
}
~~~

This is an example of a *member method* (must be placed in a class with `List` and `ArrayList` imported to run standalone). `String.class.cast(element)` checks each actual element. If all are valid, the result is a separate `List<String>` without needing an unchecked cast. If a non-`String` element is encountered, the error occurs immediately at the validation site, making it easier to diagnose.

In real applications, you can decide to reject invalid data, collect a list of errors, or convert types intentionally; yet you must properly call it **data validation/conversion**, not a "safe generic cast" over the whole collection.

### 8.3. When Forced to Interact with Legacy/Raw APIs

If a source provides only a raw `List`, try to update the API signature to be generic or create an adapter that validates the data. When you already have an invariant guarantee from an external system and must use an unchecked cast, `@SuppressWarnings("unchecked")` should be placed on the smallest possible scope with a comment explaining why the cast is safe.

`@SuppressWarnings("unchecked")` only **suppresses the warning**; it adds no runtime check, does not turn a raw type into a parameterized subtype, and does not prevent `ClassCastException`.

## 9. Common Wrong Conclusions

| Wrong conclusion | Correct reality |
| --- | --- |
| "`Integer extends Number` so `List<Integer> extends List<Number>`." | Concrete generic type arguments are invariant; use wildcards or create a properly typed copy. |
| "If you can cast, it must be a subtype." | A cast context permits narrowing conversions; the actual runtime type may not match and throw `ClassCastException`. |
| "Casting `List<Integer>` to `List<String>` converts element types." | No element transformation occurs; erasure prevents full verification of type arguments. |
| "Only explicit casts produce `unchecked`." | Assigning a raw `List` to `List<String>` is also an unchecked conversion. |
| "`instanceof List<?>` proves this is a `List<String>`." | It only proves the object is an implementation of `List`, not its element type. |
| "If it compiles, declared runtime types are always right." | Unchecked conversions can lead to heap pollution; errors may surface later when using elements. |
| "Just using `@SuppressWarnings` eliminates the risk." | The annotation does not alter type system rules or runtime behavior. |

## 10. Diagnostic Workflow When Encountering Generic Type Errors

1. **Write down the exact source and target types** of the expression. Distinguish `List<Integer>`, `List<Number>`, `List<?>`, and raw `List`.
2. **Ask whether subtyping holds** via inheritance and wildcard containment; do not infer it directly from subtyping of type arguments.
3. **If `(TargetType) expr` is present**, recognize it as an explicit cast, check whether the target is reifiable, and check whether there is an unchecked warning.
4. **If there is no cast yet `[unchecked]` appears**, look for a raw type in an assignment, method argument, or legacy library interaction.
5. **Distinguish error timing:** compile-time `incompatible types`; compile-time warning `unchecked`; runtime `ClassCastException` or another error when using the value.
6. **Adjust the API's type model** (wildcards/generic type parameters, copying, validation) before choosing to cast/suppress warnings.

### Self-Check

- Is `List<Integer>` a subtype of `List<? extends Number>`? **Yes.**
- Is `List<Integer>` a subtype of `List<Number>`? **No.**
- Is `Object obj; String s = (String) obj;` an unchecked cast? **No**, it is a runtime-checked cast.
- Does `List raw; List<String> strings = raw;` need a cast operator to emit a warning? **No**, it is an implicit unchecked conversion.
- Does `Object obj; List<String> xs = (List<String>) obj;` guarantee the elements are `String`? **No**, because the cast does not verify type arguments at runtime.

## 11. Authoritative References

- [JLS Java SE 17 §4.10.2 — Subtyping among Class and Interface Types](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.10.2): subtyping for parameterized and wildcard types.
- [JLS Java SE 17 §4.5.1 — Type Arguments of Parameterized Types](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.5.1): wildcards, containment, and upper/lower bounds.
- [JLS Java SE 17 §4.6–§4.8 — Type Erasure, Reifiable Types, Raw Types](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.6): background on runtime checking limits.
- [JLS Java SE 17 §4.12.2 — Heap Pollution](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.12.2): parameterized variables referencing incompatible data.
- [JLS Java SE 17 §5.1.6 — Narrowing Reference Conversion](https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html#jls-5.1.6): runtime checks, checked and unchecked narrowing.
- [JLS Java SE 17 §5.1.9 — Unchecked Conversion](https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html#jls-5.1.9): converting from a raw type to a parameterized type.
- [JLS Java SE 17 §5.5 — Casting Contexts](https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html#jls-5.5): contexts where casts apply.
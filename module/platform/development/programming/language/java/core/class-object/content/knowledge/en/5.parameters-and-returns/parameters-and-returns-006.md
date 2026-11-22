# Varargs Position Restrictions and Confusing Calls in Java

**Varargs** (*variable-length arguments*) allows a method or constructor to accept a **flexible number of arguments** at the **last parameter position**. In Java, varargs is declared using three dots `...` after the element type:

```java
static int sum(int... numbers) {
    int total = 0;
    for (int number : numbers) {
        total += number;
    }
    return total;
}
```

All of the following calls are valid:

```java
sum();                 // No numbers
sum(2);                // One number
sum(2, 3, 5);          // Three numbers
sum(new int[]{2, 3}); // Pass an int[] array directly
```

Even though a call can contain multiple values, in the declaration `sum(int... numbers)` there is only **one formal parameter `numbers`**. Inside the method, that parameter has the **array type `int[]`**.

The three most important points:

1. **Varargs must be the last parameter** in the formal parameter list, and only **one varargs parameter** can be declared.
2. Varargs can accept **0, 1, or more element argument expressions**, or accept **a compatible array**. The two ways of calling can lead to different ways of organizing arguments.
3. When **overloading** is present, a call containing `null`, an array, or overloads with closely related types can produce unpredictable results or compilation errors due to ambiguity.

This article analyzes valid/invalid syntax, the array mechanism, overload rules, `null` cases, object arrays, generic varargs, common pitfalls, and how to write easy-to-use APIs in Java 17 and later.

## 1. Varargs Syntax and Position Restrictions

Declaration syntax:

```java
returnType methodName(Type... parameterName) {
    // parameterName is used as a Type[] array
}
```

This is a **syntax pattern**, not a standalone Java program. The `...` goes **after the type name and before the parameter name**, and is special declaration syntax.

Valid examples:

```java
static void printAll(String... messages) {
    for (String message : messages) {
        System.out.println(message);
    }
}

static void log(String category, int level, Object... values) {
    System.out.println(category + ":" + level + ":" + values.length);
}
```

In `log(String category, int level, Object... values)`, the first two parameters `category` and `level` must appear first; `values` comes last and can accept an arbitrary number of elements.

### 1.1. Invalid Declarations

```java
// WRONG: regular parameter comes after varargs
static void wrong1(String... messages, int count) { }

// WRONG: two varargs parameters in one declaration
static void wrong2(int... numbers, String... labels) { }

// WRONG: ... is not placed after the parameter's data type
static void wrong3(...String messages) { }
```

These lines intentionally illustrate syntax errors; **they do not compile as a runnable program**.

| Declaration | Result | Reason |
| --- | --- | --- |
| `void a(int... numbers)` | Valid | Varargs is at the end and is the only parameter |
| `void b(String title, int... scores)` | Valid | Varargs comes after the required parameter |
| `void c(int[] values)` | Valid | Regular array parameter, without `...` |
| `void d(int... values, String title)` | Invalid | Varargs is not at the end |
| `void e(int... left, int... right)` | Invalid | Cannot have two varargs; the first parameter is also not at the end |
| `void f(String title, Object... args)` | Valid | One varargs at the end |
| `void g(Object... args, String title)` | Invalid | Wrong varargs position |

**If you need multiple variable-length data groups**, pass separate arrays or collections instead of trying to declare multiple varargs:

```java
static void combine(int[] left, int[] right) {
    System.out.println(left.length + right.length);
}
```

For an API that needs required information after multiple values, **reorder the parameters** so varargs comes last, or design a parameter object.

### 1.2. Varargs Does Not Apply to Local Variables/Fields

In Java 17, the `...` syntax is used on the **final varargs parameter** of a method or constructor. Do not use `int... values;` as an ordinary local array declaration:

```java
int[] values = {1, 2, 3}; // Valid
// int... values;          // WRONG when declaring a local variable
```

Inside the body of a varargs method, the parameter is still used as an array; `...` is not a "spread" operator in a call expression.

## 2. Array Mechanism: How Are `int...` and `int[]` Related?

Consider:

```java
static int sum(int... numbers) {
    int total = 0;
    for (int number : numbers) {
        total += number;
    }
    return total;
}
```

Inside `sum`, `numbers` is a parameter variable of **type `int[]`**:

- `numbers.length` returns the number of elements in the array.
- `numbers[0]` reads the first element if the array has at least one element.
- A `for-each` loop iterates over the elements of the array.
- An array can be passed directly in a matching call.

In a **variable arity** call such as `sum(2, 3, 5)`, Java collects the three values into a new `int[]` array to pass to the parameter. In the call `sum(new int[]{2, 3})`, the argument expression is **a compatible `int[]` array**, so that array can be passed **directly**, without creating an additional array containing its elements.

**Note:** Saying "a varargs method takes 3 parameters" when calling `sum(2, 3, 5)` is inaccurate if you are counting **formal parameters**. The declaration has only one formal parameter `numbers`; the call has three argument expressions.

### 2.1. Cannot Overload `int...` and `int[]` with the Same Name

The following two declarations **have a signature conflict** when placed in the same class:

```java
// WRONG: cannot place both in the same class
static void show(int... values) { }
static void show(int[] values) { }
```

A varargs parameter `int...` is represented as an **`int[]` array** in the method signature. The two declarations above do not form two distinct overloads.

If an API needs a way to accept an array and a way to accept individual values, **a single `int...` method is enough**:

```java
static void show(int... values) {
    System.out.println(values.length);
}

// Valid calls within a method:
show(1, 2);              // Two elements
show(new int[]{1, 2});   // One array argument with two elements
```

### 2.2. A Directly Passed Array Can Be Modified

Java passes arguments **by value**: a varargs method receives a copy of the reference value to the array. If the caller supplies an existing array, modifying array elements inside the method can affect the caller's array.

Complete example in the file **`VarargsArrayDemo.java`**:

```java
import java.util.Arrays;

public class VarargsArrayDemo {
    static void increaseFirst(int... values) {
        if (values.length > 0) {
            values[0]++;
        }
    }

    public static void main(String[] args) {
        int[] existing = {2, 4};

        increaseFirst(existing);
        System.out.println(Arrays.toString(existing));

        increaseFirst(7, 8); // A varargs array is created for this call
        System.out.println(Arrays.toString(existing));

        System.out.println(existing.length);
    }
}
```

Compile/run with JDK 17+:

```bash
javac -encoding UTF-8 VarargsArrayDemo.java
java VarargsArrayDemo
```

Stdout:

```text
[3, 4]
[3, 4]
2
```

In the first call, `values` and `existing` refer to the same array, so `values[0]++` changes `existing[0]` from `2` to `3`. In the call `increaseFirst(7, 8)`, the method receives a varargs array created separately from the two values; the increment does not touch the `existing` array.

**Safe design:** If a method can modify input data, clearly describe that behavior. To avoid affecting the caller's array, you can create a copy using `values.clone()` before modifying it.

## 3. Zero Arguments, One Argument, and Multiple Arguments

Consider the method:

```java
static String describe(String label, int... values) {
    return label + "=" + values.length;
}
```

Valid calls:

```java
describe("none");                // values is an empty array, length = 0
describe("one", 9);              // values has 1 element
describe("three", 1, 2, 3);      // values has 3 elements
describe("array", new int[]{4, 5}); // values has 2 elements
```

**Required parameters remain required**. `describe()` is invalid because it is missing the `label` parameter, even though `values` can be empty.

A statement such as `describe("one", 9)` contains **two arguments** (the label and the value `9`), but the declaration also has exactly **two formal parameters** (`label` and `values`). This does not mean the `values` parameter has type `int`: in the method body, it is still an **`int[]` of length 1**.

In the call `describe("three", 1, 2, 3)`, there are **four argument expressions** yet still only **two formal parameters**.

You can also explicitly pass an empty array:

```java
describe("none", new int[0]);
```

Here `values.length == 0`, just like a call that passes no numbers, but the origin of the array from the caller is different. This can matter if the method modifies or retains the input array.

## 4. `null`: A `null` Array Differs from a Single `null` Element

With **reference-type** varargs, `null` is the most common source of confusion.

Consider:

```java
static void inspect(String... words) {
    if (words == null) {
        System.out.println("Mảng null");
    } else {
        System.out.println("Số phần tử: " + words.length);
    }
}
```

The following calls are **not equivalent**:

| Call | Meaning | `inspect` Result |
| --- | --- | --- |
| `inspect()` | No elements passed | `Số phần tử: 0` |
| `inspect("A")` | One element `"A"` | `Số phần tử: 1` |
| `inspect(new String[0])` | Pass an empty array | `Số phần tử: 0` |
| `inspect((String[]) null)` | Pass a **null array reference** | `Mảng null` |
| `inspect((String) null)` | Pass **a single null String element** | `Số phần tử: 1` |
| `inspect(null)` | By default matches a **single null `String[]` array argument** call in this example; `javac` may issue a warning | `Mảng null` |

### 4.1. Illustrative Java 17 Program

Save as **`NullVarargsDemo.java`**:

```java
import java.util.Arrays;

public class NullVarargsDemo {
    static void inspect(String... words) {
        if (words == null) {
            System.out.println("Mảng null");
        } else {
            System.out.println(words.length + ": " + Arrays.toString(words));
        }
    }

    public static void main(String[] args) {
        inspect();
        inspect("A", "B");
        inspect((String[]) null);
        inspect((String) null);
        inspect(new String[]{null, "C"});
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 NullVarargsDemo.java
java NullVarargsDemo
```

**Stdout:**

```text
0: []
2: [A, B]
Mảng null
1: [null]
2: [null, C]
```

Here explicit casts are used so it **does not depend on the reader guessing** the meaning of the `null` literal:

- `(String[]) null` has type `String[]`, meaning the passed array itself is `null`.
- `(String) null` has type `String`, so Java constructs a varargs array containing **one null element**.
- `new String[]{null, "C"}` passes an array with exactly two elements, where the first element is `null`.

**Mistake causing a runtime error:** assuming `words` is always non-`null` and then accessing `words.length`. When the caller passes `(String[]) null`, reading `length` throws a `NullPointerException`. If an API wants to forbid `null` arrays, check early and throw a meaningful error, or specify in the documentation that `null` is not accepted.

### 4.2. Why Is `inspect(null)` Confusing?

With the **single overload** `inspect(String... words)`, the formal parameter is of array form `String[]`. The expression `null` can match `String[]` as a fixed-arity call, so the effect is typically a **null array**, not "a single null element". `javac` may emit a warning:

```text
non-varargs call for last parameter of varargs method
```

The exact message may vary depending on the JDK version. Clear ways to express intent:

```java
inspect((String[]) null); // Intentionally pass a null array
inspect((String) null);   // Intentionally pass a single null element
```

Use `inspect()` if you want an empty list; do not use `inspect(null)` to represent "no arguments".

### 4.3. Primitive Varargs and `null`

With `int... numbers`, a `null` argument can serve as a **null `int[]` array reference**, but **there cannot be an `int` element with a null value**:

```java
static void count(int... numbers) {
    System.out.println(numbers == null ? "null array" : numbers.length);
}

count((int[]) null);       // Valid: null int[] array
// count((int) null);      // WRONG: cannot cast null to primitive int
```

A wrapper type such as `Integer...` allows `Integer` elements to be `null`, but auto-unboxing to `int` carries the risk of a `NullPointerException`.

## 5. Overloading: Varargs Is Considered After Better-Matching Calls

**Overloading** allows multiple methods with the same name but different parameter lists. Java performs overload resolution in phases, with the general priority:

1. Methods applicable **without boxing/unboxing and without variable arity**.
2. If none is found yet, methods applicable with **boxing/unboxing**, still without variable arity.
3. If the previous two phases find no applicable method, **variable-arity calls (expanded varargs)** are considered.

Within each phase, Java also applies the rule of selecting the **most specific** method; if a single method still cannot be chosen, the call can be ambiguous.

This means a varargs method **is not always chosen** just because a call has arguments of a matching type: a fixed-arity method can win.

### 5.1. Example of Fixed and Varargs Overloads

Save as **`OverloadVarargsDemo.java`**:

```java
public class OverloadVarargsDemo {
    static void select(int value) {
        System.out.println("Một int: " + value);
    }

    static void select(int... values) {
        System.out.println("Varargs: " + values.length);
    }

    public static void main(String[] args) {
        select(5);
        select();
        select(1, 2);
        select(new int[]{7, 8, 9});
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 OverloadVarargsDemo.java
java OverloadVarargsDemo
```

**Stdout:**

```text
Một int: 5
Varargs: 0
Varargs: 2
Varargs: 3
```

Explanation:

- `select(5)` matches `select(int)` via a fixed-arity call, so the fixed overload is selected.
- `select()` cannot call `select(int)` because an argument is missing; the varargs method accepts an empty array.
- `select(1, 2)` does not match the single-`int` overload; the varargs overload receives two values.
- `select(new int[]{7, 8, 9})` passes **an `int[]` array** to the `select(int...)` overload; inside, `values.length == 3`.

**Subtle point:** in the last call, the varargs method is selected **in fixed-arity call form** because an array expression matches the `int[]` parameter. A method declared with `...` can be invoked in both **fixed-arity** form (passing an array) and **variable-arity** form (passing elements).

### 5.2. An Overload Taking a Wrapper Can Beat a Varargs Call

```java
static void choose(Integer value) {
    System.out.println("Integer");
}

static void choose(int... values) {
    System.out.println("int varargs");
}
```

In the context of the two overloads above, `choose(3)` selects `choose(Integer)` via **boxing in the fixed-arity phase**, instead of using variable arity to pack `3` into `int[]`. This declaration snippet can be tested inside its own class.

Key takeaway: overload resolution order is not simply "the primitive type `int` always prioritizes every method related to `int`". You must distinguish between **the parameter type in a fixed-arity call** and **the element type when expanding varargs**.

### 5.3. Varargs Overloads Can Be Ambiguous

Consider:

```java
static void process(String... values) {
    System.out.println("String");
}

static void process(Integer... values) {
    System.out.println("Integer");
}
```

The call `process()` is **ambiguous**, because there are no arguments to distinguish them, so both varargs overloads are applicable and neither is more specific according to the method selection rules.

The call `process(null)` is also **ambiguous** between the two array parameter types `String[]` and `Integer[]`, which have no subtype relationship.

Ways to write with explicit types:

```java
process(new String[0]);     // Selects the String... version
process(new Integer[0]);    // Selects the Integer... version
process((String[]) null);   // Selects String..., null array
process((Integer) null);    // Selects Integer..., one null element
```

This is an **illustrative snippet** to place inside a class containing the two `process` declarations above. Do not try adding `process()` or `process(null)` calls to code meant to compile: they will cause ambiguity errors.

### 5.4. Avoid Multiple Similar Varargs Overloads

An API set with overloads such as `send(String...)`, `send(Object...)`, and `send(String, Object...)` can become very hard to read on empty calls, `null`, or arguments with common types. When a public API becomes ambiguous:

- Name methods to express distinct behaviors.
- Keep the number of overloads as small as possible.
- Design explicit argument types or require passing a collection/array if that is the API's actual data.
- Use explicit casts when needed to clarify a specific call, rather than relying on scattered casts to rescue a frequently confusing API design.

## 6. An Array Argument Can Be *One Element* or *the Entire List*

This is a very confusing case when varargs has a broad element type such as `Object`.

Consider:

```java
static void inspect(Object... values) {
    System.out.println(values.length);
}
```

For a `String[]`, Java can treat the array as **an array compatible with `Object[]`** (because Java reference arrays are covariant). Therefore:

```java
inspect(new String[]{"A", "B"});          // Has 2 elements, passed as Object[]
inspect((Object) new String[]{"A", "B"}); // Has 1 element: that element is String[]
```

In the first call, `String[]` can be converted to `Object[]`, so **the array is passed as the varargs array itself**, without automatically wrapping it into a single `Object` element. `javac` may warn that the call does not use the varargs mechanism in the way many people expect.

In the second call, the `(Object)` cast gives the expression the type `Object`, so Java creates a new `Object[]` array containing one element, which is the `String[]` object.

A primitive array such as `int[]` is different: `int[]` is an `Object`, but **is not an `Object[]`**. Therefore:

```java
inspect(new int[]{1, 2}); // One Object element, which itself is an int[] array
```

### 6.1. Runnable Example to Distinguish Clearly

Save as **`ObjectVarargsDemo.java`**:

```java
import java.util.Arrays;

public class ObjectVarargsDemo {
    static void inspect(Object... values) {
        System.out.println(values.length + " => " + Arrays.deepToString(values));
    }

    public static void main(String[] args) {
        inspect("A", "B");
        inspect((Object[]) new String[]{"C", "D"});
        inspect((Object) new String[]{"E", "F"});
        inspect(new int[]{1, 2});
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 ObjectVarargsDemo.java
java ObjectVarargsDemo
```

**Stdout:**

```text
2 => [A, B]
2 => [C, D]
1 => [[E, F]]
1 => [[1, 2]]
```

Here the `(Object[])` and `(Object)` casts are used intentionally to indicate **a list of elements** versus **a single element that is an array**. `Arrays.deepToString` displays the contents of nested arrays, making the difference easy to observe.

**Do not equate an argument expression with a varargs element.** If the single expression is an array compatible with **the entire array parameter type**, it can serve as the array holding all elements; if the expression has element type `Object`, it is wrapped into a single element.

## 7. Generic Varargs and *Heap Pollution* Warnings

Varargs with an array type whose element type is **non-reifiable**, such as `List<String>...`, can trigger compiler warnings. The reasons are:

- Varargs is implemented using **arrays**.
- Java arrays perform runtime component type checking and are covariant for reference types.
- Generics normally undergo **type erasure**, so the runtime does not fully check `List<String>` and `List<Integer>` at the generic element level.
- When combined improperly, **heap pollution** can occur: a value has an actual type that does not match the type that generic code trusts it to have.

Intentionally **unsafe** example, for analysis only, **do not use**:

```java
import java.util.List;

class UnsafeExample {
    static void unsafe(List<String>... groups) {
        Object[] array = groups;
        array[0] = List.of(42);
        String first = groups[0].get(0);
        System.out.println(first);
    }
}
```

The declaration may compile with generic/varargs warnings; if `unsafe(List.of("A"))` is called, storing a `List<Integer>` into the array via the `Object[]` alias breaks the `List<String>` assumption, and then reading the value as a `String` risks a `ClassCastException`.

**Do not automatically add `@SafeVarargs` to suppress warnings** if the method might mutate the varargs array unsafely or expose the array elsewhere.

### 7.1. How to Use `@SafeVarargs` When Truly Safe

The `@SafeVarargs` annotation is a **developer's promise** that the implementation does not perform unsafe operations on the varargs parameter. In Java 17, this annotation is allowed on appropriate `static` methods, `final` methods, constructors, or `private` instance methods, because they cannot be overridden in a way that violates the promise.

An example that only **reads**, without modifying or exposing the array:

```java
import java.util.List;

public class SafeVarargsDemo {
    @SafeVarargs
    static <T> int countElements(List<T>... groups) {
        int total = 0;
        for (List<T> group : groups) {
            total += group.size();
        }
        return total;
    }

    public static void main(String[] args) {
        System.out.println(countElements(List.of("A"), List.of("B", "C")));
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 SafeVarargsDemo.java
java SafeVarargsDemo
```

Stdout:

```text
3
```

In the example, the body of `countElements` only reads the size of each list and does not expose the varargs array reference externally. This satisfies the `@SafeVarargs` commitment.

Another design approach to avoid generic array trouble is to **accept `List<List<T>>` or `Collection<? extends List<T>>`** depending on the API needs; then the caller passes an explicit collection without using generic varargs.

## 8. Constructors Also Have Varargs and the Same Position Restrictions

Constructors can declare a varargs parameter just like methods:

```java
class Team {
    private final String name;
    private final String[] members;

    Team(String name, String... members) {
        this.name = name;
        this.members = members.clone();
    }

    int memberCount() {
        return members.length;
    }
}
```

Valid calls:

```java
new Team("Empty");
new Team("Dev", "An");
new Team("Ops", "An", "Bình");
new Team("QA", new String[]{"Lan", "Minh"});
```

In the constructor `Team(String name, String... members)`, `members` is still the **last parameter**. The example class uses `members.clone()` to copy the array when storing it in the field, avoiding retaining the caller's mutable array directly; if the caller explicitly passes `(String[]) null`, this constructor will throw a `NullPointerException`, so a real API needs to decide and document whether `null` is accepted.

You cannot place a required `int level` parameter **after** `String... members` in the constructor declaration. If `level` is truly needed, place it before `members` or consider using an explicit configuration object.

## 9. Varargs in the `main` Method

Java 17 allows using varargs in the traditional `main` parameter:

```java
public static void main(String... args) {
    System.out.println(args.length);
}
```

`String... args` is equivalent to a `String[] args` parameter in its ability to receive the launcher's argument array. This is a **single formal parameter**; the words on the command line are converted by the launcher into elements of the `args` array.

Example file **`MainVarargsDemo.java`**:

```java
public class MainVarargsDemo {
    public static void main(String... args) {
        System.out.println("Count: " + args.length);
        for (String arg : args) {
            System.out.println(arg);
        }
    }
}
```

```bash
javac -encoding UTF-8 MainVarargsDemo.java
java MainVarargsDemo red blue
```

Stdout:

```text
Count: 2
red
blue
```

You cannot write both `main(String[] args)` and `main(String... args)` with the same name in one class to create an overload: their parameter signatures are equivalent, causing a duplicate definition error.

## 10. Common Invalid Calls

Based on the declaration:

```java
static void report(String title, int... scores) {
    System.out.println(title + ": " + scores.length);
}
```

Analysis of the calls:

| Call | Valid? | Explanation |
| --- | --- | --- |
| `report("A")` | Yes | Varargs receives 0 elements |
| `report("A", 10)` | Yes | One int element |
| `report("A", 10, 20)` | Yes | Two int elements |
| `report("A", new int[]{10, 20})` | Yes | Pass an int[] array |
| `report()` | No | Missing required parameter `title` |
| `report(10, "A")` | No | Wrong argument order and types |
| `report("A", new int[]{10, 20}, 30)` | No | Cannot mix "an `int[]` array" with a remaining `int` argument to form a single `int` varargs list |
| `report("A", (int[]) null)` | Yes, but dangerous | `scores` is null; reading `scores.length` causes `NullPointerException` |
| `report("A", (Integer) null)` | Unsafe / invalid in the example | A null `Integer` requires unboxing to `int` if the call is accepted, causing `NullPointerException` at runtime |
| `report("A", 2.5)` | No | Does not automatically narrow `double` to `int` |
| `report("A", "10")` | No | Does not automatically convert `String` to `int` |

**Regarding `report("A", (Integer) null)`:** if the call is selected as variable arity, Java can accept converting `Integer` to `int` via unboxing, and because the value is `null`, it throws a `NullPointerException` before entering the method body. This is a **runtime** error, not always a compile-time error; the key point is not to pass a null wrapper to a primitive parameter.

To add the value `30` to data from an existing array, create a new array (for example using `Arrays.copyOf` and then assigning the last element), or change the API to accept an appropriate collection. Java **does not support spread syntax** like `report("A", ...numbers)`.

## 11. Varargs and Generic APIs: Considering Clear Boundaries

Varargs is useful when the input data is **a small group of elements of the same type**, for example:

```java
static boolean containsAny(String source, String... fragments) {
    for (String fragment : fragments) {
        if (source.contains(fragment)) {
            return true;
        }
    }
    return false;
}
```

Calls read naturally:

```java
containsAny("Java Core", "Spring", "Java"); // true
containsAny("Java Core");                   // false
```

However, consider not using varargs when:

- The number of items is very large, and an array/collection already exists beforehand.
- You need to clearly distinguish between **no data** and **null data**.
- Elements have complex generic types and the risk of heap pollution makes maintenance difficult.
- There are multiple competing overloads, especially when an empty call or `null` is hard to resolve.
- There is a requirement to preserve object immutability or not retain a mutable parameter array.
- The parameters represent data **with different meanings**, even if they share the same type, such as `transfer(amount, accountId, fee)`. Clearly named parameters should be used instead.

With varargs, names like `values`, `items`, or `scores` should be plural to reflect that the variable inside the body is an array.

### Avoiding Null-Array Bugs with Early Checks

If the contract does not allow a `null` array:

```java
static int total(int... numbers) {
    java.util.Objects.requireNonNull(numbers, "numbers");
    int sum = 0;
    for (int value : numbers) {
        sum += value;
    }
    return sum;
}
```

When calling `total()`, Java creates an empty array; the method returns `0`. When calling `total((int[]) null)`, the call can compile, but `requireNonNull` throws a `NullPointerException` with a clearer message. If you want to reject **null elements** of `String...`, you must iterate over each element and check it individually; checking the array alone is not enough.

### Avoiding Side Effects on the Caller's Array

If a method needs to sort the received data:

```java
static int[] sortedCopy(int... values) {
    java.util.Objects.requireNonNull(values, "values");
    int[] copy = values.clone();
    java.util.Arrays.sort(copy);
    return copy;
}
```

Because a copy is created, `sortedCopy(existingArray)` does not reorder `existingArray`. This illustrative example returns the sorted array for the caller to use next; it does not modify the input source itself.

## 12. Comprehensive Practice Program

Save all of the following content into **`VarargsPractice.java`**:

```java
import java.util.Arrays;

public class VarargsPractice {
    static void printCount(String label, String... words) {
        if (words == null) {
            System.out.println(label + ": null-array");
            return;
        }
        System.out.println(label + ": " + words.length + " " +
                Arrays.toString(words));
    }

    static void choose(int number) {
        System.out.println("fixed: " + number);
    }

    static void choose(int... numbers) {
        System.out.println("varargs: " + Arrays.toString(numbers));
    }

    static void objects(Object... values) {
        System.out.println("objects: " + values.length + " " +
                Arrays.deepToString(values));
    }

    public static void main(String[] args) {
        printCount("empty");
        printCount("two", "A", "B");
        printCount("one-null", (String) null);
        printCount("array-null", (String[]) null);

        choose(7);
        choose(7, 8);
        choose(new int[]{1, 2, 3});

        objects((Object[]) new String[]{"X", "Y"});
        objects((Object) new String[]{"X", "Y"});
    }
}
```

Compile and run:

```bash
javac -encoding UTF-8 VarargsPractice.java
java VarargsPractice
```

**Exact Stdout:**

```text
empty: 0 []
two: 2 [A, B]
one-null: 1 [null]
array-null: null-array
fixed: 7
varargs: [7, 8]
varargs: [1, 2, 3]
objects: 2 [X, Y]
objects: 1 [[X, Y]]
```

This is an example gathering **confusing calls** into one program: element counts, null arrays, null elements, fixed overload precedence, and the difference between passing `String[]` as `Object[]` versus a single `Object` element. The casts in the example are used **intentionally** to force a clear call meaning.

## 13. Self-Practice Exercises with Answers

### Exercise 1 — Fixing Varargs Position

Invalid declaration:

```java
static void notifyAll(String... users, String message) {
}
```

**Why is it wrong?** The varargs parameter `users` is not last. **One way to fix it:**

```java
static void notifyAll(String message, String... users) {
    for (String user : users) {
        System.out.println(user + ": " + message);
    }
}
```

Call: `notifyAll("Đã cập nhật", "An", "Bình");`. `message` is required first, while `users` receives two elements.

### Exercise 2 — Counting Formal Parameters and Arguments

```java
static void record(String category, int... values) {
}
```

With `record("score", 1, 2, 3)`:

- Number of **formal parameters**: **2** (`category` and `values`).
- Number of **argument expressions at the call site**: **4**.
- Length of the `values` array in the body: **3**.

With `record("score")`, there are still **2 formal parameters**, but the call has only **1 argument**, and `values.length == 0`.

### Exercise 3 — Array or Single Element?

```java
static int size(Object... values) {
    return values == null ? -1 : values.length;
}
```

Predictions:

- `size(new String[]{"A", "B"})`: **2** because `String[]` can be passed as an `Object[]` array.
- `size((Object) new String[]{"A", "B"})`: **1** because the `String[]` array is treated as a single `Object` element.
- `size(new int[]{1, 2})`: **1** because `int[]` is not an `Object[]`.
- `size((Object[]) null)`: **-1** because the varargs array itself is `null`.
- `size((Object) null)`: **1** because the varargs array contains a single `null` element.

### Exercise 4 — Which Method Is Selected?

```java
static String kind(int value) {
    return "fixed";
}

static String kind(int... values) {
    return "varargs";
}
```

- `kind(1)` → **`"fixed"`**.
- `kind()` → **`"varargs"`**.
- `kind(1, 2)` → **`"varargs"`**.
- `kind(new int[]{1})` → **`"varargs"`** because the overload accepts a matching array.

### Exercise 5 — Ambiguous Calls

```java
static void send(String... parts) { }
static void send(Integer... parts) { }
```

What is the issue with `send()` and `send(null)`? **Ambiguous at compile time** because both overloads apply with neither being more specific. To select one clearly, use `send(new String[0])` or `send(new Integer[0])` for an empty call, and cast to the appropriate array type if intentionally passing a `null` array.

### Exercise 6 — Is a Copy Needed?

```java
static void replaceFirst(String... values) {
    values[0] = "changed";
}
```

If the caller passes `String[] data = {"old"}; replaceFirst(data);`, then `data[0]` becomes **`"changed"`**. If you do not want to modify the caller's data, create a copy of the array inside the method before writing.

## 14. Checklist Before Writing or Calling a Varargs Method

1. **Read the declaration:** is there only **one** `Type... name`, and is it at the end of the parameter list?
2. **Distinguish an array from elements:** is the caller passing `new Type[]{...}` or passing multiple individual expressions?
3. **Count arguments accurately:** required parameters before varargs must still all be supplied.
4. **Check types:** elements in an expanded call must be convertible to `Type`; a directly passed array must be compatible with `Type[]`.
5. **Be careful with `null`:** a null array differs from a single null element; use an explicit cast when truly needed.
6. **Check overloads:** fixed-arity candidates are considered before variable arity; `()` or `(null)` calls can be ambiguous with multiple overloads.
7. **Check the caller's existing array:** does the method modify array elements or retain the array reference?
8. **Check generic varargs:** consider heap pollution and only use `@SafeVarargs` when the implementation is genuinely safe.
9. **Avoid non-Java syntax:** there is no `...array` operator to spread an array in a call, and varargs cannot be placed before a regular parameter.
10. **Prefer clear calls:** when you want no elements, call without passing varargs arguments; when you want to pass a single null element or a null array, write an explicitly typed expression.

## Key Takeaways

- Varargs is declared as **`Type... name` in the last position**; a parameter list can have only one varargs parameter.
- Inside the method body, the varargs parameter is a **`Type[]` array**. A call can supply **0 or more elements**, or **a compatible array**.
- **`f()`**, **`f((String) null)`**, and **`f((String[]) null)`** can represent three completely different cases: an empty array, a single null element, and a null array.
- When overloading, Java prioritizes finding methods callable with a fixed number of parameters before considering varargs expansion; multiple varargs overloads can make calls ambiguous.
- **Reference arrays** such as `String[]` can be passed as `Object[]`, whereas `int[]` cannot. Use the proper cast when you need to distinguish "an array as the whole list" from "an array as a single element".
- Varargs is backed by a real array; it can share an array with the caller and carries the risk of **heap pollution** when combined with non-reifiable generics. Write APIs with clear contracts and copy data when needed.

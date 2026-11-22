# Varargs Parameters in Java: Declaration, Passing Arrays, and Zero-Argument Calls

**Varargs** (*variable arity parameters*) allow a Java method to accept a **variable number of arguments** in the last parameter position. Instead of forcing callers to create an array at every call site, Java lets them write elements consecutively: `sum(2, 3, 5)`. Inside the method, a varargs parameter is still handled as **an array**. This lesson explains the `T...` syntax, three important invocation forms (zero arguments, multiple arguments, and passing an existing array), rules regarding `null`, overloading, generics, and side effects when using arrays.

The examples are written for **Java 17 and later**. Snippets with a file name and `javac`/`java` commands are standalone programs; snippets explicitly marked "illustrative" only demonstrate syntax or compile errors.

## 1. What Problem Do Varargs Solve?

Suppose you need to sum multiple integers. You could declare a fixed signature `sum(int a, int b)`, but that method only accepts exactly two numbers; continuing to create 3-, 4-, and 5-parameter versions makes the API verbose. You could let callers pass an `int[]`, yet each time they need to combine separate numbers, they have to create the array themselves.

Varargs provide a convenient syntax:

~~~java
static int sum(int... numbers) {
    int total = 0;
    for (int number : numbers) {
        total = Math.addExact(total, number);
    }
    return total;
}
~~~

This is an **illustrative method snippet**, placed inside a class and not yet containing `main`. When called:

~~~java
sum();                     // Pass no elements -> 0
sum(2, 3, 5);              // Pass three elements -> 10
sum(new int[] {4, 6});     // Pass an existing int[] array -> 10
~~~

All three calls can use the same **single declaration**. Varargs do not turn Java into a language with an unlimited number of formal parameters: in the declaration there is still **a single trailing array parameter**, but the call-site syntax can expand to zero, one, or more elements.

## 2. The `T... name` Declaration Syntax

Basic structure:

~~~text
returnType methodName(Type... parameterName) {
    // parameterName is used as a Type[] array
}
~~~

Example:

~~~java
static void printWords(String... words) {
    for (String word : words) {
        System.out.println(word);
    }
}
~~~

In `String... words`:

- `String` is the accepted **element type**.
- `...` (exactly three dots) marks **varargs**.
- `words` is the **parameter name**; inside the method, it has type `String[]`.
- `()` is the parameter list, just as in any other Java method declaration.

Because `words` is an array inside the method body, you can use `words.length`, `words[0]` when non-empty, `Arrays.toString(words)`, or a `for-each` loop.

Constraints:

1. A formal parameter list may declare **at most one varargs parameter**.
2. If present, the varargs parameter must **appear last in the parameter list**.
3. Regular parameters can precede varargs: `printLabels(String prefix, String... labels)`.
4. No regular parameter can appear **after** varargs.
5. You can use a primitive type, reference type, or array type as the element type: `int...`, `String...`, `String[]...`.
6. A constructor can also have varargs: `Bag(String... items)`; the last-position rule still applies.

An **intentionally invalid** example:

~~~java
void invalid(int... numbers, String name) {
}
~~~

The compiler rejects it because `numbers` is varargs while `name` still follows it. Fix it to:

~~~java
void valid(String name, int... numbers) {
}
~~~

The examples above are **declaration snippets inside a class**, not standalone Java files. Being "last" applies to the order of **formal parameters** of a method/constructor; it has nothing to do with where fields are declared in the class.

## 3. Three Ways to Call: Zero Arguments, Individual Arguments, Existing Array

A call to `sum(int... numbers)` can take three common forms:

| Call | Inside `numbers` | Result |
| --- | --- | --- |
| `sum()` | A new `int[]` of length 0 in a variable-arity call | 0 |
| `sum(2)` | An array containing one element `2` | 2 |
| `sum(2, 3, 5)` | An array containing three elements `2, 3, 5` | 10 |
| `sum(new int[] {4, 6})` | The existing passed array reference itself when matching the array parameter form | 10 |
| `sum(new int[0])` | An empty array created by the caller | 0 |

With the individual-arguments syntax, you can picture the compiler arranging the elements into a suitable array to invoke the method. That is a **semantic model** for understanding Java, without needing to assume a specific memory layout or a specific number of allocations in how the JVM optimizes it.

**Calling `sum()` with no arguments does not mean the parameter is `null`.** In a normal varargs call, `numbers.length == 0`, so the loop does not execute and the sum remains 0. If the caller deliberately passes `null` with the array type, the semantics differ and must be handled separately.

### Regular Parameters Before Varargs

Given the declaration:

~~~java
static String format(String title, String... values) {
    return title + "[" + String.join(", ", values) + "]";
}
~~~

The `title` parameter must always be provided. Only the **varargs part** can accept 0 elements:

~~~java
format("Names");                   // Names[]
format("Names", "An", "Binh");      // Names[An, Binh]
format("Names", new String[] {"An", "Binh"}); // Names[An, Binh]
~~~

The three call snippets are illustrative inside a method. `format()` is invalid because it lacks the required `title` parameter.

## 4. Complete Program: Comparing Invocation Forms

Create the file **`VarargsBasicsDemo.java`**:

~~~java
import java.util.Arrays;

public class VarargsBasicsDemo {
    static int sum(int... numbers) {
        int result = 0;
        for (int number : numbers) {
            result = Math.addExact(result, number);
        }
        return result;
    }

    static String format(String title, String... values) {
        return title + "[" + String.join(", ", values) + "]";
    }

    static void inspect(String... values) {
        if (values == null) {
            System.out.println("Mảng varargs là null");
            return;
        }

        String first = values.length == 0
                ? "(không có)"
                : String.valueOf(values[0]);

        System.out.println("length=" + values.length + "; first=" + first);
    }

    static void uppercaseFirst(String... values) {
        if (values.length > 0 && values[0] != null) {
            values[0] = values[0].toUpperCase();
        }
    }

    public static void main(String[] args) {
        System.out.println("sum() = " + sum());
        System.out.println("sum(2, 3, 5) = " + sum(2, 3, 5));
        System.out.println("sum(array) = " + sum(new int[] {4, 6}));

        System.out.println(format("Names"));
        System.out.println(format("Names", "An", "Binh"));

        String[] names = {"Mai", "Lan"};
        System.out.println(format("Array", names));

        inspect();
        inspect("A", "B");
        inspect((String) null);
        inspect((String[]) null);

        String[] mutable = {"minh", "hoa"};
        uppercaseFirst(mutable);
        System.out.println(Arrays.toString(mutable));
    }
}
~~~

Run from the directory containing the file:

~~~bash
javac -encoding UTF-8 VarargsBasicsDemo.java
java VarargsBasicsDemo
~~~

Expected stdout:

~~~text
sum() = 0
sum(2, 3, 5) = 10
sum(array) = 10
Names[]
Names[An, Binh]
Array[Mai, Lan]
length=0; first=(không có)
length=2; first=A
length=1; first=null
Mảng varargs là null
[MINH, hoa]
~~~

Explanation of the line groups:

- The three `sum` calls receive **zero elements**, **three individual elements**, and **a two-element array**, respectively.
- `format("Names")` has one `title` argument and **no** `values` elements, so `String.join` joins the empty array into an empty string.
- `format("Array", names)` passes the `String[]` array directly into the varargs parameter.
- `inspect()` has a parameter array of length **0**, which differs from `inspect((String[]) null)` where the array parameter is **null**.
- `inspect((String) null)` passes **one null element**, so its length is **1**.
- `uppercaseFirst(mutable)` modifies the first element of the `mutable` array because the varargs parameter receives the exact array reference passed from the caller.

`Math.addExact` helps the `sum` example detect integer overflow via `ArithmeticException` instead of silently overflowing `int`. The API of `sum` only guarantees returning the sum when the calculation stays within the `int` value range.

## 5. Varargs Are Essentially an Array in the Method Body

At the declaration level, the following two forms **cannot coexist as two overloads** in the same class:

~~~java
void print(String... words) {
}

void print(String[] words) {
}
~~~

This is an intentional error example. Both declarations have a parameter type equivalent to a `String[]`, so the compiler will report a duplicate method signature. Both `String... words` and `String[] words` allow using `words.length` and iterating over the array in the body.

The main difference lies in the **call-site syntax**:

- With `print(String... words)`, you can call `print()`, `print("A", "B")`, or `print(new String[] {"A", "B"})`.
- With `print(String[] words)` without varargs, you must pass exactly one argument of a compatible array type, such as `print(new String[] {"A", "B"})`; you cannot call `print("A", "B")` and expect the compiler to bundle the individual arguments.

Varargs are a convenience supported by Java at **call-site compile time**, while the method body uses an array parameter. The ellipsis syntax does not turn the array elements into a new structure with a different access mechanism.

### Why Does Passing an Existing Array Require Caution?

If the last argument at the call site matches the required array type directly, Java can apply a **fixed-arity** invocation: that array argument itself is passed to the method, without necessarily wrapping it into another array. In the `uppercaseFirst(mutable)` example, the method receives the caller's `String[]` array and modifies `mutable[0]`.

Conversely, calling `uppercaseFirst("minh", "hoa")` in variable-arity form turns the individual arguments into a parameter array used for the call; the caller does not have a separate `mutable` array variable to observe as above. Side effects on the array inside the call can still occur, but how the reference is shared differs.

**You should not assume a varargs method is a pure function**. If it modifies elements inside an array passed in by the caller, the caller's object also changes. Use `Arrays.copyOf` or an appropriate copying mechanism if the method must keep the input data independent.

## 6. A Zero-Argument Call Is Not Passing null

Inside the body of `inspect(String... values)`, the call `inspect()` creates a zero-length array, **not** a null array. Explicit ways to express your intent:

| Call | Result for `values` |
| --- | --- |
| `inspect()` | Non-null array, length 0 |
| `inspect(new String[0])` | Non-null array, length 0 |
| `inspect((String[]) null)` | The array itself has `values == null` |
| `inspect((String) null)` | Array of length 1, first element is null |
| `inspect(null, "A")` | Array of length 2, first element is null |

The call `inspect(null)` can be treated in **fixed-arity form** as a null `String[]` argument, and `javac` may issue a warning; it is not the way to express "no elements". If you want empty, use `inspect()`; if you want a single null element, cast with `(String) null`. An API that accepts an array from callers should explicitly specify whether it accepts a null array and check before accessing `values.length`.

## 7. Regular Parameters and Varargs in the Same Method

A declaration such as:

~~~java
static int weightedSum(int multiplier, int... numbers) {
    int total = 0;
    for (int number : numbers) {
        total = Math.addExact(
                total, Math.multiplyExact(multiplier, number));
    }
    return total;
}
~~~

allows these calls:

~~~java
weightedSum(2);                // 0: no numbers
weightedSum(2, 3);             // 6: one element
weightedSum(2, 3, 4);          // 14: two elements
weightedSum(2, new int[] {3, 4}); // 14: passing an array
~~~

These snippets **illustrate calls and declarations inside a class**, not a standalone program. The `multiplier` parameter is required, while `numbers` accepts 0 or more elements.

If you want to accept **at least one number**, varargs by itself does not guarantee that. You can design the signature as `weightedSum(int multiplier, int first, int... rest)` to require at least one element at compile time; or continue using `int... numbers` and check `numbers.length > 0` in the body if the API should report an error when empty.

Placing regular parameters before varargs creates a more self-describing API when there is a required configuration part and a flexible-count data part.

## 8. Overloading and Varargs Call Resolution Rules

Varargs is a way of declaring the last parameter; **it does not mean it always wins** over overloads with a fixed number of parameters. Java selects methods according to applicability phases; calls that match in fixed-arity form are evaluated before falling back to variable arity.

Create the standalone file **`VarargsOverloadDemo.java`**:

~~~java
public class VarargsOverloadDemo {
    static String choose(int number) {
        return "fixed: " + number;
    }

    static String choose(int... numbers) {
        return "varargs: " + numbers.length;
    }

    public static void main(String[] args) {
        System.out.println(choose(7));
        System.out.println(choose(7, 8));
        System.out.println(choose());
        System.out.println(choose(new int[] {1, 2, 3}));
    }
}
~~~

~~~bash
javac VarargsOverloadDemo.java
java VarargsOverloadDemo
~~~

Stdout:

~~~text
fixed: 7
varargs: 2
varargs: 0
varargs: 3
~~~

`choose(7)` selects the `int` overload; two arguments or zero arguments select the varargs overload; an `int[]` can be passed directly into varargs.

**Advanced note:** multiple varargs overloads with different element types, such as `send(String...)` and `send(Integer...)`, can make `send()` ambiguous because both accept 0 elements. The next chapter on **placement limits and confusing calls** analyzes all overload phases, `null` ambiguity, and array/element selection in full.

## 9. Varargs with Reference Types and Multidimensional Arrays

Varargs accept primitive types or reference types. However, when the **element type itself is an array**, the form inside the body gains an extra array dimension:

~~~java
static int countElements(String[]... groups) {
    int count = 0;
    for (String[] group : groups) {
        count += group.length;
    }
    return count;
}
~~~

**Illustrative snippet inside a class**, assuming every `group` is non-null. `String[]... groups` means that inside the body `groups` has type `String[][]`: each element is a `String[]`.

You can call:

~~~java
countElements();                                 // 0
countElements(new String[] {"A", "B"});           // 2
countElements(new String[] {"A"}, new String[] {"B", "C"}); // 3
countElements(new String[][] {{"A"}, {"B", "C"}});          // 3
~~~

Compare this with `String... words`, whose parameter type is `String[]` and whose individual elements are `String`. The `...` syntax **does not automatically "flatten"** every kind of array recursively.

### The `Object...` and Array Pitfall

Illustrative example:

~~~java
static void log(Object... values) {
    System.out.println(values.length);
}
~~~

- `log(new int[] {1, 2})` passes **one element** of type `int[]` because `int[]` is an `Object`, yet **not** an `Object[]`; it prints `1`.
- `log(new String[] {"A", "B"})` can pass the entire `String[]` array as an `Object[]` (reference arrays are covariant); inside the body, it prints `2`.
- `log((Object) new String[] {"A", "B"})` casts the expression to `Object`, forcing the variable-arity call to receive **a single element** which is the array object; inside the body, it prints `1`.

This difference is a consequence of array types and argument type compatibility at the call site. With an API accepting `Object...`, be careful when clients pass an array that they intend to treat as **a single value**.

## 10. Varargs, Generics, and Heap Pollution Warnings

A declaration such as `static <T> void printGroups(List<T>... groups)` combines a **varargs array** with **generic type erasure**. `List<T>` is not a fully reifiable element type at runtime, so `javac` may warn about *possible heap pollution* or *unchecked generic array creation*. You should not treat a call that compiles as proof that every operation on a generic array is safe.

**Why is this dangerous?** If code treats a `List<String>[]` array as an `Object[]` and stores a `List<Integer>` into it, a later `String` read can throw `ClassCastException`. Do not perform type-unsafe writes to the varargs array, do not expose the array to callers, and consider accepting `List<List<T>>`/`Collection` when appropriate for the API.

`@SafeVarargs` is a commitment by the author that the code **performs no unsafe operations on the varargs array**; the annotation does not automatically make broken code safe. In Java 17, it is only valid on qualifying constructors or `static`, `final`, or `private` methods—not on overridable instance methods. Exploit details, runnable examples, compiler warnings, and annotation restrictions are covered in the lesson **Varargs Placement Limits and Confusing Calls**.

For simple `int...` or `String...`, beginners only need to remember "it is an array in the body"; pay the closest attention to heap pollution when the varargs element type involves non-reifiable generics.

## 11. Varargs in Constructors

A constructor can also declare a variable-arity parameter, for example:

~~~java
class Tags {
    private final java.util.List<String> values;

    Tags(String... names) {
        if (names == null) {
            throw new IllegalArgumentException("names là null");
        }
        values = java.util.List.copyOf(java.util.Arrays.asList(names));
    }

    int size() {
        return values.size();
    }
}
~~~

**This is an illustrative class definition**, without `main`; `Tags()`, `Tags("A")`, and `Tags("A", "B")` can all invoke the varargs constructor. `Tags(new String[] {"A", "B"})` is also accepted.

`List.copyOf` creates a list that disallows modification through its API; it also rejects `null` elements. If you want a clearer contract for null elements, check each name before creating the list. Accepting varargs in a constructor does not automatically make the object immutable: immutability also depends on all fields and the objects they reference.

If you design a constructor with a required parameter before varargs, such as `Tags(String owner, String... names)`, then `owner` must always be supplied when calling it; the number of names in the varargs part can still be 0.

## 12. Familiar Java APIs Using Varargs

Several standard APIs demonstrate the usefulness of varargs:

- `System.out.printf("%s: %d%n", "Count", 3)`: formats output; `printf` takes a format parameter followed by `Object...`.
- `String.format("%s-%d", "ID", 7)`: returns a formatted `String` according to format rules.
- `java.util.List.of("A", "B", "C")`: creates a list that does not support modification through its API; `List.of` provides multiple overloads including a varargs overload.
- `java.util.Arrays.asList("A", "B")`: creates a fixed-size list backed by the input/underlying array according to the API contract.
- `java.nio.file.Path.of("dir", "file.txt")`: has an overload accepting `String first, String... more` to join path segments.

Not all of the APIs above share the same semantics regarding `null`, data copying, or mutability of the result. **Varargs only describes how a variable number of arguments is passed**, not the business behavior of the API itself.

Do not confuse varargs with the `...` ellipsis when documentation writers mean "and so on": in Java code, `Type...` is formal syntax with placement and type constraints.

## 13. Common Compile-Time and Runtime Errors

| Issue | Example | How to Handle |
| --- | --- | --- |
| Varargs not in last position | `void f(int... xs, String label)` | Change to `void f(String label, int... xs)` |
| Declaring more than one varargs | `void f(int... a, String... b)` | Keep at most one, at the end |
| Using the wrong element type | `sum("3", "4")` with `int...` | Pass `int` or convert the data appropriately |
| Assuming `sum()` creates `null` | Using `numbers == null` to detect an empty array | Check `numbers.length == 0` |
| Passing `(String[]) null` and iterating immediately | `for (String x : words)` | Check for null or reject the input |
| Not distinguishing a null array from a null element | `f((String[]) null)` and `f((String) null)` | Cast to clarify intent |
| Assuming a passed array is always copied | `uppercaseFirst(array)` | Treat it as a shared array; avoid mutating or copy it yourself |
| Ambiguous varargs overload call | `send()` with `String...` and `Integer...` | Specify the array type or improve the API |
| Overloading `int[]` and `int...` | Two declarations with equivalent signatures | Keep only one declaration |
| Misusing generic varargs | `List<String>...` then manipulating as `Object[]` | Avoid unsafe writes; consider an alternative type design |
| Misapplying `@SafeVarargs` | Using on an overridable method or unsafe code | Use only when eligible and truly safe |
| Passing a primitive array to `Object...` expecting elements to be unpacked | `log(new int[]{1,2})` | Recognize it is a single `int[]` object; handle accordingly |

Another misconception is treating varargs as passing a reference to the caller's **variable**. Java always passes arguments **by value**: when passing an array, the copied value is the reference to the array; the **array object** can be shared, whereas reassigning the parameter variable does not change the array variable on the caller side.

## 14. Choosing Varargs, Arrays, or Collections?

Not every method taking a list of items should use varargs.

| Need | Usually Appropriate Choice | Reason |
| --- | --- | --- |
| Convenient API for a small, varying number of elements | `T...` | Calling `f(a, b, c)` is clear and concise |
| Caller already has an array | `T...` or `T[]` | Both accept arrays; varargs is also convenient for individual arguments |
| Need to make clear a collection must be passed | `List<T>` or `Collection<T>` | Expresses the collection object and its operations |
| Large data or data passed across multiple layers | `List<T>`, array, iterator/stream as appropriate | Avoids overly long call syntax and keeps ownership clear |
| API requires at least one element | `f(T first, T... rest)` or body validation | Varargs alone permits 0 elements |
| Multiple same-named overloads with different varargs types | Consider distinct names or a collection-based API | Avoids ambiguous invocation |

Varargs are great for the **caller** experience. When designing an API, you must still specify what happens when there are zero elements, nulls, duplicate elements, mutated input data, or very large element counts.

## 15. Self-Check

**Question 1.** Given `static int sum(int... xs)`, are the calls `sum()`, `sum(1, 2)`, and `sum(new int[]{1, 2})` valid? What is `xs.length` in each case?

**Question 2.** Why is `static void log(String... xs, int level)` invalid? Rewrite it so that `level` is required while `xs` has a flexible count.

**Question 3.** Given `void show(String... words)`, what is the difference between `show()`, `show((String[]) null)`, and `show((String) null)`?

**Question 4.** An array `String[] labels = {"a", "b"}` is passed to `uppercaseFirst(labels)`. Why can `labels[0]` change to `"A"` after the call? If the method only reads the array, does that side effect occur?

**Question 5.** Why cannot two methods with the same name, `void print(int[] values)` and `void print(int... values)`, be declared together in the same class?

**Question 6.** Given two overloads `choose(int)` and `choose(int...)`, which method does `choose(5)` select? What about `choose()`?

**Question 7.** Given `log(Object... values)`, do `log(new int[]{1, 2})` and `log(new String[]{"A", "B"})` result in the same number of elements in `values`?

**Question 8.** Why can generic varargs such as `List<String>...` trigger a warning? Does `@SafeVarargs` legitimize code that writes the wrong type into the array?

**Reference Answers:**

1. All three are valid; the lengths are 0, 2, and 2, respectively.
2. Varargs must be last; write `static void log(int level, String... xs)`.
3. An empty array of length 0; a null array reference; an array of length 1 containing a null element.
4. Because the method receives a reference to the same array and modifies an element; a read-only method does not cause that array-mutating side effect.
5. Both have parameter type `int[]` in their signature, causing a duplicate declaration.
6. `choose(int)` for a single number; `choose(int...)` when passing no numbers.
7. Different: `int[]` is a single object inside `Object...`, so length is 1; `String[]` can be passed as `Object[]`, so length is 2.
8. Due to generic type erasure combined with how arrays are type-checked at runtime; the annotation is a promise by the author, and does not turn an unsafe operation into a safe one.

## 16. References

- [Java Language Specification 17, §8.4.1 — Formal Parameters](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.4.1): variable-arity parameter declarations and placement constraints.
- [Java Language Specification 17, §15.12 — Method Invocation Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.12): overload resolution phases and variable-arity invocations.
- [Java SE 17 API — SafeVarargs](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/SafeVarargs.html): meaning and conditions for using the annotation.
- [Java SE 17 API — Arrays](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Arrays.html): methods for working with arrays, including `asList` and `toString`.

**Remember:** `T... values` is the syntax for declaring a **trailing array parameter**, allowing callers to pass **0, 1, or more individual elements** or **a compatible array**. An empty array differs from a `null` array; a pre-existing passed array can be shared; overloading and generic varargs require attention to additional rules when designing an API.

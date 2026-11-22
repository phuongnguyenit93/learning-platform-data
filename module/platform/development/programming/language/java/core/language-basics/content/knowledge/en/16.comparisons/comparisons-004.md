# Value Comparison vs. Reference Comparison in Java

> **Java core — language-basics / Comparisons**  
> **Version:** Java 17+; single standalone program, no external libraries.  
> **Goal:** Understand that `==` compares **primitive values** when used on primitives, but compares **object identity** when both operands are references; choose `equals()`, `Objects.equals()`, or array comparison APIs appropriately to check content.

## 1. Different Questions: Equal Value or Same Object?

In Java, there are two kinds of questions:

- **Equal value:** Are two numbers equal? Do two strings have the same characters? Are two objects considered equivalent according to the class's rules?
- **Same reference:** Do two reference variables point to the **exact same object** in memory?

~~~java
int x = 42;
int y = 42;
System.out.println(x == y); // true: compares int values.

String a = new String("Java");
String b = new String("Java");
System.out.println(a == b);      // false: two different objects.
System.out.println(a.equals(b)); // true: same contents.
~~~

`a == b` does not automatically compare strings character by character. When both operands are **reference types**, `==` returns `true` when they refer to the same object (or both are `null`), not when their contents are identical.

## 2. `==` and `!=` with Primitive Types

For compatible primitive operands, `==` and `!=` examine **values**, applying numeric type-promotion rules when comparing:

~~~java
int a = 10;
long b = 10L;
boolean equal = (a == b);  // true: numeric comparison.
boolean unequal = (a != b); // false.

boolean ready = true;
boolean enabled = true;
boolean sameFlag = ready == enabled; // true.
~~~

| Operand type | What does `==` mean? | Example |
| --- | --- | --- |
| `int`, `long`, `char`, ... | Compare numeric values after appropriate promotion | `10 == 10L` -> `true` |
| `boolean` | Compare logical values | `true == false` -> `false` |
| `float`, `double` | Compare floating-point values under floating-point rules | `0.0 == -0.0` -> `true` |
| Two comparable references | Check if same object or both `null` | `new Object() == new Object()` -> `false` |

**Important exception for floating-point:** `Double.NaN == Double.NaN` is `false`, even though both expressions evaluate to `NaN`. Use `Double.isNaN(...)` to check for NaN. Directly comparing two computed floating-point values often requires accounting for rounding error.

`==` is invalid for comparing incompatible types; for example, you cannot write `"1" == 1`.

## 3. `==` on References: Same Object, Not Same Content

~~~java
String first = new String("hello");
String alias = first;
String second = new String("hello");

System.out.println(first == alias);  // true: alias to the same object.
System.out.println(first == second); // false: two separate objects.
System.out.println(first.equals(second)); // true: same contents.
~~~

A simple reference assignment does not create a new object: `alias = first` copies the **reference value**. Mutating the state of the object is visible through any alias; reassigning one reference variable does not change the other.

This is especially important for mutable objects, such as arrays or custom classes. Never use `==` to decide whether two objects "have the same data" unless **object identity** is specifically what you need.

## 4. `equals()` and `Objects.equals()`: Comparison by Class Semantics

`equals(Object)` is a method defined on `Object`. However, its behavior depends on how the class implements it:

- The default `Object.equals()` essentially checks **reference identity**.
- `String.equals()` compares **character sequences**.
- Value classes or `record` types can define equality based on their **data components**.
- If a custom class **does not override `equals()`**, two separate instances will still return `equals() == false` even if their fields match.

~~~java
record Point(int x, int y) {}

Point p = new Point(2, 3);
Point q = new Point(2, 3);

System.out.println(p == q);      // false: two separate objects.
System.out.println(p.equals(q)); // true: record compares components.
~~~

When a comparison might encounter `null`, use `java.util.Objects.equals(a, b)`:

~~~java
import java.util.Objects;

// Inside a method:
String a = null;
String b = null;

boolean bothMissing = Objects.equals(a, b); // true.
boolean missingVsText = Objects.equals(a, "Java"); // false.
~~~

`Objects.equals(a, b)` returns `true` if both are null, `false` if only one is null, and delegates to `a.equals(b)` if neither is null. This **does not automatically turn a class's `equals` into content comparison**; it only protects against calling a method on a null reference.

## 5. The `String` Literal and String Pool Trap

Java stores string literals and certain constant strings in the string pool. Because of this, `==` on strings sometimes returns `true`, easily leading learners to think `==` compares content:

~~~java
String a = "Java";
String b = "Ja" + "va"; // Constant expression: can be folded into the same literal.
String c = new String("Java");

System.out.println(a == b); // true: same reference to the interned string.
System.out.println(a == c); // false: new creates a separate String.
System.out.println(a.equals(c)); // true: same characters.
~~~

**Do not rely on the string pool to check user data.** Strings read from files, parameters, APIs, or constructed at runtime are not guaranteed to share the same reference merely because their contents match.

Good rule of thumb: to check whether two strings contain the same text, use `a.equals(b)` when `a` is guaranteed non-null, `"Java".equals(a)` when comparing against a constant, or `Objects.equals(a, b)` when either may be null.

## 6. Wrapper Classes (`Integer`, `Boolean`, etc.) and Autoboxing

Wrapper classes hold a primitive value, but an `Integer` variable itself is a **reference**.

~~~java
Integer a = Integer.valueOf(1000);
Integer b = Integer.valueOf(1000);

System.out.println(a.equals(b)); // true: two int values are equal.
~~~

**Do not rely on `a == b` to compare the values of two wrappers.** Small values may use a cache, so instance identity depends on how instances were created or cached; `==` can yield inconsistent results in different situations.

When one side is a primitive and the other is its corresponding wrapper, Java **unboxes** the wrapper to compare values:

~~~java
Integer wrapped = Integer.valueOf(1000);
int primitive = 1000;
System.out.println(wrapped == primitive); // true: unboxes then compares numerically.
~~~

However, unboxing a `null` reference throws `NullPointerException`:

~~~java
Integer missing = null;
// boolean equal = (missing == 0); // NPE at runtime.
boolean safe = Objects.equals(missing, Integer.valueOf(0)); // false.
~~~

Distinguish **two wrappers** (which compare references under `==`) from **wrapper vs. primitive** (which unboxes and compares values). This bug often surfaces when changing parameter types or using generics.

## 7. Arrays: `==`, `equals()`, and `Arrays.equals()`

Arrays are objects. Two separate arrays with identical elements are still not the same object:

~~~java
int[] first = {1, 2, 3};
int[] second = {1, 2, 3};

System.out.println(first == second);              // false.
System.out.println(first.equals(second));         // false.
System.out.println(java.util.Arrays.equals(first, second)); // true.
~~~

Arrays **do not override** `Object.equals()` to compare elements. Use `Arrays.equals` for one-dimensional arrays; for nested arrays, `Arrays.deepEquals` compares inner array contents:

~~~java
int[][] a = {{1, 2}};
int[][] b = {{1, 2}};
System.out.println(java.util.Arrays.equals(a, b)); // false: separate inner arrays.
System.out.println(java.util.Arrays.deepEquals(a, b)); // true.
~~~

Quick reference table:

| Data to compare | Recommended approach | Avoid misunderstanding |
| --- | --- | --- |
| Two `int`/`boolean` | `==` or `!=` | This is primitive value comparison |
| Two references, checking same object | `==` | Does not represent equal content |
| Two `String` values, guaranteed non-null | `equals()` | `==` is affected by interning/string pool |
| Two nullable objects | `Objects.equals(a, b)` | Still depends on the class's `equals` |
| Two 1D primitive arrays | `Arrays.equals(a, b)` | Arrays inherit `Object.equals` |
| Two multidimensional arrays | `Arrays.deepEquals(a, b)` | `Arrays.equals` only compares top-level elements |
| Two instances of a custom class | `equals()` overridden per contract | Default `Object.equals()` is identity |

If you override `equals()`, also override `hashCode()` with consistent logic to preserve the contract in `HashSet`/`HashMap`. `record` is a useful choice for simple immutable data; note that array-typed components in a record are not deep-compared automatically.

## 8. Runnable Java 17+ Program

Create the file **ValueVsReferenceDemo.java**:

~~~java
import java.util.Arrays;
import java.util.Objects;

public final class ValueVsReferenceDemo {
    record Point(int x, int y) {}

    static final class Box {
        final int value;
        Box(int value) { this.value = value; }
    }

    public static void main(String[] args) {
        int x = 42;
        int y = 42;
        System.out.println("primitiveEqual=" + (x == y));

        String literal = "Java";
        String constant = "Ja" + "va";
        String created = new String("Java");
        String alias = created;
        System.out.println("literalSame=" + (literal == constant));
        System.out.println("literalVsCreated=" + (literal == created));
        System.out.println("createdAlias=" + (created == alias));
        System.out.println("stringValue=" + literal.equals(created));

        String missing = null;
        System.out.println("bothNull=" + Objects.equals(missing, null));
        System.out.println("nullVsText=" + Objects.equals(missing, literal));
        System.out.println("literalEqualsNull=" + "Java".equals(missing));

        Integer boxed = Integer.valueOf(1000);
        Integer anotherBoxed = Integer.valueOf(1000);
        int primitive = 1000;
        System.out.println("wrapperValue=" + boxed.equals(anotherBoxed));
        System.out.println("wrapperVsPrimitive=" + (boxed == primitive));
        Integer absent = null;
        try {
            System.out.println("unsafe=" + (absent == 0));
        } catch (NullPointerException ex) {
            System.out.println("wrapperNull=NullPointerException");
        }

        int[] a = {1, 2, 3};
        int[] b = {1, 2, 3};
        System.out.println("arrayIdentity=" + (a == b));
        System.out.println("arrayDefaultEquals=" + a.equals(b));
        System.out.println("arrayContent=" + Arrays.equals(a, b));

        int[][] grid1 = {{1, 2}};
        int[][] grid2 = {{1, 2}};
        System.out.println("nestedShallow=" + Arrays.equals(grid1, grid2));
        System.out.println("nestedDeep=" + Arrays.deepEquals(grid1, grid2));

        Box first = new Box(7);
        Box second = new Box(7);
        System.out.println("plainObjectEquals=" + first.equals(second));

        Point p = new Point(2, 3);
        Point q = new Point(2, 3);
        System.out.println("recordIdentity=" + (p == q));
        System.out.println("recordValue=" + p.equals(q));
        System.out.println("recordHashEqual=" + (p.hashCode() == q.hashCode()));

        double nan = Double.NaN;
        System.out.println("nanPrimitiveEqual=" + (nan == nan));
        System.out.println("nanDetected=" + Double.isNaN(nan));
    }
}
~~~

Compile and run in the directory containing the file (Bash, PowerShell, or Command Prompt):

~~~bash
javac -encoding UTF-8 ValueVsReferenceDemo.java
java ValueVsReferenceDemo
~~~

**Exact expected stdout:**

~~~text
primitiveEqual=true
literalSame=true
literalVsCreated=false
createdAlias=true
stringValue=true
bothNull=true
nullVsText=false
literalEqualsNull=false
wrapperValue=true
wrapperVsPrimitive=true
wrapperNull=NullPointerException
arrayIdentity=false
arrayDefaultEquals=false
arrayContent=true
nestedShallow=false
nestedDeep=true
plainObjectEquals=false
recordIdentity=false
recordValue=true
recordHashEqual=true
nanPrimitiveEqual=false
nanDetected=true
~~~

The output intentionally omits `boxed == anotherBoxed` because identity results for cached wrappers should never be used to test value equality. Instead, the program explicitly tests `boxed.equals(anotherBoxed)` and `boxed == primitive`; the latter unboxes and compares numerically.

## 9. Exercises and Key Takeaways

**Exercise 1.** Given two `int` variables with value 5 and two `String` variables with text "5" created by two separate `new String("5")` calls, what is `==` asking in each case?

**Exercise 2.** Write a nullable string comparison using `Objects.equals`. Why is calling `a.equals(b)` unsafe when `a == null`?

**Exercise 3.** Create two `int[]` arrays with identical elements. Compare the results of `a == b`, `a.equals(b)`, and `Arrays.equals(a, b)`.

**Exercise 4.** When `Integer wrapped = null;`, what happens with `wrapped == 0`? Contrast it with `Objects.equals(wrapped, Integer.valueOf(0))`.

**Exercise 5.** Create two `record Point(int x, int y)` instances with the same coordinates. Compare `==` and `equals()`. What happens if you write an ordinary class without overriding `equals()`?

### Remember

**`==` compares values for primitive types, but compares identity for two references.** `equals()` checks equality as defined by the class; `Objects.equals()` handles `null` safely. Use content comparison for `String`, `Arrays.equals`/`Arrays.deepEquals` for arrays, and keep wrapper caching/autoboxing traps in mind. Only use `==` on references when you genuinely want to ask "are these the exact same object?".

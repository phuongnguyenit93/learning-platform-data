# Do Not Infer Types from `null` or Standalone Array Initializers with `var`

> **Java core — language-basics / Inference with var**  
> **Version:** Java 17+ (local `var` examples require Java 10 or later).  
> **Goal:** Understand why `var x = null` and `var values = {1, 2}` do not compile; grasp the difference between **an initializer value** and **a target type context**, so you can write valid declarations while still using `var` when the initializer expression already has a determinate type.

## 1. `var` Needs a Type That Can Be Inferred at Compile Time

`var` allows the compiler to infer the **static type** of a local variable from its initializer expression. It is **not** a dynamic data type, does not automatically choose `Object`, and does not wait until runtime to guess the type.

~~~java
var count = 10;           // int
var title = "Java";       // String
var numbers = new int[3]; // int[]
~~~

After the declaration, the variable's type is fixed. For example, `count = "ten";` is invalid because `count` is `int`.

The following two declarations are **invalid** in Java 17:

~~~java
// DOES NOT COMPILE:
var unknown = null;
var scores = {10, 20, 30};
~~~

This is not because the content `null` or the numbers 10, 20, 30 are “bad”, but because **there is not enough information to produce a valid declared type** for `var`.

## 2. Why Is `var x = null` Invalid?

`null` is a value assignable to many different **reference types**, such as `String`, `Integer`, `int[]`, or `Object`. Looking only at the `null` literal, Java cannot infer which type the variable should be declared with.

~~~java
// var name = null;  // Compile error: cannot infer type from null.
~~~

Once the type is specified, initializing with `null` is completely valid:

~~~java
String name = null;
Integer quantity = null;
int[] data = null;
~~~

You can supply a type to **the initializer expression itself**, allowing `var` to infer it:

~~~java
var name = (String) null;     // String
var quantity = (Integer) null; // Integer
var data = (int[]) null;      // int[]
~~~

Although syntactically valid, writing `String name = null;` is **usually clearer** than `var name = (String) null;`. Do not overuse casts just to bypass the explicit type declaration requirement.

**Distinction:** The forms above only create **null references**; they do not create a `String`, `Integer`, or array object. Calling `name.length()` when `name == null` still throws a `NullPointerException`.

## 3. Why Is `var scores = {1, 2, 3}` Invalid?

Standalone curly braces `{1, 2, 3}` in this context are an **array initializer**, not a self-contained expression carrying a complete array type. Java allows this shorthand form when **the declaration already has a clear array type**:

~~~java
int[] scores = {1, 2, 3};        // Valid: int[] type is already present.
String[] labels = {"A", "B"};    // Valid: String[] type is already present.
~~~

In `var scores = {1, 2, 3};`, however, there is no target array type to determine the array initializer; this syntax is rejected.

Create an **explicitly typed array creation expression** instead:

~~~java
var scores = new int[] {1, 2, 3};     // Infers int[].
var labels = new String[] {"A", "B"}; // Infers String[].
var empty = new int[0];              // Infers int[].
~~~

`new int[] {1, 2, 3}` is already **an expression** of type `int[]`, so `var` can infer it. Conversely, `{1, 2, 3}` standing alone is not a valid initializer expression to use with `var`.

## 4. Comparison Table of Valid and Invalid Syntax

| Syntax | Compiles? | Reason or Inferred Type |
| --- | --- | --- |
| `var a = null;` | **No** | The `null` literal does not determine a type |
| `String a = null;` | Yes | The `String` type is explicitly declared |
| `var a = (String) null;` | Yes | Infers type `String` from the cast |
| `var a = {1, 2};` | **No** | The array initializer has no target type |
| `int[] a = {1, 2};` | Yes | The array type `int[]` is explicitly declared |
| `var a = new int[] {1, 2};` | Yes | Infers type `int[]` from array creation |
| `var a = new int[2];` | Yes | The expression has type `int[]` |
| `var a = new String[] {null, "A"};` | Yes | The array type `String[]` is already determined |
| `var grid = new int[][] {{1}, {2, 3}};` | Yes | Infers type `int[][]` |
| `var a = valueReturningString();` | Yes if the method is declared to return `String` | Type `String` is inferred from the **return type**, even if the runtime value is `null` |

**Note:** An array can contain `null` elements if it is a reference array. For example, `new String[] {null, "A"}` still has a clear `String[]` type; it is completely different from `var a = null;`.

## 5. Data Returning `null` Can Still Use `var`

What matters is the **static type of the expression**, not its runtime value:

~~~java
static String lookupName() {
    return null;
}

// Inside another method:
var name = lookupName(); // Valid: the compiler knows the return type is String.
~~~

`name` has **type `String`**, even though its current value is `null`. Java does not have to guess the type from a null literal here; the type is already in the **method declaration** `lookupName()`.

A type can also be inferred from a conditional expression if the expression's typing rules determine one:

~~~java
var selected = true ? null : "fallback"; // String, value is null.
var other = false ? null : "fallback";   // String, value is "fallback".
~~~

Here the presence of the `"fallback"` branch supplies the appropriate `String` reference type for the ternary expression. Yet `var selected = null;` by itself remains invalid.

Do not treat this syntax as a way to skip null checks: if `selected == null`, calling `selected.length()` still causes a `NullPointerException`.

## 6. Runnable Java 17+ Program

Create a file named **VarNullArrayDemo.java** with the full contents:

~~~java
public final class VarNullArrayDemo {
    private static String lookupName() {
        return null;
    }

    private static String describe(String text) {
        return text == null ? "(missing)" : text;
    }

    public static void main(String[] args) {
        String explicitNull = null;
        var typedNull = (String) null;
        var fromMethod = lookupName();

        System.out.println("explicitNull=" + describe(explicitNull));
        System.out.println("typedNull=" + (typedNull == null));
        System.out.println("fromMethodNull=" + (fromMethod == null));

        int[] compact = {1, 2, 3};
        var inferred = new int[] {1, 2, 3};
        var empty = new int[0];

        System.out.println("compactSum="
                + (compact[0] + compact[1] + compact[2]));
        System.out.println("inferredLength=" + inferred.length);
        System.out.println("inferredSecond=" + inferred[1]);
        System.out.println("emptyLength=" + empty.length);

        var labels = new String[] {null, "OK"};
        System.out.println("labelsLength=" + labels.length);
        System.out.println("firstLabelNull=" + (labels[0] == null));
        System.out.println("secondLabel=" + labels[1]);

        var grid = new int[][] {{1, 2}, {3, 4}};
        System.out.println("gridElement=" + grid[1][0]);

        var selected = true ? null : "fallback";
        var alternate = false ? null : "fallback";
        System.out.println("selectedNull=" + (selected == null));
        System.out.println("alternate=" + alternate);
    }
}
~~~

Compile and run in the directory containing the file (Bash, PowerShell, or Command Prompt):

~~~bash
javac -encoding UTF-8 VarNullArrayDemo.java
java VarNullArrayDemo
~~~

**Exact expected output:**

~~~text
explicitNull=(missing)
typedNull=true
fromMethodNull=true
compactSum=6
inferredLength=3
inferredSecond=2
emptyLength=0
labelsLength=2
firstLabelNull=true
secondLabel=OK
gridElement=3
selectedNull=true
alternate=fallback
~~~

Explanation:

1. `explicitNull` has an explicit `String` type; `typedNull` infers `String` thanks to the cast; `fromMethod` infers `String` thanks to the method's return type. All three can hold `null` at runtime.
2. `compact` is a valid `int[]` array because the declaration states the type; `inferred` and `empty` are also `int[]` because the `new int[]`/`new int[0]` expressions supply the type.
3. `labels` has type `String[]` regardless of its first element being `null`. The `grid` array has type `int[][]` and the value at `grid[1][0]` is 3.
4. The two ternary expressions have type `String` but take different branches, so one evaluates to `null` and the other evaluates to `"fallback"`.

## 7. Fixing Declaration Errors Intentionally

When you need to initialize with **null**:

~~~java
// Invalid:
// var token = null;

// Valid and clear:
String token = null;

// Valid, though usually less clear:
var castToken = (String) null;
~~~

When you need to initialize an **array**:

~~~java
// Invalid:
// var points = {4, 8};

// Valid if you want the shorthand { ... } form:
int[] points = {4, 8};

// Valid if you want to use var:
var otherPoints = new int[] {4, 8};
~~~

Do not confuse array initializers with *collection literals*: Java 17 does not have a `var numbers = {1, 2};` syntax to automatically infer `List<Integer>` or `int[]`. If you want a `List`, use an appropriate API such as `List.of(1, 2)` (when an immutable list is needed) and understand the return type and characteristics of the collection.

During code review, ask yourself **“Does this initializer expression have a determinable static type?”**. If not, write an **explicit type declaration** or use an **explicitly typed object/array creation expression** instead of trying to force `var` to guess.

## 8. Pitfalls to Avoid

| Misconception | What Is True in Java 17 |
| --- | --- |
| “`var` always infers `Object` when the type is unknown.” | False: the compiler rejects it if no valid type can be inferred |
| “A `null` value at runtime makes `var` fail.” | False: `var x = lookupName();` is valid if the return type is clear |
| “`var x = (String) null;` creates a String object.” | False: the reference is still `null` |
| “`{1, 2}` standing alone is already `int[]`.” | False: it requires a target array type or `new int[] {...}` syntax |
| “`new String[] {null}` cannot infer a type.” | False: `String[]` is present in the array creation expression |
| “Using `var` lets you reassign any type.” | False: the type is fixed at compile time |
| “`new int[] {1, 2}` is a `List<Integer>`.” | False: it is a primitive `int[]` array |

## 9. Self-Check Exercises

**Exercise 1.** Explain separately why `var a = null;` and `var b = {1, 2};` are invalid. Do they share the exact same kind of missing type information?

**Exercise 2.** Fix `var name = null;` in two ways: an explicit type declaration, or creating an initializer expression of type `String`. Which approach is clearer in real code?

**Exercise 3.** Fix `var values = {2, 4, 6};` in two ways: using `int[]` with a shorthand array initializer, or using `var` with `new int[]`.

**Exercise 4.** Write `var names = new String[] {null, "A"};`. What type does `names` have? What does `names[0] == null` evaluate to? How does this answer relate to inferring a type from a null literal?

**Exercise 5.** Write a method that returns `String` but sometimes returns `null`, then declare `var result = method();`. Why does this line still compile even though the return value may be absent?

### Takeaway

**`var` requires an initializer expression with an inferable static type.** A standalone `null` literal provides no type; a standalone array initializer `{...}` requires a target array type and is therefore invalid with `var`. Use `String x = null;` or `var x = (String) null;` when you need a typed null reference, and use `int[] x = {...};` or `var x = new int[] {...};` when you need an array. `var` only changes how **declarations are written**; it does not make Java a dynamically typed language.
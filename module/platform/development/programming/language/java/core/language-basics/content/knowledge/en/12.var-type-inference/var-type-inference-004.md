# Why `var` Requires an Initializer — Java 17+

`var` is supported in Java for **local variable type inference**. When you write:

~~~java
var quantity = 10;
~~~

the compiler reads the initializer expression `10`, determines that the expression has type `int`, and declares `quantity` as a local variable of type **`int`**. Afterward, the variable still undergoes normal static type checking. `var` is **not** a new data type, nor does it turn Java into a dynamically typed language.

**Why is an initializer required?** Because in a local variable declaration written with `var`, the compiler does not see a type written on the left-hand side. Without **an initializer expression that has a determinate type**, it has no basis to infer the variable's type at the declaration site.

~~~java
int number;       // Valid: the int type is explicitly written.
// var number;     // COMPILE ERROR: no initializer to infer type.

var age = 18;     // Valid: infers int.
// age = "18";    // COMPILE ERROR: String is not int.
~~~

**Article scope:** The “must be initialized” rule here refers to **regular local variable declarations** using `var`. Java also allows `var` in contexts that have **a different source of type inference**, such as the element variable in an enhanced `for` loop and lambda parameters; those cases are explained separately in section 6.

## 1. Comparing Explicit Declarations and `var` Declarations

| Declaration | Valid? | Where Does the Compiler Get the Type? |
| --- | --- | --- |
| `String text;` | Yes | The `String` type is written directly |
| `String text = null;` | Yes | The `String` type is already specified |
| `var text = "Java";` | Yes | The initializer `"Java"` has type `String` |
| `var count = 7;` | Yes | The initializer `7` has type `int` |
| `var amount = 7L;` | Yes | The initializer `7L` has type `long` |
| `var item;` | **No** | Missing an expression to infer the type |
| `var item = null;` | **No** | The `null` literal does not provide a concrete reference type |
| `var item = (String) null;` | Yes | The cast gives the expression type `String` |
| `var list = new java.util.ArrayList<String>();` | Yes | The object creation expression has type `ArrayList<String>` |

An easy point of confusion is that **an explicitly declared variable** can still be left unassigned at declaration time, whereas **a variable declared with `var`** cannot omit its initializer in a regular local declaration.

## 2. Type Inference Happens **at Compile Time**, Not Runtime

The basic process:

~~~text
var count = Integer.parseInt("42");
          |
          v
Compiler checks the expression:
  Integer.parseInt(...) returns int
          |
          v
Static type of count is int
          |
          v
Checks statements using count
  count = 50;      // Valid
  count = "fifty"; // Type mismatch
~~~

The compiler relies on **the static type of the expression**, not on the value after the program has run. For example, if a method is declared to return `String`, then calling it is an expression of type `String`, **even when a particular call returns `null`**.

~~~java
static String findTitle(boolean exists) {
    return exists ? "Guide" : null;
}

// Inside a method:
var title = findTitle(false); // Valid: infers String.
System.out.println(title == null); // true.
~~~

This differs completely from `var title = null;`: a standalone `null` literal has no concrete type to serve as the variable's type. Assigning the cast `(String) null` is valid because the expression then has type `String`.

## 3. Standalone Runnable Java 17+ Example

Create a UTF-8 file named **`VarNeedsInitializerDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class VarNeedsInitializerDemo {
    static String findTitle(boolean found) {
        return found ? "Guide" : null;
    }

    static int readCount() {
        return 3;
    }

    public static void main(String[] args) {
        var count = readCount();
        var price = 2.5;
        var title = "Java";

        System.out.println("count=" + count);
        System.out.println("price=" + price);
        title = title + " 17";
        System.out.println("title=" + title);

        var numbers = List.of(2, 4, 6);
        var sum = 0;
        for (var number : numbers) {
            sum += number;
        }
        System.out.println("sum=" + sum);

        var indices = new StringBuilder();
        for (var i = 0; i < 3; i++) {
            indices.append(i);
        }
        System.out.println("indices=" + indices);

        var typedNull = (String) null;
        System.out.println("typedNull=" + (typedNull == null));
        typedNull = "ready";
        System.out.println("typedNullAfterSet=" + typedNull);

        var fromMethod = findTitle(false);
        System.out.println("methodReturnedNull=" + (fromMethod == null));
        fromMethod = findTitle(true);
        System.out.println("methodReturnedText=" + fromMethod);

        String declaredLater;
        declaredLater = "assigned";
        System.out.println("explicitTypeLater=" + declaredLater);

        var parsed = Integer.parseInt("42");
        var boxed = Integer.valueOf(42);
        System.out.println("parsed=" + parsed);
        System.out.println("boxedType="
                + boxed.getClass().getSimpleName());

        var names = new ArrayList<String>();
        names.add("Ada");
        System.out.println("names=" + names);

        var mixed = new ArrayList<>();
        mixed.add("text");
        mixed.add(1);
        System.out.println("mixed=" + mixed);

        var data = new int[]{1, 2, 3};
        System.out.println("arrayLength=" + data.length);

        final var enabled = true;
        System.out.println("enabled=" + enabled);
    }
}
~~~

Open PowerShell (Windows) or Bash (Linux/macOS) in the directory containing the file, using **JDK 17 or later**:

~~~bash
java -version
javac -version
javac -encoding UTF-8 VarNeedsInitializerDemo.java
java VarNeedsInitializerDemo
~~~

**Exact expected output of `java VarNeedsInitializerDemo`:**

~~~text
count=3
price=2.5
title=Java 17
sum=12
indices=012
typedNull=true
typedNullAfterSet=ready
methodReturnedNull=true
methodReturnedText=Guide
explicitTypeLater=assigned
parsed=42
boxedType=Integer
names=[Ada]
mixed=[text, 1]
arrayLength=3
enabled=true
~~~

The outputs of `java -version` and `javac -version` depend on your environment and are not included in the expected output block.

### Explaining Each Case

- `var count = readCount();` infers `int` from the **return type declaration** of `readCount()`. The compiler does not need to execute the method.
- `var price = 2.5;` infers `double`; `var title = "Java";` infers `String`. Assigning the concatenated `" 17"` remains valid because the variable's type is String.
- `var numbers = List.of(2, 4, 6);` infers `List<Integer>`; in the enhanced `for`, the variable `number` gets element type `Integer`, and is then unboxed when added to `int sum`.
- `for (var i = 0; i < 3; i++)` has initializer `0`, so `i` is `int`; the iteration values are 0, 1, 2.
- `var typedNull = (String) null;` is valid: the expression has type `String` even though **its value** is null. `var fromMethod = findTitle(false);` is also valid because the call has type `String`.
- `String declaredLater;` is valid because the declared type is explicit. If you read `declaredLater` before assigning it, the compiler still reports *variable might not have been initialized*; **having a type** does not mean **already having a value**.
- `parsed` infers `int` from `parseInt`; `boxed` infers `Integer` from `valueOf`. Java does not infer a wrapper instead of a primitive just because both results print as 42.
- `names` infers `ArrayList<String>`. With `var mixed = new ArrayList<>();`, there is no explicit generic target type, so in this case the diamond infers `Object`, creating an `ArrayList<Object>` variable.
- `var data = new int[]{1, 2, 3};` has an array initializer of type `int[]`. `final var enabled = true;` has type `boolean` and does not allow reassigning the variable.

## 4. Why `var x = null` Is Invalid, Yet null Can Be a Result

Distinguish **the type of an expression** from **the value of an expression**:

~~~java
// var a = null; // Invalid: the null literal has no concrete type.

var b = (String) null; // Valid: b has type String.
String c = null;       // Valid: type written explicitly.
~~~

Method example:

~~~java
static String loadName() {
    return null;
}

// Inside a method:
var name = loadName(); // Valid: infers String from loadName's signature.
~~~

At runtime, `name` still holds `null`; calling `name.length()` will throw a `NullPointerException`. **Using `var` does not skip null checks** and does not create a String object in place of null.

Several other expressions without a clear target type are also invalid immediately after `var`:

~~~java
// var f = x -> x + 1;     // Lambda needs a target functional interface.
// var maker = String::new; // Method reference needs a target type.
// var a = {1, 2, 3};      // Short array initializer form needs a target array type.
~~~

Valid explicit-type ways to write them:

~~~java
java.util.function.IntUnaryOperator f = x -> x + 1;
java.util.function.Supplier<String> maker = String::new;
var a = new int[]{1, 2, 3};
~~~

With `var`, the compiler does not receive a target type written on the left-hand side to use for *poly expressions* such as lambdas or method references. Using an explicit type for a functional interface is usually clearer in intent.

## 5. Type Cannot Be Inferred from Assignments Written **After** the Declaration

~~~java
// var points;
// points = 10;
~~~

The snippet above is invalid. The compiler must determine the type **at the declaration site** in order to check the rest of the program. It does not “read backward” from later assignments to infer a type for a declaration missing an initializer.

If you want to assign later, you must supply the type:

~~~java
int points;
points = 10;
System.out.println(points);
~~~

And *definite assignment* must still be satisfied: a local variable with an explicit type that has not yet been assigned cannot be read arbitrarily.

Nor can a later value change “widen the type”:

~~~java
var points = 10;  // int.
points = 20;      // Valid.
// points = 20L;  // Error: long does not automatically narrow to int.
~~~

## 6. Exceptions Regarding the **Source of Type Information**: Enhanced `for` and Lambdas

The statement “`var` needs an initializer” is generally used for simple local variable declarations (`var name = expression;`). However, Java also allows `var` in positions **without an explicit initialization assignment right at the declaration** because the compiler obtains the type from context.

### Element Variable in Enhanced `for`

~~~java
int[] values = {2, 4, 6};
for (var value : values) {
    System.out.println(value);
}
~~~

`value` is inferred as `int` from **the element type of the `int[]` array**. The `:` of the enhanced `for` supplies the inference source, so you do not write `var value = ...`.

### Lambda Parameters in Java 17

~~~java
java.util.function.BinaryOperator<Integer> add =
        (var left, var right) -> left + right;
~~~

Both parameters are inferred as `Integer` thanks to the **target type** `BinaryOperator<Integer>`. This is the `var` form for lambdas, not a regular local variable declaration, and no initializer accompanies each parameter.

When using `var` in a lambda parameter list, **all parameters must use `var`**; do not mix `var` with explicitly typed or untyped parameters in the same list.

### Other Cases

`var` is used in the initializer of a classic `for`, such as `for (var i = 0; ... )`, and in resource declarations of `try-with-resources` such as `try (var reader = new StringReader("hi")) { ... }`. These cases **still have an initializer expression** when using the `var` declaration form.

**Common thread:** the compiler must have **a local source of type information on the spot**. That source is the initializer for a regular local variable, the element type for enhanced `for`, or the target type for a lambda.

## 7. Common Compile Errors and How to Fix Them

| Invalid Example | Cause | How to Fix |
| --- | --- | --- |
| `var x;` | No initializer to infer the type | `int x;` or `var x = 0;` |
| `var x = null;` | The null literal does not determine a concrete type | `String x = null;` or `var x = (String) null;` |
| `var x = {1, 2};` | Short array initializer has no target type | `var x = new int[]{1, 2};` |
| `var f = x -> x + 1;` | Lambda needs a target functional interface | `IntUnaryOperator f = x -> x + 1;` |
| `var x = x;` | No valid value available to use inside its own initializer | Initialize from an independent expression, e.g. `var x = 1;` |
| `var a = 1, b = 2;` | Cannot declare multiple variables in a single local `var` declarator | Split into `var a = 1; var b = 2;` |
| `var x = 1; x = "one";` | `x` was already inferred as `int` | Choose a different type right at the declaration if needed |

In addition, `var` **cannot be used as a method return type, a class field, or a regular method parameter type**. This is a syntactic position restriction, independent of whether an initializer expression exists.

## 8. When to Write `var`, When to Write an Explicit Type?

**Prefer `var`** when the initializer expression makes the type clear enough:

~~~java
var names = new java.util.ArrayList<String>();
var length = "Java".length();
~~~

**Prefer an explicit type** when you need to leave a variable unassigned until data is available, want to deliberately choose an interface/superclass as the variable type, or want a target type to help infer generics:

~~~java
String name;
name = readName();

java.util.List<String> names = new java.util.ArrayList<>();
~~~

With `var list = new java.util.ArrayList<>();`, the diamond `<>` does not receive an element constraint from a variable type on the left, so this case infers `ArrayList<Object>`. Write `ArrayList<String>` in the initializer or use `List<String>` on the left if you want to constrain elements to String.

`var` is a tool to reduce type-name repetition; **it should not be used to obscure hard-to-understand types**. The variable name, initializer method, and data type should work together so readers can deduce the type accurately.

## 9. Self-Check Exercises

1. **Missing initializer:** Why does `var score;` fail to compile while `int score;` is valid?  
   *Answer:* `int` supplies a static type; `var` needs an initializer to infer the type of a regular local variable.
2. **Null:** How does `var text = null;` differ from `var text = (String) null;`?  
   *Answer:* The first has no concrete type to infer; the second infers `String` from the cast, even though the value is null.
3. **Method returning null:** Given `static String f() { return null; }`, is `var x = f();` valid?  
   *Answer:* Yes. The static type of the call expression `f()` is `String`.
4. **Cannot use later values:** Is `var x; x = 5;` valid?  
   *Answer:* No; type inference must occur at the declaration, not by looking up types from subsequent assignments.
5. **Two literals:** What types do `var n = 10;` and `var n = 10L;` have respectively?  
   *Answer:* `int` and `long`.
6. **Enhanced for:** What type does `for (var c : "ABC".toCharArray())` infer for `c` even without `= initializer`?  
   *Answer:* `char` from the array's element type.
7. **Lambda:** Why is `BinaryOperator<Integer> add = (var a, var b) -> a + b;` valid?  
   *Answer:* The target type `BinaryOperator<Integer>` supplies the parameter types.

## Checklist

- [ ] `var` is for **static type inference**, not dynamic typing.
- [ ] For regular local variable declarations, `var` **requires an initializer expression** in the same statement.
- [ ] `var x = null` is invalid; `var x = (String) null` or a method call returning `String` can be valid.
- [ ] The type is inferred from **the expression's type**, not from runtime values or later assignments.
- [ ] Do not use short array initializers, bare lambdas, or bare method references without a target type.
- [ ] Enhanced `for` infers the type from elements; lambdas infer parameter types from the target functional interface.
- [ ] Write an explicit type if you want to declare first and assign later, or need to control the interface/generic target type.

**Conclusion:** `var` requires an initializer expression in regular local variable declarations because the compiler **must infer the type right at the declaration site**. When another context supplies type information (enhanced `for`, lambdas), Java has specific rules; what never changes is that **`var` always participates in the static type system**, never waiting for runtime data to guess a type.
# Allowed Positions for `var` in Java 17+

> **Java core — language-basics / Inference with var**  
> **Requirements:** JDK 17+; standalone examples without external Java libraries.  
> **Goal:** Know the exact places where `var` is allowed and where it is forbidden, why the compiler infers the type at compile time, and how to choose `var` without hurting code readability.

## 1. `var` Is Local Type Inference, Not Dynamic Typing

Since **Java 10**, Java allows writing `var` in certain local variable declarations instead of an explicit type name:

~~~java
var count = 3;          // The compiler infers int.
var title = "Java";     // Infers String.
var price = 12.5;       // Infers double.
~~~

The type is **inferred at compile time** from the initializer expression (or from a valid loop/lambda context), and is then **fixed**. You cannot assign an arbitrary different type to the same variable:

~~~java
var count = 3;
// count = "three"; // Compile error: count has type int, not String.
~~~

`var` is **not** the name of an actual data type, is not `Object` by default, and does not provide a “dynamic typing” mechanism. Java does not allow `var` everywhere a type name can be written.

## 2. List of Allowed Positions

| Position | Valid Example | How Is the Type Determined? |
| --- | --- | --- |
| Local variable with initializer in a method | `var number = 42;` | From the expression `42` → `int` |
| Local variable in a constructor or initializer block | `var text = "ok";` | From the initializer expression → `String` |
| Initializer section of a traditional `for` loop | `for (var i = 0; i < 3; i++)` | From `0` → `int` |
| Element variable in an enhanced `for` loop | `for (var item : names)` | From the element type of the array/`Iterable` |
| Resource variable in `try-with-resources` | `try (var reader = new StringReader("hi"))` | From the resource object being initialized |
| **Lambda** parameters with `var` | `(var a, var b) -> a + b` | From the lambda's *target functional interface*; supported since **Java 11** |

For regular local variables, **an initializer is required**. Enhanced `for` infers the type from the iterated element; lambdas infer from the target type (for example `BiFunction<Integer, Integer, Integer>`). These are specific valid syntactic forms, not “allowing `var` variables arbitrarily everywhere”.

### Local Variables Inside a Block

~~~java
void print() {
    var message = "Hello"; // Local String.
    {
        var active = true;  // Local boolean inside a nested block.
        System.out.println(message + active);
    }
}
~~~

Similarly, inside a **constructor body**, a `static { ... }` block, or an instance initializer block `{ ... }`, you can use `var` to declare a **local variable** belonging to that block. However, **fields** of a class must still be declared with a concrete type.

## 3. `var` in Both Kinds of `for` Loops

### Traditional `for` Loop

~~~java
for (var i = 0; i < 3; i++) {
    System.out.println(i);
}
~~~

`i` is inferred as `int` from `0` and has scope matching the loop construct. `i` never automatically changes type as its value increases.

### Enhanced `for` Over an Array or Collection

~~~java
String[] fruits = {"cam", "tao"};
for (var fruit : fruits) {
    System.out.println(fruit); // fruit has type String.
}
~~~

You can also use `for (var element : list)` with a collection that has a specific element type. **`var` does not inspect the runtime type of each individual object**: the compiler infers the static element type from the array declaration or the declared element type of the `Iterable`.

If a collection is declared as `List<Object>`, then `var element` is inferred as `Object`, even if some elements are actually `String` at runtime. Therefore, choosing the generic type of a collection still matters greatly.

## 4. `var` in `try-with-resources`

A resource variable in `try-with-resources` can be declared with `var` if the initializer expression has a valid resource type (implementing `AutoCloseable`):

~~~java
import java.io.StringReader;

try (var reader = new StringReader("AB")) {
    System.out.println((char) reader.read()); // A
}
~~~

`reader` is inferred as `StringReader`, which has the `read()` method. Upon leaving the `try` block, `close()` is called automatically per the `try-with-resources` mechanism.

**Do not confuse** `var` with the resource requirement: only objects whose type conforms to `AutoCloseable` can be declared as a resource. `try (var number = 10) { ... }` is **invalid** because `int` is not a closeable resource.

## 5. `var` in Lambda Parameters — Java 11 and Later

When a lambda has a clear **target type**, starting in Java 11 you can use `var` for **all** parameters:

~~~java
import java.util.function.BiFunction;

BiFunction<Integer, Integer, Integer> add =
        (var left, var right) -> left + right;
System.out.println(add.apply(4, 5)); // 9
~~~

Here the compiler knows the lambda must implement `BiFunction<Integer, Integer, Integer>`, so `left` and `right` each have type `Integer` (and `+` automatically unboxes them to add). `var` does not infer a lambda's type out of thin air: a lambda **still needs a target type**.

Valid ways to write two parameters:

~~~java
BiFunction<Integer, Integer, Integer> a = (x, y) -> x + y;
BiFunction<Integer, Integer, Integer> b = (var x, var y) -> x + y;
BiFunction<Integer, Integer, Integer> c =
        (Integer x, Integer y) -> x + y;
~~~

**Do not mix parameter declaration styles within the same lambda:**

~~~java
// DOES NOT COMPILE:
// BiFunction<Integer, Integer, Integer> bad = (var x, y) -> x + y;
// BiFunction<Integer, Integer, Integer> bad2 = (var x, Integer y) -> x + y;
~~~

If you use `var` for one lambda parameter, the remaining parameters must also use `var`. The `var` form is convenient when you need a valid annotation on a parameter while still letting the type be inferred, though in basic examples you can choose the simpler `(x, y) -> ...` syntax.

## 6. Positions Where `var` Is **Not** Allowed

| Position or Declaration Kind | Invalid Example | Reason |
| --- | --- | --- |
| Class field (including `static`) | `class A { var n = 1; }` | `var` is only supported in allowed local contexts |
| Method return type | `var getCount() { return 1; }` | The return type must be declared explicitly |
| Regular method parameter | `void send(var message) { }` | Not a lambda formal parameter |
| Constructor parameter | `A(var value) { }` | `var` cannot be used in constructor parameter declarations |
| `catch` parameter | `catch (var ex) { }` | An exception type is required |
| Uninitialized local variable | `var n;` | There is no information to infer a type |
| Initialized only with `null` | `var value = null;` | `null` is not enough to infer a type |
| Multiple variables in one statement | `var a = 1, b = 2;` | A declaration using `var` may only declare one variable |
| Array initializer without `new` | `var data = {1, 2};` | There is no target type for this initializer |
| Self-reference in the initializer | `var n = n + 1;` | A valid type cannot be inferred from the variable itself being declared |

**How to fix:**

~~~java
int n;                         // No initializer needed here.
String value = null;           // Explicit type if null is wanted initially.
var typedNull = (String) null; // Valid: type String comes from the cast.
var data = new int[] {1, 2};  // Valid: inferred type is int[].
var a = 1;                     // One variable per var declaration.
var b = 2;
~~~

The case `var typedNull = (String) null;` is valid in terms of **type-inference syntax**, but in real applications you should consider whether null makes sense. Do not cast merely to avoid an explicit type declaration.

## 7. Runnable Java 17+ Example

Create a file named **VarAllowedPlacesDemo.java** containing the entire program:

~~~java
import java.io.IOException;
import java.io.StringReader;
import java.util.ArrayList;
import java.util.function.BiFunction;

public final class VarAllowedPlacesDemo {
    public static void main(String[] args) throws IOException {
        var language = "Java";
        var count = 2;
        var names = new ArrayList<String>();
        names.add("An");
        names.add("Binh");

        System.out.println("local=" + language + ":" + count);

        for (var index = 0; index < names.size(); index++) {
            System.out.println("index=" + index + ":" + names.get(index));
        }

        for (var name : names) {
            System.out.println("each=" + name);
        }

        try (var reader = new StringReader("OK")) {
            var first = (char) reader.read();
            var second = (char) reader.read();
            System.out.println("resource=" + first + second);
        }

        BiFunction<Integer, Integer, Integer> plus =
                (var left, var right) -> left + right;
        System.out.println("lambda=" + plus.apply(4, 5));

        var scores = new int[] {3, 7};
        System.out.println("array=" + (scores[0] + scores[1]));

        var typedNull = (String) null;
        System.out.println("typedNull=" + (typedNull == null));
    }
}
~~~

Open a terminal in the directory containing the file (Bash, PowerShell, or Command Prompt) and run:

~~~bash
javac -encoding UTF-8 VarAllowedPlacesDemo.java
java VarAllowedPlacesDemo
~~~

**Exact expected output:**

~~~text
local=Java:2
index=0:An
index=1:Binh
each=An
each=Binh
resource=OK
lambda=9
array=10
typedNull=true
~~~

The `var` positions demonstrated:

1. `language`, `count`, `names`, `scores`, and `typedNull` are **local variables with initializers**.
2. `index` is declared in the initializer section of a traditional `for` loop.
3. `name` is the element variable of an enhanced `for` loop, inferred as `String` from `ArrayList<String>`.
4. `reader` is a `try-with-resources` resource, inferred as `StringReader`.
5. `left` and `right` are lambda parameters (valid since Java 11).
6. `typedNull`'s value is null, but its **inferred type is String** due to the cast; this contrasts with `var typedNull = null;`, which is invalid.

## 8. When Should You Use `var` to Keep Code Readable?

`var` reduces type repetition, but it is optional. Use it when **the type is obvious from the initializer** or context:

~~~java
var reader = new StringReader("Hi"); // StringReader type is obvious.
var count = 0;                        // int type is obvious.
~~~

Consider an explicit type when the initializer does not clearly state its meaning or can easily be misinferred:

~~~java
var result = calculate();       // To know result's type, you must check what calculate() returns.
double result2 = calculate();   // Shows the expected type immediately.
~~~

Pay special attention to the generic diamond:

~~~java
var list = new ArrayList<>();        // Usually infers ArrayList<Object>.
var strings = new ArrayList<String>(); // Element type String is explicit.
~~~

If you want the API type to be `List<String>` instead of the concrete class `ArrayList<String>`, you can write `List<String> names = new ArrayList<>();`. `var` does not choose an abstraction for you.

**`var` does not replace type analysis**: you still need to watch whether a numeric literal is `int`/`long`/`double`, the generic type of the initializer, and the type conversions Java may perform.

## 9. Self-Check Exercises

**Exercise 1.** Mark valid/invalid: `var x = 1;`, `var y;`, `var z = null;`, `var a = new int[]{2, 3};`, `var b = {2, 3};`.

**Exercise 2.** Convert the loop `for (int i = 0; i < 5; i++)` to use `var`. What is the inferred type? When does the variable leave scope?

**Exercise 3.** Given an `ArrayList<String>` with two elements, write an enhanced `for` loop using `var` to print each element. What is the static type of the element variable?

**Exercise 4.** Use `try (var reader = new StringReader("A"))` to read a character. Why must the resource type implement `AutoCloseable`?

**Exercise 5.** Declare a `BiFunction<Integer, Integer, Integer>` using a lambda with two `var` parameters. Then try changing one parameter to `Integer` and explain the compile error.

### Takeaway

`var` can be used in **local variables with initializers**, **the initializer section of `for`**, **enhanced `for` variables**, **`try-with-resources` resource variables**, and **lambda parameters** (since Java 11). `var` **cannot** be used as a field type, return type, method/constructor parameter, `catch` parameter, or local variable lacking inference data. The type is still locked at **compile time**; prioritize source-code clarity.
# `var` Infers Local Variable Type from the Initializer Expression — Java 17+

Since Java 10, `var` lets **the compiler infer the static type of a local variable** from its initializer expression. This is a declaration syntax feature: `var` does not create a new data type, does not make Java a dynamically typed language, and does not change a variable's type across subsequent assignments.

~~~java
var count = 10;        // int count = 10;
var title = "Java";    // String title = "Java";
var active = true;     // boolean active = true;
~~~

## 1. The Compiler Reads the Type of the Right-Hand Expression

When encountering `var name = expression;` in an allowed position, the compiler inspects `expression`, determines its type, and then uses that type to check every subsequent statement. The compiler does not run the program to observe values and does not infer backward from assignments after the declaration.

| Initializer Expression | Inferred Static Type | Things to Note |
| --- | --- | --- |
| `10` | `int` | An integer literal without a suffix is usually `int` |
| `10L` | `long` | `L` selects a `long` literal |
| `2.5` | `double` | A floating-point literal defaults to `double` |
| `"Java"` | `String` | The string type is clear |
| `Integer.valueOf(7)` | `Integer` | The declared return type of the method |
| `new int[]{1, 2}` | `int[]` | The array creation expression carries a concrete type |
| `java.util.List.of("A", "B")` | `List<String>` | The generic type parameter is inferred from the arguments |
| `new java.util.ArrayList<String>()` | `ArrayList<String>` | Both the implementation class and element type are explicit |

With `var count = 10;`, the compiler accepts `count = 20;` but rejects `count = "20";`. Replacing `var` with `int` in the same declaration does not change type checking.

## 2. Standalone Runnable Example on JDK 17+

Save the program as **`VarInferenceDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public final class VarInferenceDemo {
    private static String findTitle(boolean found) {
        return found ? "Guide" : null;
    }

    public static void main(String[] args) {
        var copies = 3;                         // int
        var language = "Java";                  // String
        var labels = List.of("red", "blue");     // List<String>
        var editable = new ArrayList<String>(); // ArrayList<String>
        editable.add(labels.get(0));
        // editable.add(7); // Compile error: String required.

        var total = 0;                          // int
        for (var value : new int[]{2, 4, 6}) { // value is int
            total += value;
        }

        var title = findTitle(false);           // String, value is null
        // copies = "many"; // Compile error: copies is int.

        System.out.println("copies=" + copies);
        System.out.println("language=" + language);
        System.out.println("labels=" + labels);
        System.out.println("editable=" + editable);
        System.out.println("total=" + total);
        System.out.println("titleIsNull=" + (title == null));
    }
}
~~~

In the directory containing the file, run:

~~~bash
javac --release 17 -encoding UTF-8 VarInferenceDemo.java
java VarInferenceDemo
~~~

Output:

~~~text
copies=3
language=Java
labels=[red, blue]
editable=[red]
total=12
titleIsNull=true
~~~

In the program above, `findTitle` is declared to return `String`, so `title` has static type `String` **even when its actual value is `null`**. The `for` loop infers the element type from the `int[]` array; meanwhile, the `List.of` call and the `ArrayList<String>` constructor carry generic type information at compile time.

## 3. The Expression Must Express the Type You Actually Want

`var` infers from **the current initializer**; the compiler does not use subsequent statements to guess a collection's element type:

~~~java
var mixed = new ArrayList<>();    // ArrayList<Object>
mixed.add("red");
mixed.add(7);                     // Valid for ArrayList<Object>.

var names = new ArrayList<String>();
names.add("red");
// names.add(7);                  // Invalid: String required.
~~~

If you need the static type to be an interface, write that type on the left-hand side:

~~~java
List<String> otherNames = new ArrayList<>();
~~~

In this declaration, `List<String>` expresses the desired abstraction level and provides the target type for the diamond `<>`. With `var`, the variable's type in the previous example is `ArrayList<String>`; it does not automatically become `List<String>` even though the class implements that interface.

## 4. Boundaries for Reading the Next Lessons

- **Static type checking:** `var` still obeys assignments, overloads, generics, and method/field access; in-depth examples are in the lesson “var preserves static type checking”.
- **Declaration positions:** `var` applies to valid local positions, loops, resources, and lambda parameters according to their own rules; it cannot be used as a field type or return type.
- **Inference sources:** a regular local `var` requires an initializer; `var x;` is invalid. `var x = null;` and `var a = {1, 2};` are also invalid, whereas `var a = new int[]{1, 2};` is valid.
- **Numeric expressions:** `var ratio = 5 / 2;` receives `int` with value `2`. Integer division happens before inference; the lesson on literals and numeric operations explains promotion, casting, and overflow.
- **Readability:** an initializer with enough type information for the compiler is not necessarily clear enough for human readers. Sometimes `List<String> names = ...` communicates intent better.

The rules above all stem from one point: **`var` takes the type of the expression at the declaration site, and then Java applies its normal type system**.

## 5. Self-Check

1. What types do `var n = 1; var m = 1L;` infer? **Answer:** `int`, `long`.
2. Why does `var x = Integer.valueOf(7);` not infer `int`? **Answer:** `valueOf` returns `Integer`.
3. Does `var list = new ArrayList<>();` automatically infer `ArrayList<String>` from `list.add("A")`? **Answer:** No; here it is `ArrayList<Object>`.
4. Is `var value = findTitle(false);` valid if the method returns `String` but the value is `null`? **Answer:** Yes, the static type from the method signature is `String`.
5. If you want the variable to have the interface type `List<String>` instead of the class `ArrayList<String>`, how should you write it? **Answer:** `List<String> names = new ArrayList<>();`.

**Takeaway:** Determine the type of the initializer expression, verify whether the inferred type matches your intent, and use an explicit declaration when doing so helps readers understand faster.

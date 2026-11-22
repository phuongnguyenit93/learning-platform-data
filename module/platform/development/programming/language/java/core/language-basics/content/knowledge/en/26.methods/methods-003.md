# Distinguishing Formal Parameters and Arguments — Java 17+

## 1. Two Concepts in Two Different Places

When **defining** a method, the variables declared in the list inside parentheses are **formal parameters**. When **calling** the method, the expressions providing data in the corresponding positions are **arguments**.

~~~java
static int add(int left, int right) { // left, right: formal parameters.
    return left + right;
}

int result = add(2, 3);              // 2, 3: arguments of the call.
~~~

- `left` and `right` are declared with type `int` **in the method definition**.
- `2` and `3` are two **argument expressions** at the call `add(2, 3)`.
- On the call, the value of `2` is passed to parameter `left`; the value of `3` to `right`.
- `return left + right;` produces the **return result**, not a new parameter or argument.

**Exact stdout**, if the result is printed with `System.out.println(result);`:

~~~text
5
~~~

Vietnamese terminology can express these as “tham số” and “đối số”; in this document **formal parameter** is always used for the variable on the declaration side, and **argument** for the value/expression on the call side.

## 2. Quick Comparison

| Characteristic | Formal parameter | Argument |
|---|---|---|
| Where does it appear? | Parameter list of a method or constructor declaration | Expression list of a call |
| Example | `int price` in `cost(int price)` | `20` in `cost(20)` |
| Has a type declaration? | Yes, such as `String name` | An expression with an inferred/known type; not a parameter declaration |
| Who chooses it? | The method author | Caller can pass any literal, variable, or expression |
| Lifetime/scope | Inside the method body per Java scope rules | The expression belongs to the code where the call is written |
| Usable by the method? | Yes, by parameter name | The argument value has been transferred to the parameter |
| Relationship | Receives a value from the corresponding call position | Provides a value to initialize the corresponding parameter |

Example:

~~~java
static void welcome(String guest, int times) {
    for (int i = 0; i < times; i++) {
        System.out.println("Hello " + guest);
    }
}

String person = "Lan";
int count = 2;
welcome(person, count);
~~~

At the call site, **`person` and `count` are argument expressions**, not formal parameters. Only **`guest` and `times`** in the declaration of `welcome` are formal parameters. The caller's variable names **do not need to match** the parameter names. When running the snippet inside an appropriate `main`, stdout is:

~~~text
Hello Lan
Hello Lan
~~~

## 3. Positional Mapping, Count, and Types

With `static void display(String title, int score)`, the call:

~~~java
display("Java", 90);
~~~

has the mapping:

~~~text
Call:           display("Java", 90)
                         │      │
                         ▼      ▼
Declaration:    display(String title, int score)
                          title      score
~~~

The method receives each value by **position**. There is no named-call syntax like `display(score = 90, title = "Java")` as in some other languages; in Java this is not *named arguments*.

Common errors:

~~~java
// Illustrative definition:
static void display(String title, int score) { }

// display("Java");             // Missing int argument.
// display("Java", 90, 100);    // Too many arguments.
// display(90, "Java");         // Order/types do not match.
// display("Java", "90");       // String is not automatically an int.
~~~

Normally, the number of arguments must match the number of formal parameters, and argument types must be **compatible with parameter types under Java invocation conversion rules**. There are valid conversions such as `int` to `long`, boxing, or special handling for **varargs**; one should not conclude that types must always match verbatim textually.

Java does not automatically supply a “default value for a missing parameter” for a normal method. When you need a call with less data, you can use overloads or appropriate parameter design.

## 4. Arguments Do Not Have to Be Variables

An argument is an **expression**, so many forms are valid:

~~~java
static int square(int number) {
    return number * number;
}

int n = 4;
int a = square(3);          // Literal.
int b = square(n);          // Variable in caller.
int c = square(n + 1);      // Computed expression.
int d = square(square(2));  // Result of another call.
~~~

If `a`, `b`, `c`, `d` are printed in order, stdout is:

~~~text
9
16
25
16
~~~

In **every call** to `square(...)`, the formal parameter is still `int number`. Only the **argument value** at each call differs: `3`, `4`, `5`, `4`.

You can pass the return value of another method as an argument. A nested call needs to be evaluated to a value before the outer method uses it.

## 5. A Parameter Receives a Copy of the **Value of the Argument Expression**

Java is always **pass-by-value**. In a call `f(expression)`, `expression` is evaluated in the caller, and then its value is used to initialize a formal parameter variable:

~~~java
static void increase(int number) { number++; }
int original = 5;
increase(original);
System.out.println(original); // 5.
~~~

`original` is an **argument expression**, `number` is a **parameter**; because they are two separate variables, reassigning `number` does not change `original`.

For reference types, the copied value is a reference to an object. Two variables can point to **the same array**, allowing the method to modify the contents of the shared array:

~~~java
static void changeFirst(int[] values) { values[0] = 50; }
int[] data = {1, 2};
changeFirst(data);
System.out.println(java.util.Arrays.toString(data)); // [50, 2].
~~~

Reassigning `values = new int[]{99}` inside the method **does not** make the variable `data` point to the new array. This lesson emphasizes **parameter declaration vs. supplying arguments**; the lessons on pass-by-value and array parameters provide in-depth examples on object aliasing, `null`, copying, and mutation.


## 6. Parameters Are Local Variables of the Call

Parameters have scope inside the method body. Each time the method is called, the parameter value is used within **that execution**; it is not a global variable shared across all calls.

~~~java
static int addBonus(int score) {
    score += 5;
    return score;
}

int first = addBonus(10);
int second = addBonus(30);
System.out.println(first);
System.out.println(second);
~~~

**Exact stdout:**

~~~text
15
35
~~~

Renaming a parameter in the declaration, for example from `score` to `number`, does not force the caller to rename argument variables. Conversely, the caller can call `addBonus(first)`, `addBonus(10)`, or `addBonus(5 + 5)`.

Inside a method, you cannot declare another local variable **with the same name as a parameter** while the parameter is in scope:

~~~java
static void wrong(int n) {
    // int n = 3; // Compile error: duplicate variable name with parameter.
}
~~~

A parameter can shadow a class field; if inside an instance method and you need to access the field, use `this.score` to distinguish it from the `score` parameter.

## 7. `final` Parameters and Mutable Objects

A formal parameter can be declared `final`:

~~~java
static void print(final int number) {
    System.out.println(number);
    // number = 20; // Invalid: cannot reassign a final parameter.
}
~~~

With an array reference parameter:

~~~java
static void update(final int[] values) {
    // values = new int[2]; // Invalid: reassigning final parameter.
    values[0] = 7;          // Valid: mutates the referenced array object.
}
~~~

`final` applies to the **parameter variable**, does not automatically create a copy of the argument, and does not make the data inside the object immutable. When you do not want a method to mutate the caller's array, you can copy the array with `Arrays.copyOf` and operate on the copy, or avoid mutation.

## 8. Evaluation Order of Argument Expressions

In Java, argument expressions are evaluated in **left-to-right order**. The computed values are passed to the corresponding parameters when the call is performed.

~~~java
static int trace(String label, int value) {
    System.out.println("eval " + label + "=" + value);
    return value;
}

static int subtract(int left, int right) {
    return left - right;
}

int result = subtract(trace("left", 8), trace("right", 3));
System.out.println("result=" + result);
~~~

**Exact stdout:**

~~~text
eval left=8
eval right=3
result=5
~~~

The call `trace("left", 8)` is evaluated before `trace("right", 3)`. If an argument expression throws an exception preventing the call from continuing, subsequent argument expressions may **not be evaluated**.

In simple arithmetic examples without side effects, the order is easy to overlook; when arguments call methods that change state, understanding left-to-right order avoids wrong predictions.

## 9. Constructors and Varargs Still Use Parameter/Argument Rules

Constructors also have **formal parameters** in their declarations and receive **arguments** when using `new`:

~~~java
class Book {
    final String title;
    Book(String title) { this.title = title; }
}
Book book = new Book("Java"); // "Java" is the argument.
~~~

A parameter `int... values` (*varargs*) can accept many elements supplied by the caller, yet inside the method body `values` is **an `int[]` array variable**:

~~~java
static int sum(int... values) {
    int result = 0;
    for (int n : values) result += n;
    return result;
}
System.out.println(sum());           // 0.
System.out.println(sum(2, 3));       // 5.
System.out.println(sum(new int[]{4})); // 4.
~~~

Do not confuse **the number of argument expressions** in `sum(2, 3)` with **the number of formal parameters**: the declaration has only one `values`. The varargs/arrays lesson will examine calling styles, existing arrays, `null`, and overloading in detail.


## 10. Standalone Runnable Java 17+ Program

Create the file with the exact name **`ParametersArgumentsDemo.java`**:

~~~java
import java.util.Arrays;

public final class ParametersArgumentsDemo {
    private ParametersArgumentsDemo() {}

    static void welcome(String guest, int times) {
        for (int i = 0; i < times; i++) {
            System.out.println("Hello " + guest);
        }
    }

    static int add(int left, int right) {
        return left + right;
    }

    static int square(int number) {
        return number * number;
    }

    static void increasePrimitive(int value) {
        value++;
        System.out.println("inside primitive=" + value);
    }

    static void changeArray(int[] values) {
        values[0] += 10;
        System.out.println("inside array=" + Arrays.toString(values));
    }

    static void rebindArray(int[] values) {
        values = new int[]{99};
        System.out.println("inside rebound=" + Arrays.toString(values));
    }

    static void changeString(String text) {
        text = "B";
        System.out.println("inside string=" + text);
    }

    static int trace(String label, int value) {
        System.out.println("eval " + label + "=" + value);
        return value;
    }

    static int subtract(int left, int right) {
        return left - right;
    }

    static int sum(int... numbers) {
        int total = 0;
        for (int number : numbers) {
            total += number;
        }
        return total;
    }

    static void showVarargs(String tag, int... numbers) {
        System.out.println(tag + " values=" + Arrays.toString(numbers)
                + " sum=" + sum(numbers));
    }

    public static void main(String[] args) {
        int result = add(2, 3);
        System.out.println("add=" + result);

        String person = "Lan";
        int repeat = 2;
        welcome(person, repeat);

        System.out.println("literal square=" + square(3));
        System.out.println("expression square=" + square(2 + 2));
        System.out.println("nested square=" + square(square(2)));

        int original = 5;
        increasePrimitive(original);
        System.out.println("outside primitive=" + original);

        int[] data = {1, 2};
        changeArray(data);
        System.out.println("outside array=" + Arrays.toString(data));
        rebindArray(data);
        System.out.println("outside rebound=" + Arrays.toString(data));

        String originalText = "A";
        changeString(originalText);
        System.out.println("outside string=" + originalText);

        int difference = subtract(
                trace("left", 8), trace("right", 3));
        System.out.println("subtract=" + difference);

        showVarargs("empty");
        showVarargs("many", 3, 4);
        int[] existing = {4, 5};
        showVarargs("existing", existing);
    }
}
~~~

**Requirements:** JDK 17 or later; no external libraries beyond the JDK or preview features required.

**Bash (Linux/macOS):**

~~~bash
javac --release 17 -encoding UTF-8 ParametersArgumentsDemo.java
java -cp . ParametersArgumentsDemo
~~~

**PowerShell (Windows):**

~~~powershell
javac --release 17 -encoding UTF-8 .\ParametersArgumentsDemo.java
java -cp . ParametersArgumentsDemo
~~~

### Exact expected stdout

~~~text
add=5
Hello Lan
Hello Lan
literal square=9
expression square=16
nested square=16
inside primitive=6
outside primitive=5
inside array=[11, 2]
outside array=[11, 2]
inside rebound=[99]
outside rebound=[11, 2]
inside string=B
outside string=A
eval left=8
eval right=3
subtract=5
empty values=[] sum=0
many values=[3, 4] sum=7
existing values=[4, 5] sum=9
~~~

**Reading in order:** `add` pairs the two arguments `2,3` with the two parameters `left,right`; `welcome` receives arguments from **variables** rather than necessarily literals. Changing a primitive `value` inside a method does not change the caller's variable, whereas changing an element through an `int[]` parameter can change the object the caller holds. Reassigning the `values` parameter or `text` parameter does not change the caller's variable. The two `trace` expressions demonstrate left → right evaluation order. Varargs uses a single `int[]` parameter receiving flexible argument forms.

## 11. Common Confusions

| Confusion | Explanation / fix |
|---|---|
| Calling variable `n` in caller a “formal parameter” | At `f(n)`, `n` is an **argument expression** |
| Caller variable names must match parameter names | No; mapping is by **position** and type compatibility |
| Arguments are always literals | They can be variables, calculations, or method results |
| Changing an `int` parameter changes the caller's variable | Java passes primitive values by copy |
| Java passes arrays using pass-by-reference | Java copies the **reference value**; the referenced array can be mutated |
| Assigning `values = new int[...]` changes the caller's reference | Only reassigns the parameter variable |
| `return` is another parameter | A return value is the **result** returned by the method |
| Wrong argument count/order/types | The compiler requires the call to match the declaration/overload |
| Thinking `int... numbers` declares multiple parameters | It is **one** varargs parameter of array type inside the body |
| Assuming argument expressions always run simultaneously | Java evaluates from **left to right** |

## 12. Exercises and Answers

**A — Identify the positions:**

~~~java
static void printScore(String name, int score) {
    System.out.println(name + ":" + score);
}
printScore("An", 90);
~~~

**Answer:** `String name`, `int score` are two **formal parameters**; `"An"`, `90` are two **arguments**.

**B — Using caller variables:**

~~~java
int current = 10;
System.out.println(square(current + 1));
~~~

**Answer:** the argument is the entire expression `current + 1`, with value 11; stdout is **`121`**.

**C — Predict variable change:**

~~~java
static void setValue(int value) {
    value = 99;
}
int x = 7;
setValue(x);
System.out.println(x);
~~~

**Answer:** **`7`**, because the assignment affects parameter `value`, not variable `x`.

**D — Predict array change:**

~~~java
static void setFirst(int[] array) {
    array[0] = 99;
}
int[] a = {1};
setFirst(a);
System.out.println(a[0]);
~~~

**Answer:** **`99`**, because the method modifies an element on the **shared referenced array object**.

**E — With varargs:** How many formal parameters does `static int sum(int... numbers)` have?  
**Answer:** **one** (`numbers`), of array type `int[]` in the body. The call `sum(1,2,3)` provides three elements packaged for the varargs parameter.

## 13. Checklist and Conclusion

- [ ] Distinguish **formal parameter declarations** and **argument expressions** at the call site.
- [ ] Understand arguments are mapped by position to corresponding parameters.
- [ ] Know argument types/count must match the declaration, except for special rules like varargs.
- [ ] Know arguments can be literals, variables, expressions, or other calls.
- [ ] Understand Java is always **pass-by-value**, even when passing object/array reference values.
- [ ] Distinguish mutating an object via a parameter from reassigning the parameter variable.
- [ ] Understand parameters are local variables scoped to the call, separate from caller variables.
- [ ] Recognize `final` parameters and their limits.
- [ ] Know Java evaluates argument expressions left to right.
- [ ] Run `ParametersArgumentsDemo.java` with JDK 17+ and verify exact stdout.

**Conclusion:** **Formal parameters** are variables **declared** on the method side; **arguments** are expressions supplying values at the **call site**. Java passes argument values in order into corresponding parameters. For primitives, the value is copied; for arrays/objects, the **reference** value is copied — which is the key to understanding when a method can mutate data observed by the caller.
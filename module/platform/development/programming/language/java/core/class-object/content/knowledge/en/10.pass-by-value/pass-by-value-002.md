# Passing Primitive Values to Methods in Java

## Learning Objectives

After this lesson, you will be able to:

- Explain the rule that **Java always passes arguments by value** (*pass-by-value*) and apply that rule accurately to the eight primitive types.
- Distinguish between the **caller variable**, **argument expression**, and **parameter variable** in a method call.
- Predict the result when a method reassigns or increments/decrements a parameter of type `byte`, `short`, `int`, `long`, `float`, `double`, `char`, and `boolean`.
- Understand why a method cannot swap two **primitive variables of the caller** simply by swapping two parameters.
- Use a **return value** or an appropriate API design for the caller to explicitly update a variable, instead of expecting the method to modify an external primitive variable.
- Recognize the conversions allowed when passing primitive arguments, the impact of overloading, and common errors involving widening, narrowing, boxing, and unboxing.
- Distinguish between **evaluating the argument expression before the call** (which can have side effects on caller variables) and **reassigning the parameter inside the method**.
- Compile/run the Java 17+ examples yourself and explain stdout.

## 1. Core Principle: A Method Receives a Copy of the Value

Consider a method:

~~~java
static void change(int number) {
    number = 100;
}
~~~

This is an **illustrative method declaration** that must be placed in a Java class. The caller executes:

~~~java
int original = 10;
change(original);
System.out.println(original);
~~~

The result is **`10`**, not `100`.

When the program reaches the call `change(original)`:

1. Java evaluates the argument expression `original` and obtains **an `int` value equal to 10**.
2. Java initializes a **separate parameter variable** named `number` for this call, holding **a copy of the value 10**.
3. The method body runs. The statement `number = 100;` only changes the value of **the parameter variable `number`**, and does not reassign the caller's `original` variable.
4. The method finishes. The caller continues with `original` still equal to 10.

You can visualize it as follows:

~~~text
Caller:                      Callee: change(...)
int original = 10    --->    int number = 10  (copy of the value)
                               number = 100
                               return
Caller reads original: 10    The call's number variable has ended
~~~

**One-sentence takeaway:** *Passing a primitive variable to a method passes **the current value of the variable**, without granting permission to directly modify the caller variable itself.*

This is not an arbitrary rule of a compiler; it is Java language semantics. A method parameter has its own lifetime during the call. Multiple calls to the same method also have parameters for each execution, and do not share a global parameter variable.

### 1.1. Defining Three Terms

| Term | Example | Meaning |
| --- | --- | --- |
| **Caller variable** | `int original = 10;` | Where the caller stores the current value |
| **Actual argument** | `original` in `change(original)` | Expression evaluated to obtain a value |
| **Formal parameter** | `int number` in `change(int number)` | Variable initialized from the argument value when calling the method |

The caller variable name and the parameter name do not need to be the same. Even when they **have the same name**, they are still different variables in two separate scopes.

### 1.2. How Many Primitive Types Does Java Have?

Java's eight primitive types are:

| Type | Primary Data | Example Value |
| --- | --- | --- |
| `byte` | 8-bit signed integer | `(byte) 7` |
| `short` | 16-bit signed integer | `(short) 300` |
| `int` | 32-bit signed integer | `42` |
| `long` | 64-bit signed integer | `42L` |
| `float` | 32-bit floating-point number | `1.5f` |
| `double` | 64-bit floating-point number | `1.5d` |
| `char` | 16-bit unsigned UTF-16 code unit | `'A'` |
| `boolean` | Logical value | `true`, `false` |

All eight types are **passed by value**. For a primitive argument, the value passed is not an object or an object reference. According to Java's rules, an `int` does not "point to" the memory location of the caller's `int` variable.

## 2. Standalone Program: Reassigning Parameters Does Not Change the Caller

Save to the file **`PrimitivePassByValueDemo.java`**:

~~~java
public class PrimitivePassByValueDemo {
    static void changeInt(int number) {
        System.out.println("inside before=" + number);
        number = 100;
        System.out.println("inside after=" + number);
    }

    static void changeBoolean(boolean enabled) {
        enabled = !enabled;
        System.out.println("inside enabled=" + enabled);
    }

    static void changeChar(char letter) {
        letter = 'Z';
        System.out.println("inside letter=" + letter);
    }

    public static void main(String[] args) {
        int number = 10;
        boolean enabled = true;
        char letter = 'A';

        changeInt(number);
        System.out.println("outside number=" + number);

        changeBoolean(enabled);
        System.out.println("outside enabled=" + enabled);

        changeChar(letter);
        System.out.println("outside letter=" + letter);
    }
}
~~~

Compile/run with JDK 17 or later:

~~~bash
javac PrimitivePassByValueDemo.java
java PrimitivePassByValueDemo
~~~

**Exact stdout:**

~~~text
inside before=10
inside after=100
outside number=10
inside enabled=false
outside enabled=true
inside letter=Z
outside letter=A
~~~

Analysis:

- `changeInt(number)` receives a copy of `10` and assigns `100` inside the method. The caller still has `number == 10`.
- `changeBoolean(enabled)` receives a copy of `true` and flips it to `false`. This does **not** change `main`'s `enabled` variable.
- `changeChar(letter)` receives a copy of the character `'A'` and assigns `'Z'`; the caller still keeps `'A'`.

There are no exceptions just because `boolean` or `char` differs from the integer group. They are also primitive values, so the parameter is initialized from the argument value and any parameter assignment only affects the parameter variable.

## 3. Distinguishing Modifying a Parameter from Updating a Caller Variable via a Return Value

If you want the caller to change the `number` variable to a new value, the clear approach is to **return the result from the method**, and then have **the caller explicitly reassign it**:

~~~java
static int doubled(int value) {
    return value * 2;
}

// In main or another method:
int number = 7;
number = doubled(number);
~~~

After the statement `number = doubled(number);`, the caller has `number == 14`. The `doubled` method does not secretly modify any external variable. It simply computes the result from the copy of the parameter and **returns an `int` value**. It is the caller's assignment `number = ...` that causes the caller variable to change.

### 3.1. Complete Runnable Example

Save **`ReturnPrimitiveDemo.java`**:

~~~java
public class ReturnPrimitiveDemo {
    static int addFive(int value) {
        value += 5;
        return value;
    }

    static boolean toggle(boolean value) {
        return !value;
    }

    static char nextChar(char value) {
        return (char) (value + 1);
    }

    public static void main(String[] args) {
        int score = 10;
        boolean active = true;
        char letter = 'A';

        addFive(score);
        System.out.println("ignored return=" + score);

        score = addFive(score);
        System.out.println("assigned return=" + score);

        active = toggle(active);
        System.out.println("active=" + active);

        letter = nextChar(letter);
        System.out.println("letter=" + letter);
    }
}
~~~

Commands:

~~~bash
javac ReturnPrimitiveDemo.java
java ReturnPrimitiveDemo
~~~

Output:

~~~text
ignored return=10
assigned return=15
active=false
letter=B
~~~

The key point lies in the two calls to `addFive(score)`:

- The first call computes `15` but **ignores the return value**; the caller's `score` remains `10`.
- The second call includes the assignment `score = ...`, so the caller receives and stores `15`.

Choose the right return type for the business logic. A `void` method can perform calculations and logging, but **cannot directly provide a primitive result** via `return value;`. If you want the caller to receive a result, you should generally design the method with an appropriate return type.

### 3.2. A Method Result Is a Value, Not a Variable Name

With `return value;` in a method returning `int`, Java returns **the value of the expression `value`**, not permission to modify the local/parameter variable named `value`. The caller receives a value compatible with the return type.

If the caller writes `int result = addFive(10);`, then `result` is a new variable. There is no link by which a later assignment to the old parameter variable would cause `result` to change.

## 4. Why Does Swapping Two Primitive Parameters Not Swap Caller Variables?

A classic mistake:

~~~java
static void swap(int a, int b) {
    int temporary = a;
    a = b;
    b = temporary;
}
~~~

This method **swaps the values of the two local parameters** (`a`, `b`) within the call, but does not swap the caller's primitive variables.

Save **`PrimitiveSwapDemo.java`**:

~~~java
public class PrimitiveSwapDemo {
    static void swap(int a, int b) {
        int temporary = a;
        a = b;
        b = temporary;
        System.out.println("inside swap=" + a + "," + b);
    }

    static int[] swappedValues(int a, int b) {
        return new int[] {b, a};
    }

    public static void main(String[] args) {
        int first = 3;
        int second = 8;

        swap(first, second);
        System.out.println("outside swap=" + first + "," + second);

        int[] values = swappedValues(first, second);
        first = values[0];
        second = values[1];

        System.out.println("after assignment=" + first + "," + second);
    }
}
~~~

Compile/run:

~~~bash
javac PrimitiveSwapDemo.java
java PrimitiveSwapDemo
~~~

Output:

~~~text
inside swap=8,3
outside swap=3,8
after assignment=8,3
~~~

**Why does `swappedValues` work?** The method receives two primitive values and returns a **new array containing the two swapped values**. The caller reads the array elements and then assigns them to `first` and `second`. This is an API that **returns a result**, not a method that directly modifies two primitive variables of the caller.

In this example, the array is merely one way to pass **two results** back to the caller; it is an object and has its own reference semantics. In real-world design, a clearly named record/value type may be more appropriate than an array whose positional meanings are hard to tell.

### 4.1. Is It Possible to Swap via a Method Call and Change Caller Variables?

With **only two primitive parameters passed by value**, the method has no reference path back to **the caller's local variables themselves**. However, a method can modify a **field**, an **array element**, or a mutable object passed in via a reference; that is **a different mechanism** and does not turn Java into pass-by-reference for local variables.

Do not confuse the two goals:

- **Changing the value of a local variable `int x` in the caller**: requires the caller to reassign it or handle control flow appropriately.
- **Changing the state of an object to which the caller also holds a reference**: can be done via an object method/field/array; that is not directly swapping primitive local variables.

## 5. Each Call Has Its Own Parameters

Even when calling the same method multiple times, the parameter name inside is not a "single shared variable".

~~~java
static void printAfterIncrement(int n) {
    n++;
    System.out.println(n);
}
~~~

In the same caller method:

~~~java
int x = 4;
printAfterIncrement(x);
printAfterIncrement(x);
System.out.println(x);
~~~

If run, the output is:

~~~text
5
5
4
~~~

In **each call**, the parameter `n` starts with a copy of the current value of `x`, which is `4`. After `n++` prints `5`, that call finishes. The next call receives `4` again, and does not "remember" the value of `n` from the previous call. The variable `x` still keeps `4`.

### 5.1. Recursion Does Not Share a Single Parameter Either

Save **`RecursivePrimitiveDemo.java`**:

~~~java
public class RecursivePrimitiveDemo {
    static void descend(int n) {
        System.out.println("enter=" + n);
        if (n > 0) {
            descend(n - 1);
        }
        System.out.println("exit=" + n);
    }

    public static void main(String[] args) {
        int start = 2;
        descend(start);
        System.out.println("main=" + start);
    }
}
~~~

Run:

~~~bash
javac RecursivePrimitiveDemo.java
java RecursivePrimitiveDemo
~~~

Output:

~~~text
enter=2
enter=1
enter=0
exit=0
exit=1
exit=2
main=2
~~~

Each recursive call has its own value of the parameter `n`: 2, 1, then 0. When the calls return, each frame continues printing the value of `n` **of that specific call**. Therefore, the output goes down 2 → 1 → 0, and then goes back up 0 → 1 → 2.

The example also shows that passing `start` into the method does not automatically change `start` in `main`.

## 6. Type Conversions When Passing Primitive Values

Saying "passing a copy of the value" does not mean **the argument type always matches the parameter type exactly**. Before the body runs, the compiler checks **method invocation conversion**, and Java may perform a valid conversion.

For example:

~~~java
static void printLong(long value) {
    System.out.println(value);
}

// Inside a method:
int number = 12;
printLong(number); // Valid: int -> long
~~~

Here, the caller provides an expression of type `int` with value 12. The method expects `long`; Java allows **primitive widening** (`int` → `long`). The parameter `value` receives a **corresponding `long` value**, independent of the caller's `number` variable.

If the body writes `value = 1000L;`, then the caller still has `number == 12`.

### 6.1. Common Primitive Widening Conversions

| Source Type | Valid Target Widening Types |
| --- | --- |
| `byte` | `short`, `int`, `long`, `float`, `double` |
| `short` | `int`, `long`, `float`, `double` |
| `char` | `int`, `long`, `float`, `double` |
| `int` | `long`, `float`, `double` |
| `long` | `float`, `double` |
| `float` | `double` |
| `double` | No wider primitive type |
| `boolean` | Does not widen to or from numeric types |

Some widening conversions from large integers to float/double may **lose representational precision** due to rounding. "Widening" describes a category of permitted type conversions, not a guarantee of preserving every bit or every mathematical value.

**There is no** primitive widening from `int` → `byte`, `int` → `short`, `double` → `float`, or `char` → `short`.

### 6.2. An `int` Literal Is Not Automatically Narrowed Just Because It Fits in the `byte` Range

Consider:

~~~java
static void acceptByte(byte n) {
    System.out.println(n);
}

// In the caller:
// acceptByte(10);        // Error: int does not automatically narrow to byte
byte value = 10;
acceptByte(value);       // Valid: already a byte
acceptByte((byte) 10);   // Valid: explicit cast
~~~

This is an illustrative snippet when placed in an appropriate class/method. A confusing point is that **variable assignment** `byte value = 10;` has a special rule for integer constants within the range of the smaller type, whereas **a method call** does not automatically apply `int` → `byte` narrowing just to find a matching parameter.

The cast `(byte) 10` is intentional, but you should not cast arbitrarily. For example, `(byte) 130` gives a value other than 130 due to the 8-bit limit. To avoid business logic bugs, choose a parameter type that accurately reflects the range of values to accept.

### 6.3. The `char` Type Is Also a Primitive

~~~java
static void printCode(int code) {
    System.out.println(code);
}

// In the caller:
char c = 'A';
printCode(c); // Valid: char -> int, prints 65
~~~

A `char` represents a **UTF-16 code unit**, which does not always represent a complete Unicode character. The `char` → `int` widening gives the corresponding integer value of that code unit. This is neither passing a reference nor creating a new String.

### 6.4. Boolean Does Not Become a Number

If a method accepts `int`, the call `f(true)` is invalid unless there is a matching `f(boolean)` overload. Java does **not** implicitly convert `true` to `1` or `false` to `0`.

## 7. Program on Primitive Widening and Overloading

Save **`PrimitiveConversionsDemo.java`**:

~~~java
public class PrimitiveConversionsDemo {
    static void showLong(long number) {
        System.out.println("long=" + number);
        number = 999L;
    }

    static void showDouble(double number) {
        System.out.println("double=" + number);
    }

    static void showByte(byte number) {
        System.out.println("byte=" + number);
    }

    static String choose(long number) {
        return "chosen long";
    }

    static String choose(Integer number) {
        return "chosen Integer";
    }

    static void showCodePointUnit(int code) {
        System.out.println("code=" + code);
    }

    public static void main(String[] args) {
        int value = 12;
        showLong(value);
        System.out.println("caller=" + value);

        float decimal = 1.5f;
        showDouble(decimal);

        byte small = 10;
        showByte(small);
        showByte((byte) 20);

        char letter = 'A';
        showCodePointUnit(letter);

        System.out.println(choose(7));
        System.out.println(choose(Integer.valueOf(7)));
    }
}
~~~

Run:

~~~bash
javac PrimitiveConversionsDemo.java
java PrimitiveConversionsDemo
~~~

Output:

~~~text
long=12
caller=12
double=1.5
byte=10
byte=20
code=65
chosen long
chosen Integer
~~~

Explanation:

- `showLong(value)` uses `int` → `long` widening. After the method assigns `number = 999L` to its own parameter, the caller still keeps `value == 12`.
- `showDouble(decimal)` uses `float` → `double` widening. `1.5f` has an exact binary representation, so when printed here it is `1.5`.
- `showByte(small)` directly passes a variable of type `byte`; `showByte((byte) 20)` uses an explicit cast.
- `showCodePointUnit(letter)` receives the `int` corresponding to the UTF-16 code unit of `'A'`, which is 65.
- For `choose(7)`, the argument `7` has type `int`: the overload `choose(long)` applies via primitive widening **in the strict phase**, before boxing to `Integer` is needed.
- For `choose(Integer.valueOf(7))`, the static type of the argument is already `Integer`, so the matching-type overload `choose(Integer)` applies directly.

The two overloads are only meant to illustrate **the rule for selecting a matching method**, and do not alter the **pass-by-value** principle. After selecting the overload, each method still receives its own parameter variable.

### 7.1. Order of Considering Primitive Widening and Boxing in Overloading

At a high level, Java evaluates overloads in phases:

1. **Strict invocation**: checks fixed arity with conversions that do not require boxing/unboxing, such as identity, primitive widening, and reference widening.
2. **Loose invocation**: if the previous phase has no applicable method, additionally considers boxing/unboxing and permitted combinations.
3. **Variable arity**: if there is still no applicable method, considers varargs calls with a variable number of arguments.

Therefore, primitive widening can be chosen **before** boxing if a suitable overload appears in the first phase. However, when there are multiple candidates within a phase, the compiler must apply the **most-specific** rule; one should not generalize that "primitive always beats wrapper".

For example, `Integer n = 7;` when passed to a method that only accepts `long` can be **unboxed `Integer` → `int` and then widened → `long`**. The unboxing happens before the parameter receives the value and can throw `NullPointerException` if the wrapper is `null`.

### 7.2. Pass-by-Value Still Holds with Unboxing/Boxing

In the call `accept(Integer.valueOf(7))` with an `int` parameter, Java can unbox the wrapper object to obtain **the primitive value 7** to pass into the parameter. A method modifying the `int` parameter also does not modify the `Integer` object or the caller's wrapper variable.

Conversely, if a method accepts `Integer` and you pass an `int` variable, Java may box it before passing the **reference value** to the wrapper object. The `Integer` wrapper is immutable; however, that is **passing a reference-type parameter by value**, not passing a local primitive variable by reference.

## 8. Argument Expression Evaluation Order Differs from Modifying a Parameter

A subtle point: before entering the method body, Java **evaluates the argument expressions**. If an argument expression itself modifies a caller variable, the caller can change **before the method begins**, but that is not because the method modified a parameter variable.

For example:

~~~java
static void printValues(int first, int second) {
    System.out.println(first + "," + second);
}

// In the caller:
int x = 3;
printValues(x++, x);
System.out.println(x);
~~~

Result when run:

~~~text
3,4
4
~~~

Explanation:

1. Java evaluates the first argument `x++`: the expression provides **the old value 3**, while incrementing **the caller's `x` variable** to 4.
2. Java evaluates the second argument `x`: obtaining the value 4.
3. The method's two parameters `first` and `second` receive **copies of the values 3 and 4**.
4. The method body prints `3,4`. After the method finishes, the caller prints `4`, because the expression `x++` itself incremented x earlier.

**Make this distinction very clear:**

- `method(x)` where the method reassigns the parameter: the caller **does not change** due to the assignment inside the method.
- `method(x++)`: the caller **can change**, due to the side effect of the **argument expression** evaluated in the caller before the method runs.
- `x = method(x)`: the caller **can change**, due to the **caller's assignment after the method returns**.

### 8.1. Complete Program on Argument Order

Save **`PrimitiveArgumentOrderDemo.java`**:

~~~java
public class PrimitiveArgumentOrderDemo {
    static void show(int first, int second, int third) {
        first = 100;
        System.out.println("method values=" +
                first + "," + second + "," + third);
    }

    public static void main(String[] args) {
        int x = 2;
        show(x++, ++x, x);
        System.out.println("caller x=" + x);
    }
}
~~~

Commands:

~~~bash
javac PrimitiveArgumentOrderDemo.java
java PrimitiveArgumentOrderDemo
~~~

Output:

~~~text
method values=100,4,4
caller x=4
~~~

Sequence of events:

- `x++` passes the value 2, then changes x to 3.
- `++x` changes x to 4 before returning the second argument value of 4.
- The third argument reads the current x, which is 4.
- `show` receives `(2,4,4)`, but the statement in the body `first = 100;` changes the **copy parameter** and then prints `100,4,4`.
- The caller still keeps x equal to 4.

Java specifies left-to-right evaluation order for arguments. However, code with multiple `++` operators in a single call is **hard to read**; in real programs, consider extracting them into intermediate variables.

### 8.2. What If an Argument Expression Throws an Exception?

If an argument expression throws an exception, the method call may not be executed. Argument expressions that completed earlier may already have had side effects; they do not automatically roll back. This is a property of evaluation order, independent of how the method passes parameters by value.

## 9. `final` with Primitive Parameters

You can declare a primitive parameter with the `final` modifier:

~~~java
static int addOne(final int value) {
    // value++; // Invalid: cannot reassign a final parameter
    return value + 1;
}
~~~

When a parameter is `final`, the compiler prevents **reassigning the parameter variable**; the method is still allowed to **read** and use that value for calculations.

If not declared `final`, Java allows `value++` inside the method body, but that change only applies to the **parameter variable** and still does not modify the caller variable.

**Do not confuse:**

- `final int x`: prevents reassigning the numeric value in variable x after it has been validly assigned.
- `final SomeObject obj`: prevents reassigning the reference variable obj, and does **not** automatically make the referenced object immutable.

A primitive parameter has no internal object to "mutate", so `final` here focuses entirely on parameter reassignment.

### 9.1. Effectively Final and Lambdas

A primitive parameter that is not declared `final` but is **never reassigned** can be **effectively final**. This matters when a lambda or a local/anonymous class captures the parameter.

For example:

~~~java
static Runnable makeTask(int number) {
    return () -> System.out.println(number);
}
~~~

This is a valid illustrative method in a class with the corresponding imports/syntax. `number` is captured by the lambda because it is effectively final. If you reassign `number` inside the method and still capture it, the compiler will report an error under the rule that a captured variable must be final or effectively final.

This does not change pass-by-value: `number` is initialized from **the caller's primitive value**, and using it inside the lambda does not grant permission to modify the caller's local variable.

## 10. Impact on Fields and Caller Local Variables

Suppose a class has a `total` field:

~~~java
class Meter {
    int total = 10;

    void change(int value) {
        value = 99;  // Only changes the parameter.
    }
}
~~~

Calling `meter.change(meter.total)` does **not** change the field `meter.total`; the method only receives the current value of the field.

To update the field, the method needs a statement that **writes to the field**, or it must return a result for the caller to assign:

~~~java
class Meter {
    int total = 10;

    void increaseBy(int amount) {
        total += amount;      // Actually writes to the instance field
    }

    int doubled(int value) {
        return value * 2;
    }
}
~~~

In `increaseBy(5)`, the `total` field changes because the method body **accesses and assigns to the field** of the receiving object; **not** because the parameter `amount` holds a reference to a field in the caller.

### 10.1. Program Illustrating Direct Field Assignment

Save **`PrimitiveFieldDemo.java`**:

~~~java
public class PrimitiveFieldDemo {
    private int score = 10;

    void changeCopy(int score) {
        score = 99;
        System.out.println("parameter=" + score);
    }

    void changeField(int amount) {
        this.score += amount;
    }

    public static void main(String[] args) {
        PrimitiveFieldDemo exam = new PrimitiveFieldDemo();

        exam.changeCopy(exam.score);
        System.out.println("field after copy=" + exam.score);

        exam.changeField(5);
        System.out.println("field after update=" + exam.score);
    }
}
~~~

Run:

~~~bash
javac PrimitiveFieldDemo.java
java PrimitiveFieldDemo
~~~

Output:

~~~text
parameter=99
field after copy=10
field after update=15
~~~

`changeCopy(int score)` declares a parameter with the same name as the field; `score = 99` is an assignment to the **parameter**, not to the field. If you want to write to the field, you must use `this.score` or another explicit field access. `changeField` uses `this.score += amount`, so it modifies the object's actual data field.

This is the link between **pass-by-value** and **shadowing**: two variables with the same name do not become one variable, and Java does not automatically bind a parameter to a field.

## 11. Special Primitive Values: Overflow, Floating-Point, and Boolean

Pass-by-value guarantees **the independence of the parameter variable**, not that operations on values are always mathematically intuitive.

### 11.1. Integer Overflow

Java uses finite signed integers for `byte`, `short`, `int`, and `long`. An operation can overflow without automatically reporting an error for ordinary operators such as `+`.

~~~java
static int plusOne(int value) {
    return value + 1;
}
~~~

If `plusOne(Integer.MAX_VALUE)` is called, the `int` result is **`Integer.MIN_VALUE`** due to integer overflow rules. The caller is still not modified by the method body, but the **return value** may not fit the business logic.

If reporting an error instead of overflowing is required, you can use `Math.addExact(value, 1)` with the appropriate type to receive an `ArithmeticException` on overflow.

### 11.2. `float` and `double` Have NaN and Infinity

IEEE 754 floating-point types have values such as `NaN`, `POSITIVE_INFINITY`, and `NEGATIVE_INFINITY`. Methods pass/receive them by value, but comparisons can be surprising:

~~~java
static boolean same(double left, double right) {
    return left == right;
}
~~~

For `Double.NaN`, the expression `Double.NaN == Double.NaN` is `false`. This is a floating-point comparison rule, **not** the method passing an argument incorrectly or losing the parameter.

`float` → `double` is a valid widening conversion, but the printed decimal output may look different from the literal you expected, because some decimal fractions cannot be represented exactly in binary. For example, the value `0.1f`, when widened to double, still contains the precision of **the original float value**, and does not turn into an exact mathematical `0.1`.

### 11.3. Regarding `boolean`

A method can use a `boolean` to compute a new boolean and return it. However, the method cannot make the caller's boolean variable change by writing `flag = !flag;` on the parameter. If you want the caller to receive the negated value, return a boolean and have the caller assign `flag = toggle(flag);`.

## 12. Boxing/Unboxing: The Intersection Between Primitives and References

Although this lesson focuses on primitive values, wrapper types such as `Integer`, `Long`, `Boolean`, `Character`, etc. frequently appear in Java code.

- **Boxing** converts a primitive value into an appropriate wrapper reference according to language rules.
- **Unboxing** extracts a primitive value from a wrapper reference.
- Standard wrapper classes such as `Integer` are **immutable**.

For example:

~~~java
static void consumeInt(int value) {
    value++;
}

// In the caller:
Integer boxed = Integer.valueOf(5);
consumeInt(boxed); // Unboxes to int 5 before passing
~~~

`consumeInt` receives an **`int` parameter with value 5**. The `value++` operation in the method does not change the `boxed` variable and also does not "modify the contents of the Integer object".

If `boxed` is `null`, unboxing before calling the method throws a `NullPointerException`; the method does not execute normally. This differs from a primitive variable, which cannot hold `null`.

A common mistake is thinking Java will automatically convert `int` → `long` → `Long` in a call expecting `Long`. Such a chain of **primitive widening followed by boxing** is **not** a generally permitted automatic method invocation conversion. You must use the literal `5L`, an expression of type `long`, or an intentional explicit conversion.

## 13. Common Mistakes

| Misconception or Mistake | Explanation/How to Handle |
| --- | --- |
| "Passing an `int` to a method passes the address of the int variable." | Java passes a **numeric value**; the parameter is a different variable. |
| "Reassigning a parameter inside a method changes the caller's local variable." | False; the method only reassigns the parameter. Return the result and let the caller assign it if you want a change. |
| "`swap(int a,int b)` will swap the two external variables." | False; it only swaps the two copy parameters. |
| "If the caller sees a change after `f(x++)`, the method modified x." | Wrong cause: **the argument `x++`** modified x before the method ran. |
| "If a method returns `int` without assigning the result, the caller updates automatically." | False; you must assign the result or use it at the call site. |
| "Calls to the same method share a single parameter variable." | False; each execution has its own parameter binding. |
| "`final int x` prevents the method from reading x." | False; `final` only prevents reassigning the parameter. |
| "`int` to `long` when calling is pass-by-reference." | False; that is a type conversion of the value, which is then passed by value. |
| "The literal `10` can be passed automatically to `byte` if it fits in the byte range." | Method invocation does not automatically narrow `int` → `byte`; use an appropriate type/cast. |
| "Passing an `Integer` into an `int` method mutates the object when the parameter is incremented." | False; unboxing creates a primitive value, and the wrapper is not mutated. |
| "`Integer null` unboxes to 0." | False; unboxing null throws `NullPointerException`. |
| "`float` to `double` always fixes all decimal inaccuracies." | False; the original float value already has precision limits. |
| "Modifying an instance field through a method proves Java passes primitives by reference." | False; the field changes because the method has a field assignment statement, not because the parameter aliases the field. |
| "A method cannot have side effects if it only receives primitive arguments." | False; a method can modify fields, static state, perform I/O, or call other methods. Only the **primitive parameters** do not represent caller variables. |
| "`boolean` or `char` has a separate passing mechanism." | No; all eight primitive types follow the pass-by-value mechanism. |

## 14. How to Quickly Analyze Any Primitive Call

When you see `result = compute(x, y);`, ask yourself in order:

1. **What are the static types of `x` and `y`?** Are they primitive? For example, `int`, `double`.
2. **What is the argument expression?** `x` only reads, whereas `x++` or `x = 7` can change the caller's variable immediately during evaluation.
3. **Which method does the compiler select?** Check parameter types/order/count and valid conversions.
4. **What is the actual value passed into each parameter?** If widening/unboxing occurs, examine the conversion before the body runs.
5. **What does the method do with the parameter?** `parameter++` only changes the parameter variable; it does not change locals/fields on the caller side because the parameter carries the same **old value**.
6. **Does the method modify other state?** If the method body uses `this.field++` or a static field, that is a side effect independent of the primitive passing mechanism.
7. **Is there a return value?** If so, does the caller use `x = method(x)` to update x?
8. **Is there overflow, NaN, null-unboxing, or an exception?** These can affect the result or cause the call to fail, but they do not turn pass-by-value into pass-by-reference.

If you draw a diagram, draw a **separate box for the parameter**; do not draw an arrow saying "the `int` parameter points to the caller's `int` variable". Both boxes may hold the same number 5 at the start, but they **are not the same variable**.

## 15. Quick Distinction from Passing an Object

Java only has **pass-by-value** even when the parameter type is a reference type. However, in that case, the "copied value" is the **reference value**, which can point to the same object as the caller; the method can modify a mutable object through that reference.

Illustrative example:

~~~java
static void changeInt(int value) {
    value = 99;
}

static void changeArray(int[] values) {
    values[0] = 99;
}
~~~

Caller:

~~~java
int n = 1;
int[] data = {1};

changeInt(n);
changeArray(data);

System.out.println(n);       // 1
System.out.println(data[0]); // 99
~~~

The final lines differ **not** because Java has two parameter-passing modes. With `changeInt`, the parameter holds a copy of **the integer 1**; reassigning it does not modify n. With `changeArray`, the parameter holds a copy of **the reference to the array**, so `values[0] = 99` modifies **the array object itself** that the caller is also referencing.

If the `changeArray` method writes `values = new int[]{99};`, reassigning this parameter reference also does **not** change the caller's `data` variable.

The current lesson emphasizes the primitive case; the array example here is only to prevent the misconception that Java has a separate pass-by-reference mode for objects.

## 16. Exercises with Answers

### Exercise 1. Reassigning a Parameter

~~~java
static void f(int n) {
    n = 40;
}
~~~

If the caller writes `int a = 4; f(a);`, what is `a` equal to after the call?  
**Answer:** 4. The method only reassigns parameter `n`.

### Exercise 2. Incrementing a Parameter

~~~java
static void increase(int n) {
    n++;
}
~~~

The caller uses `int count = 9; increase(count);`. What is `count`?  
**Answer:** 9. The `n++` operation only changes the call's parameter.

### Exercise 3. Returning a Result

~~~java
static int increase(int n) {
    return n + 1;
}
~~~

The caller writes `int count = 9; count = increase(count);`. What is the result?  
**Answer:** 10. It is the caller's assignment statement that receives the return value.

### Exercise 4. Swap

Method `swap(int a, int b)` swaps two parameters. The caller has `int x = 1, y = 2; swap(x, y);`. What are x/y afterward?  
**Answer:** `x == 1`, `y == 2`. The two caller variables are not reassigned.

### Exercise 5. Argument with Side Effects

Caller: `int x = 1; f(x++);`, where `f(int value)` simply prints value. What are the printed value and the value of x after the call?  
**Answer:** The method prints 1, and the caller has x = 2. The side effect of `x++` occurs **before** the method body.

### Exercise 6. Boolean

~~~java
static void deactivate(boolean active) {
    active = false;
}
~~~

Caller: `boolean active = true; deactivate(active);`. What is active equal to in the caller?  
**Answer:** `true`. The parameter is initialized from a copy of `true`.

### Exercise 7. Char

~~~java
static void change(char ch) {
    ch = 'Z';
}
~~~

Caller `char letter = 'A'; change(letter);`. What is letter equal to in the caller?  
**Answer:** `'A'`.

### Exercise 8. Widening

A method only has a `long` parameter. The caller has a variable `int value = 5;`; is calling `f(value)` valid, and does it modify value?  
**Answer:** Valid due to `int` → `long` widening. The method receives the corresponding `long` value; modifying the parameter does not modify the variable `value`.

### Exercise 9. Narrowing a Literal

A method only has `f(byte n)`. Is `f(5)` automatically valid because 5 is within the byte range?  
**Answer:** No. The literal `5` defaults to `int`; method invocation does not automatically narrow to `byte` just because the value is small.

### Exercise 10. Two Calls

Caller `int x = 3; f(x); f(x);`; the body of `f(int n)` just does `n++` and prints n. What are the two printed outputs, and what is x equal to afterward?  
**Answer:** Prints 4 then 4; x is still 3. Each call receives a copy of the value 3.

### Exercise 11. A Field Differs from a Parameter

In an instance method with the statement `this.counter += amount;`, can the field change?  
**Answer:** Yes. The method **directly assigns to the instance field**. That does not mean `amount` is a reference to a caller primitive variable.

### Exercise 12. Null Integer

A method accepts `int n`, and the caller passes a variable `Integer boxed = null;`. What error can occur?  
**Answer:** `NullPointerException` when unboxing `boxed` to prepare the primitive argument, before entering the method body.

### Exercise 13. Float and Double

A method accepts `double`, and the caller passes `float f = 0.1f;`. Is this valid, and is the decimal number guaranteed to become exact 0.1?  
**Answer:** Valid due to `float` → `double`. However, widening does not restore decimal precision already lost in the float value.

### Exercise 14. StringBuilder vs. int

Why can a method call `builder.append("X")`, causing the caller to see the object change, whereas `n = 99` on an `int` parameter does not change the caller's variable?  
**Answer:** With `StringBuilder`, the parameter holds a copy of the **reference** to the same mutable object, so the method modifies that object. With `int`, the parameter only holds a copy of the number; reassigning the parameter does not modify the external variable. Both are still pass-by-value.

## References

- Java Language Specification, [`4.2 — Primitive Types and Values](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.2): the eight primitive types and values.
- Java Language Specification, [`8.4.1 — Formal Parameters](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.4.1): formal parameter declarations.
- Java Language Specification, [`15.12.4 — Run-Time Evaluation of Method Invocation](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.12.4): argument evaluation and transferring control into a method.
- Java Language Specification, [`5.3 — Method Invocation Contexts](https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html#jls-5.3): valid type conversions when passing arguments.

## Conclusion

In Java, **all arguments are passed by value**. When passing a primitive value such as `int`, `double`, or `boolean`, the method receives **a copy of the value** in a separate parameter variable. Reassigning or incrementing the parameter **does not automatically change the caller's primitive variable**; this remains true even if the two variables have the same name, the method makes recursive calls, or a widening type conversion occurs.

If you want the caller to store a new value, **return the result and let the caller assign it**, or design an explicit state-updating operation when the business logic genuinely requires it. Do not confuse changes caused by **the argument expression `x++`**, modifying a **field inside the method body**, or mutating a **mutable object via a reference** with Java passing primitive variables by reference. Understanding this distinction helps predict code accurately and avoid bugs when building Java APIs.

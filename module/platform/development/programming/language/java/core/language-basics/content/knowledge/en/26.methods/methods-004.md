# `static` Methods for Introductory Java Programs

> **Java core — language-basics / Methods**  
> **Environment:** JDK 17+, single standalone Java file, no external libraries needed.  
> **Objective:** Create and call `static` methods from `main`; use parameters, return values, or `void`; understand why `static` belongs to a class, how it differs from instance methods, and when not to overuse static state.

## 1. `static` Means the Method Belongs to the Class

A method with the `static` keyword is attached to the **class**, and can be called without creating an instance of the class:

~~~java
public final class MathHelper {
    public static int add(int left, int right) {
        return left + right;
    }
}

// Can be called as MathHelper.add(3, 4), returning 7.
~~~

Main parts:

| Declaration part | In the example | Role |
| --- | --- | --- |
| Modifiers | `public static` | Allows calling from accessible places without an object |
| Return type | `int` | Result of the addition |
| Method name | `add` | Name used at the call site |
| Parameters | `int left, int right` | Accepts two arguments of type int |
| Body | `{ return left + right; }` | Statements executed and result returned |

General form: `[access] static ReturnType name(Type parameter, ...) { ... }`. The `[...]` markers in the descriptive line only denote optional parts, **not Java syntax** to type.

Do not assume “static” means a method only runs once or cannot take parameters: every call executes the body with the supplied arguments. `static` only determines **how the method belongs to the class and accesses members**.

## 2. `main` Is the Most Familiar `static` Method

For a Java 17 program run directly from the CLI, the standard entry point:

~~~java
public static void main(String[] args) {
    System.out.println(add(2, 3));
}
~~~

Meaning:

- `public`: allows the Java launcher to access the entry point.
- `static`: the launcher calls `main` **without creating an object** of the enclosing class.
- `void`: the method does not return a value to the caller; program output is observed via printing or other effects.
- `main`: the entry-point method name in this standard form.
- `String[] args`: array receiving CLI arguments; the variable name can differ from `args`.

When `add` is a valid static method in the same class, you can call it directly as `add(2, 3)`. The more explicit form is `ClassName.add(2, 3)`; using the class name is generally recommended when calling static methods from outside.

~~~java
public final class Starter {
    private static int add(int a, int b) {
        return a + b;
    }

    public static void main(String[] args) {
        System.out.println("sum=" + add(2, 3));
        System.out.println("qualified=" + Starter.add(4, 5));
    }
}
~~~

Compiling/running with class `Starter` requires the file `Starter.java` when the class is `public`. `main` does not run automatically from merely being declared; it is invoked by the launcher when executing `java Starter`.

## 3. Parameters, Return Types, and `void` Work as Normal

`static` does not change parameter and return-value rules:

~~~java
static double average(int a, int b) {
    return ((double) a + b) / 2;
}

static boolean isEven(int number) {
    return number % 2 == 0;
}

static void greet(String name) {
    if (name == null || name.isBlank()) {
        System.out.println("hello=guest");
        return; // Ends early because the method returns void.
    }
    System.out.println("hello=" + name.trim());
}
~~~

- `average(5, 2)` returns `3.5`. Casting `(double) a` before adding/dividing preserves the fractional part and avoids adding two `int`s before converting types.
- `isEven(8)` returns `true`; `isEven(7)` returns `false`.
- `greet(" Lan ")` prints `hello=Lan`; `greet(null)` prints `hello=guest`.
- A method with a non-`void` return type must provide an appropriate value on all normally completing paths. A `void` method can use `return;`, but cannot return a value such as `return 5;`.

**Distinction:** Numbers, strings, or variables placed in parentheses **at the call site** are *arguments*; typed variables declared **in the method definition** are *parameters*. Java passes arguments **by value**, even when that value is an object reference.

## 4. Calling a `static` Method in the Same Class or Another Class

Within the same class, calling without the class name is often easier to read:

~~~java
static int square(int n) {
    return n * n;
}

static int squarePlusOne(int n) {
    return square(n) + 1; // Calls another static method.
}
~~~

When calling a static method of **another class**, use the class name. Familiar examples in the JDK:

~~~java
int bigger = Math.max(4, 9);           // 9
String text = Integer.toString(42);   // "42"
~~~

`Math.max` and `Integer.toString` are static methods: no need for `new Math()` or `new Integer(...)`. Java has a `static import` mechanism to omit the class name, but in introductory lessons it is better to keep `Math.max(...)` so the method's origin is clear.

Not every method in an application has to be static. Choose static when the behavior can work solely through parameters or appropriate class resources, without depending on the state of a specific object.

## 5. Limitation: No `this` and No Direct Instance Access

An instance method runs with a current object and can use `this`. A static method **has no implicit `this` object**:

~~~java
public final class Multiplier {
    private final int factor;

    public Multiplier(int factor) {
        this.factor = factor;
    }

    public int multiply(int value) { // Instance method.
        return factor * value;
    }

    public static int triple(int value) { // Static method.
        return value * 3;
    }
}
~~~

Valid calls:

~~~java
Multiplier item = new Multiplier(4);
System.out.println(item.multiply(3));       // 12.
System.out.println(Multiplier.triple(3));   // 9.
~~~

Inside a static method, you cannot use `this.factor` or call `multiply(3)` directly when there is no suitable object:

~~~java
// DOES NOT COMPILE:
// static int wrong(int n) {
//     return factor * n; // factor is an instance field.
// }
// static int wrongThis(int n) {
//     return this.factor * n; // 'this' does not exist in a static context.
// }
~~~

If you genuinely need to call an instance method from a static method, you must **have an object** (for example, receive it via a parameter or create one with `new`), then call `item.multiply(3)`.

| Criterion | `static` method | Instance method |
| --- | --- | --- |
| Belongs to | Class | Object |
| Recommended call form | `Type.method(args)` | `object.method(args)` |
| Requires an instance of the class to call? | No | Yes |
| Can use `this` directly? | No | Yes |
| Accesses instance fields directly? | No | Yes, on the current object |
| Calls other static members? | Yes | Yes |

A constructor is an object creation/initialization mechanism, **not a static method**, and declares no return type.

## 6. `static` Fields: Shared State and Pitfalls While Learning

You can declare a class-level field shared across multiple static method calls:

~~~java
static int callCount = 0;

static int recordCall() {
    callCount++;
    return callCount;
}
~~~

In a normal program run, two consecutive calls to `recordCall()` return `1` then `2`. The state **does not reset to 0 on each call** because `callCount` is a class field, not a local variable of the method.

However, mutable static state makes results depend on call history and makes testing harder. When multiple threads modify `callCount++`, this operation **is not automatically thread-safe**. For introductory programs, prefer static methods that take parameters and return clear results:

~~~java
static int calculateTotal(int price, int quantity) {
    return price * quantity;
}
~~~

That calculation still risks `int` overflow for large values; appropriate types or checks are needed in real applications. `static final` is suitable for **immutable constants by contract** (for example, `static final int MAX_RETRIES = 3;`), though `final` on a reference to a mutable object does not make the object itself immutable.

## 7. Standalone Runnable Java 17+ Program

Create the file **StaticMethodsIntroDemo.java**:

~~~java
public final class StaticMethodsIntroDemo {
    private static int callCount = 0;

    private final int factor;

    public StaticMethodsIntroDemo(int factor) {
        this.factor = factor;
    }

    public int multiply(int value) {
        return factor * value;
    }

    private static int add(int left, int right) {
        return left + right;
    }

    private static double average(int a, int b) {
        return ((double) a + b) / 2;
    }

    private static boolean isEven(int n) {
        return n % 2 == 0;
    }

    private static String category(int n) {
        if (n < 0) {
            return "NEG";
        }
        if (n == 0) {
            return "ZERO";
        }
        return "POS";
    }

    private static void greet(String name) {
        if (name == null || name.isBlank()) {
            System.out.println("hello=guest");
            return;
        }
        System.out.println("hello=" + name.trim());
    }

    private static int recordCall() {
        callCount++;
        return callCount;
    }

    public static void main(String[] args) {
        System.out.println("add=" + add(3, 4));
        System.out.println("qualifiedAdd="
                + StaticMethodsIntroDemo.add(5, 6));
        System.out.println("average=" + average(5, 2));
        System.out.println("even8=" + isEven(8));
        System.out.println("even7=" + isEven(7));

        System.out.println("negative=" + category(-2));
        System.out.println("zero=" + category(0));
        System.out.println("positive=" + category(9));

        greet(" Lan ");
        greet(null);

        System.out.println("mathMax=" + Math.max(4, 9));
        System.out.println("callOne=" + recordCall());
        System.out.println("callTwo=" + recordCall());

        StaticMethodsIntroDemo first = new StaticMethodsIntroDemo(3);
        StaticMethodsIntroDemo second = new StaticMethodsIntroDemo(10);
        System.out.println("instanceOne=" + first.multiply(4));
        System.out.println("instanceTwo=" + second.multiply(2));
        System.out.println("classCounter=" + StaticMethodsIntroDemo.callCount);
    }
}
~~~

Compile and run in the directory containing the file (Bash, PowerShell, or Command Prompt):

~~~bash
javac -encoding UTF-8 StaticMethodsIntroDemo.java
java StaticMethodsIntroDemo
~~~

**Exact expected stdout:**

~~~text
add=7
qualifiedAdd=11
average=3.5
even8=true
even7=false
negative=NEG
zero=ZERO
positive=POS
hello=Lan
hello=guest
mathMax=9
callOne=1
callTwo=2
instanceOne=12
instanceTwo=20
classCounter=2
~~~

The two `add` calls show that static methods can be called directly or via the class name. `instanceOne` and `instanceTwo` differ because the two objects have different `factor` values. `callOne`/`callTwo` and `classCounter` illustrate a shared static field within the same run.

## 8. Common Mistakes, Exercises, and Checklist

| Mistake / misconception | How to handle |
| --- | --- |
| Thinking `new` is required to call a static method | Call `Type.method(...)` or directly within the same class |
| Using `this` inside a static method | There is no `this`; an object is needed to access instance state |
| Calling an instance method from `main` without an object | Create/obtain an object then call `object.method(...)` |
| Thinking static runs only once | Every call executes the method body |
| Thinking a local variable inside static persists across calls | Local variables are created per call; static fields belong to the class |
| Using mutable static fields for every intermediate result | Prefer parameters + return to avoid shared state |
| Forgetting `return value;` in an `int`-returning static method | All normally completing branches must return a value of the right type |
| Using `void` and trying to read a result from the call expression | `void` provides no value to assign |

**Exercise 1.** Write `static int cube(int n)` and call it from `main` with `n = 3`. Predict the result.

**Exercise 2.** Write `static boolean isAdult(int age)` returning true when `age >= 18`. Print results for ages 17, 18, and 21.

**Exercise 3.** Write `static void printIfPresent(String value)`: skip null or blank strings with `return;`, and print if it has content.

**Exercise 4.** Create a class with a `factor` field and an instance method `multiply`. Try calling it from `main` before/after creating an object; identify the compile error.

**Exercise 5.** Compare a local variable `int calls = 0` declared inside a method with a `static int callCount` field after two calls. Why do the results differ?

**Checklist:** Does the method genuinely not need `this` or an object's state? Are parameters/return type/`void` right? Do the class/file name and CLI commands match? Is there mutable static state causing coupling between calls?

### Key Takeaway

**`static` places a method at the class level**: well suited for `main` and small utility functions that take parameters and return results. Static methods have no `this` and cannot directly access instance members without an object. When per-object state is needed, use instance methods. Do not confuse a `static method` with a `static field`: static fields can hold **shared** state, so use them intentionally.
# Method Declaration: Name, Parameters, Return Type, and Body in Java

> **Java core — language-basics / Methods**  
> **Environment:** JDK 17+, single standalone file, no external libraries.  
> **Objective:** Declare and call methods yourself, clearly defining **name**, **parameter list**, **return type**, and **body**; understand `void`, `return`, variable scope, `static`, and instance methods.

## 1. Structure of a Method Declaration

A method is a named block of behavior defined inside a class, interface, or type that permits Java method declarations.

~~~java
public static int add(int left, int right) {
    int result = left + right;
    return result;
}
~~~

Parts in the declaration:

| Component | In the example | Meaning |
| --- | --- | --- |
| Modifiers | `public static` | Access level and whether it belongs to the class or an object |
| Return type | `int` | The result received by the caller |
| Method name | `add` | The identifier used to call the method |
| Formal parameters | `int left, int right` | Two variables that receive arguments on a call |
| Method body | `{ ... }` | The statements executed when the method is called |
| Value-returning termination statement | `return result;` | Returns the value and ends the call |

When calling `add(3, 4)`, the argument `3` is assigned to parameter `left` and `4` is assigned to `right`, so the method returns `7`. Merely **declaring** it does not run the body; the body is executed when there is a matching call.

General form:

~~~java
[modifiers] ReturnType methodName(Type1 parameter1, Type2 parameter2) {
    // statements
}
~~~

The square brackets in the illustrative line are **optional-notation markers**, not characters to type into Java. A declaration may have **no parameters**: `static String version() { return "17+"; }`. Normal non-abstract method kinds have a body inside `{ }`; `abstract` method declarations or declarations in interfaces may use a `;` instead of a body according to their own rules.

## 2. Naming and Choosing a Return Type

Method names follow Java identifier rules; the convention is **lowerCamelCase** with a verb or action-describing phrase such as `calculateTotal`, `findFirst`, `printReport`:

~~~java
static int square(int number) {
    return number * number;
}

static boolean isPositive(int number) {
    return number > 0;
}

static String title() {
    return "Java 17";
}
~~~

The return type can be a primitive (`int`, `boolean`, `double`...), a class (`String`), an array (`int[]`), an interface, or `void`.

- For a type other than `void`, `return expression;` must return a value **assignable** to the declared type; control-flow paths that complete normally must not be missing a result.
- For `void`, the method does not provide a return value; it can end with `return;` or reach the end of the body.
- `return` ends the **current method invocation**, and does not automatically end `main`, the caller's loop, or the entire JVM.

~~~java
static void announce(String text) {
    if (text == null) {
        return; // Ends the void method early.
    }
    System.out.println(text);
}
~~~

A `void` method cannot use `return 5;`; a method declared to return `int` cannot use `return "five";`.

## 3. Formal Parameters vs. Actual Arguments

~~~java
static double average(int a, int b) {
    return ((double) a + b) / 2;
}

// Inside main:
// double result = average(5, 2); // 3.5
~~~

`a` and `b` are **formal parameters** (*parameters*) in the declaration; `5` and `2` are **arguments** at the call site.

- Arguments correspond to parameters by **positional order** and must be type-compatible; `average(2, 5)` produces the same result here, but not every method is symmetric.
- In the declaration, **each parameter must state its type**: `int a, int b`, not `int a, b` when writing a method parameter list.
- You cannot use the same name for two parameters in the same declaration.
- Parameters are only in scope within the method body/allowed scope, not global variables.
- Java **passes arguments by value**: for primitives, the parameter receives a copy of the value; for objects, the parameter receives a copy of the **reference**.

~~~java
static void incrementLocal(int value) {
    value++;
}

// int count = 10;
// incrementLocal(count);
// count is still 10.
~~~

Reassigning a reference parameter does not change the caller's variable; however, calling a method that mutates a **shared mutable object** can cause the caller to observe the new state. This is still pass-by-value of the reference, not pass-by-reference of the variable.

## 4. Method Body, Local Variables, and Control Flow

The body is a block of statements `{ ... }`. It can declare local variables, check conditions, loop, call other methods, and return a result:

~~~java
static int clamp(int value, int min, int max) {
    if (min > max) {
        throw new IllegalArgumentException("min must not exceed max");
    }
    if (value < min) {
        return min;
    }
    if (value > max) {
        return max;
    }
    return value;
}
~~~

This method returns the number clamped to the range `[min, max]`. The `return` statements are in different branches; when execution reaches a `return`, the rest of the body does not run.

**Scope and initialization:**

~~~java
static int example(int input) {
    int doubled = input * 2; // Local variable.
    return doubled;
}
// doubled and input cannot be used directly outside the method.
~~~

A local variable must be **definitely assigned before it is read**. A declaration such as `int result; return result;` will not compile without a valid assignment path. You cannot declare **a method directly inside the body of another method**; place it as a member of a class or an appropriate type.

**Typical compile-time errors:**

~~~java
// WRONG: missing return for the case number <= 0.
// static int missingResult(int number) {
//     if (number > 0) return number;
// }

// WRONG: incompatible return type.
// static int wrongType() { return "Java"; }

// WRONG: declaring a nested method directly inside a method.
// static void outer() { int inner() { return 1; } }
~~~

## 5. `static` vs. Instance Methods

A `static` method belongs to the **class** and can be called using the class name. An **instance** method is associated with an object, so it is usually called through an object reference:

~~~java
public final class Counter {
    private int count;

    public Counter(int initial) {
        count = initial;
    }

    public void increase() { // Instance method.
        count++;
    }

    public int current() { // Instance method.
        return count;
    }

    public static int add(int a, int b) { // Static method.
        return a + b;
    }
}
~~~

How to call them (if the example class is placed in a valid file):

~~~java
Counter counter = new Counter(2);
counter.increase();
System.out.println(counter.current()); // 3
System.out.println(Counter.add(3, 4)); // 7
~~~

**Note:** `Counter(int initial)` is a **constructor**, because its name matches the class and it **has no return type**; it is not a `void` method. Conversely, `void Counter()` would be a method named `Counter`, not a constructor.

`static` cannot directly use instance fields via `this` when there is no object. In the runnable example at the end of the lesson, `main` is `static`; it calls static methods directly and creates an object before calling an instance method.

## 6. Method Signature, Overloading, and Varargs

For ordinary methods in a class, the **signature** is primarily distinguished by the **name and parameter types in order**. Parameter variable names and the return type are **not enough** to create another overload:

~~~java
static String describe(int number) {
    return "int:" + number;
}

static String describe(String text) {
    return "String:" + text;
}
~~~

The two methods sharing the name `describe` are **overloaded** because one takes an `int` and the other takes a `String`. The call `describe(12)` selects the `int` version; `describe("12")` selects the `String` version. The compiler uses the types at the call site to resolve overloads.

~~~java
// WRONG if static int add(int a, int b) already exists:
// static long add(int x, int y) { return x + y; }
// Changing only parameter names and return type does not create a valid overload.
~~~

If you need a variable number of `int` arguments, you can use **varargs**, which must be placed last in the parameter list:

~~~java
static int sumAll(int... values) {
    int sum = 0;
    for (int value : values) {
        sum += value;
    }
    return sum;
}

// sumAll(2, 3, 4) == 9; sumAll() == 0.
~~~

`int... values` works like an `int[]` array inside the body. You do not need to use varargs for every problem: a fixed number of parameters often keeps the contract simpler.

## 7. CLI Syntax and Runnable Java 17+ Program

Create the file **MethodDeclarationDemo.java**:

~~~java
public final class MethodDeclarationDemo {
    private final String prefix;

    // Constructor: no return type.
    public MethodDeclarationDemo(String prefix) {
        this.prefix = prefix;
    }

    // Instance method: requires an object to call.
    public String greet(String name) {
        if (name == null || name.isBlank()) {
            return prefix + "bạn";
        }
        return prefix + name.trim();
    }

    public static int add(int left, int right) {
        return left + right;
    }

    private static double average(int a, int b) {
        return ((double) a + b) / 2;
    }

    private static void announce(String label) {
        System.out.println("announce=" + label);
    }

    private static int clamp(int value, int min, int max) {
        if (min > max) {
            throw new IllegalArgumentException("min > max");
        }
        if (value < min) {
            return min;
        }
        if (value > max) {
            return max;
        }
        return value;
    }

    private static int lengthOrMinusOne(String value) {
        return value == null ? -1 : value.length();
    }

    private static void incrementLocal(int value) {
        value++; // Does not change the variable outside the method.
    }

    private static String describe(int number) {
        return "int:" + number;
    }

    private static String describe(String text) {
        return "String:" + text;
    }

    private static int sumAll(int... values) {
        int sum = 0;
        for (int value : values) {
            sum += value;
        }
        return sum;
    }

    public static void main(String[] args) {
        System.out.println("add=" + add(3, 4));
        System.out.println("average=" + average(5, 2));
        announce("GO");

        System.out.println("clampLow=" + clamp(-5, 0, 10));
        System.out.println("clampMiddle=" + clamp(6, 0, 10));
        System.out.println("clampHigh=" + clamp(18, 0, 10));

        System.out.println("length=" + lengthOrMinusOne("Java"));
        System.out.println("lengthNull=" + lengthOrMinusOne(null));

        MethodDeclarationDemo demo =
                new MethodDeclarationDemo("Xin chào, ");
        System.out.println("greet=" + demo.greet(" Lan "));
        System.out.println("greetBlank=" + demo.greet("  "));

        int counter = 10;
        incrementLocal(counter);
        System.out.println("afterCall=" + counter);

        System.out.println("describeNumber=" + describe(12));
        System.out.println("describeText=" + describe("12"));
        System.out.println("sumAll=" + sumAll(2, 3, 4));
        System.out.println("sumNone=" + sumAll());
    }
}
~~~

Compile and run in the directory containing the file, in Bash, PowerShell, or Command Prompt:

~~~bash
javac -encoding UTF-8 MethodDeclarationDemo.java
java MethodDeclarationDemo
~~~

**Exact expected stdout:**

~~~text
add=7
average=3.5
announce=GO
clampLow=0
clampMiddle=6
clampHigh=10
length=4
lengthNull=-1
greet=Xin chào, Lan
greetBlank=Xin chào, bạn
afterCall=10
describeNumber=int:12
describeText=String:12
sumAll=9
sumNone=0
~~~

`add`/`average` demonstrate accepting parameters and returning a value; `announce` is `void`. The three branches of `clamp` show multiple `return` paths; `greet` is an instance method with an implicit `this` reference via the `prefix` field. `afterCall=10` proves an `int` parameter does not modify the caller's variable. The two `describe` methods illustrate overloading, while `sumAll()` shows varargs can accept 0 arguments.

## 8. Common Mistakes and Exercises

| Mistake / misconception | How to fix |
| --- | --- |
| Forgetting the return type in a method declaration | Write `T` or `void`; only constructors omit a return type |
| Confusing parameters and arguments | Parameters go in the declaration; arguments are passed at the call site |
| Writing `static int add(int a, b)` | Specify every type: `int a, int b` |
| Missing `return` on a path of a value-returning method | Ensure every normally completing path returns a value |
| `return value;` in a `void` method | Use `return;` or omit return |
| Calling an instance method from `main` without an object | Create an object, then call via its reference |
| Trying to overload by changing only return type/parameter names | Change the parameter type list validly |
| Expecting to modify a caller's `int` variable by modifying a parameter | The parameter value is a copy; return the result and assign it in the caller |

**Exercise 1.** Write `static int multiply(int a, int b)` and call it in `main` with `3, 5`; record the exact return value.

**Exercise 2.** Write `static String category(int n)` returning `"NEG"`, `"ZERO"`, or `"POS"`, without missing any `return` path.

**Exercise 3.** Write `static void printIfNonBlank(String text)`, handling `null` and blank strings with `return;` and printing when valid.

**Exercise 4.** Create a class with an instance field, a constructor, and an instance method returning a value; compare how it is called with a `static` method.

**Exercise 5.** Write two overloads `format(int value)` and `format(double value)`. Explain why writing two methods with the same parameters but different return types is invalid.

**Exercise 6.** Use `int... values` to write a method that counts positive elements; test with zero arguments, one argument, and multiple arguments.

### Key Takeaway

**A method is defined by its name, parameters, return type, and body.** When called, arguments are passed by value into parameters. `return value;` provides a result for value-returning methods, whereas `void` returns no value. Use `static` when behavior belongs to the class, use instance methods when object state is needed, and clearly distinguish methods from constructors.
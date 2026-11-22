# `return` with a Value and `return` in `void` Methods — Java 17+

## 1. Core Rule

In Java, `return` **ends the current method call** and transfers control back to the caller. Whether a value can be returned depends on the **return type in the method declaration**.

| Method type | Valid statement | Meaning |
|---|---|---|
| `int`, `boolean`, `String`… | `return expression;` | Evaluates the expression, returns a value compatible with the declared type, and exits the method |
| `void` | `return;` | Exits early, **returning no value** |
| `void` | Reaching the end of the body without `return` | Also finishes normally, returning no value |

~~~java
static int square(int n) {
    return n * n;        // int value.
}

static void printIfPositive(int n) {
    if (n <= 0) return;  // Early exit, no expression.
    System.out.println(n);
}
~~~

`square(4)` has the value `16`; `printIfPositive(4)` prints `4` but **has no value to assign to a variable**. In both cases, `return` ends the current call.

## 2. `return expression;` in Non-`void` Methods

~~~java
static int larger(int a, int b) {
    if (a >= b) {
        return a;
    }
    return b;
}
~~~

Calling `larger(3, 8)` returns `8`. The expression after `return` must produce a value **compatible with the method's return type** under Java's conversion rules.

Other examples:

~~~java
static boolean isAdult(int age) {
    return age >= 18;
}

static String status(boolean active) {
    return active ? "ACTIVE" : "INACTIVE";
}
~~~

**Right:** `return age >= 18;` because the expression has type `boolean`. **Wrong:** in a method declared as `int`, writing `return "hello";` or `return;` will not compile.

With reference types like `String`, `return null;` may be type-valid, though callers must handle null according to the API contract. With primitive types like `int`, you cannot `return null;`.

## 3. Value-Returning Methods Must Handle All Paths

~~~java
// WRONG if uncommented: path flag == false does not return an int.
// static int broken(boolean flag) {
//     if (flag) return 1;
// }
~~~

The compiler reports a missing `return` error when a non-`void` method can **complete normally** without returning a value.

Fix:

~~~java
static int choose(boolean flag) {
    if (flag) {
        return 1;
    }
    return 2;
}
~~~

A path can also terminate with `throw` instead of returning:

~~~java
static int positiveOnly(int value) {
    if (value <= 0) {
        throw new IllegalArgumentException("must be positive");
    }
    return value;
}
~~~

**Not every line in the body needs `return`**; the requirement is that execution paths capable of completing normally must return a value. A `throw` branch terminates abruptly and needs no return value.

## 4. `return;` in `void` Methods: Guard Clauses

`void` means the method returns no value; `return;` is useful to **prevent running the rest** if the input is unsuitable.

~~~java
static void announce(String message) {
    if (message == null || message.isBlank()) {
        System.out.println("skip empty");
        return;
    }
    System.out.println("announce:" + message);
}
~~~

With `announce(null)`, the program prints `skip empty` and exits the method. With `announce("Hi")`, the condition is false so it executes `announce:Hi`.

Notes:

- `return;` is valid in a `void` method.
- `return 1;` is **invalid** in a `void` method.
- You are not required to write `return;` at the end of a `void` method; Java finishes automatically when the body completes.
- `void` is not a `null` value or the number `0`; do not write `int x = announce("Hi");`.

A `return` statement in `main(String[] args)` (which has type `void`) also ends `main` without returning a value.

## 5. `return` vs. `break` and `continue`

Placed inside a loop:

| Statement | Scope of effect |
|---|---|
| `return value;` | Ends the current **method** and returns a value |
| `return;` | Ends a `void` method |
| `break;` | Exits the nearest enclosing loop or `switch` |
| `continue;` | Skips the rest of the current iteration and moves to the next iteration |

~~~java
static int firstEven(int[] numbers) {
    for (int number : numbers) {
        if (number % 2 == 0) {
            return number; // Exits the entire method, not just the loop.
        }
    }
    return -1; // Not found.
}
~~~

`firstEven(new int[]{3, 7, 10, 12})` returns `10` as soon as the first even element is encountered. Meanwhile `firstEven(new int[]{3, 7})` returns `-1`.

Do not replace `return number;` with `break;` if the requirement is to **return the number found**: `break` only exits the loop and the method still needs a return path.

## 6. Execution Order and Unreachable Statements

~~~java
static int twice(int n) {
    System.out.println("inside twice");
    return n * 2;
}

System.out.println("before");
System.out.println("result=" + twice(4));
System.out.println("after");
~~~

**Exact stdout** when the last three calls are inside `main`:

~~~text
before
inside twice
result=8
after
~~~

Java evaluates the expression after `return`, ends the call, and then the caller continues. A statement placed **directly after an unconditional `return` in the same block** is an *unreachable statement* and causes a compile error:

~~~java
// static int invalid() {
//     return 5;
//     System.out.println("never"); // Unreachable.
// }
~~~

A `return` inside an `if` branch does not automatically make statements after the `if` unreachable: that branch might not be taken.

**`try/finally`:** If `return` occurs in `try`, `finally` still executes before the return completes, according to Java rules. Avoid placing a new `return` in `finally` because it can override the result or suppress exceptions.

## 7. How Does Java Pass and Return Values?

~~~java
static int changeLocal(int n) {
    n = 99;
    return n;
}

int x = 4;
int y = changeLocal(x);
System.out.println("x=" + x + ",y=" + y);
~~~

**Exact stdout:**

~~~text
x=4,y=99
~~~

Java passes arguments **by value**; parameter `n` is a copy of the value of `x`, so assigning `n=99` does not change `x`. `return n;` returns `99` so the caller can store it in `y`.

With objects, the passed/returned value is a **reference to an object**. Returning a reference does not automatically create a copy of the object; if caller and callee both reference a mutable object, state changes on the object can be observed in both places. This differs from reassigning the parameter variable.

## 8. Complete Java 17 Program

Create the file **`ReturnValueVoidDemo.java`**:

~~~java
public final class ReturnValueVoidDemo {
    private ReturnValueVoidDemo() {}

    static int larger(int a, int b) {
        if (a >= b) return a;
        return b;
    }

    static String grade(int score) {
        if (score < 0 || score > 100) return "INVALID";
        if (score >= 90) return "A";
        if (score >= 70) return "B";
        return "C";
    }

    static void announce(String message) {
        if (message == null || message.isBlank()) {
            System.out.println("skip empty");
            return;
        }
        System.out.println("announce:" + message);
    }

    static int firstEven(int[] numbers) {
        for (int n : numbers) {
            if (n % 2 == 0) return n;
        }
        return -1;
    }

    static int twice(int n) {
        System.out.println("inside twice");
        return n * 2;
    }

    static int changeLocal(int n) {
        n = 99;
        return n;
    }

    static void finallyDemo() {
        try {
            System.out.println("inside try");
            return;
        } finally {
            System.out.println("inside finally");
        }
    }

    public static void main(String[] args) {
        System.out.println("larger=" + larger(3, 8));
        System.out.println("grade -1=" + grade(-1));
        System.out.println("grade 69=" + grade(69));
        System.out.println("grade 70=" + grade(70));
        System.out.println("grade 90=" + grade(90));
        System.out.println("grade 101=" + grade(101));

        announce(null);
        announce(" ");
        announce("Hi");

        System.out.println("firstEven=" + firstEven(new int[]{3, 7, 10, 12}));
        System.out.println("none=" + firstEven(new int[]{3, 7}));

        System.out.println("before twice");
        System.out.println("twice=" + twice(4));
        System.out.println("after twice");

        int x = 4;
        int y = changeLocal(x);
        System.out.println("x=" + x + ",y=" + y);

        finallyDemo();
        System.out.println("after finally");
    }
}
~~~

**Bash (Linux/macOS), JDK 17+:**

~~~bash
javac --release 17 -encoding UTF-8 ReturnValueVoidDemo.java
java -cp . ReturnValueVoidDemo
~~~

**PowerShell (Windows), JDK 17+:**

~~~powershell
javac --release 17 -encoding UTF-8 .\ReturnValueVoidDemo.java
java -cp . ReturnValueVoidDemo
~~~

### Exact expected stdout

~~~text
larger=8
grade -1=INVALID
grade 69=C
grade 70=B
grade 90=A
grade 101=INVALID
skip empty
skip empty
announce:Hi
firstEven=10
none=-1
before twice
inside twice
twice=8
after twice
x=4,y=99
inside try
inside finally
after finally
~~~

**Comparison:** `larger` returns an `int`; `grade` returns early by score thresholds; `announce` uses `return;` to skip empty inputs; `firstEven` exits the whole method from inside a loop; `twice` finishes evaluating before the caller prints the result; `finallyDemo` still runs `finally` before returning to `main`.

## 9. Common Mistakes and Exercises

| Mistake | Why is it wrong? | How to fix |
|---|---|---|
| `return 1;` in a `void` method | Cannot return a value | Use `return;` |
| `return;` in an `int` method | Missing return value | Use `return intExpression;` |
| `return "A";` in a `boolean` method | Wrong type | Return a boolean expression |
| Missing `return` on a path that can complete normally | `missing return statement` | Handle all paths |
| Thinking `return` only exits the loop | `return` exits the **method** | Use `break` if you only want to exit the loop |
| Placing a statement after an unconditional `return` | `unreachable statement` | Place it before `return` or fix control flow |
| Assigning the result of a `void` method | Has no value | Call as a statement |
| Ignoring `finally` when tracing `return` | Execution order misunderstood | Account for the `finally` block |

**Exercise A.** Is `static void stop() { return; }` valid? **Yes.** It exits from `void` without returning a value.

**Exercise B.** Does `static int sign(int n) { if (n > 0) return 1; }` compile? **No**, because when `n <= 0`, the body can finish without returning an `int`. You can add `return 0;` if the contract specifies so.

**Exercise C.** What does calling `firstEven(new int[]{1, 3, 6, 8})` return? **`6`**, because it returns immediately at the first even number.

**Exercise D.** Is a `void` method without `return;` allowed? **Yes**, if it reaches the end of its body it finishes normally.

## 10. Checklist and Conclusion

- [ ] Distinguish `return expression;` and `return;`.
- [ ] Know `void` returns no value and can finish naturally.
- [ ] Know the return expression type must match the declared type.
- [ ] Know non-`void` methods must handle all normally completing paths.
- [ ] Understand `return` exits the **method**, unlike `break`/`continue`.
- [ ] Recognize `unreachable statement` after an unconditional `return`.
- [ ] Understand the returned value is used by the caller after the call completes.
- [ ] Account for `finally` when tracing `return` paths.
- [ ] Compile and run `ReturnValueVoidDemo.java` with Java 17+, and verify stdout.

**Conclusion:** `return expression;` supplies **a value matching the return type** and ends the method; `return;` in `void` **only exits early**, producing no value. Both return control to the call site, not merely out of the enclosing loop.
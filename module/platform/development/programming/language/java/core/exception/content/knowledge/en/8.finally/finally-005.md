# How Does Modifying a Returned Object Differ from Modifying a Local Variable in `finally`?

## 1. Learning Objectives

In Java, the `return` statement in a `try` block and a `finally` block follow a very important execution order: **the `return` expression is evaluated first, then `finally` runs, and only after that does the method complete returning** if `finally` completes normally.

This leads to two seemingly contradictory outcomes:

- If `try` prepares to return a **primitive value** or a **reference held in a local variable**, reassigning the local variable in `finally` does not change the value already prepared to be returned.
- If `try` prepares to return a **reference to a mutable object**, `finally` can modify **the state of that exact object**. The caller receives the same object and observes the modified state.

This lesson helps you master the difference between **variable value**, **reference value**, **referenced object**, and **value of the `return` expression**; predict program output; recognize when a `return` or `throw` in `finally` overrides a previous result; and design exception-handling code without surprises.

The examples use Java 17+; the files with `main`, `javac`/`java` commands, and `stdout` below are standalone programs.

## 2. Execution Order of `return` and `finally`

Consider the structure:

```java
static int compute() {
    int result = 10;
    try {
        return result;
    } finally {
        result = 20;
    }
}
```

This is an illustrative method. A common misconception is "`finally` runs after `return`, so assigning `result = 20` will change the return value to 20." Java does **not** work that way.

According to the Java Language Specification (JLS `14.17 and `14.20.2), when executing `return expression;`:

1. Java evaluates `expression`. Here the expression is the variable `result`, which holds the value `10`.
2. The evaluation result is saved as the **pending return value** for the current call.
3. Upon exiting `try`, the associated `finally` block is executed.
4. If `finally` completes normally, the method returns **the value prepared in step 2**.
5. If `finally` completes abruptly on its own (for example, via its own `throw` or `return`), the new exit reason **replaces** the pending exit reason; the old result may no longer be returned.

Therefore, in the example above, `compute()` returns **10**, even though the local variable holds 20 when `finally` finishes.

Timeline diagram:

```text
result = 10
    |
    v
try: evaluate return result
    |
    +--> pending return value = 10
    |
    v
finally: result = 20
    |
    v
finally completes normally
    |
    v
caller receives 10
```

The key point is that **the `return` expression has already been evaluated**, even though the method has not yet finished leaving the stack. When `finally` modifies the variable, it is working with the local variable, not rewriting the copy of the value already computed for the return statement.

## 3. Primitive Values: Changing the Variable Does Not Change the `return` Result

Create the file **`PrimitiveFinallyDemo.java`**:

```java
public class PrimitiveFinallyDemo {
    static int number() {
        int value = 10;
        try {
            return value;
        } finally {
            value = 99;
            System.out.println("finally value=" + value);
        }
    }

    public static void main(String[] args) {
        System.out.println("returned=" + number());
    }
}
```

Compile and run:

```bash
javac PrimitiveFinallyDemo.java
java PrimitiveFinallyDemo
```

Exact `stdout` output:

```text
finally value=99
returned=10
```

Explanation:

- `value` is a local variable of type `int`, initially equal to 10.
- When encountering `return value`, Java evaluates it and prepares to return the number 10.
- The `finally` block still runs and changes the variable to 99; thus the first line prints 99.
- When `finally` completes normally, the method returns 10 to the call in `main`.
- There is no "live link" between the `int` return result and the local variable `value` after the moment `return` is evaluated.

Other primitive types (`long`, `double`, `boolean`, ...) also follow the rule of evaluating the return expression before processing `finally`.

### Do Not Confuse `return value` with `return 99` Inside `finally`

The following two snippets have different meanings:

```java
// A: reassigns the variable, does NOT create a new return.
try {
    return value;
} finally {
    value = 99;
}
```

```java
// B: finally itself has another return, replacing the previous return.
try {
    return value;
} finally {
    return 99;
}
```

These are two **illustrative code snippets** inside a method returning `int`. A returns the value evaluated in `try`. B returns `99` because of the `return` statement **in `finally`**, not because of reassigning a variable. Writing `return` inside `finally` can hide errors and is generally a practice to avoid; section 9 analyzes this in detail.

## 4. Object References: Java Still Passes/Returns **by Value**

For Java objects, a reference-type local variable holds a **reference value** pointing to the object, not the entire object itself copied upon `return`.

Consider the scenario:

```java
StringBuilder text = new StringBuilder("A");
try {
    return text;
} finally {
    text.append("B");
}
```

This is a snippet placed inside a method returning `StringBuilder`. When evaluating `return text`, Java prepares to return the **reference value** to the current `StringBuilder` object. Then `finally` uses that same reference to call `append("B")`, **mutating the object's state** from `"A"` to `"AB"`.

The caller receives the reference prepared earlier, but the object behind that reference has been modified. Therefore, the caller sees `"AB"`.

Compare this with the case:

```java
StringBuilder text = new StringBuilder("A");
try {
    return text;
} finally {
    text = new StringBuilder("B");
}
```

Here, `finally` **reassigns the `text` variable to a new object**. It does not modify the old object. The reference value of the `return text` expression was already captured before the reassignment, so the caller still receives the old object containing `"A"`.

Therefore, it is necessary to distinguish:

| Action in `finally` | What changes? | Object originally referenced by `return` |
| --- | --- | --- |
| `text.append("B")` | State of the current object | **Modified**, caller can see `"AB"` |
| `text = new StringBuilder("B")` | Local variable `text` points to another object | **Not modified** by this assignment |
| `text = null` | Local variable receives `null` | Old object is still the object to be returned |
| `text.append("B"); text = new StringBuilder("C");` | Old object is modified, then variable points elsewhere | Caller receives old object already containing `"AB"` |
| `text.delete(0, text.length())` | Contents of the old object | Caller sees the old object with its contents cleared |

This is the difference between **mutation (modifying the object's state)** and **reassignment/rebinding (reassigning the reference variable)**.

## 5. Runnable Program: Contrasting Mutation and Reassignment

Create the file **`ReferenceFinallyDemo.java`**:

```java
public class ReferenceFinallyDemo {
    static StringBuilder mutated() {
        StringBuilder text = new StringBuilder("A");
        try {
            return text;
        } finally {
            text.append("B");
        }
    }

    static StringBuilder reassigned() {
        StringBuilder text = new StringBuilder("A");
        try {
            return text;
        } finally {
            text = new StringBuilder("B");
        }
    }

    static StringBuilder both() {
        StringBuilder text = new StringBuilder("A");
        try {
            return text;
        } finally {
            text.append("!");
            text = new StringBuilder("C");
        }
    }

    static StringBuilder assignedNull() {
        StringBuilder text = new StringBuilder("A");
        try {
            return text;
        } finally {
            text = null;
        }
    }

    public static void main(String[] args) {
        System.out.println("mutated=" + mutated());
        System.out.println("reassigned=" + reassigned());
        System.out.println("both=" + both());
        System.out.println("assignedNull=" + assignedNull());
    }
}
```

```bash
javac ReferenceFinallyDemo.java
java ReferenceFinallyDemo
```

`stdout` output:

```text
mutated=AB
reassigned=A
both=A!
assignedNull=A
```

Interpretation:

- `mutated()`: the `return` expression holds a reference to object A; `finally` mutates **that exact object** to AB.
- `reassigned()`: the `return` expression already held a reference to object A; `finally` only switches the local variable to object B.
- `both()`: object A receives `!` before the variable is reassigned to C; the caller receives A!.
- `assignedNull()`: the local variable becomes `null`, but the reference value prepared to be returned still points to object A; the caller receives a non-null object.

Note that `StringBuilder` is mutable. `System.out.println("..." + someStringBuilder)` uses the current contents of the object to build the display string; that is why the printed line reflects the changes made in `finally`.

### One Rule Sufficient to Predict All Four Results

**The reference value is evaluated when `return` is reached; the referenced object can continue to be modified before the method actually returns.** Reassigning the local variable does not replace the prepared reference value.

## 6. User-Defined Objects and Aliasing

`StringBuilder` is not the only type with this behavior. Any object with mutable state can be modified in `finally` and observed by the caller.

Create the file **`HolderFinallyDemo.java`**:

```java
public class HolderFinallyDemo {
    static class Holder {
        int count;

        Holder(int count) {
            this.count = count;
        }
    }

    static Holder create() {
        Holder holder = new Holder(1);
        try {
            return holder;
        } finally {
            holder.count = 2;
        }
    }

    public static void main(String[] args) {
        Holder result = create();
        System.out.println("count=" + result.count);
    }
}
```

```bash
javac HolderFinallyDemo.java
java HolderFinallyDemo
```

`stdout`:

```text
count=2
```

`result` points to the exact `Holder` object that the local variable `holder` pointed to when `return` was evaluated. `finally` modifies the `count` field on that same object to 2.

The concept of *aliasing* means having multiple references pointing to the same object. Modifying state through any valid reference changes the object, so other references can observe the change (within appropriate synchronization/visibility rules if multiple threads are involved).

### Distinguishing "Mutating an Object" from "Changing Another Reference"

```java
Holder first = new Holder(1);
Holder alias = first;
alias.count = 2;          // Mutates the same object; first.count is also 2.
alias = new Holder(99);   // Only changes the alias variable; first still points to the old object.
```

This is an illustrative snippet, assuming the `Holder` class from the example above. Similarly, in `finally`, the variable being reassigned is a separate slot storing a reference value; it does not automatically update the already-evaluated return value.

## 7. Arrays and Collections: Contents Change, Captured Reference Stays the Same

Java arrays are objects whose elements are mutable. Consider:

```java
static int[] values() {
    int[] data = {1, 2};
    try {
        return data;
    } finally {
        data[0] = 99;
    }
}
```

This is an illustrative method snippet. The caller receives **the same array** after the first element has been modified to 99. No automatic array copy is created because of `return data`.

Full program **`ArrayFinallyDemo.java`**:

```java
import java.util.Arrays;

public class ArrayFinallyDemo {
    static int[] create() {
        int[] values = {1, 2, 3};
        try {
            return values;
        } finally {
            values[0] = 7;
            values = new int[] {9, 9, 9};
        }
    }

    public static void main(String[] args) {
        System.out.println(Arrays.toString(create()));
    }
}
```

```bash
javac ArrayFinallyDemo.java
java ArrayFinallyDemo
```

Output:

```text
[7, 2, 3]
```

The line `values[0] = 7` modifies the array prepared to be returned. The line `values = new int[] {9, 9, 9}` only reassigns the `values` variable to a new array, so it does not replace the returned array.

The same applies to mutable collections like `ArrayList`:

```java
static java.util.List<String> createList() {
    java.util.List<String> items = new java.util.ArrayList<>();
    try {
        return items;
    } finally {
        items.add("added in finally");
    }
}
```

This is an illustrative method snippet. If it completes normally, the caller receives a list containing the element `"added in finally"`. However, do not use `finally` as a place to "silently append data before returning"; that makes the method contract hard to read and error-prone.

## 8. Immutable Objects: Reassigning the Variable Does Not Modify the Returned Object

`String` in Java is immutable: no operation modifies the contents of an existing `String` object. The expression `text + "B"` produces a new string value (or is optimized by the runtime in a way that preserves immutable semantics), and then assigns the new reference value to the `text` variable.

Create **`ImmutableFinallyDemo.java`**:

```java
public class ImmutableFinallyDemo {
    static String text() {
        String value = "A";
        try {
            return value;
        } finally {
            value = value + "B";
        }
    }

    public static void main(String[] args) {
        System.out.println(text());
    }
}
```

```bash
javac ImmutableFinallyDemo.java
java ImmutableFinallyDemo
```

`stdout`:

```text
A
```

The mechanism is the same as `reassigned()`: `try` prepared to return a reference to the string `"A"`. In `finally`, string concatenation creates new content and assigns the local variable `value`, without changing the `"A"` string object.

Note: "returning an object" does not automatically mean "the caller will see modified contents." You must consider **whether the object is mutable** and what `finally` actually does.

Wrapper types like `Integer` and `Long` are also immutable. If `finally` assigns `number = number + 1` to an `Integer` variable, that is an operation that computes and reassigns the variable's reference value; it does not modify the `Integer` object prepared to be returned.

## 9. `finally` Executing Its Own `return` or `throw`: Important Exceptions

Up to this point, the examples all had `finally` **completing normally**. When `finally` executes its own `return` or throws an exception, Java applies the rule prioritizing the new abrupt completion reason: `finally` can **replace** the pending result or exception.

### 9.1. `return` in `finally` Overrides the Previous Result

Create the file **`FinallyReturnOverrideDemo.java`**:

```java
public class FinallyReturnOverrideDemo {
    static int value() {
        try {
            return 10;
        } finally {
            return 20;
        }
    }

    public static void main(String[] args) {
        System.out.println(value());
    }
}
```

```bash
javac FinallyReturnOverrideDemo.java
java FinallyReturnOverrideDemo
```

Output:

```text
20
```

`return 10` was evaluated, but `finally` executes its own `return 20`. This is **another return statement** that replaces the pending result. Do not confuse this with merely changing a local variable such as `value = 20` in `finally`.

### 9.2. `return` in `finally` Can Also Swallow Exceptions

Create the file **`FinallySwallowDemo.java`**:

```java
public class FinallySwallowDemo {
    static int risky() {
        try {
            throw new IllegalStateException("original failure");
        } finally {
            return 42;
        }
    }

    public static void main(String[] args) {
        System.out.println(risky());
    }
}
```

```bash
javac FinallySwallowDemo.java
java FinallySwallowDemo
```

`stdout`:

```text
42
```

`IllegalStateException` is thrown in `try`, but `finally` returns 42, so the new completion reason replaces the propagating exception. The Java compiler accepts this construct, but it **masks errors** and often makes diagnosis difficult.

**Recommendation:** do not write `return`, `break`, or `continue` to redirect control flow out of `finally` when handling resources/exceptions; keep the `finally` block dedicated to performing necessary cleanup.

### 9.3. `finally` Throwing a New Exception Can Also Override the Previous Result

Example snippet:

```java
static String read() {
    try {
        return "ready";
    } finally {
        throw new IllegalStateException("cleanup failed");
    }
}
```

When calling `read()`, the call does not return `"ready"`; it terminates with `IllegalStateException("cleanup failed")`. This rule also applies when `try` has already thrown another exception: a new exception from `finally` can mask the original cause.

This is why cleanup in `finally` needs to be designed carefully. For resources implementing `AutoCloseable`, `try-with-resources` has a mechanism for managing close errors using **suppressed exceptions**; do not assume that a manual `finally` automatically preserves the original exception as suppressed.

## 10. Evaluation Timing of Return Expressions and Side Effects

Not only `return variable;`, Java also evaluates complex expressions **before running `finally`**. For example:

```java
static int next() {
    int count = 1;
    try {
        return count++;
    } finally {
        count += 10;
    }
}
```

This is a method snippet. `count++` returns the **old value 1** for the expression while incrementing the variable to 2. Then `finally` increments the variable to 12. The return value is still **1**.

If `return ++count;` were used, the expression would produce 2 before `finally` runs, because the prefix operator increments and then returns the new value.

### Runnable Example: Checking Print Order

Create the file **`ReturnEvaluationOrderDemo.java`**:

```java
public class ReturnEvaluationOrderDemo {
    static StringBuilder make() {
        System.out.println("evaluate return expression");
        return new StringBuilder("created");
    }

    static StringBuilder produce() {
        try {
            return make();
        } finally {
            System.out.println("execute finally");
        }
    }

    public static void main(String[] args) {
        StringBuilder result = produce();
        System.out.println("caller sees: " + result);
    }
}
```

```bash
javac ReturnEvaluationOrderDemo.java
java ReturnEvaluationOrderDemo
```

Output:

```text
evaluate return expression
execute finally
caller sees: created
```

From the output, we can see: the `make()` method is called and produces its result **before** `produce()`'s `finally` runs; only after that does `main` receive the object.

If evaluating **the return expression itself** throws an exception (for example, `return make();` where `make()` throws an error), no return value is produced. The associated `finally` is still processed according to abrupt completion rules, and then the exception continues propagating if `finally` completes normally.

## 11. `finally`, Synchronization, and Aliasing: Practical Limits

### 11.1. Observing an Object After Receiving It Differs from Snapshot Data

When an API needs an **immutable snapshot**, you should not accidentally return a mutable object and then modify it in `finally`. For instance, a method returning a `List` while `finally` still adds/removes elements produces unpredictable results for readers. A clearer choice is to finish all modifications **before `return`**, and then return the finalized value or an appropriate snapshot.

Using `List.copyOf(items)` can create an unmodifiable list at the container level, but that is not necessarily a *deep copy* of mutable element objects. Choosing snapshots and copy boundaries depends on the data contract.

### 11.2. Not Every Object Mutation Means Every Thread Sees It Immediately

In the single-threaded examples in this lesson, the caller continues execution after `finally` runs, so it observes changes deterministically. With multiple threads concurrently accessing a mutable object, you must also consider the Java Memory Model: synchronization, `volatile`, locks, or appropriate concurrent structures. Modifying a field in `finally` **does not automatically create** visibility guarantees for unsynchronized threads.

### 11.3. `finally` Is Not a Transaction System

Mutating an object and then throwing an exception can leave state modified. Java **does not automatically roll back** object changes just because the `try` block failed. If a data invariant is critical, design explicit prepare, validate, and commit steps or use an appropriate transaction mechanism.

### 11.4. Avoid Doing Too Much Manipulation in `finally`

The typical purpose of `finally` is to clean up necessary resources when leaving scope, such as releasing a resource not managed automatically. In modern code, prefer `try-with-resources` for `AutoCloseable`. Mixing result-value adjustments into `finally` causes surprises and makes APIs harder to maintain.

## 12. Quick Reference Table

| Expression in `try` | Action in `finally` | Result if `finally` completes normally |
| --- | --- | --- |
| `int x = 1; return x;` | `x = 9;` | Returns **1** |
| `int x = 1; return x++;` | `x = 9;` | Returns **1** (postfix returns old value) |
| `int x = 1; return ++x;` | `x = 9;` | Returns **2** |
| `String s = "A"; return s;` | `s = "B";` | Returns `"A"` |
| `StringBuilder b = new StringBuilder("A"); return b;` | `b.append("B");` | Returns the same object now containing `"AB"` |
| `StringBuilder b = new StringBuilder("A"); return b;` | `b = new StringBuilder("B");` | Returns the object containing `"A"` |
| `int[] a = {1}; return a;` | `a[0] = 7;` | Returns the array with first element **7** |
| `Holder h = new Holder(1); return h;` | `h.count = 2;` | Returns `Holder` with `count == 2` |
| `return 1;` | `return 2;` | Returns **2**, because `finally` has its own return statement |
| `return 1;` | `throw new IllegalStateException();` | **Throws exception**, returns no number |

The table records results according to Java 17 and assumes no new errors occur inside the operations beyond the stated cases. The shorthand snippets in the `try`/`finally` columns are for comparing semantics, not standalone Java files.

## 13. Common Misconceptions

**"`finally` runs after `return`, so changing a variable in `finally` will always update the return value."** False. The `return` expression is already evaluated and the pending value is saved before `finally` starts.

**"`finally` runs, so it cannot affect the object being returned."** False. If `finally` uses a reference to **the same mutable object** to modify its contents, the caller can receive the modified object.

**"Reassigning a reference variable to a new object is the same as modifying the old object."** False. Reassigning the variable changes **the reference value in the variable**; it does not change the object that the return value already points to.

**"`text = null` in `finally` makes the method return `null`."** Incorrect if `return text` was evaluated earlier with a non-null reference and `finally` completes normally.

**"`String` and `StringBuilder` change the same way."** False. `String` is immutable; `StringBuilder` is mutable. `String.concat` or `+` does not mutate the original `String` object.

**"Parameters, local variables, and return values all point to a single reference memory slot."** False. They can hold **copies of the reference value** to the same object, but they are distinct variables/values. Changing one reference does not necessarily change the others.

**"`finally` only cleans up, so it cannot change how the method completes."** False. `return` or `throw` in `finally` can replace the old return value or exception.

**"If `finally` throws a new error, Java automatically preserves the old error as suppressed."** Not true for manual `finally` in general. The suppressed mechanism has specific rules for `try-with-resources`; be sure to distinguish them.

**"Seeing an object modified in `finally` means Java uses return-by-reference."** False. Java always passes/returns **by value**; for reference types, that value is **a reference to an object**, and having two places point to the same object explains the mutation behavior.

**"Once `return` is reached, `finally` can be skipped in all cases."** False. When returning through normal language control flow, the associated `finally` is executed. However, this is not a cleanup guarantee if the JVM/process is forcefully terminated.

## 14. Self-Check Exercises

### Exercise 1: Primitive Variable

```java
static int test() {
    int n = 2;
    try {
        return n;
    } finally {
        n += 5;
    }
}
```

**Result?** `test()` returns **2**. `finally` changes the variable to 7, but does not change the value prepared to be returned.

### Exercise 2: Mutating an Object

```java
static StringBuilder test() {
    StringBuilder b = new StringBuilder("X");
    try {
        return b;
    } finally {
        b.append("Y");
    }
}
```

**What string does the caller observe?** `XY`, because the exact object being returned was mutated.

### Exercise 3: Reassigning a Variable

```java
static StringBuilder test() {
    StringBuilder b = new StringBuilder("X");
    try {
        return b;
    } finally {
        b = new StringBuilder("Y");
    }
}
```

**What string does the caller observe?** `X`. The local variable now points to object Y, while the `return` result still holds a reference to object X.

### Exercise 4: Arrays

```java
static int[] test() {
    int[] a = {3};
    try {
        return a;
    } finally {
        a[0] = 8;
        a = new int[]{99};
    }
}
```

**What is the first element the caller sees?** **8**. The element write mutates the old array, while the subsequent variable assignment only changes the reference in the variable.

### Exercise 5: `return` in `finally`

```java
static int test() {
    try {
        return 1;
    } finally {
        return 2;
    }
}
```

**Result?** **2**. `finally` has its own new `return`, overriding the pending result. This is an example to avoid in real applications.

### Exercise 6: Exception While Preparing Return

Suppose `return produce();` is inside `try` and `produce()` throws `IOException` before producing a result, while `finally` only logs and completes normally. **Does the method return a value?** No. The `IOException` continues propagating after `finally` if not handled by a matching handler.

### Exercise 7: API Design

If a method wants to return an immutable snapshot of a list, should it return an `ArrayList` and then continue calling `add` in `finally`? **No**. You should finalize the data before returning and choose a type/copying approach that accurately represents the required immutability.

## 15. Standard References

- [Java Language Specification 17 — `14.17 The return Statement](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.17): evaluation of the return expression and how `return` completes abruptly.
- [Java Language Specification 17 — `14.20.2 Execution of try-finally and try-catch-finally](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.20.2): execution order of `finally` and rules for replacing exit reasons.
- [Java Language Specification 17 — `4.3 Reference Types and Values](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.3): meaning of reference values and objects.
- [Java SE 17 API — StringBuilder](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/StringBuilder.html): mutable string-like object.
- [Java SE 17 API — String](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html): immutable string.

**Remember:** `return` evaluates and captures **the return value** before `finally` runs. For a primitive variable, that is the primitive value; for a reference variable, that is the reference value to the object. Changing **the local variable** does not rewrite the captured result, whereas changing **the state of the referenced object** can be visible to the caller. This rule applies when `finally` completes normally; a new `return` or `throw` in `finally` can replace the entire result.
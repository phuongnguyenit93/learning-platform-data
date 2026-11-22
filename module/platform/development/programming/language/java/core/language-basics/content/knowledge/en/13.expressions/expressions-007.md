# Side Effects in Expressions and the Risk of Unpredictability — Java 17+

## 1. Lesson Objectives

In Java, an **expression** can both **compute a value** and perform a **side effect**—mutating observable state such as assigning a variable, incrementing a counter, modifying a field, changing an array element, writing logs, or performing I/O.

~~~java
int count = 5;
int old = count++; // Expression value is 5, while count changes to 6

System.out.println(old);   // 5
System.out.println(count); // 6
~~~

The **value** part of `count++` is 5; the **side effect** part is updating `count` from 5 to 6. These are two distinct aspects of the same expression.

**Key point:** Java 17 has a **well-defined evaluation order**, not an arbitrary one. However, when a single expression reads and modifies the same state multiple times, readers can still easily mispredict the outcome. Therefore, this lesson focuses on **understanding Java accurately and writing easily verifiable code**, rather than cramming every operation onto one line.

## 2. Identifying Expressions with Side Effects

| Expression / invocation | Expression value | Possible side effect |
|---|---|---|
| `a + b` with two `int`s | `int` sum | Normally does not modify `a`, `b` |
| `x = 10` | Value after assignment | Reassigns `x` |
| `x++` | Value **before** incrementing | Increments `x` |
| `++x` | Value **after** incrementing | Increments `x` |
| `x += 3` | Value of `x` after update | Updates `x` |
| `array[index++]` | Array element at old index | Increments `index` |
| `object.change()` | Depends on method return type | Method may mutate object or other state |
| `System.out.println("hi")` | `void`, no assignable value | Writes to output |
| `new SomeClass()` | Reference to new instance if successful | Creates object; constructor may have observable behavior |

**Never infer whether a method is "read-only" or "mutating" solely from its name.** For a call like `service.getValue()`, check the API contract and implementation: a getter might write logs, update a cache, or throw an exception.

A pure operator like `a + b` does not itself mutate its operands; however, **operand expressions** can have side effects:

~~~java
int result = next() + current(); // next() or current() may mutate state
~~~

To understand it properly, examine the entire **operand evaluation process**, not just the `+` operator.

## 3. Prefix `++x`, Postfix `x++`: Same Update, Different Value

~~~java
int x = 3;

int before = x++; // before = 3, x becomes 4
int after = ++x;  // x becomes 5, after = 5

System.out.println(before); // 3
System.out.println(after);  // 5
System.out.println(x);      // 5
~~~

| Syntax | Value used in expression | State afterward |
|---|---|---|
| `x++` | Old value | `x` incremented by 1 |
| `++x` | New value | `x` incremented by 1 |
| `x--` | Old value | `x` decremented by 1 |
| `--x` | New value | `x` decremented by 1 |

In a simple loop, `i++` is usually easy to read:

~~~java
for (int i = 0; i < 3; i++) {
    System.out.println(i);
}
~~~

In a larger calculation, however, you must keep track of **pre/post-update values** and **when another expression reads the variable**. Splitting statements prevents confusion.

## 4. Java Is Not "Undefined," Yet Complex Expressions Are Hard to Read

The example below is **valid and has a deterministic result in Java**:

~~~java
int i = 1;
int sum = i++ + ++i;

System.out.println(sum); // 4
System.out.println(i);   // 3
~~~

Exact left-to-right explanation:

1. `i++` yields the **old value 1**, then updates `i = 2`.
2. `++i` updates `i = 3`, then yields the **new value 3**.
3. `1 + 3` equals **4**, and the final value of `i` is **3**.

Do not call this case "undefined behavior" in the sense used by some other languages: **Java specifies evaluation order**. The problem lies in readability, maintainability, and the risk of breaking things during refactoring.

More explicitly:

~~~java
int i = 1;
int left = i;
i++;
i++;
int right = i;
int sum = left + right;
~~~

The step-by-step version makes the intent clear and produces the same result in this case. If business logic does not require two updates, a better option is to **simplify the algorithm**, not merely add variables.

### The `i = i++` Trap

~~~java
int i = 5;
i = i++;
System.out.println(i); // 5
~~~

Why is it still 5? The right side `i++` yields the old value **5** and increments `i` to 6; finally, **the outer assignment** assigns the old value 5 back to `i`.

Write `i++;` if you only want to increment, or `i = desiredValue;` if you only want to assign. **Do not combine two assignment mechanisms on the same variable unnecessarily.**

## 5. Side Effects Follow Evaluation Order, Not Precedence

~~~java
static int trace(String label, int value) {
    System.out.println("evaluate " + label);
    return value;
}
// Inside a method:
int result = trace("A", 2) + trace("B", 3) * trace("C", 4);
~~~

The three lines `evaluate A`, `evaluate B`, `evaluate C` appear in that order; `result == 14`. Multiplication is **grouped** before addition when computing the value, yet it does not make calls B/C run before A.

Especially when methods mutate state, capture results into separate variables in the exact desired order, then perform the calculation. This reduces the risk of accidentally altering side effects when editing code.

## 6. Method Arguments Are Evaluated Before the Method Begins

When calling:

~~~java
show(trace("first", 1), trace("second", 2));
~~~

Java evaluates arguments **from left to right** before executing the body of `show`. In this example, `trace("first", 1)` runs before `trace("second", 2)`, and only then does `show` execute.

This can introduce bugs if two arguments mutate the same object:

~~~java
send(counter.incrementAndGet(), counter.get());
~~~

If `incrementAndGet()` increments state, the second argument may read **the post-increment value**, not the initial state. Do not assume two arguments are evaluated "at the same instant."

Clearer approach:

~~~java
int newValue = counter.incrementAndGet();
int snapshotAfter = counter.get();
send(newValue, snapshotAfter);
~~~

**Note:** the compiler selects overloads using the static types of argument expressions, whereas side effects from **evaluating** arguments occur at runtime. These two aspects are separate.

## 7. Short-Circuiting with `&&` and `||`

The **`&&`** operator skips the right side if the left side is already `false`; **`||`** skips the right side if the left side is already `true`.

~~~java
int divisor = 0;
boolean safe = (divisor != 0) && (10 / divisor > 2);
System.out.println(safe); // false, does not divide by 0
~~~

If a method with side effects sits in the skipped branch, the side effect **does not occur**:

~~~java
boolean result = false && updateCounter(); // updateCounter() is not called
~~~

Model:

~~~mermaid
flowchart TD
    A["Evaluate left side of &&"] --> B{"Is it true?"}
    B -- "No" --> C["Result is false, skip right side"]
    B -- "Yes" --> D["Evaluate right side"]
    E["Evaluate left side of ||"] --> F{"Is it true?"}
    F -- "Yes" --> G["Result is true, skip right side"]
    F -- "No" --> H["Evaluate right side"]
~~~

**Distinguish `&&` from `&`, and `||` from `|` when operands are boolean:**

| Operator | Skips right side? | Note |
|---|---|---|
| `&&` | Yes, when left side is false | Commonly used to guard conditional operations |
| `||` | Yes, when left side is true | Commonly used to provide a fallback choice |
| `&` | No | Evaluates both sides |
| `|` | No | Evaluates both sides |

Using `&` instead of `&&` can **unintentionally call extra methods**, mutate data, or trigger exceptions. Use the right operator and test both true and false cases.

## 8. Conditional Operator `?:` Evaluates Only the Selected Branch

~~~java
boolean useCache = true;
int answer = useCache ? readCache() : calculateFresh();
~~~

The compiler checks the types of both branches using conditional expression rules, yet at runtime Java evaluates only **the selected branch**. If `useCache` is true, `calculateFresh()` is not called.

Therefore, if a branch sends a network request, writes logs, or updates a counter, **call counts can differ** across runs. This completely follows Java semantics, not randomness.

If both branches contain significant state-mutating logic, `if/else` is usually easier to inspect:

~~~java
int answer;
if (useCache) {
    answer = readCache();
} else {
    answer = calculateFresh();
}
~~~

**Do not put side effects in both branches expecting both to execute.**

## 9. Variable Assignment, Object Mutation, and Aliasing

Side effects are not limited to modifying a primitive variable:

~~~java
final class Counter {
    int value;

    Counter(int value) {
        this.value = value;
    }

    int incrementAndGet() {
        return ++value;
    }
}

// Inside a method:
Counter original = new Counter(10);
Counter alias = original;

int current = alias.incrementAndGet();
System.out.println(current);        // 11
System.out.println(original.value); // 11
~~~

`original` and `alias` both reference **the same Counter**. A method on `alias` mutates a field on the object, so code using `original` also sees the new value.

A method call may look like a value-fetching expression yet modify shared state. In code with multiple objects, check:

- Does the method only read or does it modify fields/collections?
- Do multiple variables refer to the same object?
- Is this method allowed to be called multiple times?
- Is synchronization or protection needed when multiple threads access it?

**A well-typed computation** does not mean no state changes occur.

## 10. Array Indices with `i++`: Where Is It Read, When Is It Updated?

~~~java
int[] values = {10, 20, 30};
int i = 0;

int sum = values[i++] + values[i];

System.out.println(sum); // 30
System.out.println(i);   // 1
~~~

Java evaluates `values[i++]` first:

1. `i++` provides the old index **0**, then changes `i` to **1**.
2. Reads `values[0]` equal to **10**.
3. Evaluates `values[i]` on the right with `i = 1`: gets **20**.
4. The sum is **30**.

More readable approach:

~~~java
int first = values[i];
i++;
int second = values[i];
int sum = first + second;
~~~

Using `values[i++] = nextValue` in an array traversal algorithm can be appropriate when simple, yet **avoid combining multiple updates to the same index inside one long expression**. If `i` goes out of bounds, the program can throw `ArrayIndexOutOfBoundsException`; Java does not guess your indexing intent.

## 11. String Concatenation and Logging Can Hide Side Effects

~~~java
int n = 1;
System.out.println("n=" + n++ + ", now=" + n);
~~~

Output:

~~~text
n=1, now=2
~~~

`n++` contributes the old value 1 to the string, and then `n` is already 2 when the next sub-expression is evaluated.

**Do not use expressions with side effects just to build log messages.** Clearer approach:

~~~java
int old = n;
n++;
System.out.println("old=" + old + ", now=" + n);
~~~

An expression passed into `logger.debug(...)` or `System.out.println(...)` can be **evaluated before the call**, even if code inside the method decides not to write to the destination. To optimize log evaluation cost, check whether the specific logging API supports lazy evaluation.

## 12. Exceptions Can Halt Evaluation

An expression with completely valid compile-time types can still **fail to complete normally** at runtime:

~~~java
int zero = 0;
int value = (10 / zero) + expensiveOperation();
~~~

If `10 / zero` throws `ArithmeticException`, Java does not proceed to evaluate `expensiveOperation()`. Hence any side effect inside the right-hand method **does not occur**.

Similarly:

~~~java
String text = null;
// int length = text.length() + mutate(); // text.length() throws NPE;
// mutate() is not called.
~~~

This is a reason to avoid packing **fallible computations and state updates** into one long expression: a failing execution path can leave state partially updated and hard to roll back.

**Do not misunderstand:** catching an exception with `try/catch` does not mean prior side effects before the exception are automatically undone. If consistency across multiple operations is needed, design proper transactions or rollback.

## 13. How to Refactor Expressions with Multiple Side Effects

**Before — hard to read:**

~~~java
int result = counter.incrementAndGet()
        + values[index++]
        + service.nextValue();
~~~

This snippet mixes three state changes/observations:

1. Incrementing `counter`.
2. Incrementing `index` while selecting an element.
3. Calling `service.nextValue()`, which may have side effects per its API contract.

**After — separate intent, preserve order:**

~~~java
int counterValue = counter.incrementAndGet();
int selectedValue = values[index];
index++;
int serviceValue = service.nextValue();
int result = counterValue + selectedValue + serviceValue;
~~~

Benefits:

- Easier step-by-step debugging.
- Logs/tests can inspect state at clear boundaries.
- Easy to place validation before risky operations.
- Code reviewers see the order of operations instead of mentally simulating side effects.

**Be careful:** when refactoring, do not arbitrarily reorder method calls, change operator kinds, or drop guards; preserve the required semantics, especially when methods have side effects.

## 14. Java Has Deterministic Order, Yet Concurrency Still Has Separate Issues

The examples above assume execution on **a single thread**. Left-to-right evaluation rules do not replace synchronization mechanisms across threads.

~~~java
static int count = 0;

// If multiple threads execute concurrently:
count++;
~~~

`count++` consists of read, compute, and write; it is **not an atomic increment safe for all multithreaded scenarios**. When multiple threads write concurrently without synchronization, race conditions and lost updates can occur.

If a shared counter is needed, you can use `java.util.concurrent.atomic.AtomicInteger` as required:

~~~java
java.util.concurrent.atomic.AtomicInteger count =
        new java.util.concurrent.atomic.AtomicInteger(0);
int next = count.incrementAndGet();
~~~

**Distinguish:** Java specifies evaluation order within a single thread; however, correctness of shared state across multiple threads requires adhering to the Java Memory Model and proper synchronization. Do not use parentheses or change `i++` to `++i` to fix a race condition.

## 15. Standalone Java 17 Program with Expected Output

Save the file with the exact name **`ExpressionSideEffectsDemo.java`**:

~~~java
public final class ExpressionSideEffectsDemo {
    private ExpressionSideEffectsDemo() {}

    static int trace(String label, int value) {
        System.out.println("evaluate " + label);
        return value;
    }

    static void show(int a, int b) {
        System.out.println("arguments=" + a + "," + b);
    }

    static boolean check(boolean result, int[] calls) {
        calls[0]++;
        return result;
    }

    static int select(int value, int[] calls) {
        calls[0]++;
        return value;
    }

    static final class Counter {
        int value;

        Counter(int value) {
            this.value = value;
        }

        int addAndGet(int amount) {
            value += amount;
            return value;
        }
    }

    public static void main(String[] args) {
        int x = 3;
        int postfix = x++;
        int prefix = ++x;
        System.out.println("postfix=" + postfix
                + ", prefix=" + prefix + ", x=" + x);

        int i = 1;
        int mixed = i++ + ++i;
        System.out.println("mixed=" + mixed + ", i=" + i);

        int confusing = 5;
        confusing = confusing++;
        System.out.println("self-assignment=" + confusing);

        int arithmetic = trace("A", 2)
                + trace("B", 3) * trace("C", 4);
        System.out.println("arithmetic=" + arithmetic);

        show(trace("first", 1), trace("second", 2));

        int[] calls = {0};
        boolean guardedAnd = check(false, calls)
                && check(true, calls);
        System.out.println("&&=" + guardedAnd + ", calls=" + calls[0]);

        boolean guardedOr = check(true, calls)
                || check(false, calls);
        System.out.println("||=" + guardedOr + ", calls=" + calls[0]);

        boolean eagerAnd = check(false, calls)
                & check(true, calls);
        System.out.println("&=" + eagerAnd + ", calls=" + calls[0]);

        int[] branchCalls = {0};
        int chosen = true
                ? select(5, branchCalls)
                : select(9, branchCalls);
        System.out.println("ternary=" + chosen
                + ", calls=" + branchCalls[0]);

        Counter counter = new Counter(10);
        Counter alias = counter;
        int changed = alias.addAndGet(5);
        System.out.println("counter=" + changed
                + ", original=" + counter.value);

        int[] values = {10, 20, 30};
        int index = 0;
        int arraySum = values[index++] + values[index];
        System.out.println("array sum=" + arraySum + ", index=" + index);

        int n = 1;
        System.out.println("string side effect=" + n++
                + ", now=" + n);

        int zero = 0;
        try {
            int unused = (10 / zero) + trace("unreached", 99);
            System.out.println(unused);
        } catch (ArithmeticException ex) {
            System.out.println("division error, right skipped");
        }
    }
}
~~~

Install **JDK 17+**, open a terminal in the folder containing the file.

**Bash (Linux/macOS):**

~~~bash
javac --release 17 -encoding UTF-8 ExpressionSideEffectsDemo.java
java -cp . ExpressionSideEffectsDemo
~~~

**PowerShell (Windows):**

~~~powershell
javac --release 17 -encoding UTF-8 .\ExpressionSideEffectsDemo.java
java -cp . ExpressionSideEffectsDemo
~~~

**Exact expected output:**

~~~text
postfix=3, prefix=5, x=5
mixed=4, i=3
self-assignment=5
evaluate A
evaluate B
evaluate C
arithmetic=14
evaluate first
evaluate second
arguments=1,2
&&=false, calls=1
||=true, calls=2
&=false, calls=4
ternary=5, calls=1
counter=15, original=15
array sum=30, index=1
string side effect=1, now=2
division error, right skipped
~~~

### Reviewing Key Points

1. `x++` returns the old value, `++x` returns the new value; both modify `x`.
2. `i++ + ++i` has a deterministic result, yet is harder to read than splitting steps.
3. `i = i++` overwrites the incremented result and keeps the old value.
4. `trace A/B/C` runs left to right even though `*` has higher precedence than `+`.
5. Arguments to `show` are evaluated sequentially before the method body.
6. `&&` and `||` skip the right side once the outcome is determined; `&` does not skip.
7. `?:` calls only the selected branch.
8. Both alias variables observe the side effect on the `Counter` object.
9. `index++` modifies the index before the right side reads the array again.
10. The right side after division by 0 does not run; therefore **no `evaluate unreached` line** appears in the output.

## 16. Common Mistakes and Fixes

| Code / misconception | Problem | Fix or guideline |
|---|---|---|
| `int sum = i++ + ++i;` | Deterministic result, yet hard to audit | Separate updates from addition |
| `i = i++;` to increment `i` | Assignment overwrites the post-increment value | Write `i++;` |
| Thinking `*` has higher precedence so the right operand of addition always runs first | Confuses precedence with evaluation order | Distinguish grouping from evaluation order |
| Calling side-effecting methods across multiple arguments | Later argument state depends on earlier argument | Extract temporary variables, call in order |
| Using `&` instead of `&&` for null guards | `&` evaluates both sides | Use `&&` |
| Expecting both branches of `?:` to take effect | Only one branch is selected | Use separate statements if both actions are needed |
| `list.get(index++)` nested inside a long calculation | Easy to use the wrong index, hard to debug | Store temporary index/element |
| Assuming getters never modify anything | Methods may alter caches/logs/fields | Check the contract and implementation |
| Formatting logs with `value++` | Logging mutates state | Separate updates from formatting |
| Assuming exceptions roll back prior side effects | Java does not auto-rollback state | Design transactions/rollbacks explicitly |
| Using `count++` as a multithreaded counter | Not guaranteed atomic | Synchronization or `AtomicInteger` |
| Concluding Java has unspecified order | Java has clear evaluation rules | Know the order, yet prefer simple code |

## 17. Exercises with Answers

### Exercise A — postfix and value

~~~java
int x = 2;
int y = x++ + x++;
System.out.println(y);
System.out.println(x);
~~~

**Answer:**

~~~text
5
4
~~~

The first postfix contributes 2 then `x = 3`; the second contributes 3 then `x = 4`. The sum is 5. Although valid, this style should not be the default in business code.

### Exercise B — argument evaluation order

~~~java
static int step(int value) {
    System.out.println("step " + value);
    return value;
}

static void show(int a, int b) {
    System.out.println(a + b);
}

// In main:
show(step(1), step(2));
~~~

**Answer:**

~~~text
step 1
step 2
3
~~~

### Exercise C — short-circuiting

~~~java
int[] calls = {0};
boolean result = false && check(true, calls);
System.out.println(result);
System.out.println(calls[0]);
~~~

**Answer:**

~~~text
false
0
~~~

`check` is the helper from the runnable example above; the right side is not called, so the counter remains 0.

### Exercise D — arrays and index

~~~java
int[] a = {4, 9, 16};
int i = 0;
int sum = a[i++] + a[i];
System.out.println(sum);
System.out.println(i);
~~~

**Answer:**

~~~text
13
1
~~~

### Exercise E — refactoring hard-to-read code

Given the expression:

~~~java
int result = service.next() + counter.incrementAndGet();
~~~

Rewrite it so the order of operations is clear.

**One answer:**

~~~java
int serviceValue = service.next();
int counterValue = counter.incrementAndGet();
int result = serviceValue + counterValue;
~~~

This is a step-by-step version that **preserves the left-before-right call order**.

### Exercise F — side effects and exceptions

~~~java
int denominator = 0;
int result = (10 / denominator) + trace("after", 5);
~~~

**Answer:** throws `ArithmeticException` on integer division by 0; `trace("after", 5)` does not run, so there is no `evaluate after` output.

## 18. Checklist and Conclusion

- [ ] Distinguish between an **expression's value** and its **side effects**.
- [ ] Remember `i++` returns the old value and `++i` returns the new value.
- [ ] Understand that expressions like `i++ + ++i` have deterministic results yet are hard to maintain.
- [ ] Know why `i = i++` fails to increment the final result.
- [ ] Distinguish **operator precedence** from **evaluation order**.
- [ ] Know that Java evaluates method arguments from left to right.
- [ ] Know that `&&`/`||` short-circuit, whereas boolean `&`/`|` do not.
- [ ] Know that `?:` evaluates only the selected branch.
- [ ] Spot side effects when mutating objects via aliases or array indices.
- [ ] Understand that exceptions can halt evaluation and do not auto-roll back prior state changes.
- [ ] Avoid embedding updates in log expressions or long formulas unnecessarily.
- [ ] Extract side-effecting calls into clearly named statements.
- [ ] Distinguish single-threaded expression order from multithreaded race conditions.
- [ ] Run `ExpressionSideEffectsDemo.java` with Java 17+ `javac`/`java` and verify exact expected output.

**Conclusion:** Java expressions can both produce values and mutate state. Java 17 defines evaluation order, yet multiple side effects in a single expression remain a source of misreading, unintended mutations, and hard-to-test code. **Keep calculations simple, extract state updates into explicit steps, use short-circuiting intentionally, and test both success and exception paths.**

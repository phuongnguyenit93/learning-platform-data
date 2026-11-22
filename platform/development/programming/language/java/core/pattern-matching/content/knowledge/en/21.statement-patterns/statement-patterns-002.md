# Patterns in the `while` Statement (Java 21+)

## 1. Why is pattern matching useful in a `while` loop?

A `while` loop often reads data step by step: fetching elements from a stream, traversing linked nodes, or continuing to process data as long as it has the expected type. With traditional type checking, you have to write `instanceof`, cast, and inspect the value in separate places:

~~~java
Object current = "Java";

while (current instanceof String) {
    String text = (String) current;
    System.out.println(text.toUpperCase());
    current = 42; // Change state so the loop can terminate
}
~~~

With a **type pattern** (`String text`), the `while` condition can both check the type and declare a type-checked variable:

~~~java
Object current = "Java";

while (current instanceof String text) {
    System.out.println(text.toUpperCase());
    current = 42;
}
~~~

In the second example, Java knows `text` has type `String` **inside the loop body**, because the body only runs after the condition `instanceof String text` is true. There is no longer an explicit cast.

What makes `while` different from a regular `if` is that **the condition is re-evaluated before each iteration**. Java can bind a new value to the pattern variable on each matching iteration; if the condition no longer matches, the loop body does not execute on that iteration.

Type patterns with `instanceof` have been a standard feature since Java 16. **Record patterns** in `while` (for example, `Link(String name, var next)`) were standardized in Java 21; this lesson uses **JDK 21+** to demonstrate both.

## 2. Mechanism: check first, bind variable after matching

Core syntax:

~~~java
while (expression instanceof SomeType variable) {
    // variable has type SomeType and can be used here
    // Update the checked state so the loop can make progress
}
~~~

Three steps happen in order:

1. Java evaluates the entire `while` condition. An `instanceof` expression with a type pattern returns `false` when the value is `null` or does not belong to a compatible type.
2. If the pattern matches and the entire condition is true, the pattern variable is bound to the matched value. The loop body runs, and **the variable is in scope** there.
3. After the loop body, Java returns to check the condition again. If it no longer matches this time, the loop terminates.

Pattern variables follow **flow scoping**. The fact that a variable name appears in the condition does not mean it can be used on every line after the `while` statement.

~~~java
Object input = "hello";

while (input instanceof String text) {
    System.out.println(text.length()); // Valid
    input = null;
}

// System.out.println(text); // Compile error if uncommented
~~~

After a loop with a **positive pattern** `input instanceof String text`, the condition may have become `false`; therefore, `text` cannot be used on the following line. This is a standalone **illustrative snippet** inside a method where `input` is declared as shown above.

You should distinguish between a pattern variable having a **clear static type** and the source object being able to change type on a later iteration: `text` is a `String` in the current loop body, while the variable `input` still has the declared type `Object`.

## 3. Combining patterns with other conditions using `&&`

A `while` condition often checks more than just the type. You can simultaneously check length, content, index bounds, and other rules:

~~~java
Object[] items = {"java", "21", 42, "after"};
int index = 0;

while (index < items.length
        && items[index] instanceof String word
        && !word.isBlank()) {
    System.out.println(word);
    index++;
}
~~~

Output:

~~~text
java
21
~~~

At index `2`, the value is the integer `42`, so the pattern `String word` does not match and the loop stops. The subsequent element `"after"` is **not processed**.

The order of the three conditions is significant:

- `index < items.length` must be true before accessing `items[index]`; this avoids out-of-bounds array access.
- `items[index] instanceof String word` must match before calling a method on `word`.
- `!word.isBlank()` is only evaluated after the pattern has matched, because `&&` **short-circuits from left to right**.

As a result, `word` is in scope in the `!word.isBlank()` operand and inside the `while` body.

An **intentionally invalid** way to write this:

~~~java
// DOES NOT COMPILE: the right-hand side of || can run when the left-hand pattern fails.
while (items[index] instanceof String word || word.isBlank()) {
    // ...
}
~~~

With `||` in the expression above, Java may have to evaluate `word.isBlank()` when the left-hand pattern does not match, so `word` is not guaranteed to have a value. It is also missing a bounds check for `index`. When you need to choose between different cases, use a clear conditional structure; do not replace `&&` with `||` just to combine expressions.

## 4. The loop must make progress to terminate

Pattern matching **does not automatically make a loop progress**. The following example can run indefinitely:

~~~java
Object input = "A";

// Algorithmically WRONG: input does not change after each iteration.
while (input instanceof String text) {
    System.out.println(text);
}
~~~

The pattern always matches because `input` always holds the same string. To avoid this bug, clearly identify **what changes across each iteration**: an index increments, an iterator advances to the next element, or a variable points to the next node.

How to fix an array-traversal loop:

~~~java
Object[] values = {"A", "B", 10};
int index = 0;

while (index < values.length && values[index] instanceof String text) {
    System.out.println(text);
    index++; // Advance to the next element
}
~~~

The snippet above stops when it encounters `10`. When using `continue`, the update step must occur **before** the `continue` statement or in a place guaranteed to run on every branch that needs to continue; otherwise, it is very easy to loop forever on the same element.

Using `while (iterator.hasNext() && iterator.next() instanceof String text)` also requires care: `next()` consumes an element **even when the pattern does not match**. If you need to keep or handle the first invalid element separately, retrieve it into a `current` variable inside the loop body and explicitly decide how to handle it.

## 5. Distinguishing “stop at non-matching element” from “skip non-matching element”

This is a business-logic decision, not merely a coding style choice.

**Approach A — pattern in the `while` condition:** the loop processes a **contiguous prefix** of matching elements and stops immediately at the first non-matching element.

~~~java
int index = 0;
while (index < items.length && items[index] instanceof String word) {
    System.out.println(word);
    index++;
}
~~~

With the data `{"java", "21", 42, "after"}`, only `"java"` and `"21"` are printed. The element `42` makes the condition false, and there is no next iteration.

**Approach B — `while` checks whether traversal can continue, while the pattern is inside the body:** the loop can skip invalid values and still inspect the next element.

~~~java
int index = 0;
while (index < items.length) {
    Object item = items[index++];

    if (!(item instanceof String word)) {
        continue; // Skip only the current element
    }
    System.out.println(word);
}
~~~

With the same data, approach B also prints `"after"`. By placing `index++` before `continue`, the current element is always consumed, avoiding an infinite loop.

The two approaches serve **different** requirements:

| Requirement | Appropriate structure |
| --- | --- |
| Traverse contiguously while the next element still has the right type | Place the type pattern in the `while` condition |
| Traverse the entire source, skipping elements of the wrong type | Place the pattern in the `while` body and use `continue` |
| Report an error immediately upon encountering invalid data | Use `if (!(...))` then `throw` or return an error result |
| Need special handling for the first non-matching element | Do not blindly consume the element in the `while` condition |

In practice, choose the structure based on the meaning of the data: “reading a contiguous prefix” is different from “filtering the entire list”.

## 6. Record patterns in `while`: traversing nested structures

Starting in Java 21, a `while` condition can also deconstruct a `record`:

~~~java
record Link(String name, Link next) {}
~~~

`Link` stores a name and a pointer to the next node. You can traverse a simple linked list without calling `link.name()` and `link.next()` in two separate steps:

~~~java
Object cursor = new Link("A", new Link("B", null));

while (cursor instanceof Link(String name, var next)
        && !name.isBlank()) {
    System.out.println("link=" + name);
    cursor = next;
}
~~~

Output:

~~~text
link=A
link=B
~~~

Explanation:

- `Link(String name, var next)` is a **record pattern** consisting of two component patterns corresponding to `name` and `next` of the `Link` record.
- `String name` requires the `name` component to have a non-`null` `String` value. `var next` infers the `Link` type from the record declaration; it **can** be `null`.
- On each iteration, `cursor = next` advances to the next node. At the end, `cursor == null`, so `instanceof Link(...)` is false and the loop terminates.
- `!name.isBlank()` also adds a stopping rule for empty or whitespace-only names. It is evaluated once `name` has matched the `String` pattern.
- If a `Link` has `name == null`, the pattern `String name` does not match, so the loop body does not run for that node. If you replace it with `var name`, the pattern can receive `null` and you must check `name != null` before calling `name.isBlank()`.

This traversal style works well when the entire chain of nodes has a clear structure. For systems using user-supplied linked lists, you also need to account for **cycles** (a node pointing back to a previous node): patterns do not detect cycles automatically, so you must have a limit or a mechanism to track visited nodes if the data is not guaranteed to terminate.

## 7. Advanced case: negated patterns and variables after the loop

Flow scoping has a notable case. When a `while` condition requires that **the pattern does not yet match**, and the loop body transforms the data until the pattern matches, the pattern variable can be used **after the loop terminates normally**:

~~~java
static String normalize(Object candidate) {
    while (!(candidate instanceof String text)) {
        candidate = "ready";
    }
    return text.toUpperCase(java.util.Locale.ROOT);
}
~~~

- The loop continues only while `candidate` **does not yet** match `String text`.
- When the loop terminates because the condition becomes `false`, that means `candidate instanceof String text` has matched.
- Java can prove `text` has a value at the subsequent `return` statement; for example, `normalize(5)` returns `"READY"`.

This is an **illustrative method**, used verbatim in the complete program in section 8.

This rule differs from `while (candidate instanceof String text)`: after a positive-pattern loop, the pattern may have failed, so `text` is **no longer** usable. In addition, **do not add a `break` branch** to a negated loop and assume `text` is still guaranteed to exist. A `break` can exit the loop before the pattern matches, preventing the compiler from guaranteeing that the pattern variable was assigned afterward.

The negated case is usually useful when the loop's actual job is to **search/transform until data of the right type is encountered**. Do not use it to create an infinite loop merely hoping the data will change on its own; the exit condition must still be clearly defined.

## 8. Complete Java 21 program

The following program demonstrates four scenarios: stopping at the first value of the wrong type, skipping values of the wrong type, traversing a record with a next node, and using a pattern variable after a negated loop.

Create the file **`WhilePatternDemo.java`**:

~~~java
public class WhilePatternDemo {
    record Link(String name, Link next) {}

    static void prefix(Object[] items) {
        int index = 0;
        while (index < items.length
                && items[index] instanceof String word
                && !word.isBlank()) {
            System.out.println("prefix=" + word);
            index++;
        }
        System.out.println("stopIndex=" + index);
    }

    static void filter(Object[] items) {
        int index = 0;
        while (index < items.length) {
            Object item = items[index++];
            if (!(item instanceof String word)) {
                continue;
            }
            if (word.isBlank()) {
                continue;
            }
            System.out.println("filtered=" + word);
        }
    }

    static void walk(Object first) {
        Object cursor = first;
        int visited = 0;
        while (cursor instanceof Link(String name, var next)
                && !name.isBlank()) {
            System.out.println("link=" + name);
            visited++;
            cursor = next;
        }
        System.out.println("linksVisited=" + visited);
    }

    static String normalize(Object candidate) {
        while (!(candidate instanceof String text)) {
            candidate = "ready";
        }
        return text.toUpperCase(java.util.Locale.ROOT);
    }

    public static void main(String[] args) {
        Object[] samples = {"java", "21", 42, "after", null, " "};

        prefix(samples);
        filter(samples);
        walk(new Link("A", new Link("B", null)));
        System.out.println("normalized=" + normalize(5));
    }
}
~~~

Compile and run with **JDK 21+**:

~~~bash
javac --release 21 WhilePatternDemo.java
java WhilePatternDemo
~~~

Output:

~~~text
prefix=java
prefix=21
stopIndex=2
filtered=java
filtered=21
filtered=after
link=A
link=B
linksVisited=2
normalized=READY
~~~

### Output analysis

1. `prefix` processes the first two strings, then stops at `42` with `index == 2`. The string `"after"` is not traversed in this method.
2. `filter` scans the entire array. It skips `42` and `null` because they do not match `String word`, skips `" "` because `isBlank()` is true, yet still prints `"after"`.
3. `walk` deconstructs two `Link` records in turn. The second node has `next == null`, so the loop stops after two iterations.
4. `normalize` receives the number `5`, switches it to the string `"ready"` on the first iteration, and terminates when the pattern matches; it can use `text` afterward, so it prints `"READY"`.

This program is **standalone**, containing the record type, methods, and `main` in a single file. The intentionally invalid snippets in other sections are only meant to explain errors and **do not appear** in the compilable file.

## 9. Testing edge cases

When using patterns in a `while` condition, do not test only the case where all values have the right type. You should test the following scenarios:

| Case | Expected behavior |
| --- | --- |
| First element already has the wrong type | The loop body using a positive pattern runs zero times |
| Middle element in the list has the wrong type | The prefix loop stops immediately; the filter loop can skip and continue |
| Input value is `null` | `instanceof` does not match; the pattern variable is not dereferenced |
| Element is an empty or whitespace-only `String` | The type pattern matches, but the guard `!word.isBlank()` makes the condition false |
| Index reaches array length | `index < items.length` is false; `items[index]` access is not evaluated |
| Record node has `next == null` | Finishes processing the current node, then stops on the next check |
| Record node has `name == null` | `Link(String name, var next)` does not match at that node |
| Source does not change in the loop body | Risk of an infinite loop if the pattern is always true |
| Using `continue` before the update step | Risk of repeatedly inspecting the same element |
| Using `break` in a loop with a negated pattern | You cannot assume the pattern variable has matched after `break` |

Problems involving mutable data sources or interference from other threads require additional testing for their specific synchronization mechanisms. Flow scoping only guarantees the scope and type of the pattern variable along valid execution paths; it does **not** replace concurrency control.

## 10. Common mistakes

**Mistake 1 — confusing pattern variable scope.** `word` exists in the `while` body when a positive pattern matches; do not use `word` after the loop as if it always had a value. A negated pattern can create scope after the loop when the exit condition proves the pattern matched, but each control-flow path must be considered.

**Mistake 2 — failing to update the checked value.** `while (object instanceof String s)` can loop forever if `object` does not change. The index, iterator, or current node must advance to a new state.

**Mistake 3 — reading past the end of an array.** Place the bounds check **before** accessing `items[index]` in the `&&` chain.

**Mistake 4 — changing `&&` to `||` without considering execution paths.** With `pattern || usePatternVariable`, the pattern variable may not have been created on the right-hand side. Choosing the operator depends on the logic to express and the guarantees of flow scoping.

**Mistake 5 — assuming `instanceof` filters all business rules.** `String word` checks the type; non-blank, length, or format conditions must be added explicitly. A record pattern checks structure; it does not automatically validate all data invariants.

**Mistake 6 — assuming every record component is non-`null`.** A pattern with `String name` does not match when `name == null`, whereas `var next` can accept `null`. If you use `var name`, check `name != null` before calling methods on `name`.

**Mistake 7 — skipping the first non-matching element when business logic requires handling it.** Using `iterator.next()` in the `while` condition can consume the value and then stop immediately. Separate the element-retrieval step if you need to handle the reason it is invalid.

**Mistake 8 — putting too many conditions in one loop.** If the expression gets long, extract a named helper method, use `if` checks/`continue` in the body, or separate traversal from data validation. Concise syntax is only valuable when it remains easy to read.

## 11. Practice exercises

**Exercise A:** Given the array `{"A", "B", 7, "C"}`, predict how many times the `while` body runs if the pattern is in the condition. Then modify the program to skip `7` and continue printing `"C"` without missing any element.

**Exercise B:** Replace the first element with `null`. Compare the version that stops on mismatch with the version that filters all data; explain why `instanceof String word` does not bind a pattern variable for a `null` value.

**Exercise C:** Create `Link("A", new Link("", new Link("C", null)))`. With the guard `!name.isBlank()`, which nodes does the loop print? Change the rule to skip blank names while still advancing to `"C"` without losing the `cursor = next` update step.

**Exercise D:** Modify `normalize` to accept an initial `String` value. Verify that the negated loop runs zero times yet the method still returns the uppercase result. Then try adding a `break` branch to the body and observe how the compiler analyzes the scope of `text` at the `return` statement.

**Takeaway:** Patterns in a `while` condition let you **check types, bind variables, and evaluate guards** right at the loop-continuation point. Use `&&` in a safe order, update data on every iteration, and choose deliberately between **stopping on mismatch** and **skipping non-matching elements**. With Java 21+, record patterns also let you traverse record structures and access components directly while still following flow-scoping rules.

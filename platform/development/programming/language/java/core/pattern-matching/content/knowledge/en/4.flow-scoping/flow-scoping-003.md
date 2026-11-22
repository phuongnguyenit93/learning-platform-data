# Pattern Variable Scope with the && Operator in Java

## 1. Goal: Using the Matched Variable Directly in a Condition

Pattern matching for **instanceof** combines a type check and the declaration of a variable with the corresponding type:

~~~java
if (value instanceof String text) {
    System.out.println(text.length());
}
~~~

When the match succeeds, the compiler knows **text** is a **String**; when the match fails, the variable **text** cannot be used on that path. This mechanism is called **flow scoping** (control-flow-dependent scoping), instead of allowing a pattern variable to appear everywhere simply because its name exists in the source code.

The logical **&&** operator is especially useful when you need to check an additional property of an object after confirming its type:

~~~java
if (value instanceof String text && !text.isBlank()) {
    System.out.println(text.strip());
}
~~~

The first condition guarantees **text** is a string; the second condition only runs when the first condition is true. Therefore, **text.isBlank()** is type-safe and requires no cast. This example is valid since **Java 16** and runs on **Java 17+** without enabling preview features.

## 2. Two Core Rules of &&

**Rule A — short-circuit evaluation.** For **left && right**, Java evaluates **left** first. If **left** is **false**, the entire **&&** expression is **false** and **right** is not evaluated. Only if **left** is **true** does Java evaluate **right**.

**Rule B — a pattern variable is only in scope when definitely matched.** For **value instanceof String text**, the compiler allows using **text** on the right-hand side of **&&** because the right-hand side only executes after the left-hand side returns **true**. If the entire **if** condition is true, the variable is also in scope in the **then** branch.

Example:

~~~java
if (value instanceof String text && text.length() >= 3) {
    System.out.println(text.toUpperCase());
}
~~~

How to read it from left to right:

1. If **value == null**, **instanceof** returns **false**, so **length()** is not called.
2. If **value** is a type other than **String**, **instanceof** returns **false**, so **length()** is not called either.
3. If **value** is a **String**, the compiler binds **text** to that object and then checks **text.length() >= 3**.
4. Only when both conditions are true does the **if** block execute and **text.toUpperCase()** is allowed to be used.

| Value of **value** | **instanceof String text** | Is **text.length() >= 3** evaluated? | Enter **if** branch? |
| --- | --- | --- | --- |
| **"Java"** | true | Yes; true | Yes |
| **"hi"** | true | Yes; false | No |
| **42** (Integer) | false | No | No |
| **null** | false | No | No |

Short-circuiting is a **runtime rule** of **&&**; flow scoping is a **compile-time rule** that uses that information to decide whether a pattern variable may be referenced. The two mechanisms are related but not identical.

## 3. Using Multiple && Clauses: Each Step Adds a Condition

After proving the type in the first clause, subsequent clauses can validate the same object:

~~~java
if (value instanceof String text
        && !text.isBlank()
        && text.strip().length() >= 3) {
    System.out.println("Chuỗi hợp lệ: " + text.strip());
}
~~~

The order of the three clauses is meaningful:

- **value instanceof String text**: only continues if there is a non-**null** **String** object.
- **!text.isBlank()**: only continues if the string is not entirely whitespace.
- **text.strip().length() >= 3**: only continues if the content after stripping leading and trailing whitespace has at least three Java **String** length units.

The last condition can also use **text** because the preceding clauses have already proven that the pattern matched. When one clause is false, all subsequent clauses are skipped. In real-world code, this helps avoid calling methods on a variable that might not have the right type, while also allowing you to collapse multiple levels of nested **if** statements.

The same logic written more verbosely:

~~~java
if (value instanceof String text) {
    if (!text.isBlank()) {
        if (text.strip().length() >= 3) {
            System.out.println("Chuỗi hợp lệ: " + text.strip());
        }
    }
}
~~~

Both forms have their place: **&&** makes sense when each clause is a short check contributing to a single decision; nested **if** statements are useful if each step has its own handling, multiple failure branches, or needs to report a specific reason.

## 4. Standalone Runnable Java 17 Example

Save the code below in a file named **AndFlowScopeDemo.java**:

~~~java
public class AndFlowScopeDemo {
    static String classify(Object value) {
        if (value instanceof String text
                && !text.isBlank()
                && text.strip().length() >= 3) {
            return "Hợp lệ: " + text.strip();
        }
        return "Bỏ qua";
    }

    static String normalizeAfterGuard(Object value) {
        if (!(value instanceof String text) || text.isBlank()) {
            return "Không có chuỗi";
        }
        return "Giá trị: " + text.strip();
    }

    public static void main(String[] args) {
        System.out.println(classify(" Java "));
        System.out.println(classify("hi"));
        System.out.println(classify(12));
        System.out.println(classify(null));

        System.out.println(normalizeAfterGuard("  ok "));
        System.out.println(normalizeAfterGuard("   "));
        System.out.println(normalizeAfterGuard(null));
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 AndFlowScopeDemo.java
java AndFlowScopeDemo
~~~

Exact output:

~~~text
Hợp lệ: Java
Bỏ qua
Bỏ qua
Bỏ qua
Giá trị: ok
Không có chuỗi
Không có chuỗi
~~~

**Explanation:** **classify(" Java ")** matches **String**, is not blank, and after **strip()** leaves **Java** with length **4**, so it returns **Hợp lệ: Java**. **"hi"** matches the type but fails the length check, **12** does not match **String**, and **null** does not match **instanceof**, so all three return **Bỏ qua**. For **normalizeAfterGuard**, the negated condition with **||** returns early if it is not a string or is a blank string; the path reaching **return "Giá trị: "...** therefore always has **text** matched.

**Version note:** type patterns in **instanceof** were standardized in Java 16. The program above only uses APIs such as **String.isBlank()** (Java 11+) and **String.strip()** (Java 11+), so it compiles on JDK 17. It does not use Java 21's pattern matching for **switch** feature.

## 5. Variable Scope Inside and Outside if

An important rule: having **text** present in the condition does not mean it is always present after the entire **if**.

**In the true branch:** valid, because the **&&** condition is only true if **instanceof** matched.

~~~java
if (value instanceof String text && text.length() >= 3) {
    System.out.println(text); // Valid
}
~~~

**In the else branch:** **text** cannot be used in general, because the **&&** condition could fail right at **instanceof**.

~~~java
if (value instanceof String text && text.length() >= 3) {
    System.out.println(text);
} else {
    System.out.println("Không thỏa điều kiện");
    // Cannot assume text is in scope in the else branch.
}
~~~

**After if:** if the false branch does not necessarily exit the method, the path after **if** can still be reached when the pattern has not matched, so **text** is not guaranteed to be in scope.

~~~java
if (value instanceof String text && text.length() >= 3) {
    System.out.println(text);
}
// Cannot assume text is in scope here.
~~~

**If there is an early-exit branch:** you can prove a pattern has matched by eliminating all non-matching cases before using it:

~~~java
// Illustrative snippet inside a void-returning method.
if (!(value instanceof String text)) {
    return;
}
System.out.println(text.length()); // Valid
~~~

When reviewing code, you must rely on **which control-flow paths can still reach the point of use**, not just on the nearest curly braces.

## 6. Comparing && with || and Negation

The following two expressions differ in where the pattern variable is allowed to appear.

**Valid:**

~~~java
if (value instanceof String text && text.length() > 0) {
    System.out.println(text);
}
~~~

When the right-hand side **text.length() > 0** must be evaluated, the left-hand side was already true, so **text** is bound.

**Invalid (intentionally broken example, do not put into a runnable program):**

~~~java
// COMPILE ERROR: if instanceof is false, the right-hand side of || runs,
// but at that point text is not guaranteed to exist.
if (value instanceof String text || text.isEmpty()) {
    System.out.println("...");
}
~~~

With **||**, the right-hand side only runs when the left-hand side is false. When **instanceof** is false, there is no basis for using **text** on the right-hand side. Conversely, **||** can be safely combined with a **negated pattern**, if the right-hand side is only evaluated when the negation is false:

~~~java
// Valid: when the right-hand side runs, !(instanceof...) is false,
// meaning instanceof succeeded and text is in scope.
if (!(value instanceof String text) || text.isBlank()) {
    return;
}
System.out.println(text.strip()); // Valid after the return branch
~~~

The last snippet is **illustrative code inside a void-returning method**, not a standalone program. Here **return** eliminates two kinds of input: not matching **String**, or matching but blank. After the **if**, the remaining path guarantees **text** is bound and not blank.

The key distinction to remember is not that **||** always forbids pattern variables, but that **every usage site must lie on a path where the pattern is definitely matched**.

## 7. Common Error-Prone Situations

### Using the Variable Before the Type Check

~~~java
// Wrong: text has not been declared in the preceding clause.
if (text.length() > 2 && value instanceof String text) {
    System.out.println(text);
}
~~~

Place the type pattern on the left-hand side, and only then use the variable in subsequent **&&** clauses. The compiler cannot use a check that will happen in the future to validate a clause evaluated earlier.

### Using || in the Wrong Direction

~~~java
// Wrong: when the left-hand side is false, text does not exist on the right-hand side.
if (value instanceof String text || text.startsWith("A")) {
    System.out.println("A");
}
~~~

To check that a **String** also satisfies a prefix condition, use **&&**. To check another condition independent of the type, separate the branches clearly and do not reference the pattern variable on an unmatched path.

### Confusing ! with a Positive Condition

~~~java
if (!(value instanceof String text)) {
    // Do not use text here: this is the non-matching branch.
} else {
    System.out.println(text.length()); // This branch matched
}
~~~

Negation flips which condition enters the branch; **text** is in scope wherever the compiler proves the inner **instanceof** was true, not based on the mere presence of the variable name in the expression.

### Ignoring null

**null instanceof String text** is always false, so **&&** does not call **text.isBlank()** and avoids calling a method on **null**. This is the behavior of the type check; if the application needs to report a separate error for null, you must add logic for that case.

### Confusing Type Matching with Content Validation

**value instanceof String text && !text.isBlank()** only guarantees a non-blank string. It does not guarantee the string is a valid email, URL, date, or business format. You need to add the corresponding validator. For secondary conditions with side effects, remember they only run when all preceding clauses return true.

### Using the Variable Where the Compiler Cannot Prove It

Assigning the condition's result to a boolean variable does not imply the pattern variable becomes available in all subsequent statements:

~~~java
boolean accepted = value instanceof String text && text.length() >= 3;
// accepted only stores true/false; you cannot arbitrarily use text here.
System.out.println(accepted);
~~~

The compiler tracks the relationship between patterns and control flow; it does not infer that an arbitrary boolean variable substitutes for full type proof at a new access site.

## 8. Guidelines for Writing and Reviewing Code

Use **instanceof T variable && additionalCondition(variable)** when you need to combine a type condition with one or a few short checks without complex side effects. Put the type check before method calls that depend on that type; put cheap, easy-to-read checks before more expensive ones when doing so does not change behavior.

If you need multiple distinct error results, multiple processing statements, or complex control flow, consider splitting into nested **if** statements or using guard clauses. This makes failure and success logic clearer during code review.

When testing your own code, test at least four cases: an object of the right type that satisfies the condition, one of the right type that fails the secondary condition, the wrong type, and **null**. Also verify that the right-hand expression is not evaluated when **instanceof** is false and that all pattern variable usages compile cleanly on the target JDK.

**Key takeaway:** the **&&** operator both supports left-to-right short-circuit evaluation and enables the compiler to allow using a pattern variable from **instanceof** in the right-hand clauses and the true branch. Flow scoping ensures the variable can only be accessed where a match is proven, making code more concise while remaining type-safe.
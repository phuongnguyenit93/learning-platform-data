# Combining `instanceof` Patterns with `&&` or Guard Clauses in Java 17

> **Java core — language-basics / Type Patterns**  
> **Environment:** Java 17+, self-contained single file, JDK only; preview disabled.  
> **Goal:** Combine type checks with additional conditions using `&&`; use early-return guard clauses to use pattern variables afterward; understand *flow scoping*, short-circuiting, and variable scope errors.

## 1. Practical Scenario: Validate Then Process Input

Suppose a function receives an `Object` from an API and only accepts strings with content. The type pattern `input instanceof String text` both checks the runtime type and binds the variable `text`; if it is `null` or another type, the pattern does not match.

~~~java
static boolean hasUsableName(Object input) {
    return input instanceof String name
            && !name.isBlank()
            && name.strip().length() <= 20;
}
~~~

The function returns `false` for `null`, integers, whitespace-only strings, or strings whose length after `strip()` exceeds 20 characters. Only for valid names are the later conditions evaluated. That exact order avoids needing a cast or a separate null check.

## 2. Choosing `&&` or a Guard Clause Based on the Task

If you only need a boolean answer like `hasUsableName`, chaining conditions with `&&` avoids nested branches. When you need to explain **why** an input is rejected (wrong type, empty string, data too long) or use the checked object across multiple steps, a guard clause is usually easier to read. Section 4 compares return paths; the complete program in Section 7 counts how many times an additional condition is actually called.

| Goal | Way to Write |
| --- | --- |
| Short validation rule, no rejection reason needed | Type pattern combined with `&&` |
| Return distinct error codes and perform multi-step processing | Guard `if (!(x instanceof T t)) return ...;` |
| Return one error if wrong type **or** fails additional condition | Negated guard combined with `||` |

For both approaches, the pattern variable can only be used when control flow guarantees a type match.

## 3. When Replacing `&&` with `&` or `||`

`&&` short-circuits: it does not evaluate the extra condition if the pattern fails. The `&` operator on `boolean` evaluates both sides, so `input instanceof String s & !s.isBlank()` does not compile: the compiler cannot guarantee `s` is bound on the right-hand side.

~~~java
Object input = " Java ";
// Valid: the additional condition only runs after String has matched.
boolean ok = input instanceof String s && !s.isBlank();

// Invalid: positive OR evaluates the right-hand side when the pattern fails.
// boolean bad = input instanceof String s || s.isBlank();
~~~

For the requirement "wrong type **or** blank string", inverting the pattern condition makes `||` appropriate: `!(input instanceof String text) || text.isBlank()`. In that case, the right-hand side runs only when the String pattern truly matched. The program in Section 7 places all three approaches side by side to show differences in results and call counts.

## 4. Guard Clause: Returning Early When the Type Is Wrong

When multiple steps must run after a type check, using a guard clause is usually more readable than multiple levels of nesting:

~~~java
static String normalize(Object input) {
    if (!(input instanceof String text)) {
        return "NOT_STRING";
    }

    if (text.isBlank()) {
        return "BLANK";
    }

    return text.trim().toUpperCase(java.util.Locale.ROOT);
}
~~~

If the input is not a String or is null, the first branch executes **return** immediately. To reach the `text.isBlank()` line, Java knows the pattern must have matched, so the pattern variable `text` can be used for the rest of the method.

If you replace `return` in the first guard with a statement that only logs and lets the program continue, Java **cannot guarantee** that `text` is bound on the subsequent lines.

| Task | Appropriate Approach |
| --- | --- |
| One type check and one short extra condition | `if (x instanceof String s && !s.isBlank())` |
| Distinguish wrong-type error from blank-string error | Negated guard, then check blank |
| Multiple consecutive operations on the checked object | Guard clause to reduce branch nesting |
| No need to use the pattern variable | `x instanceof String` is enough |

## 5. Negated Guard Combined with OR and Early Return

You can combine both rejection checks:

~~~java
static String accept(Object input) {
    if (!(input instanceof String text) || text.isBlank()) {
        return "REJECTED";
    }
    return "ACCEPTED:" + text.trim();
}
~~~

On the right-hand side of OR, `text` is valid because when that side is evaluated, the pattern has already matched. If the entire condition is true, the method returns. If execution continues, Java knows `input` is a String and `text` is not blank.

Although concise, this style can become hard to read with many conditions; when you need to return separate messages for each cause, split it into two guards as in Section 4.

Example with an interface:

~~~java
static String longSequence(Object input) {
    if (input instanceof CharSequence seq && seq.length() >= 3) {
        return "LEN:" + seq.length();
    }
    return "SHORT_OR_OTHER";
}
~~~

Both `String` and `StringBuilder` implement `CharSequence`. Patterns can be used with classes or interfaces, not only `String`.

## 6. Common Mistakes and Java 17 Limitations

- **`null` references:** With `Object missing = null;`, `missing instanceof String s` returns `false`; the pattern variable `s` is not usable on that path. **The literal `null instanceof String s` does not compile in Java 17**, because the pattern is unconditional with respect to the literal's static type. Use a reference variable holding null as in the example rather than writing the literal directly.
- **Using the pattern variable in the wrong place:** After a normal `if (x instanceof String s)`, do not assume `s` can be used outside the branch; let a guard with `return` or `throw` eliminate all non-matching paths.
- **Redundant pattern:** `String alreadyString = "x";` followed by `alreadyString instanceof String s` can be rejected in Java 17 because the static type is already a subtype of the pattern type. There is no need to check an already known type.
- **Erased generics:** You cannot directly check `instanceof java.util.List<String>`; use a runtime-checkable type like `List<?>` and inspect elements individually if needed.
- **Conditions with side effects:** The right-hand side of `&&` is not called when the left-hand side is false. If the right-hand side updates variables, logs, or throws an exception, switching to another operator can change behavior.
- **Not a replacement for business validation:** Matching String does not mean the string is non-empty, properly formatted, or within bounds.

Rule of thumb: keep expressions short, prefer meaningful variable names, and use guard clauses for multiple rejection conditions or multi-step processing.

## 7. Standalone Java 17+ Program

Create a file named **InstanceofAndGuardDemo.java**:

~~~java
import java.util.Locale;

public final class InstanceofAndGuardDemo {
    private static int checkCalls;

    private static boolean nonBlank(String text) {
        checkCalls++;
        return !text.isBlank();
    }

    private static String withAnd(Object input) {
        if (input instanceof String text && nonBlank(text)) {
            return "TEXT:" + text.trim().toUpperCase(Locale.ROOT);
        }
        return "NO_TEXT";
    }

    private static String withGuard(Object input) {
        if (!(input instanceof String text)) {
            return "NOT_STRING";
        }
        if (text.isBlank()) {
            return "BLANK";
        }
        return "TEXT:" + text.trim().toUpperCase(Locale.ROOT);
    }

    private static String withOrGuard(Object input) {
        if (!(input instanceof String text) || text.isBlank()) {
            return "REJECTED";
        }
        return "ACCEPTED:" + text.trim();
    }

    private static String sequenceLabel(Object input) {
        if (input instanceof CharSequence seq && seq.length() >= 3) {
            return "LEN:" + seq.length();
        }
        return "SHORT_OR_OTHER";
    }

    private static String display(Object value) {
        if (value == null) {
            return "null";
        }
        if (value instanceof String text) {
            return "\"" + text + "\"";
        }
        return value.getClass().getSimpleName() + ":" + value;
    }

    public static void main(String[] args) {
        Object[] inputs = {null, Integer.valueOf(7), "  ", " java ", "Hi"};

        for (Object value : inputs) {
            checkCalls = 0;
            String andResult = withAnd(value);
            int checks = checkCalls;
            String guardResult = withGuard(value);
            String orResult = withOrGuard(value);

            System.out.println("input=" + display(value)
                    + ";and=" + andResult
                    + ";checks=" + checks
                    + ";guard=" + guardResult
                    + ";or=" + orResult);
        }

        System.out.println("sequenceBuilder="
                + sequenceLabel(new StringBuilder("abc")));
        System.out.println("sequenceShort=" + sequenceLabel("Hi"));
        System.out.println("sequenceNull=" + sequenceLabel(null));
    }
}
~~~

Compile and run in the directory containing the file (Bash, PowerShell, or Command Prompt):

~~~bash
javac -encoding UTF-8 InstanceofAndGuardDemo.java
java InstanceofAndGuardDemo
~~~

**Exact expected stdout:**

~~~text
input=null;and=NO_TEXT;checks=0;guard=NOT_STRING;or=REJECTED
input=Integer:7;and=NO_TEXT;checks=0;guard=NOT_STRING;or=REJECTED
input="  ";and=NO_TEXT;checks=1;guard=BLANK;or=REJECTED
input=" java ";and=TEXT:JAVA;checks=1;guard=TEXT:JAVA;or=ACCEPTED:java
input="Hi";and=TEXT:HI;checks=1;guard=TEXT:HI;or=ACCEPTED:Hi
sequenceBuilder=LEN:3
sequenceShort=SHORT_OR_OTHER
sequenceNull=SHORT_OR_OTHER
~~~

`checks=0` for null or Integer shows that `nonBlank` **does not run** when the pattern fails. For a blank string, the pattern matches, so `nonBlank` runs exactly once and returns false. Guard clauses give specific rejection labels; the OR guard gives one shared rejection label.

## 8. Practice Exercises

**Exercise 1.** Predict the condition `x instanceof String s && s.length() >= 5` for `null`, `Integer`, a 2-character string, and a 6-character string; when does the right-hand side execute?

**Exercise 2.** Rewrite Exercise 1 using a guard clause, then use `s` outside the guard branch once a type match is guaranteed.

**Exercise 3.** Explain why checking a type and combining directly with OR does not allow using the pattern variable on the right-hand side, while negating the type check and combining with OR and `s.isBlank()` is valid.

**Exercise 4.** Put a counter in the additional condition function; test null, wrong type, empty String, and valid String inputs to observe the call count.

**Exercise 5.** Use the pattern `CharSequence seq` with `StringBuilder("abcd")` and `String("xy")`; determine the output when requiring a length of at least 3.

### Key Takeaway

**`x instanceof T name && predicate(name)`** is safe because the right-hand side runs only after the pattern matches. **`if (!(x instanceof T name)) return ...;`** is a guard clause that makes `name` usable in the remainder of the method. Pattern variable scope is checked along execution flow, not just by braces.

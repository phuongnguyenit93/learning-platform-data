# Replacing the cast after instanceof with pattern matching in Java

## 1. Why replace the cast?

When a variable is declared as **Object**, an interface, or a superclass, code sometimes has to check which subclass the actual object belongs to before calling specialized methods. Before Java 16, the common pattern consisted of two consecutive steps:

1. Check the type using **instanceof**.
2. Cast (**cast**) to the exact type just checked and assign it to a variable.

~~~java
static String formatLegacy(Object value) {
    if (value instanceof String) {
        String text = (String) value;
        return "Chuỗi: " + text.strip();
    }
    return "Kiểu khác";
}
~~~

The cast here is valid thanks to the condition directly above it, but the type name **String** is repeated and the reader has to match the condition against the cast line. When there are multiple **instanceof** branches, the casts add boilerplate code, making the handling branches longer and prone to errors when renaming types.

**Pattern matching for instanceof** allows checking the type and declaring a properly typed variable in a single expression:

~~~java
static String formatModern(Object value) {
    if (value instanceof String text) {
        return "Chuỗi: " + text.strip();
    }
    return "Kiểu khác";
}
~~~

Here **value instanceof String text** means: if **value** is a non-**null** **String** object, the variable **text** is bound to that same object and has static type **String**. There is no need to write **(String) value**.

The type pattern feature in **instanceof** was standardized in **Java 16** and is available in **Java 17**. This is a compile-time language change; there is no need to enable **--enable-preview**.

## 2. Syntax and basic rules

General structure:

~~~java
if (expression instanceof TargetType patternVariable) {
    // Use patternVariable as TargetType
}
~~~

- **expression** is the reference expression to be classified, for example **value**.
- **TargetType** is a reference type that can be checked at runtime, for example **String**, **Integer**, an interface, an array, or **List<?>**.
- **patternVariable** is the variable introduced when the match succeeds.
- **instanceof** returns **false** if expression is **null**; in that case, the pattern variable does not exist in the true branch.
- The pattern variable references **the exact object being checked**, not a copy. This pattern does not perform value conversion, such as from the string **"42"** to the number **42**.

Comparison:

| Task | Written with cast | Written with pattern |
| --- | --- | --- |
| Confirm **Object** holds a string | **value instanceof String** | **value instanceof String text** |
| Obtain a properly typed variable | **String text = (String) value;** | **text** is already available on match |
| Call a string method | **text.strip()** | **text.strip()** |
| Handle **null** | **instanceof** condition is false | **instanceof** condition is false |
| Variable scope | Follows manual declaration site | Follows control flow where the match is guaranteed true |

**Type safety did not start with pattern matching:** checking **instanceof** and then casting to the matching type was already safe. Pattern matching brings the type evidence and the variable usage closer together, reducing the chance of accidentally mismatching a condition with a cast on a distant line.

## 3. Complete Java 17 example: before and after

Save the file **ReplaceCastDemo.java**:

~~~java
public class ReplaceCastDemo {
    static String before(Object value) {
        if (value instanceof String) {
            String text = (String) value;
            return "text=" + text.strip();
        }
        if (value instanceof Integer) {
            Integer number = (Integer) value;
            return "next=" + (number + 1);
        }
        return "unknown";
    }

    static String after(Object value) {
        if (value instanceof String text) {
            return "text=" + text.strip();
        }
        if (value instanceof Integer number) {
            return "next=" + (number + 1);
        }
        return "unknown";
    }

    static int nonBlankLength(Object value) {
        if (value instanceof String text && !text.isBlank()) {
            return text.strip().length();
        }
        return 0;
    }

    static void printGuarded(Object value) {
        if (!(value instanceof String text)) {
            System.out.println("not string");
            return;
        }
        System.out.println("length=" + text.length());
    }

    public static void main(String[] args) {
        Object[] values = {" Java ", 7, null};
        for (Object value : values) {
            System.out.println(before(value) + " | " + after(value));
        }
        System.out.println("trimmed length=" + nonBlankLength("  ok "));
        printGuarded("Hello");
        printGuarded(42);
    }
}
~~~

Compile and run commands with **JDK 17+**:

~~~bash
javac -encoding UTF-8 ReplaceCastDemo.java
java ReplaceCastDemo
~~~

Output:

~~~text
text=Java | text=Java
next=8 | next=8
unknown | unknown
trimmed length=2
length=5
not string
~~~

**Output explanation:** **before** and **after** handle the three values identically. For **" Java "**, both strip leading/trailing whitespace and return **text=Java**. For **7**, both recognize the **Integer** object and return **next=8**. **null** matches no pattern and receives **unknown**. In **nonBlankLength**, the **&&** condition only checks **text.isBlank()** after the **String** match succeeds; **"  ok "** has content of length **2** after **strip()**. Finally, **printGuarded** demonstrates that the pattern variable remains valid after an early-exit branch.

What must be preserved during refactoring is **behavior**, not just line count. The **after** version produces the same output as **before** for these cases and still has a fallback branch for values that are neither **String** nor **Integer**.

## 4. Pattern variable scope: why can't it be used everywhere?

A cast creates a variable with the lexical scope of the code block. With a pattern, the compiler manages **flow scoping**: the variable name can only be used on execution paths where the compiler proves the match has succeeded.

**Case 1 — inside the true branch:**

~~~java
if (value instanceof String text) {
    System.out.println(text.length()); // Valid
}
// System.out.println(text.length()); // Invalid on the general path
~~~

**Case 2 — combining an additional check with &&:**

~~~java
if (value instanceof String text && !text.isEmpty()) {
    System.out.println(text.toUpperCase()); // Valid
}
~~~

The **&&** operator evaluates from left to right and short-circuits if the left-hand side is false. Therefore, the right-hand side only runs when **text** is guaranteed to be a **String**. Conversely, **value instanceof String text || text.isEmpty()** is invalid: the right-hand side of **||** can run precisely when the left-hand side is false, so **text** is not bound.

**Case 3 — negated check and early exit:**

~~~java
// Snippet inside a method returning void.
if (!(value instanceof String text)) {
    return;
}
System.out.println(text.length()); // Valid: guaranteed to have matched by this point
~~~

**Case 4 — else is not guaranteed:**

~~~java
if (value instanceof String text) {
    System.out.println(text.strip());
} else {
    System.out.println("Không phải String");
    // text is not in scope here.
}
~~~

Do not replace every cast via a text find/replace: check where the variable is used and the control flow of **if**, **else**, **return**, **throw**, **&&**, and **||** before editing.

## 5. Safe refactoring workflow

**Step 1.** Find a genuine repeated pattern: an **obj instanceof T** condition followed by **T local = (T) obj** in a branch where **obj** is not modified before the cast. If the checked expression and the cast expression differ, re-analyze before replacing.

**Step 2.** Change the condition to **obj instanceof T local**. Keep the semantically appropriate variable name and remove the now-redundant cast line.

**Step 3.** Keep operations using **local** within the scope accepted by the compiler. If an extra guard is needed, you can place **&&** right after the type pattern; if using an early-exit branch, ensure all paths reaching the subsequent code have matched.

**Step 4.** Preserve non-matching branches, **null** handling, condition order, and expected exceptions. Independent **if** branches are not automatically equivalent to **else if** branches if multiple conditions can be true simultaneously.

**Step 5.** Compile with the project's target JDK and run test cases with matching, non-matching, and null values. Only consider further optimizing branch logic after the refactoring is complete.

Short example with an interface:

~~~java
interface Printable {
    String render();
}

static String renderIfPossible(Object value) {
    if (value instanceof Printable printable) {
        return printable.render();
    }
    return "(không hỗ trợ)";
}
~~~

The snippet above is **illustrative code within a valid class/source scope**, not a standalone program with **main**. The pattern variable **printable** has type **Printable**, so only members belonging to this interface can be accessed; calling an implementation-specific method requires checking the corresponding type.

## 6. Common limitations and mistakes

- **Do not check erased generic type arguments:** **value instanceof java.util.List<?> items** can be used to identify a list and read **size()**. However, you cannot write **value instanceof java.util.List<String> items** to assert that all elements are strings; generic **String** type information is not fully retained at runtime.
- **Do not use type patterns for primitive types in Java 17:** for example, **value instanceof int number** is not a valid check. If the input is an **Object** holding an autoboxed integer value, check **Integer number**.
- **Does not match null:** **value instanceof String text** is **false** when **value == null**. Handle null separately if application behavior requires it.
- **Do not use the variable when the match might be false:** accessing the pattern variable in **else**, outside a proven branch, or on the right-hand side of **||** with a positive pattern will not compile.
- **Do not arbitrarily reorder logic:** if an earlier branch returns, converting to multiple branches or merging conditions can change the result.
- **Do not treat a pattern as a data conversion mechanism:** **String text** does not parse numbers or validate content. **text.strip()**, **Integer.parseInt(text)**, and business validations still need to be written explicitly.
- **Do not ignore version compatibility:** type patterns for **instanceof** have existed since Java 16. **switch** patterns standardized in Java 21 are a different topic; do not use that syntax in a Java 17 program.
- **Do not use patterns unnecessarily:** when a variable already has the appropriate static type, calling methods directly is usually clearer. For an expression whose static type is already known to be a subtype of the target pattern, Java may even reject an **instanceof** with a type pattern deemed unconditional.

## 7. Post-refactoring self-check

To know if the refactoring is correct, answer the following:

1. **Are the checked type and the old cast type truly the same T?** If not, it cannot be replaced mechanically.
2. **Is the pattern variable used in a location where the compiler guarantees it has a value?** If there is **||**, negation, or multiple branches, check flow scoping carefully.
3. **Do null inputs and other implementations still take the same branch as before?**
4. **Do casts involving generics or dynamic type handling require additional element checks?**
5. **Does the project compile with Java 16+ (for example JDK 17) and have tests covering the branches?**

Moving from **instanceof → manual cast** to **instanceof T variable** makes the branch's intent clear right at the condition, reduces boilerplate, and leverages the compiler's type and scope checks. It is most effective when applied to handling code that already has correct classification logic and tests protecting current behavior.
# Reusing Variable Names in Independent Branches in Java Pattern Matching

## 1. Fundamental Rule: Names Are Reused When Scopes Do Not Overlap

In Java, a **pattern variable** is a variable declared directly inside a pattern, such as `String item` in the expression `value instanceof String item`. When the pattern matches, the compiler allows using `item` in locations where control flow guarantees that the match succeeded. This mechanism is called **flow scoping**.

A useful property is that **two patterns in independent branches can use the same variable name**, provided the scopes of those declarations do not overlap. There is no rule requiring every pattern variable in the same method to have a different name.

Java 17 example:

```java
if (value instanceof String item) {
    System.out.println(item.toUpperCase());
} else if (value instanceof Integer item) {
    System.out.println(item + 1);
}
```

This is an **illustrative snippet inside a method with a variable `Object value`**, not a standalone program. Both branches use the name `item`, yet it is still valid:

- First branch: `item` has type `String`, used only when the `String item` pattern has matched.
- Second branch: `item` has type `Integer`, used only when the `Integer item` pattern has matched.
- The two `if/else if` branches are mutually exclusive in a single execution; each name is declared in its own scope region, so there is no conflict.
- If the value matches neither type, neither branch can use `item`.

**Spelling the name the same way does not mean it is the same variable.** The two declarations above create two different pattern variables with different static types, which can only be referenced in their respective locations.

## 2. Distinguishing Variable Name, Scope, and Program Paths

To decide whether a name can be reused, we need to distinguish three concepts:

1. **Name (identifier):** the sequence of characters chosen by the programmer, such as `item`, `text`, `number`.
2. **Declaration:** the place where Java creates a variable with a specific name and type, for example `String item` or `Integer item`.
3. **Scope:** the locations in the source code where that name refers to that declaration. For a pattern variable, its scope depends on the paths along which the match is definitely true.

In `if (value instanceof String item) { ... }`, `item` can be used in the body of the true branch. It is **not automatically** usable in `else` or after the entire `if`, because execution could have taken a path where it did not match.

Therefore, Java does not just look at whether two declarations appear in **the same method**. The compiler checks whether their effective scopes intersect. If they do not intersect, reusing the same name can be completely valid.

Independence here means **independence of declaration scopes**. The two branches do not necessarily have to be mutually exclusive at runtime: two consecutive `if` statements can both execute, yet still reuse the name because each pattern variable has its own scope.

## 3. Case 1: `if/else if` Branches Sharing the Same Name

```java
static String format(Object value) {
    if (value instanceof String data) {
        return "Text: " + data.strip();
    } else if (value instanceof Integer data) {
        return "Count: " + (data + 1);
    } else if (value instanceof Long data) {
        return "Long: " + data;
    }
    return "Unsupported";
}
```

This is an **illustrative method placed inside a Java 17+ class**.

In each branch, `data` has a different type:

| Matched branch | Pattern variable | Static type of `data` | Valid action |
| --- | --- | --- | --- |
| `value instanceof String data` | `data` of the first branch | `String` | `data.strip()` |
| `value instanceof Integer data` | `data` of the second branch | `Integer` | `data + 1` (unboxed automatically) |
| `value instanceof Long data` | `data` of the third branch | `Long` | Concatenate the value into a string |

With `value = " abc "`, Java enters the `String` branch and uses `data.strip()`. With `value = Integer.valueOf(7)`, Java enters the `Integer` branch and performs addition. Using the same name `data` helps the reader understand that each branch is processing *the type-confirmed value* of that specific branch.

**Do not infer that `data` can be used after the entire `if/else if` chain.** Cases like `value = null` or `value` being a `Double` will not match any pattern; there is no single `data` variable bound across all paths.

## 4. Case 2: Two Independent `if` Statements Can Also Use the Same Name

This case is more surprising:

```java
static void inspect(Object first, Object second) {
    if (first instanceof String part) {
        System.out.println("String length: " + part.length());
    }

    if (second instanceof Integer part) {
        System.out.println("Integer plus one: " + (part + 1));
    }
}
```

**These are two consecutive `if` statements**, not `if/else if`. If `first` is a `String` and `second` is an `Integer`, **both `if` bodies run**. Reusing `part` is still valid because:

- The first `part` is in scope along the path where `first instanceof String part` matches.
- After the first `if` statement, the first `part` is no longer in scope in this normal case.
- The second `part` is a new declaration, belonging to the `second instanceof Integer part` condition and the true branch of the second statement.

The key point to remember is **non-overlapping scopes**, not "only one branch is executed". There is no sharing or overwriting of the variable `part` between the two `if` statements.

If you want to use both values simultaneously outside the branches, declare variables with clear names and types in the shared scope, or move the logic into a method with appropriate parameter types. Do not expect a branch's pattern variable to automatically become a shared variable for the whole method.

## 5. Complete Java 17 Program

Create the file **`PatternVariableNameReuse.java`**:

```java
public class PatternVariableNameReuse {

    static String classify(Object value) {
        if (value instanceof String item) {
            return "String: " + item.toUpperCase();
        } else if (value instanceof Integer item) {
            return "Integer: " + (item + 1);
        } else if (value instanceof Long item) {
            return "Long: " + (item * 2);
        }
        return "Other";
    }

    static String evaluateBoth(Object left, Object right) {
        String result = "";

        if (left instanceof String item) {
            result = "S=" + item.length();
        }

        if (right instanceof Integer item) {
            result += (result.isEmpty() ? "" : " / ")
                    + "I=" + (item + 10);
        }

        return result.isEmpty() ? "None" : result;
    }

    public static void main(String[] args) {
        System.out.println(classify("java"));
        System.out.println(classify(7));
        System.out.println(classify(6L));
        System.out.println(classify(null));
        System.out.println(evaluateBoth("hi", 3));
        System.out.println(evaluateBoth(8, "no"));
    }
}
```

Compile and run with **JDK 17 or later**:

```bash
javac PatternVariableNameReuse.java
java PatternVariableNameReuse
```

Exact expected stdout:

```text
String: JAVA
Integer: 8
Long: 12
Other
S=2 / I=13
None
```

Explanation:

- `classify("java")` matches `String item`; the first branch uses `String.toUpperCase()`.
- `classify(7)` passes an `int` argument, which is autoboxed to `Integer` when received by the `Object` parameter; the second branch adds 1.
- `classify(6L)` passes a `long` value autoboxed to `Long`; the third branch multiplies by 2.
- `classify(null)` does not match any `instanceof` type pattern, so it returns `Other`.
- `evaluateBoth("hi", 3)` shows that both `if` statements run: the first `item` variable has type `String` and the second `item` variable has type `Integer`. The output values are accumulated into `result`, but **the two pattern variables are not a single variable**.
- `evaluateBoth(8, "no")` matches neither branch and returns `None`.

What can be reused is the **declaration name**, not the state or value of the previous pattern variable.

## 6. When Does the Same Name Cause a Compilation Error?

Java allows reusing a name in **non-overlapping** scopes. If a variable with that name is still in scope where a new pattern variable is declared, Java prevents the duplicate declaration.

### Error A: The name already belongs to an enclosing local variable

```java
static void conflict(Object input) {
    String item = "original";

    // Compilation error if uncommented:
    // if (input instanceof String item) {
    //     System.out.println(item);
    // }
}
```

Here, the local variable `item` is already declared in the method scope; a pattern test with a new `item` name will conflict. The fix is to choose a different name:

```java
static void valid(Object input) {
    String item = "original";

    if (input instanceof String matchedText) {
        System.out.println(item + ": " + matchedText);
    }
}
```

### Error B: The new pattern is inside the scope of an already-matched pattern

```java
static void nestedConflict(Object first, Object second) {
    if (first instanceof String item) {
        // Compilation error if uncommented:
        // if (second instanceof Integer item) {
        //     System.out.println(item);
        // }
    }
}
```

Inside the outer `if` body, `item` of type `String` is already in scope. Declaring another `Integer item` inside it will overlap. Fix this by using different names:

```java
static void nestedValid(Object first, Object second) {
    if (first instanceof String text) {
        if (second instanceof Integer number) {
            System.out.println(text + ": " + number);
        }
    }
}
```

### Error C: Two declarations overlapping across the `&&` operator

```java
static void andConflict(Object first, Object second) {
    // Invalid if uncommented:
    // if (first instanceof String part
    //         && second instanceof Integer part) {
    //     System.out.println(part);
    // }
}
```

The right-hand side of `&&` is only evaluated when the left-hand side is true; at that point, `part` from the left-hand side is already in scope. Declaring `part` again on the right-hand side will conflict. Use two separate names:

```java
static void andValid(Object first, Object second) {
    if (first instanceof String text
            && second instanceof Integer count) {
        System.out.println(text.repeat(count));
    }
}
```

This is a valid example regarding scope. In real application code, `count` should be validated to avoid negative values and excessively large repetitions; `String.repeat(int)` can throw an exception for negative arguments.

### Error D: Assuming the variable goes out of scope after every `if`

Flow scoping has an important case: **a pattern variable can remain in scope after an `if` when the non-matching path has terminated**.

```java
static void requireString(Object input, Object second) {
    if (!(input instanceof String item)) {
        return;
    }

    System.out.println(item.length()); // Valid.

    // Cannot declare another pattern variable named item:
    // if (second instanceof Integer item) {
    //     System.out.println(item);
    // }
}
```

After the statement `if (!(input instanceof String item)) return;`, the continuing path is proven by the compiler to have matched `String item`; therefore, `item` **is still in scope**. Reusing the name `item` in a new pattern below will conflict. This is why you cannot apply the rule of thumb "as soon as a closing `}` is reached, the pattern variable goes out of scope".

If you need a second pattern, rename it to `secondNumber` or reorganize the control flow for clarity.

## 7. Checking Conditions and Valid Scopes

Several cases can be confusing when reusing names:

| Construct | Reuse the same name? | Reason |
| --- | --- | --- |
| `if (x instanceof String p) {...} else if (x instanceof Integer p) {...}` | Yes | The two branches have separate, non-overlapping pattern scopes |
| `if (x instanceof String p) {...}` then `if (y instanceof Integer p) {...}` | Yes, for this basic structure | The scope of `p` from the first `if` does not extend to the second `if` |
| `String p = "..."; if (x instanceof String p) {...}` | No | Local name `p` already exists in the enclosing scope |
| `if (x instanceof String p) { if (y instanceof Integer p) {...} }` | No | The scope of the first `p` encloses the nested `if` |
| `if (x instanceof String p && y instanceof Integer p) {...}` | No | The first `p` is already in scope on the right-hand side of `&&` |
| `if (!(x instanceof String p)) return;` then declare a new `p` | No along this continuing path | The first `p` remains in scope after the guard clause |

The table assumes `x` and `y` have a broad reference type such as `Object` and there are no other declarations with the same name. Whether `p` can be used in an expression is also subject to the flow scoping rules of that expression itself; for example, `p` from `x instanceof String p` is not automatically available on the right-hand side of `||` when the left-hand side is false.

## 8. Extension: `switch` Pattern Branches in Java 21

Starting in **Java 21**, pattern matching for `switch` is an official feature. Pattern variable names can also be reused across independent **switch rules** using the arrow `->` syntax.

The following example is an **illustrative method for Java 21+**, placed inside a class:

```java
static String describe(Object value) {
    return switch (value) {
        case null -> "Null";
        case String item -> "Text length: " + item.length();
        case Integer item -> "Integer: " + item;
        default -> "Other";
    };
}
```

The two `item` variables in `case String item` and `case Integer item` belong to two separate rule branches. In the first branch, `item` has type `String`; in the second branch, `item` has type `Integer`. This follows the same principle of **non-overlapping scopes**, but in the context of `switch`.

Do not generalize the example above to all forms of `switch` using traditional `case:` labels, where scoping rules and fall-through between statement groups can differ. The arrow-rule `switch` form keeps each branch focused and easy to read.

**Version distinction:** Java standardized pattern matching for `instanceof` in Java 16, so the `if` examples run on Java 17. The pattern `switch` example here requires Java 21 or newer.

## 9. When to Reuse a Name and When to Use Distinct Names?

Reusing a short name like `item` or `value` makes sense when:

- Independent branches all express "the value that matched the type of the current branch".
- Each branch is short, uses the variable only right there, and the variable's type is clear from the pattern.
- A shared name helps the reader compare branches without having to remember many new names.

You should use distinct names such as `text`, `number`, `user`, `order` when:

- Two or more pattern variables need to be used **at the same time** in a condition or block.
- Nested branches or guard clauses extend the scope and may cause conflicts.
- The variables carry different business meanings; meaningful names help prevent data mix-ups, even if Java allows sharing the name.

Do not alter control flow just to reuse a name. **Clarity and non-overlapping scopes** matter more than reducing the number of variable names.

## 10. Self-Check Exercise

Consider the following two snippets, both placed inside a method with `Object first` and `Object second`.

**Snippet A:**

```java
if (first instanceof String data) {
    System.out.println(data.length());
}
if (second instanceof Integer data) {
    System.out.println(data + 1);
}
```

**Snippet B:**

```java
if (first instanceof String data) {
    if (second instanceof Integer data) {
        System.out.println(data);
    }
}
```

**Question:** Which snippet compiles in Java 17? Why?

**Answer:** **A is valid** because the two `data` pattern variables are in branches with separate scopes, even though both branches can execute in the same method call. **B is invalid** because when entering the outer branch body, `data` of type `String` is still in scope; declaring `data` of type `Integer` in the nested branch causes a name overlap. Renaming the inner variable to `number` resolves the conflict.

**Key takeaway:** Java allows reusing a pattern variable name when **the scopes of the declarations are independent and non-overlapping**. To evaluate this accurately, you must trace the paths of pattern matching, especially in `if/else if`, `&&`, nested blocks, and guard clauses with `return` or `throw`.
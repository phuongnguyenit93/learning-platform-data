# Left-to-Right Associativity of the `+` Operator with Numbers and Strings in Java

## 1. Lesson objectives

The `+` operator in Java has two important roles:

- **Numeric addition** when the operands are numeric types and numeric addition applies.
- **String concatenation** when one of the two operands of `+` is `String`.

Consecutive `+` operations at the same precedence level have **left associativity**: Java groups them from left to right, unless parentheses or higher-precedence operators change the grouping.

Therefore:

```java
System.out.println(1 + 2 + "3");  // 33
System.out.println("1" + 2 + 3);  // 123
```

The two expressions contain similar symbols, yet produce different results. The key insight is that **each `+` sign is processed based on the type of the result at that point in the expression**, rather than every `+` automatically turning into concatenation just because a `String` appears somewhere.

After this lesson you will be able to:
1. Read `+` expressions accurately in left-to-right associativity order.
2. Distinguish numeric addition before string concatenation from string concatenation right from the start.
3. Use parentheses deliberately to produce the desired result.
4. Avoid confusing associativity with **operator precedence** or **operand evaluation order**.
5. Recognize error-prone cases with `char`, `null`, `+=`, numeric types, and integer overflow.

## 2. Core rule: one `+` operator, two semantics

In a Java expression, numeric addition applies to suitable numeric operands. When **one operand of `+` is `String`**, the operation is **string concatenation**. The other value is converted to string form according to string concatenation conversion rules.

Examples:

| Expression | Meaning at the `+` sign | Result |
| --- | --- | --- |
| `1 + 2` | Add two `int` numbers | Number `3` |
| `1 + 2.5` | Numeric addition, with numeric type promotion | Number `3.5` |
| `"1" + 2` | Concatenate string `"1"` and number `2` | String `"12"` |
| `1 + "2"` | Concatenate `"1"` and `"2"` | String `"12"` |
| `"Hi " + "Java"` | Concatenate two strings | String `"Hi Java"` |

Once a `+` operation produces a `String`, if that result stands on the left side of a subsequent `+`, the next operation generally continues **string concatenation**.

```java
String text = "A" + 1;      // "A1"
String longer = text + 2;   // "A12"
```

Note that `"A" + 1 + 2` does not add `1 + 2` first. `+` operations at the same level are grouped from left to right, unless parentheses or a higher-precedence operator alters the grouping.

## 3. Left associativity: reading step by step

Consider these expressions:

### Case A: numeric addition first, then string concatenation

```java
String a = 1 + 2 + "3";
```

With left associativity, the grouping is:

```text
(1 + 2) + "3"
   3     + "3"
       "33"
```

At the first `+`, both operands are integers, so the result is the **number 3**. The next operation has `String "3"`, yielding the **string "33"**.

### Case B: string concatenation from the start

```java
String b = "1" + 2 + 3;
```

Grouping:

```text
("1" + 2) + 3
    "12"   + 3
       "123"
```

The first `+` produces `String "12"`. The next `+` concatenates the number `3` into the string `"123"`, **not** adding `2 + 3`.

### Case C: string in the middle

```java
String c = 1 + "2" + 3;
```

Grouping:

```text
(1 + "2") + 3
    "12"    + 3
        "123"
```

Because the first operation already has a `String` operand, it concatenates strings from the beginning. The final result is also `"123"`, even though `1` and `3` are numbers.

Comparison table:

| Expression | Interpretation | String result |
| --- | --- | --- |
| `1 + 2 + "3"` | `(1 + 2) + "3"` | `"33"` |
| `"1" + 2 + 3` | `("1" + 2) + 3` | `"123"` |
| `1 + "2" + 3` | `(1 + "2") + 3` | `"123"` |
| `1 + 2 + "3" + 4` | `((1 + 2) + "3") + 4` | `"334"` |
| `"1" + 2 + 3 + 4` | `((("1" + 2) + 3) + 4)` | `"1234"` |

**How to predict:** move from left to right across `+` operations at the same level, always tracking the type of the **intermediate result**: while still numeric, it can continue numeric addition; once it becomes `String`, `+` with the next value performs string concatenation.

## 4. Parentheses control numeric addition

To display the **sum** of two numbers inside a string, use parentheses:

```java
int a = 10;
int b = 20;

System.out.println("Sum = " + a + b);     // Sum = 1020
System.out.println("Sum = " + (a + b));   // Sum = 30
```

The expression `"Sum = " + a + b` is interpreted as `("Sum = " + a) + b`, so the numbers are converted to strings one after another.

In `"Sum = " + (a + b)`, Java evaluates `a + b` first, producing the number `30`, and then concatenates that number to the string.

Parentheses can also produce different results in the earlier examples:

```java
System.out.println(1 + (2 + "3")); // 123
System.out.println("1" + (2 + 3)); // 15
```

Explanation:
- `2 + "3"` → `"23"`, then `1 + "23"` → `"123"`.
- `2 + 3` → number `5`, then `"1" + 5` → `"15"`.

**Practical rule:** when concatenating a label with the result of a numeric expression, write `"Label: " + (numericExpression)`. This states intent clearly and prevents bugs caused by misreading a chain of `+` operators.

## 5. Operator precedence is different from associativity

Left associativity applies when `+` operators have the **same precedence level**. It does not override the precedence of other operators.

The `*` operator has higher precedence than `+`:

```java
System.out.println(1 + 2 * 3 + "4");  // 74
System.out.println("1" + 2 * 3);      // 16
```

In the first line:
1. `2 * 3` → number `6`.
2. `1 + 6` → number `7`.
3. `7 + "4"` → string `"74"`.

In the second line, `2 * 3` → number `6`, then `"1" + 6` → string `"16"`.

Parentheses can change this:

```java
System.out.println((1 + 2) * 3 + "4"); // 94
System.out.println("1" + (2 + 3));     // 15
```

This means you cannot apply a rule of “reading the entire expression strictly in order of appearance” when `*`, `/`, parentheses, or other operators are present.

### Note on the subtraction operator

`+` can perform string concatenation, but `-` has **no** equivalent for `String`:

```java
// Does not compile:
// System.out.println("Result: " + 10 - 3);
```

Java groups from left to right: `("Result: " + 10) - 3`. After the first `+`, the left-hand side of `-` is `String`, making subtraction invalid.

Correct way to write it:

```java
System.out.println("Result: " + (10 - 3)); // Result: 7
```

Parentheses both express intent and prevent the `String` type from appearing too early in the calculation.

## 6. Distinguishing associativity from operand evaluation order

These two concepts are related, yet **not the same**:

- **Associativity** specifies how operators at the same precedence level are grouped: `a + b + c` is grouped as `(a + b) + c`.
- **Evaluation order** specifies which subexpression is evaluated first during computation. Java guarantees that operands of binary operators are evaluated in left-to-right order.

Example:

```java
static int first() {
    System.out.print("A ");
    return 1;
}

static int second() {
    System.out.print("B ");
    return 2;
}

static String third() {
    System.out.print("C ");
    return "3";
}
```

When called inside a method:

```java
String result = first() + second() + third();
System.out.println(result);
```

Output:

```text
A B C 33
```

The three methods are called in left-to-right order: `first`, `second`, `third`. Then the returned values form `1 + 2 + "3"` → `"33"`.

Note: although the compiler or JVM may optimize how string concatenation is implemented, the program must still preserve Java's **observable behavior**, including subexpression order and exceptions as defined by the specification.

### Parentheses can change grouping, but do not necessarily change call order

`a + (b + c)` causes `b + c` to be grouped before the outer `+`, yet Java still evaluates operand `a` before evaluating the right-hand operand `(b + c)`. Do not confuse **the grouping order of operations** with **the call order of functions with side effects**.

## 7. Standalone Java 17+ program

Save as `PlusAssociativityDemo.java`:

```java
public class PlusAssociativityDemo {
    static int first() {
        System.out.print("A ");
        return 1;
    }

    static int second() {
        System.out.print("B ");
        return 2;
    }

    static String third() {
        System.out.print("C ");
        return "3";
    }

    public static void main(String[] args) {
        System.out.println("A = " + (1 + 2 + "3"));
        System.out.println("B = " + ("1" + 2 + 3));
        System.out.println("C = " + (1 + "2" + 3));

        System.out.println("sum wrong = " + 10 + 20);
        System.out.println("sum correct = " + (10 + 20));

        System.out.println("parentheses = "
                + ("1" + (2 + 3)));
        System.out.println("precedence = "
                + (1 + 2 * 3 + "4"));

        System.out.println("char as number = " + ('A' + 1));
        System.out.println("char in string = " + ('A' + "1"));

        String text = "x";
        text += 1 + 2;
        System.out.println("compound = " + text);

        String other = "x";
        other = other + 1 + 2;
        System.out.println("normal = " + other);

        System.out.print("evaluation = ");
        String evaluation = first() + second() + third();
        System.out.println(evaluation);
    }
}
```

Compile and run:

```bash
javac -encoding UTF-8 PlusAssociativityDemo.java
java PlusAssociativityDemo
```

Exact output:

```text
A = 33
B = 123
C = 123
sum wrong = 1020
sum correct = 30
parentheses = 15
precedence = 74
char as number = 66
char in string = A1
compound = x3
normal = x12
evaluation = A B C 33
```

**Explanation of three easy-to-confuse points in the program:**

1. `'A' + 1` is **numeric addition**, because `char` can be promoted to `int` in numeric operations: the code of `'A'` is `65`, so the result is `66`. Meanwhile `'A' + "1"` is string concatenation `"A1"`.
2. `text += 1 + 2` produces `"x3"`, because the right-hand expression `1 + 2` is evaluated to `3` before being concatenated with the old value of `text` in the compound assignment. However, `other = other + 1 + 2` has `+` operations chained on the right-hand side, left-associating into `"x12"`.
3. `first()`, `second()`, and `third()` are all invoked in left-to-right order, and their return values yield `"33"`.

## 8. Special case: `char` combined with `+`

When no `String` is present yet, `char` is promoted to a number before addition; when paired with a `String`, it is concatenated as a character:

```java
System.out.println('A' + 'B' + "");  // 131
System.out.println("" + 'A' + 'B');  // AB
```

Constant narrowing rules, `char +=`, Unicode code points, and `println` calls are practiced in the lesson **Distinguishing character arithmetic addition from string concatenation**.

## 9. `null` and non-string values

A `null` `String` reference is still converted to the text `"null"` when participating in concatenation: `"x=" + ((String) null)` yields `"x=null"`. The `+` sign does not drop missing values automatically. With real data, decide whether to substitute a label, omit, preserve missing state, or reject before concatenation; the lesson **concat and null argument differences** explores API contracts in depth.

## 10. `+=` does not behave like every expression written with `+`

An easily misunderstood question is:

```java
String a = "x";
a += 1 + 2;
```

Many people guess `"x12"` because they see a string on the left. However, `+=` is **compound assignment**; the right-hand side is an independent expression `1 + 2`, which evaluates to the **number `3`**. Java then concatenates that number onto the old value of `a`:

```text
a += (1 + 2)
a = "x" + 3
a = "x3"
```

Comparison:

```java
String a = "x";
a += 1 + 2;         // "x3"

String b = "x";
b = b + 1 + 2;      // "x12"

String c = "x";
c = c + (1 + 2);    // "x3"
```

The key point is not a special rule exclusively for `String`, but rather the difference between **the right-hand expression of a compound assignment** and **a plain chain of `+` operations**.

The immutability of a `String` value also means `a += ...` does not modify the old string's content; instead, it creates a result string to reassign to variable `a`. If you perform many concatenations in a loop, consider `StringBuilder`.

## 11. Integer overflow happens before string concatenation

String concatenation does not make numeric addition that happened earlier immune to overflow.

```java
int max = Integer.MAX_VALUE;

System.out.println(max + 1 + ""); // -2147483648
System.out.println("" + max + 1); // 21474836471
```

Explanation:
- `max + 1 + ""` adds `int` values first, so the `int` result overflows from `2147483647` to `-2147483648`, and is then concatenated with the empty string.
- `"" + max + 1` starts with string concatenation, producing the text `"2147483647"` and then appending the digit `1`; the result `"21474836471"` is not a numeric calculation.

If you need to compute in a larger numeric range, promote the type **before adding**, for example:

```java
long result = (long) max + 1;
System.out.println("Result = " + result); // Result = 2147483648
```

Do not use “early string concatenation” as a substitute for numeric computation: it only produces text, and does not fix arithmetic or business overflow bugs.

## 12. Common mistakes and how to fix them

| Mistake | Error-prone example | Clear way to write it |
| --- | --- | --- |
| Thinking all numbers in an expression with a string are added first. | `"sum=" + a + b` | `"sum=" + (a + b)` when the sum is needed. |
| Thinking `+` always concatenates left to right regardless of precedence. | `"x" + 2 * 3` | Understand `*` runs before concatenation: `"x6"`. |
| Not tracking when the intermediate result becomes `String`. | `1 + 2 + "3"` vs `"1" + 2 + 3` | Track the type after each `+` sign. |
| Trying to subtract directly after a string concatenation result. | `"x" + 10 - 3` | `"x" + (10 - 3)`. |
| Treating `char + char` as joining two characters. | `'A' + 'B'` | `"" + 'A' + 'B'` or `StringBuilder`. |
| Treating `+=` like any regular chain of `+` operations. | `text += 1 + 2` | Remember the right-hand side `1 + 2` is numeric addition first. |
| Believing string concatenation prevents overflow. | `max + 1 + ""` | Use `long` or an appropriate numeric type before adding. |
| Assuming concatenation makes `null` disappear. | `"x" + nullable` | Specify an explicit `null` policy. |
| Concatenating strings repeatedly in a loop. | `result = result + part` | Use `StringBuilder` when building content incrementally. |

## 13. Performance and compiler behavior

Associativity and the meaning of `+` are Java language rules, independent of bytecode shape. The compiler may fold constants and modern JDKs may use `invokedynamic`, but observable behavior cannot change. Building strings repeatedly in a loop is a separate performance problem: see the lesson **Concatenation in a single expression vs. accumulation across loops**.

## 14. Output prediction exercises

### Exercise 1

```java
System.out.println(3 + 4 + "5");
System.out.println("3" + 4 + 5);
System.out.println(3 + "4" + 5);
```

**Answer:**

```text
75
345
345
```

The first line adds numbers `3 + 4 = 7` and then concatenates `"5"`. The next two lines concatenate strings starting from the very first `+`.

### Exercise 2

```java
System.out.println("total=" + 4 * 5 + 2);
System.out.println("total=" + (4 * 5 + 2));
```

**Answer:**

```text
total=202
total=22
```

On the first line, `4 * 5` produces the number `20`, then `+` with the string produces `"total=20"` and concatenates `2` into `"total=202"`. The second line uses parentheses to compute `4 * 5 + 2 = 22` first.

### Exercise 3

```java
System.out.println('A' + 'B');
System.out.println("" + 'A' + 'B');
```

**Answer:**

```text
131
AB
```

Two `char` values are added numerically on the first line; the second line starts with an empty string, switching `+` to string concatenation.

### Exercise 4

```java
String x = "N";
x += 2 + 3;
System.out.println(x);

String y = "N";
y = y + 2 + 3;
System.out.println(y);
```

**Answer:**

```text
N5
N23
```

`x += 2 + 3` evaluates the right-hand side `2 + 3` first; `y + 2 + 3` concatenates left to right starting from `y`.

### Exercise 5

```java
System.out.println(1 + (2 + "3"));
System.out.println("1" + (2 + 3));
```

**Answer:**

```text
123
15
```

Parentheses change whether the subexpression yields a `String` or a number, thereby changing the result of the outer `+`.

### Exercise 6: fix the error

The following snippet does not compile:

```java
// String text = "Remaining = " + 10 - 3;
```

**Fix:**

```java
String text = "Remaining = " + (10 - 3);
System.out.println(text); // Remaining = 7
```

`+` with `String` produces a string; arithmetic `-` cannot be applied directly to that result.

## 15. Takeaways

- `+` performs **numeric addition** when both operands are suitable numbers; when there is a `String` operand, it is **string concatenation**.
- `+` operations at the same precedence level are **left-associative**: `a + b + c` is grouped as `(a + b) + c`.
- `1 + 2 + "3"` → `"33"`, whereas `"1" + 2 + 3` → `"123"`.
- Parentheses can force a numeric addition to occur before concatenation, e.g., `"sum=" + (a + b)`.
- Precedence (`*` before `+`), associativity, and operand evaluation order are **three distinct concepts**.
- `char + char` is numeric addition if no `String` is present; `+=` has its own compound assignment semantics.
- A numeric addition performed **before** string concatenation can still overflow.
- For expressions with multiple components, prefer parentheses and intermediate variable names so readers can clearly see the intent.

## References

- [Java Language Specification `15.18 — Additive Operators`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.18)
- [Java Language Specification `15.7 — Evaluation Order`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.7)
- [Java Language Specification `15.26 — Assignment Operators`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.26)
- [Java SE 17 — `StringBuilder`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/StringBuilder.html)

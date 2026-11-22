# Pattern Dominance in Java 21

## 1. What is dominance, and why might a switch fail to compile?

**Pattern dominance** (the subsumption/shadowing relationship between patterns) is a key rule of **pattern matching for switch** in Java 21. A later `case` label is *dominated* if an earlier `case` label already covers all values that the later label could accept, according to the rules the compiler is permitted to determine.

Example:

```java
// INTENTIONALLY NON-COMPILING SNIPPET
Object input = "Java";

switch (input) {
    case CharSequence sequence -> System.out.println("text-like");
    case String text -> System.out.println("string"); // Dominated!
    default -> System.out.println("other");
}
```

Because `String` implements `CharSequence`, every `String` matches `CharSequence sequence`. The subsequent `String text` branch can never be selected: the compiler reports a **dominated case label** error.

Fix this by placing the **narrower** pattern first:

```java
switch (input) {
    case String text -> System.out.println("string");
    case CharSequence sequence -> System.out.println("text-like");
    default -> System.out.println("other");
}
```

**Key point:** dominance is evaluated based on **the values a pattern can match**, not on how variables are named. Renaming `sequence` to `s` does not solve the error; you must change the order or the coverage scope of the branches.

In Java 21, type patterns, record patterns, and pattern matching for `switch` are all **standard** features, with no need to enable `--enable-preview`.

## 2. Putting dominance in context

A pattern `switch` typically has several kinds of labels:

```java
return switch (input) {
    case null -> "missing";
    case String s when s.isBlank() -> "blank";
    case String s -> "string";
    case Number n -> "number";
    default -> "other";
};
```

Distinguish clearly:

- `String s`, `Number n`: **type patterns**.
- `String s when s.isBlank()`: **guarded case pattern**; the guard is evaluated **after** the type pattern matches.
- `case null`: a dedicated label for the `null` value.
- `default`: the fallback label, not a type pattern.
- `s`, `n`: **pattern variables**; their names do not affect the type relationship between patterns.

Dominance is primarily a **compile-time validity constraint**: if the compiler can prove that a later label is completely shadowed by an earlier label according to the JLS rules, the switch will be rejected. However, **not every overlap is a compile-time error**. Two branches can both accept some values without either covering *all* of the other; in that case, **case order** determines the behavior for the overlapping subset.

### Four questions during review

1. Which pattern appears **first**?
2. Which values match the **later** pattern?
3. Does the earlier pattern match **all** of those values, according to the JLS?
4. Is there a guard? Does the guard cause the earlier label to be considered **guarded** rather than unguarded?

If the answer to question 3 is yes and the earlier label is an **unguarded** pattern, the later label is usually dominated. Beyond pattern-vs-pattern, the JLS also has specific rules for **constants**, **default**, and **null/default**.

## 3. Parent–child type patterns: place subtype before supertype

Example hierarchy:

```text
Object
  |
  +-- CharSequence
  |      |
  |      +-- String
  |      +-- StringBuilder
  |
  +-- Number
         |
         +-- Integer
         +-- Double
```

For type patterns, a type pattern with a sufficiently broad type can dominate a type pattern with a narrower type. For example:

| Earlier case | Later case | Result |
| --- | --- | --- |
| `case Object object` | `case String text` | **Invalid**: `Object` covers `String` |
| `case CharSequence chars` | `case String text` | **Invalid**: `String` is a `CharSequence` |
| `case Number number` | `case Integer integer` | **Invalid**: `Integer` is a `Number` |
| `case String text` | `case CharSequence chars` | **Valid**: subtype before supertype |
| `case Integer integer` | `case Number number` | **Valid**: subtype before supertype |
| `case String text` | `case Integer integer` | **No dominance between these two types** |

Recommended pattern:

```java
static String classify(Object value) {
    return switch (value) {
        case null -> "null";
        case String text -> "String";
        case CharSequence chars -> "other CharSequence";
        case Integer integer -> "Integer";
        case Number number -> "other Number";
        default -> "other";
    };
}
```

Here `String` comes before `CharSequence`, and `Integer` comes before `Number`. If `case Object object` is used as the last branch, it can cover all other objects; in that case, you must not add a `default` after it because an **unconditional type pattern** can dominate `default`.

### 3.1. Based on types, not variable names

```java
case Number payment -> ...
case Integer invoice -> ... // Dominated
```

Even though `payment` and `invoice` suggest two different concepts, the subsumption relationship is **`Integer` <: `Number`**. If two business roles are truly distinct, represent them with **separate domain types**, rather than expecting local variable names to make patterns distinguish them.

### 3.2. Interfaces also participate in dominance

It is not only class inheritance:

```java
case java.util.Collection<?> values -> "collection";
case java.util.List<?> list -> "list"; // Dominated
```

`List` extends `Collection`; therefore, place `List` before `Collection` if lists need special handling. The `?` arguments are generic wildcards; they do not help distinguish two list types by element type at runtime.

## 4. Type pattern and record pattern: a general type can shadow deconstruction

A record pattern is used to test a record and its components:

```java
record Parcel(Object item) {}
```

A type pattern matching any `Parcel` can shadow a record pattern of the same record if it comes first:

```java
// INTENTIONALLY NON-COMPILING SNIPPET
return switch (value) {
    case Parcel parcel -> "any parcel";
    case Parcel(String text) -> "parcel text: " + text; // Dominated
    default -> "other";
};
```

Every value matching `Parcel(String text)` is a `Parcel` and already matches `Parcel parcel`. The compiler does not need to know what `text` is to conclude this.

**Fix:** place the record pattern branch with specific structural constraints first, and the general type pattern branch after:

```java
return switch (value) {
    case Parcel(String text) -> "parcel text: " + text;
    case Parcel parcel -> "other parcel";
    default -> "other";
};
```

The `Parcel(String text)` branch only matches a `Parcel` whose `item` component matches `String`. The remaining `Parcel parcel` branch catches other `Parcel` instances.

### 4.1. A record pattern is not identical to a type pattern

- `Parcel parcel` checks the **record type** and binds the whole object.
- `Parcel(String text)` also checks the **component** and binds `text`.
- `Parcel(Object item)` is also a **record pattern**: it deconstructs `item`, even though the component pattern has a very broad type.

Do not assume every `Parcel(...)` record pattern is automatically equivalent to `Parcel parcel`. Coverage also depends on **the type and each component pattern**.

## 5. Dominance between two record patterns: component-by-component comparison

Given:

```java
record Pair(Object left, Object right) {}
```

A record pattern with broader component patterns can dominate another record pattern of the **same record class**:

```java
// INTENTIONALLY NON-COMPILING SNIPPET
return switch (value) {
    case Pair(Object left, Object right) -> "general pair";
    case Pair(String left, String right) -> "two strings"; // Dominated
    default -> "other";
};
```

The `Pair(Object, Object)` record pattern can match every `Pair`, and both `Object` components are broad enough to cover `String` at each position. The later branch is shadowed.

Fix:

```java
return switch (value) {
    case Pair(String left, String right) -> "two strings";
    case Pair(Object left, Object right) -> "general pair";
    default -> "other";
};
```

### 5.1. More precise rule for record patterns

According to JLS 21 §14.30.3, two record patterns have a dominance relationship when they refer to the same **record class** and each component pattern of the earlier record dominates the component pattern at the **corresponding position** of the later record.

For example:

```java
case Pair(Object left, String right) -> ...
case Pair(String left, String right) -> ... // Dominated
```

Because the first component `Object` covers `String` and the second component `String` covers the same type `String`.

Conversely, the following two patterns do not have a one-way total coverage:

```java
case Pair(String left, Object right) -> "left is text";
case Pair(Object left, String right) -> "right is text";
```

For `Pair("A", "B")`, **both** patterns can match, but the first pattern does not cover all values of the second pattern (e.g., `Pair(42, "B")`), and the second pattern does not cover all values of the first pattern (e.g., `Pair("A", 42)`). Therefore, this is not a dominance error; **the earlier branch is selected** when both match.

This is why you should not assume “if two cases overlap, the compiler will definitely reject them.” Dominance requires a specific subsumption relationship, not merely an **intersection**.

### 5.2. Note on null in record components

An easily overlooked detail of Java 21: **a type pattern nested directly inside a record pattern can match `null`** if that type pattern is *unconditional* for the declared type of the component.

With `record Pair(Object left, Object right)`, the component patterns `Object left` and `Object right` can also accept a `null` component. Thus `Pair(Object left, Object right)` can match `new Pair(null, null)`, even though **the record pattern itself does not match a `null` selector**.

In contrast, `Pair(String left, Object right)` does not match a `Pair` with `left = null`, because the component has declared type `Object` and the pattern `String left` is not unconditional for `Object`.

This is a JLS 21 rule; do not mechanically apply the intuition “every `String` pattern rejects `null`” from top-level `instanceof` to record component patterns.

## 6. Guarded and unguarded patterns: how far does the compiler reason?

In the label:

```java
case Integer number when number > 0 -> "positive";
```

`Integer number` is the pattern; `number > 0` is the **guard**. The JLS distinguishes:

- **Unguarded:** there is no `when`, or the guard is a constant expression with value `true`.
- **Guarded:** there is a `when` with a condition that does not fall into the case above.

An **unguarded** earlier pattern can dominate a later pattern. A **normal guarded** earlier pattern **is not considered to cover all values** of a later unguarded pattern of the same type.

Valid example:

```java
static String sign(Integer value) {
    return switch (value) {
        case null -> "null";
        case Integer number when number > 0 -> "positive";
        case Integer number -> "zero or negative";
    };
}
```

Although both cases have `Integer number`, the first branch only applies when the guard is true; the later branch acts as a **fallback for the same subtype**.

### 6.1. Reversing the order causes an error

```java
// INTENTIONALLY NON-COMPILING SNIPPET
return switch (value) {
    case Integer number -> "integer";
    case Integer number when number > 0 -> "positive"; // Dominated
};
```

The unguarded `Integer` branch covers all `Integer` values, so the guarded branch after it can never be selected.

### 6.2. `when true` is a special case

```java
// INTENTIONALLY NON-COMPILING SNIPPET
return switch (value) {
    case Integer number when true -> "any integer";
    case Integer number -> "fallback"; // Dominated
};
```

In Java 21, `when true` is a **constant-expression true** and is treated as unguarded. If you just want a general branch, **omit `when true` altogether** for clarity.

Conversely, `when false` is a **compile-time error** for a guard with constant value `false`; do not use it to temporarily disable a branch.

### 6.3. Arbitrary guards do not get full arithmetic implication proved by the compiler

Consider:

```java
case Integer number when number > 0 -> "positive";
case Integer number when number > 10 -> "large positive";
case Integer number -> "other";
```

The first two branches **overlap** for values greater than 10. However, the compiler does not prove that `number > 0` is always true whenever `number > 10` to treat the second branch as dominated the way it treats unguarded patterns. The code may compile, yet the `large positive` branch will never be selected for numbers greater than 10 because the first branch already handles them.

**Fix according to business intent:**

```java
case Integer number when number > 10 -> "large positive";
case Integer number when number > 0 -> "positive";
case Integer number -> "other";
```

Do not treat “the compiler didn't report dominance” as proof that guard ordering is correct. Always test thresholds and overlapping cases.

## 7. Constant case and pattern: place constants before general type patterns

In a `switch` on `Integer`, the constant `42` needs to be handled **before** an unguarded `Integer` type pattern:

```java
// INTENTIONALLY NON-COMPILING SNIPPET
return switch (number) {
    case Integer n -> "some integer";
    case 42 -> "the answer"; // Dominated
};
```

An unguarded `Integer n` type pattern covers the value `42`. Fix:

```java
static String classifyInteger(Integer number) {
    return switch (number) {
        case null -> "missing";
        case 42 -> "the answer";
        case Integer n when n > 0 -> "positive";
        case Integer n -> "nonpositive";
    };
}
```

The order reads like a priority rule:

1. Special value `42`.
2. Other positive integers.
3. Remaining integers.

### 7.1. A guarded pattern before a constant does not necessarily trigger a dominance error

```java
return switch (number) {
    case Integer n when n > 0 -> "positive";
    case 42 -> "the answer";
    case Integer n -> "other";
};
```

The snippet above may **compile**, but `42` already matches the `n > 0` branch, so `case 42` is **unreachable** at runtime. For the special value to be handled, place `case 42` **before the guard**.

**Heuristic when combining label kinds:** special constants → guarded patterns → broader unguarded patterns → fallback. This is a practical code-reading convention, not a rule that every constant must always come first regardless of type or business logic.

## 8. Default, total patterns, and covering the entire selector

For a selector with static type `Object`, the `Object other` type pattern is the broadest pattern for non-null objects:

```java
static String describe(Object value) {
    return switch (value) {
        case null -> "null";
        case String text -> "string";
        case Number number -> "number";
        case Object other -> "other";
    };
}
```

No `default` is needed. Adding `default` after an **unconditional pattern for the selector type** can lead to a compile-time error because the fallback branch is dominated.

```java
// INTENTIONALLY NON-COMPILING SNIPPET
return switch (value) {
    case Object other -> "any non-null object";
    default -> "fallback"; // Dominated
};
```

In Java 21, the compiler has specific rules for the `default` label, including not placing `default` before a `case pattern` or `case null`; keep `default` last when it is needed.

### 8.1. `null` is not the same as default

- A **top-level type pattern** such as `case Object other` does not match a `null` selector.
- `case null` is used to match `null`.
- A regular `default` does not replace explicit `null` handling in a pattern `switch`.

Therefore, a switch that wants to accept both `null` and all other objects can use:

```java
return switch (value) {
    case null -> "missing";
    case Object other -> "non-null";
};
```

If the intent is to reject `null`, you can use `Objects.requireNonNull(value)` before the switch.

### 8.2. `case null, default` is a special label

Java 21 allows the combined label `case null, default` in the appropriate context:

```java
return switch (value) {
    case String text -> "text";
    case null, default -> "other or missing";
};
```

When used, this combined label must appear **at the end** of the switch block. It is not two type patterns and not a trick to bypass dominance rules. If business logic needs to distinguish `null` from an unsupported type, keeping two separate branches is easier to read.

## 9. How is dominance different from exhaustiveness?

These two mechanisms often appear side by side, but they answer **two different questions**.

| Concept | Question | Consequence when wrong |
| --- | --- | --- |
| **Dominance** | “Is any later branch completely covered by an earlier branch?” | Dominated branch → **compile-time error** |
| **Exhaustiveness** | “Do the branches cover all values that must be considered for this switch?” | Switch requires exhaustiveness but misses cases → **compile-time error** |
| **Guard order** | “Two branches can both match some values; which one is selected?” | May **compile but produce wrong results** |
| **Flow scoping** | “Is the pattern variable in scope here when the match succeeds?” | Using variable out of scope → **compile-time error** |

Example of a sealed domain:

```java
sealed interface Result permits Success, Failure {}
record Success(String value) implements Result {}
record Failure(String reason) implements Result {}
```

Exhaustive switch:

```java
static String render(Result result) {
    return switch (result) {
        case Success(var value) -> "OK:" + value;
        case Failure(var reason) -> "FAIL:" + reason;
    };
}
```

Both subtypes are covered. No `default` is needed. If business logic adds a new subtype and recompiles, the compiler can require adding the corresponding case.

However, a switch with only a guarded `Success` will not automatically be exhaustive:

```java
// INTENTIONALLY NON-COMPILING SNIPPET: missing Success when guard is false
return switch (result) {
    case Success(var value) when value != null -> "OK";
    case Failure(var reason) -> "FAIL";
};
```

This is a **missing coverage** error, not dominance. The fix is to add an unguarded `Success` branch (or an appropriate fallback policy). Do not add `default -> ""` just to silence the compiler if the goal is to handle each domain variant explicitly.

## 10. Generic types, erasure, and pattern distinguishability

In Java generics, type argument information is not always available at runtime. For a source with static type `Object`, **reifiable types** such as `List<?>` can be used in a type pattern:

```java
return switch (value) {
    case java.util.List<?> list -> "list";
    case java.util.Collection<?> collection -> "collection";
    default -> "other";
};
```

This is the proper order: `List` is a subtype of `Collection`. Reversing the two branches causes `case List<?> list` to be dominated.

You cannot distinguish arbitrary values based on specific generic type arguments like `List<String>` and `List<Integer>` when the source is just `Object`:

```java
// INTENTIONALLY NON-COMPILING SNIPPET from Object source:
case java.util.List<String> strings -> "strings";
case java.util.List<Integer> ints -> "integers";
```

This is primarily a **pattern applicability / checked cast** issue due to type erasure, not a way to resolve dominance. Match `List<?> list` and inspect individual elements, or design record wrappers with distinguishable runtime types.

According to the JLS, certain specific generic checks are valid if the **static type of the selector** already carries enough information for a checked cast. However, type arguments should not be used to distinguish two arbitrary collections from `Object`.

## 11. When the compiler reports no dominance, yet the code still has a useless branch

Some pairs of patterns **overlap without subsuming each other**. For example:

```java
record Pair(Object left, Object right) {}
```

```java
return switch (value) {
    case Pair(String left, Object right) -> "string on left";
    case Pair(Object left, String right) -> "string on right";
    case Pair(Object left, Object right) -> "general pair";
    default -> "not a pair";
};
```

For `Pair("A", "B")`, both of the first two branches match. Because the **left** branch comes first, it is selected. This is **not** compile-time dominance: each branch has values of its own that the other branch does not cover.

In system design, you must explicitly decide what happens when data satisfies both conditions:

- Prioritize checking the left?
- Prioritize checking the right?
- Is a separate `Pair(String left, String right)` case needed at the top?
- Or should the logic be moved into a clearly named classification method?

Example adding the most specific branch:

```java
case Pair(String left, String right) -> "both strings";
case Pair(String left, Object right) -> "left string";
case Pair(Object left, String right) -> "right string";
case Pair(Object left, Object right) -> "other pair";
```

This clarifies the behavior for the intersection of the two cases, avoiding implicit reliance on position. Write unit tests for `Pair("A","B")`, `Pair("A",42)`, `Pair(42,"B")`, and `Pair(42,7)`.

## 12. Complete Java 21 program: type, record, guard, constant

Save as **`PatternDominanceDemo.java`**. This program **runs on standard Java 21**, without preview flags. The intentionally non-compiling examples from earlier sections **do not belong in this file**.

```java
public class PatternDominanceDemo {
    record Parcel(Object item) {}

    sealed interface Notice permits EmailNotice, SmsNotice {}
    record EmailNotice(String address) implements Notice {}
    record SmsNotice(String number) implements Notice {}

    static String describe(Object input) {
        return switch (input) {
            case null -> "null selector";

            case String text when text.isBlank() -> "blank text";
            case String text -> "text:" + text;

            case Integer number when number > 0 ->
                "positive:" + number;
            case Integer number -> "integer:" + number;

            case Parcel(String text) when text.isEmpty() ->
                "empty payload";
            case Parcel(String text) -> "payload text:" + text;
            case Parcel(Object item) -> "payload other:" + item;

            case Object other ->
                "other:" + other.getClass().getSimpleName();
        };
    }

    static String numberClass(Integer number) {
        return switch (number) {
            case null -> "no number";
            case 42 -> "answer";
            case Integer value when value > 0 -> "positive";
            case Integer value -> "zero or negative";
        };
    }

    static String notice(Notice value) {
        return switch (value) {
            case null -> "no notice";
            case EmailNotice(String address)
                    when address != null && address.isBlank() ->
                "blank email";
            case EmailNotice(String address) ->
                "email:" + address;
            case SmsNotice(String number) -> "sms:" + number;
        };
    }

    static void check(String expected, String actual) {
        if (!expected.equals(actual)) {
            throw new AssertionError(
                    "Expected [" + expected + "] but got [" + actual + "]");
        }
    }

    public static void main(String[] args) {
        Object[] examples = {
            " ", "java", 5, -1,
            new Parcel(""), new Parcel("hi"),
            new Parcel(12), new Parcel(null),
            3.5, null
        };

        for (Object example : examples) {
            System.out.println(describe(example));
        }

        System.out.println(numberClass(42));
        System.out.println(numberClass(7));
        System.out.println(numberClass(0));

        System.out.println(notice(new EmailNotice("  ")));
        System.out.println(notice(new EmailNotice("a@b.com")));
        System.out.println(notice(new SmsNotice("090")));
        System.out.println(notice(null));

        check("empty payload", describe(new Parcel("")));
        check("payload other:null", describe(new Parcel(null)));
        check("answer", numberClass(42));
        check("positive", numberClass(7));
        check("zero or negative", numberClass(0));
        check("blank email", notice(new EmailNotice("  ")));
        check("email:null", notice(new EmailNotice(null)));
        System.out.println("checks passed");
    }
}
```

Compile and run with **JDK 21**:

```bash
javac --release 21 PatternDominanceDemo.java
java PatternDominanceDemo
```

Exact stdout for the values in the program:

```text
blank text
text:java
positive:5
integer:-1
empty payload
payload text:hi
payload other:12
payload other:null
other:Double
null selector
answer
positive
zero or negative
blank email
email:a@b.com
sms:090
no notice
checks passed
```

**What is demonstrated?**

1. `String` with guard `isBlank()` comes before general `String`.
2. `Integer` with guard `number > 0` comes before general `Integer`.
3. `Parcel(String text)` comes before `Parcel(Object item)`: the `String` component is more specific than `Object`.
4. `Parcel(null)` is handled by `Parcel(Object item)` because the `Object item` component pattern is null-matching when the component's declared type is `Object`.
5. `Object other` is placed **last** to catch remaining non-null objects; `case null` handles a null selector separately.
6. `case 42` comes before `case Integer value`, avoiding being covered by the type branch.
7. `Notice` is a sealed hierarchy consisting of two records; the switch needs no `default` and each record has a base branch.
8. `EmailNotice(String address)` with declared component type `String` can receive `null`; the guard checks `address != null` before calling `isBlank()`, so it does not throw an exception.
9. The `check` assertions verify key boundaries without requiring `-ea` or external libraries.

## 13. Three groups of compiler errors easily confused with dominance

### 13.1. Pattern not applicable to the selector type

```java
// INTENTIONALLY NON-COMPILING SNIPPET
Object input = java.util.List.of("A");
if (input instanceof java.util.List<String> strings) {
    // ...
}
```

This is a **generic type checkability** error from an `Object` source, not an error where one `case` shadows another branch.

### 13.2. Non-exhaustive switch

```java
// INTENTIONALLY NON-COMPILING SNIPPET: missing when guard is false
return switch (value) {
    case String text when text.length() > 2 -> "long text";
};
```

When the selector is an open type like `Object`, the switch expression above misses many values; even a `String` selector can fail to satisfy the guard. This is an **exhaustiveness** error, not dominance. It can be fixed with an unguarded `String text` branch and `default` when the selector type requires a fallback.

### 13.3. Pattern variable out of scope

```java
// INTENTIONALLY NON-COMPILING SNIPPET
switch (value) {
    case String text -> System.out.println(text);
    default -> {}
}
System.out.println(text); // text is not in scope here
```

This is a **flow scoping** error. A pattern variable belongs only to the matching branch; it does not exist after the switch. A switch expression can return a shared result variable:

```java
String summary = switch (value) {
    case String text -> "string:" + text;
    default -> "other";
};
System.out.println(summary);
```

Do not fix a scope error by reordering cases; different problems require different fixes.

## 14. Dominance checklist during code review

When you see a `switch` with multiple patterns, do the following:

1. **Identify the static type of the selector.** `Object`, `Number`, `Integer`, or a sealed domain? This type affects pattern applicability and exhaustiveness.
2. **Locate general cases.** `Object`, parent interfaces, `Number`, `Collection<?>`, record type patterns.
3. **Place specific cases first.** For example, `String` before `CharSequence`, `Integer` before `Number`, specific record patterns before the record's type pattern.
4. **Check record components position by position.** If every component pattern of an earlier branch covers the corresponding component of a later branch, the later branch may be dominated.
5. **Separate guards and patterns.** For guarded branches, evaluate overlap and priority order; do not expect the compiler to solve complex boolean expressions.
6. **Place special constants before unguarded type patterns.** For example, `case 42` before `case Integer n`.
7. **Define null and fallback policies.** `case null`, `default`, or an unconditional type pattern for the selector must not be used haphazardly or redundantly.
8. **Distinguish dominance errors from other errors.** Read `dominated`, `not exhaustive`, `not applicable`, or variable-scope diagnostics accurately.
9. **Write tests for overlapping cases.** Two patterns that overlap without dominating each other can still depend on case order at runtime.
10. **Recompile with exact Java 21.** Use `javac --release 21` to avoid treating preview syntax or newer Java version changes as the baseline for this topic.

### Suggested readable order

For a selector supporting multiple forms, a convenient order is typically:

1. `case null` (if `null` needs its own branch).
2. **Special constants** compatible with the selector type.
3. **Narrower patterns** or specific record structures.
4. **Guarded cases** that need priority according to business rules.
5. Broader **unguarded type/record patterns**.
6. `default` or a general unconditional pattern **if needed**, without keeping both as redundant fallbacks.

This is an **organizational guideline**, not a syntactic rule that every group must appear in every switch. For pairs of conditions with special relationships, order cases by **actual coverage** and business priority, rather than mechanically applying the group order.

## 15. Self-assessment exercises and answers

### Exercise 1 — Number/Integer order

```java
// This is a switch snippet:
case Number n -> "number";
case Integer i -> "integer";
```

**Question:** Does it compile?

**Answer:** No, within a type-compatible switch; `Number` covers `Integer`. Put `Integer` before `Number`.

### Exercise 2 — Two guarded patterns

```java
case Integer n when n >= 0 -> "nonnegative";
case Integer n when n >= 10 -> "at least ten";
case Integer n -> "negative";
```

**Question:** Dominance error or logic error?

**Answer:** The compiler does not prove arbitrary arithmetic relationships between two guards to reject them as unguarded dominance. The snippet can compile, but the `at least ten` branch will not be selected for its values because `n >= 0` handles them first. Swap the two guarded cases; keep the general case last.

### Exercise 3 — Record pattern vs type pattern

```java
record Parcel(Object item) {}

case Parcel parcel -> "parcel";
case Parcel(String text) -> "text parcel";
```

**Question:** What is the issue?

**Answer:** The `Parcel parcel` type pattern covers every `Parcel` with a string component. The later record pattern is dominated. Place `Parcel(String text)` first.

### Exercise 4 — Two merely overlapping record patterns

```java
record Pair(Object a, Object b) {}

case Pair(String a, Object b) -> "left";
case Pair(Object a, String b) -> "right";
```

**Question:** Is there complete dominance, and where does `Pair("a", "b")` go?

**Answer:** There is no complete dominance in either direction, because each pattern has values that the other does not match. `Pair("a", "b")` matches both, so the earlier **left** branch is selected. If both-strings needs dedicated handling, add `Pair(String a, String b)` at the top.

### Exercise 5 — Constant after a type pattern

```java
case Integer n -> "integer";
case 42 -> "answer";
```

**Answer:** `case 42` is dominated. Move the constant `42` before the `Integer` pattern.

### Exercise 6 — `when true` and `when false`

**Question:** Does `when true` help avoid dominance? Is `when false` a way to temporarily disable a branch?

**Answer:** No. `when true` is **unguarded** according to the specification and can dominate later cases. A guard that is the constant expression `false` is rejected at compile time. Remove the unused branch or design a valid condition.

### Exercise 7 — Does default catch null?

```java
return switch (value) {
    case String s -> "text";
    default -> "other";
};
```

**Answer:** Do not assume `default` is a policy that accepts `null`. In a Java 21 pattern switch, `null` does not match a regular type pattern and can cause a `NullPointerException` when there is no `case null` label. If `null` is an expected input, add `case null` or use `case null, default` according to policy.

### Exercise 8 — Object type pattern and default

```java
case Object obj -> "object";
default -> "fallback";
```

**Answer:** For an `Object` selector in Java 21, `Object obj` is an unconditional pattern for the selector type; a `default` after it is dominated. Choose one remaining coverage mechanism as appropriate, and handle `null` separately if needed.

## 16. Checklist when fixing a “dominated case label” error

- [ ] Have you identified the **static type of the selector** and which patterns are applicable?
- [ ] Is any supertype pattern placed before a subtype pattern?
- [ ] Is a record's type pattern placed before a detailed record pattern?
- [ ] For two record patterns, have you checked dominance **component by component**?
- [ ] For two overlapping patterns that do not dominate each other, is the **business priority** clear?
- [ ] Is a guarded branch placed before the general unguarded branch of the same type?
- [ ] Are you avoiding treating every guarded pattern as something the compiler can reason about to eliminate other branches?
- [ ] Are you avoiding `when true` to dodge dominance or `when false` to disable a branch?
- [ ] Are special constants placed before general type patterns if they need dedicated handling?
- [ ] Do `case null`, `default`, or `case null, default` have clear roles?
- [ ] Have you avoided placing an unconditional pattern for the selector together with `default`, causing redundant coverage?
- [ ] Have you avoided confusing dominance with an exhaustive switch, generic applicability, or flow scope?
- [ ] Have you tested overlapping branches and boundary values after reordering?

## 17. Official references

- [Java Language Specification 21 §14.11.1 — Switch Blocks](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11.1): rules for dominated `case` labels, guards, constants, `default`, and `null`.
- [Java Language Specification 21 §14.30.3 — Properties of Patterns](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30.3): definition of *unconditional* and dominance between type/record patterns.
- [Oracle Java 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html): examples of ordering types, guards, and constant cases.
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441): design of standard pattern matching for switch in Java 21.
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440): how record patterns are deconstructed and tested.

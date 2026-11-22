# Testing null in instanceof (Java 21)

## Objectives and Scope

In the **Testing** topic of Java Core Pattern Matching, a very common source of bugs is misjudging how `instanceof` behaves when encountering `null`. When refactoring from traditional type checks to type patterns or record patterns, you need to test **`null` at the selector**, **`null` at a nested record**, and **`null` at a leaf component** using independent scenarios.

This lesson guides you through:

- Explaining why `obj instanceof SomeType` and `obj instanceof SomeType x` return `false` when **`obj == null`**.
- Designing a test matrix covering `null`, matching type, wrong type, empty/blank strings, missing nested records, and null leaf components.
- Distinguishing `instanceof Account(...)` (record at the root) from patterns containing `Profile(...)` inside, and from `var profile` binding directly.
- Testing **flow scoping** of pattern variables and short-circuiting of `&&` to avoid `NullPointerException`.
- Writing a standalone Java 21 program with assertions, expected results, and fixed stdout to verify the behavior.

**Version:** Java 21. Type patterns for `instanceof` have been standard since Java 16 (JEP 394); record patterns became standard in Java 21 (JEP 440). The program uses `javac --release 21` and does not require `--enable-preview`.

## 1. Fundamental Rule: null on the Left-Hand Side of instanceof

Consider:

```java
Object value = null;
boolean ordinary = value instanceof String;
boolean pattern = value instanceof String text;
```

Both `ordinary` and `pattern` evaluate to **`false`**. `instanceof` does not attempt to cast `null` to `String`, and the variable `text` is **not bound** if the pattern does not match.

This remains true even for a very broad type:

```java
Object value = null;
boolean result = value instanceof Object present; // false
```

Because `null` is not an object instance, even though every non-null object is an `Object`. To distinguish the missing-data case, check `value == null` separately.

To avoid misunderstandings, separate the two questions:

| Question | How to check | When `value == null` |
|---|---|---|
| “Is it null?” | `value == null` | `true` |
| “Is it a non-null String?” | `value instanceof String s` | `false` |
| “Is it a non-null Object?” | `value instanceof Object o` | `false` |
| “Is it not a String?” | `!(value instanceof String s)` | `true` |

**Be careful with negation:** `!(value instanceof String s)` is true when `value` is null, but it is also true for any value of the wrong type. If you need to distinguish the reason, write explicit branches: null / wrong type / matching type.

## 2. Type Patterns Match Types Without Changing the Null Contract

Example:

```java
static String message(Object input) {
    if (input instanceof String text) {
        return "length=" + text.length();
    }
    return "not a string";
}
```

This is a standalone illustrative method. For `null`, it returns `not a string` and does not throw `NullPointerException`, because `text.length()` is only called when the pattern matches.

Traditional refactoring:

```java
// Before:
if (input instanceof String) {
    String text = (String) input;
    return text.length();
}

// After:
if (input instanceof String text) {
    return text.length();
}
```

Both handle null input the same way: the branch does not execute. Therefore, tests for the refactored version must include the **null case**, not only the matching-type case.

**Do not infer the reverse:** the fact that the `if` branch is safe does not mean any operation on `input` is safe. For example, `input.toString()` before `instanceof` can still throw an exception when `input` is null.

## 3. When Using Record Patterns: Three Distinct Null Positions

Suppose we have these records:

```java
record Profile(String nickname) {}
record Account(String id, Profile profile) {}
```

Consider the pattern:

```java
value instanceof Account(String id, Profile(String nickname))
```

In Java 21, the following scenarios must be distinguished:

### 3.1. Root null

If `value == null`, the entire `Account(...)` does not match. `instanceof` returns `false`.

### 3.2. Nested record null

If `value = new Account("A2", null)`, the `Account` record exists, but the `profile` component is null. The nested **record pattern** `Profile(String nickname)` does **not** match `null`. The entire deep pattern fails; `instanceof` returns `false`.

### 3.3. Null leaf component

If `value = new Account("A3", new Profile(null))`, the nested `Profile` record **exists**. The `nickname` component is declared with type `String`, and the subpattern `String nickname` is **unconditional for that component type**, so during record deconstruction it can bind `null`. The deep pattern therefore **matches successfully**.

Similarly, with `new Account(null, new Profile("An"))`, the `id` component is bound to null without causing the record pattern to fail.

A common point of confusion is that the statement “type patterns do not match null” at the `obj instanceof String s` level must **not** be applied mechanically to a **type pattern directly in a record pattern component**. The null-matching mechanism of nested components is specified separately in the Java 21 JLS for record patterns and unconditional patterns.

### 3.4. Stopping deconstruction with a var pattern

If you do not need to deconstruct `profile`, you can write:

```java
value instanceof Account(var id, var profile)
```

This pattern matches a non-null `Account` **even when `profile == null`**: `var profile` directly in the component binds null as well. Subsequent code can then check `profile == null`. It is not equivalent to `Profile(var nickname)` because the latter requires the `Profile` record itself to exist.

| Input | `Account(String id, Profile(String nick))` | `Account(var id, var profile)` |
|---|---|---|
| `null` | `false` | `false` |
| `"text"` | `false` | `false` |
| `new Account("A1", new Profile("Lan"))` | `true` | `true` |
| `new Account("A2", null)` | **`false`** | **`true`** |
| `new Account("A3", new Profile(null))` | **`true`** | `true` |
| `new Account(null, new Profile("An"))` | **`true`** | `true` |
| `new Account(null, null)` | `false` | `true` |

This table is the core of testing: **root null, nested record null, and leaf null** do not have the same semantics.

## 4. Testing Short-Circuiting with &&

The statement:

```java
return value instanceof Account(var id, Profile(var nickname))
        && nickname != null
        && !nickname.isBlank();
```

is evaluated from left to right. When `value` is not an `Account` or `profile == null`, the left-hand `instanceof` returns false; the remaining operands **do not run**. When `nickname` is null, the operand `nickname != null` returns false; `nickname.isBlank()` is not called.

Thus the expression has three cases:

- `Account` and `Profile` exist, and `nickname` has a non-whitespace character → `true`.
- `Account`/`Profile` is missing, or `nickname` is null/empty/blank → `false`.
- Root `value` is null or of the wrong type → `false`.

Intentionally add tests with `new Profile(null)` and `new Profile("  ")`. Testing only with nickname `"Lan"` cannot catch a bug such as omitting `nickname != null` before `nickname.isBlank()`.

**Dangerous counterexample:**

```java
// Unsafe if nickname can be null:
return value instanceof Account(var id, Profile(var nickname))
        && !nickname.isBlank();
```

This snippet can throw `NullPointerException` even though pattern deconstruction succeeded, because `nickname` is a **reference leaf component** and is allowed to be null.

Order also matters:

```java
// Wrong order if nickname can be null:
nickname.isBlank() || nickname == null

// Safe to check for "no nickname" or "blank nickname":
nickname == null || nickname.isBlank()
```

The right-hand side of `||` only runs when the left-hand side is false. Tests must verify both the **return value and that no exception is thrown**.

## 5. Flow Scoping When Negating instanceof

A valid pattern for handling wrong type/null early:

```java
static String scopedId(Object value) {
    if (!(value instanceof Account account)) {
        return "NOT_ACCOUNT";
    }
    return "ACCOUNT:" + account.id();
}
```

Java knows that to get past the `if` without returning, the pattern `Account account` must have matched. Therefore, the variable `account` is in scope at the subsequent `return` statement. With a root null, the negation is true and the method returns `NOT_ACCOUNT`; `account.id()` is not called.

Do not confuse this with invalid code:

```java
if (value instanceof Account account) {
    System.out.println(account.id());
}
// Do not assume 'account' is always in scope here:
// the instanceof branch might not have matched.
```

The illustrative snippets above assume `Account` is already declared. Section 6 provides all runnable methods in a single class.

## 6. Complete Java 21 Program with Automated Tests

Create the file **`NullInstanceofTestDemo.java`**. No external libraries are used; each `test(...)` call contains **expected results** and throws `AssertionError` if the actual behavior differs from expectations.

```java
import java.util.Objects;

public class NullInstanceofTestDemo {
    record Profile(String nickname) {}
    record Account(String id, Profile profile) {}

    static String classify(Object value) {
        if (value instanceof Account(String id, Profile(String nickname))) {
            return "DEEP:" + id + "/" + nickname;
        }
        if (value instanceof Account(var id, var profile)) {
            return "SHALLOW:" + id + "/profile-null=" + (profile == null);
        }
        return "OTHER";
    }

    static boolean nonBlankNickname(Object value) {
        return value instanceof Account(var id, Profile(var nickname))
                && nickname != null
                && !nickname.isBlank();
    }

    static boolean isProfileMissing(Object value) {
        return value instanceof Account(var id, var profile)
                && profile == null;
    }

    static String scopedId(Object value) {
        if (!(value instanceof Account account)) {
            return "NOT_ACCOUNT";
        }
        return "ACCOUNT:" + account.id();
    }

    static String stringLength(Object value) {
        return value instanceof String text && !text.isBlank()
                ? "LEN:" + text.length() : "NO_TEXT";
    }

    static void test(String label, Object value, String expectedClassify,
                     boolean expectedNonBlank, boolean expectedMissing,
                     String expectedId, String expectedText) {
        String actualClassify = classify(value);
        boolean actualNonBlank = nonBlankNickname(value);
        boolean actualMissing = isProfileMissing(value);
        String actualId = scopedId(value);
        String actualText = stringLength(value);
        if (!Objects.equals(expectedClassify, actualClassify)
                || expectedNonBlank != actualNonBlank
                || expectedMissing != actualMissing
                || !Objects.equals(expectedId, actualId)
                || !Objects.equals(expectedText, actualText)) {
            throw new AssertionError(label + " => "
                    + actualClassify + "/" + actualNonBlank + "/"
                    + actualMissing + "/" + actualId + "/" + actualText);
        }
        System.out.println(label + " => " + actualClassify
                + ", nonBlank=" + actualNonBlank
                + ", missing=" + actualMissing
                + ", id=" + actualId
                + ", text=" + actualText);
    }

    public static void main(String[] args) {
        test("root null", null, "OTHER", false, false, "NOT_ACCOUNT", "NO_TEXT");
        test("other type", Integer.valueOf(7), "OTHER", false, false,
                "NOT_ACCOUNT", "NO_TEXT");
        test("text", "Hi", "OTHER", false, false, "NOT_ACCOUNT", "LEN:2");
        test("blank text", "  ", "OTHER", false, false, "NOT_ACCOUNT", "NO_TEXT");
        test("full", new Account("A1", new Profile("Lan")),
                "DEEP:A1/Lan", true, false, "ACCOUNT:A1", "NO_TEXT");
        test("profile null", new Account("A2", null),
                "SHALLOW:A2/profile-null=true", false, true, "ACCOUNT:A2", "NO_TEXT");
        test("nickname null", new Account("A3", new Profile(null)),
                "DEEP:A3/null", false, false, "ACCOUNT:A3", "NO_TEXT");
        test("nickname blank", new Account("A4", new Profile("  ")),
                "DEEP:A4/  ", false, false, "ACCOUNT:A4", "NO_TEXT");
        test("id null", new Account(null, new Profile("An")),
                "DEEP:null/An", true, false, "ACCOUNT:null", "NO_TEXT");
        test("both null", new Account(null, null),
                "SHALLOW:null/profile-null=true", false, true, "ACCOUNT:null", "NO_TEXT");

        Object ref = null;
        if (ref instanceof Object present) {
            throw new AssertionError("null instanceof Object must be false");
        }
        System.out.println("null instanceof Object -> false");
    }
}
```

Compile and run on JDK 21 or later:

```bash
javac --release 21 NullInstanceofTestDemo.java
java NullInstanceofTestDemo
```

**Directly verified stdout:**

```text
root null => OTHER, nonBlank=false, missing=false, id=NOT_ACCOUNT, text=NO_TEXT
other type => OTHER, nonBlank=false, missing=false, id=NOT_ACCOUNT, text=NO_TEXT
text => OTHER, nonBlank=false, missing=false, id=NOT_ACCOUNT, text=LEN:2
blank text => OTHER, nonBlank=false, missing=false, id=NOT_ACCOUNT, text=NO_TEXT
full => DEEP:A1/Lan, nonBlank=true, missing=false, id=ACCOUNT:A1, text=NO_TEXT
profile null => SHALLOW:A2/profile-null=true, nonBlank=false, missing=true, id=ACCOUNT:A2, text=NO_TEXT
nickname null => DEEP:A3/null, nonBlank=false, missing=false, id=ACCOUNT:A3, text=NO_TEXT
nickname blank => DEEP:A4/  , nonBlank=false, missing=false, id=ACCOUNT:A4, text=NO_TEXT
id null => DEEP:null/An, nonBlank=true, missing=false, id=ACCOUNT:null, text=NO_TEXT
both null => SHALLOW:null/profile-null=true, nonBlank=false, missing=true, id=ACCOUNT:null, text=NO_TEXT
null instanceof Object -> false
```

**Reading the output:**

- `root null`: neither type nor record patterns match. No pattern variable at the root is bound.
- `other type`: `Integer` is neither `Account` nor `String`; the result looks like root null, but for a **different reason**.
- `text` and `blank text`: both are `String`, so the type pattern matches; the expression with `!text.isBlank()` further classifies the content.
- `full`: `Account` and `Profile` exist, and `nickname` is non-empty/non-blank → deep match and predicate true.
- `profile null`: nested `Profile(...)` does not match; `Account(var id, var profile)` still matches and binds `profile == null`.
- `nickname null`: the deep pattern still matches because it is a leaf component, but `nonBlankNickname` returns false without throwing an NPE.
- `nickname blank`: the two spaces are preserved in the string; the deep match succeeds, and `isBlank()` makes the predicate false.
- `id null`: a null `id` component does not prevent the record pattern from matching. The string `DEEP:null/An` is a consequence of Java string concatenation, not an ID validation rule.
- `both null`: the root `Account` exists; the shallow match succeeds, and `profile` is null. The deep match does not succeed.
- `null instanceof Object`: an independent assertion ensuring root null is not misidentified as an object.

Not every `false` result is a bug; tests must verify the **classification contract**, rather than trying to make every branch return true.

## 7. Selecting Test Cases That Can Catch Bugs

A valuable minimal test suite should include:

| Group | Example input | Bug caught |
|---|---|---|
| **Root null** | `null` | Assuming `instanceof` matches null or dereferencing before checking |
| **Wrong type** | `Integer.valueOf(7)` | Handling null and wrong type in the same branch when they should be distinguished |
| **Basic matching type** | `"Hi"` | Incorrect type pattern or flow scope |
| **Blank string** | `"  "` | Testing only the type while skipping content guards |
| **Nested record null** | `new Account("A2", null)` | Confusing a nested record pattern with a `var` component |
| **Leaf null** | `new Account("A3", new Profile(null))` | Assuming the entire record pattern fails on leaf null; omitting null guards |
| **ID null** | `new Account(null, new Profile("An"))` | Assuming every record component is non-null |
| **Non-null root, all valid** | `new Account("A1", new Profile("Lan"))` | Pattern/guard failing to accept valid cases |
| **Combined nulls** | `new Account(null, null)` | Missing fallback branch when nested data is absent |

Depending on the domain, add inputs with subtypes, multi-level nested records, empty collections, Unicode whitespace, or malformed data. However, **never assume all record components are non-null** unless constructors or boundary validation guarantee it.

## 8. Checking Exceptions, Not Just Booleans

An incorrect implementation may return the right result for normal inputs yet throw an exception when encountering null. For example:

```java
// Dangerous when value is an Account containing Profile(null):
if (value instanceof Account(var id, Profile(var nickname))
        && nickname.isBlank()) {
    System.out.println("Blank");
}
```

In Java 21, `Profile(var nickname)` can match a null `nickname`. The bug is in calling `nickname.isBlank()`, not in `instanceof` itself. To fix it:

```java
if (value instanceof Account(var id, Profile(var nickname))
        && nickname != null && nickname.isBlank()) {
    System.out.println("Blank (non-null)");
}
```

Or if business logic treats both null and blank as “missing nickname”:

```java
if (value instanceof Account(var id, Profile(var nickname))
        && (nickname == null || nickname.isBlank())) {
    System.out.println("Missing nickname");
}
```

These three snippets are **illustrative fragments to place inside a method** where `value` is already declared; they are not standalone Java files. The parentheses in the `||` condition keep the meaning clear.

When writing JUnit tests, use both return-value assertions and `assertDoesNotThrow(...)` at boundaries where null may appear. In the self-test program from Section 6, even a single NPE stops the program and prevents all 11 lines from being printed, so the test catches this risk.

## 9. JUnit 5 Test Template for Real Projects

The program in Section 6 has no framework dependencies. If your project uses JUnit Jupiter 5, you can write a separate test class to report failures per case:

```java
// Illustrative snippet, used when the project already has JUnit 5 and
// has access to the NullInstanceofTestDemo class.
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class NullInstanceofTests {
    @Test
    void nullRootDoesNotMatch() {
        assertEquals("OTHER", NullInstanceofTestDemo.classify(null));
        assertFalse(NullInstanceofTestDemo.nonBlankNickname(null));
        assertEquals("NOT_ACCOUNT", NullInstanceofTestDemo.scopedId(null));
    }

    @Test
    void nullNestedProfileFallsBack() {
        var account = new NullInstanceofTestDemo.Account("A2", null);
        assertEquals("SHALLOW:A2/profile-null=true",
                NullInstanceofTestDemo.classify(account));
        assertTrue(NullInstanceofTestDemo.isProfileMissing(account));
    }

    @Test
    void nullLeafIsSafeForGuard() {
        var account = new NullInstanceofTestDemo.Account(
                "A3", new NullInstanceofTestDemo.Profile(null));
        assertEquals("DEEP:A3/null", NullInstanceofTestDemo.classify(account));
        assertDoesNotThrow(() ->
                NullInstanceofTestDemo.nonBlankNickname(account));
        assertFalse(NullInstanceofTestDemo.nonBlankNickname(account));
    }
}
```

**Note:** this is a **test snippet that must be placed in the same package as the example class** with appropriate JUnit 5 dependencies configured; it cannot be compiled with `javac --release 21` alone without JUnit. The program in Section 6 is the standalone example that was executed and verified against stdout.

In real systems, you can turn test data into parameterized tests, but do not lump all null cases into a single assertion. Each null level (root/nested/leaf) needs its own test name and expected behavior so failures are easy to trace.

## 10. Common Mistakes When Testing null with Pattern Matching

### 10.1. Testing only non-null Objects

Testing only with `"abc"` cannot detect a missing null branch or calling `toString()` before checking. Add an independent root-null test.

### 10.2. Assuming `instanceof String s` “accepts null”

False for the root selector. Both `null instanceof String` and `value instanceof String s` when `value` is null return false.

### 10.3. Assuming any null inside a record causes the pattern to fail

False: a reference-type leaf component can be bound to null if the subpattern is unconditional for the component type. What causes a nested record pattern to fail is the **nested record itself** being null.

### 10.4. Not testing `var profile` and `Profile(...)` separately

The two forms are not equivalent when `profile` is null. Testing `Account("A2", null)` must show that the deep pattern does not match while the shallow pattern matches.

### 10.5. Placing the dereference before the null check

`nickname.isBlank() && nickname != null` can throw an exception. Use `nickname != null && !nickname.isBlank()` or `nickname == null || nickname.isBlank()` depending on requirements.

### 10.6. Misunderstanding flow scoping

A pattern variable can only be used where the compiler can prove the pattern matched. Avoid using the variable outside branches that guarantee a match. Compiling successfully is necessary, but you must still test runtime null.

### 10.7. Checking only output and ignoring the exception contract

If the previous version returned `false` on null while the new version throws an NPE, that is a behavioral change. Tests must surface errors rather than swallowing exceptions arbitrarily.

### 10.8. Using `switch default` to infer instanceof rules

`switch` has its own `case null` syntax and different exhaustiveness/dominance rules. `instanceof` has no `default`; for a null selector, it returns false. Do not conflate the two mechanisms when writing expected behavior.

### 10.9. Testing only one level of null

A single `value == null` test is not enough to prove that `new Account("A", null)` and `new Account("A", new Profile(null))` are handled properly. Test every level of the data structure.

## 11. Pre- and Post-Refactoring Testing Workflow

When migrating legacy casts to record patterns or type patterns:

1. **Identify the old contract:** does it accept root null? What does it return when a nested field is missing? Does it distinguish wrong type from missing data?
2. **Build an input matrix:** root null, wrong type, matching type, nested record null, leaf null, empty/blank strings, and complete data.
3. **Add independent expected results:** do not only write `assertEquals(before(input), after(input))`, because both versions could share the same bug.
4. **Verify type patterns:** root null always makes `instanceof` return false; do not rely on a pattern variable when the match fails.
5. **Verify record patterns:** nested record null does not match; direct `var`/unconditional component patterns can bind null.
6. **Verify short-circuiting:** place null guards before method calls; avoid NPEs when leaf components are null.
7. **Run `javac --release 21`:** catch pattern syntax/scope/typing errors according to the target version.
8. **Run tests and read the full stdout:** any `AssertionError` or exception means the run does not pass.
9. **Review output and exception contracts:** confirm no fallback branch was lost after refactoring.
10. **Add integration tests when needed:** especially when record constructors/accessors perform validation, use data across multiple modules, or receive nullable fields from external APIs.

Do not isolate null testing as “a single test at the controller”: the input boundary, the deconstruction site, and the component method call site may have different null assumptions.

## 12. Self-Check Exercise

Using:

```java
record Box(String value) {}
record Envelope(Box box) {}
```

Assume `selector` has type `Object`. Predict the results:

| Selector | Pattern | Result |
|---|---|---|
| `null` | `Envelope(Box(var s))` | `false` |
| `new Envelope(null)` | `Envelope(Box(var s))` | `false` |
| `new Envelope(null)` | `Envelope(var box)` | **`true`**, `box` is bound to null |
| `new Envelope(new Box(null))` | `Envelope(Box(var s))` | **`true`**, `s` is bound to null |
| `new Envelope(new Box(""))` | `Envelope(Box(var s))` | **`true`**, `s` is the empty string |
| `"hello"` | `Envelope(var box)` | `false` |

The pattern fragments above are placed inside a `selector instanceof ...` expression. You cannot use the variable `s` after an `if` unless the compiler guarantees the pattern matched.

**Questions:**

1. Why does `value instanceof Object obj` return false when `value` is null? **Because null is not an object instance.**
2. When the nested `Box` is null, is `Box(var s)` deconstructed? **No.**
3. When `Box` is non-null but `Box.value() == null`, does `var s` receive null? **Yes.**
4. If `s == null`, can you call `s.isBlank()` just because the record pattern matched? **No; you must guard it.**
5. Which condition guarantees `isBlank()` is not called on null? **`s != null && !s.isBlank()`**.
6. Why must you test both root null **and** nested null? **Because they affect different pattern levels and are easily mishandled during refactoring.**

## Conclusion

To test `null` in `instanceof` accurately, you must know **where the null is located**. A **null root selector** makes `instanceof` return false. A **null nested record** causes the nested record pattern not to match. However, a **null leaf component** can still be bound by the corresponding unconditional pattern inside a record pattern; in that case, guards must protect every dereference.

A good test suite for Java 21 does not only check matching-type cases. It distinguishes root/nested/leaf nulls, wrong types, short-circuiting, and properly scoped pattern variables, verifying both **return values and the absence of out-of-contract exceptions**. A self-test program with independent expected results turns these rules into verifiable behavior.

## References

- [JEP 394 — Pattern Matching for instanceof](https://openjdk.org/jeps/394)
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440)
- [Java Language Specification SE 21 — §15.20.2 The instanceof Operator](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.20.2)
- [Java Language Specification SE 21 — §14.30 Patterns](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30)
- [Oracle Java SE 21 — Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html)
- [Oracle Java SE 21 — Pattern Matching for instanceof](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-instanceof.html)

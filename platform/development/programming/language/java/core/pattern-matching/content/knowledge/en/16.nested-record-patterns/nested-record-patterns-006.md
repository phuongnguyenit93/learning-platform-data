# Handling null at each nesting level in nested record patterns (Java 21+)

When using **nested record patterns**, Java checks a record and then continues matching each component, which may itself be another record. If a link in the chain is `null`, the result depends on **the pattern being applied at that exact link**: a record pattern does not match `null`, whereas certain component type patterns (especially `var`) can match `null`. This is the deciding factor for branching and avoiding errors when processing nested data.

This article uses **Java 21 or later**. Record patterns were finalized in Java 21 (JEP 440), and pattern matching for `switch` was also finalized in this version (JEP 441); `--enable-preview` is not needed.

## 1. Multi-level record structure

Consider three nested records and a final data component:

```java
record Leaf(Object content) {}
record Branch(Leaf leaf) {}
record Tree(Branch branch) {}
```

The path from outside to inside is:

```text
Tree
  └─ branch: Branch
       └─ leaf: Leaf
            └─ content: Object
```

By default, records **do not automatically forbid `null` in reference-type components**. Therefore, all of the following objects are syntactically valid in Java if there is no explicit check in the constructor:

```java
Tree a = null;
Tree b = new Tree(null);
Tree c = new Tree(new Branch(null));
Tree d = new Tree(new Branch(new Leaf(null)));
Tree e = new Tree(new Branch(new Leaf("OK")));
```

The five cases above place `null` in **five different situations**: the outermost value, the `branch` component, the `leaf` component, the `content` component, and no `null` value at all. They should not be lumped into a single case.

## 2. Core rule: a record pattern does not match null

Consider the expression:

```java
input instanceof Tree(Branch(Leaf(var content)))
```

Java performs the match layer by layer:

1. `Tree(...)` checks that `input` is a **non-`null`** `Tree` object.
2. `Branch(...)` checks that the value of `Tree.branch()` is a **non-`null`** `Branch` object.
3. `Leaf(...)` checks that the value of `Branch.leaf()` is a **non-`null`** `Leaf` object.
4. `var content` receives the value of `Leaf.content()`. Because this is an unconditional component type pattern for the declared type `Object`, **it matches even when `content` is `null`**.

When a record pattern in step 1, 2, or 3 encounters `null`, the entire nested record pattern fails to match. With `instanceof`, the result is `false` and none of the pattern variables from that match are in scope in the success branch. Failing to match due to `null` **does not by itself throw a `NullPointerException`**: Java does not continue deconstructing a `null` record.

Notably, `var` in step 4 is a pattern for **a component inside the record**, not a record pattern. Therefore, the conclusion that "any `null` in the data causes the entire nested record pattern to fail" is **false**.

### Result table by null position

| Value of `input` | Which level contains `null` | `input instanceof Tree(Branch(Leaf(var content)))` | Reason |
| --- | --- | --- | --- |
| `null` | Outer object | `false` | `Tree(...)` does not match `null` |
| `new Tree(null)` | `branch` | `false` | `Branch(...)` does not match `null` |
| `new Tree(new Branch(null))` | `leaf` | `false` | `Leaf(...)` does not match `null` |
| `new Tree(new Branch(new Leaf(null)))` | `content` | `true` | `var content` receives the value `null` |
| `new Tree(new Branch(new Leaf("OK")))` | No `null` | `true` | All three record patterns match and `content` is `"OK"` |

If the `content` component contains `null`, you can immediately check `content == null` inside the matched branch, because this variable is validly initialized even though its value is `null`.

## 3. Capturing a component with var to handle null yourself

If you want to recognize a parent record **without requiring the child record to be non-`null`**, use `var` instead of a nested record pattern at the exact level you want to check.

```java
Object input = new Tree(null);

if (input instanceof Tree(var branch)) {
    System.out.println(branch == null); // true
}
```

`Tree(var branch)` requires `input` to be a non-`null` `Tree`, but does **not** require `branch` to be non-`null`. The variable `branch` has the inferred type `Branch`, and its value may be `null`.

One level deeper:

```java
Object input = new Tree(new Branch(null));

if (input instanceof Tree(Branch(var leaf))) {
    System.out.println(leaf == null); // true
}
```

Here, both `Tree(...)` and `Branch(...)` must receive non-`null` record objects; `var leaf` receives the `leaf` component even when it is `null`. Changing it to `Tree(Branch(Leaf(var content)))` causes the condition **not** to match, because Java would then have to apply the record pattern `Leaf(...)` to `null`.

Practical rule: **stop deconstructing at any level that may be `null` by using `var`, check the value, and only continue accessing further when it is valid**.

## 4. Do not confuse var with every type pattern

This distinction also applies to component type patterns. Given:

```java
record Box(Object content) {}
Object obj = new Box(null);
```

The following checks produce these results:

```java
obj instanceof Box(var value)     // true; value == null
obj instanceof Box(Object value)  // true; value == null
obj instanceof Box(String value)  // false
```

Because `Box` declares its component as `Object`:

- `var value` infers the type `Object`, so it matches even `null`.
- `Object value` is an unconditional type pattern with respect to the component type `Object`; when placed inside a record pattern, it also matches `null`.
- `String value` requires an actual `String` value; a `null` component does not match. It also does not match if the component is an object of a type other than `String`.

The exact condition is: **a type pattern appearing directly in the component list of a record pattern can match `null` if that pattern is unconditional with respect to the declared type of the component**. `var` in this position is the most common case. This rule applies to *component patterns*; `null instanceof Tree t` at the top level is still `false`.

For primitive-type components, such as `record Counter(int count) {}`, `count` cannot have the value `null`. The `null` issue only arises with reference types (including wrapper types like `Integer`).

## 5. Classifying null at each level with switch

Starting in Java 21, you can use `switch` with record patterns and `when` to express the branches clearly:

```java
static String classify(Object input) {
    return switch (input) {
        case null -> "outer=null";
        case Tree(Branch(Leaf(var content))) ->
                content == null ? "content=null" : "complete";
        case Tree(Branch(var leaf)) when leaf == null ->
                "leaf=null";
        case Tree(var branch) when branch == null ->
                "branch=null";
        default -> "other";
    };
}
```

How to read the branches:

1. `case null` matches when the **`switch` selector value itself** is `null`; it does not automatically match `null` inside child records.
2. `case Tree(Branch(Leaf(var content)))` applies when all three record objects are non-`null`. This branch handles `content == null` separately.
3. `case Tree(Branch(var leaf)) when leaf == null` is for non-`null` `Tree` and `Branch`, where `leaf` is `null`.
4. `case Tree(var branch) when branch == null` is for non-`null` `Tree`, where `branch` is `null`.
5. `default` handles objects that do not belong to any of the cases above (for example, `String`).

**Branch order matters:** check the most specific structure first, followed by less deeply deconstructed cases. A pattern or broad condition placed too early can shadow a specific case or cause later `case` labels to fail compilation due to *dominance*. In Java 21, when you need to catch `null` inside a record, capture the component with `var` and check `when ... == null` as shown above.

In particular, with `switch (input)`, if `input == null` and there is **no** `case null` (or an equivalent `null`-handling branch according to language rules), Java 21 will throw a `NullPointerException` before reaching `default`. `default` is not a substitute for `case null`.

## 6. The if alternative: checking sequentially before accessing

Using `switch` is not mandatory. A simple approach that is easy to set breakpoints on is checking from outside to inside:

```java
static String classifyWithIf(Object input) {
    if (input == null) {
        return "outer=null";
    }
    if (!(input instanceof Tree(var branch))) {
        return "other";
    }
    if (branch == null) {
        return "branch=null";
    }
    Leaf leaf = branch.leaf(); // safe: branch != null already checked
    if (leaf == null) {
        return "leaf=null";
    }
    Object content = leaf.content(); // safe: leaf != null already checked
    return content == null ? "content=null" : "complete";
}
```

The snippet above is **a method placed inside the class in the example below**, where `Tree`, `Branch`, and `Leaf` are already defined; the method snippet itself is not a standalone Java file. The advantage is that each `null` level has its own branch, avoiding calls to `branch.leaf()` or `leaf.content()` before checking the receiver object. By contrast, the expression `new Tree(null).branch().leaf()` will throw a `NullPointerException` because `leaf()` is called on `branch == null`.

## 7. Complete Java program and execution output

Save the code to a file named **`NestedNullPatterns.java`**:

```java
public class NestedNullPatterns {
    record Leaf(Object content) {}
    record Branch(Leaf leaf) {}
    record Tree(Branch branch) {}
    record Box(Object content) {}

    static String classify(Object input) {
        return switch (input) {
            case null -> "outer=null";
            case Tree(Branch(Leaf(var content))) ->
                    content == null ? "content=null" : "complete";
            case Tree(Branch(var leaf)) when leaf == null ->
                    "leaf=null";
            case Tree(var branch) when branch == null ->
                    "branch=null";
            default -> "other";
        };
    }

    static void demo(Object value) {
        System.out.println(classify(value));
        System.out.println(
                "nested=" + (value instanceof Tree(Branch(Leaf(var content)))));
    }

    public static void main(String[] args) {
        demo(null);
        demo(new Tree(null));
        demo(new Tree(new Branch(null)));
        demo(new Tree(new Branch(new Leaf(null))));
        demo(new Tree(new Branch(new Leaf("OK"))));

        Object box = new Box(null);
        System.out.println("box-var=" + (box instanceof Box(var v)));
        System.out.println("box-Object=" + (box instanceof Box(Object v)));
        System.out.println("box-String=" + (box instanceof Box(String v)));
    }
}
```

Compile and run with **JDK 21 or newer**:

```bash
javac --release 21 -encoding UTF-8 NestedNullPatterns.java
java NestedNullPatterns
```

Output:

```text
outer=null
nested=false
branch=null
nested=false
leaf=null
nested=false
content=null
nested=true
complete
nested=true
box-var=true
box-Object=true
box-String=false
```

The `nested=false` results in the first three cases reflect that the outer record, `Branch`, or `Leaf` respectively could not match due to `null`. When only `content` is `null`, the result becomes `nested=true`: `var content` matches and preserves `null`. The last three lines show that `var` and `Object` accept `null` in the `Box(Object)` component, whereas `String` does not.

## 8. Proactively enforcing non-null rules in records

If business logic requires `branch` to always be present, you can enforce the data constraint right when creating the record:

```java
record StrictTree(Branch branch) {
    StrictTree {
        java.util.Objects.requireNonNull(branch, "branch");
    }
}
```

This compact constructor rejects `new StrictTree(null)` with a `NullPointerException`. You can place a similar check on `Branch.leaf` or `Leaf.content` if each component must be non-`null` according to business rules. This is **a measure to enforce data invariants**; it does not change the `null`-matching rules of record patterns. The `Tree`, `Branch`, and `Leaf` records in the runnable example above intentionally allow `null` so that each level can be observed clearly.

Do not assume that every record created with a default constructor already has `null` checks: a record automatically generates accessors and a constructor, but forbidding `null` in reference components must be explicitly established by the author.

## 9. Common mistakes and how to avoid them

1. **Thinking that `var` does not match `null`.** When `var` is a component pattern inside a record pattern, it can match `null`. Check the variable before calling methods on it.
2. **Thinking that a deep nested pattern match guarantees complete data.** `Tree(Branch(Leaf(var content)))` only guarantees that the three records along the path are non-`null`; `content` can still be `null`.
3. **Using `case null` to handle every nesting level.** `case null` only applies to the selector object of `switch`. For record components, you need an appropriate pattern along with a `when` guard or an `if` check.
4. **Calling accessors before checking.** `tree.branch().leaf().content()` can throw a `NullPointerException` when an intermediate component is `null`. Use a nested record pattern or sequential checks instead.
5. **Assuming every type pattern matches `null`.** Whether a component type pattern matches `null` depends on whether it is *unconditional* with respect to the component type; `Box(String s)` against a `Box(Object)` holding `null` is an example that does not match.
6. **Reordering `case` branches arbitrarily.** Overly broad branches can shadow deeper branches. Handle specific shapes first before fallbacks, and compile to check for dominance.
7. **Assuming a switch `default` handles a `null` selector.** With Java 21 `switch`, explicitly include `case null` when the selector may be `null`.

## 10. Self-check questions

**Question 1.** Given `Object t = new Tree(new Branch(new Leaf(null)));`, is the expression `t instanceof Tree(Branch(Leaf(var c)))` true or false? — **True**; `c == null` inside the matched branch.

**Question 2.** Given `Object t = new Tree(new Branch(null));`, is the expression `t instanceof Tree(Branch(Leaf(var c)))` true or false? — **False**; `Leaf(...)` does not match `null`. To capture this component, you can use `Tree(Branch(var leaf))` and then check `leaf == null`.

**Question 3.** Does `Box(Object)` containing `null` match `Box(Object v)`? — **Yes**. When used as a component pattern that is unconditional with respect to the component type `Object`, `Object v` matches `null` as well.

**Question 4.** Why does a `switch` with `default` still need `case null`? — Because `null` in the **selector** has its own handling mechanism; `default` does not implicitly accept a `null` selector.

**Official documentation:** [Oracle Java 21 — Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html), [JEP 440](https://openjdk.org/jeps/440), [JEP 441](https://openjdk.org/jeps/441), [Java Language Specification 21, `14.30 Patterns](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30).

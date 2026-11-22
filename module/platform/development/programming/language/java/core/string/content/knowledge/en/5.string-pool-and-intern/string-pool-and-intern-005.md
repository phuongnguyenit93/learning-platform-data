# `String.intern` and Content-Based Reference Canonicalization

In Java, two `String` objects can hold **the same content** yet have **two different references**. The `String.intern()` method solves a specific need: obtaining **a shared canonical reference for the same string content** from the *string pool*. As a result, when two strings have been interned and have equal content, their `intern()` results reference **the same object**.

The word "canonicalization" in this lesson means **content-based reference canonicalization**; it does **not** mean automatically normalizing letter case, whitespace, or Unicode (NFC/NFD). To write correct programs, clearly separate three operations: **creating or holding a `String` object**, **comparing content with `equals()`**, and **obtaining a pooled reference with `intern()`**.

## 1. String Content and Object Identity Are Different

Example:

```java
String a = new String("Java");
String b = new String("Java");
```

Each `new String("Java")` expression creates a **new `String` object**, so `a` and `b` are two distinct references, even though the content is identical:

```text
a ──────> String #1 ── content "Java"
b ──────> String #2 ── content "Java"
```

- `a.equals(b)` returns `true` because `String.equals()` checks for the same sequence of characters.
- `a == b` returns `false` because `==` between two reference-type variables asks whether they point to **the same object**.
- Both objects are **immutable**: the content of a `String` cannot be modified after the object is created. Content immutability does not mean every equal string is the same object.

Conversely:

```java
String x = "Java";
String y = x;
```

`y = x` merely copies the **reference** value, so `x == y` is `true`. This behavior does not require `intern()`: both variables point to the same object directly from the assignment.

## 2. The String Pool and the Contract of `intern()`

The *String pool* is a store managed by the `String` class so that strings with the same content can share a single canonical object. This is a mechanism concerned with **reference identity**; it does not change the content-comparison rules of `String.equals()`.

For a non-null variable `s`, the call:

```java
String canonical = s.intern();
```

means:

1. If the pool already contains a `String` whose content satisfies `equals(s)`, `intern()` returns **a reference to the object already in the pool**.
2. Otherwise, the pool records the `s` object itself as the canonical representation and returns its reference, according to the `String.intern()` contract.
3. Subsequently, calls to `intern()` on other strings with **the same content** receive the same canonical reference, provided the objects and content are evaluated under Java's contract.

The core property for two **non-null** strings `s` and `t`:

```java
s.intern() == t.intern()
```

has the same boolean value as:

```java
s.equals(t)
```

This is the guarantee to understand: **equal content ⇒ interned results share the same reference**; different content ⇒ interned results are not the same object. You do not need (and should not) rely on memory addresses, allocation order, or how a JVM implements the pool in order to use this contract.

### Conceptual diagram

Suppose the pool already contains the string `"Java"`:

```text
a ────────> String #1: "Java" (non-canonical object)
                            \
                             \ a.intern()
                              v
String pool ["Java"] ──────> Canonical String: "Java"
                              ^
                             / b.intern()
                            /
b ────────> String #2: "Java" (non-canonical object)
```

Both `a.intern()` and `b.intern()` lead to **the same canonical object**. However, calling the method **does not automatically reassign** `a` or `b`. If you want a variable to hold the canonical reference, you must use the return value: `a = a.intern();`.

### What must not be inferred?

- `s.intern()` does **not necessarily** return a different object from `s`. If `s` itself is chosen as the canonical representation (or already is the canonical representation), `s == s.intern()` can be `true`. Conversely, when the pool already holds another representation, that expression can be `false`.
- `intern()` does not modify the content of `s` and does not "merge" all variables currently holding different objects.
- Two independently created `String` objects do not become the same object just by calling `equals()`. `equals()` is a content check; it does not change references.
- `intern()` is an instance method; calling it on `null` throws `NullPointerException`.

## 3. Complete Example: `intern` Returns the Canonical Object While the Old Variable Stays Unchanged

Save the code as **`InternReferenceDemo.java`**:

```java
public class InternReferenceDemo {
    public static void main(String[] args) {
        String literal = "Java";
        String fromNew = new String("Java");
        String fromBuilder = new StringBuilder()
                .append("Ja")
                .append("va")
                .toString();

        String canonical = fromBuilder.intern();

        System.out.println("new == literal: " + (fromNew == literal));
        System.out.println("new.equals(literal): " + fromNew.equals(literal));
        System.out.println("new.intern == literal: "
                + (fromNew.intern() == literal));

        System.out.println("builder == literal: "
                + (fromBuilder == literal));
        System.out.println("builder == canonical: "
                + (fromBuilder == canonical));
        System.out.println("canonical == literal: "
                + (canonical == literal));
        System.out.println("builder.equals(canonical): "
                + fromBuilder.equals(canonical));

        fromBuilder = fromBuilder.intern();
        System.out.println("builder after assignment == literal: "
                + (fromBuilder == literal));
    }
}
```

In the directory containing the file, using JDK 17+:

```bash
javac InternReferenceDemo.java
java InternReferenceDemo
```

**Stdout:**

```text
new == literal: false
new.equals(literal): true
new.intern == literal: true
builder == literal: false
builder == canonical: false
canonical == literal: true
builder.equals(canonical): true
builder after assignment == literal: true
```

**Interpretation:**

1. The literal `"Java"` is interned automatically, so `literal` points to the representation in the pool.
2. `new String("Java")` creates a separate `String` object. Thus `fromNew == literal` is `false`, while `fromNew.equals(literal)` is `true`.
3. `fromNew.intern()` returns the `"Java"` representation in the pool, so it has the same reference as `literal`.
4. `StringBuilder.toString()` creates a result object whose content equals `"Java"` but is distinct from the literal object. `fromBuilder.intern()` finds the canonical representation and returns that reference.
5. After calling `intern()`, `fromBuilder` **still** holds the old reference: `fromBuilder == canonical` is `false`. Only the final statement `fromBuilder = fromBuilder.intern();` updates the variable, making `fromBuilder == literal` become `true`.

The example intentionally uses an existing literal before calling `intern()` so that the reference outcome **does not depend** on how a never-before-seen string content gets added to the pool.

## 4. Literals, Compile-Time Constants, and Runtime Concatenation

There is no need to call `intern()` when you only want a string literal: **Java string literals are interned**. Under Java's rules, **constant expressions of type `String`** evaluated at compile time share the same property. However, concatenation based on a non-compile-time-constant variable is a runtime operation; do not treat its result as a literal.

Save **`InternConstantDemo.java`**:

```java
public class InternConstantDemo {
    public static void main(String[] args) {
        String literal = "Java";

        String folded = "Ja" + "va";
        final String constantPart = "Ja";
        String foldedFromFinal = constantPart + "va";

        String mutablePart = "Ja";
        String runtime = mutablePart + "va";

        System.out.println("literal == folded: " + (literal == folded));
        System.out.println("literal == foldedFromFinal: "
                + (literal == foldedFromFinal));
        System.out.println("literal == runtime: "
                + (literal == runtime));
        System.out.println("literal.equals(runtime): "
                + literal.equals(runtime));
        System.out.println("literal == runtime.intern(): "
                + (literal == runtime.intern()));
    }
}
```

```bash
javac InternConstantDemo.java
java InternConstantDemo
```

**Stdout:**

```text
literal == folded: true
literal == foldedFromFinal: true
literal == runtime: false
literal.equals(runtime): true
literal == runtime.intern(): true
```

Why?

- `"Ja" + "va"` is a **compile-time constant**. The compiler treats it as `"Java"`; the literal representation is interned.
- `constantPart` is a **constant variable**: a `final` variable of type `String` initialized with a constant expression. `constantPart + "va"` is also a constant expression, so it receives the same reference as the literal.
- `mutablePart` is not a constant variable. `mutablePart + "va"` is concatenated at runtime, creating a separate result object; thus `literal == runtime` is `false`, even though the content is equal.
- `runtime.intern()` finds the existing literal representation in the pool. The result `literal == runtime.intern()` is `true`.

**Note:** Not **every `final` variable** forms a constant expression. For example, `final String part = getInput();` is not a compile-time constant because its value is only known at runtime. Judge by **constant expression** rules, not merely by the `final` keyword.

**Practical takeaway:** `==` sometimes returning `true` for two equal strings is a consequence of literals/interning. It does not turn `==` into a content-comparison operator for arbitrary strings.

## 5. Two Dynamic Strings with Equal Content: `intern` Yields the Same Reference Regardless of Pool History

You can verify reference canonicalization **without guessing** whether the pool already contains the value.

**`InternInvariantDemo.java`**

```java
public class InternInvariantDemo {
    public static void main(String[] args) {
        char[] letters = {'q', 'u', 'a', 'r', 't', 'z'};

        String first = new String(letters);
        String second = new String(letters);
        String other = new String(new char[] {'Q', 'u', 'a', 'r', 't', 'z'});

        System.out.println("first == second: " + (first == second));
        System.out.println("first.equals(second): " + first.equals(second));
        System.out.println("first.intern == second.intern: "
                + (first.intern() == second.intern()));
        System.out.println("first.intern == other.intern: "
                + (first.intern() == other.intern()));
        System.out.println("first unchanged content: " + first);
    }
}
```

```bash
javac InternInvariantDemo.java
java InternInvariantDemo
```

**Stdout:**

```text
first == second: false
first.equals(second): true
first.intern == second.intern: true
first.intern == other.intern: false
first unchanged content: quartz
```

- Two calls to `new String(letters)` create two distinct objects.
- Because `first` and `second` have equal content, **regardless** of whether `"quartz"` was already in the pool, `first.intern() == second.intern()` must be `true`.
- `other` starts with `Q` instead of `q`; `String.equals()` is case-sensitive, so the interned representation is also different.
- Calling `intern()` does not change `first`: its content remains `"quartz"` and the variable was not reassigned.

If the pool does **not yet** contain an equivalent representation, the specification of `intern()` allows the first object itself to be added as the canonical representation. If the pool **already** contains one, it returns the existing representation. Because you do not control every string that the JVM or libraries may have interned earlier, examples should not assume `first == first.intern()` is always true or always false.

## 6. "Reference Canonicalization" Is Different from Unicode Text Normalization

`String.intern()` uses **content equality under `String.equals()`**, so it does not automatically trim whitespace, convert uppercase to lowercase, or normalize Unicode.

For example:

- `"ready"` and `"READY"` are not `equals()`, because their case differs. They have two different canonical references.
- `"Java"` and `"Java "` are not `equals()`, because one string has a trailing space.
- `"\u00E9"` (precomposed é: one code point) and `"e\u0301"` (e plus combining acute accent: two code points) may look identical, yet they are **not** `equals()` and do **not** become the same object merely via `intern()`.

If business requirements call for comparing equivalent Unicode forms, **normalize the text first** using `java.text.Normalizer`, and only then compare or intern if reference sharing is genuinely needed.

**`InternUnicodeDemo.java`**

```java
import java.text.Normalizer;

public class InternUnicodeDemo {
    public static void main(String[] args) {
        String composed = "\u00E9";
        String decomposed = "e\u0301";

        System.out.println("raw equals: "
                + composed.equals(decomposed));
        System.out.println("raw intern ==: "
                + (composed.intern() == decomposed.intern()));

        String normalized = Normalizer.normalize(
                decomposed, Normalizer.Form.NFC);

        System.out.println("NFC equals: "
                + composed.equals(normalized));
        System.out.println("NFC intern ==: "
                + (composed.intern() == normalized.intern()));
    }
}
```

```bash
javac InternUnicodeDemo.java
java InternUnicodeDemo
```

**Stdout:**

```text
raw equals: false
raw intern ==: false
NFC equals: true
NFC intern ==: true
```

`Normalizer.Form.NFC` resolves the Unicode equivalence in this example. By default it does not address case sensitivity, linguistic semantics, or locale-specific comparison rules. Use `intern()` **after** the normalization step only when reference sharing is genuinely beneficial; `equals()` on normalized strings is already sufficient to check content.

## 7. When to Use `intern()` and When to Use `equals()`

| Goal | Appropriate tool | Reason |
|---|---|---|
| Check whether two strings represent the same text | `a.equals(b)`, or `Objects.equals(a, b)` when null is possible | Accurate for content without depending on the pool |
| Ensure two strings with equal content use the same canonical reference | `a.intern()`, `b.intern()` | Two `intern()` results of equal strings share the same identity |
| Check whether two variables point to the exact same object | `a == b` | Compares object identity, does not compare content by itself |
| Obtain a literal as a constant string | Write `"text"` | Literals are interned automatically |
| Look up a key by text in `HashMap<String, ...>` | Let `HashMap` use `equals()`/`hashCode()` | Interning is not needed for accurate lookup |
| Reduce duplicate objects for a relatively small, frequently repeated set of values | Consider interning if measurements confirm a benefit | The pool also incurs memory and processing cost; measure on real workloads |
| Normalize Unicode text or compare case-insensitively | `Normalizer` or dedicated text-comparison rules | Interning does not perform text transformations |

### Example: `HashMap` still looks up keys accurately even with different references

**`MapWithoutInternDemo.java`**

```java
import java.util.HashMap;
import java.util.Map;

public class MapWithoutInternDemo {
    public static void main(String[] args) {
        Map<String, Integer> levels = new HashMap<>();
        levels.put("READY", 7);

        String input = new String("READY");

        System.out.println("same reference: " + (input == "READY"));
        System.out.println("same content: " + input.equals("READY"));
        System.out.println("lookup: " + levels.get(input));
        System.out.println("contains: " + levels.containsKey(input));
    }
}
```

```bash
javac MapWithoutInternDemo.java
java MapWithoutInternDemo
```

**Stdout:**

```text
same reference: false
same content: true
lookup: 7
contains: true
```

`HashMap<String, Integer>` uses `String`'s `hashCode()` and `equals()` to identify keys. The fact that `input` is a separate object does **not** prevent lookup. When only lookup is needed, interning each key or each input is unnecessary and can add extra overhead.

### Null-safe comparison

Both `intern()` and `equals()` are invoked on an object. When `candidate == null`, both `candidate.intern()` and `candidate.equals("READY")` throw `NullPointerException`. You can use:

```java
"READY".equals(candidate);          // safe if candidate is null
java.util.Objects.equals(a, b);      // safe if a or b is null
```

This is an **illustrative snippet**, not a standalone program. `Objects.equals(null, null)` returns `true` because both references are null; it does not create an empty string or any interned object.

## 8. The Contract of `intern` and Practical Limits

### 8.1. Why not use `==` instead of `equals()` in business code?

If **both references are guaranteed to be interned**, `==` reflects content equality. However, in real-world programs, data can arrive from files, HTTP, databases, `StringBuilder`, users, or external libraries. There is no guarantee that all inputs are interned unless the application itself enforces and maintains that invariant.

A snippet like:

```java
if (status == "READY") { /* ... */ }
```

is **buggy illustrative code when used to compare content**: it might accidentally pass with literals yet fail on a `new String("READY")` or a runtime-created result. If the goal is content comparison, write:

```java
if ("READY".equals(status)) { /* ... */ }
```

This expresses intent more clearly and is safe when `status` may be null.

### 8.2. Interning is not a substitute for data management

You should not automatically intern **every** string entering an application:

- Every intern call requires looking up/maintaining pool data; calling it heavily incurs CPU, memory, and memory-management interaction costs.
- If many values are **unique** or input cardinality is unbounded, the sharing benefit is small while the cost still occurs.
- If values are small and heavily repeated, it may reduce duplicate objects; however, you must measure with a profiler/benchmark on representative data to see whether it actually helps.
- Do not rely on assumptions like "all interned strings live forever" or "the pool never consumes memory": retention/collection policies and implementations can vary across JVMs and versions.
- Do not treat interning as a full-featured application cache: it has no metadata, size limit, or application-specific eviction policy to tune like a regular cache.

If the set of status labels is small and controlled, consider an `enum` or business identifier instead of forcing every user-supplied value into an interned string.

### 8.3. Do not use interned strings as arbitrary synchronization locks

Example:

```java
synchronized (userId.intern()) {
    // illustrative code: the lock may be shared unintentionally
}
```

This is an **example to avoid**, not a recommended synchronization pattern. Any component interning the same content as `userId` can obtain the same lock object, including unrelated code outside your control. This can cause lock contention or unexpected interactions between components. Manage dedicated locks with explicit lifecycles and scopes; do not turn the shared string pool into a business locking system.

### 8.4. A canonical reference is not a hash value

`intern()` does not return a numeric ID, hash code, or memory pointer that can be saved to a file. It returns a **`String` reference**. Do not use `System.identityHashCode()` as a substitute for `==` checks or to verify canonical references: identity hash codes are not guaranteed to be unique across all objects. When content needs to be checked, `equals()` remains the right choice.

## 9. Common Misconceptions

| Misconception | Reality | Right approach |
|---|---|---|
| Two strings with equal content are always `==` `true` | `==` compares references; two separate objects can be `equals()` without being `==` | Use `equals()` for content |
| Calling `a.intern();` makes variable `a` point to the pool | `intern()` **returns** the canonical reference; it does not reassign the variable | When truly needed, use `a = a.intern();` |
| Interning creates a new object every time | If a representation exists, it returns the existing reference; if not, it may add the caller object itself | Understand the pool contract properly |
| Every `s.intern()` call guarantees `s == s.intern()` | Depends on whether `s` is already the canonical object | Rely only on `s.intern() == t.intern()` for equal strings |
| `"Ja" + "va"` and runtime variable concatenation have the same reference behavior | Constant expressions are handled at compile time; runtime concatenation produces a separate result | Do not infer equality via `==` |
| Interning handles Unicode, diacritics, and case | The pool only groups strings that are `equals()` | Normalize content beforehand if business rules require it |
| `HashMap` requires interning to look up strings accurately | `HashMap` relies on `equals()` and `hashCode()` | Use normal `String` keys |
| The more you intern, the more memory you save | The pool and lookup processing have overhead; low-duplication strings are unlikely to benefit | Measure, and use only with good reason |
| Interned strings can be used as default locks | Other parts of the JVM can share the same canonical object | Use a locking mechanism under your application's control |

## 10. Knowledge Self-Check

Read the following program and predict the output before running it:

**`InternSelfCheck.java`**

```java
public class InternSelfCheck {
    public static void main(String[] args) {
        String a = "cat";
        String b = new String("cat");
        String c = b.intern();

        System.out.println(a == b);
        System.out.println(a == c);
        System.out.println(b.equals(c));

        b = b.intern();
        System.out.println(a == b);

        String d = new String("CAT");
        System.out.println(a.intern() == d.intern());
    }
}
```

```bash
javac InternSelfCheck.java
java InternSelfCheck
```

**Stdout:**

```text
false
true
true
true
false
```

- `a` is an interned literal; `b` is a new object with the same content, so initially `a == b` is `false`.
- `c = b.intern()` retrieves the literal `"cat"` representation, so `a == c` is `true`.
- `b.equals(c)` is `true` because the contents are identical, unrelated directly to object identity.
- `b = b.intern()` updates variable `b` to the canonical reference, so `a == b` becomes `true`.
- `"CAT"` differs from `"cat"` under `equals()`, so their interned results have different references.

**Remember:** `equals()` answers **"do two strings have the same content?"**; `intern()` returns a **canonical reference** for that content; `==` answers **"do two references point to the same object?"**. When you know for certain that both strings are interned, `==` can check their identity; in ordinary application logic, `equals()`/`Objects.equals()` accurately expresses text comparison and avoids depending on where a string came from.
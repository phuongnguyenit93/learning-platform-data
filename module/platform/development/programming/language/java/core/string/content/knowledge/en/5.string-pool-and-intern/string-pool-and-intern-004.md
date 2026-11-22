# How `new String` Creates Objects and Its Relationship to Existing Literals in Java

When you see two ways of writing `String a = "Java";` and `String b = new String("Java");`, both `a` and `b` represent the content `Java`, yet they **differ in object identity**. Literals are managed by Java through the **string pool** mechanism; the expression `new String(...)` creates a new `String` object according to language semantics, even when the pool already holds an object with the same content.

This lesson clarifies what is reused, what is newly created, how `==`, `equals()`, and `intern()` relate to one another, and when the `String` constructor is actually needed.

## 1. Two Initialization Styles: Literal and `new String(...)`

### Using a literal

```java
String a = "Java";
String b = "Java";
```

- `"Java"` is a **string literal** in source code.
- String literals with the same character sequence are **interned**: within the same Java program execution, references to equivalent literal values use the canonical representation from the string pool.
- In this example, `a == b` is `true` because both variables reference the same canonical `String` object.
- Assigning `b = "Java"` does not require creating another `String` object with content `Java`.

### Using the constructor `new String(String original)`

```java
String a = "Java";
String b = new String("Java");
```

- The literal `"Java"` is the input to the constructor and has a representation in the string pool.
- `new String("Java")` denotes **creating a different `String` object** from the object referenced by the literal. The content value of the new object equals the literal's value.
- `a == b` is `false`, while `a.equals(b)` is `true`.
- The constructor does not automatically make the object `b` the pool's canonical representation. To obtain the canonical representation, you can call `b.intern()`.

It is important to distinguish **object creation semantics** from how much memory the JVM has to allocate at runtime. A JIT compiler may eliminate an unobservable allocation during optimization, yet the program must still exhibit Java's object identity and comparison rules. Therefore, you should not make a blanket claim that a line `new String("Java")` *always* causes the JVM to allocate exactly two new objects: the literal may already exist in the pool beforehand, and physical allocation may be optimized.

## 2. String Pool, Heap, and References: A Mental Model

Consider the example:

```java
String literal = "Java";
String sameLiteral = "Java";
String constructed = new String("Java");
String copied = new String(literal);
```

Reference relationships according to **Java semantics**:

```text
literal -----------+
                   |
sameLiteral -------+----> [Canonical String: "Java"]  (representation in pool)

constructed ------------> [Another String: "Java"]

copied -----------------> [Yet another String: "Java"]
```

The two objects created by `new` have content equal to the literal, but are distinct `String` objects in identity. Do not confuse an object identity diagram with a physical internal memory-region layout. On modern JVMs, objects in the pool are also managed like Java objects; the pool is not an "off-heap" memory region reserved exclusively for literals. In addition, immutable `String` objects may use internal data representations that vary by JVM without changing the API contract.

**Core point:** The String pool stores and returns the canonical reference for string content, whereas `new String(...)` requests creating another object to hold the same value.

## 3. Java 17+ Example: Checking `==`, `equals()`, and `intern()`

Create the file `NewStringVsLiteral.java`:

```java
public class NewStringVsLiteral {
    public static void main(String[] args) {
        String literal = "Java";
        String sameLiteral = "Java";
        String constructed = new String("Java");
        String copied = new String(literal);

        System.out.println("literal == sameLiteral: "
                + (literal == sameLiteral));
        System.out.println("literal == constructed: "
                + (literal == constructed));
        System.out.println("literal == copied: "
                + (literal == copied));
        System.out.println("constructed == copied: "
                + (constructed == copied));

        System.out.println("literal.equals(constructed): "
                + literal.equals(constructed));
        System.out.println("constructed.equals(copied): "
                + constructed.equals(copied));

        System.out.println("constructed.intern() == literal: "
                + (constructed.intern() == literal));
        System.out.println("copied.intern() == literal: "
                + (copied.intern() == literal));
    }
}
```

Compile and run:

```bash
javac -encoding UTF-8 NewStringVsLiteral.java
java NewStringVsLiteral
```

Output:

```text
literal == sameLiteral: true
literal == constructed: false
literal == copied: false
constructed == copied: false
literal.equals(constructed): true
constructed.equals(copied): true
constructed.intern() == literal: true
copied.intern() == literal: true
```

Explanation by group of results:

1. Two variables using the same literal `"Java"` point to the canonical reference, so `==` returns `true`.
2. Each execution of `new String(...)` creates a distinct object under Java semantics; `constructed` and `copied` have different references from each other and from `literal`.
3. `equals()` is implemented by `String` to compare **character sequences**; because all three objects have the same content, the result is `true`.
4. `intern()` returns the canonical reference in the pool for a string with the same content. Since the literal `"Java"` already has a canonical representation, `constructed.intern()` and `copied.intern()` both point to that object.

You can replace the string `"Java"` with another content and apply the same rules. What is guaranteed is **the relationship among references**, not a fixed count of physical objects residing in JVM memory at all times.

## 4. Why Do `==` and `equals()` Give Different Results?

| Check | What does it compare? | Example with literal and `new` object |
| --- | --- | --- |
| `a == b` | Do the two variables point to **the same object**? | `"Java"` and `new String("Java")` → `false` |
| `a.equals(b)` | Do the two strings have **the same character sequence**? | `"Java"` and `new String("Java")` → `true` |
| `a.equalsIgnoreCase(b)` | Are the contents equivalent under the method's case-insensitive comparison rules? | `"Java"` and `"JAVA"` → `true` |
| `a.intern() == b.intern()` | Do the two values share the same canonical representation in the pool? | Two strings with equal content → `true` after interning |

In most business logic, the goal is to compare **text values**, so use `equals()`, or `Objects.equals(a, b)` if `null` is possible. The coincidence that `==` returns `true` for literals does not make `==` the right way to compare the content of arbitrary `String` values.

Error-prone example:

```java
String expected = "OK";
String actual = new String("OK");

// Wrong intent if you want to compare content:
if (actual == expected) {
    System.out.println("Match");
}

// Right intent:
if (expected.equals(actual)) {
    System.out.println("Match");
}
```

This is an illustrative snippet placed inside a method. Only the branch using `equals()` prints `Match`. Placing the known non-null literal/value first in `expected.equals(actual)` also avoids a `NullPointerException` if `actual` happens to be `null`.

## 5. What Does `String.intern()` Return When a Literal Already Exists?

The `String.intern()` method looks up the canonical representation in the string pool for the **content** of the target object:

- If the pool already contains a `String` whose content is equal according to `equals()`, `intern()` returns the existing object.
- If not, the corresponding object is placed into the pool and becomes the canonical representation, per the `intern()` contract.
- `intern()` **does not change the content** of the `String` and does not mean the variable on which the method was called automatically switches to the new reference.

With `String a = new String("Java");`, the literal `"Java"` is already in the source code and interned. Therefore:

```java
String literal = "Java";
String differentObject = new String("Java");
String canonical = differentObject.intern();

System.out.println(differentObject == literal); // false
System.out.println(canonical == literal);       // true
System.out.println(differentObject == canonical); // false
```

The lines above are an illustrative snippet that can be placed inside `main`. If you want the variable `differentObject` to subsequently point to the canonical reference, you must **reassign** it: `differentObject = differentObject.intern();`. A standalone `intern()` call does not modify the original variable.

When there is no corresponding literal in the code and the content is generated dynamically, you should not predict **which object is the canonical representation** or try to pinpoint the exact moment a string enters the pool. What you can reliably rely on is: two strings with equal content, once interned, will reference the same canonical representation.

**You should not call `intern()` on every string** out of habit. The pool has to manage canonical values, and interning a very large set of low-duplication dynamic strings can increase memory or processing overhead. Consider it only when there is a genuine need to canonicalize references for many repeated values and you have measured the impact.

## 6. Literals, Compile-Time Constant Expressions, and Runtime Concatenation

Java has another important rule: **string constant expressions** (constant expressions of type `String`) are also interned. For example, `"Ja" + "va"` is a compile-time constant expression and therefore corresponds to the literal `"Java"`.

By contrast, concatenation with an operand that is not a constant expression executes at runtime, producing a `String` value with the corresponding content that usually has a different reference from the literal until you explicitly call `intern()`.

File `ConstantVsRuntime.java`:

```java
public class ConstantVsRuntime {
    public static void main(String[] args) {
        String literal = "Java";
        String folded = "Ja" + "va";

        String suffix = new String("va");
        String joinedAtRuntime = "Ja" + suffix;

        System.out.println("folded == literal: "
                + (folded == literal));
        System.out.println("joinedAtRuntime == literal: "
                + (joinedAtRuntime == literal));
        System.out.println("joinedAtRuntime.equals(literal): "
                + joinedAtRuntime.equals(literal));
        System.out.println("joinedAtRuntime.intern() == literal: "
                + (joinedAtRuntime.intern() == literal));
    }
}
```

Run:

```bash
javac -encoding UTF-8 ConstantVsRuntime.java
java ConstantVsRuntime
```

Output:

```text
folded == literal: true
joinedAtRuntime == literal: false
joinedAtRuntime.equals(literal): true
joinedAtRuntime.intern() == literal: true
```

Reason: `folded` is the result of concatenating **two literals**; the compiler determines the constant value `"Java"` and uses the canonical representation. Conversely, `suffix` comes from the object creation expression `new String("va")`, so `"Ja" + suffix` is not a constant expression under the language rules. The concatenation result has content `"Java"` but does not automatically become the literal's canonical reference.

A `final String` variable initialized with a constant expression can also be a **constant variable**:

```java
final String prefix = "Ja";
String stillConstant = prefix + "va";
System.out.println(stillConstant == "Java"); // true
```

Conversely, simply adding `final` does not make every concatenation a compile-time constant: the initializer must also satisfy the *constant expression* rules. This is why some `==` tests on string concatenation appear to give "sometimes true, sometimes false." That is why you should use `equals()` for content.

## 7. `new String` with Non-Literal Sources

The scope of constructors goes beyond literals. Java also supports creating a `String` from an existing `String` object, from `char[]`, from array slices, or from bytes with an appropriate character encoding.

### Creating from an existing `String`

```java
String original = "data";
String copy = new String(original);

System.out.println(original == copy);      // false
System.out.println(original.equals(copy)); // true
```

Both have equal content, yet the constructor still creates a new object according to Java semantics. However, because `String` is **immutable**, creating a new object merely to "protect the content" from being modified is unnecessary. Nor should you assume that this constructor necessarily makes an independent copy of the entire internal character storage; that is a JVM implementation detail, not a reason to use the constructor.

### Creating from `char[]`: taking a snapshot of content at creation time

A `char[]` array **is mutable**, so this case has a different meaning.

File `NewStringFromArray.java`:

```java
public class NewStringFromArray {
    public static void main(String[] args) {
        char[] letters = {'J', 'a', 'v', 'a'};
        String fromArray = new String(letters);
        String literal = "Java";

        letters[0] = 'X';

        System.out.println("array=" + new String(letters));
        System.out.println("fromArray=" + fromArray);
        System.out.println("sameContent=" + fromArray.equals(literal));
        System.out.println("sameReference=" + (fromArray == literal));
    }
}
```

Run:

```bash
javac -encoding UTF-8 NewStringFromArray.java
java NewStringFromArray
```

Output:

```text
array=Xava
fromArray=Java
sameContent=true
sameReference=false
```

`new String(letters)` captures the array's content at creation time. Modifying `letters` afterward does not modify `fromArray`; this is an important contract between a mutable `char[]` source and an immutable `String` target. The value of `fromArray` still equals the literal `"Java"`, but because it was created via `new`, it does not share the literal's reference.

Similarly, there are constructors `new String(StringBuilder)` and `new String(StringBuffer)` to create a `String` from the current content of a buffer. However, when you already have a valid `String`, `new String(existingString)` rarely provides additional value.

### Creating from bytes requires knowing the charset

`new String(bytes, StandardCharsets.UTF_8)` has the job of **decoding bytes** according to UTF-8; this is not an operation for "copying a literal." When using byte constructors, pass an explicit charset matching the input data to avoid corrupted characters. Constructors accepting `String` and `char[]` do not solve byte decoding.

## 8. Should You Use `new String("literal")` in Applications?

**Usually no.** If you simply want to use fixed text content, assigning the literal directly is both concise and takes advantage of canonical reference reuse:

```java
String status = "READY"; // Suitable for a known constant value
```

If you already have a `String` object from a method or parameter, just reuse that value:

```java
static String normalizeStatus(String status) {
    return status == null ? "UNKNOWN" : status.trim();
}
```

This is an illustrative method placed in a class. Using `new String(status)` before or after `trim()` does not make string comparison safer and does not prevent others from modifying the `String`'s content (since the content is already immutable).

**Invalid** reasons to arbitrarily add `new String("...")`:

- "So the string cannot be modified from outside": `String` is already immutable.
- "To always create a string with different content": the constructor creates a different **object**, not different content.
- "To make `==` comparison accurate": it changes reference comparison; value comparison still needs `equals()`.
- "To save memory via the string pool": `new` is not the mechanism for reusing canonical representations.
- "To definitely copy the internal bytes/chars": whether internal data inside `String` is shared or copied is not part of the `String(String)` constructor's contract.

**Use a constructor when the input genuinely needs conversion to `String`**, such as `char[]`, `StringBuilder`, `StringBuffer`, or bytes with a specified charset. When the source is already a `String`, the copy constructor for object-identity semantics is rarely needed.

## 9. `null`, Identity, and Common Pitfalls

### Passing `null` to a constructor

A `String` reference equal to `null` is not an empty string object:

```java
String absent = null;
// String copy = new String(absent); // Throws NullPointerException at runtime
```

This is an illustrative snippet inside a method. Writing `new String(null)` directly should also not be used for testing, because `String` has multiple overloaded constructors, so a bare `null` literal causes an **ambiguous overload** error at compile time. If business rules require an empty string, check for `null` and explicitly return `""`.

### Common design mistakes

1. **Assuming two strings with equal content are always `==`.** You can rely on reference relationships only when you intentionally manage pooling/identity; for text comparison, use `equals()`.
2. **Thinking `new String("x")` creates new content.** The value is still `"x"`; the difference is object identity.
3. **Counting objects from the number of literals and `new` keywords in source code.** The pool may already contain the value, literals may appear in multiple places, and the JVM may optimize allocations as long as observable behavior is unchanged.
4. **Thinking `intern()` modifies the original variable.** `intern()` returns a reference; you must capture and use the return value if the goal is to use the canonical reference.
5. **Using `new String(existingString)` defensively on immutable data.** `String` itself cannot be mutated in place; creating a new object is usually redundant.
6. **Thinking every string concatenation uses the string pool.** Constant expressions are interned; concatenation with dynamic operands follows different rules and does not automatically yield a canonical representation.
7. **Automatically interning all input values.** You must consider the number of unique strings, duplication rate, and actual resources; interning does not replace designing a bounded cache/deduplication mechanism.

## 10. Self-Check Questions

**Question 1.** What does the following snippet print?

```java
String a = "hello";
String b = new String("hello");

System.out.println(a == b);
System.out.println(a.equals(b));
System.out.println(a == b.intern());
```

**Answer:** `false`, `true`, `true` respectively. The constructor creates a different object; the content is equal; `intern()` returns the canonical representation of the existing literal.

**Question 2.** Why can `String a = "J" + "ava";` be `==` to `"Java"`, whereas `String b = "J" + someVariable;` should not be tested this way?

**Answer:** `"J" + "ava"` is a compile-time constant expression and has a canonical representation in the pool. If `someVariable` is not a constant variable, concatenation occurs at runtime, producing content that may equal `"Java"` but whose reference should not be used as a content-equality check.

**Question 3.** Does `new String("Java")` automatically return the exact object residing in the pool?

**Answer:** No. `new String("Java")` creates a separate `String` object; calling `intern()` on that object retrieves the existing canonical representation for the literal `"Java"`.

**Question 4.** Why is `new String(charArray)` more useful than `new String(existingString)` when the goal is preserving content against source mutations?

**Answer:** `char[]` can be modified after being passed in, whereas `String` is immutable. The array constructor provides a string value independent of subsequent changes to the array; creating an extra `String` from an existing `String` is usually unnecessary.

**Remember:** Literals and constant expressions of type `String` are interned, allowing canonical references to be reused. `new String("...")` creates a different string object with the same content as the literal. Use `equals()` for text comparison; use `intern()` only when you genuinely need a canonical representation and have weighed the cost.
# Default Form of `Object.toString()`: Class Name, `@` Sign, and Hexadecimal Hash Code

When printing an object in Java, we may see a string like `com.example.Book@5e2de80c`. This string usually appears because the class **inherits the default implementation of `Object.toString()`**. It is **not the contents of the fields**, **not a memory address guaranteed by Java**, and **not a unique identifier** of the object.

This lesson explains the exact formula used to build the string, the meaning of each part, the relationship with `hashCode()`, cases where the default format is no longer used, how to test it with Java 17, and mistakes to avoid.

## 1. Default Contract and Formula

In `java.lang.Object`, the default `toString()` implementation can be equivalently expressed as:

~~~java
public String toString() {
    return getClass().getName() + "@"
            + Integer.toHexString(hashCode());
}
~~~

This is **illustrative code showing the formula of the method in `Object`**, not a snippet to copy into every class. The three components are concatenated directly with **no spaces**:

| Component | Source | Meaning |
|---|---|---|
| `getClass().getName()` | Runtime class of the object | Class name according to Java's binary name rules |
| `"@"` | Fixed character | Separator between the class name and the hash code |
| `Integer.toHexString(hashCode())` | `int` value from `hashCode()` | Converts the hash code to a base-**16** string using lowercase letters `a`–`f` |

For a `Book` class in package `com.example` that does not override `toString()`, the output has the **form**:

~~~text
com.example.Book@5e2de80c
~~~

The `5e2de80c` part is only an **illustrative example code**, not a predictable value for an arbitrary object. Running the same source code at another time may print a different suffix. Do not use that string as expected output data in a test.

When an object does not override `toString()`, the JVM calls the method inherited from `Object`. If the class **overrides `toString()`**, Java uses that class's implementation; the `ClassName@hex` format is no longer guaranteed.

## 2. The Class Name Is the Runtime Name, Not the Variable Name

The part before `@` comes from `getClass().getName()`. It depends on the **actual object's type**, not the declared type of the variable:

~~~java
Object value = new StringBuilder("abc");
System.out.println(value.getClass().getName());
// java.lang.StringBuilder
~~~

This is a snippet placed inside `main`. The static type of `value` is `Object`, but the runtime class is `StringBuilder`.

The name part can differ from expectations:

- Top-level class in package `com.example`: `com.example.Book`, not just `Book`.
- Member class `Demo.Item`: the binary name is usually `Demo$Item`, **not** `Demo.Item`.
- Local or anonymous classes have compiler-generated name formats; do not hardcode numeric naming conventions in tests.
- For a primitive array `int[]`, `getClass().getName()` returns `[I`; for a `String[]` array it returns `[Ljava.lang.String;`. Therefore, the default `toString()` of an array has a prefix like `[I@`, rather than the text `int[]@`.

**`Class.getName()`, `getSimpleName()`, and `getCanonicalName()` do not always return the same result.** `Object.toString()` uses `getName()`. If you want a short class name for display, that is a separate choice that must be written explicitly in a custom `toString()`.

## 3. What Is the Hash Code After the `@` Sign Really?

The part after `@` is the result of the expression:

~~~java
Integer.toHexString(hashCode())
~~~

- `hashCode()` returns a signed Java `int` integer (32-bit).
- `Integer.toHexString(...)` represents the number's bits in base 16, **without adding a `0x` prefix**.
- Letters in the hex part are lowercase. For example, decimal hash code `42` becomes `2a`, `255` becomes `ff`, `0` becomes `0`, while `-1` becomes `ffffffff`.
- This value is **not guaranteed to be a memory address**, object sequence number, UUID, or program-wide unique ID.
- Two different objects can have **the same hash**. You must not infer from identical hex suffixes that two references point to the same instance.

For a class that **does not override `hashCode()`**, `Object`'s default method typically provides a value suitable for identity hashing. Java does not require computing it from a physical address. `System.identityHashCode(obj)` returns the hash code according to `Object`'s identity mechanism even when the class has overridden `hashCode()`.

One particularly important point: **`Object.toString()` calls `hashCode()` via dynamic dispatch**. If a class overrides `hashCode()` without overriding `toString()`, the hex part reflects the **overridden hashCode**, not necessarily `System.identityHashCode()`. This is why the default should not be described as `ClassName@identityHash` in all cases.

## 4. Runnable Java 17 Example: Verifying the Formula and Deterministic Output

The following example has three nested classes:

- `Plain`: keeps `Object.hashCode()` and `Object.toString()` unchanged, so the hex part cannot be predicted in advance; the program checks the formula with booleans.
- `FixedHash`: **for illustration only**, overrides `hashCode()` to return `42` and inherits `toString()`; thus the hex part is deterministically `2a`.
- `NegativeHash`: returns `-1` to check how it converts to `ffffffff`.

Save the file **`ObjectToStringDemo.java`**, without declaring a package:

~~~java
public class ObjectToStringDemo {
    static final class Plain {}

    static final class FixedHash {
        @Override
        public int hashCode() {
            return 42;
        }
    }

    static final class NegativeHash {
        @Override
        public int hashCode() {
            return -1;
        }
    }

    public static void main(String[] args) {
        Plain plain = new Plain();
        String raw = plain.toString();

        System.out.println("plain class: "
                + plain.getClass().getName());
        System.out.println("plain prefix: "
                + raw.startsWith(plain.getClass().getName() + "@"));
        System.out.println("plain formula: "
                + raw.equals(plain.getClass().getName() + "@"
                        + Integer.toHexString(plain.hashCode())));
        System.out.println("plain identity hash: "
                + (plain.hashCode()
                        == System.identityHashCode(plain)));

        FixedHash fixed = new FixedHash();
        System.out.println("fixed: " + fixed);
        System.out.println("fixed hex: "
                + Integer.toHexString(fixed.hashCode()));

        NegativeHash negative = new NegativeHash();
        System.out.println("negative: " + negative);
        System.out.println("negative hex: "
                + Integer.toHexString(negative.hashCode()));

        int[] numbers = {1, 2, 3};
        System.out.println("array class: "
                + numbers.getClass().getName());
        System.out.println("array prefix: "
                + numbers.toString().startsWith("[I@"));
        System.out.println("array content: "
                + java.util.Arrays.toString(numbers));

        String text = "hello";
        System.out.println("String toString: " + text.toString());
    }
}
~~~

Compile and run commands on JDK 17+:

~~~bash
javac ObjectToStringDemo.java
java ObjectToStringDemo
~~~

**Predictable output** (without printing `Plain`'s random hash string):

~~~text
plain class: ObjectToStringDemo$Plain
plain prefix: true
plain formula: true
plain identity hash: true
fixed: ObjectToStringDemo$FixedHash@2a
fixed hex: 2a
negative: ObjectToStringDemo$NegativeHash@ffffffff
negative hex: ffffffff
array class: [I
array prefix: true
array content: [1, 2, 3]
String toString: hello
~~~

Explanation:

1. `Plain` is a static member class inside `ObjectToStringDemo`, so `getName()` returns the binary name `ObjectToStringDemo$Plain`. The prefix and formula checks return `true` without assuming a specific hash.
2. `Plain` does not override hash, so `hashCode()` matches `System.identityHashCode()` for that instance.
3. `FixedHash` inherits `Object.toString()` but overrides `hashCode()`. The output is **exact**: `ObjectToStringDemo$FixedHash@2a`.
4. `NegativeHash` demonstrates that `Integer.toHexString(-1)` yields `ffffffff`; base-16 conversion does not place a minus sign in front.
5. `int[]` is an object with runtime name `[I` and keeps the default `toString()`. To display elements `[1, 2, 3]`, use `Arrays.toString()`.
6. `String` overrides `toString()` and therefore returns its actual content `hello`, not `java.lang.String@...`.

**Design note:** classes that intentionally return a fixed hash in the example are only used to demonstrate dispatch and hex conversion. In real software, hash codes must align with `equals()` and have reasonable distribution across data to reduce collisions in hash collections.

## 5. What Happens When a Class Overrides equals, hashCode, or toString?

Consider each case independently:

| Class Defines | Form of `toString()` if Not Overridden | What to Note |
|---|---|---|
| Overrides none of the three | `RuntimeClassName@hex(Object.hashCode())` | The hex part is unstable across runs |
| Overrides only `hashCode()` | `RuntimeClassName@hex(overriddenHashCode())` | Still **Object.toString**, but the suffix is not the default identity hash |
| Overrides only `equals()` | Still uses Object.toString and default hash | **Risk of violating contract** if two instances considered equal by equals have different hashes |
| Overrides both `equals()` and `hashCode()` | Still has the form `RuntimeClassName@hex(hashCode())` | Two equal objects have the same hash and can have the same toString string |
| Overrides `toString()` | Depends on the overriding code | Can be JSON-like, custom text, a list of properties, etc. |

Overriding `toString()` **does not mean** `equals()` or `hashCode()` changes automatically. Conversely, overriding `equals()`/`hashCode()` does not automatically generate a readable text representation. These are different contracts.

### Custom Example to Print Fields

~~~java
final class Book {
    private final String isbn;
    private final String title;

    Book(String isbn, String title) {
        this.isbn = isbn;
        this.title = title;
    }

    @Override
    public String toString() {
        return "Book{isbn='" + isbn + "', title='" + title + "'}";
    }
}
~~~

This is a compilable class declaration; to run it, a `main` method must be added. Printing `new Book("978-1", "Java")` will produce:

~~~text
Book{isbn='978-1', title='Java'}
~~~

There is no longer the full class name, `@`, or hex because the class decided its own returned string. If `Book` is used as a **value object** in `HashSet`/`HashMap`, equality/hash must still be defined accordingly when needed; `toString()` does not replace those two contracts.

## 6. Standard Classes Do Not Necessarily Print in the Object Format

Every class inherits `toString()`, but many standard classes **override** it:

- `String.toString()` returns the string content. `StringBuilder.toString()` also creates a string representing the characters it holds.
- `Integer`, `BigDecimal`, and numeric classes generally print values according to each type's own textual rules.
- `List`, `Set`, and `Map` in common implementations print their elements/mappings; iteration order of `HashSet`/`HashMap` is not guaranteed.
- `record` has a Java-generated `toString()` reflecting its components; it does not keep the `ClassName@hex` pattern. The `record` contract has its own representation rules.
- **Arrays** are a familiar case that keeps the Object-style printing: `new int[]{1,2}.toString()` does not print `[1, 2]`. Use `Arrays.toString` or `Arrays.deepToString` for nested arrays accordingly.

Therefore, **you should not infer** from one object displaying `@hex` that all other objects do the same. You need to check whether `toString()` is overridden; you can inspect the Javadoc and how the class implements the override.

## 7. What Are the Limitations and Meaning of the Hex Value?

### Not a Memory Address

According to the Java specification, `hashCode()` is an `int` value; there is no requirement that this number contain a memory address or preserve a physical address. GC can move objects, and Java users do not need to infer physical addresses from `Object.toString()`.

### Not a Unique Key

Hashes have a finite space (32 bits). Collisions can happen, even for two different objects. If you need to know whether two variables hold the same instance, use **`==` for references**; if you need two values to be equal by business rules, use `equals()`; do not take the `@hex` suffix as proof.

### Not a Stable Storage Format

Do not store the default `Object.toString()` to use as a database ID, API key, stable link, authentication token, or data that needs to be parsed across multiple runs. The `Object.toString()` contract describes the string format but does not guarantee a fixed hash for the same business meaning across different processes.

### Do Not Assume Every Hash Is an Identity Hash

If `hashCode()` is overridden, `Object.toString()` will call the new hash. Even two objects equal by `equals()` with the same hash can print the same suffix, yet that does not make them the same instance. `System.identityHashCode()` is a separate API for obtaining an identity hash (still **not** guaranteed to be unique).

## 8. Distinguishing toString, equals, and hashCode

| Question | Use | What Not to Do |
|---|---|---|
| Want to present an object for logging/debugging? | `toString()` suited to the content you want to read | Do not treat the text as a unique identity |
| Do two references point to the same object? | `a == b` | Do not compare strings `a.toString().equals(b.toString())` |
| Are two objects equal in value? | `a.equals(b)` or `Objects.equals(a,b)` | Do not rely on `toString` output |
| Need keys organized in `HashMap`/`HashSet`? | Contract-compliant `equals()` and `hashCode()` | Do not use the hex suffix of `toString` instead of a key |
| Need to print array contents? | `Arrays.toString()`/`deepToString()` | Do not use `array.toString()` to print each element |

For example: two objects having the same `toString()` **are not guaranteed to be equal**. A hand-written `toString()` might only print `name` and omit `id`, whereas equality checks ID. Conversely, two objects can be equal by `equals()` yet have different `toString()` strings if custom code does not reflect the same fields. Thus, you should not parse or compare `toString()` text to infer equality.

## 9. Common Mistakes

1. **Treating `@5e2de80c` as a memory cell address:** Java makes no such guarantee. This is the hex of the hash code.
2. **Thinking the characters after `@` always come from Object.hashCode:** when a class overrides `hashCode()`, Object.toString will call the overridden version.
3. **Hardcoding hex values when writing tests:** default hash values are not guaranteed across runs; test using the formula or only check the structure.
4. **Confusing `getSimpleName()` with `getName()`:** nested/packaged classes have binary names different from short display names.
5. **Printing an array expecting to see elements:** `int[].toString()` yields `[I@hex`; use `Arrays.toString`.
6. **Using `toString()` as equality:** the methods serve different purposes; toString may change when improving logs.
7. **Overriding only equals while forgetting hashCode:** this can cause hash collections to misbehave; toString does not fix this bug.
8. **Assuming all standard classes print in `@hex` format:** `String`, wrappers, collections, and records have different rules.

## 10. Self-Check

**Question 1.** For an object that does not override `toString()`, what is the formula to build the string?  
**Answer:** `getClass().getName() + "@" + Integer.toHexString(hashCode())`.

**Question 2.** Class `FixedHash` only overrides `hashCode()` to return `255` without overriding `toString()`. What is the part after `@`?  
**Answer:** `ff`, because `Integer.toHexString(255)` returns `"ff"`.

**Question 3.** Does the default `Object.toString()` guarantee the hex code is unique and equal to the physical address?  
**Answer:** No. Hashes can collide and the API does not promise it is a memory address.

**Question 4.** Why can nested class names contain `$`?  
**Answer:** Because `getClass().getName()` returns the binary name, not necessarily the source/simple name.

**Question 5.** If a class overrides `toString()` to print `Book{title='Java'}`, must the `@hex` part still appear?  
**Answer:** No. The returned string is determined by the new `toString()` implementation.

**Question 6.** Does `new int[]{1,2}.toString()` return `[1, 2]`?  
**Answer:** No; arrays use Object's format. To print contents, `Arrays.toString(...)` is needed.

**Key takeaway:** The default form **`RuntimeClassName@hex(hashCode())`** reflects the class name and the hash code converted to base 16; it is useful when reading logs/debugging, but it is not a unique identifier or a way to compare values. Always distinguish the format inherited from `Object` from a `toString()` overridden by a specific class.
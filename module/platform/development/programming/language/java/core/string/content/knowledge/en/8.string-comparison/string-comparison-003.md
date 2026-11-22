# Objects.equals for Two Nullable References in Java

## 1. The Problem: Comparing When One or Both References May Be null

In Java, **String** is a reference type. Two variables can hold two String objects, point to the same object, or hold **null** (referencing no object). When using **a.equals(b)**, Java must invoke the method on object **a**; if **a == null**, this statement throws **NullPointerException**.

~~~java
String first = null;
String second = "Java";

// Illustrative error snippet if executed:
boolean equal = first.equals(second); // NullPointerException
~~~

The **java.util.Objects** class provides a static method:

~~~java
boolean result = Objects.equals(first, second);
~~~

This method **safely compares two references when null is possible**. It returns **true** if both are null, or if the first value is non-null and its **equals** method evaluates the two values as equal. If only one reference is null, the result is **false**.

**Objects.equals** is useful for Strings, value objects, object properties, and methods taking optional nullable parameters. It requires **import java.util.Objects**; this API has existed since Java 7 and works seamlessly in Java 17+.

## 2. Exact Contract of Objects.equals

Signature:

~~~java
public static boolean equals(Object a, Object b)
~~~

Its behavior is essentially equivalent to:

~~~java
public static boolean nullableEquals(Object a, Object b) {
    return (a == b) || (a != null && a.equals(b));
}
~~~

The snippet above is an **illustrative method**; place it inside a class if you want to compile it. The Java runtime automatically dispatches to the **equals** method matching the actual runtime type of **a** via dynamic method dispatch.

| Reference a | Reference b | Result | Explanation |
| --- | --- | --- | --- |
| **null** | **null** | **true** | Both are null; the **a == b** branch succeeds |
| **null** | Object | **false** | **a != null** is false, no method is called |
| Object | **null** | Usually **false** for well-behaved equals | Calls **a.equals(null)**; the equals contract requires returning false |
| Same object | Same reference | **true** | **a == b** succeeds |
| Two objects with different references | Equivalent value per **a.equals(b)** | **true** | For example, two Strings with the same content |
| Two objects with different references | Non-equivalent value | **false** | Result is based on **a.equals(b)** |

**Caveat on the condition:** a poorly written **equals** implementation can violate Java's contract, throw an exception, or return inconsistent results. **Objects.equals** only handles null on the outside and delegates to the normal **equals**; it does not fix business-logic bugs or verify the symmetry of a comparison.

### Why Are Two nulls Considered Equal?

This is the rule defined for value comparisons in **Objects.equals**: two references that both lack an object are treated as equivalent. This rule often fits when checking "are these two states the same?".

However, **two missing data fields** do not always mean "two entities are the same" in business logic. When comparing mandatory non-null identifiers, validate the identifiers before calling **Objects.equals**, or require both to be non-null:

~~~java
boolean sameKnownId = idA != null && idB != null
        && idA.equals(idB);
~~~

This is an **illustrative snippet** inside a method; it returns false if either side's identifier is missing. Do not use **Objects.equals(null, null) == true** as proof that two entities without IDs are the same entity.

## 3. Complete Example: Two Nullable Strings

Save the code to **NullableStringComparisonDemo.java**:

~~~java
import java.util.Objects;

public class NullableStringComparisonDemo {
    public static void main(String[] args) {
        String missingA = null;
        String missingB = null;
        String literal = "Java";
        String newObject = new String("Java");
        String other = "Kotlin";

        System.out.println(Objects.equals(missingA, missingB));
        System.out.println(Objects.equals(missingA, literal));
        System.out.println(Objects.equals(literal, missingA));
        System.out.println(Objects.equals(literal, newObject));
        System.out.println(literal == newObject);
        System.out.println(Objects.equals(literal, other));
        System.out.println("Java".equals(missingA));
        System.out.println(Objects.equals("", missingA));
        System.out.println(Objects.equals("", ""));
    }
}
~~~

Compile and run with JDK 17 or later:

~~~bash
javac -encoding UTF-8 NullableStringComparisonDemo.java
java NullableStringComparisonDemo
~~~

Stdout:

~~~text
true
false
false
true
false
false
false
false
true
~~~

Explanation in order:

1. Both **missingA** and **missingB** are **null**, so the result is **true**.
2. Comparing **null** with **"Java"** or vice versa yields **false**.
3. **literal** and **newObject** have the same **"Java"** content, so **Objects.equals** returns **true**, even though they are two distinct objects.
4. **literal == newObject** is **false** because **==** checks references.
5. The contents **"Java"** and **"Kotlin"** are not the same.
6. **"Java".equals(missingA)** throws no exception because the receiving object is a literal guaranteed to be non-null; the result is **false**.
7. **""** is a real empty String, distinct from **null**, and two empty strings have equal content.

For two Strings, **Objects.equals(a, b)** remains case-sensitive. For example, **Objects.equals("java", "Java")** is **false**.

## 4. Distinguishing Objects.equals, equals, and ==

| Expression | Purpose | When a is null | Conclusion |
| --- | --- | --- | --- |
| **a == b** | Reference comparison (for reference types) | Safe | Indicates whether two variables point to the same object or are both null |
| **a.equals(b)** | Calls the comparison defined by a's class | Throws **NullPointerException** | Use when a is known to be non-null |
| **Objects.equals(a, b)** | Null-safe value comparison | Safe | Suitable when both references can be null |
| **"value".equals(a)** | Content comparison against a fixed value | Safe | Concise and clear when one side is a non-null String constant |
| **Objects.requireNonNull(a)** | Validates that a must be non-null | Throws **NullPointerException** | Not a comparison; used to enforce input preconditions |

The **==** operator is especially error-prone with Strings:

~~~java
String a = "hello";
String b = new String("hello");

System.out.println(a == b);               // false
System.out.println(a.equals(b));           // true
System.out.println(Objects.equals(a, b));  // true
~~~

These are illustrative statements placed inside a method with **import java.util.Objects**. The fact that some String literals are reused by the JVM in the **string pool** can make **==** occasionally return true for two literals, but you should never rely on that phenomenon to check text. Choose **equals** or **Objects.equals** to clearly express the intent to compare content.

### When to Prefer Each Approach?

- If **a** is guaranteed non-null by contract, using **a.equals(b)** is natural.
- If **both variables may be null**, use **Objects.equals(a, b)**.
- If comparing against a String constant guaranteed non-null, **"ACTIVE".equals(status)** is a concise choice.
- If you strictly want to check for the **exact same object**, use **==**.
- If business rules disallow null, validate and report an error beforehand; do not let **Objects.equals(null, null)** accidentally count as a valid case.

## 5. Null Details Worth Clarifying

**null is different from an empty string and a whitespace-only string.**

~~~java
String absent = null;
String empty = "";
String spaces = "   ";

System.out.println(Objects.equals(absent, empty)); // false
System.out.println(Objects.equals(empty, spaces)); // false
System.out.println(empty.isEmpty());               // true
System.out.println(spaces.isBlank());              // true
~~~

These illustrative statements are inside a method with **Objects** imported. The **isEmpty()** method only checks for length 0; **isBlank()** checks whether the entire string is whitespace according to Java's rules. Treating **null**, empty strings, or blank strings as identical must be an **explicitly coded business decision**, such as an input-normalization step prior to comparison.

**There is no "treat null as the string \"null\"" rule** in **Objects.equals**. For example:

~~~java
System.out.println(Objects.equals(null, "null")); // false
~~~

By contrast, **String.valueOf((Object) null)** produces a four-character String with content **"null"**; you should not use that as a substitute for null-safe comparison.

**Argument order in a standard equals call:** the **Object.equals** contract requires symmetry: **a.equals(b)** and **b.equals(a)** must be logically equivalent when both are non-null. If a class implements equals improperly, **Objects.equals(a, b)** and **Objects.equals(b, a)** might differ. The static method does not try both directions to fix the bug.

## 6. Objects.equals with Other Object Types

**Objects.equals** has a general name because it takes two **Object** parameters. When both are non-null, the result depends on the **equals** implementation of the object type on the left.

### String and Common Value Classes

**String**, wrapper classes like **Integer**, **Long**, **Boolean**, and many other Java value classes define **equals** based on meaningful data. However, some types also require an **exact type match**:

~~~java
Object number = Integer.valueOf(10);
Object longNumber = Long.valueOf(10L);

System.out.println(Objects.equals(number, longNumber)); // false
~~~

Both numeric values represent "10", but the two wrappers are different classes, so **Integer.equals(Long)** returns false. **Objects.equals** does not automatically convert numeric types, ignore locale differences, or ignore case.

### Objects That Do Not Override equals

If a class only inherits the default **Object.equals**, comparison is essentially based on **same object**. Two new objects with identical field values are not necessarily equal:

~~~java
class Box {
    int value;
    Box(int value) {
        this.value = value;
    }
}

// The following statements are inside a method:
Box first = new Box(7);
Box second = new Box(7);
System.out.println(Objects.equals(first, second)); // false
~~~

If you want two **Box** instances with the same **value** to be considered equivalent, the class must define an appropriate **equals** (and **hashCode**). **Objects.equals** does not use reflection to compare all fields.

### Arrays Are Not Deeply Compared by Objects.equals

Java arrays do not override **Object.equals** to compare elements. Therefore:

~~~java
String[] first = {"a", "b"};
String[] second = {"a", "b"};

System.out.println(Objects.equals(first, second)); // false
System.out.println(java.util.Arrays.equals(first, second)); // true
System.out.println(Objects.deepEquals(first, second)); // true
~~~

This is an illustrative snippet; import **java.util.Objects** if using the short name. Use **Arrays.equals** for one-dimensional arrays and **Arrays.deepEquals** or **Objects.deepEquals** when nested arrays need appropriate comparison. **Objects.deepEquals** also handles null, though you should avoid misusing it on array graphs with cyclic references.

For a complete illustration, save as **ArrayEqualityDemo.java**:

~~~java
import java.util.Arrays;
import java.util.Objects;

public class ArrayEqualityDemo {
    public static void main(String[] args) {
        String[] one = {"a", "b"};
        String[] two = {"a", "b"};

        System.out.println(Objects.equals(one, two));
        System.out.println(Arrays.equals(one, two));
        System.out.println(Objects.deepEquals(one, two));

        int[][] left = {{1, 2}, {3}};
        int[][] right = {{1, 2}, {3}};

        System.out.println(Arrays.equals(left, right));
        System.out.println(Arrays.deepEquals(left, right));
    }
}
~~~

~~~bash
javac -encoding UTF-8 ArrayEqualityDemo.java
java ArrayEqualityDemo
~~~

~~~text
false
true
true
false
true
~~~

**Why?** Arrays **one** and **two** are two distinct objects, yet their corresponding elements have the same content. For **int[][]**, **Arrays.equals** at the outer level compares the subarrays by reference; **Arrays.deepEquals** recursively compares the contents of the subarrays.

## 7. Writing Null-Safe equals in Your Own Classes

In an application-defined value class, you can use **Objects.equals** to compare nullable reference fields. You must override a compatible **hashCode** whenever you override **equals**.

Complete example, save as **CustomerEqualityDemo.java**:

~~~java
import java.util.HashSet;
import java.util.Objects;
import java.util.Set;

final class Customer {
    private final String email;
    private final int level;

    Customer(String email, int level) {
        this.email = email;
        this.level = level;
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) {
            return true;
        }
        if (!(other instanceof Customer that)) {
            return false;
        }

        return level == that.level
                && Objects.equals(email, that.email);
    }

    @Override
    public int hashCode() {
        return Objects.hash(email, level);
    }
}

public class CustomerEqualityDemo {
    public static void main(String[] args) {
        Customer first = new Customer(null, 2);
        Customer second = new Customer(null, 2);
        Customer other = new Customer(null, 3);

        System.out.println(first == second);
        System.out.println(Objects.equals(first, second));
        System.out.println(Objects.equals(first, other));
        System.out.println(Objects.equals(first, null));

        Set<Customer> customers = new HashSet<>();
        customers.add(first);
        System.out.println(customers.contains(second));
    }
}
~~~

~~~bash
javac -encoding UTF-8 CustomerEqualityDemo.java
java CustomerEqualityDemo
~~~

~~~text
false
true
false
false
true
~~~

This Java 17+ example uses the **instanceof Customer that** syntax, standardized in Java 16. Two **Customer** objects with the same **level** and both having **email == null** are considered equal per the class policy. **HashSet.contains(second)** works properly because **equals** and **hashCode** are compatible.

**Design warning:** in the example, fields are **final** to help guarantee immutability. If fields participating in **equals/hashCode** are mutated after the object enters a **HashSet** or serves as a **HashMap** key, lookups may fail. For identifiers that must have a value, validate them in the constructor instead of unconditionally allowing null.

**Objects.hash(email, level)** computes a combined hash of the fields. Do not confuse it with **Objects.hashCode(value)**, a helper that returns 0 if value is null or **value.hashCode()** if non-null. Both assist in implementing hashCode; the choice must stay consistent with the fields used by **equals**.

### Records in Java 17

A **record** automatically generates **equals/hashCode** based on its components:

~~~java
record Profile(String displayName, int age) {}

Profile a = new Profile(null, 20);
Profile b = new Profile(null, 20);
System.out.println(Objects.equals(a, b)); // true
~~~

This is an illustrative snippet in a Java 17-compatible context with **Objects** imported. **Record** provides component-wise comparison per Java's contract; however, for an array-typed component, do not assume the record will deeply compare array elements. You still need to design the class semantics clearly.

## 8. Practical Use Cases

### 8.1. Comparing Old/New Values to Decide Whether to Update

When both old and new states can be null and you want to detect changes:

~~~java
if (!Objects.equals(oldValue, newValue)) {
    System.out.println("Value changed");
}
~~~

Using **!Objects.equals** handles transitions **null → value**, **value → null**, or **value A → value B** consistently. Two null values are treated as unchanged.

### 8.2. Matching a Nullable Filter Parameter

~~~java
boolean matches = Objects.equals(requestedCategory, itemCategory);
~~~

This expression means **both being null also counts as a match**. If null in a filter means **"no filter"**, a different condition is needed:

~~~java
boolean matches = requestedCategory == null
        || Objects.equals(requestedCategory, itemCategory);
~~~

The two snippets above are illustrations inside a method. They represent two different business policies; choose based on the API's definition.

### 8.3. Comparing Against a Fixed Status

~~~java
boolean active = "ACTIVE".equals(status);
~~~

When **status** can be null, calling **equals** on the literal remains safe and concise. **Objects.equals(status, "ACTIVE")** is also valid, but brings no significant benefit when one side is already guaranteed non-null.

### 8.4. Two Nullable References Needing Case-Insensitive Comparison

**Objects.equals** does not perform case-insensitive comparison on its own. If an application explicitly defines an **equalsIgnoreCase** policy for two nullable Strings:

~~~java
static boolean equalsIgnoreCaseNullable(String a, String b) {
    return a == b || (a != null && a.equalsIgnoreCase(b));
}
~~~

This is an illustrative method: two nulls return true, one null returns false, and two non-null Strings are compared case-insensitively using **String.equalsIgnoreCase**. It does not normalize Unicode and does not fully address locale-based natural language comparisons. If the requirement is Vietnamese sorting/searching, separate normalization, locale, and collation rules are needed.

## 9. When Is Objects.equals Not Enough?

- **Mandatory data required:** if both being null is still an invalid state, use a presence check or **Objects.requireNonNull** before comparing.
- **Arrays:** use **Arrays** methods appropriate for the array type and desired depth of comparison.
- **Case-insensitive comparison:** use **equalsIgnoreCase** or appropriate language comparison rules; **Objects.equals** compares exact content via **equals**.
- **Unicode normalization:** two Strings that look identical on screen but differ in NFC/NFD may still fail **equals**. Normalize intentionally before comparing if business rules require it.
- **Comparing numeric data of different types:** **Integer(10)** and **Long(10L)** are not automatically coerced to the same type.
- **Business objects that do not override equals:** **Objects.equals** does not manufacture attribute-based equality; the class must define and obey the equals/hashCode contract itself.
- **Sorting:** **Objects.equals** only returns a boolean, not an ordering relation. When ordering with nulls is needed, use **Comparator.nullsFirst(...)** or **Comparator.nullsLast(...)** with an appropriate comparator.
- **Protecting secret values:** **Objects.equals** does not guarantee constant-time comparison. For secret bytes, use dedicated APIs and designs suited to the security context.

## 10. Common Pitfalls

| Mistake | Consequence | Fix |
| --- | --- | --- |
| **nullable.equals(value)** | **NullPointerException** if nullable is null | **Objects.equals(nullable, value)** or call on a non-null constant |
| Using **==** to compare String content | Compares references; result depends on whether both variables point to the same object | Use **equals** or **Objects.equals** |
| Assuming two nulls are never equal | Misinterprets API results | Remember **Objects.equals(null, null)** is true; add business conditions when needed |
| Using **Objects.equals** on two newly created arrays | May return false even when elements match | Use **Arrays.equals/deepEquals** |
| Assuming Objects.equals compares fields of any object | Two distinct objects usually return false if using default **Object.equals** | Define equals/hashCode in value classes |
| Overriding **equals** while forgetting **hashCode** | Violates contract, causing bugs in HashMap/HashSet | Override both consistently based on the compared fields |
| Treating **null** the same as **""** | Loses the distinction between absent value and empty string | Define separate input normalization rules |
| Assuming comparison ignores case/diacritics | Comparison may return false | Use explicit normalization and comparison logic per requirements |
| Putting an object with mutable equals/hashCode fields into a HashSet | Difficult to find the object again after fields change | Design immutable keys or maintain a consistent contract |

## 11. Self-Check Knowledge Quiz

1. What does **Objects.equals(null, null)** return? — **true**, because both references are null.
2. Does **Objects.equals(null, "x")** throw NullPointerException? — **No**, it returns **false**.
3. Why does **new String("x") == "x"** differ from **Objects.equals(new String("x"), "x")**? — The first expression compares two references (false), while the second uses String.equals to compare content (true).
4. Does **Objects.equals(new int[]{1, 2}, new int[]{1, 2})** return true? — **No**, the two arrays have different references; use **Arrays.equals** to compare elements.
5. When both IDs are null, **Objects.equals(idA, idB)** returns true. Should they be treated as the same account? — **Not automatically**; business logic must enforce valid identifier constraints.
6. When overriding **equals** in a class with a nullable String field, how should that field be compared? — **Objects.equals(this.field, other.field)**, while ensuring a compatible **hashCode**.
7. What approach checks whether a state has changed from null to a new value? — **!Objects.equals(oldValue, newValue)**.
8. Are two Strings with the same text but different Vietnamese diacritic encodings always equal under equals()? — **No**; if canonical equivalence is needed, normalize Unicode consistently first.

## 12. Key Takeaways

**java.util.Objects.equals(a, b)** is a concise and safe way to compare **two references that may be null**. Its core rule is **(a == b) || (a != null && a.equals(b))**.

For Strings, it compares **content** rather than relying on object identity. It still follows the **equals** implemented by the class: it does not auto-normalize text, does not ignore case, does not deep-compare arrays, and does not validate that **null** is valid in business terms.

When using it in your own classes, uphold the **equals/hashCode** contract, define what null means, and pick the comparison method that matches the actual data type.

**API Reference:** Java SE 17 — **java.util.Objects.equals(Object, Object)**, **java.lang.Object.equals(Object)**, **java.lang.String.equals(Object)**, **java.util.Arrays.equals(...)**, and **Arrays.deepEquals(...)**.
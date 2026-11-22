# Reference Identity and Value Equality with `equals()` in Java

## 1. Two Different Questions: “Same Object” and “Same Value”

When working with Java objects, we must distinguish:

- **Reference identity:** two references point to **the exact same object**. The `==` operator between compatible reference operands checks this.
- **Value or logical equality:** two objects are considered by the class to have the same meaning according to **`equals(Object)`**; they may be created by two separate `new` operations.
- **Default `Object.equals(Object)`:** only considers two references equal when they point to the same object. Value equality must come from an overridden implementation (or a type that already provides it).

A typical example:

```java
String first = new String("Java");
String second = new String("Java");

System.out.println(first == second);      // false: two objects
System.out.println(first.equals(second)); // true: same content
```

The two `String` objects differ in identity, but `String` overrides `equals` to compare content. **Not every class has the same behavior as String.**

> **Remember:** `==` between **references** asks “is it the exact same object?”. `equals()` asks “by the class's definition, are the two objects equal?”.

This lesson, part of the topic **The `Object` Class**, will help you understand the reference model, equality contracts, `hashCode`, how to override properly, corner cases of inheritance, String, arrays, records, and the behavior of hash-based collections.

## 2. Reference Diagram and Aliasing

Consider:

```java
StringBuilder a = new StringBuilder("A");
StringBuilder b = a;
StringBuilder c = new StringBuilder("A");
```

Semantic diagram:

```text
a ──────────┐
            ├─────> StringBuilder X {text: "A"}
b ──────────┘

c ────────────────> StringBuilder Y {text: "A"}
```

- `a == b` is true: the two variables hold the same reference value.
- `a == c` is false: `new` creates a different StringBuilder object.
- `a.equals(c)` is false in this example: `StringBuilder` does not define equals based on text contents, and instead uses the default equality inherited from Object.
- `b.append("B")` modifies **X**, so reading `a.toString()` also yields `"AB"`; object Y is unchanged.

The diagram is a way to visualize **objects and aliases**; it does not guarantee physical addresses, heap/stack layout, or a specific JVM optimization strategy.

### “Equal References” Does Not Mean “Same State”

Two aliases both pointing to X always see the same object, even when X is mutable and its state changes. Two objects X/Y may contain the same data at a point in time yet have their own lifecycles/identities. Therefore, you must not use an identical `toString()` or identical field values to infer that `==` is true.

## 3. First Java 17+ Example: Object, Alias, State

Create the file **`IdentityDemo.java`**:

```java
class Box {
    private int value;

    Box(int value) {
        this.value = value;
    }

    void change(int next) {
        value = next;
    }

    int value() {
        return value;
    }
}

public class IdentityDemo {
    public static void main(String[] args) {
        Box first = new Box(10);
        Box alias = first;
        Box second = new Box(10);

        System.out.println("alias=" + (first == alias));
        System.out.println("different=" + (first == second));
        System.out.println("equals=" + first.equals(second));

        alias.change(20);

        System.out.println("first=" + first.value());
        System.out.println("second=" + second.value());
    }
}
```

```bash
javac IdentityDemo.java
java IdentityDemo
```

**Standard output:**

```text
alias=true
different=false
equals=false
first=20
second=10
```

`Box` does not override `equals`, so it uses Object's identity equality. The call `alias.change(20)` changes the state of the object that `first` also points to, without changing `second`.

**Key point:** Calling `new Box(10)` twice does not create “the same object” just because the constructor receives the same argument. To treat two boxes with the same value as logically equal, you must **design an equality contract** for Box; that does not happen automatically.

## 4. The `==` Operator: Know the Types of Both Operands

`==` does not always check identity:

| Operands | Meaning of `==` |
| --- | --- |
| Two compatible reference expressions | Same reference / both null |
| Two primitive numeric values | Compares values according to numeric promotion rules |
| Two `boolean` values | Compares true/false |
| Combining a wrapper and a primitive in valid cases | Unboxing/numeric promotion may occur; no longer purely identity |

Example:

```java
int a = 3;
int b = 3;
System.out.println(a == b); // true, primitive values
```

Comparing two `String` **references**:

```java
String x = new String("A");
String y = new String("A");
System.out.println(x == y); // false
```

**You cannot override `==` in Java.** A class can override `equals`, but cannot alter `==` semantics for reference identity.

When seeing `Integer` wrappers and `==`, do not rely on the boxing cache to compare logical numbers. If one operand is primitive, Java may unbox according to the rules; if both operands are wrapper references, identity may differ. Rely on **static types and contract**, not on a test value that happens to return true.

## 5. `null`: Comparable with `==`, but Cannot Call an Instance Method

`null` is a reference value that points to no object.

```java
String first = null;
String second = null;
String third = "Java";

System.out.println(first == second); // true
System.out.println(first == third);  // false
```

However:

```java
// first.equals(second); // NullPointerException because first is null.
```

To compare logical equality when null is possible, use:

```java
java.util.Objects.equals(first, second)
```

`Objects.equals(a,b)` has null-safe semantics: both null → true; one null → false; non-null → uses the appropriate equals.

**Do not write:** `a.equals(b)` when `a` may be null without a check. Also do not confuse `x.equals(null)==false` (for non-null x, per the contract) with `null.equals(x)` — the second expression has no receiver object.

## 6. Default Implementation from `java.lang.Object`

An ordinary class that does not override `equals(Object)` inherits Object's implementation. According to its contract, default equality is based on object identity.

Example:

```java
class Item {
    private final String code;

    Item(String code) {
        this.code = code;
    }
}
```

Two `new Item("X")` instances are two separate objects; even though the code field is the same, the default `equals` **does not compare the code field**.

### Runnable Program

File **`DefaultEqualsDemo.java`**:

```java
class Item {
    private final String code;

    Item(String code) {
        this.code = code;
    }
}

public class DefaultEqualsDemo {
    public static void main(String[] args) {
        Item one = new Item("X");
        Item two = new Item("X");
        Item alias = one;

        System.out.println(one == two);
        System.out.println(one.equals(two));
        System.out.println(one.equals(alias));
    }
}
```

```bash
javac DefaultEqualsDemo.java
java DefaultEqualsDemo
```

```text
false
false
true
```

Do not say “`equals()` always compares all fields”. The **class implementation** itself determines which data constitutes the logical value. There are objects such as connections/sessions/callbacks where default identity equality is desirable.

## 7. `String`: Value Equality by Content

`String` overrides equals to compare character content. However, String literals also have an interning/constant expressions mechanism, so `==` on some literals can also legitimately be true, which **does not mean String content should be compared using `==`**.

File **`StringEqualityDemo.java`**:

```java
public class StringEqualityDemo {
    public static void main(String[] args) {
        String literal = "Java";
        String folded = "Ja" + "va";
        String allocated = new String("Java");

        System.out.println(literal == folded);
        System.out.println(literal == allocated);
        System.out.println(literal.equals(allocated));
        System.out.println(allocated.intern() == literal);
    }
}
```

```bash
javac StringEqualityDemo.java
java StringEqualityDemo
```

```text
true
false
true
true
```

Explanation:

- `"Ja" + "va"` is a constant expression; Java uses the same interned literal representation, so `literal == folded` is true.
- `new String("Java")` creates an object with a different identity from the literal.
- `equals` compares String contents, so it is true.
- `intern()` returns the canonical string reference in the pool for the same contents.

**Working rule:** Compare text using `left.equals(right)` when the receiver is guaranteed non-null; use `Objects.equals(left,right)` if both may be null. Do not write application logic that depends on whether two Strings happen to be interned.

### `StringBuilder` Is Not Like `String`

`StringBuilder` holds mutable text and does not override equals to compare text contents. Two `new StringBuilder("A")` instances that differ in identity will not be equal by content. If you truly need to compare text, you can call `a.toString().equals(b.toString())`, keeping in mind mutable state/concurrency.

## 8. When Defining `equals(Object)`, You Must Preserve an Equivalence Relation

Unlike `==`, which only compares identity, `equals` can represent domain equality. Every override must maintain **reflexivity, symmetry, transitivity, consistency when relevant state does not change**, and `x.equals(null) == false` for non-null x. The method name and signature must be exactly `public boolean equals(Object other)`; `equals(MyType)` is only an overload.

This lesson asks **when value equality is more appropriate than identity**: for example, two `Money` objects with the same amount/currency may be equal by value, whereas two customer entities with the same name are not necessarily the same customer. From that choice, you then design criteria, null/type handling, and tests.

**Self-check:** if `parent.equals(child)` is true while `child.equals(parent)` is false, then the contract's **symmetry is broken**; in that case, `HashSet`/collections cannot be relied upon for the intended equality. The inheritance example in section 16 demonstrates this bug with concrete stdout. The *equals/hashCode contract* lesson goes deeper into how to implement and thoroughly test all five conditions.

## 9. Choosing Identity Equality or Value Equality by Business Domain

Not every object must be value-equal when its fields are the same.

**Use identity when a separate instance identity/lifecycle is essential:**

- Two network connection objects with identical configuration are still two connections.
- Two independent transactions with the same total amount are not necessarily the same transaction.
- Two mutable view/controller objects with identical contents may still be different entities.

**Use value equality when specific fields are the “value” of the object:**

- Coordinates `(x,y)`.
- Normalized product code `ProductId("A1")`.
- Range `[start,end]`.
- Dates, value pairs, immutable configurations if defined by the contract.

The question to ask is: **are two separately created objects with the same business value interchangeable in comparisons, Sets, Maps, caches, or business logic?** If yes, value equality is usually the right choice.

For entities with an ID, equality may be based on the ID according to the contract. However, if the ID is generated late, mutable, or subject to ORM proxy mechanisms, it must be designed carefully. **Do not automatically** use all fields of a mutable entity for equals.

## 10. Overriding `equals(Object)` with the Correct Signature

A good value object implementation should:

1. Quickly handle `this == other` if it is the same object.
2. Safely check null/type.
3. Compare the exact fields that determine equality.
4. Have a consistent `hashCode()`.
5. Limit mutable fields participating in equality when it needs to be used as a key.
6. Consider `final class` to avoid complex hierarchy equality.

### Complete Java 17+ Example

Create **`ProductIdDemo.java`**:

```java
import java.util.Objects;

final class ProductId {
    private final String value;

    ProductId(String value) {
        this.value = Objects.requireNonNull(value, "value");
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) {
            return true;
        }
        if (!(other instanceof ProductId id)) {
            return false;
        }
        return value.equals(id.value);
    }

    @Override
    public int hashCode() {
        return value.hashCode();
    }

    @Override
    public String toString() {
        return "ProductId[" + value + "]";
    }
}

public class ProductIdDemo {
    public static void main(String[] args) {
        ProductId first = new ProductId("A1");
        ProductId second = new ProductId("A1");
        ProductId third = new ProductId("B2");

        System.out.println("same reference=" + (first == second));
        System.out.println("same value=" + first.equals(second));
        System.out.println("different=" + first.equals(third));
        System.out.println("null=" + first.equals(null));
        System.out.println("hash matches=" +
                (first.hashCode() == second.hashCode()));
        System.out.println(first);
    }
}
```

```bash
javac ProductIdDemo.java
java ProductIdDemo
```

```text
same reference=false
same value=true
different=false
null=false
hash matches=true
ProductId[A1]
```

**Why is this correct?**

- Two `new` operations create different identities, yet the String value is the same.
- `instanceof ProductId id` checks the type and creates a pattern variable (Java 17).
- `value.equals(id.value)` invokes String value equality.
- `hashCode()` uses the same `value`, so equal ProductIds have equal hashes.
- `final class` prevents subclasses from adding state that causes symmetry issues.
- `private final String value` uses an immutable String, keeping equality stable throughout the object's lifecycle.

Do not mistake `final` on a field as the sole reason for immutability: if the field points to a mutable `ArrayList`, a protective API/defensive copy is still needed.

## 11. `hashCode()` Must Be Consistent with Logical Equality

Fundamental requirement: **two objects that are `equals()` to each other must have the same `hashCode()`**. Equal hashes do not prove equality because collisions are valid. Therefore, when overriding `equals` based on value fields, override `hashCode` accordingly using those same fields.

~~~java
@Override
public int hashCode() {
    return java.util.Objects.hash(region, code);
}
~~~

This is a method fragment inside a class that has `region` and `code`; it is not a standalone program. With `HashSet` and `HashMap`, violating this requirement can cause a key that is “equal” according to the domain to fail to be looked up as expected.

This lesson treats hashing as **a practical consequence of choosing equality**. The next contract lesson analyzes collisions, consistency, inheritance, arrays/records, and hash testing. If fields participating in equality can change after insertion into a hash collection, the mutable keys lesson will separately explain retention/lookup risks.

## 12. Testing with `HashSet`: Deduplication Based on Equality

File **`HashSetEqualityDemo.java`**:

```java
import java.util.HashSet;
import java.util.Set;

final class Code {
    private final String value;

    Code(String value) {
        this.value = java.util.Objects.requireNonNull(value);
    }

    @Override
    public boolean equals(Object other) {
        return other instanceof Code code
                && value.equals(code.value);
    }

    @Override
    public int hashCode() {
        return value.hashCode();
    }
}

public class HashSetEqualityDemo {
    public static void main(String[] args) {
        Set<Code> codes = new HashSet<>();

        System.out.println(codes.add(new Code("X")));
        System.out.println(codes.add(new Code("X")));
        System.out.println(codes.add(new Code("Y")));
        System.out.println("size=" + codes.size());
        System.out.println(codes.contains(new Code("X")));
    }
}
```

```bash
javac HashSetEqualityDemo.java
java HashSetEqualityDemo
```

```text
true
false
true
size=2
true
```

The second `Code("X")` is a new object with a different reference, but it has the same equality/hash, so `HashSet.add` returns false. `contains(new Code("X"))` is still true even when looking up with a new object.

This illustrates why **value equality is not just for printing booleans**: it affects data behavior in collections.

## 13. `HashMap` Looks Up Keys Using Value Equality

File **`HashMapEqualityDemo.java`**:

```java
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;

record UserId(String value) {
    UserId {
        Objects.requireNonNull(value);
    }
}

public class HashMapEqualityDemo {
    public static void main(String[] args) {
        Map<UserId, String> users = new HashMap<>();

        UserId stored = new UserId("u-1");
        UserId lookup = new UserId("u-1");

        users.put(stored, "An");

        System.out.println(stored == lookup);
        System.out.println(stored.equals(lookup));
        System.out.println(users.get(lookup));
        System.out.println(users.containsKey(lookup));
    }
}
```

```bash
javac HashMapEqualityDemo.java
java HashMapEqualityDemo
```

```text
false
true
An
true
```

The `UserId` record in Java 17 automatically has equals/hashCode based on its components. The two UserId instances differ in identity yet share the same String value, so the Map lookup succeeds.

If `UserId` did not have value equality or used an unstable mutable key, the result could differ. **Hash-based lookup is the reason to care about hashCode alongside equals**.

## 14. `Objects.equals`: Null-Safe Comparison

File **`NullSafeEqualityDemo.java`**:

```java
import java.util.Objects;

public class NullSafeEqualityDemo {
    public static void main(String[] args) {
        String a = null;
        String b = null;
        String c = "Java";
        String d = new String("Java");

        System.out.println(Objects.equals(a, b));
        System.out.println(Objects.equals(a, c));
        System.out.println(Objects.equals(c, d));
        System.out.println(c == d);
    }
}
```

```bash
javac NullSafeEqualityDemo.java
java NullSafeEqualityDemo
```

```text
true
false
true
false
```

In simplified terms, `Objects.equals(a,b)` is equivalent to:

```java
a == b || (a != null && a.equals(b))
```

This is an **expression fragment** inside a method where `a`/`b` are already declared, not a standalone program.

`Objects.equals` handles null, and after that still depends on the class's `equals`. It does **not** automatically deep-compare arrays, automatically fix the symmetry/transitivity of custom equality, or turn mutable objects into immutable ones.

## 15. Pitfall: `equals(MyClass)` Is an Overload, Not an Override

A very common mistake:

```java
class Key {
    private final String text;

    Key(String text) {
        this.text = text;
    }

    boolean equals(Key other) {
        return other != null && text.equals(other.text);
    }
}
```

The method above has parameter `Key`, whereas `Object.equals` has parameter `Object`. This is **overloading**, not overriding.

File **`EqualsOverloadDemo.java`**:

```java
class Key {
    private final String text;

    Key(String text) {
        this.text = text;
    }

    boolean equals(Key other) {
        return other != null && text.equals(other.text);
    }
}

public class EqualsOverloadDemo {
    public static void main(String[] args) {
        Key first = new Key("A");
        Key second = new Key("A");
        Object asObject = second;

        System.out.println(first.equals(second));
        System.out.println(first.equals(asObject));
        System.out.println(((Object) first).equals(second));
    }
}
```

```bash
javac EqualsOverloadDemo.java
java EqualsOverloadDemo
```

```text
true
false
false
```

Because the overload is chosen based on the static type of the argument, the results differ: `equals(Key)` compares text, whereas the inherited `equals(Object)` compares identity.

**Fix:** write **`@Override public boolean equals(Object other)`**. The annotation helps the compiler catch if the name or parameter signature is wrong. Do not write `boolean equal(Object)` (missing `s`), `private boolean equals(Object)`, or `boolean equals(Key)` and assume you have replaced Object.equals behavior.

## 16. Inheritance Can Break the Symmetry of Equality

A superclass may define equality based on `name`, while a subclass wants to compare `name` and `level`. In that case, the two directions of `equals` risk being asymmetric.

File **`EqualitySymmetryDemo.java`** — runnable code, but intentionally demonstrates **an incorrect equality design**:

```java
class BaseValue {
    final String name;

    BaseValue(String name) {
        this.name = name;
    }

    @Override
    public boolean equals(Object other) {
        return other instanceof BaseValue base
                && name.equals(base.name);
    }

    @Override
    public int hashCode() {
        return name.hashCode();
    }
}

class DetailedValue extends BaseValue {
    final int level;

    DetailedValue(String name, int level) {
        super(name);
        this.level = level;
    }

    @Override
    public boolean equals(Object other) {
        return other instanceof DetailedValue detail
                && name.equals(detail.name)
                && level == detail.level;
    }

    @Override
    public int hashCode() {
        return 31 * super.hashCode() + level;
    }
}

public class EqualitySymmetryDemo {
    public static void main(String[] args) {
        BaseValue base = new BaseValue("A");
        DetailedValue detail = new DetailedValue("A", 2);

        System.out.println(base.equals(detail));
        System.out.println(detail.equals(base));
    }
}
```

```bash
javac EqualitySymmetryDemo.java
java EqualitySymmetryDemo
```

```text
true
false
```

`base.equals(detail)` is true while `detail.equals(base)` is false → **violates symmetry**. A class hierarchy can also break hashCode consistency when the fields used to compute the hash differ.

**Simple way to avoid this for value objects:** use a `final class` or record if inheritance is not needed. With an open hierarchy, you must intentionally design equality across subclasses and thoroughly test symmetry/transitivity; do not just add `instanceof` arbitrarily.

## 17. `getClass()` or `instanceof` in `equals`?

Two kinds of type checks:

**Exact runtime class:**

```java
if (other == null || getClass() != other.getClass()) {
    return false;
}
```

**Accepting subtypes that satisfy instanceof:**

```java
if (!(other instanceof ProductId id)) {
    return false;
}
```

The choice depends on the contract:

- A `getClass` check only accepts the exact runtime class, which can help prevent asymmetric base-subclass equality, though it sometimes does not fit proxies/domains.
- `instanceof` is convenient when the type is `final`, since there are no subclasses adding fields that cause ambiguity.
- With open inheritance, subclass equality must coordinate across the entire hierarchy to uphold the contract.
- With persistence frameworks that generate proxies, you need to understand runtime class/proxy behavior before setting a rigid equality rule.

**There is no single right formula for every class.** Decide whether equality is permitted between subtype instances and whether subtype state participates in the identity/value definition.

## 18. Records in Java 17 Automatically Define Value Equality

File **`RecordEqualityDemo.java`**:

```java
record Point(int x, int y) {
}

public class RecordEqualityDemo {
    public static void main(String[] args) {
        Point first = new Point(2, 3);
        Point second = new Point(2, 3);
        Point other = new Point(3, 2);

        System.out.println(first == second);
        System.out.println(first.equals(second));
        System.out.println(first.equals(other));
        System.out.println(
                first.hashCode() == second.hashCode());
        System.out.println(first);
    }
}
```

```bash
javac RecordEqualityDemo.java
java RecordEqualityDemo
```

```text
false
true
false
true
Point[x=2, y=3]
```

Records have equals/hashCode/toString generated according to component semantics. With primitive components `x`, `y`, this is straightforward value equality. However, **a record does not automatically deep-copy or deep-freeze mutable component objects**, especially arrays.

## 19. A Record with an Array Component Can Still Use Identity for the Array

File **`RecordWithArrayDemo.java`**:

```java
record Numbers(int[] values) {
}

public class RecordWithArrayDemo {
    public static void main(String[] args) {
        int[] shared = {1, 2};

        Numbers a = new Numbers(shared);
        Numbers b = new Numbers(new int[] {1, 2});
        Numbers c = new Numbers(shared);

        System.out.println(a.equals(b));
        System.out.println(a.equals(c));
        System.out.println(a.values() == c.values());
    }
}
```

```bash
javac RecordWithArrayDemo.java
java RecordWithArrayDemo
```

```text
false
true
true
```

Record equality for an array component does not automatically use `Arrays.equals`. Different array references with identical contents → false; the same source array reference → true.

If comparing array contents is required, you must define consistent custom equals/hashCode (along with a defensive-copy contract) or store the data using an appropriate immutable value representation. The default record accessor returning an array reference can also expose mutable contents.

## 20. Arrays: `array.equals` Compares Identity, `Arrays.equals` Compares Contents

File **`ArrayEqualityDemo.java`**:

```java
import java.util.Arrays;

public class ArrayEqualityDemo {
    public static void main(String[] args) {
        int[] first = {1, 2, 3};
        int[] second = {1, 2, 3};
        int[] alias = first;

        System.out.println(first == second);
        System.out.println(first.equals(second));
        System.out.println(first == alias);
        System.out.println(Arrays.equals(first, second));
    }
}
```

```bash
javac ArrayEqualityDemo.java
java ArrayEqualityDemo
```

```text
false
false
true
true
```

Java arrays are objects, but they do not override equals by content. `Arrays.equals(int[],int[])` has a contract to compare corresponding slots.

For nested arrays, compare multi-level contents with `Arrays.deepEquals` when appropriate.

### Nested Arrays

File **`DeepArrayEqualityDemo.java`**:

```java
import java.util.Arrays;

public class DeepArrayEqualityDemo {
    public static void main(String[] args) {
        int[][] a = {{1, 2}, {3}};
        int[][] b = {{1, 2}, {3}};

        System.out.println(a == b);
        System.out.println(Arrays.equals(a, b));
        System.out.println(Arrays.deepEquals(a, b));
        System.out.println(Arrays.deepToString(a));
    }
}
```

```bash
javac DeepArrayEqualityDemo.java
java DeepArrayEqualityDemo
```

```text
false
false
true
[[1, 2], [3]]
```

`Arrays.equals(a,b)` here compares references to the inner arrays (one level). `Arrays.deepEquals` deeply compares nested array contents as specified by the API. Do not confuse it with comparing arbitrary object graphs with circular references; deepEquals has conditions/limitations with array cycles.

## 21. Collections: List/Set/Map Have Logical Equality

Many collections in Java have specific contracts:

- **`List.equals`**: same number of elements and corresponding elements are equal **in order**.
- **`Set.equals`**: same set of elements according to equality; iteration order is not decisive.
- **`Map.equals`**: same key-value mappings; iteration order is not an equality requirement.

File **`CollectionEqualityDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Set;

public class CollectionEqualityDemo {
    public static void main(String[] args) {
        List<String> first =
                new ArrayList<>(List.of("A", "B"));
        List<String> second =
                new ArrayList<>(List.of(new String("A"), "B"));
        List<String> reversed = List.of("B", "A");

        System.out.println(first == second);
        System.out.println(first.equals(second));
        System.out.println(first.equals(reversed));

        System.out.println(Set.of("A", "B")
                .equals(Set.of("B", "A")));
        System.out.println(Map.of("A", 1, "B", 2)
                .equals(Map.of("B", 2, "A", 1)));
    }
}
```

```bash
javac CollectionEqualityDemo.java
java CollectionEqualityDemo
```

```text
false
true
false
true
true
```

In this example, the two `new ArrayList<>(...)` instances are two separate objects, so `first==second` is definitely false. The corresponding List contents are equal, so `first.equals(second)` is true.

**Avoid an unguaranteed check:** `List.of(...) == List.of(...)` is not a reliable identity test, because unmodifiable value-based factory results carry no promise of stable reference identity. Only use the `List.equals` contract when you want to compare contents.

## 22. `BigDecimal.equals` Differs from `compareTo` on Scale

An important exception: `BigDecimal.equals` does not only compare numeric magnitude, it also requires the same **scale**; `compareTo` compares numerical order.

File **`BigDecimalEqualityDemo.java`**:

```java
import java.math.BigDecimal;

public class BigDecimalEqualityDemo {
    public static void main(String[] args) {
        BigDecimal a = new BigDecimal("2.0");
        BigDecimal b = new BigDecimal("2.00");

        System.out.println(a == b);
        System.out.println(a.equals(b));
        System.out.println(a.compareTo(b) == 0);
        System.out.println(a.scale());
        System.out.println(b.scale());
    }
}
```

```bash
javac BigDecimalEqualityDemo.java
java BigDecimalEqualityDemo
```

```text
false
false
true
1
2
```

The numeric values are equal, yet the scales differ. `HashSet<BigDecimal>` uses equals/hashCode; `TreeSet<BigDecimal>` uses order/compareTo. If ordering is inconsistent with equals, the two structures may yield different results for what they consider “duplicate” according to their contracts.

**Lesson:** equality depends on the **type contract**. Do not assume that every class must treat two representations of the same number as equal.

## 23. When `==` Is Right: null, Alias, and Enum

`==` is appropriate when **identity** is required:

- `object == null`.
- Whether two references point to the same component instance.
- Checking aliases in an object graph.
- Comparing enum constants.
- `this == other` in an equals implementation.

File **`EnumIdentityDemo.java`**:

```java
enum Status {
    NEW, DONE
}

public class EnumIdentityDemo {
    public static void main(String[] args) {
        Status first = Status.NEW;
        Status second = Status.NEW;
        Status third = Status.DONE;

        System.out.println(first == second);
        System.out.println(first.equals(second));
        System.out.println(first == third);
    }
}
```

```bash
javac EnumIdentityDemo.java
java EnumIdentityDemo
```

```text
true
true
false
```

Enum constants have identity per the type's constants and do not allow callers to arbitrarily create `new Status()`. `==` is the appropriate and null-safe way to compare enum values; `equals` also gives the same result for matching constants, but requires a non-null receiver.

## 24. `IdentityHashMap`: Key Equality by Reference Identity

`HashMap` uses the logical equality/hashCode of keys. However, Java also has `IdentityHashMap` to intentionally use identity semantics for keys.

File **`IdentityHashMapDemo.java`**:

```java
import java.util.HashMap;
import java.util.IdentityHashMap;
import java.util.Map;

public class IdentityHashMapDemo {
    public static void main(String[] args) {
        String a = new String("A");
        String b = new String("A");

        Map<String, Integer> values = new HashMap<>();
        values.put(a, 1);
        values.put(b, 2);

        Map<String, Integer> identities = new IdentityHashMap<>();
        identities.put(a, 1);
        identities.put(b, 2);

        System.out.println(a == b);
        System.out.println(a.equals(b));
        System.out.println("value keys=" + values.size());
        System.out.println("identity keys=" + identities.size());
    }
}
```

```bash
javac IdentityHashMapDemo.java
java IdentityHashMapDemo
```

```text
false
true
value keys=1
identity keys=2
```

`HashMap` sees that the String contents are equal, so the two puts have the same logical key, giving size=1. `IdentityHashMap` treats the two `new String("A")` instances as two separate keys, giving size=2.

This is a **map with special behavior**, suitable for certain algorithms based on object identity; it should not be used in place of a default HashMap just because the two classes have similar names.

## 25. `System.identityHashCode` Is Not a Unique Object ID

`System.identityHashCode(x)` obtains a hash based on Object's identity semantics even when `x` overrides hashCode. However:

- Hash values **can collide** and are not guaranteed to be unique.
- It is not necessarily a memory address.
- Do not use it as a business key or long-lived identifier.
- It does not imply “if two objects have the same hash, they are the same object”.
- `System.identityHashCode(null)` returns 0 per the API.

Example expression:

```java
int identityHash = System.identityHashCode(object);
```

This is a **code snippet** that requires the `object` variable; there is no fixed stdout for the identityHash value. If you need to know whether it is the same instance, `a==b` is the direct check. If you need a business identifier, model an ID field with a clear contract.

## 26. Mutable Key: Warning When Using Logical Equality in `HashMap`

A class may implement `equals/hashCode` correctly according to its **current state**, yet become an unstable key if a field used for hashing is modified **after insertion**.

~~~java
record StableKey(String code) {
    StableKey {
        java.util.Objects.requireNonNull(code);
    }
}
~~~

This is a valid record declaration. Since the `code` component is an immutable String and its reference cannot be changed in the record, the key has stable equality/hash for the scope of this example. By contrast, a record containing a mutable List/array can still hold state that can change; `record` does not automatically guarantee deep immutability.

**Usage rule:** prefer immutable value keys, and do not mutate equality fields on objects currently stored in a `HashMap`/`HashSet`. The *consequences of mutating equals/hashCode fields* lesson provides a program that investigates the state where a key still exists in the collection yet lookup is not guaranteed.

## 27. Equality with Multiple Fields: Participating Data Must Be Consistent

If a class represents a product code within a region, it may need both `region` and `code`.

File **`CompositeKeyDemo.java`**:

```java
import java.util.Objects;

final class CatalogKey {
    private final String region;
    private final String code;

    CatalogKey(String region, String code) {
        this.region = Objects.requireNonNull(region);
        this.code = Objects.requireNonNull(code);
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) {
            return true;
        }
        if (!(other instanceof CatalogKey key)) {
            return false;
        }
        return region.equals(key.region)
                && code.equals(key.code);
    }

    @Override
    public int hashCode() {
        return Objects.hash(region, code);
    }
}

public class CompositeKeyDemo {
    public static void main(String[] args) {
        CatalogKey a = new CatalogKey("VN", "P1");
        CatalogKey b = new CatalogKey("VN", "P1");
        CatalogKey c = new CatalogKey("US", "P1");

        System.out.println(a.equals(b));
        System.out.println(a.equals(c));
        System.out.println(a.hashCode() == b.hashCode());
    }
}
```

```bash
javac CompositeKeyDemo.java
java CompositeKeyDemo
```

```text
true
false
true
```

Two keys are equal when **both region and code are equal**. The hash is computed from the same fields. Do not add a field to equals and forget hashCode; likewise, do not change the equality semantics of a public value class without considering dependent data structures, caches, or clients.

For a hot path, `Objects.hash` can incur varargs overhead; you can use a direct hashing formula if profiling proves it necessary, but a correct contract matters more than premature optimization.

## 28. Testing equals with Standard Scenarios

A test suite should include:

1. **Self:** `x.equals(x)`.
2. **Equal twin:** two instances with different identities, same business value.
3. **Different:** at least one field participating in equality differs.
4. **Null:** `x.equals(null)` returns false.
5. **Unrelated type:** `x.equals("text")` returns false.
6. **Symmetry:** both directions `x.equals(y)` and `y.equals(x)` yield the same result.
7. **Transitivity:** three objects pairwise equal according to the contract.
8. **Consistency:** repeated calls when equality state has not changed.
9. **hashCode:** equal objects have equal hashes.
10. **Collections:** set dedup and map lookup work as defined.

File **`EqualsSelfTest.java`**:

```java
import java.util.HashSet;
import java.util.Set;

record Point(int x, int y) {
}

public class EqualsSelfTest {
    static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    public static void main(String[] args) {
        Point a = new Point(2, 3);
        Point b = new Point(2, 3);
        Point c = new Point(2, 3);
        Point different = new Point(3, 2);

        check(a.equals(a), "reflexive");
        check(a.equals(b) && b.equals(a), "symmetric");
        check(a.equals(b) && b.equals(c) && a.equals(c),
                "transitive");
        check(!a.equals(different), "different");
        check(!a.equals(null), "null");
        check(!a.equals("text"), "unrelated type");
        check(a.hashCode() == b.hashCode(), "hash code");

        Set<Point> points = new HashSet<>();
        points.add(a);
        points.add(b);
        check(points.size() == 1, "set dedup");

        System.out.println("equals checks passed");
    }
}
```

```bash
javac EqualsSelfTest.java
java EqualsSelfTest
```

```text
equals checks passed
```

This is a self-test using main, not JUnit; it **does not prove** that every case is correct. For inheritance or complex custom equality, consider property-based tests across many inputs and multiple subtype combinations.

## 29. Some Advanced Corner Cases of Java Equality

### Comparing Floating-Point Numbers

`Double.equals` has specific rules for `NaN` and the sign of zero that do not entirely match primitive `double ==`. When using floating-point numbers as business values, check cases involving `NaN`, `+0.0`, `-0.0`, and numerical inaccuracy.

**Do not** use the relation “two numbers differing by less than epsilon” as a regular `equals` if it breaks transitivity. Use a separate method such as `approximatelyEqual(a,b,tolerance)`.

### Comparing `BigDecimal` by Numeric Value

If the goal is “2.0 and 2.00 have the same magnitude”, `compareTo==0` may be suitable instead of `equals`. However, in that case you need to design Set/Map keys properly: you cannot simply alter BigDecimal's hashCode semantics from the outside.

### Getters and Mutable State

If equality is computed from a mutable list or a changing timestamp, an object may transition from equal to unequal over time. By contract, consistency only applies when the relevant information does not change; however, such changes are still dangerous for caches/hash sets.

### Inheritance

Do not arbitrarily choose `instanceof` or `getClass` without considering base/subclass equality. You need symmetry, transitivity, the same hash scope, and stable behavior for clients.

### `Objects.deepEquals`

`Objects.deepEquals(a,b)` uses array-aware semantics when both arguments are arrays, but **it does not automatically make every object graph deep value-equal**. For complex nested structures or cyclic objects, clearly define the domain's logical equality.

## 30. Common Mistakes Table

| Mistake | Why Is It Wrong? | Correct Approach |
| --- | --- | --- |
| `string1 == string2` to compare content | Identity differs even with identical text | `equals`/`Objects.equals` |
| Thinking `Object.equals` compares fields | Default is based on identity | Override or use a value type |
| Writing `equals(MyType)` | Overloads instead of overriding | `@Override equals(Object)` |
| Writing `equal(Object)` | Wrong name | `equals(Object)` |
| `private boolean equals(Object)` | Cannot reduce public visibility of Object.equals | `public` |
| Forgetting `hashCode` when overriding equals | Can break hash-based collections | Override consistently |
| `equals(null)` throws NPE | Violates the contract | Check null/type first |
| Adding subclass fields in equals without considering superclass | Breaks symmetry/transitivity | Design the hierarchy or use a final value class |
| Using mutable fields as a key hash | Hash may change after put | Immutable key |
| Using raw hashCode as a unique ID | Collisions can occur | Dedicated business ID |
| Thinking same hash means equals | Hash collisions are valid | Check equals |
| Calling `null.equals(x)` | Null receiver | `Objects.equals` |
| Using `array.equals` to compare elements | Arrays default to identity | `Arrays.equals/deepEquals` |
| Thinking record array components compare deeply | Does not automatically deep-compare | Custom equality/immutable components |
| Using `List.of(...) == List.of(...)` as a contract | Identity is not guaranteed | List.equals |
| Confusing List and Set equality | List cares about order, Set does not | Choose the right contract |
| Confusing `BigDecimal.equals` with compareTo | Scale affects equals | Choose numeric value or representation semantics |
| Using `==` for wrapper numbers without checking types | Boxing/unboxing/identity differ | Type-correct value comparison |
| Using `IdentityHashMap` instead of HashMap everywhere | Unintentionally changes key semantics | Use only when identity is needed |
| Assuming `System.identityHashCode` is a RAM address | Not guaranteed | Do not infer addresses from hashes |
| Using non-transitive near-equality in equals | Breaks the contract | Separate method for tolerance |
| Thinking a `final` field guarantees deep immutability | Final reference but mutable object | Defensive copy/immutable component |
| Assuming `equals` is always symmetric even with a wrong implementation | Can be coded incorrectly | Test both directions thoroughly |

## 31. Comprehensive Practice: Entity Identity and Value Key

Create **`IdentityValueTraceDemo.java`**:

```java
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;

record BookId(String code) {
    BookId {
        Objects.requireNonNull(code);
    }
}

final class Book {
    private final BookId id;
    private String title;

    Book(BookId id, String title) {
        this.id = Objects.requireNonNull(id);
        this.title = title;
    }

    BookId id() {
        return id;
    }

    String title() {
        return title;
    }

    void rename(String newTitle) {
        title = newTitle;
    }
}

public class IdentityValueTraceDemo {
    public static void main(String[] args) {
        BookId id1 = new BookId("B1");
        BookId id2 = new BookId("B1");

        Book first = new Book(id1, "Java");
        Book second = new Book(id2, "Java");
        Book alias = first;

        System.out.println("id identity=" + (id1 == id2));
        System.out.println("id value=" + id1.equals(id2));
        System.out.println("book identity=" + (first == second));
        System.out.println("book equals=" + first.equals(second));

        alias.rename("Java Core");
        System.out.println("first title=" + first.title());
        System.out.println("second title=" + second.title());

        Map<BookId, String> labels = new HashMap<>();
        labels.put(first.id(), "entry");
        System.out.println("lookup=" + labels.get(second.id()));
    }
}
```

```bash
javac IdentityValueTraceDemo.java
java IdentityValueTraceDemo
```

```text
id identity=false
id value=true
book identity=false
book equals=false
first title=Java Core
second title=Java
lookup=entry
```

### Trace

1. `id1` and `id2` are two different record instances, yet their logical value is the same.
2. `first` and `second` are two Book objects; Book does not override equals, so it uses Object's identity equality.
3. `alias=first` creates a reference alias; `alias.rename` mutates the first Book, not the second Book.
4. HashMap stores key `id1`, yet looking up with `id2` still works, because record value equality and hashCode match.
5. A business domain can perfectly well use **identity equality for objects with their own lifecycle** and **value equality for IDs**; there is no need to force every class to compare fields identically.

## 32. Self-Check Questions

**1.** If two references point to the same object, what does `==` return?  
**Answer:** True. According to a proper equals contract, `a.equals(b)` is also true if the receiver is non-null.

**2.** If two objects are different but have identical fields, is `==` true?  
**Answer:** No. `equals` depends on the implementation.

**3.** What equality does a class have if it does not override equals?  
**Answer:** Default Object identity equality.

**4.** For two independent `new String("A")` objects, how do you compare their content?  
**Answer:** `String.equals`, or `Objects.equals` if nulls are possible.

**5.** Does `a == null` throw an NPE?  
**Answer:** No. `a.equals(...)` can throw an NPE if a is null.

**6.** What is the exact signature to override?  
**Answer:** `public boolean equals(Object other)`, and `@Override` should be used.

**7.** What is wrong with `equals(MyType)` if you intend to override?  
**Answer:** It overloads; the inherited equals(Object) still exists.

**8.** How must the hashCodes of two equal objects relate?  
**Answer:** They must be equal.

**9.** Do two equal hashCodes prove that equals is true?  
**Answer:** No, collisions are valid.

**10.** Can a `final` class be used to reduce equality inheritance risks?  
**Answer:** Yes, especially with value objects.

**11.** Does `record Point(int x,int y)` have equals?  
**Answer:** Yes, automatically generated from its components.

**12.** Does a record with an array component automatically compare elements deeply?  
**Answer:** No; arrays normally use identity equality.

**13.** How do `Arrays.equals` and `Arrays.deepEquals` differ?  
**Answer:** One compares elements at a single level, while deepEquals inspects nested arrays according to its contract.

**14.** Can `HashMap.get(new EqualKey(...))` find a key from a different instance?  
**Answer:** Yes, if equals/hashCode are valid and the key state is stable.

**15.** How does `IdentityHashMap` differ from `HashMap`?  
**Answer:** It compares key reference identity instead of standard logical equality.

**16.** `BigDecimal("2.0").equals(BigDecimal("2.00"))`?  
**Answer:** False because the scales differ, though compareTo can be 0.

**17.** How should `enum` values be compared?  
**Answer:** `==` is appropriate for constants.

**18.** If a key is mutated after `put`, what is the risk?  
**Answer:** Unstable hash/equals, making lookup unreliable.

**19.** What properties must `equals` satisfy?  
**Answer:** Reflexive, symmetric, transitive, consistent; comparison with null must be false.

**20.** How can `equals` in a superclass and subclass differ?  
**Answer:** It can cause symmetry/transitivity conflicts when the subclass adds state; the entire hierarchy must be designed together.

## 33. Review Checklist Before Publishing an Equality API

- [ ] Have you decided whether the class needs reference identity or value equality according to the domain?
- [ ] Is the set of fields forming the logical value clearly described?
- [ ] If overridden, is it the correct `public boolean equals(Object)` with `@Override`?
- [ ] Does `equals(null)` return false without any null dereference?
- [ ] Is `equals` reflexive, symmetric, transitive, and consistent?
- [ ] Does `hashCode` use the same set of data that determines equality?
- [ ] Do two equal values have equal hashes?
- [ ] Are any mutable fields participating in equality when the object is used as a key/set element?
- [ ] If inheritance is present, have both base→subclass and subclass→base been tested?
- [ ] Should a `final` value class or record be used to reduce hierarchy issues?
- [ ] If using arrays, have `Arrays.equals`/`deepEquals` and corresponding hashing been chosen?
- [ ] If using a record with mutable components, are aliases/copy policies safeguarded?
- [ ] Have you avoided `==` for comparing String/List contents?
- [ ] Have you used null-safe `Objects.equals` when the receiver may be null?
- [ ] Have you considered BigDecimal scale and floating-point corner cases?
- [ ] Are there unit/self-tests for equal twin, different value, null, and unrelated type?
- [ ] Have you tested `HashSet` dedup and `HashMap` lookup with a different yet equal key object?
- [ ] Have you avoided using raw identityHashCode as a unique ID?
- [ ] Have you avoided writing tests that rely on the reference identity of value-based factory outputs?
- [ ] Do the Java 17+ examples have the correct file/public class and stdout that does not depend on raw hashes or collection iteration order?

---

**Remember:** `==` between references answers **“do they point to the same object?”**; `equals(Object)` answers **“how does this class define two objects as equal?”**. `Object.equals` defaults to identity; `String`, records, and collections have their own value equality contracts. When defining equality yourself, you must **override with the exact signature**, follow the **reflexive, symmetric, transitive, consistent, and null rules**, and provide a **consistent `hashCode`**. Be careful with **inheritance, arrays, mutable keys, and null**. Choose equality according to business meaning and preserve that contract throughout the objects' lifecycle.

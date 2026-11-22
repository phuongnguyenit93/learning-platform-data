# Record `equals()`: Same Record Class and Equal Corresponding Components

## 1. Records and Value-Based Equality

`record` is a kind of class in Java for declaring **data components (record components)** as the primary state of an object. With Java 17:

```java
record Point(int x, int y) {}
```

This is a valid type declaration, without a `main` method to run standalone. The compiler automatically generates the canonical constructor, `x()`/`y()` accessors, and the three methods `equals(Object)`, `hashCode()`, and `toString()` if the programmer does not declare them explicitly.

For **compiler-generated `equals(Object)`**, the rule is:

> Two records are equal when they belong to the **exact same record class** and **every pair of corresponding components is equal**, according to the comparison semantics of the component's type.

For example, `new Point(2, 3).equals(new Point(2, 3))` returns `true` even though two new objects are created. `new Point(2, 3).equals(new Point(2, 4))` returns `false` because the `y` component differs.

This differs from `==` on two references: `==` asks whether they point to **the exact same object**. A record is suitable as a value-carrying type, such as coordinates, composite date-time fields, computation outputs, and data keys; however, components must be designed so that *all components* truly belong to the logical value's meaning.

Distinguish **auto-generated behavior** from **customly overriding `equals`/`hashCode`**. Java allows writing these two methods in a record. When doing so, the programmer is responsible for the equality contract and may choose rules different from the default (see section 8). Statements about "same record type and all components equal" in this lesson apply directly to **the auto-generated methods**.

## 2. First Condition: Exact Same Record Class

Two records with identical component names, types, and data are still two different types if they are declared as two separate classes:

```java
record Point(int x, int y) {}
record Coordinate(int x, int y) {}

Point p = new Point(2, 3);
Coordinate c = new Coordinate(2, 3);

System.out.println(p.equals(new Point(2, 3))); // true
System.out.println(p.equals(c));               // false
```

This is an illustrative snippet; the complete program is in section 5. `Point` and `Coordinate` both have two identical `int`s, yet are **two different record classes**. Auto-generated equality does not perform cross-class structural comparison (structural equality). Nor are two records of different types automatically equal just because `toString()` looks similar or `hashCode()` collides.

Some consequences:

- Two `Point` objects with different references but the same `x` and `y` can be equal; `p1 == p2` is not how to compare values.
- `Point` is not automatically equal to `Coordinate` even when they share the same data and component names.
- A variable of type `Object` or an interface holding a `Point` instance still uses `Point.equals` at runtime.
- `p.equals(null)` is `false`. Conversely, if **the variable `p` itself is `null`**, `p.equals(...)` will throw `NullPointerException`; you can use `Objects.equals(p, q)` when either reference might be null.

Every record is an **implicitly `final`** class and directly extends `java.lang.Record`. Therefore, no subclass of `Point` is permitted to add components and override the equality provided by `Point`. This is an important difference from a regular class hierarchy, where a subclass easily breaks the symmetry of `equals` when adding conditions.

## 3. Second Condition: Every Corresponding Component Must Be Equal

After determining that two objects belong to the same record class, the auto-generated `equals` evaluates each **corresponding pair of components in declaration order**. The semantics depend on the type of that component:

| Component Type | Relevant Equality Rule | Example |
| --- | --- | --- |
| `int`, `long`, `boolean`, `char`, and non-floating-point primitives | Compares corresponding primitive values | `Point(2,3)` equals `Point(2,3)` |
| `float` and `double` | Semantics like `Float.compare`/`Double.compare` (or wrapper equality), with special rules for NaN and signed zero | `NaN` equals `NaN`; `+0.0` differs from `-0.0` |
| `String` | Based on `String.equals`, compares character contents | Two strings with different references and identical contents are still equal |
| Other reference types | Compares using `Objects.equals`, calling the value's `equals` when non-null | Nested records, `List`, other objects |
| Arrays such as `int[]` | `equals` inherited from `Object`: compares array identity | Two separate arrays with the same elements are not automatically equal |
| `List` | Follows the `List.equals` contract of the component object | Two lists with the same elements in order can be equal |

**There is no default mechanism to "automatically deep-compare everything"**. A record uses the way the **component type** defines equality. If even a single component differs, the two records are not equal.

Example with reference components:

```java
record Label(String text) {}

boolean a = new Label(new String("core"))
        .equals(new Label(new String("core"))); // true
boolean b = new Label(null).equals(new Label(null)); // true
boolean c = new Label(null).equals(new Label("core")); // false
```

This is an illustrative snippet. Two `String`s have the same content so `String.equals` returns true; two `null` components are also equal when compared via `Objects.equals`. You should not say that `record` relies on the identity of every field: identity is only the rule for **component types** that do not override equality.

### Why Do `float` and `double` Need Attention?

Primitive `double` has special `==` operator rules: `Double.NaN == Double.NaN` is `false`, while `+0.0 == -0.0` is `true`. However, a record's auto-generated `equals` uses comparison semantics that preserve reflexivity and hash compatibility:

- `new Measurement(Double.NaN).equals(new Measurement(Double.NaN))` is `true`.
- `new Measurement(+0.0).equals(new Measurement(-0.0))` is `false`.
- Different NaN bit representations are grouped into the same equivalence class when using `Double.compare`/`Double.equals` semantics.

Therefore, **you cannot assume** a record uses plain primitive `==` for every component. If manually rewriting `equals` for a record containing floating-point numbers, be sure to specifically test NaN, signed zeros, and `hashCode`.

### Record Components and Business Identity Meaning

`record Product(String sku, String displayName) {}` compares both `sku` **and** `displayName`. If only `sku` identifies a product, a change in the display name will cause two `Product`s to differ under default equality. During design, decide whether this record represents a **full snapshot** or an **identifier**, avoiding accidentally using a snapshot record as a key when only an ID is needed.

## 4. Arrays and Mutable Data: Limitations of Records

### Array Components

```java
record NumberBox(int[] numbers) {}

NumberBox a = new NumberBox(new int[] {1, 2});
NumberBox b = new NumberBox(new int[] {1, 2});
System.out.println(a.equals(b)); // false
```

The two arrays have equal contents but are two different **array objects**. Comparing `NumberBox` by default uses `int[]` equality, meaning by array identity. If you want to compare array contents, that must be designed explicitly, such as using `Arrays.equals` in a custom `equals`/`hashCode` pair or switching to an immutable collection component with appropriate semantics.

If two records are created with **the same array reference**, they can be equal. This only confirms the same array object, not element-by-element comparison.

### `final` Does Not Mean Deep Immutability

A record holds `private final` component fields so the reference cannot be reassigned after creation. However, a reference component can still point to a mutable object:

```java
record Permissions(java.util.List<String> roles) {}

java.util.List<String> mutable = new java.util.ArrayList<>();
mutable.add("READER");
Permissions p = new Permissions(mutable);

mutable.add("EDITOR"); // The List contents inside p have changed.
```

This is an illustrative code snippet. `List.equals` and `List.hashCode` are based on elements, so when the list changes, `p.equals(...)` and `p.hashCode()` can also change. That is dangerous if `p` is already a key in a `HashMap` or an element of a `HashSet`.

The solution for `List<String>` is to copy and retain a list that cannot be modified from outside:

```java
record Permissions(java.util.List<String> roles) {
    Permissions {
        roles = java.util.List.copyOf(roles);
    }
}
```

This is a valid Java 17 record using a compact constructor. `List.copyOf` creates a snapshot that cannot be modified through normal APIs and rejects null elements; with immutable `String`s, keeping the key stable is simpler. With a list of mutable objects, an unmodifiable list **does not automatically make elements immutable**.

With arrays, cloning only in the constructor while the accessor still publicly exposes the internal array still leaves a risk of mutation via the accessor. Consider defensive copying on both input/output and purposefully defining equality/hashing.

## 5. Compilable and Runnable Java 17+ Example

Create the file `RecordEqualityDemo.java`:

```java
import java.util.Arrays;
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;

public class RecordEqualityDemo {
    record Point(int x, int y) {}
    record Coordinate(int x, int y) {}
    record Label(String text) {}
    record NumberBox(int[] numbers) {}
    record Measurement(double value) {}

    public static void main(String[] args) {
        Point p1 = new Point(2, 3);
        Point p2 = new Point(2, 3);
        Point p3 = new Point(2, 4);
        Coordinate c = new Coordinate(2, 3);

        System.out.println("same reference: " + (p1 == p2));
        System.out.println("same record values: " + p1.equals(p2));
        System.out.println("different component: " + p1.equals(p3));
        System.out.println("different record class: " + p1.equals(c));
        System.out.println("equal hash: " + (p1.hashCode() == p2.hashCode()));

        Set<Point> points = new HashSet<>();
        points.add(p1);
        points.add(p2);
        System.out.println("set size: " + points.size());

        Map<Point, String> results = new HashMap<>();
        results.put(p1, "ready");
        System.out.println("map lookup: " + results.get(new Point(2, 3)));

        Label a = new Label(new String("core"));
        Label b = new Label(new String("core"));
        System.out.println("string component: " + a.equals(b));
        System.out.println("two null components: "
                + new Label(null).equals(new Label(null)));

        int[] arrayA = {1, 2};
        int[] arrayB = {1, 2};
        System.out.println("array contents: " + Arrays.equals(arrayA, arrayB));
        System.out.println("record with arrays: "
                + new NumberBox(arrayA).equals(new NumberBox(arrayB)));
        System.out.println("record shared array: "
                + new NumberBox(arrayA).equals(new NumberBox(arrayA)));

        System.out.println("NaN records equal: "
                + new Measurement(Double.NaN)
                        .equals(new Measurement(Double.NaN)));
        System.out.println("signed zero records equal: "
                + new Measurement(+0.0)
                        .equals(new Measurement(-0.0)));
    }
}
```

Compile/run:

```bash
javac --release 17 RecordEqualityDemo.java
java RecordEqualityDemo
```

Exact stdout:

```text
same reference: false
same record values: true
different component: false
different record class: false
equal hash: true
set size: 1
map lookup: ready
string component: true
two null components: true
array contents: true
record with arrays: false
record shared array: true
NaN records equal: true
signed zero records equal: false
```

Explanation based on the output:

1. `p1` and `p2` are two distinct objects so `== false`, yet belong to the same record class with the same `x`/`y` so `equals true`.
2. `p3` differs in `y`; `Coordinate` differs in runtime type. Neither equals `p1`.
3. Two equal `Point`s have the same hash. `HashSet` keeps only one logical value; `HashMap` finds the inserted entry using a new `Point` object with the same data.
4. `String` components compare by contents; two `null` components are also equal. Two arrays have identical elements per `Arrays.equals`, yet two `NumberBox` instances holding different array references are unequal; if they share the same array, they are equal.
5. The floating-point record treats NaN as equal to NaN, yet distinguishes `+0.0` and `-0.0` per wrapper semantics, differing from intuition built on primitive `==`.

## 6. `hashCode()` and Collection Behavior

In addition to `equals`, Java generates `hashCode()` corresponding to the components. The required invariant is:

```text
a.equals(b) == true  =>  a.hashCode() == b.hashCode()
```

This is an expression of the contract. The converse is **false**: different values may have the same hash (collisions). The specific numeric value of a record's hash code is not something to rely on when designing application contracts, because how components are combined is not promised as a fixed public formula across all JDK implementations.

Records with stable components make very convenient keys:

```java
record Key(String code, int version) {}

java.util.Map<Key, String> map = new java.util.HashMap<>();
map.put(new Key("ORD-7", 2), "done");
String result = map.get(new Key("ORD-7", 2)); // "done"
```

This is an illustrative snippet; the same key reference is not required because `equals` uses values. However, a record with a `List` or mutable object participating in `equals`/`hashCode` can change its hash when its contents change, making key lookup unreliable.

Do not confuse this with ordered collections: `TreeMap`/`TreeSet` rely on `Comparable`/`Comparator`. `record Point(int x,int y) {}` does not automatically implement `Comparable<Point>`; having `equals`/`hashCode` does not create a natural ordering. To use sorted collections, provide an appropriate comparator or implement `Comparable`.

## 7. Typical Mistakes and Misconceptions

**"Two records with the same fields must be equal."** Not sufficient. With auto-generated equality, **the exact same record class** is also a required condition; `Point(2,3)` differs from `Coordinate(2,3)`.

**"Records automatically deep-compare all reference components."** False. They use the component's `equals`. `String` compares contents, `List` compares elements per the List contract, and arrays default to identity. For a custom type you wrote without overriding `equals`, that component still compares by identity.

**"All records are completely immutable."** False. Component field references are `final`, but the objects they point to can be mutable. Arrays and lists in particular often require defensive copying if stable values are needed.

**"Records use `==` for all primitives."** For `float`/`double`, auto-generated equality handles NaN and signed zero using wrapper-like semantics, differing from the primitive `==` operator. Test boundary values before implementing `equals` manually.

**"Having equals means hashCode is unnecessary."** If keeping both auto-generated methods, Java guarantees compatibility. However, if overriding `equals` and omitting `hashCode`, you can break the contract, especially if excluding a component from comparison.

**"Identical `toString` means objects are equal."** `toString` is for display/debugging, not an identity contract. Do not rely on printed strings in place of `equals`, or use display order to infer hash results.

## 8. When Equality Different from the Default Is Needed: How Should You Design It?

Java allows explicitly declaring `equals(Object)` and `hashCode()` in a record. For example, a product display object has `sku` as a key, while `displayName` is merely supplementary data:

```java
import java.util.Objects;

record Product(String sku, String displayName) {
    Product {
        Objects.requireNonNull(sku);
    }

    @Override
    public boolean equals(Object other) {
        return this == other
                || (other instanceof Product p && sku.equals(p.sku));
    }

    @Override
    public int hashCode() {
        return sku.hashCode();
    }
}
```

This is a valid Java 17 record declaration, solely as an example of **customization**; it no longer compares `displayName`. Two `Product`s with the same `sku` will be equal even if `displayName` differs. Ensure `equals`/`hashCode` are based on the same key and that the key data is stable.

However, when the goal is simply to use a product code as a map key, a simpler option is usually to design a separate `record ProductId(String sku) {}` and store `displayName` in another model. That avoids breaking the default expectation that a record's components determine the value state of the record itself.

When manually overriding equality, protect the `Object` contract: reflexivity, symmetry, transitivity, consistency, null handling, and the implication between equals/hashCode. Do not arbitrarily treat two different record classes as equal; define the meaning clearly and verify symmetry across both types.

## 9. Checklist for Testing a Record

1. Two instances of **the same record class** with all identical components must be equal when using generated methods, even with different references.
2. Changing one component must change the result according to the equality semantics of that exact component type.
3. Two **different record classes** with the same structure/data remain unequal by default.
4. Test `null` components, `String`, nested records, arrays, and collections to understand which types compare by value and which compare by identity.
5. Test `float`/`double` with NaN and both signed zeros; avoid mechanically applying primitive `==`.
6. For mutable reference components, test whether data can be modified after creation; use defensive copies/immutability when used as collection keys.
7. Two equal records must have the same `hashCode()`; do not require equal hashes to imply equal records.
8. Use `HashSet`/`HashMap` with a new key of the same value to verify lookup and deduplication according to business meaning.
9. If writing `equals` manually, always review `hashCode`, stability, reflexivity, symmetry, and transitivity; consider whether a separate key record should be created.
10. If sorting is required, define a separate `Comparator` or `Comparable`, as records do not automatically have a natural ordering.

**Conclusion:** Java's auto-generated `equals(Object)` for a record returns `true` when the other object is of **the exact same record class** and **each pair of corresponding components is equal**. What "equal" means comes from the component type: primitives, floating-point numbers, `String`, arrays, and collections have different rules. Designing the right types and stability of components determines whether a record is truly a reliable value in an application.
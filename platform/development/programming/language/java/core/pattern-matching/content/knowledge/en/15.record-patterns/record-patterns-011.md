# Record Patterns and Record Immutability (Java 21)

## Objectives

After this lesson, you will be able to distinguish a **record class** from a **record pattern**, explain why records only provide **shallow immutability**, recognize when a record deconstruction exposes a mutable reference, and design records that preserve the intended immutability when holding a `List`, an array, or stateful objects.

**Version:** `record` has been a standard feature since Java 16; **record patterns** and pattern matching for `switch` are standard features in **Java 21** (no `--enable-preview` required). The examples run on JDK 21 and later.

## 1. How do a record class and a record pattern differ?

A `record` declares a data type with a fixed set of components:

```java
record Point(int x, int y) {}
```

The compiler provides `private final` component fields, accessors `x()` and `y()`, a canonical constructor, as well as `equals(Object)`, `hashCode()`, and `toString()` based on the components. For example:

```java
Point p = new Point(2, 4);
System.out.println(p.x()); // 2
System.out.println(p);     // Point[x=2, y=4]
```

By contrast, a **record pattern** is a pattern for *type-testing and deconstructing components* of a record value. For example, when `value` has declared type `Object`:

```java
if (value instanceof Point(int x, int y)) {
    System.out.println(x + y);
}
```

`Point(int x, int y)` in the condition above is **not a constructor call**. It checks whether `value` matches the `Point` record, then extracts the two components and binds them to pattern variables `x` and `y` for use in the matching branch. Writing `Point(var x, var y)` also works: Java infers the type of both variables as `int`.

Compare three ways of accessing data:

| Approach | Meaning |
| --- | --- |
| `p.x()` | Retrieve a component via its accessor |
| `value instanceof Point p` | Type check, keeping a reference to the entire `Point` |
| `value instanceof Point(var x, var y)` | Type check and directly deconstruct both components |

**Core relationship:** a record class determines how data is stored and exposed; a record pattern determines how that data is **read/deconstructed** in a match expression. A pattern **does not copy the record**, **does not mutate the record's state**, and **does not by itself make the data safer**.

## 2. How do record patterns work?

General form:

```java
RecordType(pattern1, pattern2, ...)
```

- `RecordType` must be a record type compatible with the value being tested.
- The number of component patterns must match the number of components, in the exact order of the record declaration.
- Each component is obtained via the record's accessor and matched against the corresponding pattern.
- Pattern variables are only in scope at locations where the compiler determines the match has succeeded.

Example with nested records:

```java
record Point(int x, int y) {}
record Rectangle(Point topLeft, Point bottomRight) {}

Object shape = new Rectangle(new Point(1, 2), new Point(5, 8));

if (shape instanceof Rectangle(
        Point(int left, int top),
        Point(int right, int bottom))) {
    System.out.println(left + "," + top + " -> " + right + "," + bottom);
}
// Output: 1,2 -> 5,8
```

`Rectangle(Point(...), Point(...))` is a **nested record pattern**: Java matches `Rectangle` and then continues deconstructing each `Point`. This avoids manual casts and long chains of accessor calls. When you want to keep a nested object intact, you can use `var`, for example `Rectangle(Point(var x, var y), var otherCorner)`.

### `null` and matching conditions

`null` **does not match any record pattern**. Therefore:

- `value instanceof Point(var x, var y)` returns `false` if `value == null`.
- Given `record Holder(Point point) {}`, the value `new Holder(null)` can match `Holder(var point)`, but **does not** match `Holder(Point(var x, var y))`, because the `point` component is `null`.
- In a `switch` with patterns, use `case null` to handle `null`; if there is no matching case for `null`, `switch` can throw a `NullPointerException`. A standalone `default` does not replace handling `null`.

Record patterns also appear in Java 21 `switch` statements/expressions. A `when` clause lets you add an extra guard condition; place more specific cases before general ones to avoid dominance errors.

## 3. Record immutability: `final` does not mean deep immutability

Each component is stored in a `final` field, so the field cannot be reassigned after the object is constructed. For example, `Point` has no setters for `x`/`y`; if you want different coordinates, you typically create a new `Point`.

However, `final` **locks the reference in the field**, not the object that the reference points to. Consider:

```java
record Profile(String name, List<String> roles) {}

List<String> source = new ArrayList<>(List.of("read"));
Profile profile = new Profile("An", source);

// The roles field itself cannot be reassigned to another List,
// but the List it points to can still be modified:
source.add("write");
System.out.println(profile.roles()); // [read, write]
```

The newly created record holds **the same reference** `source`. If someone mutates `source`, the data observed through `profile.roles()` also changes. Similarly:

```java
if (profile instanceof Profile(var name, var roles)) {
    roles.add("admin"); // modifies the List referenced by the component
}
```

A record pattern only extracts the `roles` reference; deconstruction does not clone the `List`. Thus, **records guarantee immutability of their component fields, but by default are only shallowly immutable**—they do not guarantee that every object inside is immutable. This also affects consistency when sharing data across threads and when using a record with mutable components as a `HashMap` key.

### When can a record be considered immutable in practice?

A record that only contains primitive values, `String`, or truly immutable objects is usually well suited as a value object:

```java
record Coordinate(int latitude, int longitude) {}
record PersonName(String first, String last) {}
```

For components of type `List`, arrays, or mutable objects, you must proactively protect them both when **accepting input** and when **returning data**. Nested records are also only safe if the deeply nested components are controlled in the same way.

## 4. Complete program: deconstructing records and checking immutability

Create the file **`RecordPatternDemo.java`**:

```java
import java.util.*;

public class RecordPatternDemo {
    record Point(int x, int y) {}
    record Rectangle(Point upperLeft, Point lowerRight) {}

    // Shallowly immutable only: the List can still be mutated.
    record Profile(String name, List<String> roles) {}

    // Copy the List on record creation to protect the input data.
    record SafeProfile(String name, List<String> roles) {
        SafeProfile {
            Objects.requireNonNull(name);
            roles = List.copyOf(roles);
        }
    }

    // Arrays must be copied both on input and on output.
    record Packet(byte[] data) {
        Packet {
            Objects.requireNonNull(data);
            data = data.clone();
        }

        @Override
        public byte[] data() {
            return data.clone();
        }

        // Arrays use content-based equals/hashCode instead of reference identity.
        @Override
        public boolean equals(Object other) {
            return other instanceof Packet p && Arrays.equals(data, p.data);
        }

        @Override
        public int hashCode() {
            return Arrays.hashCode(data);
        }
    }

    static String inspect(Object value) {
        return switch (value) {
            case Rectangle(Point(var x1, var y1), Point(var x2, var y2)) ->
                    "Rectangle (" + x1 + "," + y1 + ") -> ("
                            + x2 + "," + y2 + ")";
            case Point(var x, var y) when x == y -> "Point on x=y: " + x;
            case Point(var x, var y) -> "Point (" + x + "," + y + ")";
            case null -> "null";
            default -> "unknown";
        };
    }

    public static void main(String[] args) {
        System.out.println(inspect(
                new Rectangle(new Point(1, 2), new Point(5, 8))));
        System.out.println(inspect(new Point(3, 3)));
        System.out.println(inspect(null));

        List<String> source = new ArrayList<>(List.of("read"));
        Profile profile = new Profile("An", source);
        if (profile instanceof Profile(var name, var roles)) {
            roles.add("write");
        }
        System.out.println(profile.roles());

        SafeProfile stable = new SafeProfile("An", source);
        source.add("delete");
        System.out.println(stable.roles());

        try {
            stable.roles().add("admin");
        } catch (UnsupportedOperationException ex) {
            System.out.println("unmodifiable");
        }

        byte[] buffer = {1, 2};
        Packet packet = new Packet(buffer);
        buffer[0] = 9;
        if (packet instanceof Packet(var snapshot)) {
            snapshot[1] = 8;
        }
        System.out.println(Arrays.toString(packet.data()));
        System.out.println(packet.equals(new Packet(packet.data())));
    }
}
```

Compile and run on JDK 21 or later:

```bash
javac --release 21 RecordPatternDemo.java
java RecordPatternDemo
```

Output:

```text
Rectangle (1,2) -> (5,8)
Point on x=y: 3
null
[read, write]
[read, write]
unmodifiable
[1, 2]
true
```

Key takeaways:

1. `inspect` uses nested record patterns to read the two points of a `Rectangle`. For `Point(3,3)`, the `when x == y` branch is selected before the general `Point` branch.
2. `Profile` shares `source` with the outside. The `roles` variable extracted by the pattern points to that same list, so adding `"write"` changes the data seen through `profile`.
3. `SafeProfile` calls `List.copyOf(roles)` in its **compact canonical constructor**. Therefore, subsequent changes to `source` do not affect `stable`, and the returned list also rejects `add`.
4. `Packet` clones the array in both its constructor and accessor. When the pattern `Packet(var snapshot)` is matched, the `data()` accessor is invoked, so `snapshot` is a copy. Modifying `buffer` or `snapshot` does not alter the internal component.
5. `Packet` defines custom `equals` and `hashCode` using `Arrays.equals`/`Arrays.hashCode`. With the auto-generated implementation, an array component would be compared by reference identity rather than element contents. Two `Packet` instances with identical bytes in different arrays would be considered unequal; meanwhile, an accessor returning a copy could violate the record's copying contract. Thus, you must consider both **data immutability** and **equality semantics**.

## 5. Designing safe records with mutable data

**Step 1: Validate invariants in the constructor.** A compact canonical constructor lets you validate and normalize parameters before the compiler assigns them to the fields:

```java
record Money(String currency, long cents) {
    Money {
        Objects.requireNonNull(currency, "currency");
        if (currency.isBlank()) {
            throw new IllegalArgumentException("currency must not be blank");
        }
        if (cents < 0) {
            throw new IllegalArgumentException("cents must be >= 0");
        }
    }
}
```

Use the constructor only to initialize/validate components; do not use records for models that require changing identity or continuous internal state mutations.

**Step 2: Break aliases on input.** For `List<String>`, `List.copyOf` is usually the right choice: it creates/returns an unmodifiable list, isolated from later changes to the mutable input list, and rejects `null` elements. For `Map`/`Set`, `Map.copyOf` and `Set.copyOf` behave similarly.

**Step 3: Evaluate component depth.** `List.copyOf` is a **shallow copy of the elements**. If a `List` contains a `StringBuilder` or a bean with setters, anyone holding a reference to those elements can still mutate their contents even though the list disallows additions/removals. Illustrative example:

```java
record Notes(List<StringBuilder> items) {
    Notes {
        items = List.copyOf(items);
    }
}

// The List does not allow additions/removals, but the StringBuilder inside is still mutable.
StringBuilder text = new StringBuilder("A");
Notes notes = new Notes(List.of(text));
text.append("B");
System.out.println(notes.items().get(0)); // AB
```

For deeper immutability, convert elements to an immutable type (such as `String` or a record containing only immutable values), or copy each element according to your domain's rules. For instance, `record Order(List<LineItem> items)` with `List.copyOf(items)` is safer if `LineItem` is an immutable record with immutable components.

**Step 4: Protect accessors for arrays/mutable objects as well.** Cloning on input alone is not enough: if the accessor returns the internal array directly, callers can still mutate that array. Conversely, cloning in the accessor without revisiting `equals`/`hashCode` can prevent the record from behaving like a proper value object.

**Step 5: Preserve the record contract.** Value-wise, a copy constructed from the accessors themselves should equal the original:

```java
R copy = new R(r.component1(), r.component2());
assert r.equals(copy);
```

This is an **illustrative pattern** for a record `R` with two components, not a standalone runnable Java snippet. When customizing constructors, accessors, `equals`, or `hashCode`, preserve the corresponding contract. In particular, avoid accessors with side effects: record patterns invoke accessors to extract components, so side effects make pattern matching unpredictable.

## 6. Record patterns do not change a record's immutability characteristics

Keep these three layers of behavior distinct:

| Layer | What is guaranteed? | What is not guaranteed? |
| --- | --- | --- |
| Record fields | Component references/values cannot be reassigned after construction | Referenced objects are automatically immutable |
| Record patterns | Type checking and extracting components via accessors | Does not clone, lock, or re-validate data |
| Defensive copy + immutable components | Can prevent mutable aliases and preserve data invariants | `List.copyOf` does not automatically deep-copy mutable elements |

It follows that if a record holds a mutable `List`, `case Profile(var name, var roles)` exposes the same reference that `profile.roles()` would return. If the record is designed with defensive copies and safe accessors, the pattern also observes through those accessors; **safety comes from the record's design**, not from pattern syntax.

Record patterns are ideal for reading nested data models, handling cases in `switch`, and writing clear data-inspection logic. When data needs to change frequently, consider a controlled mutable class or creating a **new record** to represent the new state:

```java
record Counter(int value) {
    Counter increment() {
        return new Counter(value + 1);
    }
}
Counter before = new Counter(1);
Counter after = before.increment(); // before.value() is still 1
```

### Common pitfalls

- **Using a record with a `List`/array and assuming it is deeply immutable:** add defensive copies, choose immutable components, and protect accessors when needed.
- **Thinking `var roles` in a record pattern is a copy:** it is a variable receiving the component value; for reference types, it can point to the same mutable object.
- **Placing `case Point(var x, var y)` before `case Point(var x, var y) when ...`:** the general case can dominate the specific one; reverse their order.
- **Assuming a nested pattern accepts `null`:** record patterns do not match `null`, including `null` in a nested component.
- **Using `record Payload(byte[] bytes)` and relying on auto-generated `equals` to compare array contents:** arrays default to reference equality; choose an appropriate equality policy.
- **Writing record pattern examples on JDK 17 without checking the version:** JDK 17 supports records, but record patterns only became standard in Java 21.
- **Using `record` instead of every class:** records fit best when the data shape is a stable public contract; records do not support extending arbitrary classes or adding instance fields outside components.

## 7. Self-check

1. Why can the observable contents of `record Profile(List<String> roles)` still change after the constructor runs? **Because the `final` field fixes the reference, while the `List` object itself can still be modified.**
2. Does `if (o instanceof Point(int x, int y))` create a new `Point`? **No.** It matches the type and extracts the components of the existing object.
3. If `List.copyOf` contains a mutable object, is the record deeply immutable? **No.** The elements themselves must also be protected.
4. Does `Holder(Point(var x, var y))` match `new Holder(null)`? **No.** The nested `Point` pattern does not match `null`.
5. Why does cloning an array in both the constructor and the accessor also require considering equality? **Because the generated `equals` compares array references; copied values with identical contents might not be considered equal.**

## References

- [Oracle Java SE 21 — Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html)
- [Oracle Java SE 21 — Record Classes](https://docs.oracle.com/en/java/javase/21/language/records.html)
- [Java SE 21 API — java.lang.Record](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Record.html)

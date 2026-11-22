# Do Not Rely on the Generated Hash Algorithm or `toString()` Format as a Fixed Protocol

## Lesson Objectives

A `record` declaration in Java automatically provides `equals(Object)`, `hashCode()`, and `toString()` if the programmer does not declare them explicitly. These methods are very useful when working with **data-carrying objects**: comparing components, using them as collection keys, and quickly reading state while debugging.

However, a **behavioral contract** does not mean a **guarantee to preserve implementation details or exact output text**. For auto-generated methods, Java guarantees important properties; Java does not promise a specific arithmetic hash formula or a `toString()` string that can serve as a long-term data exchange format.

After this lesson, you can:

- State what is guaranteed and what is not guaranteed by auto-generated `equals()`, `hashCode()`, and `toString()` for a `record`.
- Avoid storing `hashCode()` as an identifier, checksum, or persistent correlation key across runs.
- Avoid parsing auto-generated `toString()` to reconstruct records or using it as JSON, CSV, API messages, or a storage format.
- Design an explicitly versioned codec when a stable data format is required.
- Write contract-oriented tests while understanding pitfalls with array or mutable-object components.

## 1. What Is Generated from a Record Declaration?

Java 17+ example:

```java
record Event(int id, String action) {}
```

The declaration above creates a record type with two components, each backed by a `private final` field and a corresponding `id()`, `action()` accessor. Besides the canonical constructor, the record has `equals(Object)`, `hashCode()`, and `toString()` unless explicitly implemented.

You can write:

```java
Event a = new Event(42, "LOGIN");
Event b = new Event(42, "LOGIN");
Event c = new Event(43, "LOGIN");

System.out.println(a.equals(b));                // true
System.out.println(a.hashCode() == b.hashCode()); // true
System.out.println(a.equals(c));                // false
```

These are illustrative code snippets that belong inside a method with access to `Event`; a standalone program appears later.

**Key contract:**

- The auto-generated `equals()` method checks that the argument is an instance of **the same record class** and corresponding components are equal according to the rules of each component type. For reference-type components, the rule is equivalent to `Objects.equals(...)`; for primitive types, comparison semantics matching the corresponding wrapper class are used.
- If `a.equals(b)` is `true`, `a.hashCode()` and `b.hashCode()` **must be equal** as long as the relevant data does not change.
- Auto-generated `toString()` is a human-readable representation including the record class name, component names, and string representations of component values. **The exact syntax is not locked as a protocol.**

Two records with identical data may print identical text, yet that does not turn that text into an official storage format. Component-based comparison and reading a display string are two different needs.

## 2. Semantic Guarantees vs. Algorithmic Guarantees

To distinguish accurately, see the following table:

| Aspect | What You Can Rely On | What You Should Not Assume |
| --- | --- | --- |
| Auto-generated `equals()` | Same record class and equal corresponding components imply equal records | Machine code, check order, or a fixed internal comparison algorithm |
| Auto-generated `hashCode()` | Hash is derived from components; equal records must have equal hashes | An arithmetic formula, combining order, or fixed `int` value across environments |
| Auto-generated `toString()` | Representation containing record name, component names, and component value strings | Fixed brackets, commas, equals signs, spaces, escaping, or character layout |
| Accessors like `id()` | Retrieving component value with its declared type | That this is automatically a versioned serialization format |

This is especially important when upgrading JDKs: two Java releases can both fully comply with the `Record` contract while choosing different hash generation algorithms or `toString()` formatting.

The Java API explicitly states that **the exact hash algorithm of a record is unspecified and subject to change**, including the hash number for the same data across executions. For `toString()`, the API likewise states **the exact format may change and programs should not parse that string to recover components**.

Therefore, proper tests should assert **relationships and behavior**, rather than locking onto details the platform does not promise.

## 3. Do Not Treat `record.hashCode()` as a Stable Identifier

Consider:

```java
record Order(int orderId, String status) {}
```

In memory, `hashCode()` is very helpful for `HashMap<Order, ...>` or `HashSet<Order>` when components maintain contract-compliant state.

However, the following uses are unsafe:

- Writing `order.hashCode()` to a database and treating it as the order's primary key.
- Sending the hash to another service as a reference ID for that service to recompute from the record.
- Using the hash code as a persistent cache filename that must match across JDK upgrades or subsequent application runs.
- Comparing a record's hash across two JVMs or two implementations as mandatory proof of identical data.
- Treating a 32-bit hash as a sufficiently strong checksum, digital signature, integrity proof, or security token.

There are two independent reasons.

### 3.1. The Algorithm Is Not a Public Contract

Java only requires the hash code to be properly derived from the components and obey the `Object.hashCode()` contract. It does not mean the compiler must use a formula like `Objects.hash(id, status)`, `31 * id + status.hashCode()`, or any assumed formula.

Code like the following is an anti-pattern:

```java
Order order = new Order(10, "PAID");

// Do not permanently store order.hashCode() as a protocol key.
// Do not assert in tests that order.hashCode() must equal a predicted integer.
int implementationHash = order.hashCode();
```

The `implementationHash` result is a valid `int`, yet from a value observed on one JDK you must not conclude that every version must return the same number.

Some components also compute their hash codes depending on inner objects: if a component is an array or a type that does not override `hashCode()`, the component's hash may reflect object identity. In that case, two pieces of data that "look alike" may not have equal hashes.

### 3.2. Collisions Can Always Happen

`hashCode()` returns a 32-bit `int`. Many distinct records can share the same hash. The contract only guarantees one direction:

```text
a.equals(b) == true
           ⇒ a.hashCode() == b.hashCode()
```

There is no converse:

```text
a.hashCode() == b.hashCode()
           ⇏ a.equals(b) == true
```

Consequently, even if you fix a hash algorithm yourself, a hash value still does not automatically become a unique ID. A system needing stable identifiers should have an **explicit business ID**, such as an `orderId` managed per system requirements; generating IDs and guaranteeing uniqueness are a separate part of data design.

If you truly need a durable content-derived lookup key, you must define a **canonical byte format** and an identification/hashing strategy built for that purpose. A fast hash for collections does not replace identifiers or cryptographic functions.

## 4. Do Not Treat Auto-Generated `record.toString()` as JSON, CSV, or a Wire Protocol

Given:

```java
record Order(int id, String status) {}
Order order = new Order(10, "PAID");
System.out.println(order);
```

A current JDK release may display something like:

```text
Order[id=10, status=PAID]
```

**The line above only illustrates a common display style, not character output guaranteed by Java across all versions.** Do not write parsers or tests requiring matches on `[`, `]`, `=`, commas, or whitespace of this display pattern.

The following example is an **anti-pattern**:

```java
String display = order.toString();

// WRONG: trying to parse display based on ',' or '=' of auto-generated toString.
// WRONG: sending display as JSON/CSV or claiming it has a fixed schema.
// WRONG: storing display in a DB and using split(...) to reconstruct Order.
```

Typical problems:

1. **The syntax is not fixed.** Java may change character arrangement, symbols, and formatting details while still satisfying the `toString()` contract.
2. **Component values are not automatically escaped according to a protocol you choose.** For instance, strings containing commas, newlines, brackets, or `=` make delimiter-based parsers fragile.
3. **Nested values may not be recoverable data.** If a component is an array, the array's own `toString()` does not print a JSON-like data structure; some component values may use debug-oriented formatting.
4. **Sensitive information can appear in logs.** A record containing tokens, emails, or secrets can expose contents if printed by default without control.

`toString()` is very useful for quickly inspecting state during development. If a fixed UI display format is needed, create a dedicated formatter. If sending or storing data is needed, use a **serialization format with an explicit schema**.

## 5. Complete Java 17+ Example: Comparing the Contract and a Versioned Format

This program uses the `Event` record and intentionally does **not** rely on hash numbers or auto-generated `toString()` strings to encode data.

To keep the example standalone without external JSON libraries, we define a minimal codec:

- Prefix `v1` identifies the format version.
- `id` is a decimal integer.
- `action` is UTF-8 encoded and then URL-safe Base64 encoded without padding, so this field itself never contains the `|` character.

This format is for demonstration only; in real systems, JSON/CBOR/Protobuf or a standard with proper schema and escaping rules is usually more convenient.

Save the file `RecordProtocolDemo.java`:

```java
import java.nio.charset.StandardCharsets;
import java.util.Base64;
import java.util.Objects;

public class RecordProtocolDemo {
    record Event(int id, String action) {
        Event {
            Objects.requireNonNull(action, "action");
        }
    }

    static String encode(Event event) {
        String payload = Base64.getUrlEncoder()
                .withoutPadding()
                .encodeToString(
                        event.action().getBytes(StandardCharsets.UTF_8));
        return "v1|" + event.id() + "|" + payload;
    }

    static Event decode(String wire) {
        String[] parts = wire.split("\\|", -1);
        if (parts.length != 3 || !"v1".equals(parts[0])) {
            throw new IllegalArgumentException("Unsupported wire format");
        }

        int id = Integer.parseInt(parts[1]);
        String action = new String(
                Base64.getUrlDecoder().decode(parts[2]),
                StandardCharsets.UTF_8);
        return new Event(id, action);
    }

    public static void main(String[] args) {
        Event a = new Event(42, "LOGIN");
        Event b = new Event(42, "LOGIN");
        Event c = new Event(43, "LOGIN");

        System.out.println("equal records: " + a.equals(b));
        System.out.println("equal hash contract: "
                + (a.hashCode() == b.hashCode()));
        System.out.println("different records: " + !a.equals(c));

        String wire = encode(a);
        System.out.println("wire: " + wire);
        System.out.println("round trip: " + decode(wire).equals(a));

        // Do not rely on hash digits or toString() formatting.
        System.out.println("debug text available: "
                + !a.toString().isBlank());
    }
}
```

Compile and run with JDK 17+:

```bash
javac RecordProtocolDemo.java
java RecordProtocolDemo
```

**Deterministic output of the program itself:**

```text
equal records: true
equal hash contract: true
different records: true
wire: v1|42|TE9HSU4
round trip: true
debug text available: true
```

Explanation:

- `a.equals(b)` is `true` because both are of class `Event` and their corresponding components are equal.
- The hash codes of `a` and `b` must be equal by contract; we **only test equality**, without printing or asserting a specific hash number.
- `a` and `c` have different `id`s so they are not equal.
- `wire` is produced by rules defined by the program itself. The string `LOGIN` encodes in URL-safe Base64 as `TE9HSU4`, so the representation `v1|42|TE9HSU4` is predictable.
- `decode(wire)` recovers the fields through a versioned codec, without parsing `Event.toString()`.
- `toString()` remains usable for display purposes; the program only verifies that an informational string is present, without tying it to a specific display syntax.

This example codec is still simple: `decode` uses the default UTF-8 decoder and does not define full rules for validating malicious input, size limits, schema evolution, or backward compatibility. In a real protocol, add those constraints and test malformed data. Still, it demonstrates the key principle: **the exchange format lives inside a contract controlled by the application**.

## 6. Writing Focused Tests

A good test for an auto-generated record should verify the properties Java guarantees:

```java
Event x = new Event(7, "READY");
Event y = new Event(7, "READY");
Event z = new Event(8, "READY");

// Check semantic contract:
boolean sameValue = x.equals(y);                 // true
boolean equalHash = x.hashCode() == y.hashCode(); // true
boolean different = !x.equals(z);                // true
boolean noNullEquality = !x.equals(null);        // true

// Check format defined by the program itself:
boolean codecRoundTrip = decode(encode(x)).equals(x); // true
boolean schemaVersion = encode(x).startsWith("v1|");  // true
```

This is an **illustrative snippet inside the `RecordProtocolDemo` class**, using `Event` and `encode/decode` from the complete example.

Types of assertions you should not write:

```java
// ANTI-PATTERN:
// assertEquals(12345678, x.hashCode());
// assertEquals("Event[id=7, action=READY]", x.toString());
```

Both assertions above tie code to details that are not guaranteed parts of auto-generation's contract. They may happen to pass on the current JVM and then become brittle when implementations change.

If you **define your own** formatter or codec intended to produce specific output, testing the exact string/bytes produced by that formatter or codec is appropriate. Distinguish clearly:

- **Testing Java record contracts:** `equals` semantics and relation with `hashCode`, presence of information in `toString` representation.
- **Testing application contracts:** exact strings/bytes of a codec or formatter committed to by the application, including versioning and special-character handling.

When a product requires durable storage, add golden tests for the application codec across software versions; such golden tests are the responsibility of the application schema, not the job of `record.toString()`.

## 7. Easy-to-Miss Detail: Array or Mutable Object Components

`record` is **shallowly immutable**: component references cannot be reassigned from outside, yet the contents of the objects components point to can still change.

Example:

```java
record Packet(byte[] data) {}

Packet first = new Packet(new byte[] {1, 2});
Packet second = new Packet(new byte[] {1, 2});

System.out.println(first.equals(second)); // false
```

This is an illustrative snippet inside a method. Even though both `byte[]` arrays have identical contents, the auto-generated record uses **reference-type component** equality rules. Arrays do not override `Object.equals()` to compare element-by-element, so two distinct arrays are unequal by reference.

Similarly, the hash of a record with an array component will be based on the array component's hash, not automatically computing `Arrays.hashCode(data)` or `Arrays.deepHashCode(data)`. Auto-generated `toString()` may contain an identity-style representation of the array rather than a parseable list of bytes.

Another mistake is expecting `final` on a component to make inner contents completely immutable. The following still mutates the array:

```java
byte[] bytes = {1, 2};
Packet packet = new Packet(bytes);
bytes[0] = 9;                    // Original array is modified
packet.data()[1] = 8;            // Accessor returns the array reference
```

This does not necessarily change an array record's hash with array contents, because default array hashing is identity-based; yet it illustrates why **a record is not automatically a deeply immutable value**. For other mutable component types whose `equals/hashCode` rely on internal state, mutating state can alter `equals/hashCode` results while the object is inside a `HashMap` or `HashSet`.

If business logic needs value-based array comparison, explicitly define corresponding comparison and hashing using `Arrays.equals/hashCode` or `Arrays.deepEquals/deepHashCode`, and also consider **defensive copying** in constructor/accessor. That is a separate design decision: it cannot be inferred from a record's auto-generated methods.

## 8. What Must a Stable Protocol Explicitly Decide?

When a record is a DTO or application model participating in an API, the existence of the record does not substitute for an external schema. A long-lived protocol needs at least:

1. **Field names and data types:** e.g., `id` is an integer, `action` is a UTF-8 string; which fields are required and which can be `null`.
2. **Structure and encoding:** JSON, CBOR, Protobuf, or a specified format; if a custom string format, escaping/delimiters/field lengths must be specified.
3. **Versioning and compatibility:** how adding fields, renaming, changing types, unknown fields, or missing values are handled.
4. **Normalization rules:** field order if needed, floating-point numbers, timezones, locales, Unicode characters, whitespace, encoding, and edge cases.
5. **Input validation:** length limits, valid values, malformed data, unsupported versions.
6. **Separating identifiers and checksums:** business IDs, content digests, or digital signatures must be chosen per requirements, not replaced by `record.hashCode()`.

For instance, the record:

```java
record Payment(long id, String currency, long amountMinor) {}
```

can map to a JSON document with a schema managed by the application or a serialization library. When a stable JSON format is needed, define property names, string/number rules, versioning, backward compatibility, and serialization library/settings. **Do not send `payment.toString()` assuming the receiver can interpret it as JSON.**

You can manually override `toString()` to control presentation:

```java
record Payment(long id, String currency, long amountMinor) {
    @Override
    public String toString() {
        return "Payment #" + id + " (" + currency + ")";
    }
}
```

However, this is an **application-author-defined format**, not the record's default syntax. It is better suited for human-readable messages; if used as a protocol, it still needs a specification, escaping, versioning, and compatibility rules. Overriding one method does not automatically solve serialization concerns.

## 9. Common Mistakes

### Mistake 1 — Coupling Tests to a Specific Hash Number

Observing `hashCode() == 12345` on one JDK creates no requirement that every JVM must return that exact number. Test that **equal objects have equal hashes**, not fixed compiler-generated hashes.

### Mistake 2 — Using Hash as a Primary Key or Transaction Code

Hashes can collide and generation formulas can change. Use stable business IDs or a purpose-built identification mechanism.

### Mistake 3 — Parsing `toString()` with `split`

Auto-generated `toString()` has no stable syntax guarantee; components may contain delimiters or newlines. Use a schema-backed codec/serialization.

### Mistake 4 — Assuming a Record's `toString()` Is JSON

A debug representation is not equivalent to JSON. Looking syntactically similar on one machine does not make it a specified protocol.

### Mistake 5 — Thinking Records Auto-Generate Deep Comparison

Records check components according to each component type's rules. Arrays have identity-based `equals()`, without automatic deep content comparison. If deep value comparison is needed, implement it explicitly and preserve the `hashCode` contract.

### Mistake 6 — Confusing Field Immutability with Content Immutability

Final component fields do not prohibit mutating elements inside a referenced array or collection. If using a record as a hash key, check the stability of data participating in `equals/hashCode`.

### Mistake 7 — Using Default `toString()` in Logs Containing Sensitive Data

The default representation can put component strings into logs. Assess fields that must be masked, choose an appropriate logger/formatter, and do not print tokens or secrets merely because records come with `toString()`.

### Mistake 8 — Treating Current Implementation Details as Part of the Specification

Behavior observed in one OpenJDK release can be an internal detail, not a long-term compatibility promise. Rely on Javadoc/JLS when deciding what can become an application contract.

## 10. Self-Check Exercise

Consider the record:

```java
record Snapshot(int version, String payload) {}
Snapshot x = new Snapshot(1, "ok");
Snapshot y = new Snapshot(1, "ok");
Snapshot z = new Snapshot(2, "ok");
```

This is a snippet placed inside a method with access to `Snapshot`.

Evaluate the statements:

| Statement | True/False | Reason |
| --- | --- | --- |
| `x.equals(y)` is `true`. | **True** | Same class and equal component values. |
| `x.hashCode() == y.hashCode()` must be `true`. | **True** | Guaranteed by the hash contract. |
| `x.hashCode()` must be a fixed integer across all JDKs. | **False** | The auto-generated record hash algorithm is not fixed. |
| `x.equals(z)` is `false`. | **True** | The `version` component differs. |
| If `x` and `z` have matching hashes, then `x.equals(z)` must be `true`. | **False** | Collisions do not imply equality. |
| The `x.toString()` string can be parsed using `[`, `,`, `=`, and `]` according to the Java spec. | **False** | The exact syntax of auto-generated `toString()` is not guaranteed. |
| `x.toString()` can be used to inspect state while debugging. | **True** | That is the appropriate purpose of a human-readable representation. |
| For durable storage, define a format/schema and version instead of relying on `toString()`. | **True** | The application controls its own data contract. |

Hands-on exercise: keep the `Snapshot` record, but design a `v1` codec with explicit string encoding. Add a field to the record in version `v2` and define how the `v2` reader accepts `v1` data. Write round-trip tests and legacy-version tests. These tests should protect the format **committed to by the application**, not JVM-generated hash numbers or debug syntax.

## 11. Official Reference Documentation

- [Java SE 21 — `java.lang.Record`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Record.html): directly describes the contract and limits of `equals()`, `hashCode()`, and `toString()`.
- [Java SE 21 — Record Classes](https://docs.oracle.com/en/java/javase/21/language/records.html): explains the members and methods generated for records.

When needing to know whether a behavior can be relied on long-term, prioritize **the API contract and Java Language Specification**, rather than copying output from a current run and treating it as standard.

## Key Takeaway

**With auto-generated records, rely on the equality and hash code contracts, not on the hash formula or the exact characters of `toString()`.** Hash codes are for in-memory hash-based operations; `toString()` representations are for reading and diagnostics. When a format stable across versions, machines, and processes is needed, explicitly design **schema, codec, encoding, and versioning**, and test that exact format.
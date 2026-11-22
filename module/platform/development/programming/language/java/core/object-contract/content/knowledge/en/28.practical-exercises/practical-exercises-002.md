# Building Multi-Field Business Keys in Java

## 1. Real-World Problem: A Single Field Is Not Enough to Identify an Object

In many systems, an identifier can collide across customers, integration channels, or business scopes. For example, invoice code **INV-0042** might appear in both tenants; even the same tenant might receive that code from two different source systems.

Suppose the business rule has been confirmed:

> An invoice is uniquely identified by **(tenantId, sourceSystem, externalNumber)**. All three fields are required; the system treats these codes as case-insensitive and strips leading/trailing whitespace.

That triplet is a **composite business key**. It represents *the same entity in a business sense*, even if two Java objects are created at two different times.

Example:

| tenantId | sourceSystem | externalNumber | Same key as the first row? |
| --- | --- | --- | --- |
| SHOP-A | ERP | INV-0042 | Itself |
| shop-a | erp | inv-0042 | Yes, per the chosen normalization rule |
| SHOP-B | ERP | INV-0042 | No: different tenant |
| SHOP-A | WEB | INV-0042 | No: different source |
| SHOP-A | ERP | INV-0099 | No: different invoice number |

If only **externalNumber** is used as the key of a **Map** or as a deduplication condition, data from different tenants/sources can overwrite each other. If arbitrary string concatenation is used to build the key, we also face ambiguity risks and difficult maintenance.

In Java, the solution is usually to create **a dedicated data type for the key**, define the set of fields participating in comparison, normalize values at input time, and ensure **equals()/hashCode()** are consistent.

## 2. Distinguishing Business Keys and Technical Keys

A **business key** is a combination of attributes meaningful to users or integrated systems: tenant, source, partner code, effective date, etc. For example, **(tenantId, sourceSystem, externalNumber)**.

A **technical key** is a system-generated identifier, usually an auto-incrementing **id** or **UUID**, used for storage, internal references, or a database primary key.

An invoice might have:

- **id = 98217**: internal technical key.
- **(SHOP-A, ERP, INV-0042)**: business key to find the invoice received from ERP for tenant SHOP-A.

The two key types are not mutually exclusive. A common design uses **id** as the primary key and applies a **UNIQUE** constraint to the business triplet. When an invoice number or business rule can change, clarify whether that key represents stable identity or is only a lookup/deduplication key at a point in time.

A good composite key should answer: **"Does changing just one field in this tuple turn the object into a different entity?"** If yes, that field usually belongs in the key; if no, it is likely an ordinary attribute.

## 3. The equals() and hashCode() Contract for Composite Keys

**HashMap**, **HashSet**, and hash-based structures use **hashCode()** to distribute elements and **equals()** to determine whether two keys share the same identity. Therefore:

1. **Reflexive:** for a valid key **a**, **a.equals(a)** is **true**.
2. **Symmetric:** **a.equals(b)** and **b.equals(a)** produce the same result.
3. **Transitive:** if **a.equals(b)** and **b.equals(c)**, then **a.equals(c)**.
4. **Consistent:** when values participating in comparison do not change, calling **equals()** repeatedly must return the same result.
5. **Comparison with null:** **a.equals(null)** is **false**.
6. **Hash compatibility:** if **a.equals(b)** is **true**, then **a.hashCode() == b.hashCode()** must hold.

The converse **is not required**: two *different* keys may share a hash because hash collisions are normal. Therefore, **hashCode()** must never be treated as a unique identifier, and hash values alone must not be used to confirm duplicate data.

When building a key from three fields, all three fields must participate in the identity comparison; omitting **sourceSystem** in **equals()** or **hashCode()** can create subtle bugs. At the same time, fields participating in the hash must remain **stable for the entire time the key resides in a Map/Set**.

## 4. Java 17+ Solution: Using an Immutable record

**record** fits business keys composed of simple value components. Java automatically generates the canonical constructor, accessors, **equals()**, **hashCode()**, and **toString()** based on all record components. We can add a compact canonical constructor to validate and normalize inputs before storing them.

Complete example, saved in file **InvoiceKeyDemo.java**:

~~~java
import java.util.HashMap;
import java.util.Locale;
import java.util.Map;
import java.util.Objects;

public class InvoiceKeyDemo {
    public record InvoiceKey(
            String tenantId,
            String sourceSystem,
            String externalNumber) {

        // Compact canonical constructor:
        // normalize before Java assigns to the record fields.
        public InvoiceKey {
            tenantId = normalize("tenantId", tenantId);
            sourceSystem = normalize("sourceSystem", sourceSystem);
            externalNumber = normalize("externalNumber", externalNumber);
        }

        private static String normalize(String field, String value) {
            Objects.requireNonNull(value, field + " must not be null");
            String result = value.strip().toUpperCase(Locale.ROOT);
            if (result.isEmpty()) {
                throw new IllegalArgumentException(field + " must not be blank");
            }
            return result;
        }
    }

    public static void main(String[] args) {
        InvoiceKey first = new InvoiceKey(
                "shop-a", "erp", " inv-0042 ");
        InvoiceKey same = new InvoiceKey(
                " SHOP-A ", "ERP", "INV-0042");
        InvoiceKey otherTenant = new InvoiceKey(
                "shop-b", "erp", "INV-0042");
        InvoiceKey otherSource = new InvoiceKey(
                "shop-a", "web", "INV-0042");

        Map<InvoiceKey, String> states = new HashMap<>();
        states.put(first, "NEW");
        states.put(same, "PAID");
        states.put(otherTenant, "NEW");
        states.put(otherSource, "REVIEW");

        System.out.println("same identity: " + first.equals(same));
        System.out.println("same hash: "
                + (first.hashCode() == same.hashCode()));
        System.out.println("different tenant: "
                + first.equals(otherTenant));
        System.out.println("different source: "
                + first.equals(otherSource));
        System.out.println("size: " + states.size());
        System.out.println("normalized: " + first);
        System.out.println("lookup: " + states.get(
                new InvoiceKey("SHOP-A", "ErP", "inv-0042")));
    }
}
~~~

Compile and run with JDK 17 or higher:

~~~bash
javac InvoiceKeyDemo.java
java InvoiceKeyDemo
~~~

Expected output:

~~~text
same identity: true
same hash: true
different tenant: false
different source: false
size: 3
normalized: InvoiceKey[tenantId=SHOP-A, sourceSystem=ERP, externalNumber=INV-0042]
lookup: PAID
~~~

**Explanation:** The two objects **first** and **same** have different references but share the same business identity after normalization. Calling **put(same, "PAID")** replaces the value of the already-present equivalent key, so **size** is **3**, not **4**. The two invoices from a different tenant or different source are still stored separately. The final lookup creates a new key object yet still finds the **PAID** state.

The code above uses the rule **strip leading/trailing whitespace + case-insensitive across all three fields** because that is the stated business assumption. **Do not apply this normalization mechanically**: if tenantId, codes with mixed case, or externalNumber actually distinguish character casing, uppercasing can mistakenly merge two distinct entities.

### Why is record useful?

- **Inherently final:** no subclass can be created to alter equality behavior.
- **Fixed components:** record fields are assigned once when the object is created.
- **Less boilerplate:** no need to hand-write equals/hashCode/toString where fields are easily missed.
- **Clear semantics:** accessors **tenantId()**, **sourceSystem()**, and **externalNumber()** state the components of the key.
- **Safe as keys:** all components are immutable **String** instances, so key values cannot change after entering a HashMap.

Note: a record only guarantees **shallow immutability**. If a component is an array, list, or mutable object, its internal contents can still change. For example, **record Key(byte[] bytes)** does not copy the array automatically and default array comparison uses reference equality; it should not be used directly as a byte-content key without an appropriate copying/comparison design.

## 5. When a Class Is Needed: Implementing equals/hashCode in Sync

If you do not use a record (for example, needing a class with custom constructors, a different API presentation, or working in an older codebase), design a **final class** with **private final** fields, a constructor validating input, and both **equals()** and **hashCode()** based on the exact same set of fields.

Standalone Java 17 example in **InvoiceKeyClassDemo.java**:

~~~java
import java.util.HashSet;
import java.util.Locale;
import java.util.Objects;
import java.util.Set;

public class InvoiceKeyClassDemo {
    public static final class InvoiceKey {
        private final String tenantId;
        private final String sourceSystem;
        private final String externalNumber;

        public InvoiceKey(
                String tenantId, String sourceSystem, String externalNumber) {
            this.tenantId = normalize(tenantId);
            this.sourceSystem = normalize(sourceSystem);
            this.externalNumber = normalize(externalNumber);
        }

        private static String normalize(String value) {
            Objects.requireNonNull(value, "key component");
            String result = value.strip().toUpperCase(Locale.ROOT);
            if (result.isEmpty()) {
                throw new IllegalArgumentException("Blank key component");
            }
            return result;
        }

        @Override
        public boolean equals(Object obj) {
            if (this == obj) {
                return true;
            }
            if (!(obj instanceof InvoiceKey other)) {
                return false;
            }
            return tenantId.equals(other.tenantId)
                    && sourceSystem.equals(other.sourceSystem)
                    && externalNumber.equals(other.externalNumber);
        }

        @Override
        public int hashCode() {
            return Objects.hash(tenantId, sourceSystem, externalNumber);
        }
    }

    public static void main(String[] args) {
        InvoiceKey a = new InvoiceKey("shop-a", "erp", "inv-0042");
        InvoiceKey b = new InvoiceKey("SHOP-A", "ERP", " INV-0042 ");
        InvoiceKey c = new InvoiceKey("shop-a", "web", "inv-0042");

        Set<InvoiceKey> keys = new HashSet<>();
        keys.add(a);
        keys.add(b);

        System.out.println("equal: " + a.equals(b));
        System.out.println("same hash: " + (a.hashCode() == b.hashCode()));
        System.out.println("other source equal: " + a.equals(c));
        System.out.println("set size: " + keys.size());
    }
}
~~~

~~~bash
javac InvoiceKeyClassDemo.java
java InvoiceKeyClassDemo
~~~

Expected output:

~~~text
equal: true
same hash: true
other source equal: false
set size: 1
~~~

**Objects.hash(...)** computes a hash from multiple components; using this algorithm is not mandatory, but you must use **the exact fields** that appear in **equals()**. For a key composed of immutable fields, there is no need to manually cache the hash unless a need is measured; incorrect caching or caching based on mutable fields easily breaks the contract. Using **instanceof** is safe here because the key class is declared **final**, so there is no subclass to break symmetry.

## 6. Choosing the Right Fields for the Key

Key design must start from **identification rules**, not from the list of fields already present in an entity.

For example, an invoice record might contain:

| Field | Included in InvoiceKey? | Reason |
| --- | --- | --- |
| tenantId | Yes | Same invoice number across tenants represents two different invoices |
| sourceSystem | Yes | ERP and WEB have separate code namespaces |
| externalNumber | Yes | Invoice code within the tenant + source scope |
| status | No | Status NEW/PAID can change |
| totalAmount | No | Total amount can be adjusted |
| updatedAt | No | Modification timestamp is not identity |
| databaseId | Not in business key | Internal identifier, belongs to storage model |
| displayName | No | Display name does not identify the record |

Questions to verify with the domain owner:

1. Can a tuple of values be reused for **two different entities over time**? If yes, do we need a version type/effective date, or should it not be used as an immutable identity?
2. Which values are known immediately at creation time, and which appear only after a workflow completes? A key missing components initially needs a clear strategy.
3. Do tenant, region, provider, environment, or source channel split into independent namespaces?
4. Are values sensitive to case, whitespace, Vietnamese diacritics, Unicode, or leading zeros?
5. Can any field change after the key has been used for lookup, caching, or synchronization?

If a field can legally change while **still representing the same entity**, it should not be used as a stable identity key in a long-lived cache. You can use the technical **id** for identity and let the business key serve as a lookup condition; handle business key changes as index/mapping updates rather than assuming a new entity.

## 7. Normalization and Validation: Defining What "Equal" Means

Good normalization eliminates input differences that carry no business meaning. Bad normalization causes **information loss** or mistakenly merges keys.

| Data | Decision to finalize | Example |
| --- | --- | --- |
| Leading/trailing whitespace | Strip or keep? | " INV-1 " → "INV-1" if whitespace carries no meaning |
| Case sensitivity | Sensitive or insensitive? | "erp" = "ERP" if representing the same source code |
| Unicode | Normalize NFC/NFKC? | Accented characters represented by multiple code sequences |
| Leading zeros | Meaningful or not? | "0007" and "7" may be two distinct codes |
| Null/blank values | Forbidden or meaningful? | Null tenantId usually must be rejected |
| Numeric types | Floating/decimal value or identifier code? | "1.0" and "1.00" may differ when treated as codes |
| Time | Instant or calendar date in a business timezone? | LocalDate differs from Instant |
| String delimiter | Escaping and schema? | ("AB","C") differs from ("A","BC") |

Some technical principles:

- **String.strip()** (Java 11+) removes Unicode whitespace as defined by Java at both ends; **String.trim()** has a different character range. Choose based on actual inputs.
- **toUpperCase(Locale.ROOT)** avoids depending on the machine's default locale, yet can still make two distinct codes identical. Case-insensitivity rules must be decided by the business and align with how other systems process codes.
- For Unicode with multiple equivalent representations, consider **java.text.Normalizer** using NFC when truly needed; do not automatically use NFKC if compatibility folding loses business distinctions.
- With **BigDecimal**, **new BigDecimal("1.0").equals(new BigDecimal("1.00"))** is **false** because the scale differs; **compareTo(...) == 0** is **true**. If a numeric value is a key component, clarify scale semantics before picking a canonical form, avoiding piecemeal fixes to equality.
- For dates/times, use appropriate immutable types (**LocalDate**, **Instant**, ...), and specify the timezone at conversion boundaries rather than using default timezones that differ across machines.
- For nullable keys, decide whether null is valid before writing **equals()**. If there are optional fields, state clearly how absence affects uniqueness; many databases handle **NULL** in UNIQUE constraints differently from Java comparisons.

**Placing validation at key creation time** is beneficial because all valid key objects then follow the same rules. If the app, batch import, and database use three different normalization approaches, deduplication becomes inconsistent. It is best to have a tested normalization policy applied at the boundary and reflected in how data is stored/indexed.

## 8. Why Not Use Arbitrary String Concatenation as a Key?

The following snippet easily causes confusion:

~~~java
// Illustrates an error, not a standalone program:
String key = tenantId + sourceSystem + externalNumber;
~~~

The component tuples **("AB", "C", "D")** and **("A", "BC", "D")** both become **"ABCD"**. Using a simple delimiter can also collide if a component itself contains the delimiter:

~~~java
// Also just an illustration:
String key = tenantId + "|" + sourceSystem + "|" + externalNumber;
~~~

If a field contains the **|** character without escaping/length rules, the string becomes hard to split and can be ambiguous. Use a typed key like **record InvoiceKey(...)** so Java compares **each component**. If a key must be passed over a URL, message, or persistence as a string, design **unambiguous serialization**: per-part lengths, a structured format with a schema, rule-based escaping, and format versioning. That is a key encoding/decoding concern, separate from object equality contracts.

Similarly, do not use **Arrays.toString(...)** or **Objects.hash(...)** as a "unique key code": text representation is not automatically an invariant format, and hashes can collide across different keys.

## 9. Dangerous Bug: Mutating a Key After Putting It into a HashMap

Consider a hypothetical scenario with a key class whose **externalNumber** field can be reassigned:

~~~java
// Code illustrating unsafe behavior:
MutableInvoiceKey key = new MutableInvoiceKey("SHOP-A", "ERP", "INV-1");
map.put(key, invoice);
key.setExternalNumber("INV-2");
Invoice result = map.get(key); // May not be found
~~~

This is **not a standalone Java program**: **MutableInvoiceKey**, **Invoice**, and **map** are merely illustrative types/variables. When a value participating in **hashCode()** changes after **put**, HashMap's old bucket is not automatically rebuilt; lookup may return **null** or encounter unpredictable states. **HashSet** suffers from the exact same issue.

Proper handling:

- Use immutable keys such as a **record** or a **final class** with final fields holding immutable values.
- If the business needs to change a code, create a **new key**; remove the old mapping and add the new mapping in a controlled operation.
- If a cache stores mutable entities, keep an **immutable business key** separate from the entity; do not directly use an entity whose equals/hashCode depends on mutable fields.
- For collection or array contents, perform defensive copying and compare according to actual semantics rather than merely placing the reference in a final field.

A **final field** pointing to a **List** still allows the **List** to be modified if there is no corresponding copy/immutability mechanism.

## 10. HashMap Does Not Replace a Database UNIQUE Constraint

The example in section 4 proves **HashMap** merges equivalent key objects within **a single process**. It does not guarantee that two requests, two JVMs, or two workers will not concurrently write two invoices with the same business key into the database.

If the three normalized columns form the business key, an illustrative SQL design is:

~~~sql
CREATE TABLE invoices (
    id BIGINT PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL,
    source_system VARCHAR(64) NOT NULL,
    external_number VARCHAR(120) NOT NULL,
    status VARCHAR(20) NOT NULL,
    CONSTRAINT uq_invoice_business
        UNIQUE (tenant_id, source_system, external_number)
);
~~~

This is an **illustrative SQL schema**; exact syntax and **id** generation depend on the database engine. The application must store a consistent normalized form or design matching indexes/collations; if the database compares differently from Java, the two layers may yield different uniqueness results.

Reliable deduplication cannot be achieved solely by:

~~~text
1. SELECT to check that it does not exist yet
2. If it does not exist yet, INSERT
~~~

Two concurrent requests can both pass the check and then both INSERT. A UNIQUE constraint in the database enforces deduplication across concurrent requests; the application must handle uniqueness/transaction violations and decide whether to retry, return an error, or return an idempotent response per business requirements. For external ingestion flows, the business key can serve as the basis for **idempotency**, though payload conflicts must still be detected: a matching key does not automatically confirm the entire request payload is valid or identical.

### The JPA/Hibernate case

Do not equate an **InvoiceKey** lookup object with the **equals/hashCode policy of a JPA entity**. An entity may have a technical **id**, proxies, managed/detached states, and a different lifecycle. If choosing a composite primary key with **@EmbeddedId** or **@IdClass**, follow the specific requirements of the JPA provider (key type, constructor, serializable, equality, column mapping). Do not assume any record can be used directly as a JPA embeddable across all versions/providers. Even when the database uses a technical primary key, you can still have **UNIQUE (tenant_id, source_system, external_number)** to preserve business rules.

## 11. Using Composite Keys in HashSet, Caches, and Ordered Structures

With **HashSet**, adding an invoice with an already-present key does not increase the element count. With **Map/HashMap**, **put** with an equal key replaces the value currently bound to that key. This differs from a database: **put** overwriting is normal Map behavior, whereas a duplicate UNIQUE write is typically an error or an intentional handling branch. Do not let cache overwrites hide a business event that ought to report an error.

If using **TreeMap** or **TreeSet**, in addition to equals/hashCode you must define a **Comparator** or **Comparable**. The Comparator must examine the exact same components that determine identity; if **compare(a,b) == 0** for two keys while **!a.equals(b)**, the ordered structure may treat them as a single key and drop elements unexpectedly.

**Illustrative code snippet** using the record defined in section 4:

~~~java
import java.util.Comparator;

Comparator<InvoiceKeyDemo.InvoiceKey> byKey =
        Comparator.comparing(InvoiceKeyDemo.InvoiceKey::tenantId)
                .thenComparing(InvoiceKeyDemo.InvoiceKey::sourceSystem)
                .thenComparing(InvoiceKeyDemo.InvoiceKey::externalNumber);
~~~

This snippet must be placed in a scope allowing variable declarations (such as a method) and in the appropriate package/class path. Since all components are already normalized **String** values, comparing along the same three fields produces zero when the records are equal. If a case-insensitive comparison is applied on raw unnormalized values instead, compatibility with **equals()** must be checked carefully.

With multi-tenant caches, **tenantId** is always part of the lookup when the domain requires tenant isolation; forgetting to include tenant in the cache key can lead to returning the wrong customer's data.

## 12. Testing Strategy for Composite Keys

A minimal test suite should verify both **comparison operations** and **collection behavior**, rather than checking hashes alone:

| Test case | Expected result |
| --- | --- |
| Two identical triplets | equals true, equal hashes |
| Differing only in case/whitespace per policy | equals true after normalization |
| Differing only in tenantId | equals false |
| Differing only in sourceSystem | equals false |
| Differing only in externalNumber | equals false |
| null/blank in a required field | Constructor rejects with a clear exception |
| Add two equivalent keys to HashSet | Single element |
| put two equivalent keys into HashMap | New value replaces old value, key count does not increase |
| Recreate key from persisted data | Looks up the corresponding record |
| Compare with null, different-type object | equals false |
| Concurrent duplicate inserts across requests | Database UNIQUE allows only one business key to exist |

Tests should cover **reflexivity, symmetry, transitivity**, consistency across repeated calls, and ensuring equal objects share the same hash. **Property-based tests** can be added when normalization rules involve many variations of Unicode, whitespace, tenants, and integration sources.

Standalone Java 17 test example requiring no external libraries, saved as **InvoiceKeyChecks.java** in the same directory as **InvoiceKeyDemo.java**:

~~~java
import java.util.HashSet;
import java.util.Set;

public class InvoiceKeyChecks {
    private static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    public static void main(String[] args) {
        var a = new InvoiceKeyDemo.InvoiceKey(
                "shop-a", "erp", "inv-0042");
        var b = new InvoiceKeyDemo.InvoiceKey(
                " SHOP-A ", "ERP", " INV-0042 ");
        var c = new InvoiceKeyDemo.InvoiceKey(
                "shop-a", "erp", "inv-0042");
        var other = new InvoiceKeyDemo.InvoiceKey(
                "shop-b", "erp", "inv-0042");

        check(a.equals(a), "reflexive");
        check(a.equals(b) && b.equals(a), "symmetric");
        check(a.equals(b) && b.equals(c) && a.equals(c),
                "transitive");
        check(a.hashCode() == b.hashCode(), "same hash");
        check(!a.equals(other), "different tenant");
        check(!a.equals(null), "not equal to null");
        check(!a.equals("not an InvoiceKey"), "different type");

        Set<InvoiceKeyDemo.InvoiceKey> set = new HashSet<>();
        set.add(a);
        set.add(b);
        set.add(other);
        check(set.size() == 2, "set identity");

        boolean rejected = false;
        try {
            new InvoiceKeyDemo.InvoiceKey("shop-a", "", "inv-1");
        } catch (IllegalArgumentException expected) {
            rejected = true;
        }
        check(rejected, "reject blank component");

        System.out.println("All composite-key checks passed.");
    }
}
~~~

Run:

~~~bash
javac InvoiceKeyDemo.java InvoiceKeyChecks.java
java InvoiceKeyChecks
~~~

Expected output:

~~~text
All composite-key checks passed.
~~~

These tests confirm basic object and collection behavior. Ensuring real uniqueness during concurrent writes still requires integration tests against a real database, because HashMap tests cannot detect race conditions across transactions.

## 13. Comprehensive Practice: Designing a Key for Integrated Products

An e-commerce marketplace receives SKUs from partners. Different partners may send identical SKUs; each tenant has independent catalogs. A product variant is uniquely identified by **(tenantId, partnerId, sku, variantCode)**.

**Practice requirements:**

1. Explicitly decide which fields are case-sensitive, whether whitespace is stripped, and how to handle missing **variantCode**. Write down your assumptions before coding.
2. Create a **record ProductKey** containing the four fields and validation according to those decisions.
3. Add two key objects differing only in input formatting into a **HashSet**; verify they merge or stay separate according to your rules.
4. Create two keys with the same SKU but different tenant or partner; verify they are always recognized as distinct.
5. Create a **Map<ProductKey, ProductData>** for lookup and explain what happens when calling **put** with two equal keys.
6. Propose **UNIQUE (tenant_id, partner_id, sku, variant_code)** or an alternative constraint reflecting how optional fields are stored. If variantCode allows null, verify the UNIQUE/NULL semantics of the specific database engine.
7. Evaluate whether changing a SKU changes the product's identity or only its lookup key; from that, decide whether a stable internal **id** is needed.

**Solution hints:** prefer normalized, immutable key components; use the equals/hashCode generated by the record; do not put selling price, stock quantity, or display name into the key if they are merely mutable attributes. Enforce uniqueness at the database rather than only inside the JVM. For optional fields, clearly specify whether "no variant" is a single value or an unspecified state requiring separate handling.

## 14. Design Review Checklist

Before putting a composite business key into production, verify:

- **Domain:** does the field combination truly identify exactly one entity within the proper tenant/source/time scope?
- **Stability:** can any field participating in the key change after the key is used?
- **Normalization:** is there a clear policy for case, whitespace, Unicode, null, numbers, and time; is the policy consistent with the database?
- **Equality:** does equals compare each component properly; does hashCode use the same components and satisfy the contract?
- **Immutability:** does the record/final class contain any mutable fields that need copying or redesign?
- **Collections:** do HashMap/HashSet overwrites or key merges require special business handling?
- **Multi-tenancy:** do all lookups/queries/caches include full scoping fields so data is never read across customers?
- **Storage and concurrency:** does the database have an appropriate UNIQUE constraint, and do transactions handle conflicts when two requests create concurrently?
- **System compatibility:** do serialization and versioning formats preserve components without relying on ambiguous delimiters?
- **Testing:** are there cases for each differing field, normalization, null, potential collisions, and concurrent write flows?

## 15. Key Takeaway

**A multi-field business key is an identity model, not merely string concatenation.** First confirm which fields *truly* identify an object within the business scope. Then encapsulate them in an immutable **record** or **final class**, apply consistent validation and normalization, and let **equals()/hashCode()** accurately reflect all key components. Use this key safely in Maps/Sets while letting the database enforce uniqueness constraints when multiple processes or requests write data concurrently.

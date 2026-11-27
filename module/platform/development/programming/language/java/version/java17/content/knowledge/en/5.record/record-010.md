# Inheritance, Instance Field, and Initializer Restrictions in Records (Java 17)

## 1. What Problem Are Records Designed to Solve?

In Java 17, `record` is a way to declare a class for **objects defined primarily by a fixed set of data**. Rather than manually writing fields, constructors, accessors, `equals()`, `hashCode()`, and `toString()`, the developer describes the data via **record components** right on the declaration header.

Example:

~~~java
public record ProductView(String sku, String name, long priceInCents) {
}
~~~

From that declaration, the compiler generates the necessary members, practically equivalent in usage to:

- Three `private final` instance fields: `sku`, `name`, `priceInCents`.
- A canonical constructor accepting the three corresponding parameters.
- Accessors `sku()`, `name()`, `priceInCents()`.
- `equals()` and `hashCode()` based on the components.
- `toString()` showing the record name and components.

~~~java
ProductView p = new ProductView("BK-17", "Java 17", 250_000L);

System.out.println(p.sku());          // BK-17
System.out.println(p.priceInCents());  // 250000
System.out.println(p);
~~~

In applications, records fit DTOs, computation results, snapshot data, value objects, or data branches of a sealed hierarchy when structural constraints align.

**Key point:** A record is not merely a boilerplate-reduction tool. A record has a **constrained state and inheritance model**: it cannot have an arbitrary superclass, cannot declare extra instance fields, and cannot use instance initializer blocks. These are deliberate language design choices to keep the data structure transparent.

Records were standardized in Java 16 (JEP 395), so **they can be used stably in Java 17 without enabling preview**.

## 2. Visualizing a Record's Structure

Consider:

~~~java
public record BookingSnapshot(
        String bookingId,
        int guestCount,
        boolean confirmed
) {
}
~~~

The three names inside the parentheses of the record declaration are **components**. They define the exposed state set in the data model:

~~~text
BookingSnapshot
├── component bookingId: String
│   ├── private final field bookingId
│   └── public accessor bookingId()
├── component guestCount: int
│   ├── private final field guestCount
│   └── public accessor guestCount()
└── component confirmed: boolean
    ├── private final field confirmed
    └── public accessor confirmed()

Canonical constructor:
    BookingSnapshot(String bookingId, int guestCount, boolean confirmed)
~~~

This is a conceptual diagram. You do not need to write the fields, accessors, and constructor manually if the compiler-generated behavior suits you.

A record can contain **methods, static fields, static initializers, custom constructors, and nested types** per Java rules. However, it does not allow extending instance state with extra fields outside the header.

## 3. Inheritance Restrictions: Records Are Final Classes

### 3.1. A Record Is Implicitly `final`

Every record is an **implicitly `final`** class. You cannot declare a subclass extending a record:

~~~java
record Money(long amountInCents) {
}

// INVALID: cannot extend a record.
// class DiscountedMoney extends Money {
//     DiscountedMoney(long amountInCents) {
//         super(amountInCents);
//     }
// }
~~~

This is an important difference from regular classes. A record describes a fixed set of components; if subclasses existed, a subclass could introduce additional instance state and alter the meaning of the data model.

Several consequences follow:

- There is no `abstract record` forcing subclasses to implement members.
- There is no `sealed record` or `non-sealed record` to open further inheritance branches.
- Writing `final record` is unnecessary; the compiler already applies `final`.
- You cannot model a domain by creating a base record and extending it to add more components.

Example of an invalid design:

~~~java
// The idea below is INVALID:
// record Person(String name) {}
// record Employee(String name, long employeeId) extends Person(name) {}
~~~

If `Employee` and `Person` are two independent data types, use separate records or use composition:

~~~java
record PersonName(String value) {
}

record Employee(PersonName personName, long employeeId) {
}
~~~

Composition expresses **Employee has-a PersonName**. It fits well when reusing part of a data structure without introducing invalid inheritance relationships.

### 3.2. A Record Already Inherits `java.lang.Record`

In the class model, every record directly inherits `java.lang.Record` as defined by Java:

~~~text
java.lang.Object
       │
java.lang.Record
       │
BookingSnapshot  (final)
~~~

Therefore, you **cannot** add `extends BaseEntity`, `extends AbstractDto`, or any arbitrary superclass to a record declaration.

~~~java
class BaseEntity {
    private final String id;

    BaseEntity(String id) {
        this.id = id;
    }
}

// INVALID: a record cannot extend BaseEntity.
// record OrderView(String id, long total) extends BaseEntity { }
~~~

Similarly, you cannot write a regular class extending `java.lang.Record` to mimic a record. Extending `java.lang.Record` is reserved exclusively for record declarations under language rules.

If a framework or domain model requires inheriting a specific superclass, choose a **regular class**, or redesign the contract using interfaces and composition. Do not try to force a record into a hierarchy it does not support.

### 3.3. Records Can Still Implement Interfaces

**Not inheriting a class** does not mean records cannot participate in polymorphism. A record can implement one or more interfaces:

~~~java
interface HasId {
    String id();
}

interface Describable {
    String description();
}

record OrderSummary(String id, long totalInCents)
        implements HasId, Describable {

    @Override
    public String description() {
        return "Order " + id + ": " + totalInCents + " cents";
    }
}
~~~

In this example:

- `OrderSummary` remains `final`.
- The compiler-generated `id()` accessor satisfies the `HasId` contract.
- The `description()` method is behavior written by the developer.
- Interfaces still let other code work through an abstract type.

~~~java
HasId item = new OrderSummary("ORD-1", 120_000L);
System.out.println(item.id()); // ORD-1
~~~

A record is a data class that can have **behavior**, not a field-only struct. The rule to keep is that methods cannot silently add instance state outside the component list.

### 3.4. Combining Records with Sealed Interfaces

Java 17 provides `sealed interface`, allowing you to restrict which types may directly implement it. Records are very natural leaf branches since they are already `final`.

~~~java
sealed interface ValidationResult
        permits Accepted, Rejected {
}

record Accepted(String token) implements ValidationResult {
}

record Rejected(String reason) implements ValidationResult {
}
~~~

Diagram:

~~~text
ValidationResult (sealed interface)
├── Accepted (record, implicitly final)
└── Rejected (record, implicitly final)
~~~

Note that `sealed` restricts **direct subtypes** of the root interface/class; `record` prevents **further** inheritance from each branch. Direct permitted subclasses must also satisfy Java 17's module/package rules.

`sealed` is not required for records: a record can simply be an ordinary DTO. Choose `sealed` when the domain genuinely has a controlled set of variants.

## 4. Instance Field Restriction: No Extra Instance Fields Allowed

### 4.1. Components Are the Source of Instance State

Given:

~~~java
record Invoice(String invoiceId, long totalInCents) {
}
~~~

The compiler generates `private final` instance fields corresponding to the two components. You **do not redeclare** them manually, nor **may you add** other instance fields:

~~~java
// INVALID:
// record Invoice(String invoiceId, long totalInCents) {
//     private int discountPercent;          // extra instance field
//     private final String normalizedId;    // extra instance field
// }
~~~

Even when the extra field is `final`, Java still forbids declaring it in the record body. This rule guarantees that a record's instance state is described entirely in its header, never split between header and body.

### 4.2. To Store More Data, Decide Whether It Truly Is a Component

Suppose the payment total is computed from `quantity` and `unitPriceInCents`:

~~~java
record LineItem(String sku, int quantity, long unitPriceInCents) {

    long totalInCents() {
        return Math.multiplyExact((long) quantity, unitPriceInCents);
    }
}
~~~

If `totalInCents` can always be derived from the components, computing it in a method is usually clearer than storing an extra instance field, which records forbid anyway.

Conversely, if the total amount was established as a **domain snapshot** (e.g., incorporating discounts, tax, or rules frozen at transaction time), it can be declared as a meaningful component:

~~~java
record FinalizedLineItem(
        String sku,
        int quantity,
        long unitPriceInCents,
        long finalTotalInCents
) {
}
~~~

Then you must define and enforce appropriate invariants to prevent inconsistent combinations of values. Consider whether `finalTotalInCents` is an independent domain fact or just a derived calculation.

### 4.3. `static` Fields Are Allowed

`static` fields belong to the **record class**, not to any individual instance's state, so declaring them is allowed:

~~~java
import java.util.regex.Pattern;

record ProductCode(String value) {
    private static final Pattern FORMAT =
            Pattern.compile("[A-Z]{2}-[0-9]{4}");

    ProductCode {
        if (value == null || !FORMAT.matcher(value).matches()) {
            throw new IllegalArgumentException("Invalid product code");
        }
    }
}
~~~

`FORMAT` is shared configuration for validating codes, not a component of each `ProductCode`. Two instances `ProductCode("AB-1234")` and `ProductCode("AB-1234")` are still compared by their `value` component, not by `FORMAT`.

A static field *can be mutable* under Java rules, though mutable global state should be avoided unless truly necessary. `private static final` for shared constants or utilities is usually much easier to reason about.

### 4.4. Records Do Not Automatically Guarantee Deep Immutability

Generated component fields are `private final`: references cannot be reassigned after initialization. However, if a reference points to a mutable object, that object's contents can still change.

Example:

~~~java
import java.util.ArrayList;
import java.util.List;

record Team(String name, List<String> members) {
}

List<String> source = new ArrayList<>(List.of("An", "Binh"));
Team team = new Team("Core", source);
source.add("Chi");

System.out.println(team.members()); // [An, Binh, Chi]
~~~

This is a case of a **mutable object shared through a component**, not the record's `members` field being reassigned.

If the contract requires the member list not to change after record creation, copy defensively in the constructor:

~~~java
import java.util.List;
import java.util.Objects;

record SafeTeam(String name, List<String> members) {
    SafeTeam {
        Objects.requireNonNull(name, "name");
        members = List.copyOf(members);
    }
}
~~~

`List.copyOf` creates a list unmodifiable through its API and disallows `null` elements. If elements themselves are mutable objects, the copy is still a **shallow copy**: protect the elements as well if the domain requires deep immutability.

Practical consequence: when implementing value-based `equals()`/`hashCode()`, component data should have stable semantics. Allowing a component to mutate through an aliased reference can break records used as `Map` keys or `Set` elements.

## 5. Initializer Restrictions: No Instance Initializers Allowed

Regular Java classes can contain an **instance initializer block**:

~~~java
class OrdinaryCounter {
    private final int count;

    {
        System.out.println("Initializing instance");
    }

    OrdinaryCounter(int count) {
        this.count = count;
    }
}
~~~

The `{ ... }` block directly inside the class body is an instance initializer. However, **a record declaration cannot declare an instance initializer**.

~~~java
// INVALID:
// record Counter(int count) {
//     {
//         if (count < 0) {
//             throw new IllegalArgumentException("negative count");
//         }
//     }
// }
~~~

To validate or normalize data on every record instantiation, use a **canonical constructor**; usually a **compact canonical constructor** is the most concise option.

~~~java
record Counter(int count) {
    Counter {
        if (count < 0) {
            throw new IllegalArgumentException("negative count");
        }
    }
}
~~~

Here `Counter { ... }` **is not an instance initializer block**. It is the record-specific **compact canonical constructor** syntax. Do not confuse the two constructs just because both use a braced block.

### 5.1. Static Initializers Are Still Allowed

A record can contain a **static initializer block** to set up class-level static data:

~~~java
import java.time.ZoneId;

record OfficeTime(String locationName) {
    private static final ZoneId DISPLAY_ZONE;

    static {
        DISPLAY_ZONE = ZoneId.of("Asia/Ho_Chi_Minh");
    }

    String zoneName() {
        return DISPLAY_ZONE.getId();
    }
}
~~~

`static { ... }` runs when the JVM **initializes the class** per class-initialization rules, not on every `new OfficeTime(...)` call. It differs from a compact constructor:

| Construct | Allowed in a Record? | Timing / Role |
|---|---|---|
| Manually declared instance field | **No** | Instance state must live in record components |
| Instance initializer `{ ... }` | **No** | No mechanism for separate instance initializer blocks |
| Static field `static ...` | **Yes** | Class-level data shared across instances |
| Static initializer `static { ... }` | **Yes** | Initializes static class logic |
| Compact canonical constructor `RecordName { ... }` | **Yes** | Parameter validation/normalization per instance creation |
| Valid normal constructors | **With constraints** | Must obey canonical/delegating constructor rules |

Avoid placing expensive logic, error-prone I/O, or unstable environment dependencies in a static initializer when a clearer initialization mechanism is possible. Failures during class initialization can break every subsequent use of that class in the class loader.

## 6. Canonical Constructor: The Control Point When Creating a Record

### 6.1. Auto-Generated Canonical Constructor

The declaration:

~~~java
record UserId(String value) {
}
~~~

has a **canonical constructor** matching its component list:

~~~java
new UserId("U-100");
~~~

If not defined manually, the compiler provides a constructor taking the exact components in header order.

### 6.2. Compact Canonical Constructor: Validating and Normalizing Values

To validate and normalize a product SKU:

~~~java
import java.util.Locale;
import java.util.Objects;

public record Sku(String value) {

    public Sku {
        Objects.requireNonNull(value, "value");

        // Normalize the parameter before the value is stored in the field.
        value = value.strip().toUpperCase(Locale.ROOT);

        if (!value.matches("[A-Z]{2}-[0-9]{4}")) {
            throw new IllegalArgumentException("SKU must match AB-1234");
        }
    }
}
~~~

In a compact constructor:

1. Component parameters are supplied implicitly; you do not write `(String value)`.
2. You can validate, throw exceptions, or **reassign parameters** to normalize inputs.
3. Once the compact constructor body completes normally, the compiler assigns the component parameter values to the corresponding `private final` fields.

~~~java
Sku a = new Sku(" ab-1234 ");
Sku b = new Sku("AB-1234");

System.out.println(a.value()); // AB-1234
System.out.println(a.equals(b)); // true
~~~

**Important note:** Do not assign directly to a component field inside a compact constructor body:

~~~java
// INVALID:
// record Sku(String value) {
//     Sku {
//         this.value = value.strip(); // compiler assigns fields after the block
//     }
// }
~~~

Normalize the **`value` parameter**, or use a full explicit canonical constructor if you genuinely need explicit control over field assignment.

### 6.3. Explicit Canonical Constructor: Manually Assigning All Component Fields

You can also write out the full canonical constructor with a parameter list matching the component names and types:

~~~java
import java.util.Objects;

public record Coordinates(double latitude, double longitude) {

    public Coordinates(double latitude, double longitude) {
        if (!Double.isFinite(latitude) ||
                latitude < -90 || latitude > 90) {
            throw new IllegalArgumentException("Invalid latitude");
        }
        if (!Double.isFinite(longitude) ||
                longitude < -180 || longitude > 180) {
            throw new IllegalArgumentException("Invalid longitude");
        }

        this.latitude = latitude;
        this.longitude = longitude;
    }
}
~~~

Unlike a compact constructor, when writing an explicit canonical constructor you must ensure **all component fields are properly assigned before the constructor finishes normally**. The compiler does not insert trailing assignments as in a compact constructor.

The canonical constructor of a `public record` must also have appropriate visibility; when declaring a `public record`, declare its canonical constructor `public`. It is part of the public type's instantiation contract.

In most cases requiring only validation or normalization, a compact constructor is shorter and avoids repeating parameter lists.

### 6.4. Auxiliary Constructors Must Call Another Constructor of the Same Record

A record can still have **overloaded constructors** to supply default values:

~~~java
record Ticket(String code, int seatCount) {

    Ticket {
        if (code == null || code.isBlank()) {
            throw new IllegalArgumentException("Invalid ticket code");
        }
        if (seatCount < 1) {
            throw new IllegalArgumentException("Seat count must be positive");
        }
    }

    Ticket(String code) {
        this(code, 1);
    }
}
~~~

`Ticket(String code)` **is not the canonical constructor**. It must call another constructor of the record via `this(...)` under Java 17 rules; here it delegates to the canonical constructor.

As a result, whether calling `new Ticket("T1")` or `new Ticket("T1", 3)`, data passes through the record's primary validation path.

Do not write an auxiliary constructor that tries to assign fields directly:

~~~java
// INVALID:
// record Ticket(String code, int seatCount) {
//     Ticket(String code) {
//         this.code = code;
//         this.seatCount = 1;
//     }
// }
~~~

**Distinction:** Java 17 requires auxiliary constructors to delegate via `this(...)`; do not apply preview constructor rules/features from later Java releases in this lesson.

## 7. Accessors and Methods: Behavior Is Allowed, State Model Cannot Change

Default accessors share the exact component name, **without a `get` prefix**:

~~~java
record Price(long cents) {
}

Price price = new Price(10_000);
System.out.println(price.cents());
~~~

You can add other methods:

~~~java
record Rectangle(double width, double height) {
    Rectangle {
        if (!(width > 0.0) || !(height > 0.0) ||
                !Double.isFinite(width) || !Double.isFinite(height)) {
            throw new IllegalArgumentException("Invalid dimensions");
        }
    }

    double area() {
        return width * height;
    }

    boolean isSquare() {
        return Double.compare(width, height) == 0;
    }
}
~~~

Both methods compute directly from components; no extra `area` or `isSquare` fields are needed.

### 7.1. Explicit Accessors Can Be Written to Protect Data

For array components, copy both on input and on output to avoid external mutation:

~~~java
import java.util.Objects;

record BytePayload(byte[] data) {
    BytePayload {
        Objects.requireNonNull(data, "data");
        data = data.clone();
    }

    @Override
    public byte[] data() {
        return data.clone();
    }
}
~~~

Now callers cannot modify the array stored inside the record via either the input reference or the accessor.

Even so, **an array component has `equals`/`hashCode` semantics that warrant attention**: a record's default `equals()`/`hashCode()` do not automatically compare `byte[]` contents using `Arrays.equals`/`Arrays.hashCode`. If business rules require content equality for arrays, design it explicitly (for instance, overriding `equals` and `hashCode` consistently, or using another suitable data type).

Additionally, an explicit accessor must preserve the record's contract: same component name, matching return type, `public` visibility, and not returning values contradicting the record's state. Do not override an accessor to return random or time-varying values.

### 7.2. No Compiler-Generated Setters

~~~java
record UserProfile(String displayName) {
}

UserProfile first = new UserProfile("An");

// INVALID:
// first.displayName = "Binh";
// first.setDisplayName("Binh");

UserProfile changed = new UserProfile("Binh");
~~~

Instead of mutating an instance's state, you create a new object for a different state. If the domain genuinely requires a continuously mutating internal lifecycle, a class with managed state may fit better than a record.

## 8. Comprehensive Java 17 Example: No Class Inheritance, No Extra Instance Fields, No Instance Initializers

This example places all code in **RecordConstraintsDemo.java**. It models a booking snapshot requiring:

- A booking ID and a list of guests.
- Validation of the ID upon object creation.
- A guest list unmodifiable externally after creating the snapshot.
- Guest count exposed via a computed method, without adding an extra instance field.
- A shared validation pattern in a static field.
- An auxiliary constructor supplying a default timestamp.
- Participation in a sealed interface representing processing outcomes.

~~~java
import java.time.Instant;
import java.time.ZoneId;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import java.util.regex.Pattern;

public class RecordConstraintsDemo {

    sealed interface BookingOutcome permits BookingSnapshot, BookingRejected {
    }

    public record BookingSnapshot(
            String bookingId,
            List<String> guests,
            Instant createdAt
    ) implements BookingOutcome {

        // Static field: shared across instances, not part of per-snapshot state.
        private static final Pattern ID_PATTERN =
                Pattern.compile("BK-[0-9]+");

        private static final ZoneId DISPLAY_ZONE;

        // Static initializer: runs when the class is initialized.
        static {
            DISPLAY_ZONE = ZoneId.of("Asia/Ho_Chi_Minh");
        }

        // Compact canonical constructor: validates and copies data.
        public BookingSnapshot {
            Objects.requireNonNull(bookingId, "bookingId");
            Objects.requireNonNull(guests, "guests");
            Objects.requireNonNull(createdAt, "createdAt");

            if (!ID_PATTERN.matcher(bookingId).matches()) {
                throw new IllegalArgumentException("Code must match BK-123");
            }

            guests = List.copyOf(guests);
            if (guests.isEmpty() || guests.stream().anyMatch(String::isBlank)) {
                throw new IllegalArgumentException("Invalid guest list");
            }
        }

        // Auxiliary constructor delegating to canonical constructor.
        public BookingSnapshot(String bookingId, List<String> guests) {
            this(bookingId, guests, Instant.now());
        }

        // Method derived from components; no extra instance field needed.
        public int guestCount() {
            return guests.size();
        }

        public String formattedCreatedAt() {
            return createdAt.atZone(DISPLAY_ZONE).toString();
        }
    }

    public record BookingRejected(String reason) implements BookingOutcome {
        public BookingRejected {
            Objects.requireNonNull(reason, "reason");
            if (reason.isBlank()) {
                throw new IllegalArgumentException("Reason must not be blank");
            }
        }
    }

    static String describe(BookingOutcome outcome) {
        if (outcome instanceof BookingSnapshot snapshot) {
            return snapshot.bookingId() + ": " +
                    snapshot.guestCount() + " guests";
        }
        if (outcome instanceof BookingRejected rejected) {
            return "Rejected: " + rejected.reason();
        }
        throw new IllegalStateException("Unhandled outcome");
    }

    public static void main(String[] args) {
        List<String> source = new ArrayList<>(List.of("An", "Binh"));
        Instant time = Instant.parse("2026-11-15T14:00:00Z");

        BookingSnapshot first =
                new BookingSnapshot("BK-123", source, time);

        // Try mutating the original list after creating the snapshot.
        source.add("Chi");

        BookingSnapshot sameValues = new BookingSnapshot(
                "BK-123", List.of("An", "Binh"), time
        );

        System.out.println(first.guests());
        System.out.println(first.guestCount());
        System.out.println(first.equals(sameValues));
        System.out.println(describe(first));
        System.out.println(describe(new BookingRejected("Fully booked")));
        System.out.println(first.formattedCreatedAt());
    }
}
~~~

Run from the directory containing the file with JDK 17:

~~~shell
java -version
javac --release 17 RecordConstraintsDemo.java
java RecordConstraintsDemo
~~~

Illustrative output:

~~~text
[An, Binh]
2
true
BK-123: 2 guests
Rejected: Fully booked
2026-11-15T21:00+07:00[Asia/Ho_Chi_Minh]
~~~

What to observe:

1. After adding `"Chi"` to `source`, the `guests` list in `first` remains `["An", "Binh"]` thanks to `List.copyOf`.
2. `guestCount()` computes from `guests` on each call; no `private int guestCount` is needed.
3. Two snapshots with equal components per contract are equal; `List` compares contents via `equals`.
4. `ID_PATTERN` and `DISPLAY_ZONE` are static members and do not participate in instance `equals`/`hashCode`.
5. The constructor validates each record on creation; the static initializer does not replace per-instance input checks.
6. `BookingSnapshot` implements `BookingOutcome` while remaining a `final` class.
7. `describe` uses pattern matching for `instanceof`, which is stable in Java 17. Pattern matching for `switch` was not stable in Java 17 and is not needed here.

## 9. Distinguishing Records from Regular Immutable Classes

A hand-written class allows more varied internal structure than a record:

~~~java
import java.util.Objects;

final class AccountLabel {
    private final String value;
    private final int lengthCache;

    AccountLabel(String value) {
        this.value = Objects.requireNonNull(value).strip();
        this.lengthCache = this.value.length();
    }

    String value() {
        return value;
    }

    int length() {
        return lengthCache;
    }
}
~~~

A class can hold a precomputed instance field and store `lengthCache`. A record cannot add a similar field outside its component list. However, that **does not mean records are inferior** in every case: `length()` can simply call `value.length()`, avoiding redundant state storage.

| Criterion | Record | Regular Class |
|---|---|---|
| Instance field set | Defined by components | Fields designed manually |
| Arbitrary class inheritance | No; already extends `java.lang.Record` | Can extend a suitable class |
| Subclassed by other classes | No; implicitly final | Depends on `final`, `sealed`, and other rules |
| Implements interfaces | Yes | Yes |
| Instance initializer blocks | No | Yes |
| Static fields/blocks | Yes | Yes |
| Constructor validation | Yes, typically using compact constructor | Yes, regular constructor |
| Accessors | Generated by component name; can be declared explicitly | Defined manually |
| `equals`, `hashCode`, `toString` | Auto-generated from components unless explicitly declared | Must write manually or use tools |
| Referenced mutable data | Can exist; needs defensive copying when appropriate | Same, depends on design |
| Best suited for | Value carrier/DTO/snapshot with clear state set | Objects needing flexible internal state or class inheritance |

Do not force multi-level class inheritance out of OOP habit, nor convert every class into a record just to trim boilerplate. An entity with business-mutating state, requiring ORM proxies, or needing to inherit a base class may need a regular class.

## 10. Practical Limitations Encountered in Real Applications

### 10.1. Records Have No JavaBean Setters or Default No-Arg Constructor

~~~java
record UserView(long id, String name) {
}
~~~

The generated constructor accepts `id` and `name`; accessors are `id()` and `name()`, not `getId()` and `getName()` by default. The compiler also does not generate a no-arg constructor `UserView()`.

Therefore, when using frameworks or mapping tools, verify whether that version **supports record construction and accessors**, instead of assuming every JavaBean-based mechanism works identically to a traditional class.

### 10.2. Records Are Usually Unsuitable as JPA Entities

JPA entities typically require an ORM-managed lifecycle, inheritance/proxying capability, and specific constructor/state-field conventions. Because records are `final`, lack a default no-arg constructor, and have `final` component fields, records are usually better suited for **DTOs/projections** or read-only data when supported by the framework.

~~~text
Database row
    ↓ (ORM entity is typically a class)
OrderEntity
    ↓ mapped to DTO
OrderResponse (record)
    ↓ returned to API client
~~~

This separation keeps data lifecycle responsibilities in the entity while the record carries a cleanly structured snapshot out of the domain/service layer.

### 10.3. Cannot Store Hidden Instance Caches in a Record

For example, suppose a `Report` performs an expensive sum. You might wish for:

~~~java
// INVALID:
// record Report(List<Long> numbers) {
//     private Long cachedTotal;
// }
~~~

Options to consider:

- Recompute in a method if the data is small and cost is low.
- Compute at creation time and include the result as a component when it is a meaningful part of the snapshot.
- Extract a service/cache keyed appropriately to manage expensive computations.
- Use a class when the object itself needs cached state with its own lifecycle.

Do not blindly place a `static Map<Report, Long>` inside a record: global caches introduce memory, concurrency, lifecycle, and invalidation issues; only use one with an explicit design.

### 10.4. Do Not Confuse `final` Fields with Immutability of the Whole Object Graph

~~~java
import java.util.Date;

record LegacyTimestamp(Date value) {
}
~~~

`Date` is mutable, so the record above is not deeply immutable. In modern Java code, prefer an appropriate `java.time` type such as `Instant` instead of mutable date types in new models:

~~~java
import java.time.Instant;

record EventTime(Instant instant) {
}
~~~

Choosing the right data types is usually better than wrapping mutable objects in a record and hoping they become immutable.

## 11. Table of Valid and Invalid Syntax in Java 17

| Declaration or Operation | Valid? | Reason |
|---|---|---|
| `record Point(int x, int y) {}` | Yes | Normal record |
| `record Point(int x, int y) implements Printable {}` | Yes if interface matches | Records can implement interfaces |
| `class Child extends Point {}` | No | Records are implicitly final |
| `record Child(int x) extends Parent {}` | No | Records cannot have arbitrary superclasses |
| `abstract record Item(int id) {}` | No | Records cannot be abstract |
| `sealed record Item(int id) {}` | No | Records cannot be sealed |
| `record R(int n) { int extra; }` | No | Cannot declare extra instance fields |
| `record R(int n) { static int count; }` | Yes | Static fields do not belong to instance state |
| `record R(int n) { { ... } }` | No | Instance initializers are forbidden |
| `record R(int n) { static { ... } }` | Yes if block body is valid | Static initializers are allowed |
| `record R(int n) { R { ... } }` | Yes if body is valid | Compact canonical constructor |
| `record R(int n) { R(int n) { this.n = n; } }` | Yes | Explicit canonical constructor assigning fields |
| `record R(int n) { R() { this(0); } }` | Yes | Auxiliary constructor delegating to canonical |
| `record R(int n) { int doubleN() { return n * 2; } }` | Yes | Instance method declaring no new fields |

In the table, `{ ... }` is placeholder notation; if copying literally, replace with valid Java code.

## 12. Common Misconceptions

**"A record is just a normal class with IDE-generated getters and setters."**  
No. A record is language syntax with a defined component set, constructor, and methods generated by the compiler under a specific contract; records have no default setters.

**"Records are final, so they cannot implement interfaces."**  
False. `final` prevents a class from being subclassed, not from implementing interfaces.

**"Records have no fields at all."**  
False. Records have `private final` instance fields generated from components. What is forbidden is **manually declaring extra** instance fields in the body.

**"Marking an extra field `final` makes it allowed."**  
False. The rule forbidding extra instance fields applies even when the field is `final`.

**"No blocks are allowed inside a record."**  
False. Instance initializers are forbidden, yet **static initializers** and **constructor bodies** (especially compact canonical constructors) are allowed.

**"A compact constructor is just an instance initializer block by another name."**  
False. A compact constructor acts as a constructor and includes implicit assignment to component fields after its body finishes normally.

**"Having a `List<String>` component means the record is always immutable."**  
False. `final` only protects the reference stored in the field; you must defend against mutable contents.

**"With records, every derived attribute must become a component."**  
No. Derived values can be computed from components in methods. Only store a derived attribute as a component if it belongs in the data contract.

**"For a record to be part of a sealed hierarchy, the record itself must be sealed."**  
No. A record is `final`, so it can serve directly as a permitted subtype of a sealed interface/class when inheritance rules allow.

## 13. Practice Exercises

### Exercise 1 — Evaluate Syntax

Inspect the following declarations and predict which ones the Java 17 compiler accepts:

~~~java
record A(int id) {
    static final int MIN_ID = 1;
}

// Adding instance fields is forbidden:
// record B(int id) {
//     private final String label = "default";
// }

record C(int id) {
    C {
        if (id < 1) {
            throw new IllegalArgumentException("id must be positive");
        }
    }
}

record D(int id) {
    static {
        System.out.println("Initializing class D");
    }
}
~~~

Explain why `A`, `C`, and `D` are valid while `B` is invalid; identify when each corresponding block executes.

### Exercise 2 — Design an Immutable Snapshot

Design record `CourseSnapshot` with:

- `courseId: String`, must not be blank.
- `title: String`, must not be blank.
- `lessons: List<String>`, non-null, non-empty, no null elements.
- `publishedAt: Instant`, non-null.

Use a compact constructor, `List.copyOf`, and a `lessonCount()` method. After creating the record from an `ArrayList`, mutate the original list to verify the snapshot is unaffected.

Try calling `snapshot.lessons().add("New lesson")` and explain why modifying the list is disallowed.

### Exercise 3 — Replace Inheritance with Composition

You are considering `record Manager extends Employee` to add `teamSize`. Redesign it using:

~~~java
record EmployeeIdentity(String employeeId, String displayName) {
}

record ManagerSnapshot(EmployeeIdentity identity, int teamSize) {
}
~~~

Add validation and a `summary()` method. Explain which part is a **has-a** relationship and why `extends` cannot be used between two records.

### Exercise 4 — Auxiliary Constructors

Write record `Money(String currency, long amountInMinorUnit)` with:

- A compact constructor validating `currency` per application rules and ensuring the amount is non-negative.
- An auxiliary constructor `Money(long amountInMinorUnit)` using a domain-defined default currency code, delegating with `this(...)`.
- A method `isZero()` computed from `amountInMinorUnit`.

Do not declare extra instance fields or use instance initializers. State why an auxiliary constructor cannot assign fields directly.

### Exercise 5 — Records in a Sealed Hierarchy

Design:

~~~text
ApiResult (sealed interface)
├── Ok (record)
└── Error (record)
~~~

Each branch has appropriate components. Write a handling method using `instanceof` patterns in Java 17 and try writing a third implementation not listed in `permits`. Explain the compiler error. Then consider whether an open interface should be used instead if third parties must define their own result variants.

## 14. Self-Check Questions

1. Why is a record considered `final` even without the `final` keyword in its declaration?
2. Which class does a record directly inherit? Can you write `extends BaseDto`?
3. Can a record implement interfaces or serve as a permitted subtype of a sealed interface?
4. Why is `private final int extra` still forbidden when declared as an instance field in a record body?
5. Should a value derived from components become a method or an additional component? What decides?
6. What is the difference between `{ ... }`, `static { ... }`, and `RecordName { ... }` inside a record declaration?
7. In a compact constructor, why is reassigning a parameter allowed while assigning a component field directly is forbidden?
8. What must an explicit canonical constructor do so that all component fields are initialized?
9. How must an auxiliary constructor of a record delegate in Java 17?
10. Why can a record containing a `List` or array still be affected by mutable data?
11. Why might a record's default `equals()` with an array component fail to match business content-comparison semantics?
12. When is a regular class a better choice than a record?

## 15. References

- [OpenJDK JEP 395 — Records](https://openjdk.org/jeps/395): design goals and record semantics standardized in Java 16.
- [Java Language Specification — Java SE 17, §8.10 Record Classes](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10): official rules on inheritance, components, fields, initializers, constructors, and accessors.
- [Java SE 17 API — `java.lang.Record`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Record.html): base class of all records.
- [dev.java — Records](https://dev.java/learn/records/): guide to using records in modern Java.

A record is a solid choice when you want instance state **completely declared through components**, clear data contracts, and no need for class-inheritance extensibility. Use constructors for validation or normalization, static fields or static initializers for shared data, and methods for calculations based on components. Understanding these three restrictions helps you use records in harmony with Java 17's design and avoid mechanically converting traditional classes.

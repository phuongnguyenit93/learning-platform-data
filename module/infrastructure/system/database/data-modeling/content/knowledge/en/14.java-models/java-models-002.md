# Creating Value Objects for Identifiers, Money, Quantities, and Time Windows

In a business system, `UUID`, `BigDecimal`, `String`, and `Instant` are useful Java types, yet they do not express enough about **what the value means**. Even though both are `UUID`s, an order ID must never be accidentally passed as a customer ID. Even though both are `BigDecimal`s, an amount of 100 USD cannot be added directly to 100 VND, nor can 5 kg be added to 5 meters. Even with two timestamps, a reservation interval requires clear rules about endpoints and time zones.

**Value objects** bring those meanings and constraints directly into the Java model. This lesson belongs to the **Java Models** chapter of the **DATABASE_DATA_MODELING** module: building the skill of turning business requirements into entities, relationships, constraints, keys, indexes, and physical schemas; and comparing how to model relational, document, graph, and analytical data. We will design four groups of value objects and examine how to preserve their semantics across APIs and databases.

## 1. What Is a Value Object and How Does It Differ from an Entity?

A value object is defined by **the values and meaning of its internal components**, rather than an independent identity of the object itself. Two objects representing the same 20.00 USD are considered equal in value, regardless of where they were constructed. Conversely, two orders with the same total amount and creation date remain two distinct entities if they carry different order IDs.

| Aspect | Value Object | Entity |
| --- | --- | --- |
| Equality definition | Equal when meaningful components are equal | Same business identity, even when attributes change |
| Lifecycle | Can be recreated and replaced with a new value | Has an identity and lifecycle that must be tracked |
| Mutation | Immutability preferred; operations produce a new value | State changes through controlled behavior |
| Examples | `OrderId`, `Money`, `Quantity`, `TimeWindow` | `Order`, `Customer`, `Reservation` |
| Data mapping | Typically flattened into one or more columns/attributes of an entity | Typically tied to a primary key and relationships between entities |

Note: **`OrderId` is a value object**, whereas **`Order` is an entity**. The order ID is a value representing the entity's identity; the Java object holding the ID does not have an independent lifecycle of its own. A value object can be stored alongside an entity or transferred over an API without needing its own table and primary key.

Good designs typically exhibit these properties:

1. **Clear semantics:** type and field names describe the value domain, units, and usage boundaries.
2. **Valid upon creation:** constructors/factories reject nonsensical values; never construct a "temporarily invalid" object expecting another layer to fix it.
3. **Immutable:** no setters; operations such as `plus`, `multiply`, or `shift` return a new value.
4. **Value-based equality:** normalization ensures two equivalent representations compare equal properly.
5. **Storage compatibility:** provides explicit conversions to SQL columns, JSON, or other representations while preserving constraints.

Java 17+ offers `record`s, which are very convenient for value objects because they generate accessors, a canonical constructor, `equals`/`hashCode`, and `toString`. However, a `record` provides **only shallow immutability**; components holding lists, arrays, or mutable objects still require defensive copying. When custom creation policies, performance, or framework compatibility demand it, you can use a `final class` with `private final` fields and implement equality yourself.

## 2. From Business Requirements to Four Value Types

Suppose an application receives a reservation and pricing request:

- An order and a customer both have UUID identifiers, but they must not be passed in place of one another.
- A price requires **an amount and a currency**, with a specified rounding policy.
- A quantity requires **a numeric value and a unit of measure**, and quantities of different dimensions must not be added.
- A reservation slot has **a start time and an end time**, must be non-empty, and must support overlap checks.

| Business Concept | Weak Representation | Proposed Value Object | Typical Invariants |
| --- | --- | --- | --- |
| Order ID | `String` or `UUID` reused everywhere | `OrderId(UUID)` | Non-`null` UUID; different ID types are not interchangeable |
| Monetary amount | Standalone `double` or `BigDecimal` | `Money(BigDecimal, Currency)` | Only add same currency; decimal scale matches policy |
| Quantity | `double quantity` | `Quantity(BigDecimal, Unit)` | Mandatory unit; explicit rules for negative/zero quantities |
| Time window | Two separate `LocalDateTime` values | `TimeWindow(Instant, Instant)` | Start strictly before end; consistent endpoint inclusion rule |

In this chapter, record field names are part of the semantics: `startInclusive` and `endExclusive` convey far more information than ambiguous `from` and `to`.

## 3. Complete, Runnable Java 17+ Example

Save the following code to `ValueObjectDemo.java`. The records are nested inside the same class for easy demonstration. In a real project, each type can live in its own file under the appropriate domain package.

```java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.Duration;
import java.time.Instant;
import java.util.Currency;
import java.util.Objects;
import java.util.UUID;

public final class ValueObjectDemo {

    record OrderId(UUID value) {
        public OrderId {
            Objects.requireNonNull(value, "value");
        }

        static OrderId parse(String raw) {
            return new OrderId(UUID.fromString(raw));
        }
    }

    record CustomerId(UUID value) {
        public CustomerId {
            Objects.requireNonNull(value, "value");
        }
    }

    record Money(BigDecimal amount, Currency currency) {
        public Money {
            Objects.requireNonNull(amount, "amount");
            Objects.requireNonNull(currency, "currency");

            int fractionDigits = currency.getDefaultFractionDigits();
            if (fractionDigits < 0) {
                throw new IllegalArgumentException(
                    "Currency has no defined minor unit: " + currency
                );
            }
            // Normalize scale; do not round automatically on input.
            amount = amount.setScale(
                fractionDigits, RoundingMode.UNNECESSARY
            );
        }

        static Money of(String amount, String currencyCode) {
            return new Money(
                new BigDecimal(amount),
                Currency.getInstance(currencyCode)
            );
        }

        Money plus(Money other) {
            Objects.requireNonNull(other, "other");
            if (!currency.equals(other.currency)) {
                throw new IllegalArgumentException(
                    "Cannot add different currencies"
                );
            }
            return new Money(amount.add(other.amount), currency);
        }

        Money times(BigDecimal factor, RoundingMode rounding) {
            Objects.requireNonNull(factor, "factor");
            Objects.requireNonNull(rounding, "rounding");
            BigDecimal calculated = amount.multiply(factor);
            int scale = currency.getDefaultFractionDigits();
            return new Money(calculated.setScale(scale, rounding), currency);
        }
    }

    enum Unit {
        PIECE, KILOGRAM, METER
    }

    record Quantity(BigDecimal value, Unit unit) {
        public Quantity {
            Objects.requireNonNull(value, "value");
            Objects.requireNonNull(unit, "unit");
            if (value.signum() < 0) {
                throw new IllegalArgumentException(
                    "Quantity must not be negative"
                );
            }

            // 2.500 and 2.5 represent the same quantity.
            value = value.signum() == 0
                ? BigDecimal.ZERO
                : value.stripTrailingZeros();
        }

        static Quantity of(String raw, Unit unit) {
            return new Quantity(new BigDecimal(raw), unit);
        }

        Quantity plus(Quantity other) {
            Objects.requireNonNull(other, "other");
            if (unit != other.unit) {
                throw new IllegalArgumentException(
                    "Cannot add different measurement units"
                );
            }
            return new Quantity(value.add(other.value), unit);
        }
    }

    record TimeWindow(Instant startInclusive, Instant endExclusive) {
        public TimeWindow {
            Objects.requireNonNull(startInclusive, "startInclusive");
            Objects.requireNonNull(endExclusive, "endExclusive");
            if (!startInclusive.isBefore(endExclusive)) {
                throw new IllegalArgumentException(
                    "Start must be earlier than end"
                );
            }
        }

        boolean contains(Instant instant) {
            Objects.requireNonNull(instant, "instant");
            return !instant.isBefore(startInclusive)
                && instant.isBefore(endExclusive);
        }

        boolean overlaps(TimeWindow other) {
            Objects.requireNonNull(other, "other");
            return startInclusive.isBefore(other.endExclusive)
                && other.startInclusive.isBefore(endExclusive);
        }

        Duration elapsed() {
            return Duration.between(startInclusive, endExclusive);
        }
    }

    public static void main(String[] args) {
        UUID rawId = UUID.randomUUID();
        OrderId orderId = new OrderId(rawId);
        CustomerId customerId = new CustomerId(rawId);
        // Despite sharing the same UUID, OrderId and CustomerId are two distinct types.
        System.out.println(orderId.value().equals(customerId.value())); // true

        Money base = Money.of("19.90", "USD");
        Money fee = Money.of("0.10", "USD");
        Money total = base.plus(fee);
        System.out.println(total.amount());                              // 20.00
        System.out.println(Money.of("10.0", "USD")
            .equals(Money.of("10.00", "USD")));                             // true

        Quantity cargo = Quantity.of("2.500", Unit.KILOGRAM);
        Quantity extra = Quantity.of("0.5", Unit.KILOGRAM);
        System.out.println(cargo.plus(extra).value());                   // 3

        TimeWindow first = new TimeWindow(
            Instant.parse("2026-11-22T01:00:00Z"),
            Instant.parse("2026-11-22T02:00:00Z")
        );
        TimeWindow next = new TimeWindow(
            first.endExclusive(),
            Instant.parse("2026-11-22T03:00:00Z")
        );
        System.out.println(first.overlaps(next));                        // false
        System.out.println(first.elapsed().toMinutes());                  // 60
    }
}
```

**Why do constructors matter?** If the application could construct `new TimeWindow(end, start)` or `new Money(amount, null)` and only validate later in the service layer, invalid objects could leak into other layers. A record's canonical constructor turns constraints into mandatory checks at every direct instantiation site, including objects produced by calculations.

The `plus` methods always return **new objects**. Calling `base.plus(fee)` does not mutate `base`. This immutability makes passing values across methods and processing threads much more predictable.

## 4. Identifier Objects: Preventing Key Mix-Ups Without Losing Identity

A common bug is declaring:

```java
void transferOrder(UUID orderId, UUID customerId) { /* ... */ }
```

The compiler cannot catch a call where the two UUIDs are swapped. By using two distinct types:

```java
final class TransferService {
    void transferOrder(ValueObjectDemo.OrderId orderId,
                       ValueObjectDemo.CustomerId customerId) {
        /* ... */
    }
}
```

Then a `CustomerId` cannot be passed to an `OrderId` parameter. The types in the example are placed in the same class/package to illustrate syntax; in real applications, design appropriate visibility and package structure.

**Rules for identifiers:**

- Wrap primitives with domain-specific types: `OrderId`, `CustomerId`, `ReservationId`. Do not reuse a generic `Id` class across all entity types if doing so erases type distinction.
- Distinguish **internal identifiers** from **display codes**: a UUID can serve as the primary key, while an order code like `ORD-2026-000042` can be a separate business field requiring uniqueness. Display code formats can change without needing to change keys.
- A `parse` factory acts as the conversion boundary from API strings to strongly typed values. Handle invalid UUID strings at the boundary with an appropriate message; do not leak low-level exceptions into public error messages.
- Two `new OrderId(sameUuid)` value objects are equal via `equals`; however, `OrderId` and `CustomerId` belong to two different domains even when wrapping the same UUID.
- An identifier is not a password or access permission: knowing an ID must not automatically grant read/write access to data. Authorization checks remain mandatory at the application layer.

In a relational database, the primary key `orders.id UUID PRIMARY KEY` guarantees uniqueness, while foreign keys in related tables guarantee valid references. The Java compiler prevents mixing up ID types in code, but **cannot replace foreign keys and unique constraints** in the database.

## 5. Money Objects: Amount, Currency, and Rounding

`Money` needs at least two components: **`amount`** and **`currency`**. Never write `Money(100)` and implicitly assume USD or VND. Each business flow must clarify whether an amount represents a price, tax, discount, balance, refund, or exchange rate.

### Choosing `BigDecimal` Over Binary Floating Point

`double` cannot accurately represent many decimal fractions; chained calculations can introduce unwanted rounding errors. For monetary amounts, construct from strings or controlled decimal representations:

```java
import java.math.BigDecimal;

final class DecimalExample {
    void illustrate() {
        BigDecimal correct = new BigDecimal("0.10");
        // The approach below retains the binary approximation of double:
        BigDecimal risky = new BigDecimal(0.10);
    }
}
```

Addition and subtraction can be performed directly with `BigDecimal`; division and multiplication producing extra digits require an explicit rounding policy. For example, `Money.times(factor, RoundingMode.HALF_EVEN)` forces the caller to specify a rounding rule wherever a calculation may lose precision.

### Normalization and Equality

`BigDecimal("10.0").equals(BigDecimal("10.00"))` returns `false` because `equals` considers **scale**, even though `compareTo` considers them equal. Because `record` generates `equals` from its components, unnormalized monetary values representing the same amount could compare unequal.

The `Money` example uses `currency.getDefaultFractionDigits()` to normalize the currency's fractional digits:

| Input Value | Currency | Result in Example Model |
| --- | --- | --- |
| `"10.0"` | USD (2 fractional digits) | `10.00` |
| `"10.00"` | USD | `10.00`; equal to the value above |
| `"10.001"` | USD | Rejected because rounding is required without a policy |
| `"2500"` | VND (0 fractional digits) | `2500` |
| `"2500.5"` | VND | Rejected under this policy |

This is an **illustrative policy for settled payment amounts**. In practice, unit prices by weight, electricity tariffs, tax rates, or exchange rates may require more decimal places than the smallest currency unit. In those cases, define separate types/classes such as `UnitPrice`, `ExchangeRate`, or `TaxRate` that retain appropriate internal precision and only round at designated business steps. Do not apply a single scale rule to every money-related number.

### Context-Dependent Invariants

- **Never add different currencies:** `Money(10 USD) + Money(10 EUR)` must fail or go through an explicit conversion workflow. Conversion requires an exchange rate, source, effective timestamp, and rounding policy; you cannot conjure a "default" rate from two currency codes alone.
- **Do not block negative amounts in every `Money` by default:** negative amounts can be valid for adjustment entries or refunds. However, `ProductPrice` and `AmountToPay` may require their own `>= 0` constraint.
- **Distinguish calculation from allocation:** splitting 10.00 USD among 3 people requires a remainder-cent allocation rule; merely rounding three independent quotients can yield a sum different from 10.00 USD. The minor currency unit must be preserved under reconciliation policies.
- **Do not use enum `ordinal` or arbitrary integers to represent currencies:** store ISO 4217 codes or stable domain codes as required and validate against supported codes.

## 6. Quantity Objects: Numeric Values Always Paired with Units

`Quantity(BigDecimal, Unit)` expresses that **3** only makes sense alongside a unit. Operations are valid only when both operands share the same unit and meaning.

```text
2.5 KILOGRAM + 0.5 KILOGRAM = 3 KILOGRAM
2.5 KILOGRAM + 0.5 METER    = invalid
```

In the example, `Quantity.plus` only adds when `unit` matches. If the system also supports `GRAM`, performing `500 GRAM + 1 KILOGRAM` must pass through a **controlled conversion function** after verifying both share the mass dimension—not merely comparing string names. Conversions should specify the conversion factor, precision, and target unit.

**Domain-specific boundaries:**

- The general `Quantity` in the example permits `0` because zero inventory is valid. `OrderLineQuantity` may require `> 0`.
- Counts of **pieces** usually must be integers; `Quantity(2.5, PIECE)` is valid only if the business allows fractional items. Otherwise, add unit-specific constraints or define a dedicated type like `PieceCount`.
- Negative quantities can make sense in **inventory movements**; model `StockDelta` separately from `StockOnHand` instead of relaxing constraints on every `Quantity`.
- In measurements, `2.50 kg` and `2.5 kg` may be equal in **magnitude**, yet differ in **reported precision**. The example's `stripTrailingZeros()` normalization intentionally discards significant-digit information; if that matters, store precision/instrument metadata separately.

Not all units convert via simple multiplication: Celsius/Fahrenheit temperatures have different zero points; percentages, durations, and counts also have distinct rules. Place operations on the appropriate quantity type or conversion service rather than a single `Unit` enum with unbounded responsibilities.

## 7. Time Window Objects: Absolute Instants and Half-Open Endpoints

The `TimeWindow(startInclusive, endExclusive)` design uses the **[start, end)** convention: inclusive of the start instant, exclusive of the end instant.

```text
A = [08:00, 09:00)
B = [09:00, 10:00)
A and B are adjacent and do NOT overlap.

C = [08:30, 09:30)
A and C DO overlap.
```

Under this convention, `contains` returns `true` at `startInclusive` and `false` at `endExclusive`. The overlap formula for two **non-empty** intervals is:

\[
A_{\text{start}} < B_{\text{end}}
\quad\land\quad
B_{\text{start}} < A_{\text{end}}
\]

This is the condition used in `overlaps`. If empty intervals (`start == end`) were allowed, the formula and check semantics would need revision, which is why the example rejects them in the constructor.

### Choosing the Right Time Type for the Business Question

| Question | Typically Suitable Java Type | Notes |
| --- | --- | --- |
| "When exactly did the event occur?" | `Instant` | A point on the timeline; suited for storing and comparing absolute timestamps |
| "User booked an appointment for 09:00 in Hanoi?" | `LocalDateTime` with `ZoneId` | Must be resolved to an absolute instant when confirming the schedule |
| "Holiday on 2026-11-22?" | `LocalDate` | Calendar date, not tied to UTC or a specific time of day |
| "Elapsed time between two instants?" | `Duration` | Absolute duration measured in seconds/nanoseconds |
| "Add one calendar month?" | `Period` or time-zone-aware date arithmetic | A month does not have a fixed number of hours |

`LocalDateTime` **contains no time zone** and does not uniquely identify an `Instant`. When storing schedules in local time, you must know the `ZoneId`; time zones with daylight saving transitions may have non-existent or repeated local hours. A local calendar day is not necessarily 24 absolute hours everywhere either. If you need a recurring schedule like "09:00 every Monday", store the local schedule rule and `ZoneId`, rather than blindly adding `Duration.ofDays(7)` to the previous run in all cases.

Example converting a UTC instant to Vietnam local time:

```java
import java.time.Instant;
import java.time.ZoneId;
import java.time.ZonedDateTime;

final class TimeZoneExample {
    static void show() {
        Instant point = Instant.parse("2026-11-22T02:00:00Z");
        ZonedDateTime local = point.atZone(ZoneId.of("Asia/Ho_Chi_Minh"));
        System.out.println(local);
        // 2026-11-22T09:00+07:00[Asia/Ho_Chi_Minh]
    }
}
```

Note that `TimeWindow` represents an interval between two **resolved points in time**, whereas recurring schedule rules and time-zone "business hours" are distinct concepts; do not force everything into two `Instant`s if you need to regenerate future schedules.

## 8. Immutability and Equality: `record` Pitfalls

A `record` only prevents reassigning its component fields; it does not make objects inside them immutable. For example:

```java
import java.util.List;
import java.util.Objects;

record SelectedTags(List<String> values) {
    public SelectedTags {
        Objects.requireNonNull(values, "values");
        values = List.copyOf(values);
    }
}
```

`List.copyOf` prevents mutating the list through an external reference, produces a structurally unmodifiable list, and rejects `null` elements. If elements themselves are mutable objects, you still need a deep copy or immutable element types. Arrays such as `byte[]` introduce another issue: default array equality uses reference identity, so `record Payload(byte[] data)` does not automatically provide content-based `equals`.

**The key point for numeric values** is defining "equal" precisely:

- `Money` normalizes `BigDecimal` to the currency's fractional digits. Same amount and currency compare equal under the record.
- `Quantity` normalizes with `stripTrailingZeros` so `2.500 kg` equals `2.5 kg`. If measurement precision has business significance, do not apply this equality semantics blindly.
- `TimeWindow` values are equal when both `Instant` endpoints are equal; two local-time representations describing the same absolute instants resolve to the same `Instant`.
- `OrderId` values are equal when their inner UUIDs are equal, but identifier equality does not mean two `Order` objects have identical attribute states.

Never construct a value object with mutable fields used as a `HashMap` key or `HashSet` element and then mutate fields that participate in `hashCode`. That is one major reason to design value objects as immutable.

## 9. Mapping Value Objects to a Data Schema

Java value objects do not require their own tables. In a relational model, value objects are typically **flattened** into columns of the entity table; when read back, the adapter/repository reconstructs the value object and runs validation checks.

Example portion of a reservation schema in PostgreSQL:

```sql
CREATE TABLE reservations (
    id UUID PRIMARY KEY,
    customer_id UUID NOT NULL,
    total_amount NUMERIC(20, 4) NOT NULL,
    total_currency VARCHAR(3) NOT NULL,
    reserved_quantity NUMERIC(20, 6) NOT NULL,
    quantity_unit VARCHAR(16) NOT NULL,
    starts_at TIMESTAMPTZ NOT NULL,
    ends_at TIMESTAMPTZ NOT NULL,

    CONSTRAINT ck_total_nonnegative CHECK (total_amount >= 0),
    CONSTRAINT ck_quantity_positive CHECK (reserved_quantity > 0),
    CONSTRAINT ck_window_nonempty CHECK (starts_at < ends_at),
    CONSTRAINT ck_unit CHECK (
        quantity_unit IN ('PIECE', 'KILOGRAM', 'METER')
    )
);
```

Both `id` and `customer_id` are UUIDs in storage, yet they map to distinct Java types: `ReservationId` and `CustomerId`. In a real system, `customer_id` needs a foreign key to the customers table if the relationship is enforced by the database. `NUMERIC` preserves exact decimal digits within configured precision/scale limits, avoiding binary floating-point inaccuracies.

**What the schema above does not automatically guarantee:**

1. `NUMERIC(20,4)` and `NUMERIC(20,6)` are **storage precision decisions**, not universal rules for every currency or quantity. This example may need adjustment if prices require more decimal digits or quantities need higher resolution.
2. `total_currency VARCHAR(3)` does not guarantee a valid currency code on its own. You can use a currency lookup table, foreign key, and domain check; per-currency scale rules must still be enforced in the appropriate place.
3. `CHECK (starts_at < ends_at)` prevents empty or inverted intervals **within a single row**, but does not stop two rows from booking the same resource with overlapping windows. You need specialized exclusion/overlap constraints, transactions/locking, or an appropriate concurrency strategy. `TimeWindow.overlaps` in Java is insufficient when multiple processes write concurrently.
4. `TIMESTAMPTZ` represents an absolute timestamp; it does not preserve the user's original time zone name. If you need to interpret local schedules or render in the originally chosen time zone, store `zone_id` separately.
5. Do not force a value object into a lookup table when it has no independent identity or lifecycle. For instance, giving every `Money` its own row just to hold an amount usually adds unnecessary complexity. Conversely, if `Unit` is a configurable catalog with descriptions, conversions, versions, and independent management, a reference table can be appropriate.

### JPA/Hibernate, JSON, and Other Storage Engines

With **JPA**, a `record` is unsuitable as a standard entity because entities require instantiation and state management per JPA rules. For value objects, consider `@Embeddable` with provider-supported types or an `AttributeConverter` for single-column mappings. Direct support for mapping a `record` as an embeddable depends on the JPA/provider version; when unsure, use an embeddable class or appropriate converter and test the mapping. Do not assume every ORM natively understands `Currency`, `OrderId`, or `Quantity`.

With **JSON/APIs**, send properties with meaningful names, for example:

```json
{
  "orderId": "b6e8be40-e148-4e31-80f4-efab7880a552",
  "total": { "amount": "19.90", "currency": "USD" },
  "quantity": { "value": "2.5", "unit": "KILOGRAM" },
  "timeWindow": {
    "startInclusive": "2026-11-22T01:00:00Z",
    "endExclusive": "2026-11-22T02:00:00Z"
  }
}
```

Decimal strings prevent JavaScript clients from unintentionally turning monetary values into floating-point numbers. When receiving requests, the API must parse values, validate currency/unit codes, normalize, and handle validation errors. Adding or changing value object fields is an **API contract change**, requiring compatibility rules and migrations as needed.

In a **document database**, `total` and `quantity` can be stored as nested objects, while still accounting for atomic updates and data validation. In a **graph database**, value objects typically become node/edge properties rather than standalone nodes, unless the data has its own relationships and lifecycle. In **analytical systems**, retain normalized values, unit/currency codes, effective timestamps, and necessary conversion details so disparate quantities are never mistakenly aggregated together.

## 10. Verifying with Edge Cases

Value objects especially need testing at **domain value boundaries**—places where primitive types fail to catch bugs.

| Case | Expected Result | Rationale |
| --- | --- | --- |
| `new OrderId(null)` | Rejected | Invalid identifier |
| `Money.of("10.0", "USD")` vs `Money.of("10.00", "USD")` | Equal | Same amount, normalized scale |
| `Money.of("10.001", "USD")` | Rejected | No input rounding policy provided |
| Adding `10 USD` and `10 VND` | Rejected | Different currencies |
| `Quantity.of("2.500", KILOGRAM)` vs `Quantity.of("2.5", KILOGRAM)` | Equal | Magnitude normalization |
| Adding `2 KILOGRAM` and `2 METER` | Rejected | Different units |
| `TimeWindow(t, t)` or `TimeWindow(later, earlier)` | Rejected | Empty or inverted interval |
| `[08:00,09:00)` vs `[09:00,10:00)` | Non-overlapping | Half-open interval convention |
| Two overlapping resource bookings written concurrently | Database protection required | Checking individual objects in memory is insufficient |

Do not test constructors alone. Test operations producing new values, API/database conversions, schema/data format changes, and concurrent update scenarios. For example, when adding the `GRAM` unit, include explicit tests for unit conversion and rounding.

## 11. Applied Exercise

A store lets customers schedule deliveries by time slot with the following requirements:

1. Each product has a `ProductId`, and each order has an `OrderId`; both are stored as UUIDs.
2. Listed prices use VND; some items are sold by `KILOGRAM` and others by `PIECE`.
3. The store divides delivery slots into 09:00–10:00 and 10:00–11:00 in each region's local time.
4. Business policies allow discounts, refunds, and inventory adjustments.
5. Multiple processes handle orders concurrently.

Complete the following:

- Identify the required value objects and entities; explain why a `ProductId` cannot be passed to an `OrderId` parameter.
- Propose types for `Money`, `Price`, `Quantity`, and `StockDelta` with appropriate non-negative/signed rules, fractional precision, and currencies.
- Choose the data to store for a local delivery slot, how to convert it to `Instant`, and how to determine whether two adjacent slots overlap.
- Design database columns for price, quantity, unit, time zone, and time window; specify Java-level validation, database constraints, and concurrency controls.
- Describe one business change (adding foreign currency, adding a unit, changing precision, or modifying the schedule) and its impact on APIs, stored data, and tests.

**Reference answer:** `Product` and `Order` are typically entities; `ProductId` and `OrderId` are distinct value objects. `Price` requires non-negative values while `StockDelta` can be negative. Delivery slots need timestamps and a location-based time zone using the `[start,end)` convention. Java checks protect the validity of a single value, whereas uniqueness, foreign keys, and write contention must also be handled by the database and transactions.

## 12. Design Checklist Before Saving the Schema

- [ ] Every value carries a **business-meaningful type and name**, not bare `String`, `UUID`, or `BigDecimal`.
- [ ] Constructors/factories reject `null`, invalid numeric ranges, invalid units, and invalid time intervals.
- [ ] `equals`/`hashCode` rules reflect **semantic equality**, including after `BigDecimal` normalization.
- [ ] Values are genuinely immutable; mutable components are defensively copied or replaced with immutable types.
- [ ] Addition, multiplication, conversion, and rounding have explicit policies; different currencies or incompatible units are never mixed.
- [ ] `Instant` is separated from local time, and a consistent interval endpoint convention is enforced.
- [ ] Java ↔ API ↔ database mappings preserve currency, unit, time zone, and precision details.
- [ ] Database constraints cover shared data, primary/foreign keys, and concurrent updates where required.
- [ ] A schema evolution, data migration, and compatibility testing plan exists for value domain changes.

**Key takeaway:** value objects turn implicit business rules into verifiable types. `OrderId` prevents identity mix-ups; `Money` binds amount to currency and rounding policy; `Quantity` binds number to unit; `TimeWindow` fixes the semantics of interval endpoints. When those meanings are preserved across Java, APIs, and storage, the data model becomes clearer, more consistent, and easier to evolve.

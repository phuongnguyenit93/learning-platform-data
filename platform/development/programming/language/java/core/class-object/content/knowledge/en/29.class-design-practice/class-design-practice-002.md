# Keeping Minimal State and Avoiding Storing Unnecessary Derived Data in Java Class Design

## 1. Learning Objectives

After studying this lesson, you will be able to:

- Distinguish **source state** (*source of truth*, *canonical state*) from **derived data** (*derived/computed data*), display data, and caches.
- Answer the question “Does this field really need to be stored?” before adding an instance field to a Java class.
- Identify values that can be computed accurately from other fields, such as `total = unitPrice × quantity`, `area = width × height`, `fullName = firstName + lastName`, or `age = current date - birth date`.
- Understand why storing both source data and derived data simultaneously can create **contradictory state**, hard-to-maintain synchronization logic, and bugs when adding setters/constructors or changing formulas.
- Know how to design private fields, constructor validation, and instance methods to centralize state-update responsibility in the proper class.
- Use immutable values and defensive copying to prevent external objects from modifying input data and causing derived results to change uncontrollably.
- Leverage Java 17 `record` when state is a simple set of values; remember that a record component is the representation and a record does not allow adding custom instance fields outside its components.
- Distinguish **immutable values finalized at a business point in time** (checkout price, actual tax collected, transaction exchange rate, audited balance) from **purely recomputable values**: do not automatically eliminate every value that looks derived.
- Consider performance when computing expensive values: lazy cache, cache invalidation, versioning, external cache; understand that a cache is **auxiliary state with a correctness cost**, not a new truth.
- Avoid integer overflow, unit errors, and rounding/precision errors when computing money, totals, and derived values.
- Design public APIs that do not expose mutable backing collections and do not force callers to synchronize two separate setters.
- Distinguish a **derived value at the current point in time** from a **historical snapshot** or a **denormalized read model** in persistence/analytics.
- Write Java 17+ programs, run `javac`/`java`, compare stdout, and test invariants using independent examples.

> **Scope:** This lesson focuses on the principle of keeping **minimal yet sufficient object state** and avoiding storing data that can be recomputed from source state. Not all caching or materialized values are wrong. We need to distinguish business requirements, stability over time, computation cost, and consistency.

## 2. Core Concept: What Is Minimal State?

In Java, **the state of an instance** is typically represented by instance fields. A minimal-state design stores **the independent facts necessary** to describe the object, without redundantly storing values that can be completely derived from those facts.

For example, an order line:

~~~java
final class OrderLine {
    private final long unitPriceCents;
    private final int quantity;
}
~~~

The value `totalCents` can be calculated accurately from the two fields:

~~~java
long totalCents() {
    return Math.multiplyExact(unitPriceCents, quantity);
}
~~~

If the class also declares `private long totalCents;` and stores it in the constructor, it has **two ways of representing the same piece of information**:

~~~text
unitPriceCents ─┐
                ├── multiplication ──► totalCents
quantity ───────┘

If all three are stored:
    source fields and cached total can disagree.
~~~

**Keeping minimal state** does not mean “every class must have only one field.” The goal is for each field to have an **independent reason to exist**: identity, original input, committed snapshot data, a protected invariant, or a cache whose recomputation cost is justified.

### 2.1. Source, Derived, and Snapshot Data

| Type of Information | Example | Store in Object? |
| --- | --- | --- |
| Source/canonical | `quantity`, `unitPriceCents` | Yes, if it defines the object |
| Purely derived | `totalCents = price × quantity` | Usually computed when needed |
| Presentation | `displayText = name + " / " + code` | Usually computed or handled in the view |
| Business snapshot | Finalized price at checkout | May **have** to be stored for auditing |
| Time-dependent derived | Age “today” from birth date | Compute using the passed-in date |
| Expensive derived cache | Sum from a set of millions of records | Can be cached in a controlled manner |
| External materialized read model | Total revenue report, fast lookup table | Can exist separately, with refresh/versioning |
| Redundant data added for convenience | `isAdult` + `birthDate` + `age` | Usually omit, or define snapshot semantics very clearly |

**Key question:** if a derived field and the source fields disagree, **which value is trusted?** Without a consistent answer, the representation is error-prone.

## 3. How to Spot a Field That Should Not Be Stored

Ask yourself in turn:

1. Can that field be computed from **existing fields** using a deterministic formula?
2. Is the formula fast and cheap at the typical scale of use?
3. Is there an independent source of updates for that field?
4. Does the value need to reflect a **past point in time** rather than the present?
5. Are there any side effects, I/O, service calls, or external data in the calculation?
6. If a source field changes, do multiple “shadow” fields have to be updated to avoid a mismatch?
7. Can a dangerous setter be avoided by **not storing derived data**?
8. If caching is needed, who is allowed to invalidate the cache, and how do you ensure every mutation path updates it?
9. Does this field give the constructor too many parameters, making invariants hard to protect?
10. If the object is serialized, does the derived field need to be in the schema, or can the consumer compute it itself?

If a field has a simple, cheap formula, no snapshot semantics, and no independent source, **computing it in a method** is usually a good choice.

## 4. Anti-pattern: Storing Both Source Data and Totals

A design prone to drift:

~~~java
class BadLine {
    int quantity;
    long unitPriceCents;
    long totalCents;

    BadLine(int quantity, long unitPriceCents) {
        this.quantity = quantity;
        this.unitPriceCents = unitPriceCents;
        this.totalCents = quantity * unitPriceCents;
    }

    void setQuantity(int quantity) {
        this.quantity = quantity;
        // Forgot to update totalCents!
    }
}
~~~

This is an **intentionally buggy illustrative snippet**, not a design recommendation. When quantity changes, the old total remains and the object is in an inconsistent state.

If all source data is mutable, the growing number of update paths makes bugs even more likely: setters, bulk updates, JSON deserialization, ORM hydration, reflection-based frameworks, or a future developer adding a field. Code review must inspect every place where mutation can occur.

**Fix:** a single source of truth, a `totalCents()` method that computes from quantity and unitPriceCents, along with invariant validation.

## 5. Program 1: Immutable OrderLine with a Derived Total

Save **`OrderLineDemo.java`**:

~~~java
public class OrderLineDemo {
    static final class OrderLine {
        private final String sku;
        private final long unitPriceCents;
        private final int quantity;

        OrderLine(String sku, long unitPriceCents, int quantity) {
            if (sku == null || sku.isBlank()) {
                throw new IllegalArgumentException("sku");
            }
            if (unitPriceCents < 0 || quantity < 0) {
                throw new IllegalArgumentException("negative");
            }
            this.sku = sku;
            this.unitPriceCents = unitPriceCents;
            this.quantity = quantity;
        }

        long totalCents() {
            return Math.multiplyExact(unitPriceCents, quantity);
        }

        OrderLine withQuantity(int next) {
            return new OrderLine(sku, unitPriceCents, next);
        }

        int quantity() {
            return quantity;
        }
    }

    public static void main(String[] args) {
        OrderLine original = new OrderLine("PEN", 125, 3);
        OrderLine updated = original.withQuantity(4);

        System.out.println("quantity=" + original.quantity());
        System.out.println("original total=" + original.totalCents());
        System.out.println("updated total=" + updated.totalCents());
        System.out.println("original unchanged=" +
                (original.quantity() == 3));
    }
}
~~~

Run:

~~~bash
javac --release 17 OrderLineDemo.java
java OrderLineDemo
~~~

**Stdout:**

~~~text
quantity=3
original total=375
updated total=500
original unchanged=true
~~~

**Explanation:**

- `sku`, `unitPriceCents`, and `quantity` are the source data.
- There is no `totalCents` field. The method recomputes it using `Math.multiplyExact` so `long` does not overflow silently.
- The constructor guards against null/blank sku and negative quantity/price.
- `withQuantity` creates a new object, adds no setter, and needs no “total synchronization.”
- Old and new objects have their own invariants.
- **Cents** are used as the unit in the example to avoid floating-point errors for money; in real financial systems, appropriate currency, limits, and rounding policies are also required.

## 6. Before/After Snippets Where Derived Data Easily Drifts

**Before (risky):**

~~~java
class Profile {
    String firstName;
    String lastName;
    String fullName;

    void changeLastName(String last) {
        lastName = last;
        // Forgot to update fullName.
    }
}
~~~

**After (single source):**

~~~java
class Profile {
    private final String firstName;
    private final String lastName;

    Profile(String firstName, String lastName) {
        this.firstName = firstName;
        this.lastName = lastName;
    }

    String fullName() {
        return firstName + " " + lastName;
    }
}
~~~

The snippets above are for comparing ideas and have no `main`. If updating the name is needed, you can provide a constructor/`withLastName(...)` or a controlled mutation method. Do not additionally store fullName in the same object if it is merely the concatenation of two strings with no independent snapshot/standardized-name requirement.

### 6.1. Distinguishing Data That Needs Normalization from Derived Data

For example, when an email is normalized (strip/lowercase according to a **defined policy**) in the constructor: the **normalized value** itself can be the canonical source, with no need to store both `rawEmail` and `normalizedEmail` unless the business needs the raw original input as a record with independent meaning.

## 7. Program 2: Full Name Is a Method, Not a Field

Save **`FullNameDemo.java`**:

~~~java
import java.util.Objects;

public class FullNameDemo {
    record Person(String firstName, String lastName) {
        Person {
            firstName = Objects.requireNonNull(firstName).strip();
            lastName = Objects.requireNonNull(lastName).strip();

            if (firstName.isEmpty() || lastName.isEmpty()) {
                throw new IllegalArgumentException("name");
            }
        }

        String fullName() {
            return firstName + " " + lastName;
        }

        Person withLastName(String next) {
            return new Person(firstName, next);
        }
    }

    public static void main(String[] args) {
        Person first = new Person("  Lan ", " Nguyen  ");
        Person second = first.withLastName("Tran");

        System.out.println("first=" + first.fullName());
        System.out.println("second=" + second.fullName());
        System.out.println("same first name=" +
                first.firstName().equals(second.firstName()));
    }
}
~~~

Run:

~~~bash
javac --release 17 FullNameDemo.java
java FullNameDemo
~~~

Stdout:

~~~text
first=Lan Nguyen
second=Lan Tran
same first name=true
~~~

Record components are the canonical representation. `fullName()` is a derived value; there is no need to add a third component just to hold the concatenation.

## 8. Geometry: Store Width/Height, Compute Area

A rectangle:

~~~java
record Rectangle(int width, int height) {
    Rectangle {
        if (width < 0 || height < 0) {
            throw new IllegalArgumentException("size");
        }
    }

    long area() {
        return (long) width * height;
    }
}
~~~

If `area` is stored as a component in addition to width/height, a caller could call `new Rectangle(4, 5, 99)` unless validation is added. If area is just multiplication, putting it into the representation complicates the constructor/API and leads to “redundant state.”

### 8.1. Program 3: area/perimeter Computed When Needed

Save **`RectangleDerivedDemo.java`**:

~~~java
public class RectangleDerivedDemo {
    record Rectangle(int width, int height) {
        Rectangle {
            if (width < 0 || height < 0) {
                throw new IllegalArgumentException("size");
            }
        }

        long area() {
            return (long) width * height;
        }

        long perimeter() {
            return 2L * (width + (long) height);
        }

        boolean isSquare() {
            return width == height;
        }
    }

    public static void main(String[] args) {
        Rectangle a = new Rectangle(4, 5);
        Rectangle b = new Rectangle(6, 6);

        System.out.println("a area=" + a.area());
        System.out.println("a perimeter=" + a.perimeter());
        System.out.println("a square=" + a.isSquare());
        System.out.println("b area=" + b.area());
        System.out.println("b square=" + b.isSquare());
    }
}
~~~

Run:

~~~bash
javac --release 17 RectangleDerivedDemo.java
java RectangleDerivedDemo
~~~

Stdout:

~~~text
a area=20
a perimeter=18
a square=false
b area=36
b square=true
~~~

**Explanation:** `isSquare`, `area`, and `perimeter` are all facts derived from width/height. `(long)` performs the arithmetic as long to avoid int overflow in the respective cases; production code also needs to consider the maximum limit of long.

## 9. Derived Data Dependent on “Now”: Do Not Store age as Fixed State

If a class stores `birthDate` and `age` at the same time, age changes with the date, yet the age field **does not increment itself at midnight**. This is a common business logic bug.

Better:

~~~java
record Person(java.time.LocalDate birthDate) {
    int ageOn(java.time.LocalDate date) {
        return java.time.Period.between(birthDate, date).getYears();
    }
}
~~~

A “current age” calculation depends on a clock/time zone or a `LocalDate` passed in. **Passing the evaluation date into the method** makes tests deterministic and avoids storing “today’s age” as source data.

Caution: if the real domain needs to store the declared age at the time of insurance enrollment, that is a **business snapshot** that may need to be kept. History must not be lost simply because a new age can be calculated today.

## 10. Program 4: Birth Date Is the Source, Age Is a Derived Value

Save **`AgeDerivedDemo.java`**:

~~~java
import java.time.LocalDate;
import java.time.Period;

public class AgeDerivedDemo {
    record Person(LocalDate birthDate) {
        Person {
            if (birthDate == null) {
                throw new IllegalArgumentException("birthDate");
            }
        }

        int ageOn(LocalDate date) {
            if (date.isBefore(birthDate)) {
                throw new IllegalArgumentException("date before birth");
            }
            return Period.between(birthDate, date).getYears();
        }
    }

    public static void main(String[] args) {
        Person p = new Person(LocalDate.of(2000, 10, 18));

        System.out.println("age 2025=" +
                p.ageOn(LocalDate.of(2025, 10, 18)));
        System.out.println("age 2026=" +
                p.ageOn(LocalDate.of(2026, 10, 18)));
        System.out.println("birth=" + p.birthDate());
    }
}
~~~

Run:

~~~bash
javac --release 17 AgeDerivedDemo.java
java AgeDerivedDemo
~~~

Stdout:

~~~text
age 2025=25
age 2026=26
birth=2000-10-18
~~~

Person itself needs no “updateAgeOnBirthday” setter. The caller decides the evaluation date, so the calculation is consistent and easy to test.

**Do not derive the age value from the system date in unit tests** if you want stdout to be the same on every day. For a UI that needs `LocalDate.now(zone)`, provide a `Clock` or the current date from the application boundary.

## 11. Derived Collection: Cart Total Should Come from the Source Lines

Suppose Cart contains a List<OrderLine> and a `subtotalCents` field. If items are added to or removed from the list and the code forgets to update the subtotal, the invariant `subtotal = sum(lines)` is broken.

A small design:

~~~java
final class Cart {
    private final java.util.List<Line> lines;

    long subtotalCents() {
        long sum = 0;
        for (Line line : lines) {
            sum = Math.addExact(sum, line.totalCents());
        }
        return sum;
    }
}
~~~

A total field is unnecessary if the cart is small and addition is cheap. If Cart is immutable, each change creates a new Cart, sparing the code from managing invalidation.

### 11.1. Defensive Copy and Element Immutability

If the constructor simply writes `this.lines = input` where `input` is a mutable ArrayList, the caller can change its contents after construction, making Cart “immutable” on paper while the derived subtotal fluctuates unexpectedly.

Use `List.copyOf(input)` (Java 10+) to create an unmodifiable snapshot of the **collection structure**. However, it is a shallow copy: if the elements are mutable, the contents of individual elements can still be modified through aliases. A good choice is for the elements to also be immutable records/value objects.

## 12. Program 5: Immutable Cart Without Storing Subtotal

Save **`ImmutableCartDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class ImmutableCartDemo {
    record Line(String sku, long unitPriceCents, int quantity) {
        Line {
            if (sku == null || sku.isBlank()
                    || unitPriceCents < 0 || quantity < 0) {
                throw new IllegalArgumentException("line");
            }
        }

        long totalCents() {
            return Math.multiplyExact(unitPriceCents, quantity);
        }
    }

    static final class Cart {
        private final List<Line> lines;

        Cart(List<Line> input) {
            this.lines = List.copyOf(input);
        }

        long subtotalCents() {
            long sum = 0;
            for (Line line : lines) {
                sum = Math.addExact(sum, line.totalCents());
            }
            return sum;
        }

        Cart plus(Line line) {
            List<Line> next = new ArrayList<>(lines);
            next.add(line);
            return new Cart(next);
        }

        int size() {
            return lines.size();
        }
    }

    public static void main(String[] args) {
        Cart original = new Cart(List.of(
                new Line("PEN", 100, 2),
                new Line("BOOK", 500, 1)));
        Cart updated = original.plus(new Line("ERASER", 100, 1));

        System.out.println("original size=" + original.size());
        System.out.println("original subtotal=" +
                original.subtotalCents());
        System.out.println("updated size=" + updated.size());
        System.out.println("updated subtotal=" +
                updated.subtotalCents());
        System.out.println("original still=" +
                original.subtotalCents());
    }
}
~~~

Run:

~~~bash
javac --release 17 ImmutableCartDemo.java
java ImmutableCartDemo
~~~

Stdout:

~~~text
original size=2
original subtotal=700
updated size=3
updated subtotal=800
original still=700
~~~

List.copyOf rejects null elements and prevents callers from modifying the returned collection structure. Immutable `Line` records hold the source values; Cart does not store `subtotalCents`, so there is no risk of forgetting to update subtotal after `plus`.

**Performance:** each `subtotalCents()` call runs in O(n). For typical carts, this is usually a simpler trade-off than maintaining a mutable cache; with millions of items and high-frequency queries, measure in practice before changing the design.

## 13. Program 6: Bug When Caching Derived Data and Forgetting Invalidation

This example intentionally demonstrates **a flawed design whose code still compiles and runs** so you can observe drift.

Save **`StaleTotalDemo.java`**:

~~~java
public class StaleTotalDemo {
    static class Line {
        int quantity;
        final long unitPriceCents;
        final long cachedTotalCents;

        Line(int quantity, long unitPriceCents) {
            this.quantity = quantity;
            this.unitPriceCents = unitPriceCents;
            this.cachedTotalCents = quantity * unitPriceCents;
        }

        void changeQuantity(int next) {
            quantity = next; // BUG: cachedTotalCents does not change.
        }

        long recomputedTotalCents() {
            return (long) quantity * unitPriceCents;
        }
    }

    public static void main(String[] args) {
        Line line = new Line(2, 100);
        System.out.println("before cached=" + line.cachedTotalCents);

        line.changeQuantity(3);

        System.out.println("after cached=" + line.cachedTotalCents);
        System.out.println("correct now=" +
                line.recomputedTotalCents());
        System.out.println("consistent=" +
                (line.cachedTotalCents ==
                        line.recomputedTotalCents()));
    }
}
~~~

Run:

~~~bash
javac --release 17 StaleTotalDemo.java
java StaleTotalDemo
~~~

Stdout:

~~~text
before cached=200
after cached=200
correct now=300
consistent=false
~~~

The issue is not wrong multiplication; the issue is that **derived data became an independent field** whose update path fails to protect the invariant. A new setter, ORM hydration, or a partial update can repeat this bug.

**Clean fix:** remove the `cachedTotalCents` field and compute `(long) quantity * unitPriceCents` in a getter, or replace the entire object with a new value.

## 14. Encapsulation Helps Protect the Source of Truth

Use `private` fields and **controlled methods**:

~~~java
final class Item {
    private long unitPriceCents;
    private int quantity;

    void changeQuantity(int next) {
        if (next < 0) {
            throw new IllegalArgumentException("quantity");
        }
        quantity = next;
    }

    long totalCents() {
        return Math.multiplyExact(unitPriceCents, quantity);
    }
}
~~~

The snippet above omits a constructor and other APIs, but illustrates the core point: each mutation changes only the **source field**, and derived methods read the current state.

A public class with fields such as `public int quantity` and `public int total` makes the invariant depend on the discipline of every caller, which is hard to maintain. `private` does not create correctness by itself; you still need validation and policies inside methods.

### 14.1. Do Not Let Callers Update Two Fields with Two Setters

An API like `setQuantity(3); setTotal(300);` can become temporarily inconsistent, throw between the two calls, or suffer from a concurrency race. It is better to have a command with domain semantics (changeQuantity) and a derived getter that computes total.

## 15. Program 7: Mutable Source, Getter Always Consistent

Save **`ControlledMutationDemo.java`**:

~~~java
public class ControlledMutationDemo {
    static final class Line {
        private final long unitPriceCents;
        private int quantity;

        Line(long unitPriceCents, int quantity) {
            if (unitPriceCents < 0) {
                throw new IllegalArgumentException("price");
            }
            this.unitPriceCents = unitPriceCents;
            changeQuantity(quantity);
        }

        void changeQuantity(int next) {
            if (next < 0) {
                throw new IllegalArgumentException("quantity");
            }
            quantity = next;
        }

        long totalCents() {
            return Math.multiplyExact(unitPriceCents, quantity);
        }
    }

    public static void main(String[] args) {
        Line line = new Line(120, 2);
        System.out.println("before=" + line.totalCents());

        line.changeQuantity(3);
        System.out.println("after=" + line.totalCents());

        try {
            line.changeQuantity(-1);
        } catch (IllegalArgumentException expected) {
            System.out.println("invalid rejected");
        }

        System.out.println("after rejection=" +
                line.totalCents());
    }
}
~~~

Run:

~~~bash
javac --release 17 ControlledMutationDemo.java
java ControlledMutationDemo
~~~

Stdout:

~~~text
before=240
after=360
invalid rejected
after rejection=360
~~~

There is no duplicated total field. Failed mutation validation leaves the previous source state intact; the getter reflects it accurately.

**Concurrency:** the example mutable class is not automatically thread-safe. Even after removing the derived field, if multiple threads read and write quantity, synchronization or immutable snapshots/atomic designs are needed for proper visibility and consistency.

## 16. It Is Not “The Fewer Fields, the Better”

Minimal must still be **sufficient to retain facts that cannot be reconstructed**. Do not remove:

- Actual transaction timestamps.
- External identifiers or idempotency keys.
- Prices/exchange rates/taxes finalized in the transaction.
- Audit actor and audit reason.
- Provider responses or approval codes with historical significance.
- Statuses with an independent decision source, such as “paymentApproved” from a payment gateway (which cannot be derived from subtotal).
- Old snapshots needed for auditing or external systems.
- Versions of data computed under old business rules.

A value that “can be computed from current data” does not necessarily reconstruct **a past event**. For example, today you can compute today’s age, but the age declared at the time a contract was signed may carry its own legal significance.

### 16.1. Principle for Determining the Canonical Representation

A field should be stored if it has an **independent source of change** or carries **point-in-time semantics** that cannot be accurately re-derived when the context changes. Minimizing state means reducing duplication, not losing evidence and information lineage.

## 17. Monetary Amounts, BigDecimal, Rounding, and Minimal State

It is not just about field duplication; the derived calculation must be right for the domain. For money:

- Use integer minor units such as cents if the currency/domain allows it and the limits are clear.
- Or use `BigDecimal` with a currency and a scale/rounding policy.
- Avoid `double` as the authoritative source for monetary amounts requiring exactness.
- Use `BigDecimal(String)` or `BigDecimal.valueOf` appropriately, and avoid `new BigDecimal(0.1)` if an exact decimal 0.1 is expected.
- Use `Math.addExact`/`multiplyExact` when integer overflow would be a bug that must be detected.
- If the “amount charged” snapshot is the actual settled data, the **actual payment amount** may need to be stored independently even though the expected amount can be calculated from line items.

### 17.1. Program 8: BigDecimal Total Computed from the Source

Save **`BigDecimalLineDemo.java`**:

~~~java
import java.math.BigDecimal;
import java.util.Objects;

public class BigDecimalLineDemo {
    static final class Line {
        private final BigDecimal unitPrice;
        private final int quantity;

        Line(BigDecimal unitPrice, int quantity) {
            Objects.requireNonNull(unitPrice, "unitPrice");
            if (unitPrice.signum() < 0 || quantity < 0) {
                throw new IllegalArgumentException("negative");
            }
            this.unitPrice = unitPrice;
            this.quantity = quantity;
        }

        BigDecimal total() {
            return unitPrice.multiply(BigDecimal.valueOf(quantity));
        }
    }

    public static void main(String[] args) {
        Line line = new Line(new BigDecimal("2.50"), 3);
        System.out.println("unit price=" + "2.50");
        System.out.println("total=" + line.total().toPlainString());
    }
}
~~~

Run:

~~~bash
javac --release 17 BigDecimalLineDemo.java
java BigDecimalLineDemo
~~~

Stdout:

~~~text
unit price=2.50
total=7.50
~~~

`BigDecimal.multiply` computes the total with the right scale in this case. The demo uses values that do not require rounding; a real application must specify currency/scale/exchange rate/discount/rounding in the proper places rather than implicitly assuming every currency has 2 decimal digits.

## 18. Audit Principle: A “Derived Value” Can Become a Mandatory Snapshot

Ask two different questions:

1. **How much is the current cart worth?** This can be calculated from Cart.lines, quantities, and current unit prices.
2. **How much was the 01/01 order actually charged?** This may be a finalized transaction fact; it should not be recalculated from new catalog prices.

This is why **OrderDraft** and **ConfirmedOrder** can have different representations:

~~~text
OrderDraft:
    current lines
    subtotal() computed from lines

ConfirmedOrder:
    line snapshots
    amountCharged
    confirmedAt
    paymentReference
~~~

`amountCharged` in ConfirmedOrder is not necessarily “useless duplication”: it can be the settlement result, including rounding, promotions, tax, delivery fees, and external payment behavior. It is a **historical fact** that the business needs to preserve.

Be careful when using the same name `total` for “computed cart subtotal” and “actual settled amount.” Name APIs to reflect their meaning.

## 19. Program 9: Distinguishing Expected Total from Settled Amount

Save **`OrderSnapshotDemo.java`**:

~~~java
import java.time.LocalDate;

public class OrderSnapshotDemo {
    record Draft(long unitPriceCents, int quantity) {
        long expectedTotal() {
            return Math.multiplyExact(unitPriceCents, quantity);
        }
    }

    record Confirmed(long expectedTotalCents,
                     long chargedCents,
                     LocalDate date) {
        Confirmed {
            if (expectedTotalCents < 0 || chargedCents < 0
                    || date == null) {
                throw new IllegalArgumentException("confirmation");
            }
        }

        long adjustmentCents() {
            return chargedCents - expectedTotalCents;
        }
    }

    public static void main(String[] args) {
        Draft draft = new Draft(100, 3);
        Confirmed confirmed =
                new Confirmed(draft.expectedTotal(), 280,
                        LocalDate.of(2026, 1, 1));

        System.out.println("expected=" + draft.expectedTotal());
        System.out.println("charged=" + confirmed.chargedCents());
        System.out.println("adjustment=" +
                confirmed.adjustmentCents());
        System.out.println("date=" + confirmed.date());
    }
}
~~~

Run:

~~~bash
javac --release 17 OrderSnapshotDemo.java
java OrderSnapshotDemo
~~~

Stdout:

~~~text
expected=300
charged=280
adjustment=-20
date=2026-01-01
~~~

`chargedCents` is a finalized result that may differ from expectedTotal (for example, a policy adjustment), and is not necessarily duplicated calculated state. `adjustmentCents()` is the actual derived value from the two facts in Confirmed.

This is a simplified model: production code needs to store the adjustment policy and settlement confirmation from the payment system.

## 20. A Transaction History Can Be the Source for Computing Balance

If the domain requirements establish the **ledger/history** as the source of truth, the current balance can be computed from the opening balance plus the movements.

~~~text
openingBalance + Σ movements = currentBalance
~~~

Keeping **both the ledger and a mutable balance** in the same object introduces a synchronization invariant between the two forms of state. However, an accounting system with many transactions typically uses a **materialized balance** for performance and transactional consistency. This is an acceptable cache/view case when reconciliation and atomic updates are in place.

In this small example, we prioritize simplicity: storing only the opening amount and a controlled list of movements.

### 20.1. Program 10: Balance Derived from Transactions

Save **`LedgerBalanceDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class LedgerBalanceDemo {
    static final class Ledger {
        private final long openingBalance;
        private final List<Long> movements = new ArrayList<>();

        Ledger(long openingBalance) {
            if (openingBalance < 0) {
                throw new IllegalArgumentException("opening");
            }
            this.openingBalance = openingBalance;
        }

        long balance() {
            long value = openingBalance;
            for (long movement : movements) {
                value = Math.addExact(value, movement);
            }
            return value;
        }

        void deposit(long amount) {
            if (amount <= 0) {
                throw new IllegalArgumentException("deposit");
            }
            Math.addExact(balance(), amount);
            movements.add(amount);
        }

        void withdraw(long amount) {
            if (amount <= 0 || amount > balance()) {
                throw new IllegalArgumentException("withdraw");
            }
            movements.add(-amount);
        }

        List<Long> history() {
            return List.copyOf(movements);
        }
    }

    public static void main(String[] args) {
        Ledger ledger = new Ledger(100);
        ledger.deposit(50);
        ledger.withdraw(20);

        System.out.println("balance=" + ledger.balance());
        System.out.println("movements=" + ledger.history().size());

        try {
            ledger.withdraw(200);
        } catch (IllegalArgumentException expected) {
            System.out.println("overdraft rejected");
        }

        System.out.println("still balance=" + ledger.balance());
    }
}
~~~

Run:

~~~bash
javac --release 17 LedgerBalanceDemo.java
java LedgerBalanceDemo
~~~

Stdout:

~~~text
balance=130
movements=2
overdraft rejected
still balance=130
~~~

**Explanation:**

- Ledger stores source events, without adding a mutable `balance` field.
- `balance()` computes from openingBalance + movements.
- `deposit` checks for overflow before recording.
- `withdraw` ensures sufficient funds.
- `history()` returns a structurally unmodifiable snapshot.
- The demo is single-threaded and in-memory; it has no concurrency, idempotency, or durable transactions.

**Practical exception:** with millions of movements, recomputing in O(n) every time can be expensive. In real systems, a materialized balance + atomic ledger transactions + periodic reconciliation is a valid design; the point is not “no balance cache at any cost.”

## 21. Immutable vs. Mutable Objects in State Minimization

### 21.1. Immutable Value Object

If all canonical fields are `private final` and nested values are immutable, derived values can be computed at any time without worrying about concurrent mutation inside the object.

~~~java
record Point(int x, int y) {
    long distanceSquared() {
        return (long) x * x + (long) y * y;
    }
}
~~~

Record `Point` has only x/y components; `distanceSquared()` is a method. You should not add `distanceSquared` as a record component simply because it can be computed.

### 21.2. Mutable Object

If a class allows source fields to change, derived getters must read consistent state according to the concurrency model. Do not arbitrarily add cached fields unless all mutations have an invalidation contract. If multiple threads access it, a thread-safety policy is needed.

### 21.3. Records Are Not Automatically Deeply Immutable

A record with `List<String> items` only holds a **final List reference**. If the original List is mutable, others can modify its contents and cause derived counts/totals to change. Defensive copying or choosing immutable component types is an important part of a trustworthy representation.

## 22. Program 11: Defensive Copy to Protect Source Data

Save **`DefensiveCopyDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class DefensiveCopyDemo {
    record Basket(List<String> items) {
        Basket {
            items = List.copyOf(items);
        }

        int count() {
            return items.size();
        }

        String summary() {
            return String.join(",", items);
        }
    }

    public static void main(String[] args) {
        List<String> source = new ArrayList<>(List.of("A"));
        Basket basket = new Basket(source);

        source.add("B");

        System.out.println("source=" + source);
        System.out.println("basket=" + basket.summary());
        System.out.println("count=" + basket.count());

        try {
            basket.items().add("C");
        } catch (UnsupportedOperationException expected) {
            System.out.println("basket unmodifiable");
        }
    }
}
~~~

Run:

~~~bash
javac --release 17 DefensiveCopyDemo.java
java DefensiveCopyDemo
~~~

Stdout:

~~~text
source=[A, B]
basket=A
count=1
basket unmodifiable
~~~

`List.copyOf` returns an unmodifiable snapshot of the elements/reference sequence at creation time. With immutable String elements, Basket’s derived count/summary cannot be altered by the caller through the original list.

If the elements are mutable `Item` objects, `List.copyOf` **does not deep-copy the Item objects**. You must also protect element state if an immutable snapshot is genuinely part of the business contract.

## 23. Minimizing State Keeps Constructors and APIs Concise, and Invariants Clear

A constructor taking two source fields:

~~~java
new Rectangle(3, 5);
~~~

Is easier to understand than:

~~~java
new Rectangle(3, 5, 15, 16, false);
~~~

if the last three arguments are just area/perimeter/isSquare that can be derived from the first two numbers. A long API permits contradictory inputs or demands complex validation.

A public constructor taking `amount, quantity, total` raises the question: which value wins if total ≠ amount × quantity? If total is not an independent business fact, remove the parameter and compute it via a method.

### 23.1. Derived Getters Must Not Have Unexpected Side Effects

A good `total()` method is usually **pure** with respect to state: the same canonical inputs produce the same output, without mutating fields, making network calls, or altering transactions.

If a method performs I/O or mutates state, a name like `getTotal()` is misleading. Separate queries/computations from commands/side effects clearly.

## 24. Caching When Computation Is Expensive: A Conditional Trade-Off

A cache field may be reasonable if:

1. The derived calculation is genuinely expensive (measured with a profiler/benchmark).
2. The result is read many times between mutations.
3. The inputs have a **clear mutation boundary** and centralized updates.
4. There is a complete invalidation strategy.
5. Cache memory usage is acceptable.
6. Concurrency/visibility rules are designed.
7. When the cache is invalid/missing, it can be accurately recomputed from the source.
8. The cache is not treated as an independent business fact if it is only a derived value.

**Key point:** a cache **does not replace the source of truth**. When inputs change, the cache must be invalidated or versioned.

### 24.1. Strategies

| Strategy | Pros | Risks |
| --- | --- | --- |
| Compute on demand | Fewer fields, always matches source | O(n) on every read |
| Eager recompute on mutation | O(1) getter | Every mutation must update the cache; transaction consistency |
| Lazy + dirty flag | Recomputed when needed | Dirty flag/invalidation must be exact |
| Versioned cache | Can compare sourceVersion/cacheVersion | Version drift, concurrency |
| External cache/materialized view | Separates read optimization from domain source | Delayed sync/updates, eviction, failures |
| Immutable object memoization | Inputs do not change after construction | Thread-safety/publication if lazy; extra memory |

Do not add a cache merely because “it feels like a getter should be O(1)”; decide after measuring on a real workload.

## 25. Program 12: Cached Derived Total with Explicit Invalidation

Save **`ValidatedCacheDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class ValidatedCacheDemo {
    static final class Report {
        private final List<Long> amounts = new ArrayList<>();
        private boolean dirty = true;
        private long cachedTotal;
        private int calculations;

        void add(long amount) {
            if (amount < 0) {
                throw new IllegalArgumentException("amount");
            }
            amounts.add(amount);
            dirty = true;
        }

        long total() {
            if (dirty) {
                long sum = 0;
                for (long amount : amounts) {
                    sum = Math.addExact(sum, amount);
                }
                cachedTotal = sum;
                dirty = false;
                calculations++;
            }
            return cachedTotal;
        }

        int calculations() {
            return calculations;
        }
    }

    public static void main(String[] args) {
        Report report = new Report();

        report.add(10);
        report.add(20);

        System.out.println("first=" + report.total());
        System.out.println("second=" + report.total());
        System.out.println("calcs=" + report.calculations());

        report.add(5);

        System.out.println("after change=" + report.total());
        System.out.println("calcs after change=" +
                report.calculations());
    }
}
~~~

Run:

~~~bash
javac --release 17 ValidatedCacheDemo.java
java ValidatedCacheDemo
~~~

Stdout:

~~~text
first=30
second=30
calcs=1
after change=35
calcs after change=2
~~~

This is **an illustration of when a cache is actually chosen**; the fact that it needs `dirty`, `cachedTotal`, and `calculations` shows the extra state cost. `calculations` is only a metric to explain the demo, not part of domain state. The class does not expose the mutable `amounts` list, and every mutation goes through `add` to set dirty.

**Warning:** this is a single-threaded sample. If multiple threads read and write Report, `dirty` and `cachedTotal` require synchronization, atomic snapshots, or an immutable approach; simply adding `volatile` on one field does not automatically produce a consistent snapshot of the whole object. With very large numbers, summation can overflow; `Math.addExact` detects this instead of silently wrapping.

## 26. Caching Increases State and the Number of Invariants to Test

When there is only the `amounts` list:

~~~text
total() = sum(amounts)
~~~

A simple data-source invariant is that amounts contains only non-negative numbers (per the domain).

When there is a cache:

~~~text
dirty=false ⇒ cachedTotal == sum(amounts)
dirty=true  ⇒ cachedTotal is not used as query result
~~~

This must be guaranteed across:
- every add/update/delete path;
- rollback when a mutation fails;
- deserialization/rehydration;
- concurrency memory visibility;
- copying/cloning the object;
- version changes;
- exceptions during computation.

Therefore, every redundant field has a **correctness cost**. Do not evaluate it solely by the number of bytes for that field.

## 27. Derived State for Collections: `size`, `isEmpty`, `contains`

With a private List source:

~~~java
private final List<String> items = new ArrayList<>();

int count() {
    return items.size();
}

boolean empty() {
    return items.isEmpty();
}
~~~

There is no need to add `itemCount` or `emptyFlag` to mirror the List size/status: List already maintains its size according to its own implementation.

A `contains("A")` call is a derived query on items; if it runs too expensively, consider an appropriate data structure such as Set instead of manually maintaining count flags or indexes. Choosing a source-data structure suited to the access patterns is usually better than adding a redundant cache.

### 27.1. When Multiple Representations Are Needed for Optimization

A service may hold `Map<Id,Item>` and an index `Map<Category,List<Id>>` for fast queries. That is **deliberate denormalization**, not minimal-state design in the simple sense. It requires ownership, atomic updates, rebuilding, and reconciliation. Keep the domain object simple if indexing belongs to the infrastructure/read layer.

## 28. Invariants Protected by Methods, Not by Caller Promises

You can establish rules such as:

- Source field `quantity >= 0`.
- `unitPriceCents >= 0`.
- `totalCents() = exactMultiply(quantity, unitPriceCents)`.
- `lines` contains no nulls.
- `birthDate` is non-null; the ageOn method validates the evaluation date.
- `openingBalance >= 0` and withdrawal rules.
- `cacheValid ⇒ cachedTotal matches sourceVersion` if a cache exists.

Simply writing a comment `// Always keep total synced` is not enough. Put invariants into constructors, controlled APIs, and tests.

### 28.1. Atomicity Across Multiple Sources

When two canonical source fields need to be updated **at the same time**, a `changePriceAndQuantity` method or immutable replacement can protect the invariant. Minimizing fields does not replace synchronization/transaction requirements. If two fields form a logically atomic state, they still must be updated consistently.

## 29. Equality and hashCode When Keeping Redundant Fields

If a class implements its own `equals`/`hashCode`, it must define identity/value semantics according to the **canonical state**. Do not include a transient derived cache in equality/hashing if the cache is not part of business identity: two objects with identical inputs but different warm/cold cache states should not unexpectedly be unequal.

With `record Rectangle(int width,int height)`, the generated equals/hashCode reflect the components; the derived area method does not add an extra field.

Conversely, if `area` is added as a record component, it becomes part of the representation/equality even though it is merely calculated from width/height. That complicates the API/invariants and can affect serialization.

### 29.1. Protecting Mutable Keys

If an object is used as a HashMap/HashSet key, fields affecting equals/hash should not be mutated while the object is serving as a key. A derived getter may look innocuous, but equality based on mutable source state can cause lookup failures. Immutable value objects are usually easier to use safely.

## 30. Program 13: Record Value Equality Based on Source Components

Save **`MinimalRecordEqualityDemo.java`**:

~~~java
public class MinimalRecordEqualityDemo {
    record Rectangle(int width, int height) {
        long area() {
            return (long) width * height;
        }
    }

    public static void main(String[] args) {
        Rectangle a = new Rectangle(2, 6);
        Rectangle b = new Rectangle(2, 6);
        Rectangle c = new Rectangle(3, 4);

        System.out.println("a area=" + a.area());
        System.out.println("c area=" + c.area());
        System.out.println("a equals b=" + a.equals(b));
        System.out.println("a equals c=" + a.equals(c));
        System.out.println("same area=" + (a.area() == c.area()));
    }
}
~~~

Run:

~~~bash
javac --release 17 MinimalRecordEqualityDemo.java
java MinimalRecordEqualityDemo
~~~

Stdout:

~~~text
a area=12
c area=12
a equals b=true
a equals c=false
same area=true
~~~

Two shapes with the same derived area do not necessarily have the same canonical width/height, so area should not be used as a shortcut replacing the representation in equality.

## 31. Normalize Input Once, Without Keeping Both Original and Normalized Copies When Unnecessary

If the domain policy defines a canonical email as a trimmed lowercase ASCII domain-friendly string, validate and then store **a single canonical representation**:

~~~java
record Email(String value) {
    Email {
        value = value.strip().toLowerCase(
                java.util.Locale.ROOT);
    }
}
~~~

This is a **snippet** illustrating a simplified policy, not comprehensive email internationalization/canonicalization: email addresses have complex local-part rules and the application must choose the right policy. For ordinary domain IDs with case-insensitive rules defined by the application itself, normalization can be performed in a controlled way.

Do not store both the raw input and the canonical value simultaneously if the raw input serves no independent audit purpose. If you must display a name exactly as entered by the user or keep it for compliance, the raw snapshot can be real data that needs to be retained.

## 32. Program 14: Single-Field Canonical Code

Save **`NormalizedCodeDemo.java`**:

~~~java
import java.util.Locale;
import java.util.Objects;

public class NormalizedCodeDemo {
    record ProductCode(String value) {
        ProductCode {
            value = Objects.requireNonNull(value, "value")
                    .strip()
                    .toUpperCase(Locale.ROOT);

            if (value.isEmpty()) {
                throw new IllegalArgumentException("blank");
            }
        }

        String display() {
            return "SKU-" + value;
        }
    }

    public static void main(String[] args) {
        ProductCode a = new ProductCode("  pen ");
        ProductCode b = new ProductCode("PEN");

        System.out.println("canonical=" + a.value());
        System.out.println("same value=" + a.equals(b));
        System.out.println("display=" + a.display());
    }
}
~~~

Run:

~~~bash
javac --release 17 NormalizedCodeDemo.java
java NormalizedCodeDemo
~~~

Stdout:

~~~text
canonical=PEN
same value=true
display=SKU-PEN
~~~

The object holds one canonical value. `display` is a derived presentation value; no `displayCode` field is needed. The `strip/upper` policy belongs to the ProductCode domain in the demo.

## 33. API Design: Clear Naming for Source Queries and Derived Queries

A domain class might provide:

~~~java
long unitPriceCents();
int quantity();
long expectedTotalCents();
~~~

The method names clearly convey their meaning:
- Unit price is a source value.
- Quantity is a source value.
- Expected total is a computed value.

Do not mix:
- `getTotal()` updating the database, mutating a cache, and calling a payment provider at the same time.
- `setTotal()` when the total value is derived from the source.
- `getAge()` relying on implicit system time, making tests nondeterministic.
- `getChargedAmount()` when in reality it only computes the expected amount from the current catalog.

Name methods according to domain semantics to avoid confusing snapshots with derived views.

## 34. DTOs, Persistence, and JSON: Avoid Sending “Two Sources of Truth”

When serializing an object to a DTO, it is sometimes useful to return both source and derived fields for consumer display convenience:

~~~text
{
  "unitPriceCents": 125,
  "quantity": 3,
  "totalCents": 375
}
~~~

This is an **illustrative JSON schema**, not Java code. The question is determining **who owns total**:

- The server can include total as a **derived response field** (computed each time).
- The client should not send total to override business validation if it is merely derived.
- If the client sends both source and total, the server must have a clear rule: recompute/validate or reject mismatches.
- When persisting a completed transaction, the settled amount is an independent snapshot that may need to be stored.
- In read models/materialized views, storing total for performance is acceptable if refresh/versioning/reconciliation and the true source are in place.

Do not treat “minimal state” as a mandate to strip derived values from **every API response**; it primarily addresses **authoritative internal state**, and does not forbid presentation projections.

## 35. Computation Cost and Evaluation Heuristics

A heuristic:

1. **O(1) and pure**, such as fullName, area, quantity×price: almost always compute it.
2. **O(n) with small n**, such as the subtotal of a cart with a few dozen lines: usually compute it.
3. **O(n) with large n and frequent queries**: run benchmarks and consider caching/materialized views.
4. **I/O or cross-service**: do not call it a “simple derived getter”; this is a query boundary/service concern.
5. **Time-varying**, such as age or exchange rate: pass the clock/context and define snapshot semantics.
6. **Must retain history**: store a separate snapshot even if it looks derived.
7. **Thread-safety/invalidation is too complex**: consider immutable snapshots or an external cache instead of internal fields.
8. **Large derived output**: consider streaming or a lazy iterator instead of a field storing a full copied list.

A field that reduces CPU usage while adding synchronization, invalidation, and memory overhead is not automatically optimal. The total cost is what decides.

## 36. Field Evaluation Checklist Template

| Question | If “Yes” | Course of Action |
| --- | --- | --- |
| Is there a formula from source fields? | Derived candidate | Write a method; do not rush to store it |
| Is the formula cheap/pure? | Easy to recompute | Keep minimal state |
| Do inputs change independently? | Prone to drift | Even more reason to avoid duplicate fields |
| Is it a finalized historical event? | Meaningful snapshot | Clearly store as an immutable fact |
| Does it depend on date/clock/external rate? | Context changes | Pass context; distinguish snapshots |
| Is recomputation very costly in CPU/I/O? | Performance concern | Measure and design caching with a contract |
| Are there many mutation paths? | Cache invalidation is hard | Use encapsulation/immutability instead |
| Is equality/serialization needed? | Representation API concern | Avoid derived fields causing coupling |
| Are there mutable nested collections? | Source may be silently modified | Defensive copy/immutable elements |
| Are there concurrent readers/writers? | Consistency/visibility concern | Snapshots or synchronization |
| Does the data appear in an API response? | May just be a projection | Compute from source at serialization time |
| Do data migrations change the rule? | Historical divergence | Version rule/snapshot/reconciliation |

## 37. What Should Unit Tests Verify?

- Given source values, the computed getter returns the right result.
- Changing the source via valid methods makes computed values accurate immediately.
- Invalid mutations throw and **do not corrupt source state**.
- The old immutable object does not change when a new object is created.
- The caller modifying the input list after construction does not alter internal state.
- If a cache with invalidation exists, the computation count and value after change are correct.
- Equal sources yield equal derived outputs under the same formula.
- Different sources can produce the same derived output, yet the objects are not necessarily equal.
- Monetary calculations do not overflow silently.
- Time-derived values use a fixed input date/clock.
- Historical snapshots do not change when the current price list changes.
- DTO serialization/deserialization must adhere to the source-of-truth rules.
- Concurrency tests when a shared mutable source/cache is genuinely multi-threaded.

### 37.1. Program 15: Testing the Minimal-State Contract

Save **`MinimalStateContractTest.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class MinimalStateContractTest {
    record Line(long priceCents, int quantity) {
        Line {
            if (priceCents < 0 || quantity < 0) {
                throw new IllegalArgumentException("line");
            }
        }

        long total() {
            return Math.multiplyExact(priceCents, quantity);
        }
    }

    record Cart(List<Line> lines) {
        Cart {
            lines = List.copyOf(lines);
        }

        long subtotal() {
            long sum = 0;
            for (Line line : lines) {
                sum = Math.addExact(sum, line.total());
            }
            return sum;
        }
    }

    static void check(boolean ok, String description) {
        if (!ok) {
            throw new AssertionError(description);
        }
    }

    public static void main(String[] args) {
        List<Line> input = new ArrayList<>();
        input.add(new Line(125, 2));
        Cart cart = new Cart(input);

        check(cart.subtotal() == 250, "initial total");
        input.add(new Line(500, 1));
        check(cart.lines().size() == 1, "defensive copy");
        check(cart.subtotal() == 250, "subtotal unchanged");

        try {
            cart.lines().add(new Line(1, 1));
            throw new AssertionError("mutation accepted");
        } catch (UnsupportedOperationException expected) {
            // List copy prevents the structure from being modified.
        }

        try {
            new Line(-1, 1);
            throw new AssertionError("negative accepted");
        } catch (IllegalArgumentException expected) {
            // Constructor protects the source invariant.
        }

        check(new Line(125, 2).total() == cart.subtotal(),
                "same formula");

        System.out.println("minimal state checks passed");
    }
}
~~~

Run:

~~~bash
javac --release 17 MinimalStateContractTest.java
java MinimalStateContractTest
~~~

Stdout:

~~~text
minimal state checks passed
~~~

Tests run proactively using `check`, without relying on `assert` (which is disabled by default unless `-ea` is passed). In particular, Cart has no extra total field and still satisfies all the checks.

## 38. Common Mistakes

| Design/Issue | Why Is It Dangerous? | Fix |
| --- | --- | --- |
| `price, qty, total` as 3 mutable fields | Total can become stale | Store price/qty, compute total |
| `firstName, lastName, fullName` | Duplicate string; changing first/last name causes drift | `fullName()` method |
| `width, height, area, perimeter` | Complex constructors and setters | Derived geometry methods |
| `birthDate, age` | Age changes over time | `ageOn(date)` |
| `items, itemCount, emptyFlag` | List already maintains size | `size()`/`isEmpty()` |
| Exposing `ArrayList` while keeping a cached sum | External mutations bypass invalidation | Private list, defensive copy/query |
| Keeping a cached sum without dirty/version | Stale result | Compute or invalidation/versioning |
| Treating every snapshot as redundant duplication | Loses historical price/tax | Classify authoritative event facts |
| Using `double` for authoritative monetary totals | Precision issues | Cents/BigDecimal + policy |
| Using `quantity*price` without checking overflow | Silent wraparound | Exact operations/validation |
| Getter performing network I/O | Unexpected side effects/latency | Explicit query service |
| Derived cache in equals/hashCode | Warm/cold objects unequal | Canonical identity/value semantics |
| Using a mutable object as a key and then updating its fields | Hash-based lookup breaks | Immutable keys |
| Two setters `setQty/setTotal` | Non-atomic consistency | Single source, derived query |
| Treating `List.copyOf` as a deep copy | Mutable elements still change | Immutable elements/deep snapshot if needed |
| Storing a derived flag `isExpired` permanently | Time changes state | `isExpiredAt(now)` |
| Heavy recomputation in a frequently called getter | Performance cost | Benchmark + deliberate cache |
| Shared mutable cache lacking synchronization | Races/stale visibility | Immutable snapshots/locking |
| DTO allowing client to send total override | Client may supply wrong value | Recompute/validate server-side |
| Removing actual settlement amount because it “can be recomputed” | Loses audit history | Keep independent snapshot fact |

## 39. Practice Exercises

### Exercise 1. Redesign Student

Given fields `birthDate`, `age`, and `displayAge`, what should be kept?

**Suggested answer:** if only the current age is needed, keep `birthDate`; use `ageOn(LocalDate)` and a display method. If the age declared at admission time is a fixed fact, model the snapshot separately so historical meaning is not lost.

### Exercise 2. A Cart with 3 Lines

Given `List<Line> lines`, `int count`, and `long subtotal`, can count/subtotal be removed?

**Answer:** `count() = lines.size()` and `subtotal() = sum(lines.total())`. If the list is small, remove the redundant fields. If subtotal is a finalized snapshot or very expensive to compute, reclassify it and design it with a contract.

### Exercise 3. Area Formula

~~~java
record Rectangle(int width, int height, long area) {}
~~~

**Answer:** if area is merely width×height, the record should keep only width and height along with an area method. If area was measured in the field and carries a different meaning, it must not be derived by a formula.

### Exercise 4. Settled Amount

The cart expected 10000 cents, and the gateway charged 9800 cents. Should `chargedCents` be removed because “total = items sum”?

**Answer:** No. The charged amount is an external settlement fact that can differ from the expected total; keep the snapshot along with the reference/adjustment context.

### Exercise 5. Caching Needed

Summing 1 million events, with the getter called 1000 times/second and mutations occurring once per hour. What should you do?

**Answer:** measure the cost; a snapshot/cache or a materialized read model may be appropriate. Clearly define cache invalidation and concurrency; do not accidentally turn the cache into an authoritative fact.

### Exercise 6. External Mutation

A constructor receives an ArrayList and assigns it directly to a private final List, while subtotal is computed. Is this safe?

**Answer:** No, if the caller still holds the ArrayList and can modify it. Use `List.copyOf`/immutable element values or an explicit live-view contract.

### Exercise 7. Is a Private Field Enough?

Quantity/Price are private, yet one method modifies quantity without updating cachedTotal. Is the invariant protected?

**Answer:** Not yet. Private only narrows the mutation paths; you still need to remove derived state or implement correct invalidation.

### Exercise 8. Currency

Should `double total = 0.1 + 0.2` be an authoritative monetary amount?

**Answer:** No, because binary floating-point cannot represent all decimal fractions accurately. Choose cents/BigDecimal with an appropriate scale/rounding policy.

### Exercise 9. Record Containing a List

Is `record Cart(List<Line> lines)` automatically immutable?

**Answer:** The record field is final, but the List elements/structure can be mutable through an alias; a defensive copy or an immutable data model is needed.

### Exercise 10. Getter with a Service Call

`getCurrentExchangeRate()` needs to make a network call. Should a rate field be stored and treated as derived from the currency pair?

**Answer:** Do not automatically treat it as a pure formula. A rate has a timestamp, provider, version, and caching/consistency contract; model the query/snapshot clearly.

### Exercise 11. Does Full Name Need Localization?

Person names have display rules depending on locale/policy. Does this make fullName source state?

**Answer:** Not necessarily. A formatting strategy/locale can be passed into a display method. Only store the original display name when it is a user-authored independent fact that needs to be retained.

### Exercise 12. Does Caching Change Equality?

Two objects have the same inputs; one has a warm cache and the other does not. Should they be unequal?

**Answer:** Usually no if the cache is only a performance detail; equals/hashCode should follow canonical identity/value semantics.

## 40. Class Design Checklist

- [ ] Does each field have an independent data source or a clear reason to be stored?
- [ ] Can any field be computed cheaply and accurately from other fields?
- [ ] Has a source of truth been chosen where mismatches could occur?
- [ ] Are source fields private and thoroughly validated?
- [ ] Does any setter require callers to manually update derived fields?
- [ ] Do derived getters have pure behavior and appropriate names?
- [ ] Is duplicate state avoided in constructors/record components?
- [ ] Have integer overflow and currency/scale/rounding been considered?
- [ ] Is data that varies with clock/context computed using explicit inputs?
- [ ] Are there snapshot/audit facts that must not be removed?
- [ ] Are mutable collection inputs defensively copied?
- [ ] Are nested elements genuinely immutable?
- [ ] If caching, has performance been measured and an invalidation policy established?
- [ ] Is there a concurrency policy for cached/mutable canonical fields?
- [ ] Can the cache be rebuilt/reconciled from authoritative state?
- [ ] Do derived fields accidentally participate in equals/hashCode?
- [ ] Do DTOs/persistence distinguish input truth from output projection?
- [ ] Do unit tests verify updates, rejections, copying, snapshots, and overflow?
- [ ] When a business formula changes, is versioning of historical amounts needed?
- [ ] Is the design readable and does it have fewer invariants than before?

## 41. References

- [Java Language Specification Java SE 17 `8.3 — Field Declarations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.3): instance fields, static fields, field modifiers.
- [JLS Java SE 17 `8.3.1.2 — final Fields](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.3.1.2): final fields and definite assignment.
- [JLS Java SE 17 `8.8 — Constructor Declarations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.8): constructors and initialization.
- [JLS Java SE 17 `8.10 — Record Classes](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10): component-based representation, derived methods.
- [Java SE 17 `java.util.List.copyOf`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection)): unmodifiable snapshot, null restrictions, shallow elements.
- [Java SE 17 `java.math.BigDecimal`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html): arbitrary-precision decimal calculations, multiply, scale/rounding.
- [Java SE 17 `java.lang.Math.addExact`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Math.html#addExact(long,long)) and [`multiplyExact`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Math.html#multiplyExact(long,long)): overflow checking.
- [Java SE 17 `java.time.LocalDate`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/LocalDate.html): dates and temporal computations.
- [Java SE 17 `java.time.Period`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Period.html): date-based amount and age computation.
- [Oracle Java 17 — Creating Unmodifiable Lists, Sets, and Maps](https://docs.oracle.com/en/java/javase/17/core/creating-immutable-lists-sets-and-maps.html): unmodifiable factory/copy APIs and trade-offs.

## Conclusion

Good class design does not try to minimize the number of fields at all costs; it keeps **a sufficient, clear, and consistent set of source state**. Results such as `area`, `fullName`, `lineTotal`, `cartSubtotal`, `isEmpty`, or `ageOn(date)` should usually be **computed from source fields**, not stored as duplicated mutable fields.

Reducing redundant state reduces the number of invariants, setters, constructor parameters, synchronization paths, and bugs when formulas change. Encapsulation, validation, immutable values, and defensive copies keep the source of truth stable.

When performance genuinely demands it, a **controlled cache** is a valid optimization—but it must have invalidation, a concurrency policy, and the ability to recompute from the source. When the business requires **actual historical/snapshot facts**, store them with their own distinct meaning rather than removing them just because they look like derived data.

**Rule of thumb:** *Store facts that genuinely need to be remembered; recompute what can reliably be derived; cache only when recomputation cost has been proven; preserve snapshots that carry business meaning.*

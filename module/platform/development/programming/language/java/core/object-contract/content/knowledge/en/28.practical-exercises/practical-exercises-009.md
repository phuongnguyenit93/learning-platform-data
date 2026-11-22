# Checklist Before Publishing a Value-Contract Class in Java

## Objective: What Must Be Certain Before Release?

A **value contract** specifies when two instances represent **the same value**, which inputs are valid, how state can change, and which behaviors callers are entitled to rely on. Before publishing a value-style class to another module, library, or public API, answer the questions below with **concrete decisions and verification checks**. Do not just check whether the class overrides `equals()` and `hashCode()`.

Typical examples include `Money`, `Point`, `EmailAddress`, `DateRange`, or a business identifier. Two instances of a value object can be two distinct objects in memory (`a != b` under `==`) yet still satisfy `a.equals(b) == true`. This differs from an *entity*, where identity can depend on a distinct ID and a long-lived lifecycle.

**Opening question to lock down:** Does this class truly represent *a value* or *an entity with its own identity*? If you cannot clearly state the rule for when two instances represent the same value, do not publish an equality contract yet.

## 1. Stage-by-Stage Question List

### A. Defining the Meaning and Scope of the Value

- [ ] **What concept does the object represent?** Write a single clear sentence, e.g., "A non-negative monetary amount with a currency code, accurate to two decimal places."
- [ ] **Which attributes constitute the value?** List fields governing equality; which fields are only display data, descriptions, caches, metadata, or derived data?
- [ ] **Are two instances with identical data created at two different times equal?** If yes, `==` is not the criterion; define value equality.
- [ ] **Is any field carrying stable entity identity?** If yes, reconsider treating the class as a value object; do not accidentally merge two distinct entities that happen to share attributes.
- [ ] **Are domain constraints documented?** For example, are negative unit prices valid, are inverted date ranges valid, and which character set is allowed for currency codes?
- [ ] **Are there different input representations that are equivalent?** For example, `" usd "` and `"USD"`, or `BigDecimal("10.0")` and `BigDecimal("10.00")`.
- [ ] **Does the class need to implement `Comparable`?** If yes, is a total ordering meaningful, and is `compareTo(x) == 0` consistent with `equals(x)`?

**Decision to record:** a table listing every component, validation rule, normalization rule, and whether it participates in `equals()`/`hashCode()`. Any unresolved rule must be settled before designing the public API.

### B. `null` Policy and Invariants

- [ ] **Which fields forbid `null`?** Required fields must be checked right at the constructor/factory, e.g., `Objects.requireNonNull(name, "name")`.
- [ ] **Do optional fields distinguish `null`, empty strings, and absent values?** Merge those states only when the business domain truly allows it.
- [ ] **Are there cross-field validity constraints?** For example, `start <= end`, or two coordinates must use the same reference frame.
- [ ] **When input is invalid, what does the method do?** Document the exception type, diagnostic message, and whether it normalizes or rejects.
- [ ] **Do all object creation paths enforce invariants?** Inspect constructors, static factories, builders, parsers, JSON mappers, ORMs, deserialization, and copy methods.
- [ ] **Can getters unexpectedly return `null`?** Documentation and type contracts must match actual runtime behavior.

Do not use sentinels such as `0`, `"N/A"`, fake dates, or empty strings to represent missing data if they could be valid values. The `null` rule must be consistent across input, stored state, equality, `toString()`, and return APIs.

### C. Normalization and Canonical Representation

- [ ] **Are the exact normalization steps, order of application, and locale defined?** For example, trimming ends, Unicode normalization, case folding with `Locale.ROOT`, unit conversion.
- [ ] **Does normalization lose information?** Changing case, stripping accents, or collapsing whitespace can collide names/IDs that differed in meaning; do this only when the specification allows it.
- [ ] **Is normalization stable and idempotent?** A valid value normalized a second time must remain unchanged.
- [ ] **Are characters validated before/after normalization?** Avoid silently "fixing" a malformed code into another code.
- [ ] **How precise must numeric values be?** Do not use `double` for money by default; for `BigDecimal`, have `scale`, rounding, and the relationship between `equals()` and `compareTo()` been explicitly decided?
- [ ] **Do timestamps or measurement units have a unified representation?** State timezone/UTC, base unit, precision, and conversion bounds.

**Note on `BigDecimal`:** `new BigDecimal("10.0").compareTo(new BigDecimal("10.00")) == 0`, yet `equals()` is `false` because `scale` differs. If a field participates in equality of a record or class, normalize scale or intentionally design a compatible comparison and hash. Never change `equals()` alone while ignoring `hashCode()`.

### D. `equals()`, `hashCode()`, and Comparison Ordering

- [ ] **Is `equals()` reflexive?** For every valid value `x`, `x.equals(x)` is `true`.
- [ ] **Is it symmetric?** `x.equals(y)` and `y.equals(x)` must match, including when subclasses or proxies are involved.
- [ ] **Is it transitive?** If `x.equals(y)` and `y.equals(z)`, then `x.equals(z)` must hold.
- [ ] **Is it consistent while relevant state does not change?** Results must not depend on unstable caches, current time, or unexpected external state.
- [ ] **Is `x.equals(null)` always `false`?**
- [ ] **Do two equal instances have equal hashes?** `x.equals(y) => x.hashCode() == y.hashCode()`; the converse is not guaranteed due to collisions.
- [ ] **Are all and only the fields chosen for equality used consistently?** Avoid cache fields, logging timestamps, mutable state, or derived fields outside value semantics.
- [ ] **Could any subclass break symmetry/transitivity?** Without a complete hierarchy equality design, consider `final` or `record` (records are `final` by default).
- [ ] **If implementing `Comparable`, a comparator, or using `TreeSet`/`TreeMap`, is the ordering relation documented?** `compareTo() == 0` may differ from `equals()`, which makes sorted collections behave differently from hash collections; know the impact upfront.

With `record`, `equals()` and `hashCode()` are generated from **all components**. Review components carefully before publishing a record: adding a component usually affects constructors, pattern matching, string representation, and value equality definitions. If a value must ignore certain metadata, you may need a class design or explicit overrides instead of default equality.

### E. Immutability, Defensive Copying, and Derived Data

- [ ] **Is the object truly immutable after creation?** `final` on a reference field does not make a `List`, array, `Date`, or child object immutable.
- [ ] **Does the constructor copy mutable data passed by the caller?** Use defensive copies such as `List.copyOf(...)` when appropriate (note `List.copyOf` rejects `null` elements and copies structure only, not deep-copying elements).
- [ ] **Do accessors expose internal mutable references?** Return copies or appropriate unmodifiable views; keep the policy consistent.
- [ ] **Do derived values have a clear source of truth?** For example, `total = unitPrice * quantity`; avoid storing and allowing independent mutation of both source and result.
- [ ] **If caching is present, when is the cache invalidated and does it participate in equality/hash?** Cached values should usually be excluded from equality; if a lazy cache is used across threads, it needs a concurrency policy.
- [ ] **Can the object be used safely as a `HashMap` key or `HashSet` element?** Components participating in the hash should remain immutable for as long as the object resides in the collection.

**Aliasing test:** create a value object from a collection/array, mutate the original data after construction, and verify `equals()`, `hashCode()`, and getters of the value object remain unchanged. Repeat the check after obtaining a reference from a getter and trying to mutate it.

### F. Public API, Errors, and Compatibility

- [ ] **Do type, constructor, factory, and method names accurately convey immutability?** For example, `Money.of(...)`, `plus(...)`, `amount()`; avoid getters or setters that mislead callers into thinking immutable fields can be mutated.
- [ ] **Is the visibility of constructors and helpers intentional?** Ensure validation cannot be bypassed via secondary constructors or builders.
- [ ] **Is `toString()` safe for logging?** Records have a default `toString()` printing every component, which can accidentally leak sensitive information.
- [ ] **Is a stable JSON, database, text, or binary representation needed?** Normalization, schema, field names, number formats, and round-trip parsing must align with the contract.
- [ ] **Are exceptions from parsing, normalization, and numeric operations documented?** Callers must know when error handling is needed.
- [ ] **If published as a library API, is the versioning policy defined?** Changing `equals()`, normalization, `hashCode()`, or constructor rules can alter behavior even when Java signatures stay identical.
- [ ] **Does documentation show an example distinguishing two distinct instances that are equal by value?** Remind callers not to use `==` to compare two independent value objects.

Do not rely on `System.identityHashCode()` to determine value equality, and do not use `toString()` or `hashCode()` values as unique IDs. `hashCode()` serves bucket organization in hash collections and permits collisions; hash values can vary across implementations/versions and are not durable identifiers.

## 2. Pre-Release Check Example: Value Object `Money`

The policy below is chosen **for the example**, not prescribed for all financial systems:

1. Money consists of a currency code and a non-negative amount. It is a **value object**, not an account or transaction with an ID.
2. The currency code accepts exactly three **ASCII** letters, case-insensitive, stripping leading/trailing whitespace; only valid ASCII letters are accepted. The example uses a three-character syntax rule and does not validate whether the code is in the ISO 4217 list.
3. `amount` is required, non-negative, with at most two digits after the decimal point; normalized to `scale = 2` **without silent rounding**.
4. `record` stores only the two normalized components; default `equals()` and `hashCode()` examine both. No setters, caches, or derived fields.
5. `plus()` requires matching currency codes and returns a new value object; it does not perform exchange-rate conversion.

Place the Java 17+ program in `ValueContractReview.java`:

```java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.HashSet;
import java.util.Locale;
import java.util.Objects;
import java.util.Set;

public class ValueContractReview {
    public record Money(String currency, BigDecimal amount) {
        public Money {
            currency = Objects.requireNonNull(currency, "currency").strip();
            if (!currency.matches("[A-Za-z]{3}")) {
                throw new IllegalArgumentException("currency must be three ASCII letters");
            }
            currency = currency.toUpperCase(Locale.ROOT);

            amount = Objects.requireNonNull(amount, "amount");
            try {
                amount = amount.setScale(2, RoundingMode.UNNECESSARY);
            } catch (ArithmeticException ex) {
                throw new IllegalArgumentException("amount requires rounding", ex);
            }
            if (amount.signum() < 0) {
                throw new IllegalArgumentException("amount must be nonnegative");
            }
        }

        public Money plus(Money other) {
            Objects.requireNonNull(other, "other");
            if (!currency.equals(other.currency)) {
                throw new IllegalArgumentException("different currencies");
            }
            return new Money(currency, amount.add(other.amount));
        }
    }

    public static void main(String[] args) {
        Money first = new Money(" usd ", new BigDecimal("10.0"));
        Money second = new Money("USD", new BigDecimal("10.00"));
        Money euro = new Money("EUR", new BigDecimal("10.00"));

        System.out.println("same reference: " + (first == second));
        System.out.println("same value: " + first.equals(second));
        System.out.println("same hash: " + (first.hashCode() == second.hashCode()));
        System.out.println("different currency: " + first.equals(euro));
        System.out.println("canonical code: " + first.currency());
        System.out.println("canonical amount: " + first.amount().toPlainString());
        System.out.println("sum: "
                + first.plus(new Money("usd", new BigDecimal("2.50")))
                       .amount().toPlainString());

        Set<Money> values = new HashSet<>();
        values.add(first);
        values.add(second);
        System.out.println("set size: " + values.size());

        try {
            new Money("usd", new BigDecimal("1.234"));
        } catch (IllegalArgumentException ex) {
            System.out.println("fractional precision rejected");
        }
        try {
            first.plus(euro);
        } catch (IllegalArgumentException ex) {
            System.out.println("cross-currency addition rejected");
        }
    }
}
```

Compile and run:

```bash
javac -encoding UTF-8 ValueContractReview.java
java ValueContractReview
```

Deterministic output:

```text
same reference: false
same value: true
same hash: true
different currency: false
canonical code: USD
canonical amount: 10.00
sum: 12.50
set size: 1
fractional precision rejected
cross-currency addition rejected
```

**Analysis:** `first` and `second` are created via two `new` calls so they have different references, yet their normalized record components are equal. `HashSet` keeps one element because `equals()` and `hashCode()` are consistent. `amount` is an immutable `BigDecimal`, ensuring the record in the example exposes no mutable state. All `Money` creation passes through the invariant-enforcing constructor; addition returns a new instance. Input `"1.234"` is rejected because `scale = 2` cannot be set without rounding.

**Intentional limitations:** The example does not verify currency codes against real ISO codes, does not convert exchange rates, does not define division or floating-point multiplication, and uses exactly two decimal places for all currencies. Real systems must adapt these rules to specific currencies and problems. The example also does not use `Money` as an entity or replace transactional business modeling.

## 3. Minimum Test Matrix to Approve the Contract

Turn the questions into independent tests over valid and invalid values. The table below states expected outcomes; do not test by comparing `toString()` strings unless that is itself the output contract.

| Test group | Data/test | Outcome to verify |
| --- | --- | --- |
| Reflexivity | `x.equals(x)` | `true`. |
| Symmetry | `x.equals(y)` and `y.equals(x)` | Same result. |
| Transitivity | `x ==value y`, `y ==value z` | `x.equals(z) == true`. |
| `null` in `equals()` | `x.equals(null)` | `false`. |
| Different type | `x.equals("other")` | `false`, no exception thrown. |
| Equivalence via normalization | `" usd ", 10.0` and `"USD", 10.00` | `equals == true`, equal hashes. |
| Equal hashes do not imply equal values | Any two colliding objects | `equals()` still decides by value; do not treat hash as ID. |
| Differing equality component | `USD 10.00` and `EUR 10.00` | `equals == false`. |
| Hash collection | Add two equivalent values to `HashSet` | Size 1. |
| Required `null` | `currency = null`, `amount = null` | Fail fast and consistently (`NullPointerException` in the example). |
| Invalid code | Blank code, `"US1"`, non-ASCII characters | `IllegalArgumentException`. |
| Invalid number | `amount < 0` or requires rounding | `IllegalArgumentException`. |
| Idempotence | Reconstruct from `x.currency()` and `x.amount()` | Canonical value unchanged. |
| Immutability | Read fields and call `plus()` | `x` unchanged; result is a new instance. |
| Invalid operation semantics | Add two different currency codes | Rejected, not summed purely numerically. |
| Conversion/serialization | Serialize then deserialize (if supported) | Invariants and equality remain valid; encoding has explicit versioning. |

For classes containing mutable references, add **defensive copy** tests before and after initialization. For classes with hand-written `equals()`/`hashCode()`, test subclass and proxy cases if the design permits inheritance. For `Comparable`, add antisymmetry of sign, transitivity of ordering, and consistency with `equals()` per the chosen contract.

## 4. Mandatory Questions in Code Review

Before merging or releasing an API, reviewers should ask the author to point directly in code or docs to:

1. **"When are two instances equal?"** Give three examples: equal after normalization, unequal due to one value field, and different references yet equal by value.
2. **"Do all creation paths uphold invariants?"** Point to constructors/factories and boundary input tests; check parsers, builders, and deserializers.
3. **"Can any state cause the hash to change while the object is a key?"** If yes, require immutability or revisit the equality design.
4. **"What is preserved and what is normalized?"** Check for potential information loss, Unicode, locale, `BigDecimal.scale`, timezones, and `null`/empty handling.
5. **"Was metadata or cache accidentally included in equality?"** If it is a record, inspect every component carefully.
6. **"When values are invalid, what does the API report?"** Exceptions must be clear and predictable to callers.
7. **"Do any getters expose mutable structures?"** Try mutating the initial collection/array and the returned object.
8. **"Which consumers are affected by post-release changes?"** Include `HashSet`/`HashMap`, cache keys, database unique keys, JSON schemas, and comparison methods.

### Before–after issue identification example

**Problematic design (illustrative code, not a standalone program):**

```java
// amount and currency are mutable fields that already participate in equals/hashCode.
// If the instance is inside a HashSet, setters can cause lookups to fail.
money.setCurrency("EUR");

// If total is also stored as a separately mutable field,
// total may no longer match amount * quantity.
```

**Tighter design:** factories/constructors validate all inputs, normalize once, store immutable state, and return new instances when values change. Derived values are computed from source components or explicitly managed caches. API promises must match the invariants the code actually enforces.

## 5. Release Acceptance Criteria

Mark as **ready to publish** when all four result groups are met simultaneously:

- **Readable contract:** describes value kind, fields participating in equality, `null` rules, normalization, precision, exceptions, immutability, and related behaviors.
- **Matching implementation:** all creation paths maintain invariants; `equals()`/`hashCode()` obey the contract; internals expose no mutable state; operations return valid values.
- **Verification evidence:** tests cover equality/hash laws, data boundaries, creation/loading paths, collections, ordering relations if any, and immutability.
- **Compatibility review:** checks impact on public APIs, consumers, serialization, database/caching, and versioning rules on changes.

If any core question remains unanswered (especially **which values are equal, which inputs are valid, and which state can change**), treat it as a design issue to resolve before release rather than patching with a random `hashCode()` or caller-side validation wrappers.

## 6. Short Contract Template Alongside the Class

```text
Type: Money (value object, immutable)
Components: currency (ASCII 3 letters, uppercase), amount (>= 0, scale 2)
Null policy: both required; null rejected
Canonicalization: strip currency, validate ASCII, uppercase Locale.ROOT;
                  amount.setScale(2, UNNECESSARY)
Equality/hash: both canonical components, record defaults
Ordering: no Comparable; different currencies have no implicit order
Derived values: none stored; plus() returns new Money
Failure policy: invalid state or mixed currencies -> exception
Compatibility: changes in equality, scale or normalization need review
```

**Key takeaway:** A reliable value contract is a consistent whole across **business semantics, canonical representation, invariants, equality/hashing, immutability, API, and tests**. The checklist is only complete once every answer has been turned into observable, verified behavior in code.

## References

- [Java SE 17 — `Object.equals()` / `hashCode()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html)
- [Java SE 17 — `Record` and record specification](https://docs.oracle.com/en/java/javase/specs/jls/se17/html/jls-8.html#jls-8.10)
- [Java SE 17 — `BigDecimal`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html)
- [Java SE 17 — `Set`, `HashSet`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashSet.html)
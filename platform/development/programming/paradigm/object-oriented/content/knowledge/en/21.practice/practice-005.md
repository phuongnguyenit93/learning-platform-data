# Value objects and equality in Java OOP

> **Learning goal:** Design *value objects* that validate their data at construction, remain immutable throughout their lifetimes, compare by **value**, and work correctly as `HashMap` keys and `HashSet` or `TreeSet` elements.

Suppose a store identifies products by SKU and represents unit prices as amounts with currencies. Two variables containing the same normalized SKU or the same amount and currency should be **semantically equal**, even if their objects were created at different times.

This exercise combines value-object design with testing the `equals`, `hashCode`, and `compareTo` contracts; it goes beyond merely adding comparison methods to a class.

## 1. Distinguishing identity and value equality

An *entity* (such as a domain `Order`) usually has its **own identity**: two orders with identical totals may still be different orders. A *value object* (such as a normalized SKU or monetary amount) is identified mainly by **the attributes that determine its meaning**.

~~~java
String sku1 = new String("BOOK-1");
String sku2 = new String("BOOK-1");

System.out.println(sku1 == sku2);      // false: hai tham chiếu khác nhau
System.out.println(sku1.equals(sku2)); // true: cùng nội dung
~~~

For user-defined classes:

- `==` checks whether operands reference the same object.
- By default, `Object.equals` returns `true` only when both variables reference the same object.
- Regular classes can override `equals`/`hashCode`; alternatively, a `record` generates component-based equality.
- A `record` compares **its components** by value; if a component contains an array or mutable object, deep immutability and equality semantics still need explicit handling.

| Concept | Entity | Value object |
|---|---|---|
| Meaning of "the same" | Business identity, such as `orderId` | Values of semantically significant attributes |
| Example | Order, user account | SKU, Money, date range |
| Immutability | Business state may change | Prefer immutability for sharing and comparison |
| Two objects with identical displayed data | May still represent distinct entities | Equal if all meaningful components are equal |
| Use in hash-based collections | Based on stable, intentionally designed identity | Suitable when `equals` and `hashCode` are consistent |

**Note:** Do not define entity `equals` solely in terms of all mutable fields. Changing hashed fields while an entity is used as a key can break lookups.

## 2. Requirements and acceptance contract

Build two value objects:

### A. `Sku` — Product identifier

- Accept external text, `trim()` leading/trailing whitespace, and uppercase with `Locale.ROOT`.
- After normalization, require **3–20 characters**, with an uppercase Latin letter or digit at each end; allow `A-Z`, `0-9`, and `-` in between.
- Throw `IllegalArgumentException` for null or invalid strings.
- `new Sku(" ab-01 ")` must equal `new Sku("AB-01")` and have the same hash.
- No setters; the SKU value must remain fixed after construction.

### B. `Money` — Monetary amount

For simplicity, the exercise supports only **USD** and **EUR**, both with **2 decimal places** in this system. No exchange-rate conversion is performed.

- Store an enum `Currency` of `USD` or `EUR` and a `BigDecimal amount`.
- Reject `null`; monetary amounts must be **nonnegative**.
- Normalize `BigDecimal` to **scale = 2** with `setScale(2, RoundingMode.UNNECESSARY)`. Allow redundant trailing 0 digits but never silently round a third decimal place whose digit is not 0.
- `USD 12.3` must equal `USD 12.30` and have the same hash.
- `USD 12.30` must **not** equal `EUR 12.30`: the numbers match, but the currencies differ.
- `add` may combine amounts only when both use the same currency; mixing USD and EUR must be rejected.
- `compareTo` must impose an order **consistent with equals**. For technical sorting in collections, compare **currency codes first**, then amounts. This ordering **does not represent economic conversion**.
- Business comparison method `greaterThan` accepts only the same currency and throws for different currencies.

### C. `ProductKey` and `ProductTags`

- `ProductKey(Sku, Money)` treats SKU + unit price as a composite value: objects with the same SKU, currency, and amount are equal.
- `ProductTags` holds a `List<String>` and must copy the input so later caller modifications cannot change its state; it must not return a mutable list either.
- Comparison of `ProductKey` does not need random IDs, creation timestamps, or counters; those would make semantically equal values appear different.

### Core acceptance cases

| ID | Test case | Expected result |
|---|---|---|
| EQ01 | Two `Sku` values from `" ab-01 "` and `"AB-01"` | `equals = true`; identical hashes |
| EQ02 | Different SKUs | `equals = false` |
| EQ03 | `Money(USD, 12.3)` and `Money(USD, 12.30)` | Equal values, equal hashes, `compareTo = 0` |
| EQ04 | `USD 12.30` and `EUR 12.30` | Different; `compareTo != 0` |
| EQ05 | `HashSet` with two equivalent SKUs | Contains only 1 element |
| EQ06 | Use an equivalent `Money` key for `get` in `HashMap` | Retrieve the value previously `put` |
| EQ07 | `TreeSet` containing equivalent `Money` values | No duplicate element is created |
| EQ08 | Add USD to EUR | `IllegalArgumentException` |
| EQ09 | Negative amount or value requiring rounding, e.g. `1.234` | Rejected |
| EQ10 | Mutate source list after creating `ProductTags` | Value-object state remains unchanged |
| EQ11 | Mutate the list returned by `ProductTags` | Rejected |
| EQ12 | `equals(null)` or `equals` with a different type | `false` |

## 3. Real-world trap: BigDecimal has two meanings of equality

`BigDecimal` uses the **numeric value** for `compareTo` but **both value and scale** for `equals`:

~~~java
BigDecimal a = new BigDecimal("12.3");
BigDecimal b = new BigDecimal("12.30");

System.out.println(a.compareTo(b) == 0); // true
System.out.println(a.equals(b));         // false
~~~

If `Money.equals` uses `amount.compareTo(other.amount) == 0` while `hashCode` uses `amount.hashCode()`, two objects can become **equal by equals but have different hashes**. That violates the hash contract and can make `HashSet`/`HashMap` behave unexpectedly.

Here both amounts are normalized with `setScale(2, UNNECESSARY)` in the constructor. The record can then generate correct `equals` and `hashCode` because its `BigDecimal` component has a fixed scale. This is an example of a **canonical representation**: differently written inputs with the same meaning map to one representation.

Avoid `new BigDecimal(0.1)` when an exact decimal representation of text input is required. Use `new BigDecimal("0.1")` or a suitable factory such as `BigDecimal.valueOf(0.1)`. In this example, monetary input comes from strings.

## 4. Implement it first: starter code

Before viewing the solution, try completing the logic in these types:

~~~java
record Sku(String code) {
    Sku {
        // TODO: normalize + validate; gán ngược vào code
    }
}

enum Currency { EUR, USD }

record Money(Currency currency, BigDecimal amount)
        implements Comparable<Money> {
    Money {
        // TODO: validate currency và chuẩn hóa amount về scale 2
    }

    Money add(Money other) {
        // TODO: chỉ cộng khi cùng currency
        throw new UnsupportedOperationException();
    }

    @Override
    public int compareTo(Money other) {
        // TODO: thứ tự theo mã tiền tệ, sau đó theo amount
        throw new UnsupportedOperationException();
    }
}
~~~

Questions to ask before coding:

1. Will any field change after the object enters a `HashSet` or becomes a `HashMap` key?
2. Should objects with identical contents but different constructor order or case representations be equal?
3. Does ordering require `a.compareTo(b) == 0` if and only if `a.equals(b)`?
4. If an object contains a `List`, `Date`, or array, does simply declaring it `final` prevent mutable aliases?
5. Can different currencies be added or compared directly in economic terms?

## 5. Standalone Java 17 reference solution

Create **`ValueObjectPractice.java`**, paste in all the code below, and run it with JDK 17 or later without external libraries:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.TreeSet;

public class ValueObjectPractice {

    // Chỉ hỗ trợ hai loại tiền tệ có hai chữ số thập phân.
    enum Currency { EUR, USD }

    // Value object cho mã SKU chuẩn hóa.
    record Sku(String code) {
        Sku {
            if (code == null) {
                throw new IllegalArgumentException("SKU is null");
            }
            code = code.trim().toUpperCase(Locale.ROOT);
            if (!code.matches("[A-Z0-9][A-Z0-9-]{1,18}[A-Z0-9]")) {
                throw new IllegalArgumentException("Invalid SKU: " + code);
            }
        }
    }

    // Cả currency và amount đều là các component bất biến trong bài này.
    record Money(Currency currency, BigDecimal amount)
            implements Comparable<Money> {

        Money {
            currency = Objects.requireNonNull(currency, "currency");
            amount = Objects.requireNonNull(amount, "amount")
                    .setScale(2, RoundingMode.UNNECESSARY);
            if (amount.signum() < 0) {
                throw new IllegalArgumentException("Money must be >= 0");
            }
        }

        static Money of(Currency currency, String decimal) {
            return new Money(currency, new BigDecimal(decimal));
        }

        private void requireSameCurrency(Money other) {
            Objects.requireNonNull(other, "other");
            if (currency != other.currency) {
                throw new IllegalArgumentException(
                    "Currency mismatch: " + currency + " vs " + other.currency
                );
            }
        }

        Money add(Money other) {
            requireSameCurrency(other);
            return new Money(currency, amount.add(other.amount));
        }

        // So sánh nghiệp vụ chỉ hợp lệ khi cùng đơn vị tiền tệ.
        boolean greaterThan(Money other) {
            requireSameCurrency(other);
            return amount.compareTo(other.amount) > 0;
        }

        // Thứ tự phục vụ sorted collections: currency trước, amount sau.
        // KHÔNG phải phép so sánh sức mua giữa USD và EUR.
        @Override
        public int compareTo(Money other) {
            Objects.requireNonNull(other, "other");
            int byCurrency = currency.name().compareTo(other.currency.name());
            return byCurrency != 0
                    ? byCurrency : amount.compareTo(other.amount);
        }
    }

    // Value object kết hợp: equals/hashCode do record sinh theo hai component.
    record ProductKey(Sku sku, Money unitPrice) {
        ProductKey {
            Objects.requireNonNull(sku, "sku");
            Objects.requireNonNull(unitPrice, "unitPrice");
        }
    }

    // Ví dụ value object có thành phần là một collection.
    // String immutable; List.copyOf loại bỏ alias mutable của danh sách.
    record ProductTags(List<String> values) {
        ProductTags {
            values = List.copyOf(Objects.requireNonNull(values, "values"));
            if (values.stream().anyMatch(String::isBlank)) {
                throw new IllegalArgumentException("Tag cannot be blank");
            }
        }
    }

    private static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    private static void expect(
            Class<? extends RuntimeException> type, Runnable operation) {
        try {
            operation.run();
        } catch (RuntimeException ex) {
            if (type.isInstance(ex)) return;
            throw new AssertionError(
                "Expected " + type.getSimpleName()
                    + " but got " + ex.getClass().getSimpleName(), ex
            );
        }
        throw new AssertionError("Expected " + type.getSimpleName());
    }

    public static void main(String[] args) {
        // 1. Hai object khác tham chiếu nhưng bằng giá trị.
        Sku first = new Sku(" ab-01 ");
        Sku second = new Sku("AB-01");
        check(first != second, "Objects should be distinct references");
        check(first.equals(second), "SKU value equality");
        check(second.equals(first), "Symmetric equality");
        check(first.hashCode() == second.hashCode(), "Equal hash codes");
        check(!first.equals(null), "Not equal to null");
        check(!first.equals("AB-01"), "Not equal to different type");

        Set<Sku> skuSet = new HashSet<>();
        skuSet.add(first);
        skuSet.add(second);
        check(skuSet.size() == 1, "HashSet should deduplicate equal SKUs");
        expect(IllegalArgumentException.class, () -> new Sku("a"));
        expect(IllegalArgumentException.class, () -> new Sku("bad!"));
        System.out.println("PASS: SKU equality and HashSet");

        // 2. Chuẩn hóa BigDecimal: 12.3 và 12.30 có cùng biểu diễn.
        Money usd1 = Money.of(Currency.USD, "12.3");
        Money usd2 = Money.of(Currency.USD, "12.30");
        Money eur = Money.of(Currency.EUR, "12.30");

        check(usd1 != usd2, "Distinct Money instances");
        check(usd1.equals(usd2), "Numeric representation normalized");
        check(usd1.hashCode() == usd2.hashCode(), "Equal Money hash");
        check(usd1.compareTo(usd2) == 0, "Comparison consistent with equals");
        check(!usd1.equals(eur), "Currency belongs to value");
        check(usd1.compareTo(eur) != 0, "Currencies distinguish sort keys");

        Map<Money, String> descriptions = new HashMap<>();
        descriptions.put(usd1, "Twelve USD and thirty cents");
        check("Twelve USD and thirty cents".equals(descriptions.get(usd2)),
                "HashMap equivalent-key lookup");

        Set<Money> sorted = new TreeSet<>();
        sorted.add(usd1);
        sorted.add(usd2);
        sorted.add(eur);
        check(sorted.size() == 2, "TreeSet uses compareTo for duplicates");
        System.out.println("PASS: Money equality, HashMap and TreeSet");

        // 3. Phép toán phải tuân thủ miền và đơn vị tiền tệ.
        Money plus = usd1.add(Money.of(Currency.USD, "0.70"));
        check(plus.equals(Money.of(Currency.USD, "13.00")),
                "Currency-preserving addition");
        check(usd1.greaterThan(Money.of(Currency.USD, "12.29")),
                "Greater-than same currency");
        expect(IllegalArgumentException.class, () -> usd1.add(eur));
        expect(IllegalArgumentException.class, () -> usd1.greaterThan(eur));
        expect(IllegalArgumentException.class,
                () -> Money.of(Currency.USD, "-0.01"));
        expect(ArithmeticException.class,
                () -> Money.of(Currency.USD, "1.234"));
        System.out.println("PASS: currency-aware operations and validation");

        // 4. Giá trị tổng hợp: cùng SKU và Money thì cùng ProductKey.
        ProductKey key1 = new ProductKey(first, usd1);
        ProductKey key2 = new ProductKey(second, usd2);
        check(key1.equals(key2), "Composite value equality");
        check(key1.hashCode() == key2.hashCode(), "Composite hash");
        System.out.println("PASS: composite value object");

        // 5. Defensive copy: thay đổi list gốc không làm đổi value object.
        List<String> input = new ArrayList<>(List.of("sale", "book"));
        ProductTags tags = new ProductTags(input);
        input.set(0, "changed");
        check(tags.values().get(0).equals("sale"),
                "Input list must not alias internal state");
        expect(UnsupportedOperationException.class,
                () -> tags.values().add("hidden"));
        check(tags.equals(new ProductTags(List.of("sale", "book"))),
                "List components compare by contents");
        System.out.println("PASS: immutable composite data and defensive copy");

        // 6. Bẫy BigDecimal thuần: equals không giống compareTo.
        BigDecimal a = new BigDecimal("12.3");
        BigDecimal b = new BigDecimal("12.30");
        check(a.compareTo(b) == 0, "Numeric values match");
        check(!a.equals(b), "Raw BigDecimal scale differs");
        System.out.println("PASS: BigDecimal equality pitfall demonstrated");
    }
}
~~~

Run from the directory containing the file:

~~~bash
javac ValueObjectPractice.java
java ValueObjectPractice
~~~

Expected output:

~~~text
PASS: SKU equality and HashSet
PASS: Money equality, HashMap and TreeSet
PASS: currency-aware operations and validation
PASS: composite value object
PASS: immutable composite data and defensive copy
PASS: BigDecimal equality pitfall demonstrated
~~~

### Design explanation

**`Sku`:** Normalization occurs in the `record`'s *compact constructor*. Reassigning the `code` parameter updates the value stored in the record component. Each object then has a canonical representation.

**`Money`:** Because every `amount` has `scale = 2`, record-generated `equals` and `hashCode` treat `12.3` and `12.30` as equivalent after normalization. Currency is also a component and therefore participates in equality.

**`ProductKey`:** A composite key combining two immutable value objects. It uses neither creation time, memory address, nor a random ID; therefore, it is suitable as a key as long as object-construction rules remain stable.

**`ProductTags`:** `List.copyOf` creates an unmodifiable list detached from the mutable source list. Because every element is a `String` (immutable), callers cannot indirectly mutate its elements. If elements were `StringBuilder` or `Date`, they would also need copying, not just the list.

**`compareTo`:** Ordering is defined as (currency name, amount). It works for `TreeSet`/`TreeMap` because two `Money` values satisfy `compareTo == 0` only when both currency and normalized amount match. This ordering cannot determine whether EUR 10 has more or less purchasing power than USD 11 in economic terms.

## 6. How to test the equals, hashCode, and compareTo contracts

### The `equals` contract

Let `a`, `b`, and `c` be objects that do not change during the checks:

| Property | Required condition |
|---|---|
| Reflexivity (*reflexive*) | `a.equals(a) == true` |
| Symmetry (*symmetric*) | `a.equals(b) == b.equals(a)` |
| Transitivity (*transitive*) | If `a=b` and `b=c` under equals, then `a=c` |
| Consistency (*consistent*) | Repeated calls return the same result while data is unchanged |
| Comparison with null | `a.equals(null) == false` |

If `a.equals(b)` is `true`, then `a.hashCode() == b.hashCode()` is **required**. The reverse is not required: distinct objects **can have hash collisions**.

### The `compareTo` contract

Java `Comparable` requires consistent ordering. Its key properties include:

- The sign of `a.compareTo(b)` is opposite to the sign of `b.compareTo(a)`.
- If `a > b` and `b > c` under comparison, then `a > c`.
- If `a.compareTo(b) == 0`, comparisons of `a` and `b` with any other value must have the same sign.
- Consistency with equals is **strongly recommended** for `TreeSet` and `TreeMap`: `compareTo == 0` should correspond to `equals == true`. If intentionally inconsistent, document it, because sorted collections distinguish elements using `compareTo`.

In Java, `HashSet` relies on `hashCode` and `equals`; `TreeSet` (with natural ordering) uses `compareTo`. A `Money` comparator that ignores currencies or fails to normalize scale may produce different set results.

~~~mermaid
flowchart TD
    A["Tạo hai value object từ input"] --> B["Chuẩn hóa và validate trong constructor"]
    B --> C["Các component có ý nghĩa có cùng giá trị?"]
    C -->|Có| D["equals = true; hashCode bằng nhau"]
    C -->|Không| E["equals = false; hash có thể trùng"]
    D --> F["HashSet/HashMap nhận diện cùng khóa"]
    D --> G["Nếu Comparable: compareTo = 0"]
    E --> H["Nếu Comparable: compareTo khác 0"]
    G --> I["TreeSet/TreeMap nhận diện cùng phần tử"]
~~~

The diagram assumes `compareTo` is consistent with `equals`, as in the solution. Hash collisions are not defects provided `equals` still distinguishes values correctly.

## 7. Implementing equals/hashCode manually without records

In older projects or classes with special designs, use a **final class** with immutable fields and manual overrides:

~~~java
import java.util.Locale;
import java.util.Objects;

public final class ProductCode {
    private final String value;

    public ProductCode(String raw) {
        if (raw == null) {
            throw new IllegalArgumentException("raw cannot be null");
        }
        String normalized = raw.trim().toUpperCase(Locale.ROOT);
        if (normalized.isEmpty()) {
            throw new IllegalArgumentException("empty product code");
        }
        this.value = normalized;
    }

    public String value() {
        return value;
    }

    @Override
    public boolean equals(Object obj) {
        if (this == obj) return true;
        if (!(obj instanceof ProductCode other)) return false;
        return value.equals(other.value);
    }

    @Override
    public int hashCode() {
        return Objects.hash(value);
    }

    @Override
    public String toString() {
        return value;
    }
}
~~~

Two instances, `new ProductCode(" abc ")` and `new ProductCode("ABC")`, are equal and have the same hash. Making the class `final` here eliminates subclass-related problems that could break the symmetry of `equals` when subclasses add new meaningful fields.

A common mistake:

~~~java
@Override
public boolean equals(Object obj) {
    // Sai: chỉ so sánh field "name" và bỏ qua currency.
    // Hoặc sai: equals dùng compareTo của BigDecimal,
    // nhưng hashCode vẫn dùng BigDecimal.hashCode() chưa chuẩn hóa.
}
~~~

Never override `equals` while forgetting `hashCode`; do not use mutable hashed fields while an object is stored as a key.

## 8. Mutable value-object and aliasing pitfalls

### 8.1. A key changes after insertion into HashMap

~~~java
class MutableKey {
    String code;

    MutableKey(String code) { this.code = code; }

    @Override
    public boolean equals(Object obj) {
        return obj instanceof MutableKey other
                && java.util.Objects.equals(code, other.code);
    }

    @Override
    public int hashCode() {
        return java.util.Objects.hashCode(code);
    }
}
~~~

If you `put` a `MutableKey` into a `HashMap` and then change its `code`, the key's hash can change. Subsequent lookups may fail even though the object remains in the map. Do not rely on a lucky result for a particular input; the design error is **unstable equality/hash data while the key is stored**.

Fix: keep fields `private final`, normalize during construction, and create a **new object** instead of using a setter.

### 8.2. A record containing an array is not automatically a deep value object

~~~java
record ArrayKey(byte[] bytes) {}
~~~

Arrays are mutable, and array `equals` compares references. Two different arrays containing identical bytes are not equal by contents under record-generated equality. Callers can also modify an input array after passing it to the constructor.

A safer design is a purpose-built immutable value object that copies arrays on input/output and overrides equals/hashCode using `Arrays.equals`/`Arrays.hashCode`, or another suitable immutable structure. Do not expose a raw array as a record component and assume deep immutability.

### 8.3. `Collections.unmodifiableList` and `List.copyOf` are different

- `Collections.unmodifiableList(original)` creates an unmodifiable **view** through a wrapper, but still reflects modifications made by the owner of `original`.
- `List.copyOf(original)` creates an API-level immutable list representation that retains the values at receipt time, but **does not deep-copy** individual elements.
- Decide explicitly whether you need a **live read-only view** or an **immutable snapshot**. Value objects usually favor snapshots when input collections can change.

## 9. Advanced exercise: write manual property-based tests

Without a library, generate many numeric strings with the same amount but different scales, such as `"12.3"` and `"12.30"`, and try:

~~~java
Money a = Money.of(Currency.USD, "12.3");
Money b = Money.of(Currency.USD, "12.30");

assert a.equals(b);
assert b.equals(a);
assert a.hashCode() == b.hashCode();
assert a.compareTo(b) == 0;
~~~

**Note:** Java `assert` is disabled by default unless run with `-ea`. For effective CI tests, use JUnit Assertions or a `check` helper as in the complete example; if using `assert`, run `java -ea ...`.

You can also iterate automatically through pairs of values:

~~~java
String[] inputs = {"0", "0.0", "0.00", "1.2", "1.20", "12.30"};

for (String x : inputs) {
    for (String y : inputs) {
        Money a = Money.of(Currency.USD, x);
        Money b = Money.of(Currency.USD, y);
        if (a.compareTo(b) == 0) {
            if (!a.equals(b) || a.hashCode() != b.hashCode()) {
                throw new AssertionError("Inconsistent Money: " + x + ", " + y);
            }
        }
    }
}
~~~

In this example, `Money` and `Currency` are nested types within `ValueObjectPractice`; in another test file, use `ValueObjectPractice.Money` and `ValueObjectPractice.Currency` (in the same package) or import them appropriately.

In a project with JUnit 5, replace the loop with `@ParameterizedTest`/`@MethodSource` and expand boundary cases: `0`, `0.01`, `999999.99`, negatives, scale 3 requiring rounding, and different currencies. On failure, print inputs for reproducibility.

## 10. Extension exercises

1. **Enhance `Sku`:** Disallow consecutive `"--"` in an SKU. Test `"AB--01"` and confirm already valid SKUs still compare correctly.
2. **Add `Money.subtract`:** Decide whether negatives are allowed under business rules. Otherwise, reject a subtraction that would produce a negative value before returning the value object.
3. **Create `Percentage`:** Accept 0–100% with a fixed scale; do not use `double` for ratios. Ensure `5.0%` and `5.00%` are equivalent under the contract.
4. **Create `DateRange`:** Store start/end dates, require `start <= end`, and provide `contains(LocalDate)`. Two ranges with identical endpoints must be equal and have equal hashes.
5. **Create `EmailAddress`:** Define normalization rules before implementing equals. Do not assume the whole email local part is case-insensitive unless your system specifies that behavior.
6. **Replace the record with a hand-written class:** Implement `Money` as a `final class` with `private final` fields and manual `equals`/`hashCode`/`compareTo`. Rerun the same tests and compare code size and maintenance risks.
7. **Test collections:** Add 50 equivalent amount representations and count `HashSet` and `TreeSet` elements after normalization. Do not infer value equality from hash codes alone.

### Self-assessment rubric — 10 points

| Criterion | Points |
|---|---:|
| Data is normalized, validated, and immutable after construction | 2 |
| Identity/value distinction is correct; equals uses meaningful components | 2 |
| hashCode is consistent; HashSet/HashMap do not duplicate equal keys | 2 |
| compareTo agrees with equals; TreeSet behaves correctly | 2 |
| Correctly handles BigDecimal scale, mutable alias, and currency traps | 2 |

**Completion criteria:** Create two distinct value objects from differently written but semantically equivalent inputs and prove they are equal, have the same hash, behave consistently in hash/sorted collections, and cannot be modified through aliases. Also explain why entities and value objects should not automatically share the same equality policy.

# Fixtures, Object Builders, and Scenario-Specific Meaningful Data

## 1. Why Is Test Data Part of Test Design?

Many Java/Spring Boot tests start by constructing an object with 15–30 fields, filling in a few random strings, and calling a service. Over time, hundreds of tests duplicate the same data setup; when a DTO changes its constructor, the entire suite breaks. Worse, meaningless default data can cause a test to **PASS even when the business logic is wrong**.

For example, when testing free shipping starting at 100.00, using a cart with a subtotal of 1000.00 only proves a case far away from the boundary. A comparison bug using `> 100` instead of `>= 100` will go undetected. Values such as `99.99`, `100.00`, and `100.01` are what distinguish the rule.

This lesson teaches three related techniques:

- **Fixture**: prepared data or object structures so a test has a consistent starting point.
- **Test Data Builder**: a builder with valid defaults that lets you specify only the attributes that need to change for each scenario.
- **Scenario-specific data**: data chosen **because it distinguishes business outcomes**, not merely “having enough objects to run”.

We will apply these in Java 17 and Spring Boot 3.5 with JUnit Jupiter, AssertJ, Mockito, `@WebMvcTest`, `@DataJpaTest`, and a full-context HTTP test. The content also covers `@Sql`, Testcontainers, `Clock`, random seeds, data isolation, privacy, and common anti-patterns.

### Lesson Goals

1. Distinguish **fixture factory**, **Object Mother**, **Test Data Builder**, **production builder**, and **database seed fixture**.
2. Create **a minimal, valid default**, then override only the meaningful fields mentioned in the test name.
3. Use values at **the boundary and both sides of the boundary**, rather than arbitrary data.
4. Keep fixtures **deterministic**, isolated between tests, and free of shared mutable objects.
5. Know when a test must create an **invalid object** instead of letting the builder block invalid cases.
6. Use `@ParameterizedTest`/`@CsvSource`/`@MethodSource` to build readable scenario tables.
7. Test JSON APIs using request fixtures serialized with Jackson rather than hand-concatenating JSON strings for the happy path.
8. Test JPA mappings with persisted fixtures, `flush`/`clear`, and default rollback.
9. Understand that fixtures do not replace integration infrastructure: H2 differs from PostgreSQL, and an in-memory list differs from a real database.
10. Avoid test data containing personal information or production secrets; use synthetic fixtures.

**Core principle:** Fixtures must make **Given** explicit. A good test does not merely create enough data to run; it creates data that makes deviations in business rules observable.

## 2. Terminology and Boundaries

### 2.1. What Is a Fixture?

In testing terminology, a *test fixture* can refer to the entire **prepared input state/environment** for a test: object graphs, database rows, files, clock, fake gateways, or configuration. In this lesson, we focus on **data** and how to construct it.

A fixture can be:

~~~java
Cart cart = new Cart(
        "customer-001",
        CustomerTier.REGULAR,
        List.of(new CartLine(
                "BOOK-001", 2, new BigDecimal("50.00"))),
        null);
~~~

This snippet assumes the `Cart` and `CartLine` records and `CustomerTier` enum from the project in Section 8. It is meaningful when proving a cart is **exactly at the 100.00 threshold**. However, repeating those 10 lines in every test creates substantial noise.

### 2.2. Fixture Factory

A factory uses methods named after scenarios:

~~~java
Cart defaultCart = CartFixtures.validCart();
Cart below = CartFixtures.belowShippingThreshold();
Cart at = CartFixtures.atShippingThreshold();
~~~

Benefit: the method name explains the meaning of the data while avoiding constructor repetition. However, if you create hundreds of factory methods combining every field, the number of methods explodes and becomes hard to maintain.

### 2.3. Object Mother

*Object Mother* is a pattern for organizing factory methods that provide canonical domain objects: `aRegularCustomer()`, `aVipCustomer()`, `anUnpaidOrder()`, etc.

Strength: tests read like a story. Weakness: it easily turns into a bloated `TestData` class with dozens of interdependent methods where nobody knows which implicit fields are being populated.

### 2.4. Test Data Builder

A builder starts from **a valid object** and allows scenario-specific overrides:

~~~java
Cart cart = CartFixtures.aCart()
        .withCustomerId("customer-002")
        .vip()
        .withLine(CartFixtures.line(
                "BOOK-002", 2, "60.00"))
        .build();
~~~

Default data lives inside the builder, while the test displays **only the relevant characteristics**: VIP customer, subtotal 120.00. When default validity changes, the builder is updated in one central place.

### 2.5. Production Builders Differ from Test Builders

Production builders typically support:
- Construction APIs for domain entities/DTOs.
- Business invariants/validation.
- Optional fields and immutable objects.
- Official APIs called by production code.

**Test Data Builders** support:
- Valid defaults to reduce noise.
- Quick single-attribute overrides.
- Creating *invalid test data* to test validation.
- Keeping production models from bloating just to serve tests.

If you use Lombok `@Builder`/`@SuperBuilder` in production, you can still use it for tests; however, you must verify valid defaults, required fields, inheritance, and constructor invariants. Do not add Lombok to a project just for a simple two-field fixture.

### 2.6. Database Seeds Are Not Object Fixtures

`new PurchaseRecord(...)` in memory is different from a row **that has been INSERTed into and queried from the database**. With `@DataJpaTest`, use `saveAndFlush`, `TestEntityManager.persistAndFlush`, or `@Sql`, and then verify from a fresh persistence context. Calling a constructor alone does not test JPA mappings, transactions, constraints, or query methods.

## 3. Designing Meaningful Data Around Business Rules

### 3.1. One Scenario Is One Observable Difference

Suppose the product has the following rules:

- Subtotal = sum of `unitPrice × quantity`.
- Shipping fee is **15.00** if subtotal is **less than 100.00**.
- Shipping fee is **0.00** when subtotal is **100.00 or more**.
- `VIP` customers receive **10% off the subtotal**, rounded to 2 decimal places.
- Coupon `SAVE10` deducts an additional **10.00**, but total discount cannot exceed the subtotal.
- Price, quantity, `customerId`, and coupon must be valid.
- Total = subtotal − discount + shipping.

With these rules, the following fixtures are meaningful:

| Scenario | Data | Bug Detected |
| --- | --- | --- |
| Below threshold | Subtotal 99.99 | Must not get free shipping |
| Exactly at threshold | Subtotal 100.00 | Detects `>` instead of `>=` |
| Above threshold | Subtotal 100.01 | Verifies free-shipping branch |
| VIP | Subtotal 120.00, tier VIP | Deducts exactly 12.00 |
| Coupon | Subtotal 120.00, SAVE10 | Deducts 10.00, total 110.00 |
| VIP + coupon | Subtotal 120.00, VIP, SAVE10 | Combined discount 22.00, total 98.00 |
| Coupon larger than subtotal | Subtotal 5.00, SAVE10 | Discount capped at 5.00, never negative |
| Invalid quantity | Quantity 0 | Tests validation instead of normal multiplication |
| Negative price | Unit price -1.00 | Prevents computing an invalid total |
| Nonexistent coupon | BADCODE | Rejects input per contract |
| No lines | Empty list | Prevents treating an empty cart as a valid order |

A fixture with subtotal 1000.00, tier REGULAR, and coupon null **cannot** replace the table above.

### 3.2. The “One Intentional Variable” Rule

When testing VIP customers, keep other variables constant:
- Same subtotal.
- Same quantity and SKU.
- Same null coupon.
- Change only tier REGULAR ↔ VIP.

When testing the shipping fee threshold, keep tier REGULAR, coupon null, and quantity 1, changing only `unitPrice` among 99.99, 100.00, and 100.01.

This is how you isolate the cause. If you change tier, coupon, quantity, SKU, and date all at once, a test failure makes it hard to tell which business rule broke.

### 3.3. Meaningful Values Beat Magic Numbers

The name `oneHundredAndOne()` is usually less clear than `atFreeShippingThreshold()`. A test value should carry meaning in the business vocabulary:

~~~java
Cart atThreshold = CartFixtures.atShippingThreshold();
Quote result = pricing.quote(atThreshold);
assertThat(result.shipping())
        .isEqualByComparingTo("0.00");
~~~

The test reads like a requirement. If the rule changes from 100.00 to 150.00, the factory should be updated by an intentional review decision—**do not bulk-update expected values** without understanding the new contract.

### 3.4. Null, Empty, Missing, and Zero

These cases are distinct:

| Value | Possible Meaning |
| --- | --- |
| `null` coupon | No coupon applied |
| `""` coupon | User sent an empty string; may be invalid |
| `"BADCODE"` | Nonexistent coupon |
| `quantity=0` | Invalid input |
| `unitPrice=0.00` | May be valid for free promotional items or forbidden by domain |
| `lines=[]` | Empty cart, must be handled explicitly |
| JSON missing `couponCode` | Jackson may pass null; contract must be known |
| JSON with `"couponCode":null` | Property is present but null |

“Happy path” fixtures should avoid arbitrary nulls in required fields; **negative fixtures** should intentionally construct invalid cases to test the exact validation boundary.

## 4. Test Data Must Be Deterministic, Isolated, and Safe

### 4.1. Deterministic

The same input, code, and dependencies/configuration must produce the same test result. Avoid:
- `LocalDateTime.now()` directly in expected values.
- `UUID.randomUUID()` if you later compare the ID against a fixed constant.
- Unseeded `new Random()` in tests that require reproducibility.
- Data fetched from the internet or a production DB.
- Results that depend on the execution order of JUnit methods.

Use `Instant.parse("2026-01-15T08:00:00Z")` or inject `Clock.fixed(...)` when business logic depends on time.

### 4.2. Clock.fixed

~~~java
Clock fixed = Clock.fixed(
        Instant.parse("2026-01-15T08:00:00Z"),
        ZoneOffset.UTC);

Instant createdAt = Instant.now(fixed);
assertThat(createdAt)
        .isEqualTo(Instant.parse("2026-01-15T08:00:00Z"));
~~~

This is a snippet inside a test with imports for `java.time.Clock`, `Instant`, `ZoneOffset`, and AssertJ. Do not use the OS clock for expected values when the logic only needs a fixed instant. For deadline/expiry logic, test before, exactly at, and after the deadline.

### 4.3. Seeded Randomness and Property Testing

For example-based tests, choose fixed, readable fixtures. If you want to generate hundreds of cases, consider property-based testing with jqwik or QuickTheories using a reproducible seed and proper constraints.

~~~java
Random random = new Random(12345L);
int quantity = random.nextInt(1, 11);
~~~

This snippet illustrates Java 17. A seed makes the random sequence reproducible, but for a test with a specific requirement like shipping fee at 100.00, **fixed boundary data is better than random data**. Do not generate names/IDs that could collide in parallel integration tests without a safe namespace.

### 4.4. Do Not Share Mutable Fixtures

Wrong:

~~~java
static final List<CartLine> SHARED_LINES =
        new ArrayList<>();

@BeforeEach
void setUp() {
    SHARED_LINES.add(...);  // subsequent tests may accumulate state
}
~~~

This is an anti-pattern. A fixture should create a **new instance for each test**; builders are created fresh each time. For JPA entities, strictly avoid sharing the same managed entity across tests: IDs, persistence contexts, lazy proxies, and dirty checking make state unpredictable.

### 4.5. Immutable Snapshots

Java records are well suited as request/result DTOs. For list fields, the record compact constructor should make a defensive copy:

~~~java
public record Cart(
        String customerId,
        CustomerTier tier,
        List<CartLine> lines,
        String couponCode) {

    public Cart {
        lines = List.copyOf(lines);
    }
}
~~~

`List.copyOf` prevents callers from mutating the list after creating a cart, though it does not deep-copy mutable elements. In this project, `CartLine` is also a record with an immutable `BigDecimal`, so the graph is stable.

### 4.6. Do Not Use Production Data

Fixtures must never contain PII, real passwords, real tokens, real card numbers, or un-anonymized database dumps. Create synthetic customers, test SKUs, and example email domains (if any). You can use identifiers like `customer-test-001`—you do not need real personal information to catch a bug in total calculation.

## 5. When to Choose a Fixture Factory, Builder, or @Sql?

| What to Test | How to Create Data | Reason |
| --- | --- | --- |
| A pure Java function | `CartFixtures.aCart().build()` | No Spring context needed |
| Multiple business scenarios | Named factory + builder overrides | Clear names + minimal duplication |
| MVC controller receiving JSON | Serialize request fixture with ObjectMapper | Tests HTTP/Jackson, no string concatenation |
| Controller behavior when service returns a result | `@MockitoBean` service + result fixture | Preserves the MVC slice |
| JPA entity mapping | Entity fixture + `persistAndFlush`/`clear` | Verifies persisted state |
| Multiple rows with foreign-key relationships | Builder graph or `@Sql` scripts | Shows relationships clearly; checks constraints |
| Large/versioned standard data | `@Sql`/test resource JSON/CSV/LDIF | Review diffs like a contract |
| PostgreSQL-specific SQL/queries | Testcontainers PostgreSQL + real schema | H2 is not equivalent |
| Time/expiry tests | `Clock.fixed` / injectable `Clock` | Independent of wall clock |
| Complex valid/invalid inputs | Dedicated builder for negative cases | Does not break default fixtures |
| Data with thousands of variants | Parameterized/property tests | Covers large space, reproducible |

Not every object needs a builder. A two-field record with a clear constructor is often easier to read than an 80-line builder. Choose abstractions to **reduce noise and highlight requirements**, not to maximize the number of helper classes.

## 6. Using Fixtures for Arrange–Act–Assert

A well-structured test:

~~~java
@Test
void vipGetsTenPercentDiscount() {
    // Arrange: highlight only the condition being tested
    Cart cart = CartFixtures.vipEligible();

    // Act: call the system under test
    Quote actual = pricing.quote(cart);

    // Assert: verify the business result
    assertThat(actual.discount())
            .isEqualByComparingTo("12.00");
}
~~~

Compare with:

~~~java
@Test
void test1() {
    String a = "X";
    int b = 2;
    BigDecimal c = new BigDecimal("60.00");
    // many other unrelated fields...
    assertThat(pricing.quote(new Cart(...)).discount())
            .isEqualByComparingTo("12.00");
}
~~~

The first version makes Given/When/Then and the rule under test immediately clear. The second forces the reader to compute `b * c` backwards and guess the intent.

### 6.1. Assertions Should Not Duplicate the Algorithm

If the expected value is computed using **the same production code/algorithm**, the test can repeat the bug:

~~~java
// Avoid this in boundary tests:
BigDecimal expected = cartSubtotal(cart)
        .multiply(VIP_RATE);
assertThat(pricing.quote(cart).discount())
        .isEqualByComparingTo(expected);
~~~

If `cartSubtotal` is wrong in the same way in both the test and production, the assertion will not catch it. For simple scenarios, use concrete expected values and explain why: 120.00 × 10% = 12.00.

### 6.2. A Test Can Assert Multiple Things, but Must Focus on One Behavior

A pricing test can check `subtotal`, `discount`, `shipping`, and `total` together because they describe the same quote. However, do not mix assertions for emails, repositories, HTTP headers, and DB transactions in a unit test verifying a pricing function. Those boundaries deserve their own tests.

## 7. Complete Spring Boot Project: Java 17 and Maven

### 7.1. Project Goal

We will implement a cart-quoting application. Rules as in Section 3:
- Regular subtotal 40.00 → shipping 15.00 → total 55.00.
- Regular subtotal 99.99 → shipping 15.00 → total 114.99.
- Regular subtotal 100.00 → shipping 0.00.
- VIP subtotal 120.00 → discount 12.00 → total 108.00.
- Coupon `SAVE10` on subtotal 120.00 → discount 10.00 → total 110.00.
- VIP + coupon on subtotal 120.00 → discount 22.00 → total 98.00.
- If the coupon exceeds the subtotal, discount is capped at the subtotal (non-negative).
- Invalid input throws `IllegalArgumentException` at the service layer.

The same repo contains a `PurchaseRecord` entity to demonstrate JPA persisted fixtures, while the quote service **does not depend on the repository**. We intentionally separate them to compare pure Java fixtures and database fixtures without dragging JPA into simple pricing calculations.

### 7.2. File Tree

~~~text
fixture-builder-lab/
├── pom.xml
├── src/main/resources/application.properties
├── src/main/java/com/example/fixturelab/
│   ├── FixtureLabApplication.java
│   ├── CustomerTier.java
│   ├── CartLine.java
│   ├── Cart.java
│   ├── Quote.java
│   ├── CheckoutPricingService.java
│   ├── QuoteController.java
│   ├── PurchaseRecord.java
│   └── PurchaseRecordRepository.java
└── src/test/java/com/example/fixturelab/
    ├── support/
    │   ├── CartFixtures.java
    │   └── PurchaseRecordFixtures.java
    ├── CartFixturesTest.java
    ├── CheckoutPricingServiceTest.java
    ├── QuoteControllerJsonTest.java
    ├── PurchaseRecordRepositoryTest.java
    └── QuoteHttpIntegrationTest.java
~~~

All production Java files reside in `com.example.fixturelab`; the two fixture helpers reside in `com.example.fixturelab.support`. They live under `src/test/java` and are **not packaged into the production artifact**. There are no static global mutable entities.

### 7.3. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.16</version>
    <relativePath/>
  </parent>
  <groupId>com.example</groupId>
  <artifactId>fixture-builder-lab</artifactId>
  <version>1.0.0</version>
  <properties>
    <java.version>17</java.version>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-data-jpa</artifactId>
    </dependency>
    <dependency>
      <groupId>com.h2database</groupId>
      <artifactId>h2</artifactId>
      <scope>runtime</scope>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-test</artifactId>
      <scope>test</scope>
    </dependency>
  </dependencies>
  <build>
    <plugins>
      <plugin>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-maven-plugin</artifactId>
      </plugin>
    </plugins>
  </build>
</project>
~~~

The Spring Boot parent/BOM manages Spring Framework, JUnit Jupiter, AssertJ, Mockito, Jackson, and Hibernate. `@MockitoBean` in the example belongs to Spring Framework 6.2 and works with Boot 3.5. Do not add the legacy `@MockBean` just to avoid updating an import.

### 7.4. application.properties

`src/main/resources/application.properties`:

~~~properties
spring.datasource.url=jdbc:h2:mem:fixture_lab;DB_CLOSE_DELAY=-1
spring.datasource.username=sa
spring.datasource.password=
spring.jpa.hibernate.ddl-auto=create-drop
spring.jpa.open-in-view=false
spring.jpa.show-sql=false
~~~

`create-drop` is suitable for an H2 lab, not for production. `@DataJpaTest` may replace the datasource with another embedded DB via auto-configuration, but with the same goal: an isolated database during tests.

### 7.5. FixtureLabApplication.java

~~~java
package com.example.fixturelab;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class FixtureLabApplication {

    public static void main(String[] args) {
        SpringApplication.run(FixtureLabApplication.class, args);
    }
}
~~~

### 7.6. CustomerTier.java

~~~java
package com.example.fixturelab;

public enum CustomerTier {
    REGULAR,
    VIP
}
~~~

This enum makes the two business branches explicit. Do not keep both a boolean `isVip` field and `CustomerTier` to avoid contradictory test inputs.

### 7.7. CartLine.java

~~~java
package com.example.fixturelab;

import java.math.BigDecimal;

public record CartLine(
        String sku,
        int quantity,
        BigDecimal unitPrice) {
}
~~~

The record intentionally **does not block invalid input in the constructor**. The goal is to allow fixtures to create a line with quantity 0 or a negative price to test validation in `CheckoutPricingService`. If a production domain uses validated value objects (where the constructor throws immediately), negative tests must test **that constructor directly** or HTTP binding/validation, rather than forcing a builder to bypass impossible invariants.

### 7.8. Cart.java

~~~java
package com.example.fixturelab;

import java.util.List;

public record Cart(
        String customerId,
        CustomerTier tier,
        List<CartLine> lines,
        String couponCode) {

    public Cart {
        lines = List.copyOf(lines);
    }
}
~~~

The compact constructor protects against external list mutations altering a fixture after build. `List.copyOf` does not accept a null list or null elements; therefore, the `lines=null` case is rejected at record construction rather than in the service. A test needing to verify missing/null JSON can use raw JSON input / HTTP binding tests per the contract, rather than forcing an object builder to construct an invalid record.

### 7.9. Quote.java

~~~java
package com.example.fixturelab;

import java.math.BigDecimal;

public record Quote(
        BigDecimal subtotal,
        BigDecimal discount,
        BigDecimal shipping,
        BigDecimal total) {
}
~~~

The result is a value object; use `BigDecimal` for money instead of `double`. When comparing numeric values, AssertJ `isEqualByComparingTo` avoids scale mismatches between `19.9` and `19.90` when scale is not part of the contract.

### 7.10. CheckoutPricingService.java

~~~java
package com.example.fixturelab;

import java.math.BigDecimal;
import java.math.RoundingMode;

import org.springframework.stereotype.Service;

@Service
public class CheckoutPricingService {

    private static final BigDecimal FREE_SHIPPING_AT =
            new BigDecimal("100.00");
    private static final BigDecimal SHIPPING_FEE =
            new BigDecimal("15.00");
    private static final BigDecimal VIP_RATE =
            new BigDecimal("0.10");
    private static final BigDecimal COUPON_VALUE =
            new BigDecimal("10.00");

    public Quote quote(Cart cart) {
        if (cart == null || cart.customerId() == null
                || cart.customerId().isBlank()) {
            throw new IllegalArgumentException(
                    "customerId must be present");
        }
        if (cart.tier() == null) {
            throw new IllegalArgumentException(
                    "tier must be present");
        }
        if (cart.lines().isEmpty()) {
            throw new IllegalArgumentException(
                    "cart must contain at least one line");
        }

        BigDecimal subtotal = BigDecimal.ZERO;
        for (CartLine line : cart.lines()) {
            if (line == null || line.sku() == null
                    || line.sku().isBlank()) {
                throw new IllegalArgumentException(
                        "sku must be present");
            }
            if (line.quantity() <= 0) {
                throw new IllegalArgumentException(
                        "quantity must be positive");
            }
            if (line.unitPrice() == null
                    || line.unitPrice().signum() < 0
                    || line.unitPrice().scale() > 2) {
                throw new IllegalArgumentException(
                        "unitPrice must be non-negative with at most 2 decimals");
            }
            subtotal = subtotal.add(
                    line.unitPrice().multiply(
                            BigDecimal.valueOf(line.quantity())));
        }

        if (cart.couponCode() != null
                && !"SAVE10".equals(cart.couponCode())) {
            throw new IllegalArgumentException(
                    "unsupported coupon");
        }

        BigDecimal vipDiscount = cart.tier() == CustomerTier.VIP
                ? subtotal.multiply(VIP_RATE).setScale(
                        2, RoundingMode.HALF_UP)
                : BigDecimal.ZERO;
        BigDecimal couponDiscount =
                "SAVE10".equals(cart.couponCode())
                        ? COUPON_VALUE : BigDecimal.ZERO;

        BigDecimal discount = vipDiscount.add(couponDiscount)
                .min(subtotal)
                .setScale(2, RoundingMode.HALF_UP);

        BigDecimal shipping =
                subtotal.compareTo(FREE_SHIPPING_AT) >= 0
                        ? BigDecimal.ZERO : SHIPPING_FEE;

        BigDecimal total = subtotal.subtract(discount)
                .add(shipping)
                .setScale(2, RoundingMode.HALF_UP);

        return new Quote(
                subtotal.setScale(2, RoundingMode.HALF_UP),
                discount,
                shipping.setScale(2, RoundingMode.HALF_UP),
                total);
    }
}
~~~

Business decisions are intentionally small enough that expected values can be calculated independently by hand:
- The shipping threshold applies to the **subtotal before discount**.
- VIP takes 10% off the subtotal and uses `HALF_UP` rounding.
- Coupon can be combined with the VIP discount.
- Total discount does not exceed the subtotal.
- All monetary results display scale 2; no floating-point arithmetic is used.

In production, currency, tax, exchange rates, shipping rules, and coupon eligibility must be clearly defined; this is a lab for learning fixture/branch testing, not a complete checkout engine.

### 7.11. QuoteController.java

~~~java
package com.example.fixturelab;

import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/quotes")
public class QuoteController {

    private final CheckoutPricingService pricing;

    public QuoteController(CheckoutPricingService pricing) {
        this.pricing = pricing;
    }

    @PostMapping
    public Quote quote(@RequestBody Cart cart) {
        return pricing.quote(cart);
    }
}
~~~

The controller receives JSON mapped to `Cart` via Jackson. The example omits an error handler for invalid requests; unit tests check invalid inputs directly on the service, while the API may return a default error status if the exception is unmapped. For a real API to return 400 with a standard error contract, add `@RestControllerAdvice` or bean validation and test it separately.

### 7.12. PurchaseRecord.java

~~~java
package com.example.fixturelab;

import java.math.BigDecimal;
import java.time.Instant;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "purchase_records")
public class PurchaseRecord {

    @Id
    @Column(name = "reference_code", length = 80)
    private String referenceCode;

    @Column(name = "customer_id", nullable = false, length = 80)
    private String customerId;

    @Column(name = "order_total", nullable = false,
            precision = 12, scale = 2)
    private BigDecimal total;

    @Column(nullable = false, length = 20)
    private String status;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    protected PurchaseRecord() {
        // JPA constructor
    }

    public PurchaseRecord(
            String referenceCode,
            String customerId,
            BigDecimal total,
            String status,
            Instant createdAt) {
        this.referenceCode = referenceCode;
        this.customerId = customerId;
        this.total = total;
        this.status = status;
        this.createdAt = createdAt;
    }

    public String getReferenceCode() {
        return referenceCode;
    }

    public String getCustomerId() {
        return customerId;
    }

    public BigDecimal getTotal() {
        return total;
    }

    public String getStatus() {
        return status;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }
}
~~~

A JPA entity is a **mutable/persistence-managed model**, different from the `Cart` Java record. Do not share the same managed instance across tests. Use an assigned `referenceCode` so fixtures have explicit identity and tests do not depend on database-generated sequences.

### 7.13. PurchaseRecordRepository.java

~~~java
package com.example.fixturelab;

import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;

public interface PurchaseRecordRepository
        extends JpaRepository<PurchaseRecord, String> {

    List<PurchaseRecord> findByStatus(String status);
}
~~~

`findByStatus` is a derived query; the JPA test verifies persistence mapping and the actual query. You cannot prove the query works merely by mocking the repository to return a `List`.

## 8. Test Fixtures in src/test/java

### 8.1. CartFixtures.java

`src/test/java/com/example/fixturelab/support/CartFixtures.java`:

~~~java
package com.example.fixturelab.support;

import java.math.BigDecimal;
import java.util.List;

import com.example.fixturelab.Cart;
import com.example.fixturelab.CartLine;
import com.example.fixturelab.CustomerTier;

public final class CartFixtures {

    private CartFixtures() {
    }

    public static CartLine line(
            String sku, int quantity, String unitPrice) {
        return new CartLine(
                sku, quantity, new BigDecimal(unitPrice));
    }

    public static CartBuilder aCart() {
        return new CartBuilder();
    }

    public static Cart validCart() {
        return aCart().build();
    }

    public static Cart belowShippingThreshold() {
        return aCart()
                .withLine(line("BOOK-001", 1, "99.99"))
                .build();
    }

    public static Cart atShippingThreshold() {
        return aCart()
                .withLine(line("BOOK-001", 2, "50.00"))
                .build();
    }

    public static Cart vipEligible() {
        return aCart()
                .vip()
                .withLine(line("BOOK-001", 2, "60.00"))
                .build();
    }

    public static Cart couponEligible() {
        return aCart()
                .withLine(line("BOOK-001", 2, "60.00"))
                .withCouponCode("SAVE10")
                .build();
    }

    public static Cart invalidQuantity() {
        return aCart()
                .withLine(line("BOOK-001", 0, "40.00"))
                .build();
    }

    public static final class CartBuilder {

        private String customerId = "customer-test-001";
        private CustomerTier tier = CustomerTier.REGULAR;
        private List<CartLine> lines = List.of(
                line("BOOK-001", 1, "40.00"));
        private String couponCode;

        private CartBuilder() {
        }

        public CartBuilder withCustomerId(String value) {
            this.customerId = value;
            return this;
        }

        public CartBuilder withTier(CustomerTier value) {
            this.tier = value;
            return this;
        }

        public CartBuilder vip() {
            return withTier(CustomerTier.VIP);
        }

        public CartBuilder withLine(CartLine value) {
            this.lines = List.of(value);
            return this;
        }

        public CartBuilder withLines(CartLine... values) {
            this.lines = List.of(values);
            return this;
        }

        public CartBuilder withCouponCode(String value) {
            this.couponCode = value;
            return this;
        }

        public Cart build() {
            return new Cart(
                    customerId,
                    tier,
                    List.copyOf(lines),
                    couponCode);
        }
    }
}
~~~

**Why is this approach effective?**
- `aCart()` returns a **new builder** each time, with no static mutable instance.
- Defaults include a customer, tier, one valid line, and a null coupon.
- Named scenarios cover the most common cases without generating every possible combination.
- `withLine` replaces all lines, avoiding unexpected accumulation from defaults.
- `withLines` supports multi-line scenarios when needed; empty varargs produce an empty list to test validation.
- `build()` returns a `Cart` with a defensive copy. Subsequent edits to the builder do not mutate previously built objects.
- `invalidQuantity()` intentionally creates quantity 0 to test validation. A builder must not silently coerce quantity to 1 when a test needs invalid input.
- Money values pass strings to `BigDecimal` rather than `new BigDecimal(0.1)` to avoid floating-point representation issues.

**An intentional limitation:** `customerId` and SKU are fixed. When integration tests run in parallel against persisted data, override identity with per-test values (or create a namespace) instead of sharing default record keys across tests.

### 8.2. PurchaseRecordFixtures.java

`src/test/java/com/example/fixturelab/support/PurchaseRecordFixtures.java`:

~~~java
package com.example.fixturelab.support;

import java.math.BigDecimal;
import java.time.Instant;

import com.example.fixturelab.PurchaseRecord;

public final class PurchaseRecordFixtures {

    private PurchaseRecordFixtures() {
    }

    public static PurchaseBuilder aPurchase() {
        return new PurchaseBuilder();
    }

    public static final class PurchaseBuilder {

        private String referenceCode = "fixture-default-001";
        private String customerId = "customer-test-001";
        private BigDecimal total = new BigDecimal("100.00");
        private String status = "NEW";
        private Instant createdAt =
                Instant.parse("2026-01-15T08:00:00Z");

        private PurchaseBuilder() {
        }

        public PurchaseBuilder withReferenceCode(String value) {
            this.referenceCode = value;
            return this;
        }

        public PurchaseBuilder withCustomerId(String value) {
            this.customerId = value;
            return this;
        }

        public PurchaseBuilder withTotal(String value) {
            this.total = new BigDecimal(value);
            return this;
        }

        public PurchaseBuilder withStatus(String value) {
            this.status = value;
            return this;
        }

        public PurchaseBuilder withCreatedAt(Instant value) {
            this.createdAt = value;
            return this;
        }

        public PurchaseRecord build() {
            return new PurchaseRecord(
                    referenceCode,
                    customerId,
                    total,
                    status,
                    createdAt);
        }
    }
}
~~~

For database fixtures:
- `referenceCode` must be overridden individually when inserting multiple rows in the same test.
- `createdAt` is a fixed instant, never calling the wall clock.
- `total` uses a `BigDecimal` string.
- Do not pretend an entity is “persisted” just by instantiating it; tests must call `persistAndFlush` or repository `saveAndFlush`.
- The builder does not open transactions, call repositories, or hold a static `EntityManager`. **Fixture construction** is separate from **fixture persistence**.
- Avoid enforcing business validation across all builder fields; some negative tests need missing values, invalid statuses, or nulls to test validation and constraints.

## 9. Verifying Builder and Fixture Independence

### 9.1. CartFixturesTest.java

`src/test/java/com/example/fixturelab/CartFixturesTest.java`:

~~~java
package com.example.fixturelab;

import org.junit.jupiter.api.Test;

import static com.example.fixturelab.support.CartFixtures.aCart;
import static com.example.fixturelab.support.CartFixtures.line;
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class CartFixturesTest {

    @Test
    void defaultFixtureIsValidAndPredictable() {
        Cart cart = aCart().build();

        assertThat(cart.customerId())
                .isEqualTo("customer-test-001");
        assertThat(cart.tier())
                .isEqualTo(CustomerTier.REGULAR);
        assertThat(cart.lines()).hasSize(1);
        assertThat(cart.lines().get(0).unitPrice())
                .isEqualByComparingTo("40.00");
        assertThat(cart.couponCode()).isNull();
    }

    @Test
    void changesToOneBuilderDoNotChangeAnotherFixture() {
        Cart special = aCart()
                .vip()
                .withCouponCode("SAVE10")
                .build();

        Cart standard = aCart().build();

        assertThat(special.tier())
                .isEqualTo(CustomerTier.VIP);
        assertThat(special.couponCode())
                .isEqualTo("SAVE10");

        assertThat(standard.tier())
                .isEqualTo(CustomerTier.REGULAR);
        assertThat(standard.couponCode()).isNull();
    }

    @Test
    void buildingThenOverridingDoesNotMutateOldCart() {
        var builder = aCart();
        Cart original = builder.build();

        Cart changed = builder
                .withLine(line("BOOK-002", 2, "60.00"))
                .build();

        assertThat(original.lines().get(0).sku())
                .isEqualTo("BOOK-001");
        assertThat(original.lines().get(0).quantity())
                .isEqualTo(1);

        assertThat(changed.lines().get(0).sku())
                .isEqualTo("BOOK-002");
        assertThat(changed.lines().get(0).quantity())
                .isEqualTo(2);
    }

    @Test
    void builtCartDoesNotExposeMutableList() {
        Cart cart = aCart().build();

        assertThatThrownBy(() ->
                cart.lines().add(line("EXTRA", 1, "1.00")))
                .isInstanceOf(UnsupportedOperationException.class);
    }
}
~~~

Testing fixture helpers is not necessary for every project, but when a builder is reused across hundreds of tests, a few simple assertions catch **shared-state bugs**, wrong defaults, or mutation leakage.

### 9.2. Why Not Use a Static Cart Singleton?

Even if `static final Cart` is a record holding immutable components, safe against mutation, tests need flexible overrides where a fresh object builder is easier to control. If `static final PurchaseRecord ENTITY` is a mutable JPA entity, sharing it is even more dangerous due to managed/detached/ID state and the persistence context.

**Default recommendation:** static **factory methods**, never static **mutable entity instances**.

## 10. Unit Tests Using Meaningful Fixtures

### 10.1. CheckoutPricingServiceTest.java

`src/test/java/com/example/fixturelab/CheckoutPricingServiceTest.java`:

~~~java
package com.example.fixturelab;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;

import static com.example.fixturelab.support.CartFixtures.aCart;
import static com.example.fixturelab.support.CartFixtures.atShippingThreshold;
import static com.example.fixturelab.support.CartFixtures.belowShippingThreshold;
import static com.example.fixturelab.support.CartFixtures.couponEligible;
import static com.example.fixturelab.support.CartFixtures.invalidQuantity;
import static com.example.fixturelab.support.CartFixtures.line;
import static com.example.fixturelab.support.CartFixtures.validCart;
import static com.example.fixturelab.support.CartFixtures.vipEligible;
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class CheckoutPricingServiceTest {

    private final CheckoutPricingService pricing =
            new CheckoutPricingService();

    @Test
    void defaultCartHasPaidShipping() {
        Quote result = pricing.quote(validCart());

        assertThat(result.subtotal())
                .isEqualByComparingTo("40.00");
        assertThat(result.discount())
                .isEqualByComparingTo("0.00");
        assertThat(result.shipping())
                .isEqualByComparingTo("15.00");
        assertThat(result.total())
                .isEqualByComparingTo("55.00");
    }

    @Test
    void belowThresholdStillPaysShipping() {
        Quote result = pricing.quote(
                belowShippingThreshold());

        assertThat(result.subtotal())
                .isEqualByComparingTo("99.99");
        assertThat(result.shipping())
                .isEqualByComparingTo("15.00");
        assertThat(result.total())
                .isEqualByComparingTo("114.99");
    }

    @Test
    void exactlyAtThresholdGetsFreeShipping() {
        Quote result = pricing.quote(atShippingThreshold());

        assertThat(result.subtotal())
                .isEqualByComparingTo("100.00");
        assertThat(result.shipping())
                .isEqualByComparingTo("0.00");
        assertThat(result.total())
                .isEqualByComparingTo("100.00");
    }

    @ParameterizedTest(name = "subtotal {0} gives shipping {1}")
    @CsvSource({
            "99.99, 15.00, 114.99",
            "100.00, 0.00, 100.00",
            "100.01, 0.00, 100.01"
    })
    void shippingBoundaryOnBothSides(
            String price,
            String expectedShipping,
            String expectedTotal) {
        Cart cart = aCart()
                .withLine(line("BOOK-001", 1, price))
                .build();

        Quote result = pricing.quote(cart);

        assertThat(result.shipping())
                .isEqualByComparingTo(expectedShipping);
        assertThat(result.total())
                .isEqualByComparingTo(expectedTotal);
    }

    @Test
    void vipGetsTenPercentOfSubtotal() {
        Quote result = pricing.quote(vipEligible());

        assertThat(result.subtotal())
                .isEqualByComparingTo("120.00");
        assertThat(result.discount())
                .isEqualByComparingTo("12.00");
        assertThat(result.shipping())
                .isEqualByComparingTo("0.00");
        assertThat(result.total())
                .isEqualByComparingTo("108.00");
    }

    @Test
    void couponChangesOnlyTheExpectedRule() {
        Quote result = pricing.quote(couponEligible());

        assertThat(result.discount())
                .isEqualByComparingTo("10.00");
        assertThat(result.total())
                .isEqualByComparingTo("110.00");
    }

    @Test
    void vipAndCouponCanBeCombined() {
        Cart cart = aCart()
                .vip()
                .withLine(line("BOOK-001", 2, "60.00"))
                .withCouponCode("SAVE10")
                .build();

        Quote result = pricing.quote(cart);

        assertThat(result.discount())
                .isEqualByComparingTo("22.00");
        assertThat(result.total())
                .isEqualByComparingTo("98.00");
    }

    @Test
    void couponCannotMakeSubtotalNegative() {
        Cart cart = aCart()
                .withLine(line("GIFT", 1, "5.00"))
                .withCouponCode("SAVE10")
                .build();

        Quote result = pricing.quote(cart);

        assertThat(result.discount())
                .isEqualByComparingTo("5.00");
        assertThat(result.shipping())
                .isEqualByComparingTo("15.00");
        assertThat(result.total())
                .isEqualByComparingTo("15.00");
    }

    @Test
    void invalidQuantityIsRejected() {
        assertThatThrownBy(() ->
                pricing.quote(invalidQuantity()))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("quantity");
    }

    @Test
    void negativeUnitPriceIsRejected() {
        Cart cart = aCart()
                .withLine(line("BOOK-001", 1, "-1.00"))
                .build();

        assertThatThrownBy(() -> pricing.quote(cart))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("unitPrice");
    }

    @Test
    void unknownCouponIsRejected() {
        Cart cart = aCart()
                .withCouponCode("NOT-A-COUPON")
                .build();

        assertThatThrownBy(() -> pricing.quote(cart))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("unsupported coupon");
    }

    @Test
    void emptyCartIsRejected() {
        Cart cart = aCart().withLines().build();

        assertThatThrownBy(() -> pricing.quote(cart))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("at least one line");
    }
}
~~~

This is a **pure unit test**: it does not boot Spring, Hibernate, MockMvc, a server, or H2. `CheckoutPricingService` has no state or dependencies, so `new` is enough. Data and expected values are chosen to **expose faulty branches**.

### 10.2. Why Is @CsvSource Useful?

The rows `99.99`/`100.00`/`100.01` share the same assertion logic, differing only in input and expected output. A parameterized test avoids three identical methods while allowing IDEs and test reports to pinpoint which case failed.

Do not overuse `@CsvSource` for complex, hard-to-read object graphs. When each case involves multiple lines, statuses, and customer tiers, use `@MethodSource` returning `Stream<Arguments>` with **clear scenario names** or named fixture methods.

### 10.3. When @MethodSource Is Needed

~~~java
static Stream<Arguments> cases() {
    return Stream.of(
        arguments("below threshold",
                CartFixtures.belowShippingThreshold(), "15.00"),
        arguments("at threshold",
                CartFixtures.atShippingThreshold(), "0.00")
    );
}

@ParameterizedTest(name = "{0}")
@MethodSource("cases")
void shippingCases(String name, Cart cart, String expected) {
    assertThat(pricing.quote(cart).shipping())
            .isEqualByComparingTo(expected);
}
~~~

This is an **extension snippet**, not a standalone runnable file: it requires imports for `Stream`, `Arguments`, `MethodSource`, `ParameterizedTest`, and the `pricing` field. Choose `@MethodSource` when object data cannot be represented cleanly in CSV. Each item should be freshly created or immutable to prevent state leakage.

## 11. MockMvc Slice: Fixtures Must Pass Through the Wire Format

### 11.1. Why Not Mock Both the Controller and JSON?

A unit test mocking the controller or calling its Java method returning `Quote` verifies the Java method, but does not prove the endpoint has the right route, HTTP `Content-Type`, or Jackson field names. To verify the HTTP contract, use `@WebMvcTest(QuoteController.class)` with the real controller and real JSON mapper, mocking the business service via `@MockitoBean`.

### 11.2. QuoteControllerJsonTest.java

`src/test/java/com/example/fixturelab/QuoteControllerJsonTest.java`:

~~~java
package com.example.fixturelab;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.MediaType;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import java.math.BigDecimal;

import static com.example.fixturelab.support.CartFixtures.atShippingThreshold;
import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(QuoteController.class)
class QuoteControllerJsonTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    ObjectMapper mapper;

    @MockitoBean
    CheckoutPricingService pricing;

    @Test
    void serializesMeaningfulCartAndChecksReturnedJson()
            throws Exception {
        Cart input = atShippingThreshold();

        Quote expected = new Quote(
                new BigDecimal("100.00"),
                new BigDecimal("0.00"),
                new BigDecimal("0.00"),
                new BigDecimal("100.00"));

        when(pricing.quote(any(Cart.class)))
                .thenReturn(expected);

        String response = mvc.perform(
                post("/api/quotes")
                        .contentType(MediaType.APPLICATION_JSON)
                        .accept(MediaType.APPLICATION_JSON)
                        .content(mapper.writeValueAsBytes(input)))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON))
                .andExpect(jsonPath("$.subtotal").isNumber())
                .andExpect(jsonPath("$.discount").isNumber())
                .andExpect(jsonPath("$.shipping").isNumber())
                .andExpect(jsonPath("$.total").isNumber())
                .andReturn()
                .getResponse()
                .getContentAsString();

        JsonNode tree = mapper.readTree(response);
        assertThat(tree.path("shipping").decimalValue())
                .isEqualByComparingTo("0.00");
        assertThat(tree.path("total").decimalValue())
                .isEqualByComparingTo("100.00");

        ArgumentCaptor<Cart> captured =
                ArgumentCaptor.forClass(Cart.class);
        verify(pricing).quote(captured.capture());

        assertThat(captured.getValue().customerId())
                .isEqualTo(input.customerId());
        assertThat(captured.getValue().tier())
                .isEqualTo(CustomerTier.REGULAR);
        assertThat(captured.getValue().lines())
                .hasSize(1);
        assertThat(captured.getValue()
                .lines().get(0).unitPrice())
                .isEqualByComparingTo("50.00");
    }
}
~~~

**What this test verifies:**
- `@WebMvcTest` loads the controller + MVC/Jackson slice without needing the full JPA context.
- `@MockitoBean` replaces the service in the Spring context, while JSON mapping is real.
- Jackson serializes **the `Cart` fixture itself**, avoiding hardcoded happy-path JSON that drifts from the Java model.
- `ArgumentCaptor` verifies the request was deserialized properly before being passed to the service.
- The JSON response is parsed with `JsonNode`, avoiding raw string comparisons sensitive to whitespace or key ordering.
- Monetary values are compared as `BigDecimal`, without casting to string or double.
- Do not infer that this test proves the pricing algorithm; the service **is mocked**. Unit tests in Section 10 test the business logic, and full HTTP integration in Section 13 tests both layers together.

If a test needs to verify invalid JSON, missing fields, or raw inputs, you can send a literal JSON string separately because that is a **wire-level error scenario**, not a happy-path business fixture.

## 12. @DataJpaTest: Persisting Fixtures and Reading Back from the Database

### 12.1. Why Not Assert Only on the Built Object?

`PurchaseRecordFixtures.aPurchase().build()` returns a Java object with the expected fields, so getters will still return the right values even if `@Column` annotations are wrong or repository queries fail. You must persist and read back via the database.

In Spring Boot 3.5, `@DataJpaTest`:
- Scans JPA entities and repositories, not all services/controllers.
- Typically replaces the `DataSource` with an embedded DB when H2 is on the classpath.
- Enables transactions and **rolls back by default after each test**.
- Can inject `TestEntityManager`.
- Does not prove PostgreSQL-specific constraints when running against H2.

### 12.2. PurchaseRecordRepositoryTest.java

`src/test/java/com/example/fixturelab/PurchaseRecordRepositoryTest.java`:

~~~java
package com.example.fixturelab;

import java.time.Instant;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.boot.test.autoconfigure.orm.jpa.TestEntityManager;

import static com.example.fixturelab.support.PurchaseRecordFixtures.aPurchase;
import static org.assertj.core.api.Assertions.assertThat;

@DataJpaTest
class PurchaseRecordRepositoryTest {

    @Autowired
    TestEntityManager entityManager;

    @Autowired
    PurchaseRecordRepository repository;

    @Test
    void persistsAndReloadsAllImportantFields() {
        PurchaseRecord fixture = aPurchase()
                .withReferenceCode("fixture-db-001")
                .withCustomerId("customer-db-001")
                .withTotal("119.90")
                .withStatus("NEW")
                .build();

        entityManager.persistAndFlush(fixture);
        entityManager.clear();

        PurchaseRecord stored = repository
                .findById("fixture-db-001")
                .orElseThrow();

        assertThat(stored.getReferenceCode())
                .isEqualTo("fixture-db-001");
        assertThat(stored.getCustomerId())
                .isEqualTo("customer-db-001");
        assertThat(stored.getTotal())
                .isEqualByComparingTo("119.90");
        assertThat(stored.getStatus())
                .isEqualTo("NEW");
        assertThat(stored.getCreatedAt())
                .isEqualTo(Instant.parse(
                        "2026-01-15T08:00:00Z"));
    }

    @Test
    void derivedQueryUsesRealDatabaseRows() {
        repository.saveAndFlush(aPurchase()
                .withReferenceCode("fixture-paid-001")
                .withStatus("PAID")
                .build());

        entityManager.clear();

        List<PurchaseRecord> paid =
                repository.findByStatus("PAID");

        assertThat(paid)
                .extracting(PurchaseRecord::getReferenceCode)
                .containsExactly("fixture-paid-001");
    }

    @Test
    void missingReferenceIsEmpty() {
        assertThat(repository.findById("not-present"))
                .isEmpty();
    }
}
~~~

**Why is `persistAndFlush` followed by `clear` useful?**
- `persistAndFlush` sends SQL to the database inside the test transaction.
- `clear` evicts managed entities from the JPA first-level cache.
- The subsequent query must materialize a fresh entity from the database, verifying the actual mapping rather than returning the cached instance from the persistence context.
- `@DataJpaTest` rolls back by default, so fixture rows normally do not persist after the test, preventing test-order coupling.

**Warning:** `flush` is still **not a commit**. If your test logic depends on `@TransactionalEventListener(AFTER_COMMIT)`, deferred constraints, or another connection observing the row, write a dedicated commit/integration test using `@Commit`/`TestTransaction` and cleanup. Do not use a default-rollback JPA test and claim commit behavior was verified.

### 12.3. Factory + Persistence Helpers: Do Not Over-Mix Responsibilities

A helper like:

~~~java
PurchaseRecord persistPurchase(
        PurchaseRecordRepository repository,
        String referenceCode) {
    return repository.saveAndFlush(
            aPurchase().withReferenceCode(referenceCode).build());
}
~~~

This is a snippet, not part of the runnable project. It helps when many tests must persist a valid row, provided the **side effect is explicit** in the method name. Avoid having `aPurchase()` silently hit the database—a name that sounds like pure Java object construction should not perform I/O.

### 12.4. @Sql When Fixtures Are Large

Spring TestContext supports `@Sql` to seed data from scripts:

~~~java
@Test
@Sql("/sql/purchase-fixture.sql")
void reportsPurchasedOrders() {
    // Verifies query against committed/uncommitted fixture depending on config.
}
~~~

This is an optional snippet; to run it, you must create `src/test/resources/sql/purchase-fixture.sql` matching the schema. `@Sql` does not automatically put data into a separate transaction; default semantics depend on the active test transaction, `DataSource`/`PlatformTransactionManager`, and `@SqlConfig`. In a transactional `@DataJpaTest`, seed scripts typically join the test transaction and roll back with the test.

When you need an independently committed seed:

~~~java
@Sql(
    scripts = "/sql/purchase-fixture.sql",
    config = @SqlConfig(
        transactionMode = SqlConfig.TransactionMode.ISOLATED))
~~~

This snippet requires `@Sql` and `@SqlConfig` imports along with an actual resource file. `ISOLATED` leaves committed rows behind; you must clean them up in an independent transaction rather than relying on `@DirtiesContext` as database cleanup.

### 12.5. Foreign-Key Relationships and Persistence Order

For a JPA entity graph with Purchase + Lines + Customer:
- Set the owning side properly.
- Use `cascade` intentionally; do not put `CascadeType.ALL` on every association just to seed tests quickly.
- Pay attention to `orphanRemoval`, foreign keys, and `NOT NULL`/`UNIQUE` constraints.
- With identity-generated IDs, call `persist`/`flush` in the proper order.
- Make **required relationships explicit** in test data; do not let a builder silently attach unrelated child entities.
- Use an isolated test DB for scenarios requiring real commits or testing locks/isolation.

## 13. Full HTTP Test: Fixtures Flow Through Both Controller and Service

### 13.1. QuoteHttpIntegrationTest.java

`src/test/java/com/example/fixturelab/QuoteHttpIntegrationTest.java`:

~~~java
package com.example.fixturelab;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static com.example.fixturelab.support.CartFixtures.vipEligible;
import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class QuoteHttpIntegrationTest {

    @Autowired MockMvc mvc;
    @Autowired ObjectMapper mapper;

    @Test
    void vipFixtureHasExpectedEndToEndQuote()
            throws Exception {
        Cart input = vipEligible();

        String body = mvc.perform(post("/api/quotes")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_JSON)
                .content(mapper.writeValueAsBytes(input)))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON))
                .andReturn()
                .getResponse()
                .getContentAsString();

        JsonNode root = mapper.readTree(body);

        assertThat(root.path("subtotal").decimalValue())
                .isEqualByComparingTo("120.00");
        assertThat(root.path("discount").decimalValue())
                .isEqualByComparingTo("12.00");
        assertThat(root.path("shipping").decimalValue())
                .isEqualByComparingTo("0.00");
        assertThat(root.path("total").decimalValue())
                .isEqualByComparingTo("108.00");
    }
}
~~~

This test uses the real controller, real pricing service, and real Jackson HTTP layer, though **it does not open a TCP socket** because MockMvc uses mock servlet requests. It verifies that a meaningful fixture survives serialization/deserialization and business calculation. Because pricing does not touch JPA, the test leaves no committed rows; for a real service writing to the DB, prepare and clean up accordingly.

### 13.2. Why Not Use @SpringBootTest for Every Test?

Pure pricing tests are fast and verify many boundaries. MVC slices verify routing and JSON with a mocked service. Full-context tests verify a key integrated path. Using the full context for every invalid quantity, coupon, and threshold case makes the suite slow and makes failure messages harder to diagnose.

A solid distribution:
- 10+ pure unit cases for business rules.
- 1–3 MVC slice cases for the JSON contract.
- A few JPA slice cases for persisted mappings.
- A small number of full-context cases for critical cross-layer paths.

Actual numbers depend on risk and complexity rather than a rigid test-count quota.

## 14. Running the Project and Reading Results

### 14.1. Maven Commands

With JDK 17+, Maven, and a dependency repository:

~~~bash
mvn -q clean test

mvn -q -Dtest=CartFixturesTest test
mvn -q -Dtest=CheckoutPricingServiceTest test
mvn -q -Dtest=QuoteControllerJsonTest test
mvn -q -Dtest=PurchaseRecordRepositoryTest test
mvn -q -Dtest=QuoteHttpIntegrationTest test
~~~

These classes are designed for Spring Boot 3.5.16 and Java 17. When Maven succeeds, the process exits with code `0`; test reports are written to `target/surefire-reports`. **Maven was not executed while writing this lesson**, so verify the actual build on your project's JDK/OS/dependency setup before treating it as executed.

### 14.2. Running the App to Inspect the Response

~~~bash
mvn spring-boot:run
~~~

In another terminal:

~~~bash
curl -X POST "http://localhost:8080/api/quotes" \
     -H "Content-Type: application/json" \
     -d '{"customerId":"customer-test-001","tier":"REGULAR","lines":[{"sku":"BOOK-001","quantity":2,"unitPrice":50.00}],"couponCode":null}'
~~~

Expected JSON response (object key order and whitespace are not part of the contract):

~~~json
{
  "subtotal": 100.00,
  "discount": 0.00,
  "shipping": 0.00,
  "total": 100.00
}
~~~

Without a domain error handler, invalid requests receive the default server error status; this is a lab limitation, not a REST API design recommendation. In a real product, map validation failures to 400 with a contract-compliant error DTO.

### 14.3. Why Exact Stdout Is Not Shown

`mvn -q clean test` does not produce identical logs across environments. Plugin versions, Hibernate SQL logging, OS, JDK, and Maven cache all affect console output. Reliable outcomes are the exit code, Surefire reports, and assertions. For pure unit tests, inspect individual named test results rather than guessing from console line counts.

## 15. Fixtures by Test Type

### 15.1. Unit Tests: Fewest Dependencies

- Build carts with the builder in memory.
- Do not mock repositories if the algorithm does not call any repository.
- No `@SpringBootTest` needed.
- Use boundary values, invalid inputs, and multi-line structures.
- Compute expected values independently so they are easy to review.

### 15.2. MVC Slice: Fixtures as the JSON Contract

- Construct requests with the builder and serialize with `ObjectMapper` to match the model.
- Keep the real controller and Jackson, and mock the service collaborator with `@MockitoBean`.
- Verify HTTP status, `Content-Type`, JSON fields/types, and the data passed to the service.
- For malformed JSON, invalid enum values, or missing required fields, send raw JSON intentionally.
- Do not let a DTO fixture replace serialization testing; tests must actually send JSON through MockMvc.

### 15.3. JPA Slice: Persisted State Must Be Real

- Create a fresh JPA entity fixture.
- Save/persist and flush before testing critical constraints.
- Call `EntityManager.clear()` when proving mappings read from the database, avoiding false positives from the first-level cache.
- Test real query methods against a test database.
- Understand `@DataJpaTest` default rollback; do not try to verify commit-phase events in a rollback test.
- When PostgreSQL-specific behavior is required, use Testcontainers with `@AutoConfigureTestDatabase(replace = NONE)`.

### 15.4. Full Integration: Different Layers Need Different Data

In a full context, helpers may need to create customers, orders, lines, payments, and outbox entries. Separate:
- **Entity builders** that construct objects.
- **Persistence fixtures** that write entities within transactions.
- **External fakes** that simulate brokers/payments/email with controlled outcomes.
- **Scenarios** describing business states such as `anOrderReadyForCapture()`.

Never let a default helper send real messages or call production providers.

### 15.5. Contract/Golden Fixtures

A large JSON file can help guard response schema stability. However, avoid blind snapshots:
- Review diffs carefully whenever contracts change.
- Never auto-overwrite golden files just because a test failed.
- Scrub dynamic UUIDs/dates, PII, and secrets.
- Assert key properties explicitly.
- Distinguish strict vs. lenient JSON comparison (extra fields, array order).

## 16. Anti-Patterns and How to Improve Them

### 16.1. “One Giant Fixture That Knows Everything”

A `TestFixtureManager` class containing builders for 40 aggregates, reading files, opening databases, publishing to Kafka, and resetting Redis turns `Given` into hidden magic. Fix this by splitting helpers by domain/boundary (`CartFixtures`, `PurchaseRecordFixtures`, `FakePaymentGateway`).

### 16.2. Invalid Defaults

A builder defaulting to `customerId=null` and `quantity=0` forces every test to override required fields. When a new field is added, tests fail en masse. Fix: make defaults valid for common scenarios; override specifically for negative cases.

### 16.3. Builders Hiding Invalid Data

A builder that silently replaces quantity 0 with 1 prevents a “quantity 0 must be rejected” test from ever reaching validation. Allow creating invalid fixtures at the right boundary; only production constructors should enforce domain invariants as designed.

### 16.4. Shared Mutable Singletons

`static final List<OrderLine> lines = new ArrayList<>()` or `static PurchaseRecord shared` causes order-dependent tests. Use factories that create fresh instances, immutable records, and `List.copyOf`.

### 16.5. Unnecessary Random Values

Random UUIDs and dates in snapshots make expected values hard to reproduce. Use randomness only when uniqueness or coverage requires it, with a seeded/injected generator and a logged seed on failure. For boundary tests, fixed values are clearer.

### 16.6. Overly “Clean” Data

Testing only single-line orders priced at a round 100.00 misses:
- Multiple lines / duplicate SKUs.
- Unicode, whitespace, and special characters.
- Decimal rounding by 0.01.
- Empty lists.
- Max/min allowed sizes.
- Missing required fields.
- JSON `null` vs. absent field.
- Records at time boundaries.

Add cases **driven by risk**, rather than generating thousands of meaningless arbitrary combinations.

### 16.7. Fixtures Computing Expected Values via Production Helpers

If a test calls the same subtotal helper as production to compute the expected total, formula bugs are copied into the test. Use independently calculated numeric scenarios and assert explainable constants.

### 16.8. Fixtures Persisting Implicitly Without Clear Names

A method named `aCustomer()` that secretly saves to the DB creates hidden side effects. Name it `persistCustomer()`, or separate `CustomerFixtures.aCustomer()` from `repository.save` in `Arrange`. Keep I/O boundaries obvious.

### 16.9. Unflushed JPA Entities Passing Tests

Asserting only Java getters after `save` does not test SQL constraints or column mappings. Use `persistAndFlush`/`clear` when reading state from the DB, and test commit-time constraints separately.

### 16.10. Treating @DirtiesContext as Database Cleanup

`@DirtiesContext` only evicts the cached Spring application context; it does not guarantee deleting rows from PostgreSQL or a shared test DB. Use default rollback where appropriate, cleanup scripts in a fresh transaction, or ephemeral databases/containers.

### 16.11. Relying on JUnit Execution Order

Test A seeds data and Test B queries it without its own `Arrange`; when JUnit runs Test B alone or in parallel, it fails. Every test must create its own required data or use well-scoped, isolated lifecycle fixtures.

### 16.12. Testing External Systems with Production Dumps

Putting production dumps in CI can violate security policies and make tests depend on drifting data. Use synthetic fixtures or approved sanitized datasets. Never include secrets or personal data in Markdown, logs, or snapshots.

### 16.13. Using @SpringBootTest for All Tests

Running the full context for pure logic slows down the suite, pulls in unrelated databases/networks, and masks missing dependency injection. Use unit and slice tests for most branches, reserving full integration for key cross-layer paths.

### 16.14. Using Complex Builders for Every Fixture

If you just need `new Money("USD", "10.00")`, a builder with 20 setters adds no value. Prefer clear constructors/value objects for small data. Builders shine when there are many optional fields, complex graphs, and valid defaults.

### 16.15. Comparing Raw JSON Strings in API Tests

Whitespace and key order in JSON objects are usually not part of the contract. Use Jackson or JSON-aware matchers. However, when testing missing fields or malformed JSON in HTTP requests, raw JSON literals are intentional and completely appropriate test data.

## 17. As Data Evolves: Versioning and Reducing Coupling

### 17.1. Builders Should Not Mirror the Entire Database Schema

Focus on fields needed by business logic and tests. If a production DTO adds an optional field, the fixture helper should provide a sensible default without forcing every existing test to assert on the new field. Be clear about which fields belong to which contract.

### 17.2. Separating Test Support from Main Artifacts

Place fixtures in `src/test/java` of the module. If multiple modules need to share them, create a test-fixtures artifact/module (Gradle `java-test-fixtures` or a properly configured Maven `test-jar`), without accidentally exposing test dependencies to production runtime.

### 17.3. Scenario Names Must Speak the Business Language

Good:
- `atShippingThreshold()`.
- `vipEligible()`.
- `anExpiredSubscription()`.
- `anInvoiceWithUnpaidBalance()`.
- `aCustomerWithoutAddress()` (negative case).

Poor:
- `sample1()`, `bigObject()`, `fullEntity()`, `testDataForMethod3()`.

Names should describe the real condition. When a business rule changes, a misleading name is more dangerous than a long constructor because it misdirects test reviewers.

### 17.4. Defaults Should Be Reviewed Like Production Code

A fixture default should not change silently when business rules evolve. Change a default only while keeping it valid and representative; for scenarios that must preserve older conditions to test backward compatibility, use a fixed named factory.

### 17.5. Avoid Fixture Dependency Chains

A factory chain where `approvedOrder()` calls `pendingOrder()`, which calls `orderWithCustomer()`, which calls `customerWithAddress()`, which calls a DB helper causes small edits to ripple across the entire suite. Keep chains short, overrides explicit, and fixture units narrowly scoped.

### 17.6. Testcontainers and Production-Like Data

When queries rely on PostgreSQL, MySQL, or Cassandra semantics, embedded H2 may not suffice. Testcontainers provides ephemeral instances, but you still must:
- Apply schemas/migrations.
- Write intentional test data.
- Ensure per-test uniqueness and isolation.
- Clean up committed fixtures or discard the container.
- Verify the container image/version matches production behavior.

Testcontainers does not replace fixture design; a real database populated with meaningless data still yields weak tests.

## 18. Advanced Topics

### 18.1. Testing Expiration Instants

For a rule “voucher expires at 12:00:00Z”, test:
- `11:59:59.999Z`.
- `12:00:00Z`.
- `12:00:00.001Z`.

Inject `Clock` to avoid depending on execution time. Test in UTC and across offset conversions when the contract requires it; never use `LocalDateTime.now()` and risk race conditions.

### 18.2. Currency, Rounding, and Precision

When prices use `BigDecimal`:
- Use `new BigDecimal("0.10")` instead of `new BigDecimal(0.1)`.
- When comparing numeric values, `isEqualByComparingTo` is appropriate when scale is not part of the contract.
- If the API requires two decimal places, verify JSON serialization/formatting separately.
- Rounding modes must be explicit, such as `RoundingMode.HALF_UP` in this lab.
- Test edge cases: 0, 0.01, multiple lines, and large-value/overflow constraints.

### 18.3. Stable Ordering

A list returned by a repository without `ORDER BY` has no guaranteed order. Test data may contain the exact two rows while `containsExactly(...)` fails spuriously if order is not part of the business contract. Use `containsExactlyInAnyOrder(...)` or add explicit ordering to the query. In this JPA project, `findByStatus("PAID")` returns only one row, so sorting is not tested there.

### 18.4. Concurrency and Uniqueness

For tests running in parallel against a shared database:
- Use per-test data namespaces or separate schemas/containers.
- Never call `repository.deleteAll()` in one test while another test is using the DB.
- Do not hardcode keys that can collide across parallel test classes.
- You may use `UUID.randomUUID()` for uniqueness, storing the generated ID in a test-local variable rather than asserting an exact literal.
- Do not rely on a static counter across multiple JVMs or test workers.

### 18.5. Testing Invalid Input at the Right Boundary

If a production record constructor enforces invariants, an invalid fixture will fail during `Arrange`. Tests must **assert around the constructor** or send raw HTTP input to test Bean Validation; do not write tests expecting a service to handle an object that cannot be constructed. In this lab, `CartLine` does not self-validate so the service branch can be tested directly.

### 18.6. Data Snapshots and Migrations

JSON/SQL snapshots can help catch broad regressions, but:
- Review them whenever the schema changes.
- Never blindly accept all snapshot diffs.
- Exclude session tokens and environment-specific URLs/credentials.
- Version the contract.
- Separate volatile fields (timestamps/IDs) from required business fields.
- Do not rely solely on full-payload snapshots when a business decision actually hinges on one specific field.

## 19. Troubleshooting

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Tests fail en masse after adding a DTO field | Fixture constructors duplicated everywhere | Centralize valid defaults in a builder/factory |
| Test passes despite wrong shipping threshold | Subtotal chosen far from threshold | Use 99.99 / 100.00 / 100.01 |
| Test fails depending on execution order | Static mutable fixture or leftover test data | Fresh instances + rollback/cleanup |
| Date test flakes around midnight | `now()` / OS timezone | Inject `Clock.fixed` |
| Duplicate JPA key during parallel runs | Shared assigned IDs | Per-test namespace / database isolation |
| Entity getters pass but production query fails | Missing persist/flush/clear | Test repository against a real DB |
| `@DataJpaTest` fails to load service | Slice limits component scan | Selective `@Import` or test at another boundary |
| `@WebMvcTest` missing service bean | Controller collaborator has no bean | `@MockitoBean` for the service |
| JSON request test fails mapping | Raw JSON / DTO keys / enum mismatch | `ObjectMapper` for valid fixtures, raw JSON for invalid |
| `BigDecimal` equality fails | Scale mismatch like 19.9 vs 19.90 | `isEqualByComparingTo` if only numeric equality matters |
| H2 test passes but PostgreSQL fails | SQL dialect / constraint differences | Testcontainers with matching engine |
| `@Sql` seed is not cleaned up | Isolated/committed SQL fixture | Explicit cleanup script/transaction |
| List fixture gets mutated | Returned mutable reference | `List.copyOf` / fresh builder per test |
| Invalid quantity test never reaches service | Builder auto-fixes / constructor validates early | Test at the proper validation boundary |
| Parameterized test is hard to read | CSV encodes complex object graphs | `@MethodSource` with named fixtures |
| Golden file diffs explode | Dynamic IDs/dates or overly broad snapshots | Deterministic data, selective assertions |
| CI leaks PII | Production dumps or verbose test logs | Synthetic fixtures and scrubbed logs |
| Service unit test is unusually slow | Unnecessary `@SpringBootTest` | Plain JUnit / Mockito |
| Fixture helper hits DB unexpectedly | Construction and persistence mixed | Separate factory from persist helper |

Debug in order: Is **Given** truly the right scenario? Does the fixture create fresh objects? Is the test calling the SUT or mocking the SUT itself? Is the boundary pure object, MVC, JPA, or full context? Were expected values computed independently? Are database transactions and cleanup right? Only after checking these should you modify production code.

## 20. Exercises

1. Write a shipping-threshold test using only subtotal 1000.00; then intentionally change `>=` to `>`. Why did the old test miss it? Add 100.00.
2. Add the `99.99` and `100.01` scenarios using `@CsvSource` and verify the results.
3. Write `aVipCart()` using the builder without copying the full constructor.
4. Verify the default builder creates a valid object without sharing a mutable list.
5. Build a `Cart`, then modify the builder; prove the previously built `Cart` did not change.
6. Create an invalid quantity of 0 and a negative price; test the errors in `CheckoutPricingService`.
7. Write a test combining VIP + `SAVE10` on subtotal 120.00 with expected total 98.00.
8. Use `@MethodSource` for multiple object graphs, displaying each scenario name in the test display name.
9. Add an injectable `Clock` for a voucher expiration rule, testing before, exactly at, and after expiration.
10. Create `PurchaseRecordFixtures` with valid defaults and override status to `PAID` to test `findByStatus`.
11. In a JPA slice test, call `persistAndFlush` and `clear`; explain why this is not equivalent to a commit.
12. Seed a row with `@Sql`, contrasting default transaction participation with `ISOLATED`.
13. Test a JSON request fixture via `MockMvc` + `ObjectMapper`, using an `ArgumentCaptor` to verify the `Cart` deserialized properly.
14. Mock `CheckoutPricingService` in `@WebMvcTest` and explain why the test does not verify the pricing algorithm.
15. Write a full-context test using the real pricing service and a scenario with subtotal 120.00.
16. Add a JPA entity with a foreign key and design a builder graph with explicit owning side and cascades.
17. Run tests in parallel with fixed assigned IDs, observe collisions, and design proper isolation.
18. Take a snapshot containing a dynamic timestamp and refactor it to `Clock.fixed` and selective assertions.
19. Compare Object Mother vs. Test Data Builder as a model grows from 4 to 20 fields.
20. Review a fixture containing production data and replace it with safe synthetic values.

## 21. Fixture Review Checklist

- [ ] Does the fixture name express a specific business scenario?
- [ ] Is the default object valid for the happy path?
- [ ] Does the test override only the field under test instead of changing multiple variables?
- [ ] Is there data just below, at, and just above critical thresholds?
- [ ] Are invalid/null/empty/duplicate cases tested at the appropriate boundary?
- [ ] Are expected values calculated independently without copying production logic?
- [ ] Does each test get a fresh instance or immutable object?
- [ ] Are there no static mutable entities or lists shared across tests?
- [ ] Are list/map fields defensively copied where needed?
- [ ] Does the builder avoid “auto-fixing” invalid data meant to be tested?
- [ ] Are `BigDecimal` strings, precision, and rounding aligned with the contract?
- [ ] Is there a deterministic strategy for `Clock`/UUID/randomness when needed?
- [ ] Do unit tests avoid loading the Spring context unnecessarily?
- [ ] Do MVC slices use `ObjectMapper` fixtures and keep the real controller and Jackson?
- [ ] Does `@MockitoBean` mock only collaborators, never the SUT?
- [ ] Do JPA slices persist/flush/clear when proving mappings?
- [ ] Is `@DataJpaTest` default rollback properly understood?
- [ ] Do committed DB fixtures have explicit cleanup or ephemeral databases?
- [ ] Are `@Sql` scripts and transaction scopes clear?
- [ ] Are tests independent of JUnit method execution order?
- [ ] Do parallel tests have unique IDs and proper isolation?
- [ ] Are production secrets and PII absent from fixtures?
- [ ] Are snapshot/golden files reviewed intentionally?
- [ ] Are there test commands and Surefire reports confirming actual execution?

**Conclusion:** A good fixture is not the object with the most fields, but data that **clarifies the condition of a test**. Use Test Data Builders with valid defaults, named scenario factories for key cases, and fresh fixtures for each test. Choose boundary values sensitive enough to expose bugs; keep identities, time, and money deterministic. In unit tests, object fixtures suffice; in MVC, data must pass through JSON mapping; in JPA, it must actually be persisted and queried to verify the schema and repository. Meaningful, properly scoped data makes tests less brittle and far better at catching real bugs.

## 22. Official References

- Spring Boot 3.5 — Testing Spring Boot Applications: https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html
- Spring Boot 3.5 — DataJpaTest API: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/autoconfigure/orm/jpa/DataJpaTest.html
- Spring Framework 6.2 — @MockitoBean/@MockitoSpyBean: https://docs.spring.io/spring-framework/reference/6.2/testing/annotations/integration-spring/annotation-mockitobean.html
- Spring Framework 6.2 — TestContext Transaction Management: https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/tx.html
- Spring Framework 6.2 — @Sql, SQL script execution: https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/executing-sql.html
- JUnit 5 User Guide — Parameterized Tests: https://docs.junit.org/current/user-guide/#writing-tests-parameterized-tests
- AssertJ — Core assertions guide: https://assertj.github.io/doc/
- Spring Data JPA — Repositories and Testing: https://docs.spring.io/spring-data/jpa/reference/
- Spring Boot 3.5 — Testcontainers: https://docs.spring.io/spring-boot/3.5/reference/testing/testcontainers.html
- Java 17 — Records (JLS): https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10

# Writing Unit Tests for Business Rules with Error Branches and Boundary Conditions

## 1. Why is a single happy-path test not enough?

In **Spring Boot - testing**, under **Integration Practice**, a business feature can return the right answer on an ordinary example yet fail at critical thresholds: quantity equal to 0, exceeding the limit, price equal to 0, amounts with three decimal places, a discount barely qualifying, an after-discount total right at the free-shipping threshold, or inventory short by a single unit.

**Quality unit tests must prove both valid rules and rejection branches.** That requires an explicit contract: valid input yields the right arithmetic result and interactions, while invalid input throws the right exception type with no side effects. Checking for any generic exception is not enough; you must understand validation ordering and why an external port **must not be called** once data is invalid.

This practice lab chooses an **order price quoting** rule to provide rich scenarios:
- Product SKU must be valid and normalized.
- Integer quantity from **1 to 20**, both bounds inclusive.
- Unit price from **0.01 to 10,000.00** in currency with two decimal places.
- Coupon **SAVE10** gives **10%** off if the **pre-discount subtotal** is at least **100.00**.
- Compute discount using **BigDecimal**, rounded **HALF_UP** to two decimal places.
- Check remaining stock through **InventoryPort**, the sole outbound dependency.
- If inventory reports a negative number, treat it as a data/infrastructure error; if remaining stock is less than ordered quantity, throw an insufficient-stock exception.
- Shipping fee is **12.00** if the **net total after discount** is below **200.00**; **200.00** or above ships free.
- Total payable = pre-discount subtotal − discount + shipping.

The example stack uses **Java 17+, Spring Boot 3.4.5, Gradle, JUnit Jupiter, Mockito, and MockitoExtension**. The system under test is a plain Java class, **without starting a Spring ApplicationContext**. This is intentional: the quoting algorithm needs no server, DataSource, or Spring proxy to test business branches. When bean wiring, transactions, or databases need testing, separate integration tests cover them.

**The results in this article are expected assertions from the source code, not a claim that Gradle or the test suite was executed during authoring.**

## 2. Separate specification from code before writing tests

A rule needs to be written as a measurable contract. Without a specification, a developer can write tests that match an implementation bug without realizing it.

| Rule | Input or boundary | Expectation |
| --- | --- | --- |
| SKU | null, empty, whitespace | IllegalArgumentException |
| SKU | After trim + uppercase does not match format | IllegalArgumentException |
| SKU | " abc-123 " | Normalized to ABC-123 |
| Quantity | 0, negative, 21 | IllegalArgumentException |
| Quantity | 1 or 20 | Valid |
| Unit price | null, 0, negative | IllegalArgumentException |
| Unit price | 0.01 or 10000.00 | Valid |
| Unit price | 10000.01 | IllegalArgumentException |
| Unit price | 1.234 | IllegalArgumentException because exact two decimal places cannot be preserved |
| Unit price | 10.000 | Valid, because it reduces to 10.00 without rounding |
| Coupon | null, empty, blank | No coupon applied |
| Coupon | Unknown code | InvalidCouponException |
| Coupon | SAVE10 and subtotal 99.99 | CouponNotApplicableException |
| Coupon | SAVE10 and subtotal 100.00 | Discount 10.00 |
| Discount | 100.05 × 10% = 10.005 | Rounded HALF_UP to 10.01 |
| Stock | Negative available | InventoryUnavailableException |
| Stock | available = quantity − 1 | InsufficientStockException |
| Stock | available = quantity | Valid |
| Shipping | Net 199.99 | Fee 12.00 |
| Shipping | Net 200.00 | Free |
| Shipping | Net 200.01 | Free |
| Total | Any valid quote | subtotal − discount + shipping |

**Important:** Coupon eligibility is based on the **pre-discount subtotal**, whereas the shipping threshold is based on the **post-discount net**. For example, subtotal 200.00 with coupon SAVE10 gives a 20.00 discount and net 180.00; this order **still pays 12.00 shipping**, totaling 192.00. This is a branch easily misimplemented if shipping threshold is checked before discounting.

### Processing order is part of the contract

~~~text
Non-null request
    |
    v
Validate + normalize SKU
    |
    v
Validate quantity
    |
    v
Validate monetary unit price
    |
    v
Normalize coupon; validate coupon + subtotal threshold
    |
    v
InventoryPort.availableUnits(normalizedSku)
    |
    +-- negative available? -> InventoryUnavailableException
    |
    +-- less than requested? -> InsufficientStockException
    |
    v
Discount / net / shipping / total
    |
    v
Immutable PriceQuote result
~~~

You must verify **`verifyNoInteractions(inventory)`** for input or coupon errors: an invalid request must not make unnecessary DB/remote inventory calls. For valid requests, assert it is called **exactly once with the normalized SKU**.

## 3. Choosing unit testing techniques

**JUnit Jupiter** provides `@Test`, `@ParameterizedTest`, `@MethodSource`, `@ValueSource`, `assertAll`, `assertEquals`, `assertThrowsExactly`, and lifecycle callbacks. **Mockito** creates an outbound port mock to set stock levels or actively throw exceptions. **MockitoExtension** integrates mock lifecycle and appropriate strict stubbing.

Unit tests should:
- Instantiate the service via constructor, without `@SpringBootTest`.
- Never mock the class under test itself.
- Mock **InventoryPort**, not `BigDecimal`, records, or policy implementations.
- Include positive/negative controls, especially at thresholds.
- Use inputs that clearly describe each scenario; avoid randomness and network calls in a deterministic suite.
- Compare monetary values using `BigDecimal` normalized to scale 2, never `double`.
- Assert the exact exception type and accompanying fields when an exception carries data.
- Verify no dependency calls occur on failed validation branches.
- Name tests to express **behavior** rather than vague names like `test1`, `test2`.
- Use parameterized tests when many cases share the same structure; keep standalone tests for an important policy or distinct exception branch.

### Where do unit tests differ from integration tests?

Unit tests do not prove Spring component scanning, `@Transactional`, database migrations, API security, or repository queries. A quote service unit test passing in the JVM only proves the algorithm and its interaction with a **mocked port** under contract.

When using Spring Boot, clean architecture keeps business logic in plain Java and integrates it via `@Bean` or `@Service` + a real `InventoryPort` adapter in another layer. Then add:
- `@SpringBootTest` when checking wiring, profiles, and transactions/proxies;
- `@DataJpaTest` to check persistence queries;
- `@WebMvcTest`/MockMvc to check HTTP mapping/validation;
- Testcontainers integration to check a real database.

**Do not turn unit tests into Spring integration tests just because the project uses Spring Boot.** Booting an entire context for BigDecimal branches increases runtime and can hide bugs behind complex fixtures.

## 4. Complete Java 17 / Spring Boot 3.4.5 project

### 4.1. File tree

~~~text
settings.gradle
build.gradle
src/main/java/com/example/quoteqa/QuoteQaApplication.java
src/main/java/com/example/quoteqa/QuoteRequest.java
src/main/java/com/example/quoteqa/PriceQuote.java
src/main/java/com/example/quoteqa/InventoryPort.java
src/main/java/com/example/quoteqa/OrderQuoteService.java
src/test/java/com/example/quoteqa/OrderQuoteServiceTest.java
~~~

The project is designed to **compile with Java 17**, using Spring Boot dependency management for JUnit/Mockito. `OrderQuoteService` is a Java domain service without `@Service` in this demo; the Spring Boot application class serves only as an entry point. This is not a web API. You can run Gradle tests directly to practice; no Docker, database, or HTTP server is needed.

### 4.2. settings.gradle

~~~groovy
rootProject.name = 'unit-branch-boundary-quote'
~~~

### 4.3. build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.4.5'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

**spring-boot-starter-test** supplies JUnit Jupiter, Mockito, and common assertion libraries. No `@SpringBootTest`, `spring-boot-starter-web`, or database driver is needed because the subject under test is plain Java. In Spring Boot 3.4, `MockitoExtension` comes from Mockito's JUnit Jupiter integration included in the test starter.

### 4.4. QuoteQaApplication.java

~~~java
package com.example.quoteqa;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class QuoteQaApplication {

    public static void main(String[] args) {
        SpringApplication.run(QuoteQaApplication.class, args);
    }
}
~~~

This is just the application entry point so the project follows standard Spring Boot structure. **`OrderQuoteService` is not injected as a Spring bean** in the demo, since the primary task is unit testing the policy in isolation. If a real application registers the service as a bean, configure the corresponding `InventoryPort` adapter and add a separate wiring test.

### 4.5. QuoteRequest.java

~~~java
package com.example.quoteqa;

import java.math.BigDecimal;

public record QuoteRequest(
        String sku,
        int quantity,
        BigDecimal unitPrice,
        String couponCode) {
}
~~~

Record grouping all inputs. Intentionally has no validation in the canonical constructor: **`OrderQuoteService`** validates and normalizes inputs in the exact contract order. That lets unit tests construct invalid requests and assert that the service rejects them. In a real API, validation can be added at the transport layer, yet domain invariants are still required when the service is called outside HTTP.

### 4.6. PriceQuote.java

~~~java
package com.example.quoteqa;

import java.math.BigDecimal;

public record PriceQuote(
        String normalizedSku,
        int quantity,
        BigDecimal subtotal,
        BigDecimal discount,
        BigDecimal shipping,
        BigDecimal total) {
}
~~~

Immutable record holding the financial result. All `BigDecimal` monetary fields are returned by the service with **scale = 2**. Named **`normalizedSku`** to distinguish the raw request SKU from the value used when calling inventory.

### 4.7. InventoryPort.java

~~~java
package com.example.quoteqa;

@FunctionalInterface
public interface InventoryPort {

    int availableUnits(String normalizedSku);
}
~~~

This is the only outbound dependency. A production adapter might call a repository/API, while unit tests only need a Mockito mock or lambda fake. Demo contract: values `>= 0` represent valid stock; negative numbers represent invalid inventory data. An adapter can throw `InventoryUnavailableException` if upstream/database fails; the service does not swallow exceptions into fake quotes.

## 5. OrderQuoteService: real business policy

**src/main/java/com/example/quoteqa/OrderQuoteService.java**

~~~java
package com.example.quoteqa;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.Locale;
import java.util.Objects;

public final class OrderQuoteService {

    private static final BigDecimal MIN_UNIT =
        new BigDecimal("0.01");
    private static final BigDecimal MAX_UNIT =
        new BigDecimal("10000.00");
    private static final BigDecimal MIN_COUPON_SUBTOTAL =
        new BigDecimal("100.00");
    private static final BigDecimal FREE_SHIPPING_AT =
        new BigDecimal("200.00");
    private static final BigDecimal SHIPPING_FEE =
        new BigDecimal("12.00");
    private static final BigDecimal TEN_PERCENT =
        new BigDecimal("0.10");
    private static final BigDecimal ZERO =
        new BigDecimal("0.00");

    private final InventoryPort inventory;

    public OrderQuoteService(InventoryPort inventory) {
        this.inventory = Objects.requireNonNull(
            inventory, "inventory");
    }

    public PriceQuote quote(QuoteRequest request) {
        Objects.requireNonNull(request, "request");

        String sku = normalizeSku(request.sku());
        int quantity = validateQuantity(request.quantity());
        BigDecimal unitPrice =
            validateUnitPrice(request.unitPrice());

        String coupon = normalizeCoupon(
            request.couponCode());
        BigDecimal subtotal = unitPrice
            .multiply(BigDecimal.valueOf(quantity))
            .setScale(2, RoundingMode.UNNECESSARY);

        BigDecimal discount = ZERO;

        if (coupon != null) {
            if (subtotal.compareTo(
                    MIN_COUPON_SUBTOTAL) < 0) {
                throw new CouponNotApplicableException(
                    "SAVE10 requires subtotal >= 100.00");
            }

            discount = subtotal
                .multiply(TEN_PERCENT)
                .setScale(2, RoundingMode.HALF_UP);
        }

        int available = inventory.availableUnits(sku);

        if (available < 0) {
            throw new InventoryUnavailableException(
                "inventory returned negative availability");
        }
        if (available < quantity) {
            throw new InsufficientStockException(
                quantity, available);
        }

        BigDecimal net = subtotal.subtract(discount);
        BigDecimal shipping = net.compareTo(
                FREE_SHIPPING_AT) >= 0
            ? ZERO
            : SHIPPING_FEE;

        BigDecimal total = net.add(shipping);

        return new PriceQuote(
            sku, quantity, subtotal,
            discount, shipping, total);
    }

    private static String normalizeSku(String raw) {
        if (raw == null) {
            throw new IllegalArgumentException(
                "sku is required");
        }

        String normalized = raw
            .trim()
            .toUpperCase(Locale.ROOT);

        if (!normalized.matches("[A-Z0-9-]{3,16}")) {
            throw new IllegalArgumentException(
                "sku format is invalid");
        }
        return normalized;
    }

    private static int validateQuantity(int quantity) {
        if (quantity < 1 || quantity > 20) {
            throw new IllegalArgumentException(
                "quantity must be between 1 and 20");
        }
        return quantity;
    }

    private static BigDecimal validateUnitPrice(
            BigDecimal raw) {
        if (raw == null) {
            throw new IllegalArgumentException(
                "unitPrice is required");
        }
        if (raw.compareTo(MIN_UNIT) < 0
                || raw.compareTo(MAX_UNIT) > 0) {
            throw new IllegalArgumentException(
                "unitPrice must be between 0.01 and 10000.00");
        }

        try {
            return raw.setScale(
                2, RoundingMode.UNNECESSARY);
        } catch (ArithmeticException ex) {
            throw new IllegalArgumentException(
                "unitPrice must have exact cents",
                ex);
        }
    }

    private static String normalizeCoupon(
            String raw) {
        if (raw == null || raw.isBlank()) {
            return null;
        }

        String normalized = raw.trim()
            .toUpperCase(Locale.ROOT);

        if (!"SAVE10".equals(normalized)) {
            throw new InvalidCouponException(
                "unknown coupon: " + normalized);
        }
        return normalized;
    }

    public static final class InvalidCouponException
            extends IllegalArgumentException {

        public InvalidCouponException(String message) {
            super(message);
        }
    }

    public static final class CouponNotApplicableException
            extends IllegalArgumentException {

        public CouponNotApplicableException(String message) {
            super(message);
        }
    }

    public static final class InventoryUnavailableException
            extends IllegalStateException {

        public InventoryUnavailableException(String message) {
            super(message);
        }
    }

    public static final class InsufficientStockException
            extends IllegalStateException {

        private final int requested;
        private final int available;

        public InsufficientStockException(
                int requested, int available) {
            super("insufficient stock: requested="
                + requested + ", available=" + available);
            this.requested = requested;
            this.available = available;
        }

        public int getRequested() {
            return requested;
        }

        public int getAvailable() {
            return available;
        }
    }
}
~~~

### 5.1. What matters in the implementation?

**`Objects.requireNonNull(request)`**: a null request has its own contract, throwing a `NullPointerException` naming the parameter. Do not let an accidental NPE occur deeper in the service when calling `request.sku()`.

**`normalizeSku`**: trims spaces at both ends and uppercases with `Locale.ROOT`. SKU must not be null and must match valid characters/length. Sends the exact normalized SKU to inventory; tests should verify the exact argument.

**`validateQuantity`**: accepts 1 and 20, rejects 0 and 21. Conditions using **`>= / <=`** map cleanly to the min/max contract. Test just below, at, and just above each bound to catch mutations changing inclusive to exclusive.

**`validateUnitPrice`**: price is compared against Min/Max using **`BigDecimal.compareTo`**, never `double`. **`setScale(2, RoundingMode.UNNECESSARY)`** accepts `10.000` because it represents `10.00` exactly, but rejects `1.234` because it would require rounding. For input prices, silent rounding is wrong: if a caller sends `1.234`, the service demands corrected data instead of silently truncating/rounding.

**`normalizeCoupon`**: null/blank means no coupon. Unknown codes are rejected **before the inventory call**. Code `SAVE10` applies only when pre-discount subtotal `>= 100.00`.

**Coupon discount**: uses `BigDecimal("0.10")`, `HALF_UP` at two decimals; e.g., `100.05 × 0.10 = 10.005 → 10.01`. Never use float/double.

**Inventory check**: calls the outbound port only after validation finishes. Negative values are treated as anomalous, stock equal to quantity is accepted, and being short by one unit throws `InsufficientStockException` with `requested`/`available` so the caller can diagnose.

**Shipping**: based on **net after coupon**, not subtotal before coupon. Net `>= 200.00` is free; lower net pays `12.00`. Shipping must not be calculated on a total that already includes shipping (avoiding circular logic).

**`PriceQuote`**: returns fields with scale 2, with no side effects such as creating an order, reserving stock, or sending a message. This lab computes a quote, not an order placement: if atomic reservation is needed, separate transaction/idempotency integration tests are required.

## 6. Complete unit tests with JUnit Jupiter and Mockito

**src/test/java/com/example/quoteqa/OrderQuoteServiceTest.java**

~~~java
package com.example.quoteqa;

import java.math.BigDecimal;
import java.util.stream.Stream;

import com.example.quoteqa.OrderQuoteService.CouponNotApplicableException;
import com.example.quoteqa.OrderQuoteService.InsufficientStockException;
import com.example.quoteqa.OrderQuoteService.InvalidCouponException;
import com.example.quoteqa.OrderQuoteService.InventoryUnavailableException;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.Arguments;
import org.junit.jupiter.params.provider.MethodSource;
import org.junit.jupiter.params.provider.ValueSource;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import static org.junit.jupiter.api.Assertions.assertAll;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertSame;
import static org.junit.jupiter.api.Assertions.assertThrowsExactly;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.verifyNoMoreInteractions;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class OrderQuoteServiceTest {

    @Mock
    private InventoryPort inventory;

    private OrderQuoteService service;

    @BeforeEach
    void setUp() {
        service = new OrderQuoteService(inventory);
    }

    @ParameterizedTest(name = "{index}: {0}")
    @MethodSource("validPricingCases")
    void calculatesQuoteAtImportantBoundaries(
            String caseName,
            String priceText,
            int quantity,
            String coupon,
            String expectedSubtotal,
            String expectedDiscount,
            String expectedShipping,
            String expectedTotal) {

        when(inventory.availableUnits("ABC-123"))
            .thenReturn(20);

        QuoteRequest input = new QuoteRequest(
            "ABC-123", quantity,
            new BigDecimal(priceText), coupon);

        PriceQuote result = service.quote(input);

        assertAll(caseName,
            () -> assertEquals("ABC-123",
                result.normalizedSku()),
            () -> assertEquals(quantity,
                result.quantity()),
            () -> assertEquals(
                new BigDecimal(expectedSubtotal),
                result.subtotal()),
            () -> assertEquals(
                new BigDecimal(expectedDiscount),
                result.discount()),
            () -> assertEquals(
                new BigDecimal(expectedShipping),
                result.shipping()),
            () -> assertEquals(
                new BigDecimal(expectedTotal),
                result.total()),
            () -> assertEquals(
                result.subtotal()
                    .subtract(result.discount())
                    .add(result.shipping()),
                result.total())
        );

        verify(inventory).availableUnits("ABC-123");
        verifyNoMoreInteractions(inventory);
    }

    static Stream<Arguments> validPricingCases() {
        return Stream.of(
            Arguments.of(
                "minimum accepted price",
                "0.01", 1, null,
                "0.01", "0.00", "12.00", "12.01"),
            Arguments.of(
                "small subtotal",
                "1.25", 3, null,
                "3.75", "0.00", "12.00", "15.75"),
            Arguments.of(
                "below shipping threshold",
                "199.99", 1, null,
                "199.99", "0.00", "12.00", "211.99"),
            Arguments.of(
                "exactly shipping threshold",
                "200.00", 1, null,
                "200.00", "0.00", "0.00", "200.00"),
            Arguments.of(
                "above shipping threshold",
                "200.01", 1, null,
                "200.01", "0.00", "0.00", "200.01"),
            Arguments.of(
                "coupon threshold exactly 100",
                "20.00", 5, "SAVE10",
                "100.00", "10.00", "12.00", "102.00"),
            Arguments.of(
                "half up discount rounding",
                "100.05", 1, "SAVE10",
                "100.05", "10.01", "12.00", "102.04"),
            Arguments.of(
                "coupon turns free shipping into paid",
                "200.00", 1, "SAVE10",
                "200.00", "20.00", "12.00", "192.00"),
            Arguments.of(
                "coupon net reaches 200 exactly",
                "222.22", 1, "SAVE10",
                "222.22", "22.22", "0.00", "200.00"),
            Arguments.of(
                "maximum quantity is allowed",
                "10.00", 20, null,
                "200.00", "0.00", "0.00", "200.00"),
            Arguments.of(
                "maximum accepted unit price",
                "10000.00", 1, null,
                "10000.00", "0.00", "0.00", "10000.00"),
            Arguments.of(
                "blank coupon means no coupon",
                "50.00", 2, "  ",
                "100.00", "0.00", "12.00", "112.00"),
            Arguments.of(
                "lowercase coupon accepted",
                "250.00", 1, "save10",
                "250.00", "25.00", "0.00", "225.00")
        );
    }

    @Test
    void normalizesSkuAndCouponBeforeInventoryCall() {
        when(inventory.availableUnits("ABC-123"))
            .thenReturn(2);

        PriceQuote result = service.quote(
            new QuoteRequest(
                "  abc-123  ", 2,
                new BigDecimal("60.00"),
                "  save10  "));

        assertAll(
            () -> assertEquals(
                "ABC-123", result.normalizedSku()),
            () -> assertEquals(
                new BigDecimal("120.00"),
                result.subtotal()),
            () -> assertEquals(
                new BigDecimal("12.00"),
                result.discount()),
            () -> assertEquals(
                new BigDecimal("12.00"),
                result.shipping()),
            () -> assertEquals(
                new BigDecimal("120.00"),
                result.total())
        );
        verify(inventory).availableUnits("ABC-123");
        verifyNoMoreInteractions(inventory);
    }

    @Test
    void rejectsNullRequestWithoutCallingInventory() {
        NullPointerException error =
            assertThrowsExactly(
                NullPointerException.class,
                () -> service.quote(null));

        assertEquals("request", error.getMessage());
        verifyNoInteractions(inventory);
    }

    @ParameterizedTest
    @MethodSource("invalidSkuCases")
    void rejectsInvalidSkuBeforeInventory(String sku) {
        QuoteRequest request = new QuoteRequest(
            sku, 1, new BigDecimal("10.00"), null);

        IllegalArgumentException error =
            assertThrowsExactly(
                IllegalArgumentException.class,
                () -> service.quote(request));

        assertNotNull(error.getMessage());
        verifyNoInteractions(inventory);
    }

    static Stream<Arguments> invalidSkuCases() {
        return Stream.of(
            Arguments.of((Object) null),
            Arguments.of(""),
            Arguments.of("  "),
            Arguments.of("ab"),
            Arguments.of("a_b"),
            Arguments.of("ABC!123"),
            Arguments.of("ABCDEFGHIJKLMNOPQ")
        );
    }

    @ParameterizedTest
    @ValueSource(ints = {
        Integer.MIN_VALUE, -1, 0, 21, Integer.MAX_VALUE
    })
    void rejectsQuantityOutsideOneToTwenty(int quantity) {
        QuoteRequest request = new QuoteRequest(
            "ABC-123", quantity,
            new BigDecimal("10.00"), null);

        IllegalArgumentException error =
            assertThrowsExactly(
                IllegalArgumentException.class,
                () -> service.quote(request));

        assertTrue(error.getMessage().contains("quantity"));
        verifyNoInteractions(inventory);
    }

    @ParameterizedTest
    @MethodSource("invalidUnitPriceCases")
    void rejectsInvalidUnitPriceBeforeInventory(
            BigDecimal price) {
        QuoteRequest request = new QuoteRequest(
            "ABC-123", 1, price, null);

        IllegalArgumentException error =
            assertThrowsExactly(
                IllegalArgumentException.class,
                () -> service.quote(request));

        assertTrue(error.getMessage().contains("unitPrice"));
        verifyNoInteractions(inventory);
    }

    static Stream<Arguments> invalidUnitPriceCases() {
        return Stream.of(
            Arguments.of((Object) null),
            Arguments.of(new BigDecimal("-0.01")),
            Arguments.of(new BigDecimal("0.00")),
            Arguments.of(new BigDecimal("0.001")),
            Arguments.of(new BigDecimal("1.234")),
            Arguments.of(new BigDecimal("10000.01"))
        );
    }

    @Test
    void acceptsTrailingZeroesThatDoNotRequireRounding() {
        when(inventory.availableUnits("ABC-123"))
            .thenReturn(1);

        PriceQuote result = service.quote(
            new QuoteRequest(
                "ABC-123", 1,
                new BigDecimal("10.000"), null));

        assertEquals(
            new BigDecimal("10.00"),
            result.subtotal());
        assertEquals(
            new BigDecimal("22.00"),
            result.total());

        verify(inventory).availableUnits("ABC-123");
    }

    @Test
    void unknownCouponFailsBeforeInventory() {
        InvalidCouponException error =
            assertThrowsExactly(
                InvalidCouponException.class,
                () -> service.quote(new QuoteRequest(
                    "ABC-123", 1,
                    new BigDecimal("150.00"),
                    "BOGUS")));

        assertTrue(error.getMessage().contains("BOGUS"));
        verifyNoInteractions(inventory);
    }

    @Test
    void couponAtOneCentBelowMinimumIsRejected() {
        CouponNotApplicableException error =
            assertThrowsExactly(
                CouponNotApplicableException.class,
                () -> service.quote(new QuoteRequest(
                    "ABC-123", 1,
                    new BigDecimal("99.99"),
                    "SAVE10")));

        assertTrue(error.getMessage().contains("100.00"));
        verifyNoInteractions(inventory);
    }

    @Test
    void stockEqualToRequestedQuantityIsAccepted() {
        when(inventory.availableUnits("ABC-123"))
            .thenReturn(3);

        PriceQuote quote = service.quote(
            new QuoteRequest(
                "ABC-123", 3,
                new BigDecimal("10.00"), null));

        assertEquals(3, quote.quantity());
        assertEquals(
            new BigDecimal("42.00"), quote.total());
        verify(inventory).availableUnits("ABC-123");
    }

    @Test
    void stockOneBelowRequestedIsRejected() {
        when(inventory.availableUnits("ABC-123"))
            .thenReturn(2);

        InsufficientStockException error =
            assertThrowsExactly(
                InsufficientStockException.class,
                () -> service.quote(new QuoteRequest(
                    "ABC-123", 3,
                    new BigDecimal("10.00"), null)));

        assertAll(
            () -> assertEquals(3, error.getRequested()),
            () -> assertEquals(2, error.getAvailable()),
            () -> assertTrue(error.getMessage()
                .contains("insufficient stock"))
        );
        verify(inventory).availableUnits("ABC-123");
        verifyNoMoreInteractions(inventory);
    }

    @Test
    void zeroStockIsRejectedForPositiveQuantity() {
        when(inventory.availableUnits("ABC-123"))
            .thenReturn(0);

        InsufficientStockException error =
            assertThrowsExactly(
                InsufficientStockException.class,
                () -> service.quote(new QuoteRequest(
                    "ABC-123", 1,
                    new BigDecimal("10.00"), null)));

        assertEquals(0, error.getAvailable());
        verify(inventory).availableUnits("ABC-123");
    }

    @Test
    void negativeAvailabilityIsInfrastructureError() {
        when(inventory.availableUnits("ABC-123"))
            .thenReturn(-1);

        InventoryUnavailableException error =
            assertThrowsExactly(
                InventoryUnavailableException.class,
                () -> service.quote(new QuoteRequest(
                    "ABC-123", 1,
                    new BigDecimal("10.00"), null)));

        assertTrue(error.getMessage()
            .contains("negative availability"));
        verify(inventory).availableUnits("ABC-123");
    }

    @Test
    void inventoryPortFailurePropagatesUnchanged() {
        InventoryUnavailableException upstream =
            new InventoryUnavailableException(
                "inventory timeout");

        when(inventory.availableUnits("ABC-123"))
            .thenThrow(upstream);

        InventoryUnavailableException actual =
            assertThrowsExactly(
                InventoryUnavailableException.class,
                () -> service.quote(new QuoteRequest(
                    "ABC-123", 1,
                    new BigDecimal("10.00"), null)));

        assertSame(upstream, actual);
        verify(inventory).availableUnits("ABC-123");
    }

    @Test
    void constructorRejectsMissingInventoryPort() {
        NullPointerException error =
            assertThrowsExactly(
                NullPointerException.class,
                () -> new OrderQuoteService(null));

        assertEquals("inventory", error.getMessage());
        verifyNoInteractions(inventory);
    }

    @Test
    void fakeCanTestCoreFormulaWithoutMockito() {
        InventoryPort fakeInventory = sku -> 20;
        OrderQuoteService policy =
            new OrderQuoteService(fakeInventory);

        PriceQuote result = policy.quote(
            new QuoteRequest(
                "ABC-123", 1,
                new BigDecimal("200.00"),
                "SAVE10"));

        assertAll(
            () -> assertEquals(
                new BigDecimal("200.00"),
                result.subtotal()),
            () -> assertEquals(
                new BigDecimal("20.00"),
                result.discount()),
            () -> assertEquals(
                new BigDecimal("12.00"),
                result.shipping()),
            () -> assertEquals(
                new BigDecimal("192.00"),
                result.total())
        );
    }
}
~~~

### 6.1. Why use `@ParameterizedTest` and `@MethodSource`?

Pricing scenarios share the same structure: build a `QuoteRequest`, mock sufficient stock, call `quote`, and compare six fields plus an invariant. Using **`@MethodSource`** supplies named **`Arguments`** per case, keeping each boundary readable in test reports.

The `validPricingCases` set covers:
- Minimum price `0.01`.
- Small subtotal with shipping fee.
- Net right **below**, **at**, and **above** the `200.00` free-shipping threshold.
- Coupon eligible right at **100.00** pre-discount.
- `HALF_UP` rounding **`10.005` to `10.01`**.
- Coupon turning a free-shipping order into a paid-shipping order.
- Coupon bringing net to exactly `200.00`.
- Quantity at maximum `20`.
- Unit price at maximum `10000.00`.
- Blank coupon applying no discount.
- Lowercase coupon being normalized.

Each case asserts **every `BigDecimal` field** and the **invariant `total = subtotal − discount + shipping`**, then verifies inventory was called once. Asserting only `total` is insufficient: a bug subtracting the wrong discount while adding the wrong shipping could accidentally produce the same total. Asserting `subtotal`/`discount`/`shipping` separately catches errors in the exact branch.

### 6.2. Why not just one happy-path test?

A single test with price 100, quantity 1, and no coupon will fail to catch:
- `quantity=0` or `21` being accepted;
- shipping comparator flipped from `>=` to `>`;
- coupon eligibility comparator flipped from `>=` to `>`;
- discount calculated after shipping;
- 10% computed with `double` causing rounding drift;
- inventory called before validation;
- missing SKU/coupon normalization;
- out-of-stock or inventory timeout swallowed;
- coupon applied after granting free shipping based on subtotal.

Boundary tests are how you **kill mutations near thresholds**. No code coverage percentage replaces asserting the exact contract of each branch.

### 6.3. How does `assertThrowsExactly` differ from `assertThrows`?

**`assertThrows(IllegalArgumentException.class, ...)`** passes if the thrown exception is a subclass of `IllegalArgumentException`. For distinct business branches like **`InvalidCouponException`** or **`CouponNotApplicableException`**, **`assertThrowsExactly`** requires the exact class to be thrown, preventing a test from passing due to an unexpected exception sharing the same superclass.

Use `assertThrows` when the contract intentionally accepts subtypes; use `assertThrowsExactly` when the **specific type** is part of the API. Never just `assertThrows(Exception.class)` or catch `Throwable` and call it a passing test.

For exceptions carrying data, verify **`requested`**, **`available`**, message keys, or cause. Avoid asserting full stack traces, line numbers, internal Mockito proxy class names, or locale-dependent wording outside the contract.

### 6.4. `assertAll` and `BigDecimal`

**`assertAll`** groups multiple assertions for one result. If one field is wrong, JUnit can report multiple failures together instead of stopping at the first field. This helps on multi-field quotes.

**`new BigDecimal("10.00")`** and **`new BigDecimal("10.0")`** are numerically equal, but `BigDecimal.equals` also requires equal scale. In this demo, the service returns **scale 2**, so `assertEquals(BigDecimal("10.00"), result)` checks both **value** and the scale contract. If business only needs numerical equality, use `compareTo` or AssertJ's `isEqualByComparingTo`; choose intentionally so scale differences do not become false bugs.

**Never use `BigDecimal(double)`** to construct money amounts or call `equals` between `BigDecimal`s of arbitrary scale. `HALF_UP` here is an illustrative policy; real-world money/tax may require currency-specific rounding rules, tax jurisdictions, and a dedicated `Money` object.

### 6.5. What does `verifyNoInteractions` protect?

A request with `quantity=0` or an unknown coupon can be rejected immediately without wasting a network/database call. **`verifyNoInteractions(inventory)`** asserts that. If the implementation is modified to query inventory before validation, the test fails even though the exception remains the same.

Note: **`verifyNoInteractions` does not prove there are no side effects outside the mock** (such as writing files or mutating static global state). Design services to interact only through observable ports, or add integration tests for real effects. Do not mock every dependency just to assert call counts, as tests become implementation-coupled.

### 6.6. When is `verifyNoMoreInteractions` too strict?

For a **command** whose contract requires querying inventory exactly once for cost/consistency reasons, `verifyNoMoreInteractions` makes sense. But if the implementation is allowed to cache, prefetch, or batch, hard-coding call counts pins unimportant internal optimizations. Only verify interactions that belong to the contract, rather than locking down every internal helper method call.

Here `InventoryPort` has a single simple method; checking once aligns with avoiding redundant queries and side effects.

## 7. Reading the boundary matrix: below – at – above

### 7.1. Quantity

| Quantity | Scenario | Expectation |
| --- | --- | --- |
| -1 | Below min | IllegalArgumentException |
| 0 | Just below min | IllegalArgumentException |
| 1 | Valid min | Quote succeeds |
| 20 | Valid max | Quote succeeds if stock suffices |
| 21 | Just above max | IllegalArgumentException |
| Integer.MAX_VALUE | Extreme out-of-range | IllegalArgumentException |

Negative quantities and 0 are invalid. Specifically **1 and 20** catch bugs changing `>=` to `>` or `<=` to `<`. You do not need to run every integer in the range to prove boundary conditions; adding a few representative middle values and invariant tests suffices for simple rules.

### 7.2. Monetary values

| Unit price | Expectation | Reason |
| --- | --- | --- |
| null | Error | Required |
| -0.01 | Error | Negative |
| 0.00 | Error | Below minimum |
| 0.001 | Error | Below minimum |
| 0.01 | Success | Exact lower bound |
| 1.234 | Error | Requires rounding to cents |
| 10.000 | Success, normalized 10.00 | Extra trailing zeroes exact |
| 10000.00 | Success | Exact upper bound |
| 10000.01 | Error | Above max |

Unit price has a max to guard against absurd data; quantity also has a max, so subtotal can exceed max unit price while remaining valid. **Do not mistakenly apply max unit price to subtotal.**

### 7.3. Coupon threshold

| Pre-discount subtotal | Coupon | Expectation |
| --- | --- | --- |
| 99.99 | SAVE10 | CouponNotApplicableException |
| 100.00 | SAVE10 | Discount 10.00 |
| 100.05 | SAVE10 | Discount 10.01, HALF_UP |
| 200.00 | SAVE10 | Discount 20.00, net 180.00 |
| 222.22 | SAVE10 | Discount 22.22, net 200.00 |
| 50.00 | null | No discount |
| 50.00 | unknown | InvalidCouponException |

**Include a negative case just below 100.00 and a positive case at exactly 100.00.** If the implementation uses `>` instead of `>=`, this pair catches it. Also include an unknown-coupon test to distinguish invalid codes from valid-but-ineligible codes.

### 7.4. Shipping threshold on post-discount net

| Subtotal | Discount | Net | Shipping |
| --- | --- | --- | --- |
| 199.99 | 0.00 | 199.99 | 12.00 |
| 200.00 | 0.00 | 200.00 | 0.00 |
| 200.01 | 0.00 | 200.01 | 0.00 |
| 200.00 | 20.00 | 180.00 | 12.00 |
| 222.22 | 22.22 | 200.00 | 0.00 |

Do not assume “subtotal >= 200 means free shipping” when a coupon reduces net below the threshold. That is a combined discount-and-shipping branch often missed by tests that only check each rule in isolation.

### 7.5. Inventory

| Available | Quantity | Expectation |
| --- | --- | --- |
| -1 | 1 | InventoryUnavailableException |
| 0 | 1 | InsufficientStockException |
| 2 | 3 | InsufficientStockException(requested=3, available=2) |
| 3 | 3 | Success |
| 4 | 3 | Success |
| InventoryPort throws | 1 | Exception propagates per policy |

**Different boundaries have different semantics.** `Available = -1` must not be interpreted as merely missing one item; it indicates an invalid inventory adapter/response needing investigation. In a production adapter, it is usually better to throw a typed exception when upstream fails rather than returning a negative sentinel; the demo unit test still checks the port's invariant.

## 8. Designing independent, repeatable tests

### Do not use `@SpringBootTest` for domain unit tests

A quote service test does not need Spring IoC, an HTTP server, JPA, Kafka, or `@Transactional`. **`@SpringBootTest`** builds an `ApplicationContext` that may pull in unrelated configurations and external dependencies, making tests slower and flakier. Use:

~~~java
@ExtendWith(MockitoExtension.class)
class OrderQuoteServiceTest {
    @Mock InventoryPort inventory;
    OrderQuoteService service;

    @BeforeEach
    void setUp() {
        service = new OrderQuoteService(inventory);
    }
}
~~~

The suite runs with JUnit 5 + Mockito. `MockitoExtension` creates/manages mocks and strict stubbing. Do not manually call `MockitoAnnotations.openMocks` alongside `MockitoExtension` unnecessarily, as it can create overlapping lifecycles or improperly closed resources.

### Do not use clocks, networks, or randomness in tests

Quotes are deterministic from `QuoteRequest` and `InventoryPort` responses. Real-world rules involving expiration times or FX rates should inject **`Clock`**, **`ExchangeRatePort`**, and **`TaxPolicy`** via contract and fake them. If a test calls `Instant.now` or a live remote rate API, it stops being deterministic. A unit test should run repeatedly with the same seed data and yield identical results.

### Make tests fail when the implementation is wrong

A test containing only:

~~~java
assertNotNull(service.quote(validRequest));
~~~

will pass even when discount/shipping/total are wrong. It is better to assert exact fields, exception types, boundary behavior, and relevant port interactions. Test data should differentiate between two branches instead of picking numbers where both branches produce the same output.

### Do not assert non-contract internals

Do not use reflection to inspect the private `MIN_COUPON_SUBTOTAL` constant or verify private methods. Test **observable public behavior** from `quote()` rather than implementation details. Changing helper methods or refactoring code should not break tests if behavior has not changed.

### Unit tests do not check reservation races

The `quote` method only **reads `availableUnits`**; it does not atomically reserve stock. Two concurrent orders could both see enough stock; that is an order-placement/reservation concern. Integration tests should verify transactions/isolation/optimistic locking if business requires stock holding. Never describe this unit test as proof of concurrent order safety.

## 9. Protecting error branches with exact exceptions

### Invalid input is `IllegalArgumentException`

- Invalid SKU format.
- Quantity outside 1..20.
- `unitPrice` null/out-of-range/invalid precision.

These errors occur before `InventoryPort`. Tests use `assertThrowsExactly(IllegalArgumentException.class)` and `verifyNoInteractions`.

### `InvalidCouponException` vs `CouponNotApplicableException`

- Unknown code: **`InvalidCouponException`**.
- `SAVE10` validly named but subtotal below 100.00: **`CouponNotApplicableException`**.

Both extend `IllegalArgumentException`, yet user/business error mapping may differ (e.g., `INVALID_COUPON` vs `COUPON_MINIMUM_NOT_MET`). Therefore unit tests require exact subclasses instead of generic `IllegalArgumentException`.

### `InsufficientStockException` and `InventoryUnavailableException`

- Stock returns 2 when ordering 3: **`InsufficientStockException`**, carrying `requested`/`available`.
- Stock returns -1: **`InventoryUnavailableException`**, not a low-stock state.
- Adapter throws `InventoryUnavailableException`: **propagate unchanged** per code.

Never return a zero-total `PriceQuote` when inventory is unavailable: that fails open, masking errors or creating bad payment decisions. If the product wants a cached-stock fallback, design an explicit policy with tests for stale-data semantics; do not infer it from this demo.

## 10. Measuring coverage without equating it to quality

**Line coverage** shows how many lines were executed. **Branch coverage** shows whether true/false conditions were traversed. Yet even high branch coverage can lack strong assertions.

For example:

~~~java
if (net.compareTo(FREE_SHIPPING_AT) >= 0) {
    shipping = ZERO;
}
~~~

A test with `net=250` and a test with `net=50` cover both branches yet **fail to catch mutating `>=` to `>`**. Add a test at `net=200` exactly. Similarly:
- `Quantity=1` and `20` to test inclusive endpoints.
- `Coupon subtotal=99.99` and `100.00`.
- `Stock available=quantity-1` and `quantity`.
- `Discount 10.005` to catch swapping `HALF_UP` for `HALF_EVEN` or `DOWN` in the right case.
- `UNKNOWN` coupon and valid-but-ineligible coupon to catch merged exception branches.

**Mutation testing** (such as PIT for Java) intentionally flips operators/constants to measure whether tests detect bugs. It is a supplementary tool, not a replacement for the business spec. A test can kill a mutant while asserting wrong expected behavior if the initial spec was wrong. Prioritize business review and meaningful boundary cases.

### Data tables are evidence, not random data

`@MethodSource` clearly documents `caseName`, `price`, `quantity`, `coupon`, and expected numbers. Test reports immediately reveal which scenario failed. Use concise, discriminating test data; avoid 1,000 random cases that are hard to debug when failing. If property-based testing is needed, choose jqwik/QuickTheories with fixed seeds, shrinking, and clear invariants—while keeping example-based boundary tests.

## 11. Techniques: `assertAll`, `assertThrowsExactly`, and Mockito

### Assert all fields without circular assertions

The codebase asserts expected fields using independent literals. It also asserts **`subtotal - discount + shipping = total`**. Invariants are useful, though if a test only compares two values computed by the same buggy implementation it can miss errors. Always include exact expected numbers from the business spec.

### Check exception, cause, and message

~~~java
InsufficientStockException error =
    assertThrowsExactly(
        InsufficientStockException.class,
        () -> service.quote(request));

assertAll(
    () -> assertEquals(3, error.getRequested()),
    () -> assertEquals(2, error.getAvailable())
);
~~~

This is an illustrative snippet inside a test. Error message wording can change with language or refactoring; prefer contract codes/types/structured fields over asserting full English sentences unless required.

### Verify no port call on error branches

~~~java
assertThrowsExactly(
    IllegalArgumentException.class,
    () -> service.quote(badRequest));

verifyNoInteractions(inventory);
~~~

This is a key assertion about validation order. For positive cases:

~~~java
verify(inventory).availableUnits("ABC-123");
verifyNoMoreInteractions(inventory);
~~~

Verifications should tie to the real contract: SKU normalization and query count. If business rules change to allow batch checks or cache refreshes, update the test spec before refactoring instead of turning every internal detail into a brittle assertion.

### `@ParameterizedTest` does not automatically provide Spring context isolation

JUnit Jupiter defaults to `PER_METHOD`, creating a new test instance per invocation lifecycle; `MockitoExtension` initializes fresh mocks accordingly. Still, static mutable state or system properties can leak between test cases. Do not use a static inventory map mutated by cases without resetting. Parameterized tests still need deterministic, independent invocations.

## 12. Testing validation priority order

When an input has multiple simultaneous errors, the service currently follows this order:
1. null request;
2. SKU format;
3. quantity range;
4. unitPrice range/precision;
5. unknown/ineligible coupon;
6. inventory availability.

If tests must enforce **which error takes precedence**, add contracts:
- Unknown coupon + stock unavailable → coupon error first and no inventory call.
- Quantity=0 + invalid coupon → quantity error first.
- Invalid unit price + missing stock → price error first.

Do not assume every service must share this demo's validation order. Order is only a contract when agreed with product and reflected in API error responses. At minimum, ensure **invalid requests never call outbound ports**, as that is efficient and safe. The current service does this properly.

In an API integration, controller Bean Validation may reject earlier than domain validation. That is a different layer; `OrderQuoteService` unit tests remain important because the service can be invoked from a scheduler, message consumer, or another service bypassing HTTP.

## 13. Combining with real Spring Boot

Integrating the policy into a Spring context typically requires an adapter implementing `InventoryPort`:

~~~java
@Configuration(proxyBeanMethods = false)
class QuoteWiring {

    @Bean
    OrderQuoteService orderQuoteService(
            InventoryPort inventoryPort) {
        return new OrderQuoteService(inventoryPort);
    }
}
~~~

This is **only an integration-guiding snippet**, not part of the current runnable tree because there is no `InventoryPort` adapter bean. When adding a real adapter (JPA, JDBC, or HTTP client), add:
- `@SpringBootTest` checking bean registration and dependency injection;
- Repository/JPA integration tests checking data/query contracts;
- HTTP/MVC tests checking request validation and status mapping from exceptions;
- Transaction tests checking stock reservation if order placement has side effects;
- Testcontainers to verify real database dialects/constraints when relevant.

A passing `@SpringBootTest contextLoads` does not prove coupon thresholds, `HALF_UP` rounding, or stock boundaries are right. Unit tests are a separate layer of evidence that run very quickly so CI can execute them frequently.

### Separating Quote vs PlaceOrder

Quoting **does not decrement stock**. Production `PlaceOrder` may need:
- saving the order inside a transaction;
- checking inventory lock/version;
- an idempotency key to prevent double-charging;
- pricing consistency validation;
- external payment timeout handling;
- outbox/event publishing.

Those are separate integration/contract tests. Do not mock `InventoryPort` and claim stock was reserved atomically. Unit tests should never promise what the implementation does not do.

## 14. Real-world mistakes and how to avoid them

| Anti-pattern | Consequence | Alternative |
| --- | --- | --- |
| Only testing happy path 200.00 | Misses min/max bugs | Under/at/over boundary |
| Line coverage only, no money assertions | Wrong total still passes | Assert exact fields + invariants |
| Using double for money | Precision drift | BigDecimal(String), explicit scale/rounding policy |
| Using `==` or `equals` without understanding scale | Broken money assertions | compareTo or value+scale contract |
| Calculating shipping before discount | Wrong combined rule | Test coupon flipping free→paid |
| Coupon threshold using `>` instead of `>=` | Fails right at 100.00 | Test subtotal=100.00 |
| Free shipping threshold using `>` instead of `>=` | Net 200 still charged shipping | Test net=200.00 |
| Quantity=0 calls inventory first | Unnecessary side effect | verifyNoInteractions |
| Mocking OrderQuoteService itself | Rule never runs | Real service, mock InventoryPort |
| `@SpringBootTest` for every branch test | Slow, context-coupled | Plain JUnit + Mockito |
| Testing generic exception superclass | Masks wrong branch | Typed `assertThrowsExactly` |
| Leaving Mockito default answer 0 and thinking it's a stock=0 fixture | False-passing test | Explicit stub per scenario |
| Verifying every helper call | Brittle refactoring | Verify contract-boundary effects |
| Non-reproducible random test cases | Flaky | Table-driven deterministic |
| Shared static inventory map | Cross-test contamination | Per-test fake/mock |
| Not separating invalid coupon and ineligible coupon | Wrong API error code | Two typed exceptions |
| Swallowing InventoryUnavailable and returning total 0 | Dangerous fail-open | Propagate typed failure |
| Turning quote into stock reserve without transaction | Overselling | Integration/transaction tests |
| Asserting full exception stacktrace | Brittle | Type + relevant structured details |
| Huge fixtures with multiple simultaneous errors | Unclear which branch won | One primary invalid condition per test |
| Hard-coding default timezone/locale | CI environment differences | Explicit Locale/Clock when needed |

## 15. Run commands and expected outcomes

After creating the files and a Java 17-compatible Gradle Wrapper:

~~~bash
./gradlew clean test
./gradlew test --tests com.example.quoteqa.OrderQuoteServiceTest
./gradlew test --tests com.example.quoteqa.OrderQuoteServiceTest.calculatesQuoteAtImportantBoundaries
./gradlew test --tests com.example.quoteqa.OrderQuoteServiceTest.couponAtOneCentBelowMinimumIsRejected
./gradlew test --tests com.example.quoteqa.OrderQuoteServiceTest.stockOneBelowRequestedIsRejected
~~~

On Windows use **`gradlew.bat`**. If wrapper scripts are not yet generated in a new project, use an installed Gradle or generate the wrapper first; `build.gradle` alone does not supply `./gradlew`. **No `BUILD SUCCESSFUL` log was observed while authoring this README.**

| Test group | Expectation |
| --- | --- |
| validPricingCases | 13 valid samples, exact quote fields |
| normalizesSkuAndCouponBeforeInventoryCall | Normalized SKU/coupon; inventory called once |
| rejectsNullRequestWithoutCallingInventory | Exact NullPointerException; no interaction |
| rejectsInvalidSkuBeforeInventory | 7 invalid SKU cases; no interaction |
| rejectsQuantityOutsideOneToTwenty | 5 invalid quantities; no interaction |
| rejectsInvalidUnitPriceBeforeInventory | 6 invalid prices; no interaction |
| acceptsTrailingZeroesThatDoNotRequireRounding | 10.000 → 10.00; total 22.00 |
| unknownCouponFailsBeforeInventory | InvalidCouponException; no interaction |
| couponAtOneCentBelowMinimumIsRejected | CouponNotApplicableException |
| stockEqualToRequestedQuantityIsAccepted | available=quantity accepted |
| stockOneBelowRequestedIsRejected | InsufficientStockException(3,2) |
| zeroStockIsRejectedForPositiveQuantity | InsufficientStockException |
| negativeAvailabilityIsInfrastructureError | InventoryUnavailableException |
| inventoryPortFailurePropagatesUnchanged | Same exception instance propagated |
| constructorRejectsMissingInventoryPort | NullPointerException inventory |
| fakeCanTestCoreFormulaWithoutMockito | Quote net 180 + ship 12 = total 192 |

JUnit `@ParameterizedTest` from `@MethodSource` runs one invocation per row in `validPricingCases`; `@MethodSource` for invalid SKU/price and `@ValueSource` for quantity expand the test invocation count. Do not simply count Java `@Test` method annotations to report total tests: each parameterized case is a separate invocation.

## 16. Follow-up exercises after completion

**Exercise A — verify coupon SAVE10 is rejected at 99.99 but accepted at 100.00.** Write two independent assertions. Why are 99.00 and 101.00 insufficient? Because they fail to catch an off-by-one equals sign at the threshold.

**Exercise B — multiplication and rounding.** Test `100.05 × 10% = 10.005 → 10.01`. Write a test that catches mutating `HALF_UP` to `HALF_EVEN`. With `10.005`, `HALF_EVEN` produces `10.00`, so asserting `10.01` distinguishes them.

**Exercise C — shipping.** Pass `subtotal=200.00` and `SAVE10`; expected `total=192.00`. Why might a test at price `250.00` miss this? Because after discount `225` still qualifies for free shipping, hiding the free→paid transition.

**Exercise D — normalization.** Raw SKU `" abc-123 "` must call `inventory.availableUnits("ABC-123")`, never the raw string. Raw coupon `" save10 "` must apply 10%.

**Exercise E — performance.** Test `verifyNoInteractions` for invalid inputs; in a real adapter where `InventoryPort` queries a DB, what is the benefit? Preventing invalid requests from causing unnecessary I/O, load, and side effects.

**Exercise F — add coupon SAVE20.** Extend the policy so another coupon gives 20% off with its own threshold. Add exact-type exception tests, boundary tables, unknown-code tests, and post-discount shipping tests. Do not copy SAVE10 tests and forget the new threshold.

**Exercise G — tax calculation.** If applying VAT, determine the base (pre/post discount), rounding order, shipping taxability, and currency policy before writing code. A test without a spec cannot decide the right output.

**Exercise H — stock reservation.** Add a `PlaceOrderService` with transactions; write integration tests for concurrent requests and uniqueness/idempotency. Do not try to prove atomicity with `verify(mock).availableUnits()`.

**Exercise I — mutation testing.** Use PIT to mutate `>=`/`>` and `<`/`<=` operators on thresholds. Triage surviving important mutants instead of running the tool just to boost a percentage.

**Exercise J — test report.** Name parameterized cases clearly so report readers immediately know which boundary failed. Do not dump all cases into one `for`-loop with contextless failure messages.

## 17. Self-check questions

**1.** Why test `quantity=0` and `1`? Because min 1 is inclusive; 0 must fail, 1 must pass.

**2.** Why test `quantity=20` and `21`? Because max 20 is inclusive; 20 passes, 21 fails.

**3.** Why are `coupon subtotal=99.99` and `100.00` important? To catch wrong comparison operators at the threshold.

**4.** Is shipping based on subtotal or net? **Post-discount net** per the demo spec.

**5.** What total does subtotal 200 with SAVE10 produce? **192.00** (net 180 + shipping 12).

**6.** Does subtotal 222.22 with SAVE10 get free shipping? **Yes**, discount 22.22 and net 200.00.

**7.** Is price `10.000` rejected? **No**, it can be represented as `10.00` exactly.

**8.** Is price `1.234` rejected? **Yes**, it requires rounding to keep 2 decimals.

**9.** Is using `double` for money acceptable? **No**, use `BigDecimal(String)` and an explicit rounding policy.

**10.** What is `HALF_UP` of `10.005` to 2 decimals? **10.01**.

**11.** Why should exception message assertions also be selective? Full sentences easily change; types and structured data are usually more stable.

**12.** How do `assertThrowsExactly` and `assertThrows` differ? `Exactly` requires the exact class; `assertThrows` accepts subtypes.

**13.** How is `assertAll` useful? It reports multiple errors for the same quote in a single invocation.

**14.** What does `verifyNoInteractions` for an invalid price prove? Input validation does not call inventory.

**15.** What does `available = quantity − 1` yield? **`InsufficientStockException`**.

**16.** What does `available = quantity` yield? **Success**, the stock boundary.

**17.** Is negative `available` treated as simply low stock? **No**, the service throws `InventoryUnavailableException`.

**18.** Is `@SpringBootTest` needed for pure price calculation? **No**.

**19.** Should you mock `BigDecimal` or the service itself? **No**, use real instances; mock the outbound port.

**20.** What does `@MethodSource` do? Supplies multiple input/expected cases to a parameterized test.

**21.** What does `MockitoExtension` provide? Mock setup/teardown and stubbing lifecycle for JUnit Jupiter.

**22.** Does a single test at 200.00 catch the 100.00 coupon eligibility threshold? **Not necessarily**; you need tests right at the 100.00 threshold.

**23.** Do unit tests prove JPA queries and real transactions? **No**, integration tests are required.

**24.** Does a quote unit test guarantee no overselling under concurrent orders? **No**, quoting does not reserve stock.

**25.** Core rule? **Test observable behavior on both success and failure, just below/at/just above thresholds, with exact assertions and zero calls to side-effect ports on invalid input.**

### QA Checklist

- Did you write the spec with inputs, thresholds, rounding, and error behavior before coding?
- Did you test inclusive min/max and adjacent invalid values?
- Did you assert exact discount, shipping, and total with explicit `BigDecimal` scale?
- Did you test coupon 99.99/100.00 and shipping 199.99/200.00/200.01?
- Did you test a coupon turning a free-shipping order into a paid-shipping order?
- Did you test `HALF_UP` on an exact half-cent case?
- Did you test SKU/coupon normalization and the exact port argument?
- Did you test null request, SKU, quantity, price, and unknown coupon?
- Did you assert exact exception types for `InvalidCoupon`, `CouponNotApplicable`, `InsufficientStock`, and `InventoryUnavailable`?
- Did you test stock equal / one less / zero / negative / error from port?
- Do invalid requests verify `verifyNoInteractions(inventory)`?
- Do valid requests verify inventory is called exactly once?
- Are inputs deterministic, without reading the system clock, randomness, or real network?
- Did you use JUnit `@ParameterizedTest`/`@MethodSource` so boundary tables are clear?
- Did you separate domain policy unit tests from Spring integration/wiring tests?
- Did you avoid mocking the class under test or asserting private internals?
- Did you avoid treating coverage percentage as a substitute for assertion strength?
- Did you avoid claiming Gradle ran if there is no runtime log?

**Conclusion:** A high-value unit test does more than prove “the price came out right” for one nice input. It must confirm **rejection branches, inclusive/exclusive boundary conditions, accurate calculations, controlled side effects, and per-field contract compliance**. With **JUnit Jupiter + Mockito**, keep `OrderQuoteService` as the real subject, fake `InventoryPort`, use parameterized scenarios at thresholds, and use structured exception assertions. This provides the foundation to combine with Spring Boot integration tests at the adapter/transaction/API layers when broader evidence is needed.

## Official documentation

- Spring Boot 3.4 — Test Scope Dependencies (JUnit 5, Mockito, AssertJ): https://docs.spring.io/spring-boot/3.4/reference/testing/test-scope-dependencies.html
- Spring Boot 3.4 — Testing: https://docs.spring.io/spring-boot/3.4/reference/testing/index.html
- JUnit Jupiter — Writing Tests, Assertions, and Parameterized Tests: https://docs.junit.org/current/user-guide/
- JUnit 5 — Parameterized Tests / @MethodSource: https://junit.org/junit5/docs/current/user-guide/#writing-tests-parameterized-tests-sources-MethodSource
- Mockito — MockitoExtension API: https://javadoc.io/doc/org.mockito/mockito-junit-jupiter/latest/org/mockito/junit/jupiter/MockitoExtension.html
- Mockito — Verification API: https://javadoc.io/doc/org.mockito/mockito-core/latest/org/mockito/Mockito.html
- Java 17 — BigDecimal compareTo, setScale, RoundingMode: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html
- Java 17 — RoundingMode: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/RoundingMode.html

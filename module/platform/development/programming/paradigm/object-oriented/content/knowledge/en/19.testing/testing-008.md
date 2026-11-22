# Avoiding Tests Overcoupled to Internal Details

> **Context:** OOP → Testing. The goal is to catch business defects while allowing implementation refactoring when public behavior remains unchanged.

## 1. The Problem: A Test Can Be Right Today but Block Tomorrow's Changes

When a class under test (SUT — System Under Test) uses collaborators, many details are *observable*: return values, exceptions, state, emails sent, dependency call counts, helper call order, private field names, and collection types. But not all are **client contracts**.

An **implementation-coupled test** fails when developers change algorithms, split or combine helpers, add caching, or replace data structures even though promised client behavior remains correct. This is a *brittle test*.

A reliable test asks: **Given this input, which required outcome or side effect follows?** Verify interactions only when actual requirements constrain those interactions.

| Overcoupled Test | Contract-Oriented Test |
|---|---|
| Uses reflection to invoke private calculateSubtotal helper | Calls the public quote API and asserts the total |
| Verifies catalog.priceOf is called exactly 2 times | Asserts repeated SKUs are priced correctly across line items |
| Asserts the implementation uses HashMap | Asserts business results across data sets |
| Verifies 5 helper calls in a particular order | Asserts final state and meaningful side effects |
| Asserts error messages including line numbers/stack traces | Asserts promised error types and information |

**Important exception:** sending mail, writing databases, charging payments, and publishing events can be **observable side effects**. Verifying *no mail is sent after a failed payment* is entirely valid because that is a business rule. An internal interaction is merely an implementation detail when no contract promises it.

## 2. Standalone Example: Two Algorithms, One Contract

Quote-service requirements:
- Every line has an SKU and a positive integer quantity; the cart is nonempty.
- Merchandise subtotal equals unit prices multiplied by quantities and summed.
- Shipping costs 30.000 VND below a 500.000 VND subtotal and is free at 500.000 VND or above.
- Return merchandise subtotal, shipping, and total; the number of SKU price lookups **is not** part of the public contract.

Implementation A looks up the price of each line; implementation B groups quantities by SKU first, then looks up prices. This refactor may reduce calls to collaborator **PriceCatalog** without changing results. We write one suite for both.

Save the following as **QuoteContractDemo.java**; it uses Java 11 or newer and requires no JUnit:

~~~java
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public class QuoteContractDemo {
    static final long FREE_SHIPPING_FROM = 500_000L;
    static final long SHIPPING_FEE = 30_000L;

    static final class Line {
        final String sku;
        final int quantity;
        Line(String sku, int quantity) {
            this.sku = sku;
            this.quantity = quantity;
        }
    }

    static final class Quote {
        final long subtotal;
        final long shipping;
        final long total;
        Quote(long subtotal, long shipping) {
            this.subtotal = subtotal;
            this.shipping = shipping;
            this.total = Math.addExact(subtotal, shipping);
        }
    }

    interface PriceCatalog {
        long priceOf(String sku);
    }

    interface QuoteService {
        Quote quote(List<Line> lines);
    }

    // Test fake: giá cố định trong RAM, không dùng API hay database.
    static final class FakeCatalog implements PriceCatalog {
        private final Map<String, Long> prices =
                Map.of("BOOK", 200_000L, "PEN", 50_000L);
        int lookups;

        @Override
        public long priceOf(String sku) {
            lookups++;
            Long price = prices.get(sku);
            if (price == null) {
                throw new IllegalArgumentException("Unknown SKU: " + sku);
            }
            return price;
        }
    }

    private static void validate(List<Line> lines) {
        if (lines == null || lines.isEmpty()) {
            throw new IllegalArgumentException("Empty cart");
        }
        for (Line line : lines) {
            if (line == null || line.sku == null
                    || line.sku.isBlank() || line.quantity <= 0) {
                throw new IllegalArgumentException("Invalid line");
            }
        }
    }

    private static Quote buildQuote(long subtotal) {
        return new Quote(subtotal,
                subtotal >= FREE_SHIPPING_FROM ? 0L : SHIPPING_FEE);
    }

    // Implementation A: tra giá một lần cho từng dòng.
    static final class PerLineService implements QuoteService {
        private final PriceCatalog catalog;
        PerLineService(PriceCatalog catalog) {
            this.catalog = catalog;
        }

        @Override
        public Quote quote(List<Line> lines) {
            validate(lines);
            long subtotal = 0L;
            for (Line line : lines) {
                long amount = Math.multiplyExact(
                        catalog.priceOf(line.sku), (long) line.quantity);
                subtotal = Math.addExact(subtotal, amount);
            }
            return buildQuote(subtotal);
        }
    }

    // Implementation B: gộp SKU, mỗi SKU chỉ tra giá một lần.
    // Tổng quantity dùng long vì nhiều dòng int dương có thể vượt int.
    static final class GroupedService implements QuoteService {
        private final PriceCatalog catalog;
        GroupedService(PriceCatalog catalog) {
            this.catalog = catalog;
        }

        @Override
        public Quote quote(List<Line> lines) {
            validate(lines);
            Map<String, Long> grouped = new LinkedHashMap<>();
            for (Line line : lines) {
                grouped.merge(line.sku, (long) line.quantity, Math::addExact);
            }

            long subtotal = 0L;
            for (Map.Entry<String, Long> entry : grouped.entrySet()) {
                long amount = Math.multiplyExact(
                        catalog.priceOf(entry.getKey()),
                        entry.getValue());
                subtotal = Math.addExact(subtotal, amount);
            }
            return buildQuote(subtotal);
        }
    }

    private static void check(boolean ok, String message) {
        if (!ok) throw new AssertionError(message);
    }

    private static void assertQuote(QuoteService service,
                                    List<Line> lines,
                                    long subtotal, long shipping, long total) {
        Quote actual = service.quote(lines);
        check(actual.subtotal == subtotal, "Wrong subtotal");
        check(actual.shipping == shipping, "Wrong shipping");
        check(actual.total == total, "Wrong total");
    }

    private static void expectInvalid(Runnable action) {
        try {
            action.run();
        } catch (IllegalArgumentException expected) {
            return;
        }
        throw new AssertionError("Expected invalid input rejection");
    }

    // Kiểm tra hợp đồng, không biết SUT dùng vòng lặp nào.
    private static void runContract(QuoteService service) {
        // 2 dòng trùng BOOK: 400.000 + 2 PEN: 100.000.
        assertQuote(service, List.of(
                new Line("BOOK", 1),
                new Line("BOOK", 1),
                new Line("PEN", 2)),
                500_000L, 0L, 500_000L);

        // Thấp hơn ngưỡng: vẫn tính phí.
        assertQuote(service,
                List.of(new Line("BOOK", 1)),
                200_000L, 30_000L, 230_000L);

        // Hai quantity int đều hợp lệ, nhưng cộng lại vượt Integer.MAX_VALUE.
        // Tổng tiền vẫn nằm trong miền long: hai implementation phải như nhau.
        assertQuote(service, List.of(
                new Line("BOOK", Integer.MAX_VALUE),
                new Line("BOOK", Integer.MAX_VALUE)),
                858_993_458_800_000L, 0L, 858_993_458_800_000L);

        expectInvalid(() -> service.quote(List.of()));
        expectInvalid(() ->
                service.quote(List.of(new Line("BOOK", 0))));
    }

    public static void main(String[] args) {
        FakeCatalog first = new FakeCatalog();
        FakeCatalog second = new FakeCatalog();

        runContract(new PerLineService(first));
        runContract(new GroupedService(second));

        System.out.println("Both implementations PASS");
        System.out.println("Per-line lookups: " + first.lookups);
        System.out.println("Grouped lookups: " + second.lookups);
    }
}
~~~

Run:

~~~bash
javac QuoteContractDemo.java
java QuoteContractDemo
~~~

Expected output:

~~~text
Both implementations PASS
Per-line lookups: 6
Grouped lookups: 4
~~~

The suite **PASSES for both implementations**. The price-lookup counters illustrate an implementation difference (6 versus 4 calls for three valid carts), not a pass condition. A test insisting on exactly four lookups would fail after a refactor even when prices remained correct.

The cases deliberately detect real business defects: duplicate SKUs, free shipping at **exactly 500.000**, below-threshold carts, empty input, quantity 0, and total quantities beyond `int` while money totals still fit `long`. Changing the comparison from >= to > makes the boundary case fail: a meaningful regression.

## 3. A Brittle Mockito Test and Its Replacement

This anti-pattern assumes the section 2 classes are imported appropriately and Mockito is available:

~~~java
PriceCatalog catalog = mock(PriceCatalog.class);
when(catalog.priceOf("BOOK")).thenReturn(200_000L);
when(catalog.priceOf("PEN")).thenReturn(50_000L);

QuoteService service = new PerLineService(catalog);
service.quote(List.of(
        new Line("BOOK", 1),
        new Line("BOOK", 1),
        new Line("PEN", 2)));

verify(catalog, times(2)).priceOf("BOOK");
verify(catalog, times(1)).priceOf("PEN");
~~~

Replacing PerLineService with GroupedService reduces BOOK lookups from 2 to 1. The test fails even though the contract is unchanged.

A more durable test (JUnit 5, in the same package as the sample classes):

~~~java
import java.util.List;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;

class QuoteBehaviorTest {
    @Test
    void duplicateSkuKeepsCorrectTotals() {
        QuoteContractDemo.PriceCatalog catalog = sku -> {
            if (sku.equals("BOOK")) return 200_000L;
            if (sku.equals("PEN")) return 50_000L;
            throw new IllegalArgumentException("Unknown SKU");
        };
        QuoteContractDemo.QuoteService service =
                new QuoteContractDemo.GroupedService(catalog);

        QuoteContractDemo.Quote quote = service.quote(List.of(
                new QuoteContractDemo.Line("BOOK", 1),
                new QuoteContractDemo.Line("BOOK", 1),
                new QuoteContractDemo.Line("PEN", 2)));

        assertEquals(500_000L, quote.subtotal);
        assertEquals(0L, quote.shipping);
        assertEquals(500_000L, quote.total);
    }
}
~~~

This test remains green whether PerLineService or GroupedService is used. Add JUnit Jupiter dependencies and run with a Maven/Gradle/IDE test runner; section 2's standalone example needs no dependencies.

**Why not verify PriceCatalog calls?** Here lookup is only a means to calculate prices. If a new requirement states “look up each SKU at most once per quote,” the lookup limit becomes **a testable contract**. Add a separately named assertion for that new constraint; implementation A then fails while B passes.

## 4. When Interaction Verification Is Truly Appropriate

Collaborators at external boundaries—mail, payments, event publication, databases—may have **side effects**. If the rule is “do not send an invoice after payment is declined,” verify that no invoice send was requested on failure. Illustrative Mockito snippet (types are application-defined):

~~~java
when(gateway.charge(orderId, totalVnd)).thenReturn(false);

CheckoutResult result = checkout.checkout(orderId);

assertEquals(CheckoutResult.PAYMENT_DECLINED, result);
verifyNoInteractions(receiptSender);
~~~

Here, **not calling ReceiptSender** is a meaningful requirement, unlike a private helper's call count. Likewise, authentication before sensitive actions or publishing events only after commit can be contractual. There is no absolute rule to “avoid all verify(mock) calls.”

~~~mermaid
flowchart TD
    A["Muốn thêm một assertion"] --> B{"Nó bảo vệ yêu cầu quan sát được?"}
    B -- "Có" --> C["Assert kết quả, state, error hoặc side effect"]
    B -- "Không rõ" --> D{"Chỉ đổi thuật toán thì assertion đổi?"}
    D -- "Có" --> E["Xem lại và diễn đạt bằng hành vi nghiệp vụ"]
    D -- "Không" --> F["Xác định yêu cầu và cấp test thích hợp"]
    C --> G["Test ca biên, ca lỗi và ca bình thường"]
    E --> G
    F --> G
~~~

## 5. Common Forms of Excessive Coupling

**Reflection to invoke private methods.** Renaming, merging, or splitting helpers breaks tests despite an intact API. Test through public APIs. If substantial logic is genuinely independent, extract it into a component with its own contract and test via that interface.

**Asserting private fields or collection structure.** For example, reflection exposes a cache field and checks that a HashMap holds 3 elements. Changing the cache to LRU breaks the test. If TTL or lookup limits matter, use a fake Clock and a call-counting adapter to verify the requirement without freezing the Map type.

**Mocking every value object.** For Money, Address, and OrderLine, real objects are usually preferable. Excessive mocking means tests mostly verify stubs the tests themselves created.

**Verifying the entire call order.** Reserve Mockito InOrder for promised ordering, such as authentication before charging or publishing only after commit. Do not verify each validate/parse/calculate/format helper when those are internal steps.

**Oversized data snapshots.** Random IDs, timestamps, debug metadata, and unspecified JSON property ordering may change. Assert important public fields; snapshot the entire structure only when that structure is itself the API contract.

**Using real clocks and randomness.** When a rule depends on time, inject java.time.Clock; for random IDs, inject Supplier<UUID> or a generator interface. Make nondeterministic inputs reproducible in tests and assert business outcomes. Do not assert how often Instant.now() is invoked in a private helper.

**Using doubles without integration tests.** Fake catalogs do not simulate timeouts, cache consistency, or schema changes. Unit tests establish application logic assuming collaborator contracts hold; integration tests establish whether real adapters actually satisfy those contracts.

## 6. Choose a Test Level for Each Responsibility

| Level | What to Establish | Test Double | Limitation |
|---|---|---|---|
| Unit | Behavior of one SUT | Substitute collaborators to control inputs | Prone to over-mocking |
| Component | Rules across collaborating classes | Selective use | Fakes may omit transaction behavior |
| Integration | Real APIs, SQL, mapping, and transactions | Fewer at the primary boundary under test | Slow and requires an environment |
| End-to-end | Final workflow from the user's perspective | Controlled environment | Expensive and unstable if too many cases are combined |

Also distinguish **public contracts** from implementation choices: an API may specify ordering, idempotency, call limits, exception types, or monetary precision. If these properties are promised, test them. Private/public modifiers alone do not determine which properties are internal details.

## 7. Checklist khi review test

1. Test names express requirements (e.g., freeShippingAppliesAtThreshold), not helpers (testCallsPriceOfTwice).
2. Arrange constructs only relevant data, stubs, and dependencies.
3. Act invokes the public API or appropriate contractual interface.
4. Assert required outcomes, state, errors, and external effects.
5. Do not force implementations to retain arbitrary call counts, helper names, collection types, or processing order.
6. Add normal, failure, boundary, and integration cases for important connections.
7. When tests fail after refactoring, determine whether **the contract changed** or the test was merely asserting internals.

## 8. Exercises and Self-Assessment

**Exercise 1:** Replace PerLineService's total-calculation loop with a Stream while retaining runContract assertions. All cases should still pass.

**Exercise 2:** Change the free-shipping condition to subtotal > 500_000. The exactly-500.000 case must FAIL: a genuine regression.

**Exercise 3:** Write verify(catalog, times(2)).priceOf("BOOK"), then switch to GroupedService. Explain why the failure is a false alarm without a lookup-count requirement.

**Exercise 4:** Add the requirement “look up each SKU at most once per quote.” Write a dedicated test; implementation A fails and B passes. Lookup count is now a contractual condition.

**Exercise 5:** Cover a missing SKU, null Line, negative quantity, and money totals exceeding long. Specify promised exception types and avoid asserting undocumented internal messages/stack traces.

**Remember:** A quality test suite permits valid refactoring while failing when promised behavior is broken. Verify **meaningful outcomes and effects**, use test doubles to isolate dependencies, and reserve interaction assertions for calls required by the specification.

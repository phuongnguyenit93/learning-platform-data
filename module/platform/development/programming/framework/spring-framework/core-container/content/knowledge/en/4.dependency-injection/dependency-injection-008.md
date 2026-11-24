# Recognizing Too Many Dependencies and Responsibilities to Split — Spring Framework Core Container

## 1. Goal: A Long Constructor Is a Signal Worth Analyzing

Constructor injection makes a class's dependencies **explicit in its signature**. Precisely for that reason, when a service has to take 6–10 collaborators, you immediately see complexity that field injection or a service locator might previously have hidden.

**Many parameters are not automatically a bug.** There is no rule in Java or Spring saying “constructors with 5 or more parameters are wrong”. Examine **which responsibilities the dependencies represent**, which business changes force edits to the class, how cohesive its methods are, and how hard it is to test.

For example, `OrderService` handles quoting, inventory reservation, payment collection, shipping scheduling, sending receipts, and auditing. A constructor taking 7 dependencies can be a symptom that the class carries multiple reasons to change. A good refactoring **splits responsibilities along clear boundaries**, rather than merely hiding seven parameters inside another object.

After this lesson, you can:

1. Spot signs of **too many dependencies**, **low cohesion**, **high coupling**, and classes with multiple reasons to change.
2. Distinguish **dependency count** from **design quality**; evaluate co-change timing, method clusters, and the service's true role.
3. Map which collaborators a class uses for each business capability to find splittable responsibility clusters.
4. Refactor `OrderService` into `QuoteService`, `PurchaseService`, `FulfillmentService`, and `OrderWorkflow` with transparent dependency structures.
5. Wire the split classes using `@Configuration`/`@Bean` and **constructor injection** in plain Spring Framework.
6. Verify with Java 17+, Maven, `javac`/`java`, and deterministic stdout.
7. Avoid anti-patterns: `ApplicationContext.getBean(...)` in business code, “God facade”, generic dependency bags, passing a giant container, and overengineering.
8. Design unit tests and smoke tests to ensure refactoring **preserves behavior** under key conditions.

**Scope:** This is a technique for **evaluating and splitting responsibilities from the signal of too many constructor dependencies** in the *Dependency Injection* chapter. No Spring Boot, database, message broker, microservices architecture, or other DI framework is needed.

## 2. Pre-Refactor Example: One Class Doing Too Much

Imagine a service executing the entire flow:

~~~java
// Pre-refactor sketch: NOT a complete Java file.
final class OrderService {
    private final PriceCatalog catalog;
    private final DiscountPolicy discount;
    private final StockGateway stock;
    private final PaymentGateway payment;
    private final ShippingGateway shipping;
    private final ReceiptSender receipts;
    private final AuditSink audit;

    OrderService(
            PriceCatalog catalog,
            DiscountPolicy discount,
            StockGateway stock,
            PaymentGateway payment,
            ShippingGateway shipping,
            ReceiptSender receipts,
            AuditSink audit) {
        this.catalog = java.util.Objects.requireNonNull(catalog);
        this.discount = java.util.Objects.requireNonNull(discount);
        this.stock = java.util.Objects.requireNonNull(stock);
        this.payment = java.util.Objects.requireNonNull(payment);
        this.shipping = java.util.Objects.requireNonNull(shipping);
        this.receipts = java.util.Objects.requireNonNull(receipts);
        this.audit = java.util.Objects.requireNonNull(audit);
    }

    // quote(...), buy(...), ship(...), notify(...), audit(...) ...
}
~~~

The block above only illustrates the **dependency list**; the `...` in the comment is not runnable business code. Such a service may contain multiple methods, each touching only a subset of the seven collaborators.

| Business Group | Corresponding Collaborators | Reasons Likely to Change |
| --- | --- | --- |
| Quoting | `PriceCatalog`, `DiscountPolicy` | Pricing rules and promotions |
| Purchasing / payment | `StockGateway`, `PaymentGateway` | Inventory and payment integration |
| Order fulfillment | `ShippingGateway`, `ReceiptSender`, `AuditSink` | Shipping, notifications, audit logs |

If `OrderService` gets modified when promotion formulas change, when switching payment providers, **and** when adding a receipt channel, those are multiple **reasons to change** living in one class. Maintainers must understand more than the part they are editing, while tests for quoting may have to supply all seven unrelated fakes.

**However:** having seven constructor parameters does not automatically mean violating the Single Responsibility Principle (SRP). A genuine orchestration adapter whose job is coordinating seven collaborators without housing their internal logic can still be reasonable, especially at the application-service boundary. Inspect actual methods and changes before concluding.

## 3. Signals More Important Than a Raw Number

### 3.1. Method Clusters Using Different Groups of Dependencies

Build a matrix:

| Method in Old Class | Catalog | Discount | Stock | Payment | Shipping | Receipt | Audit |
| --- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| `quote()` | X | X | | | | | |
| `charge()` | | | X | X | | | |
| `fulfill()` | | | | | X | X | X |
| `placeOrder()` | X | X | X | X | X | X | X |

The matrix reveals three fairly independent clusters plus an **orchestration** method calling the steps. If `placeOrder()` also implements pricing formulas, payment states, and receipt formatting directly, it becomes a “god method”. If it merely invokes cleanly separated steps, its orchestration role is easy to understand.

### 3.2. Cohesion and Coupling

- **Cohesion:** do a class's methods and data serve one clear responsibility together? A `QuoteService` handling quote calculations is typically more cohesive than a class that both calculates quotes and sends emails.
- **Coupling:** how many APIs or volatile details must the class know? A class depending on too many concrete clients gets dragged into changes across many systems.
- **Change coupling:** unrelated features or bugfixes keep modifying the same class for disconnected responsibilities. If changing a notification channel risks breaking pricing, boundaries are unclear.
- **Test friction:** unit testing a quoting rule still forces creating unused payment/stock/shipping/email mocks; that signals unnecessary coupling.
- **Difficulty stating responsibility:** if describing the class requires chaining “and… and… and…”, try writing a tighter contract.

### 3.3. Signals to Verify, Not Absolute Rules

A constructor with two dependencies can still mix two completely unrelated responsibilities. An infrastructure class like a composite engine, adapter, or orchestrator may legitimately need five collaborators for **one unified task**. Judge by **reasons to change and business relationships**, not solely line count, field count, or parameter count.

Do not split classes just to satisfy a linter rule like `max-params=4`. If splitting forces jumping through eight pass-through classes without improving clarity, that may be **overengineering**.

## 4. Mapping Responsibilities Before Touching Code

A practical workflow:

1. **Read the public API:** which operations genuinely belong to this class?
2. **List dependencies and roles:** where is each dependency used, and for what outcome?
3. **Group methods that change for the same reason:** pricing/discount, purchase/stock/payment, fulfillment/shipping/receipt/audit.
4. **Identify handoff points:** the orchestrator should only connect steps, not duplicate their algorithms.
5. **Extract one cluster first:** apply Extract Class/Extract Service; pass inputs/outputs via meaningful types like records.
6. **Write unit tests for the extracted cluster**, then add a Spring wiring test to verify bean candidates.
7. **Iterate based on evidence** until each class has a clear responsibility; stop if further splitting only creates forwarding methods.
8. **Compare behavior before vs. after**, especially payment/stock failures, side-effect ordering, and boundary conditions.

### Target Design After Refactoring

~~~mermaid
flowchart TD
    W["OrderWorkflow"] --> P["PurchaseService"]
    W --> F["FulfillmentService"]
    P --> Q["QuoteService"]
    P --> S["StockGateway"]
    P --> Pay["PaymentGateway"]
    Q --> Cat["PriceCatalog"]
    Q --> D["DiscountPolicy"]
    F --> Ship["ShippingGateway"]
    F --> R["ReceiptSender"]
    F --> A["AuditSink"]
~~~

**Read the diagram in consumer → dependency direction.** `OrderWorkflow` orchestrates two major steps. `QuoteService` only computes prices; `PurchaseService` coordinates quoting/stock/payment; `FulfillmentService` schedules shipping and records completion.

The new groups do not necessarily mean fewer total beans than the old class. The goal is **shrinking the scope of comprehension and scope of change for each component**. The dependency graph still mirrors the domain accurately instead of “hiding” a complex graph behind a vague interface.

## 5. Concrete Changes in Design

| Before | After | Benefit |
| --- | --- | --- |
| `OrderService` handles catalog and discounts directly | `QuoteService` depends on `PriceCatalog` and `DiscountPolicy` | Test quoting independently of external gateways |
| `OrderService` holds stock/payment logic | `PurchaseService` depends on `QuoteService`, `StockGateway`, `PaymentGateway` | Focuses the purchasing and charging contract |
| `OrderService` calls shipping/receipt/audit itself | `FulfillmentService` depends on the three fulfillment collaborators | Changing delivery/notification does not touch pricing formulas |
| Main method knows all seven collaborators | `OrderWorkflow` takes `PurchaseService` and `FulfillmentService` | Readable orchestration with minimal detail |
| Data passed as scattered parameters | `OrderRequest`, `Quote`, and `Purchase` records carry structured meaning | Clear contracts, fewer parameter-order mistakes |

**Be careful with payments and side effects:** splitting classes does not magically create distributed transactions. The demo reserves stock before charging, then schedules shipping. If charging fails after reserving stock, a real system needs compensation, idempotency, or transaction policies. Refactoring **must never silently reorder side effects** if the prior contract depended on ordering.

## 6. Runnable Spring Framework + Java 17+ Example

The demo project uses **Spring Framework 6.2.19** (pinned for reproducibility, not claimed as the newest), JDK 17+, and Maven. No Spring Boot, database, HTTP server, or real payment provider required. Gateways are replaced with **deterministic in-memory** implementations to observe responsibility boundaries.

~~~text
order-responsibilities-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── OrderResponsibilitiesDemo.java
~~~

### 6.1. `pom.xml` File

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>order-responsibilities-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.19</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.1</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
                <configuration>
                    <mainClass>demo.OrderResponsibilitiesDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Maven resolves transitive dependencies from `spring-context`. To run `javac` directly, you must supply the relevant Spring JARs to the compiler and launcher.

### 6.2. `src/main/java/demo/OrderResponsibilitiesDemo.java` File

~~~java
package demo;

import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public final class OrderResponsibilitiesDemo {
    private OrderResponsibilitiesDemo() {}

    public record OrderRequest(String sku, int quantity) {
        public OrderRequest {
            if (sku == null || sku.isBlank()) {
                throw new IllegalArgumentException("sku required");
            }
            if (quantity <= 0) {
                throw new IllegalArgumentException("quantity must be positive");
            }
        }
    }

    public record Quote(OrderRequest request, int totalCents) {}
    public record Purchase(OrderRequest request, int totalCents,
                           String paymentId) {}

    public interface PriceCatalog {
        int unitPrice(String sku);
    }

    public interface DiscountPolicy {
        int discountCents(int subtotal);
    }

    public interface StockGateway {
        void reserve(String sku, int quantity);
    }

    public interface PaymentGateway {
        String charge(int totalCents);
    }

    public interface ShippingGateway {
        String schedule(String sku, int quantity);
    }

    public interface ReceiptSender {
        void send(String receipt);
    }

    public interface AuditSink {
        void record(String event);
    }

    public static final class RecordingReceiptSender
            implements ReceiptSender {
        private final List<String> sent = new ArrayList<>();

        @Override
        public void send(String receipt) {
            sent.add(receipt);
        }

        public List<String> snapshot() {
            return List.copyOf(sent);
        }
    }

    public static final class RecordingAuditSink implements AuditSink {
        private final List<String> events = new ArrayList<>();

        @Override
        public void record(String event) {
            events.add(event);
        }

        public List<String> snapshot() {
            return List.copyOf(events);
        }
    }

    public static final class QuoteService {
        private final PriceCatalog catalog;
        private final DiscountPolicy discount;

        public QuoteService(PriceCatalog catalog, DiscountPolicy discount) {
            this.catalog = Objects.requireNonNull(catalog);
            this.discount = Objects.requireNonNull(discount);
        }

        public Quote quote(OrderRequest request) {
            Objects.requireNonNull(request);
            int unitPrice = catalog.unitPrice(request.sku());
            if (unitPrice <= 0) {
                throw new IllegalArgumentException("invalid unit price");
            }
            int subtotal = Math.multiplyExact(unitPrice, request.quantity());
            int reduction = discount.discountCents(subtotal);
            if (reduction < 0 || reduction > subtotal) {
                throw new IllegalArgumentException("invalid discount");
            }
            return new Quote(request, Math.subtractExact(subtotal, reduction));
        }
    }

    public static final class PurchaseService {
        private final QuoteService quotes;
        private final StockGateway stock;
        private final PaymentGateway payments;

        public PurchaseService(
                QuoteService quotes, StockGateway stock,
                PaymentGateway payments) {
            this.quotes = Objects.requireNonNull(quotes);
            this.stock = Objects.requireNonNull(stock);
            this.payments = Objects.requireNonNull(payments);
        }

        public Purchase buy(OrderRequest request) {
            Quote quote = quotes.quote(request);
            stock.reserve(request.sku(), request.quantity());
            String paymentId = payments.charge(quote.totalCents());
            return new Purchase(request, quote.totalCents(), paymentId);
        }
    }

    public static final class FulfillmentService {
        private final ShippingGateway shipping;
        private final ReceiptSender receipts;
        private final AuditSink audit;

        public FulfillmentService(
                ShippingGateway shipping, ReceiptSender receipts,
                AuditSink audit) {
            this.shipping = Objects.requireNonNull(shipping);
            this.receipts = Objects.requireNonNull(receipts);
            this.audit = Objects.requireNonNull(audit);
        }

        public String fulfill(Purchase purchase) {
            String shipmentId = shipping.schedule(
                    purchase.request().sku(), purchase.request().quantity());
            String result = "payment=" + purchase.paymentId()
                    + ",shipment=" + shipmentId
                    + ",total=" + purchase.totalCents();
            receipts.send(result);
            audit.record("fulfilled:" + purchase.request().sku());
            return result;
        }
    }

    public static final class OrderWorkflow {
        private final PurchaseService purchases;
        private final FulfillmentService fulfillment;

        public OrderWorkflow(
                PurchaseService purchases,
                FulfillmentService fulfillment) {
            this.purchases = Objects.requireNonNull(purchases);
            this.fulfillment = Objects.requireNonNull(fulfillment);
        }

        public String run(OrderRequest request) {
            Purchase purchase = purchases.buy(request);
            return fulfillment.fulfill(purchase);
        }

        public PurchaseService purchases() {
            return purchases;
        }

        public FulfillmentService fulfillment() {
            return fulfillment;
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class AppConfig {
        @Bean
        public PriceCatalog priceCatalog() {
            return sku -> {
                if (!"BOOK".equals(sku)) {
                    throw new IllegalArgumentException("unknown sku");
                }
                return 150;
            };
        }

        @Bean
        public DiscountPolicy discountPolicy() {
            return subtotal -> subtotal >= 300 ? 20 : 0;
        }

        @Bean
        public StockGateway stockGateway() {
            return (sku, quantity) -> {
                if (quantity > 5) {
                    throw new IllegalArgumentException("not enough stock");
                }
            };
        }

        @Bean
        public PaymentGateway paymentGateway() {
            return amount -> "PAY-" + amount;
        }

        @Bean
        public ShippingGateway shippingGateway() {
            return (sku, quantity) -> "SHIP-" + sku + "-" + quantity;
        }

        @Bean
        public RecordingReceiptSender receiptSender() {
            return new RecordingReceiptSender();
        }

        @Bean
        public RecordingAuditSink auditSink() {
            return new RecordingAuditSink();
        }

        @Bean
        public QuoteService quoteService(
                PriceCatalog catalog, DiscountPolicy discount) {
            return new QuoteService(catalog, discount);
        }

        @Bean
        public PurchaseService purchaseService(
                QuoteService quotes, StockGateway stock,
                PaymentGateway payments) {
            return new PurchaseService(quotes, stock, payments);
        }

        @Bean
        public FulfillmentService fulfillmentService(
                ShippingGateway shipping, ReceiptSender receipts,
                AuditSink audit) {
            return new FulfillmentService(shipping, receipts, audit);
        }

        @Bean
        public OrderWorkflow orderWorkflow(
                PurchaseService purchases, FulfillmentService fulfillment) {
            return new OrderWorkflow(purchases, fulfillment);
        }
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext(AppConfig.class)) {
            OrderWorkflow workflow = context.getBean(OrderWorkflow.class);
            QuoteService quotes = context.getBean(QuoteService.class);
            RecordingReceiptSender sent =
                    context.getBean(RecordingReceiptSender.class);
            RecordingAuditSink audit =
                    context.getBean(RecordingAuditSink.class);

            OrderRequest request = new OrderRequest("BOOK", 2);
            System.out.println("workflowWired=" +
                    (workflow.purchases() == context.getBean(PurchaseService.class)
                     && workflow.fulfillment()
                     == context.getBean(FulfillmentService.class)));
            System.out.println("quoteTotal=" +
                    quotes.quote(request).totalCents());
            System.out.println("result=" + workflow.run(request));
            System.out.println("sent=" + sent.snapshot());
            System.out.println("audit=" + audit.snapshot());
            System.out.println("workflowSingleton=" +
                    (workflow == context.getBean(OrderWorkflow.class)));
        }
    }
}
~~~

**Ensuring the demo is self-explanatory:**

- One top-level public class `OrderResponsibilitiesDemo` matches the file name; interfaces, records, services, and config live inside it as nested types.
- The records `OrderRequest` and `Quote`/`Purchase` use Java 17. `OrderRequest` validates SKU and quantity in its constructor, and `QuoteService` uses `Math.multiplyExact`/`Math.subtractExact` to avoid silent integer overflow.
- `QuoteService` receives **two collaborators** (catalog and discount) without knowing stock, payment, or shipping.
- `PurchaseService` receives **three collaborators** (quote, stock, payment) and only performs the purchase phase.
- `FulfillmentService` receives **three collaborators** (shipping, receipts, audit) without computing prices.
- `OrderWorkflow` receives **two meaningful services** and chains the two stages. It holds neither the seven low-level gateways nor any Spring API imports in business code.
- `@Bean` factory methods in `AppConfig` use **method parameters for Spring to resolve**. They do not invoke other `@Bean` methods directly under `proxyBeanMethods=false`.
- Fake gateways and the two recording adapters are container-managed; the fake payment creates ID `PAY-280`, and fake shipping creates `SHIP-BOOK-2`.
- Recording adapters use `ArrayList` because the demo runs single-threaded. If a singleton bean serves concurrent requests, design proper concurrency and lifecycle handling; `final` references do not automatically make lists thread-safe.
- The program executes the workflow once; the earlier `quotes.quote(...)` call only computes data and does **not** reserve, charge, or ship. There is no randomness, clock usage, or hash code in stdout.

### 6.3. Running with Maven and Deterministic stdout

Open a terminal in `order-responsibilities-demo`:

~~~bash
java -version
javac -version
mvn -version
mvn -q clean compile exec:java
~~~

**Exact six stdout lines printed by `main` on a successful run:**

~~~text
workflowWired=true
quoteTotal=280
result=payment=PAY-280,shipment=SHIP-BOOK-2,total=280
sent=[payment=PAY-280,shipment=SHIP-BOOK-2,total=280]
audit=[fulfilled:BOOK]
workflowSingleton=true
~~~

Explaining `quoteTotal=280`: unit price `150` × quantity `2` = `300`; `DiscountPolicy` subtracts `20` when subtotal is at least `300`, leaving `280`. `PurchaseService` passes `280` to the fake payment, then `FulfillmentService` records the receipt and audit entry.

Version commands and any Maven/Spring logs are not part of **the six program stdout lines**. The gateways here are fakes, so `PAY-280` does not indicate a real bank transaction.

### 6.4. Running Directly with `javac`/`java`

Spring APIs must be on the compile and runtime classpaths. Generate a file containing full dependencies:

~~~bash
mvn -q dependency:build-classpath -Dmdep.outputFile=classpath.txt
~~~

**Linux/macOS (bash/zsh):**

~~~bash
mkdir -p out
javac --release 17 -encoding UTF-8 \
  -cp "$(cat classpath.txt)" \
  -d out src/main/java/demo/OrderResponsibilitiesDemo.java
java -cp "out:$(cat classpath.txt)" demo.OrderResponsibilitiesDemo
~~~

**Windows PowerShell:**

~~~powershell
$deps = (Get-Content -Raw classpath.txt).Trim()
New-Item -ItemType Directory -Force out | Out-Null
javac --release 17 -encoding UTF-8 -cp "$deps" -d out src/main/java/demo/OrderResponsibilitiesDemo.java
java -cp "out;$deps" demo.OrderResponsibilitiesDemo
~~~

The classpath separator is `:` on Unix and `;` on Windows. Both ways run the same `main` method and produce the exact same six output lines. If `javac` reports missing `org.springframework...`, the first issue is classpath/dependencies rather than a constructor injection error.

## 7. Why Is the Split-Responsibility Version Better?

### 7.1. Fewer Reasons to Change per Class

Suppose a new discount type is added: typically only `DiscountPolicy` or quote logic changes, with no need to edit shipping or sender code. Changing an email template: swap the `ReceiptSender` implementation without touching `QuoteService`. Changing payment provider: swap `PaymentGateway` and test `PurchaseService`.

This relationship is far more informative than measuring constructor length:

| Change Need | Primary Focus Affected |
| --- | --- |
| Change price catalog / discount | `QuoteService` and its collaborators |
| Change reservation / charging rules | `PurchaseService` and gateways |
| Change shipping / notifications | `FulfillmentService` and adapters |
| Reorder major use-case steps | `OrderWorkflow` |

This does not mean you **never** edit multiple classes at once. A cross-cutting feature may still update both the workflow and data contracts, yet clear boundaries make changes easier to assess.

### 7.2. Lower Testing Cost

Before refactoring, testing a price calculation might require creating or mocking seven dependencies just to instantiate `OrderService`. After refactoring, unit testing `QuoteService` only needs `PriceCatalog` and `DiscountPolicy`.

~~~java
// Illustrative snippet within scope of the demo's nested types:
PriceCatalog prices = sku -> 100;
DiscountPolicy discount = subtotal -> 10;
QuoteService quotes = new QuoteService(prices, discount);

Quote q = quotes.quote(new OrderRequest("BOOK", 2));
System.out.println(q.totalCents()); // 190
~~~

This **is not a standalone Java file**; place it inside a suitable method/test. Result `190` = `100 × 2 − 10`. That test never constructs stock, payment, shipping, receipts, or audit. Tests stay fast and focused on the responsibility under test.

### 7.3. Overall Wiring Still Must Be Verified

Having more classes does not automatically make Spring configuration right. In the example, `OrderWorkflow` depends on one `PurchaseService` and one `FulfillmentService`; Spring must have matching beans for both. If `PaymentGateway` is missing, startup typically fails while creating the `PurchaseService`/`OrderWorkflow` singletons. If two `PaymentGateway` candidates exist with no single winner, Spring will fail with ambiguity.

Combine two kinds of tests:

- **Unit tests** for Quote/Purchase/Fulfillment individually, with fakes tailored to each responsibility.
- **Spring wiring/smoke tests** creating a context, verifying `OrderWorkflow` receives the right beans, and exercising a valid flow.

Do not use Java `assert` without `-ea` enabled as a substitute for mandatory checks; use executed test assertions or `if (...) throw ...`.

## 8. Ways to “Reduce Parameters” That Do Not Solve the Problem

### 8.1. Wrapping Every Dependency into One Bag

~~~java
// Illustrative anti-pattern:
record AllDependencies(
        PriceCatalog catalog, DiscountPolicy discount,
        StockGateway stock, PaymentGateway payment,
        ShippingGateway shipping, ReceiptSender receipts,
        AuditSink audit) {}

final class OrderService {
    OrderService(AllDependencies everything) {
        // Still holds and works with all 7 collaborators.
    }
}
~~~

Surface constructor parameter count drops from 7 to 1, yet the class still has access to all the old responsibilities. It does not improve cohesion and merely **hides coupling**. A valid parameter object must **group domain-cohesive data/behavior**, not bundle arbitrary services together for convenience.

### 8.2. Injecting `ApplicationContext` and Calling `getBean`

~~~java
// Illustrative anti-pattern:
final class OrderService {
    private final ApplicationContext context;

    OrderService(ApplicationContext context) {
        this.context = context;
    }

    void process() {
        PaymentGateway gateway = context.getBean(PaymentGateway.class);
        // Real dependency is hidden inside the method.
    }
}
~~~

This is a snippet lacking imports and full implementation, **not runnable code**. It turns the class into a **service locator consumer**: the constructor signature has one parameter, yet real dependencies are hidden, errors surface late, and unit tests get harder. Occasionally using context/providers makes sense in infrastructure or the composition root, not as a shortcut to slim down a business service.

### 8.3. Moving Constructor Arguments to `@Autowired` Fields

~~~java
// Illustrative anti-pattern for required collaborators:
@Autowired private PriceCatalog catalog;
@Autowired private PaymentGateway payment;
@Autowired private ShippingGateway shipping;
~~~

Those field declarations must live inside a valid class with imports; not a standalone file. Switching from constructor to field injection merely **hides** dependencies from the construction API. If a class already holds too many responsibilities, converting to field injection splits none of them.

### 8.4. Adding a Facade That Simply Forwards Everything

An `OrderFacade` with seven public methods delegating everything straight to one `OrderHelper` holding all the algorithms brings no real improvement. Move **decision ownership of each part** (pricing, payment, fulfillment) to its rightful place. An orchestration layer adds value when it expresses the **use-case flow** and coordinates steps that already own clear responsibilities.

### 8.5. Splitting Into Microservices Prematurely

SRP and constructor DI are **class/module design** concerns, not a mandate to split a system into seven independent network services. Moving payment/stock/shipping into microservices adds network failures, eventual consistency, and operational overhead without automatically fixing low cohesion in application code.

## 9. When Should You Keep a Relatively Long Constructor?

Do not optimize purely for appearances. Keeping multiple parameters is fine when:

- The collaborators genuinely serve **one cohesive goal** together, such as an adapter aggregating data from multiple backends.
- The class performs **pure, clear orchestration** without simultaneously owning independently changing details; each collaborator is an intentional step.
- Further splitting would create lots of pass-through wrappers with no new contract or better testability.
- Dependencies are mandatory parts of a single algorithm, and wrapping them in another class adds no clarity to boundaries.
- Grouped data is represented by a valid domain value object with shared invariants, rather than a bag of services.

The deciding question is not “how many parameters?” but: **Can the class's responsibility be stated in one meaningful sentence? Do its methods and dependencies move together when the business changes?**

If a constructor is long yet the class is cohesive, improve **clear naming, module grouping, composition root structure, and tests** first rather than splitting arbitrarily.

## 10. Spring DI Errors Related to Refactoring

| Symptom | Common Cause | How to Handle |
| --- | --- | --- |
| `UnsatisfiedDependencyException` | A new service needs an unregistered collaborator | Check `@Bean`/scans and constructor parameters |
| `NoSuchBeanDefinitionException` | Missing bean for an interface in the new graph | Register the adapter or configure test fakes explicitly |
| `NoUniqueBeanDefinitionException` | Two beans share a type with no selection rule | Use `@Qualifier`/`@Primary` by role; do not guess |
| `BeanCurrentlyInCreationException` | Splitting classes introduced a constructor dependency cycle | Sketch the graph, extract shared responsibility; avoid cycles |
| Context refresh succeeds, output is wrong | Logic moved incorrectly or side-effect order changed | Regression tests for business paths and auditing |
| Constructor has fewer params yet class stays complex | Switched to `ApplicationContext`, dependency bag, or field injection | Re-examine responsibilities and hidden dependencies |
| Dozens of tiny forwarding-only services | Split solely to shrink parameter counts | Merge back where contracts are genuinely cohesive |
| Quote tests must mock payment/shipping | Quoting logic was not separated from workflow | Separate pricing logic with clear inputs/outputs |
| Singleton writes shared state unsafely | Mutable fake/list or service called concurrently | Design thread-safe/stateless beans, constrain scope |
| Purchase reserved stock yet payment failed | Missing rollback/compensation strategy | Design real business semantics; do not confuse with DI refactor |
| Default constructor creates object missing dependencies | Dodging wiring errors with invalid state | Enforce required constructor and fail-fast validation |
| `javac` cannot find Spring packages | Missing Maven/JAR classpath | Fix build/classpath before diagnosing the bean graph |

**Important:** Splitting classes can **expose** circular dependencies previously masked by a service locator or mutable fields. Treat that as an opportunity to fix the dependency graph design, not a reason to revert to hiding dependencies.

## 11. Verifiable Refactoring Plan

A safe approach on a live system:

1. **Capture current behavior:** tests for pricing, discounts, stock failures, payment failures, fulfillment, and auditing.
2. **Identify invariants:** never charge invalid quantities; never send receipts before valid payment; record audit at the right stage.
3. **Extract quoting first:** `QuoteService` returns an immutable `Quote` with zero knowledge of payment/shipping. Confirm old and new quotes match.
4. **Extract purchasing:** `PurchaseService` takes `QuoteService` and purchase gateways, returning a valid `Purchase`.
5. **Extract post-purchase:** `FulfillmentService` takes `Purchase` data rather than re-invoking pricing.
6. **Keep orchestration thin:** `OrderWorkflow` only expresses step order and use-case-level coordination.
7. **Update Spring configuration:** register beans and dependencies via factory method parameters/constructors, without calling `@Bean` methods directly under `proxyBeanMethods=false`.
8. **Run unit tests, integration tests, and failure-path tests**; verify side effects and exception behavior stay intact.
9. **Measure ease of change and testing**, not merely parameter count. If purposeless pass-through layers emerge, consider merging.
10. **Document boundaries and ownership** of side effects, especially transactions, retries, idempotency, and auditing.

### Worthwhile Regression Cases

| Case | Key Expectation |
| --- | --- |
| BOOK × 2, subtotal 300 | Discount 20; total 280 |
| BOOK × 1, subtotal 150 | No discount; total 150 |
| Unsupported SKU | Quote fails; payment/fulfillment are not called |
| Quantity 0 or negative | `OrderRequest` rejects before side effects |
| Quantity exceeds simulated stock (over 5) | Stock fails; no charge |
| Fake payment throws error | No receipt/fulfillment; evaluate stock compensation in real systems |
| Shipping fails after payment | Cannot blindly retry; requires policy/idempotency/compensation |
| `QuoteService` unit test | No Payment/Stock/Shipping setup needed |
| `OrderWorkflow` wiring | Injects both services properly; context startup succeeds |

Note: this table is a **test plan**, not a claim that the console example ran every case. Only the happy path produces the six stdout lines in section 6.3.

## 12. Exercises with Answers

**Exercise 1.** A constructor has seven parameters. Does that guarantee the class violates SRP?

**Answer:** No. It is a signal to check method clusters, reasons to change, cohesion, coupling, and test friction. A clear orchestrator can legitimately coordinate multiple collaborators while holding one unified responsibility.

**Exercise 2.** Why isn't passing an `AllDependencies` object into the constructor a sufficient refactoring?

**Answer:** It reduces visible parameter count while keeping access to all seven collaborators and multiple responsibilities. It does nothing to isolate price, payment, and shipping changes from one another.

**Exercise 3.** If `QuoteService` requires mocking `PaymentGateway` in unit tests, what might be wrong?

**Answer:** Pricing logic is still unnecessarily coupled to payment, or the test is pulling in excess infrastructure. Separate pricing from charging so quote unit tests only need price catalog and discount policy.

**Exercise 4.** When should you keep `OrderWorkflow` instead of calling everything from `main`?

**Answer:** When a real use case needs guaranteed Purchase→Fulfillment ordering and multiple entry points (CLI, web, jobs) share the orchestration contract. If the app is tiny with no orchestration rules, this class may be unnecessary.

**Exercise 5.** Does splitting classes automatically solve transaction or payment failures?

**Answer:** No. Side-effect ordering, idempotency, compensation, and exception handling must be designed explicitly. Refactoring should preserve or improve the business contract, not merely rearrange class structure.

**Exercise 6.** Should you replace seven constructor parameters with `ApplicationContext` to silence a linter warning?

**Answer:** Not in a business service. Service locator hides real dependencies, delays failures, and complicates unit tests. Prefer constructor injection with clear responsibilities.

**Exercise 7.** Why is having only two collaborators in `QuoteService` helpful for testing?

**Answer:** It only needs the catalog and discount policy, so simple fakes suffice; pricing tests are decoupled from shipping, notifications, and payment, making failures easy to pinpoint.

**Exercise 8.** If you add a pointless forwarding wrapper solely to cap every constructor at 3 parameters, is the design guaranteed to be better?

**Answer:** No. That can introduce zero-value indirection. The criteria are cohesion, responsibility boundaries, ease of change/testing, and clarity of the dependency graph.

## 13. Review Checklist

- [ ] You can state each service's responsibility in one concise sentence.
- [ ] Constructors show real dependencies rather than hiding them in a service locator or injected fields.
- [ ] You do not treat an arbitrary parameter-count threshold as a standalone verdict.
- [ ] You have a method–dependency matrix and know which responsibility clusters change together.
- [ ] `QuoteService` knows nothing about payment/shipping; `FulfillmentService` does not calculate prices.
- [ ] `OrderWorkflow` coordinates meaningful stages without holding all seven low-level clients.
- [ ] Value objects/records have explicit contracts and invariants, not merely serving as a “bag” of services.
- [ ] Spring configuration injects collaborators via constructors or `@Bean` method parameters.
- [ ] Run Java 17+ with Maven/`javac`/`java` and verify the exact **six stdout lines**.
- [ ] Test missing/ambiguous beans, cycles, and business failure paths.
- [ ] Unit test small services without Spring; smoke test the context for wiring.
- [ ] Avoid adding pass-through layers that do not improve maintainability or testability.
- [ ] Side effects have clear ownership: inventory reservation, charging, shipping, receipt, auditing.
- [ ] Never declare refactoring complete solely because constructor parameter counts decreased.
- [ ] Avoid accidentally altering the ordering or invocation count of business operations.

**Conclusion:** Constructor injection does not cause “too many dependencies” — it **makes them visible**. When a class has multiple reasons to change, loosely related method clusters, and unit tests forced to build unused collaborators, split along **cohesive business responsibilities**. Do not merely hide dependencies inside a bag, context, or wrapper; improve the **dependency graph, contract clarity, and testability**.

### Official Documentation and Related Concepts

- [Spring Framework — Dependency Injection](https://docs.spring.io/spring-framework/reference/core/beans/dependencies/factory-collaborators.html)
- [Spring Framework — Java-based Container Configuration](https://docs.spring.io/spring-framework/reference/core/beans/java.html)
- [Spring Framework — Using @Bean](https://docs.spring.io/spring-framework/reference/core/beans/java/bean-annotation.html)

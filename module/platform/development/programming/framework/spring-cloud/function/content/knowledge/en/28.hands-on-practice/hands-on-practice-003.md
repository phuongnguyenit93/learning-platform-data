# Composing Order Validation and Processing Pipelines

## 1. Practice Problem

In the **Spring Cloud Function** (`SPRING_CLOUD_FUNCTION`) module, a business capability is expressed as a `Supplier`, `Function`, or `Consumer`, managed by `FunctionCatalog` so it can be reused over HTTP, event-driven systems, or serverless platforms. When business logic consists of multiple steps, instead of putting everything into one giant bean, we can **compose small functions together** (*function composition*).

The sales system in this lesson receives orders containing an order ID, customer ID, order lines, and a coupon code. We need to:

1. **Validate and normalize** input data: order ID, customer ID, SKU, quantity, unit price, and coupon.
2. **Calculate pricing:** sum each line item, apply a 10% discount for the `VIP10` coupon, and determine the payable total.
3. **Complete the order:** generate a clearly structured receipt.
4. **Record an audit log:** only when the processing chain completes successfully.

Each step takes a specific Java type and returns a specific Java type:

~~~text
JSON / message / direct call
            |
            v
       OrderRequest
            |
            v
   validateOrder (Function)
            |
            v
      ValidatedOrder
            |
            v
    priceOrder (Function)
            |
            v
       PricedOrder
            |
            v
   completeOrder (Function)
            |
            v
       OrderReceipt
          /       \
         v         v
 formatReceipt   auditReceipt
  (Function)     (Consumer)
         |         |
         v         v
    String       side effect
~~~

The main pipeline is expressed in Spring Cloud Function as:

~~~properties
spring.cloud.function.definition=validateOrder|priceOrder|completeOrder
~~~

With a lookup through `FunctionCatalog`, we can also look up the definition above directly:

~~~java
Function<OrderRequest, OrderReceipt> pipeline =
        catalog.lookup("validateOrder|priceOrder|completeOrder");
~~~

> **Core objective:** Compose three `Function` beans in exact order with compatible types. This is neither three separate HTTP requests, nor does it automatically create three topics. Spring Cloud Function presents the chain as **a single logical function** with the first step's input and the last step's output.

### Learning Outcomes

After completing this lesson, you will:

- Create a Java 17 application with fully typed generic `@Bean` definitions.
- Use `record` types for input contracts, intermediate data, and receipts.
- Test each stage independently, then test composition through `FunctionCatalog`.
- Understand execution order, validation errors, monetary overflow, and downstream short-circuiting.
- Compose `Supplier|Function` into a supplier and `Function|Consumer` into a consumer.
- Run the HTTP adapter, test composition via URL, and verify JSON output.
- Distinguish logic tests, catalog tests, and adapter tests; know how to extend to Spring Cloud Stream/serverless.

## 2. Tools and Versions

The example uses **JDK 17**, **Maven 3.9+**, **Spring Boot 3.5.0**, and **Spring Cloud 2025.0.0 (Northfields)**. According to the Spring Cloud release announcement, release train 2025.0.0 is compatible with Spring Boot 3.5.0. This version pair gives the lab a reproducible baseline; for real projects, pick supported patch releases within the same compatible branch rather than keeping initial releases.

Prerequisites:

- JDK, Maven, and an IDE with Java/Spring support.
- Port `8080` available for HTTP testing (or change the port in `application.yml`).
- `curl` or Postman for sending JSON requests.
- No Kafka, RabbitMQ, database, or cloud account required for the mandatory lab.

**Important scope limits:** The audit in this lesson writes only to memory and does not handle database transactions, real payments, inventory, customer authentication, or duplicate-order prevention. This is a **composition and validation** lab, not a production order system.

## 3. Project Structure

Create the directory `order-composition-lab`:

~~~text
order-composition-lab/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/orderlab/
    │   │   ├── OrderLabApplication.java
    │   │   ├── OrderLine.java
    │   │   ├── OrderRequest.java
    │   │   ├── ValidatedOrder.java
    │   │   ├── PricedOrder.java
    │   │   ├── OrderReceipt.java
    │   │   ├── OrderOperations.java
    │   │   ├── OrderAuditStore.java
    │   │   └── OrderFunctions.java
    │   └── resources/application.yml
    └── test/java/com/example/orderlab/
        ├── OrderOperationsTest.java
        ├── OrderFunctionCatalogTest.java
        └── OrderHttpTest.java
~~~

All Java files use package `com.example.orderlab`. Having `OrderLabApplication` in the same package lets Spring Boot scan related configuration classes and components.

## 4. Initializing Maven and Spring Cloud Function

Create `pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>order-composition-lab</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <name>order-composition-lab</name>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>org.springframework.cloud</groupId>
                <artifactId>spring-cloud-dependencies</artifactId>
                <version>2025.0.0</version>
                <type>pom</type>
                <scope>import</scope>
            </dependency>
        </dependencies>
    </dependencyManagement>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-function-web</artifactId>
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

**Dependency roles:**

| Artifact | Role |
| --- | --- |
| `spring-boot-starter-web` | Spring MVC/Tomcat and Jackson JSON for HTTP |
| `spring-cloud-function-web` | `FunctionCatalog` and web adapter exporting functional beans as endpoints |
| `spring-boot-starter-test` | JUnit Jupiter, Spring Boot Test, MockMvc |
| `spring-cloud-dependencies` | BOM managing Spring Cloud Function versions aligned with the release train |

Unit/catalog tests **do not require a broker**. If you only want to test the catalog without web support, you can remove the web dependencies and use `spring-cloud-function-context`; in this lab we keep web so we can try composition over HTTP.

## 5. Building Data Contracts for Each Stage

Separating data types clearly lets the **compiler** catch mismatched stage compositions, rather than using `Function<Object,Object>` or passing raw JSON between every step.

### 5.1. OrderLine.java — an Order Line Item

~~~java
package com.example.orderlab;

public record OrderLine(
        String sku,
        int quantity,
        long unitPriceVnd) {
}
~~~

### 5.2. OrderRequest.java — Initial Request

~~~java
package com.example.orderlab;

import java.util.List;

public record OrderRequest(
        String orderId,
        String customerId,
        List<OrderLine> lines,
        String couponCode) {
}
~~~

`couponCode` can be `null` or a blank string, meaning **no coupon is used**. Order ID, customer ID, and the list of order lines are required by lab policy; converting JSON into a record can succeed even when fields are invalid from a business standpoint, so validation must run in the next step.

### 5.3. ValidatedOrder.java — Validated Data

~~~java
package com.example.orderlab;

import java.util.List;

public record ValidatedOrder(
        String orderId,
        String customerId,
        List<OrderLine> lines,
        String couponCode) {
}
~~~

`ValidatedOrder` has a structure similar to `OrderRequest`, but expresses a **process guarantee**: only requests that have passed through `validateOrder` produce this type in the standard pipeline. It is not an absolute security boundary because Java still allows other code to call the record constructor. If strict invariants must be enforced, choose a class with a controlled constructor/factory.

### 5.4. PricedOrder.java — Pricing Result

~~~java
package com.example.orderlab;

public record PricedOrder(
        String orderId,
        String customerId,
        long subtotalVnd,
        long discountVnd,
        long payableVnd) {
}
~~~

Because the monetary values are **integer VND**, there is no floating-point error when multiplying or summing quantities and unit prices. In currency domains with decimal fractions, you need `BigDecimal`, explicit rounding rules, and explicit currency units.

### 5.5. OrderReceipt.java — Final Result

~~~java
package com.example.orderlab;

public record OrderReceipt(
        String orderId,
        String customerId,
        String status,
        long subtotalVnd,
        long discountVnd,
        long payableVnd) {
}
~~~

`status = "ACCEPTED"` in the example only means **the order is valid and has been priced**. It does not mean payment has been settled or goods have been shipped. Do not confuse business status with HTTP status codes or message broker acknowledgments.

### 5.6. Example Input JSON

~~~json
{
  "orderId": " O-101 ",
  "customerId": " C-009 ",
  "lines": [
    { "sku": " pen ", "quantity": 2, "unitPriceVnd": 300000 },
    { "sku": " notebook ", "quantity": 1, "unitPriceVnd": 150000 }
  ],
  "couponCode": " vip10 "
}
~~~

The input contains whitespace and lowercase letters to demonstrate the role of validation/normalization. Expected output after the pipeline:

~~~json
{
  "orderId": "O-101",
  "customerId": "C-009",
  "status": "ACCEPTED",
  "subtotalVnd": 750000,
  "discountVnd": 75000,
  "payableVnd": 675000
}
~~~

## 6. Writing Pure Java Business Logic per Stage

Create `OrderOperations.java`:

~~~java
package com.example.orderlab;

import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Set;

public final class OrderOperations {

    private OrderOperations() {
    }

    public static ValidatedOrder validate(OrderRequest request) {
        if (request == null) {
            throw new IllegalArgumentException("order request is required");
        }

        String orderId = requiredCode(request.orderId(), "orderId");
        String customerId = requiredCode(
                request.customerId(), "customerId");

        if (request.lines() == null || request.lines().isEmpty()) {
            throw new IllegalArgumentException(
                    "lines must contain at least one item");
        }

        List<OrderLine> safeLines = new ArrayList<>();
        Set<String> seenSkus = new HashSet<>();

        for (OrderLine line : request.lines()) {
            if (line == null) {
                throw new IllegalArgumentException(
                        "lines must not contain null");
            }

            String sku = requiredCode(line.sku(), "sku");
            if (!seenSkus.add(sku)) {
                throw new IllegalArgumentException(
                        "duplicate sku: " + sku);
            }
            if (line.quantity() <= 0) {
                throw new IllegalArgumentException(
                        "quantity must be positive");
            }
            if (line.unitPriceVnd() <= 0) {
                throw new IllegalArgumentException(
                        "unitPriceVnd must be positive");
            }
            safeLines.add(new OrderLine(
                    sku, line.quantity(), line.unitPriceVnd()));
        }

        String coupon = request.couponCode() == null
                ? ""
                : request.couponCode().trim().toUpperCase(Locale.ROOT);
        if (!coupon.isEmpty() && !coupon.equals("VIP10")) {
            throw new IllegalArgumentException(
                    "unsupported coupon code");
        }

        return new ValidatedOrder(
                orderId,
                customerId,
                List.copyOf(safeLines),
                coupon);
    }

    public static PricedOrder price(ValidatedOrder order) {
        long subtotal = 0L;
        for (OrderLine line : order.lines()) {
            long itemTotal = Math.multiplyExact(
                    line.unitPriceVnd(), line.quantity());
            subtotal = Math.addExact(subtotal, itemTotal);
        }

        // Lab policy: VIP10 gives 10% off, rounded down to whole VND.
        long discount = order.couponCode().equals("VIP10")
                ? subtotal / 10
                : 0L;
        long payable = Math.subtractExact(subtotal, discount);

        return new PricedOrder(
                order.orderId(),
                order.customerId(),
                subtotal,
                discount,
                payable);
    }

    public static OrderReceipt complete(PricedOrder priced) {
        return new OrderReceipt(
                priced.orderId(),
                priced.customerId(),
                "ACCEPTED",
                priced.subtotalVnd(),
                priced.discountVnd(),
                priced.payableVnd());
    }

    public static String format(OrderReceipt receipt) {
        return "ORDER=" + receipt.orderId()
                + ";STATUS=" + receipt.status()
                + ";PAYABLE=" + receipt.payableVnd();
    }

    private static String requiredCode(
            String value, String fieldName) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(
                    fieldName + " must not be blank");
        }
        return value.trim().toUpperCase(Locale.ROOT);
    }
}
~~~

### 6.1. Analyzing the Validation Rules

| Rule | Rejected Input | Why? |
| --- | --- | --- |
| `orderId` and `customerId` required | `null`, whitespace | Cannot identify the order or customer |
| `lines` non-empty | `null` list or zero elements | Order has no items |
| Every line has an `sku` | Blank or null SKU | Cannot identify the item |
| No duplicate SKUs after normalization | `"pen"` and `" PEN "` | Avoid double-counting the same SKU in the lab model |
| `quantity > 0` | 0 or negative numbers | Cannot order invalid quantities |
| `unitPriceVnd > 0` | 0 or negative numbers | Lab pricing policy |
| Valid coupon | Non-empty string other than `VIP10` | Avoid silently ignoring unsupported codes |
| Totals do not overflow | Product or sum exceeds `long` | Must not wrap around to wrong numbers |

These rules are **explicitly stated for the lab**, not mandatory for every sales system. For example, a unit price of 0 or duplicate SKUs may be valid in another business domain; in that case, adjust the policy and update tests accordingly.

### 6.2. Why List.copyOf and Math.*Exact?

`List.copyOf(safeLines)` creates an unmodifiable list that rejects standard `add/remove` operations, preventing downstream stages from mutating the validated dataset. `OrderLine` itself is a record, so fields on each line cannot be reassigned either.

`Math.multiplyExact`, `Math.addExact`, and `Math.subtractExact` throw `ArithmeticException` on overflow. Using standard `long` arithmetic could silently wrap around to negative or wrong totals without raising an error. In production, decide how to surface this error in responses/events and apply appropriate value bounds.

### 6.3. Responsibilities of Each Stage

- `validate`: converts untrusted `OrderRequest` into `ValidatedOrder`.
- `price`: processes only `ValidatedOrder`, without reading JSON or re-checking every field.
- `complete`: creates an `OrderReceipt` containing the result details.
- `format`: converts the receipt into a display string; does not recalculate prices.

A stage **does not need to know** whether the previous stage arrived from HTTP, a message broker, or a unit test. This is what enables reuse.

## 7. Registering Each Stage as a Spring Functional Bean

### 7.1. AuditStore.java

Create `OrderAuditStore.java`:

~~~java
package com.example.orderlab;

import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

import org.springframework.stereotype.Component;

@Component
public class OrderAuditStore {

    private final CopyOnWriteArrayList<OrderReceipt> entries =
            new CopyOnWriteArrayList<>();

    public void record(OrderReceipt receipt) {
        entries.add(receipt);
    }

    public List<OrderReceipt> snapshot() {
        return List.copyOf(entries);
    }

    public void clear() {
        entries.clear();
    }
}
~~~

This store is strictly for practice and tests; data is lost when the application restarts. `CopyOnWriteArrayList` is unsuitable for heavy write loads. Because order data can be sensitive, access control, retention policies, and durable auditing are needed in a real system.

### 7.2. OrderFunctions.java

~~~java
package com.example.orderlab;

import java.util.List;
import java.util.function.Consumer;
import java.util.function.Function;
import java.util.function.Supplier;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class OrderFunctions {

    @Bean
    public Supplier<OrderRequest> demoOrder() {
        return () -> new OrderRequest(
                " O-101 ",
                " C-009 ",
                List.of(
                        new OrderLine(" pen ", 2, 300_000L),
                        new OrderLine(" notebook ", 1, 150_000L)),
                " vip10 ");
    }

    @Bean
    public Function<OrderRequest, ValidatedOrder> validateOrder() {
        return OrderOperations::validate;
    }

    @Bean
    public Function<ValidatedOrder, PricedOrder> priceOrder() {
        return OrderOperations::price;
    }

    @Bean
    public Function<PricedOrder, OrderReceipt> completeOrder() {
        return OrderOperations::complete;
    }

    @Bean
    public Function<OrderReceipt, String> formatReceipt() {
        return OrderOperations::format;
    }

    @Bean
    public Consumer<OrderReceipt> auditReceipt(
            OrderAuditStore auditStore) {
        return auditStore::record;
    }
}
~~~

**Exact signatures determine how composition works:**

| Bean | Interface | Input Type | Output Type |
| --- | --- | --- | --- |
| `demoOrder` | `Supplier<OrderRequest>` | None | `OrderRequest` |
| `validateOrder` | `Function<OrderRequest,ValidatedOrder>` | `OrderRequest` | `ValidatedOrder` |
| `priceOrder` | `Function<ValidatedOrder,PricedOrder>` | `ValidatedOrder` | `PricedOrder` |
| `completeOrder` | `Function<PricedOrder,OrderReceipt>` | `PricedOrder` | `OrderReceipt` |
| `formatReceipt` | `Function<OrderReceipt,String>` | `OrderReceipt` | `String` |
| `auditReceipt` | `Consumer<OrderReceipt>` | `OrderReceipt` | No business payload |

The contract is expressed directly via generics, so a reader can immediately see that `validateOrder|priceOrder|completeOrder` can be chained sequentially. `FunctionCatalog` can leverage this type information to standardize invocation and handle message conversion at adapter boundaries.

### 7.3. Entry Point and Configuration

Create `OrderLabApplication.java`:

~~~java
package com.example.orderlab;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OrderLabApplication {

    public static void main(String[] args) {
        SpringApplication.run(OrderLabApplication.class, args);
    }
}
~~~

Create `src/main/resources/application.yml`:

~~~yaml
spring:
  application:
    name: order-composition-lab
  cloud:
    function:
      single-function-fallback-enabled: false

server:
  port: 8080
~~~

In this lab, **do not preset** `spring.cloud.function.definition` so we can experiment with individual functions and compositions by name via `FunctionCatalog`/HTTP. When deploying a fixed pipeline on Spring Cloud Stream, we will explicitly set `definition` in the extension section.

## 8. Spring Cloud Function Composition Rules

Spring Cloud Function lets you chain beans in order using `|` (pipe) or `,` (comma):

~~~text
validateOrder|priceOrder|completeOrder
~~~

Some examples:

| Definition | Resulting Function Type | Meaning |
| --- | --- | --- |
| `validateOrder|priceOrder` | `Function<OrderRequest,PricedOrder>` | Validate then price |
| `validateOrder|priceOrder|completeOrder` | `Function<OrderRequest,OrderReceipt>` | Full order processing chain |
| `validateOrder|priceOrder|completeOrder|formatReceipt` | `Function<OrderRequest,String>` | Return formatted receipt string |
| `demoOrder|validateOrder|priceOrder|completeOrder` | `Supplier<OrderReceipt>` | No input; pull demo order and process it |
| `validateOrder|priceOrder|completeOrder|auditReceipt` | `Consumer<OrderRequest>` | Accept order, process, and audit; return no receipt |
| `auditReceipt|completeOrder` | Invalid composition | Consumer produces no payload for the next stage |

These are **function-contract** composition rules, not content-based order routing. `a|b` means the output of `a` feeds into `b`; it does not automatically create two parallel branches or two output bindings.

### 8.1. Note on Ordering

~~~text
CORRECT:
OrderRequest -> validateOrder -> ValidatedOrder
             -> priceOrder -> PricedOrder
             -> completeOrder -> OrderReceipt

WRONG:
OrderRequest -> priceOrder
  (priceOrder requires ValidatedOrder, not OrderRequest)
~~~

Real-world steps can have side effects, so reordering them does not merely cause type errors—it can also alter business outcomes. Placing validation before pricing, inventory checks, or order persistence filters out bad data early.

### 8.2. Composition Is Not a Transaction

Composing three functions into a pipeline **does not** provide atomicity, distributed transactions, or rollback. If a later stage fails after an earlier stage wrote to a database, the framework does not automatically compensate for you. In this lab, the three main stages have no side effects; `auditReceipt` is placed **at the end** so it only records once a receipt is produced successfully.

## 9. Testing Logic Independently Before Starting Spring

Create `OrderOperationsTest.java`:

~~~java
package com.example.orderlab;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.List;

import org.junit.jupiter.api.Test;

class OrderOperationsTest {

    private OrderRequest validInput() {
        return new OrderRequest(
                " o-101 ",
                " c-009 ",
                List.of(
                        new OrderLine(" pen ", 2, 300_000L),
                        new OrderLine(" notebook ", 1, 150_000L)),
                " vip10 ");
    }

    @Test
    void validateNormalizesIdsSkusAndCoupon() {
        ValidatedOrder validated =
                OrderOperations.validate(validInput());

        assertEquals("O-101", validated.orderId());
        assertEquals("C-009", validated.customerId());
        assertEquals("PEN", validated.lines().get(0).sku());
        assertEquals("NOTEBOOK", validated.lines().get(1).sku());
        assertEquals("VIP10", validated.couponCode());
    }

    @Test
    void priceComputesSubtotalDiscountAndPayable() {
        PricedOrder priced = OrderOperations.price(
                OrderOperations.validate(validInput()));

        assertEquals(750_000L, priced.subtotalVnd());
        assertEquals(75_000L, priced.discountVnd());
        assertEquals(675_000L, priced.payableVnd());
    }

    @Test
    void completesAndFormatsReceipt() {
        PricedOrder priced = OrderOperations.price(
                OrderOperations.validate(validInput()));
        OrderReceipt receipt = OrderOperations.complete(priced);

        assertEquals("ACCEPTED", receipt.status());
        assertEquals("O-101", receipt.orderId());
        assertEquals(
                "ORDER=O-101;STATUS=ACCEPTED;PAYABLE=675000",
                OrderOperations.format(receipt));
    }

    @Test
    void rejectsInvalidInput() {
        assertThrows(IllegalArgumentException.class,
                () -> OrderOperations.validate(
                        new OrderRequest(" ", "C-1", List.of(), null)));

        assertThrows(IllegalArgumentException.class,
                () -> OrderOperations.validate(
                        new OrderRequest(
                                "O-2", "C-1",
                                List.of(new OrderLine("X", 0, 100L)),
                                null)));

        assertThrows(IllegalArgumentException.class,
                () -> OrderOperations.validate(
                        new OrderRequest(
                                "O-3", "C-1",
                                List.of(new OrderLine("X", 1, 100L)),
                                "UNKNOWN")));
    }

    @Test
    void rejectsDuplicateSkusAfterNormalization() {
        OrderRequest invalid = new OrderRequest(
                "O-4", "C-1",
                List.of(
                        new OrderLine("pen", 1, 100L),
                        new OrderLine(" PEN ", 1, 100L)),
                null);
        assertThrows(IllegalArgumentException.class,
                () -> OrderOperations.validate(invalid));
    }

    @Test
    void rejectsOverflowInsteadOfReturningWrongMoney() {
        OrderRequest big = new OrderRequest(
                "O-5", "C-1",
                List.of(new OrderLine("X", 2, Long.MAX_VALUE)),
                null);
        ValidatedOrder validated = OrderOperations.validate(big);

        assertThrows(ArithmeticException.class,
                () -> OrderOperations.price(validated));
    }

    @Test
    void createsUnmodifiableValidatedLineList() {
        ValidatedOrder validated = OrderOperations.validate(validInput());
        assertTrue(validated.lines().size() == 2);
        assertThrows(UnsupportedOperationException.class,
                () -> validated.lines().add(
                        new OrderLine("NEW", 1, 100L)));
    }
}
~~~

Unit tests only prove Java logic: input types, arithmetic, validation, and exceptions. They **do not** prove that beans are registered by Spring or that `FunctionCatalog` builds the composition properly.

### 9.1. Why Test Overflow?

If a request contains quantity `2` and unit price `Long.MAX_VALUE`, `Math.multiplyExact` throws `ArithmeticException` instead of returning a negative amount due to overflow. In a real system, you should enforce business caps prior to calculation and map errors for APIs/messages; this test proves we do not silently compute wrong totals.

### 9.2. Distinguishing Validation from Deserialization

JSON missing `lines` may be deserialized by Jackson as `null` (depending on configuration), and then rejected by `validate`. Malformed JSON syntax or fields of incompatible types may be rejected by the converter **before** the function is called. In production, separate **data parsing errors** from **business rule errors**.

## 10. Testing the Pipeline via FunctionCatalog

Create `OrderFunctionCatalogTest.java`:

~~~java
package com.example.orderlab;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.List;
import java.util.function.Consumer;
import java.util.function.Function;
import java.util.function.Supplier;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.function.context.FunctionCatalog;

@SpringBootTest(
        classes = OrderLabApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
class OrderFunctionCatalogTest {

    @Autowired
    private FunctionCatalog catalog;

    @Autowired
    private OrderAuditStore auditStore;

    private OrderRequest validInput() {
        return new OrderRequest(
                " o-101 ",
                " c-009 ",
                List.of(
                        new OrderLine(" pen ", 2, 300_000L),
                        new OrderLine(" notebook ", 1, 150_000L)),
                " vip10 ");
    }

    @BeforeEach
    void resetAudit() {
        auditStore.clear();
    }

    @Test
    void allThreeStagesAreAvailableByName() {
        Function<OrderRequest, ValidatedOrder> validate =
                catalog.lookup("validateOrder");
        Function<ValidatedOrder, PricedOrder> price =
                catalog.lookup("priceOrder");
        Function<PricedOrder, OrderReceipt> complete =
                catalog.lookup("completeOrder");

        assertNotNull(validate);
        assertNotNull(price);
        assertNotNull(complete);

        ValidatedOrder validated = validate.apply(validInput());
        PricedOrder priced = price.apply(validated);
        OrderReceipt receipt = complete.apply(priced);

        assertEquals(750_000L, priced.subtotalVnd());
        assertEquals("ACCEPTED", receipt.status());
        assertEquals(675_000L, receipt.payableVnd());
    }

    @Test
    void compositionProducesSameReceiptAsManualChain() {
        Function<OrderRequest, OrderReceipt> pipeline =
                catalog.lookup(
                        "validateOrder|priceOrder|completeOrder");

        assertNotNull(pipeline);

        OrderReceipt receipt = pipeline.apply(validInput());

        assertEquals(new OrderReceipt(
                "O-101", "C-009", "ACCEPTED",
                750_000L, 75_000L, 675_000L), receipt);
        assertTrue(auditStore.snapshot().isEmpty());
    }

    @Test
    void compositionCanAddAFormattingStage() {
        Function<OrderRequest, String> pipeline =
                catalog.lookup(
                        "validateOrder|priceOrder|completeOrder"
                        + "|formatReceipt");

        assertNotNull(pipeline);
        assertEquals(
                "ORDER=O-101;STATUS=ACCEPTED;PAYABLE=675000",
                pipeline.apply(validInput()));
    }

    @Test
    void supplierCanStartAComposition() {
        Supplier<OrderReceipt> supplier =
                catalog.lookup(
                        "demoOrder|validateOrder|priceOrder"
                        + "|completeOrder");

        assertNotNull(supplier);
        assertEquals(675_000L, supplier.get().payableVnd());
    }

    @Test
    void compositionEndingInConsumerRecordsReceipt() {
        Consumer<OrderRequest> pipeline =
                catalog.lookup(
                        "validateOrder|priceOrder|completeOrder"
                        + "|auditReceipt");

        assertNotNull(pipeline);
        pipeline.accept(validInput());

        assertEquals(1, auditStore.snapshot().size());
        assertEquals(
                675_000L,
                auditStore.snapshot().get(0).payableVnd());
    }

    @Test
    void invalidOrderStopsBeforeConsumer() {
        Consumer<OrderRequest> pipeline =
                catalog.lookup(
                        "validateOrder|priceOrder|completeOrder"
                        + "|auditReceipt");
        assertNotNull(pipeline);

        OrderRequest invalid = new OrderRequest(
                "O-BAD", "C-1",
                List.of(new OrderLine("PEN", -1, 100L)),
                null);

        assertThrows(RuntimeException.class,
                () -> pipeline.accept(invalid));
        assertTrue(auditStore.snapshot().isEmpty());
    }
}
~~~

### 10.1. Test Results

| Test | What Is Verified? |
| --- | --- |
| `allThreeStagesAreAvailableByName` | Beans are registered in the catalog and can be called independently |
| `compositionProducesSameReceiptAsManualChain` | `a|b|c` chains in order and yields the expected total |
| `compositionCanAddAFormattingStage` | `OrderReceipt` output chains into `Function<OrderReceipt,String>` |
| `supplierCanStartAComposition` | `Supplier|Function|Function|Function` produces a composite supplier |
| `compositionEndingInConsumerRecordsReceipt` | `Function|Consumer` follows the consumer contract and executes side effects |
| `invalidOrderStopsBeforeConsumer` | On validation failure, the trailing consumer is not invoked |

**What is not yet proven:** HTTP URLs being exposed, Kafka receiving messages, or a database committing transactions. These tests operate at the **Spring context and FunctionCatalog** level.

### 10.2. Why Is Testing Through FunctionCatalog Important?

~~~java
// Testing pure logic only: manual chaining.
OrderReceipt direct = OrderOperations.complete(
        OrderOperations.price(
                OrderOperations.validate(request)));

// Testing composition provided by Spring Cloud Function.
Function<OrderRequest, OrderReceipt> pipeline =
        catalog.lookup("validateOrder|priceOrder|completeOrder");
OrderReceipt composed = pipeline.apply(request);
~~~

In the second case, we verify **bean registration, lookup, wrappers, and composition ordering**. `FunctionCatalog` may return an instrumented instance, so you should not compare `pipeline.getClass()` with the raw bean class. Verify behavior and contracts instead.

### 10.3. Keeping Consumer Tests Isolated from Interference

`OrderAuditStore` is a singleton in the Spring context. `@BeforeEach` clears the store so sequential tests do not depend on execution order. If tests run **in parallel**, multiple tests can still share the store concurrently; in that case, use better test isolation, per-test mock beans, or disable parallel execution for this group.

Additionally, `FunctionCatalog` may construct composite wrappers/lambdas lazily. Therefore, look up and **invoke** the function before asserting results rather than relying solely on catalog name listings.

## 11. Configuring Composition with spring.cloud.function.definition

In the previous test, we looked up the pipeline string directly:

~~~java
catalog.lookup("validateOrder|priceOrder|completeOrder");
~~~

When an adapter such as Spring Cloud Stream needs to select a single pipeline, you can configure:

~~~yaml
spring:
  cloud:
    function:
      definition: "validateOrder|priceOrder|completeOrder"
~~~

The adapter then treats the composition chain as **one function** with:

~~~text
Input:  OrderRequest
Output: OrderReceipt
~~~

Do not confuse `spring.cloud.function.definition` with the name of a real Java bean: `validateOrder|priceOrder|completeOrder` is a **composition definition**, while `validateOrder`, `priceOrder`, and `completeOrder` are independent beans.

### 11.1. Using Commas and Pipes

`FunctionCatalog` and adapters support `a|b` or `a,b` syntax for composition in documented contexts. In YAML configuration, quoting `|` inside a string avoids confusion with YAML's block scalar indicator when whitespace is present.

In HTTP URLs, commas are often more convenient than `|` because some shells treat `|` as a pipe operator:

~~~text
/validateOrder,priceOrder,completeOrder
~~~

**Do not confuse semicolons `;` with commas**: in certain web-adapter `spring.cloud.function.definition` settings, `;` is used to **select multiple exposed functions or compositions**, not to pipe output into input.

### 11.2. FunctionCatalog Does Not Guarantee Type Safety Just Because of a Pipe

For example:

~~~text
priceOrder|validateOrder
~~~

is not a sensible pipeline because `priceOrder`'s `PricedOrder` output is incompatible with `validateOrder`'s `OrderRequest` input. Type conversion can step in for certain framework-supported cases, but you should not expect converters to magically morph arbitrary business DTOs into one another.

Precise generic signatures on every bean plus composition tests catch this mismatch before deploying an adapter.

## 12. Testing the HTTP Adapter with MockMvc

With `spring-boot-starter-web` and `spring-cloud-function-web` in `pom.xml`, the Spring Cloud Function web adapter can export functional beans as HTTP endpoints. A **POST** request to the composition runs the full chain and serializes `OrderReceipt` as JSON.

Create `OrderHttpTest.java`:

~~~java
package com.example.orderlab;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest(classes = OrderLabApplication.class)
@AutoConfigureMockMvc
class OrderHttpTest {

    @Autowired
    private MockMvc mvc;

    private static final String VALID_ORDER_JSON = """
            {
              "orderId": " O-101 ",
              "customerId": " C-009 ",
              "lines": [
                {"sku": " pen ", "quantity": 2,
                 "unitPriceVnd": 300000},
                {"sku": " notebook ", "quantity": 1,
                 "unitPriceVnd": 150000}
              ],
              "couponCode": " vip10 "
            }
            """;

    @Test
    void postExecutesFullCompositionOverHttp() throws Exception {
        mvc.perform(post(
                        "/validateOrder,priceOrder,completeOrder")
                        .contentType(MediaType.APPLICATION_JSON)
                        .accept(MediaType.APPLICATION_JSON)
                        .content(VALID_ORDER_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.orderId").value("O-101"))
                .andExpect(jsonPath("$.customerId").value("C-009"))
                .andExpect(jsonPath("$.status").value("ACCEPTED"))
                .andExpect(jsonPath("$.subtotalVnd").value(750000))
                .andExpect(jsonPath("$.discountVnd").value(75000))
                .andExpect(jsonPath("$.payableVnd").value(675000));
    }
}
~~~

**The goal of an HTTP test differs from a catalog test:**

- The URL is actually mapped to the composition by the web adapter.
- Input JSON is converted into `OrderRequest`.
- Validation and pricing execute in a single invocation.
- `OrderReceipt` is returned as JSON matching the expected schema.

Only valid data is tested here. With invalid input, an `IllegalArgumentException` thrown by the validation stage **does not automatically become a structured HTTP 400 response**. For a public API, design and test error mapping (e.g., `@ControllerAdvice` in an appropriate web layer or adapter-supported handler mechanisms).

### 12.1. Do Not Place Audit Before Validation

If you change the pipeline to place the audit consumer at the front, it will no longer have a compatible contract to continue processing because a consumer returns no output. With the pipeline ending in `auditReceipt`, auditing is only invoked **after** the receipt-creation steps succeed.

Even so, this does **not** make auditing an atomic transaction. If a real audit store fails after the order has been priced, you need retry/idempotency or transaction/outbox patterns depending on requirements.

## 13. Running the Application and Sending HTTP Requests

In `order-composition-lab`:

~~~bash
java -version
mvn -version
mvn test
mvn spring-boot:run
~~~

Once the application is running on `http://localhost:8080`, open another terminal to send requests.

### 13.1. POST a Valid Order

~~~bash
curl -i -X POST \
  "http://localhost:8080/validateOrder,priceOrder,completeOrder" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  --data-binary '{
    "orderId": " O-101 ",
    "customerId": " C-009 ",
    "lines": [
      {"sku":" pen ","quantity":2,"unitPriceVnd":300000},
      {"sku":" notebook ","quantity":1,"unitPriceVnd":150000}
    ],
    "couponCode":" vip10 "
  }'
~~~

The expected business result is an `OrderReceipt` JSON object with `payableVnd = 675000`. According to the web adapter, the HTTP status for a successful `Function` call is **200 OK**.

### 13.2. Fetching a Demo Order with a Supplier

~~~bash
curl -i "http://localhost:8080/demoOrder"
~~~

`demoOrder` is a `Supplier<OrderRequest>` returning a sample DTO. It **does not** create a database record and does not automatically publish an event to a broker. The Supplier's JSON output has not been validated/normalized, so fields may still contain whitespace as configured in the demo.

### 13.3. Trying a Composition Starting with a Supplier

~~~bash
curl -i \
  "http://localhost:8080/demoOrder,validateOrder,priceOrder,completeOrder" \
  -H "Accept: application/json"
~~~

A composition starting with a `Supplier` still requires no request payload; when the adapter supports that invocation path, the business result is a receipt for `675000` VND. If a web adapter version uses different export rules, check the `definition` configuration and test the actual endpoint.

### 13.4. Trying String Output

~~~bash
curl -i -X POST \
  "http://localhost:8080/validateOrder,priceOrder,completeOrder,formatReceipt" \
  -H "Content-Type: application/json" \
  -H "Accept: text/plain" \
  --data-binary '{
    "orderId":"O-102",
    "customerId":"C-010",
    "lines":[{"sku":"PEN","quantity":1,"unitPriceVnd":100000}],
    "couponCode":null
  }'
~~~

Expected business value:

~~~text
ORDER=O-102;STATUS=ACCEPTED;PAYABLE=100000
~~~

`Accept: text/plain` is the client's content-negotiation request; **check the response `Content-Type` header as well** rather than inferring it solely from the Java `String` return type.

### 13.5. A Rejected Order

Try submitting an order with `quantity = -1`:

~~~bash
curl -i -X POST \
  "http://localhost:8080/validateOrder,priceOrder,completeOrder" \
  -H "Content-Type: application/json" \
  --data-binary '{
    "orderId":"O-BAD",
    "customerId":"C-010",
    "lines":[{"sku":"PEN","quantity":-1,"unitPriceVnd":100000}],
    "couponCode":null
  }'
~~~

The `validateOrder` stage should reject this input with an exception. **The exact HTTP status code and error payload are not fixed in this lesson**, as they depend on the web adapter and exception handling configuration. In a production API, standardize error responses (appropriate 4xx status, business error code, correlation ID, no leaked stack traces) and test against that contract.

**Shell note:** Commands using `--data-binary '...'` and trailing `\` line continuations follow Bash/Git Bash syntax. On Windows PowerShell, use `curl.exe` with appropriate quoting or `Invoke-RestMethod`.

## 14. Moving the Pipeline into Spring Cloud Stream

Spring Cloud Stream uses `spring.cloud.function.definition` to select a function or composition chain and create **input/output bindings** with a binder (Kafka, RabbitMQ, etc.). The Maven project in this lesson does **not** yet include a Stream binder, so this section is an extension step and cannot run with the current `pom.xml` alone.

Suppose we configure:

~~~yaml
spring:
  cloud:
    function:
      definition: "validateOrder|priceOrder|completeOrder"
~~~

The pipeline still has only **one input and one output**:

~~~text
orders.received
       |
       v
   input binding
       |
       v
 validateOrder|priceOrder|completeOrder
       |
       v
   output binding
       |
       v
orders.receipts
~~~

### 14.1. Binding Names for a Composition

By Spring Cloud Stream convention, default binding names are derived from the **composite function name**, for example:

~~~text
validateOrder|priceOrder|completeOrder-in-0
validateOrder|priceOrder|completeOrder-out-0
~~~

These names are quite long. You can use `spring.cloud.stream.function.bindings` to alias them to clearer names and then configure destinations:

~~~yaml
spring:
  cloud:
    function:
      definition: "validateOrder|priceOrder|completeOrder"
    stream:
      function:
        bindings:
          "validateOrder|priceOrder|completeOrder-in-0": orderInput
          "validateOrder|priceOrder|completeOrder-out-0": orderOutput
      bindings:
        orderInput:
          destination: orders.received
          group: order-processors
          content-type: application/json
        orderOutput:
          destination: orders.receipts
          content-type: application/json
~~~

**Explanation:**

- `orderInput` and `orderOutput` are the mapped binding names.
- `orders.received` and `orders.receipts` are destinations on the binder, not bean names.
- `-in-0` and `-out-0` use index **0** because the pipeline has one input and one output.
- Even though the pipeline has three stages, it does not automatically create **three** input/output ports.

When running real messaging, you must add Spring Cloud Stream and the appropriate binder dependencies, configure the broker, and test serialization/deserialization, retries, DLQ, idempotency, and observability.

### 14.2. Error Contracts in Messaging

For imperative functions, Spring Cloud Stream can apply error handling/retries around message processing depending on the binder and configuration. If `validateOrder` throws an exception, **there is no valid `OrderReceipt`** to emit to the normal output. How the broker retries, routes to a DLQ, or ACKs the message depends on the adapter; never assume an exception automatically generates a rejection receipt or error event.

A production strategy might:

- Route **permanently invalid** inputs to a rejection event with its own schema.
- Apply bounded retries for transient errors such as downstream connectivity issues.
- Use an idempotency key such as order ID or transaction ID and guard against duplicate processing.
- Track failed record counts and measure per-stage latency.

These are architectural additions on top of messaging, not automatic behaviors of `FunctionCatalog`.

## 15. Why Not Embed Validation in a Controller?

Suppose you only implement:

~~~java
@PostMapping("/orders")
public OrderReceipt create(@RequestBody OrderRequest request) {
    // validate, price, and build receipt inside the controller...
}
~~~

This works over HTTP, but makes the logic hard to reuse when the application needs to process orders from Kafka or a Lambda event. In the lab, the same business logic lives in:

~~~java
Function<OrderRequest, ValidatedOrder>
Function<ValidatedOrder, PricedOrder>
Function<PricedOrder, OrderReceipt>
~~~

The web/controller layer is an **adapter**: it receives requests, enforces transport auth/validation, and invokes the pipeline. Spring Cloud Stream is another adapter: it receives messages, converts payloads, and calls the **same stages**. There is no need to copy pricing logic across three execution paths.

### 15.1. Do Not Treat Exceptions as Result Values

`IllegalArgumentException` from validation is an **error control flow**, not an `OrderReceipt`. In composition, an exception normally aborts invocation before the next stage runs. If the business requires producing a **structured rejection response**, you can design a result type:

~~~java
public record OrderDecisionResult(
        boolean accepted,
        OrderReceipt receipt,
        String rejectionReason) {
}
~~~

With such a type, every stage must have a clear contract for both success and failure; this can be implemented via functions operating on a result wrapper or an outer stage wrapping the pipeline. **Do not** simply return `null` instead of `ValidatedOrder` to represent rejection and expect `priceOrder` to handle null gracefully on its own.

### 15.2. Notes on Transactions, Side Effects, and Replay

Composition behaves logically like chaining `Function.andThen`; it is **not** a database transaction or distributed saga:

- If the audit succeeds but the HTTP response is lost, the client may retry.
- If the message broker redelivers an event, processing may run again.
- If a real payment step has side effects, retrying the whole pipeline could create duplicate charges.
- If checking inventory and deducting inventory are two separate operations, race conditions can occur.

In production systems, add **idempotency, transactional outbox, optimistic locking, or workflow/saga** patterns depending on the problem; do not assume Spring Cloud Function solves these automatically.

## 16. Advanced Exercises

### Exercise A — Adding a Customer Verification Stage

Write `Function<ValidatedOrder, ValidatedOrder> verifyCustomer` checking that customer IDs start with `C-`. Compose:

~~~text
validateOrder|verifyCustomer|priceOrder|completeOrder
~~~

**Criteria:** `verifyCustomer`'s output remains `ValidatedOrder`, matching `priceOrder`'s input type. Unit tests must cover both valid and invalid customers. Avoid placing blocking calls to a real database in the lab before designing dependencies and retries.

### Exercise B — Capped VIP20 Coupon

Update business rules to accept `VIP20`, offering 20% off capped at 100,000 VND:

~~~text
subtotal=750000  ->  20%=150000  ->  discount=100000
payable=650000
~~~

**Task:** Update validation, pricing, and tests including the cap-hit case. Avoid `double` for integer VND calculations; use integer arithmetic, numeric bounds, and `Math.*Exact` where appropriate.

### Exercise C — Choosing a Different Pipeline Definition

Try:

~~~text
validateOrder|priceOrder|completeOrder|formatReceipt
~~~

**Question:** What are the generic input/output types of the composite function? Does it still return `OrderReceipt`?

**Expected:** `Function<OrderRequest,String>`. The final result is the formatted receipt string. Use a catalog test to prove it; do not infer output from the initial stage.

### Exercise D — Testing That Downstream Is Not Called After an Error

Create a mock `Consumer<OrderReceipt>` with an invocation counter. Chain it after `completeOrder` and submit an invalid order:

~~~text
validateOrder|priceOrder|completeOrder|countAudit
~~~

**Task:** The counter must remain 0 after the rejected request. Use an observable object (`AtomicInteger` or a test double). Do not merely assert an exception and assume the consumer never ran.

### Exercise E — Structured Rejection Events

Instead of throwing an exception for invalid user data, design an `OrderProcessingResult` with `Accepted(receipt)` and `Rejected(reason)`. Compare the two approaches:

- **Exception:** convenient for infrastructure errors or unexpected states, but requires error mapping at each adapter.
- **Result type:** easy to represent business outcomes in JSON or events, but each stage must understand or propagate the rejected case.

**Note:** Java `sealed interface`/records can help model outcomes, though JSON polymorphism requires explicit serialization/deserialization handling across adapter boundaries.

### Exercise F — Multi-Protocol Deployment Diagram

Draw a diagram:

~~~text
HTTP ----------\
Kafka ----------> parse -> validate -> price -> complete -> adapter output
Serverless ----/
~~~

Clearly label which components depend on the transport protocol and which can be shared. Analyze how errors, authentication, and retries are handled when moving from HTTP to event-driven execution.

## 17. Common Errors and Troubleshooting

| Symptom | Possible Cause | What to Check |
| --- | --- | --- |
| `mvn test` missing dependencies | Wrong Spring Boot/Cloud BOM or Maven hasn't downloaded artifacts | Check `pom.xml` and version compatibility matrix |
| `catalog.lookup(...)` returns null | Bean not scanned, wrong name, or wrong definition | Check `@Configuration`, package, and `@Bean` names |
| `priceOrder|validateOrder` fails | Incompatible generic signatures | Check each stage's input/output table |
| Pipeline returns wrong DTO | Stages out of order or intermediate data wrong | Unit test each stage, then run catalog test |
| Unexpected negative monetary totals | Arithmetic overflow or unvalidated inputs | Use `Math.*Exact` and input bounds |
| Coupon `vip10` not applied | Missing normalization or changed rules | Inspect `validate` and `price` |
| JSON accepted despite missing `lines` | Deserialization produces null/empty or incomplete input | Test real JSON and validation |
| HTTP test returns 404 | Web adapter inactive, wrong composition URL, or filtered by `definition` | Check dependencies, logs, and mapping |
| HTTP returns 500 for invalid order | Exception not mapped to an appropriate 4xx error | Implement adapter-specific error handling |
| Duplicate records in audit | State not cleared between tests or duplicate event delivery | Isolate tests / enforce idempotency |
| Assuming composition creates three topics | Confusing stage count with binding count | Review single input / single output contract |
| Broker receives no output | Missing binder or wrong destination | Write a Stream integration test |
| Placing `Consumer` mid-chain | Consumer produces no payload | Put Consumer at the end or redesign stages |
| Latency spikes unexpectedly | Stage performs blocking IO or whole-pipeline retries | Isolate IO, set timeouts, and monitor per-stage latency |
| Sensitive order info appears in logs | Uncontrolled logging of raw payloads | Log only needed metadata; avoid storing PII indiscriminately |

### Ordered Debugging Workflow

1. Run `java -version` and `mvn -version`.
2. Run `mvn test` and fix business unit tests first.
3. Test `validate`, `price`, and `complete` individually.
4. Verify Spring creates the beans with the exact names used in the definition.
5. Test `catalog.lookup("validateOrder|priceOrder|completeOrder")`.
6. Test supplier composition and consumer side effects if used.
7. Test HTTP JSON requests against the composite endpoint.
8. Only then verify binder/serverless triggers if extending.

## 18. Lab Completion Criteria

| Criterion | Evidence |
| --- | --- |
| 3 stages separated | `validateOrder`, `priceOrder`, and `completeOrder` beans have proper generics |
| Input validation | Rejects missing IDs, empty lines, duplicate SKUs, invalid quantity/price |
| Accurate pricing | `750000 - 75000 = 675000` |
| Overflow protection | Controlled failure test for `Math.multiplyExact` |
| Composition works | `catalog.lookup("validateOrder|priceOrder|completeOrder")` returns the right receipt |
| Supplier composition | `demoOrder|...` produces `Supplier<OrderReceipt>` |
| Consumer composition | `...|auditReceipt` runs audit after successful processing |
| Stops on error | Invalid orders never reach the consumer |
| HTTP adapter | MockMvc and `curl` return expected JSON responses |
| Limitations understood | Composition does not automatically provide transactions, retries, or a binder |

**Summary:** Build each `Function` with a single responsibility and clear generics, test each stage first, and then compose them via `FunctionCatalog`. Composition gives us a unified function carrying the input/output types of the whole chain, without automatically creating transactions or delivery guarantees. When switching protocols, validation and pricing logic remain reusable, while adapters handle mapping, serialization, error handling, and infrastructure integration.

## 19. Self-Check Questions

**Question 1.** What input and output types does `validateOrder|priceOrder|completeOrder` take and return?

**Answer:** `Function<OrderRequest,OrderReceipt>`. The input type comes from the first stage, and the output type comes from the final stage.

**Question 2.** If reversed to `priceOrder|validateOrder`, why does it fail to make sense?

**Answer:** `priceOrder` takes `ValidatedOrder` and returns `PricedOrder`, whereas `validateOrder` expects `OrderRequest`. The two stages have incompatible types under the business contract.

**Question 3.** If a pipeline ends with `auditReceipt`, is the result `Function<OrderRequest,OrderReceipt>` or `Consumer<OrderRequest>`?

**Answer:** `Consumer<OrderRequest>`, because the trailing consumer produces no business output payload.

**Question 4.** Does composing `demoOrder|validateOrder|priceOrder|completeOrder` require JSON input?

**Answer:** No. The first stage is `Supplier<OrderRequest>`, which supplies the input, so the composite pipeline is a `Supplier<OrderReceipt>`.

**Question 5.** Why not just use `unitPrice * quantity` directly on `long`?

**Answer:** It can overflow and silently produce wrong results. `Math.multiplyExact` detects overflow by throwing an exception.

**Question 6.** When `validateOrder` throws `IllegalArgumentException`, is an `OrderReceipt` created?

**Answer:** Not on the happy path. The exception aborts execution before `priceOrder`/`completeOrder`. The adapter decides how to represent the failure.

**Question 7.** Does Spring Cloud Function composition automatically create three output bindings just because there are three stages?

**Answer:** No. A `Function<OrderRequest,OrderReceipt>` chain has one logical input and one logical output. Spring Cloud Stream binds the pipeline as a single composite function.

**Question 8.** Does a MockMvc test returning 200 prove the order has been paid?

**Answer:** No. The lab only validates, prices, and produces an `ACCEPTED` receipt; there is no payment gateway or database transaction.

**Question 9.** What needs to be done to process orders from Kafka instead of HTTP?

**Answer:** Add Spring Cloud Stream/the Kafka binder, configure `spring.cloud.function.definition` and bindings/destinations, and test JSON, retries, DLQ, and idempotency. You do not need to duplicate `OrderOperations` logic.

## References

- [Spring Cloud Function — Programming Model, FunctionCatalog, and Function Composition](https://docs.spring.io/spring-cloud-function/reference/4.3/spring-cloud-function/programming-model.html)
- [Spring Cloud Function — Standalone Web Applications and HTTP composition](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/standalone-web-applications.html)
- [Spring Cloud Function — Functional Bean Definitions](https://docs.spring.io/spring-cloud-function/reference/functional.html)
- [Spring Cloud Stream — Binding names and function composition](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binding-names.html)
- [Spring Cloud Stream — Functional binding names](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/functional-binding-names.html)
- [Spring Boot — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html)
- [Spring Cloud 2025.0.0 — Release announcement and Spring Boot 3.5.0 compatibility](https://spring.io/blog/2025/05/29/spring-cloud-2025-0-0-is-abvailable/)
- [Java 17 — Function, Supplier, Consumer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/function/package-summary.html)
- [Java 17 — Math.multiplyExact, addExact, subtractExact](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Math.html)

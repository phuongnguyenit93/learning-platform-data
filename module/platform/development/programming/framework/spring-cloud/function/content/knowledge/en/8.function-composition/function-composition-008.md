# Invalid Composition Orders

## 1. Why Do We Need to Know Invalid Composition Orders?

Spring Cloud Function lets you package business logic as `Supplier`, `Function`, and `Consumer` beans, then select or compose them via `FunctionCatalog`. This enables reusing logic independently of HTTP, event-driven systems, or serverless environments when an appropriate adapter is present.

However, **not every arrangement of the three function kinds forms a meaningful pipeline**. A name chain like `"parseOrder|saveOrder|formatOrder"` may look like a valid pipeline, yet it is wrong because `saveOrder` is a `Consumer`: it performs an action and **produces no output** for `formatOrder`. Likewise, placing a `Supplier` after a `Function` does not mean the `Supplier` will receive data from the `Function`.

This lesson belongs to the **Function Composition** chapter and focuses on identifying invalid orders, explaining why they fail, and fixing them with proper type contracts.

After this lesson, you will be able to:

- Read the input/output contracts of `Supplier<T>`, `Function<T, R>`, and `Consumer<T>`.
- Spot chains that place a source in the middle/end or place a `Consumer` before a step that still needs data.
- Distinguish **wrong order**, **type incompatibility**, **wrong business semantics**, and **unsupported adapter configuration**.
- Fix a pipeline by reordering steps, adding an intermediate `Function`, or combining terminal actions into a single `Consumer`.
- Test compositions via plain Java, `FunctionCatalog.lookup(...)`, and adapters as needed.

> **Scope:** Examples use Java 17, Spring Boot, and Spring Cloud Function. Direct composition support for some combinations (especially those involving `Supplier`/`Consumer`, reactive types, or `Message`) may depend on the Spring Cloud Function and adapter versions. The rules below follow from **data contracts**; for catalog name expressions, always verify on the exact version you are running.

## 2. Recalling the "Input Port" and "Output Port" of Each Function Kind

The three Java interfaces have distinct roles:

| Kind | Interface | Input port | Output port |
|---|---|---|---|
| Source | `Supplier<T>` | None | `T` |
| Transform | `Function<T, R>` | `T` | `R` |
| Sink | `Consumer<T>` | `T` | None (`void`) |

The corresponding methods invoked are:

~~~java
Supplier<String> source = () -> "42";
Function<String, Integer> parse = Integer::parseInt;
Consumer<Integer> sink = System.out::println;

String raw = source.get();         // "42"
Integer number = parse.apply(raw); // 42
sink.accept(number);               // prints 42
~~~

A sound pipeline must connect the **output port of the previous step** to the **input port of the next step**. If a step has no output port, there is no data to forward. If a step has no input port, it cannot use the result sent by the previous step.

Diagrams of common valid forms:

~~~text
Function<A,B> → Function<B,C>       ⇒ Function<A,C>

Supplier<A>   → Function<A,B>       ⇒ Supplier<B>

Function<A,B> → Consumer<B>         ⇒ Consumer<A>

Supplier<A>   → Consumer<A>         ⇒ Runnable (no input/output)

Supplier<A> → Function<A,B> → Consumer<B>
                                    ⇒ Runnable
~~~

In plain Java, the `Runnable` result can be written as `() -> sink.accept(source.get())`. With Spring Cloud Function, a name chain `"source|sink"` can represent the corresponding combination under supported composition mechanisms. Do not mistake this for an automatic task schedule: `Runnable.run()` only executes when invoked.

### 2.1. The | Symbol Means Data Chaining, Not Arbitrary Listing

When writing:

~~~java
catalog.lookup("first|second|third");
~~~

the intended order is:

~~~text
input → first → second → third → output/final action
~~~

Each name must be registered in the catalog and have a contract compatible with the next name. This order cannot be swapped arbitrarily, even if all beans exist in the Spring context.

## 3. Categorizing Reasons Why a Composition Fails

Before fixing a chain, identify how it is broken:

1. **Missing input port:** placing a `Supplier` after another step even though the `Supplier` accepts no data from the preceding step.
2. **Missing output port:** placing a `Consumer` before another `Function`/`Consumer` and expecting a `void` result to flow onward.
3. **Incompatible types:** the previous step returns `Order`, whereas the next step expects `EmailAddress`.
4. **Compatible types, wrong semantics:** both use `String`, but one produces a customer ID while the other treats it as an email.
5. **Wrong overall interface:** a pipeline starting with `Supplier` and ending with `Consumer` behaves as `Runnable`, not a `Function` taking input.
6. **Misjudging adapter capabilities:** succeeding in Java/catalog lookup does not prove an HTTP or event binder will automatically trigger and wire the pipeline.

A quick check is to write each step as `Input → Output` before deciding on the name chain.

## 4. Do Not Place a Supplier After a Function

Consider:

~~~text
normalize: Function<String, String>
generate:  Supplier<String>

"normalize|generate"  ← not a valid data-passing flow
~~~

After `normalize`, the application has a `String`. However, `generate.get()` **takes no parameters**, so it has nowhere to use that `String`.

In Java:

~~~java
import java.util.function.Function;
import java.util.function.Supplier;

Function<String, String> normalize = String::trim;
Supplier<String> generate = () -> "NEW";

// Does not compile: andThen requires a Function, not a Supplier.
// Function<String, String> bad = normalize.andThen(generate);
~~~

### 4.1. How to Fix It?

**Scenario A:** The requirement is "generate data and then normalize it." Reverse the order to source first, transform second:

~~~java
Supplier<String> generate = () -> "  NEW  ";
Function<String, String> normalize = String::trim;

Supplier<String> normalized =
        () -> normalize.apply(generate.get());

System.out.println(normalized.get()); // NEW
~~~

With beans registered in Spring Cloud Function, the expression by name is:

~~~text
generate|normalize
~~~

**Scenario B:** The requirement is "receive data from the caller and generate a new code derived from it." In that case, the second step **should not be an independent Supplier**. Write a `Function<Input, Output>` that actually uses the input:

~~~java
Function<String, String> generateId =
        normalized -> "ID-" + normalized;

Function<String, String> pipeline =
        normalize.andThen(generateId);
~~~

In Spring Cloud Function, after registering both `Function` beans, the expression is `"normalize|generateId"`.

## 5. Do Not Place a Consumer Before a Function

Consider:

~~~text
saveOrder:   Consumer<Order>
formatOrder: Function<Order, String>

"saveOrder|formatOrder"  ← invalid under output-passing model
~~~

`Consumer.accept(order)` has return type `void`. Therefore, no new `Order` is returned for `formatOrder` to use.

Corresponding Java code cannot form a `Function` chained after a `Consumer` the way `Function.andThen` works:

~~~java
Consumer<String> save = System.out::println;
Function<String, Integer> length = String::length;

// No Function-style composition exists based on save's output:
// var invalid = save.andThen(length);
~~~

`Consumer.andThen` in Java only accepts **another Consumer**, not a `Function`.

### 5.1. Reorder So the Consumer Is at the End

If the goal is "format and then save," the order is:

~~~text
formatOrder: Function<Order, String>
saveText:    Consumer<String>

"formatOrder|saveText" ⇒ Consumer<Order>
~~~

Plain Java:

~~~java
Function<String, String> normalize = String::trim;
Consumer<String> save = System.out::println;

Consumer<String> pipeline =
        raw -> save.accept(normalize.apply(raw));

pipeline.accept("  ORD-42  "); // ORD-42
~~~

Here, the final step **returns no business value**. The entire pipeline is also a `Consumer`, invoked via `accept`.

### 5.2. When You Need Both to Save and to Return a Result

Do not place a `Consumer` in the middle and try to "chain after" it. There are two design options:

- Use a `Function<Order, Receipt>` that performs the business logic and returns a meaningful `Receipt`, with side-effect responsibilities explicitly documented.
- Separate an orchestration workflow: compute the result, call the `Consumer` to persist it, and then return the result held by the workflow; do not treat that as the `Consumer` emitting an output.

Java illustration of the second option:

~~~java
Function<String, String> normalize = String::trim;
Consumer<String> audit = System.out::println;

Function<String, String> normalizeAndAudit = raw -> {
    String value = normalize.apply(raw);
    audit.accept(value);
    return value;
};
~~~

`normalizeAndAudit` returns a value **explicitly returned by the code**, not a value from `audit.accept`. When side effects are involved, clearly define error and retry behavior.

## 6. Do Not Place a Consumer Before a Supplier

A chain such as:

~~~text
writeAudit: Consumer<AuditRecord>
nextEvent:  Supplier<Event>

"writeAudit|nextEvent"
~~~

does not mean "write audit and pass the result to Supplier." The `Consumer` returns no output, and the `Supplier` takes no input. These two steps have no data connection between them.

If the goal is to run two actions sequentially without passing a value, write an explicit workflow:

~~~java
Consumer<String> audit = System.out::println;
Supplier<String> nextEvent = () -> "EVT-9";

Runnable workflow = () -> {
    audit.accept("starting");
    String event = nextEvent.get();
    System.out.println("next: " + event);
};
~~~

This is **orchestration**, not sequential `Function` composition based on output/input types. Writing such code explicitly helps readers understand exactly which actions occur and why.

## 7. Two Suppliers Do Not Compose into a Linear Pipeline

Consider:

~~~text
orders:   Supplier<Order>
payments: Supplier<Payment>

"orders|payments"
~~~

`payments` has no port to receive an `Order` from `orders`. Therefore, this notation does not represent a "fetch order then process with payment" pipeline.

### 7.1. If You Want to Combine Results from Two Sources

Model a combined source explicitly:

~~~java
import java.util.function.Supplier;

record Pair<A, B>(A left, B right) {}

Supplier<String> orderId = () -> "ORD-42";
Supplier<Long> amount = () -> 125_000L;

Supplier<Pair<String, Long>> combined = () ->
        new Pair<>(orderId.get(), amount.get());

System.out.println(combined.get());
// Pair[left=ORD-42, right=125000]
~~~

Both `Supplier` instances are **called separately** and their results are explicitly combined into a `Pair`. This is custom Java logic, not `orders|payments` under port chaining.

### 7.2. If You Want to Use the First Source's Output to Query the Second

The second step must then be a `Function`:

~~~java
Supplier<String> orderId = () -> "ORD-42";

Function<String, Long> findAmount =
        id -> id.equals("ORD-42") ? 125_000L : 0L;

Supplier<Long> amount =
        () -> findAmount.apply(orderId.get());
~~~

With Spring Cloud Function, if the two beans are named `orderId` and `findAmount`, the expression `"orderId|findAmount"` properly describes the data flow.

## 8. Two Consumers Do Not Chain by Passing Output

Suppose you have:

~~~text
save:  Consumer<Order>
audit: Consumer<Order>

"save|audit"  ← no output data from save for audit
~~~

Because `save.accept` returns `void`, `audit` cannot be treated as consuming the result of `save`. However, **Java supports `Consumer.andThen`** to call two Consumers sequentially **with the same input**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.function.Consumer;

List<String> events = new ArrayList<>();

Consumer<String> save =
        id -> events.add("SAVE:" + id);

Consumer<String> audit =
        id -> events.add("AUDIT:" + id);

Consumer<String> saveAndAudit = save.andThen(audit);
saveAndAudit.accept("ORD-42");

System.out.println(events);
// [SAVE:ORD-42, AUDIT:ORD-42]
~~~

The result remains `Consumer<String>`. Both receive `"ORD-42"`, and no value is passed from `save`'s result to `audit`.

**In Spring Cloud Function:** do not assume `FunctionCatalog.lookup("save|audit")` has the same meaning or is supported like `save.andThen(audit)` across every version. When two side effects are needed in sequence, the clear approach is to register **one composite Consumer bean** using Java's `andThen` or write dedicated orchestration.

Example:

~~~java
@Bean
public Consumer<Order> saveAndAudit(
        @Qualifier("save") Consumer<Order> save,
        @Qualifier("audit") Consumer<Order> audit) {

    return save.andThen(audit);
}
~~~

This snippet is a method in a `@Configuration` class where the `Order` type and `save`, `audit` beans are already declared; `@Qualifier` comes from `org.springframework.beans.factory.annotation.Qualifier`. Then `saveAndAudit` can be selected as the final `Consumer` step.

## 9. A Consumer in the Middle of a Pipeline Is a Red Flag

This is a common mistake when building multi-step chains:

~~~text
parseOrder|saveOrder|notifyCustomer
~~~

Suppose:

~~~text
parseOrder:      Function<String, Order>
saveOrder:       Consumer<Order>
notifyCustomer:  Function<Order, String>
~~~

After `parseOrder` comes `Order`; `saveOrder` receives it, but passes no `Order` onward. Therefore, `notifyCustomer` **receives no input from the preceding step**.

Also avoid:

~~~text
supplier|consumer|function
function|consumer|supplier
supplier|consumer|consumer
~~~

In a linear pipeline model, there is no output after a `Consumer` for a downstream step. Even if `Supplier|Consumer` forms a `Runnable`, a `Runnable` likewise has no output port to chain onward.

### 9.1. Fixing with a Single Terminal Consumer

If the business logic needs both saving and auditing, combine both actions into **one** terminal `Consumer`:

~~~text
parseOrder:     Function<String, Order>
saveAndAudit:   Consumer<Order>

"parseOrder|saveAndAudit"
               ⇒ Consumer<String>
~~~

If you also need a validation step outputting `Order`, place it **before** the `Consumer`:

~~~text
parseOrder|validateOrder|saveAndAudit
~~~

with signatures:

~~~text
parseOrder:     String → Order
validateOrder:  Order → Order
saveAndAudit:   Order → void
~~~

Do not arbitrarily turn a `Consumer` into a `Function<Order,Order>` just to have an "output," unless that function genuinely has an explicit business contract for returning the `Order` and defined behavior when the side effect fails.

## 10. Right Function-Kind Order, Wrong Intermediate Types

The order `Function → Function → Consumer` may look valid **in shape**, yet still fail if output and input types do not match.

Suppose:

~~~text
parseOrder:       Function<String, Order>
validateOrder:    Function<Order, Boolean>
saveOrder:        Consumer<Order>
~~~

The chain:

~~~text
parseOrder|validateOrder|saveOrder
~~~

has no natural chaining contract, because `validateOrder` returns `Boolean` while `saveOrder` accepts `Order`. A `Boolean` result no longer carries the `Order` data to save.

### 10.1. Fixing the Validation Result Type

If validation only aims to reject invalid data, you can define it as `Function<Order, Order>`:

~~~java
record Order(String sku, int quantity) {}

Function<Order, Order> validateOrder = order -> {
    if (!order.sku().matches("SKU-[0-9]+")
            || order.quantity() <= 0) {
        throw new IllegalArgumentException("Invalid order");
    }
    return order;
};
~~~

Then the contract:

~~~text
String → Order → Order → void
~~~

fits `parseOrder|validateOrder|saveOrder`, assuming the beans are registered under those exact names in the catalog.

Another option is to use a `ValidationResult<Order>` type, followed by a `Function` that handles the validation result and extracts the valid `Order` before saving. Never coerce `Boolean` into `Order` or silently ignore an invalid state.

### 10.2. Matching Types, Wrong Semantics

~~~text
extractCustomerId: Function<Order, String>
sendEmail:         Consumer<String>
~~~

Both use `String`, yet `sendEmail` expects an email while the data is a customer ID. The pipeline does not break on generics, but it is still **semantically wrong**.

Define explicit types when appropriate:

~~~java
record CustomerId(String value) {}
record EmailAddress(String value) {}
~~~

With `Function<Order, CustomerId>` and `Consumer<EmailAddress>`, the Java compiler can catch accidental mismatches when composing in code.

## 11. Spring Cloud Function Example: Broken Then Fixed

Build an application that receives orders formatted as `"SKU-42,2"`, then validates and saves/audits them. A common mistake is trying to chain two consecutive `Consumer` beans with `|` as if the first `Consumer` returns data to the second.

### 11.1. Defining Beans and Data Model

Using Java 17 and Spring Boot:

~~~java
package example.functions;

import java.util.List;
import java.util.Queue;
import java.util.concurrent.ConcurrentLinkedQueue;
import java.util.function.Consumer;
import java.util.function.Function;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OrderFunctions {

    public record Order(String sku, int quantity) {}

    public static final class Ledger {
        private final Queue<Order> saved =
                new ConcurrentLinkedQueue<>();
        private final Queue<Order> audited =
                new ConcurrentLinkedQueue<>();

        public void save(Order order) {
            saved.add(order);
        }

        public void audit(Order order) {
            audited.add(order);
        }

        public List<Order> savedOrders() {
            return List.copyOf(saved);
        }

        public List<Order> auditedOrders() {
            return List.copyOf(audited);
        }
    }

    @Bean
    public Ledger ledger() {
        return new Ledger();
    }

    @Bean
    public Function<String, Order> parseOrder() {
        return raw -> {
            String[] parts = raw.split(",", -1);
            if (parts.length != 2) {
                throw new IllegalArgumentException(
                        "Expected format: SKU,quantity");
            }

            String sku = parts[0].trim();
            int quantity = Integer.parseInt(parts[1].trim());
            return new Order(sku, quantity);
        };
    }

    @Bean
    public Function<Order, Order> validateOrder() {
        return order -> {
            if (!order.sku().matches("SKU-[0-9]+")
                    || order.quantity() <= 0) {
                throw new IllegalArgumentException(
                        "Invalid order");
            }
            return order;
        };
    }

    @Bean
    public Consumer<Order> saveOrder(Ledger ledger) {
        return ledger::save;
    }

    @Bean
    public Consumer<Order> auditOrder(Ledger ledger) {
        return ledger::audit;
    }

    @Bean
    public Consumer<Order> saveAndAudit(
            @Qualifier("saveOrder") Consumer<Order> save,
            @Qualifier("auditOrder") Consumer<Order> audit) {

        return save.andThen(audit);
    }
}
~~~

The function beans are registered by method name: `parseOrder`, `validateOrder`, `saveOrder`, `auditOrder`, and `saveAndAudit`. The `Ledger` bean is only a storage helper for illustration, not a `Function`/`Supplier`/`Consumer`.

### 11.2. Easily Confused Chain: Two Consecutive Consumers

~~~yaml
spring:
  cloud:
    function:
      definition: "parseOrder|saveOrder|auditOrder"
~~~

In terms of data ports, this chain has no output from `saveOrder` for `auditOrder`. Do not treat this as valid chaining of two side effects just because Java has `Consumer.andThen`.

### 11.3. Fixed Chain: Function → Function → Consumer

Change to:

~~~yaml
spring:
  cloud:
    function:
      definition: "parseOrder|validateOrder|saveAndAudit"
~~~

Contract table:

| Step | Input type | Output type |
|---|---|---|
| `parseOrder` | `String` | `Order` |
| `validateOrder` | `Order` | `Order` |
| `saveAndAudit` | `Order` | `void` |
| Overall pipeline | `String` | `void` — `Consumer<String>` |

Lookup and execution from Java:

~~~java
import java.util.function.Consumer;
import org.springframework.cloud.function.context.FunctionCatalog;

Consumer<String> pipeline =
        catalog.lookup("parseOrder|validateOrder|saveAndAudit");

if (pipeline == null) {
    throw new IllegalStateException("Order pipeline not found");
}

pipeline.accept("SKU-42,2");
~~~

When successful, the ledger records a validated order in both the saved and audited lists. This is the behavior **of an intentionally composed Consumer bean**, rather than assuming two Consumers chain via output.

### 11.4. Note on Side Effects

`saveAndAudit` invokes `save` then `audit`. If `save` succeeds and `audit` fails, already saved data does not roll back automatically. In production, you must have transaction/idempotency rules or appropriate error handling. Composition and `Consumer.andThen` do not automatically provide distributed transactions.

## 12. Invalid Expressions Involving Supplier and Runnable

A `Supplier` placed at the start of a chain can compose with `Function` steps to generate new data:

~~~text
generateOrder|validateOrder
Supplier<Order> + Function<Order,Order>
                       ⇒ Supplier<Order>
~~~

A `Supplier` composed at the end with a `Consumer` can produce `Runnable` behavior:

~~~text
generateOrder|saveOrder
Supplier<Order> + Consumer<Order>
                       ⇒ Runnable
~~~

However, do not write:

~~~text
generateOrder|saveOrder|auditOrder
~~~

expecting `auditOrder` to receive output from `saveOrder`. The contract after `saveOrder` is already **no input / no output**.

If you need to both save and audit, you can use `"generateOrder|saveAndAudit"`, where `saveAndAudit` is a composite `Consumer` as in the previous example.

Nor can you chain a `Function` directly **after a `Runnable`** via an output → input mechanism; `Runnable.run()` returns `void` and supplies no data for further transformation.

## 13. Messages, Payload Conversion, and Reactive Streams Do Not Fix Wrong Orders

### 13.1. Message<T> Differs from T

In an event-driven system, you may have steps:

~~~text
Function<Message<String>, Message<Order>>
Consumer<Message<Order>>
~~~

`Message<T>` contains a payload and headers. If the `Consumer` requires `Message<Order>` while the `Function` returns only `Order`, the two Java signatures are not identical. Spring Cloud Function or an adapter may provide conversion/wrapping in some cases, but **never use that conversion capability to justify an invalid order**.

For example, placing a `Consumer` before a `Function` still produces no output just because payloads are wrapped as `Message`. Test serialization, content-type, headers, and conversion at the adapter boundary on your actual version.

### 13.2. Reactive Types Must Consider the Entire Publisher

The signatures:

~~~text
Function<Flux<String>, Flux<Order>>
Consumer<Flux<Order>>
~~~

can connect in Java under generics because the `Function`'s return type matches what the `Consumer` accepts. However:

~~~text
Function<String, Order>
Consumer<Flux<Order>>
~~~

is not a pair with directly compatible types: `Order` differs from `Flux<Order>`. Some adapters/frameworks have context-dependent imperative/reactive adaptation, so test rather than merely reading the element type `Order` and assuming certainty.

More importantly, a reactive `Publisher` may be processed **lazily**: when the `Function` is called to create a `Flux` differs from when a subscriber actually receives elements. The `|` symbol only describes composition order; it does not guarantee elements run on one thread or that all side effects have completed when the `Publisher` is created.

### 13.3. Do Not Confuse Definition with Adapter

`spring.cloud.function.definition` selects the chain name for Spring Cloud Function/the adapter. It **does not automatically open HTTP endpoints, create input/output bindings, or trigger a Runnable**. A pipeline with valid order and types can still fail to run if starters or HTTP, event, or serverless configurations are missing.

Conversely, an adapter capable of payload conversion should not be treated as a tool that automatically fixes chains with a `Consumer` in the middle or a `Supplier` at the end.

## 14. Testing to Catch Invalid Composition Orders

### 14.1. Java Unit Test: Function Runs Before Consumer

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.ArrayList;
import java.util.List;
import java.util.function.Consumer;
import java.util.function.Function;

import org.junit.jupiter.api.Test;

class FunctionConsumerOrderTest {

    @Test
    void transformsBeforeConsuming() {
        List<String> trace = new ArrayList<>();

        Function<String, Integer> parse = raw -> {
            trace.add("parse");
            return Integer.parseInt(raw);
        };

        Consumer<Integer> save = number ->
                trace.add("save:" + number);

        Consumer<String> pipeline =
                raw -> save.accept(parse.apply(raw));

        pipeline.accept("42");

        assertEquals(List.of("parse", "save:42"), trace);
    }
}
~~~

This test verifies the data flow of a valid `Function → Consumer` composition and prevents the misconception that the `Consumer` produces a result for a later step.

### 14.2. Unit Test: If Function Fails, Consumer Does Not Run

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Consumer;
import java.util.function.Function;

import org.junit.jupiter.api.Test;

class CompositionFailureTest {

    @Test
    void failedParseStopsConsumer() {
        AtomicInteger saved = new AtomicInteger();

        Function<String, Integer> parse = Integer::parseInt;
        Consumer<Integer> sink =
                value -> saved.incrementAndGet();

        Consumer<String> pipeline =
                raw -> sink.accept(parse.apply(raw));

        assertThrows(NumberFormatException.class,
                () -> pipeline.accept("invalid"));

        assertEquals(0, saved.get());
    }
}
~~~

### 14.3. Integration Test with FunctionCatalog

A Spring Boot application with the following main class in package `example.functions`:

~~~java
package example.functions;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OrderApplication {
    public static void main(String[] args) {
        SpringApplication.run(OrderApplication.class, args);
    }
}
~~~

You can test the fixed pipeline from section 11:

~~~java
package example.functions;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

import java.util.List;
import java.util.function.Consumer;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.function.context.FunctionCatalog;

@SpringBootTest(classes = OrderApplication.class)
class CompositionCatalogTest {

    @Autowired
    FunctionCatalog catalog;

    @Autowired
    OrderFunctions.Ledger ledger;

    @Test
    void correctOrderResolvesAndRuns() {
        Consumer<String> pipeline =
                catalog.lookup(
                    "parseOrder|validateOrder|saveAndAudit");

        assertNotNull(pipeline);
        pipeline.accept("SKU-42,2");

        List<OrderFunctions.Order> expected =
                List.of(new OrderFunctions.Order("SKU-42", 2));

        assertEquals(expected, ledger.savedOrders());
        assertEquals(expected, ledger.auditedOrders());
    }
}
~~~

The test requires appropriate Spring Cloud Function and Spring Boot Test dependencies. If the context or ledger is shared across tests, isolate or reset data between test runs.

### 14.4. Should You Assert That Invalid Chains Always Return null?

**No.** Depending on the Spring Cloud Function version, an invalid expression may be rejected immediately on `lookup`, throw an exception, return `null`, or fail only upon execution. When writing negative tests, verify the behavior **of the exact version you are running**; do not hard-code an assumption that every invalid chain always returns `null`.

What a negative test must prove is that an invalid expression is not accepted as a valid business pipeline and does not cause unexpected side effects. If testing a chain that might invoke a `Consumer`, use an isolated store/spy to detect unintended actions.

## 15. Diagnostic Checklist for Invalid Composition Chains

When encountering an error in `catalog.lookup("A|B|C")` or `spring.cloud.function.definition` configuration, check in order:

| Question | What to verify |
|---|---|
| Are bean names correct? | `@Bean`, explicit names, component scan, catalog |
| Is a Supplier placed after another step? | `Supplier` has no input port |
| Is a Consumer placed before another step? | `Consumer` produces no output |
| Do intermediate types connect? | Can `Output(A)` be passed to `Input(B)`? |
| Are data semantics right? | `Order` differs from `Receipt`; ID differs from email |
| What is the overall contract? | `Function`, `Supplier`, `Consumer`, or `Runnable` |
| Does it depend on conversion? | Message/payload/reactive must be tested at runtime |
| Is a real adapter configured? | HTTP endpoint, binder, serverless handler, and config |
| If side effects exist, are retries/duplicates handled? | Idempotency, transactions, logging, errors |

Do not apply a quick fix by changing all generics to `Object` or casting to `String`. Those approaches hide bugs and make them surface late in production.

## 16. Self-Practice Exercises

**Exercise 1 — Reordering.** Given `fetch: Supplier<String>` and `normalize: Function<String,String>`, what is wrong with `normalize|fetch`? Write the valid order and determine the overall type.

**Exercise 2 — Consumer in the Middle.** Given `parse: Function<String,Order>`, `save: Consumer<Order>`, and `format: Function<Order,String>`, why is `parse|save|format` not a valid linear pipeline? Give two ways to fulfill the requirement of both saving and formatting.

**Exercise 3 — Validation Losing Data.** Given `parse: String → Order`, `check: Order → Boolean`, and `save: Consumer<Order>`, why is `parse|check|save` type-invalid? Write the signature for a new validation step that retains the valid `Order`.

**Exercise 4 — Two Consumers.** Given `audit: Consumer<Order>` and `notify: Consumer<Order>`, use `Consumer.andThen` in Java to create a composite `Consumer`, then explain how it differs from the idea of passing output from `audit` to `notify`.

**Exercise 5 — Two Suppliers.** Given `orderId: Supplier<String>` and `lookupAmount: Supplier<Long>`, why does `orderId|lookupAmount` not pass the ID to the second step? If `lookupAmount` needs to use the ID, replace it with an appropriate Java interface.

**Exercise 6 — Runnable.** What is the overall contract of `Supplier<Order>|Consumer<Order>`? State the proper method to invoke and explain why you cannot chain another `Function` after the `Consumer`.

**Exercise 7 — Adapter.** `catalog.lookup("parseOrder|saveAndAudit")` works in Java, but the messaging adapter produces no output. Is that necessarily a bug? State what to check on the binder side and the `Consumer` contract.

**Exercise 8 — Negative Test.** Write a test verifying that the input `"SKU-42,0"` is rejected by `validateOrder` and that `saveAndAudit` produces no side effects. Why shouldn't you only check whether `lookup` returns `null` for invalid chains?

### Solution Hints

- **Exercise 1:** `fetch|normalize` yields `Supplier<String>`; a `Supplier` cannot accept data from a preceding step.
- **Exercise 2:** You can format before calling an appropriate `Consumer`, or write an explicit workflow holding the `Order`/result to both save and return it.
- **Exercise 3:** `Boolean` is not `Order`; use `Function<Order,Order>` that validates and returns the `Order`, or a result model with a conversion step back to `Order`.
- **Exercise 4:** `Consumer<Order> both = audit.andThen(notify);`; both receive the same `Order`.
- **Exercise 5:** Change it to `Function<String,Long> lookupAmount` so it accepts the order ID as input.
- **Exercise 6:** `Runnable`, invoked with `run()`; `Consumer` returns `void`, so there is no value for a downstream `Function`.
- **Exercise 7:** Not necessarily; a `Consumer` produces no business output. Check the input binding, acknowledgment, and whether the adapter supports the definition.
- **Exercise 8:** Write a test invoking the valid pipeline with invalid data and using a spy/store to verify nothing was saved; failure behavior for invalid name chains depends on the framework.

## 17. Key Takeaways

- A `|` pipeline only makes sense when **the output of the previous step** can enter **the input of the next step**.
- `Supplier` has no input, so it usually belongs as a **source at the start**; `Consumer` has no output, so it usually belongs as a **sink at the end**.
- Chains like `Function|Supplier`, `Consumer|Function`, `Consumer|Supplier`, `Supplier|Supplier`, or `Function|Consumer|Function` do not describe valid output → input flows.
- Java's `Consumer.andThen` can compose **two actions with the same input**, but it does not mean the first `Consumer` returns data to the next via `|`.
- Even a valid function-kind order can still be wrong due to generics or business semantics; check **every intermediate type** and the role of each step.
- `FunctionCatalog.lookup(...)` and `spring.cloud.function.definition` do not replace runtime testing or HTTP, event, and serverless adapter configuration.
- For `Consumer` and `Runnable` flows with side effects, always explicitly design retries, error handling, and idempotency rather than expecting composition to handle them automatically.

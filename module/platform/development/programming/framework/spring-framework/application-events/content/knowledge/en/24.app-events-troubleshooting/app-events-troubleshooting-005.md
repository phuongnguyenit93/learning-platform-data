# Troubleshooting: SpEL Condition Always False in @EventListener

## 1. Symptoms and Scope of the Issue

In Spring Framework, the `@EventListener` annotation has a `condition` attribute that accepts a **Spring Expression Language (SpEL)** expression. Spring only invokes the listener method when the expression evaluates to a truthy matching value. This configuration is convenient for filtering events by state or data, yet easily leads to the situation where "the publisher sent the event, but the listener stayed completely silent".

Example:

~~~java
@EventListener(condition = "#p0.status() == 'PAID'")
public void handle(PaymentChanged event) {
    System.out.println("Payment paid: " + event.paymentId());
}
~~~

*This is an illustrative snippet inside a Spring-managed bean; `PaymentChanged` is an application-defined record or class. A complete runnable project is in section 6.*

If a `PaymentChanged` with `status = "PENDING"` is published, the listener not running is **by design**. However, if the event contains `"PAID"` and the listener still does not run, distinguish three fundamental cases:

1. **The condition genuinely evaluates to false:** the listener was found, the event type matched, the expression was evaluated, and the condition was not satisfied.
2. **The condition was never evaluated at all:** the event never reached the listener due to a type mismatch, unregistered bean/annotation, wrong `ApplicationContext`, wrong timing, or blocking by a transaction mechanism.
3. **SpEL/evaluation error:** the expression has invalid syntax, a nonexistent variable, wrong property access, or a method throws an exception. In the default synchronous flow, this error **usually throws an exception onto the publish call path**; it does not equate to a normal false result.

The goal of diagnosis is to pinpoint **the exact step that dropped the event**, rather than randomly editing the expression or disabling conditions in production.

## 2. How Does @EventListener(condition) Work?

Example configuration:

~~~java
@EventListener(condition = "#p0.total() >= 1000 and #p0.status() == 'PAID'")
public void onPayment(PaymentChanged event) {
    // Only invoked when both conditions hold.
}
~~~

Processing order from the developer's perspective:

~~~text
Publisher.publishEvent(event)
        |
        v
ApplicationEventMulticaster selects listeners by event type
        |
        +-- Type mismatch? ---> Do not invoke listener, skip evaluating condition
        |
        v
ApplicationListenerMethodAdapter resolves method arguments
        |
        +-- No matching arguments? --> Do not invoke method
        |
        v
EventExpressionEvaluator evaluates SpEL condition
        |
        +-- false --> Skip listener method
        |
        +-- true  --> Invoke listener method
        |
        +-- exception --> Enter error handling, not treated as false
~~~

For default listeners without an async executor or `@Async`, the steps above typically execute on the event-publishing thread. A listener returning a new event can also trigger downstream events, yet **if the condition is false, the method does not run and no return event is emitted**.

`condition` takes a **direct SpEL expression**; it does not require `#{...}` delimiters like template syntax used in some other configuration contexts. Simple syntax example:

~~~java
@EventListener(condition = "#p0.total() > 1000")
~~~

*This is an illustrative annotation snippet; not a standalone Java program.*

An empty condition `condition = ""` means the listener applies no SpEL filter. Spring does not automatically inspect business status unless you declare it.

## 3. Which Results Does Spring Treat as True?

According to `EventListener.condition` Javadoc, the listener is invoked when the expression evaluates to:

- Boolean `true`.
- Or a String accepted by Spring as representing true, including `"true"`, `"on"`, `"yes"`, and `"1"`.

Boolean `false` does not satisfy the condition; comparison expressions in practice should return an **explicit Boolean** rather than relying on string conversion.

Examples:

| Expression | Result | Passes filter? |
| --- | --- | --- |
| `true` | Boolean `true` | Yes |
| `false` | Boolean `false` | No |
| `1 > 0` | Boolean `true` | Yes |
| `'PAID' == 'PENDING'` | Boolean `false` | No |
| `'yes'` | String `"yes"` | Yes per annotation contract |
| `'0'` | String `"0"` | Avoid; not a documented true token |
| `#p0.total() >= 1000` | Depends on `total()` value | Only when true |

Do not assume `null`, an empty string, or an arbitrary object always equals `false` across all versions or evaluation paths: an expression returning an unexpected type can trigger conversion/evaluation errors. When writing filter conditions, write explicit comparisons that return `true` or `false`.

**Important:** if the expression is syntactically valid yet every published event has `status = "PENDING"`, always evaluating to false is natural. Diagnosis must inspect **the actual published data**, not just the annotation.

## 4. SpEL Variables Provided by Spring for Event Listeners

Spring creates a **dedicated evaluation context for events**. Key access paths to remember:

| Access path | Meaning | Example |
| --- | --- | --- |
| `#p0` | First argument of the listener method | `#p0.status() == 'PAID'` |
| `#a0` | Index-based alias for the first argument | `#a0.total() >= 1000` |
| `#root.args[0]` | Argument at index 0 in the arguments array | `#root.args[0].status() == 'PAID'` |
| `args[0]` | Accessing the args array via root object | `args[0].total() > 0` |
| `#payment` | Parameter named `payment`, **only when parameter names can be resolved** | `#payment.status() == 'PAID'` |
| `#root.event` | **Actual ApplicationEvent** passed by the multicaster | Depends on event type and wrapper |
| `event` | Alias for event on the root object | Must know which class event is |

Indexing starts at **0**. For a method `handle(PaymentChanged event)`, `#p0`, `#a0`, and `#root.args[0]` all point to **the resolved listener argument** — in this example, `PaymentChanged`.

To avoid depending on compiler metadata, **prefer `#p0` when the listener has a single event parameter**. If you want readable expressions using `#payment`, ensure the Java compiler preserves parameter name metadata—typically via `-parameters` in Maven/Gradle—and verify the exact declared name.

### 4.1. Parameter Names Missing from Bytecode

This snippet is only stable if the method genuinely has a parameter named `payment` and Spring can recognize that name:

~~~java
@EventListener(condition = "#payment.status() == 'PAID'")
public void handle(PaymentChanged payment) {
    // ...
}
~~~

If the parameter is renamed to `event` without updating the expression, or parameter name metadata is absent from the compiled class, `#payment` may fail to bind. Depending on the expression, this can cause a **SpEL error**, not necessarily false. Way to reduce risk:

~~~java
@EventListener(condition = "#p0.status() == 'PAID'")
public void handle(PaymentChanged payment) {
    // Does not depend on the variable name payment in bytecode.
}
~~~

When you want to use `#payment`, add `<parameters>true</parameters>` to `maven-compiler-plugin` or configure `-parameters` accordingly; then test on the actual deployed artifact. Do not rely on it working in your IDE while failing in the CI JAR.

### 4.2. #root.event Is Not the Same as #p0 for Payload Objects

Suppose the publisher emits a record that does not extend `ApplicationEvent`:

~~~java
context.publishEvent(new PaymentChanged("p-1", "PAID", 1500));
~~~

Spring Framework wraps that object in `PayloadApplicationEvent<PaymentChanged>`. In that case:

- `#p0`: is normally `PaymentChanged` itself, received by the method.
- `#root.event`: is the `PayloadApplicationEvent` object used by Spring for multicasting.
- `#root.event.payload`: is the original payload of `PayloadApplicationEvent`.
- `#root.event.source`: is the source of the wrapper event, **not `PaymentChanged` by default**.

Therefore:

~~~java
// Correct for a listener accepting PaymentChanged as its argument:
@EventListener(condition = "#p0.status() == 'PAID'")

// Also accessible through the wrapper when the event is a payload:
@EventListener(condition = "#root.event.payload.status() == 'PAID'")
~~~

*These are illustrative annotation snippets placed on an appropriate listener method. For a custom class extending `ApplicationEvent`, `#root.event` is that event subclass itself, so do not hardcode the `payload` rule for every event.*

Common mistake:

~~~java
// May fail on property/method lookup because root.event is the wrapper,
// not the business payload:
@EventListener(condition = "#root.event.status() == 'PAID'")
~~~

This expression **must not be assumed to be "always false"**: if the wrapper class has no `status()`, Spring may throw `SpelEvaluationException` during evaluation.

### 4.3. Do Not Confuse #root and #this

In SpEL, `#root` refers to the root object of the evaluation context, whereas `#this` can change meaning during collection selection/projection steps. For simple conditions on an event payload, `#p0` or `#root.args[0]` is usually clearer and less error-prone than relying on SpEL's implicit target object.

## 5. Reasons SpEL Filters Out Every Event

### 5.1. Case or Whitespace Mismatch

~~~java
// actual status = "paid" or "PAID " -> does not match:
@EventListener(condition = "#p0.status() == 'PAID'")
~~~

String comparison in the example requires an exact match. If the contract permits variations, normalize at the producer or perform an intentional comparison:

~~~java
@EventListener(condition =
        "#p0.status() != null and #p0.status().trim().equalsIgnoreCase('PAID')")
~~~

*This is an annotation snippet; normalization on the listener is unnecessary if the schema mandates exact status formatting at the producer.*

For money and business statuses with strict contracts, prefer validating the payload and storing an enum/canonical value; do not make every consumer patch malformed input data.

### 5.2. Actual Data Type Differs from What You Are Comparing

Suppose `status` is a Java enum `PaymentStatus.PAID`:

~~~java
public enum PaymentStatus {
    PENDING, PAID, CANCELLED
}
~~~

Writing an expression comparing an enum with a string easily causes confusion or conversion dependence. Express intent explicitly:

~~~java
@EventListener(condition = "#p0.status().name() == 'PAID'")
~~~

*The event method must return a non-null enum. If comparing directly against an enum constant in SpEL, `T(com.example.PaymentStatus).PAID` requires the exact class/namespace and compatible class loading.*

Do not assume `'PAID'`, `PaymentStatus.PAID`, and a String from JSON are always the same type. Inspect the **runtime type** and actual getter return value.

### 5.3. Numeric Thresholds and Boundary Operators

~~~java
@EventListener(condition = "#p0.total() > 1000")
~~~

When `total() == 1000`, the condition above is **false**, whereas `>= 1000` is true. Mismatches commonly occur when business rules say "1,000 or more" yet code uses `>`.

| Data | `> 1000` | `>= 1000` |
| --- | --- | --- |
| 999 | false | false |
| 1000 | false | true |
| 1001 | true | true |

Also check units: `totalMinorUnits` (smallest currency unit) differs from `totalMajorUnits`. A syntactically valid condition can still be "always false" if the producer sends 99 instead of 9,900 due to unit inconsistency.

### 5.4. Null Checks, Missing Data, or Different Field Names

Suppose event `PaymentChanged` has an optional `region`. Do not immediately call `#p0.region().equals('VN')` if `region()` can be null. Safer form:

~~~java
@EventListener(condition =
        "#p0.region() != null and #p0.region().equals('VN')")
~~~

SpEL supports conditional and safe-navigation operators; if using `?.`, still double-check the expected result when the middle segment is null. **Safe navigation does not turn missing-data conditions into true**.

Wrong property names are also common. For a standard JavaBean `getStatus()`, SpEL can access `status`. For a Java record with a `status()` method, calling `#p0.status()` explicitly avoids assumptions about getter syntax and metadata. When debugging, compare getters, actual methods, and the event type received by the listener.

### 5.5. Referencing Parameters by Name When Names Are Unavailable

~~~java
@EventListener(condition = "#payment.total() > 1000")
public void onChanged(PaymentChanged event) {}
~~~

`#payment` does not match parameter name `event`. Thus the condition cannot evaluate as expected. Switch to `#p0.total() > 1000` or fix the name + compiler metadata, then retest. Without valid binding, the expression may **throw an exception**, unlike a Boolean false comparison.

### 5.6. #root.event Path Assuming a Payload Wrapper

~~~java
@EventListener(condition = "#root.event.payload.status() == 'PAID'")
~~~

This works when the underlying event is `PayloadApplicationEvent`. However, if the publisher emits a custom `ApplicationEvent` with `getStatus()`, it **does not automatically have** a `payload` property. Choose the expression based on the actual event type, or use `#p0`/`#root.args[0]` against the listener parameter to reduce coupling to the wrapper.

### 5.7. Data Inside the Event Is Not What You Think

If the publisher builds a snapshot with `status=PENDING` and immediately updates the database to PAID right after `publishEvent(...)`, the already-published event does not mutate its status. Conversely, if using a mutable payload modified by another thread before the listener runs, the filter value may differ from publish time.

**Prefer immutable event payloads**, observe the status right before publishing, and clearly define which fact snapshot the event represents. In async listeners, never guess the event's values from database state inspected minutes later during debugging.

## 6. Runnable Java 17+ Example: Seeing True, False, and No Match

The example uses **Spring Framework 6.2.9** with Java 17+ and Maven, without Spring Boot, a database, or a web server. It registers four listeners for the `PaymentChanged` record:

- One listener **without a condition**, printing every received event to prove event type matching and listener bean registration.
- A listener receiving only `PAID` transactions with `amount >= 1000`.
- A listener receiving only `PAID` transactions with `amount < 1000`.
- A listener filtering `PENDING` via `#root.event.payload` instead of `#p0`, illustrating the difference between wrapper and payload.

Methods use `@Order` so log ordering in the **synchronous** example is deterministic. The example only illustrates event filtering and performs no real monetary transactions.

### 6.1. Structure

~~~text
spel-event-condition-demo/
├── pom.xml
└── src/main/java/EventConditionDemo.java
~~~

File `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>spel-event-condition-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.9</version>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

File `src/main/java/EventConditionDemo.java`:

~~~java
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.core.annotation.Order;

public class EventConditionDemo {

    public record PaymentChanged(
            String paymentId,
            String status,
            int amount) {
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {
        @Bean
        public Handlers handlers() {
            return new Handlers();
        }
    }

    public static class Handlers {

        @Order(0)
        @EventListener
        public void onAny(PaymentChanged event) {
            System.out.println("SEEN " + event.paymentId()
                    + " status=" + event.status()
                    + " amount=" + event.amount());
        }

        @Order(10)
        @EventListener(condition =
                "#p0.status() == 'PAID' and #p0.amount() >= 1000")
        public void onLargePaid(PaymentChanged event) {
            System.out.println("MATCH_PAID_LARGE " + event.paymentId());
        }

        @Order(20)
        @EventListener(condition =
                "#a0.status() == 'PAID' and #a0.amount() < 1000")
        public void onSmallPaid(PaymentChanged event) {
            System.out.println("MATCH_PAID_SMALL " + event.paymentId());
        }

        @Order(30)
        @EventListener(condition =
                "#root.event.payload.status() == 'PENDING'")
        public void onPending(PaymentChanged event) {
            System.out.println("MATCH_PENDING " + event.paymentId());
        }
    }

    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(Config.class)) {
            context.publishEvent(new PaymentChanged("A", "PAID", 1500));
            context.publishEvent(new PaymentChanged("B", "PAID", 500));
            context.publishEvent(new PaymentChanged("C", "PENDING", 999));
            context.publishEvent(new PaymentChanged("D", "CANCELLED", 2000));
        }
    }
}
~~~

### 6.2. Test Run

In the directory containing `pom.xml`, using JDK 17+ and Maven:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=EventConditionDemo
~~~

**Lines printed by the program itself** (excluding Maven's own output, if any):

~~~text
SEEN A status=PAID amount=1500
MATCH_PAID_LARGE A
SEEN B status=PAID amount=500
MATCH_PAID_SMALL B
SEEN C status=PENDING amount=999
MATCH_PENDING C
SEEN D status=CANCELLED amount=2000
~~~

### 6.3. Why Is This Output Correct?

1. `AnnotationConfigApplicationContext` loads beans from `Config`; the `Handlers` bean has four `@EventListener` methods.
2. `context.publishEvent(new PaymentChanged(...))` publishes a payload object that does not extend `ApplicationEvent`; Spring infrastructure wraps it in `PayloadApplicationEvent`.
3. `onAny` has no condition, so it receives all four events. `@Order(0)` places this listener ahead of methods with higher order values in the current synchronous configuration.
4. When `A: PAID/1500` is published, `#p0.status() == 'PAID'` and `#p0.amount() >= 1000` both hold: prints `MATCH_PAID_LARGE A`. Neither `< 1000` nor `PENDING` matches.
5. For `B: PAID/500`, the small-paid listener prints `MATCH_PAID_SMALL B`. Large-paid does not run because the threshold is not met.
6. For `C: PENDING/999`, both PAID conditions are false. `#root.event.payload.status()` reads the status from the `PayloadApplicationEvent` wrapper and prints `MATCH_PENDING C`.
7. For `D: CANCELLED/2000`, none of the conditions match, so **only** `SEEN D...` appears. This demonstrates proper filtering, not a broken listener.

The example does not enable `@Async`, configure a multicaster executor, or use transactions. Thus results are observed sequentially on one thread. If switched to async configuration, **do not treat the example's stdout ordering as a global guarantee**.

## 7. Ordered Diagnostic Procedure to Avoid Misguided Fixes

### Step 1: Confirm the Publisher Emitted the Right Object

At the event-publishing site, add controlled logging right before `publishEvent(...)`:

~~~java
logger.info("Publishing PaymentChanged id={} status={} amount={}",
        event.paymentId(), event.status(), event.amount());
publisher.publishEvent(event);
~~~

*Illustrative snippet requiring `logger`, `publisher`, and `event` in the corresponding service.*

Confirm both the **runtime type** and **actual values** (do not just guess from the database or UI). Do not log payloads containing sensitive data. If the publisher does not run or publishes the wrong object type, fix the source before touching SpEL.

### Step 2: Prove the Event Reaches a Properly Typed Listener

Add a temporary listener **without a condition**:

~~~java
@EventListener
public void probe(PaymentChanged event) {
    logger.info("Probe received type={} paymentId={}",
            event.getClass().getName(), event.paymentId());
}
~~~

*Integration snippet placed in a Spring bean requiring an appropriate logger.*

If the probe does **not** run: the issue may be that the bean is not Spring-managed, the event has a different type, the context is wrong, the listener registered late, the context closed, or an error occurred at the publish site. If the probe runs while the conditional listener does not: focus on the expression and data.

**Do not temporarily add a probe with side effects into production**. It should only log safe identifiers or be used in tests.

### Step 3: Temporarily Remove Condition, Then Replace with true

Try in a test environment:

~~~java
@EventListener
public void onPayment(PaymentChanged event) { /* probe */ }
~~~

Then:

~~~java
@EventListener(condition = "true")
public void onPayment(PaymentChanged event) { /* probe */ }
~~~

If both work while the real expression fails, the fault lies in **condition evaluation or the compared data**, not basic event routing.

### Step 4: Switch Named Variables to #p0

~~~java
// Depends on parameter name:
@EventListener(condition = "#payment.status() == 'PAID'")

// Independent of parameter name:
@EventListener(condition = "#p0.status() == 'PAID'")
~~~

*Both are annotation snippets; apply one at a time.*

If the second works, check compiler metadata and the method's parameter name. With Maven:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <configuration>
        <parameters>true</parameters>
    </configuration>
</plugin>
~~~

*This Maven snippet is configuration added inside `<plugins>` of a project already having the compiler plugin; it is not a full `pom.xml`. Some Maven parents/BOMs already enable `-parameters`, yet testing the deployed artifact remains important.*

### Step 5: Break the Condition into Independent Clauses

If the condition is:

~~~java
@EventListener(condition =
        "#p0.status() == 'PAID' and #p0.amount() > 1000")
~~~

Test each part individually against a concrete event:

~~~text
event.status() = "PAID"
event.amount() = 1000

#p0.status() == 'PAID'  -> true
#p0.amount() > 1000     -> false
Combined with 'and'     -> false
~~~

Check boundary values `999`, `1000`, `1001`, plus `null` or enum cases. When a long expression is always false, often **just one sub-clause never holds**.

### Step 6: Confirm the Root Type for #root.event

If the method accepts a payload record, try `#p0.status()`. When debugging `#root.event`, note that it may be `PayloadApplicationEvent`. For a custom `ApplicationEvent`, the root event is an instance of the custom subclass. Do not choose an expression based on the method parameter's class name and assume the root event is necessarily the same object.

### Step 7: Separate SpEL Errors from False

If there is a stack trace like `SpelEvaluationException` or a method-invocation error, treat it as an **expression or data error**, not a false filter. When the listener runs on an executor or `@Async`, exceptions may be logged on another thread rather than returning to the caller like a synchronous call. Check logging and the appropriate `ErrorHandler`/`AsyncUncaughtExceptionHandler`.

### Step 8: Check Gates Outside SpEL

If the listener still does not appear, check event type, bean registration, context, lifecycle, transaction phase, and async execution conditions. In particular, `@TransactionalEventListener` does not run outside a matching transaction by default when `fallbackExecution=false`, **even when the condition expression is true**.

### Step 9: Write Regression Tests for Both True and False Values

Do not only test "one PAID event is processed". Verify PENDING events, boundary amounts, enums/nulls where supported, and unrelated event types. Tests should publish events through a real Spring context to verify both the expression context and bean registration.

## 8. Debugging SpEL Outside @EventListener: Useful but Limited

You can use `SpelExpressionParser` in tests to see how a comparison behaves. Example creating an evaluation context with variable `p0`:

~~~java
var parser = new SpelExpressionParser();
var context = new StandardEvaluationContext();
context.setVariable("p0",
        new PaymentChanged("A", "PAID", 1500));

Boolean match = parser.parseExpression(
        "#p0.status() == 'PAID' and #p0.amount() >= 1000")
        .getValue(context, Boolean.class);

System.out.println(match); // true
~~~

*This is an illustrative integration snippet: requires importing `org.springframework.expression.spel.standard.SpelExpressionParser`, `org.springframework.expression.spel.support.StandardEvaluationContext`, and the `PaymentChanged` record. It is not a standalone Java file; the runnable example in section 6 uses the listener infrastructure itself to verify.*

This tests **the value and syntax of the chosen expression**, yet **does not recreate the full `@EventListener`-specific evaluation context**: root object, `#root.event`, parameter name variables, type resolution, and Spring context infrastructure may differ. Therefore the most important test remains **publishing through a real `ApplicationContext`**.

If the expression invokes beans, property accessors, or complex helpers, results in a manually constructed `StandardEvaluationContext` may differ from when Spring processes the annotation. Do not use a pure SpEL unit test result to conclude the listener is properly registered.

## 9. Not Every Issue Is SpEL: Cases That Look Like "Always False"

| Symptom | Possible cause | How to distinguish |
| --- | --- | --- |
| Publisher logs emission, all `@EventListener` methods stay silent | Wrong context, unmanaged bean, or different event type | Add conditionless probe, check type/context |
| Conditionless probe runs, conditional listener stays silent | Data mismatch, condition false, or SpEL error | Temporarily set `condition="true"`, simplify expression |
| Exception occurs at publish time | Parse/evaluation error or listener body error (sync) | Read stack trace instead of assuming false |
| Fails only when packaged as JAR, works in IDE | `-parameters` metadata or different build config | Switch to `#p0`, inspect bytecode/build |
| `@TransactionalEventListener` does not run in non-transactional code | Default no fallback outside transaction | Test inside proper transaction or review `fallbackExecution` |
| `@Async` method shows no logs and caller sees no error | Exception on worker or misconfigured executor | Check `@EnableAsync`, executor, async error handler |
| Event published before listener bean was registered | Listeners do not receive historical events | Register at the right time or use bootstrap listener |
| Method expects a different type than the actual payload | Spring does not route the event to the method | Check method parameter/event type/generics |
| DB data became PAID yet filter still sees false | Event snapshot carries the old status | Log values right at `publishEvent` |
| Same `@EventListener` runs in one environment but not another | Bean excluded by profile/conditional config | Check bean registration and activation config |

### 9.1. @TransactionalEventListener and fallbackExecution

~~~java
@TransactionalEventListener(
        phase = TransactionPhase.AFTER_COMMIT,
        condition = "#p0.status() == 'PAID'")
public void afterCommit(PaymentChanged event) {
    // Runs only when transaction condition and filter both match.
}
~~~

*Integration snippet requiring imports for `@TransactionalEventListener` and `TransactionPhase` along with an appropriate transaction manager/transaction.*

If an event is published **without a transaction** while `fallbackExecution` remains at its default `false`, the listener will not execute. This happens **even when the business status is PAID**; the cause is not necessarily the expression returning false.

Enabling `fallbackExecution=true` allows the listener to run without a transaction, but alters semantics: execution is no longer bound to `AFTER_COMMIT` of an originating transaction in non-transactional calls. Use it only when that is genuinely the intended design.

### 9.2. Do Not Confuse @ConditionalOnProperty with @EventListener(condition)

In Spring Boot, `@ConditionalOnProperty` decides **whether a bean/configuration definition is registered** based on the environment, typically at startup. `@EventListener(condition=...)` filters **each event at delivery time** using SpEL.

If the bean containing the listener was never created due to profile/conditional configuration, the `@EventListener` expression never gets a chance to be evaluated. Fix the problem at the proper layer.

### 9.3. Events Published Too Early

An `@EventListener` on a regular bean cannot listen for Spring Boot events occurring **before the ApplicationContext is created and listener methods are registered** (such as `ApplicationStartingEvent` and `ApplicationEnvironmentPreparedEvent`). Register an early listener via `SpringApplication.addListeners(...)` or another bootstrap mechanism if genuinely needed. Using `condition="true"` will not fix a late-registered listener.

## 10. SpEL Edge Cases and Reliable Condition Design

### 10.1. Do Not Turn condition into a Complex Business Engine

`@EventListener(condition=...)` fits short, clear filters:

~~~java
@EventListener(condition = "#p0.status() == 'PAID'")
~~~

If you need database queries, network API calls, dynamic authorization, or too many combined rules, put that logic inside the listener method or an independently tested service. SpEL can invoke methods/beans, but overusing it makes debugging harder, adds per-event overhead, and obscures side effects.

A condition used for security **does not replace** authorization checks in the service/domain layer. Enforce access control in the appropriate place rather than relying on an annotation filter to block other call paths.

### 10.2. Condition Is Not a Payload Validation Tool

If `PaymentChanged` requires `status` to be one of `PAID`, `PENDING`, `CANCELLED`, validate at the event creation boundary. Do not rely on a false condition to silently drop events with invalid status values.

Distinguish:

- **Events not matching filter rules**: skipping is valid behavior.
- **Events violating contract**: need warning metrics/logs or error handling, not silent ignoring by default.
- **Events needing retries**: require dedicated retry/durable delivery mechanisms when business rules demand it.

### 10.3. Avoid Dynamic Expressions from Untrusted Sources

The `condition` annotation attribute is a static expression in application code. Do not concatenate user input strings and parse/execute arbitrary SpEL for "flexible conditions": SpEL's method/type/bean access capabilities can pose severe security risks if expressions are externally controlled.

If user-configurable filtering rules are needed, build a tightly bounded DSL/checker function or a properly sandboxed expression evaluator — never expose full SpEL as an unrestricted execution language.

### 10.4. Enums, Nulls, and String Contracts

The `status` field in the runnable example uses a String to illustrate case mismatch. In real business code, enums or validated value types usually catch bad data earlier.

Consider null-safety: `#p0.status() != null and #p0.status().equals('PAID')`; SpEL's `and` operator short-circuits so the `equals` call does not run when status is null. If the event guarantees a non-null status by contract, simplify the filter and enforce the invariant in the constructor/validator.

### 10.5. Expression Evaluation Overhead

SpEL expressions are processed by the framework for matching event listeners. Under high throughput, avoid filters doing heavy work, I/O, or excessive object allocation. Measure latency/CPU at high event volumes and consider splitting events by explicit type (e.g., `PaymentCaptured` instead of one `PaymentChanged` with dozens of conditions) when the domain model permits.

### 10.6. Useful Logging That Protects Sensitive Data

In diagnostic logs, record at minimum the event type, eventId/correlationId (when available), normalized status, threshold, and outcome. Avoid dumping entire payloads containing PII/secrets. If the listener is async, logs may appear after publish logs and on a different thread; ensure proper context/trace propagation, and do not equate a missing trace ID with the listener not running.

## 11. Minimal Regression Testing Plan

Use the same Spring context setup as section 6 and test these cases:

| Event data | Condition `PAID and amount>=1000` | Outcome |
| --- | --- | --- |
| `PAID, 1500` | true | LargePaid runs |
| `PAID, 1000` | true | LargePaid runs (equal boundary) |
| `PAID, 999` | false | LargePaid does not run |
| `PENDING, 5000` | false | LargePaid does not run |
| `CANCELLED, 5000` | false | LargePaid does not run |
| `paid, 1500` | false without case normalization | LargePaid not called |
| `PAID, -1` | false | Condition false; producer should still block contract-invalid payloads |

For methods with complex conditions, test **positive, negative, boundary, null, wrong-type, and invalid-expression** cases. Verify both listener bean registration and actual event publication.

Testing steps can include:

1. Create a real `AnnotationConfigApplicationContext`.
2. Register the bean containing `@EventListener` and a thread-safe collector when needed.
3. Publish events with exact test data.
4. Assert the listener is invoked only for cases where the condition is true.
5. For expressions referencing invalid properties/variables, assert errors are detected in synchronous setup rather than expecting silent skipping.
6. If async, use `CountDownLatch` or await with a timeout rather than fixed `Thread.sleep(...)`.
7. If transactional, test no-transaction, commit, and rollback paths with the test's actual transaction manager.
8. Run tests using the same Maven/Gradle compiler settings as the production artifact, especially when conditions reference parameter names.

**Do not test SpEL solely by invoking the handler method directly**: direct method calls bypass Spring's `@EventListener` filter infrastructure. Events must be published through `ApplicationContext` to trigger conditions.

## 12. Checklist When Production Shows "Zero Logs"

1. **Was `publishEvent(...)` actually called?** Confirm from producer logs with event ID and status right at publish time.
2. **Does the event type match the listener parameter?** Check runtime class, generics, and classloader if needed.
3. **Is the listener inside a Spring-managed bean?** Check component scan, `@Bean`, profiles, and the right context.
4. **Does the listener receive events when the condition is removed?** Use a side-effect-free probe in a test environment.
5. **Does `condition="true"` work?** If yes, move on to debugging data and the expression.
6. **Does switching from parameter name to `#p0` fix it?** If yes, check `-parameters` metadata.
7. **Are `#root.event` and payload confused?** For directly published records, the root event may be `PayloadApplicationEvent`.
8. **Have case/null/enum/threshold boundaries been checked?** Especially exact equality at thresholds.
9. **Is there a SpEL exception hidden on another log/thread?** Check `ErrorHandler` and async handling.
10. **Is another gate outside the condition blocking it?** `@TransactionalEventListener`, no-transaction, phase, late listener registration, different context.
11. **Is there a Spring-context test reproducing both true and false?** Lock it in with a regression test.

Once the root cause is found, prioritize fixing **data contracts, clear expressions, or runtime configuration**. Do not leave `condition="true"` in production code just to "cure" a silent listener if business rules still require filtering.

## 13. Self-Check Exercises

**Q1.** For a method receiving `PaymentChanged event` when the compiler does not retain parameter names, how should the parameter be referenced in SpEL?

**Answer:** Use `#p0`, `#a0`, or `#root.args[0]`, e.g. `#p0.status() == 'PAID'`. These do not depend on Java variable names.

**Q2.** Why might `#root.event.status()` fail when the publisher calls `publishEvent(new PaymentChanged(...))`?

**Answer:** Because payload objects are typically wrapped by Spring in `PayloadApplicationEvent`, making `#root.event` the wrapper rather than `PaymentChanged`. Use `#p0.status()` or `#root.event.payload.status()` where appropriate.

**Q3.** With `status="PAID"` and `amount=1000`, what is the result of `#p0.status() == 'PAID' and #p0.amount() > 1000`?

**Answer:** False, because `1000 > 1000` is false. If values equal to the threshold must match, use `>= 1000`.

**Q4.** Can you conclude "SpEL is always false" when a `@TransactionalEventListener` does not run outside a transaction?

**Answer:** No. With the default `fallbackExecution=false`, the listener may not be invoked due to lacking an appropriate transaction, even when the condition is true.

**Q5.** An expression accesses a nonexistent property on `#root.event`. Does Spring always silently return false?

**Answer:** No. Usually a SpEL evaluation error occurs (e.g., `SpelEvaluationException`). In async listeners, the error may only appear on a separate executor/log/handler.

**Q6.** Why is calling `handlers.onLargePaid(event)` directly in a unit test insufficient to test `condition`?

**Answer:** Direct Java calls bypass the `@EventListener` infrastructure; annotation filters are evaluated when Spring receives and dispatches events through the context.

**Q7.** An event has status `paid` (lowercase); does `#p0.status() == 'PAID'` match?

**Answer:** No, if comparing strictly as in the example; status must be normalized or compared case-insensitively per contract.

**Q8.** If a single event with matching status/amount fails to trigger a filtered listener, what least-invasive debugging step should come first?

**Answer:** Confirm the publisher emitted the right type/data, then test with an unconditional listener or `condition="true"` in a test environment to separate routing from the expression.

## References

- [Spring Framework 6.2 — ApplicationContext Events](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html): type-based event handling, `@EventListener(condition)`, and SpEL metadata table (`#root.event`, `#root.args`, `#a0`).
- [Spring Framework 6.2.9 Javadoc — EventListener](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/context/event/EventListener.html): Boolean and true-string contract, `condition`, event class list, listener ID.
- [Spring Framework 6.2 Javadoc — PayloadApplicationEvent](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/context/PayloadApplicationEvent.html): wrapper when publishing payload objects.
- [Spring Framework — SpEL Language Reference](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref.html): comparison and logical operators, null handling, property/method access.
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html): `@TransactionalEventListener`, `fallbackExecution`, and transaction phases.
- [Spring Framework 6.2 Javadoc — ApplicationListenerMethodAdapter](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/context/event/ApplicationListenerMethodAdapter.html): listener method processing, argument resolution, and condition evaluation.
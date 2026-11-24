# Overly Broad Matching Risks of rollbackForClassName and noRollbackForClassName

> **Spring Framework — Transaction Management → Rollback Rules.** This lesson explains why the `rollbackForClassName` and `noRollbackForClassName` attributes on `@Transactional` can affect **exceptions you never intended to configure**, causing transactions to roll back or commit unexpectedly. The focus is on **substring matching in exception class names**, colliding names and nested classes, how Spring resolves multiple rules, and how to choose safe, testable rules.

## 1. The Problem: One Exception Name Can Match Multiple Different Types

Consider a service that saves an order. If the business error `OrderRejectedException` occurs, the author wants to persist a processed status, so they configure that exception **not to trigger rollback**:

```java
@Transactional(noRollbackForClassName = "OrderRejectedException")
public void submitOrder() {
    // Save data and process business logic...
}
```

This is a **fragment**: the method must reside on a transaction-managed Spring bean, not a standalone Java program. A problem arises when the codebase adds `OrderRejectedExceptionCritical`, a `RuntimeException` representing a severe failure: **its class name still contains the substring `OrderRejectedException`**.

With `noRollbackForClassName = "OrderRejectedException"`, Spring may choose **not to roll back** even when the method throws `OrderRejectedExceptionCritical`. For a `RuntimeException`, that goes against the usual default rollback policy. If write operations succeeded before the error, the transaction manager may attempt to commit those changes.

The reverse direction is equally noteworthy:

```java
@Transactional(rollbackForClassName = "OrderRejectedException")
public void submitOrder() {
    // ...
}
```

The author may have meant to specify rollback for a particular checked exception, yet `OrderRejectedExceptionV2` (a class that **does not extend** `OrderRejectedException`) can also be forced to roll back if its name contains that substring. Even a nested exception named `OrderRejectedException$Details` can match.

**Similar names do not imply an inheritance relationship.** String pattern matching is no substitute for Java type checking. That is the core risk to remember when using the `ClassName` suffix.

## 2. Distinguishing the Four Rollback Attributes of `@Transactional`

The proper annotation import is `org.springframework.transaction.annotation.Transactional`. There are four configuration groups:

| Attribute | Value type | Matching condition | Effect when matched |
| --- | --- | --- | --- |
| `rollbackFor` | `Class<? extends Throwable>[]` | Actual exception equals or **extends** the declared type | Choose rollback |
| `noRollbackFor` | `Class<? extends Throwable>[]` | Actual exception equals or **extends** the declared type | Choose no rollback |
| `rollbackForClassName` | `String[]` | Exception name in the inheritance chain **contains** the pattern | Choose rollback |
| `noRollbackForClassName` | `String[]` | Exception name in the inheritance chain **contains** the pattern | Choose no rollback |

The two `Class`-based attributes are **recommended by Spring** because they align with the Java type system. The two string-based `ClassName` attributes are useful when the exception class cannot be referenced directly at compile time, but their patterns require extra care.

Example of two ways to define rollback:

```java
@Transactional(rollbackFor = OrderRejectedException.class)
public void typedRule() {
    // Matches OrderRejectedException and its actual subclasses.
}

@Transactional(rollbackForClassName = "OrderRejectedException")
public void stringRule() {
    // Matches any Throwable whose class/superclass name contains the string above.
}
```

This snippet is a **fragment**, assuming an `OrderRejectedException` class and methods inside a Spring bean. A `ClassName` entry is not a regex, glob, or exact-match class name; Spring does not require the pattern to equal the entire class name.

### Default Rule When No Custom Rule Matches

Under standard Spring transaction attribute defaults, `RuntimeException` and `Error` trigger rollback, whereas checked `Exception`s generally do not. If a custom rule is configured but **does not match** the exception under consideration, Spring falls back to the corresponding default policy.

Since Spring Framework 6.2, applications can alter the default policy at configuration level (e.g., `@EnableTransactionManagement(rollbackOn = RollbackOn.ALL_EXCEPTIONS)`), so the outcome when **no rule matches** may differ from the traditional default. Explicit rules on the annotation still need to be evaluated under the precedence mechanism.

**Important:** `rollbackForClassName` and `noRollbackForClassName` only determine the rule-based rollback/commit decision at the transaction boundary. They do not guarantee the database can actually commit if the driver, engine, or transaction is already rollback-only; nor do they turn a swallowed exception into a rollback.

## 3. How Does Spring Match Exception Name Strings?

Under the hood, Spring uses the logic of `RollbackRuleAttribute` and `NoRollbackRuleAttribute`. For a rule constructed with a `String`, Spring checks whether the exception class name **contains** the pattern. Checking the current class and then walking the superclass chain can be illustrated by this model:

```text
thrown exception
       |
       v
check the exception's class name
       |
       +-- contains pattern? ---> match at depth = 0
       |
       +-- does not contain ----> check superclass
                                  |
                                  +-- contains pattern? ---> depth = 1
                                  |
                                  +-- continue up superclasses...
                                  |
                                  +-- no more matching superclasses => depth = -1
```

This is an **explanatory model**, not verbatim Spring source code.

Details with practical consequences:

1. The pattern is a **substring** (`String.contains(...)`), case-sensitive according to Java class names.
2. Wildcard/regex syntax is not supported in these rollback patterns. `"Order*Exception"` does **not** mean “any class with prefix Order and suffix Exception”.
3. Spring can check the **fully qualified class name** as well as superclass names; the pattern `"OrderRejectedException"` can match `com.acme.orders.OrderRejectedException`, `com.other.OrderRejectedException`, or `com.acme.OrderRejectedExceptionV2`.
4. For nested classes, Java's binary class name contains `$`; for example, `com.acme.OrderRejectedException$Details` contains `com.acme.OrderRejectedException`.
5. Rules match against the **thrown exception type and its superclasses**. Do not confuse walking superclasses with automatically walking `Throwable.getCause()`: a rule matching the cause's name **does not automatically** apply when a wrapper exception is what exits the method.
6. If a rule matches a superclass, the resulting depth is positive. When multiple rules match, depth is what decides the winning rule.

A somewhat surprising consequence: even a **fully qualified pattern** is still a substring check, not an exact-equality rule.

```java
@Transactional(
    rollbackForClassName = "com.acme.orders.OrderRejectedException"
)
public void submitOrder() {
    // ...
}
```

The configuration above can still match `com.acme.orders.OrderRejectedExceptionV2` and `com.acme.orders.OrderRejectedException$Details`. Including the package name reduces cross-package collisions, yet **does not eliminate** suffix or nested-class collisions.

## 4. Four Types of Unintended Matches

### 4.1. Overly Generic Pattern: `"Exception"`

```java
@Transactional(rollbackForClassName = "Exception")
public void process() {
    // ...
}
```

The pattern `"Exception"` appears in the names of vast numbers of classes such as `IOException`, `SQLException`, `IllegalArgumentException`, and `RuntimeException`. It can match at depth 0 and override other rules that only match via a superclass.

If you truly want a rollback policy for all `Exception`s (including checked exceptions), the **type rule** `rollbackFor = Exception.class` is the clear, type-safe choice; or use the global default rollback configuration supported by your Spring version when intended application-wide.

However, `"Exception"` does not match every `Throwable`: `Error` is a separate branch of `Throwable`, not a subclass of `Exception`. Do not document `rollbackForClassName = "Exception"` as “rolls back on all errors” without noting this limitation.

### 4.2. Short Name Pattern Matching a Same-Named Class in Another Package

```java
@Transactional(noRollbackForClassName = "ValidationException")
public void register() {
    // ...
}
```

`com.acme.customer.ValidationException` and `com.vendor.gateway.ValidationException` can have completely different purposes while both containing `ValidationException`. If the second class signals an infrastructure failure that needs rollback, this configuration can still request no rollback.

A new dependency introducing an exception with the same simple name can **silently alter transaction semantics** without touching the file containing `@Transactional`.

### 4.3. Same Prefix, Added Suffix: `CustomExceptionV2`

Suppose there are **sibling classes with no inheritance relationship**:

```java
class PaymentDeclinedException extends Exception {}

class PaymentDeclinedExceptionV2 extends Exception {}
```

A string rule:

```java
@Transactional(
    rollbackForClassName = "PaymentDeclinedException"
)
public void settle() {
    // ...
}
```

Matches **both classes** even if the author intended only the first. By contrast:

```java
@Transactional(
    rollbackFor = PaymentDeclinedException.class
)
public void settle() {
    // ...
}
```

Matches only `PaymentDeclinedException` or its **actual subclasses**, not `PaymentDeclinedExceptionV2` if it is a sibling class.

Suffixes like `V2`, `Special`, `Critical`, `Retryable`, `Impl`, or generated class names can cause an old pattern to match too broadly. Substring inclusion in the class name rather than Java subclassing is the core hazard.

### 4.4. Nested Classes: The `$` Character in Binary Names

```java
class CustomException extends Exception {
    static class AuditDetail extends Exception {}
}
```

Their binary names typically look like:

```text
com.acme.CustomException
com.acme.CustomException$AuditDetail
```

The rule `rollbackForClassName = "com.acme.CustomException"` **still matches** `CustomException$AuditDetail` even though `AuditDetail` does not extend `CustomException`. It is simply declared inside `CustomException`, so its binary name contains the outer class name string.

This differs completely from the type-based rule `rollbackFor = CustomException.class`, which only matches genuine inheritance relationships.

## 5. Why Is `noRollbackForClassName` Especially Dangerous?

With an overly broad `rollbackForClassName`, Spring may **cancel** a transaction the author meant to commit. With an overly broad `noRollbackForClassName`, Spring may **request commit** of a transaction after a severe error has already occurred—often worse because operations prior to the error can be persisted incompletely.

Example:

```java
@Transactional(noRollbackForClassName = "BusinessException")
public void transfer() {
    jdbc.update("UPDATE accounts SET balance = balance - 50 WHERE id = 1");
    // Subsequent operations may fail.
    checkAndCreditDestination();
}
```

This snippet is an **illustrative fragment**, not a standalone program; it requires JDBC setup, tables, and `checkAndCreditDestination()`. Suppose the latter throws `BusinessExceptionCritical extends RuntimeException`. Because its name contains `BusinessException`, an overly broad “no rollback” rule can prevent default rollback behavior for the runtime exception. The manager may attempt to commit the executed debit if the database has not already forced the transaction rollback-only.

This does not mean Spring can always commit: certain SQL errors can put the database transaction into an uncommittable state, or an inner transaction may have already marked rollback-only. **The `noRollbackForClassName` rule dictates the exception-based choice, not the database's ability to commit.**

Comparing two configurations:

```java
// Easy to match unintentionally.
@Transactional(noRollbackForClassName = "BusinessException")
public void riskyMethod() { /* ... */ }

// Clearer: only this class and its actual subclasses are exempt from rollback.
@Transactional(noRollbackFor = BusinessException.class)
public void saferMethod() { /* ... */ }
```

In real code, `BusinessException` needs a clear definition and business meaning. Do not pick `noRollbackFor` just to hide exceptions from showing up: whether to keep or revert changes must follow **data invariants**. A business exception can still demand rollback; for instance, an invalid money transfer must restore balances to their previous state.

### The `"Exception"` Pattern in `noRollbackForClassName`

```java
@Transactional(noRollbackForClassName = "Exception")
public void dangerous() { /* ... */ }
```

This can exempt **a vast number of `RuntimeException`s** from rollback, including `IllegalStateException`, `IllegalArgumentException`, `NullPointerException`, and standard `DataAccessException`s. It practically inverts the default rollback policy for the `Exception` branch without changing any business code.

Never use this pattern as a “catch all exceptions and still commit” trick, especially when an operation runs multiple SQL statements that must succeed or fail together.

## 6. Which Rule Does Spring Choose When Both Rollback and No-Rollback Match?

Spring represents rollback rules with `RollbackRuleAttribute` and no-rollback rules with `NoRollbackRuleAttribute`. `RuleBasedTransactionAttribute.rollbackOn(Throwable)` compares candidate matching rules.

**The rule with the smaller match depth (closer to the thrown exception type) generally wins.** Think of it as:

- Direct match on the thrown exception class: `depth = 0`.
- Match on the nearest superclass: `depth = 1`.
- Match on the next superclass up: `depth = 2`, and so on.
- No match: `depth = -1`, and the rule does not participate in the decision.

It does **not** mean “longer pattern has higher priority” or “type-based rule always beats pattern-based rule”.

Example:

```java
@Transactional(
    rollbackFor = RuntimeException.class,
    noRollbackForClassName = "PaymentException"
)
public void charge() {
    // May throw PaymentExceptionCritical extends RuntimeException.
}
```

If `PaymentExceptionCritical` **extends `RuntimeException`**, both rules match:

- `noRollbackForClassName="PaymentException"` matches directly in the name `PaymentExceptionCritical` → `depth 0`.
- `rollbackFor=RuntimeException.class` matches the superclass `RuntimeException` → `depth 1`.
- **The no-rollback rule wins**; the interceptor will not actively roll back *solely because* of that exception under the selected rule.

This is why an overly broad string pattern can override a class-based rule that the author assumed was “stronger”.

If two opposing rules have the **same depth** for an exception, do not rely on declaration order to decide business policy. Design consistent, non-overlapping rules or test the exact semantics of your Spring version.

### Inheritance vs. Cause Relationships

Another example:

```java
@Transactional(rollbackFor = IOException.class)
public void importFile() {
    // ...
}
```

If the method actually throws a `RuntimeException` wrapping an `IOException` as its `cause`, `rollbackFor=IOException.class` **does not directly match the `RuntimeException` through its cause chain**. Under standard configuration, the `RuntimeException` still rolls back via the default rule. Yet if there is a no-rollback rule for the wrapper, or another fallback, the outcome can change.

To control wrappers, define rules against the **exception type that actually exits the transaction boundary** (or design consistent error translation). Do not confuse class-name substring matching with searching exception messages or causes.

## 7. Runnable Java 17+ Example: Measuring Rule Outcomes Directly from Spring Metadata

This example uses `AnnotationTransactionAttributeSource` to read the annotation into a `TransactionAttribute` and invoke `rollbackOn(Throwable)`. This is **real Spring API** showing whether Spring chooses rollback or not for a given exception.

The example **does not open a database or run real transactions**; it tests **rollback rule evaluation** in isolation and compiles/runs with Java 17+ and Spring Framework 6.2.x. To prove commit/rollback effects on data, add a real integration test as shown in the next section.

### 7.1. Project Structure

```text
rollback-pattern-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── dev/
                └── learning/
                    └── RollbackPatternDemo.java
```

Create `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
            https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>dev.learning</groupId>
    <artifactId>rollback-pattern-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-tx</artifactId>
            <version>6.2.8</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
                <configuration>
                    <release>17</release>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>dev.learning.RollbackPatternDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

### 7.2. Create `src/main/java/dev/learning/RollbackPatternDemo.java`

```java
package dev.learning;

import java.io.IOException;
import java.lang.reflect.Method;

import org.springframework.transaction.annotation.AnnotationTransactionAttributeSource;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.interceptor.TransactionAttribute;

public final class RollbackPatternDemo {

    // Base checked exception.
    public static class PaymentException extends Exception {

        // This is a nested class; it does NOT extend PaymentException.
        public static class DetailException extends Exception {}
    }

    // Actual subclass: type-based rule should match.
    public static class PaymentExceptionSubtype extends PaymentException {}

    // Only shares a name prefix: does NOT extend PaymentException.
    public static class PaymentExceptionV2 extends Exception {}

    // RuntimeException matching the substring, but does not extend PaymentException.
    public static class PaymentExceptionCritical
            extends RuntimeException {}

    public static class Rules {

        @Transactional(rollbackForClassName = "PaymentException")
        public void pattern() {}

        @Transactional(rollbackFor = PaymentException.class)
        public void typed() {}

        @Transactional(noRollbackForClassName = "PaymentException")
        public void noPattern() {}

        @Transactional(noRollbackFor = PaymentException.class)
        public void noTyped() {}

        @Transactional(rollbackForClassName = "Exception")
        public void broad() {}

        @Transactional
        public void baseline() {}

        @Transactional(
            rollbackFor = RuntimeException.class,
            noRollbackForClassName = "PaymentException"
        )
        public void competing() {}
    }

    private static final AnnotationTransactionAttributeSource SOURCE =
            new AnnotationTransactionAttributeSource();

    private static boolean shouldRollback(
            String methodName, Throwable error)
            throws NoSuchMethodException {

        Method method = Rules.class.getMethod(methodName);
        TransactionAttribute attr =
                SOURCE.getTransactionAttribute(method, Rules.class);

        if (attr == null) {
            throw new IllegalStateException(
                    "Missing @Transactional on " + methodName);
        }

        return attr.rollbackOn(error);
    }

    private static void show(
            String label, String methodName, Throwable error)
            throws NoSuchMethodException {
        System.out.println(
                label + "=" + shouldRollback(methodName, error));
    }

    public static void main(String[] args)
            throws NoSuchMethodException {

        show("pattern.exact", "pattern", new PaymentException());
        show("pattern.subtype", "pattern",
                new PaymentExceptionSubtype());
        show("pattern.suffix", "pattern",
                new PaymentExceptionV2());
        show("pattern.nested", "pattern",
                new PaymentException.DetailException());

        show("type.exact", "typed", new PaymentException());
        show("type.subtype", "typed",
                new PaymentExceptionSubtype());
        show("type.suffix", "typed", new PaymentExceptionV2());
        show("type.nested", "typed",
                new PaymentException.DetailException());

        show("noPattern.runtime", "noPattern",
                new PaymentExceptionCritical());
        show("noType.runtime", "noTyped",
                new PaymentExceptionCritical());

        show("baseline.checked", "baseline", new IOException());
        show("broad.checked", "broad", new IOException());

        show("competing.runtime", "competing",
                new PaymentExceptionCritical());
    }
}
```

**Why is this code a valid demonstration of Spring rule matching?**

- `AnnotationTransactionAttributeSource` reads the actual `@Transactional` metadata on `Rules`.
- `TransactionAttribute.rollbackOn(Throwable)` returns `true` if rollback is required under the active rules, and `false` if rollback is not requested under the active rules.
- All exceptions are independent Java classes declared in the same file, making the contrast between **Java inheritance** and **textual name matching** easy to observe.
- `PaymentException.DetailException` is a nested class: its binary name contains `PaymentException$DetailException`, yet its superclass is `Exception`, not `PaymentException`.
- `PaymentExceptionV2` is a sibling checked exception; its name contains `PaymentException`, yet it does not inherit from it.
- `PaymentExceptionCritical` is a runtime exception, so it rolls back by default; a no-rollback pattern can still invert that decision.

### 7.3. Compile and Run

In the `rollback-pattern-demo` directory, JDK 17+ and Maven are required; the first Maven run needs access to the dependency repository:

```bash
mvn -q clean compile exec:java
```

The lines printed by the program in order (ignoring auxiliary logs depending on Maven configuration):

```text
pattern.exact=true
pattern.subtype=true
pattern.suffix=true
pattern.nested=true
type.exact=true
type.subtype=true
type.suffix=false
type.nested=false
noPattern.runtime=false
noType.runtime=true
baseline.checked=false
broad.checked=true
competing.runtime=false
```

### 7.4. Reading the Results by Group

**Pattern rollback group:**

- `pattern.exact=true` matches as intended.
- `pattern.subtype=true` also matches appropriately because a subclass of `PaymentException` has a superclass containing the pattern.
- `pattern.suffix=true` proves **unintended matching**: `PaymentExceptionV2` is not a subclass.
- `pattern.nested=true` proves a nested class's binary name can match despite having no inheritance relationship.

**Typed rollback group:**

- `type.exact=true` and `type.subtype=true` match exact type relationships.
- `type.suffix=false` and `type.nested=false`. These two exceptions are checked, do not match the typed rule, and fall back to the default no-rollback policy.

**No-rollback group:**

- `noPattern.runtime=false`: a runtime exception is excluded from rollback because its name contains the pattern.
- `noType.runtime=true`: the typed rule only exempts `PaymentException` and its true subclasses; `PaymentExceptionCritical` does not belong to that hierarchy and still rolls back by default.

**Broad pattern and competing rules group:**

- `baseline.checked=false`: `IOException` is a checked exception, so it does not automatically roll back under standard defaults.
- `broad.checked=true`: `IOException` contains the substring `Exception`, so the broad pattern requests rollback.
- `competing.runtime=false`: the no-rollback pattern directly matches `PaymentExceptionCritical` at depth 0, while the typed rollback rule `RuntimeException.class` matches its superclass at depth 1. The closer rule wins.

**Demo limitation:** this is **transaction rule evaluation**, without AOP proxies, JDBC connections, or real commits. It verifies the matching mechanism; do not use these true/false results alone to claim a database rolled back or committed.

## 8. Applying the Lesson to a Transactional Service

### Unintended Outcome: Data Commits When a Runtime Exception Occurs

In a Spring service using `JdbcTemplate` and a `PlatformTransactionManager` for the right datasource:

```java
@Service
public class PaymentService {
    private final JdbcTemplate jdbc;

    public PaymentService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional(noRollbackForClassName = "PaymentDeclinedException")
    public void charge(long orderId) {
        jdbc.update(
            "UPDATE payments SET reserved = TRUE WHERE order_id = ?",
            orderId
        );
        throw new PaymentDeclinedExceptionCritical();
    }
}
```

This snippet is a **fragment within a Spring application**, requiring imports and `PaymentDeclinedExceptionCritical extends RuntimeException`. The point is showing the business method already updated a row before the exception escaped. If the bean is called through a Spring proxy and there is no other rollback-only factor, the no-rollback pattern can make the manager **commit** the `reserved` update despite the runtime exception.

To verify in practice, write an integration test: seed a row with `reserved=false`, invoke `charge(...)` via the Spring proxy and catch the exception **outside** the call, then query on an independent connection. Reading back `reserved` reveals whether commit or rollback occurred. Next, try `noRollbackFor = PaymentDeclinedException.class` with a critical exception class that does not extend `PaymentDeclinedException` to observe the policy change.

Do not rely on mock tests that only assert `update(...)` was called. Mocks do not prove whether the transaction committed or rolled back.

### Reverse Case: Accidentally Rolling Back a New Checked Exception

```java
@Transactional(rollbackForClassName = "GatewayTimeoutException")
public void processBatch() throws GatewayTimeoutExceptionV2 {
    // Record some results that the business logic might want to keep.
    throw new GatewayTimeoutExceptionV2();
}
```

This is also a fragment; assume `GatewayTimeoutExceptionV2 extends Exception` and does not extend `GatewayTimeoutException`. Spring's standard default does not roll back for that checked exception, yet the rollback pattern still matches because of the substring. If the business logic truly wanted to commit partial results, behavior has diverged from expectations.

Do not treat “partial commit” as inherently right: in an operation needing atomicity, rolling back might actually be the desired behavior. **The risk here is that the configuration does not reflect an intentional decision about the exact exception type thrown.**

## 9. Differences Between Exception Type, Class Name, and Cause

When a lower-layer error is wrapped:

```java
try {
    gateway.call();
} catch (IOException cause) {
    throw new IllegalStateException("Gateway failed", cause);
}
```

The exception exiting the transactional boundary is `IllegalStateException`, while `IOException` sits in `cause`. When Spring evaluates rollback rules, it inspects the exception thrown across the boundary and its **superclasses**. Do not assume `rollbackForClassName = "IOException"` automatically searches inside `cause`.

For `IllegalStateException`, Spring rolls back by default because it is a `RuntimeException`. However, if `noRollbackForClassName="IllegalState"` is present, the configuration can alter the outcome. That is why rules on the outer exception must be explicit rather than relying on a pattern hidden in the cause.

On the other hand, if the repository layer uses Spring exception translation to turn `SQLException` into `DataAccessException` (runtime), the exception type exiting the service can differ from the type thrown by the JDBC driver. Rules should be based on the **translated exception type at the service boundary**, not on observing a driver-layer subclass prior to translation.

## 10. Safe Configuration Strategies

### 10.1. Prefer Type-Safe Rules When the Exception Class Is Available

```java
@Transactional(
    rollbackFor = IOException.class,
    noRollbackFor = RecoverableBusinessException.class
)
public void handle() throws IOException {
    // ...
}
```

This fragment requires an actual `RecoverableBusinessException` class. With type rules, the compiler verifies class names; refactoring a package/class name can be updated automatically by the IDE. `IOException.class` matches `IOException` and its subclasses, not a sibling class whose name merely happens to contain `IOException`.

**Do not write `rollbackForClassName="IOException"` when you can reference `IOException.class`.**

### 10.2. If You Must Use ClassName, Pick a Sufficiently Specific Name

Sometimes the exception type lives in an optional integration module and the current source code should not carry a compile-time dependency. In that case:

```java
@Transactional(
    rollbackForClassName =
        "com.vendor.special.GatewaySessionExpiredException"
)
public void processExternalSession() {
    // ...
}
```

This is better than `"Exception"` or `"Session"` because it limits package collisions. **Even so, you must still test** suffixed names like `GatewaySessionExpiredExceptionV2` and nested classes like `GatewaySessionExpiredException$Detail`. There is no default “exact equals” syntax in `rollbackForClassName`.

If the business requirement strictly demands **only one exact class, with no subclasses/suffixes/nested matches**, the `ClassName` option cannot express an exact-string match condition. You need to bring the appropriate dependency onto the classpath and use a type-based rule, or build error handling inside the service by concrete exception type with explicit boundary control.

### 10.3. Separate Exceptions with Distinct Semantics

```java
class PaymentDeclinedException extends Exception {}
class PaymentInfrastructureFailure extends RuntimeException {}
```

These two classes have distinct business semantics. Your exception hierarchy should reflect error-handling policy rather than merely appending suffixes like `V2`/`Critical` and hoping old patterns exclude new classes.

Still, **renaming does not fundamentally cure pattern flaws**: another dependency could still introduce a class containing the matching substring. Type safety and tests remain essential.

### 10.4. Avoid Overlapping Positive and Negative Rules

```java
@Transactional(
    rollbackForClassName = "Exception",
    noRollbackFor = BusinessException.class
)
public void settle() {
    // ...
}
```

The broad pattern `"Exception"` can match `BusinessException` directly at depth 0; the negative typed rule also matches at depth 0. Such equal-rank ties are hard to read and fragile under refactoring or rule reordering. **Avoid conflicting rules at the same depth**; define clear exception groups and test boundary classes.

Also note: **a specific rule in `@Transactional` does not replace every other rule**. If an exception matches no rule, the default fallback can still roll back runtime errors. If an exception matches a no-rollback rule while the underlying transaction is already rollback-only, the physical commit can still fail.

### 10.5. Review by Behavior, Not Just Annotation Syntax

Whenever you see `rollbackForClassName` or `noRollbackForClassName` in a code review, ask:

- Which exception classes **can actually exit** the method through the Spring proxy?
- Are there subclasses, suffixed siblings, nested classes, or same simple names in other packages?
- Which exceptions get altered in type by a wrapper or translator before exiting?
- Are there competing rollback/no-rollback rules, and which rule depth wins?
- Is the rule genuinely business-driven, or is it masking swallowed exceptions?
- What happens to already written data when the exception is thrown: commit, rollback, or database-enforced rollback-only?

If you cannot answer with tests, the pattern may be an implicit behavioral dependency.

## 11. Recommended Regression Test Suite

### Pure Rule-Matching Tests (Fast, No Database Needed)

Section 7 showed how to test `TransactionAttribute.rollbackOn(Throwable)`:

| Case | Pattern-based rule | Desired type-based rule |
| --- | --- | --- |
| Exact exception name | Matches | Matches |
| True subclass of configured exception | Matches (via superclass) | Matches |
| Sibling `...ExceptionV2` whose name contains pattern | **May match unintentionally** | Does not match |
| Non-inheriting nested `...Exception$Detail` | **May match unintentionally** | Does not match |
| Exception with same simple name in another package | May match a simple-name pattern | Does not match unless same class |
| Runtime exception whose name contains `noRollbackForClassName` | May be excluded from default rollback | Type rule has no effect without inheritance |
| Broad `"Exception"` against `IOException` | Matches | `Exception.class` also matches by type, more explicitly |

### Integration Tests with a Real Transaction Manager and Database

1. **Prepare:** create initial data in a committed transaction; know the exact rows.
2. **Invoke:** call the service bean through the Spring proxy, not via `new` or `this.method()`.
3. **Cause failure:** trigger an error after executing write operations; use both the intended exception class and lookalike-named classes to distinguish behavior.
4. **Observe:** after the method returns/throws, read data using an independent connection/transaction. Verifying mock invocations alone is not enough.
5. **Assert:** for rollback cases, data returns to the initial state; for intentional business no-rollback cases, only permitted changes remain.
6. **Repeat:** swap the exception class to `...V2` or a nested class and verify the rule still reflects the intended policy.

One note when using Spring TestContext: a `@Transactional` test method may be rolled back by the framework at the end of the test, distorting observation of a service commit. To test **actual service commits**, design the test without wrapping it in an unnecessary test-managed transaction, or use `TestTransaction` appropriately to control test boundaries.

### When You Need to Verify Precedence

In unit tests, inspect `RollbackRuleAttribute.getDepth(Throwable)` or the final result of `RuleBasedTransactionAttribute.rollbackOn(Throwable)`. Do not just verify that a rule exists on the annotation; verify the **actual exception** against the complete rule set.

An application may alter default rules based on Spring version/configuration. Regression tests must therefore run against the same Spring version and transaction configuration that the application deploys.

## 12. Common Misconceptions

**“Writing the full package makes ClassName an exact match.”** False. A fully qualified pattern can still match suffixes like `V2` and nested `$Detail`.

**“The `*Exception` pattern works as a glob wildcard.”** False. Spring does not treat `*` as a wildcard in these rollback rule patterns.

**“`rollbackForClassName` only checks simple class names, ignoring superclasses.”** False. Spring can walk up the superclass hierarchy; a superclass match has a greater depth than a direct match.

**“A typed rule always takes priority over a string pattern.”** False. Winner selection relies on **match depth**, so a direct pattern match can beat a typed superclass rule.

**“`noRollbackForClassName` only handles checked exceptions.”** False. It can match `RuntimeException`s, significantly altering default rollback behavior.

**“`noRollbackForClassName` guarantees the transaction commits after an error.”** False. It changes the exception-based rollback decision; commit can still fail if the database/resource errors or the transaction is already rollback-only.

**“Rollback rules automatically inspect `getCause()`.”** False under the described exception/superclass matching semantics. If an exception is wrapped, rules must match the exception evaluated at the boundary.

**“If the `rollbackOn(...)` unit test passes, no integration test is needed.”** False. Unit tests only show rule selection. Tests against a real transaction manager + datasource are needed to confirm data commits/rolls back as designed.

## 13. Configuration Checklist

- [ ] If the exception class is known at compile time, use `rollbackFor = X.class` or `noRollbackFor = X.class`.
- [ ] If using `ClassName` due to module constraints, write a sufficiently specific name and document the reason.
- [ ] Avoid blindly using overly broad patterns like `"Exception"`, especially with `noRollbackForClassName`.
- [ ] Check for package collisions, `V2` suffixes, nested `$` classes, and same simple names.
- [ ] Understand superclass matching, rule depth, and default fallbacks.
- [ ] Avoid conflicting rules at equal depth where outcomes depend on obscure ordering.
- [ ] Test checked exceptions, runtime exceptions, and wrapped/translated exceptions.
- [ ] Confirm the method is intercepted through a Spring proxy and resources participate in the right transaction manager.
- [ ] Test persisted data after the method throws, including both intentional commit and rollback cases.
- [ ] Re-verify semantics when upgrading Spring or changing the default rollback policy.

## 14. Self-Check

**Question 1.** Does `rollbackForClassName = "com.acme.CustomException"` match `com.acme.CustomExceptionV2` even without inheritance?

Yes. The second class's name contains the entire pattern string. That is precisely why even an FQCN does not guarantee exact matching.

**Question 2.** Can `noRollbackForClassName = "Exception"` stop `NullPointerException` from rolling back?

Yes. `NullPointerException` is a runtime exception whose name contains `Exception`. If this rule wins and the transaction is not already rollback-only, the manager may try to commit instead of rolling back by default.

**Question 3.** Does the rule `rollbackFor = CustomException.class` match `CustomException$NestedException`?

Only if the nested exception **actually extends `CustomException`**. Having a binary name containing the string `CustomException` does not by itself make a type-based rule match.

**Question 4.** Why can `noRollbackForClassName="PaymentException"` beat `rollbackFor=RuntimeException.class` for `PaymentExceptionCritical extends RuntimeException`?

The pattern matches the name `PaymentExceptionCritical` directly at depth 0, whereas typed `RuntimeException` matches at superclass depth 1. The lower depth wins.

**Question 5.** Does `rollbackForClassName="IOException"` automatically match an `IllegalStateException` whose cause is an `IOException`?

Not under the described class-name and superclass matching mechanism. You must account for the actual exception type exiting the transaction boundary; in that scenario `IllegalStateException` may roll back under the default runtime policy.

**Question 6.** How do you prove a no-rollback rule affects real commits?

Write an integration test with previously committed seed data, call the service through its proxy, raise the exception after writing, and query from an independent connection after the transaction finishes. Compare actual data against the desired business policy.

## 15. Key Takeaways to Remember

- **`rollbackForClassName`/`noRollbackForClassName` match substrings of exception class names**, not Java type equality and not wildcards/regexes.
- **Similar names, `V2` suffixes, shared simple names, and `$` nested classes** can cause a rule to apply to unintended exceptions.
- **Overly broad `noRollbackForClassName` is especially risky** because it can turn a runtime failure that should roll back into a commit request.
- **The strongest matching rule** is decided by match depth in the exception superclass hierarchy, not merely attribute name or pattern length.
- **Prefer `Class`-based `rollbackFor`/`noRollbackFor` whenever possible**; if strings are unavoidable, write unit/integration tests with lookalike names and wrapped exceptions.
- **A rollback rule decision is not synonymous with the physical commit outcome**: the database, transaction manager, rollback-only flags, and resource participation still determine the final result.

## Official References

1. [Spring Framework 6.2 — Rolling Back a Declarative Transaction](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/declarative/rolling-back.html): comparing type-based and pattern-based rules, false positive warnings for similar names/nested classes, strongest matching rule.
2. [Spring Framework 6.2 — `@Transactional` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/annotation/Transactional.html): semantics of `rollbackFor`, `noRollbackFor`, `rollbackForClassName`, and `noRollbackForClassName`.
3. [Spring Framework 6.2 — `RollbackRuleAttribute` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/interceptor/RollbackRuleAttribute.html): type/pattern constructors, `getDepth(Throwable)`, and superclass matching.
4. [Spring Framework 6.2 — `NoRollbackRuleAttribute` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/interceptor/NoRollbackRuleAttribute.html): semantics of negative rules.
5. [Spring Framework 6.2 — `RuleBasedTransactionAttribute` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/interceptor/RuleBasedTransactionAttribute.html): `rollbackOn(Throwable)` and winner selection rules.
6. [Spring Framework 6.2 — Using `@Transactional`](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/declarative/annotations.html): defaults and global rollback policy support since Spring 6.2.

# Splitting Transaction Policies for Service Groups with XML in Spring Framework

## 1. Problem: multiple service groups do not necessarily share one policy

In a Spring application, services typically handle different kinds of work:

- **Order/Command service** modifies data and needs rollback whenever any required business step fails, including certain checked exceptions.
- **Report/Query service** primarily reads data, needs a clear read-transaction scope, and can declare `read-only="true"` so the infrastructure is allowed to optimize.
- **Batch/Import service** processes longer batches and may need timeouts and per-batch transaction boundaries rather than one giant transaction.

If a single policy is attached across the entire `service` package, those requirements easily conflict. Spring provides **XML declarative transaction** configuration: define multiple `<tx:advice>` elements, select the target methods with **AOP pointcuts**, and connect each pointcut to an advice using `<aop:advisor>`.

**Lesson goal:** understand how to **split transaction policies for service groups** in XML, know which policy applies where, avoid overlapping or uncovered advisors, and verify with real data.

After this lesson, you will know how to:

1. Distinguish **target selection** (pointcut), **transaction rules** (`tx:advice`), and **transaction execution** (transaction manager).
2. Write XML declaring two groups with different policies without requiring `@Transactional` on every method.
3. Understand the boundaries of `read-only`, `rollback-for`, `timeout`, `propagation`, and how a policy depends on an outer transaction.
4. Run a Java 17+, Spring Boot, JDBC, and H2 example showing the write group rolling back `IOException` while the report group is marked read-only.
5. Diagnose overly broad package pointcuts, proxy-bypassing calls, mismatched transaction managers, and multiple advisors intercepting the same call.

This article belongs to the **XML Configuration** section of the Spring Framework — transaction management module. The Java part verifies how XML affects Spring beans; XML is where the transaction policies are declared.

## 2. Three-component model: pointcut, advice, and transaction manager

Think of each group as a **"who" + "how"** pair.

| Component | Role | Example |
| --- | --- | --- |
| `<aop:pointcut>` | Selects which method calls belong to which group | All public methods of `orders.*Service` |
| `<tx:advice>` | Defines propagation, readOnly, timeout, and rollback rules by method name | Orders group: `REQUIRED` and roll back checked `Exception` |
| `<aop:advisor>` | Connects the pointcut to the right advice | `ordersPointcut` → `ordersTxAdvice` |
| `PlatformTransactionManager` | Opens, joins, commits, or rolls back on a specific resource | `DataSourceTransactionManager` for JDBC `DataSource` |
| Spring AOP proxy | Intercepts matching calls so transaction advice runs | Bean injected into the caller |

Execution flow:

```text
Caller invokes Spring bean through proxy
               |
               v
AOP pointcut checks method/class/package
       |                           |
       v                           v
  Orders group                Reports group
  ordersTxAdvice              reportsTxAdvice
  REQUIRED, read-write        REQUIRED, read-only
  rolls back checked Exception shorter timeout
       |                           |
       +-------------+-------------+
                     v
             TransactionInterceptor
                     |
                     v
           PlatformTransactionManager
                     |
                     v
             JDBC / JPA / resource
                     |
                     v
            Commit or rollback
```

**Distinguish two filtering levels:**

- The AspectJ expression in `<aop:pointcut>` selects *which calls* are eligible for advice processing, by package, class, method, and signature.
- The `<tx:method name="...">` tags **inside an advice** only select *which rule* applies to method names already caught by the pointcut. `name="find*"` does not automatically extend the advisor across the whole application.

For example, if you have `<tx:method name="find*" read-only="true"/>` but the pointcut only matches the `orders` package, a service in the `reports` package **will not** be handled by that advice just because a method is named `findById`.

The infrastructure must have an appropriate transaction manager. The advice does not manage JDBC connections or EntityManagers directly; it delegates to the manager to do so.

## 3. Designing groups before writing XML

A controlled approach is splitting by **meaning and work boundaries**, not merely by file or method names:

| Group | Representative Methods | Suggested Policy | Goal |
| --- | --- | --- | --- |
| `orders` | `createSuccess`, `createThenFail`, `submit` | `REQUIRED`, read-write, `rollback-for="java.lang.Exception"` | Multiple write steps succeed together; specified checked exceptions roll back |
| `reports` | `findCount`, `findSummary`, `getTotals` | `REQUIRED`, `read-only="true"` | Have a read transaction and clearly express query intent |
| `imports` (system-dependent) | `importChunk` | `REQUIRED`, timeout per chunk | Avoid holding one transaction for an entire large file |

**Before configuring**, decide two things: which services truly belong to the group, and whether that policy makes sense for **all methods** in the group. If the same class contains both writes and queries, splitting by package alone may not suffice; split into dedicated services or add specific method-name rules inside the same advice.

Do not assume that:

- An HTTP GET method always needs a transaction.
- `read-only="true"` guarantees the database will reject INSERT/UPDATE.
- Each group having its own advisor means calls from one group to another automatically create two independent transactions.
- One XML `transaction-manager` can provide atomicity across two DBs or a message broker outside the manager's resource.

**Transaction policies are business design and resource capability**, while XML is merely the way to describe/apply them.

## 4. Main XML configuration: two advices, two pointcuts, two advisors

Suppose the services live in:

```text
lesson.xmltx.orders.OrderService
lesson.xmltx.reports.ReportService
```

Place the policies in `src/main/resources/transaction-policies.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xmlns:aop="http://www.springframework.org/schema/aop"
       xmlns:tx="http://www.springframework.org/schema/tx"
       xsi:schemaLocation="
         http://www.springframework.org/schema/beans
         https://www.springframework.org/schema/beans/spring-beans.xsd
         http://www.springframework.org/schema/aop
         https://www.springframework.org/schema/aop/spring-aop.xsd
         http://www.springframework.org/schema/tx
         https://www.springframework.org/schema/tx/spring-tx.xsd">

    <!-- Write group: also rolls back checked Exceptions escaping the method. -->
    <tx:advice id="ordersTxAdvice" transaction-manager="transactionManager">
        <tx:attributes>
            <tx:method name="*"
                       propagation="REQUIRED"
                       read-only="false"
                       timeout="10"
                       rollback-for="java.lang.Exception"/>
        </tx:attributes>
    </tx:advice>

    <!-- Report group: read transaction when called from outside. -->
    <tx:advice id="reportsTxAdvice" transaction-manager="transactionManager">
        <tx:attributes>
            <tx:method name="*"
                       propagation="REQUIRED"
                       read-only="true"
                       timeout="5"/>
        </tx:attributes>
    </tx:advice>

    <aop:config proxy-target-class="true">
        <aop:pointcut id="ordersOperations"
            expression="execution(* lesson.xmltx.orders.*Service.*(..))"/>
        <aop:pointcut id="reportsOperations"
            expression="execution(* lesson.xmltx.reports.*Service.*(..))"/>

        <aop:advisor advice-ref="ordersTxAdvice"
                     pointcut-ref="ordersOperations"/>
        <aop:advisor advice-ref="reportsTxAdvice"
                     pointcut-ref="reportsOperations"/>
    </aop:config>
</beans>
```

**Reading the configuration in order:**

1. `ordersTxAdvice` defines a rule for any method name (`name="*"`) *if* the orders pointcut matches. `rollback-for="java.lang.Exception"` extends rollback to checked exceptions like `IOException`, in addition to default rollback behavior for unchecked exceptions.
2. `reportsTxAdvice` creates a transaction with a read-only hint for report-group methods and a 5-second timeout when starting a new transaction.
3. `execution(* lesson.xmltx.orders.*Service.*(..))` matches executions of methods with any return type on classes whose names end in `Service` in the **direct package** `lesson.xmltx.orders`. The same applies for `reports`.
4. Two `<aop:advisor>` elements bind each policy separately to the two groups. Methods on `OrderService` do not receive `reportsTxAdvice`, and vice versa.
5. `transaction-manager="transactionManager"` references the bean with that name in the Spring container. In the example below, it is a `DataSourceTransactionManager` sharing the H2 `DataSource`.
6. `proxy-target-class="true"` requests class-based proxies in the example. Classes/methods must be interceptable by the proxy; use public methods on Spring beans and avoid `final`/`private` for transaction entry points.

**Matching rule note:** the pattern above only matches classes in the direct package, not subpackages like `orders.internal`. If the project structure requires subpackages, you can consider `execution(* lesson.xmltx.orders..*Service.*(..))` and verify the matched scope in tests. Do not arbitrarily replace it with `execution(* lesson.xmltx..*.*(..))`, as it can open transactions for controllers, utilities, or orchestration classes outside the intended design scope.

### 4.1. Why not share a single advice?

A single advice can hold many `tx:method` lines, but those lines mainly distinguish **by method name**. If both groups have `execute`, `find`, or `process` yet need different policies based on **service role**, a single advice attached across the whole service layer leads to unclear configuration.

Splitting by group lets you inspect and edit each policy independently—for example, the orders group is read-write and rolls back checked exceptions while the reports group is read-only—and scope boundaries are visible directly in the pointcuts.

However, do not duplicate advices just because code sits in different packages. If two groups share the same policy and lifecycle, they can share one advice with well-organized pointcuts. The goal is **reflecting real differences**, not multiplying XML elements.

### 4.2. How do XML policies and `@Transactional` differ?

`<tx:advice>` + `<aop:advisor>` is a way to attach transaction attributes **outside Java source** using XML. The methods in the example **have no `@Transactional`**.

`<tx:annotation-driven/>`, on the other hand, enables infrastructure to read `@Transactional` annotations on beans. These are two ways to declare metadata; both can create transactional advice, but they are not synonymous tags. Avoid adding both and letting two advisors apply to the same method without explicitly designing order/configuration. With Spring Boot, annotation-driven transactions may be auto-configured when conditions match; the XML advisors in this example can still operate independently because they have their own pointcuts and `tx:advice`.

## 5. Parameters on `<tx:method>` and how to choose them

`<tx:method name="...">` applies transaction attributes to method name patterns **already matched by the pointcut**. Some attributes:

| XML Attribute | Common Default | When to Consider |
| --- | --- | --- |
| `name` | Required | `find*`, `get*`, or `*` |
| `propagation` | `REQUIRED` | Join current transaction or create a new one if none exists |
| `isolation` | `DEFAULT` | Specify when you understand data and concurrency needs; for new transactions |
| `read-only` | `false` | Mark read operations when supported by transaction manager/driver/ORM |
| `timeout` | Manager default timeout or unlimited | Limit duration of a new transaction in seconds |
| `rollback-for` | Rolls back unchecked exceptions and `Error` by default | Add checked exceptions that must roll back |
| `no-rollback-for` | No extra rules | An error type that still allows commit per business requirements |

Within the same advice, you can declare specific policies for method name groups and a wildcard fallback:

```xml
<tx:advice id="mixedServiceAdvice" transaction-manager="transactionManager">
    <tx:attributes>
        <tx:method name="find*" read-only="true"/>
        <tx:method name="get*" read-only="true"/>
        <tx:method name="*" rollback-for="java.lang.Exception"/>
    </tx:attributes>
</tx:advice>
```

This is an **illustration of selecting policies within one advice**, not configuration to add to the two-group example above. Spring picks the best-matching name rule when multiple patterns match, so check method naming and test critical methods; a method named `loadAndUpdate` will not become read-only just because it "looks like a query."

**Attribute boundaries:**

- `read-only="true"` is a hint to the infrastructure that may lead to optimizations or driver/DB restrictions depending on the environment; **do not treat it as security or an absolute write-prevention constraint**.
- `timeout` and `isolation` mainly take effect when a new physical transaction is created. If a method only joins an existing transaction under `REQUIRED`, do not expect every inner policy attribute to override the outer transaction's settings automatically.
- `rollback-for` acts when an exception escapes through the transaction interceptor; if a method catches the exception and returns normally, the policy may treat the operation as successful.
- `REQUIRES_NEW` creates an independent physical transaction and consumes extra resources; choose it only when business logic requires an independent commit, not as a workaround for an overly broad pointcut.

## 6. Runnable project to verify the two groups' policies

We create a small example with **Java 17+**, **Spring Boot 3.3.13**, **Spring JDBC**, **Spring AOP**, and **H2**. Boot provides embedded `DataSource` configuration and loads beans; XML is where transaction policies are attached. To avoid depending on an auto-generated transaction manager bean name, we declare the `transactionManager` bean explicitly in Java.

The two groups have verifiable behaviors:

- `OrderService.createSuccess` inserts successfully and commits.
- `OrderService.createThenFail` inserts and then throws **checked `IOException`**. XML `rollback-for` causes the insert to roll back.
- `ReportService.findCount` queries row count and prints transaction state: transaction active and read-only true when called directly from the runner.

### 6.1. File structure

```text
xml-transaction-groups/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/lesson/xmltx/
    │   ├── XmlPolicyApplication.java
    │   ├── orders/OrderService.java
    │   └── reports/ReportService.java
    └── resources/
        ├── schema.sql
        └── transaction-policies.xml
```

The `transaction-policies.xml` file **is the exact XML from Section 4**. Do not alter the advisor wiring when running the demo.

**`settings.gradle`**

```groovy
rootProject.name = 'xml-transaction-groups'
```

**`build.gradle`**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'lesson'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    implementation 'org.springframework.boot:spring-boot-starter-aop'
    runtimeOnly 'com.h2database:h2'
}
```

`spring-boot-starter-jdbc` provides JDBC, Spring transaction infrastructure, and required dependencies; `spring-boot-starter-aop` provides Spring AOP/AspectJ pointcut support. H2 is the in-memory DB used for the lesson. Gradle 8.x compatible with Spring Boot 3.3 and JDK 17+ fits this example.

**`src/main/resources/schema.sql`**

```sql
CREATE TABLE purchase_order (
    id INT PRIMARY KEY,
    description VARCHAR(120) NOT NULL
);
```

Spring Boot automatically initializes `schema.sql` against embedded H2 at startup. The example needs no web controller or REST endpoint.

### 6.2. `OrderService` — write group and checked exception rollback

**`src/main/java/lesson/xmltx/orders/OrderService.java`**

```java
package lesson.xmltx.orders;

import java.io.IOException;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.support.TransactionSynchronizationManager;

@Service
public class OrderService {
    private final JdbcTemplate jdbc;

    public OrderService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public void createSuccess(int id) {
        showTransaction("order success");

        jdbc.update(
            "INSERT INTO purchase_order(id, description) VALUES (?, ?)",
            id, "created"
        );
    }

    public void createThenFail(int id) throws IOException {
        showTransaction("order failure");

        jdbc.update(
            "INSERT INTO purchase_order(id, description) VALUES (?, ?)",
            id, "should rollback"
        );

        // Checked exception: XML rollback-for must take effect.
        throw new IOException("checked failure");
    }

    private static void showTransaction(String label) {
        System.out.println(label + " txActive=" +
            TransactionSynchronizationManager.isActualTransactionActive() +
            " readOnly=" +
            TransactionSynchronizationManager.isCurrentTransactionReadOnly());
    }
}
```

**There is no `@Transactional` in this service.** Transactions still apply because the XML pointcut matches public methods of `OrderService` and the advisor attaches `ordersTxAdvice`. `showTransaction` is a private helper called from an already-transactional method; the helper does not need separate proxy interception.

If `createThenFail` lacked a checked-exception rollback policy, Spring would normally **commit** by default when the method throws checked `IOException`. The demo proves XML `rollback-for="java.lang.Exception"` changes that decision: the insert from the failing run is rolled back.

### 6.3. `ReportService` — read-only query group

**`src/main/java/lesson/xmltx/reports/ReportService.java`**

```java
package lesson.xmltx.reports;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.support.TransactionSynchronizationManager;

@Service
public class ReportService {
    private final JdbcTemplate jdbc;

    public ReportService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public int findCount() {
        System.out.println("report find txActive=" +
            TransactionSynchronizationManager.isActualTransactionActive() +
            " readOnly=" +
            TransactionSynchronizationManager.isCurrentTransactionReadOnly());

        Integer count = jdbc.queryForObject(
            "SELECT COUNT(*) FROM purchase_order",
            Integer.class
        );
        return count;
    }
}
```

Method `findCount` carries no annotation yet is matched by the `reportsOperations` pointcut. When called from the runner outside any transaction, `reportsTxAdvice` creates a new transaction with `read-only="true"`. Reading `isCurrentTransactionReadOnly()` confirms **Spring's current transaction metadata**; it does not prove H2 rejects every write statement. Do not use this single flag to claim the DB always runs at a specific isolation level.

### 6.4. Main application: load XML and create the matching transaction manager

**`src/main/java/lesson/xmltx/XmlPolicyApplication.java`**

```java
package lesson.xmltx;

import java.io.IOException;

import javax.sql.DataSource;

import lesson.xmltx.orders.OrderService;
import lesson.xmltx.reports.ReportService;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.ImportResource;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;

@SpringBootApplication
@ImportResource("classpath:transaction-policies.xml")
public class XmlPolicyApplication {
    public static void main(String[] args) {
        SpringApplication.run(XmlPolicyApplication.class, args);
    }

    @Bean
    PlatformTransactionManager transactionManager(DataSource dataSource) {
        return new DataSourceTransactionManager(dataSource);
    }

    @Bean
    CommandLineRunner demo(OrderService orders, ReportService reports) {
        return args -> {
            orders.createSuccess(101);
            System.out.println("count after success=" + reports.findCount());

            try {
                orders.createThenFail(102);
            } catch (IOException ex) {
                System.out.println("caught=" + ex.getMessage());
            }

            System.out.println("count after failure=" + reports.findCount());
        };
    }
}
```

**Why does this configuration work?**

- `@SpringBootApplication` scans the two `@Service` classes under `lesson.xmltx`; thus Spring owns the beans and can create proxies.
- `@ImportResource` loads the exact XML file in `src/main/resources`, registering both transaction advices and both advisors.
- `transactionManager` is the bean name referenced by both `<tx:advice>` elements. It uses the same `DataSource` that Boot configured for `JdbcTemplate`.
- `CommandLineRunner` receives the services via dependency injection, so the caller goes through proxies. Avoid `new OrderService(...)` and avoid calling transactional methods via `this.method()` inside the same bean.
- Each `reports.findCount()` runs after the order method has completed through its proxy, so the read occurs after the order transaction commits or rolls back. That allows verifying the final result.

### 6.5. Running the application and comparing results

From the project directory, with JDK 17+ and a compatible Gradle 8.x:

```bash
gradle bootRun
```

If a compatible Gradle Wrapper has been generated, you can run `./gradlew bootRun` on Linux/macOS or `gradlew.bat bootRun` on Windows. Do not use plain `javac` for a project with Spring/H2 libraries outside the JDK; Gradle supplies the classpath.

Ignoring Spring Boot/Gradle startup logs, the lines printed by the program will appear in order:

```text
order success txActive=true readOnly=false
report find txActive=true readOnly=true
count after success=1
order failure txActive=true readOnly=false
caught=checked failure
report find txActive=true readOnly=true
count after failure=1
```

**Explanation of each result:**

1. `createSuccess(101)` gets a read-write transaction opened by the orders advisor; INSERT succeeds and commits. The first report query sees one row.
2. `findCount` gets a new read-only transaction opened by the reports advisor; because the runner has no outer transaction, Spring's flags are `txActive=true readOnly=true`.
3. `createThenFail(102)` inserts id 102 and throws checked `IOException`. The orders advice matches the `rollback-for` `java.lang.Exception` rule so Spring rolls back that method's transaction.
4. The runner catches the exception **outside the proxy**, after the transaction interceptor has handled rollback. The next query still sees one row, proving id 102 was not committed.
5. There are no annotations on either service. The differing behaviors come entirely from **pointcut + advice + transaction manager** in XML.

If you remove only `rollback-for="java.lang.Exception"` from the orders advice and rerun on a fresh H2 DB, an ordinary checked `IOException` does not trigger rollback by default; the row count may increase to 2. This is a way to contrast XML policies, though **not the intended standard configuration of the initial run**.

## 7. Splitting by method name within the same group

One package does not always correspond to one policy. For example, a `customer` group has both queries and writes. When splitting packages is impractical, you can use name-based rules:

```xml
<tx:advice id="customerTxAdvice" transaction-manager="transactionManager">
    <tx:attributes>
        <tx:method name="find*" propagation="REQUIRED" read-only="true"/>
        <tx:method name="get*" propagation="REQUIRED" read-only="true"/>
        <tx:method name="calculate*" propagation="SUPPORTS" read-only="true"/>
        <tx:method name="*" propagation="REQUIRED"
                   rollback-for="java.lang.Exception"/>
    </tx:attributes>
</tx:advice>
```

This is an **independent variation**, not included in the demo project's XML. To apply it, you must create a separate pointcut/advisor for `customer` and ensure it does not overlap the scope of other advisors.

The `name` selector can use `*` as a fallback. However, a method named `getAndCreate` that actually writes data would be treated as read-only if relying solely on the name; the sustainable approach is **designing APIs that reflect their meaning** and adding tests for policy groups. If exception rules or timeouts differ across important cases, split beans or add exact rules rather than a confusing glob.

**`propagation="SUPPORTS"` is not equivalent to `REQUIRED`:** when there is no outer transaction, SUPPORTS does not open a new physical transaction. Therefore, if the goal is to have a real read transaction for snapshot consistency, `REQUIRED` is the option to consider. `read-only="true"` on a SUPPORTS configuration does not turn a method without a physical transaction into a DB transaction.

## 8. What happens when two groups call each other?

A common design mistake is treating each advisor as an "independent" transaction per method. In reality, propagation governs the relationship between transactions:

| Call Flow | With `REQUIRED` in Both Groups | Conclusion |
| --- | --- | --- |
| Runner → `orders.createSuccess` | Order opens a read-write transaction | Commits when the order proxy finishes |
| Runner → `reports.findCount` | Report opens a read-only transaction | Queries inside the new read transaction |
| Order method → report method through Spring proxy | Report usually **joins the existing read-write transaction** | `read-only="true"` on the report method does not turn an already-open physical transaction into read-only |
| Report method → order method through Spring proxy | Order usually joins the existing read transaction | Inner read-write config is not guaranteed to "upgrade" the physical transaction; avoid writes inside a read scope |
| Outer method → inner method on same bean via `this.inner()` | Inner call bypasses the AOP proxy | XML advisor for inner does not run separately; may still use the outer transaction |

If the reports group genuinely needs a separate snapshot isolated from an active write transaction, you may need different boundaries, an appropriate manager/propagation, and accept the corresponding resource cost. Do not add `REQUIRES_NEW` out of habit, as it can commit independently even when the outer use case rolls back, consume extra connections, and complicate business invariants.

Similarly, if code makes HTTP calls, sends emails, uses queues, or writes to another DB, a local transaction manager does not coordinate those resources automatically. Configuring multiple XML policies **is not a cross-system atomicity solution**.

## 9. How to choose pointcuts so groups do not overlap

### 9.1. Match by stable package

Consider the structure:

```text
lesson.xmltx.orders.OrderService
lesson.xmltx.orders.internal.ValidationService
lesson.xmltx.reports.ReportService
lesson.xmltx.shared.AuditService
```

`execution(* lesson.xmltx.orders.*Service.*(..))` matches `*Service` classes directly in the `orders` package, and does not automatically match `orders.internal`. `execution(* lesson.xmltx.orders..*Service.*(..))` can also match subpackages. Decide whether `ValidationService` should be a transaction entry point or simply a helper running inside `OrderService`'s transaction; do not broaden pointcuts just to "cover everything."

**Verify with tests** that critical methods are matched by the intended advice, especially after moving packages, renaming services, or splitting classes.

### 9.2. Avoid multiple advisors matching the same call

If you add a catch-all pointcut like `execution(* lesson.xmltx..*Service.*(..))` and attach another advice, `OrderService` could be intercepted by both the catch-all advisor and the orders-group advisor. Depending on advice order and propagation, this can produce multiple logical scopes, join the same physical transaction, or open an independent new transaction. **Do not assume an advisor declared later overrides an earlier advisor.**

Safe practices:

1. Design package/class patterns so policy groups do not intersect.
2. If multiple advices are unavoidable, define `order` on `<aop:advisor>` and understand transaction-boundary semantics; test exceptions/commits thoroughly.
3. Use a single transaction policy to own the use-case boundary; only add a second policy for a clear purpose, and avoid accidentally stacking `REQUIRES_NEW`.

### 9.3. Narrow scope avoids applying transactions to controllers

An overly broad pointcut can proxy controllers, utilities, mappers, or long-running orchestrators. As a result, transactions start too early, hold DB connections while calling external services, increase lock contention, and obscure the actual commit scope.

Place **transaction boundaries** at application/service use cases; group-based pointcuts are just the tool to express those boundaries in XML configuration.

## 10. If you want to configure the entire transaction manager in XML

In the Spring Boot example, `DataSource` is auto-configured and `transactionManager` is a Java bean to keep the lesson concise and easy to run. In a plain Spring Framework application, you can also declare the manager in XML, for example:

```xml
<bean id="transactionManager"
      class="org.springframework.jdbc.datasource.DataSourceTransactionManager">
    <property name="dataSource" ref="dataSource"/>
</bean>
```

This is only a **configuration fragment**: you still need a valid `dataSource` bean, a Spring context, a JDBC driver, and service beans in the same context. Do not add the bean above to the demo project while the Java `transactionManager` bean already exists; two definitions with the same name will conflict or depend on bean-overriding rules.

With a differently named manager, update all corresponding XML references:

```xml
<tx:advice id="ordersTxAdvice" transaction-manager="ordersTransactionManager">
    <tx:attributes>
        <tx:method name="*" rollback-for="java.lang.Exception"/>
    </tx:attributes>
</tx:advice>
```

If the system has two `DataSource` beans, each manager must be wired to the right resource. Assigning a service to a "different group" while the advisor still references the old DB's manager will prevent reads/writes from participating as intended. Two local managers also do not automatically combine into a distributed atomic transaction.

## 11. Common XML configuration mistakes

**Mistake 1 — `<tx:advice>` without an advisor.** The advice declares a policy, but it is not connected to any pointcut so no calls are intercepted by it. You need `<aop:advisor advice-ref="..." pointcut-ref="..."/>` and Spring AOP runtime.

**Mistake 2 — Wrong package or class name in the pointcut.** The XML may still load, yet the service does not match so there is no transaction. Check full package names, method/class names, matchers, and proxies.

**Mistake 3 — Only configuring `<tx:annotation-driven/>` and expecting XML `tx:method` rules to apply.** Annotation-driven only processes annotations; for group-based XML rules you need `tx:advice`, pointcuts, and advisors.

**Mistake 4 — Thinking `name="find*"` matches methods in every package.** `tx:method` only selects attributes for calls that already satisfied the pointcut. Verify each filtering layer.

**Mistake 5 — Calling the service via `new` or `this.inner()`.** With default proxy mode, the call bypasses the corresponding proxy, so the XML advisor does not run separately. Call through the Spring-injected bean; if the outer call already has a transaction, the inner method may simply join that transaction.

**Mistake 6 — Putting policies on `private`/`final` methods.** Class-based proxies cannot override private/final methods to intercept them. Choose public non-final methods as transaction entry points or redesign bean boundaries.

**Mistake 7 — Believing `read-only="true"` is an absolute write lock.** It is a hint or level of enforcement depending on the driver/manager/DB. Do not use it in place of constraints, DB permissions, and testing.

**Mistake 8 — Catching a checked exception without rethrowing.** `rollback-for` only works if the transaction interceptor sees the matching exception or the transaction has been marked rollback-only. Swallowing an error and returning can lead to commit.

**Mistake 9 — The same method matching multiple advisors with different policies.** They can nest, with no "last advisor wins" semantics. Control scope, order, and propagation.

**Mistake 10 — Choosing the wrong transaction manager.** A service using a `JdbcTemplate` for DB A while the advice opens a transaction on DB B will not yield atomic results for DB A. Check the actual `DataSource`, manager, and repository beans.

**Mistake 11 — Tests annotated with `@Transactional` on the outside.** Spring Test may roll back by default at the end of a test, hiding the fact that the service fails to roll back properly at runtime. Check DB state **after the method scope ends**, avoiding test transactions skewing the signal.

**Mistake 12 — Transactions wrapping network calls and overly long batches.** A policy using one timeout for all methods can cause large jobs to time out while short requests work fine. Split boundaries per chunk or use case; do not just raise a global timeout.

## 12. Testing and observing active policies

To verify **the right group, right policy, right data**, check three layers:

1. **Pointcut and proxy:** is the bean injected by Spring, do real calls pass through the proxy, and which advisors match? Is there self-invocation or an unproxyable class/method?
2. **Transaction attributes:** inside the method, do `TransactionSynchronizationManager.isActualTransactionActive()` and `isCurrentTransactionReadOnly()` match the test intent? Are timeout/propagation right when the method opens a new transaction?
3. **Data outcome:** in a transaction that performs an INSERT and then throws an error, read the DB back from an outer scope after the method ends; did it roll back properly according to checked/unchecked rules?

You can temporarily enable transaction logs to observe Spring creating/completing transactions:

```properties
logging.level.org.springframework.transaction.interceptor=TRACE
logging.level.org.springframework.jdbc.datasource.DataSourceTransactionManager=DEBUG
```

These are debug-support properties and do not need to be added to the project to produce the demo output shown earlier. Avoid using only the log message "Getting transaction for method" as proof that every DB operation joined the transaction; SQL results after commit/rollback remain the strongest check.

Suggested tests for production code:

- **Orders group:** insert succeeds; RuntimeException rolls back; checked exceptions per policy roll back; intentionally swallowed exceptions may commit.
- **Reports group:** normal reads; Spring read-only flag when called directly; do not infer the DB forbids writes.
- **Cross-group flows:** order calls report and report calls order via proxy; confirm `REQUIRED` propagation does not change the read-only state of an outer physical transaction.
- **Boundaries:** self-invocation, beans created with `new`, final/private methods, or classes moved to new packages; ensure tests detect lost interception.
- **Overlapping advisors:** if actually present, test advice/transaction manager order and rollback behavior in each scope.

## 13. Pre-deployment decision checklist

Ask these questions when adding a new service to XML:

- Does the new service share the same **business intent** and transaction policy as an existing group?
- Which pointcut matches its methods? Could it accidentally match other services or miss subpackages?
- Which `tx:advice` applies? Are the `tx:method name="*"` fallback, rollback rules, and timeout correct?
- Does another advisor also match those methods? If so, is that intentional design or a bug?
- Are methods called through the Spring proxy and using the right transaction manager/resource?
- Does the method join an outer transaction or open a new one? Do `read-only`, timeout, and isolation actually take effect in that case?
- Are there tests checking database state after commit/rollback with failures occurring between operations?

**Principle:** split policies by **work type and resource boundaries**, use pointcuts to isolate the right group, use `tx:advice` to describe behavior, and test actual DB outcomes.

## 14. Self-check questions

**Question 1.** Is `<tx:advice>` alone enough for all services to get transactions automatically?

**Answer:** No. You also need an advisor/pointcut connecting to actual calls through a Spring AOP proxy, an appropriate manager, and beans managed in the Spring context.

**Question 2.** Two services both have a `process()` method, yet the orders group needs checked-exception rollback while the reports group is read-only. Can you separate them using `tx:method name="process"` inside a single shared advice?

**Answer:** A shared method-name rule cannot distinguish the groups; use package/class-based pointcuts and two separate advices (or organize service APIs/rules appropriately) so each group has a clear policy.

**Question 3.** In the demo, why does `IOException` from `createThenFail` trigger a rollback?

**Answer:** Because the XML orders advice matches the method via its pointcut and specifies `rollback-for="java.lang.Exception"`. The checked `IOException` escapes the method through the proxy and is rolled back by the transaction interceptor.

**Question 4.** `ReportService.findCount()` has `read-only="true"`. If called inside an existing read-write transaction of the orders group, does the physical transaction become read-only?

**Answer:** No. With `REQUIRED`, the report method typically joins the existing transaction and does not overwrite the characteristics of the outer physical transaction.

**Question 5.** Does adding a catch-all advisor matching every `*Service` with `REQUIRES_NEW` make "the second policy replace the old policy"?

**Answer:** No. Multiple advices can run around a single call, creating nested transaction scopes depending on order/propagation. You must actively control match points and ordering; avoid unintentional overlapping advisors.

**Question 6.** Should you configure `read-only="true"` for every `find*` method and treat that as a guarantee of data safety?

**Answer:** No. Read-only has different effects depending on the manager/DB and is only one part of the design; proper DB permissions, constraints, and API design are required.

## 15. References

- Spring Framework — Example of Declarative Transaction Implementation: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/first-example.html
- Spring Framework — Understanding Declarative Transaction Implementation: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html
- Spring Framework — `<tx:advice/>` Settings: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/txadvice-settings.html
- Spring Framework — Rolling Back a Declarative Transaction: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html
- Spring Framework — Proxying Mechanisms: https://docs.spring.io/spring-framework/reference/core/aop/proxying.html

**Remember:** XML can divide transaction policies into clear groups: **pointcuts decide who is intercepted, advices decide how transactions are handled, and managers decide which resources are committed/rolled back**. When a method is called within an existing transaction, propagation determines to what extent the policy actually takes effect.
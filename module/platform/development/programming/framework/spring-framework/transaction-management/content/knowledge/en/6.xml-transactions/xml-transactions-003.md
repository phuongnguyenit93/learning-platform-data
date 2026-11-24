# Attaching Transaction Advice to a Pointcut with AOP

## 1. Problem and Objective

In Spring Framework, **declarative transaction management** lets you declare transaction boundaries outside of business code. In addition to using `@Transactional`, you can configure all transactions with **XML + Spring AOP**. A service does not need any annotations to be wrapped in a transaction by Spring if the AOP configuration is accurate and calls go through the Spring-managed bean.

This lesson focuses on three components that must not be confused:

- **Transaction advice:** `<tx:advice>` defines how transactions are managed and sets rules for propagation, isolation, read-only, timeout, and rollback for methods.
- **Pointcut:** `<aop:pointcut>` uses an AspectJ `execution(...)` expression to select **which method executions** are intercepted.
- **Advisor:** `<aop:advisor>` **connects** the transaction advice to the pointcut via `advice-ref` and `pointcut-ref`.

There is also a **transaction manager** (for example `DataSourceTransactionManager`) that performs commit/rollback against the database. If the manager is missing or the service uses the wrong datasource, the advisor cannot guarantee atomicity on its own.

Visualization:

~~~text
           applicationContext.xml
    +------------------------------------+
    | <tx:advice id="txAdvice">          |
    |   <tx:method name="transfer".../>  |
    | </tx:advice>                       |
    |              |                     |
    |              v                     |
    | <aop:advisor                       |
    |   advice-ref="txAdvice"            |
    |   pointcut-ref="servicePointcut"/> |
    |              ^                     |
    |              |                     |
    | <aop:pointcut id="servicePointcut" |
    |   expression="execution(...)"/>    |
    +------------------------------------+
                  |
                  v
          Spring AOP proxy
                  |
    caller --> proxy.transfer(...)
                  |
          BEGIN or join transaction
                  |
              target method
                  |
           COMMIT or ROLLBACK
~~~

**Pointcut** is the "where?" condition, **advice** is the "what to do?" rule, and **advisor** is the link "where to apply the rule?". Spring AOP is **proxy**-based by default; call sites must go through the container-managed proxy.

## 2. Selecting methods and attaching advice: two separate matches

Consider a service that transfers 200 from account A with 1,000 to account B with 500. Both SQL statements—debiting A and crediting B—must succeed together or fail together.

Conceptual configuration:

~~~xml
<tx:advice id="txAdvice" transaction-manager="txManager">
    <tx:attributes>
        <tx:method name="transfer" propagation="REQUIRED"/>
    </tx:attributes>
</tx:advice>

<aop:config>
    <aop:pointcut id="transferOperation"
        expression="execution(* com.example.xmltx.TransferService.transfer(..))"/>
    <aop:advisor advice-ref="txAdvice"
                 pointcut-ref="transferOperation"/>
</aop:config>
~~~

For the transaction to be applied properly:

1. The **pointcut** must match the `TransferService.transfer(...)` method called through the proxy.
2. Inside `txAdvice`, there must be a `tx:method` matching the **method name** `transfer` to select the transaction attributes.
3. `aop:advisor` must point to the exact IDs of both the advice and the pointcut.
4. The advice must point to the right transaction manager, and the manager must manage the right resource.

These two selection mechanisms are **different**. `execution(...)` checks Java signatures and types; `tx:method name="transfer"` checks the method name to assign a policy. An advice containing only `<tx:method name="find*"/>` provides no rule for `transfer`. An advice containing `<tx:method name="*"/>` still cannot "rescue" a call that does not match the pointcut.

Unlike `<aop:before>` used for logging, `tx:advice` provides a specialized transaction interceptor with **around** behavior: preparing the transaction, invoking the method, committing on normal completion, or rolling back according to rules when an exception occurs. There is no need to write a custom `@Around` calling JDBC `commit()`.

## 3. Complete runnable example with Java 17 and Maven

We create a plain Spring Framework application without Spring Boot, using Spring XML, Spring JDBC, and in-memory H2. The example chooses released versions: Spring Framework **6.2.9**, AspectJ Weaver **1.9.24**, and H2 **2.3.232**. The AOP/transaction concepts still apply when a project uses other compatible versions.

Directory structure:

~~~text
xml-transaction-lab/
├── pom.xml
└── src/
    └── main/
        ├── java/com/example/xmltx/
        │   ├── TransferService.java
        │   └── XmlTxDemo.java
        └── resources/
            └── applicationContext.xml
~~~

### 3.1. The pom.xml file

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>xml-transaction-lab</artifactId>
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
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <version>6.2.9</version>
        </dependency>
        <dependency>
            <groupId>org.aspectj</groupId>
            <artifactId>aspectjweaver</artifactId>
            <version>1.9.24</version>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <version>2.3.232</version>
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
                <version>3.5.0</version>
                <configuration>
                    <mainClass>com.example.xmltx.XmlTxDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`spring-context` provides the Spring container and the required AOP/bean modules via transitive dependencies; `spring-jdbc` provides `JdbcTemplate` along with the transaction manager for JDBC; `aspectjweaver` enables parsing AspectJ expressions in Spring AOP. **Adding `aspectjweaver` does not mean the application is using bytecode weaving**: this lesson still operates via proxies. H2 is the test database running in JVM memory.

### 3.2. Java service without transaction annotations

File `src/main/java/com/example/xmltx/TransferService.java`:

~~~java
package com.example.xmltx;

import org.springframework.jdbc.core.JdbcTemplate;

public class TransferService {
    private final JdbcTemplate jdbc;

    public TransferService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public void transfer(long fromId, long toId,
                         long amount, boolean failAfterDebit) {
        if (amount <= 0 || fromId == toId) {
            throw new IllegalArgumentException("Invalid transfer");
        }

        int debited = jdbc.update(
            "UPDATE account SET balance = balance - ? " +
            "WHERE id = ? AND balance >= ?",
            amount, fromId, amount
        );
        if (debited != 1) {
            throw new IllegalStateException(
                "Source missing or insufficient balance"
            );
        }

        // For learning purposes only: error between two UPDATEs.
        if (failAfterDebit) {
            throw new IllegalStateException(
                "simulated error after debit"
            );
        }

        int credited = jdbc.update(
            "UPDATE account SET balance = balance + ? WHERE id = ?",
            amount, toId
        );
        if (credited != 1) {
            throw new IllegalStateException(
                "Destination account does not exist"
            );
        }
    }
}
~~~

The service contains only constructor injection and business code. It **does not use `@Transactional`**. If the XML is applied properly, both `UPDATE` statements participate in the same transaction. The intentional error happens **after the debit statement on A has already run**, so rollback must restore A back to 1,000; this is the real test of the transaction advice.

`JdbcTemplate.update` returns the number of updated rows. The checks for source, destination, and `balance >= ?` prevent accepting a transfer that misses a row or overdraws the balance. The demo uses integer units for currency and is not a production financial design.

### 3.3. Complete XML: transaction manager, tx:advice, pointcut, advisor

File `src/main/resources/applicationContext.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xmlns:tx="http://www.springframework.org/schema/tx"
       xmlns:aop="http://www.springframework.org/schema/aop"
       xsi:schemaLocation="
           http://www.springframework.org/schema/beans
           https://www.springframework.org/schema/beans/spring-beans.xsd
           http://www.springframework.org/schema/tx
           https://www.springframework.org/schema/tx/spring-tx.xsd
           http://www.springframework.org/schema/aop
           https://www.springframework.org/schema/aop/spring-aop.xsd">

    <!-- Same DataSource used in both service and transaction. -->
    <bean id="dataSource"
          class="org.springframework.jdbc.datasource.DriverManagerDataSource">
        <property name="driverClassName" value="org.h2.Driver"/>
        <property name="url"
                  value="jdbc:h2:mem:xml_tx_lab;DB_CLOSE_DELAY=-1"/>
        <property name="username" value="sa"/>
        <property name="password" value=""/>
    </bean>

    <bean id="jdbcTemplate"
          class="org.springframework.jdbc.core.JdbcTemplate">
        <constructor-arg ref="dataSource"/>
    </bean>

    <bean id="txManager"
          class="org.springframework.jdbc.datasource.DataSourceTransactionManager">
        <constructor-arg ref="dataSource"/>
    </bean>

    <bean id="transferService"
          class="com.example.xmltx.TransferService">
        <constructor-arg ref="jdbcTemplate"/>
    </bean>

    <!-- Transaction rule for method named transfer. -->
    <tx:advice id="txAdvice" transaction-manager="txManager">
        <tx:attributes>
            <tx:method name="transfer" propagation="REQUIRED"
                       isolation="DEFAULT"/>
        </tx:attributes>
    </tx:advice>

    <!-- AOP pointcut and advisor attaching transaction advice. -->
    <aop:config proxy-target-class="true">
        <aop:pointcut id="transferOperation"
            expression="execution(public * com.example.xmltx.TransferService.transfer(..))"/>
        <aop:advisor pointcut-ref="transferOperation"
                     advice-ref="txAdvice"/>
    </aop:config>
</beans>
~~~

Reading each part:

1. `dataSource` uses in-memory H2. `DriverManagerDataSource` fits a demo lesson, whereas real environments should use a connection pool.
2. `jdbcTemplate` uses `dataSource` to access data.
3. `txManager` is a `DataSourceTransactionManager`, **managing the same `dataSource` bean**. The transaction advice references the exact ID `txManager` via `transaction-manager="txManager"`.
4. `transferService` is created by the Spring container. If a caller manually invokes `new TransferService(...)`, it will not go through the AOP proxy.
5. `txAdvice` has the rule `name="transfer"`: in a transaction context, `REQUIRED` joins an existing transaction or creates a new one; `DEFAULT` uses the database's default isolation.
6. `transferOperation` is a pointcut selecting the exact public method `transfer(...)` on the fully qualified class.
7. `aop:advisor` attaches `txAdvice` to `transferOperation`. This is the core wiring step of the lesson.
8. `proxy-target-class="true"` requests a class-based proxy, allowing the bean to be retrieved by `TransferService.class`. Neither the class nor the method may be `final` if the class proxy is to intercept it.

**Important to remember:** `<tx:advice>` is an element from the `tx` namespace at the `beans` level, whereas `<aop:pointcut>` and `<aop:advisor>` go inside `<aop:config>`. The IDs are **bean/configuration element names**, not Java class names.

### 3.4. Program observing commit and rollback

File `src/main/java/com/example/xmltx/XmlTxDemo.java`:

~~~java
package com.example.xmltx;

import org.springframework.aop.support.AopUtils;
import org.springframework.context.support.ClassPathXmlApplicationContext;
import org.springframework.jdbc.core.JdbcTemplate;

public class XmlTxDemo {
    public static void main(String[] args) {
        try (var context =
                 new ClassPathXmlApplicationContext("applicationContext.xml")) {
            JdbcTemplate jdbc = context.getBean(
                "jdbcTemplate", JdbcTemplate.class
            );
            TransferService service = context.getBean(
                "transferService", TransferService.class
            );

            if (!AopUtils.isAopProxy(service)) {
                throw new AssertionError("Service is not AOP-proxied");
            }

            jdbc.execute(
                "CREATE TABLE account (" +
                "id BIGINT PRIMARY KEY, " +
                "balance BIGINT NOT NULL CHECK (balance >= 0))"
            );
            jdbc.update(
                "INSERT INTO account(id, balance) VALUES (?, ?)",
                1L, 1000L
            );
            jdbc.update(
                "INSERT INTO account(id, balance) VALUES (?, ?)",
                2L, 500L
            );

            printBalances(jdbc, "Initial");

            try {
                service.transfer(1L, 2L, 200L, true);
                throw new AssertionError("Expected failure");
            } catch (IllegalStateException expected) {
                if (!"simulated error after debit"
                        .equals(expected.getMessage())) {
                    throw expected;
                }
                System.out.println("Caught: " + expected.getMessage());
            }

            assertBalances(jdbc, 1000L, 500L);
            printBalances(jdbc, "After rollback");

            service.transfer(1L, 2L, 200L, false);
            assertBalances(jdbc, 800L, 700L);
            printBalances(jdbc, "After commit");
        }
    }

    private static long balance(JdbcTemplate jdbc, long id) {
        Long v = jdbc.queryForObject(
            "SELECT balance FROM account WHERE id = ?",
            Long.class, id
        );
        if (v == null) {
            throw new IllegalStateException("Missing account " + id);
        }
        return v;
    }

    private static void printBalances(JdbcTemplate jdbc, String label) {
        System.out.printf(
            "%s: A=%d, B=%d%n",
            label, balance(jdbc, 1L), balance(jdbc, 2L)
        );
    }

    private static void assertBalances(JdbcTemplate jdbc,
                                       long expectedA, long expectedB) {
        long a = balance(jdbc, 1L);
        long b = balance(jdbc, 2L);
        if (a != expectedA || b != expectedB) {
            throw new AssertionError(
                "Expected A=" + expectedA + ", B=" + expectedB +
                "; actual A=" + a + ", B=" + b
            );
        }
    }
}
~~~

`AopUtils.isAopProxy(service)` checks whether the bean has a proxy, but **checking for a proxy alone is not enough** to prove that the specific `transfer` method is transaction-advised. An exception test occurring **after a successful SQL write**, followed by reading the data back after the service call, is the true proof.

### 3.5. Running with Maven

Requires JDK 17+ and Maven 3.9+:

~~~bash
java -version
mvn -version
mvn -q compile exec:java
~~~

If Maven downloads dependencies and the application runs properly, the lines printed by the program will be:

~~~text
Initial: A=1000, B=500
Caught: simulated error after debit
After rollback: A=1000, B=500
After commit: A=800, B=700
~~~

Timing, Maven output, and internal logs may vary; those four lines are the output **defined by the Java code**. The `assertBalances` checks will throw `AssertionError` if the data does not match.

During the failing attempt, A was debited to 800 **inside the transaction** before the exception occurred. After the advice triggers rollback, reading from outside the method shows A restored to 1,000. On the next call without error, both statements run and the transaction commits: A = 800, B = 700.

## 4. Full breakdown of the AOP call

Flow for `service.transfer(1L, 2L, 200L, true)`:

~~~text
XmlTxDemo retrieves transferService from Spring context
             |
             v
Spring AOP proxy receives call to transfer(...)
             |
             +-- Pointcut execution(...) matches
             +-- Advisor leads to txAdvice
             +-- tx:method name="transfer" selects rule
             |
             v
TransactionInterceptor calls txManager
             |
             +-- REQUIRED: starts a new transaction
             |             (since demo has no outer transaction)
             v
Target TransferService.transfer(...)
             |
             +-- JdbcTemplate UPDATEs account A
             |      (A=800, not yet committed)
             +-- throws IllegalStateException
             |
             v
Interceptor determines exception matches rollback rule
             |
             v
DataSourceTransactionManager.rollback(...)
             |
             v
Caller receives exception; reading again shows A=1000, B=500
~~~

With `failAfterDebit=false`, the target returns normally and the transaction interceptor requests commit.

In real applications, `REQUIRED` can also **join an existing transaction**. In that case, when the service method returns is not necessarily when commit happens: the outer transaction boundary decides. The JDBC transaction manager manages the connection and transaction context; `JdbcTemplate` participates because it uses the same `DataSource`.

**Relationship to atomicity:** the advisor/pointcut only decides **whether a transaction wraps the method**; the database engine actually executes commit/rollback, logging, and locking. AOP does not replace database ACID properties.

## 5. Understanding `execution(...)` pointcut syntax

Expression in XML:

~~~xml
expression="execution(public * com.example.xmltx.TransferService.transfer(..))"
~~~

| Part | Meaning |
| --- | --- |
| `execution(...)` | Selects join points at method execution. |
| `public` | Public methods only. |
| `*` | Any return type, including `void`. |
| `com.example.xmltx.TransferService` | Fully qualified Java class name. |
| `transfer` | Method name to intercept. |
| `(..)` | Any number and types of parameters. |

Renaming a package, class, or method without updating the expression will prevent the advisor from matching as intended.

Other example pointcuts, **for illustration only—do not add them simultaneously to the lab configuration**:

~~~xml
<!-- All public methods of classes named *Service in the service package -->
<aop:pointcut id="serviceMethods"
    expression="execution(public * com.example.app.service.*Service.*(..))"/>

<!-- Including subpackages under service -->
<aop:pointcut id="nestedServices"
    expression="execution(* com.example.app.service..*Service.*(..))"/>

<!-- Only methods named save* in a single package level -->
<aop:pointcut id="saveOperations"
    expression="execution(* com.example.app.service.*.save*(..))"/>
~~~

`..` in the package segment can span multiple subpackage levels; `(..)` in the parameter list means accept any parameters. Do not accidentally include repository, utility, and getter classes when business logic only needs transactions at the service layer.

If you need to combine conditions in an XML attribute, use the AspectJ keyword `and` or escape `&&` as `&amp;&amp;` so the XML remains valid.

### Interface proxies vs class proxies

Spring AOP can create a **JDK dynamic proxy** when a bean has an interface, or a **class-based proxy**. In the lab, `proxy-target-class="true"` is used to proxy the `TransferService` class so callers can retrieve the bean by that class. With a JDK proxy, callers should retrieve the bean through the interface implemented by the proxy; casting to the implementation class may fail.

Regardless of proxy type, self-invocation (`this.someMethod()`) inside the same target **does not pass through the proxy** in standard Spring AOP. Final classes/methods are also a limitation for subclassing-based proxies. When choosing a pointcut, always cross-check against the actual proxy type and call path.

## 6. Transaction attributes: what can be configured in `tx:method`?

A large service may have multiple method rules. Example of **replacing** `txAdvice` in the lab with the configuration:

~~~xml
<tx:advice id="txAdvice" transaction-manager="txManager">
    <tx:attributes>
        <tx:method name="find*" read-only="true"
                   propagation="SUPPORTS"/>
        <tx:method name="get*" read-only="true"
                   propagation="SUPPORTS"/>
        <tx:method name="transfer*" propagation="REQUIRED"
                   rollback-for="java.lang.Exception"/>
        <tx:method name="*" propagation="REQUIRED"/>
    </tx:attributes>
</tx:advice>
~~~

| Attribute | Role |
| --- | --- |
| `name` | Method name pattern (`transfer*`, `get*`, `*`); this is a rule **inside the advice**. |
| `propagation` | How to join or create a transaction, e.g. `REQUIRED` and `SUPPORTS`. |
| `isolation` | Isolation level requested when a new transaction is created, e.g. `DEFAULT`, `READ_COMMITTED`. |
| `read-only` | Hint for the transaction manager/driver/engine; not a guarantee blocking every UPDATE statement. |
| `rollback-for` | Additional exception types requiring rollback, especially checked exceptions. |
| `no-rollback-for` | Exception types that do not trigger rollback despite failure; use only when business logic permits. |
| `timeout` | Transaction time limit when supported by the manager/engine. |

Spring rolls back by default when a `RuntimeException` or `Error` escapes a transactional method; checked exceptions do not trigger rollback by default. If business logic needs rollback on `IOException`, configure `rollback-for="java.io.IOException"` or an appropriate parent type. Do not add `rollback-for="java.lang.Exception"` merely to "be safe about everything": clearly decide the desired state when a checked exception occurs.

**Two-level selection note:** `name="get*"` does not automatically add `getBalance()` to the pointcut. If the current pointcut only matches `transfer`, getters remain outside that advisor even if the advice declares a `get*` rule. Conversely, a pointcut may match a method while no advice rule matches the method name.

**Propagation:** `REQUIRED` (default) joins an existing transaction if present, or creates a new one. `SUPPORTS` joins if one exists, otherwise does not create a transaction. `REQUIRES_NEW` creates an independent transaction (when supported by the manager); independent commits can break overall atomicity if misused in a transfer use case.

## 7. XML AOP advice vs `tx:annotation-driven` configuration

**The configuration under study** explicitly defines a pointcut and advisor:

~~~xml
<tx:advice id="txAdvice" transaction-manager="txManager">
    <tx:attributes>
        <tx:method name="transfer" propagation="REQUIRED"/>
    </tx:attributes>
</tx:advice>
<aop:config proxy-target-class="true">
    <aop:pointcut id="transferOperation"
        expression="execution(public * com.example.xmltx.TransferService.transfer(..))"/>
    <aop:advisor pointcut-ref="transferOperation"
                 advice-ref="txAdvice"/>
</aop:config>
~~~

**Annotation-based configuration** is a different mechanism:

~~~xml
<tx:annotation-driven transaction-manager="txManager"/>
~~~

~~~java
@Transactional
public void transfer(/* parameters */) {
    // Method belonging to a Spring bean.
}
~~~

The Java annotation snippet above only illustrates the idea and is not a standalone compilable program. With `tx:annotation-driven`, Spring reads transaction attributes from `@Transactional`. With `tx:advice + aop:advisor`, Spring uses the pointcut and XML rules; **the Java service can have no annotations at all**.

Do not casually enable both mechanisms on the same service: advisor ordering and multi-layer transaction wrapping can cause confusing behavior. When a system already uses XML transaction advice, establish the source of truth for transaction policies before adding `@Transactional` or `tx:annotation-driven`.

## 8. Trying XML changes to confirm the advisor works

Only perform these counter-tests in a **copy of the lab**:

| Change | Expected Result / Meaning |
| --- | --- |
| Remove `<aop:advisor .../>`, keep `txAdvice` | Advice exists but is not wired to the pointcut; `transfer` has no transaction from that advisor. |
| Change the pointcut to a nonexistent method name | Does not match `transfer`, so the call may not be proxied by this advisor. |
| Keep the pointcut but change `tx:method name="transfer"` to only `name="find*"` | The call matches the pointcut but lacks a transaction attribute for `transfer`. |
| Restore standard XML | Failure after UPDATE A is rolled back; A = 1,000, B = 500. |
| Broaden the pointcut to the entire service layer | More methods may be selected; inspect each rule and business boundary individually. |

**Caution in counter-tests:** `XmlTxDemo` deliberately checks `AopUtils.isAopProxy(service)`. If removing the advisor removes the proxy, the program stops before running SQL. To see the auto-commit consequence firsthand, temporarily remove that proxy check only in a lab copy and rerun; then restore both the assertion and the advisor. In the lab's H2 setup, if the first `UPDATE` commits individually before the exception, A remains 800, B = 500, and the post-error check fails. Never run this kind of experiment on real data.

Do not use successful context startup alone as proof that transactions work. A good test must trigger an error **after at least one UPDATE**, then read the database **after the proxy call completes**.

## 9. Common errors and root-cause fixes

### 9.1. Wrong ID or omitting `transaction-manager`

`transaction-manager="txManager"` must point to the right transaction manager bean. If this attribute is omitted, the default manager name looked up by XML transaction advice is `transactionManager`. In the lab the bean is named `txManager`, so that reference cannot be omitted. Use `DataSourceTransactionManager` with the **same DataSource** that `JdbcTemplate` uses.

### 9.2. Missing AOP dependency or XML namespace

`<tx:advice>` requires the `tx` namespace and `spring-tx.xsd` schema; `<aop:config>` requires the `aop` namespace and `spring-aop.xsd` schema. The `execution(...)` expression requires AspectJ pointcut parsing support. XML resolution failures, missing classes, or pointcut parse errors usually come from wrong namespaces, classpath, dependencies, or expressions.

### 9.3. Advice, pointcut, and advisor do not match

When transactions fail to activate, check **all at once** the class/method name in the pointcut, the method name in `tx:method`, `pointcut-ref`, `advice-ref`, the transaction manager, and the proxy path. This is a classic mistake when someone declares transaction advice but forgets to attach the advisor.

### 9.4. Creating the service with `new` or self-invocation

~~~java
// Illustrating bypassing the Spring AOP proxy; not a file from the lab.
TransferService s = new TransferService(jdbc);
s.transfer(1L, 2L, 200L, true);
~~~

Using `new` creates an instance outside the container, so advice is not applied through a proxy. Similarly, calling `this.transfer(...)` from another method in the same target usually bypasses the interceptor. Let another bean invoke the public service method through Spring.

### 9.5. Swallowing exceptions mid-transaction

If a method catches `RuntimeException` after writing SQL and finishes normally, the advice may commit intermediate data if the transaction has not been marked rollback-only. In practice you must rethrow the exception or explicitly mark rollback according to business policy. Do not assume "having an exception inside a try-catch" is enough.

### 9.6. Confusing `read-only` and `isolation`

`read-only="true"` is primarily an attribute/hint that the transaction manager and driver/engine may leverage; it does not replace database permissions. `isolation="READ_COMMITTED"` only requests an isolation level when opening a new transaction; if the method joins an existing transaction, you cannot assume it changes the active isolation level. Locking/MVCC behaviors also depend on the database.

### 9.7. Transactions outside the database

A local JDBC transaction does not automatically undo emails, HTTP calls, published messages, or writes in another database. If a use case must coordinate multiple resources, design explicitly—such as transactional outbox, idempotency, or saga where appropriate. An AOP advisor does not automatically turn a single-resource transaction into a distributed transaction.

## 10. Checking and debugging existing systems

Beyond the lab run, useful checks in a real application include:

1. Verify the bean is retrieved from the right Spring application context and is proxied if needed: `AopUtils.isAopProxy(bean)`.
2. Place a breakpoint in the service method; observe whether the caller came through a proxy or called directly via `this/new`.
3. Check that the pointcut matches the signature (right package, class, method name, public/final), then check that `tx:method` matches the name.
4. Confirm the transaction manager referenced by the advice and the service's `DataSource` belong to the same resource managed by the manager.
5. In a test environment, you can inspect `TransactionSynchronizationManager.isActualTransactionActive()` inside the method; this is a debug signal, not a substitute for a rollback test.
6. Intentionally throw an exception after the first write statement; **read the value again from outside the transaction** after the proxy finishes. If the original data is restored, you have proof of real rollback.
7. When multiple advisors/aspects apply to one method, check advice order (`order`) and transaction boundaries. Do not guess based solely on proxy names.

A proxy may exist while a specific method does not yet have `txAdvice` applied. Therefore **rollback results after an error are the decisive test**.

## 11. Self-check

1. **Can you declare `tx:advice` and `aop:pointcut` without declaring `aop:advisor`?** — The components are not yet connected; that configuration does not automatically apply transactions to methods.
2. **How does the `execution(...)` pointcut differ from `tx:method name="..."`?** — The pointcut selects method invocations by signature; `tx:method` selects transaction attributes based on the method name already handled by the advice.
3. **Who calls commit or rollback?** — The transaction interceptor coordinating with the transaction manager, such as `DataSourceTransactionManager`.
4. **Why doesn't the Java class in the example need `@Transactional`?** — The XML transaction advice + AOP advisor already describes the policy wrapping calls through the Spring proxy.
5. **If you change only the Java package and forget the pointcut, what can happen?** — The pointcut no longer matches the method, and transaction advice is not applied to the call.
6. **Why use `aspectjweaver` while saying the example does not use weaving?** — Spring AOP proxies use the library to parse pointcut expressions; it does not enable compile/load-time bytecode weaving.
7. **Does a `this.transfer(...)` call from the same target go through the transaction interceptor?** — Normally no in proxy mode, so it does not create a new transaction boundary on its own.
8. **Does `REQUIRED` guarantee commit when a child method returns?** — Not if it is joining the caller's transaction; the outer transaction decides commit.
9. **Why must an error test run after an UPDATE?** — To prove intermediate changed data is undone; failing before any SQL runs does not prove rollback works.
10. **Can `read-only="true"` alone prevent updates?** — No. Database permissions and business rules are needed; read-only is a transaction attribute/hint.

## 12. Conclusion and cheat sheet

| Configuration | Question Answered |
| --- | --- |
| `<bean id="txManager">` | Who manages transactions on which resource? |
| `<tx:advice id="txAdvice">` | What propagation/isolation/rollback rules does the transaction have? |
| `<tx:method name="transfer">` | Which rule applies to the method name? |
| `<aop:pointcut expression="execution(...)">` | Which method executions are selected? |
| `<aop:advisor pointcut-ref="..." advice-ref="...">` | How is the advice connected to the selected set of methods? |
| Spring AOP proxy | Do calls into the service go through the interceptor? |

**Remember:** XML transaction management works when **the pointcut selects the right method**, **the transaction advice has the right rule**, **the advisor connects the two components**, and **the transaction manager uses the right resource**. When callers go through the proxy, Spring wraps the method in a transaction, and the database guarantees commit/rollback. This is an explicit way to attach transaction advice to a pointcut with AOP, verifiable through post-error data state.

### Official References

- [Spring Framework — Example of Declarative Transaction Implementation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/first-example.html)
- [Spring Framework — Schema-based AOP Support](https://docs.spring.io/spring-framework/reference/core/aop/schema.html)
- [Spring Framework — Rolling Back a Declarative Transaction](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html)
- [Spring Framework — Advising Transactional Operations](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/applying-more-than-just-tx-advice.html)
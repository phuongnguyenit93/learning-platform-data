# Defining `tx:advice` and `tx:method` Attributes in Spring Framework

## Objectives

After this lesson, you will be able to read and write **XML-based transaction management** configurations in Spring, understand the roles of `<tx:advice>`, `<tx:attributes>`, and `<tx:method>`; connect transaction advice with AOP pointcuts; accurately choose the attributes `name`, `propagation`, `isolation`, `timeout`, `read-only`, `rollback-for`, and `no-rollback-for`; and verify behavior with a JDBC example covering both commit and rollback.

The scope is **Spring Framework XML configuration**. The main example uses Java 17, Spring JDBC, and an imperative transaction manager. The same Spring transaction principles also appear in annotation-based configuration, while XML syntax and application points are explained specifically here.

## 1. Why do we need `tx:advice`?

Suppose a `transfer()` service executes two SQL statements: debiting the source account and crediting the destination account. If the credit statement fails, the debit must be undone. Instead of writing `connection.setAutoCommit(false)`, `commit()`, `rollback()`, and resource-cleanup code in every service, we declare transaction rules in XML. Spring uses AOP proxies and a transaction interceptor to manage the transaction lifecycle around method calls.

Three parts have distinct responsibilities:

1. **`<tx:advice>`:** creates a *transaction advice* with an identifier and a reference to a transaction manager. This advice describes "how to manage transactions."
2. **`<tx:attributes>` containing `<tx:method>` elements:** specifies *which method names* use which transaction policy.
3. **`<aop:pointcut>` + `<aop:advisor>`:** identifies *which beans/methods* AOP intercepts and binds the interception point to the advice just defined.

```text
Client calls method on Spring proxy
    │
    ├─ Does the AOP pointcut match class + method?
    │    └─ No → this advice is not applied
    │
    └─ Yes → look up matching <tx:method name="...">
             │
             ├─ No matching rule → advice does not create a transaction for that method
             │
             └─ Match → TransactionInterceptor uses TransactionManager:
                        open/join transaction
                        invoke method body
                        normal return → commit (if transaction owner)
                        rollback-triggering exception → rollback/mark rollback-only
```

A standalone `<tx:advice>` configuration **does not attach itself** to a service; `<aop:advisor>` and a corresponding pointcut are required. Conversely, a pointcut only selects where to intervene—it does not specify `read-only` or rollback rules without the advice.

## 2. Standard XML structure

The following concise example illustrates all components (`txManager` is a `PlatformTransactionManager` bean already declared in the context):

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

    <tx:advice id="serviceTxAdvice" transaction-manager="txManager">
        <tx:attributes>
            <tx:method name="find*" read-only="true"/>
            <tx:method name="save*" propagation="REQUIRED"
                       isolation="READ_COMMITTED" timeout="15"/>
            <tx:method name="*" propagation="REQUIRED"/>
        </tx:attributes>
    </tx:advice>

    <aop:config>
        <aop:pointcut id="serviceMethods"
                      expression="execution(* com.example.service.*Service.*(..))"/>
        <aop:advisor pointcut-ref="serviceMethods"
                     advice-ref="serviceTxAdvice"/>
    </aop:config>
</beans>
```

This is an **illustrative configuration snippet**, not a standalone runnable application because the service, datasource, and `txManager` beans are omitted. Section 7 has a complete Maven project to try out.

How to read it:

- `id="serviceTxAdvice"`: bean name of the advice for `advice-ref` to reference.
- `transaction-manager="txManager"`: name of the bean capable of managing transactions, such as `JdbcTransactionManager` or `JpaTransactionManager`. If the bean is named exactly `transactionManager`, this attribute can be omitted; with any other name it must be specified explicitly.
- `<tx:attributes>`: groups transaction rules by method name.
- `<tx:method name="find*" .../>`: all methods matching `find*` receive a read-only policy.
- `<tx:method name="*"/>`: default rule for methods that have not matched a more specific rule.
- `expression="execution(* com.example.service.*Service.*(..))"`: AspectJ pointcut expression selecting methods of classes ending with `Service` directly in the `com.example.service` package. The `*` in this AOP expression follows AspectJ syntax; it is **different** from using `*` to match *method names* in the `tx:method name` attribute.

When you want to include subpackages, you must adjust the pointcut (for example using `com.example.service..*Service`) and verify it matches the exact intended targets. Avoid writing an overly broad pointcut that accidentally wraps controllers, DAOs, or unrelated services.

## 3. Complete table of `tx:method` attributes

According to the Spring Framework documentation, `name` is the **required** attribute; the remaining six attributes are all optional.

| Attribute | Value / Default | Meaning |
|---|---|---|
| `name` | **Required**; exact name or pattern with `*` | Selects method names receiving this rule, e.g. `getById`, `get*`, `*Service`, `*` |
| `propagation` | `REQUIRED` | How the method joins or creates a transaction when the caller already has / does not have a transaction |
| `isolation` | `DEFAULT` | Data isolation level in a new transaction; depends on DB/driver |
| `timeout` | `-1` (infrastructure default) | Transaction time limit, in **seconds**, if supported by the manager/resource |
| `read-only` | `false` | Read-only transaction hint; may assist optimization and may be enforced by driver/DB |
| `rollback-for` | No additional rule | Comma-separated list of exception names/name patterns that **must roll back** |
| `no-rollback-for` | No additional rule | Comma-separated list of exception names/name patterns that **do not roll back under this rule** |

If nothing extra is declared: propagation = `REQUIRED`, isolation = `DEFAULT`, read-write transaction, timeout per the transaction system, `RuntimeException` and `Error` cause rollback while checked `Exception` types normally do not. Explicit rollback rules can override default behavior.

Note: `isolation`, `timeout`, and `read-only` apply when a new transaction is started, typically with `REQUIRED` (when no transaction exists) or `REQUIRES_NEW`. When `REQUIRED` joins an existing transaction, it usually uses the actual characteristics of the outer transaction. Different managers may validate or handle this differently depending on configuration.

### 3.1. `name`: selecting methods by name

```xml
<tx:attributes>
    <tx:method name="findById" read-only="true"/>
    <tx:method name="find*" read-only="true"/>
    <tx:method name="*Report" read-only="true"/>
    <tx:method name="*" propagation="REQUIRED"/>
</tx:attributes>
```

Within the same advice, an exact name match takes precedence; among patterns, Spring chooses the most specific match (typically the pattern with the longest string). Therefore `findById` follows its dedicated rule, `findAll` follows `find*`, and `generateReport` follows `*Report`. Having a `*` rule avoids accidentally leaving remaining methods uncovered. Avoid creating ambiguous overlapping patterns with the same specificity.

`name` only inspects the **method name**; it does not distinguish two overloads `find(long)` and `find(String)` by parameter types. If you need to select by type/arguments/class scope, use an appropriate AOP pointcut expression and, when necessary, separate advice definitions. This is not regex; `*` is a wildcard for character sequences in the method name.

### 3.2. `propagation`: relationship with the caller's transaction

| Value | If a transaction already exists | If no transaction exists |
|---|---|---|
| `REQUIRED` | Joins the existing transaction | Creates a new transaction |
| `REQUIRES_NEW` | Suspends the old transaction, creates an independent transaction | Creates a new transaction |
| `SUPPORTS` | Joins if one exists | Executes without a transaction |
| `MANDATORY` | Must join | Throws an exception because a transaction is missing |
| `NOT_SUPPORTED` | Suspends the transaction, executes without a transaction | Executes without a transaction |
| `NEVER` | Throws an exception if a transaction is active | Executes without a transaction |
| `NESTED` | Attempts to create a nested scope with a savepoint (if supported by the manager) | Typically behaves like `REQUIRED` |

For example, `REQUIRES_NEW` is useful when an audit record needs its own transaction, but it has a consequence: the audit record can commit even while the outer transaction rolls back. It may require an additional connection; check the connection pool, especially under high concurrency. `NESTED` depends on savepoints and the transaction manager, and is not inherently compatible with every infrastructure.

### 3.3. `isolation`: isolation level

Common values: `DEFAULT`, `READ_UNCOMMITTED`, `READ_COMMITTED`, `REPEATABLE_READ`, `SERIALIZABLE`.

- `DEFAULT`: uses the DB's default isolation level.
- `READ_UNCOMMITTED`: weak level, may allow reading uncommitted data if the database actually supports it.
- `READ_COMMITTED`: prevents dirty reads; changes can still be observed between two queries.
- `REPEATABLE_READ`: stronger guarantee when re-reading the same row; details around phantoms, locks, and snapshots depend on the DB.
- `SERIALIZABLE`: aims for serial execution semantics; may increase contention and retry needs.

Example: `<tx:method name="settle*" isolation="SERIALIZABLE"/>` expresses a requirement, **not a guarantee** that every database/driver behaves identically. Test on the production DB and handle deadlock/serialization errors with a safe retry policy.

### 3.4. `timeout` and `read-only`

```xml
<tx:method name="create*" propagation="REQUIRED"
           timeout="30" read-only="false"/>
<tx:method name="get*" propagation="REQUIRED"
           timeout="5" read-only="true"/>
```

`timeout="30"` means 30 seconds, **not 30 ms**. It does not guarantee automatically killing arbitrary CPU work or canceling every blocking call at exactly second 30: when it is detected/enforced depends on the transaction manager, JDBC statements, and resources in use. `timeout="-1"` means use the infrastructure default, not necessarily infinite.

`read-only="true"` is a **hint**, not a security authorization layer. Some DBs/drivers may block writes or optimize; others do not. Even with a read-only rule, the application still needs appropriate DB permissions and should avoid writing data in methods marked read-only.

### 3.5. `rollback-for` and `no-rollback-for`

By default, unchecked errors (`RuntimeException`) and `Error` roll back; checked exceptions such as `IOException` do not roll back by default. XML configuration:

```xml
<tx:method name="importData"
           rollback-for="java.io.IOException,com.example.tx.ImportFailedException"/>

<tx:method name="confirmOrder"
           no-rollback-for="com.example.tx.NotificationWarningException"/>
```

- `rollback-for` requires rollback when a matching exception occurs, including checked exceptions outside the default rule.
- `no-rollback-for` requests not rolling back for that exception; **work already written before the exception escapes may be committed**. Only use this when that is genuinely an acceptable business outcome.
- Values in XML are **exception name patterns**, not statically checked Java `Class<?>` objects. Fully qualified package names reduce unintended matches. For instance, `Exception` is too broad and may accidentally match many other classes; rollback patterns **do not support wildcards `*`** like `name` does.
- If multiple rollback/no-rollback rules match, the *strongest/most specific* rule wins. Do not rely on the declaration order of the two attributes to guess the outcome.
- If code catches and swallows an exception inside the service, the interceptor sees the method return normally and usually commits; `rollback-for` cannot handle a swallowed exception. You can rethrow the exception or mark rollback-only via Spring's API.

**Semantic warning:** `no-rollback-for="java.lang.IllegalArgumentException"` does not mean "safely ignore all input errors." If DB updates happened before the exception occurred, this policy can commit partial changes.

## 4. Actual processing flow

Suppose there are two beans `accountService` and `transactionManager`, sharing one JDBC datasource:

1. Client calls a method on the **Spring proxy**, not directly on a manually `new`-ed object.
2. `<aop:pointcut>` determines whether that method falls within the AOP scope.
3. The transaction interceptor retrieves configuration from the matching `<tx:method>`, e.g. `getBalance` → `get*`, `transfer` → `transfer*`.
4. `PlatformTransactionManager` opens a new transaction or joins an existing one according to propagation. With JDBC, Spring binds the connection to the thread following `TransactionSynchronizationManager` rules.
5. The service uses `JdbcTemplate`/repository wired to the transaction-bound datasource.
6. On success → the transaction owner commits; on a rollback-triggering exception → rolls back or marks rollback-only if participating in an outer transaction.
7. Spring releases resources according to the transaction lifecycle.

In nested `REQUIRED` situations, an inner call can mark the shared transaction as rollback-only; even if the outer method catches the exception and returns normally, committing on the outside can still throw `UnexpectedRollbackException`. This is why you need to understand actual transaction boundaries rather than just looking at method names.

## 5. Runnable example: Spring XML + Java 17 + H2

The demo project uses XML configuration, **without `@Transactional`**. The service contains two transfer operations and one operation that intentionally throws a checked exception to observe `rollback-for`. H2 is an in-memory database; the application initializes data in `Main`.

Structure:

```text
tx-xml-demo/
├── pom.xml
└── src/main/
    ├── java/com/example/tx/
    │   ├── AccountOperations.java
    │   ├── AccountServiceImpl.java
    │   └── Main.java
    └── resources/
        └── applicationContext.xml
```

### 5.1. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>tx-xml-demo</artifactId>
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
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <version>6.2.19</version>
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
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
```

`spring-context` provides the XML application context, `spring-jdbc` provides `JdbcTemplate` and `JdbcTransactionManager`, `aspectjweaver` handles AspectJ pointcut expressions in AOP, and H2 is the test DB. Versions are pinned so the example is reproducible; real projects should manage versions via a BOM and their own upgrade policies.

### 5.2. `AccountOperations.java`

```java
package com.example.tx;

import java.io.IOException;
import java.math.BigDecimal;

public interface AccountOperations {
    BigDecimal getBalance(long accountId);
    void transfer(long from, long to, BigDecimal amount);
    void transferChecked(long from, BigDecimal amount) throws IOException;
}
```

### 5.3. `AccountServiceImpl.java`

```java
package com.example.tx;

import java.io.IOException;
import java.math.BigDecimal;
import org.springframework.jdbc.core.JdbcTemplate;

public class AccountServiceImpl implements AccountOperations {
    private final JdbcTemplate jdbc;

    public AccountServiceImpl(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Override
    public BigDecimal getBalance(long accountId) {
        return jdbc.queryForObject(
            "SELECT balance FROM accounts WHERE id = ?",
            BigDecimal.class,
            accountId
        );
    }

    @Override
    public void transfer(long from, long to, BigDecimal amount) {
        if (amount == null || amount.signum() <= 0 || from == to) {
            throw new IllegalArgumentException("invalid transfer");
        }

        int debited = jdbc.update(
            "UPDATE accounts SET balance = balance - ? " +
            "WHERE id = ? AND balance >= ?",
            amount, from, amount
        );
        if (debited != 1) {
            throw new IllegalStateException("missing sender or insufficient balance");
        }

        int credited = jdbc.update(
            "UPDATE accounts SET balance = balance + ? WHERE id = ?",
            amount, to
        );
        if (credited != 1) {
            throw new IllegalStateException("missing recipient");
        }
    }

    @Override
    public void transferChecked(long from, BigDecimal amount)
            throws IOException {
        jdbc.update(
            "UPDATE accounts SET balance = balance - ? WHERE id = ?",
            amount, from
        );
        throw new IOException("checked failure");
    }
}
```

`transferChecked()` is a **method that intentionally fails to verify rollback**, not complete transfer business logic. It only runs in the test example; in real applications you must never debit money and then deliberately throw an exception. `transfer()` is the business flow that checks updated row counts and requires two atomic updates.

### 5.4. `applicationContext.xml`

```xml
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

    <bean id="dataSource"
          class="org.springframework.jdbc.datasource.DriverManagerDataSource">
        <property name="driverClassName" value="org.h2.Driver"/>
        <property name="url" value="jdbc:h2:mem:txdemo;DB_CLOSE_DELAY=-1"/>
        <property name="username" value="sa"/>
        <property name="password" value=""/>
    </bean>

    <bean id="jdbcTemplate"
          class="org.springframework.jdbc.core.JdbcTemplate">
        <constructor-arg ref="dataSource"/>
    </bean>

    <bean id="transactionManager"
          class="org.springframework.jdbc.support.JdbcTransactionManager">
        <constructor-arg ref="dataSource"/>
    </bean>

    <bean id="accountService" class="com.example.tx.AccountServiceImpl">
        <constructor-arg ref="jdbcTemplate"/>
    </bean>

    <tx:advice id="accountTxAdvice"
               transaction-manager="transactionManager">
        <tx:attributes>
            <tx:method name="get*" read-only="true"/>
            <tx:method name="transferChecked" propagation="REQUIRED"
                       isolation="READ_COMMITTED" timeout="15"
                       rollback-for="java.io.IOException"/>
            <tx:method name="transfer*" propagation="REQUIRED"
                       isolation="READ_COMMITTED" timeout="15"/>
            <tx:method name="*" propagation="REQUIRED"/>
        </tx:attributes>
    </tx:advice>

    <aop:config>
        <aop:pointcut id="accountOps"
                      expression="execution(* com.example.tx.AccountOperations.*(..))"/>
        <aop:advisor advice-ref="accountTxAdvice" pointcut-ref="accountOps"/>
    </aop:config>
</beans>
```

Selected rules:

- `getBalance` → `get*`, read-only.
- `transfer` → `transfer*`, new transaction or joins existing transaction; `READ_COMMITTED` isolation when creating a new transaction; 15-second timeout.
- `transferChecked` → **exact-match** rule, so `rollback-for="java.io.IOException"` takes effect. This rule also declares isolation/timeout separately because it **does not inherit** options from the `transfer*` rule.
- `*` → fallback for remaining methods; in the demo no method uses this fallback.

`DriverManagerDataSource` is suitable for small demos/tests because each connection acquisition may create a new connection; real production systems should use a pooled datasource with appropriate security and resilience settings.

### 5.5. `Main.java` and output

```java
package com.example.tx;

import java.io.IOException;
import java.math.BigDecimal;
import org.springframework.context.support.ClassPathXmlApplicationContext;
import org.springframework.jdbc.core.JdbcTemplate;

public class Main {
    private static String balances(AccountOperations service) {
        return "A=" + service.getBalance(1) +
               " B=" + service.getBalance(2);
    }

    public static void main(String[] args) {
        try (var context =
                 new ClassPathXmlApplicationContext("applicationContext.xml")) {
            var jdbc = context.getBean(JdbcTemplate.class);
            jdbc.execute(
                "CREATE TABLE accounts (" +
                "id BIGINT PRIMARY KEY, balance DECIMAL(19, 2) NOT NULL)"
            );
            jdbc.update(
                "INSERT INTO accounts (id, balance) VALUES (?, ?)",
                1, new BigDecimal("100.00")
            );
            jdbc.update(
                "INSERT INTO accounts (id, balance) VALUES (?, ?)",
                2, new BigDecimal("50.00")
            );

            // Retrieve the bean from Spring context so calls go through the AOP proxy.
            AccountOperations service = context.getBean(AccountOperations.class);
            System.out.println("Initial: " + balances(service));

            service.transfer(1, 2, new BigDecimal("20.00"));
            System.out.println("Success: " + balances(service));

            try {
                service.transferChecked(1, new BigDecimal("5.00"));
            } catch (IOException ex) {
                System.out.println("Checked error: " + ex.getMessage());
            }
            System.out.println("After checked rollback: " + balances(service));

            try {
                service.transfer(1, 999, new BigDecimal("5.00"));
            } catch (IllegalStateException ex) {
                System.out.println("Runtime error: " + ex.getMessage());
            }
            System.out.println("After runtime rollback: " + balances(service));
        }
    }
}
```

In the project directory (with JDK 17+ and Maven installed), run:

```bash
mvn -q compile exec:java -Dexec.mainClass=com.example.tx.Main
```

Six lines **printed by the program** (Maven or logging frameworks may add other messages depending on the environment):

```text
Initial: A=100.00 B=50.00
Success: A=80.00 B=70.00
Checked error: checked failure
After checked rollback: A=80.00 B=70.00
Runtime error: missing recipient
After runtime rollback: A=80.00 B=70.00
```

Why is the output correct?

1. First, `getBalance()` returns 100.00 and 50.00.
2. `transfer(1, 2, 20.00)` executes two UPDATE statements and commits: 80.00 and 70.00.
3. `transferChecked()` debited 5.00 but threw checked `IOException`. The XML rule `rollback-for="java.io.IOException"` forces rollback, so balances remain **unchanged**.
4. `transfer(1, 999, 5.00)` debits account A first, then detects the recipient does not exist and throws unchecked `IllegalStateException`. Default rollback rules undo the debit.

If you accidentally call `new AccountServiceImpl(jdbc)` directly instead of retrieving the bean from the context, the interceptor will not run. And if you remove the rollback rule for the checked exception, step (3) risks **committing the 5.00 debit** because `IOException` is not rolled back under default rules.

## 6. Configuration errors and how to check them

| Symptom | Common Cause | How to Resolve |
|---|---|---|
| Service runs without a transaction | Declared `tx:advice` without `aop:advisor`, pointcut does not match, or called outside proxy | Check pointcut, `advice-ref`, bean retrieved from context, and interceptor logs |
| Cannot find transaction manager | `transaction-manager` points to wrong bean; defaults to bean named `transactionManager` if omitted | Confirm bean id and datasource managed by the manager |
| Read method creates a write transaction | `name` does not match, missing `read-only="true"`, or broad `*` rule applied | Check actual method name and specific rules |
| Checked exception does not roll back | Missing `rollback-for` configuration or exception caught inside method | Add a rule with the appropriate exception name and let the error escape through the transaction interceptor |
| An error still commits | Using `no-rollback-for`, swallowing errors, or conflicting rules | Review rollback policy; only allow commit when it is a valid business outcome |
| Isolation/timeout not as expected | Method joins an already open transaction, manager/driver does not support it, or timeout not enforced by resource | Check propagation, transaction owner, and DB capabilities |
| `this.method()` does not trigger its own transaction | Self-invocation bypasses the default Spring proxy | Place the boundary on a proxied method or extract to another bean |
| Behavior differs across environments | DBs differ in isolation/read-only support; datasource/manager config differs | Run integration tests on the real DB and driver; do not rely solely on mocked unit tests |
| `NESTED` fails | Manager does not support savepoints/nested transactions | Check manager capabilities and choose an appropriate propagation |
| Two calls use two datasources | Transaction manager and repository do not share the same resource | Check connections/beans; do not assume a local transaction spans multiple datasources |

**Test proactively:** verify that the advice is actually triggered, then test both success and rollback. A useful indicator is enabling DEBUG logging for `org.springframework.transaction` and `org.springframework.aop`, though exact log details and logger names can vary between versions. A more reliable verification is reading DB state back after each case.

**Distinguishing the two XML mechanisms:**

- `<tx:advice>` + `<aop:advisor>`: rules are described by *method name* in XML, and services can be unannotated POJOs.
- `<tx:annotation-driven>`: enables processing of `@Transactional` annotations on beans; this is an alternative approach. If both are configured on the same method, carefully inspect the scope and advice order to avoid duplicate interception rather than assuming they automatically merge into one rule.

## 7. Self-check exercises

1. With `<tx:method name="find*" read-only="true"/>` and `<tx:method name="*"/>`, which rule does `findByCode()` select? **Answer:** `find*`.
2. If you remove `<aop:advisor>` while keeping `<tx:advice>`, are transactions automatically applied to services? **No**; an advisor/pointcut is needed to bind the advice.
3. What is `rollback-for="java.io.IOException"` for? **Adding rollback for a checked exception** when it escapes the method.
4. Can two overloads `save(long)` and `save(String)` receive two different rules using only `name="save"`? **No**, because `tx:method` matches method names, not signatures.
5. Does `read-only="true"` prevent every `UPDATE` statement on every database? **No**; it is a hint, so you must check the DB/driver and access permissions.
6. Can `REQUIRES_NEW` commit when the outer transaction rolls back? **Yes**, because it is an independent transaction.
7. Why does `name="transferChecked"` need to redeclare `timeout` even when `name="transfer*" timeout="15"` is present? **The specific rule is selected as a whole; attributes are not partially inherited from a broader rule.**

## Official Documentation

- Spring — Example of Declarative Transaction Implementation: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/first-example.html
- Spring — `<tx:advice/>` Settings (`tx:method` default values table): https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/txadvice-settings.html
- Spring — Rolling Back a Declarative Transaction: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html
- Spring — Schema-based AOP Support: https://docs.spring.io/spring-framework/reference/core/aop/schema.html
- Spring — Understanding the Declarative Transaction Implementation: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html

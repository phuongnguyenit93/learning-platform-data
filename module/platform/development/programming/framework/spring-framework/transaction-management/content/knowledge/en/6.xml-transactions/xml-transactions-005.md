# Configuring Manager, `rollback-for`, and `no-rollback-for` via XML in Spring Framework

## 1. What will you learn and when to use it?

In Spring Framework, **declarative transaction management** lets you separate transaction management from business code. Instead of calling `commit()` and `rollback()` manually, you declare rules in XML; Spring AOP applies those rules to service method calls.

This article belongs to the **XML Configuration** section of Spring transaction management and focuses on three requirements:

1. **Manager:** configure a `PlatformTransactionManager` suitable for the data source, give it the right bean name, and link it to the transaction advice.
2. **`rollback-for`:** force rollback for specific exceptions, especially **checked exceptions** that do not cause Spring to roll back by default.
3. **`no-rollback-for`:** exclude rollback for a specific exception, including **unchecked exceptions** that trigger rollback by default.

The goal after this lesson is to be able to read `<tx:advice>`, `<tx:method>`, and `<aop:advisor>` configurations; know when a transaction commits or rolls back; run a Java 17+ example with easily comparable cases; and avoid mistakes involving exception patterns, pointcuts, managers, and transaction scopes.

**Sample scenario:** A service writes records to a database. The input-validation business error `BusinessFailureException` is a checked exception yet requires rollback. Conversely, a warning `NonFatalOperationException` is an unchecked exception, yet previously written data may be kept. Both policies live in XML, while the Java service needs no `@Transactional` annotation.

## 2. How manager, advice, and AOP connect

```text
Caller
  |
  v
Spring AOP proxy
  |  <aop:advisor> links pointcut + txAdvice
  v
TransactionInterceptor
  |
  +-- <tx:advice transaction-manager="txManager">
  |     <tx:method name="..." rollback-for="..." no-rollback-for="...">
  |
  +-- txManager: PlatformTransactionManager
  |     DataSourceTransactionManager / JpaTransactionManager / ...
  |
  +-- start or join transaction
  |
  +-- invoke business service method
  |
  +-- method returns / exception escapes
  |
  +-- commit or rollback per rules and actual state
  v
Caller receives result or exception
```

Reading each part's role:

| XML / Component | Responsibility |
| --- | --- |
| `<bean id="dataSource">` | Provides connections to the database |
| `<bean id="txManager">` | Manages physical transactions appropriate for the data source |
| `<tx:advice id="txAdvice" transaction-manager="txManager">` | Declares transaction metadata bound to which manager |
| `<tx:attributes>` and `<tx:method>` | Selects transaction policies by method name |
| `<aop:pointcut>` | Selects which service calls receive the advice |
| `<aop:advisor>` | Attaches the pointcut to `txAdvice` to create proxies |

**Merely declaring a transaction manager does not automatically make methods transactional.** Likewise, declaring `<tx:advice>` without an advisor/pointcut still does not identify which calls are intercepted. `TransactionInterceptor` only gets a chance to decide rollback when the method is called **through a proxy**.

## 3. Configuring a transaction manager with XML

### 3.1. Simple JDBC configuration

```xml
<bean id="dataSource"
      class="org.springframework.jdbc.datasource.DriverManagerDataSource">
    <property name="driverClassName" value="org.h2.Driver"/>
    <property name="url" value="jdbc:h2:mem:xml_tx;DB_CLOSE_DELAY=-1"/>
    <property name="username" value="sa"/>
    <property name="password" value=""/>
</bean>

<bean id="txManager"
      class="org.springframework.jdbc.datasource.DataSourceTransactionManager">
    <property name="dataSource" ref="dataSource"/>
</bean>

<bean id="jdbcTemplate"
      class="org.springframework.jdbc.core.JdbcTemplate">
    <constructor-arg ref="dataSource"/>
</bean>
```

In this example:

- `dataSource` creates JDBC connections. `DriverManagerDataSource` suits practice exercises because no connection pool configuration is needed; production systems typically use a pool like HikariCP.
- `txManager` is a `DataSourceTransactionManager`, suited for local transactions on **a single JDBC DataSource**. It controls the lifecycle of connections participating in a transaction.
- `jdbcTemplate` is configured with the **exact same `dataSource` bean**. Hence the service's SQL statements participate in the transaction controlled by the Spring manager.
- If `txManager` uses DataSource A while the DAO/JdbcTemplate uses an unrelated DataSource B, a rollback on A will not automatically roll back SQL statements on B.
- `JdbcTransactionManager` is an enhanced variant of `DataSourceTransactionManager` supporting commit/rollback exception translation. `DataSourceTransactionManager` is used here to show the basic XML pattern.

### 3.2. Choosing a manager suitable for the technology

| Case | Commonly Used Manager | Notes |
| --- | --- | --- |
| JDBC with one `DataSource` | `DataSourceTransactionManager` or `JdbcTransactionManager` | Requires the DAO to participate in Spring-managed connections |
| JPA | `JpaTransactionManager` | Bound to the appropriate `EntityManagerFactory` |
| JTA/XA | `JtaTransactionManager` | Requires corresponding transaction infrastructure |
| Reactive transaction | Appropriate `ReactiveTransactionManager` | Does not use the thread-bound JDBC semantics of this example |

Managers cannot be swapped arbitrarily just because they are declared in XML. With multiple data sources, two local JDBC managers **do not automatically form a distributed transaction**; a dedicated design is needed if business logic requires atomicity across multiple resources.

### 3.3. The manager bean name matters

```xml
<tx:advice id="txAdvice" transaction-manager="txManager">
    <tx:attributes>
        <tx:method name="*"/>
    </tx:attributes>
</tx:advice>
```

`transaction-manager="txManager"` must match the `id` of the transaction manager bean. If the bean is named `transactionManager`, you can usually **omit** the `transaction-manager` attribute on `<tx:advice>` because that is the default name expected by the namespace. If the manager is named `txManager`, it must be specified explicitly as above. A wrong bean name can prevent `ApplicationContext` from creating the advice; choosing the wrong manager pointing to another database is even more dangerous because transactions will not cover the intended data.

## 4. Declaring `tx:advice` and `aop:advisor`

An XML snippet showing the method-selection mechanism:

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

    <!-- Beans txManager, dataSource, and orderService must also be declared. -->

    <tx:advice id="txAdvice" transaction-manager="txManager">
        <tx:attributes>
            <tx:method name="get*" read-only="true"/>
            <tx:method name="save*" propagation="REQUIRED"/>
            <tx:method name="*"/>
        </tx:attributes>
    </tx:advice>

    <aop:config>
        <aop:pointcut id="serviceMethods"
                      expression="execution(* demo.OrderService.*(..))"/>
        <aop:advisor advice-ref="txAdvice"
                     pointcut-ref="serviceMethods"/>
    </aop:config>
</beans>
```

This is an **illustrative fragment**, not standalone runnable until the missing beans are added. The complete version is in Section 7.

Explanation:

- `<tx:method name="get*" read-only="true"/>` applies metadata to methods starting with `get`.
- `name="save*"` applies to names starting with `save`.
- `name="*"` is the fallback rule for remaining names.
- `<aop:pointcut>` selects executions of methods on the `demo.OrderService` interface.
- `<aop:advisor>` attaches transaction advice to the methods selected by the pointcut.
- Advice is applied when callers obtain the service bean from Spring and call through the proxy. Calling an object created with `new` does not pass through the interceptor; self-invocation via `this.otherMethod()` within the same bean can also bypass the proxy.

Commonly used attributes of `<tx:method>`:

| Attribute | Example Value | Meaning |
| --- | --- | --- |
| `name` | `save*`, `get*`, `*` | Method name pattern, supporting the `*` wildcard |
| `propagation` | `REQUIRED`, `REQUIRES_NEW`, `NESTED` | Transaction relationship with the caller |
| `isolation` | `DEFAULT`, `READ_COMMITTED` | Isolation level |
| `timeout` | `30` | Timeout in seconds, depending on the transaction manager |
| `read-only` | `true` | Hint for read operations, not an absolute write-blocking command |
| `rollback-for` | `demo.BusinessFailureException` | Exception pattern requiring rollback |
| `no-rollback-for` | `demo.NonFatalOperationException` | Exception pattern avoiding rollback |

When a transaction already exists in the outer scope, `REQUIRED` joins that transaction. In that case, `isolation`/`timeout`/`read-only` on the inner metadata usually do not change the characteristics already decided when the physical transaction was created. To verify the policy in the example, we invoke the service from a caller without an outer transaction.

## 5. Default rollback when no rule is declared

Spring declarative transactions normally decide based on the exception **escaping the transactional interceptor**:

| Method Outcome | Default if Manager Owns the Transaction |
| --- | --- |
| Normal return | Commit, unless already rollback-only or another error occurs |
| Throws `RuntimeException` | Rollback |
| Throws `Error` | Rollback |
| Throws checked exception, e.g. `IOException` | Usually commits, then propagates the exception to caller |
| Checked exception configured in `rollback-for` | Rollback |
| Unchecked exception configured in `no-rollback-for` | May commit, then still propagates the exception to caller |

Defaults of `<tx:advice>`: propagation `REQUIRED`, isolation `DEFAULT`, read-write, timeout depending on the underlying transaction system; unchecked runtime/error roll back, checked exceptions do not roll back.

Key takeaway: **an exception does not automatically mean rollback**. A method can execute an INSERT successfully and then throw a checked exception; the interceptor still commits by default and then rethrows the exception. This is why Spring recommends declaring rollback policies that match business semantics, not just exception types.

If an exception is caught and handled inside the method before returning to the interceptor, the transaction interceptor only sees a **normal return**; the XML rules will not automatically trigger for a swallowed exception. When rollback is needed in that situation, you can rethrow an appropriate exception or explicitly mark rollback-only via Spring's API, after considering the impact on any outer transaction.

## 6. Syntax of `rollback-for` and `no-rollback-for`

### 6.1. `rollback-for`: abort even on checked exceptions

```xml
<tx:advice id="txAdvice" transaction-manager="txManager">
    <tx:attributes>
        <tx:method name="saveCheckedRollback"
                   rollback-for="demo.BusinessFailureException"/>
        <tx:method name="*"/>
    </tx:attributes>
</tx:advice>
```

If `saveCheckedRollback()` executes an INSERT and then throws `BusinessFailureException` (checked) out of the proxy, the XML rule mandates rollback. Without this rule, a checked exception usually leads to commit because defaults only roll back on `RuntimeException`/`Error`.

### 6.2. `no-rollback-for`: keep data despite an exception

```xml
<tx:advice id="txAdvice" transaction-manager="txManager">
    <tx:attributes>
        <tx:method name="saveUncheckedNoRollback"
                   no-rollback-for="demo.NonFatalOperationException"/>
        <tx:method name="*"/>
    </tx:attributes>
</tx:advice>
```

`NonFatalOperationException` extends `RuntimeException` yet is excluded from rollback on this method. If the interceptor owns the transaction and there is no prior rollback-only flag or other commit error, Spring **commits** and then **still throws the exception** to the caller. `no-rollback-for` does not mean "ignore the exception" or "catch the error for the caller."

Only configure this for **acceptable warning-like errors** where prior changes are genuinely allowed to persist. If data is already inconsistent, committing can leave corrupted state in the database.

### 6.3. When both are present: the strongest rule wins

```xml
<tx:method name="saveUncheckedNoRollback"
           rollback-for="java.lang.Throwable"
           no-rollback-for="demo.NonFatalOperationException"/>
```

This expresses "all other errors roll back; this specific warning does not roll back." For `NonFatalOperationException`, the more specific no-rollback pattern matches the actual exception directly; the `Throwable` rollback pattern only matches an ancestor in the hierarchy. Therefore **the stronger no-rollback rule is chosen**. For another exception not covered by the exception rule, the broad rollback rule may be selected.

Spring **does not** simply pick whichever rule appears first or last in XML, nor does `no-rollback-for` always win by default. When multiple rules match, it prioritizes the rule evaluated as **strongest** for the thrown exception type.

### 6.4. XML uses exception *patterns*, not Java `Class` syntax

The attributes accept a comma-separated list of exception names:

```xml
<tx:method name="import*"
           rollback-for="demo.BusinessFailureException,java.io.IOException"
           no-rollback-for="demo.NonFatalOperationException"/>
```

Patterns can be fully qualified class names or parts of class names. Because this is **substring pattern matching** against class names along the hierarchy, patterns like `Exception` or `RuntimeException` can match very broadly. The pattern `demo.BusinessFailureException` could also match `demo.BusinessFailureExceptionV2` because the name contains the same substring.

**There is no `*` wildcard in exception patterns.** The `*` character is allowed in `tx:method name="save*"` to select method names, but `rollback-for="*Exception"` does not mean "every Exception." Use unique, fully qualified names for business exceptions, and avoid overly short strings that cause accidental matches.

When using Java annotations, `@Transactional(rollbackFor = BusinessFailureException.class, noRollbackFor = NonFatalOperationException.class)` defines rules **by class type**; `rollbackForClassName` and `noRollbackForClassName` are the pattern-based equivalents to XML. Do not assume XML rules are type-safe like `.class`.

### 6.5. Two distinct matching layers

Spring resolves the method's transaction metadata by `<tx:method name="...">` first, and only then decides rollback based on the exception rules **of that chosen metadata**.

```xml
<tx:attributes>
    <tx:method name="saveCritical"
               rollback-for="demo.BusinessFailureException"/>
    <tx:method name="save*"
               no-rollback-for="demo.NonFatalOperationException"/>
    <tx:method name="*"/>
</tx:attributes>
```

`saveCritical` matches the more specific name rule over `save*`. Spring does not automatically accumulate all exception rules from different `<tx:method>` entries into one combined set. When debugging, check **which method mapping is active** before analyzing exception rules.

## 7. Runnable Java 17+ project using only XML, Maven, Spring JDBC, and H2

The exercise below uses Spring Framework **6.2.19** and Java 17+. The goal is to observe how the exact same INSERT operation can commit or roll back differently purely due to XML rules.

Five cases:

1. `saveOk` returns normally → commit.
2. `saveCheckedDefault` throws a checked exception, no custom rollback rule → commit.
3. `saveCheckedRollback` throws a checked exception, XML `rollback-for` → rollback.
4. `saveUncheckedDefault` throws an unchecked exception, default → rollback.
5. `saveUncheckedNoRollback` throws a specific unchecked exception, XML `no-rollback-for` beats broad rollback → commit.

### 7.1. Directory structure

```text
xml-tx-rules/
├── pom.xml
└── src/main/
    ├── java/demo/
    │   ├── Main.java
    │   ├── OrderService.java
    │   ├── OrderServiceImpl.java
    │   ├── BusinessFailureException.java
    │   └── NonFatalOperationException.java
    └── resources/
        └── applicationContext.xml
```

### 7.2. The `pom.xml` file

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>xml-tx-rules</artifactId>
    <version>1.0.0</version>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven.compiler.release>17</maven.compiler.release>
        <spring.version>6.2.19</spring.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>${spring.version}</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <version>${spring.version}</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-tx</artifactId>
            <version>${spring.version}</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-aop</artifactId>
            <version>${spring.version}</version>
        </dependency>
        <dependency>
            <groupId>org.aspectj</groupId>
            <artifactId>aspectjweaver</artifactId>
            <version>1.9.22.1</version>
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
                <version>3.5.0</version>
                <configuration>
                    <mainClass>demo.Main</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

`spring-context` provides the XML context, `spring-jdbc` provides `JdbcTemplate` and the manager, `spring-tx` provides the transaction abstraction, and `spring-aop` + `aspectjweaver` support pointcuts; H2 is the in-memory database running inside the JVM.

### 7.3. The `applicationContext.xml` file

**`src/main/resources/applicationContext.xml`**

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
        <property name="url" value="jdbc:h2:mem:xml_tx;DB_CLOSE_DELAY=-1"/>
        <property name="username" value="sa"/>
        <property name="password" value=""/>
    </bean>

    <bean id="jdbcTemplate" class="org.springframework.jdbc.core.JdbcTemplate">
        <constructor-arg ref="dataSource"/>
    </bean>

    <bean id="txManager"
          class="org.springframework.jdbc.datasource.DataSourceTransactionManager">
        <property name="dataSource" ref="dataSource"/>
    </bean>

    <bean id="orderService" class="demo.OrderServiceImpl">
        <constructor-arg ref="jdbcTemplate"/>
    </bean>

    <tx:advice id="txAdvice" transaction-manager="txManager">
        <tx:attributes>
            <tx:method name="saveCheckedRollback"
                       propagation="REQUIRED"
                       rollback-for="demo.BusinessFailureException"/>

            <tx:method name="saveUncheckedNoRollback"
                       propagation="REQUIRED"
                       rollback-for="java.lang.Throwable"
                       no-rollback-for="demo.NonFatalOperationException"/>

            <tx:method name="*" propagation="REQUIRED"/>
        </tx:attributes>
    </tx:advice>

    <aop:config>
        <aop:pointcut id="orderServiceMethods"
                      expression="execution(* demo.OrderService.*(..))"/>
        <aop:advisor advice-ref="txAdvice"
                     pointcut-ref="orderServiceMethods"/>
    </aop:config>
</beans>
```

Cross-checking the configuration: `txManager` and `JdbcTemplate` point to the same `dataSource`; `txAdvice.transaction-manager` points to `txManager`; `<aop:advisor>` links `txAdvice` with the pointcut; specific rules apply to real method names; `name="*"` applies to remaining methods.

`<tx:advice>` is metadata, while `<aop:config>` causes Spring to create the AOP proxy. Neither `<tx:annotation-driven>` nor `@Transactional` is needed for this project.

### 7.4. Service interface

**`src/main/java/demo/OrderService.java`**

```java
package demo;

public interface OrderService {
    void saveOk(long id);
    void saveCheckedDefault(long id) throws BusinessFailureException;
    void saveCheckedRollback(long id) throws BusinessFailureException;
    void saveUncheckedDefault(long id);
    void saveUncheckedNoRollback(long id);
}
```

**`src/main/java/demo/BusinessFailureException.java`**

```java
package demo;

public class BusinessFailureException extends Exception {
    public BusinessFailureException(String message) {
        super(message);
    }
}
```

**`src/main/java/demo/NonFatalOperationException.java`**

```java
package demo;

public class NonFatalOperationException extends RuntimeException {
    public NonFatalOperationException(String message) {
        super(message);
    }
}
```

`BusinessFailureException` is a checked exception because it directly extends `Exception`; `NonFatalOperationException` is an unchecked exception because it extends `RuntimeException`. Both classes are placed in the `demo` package to match the XML exception patterns and pointcut.

### 7.5. Implementation: business logic only, no transaction declarations

**`src/main/java/demo/OrderServiceImpl.java`**

```java
package demo;

import org.springframework.jdbc.core.JdbcTemplate;

public class OrderServiceImpl implements OrderService {
    private final JdbcTemplate jdbc;

    public OrderServiceImpl(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    private void insert(long id, String note) {
        jdbc.update(
                "INSERT INTO tx_event(id, note) VALUES (?, ?)",
                id, note);
    }

    @Override
    public void saveOk(long id) {
        insert(id, "normal");
    }

    @Override
    public void saveCheckedDefault(long id) throws BusinessFailureException {
        insert(id, "checked-default");
        throw new BusinessFailureException("checked default");
    }

    @Override
    public void saveCheckedRollback(long id) throws BusinessFailureException {
        insert(id, "checked-rollback");
        throw new BusinessFailureException("checked rollback");
    }

    @Override
    public void saveUncheckedDefault(long id) {
        insert(id, "unchecked-default");
        throw new IllegalStateException("runtime default");
    }

    @Override
    public void saveUncheckedNoRollback(long id) {
        insert(id, "unchecked-no-rollback");
        throw new NonFatalOperationException("non-fatal");
    }
}
```

Each method executes an `INSERT` before returning or throwing an exception. Because the Java code does not control commit/rollback itself, the database state after each call reflects the **XML transaction rules**.

### 7.6. `Main` verifying committed state

**`src/main/java/demo/Main.java`**

```java
package demo;

import org.springframework.context.support.ClassPathXmlApplicationContext;
import org.springframework.jdbc.core.JdbcTemplate;

public class Main {
    public static void main(String[] args) {
        try (ClassPathXmlApplicationContext context =
                     new ClassPathXmlApplicationContext("applicationContext.xml")) {

            JdbcTemplate jdbc = context.getBean("jdbcTemplate", JdbcTemplate.class);
            OrderService service = context.getBean("orderService", OrderService.class);

            jdbc.execute("""
                    CREATE TABLE tx_event (
                        id BIGINT PRIMARY KEY,
                        note VARCHAR(80) NOT NULL
                    )
                    """);

            service.saveOk(1L);
            System.out.println("saveOk committed=" + exists(jdbc, 1L));

            try {
                service.saveCheckedDefault(2L);
            } catch (BusinessFailureException expected) {
                System.out.println("caught checked-default");
            }
            System.out.println("checkedDefault committed=" + exists(jdbc, 2L));

            try {
                service.saveCheckedRollback(3L);
            } catch (BusinessFailureException expected) {
                System.out.println("caught checked-rollback");
            }
            System.out.println("checkedRollback committed=" + exists(jdbc, 3L));

            try {
                service.saveUncheckedDefault(4L);
            } catch (IllegalStateException expected) {
                System.out.println("caught unchecked-default");
            }
            System.out.println("uncheckedDefault committed=" + exists(jdbc, 4L));

            try {
                service.saveUncheckedNoRollback(5L);
            } catch (NonFatalOperationException expected) {
                System.out.println("caught unchecked-no-rollback");
            }
            System.out.println("uncheckedNoRollback committed=" + exists(jdbc, 5L));
        }
    }

    private static boolean exists(JdbcTemplate jdbc, long id) {
        Integer count = jdbc.queryForObject(
                "SELECT COUNT(*) FROM tx_event WHERE id = ?",
                Integer.class, id);
        return count != null && count > 0;
    }
}
```

`Main` retrieves `orderService` from the Spring container so calls go through the AOP proxy. The caller has no outer transaction. When a method returns or an exception escapes, the interceptor has already finished committing or rolling back before `Main` executes `SELECT COUNT(*)`. The verification query thus observes post-transaction data.

### 7.7. Running and expected output

Requires JDK 17+ and Maven; in the directory containing `pom.xml`:

```bash
mvn -q compile exec:java
```

Lines **printed by `Main`** (excluding library/Maven logs):

```text
saveOk committed=true
caught checked-default
checkedDefault committed=true
caught checked-rollback
checkedRollback committed=false
caught unchecked-default
uncheckedDefault committed=false
caught unchecked-no-rollback
uncheckedNoRollback committed=true
```

| ID | Method | Exception | Deciding Rule | After Proxy Call Ends |
| --- | --- | --- | --- | --- |
| 1 | `saveOk` | None | Normal return | Row exists |
| 2 | `saveCheckedDefault` | `BusinessFailureException` | Checked exception does not roll back by default | Row exists |
| 3 | `saveCheckedRollback` | `BusinessFailureException` | XML `rollback-for` | No row |
| 4 | `saveUncheckedDefault` | `IllegalStateException` | Runtime exception rolls back by default | No row |
| 5 | `saveUncheckedNoRollback` | `NonFatalOperationException` | Most specific XML `no-rollback-for` | Row exists |

If XML has a wrong method name so a special rule is not selected, the method falls back to `name="*"`, producing a different result. If no advisor/pointcut matches, the INSERT may auto-commit because the service is called without the transaction interceptor; this is a critical bug to catch with tests.

## 8. Distinguishing from `tx:annotation-driven`

Do not confuse the two configuration styles:

**A. XML advice, no annotation required on the service:**

```xml
<tx:advice id="txAdvice" transaction-manager="txManager">
    <tx:attributes>
        <tx:method name="saveCheckedRollback"
                   rollback-for="demo.BusinessFailureException"/>
        <tx:method name="*"/>
    </tx:attributes>
</tx:advice>
<aop:config>
    <aop:pointcut id="serviceOps"
                  expression="execution(* demo.OrderService.*(..))"/>
    <aop:advisor advice-ref="txAdvice" pointcut-ref="serviceOps"/>
</aop:config>
```

**B. XML enabling `@Transactional` annotation processing:**

```xml
<tx:annotation-driven transaction-manager="txManager"/>
```

When choosing B, a method can be declared in Java:

```java
@Transactional(
    rollbackFor = BusinessFailureException.class,
    noRollbackFor = NonFatalOperationException.class
)
public void operation() throws BusinessFailureException {
    // Business logic goes here.
}
```

The Java snippet above **only illustrates the annotation**, not a standalone runnable class. `rollbackFor`/`noRollbackFor` use type-safe class references; `rollbackForClassName`/`noRollbackForClassName` use patterns. Meanwhile XML `rollback-for`/`no-rollback-for` are patterns.

`<tx:annotation-driven>` automatically configures the corresponding transaction advisor for annotations. With `<tx:advice>`, you must explicitly bind it using `<aop:advisor>`. When migrating from XML to annotations, align the manager, pointcut, propagation, and exception rules; avoid accidentally applying two advisors stacked on the same method.

## 9. Multiple managers: an illustrative example

```xml
<bean id="primaryTxManager"
      class="org.springframework.jdbc.datasource.DataSourceTransactionManager">
    <property name="dataSource" ref="primaryDataSource"/>
</bean>

<bean id="auditTxManager"
      class="org.springframework.jdbc.datasource.DataSourceTransactionManager">
    <property name="dataSource" ref="auditDataSource"/>
</bean>

<tx:advice id="primaryAdvice" transaction-manager="primaryTxManager">
    <tx:attributes>
        <tx:method name="*"/>
    </tx:attributes>
</tx:advice>

<tx:advice id="auditAdvice" transaction-manager="auditTxManager">
    <tx:attributes>
        <tx:method name="*"/>
    </tx:attributes>
</tx:advice>
```

This is a **fragment**, omitting DataSource beans and advisors. Each advice is bound to a specific manager, so it must be linked to the **right pointcut** and the **right DAO/DataSource**. Two JDBC managers do not guarantee atomicity between two databases; do not use database A's manager expecting to roll back operations already auto-committed on B.

If multiple transactional advisors apply to the same method, processing order, managers, and transaction scopes can affect the outcome. Clarify ownership and avoid overly broad pointcuts that create unpredictable behavior.

## 10. Limitations and common pitfalls

### 10.1. `no-rollback-for` does not force commit on a broken transaction

`no-rollback-for` only states that the exception in question is **not a reason for Spring to request rollback**. It does not clear a prior `rollback-only` flag, does not rescue a transaction that already failed at the database level, and does not prevent an outer transaction from rolling back. If the manager does not own the physical transaction because it joined an outer `REQUIRED` transaction, the final commit is still decided by the outer boundary.

### 10.2. Using overly broad exception patterns

`rollback-for="Exception"` can match many unintended exception types. `no-rollback-for="RuntimeException"` can lead to committing errors that should roll back. Use fully qualified class names, avoid patterns that collide with classes having other suffixes or nested classes, and test exception hierarchies.

### 10.3. Pointcut does not match the method

`execution(* demo.OrderService.*(..))` selects methods of `OrderService`. If the package/interface changes or a method is not on the interface, the proxy may not handle it as intended. Verify in practice that the bean is proxied and callers invoke public methods through the Spring bean rather than instantiating objects manually.

### 10.4. Manager and DAO do not share the same `DataSource`

A manager only manages the resource it is properly configured for. If a DAO acquires an independent connection and commits on its own, the manager cannot roll back that change. Use `JdbcTemplate`/`DataSourceUtils` properly so operations participate in transaction-bound resources.

### 10.5. Catching the exception inside the method itself

An internal `try/catch` can make the interceptor see a normal return. To request rollback after catching an error, you can use `TransactionAspectSupport.currentTransactionStatus().setRollbackOnly()`, though doing so couples business code to Spring; prefer expressing decisions at the transaction boundary/rules when appropriate.

### 10.6. Self-invocation or unproxyable methods

Calling `this.someTransactionalMethod()` inside the same object usually does not pass through the Spring proxy. Extract methods needing a transaction boundary into another Spring bean, or ensure external calls go through the proxy.

### 10.7. Inner `REQUIRED` joining an outer transaction

If an inner interceptor has already marked the shared transaction rollback-only, an outer method catching the exception and continuing **is not guaranteed to commit successfully**; at the end of the outer method `UnexpectedRollbackException` may be thrown. An inner `no-rollback-for` rule cannot override an outer rollback decision already made.

### 10.8. Checked exception unexpectedly commits

Changing a business exception from a `RuntimeException` subclass to an `Exception` subclass can change default behavior from rollback to commit. Whenever changing exception hierarchies, review XML rules and test database outcomes.

### 10.9. Transactional behavior does not cover off-DB side effects

JDBC rollback cannot retract emails, HTTP requests, or published messages. Those require separate outbox, idempotency, or compensation designs; `rollback-for` only governs the transaction Spring manages.

### 10.10. Misunderstanding `read-only`, `timeout`, and `isolation`

`read-only="true"` is usually only a hint and does not always prohibit SQL writes. `timeout` and `isolation` are bounded by the manager/driver and when a new transaction starts. When a `REQUIRED` method joins an outer transaction, inner metadata does not replace existing attributes by default.

## 11. Systematic debugging

If the data after throwing an exception **does not match expectations**:

1. **Did XML load successfully?** Check namespaces, `schemaLocation`, bean IDs, package/class names, and AOP/AspectJ dependencies.
2. **Is the service proxied?** Retrieve the bean from the Spring context. In debug code you can use `org.springframework.aop.support.AopUtils.isAopProxy(service)`.
3. **Does the pointcut match the call?** Check signature, interface, public visibility, and self-invocation.
4. **Does the advisor reference the right advice?** Check `advice-ref` and `pointcut-ref`.
5. **Which manager is selected?** `txAdvice.transaction-manager` must be the right bean, sharing the same `DataSource` as `JdbcTemplate`/DAO.
6. **Which `tx:method name` matches?** Identify exact method, wildcard, and fallback. Do not assume rules from multiple methods combine.
7. **What type is the actual exception?** Check checked/unchecked and class name/hierarchy against XML patterns.
8. **Is there an outer transaction or prior rollback-only?** Inner rules do not decide the outcome of the whole outer transaction.
9. **Test the database after the method finishes:** Run a SELECT on a connection outside the finished transaction. Do not just check that the method threw an exception or read uncommitted data inside the same transaction.

If using Spring Boot, you can increase logging in `application.properties`:

```properties
logging.level.org.springframework.transaction.interceptor=TRACE
logging.level.org.springframework.jdbc.datasource=DEBUG
```

**Note:** The `ClassPathXmlApplicationContext` project in this lesson does not automatically use Boot's logging properties; to trace in pure XML you must configure an appropriate logging backend. Logs only assist diagnosis and do not replace queries verifying committed data.

## 12. Short exercises with answers

**Exercise 1.** Remove `rollback-for` from `saveCheckedRollback` in XML and rerun on a fresh database. Does record id=3 remain?

**Answer:** Yes. `BusinessFailureException` is a checked exception, so by default Spring does not roll back solely because of that exception.

**Exercise 2.** Remove `no-rollback-for` from `saveUncheckedNoRollback` while keeping `rollback-for="java.lang.Throwable"`. Does record id=5 remain?

**Answer:** No. The broad rollback rule matches this exception, causing the transaction to roll back.

**Exercise 3.** Remove both rules from `saveUncheckedNoRollback`. Does it roll back?

**Answer:** Yes. The method throws a `RuntimeException` subclass, so the default rule rolls back.

**Exercise 4.** Change `name="saveCheckedRollback"` to `name="saveWrong"`; what happens?

**Answer:** The method actually falls into fallback `name="*"`; the checked exception again does not roll back by default and id=3 is committed.

**Exercise 5.** Can `rollback-for="*Exception"` be used as a wildcard?

**Answer:** No. `tx:method name` supports `*` for matching method names, whereas exception patterns do not have that wildcard semantics.

**Exercise 6.** Does `no-rollback-for="demo.NonFatalOperationException"` swallow the error and return normally?

**Answer:** No. The caller still receives the exception; the policy only determines how the transaction is handled.

**Exercise 7.** The outer transaction has already been marked `rollback-only`. Can you set `no-rollback-for` on the inner method to force the outer transaction to commit?

**Answer:** No. An inner rule does not clear the `rollback-only` state of the physical transaction.

**Exercise 8.** Only `<tx:advice>` is declared without `<aop:advisor>`. Will it automatically intercept every service call?

**Answer:** No. The advice must be bound to a pointcut to create a proxy applying the metadata.

## 13. References

- Spring Framework — Example of Declarative Transaction Implementation: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/first-example.html
- Spring Framework — Rolling Back a Declarative Transaction: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html
- Spring Framework — Settings of `<tx:advice>`: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/txadvice-settings.html
- Spring Framework — Using `@Transactional` and `<tx:annotation-driven>`: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html
- Spring Framework — Declarative transaction implementation/proxy: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html
- Spring Framework — JDBC connections and DataSource transaction manager: https://docs.spring.io/spring-framework/reference/data-access/jdbc/connections.html

**Remember:** The **Manager** chooses and controls transaction resources; the **pointcut/advisor** determines which calls are intercepted; **`tx:method`** carries the rollback policy. `rollback-for` adds rollback for exceptions that must discard data, while `no-rollback-for` excludes rollback for exceptions permitted to keep data. When rules overlap, Spring selects **the strongest rule for the actual exception**, not simply by XML order.
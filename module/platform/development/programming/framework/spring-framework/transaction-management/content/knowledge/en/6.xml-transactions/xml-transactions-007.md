# Comparing XML and Annotation Configurations for Identical Transaction Behavior in Spring Framework

A Spring application can use **XML** or **Java annotations** to declare transaction boundaries. The two configurations are truly equivalent only when they **select the same set of methods**, use the same **`TransactionManager` and data resource**, share the same **propagation/isolation/timeout/read-only/rollback rules**, and produce the **same commit or rollback outcome** when invoked through a Spring proxy.

This article focuses on **Spring Framework's** declarative transaction mechanism, with the main topic being **comparing XML and annotations for identical behavior**. The practical section uses Java 17+, Spring JDBC, H2, and a transfer service to compare the two configuration styles without needing an external database server.

## 1. Three configuration levels to distinguish

| Purpose | XML | Java / Annotation | Relationship |
| --- | --- | --- | --- |
| Declaring beans and dependencies | bean, constructor-arg, property | @Configuration, @Bean, constructor injection | Create the same objects |
| Declaring the transaction manager | JdbcTransactionManager/DataSourceTransactionManager bean | @Bean PlatformTransactionManager | Specify the same transaction resource |
| Specifying transaction policy by pointcut | tx:advice, tx:method, aop:pointcut, and aop:advisor | @Transactional on method/class | Two ways to describe the same transaction behavior |
| Enabling annotation processing | tx:annotation-driven | @EnableTransactionManagement | Two ways to activate reading `@Transactional` |
| Choosing class-based proxies | proxy-target-class="true" in AOP/tx XML config | proxyTargetClass=true on @EnableTransactionManagement | Choose how proxies are created in proxy mode |

Common point of confusion: **`tx:annotation-driven` is equivalent to `@EnableTransactionManagement` in its job of activating annotation processing**, **not** an alternative way of writing `@Transactional` itself. Conversely, **`tx:advice`** declares policies in XML; **`aop:advisor`** binds those policies to a pointcut that selects methods. No `@Transactional` is needed in Java source if pure XML advice is configured properly.

Diagram:

~~~text
Caller -> Spring AOP proxy -> TransactionInterceptor
                                  |
                       transaction attributes
                         /               \
                   XML tx:method     @Transactional
                         \               /
                          TransactionManager
                                |
                  DataSource -> JDBC Connection -> DBMS
                                |
                       commit / rollback / cleanup
~~~

Spring AOP can create a proxy and invoke the same `TransactionInterceptor` for both metadata sources. **The database executes the actual transaction**; XML/annotations only control how Spring selects and applies transaction policies.

## 2. Setting the comparison baseline: same problem, same policy

Suppose we have a `wallet` table:

| id | Initial balance |
| --- | ---: |
| 1 (A) | 100 |
| 2 (B) | 100 |

The **transfer(boolean fail)** method will:

1. Subtract 10 from A using an SQL UPDATE.
2. Add 10 to B using an SQL UPDATE.
3. If `fail=false`, finish normally so Spring commits.
4. If `fail=true`, throw `IllegalStateException` after both UPDATEs so Spring rolls back.

Target contract:

| Attribute | Identical Value for Both |
| --- | --- |
| TransactionManager | Bean named `transactionManager`, type `JdbcTransactionManager` |
| DataSource | H2 JDBC; manager and JdbcTemplate use the same DataSource in each context |
| Transaction boundary | Public `transfer(boolean)` method invoked through the bean proxy |
| Propagation | REQUIRED |
| Isolation | READ_COMMITTED |
| Timeout | 10 seconds |
| Read-only | false |
| Rollback rule | `IllegalStateException` triggers rollback when escaping the method |
| Proxy | Class-based proxy |
| Observed on success | A=90, B=110 |
| Observed after failure | A=90, B=110 because the update was rolled back |

Timeout and `READ_COMMITTED` here serve the example; they only take effect as supported by the manager and DBMS. In practice, choose policies according to business consistency requirements.

## 3. First approach: pure XML configuration with `tx:advice` and `aop:advisor`

The following XML file declares four beans and one advisor:

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

    <bean id="dataSource"
          class="org.springframework.jdbc.datasource.DriverManagerDataSource">
        <property name="driverClassName" value="org.h2.Driver"/>
        <property name="url" value="jdbc:h2:mem:xml_demo;DB_CLOSE_DELAY=-1"/>
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

    <bean id="transferService" class="demo.TransferService">
        <constructor-arg ref="jdbcTemplate"/>
    </bean>

    <tx:advice id="transferTxAdvice"
               transaction-manager="transactionManager">
        <tx:attributes>
            <tx:method name="transfer"
                       propagation="REQUIRED"
                       isolation="READ_COMMITTED"
                       timeout="10"
                       read-only="false"
                       rollback-for="java.lang.IllegalStateException"/>
        </tx:attributes>
    </tx:advice>

    <aop:config proxy-target-class="true">
        <aop:pointcut id="transferOperation"
                      expression="execution(* demo.TransferService.transfer(..))"/>
        <aop:advisor advice-ref="transferTxAdvice"
                     pointcut-ref="transferOperation"/>
    </aop:config>
</beans>
~~~

Understanding the configuration:

- **bean `dataSource`** provides JDBC Connections; **`jdbcTemplate`** and **`transactionManager`** both reference it. This is required for JDBC statements to participate in local transactions managed by Spring.
- **`tx:advice`** defines *which transaction behavior to apply* (propagation, isolation, timeout, rollback...). It does not yet choose where to apply it.
- **`tx:method name="transfer"`** selects method groups by **name** among the methods already selected by the pointcut. You can use `name="get*"`, `name="save*"`, or `name="*"` when genuinely intending to cover those groups.
- **`aop:pointcut`** specifies *which method executions* are selected; the expression here targets only **`demo.TransferService.transfer(..)`**.
- **`aop:advisor`** links the advice to the pointcut. Without it, declaring transaction attributes does not wrap the requested methods automatically.
- **`proxy-target-class="true"`** selects a class-based proxy (CGLIB) to match an interface-less service; proxy mode still has self-invocation limitations.

Notably, because the policy lives in XML, `demo.TransferService` is written as a POJO **without `@Transactional`**. However, you must actually load the XML file into an `ApplicationContext` and invoke the service through the Spring-managed bean.

## 4. Second approach: `@Transactional` and `@EnableTransactionManagement`

Instead of selecting methods via a pointcut in XML, we place the policy directly on the Java method:

~~~java
@Transactional(
        transactionManager = "transactionManager",
        propagation = Propagation.REQUIRED,
        isolation = Isolation.READ_COMMITTED,
        timeout = 10,
        readOnly = false,
        rollbackFor = IllegalStateException.class)
public void transfer(boolean fail) {
    // Executes the same UPDATE logic as the XML version.
}
~~~

This is a **snippet**; standalone runnable code requires the class, imports, DataSource, and Spring context. Equivalent annotation parameters:

| XML tx:method | Java Annotation |
| --- | --- |
| propagation="REQUIRED" | propagation = Propagation.REQUIRED |
| isolation="READ_COMMITTED" | isolation = Isolation.READ_COMMITTED |
| timeout="10" | timeout = 10 |
| read-only="false" | readOnly = false |
| rollback-for="java.lang.IllegalStateException" | rollbackFor = IllegalStateException.class |
| transaction-manager="transactionManager" on tx:advice | transactionManager = "transactionManager" on @Transactional |

Beans are created with `@Configuration`/`@Bean`; `@EnableTransactionManagement` activates annotation-driven proxies:

~~~java
@Configuration(proxyBeanMethods = false)
@EnableTransactionManagement(proxyTargetClass = true)
public class JavaConfig {
    @Bean
    public DataSource dataSource() {
        DriverManagerDataSource ds = new DriverManagerDataSource();
        ds.setDriverClassName("org.h2.Driver");
        ds.setUrl("jdbc:h2:mem:annotation_demo;DB_CLOSE_DELAY=-1");
        ds.setUsername("sa");
        ds.setPassword("");
        return ds;
    }

    @Bean
    public JdbcTemplate jdbcTemplate(DataSource ds) {
        return new JdbcTemplate(ds);
    }

    @Bean
    public PlatformTransactionManager transactionManager(DataSource ds) {
        return new JdbcTransactionManager(ds);
    }

    @Bean
    public AnnotatedTransferService transferService(JdbcTemplate jdbc) {
        return new AnnotatedTransferService(jdbc);
    }
}
~~~

This configuration is shown in full with imports in the runnable section. **`@EnableTransactionManagement` enables the infrastructure**, while **`@Transactional` is the policy**. If an application uses Spring Boot, transaction infrastructure may already be auto-configured; inspect the actual setup before adding overlapping configuration.

The two H2 URLs use different database names so both runs execute independently with identical initial data. That is not a transaction difference under comparison.

## 5. Runnable example with Java 17+, Maven, and H2

This section creates a Spring Framework program without Spring Boot. It reuses the exact same **business logic body** for both configurations by having the annotated class extend the unannotated class and call `super.transfer(...)`. Thus only the source of transaction metadata changes.

Directory structure:

~~~text
transaction-config-compare/
├── pom.xml
└── src/main/
    ├── java/demo/
    │   ├── TransferService.java
    │   ├── AnnotatedTransferService.java
    │   ├── JavaConfig.java
    │   └── ComparisonDemo.java
    └── resources/
        └── tx-xml.xml
~~~

### 5.1. Dependencies

**pom.xml**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>transaction-config-compare</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.12</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-aop</artifactId>
            <version>6.2.12</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <version>6.2.12</version>
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
                <version>3.5.1</version>
                <configuration>
                    <mainClass>demo.ComparisonDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**AspectJ Weaver** on the classpath supports evaluating XML pointcut expressions in Spring AOP; the example still runs in **proxy mode** and does not require AspectJ bytecode weaving for transactions.

### 5.2. Single shared business logic

**src/main/java/demo/TransferService.java**

~~~java
package demo;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.support.TransactionSynchronizationManager;

public class TransferService {
    private final JdbcTemplate jdbc;

    public TransferService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public void transfer(boolean fail) {
        if (!TransactionSynchronizationManager.isActualTransactionActive()) {
            throw new IllegalStateException("No active Spring transaction");
        }

        int debited = jdbc.update(
                "UPDATE wallet SET balance = balance - 10 WHERE id = ?", 1);
        int credited = jdbc.update(
                "UPDATE wallet SET balance = balance + 10 WHERE id = ?", 2);

        if (debited != 1 || credited != 1) {
            throw new IllegalStateException("Wallet row missing");
        }

        if (fail) {
            throw new IllegalStateException("simulated failure");
        }
    }
}
~~~

In the XML context, the advisor selects this **`TransferService.transfer`** method. In the annotation context, the overridden method has `@Transactional` and calls the exact code above via `super.transfer(fail)`. Both variants therefore run identical SQL.

`isActualTransactionActive()` detects if the method runs outside a Spring transaction in the demo; it does **not** replace verifying the DB after commit. Note that with imperative JDBC, transaction context is typically thread-bound. Do not assume calls dispatched to an `@Async` thread automatically join the transaction.

### 5.3. Actual runnable XML file

Save the exact file **`src/main/resources/tx-xml.xml`**:

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

    <bean id="dataSource"
          class="org.springframework.jdbc.datasource.DriverManagerDataSource">
        <property name="driverClassName" value="org.h2.Driver"/>
        <property name="url" value="jdbc:h2:mem:xml_demo;DB_CLOSE_DELAY=-1"/>
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

    <bean id="transferService" class="demo.TransferService">
        <constructor-arg ref="jdbcTemplate"/>
    </bean>

    <tx:advice id="transferTxAdvice" transaction-manager="transactionManager">
        <tx:attributes>
            <tx:method name="transfer"
                       propagation="REQUIRED"
                       isolation="READ_COMMITTED"
                       timeout="10"
                       read-only="false"
                       rollback-for="java.lang.IllegalStateException"/>
        </tx:attributes>
    </tx:advice>

    <aop:config proxy-target-class="true">
        <aop:pointcut id="transferOperation"
                      expression="execution(* demo.TransferService.transfer(..))"/>
        <aop:advisor advice-ref="transferTxAdvice"
                     pointcut-ref="transferOperation"/>
    </aop:config>
</beans>
~~~

### 5.4. Annotated service

**src/main/java/demo/AnnotatedTransferService.java**

~~~java
package demo;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.annotation.Isolation;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

public class AnnotatedTransferService extends TransferService {
    public AnnotatedTransferService(JdbcTemplate jdbc) {
        super(jdbc);
    }

    @Override
    @Transactional(
            transactionManager = "transactionManager",
            propagation = Propagation.REQUIRED,
            isolation = Isolation.READ_COMMITTED,
            timeout = 10,
            readOnly = false,
            rollbackFor = IllegalStateException.class)
    public void transfer(boolean fail) {
        super.transfer(fail);
    }
}
~~~

The overridden method is **public, non-final**, and called externally through the Spring bean; the interceptor opens the transaction before calling the superclass logic. There is no need to put `@Transactional` on the superclass in the XML branch.

### 5.5. Complete Java configuration

**src/main/java/demo/JavaConfig.java**

~~~java
package demo;

import javax.sql.DataSource;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.jdbc.support.JdbcTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;

@Configuration(proxyBeanMethods = false)
@EnableTransactionManagement(proxyTargetClass = true)
public class JavaConfig {
    @Bean
    public DataSource dataSource() {
        DriverManagerDataSource ds = new DriverManagerDataSource();
        ds.setDriverClassName("org.h2.Driver");
        ds.setUrl("jdbc:h2:mem:annotation_demo;DB_CLOSE_DELAY=-1");
        ds.setUsername("sa");
        ds.setPassword("");
        return ds;
    }

    @Bean
    public JdbcTemplate jdbcTemplate(DataSource ds) {
        return new JdbcTemplate(ds);
    }

    @Bean
    public PlatformTransactionManager transactionManager(DataSource ds) {
        return new JdbcTransactionManager(ds);
    }

    @Bean
    public AnnotatedTransferService transferService(JdbcTemplate jdbc) {
        return new AnnotatedTransferService(jdbc);
    }
}
~~~

### 5.6. Running both approaches

**src/main/java/demo/ComparisonDemo.java**

~~~java
package demo;

import org.springframework.aop.support.AopUtils;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.support.ClassPathXmlApplicationContext;
import org.springframework.jdbc.core.JdbcTemplate;

public final class ComparisonDemo {
    private ComparisonDemo() {}

    public static void main(String[] args) {
        try (var xml = new ClassPathXmlApplicationContext("tx-xml.xml")) {
            run("XML", xml);
        }

        try (var javaConfig =
                new AnnotationConfigApplicationContext(JavaConfig.class)) {
            run("Annotation", javaConfig);
        }
    }

    private static void run(String label, ConfigurableApplicationContext context) {
        JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);
        TransferService service =
                context.getBean("transferService", TransferService.class);

        jdbc.execute("CREATE TABLE wallet ("
                + "id INT PRIMARY KEY, "
                + "balance INT NOT NULL CHECK (balance >= 0))");
        jdbc.update("INSERT INTO wallet(id, balance) VALUES (?, ?)", 1, 100);
        jdbc.update("INSERT INTO wallet(id, balance) VALUES (?, ?)", 2, 100);

        System.out.println(label + " proxy=" + AopUtils.isAopProxy(service));
        show(label + " initial", jdbc);

        service.transfer(false);
        show(label + " after commit", jdbc);

        try {
            service.transfer(true);
        } catch (IllegalStateException expected) {
            System.out.println(label + " caught: " + expected.getMessage());
        }
        show(label + " after rollback", jdbc);
    }

    private static void show(String label, JdbcTemplate jdbc) {
        Integer a = jdbc.queryForObject(
                "SELECT balance FROM wallet WHERE id = ?", Integer.class, 1);
        Integer b = jdbc.queryForObject(
                "SELECT balance FROM wallet WHERE id = ?", Integer.class, 2);
        System.out.printf("%s: A=%d, B=%d%n", label, a, b);
    }
}
~~~

From the **transaction-config-compare** directory, run:

~~~bash
mvn -q compile exec:java
~~~

**Stdout lines printed by the program itself** (excluding framework or Maven logs):

~~~text
XML proxy=true
XML initial: A=100, B=100
XML after commit: A=90, B=110
XML caught: simulated failure
XML after rollback: A=90, B=110
Annotation proxy=true
Annotation initial: A=100, B=100
Annotation after commit: A=90, B=110
Annotation caught: simulated failure
Annotation after rollback: A=90, B=110
~~~

Explanation:

1. **`AopUtils.isAopProxy(service)=true`** shows that both approaches create Spring proxies. This is necessary but not sufficient to prove transactions work; hence the method also checks `isActualTransactionActive()`.
2. **`transfer(false)`** executes two UPDATEs on the connection coordinated by the transaction manager, then commits. New balances: A=90, B=110.
3. **`transfer(true)`** executes two UPDATEs and then throws `IllegalStateException`; both XML `rollback-for` and annotation `rollbackFor` mandate rollback, so balances afterward stay A=90, B=110.
4. The two `ApplicationContext` instances use two **differently named** H2 DBs so each run initializes identical data. That avoids the two runs overwriting each other's table during comparison.
5. Data is read back **after the transactional method completes**. This verifies durable state in the example better than merely looking for the words "commit" or "rollback" in logs.

**`DriverManagerDataSource` is not a connection pool** and is used here only to minimize dependencies in the demo. In production environments, use an appropriately pooled `DataSource`; the transaction manager and repository must still point to the exact same resource.

## 6. Another equivalent pair: XML enabling `@Transactional`

There are two XML models to distinguish:

**Model A — policy in XML:** `tx:advice` + `tx:method` + `aop:pointcut` + `aop:advisor`. The Java service needs no `@Transactional`.

**Model B — policy remains `@Transactional`, XML only enables annotation reading:**

~~~xml
<!-- Placed inside <beans> with the tx namespace, while declaring transactionManager
     and service beans in the same appropriate ApplicationContext. -->
<tx:annotation-driven transaction-manager="transactionManager"
                      proxy-target-class="true"/>
~~~

Model B is closely equivalent to Java:

~~~java
@EnableTransactionManagement(proxyTargetClass = true)
// This annotation sits on a @Configuration class that declares the appropriate manager.
~~~

If services already have `@Transactional` while the project still wires beans in XML, Model B lets you **combine XML bean wiring with annotation method policies**. You do not have to rewrite all XML into `@Bean` methods just to enable annotations. However, simply adding `tx:annotation-driven` without `@Transactional` on methods will not create transaction boundaries like the XML advisor in Model A.

Table:

| Policy Source | Infrastructure Required | When to Use |
| --- | --- | --- |
| XML tx:method | XML tx:advice + AOP advisor | Want to control policies outside Java source |
| Java @Transactional | XML tx:annotation-driven | XML bean wiring with policies placed on methods |
| Java @Transactional | @EnableTransactionManagement | Java/annotation configuration |
| Java @Transactional | Compatible Spring Boot transaction auto-configuration | Boot already configures transaction management |

In proxy mode, everything still requires calls to pass through the bean proxy. **An annotation keyword in source code alone does not make an object created with `new` transactional.**

## 7. XML and annotation attributes must match completely

| XML tx:method / tx:advice | Java @Transactional | Notes |
| --- | --- | --- |
| name="transfer" | Placed on `transfer` method | XML also requires pointcut matching |
| name="get*" read-only="true" | @Transactional(readOnly=true) on matching getters | Must enumerate/locate the exact methods covered by XML |
| propagation="REQUIRED" | propagation=Propagation.REQUIRED | Joins existing transaction or opens a new one |
| propagation="REQUIRES_NEW" | propagation=Propagation.REQUIRES_NEW | Independent transaction if manager supports suspending |
| propagation="NESTED" | propagation=Propagation.NESTED | Savepoint if transaction manager/driver supports it |
| isolation="READ_COMMITTED" | isolation=Isolation.READ_COMMITTED | Applies when opening a new physical transaction; DBMS decides details |
| timeout="10" | timeout=10 | Seconds; enforcement level depends on resource |
| read-only="false" | readOnly=false | Do not use `readOnly` in place of DB permissions |
| rollback-for="com.example.BusinessCheckedException" | rollbackFor=BusinessCheckedException.class | Adds rollback for checked exceptions |
| no-rollback-for="com.example.ExpectedException" | noRollbackFor=ExpectedException.class | Exception may escape without triggering rollback |
| transaction-manager="billingTxManager" | transactionManager="billingTxManager" | Specifies the exact manager and resource |

**Do not mechanically convert an XML name pattern into class-level `@Transactional`.** For example, if XML makes `get*` read-only and other methods read-write, turning the whole class into `readOnly=true` changes the policy for write operations.

**Do not overlook rollback rules.** By default in common cases, `@Transactional` rolls back for `RuntimeException` and `Error`, whereas checked `Exception` types usually do not trigger rollback automatically. If XML had `rollback-for` for a checked exception, the annotation version must have `rollbackFor`, or an equivalent default rollback configuration. Specific exception rules must be verified when exception inheritance is involved.

**Do not confuse propagation and isolation.** Propagation governs relationships between nested method calls; isolation regulates how concurrent transactions read/write data. A `REQUIRED` method joining an outer transaction usually cannot reapply a new isolation level to an already-existing physical transaction.

**Do not treat `readOnly=true` as a guaranteed write block.** Its effect depends on the Spring manager, JDBC driver, and DBMS; use DB permissions or real constraints if writes must be forbidden.

## 8. Pointcut scope is the biggest difference when migrating

XML can configure transactions for an entire group of beans without editing Java code:

~~~xml
<tx:advice id="serviceTx" transaction-manager="transactionManager">
    <tx:attributes>
        <tx:method name="find*" read-only="true"/>
        <tx:method name="get*" read-only="true"/>
        <tx:method name="*" propagation="REQUIRED"/>
    </tx:attributes>
</tx:advice>

<aop:config>
    <aop:pointcut id="serviceMethods"
                  expression="execution(* com.example.service.*.*(..))"/>
    <aop:advisor advice-ref="serviceTx" pointcut-ref="serviceMethods"/>
</aop:config>
~~~

**The actual scope** is the intersection of two conditions: a method matches **`aop:pointcut`** and matches a **`tx:method`**. In the example, `find*`/`get*` receive `readOnly` and other names receive the general policy. When migrating to annotations, list the currently selected methods, identify read-only methods, and place `@Transactional` accurately (on the class with method overrides where appropriate). Putting an annotation on a class can accidentally wrap methods that XML previously did not match.

With multiple modules, package names, subclasses, interfaces, overloaded methods, or beans using JDK dynamic proxies, re-test the actual method scope. Do not assume a pointcut expression is equivalent to putting `@Transactional` on every service.

### Where is XML still useful?

XML is useful when configuring policies from outside Java source (for example applying to library classes managed by Spring) or when a large pattern-based rule set is desired. Annotations close to code are convenient for reading per-method policies and spotting impact when refactoring names. Both can be right as long as the contract is clearly defined.

## 9. Proxies, `ApplicationContext`, and duplicate configuration

### 9.1. Self-invocation

In proxy mode, external calls to a bean can be intercepted, but:

~~~java
// Illustrative snippet, not a standalone program.
public void outer() {
    this.inner();
}

@Transactional(propagation = Propagation.REQUIRES_NEW)
public void inner() {
    // ...
}
~~~

If `outer()` calls `inner()` directly on `this`, the transaction metadata on `inner` is usually **not intercepted** as a proxy call. The same holds for XML advice when an internal call inside the same target object bypasses the proxy. Design service boundaries across another bean/proxy when an independent transaction is needed.

Private/final methods and beans not managed by the container also risk not being intercepted depending on proxy type; verify interception capabilities for your actual framework version.

### 9.2. Context containing the service

`@EnableTransactionManagement` or `tx:annotation-driven` discovers transactional beans in the **configured `ApplicationContext`**. Placing them in a controller-only child context while services live in the parent context can prevent services from being advised properly. When migrating XML, know which context loads the service beans and which loads the transaction infrastructure.

### 9.3. Do not accidentally create two advisors for the same method

If you keep XML `tx:advice` + `aop:advisor` and also add `@Transactional` and enable annotation-driven processing for the same methods, the system may end up with **two transactional advisors** intercepting a single call. Advisor order, logical transaction scopes, and logs may change. Establish one clear source of policy and test it, rather than enabling everything "just to be safe."

In applications with security, caching, or custom AOP, review **advice order** if behavior depends on which runs first. Class-based proxies and JDK proxies also differ in types/casting, so verify the API clients consume.

## 10. When there are multiple transaction managers

XML advice can specify:

~~~xml
<tx:advice id="billingAdvice" transaction-manager="billingTxManager">
    <tx:attributes>
        <tx:method name="settle" propagation="REQUIRED"/>
    </tx:attributes>
</tx:advice>
~~~

Equivalent annotation:

~~~java
// Snippet inside a Spring-managed service.
@Transactional(transactionManager = "billingTxManager")
public void settle() {
    // Accesses the billing repository.
}
~~~

The two approaches are only equivalent when **`billingTxManager`** points to the same resource as the repository. If the Java annotation omits the qualifier and picks a default manager for another `DataSource`, transactions may open on the wrong DB even though logs still show "Creating new transaction."

With two independent `DataSource` beans, a local manager cannot automatically make operations atomic across both. If multi-resource coordination is genuinely required, evaluate JTA/XA or consistency designs such as transactional outbox/saga according to system requirements.

## 11. Testing behavior after conversion

Do not merely verify that the XML file parses or `@Transactional` appears in source code. Meaningful verification should prove:

1. **Bean proxy:** invoke the Spring bean, check `AopUtils.isAopProxy(...)` or `TransactionInterceptor` logs.
2. **Entry boundary:** inside the method, Spring's transaction context is active when expected.
3. **Real commit:** after a successful write, open another connection/transaction to read the persisted data.
4. **Real rollback:** intentionally throw an exception after a second operation and verify neither uncommitted change remains.
5. **Checked exception:** when the policy includes `rollback-for`/`rollbackFor`, test the corresponding checked exception.
6. **Nested propagation:** if `REQUIRED`, `REQUIRES_NEW`, or `NESTED` is used, verify physical transactions and savepoint behavior.
7. **Right manager:** verify the actual manager bean, `DataSource`, and JPA provider used.
8. **No unintended transactions:** methods that did not match the previous XML pointcut must retain their expected behavior after conversion.

You can enable logging in Spring Boot in a test environment:

~~~properties
logging.level.org.springframework.transaction.interceptor=TRACE
logging.level.org.springframework.jdbc.datasource=DEBUG
logging.level.org.springframework.jdbc.support=DEBUG
~~~

Lines like *Creating new transaction*, *Getting transaction for*, *Initiating transaction commit*, *Initiating transaction rollback*, and *Releasing JDBC Connection* help trace context. **Log messages initiating commit are not final proof if commit itself throws an exception**; read the database back.

If the test class itself is `@Transactional` and the test framework rolls back automatically at the end of the test, do not use queries running inside that same test transaction to claim a physical commit succeeded. Design integration tests reading from an independent transaction or connection when needed.

## 12. Common errors and how to diagnose them

| Symptom | Possible Cause | What to Check |
| --- | --- | --- |
| XML works, annotation is ignored | Forgot to enable annotation transactions, bean outside context, self-invocation | @EnableTransactionManagement/tx:annotation-driven, AOP proxy, call stack |
| Annotation rolls back but XML commits | XML missing rollback-for, pointcut matches wrong methods | Policy + actual exception escaping the boundary |
| XML rolls back but annotation commits | Omitted rollbackFor when converting checked exception | Match exception classes and rollback rules |
| XML advisor does nothing | Missing aop:advisor, missing aspectjweaver, or pointcut does not match | Context loading, advisor, AOP expression, proxy |
| Two setups hit different DBs | Wrong TransactionManager bean or DataSource wiring | Match bean names, JDBC URLs, repositories |
| Annotation adds transactions to too many methods | Placed @Transactional on class too broadly | List XML pointcut matches prior to migration |
| UnexpectedRollbackException | Inner REQUIRED marked rollback-only | Check transaction propagation and where setRollbackOnly happened |
| NESTED unsupported | Transaction manager/driver does not support savepoints | Check manager and JDBC savepoint capability |
| New transaction does not start | Internal call bypasses proxy or joins REQUIRED | Inspect proxy/advisor, transaction owner |
| One request intercepted twice | Both XML advice and annotation advice apply | List advisors, clarify policy owner |
| Commit logged yet balances look wrong | Different SQL/DB, lock/race, or indeterminate commit result | SQL update counts and independent database readback |

**Useful diagnostic chain:** service bean → AOP proxy/advisor → policy metadata → TransactionManager → DataSource/Connection → SQL → commit/rollback → data read after transaction. Every link must align before claiming "XML and annotations have identical behavior."

## 13. Knowledge self-check

**1. Is `tx:annotation-driven` the same thing as `@Transactional`?**  
No. It is the XML way to enable processing `@Transactional`, functionally equivalent to `@EnableTransactionManagement`. XML `tx:advice`/`tx:method` + AOP advisor is the model for declaring policies in XML.

**2. Does XML `tx:method name="transfer"` apply to every bean that has a `transfer` method?**  
Not automatically. It only applies where the advisor/pointcut matches, uses the right manager, and the bean is proxied by Spring.

**3. Why does the example with XML policy roll back even though `TransferService` has no `@Transactional`?**  
Because the XML advisor wraps calls from callers to the Spring proxy and passes the policy to `TransactionInterceptor`; the method runs inside the transaction opened by the manager.

**4. Can you declare beans in XML while still putting `@Transactional` on methods?**  
Yes. Use `tx:annotation-driven` with the transaction manager and service beans in the right context, or an equivalent annotation-transaction activation mechanism.

**5. Why must `rollbackFor` and `rollback-for` match when checked exceptions are involved?**  
Because Spring does not roll back checked `Exception` types by default. If one side declares the rule and the other omits it, one may roll back while the other commits.

**6. Does `AopUtils.isAopProxy(bean)=true` prove that the method's transaction works?**  
No. The proxy could exist for another advice, or the pointcut might not select that method. You must verify the interceptor/context and commit/rollback against the database.

**7. If both configurations have the same policy yet use two different `DataSource`s, are they equivalent?**  
Not regarding resources. Two databases can yield identical demo output from identical seed data, but in a real application you must verify the manager and repository use the intended resource.

**8. Can you convert XML `name="get*" read-only=true` into `@Transactional(readOnly=true)` on the entire service?**  
Only when the entire service genuinely has an equivalent policy. If write methods also reside in the class, class-level `readOnly=true` can change behavior.

## 14. Practical conclusion

Comparing XML and annotations in Spring transactions does not stop at syntax:

- **Beans and resources:** XML bean/ref ↔ Java `@Bean`/injection, sharing the same DataSource and TransactionManager.
- **Policy:** XML `tx:method` + AOP pointcut/advisor ↔ `@Transactional` on the exact methods/classes; keeping propagation, isolation, timeout, and rollback identical.
- **Annotation activation:** XML `tx:annotation-driven` ↔ Java `@EnableTransactionManagement`.
- **Behavior:** confirm Spring proxy, active transaction, commit/rollback, and DB readback.
- **Safe migration:** audit all pointcut matches, avoid accidentally broadening annotation scope, avoid duplicate advisors, and verify on the real DBMS.

In the complete runnable example, both configurations commit when no error occurs and both roll back when `IllegalStateException` escapes the method. This proves identical behavior for the defined contract, whether the policy source is XML or annotations.

## References

- [Spring Framework — Declarative Transaction Implementation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html)
- [Spring Framework — Declarative Transaction XML Example](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/first-example.html)
- [Spring Framework — Using @Transactional](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html)
- [Spring Framework — Schema-based AOP Support](https://docs.spring.io/spring-framework/reference/core/aop/schema.html)
- [Spring Framework — Transaction Propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html)
- [Spring Framework — Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html)

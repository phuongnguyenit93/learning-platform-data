# Enabling Annotations with `<tx:annotation-driven>` in Spring Framework (XML Configuration)

In Spring Framework, `@Transactional` lets you declare transaction boundaries directly on a Java class or method. However, **merely writing `@Transactional` is not enough**: the container must enable the infrastructure to read annotations, create transaction advice/proxies, and know which transaction manager to use. When an application is configured with XML, the **`<tx:annotation-driven/>`** element is the direct way to enable that mechanism.

This article focuses on **XML configuration in Spring transaction management**. The emphasis is on declaring the `tx` namespace correctly, wiring it to a `PlatformTransactionManager`, how Spring creates proxies, and when `@Transactional` actually takes effect. The complete example uses Spring Framework 6.2, Java 17, JDBC, and H2 so you can observe commit and rollback behavior yourself.

## 1. What problem does `<tx:annotation-driven/>` solve?

Consider a business service:

```java
@Service
public class PaymentService {
    @Transactional
    public void pay() {
        // write payment record
        // update balance
    }
}
```

This is **illustrative code**, not a standalone runnable program. The intended meaning is that both DB operations run within the same transaction. However:

- `@Transactional` only supplies **metadata**: propagation, isolation, `readOnly`, timeout, rollback rules, and an optional transaction manager.
- Spring must register the annotation-aware infrastructure, create the advisor/interceptor, and decide which beans need proxying.
- There must be a **suitable transaction manager** for the data access infrastructure. For local JDBC transactions, this is e.g. `JdbcTransactionManager`/`DataSourceTransactionManager`; for JPA, it is typically `JpaTransactionManager`.
- Method calls must **go through the Spring proxy** when using the default `proxy` mode.
- The DAO/repository must access a compatible resource so the operations actually participate in the same transaction.

`<tx:annotation-driven/>` solves the part of **enabling annotation-driven declarative transactions** at the application context level. It does not replace a transaction manager, does not automatically create a datasource, does not write SQL for you, and does not turn every direct method call into a transactional call.

Overview flow:

```text
XML ApplicationContext
   |
   +-- <tx:annotation-driven/>: registers transaction infrastructure
   |         |
   |         +-- transaction attribute source: reads @Transactional
   |         +-- transaction advisor + TransactionInterceptor
   |         +-- auto-proxy for matching Spring beans
   |
   +-- <bean id="transactionManager" .../>
   |         |
   |         +-- manages DataSource/EntityManager/transaction backend
   |
   +-- @Service/@Repository or bean declared in XML
             |
Caller --> service proxy --> TransactionInterceptor
                                 |
                                 +-- getTransaction(...)
                                 +-- invoke target method
                                 +-- commit / rollback
                                 +-- resource cleanup
```

This element is required for **transaction annotation infrastructure**; it is not synonymous with `<context:annotation-config/>` (dependency injection and bean configuration annotations) or `<aop:aspectj-autoproxy/>` (enabling aspect processing). Those elements **do not automatically replace** the transaction interceptor registered by `<tx:annotation-driven/>`.

## 2. Minimal XML configuration and the meaning of each piece

An XML file can be structured as follows:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xmlns:tx="http://www.springframework.org/schema/tx"
       xmlns:context="http://www.springframework.org/schema/context"
       xsi:schemaLocation="
           http://www.springframework.org/schema/beans
           https://www.springframework.org/schema/beans/spring-beans.xsd
           http://www.springframework.org/schema/tx
           https://www.springframework.org/schema/tx/spring-tx.xsd
           http://www.springframework.org/schema/context
           https://www.springframework.org/schema/context/spring-context.xsd">

    <context:component-scan base-package="demo.tx"/>

    <bean id="dataSource"
          class="org.springframework.jdbc.datasource.DriverManagerDataSource">
        <property name="driverClassName" value="org.h2.Driver"/>
        <property name="url" value="jdbc:h2:mem:txdemo;DB_CLOSE_DELAY=-1"/>
        <property name="username" value="sa"/>
        <property name="password" value=""/>
    </bean>

    <bean id="transactionManager"
          class="org.springframework.jdbc.support.JdbcTransactionManager">
        <constructor-arg ref="dataSource"/>
    </bean>

    <bean id="jdbcTemplate"
          class="org.springframework.jdbc.core.JdbcTemplate">
        <constructor-arg ref="dataSource"/>
    </bean>

    <tx:annotation-driven transaction-manager="transactionManager"/>
</beans>
```

The example illustrates a **single application context** with JDBC/H2. The components are:

1. **`xmlns:tx` and `spring-tx.xsd`** register the transaction namespace syntax so the XML parser understands the `tx:annotation-driven` element. The `tx` prefix must point to the exact URI `http://www.springframework.org/schema/tx`; the prefix name is a convention, while the namespace URI determines the meaning.
2. **`xmlns:context` together with `<context:component-scan>`** instructs the container to find classes annotated with `@Component`, `@Service`, `@Repository`, etc. under the `demo.tx` package. You can use `<bean .../>` instead of component scanning to register each service individually; `<tx:annotation-driven/>` does not depend on how the bean is registered.
3. **`dataSource`** provides JDBC connections. `DriverManagerDataSource` is suitable for small examples without a connection pool; production applications should use an appropriate pool/configuration.
4. **`transactionManager`** is the Spring bean implementing the `PlatformTransactionManager` contract. Here `JdbcTransactionManager` manages local transactions for that same `dataSource`.
5. **`jdbcTemplate`** obtains connections through Spring's JDBC infrastructure and can use the connection bound to the current transaction.
6. **`<tx:annotation-driven transaction-manager="transactionManager"/>`** enables `@Transactional` processing infrastructure and specifies the default manager bean to use.

A point you cannot overlook: `transactionManager` and `jdbcTemplate` in this configuration **reference the exact same `dataSource` bean**. If a DAO obtains a separate connection from another source or uses an incompatible manager, the annotation may be present while the data operations do not participate in the transaction you expect.

### Can it be shortened to `<tx:annotation-driven/>`?

Yes, when the default transaction manager bean is named **`transactionManager`**:

```xml
<bean id="transactionManager"
      class="org.springframework.jdbc.support.JdbcTransactionManager">
    <constructor-arg ref="dataSource"/>
</bean>

<tx:annotation-driven/>
```

According to the namespace documentation, the default value of the `transaction-manager` attribute is the bean name `transactionManager`. If you give it another name (for example `ordersTxManager`), you should declare it explicitly:

```xml
<bean id="ordersTxManager"
      class="org.springframework.jdbc.support.JdbcTransactionManager">
    <constructor-arg ref="ordersDataSource"/>
</bean>

<tx:annotation-driven transaction-manager="ordersTxManager"/>
```

The two snippets above are **configuration fragments**; you must define `dataSource`/`ordersDataSource` and the corresponding `<beans>`/namespace declarations in an actual file.

> Do not assume that setting `id="transactionManager"` creates transactions by itself: the manager bean must have a valid class, dependencies, and resource; `<tx:annotation-driven/>` only connects the annotation infrastructure to that manager.

## 3. Standalone runnable example: XML enables commit and rollback

The example uses **JDK 17+**, **Maven 3.9+**, **Spring Framework 6.2.14**, and in-memory H2. Spring Boot auto-configuration is not used so it is clear that `<tx:annotation-driven/>` itself is the configuration enabling transactions; the sample data lives only in an in-memory database.

Goal: a service debits A and then credits B. When `IllegalStateException` is thrown between the two statements, the transaction rolls back. When it succeeds, both changes are committed.

Exact structure:

```text
tx-xml-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── demo/
        │       └── tx/
        │           ├── Main.java
        │           └── TransferService.java
        └── resources/
            └── spring-tx.xml
```

### 3.1. Maven dependencies

File `pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="
             http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>tx-xml-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <spring.version>6.2.14</spring.version>
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
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <version>2.3.232</version>
            <scope>runtime</scope>
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

`spring-context` provides the XML container/component scanning; `spring-jdbc` provides `JdbcTemplate`, `DriverManagerDataSource`, and the JDBC transaction manager, pulling in the required Spring modules for transactions. H2 is the runtime-only JDBC driver/database. A real application should keep dependency management/BOM consistent if multiple Spring modules are used.

### 3.2. Complete XML configuration

File `src/main/resources/spring-tx.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xmlns:tx="http://www.springframework.org/schema/tx"
       xmlns:context="http://www.springframework.org/schema/context"
       xsi:schemaLocation="
           http://www.springframework.org/schema/beans
           https://www.springframework.org/schema/beans/spring-beans.xsd
           http://www.springframework.org/schema/tx
           https://www.springframework.org/schema/tx/spring-tx.xsd
           http://www.springframework.org/schema/context
           https://www.springframework.org/schema/context/spring-context.xsd">

    <context:component-scan base-package="demo.tx"/>

    <bean id="dataSource"
          class="org.springframework.jdbc.datasource.DriverManagerDataSource">
        <property name="driverClassName" value="org.h2.Driver"/>
        <property name="url" value="jdbc:h2:mem:transfer_demo;DB_CLOSE_DELAY=-1"/>
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

    <tx:annotation-driven transaction-manager="transactionManager"/>
</beans>
```

`DB_CLOSE_DELAY=-1` keeps the H2 in-memory database alive for the lifetime of the JVM even when connections used outside a transaction are closed after each operation. This allows reading balances back with `JdbcTemplate` without holding a fixed connection. In production, manage a proper connection pool and lifecycle instead of `DriverManagerDataSource`.

### 3.3. Annotated service

File `src/main/java/demo/tx/TransferService.java`:

```java
package demo.tx;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class TransferService {
    private final JdbcTemplate jdbc;

    public TransferService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void transfer(int fromId, int toId, int amount, boolean fail) {
        if (amount <= 0 || fromId == toId) {
            throw new IllegalArgumentException("invalid transfer");
        }

        int debitRows = jdbc.update(
                "UPDATE accounts SET balance = balance - ? WHERE id = ?",
                amount, fromId);

        if (debitRows != 1) {
            throw new IllegalArgumentException("source account missing");
        }

        if (fail) {
            throw new IllegalStateException("simulated failure");
        }

        int creditRows = jdbc.update(
                "UPDATE accounts SET balance = balance + ? WHERE id = ?",
                amount, toId);

        if (creditRows != 1) {
            throw new IllegalArgumentException("destination account missing");
        }
    }
}
```

`@Service` makes the class discoverable by `component-scan`. Having a single constructor lets Spring perform constructor injection without `@Autowired`. `@Transactional` on the public method tells Spring to create a transaction boundary around calls going through the proxy.

### 3.4. Program invoking the service through the Spring container

File `src/main/java/demo/tx/Main.java`:

```java
package demo.tx;

import org.springframework.context.support.ClassPathXmlApplicationContext;
import org.springframework.jdbc.core.JdbcTemplate;

public class Main {
    public static void main(String[] args) {
        try (ClassPathXmlApplicationContext context =
                     new ClassPathXmlApplicationContext("spring-tx.xml")) {

            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);

            jdbc.execute("""
                    CREATE TABLE accounts (
                        id INT PRIMARY KEY,
                        balance INT NOT NULL
                    )
                    """);

            jdbc.update("INSERT INTO accounts (id, balance) VALUES (?, ?)", 1, 100);
            jdbc.update("INSERT INTO accounts (id, balance) VALUES (?, ?)", 2, 50);

            TransferService service = context.getBean(TransferService.class);

            printBalances(jdbc, "BEFORE");

            try {
                service.transfer(1, 2, 30, true);
            } catch (IllegalStateException expected) {
                System.out.println("THROW=" + expected.getMessage());
            }
            printBalances(jdbc, "AFTER_ROLLBACK");

            service.transfer(1, 2, 30, false);
            printBalances(jdbc, "AFTER_COMMIT");
        }
    }

    private static void printBalances(JdbcTemplate jdbc, String label) {
        Integer a = jdbc.queryForObject(
                "SELECT balance FROM accounts WHERE id = 1", Integer.class);
        Integer b = jdbc.queryForObject(
                "SELECT balance FROM accounts WHERE id = 2", Integer.class);

        System.out.println(label + ": A=" + a + ", B=" + b);
    }
}
```

Run in the `tx-xml-demo` directory:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.tx.Main
```

Lines **printed by the program itself**, excluding library/Maven logs:

```text
BEFORE: A=100, B=50
THROW=simulated failure
AFTER_ROLLBACK: A=100, B=50
AFTER_COMMIT: A=70, B=80
```

Explanation following the exact execution path:

1. `Main` initializes `ClassPathXmlApplicationContext`, causing Spring to parse `spring-tx.xml`, register the service, datasource, JDBC template, and manager; `<tx:annotation-driven/>` enables the transaction infrastructure.
2. The two `INSERT` statements set up the initial data. `context.getBean(TransferService.class)` retrieves the **Spring-managed service bean**, the object that the transaction auto-proxy can wrap.
3. On `service.transfer(..., true)`: the interceptor opens a transaction; `JdbcTemplate` performs the debit using the connection belonging to the transaction; `IllegalStateException` exits the method before the credit. Spring rolls back by default on `RuntimeException`, so the balances remain 100 and 50.
4. On `service.transfer(..., false)`: both debit and credit run normally, the interceptor asks the manager to commit, and the balances become 70 and 80.
5. The service **never calls `begin()`, `commit()`, or `rollback()` manually**: annotation metadata + XML infrastructure + the transaction manager handle that part.

In the demo, `TransferService` does not implement an interface; when a proxy is needed, Spring can use a class-based proxy for this object even though `proxy-target-class` is not enabled. Do not test this by casting/comparing proxy class names; instead observe rollback behavior or use `AopUtils.isAopProxy(bean)` in a diagnostic environment.

**Limitations of the example:** it does not check for sufficient funds, concurrent locking, optimistic locking, or duplicate transfers. This is an example for understanding transaction activation, not production-ready funds-transfer business code.

### 3.5. Try disabling `<tx:annotation-driven/>` to see the difference

In a **copy of the demo** using a fresh H2 DB, remove or comment out just one line:

```xml
<tx:annotation-driven transaction-manager="transactionManager"/>
```

At this point the method still has `@Transactional`, but the XML context no longer enables transaction annotation infrastructure. In the demo's `DriverManagerDataSource` + `JdbcTemplate` setup, each `UPDATE` outside a Spring transaction uses a connection with default JDBC auto-commit. When an exception occurs between the two `UPDATE` statements, the debit may have already committed individually while the credit has not run; the total balance is no longer consistent. That is the clearest illustration of the difference between **annotation metadata** and **annotation execution infrastructure**.

Note: if the application has another transaction configuration (Java `@EnableTransactionManagement`, another proxy/transaction advice, Spring Boot auto-configuration, container-managed transactions), removing one XML line **does not guarantee** turning off all transactions. The experiment above only has a deterministic conclusion in the minimal context presented.

## 4. How does Spring process `<tx:annotation-driven>`?

When reading XML, Spring uses a namespace handler/parser mechanism to register the infrastructure for processing transaction annotations. In the default `proxy` mode, conceptually there are:

- **Transaction annotation attribute source:** reads metadata on classes/methods, such as `@Transactional(propagation=..., rollbackFor=...)`.
- **Transaction advisor:** determines which calls need advice applied based on the metadata.
- **`TransactionInterceptor`:** wraps the invocation, interacting with the transaction manager before/after the method is called.
- **Auto-proxy creator:** creates proxies for matching beans so callers go through the interceptor.
- **Transaction manager:** works with the actual transaction and data resources; the infrastructure typically selects the XML default manager or the manager qualified in `@Transactional`.

This is a **logical model**; it does not mean every `@Transactional` method corresponds to a physical transaction or that Spring must create a separate proxy per annotation. The manager also has to check propagation and whether a transaction already exists.

Timeline of a `REQUIRED` call with no prior transaction:

```text
1. caller -> proxy.placeOrder()
2. interceptor resolves @Transactional for method
3. manager.getTransaction(definition)
4. manager opens local JDBC transaction or works with appropriate resource backend
5. interceptor -> target.placeOrder()
6. target -> repository/JdbcTemplate -> DB operations inside transaction
7. method return: manager.commit(status)
   method throws exception matching rollback rule: manager.rollback(status)
8. manager releases transaction resource, proxy returns result/exception
```

If a transaction already exists and `@Transactional` uses `Propagation.REQUIRED`, the new scope **joins the existing transaction**. `@Transactional` does not promise that every method gets an independent transaction. This is a characteristic of the transaction model, not a specific property of XML.

For JDBC, `JdbcTemplate` works through the `DataSourceUtils` mechanism to obtain the connection appropriate for the transaction bound to the current thread. If code obtains a connection from another datasource or creates a connection outside Spring's infrastructure, that operation may not belong to the transaction just opened.

## 5. Attributes of `<tx:annotation-driven>` and default values

This is the set of important XML element attributes; they should be kept distinct from **attributes of `@Transactional` itself**.

| XML Attribute | Default | What is it used for? |
| --- | --- | --- |
| `transaction-manager` | `transactionManager` | Specifies the default transaction manager bean name for annotations that do not specify a particular manager. |
| `mode` | `proxy` | Chooses processing via Spring AOP proxies or `aspectj` weaving. |
| `proxy-target-class` | `false` | In `proxy` mode, prefers class-based proxies when `true`; `false` usually prefers JDK interface proxies if the target has suitable interfaces. |
| `order` | `Ordered.LOWEST_PRECEDENCE` | Order of the transaction advice relative to other advisors in the AOP chain. |

Example configuration tailored to specific needs:

```xml
<tx:annotation-driven
    transaction-manager="ordersTxManager"
    mode="proxy"
    proxy-target-class="true"
    order="100"/>
```

This is an XML fragment and requires the `ordersTxManager` bean to exist. It requests class-based proxies. **You do not need to proactively enable `proxy-target-class="true"` just because you use `@Transactional`**; choose based on bean interfaces, how beans are invoked, and proxy limitations.

### 5.1. `mode="proxy"` vs `mode="aspectj"`

**Proxy mode** is the default:

- Spring wraps a bean in a proxy when the bean has matching transactional methods.
- Only calls **entering through the proxy** are intercepted by transaction advice.
- `this.someMethod()` calls within the same bean do not create another proxy invocation.
- Final methods cannot be overridden by a class-based proxy; private methods are not interception points via a proxy in the normal way.
- Calling annotated methods in a constructor or during `@PostConstruct` typically does not have a complete proxy to guarantee transactions.

**AspectJ mode** can use bytecode weaving to apply the transaction aspect without relying on callers going through a proxy. However, simply setting:

```xml
<tx:annotation-driven mode="aspectj"/>
```

is **not enough** for weaving to work: you need the `spring-aspects` module and compile-time or load-time weaving configuration along with the appropriate AspectJ setup. It is a distinct architectural choice, not a "switch to fix all transaction bugs" in an ordinary XML application.

### 5.2. JDK proxy vs class-based proxy

If a bean implements an interface, `proxy-target-class="false"` typically chooses a **JDK dynamic proxy**, where the proxy's exposed surface consists primarily of the implemented interfaces. This affects injecting by concrete class type and which methods can be called. If you need to inject by concrete class, you can choose class-based proxies (`proxy-target-class="true"`) when the class can be proxied, or adjust clients to depend on the interface.

If the target has no suitable interface, Spring AOP can use a class-based proxy even when the default value is `false`. Do not conclude that "setting false guarantees non-interface classes are unsupported."

**Global configuration note:** multiple declarations of `<aop:config>`, `<aop:aspectj-autoproxy>`, and `<tx:annotation-driven>` in the same context can merge into a shared auto-proxy creator. Enabling class-based proxies in one part of the configuration can affect proxies in other parts. Review the overall AOP design before changing this flag.

### 5.3. The `order` attribute does not change DB commit logic

`order` determines advice ordering when logging, security, retry, monitoring, or other aspects are present. Different orders change whether "the transaction starts before or after another advice" in certain call stacks. It does not change isolation, propagation, or datasource configuration by itself.

For example, if a retry advice sits outside the transaction interceptor, each retry can enter **a new transaction**; if the retry advice sits inside an outer transaction advice, retry attempts may share a transaction state that can no longer be committed after an error. Designing AOP advice order must consider those semantics, not just pick an arbitrary number.

## 6. `@Transactional` attributes still live on Java classes/methods

`<tx:annotation-driven>` enables the **annotation-reading mechanism**; transaction details for each operation are declared as follows:

```java
@Service
@Transactional(readOnly = true)
public class AccountQueryService {
    @Transactional(
        readOnly = false,
        propagation = Propagation.REQUIRES_NEW,
        rollbackFor = BusinessCheckedException.class
    )
    public void updateAccount() throws BusinessCheckedException {
        // update operations and custom rollback rules
    }
}
```

This is an **illustrative snippet**; it needs `BusinessCheckedException`, imports, and actual DAO logic. An annotation on a **specific** method can take precedence over class-level annotation configuration. Use `@Transactional` from `org.springframework.transaction.annotation.Transactional`, or in certain cases the standard Jakarta Transaction annotation supported by Spring; do not confuse it with annotations from other libraries.

Common default values:

| Attribute of `@Transactional` | Default and Meaning |
| --- | --- |
| `propagation` | `REQUIRED`: join the existing transaction or create a new one if none exists. |
| `isolation` | `DEFAULT`: use the backend's default isolation level if a new transaction is created. |
| `readOnly` | `false`; when `true`, it is usually an optimization/check hint acted upon by the manager/provider, not a write-blocking barrier enforced by every DB system. |
| `timeout` | Follows the transaction system, or unlimited if unsupported. |
| `rollbackFor` | Adds no special checked exception rules unless specified. |
| default rollback | `RuntimeException` and `Error` trigger rollback; ordinary checked `Exception` types do not. |
| `transactionManager` or `value` | Qualifier selecting a specific manager when needed. |

You can specify a manager per method if the application has multiple managers:

```java
@Transactional("ordersTxManager")
public void placeOrder() {
    // uses the transaction manager identified by qualifier/bean name
}
```

This is an **illustrative snippet**, not a standalone program. The name `ordersTxManager` must point to a real manager that manages the exact resource used by the operation's DAO.

**Do not mix the two attribute layers:** `mode`, `order`, and `proxy-target-class` belong to the advice activation configuration; `propagation`, `readOnly`, `isolation`, and `rollbackFor` belong to the method's transaction metadata.

## 7. Two ways to register services: XML beans and component scanning

`<tx:annotation-driven>` works with container-managed beans and does not require every bean to be declared with `@Service`.

### Approach A: Registering a service via XML

```xml
<bean id="paymentService" class="demo.tx.PaymentService">
    <constructor-arg ref="jdbcTemplate"/>
</bean>

<tx:annotation-driven transaction-manager="transactionManager"/>
```

The `jdbcTemplate` and `transactionManager` beans and the `PaymentService` class must be defined accordingly. Spring still reads `@Transactional` from `PaymentService` when the bean is created in the same context.

### Approach B: Registering via component scanning in XML

```xml
<context:component-scan base-package="demo.tx"/>
<tx:annotation-driven transaction-manager="transactionManager"/>
```

When `PaymentService` is annotated with `@Service` and resides under the scanned package, Spring creates the bean and applies the appropriate transaction advice. It is not mandatory to add `<context:annotation-config/>` if `component-scan` already registers the necessary annotation post-processors in normal configurations.

Conversely, an object instantiated with `new PaymentService(...)` outside the container is not automatically wrapped by Spring AOP just because the class has `@Transactional`. The key is **a managed bean and callers obtaining the proper proxy**.

## 8. ApplicationContext and WebApplicationContext: where should the tag go?

An easily overlooked limitation: `<tx:annotation-driven/>` **only looks for transactional beans in the same application context where the element is declared**. Especially in traditional XML-based Spring MVC, there may be a parent context for services/repositories and a child `DispatcherServlet` context for controllers.

Example structure:

```text
Root WebApplicationContext
   |-- services
   |-- repositories
   |-- dataSource
   |-- transactionManager
   |-- <tx:annotation-driven/>  <-- appropriate for services in root
   |
   +-- DispatcherServlet child WebApplicationContext
          |-- controllers
          |-- view resolvers / MVC configuration
```

If service beans are defined in the **root context** but you only place `<tx:annotation-driven/>` in the **child DispatcherServlet context**, the child's transaction advice does not reach up to wrap root service beans. As a result, a controller may call the service while the service's `@Transactional` never activates.

This is a very common situation in legacy XML projects that creates the illusion of "I declared `<tx:annotation-driven/>` yet it doesn't roll back." The solution is to place the element in the context that actually creates/registers the services needing transactions, alongside the appropriate manager. Do not fix it by copying all services into multiple contexts, because that can create multiple bean instances, multiple datasources, or hard-to-control duplicate transaction infrastructure.

In applications with multiple contexts, check **exactly which XML file is loaded into which context**. The mere presence of an XML file in `resources/` or on the classpath does not mean it has been loaded.

## 9. Multiple transaction managers: picking the right resource

One XML file can contain multiple data sources:

```xml
<bean id="ordersDataSource"
      class="org.springframework.jdbc.datasource.DriverManagerDataSource">
    <!-- dedicated JDBC configuration for orders -->
</bean>

<bean id="reportingDataSource"
      class="org.springframework.jdbc.datasource.DriverManagerDataSource">
    <!-- dedicated JDBC configuration for reporting -->
</bean>

<bean id="ordersTxManager"
      class="org.springframework.jdbc.support.JdbcTransactionManager">
    <constructor-arg ref="ordersDataSource"/>
</bean>

<bean id="reportingTxManager"
      class="org.springframework.jdbc.support.JdbcTransactionManager">
    <constructor-arg ref="reportingDataSource"/>
</bean>

<tx:annotation-driven transaction-manager="ordersTxManager"/>
```

This is a **structural reading fragment, not a standalone runnable configuration**: the datasource beans must include real connection properties. `ordersTxManager` is the default manager for unqualified annotations in this XML; a method needing the other manager can use `@Transactional("reportingTxManager")` if that name/qualifier exists.

Mandatory questions to answer before trusting that rollback works:

1. Which transaction manager does the service actually use after resolving annotations?
2. Which datasource does the repository/JDBC template/JPA persistence unit use?
3. Do the manager and DAO share the same compatible resource/backend?
4. Is there a non-DB operation (HTTP, email, file I/O) that we **mistakenly assume** will also be rolled back?

`<tx:annotation-driven/>` does not automatically create a distributed transaction across two datasources. A `JdbcTransactionManager` for datasource A does not automatically roll back data on datasource B. Cases requiring multi-resource atomicity need appropriate coordination infrastructure (such as JTA/XA when needed and supported) or integration strategies like outbox/saga depending on business requirements.

With JPA, declare `JpaTransactionManager` for the appropriate `EntityManagerFactory` instead of picking a JDBC manager out of habit. With R2DBC/reactive, you need a transaction manager and context management compatible with reactive execution; the JDBC example in this article does not demonstrate reactive behavior.

## 10. Common errors when enabling annotations with XML

| Symptom | Possible Cause | How to Check and Fix |
| --- | --- | --- |
| Spring reports unrecognized `tx` prefix / XML parse error | Missing `xmlns:tx` or incorrect `spring-tx.xsd` line | Re-check the namespace URI and `xsi:schemaLocation`; place the element inside `<beans>`. |
| Cannot find `transactionManager` | Manager bean does not exist, wrong id, or XML not loaded | Set `id="transactionManager"` or configure `transaction-manager="idPhuHop"`, and ensure the bean is created in the applicable context. |
| Method is annotated but does not roll back | XML with `<tx:annotation-driven/>` not loaded, call bypasses proxy, wrong context/manager | Check the active context, bean proxy, and actual datasource; write a test throwing an unchecked exception between two UPDATEs. |
| Bean created with `new` | Not a Spring-managed bean | Register via `<bean>` or `component-scan`; inject/retrieve the bean from the context. |
| `this.process()` calls a method in the same class | Self-invocation bypasses transaction proxy advice | Move the boundary to an externally called method or extract the transactional method to another bean. |
| `@Transactional` on a private/final method | Method is not intercepted by the proxy as expected | Place the transaction boundary on a proxyable public method; check the actual proxy type. |
| Declared only in child servlet context | Service lives in the parent/root context | Place `<tx:annotation-driven/>` in the context that manages the services to avoid misregistration. |
| Transaction exists but SQL changes still commit individually | DAO acquires a connection/resource not participating in the manager | Check datasource identity and use `JdbcTemplate`/`DataSourceUtils` or compatible JPA integration. |
| Interface bean cannot be injected by concrete class | JDK dynamic proxy only exposes interfaces | Inject by interface or choose class-based proxy when appropriate. |
| Checked exception does not roll back | Default rollback rules do not include checked exceptions | Use `rollbackFor`, or design an explicit exception policy. |
| Exception is caught and method returns normally | Transaction interceptor does not see an escaping exception | Propagate the exception or explicitly mark rollback-only per the contract. |
| Added `mode="aspectj"` but no transaction occurs | Missing `spring-aspects`/weaving | Complete the AspectJ setup or return to normal proxy mode. |
| Transaction does not propagate across `@Async`/new thread | Imperative transactions are typically bound to the execution thread | Place the transaction on the worker thread executing the work or design separate boundaries. |
| Calling `@Transactional` during `@PostConstruct` | Proxy is not yet ready for bean self-invocation | Move initialization to a coordinator calling through the bean proxy after the context is ready. |

### 10.1. Self-invocation: an example where it is very easy to think it is enabled

```java
@Service
public class InvoiceService {
    public void submit() {
        saveInvoice(); // internal call: bypasses the proxy
    }

    @Transactional
    public void saveInvoice() {
        // DB operations
    }
}
```

This is an illustrative snippet without a DAO implementation. With `mode="proxy"`, an external caller invoking `submit()` through the proxy **does not cause** the annotation on `saveInvoice()` to apply to the internal call. If `submit()` does not already have a transaction, no new transaction is created solely by the annotation on `saveInvoice()`.

You can fix this by placing `@Transactional` on public `submit()` (when the entire use case needs a transaction), or by moving `saveInvoice()` to a separate bean and injecting it so the call goes through a proxy. If the outer method is already inside a transaction, the internal call can continue using the **existing** transaction, but the inner method's own annotation still will not create a new boundary or propagation behavior.

### 10.2. Seeing SQL execute does not prove commit

When using JPA, `flush()` sends SQL to the DB without guaranteeing the transaction has committed. With JDBC, an `UPDATE` returning a row count likewise only indicates that SQL executed in the current context. You must verify data state **after the transaction boundary ends** to test real rollback behavior.

### 10.3. Read-only is not an absolute write-blocking mechanism

`@Transactional(readOnly = true)` can help the framework/provider optimize and pass a read-only hint down to the connection or persistence context; you should not expect every DB to reject `INSERT`/`UPDATE` in all cases. To enforce read/write permissions, use DB permissions, API design, and appropriate mechanisms.

## 11. Distinguishing from pure XML transaction configuration and Java configuration

Spring supports the following ways to declare transactions:

| Approach | Where are transaction rules declared? | How is it activated? |
| --- | --- | --- |
| XML + annotation | `@Transactional` on Java class/method | `<tx:annotation-driven/>` in the XML context. |
| Java config + annotation | `@Transactional` on Java class/method | `@EnableTransactionManagement` on Java configuration or compatible auto-configuration. |
| XML pattern-based advice | `<tx:advice>` with `<tx:attributes>/<tx:method>` and an AOP pointcut | `<aop:config>` binds transaction advice to method patterns. |
| Programmatic | `TransactionTemplate` or `PlatformTransactionManager` in code | Code explicitly coordinates transactions via API. |

**The key feature of `<tx:annotation-driven/>` is enabling annotation-based transactions in an XML application.** You do not need to simultaneously write `<tx:advice>`/`<aop:config>` just to make `@Transactional` work.

Example of pattern-based declarative XML (only for comparison, not needed for the demo above):

```xml
<tx:advice id="txAdvice" transaction-manager="transactionManager">
    <tx:attributes>
        <tx:method name="save*" rollback-for="java.lang.Exception"/>
        <tx:method name="get*" read-only="true"/>
        <tx:method name="*"/>
    </tx:attributes>
</tx:advice>

<aop:config>
    <aop:pointcut id="serviceMethods"
                  expression="execution(* demo.tx.*Service.*(..))"/>
    <aop:advisor advice-ref="txAdvice" pointcut-ref="serviceMethods"/>
</aop:config>
```

This is an **XML fragment** requiring the `aop` namespace, a valid datasource/manager, and target classes. It illustrates placing rules **in XML** instead of annotations; you should not casually enable both advisors on the exact same methods without understanding how they interact.

Spring Boot typically provides auto-configuration for transaction management and infrastructure when the required dependencies/transaction manager are present; many Boot applications use `@Transactional` without writing `<tx:annotation-driven/>`. When maintaining an XML application, do not mechanically copy Boot's setup and conclude the XML tag is redundant or always mandatory. Inspect the actual context and activation mechanism of the running application.

## 12. Debugging and verifying configuration

An evidence-based verification process:

1. **Check that the XML is actually loaded:** use `ClassPathXmlApplicationContext("spring-tx.xml")`, root context configuration, or the appropriate Spring mechanism; simply having the XML file in resources is not enough.
2. **Confirm the service is a Spring bean:** retrieve it from `ApplicationContext` or inject the bean; do not instantiate with `new` in the caller.
3. **Confirm the bean has an AOP proxy:** in a debug environment, `AopUtils.isAopProxy(service)` can tell you whether the obtained object is an AOP proxy. It does not by itself prove the transaction rules are right, but it is very useful for checking the proxy precondition.
4. **Confirm the manager:** check the bean name in XML and the resource managed by that manager; pay attention when there are multiple transaction managers.
5. **Confirm calls hit the right boundary:** the public method is called **from outside through the proxy**, not just via `this.method()`.
6. **Intentionally throw an unchecked exception between two writes:** read the result after the method returns/throws; if the whole transaction is configured properly, both uncommitted writes will roll back.
7. **Inspect transaction logs at an appropriate level:** look for signs of the manager starting/joining and ending transactions, paying attention to the call stack/exceptions.
8. **Check resource consistency:** the DAO must use the datasource/persistence unit coordinated by the manager; observe through an integration test.

Example of a small proxy check:

```java
import org.springframework.aop.support.AopUtils;

Object service = context.getBean("transferService");
System.out.println(AopUtils.isAopProxy(service));
```

This is an **illustrative snippet**; `context` must be an initialized Spring context. `true` confirms the object is an AOP proxy; further analysis of the advisor/transaction and DB results is needed to prove `@Transactional` actually works. Proxy class names can vary across environments/versions, so do not assert on class name strings.

To diagnose transactions in a real application, you can configure logging at `TRACE`/`DEBUG` for `org.springframework.transaction` and `org.springframework.jdbc.datasource` in a test environment. Limit verbose logging in production due to overhead and sensitive data.

**Do not use a `@Transactional` test method as your sole proof:** Spring Test may start/roll back a test transaction automatically, masking the fact that the service was not proxied as expected. Verify service boundaries and DB state outside an enclosing test transaction where appropriate.

## 13. Self-check exercises

**Scenario A — Adding only the annotation.** An XML project already has `<context:component-scan>`, `JdbcTemplate`, and `transactionManager`, but does not yet have `<tx:annotation-driven/>`. A developer adds `@Transactional` to a service. Is rollback guaranteed when the method throws an exception?

**Answer:** No. In this minimal context, the annotation is only metadata; the transaction annotation infrastructure has not been registered. You must enable `<tx:annotation-driven/>` or an equivalent activation mechanism that actually exists.

**Scenario B — Renaming the transaction manager.** XML declares `<bean id="paymentTxManager" .../>` but only uses `<tx:annotation-driven/>`. What could go wrong?

**Answer:** The element looks for a default manager bean named `transactionManager` when the annotation does not specify a manager. You should declare `<tx:annotation-driven transaction-manager="paymentTxManager"/>`, and verify that the manager exists and matches the DAO resource.

**Scenario C — Self-invocation.** `checkout()` calls `this.pay()` in the same class, `pay()` has `@Transactional`, and XML has annotation-driven enabled. Is a transaction automatically created for `pay()`?

**Answer:** With default proxy mode, no, because `this.pay()` bypasses the proxy. Move the transaction to an outer boundary or extract to another bean.

**Scenario D — Wrong context.** `<tx:annotation-driven/>` is in the DispatcherServlet child context, while the service bean is in the root context. Is the service automatically wrapped by the child's advice?

**Answer:** No. The infrastructure only processes beans belonging to its own context. It must be configured in the context that creates the service.

**Scenario E — Choosing `proxy-target-class="true"`.** Does this automatically make private methods transactional?

**Answer:** No. A class-based proxy cannot override a private method to intercept it like a public service method; moreover, it is still proxy mode, so self-invocation continues to bypass advice.

**Scenario F — `mode="aspectj"`.** Can you simply add this attribute to XML to make self-invocation transactional?

**Answer:** No. AspectJ weaving and the necessary dependencies/configuration are required; if you are not ready for that, designing service boundaries suited for proxy mode is usually simpler.

**Scenario G — Multi-datasource transactions.** There is a manager for DB A, annotations are enabled, but the service uses a JDBC template for DB B. Will Spring roll back both DBs?

**Answer:** Not automatically. A local manager for A does not coordinate B just because they share the same `@Transactional` method; you need the right manager/resource configuration and a separate multi-resource strategy.

## 14. Summary of principles to remember

- `@Transactional` declares **transaction conditions**; `<tx:annotation-driven/>` enables **annotation processing infrastructure** in the **right Spring context**.
- The XML element requires the `tx` namespace/`spring-tx.xsd` and a `TransactionManager` suitable for the data access infrastructure; the default manager name is `transactionManager`.
- `mode="proxy"` is the default: **only calls going through the proxy** are intercepted; self-invocation, constructor/init code, and proxy limitations do not disappear just because XML is enabled.
- `proxy-target-class` controls the proxy type; `mode="aspectj"` is a separate weaving mechanism requiring additional configuration.
- Per-method transaction attributes belong on `@Transactional`; default rollback applies to unchecked exceptions/Errors, not by default to all checked exceptions.
- For JDBC/JPA, you must use the matching datasource/persistence unit and manager; annotations do not unify independent resources.
- The most reliable verification is an **integration scenario with both commit and rollback**, reading DB state after the transaction boundary ends.

Remember the flow: **XML namespace + `<tx:annotation-driven/>` → transaction proxy/interceptor → `@Transactional` metadata → right transaction manager → DAO using the right resource → commit/rollback**.

## Official References

- [Spring Framework 6.2 — Using `@Transactional`](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/declarative/annotations.html)
- [Spring Framework — Understanding Declarative Transaction Implementation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html)
- [Spring Framework — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html)
- [Spring Framework — Transaction Propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html)
- [Spring Framework — Controlling Database Connections](https://docs.spring.io/spring-framework/reference/data-access/jdbc/connections.html)
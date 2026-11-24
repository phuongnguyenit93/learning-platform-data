# AspectJ Mode and Code Weaving Requirements Instead of Proxies in Spring Transaction Management

## 1. Why Does Spring Need AspectJ Mode?

When using `@Transactional`, Spring Framework must place logic to begin, join, commit, or roll back a transaction around the business method invocation. The default mechanism is a **Spring AOP proxy**: the caller invokes a bean through a proxy, the proxy routes the call through `TransactionInterceptor`, and then reaches the actual method. This mechanism is simple and sufficient for most applications, yet it has an intentional limitation: **internal calls `this.method()` do not pass through the proxy**.

**AspectJ mode** weaves transaction advice directly into the **target class's bytecode** via *weaving*. Once a class is properly woven, advice applies at matching method execution join points, including calls within the same object. Spring still uses the familiar transaction manager and `@Transactional` rules; what changes here is the **interception mechanism**, not a different kind of database transaction.

Problem example:

```java
@Service
public class InvoiceService {
    public void submit() {
        save(); // this.save(): does not go through the Spring proxy
    }

    @Transactional
    public void save() {
        // Two DB operations that must commit or roll back together
    }
}
```

This is **illustrative code**; without a repository, it does not compile/run standalone. If you only enable default `@EnableTransactionManagement` or `<tx:annotation-driven/>` in proxy mode, a caller invoking `submit()` through the proxy **does not cause `save()`'s annotation to apply** to the internal call; if `submit()` does not already have a transaction, both operations inside `save()` can run outside any transaction as expected. With **AspectJ mode and a woven class**, executing `save()` is intercepted by advice even when called from `submit()`.

This lesson explains **how AspectJ differs from proxies**, **what weaving actually requires**, **how to enable it with Spring XML or Java configuration**, a runnable Java 17 example, and how to diagnose failures when switching `mode` alone leaves transactions inactive.

## 2. Comparing Proxies and AspectJ by Execution Path

### 2.1. Proxy mode (default)

```text
External caller
    |
    v
Spring bean proxy
    |
    +-- TransactionInterceptor
    |       +-- resolve @Transactional
    |       +-- transactionManager.getTransaction(...)
    |
    v
Target.method()
    |
    +-- this.anotherMethod()  --> calls target directly
                                  (does not re-enter proxy)
```

Proxy mode only intercepts method invocations going **through the proxy**. If `anotherMethod()` has its own annotation, that annotation does not create a new transaction boundary when invoked via `this.anotherMethod()`.

Even switching from JDK dynamic proxies to class-based proxies (`proxy-target-class=true`), **self-invocation still bypasses the proxy**. Class-based proxying is not AspectJ weaving.

### 2.2. AspectJ mode (with weaving)

```text
Build-time weaving or load-time weaving
       |
       v
Class bytecode woven with the transaction aspect
       |
       v
Caller --> Target.method()
              |
              +-- this.anotherMethod()
                     |
                     +-- advice woven into execution
                          +-- resolve @Transactional
                          +-- transactionManager.getTransaction(...)
                          +-- method body
                          +-- commit/rollback
```

This is a **conceptual diagram**, not an exact representation of a specific AspectJ version's bytecode. Essential difference: advice does not require the caller to pass through a proxy object at call time. It is woven into matching join points of the transformed class, so internal calls and directly annotated methods with appropriate visibility can be handled.

Spring transactions still have **logical scopes and physical transaction scopes**. A `REQUIRED` method can join an active transaction; AspectJ does not mean every method call starts an independent transaction.

| Criterion | Spring AOP proxy | AspectJ weaving |
| --- | --- | --- |
| How advice is applied | Proxy intercepts external calls | Bytecode woven at matching join points |
| `this.inner()` | Does not trigger additional advice | Can be intercepted if `inner()` is woven and matches transaction annotation |
| Public method called outside bean | Yes, if going through an eligible proxy | Yes, when class/method is woven |
| Directly annotated private method | Not a proxy interception point | Can be advised in AspectJ mode |
| Annotation declared only on interface | May be recognized in Spring proxy mode in suitable setups | **Do not rely on it**; AspectJ follows Java annotation inheritance and needs annotations on concrete class/method |
| Bean created with `new` outside Spring | Normally not proxied | Woven class still carries advice, yet the transaction aspect **must be configured with a manager before use** |
| Required tooling | Spring transaction AOP infrastructure | `spring-aspects`, AspectJ compiler/weaver, and real weaving setup |
| Modifies app bytecode | No, under standard proxy mechanism | Yes, at build time or class loading |
| Ease of operation/debugging | Usually simpler | Requires managing agents, classloaders, weaving scope, and build artifacts |

**Do not interpret "AspectJ replaces proxies" as guaranteeing the entire app has no proxies left**: other Spring AOP capabilities, such as caching or security, may still create their own proxies. Here we are discussing **transaction advice** in AspectJ mode.

## 3. Changing `mode` Is Not Enough: Four Conditions Must Hold Simultaneously

This configuration line only **selects the AspectJ mechanism**:

```xml
<tx:annotation-driven mode="aspectj" transaction-manager="transactionManager"/>
```

For transactions to actually apply to annotated methods, all of these conditions must be met:

1. **Valid transaction metadata.** Spring's `@Transactional` is declared on the **implementation class or implementation method**, not relying solely on interface annotations.
2. **Spring transaction aspect present.** The `org.springframework:spring-aspects` dependency provides `org.springframework.transaction.aspectj.AnnotationTransactionAspect`, the aspect that recognizes `@Transactional`.
3. **Actual weaving.** Use the AspectJ compiler at build time or the AspectJ load-time weaver when the JVM loads classes. Adding the JAR to the classpath without weaving will not magically inject advice into methods.
4. **Properly configured transaction manager.** `AnnotationTransactionAspect` must receive an appropriate `PlatformTransactionManager`/transaction manager **before any transactional method executes**; DAOs/repositories must use resources coordinated by that manager.

Ensure **target classes are within weaving scope**, have not already been loaded by a classloader before the load-time transformer is registered, and that the app actually runs with the woven artifact/JVM setup.

An architectural checklist:

```text
@Transactional on concrete method/class?
            |
            v
spring-aspects provides AnnotationTransactionAspect?
            |
            v
AspectJ weaver transformed the target class?
            |
            v
Spring injected transaction manager into the aspect?
            |
            v
DAO uses the same transaction resource?
            |
            v
Commit/rollback occurs when method executes
```

If any step is missing, replacing `proxy` with `aspectj` **creates no magic**. In particular, `@EnableAspectJAutoProxy` and `<aop:aspectj-autoproxy/>` only enable **Spring AOP proxies** for aspects declared with `@AspectJ` syntax; they **do not** enable bytecode weaving.

## 4. Two Bytecode Weaving Paths: Build-Time and Load-Time

### 4.1. Compile-time weaving (CTW)

The AspectJ compiler (`ajc`) compiles Java/AspectJ sources and weaves advice into class outputs. This requires the build pipeline to select the right compiler/plugin and place required aspects on the aspect path/classpath.

```text
.java / .aj  +  transaction aspect
             |
             v
        AspectJ compiler (ajc)
             |
             v
       woven .class files
             |
             v
           JVM runs
```

Advantage: weaving errors typically surface right at build time; production JVMs do not strictly need an LTW agent for already-woven classes. Check the plugin, AspectJ version, and actual `.class` outputs after building. Standard `javac` **does not weave** the transaction aspect merely because a class carries annotations.

### 4.2. Post-compile / binary weaving

If `.class` files or JARs were already compiled by `javac`, AspectJ can weave **already-compiled bytecode** in an additional build step. You still must supply the aspect and configure tooling properly. This helps when code is compiled by another toolchain yet you control the packaging step.

```text
javac -> unwoven .class -> ajc binary weaving -> woven .class
```

Check to avoid double-weaving if the same class is woven again at runtime, as results and advice interactions can become complex.

### 4.3. Load-time weaving (LTW)

AspectJ LTW transforms classes **as the JVM loads them**, via a class-file transformer. The most visible way in a standalone Java app is a Java agent:

```bash
java -javaagent:/path/to/aspectjweaver.jar -cp "..." demo.weaving.Main
```

The path and classpath are illustrative; a complete runnable example appears in section 7. The `-javaagent` flag must be passed **at JVM startup**. Placing it after the main class name is invalid. Running `java` without the agent will not weave this way, even if Maven downloaded the JAR.

AspectJ LTW reads **`META-INF/aop.xml`** files on the classpath to know which aspects and target classes to weave. `spring-aspects` ships a `META-INF/aop.xml` listing Spring-provided aspects, including `AnnotationTransactionAspect`. An application can add its own `META-INF/aop.xml` to **scope packages to weave** or configure diagnostic output. AspectJ configuration files are merged according to AspectJ's LTW rules.

Note the roles of the JARs:

| Library/Tool | Purpose |
| --- | --- |
| `spring-tx` / Spring JDBC/JPA dependencies | Transaction API, managers, interceptors, and resource integration |
| `spring-aspects` | Spring's transaction AspectJ aspect, including `AnnotationTransactionAspect` |
| `aspectjweaver` | AspectJ weaving runtime and Java instrumentation agent for LTW |
| `aspectjtools` / AspectJ Maven plugin | Used when compiling or weaving at **build time**, not required by the LTW agent |
| `spring-instrument` | A **different** Java agent provided by Spring for certain Spring LTW/classloader mechanisms; do not confuse with `aspectjweaver` |

When choosing the `aspectjweaver` LTW agent, **you do not automatically need both `-javaagent:spring-instrument` and `-javaagent:aspectjweaver`**. Spring offers an alternative LTW path via `<context:load-time-weaver/>`, using a classloader-compatible `LoadTimeWeaver`; in environments needing Java instrumentation, that path may use the `spring-instrument` agent. Pick **one configured and verified mechanism**; do not blindly copy every agent flag into your launch command.

### 4.4. Spring `LoadTimeWeaver` and classloader selection

Spring supports `<context:load-time-weaver/>` (XML) or `@EnableLoadTimeWeaving` (Java config) to enable LTW infrastructure for the appropriate `ApplicationContext`/classloader. An example Spring LTW configuration:

```xml
<context:load-time-weaver aspectj-weaving="on"/>
```

This is a **fragment**; it requires the `context` namespace, XSD declarations, and a compatible classloader/agent environment. `aspectj-weaving` accepts `on`, `off`, or `autodetect`; `autodetect` checks for `META-INF/aop.xml`. Do not confuse this element with `<tx:annotation-driven mode="aspectj"/>`: one selects the **transaction advice implementation**, while the other handles **weaving infrastructure**.

In a standalone Java app, passing `-javaagent:aspectjweaver-...jar` with `META-INF/aop.xml` is the direct path, without needing `<context:load-time-weaver/>` in this lesson's example. In app servers or multi-classloader environments, weaving must match the classloader actually loading services and may require container-specific integration.

## 5. Spring Configuration: Both XML and Java Support AspectJ Mode

### 5.1. XML transaction annotations

Minimal structural configuration:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xmlns:tx="http://www.springframework.org/schema/tx"
       xsi:schemaLocation="
           http://www.springframework.org/schema/beans
           https://www.springframework.org/schema/beans/spring-beans.xsd
           http://www.springframework.org/schema/tx
           https://www.springframework.org/schema/tx/spring-tx.xsd">

    <bean id="transactionManager"
          class="org.springframework.jdbc.support.JdbcTransactionManager">
        <constructor-arg ref="dataSource"/>
    </bean>

    <tx:annotation-driven mode="aspectj"
                          transaction-manager="transactionManager"/>
</beans>
```

This is an **XML fragment**, not standalone: it requires defining `dataSource`, a Spring context, target beans, and corresponding weaving. The `transaction-manager` attribute points to a real bean. The traditional XML default manager name is `transactionManager`, though specifying it explicitly avoids confusion when multiple managers exist.

The `proxy-target-class` attribute **only applies in `mode="proxy"`**; it does not turn AspectJ mode into a "stronger class-based proxy". `order` mainly controls the transaction advisor's order in proxy mode; ordering and precedence among multiple woven AspectJ aspects follow AspectJ's own rules and must be checked in weaving config.

### 5.2. Equivalent Java configuration

```java
@Configuration
@EnableTransactionManagement(mode = AdviceMode.ASPECTJ)
public class TransactionConfiguration {
    @Bean
    PlatformTransactionManager transactionManager(DataSource dataSource) {
        return new JdbcTransactionManager(dataSource);
    }
}
```

This is an **illustrative snippet** with imports from `org.springframework.context.annotation`, `org.springframework.transaction`, `org.springframework.jdbc.support`, and `javax.sql.DataSource`. You must add a `DataSource` bean, the `spring-aspects` dependency, and actual weaving. `AdviceMode.ASPECTJ` selects the transaction advice strategy; it **does not install a Java agent automatically**.

### 5.3. Aspects outside the Spring IoC container

In an application not using a Spring container to configure the aspect, Spring allows configuring `AnnotationTransactionAspect` programmatically, provided classes are woven:

```java
DataSourceTransactionManager manager =
        new DataSourceTransactionManager(dataSource);
AnnotationTransactionAspect.aspectOf().setTransactionManager(manager);
```

This is an illustrative fragment; `dataSource` must exist with appropriate imports. Even though AspectJ can advise objects instantiated via `new`, **the manager must still be configured before any advised method runs**. In a typical Spring app, `<tx:annotation-driven mode="aspectj"/>` or `@EnableTransactionManagement(mode=AdviceMode.ASPECTJ)` handles wiring this aspect.

Do not both call `aspectOf().setTransactionManager(...)` manually and let the container manage the same transaction aspect without a clear reason: split ownership creates confusion.

## 6. `@Transactional` Semantics in AspectJ Mode

AspectJ changes **how interception happens**, while Spring transaction rules remain intact:

- **`REQUIRED` (default):** joins an existing transaction or creates a new one if none exists.
- **`REQUIRES_NEW`:** suspends the active transaction and begins an independent transaction; may require an extra JDBC connection.
- **`NESTED`:** uses a savepoint inside the same physical transaction when supported by manager and resource.
- **Default rollback:** `RuntimeException` and `Error` trigger rollback; checked exceptions normally need `rollbackFor` to roll back.
- **`readOnly=true`:** hint for the manager/provider; does not guarantee the database rejects all write statements.
- **Resources:** JDBC repositories must use connections bound to the transaction manager; files, emails, and HTTP calls do not automatically roll back with a JDBC transaction.

AspectJ also has points requiring special attention:

1. **Place annotations on the implementation.** When weaving, do not annotate only an interface expecting AspectJ to see the metadata as in proxy mode. Java does not inherit annotations from interface methods onto implementations.
2. **Class-level vs. method-level annotations.** `@Transactional` on a concrete class establishes defaults for public operations. If you need a transaction on a **non-public method**, place `@Transactional` **directly on that method**; do not infer every private helper is transactional just because the class is annotated.
3. **Self-invocation is handled once the class is woven.** For instance, public `run()` calling `this.save()`; `save()` with its own direct annotation can be intercepted by advice in AspectJ mode.
4. **Not every operation is a method join point matched by `AnnotationTransactionAspect`.** Field access, constructors, file writes, other threads, and object lifecycle events do not automatically become transactional via weaving.
5. **Thread/reactive boundaries still exist.** Imperative transactions are normally bound to the execution thread. AspectJ does not automatically propagate transactions to other threads; R2DBC/reactive needs `ReactiveTransactionManager` and the proper Reactor Context.

A private method example, **purely illustrative**:

```java
public void submit() {
    persistInternal(); // call within the same object
}

@Transactional
private void persistInternal() {
    // DB access using resources coordinated by Spring's transaction manager
}
```

For an aspect woven into the concrete class, a method-level annotation on `private persistInternal()` can establish a transaction boundary. In proxy mode, private methods are not interception points. Section 7 uses a public method to isolate the **self-invocation** effect cleanly without mixing in visibility differences.

## 7. Complete Java 17 Example: Self-Invocation Truly Rolling Back with AspectJ

### 7.1. Goal and stack

The example uses:

- Java **17+** and Maven **3.9+**.
- Spring Framework **6.2.18**, using XML `ClassPathXmlApplicationContext`.
- `spring-aspects` **6.2.18** with AspectJ Weaver **1.9.25**.
- Spring JDBC and in-memory H2 **2.3.232**.
- A service with `runTransfer()` calling `transfer()` directly within the same object. **Only `transfer()` has `@Transactional`.**

In default proxy mode, the internal call never enters the transaction interceptor. In AspectJ mode **with a real weaving agent**, executing `transfer()` has woven advice; when an exception occurs between two operations, the JDBC transaction rolls back.

Directory structure:

```text
spring-tx-aspectj-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── demo/
        │       └── weaving/
        │           ├── Main.java
        │           └── TransferService.java
        └── resources/
            ├── spring.xml
            └── META-INF/
                └── aop.xml
```

### 7.2. `pom.xml`: both transaction and weaving

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>spring-tx-aspectj-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <spring.version>6.2.18</spring.version>
        <aspectj.version>1.9.25</aspectj.version>
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
            <artifactId>spring-aspects</artifactId>
            <version>${spring.version}</version>
        </dependency>
        <dependency>
            <groupId>org.aspectj</groupId>
            <artifactId>aspectjweaver</artifactId>
            <version>${aspectj.version}</version>
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
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-dependency-plugin</artifactId>
                <version>3.8.1</version>
            </plugin>
        </plugins>
    </build>
</project>
```

Explanation: `spring-context` supplies the IoC/XML container; `spring-jdbc` supplies `JdbcTemplate` and the JDBC transaction manager; `spring-aspects` contains `AnnotationTransactionAspect`; `aspectjweaver` acts as Java agent and weaving runtime; H2 is runtime-only. Pin all Spring modules to **the exact same version** to prevent dependency mismatches. A Spring Boot app can use a BOM to manage versions, yet this example deliberately omits Boot so AspectJ configuration can be observed directly.

### 7.3. `spring.xml`: selecting `mode="aspectj"`

File `src/main/resources/spring.xml`:

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

    <context:component-scan base-package="demo.weaving"/>

    <bean id="dataSource"
          class="org.springframework.jdbc.datasource.DriverManagerDataSource">
        <property name="driverClassName" value="org.h2.Driver"/>
        <property name="url" value="jdbc:h2:mem:aspectj_tx;DB_CLOSE_DELAY=-1"/>
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

    <tx:annotation-driven mode="aspectj"
                          transaction-manager="transactionManager"/>
</beans>
```

The manager and `JdbcTemplate` reference **the same `dataSource`**. `DriverManagerDataSource` creates no connection pool; it suffices for the demo. `DB_CLOSE_DELAY=-1` keeps the H2 database in the JVM as short-lived connections close. In real deployments, use a proper pooled datasource.

`<tx:annotation-driven mode="aspectj"/>` tells Spring to configure the transaction aspect; it **does not** attach a Java agent to the JVM. Step 7.6 launches the JVM with `-javaagent`.

### 7.4. `META-INF/aop.xml`: scoping which classes are woven

File `src/main/resources/META-INF/aop.xml`:

```xml
<!DOCTYPE aspectj PUBLIC "-//AspectJ//DTD//EN"
                           "https://www.eclipse.org/aspectj/dtd/aspectj.dtd">
<aspectj>
    <weaver options="-showWeaveInfo">
        <include within="demo.weaving..*"/>
    </weaver>
</aspectj>
```

Explanation: `include within="demo.weaving..*"` restricts target types to the application package and its subpackages. `-showWeaveInfo` prints useful join point/weaving info during verification; you can remove this option in production once verified. This application config file **does not define** `AnnotationTransactionAspect` itself; Spring ships that aspect and its AspectJ configuration in the **`spring-aspects` JAR**. AspectJ LTW merges all `META-INF/aop.xml` files visible on the classpath.

Do not place another `aop.xml` that arbitrarily overrides/filters aspects without understanding `include/exclude` semantics. Some filters can affect aspects declared by **other `aop.xml` files**; verify the actual list of woven aspects.

### 7.5. Service: same-object call still gets a transaction

File `src/main/java/demo/weaving/TransferService.java`:

```java
package demo.weaving;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronizationManager;

@Service
public class TransferService {
    private final JdbcTemplate jdbc;

    public TransferService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public void runTransfer(boolean fail) {
        transfer(fail); // this.transfer(fail): self-invocation
    }

    @Transactional
    public void transfer(boolean fail) {
        System.out.println("TX_ACTIVE=" +
                TransactionSynchronizationManager.isActualTransactionActive());

        jdbc.update(
                "UPDATE account SET balance = balance - 30 WHERE id = 1");

        if (fail) {
            throw new IllegalStateException("planned failure");
        }

        jdbc.update(
                "UPDATE account SET balance = balance + 30 WHERE id = 2");
    }
}
```

`runTransfer()` **has no** `@Transactional`; it only calls `transfer()` in the same class. `transfer()` has the annotation on a **concrete public method**. `TransactionSynchronizationManager.isActualTransactionActive()` is used only for observation in this lesson; business services should normally not rely on it to drive control flow.

In AspectJ mode, if `TransferService`'s bytecode is successfully woven, the internal `transfer(fail)` call still goes through the transaction aspect. In proxy mode, that internal call bypasses the transaction proxy; `@Transactional` on `transfer()` does not activate a transaction for that call.

### 7.6. Main and the right launch command with the JVM agent

File `src/main/java/demo/weaving/Main.java`:

```java
package demo.weaving;

import org.springframework.context.support.ClassPathXmlApplicationContext;
import org.springframework.jdbc.core.JdbcTemplate;

public class Main {
    public static void main(String[] args) {
        try (ClassPathXmlApplicationContext context =
                     new ClassPathXmlApplicationContext("spring.xml")) {

            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);

            jdbc.execute("""
                    CREATE TABLE account (
                        id INT PRIMARY KEY,
                        balance INT NOT NULL
                    )
                    """);

            jdbc.update("INSERT INTO account (id, balance) VALUES (1, 100)");
            jdbc.update("INSERT INTO account (id, balance) VALUES (2, 50)");

            TransferService service = context.getBean(TransferService.class);

            print(jdbc, "BEFORE");

            try {
                service.runTransfer(true);
            } catch (IllegalStateException ex) {
                System.out.println("FAIL=" + ex.getMessage());
            }

            print(jdbc, "AFTER_FAIL");

            service.runTransfer(false);
            print(jdbc, "AFTER_SUCCESS");
        }
    }

    private static void print(JdbcTemplate jdbc, String label) {
        Integer a = jdbc.queryForObject(
                "SELECT balance FROM account WHERE id = 1", Integer.class);
        Integer b = jdbc.queryForObject(
                "SELECT balance FROM account WHERE id = 2", Integer.class);

        System.out.println(label + ": A=" + a + ", B=" + b);
    }
}
```

Compile and copy runtime dependency JARs into an explicit directory:

```bash
mvn -q package dependency:copy-dependencies -DoutputDirectory=target/dependency
```

On **Windows PowerShell** (classpath uses `;`):

```powershell
java -javaagent:target/dependency/aspectjweaver-1.9.25.jar -cp "target/classes;target/dependency/*" demo.weaving.Main
```

On **Linux/macOS** (classpath uses `:`):

```bash
java -javaagent:target/dependency/aspectjweaver-1.9.25.jar -cp "target/classes:target/dependency/*" demo.weaving.Main
```

This is a **fresh JVM** running the newly built classes and JARs, unlike calling `mvn exec:java` inside the Maven JVM without an agent attached at JVM startup. In an IDE, add `-javaagent:...` under **VM options** in the run configuration and ensure `META-INF/aop.xml` and `spring-aspects` are on the runtime classpath.

**Lines printed by the program** (ignoring weaving info, logging, and environment-dependent messages):

```text
BEFORE: A=100, B=50
TX_ACTIVE=true
FAIL=planned failure
AFTER_FAIL: A=100, B=50
TX_ACTIVE=true
AFTER_SUCCESS: A=70, B=80
```

Explanation:

1. Spring initializes the XML container, creates `JdbcTemplate`, `JdbcTransactionManager`, `TransferService`, and configures `AnnotationTransactionAspect`.
2. The AspectJ agent transforms classes in package `demo.weaving` as they load, giving `transfer()` transaction advice.
3. When `runTransfer(true)` internally calls `transfer(true)`, the aspect opens a transaction; `TX_ACTIVE=true` shows a Spring imperative transaction is active inside the method.
4. After the debit, `IllegalStateException` exits `transfer()`; under default rollback rules, Spring rolls back the debit. `Main` catches the exception outside the scope, then queries again and still sees A=100, B=50.
5. `runTransfer(false)` succeeds on both updates, the transaction commits, and finally A=70, B=80.

The demo's value is **observing an internal call** being transactionalized. The `TX_ACTIVE=true` flag is only a secondary signal; the primary proof is data remaining unchanged after failure and changing atomically after success. The demo does not check sufficient funds, concurrent locking, or transfer idempotency; do not use it directly as a banking application.

### 7.7. Control experiment: missing weaving or reverting to proxy mode

If you change the XML to:

```xml
<tx:annotation-driven mode="proxy"
                      transaction-manager="transactionManager"/>
```

and run with this design, `runTransfer()` still calls `this.transfer()`, so `transfer()`'s own annotation **is not intercepted by a Spring transaction proxy**. With `DriverManagerDataSource` and default JDBC auto-commit in the demo, the debit on failure can commit on its own, showing **no atomicity as expected**.

Another control check: keep `mode="aspectj"` yet **omit `-javaagent`** and have no build-time woven classes. `TransferService` is never transformed; self-invocation gets no AspectJ advice. Therefore `mode="aspectj"` and dependency presence **cannot be used as proof** that bytecode was woven.

When comparing, run each configuration in a **fresh JVM** with a fresh in-memory H2 DB. Do not reuse the same data after a broken run, since auto-committed changes would alter the starting state of the next experiment.

## 8. How to Confirm a Class Was Actually Woven

Simply seeing beans initialize or `aop.xml` on the classpath is not enough. Use evidence from both build/runtime and the database.

### 8.1. Inspecting runtime weaving

In the LTW demo, add `-showWeaveInfo` to `<weaver>` as in section 7.4. Watch AspectJ logs for weaving info on methods/classes in your app package, especially join points on `TransferService`. When no info appears, check:

- Was the agent passed via `-javaagent` before the main class name?
- Is the agent JAR path and version exact?
- Is `spring-aspects` on the runtime classpath?
- Was `META-INF/aop.xml` copied into `target/classes/META-INF/`?
- Does `include within` cover the **exact package and class**?
- Was the class loaded too early before the transformer was registered?
- Do server/IDE classloaders see the same JARs and config?

Weaving logs still do not replace commit/rollback tests. If the class has another advisor, Spring might still create a proxy; `AopUtils.isAopProxy(bean)` **is not a test for AspectJ weaving**.

### 8.2. Checking the transaction manager and resources

Suppose AspectJ advice runs yet JDBC still auto-commits outside a transaction. Verify whether the manager used by the aspect governs the **same `DataSource`** from which `JdbcTemplate` obtains connections. For JPA, check the right `EntityManagerFactory`/`JpaTransactionManager`; with multiple datasources, check the right manager or qualifier.

`TransactionSynchronizationManager.isActualTransactionActive()` is a diagnostic signal for thread-local state in imperative transactions; it **does not guarantee** that an HTTP request, email, or connection from another datasource joined the transaction.

### 8.3. Verifying with behavioral tests

A useful test should include:

1. Initial DB data already committed.
2. Calling an unannotated wrapper method containing `this.transactionalMethod()`.
3. Intentionally throwing an unchecked exception **after the first DB operation, before the second**.
4. Letting the interceptor/aspect finish the transaction.
5. Re-reading data **after the scope** from an appropriate context; verify no partial commit occurred.
6. Retrying with the success path; verify both changes committed.
7. Comparing against proxy mode or running without weaving to prove the difference.

Beware test methods annotated with `@Transactional` by Spring Test: the test framework can auto-roll back at the end, masking the fact that the service's transactional method was never woven. Ensure the test observes the exact boundary under test.

## 9. Limitations AspectJ Does Not Automatically Eliminate

### 9.1. Weaving does not replace the transaction manager

AspectJ only handles attaching advice. It does not magically open a transaction without a compatible manager. Commit/rollback execution still depends on the database, JDBC/JPA/R2DBC provider, and transaction infrastructure.

### 9.2. Does not automatically fix multi-thread bugs

Imperative Spring transactions usually bind resources to the current thread. If a method spawns another thread via `new Thread`, an executor, or `@Async`, weaving a method on the new thread can create/join **a transaction in that thread's context**, yet it does not automatically transfer the parent thread's JDBC connection/physical transaction to the new thread. You must design explicit transaction scopes where the work executes.

### 9.3. Does not turn non-DB side effects into rollbackable resources

If a method already sent an email or called an external service, rolling back the database does not undo effects that already happened. When consistency between DB and messaging is required, consider an outbox or suitable coordination. This is a transaction/resource concern, not proxy-versus-AspectJ.

### 9.4. Unwoven classes keep old semantics

With LTW, classes already loaded by the JVM before the transformer appears are normally not woven retroactively by standard LTW configurations. In app servers, plugins, hot reload, native images, or multi-classloader setups, differences between **current classpath** and **actual classloader** affect weaving scope. Java agents must be set up early, and build/test/deployment must run with the same weaving configuration.

### 9.5. Reflection/final/private is not "everything is safe"

AspectJ can advise method executions that proxies do not intercept, including non-public methods when annotated directly; however, the transaction aspect only applies to **matching join points and woven classes**. It does not mean every constructor, field access, synthetic method, or reflective operation automatically gets a transaction. Write real tests for your application's cases.

### 9.6. Advice ordering and performance

Weaving can increase build or class-loading overhead and complicate debugging/stack traces. Weaving all third-party dependencies unnecessarily causes overhead and warnings. Restrict `<include within="my.application..*"/>` to needed packages; when multiple aspects exist, inspect their precedence/ordering. Do not assume the `order` attribute of proxy-mode transaction advisors dictates all ordering among woven AspectJ aspects.

## 10. Common Configuration Errors and Fixes

| Symptom | Common Cause | Check/Fix |
| --- | --- | --- |
| `mode="aspectj"` set yet self-invocation still runs outside transactions | Bytecode not woven | Use `ajc` in build or LTW agent; check `-showWeaveInfo` and rollback tests |
| Spring reports missing `AnnotationTransactionAspect` | Missing `spring-aspects` | Add `org.springframework:spring-aspects` matching Spring version |
| Agent reports JAR not found | Wrong `-javaagent` path | Verify JAR name/version and path from working directory |
| Agent runs yet classes are not woven | Wrong `META-INF/aop.xml` or included packages | Check `target/classes/META-INF/aop.xml`, package pattern, classloader |
| Weaving log shows only other aspects | Transaction aspect not registered or filtered out | Check `spring-aspects` config and aspect `include/exclude` rules |
| Runtime reports transaction manager not configured | Aspect not injected with manager or XML context not loaded | Check `<tx:annotation-driven mode="aspectj">`, `transactionManager` bean, execution timing |
| Annotation on interface has no effect | AspectJ does not inherit interface annotations | Put `@Transactional` on concrete class or implementation method |
| Only a proxy appears despite AspectJ enabled | Bean has another advisor | Do not treat proxy flags as proof; check weaving logs and behavior |
| Private method not transactional | Annotation only at class level or class not woven | Annotate directly on private method, confirm weaving |
| Checked exception does not roll back | Default rollback rule | Configure `rollbackFor` appropriately, or use unchecked exceptions per contract |
| Method catches exception and returns normally | Advice sees no exception escaping the scope | Propagate exception or mark rollback-only when appropriate |
| H2/JDBC update commits individually | DAO uses connection/resource outside manager | Check `DataSource` of JDBC template and manager |
| Fails only in production, tests pass | Different JVM args, JARs, classloader, or build artifact | Compare CLI/agent, dependency tree, resources, and weaving logs across environments |
| Warnings when weaving unrelated libraries | Package weaving filter too broad | Add `include within` limiting to application packages |

Two quick triage questions:

- **Is the advice running?** Inspect weaving logs/transaction debug output and verify internal methods get transactions.
- **Is the DB participating in the right transaction?** Check the manager, resource, and post-rollback data state.

If the first answer is yes and the second is no, tweaking proxy vs. AspectJ further usually will not fix the root cause.

## 11. When to Choose AspectJ vs. Keeping Proxies?

Choose **proxy mode** if you can place transactions on clear public service methods and callers invoke through Spring-managed beans. This fits most business use cases, is easy to test, and avoids JVM instrumentation dependencies. For instance, instead of `this.save()`, move the transaction boundary up to `submit()` or extract `save()` into another injected bean.

AspectJ is worth considering when:

- Transaction boundaries are needed on **self-invocation** where the architecture cannot easily be refactored.
- You genuinely need to intercept directly annotated **non-public implementation methods**.
- Advice must apply to objects **bypassing Spring proxies**, and the team can manage weaving/transaction aspect lifecycles.
- Controlled AspectJ CTW/LTW processes already exist in build and deployment.

Trade-offs to weigh: bytecode weaving tightens build/runtime setup; troubleshooting requires inspecting classloaders and woven classes; coordinating multiple aspects can grow complex. Switching modes solely because "AspectJ is stronger" rarely helps if service transaction boundaries are already clean.

A decision diagram:

```text
Is the transactional method called through a Spring proxy?
    |
    +-- Yes --> proxy mode is usually enough
    |
    +-- No --> can the boundary move to a public service
                     or be extracted to another bean?
                    |
                    +-- Yes --> consider restructuring, keep proxy
                    |
                    +-- No --> need self/non-public interception?
                                    |
                                    +-- Yes --> evaluate AspectJ + weaving
                                    |
                                    +-- No --> check manager/resource/lifecycle
```

## 12. Self-Check Questions

**Question 1.** Only `<tx:annotation-driven mode="aspectj"/>` is declared and `@Transactional` is added to a method. There is no `spring-aspects` and no weaving agent/build step. Does self-invocation get a transaction?

**Explanation:** No. Selecting the mode is not equivalent to transformed bytecode. You need `spring-aspects`, manager wiring, and actual CTW/LTW.

**Question 2.** `<aop:aspectj-autoproxy/>` is added while keeping `mode="proxy"`. Is `this.save()` intercepted by the transaction interceptor?

**Explanation:** No. `<aop:aspectj-autoproxy/>` still creates **Spring AOP proxies**; it performs no AspectJ bytecode weaving and does not fix self-invocation.

**Question 3.** An interface has `@Transactional`, while the implementation has no annotation. Does AspectJ necessarily pick up that transaction metadata?

**Explanation:** No. AspectJ follows Java's annotation inheritance rules; place annotations on concrete implementation classes/methods when weaving.

**Question 4.** Does class-level `@Transactional` turn every `private helper()` into a transactional method?

**Explanation:** No. With Spring's AspectJ transaction aspect, class-level annotations set defaults for public operations; you need annotations **directly on non-public methods** if you want them to be transactional join points.

**Question 5.** `@Transactional` is woven, yet the DAO uses a different datasource from the manager. Are both databases guaranteed to roll back?

**Explanation:** No. Weaving decides where advice runs; resources and transaction managers decide which data is governed.

**Question 6.** Using LTW, `aspectjweaver` is added to Maven and `mvn exec:java` is run without passing `-javaagent` at JVM startup. Are classes guaranteed to be woven?

**Explanation:** No. Adding a dependency to the classpath does not register a Java transformer. You need the agent or another configured and verified weaving infrastructure.

**Question 7.** `@Transactional(rollbackFor = IOException.class)` is woven properly and `IOException` escapes the method. Do rollback rules differ from proxy mode?

**Explanation:** Not in the nature of Spring's propagation/rollback rules; the difference is how the method is intercepted. With matching transaction manager/resources, configured checked exceptions also lead to rollback.

**Question 8.** A service uses `@Async` to run on another thread. Does enabling AspectJ automatically carry an open JDBC transaction to the new thread?

**Explanation:** No. Imperative transactions have thread-bound contexts; establish valid boundaries where the code executes and check coordination across threads.

## 13. Reliable Deployment Checklist

Before considering AspectJ mode operational, verify:

1. `@Transactional` sits on the concrete implementation class/method to intercept, and metadata matches business semantics.
2. `spring-aspects` matches the Spring version, and `AnnotationTransactionAspect` is not filtered out from weaving.
3. The transaction manager is wired to the aspect and manages the **right resource**.
4. One of **CTW/binary weaving/LTW** is selected, built, and actually executed—not merely added as a dependency.
5. Under LTW, JVM/agent/classloader and `META-INF/aop.xml` are correct; package includes cover target classes.
6. Deployment artifacts are not rebuilt or launched on another JVM omitting weaving.
7. Tests cover **self-invocation fail/success** and read post-conditions outside the transaction scope.
8. Needed exception types and propagations have clear tests, especially with nested or `REQUIRES_NEW`.
9. AOP proxy flags are never used as proof of bytecode weaving.
10. Weaving and transaction logs are safely scoped in production, exposing no sensitive data and avoiding unnecessary overhead.

## 14. Key Takeaways

**Proxy mode** places the transaction interceptor before a method via a Spring proxy; self-invocation bypasses the proxy. **AspectJ mode** uses Spring's transaction AspectJ aspect to weave advice into bytecode, enabling interception of internal calls and directly annotated non-public implementation methods.

The minimum conditions for this to hold are: **annotation on concrete target + `spring-aspects` + actual weaving + properly configured transaction manager + data access using matching resources**. `mode="aspectj"` only picks the advice strategy; it does not run `ajc`, attach a Java agent, or convert already-loaded classes into woven classes.

## Official Documentation

- [Spring Framework 6.2 — Using @Transactional (proxy vs AspectJ mode)](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/declarative/annotations.html)
- [Spring Framework — Using @Transactional with AspectJ](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/aspectj.html)
- [Spring Framework — Using AspectJ with Spring Applications; load-time weaving](https://docs.spring.io/spring-framework/reference/6.2/core/aop/using-aspectj.html)
- [Spring Framework — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html)
- [AspectJ Development Environment Guide](https://eclipse.dev/aspectj/doc/latest/devguide/devguide.html)
- [AspectJ Weaver agent artifact](https://central.sonatype.com/artifact/org.aspectj/aspectjweaver/1.9.25)
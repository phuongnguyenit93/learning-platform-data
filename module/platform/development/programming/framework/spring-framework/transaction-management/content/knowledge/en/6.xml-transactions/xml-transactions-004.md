# Method-Name Transaction Policies and Pattern Precedence in XML Configuration

## 1. Problem: one service, multiple transaction policies

In Spring Framework, you can assign transaction policies to **groups of methods by name** without placing `@Transactional` on every Java method. Traditional XML configuration uses:

- `<aop:pointcut>` to determine **which bean method calls** can receive advice.
- `<aop:advisor>` to bind that pointcut to the transaction advice.
- `<tx:advice>` and `<tx:attributes>` to declare **transaction attributes**.
- Each `<tx:method name="...">` defines a method-name matching rule, such as `get*`, `save*`, `*`, or an exact name.

The tricky part of this topic is: **if multiple patterns match a method name, which rule does Spring choose?** And does the order of lines in XML determine precedence?

Consider a service containing:

```java
public class AccountService {
    public long getBalance() { /* read */ return 0; }
    public void getAndChangeBalance(long delta) { /* write */ }
    public void saveAccount() { /* write */ }
    public void updateBalance(long delta) { /* write */ }
}
```

We want `getBalance` to be read-only, `saveAccount` to have its own rollback policy, and all other operations to receive a default transaction. However, `getAndChangeBalance` **both matches `get*` and actually writes data**, so an exact rule is needed to override the read configuration.

To understand this properly, distinguish **two selection layers**:

1. Does the **AOP pointcut** select the call? If not, this transaction advice is not executed.
2. Which `<tx:method>` configuration does **`TransactionAttributeSource`** choose for the method name? The single chosen rule determines the entire set of attributes for that transaction.

The `name` syntax is a method-name pattern, **not** a Java regular expression, not a Spring bean name, not an endpoint path, and not a table name.

## 2. XML structure and the role of each part

A basic read/write configuration:

```xml
<tx:advice id="txAdvice" transaction-manager="txManager">
    <tx:attributes>
        <tx:method name="get*" read-only="true"/>
        <tx:method name="save*" propagation="REQUIRED"
                   rollback-for="com.example.BusinessException"/>
        <tx:method name="*" propagation="REQUIRED"/>
    </tx:attributes>
</tx:advice>

<aop:config>
    <aop:pointcut id="serviceOps"
                  expression="execution(* com.example.service.*Service.*(..))"/>
    <aop:advisor pointcut-ref="serviceOps" advice-ref="txAdvice"/>
</aop:config>
```

This is an **illustrative XML snippet**, not a standalone `<beans>` file: the `txManager` and service beans must exist, and the `tx` and `aop` namespaces/XSDs must be declared. A complete runnable example appears in Section 7.

Explanation:

| Part | What does it decide? | Example |
| --- | --- | --- |
| `<aop:pointcut expression="...">` | Which join points/calls are selected | Methods in service classes within a specified package |
| `<aop:advisor>` | Which advice applies to which pointcut | `txAdvice` for `serviceOps` |
| `<tx:advice transaction-manager="txManager">` | Which manager the transaction interceptor uses | `JdbcTransactionManager`, `JpaTransactionManager` depending on resource |
| `<tx:attributes>` | List of transaction rules by method name | `get*`, `save*`, `*` |
| `<tx:method name="get*">` | Configuration for the group of names matching the pattern | Read-only, propagation, rollback rules... |

**The two kinds of `*` do not play the same role:** the `*` in `execution(* ... )` belongs to AspectJ pointcut syntax; the `*` in `<tx:method name="get*">` is a simple method-name wildcard. Do not put full pointcut syntax as the value of `name`.

If a method named `getBalance` belongs to an object outside the pointcut, `getBalance` matching `get*` is **not enough** to apply transaction advice. Conversely, if a call matches the pointcut but matches no `<tx:method>`, this advice supplies no transaction attributes for that call. An active transaction from the caller may still exist if created by outer code, but **not opened by this unmatched rule**.

## 3. Method-name pattern syntax: exact, wildcard, fallback

The `name` of `<tx:method>` is compared against the **Java method name**. Spring uses simple matching with the `*` wildcard, which is case-sensitive.

| Pattern | Matches | Does not match |
| --- | --- | --- |
| `getBalance` | Only the name `getBalance` | `getBalanceById`, `GetBalance` |
| `get*` | `get`, `getBalance`, `getById` | `findBalance`, `GETBalance` |
| `*Account` | `saveAccount`, `deleteAccount` | `saveAccountById` |
| `*ById` | `findById`, `deleteById` | `findAll` |
| `*Order*` | `getOrder`, `updateOrderStatus` | `getAccount` |
| `*` | Every method name within advice scope | No method name is excluded by this pattern |

Because this is a **simple wildcard**, `get.*` is not interpreted as regex "get followed by any character"; the dot is a literal character, so it does not replace `get*`. Syntax like `?`, character classes `[a-z]`, or `^get` are also not regex features supported by `name`. Overloads such as `getBalance()` and `getBalance(long)` share the same name `getBalance`, so **you cannot select separate policies by parameter count/type using `<tx:method name>` alone**. To select by parameter types, express it in the AOP pointcut or use a different API/configuration design.

Typically, a readable rule set consists of: **exact patterns for exceptions**, **prefix/suffix patterns with clear intent**, and the `*` pattern as a **fallback** if you want all pointcut-selected methods to have transactions.

Example:

```xml
<tx:attributes>
    <tx:method name="getAndChangeBalance" read-only="false"/>
    <tx:method name="get*" read-only="true"/>
    <tx:method name="save*" rollback-for="com.example.BusinessException"/>
    <tx:method name="*" propagation="REQUIRED"/>
</tx:attributes>
```

Here `getAndChangeBalance` must be read according to the **exact** rule, even though its name starts with `get`. This is one reason to inspect actual method names instead of assuming every name starting with `get` only reads data.

## 4. Precedence rules: exact first, then most specific matching pattern

Spring implements method-name rule sets via `NameMatchTransactionAttributeSource`. The key rules of this attribute source are:

1. **Exact match takes priority:** if the method name equals a key in the map verbatim, use that rule immediately.
2. **If no exact match:** scan matching wildcard patterns and pick the **most specific pattern by pattern string length** (in the implementation, the pattern with the larger `length` wins).
3. **Fallback `*`** has length 1, so it wins only when no longer pattern matches.
4. **When two different wildcard patterns both match and have the same length**, do not build logic that depends on "the top line wins" or "the bottom line wins." Fix the configuration to avoid collisions or add an exact match.

This is **precedence when selecting one method-name rule**, not AOP advisor `order`, not exception rollback precedence, and not precedence between two transaction managers.

### 4.1. Exact always beats wildcard

```xml
<tx:attributes>
    <tx:method name="get*" read-only="true"/>
    <tx:method name="getAndChangeBalance" read-only="false"/>
    <tx:method name="*" read-only="false"/>
</tx:attributes>
```

Results:

- `getBalance` selects `get*` → `read-only=true`.
- `getAndChangeBalance` selects exact `getAndChangeBalance` → `read-only=false`.
- `updateBalance` selects `*` → `read-only=false`.

In the example above, the exact rule placed **after** `get*` still wins. Do not interpret it as a firewall "first match wins" model: that is **not** how `NameMatchTransactionAttributeSource` works.

### 4.2. Overlapping wildcards: pattern length decides

Suppose the rules are:

```xml
<tx:attributes>
    <tx:method name="get*" read-only="true"/>
    <tx:method name="*Balance" read-only="false"/>
    <tx:method name="*" read-only="false"/>
</tx:attributes>
```

Method `getBalance` matches both `get*` (4 characters) and `*Balance` (8 characters). Because there is no exact match, `*Balance` is longer, so **`read-only=false`** is selected. This can be surprising if an author assumes the `get*` prefix is always more important than a suffix.

Adding:

```xml
<tx:method name="getBalance" read-only="true"/>
```

makes exact `getBalance` beat both wildcards. Pattern string length is the selection rule of Spring's current implementation, **not a semantic scoring system where "read" outranks "write."**

### 4.3. Overlapping patterns of the same length

For example, `get*` and `*By` both have 4 characters; for a method `getBy`, both can match. Do not rely on the positions of the two XML elements to assume one rule will always win across all configuration/version changes. Pick one of two safe approaches:

- Add `<tx:method name="getBy" .../>` with an explicit policy.
- Change the patterns/service naming so the groups do not overlap functionally.

**Note:** do not equate "longest pattern" with "pattern with fewest wildcards." A long pattern name does not automatically guarantee narrower semantics in every case; when wildcards overlap, prefer an exact match or regroup them.

### 4.4. A method receives its entire policy from the single chosen rule

If configured as:

```xml
<tx:attributes>
    <tx:method name="get*" read-only="true"/>
    <tx:method name="getAccount" propagation="REQUIRES_NEW"/>
    <tx:method name="*" rollback-for="java.lang.Exception"/>
</tx:attributes>
```

then `getAccount` is matched by the **exact rule**, with `propagation=REQUIRES_NEW`. Do not infer "Spring will merge `read-only=true` from `get*` and `rollback-for` from `*` onto the exact rule." Attributes are not inherited or combined across multiple matching `<tx:method>` entries. Each rule holds its own values, and omitted parts use **default transaction attribute values**, such as `read-only=false`, rather than taking them from wildcard rules below.

This is why you must specify all important attributes in a dedicated rule, especially when it alters semantics relative to the default group.

## 5. Transaction attributes attached to each pattern

Commonly used attributes in `<tx:method>`:

| Attribute | Values / Meaning | Common Default |
| --- | --- | --- |
| `name` | Method name or wildcard pattern; **required** | None |
| `propagation` | `REQUIRED`, `REQUIRES_NEW`, `SUPPORTS`, `MANDATORY`, `NOT_SUPPORTED`, `NEVER`, `NESTED` | `REQUIRED` |
| `isolation` | `DEFAULT`, `READ_COMMITTED`, `REPEATABLE_READ`, `SERIALIZABLE`, ... | `DEFAULT` |
| `read-only` | Hint for read transactions; not an authorization mechanism | `false` |
| `timeout` | Seconds, when supported by the transaction manager/transaction type | `-1` (uses system default) |
| `rollback-for` | Exception type names/patterns triggering rollback, comma-separated | RuntimeException and Error by default; checked Exception does not roll back by default |
| `no-rollback-for` | Exception type names/patterns that do not trigger rollback | No additional rules |

With `propagation=REQUIRED`, if no transaction exists, Spring opens a new one; if a compatible transaction already exists, the method typically joins it. `REQUIRES_NEW` creates an independent transaction and can suspend an outer transaction; do not choose it merely to "save immediately." `SUPPORTS` may run **without an actual transaction** if the caller has none. `read-only=true` is a hint for optimization or DB-side enforcement depending on manager/driver, **not an absolute guarantee prohibiting every write SQL statement**.

`isolation`, `timeout`, and `read-only` usually have configuration effect for a **newly created transaction** and have specific limitations when a method only joins an existing transaction. When you need to change isolation or timeout, determine in which scope the transaction is actually opened.

### 5.1. Rollback rules are not method-name precedence

There are **two distinct selection steps**:

1. Spring picks **one** `<tx:method name="...">` rule by exact/wildcard matching.
2. When the method throws an exception, within that chosen rule alone, Spring decides rollback using exception rules: `rollback-for`, `no-rollback-for`, and default rules.

Example:

```xml
<tx:attributes>
    <tx:method name="save*" rollback-for="demo.xmltx.BusinessException"/>
    <tx:method name="*" propagation="REQUIRED"/>
</tx:attributes>
```

If `saveThenFail` throws checked `BusinessException`, the `save*` rule decides rollback. The `*` rule **is not consulted further to "supply missing" rollback attributes**.

Differences regarding wildcards:

- `name="save*"`: `*` is a wildcard for **method names**.
- `rollback-for="demo.xmltx.BusinessException"`: expression matching **exception type names** per Spring's rollback rule mechanism; **do not** use `*` to form a glob. Prefer fully qualified exception names to avoid accidentally matching another class containing a similar substring.
- If both `rollback-for` and `no-rollback-for` appear in the **same rule**, the stronger matching exception rule determines the outcome. This is a **different** precedence system from method-pattern ordering.

Without exception rules configured, Spring rolls back by default on `RuntimeException` and `Error`; ordinary checked `Exception` types do not trigger rollback by default. Swallowing exceptions inside a method can also let the transaction finish normally unless it has already been marked rollback-only.

## 6. Outcome table for a rule set with exceptions

Consider the configuration used throughout this lesson:

```xml
<tx:attributes>
    <tx:method name="getAndChangeBalance" read-only="false"/>
    <tx:method name="get*" read-only="true"/>
    <tx:method name="save*" rollback-for="demo.xmltx.BusinessException"/>
    <tx:method name="*" propagation="REQUIRED"/>
</tx:attributes>
```

Assuming calls **all go through the proxy** and match the service pointcut, we get:

| Method | Matched Pattern | Propagation | Read-only | Rollback Policy |
| --- | --- | --- | --- | --- |
| `getSnapshot()` | `get*` | `REQUIRED` (default) | `true` | Default |
| `getAndChangeBalance(5)` | `getAndChangeBalance` (exact) | `REQUIRED` | `false` | Default |
| `saveThenFail(20)` | `save*` | `REQUIRED` | `false` | Rolls back `BusinessException` too |
| `updateBalance(3)` | `*` | `REQUIRED` | `false` | Default |
| `deleteAccount()` | `*` | `REQUIRED` | `false` | Default |

The rows specify **transaction characteristics**, not whether the method actually wrote to the DB. `read-only=true` does not turn a method into a SELECT; if mistakenly assigned to a write method, behavior depends on the resource/transaction manager—it may be blocked or mis-optimized.

One way to self-verify the policy is to observe inside the method:

```java
TransactionSynchronizationManager.isActualTransactionActive();
TransactionSynchronizationManager.isCurrentTransactionReadOnly();
```

These two APIs report the transaction state Spring sees on the thread at the moment of invocation. They are useful for testing imperative JDBC/JPA configuration, though they do not replace real commit/rollback tests. In reactive transactions, context is not similarly thread-local.

## 7. Complete example: Spring XML, JDBC, H2, and precedence rules

The example below is an **independent Gradle project**, using **Java 17 + Spring Framework 6.2.12 + H2** and pure XML configuration, without Spring Boot and without `@Transactional` on the service. The key point to see is that XML itself drives transactions.

Structure:

```text
xml-transaction-policy/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/demo/xmltx/
    │   ├── App.java
    │   ├── AccountService.java
    │   └── BusinessException.java
    └── resources/
        └── tx-context.xml
```

### 7.1. Dependencies and Java version

**`settings.gradle`**

```groovy
rootProject.name = 'xml-transaction-policy'
```

**`build.gradle`**

```groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.12'
    implementation 'org.springframework:spring-aop:6.2.12'
    implementation 'org.springframework:spring-jdbc:6.2.12'
    implementation 'org.springframework:spring-tx:6.2.12'
    implementation 'org.aspectj:aspectjweaver:1.9.24'
    runtimeOnly 'com.h2database:h2:2.3.232'
}

application {
    mainClass = 'demo.xmltx.App'
}
```

`spring-context` reads XML and creates beans; `spring-tx` provides transaction advice; `spring-jdbc` supports `JdbcTemplate` and `JdbcTransactionManager`; `spring-aop` together with `aspectjweaver` evaluates `execution(...)` expressions. H2 is the in-memory database for the demo. If a project manages Spring versions via a BOM or version catalog, keep Spring module versions aligned.

### 7.2. Complete XML configuration

**`src/main/resources/tx-context.xml`**

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

    <!-- Use DriverManagerDataSource only in small examples. -->
    <bean id="dataSource"
          class="org.springframework.jdbc.datasource.DriverManagerDataSource">
        <property name="driverClassName" value="org.h2.Driver"/>
        <property name="url" value="jdbc:h2:mem:xmlpolicy;DB_CLOSE_DELAY=-1"/>
        <property name="username" value="sa"/>
        <property name="password" value=""/>
    </bean>

    <bean id="jdbc"
          class="org.springframework.jdbc.core.JdbcTemplate">
        <constructor-arg ref="dataSource"/>
    </bean>

    <bean id="txManager"
          class="org.springframework.jdbc.support.JdbcTransactionManager">
        <constructor-arg ref="dataSource"/>
    </bean>

    <bean id="accountService" class="demo.xmltx.AccountService">
        <constructor-arg ref="jdbc"/>
    </bean>

    <tx:advice id="txAdvice" transaction-manager="txManager">
        <tx:attributes>
            <!-- Exact: a get* method that actually writes data. -->
            <tx:method name="getAndChangeBalance"
                       propagation="REQUIRED" read-only="false"/>

            <!-- All other get* methods are read-only. -->
            <tx:method name="get*" read-only="true"/>

            <!-- Business checked exception also triggers rollback. -->
            <tx:method name="save*"
                       rollback-for="demo.xmltx.BusinessException"/>

            <!-- All other methods receive the default transaction. -->
            <tx:method name="*" propagation="REQUIRED"/>
        </tx:attributes>
    </tx:advice>

    <aop:config>
        <aop:pointcut id="accountServiceOps"
                      expression="execution(* demo.xmltx.AccountService.*(..))"/>
        <aop:advisor pointcut-ref="accountServiceOps"
                     advice-ref="txAdvice"/>
    </aop:config>
</beans>
```

**Notes on namespaces and wiring:**

- `transaction-manager="txManager"` must point to the right bean. If omitted, `<tx:advice>` looks up `transactionManager` by default; the bean in this example is named `txManager`, so it must be specified explicitly.
- `<aop:advisor>` links service calls with `txAdvice`. Having `<tx:advice>` alone without an advisor/pointcut does not give the service transactions from this configuration.
- `AccountService` in the demo is a public, non-final class with public transactional methods; Spring can create a class-based proxy because the service implements no interface. Creating the service with `new` outside the container bypasses advice.
- `DriverManagerDataSource` does not use connection pooling; suitable for a short demo, while production should use a pool such as HikariCP.
- `<tx:annotation-driven/>` is not needed in the example because policies are specified **in XML by method name**, not via annotation metadata.

### 7.3. Java service and checked exception

**`src/main/java/demo/xmltx/BusinessException.java`**

```java
package demo.xmltx;

public class BusinessException extends Exception {
    public BusinessException(String message) {
        super(message);
    }
}
```

**`src/main/java/demo/xmltx/AccountService.java`**

```java
package demo.xmltx;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.support.TransactionSynchronizationManager;

public class AccountService {
    private final JdbcTemplate jdbc;

    public AccountService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public String getSnapshot() {
        Long balance = jdbc.queryForObject(
            "SELECT balance FROM accounts WHERE id = 1", Long.class);
        return "balance=" + balance + ", " + txState();
    }

    public void getAndChangeBalance(long delta) {
        System.out.println("exact getAndChangeBalance: " + txState());
        jdbc.update(
            "UPDATE accounts SET balance = balance + ? WHERE id = 1",
            delta);
    }

    public void saveThenFail(long delta) throws BusinessException {
        System.out.println("saveThenFail: " + txState());
        jdbc.update(
            "UPDATE accounts SET balance = balance + ? WHERE id = 1",
            delta);
        throw new BusinessException("checked failure");
    }

    public void updateBalance(long delta) {
        System.out.println("fallback updateBalance: " + txState());
        jdbc.update(
            "UPDATE accounts SET balance = balance + ? WHERE id = 1",
            delta);
    }

    private String txState() {
        return "tx="
            + TransactionSynchronizationManager.isActualTransactionActive()
            + ", readOnly="
            + TransactionSynchronizationManager.isCurrentTransactionReadOnly();
    }
}
```

Method `txState()` is a private helper to **observe state** and needs no separate advice; calls from the public methods happen while the corresponding transaction is open. Method `saveThenFail()` intentionally throws a **checked exception** after SQL to demonstrate the effect of `rollback-for` in the `save*` pattern.

### 7.4. Create table, call proxy, and check output

**`src/main/java/demo/xmltx/App.java`**

```java
package demo.xmltx;

import org.springframework.context.support.ClassPathXmlApplicationContext;
import org.springframework.jdbc.core.JdbcTemplate;

public class App {
    public static void main(String[] args) {
        try (var context = new ClassPathXmlApplicationContext("tx-context.xml")) {
            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);
            jdbc.execute(
                "CREATE TABLE accounts (id BIGINT PRIMARY KEY, balance BIGINT NOT NULL)");
            jdbc.update(
                "INSERT INTO accounts (id, balance) VALUES (1, 100)");

            AccountService service = context.getBean(AccountService.class);

            System.out.println("initial: " + service.getSnapshot());

            service.getAndChangeBalance(5);
            System.out.println("after exact: " + service.getSnapshot());

            try {
                service.saveThenFail(20);
            } catch (BusinessException ex) {
                System.out.println("caught: " + ex.getMessage());
            }
            System.out.println("after rollback: " + service.getSnapshot());

            service.updateBalance(3);
            System.out.println("after fallback: " + service.getSnapshot());
        }
    }
}
```

If the project has a Gradle Wrapper (run `gradle wrapper` with a compatible Gradle installation if not present), the execution command on Linux/macOS is:

```bash
./gradlew run
```

On Windows PowerShell:

```powershell
.\gradlew.bat run
```

**Lines printed by the program, in order** (Spring/Gradle logs may also appear):

```text
initial: balance=100, tx=true, readOnly=true
exact getAndChangeBalance: tx=true, readOnly=false
after exact: balance=105, tx=true, readOnly=true
saveThenFail: tx=true, readOnly=false
caught: checked failure
after rollback: balance=105, tx=true, readOnly=true
fallback updateBalance: tx=true, readOnly=false
after fallback: balance=108, tx=true, readOnly=true
```

Step-by-step explanation:

1. `getSnapshot` matches `get*`: Spring creates a read-only transaction; `tx=true, readOnly=true`. Balance is 100.
2. `getAndChangeBalance` matches exact: read-write transaction despite the `get` prefix; updates by +5, commits when the proxy method ends. Balance becomes 105.
3. `saveThenFail` matches `save*`, runs an UPDATE adding 20, then throws `BusinessException`. Because `rollback-for` is configured for this checked exception, the transaction rolls back; balance afterward remains 105.
4. `updateBalance` matches neither exact, `get*`, nor `save*`, so it receives `*`: read-write transaction and commits successfully; final balance is 108.

This is a **runnable XML policy** example with the dependencies and project structure shown; `jdbc.execute` initializes the schema at the start of `main`, so no migration tool is needed in this short example. Copying only the Java snippets without the XML and dependencies will not run.

### 7.5. Why do results differ when called the wrong way?

- If you call `new AccountService(jdbc).saveThenFail(...)` outside the Spring context, the service is not proxied and there is no `@Transactional` in the code, so there is no XML transaction advice; JDBC may run in autocommit mode and the UPDATE is not rolled back as expected.
- If a method in `AccountService` directly calls `this.saveThenFail(...)`, self-invocation does not go through the Spring AOP proxy; it **does not** apply the dedicated transaction advice of the called method name. If already inside an outer method's transaction, SQL can still participate in that transaction, but the `save*` policy itself is not applied to the internal call.
- If you delete `<aop:advisor>` or miswrite the pointcut, `<tx:method>` elements may still parse validly yet never apply to the intended calls.
- If you declare `<tx:method name="get*" read-only="true"/>` and forget the exact `getAndChangeBalance` rule, the write method receives the read-only hint; behavior can vary by DB/driver. Avoid naming write methods so they look like read methods whenever possible.

## 8. Distinguishing XML order, pattern specificity, and AOP advisor order

Three concepts are often mixed up:

| Mechanism | Controls | Does the upper `<tx:method>` win? |
| --- | --- | --- |
| Exact/wildcard name matching | Choosing one transaction attribute for a **method name** | No; exact first, then more specific wildcard |
| `<aop:advisor order="...">` | Application order of **multiple advisors/aspects** at the same join point | Unrelated to how `name` is matched |
| `rollback-for` and `no-rollback-for` | Rollback decision when an exception occurs within the **already chosen rule** | No; stronger matching exception rule decides |

If two different advisors both select the same method, there may be two advice chains with different transaction semantics. Do not assume that XML from advisor A with `get*` will be "merged" with `save*` from advisor B into one unified policy. Restrict pointcuts, coordinate advisor order, and minimize overlapping policies. When combining `<tx:annotation-driven/>`/`@Transactional` with XML `<tx:advice>` on the same bean, test explicitly which mechanism actually intercepts calls; do not assume one automatically overrides the other.

If `<tx:annotation-driven/>` is used, transaction attributes typically come from annotations on classes/methods; `<tx:method>` syntax is **not a field of `@Transactional`**. This article covers only **XML declarative transaction policy by method name**.

## 9. Common pitfalls

### 9.1. Omitting fallback leaves some methods unconfigured for transactions

```xml
<tx:attributes>
    <tx:method name="get*" read-only="true"/>
    <tx:method name="save*" propagation="REQUIRED"/>
</tx:attributes>
```

`deleteAccount` matches no rule, so this advice does not open a transaction for that method. If all service methods are required to be transactional, add `<tx:method name="*"/>` or adjust pointcuts/policy groups accordingly. If non-transactional methods are intentional, omitting the fallback is a valid design choice, though it needs testing.

### 9.2. An overly broad pattern changes semantics unexpectedly

`get*` can accidentally select a write method like `getOrCreateUser`; `save*` can affect a method that only checks/updates a cache. Prefer **naming methods to reflect actual behavior**, use exact rules for exceptions, and test policies when refactoring API names.

### 9.3. Relying on XML order to resolve pattern overlap

Swapping the order between `get*` and `*Balance` is not a reliable fix. Check pattern lengths, add exact rules when needed, and avoid same-length overlapping matches. Renaming a method can silently change the applied rule without causing a compile error.

### 9.4. Treating `read-only=true` as a mechanism blocking all UPDATEs

`read-only` is a transaction hint/setting; managers/drivers/databases may enforce it differently. It is not a security boundary. Control permissions at the DB level, test write behavior, and use read-write transactions for methods that genuinely modify data.

### 9.5. Reading policy on a method but calling internally inside the bean

Standard Spring AOP proxies apply advice to calls **entering through the proxy**. `this.saveAccount()` within the same object does not re-select the `save*` rule. Split services, call through an appropriate Spring bean, or design clear transaction boundaries rather than relying on self-invocation.

### 9.6. Placing `rollback-for` on a wildcard and expecting exact rules to inherit it

If an exact match exists without `rollback-for`, the exact rule gets its default rollback semantics; the wildcard rule does not "top up" rollback rules. To make a checked exception roll back both exact and fallback methods, declare it explicitly on each relevant rule or redesign the rule grouping.

### 9.7. Applying XML to multiple layers at once

A pointcut like `execution(* com.example..*(..))` is too broad and can wrap controllers, repositories, and utilities; multiple nested transaction scopes create hard-to-control behavior. Choose the **service boundary** as where business transactions are declared, using a clear pointcut. Broaden only when there is a verified technical reason.

### 9.8. Picking the wrong transaction manager or resource

`<tx:advice transaction-manager="txManager">` does not create a `DataSource` or `EntityManagerFactory`. For JDBC use a DataSource-compatible manager; for JPA use a JPA-compatible manager. With multiple DBs/managers, explicitly specify which bean the advisor uses. A single `@Transactional`/`<tx:advice>` does not create a distributed transaction across multiple uncoordinated resources.

## 10. Process for designing and testing an XML policy

Before putting a rule set into a real module:

1. **List all public service methods** covered by the pointcut, including methods after renaming/refactoring.
2. **Group behaviors:** reads, writes, special operations needing different propagation/timeout/rollback.
3. **Add fallback intentionally:** `*` if every pointcut-matched method should have a transaction; omit if remaining methods are intentionally excluded from this advice.
4. **Add exact matches** for exceptions that could match multiple patterns or misleading names like `getAndChangeBalance`.
5. **Check wildcard overlaps:** which pattern is longer; do two same-length patterns both match; if so, eliminate ambiguity.
6. **Explicitly write non-default attributes:** propagation, read-only, rollback-for, and any attributes that must apply, without relying on "inheritance" from `*`.
7. **Test with real proxies** and a transactional database: observe active transaction, readOnly, commit, and rollback after exceptions; verify methods outside the pointcut.
8. **Retest after renaming methods** or changing advisor order/types; those changes do not necessarily produce compile errors even though transaction semantics have changed.

You can document an expected-policy table in docs or integration tests:

| Method | Expected | Evidence |
| --- | --- | --- |
| `getSnapshot` | `get*` read-only | `tx=true, readOnly=true` |
| `getAndChangeBalance` | Exact read-write | `readOnly=false` and writes commit |
| `saveThenFail` | `save*` rolls back checked `BusinessException` | After exception, DB keeps balance 105 |
| `updateBalance` | Fallback `*` read-write | After return, DB has balance 108 |

In Spring tests, be careful if the test method itself is wrapped in `@Transactional`: data may be rolled back by the **test's** transaction after assertions run, skewing observation of service commits. To verify real commits, call the service from a scope without an outer transaction or design test transaction boundaries clearly.

## 11. Comprehension check questions

**1. `getAccount` matches `get*`, `*Account`, and `*`. Which rule wins when there is no exact match?**  
`*Account` has a longer pattern string than `get*` and `*`, so it is selected in `NameMatchTransactionAttributeSource`.

**2. What if `<tx:method name="getAccount" read-only="true"/>` is added at the end of the list?**  
Exact match beats wildcards. It does not depend on being last.

**3. Does an exact rule specifying only `propagation=REQUIRES_NEW` automatically pick up `read-only=true` from `get*`?**  
No. Spring chooses one transaction attribute definition; omitted attributes receive defaults and are not merged from other wildcards.

**4. What should you do when two same-length patterns both match a method name?**  
Do not rely on XML order as a business contract. Add an exact rule or redesign the patterns to avoid conflict.

**5. Why would a method matching `save*` not roll back as expected?**  
Check the pointcut, whether calls go through the proxy, whether the manager is right, whether exceptions are swallowed, and whether checked exceptions have `rollback-for` declared.

**6. Does `name="save*"` match Java methods regardless of upper/lower case?**  
No; simple matching is case-sensitive, so `SaveAccount` does not match `save*`.

**7. What happens if a method matches the AOP pointcut but matches no method-name rule?**  
This advice provides no transaction attribute for the method; a transaction is not opened solely because of the pointcut.

## 12. Key takeaways

**XML method-name transaction configuration is the intersection of an AOP pointcut and `<tx:method>` policies.** When a method is within the advice's scope, Spring prioritizes **exact name**, then **longest matching wildcard pattern**, with `*` as fallback. Once a rule is chosen, Spring uses **all transaction attributes of that rule** with defaults for undeclared attributes; it does not combine policies from multiple rules.

Therefore, a maintainable policy set typically has **clear naming conventions**, a few **exact exception rules**, unambiguous **group wildcards**, an **intentionally chosen fallback**, and testing via **Spring proxies + a real transactional database**.

## References

- Spring Framework 6.2, *Example of Declarative Transaction Implementation*: https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/declarative/first-example.html
- Spring Framework 6.2, *`<tx:advice/>` Settings*: https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/declarative/txadvice-settings.html
- Spring Framework 6.2, *Rolling Back a Declarative Transaction*: https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/declarative/rolling-back.html
- Spring Framework, *Understanding Declarative Transaction Implementation*: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html
- Spring Framework, *Using `@Transactional`*: https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/declarative/annotations.html
- Spring Framework API, *NameMatchTransactionAttributeSource*: https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/transaction/interceptor/NameMatchTransactionAttributeSource.html
- Spring Framework API, *TransactionSynchronizationManager*: https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/transaction/support/TransactionSynchronizationManager.html

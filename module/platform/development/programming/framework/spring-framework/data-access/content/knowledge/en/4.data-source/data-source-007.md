# DataSource Obtained via JNDI in Managed Environments

When a Java/Spring application runs in a **managed environment** (such as a WAR application deployed on Apache Tomcat or a Jakarta EE application server), administrators typically configure database connections at the container level. The application does not create pools itself or embed JDBC configuration in source code; instead, it **looks up a `javax.sql.DataSource` object registered by the environment** via JNDI (Java Naming and Directory Interface). This `DataSource` object is then supplied to Spring components such as `JdbcTemplate`, repositories, or transaction managers.

This lesson focuses on the *DataSource via JNDI* mechanism, how to configure container-side resources, connecting the resource to Spring, testing, and common operational errors. Examples use Java 17+, Spring Framework 6+, and Tomcat 10.1; other servers have different declaration syntax and namespaces.

## 1. Learning Outcomes

After this lesson, you can:

1. Explain the distinct roles of `DataSource`, JNDI naming service, JDBC driver, connection pool, and Spring.
2. Distinguish the JNDI name `java:comp/env/jdbc/LearningDB` from the JDBC URL `jdbc:h2:mem:learning`, as well as the relative namespace `jdbc/LearningDB`.
3. Declare a `DataSource` resource in the container, map it into the web application's environment, and look it up using Java or Spring.
4. Create a Spring `DataSource` bean from `JndiDataSourceLookup`, inject it into `JdbcTemplate`, and manage connections properly.
5. Identify the difference between *container-managed pooling* and *container-managed transactions*; avoid configuring two incompatible transaction mechanisms.
6. Diagnose missing JNDI context, wrong resource name, missing JDBC driver, and database connection failures.

## 2. Operating Model: Who Provides What?

**`javax.sql.DataSource`** is the JDBC interface representing a provider of `java.sql.Connection`. It is not required to be a connection pool: an implementation may create a new connection each time, use a pool, or provide transaction-managed connections. With Tomcat in this example, the JNDI resource points to a `DataSource` created and managed by the container's pool.

**JNDI** is an API for naming and looking up objects or resources. The application asks a naming provider for a logical name; the provider returns the resource that has been bound/configured. JNDI is not a database connection protocol, does not execute SQL itself, and does not by itself guarantee pooling.

**The JDBC driver** implements the concrete connection to the database. It can be loaded by the container's classloader when the container builds the pool. **Spring JDBC** uses the injected `DataSource` and provides abstractions like `JdbcTemplate`; Spring does not necessarily know the database URL, user, or password.

~~~text
Operations team / container configuration
  ├─ JDBC driver + JDBC URL + credentials
  ├─ Connection pool, connection limits, timeouts
  └─ JNDI binding: java:comp/env/jdbc/LearningDB
                          │
               InitialContext / lookup
                          ▼
             DataSource (javax.sql.DataSource)
                          │
             @Bean dataSource() in Spring
                          │
          JdbcTemplate / Repository / Service
                          │
                    getConnection()
                          ▼
                       Database
~~~

Key point: **Spring receives `DataSource` through a stable JNDI name**, while actual connection parameters live in the deployment environment. The application can use the same interface across different environments, provided each environment supplies a resource with the right name and type.

### Comparing JNDI vs. Self-Configured Pool

| Criterion | DataSource via JNDI | Application-Configured DataSource |
| --- | --- | --- |
| Who creates `DataSource`? | Container/naming provider | Application or framework auto-configuration |
| Who configures JDBC URL/credentials? | Deployment environment | Application config/secret manager |
| Who manages the pool? | Container's resource factory | Application's pool implementation |
| Business code dependency | Typically depends only on `DataSource` | Should also depend only on `DataSource` |
| Suitable for | WAR in external container/application server with JNDI | Standalone service, executable JAR, environments without JNDI |

Neither option is automatically superior in all cases. The decision depends on the deployment model, operational requirements, and infrastructure ownership.

## 3. JNDI Namespaces and Resource Names

JNDI works with **names**, for example:

- `java:comp/env`: the *environment naming context* (ENC) area of a component/web application in the Jakarta EE model.
- `jdbc/LearningDB`: logical name typically declared relatively inside the application's ENC.
- `java:comp/env/jdbc/LearningDB`: full path to the resource when the deployment environment provides the corresponding namespace.

In Tomcat, declaring a resource with `name="jdbc/LearningDB"` under `<Context>` makes the resource available in that web application's `java:comp/env` namespace. Here `jdbc/LearningDB` is not a JDBC URL; it is just a key to look up an object.

Java example using the JNDI API:

~~~java
import javax.naming.InitialContext;
import javax.sql.DataSource;

InitialContext initialContext = new InitialContext();
DataSource dataSource = (DataSource)
        initialContext.lookup("java:comp/env/jdbc/LearningDB");
~~~

This is an **illustrative code snippet inside an environment with a JNDI provider**, not a complete standalone Java file. If run in an ordinary JVM without a naming context provided, `new InitialContext()` may construct the object, yet `lookup(...)` fails, typically with `NoInitialContextException`.

You can also look up relatively through an already retrieved ENC:

~~~java
import javax.naming.Context;
import javax.naming.InitialContext;
import javax.sql.DataSource;

Context environment = (Context)
        new InitialContext().lookup("java:comp/env");
DataSource dataSource = (DataSource)
        environment.lookup("jdbc/LearningDB");
~~~

Both approaches target the same resource in the **example Tomcat configuration**. Another application server might expose namespaces such as `java:jboss/datasources/...` or its own global name; do not arbitrarily prepend `java:comp/env/` to every kind of name.

**Package note:** `javax.naming.*` and `javax.sql.DataSource` remain in Java SE. Even though Tomcat 10+ Servlet code uses `jakarta.servlet.*`, do not change `javax.sql.DataSource` to `jakarta.sql.DataSource`; the latter is not the corresponding JDBC interface.

## 4. Container Example: Registering DataSource in Tomcat 10.1

Let us create a development resource with in-memory H2. Actually running the example requires Tomcat 10.1 (Java 11+; application snippets use Java 17+), the H2 JDBC driver JAR on a classpath visible to Tomcat's resource factory, and a web application deployed to Tomcat. In production, replace H2 with a real DBMS and store credentials in the environment's secret management mechanism.

### 4.1. Declaring `<Resource>` in the Application's Context

One way to configure Tomcat per application is placing a `META-INF/context.xml` file in the WAR (depending on server deployment policy) or configuring the corresponding Context on the container side. Example:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<Context>
    <Resource
        name="jdbc/LearningDB"
        auth="Container"
        type="javax.sql.DataSource"
        driverClassName="org.h2.Driver"
        url="jdbc:h2:mem:learning;DB_CLOSE_DELAY=-1"
        username="sa"
        password=""
        maxTotal="10"
        maxIdle="5"
        maxWaitMillis="10000"
        testOnBorrow="true"
        validationQuery="SELECT 1" />
</Context>
~~~

Meaning of each attribute:

| Attribute | Role |
| --- | --- |
| `name` | Relative resource name in ENC: `jdbc/LearningDB` |
| `auth="Container"` | Container provides resource authentication per configuration |
| `type="javax.sql.DataSource"` | Interface expected by the application upon lookup |
| `driverClassName` | JDBC driver class name; H2 must be on the appropriate classpath |
| `url` | Actual JDBC URL; here in-memory H2 for the lab exercise |
| `username` / `password` | Connection credentials; sample `sa` and empty password are for lab use only |
| `maxTotal` | Limit on total concurrent connections allocated by the pool, per pool implementation |
| `maxIdle` | Maximum idle connections retained by the pool |
| `maxWaitMillis` | Maximum wait time when borrowing a connection, in milliseconds in this pool configuration |
| `testOnBorrow` / `validationQuery` | Validates a connection before handing it to the caller, with example query `SELECT 1` |

The pool attributes in the table belong to Tomcat/DBCP's matching default resource factory in the example configuration, **not the standard `DataSource` API**. Another JNDI provider or server may use different attribute names.

**JDBC driver placement:** For a resource created by Tomcat, place the JDBC driver JAR where Tomcat's classloader can see it, typically `$CATALINA_BASE/lib` or `$CATALINA_HOME/lib`. Merely declaring the dependency in the WAR may not suffice for a container-created resource factory. If the driver is absent or the URL is wrong, connection errors can happen immediately when the pool is created or only when borrowing a connection.

**H2 nature:** `jdbc:h2:mem:learning;DB_CLOSE_DELAY=-1` is an in-memory database for the example, not durable storage. `DB_CLOSE_DELAY=-1` keeps the database alive when the last connection closes within the same JVM; when the JVM stops, data disappears.

### 4.2. Declaring the Contract in `web.xml`

You can declare resource requirements in the WAR's `WEB-INF/web.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<web-app xmlns="https://jakarta.ee/xml/ns/jakartaee"
         version="6.0">
    <resource-ref>
        <description>DataSource provided by container</description>
        <res-ref-name>jdbc/LearningDB</res-ref-name>
        <res-type>javax.sql.DataSource</res-type>
        <res-auth>Container</res-auth>
    </resource-ref>
</web-app>
~~~

In Tomcat, if the resource is already validly defined in `<Context>`, adding `resource-ref` is usually not mandatory to perform lookup, but is useful for **declaring the application's dependency**. Another container may require deployment descriptor configuration or a different binding mechanism. The name in `res-ref-name` and the name published in ENC must match.

Do not confuse `<Resource>` in Context (container configuration that fulfills it) with `<resource-ref>` in `web.xml` (application requirement). Simply declaring the contract does not guarantee a working pool if the container has not supplied the matching resource.

### 4.3. Global Resources and ResourceLink

Tomcat also supports `<GlobalNamingResources>` in `server.xml` to declare server-wide resources. A web application does not automatically see every global resource; a `<ResourceLink>` in the application's Context may be required.

~~~xml
<Context>
    <ResourceLink
        name="jdbc/LearningDB"
        global="sharedLearningDataSource"
        type="javax.sql.DataSource" />
</Context>
~~~

This snippet **only illustrates linking** to a global resource already defined by an administrator named `sharedLearningDataSource`; it does not create a new global resource. The application still looks up under the local name `java:comp/env/jdbc/LearningDB`. Sharing one pool across multiple applications requires considering isolation, credentials, quotas, and each application's impact on the pool.

## 5. Testing Lookup with Java SE/JDBC Before Spring Integration

The goal of this step is to independently confirm three things: (1) the JNDI name exists, (2) the object is actually a `DataSource`, and (3) a connection can be borrowed to execute SQL.

Save the following as `JndiProbe.java`:

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import javax.naming.InitialContext;
import javax.naming.NamingException;
import javax.sql.DataSource;

public final class JndiProbe {
    public static void main(String[] args)
            throws NamingException, SQLException {
        InitialContext context = new InitialContext();
        DataSource dataSource = (DataSource)
                context.lookup("java:comp/env/jdbc/LearningDB");

        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement =
                     connection.prepareStatement("SELECT 1");
             ResultSet results = statement.executeQuery()) {
            if (!results.next()) {
                throw new IllegalStateException("Query returned no rows");
            }
            System.out.println("DB ready: " + results.getInt(1));
        }
    }
}
~~~

The syntax uses APIs built into the JDK; you can **compile-check** with Java 17 or newer without Spring libraries:

~~~bash
javac --release 17 JndiProbe.java
~~~

When `main` is invoked in a **JVM with a valid naming provider and JNDI binding**, with H2 and the configured resource, expected output:

~~~text
DB ready: 1
~~~

The runtime condition is mandatory: running `java JndiProbe` from an ordinary terminal **does not inherit the ENC of an application running inside Tomcat**, so it may fail before acquiring a connection. Therefore, proper integration testing must invoke the lookup code inside a runtime/container with a JNDI context—for instance, via an endpoint/servlet or an in-container test. The output above is only the result **when the environment is configured properly**, not guaranteed stdout of a standalone CLI program.

`try-with-resources` closes `ResultSet`, `PreparedStatement`, and `Connection`, even when an exception occurs. With a pooled `DataSource`, `Connection.close()` usually returns the logical connection to the pool rather than necessarily closing the physical socket. **Do not hold a `Connection` long-term in a singleton bean or share one Connection across requests.**

### Identifying Errors by Layer

- `new InitialContext().lookup(...)` fails → check naming provider, namespace, resource name, descriptors, and JNDI registration timing.
- Lookup succeeds but object type is wrong → check `type`, resource factory, and classloader/interfaces.
- `dataSource.getConnection()` fails → check JDBC driver, database, credentials, network, TLS, timeouts, or exhausted pool.
- Connection succeeds but SQL fails → check SQL syntax, schema, user privileges, and dialect compatibility.

Do not bypass errors by creating a temporary `DriverManagerDataSource` in production: doing so can mask JNDI configuration issues and unintentionally alter connection/transaction management.

## 6. Integrating into Spring Framework with JndiDataSourceLookup

In Spring, business code should receive the `DataSource` bean via constructor injection rather than calling JNDI directly in every repository. Spring provides `org.springframework.jdbc.datasource.lookup.JndiDataSourceLookup` to obtain a `DataSource` from JNDI with type checking.

### 6.1. Java-Based Configuration (Spring Framework 6+)

Example `DataAccessConfig.java` class in the application context of a web app deployed to a container:

~~~java
import javax.sql.DataSource;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.lookup.JndiDataSourceLookup;

@Configuration
public class DataAccessConfig {

    @Bean
    public DataSource dataSource() {
        JndiDataSourceLookup lookup = new JndiDataSourceLookup();
        return lookup.getDataSource("jdbc/LearningDB");
    }

    @Bean
    public JdbcTemplate jdbcTemplate(DataSource dataSource) {
        return new JdbcTemplate(dataSource);
    }
}
~~~

Appropriate Spring modules such as `spring-context`, `spring-jdbc`, and web application dependencies are required. This configuration class **is not an executable Java CLI**: it requires a Spring application context inside a container that already has the JNDI resource.

Why is the short name `jdbc/LearningDB` valid? The constructor of `JndiDataSourceLookup` enables `resourceRef=true`. For relative names without a scheme, Spring prepends `java:comp/env/` to look up `java:comp/env/jdbc/LearningDB`. Alternatively, you can supply the **full name**:

~~~java
return lookup.getDataSource("java:comp/env/jdbc/LearningDB");
~~~

Do not assume every Spring JNDI class behaves identically: the base `JndiLocatorSupport` defaults `resourceRef=false`; `JndiDataSourceLookup` specifically chooses a default suited to DataSources in ENC. Names with their own scheme do not get the prefix applied the way relative names do.

When Spring creates the `dataSource` bean, it looks up the resource. If the name does not exist, `getDataSource(...)` can throw `DataSourceLookupFailureException` (wrapping `NamingException`), causing application context startup failure. This is an appropriate signal when a required infrastructure dependency is absent. The approach above performs the lookup only during bean initialization, not on every SQL statement.

### 6.2. Repository Knows Only JdbcTemplate

Example `DatabaseCheckRepository.java` in an application with appropriate component scanning:

~~~java
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class DatabaseCheckRepository {
    private final JdbcTemplate jdbcTemplate;

    public DatabaseCheckRepository(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    public int probe() {
        Integer value =
                jdbcTemplate.queryForObject("SELECT 1", Integer.class);
        if (value == null) {
            throw new IllegalStateException("Database returned NULL");
        }
        return value;
    }
}
~~~

With H2 in the example, `probe()` returns `1`. `JdbcTemplate` borrows connections via Spring JDBC, creates and closes JDBC resources; the repository does not need to know the URL or lookup mechanism. When running with Spring-managed transactions, `JdbcTemplate` uses the `DataSourceUtils` mechanism to join the connection bound to the transaction in the right context.

The example shows *wiring*, not a guarantee that the application runs from just two classes. It requires WAR/container deployment, Spring context, dependencies, pool, and database configured as in earlier sections.

## 7. Another Way to Declare the Bean: JndiObjectFactoryBean

Spring also provides `org.springframework.jndi.JndiObjectFactoryBean`: a `FactoryBean` that looks up a JNDI object and exposes it as a Spring bean. It can be used when integrating a JNDI resource via XML or lookup configuration with many options.

~~~java
import javax.sql.DataSource;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jndi.JndiObjectFactoryBean;

@Configuration
public class AlternativeJndiConfig {
    @Bean
    public JndiObjectFactoryBean dataSource() {
        JndiObjectFactoryBean factory = new JndiObjectFactoryBean();
        factory.setJndiName("java:comp/env/jdbc/LearningDB");
        factory.setExpectedType(DataSource.class);
        return factory;
    }
}
~~~

This is an **alternative** to the `dataSource()` bean in Section 6; do not declare both beans with the same name in the same application context. When components inject `DataSource`, Spring resolves the object provided by the `FactoryBean`, without requiring repositories to depend directly on `JndiObjectFactoryBean`.

Advanced options of `JndiObjectFactoryBean`:

| Property | Meaning |
| --- | --- |
| `jndiName` | JNDI name to look up |
| `expectedType` | Expected object type, e.g. `DataSource.class` |
| `resourceRef` | If enabled, relative names are directed to `java:comp/env/` |
| `lookupOnStartup` | Default `true`: performs lookup during bean initialization |
| `cache` | Default `true`: caches the lookup result |
| `proxyInterface` | Proxy interface needed for matching lazy lookup/hot redeploy setups |

If you need to defer lookup:

~~~java
factory.setJndiName("jdbc/LearningDB");
factory.setResourceRef(true);
factory.setExpectedType(DataSource.class);
factory.setLookupOnStartup(false);
factory.setProxyInterface(DataSource.class);
~~~

This is a **behavior change**: the application can create the proxy bean before the JNDI resource is ready; errors will appear at actual usage time if the binding is still missing. Do not enable lazy lookup to "hide" configuration errors; use it only when there is an explicit late-resource-deployment need. `cache=false` can cause lookup to occur repeatedly per proxy invocation, which does not mean automatic load balancing or pool management.

## 8. When Using Spring Boot Deployed to an Application Server

Spring Boot offers a property option to configure a JNDI DataSource, instead of declaring `@Bean DataSource` manually:

~~~yaml
spring:
  datasource:
    jndi-name: "java:comp/env/jdbc/LearningDB"
~~~

In a Boot environment with appropriate JDBC auto-configuration, `spring.datasource.jndi-name` specifies where to obtain `DataSource`. When choosing JNDI, direct DataSource-creation properties such as `spring.datasource.url`, `username`, and `password` are no longer the DataSource source via this auto-configuration path.

A crucial condition: **the property does not create the JNDI resource**. If the server does not bind that name, the application still cannot connect. An executable JAR using an embedded servlet container **does not automatically have ENC/pool configuration like a WAR on external Tomcat**; a dedicated JNDI registration mechanism must exist if you truly want to use JNDI.

Manual bean configuration in Section 6 and Boot property configuration in this section are **two alternatives**. Once you define a custom `DataSource` bean, you must understand how auto-configuration backs off/adjusts; avoid adding both unintentionally, as it can make dependency injection and pool/transaction management hard to determine.

This lesson does not require Spring Boot: the essence of JNDI lookup lies in the Java naming API, the DataSource interface, the container, and Spring's wiring mechanism.

## 9. Who Owns the Pool, Lifecycle, and Configuration?

In the container-managed model here, **the container creates/closes the pool** along the application or server lifecycle, depending on how the resource is scoped. Spring may hold only a reference to `DataSource` for usage; the Spring application context closing **does not mean** Spring owns the pool to call `close()` itself.

Distinguish three operations:

1. **Lookup**: retrieving the DataSource object from JNDI. Usually done once during bean initialization.
2. **Borrow connection**: calling `dataSource.getConnection()` when JDBC work is needed; may wait if the pool is exhausted.
3. **Release connection**: closing the logical connection properly after the operation/transaction so the pool can reuse it.

Even when the `DataSource` object is a singleton, **do not** infer there is only a single `Connection`. A singleton `DataSource` can simultaneously lend different connections to many threads. A single connection must not be shared arbitrarily across requests/threads.

### Environment-Specific Configuration and Secret Management

Example environments sharing the same local name:

| Environment | JNDI Name Used by Application | Actual Configuration at Container |
| --- | --- | --- |
| Development | `jdbc/LearningDB` | H2 or test database |
| Staging | `jdbc/LearningDB` | Staging database, restricted access privileges |
| Production | `jdbc/LearningDB` | Production database, TLS/pool/monitoring per policy |

The application **does not need to change business code** when environments publish resources with consistent names and contracts. However, schemas, dialects, and transaction semantics still need compatibility; merely sharing a JNDI name does not guarantee identical database behavior.

Production credentials should not be committed into `context.xml` inside source code. Depending on the platform, use a secrets/credential store, external container configuration outside the artifact, and appropriate access permissions. Minimize database user privileges per function; avoid logging passwords or sensitive connection details. A JNDI binding is not a complete database access control mechanism.

## 10. JNDI DataSource and Transactions: Do Not Conflate Two Kinds of "Managed"

"Managed environment" easily causes confusion because **container-managed DataSource** (container supplies the pool) and **container-managed transaction/JTA** (container coordinates transactions) are two separate decisions.

### Case A — Container Supplies Pool, Spring Manages Local JDBC Transactions

If the application uses a non-JTA DataSource from the container and wants Spring to manage JDBC transactions, you can configure Spring's transaction manager for that DataSource, such as `JdbcTransactionManager` or `DataSourceTransactionManager`:

~~~java
import javax.sql.DataSource;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.support.JdbcTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration
public class LocalJdbcTransactionConfig {
    @Bean
    public PlatformTransactionManager transactionManager(
            DataSource dataSource) {
        return new JdbcTransactionManager(dataSource);
    }
}
~~~

This is supplementary wiring for the DataSource in Section 6, used when the architecture chooses **local JDBC transactions**. Services can use `@Transactional` when transaction management is enabled/configured properly. Spring JDBC acquires connections consistently via `DataSourceUtils`; running SQL with `JdbcTemplate` ensures participation in the active transaction. With hand-written JDBC code, take care to use `DataSourceUtils` or Spring's equivalent mechanism to avoid accidentally grabbing another connection outside the transaction.

### Case B — Container/JTA Manages Distributed Transactions

If resources belong to application-server-managed transactions, or one transaction must coordinate multiple XA resources, `JtaTransactionManager` paired with the environment's JTA configuration may be required:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.jta.JtaTransactionManager;

@Configuration
public class ManagedTransactionConfig {
    @Bean
    public PlatformTransactionManager transactionManager() {
        return new JtaTransactionManager();
    }
}
~~~

This is an illustrative configuration pattern, **insufficient on its own to provide a JTA coordinator**. The application server must support and configure JTA appropriately; not every default Tomcat installation provides a full JTA transaction coordinator. In a concrete system, vendor/server-specific transaction manager configuration may be needed.

**Rule:** If Spring manages local JDBC transactions with a non-JTA manager, use a DataSource that the container does not automatically enroll in conflicting JTA transactions on the same connection. If the container manages JTA, choose a JTA-integrated transaction manager and matching resources. **Having a JNDI name does not by itself dictate which transaction manager to use.**

## 11. Layered Testing, from Container to Repository

A sensible verification sequence:

1. **Verify deployment:** Web application runs in the expected Tomcat/application server; the Context file is actually loaded per the server's deploy policy.
2. **Verify name:** Namespace has `jdbc/LearningDB` registered, distinguishing relative vs. full names.
3. **Verify type:** Lookup returns an object compatible with `javax.sql.DataSource`. With Spring, the `DataSource` bean resolves at context startup.
4. **Verify connection:** Run a simple `SELECT 1` query inside the container environment. Example result with H2 is `1`.
5. **Verify JDBC/Spring:** Call `DatabaseCheckRepository.probe()` and verify it returns `1` in an actual deployment test.
6. **Verify pool:** Observe active/idle connections, wait times, timeouts, and behavior under concurrent requests; return connections via proper closing mechanisms.
7. **Verify transactions:** Test rollback on failure across multiple write operations; especially when using `@Transactional` and container/JTA.

If a naming provider is absent in unit tests running outside the container, you can **inject a dedicated test DataSource** (such as H2 created by test configuration) into the repository to test SQL logic. That is a Spring JDBC unit/integration test, not a JNDI test. To prove the JNDI binding works, you need a real JNDI environment or an intentionally configured test naming provider.

When testing real JNDI code, use the proper runtime classpath and lifecycle. Do not assume Spring creates JNDI resources for the application merely because `spring-jdbc` is in the project.

## 12. Common Troubleshooting Table

| Symptom | Causes to Check | Approach |
| --- | --- | --- |
| `NoInitialContextException` | Running outside an environment with a provider; naming config does not exist yet | Confirm app runs inside a valid container/naming provider |
| `NameNotFoundException` | Wrong name, wrong namespace, Context missing `<Resource>` or `<ResourceLink>` | Compare local name `jdbc/LearningDB` with full name `java:comp/env/jdbc/LearningDB` |
| `DataSourceLookupFailureException` on Spring startup | JNDI lookup failed | Read root cause `NamingException`, check initialization order and container configuration |
| `ClassCastException` or type mismatch | Resource is not a `DataSource` or wrong classloader/type | Check `type="javax.sql.DataSource"`, factory, and jar/classloader |
| `ClassNotFoundException: org.h2.Driver` | JDBC driver unavailable to pool factory | Place driver on Tomcat's appropriate classpath, verify version |
| `SQLException` on `getConnection()` | URL, credentials, privileges, network, TLS, pool exhausted, or DB stopped | Check actual JDBC URL, pool/driver logs, timeouts, and access privileges |
| Lookup succeeds yet slow under heavy load | Pool lacks connections, connections held too long, slow queries | Observe active/idle/wait time and queries, close resources promptly |
| `@Transactional` fails to roll back as expected | Wrong transaction manager, connection not participating in transaction | Verify local vs. JTA transaction, `DataSourceUtils`, and proxy boundaries |
| Works in WAR, fails in executable JAR | Different naming provider and container configuration | Choose DataSource configuration matching each packaging/runtime |
| DB drops connections after idle time | Old connection/network or server timeout, unsuitable pool validation | Adjust validation/eviction/lifetime per pool and DB characteristics |

Always start from the **root cause** and actual failure layer. Do not diagnose every JNDI failure as a database error: in many cases lookup has not even returned a `DataSource`, so the JDBC driver and SQL statements were never invoked.

## 13. Mistakes to Avoid

**Mistake 1 — Confusing a JNDI name with a JDBC URL.**

~~~text
JNDI: java:comp/env/jdbc/LearningDB
JDBC: jdbc:h2:mem:learning;DB_CLOSE_DELAY=-1
~~~

JNDI selects a resource by name; the JDBC URL is used by the driver to connect to the database. Both strings include `jdbc`, yet serve two different layers.

**Mistake 2 — Creating a second pool after looking up a DataSource.** If the container already created a pooled DataSource, wrapping it in another independent pool can cause double pooling and make connection and timeout control difficult. Only add proxies/wrappers when you clearly understand their purpose, such as transaction-aware or lazy connection—do not assume JNDI lookup returns a raw single connection.

**Mistake 3 — Passing a short name to an API that does not add the ENC prefix automatically.** `new InitialContext().lookup("jdbc/LearningDB")` is not the same as `JndiDataSourceLookup.getDataSource("jdbc/LearningDB")`. With direct `InitialContext`, look up the full name or obtain the ENC context first. With `JndiDataSourceLookup`, the constructor enables `resourceRef`, so relative names are converted into ENC names.

**Mistake 4 — Forgetting to close Connection.** When JDBC resources are not released, the pool can gradually run dry. Use `try-with-resources` or `JdbcTemplate`; do not store connections in a field of a singleton/repository.

**Mistake 5 — Assuming JNDI automatically creates transactions and pooling.** Lookup only retrieves an object; pool behavior, local/JTA transactions, retries, and recovery come from the relevant implementation and configuration.

**Mistake 6 — Assuming every server behaves like Tomcat.** XML configuration, classloaders, namespaces, driver placement, pool attributes, and JTA differ across Tomcat, WildFly/JBoss, WebLogic, and other environments. The Java `DataSource` interface stays the same, while operations must follow the actual server's documentation.

**Mistake 7 — Mixing two DataSource strategies.** Simultaneously using Boot JNDI auto-config, custom beans, an app-managed Hikari pool, and a container pool without knowing which bean is actually injected invites hard-to-find bugs. Choose a clear configuration matching the deployment model.

**Mistake 8 — Failing to separate business testing from JNDI testing.** A repository unit test can use an independent test DataSource; only an integration test inside the naming environment confirms the JNDI resource. The two test types answer different questions.

## 14. Applied Exercises

1. **Explain the path:** With `<Resource name="jdbc/LearningDB">` declared in Tomcat, write the full name for `InitialContext.lookup(...)` and the short name for `JndiDataSourceLookup.getDataSource(...)`.  
   **Answer:** `java:comp/env/jdbc/LearningDB` and `jdbc/LearningDB`.

2. **Choose where to configure:** If staging DB switches to PostgreSQL while keeping the name `jdbc/LearningDB`, which layer should be updated first?  
   **Answer:** Container/resource configuration (driver, URL, credentials, pool) and compatible schema/migrations. The repository depends only on `DataSource`, so it needs no changes for the JNDI binding update.

3. **Error analysis:** `JndiDataSourceLookup` throws `DataSourceLookupFailureException` at startup. Should you immediately edit the JDBC URL in the repository?  
   **Answer:** No. First inspect the root cause of the lookup, container, and JNDI name. When lookup has not returned a DataSource, repository code may not have executed yet.

4. **Connection lifecycle:** Why is `try (Connection conn = ds.getConnection())` still necessary if connections are managed by a pool?  
   **Answer:** `close()` releases the logical connection back to the pool so other requests can borrow it; omitting close exhausts the pool.

5. **Transactions:** Does a DataSource appearing in JNDI prove the server is managing every transaction with JTA?  
   **Answer:** No. You must verify the resource type and transaction architecture. Local Spring JDBC transactions and JTA have separate transaction managers/configurations.

6. **Testing:** A unit test for `DatabaseCheckRepository` injects an H2 DataSource and returns `1`. What does this test prove, and what does it not yet prove?  
   **Answer:** It proves the repository/JdbcTemplate can query the H2 test DB; it does not yet prove the JNDI resource exists in the deployment environment's container.

## 15. Key Takeaways

- **JNDI is a name-based lookup mechanism**; the resource returned in this lesson is a container-managed `javax.sql.DataSource` object.
- **JNDI names and JDBC URLs are different**; the application uses a logical name, while the container holds connection/pool details.
- With Tomcat, `jdbc/LearningDB` in Context appears at `java:comp/env/jdbc/LearningDB`; naming rules must be verified against the actual server.
- `JndiDataSourceLookup` or `JndiObjectFactoryBean` creates a Spring bean from a JNDI resource; repositories continue using `JdbcTemplate` via dependency injection.
- Pool lifecycle, connection return, and transaction manager type must be defined explicitly. **A JNDI DataSource does not automatically imply JTA.**
- Unit tests for repositories and integration tests for JNDI are two distinct verification layers.

### Official References

- [Spring Framework — Controlling Database Connections](https://docs.spring.io/spring-framework/reference/data-access/jdbc/connections.html): how Spring uses DataSource, JdbcTemplate, DataSourceUtils, and transaction-aware access.
- [Spring Framework — JndiDataSourceLookup API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/datasource/lookup/JndiDataSourceLookup.html): looking up DataSource via JNDI.
- [Spring Framework — JndiObjectFactoryBean API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jndi/JndiObjectFactoryBean.html): startup lookup, caching, and proxying.
- [Apache Tomcat 10.1 — JNDI Resources How-To](https://tomcat.apache.org/tomcat-10.1-doc/jndi-resources-howto.html): declaring Context, resource-ref, and using DataSource.
- [Spring Boot — SQL Databases](https://docs.spring.io/spring-boot/reference/data/sql.html): configuring `spring.datasource.jndi-name` when running on an application server.
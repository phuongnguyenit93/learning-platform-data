# Identifying Input Properties, Output Beans, and Public Extension Points When Reading Auto-Configuration Code

## 1. Goal: Turning an Auto-Configuration Class into a Verifiable Map

A Spring Boot auto-configuration class is often only the starting point. The properties it accepts may be bound into a `@ConfigurationProperties` class; the beans visible to the application may be created in nested or `@Import`ed `@Configuration` classes; and behavior may be tuned through properties, a user-provided bean, or a public callback interface.

When reading the source code, you need to answer four questions:

1. **Input:** what configuration enters the auto-configuration? What is the property prefix, what does each key mean, and which conditions read directly from `Environment`?
2. **Conditions:** when do the class and each branch/bean method apply? Which classpath entries, properties, existing beans, resources, or environment states are checked?
3. **Output:** which beans are registered? What are their names, return types, scopes, dependencies, and definition sources?
4. **Extension points:** can the application customize behavior via properties, custom beans, `Customizer`, `Configurer`, `ConnectionDetails`, or another public interface?

This map helps answer practical questions: which property to change to select a different pool, why a default bean did not appear, how to replace one dependency while keeping the rest of the auto-configuration, and which APIs are designed for application extension.

This article uses **Spring Boot 3.5.x, Spring Framework 6.2, and Java 17+** as its baseline. When reading another project, use the source/Javadoc matching the dependency version in that project; do not infer packages, properties, or callbacks from the latest `main` branch.

## 2. Overall Model: From Candidate to Bean in Context

You can picture the process as follows:

~~~text
META-INF/spring/...AutoConfiguration.imports
                   |
                   v
       Auto-configuration candidate list
                   |
                   v
    Class-level annotations (@Conditional...)
                   |
                   v
  @EnableConfigurationProperties / @Import
                   |
                   v
   Nested configuration branches / bean methods
                   |
                   v
    Conditions of each branch and each bean
                   |
                   v
  Bean definitions registered into the context
                   |
                   v
       Instances created when Spring needs them
~~~

Each layer must be read in its proper role:

- **Imports file:** tells you which classes are published as auto-configuration candidates.
- **Class annotations:** conditions governing the entire configuration, before/after ordering, enabled property types, and imported configurations.
- **Nested configurations:** split branches by implementation type or environment.
- **Bean methods:** define output beans, types, names, parameter dependencies, and individual conditions.
- **Configuration properties:** describe structured inputs, data types, and defaults.
- **Customizer/configurer/connection details:** extension points for the application to intervene in bean creation.

Distinguish **bean definition** from **bean instance**. Auto-configuration first decides which bean definitions are registered. Singleton instances are normally created during context initialization, whereas lazy or prototype beans have different creation timing. Therefore, reading a `@Bean` method does not mean every startup produces a corresponding instance; you must consider all conditions and the lifecycle.

## 3. Preparing the Right Source Before Reading

### 3.1. Identify the Actual Running Version

First, identify the Spring Boot version managed by Maven/Gradle:

~~~xml
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.16</version>
    <relativePath/>
</parent>
~~~

Or inspect the dependency tree:

~~~bash
mvn dependency:tree -Dincludes=org.springframework.boot
~~~

With Gradle:

~~~bash
./gradlew dependencyInsight --dependency spring-boot-autoconfigure --configuration runtimeClasspath
~~~

Do not look only at the version written in one starter: dependency management, BOMs, or version overrides can make Boot modules non-uniform compared to expectations. Determine the actual versions of `spring-boot`, `spring-boot-autoconfigure`, and related modules.

### 3.2. Open the Sources JAR or Source in the IDE

The best way to read is using the **exact-version sources JAR**. With Maven:

~~~bash
mvn dependency:sources
~~~

Then the IDE can open the declaration/source of classes from the dependency. If you need to inspect the JAR:

~~~bash
jar tf ~/.m2/repository/org/springframework/boot/spring-boot-autoconfigure/3.5.16/spring-boot-autoconfigure-3.5.16.jar
~~~

On Windows PowerShell, the Maven local repository path typically resides under the user profile directory; substitute the path matching your machine.

In the IDE:
1. Ctrl/Cmd-click the auto-configuration name.
2. Open the class and any `@Import`ed classes.
3. Open the `@ConfigurationProperties` type.
4. Follow factory methods and customizer interfaces.
5. Use Find Usages to pinpoint where the framework actually invokes the extension point.

If the sources JAR is unavailable, you can use Javadoc or GitHub source at the **matching tag**. Do not use a class from Spring Boot 4.x to draw conclusions about packages or behavior in Spring Boot 3.5.x.

### 3.3. Locate the Auto-Configuration Declaration File

Spring Boot 3.x uses an imports file:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

The file contains a list of fully qualified class names, one candidate per line. When developing your own starter, this is where you declare the library's auto-configurations.

Do not confuse this file with:
- `META-INF/spring.factories`: still used for several other factory/extension types, but no longer the standard way to register auto-configuration candidates in Boot 3.x.
- `META-INF/spring-configuration-metadata.json`: metadata describing properties and supporting IDE tooling.
- `spring-autoconfigure-metadata.properties`: metadata optimizing candidate filtering; not a list of public properties for user configuration.

## 4. Ordered Source-Reading Workflow

### Step 1 — Read Annotations on the Main Class

Look for the following annotations:

| Annotation | What to Note |
| --- | --- |
| `@AutoConfiguration` | Is this an auto-configuration? Are there `before`, `after`, or class-name ordering attributes? |
| `@ConditionalOnClass` | Which libraries/classes must be on the classpath? |
| `@ConditionalOnMissingBean` | Which user-provided beans will make this configuration back off? |
| `@ConditionalOnBean` | Which beans from other configurations are required? |
| `@ConditionalOnProperty` | Which property enables/disables the class or branch? What are `havingValue` and `matchIfMissing`? |
| `@ConditionalOnWebApplication` / `@ConditionalOnNotWebApplication` | Which web/non-web scope is supported? |
| `@EnableConfigurationProperties` | Which properties classes are registered and bound? |
| `@Import` | Which additional configurations need to be read next? |
| `@ImportAutoConfiguration` | Are other auto-configurations explicitly imported? |

**Do not stop at class-level conditions.** A class may match while a bean method inside it does not match. Each nested configuration branch can also have its own conditions.

### Step 2 — Follow Imported Classes

Example:

~~~java
@AutoConfiguration
@EnableConfigurationProperties(ClientProperties.class)
@Import(ClientTransportConfiguration.class)
class ClientAutoConfiguration {
}
~~~

The three lines on that class are not enough to identify output beans. You must open `ClientTransportConfiguration`, nested configurations, and imported methods.

A configuration class may only gather conditions and imports; the actual beans are declared in other classes. Therefore, do not search for `@Bean` only in files named `*AutoConfiguration.java`.

### Step 3 — Find All Property Prefixes and Property Read Sites

Look for:

- `@ConfigurationProperties("...")`;
- `@EnableConfigurationProperties(...)`;
- `@ConfigurationPropertiesScan`;
- `@ConfigurationProperties` on `@Bean` methods;
- `@ConditionalOnProperty`;
- `Environment.getProperty(...)`;
- `Binder.get(environment)`;
- `@Value` placeholders.

**A property can be read through multiple mechanisms.** For example, `spring.datasource.type` is both bound into `DataSourceProperties` and may be read in a condition to decide whether to select the pooled DataSource branch.

Separate into three groups:

1. **Bound properties:** become fields in a configuration object.
2. **Conditional properties:** used to decide whether a configuration/bean matches.
3. **Directly read properties:** accessed via `Environment`, `Binder`, or placeholders at a specific site.

A single key can belong to multiple groups. Do not assume every field in `@ConfigurationProperties` is used in conditions.

### Step 4 — Inventory Output Beans

Find all:
- `@Bean`;
- `@Import` leading to classes with `@Bean`;
- `ImportSelector` or registrars if the auto-configuration uses dynamic registration;
- factories/registrars creating bean definitions.

For each bean, record:

| Attribute to Read | How to Find |
| --- | --- |
| Bean name | `@Bean` method name, or explicit `@Bean("...")` value |
| Return type | Method return type |
| Actual implementation | Instantiated class or invoked builder |
| Conditions | Annotations on class, nested class, and method |
| Dependencies | Method parameters, constructors, and `@DependsOn` |
| Scope/lazy | `@Scope`, `@Lazy`, `@Primary`, and related metadata |
| Back-off | `@ConditionalOnMissingBean` or alternative condition |
| Source | Class and method that actually define the bean |

**Return type matters.** Spring Boot conditions often rely on type information available when registering bean definitions. A method returning `Object` even though it actually creates a `DataSource` can make type matching less accurate than a method declaring the exact type.

### Step 5 — Identify Public Extension Points

Look for interfaces/classes with names or roles such as:
- `Customizer`;
- `Configurer`;
- `Builder`;
- `ConnectionDetails`;
- `Provider`;
- `Strategy`;
- `Factory`.

Then verify:
1. Is the interface `public`?
2. Does Javadoc describe it as a callback or extension point for applications?
3. Does the framework collect it via `ObjectProvider`, `orderedStream()`, `List<...>`, or another mechanism?
4. Where and when is the callback applied?
5. Does it modify only one bean, or affect all builders/beans created through a factory?
6. Is there an ordering contract such as `@Order`/`Ordered`?

**A name alone is not enough to conclude it is a public API.** A package-private class named `Customizer` or an internal nested condition is not an extension point supported for applications. Record an extension point only when there is a public contract and an actual call site in the source.

## 5. Real Example: Reading DataSourceAutoConfiguration in Spring Boot 3.5

A good example for practicing source reading is:

~~~java
org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration
~~~

Boot 3.5 Javadoc describes this class as auto-configuration for `javax.sql.DataSource`. The annotations on the main class mean:

~~~java
@AutoConfiguration(before = SqlInitializationAutoConfiguration.class)
@ConditionalOnClass({
    DataSource.class,
    EmbeddedDatabaseType.class
})
@ConditionalOnMissingBean(type = "io.r2dbc.spi.ConnectionFactory")
@EnableConfigurationProperties(DataSourceProperties.class)
@Import({
    DataSourcePoolMetadataProvidersConfiguration.class,
    DataSourceCheckpointRestoreConfiguration.class
})
public class DataSourceAutoConfiguration {
    // Nested configurations are declared below.
}
~~~

This is an illustrative excerpt of the class-level annotations in Boot 3.5; imports and some secondary content are omitted to focus on how to read it.

### 5.1. Inputs from Class-Level Annotations

| Component | Meaning |
| --- | --- |
| `before = SqlInitializationAutoConfiguration.class` | Orders DataSource auto-configuration bean definitions before SQL initialization configuration per the ordering contract |
| `@ConditionalOnClass(DataSource.class, EmbeddedDatabaseType.class)` | Requires JDBC DataSource API and embedded database type on the classpath |
| `@ConditionalOnMissingBean(type = "io.r2dbc.spi.ConnectionFactory")` | If an R2DBC ConnectionFactory is already present, this JDBC DataSource auto-configuration is not applied |
| `@EnableConfigurationProperties(DataSourceProperties.class)` | Registers and binds standard configuration prefixed with `spring.datasource` |
| `@Import(...)` | Adds metadata provider configuration and checkpoint/restore support |

An easily missed detail: the class-level condition checks for an **R2DBC ConnectionFactory**. If a project has an R2DBC dependency and has registered a ConnectionFactory, not seeing JDBC DataSource auto-configured may be the result of this condition, not necessarily a URL property error.

Auto-configuration ordering controls the registration order of bean definitions; it does not mean the DataSource instance is guaranteed to be created before every other bean. Instance creation also depends on the dependency graph.

### 5.2. Input Properties: DataSourceProperties

Open the class:

~~~java
org.springframework.boot.autoconfigure.jdbc.DataSourceProperties
~~~

This class is bound to the prefix:

~~~java
@ConfigurationProperties("spring.datasource")
public class DataSourceProperties {
    // DataSource configuration fields.
}
~~~

Common standard keys:

| Property | Purpose |
| --- | --- |
| `spring.datasource.url` | JDBC URL |
| `spring.datasource.username` | Username |
| `spring.datasource.password` | Password |
| `spring.datasource.driver-class-name` | Driver class; often inferred from URL |
| `spring.datasource.type` | Specifies DataSource/pool implementation |
| `spring.datasource.name` | Database/DataSource name per properties contract |
| `spring.datasource.generate-unique-name` | Whether to generate a unique embedded database name |
| `spring.datasource.embedded-database-connection` | Embedded database type to use |
| `spring.datasource.jndi-name` | JNDI name of the DataSource; the JNDI branch is handled by a related auto-configuration |

Standard fields live in `DataSourceProperties`; **pool-specific properties** live under each implementation's own prefix, for example:

~~~properties
spring.datasource.hikari.maximum-pool-size=20
spring.datasource.hikari.connection-timeout=30000
~~~

If using Tomcat JDBC pool or DBCP2, the prefix and keys differ. Read the specific implementation configuration class, such as `DataSourceConfiguration.Hikari`, to know which property prefix is bound for the pool.

Note: `spring.datasource.jndi-name` relates to `DataSourceProperties`, yet creating a DataSource from JNDI is performed separately by `JndiDataSourceAutoConfiguration`. When you see a property in a properties class, you must still trace which class actually uses it.

### 5.3. Condition of the Embedded Database Branch

In the source of `DataSourceAutoConfiguration`, there is a nested class:

~~~java
@Configuration(proxyBeanMethods = false)
@Conditional(EmbeddedDatabaseCondition.class)
@ConditionalOnMissingBean({
    DataSource.class,
    XADataSource.class
})
@Import(EmbeddedDataSourceConfiguration.class)
protected static class EmbeddedDatabaseConfiguration {
}
~~~

The embedded database condition evaluates factors such as:
- whether `spring.datasource.url` has been set;
- whether a supported pooled DataSource is available;
- whether embedded database classes are on the classpath;
- whether a suitable embedded database driver is present.

If a URL is specified for an external database, the embedded branch no longer matches. If a pool is available, Boot prefers a pooled DataSource over an embedded database. If the user has already provided a `DataSource` or `XADataSource`, the default configuration branch backs off.

### 5.4. Condition of the Pooled DataSource Branch

Another nested class:

~~~java
@Configuration(proxyBeanMethods = false)
@Conditional(PooledDataSourceCondition.class)
@ConditionalOnMissingBean({
    DataSource.class,
    XADataSource.class
})
@Import({
    DataSourceConfiguration.Hikari.class,
    DataSourceConfiguration.Tomcat.class,
    DataSourceConfiguration.Dbcp2.class,
    DataSourceConfiguration.OracleUcp.class,
    DataSourceConfiguration.Generic.class,
    DataSourceJmxConfiguration.class
})
protected static class PooledDataSourceConfiguration {
}
~~~

The pooled branch can be selected when:
- `spring.datasource.type` is specified; or
- a supported connection pool is on the classpath.

Then the nested implementation configurations decide which pool is used. According to Boot 3.5 documentation, the usual preference order prioritizes **HikariCP**, followed by Tomcat pool, Commons DBCP2, and Oracle UCP when earlier choices are absent.

Do not read only `PooledDataSourceConfiguration` and conclude the pool is always Hikari. Open `DataSourceConfiguration.Hikari` and inspect `@ConditionalOnClass`, `@ConditionalOnMissingBean`, `@ConditionalOnProperty`, and the exact `@Bean` method.

### 5.5. Output Beans

When conditions match, the output typically includes:

| Bean / Bean Group | Source | Meaning |
| --- | --- | --- |
| `dataSource` | Nested configuration for embedded or pool implementation | The DataSource the application injects to work with the database |
| `DataSourceProperties` | `@EnableConfigurationProperties` | Bean holding configuration bound from `spring.datasource` |
| Default `JdbcConnectionDetails` in the pooled branch | Bean method creating property-backed details if no bean of the same type exists | Encapsulates URL, username, password, and connection details for the DataSource |
| Pool metadata providers | Imported classes | Supports reading pool metadata, such as status/connection info |
| Embedded database support | Embedded configuration imported when the branch matches | Creates an embedded database when classpath and conditions allow |

The exact list depends on the classpath and branch. A project with Hikari may receive `HikariDataSource`; a project with only an embedded database may receive an embedded implementation. Support beans do not necessarily appear in every case.

Key lesson: **the entry-point class does not necessarily declare the DataSource bean directly**. It enables properties, applies conditions, and imports nested configurations. To know the real implementation, follow through to the imported `@Bean` class.

## 6. Public Extension Points in the DataSource Example

### 6.1. Configuring via Standard Properties

This is the simplest extension point. Operators change `application.properties`, YAML, environment variables, or command-line arguments without modifying Java source.

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://localhost:5432/orders
    username: app_user
    password: change-me
    hikari:
      maximum-pool-size: 20
      connection-timeout: 30000
~~~

Boot binds the standard part into `DataSourceProperties` and the Hikari part into the corresponding pool configuration. When reading source, identify each class's property prefix instead of lumping every key into one object.

### 6.2. Providing the Application's Own DataSource

`@ConditionalOnMissingBean(DataSource.class)` is an important extension point. If the user registers a matching DataSource bean before auto-configuration processes that branch, Boot will not create the default DataSource in the corresponding branch.

Illustrative example:

~~~java
@Configuration(proxyBeanMethods = false)
class MyDatabaseConfiguration {

    @Bean
    DataSource applicationDataSource() {
        return DataSourceBuilder.create()
                .url("jdbc:postgresql://localhost:5432/orders")
                .username("app_user")
                .password("change-me")
                .build();
    }
}
~~~

The snippet requires the PostgreSQL driver dependency and a compatible pool/implementation on the classpath. In real applications, do not hard-code credentials; retrieve them from a secret store or external configuration.

**Backing off does not mean all DataSource-related auto-configurations disappear.** Other configurations such as JDBC template, transaction manager, or SQL initialization may still apply if conditions and dependencies match. Therefore, you must continue tracing downstream auto-configurations.

### 6.3. Providing JdbcConnectionDetails

In Spring Boot 3.5, `JdbcConnectionDetails` is a public interface describing the details needed to connect via JDBC. Auto-configuration can provide an implementation reading from `DataSourceProperties` if no matching bean exists yet.

When you need to supply connection details from a custom source, you can register a bean:

~~~java
@Configuration(proxyBeanMethods = false)
class CustomJdbcConnectionConfiguration {

    @Bean
    JdbcConnectionDetails customJdbcConnectionDetails() {
        return new JdbcConnectionDetails() {

            @Override
            public String getJdbcUrl() {
                return "jdbc:postgresql://localhost:5432/orders";
            }

            @Override
            public String getUsername() {
                return "app_user";
            }

            @Override
            public String getPassword() {
                return "change-me";
            }
        };
    }
}
~~~

This is an illustrative example of the extension interface; in real environments, obtain values from a secure configuration source. When auto-configuration finds an application-provided `JdbcConnectionDetails` bean, the default property-backed bean can back off. This fits service connections or custom connection providers.

Do not confuse `JdbcConnectionDetails` with `DataSource`: one describes connection details; the other is the abstraction used to obtain a JDBC Connection.

### 6.4. JNDI as a Related Configuration Branch

If the DataSource is managed by an application server, you can use:

~~~properties
spring.datasource.jndi-name=java:comp/env/jdbc/OrdersDS
~~~

When reading source, look next at `JndiDataSourceAutoConfiguration` and its conditions. Do not assume every branch inside `DataSourceAutoConfiguration` handles JNDI.

### 6.5. Not Every Internal Class Is an Extension Point

Nested conditions like `EmbeddedDatabaseCondition` or `PooledDataSourceCondition` are primarily implementation details. Do not make your application depend directly on internal package-private or protected classes if documentation does not guarantee support.

Prefer extension points that are:
- documented properties;
- bean types checked via `@ConditionalOnMissingBean`;
- public interfaces such as `JdbcConnectionDetails`;
- builders/customizers/configurers published as callbacks in Javadoc;
- APIs documented in the Reference Guide.

## 7. Following Output Beans Further: JdbcTemplateAutoConfiguration

To see why multi-class tracing is necessary, open next:

~~~java
org.springframework.boot.autoconfigure.jdbc.JdbcTemplateAutoConfiguration
~~~

In Boot 3.5, this class has the key annotations:

~~~java
@AutoConfiguration(after = DataSourceAutoConfiguration.class)
@ConditionalOnClass({
    DataSource.class,
    JdbcTemplate.class
})
@ConditionalOnSingleCandidate(DataSource.class)
@EnableConfigurationProperties(JdbcProperties.class)
@Import({
    DatabaseInitializationDependencyConfigurer.class,
    JdbcTemplateConfiguration.class,
    NamedParameterJdbcTemplateConfiguration.class
})
public class JdbcTemplateAutoConfiguration {
}
~~~

Key takeaways:
- This auto-configuration runs **after** DataSource auto-configuration.
- Both JDBC DataSource and JdbcTemplate APIs are required on the classpath.
- A single DataSource candidate is required for type-based injection; multiple DataSources without a clear primary can cause the condition not to match.
- Inputs for the template belong to `JdbcProperties`, prefix `spring.jdbc`, not all under `spring.datasource`.
- `JdbcTemplate` and `NamedParameterJdbcTemplate` beans are declared in the imported configurations.

Example properties for the template:

~~~properties
spring.jdbc.template.fetch-size=100
spring.jdbc.template.query-timeout=5s
spring.jdbc.template.max-rows=500
~~~

This reveals a linked chain:
1. `DataSourceAutoConfiguration` creates the DataSource.
2. `JdbcTemplateAutoConfiguration` requires a uniquely selectable DataSource.
3. `JdbcTemplateConfiguration` and `NamedParameterJdbcTemplateConfiguration` register the template beans.
4. Business beans inject `JdbcTemplate` to execute queries.

If you want to know which bean a property adjusts, trace backward from the bean method to the properties type. Do not assign every `spring.jdbc.*` key to `DataSourceProperties` just because both relate to JDBC.

## 8. Searching Quickly with an IDE or ripgrep

In the source repository or an extracted sources JAR, you can use:

~~~bash
rg -n "@ConfigurationProperties|@EnableConfigurationProperties" spring-boot-project/spring-boot-autoconfigure/src/main/java
~~~

Find conditions and beans:

~~~bash
rg -n "@ConditionalOnProperty|@ConditionalOnMissingBean|@ConditionalOnBean|@ConditionalOnClass|@Bean|@Import" path/to/autoconfigure/package
~~~

Find callbacks:

~~~bash
rg -n "Customizer|Configurer|Builder|ConnectionDetails|Provider|Strategy" path/to/autoconfigure/package
~~~

Find metadata:

~~~bash
rg --files | rg "AutoConfiguration.imports|spring-configuration-metadata.json|additional-spring-configuration-metadata.json"
~~~

When reading code in the IDE, use Find Usages to confirm:
- where the properties class is enabled;
- where customizers are collected and applied;
- which builder is exposed to the application;
- which bean backs off when a user bean appears.

Do not search by class name alone. A public customizer with no call site nearby may be an extension point for another subsystem; you must verify exactly who consumes it.

## 9. Configuration Properties Metadata

Spring Boot can generate:

~~~text
META-INF/spring-configuration-metadata.json
~~~

This file powers IDE autocomplete and describes properties, data types, default values, and deprecations when declared. You can inspect this metadata in the auto-configuration module or built JAR.

Metadata is useful for identifying:
- canonical property names;
- types (String, boolean, Duration, Class, enum, list...);
- descriptions;
- default values if present;
- deprecated/replacement properties;
- metadata source.

However, metadata does not replace source code:
- It does not fully show which conditions use a property.
- It does not prove a bean will be created in every environment.
- A property may be read directly via `Environment` or a custom condition without generated metadata.
- A default inside a properties object is not necessarily a property present in `Environment`.

Per Spring Boot recommendations, property keys should use **lowercase kebab-case**, such as `spring.datasource.driver-class-name`. Relaxed binding maps keys from files, YAML, system properties, and environment variables onto the appropriate Java fields.

## 10. Testing: Verifying Inputs, Outputs, and Back-Off

A good testing approach is `ApplicationContextRunner`: create a minimal context, supply specific properties, load the auto-configuration under test, and assert output beans.

The example below uses:
- Spring Boot **3.5.16**;
- Java 17+;
- `spring-boot-starter-jdbc`;
- H2 database in tests;
- `spring-boot-starter-test`.

### 10.1. Maven Dependencies

~~~xml
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.16</version>
    <relativePath/>
</parent>

<properties>
    <java.version>17</java.version>
</properties>

<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-jdbc</artifactId>
    </dependency>

    <dependency>
        <groupId>com.h2database</groupId>
        <artifactId>h2</artifactId>
        <scope>test</scope>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

If the project already has a parent/BOM managing versions, do not add a second parent; add only the missing dependencies.

### 10.2. Test Source

Create **`src/test/java/example/DataSourceAutoConfigurationReadingTests.java`**:

~~~java
package example;

import javax.sql.DataSource;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration;
import org.springframework.boot.autoconfigure.jdbc.DataSourceProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.datasource.DriverManagerDataSource;

import static org.assertj.core.api.Assertions.assertThat;

class DataSourceAutoConfigurationReadingTests {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(
                                    DataSourceAutoConfiguration.class));

    @Test
    void propertiesCreateADataSource() {
        runner.withPropertyValues(
                "spring.datasource.url=jdbc:h2:mem:source_read",
                "spring.datasource.username=sa",
                "spring.datasource.password="
        ).run(context -> {
            assertThat(context).hasSingleBean(DataSource.class);
            assertThat(context).hasSingleBean(DataSourceProperties.class);
            assertThat(context).hasBean("dataSource");
        });
    }

    @Test
    void userDataSourceMakesDefaultDataSourceBackOff() {
        runner.withUserConfiguration(UserDataSourceConfiguration.class)
                .run(context -> {
                    assertThat(context).hasSingleBean(DataSource.class);
                    assertThat(context).hasBean("applicationDataSource");
                    assertThat(context).doesNotHaveBean("dataSource");
                });
    }

    @Configuration(proxyBeanMethods = false)
    static class UserDataSourceConfiguration {

        @Bean
        DataSource applicationDataSource() {
            return new DriverManagerDataSource(
                    "jdbc:h2:mem:user_defined", "sa", "");
        }
    }
}
~~~

The test project needs `spring-boot-starter-jdbc`, H2, and `spring-boot-starter-test`. The first test checks the properties bean and output DataSource; the second test confirms that an application-provided bean makes the default DataSource branch back off.

**Test limitation:** it verifies bean registration, not that every SQL query succeeds. If you need to confirm actual connectivity, open a connection or execute a query in an integration test.

### 10.3. Running the Tests

~~~bash
mvn test -Dtest=DataSourceAutoConfigurationReadingTests
~~~

Or Maven Wrapper:

~~~bash
./mvnw test -Dtest=DataSourceAutoConfigurationReadingTests
~~~

Windows PowerShell:

~~~powershell
.\mvnw.cmd test '-Dtest=DataSourceAutoConfigurationReadingTests'
~~~

**Expected result:** both tests PASS:
- When the JDBC URL property is present and H2/Hikari are on the classpath, auto-configuration can register a DataSource.
- When the user provides a DataSource bean, the default DataSource branch backs off and the application-provided bean is retained.

If you want to verify the exact implementation, you can add an assertion:

~~~java
assertThat(context.getBean(DataSource.class))
        .isInstanceOf(com.zaxxer.hikari.HikariDataSource.class);
~~~

Only assert Hikari when Hikari is actually on the classpath and no other pool is specified. With an embedded DB or another implementation, the assertion should match accordingly.

## 11. How to Build an Analysis Table for Any Auto-Configuration

After reading the source, record the findings in a unified table:

| Category | Question to Answer | Evidence in Source |
| --- | --- | --- |
| Candidate | Which imports file loads the class? | `AutoConfiguration.imports` |
| Version | Which exact version of source and Javadoc? | Maven/Gradle dependency tree |
| Class conditions | Which classes/properties/beans are needed at the class level? | Annotations on the class |
| Properties | What are the prefix and input keys? | `@ConfigurationProperties`, metadata, Environment reads |
| Nested conditions | Which branches are enabled? | Nested `@Configuration`, `@Conditional...` |
| Output beans | Which bean names, types, and implementations are created? | `@Bean`, imported configurations |
| Dependencies | Which beans do they depend on? | Method parameters, constructors, `@DependsOn` |
| Back-off | Which user bean causes Boot to stop creating the default? | `@ConditionalOnMissingBean` |
| Public extension | Are there any callbacks/interfaces/strategies? | Public API + framework call site |
| Ordering | Which auto-configurations does it depend on before/after? | `before`, `after`, `@AutoConfigureOrder` |
| Verification | Which tests prove each branch? | `ApplicationContextRunner`, integration tests |

Once complete, you can summarize the auto-configuration in one sentence covering inputs, conditions, and outputs, for example:

> When the JDBC API and a compatible pool/embedded database are present, no R2DBC ConnectionFactory exists, and no application-provided DataSource is present, Spring Boot binds `spring.datasource.*`, selects the matching embedded or pooled branch, and registers a DataSource along with the necessary support beans.

This summary sentence is a verifiable synthesis from source code; it does not replace the detailed condition table.

## 12. Common Mistakes When Reading Source

| Mistake | Why It Is Wrong | How to Fix |
| --- | --- | --- |
| Reading only the initial `*AutoConfiguration` class | Beans may live in nested/imported configurations | Follow `@Import` and open imported classes |
| Assuming `@ConfigurationProperties` means the bean is definitely used | The properties bean may be bound while the branch consuming it does not match | Follow methods accepting properties and their conditions |
| Treating property conditions as the entire input | Properties can also be bound or read via Environment | Search `@ConfigurationProperties`, `@Value`, `Binder`, and `Environment` |
| Recording only the class name, ignoring version | Packages and properties can change across Boot versions | Check the dependency tree and exact-version sources JAR |
| Thinking `@ConditionalOnMissingBean` deletes existing beans | It decides whether default bean registration proceeds | Inspect user-provided bean definitions and condition branches |
| Assuming a bean method always creates a singleton | Scope may differ; the instance may be lazy | Read `@Scope`, `@Lazy`, and lifecycle |
| Assuming every class containing "Customizer" is public API | It may be an internal helper or not collected by the framework | Check visibility, Javadoc, and where the callback is invoked |
| Using JSON metadata as complete source | Metadata does not describe all conditions or runtime logic | Cross-check source, Javadoc, and metadata |
| Reading an output bean without following its dependency chain | Downstream beans may have their own conditions | Follow dependent auto-configurations |
| Testing only context startup | A bean may exist yet be misconfigured or unusable | Assert property binding, type, implementation, and behavior |

## 13. Distinguishing Public API from Internal Details

When developing an application or starter, distinguish:

**Public contract**
- Documented property prefixes/keys;
- public interfaces/classes with Javadoc;
- bean types designed to be overridden by users;
- callbacks collected and invoked by the framework;
- annotations and extension APIs in the Reference Guide.

**Implementation details**
- undocumented package-private/protected nested classes;
- private methods and internal variable names;
- dedicated condition classes used solely to decide a branch;
- metadata optimizing import/filtering;
- unpublished internal collection ordering.

If application code directly imports implementation details, upgrading Boot can break the build even when public behavior remains unchanged. Extend via public APIs and test contracts rather than depending on internal classes.

## 14. Practical Workflow in a Repository

1. Pick the exact auto-configuration from the Condition Evaluation Report or from a bean the application uses.
2. Identify the Boot version in the dependency tree.
3. Open the main class source and imports file.
4. Note class-level annotations: classpath, bean, property, ordering.
5. Open all related `@Import` and nested configurations.
6. Find `@ConfigurationProperties`, record prefixes and keys, and cross-check configuration metadata.
7. Find `@Bean` methods and tabulate names/types/conditions/dependencies.
8. Find `@ConditionalOnMissingBean` and identify which user beans make Boot back off.
9. Find public customizers/configurers/connection details and their actual call sites.
10. Follow downstream auto-configurations to understand the complete bean chain.
11. Write `ApplicationContextRunner` tests for match, no-match, user override, and property variants.
12. Record results by version; do not copy conclusions from another source branch.

A good source analysis report should include:
- Class name and version read;
- input properties;
- class/method conditions;
- bean outputs and implementations;
- public extension points;
- tests proving the main cases;
- conditions or behavior dependent on classpath/profile.

## 15. Self-Check Questions

**Question 1.** If an auto-configuration class has `@EnableConfigurationProperties(MyProperties.class)`, is that enough to conclude the business bean will be created?

**Answer:** Not yet. That annotation registers/binds the properties bean. Business beans still depend on nested configurations, `@Bean` methods, and their corresponding conditions.

**Question 2.** Where should you look to find property prefixes?

**Answer:** Open classes annotated with `@ConfigurationProperties` or bean methods carrying that annotation; check generated metadata and places reading `Environment`/`Binder` for additional conditional properties.

**Question 3.** Why is it necessary to open nested/imported configurations?

**Answer:** The entry-point class may only specify conditions and import branches; the actual output beans are declared inside the imported classes.

**Question 4.** What extension point does `@ConditionalOnMissingBean(DataSource.class)` represent?

**Answer:** If the application provides a matching DataSource before that auto-configuration branch is evaluated, Boot can skip the default DataSource to preserve the application's bean.

**Question 5.** How do you verify a Customizer is a genuine public extension point?

**Answer:** Check the public interface, Javadoc, and where the framework collects/invokes it. Having "Customizer" in the class name is not enough to prove an extension contract.

**Question 6.** Why test with `ApplicationContextRunner`?

**Answer:** It creates a small context with controllable classpath/properties/user beans, allowing verification of conditions and bean registration per case without starting the entire application.

## 16. Official References

- Spring Boot 3.5 Reference — Creating Your Own Auto-configuration: https://docs.spring.io/spring-boot/3.5/reference/features/developing-auto-configuration.html
- Spring Boot 3.5 Reference — Externalized Configuration: https://docs.spring.io/spring-boot/3.5/reference/features/external-config.html
- Spring Boot 3.5 API — `DataSourceAutoConfiguration`: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/jdbc/DataSourceAutoConfiguration.html
- Spring Boot 3.5 API — `DataSourceProperties`: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/jdbc/DataSourceProperties.html
- Spring Boot 3.5 API — `JdbcConnectionDetails`: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/jdbc/JdbcConnectionDetails.html
- Spring Boot 3.5 API — `JdbcTemplateAutoConfiguration`: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/jdbc/JdbcTemplateAutoConfiguration.html
- Spring Boot 3.5 Reference — SQL Databases: https://docs.spring.io/spring-boot/3.5/reference/data/sql.html
- Spring Boot 3.5 Appendix — Common Application Properties: https://docs.spring.io/spring-boot/3.5/appendix/application-properties/

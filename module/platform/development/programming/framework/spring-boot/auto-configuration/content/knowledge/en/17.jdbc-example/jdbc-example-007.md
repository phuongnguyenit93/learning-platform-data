# Reading the Report on Missing Driver, Missing Connection Info, or Replaced DataSource Bean

> **Spring Boot Auto Configuration → JDBC Example.** This lesson explains how to read datasource startup failures across three root-cause groups: JDBC driver missing from the runtime classpath, insufficient connection info, and auto-configuration yielding to an application-provided DataSource bean. Examples use Spring Boot 3.3.x, Java 17+, JDBC, and H2; PostgreSQL/MySQL errors are analyzed separately.

## 1. Start with the question: which stage is the application failing at?

When Spring Boot starts a JDBC application, several things happen before the first SQL statement runs:

1. Spring discovers candidate auto-configurations based on the classpath and registration mechanism.
2. Spring evaluates conditions such as **@ConditionalOnClass**, **@ConditionalOnMissingBean**, and properties.
3. If conditions are satisfied, auto-configuration registers the **DataSource** bean and related components.
4. When the bean is instantiated or a connection is requested, the driver and connection info are used.
5. The application opens a connection to the database; only then can network, authentication, or SQL errors occur.

Therefore, the same generic message like *Failed to configure a DataSource* can stem from different root causes. Distinguish among:

- **Driver not found:** the corresponding JDBC library is not packaged or cannot be loaded at runtime.
- **Missing URL/connection info:** Spring does not know which database to connect to or lacks enough configuration to create a datasource.
- **Cannot connect/authenticate:** driver and URL may be correct, yet the database is unreachable or rejects login.
- **Bean replaced:** the application registered a DataSource itself; Spring Boot deliberately skips the default datasource configuration.
- **Custom bean failed:** auto-configuration backed off, yet the application's datasource factory method failed.

Do not start by randomly adding dependencies, changing URLs, or excluding DataSourceAutoConfiguration. First find the **root exception**, the auto-configuration conditions, and which bean was actually registered.

## 2. Three concepts to distinguish

### 2.1. What is a JDBC driver?

A JDBC driver is a library implementing the connection protocol for a database management system. Examples:

| Database | JDBC driver artifact | Commonly used driver class |
| --- | --- | --- |
| PostgreSQL | org.postgresql:postgresql | org.postgresql.Driver |
| MySQL | com.mysql:mysql-connector-j | com.mysql.cj.jdbc.Driver |
| H2 | com.h2database:h2 | org.h2.Driver |
| Microsoft SQL Server | com.microsoft.sqlserver:mssql-jdbc | com.microsoft.sqlserver.jdbc.SQLServerDriver |

Spring Boot's JDBC starter provides Spring's JDBC infrastructure and the default connection pool (HikariCP in common setups), but **does not automatically bundle drivers for every database**. The application must declare the driver matching the database in use.

Drivers are usually declared at runtime because source code does not necessarily reference the driver class directly:

~~~xml
<dependency>
    <groupId>org.postgresql</groupId>
    <artifactId>postgresql</artifactId>
    <scope>runtime</scope>
</dependency>
~~~

When using the Spring Boot parent or BOM, the driver version can be managed by the corresponding dependency management. With Gradle:

~~~groovy
runtimeOnly 'org.postgresql:postgresql'
~~~

JDBC 4 supports driver discovery via the service provider mechanism when the driver JAR includes proper metadata. Therefore, if the URL is recognized and the driver is on the runtime classpath, you usually do not need to call Class.forName manually or declare driver-class-name by hand. The spring.datasource.driver-class-name property should only be set when explicit specification is needed or the driver cannot be properly inferred from the URL.

### 2.2. The JDBC URL tells where the database is and which protocol to use

A URL has the general form:

~~~text
jdbc:<database-type>:<database-specific-address>
~~~

Example:

~~~properties
spring.datasource.url=jdbc:postgresql://localhost:5432/orders
spring.datasource.username=app_user
spring.datasource.password=secret
~~~

The URL both supplies the database address and tells Spring Boot which driver type is needed. Username/password depend on the database's authentication policy; some environments may use trust authentication, socket identity, or another secret provider. Thus, missing username/password is not always an error, whereas the URL is usually essential when no embedded database is available for Spring to configure automatically.

### 2.3. DataSource is the connection bean, not the JDBC driver

DataSource is the standard JDBC abstraction for obtaining a Connection. It can be implemented by:
- HikariDataSource — connection pool.
- org.apache.tomcat.jdbc.pool.DataSource — Tomcat JDBC pool.
- BasicDataSource — Apache DBCP.
- DriverManagerDataSource — simple implementation, commonly used in examples/tests, not a connection pool.
- A datasource provided directly by the application or another library.

The driver is the component communicating with the database; the URL describes the endpoint; DataSource is the object the application uses to obtain connections. **Having a driver does not mean having a URL; having a URL does not mean the driver is packaged; having a DataSource bean does not guarantee a successful connection.**

## 3. How Spring Boot auto-configures DataSource

In Spring Boot 3.3, DataSourceAutoConfiguration resides in package:

~~~text
org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration
~~~

This auto-configuration has classpath and other conditions. Internally, Boot chooses the suitable configuration:
- If an embedded database such as H2, HSQLDB, or Derby is present and no user-provided datasource exists, Boot can auto-configure an embedded datasource.
- If a suitable connection pool (typically HikariCP) is present, Boot can configure a pooled datasource based on spring.datasource.* properties.
- If the application has already registered a suitable DataSource, the default datasource branches usually **back off** via @ConditionalOnMissingBean.
- If the environment uses an R2DBC ConnectionFactory, the JDBC auto-configuration condition can also prevent the default JDBC configuration from applying.

Conceptual model:

~~~text
Spring Boot starts
        |
        v
Does DataSourceAutoConfiguration have required classes on classpath?
        |
        +-- No --> JDBC auto-configuration does not apply
        |
        +-- Yes
             |
             v
DataSource bean provided by app/other library exists?
             |
             +-- Yes --> default datasource auto-configuration backs off
             |
             +-- No
                    |
                    v
       Suitable embedded DB present?
                    |
                    +-- Yes --> can configure embedded DataSource
                    |
                    +-- No
                           |
                           v
                Suitable URL and driver present?
                           |
                           +-- Yes --> create DataSource per pool/type config
                           |
                           +-- No --> startup failure
~~~

This is an orienting diagram. Exact branch details are determined by the Boot version, pool implementation, classpath, and actual configuration conditions. Do not use this diagram in place of the application's Condition Evaluation Report.

### 3.1. Why can it still run without a URL when H2 is present?

If H2 is on the runtime classpath, Boot can select the embedded database and generate a default in-memory URL when the user omits a URL. Therefore, not seeing spring.datasource.url **does not automatically prove the configuration is wrong**.

Conversely, if there is no embedded database and no URL is declared, Boot cannot guess an external database endpoint. A common case is:

~~~text
Failed to configure a DataSource:
'url' attribute is not specified and no embedded datasource could be configured.
Reason: Failed to determine a suitable driver class
~~~

This message indicates Boot cannot create a default datasource with the available information. It does not mean adding any arbitrary driver is enough; the application still needs a URL/endpoint or a suitable embedded database.

### 3.2. Why can DataSourceAutoConfiguration back off?

A user configuration declares:

~~~java
@Bean
DataSource dataSource() {
    // create custom DataSource
}
~~~

Once Spring recognizes this DataSource bean, default auto-configuration does not need to create a competing datasource. The condition report may show that @ConditionalOnMissingBean did not match because a bean of type javax.sql.DataSource was already found.

This is usually **correct behavior**, not a bug. If the custom bean works, Boot skipping the default datasource is what you want. If the custom bean fails, investigate the factory method, driver, URL, and credentials of that bean itself.

## 4. Reading error signals by root cause

### 4.1. Missing URL or no embedded database

Common symptom:

~~~text
Failed to configure a DataSource:
'url' attribute is not specified and no embedded datasource could be configured.
Reason: Failed to determine a suitable driver class
~~~

How to interpret:
- Boot is trying to create a datasource automatically.
- No suitable URL is present.
- No usable embedded database was found.
- Boot cannot infer a suitable driver to complete the datasource.

Check:
1. Is spring.datasource.url declared in the active profile?
2. Is the key name correct (spring.datasource.url, not spring.datasource.jdbc-url in standard DataSourceProperties config)?
3. Is an embedded DB like H2 actually on the runtime classpath?
4. Do profiles, environment variables, or launch arguments unset/override the URL?
5. Does the application intentionally use a self-created datasource?

Do not fix this by only adding driver-class-name while still lacking a URL. A driver that knows how to talk to PostgreSQL cannot know the hostname, port, and database name on its own.

### 4.2. URL points to a database, but the driver JAR is missing

Suppose the application configures:

~~~properties
spring.datasource.url=jdbc:postgresql://localhost:5432/orders
~~~

but the runtime classpath lacks org.postgresql:postgresql. With HikariCP, the root error often looks like:

~~~text
Failed to load driver class org.postgresql.Driver
~~~

or an error about the driver not being loaded / not accepting the JDBC URL. The exact message depends on the pool, driver, and configuration.

How to check:
- Does the URL have the proper jdbc:postgresql: scheme?
- Is the org.postgresql:postgresql artifact resolved at runtime?
- Was the dependency mistakenly placed in test, provided, or compileOnly scope, or excluded from the dependency graph?
- Does the executable JAR/container package the driver JAR?
- Does the specified driver class match the database and driver version?

Fix by adding the right driver artifact as a runtime dependency and repackaging. Do not add a MySQL driver to fix a PostgreSQL URL; each driver only supports its own protocol.

### 4.3. Driver class is present, but URL is invalid or incompatible

Example:

~~~properties
spring.datasource.url=jdbc:postgres://localhost:5432/orders
spring.datasource.driver-class-name=org.postgresql.Driver
~~~

The URL above uses the wrong scheme; the standard PostgreSQL JDBC URL is jdbc:postgresql://... You may see an error such as:

~~~text
Driver ... claims to not accept jdbcUrl
~~~

Compare:
- URL scheme.
- Driver class.
- Database type and driver version.
- URL parameters.
- The pool in use and how the pool passes the URL to the driver.

Do not conclude the driver is missing merely because the pool reports the URL is rejected. The JAR may have loaded successfully while the URL itself is wrong.

### 4.4. Driver and URL are correct, but the database is unreachable

The following errors happen at the connection stage:

~~~text
Connection refused
Connection timed out
UnknownHostException
password authentication failed
Access denied for user
database does not exist
~~~

These are not missing-driver errors:
- Connection refused: the endpoint may be right, but the server is not listening, the port is wrong, or a firewall rejects it.
- Connection timed out: no response received within the timeout; check network, security groups, routes, and server.
- UnknownHostException: hostname cannot be resolved.
- Authentication failure: the database rejects the credentials or authentication method.
- Database does not exist: the server responded, but the database name is wrong or has not been created yet.

Read Caused by along with the selected JDBC URL/driver info. Do not post passwords, tokens, or URLs containing secrets into logs, issues, or public diagnostic reports.

### 4.5. DataSourceAutoConfiguration did not match because a bean already exists

In the Condition Evaluation Report, you may see content similar to:

~~~text
DataSourceConfiguration.Hikari:
   Did not match:
      @ConditionalOnMissingBean
      found beans of type 'javax.sql.DataSource'
~~~

Meaning: Boot found an existing datasource and **deliberately did not create the default Hikari datasource**. This is a sign of a replacement bean, not proof that the default driver is missing.

Next steps:
1. Find the bean name and actual class of the DataSource.
2. Locate the configuration/factory method that created the bean.
3. Check whether that bean receives the right properties.
4. Try opening a connection and inspect the root exception.
5. Check @Primary / @Qualifier if multiple datasources exist.

If the user-created bean fails, Spring does not fall back to creating another default datasource as a backup. The back-off condition was already satisfied by the presence of the bean definition; the custom bean must be fixed at its root cause.

## 5. Condition Evaluation Report: what to read and where?

### 5.1. Enable the report with --debug

Run the application with:

~~~bash
java -jar target/jdbc-diagnostics-1.0.0.jar --debug
~~~

Or add the appropriate debug setting when running in your IDE. Spring Boot prints the **Condition Evaluation Report**, containing:
- Positive matches: conditions that matched.
- Negative matches: conditions that did not match and why.
- Exclusions: excluded auto-configurations.
- Unconditional classes: configurations processed without standard conditions.

When investigating datasources, look for these names:
- DataSourceAutoConfiguration
- DataSourceConfiguration.Hikari
- EmbeddedDatabaseConfiguration
- PooledDataSourceConfiguration
- Auto-configurations related to transaction manager or JDBC template if needed.

Nested configuration names and formatting may vary across versions. Read your own application's report.

### 5.2. Four result patterns and how to conclude

| Observation | Interpretation | Next step |
| --- | --- | --- |
| DataSourceAutoConfiguration did not match due to missing class | Required JDBC infrastructure is missing from the classpath | Check spring-jdbc, starters, and runtime dependencies |
| DataSourceAutoConfiguration matched, but initialization failed due to URL/driver | Auto-config conditions passed; error is in connection info or datasource creation | Read failure analysis and Caused by; check URL/driver |
| DataSourceConfiguration.Hikari did not match because DataSource already exists | Bean provided by app or another library; Boot backed off | Identify the actual bean and factory method |
| Embedded database configuration matched | Boot may use default H2/HSQLDB/Derby | Confirm whether the app intentionally uses an embedded DB |

**A positive match does not mean connecting succeeded.** The condition report states which configuration was chosen; it does not prove the driver can open a connection, the database exists, or credentials are valid.

### 5.3. Using Actuator when the application can start

If the application has spring-boot-starter-actuator, the conditions endpoint can help inspect conditions after the context is created:

~~~properties
management.endpoints.web.exposure.include=health,info,conditions
~~~

The endpoint is typically:

~~~text
/actuator/conditions
~~~

Only expose diagnostic endpoints in controlled environments and protect them with appropriate security controls. If the application fails before the server/Actuator is ready, use --debug and the stack trace instead of expecting the endpoint to be reachable.

### 5.4. Read the root exception, not just the first line

For example, a stack trace may pass through:
- BeanCreationException
- UnsatisfiedDependencyException
- DataSourceBeanCreationException
- HikariPool / HikariConfig
- DriverManager
- The specific JDBC driver

The outer Spring exceptions describe which bean could not be created. Deeper Caused by entries usually reveal the real reason: driver class failed to load, invalid URL, socket timeout, authentication failure, or SQL error. Record both the outer exception and the root cause.

## 6. Checking runtime dependencies and artifacts

### 6.1. Maven

View the overall dependency tree:

~~~bash
mvn dependency:tree
~~~

Inspect only the PostgreSQL driver:

~~~bash
mvn dependency:tree -Dincludes=org.postgresql:postgresql
~~~

Inspect dependencies resolved in runtime scope:

~~~bash
mvn dependency:tree -Dscope=runtime
~~~

If the driver is missing, check:
- Was the dependency declared in the right module?
- Is it in dependencyManagement while missing from actual dependencies?
- Is the scope test or provided?
- Is there an exclusion from a parent dependency?
- Does the module building the executable JAR inherit the dependency?

### 6.2. Gradle

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency postgresql --configuration runtimeClasspath
~~~

runtimeClasspath matters because an application can compile successfully while lacking the driver at runtime. dependencyInsight explains why a module/version was selected and which dependency path pulled it in.

### 6.3. Inspecting a Spring Boot executable JAR

In a Spring Boot executable JAR, dependencies typically live in:

~~~text
BOOT-INF/lib/
~~~

Check in Bash:

~~~bash
jar tf target/app.jar | grep BOOT-INF/lib
~~~

On Windows PowerShell/CMD:

~~~powershell
jar tf target/app.jar | findstr BOOT-INF/lib
~~~

Look for the exact artifact, such as postgresql-*.jar or mysql-connector-j-*.jar. Inspect container images similarly: a dependency present on an IDE machine is not guaranteed to be inside the running image.

### 6.4. Do not confuse compile classpath with runtime classpath

| Declaration | Typical meaning | Risk for JDBC driver |
| --- | --- | --- |
| Maven compile / runtime | Available at runtime | Suitable for driver if packaged |
| Maven test | Only for tests | Production app lacks driver |
| Maven provided | Expected to be provided by runtime environment | May be missing in executable JAR/container |
| Gradle runtimeOnly | Needed only at runtime | Usually appropriate for driver |
| Gradle testRuntimeOnly | Test runtime only | Production may lack driver |
| Gradle compileOnly | Compile only | Insufficient for JDBC connections at runtime |

The driver must be present in the actual runtime environment, not just during compilation.

## 7. Distinguishing standard DataSource config from user-created beans

### 7.1. Standard configuration via spring.datasource.*

PostgreSQL example:

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://db.example.internal:5432/orders
    username: orders_app
    password: secret-from-environment
    driver-class-name: org.postgresql.Driver
    hikari:
      maximum-pool-size: 10
      connection-timeout: 30000
~~~

Under default auto-configuration:
- DataSourceProperties reads spring.datasource.* properties.
- Spring Boot infers the driver from the URL when possible.
- Boot selects the appropriate datasource/pool implementation.
- Pool properties under spring.datasource.hikari.* are applied to Hikari when Hikari is chosen.

Normally you can omit driver-class-name if the URL and driver JAR are sufficient to infer the driver. Explicit declaration is useful when control is needed, but it never substitutes for the driver JAR.

### 7.2. User declares DataSource themselves: Boot yields

Example:

~~~java
@Configuration(proxyBeanMethods = false)
class CustomDatabaseConfiguration {

    @Bean
    DataSource dataSource() {
        DriverManagerDataSource dataSource =
                new DriverManagerDataSource();

        dataSource.setDriverClassName("org.h2.Driver");
        dataSource.setUrl("jdbc:h2:mem:customdb;DB_CLOSE_DELAY=-1");
        dataSource.setUsername("sa");
        dataSource.setPassword("");

        return dataSource;
    }
}
~~~

This is a manual configuration using DriverManagerDataSource, suitable for examples or simple tests. It is not a production connection pool. When this bean is registered, DataSourceAutoConfiguration does not create a competing default datasource because the missing-bean condition is no longer satisfied.

Key point to remember: **spring.datasource.* does not automatically bind to every user-written DataSource bean.** When creating a bean manually, the user must configure it themselves or use DataSourceProperties / @ConfigurationProperties per their own design.

### 7.3. If you want to create HikariDataSource manually and still bind properties

A common approach is using DataSourceProperties to convert the standard url into the pool's matching URL property:

~~~java
@Configuration(proxyBeanMethods = false)
class CustomPoolConfiguration {

    @Bean
    @ConfigurationProperties("app.datasource")
    DataSourceProperties dataSourceProperties() {
        return new DataSourceProperties();
    }

    @Bean
    @ConfigurationProperties("app.datasource.configuration")
    HikariDataSource dataSource(DataSourceProperties properties) {
        return properties.initializeDataSourceBuilder()
                .type(HikariDataSource.class)
                .build();
    }
}
~~~

Configuration example:

~~~yaml
app:
  datasource:
    url: jdbc:postgresql://localhost:5432/orders
    username: orders_app
    password: secret-from-environment
    configuration:
      maximum-pool-size: 10
      connection-timeout: 30000
~~~

This is a custom datasource configuration using its own prefix app.datasource; it does not automatically apply spring.datasource defaults. Ensure the PostgreSQL dependency and configuration registration conditions are properly declared.

When binding directly onto HikariDataSource, Hikari's property is jdbc-url, whereas standard DataSourceProperties uses url. This is a common source of confusion; using DataSourceProperties.initializeDataSourceBuilder() preserves the url name in application config.

### 7.4. Multiple DataSources and @Primary / @Qualifier

If an application has multiple datasources, Boot may back off default datasource configuration when a user-provided DataSource bean already exists. When injecting without specifying a bean, Spring can throw NoUniqueBeanDefinitionException.

Solutions:
- Use @Qualifier("ordersDataSource") when a service needs a specific datasource.
- Use @Primary on the default datasource when injections do not specify a qualifier.
- Configure transaction managers and repositories appropriate for each datasource.
- Check bean names, types, and package scanning/imports.

@Primary only helps Spring pick a preferred bean when type-based injection has multiple candidates. It is **not** what makes DataSourceAutoConfiguration create or skip creating a bean; the presence of a DataSource bean is what triggers the back-off condition.

## 8. Java 17 + Spring Boot 3.3 Lab: observing default and replacement datasources

The lab uses H2 to run locally without a database server. There are two states:
1. Custom datasource disabled: Boot creates a Hikari datasource from spring.datasource.*.
2. Custom datasource enabled: the application registers its own DataSource; Boot backs off.

### 8.1. Project structure

~~~text
jdbc-diagnostics/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── demo/
        │       └── jdbc/
        │           └── JdbcDiagnosticsApplication.java
        └── resources/
            └── application.properties
~~~

### 8.2. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>jdbc-diagnostics</artifactId>
    <version>1.0.0</version>
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
            <scope>runtime</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

spring-boot-starter-jdbc brings in Spring JDBC and HikariCP in the standard starter setup. H2 is the separate database driver declared at runtime.

### 8.3. application.properties

~~~properties
spring.datasource.url=jdbc:h2:mem:autoconfigdb;DB_CLOSE_DELAY=-1
spring.datasource.username=sa
spring.datasource.password=

spring.main.banner-mode=off
logging.level.root=OFF
~~~

The URL points to an H2 in-memory database named autoconfigdb. DB_CLOSE_DELAY=-1 keeps the database alive for the JVM's lifetime even if a connection closes; when the JVM exits, the in-memory database disappears.

### 8.4. JdbcDiagnosticsApplication.java

~~~java
package demo.jdbc;

import java.sql.Connection;
import java.sql.ResultSet;
import java.sql.Statement;
import javax.sql.DataSource;

import org.springframework.beans.factory.ObjectProvider;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.datasource.DriverManagerDataSource;

@SpringBootApplication
public class JdbcDiagnosticsApplication {

    public static void main(String[] args) {
        SpringApplication.run(JdbcDiagnosticsApplication.class, args);
    }

    @Bean
    @ConditionalOnProperty(
            prefix = "demo.datasource",
            name = "custom",
            havingValue = "true"
    )
    DataSource customDataSource() {
        DriverManagerDataSource dataSource =
                new DriverManagerDataSource();

        dataSource.setDriverClassName("org.h2.Driver");
        dataSource.setUrl(
                "jdbc:h2:mem:customdb;DB_CLOSE_DELAY=-1"
        );
        dataSource.setUsername("sa");
        dataSource.setPassword("");

        return dataSource;
    }

    @Bean
    ApplicationRunner report(
            ApplicationContext context,
            ObjectProvider<DataSource> dataSources) {

        return args -> {
            String[] names =
                    context.getBeanNamesForType(DataSource.class);

            System.out.println("DataSource bean count: " + names.length);

            DataSource dataSource = dataSources.getIfAvailable();
            if (dataSource == null) {
                System.out.println("DataSource present: false");
                return;
            }

            System.out.println(
                    "DataSource implementation: " +
                    dataSource.getClass().getName()
            );

            try (Connection connection = dataSource.getConnection()) {
                System.out.println(
                        "Database URL: " +
                        connection.getMetaData().getURL()
                );

                try (Statement statement = connection.createStatement();
                     ResultSet result = statement.executeQuery("SELECT 1")) {

                    result.next();
                    System.out.println("SELECT 1: " + result.getInt(1));
                }
            }
        };
    }
}
~~~

@ConditionalOnProperty on customDataSource() only creates the replacement bean when demo.datasource.custom=true. Because this is a bean in application configuration, it is registered before default datasource auto-configuration evaluates its missing-bean condition.

ObjectProvider<DataSource> lets the runner handle the missing-datasource case without causing constructor injection to fail immediately. In the lab's two passing cases there is always exactly one datasource.

### 8.5. Case A — Boot creates the default datasource

Package:

~~~bash
mvn -q -DskipTests package
~~~

Run:

~~~bash
java -jar target/jdbc-diagnostics-1.0.0.jar
~~~

Stdout printed by the program:

~~~text
DataSource bean count: 1
DataSource implementation: com.zaxxer.hikari.HikariDataSource
Database URL: jdbc:h2:mem:autoconfigdb
SELECT 1: 1
~~~

Conclusions:
- H2 driver is on the runtime classpath.
- URL and credentials work.
- Auto-configuration picks the Hikari datasource.
- Connection opens successfully and the verification SQL query returns 1.

### 8.6. Case B — Application provides its own DataSource

Run the same artifact with the property enabling the custom bean:

~~~bash
java -jar target/jdbc-diagnostics-1.0.0.jar --demo.datasource.custom=true
~~~

Stdout:

~~~text
DataSource bean count: 1
DataSource implementation: org.springframework.jdbc.datasource.DriverManagerDataSource
Database URL: jdbc:h2:mem:customdb
SELECT 1: 1
~~~

Conclusions:
- The application's customDataSource bean exists.
- DataSourceAutoConfiguration did not create the default Hikari datasource.
- DriverManagerDataSource opens a connection successfully because the H2 driver is present.
- spring.datasource.url in application.properties does not automatically become the custom bean's URL; the custom bean uses the URL declared in its factory method.

This is **intentional back-off**, not a driver error. If you want the custom bean to use external configuration, bind properties to it as shown in section 7.3.

### 8.7. Case C — Remove H2 to reproduce missing URL and embedded database

To test the missing URL error:
1. Temporarily remove the H2 dependency from pom.xml.
2. Delete or comment out spring.datasource.url, username, and password in application.properties.
3. Re-run mvn -q clean package.
4. Start the application.

With no embedded database and no URL, startup will fail. Failure analysis typically contains:

~~~text
Failed to configure a DataSource:
'url' attribute is not specified and no embedded datasource could be configured.
Reason: Failed to determine a suitable driver class
~~~

This is a **missing connection info / no embedded DB** situation, not proof that a PostgreSQL or MySQL driver needs to be added arbitrarily. Identify the real database the application intends to use, then declare its URL and proper driver.

Restore the H2 dependency and application.properties after testing.

### 8.8. Case D — PostgreSQL URL without PostgreSQL driver

To simulate a missing driver:
1. Keep the spring-boot-starter-jdbc dependency.
2. Do not add org.postgresql:postgresql.
3. Change the URL to:

~~~properties
spring.datasource.url=jdbc:postgresql://localhost:5432/orders
spring.datasource.username=orders_app
spring.datasource.password=secret
~~~

4. Optionally remove H2 to avoid embedded fallback; the PostgreSQL URL already specifies the needed driver.
5. Package and run again.

The root error typically indicates org.postgresql.Driver cannot be loaded. A running database server is not required to detect some driver-loading errors: if the driver JAR is absent, the error can occur before attempting a connection.

Fix by adding:

~~~xml
<dependency>
    <groupId>org.postgresql</groupId>
    <artifactId>postgresql</artifactId>
    <scope>runtime</scope>
</dependency>
~~~

Then rebuild. Once the driver loads, if PostgreSQL is not running or credentials are wrong, the next failure will be in the network/authentication category; that is a separate diagnostic stage.

## 9. Testing whether auto-configuration creates or backs off DataSource

You can use ApplicationContextRunner to test conditions without running the full application. Add the test dependency to pom.xml:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

Create a custom datasource configuration for use in tests:

~~~java
package demo.jdbc;

import javax.sql.DataSource;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.datasource.DriverManagerDataSource;

@Configuration(proxyBeanMethods = false)
class TestDataSourceConfiguration {

    @Bean
    DataSource userDataSource() {
        DriverManagerDataSource dataSource =
                new DriverManagerDataSource();

        dataSource.setDriverClassName("org.h2.Driver");
        dataSource.setUrl("jdbc:h2:mem:userdb");
        dataSource.setUsername("sa");
        dataSource.setPassword("");

        return dataSource;
    }
}
~~~

Create the test:

~~~java
package demo.jdbc;

import javax.sql.DataSource;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.jdbc.datasource.DriverManagerDataSource;

import static org.assertj.core.api.Assertions.assertThat;

class DataSourceAutoConfigurationTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(AutoConfigurations.of(
                            DataSourceAutoConfiguration.class
                    ));

    @Test
    void embeddedH2CanCreateDefaultDataSourceWithoutUrl() {
        runner.run(context -> {
            assertThat(context).hasSingleBean(DataSource.class);
            assertThat(context.getBean(DataSource.class))
                    .isNotNull();
        });
    }

    @Test
    void userDataSourceMakesAutoConfigurationBackOff() {
        runner.withUserConfiguration(TestDataSourceConfiguration.class)
                .run(context -> {
                    assertThat(context).hasSingleBean(DataSource.class);
                    assertThat(context.getBean(DataSource.class))
                            .isInstanceOf(DriverManagerDataSource.class);
                });
    }
}
~~~

With the H2 runtime dependency still present, run:

~~~bash
mvn test
~~~

Expected **2 tests PASS**:
- H2 is on the classpath so Boot can create an embedded datasource even without an explicit URL.
- When user configuration supplies a datasource, the custom bean is present and auto-configuration does not create an additional default datasource.

These two tests verify bean selection. Missing-driver or missing-URL-without-embedded-DB cases are startup failures; verify them with dedicated integration tests or test runs with the corresponding classpath rather than pretending the context succeeds in those cases.

## 10. How to read the report for each real-world scenario

### Scenario 1 — No suitable driver

**Evidence:**
- URL uses a PostgreSQL/MySQL scheme.
- Dependency tree or executable JAR lacks the corresponding driver.
- Stack trace reports inability to load the driver class.

**Conclusion:** runtime dependency/driver error. Add the exact artifact and check scope/packaging.

### Scenario 2 — No URL and no embedded DB

**Evidence:**
- spring.datasource.url does not exist in the Environment.
- H2/HSQLDB/Derby are absent from the runtime classpath.
- Failure analysis states URL is not specified and no embedded datasource could be configured.

**Conclusion:** missing connection endpoint. Provide a real database URL and appropriate driver, or add an embedded database if intended.

### Scenario 3 — URL is valid, but connection is refused

**Evidence:**
- Driver loaded.
- URL accepted by the driver.
- getConnection() fails with network, timeout, or authentication error.

**Conclusion:** check host/port, server status, DNS, firewall, database name, username/password, and permissions. Do not keep adding drivers if the driver already loaded properly.

### Scenario 4 — DataSourceAutoConfiguration backed off

**Evidence:**
- Negative match on @ConditionalOnMissingBean.
- Report states a DataSource bean was already found.
- Context contains the bean name/class of a datasource registered by the user or another library.

**Conclusion:** Boot is yielding to an existing bean. Identify that bean's factory method, config properties, and connection logic.

### Scenario 5 — Custom bean exists, but cannot open a connection

**Evidence:**
- Condition report confirms Boot backed off.
- Context has the custom datasource.
- Failure occurs when obtaining a connection, usually starting from the custom bean's class/driver/URL.

**Conclusion:** fix the custom datasource's factory method or property binding. Do not wait for Boot to create a second datasource; the back-off condition worked properly.

### Scenario 6 — Multiple DataSources exist

**Evidence:**
- Bean count is greater than one.
- Injection by type throws NoUniqueBeanDefinitionException.

**Conclusion:** determine which datasource belongs to which repository/service; use @Qualifier, @Primary, transaction managers, and properly scoped repository configuration.

## 11. Step-by-step diagnostic workflow

1. **Read the first exception and the full Caused by chain.** Determine whether failure occurred during condition resolution, bean creation, driver loading, or opening a connection.
2. **Check whether a DataSource bean is registered.** Use the condition report and bean type/name; do not assume Boot always creates a default datasource.
3. **If no bean exists:** check whether DataSourceAutoConfiguration matched, which nested config was excluded, and why.
4. **If the bean is user-provided:** locate the exact factory method/class and property sources for that bean.
5. **Verify the JDBC URL.** Does the scheme match the database? Are host, port, database name, and query parameters valid?
6. **Verify the driver on the runtime classpath.** Use Maven/Gradle dependency trees and inspect the executable JAR/container contents.
7. **Verify credentials.** Confirm the actual username/password or authentication method; do not log secrets.
8. **Test connectivity with the same endpoint and credentials from the deployment environment.** This separates application errors from network/database errors.
9. **Use --debug to read the Condition Evaluation Report.** Distinguish positive matches, negative matches, and back-off due to an existing bean.
10. **Fix one confirmed root cause, then re-run tests/startup and a simple query.** Do not only check that the app printed Started; verify obtaining a connection and executing SQL succeed.

## 12. Common misconceptions

1. **Adding spring-boot-starter-jdbc brings all drivers.** False; specific database drivers are usually separate dependencies.
2. **Having a driver means no URL is needed.** False for external databases; the driver does not know the endpoint on its own.
3. **Missing URL is always an error.** False if an embedded database is on the classpath and Boot can auto-configure it.
4. **Failed to determine a suitable driver class always has one single cause.** You must read the URL, embedded DB, driver, and runtime classpath to pinpoint it.
5. **DataSourceAutoConfiguration backing off means auto-configuration is broken.** It may be the intended behavior because the application already provided a datasource.
6. **@Primary stops Boot from creating a datasource.** The back-off condition checks whether a DataSource bean exists; @Primary mainly resolves injection choice when multiple beans exist.
7. **spring.datasource.* automatically binds to every custom datasource.** False; user-created beans need their own configuration/binding.
8. **Having a DataSource bean means the database can connect.** False; the bean object can be created while opening a connection still fails.
9. **Connection refused means missing driver.** This is usually a network/server error; the driver already got past loading.
10. **NoUniqueBeanDefinitionException means missing datasource.** It can mean multiple datasources exist; check bean count and qualifiers.
11. **Excluding DataSourceAutoConfiguration fixes all JDBC errors.** It can remove default beans the app actually needs while fixing neither the driver nor connectivity.
12. **Running in an IDE means the executable JAR/container has the driver.** Runtime artifacts can differ from the IDE classpath.
13. **Reading only the first log line is enough.** The root exception is usually deeper in Caused by.
14. **Passwords are always required or always empty.** That depends on the database and authentication policy; do not enforce one rule across all systems.
15. **A positive match in the report means SQL will run.** The report only describes configuration conditions; open a connection and run a query to verify.

## 13. Operations and release checklist

- [ ] Identified which DataSource bean is actually used.
- [ ] Driver artifact matches the database and is on the runtime classpath.
- [ ] JDBC URL has the correct scheme, host, port, database name, and parameters.
- [ ] URL or embedded database is sufficient for Boot to configure the datasource.
- [ ] Credentials/authentication are supplied via an appropriate configuration source.
- [ ] If a custom DataSource exists, its factory method binds/configures it completely.
- [ ] Understood clearly why DataSourceAutoConfiguration matched or backed off.
- [ ] If multiple datasources exist, qualifiers/primary and transaction managers are set properly.
- [ ] Verified the executable JAR/container, not just the IDE classpath.
- [ ] Ran --debug or read the Condition Evaluation Report when discrepancies appeared.
- [ ] Tested getConnection() and a simple SQL statement.
- [ ] Avoided putting passwords, tokens, or secrets in logs and error reports.

## 14. Self-check questions

**Question 1.** spring-boot-starter-jdbc is present, and the application uses PostgreSQL. Why is the PostgreSQL driver still required?  
**Answer:** The starter provides JDBC/pool infrastructure; the PostgreSQL driver is a separate library implementing the PostgreSQL protocol and must be on the runtime classpath.

**Question 2.** spring.datasource.url is not declared, but H2 is on the runtime classpath. Will startup definitely fail?  
**Answer:** No. Boot can automatically configure embedded H2.

**Question 3.** The URL is jdbc:postgresql://..., but org.postgresql.Driver cannot be loaded. Which error category?  
**Answer:** Missing or unloadable driver on the runtime classpath.

**Question 4.** The condition report says @ConditionalOnMissingBean did not match because a DataSource was found. Does that mean Boot is broken?  
**Answer:** No. Boot is yielding to the already-registered datasource bean.

**Question 5.** The application has a custom DataSource, yet spring.datasource.url has no effect. Why?  
**Answer:** A custom bean does not automatically receive datasource auto-configuration binding; the bean must be configured or bound to DataSourceProperties separately.

**Question 6.** Driver and URL are correct, yet Connection refused occurs. What should be checked?  
**Answer:** Whether the server is running, host/port, DNS, firewall, routes, and endpoint; stop blindly adding drivers.

**Question 7.** Two DataSource beans exist, and injection by type fails. What is the solution?  
**Answer:** Define the role of each bean, use @Qualifier or @Primary appropriately, and configure repositories/transaction managers.

## 15. Official references

- [Spring Boot 3.3 Javadoc — DataSourceAutoConfiguration](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/jdbc/DataSourceAutoConfiguration.html).
- [Spring Boot 3.3 Javadoc — DataSourceProperties](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/jdbc/DataSourceProperties.html).
- [Spring Boot Reference — SQL Databases and Configure a DataSource](https://docs.spring.io/spring-boot/3.3/reference/data/sql.html).
- [Spring Boot Reference — Auto-configuration and Condition Evaluation Report](https://docs.spring.io/spring-boot/3.3/reference/using/auto-configuration.html).
- [Spring Boot Reference — Externalized Configuration](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html).
- [JDBC API — DataSource](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/javax/sql/DataSource.html)
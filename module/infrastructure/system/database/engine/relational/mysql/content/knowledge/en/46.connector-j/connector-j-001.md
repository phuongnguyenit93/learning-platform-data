# Choosing Connector/J by JDK, JDBC, and MySQL Compatibility Matrix

MySQL Connector/J is the official JDBC Type 4 driver for Java applications to connect to MySQL over the MySQL network protocol. Selecting a driver version requires evaluating the Java runtime, the JDBC level implemented by the driver, the MySQL Server version, the framework in use, and security requirements simultaneously. A newer JDK does not automatically make every new JDBC method supported by the driver; similarly, a newer driver is not necessarily suitable for every older server version.

This lesson belongs to the **DATABASE_MYSQL** module and focuses on connecting to MySQL from Java applications: reading compatibility matrices, choosing artifacts, managing dependencies, verifying the running driver, and testing before production upgrades.

## 1. Where Does Connector/J Fit in Java and MySQL Architecture?

A JDBC application typically consists of the following components:

1. The application calls standard APIs in java.sql and javax.sql.
2. JDBC DriverManager or DataSource selects the appropriate driver.
3. MySQL Connector/J translates JDBC calls into MySQL protocol messages.
4. MySQL Server authenticates the connection, executes SQL, and returns results.

Connector/J is a **Type 4** driver: the protocol implementation is written in pure Java and does not require native MySQL client libraries. Applications can use the same standard JDBC API without implementing the database protocol themselves.

Connector/J supports two API tracks:

- **JDBC API** used with Connection, PreparedStatement, ResultSet, DataSource, and frameworks such as Spring JDBC, Hibernate, or MyBatis.
- **X DevAPI** is MySQL's proprietary API, using the X Protocol and a collection/table model. It is not the JDBC API and does not replace the JDBC driver in applications using java.sql.

A Spring Boot application using the JDBC URL jdbc:mysql://... uses Connector/J over the classic MySQL protocol. X DevAPI is a separate choice when the application actively uses that API.

## 2. Distinguishing JDK, JRE, and JDBC Versions

These three concepts are related but not synonymous:

| Component | Meaning | What to check |
|---|---|---|
| JDK | Java Development Kit, containing the compiler and runtime | The version used to compile and the bytecode target of the application |
| JRE/runtime | Java application runtime environment | The actual Java version of the container, host, or process |
| JDBC API | Java API contract for database access | Which JDBC level the driver implements and whether it supports the methods the application needs |

A driver may run on a newer JRE while only implementing an older JDBC level. For example, Connector/J 26.10 implements JDBC 4.2. If an application or library calls a method available only in JDBC 4.3, the driver may throw SQLFeatureNotSupportedException even when the application is running on a modern JDK.

Therefore, you need to check all of the following:

- The driver's minimum Java runtime.
- The JDBC level implemented by the driver.
- The specific APIs called by the framework or application.
- The Java bytecode target of the application itself.

Do not choose a driver solely based on the output of java -version. Cross-check against the compatibility documentation of the exact Connector/J version and test the APIs actually used.

## 3. Reading the Connector/J Compatibility Matrix

At the time of writing (November 2026), the current release series is Connector/J **26.10.0**, announced GA on October 21, 2026, replacing the 9.7 series. The 26.10 compatibility documentation states:

- JRE 8 or higher.
- JDK 8 or higher if building Connector/J from source.
- JDBC 4.2.
- MySQL Server 8.4 or higher according to the version compatibility chapter.

The Connector/J **9.7.0** series reached GA earlier, and its release notes state support for MySQL Server 8.0 or higher, also implementing JDBC 4.2. Therefore, if the server is on MySQL 8.0, carefully read the matrix for the selected driver branch rather than just looking at the latest version number.

| Driver | Documented Java runtime | JDBC | MySQL Server per version documentation |
|---|---|---|---|
| Connector/J 26.10.0 | JRE 8+ | 4.2 | Compatibility chapter states 8.4+ |
| Connector/J 9.7.0 | Check 9.x branch documentation and release package | 4.2 | 8.0+ |
| Connector/J 8.0.x | JRE 8+ per 8.0 branch documentation | 4.2 | Cross-check patch and target server; 8.0 branch documentation describes MySQL 8.0+ support |
| Connector/J 5.1.x | Older Java per legacy documentation | Older JDBC | Use only when maintaining an already tested legacy platform |

**Note on version 26.10 documentation:** the overview and What's New sections describe 26.10 as usable with MySQL Server 8.0 and higher, whereas the Compatibility with MySQL and Java Versions chapter states 8.4 and higher. When there is a discrepancy between the overview description and the detailed matrix, do not assume production supportability on your own. Cross-check release notes, updated support matrices, and the support policy of the target server; test with the exact version pair before deployment.

### Choose by Server First, Then Check Java

A practical selection approach:

- **MySQL Server 8.4 or higher:** evaluate Connector/J 26.10.0 first, then check Java runtime, JDBC API, and compatibility changes.
- **MySQL Server 8.0:** Connector/J 9.7.0 is documented in its release notes as supporting 8.0 and higher. If you want to use 26.10.0, clarify the discrepancy in the official documentation and confirm via testing.
- **Older MySQL Server:** use the compatibility matrix and release notes for the exact driver branch. Do not assume the latest driver supports all older servers.
- **Older Java runtime:** select a driver branch that still supports that runtime and has appropriate patches. If no supported branch exists, plan a Java/server upgrade rather than keeping a legacy driver indefinitely.

A version pair documented as compatible still requires testing authentication plugins, TLS, SQL mode, timezones, data types, prepared statements, and the features the application actually uses.

## 4. JDBC 4.x and Automatic Driver Loading

Modern Connector/J supports automatic JDBC driver registration via the Service Provider mechanism. When the JAR is on the appropriate classpath or module path, DriverManager can locate the driver without calling Class.forName().

Current driver class name:

~~~java
com.mysql.cj.jdbc.Driver
~~~

Connection example:

~~~java
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.SQLException;

public class MySqlConnectionExample {
    public static void main(String[] args) throws SQLException {
        String url = "jdbc:mysql://db.example.com:3306/app";
        String user = System.getenv("DB_USER");
        String password = System.getenv("DB_PASSWORD");

        try (Connection connection =
                 DriverManager.getConnection(url, user, password)) {
            System.out.println("Connected: " + !connection.isClosed());
        }
    }
}
~~~

Class.forName("com.mysql.cj.jdbc.Driver") is only needed in certain legacy environments with special class loading mechanisms. If DriverManager reports that no suitable driver was found, verify whether the JAR is actually on the runtime classpath, or whether the dependency was excluded or mispackaged, before adding Class.forName.

Do not use the old class name com.mysql.jdbc.Driver in new applications. That is the legacy name from Connector/J 5.1; modern applications should rely on auto-registration or use com.mysql.cj.jdbc.Driver when an explicit declaration is required.

## 5. Declaring Maven and Gradle Dependencies

Connector/J is published on Maven Central with:

- groupId: com.mysql
- artifactId: mysql-connector-j

Maven example for Connector/J 26.10.0:

~~~xml
<dependency>
    <groupId>com.mysql</groupId>
    <artifactId>mysql-connector-j</artifactId>
    <version>26.10.0</version>
    <scope>runtime</scope>
</dependency>
~~~

Gradle example:

~~~kotlin
dependencies {
    runtimeOnly("com.mysql:mysql-connector-j:26.10.0")
}
~~~

If the target server is MySQL 8.0 and you chose the 9.7 branch after checking compatibility, replace the version with a project-approved 9.7.x patch. Do not use dynamic versions like plus signs or latest.release in production because subsequent builds could pull a different driver without any explicit source code change.

### Choosing Scope

- **runtime** is appropriate when the source code only uses standard JDBC APIs available in the JDK and the driver is only needed at runtime.
- **compile** may be needed if the source code directly references Connector/J-specific classes or extensions.
- In Spring Boot, check which BOM or parent version manages the dependency. Do not add a second Connector/J version if a starter already pulls the driver into the dependency graph.

Inspect actual dependencies:

~~~bash
# Maven
mvn dependency:tree -Dincludes=com.mysql:mysql-connector-j

# Gradle
./gradlew dependencies --configuration runtimeClasspath
~~~

There should only be one version of Connector/J at runtime. If both the old mysql-connector-java JAR and the new mysql-connector-j JAR are present, the classloader may load an unexpected driver or cause hard-to-diagnose errors.

## 6. Inspecting the Actual Driver and Server at Runtime

Do not rely solely on pom.xml or build.gradle. An application might run with a different JAR provided by the container, application server, plugin, shaded JAR, or prepackaged libraries.

Read metadata from the connection:

~~~java
import java.sql.Connection;
import java.sql.DatabaseMetaData;
import java.sql.DriverManager;

public class DriverDiagnostics {
    public static void printInfo(String url, String user, String password)
            throws Exception {
        try (Connection connection =
                 DriverManager.getConnection(url, user, password)) {
            DatabaseMetaData metadata = connection.getMetaData();

            System.out.println("Driver: "
                    + metadata.getDriverName());
            System.out.println("Driver version: "
                    + metadata.getDriverVersion());
            System.out.println("Database: "
                    + metadata.getDatabaseProductName());
            System.out.println("Server version: "
                    + metadata.getDatabaseProductVersion());
            System.out.println("JDBC: "
                    + metadata.getJDBCMajorVersion() + "."
                    + metadata.getJDBCMinorVersion());
        }
    }
}
~~~

You can check the running Java version with:

~~~java
System.out.println(System.getProperty("java.version"));
System.out.println(System.getProperty("java.vendor"));
~~~

This information confirms the actual runtime, actual driver, and actual server in a single check. Avoid logging URLs containing passwords or sensitive data.

## 7. Differences to Test When Upgrading the Driver

Upgrading from Connector/J 5.1 to 8.x, 9.x, or 26.x is not just changing the artifact name. Changes may affect:

- Driver class name and package.
- Connection property names or default values.
- Authentication plugin handling.
- TLS, certificates, and hostname verification.
- Timezone, DATE, TIME, TIMESTAMP, and java.time mappings.
- MySQL data type to Java type mappings.
- Server-side prepared statements and client-side prepared statements.
- Metadata, warnings, exceptions, and SQLState.
- Connection pool behavior when detecting invalid connections.

### Authentication

Modern MySQL typically uses caching_sha2_password as the default authentication plugin. Choose a driver new enough to support the server's authentication mechanism; verify application accounts and how credentials are exchanged in TLS-enabled environments.

Do not resolve authentication errors by arbitrarily downgrading database account plugins in production. First identify the driver, server, account plugin, and actual error message.

### TLS

Production connections should verify the server certificate and hostname. With Connector/J, you can configure sslMode=VERIFY_IDENTITY along with an appropriate trust store:

~~~text
jdbc:mysql://db.example.com:3306/app?sslMode=VERIFY_IDENTITY
~~~

The certificate must be issued for the hostname the application uses to connect, and the CA chain must be trusted by the runtime. If using older Java 8, check the JSSE provider and update version; Oracle Java 8 prior to 8u261 supports up to TLS 1.2 according to Connector/J documentation, whereas 8u261 and later support TLS 1.3.

Do not use sslMode=DISABLED as a quick fix for certificate errors in production. Fix the trust chain, hostname, or TLS configuration instead.

### Timezone and Temporal Types

Changing driver versions can expose legacy assumptions about timezones. Check:

- serverTimezone in legacy configurations and supported replacement properties in the version in use.
- connectionTimeZone and how the driver synchronizes session timezones.
- Java types used for DATE, TIME, DATETIME, and TIMESTAMP.
- Behavior during daylight saving time transitions on timezone-aware systems.

Write round-trip tests: insert representative temporal values, read them back, and compare instants or local date-times according to column semantics. Do not check display strings alone.

## 8. Choosing the Driver in Spring, Hibernate, and Connection Pools

Frameworks do not replace Connector/J. Spring JDBC, Hibernate, MyBatis, or HikariCP still need a JDBC driver to connect to MySQL.

When using Spring Boot:

- Identify which starter or BOM manages the driver version.
- Check the dependency tree to avoid duplicate drivers or overridden versions.
- Configure the URL, username, password, and TLS in secret/configuration management.
- Use the framework-managed DataSource/connection pool; do not create a new DriverManager connection per request in a web application.

When using Hibernate:

- Verify that the Hibernate version supports the project's Java and JDBC APIs.
- Use the dialect matching the Hibernate version; do not assume the driver selects the right dialect in every version.
- Test data type mappings, generated keys, batch updates, and transactions.

When using HikariCP or another pool:

- Check validation and timeouts.
- Check connection lifetime, idle timeout, and server wait timeout.
- Confirm that broken connections are evicted from the pool.
- Measure connection acquisition time, new connection creation time, and query execution time.

## 9. Test Matrix Before Selecting a Version

Build a minimal matrix covering these axes:

| Axis | Values to include in testing |
|---|---|
| Java runtime | Minimum Java version and production version |
| Connector/J | Current version and target upgrade version |
| MySQL Server | Production, staging, and next planned server upgrade version |
| JDBC/framework | JDBC level and Spring/Hibernate/MyBatis versions |
| Authentication | Application account plugin |
| TLS | CA, hostname, TLS protocol, and trust store |
| Connection pool | HikariCP or active pool, timeouts, and validation |
| Data | Unicode, decimal, binary, JSON, and temporal types |

Test cases should include:

1. Opening a new connection and verifying server identity via TLS.
2. Logging in using the production authentication plugin.
3. Running SELECT, INSERT, UPDATE, DELETE, and PreparedStatement with bound parameters.
4. Committing and rolling back transactions.
5. Retrieving generated keys and reading metadata.
6. Reading/writing Unicode, DECIMAL, BLOB, JSON, and temporal values.
7. Verifying batch updates and updated row counts.
8. Testing connection pool behavior during server restarts or network interruptions.
9. Verifying timeouts, retries, and exception mapping.
10. Running integration tests against the exact target MySQL Server version.

Do not test only a successful connection. A driver might connect successfully yet still have differences in timezones, prepared statements, data types, or pooling that cause application failures under real workloads.

## 10. Connector/J Upgrade Procedure

**Step 1 — Record the baseline**

Collect the current Java, Connector/J, MySQL Server, JDBC API, framework, connection pool, URL properties, and authentication plugin versions. Save the dependency tree to know which JARs are packaged.

**Step 2 — Read release notes**

Read the compatibility matrix and release notes from the current version through the target version. Focus on changed connection properties, default behaviors, authentication, TLS, timezones, and fixed bugs.

**Step 3 — Upgrade in a test environment**

Change only the driver version in dependency management. Run integration tests on the same Java runtime and server version as production. Do not upgrade Java, framework, server, and driver simultaneously without a plan to isolate root causes on failure.

**Step 4 — Verify the runtime artifact**

Inspect the dependency tree, packaged JAR contents, and JDBC metadata while the application is running. Confirm no old driver is being loaded from the application server's lib directory or the container base image.

**Step 5 — Controlled rollout**

Roll out to a small group of instances, monitoring connection errors, authentication, SQL exceptions, latency, and pool saturation. Keep the old artifact version and a tested rollback plan ready.

**Step 6 — Finalize**

Once metrics stabilize, update version documentation, dependency locks, and build pipelines. Remove old JARs from deployment environments to prevent accidental loading.

## 11. Troubleshooting Common Compatibility Errors

### No suitable driver

The driver was not found or the URL was not recognized by the driver. Check runtime dependencies, classpath, excluded artifacts, and the jdbc:mysql: URL prefix.

### ClassNotFoundException: com.mysql.cj.jdbc.Driver

The JAR is not in the active classloader, the dependency was not packaged, or the application is loading from a different classloader. Inspect the runtime artifact instead of just checking dependencies in the IDE.

### SQLFeatureNotSupportedException

The application or framework called a JDBC method not implemented by the driver. Cross-check the driver's actual JDBC level and determine whether a compatible API can be used or a driver upgrade is needed.

### Authentication errors

Check the user's authentication plugin, Connector/J version, TLS, and account privileges. Do not alter the server authentication mechanism before identifying the root cause.

### TLS or certificate errors

Check the hostname on the certificate, trust store, CA chain, Java/JSSE version, and sslMode. Avoid disabling identity verification to bypass errors.

### Timezone errors or shifted temporal data

Check the server timezone, session timezone, driver configuration, and Java types used for reading/writing. Create round-trip tests with representative instants and local date-times.

### Application runs but uses the wrong driver version

Check DatabaseMetaData.getDriverVersion(), the dependency tree, the application server library directory, and the JARs packaged inside the application.

## 12. Connector/J Selection Checklist

- [ ] Identified the actual Java runtime version of the application.
- [ ] Distinguished the build JDK from the execution JRE/runtime.
- [ ] Identified the JDBC API level required by the framework or application.
- [ ] Cross-checked Connector/J against the exact MySQL Server version.
- [ ] Read the compatibility matrix and release notes for the driver branch.
- [ ] Selected a specific driver version and pinned the dependency.
- [ ] Only one Connector/J version exists at runtime.
- [ ] Verified the driver at runtime via DatabaseMetaData.
- [ ] Tested authentication and TLS with production settings.
- [ ] Tested timezones, data types, transactions, and prepared statements.
- [ ] Executed integration tests against the exact target server version.
- [ ] Prepared a tested driver rollback plan.

## References

- [MySQL Connector/J Developer Guide — Overview](https://dev.mysql.com/doc/connector-j/en/connector-j-overview.html)
- [MySQL Connector/J — Compatibility with MySQL and Java Versions](https://dev.mysql.com/doc/connector-j/en/connector-j-versions.html)
- [MySQL Connector/J — Installing Using Maven](https://dev.mysql.com/doc/connector-j/en/connector-j-installing-maven.html)
- [MySQL Connector/J — Driver/Datasource Class Name](https://dev.mysql.com/doc/connector-j/en/connector-j-reference-driver-name.html)
- [MySQL Connector/J 26.10 Release Notes](https://dev.mysql.com/doc/relnotes/connector-j/en/news-26-10-0.html)
- [MySQL Connector/J 9.7 Release Notes](https://dev.mysql.com/doc/relnotes/connector-j/en/news-9-7-0.html)

## Conclusion

Choosing Connector/J is a compatibility problem across the Java runtime, JDBC API, MySQL Server, and application framework. Connector/J 26.10.0 is the current GA release series at the time of writing and implements JDBC 4.2; the 9.7.0 series has release notes documenting support for MySQL Server 8.0 and higher. Read the matrix for the exact branch, verify discrepancies between overview descriptions and compatibility tables when present, pin dependencies, and verify the actual driver at runtime. A successful connection is only the first step; testing authentication, TLS, timezones, data types, transactions, and connection pooling is what proves the driver fits the application.

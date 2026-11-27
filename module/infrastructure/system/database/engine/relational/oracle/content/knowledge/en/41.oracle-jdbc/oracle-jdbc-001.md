# Choosing an Oracle JDBC Driver by JDK and Database Compatibility Matrix

When a Java application connects to Oracle Database, choosing a JDBC driver requires considering three factors simultaneously:

1. **Application JDK**: the driver JAR must be able to run on the deployed Java runtime.
2. **Oracle Database version**: the driver/database combination must be in the compatibility matrix or certified by Oracle for that specific release.
3. **Features and support policy**: the JDBC API level, Thin/OCI, UCP, TLS/wallet, Oracle data types, and support lifetime must fit the application.

File names such as ojdbc8.jar, ojdbc11.jar, or ojdbc17.jar primarily indicate the JAR line corresponding to the compiled/supported Java level. The number in the file name is **not** the Oracle Database version and does not directly indicate the driver release. For example, a 26ai driver release can provide ojdbc8.jar, ojdbc11.jar, and ojdbc17.jar to serve different JDKs.

Oracle recommends using the latest JDBC driver release that supports the JDK and database your application uses, while aligning with your organization's support requirements. Do not choose a driver simply by looking at the database version or copying a JAR from another application.

## 1. Where does the JDBC driver sit in the connection architecture?

JDBC is Java's standard API for database access. Applications call interfaces in java.sql and javax.sql; the JDBC driver implements those interfaces to communicate with Oracle Database.

Typical JDBC Thin connection flow:

~~~text
Java application
      |
      v
JDBC API (java.sql / javax.sql)
      |
      v
Oracle JDBC driver (ojdbcX.jar)
      |
      v
Oracle Net over TCP/IP or TCPS
      |
      v
Listener / database service
      |
      v
Oracle Database
~~~

The JDBC driver is responsible for translating JDBC calls into the protocol and messages that Oracle Database understands. The driver also handles data type mapping, bind variables, transactions, metadata, statements, result sets, and Oracle-specific extensions.

### 1.1. Three independent versions to distinguish

- **JDK version**: the Java runtime/compiler used by the application, for example JDK 8, 11, 17, 21, or 25.
- **JDBC specification version**: the API standard implemented by the driver, for example JDBC 4.2 or JDBC 4.3.
- **Oracle JDBC driver release**: the release line of the driver, for example 19c, 21c, 23ai/26ai.

For example, ojdbc17.jar belongs to the JAR line for JDK 17 and above according to release-specific certification. It can implement JDBC 4.3 and connect to multiple database versions according to the compatibility matrix. It does not mean it only connects to Oracle Database 17.

### 1.2. A driver does not replace database features

A newer driver can connect to an older database if the combination is supported, but it cannot create features that the database server lacks. For example, a data type or SQL feature introduced only in a newer database release will not automatically appear on an older database just because the application uses a newer JDBC driver.

Similarly, a successful connection does not prove that every specific feature, authentication method, data type, or HA feature is certified for that combination.

## 2. Driver selection workflow

Follow this order to narrow down your selection:

1. Identify the actual JDK of the application's runtime process, not just the JDK on the development machine.
2. Select the Oracle JDBC JARs certified with that JDK.
3. Cross-check the driver release against the Oracle Database version in the interoperability/certification matrix.
4. Check the JDBC API level and features the application needs to use.
5. Choose Thin or OCI based on connection requirements.
6. Select the required artifacts and companion JARs for pooling, TLS/wallet, NLS, or HA.
7. Pin the version in Maven/Gradle and inspect the dependency tree to eliminate duplicate JARs.
8. Test on the exact JDK, database release, service, authentication, and deployment environment.
9. Record the driver version, database version, JDK version, and test results for future upgrades.

Do not infer compatibility solely from a successful compilation. The compiler may find the classes and methods, yet the runtime, database protocol, or server features can still be incompatible.

## 3. Common Oracle JDBC JARs by JDK

The following table describes choices in the current Oracle JDBC 26ai line at the time of writing. Certification can change with quarterly releases; always check the exact release notes of the artifact to be deployed.

| Application runtime JDK | JAR to consider | JDBC API | Notes |
| --- | --- | --- | --- |
| JDK 8 | ojdbc8.jar | JDBC 4.2 | Choice for applications still running Java 8 |
| JDK 11 | ojdbc11.jar | JDBC 4.3 | Suitable when JDBC 4.3 is needed; ojdbc8 can also run but only provides JDBC 4.2 |
| JDK 17 | ojdbc17.jar | JDBC 4.3 | Default choice for new Java 17 applications |
| JDK 19 | ojdbc17.jar | JDBC 4.3 | Listed in the certification of the current driver line |
| JDK 21 | ojdbc17.jar or ojdbc11.jar | JDBC 4.3 | Choose based on API baseline and release-specific certification |
| JDK 25 | ojdbc17.jar | JDBC 4.3 | The 26ai download page currently lists JDK 25; check release notes and companion artifact limitations |

Specific details currently listed on the Oracle JDBC 26ai download page:
- ojdbc17.jar: JDBC 4.3; certified for JDK 17, 19, 21, and 25; compatible with Jakarta APIs.
- ojdbc11.jar: JDBC 4.3; certified for JDK 11 and 21.
- ojdbc8.jar: JDBC 4.2; certified for JDK 8 and 11.

The Oracle JDBC Developer's Guide 26ai also lists ojdbc17 for JDK 17/19/21, ojdbc11 for JDK 11, and ojdbc8 for JDK 8/11. The tables in the Developer's Guide and the Downloads page are not completely aligned regarding JDK 21/25. Therefore, for JDK 21 or 25, verify the release notes of the exact downloaded JAR; do not apply an old table to every quarterly release.

### 3.1. ojdbc8.jar

Use when:
- The application must run on JDK 8.
- JDBC 4.2 is required.
- The framework or application server cannot yet be upgraded to a newer JDK.
- The selected driver release is certified with the database server in use.

ojdbc8.jar can run on JDK 11 in certified combinations, but it still implements JDBC 4.2. If the application needs JDBC 4.3 APIs, choose a more suitable JAR such as ojdbc11 or ojdbc17.

### 3.2. ojdbc11.jar

Use when:
- The application runs on JDK 11.
- JDBC 4.3 is required.
- You want a JDK 11 baseline driver across JDKs certified by the release.

Some quarterly releases certify ojdbc11 with JDK 21. Do not assume every older ojdbc11 release runs or is supported on JDK 21; check the exact release.

### 3.3. ojdbc17.jar

Use when:
- The application runs JDK 17 or higher within the certified JDK range.
- JDBC 4.3 is required.
- You want a newer driver with supported Jakarta API integrations.
- The application is upgrading to JDK 17, 21, or 25.

The name ojdbc17 indicates the JAR line compiled for the Java 17 baseline, not that it only runs on exactly JDK 17. Newer JDKs are supported when Oracle certifies them for the corresponding release.

### 3.4. ojdbc10.jar and older JARs

ojdbc10.jar belongs to the Oracle JDBC 19c line and should only be considered when maintaining a legacy system with specific constraints. Oracle documentation lists ojdbc10 for JDK 11 and 17 in the 19c line. For new applications, prefer the current JAR line corresponding to your JDK rather than picking ojdbc10 just because the name has the number 10.

JARs such as ojdbc6.jar, ojdbc7.jar, and ojdbc5.jar belong to older Java generations. If an application still depends on them, plan to upgrade the JDK, driver, and database; do not use legacy JARs for a new project.

## 4. JDBC driver and Oracle Database compatibility matrix

Driver/database compatibility is a separate check from driver/JDK compatibility. After choosing a JAR that runs on your JDK, you still must check whether the driver release is certified with the database release.

### 4.1. Matrix in Oracle JDBC Developer's Guide 26ai

Oracle JDBC Developer's Guide 26ai publishes the following interoperability matrix:

| JDBC driver release | Database 26.x | Database 21.x | Database 19.x |
| --- | --- | --- | --- |
| JDBC 26 | Yes | Yes | Yes |
| JDBC 21.x | Yes | Yes | Yes |
| JDBC 19.x | Yes | Yes | Yes |

This matrix shows the combinations listed by Oracle in the 26ai documentation. The driver release does not have to match the database release number.

### 4.2. Special note on Oracle Database 23ai

The Oracle JDBC Downloads page for the 26ai package currently states that driver release 26ai supports Oracle Database 26ai, 23ai, 21c, and 19c. Meanwhile, the interoperability table in Developer's Guide 26ai only lists 26.x, 21.x, and 19.x, without a 23.x column.

For database 23ai, check the JDBC-UCP Release Notes of the exact 26ai package and verify the specific combination before moving to production. Do not assume it is unsupported merely because one table omits it, nor ignore the discrepancy between the two documentation pages.

The Oracle JDBC FAQ has a separate matrix for the 23.x driver line:

| JDBC driver release | Database 23.x | Database 21.x | Database 19.x | Database 18.3 | Database 12.2/12.1 |
| --- | --- | --- | --- | --- | --- |
| JDBC 23.x | Yes | Yes | Yes | No | No |
| JDBC 21.x | Yes | Yes | Yes | Was | Was |
| JDBC 19.x | Yes | Yes | Yes | Was | Was |
| JDBC 18.x | No | Was | Was | Was | Was |
| JDBC 12.2/12.1 | No | Was | Was | Was | Was |

In the FAQ, the status Was means the combination was previously supported but is no longer covered by the corresponding Oracle support levels; it must not be interpreted as current support certification. For older databases such as 18c, 12c, or 11g, check support policies and historical matrices before retaining an old driver.

### 4.3. Why shouldn't you only pick a driver with the same number as the database?

For example:
- Oracle Database 19c can use a newer driver release if the combination is certified.
- Oracle Database 26ai can use JDBC 21.x or 19.x according to the published 26ai matrix.
- An application running JDK 8 still needs a JAR that supports JDK 8, even when the database is 26ai.

Choose based on the matrix and JDK, not on rules like "19c must use ojdbc19" or "database 21c must use ojdbc21".

### 4.4. Compatibility does not equal support lifetime

A driver/database pair may be able to connect, yet the database release or driver release has reached the end of its support window. When planning for production, verify separately:
- Whether the driver release is in an actively supported Oracle line.
- Whether the database release still has Premier/Extended Support or appropriate coverage.
- Whether new quarterly security/bug fixes are available.
- Whether the organization requires certification from Oracle Support or the application vendor.

Do not use a passing smoke test as a substitute for support/certification policy.

## 5. Choosing Thin or OCI driver

Oracle provides multiple JDBC driver types. For typical Java client applications, Oracle recommends JDBC Thin unless there is a specific requirement that only OCI satisfies.

### 5.1. JDBC Thin (Type 4)

Characteristics:
- Pure Java.
- No need to install Oracle Client on the application host.
- Uses Oracle Net over TCP/IP or TCPS.
- Easy to package in applications, containers, and cloud runtimes.
- Highly portable across Linux, Windows, and supported JVM platforms.

Example URL:

~~~java
String url = "jdbc:oracle:thin:@//dbhost.example.com:1521/app_service";
~~~

The Thin driver requires a TCP/IP listener on the database side and a valid service name.

### 5.2. JDBC OCI (Type 2)

The OCI driver calls the Oracle Call Interface via native libraries. It requires:
- A compatible Oracle Client or Instant Client.
- Native OCI libraries matching the platform and architecture.
- A properly configured library path.
- A client/library version compatible with the operating system.

Choose OCI only when the application genuinely needs OCI-specific capabilities, such as an existing Oracle Client environment or an adapter/protocol not supported by Thin. OCI complicates deployment due to native library dependencies.

Oracle has published deprecation notices related to the JDBC-OCI/Type 2 driver in support documentation. Before starting a new project using OCI, check MOS note 2953282.1 and the current support policy.

### 5.3. Comparison

| Criterion | Thin | OCI |
| --- | --- | --- |
| Driver type | Type 4, pure Java | Type 2, Java + native code |
| Oracle Client on client host | Not required | Required |
| TCP/IP and TCPS | Yes | Yes |
| OS/native library dependency | Low | High |
| Portability/container | Favorable | Requires packaging native client |
| Default choice | Recommended by Oracle | Only when OCI-specific requirements exist |

## 6. Choosing dependencies from Maven Central

Oracle publishes JDBC artifacts on Maven Central. The commonly used Group ID is com.oracle.database.jdbc. You should pin a specific version and use the same release line for the driver, UCP, and companion artifacts.

### 6.1. Minimal Maven dependency

Example for a JDK 17 application using ojdbc17. Version 23.26.4.0.0 is a 26ai JDBC release listed on Maven Central at the time of writing; check for the latest version before deploying:

~~~xml
<dependency>
    <groupId>com.oracle.database.jdbc</groupId>
    <artifactId>ojdbc17</artifactId>
    <version>23.26.4.0.0</version>
</dependency>
~~~

For JDK 11, choose artifact ojdbc11. For JDK 8, choose ojdbc8. Do not add multiple driver artifacts simultaneously to the runtime classpath without a specific reason.

### 6.2. Maven with production companion dependencies

Oracle provides production POM artifacts to pull in the JDBC driver and the companion JARs needed for defined use cases:

~~~xml
<dependency>
    <groupId>com.oracle.database.jdbc</groupId>
    <artifactId>ojdbc17-production</artifactId>
    <version>23.26.4.0.0</version>
    <type>pom</type>
</dependency>
~~~

Use the production POM when the application needs the companion artifacts specified by Oracle. If you only use basic JDBC Thin, the main ojdbc JAR may already suffice; do not add libraries just because they appear in a full archive bundle.

### 6.3. Maven with UCP

If using Oracle Universal Connection Pool together with ojdbc17:

~~~xml
<dependencies>
    <dependency>
        <groupId>com.oracle.database.jdbc</groupId>
        <artifactId>ojdbc17</artifactId>
        <version>23.26.4.0.0</version>
    </dependency>

    <dependency>
        <groupId>com.oracle.database.jdbc</groupId>
        <artifactId>ucp17</artifactId>
        <version>23.26.4.0.0</version>
    </dependency>
</dependencies>
~~~

Choose the UCP artifact matching the JDK/driver line: ucp17 pairs with ojdbc17, ucp11 pairs with ojdbc11, and ucp.jar with the corresponding ojdbc8 line. Check the release notes of the same version to confirm JDK certification.

### 6.4. Checking the dependency tree

Maven:

~~~bash
mvn dependency:tree -Dincludes=com.oracle.database.jdbc
~~~

Look for cases such as:
- Two ojdbc versions appearing together.
- A framework pulling in an old driver transitively.
- UCP not belonging to the same release family as ojdbc.
- Duplicate companion JAR versions.
- A dependency bundling ojdbc inside a shaded/fat JAR while the application also declares ojdbc.

Keep a single explicit driver version at runtime. If a third-party library declares another driver, handle it with controlled dependency mediation or exclusions.

## 7. Gradle dependencies

Example for a JDK 17 application:

~~~groovy
dependencies {
    implementation("com.oracle.database.jdbc:ojdbc17:23.26.4.0.0")
}
~~~

Add UCP when needed:

~~~groovy
dependencies {
    implementation("com.oracle.database.jdbc:ojdbc17:23.26.4.0.0")
    implementation("com.oracle.database.jdbc:ucp17:23.26.4.0.0")
}
~~~

Inspect runtime dependencies:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Inspect why a version was selected:

~~~bash
./gradlew dependencyInsight \
    --dependency ojdbc \
    --configuration runtimeClasspath
~~~

Ensure the Gradle toolchain, compiler, and application runtime use the exact JDK of the deployment environment. The build machine might use JDK 21 while the production container runs JDK 17; verify both.

## 8. Companion JARs and when you need them

The ojdbc JAR provides the core driver. Certain features require additional companion libraries.

| Artifact | Typical purpose |
| --- | --- |
| ucp17/ucp11/ucp | Oracle Universal Connection Pool |
| orai18n | Globalization/NLS support for cases requiring additional coverage |
| oraclepki | Oracle PKI/wallet support in applicable configurations |
| osdt_core, osdt_cert | Oracle security components used with certain wallet/certificate setups |
| ons | Oracle Notification Service for applicable HA features |
| simplefan | Fast Application Notification integration |
| xdb, xmlparserv2 | Certain XML/Oracle XML DB functions |
| rsi | Reactive Streams Ingestion for applicable ingest workloads |

Not every application needs all companion JARs. Identify the features you need, then add the exact artifacts per the Oracle Maven Central Guide and that feature's documentation.

### 8.1. Wallet and TLS

If connecting over TCPS or using Oracle Wallet, you may need the corresponding security companion libraries and wallet/truststore configuration. Do not copy a random set of security JARs from an old Oracle Home into a new application; use the exact artifact/version set supported by the documentation.

### 8.2. NLS and international data

Applications storing Vietnamese text with diacritics or Unicode data typically use the Thin driver with built-in Unicode support. Certain Oracle object/collection types and specialized character sets may require orai18n. Determine actual needs and check the NLS documentation for your driver release.

### 8.3. UCP is not a JDBC driver

UCP is a connection pool. It manages the lifecycle and reuse of connections; ojdbc remains the driver that communicates with the database. Installing UCP does not replace ojdbc.

## 9. Identifying the actual JDK

A common mistake is choosing a driver based on the JDK installed on a laptop while the production application runs on a different JDK.

### 9.1. Checking the Java runtime

~~~bash
java -version
~~~

Check the compiler:

~~~bash
javac -version
~~~

Check which JDK Maven is using:

~~~bash
mvn -version
~~~

For Gradle:

~~~bash
./gradlew -version
~~~

These commands help identify the toolchain, but the production environment still needs to be verified separately. You can log the version at application startup:

~~~java
System.out.println("Runtime Java: " + Runtime.version());
~~~

### 9.2. Build JDK and runtime JDK

Maven/Gradle can compile with one JDK while packaging an application that runs on another JDK. The driver must be compatible with the final runtime JVM, not just the compiler.

For example:
- Compiled with JDK 21.
- Production container runs JDK 17.
- If the driver requires JDK 21 bytecode, the application will fail when running on JDK 17.

Conversely, a JDK 17 baseline driver can run on a newer JDK if Oracle certifies that release.

### 9.3. Java bytecode version

A JDK cannot read class files compiled for a newer Java release. A common error is UnsupportedClassVersionError. This is a sign to check the class version and runtime JDK, not a network/database error.

## 10. Identifying the Oracle Database version

Do not rely on service names or environment names like PROD/DEV to infer the database version.

You can ask the DBA or query:

~~~sql
SELECT banner
FROM v$version
ORDER BY banner;
~~~

Or from JDBC:

~~~java
DatabaseMetaData meta = connection.getMetaData();

System.out.println(meta.getDatabaseProductName());
System.out.println(meta.getDatabaseProductVersion());
~~~

In a multitenant environment, connect to the actual service/PDB that the application uses. The database home version, CDB/PDB compatibility, and service endpoint may be distinct details that need to be recorded.

### 10.1. Recording DB identity

In systems with multiple databases:
- DB_NAME and DB_UNIQUE_NAME.
- Database release and RU.
- Service name.
- CDB/PDB if applicable.
- Primary/standby role if using Data Guard.
- RAC/SCAN endpoint if applicable.

The compatibility matrix must be applied to the database server that actually receives the connections.

## 11. Identifying the JDBC driver version

Oracle documents that you can run the JAR directly to view its version:

~~~bash
java -jar ojdbc17.jar
~~~

Similarly:

~~~bash
java -jar ojdbc11.jar
java -jar ojdbc8.jar
~~~

In the application, read metadata:

~~~java
DatabaseMetaData meta = connection.getMetaData();

System.out.println("Driver name: " + meta.getDriverName());
System.out.println("Driver version: " + meta.getDriverVersion());
System.out.println("JDBC API: " +
    meta.getJDBCMajorVersion() + "." +
    meta.getJDBCMinorVersion());
System.out.println("Database: " + meta.getDatabaseProductVersion());
~~~

This is a useful way to verify which driver is actually loaded at runtime. It also helps detect an application server or container loading an old JAR from a shared library.

## 12. Minimal JDBC Thin connection check

A small smoke test should verify:
- The JDK runs properly.
- The driver is loaded.
- The URL/service is valid.
- Authentication works.
- Listener/network connectivity is clear.
- The database returns a result.

Example:

~~~java
import java.sql.Connection;
import java.sql.DatabaseMetaData;
import java.sql.DriverManager;
import java.sql.ResultSet;
import java.sql.Statement;

public class OracleJdbcSmokeTest {
    public static void main(String[] args) throws Exception {
        String url = System.getenv("DB_URL");
        String user = System.getenv("DB_USER");
        String password = System.getenv("DB_PASSWORD");

        try (Connection connection =
                 DriverManager.getConnection(url, user, password)) {

            DatabaseMetaData meta = connection.getMetaData();

            System.out.println("Driver: " + meta.getDriverName());
            System.out.println("Driver version: " + meta.getDriverVersion());
            System.out.println("Database: " +
                               meta.getDatabaseProductVersion());

            try (Statement statement = connection.createStatement();
                 ResultSet result =
                     statement.executeQuery("SELECT SYSDATE FROM DUAL")) {

                if (result.next()) {
                    System.out.println("Database time: " +
                                       result.getTimestamp(1));
                }
            }
        }
    }
}
~~~

JDBC 4 auto-registers the driver via the service provider mechanism when the JAR is properly on the classpath/module path. Modern applications usually do not need to call Class.forName("oracle.jdbc.OracleDriver") manually. Only use Class.forName if required by a legacy framework or environment.

### 12.1. URL using service name

Common format:

~~~text
jdbc:oracle:thin:@//hostname:1521/service_name
~~~

Example:

~~~text
jdbc:oracle:thin:@//dbhost.example.com:1521/salespdb.example.com
~~~

Prefer service names for environments with PDBs, RAC, or service routing. Old SID-style URLs may exist in legacy applications but should not be used instead of a service when the architecture requires service-level routing.

### 12.2. Do not hardcode passwords in source code

Use a secret manager, environment injection, or the platform's secure configuration. Do not commit DB_PASSWORD to repositories, Docker images, logs, or command history.

## 13. DataSource and connection pools in production

The driver is the component that creates connections; production applications should usually obtain connections through a DataSource and connection pool rather than opening a new TCP/database session per request.

### 13.1. OracleDataSource

Oracle provides OracleDataSource. Basic configuration example:

~~~java
import java.sql.Connection;
import oracle.jdbc.pool.OracleDataSource;

public class OracleDataSourceExample {
    public static void main(String[] args) throws Exception {
        OracleDataSource dataSource = new OracleDataSource();

        dataSource.setURL(
            "jdbc:oracle:thin:@//dbhost.example.com:1521/app_service"
        );
        dataSource.setUser(System.getenv("DB_USER"));
        dataSource.setPassword(System.getenv("DB_PASSWORD"));

        try (Connection connection = dataSource.getConnection()) {
            System.out.println(
                connection.getMetaData().getDatabaseProductVersion()
            );
        }
    }
}
~~~

This is a simple DataSource, not yet a pool. For production, use UCP or a pool suited to your framework.

### 13.2. UCP

UCP provides connection pooling and integrates Oracle HA features according to supported configurations. Choose the ucp artifact matching your JDK/driver line, and configure min/max pool size, timeouts, validation, and failover behavior according to your workload.

### 13.3. Third-party pools

HikariCP and other pools can also be used with Oracle JDBC Thin. In that case, only the ojdbc driver and the truly required companion artifacts are needed. Do not add UCP if the application does not use UCP.

### 13.4. A larger pool size is not always better

An oversized pool can increase sessions/processes, PGA usage, contention, and database load. Choose pool size based on concurrency, database capacity, transaction duration, and the number of application instances. Set connection timeout, idle timeout, max lifetime, and validation according to the pool's guidelines.

## 14. Frameworks and application servers

### 14.1. Spring Boot

Configuration example:

~~~properties
spring.datasource.url=jdbc:oracle:thin:@//dbhost.example.com:1521/app_service
spring.datasource.username=your_database_user
spring.datasource.password=inject_from_secret_store
spring.datasource.driver-class-name=oracle.jdbc.OracleDriver
~~~

Ensure the ojdbc dependency is on the application's runtime classpath. Spring Boot can automatically infer the driver from the URL in many configurations, but explicitly declaring the driver class makes verification easier in complex environments.

### 14.2. Jakarta EE / application servers

Application servers may manage the JDBC driver in a shared module and configure the DataSource at the server level. When deploying:
- Check which driver module the server is loading.
- Check whether the application also packages another ojdbc version.
- Check classloader isolation.
- Check the JNDI datasource and pool.
- Check transaction manager/XA driver requirements.

Do not assume a JAR inside a WAR/EAR will always take precedence over a JAR in a server module.

### 14.3. Containers and Kubernetes

With JDBC Thin:
- Package the JAR inside the application artifact.
- No Oracle Client native libraries are needed.
- Manage wallets/certificates via secure secrets/volumes if using TCPS.
- Size the connection pool appropriately for the replica count.
- Monitor total connections across all pods.
- Verify DNS, network policies, and listener/service routing.

If each pod creates a pool of up to 50 connections and there are 20 pods, the database can receive up to 1,000 connections from that service. Capacity planning must account for all replicas, not just a single JVM.

## 15. TLS, wallet, and authentication

JDK/driver compatibility alone is not enough to ensure secure connections work. You must check authentication and TLS feature support for both the driver and the database.

### 15.1. TCP and TCPS

- TCP is an Oracle Net connection unencrypted at the transport layer.
- TCPS uses TLS to encrypt and verify the server certificate.
- Mutual TLS (mTLS) may also require a client credential/wallet.

If the system requires TCPS, verify the TLS protocol, cipher suites, truststore/wallet, certificate expiry, hostname/DN validation, and network policy.

### 15.2. Oracle Wallet and companion JARs

Certain wallet/security configurations require artifacts such as oraclepki, osdt_core, and osdt_cert. Add the exact versions and configure them according to the Oracle JDBC documentation; do not put wallet private keys or passwords in source code.

### 15.3. Authentication protocols

A driver that is too old may not support a newer database authentication policy. If you encounter ORA-28040 or similar authentication errors:
- Check the JDBC driver version.
- Check the database authentication policy.
- Check password verifiers and account status.
- Read the alert log and client error details.
- Upgrade the driver according to the matrix before considering changes to security policy.

Do not downgrade the database authentication policy just to let an old client connect without a security assessment and approval.

## 16. JDBC API 4.2 and 4.3

The JDBC specification version indicates the standard API implemented by the driver. It is not the Oracle Database version.

### 16.1. JDBC 4.2

Some JARs such as ojdbc8.jar implement JDBC 4.2. Applications using APIs available since JDBC 4.2 can operate within the scope supported by the driver.

### 16.2. JDBC 4.3

ojdbc11 and ojdbc17 of the corresponding releases implement JDBC 4.3. If an application or framework needs JDBC 4.3 APIs, do not choose ojdbc8 just because the JDK runtime can load that JAR.

### 16.3. Standard APIs and Oracle extensions

Applications should prefer the standard java.sql/javax.sql APIs whenever sufficient. Oracle packages such as oracle.jdbc provide extensions for data types, performance, LOBs, object types, and HA. When using extensions, coupling to the driver release increases; check the Javadoc and compatibility notes.

### 16.4. Jakarta APIs

Oracle notes that ojdbc17 from the corresponding releases is compatible with Jakarta APIs. If an application uses Jakarta EE or libraries that migrated from javax to jakarta, verify which exact APIs are supported and the corresponding dependencies. Do not equate the driver's Jakarta API compatibility with being able to switch namespaces across the entire application without code changes.

## 17. Oracle-specific data types and features

When upgrading the driver, test the data types the application actually uses:
- NUMBER and precision/scale.
- DATE, TIMESTAMP, TIMESTAMP WITH TIME ZONE.
- CLOB/BLOB/NCLOB.
- RAW and binary data.
- ARRAY, STRUCT, REF CURSOR.
- XMLType or XML-related APIs.
- JSON types and JSON APIs according to database release.
- VECTOR or new data types in supported database releases.
- PL/SQL associative arrays and stored procedure binding.

A newer driver may expose APIs to represent new data types, but the database server must have the corresponding data type/feature. An older driver may connect but not know how to map a new data type using modern APIs.

### 17.1. Testing stored procedures

If the application uses CallableStatement, REF CURSOR, array binding, or PL/SQL object types, add tests for:
- IN, OUT, and IN OUT parameters.
- Null handling.
- Type mapping.
- Transaction behavior.
- LOB lifecycle.
- Cursor closing.
- Error propagation.

### 17.2. Testing Unicode and NLS

Test Vietnamese text with diacritics, supplementary characters, NCHAR/NVARCHAR2, CLOB/NCLOB, and the database character set. Ensure data is not corrupted by character set conversion during binding or reading ResultSets.

## 18. Common errors when selecting or loading a driver

| Error | Possible cause | How to check |
| --- | --- | --- |
| ClassNotFoundException: oracle.jdbc.OracleDriver | JAR missing from runtime classpath | Check dependency tree, WAR/EAR/container module |
| No suitable driver | Driver not loaded, wrong URL, or JAR not on classpath | Check jdbc:oracle:thin URL, service provider, and dependencies |
| UnsupportedClassVersionError | Driver or dependency compiled for a newer JDK than runtime | Check java -version and class-file baseline |
| NoSuchMethodError | Conflicting versions of driver/companion JARs | Check runtime dependencies and classloader |
| ORA-28040 | Incompatible authentication protocol/verifier | Check driver version and database security policy |
| ORA-12514 | Listener does not recognize service name | Check service registration, listener, and URL |
| ORA-12541 | No listener at host/port | Check network, listener, and port |
| ORA-12154 | Could not resolve connect identifier | Check TNS_ADMIN, tnsnames, or URL |
| ORA-01017 | Invalid username/password | Check credentials and account |
| ORA-17002 / I/O error | Network/socket interrupted | Check firewall, timeout, listener, and network |
| TLS handshake failure | Certificate, truststore, wallet, or TLS policy | Check certificate chain, hostname, protocol, and companion JARs |

### 18.1. ClassNotFoundException

Ensure the artifact is in the runtime package. With Maven, provided or test scope can prevent the driver from being packaged. With an application server, the driver might reside in a server module rather than the WAR.

### 18.2. No suitable driver

Check:
- Whether the URL starts with jdbc:oracle:thin:.
- Whether the Oracle driver is present at runtime or only at compile time.
- Whether the driver is discovered by the JDBC 4 service loader.
- Whether there is classloader isolation.
- Whether the URL has invalid characters/format.

### 18.3. NoSuchMethodError

This is usually a binary dependency conflict. For example, ojdbc17 and a companion JAR from an older version coexist on the classpath. Inspect the dependency tree and the actual list of JARs in the container.

### 18.4. ORA-28040

Do not resolve this by automatically lowering the authentication version. First verify the driver release, database authentication settings, and password verifiers. Upgrading the driver to a supported release is usually the logical first step.

## 19. Compatibility testing before production

A single successful connection is only a smoke test. Your test suite must verify the features and load that the real application uses.

### 19.1. Minimal test matrix

| Item | Check |
| --- | --- |
| JDK | Exact production runtime |
| Driver JAR | Version and JDBC API level |
| Database | Actual release/RU and service |
| Connection | Thin/OCI, TCP/TCPS |
| Authentication | Password, wallet, Kerberos, or method in use |
| Datatypes | NUMBER, DATE, TIMESTAMP, LOB, relevant JSON/object types |
| Transactions | Commit, rollback, isolation, and timeouts |
| Pool | Validation, timeout, leak detection, and reconnect |
| HA | RAC service, FAN, failover, or Data Guard if used by the app |
| Deployment | Classloader, container, application server |
| Performance | Batching, fetch size, LOB streaming, pool concurrency |
| Observability | Driver version, SQL exceptions, and connection metrics |

### 19.2. Testing on the exact runtime

Run smoke tests inside the exact container or application server that will be deployed. Testing on a laptop may use a different JDK, different ojdbc JAR, different TNS_ADMIN, different wallet, different network route, or different DNS.

Therefore, local results do not replace staging/pre-production testing.

### 19.3. Driver upgrade testing

Before replacing the JAR:
1. Record the current driver version.
2. Save the dependency tree.
3. Run integration tests on the old version.
4. Upgrade the driver in a separate branch.
5. Re-run data type, transaction, pool, and HA tests.
6. Measure latency/throughput with a representative workload.
7. Check logs and SQL exceptions.
8. Deploy to canary or staging.
9. Prepare a dependency rollback in case of regression.

## 20. Common driver selection scenarios

### 20.1. JDK 8, database 19c

- Choose ojdbc8.jar.
- Choose a driver release certified with JDK 8 and Database 19c.
- Check whether JDBC 4.2 meets application needs.
- If JDBC 4.3 is needed, you must upgrade the JDK and choose a compatible driver.

### 20.2. JDK 11, database 19c

- Prefer considering ojdbc11.jar if JDBC 4.3 is needed.
- ojdbc8.jar can also run on JDK 11 within the certified scope, but only provides JDBC 4.2.
- Verify database 19c and the quarterly driver release in the matrix.

### 20.3. JDK 17, database 19c or 21c

- Prefer ojdbc17.jar from the current driver line if the combination is certified.
- Check the Oracle-specific features used by the application.
- If the application server manages the driver, upgrade the shared module and remove duplicate JARs from the application.

### 20.4. JDK 21, database 19c or 21c

- Consider ojdbc17.jar from the current line.
- ojdbc11.jar may be an option in certified releases.
- Verify exact JDK 21 support in the JAR's download page/release notes.
- Do not infer from an older ojdbc11 that every quarterly release supports JDK 21.

### 20.5. JDK 25, database 26ai or 19c

- The Oracle JDBC Downloads page currently lists ojdbc17.jar from the 26ai package for JDK 25.
- Database 26ai and 19c are in the list of database versions supported by the 26ai JDBC package.
- Check the release notes for the exact artifact; the download page notes known issues in the JDK 25 certification of the companion RSI artifact.
- If the application uses RSI, evaluate the specific bug IDs mentioned in the release notes separately.

### 20.6. JDK 8, database 26ai

- Check ojdbc8.jar in the 26ai driver package because the download page lists JDK 8/11.
- Cross-check database 26ai in the interoperability matrix.
- Accept JDBC 4.2 and test the data types/features the application requires.
- If the application requires JDBC 4.3 APIs, upgrade the JDK instead of trying to use ojdbc8.

### 20.7. Database 23ai

- The 26ai JDBC download page states support for database 23ai.
- The Developer's Guide 26ai matrix does not have a 23.x column.
- The 23.x FAQ line has a separate matrix for JDBC 23.x.
- Verify the exact release notes and Oracle Support certification for the planned JDK/driver/database pair.

## 21. Managing multiple drivers in enterprise environments

Enterprise systems often run multiple applications on a single application server or cluster. Some errors arise from multiple driver versions coexisting.

### 21.1. One runtime should have one explicit driver version

If an application uses two ojdbc versions:
- The classloader may load the wrong class.
- Driver auto-registration may register multiple drivers.
- Metadata may report unexpected versions.
- A companion JAR may call an API that does not exist in the loaded version.

Place the driver in a managed location and define classloader precedence clearly.

### 21.2. Driver in server module vs. driver in WAR/EAR

The application server may provide the driver in a shared module. If the WAR also packages ojdbc, understand parent-first/child-first rules and isolation. Do not replace JARs directly in server directories without a change plan.

### 21.3. Driver in fat JARs

Spring Boot executable JARs or shaded JARs can bundle the driver. Inspect the contents of the final artifact, not just the POM. Dependency exclusions and shading can cause the runtime to differ from the expected dependency tree.

## 22. Driver upgrades and patching policy

Oracle JDBC is released in release/quarterly updates. Choosing the latest suitable release does not mean updating without testing.

Patching workflow:
- Monitor Oracle JDBC Downloads and release notes.
- Review bug fixes and known issues.
- Review security advisories and vulnerability scanning.
- Check the JDK/database matrix.
- Pin versions in the build.
- Do not use dynamic versions like latest or uncontrolled version ranges.
- Run integration/regression tests.
- Update the SBOM and license inventory.
- Record the driver version in startup logs.
- Have a rollback plan.

### 22.1. Database and driver versions have separate lifecycles

Database 19c has its own support lifecycle; JDBC driver 26ai has its own release lifecycle. Do not infer the driver's support lifetime solely from the database. Check the Oracle Lifetime Support Policy and JDBC FAQ for long-term planning.

### 22.2. Do not mix JARs from different quarterly releases

For example, ojdbc17 version 23.26.4.0.0 should not be paired with ucp17 or security companion JARs from an incompatible release unless instructed by Oracle. Use the same release family and follow dependency guidance.

## 23. Checking the driver in CI/CD

A pipeline can automatically verify the JDK, dependencies, and database integration.

Recommended steps:
1. Print the JDK version in the build log.
2. Save the runtime dependency tree.
3. Verify that only one Oracle JDBC driver version is resolved.
4. Verify artifact checksums or repository source.
5. Run unit tests that do not depend on the database.
6. Run integration tests against the target Oracle Database version.
7. Test TLS/wallet if used in production.
8. Test pool startup/reconnect.
9. Record driver/database/JDK versions in the test report.
10. Block release if the combination is outside the matrix or unapproved.

Do not expose database secrets in build logs. Use a secret store and ephemeral test credentials.

## 24. Pre-release application checklist

- [ ] Identified production runtime JDK.
- [ ] Identified Oracle Database release and RU.
- [ ] Checked driver/JDK certification.
- [ ] Checked driver/database interoperability matrix.
- [ ] Confirmed required JDBC API level.
- [ ] Chosen Thin or OCI based on requirements.
- [ ] Pinned artifact/version.
- [ ] No multiple ojdbc versions at runtime.
- [ ] UCP/companion JARs from the same release family if used.
- [ ] Verified URL/service name.
- [ ] Tested authentication and TLS/wallet.
- [ ] Tested data types and PL/SQL features used by the app.
- [ ] Tested connection pool, timeouts, and reconnect.
- [ ] Ran smoke test on the exact container/server.
- [ ] Recorded driver/database/JDK versions in logs.
- [ ] Checked release notes, known issues, and support policy.
- [ ] Prepared a rollback plan for the driver upgrade.

## 25. Official references

Compatibility tables change by release. When deploying, prioritize Oracle documentation for your exact driver version and database release, then confirm with Oracle Support if the combination falls outside public tables.

1. **Oracle JDBC Developer's Guide 26ai — Getting Started, Version Compatibility**  
   https://docs.oracle.com/en/database/oracle/oracle-database/26/jjdbc/JDBC-getting-started.html

2. **Oracle JDBC Developer's Guide 26ai — Introducing JDBC, Choosing the Appropriate Driver**  
   https://docs.oracle.com/en/database/oracle/oracle-database/26/jjdbc/introducing-JDBC.html

3. **Oracle JDBC and UCP Downloads** — driver JAR, JDK certification, database versions, release notes, and companion archives  
   https://www.oracle.com/database/technologies/appdev/jdbc-downloads.html

4. **Oracle JDBC FAQ** — interoperability matrix, JDK/JAR guidance, and release-specific questions  
   https://www.oracle.com/database/technologies/faq-jdbc.html

5. **Oracle Maven Central Developer's Guide** — group ID, artifacts, BOM, and production dependencies  
   https://www.oracle.com/database/technologies/maven-central-guide.html

6. **Maven Central — Oracle ojdbc17 artifact**  
   https://central.sonatype.com/artifact/com.oracle.database.jdbc/ojdbc17

Information regarding the 26ai driver/JDK/database matrix in this article was cross-checked on 2026-11-14. Version 23.26.4.0.0 is an example dependency listed on Maven Central at that time; check for newer releases before creating a production build.

## 26. Self-study exercises

1. Distinguish between JDK version, JDBC specification version, and Oracle JDBC driver release.
2. Why does ojdbc17.jar not mean it only connects to Oracle Database 17?
3. State the three factors to check before choosing a driver.
4. Which JAR should you consider starting with for JDK 8?
5. Which JAR should you choose for JDK 11 needing JDBC 4.3?
6. Distinguish between ojdbc8 and ojdbc11 regarding the JDBC API.
7. Why can ojdbc17 run on JDKs newer than JDK 17?
8. When should you consider ojdbc10?
9. Explain the driver/database interoperability matrix.
10. Why doesn't the driver release need to match the database release number?
11. Which database releases does the JDBC 26ai matrix publish in the Developer's Guide?
12. Why is it necessary to double-check database 23ai separately when Oracle pages list it differently?
13. What does the status Was mean in the FAQ?
14. Distinguish between driver compatibility and the Oracle product support lifecycle.
15. Compare JDBC Thin and JDBC OCI.
16. Why is Thin suitable for containers?
17. When are Oracle Client native libraries needed?
18. Write the Maven dependency for ojdbc17.
19. Write the Gradle dependency for ojdbc17.
20. Why should two ojdbc versions not be packaged in the same runtime?
21. How does UCP differ from a JDBC driver?
22. State the roles of orai18n and oraclepki.
23. Write commands to check the JDK and Maven runtime.
24. Write a command to check the version of an ojdbc JAR.
25. Use DatabaseMetaData to print the driver and database versions.
26. Write a JDBC Thin URL using a service name.
27. Explain the UnsupportedClassVersionError error.
28. Analyze the causes of No suitable driver and NoSuchMethodError.
29. Design a test plan for upgrading ojdbc in a Spring Boot application.
30. Build a test matrix covering JDK, driver, database, TLS, data types, UCP, and application server for a production system.

**Choosing an Oracle JDBC driver is an intersection problem between the JDK runtime, driver release, database release, and application features.** Identify the JDK actually running the application, select a JAR certified for that JDK, verify the interoperability matrix with the database, and only then finalize dependencies and companion artifacts. Prefer Thin for typical Java applications, pin a single explicit driver version, test on the exact deployment environment, and read the release notes before every upgrade.

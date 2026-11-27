# Reading the Java, Spring Boot, Spring Data, and Hibernate Compatibility Matrix

## Objective

A Spring Data JPA application does not just have four versions that need to match. It is a set of interdependent components: JDK, Spring Boot, Spring Framework, Spring Data JPA, Jakarta Persistence API, Hibernate ORM, JDBC driver, database engine, and build tool. A version may be supported by Spring Boot yet not necessarily supported by a third-party library in the dependency graph on the same JDK.

Reading the compatibility matrix helps answer three questions:

1. Does this set of versions fall within the published support range of each component?
2. Which exact versions is dependency management selecting at build time?
3. Does the resolved set of versions work together in the application, tests, CI, and production environment?

The key rule is to **take the intersection of all requirements**, not just look at a single Spring Boot row. The Spring Boot BOM is a good starting point because it manages a set of dependencies that have been tested together. Even then, you still must verify the JDK, Hibernate, database driver, database, and any overridden libraries.

This lesson explains how to read each layer, how to use the BOM, how to detect conflicts, an example of the official matrix as of 2026-11-09, and a small Maven project to inspect the actual dependency graph.

## 1. The compatibility matrix is not a single table

Each project publishes its own type of constraints:

- Spring Boot publishes minimum/maximum JDK versions, minimum Spring Framework versions, and supported build tools.
- The Spring Boot BOM publishes the dependency versions managed by Boot, including Spring Data JPA, Hibernate ORM, and Jakarta Persistence API.
- Spring Data publishes its release train BOM and its requirements for Spring Framework.
- Hibernate publishes compatible Java versions, Jakarta Persistence versions, database integrations, and Spring Boot platforms.
- The JDBC driver publishes supported JDK and database versions.
- The database vendor publishes compatible server versions, protocols, and drivers.

A simple comparison like "Spring Boot 3 means Hibernate 6" is not enough. You need to check both the specific versions and the support range of each project.

A valid configuration must simultaneously satisfy:

~~~text
JDK supported by Spring Boot
AND JDK supported by Hibernate
AND Spring Framework within the range required by Spring Data
AND Spring Data JPA within the corresponding dependency set
AND Jakarta Persistence API matching Hibernate
AND JDBC driver supporting the JDK and database server
AND build tool supporting the Spring Boot version
~~~

A matrix only tells you published compatibility. It does not replace integration tests against a real database, nor does it by itself prove that the application has no runtime errors.

## 2. Understanding the role of each component

| Component | Role | Questions to check |
| --- | --- | --- |
| JDK | Compiles and runs the Java application | Which Java versions are supported by the framework and libraries? |
| Spring Boot | Application platform and dependency management | Which Boot release fits the JDK and Spring Framework? |
| Spring Framework | Core container, transactions, web, and integration | Which Framework generation does Spring Data require? |
| Spring Data JPA | Repository abstraction and JPA integration | Which module version belongs to the corresponding release train/BOM? |
| Jakarta Persistence | Standard ORM API | Which JPA API generation does the Hibernate implementation support? |
| Hibernate ORM | JPA provider and ORM engine | Which Hibernate version is compatible with the JDK, JPA, and Boot? |
| JDBC driver | Java connection to the database | Which JDK and database server versions does the driver support? |
| Database engine | Executes SQL and stores data | Are dialect, data types, locking, and SQL features supported? |
| Maven/Gradle | Dependency resolution and build | Is the build tool version within Boot's requirements? |

### Spring Data JPA and Hibernate are not the same library

Spring Data JPA provides repository abstractions such as JpaRepository, derived queries, Specifications, and repository composition. Hibernate ORM is a JPA provider that implements the persistence API and executes SQL.

Therefore, the dependency graph typically includes both:

~~~text
Application
  └── spring-boot-starter-data-jpa
        ├── spring-data-jpa
        ├── spring-orm
        ├── jakarta.persistence-api
        └── hibernate-core
~~~

The version number of Spring Data JPA does not need to match Hibernate's. The two projects release independently; the Boot BOM selects compatible versions for a release line.

### Jakarta Persistence is the contract layer

Spring Data JPA calls the Jakarta Persistence API; Hibernate implements that API. If the API and provider belong to two incompatible generations, errors can occur at compile time, when initializing EntityManagerFactory, or when running queries.

Do not just look at the name "JPA". Determine the exact generation: Jakarta Persistence 2.2, 3.0, 3.1, or 3.2.

## 3. Reading the matrix in order

When choosing a set of versions, read in the following order:

1. **Choose the JDK runtime.** Determine the JDK that developer machines, CI, and production will run.
2. **Choose the Spring Boot release line.** Check Java and build tool requirements.
3. **Read Boot's managed dependency coordinates.** Note Spring Framework, Spring Data JPA, Hibernate, and Jakarta Persistence.
4. **Cross-check Spring Data.** Confirm the module belongs to the appropriate release train and its Framework requirement is not higher than the version provided by Boot.
5. **Cross-check Hibernate.** Check supported JDK, Jakarta Persistence, and Spring Boot generations.
6. **Cross-check the JDBC driver/database.** Check both the Java driver and the server version.
7. **Inspect the resolved dependency graph.** Do not rely on versions declared in build files; verify the versions Maven/Gradle actually selects.
8. **Build, test, and run on the target runtime.** A valid matrix is a necessary condition; integration tests confirm actual behavior.

Do not start by finding the "latest" Hibernate version and forcing Spring Boot to use it. Choose the platform release line first, then inspect the platform's dependency management.

## 4. Official matrix example as of 2026-11-09

The table below illustrates two release lines published in official documentation. This is a snapshot for learning how to read the matrix, not advice to upgrade every project to the same version.

| Component | Spring Boot 3.4.13 | Spring Boot 4.1.2 |
| --- | --- | --- |
| Java according to Spring Boot | 17 to 24 | 17 to 27 |
| Spring Framework | 6.2.15 | 7.0.10 |
| Spring Data JPA managed by Boot | 3.4.13 | 4.1.2 |
| Hibernate ORM managed by Boot | 6.6.39.Final | 7.4.13.Final |
| Jakarta Persistence | 3.1.0 | 3.2 generation |
| Hibernate compatible with Spring Boot | Hibernate 6.6 supports Boot 3.4–3.5 | Hibernate 7.4 supports Boot 4.1 |

Sources for each row:

- Spring Boot 3.4.13 System Requirements: Java 17–24, Spring Framework 6.2.15 or above.
- Spring Boot 3.4.13 Managed Dependency Coordinates: Spring Data JPA 3.4.13, Hibernate Core 6.6.39.Final, Jakarta Persistence API 3.1.0.
- Spring Boot 4.1.2 System Requirements: Java 17–27, Spring Framework 7.0.10 or above.
- Spring Boot managed coordinates 4.1.2: Spring Data JPA 4.1.2 and Hibernate Core 7.4.13.Final.
- Hibernate 6.6 compatibility: Jakarta Persistence 3.1 and Spring Boot 3.4–3.5.
- Hibernate 7.4 compatibility: Jakarta Persistence 3.2 and Spring Boot 4.1.

Key point when reading the table: Spring Boot's JDK range does not automatically become the JDK range of every third-party dependency. Hibernate has its own Java matrix. For example, Hibernate 6.6 lists Java 11, 17, 21; Java 25 is explicitly noted from 6.6.40 onwards. Because Boot 3.4.13 manages Hibernate 6.6.39.Final, the explicitly listed intersection between the two matrices is Java 17 and 21. Java 24 is within Boot's range but does not appear in this Hibernate release's compatible JDK list; you must check the specific release notes/support policy before choosing it.

Similarly, Hibernate 7.4 lists Java 17, 21, 25, and 26. Even though Spring Boot 4.1.2 announces support up to Java 27, do not infer that Hibernate 7.4.13 is also published as supporting Java 27 if the Hibernate matrix does not yet list that version.

## 5. Computing the intersection of constraints

Suppose the project chooses Spring Boot 3.4.13:

- Boot requires a minimum of Java 17 and announces support up to Java 24.
- Boot manages Spring Framework 6.2.15.
- Boot manages Spring Data JPA 3.4.13.
- Boot manages Hibernate ORM 6.6.39.Final.
- Boot manages Jakarta Persistence API 3.1.0.
- Hibernate 6.6 is compatible with Spring Boot 3.4–3.5 and Jakarta Persistence 3.1.
- Hibernate 6.6.39 has a supported JDK list that must be cross-checked separately; Java 17 and 21 are the explicitly listed intersection with Boot's Java range.

A reproducible baseline platform set is:

~~~text
JDK:                  17
Spring Boot:          3.4.13
Spring Framework:     6.2.15 (Boot-managed)
Spring Data JPA:      3.4.13 (Boot-managed)
Hibernate ORM:        6.6.39.Final (Boot-managed)
Jakarta Persistence:  3.1.0 (Boot-managed)
~~~

This is how to read the dependency matrix, not a requirement to pin all of the above versions in pom.xml. In a project using Boot parent/BOM, you usually only declare the Spring Boot starter and let Boot manage the versions.

### Do not pick the highest version from each column

For example, do not manually combine:

~~~text
Spring Boot 3.4.x
Spring Framework 7.x
Spring Data JPA 4.x
Hibernate 7.4.x
Jakarta Persistence 3.2
~~~

This is picking each column independently and can create an unsupported dependency graph. Major generations should be upgraded as a controlled platform set.

## 6. Spring Data release trains and module versions

Spring Data uses a release train to manage multiple modules with different release schedules. A release train has a calendar-based name, for example in the form YYYY.MINOR.MICRO; the version of a module such as Spring Data JPA does not necessarily match the release train number.

For example:

- Spring Data JPA has its own version.
- Spring Data Commons has its own version.
- Spring Data JDBC, MongoDB, Redis, and other modules also have their own versions.
- The release train BOM specifies the compatible set of versions across modules.
- Spring Boot selects a set of Spring Data module versions aligned with the Boot release line.

Therefore, do not assume Spring Data JPA must share the same major/minor number as Spring Boot. Check the artifact versions in Boot managed coordinates or the release train BOM.

### When the application uses Spring Boot

If using the Spring Boot parent or importing the Boot BOM, by default let Boot select Spring Data JPA:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-jpa</artifactId>
</dependency>
~~~

Do not add a separate version for spring-data-jpa without a specific reason.

### When not using Spring Boot

If a project uses Spring Framework directly, the Spring Data BOM helps select modules from the same release train:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.data</groupId>
            <artifactId>spring-data-bom</artifactId>
            <version>2025.0.13</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Then declare the module without specifying a version:

~~~xml
<dependency>
    <groupId>org.springframework.data</groupId>
    <artifactId>spring-data-jpa</artifactId>
</dependency>
~~~

When using the Spring Data BOM standalone, you must check the Spring Framework requirement of that release train. Do not pick the latest BOM and pair it with an older Spring Framework without verifying compatibility.

## 7. How does the Spring Boot BOM manage dependencies?

Spring Boot publishes a curated dependency list as a BOM named spring-boot-dependencies. The BOM provides default versions for many libraries chosen together for the same release line.

When using the Spring Boot parent, dependencies included in the BOM can be declared without a version:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-jpa</artifactId>
</dependency>
~~~

The starter pulls in matching components such as Spring Data JPA, Spring ORM, Hibernate, and the Jakarta Persistence API.

Benefits:

- Spring dependencies are aligned to the same release line.
- Hibernate modules use synchronized versions.
- No need to manually pin every transitive dependency.
- Upgrading Boot upgrades the entire set of dependencies in a tested configuration.
- Reduces the risk of selecting mismatched API/provider generations.

### A BOM does not mean every dependency in the project is automatically compatible

A dependency added by the project may not be in the Boot BOM. Another library can also bring in transitive dependencies with different versions. Therefore, check the dependency tree after adding libraries.

### Do not import multiple BOMs arbitrarily

If you import the Boot BOM, Spring Data BOM, and Hibernate BOM at the same time, dependency management order or version overrides can produce unexpected results.

Only add a second BOM when you have a clear purpose, have read the build tool's precedence rules, and have checked the effective POM/dependency graph. In a typical Boot application, the Boot BOM should be the primary source of dependency management.

## 8. Distinguishing javax.persistence and jakarta.persistence

This is an important boundary when upgrading from older Spring ecosystems to Spring Boot 3+.

| Platform | Commonly used persistence namespace |
| --- | --- |
| Spring Boot 2.x / Hibernate 5.x generation | javax.persistence.* |
| Spring Boot 3.x / Hibernate 6.x generation | jakarta.persistence.* |
| Spring Boot 4.x / Hibernate 7.x generation | jakarta.persistence.* |

Jakarta Persistence 3.x uses the jakarta.persistence package. Common annotations and interfaces:

~~~java
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
~~~

If source code still imports javax.persistence.Entity in a Boot 3 or Boot 4 project, the compiler may not find the corresponding annotation or the provider will not recognize the mapping as expected.

Do not add both APIs just to "make it run". An entity class should not mix javax and jakarta annotations. When upgrading major generations, migrate imports, dependencies, annotation processors, integration libraries, and test fixtures to the appropriate namespace.

## 9. Reading the Hibernate ORM matrix

Hibernate has a separate compatibility page for each series. When reading it, check:

- Supported Java runtimes.
- Implemented Jakarta Persistence version.
- Jakarta EE generation if the application depends on a container.
- Compatible Spring Boot generation.
- Database dialects and database versions.
- Support/maintenance status of the series.

### Jakarta Persistence version

Hibernate ORM 6.6 implements Jakarta Persistence 3.1. Hibernate ORM 7.4 implements Jakarta Persistence 3.2. If code uses new JPA 3.2 APIs while the provider only implements JPA 3.1, compilation may fail or runtime APIs will be unavailable.

### Spring Boot generation

Hibernate 6.6 announces compatibility with Spring Boot 3.4–3.5. Hibernate 7.4 announces compatibility with Spring Boot 4.1. This is a stronger signal than looking only at Hibernate's major version.

### Support status

Compatible does not mean fully maintained. A series may be in limited support or end-of-life status. When choosing a version for a new project, check both the compatibility matrix and the maintenance policy/security support.

Do not keep an EOL series just because it still runs on the current JDK.

## 10. Check the actual JDK, not just the Java source level

Three concepts must be distinguished:

1. **JDK running Maven/Gradle:** the JVM that the build tool is using.
2. **Compiler release/target:** the bytecode and Java APIs that the source is allowed to use.
3. **Production JDK:** the JVM that actually runs the application after deployment.

For example, pom has:

~~~xml
<properties>
    <java.version>17</java.version>
</properties>
~~~

This does not by itself prove that production is running Java 17. The container image or server may be using Java 21, 24, or another JDK.

Check the environment:

~~~bash
java -version
mvn -version
~~~

If using Gradle:

~~~bash
./gradlew -version
~~~

Check the JDK in CI and the Docker image. A project compiled with release 17 can still fail if a runtime dependency requires a newer JDK.

### Toolchain

Maven Toolchains or Gradle Java Toolchains help select the compiler JDK intentionally. Use toolchains when developers, CI, and build agents have multiple JDKs; you must still ensure the production runtime is within the dependency support range.

## 11. Database and JDBC driver are also part of the matrix

An application can resolve Spring Data JPA and Hibernate successfully and still be incompatible with the database server or JDBC driver.

Check:

- Whether the database server version is supported by the Hibernate dialect.
- Whether the JDBC driver version supports the JDK in use.
- Whether the driver supports the server's protocol/TLS/authentication.
- Whether data types, sequences, identity, JSON, arrays, enums, and pagination match the dialect.
- Whether locking, isolation, and transaction semantics match business requirements.
- Whether the migration tool supports that database version.

For example, Hibernate 6.x has different dialects from Hibernate 7.x. Do not copy old dialect settings to a new version without checking the documentation. In many cases Hibernate detects the dialect automatically from JDBC metadata; only configure a dialect manually when there is a reason and it has been verified.

### H2 does not replace the production database

H2 is suitable for fast tests, but it does not prove PostgreSQL/MySQL/SQL Server/Oracle compatibility. When using native SQL, stored procedures, locking, or vendor-specific types, run integration tests against the exact production database engine and JDBC driver, for example via Testcontainers.

## 12. Verifying the dependency graph with Maven

The pom.xml file only shows direct dependencies and dependency management. Maven is what resolves the final versions.

### Print the effective POM

~~~bash
mvn help:effective-pom -Doutput=target/effective-pom.xml
~~~

The effective POM shows the configuration after parent inheritance and dependency management are applied.

### Print the dependency tree

~~~bash
mvn dependency:tree
~~~

Filter the relevant components:

~~~bash
mvn dependency:tree -Dverbose -Dincludes=org.springframework.data:spring-data-jpa,org.springframework:spring-orm,org.hibernate.orm:hibernate-core,jakarta.persistence:jakarta.persistence-api
~~~

Read the output to determine:

- Which version was selected.
- Which dependency pulled that version in.
- Which versions were omitted due to conflicts.
- Whether two generations of the same API appear in the graph.

### Check a property

~~~bash
mvn help:evaluate -Dexpression=java.version -q -DforceStdout
~~~

This command reads the Maven project property. You still must check the actual JDK with mvn -version.

### When you see an unexpected version

1. Open the effective POM.
2. Find the dependencyManagement managing the artifact.
3. Check whether a direct dependency declares its own version.
4. Check BOM imports and their import order.
5. Check transitive dependencies bringing in another version.
6. Use the dependency tree to confirm the final version.
7. After making changes, rebuild and run tests.

Do not fix this by adding a random version to the first dependency you see in the tree. First identify the source managing the version.

## 13. Verifying the dependency graph with Gradle

Gradle can print all dependencies by configuration:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Find why a version was selected:

~~~bash
./gradlew dependencyInsight --dependency spring-data-jpa --configuration runtimeClasspath
./gradlew dependencyInsight --dependency hibernate-core --configuration runtimeClasspath
./gradlew dependencyInsight --dependency jakarta.persistence-api --configuration runtimeClasspath
~~~

Dependency insight shows the selected version, constraints, and dependency path. This is a quick way to detect when a library has pulled in a Hibernate or Jakarta Persistence API version different from the Boot BOM.

If using Gradle native BOM support:

~~~gradle
dependencies {
    implementation platform("org.springframework.boot:spring-boot-dependencies:3.4.13")
    implementation "org.springframework.boot:spring-boot-starter-data-jpa"
    runtimeOnly "com.h2database:h2"
    testImplementation "org.springframework.boot:spring-boot-starter-test"
}
~~~

If using the Spring Boot Gradle plugin, the plugin can automatically import Boot dependency management according to the corresponding configuration. There is no need to repeat platform if the plugin already provides the same BOM.

## 14. Maven example using Spring Boot-managed versions

The example below uses Spring Boot 3.4.13, Java 17, Spring Data JPA, and H2. It does not declare separate versions for Spring Data JPA, Hibernate, or Jakarta Persistence; the Boot BOM selects them.

### Project structure

~~~text
compatibility-check/
├── pom.xml
└── src/
    └── main/
        ├── java/com/example/compatibility/
        │   ├── CompatibilityApplication.java
        │   ├── Book.java
        │   └── BookRepository.java
        └── resources/
            └── application.properties
~~~

### pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.4.13</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>compatibility-check</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-data-jpa</artifactId>
        </dependency>

        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <scope>runtime</scope>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
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

### application.properties

~~~properties
spring.datasource.url=jdbc:h2:mem:compatibilitydb;DB_CLOSE_DELAY=-1
spring.datasource.username=sa
spring.datasource.password=
spring.jpa.hibernate.ddl-auto=create-drop
spring.jpa.open-in-view=false
~~~

### Book.java

~~~java
package com.example.compatibility;

import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "books")
public class Book {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String title;

    protected Book() {
    }

    public Book(String title) {
        this.title = title;
    }

    public Long getId() {
        return id;
    }

    public String getTitle() {
        return title;
    }
}
~~~

### BookRepository.java

~~~java
package com.example.compatibility;

import org.springframework.data.jpa.repository.JpaRepository;

public interface BookRepository extends JpaRepository<Book, Long> {
}
~~~

### CompatibilityApplication.java

~~~java
package com.example.compatibility;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class CompatibilityApplication {
    public static void main(String[] args) {
        SpringApplication.run(CompatibilityApplication.class, args);
    }

    @Bean
    CommandLineRunner demo(BookRepository repository) {
        return args -> {
            repository.save(new Book("Spring Data JPA"));

            System.out.println("Spring Data JPA compatibility check:");
            repository.findAll().forEach(book ->
                    System.out.println(book.getId() + " | " + book.getTitle()));
        };
    }
}
~~~

### Build and run

~~~bash
java -version
mvn -version
mvn clean verify
mvn spring-boot:run
~~~

Application output on a fresh H2 database:

~~~text
Spring Data JPA compatibility check:
1 | Spring Data JPA
~~~

ID 1 is the result of a fresh in-memory database and one record inserted in the example. The build command verifies compile/test/package; the dependency:tree command from earlier verifies the resolved versions.

### Expected dependency versions according to Boot 3.4.13

Boot 3.4.13's managed coordinates documentation publishes:

~~~text
org.springframework.data:spring-data-jpa:3.4.13
org.springframework: spring-framework modules: 6.2.15
org.hibernate.orm:hibernate-core:6.6.39.Final
jakarta.persistence:jakarta.persistence-api:3.1.0
~~~

Actual output may include additional dependencies and modules. Use dependency:tree to verify on the built project, rather than treating the documentation table as a substitute for build output.

## 15. When is it acceptable to override a Boot-managed version?

Sometimes you need to upgrade a dependency for a bug fix, security advisory, or feature that the Boot release line does not yet manage. This is an intentional decision that requires compatibility verification.

Before overriding, answer:

1. Is the new version compatible with the Spring Framework in use?
2. Does the Spring Data JPA version support the new Hibernate version?
3. Does the new Hibernate version implement the current Jakarta Persistence API?
4. Do all Hibernate modules such as core, envers, spatial, and hibernate-micrometer share the same version?
5. Are the JDBC driver and database dialect compatible?
6. Is there a migration guide for API, SQL generation, type mapping, or behavior changes?
7. Do integration tests run against the production JDK and database?

### Overriding an existing property

Boot provides several properties to customize managed dependency versions. Property names and support scope depend on the Boot release. Only use properties published in the documentation for the exact release line.

Do not invent an arbitrary property and assume Maven/Gradle will apply it.

### Overriding a dependency directly

When declaring a custom version, that dependency can override the Boot BOM's choice. You must inspect the effective POM and dependency tree to see the final result.

Do not change only hibernate-core if other Hibernate modules in the graph remain on an older version. Do not add a new Jakarta Persistence API version just to compile if the provider does not implement that generation.

### Do not override just because a newer version exists

A newer version is not always compatible with an older platform. Check the compatibility matrix, migration guide, and release notes before upgrading.

## 16. Upgrade by platform, not by upgrading individual libraries at random

When upgrading from Boot 2.x to Boot 3.x, major changes include:

- Minimum JDK increases to Java 17.
- Spring Framework 5 moves to 6.
- Spring Data JPA 2.x moves to 3.x.
- Hibernate 5 moves to 6.
- Java EE javax namespace moves to Jakarta namespace.
- Jakarta Persistence API moves to the 3.1 generation in Boot 3.4.

When upgrading to Boot 4.x, check again:

- Spring Framework 7.
- Spring Data JPA 4.x.
- Hibernate 7.x.
- Jakarta Persistence 3.2.
- Servlet/container generation and starters/modules that changed.
- Whether third-party libraries already support Spring Framework 7 and Jakarta Persistence 3.2.

Do not just change javax imports to jakarta and consider the migration done. You need to check deprecated or changed methods/APIs, dialects, type mappings, query parsing, transaction behavior, test infrastructure, and integration libraries.

### Controlled upgrade sequence

1. Read the Spring Boot migration guide for each major generation.
2. Read the migration guides for Spring Framework, Spring Data, and Hibernate.
3. Lock down the JDK and build tool.
4. Upgrade the Boot parent/BOM.
5. Remove old version overrides that are no longer needed.
6. Migrate namespaces and fix compile errors.
7. Run unit tests and repository integration tests.
8. Run tests against the production database engine.
9. Check generated SQL, schema validation, transactions, and locking.
10. Verify startup, observability, deployment image, and rollback plan.

## 17. Reading errors based on version mismatch symptoms

| Symptom | Possible cause | How to check |
| --- | --- | --- |
| NoClassDefFoundError: javax/persistence/... | Old code/library using javax in a Jakarta application | Find the dependency still pulling javax.persistence and check imports. |
| NoClassDefFoundError: jakarta/persistence/... | Missing Jakarta API or wrong provider generation | Check the dependency tree and Hibernate version. |
| NoSuchMethodError in Spring Data/Hibernate | Compile/runtime resolved two different versions or incompatible override | Check the dependency tree, packaged jar, and runtime classpath. |
| UnsupportedClassVersionError | Runtime JDK is lower than class bytecode | Compare javac release with the production JDK. |
| Failed to configure a DataSource / driver not found | Missing JDBC driver or incompatible version | Check runtime dependencies and driver compatibility. |
| Could not determine recommended JdbcType / dialect errors | Mapping or dialect does not match provider/database | Read the Hibernate migration guide, dialect, and type mappings. |
| EntityManagerFactory startup failure | API/provider mismatch, mapping, or schema error | Inspect the root cause, dependency graph, and persistence metadata. |
| Spring Data repository method fails to initialize | API/module version skew or invalid query method | Check the Spring Data JPA version and startup stack trace. |
| Method not found after major upgrade | API changed between generations | Read the migration guide for the exact module. |

Do not fix errors by removing dependencies at random. Identify which artifact and version loaded the class and which dependency path brought it in.

## 18. Pre-project compatibility matrix reading checklist

- [ ] Chosen the JDK runtime and verified it on developer machines, CI, and production.
- [ ] Spring Boot release line supports the selected JDK and build tool.
- [ ] Read managed dependency coordinates for the exact Boot version.
- [ ] Spring Framework satisfies the Spring Data release line requirements.
- [ ] Spring Data JPA version is managed by the appropriate Boot BOM or Spring Data BOM.
- [ ] Jakarta Persistence API generation matches the Hibernate provider.
- [ ] Hibernate compatibility page lists the Spring Boot generation in use.
- [ ] JDK lies in the intersection between Boot and Hibernate.
- [ ] JDBC driver supports the JDK and database server version.
- [ ] Database dialect and SQL features match.
- [ ] No mixing of javax.persistence and jakarta.persistence.
- [ ] No unexplained version overrides.
- [ ] Dependency tree has no conflicting API/provider generations.
- [ ] Maven effective POM or Gradle dependencyInsight has been checked.
- [ ] Build/tests run successfully on the target JDK.
- [ ] Integration tests run on a production-like database.
- [ ] Checked maintenance status and security support of the release lines.

## 19. Practical principles

- Choose the JDK and Spring Boot release line first, then read the Boot-managed dependency versions.
- Treat Spring Data JPA and Hibernate as two separate components aligned through the BOM.
- Check the Jakarta Persistence API generation instead of just looking at the word JPA.
- Compute the intersection between the JDK ranges of Boot and Hibernate.
- Use the Spring Boot BOM as the default version management source in Boot applications.
- Only use the standalone Spring Data BOM when not relying on Boot dependency management or after verifying compatibility.
- Do not mix versions across multiple major generations.
- Use Maven dependency:tree/effective-pom or Gradle dependencyInsight to see actual versions.
- Check the JDBC driver and database server, not stopping at a successful compile.
- Read migration guides and support lifecycles before a major upgrade.
- Verify the version set with builds, integration tests, and a production-like runtime.

Core takeaway: **Read the compatibility matrix by intersecting the constraints of the JDK, Spring Boot, Spring Framework, Spring Data JPA, Jakarta Persistence, Hibernate, and the database driver. Use the Boot BOM to keep dependencies synchronized, verify actual versions with the dependency tree, and confirm with integration tests on the target JDK and database.**

## 20. Official references

- Spring Boot 3.4 System Requirements: https://docs.spring.io/spring-boot/3.4/system-requirements.html
- Spring Boot 3.4 Managed Dependency Coordinates: https://docs.spring.io/spring-boot/3.4/appendix/dependency-versions/coordinates.html
- Spring Boot Build Systems and Dependency Management: https://docs.spring.io/spring-boot/reference/using/build-systems.html
- Spring Boot 4.1 System Requirements: https://docs.spring.io/spring-boot/system-requirements.html
- Spring Boot Managed Dependency Coordinates: https://docs.spring.io/spring-boot/appendix/dependency-versions/coordinates.html
- Spring Data Dependencies and Release Train BOM: https://docs.spring.io/spring-data/jpa/reference/data-commons/dependencies.html
- Hibernate ORM 6.6 Compatibility: https://hibernate.org/orm/releases/6.6/
- Hibernate ORM 7.4 Compatibility: https://hibernate.org/orm/releases/7.4/
- Hibernate ORM Documentation and Migration Guides: https://hibernate.org/orm/documentation/

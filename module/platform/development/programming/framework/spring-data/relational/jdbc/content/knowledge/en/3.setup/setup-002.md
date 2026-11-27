# Declaring `spring-boot-starter-data-jdbc` and Managing Dependencies with a BOM

To use **Spring Data JDBC** in a Spring Boot application, a key initialization step is declaring the right libraries in your build tool. A solid configuration answers three questions: **which starter to add**, **what manages the versions of related libraries**, and **which driver enables the application to connect to the actual database**.

In most Spring Boot projects, you only need to declare the `org.springframework.boot:spring-boot-starter-data-jdbc` dependency together with your database management system's JDBC driver, and let the **Spring Boot BOM** manage compatible versions. There is no need to manually pick individual versions for Spring Data, Spring JDBC, and drivers that are already managed by the BOM.

This lesson uses **Spring Boot 3.3.5 and Java 21 to illustrate configuration syntax**. This pairing is chosen purely for demonstration and does not imply that 3.3.5 is the latest release. When applying this to a real project, use the Spring Boot version selected by your project and ensure the BOM matches that version.

## 1. Understanding the Three Components to Declare

| Component | Example | Role |
| --- | --- | --- |
| **Starter** | `spring-boot-starter-data-jdbc` | Bundles the dependencies required for Spring Data JDBC and enables appropriate auto-configuration in Spring Boot. |
| **BOM (Bill of Materials)** | `spring-boot-dependencies` | Defines managed versions for a curated set of libraries to reduce conflicts and maintain compatibility. |
| **JDBC driver** | `org.postgresql:postgresql` | Provides the concrete JDBC communication layer for PostgreSQL; can be swapped for MySQL, MariaDB, H2, etc. |

Visualizing the path from the build tool to the database:

```text
build.gradle or pom.xml
    |
    +-- spring-boot-starter-data-jdbc
    |       |
    |       +-- Spring Data JDBC / Spring Data Relational
    |       +-- Spring JDBC
    |       +-- required supporting libraries
    |
    +-- Driver (e.g., PostgreSQL JDBC driver)
    |
    +-- Spring Boot BOM: manages compatible versions
            |
            v
      Java / Spring Boot Application
            |
            v
      Repository -> JDBC -> Driver -> Database
```

This diagram illustrates the main dependency groups only; the actual dependency graph may vary depending on the Spring Boot version.

**A starter is not a database.** Adding a starter equips the application with data-access libraries, but it does not create a database, tables, or connection credentials. Nor does the driver create tables; connection configuration and schema migrations are separate follow-up steps.

## 2. What Is `spring-boot-starter-data-jdbc`?

The Maven/Gradle dependency has the coordinates:

```text
Group ID:    org.springframework.boot
Artifact ID: spring-boot-starter-data-jdbc
Version:     managed by the Spring Boot BOM
```

A Spring Boot starter is a **convenient entry point**: instead of manually listing every library needed for `JdbcTemplate`, Spring Data JDBC repositories, Spring Data Relational, and the underlying JDBC infrastructure, you declare the starter, and the dependency management system resolves the appropriate transitive dependencies.

Distinguishing commonly confused starters:

| Dependency | Purpose | Does It Replace `spring-boot-starter-data-jdbc`? |
| --- | --- | --- |
| `spring-boot-starter-jdbc` | JDBC support via Spring JDBC, `JdbcTemplate`, and `DataSource` configuration. | **Not completely.** Does not provide the full Spring Data JDBC repository/mapping model. |
| `spring-boot-starter-data-jdbc` | Adds Spring Data JDBC repositories and aggregate mapping, along with JDBC infrastructure. | **The right choice** for this lesson. |
| `spring-boot-starter-data-jpa` | Integrates Spring Data JPA, a JPA provider such as Hibernate, and the ORM model. | **No.** JPA and Data JDBC use different persistence mechanisms. |
| `spring-boot-starter-data-r2dbc` | Supports relational data access via the reactive R2DBC API. | **No.** R2DBC does not use blocking JDBC. |

If you are only using Spring Data JDBC, you normally **do not need to add `spring-boot-starter-jdbc`**, because the Data JDBC starter already brings in the corresponding JDBC infrastructure. Adding Data JPA at the same time under the assumption that it is required for repositories is another common misconception.

## 3. What Is a BOM and Why Use It?

A **BOM (Bill of Materials)** in the Maven ecosystem is a POM file dedicated to managing dependency versions. Spring Boot publishes the `org.springframework.boot:spring-boot-dependencies` BOM matching each Spring Boot release.

Conceptually, a BOM can manage versions for:

- `org.springframework.data:spring-data-jdbc`;
- `org.springframework:spring-jdbc`;
- `org.postgresql:postgresql`;
- HikariCP, Jackson, test libraries, and many other dependencies.

Once the BOM is properly applied, your application dependency declaration can simply be written as:

```groovy
implementation 'org.springframework.boot:spring-boot-starter-data-jdbc'
runtimeOnly 'org.postgresql:postgresql'
```

You **do not need to append `:version`** to those two coordinates because the BOM supplies the managed versions.

### 3.1. What Problem Does a BOM Solve?

Suppose a project manually sets versions for Spring Data JDBC, Spring Framework, drivers, and supporting libraries; the build author must then ensure they are all compatible. If one library is upgraded independently, the dependency graph can end up with mismatched versions that trigger runtime errors or method linkage failures.

A BOM consolidates most version choices into **a single, consistent source of truth**. With Spring Boot, you typically upgrade the Boot/BOM version on a planned schedule, and the build picks up the corresponding managed version set.

```text
Without a BOM:
  Spring Data JDBC version A
  Spring JDBC version B
  Spring Framework version C
  Driver version D
  -> track compatibility manually

With Spring Boot BOM:
  Spring Boot/BOM version X
  -> set of versions managed together by Spring Boot
```

A BOM **reduces the risk** of conflicts; it does not mean every possible set of dependencies in a project is guaranteed to be compatible, especially when adding libraries outside the BOM's scope or overriding versions.

### 3.2. What Does a BOM Manage and Not Manage?

A BOM primarily manages **dependency versions**:

- It does not automatically add `spring-boot-starter-data-jdbc` to your project. You still have to declare the libraries you use.
- It does not automatically install drivers for every database type. You must add the right driver.
- It does not manage **Gradle plugin or Maven plugin** versions through the same standard dependency management mechanism; Maven's `spring-boot-starter-parent` adds its own plugin management mechanism.
- It does not create tables, run migrations, grant database permissions, manage passwords, or run business tests.
- It does not guarantee that a dependency whose version you forced manually remains compatible with all other libraries.

Therefore, standard practice is to **declare the dependencies you need, let the BOM manage versions, and only override a version when you have a verified reason**.

## 4. Declaring Dependencies with Gradle Groovy DSL (`build.gradle`)

For a Spring Boot project using `build.gradle`, a complete dependency-level example looks like this:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-jdbc'
    runtimeOnly 'org.postgresql:postgresql'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Role of each declaration:

| Configuration | Meaning |
| --- | --- |
| `id 'java'` | Enables Java tasks and configures source sets, compilation, and testing. |
| `id 'org.springframework.boot'` | Integrates Spring Boot application tasks and packaging with Gradle. |
| `id 'io.spring.dependency-management'` | Enables dependency management; when paired with the Spring Boot Gradle plugin, the corresponding Spring Boot BOM is applied automatically. |
| `mavenCentral()` | Allows Gradle to download artifacts from Maven Central. |
| `implementation '...starter-data-jdbc'` | Places Spring Data JDBC and its transitive dependencies onto the appropriate compile/runtime classpaths. |
| `runtimeOnly 'org.postgresql:postgresql'` | Places the PostgreSQL JDBC driver on the runtime classpath without requiring business code to compile directly against driver classes. |
| `testImplementation '...starter-test'` | Adds the Spring Boot testing infrastructure. |
| `JavaLanguageVersion.of(21)` | Selects the Java toolchain used to compile/run Java tasks; does not determine Spring library versions. |

**Why are there no version numbers after the starter and driver?** The Spring Boot Gradle plugin works with `io.spring.dependency-management` to automatically import the `spring-boot-dependencies` BOM matching the Spring Boot plugin version. As a result, BOM-managed coordinates can be declared without a version.

Note that **the versions of the two plugins inside the `plugins` block must still be declared or managed elsewhere via Gradle's plugin management mechanism**. The dependency BOM does not automatically pick the version of the `io.spring.dependency-management` plugin.

### 4.1. Equivalent Configuration in Gradle Kotlin DSL

If the project uses `build.gradle.kts`:

```kotlin
plugins {
    java
    id("org.springframework.boot") version "3.3.5"
    id("io.spring.dependency-management") version "1.1.6"
}

group = "com.example"
version = "0.0.1-SNAPSHOT"

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(21))
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-jdbc")
    runtimeOnly("org.postgresql:postgresql")

    testImplementation("org.springframework.boot:spring-boot-starter-test")
}

tasks.test {
    useJUnitPlatform()
}
```

Both Gradle examples have the same meaning; choose the syntax matching your project's build file type and do not mix Groovy DSL into `build.gradle.kts`.

### 4.2. Alternative: Gradle Native BOM with `platform(...)`

Gradle also provides its own standard version management mechanism: importing a BOM with `platform(...)`, **without needing the `io.spring.dependency-management` plugin**. If the application uses the Spring Boot Gradle plugin, you can reference the BOM coordinates tied to that plugin version:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation platform(
        org.springframework.boot.gradle.plugin.SpringBootPlugin.BOM_COORDINATES
    )

    implementation 'org.springframework.boot:spring-boot-starter-data-jdbc'
    runtimeOnly 'org.postgresql:postgresql'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

In this example:

1. `SpringBootPlugin.BOM_COORDINATES` provides the Spring Boot BOM coordinates corresponding to the Spring Boot plugin version.
2. `platform(...)` imports the BOM's dependency version constraints using Gradle's native mechanism.
3. Dependencies included in the BOM continue to be declared without individual versions.

When starting a new project, it is best to **pick one clear BOM strategy**: either Spring's dependency management plugin or Gradle's native platform. Avoid importing multiple similar BOMs arbitrarily, as it becomes hard to tell which configuration decides the final versions.

If a project only applies the Gradle `java` plugin without the Spring Boot plugin, you can also write directly:

```groovy
dependencies {
    implementation platform('org.springframework.boot:spring-boot-dependencies:3.3.5')
    implementation 'org.springframework.boot:spring-boot-starter-data-jdbc'
    runtimeOnly 'org.postgresql:postgresql'
}
```

In this case, **the BOM version is specified explicitly**. This approach can be used for a library module or a build that does not apply the Spring Boot Gradle plugin; the BOM version should be kept aligned with the consuming application.

## 5. Declaring Dependencies with Maven (`pom.xml`)

Maven supports two ways of using Spring Boot's managed versions: inheriting from `spring-boot-starter-parent`, or importing `spring-boot-dependencies` as a BOM inside `dependencyManagement`.

### 5.1. Common Approach: Inheriting `spring-boot-starter-parent`

A minimal `pom.xml` example for a Spring Boot application using PostgreSQL:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>jdbc-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>21</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-data-jdbc</artifactId>
        </dependency>

        <dependency>
            <groupId>org.postgresql</groupId>
            <artifactId>postgresql</artifactId>
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
```

`spring-boot-starter-parent` inherits dependency management based on the Spring Boot BOM while also providing useful Maven defaults and plugin management. That is why the snippet above omits `<version>` for the starter, driver, and Spring Boot Maven plugin.

**Do not confuse the names:** `spring-boot-starter-parent` is a **parent POM**; `spring-boot-dependencies` is the **BOM** that manages dependency versions. The parent brings the BOM into dependency management and adds build configuration; they are related, but they are not the same artifact.

### 5.2. When the Project Already Has Its Own Parent POM: Importing the BOM

A `pom.xml` can declare only one direct parent. If a project already inherits from a corporate or multi-module parent, you can import the Spring Boot BOM inside `dependencyManagement` instead of replacing the existing parent.

Key configuration blocks:

```xml
<properties>
    <spring-boot.version>3.3.5</spring-boot.version>
    <maven.compiler.release>21</maven.compiler.release>
</properties>

<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-dependencies</artifactId>
            <version>${spring-boot.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-jdbc</artifactId>
    </dependency>
    <dependency>
        <groupId>org.postgresql</groupId>
        <artifactId>postgresql</artifactId>
        <scope>runtime</scope>
    </dependency>
</dependencies>
```

Place those blocks **inside the POM's `<project>` element** while keeping your existing valid parent. Importing the BOM makes Maven aware of the managed dependency versions. However, **importing the BOM does not bring along the build/plugin management defaults of `spring-boot-starter-parent`**; if the application needs the Spring Boot Maven plugin, you must configure the plugin and its version in `build/plugins` or through the project's parent/pluginManagement:

```xml
<build>
    <plugins>
        <plugin>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-maven-plugin</artifactId>
            <version>${spring-boot.version}</version>
        </plugin>
    </plugins>
</build>
```

Additional compiler/test/resource plugin configuration may be needed depending on the parent POM in use. The BOM resolves dependency versions; it does not replace everything the Spring Boot parent provides.

## 6. Adding the Right JDBC Driver for Your Database

`spring-boot-starter-data-jdbc` provides the data-access layer, while the driver must match your database and JDBC URL.

A few Gradle examples:

```groovy
// PostgreSQL
runtimeOnly 'org.postgresql:postgresql'

// MySQL
runtimeOnly 'com.mysql:mysql-connector-j'

// MariaDB
runtimeOnly 'org.mariadb.jdbc:mariadb-java-client'

// H2 (embedded database, commonly used for demos/tests)
runtimeOnly 'com.h2database:h2'
```

**Only declare the driver actually needed for your application's environment.** The lines above are alternative examples for illustration, not a requirement to add all four drivers at once.

`runtimeOnly` is usually appropriate when Java code only uses standard JDBC interfaces (`DataSource`, `Connection`) or Spring Data repositories without referencing driver-specific classes directly. If source code intentionally imports a driver class at compile time, the dependency scope should be reconsidered.

The equivalent declaration in Maven, using PostgreSQL as an example:

```xml
<dependency>
    <groupId>org.postgresql</groupId>
    <artifactId>postgresql</artifactId>
    <scope>runtime</scope>
</dependency>
```

**Do not specify a version if it is already managed by the active BOM.** If you choose a driver outside the BOM's managed list, supply its version using appropriate dependency management configuration.

## 7. Configuring `DataSource` After Adding Dependencies

Adding dependencies only puts the classes and configuration mechanisms onto the classpath. The application still needs to know where the database lives and what credentials to use.

Example `src/main/resources/application.yml` for PostgreSQL:

```yaml
spring:
  datasource:
    url: jdbc:postgresql://localhost:5432/shopdb
    username: ${DB_USER}
    password: ${DB_PASSWORD}
```

Explanation:

- `spring.datasource.url` is the JDBC URL pointing to the `shopdb` database on the local PostgreSQL instance.
- `spring.datasource.username` and `password` read values from environment variables; never place real passwords directly in examples or source code.
- Because the PostgreSQL driver was added with `runtimeOnly`, Spring Boot can detect the matching driver from the URL and classpath.
- Spring Boot typically configures a connection pool provided alongside the JDBC infrastructure when the appropriate library is on the classpath.

The `shopdb` database must be created and permissions granted beforehand. Furthermore, **Spring Data JDBC does not automatically generate table structures like JPA/Hibernate's `hibernate.ddl-auto` mode**. Schemas are usually handled by SQL migrations (such as Flyway or Liquibase) or separately managed table creation scripts.

Manual table creation example:

```sql
CREATE TABLE customers (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    name VARCHAR(150) NOT NULL
);
```

This is PostgreSQL DDL for illustration. Real schemas and migrations must match your application's database and system version.

## 8. A Small Example Showing What the Dependencies Enable

With the starter, driver, datasource, and `customers` table properly configured, you can write an aggregate root and repository as follows:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Table;

@Table("customers")
public record Customer(@Id Long id, String name) {
}
```

```java
import org.springframework.data.repository.CrudRepository;

public interface CustomerRepository
        extends CrudRepository<Customer, Long> {
}
```

A service can receive `CustomerRepository` via constructor injection and call `save`, `findById`, or `findAll`. For example:

```java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class CustomerService {
    private final CustomerRepository repository;

    public CustomerService(CustomerRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public Customer create(String name) {
        return repository.save(new Customer(null, name));
    }
}
```

In the immutable record model above, `save` returns an instance containing the generated ID after inserting the row; the application should use **the returned object**. Spring Data JDBC generates the SQL/mapping for the repository, the JDBC driver communicates with PostgreSQL, and the database persists the row.

This example assumes the classes reside in packages discovered by Spring Boot component/repository scanning. If placed outside the default scan scope, adjust the scan configuration accordingly. The Java classes above illustrate that the dependencies already support repositories; they do not replace connection configuration, migrations, or running a database.

## 9. How to Inspect Which Dependencies and Versions Were Actually Selected

Reading `build.gradle` or `pom.xml` shows what dependencies were declared; the **resolved dependency graph** shows which libraries and versions actually enter the classpath. When encountering version errors or missing drivers, this is the place to inspect first.

Reference commands to run in the project directory (not executed within this lesson):

**Gradle:**

```bash
# View runtime dependencies and resolved versions
./gradlew dependencies --configuration runtimeClasspath

# See why a library was selected on runtimeClasspath
./gradlew dependencyInsight \
  --dependency org.springframework.data:spring-data-jdbc \
  --configuration runtimeClasspath
```

On Windows, use `gradlew.bat`, or place the arguments on a single line as appropriate for your shell.

**Maven:**

```bash
# View the dependency tree
mvn dependency:tree

# View the effective POM after parent inheritance / BOM import
mvn help:effective-pom
```

When inspecting, look for three things:

1. `spring-boot-starter-data-jdbc` and `spring-data-jdbc` appear in the dependency graph.
2. The appropriate driver (for example, `org.postgresql:postgresql`) is on the **runtime** classpath.
3. The selected versions match the project's BOM strategy, aside from any intentionally managed exceptions.

You can also use your IDE's dependency view or existing dependency analysis tools if your project already has them. Never guess a version simply because a dependency omits `version` in the build file.

## 10. Troubleshooting Common Initialization Errors

| Symptom | Common Cause | How to Fix |
| --- | --- | --- |
| `Could not find ...` / dependency resolution failure | Missing `repositories { mavenCentral() }`, wrong artifact coordinates, or unreachable repository. | Check dependency coordinates, repository configuration, network/proxy, and artifact source. |
| Unable to determine version of starter or driver | BOM not properly imported/applied, or dependency is not managed by the current BOM. | Check Spring Boot parent, `dependencyManagement`, Gradle dependency management plugin, or `platform(...)`. |
| `Failed to configure a DataSource` due to missing URL | Datasource not configured, no suitable embedded database, or missing environment variable. | Provide `spring.datasource.url`, username/password, and start the corresponding database. |
| `No suitable driver` / failed to load JDBC driver | Missing driver or URL does not match any driver on the classpath. | Add the driver to the runtime classpath and verify the JDBC URL prefix. |
| `Connection refused` | No database listening at the configured host/port, or network blocked. | Check host, port, Docker/network, and database status. |
| Error `relation "customers" does not exist` | Database connection succeeded, but the table does not exist or lives in another schema. | Create/migrate the schema in the right database and check schema/search path. |
| Cannot inject `CustomerRepository` | Interface not detected by Spring Data, unsuitable package scan, or repository infrastructure not enabled/initialized. | Check starter, package location, and Spring Boot configuration. |
| `NoSuchMethodError` / linkage error after upgrading libraries | Incompatible library versions may exist on the classpath. | Inspect `dependencyInsight` or `dependency:tree`, remove redundant overrides, and align with the BOM. |

These messages represent **categories of errors**, and not every case shares the exact same root cause. Read both the `Caused by` chain and the dependency graph before changing library versions.

## 11. When Should You Explicitly Pin a Dependency Version?

The goal of a BOM is to establish a unified version baseline, though sometimes a project needs a specific version: a verified security fix, a library outside the BOM's scope, or a documented compatibility requirement.

Gradle example with an explicitly pinned driver version:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-jdbc'
    runtimeOnly 'org.postgresql:postgresql:42.7.4'
}
```

This is an **override syntax example**, not a recommendation to choose version `42.7.4` for every project. When specifying a custom version, check Java compatibility, Spring Boot compatibility, driver compatibility, relevant security advisories, and the actual resolved graph.

With Maven, you can adjust a dependency version using the project's `dependencyManagement` section or a direct `<version>` declaration on the specific dependency. If multiple BOMs are imported, import order and dependency management precedence must be reviewed according to the actual Maven configuration. Avoid adding arbitrary overrides without a clear reason.

For **multi-module** projects, also decide where shared versions are managed: a parent POM, root Gradle convention/build logic, or a version catalog. Modules sharing Spring Boot should follow a consistent versioning strategy rather than each module picking a different BOM.

## 12. Misconceptions to Avoid

**"Adding the starter means the PostgreSQL driver is already included."** False. The starter does not pick a specific database by default; when using PostgreSQL, declare the PostgreSQL driver.

**"Having the Spring Boot plugin means Gradle always manages dependencies automatically."** Not enough to conclude. With Gradle, check whether the project uses `io.spring.dependency-management`, native `platform(...)`, or another convention management setup. The Spring Boot plugin works alongside these approaches, but the plugin declaration alone does not remove the need to verify dependency management.

**"The BOM automatically adds every library it lists."** False. The BOM provides versions, while the application only pulls in dependencies that are explicitly declared or brought in transitively.

**"Versions in the Spring Boot BOM also manage Gradle plugins."** False. Gradle plugin versions are handled by Gradle plugin management; distinguish this from dependency version management.

**"Using Spring Data JDBC still requires adding the JPA starter."** False. JPA is not a prerequisite; accidentally adding JPA can introduce unwanted auto-configuration, persistence behavior, and unnecessary dependencies.

**"Setting every version manually is definitely more stable."** False. Scattered versions can drift out of sync; override only in a controlled way and verify the dependency graph.

**"Being able to connect means tables and data are ready."** False. Setting up connections and managing schemas are two separate responsibilities. Real systems require migrations, data constraints, backup procedures, and controlled schema evolution.

## 13. Self-Practice

Try three scenarios to reinforce how configuration works:

1. **Create an application using PostgreSQL:** declare `spring-boot-starter-data-jdbc`, the PostgreSQL driver, and the BOM via the Spring Boot parent or appropriate Gradle setup; use `application.yml` to configure the JDBC URL and credentials via environment variables.
2. **Switch to H2 for a demo:** swap the driver for `com.h2database:h2`, configure an appropriate H2 JDBC URL, and explain why in-memory data is not preserved across database restarts.
3. **Project with an existing custom Maven parent:** import `spring-boot-dependencies` inside `dependencyManagement`, keep the existing parent, and specify how to manage the Spring Boot Maven plugin version.

When reviewing the results, make sure you can answer: why the starter omits `version`, why a driver is still needed, how the BOM is applied, and how the dependency graph explains the final resolved versions.

**Key takeaway:** Effective Spring Data JDBC initialization starts with **`spring-boot-starter-data-jdbc` + the right driver + a clear Spring Boot BOM strategy**. The starter brings data-access capabilities into the application; the BOM keeps dependency versions aligned; the driver connects the application to the database management system. After dependencies are in place, you still need to configure `DataSource` and manage your schema properly.

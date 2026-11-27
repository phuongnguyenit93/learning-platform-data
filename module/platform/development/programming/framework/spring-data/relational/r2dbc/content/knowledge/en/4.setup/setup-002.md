# Declaring Dependencies with Gradle or Maven

Spring Data Relational R2DBC needs two groups of libraries for an application to access a relational database reactively: the Spring components providing repository and transaction abstractions, and the R2DBC driver for the specific database management system. When using Spring Boot, the starter dependency brings compatible Spring components into the application; the driver must still be selected based on the database the application connects to.

This lesson explains how to declare those dependencies with Gradle and Maven, how to manage versions, how to choose the appropriate scopes, and how to verify that dependencies were resolved properly.

## 1. Understanding the Required Dependencies

Before editing build files, distinguish the role of each library group.

### 1.1. Spring Data R2DBC and the Spring Boot Starter

Spring Data R2DBC provides relational data mapping under the reactive repository model. Applications can declare repositories returning `Mono` or `Flux`, use `R2dbcEntityTemplate` or `DatabaseClient`, and integrate reactive transactions.

For a Spring Boot application, the commonly used dependency is:

~~~text
org.springframework.boot:spring-boot-starter-data-r2dbc
~~~

This starter gathers the Spring libraries required for Spring Data R2DBC and integrates Spring Boot auto-configuration. Thanks to the starter, the application does not need to declare foundational libraries like Spring Data R2DBC, Spring R2DBC, and the reactive components they require individually.

The starter does not represent a specific database management system. The application still needs to add the R2DBC driver corresponding to PostgreSQL, MySQL, H2, or another DBMS.

There is no need to declare `spring-data-r2dbc` separately when the starter already provides that module. Duplicate declarations can make it harder for readers to tell which dependency controls the actual version.

### 1.2. Database R2DBC Driver

The driver translates operations from the R2DBC SPI into the protocol understood by the database management system. Choose a driver matching your database and a version compatible with your deployment environment.

Some common dependency coordinates:

| DBMS | R2DBC driver dependency |
|---|---|
| PostgreSQL | `org.postgresql:r2dbc-postgresql` |
| MySQL | `io.asyncer:r2dbc-mysql` |
| H2 | `io.r2dbc:r2dbc-h2` |
| Microsoft SQL Server | `io.r2dbc:r2dbc-mssql` |
| Oracle Database | `com.oracle.database.r2dbc:oracle-r2dbc` |
| MariaDB | `org.mariadb:r2dbc-mariadb` |

Artifact names and compatibility can vary across driver release lines. Cross-check the driver documentation against your database and Spring Boot versions before selecting a version.

For applications that only use the driver via connection configuration, the driver is typically declared in runtime scope. If source code directly references driver-specific classes or APIs, the dependency may be needed in compile scope.

### 1.3. R2DBC Drivers Differ from JDBC Drivers

R2DBC and JDBC are two different database access APIs. The PostgreSQL JDBC driver has the coordinates:

~~~text
org.postgresql:postgresql
~~~

The PostgreSQL R2DBC driver has the coordinates:

~~~text
org.postgresql:r2dbc-postgresql
~~~

Adding the JDBC driver will not enable Spring Data R2DBC to connect to the database. For an application using R2DBC, you must declare an R2DBC driver and configure a URL with the `r2dbc:` scheme.

An application can use both JDBC and R2DBC if there is a clear need, but in that case keep in mind they have separate connection factories/data sources, transaction managers, and access mechanisms. Adding `spring-boot-starter-jdbc` does not replace `spring-boot-starter-data-r2dbc`.

## 2. Managing Dependency Versions

Libraries in the Spring ecosystem depend on each other. Spring Boot, Spring Framework, Spring Data, Reactor, the R2DBC SPI, and the driver must be version-compatible.

Spring Boot provides a BOM (Bill of Materials) to manage library versions that have been tested together. When using Spring Boot dependency management, you typically only declare group, artifact, and scope; do not manually set versions for dependencies managed by the BOM.

For example, let the BOM manage the versions of the starter and driver:

~~~text
org.springframework.boot:spring-boot-starter-data-r2dbc
org.postgresql:r2dbc-postgresql
~~~

Do not arbitrarily mix a new `spring-data-r2dbc` version with an old Spring Framework version, or upgrade `r2dbc-spi` on its own without checking the driver. Forcing a dependency to a version different from the BOM can cause compilation errors, `NoSuchMethodError`, `ClassNotFoundException`, or runtime errors when initializing the connection factory.

If the project does not use Spring Boot, manage versions using the Spring Data/Spring Framework BOM and compatibility tables, while also checking the R2DBC driver's requirements. Avoid copying disconnected versions from different examples that do not belong to the same release line.

## 3. Declaring with Gradle

Gradle supports Groovy DSL in `build.gradle` and Kotlin DSL in `build.gradle.kts`. The syntax differs, but the dependency configuration semantics are equivalent.

### 3.1. Gradle with Groovy DSL

A Spring Boot application using PostgreSQL can declare dependencies as follows:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '<spring-boot-version>'
    id 'io.spring.dependency-management' version '<dependency-management-plugin-version>'
}

group = 'com.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-r2dbc'
    runtimeOnly 'org.postgresql:r2dbc-postgresql'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}
~~~

Replace the version placeholders with Spring Boot and plugin versions compatible with your project. When the Spring Boot Gradle plugin is configured alongside the dependency management plugin, Spring Boot's BOM can manage library versions. Thus, the starter and driver dependencies in the example do not need separate version declarations.

Meaning of the configurations:

- `implementation`: dependency is present on both the module's compile classpath and runtime classpath.
- `runtimeOnly`: dependency is needed at runtime, but source code does not need to reference it directly at compile time.
- `testImplementation`: dependency is only used for compiling and running tests.
- `repositories`: where Gradle searches for and downloads artifacts; `mavenCentral()` is the standard public repository.
- `java.toolchain`: selects the JDK version used to compile and run Gradle Java tasks.

Spring Data R2DBC is accessed via the starter in `implementation`. The PostgreSQL driver is used when establishing connections at runtime, so it is usually placed in `runtimeOnly`.

If the application directly references driver classes—for instance, configuring driver-specific options via Java APIs—consider moving the driver to `implementation`. Only do so when source code genuinely requires those APIs.

### 3.2. Gradle with Kotlin DSL

If the project uses `build.gradle.kts`, the corresponding declaration is:

~~~kotlin
plugins {
    java
    id("org.springframework.boot") version "<spring-boot-version>"
    id("io.spring.dependency-management") version "<dependency-management-plugin-version>"
}

group = "com.example"
version = "1.0.0"

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-r2dbc")
    runtimeOnly("org.postgresql:r2dbc-postgresql")

    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("io.projectreactor:reactor-test")
}
~~~

Kotlin DSL uses function calls and parentheses instead of Groovy's string-based syntax. Do not mix syntax from both DSLs in the same build file.

### 3.3. Using the BOM Directly in Gradle

A project may want to use the Spring Boot BOM without the dependency management plugin. Gradle natively supports platform dependencies:

~~~kotlin
dependencies {
    implementation(platform(
        "org.springframework.boot:spring-boot-dependencies:<spring-boot-version>"
    ))

    implementation("org.springframework.boot:spring-boot-starter-data-r2dbc")
    runtimeOnly("org.postgresql:r2dbc-postgresql")
}
~~~

`platform(...)` brings the version constraints in the BOM into the dependency configuration. When using this approach, ensure the BOM is applied to the right configurations/modules and does not introduce conflicting version rules at the same time.

If the project uses the Spring Boot plugin to package an executable jar or manage Boot tasks, you can continue using that plugin. Packaging plugins and dependency version management are related but distinct responsibilities.

### 3.4. Using a Version Catalog in Multi-Module Projects

A Gradle version catalog allows naming dependencies and plugins in one place, typically in `gradle/libs.versions.toml`. This helps modules use consistent dependency coordinates and reduces repetitive coordinate strings.

Example catalog:

~~~toml
[versions]
spring-boot = "<spring-boot-version>"

[libraries]
spring-boot-starter-data-r2dbc = {
    module = "org.springframework.boot:spring-boot-starter-data-r2dbc"
}
postgresql-r2dbc = {
    module = "org.postgresql:r2dbc-postgresql"
}
~~~

In a module:

~~~kotlin
dependencies {
    implementation(libs.spring.boot.starter.data.r2dbc)
    runtimeOnly(libs.postgresql.r2dbc)
}
~~~

A version catalog manages dependency names and coordinates; it does not replace a BOM. If the BOM already manages versions, do not attach an independent version to each library alias. Choose a single consistent version management strategy across the entire project.

## 4. Declaring with Maven

Maven declares dependencies inside the `dependencies` section of `pom.xml`. There are two common ways to use Spring Boot's dependency management: inheriting from `spring-boot-starter-parent` or importing the BOM inside `dependencyManagement`.

### 4.1. Inheriting the Spring Boot Parent

If the project can use the Spring Boot parent, declare the parent and dependencies as follows:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>REPLACE_WITH_SPRING_BOOT_VERSION</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>r2dbc-sample</artifactId>
    <version>1.0.0</version>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-data-r2dbc</artifactId>
        </dependency>

        <dependency>
            <groupId>org.postgresql</groupId>
            <artifactId>r2dbc-postgresql</artifactId>
            <scope>runtime</scope>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>

        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
~~~

Replace `REPLACE_WITH_SPRING_BOOT_VERSION` with the Spring Boot version chosen by your project. The parent manages many dependency versions, so dependencies covered by the BOM normally do not need a `<version>` tag.

The Maven scopes corresponding to the Gradle example:

| Maven scope | Role |
|---|---|
| `compile` (default) | Present on both compile classpath and runtime classpath; used for the starter |
| `runtime` | Needed to run the application, not needed to compile source code; appropriate for the driver when driver APIs are not referenced |
| `test` | Used only during test compilation and test runtime |
| `provided` | Dependency supplied by the runtime environment; usually not the right choice for an R2DBC driver in a standalone application |

Do not omit `<scope>runtime</scope>` just because the driver is not imported in Java code; the runtime scope accurately expresses the driver's role in this case.

### 4.2. Importing the Spring Boot BOM Without Using the Parent

A project may already inherit another parent POM or follow its own parent management convention. In that case, import the Spring Boot BOM in `dependencyManagement`:

~~~xml
<properties>
    <spring-boot.version>REPLACE_WITH_SPRING_BOOT_VERSION</spring-boot.version>
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
        <artifactId>spring-boot-starter-data-r2dbc</artifactId>
    </dependency>

    <dependency>
        <groupId>org.postgresql</groupId>
        <artifactId>r2dbc-postgresql</artifactId>
        <scope>runtime</scope>
    </dependency>
</dependencies>
~~~

In a real `pom.xml`, the property version expression must be `${spring-boot.version}`. The example uses a property so you only need to update one place when upgrading Spring Boot.

Importing the BOM only brings dependency management rules into the project. If you need to package the application as an executable jar, configure `spring-boot-maven-plugin` according to your project's build setup. The BOM does not replace the packaging functionality of the Maven plugin.

### 4.3. Managing Dependencies in Multi-Module Maven Projects

In a multi-module project, you can place the BOM and shared dependency rules in the parent POM. Child modules inherit `dependencyManagement` and declare only the dependencies they actually use in `dependencies`.

Distinguish clearly:

- `dependencyManagement` specifies default versions and metadata for a dependency when a child module declares it.
- `dependencies` actually brings the dependency into the current module and its corresponding classpath.
- Declaring a dependency in `dependencyManagement` does not mean every child module automatically uses that dependency.

For example, a module accessing PostgreSQL can declare the starter and driver; a module containing only DTOs or domain models does not need to pull in the R2DBC driver.

## 5. Choosing Drivers and Scopes by Environment

### 5.1. Application Connecting to PostgreSQL

Gradle:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-r2dbc")
    runtimeOnly("org.postgresql:r2dbc-postgresql")
}
~~~

Maven:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-r2dbc</artifactId>
</dependency>
<dependency>
    <groupId>org.postgresql</groupId>
    <artifactId>r2dbc-postgresql</artifactId>
    <scope>runtime</scope>
</dependency>
~~~

### 5.2. Application Connecting to MySQL

Replace the PostgreSQL driver with the MySQL driver:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-r2dbc")
    runtimeOnly("io.asyncer:r2dbc-mysql")
}
~~~

Do not keep multiple drivers simultaneously "just in case." Only add drivers for databases the application actually supports. If there are multiple databases, configure each corresponding connection factory explicitly and check how auto-configuration behaves in your application.

### 5.3. Using H2 for Test Environments

H2 has its own R2DBC driver:

~~~kotlin
dependencies {
    runtimeOnly("io.r2dbc:r2dbc-h2")
}
~~~

You can use H2 to test some data access flows quickly. However, H2 is not a complete substitute for PostgreSQL, MySQL, or your production database. SQL syntax, data types, isolation, locking, and driver behavior can differ. Tests that need to verify concurrency behavior should run against the target DBMS, for example using Testcontainers.

If the H2 driver is only for tests, place the dependency in `testRuntimeOnly` instead of `runtimeOnly` to avoid packaging it into the production runtime.

## 6. Connecting Dependencies to Application Configuration

After adding the starter and driver, a Spring Boot application can configure the connection using R2DBC properties. Example with PostgreSQL:

~~~yaml
spring:
  r2dbc:
    url: r2dbc:postgresql://localhost:5432/appdb
    username: app_user
    password: ${DB_PASSWORD}
~~~

The URL starts with `r2dbc:postgresql:` so the PostgreSQL R2DBC driver recognizes the protocol. The driver must be on the runtime classpath for Spring Boot to create the matching connection factory.

For MySQL, the URL uses the corresponding scheme, such as `r2dbc:mysql://localhost:3306/appdb`. Specific schemes and options must follow the driver documentation.

Do not confuse the following properties:

| R2DBC | JDBC |
|---|---|
| `spring.r2dbc.url` | `spring.datasource.url` |
| `spring.r2dbc.username` | `spring.datasource.username` |
| `spring.r2dbc.password` | `spring.datasource.password` |
| URL with `r2dbc:` scheme | URL with `jdbc:` scheme |

If you only configure `spring.datasource.*` and only add a JDBC driver, Spring Boot will configure JDBC when the appropriate dependencies are present; that does not create an R2DBC connection.

It is generally unnecessary to declare `driver-class-name` like traditional JDBC setups. R2DBC drivers are typically discovered through the SPI mechanism and the URL scheme. Only add separate configuration when required by driver documentation or multi-database setups.

Passwords should not be committed to shared configuration files. Use environment variables, a secret manager, or your deployment platform's secure configuration mechanism.

## 7. When Not to Use the Spring Boot Starter?

A standalone Spring Framework application or library can declare Spring Data R2DBC directly instead of using the Spring Boot starter. In that case, the dependency set typically includes:

- `org.springframework.data:spring-data-r2dbc` for repositories and data mapping.
- Spring R2DBC for connection integration and R2DBC operations.
- The R2DBC SPI and database driver.
- Reactor Core for the reactive publisher types used by Spring Data.
- Required Spring Framework components for context, configuration, and transaction management.

Many foundational dependencies are pulled in transitively by Spring Data R2DBC. Do not add individual artifacts from an arbitrary list and pick independent versions. Use the compatible Spring Data BOM and align with Spring Framework and driver versions.

When using Spring Boot, the starter is the simpler and more maintainable choice for typical applications. Only declare dependencies manually when there is a specific architectural reason, such as integrating into a non-Boot Spring Framework application or building a library with tightly controlled dependency boundaries.

## 8. Dependencies for Testing

R2DBC applications commonly need to test publishers and database interactions.

Some useful dependencies:

| Dependency | Purpose |
|---|---|
| `spring-boot-starter-test` | JUnit, Spring Test, AssertJ, and common testing libraries |
| `io.projectreactor:reactor-test` | `StepVerifier` and tools for testing Reactor publishers |
| R2DBC driver for the test database | Connects to the database in integration tests |
| Testcontainers for the target database | Launches an isolated database close to the production environment |

Gradle:

~~~kotlin
dependencies {
    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("io.projectreactor:reactor-test")
    testRuntimeOnly("io.r2dbc:r2dbc-h2")
}
~~~

This snippet illustrates testing with H2; if integration tests use PostgreSQL in Testcontainers, declare the appropriate Testcontainers module and the PostgreSQL R2DBC driver on the test runtime or runtime classpath depending on how tests launch the application.

Do not place test-only libraries into `implementation` or production dependencies if there is no actual runtime need.

## 9. Verifying Resolved Dependencies

Declaring dependencies in the build file is only the first step. You need to confirm that Gradle or Maven downloaded the right artifacts and chose compatible versions.

### 9.1. Checking with Gradle

View all runtime dependencies:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

On Windows you can use the `gradlew.bat` wrapper:

~~~powershell
.\gradlew.bat dependencies --configuration runtimeClasspath
~~~

Find a specific dependency and why Gradle selected its version:

~~~bash
./gradlew dependencyInsight --dependency r2dbc-postgresql --configuration runtimeClasspath
~~~

`dependencyInsight` is useful when multiple libraries request different versions. Its output shows which dependency pulled the artifact in and which rule caused Gradle to pick the final version.

### 9.2. Checking with Maven

View the dependency tree:

~~~bash
./mvnw dependency:tree
~~~

You can filter by artifact groups to make the output easier to read:

~~~bash
./mvnw dependency:tree -Dincludes=org.springframework.boot,org.springframework.data,io.r2dbc,org.postgresql
~~~

On Windows use `mvnw.cmd` if the project provides the Maven Wrapper.

Inspecting the dependency tree helps detect duplicate starter declarations, accidentally added JDBC drivers, or a library transitively pulling in an unexpected version.

### 9.3. Checking at Runtime

After dependencies are resolved:

1. Verify the R2DBC driver is on the runtime classpath.
2. Check that the URL scheme matches the driver.
3. Start the application and check for errors creating the connection factory or connecting to the database.
4. Run a simple repository query to confirm the driver, credentials, and database work.
5. For integration tests, verify that tests actually use the intended database rather than accidentally connecting to another local database.

The error `Failed to determine a suitable R2DBC Connection URL` is typically related to a missing or incorrect URL property. Errors about no provider/driver found are usually related to a missing driver on the classpath or a scheme unsupported by the driver. Authentication or network connection errors require checking credentials, hostname, port, database name, and access permissions.

## 10. Common Dependency Declaration Mistakes

| Mistake | Cause | How to fix |
|---|---|---|
| Adding only `spring-boot-starter-data-r2dbc` without a driver | The starter does not select a specific database driver | Add the R2DBC driver for the DBMS in use |
| Adding a JDBC driver instead of an R2DBC driver | The two drivers implement different APIs | Use the corresponding R2DBC artifact |
| Declaring `spring-data-r2dbc` separately alongside the Boot starter | Duplicate module and risk of version drift | Use the starter or manage the entire stack yourself; avoid overlapping declarations |
| Manually setting versions for individual Spring libraries | Modules may become incompatible | Use the Spring Boot BOM or the corresponding BOM |
| Placing the driver in test scope when the application needs to run in production | The driver is absent from the production runtime | Use Gradle `runtimeOnly` or Maven `runtime` |
| Placing test dependencies in production compile/runtime scope | Adds unnecessary dependencies | Move them to `testImplementation` or Maven `test` |
| Configuring `spring.datasource.url` for an R2DBC-only application | That property belongs to JDBC configuration | Use `spring.r2dbc.url` with the `r2dbc:` scheme |
| Adding multiple unnecessary drivers | Cluttered classpath, harder to predict auto-configuration | Declare only drivers supported by the application |
| Testing with H2 and assuming identical production behavior | Differences between databases and drivers | Run integration tests against the target database |
| Treating a version catalog as if it manages the BOM itself | A catalog mainly defines dependency names and coordinates | Combine the version catalog with a BOM or explicit version rules |

## 11. Dependency Declaration Workflow for a New Project

When starting a Spring Data R2DBC application, you can follow this order:

1. Identify the database management system and supported R2DBC driver.
2. Identify the Spring Boot version the project uses, or the Spring Data/Spring Framework versions if not using Boot.
3. Choose a single consistent version management mechanism, preferring the Spring Boot BOM for Boot applications.
4. Add `spring-boot-starter-data-r2dbc` as a compile dependency.
5. Add the database's R2DBC driver as a runtime dependency.
6. Add testing libraries to test dependencies, and a separate test driver if needed.
7. Configure the URL, username, and password using `spring.r2dbc.*` properties.
8. Inspect the runtime dependency tree and start the application to confirm the driver is loaded.
9. Write integration tests against a database compatible with the deployment environment.

## 12. Key Takeaways

- Spring Boot applications using Spring Data R2DBC usually start with `spring-boot-starter-data-r2dbc`.
- The starter provides Spring Data and reactive integration; the database's R2DBC driver must be declared separately.
- The PostgreSQL JDBC driver and PostgreSQL R2DBC driver are two different artifacts.
- Use the Spring Boot BOM to keep versions synchronized; avoid upgrading Spring Data, Spring Framework, Reactor, or the R2DBC SPI individually without checking compatibility.
- In Gradle, the starter is typically `implementation`, the driver is `runtimeOnly`, and test libraries are `testImplementation`.
- In Maven, the starter defaults to compile scope, the driver is typically `runtime`, and test libraries are `test`.
- R2DBC connection URLs use the `r2dbc:` scheme, and Spring Boot configuration lives under `spring.r2dbc`.
- Inspecting the dependency tree and running integration tests helps catch missing drivers, version mismatches, and JDBC/R2DBC confusion before deployment.

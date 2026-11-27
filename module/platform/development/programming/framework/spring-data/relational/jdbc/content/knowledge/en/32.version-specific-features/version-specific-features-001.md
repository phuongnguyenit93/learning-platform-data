# Reading Release Trains, Release Notes, and the Spring Boot Compatibility Matrix

In **Spring Data Relational JDBC**, library versions directly affect repository APIs, mapping, transaction integration, custom conversions, and JDBC features. When upgrading or creating a new project, do not pick a standalone `spring-data-jdbc` version simply because it is the latest on Maven Central. You need to identify the Spring Boot version in use, the corresponding Spring Data release train, the Spring Framework version managed by Boot, the minimum Java version, and the JDBC driver compatible with the database.

Three sources of information must be read together:

- **Release train:** indicates the group of Spring Data versions released and managed together.
- **Release notes/changelog:** describes new features, behavior changes, deprecations, bug fixes, and migration instructions.
- **Compatibility matrix/system requirements:** indicates the supported platform versions, especially Spring Boot, Spring Framework, Java, and Spring Data modules.

Spring Boot provides dependency management to select a set of versions that have been tested together. In a Boot-based application, the safe approach is usually to let Boot manage Spring Data JDBC and related Spring libraries, and only add the appropriate JDBC driver for the database. When upgrading, read the release notes for both Boot and Spring Data instead of checking only a single changelog in isolation.

## 1. Distinguishing Version Types

The Spring ecosystem has multiple projects with their own release cycles. A version number can represent Boot, Framework, the Data release train, a Spring Data module, or a JDBC driver.

| Component | Version notation example | Role |
| --- | --- | --- |
| Spring Boot | 3.5.x, 4.0.x | Application platform, auto-configuration, and dependency management |
| Spring Framework | 6.2.x, 7.0.x | Container, transactions, JDBC abstraction, and core APIs |
| Spring Data release train | 2025.0, 2025.1 | Synchronized version group of Spring Data modules |
| Spring Data JDBC | 3.x.y | Specific JDBC repository/mapping module |
| Spring Data Relational | 3.x.y | Shared relational mapping and infrastructure |
| Spring Data Commons | 3.x.y | Repository abstraction, paging, auditing, and shared components |
| JDBC driver | Vendor-specific version for PostgreSQL/MySQL/Oracle/... | Connection and data conversion between JDBC and the database |
| Java | 17, 21, 25, ... | JDK for running and compiling the application |

The version examples in the table only illustrate version formats, not a guarantee that every combination is compatible. A Spring Data module may use version 3.x, while the release train is named by year such as 2025.0. **A release train name is neither a module version nor a Spring Boot version.**

When reading an announcement like “Spring Data 2025.0”, do not assume the dependency to declare is `spring-data-jdbc:2025.0`. Open the release train page or BOM to find the actual module version.

## 2. What Is a Spring Data Release Train?

Spring Data consists of many modules, such as Spring Data Commons, Spring Data Relational, Spring Data JDBC, Spring Data JPA, Spring Data MongoDB, Spring Data Redis, and other integration modules.

These modules share the repository abstraction, mapping concepts, and several common dependencies. If each module is upgraded independently without following a tested set of versions, API mismatches or dependency incompatibilities can occur.

A **release train** groups Spring Data module versions into a synchronized release. A release train typically provides a BOM to manage the versions of the modules belonging to that train.

~~~text
Spring Data release train
        │
        ├── Spring Data Commons
        ├── Spring Data Relational
        ├── Spring Data JDBC
        ├── Spring Data JPA
        └── Other Spring Data modules
~~~

An application that only uses Spring Data JDBC does not need to declare every module in the train. However, when multiple Spring Data modules are needed, the BOM keeps their versions compatible with one another.

### 2.1. A Release Train Is Not a Library

A release train is the name/label of a release set. The actual dependency is still an artifact such as:

~~~xml
<dependency>
    <groupId>org.springframework.data</groupId>
    <artifactId>spring-data-jdbc</artifactId>
</dependency>
~~~

When using dependency management, the artifact version is taken from the BOM/parent instead of being specified directly on the dependency. This reduces the risk of accidentally pulling in a module from another train.

### 2.2. Module Versions Change with the Release Train

Spring Data modules use their own versions, typically with major/minor/patch numbers following the train's release cadence. Therefore:

- A single release train can manage multiple different artifact versions.
- The `spring-data-jdbc` version does not necessarily match the `spring-data-jpa` version.
- Do not infer a train version simply by dropping a dot or changing the year.
- Do not use a module version from a new train with Commons/Relational from an old train unless official documentation confirms that combination.

When you need to determine the exact version, use the BOM or the dependency versions page of the selected Spring Boot release.

## 3. How Does Spring Boot Manage Spring Data?

Spring Boot publishes a BOM named `spring-boot-dependencies`. This BOM manages versions for many dependencies commonly used by Boot applications, including Spring Framework, Spring Data, logging, JSON libraries, and integration libraries.

With Spring Boot, dependency management is a key layer for keeping components compatible:

~~~text
Spring Boot version
       │
       ▼
spring-boot-dependencies BOM
       │
       ├── Spring Framework version
       ├── Spring Data release train / module versions
       ├── Spring Data JDBC
       ├── Spring Data Relational
       ├── Spring Data Commons
       └── Other managed dependencies
~~~

When upgrading Boot, the BOM typically updates the entire group of dependencies together. This avoids changing only Spring Data JDBC while leaving an incompatible Commons or Framework version behind.

### 3.1. Spring Boot Starter and Managed Versions

In a Spring Boot application, you typically add the starter:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-jdbc</artifactId>
</dependency>
~~~

The starter brings in the required dependencies for Spring Data JDBC. The JDBC driver is usually declared separately according to the database, for example PostgreSQL:

~~~xml
<dependency>
    <groupId>org.postgresql</groupId>
    <artifactId>postgresql</artifactId>
    <scope>runtime</scope>
</dependency>
~~~

Do not specify an explicit version for the starter or driver if the Boot BOM manages that version, unless there is a specific reason and compatibility has been verified. If Boot does not manage a needed driver version, declare the version according to the driver's official documentation.

### 3.2. Maven with the Spring Boot Parent

Example using the Spring Boot parent. Version 3.5.0 here is only a syntax example to illustrate dependency management; a project must replace it with a GA release selected from the current compatibility matrix:

~~~xml
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.0</version>
    <relativePath/>
</parent>

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
~~~

Here, you do not need to write a version for the starter. The parent provides dependency management to select the appropriate version.

### 3.3. Maven Without Using the Boot Parent

If a project does not inherit from `spring-boot-starter-parent` but still uses Spring Boot, it can import the BOM:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-dependencies</artifactId>
            <version>3.5.0</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Then declare the starter/dependencies without versions as in the example above. If importing additional BOMs, you must understand Maven's dependency management precedence order; avoid letting multiple BOMs unintentionally override each other.

### 3.4. Gradle with the Spring Boot Plugin

Gradle Groovy DSL example:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.0'
    id 'io.spring.dependency-management' version '1.1.7'
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-jdbc'
    runtimeOnly 'org.postgresql:postgresql'
}
~~~

The Boot plugin works with dependency management to apply Boot-managed versions. If a project uses Gradle native BOM/platform support instead of the dependency management plugin, declare the appropriate platform and inspect the actual resolution result.

Do not mix multiple version management mechanisms unless you understand the precedence among plugins, platforms, constraints, version catalogs, and dependency substitution.

## 4. Spring Boot and Spring Data Compatibility Matrix

The compatibility matrix answers the question: which set of Spring Framework and Spring Data versions is a given Boot release built with? The most reliable source for a Boot application is the dependency versions appendix/BOM of that exact Boot version.

When reading the matrix, identify:

1. The exact Spring Boot version, including major/minor/patch.
2. The Spring Framework version managed by Boot.
3. The Spring Data release train managed by Boot.
4. The module versions for `spring-data-jdbc`, `spring-data-relational`, and `spring-data-commons`.
5. The minimum Java version and supported JDK versions.
6. The supported driver/database versions according to the vendor's documentation.

Example compatibility record table for a project:

| Component | Project version | Confirmation source |
| --- | --- | --- |
| Spring Boot | Selected GA release | Boot dependency versions / system requirements |
| Spring Framework | Version managed by Boot BOM | Boot dependency versions |
| Spring Data train | Train managed by Boot BOM | Boot BOM / Spring Data release train |
| Spring Data JDBC | Version managed by BOM | Effective POM / Gradle dependency report |
| Spring Data Relational | Version managed by BOM | Effective POM / Gradle dependency report |
| Spring Data Commons | Version managed by BOM | Effective POM / Gradle dependency report |
| Java | Runtime and compile JDK | Boot system requirements |
| JDBC driver | Selected version | Driver documentation and Boot BOM if present |
| Database server | Environment version | Vendor/database support matrix |

Do not copy a compatibility table from an old blog or article if you do not know which Boot release it applies to. The matrix can change between major/minor releases.

### 4.1. Checking the Java Baseline

Spring Boot specifies a minimum Java version for each release line. Spring Framework and Spring Data also have their own runtime requirements. The application must satisfy the requirements of the entire stack, especially the Boot version in use.

Check at least three places:

- The Java runtime used to run the application.
- The Java toolchain/source compatibility used for compilation.
- The JDK installed in CI and production environments.

Maven example:

~~~xml
<properties>
    <java.version>17</java.version>
</properties>
~~~

This is a configuration example, not the Java requirement for every Boot version. Obtain the Java baseline from the system requirements page of the exact Boot release.

Gradle example:

~~~groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
~~~

Setting source/target to a newer JDK does not guarantee that the production runtime has the matching JDK. CI and production images/containers must use a compatible runtime.

### 4.2. Checking the JDBC Driver and Database

The Boot BOM may manage the JDBC driver version, but that does not replace the database vendor's support matrix. You should verify:

- Does the driver version support the running JDK?
- Does the driver support the deployed database server version?
- Does the driver support the data types used by the application such as JSONB, UUID, enum, array, or timestamp?
- Do URL/timeout/pooling properties match the driver?
- Does the database server support the SQL syntax and features used by Spring Data JDBC queries?

For example, an application may resolve dependencies successfully, yet an older driver might not properly support the PostgreSQL type expected by a converter. A successful build does not mean runtime compatibility has been verified.

## 5. Finding Release Notes for the Exact Version

Do not read a generic changelog and assume every item applies to your project. Identify the current version and the target version, then read the release notes for each relevant project.

For a Spring Data JDBC upgrade, the sources to check include:

| Source | What to read |
| --- | --- |
| Spring Boot release notes | Dependency upgrades, auto-configuration changes, migration guide |
| Spring Data release train notes | Overall train changes, new modules, compatibility |
| Spring Data Relational release notes | Mapping, aggregate persistence, converters, auditing, dialect |
| Spring Data JDBC release notes/changelog | Repositories, query methods, JDBC-specific changes |
| Spring Data Commons release notes | Repository abstraction, projections, paging, auditing, events |
| Spring Framework release notes | Transactions, JDBC support, bean/container behavior |
| JDBC driver release notes | JDK support, protocol, type mapping, security fixes |
| Database release notes | SQL behavior, deprecated features, server compatibility |

A change in Commons can affect Spring Data JDBC even if the JDBC module changelog does not repeat it. Similarly, changes in Spring Framework can affect transactions or infrastructure used by Spring Data JDBC.

### 5.1. Reading Across the Version Range, Not Just the Latest Release

Suppose a project is on Boot 3.3.x and plans to upgrade to 3.5.x. Reading workflow:

1. Read Boot migration/release notes from the current line to the target line.
2. Identify the Spring Framework and Spring Data versions managed by the target Boot release.
3. Read the Spring Data train release notes that the project passes through.
4. Read the Spring Data JDBC/Relational/Commons notes for any relevant changes.
5. Read the driver release notes if the Boot BOM changes the driver or the application needs a driver upgrade.
6. Check database server changes if the database version is also part of the upgrade plan.

If crossing multiple release trains, do not read only the target train's notes. A deprecation may appear in an earlier train and be removed in a later train; intermediate migration notes can contain critical guidance.

### 5.2. Searching for Items Relevant to the Application

When reading release notes, prioritize keywords matching your codebase:

- JDBC, Relational, Repository, Aggregate.
- Mapping, Converter, JdbcValue, Dialect.
- Query, `@Query`, Pageable, Sort, Limit.
- Transaction, Optimistic Locking, `@Version`.
- Auditing, Callbacks, Events.
- Java, JDK, Spring Framework, Spring Boot.
- Deprecated, Breaking, Removed, Migration.

Do not search only by the class names you directly use. A change in dependencies, default configuration, or database dialect can affect the application even if your code does not directly import that class.

## 6. Distinguishing New Features, Deprecations, and Breaking Changes

Release notes typically contain several kinds of changes. Distinguish them to estimate upgrade effort.

| Change type | Meaning | Action |
| --- | --- | --- |
| Feature | New API/capability available | Adopt only if the application needs it |
| Bug fix | Incorrect behavior fixed | Check if old workarounds should be removed |
| Dependency upgrade | Dependent library upgraded | Check compatibility and CVEs |
| Deprecation | API still exists but replacement is recommended | Plan migration |
| Behavior change | API may stay the same while result/behavior changes | Write tests for the affected behavior |
| Breaking change | Old API or contract is no longer compatible | Update code/configuration before production upgrade |
| Removal | Old API/dependency removed | Find all usages and migration paths |
| Security fix | Vulnerability patched | Assess priority and apply appropriate patch |

### 6.1. Deprecation Is Not Removal

An API marked deprecated still compiles and runs, though the application should move to the recommended API. You do not have to delete every deprecated API immediately if the migration is broad; read the rationale and expected removal timeline.

When an API is removed in a new release, compile errors usually point to direct call sites. However, behavior changes may not cause compile errors, so tests and release notes remain essential.

### 6.2. Checking Behavior Changes

For example, a new release may change:

- How Spring Data detects new entities.
- How query derivation parses method names.
- How converters select a JDBC type.
- How auditing updates fields on insert.
- How a dialect generates SQL for pagination or generated keys.
- How optimistic locking reports errors.

Compiling without errors does not guarantee the behavior matches the previous version. Write focused tests for areas with changes noted in the release notes.

## 7. GA, Milestone, Release Candidate, and Snapshot

Spring projects may publish pre-GA stages:

| Stage | Meaning | Where to use |
| --- | --- | --- |
| Snapshot | Continuously changing development build | Experimentation, intentional internal CI |
| Milestone (M) | Preview build at a development milestone | Evaluating upcoming features |
| Release Candidate (RC) | Near-final build for pre-GA verification | Compatibility testing, pre-release feedback |
| General Availability (GA) | Official release | Standard choice for production |
| Service release/patch | Patch within the same release line | Bug/security updates per project policy |

Versions with suffixes like `-SNAPSHOT`, `-M1`, `-RC1` do not have the same stability level as GA releases. Do not use a snapshot just to get a newer API if the application requires production stability.

For production, choose a supported GA/patch release and follow Spring's support policy. If you must use a pre-release to evaluate a feature, isolate it in a branch or test environment and document the risk clearly.

## 8. Checking the Actual Version Resolved by the Build

`pom.xml` or `build.gradle` states declared requirements, but the actual version can be altered by a parent, BOM, plugin, constraint, version catalog, or dependency conflict resolution.

Therefore, after reading the matrix and choosing a Boot version, inspect the resolved dependency graph.

### 8.1. Maven

Display the dependency tree for Spring Data:

~~~bash
./mvnw dependency:tree -Dincludes=org.springframework.data
~~~

Check Spring Framework specifically:

~~~bash
./mvnw dependency:tree -Dincludes=org.springframework
~~~

Generate the effective POM to see parent/BOM and dependency management after Maven merges them:

~~~bash
./mvnw help:effective-pom
~~~

If a dependency has an unexpected version, inspect which dependency path brings it in and which dependency management entry overrides it. Do not add a version override just to make the build pass without understanding the source of the conflict.

### 8.2. Gradle

Check the Spring Data JDBC version:

~~~bash
./gradlew dependencyInsight --dependency spring-data-jdbc --configuration runtimeClasspath
~~~

Check Commons or Relational:

~~~bash
./gradlew dependencyInsight --dependency spring-data-commons --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-data-relational --configuration runtimeClasspath
~~~

`dependencyInsight` explains which dependency requested the version and why Gradle selected the final version. This is how you detect a version overridden by a constraint or another dependency.

### 8.3. Checking the JDBC Driver

Maven:

~~~bash
./mvnw dependency:tree -Dincludes=org.postgresql:postgresql
~~~

Gradle:

~~~bash
./gradlew dependencyInsight --dependency postgresql --configuration runtimeClasspath
~~~

Substitute the coordinates for your actual driver. Compare the resolved version with the version managed by the Boot BOM and the vendor's support matrix.

## 9. Common Errors Caused by Version Mismatches

| Symptom | Possible cause | How to investigate |
| --- | --- | --- |
| `NoSuchMethodError` | Runtime loads a different class version than compile time | Check the dependency tree and runtime classpath |
| `NoClassDefFoundError` | Required module is missing or version no longer has that class | Check transitive dependencies and release notes |
| `ClassNotFoundException` | Code/config references a class absent from running artifacts | Identify the JAR containing the class and its actual version |
| `AbstractMethodError` | API/interface changed while an implementation or old dependency is out of sync | Check Spring modules from the same train |
| Auto-configuration/repository bean error | Boot, Framework, and Data are not a compatible combination | Compare against the Boot BOM and dependency appendix |
| `UnsupportedClassVersionError` | Runtime JDK is lower than bytecode target | Check build JDK and production JDK |
| Driver rejects data type | Driver version or database type mapping is incompatible | Check driver release notes and JDBC types |
| SQL syntax/feature error | Database server/dialect does not support generated SQL | Check database version and dialect |
| Paging/locking behavior changed | Behavior change in module or dialect | Read release notes and run integration tests |
| Build uses one version but production uses another | Inconsistent packaging/container/classpath | Inspect dependency report and deployed artifact contents |

Do not fix a `NoSuchMethodError` by adding a random new dependency. First identify which class is being loaded and which artifact version provides it.

## 10. Process for Upgrading Spring Boot and Spring Data JDBC

A controlled upgrade should follow a clear sequence:

1. **Record baseline:** current Boot, Framework, Data train, Spring Data JDBC/Relational/Commons, Java, driver, and database server versions.
2. **Select target version:** choose only a supported GA release, based on system requirements and the target Boot dependency matrix.
3. **Read release notes:** read the Boot migration guide, Spring Data train notes, JDBC/Relational/Commons module notes, and driver notes across the upgrade range.
4. **Update dependency management:** upgrade the Boot parent/plugin/BOM; let Boot manage Spring Data modules if the application uses Boot.
5. **Remove old overrides:** check whether direct version declarations for Spring Framework, Commons, Relational, or JDBC are still needed.
6. **Check Java:** align the JDK across developer machines, CI, build toolchain, and production runtime.
7. **Inspect dependency graph:** use Maven dependency tree/effective POM or Gradle `dependencyInsight`.
8. **Compile and test:** focus on repositories, mapping, converters, queries, auditing, transactions, and optimistic locking.
9. **Test against a real database:** use the same database engine/driver and migrations as the deployment environment.
10. **Verify operations:** pool, metrics, timeouts, connection behavior, and production configuration.
11. **Roll out in stages:** staging/canary before broad rollout, with a rollback plan compatible with schema and data.

Upgrading library versions and upgrading the database server are two separable changes. If you change both at once, errors are harder to attribute. When possible, upgrade one layer at a time and test between steps.

## 11. Example: A Project Wants to Upgrade Spring Data JDBC

Suppose a project uses Spring Boot and depends on `spring-boot-starter-data-jdbc`. The development team wants to use a new Spring Data JDBC API.

### Step 1: Identify Which Module/Version Has the API

Look up the API in the Spring Data JDBC Javadoc/reference documentation. Identify the first version that includes the API and which release train it belongs to. Do not rely solely on a blog post or forum answer.

### Step 2: Identify Which Boot Version Manages That Train

Open the dependency versions appendix for each candidate Boot line. Check which Spring Data train and `spring-data-jdbc` version the Boot BOM manages.

### Step 3: Check Java and Framework

If the target Boot version requires a newer Java version, update the JDK for developers, CI, and production. Confirm that internal libraries and other agents/runtimes are compatible.

### Step 4: Upgrade the Boot BOM

Prefer upgrading the Boot parent/plugin/BOM so the entire stack moves to the Boot-managed combination. Do not just add a new `spring-data-jdbc` version alongside older Commons/Relational artifacts.

### Step 5: Read Migration Notes

Look for breaking changes/deprecations in Boot, Framework, the Spring Data train, and the JDBC module. Update code/configuration per the migration guide before deployment.

### Step 6: Inspect the Dependency Graph

Confirm that Spring Data JDBC, Relational, and Commons align with the expected BOM combination. Verify the driver version and database compatibility separately.

### Step 7: Test JDBC Use Cases

Run representative tests: insert/update aggregates with children, derived queries and `@Query`, projections/DTOs, custom conversions, optimistic locking and `@Version`, auditing, transaction rollback, pagination/sorting, and dialect-specific SQL.

### Step 8: Deploy to Staging

Use migrations and a database engine close to production. Monitor logs, pool metrics, query latency, mapping errors, and transactions. Only roll out to production after results stabilize.

## 12. When Should You Override Versions Outside the Boot BOM?

In a Boot application, avoid overriding individual versions for `spring-data-jdbc`, `spring-data-relational`, or `spring-data-commons` just to get a new feature. Overrides can create combinations that Boot has not tested.

Situations where an override may be necessary:

- The Boot BOM has not yet included a required security patch.
- A bug has been fixed in a patch release and Spring confirms an appropriate override approach.
- A driver dependency needs a newer patch than the one managed by Boot.
- The application has a special compatibility requirement documented in official guidance.

When overriding:

1. Identify the exact dependency to override and why.
2. Check compatibility with related Spring modules.
3. Use an appropriate GA/patch version; do not arbitrarily pull modules from another train.
4. Record the override clearly in centralized dependency management.
5. Inspect the dependency graph after resolution.
6. Run integration tests against the target database.
7. Plan to remove the override once the Boot BOM includes the patch.

If the application needs to upgrade multiple Spring Data modules together, consider upgrading Boot to the line managing that release train instead of manually assembling individual artifacts.

## 13. Official Sources to Use

| Source | Used to answer |
| --- | --- |
| Spring Boot system requirements | Boot's Java baseline and runtime requirements |
| Spring Boot dependency versions | Which versions Boot manages for Framework, Data, and drivers |
| Spring Boot release notes/migration guide | Changes when upgrading Boot |
| Spring Data release trains | Current trains, modules, and compatibility |
| Spring Data Relational reference/release notes | Features and changes in JDBC/Relational |
| Spring Framework release notes | Core platform, JDBC, and transaction changes |
| JDBC driver release notes | JDK/database support, protocol, and type mapping |
| Database vendor support matrix | Supported server/driver versions |

Reference URLs:

- [Spring Boot — System Requirements](https://docs.spring.io/spring-boot/system-requirements.html): Java and build tool requirements by Boot version.
- [Spring Boot — Dependency Versions](https://docs.spring.io/spring-boot/appendix/dependency-versions/coordinates.html): dependency versions managed by Boot.
- [Spring Boot — Managing Dependencies](https://docs.spring.io/spring-boot/reference/using/build-systems.html#using.build-systems.dependency-management): how to use parent/BOM and dependency management.
- [Spring Data — Project and Release Trains](https://spring.io/projects/spring-data): Spring Data modules and release trains.
- [Spring Data Relational Reference](https://docs.spring.io/spring-data/relational/reference/): Spring Data JDBC/Relational documentation.
- [Spring Data Relational — Release History](https://github.com/spring-projects/spring-data-relational/releases): release notes by project tag.
- [Spring Boot — Release History](https://github.com/spring-projects/spring-boot/releases): release notes and changes per release.
- [PostgreSQL JDBC Driver Documentation](https://jdbc.postgresql.org/documentation/): driver configuration, type mapping, and compatibility.

Always select the documentation page for the exact major/minor version when Spring provides a version selector. The `current` page is useful for reading the latest release, but it may describe APIs that differ from the running application.

## 14. Common Mistakes When Reading Versions and Release Notes

| Mistake | Consequence | How to avoid |
| --- | --- | --- |
| Thinking a release train is an artifact version | Declaring the wrong dependency version | Look up module versions in the BOM |
| Upgrading Spring Data JDBC alone | Commons/Relational version mismatch | Let Boot BOM or Spring Data BOM manage them together |
| Using the latest version on Maven Central | May exceed Boot's supported combination | Choose from the target Boot matrix |
| Reading only the JDBC changelog | Missing changes from Commons/Relational/Framework | Read notes across the entire dependency stack |
| Using the `current` page to infer old-version APIs | Code fails to compile or behaves differently | Open docs for the exact version |
| Confusing a patch release with a minor/major migration | Missing breaking changes | Check the version range and migration guide |
| Using milestone/snapshot in production | Unstable builds or shifting dependencies | Prefer supported GA releases |
| Treating build success as full compatibility | Runtime/driver/database errors can still happen | Run integration tests with a real database and driver |
| Checking versions only in build files | Missing dependency conflicts | Inspect effective POM/`dependencyInsight` |
| Upgrading libraries without upgrading the JDK | Runtime cannot load new bytecode | Align build, CI, and production JDKs |

## 15. Checklist Before Selecting or Upgrading a Version

Before changing dependencies, answer these questions:

1. What are the current Boot version and the target version?
2. Which Spring Framework and Spring Data release train does the target Boot manage?
3. What are the actual module versions of Spring Data JDBC/Relational/Commons?
4. Do the Java runtime and build JDK meet system requirements?
5. Does the JDBC driver version support the JDK and database server?
6. Have release notes for Boot, Framework, the Data train, and the driver been read across the entire upgrade range?
7. Are there deprecations/removals or behavior changes affecting the codebase?
8. Is any dependency overridden by a parent, BOM, constraint, or version catalog?
9. Does the resolved dependency graph match the intended combination?
10. Have integration tests run against the target database/driver?
11. Is there a data migration and rollback plan if the schema changes?
12. Are release support timelines and security advisories tracked for the chosen version?

## 16. Practice Exercises

**Exercise 1 — Reading the dependency BOM.** Choose a Spring Boot GA version. Open the dependency versions appendix and record the managed Spring Framework, Spring Data JDBC, Spring Data Relational, Spring Data Commons, and JDBC driver versions.

**Exercise 2 — Identifying the release train.** From the Spring Data JDBC version in the BOM, find the corresponding release train on the Spring Data page. Explain why module versions do not necessarily match the train name.

**Exercise 3 — Reading release notes.** Choose two consecutive release trains. Find one feature, one bug fix, one deprecation, and one breaking/behavior change that could affect a JDBC application.

**Exercise 4 — Checking the Java baseline.** Read the system requirements for the chosen Boot version. Compare with the JDK on your machine, CI, and production runtime; note any incompatibilities.

**Exercise 5 — Maven dependency tree.** Create a project using `spring-boot-starter-data-jdbc`. Run `dependency:tree` and `help:effective-pom`; locate the resolved Spring Data JDBC/Relational/Commons versions.

**Exercise 6 — Gradle dependencyInsight.** Create the same setup with Gradle. Run `dependencyInsight` for `spring-data-jdbc` and explain why Gradle chose that version.

**Exercise 7 — Detecting an override.** Add an experimental version override for one Spring Data module on a separate branch. Observe how the dependency graph changes and explain the risks when a module drifts from the train. Then remove the override.

**Exercise 8 — Planning an upgrade.** Choose an older Boot version and a newer GA Boot version. Read migration notes across the upgrade range, list code/configuration to inspect, and list the integration tests to run.

**Exercise 9 — Driver compatibility.** Choose the PostgreSQL/MySQL/SQL Server driver in use. Consult the driver documentation to confirm JDK, database server, and required application data type support.

**Exercise 10 — Creating a compatibility matrix.** Write a version table for Boot, Framework, Data train, Data JDBC, Java, JDBC driver, and database server. Attach official source links and the verification date.

### Conclusion

Reading versions properly means reading an entire dependency ecosystem. Start from the Spring Boot version, use the BOM to identify Spring Framework and Spring Data module versions, then read release notes across the entire upgrade range and confirm Java/driver/database compatibility via official documentation. Finally, inspect the resolved dependency graph and run integration tests against the target database. This process avoids ending up with a single dependency on a new version while the overall stack is incompatible.

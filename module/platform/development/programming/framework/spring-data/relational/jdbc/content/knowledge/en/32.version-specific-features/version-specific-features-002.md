# Matching APIs in Use with Version-Specific Documentation

An API may appear across multiple generations of Spring Data JDBC, yet method signatures, packages, return types, default behaviors, and compatibility requirements can change by version. An example on the latest documentation page may not work in a project running an older version.

When looking up an API, answer two questions in strict order:

1. **Which version is the project actually loading?** You must check resolved dependencies, not just the version declared directly in a build file.
2. **Does the documentation you have open describe that exact version?** Reference documentation explains concepts and usage; Javadoc confirms API signatures; release notes and upgrade notes show what changed between versions.

This lesson explains how to identify the Spring Data Relational/JDBC and Spring Framework versions in a project, select the right documentation branch, verify a specific API, compare differences across versions, and handle cases where code snippets on the Internet no longer match your current dependencies.

> **Reference date for examples in this lesson: 13-11-2026.** At this point, Spring Data Relational 4.1.2 is the current stable release in the Spring Data 2026.0.2 release train. The Getting Started guide for the 4.1.2 branch requires Spring Framework 7.0.10 or higher. These numbers are dated illustrative benchmarks, not values to copy blindly into every project.

## 1. Why Must You Consult Version-Specific Documentation?

Suppose a project uses Spring Data JDBC 3.5.x. You search online and open an example from the 4.1.x documentation. The new page may show an API or configuration style that is valid in the new version, whereas the older project may:

- Not yet have the illustrated class or method.
- Have a method with the same name but a different overload or return type.
- Use a different package.
- Have a different default behavior.
- Require a different Spring Framework version.
- Have a bug that was fixed in the new version but still exists in the project's version.
- Have changed how configuration or integration with other libraries works.

For example, when reading about **`JdbcClient`**, remember that it is a Spring Framework API in the `org.springframework.jdbc.core.simple` package, not an API defined by Spring Data JDBC. Knowing which Spring Data JDBC version a project uses is not enough to conclude `JdbcClient` is available; you need to check the actual `spring-jdbc` version.

Similarly:

- **`@Version`** belongs to Spring Data Commons.
- **`@Query`** and **`@Modifying`** for JDBC repositories belong to Spring Data Relational/JDBC.
- **`@Transactional`** belongs to Spring Framework.
- **`JdbcClient`** belongs to Spring Framework JDBC.

A Spring Data JDBC project typically uses multiple modules simultaneously. Therefore, consult the documentation of the specific module that owns the API you are using.

### 1.1. Common Mismatches

| Mismatch | Example | Consequence |
|---|---|---|
| Wrong module version | Using a 4.1 example for a 3.5 dependency | Code fails to compile or behaves differently |
| Wrong module | Looking up a JPA API to apply to JDBC | Using the wrong annotation or semantics |
| Wrong framework layer | Assuming `JdbcClient` belongs to Spring Data JDBC | Checking the wrong artifact |
| Wrong release stage | Using snapshot or milestone docs | Relying on an unstable API |
| Wrong actual dependency | Build file declares one version while BOM resolves another | Docs do not match runtime |
| Wrong documentation type | Reading only a guide without checking Javadoc | Missing signatures, overloads, or deprecations |
| Wrong point in time | Using an old blog post without reading upgrade notes | Missing recent changes and bug fixes |

## 2. Distinguishing Version Types in the Spring Ecosystem

Do not treat every version number with “Spring” in its name as the same thing.

| Version type | Example | Meaning |
|---|---|---|
| Spring Boot | Project's Boot version | Application platform version and Boot's dependency management |
| Spring Data release train | 2026.0.2 | Compatible version set across multiple Spring Data modules |
| Spring Data Relational | 4.1.2 | Module version containing Spring Data JDBC and Spring Data R2DBC |
| Spring Data Commons | 4.1.2 | Shared infrastructure across many Spring Data modules |
| Spring Framework | 7.0.10 | Underlying framework that Spring Data modules depend on |
| Spring JDBC | Resolved `spring-jdbc` artifact version | Contains `JdbcTemplate`, `NamedParameterJdbcTemplate`, `JdbcClient` |
| JDBC driver | e.g., PostgreSQL JDBC driver | Vendor's database connectivity library |

A release train can have a different version number from its module versions. For example, release train 2026.0.2 manages Spring Data Relational 4.1.2. Do not put 2026.0.2 into the `spring-data-jdbc` dependency version.

Nor should you infer the Spring Framework version solely from the Spring Data version. Read the compatibility requirements of the Spring Data branch in use and inspect the resolved dependencies.

### 2.1. Illustrative Version Snapshot as of 13-11-2026

| Spring Data Relational | Minimum Spring Framework stated in Getting Started | Documentation to select |
|---|---|---|
| 4.1.2 | 7.0.10 | Reference/Javadoc 4.1.x |
| 3.5.13 | 6.2.19 | Reference/Javadoc 3.5.x |

Spring Data 2026.0.2 published Spring Data Relational 4.1.2. The 3.5.13 documentation maintains its own branch and specifies Spring Framework 6.2.19 or higher.

This example shows that two branches have different framework baselines. When working on a project, check the exact patch version and actual dependency graph rather than comparing only major/minor numbers.

## 3. Determining the Project's Actual Version

This is the most important step. The version in a dependency declaration may not be the final version placed on the classpath.

A dependency can be managed by:

- Spring Boot dependency management.
- A Spring Data release train BOM.
- A Maven parent POM.
- A Gradle platform or version catalog.
- A dependency constraint.
- A transitive dependency declared by another library.
- A build version-forcing rule or resolution strategy.

Always inspect **effective/resolved dependencies**.

## 4. Checking with Maven

### 4.1. Viewing the Dependency Tree

Use the Maven Wrapper if the project has `mvnw`:

~~~bash
./mvnw dependency:tree \
  -Dincludes=org.springframework.data:spring-data-jdbc,org.springframework.data:spring-data-relational,org.springframework.data:spring-data-commons,org.springframework:spring-jdbc,org.springframework:spring-tx
~~~

On Windows, you can run:

~~~powershell
.\mvnw.cmd dependency:tree -Dincludes=org.springframework.data:spring-data-jdbc,org.springframework.data:spring-data-relational,org.springframework.data:spring-data-commons,org.springframework:spring-jdbc,org.springframework:spring-tx
~~~

The output shows the resolved version and which dependency brings each artifact into the graph. In a multi-module project, run it in the module that actually declares or uses Spring Data JDBC.

Do not look only at the direct dependency block in `pom.xml`. For example:

~~~xml
<dependency>
    <groupId>org.springframework.data</groupId>
    <artifactId>spring-data-jdbc</artifactId>
</dependency>
~~~

No version does not mean a missing version. The version may be supplied by a parent POM or BOM.

### 4.2. Viewing the Effective POM

~~~bash
./mvnw help:effective-pom
~~~

The effective POM shows the configuration after Maven merges parents, properties, and dependency management. Use it to find:

- Which BOMs are imported.
- Which version properties apply.
- Whether dependency management overrides a version.
- What configuration the parent POM provides.

If you need to focus on a specific artifact, combine `dependency:tree` with the effective POM instead of reading the entire output manually.

### 4.3. Checking Dependency Conflicts

Maven typically selects one version using mediation rules. If two dependencies request different versions, the dependency tree shows the paths and the selected version.

Example:

~~~text
application
+- spring-data-jdbc:4.1.2
|  \- spring-data-relational:4.1.2
\- another-library
   \- spring-data-relational:4.0.8
~~~

Check the actual version and why it was chosen. Do not fix conflicts by adding arbitrary versions to every dependency. First identify the BOM or constraint managing them.

## 5. Checking with Gradle

### 5.1. Viewing dependencyInsight

For Gradle, `dependencyInsight` helps determine why a version was selected:

~~~bash
./gradlew dependencyInsight \
  --dependency spring-data-jdbc \
  --configuration runtimeClasspath
~~~

Check Spring JDBC separately:

~~~bash
./gradlew dependencyInsight \
  --dependency spring-jdbc \
  --configuration runtimeClasspath
~~~

You can check the compile classpath if you need to know which API the compiler sees:

~~~bash
./gradlew dependencyInsight \
  --dependency spring-data-jdbc \
  --configuration compileClasspath
~~~

### 5.2. Viewing the Full Dependency Graph

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Pay attention to indicators such as:

- `by constraint`: version chosen by a dependency constraint.
- `by conflict resolution`: Gradle chose a version after resolving a conflict.
- `selected by rule`: a resolution rule took effect.
- `forced`: version forced by configuration.

These markers explain why the version on the classpath differs from the version seen in a single declaration line.

### 5.3. Checking Version Catalogs and Platforms

A project may declare dependencies through a version catalog:

~~~toml
[versions]
spring-data = "4.1.2"

[libraries]
spring-data-jdbc = {
    module = "org.springframework.data:spring-data-jdbc",
    version.ref = "spring-data"
}
~~~

Or use a platform/BOM:

~~~kotlin
dependencies {
    implementation(
        platform("org.springframework.data:spring-data-bom:2026.0.2")
    )

    implementation("org.springframework.data:spring-data-jdbc")
}
~~~

If the project uses the Spring Boot plugin and Boot BOM, check Boot's dependency management before adding another BOM. Avoid creating two competing sources of version management.

## 6. Spring Boot and the Spring Data BOM

Spring Boot typically manages Spring Data and Spring Framework versions via Boot's dependency management.

In a Spring Boot project, the dependency is usually declared without a version:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-jdbc</artifactId>
</dependency>
~~~

Or a module is declared directly when the project already has appropriate dependency management:

~~~xml
<dependency>
    <groupId>org.springframework.data</groupId>
    <artifactId>spring-data-jdbc</artifactId>
</dependency>
~~~

Spring Data also provides a release train BOM to manage compatible module versions.

Maven example using the Spring Data BOM:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.data</groupId>
            <artifactId>spring-data-bom</artifactId>
            <version>2026.0.2</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>org.springframework.data</groupId>
        <artifactId>spring-data-jdbc</artifactId>
    </dependency>
</dependencies>
~~~

This is an example of using the BOM directly for a project managing Spring Data versions by release train. If Spring Boot already manages versions, prefer Boot's mechanism and override only with a clear compatibility justification.

Spring Data documentation notes that when you need to upgrade the release train managed by Spring Boot, you can configure the `spring-data-bom.version` property according to Boot's instructions. Do not add another BOM without understanding dependency management precedence.

## 7. Choosing the Right Set of Documentation

Each type of documentation answers a different kind of question.

| Source | Used to answer | Should not replace |
|---|---|---|
| Reference documentation | Concepts, semantics, configuration, and usage examples | Exact signatures of every method |
| Javadoc | Classes, methods, constructors, annotations, generics, and deprecations | System-wide architectural guides |
| Release notes | New features, bug fixes, breaking changes, dependency updates | Complete usage guides |
| Upgrade notes | Steps and considerations when upgrading versions | API reference |
| Source code at exact tag | Implementation behavior when docs are unclear | Public API contract if relying solely on implementation details |
| Dependency metadata/BOM | Relationships and compatible versions | API semantics |

A solid lookup workflow usually combines several sources:

1. Reference guide to understand usage.
2. Javadoc to confirm the API exists in the running version.
3. Release notes/upgrade notes to see changes between versions.
4. Source code at the exact release tag when clarifying an undocumented detail.

Do not use source code from the `main` branch to infer the behavior of an artifact running on an older release.

## 8. Opening the Right Reference Documentation Branch

The Spring Data documentation site may open the latest stable release by default. Check the version header on the page and select the matching branch.

Useful URLs:

- [Spring Data Relational reference — current stable](https://docs.spring.io/spring-data/relational/reference/): as of 13-11-2026, this is 4.1.2.
- [Spring Data Relational reference — 3.5 branch](https://docs.spring.io/spring-data/relational/reference/3.5/): use when the project is on the 3.5.x line.
- [Spring Data JDBC — Getting Started](https://docs.spring.io/spring-data/relational/reference/jdbc/getting-started.html): framework requirements, configuration, and database dialects of the current release.
- [Spring Data Relational Javadoc 4.1.2](https://docs.spring.io/spring-data/relational/reference/api/java/): API reference for 4.1.2.
- [Spring Data upgrade notes](https://docs.spring.io/spring-data/relational/reference/commons/upgrade.html): pointers to release notes and upgrade guidance.

When the site has a version selector, verify the version at the top of the page after selecting it. Do not rely solely on search URLs or browser tab titles.

### 8.1. Distinguishing Stable, Preview, and Snapshot

Spring Data publishes several release statuses:

| Status | Example | Meaning |
|---|---|---|
| Stable | 4.1.2 | Stable release |
| Milestone | 4.2.0-M1 | Milestone preview build |
| Release candidate | 4.2.0-RC1 | Release candidate build |
| Snapshot | 4.2.0-SNAPSHOT | Continuous development build |

If a production project uses a stable release, consult the stable docs for that branch. Only use preview/snapshot docs when the project genuinely depends on that version and accepts that APIs may change.

Do not mistake a snapshot with a higher minor number for the current stable release. “Newer” does not mean “matching version”.

## 9. Identifying the Module That Owns an API

An import statement reveals which module an API belongs to, which points to the right Javadoc.

| API | Typical package | Owning module |
|---|---|---|
| `@Query` for JDBC repositories | `org.springframework.data.jdbc.repository.query` | Spring Data Relational/JDBC |
| `@Modifying` for JDBC repositories | `org.springframework.data.jdbc.repository.query` | Spring Data Relational/JDBC |
| `@EnableJdbcAuditing` | `org.springframework.data.jdbc.repository.config` | Spring Data Relational/JDBC |
| `@Version` | `org.springframework.data.annotation` | Spring Data Commons |
| `@Id` | `org.springframework.data.annotation` | Spring Data Commons |
| `JdbcAggregateTemplate` | `org.springframework.data.jdbc.core` | Spring Data Relational/JDBC |
| `JdbcClient` | `org.springframework.jdbc.core.simple` | Spring Framework JDBC |
| `JdbcTemplate` | `org.springframework.jdbc.core` | Spring Framework JDBC |
| `@Transactional` | `org.springframework.transaction.annotation` | Spring Framework transaction |

For example, when looking up `JdbcClient`, open the Spring Framework Javadoc/reference for the version that the `spring-jdbc` dependency resolves to. Checking only Spring Data JDBC docs is not enough to verify every overload of `JdbcClient`.

Similarly, `@Version` is defined in Spring Data Commons. When verifying this annotation, check the Spring Data Commons artifact corresponding to your project's release train.

## 10. Verifying an API Layer by Layer

Suppose code uses `@Query` and `@Modifying`:

~~~java
import org.springframework.data.jdbc.repository.query.Modifying;
import org.springframework.data.jdbc.repository.query.Query;
import org.springframework.data.repository.CrudRepository;

public interface OrderRepository
        extends CrudRepository<SalesOrder, Long> {

    @Modifying
    @Query("""
        UPDATE sales_orders
        SET status = :status
        WHERE id = :id
        """)
    int updateStatus(Long id, String status);
}
~~~

When matching against documentation, do not stop just because you see an annotation with the same name. Verify:

1. Does the annotation import belong to the JDBC package?
2. Does that annotation exist in the resolved dependency version?
3. Does the method support `UPDATE` statements in that version?
4. Is the `int` return type supported and does it represent affected rows as expected?
5. Are named parameters bound by method parameter name under the current compiler configuration, or is `@Param` required?
6. Does the SQL statement match the database dialect?
7. Is the transaction boundary appropriate for the use case?
8. Does direct SQL bypass aggregate invariants, auditing, or optimistic locking?

Reference documentation explains query methods and modifying queries. Javadoc confirms the annotation and methods. Database vendor docs are still required for specific SQL syntax.

### 10.1. Confirming Signatures via Javadoc

When opening a class or annotation in the Javadoc for the right version, check:

- Fully qualified class name.
- Public constructors and methods.
- Parameters and generic types.
- Return type.
- Checked exceptions, if any.
- Annotation target and retention.
- `@Deprecated` and `@since`.
- Notes on thread safety or lifecycle, if present.

A method with the same name taking different parameter types can prevent compilation or resolve to an unintended overload.

### 10.2. Checking `@since` and `@Deprecated`

If Javadoc includes `@since`, it gives a useful hint about when the API appeared. If `@Deprecated` is present, read the description to learn:

- Since which version the API was deprecated.
- What replacement API is suggested.
- Whether removal is planned for a specific version.
- Any behavior changes to address before migrating.

Do not delete an API just because the IDE crosses it out. Read the deprecation note and upgrade guide before making changes.

## 11. Example: Distinguishing Spring Data JDBC and Spring Framework `JdbcClient`

Suppose a project uses Spring Data JDBC to persist aggregates and wants to add `JdbcClient` for a reporting query.

The two APIs belong to two different modules:

~~~java
import org.springframework.data.jdbc.core.JdbcAggregateTemplate;
import org.springframework.jdbc.core.simple.JdbcClient;
~~~

`JdbcAggregateTemplate` belongs to Spring Data Relational/JDBC. `JdbcClient` belongs to Spring Framework JDBC.

Therefore, you must check both versions:

~~~text
spring-data-jdbc : 4.1.2
spring-jdbc      : 7.0.10
~~~

This version pair is illustrative based on the 4.1.2 documentation baseline, not a guarantee that every application's dependency graph will match. If Spring Boot or a BOM manages different versions, use your project's actual resolution result.

Bean configuration:

~~~java
@Configuration
class QueryConfiguration {

    @Bean
    JdbcClient jdbcClient(NamedParameterJdbcTemplate template) {
        return JdbcClient.create(template);
    }
}
~~~

When code fails to compile, do not immediately change the Spring Data JDBC version. Identify which artifact owns the missing class, check the `spring-jdbc` version, and open the corresponding Spring Framework Javadoc.

This avoids upgrading an unrelated module just to fix a dependency issue in another module.

## 12. Comparing Documentation Between Two Version Branches

When a project upgrades from Spring Data Relational 3.5.x to 4.1.x, use documentation from both branches for comparison.

A workflow:

1. Record the current versions from the dependency tree.
2. Open the reference/Javadoc for the current branch.
3. Record the APIs currently used in source code.
4. Open upgrade notes and release notes for each release train crossed.
5. Open the documentation for the target branch.
6. Compare packages, method signatures, configuration, and semantics.
7. Run compile/tests with the target dependencies.
8. Update only the parts that actually changed or where you intend to adopt new APIs.

Do not read only the target version's release notes if the project skips multiple releases. The Spring Data upgrade guide notes that intermediate release notes must also be reviewed when skipping multiple releases.

### 12.1. Do Not Infer API Changes from Version Numbers Alone

Two branches may keep identical API signatures while changing bug fixes or edge-case semantics. Conversely, a release may add new APIs without removing old ones.

Categorize the comparison findings:

| Type of difference | Action needed |
|---|---|
| New API added | Use only if available in target version and needed by the use case |
| API deprecated | Plan replacement, read deprecation notes |
| API removed or signature changed | Update source code and tests |
| Behavior fixed/changed | Check business impact |
| Dependency baseline changed | Check JDK, Framework, Boot, and integration libraries |
| No relevant changes | Keep existing code; do not refactor solely due to a version bump |

### 12.2. Separating API Changes from Behavior Changes

For example, a method may still compile after an upgrade, yet edge-case handling may have changed. The compiler cannot detect this difference.

Therefore, beyond compile checks, maintain integration tests for behaviors the application relies on, especially:

- Aggregate persistence.
- Optimistic locking.
- Query derivation and modifying queries.
- Auditing callbacks.
- Transaction rollback.
- Database dialects and generated SQL.
- Mapping of nulls, enums, date/time, and embedded properties.

## 13. Reading Release Notes and Upgrade Notes Along the Upgrade Path

Release notes typically describe:

- New features.
- Bug fixes.
- Deprecations.
- Breaking changes.
- Dependency upgrades.
- Upgrade instructions.

When upgrading across multiple versions, do not read only the latest release notes. For example, from 3.5.x to 4.1.x, review relevant changes in intermediate release trains and identify the minimum Framework version.

Spring Data provides an upgrade page directing readers to release notes on the project wiki. Upgrade instructions typically appear at the top of each version's release notes.

Official references as of this lesson's snapshot:

- Spring Data 2026.0.2 announced Spring Data Relational 4.1.2.
- Spring Data Relational 4.1.2 Getting Started requires Spring Framework 7.0.10 or higher.
- Spring Data Relational 3.5.13 Getting Started requires Spring Framework 6.2.19 or higher.

These sources help distinguish module versions from framework baselines. Do not use a release announcement blog post as a substitute for API reference; use it to confirm versions, then open the corresponding reference/Javadoc.

## 14. Cross-Checking Examples Found on the Internet

An example from Stack Overflow, a blog, or a GitHub repository may have been written for a different version. Before copying it, check:

- The publication date and version mentioned in the post.
- The example's `pom.xml`, `build.gradle`, or version catalog.
- Package imports in the code.
- Whether the API used belongs to Spring Data or Spring Framework.
- Whether the article uses a snapshot or milestone.
- Whether any release note changed that API after the post was written.
- Whether the example uses a different database dialect from your project.

If the post does not mention a version, inspect the dependency file in its repository. If still undetermined, treat the snippet as an idea reference and verify the API in the official documentation for your running version.

Never assume a code snippet is right just because it has many upvotes or compiles in a different project.

## 15. Verifying with Compiler, Tests, and Runtime

Documentation states what an API supports; builds and tests confirm your actual project can use that API within its current dependency graph.

A verification workflow:

### 15.1. Compile

Maven:

~~~bash
./mvnw -DskipTests compile
~~~

Gradle:

~~~bash
./gradlew compileJava
~~~

Compiling confirms classes, imports, and method signatures on the compile classpath. It does not prove runtime semantics are correct.

### 15.2. Unit Tests

Verify application service logic, mapping, and error handling with appropriate tests. Unit tests mocking repositories do not prove real SQL or database transaction behavior.

### 15.3. Integration Tests

Use a database engine/version close to production to verify:

- Repositories initialize with current dependencies.
- Generated SQL runs properly.
- Mapping and conversions work.
- Transactions and rollbacks behave properly.
- Callbacks/auditing are invoked on the expected path.
- Locking and concurrency have the intended semantics.

### 15.4. Checking Runtime Dependencies

If compilation succeeds but runtime throws `NoSuchMethodError`, `ClassNotFoundException`, or `NoClassDefFoundError`, inspect the runtime classpath. Compile and runtime may resolve different versions, or a dependency may be excluded/overridden.

Do not resolve linkage errors by throwing random JARs onto the classpath. Identify which dependency provides the class and which version the runtime loads.

## 16. API Lookup Checklist

When using a Spring Data JDBC API, follow this checklist:

| Question | Where to check |
|---|---|
| Which version is the project using? | Maven `dependency:tree` / Gradle `dependencyInsight` |
| Who manages the version? | Effective POM, BOM, version catalog, constraints |
| Which module owns the API? | Fully qualified import and dependency artifact |
| Where is the version-matched guide? | Reference documentation for that branch |
| What is the exact method signature? | Javadoc for that exact version |
| Is the API deprecated? | Javadoc and release notes |
| Are there behavior changes? | Release notes, upgrade notes, source at exact tag |
| Are newer framework/JDK versions required? | Getting Started and dependency compatibility |
| Does the code compile? | Compile with resolved dependencies |
| Is SQL/runtime behavior right? | Integration tests on the target database |

### 16.1. Record Card for a Critical API

When an API significantly affects persistence or transactions, record:

~~~text
API:
Fully qualified name:
Artifact:
Resolved version:
Spring Data release train:
Spring Framework version:
Reference documentation:
Javadoc:
Relevant upgrade notes:
Database/dialect:
Compile result:
Integration test:
Known limitations:
~~~

This card helps reviewers understand which version the API relies on and where to check during future upgrades.

## 17. Common Mistakes

| Mistake | Consequence | How to handle |
|---|---|---|
| Looking only at versions in build files | Missing BOMs or transitive dependencies | Inspect resolved dependencies |
| Opening the latest docs page and copying code | Using APIs absent in the current version | Select the matching documentation branch |
| Confusing release train with module version | Declaring wrong artifact versions | Record train and module versions separately |
| Checking Spring Data docs for Spring Framework APIs | Checking the wrong signatures | Identify the owning package and artifact |
| Using snapshot docs for stable dependencies | Relying on unreleased APIs | Choose stable docs |
| Reading only the reference guide | Missing overloads and deprecations | Cross-check Javadoc |
| Reading only Javadoc | Missing aggregate semantics and transaction behavior | Read the reference guide |
| Skipping intermediate release notes | Missing migration requirements | Read all crossed release notes |
| Treating compile success as sufficient | Missing behavior/runtime mismatches | Run integration tests |
| Adding arbitrary dependency versions to fix errors | Creating incompatible dependency graphs | Identify the root cause of version resolution |
| Using a blog post's date as the project version | Code examples may be outdated | Check dependency graph and docs version |

## 18. Workflow from Discovering an API to Using It

When encountering a new API or mismatched code snippet, proceed in order:

**Step 1 — Identify the API.** Write down the class/method name and full import.

**Step 2 — Identify the artifact.** Find which module provides the class, distinguishing Spring Data JDBC, Spring Data Commons, and Spring Framework.

**Step 3 — Resolve the version.** Use `dependency:tree` or `dependencyInsight` to get the actual version.

**Step 4 — Identify the release train.** Check the BOM and dependency management controlling the module.

**Step 5 — Select the matching reference docs.** Open the documentation branch matching the module version.

**Step 6 — Check Javadoc.** Confirm signatures, overloads, generics, deprecations, and `@since`.

**Step 7 — Read release notes.** If porting code from an older branch, review intermediate release notes.

**Step 8 — Check the baseline.** Confirm Spring Framework, Spring Boot, JDK, and JDBC driver compatibility.

**Step 9 — Compile and test.** Use the project's real dependency graph.

**Step 10 — Record sources.** Save links to the version-specific reference/Javadoc/release notes in technical docs or code reviews.

~~~text
API name / import
       |
       v
Identify owning artifact
       |
       v
Resolve dependency version
       |
       v
Identify BOM / release train
       |
       v
Select matching Reference docs branch
       |
       v
Check Javadoc / signature
       |
       v
Read release notes / upgrade notes
       |
       v
Compile + integration test
       |
       v
Record version and reference sources
~~~

## 19. Reasoning Exercises

**Scenario A — No Version in Dependency Declaration**

`pom.xml` declares `spring-data-jdbc` without a version. Can we conclude the project has no version?

**Hint:** No. The version may be managed by the Spring Boot parent or Spring Data BOM. Use `dependency:tree` and the effective POM to find the actual version.

**Scenario B — API Not Found**

An example in new docs uses a method that fails to compile in the project. What should you do before upgrading dependencies?

**Hint:** Identify the artifact owning the method, check the resolved version, open the version-matched Javadoc, and read release notes. Only then decide whether to use an alternative API or upgrade versions.

**Scenario C — JdbcClient**

The project uses Spring Data JDBC 3.5.x, but the compiler cannot find `JdbcClient`. Should we conclude Spring Data JDBC lacks this API?

**Hint:** No. `JdbcClient` belongs to Spring Framework JDBC. Check the `spring-jdbc` version and actual framework baseline.

**Scenario D — BOM and Artifact Version**

The release train is 2026.0.2 and Spring Data Relational is 4.1.2. Which version goes into the dependency when using the BOM?

**Hint:** The BOM supplies compatible module versions. When importing the BOM, the `spring-data-jdbc` dependency can omit its version; do not enter 2026.0.2 as the module version.

**Scenario E — Snapshot Documentation**

A snapshot page describes an API newer than stable docs. The production project uses a stable release. Should that API be adopted immediately?

**Hint:** No. Only use it if the project actually upgrades to the preview/snapshot version and accepts that status. For stable dependencies, consult stable Javadoc/reference.

**Scenario F — Compile Succeeds**

An API compiles cleanly, yet the query behaves differently from expectations on PostgreSQL. Which docs should be checked?

**Hint:** Reference guide and Javadoc for the Spring API, release notes for behavior changes, database documentation for SQL dialect, and then integration tests on PostgreSQL.

## 20. Takeaways

| Component | Role |
|---|---|
| Resolved dependency | Actual version placed on the classpath |
| Spring Data BOM | Manages compatible Spring Data modules |
| Spring Boot BOM | Manages dependencies per Boot version |
| Release train | Compatible version group of Spring Data |
| Reference documentation | Explains semantics and usage |
| Javadoc | Confirms public APIs and signatures |
| Release notes | Documents features, bug fixes, and changes |
| Upgrade notes | Guides transitions between versions |
| Source at release tag | Clarifies implementation when docs are insufficient |
| Compile test | Confirms API presence on compile classpath |
| Integration test | Confirms behavior with actual dependencies and database |

**Looking up the right API starts from the project's resolved version, not from the first search result.** Identify the artifact owning the API, inspect the BOM and dependency graph, open the reference/Javadoc for the right branch, read release notes when upgrading, and then compile and test on the real configuration. This approach avoids mixing up APIs across Spring Data JDBC, Spring Data Commons, and Spring Framework while keeping technical examples aligned with the running application version.

## References

- [Spring Data Relational — Reference Documentation](https://docs.spring.io/spring-data/relational/reference/): current stable documentation; as of 13-11-2026, Spring Data Relational 4.1.2.
- [Spring Data Relational — Javadoc 4.1.2](https://docs.spring.io/spring-data/relational/reference/api/java/): public API for Spring Data Relational 4.1.2.
- [Spring Data Relational 3.5 — Reference Documentation](https://docs.spring.io/spring-data/relational/reference/3.5/): documentation for the 3.5.x branch.
- [Spring Data JDBC — Getting Started](https://docs.spring.io/spring-data/relational/reference/jdbc/getting-started.html): dependencies, Spring Framework requirements, and JDBC configuration for the current branch.
- [Spring Data 2026.0.2 and 2025.1.8 released](https://spring.io/blog/2026/10/22/spring-data-2026-0-2-and-2025-1-8-released/): confirms Spring Data Relational 4.1.2 belongs to release train 2026.0.2.
- [Spring Data — Upgrading](https://docs.spring.io/spring-data/relational/reference/commons/upgrade.html): links to release notes and upgrade guidance.
- [Spring Framework — JDBC Core](https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html): JDBC APIs such as `JdbcTemplate` and `JdbcClient` belonging to Spring Framework.

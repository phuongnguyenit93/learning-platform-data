# Identifying Experimental Features and Verifying Them Before Documenting

Spring Data JDBC evolves across versions of Spring Data and Spring Boot. A feature may appear in the latest documentation, in a development source branch, or in a milestone release, yet not be present in the version your project uses. An API may also already exist while still marked experimental, incubating, deprecated, or internal.

Therefore, before including a feature in technical documentation, verify three separate things:

1. **Is the feature actually present in the version the project uses?**
2. **What support status does that API have, and what are its usage conditions?**
3. **Does the behavior work in the target configuration, database, and driver?**

None of these three questions can be answered solely from a latest documentation page or an example found online. This lesson provides a verification workflow based on resolved dependencies, how to read Javadoc and release notes, how to spot indicators of experimental APIs, how to write integration tests, and how to record results so readers know the exact versions a feature applies to.

## 1. Distinguishing Documentation Versions from Application Versions

Spring Data JDBC is part of the Spring Data ecosystem. In a Spring Boot project, dependency management typically selects Spring Framework and Spring Data versions compatible with the Spring Boot release.

This means:

- The latest Spring Data JDBC documentation may describe APIs missing from the project's dependencies.
- Examples on a development source branch may contain unreleased changes.
- A feature introduced in a milestone or release candidate may change before GA.
- The `spring-data-jdbc` and `spring-data-relational` versions must be compatible with each other.
- The database and JDBC driver may also constrain a feature's behavior.

For example, a project uses an older Spring Boot release while an author opens Spring Data Relational docs for a newer release. The new docs may show methods or annotations absent from the actual classpath. Copying the example without checking dependencies may leave learners with code that fails to compile.

**Principle:** identify the dependency version your project actually resolves first, then consult documentation, Javadoc, and source code for that exact version.

## 2. Determining the Actual Spring Data JDBC Version

Do not look only at the version declared in a build file. Dependency management, BOMs, plugins, or transitive dependencies can cause the version used to differ from what an author assumes.

### 2.1. Checking with Gradle

With Gradle, use `dependencyInsight` to inspect the selected version and the reason it was chosen:

~~~bash
./gradlew dependencyInsight --dependency spring-data-jdbc --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-data-relational --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-data-commons --configuration runtimeClasspath
~~~

On Windows, you can run `gradlew.bat` instead of `./gradlew`.

The `dependencies` command displays the runtime dependency tree:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Check:

- The final selected version of `spring-data-jdbc`.
- The resolved version of `spring-data-relational`.
- The related `spring-data-commons` version.
- Which dependency requested each version and whether any rule forces a different version.
- Whether any snapshot, milestone, or release candidate dependency is present.

`dependencyInsight` is especially useful when multiple dependencies request the same module and Gradle picks one according to resolution rules.

### 2.2. Checking with Maven

With Maven:

~~~bash
./mvnw dependency:tree -Dincludes=org.springframework.data:spring-data-jdbc
./mvnw dependency:tree -Dincludes=org.springframework.data:spring-data-relational
./mvnw dependency:tree -Dincludes=org.springframework.data:spring-data-commons
~~~

If the project lacks the Maven Wrapper, use `mvn` instead of `./mvnw`.

To inspect dependency management after parent inheritance and BOM imports:

~~~bash
./mvnw help:effective-pom
~~~

Focus on actual resolved dependencies and the `dependencyManagement` section. A version written in a property or parent POM is only an input to dependency management; the resolved dependency tree reveals which artifacts actually enter the classpath.

### 2.3. Checking Spring Boot and the BOM

If the project uses Spring Boot, check the Spring Boot parent or plugin version and any imported BOMs. Spring Boot manages a compatible set of versions for Spring libraries.

Usually, let Spring Boot dependency management choose the Spring Data JDBC version. If an override is justified, confirm that the Spring Data release train is compatible with the project's Spring Boot and Spring Framework versions.

Do not arbitrarily set three separate versions for:

~~~text
spring-data-jdbc
spring-data-relational
spring-data-commons
~~~

Mixing modules from different release trains can cause binary compatibility errors, `NoSuchMethodError`, `ClassNotFoundException`, or inconsistent mapping behavior.

## 3. Reading the Right Type of Documentation and Evidence

Not every source answers the same question. Use the source appropriate for the evidence you need to confirm.

| Source | What can it confirm? | Limitations |
|---|---|---|
| Version-matched reference documentation | Documented usage and related configuration | The `current` page may describe a newer release |
| Artifact/version-matched Javadoc | Public API signatures, parameters, return types, annotations, and API notes | Javadoc may lack descriptions of internal behavior |
| Release notes/changelog | Version introduced, changes, and migration notes | Summaries may omit edge conditions |
| Migration guide | Changes to handle when upgrading | Does not replace application testing |
| Source code at exact Git tag | Implementation and annotations of that exact release | Source alone does not prove behavior in your application config |
| Upstream project tests at exact tag | How maintainers test the feature | Upstream tests do not replace tests with your project's database |
| Resolved artifact | Classes and methods actually present on the classpath | Class presence does not mean stable support |
| Application integration tests | Behavior with target config, driver, and database | Confirms only the scope exercised by tests |

### 3.1. Using Versioned Documentation

When consulting reference documentation, choose the Spring Data version matching the resolved dependency. If the site has a version selector, do not leave it on `current` when the project runs an older release.

Verify:

- The module is Spring Data JDBC/Relational, not Spring Data JPA.
- The documentation page belongs to the right release train.
- APIs in the example exist in the project's version.
- Compatibility notes for Java, Spring Framework, database, or driver apply.

Examples using `@Query`, `JdbcAggregateTemplate`, custom conversions, or callbacks must be cross-checked against the exact version's API, even when class names match.

### 3.2. Using Javadoc to Confirm API Contracts

Javadoc helps verify:

- Whether the class and method are part of the public API.
- Exact parameter types and return types.
- Available constructors or overloads.
- Which version the method is marked `@since`.
- Whether the API is deprecated or carries usage warnings.
- Annotations describing API stability if the project provides such metadata.

Never infer method signatures from a blog post or an example for a different version. Read the Javadoc for the resolved artifact.

### 3.3. Using Release Notes and Migration Notes

Release notes typically state in which release a feature was added, fixed, or changed. Migration guides may highlight removed legacy behaviors or new configuration styles.

When seeing a feature announced:

1. Note the first version mentioned in release notes.
2. Check whether that version is a milestone, release candidate, or GA.
3. Confirm the API is present in the GA artifact your project intends to support.
4. Read migration notes of subsequent versions to see if the API changed or was deprecated.

Do not treat a “new feature” line in a changelog as proof that the feature exists in earlier versions or keeps the exact same signature in future versions.

## 4. Recognizing the Status of an API

A feature may be new yet stable, or may have existed for some time while remaining experimental. Distinguish API stability status from feature age.

### 4.1. Common Statuses

| Status | Practical meaning when writing documentation |
|---|---|
| Stable/public API | Has a public API contract; still state versions and limitations |
| Experimental | API or feature may change; do not present as a stable contract |
| Incubating | Under active development/refinement; check what the label means in that project |
| Preview or milestone | Pre-release or pre-GA build; does not represent a stable production release |
| Deprecated | Still usable, but migrating to an alternative is recommended |
| Internal/unsupported | Not a supported public contract; avoid instructing applications to depend on it directly |

Terminology and support policies can vary across projects. Never assign a status based solely on class naming.

### 4.2. Looking for API Guardian Metadata

Some Java libraries use annotations from API Guardian to declare API status, for example:

~~~java
import org.apiguardian.api.API;

@API(status = API.Status.EXPERIMENTAL)
public class ExampleFeature {
}
~~~

Common statuses in this metadata include `STABLE`, `MAINTAINED`, `DEPRECATED`, `EXPERIMENTAL`, and `INTERNAL`.

If a class or method is marked `EXPERIMENTAL`, reflect that clearly in documentation. Never strip the annotation and present the API as a stable contract.

If marked `INTERNAL`, do not instruct application developers to depend on it directly unless official documentation explicitly calls out a special case and accepts the risk.

Not every API carries an API Guardian annotation. **Not seeing the annotation does not mean the API is definitely stable.** When metadata is absent, combine Javadoc, reference docs, packages, release notes, and project policy.

### 4.3. Checking `@Deprecated`

Example:

~~~java
@Deprecated(since = "x.y", forRemoval = true)
public void oldOperation() {
}
~~~

`since` indicates the version where deprecation was marked if provided. `forRemoval = true` signals that the API is scheduled for future removal per the annotation contract.

When writing documentation:

- State since which version the API was deprecated if verified.
- Point to the replacement recommended by official documentation.
- Note if the old approach remains available across a version range you need to support.
- Do not teach learners to start new projects with a deprecated API when a supported alternative exists.

### 4.4. Reading `@since` Correctly

Javadoc may state:

~~~java
/**
 * @since 3.x
 */
~~~

This information helps identify when an API was introduced. However:

- `@since` does not by itself guarantee the API is stable.
- A missing `@since` does not prove the API existed since version 1.0.
- `@since` may denote the module version, which does not necessarily match the Spring Boot version number.
- Cross-check against release notes and actual artifacts.

## 5. Warning Signs Beyond Annotations

Even without an explicit experimental label, several signals indicate further verification is needed before putting an API into a lesson.

### 5.1. Internal Package or Class Names

Packages named `internal`, `impl`, or non-public classes are usually not supported extension points for applications. While not an absolute rule, this is a signal to check carefully.

Prefer:

- Public interfaces or classes in official API packages.
- Configurations documented in the reference guide.
- Extension points with public contracts and examples.

Avoid instructing users to import an internal implementation class just because it solves a problem in one version.

### 5.2. APIs Only on the `main` Branch or in Snapshots

A class may appear on GitHub's development branch before it exists in any GA artifact. Likewise, dependencies with `-SNAPSHOT` or milestone suffixes are not proof of a stably released API.

Distinguish:

- Source code at a release tag.
- Source code on a development branch.
- Milestone or release candidate artifacts.
- Published GA artifacts.

If documentation must describe released features, verify the GA artifact and corresponding tag.

### 5.3. Features Requiring Explicit Opt-In

Some features work only when:

- Another module dependency is added.
- An enablement annotation is configured.
- A specific bean is declared.
- A feature flag or property is turned on.
- A supporting database dialect or driver is used.
- A specific transaction manager is used.

The presence of a class on the classpath does not prove a feature is enabled. Check configuration conditions and actual beans in the application context.

## 6. Inspecting APIs in Resolved Artifacts

Once you know the dependency version, you can verify directly inside the artifact that the class and method exist.

### 6.1. Inspecting JAR Contents

Example:

~~~bash
jar tf path/to/spring-data-jdbc-version.jar
~~~

On Windows, filter class names with `findstr`; on macOS/Linux, use `grep`.

This command confirms the class is inside the JAR, but does not tell you whether the API is stable or behaves properly at runtime.

### 6.2. Checking Signatures with `javap`

If you know the fully qualified class name:

~~~bash
javap -classpath path/to/spring-data-jdbc-version.jar fully.qualified.ClassName
~~~

To view annotations and detailed signatures:

~~~bash
javap -v -classpath path/to/spring-data-jdbc-version.jar fully.qualified.ClassName
~~~

If the class depends on other artifacts, add them to the classpath or open the external library in your IDE. `javap` is helpful when Javadoc is unavailable or when verifying specific method overloads.

### 6.3. Checking Annotations via Reflection

In a small test, you can inspect runtime annotations if they have appropriate retention:

~~~java
API api = ExampleFeature.class.getAnnotation(API.class);

if (api != null) {
    System.out.println(api.status());
}
~~~

Reflection reads only metadata retained in the bytecode. If an annotation has non-runtime retention or metadata lives in Javadoc/source, reflection does not replace checking the docs.

## 7. Compiling Examples with the Exact Dependencies

An example may look plausible while calling a method absent from your project's version. Basic verification means putting the example into a module or sample project using the application's exact dependency management.

### 7.1. Running the Compile Task

Gradle:

~~~bash
./gradlew compileJava
~~~

Maven:

~~~bash
./mvnw -DskipTests compile
~~~

If a snippet is partial code, place it in a class with the required imports and dependencies. A snippet missing imports does not prove an API is broken; distinguish incomplete snippets from nonexistent APIs.

### 7.2. Do Not Verify by Arbitrarily Upgrading Dependencies

If code compiles only after upgrading Spring Data JDBC to the latest version, that does not prove the example works for the project's current version.

Record clearly:

- The initial dependency version.
- The version where the snippet compiles.
- Which API or method was added in the new version.
- Whether the project plans to upgrade.

Never silently bump a version just to make an example pass and continue presenting it as an example for the older version.

## 8. Verifying Behavior with Integration Tests

Compilation only verifies compile-time API and type compatibility. With Spring Data JDBC, much of the behavior also depends on mapping, dialects, JDBC drivers, and databases.

A feature should only be described as verified in a given environment when covered by appropriate tests.

### 8.1. Testing Against the Target Database

If a feature involves:

- SQL generated by Spring Data.
- Generated IDs.
- Optimistic locking.
- Transactions and savepoints.
- Custom conversions.
- Aggregate collection mapping.
- Pagination or dialects.

run integration tests with the database/driver that documentation claims to support.

H2 can be useful for quick tests, but it does not replace PostgreSQL, MySQL, SQL Server, or a production database when behavior depends on dialect. Do not conclude a feature works across all databases simply because an H2 test passes.

### 8.2. Using `@DataJdbcTest` or an Appropriate Test Context

Illustrative integration test skeleton:

~~~java
@DataJdbcTest
class FeatureIntegrationTest {

    @Autowired
    PurchaseOrderRepository orders;

    @Test
    void featureBehavesAsDocumented() {
        // Arrange: prepare test data.
        // Act: call the repository or JdbcAggregateTemplate.
        // Assert: verify the result and database state.
    }
}
~~~

If the feature requires custom configuration, import that configuration into the test or use a test application context equivalent to the application. Do not check only the returned object; when needed, query the database to confirm data was written accurately.

### 8.3. Testing Edge Cases as Well

A single happy-path test is rarely enough. Depending on the feature, test:

- Null values and empty data.
- Aggregates with child collections and aggregates without child collections.
- Initial insert and subsequent update.
- Constraint errors and rollbacks.
- Two concurrent updates.
- Different database/driver versions within the support matrix.
- Missing configuration or disabled feature flags.

You do not need to test every possible combination in a single lesson. Choose cases that prove the contract and limits your documentation describes.

## 9. Checking Activation Conditions and Spring Configuration

A feature may exist in the JAR yet fail to activate because a required bean or configuration is not registered.

Check:

1. Is the required dependency on the runtime classpath?
2. Is the enablement annotation placed on a scanned configuration class?
3. Are required extension point beans registered?
4. Are properties/feature flags set to the expected values?
5. Is conditional configuration activating as intended?
6. Does repository scanning include the required package?
7. Is another configuration overriding or replacing the bean?

With Spring Boot, debug mode or the condition evaluation report shows which auto-configurations applied and why others were skipped. If using the Actuator conditions endpoint, configure proper access controls before using it in shared environments.

Do not expose internal diagnostic endpoints publicly in production just to verify a lesson.

## 10. Verifying a Feature Layer by Layer

A verification workflow can be split into four layers of evidence:

| Layer | Question | Evidence |
|---|---|---|
| Availability | Is it in the version currently used? | Dependency tree, artifact, class/method |
| API status | Is it stably supported? | API metadata, Javadoc, reference docs, release notes |
| Activation | What config is needed to run it? | Beans/configuration/properties, application context |
| Behavior | Does it work as documented? | Integration tests with target database and driver |

Do not skip any layer. For example:

- A class exists in the JAR, yet the API is marked experimental.
- The API is stable, yet the project has not enabled the required bean.
- Code compiles, yet the database dialect lacks required SQL syntax support.
- H2 tests pass, yet the production database behaves differently.

## 11. Example Verification Workflow for a New API

Suppose a draft document wants to introduce a new method on `JdbcAggregateTemplate`.

Do not immediately write that the method exists across all Spring Data JDBC versions. Perform these steps:

**Step 1 — Identify dependencies:** run `dependencyInsight` or `dependency:tree` and record the `spring-data-jdbc`, `spring-data-relational`, and release train versions.

**Step 2 — Check reference docs:** open the documentation for that exact release. Locate the method and verify its description, configuration requirements, and limitations.

**Step 3 — Check Javadoc:** confirm the method signature, return type, API Guardian annotations, `@Deprecated`, and `@since` if present.

**Step 4 — Check release notes:** confirm which release introduced the method and whether it changed afterward.

**Step 5 — Inspect the artifact:** use your IDE, `jar tf`, or `javap` to confirm the classpath actually contains the method.

**Step 6 — Compile a sample:** place the example in a project using the exact same dependency management.

**Step 7 — Run integration tests:** invoke the method on real aggregates, checking database outcomes, transactions, and error cases.

**Step 8 — Write a scoped conclusion:** state the verified versions, API status, and tested database/driver.

If a step lacks evidence, clearly note what remains unverified instead of guessing.

## 12. Recording Results in a Version Matrix

When a lesson describes a feature that differs across releases, create a compatibility table:

| Component | Value to record |
|---|---|
| Spring Boot | Project version or version range |
| Spring Data release train | Corresponding release train |
| Spring Data JDBC | Resolved artifact version |
| Spring Data Relational | Resolved artifact version |
| Spring Framework | Version chosen by dependency management |
| Java | Compile/runtime version |
| Database | DBMS product and version |
| JDBC driver | Name and version |
| API status | Stable/experimental/deprecated/internal or metadata absent |
| Test result | Compile, integration tests, and configuration executed |

Do not write “supports Spring Data JDBC 3.x” if you only tested one patch release without checking the version range. When only one version is verified, write “verified on version x.y.z”.

### 12.1. Verification Note Template for a Lesson

You can use this structure in documentation:

~~~text
Feature:
Spring Data JDBC version:
Spring Data Relational version:
Spring Boot version:
Database and JDBC driver:
Introduced in version:
API status:
Referenced docs/Javadoc:
Required configuration:
Known limitations:
Tests executed:
Scope of conclusion:
~~~

This template helps other authors update the lesson when dependencies change. It also separates observed facts from assumptions or predictions.

## 13. Phrasing Documentation According to Feature Status

Language in a lesson must accurately reflect the level of support.

### 13.1. API Confirmed Public and Stable

You can write:

> This API is available in the stated Spring Data JDBC version and is documented in official documentation as a public API. The example below has been compiled and tested with the database/driver recorded in the environment section.

Still state versions and configuration conditions.

### 13.2. Experimental or Incubating API

Write:

> This feature is marked experimental in the verified version. Method names, signatures, or behaviors may change in future releases. Use it only after assessing upgrade risks and re-verifying against your deployment version.

Do not write it as a stable API broadly recommended for every project.

### 13.3. Preview or Milestone API

State clearly that it is a pre-GA build, its exact version, and its experimental intent. Do not use a milestone build as proof of GA behavior without re-verifying.

### 13.4. Deprecated API

State the deprecated version, the replacement API, and migration notes. Do not delete information about the old API if readers need to upgrade from a release that still supports it, but do not recommend it for new code when an official alternative exists.

### 13.5. Undetermined Status

If no metadata or official statement is found:

> No API stability declaration was found for this component in the inspected sources. Verify against the Javadoc/release notes of your target version before relying on it as a long-term contract.

Never turn an “undetermined” status into stable or experimental on your own.

## 14. Common Misconceptions

| Misconception | Why it is wrong | How to handle |
|---|---|---|
| The `current` docs apply to every version | `current` may belong to a newer release | Select version-matched documentation |
| A class in the JAR means a stable API | The class may be experimental or internal | Check metadata and Javadoc |
| `@since` means stably supported | `@since` only states when it appeared | Check API status and release notes |
| Absence of `@API` means stable | Not every project annotates every API | Use multiple sources of evidence |
| Code on GitHub `main` works in the current release | `main` may contain unreleased changes | Check release tags and artifacts |
| Milestone/RC equals GA | APIs may still change before GA | Label the exact version type |
| Code compiles means the feature works | Runtime needs beans, config, dialect, and driver | Run integration tests |
| H2 test passes means all databases support it | Dialects and drivers differ | Test on the target database |
| Repositories and `JdbcTemplate` both run callbacks | Direct `JdbcTemplate` mapping bypasses the Spring Data entity lifecycle | Identify the actual persistence path |
| Upgrading a dependency to clear an error is enough | May cause release train conflicts | Check the BOM and dependency tree |
| One passing test proves an entire version range | Tests confirm only the specific environment | State the exact verification scope |

## 15. Checklist Before Documenting a Feature

Before writing definitively about a feature, answer these items:

1. Has the actual `spring-data-jdbc` version been identified?
2. Have `spring-data-relational` and `spring-data-commons` compatibility been confirmed?
3. Have reference docs for the exact release been read?
4. Have Javadoc and API status (if available) been checked?
5. Have release notes and the migration guide been reviewed?
6. Does the feature require extra annotations, beans, properties, or dependencies?
7. Are there database dialect or JDBC driver limitations?
8. Does the example compile against the target dependencies?
9. Are critical behaviors covered by integration tests?
10. Does the documentation clearly state versions and verification limits?

This checklist is an evidence-gathering process for authors. It does not replace formal project content review or pre-release testing.

## 16. Practice Exercises

### Exercise 1 — Checking Actual Dependencies

1. Open a Spring Boot project using Spring Data JDBC.
2. Run `dependencyInsight` or `dependency:tree`.
3. Record the JDBC, Relational, and Commons versions.
4. Identify which BOM or dependency management selected those versions.
5. Compare with the version shown on the documentation page you have open.

### Exercise 2 — Classifying an API

1. Choose a public class or method in Spring Data JDBC.
2. Open the version-matched Javadoc.
3. Look for `@API`, `@Deprecated`, and `@since` if present.
4. Cross-check release notes and the source tag.
5. Record the API status with evidence; if no declaration exists, record undetermined.

### Exercise 3 — Verifying a Code Example

1. Create a sample class using an API you are investigating.
2. Compile it using the project's exact dependencies.
3. If compilation fails, distinguish missing imports, absent APIs, and version conflicts.
4. Run an integration test against the target database.
5. Record the test conditions and outcomes clearly.

### Exercise 4 — Writing a Compatibility Note

1. Pick a new feature mentioned in release notes.
2. Find the first version containing the feature.
3. Identify whether that release is a milestone, RC, or GA.
4. Check the API status in the GA release.
5. Write a concise compatibility note without generalizing beyond what was verified.

## 17. Conclusion

To identify experimental features and verify them before documenting, start from **the project's resolved dependencies**, then cross-check version-matched reference documentation, Javadoc, release notes, and source tags. Check metadata like `@API`, `@Deprecated`, and `@since`, but never treat missing annotations as proof that an API is stable.

Next, confirm the feature exists in the actual artifact, compile examples with the target dependencies, and run integration tests against the supported databases and JDBC drivers. A class present in a JAR proves only existence; a compiling example proves only signature compatibility. Behavior, activation configuration, and database constraints must be verified separately.

When writing, explicitly state verified versions, API status, required configuration, and test scope. Where status or compatibility lacks evidence, state that clearly. Doing so keeps Spring Data JDBC documentation aligned with real-world versions and avoids turning preview or experimental features into stable advice for readers.

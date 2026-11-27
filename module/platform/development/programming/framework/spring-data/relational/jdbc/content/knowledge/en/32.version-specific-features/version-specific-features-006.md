# AOT and Native Image: Configuration, Repository Optimization, and Limitations

In **Spring Data Relational JDBC (Spring Data JDBC)**, Ahead-of-Time processing (AOT) prepares part of the work that normally happens at application startup. Spring analyzes configuration and bean definitions at build time, generating initialization code, proxies, and runtime hints. Spring Data JDBC can also pre-generate implementations for eligible repository query methods.

When combined with **GraalVM Native Image**, AOT outputs are used to compile the application into an executable targeting a specific operating system and architecture. Native images can start faster and use less memory for many workloads, but they require the application to follow a closed-world model: classpath, bean graph, reflection, resources, and proxies must be known ahead of time or declared via hints.

This lesson distinguishes AOT from native compilation, covers Spring Boot/Gradle configuration, explains how Spring Data JDBC generates repository query methods, shows how to declare domain types and dialects, discusses runtime hints, reviews key limitations, and outlines a native image testing workflow.

## 1. Distinguishing AOT and GraalVM Native Image

The two concepts are related but not synonymous:

- **Spring AOT** analyzes the `ApplicationContext` at build time, generating source code/bytecode and runtime hints to initialize the application more statically.
- **GraalVM Native Image** uses static analysis to compile the application and its dependencies into a native executable that does not require bundling a JVM to run.

AOT can also run on the JVM. This is useful for verifying generated initialization code before spending time building a native executable.

~~~mermaid
flowchart TD
    Source["Spring Boot + Spring Data JDBC source"]
    AOT["Spring AOT<br/>processAot"]
    Generated["Generated code<br/>Runtime hints<br/>AOT repository methods"]
    JVM["Run on JVM<br/>spring.aot.enabled=true"]
    Native["GraalVM Native Image<br/>nativeCompile"]
    Executable["Platform-specific executable"]
    Source --> AOT --> Generated
    Generated --> JVM
    Generated --> Native --> Executable
~~~

| Aspect | Standard JVM | AOT on JVM | Native image |
|---|---|---|---|
| Spring context | Mostly analyzed at runtime | Uses generated AOT outputs | Uses generated AOT outputs |
| Repository query methods | May require metadata processing at startup | Uses pre-generated eligible implementations | Uses pre-generated eligible implementations |
| Reflection/resources/proxies | JVM is generally more flexible | Inspects generated hints | Must be statically analyzed or declared upfront |
| Runtime classpath | May vary depending on deployment | Fixed per built artifact | Fixed at build time |
| Output | JAR/classes running on JVM | JAR/classes containing AOT assets | OS/CPU target executable |

Enabling AOT does not automatically turn an application into a native executable. AOT produces the necessary assets; the native image compiler produces the executable.

## 2. What Benefits Does AOT Bring to Spring Data JDBC?

Spring Data JDBC contributes to AOT in several ways:

1. **`ManagedTypes` and entity metadata:** records the set of domain types discovered while processing the application.
2. **Runtime hints for repositories:** supplies reflection hints for entities, return types, Spring Data annotations, and repository fragments.
3. **AOT repository methods:** pre-generates implementations for query methods that can be determined at build time.
4. **Auditing and other integrations:** contributes hints required by related Spring Data features.

Notably, AOT repositories shift part of derived query, annotated query, and named query analysis from startup to build time. As a result, applications can reduce repository metadata processing work at startup.

**AOT repositories do not optimize database execution plans and do not automatically make SQL statements run faster.** If a query is slow due to a missing index, returning too many columns, or an unsuitable JOIN, you still must optimize the query and schema as usual.

## 3. Marking Domain Types for Spring Data Discovery

Spring Data needs to know which domain types it manages. With Spring Data JDBC, use mapping annotations on entities:

~~~java
package com.example.sales.order;

import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Table;

@Table("orders")
public class Order {

    @Id
    private Long id;

    private Long customerId;
    private String status;

    protected Order() {
    }

    public Order(Long customerId) {
        this.customerId = customerId;
        this.status = "DRAFT";
    }

    public Long getId() {
        return id;
    }

    public Long getCustomerId() {
        return customerId;
    }

    public String getStatus() {
        return status;
    }
}
~~~

**`@Table`** helps Spring Data identify the domain type during entity scanning and register it in **`ManagedTypes`**. This matters for native images because they cannot rely on dynamic runtime classpath scanning like a standard JVM.

For child entities mapped to separate tables via **`@MappedCollection`**, ensure the domain mapping is properly recognized by Spring Data. If an application uses a custom package layout or entity scanning setup, configure the managed types set according to your project's Spring Data JDBC configuration.

Do not rely on a native executable discovering classes across packages at runtime. Type discovery must complete during the AOT phase.

## 4. Configuring Gradle for AOT and Native Image

With the Spring Boot Gradle Plugin, you can add the GraalVM Native Build Tools plugin:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '4.1.2'
    id 'org.graalvm.buildtools.native' version '1.1.14'
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-jdbc'
    runtimeOnly 'org.postgresql:postgresql'
}
~~~

This example follows current Spring Boot 4.1.2 and Native Build Tools 1.1.14 documentation. In a real project, use the Spring Boot, Spring Data Relational, GraalVM, and JDBC driver versions supported by your project's dependency management; do not mix arbitrary versions.

When the GraalVM Native Image plugin is applied, Spring Boot automatically configures the AOT plugin and related tasks. Common tasks include:

~~~bash
# Generate AOT code and resources for the application
./gradlew processAot

# Compile the native executable
./gradlew nativeCompile

# Compile and run tests inside a native image
./gradlew nativeTest
~~~

**`nativeCompile`** uses the output from **`processAot`**. **`nativeTest`** uses the AOT output of the application and tests. Native image compilation generally consumes more time and resources than building a JVM JAR.

If you only want to run AOT on the JVM to verify the generated context, you can apply the **`org.springframework.boot.aot`** plugin without the native plugin:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '4.1.2'
}

apply plugin: 'org.springframework.boot.aot'
~~~

After building an artifact with AOT assets, you can run:

~~~bash
java -Dspring.aot.enabled=true -jar build/libs/application.jar
~~~

The command and artifact path may need adjustment based on your project name and Gradle configuration. If the JAR contains no generated AOT assets, setting the system property alone will not create them.

## 5. Which Configuration Decisions Does AOT Fix at Build Time?

Spring AOT analyzes the `ApplicationContext` using the classpath and `Environment` available at build time. Consequently, certain decisions become fixed parts of the processed application:

- The classpath must be determined at build time.
- The bean graph cannot arbitrarily change based on runtime properties.
- Profiles active during AOT may become fixed in the generated configuration.
- Conditions such as **`@ConditionalOnProperty`** are evaluated at build time.
- Beans registered dynamically in ways AOT cannot analyze may be omitted from the generated context or lack hints.

Example:

~~~java
@Configuration
@Profile("production")
class ProductionConfiguration {
    // Beans are only included in the AOT context if the matching profile
    // is active during the AOT build environment.
}
~~~

If AOT runs without the **production** profile enabled, passing **`--spring.profiles.active=production`** when launching the native image cannot guarantee creating beans that were excluded from the generated context.

Similarly, if a bean is created only when **`feature.enabled=true`**, configure that property during **`processAot`**. Do not expect toggling the property when launching the native image to re-evaluate the entire bean graph.

### Avoid Registering Beans That AOT Cannot Infer

Review these patterns carefully:

- Registering singleton instances directly via **`registerSingleton`**.
- Bean definitions using instance suppliers/lambdas or method references that AOT cannot transform.
- Instantiating beans from class names read from runtime configuration.
- Performing custom classpath scanning or creating dynamic proxies/classes at runtime.
- Bean factory methods declaring overly broad return types that prevent AOT from recognizing the concrete implementation.

Prefer **`@Configuration`**, **`@Bean`**, component scanning, and concrete return types. If dynamic bean registration is unavoidable, check Spring Framework's AOT guidance and provide suitable contributions/hints.

## 6. AOT Repositories in Spring Data JDBC

**AOT repositories** are a Spring Data-specific optimization: Spring Data analyzes known query methods at build time and generates implementations for eligible methods.

Example repository:

~~~java
package com.example.sales.order;

import java.util.List;
import java.util.Optional;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jdbc.repository.query.Modifying;
import org.springframework.data.jdbc.repository.query.Query;
import org.springframework.data.repository.CrudRepository;
import org.springframework.data.repository.query.Param;

public interface OrderRepository extends CrudRepository<Order, Long> {

    List<Order> findByStatus(String status);

    Optional<Order> findByExternalReference(String externalReference);

    Page<Order> findByCustomerId(Long customerId, Pageable pageable);

    @Query("SELECT * FROM orders WHERE status = :status")
    List<Order> findOrdersByStatus(@Param("status") String status);

    @Modifying
    @Query("UPDATE orders SET status = :status WHERE id = :id")
    int changeStatus(@Param("id") Long id, @Param("status") String status);
}
~~~

Methods such as **`findByStatus`**, queries with **`@Query`**, named queries, and paginated methods can be analyzed ahead of time. Spring Data generates query method implementations to avoid re-analyzing method metadata on every application startup.

Generated fragments follow a naming pattern like:

~~~text
<Repository FQCN>Impl__Aot
~~~

The fragment is placed in the repository interface's package. This is an internal detail managed by Spring Data. Do not reference generated classes directly in application code because naming and generation details can change between versions.

## 7. Which Query Methods Are Supported by AOT Repositories?

According to Spring Data Relational 4.1.2 documentation, the following groups are eligible unless excluded by another limitation:

| Group | Supported |
|---|---|
| Derived query methods | Yes |
| Queries declared with **`@Query`** | Yes |
| Named query methods | Yes |
| **`@Modifying`** returning **`void`**, **`int`**, **`long`** | Yes |
| Pagination | Yes |
| Return types **`Slice`**, **`Stream`**, **`Optional`** | Yes |
| DTO projections and interface projections | Yes |
| Value Expressions | Yes |

Not every method in a repository interface receives a newly generated implementation. Methods provided by the base repository class or corresponding fragments continue using those fragments' implementations.

## 8. Important Limitations of AOT Repositories

Current documentation lists several excluded or currently unsupported cases:

| Case | Status |
|---|---|
| Methods taking **`ScrollPosition`**, e.g., keyset scrolling | Not yet supported |
| Methods inherited from **`CrudRepository`** | Not regenerated; uses base repository implementation |
| Querydsl methods | Not generated by JDBC AOT repositories |
| Query by Example | Not generated by JDBC AOT repositories |
| Methods with overly complex implementations | May be excluded from AOT generation |
| Methods handled by custom repository implementation fragments | Not standalone query methods for AOT code generation |
| Stored procedure methods | May appear in metadata, but method code is not generated in AOT repositories |

This does not mean excluded methods automatically fail in a native image. They still rely on the base fragment, custom fragment, or respective mechanism and must satisfy the native image/hints requirements of that implementation.

Example method using **`ScrollPosition`**:

~~~java
Window<Order> findFirst100ByStatusOrderById(
    String status,
    ScrollPosition position
);
~~~

This keyset/scrolling form is not part of the AOT repository method set supported in the 4.1.2 documentation. If the application targets native image, verify the specific method against your Spring Data version and consider **`Pageable`**/**`Slice`** pagination if appropriate for the business case.

### Custom Repository Fragments

Example repository with a fragment:

~~~java
public interface OrderSearchRepository {
    List<Order> searchWithSpecialRules(String status);
}

public class OrderSearchRepositoryImpl
        implements OrderSearchRepository {

    @Override
    public List<Order> searchWithSpecialRules(String status) {
        // Custom implementation.
        return List.of();
    }
}
~~~

Methods implemented by this fragment are not rewritten into derived query implementations by the AOT query generator. If the custom fragment uses reflection, resources, or dynamic proxies, the implementation itself must provide any necessary native image hints.

## 9. Generated Repository Metadata

During AOT processing, Spring Data JDBC introspects query methods and stores metadata as JSON alongside the repository interface's package. The metadata can describe:

- Repository name and module.
- Method signatures.
- Normalized queries.
- Count queries for pagination.
- Named query names.
- Fragments to which methods delegate.

Condensed illustrative example:

~~~json
{
  "name": "com.example.sales.order.OrderRepository",
  "module": "JDBC",
  "type": "IMPERATIVE",
  "methods": [
    {
      "name": "findByStatus",
      "signature": "List<Order> findByStatus(String)",
      "query": {
        "query": "SELECT * FROM orders WHERE status = :status"
      }
    }
  ]
}
~~~

This example explains the metadata structure; it is not a configuration file for applications to author manually. Spring Data manages the generated metadata.

Queries in metadata are in normalized form:

- Value expressions are replaced with bind markers.
- Metadata does not capture full runtime bind-value processing.
- **`StartingWith`**/**`EndingWith`** can append wildcards to bound values at runtime.
- Runtime sorting cannot be baked into a fixed query string at build time because sort parameters are only known when the method is called.

## 10. Options to Enable/Disable AOT Repositories

AOT repositories are generated when Spring AOT is enabled. You can disable generation to diagnose issues or temporarily opt out of this optimization:

~~~properties
# Disable AOT repositories for all Spring Data modules
spring.aot.repositories.enabled=false

# Or disable AOT repositories only for Spring Data JDBC
spring.aot.jdbc.repositories.enabled=false
~~~

These two properties have different scopes. Normal applications do not need to disable AOT repositories if all query methods work properly. If disabled during investigation, re-verify the native image because you are changing how repositories are prepared.

Another build-time decision to keep in mind: the Spring Data module implementing a repository is fixed in the AOT output. If you change the implementing module or alter bean conditions affecting repositories, you must re-run AOT processing.

## 11. Providing `JdbcDialect` to Avoid Early Database Access

Spring Data JDBC needs **`JdbcDialect`** to handle SQL differences across databases. The default behavior may detect the dialect by acquiring a connection and reading metadata. During AOT processing, dialect detection can trigger premature database access at build time.

Spring Data Relational documentation recommends providing an explicit dialect to avoid unnecessary database connections during AOT processing.

Example for PostgreSQL in a custom Spring Data JDBC configuration:

~~~java
package com.example.config;

import org.springframework.context.annotation.Configuration;
import org.springframework.data.jdbc.core.dialect.JdbcDialect;
import org.springframework.data.jdbc.core.dialect.JdbcPostgresDialect;
import org.springframework.data.jdbc.repository.config.AbstractJdbcConfiguration;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcOperations;

@Configuration
public class JdbcConfiguration extends AbstractJdbcConfiguration {

    @Override
    public JdbcDialect jdbcDialect(
            NamedParameterJdbcOperations operations) {
        return JdbcPostgresDialect.INSTANCE;
    }
}
~~~

This snippet is suitable only when the application actually uses PostgreSQL. For MySQL, MariaDB, SQL Server, or other databases, select the matching JDBC dialect. In Spring Boot applications using auto-configuration, integrate dialect configuration via the extension point/bean supported by your Boot and Spring Data JDBC versions; avoid creating two competing persistence configurations.

Do not declare the PostgreSQL dialect merely to make an AOT build pass when the runtime database is a different engine. The dialect controls SQL rendering and data type handling, so choosing the wrong dialect can break queries or writes.

## 12. Runtime Hints for Native Images

Native image performs reachability analysis from entry points. GraalVM cannot automatically infer every dynamic behavior, such as:

- Reflective invocations of methods/constructors with no direct calls.
- Loading files/resources from dynamically constructed names.
- Java serialization.
- Creating JDK dynamic proxies from interfaces.
- JNI or native libraries.

Spring AOT and Spring Data contribute many hints automatically, including hints for auditing, managed types, repository entities/return types, repository fragments, and annotations. However, third-party dependencies or custom code may require additional hints.

### Registering a `RuntimeHintsRegistrar`

Example where an external library uses reflection to instantiate **`LegacyPayload`** and reads resources:

~~~java
package com.example.nativeimage;

import org.springframework.aot.hint.MemberCategory;
import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.RuntimeHintsRegistrar;

public class ApplicationRuntimeHints implements RuntimeHintsRegistrar {

    @Override
    public void registerHints(
            RuntimeHints hints,
            ClassLoader classLoader) {

        hints.reflection().registerType(
            LegacyPayload.class,
            MemberCategory.INVOKE_PUBLIC_CONSTRUCTORS,
            MemberCategory.INVOKE_PUBLIC_METHODS
        );

        hints.resources().registerPattern(
            "legacy/config/*.json"
        );
    }
}
~~~

Activate hints with **`@ImportRuntimeHints`**:

~~~java
package com.example.config;

import com.example.nativeimage.ApplicationRuntimeHints;
import org.springframework.aot.hint.annotation.ImportRuntimeHints;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@ImportRuntimeHints(ApplicationRuntimeHints.class)
public class NativeImageConfiguration {
}
~~~

Register only the necessary access. Do not blindly enable reflection on every class or include all resources in the image; overly broad hints reduce the benefits of static analysis and can bloat executable size.

### Hints for Type Binding

For types serialized/deserialized without being inferred by Spring from known endpoints or contracts, use **`@RegisterReflectionForBinding`** or register appropriate reflection hints. Types managed by Spring Data JDBC generally already have hints contributed by Spring Data; add extra hints only when actual errors reveal something missing.

### `RuntimeHintsPredicates`

You can test custom hints without building a native image:

~~~java
@Test
void registersLegacyPayloadHints() {
    RuntimeHints hints = new RuntimeHints();
    new ApplicationRuntimeHints()
        .registerHints(hints, getClass().getClassLoader());

    assertThat(
        RuntimeHintsPredicates.reflection()
            .onType(LegacyPayload.class)
    ).accepts(hints);

    assertThat(
        RuntimeHintsPredicates.resource()
            .forResource("legacy/config/sample.json")
    ).accepts(hints);
}
~~~

These tests verify that the registry contains the expected hints. They do not replace running the native executable and exercising the actual code paths.

## 13. Testing AOT on the JVM Before Building Native

A practical workflow should be layered:

1. Run unit and integration tests on the JVM as usual.
2. Run AOT processing to catch issues in generated bean definitions and repository methods.
3. Run the application on the JVM with **`spring.aot.enabled=true`**.
4. Build the native executable.
5. Run the native executable and integration tests against the target database.
6. Run native tests in CI at an appropriate cadence.

Example testing AOT on the JVM:

~~~bash
java -Dspring.aot.enabled=true -jar build/libs/application.jar
~~~

When the AOT-enabled JVM starts cleanly, confidence increases because the application is using the generated initialization code. However, native images still differ regarding reflection, resources, proxies, class loading, and drivers.

Spring Boot recommends keeping most unit/integration tests on the JVM for a fast feedback loop, and focusing native testing on areas prone to diverge between JVM and native executables.

## 14. Testing Spring Data JDBC in a Native Image

A native smoke test verifying only that the application context starts is not sufficient. For Spring Data JDBC, verify actual operations:

- Repositories are initialized and injected properly.
- Derived query methods return accurate results.
- **`@Query`** and **`@Modifying`** bind parameters properly.
- Pagination/count queries return accurate metadata.
- DTO/interface projections map cleanly.
- Custom repository fragments work.
- Converters, callbacks, and auditing are invoked properly.
- ID generation and optimistic locking work.
- The JDBC driver connects to the database.
- Flyway/Liquibase or migration resources are packaged and readable.
- Transactions commit and roll back properly.
- JSON serialization and resources used by endpoints are present in the image.

In particular, run tests with the real database and JDBC driver. H2 can be useful for fast checks, yet it does not prove PostgreSQL/MySQL/SQL Server drivers work inside a native image.

## 15. Tracing Agent for Finding Missing Hints

The GraalVM Native Image tracing agent can run the JVM application and record reflection, resource, or proxy usages exercised by running code:

~~~bash
java -Dspring.aot.enabled=true \
  -agentlib:native-image-agent=config-output-dir=build/native-agent-config \
  -jar build/libs/application.jar
~~~

After startup, exercise representative flows such as signing in, finding orders, running projection queries, reading config files, and calling endpoints. When the application exits, the agent writes observed hints to the output directory.

The tracing agent is helpful for discovering dynamic behavior missed by AOT, though results cover only executed code paths. If you skip an update flow or a rare query, the agent cannot record hints for that path.

When running the agent across a test suite, the output may include hints needed only by the test framework. Review and filter entries before placing files into:

~~~text
src/main/resources/META-INF/native-image/
~~~

Do not copy the entire output mechanically. Combine the tracing agent with reachability metadata documentation and real native tests.

## 16. Limitations of JDBC Drivers and Third-Party Dependencies

Spring Data JDBC can contribute hints for Spring Data code, but it cannot automatically supply complete hints for every external library.

Components to check:

- Does the JDBC driver have reachability metadata/native support compatible with your GraalVM version?
- Does the driver load resources, charsets, or classes by dynamic name?
- Does the connection pool require special reflection/proxy configuration?
- Do migration libraries have resources/scripts that must be included in the image?
- Do logging, metrics, tracing, or security providers rely on reflection/JNI?
- Do custom converters, type handlers, and callbacks use uninferred reflection?

If a dependency lacks metadata or has runtime behavior incompatible with a closed-world assumption, adding one simple reflection hint may not be enough. Check the library's documentation, the reachability metadata repository, or replace incompatible dependencies/patterns.

A native image is also an executable bound to its target OS and architecture. Building on Linux x86-64 does not produce a Windows ARM64 executable. Build on the matching target or use an appropriate buildpack/CI pipeline.

## 17. Fixed AOT Decisions and Handling Changes

Once generated AOT assets are created, build-time decisions become part of the artifact:

| Change | Re-run AOT? |
|---|---|
| Adding/removing beans or changing **`@Configuration`** | Yes |
| Changing profiles or conditional properties affecting the bean graph | Yes |
| Adding/modifying repository query methods | Yes |
| Changing domain types/repository fragments | Yes |
| Changing dependencies or versions affecting the classpath | Yes |
| Changing only data in the database | No, if AOT code/config is unchanged |
| Changing a runtime property not affecting the bean graph | Usually no, but verify whether AOT evaluated that property |

If switching the Spring Data module backing a repository or moving repository configuration across modules, AOT re-processing is required. Do not reuse stale generated classes with updated source code.

## 18. Common Misconceptions

| Misconception | Reality | How to handle |
|---|---|---|
| Enabling AOT produces a native executable | AOT generates code/hints; the native compiler builds the executable | Run the native build task |
| AOT repositories generate every repository method | Only eligible query methods are generated | Check base methods, custom fragments, and unsupported methods |
| **`CrudRepository.save`/`findById`** are regenerated | Base implementations continue to be used | Keep repository base implementations native-compatible |
| AOT makes SQL faster | Primarily shifts query method analysis to build time | Optimize indexes, SQL, projections, and transactions separately |
| Every **`ScrollPosition`** method is AOT-supported | Keyset/`ScrollPosition` is not currently supported in JDBC AOT repositories | Check version and choose an appropriate API |
| **`@Table`** only sets the table name | It also helps Spring Data discover domain types for `ManagedTypes` | Annotate managed domain types |
| Native image can scan the classpath at runtime | Closed-world does not support JVM-style dynamic classpath scanning | Let scanning happen at build time |
| Spring auto-generates all reflection hints for third-party libraries | Spring mostly knows its own integrations | Check reachability metadata and add hints when needed |
| Running AOT on JVM proves native will run | AOT JVM does not cover all native differences | Build and run native tests |
| Profiles can be switched freely after building a native image | Profile/conditional bean decisions are locked at build time | Build artifacts per target environment/features |
| Running the tracing agent once is enough | Agent records only executed code paths | Exercise representative flows and review hints |
| A native build on one OS runs on all OSes | Executables are platform/architecture-specific | Build for the deployment target |

## 19. Recommended Implementation Workflow

### Development Phase

1. Use standard Spring Data JDBC repositories and query methods.
2. Annotate domain types with **`@Table`** and verify entity scanning.
3. Keep custom repository fragments simple, clear, and free of unnecessary dynamic reflection.
4. Run tests on the JVM against the corresponding database.
5. Enable AOT to catch bean configurations that depend on runtime state.

### Native Preparation Phase

1. Add the GraalVM Native Build Tools plugin.
2. Run **`processAot`** with the appropriate environment/profiles/conditional properties.
3. Provide an explicit **`JdbcDialect`** to avoid early DB access during dialect detection.
4. Check which query methods are AOT-generated and which use fragment/base implementations.
5. Add `RuntimeHints` for dynamic code or third-party dependencies if needed.
6. Run on an AOT-enabled JVM.

### CI/CD Phase

1. Run unit and integration tests on the JVM.
2. Run AOT processing and an AOT-enabled JVM smoke test.
3. Build the native executable for the deployment target.
4. Run native tests or a native integration smoke test.
5. Verify JDBC connectivity, repository CRUD/queries, transactions, and migrations.
6. Measure startup time, memory footprint, and request performance on a representative workload.
7. Record platform, JDK/GraalVM, Spring Boot, and driver versions alongside the artifact.

Measuring startup and memory is necessary to confirm native image provides tangible benefits for the workload. Native builds take longer, so not every service warrants native deployment.

## 20. Practice Exercises

1. Create a Spring Boot application using Spring Data JDBC with an `Order` entity annotated with **`@Table`**.
2. Create **`OrderRepository`** with derived queries, **`@Query`**, **`@Modifying`**, and pagination.
3. Add the GraalVM Native Build Tools plugin and run **`processAot`**.
4. Inspect generated sources, runtime hints, and repository query metadata.
5. Run the application on the JVM with **`spring.aot.enabled=true`**.
6. Build a native executable and run it against a test database.
7. Write a repository method taking **`ScrollPosition`**; identify its AOT limitations in your version.
8. Create a custom repository fragment using reflection on a class determined from configuration; test a native build and add minimal hints.
9. Use **`RuntimeHintsPredicates`** to test custom hints.
10. Run the tracing agent across real repository/query flows; review the output before adding it to resources.
11. Verify the JDBC driver and migration resources inside the native executable.
12. Compare startup time, memory footprint, and request throughput between JVM and native image.

## 21. Takeaways

Spring AOT prepares the `ApplicationContext`, generated code, and runtime hints at build time. GraalVM Native Image uses those outputs to produce a platform-specific executable. Spring Data JDBC adds AOT repository generation for eligible derived, annotated, and named query methods, shifting part of query method analysis to build time.

AOT repositories do not replace base CRUD implementations, do not generate every custom fragment, and currently have limitations with **`ScrollPosition`** and keyset scrolling. Annotate domain types, configure profiles and **`JdbcDialect`** properly, supply runtime hints for dynamic code/dependencies, and test AOT on the JVM before building native. Finally, run native integration tests against a real JDBC driver and database; build success alone is not enough to prove the application works correctly.

## References

- [Spring Data Relational — Ahead of Time Optimizations](https://docs.spring.io/spring-data/relational/reference/jdbc/aot.html)
- [Spring Framework — Ahead of Time Optimizations](https://docs.spring.io/spring-framework/reference/core/aot.html)
- [Spring Boot — Introducing GraalVM Native Images](https://docs.spring.io/spring-boot/reference/packaging/native-image/introducing-graalvm-native-images.html)
- [Spring Boot — Ahead-of-Time Processing with Gradle](https://docs.spring.io/spring-boot/gradle-plugin/aot.html)
- [Spring Boot — Advanced Native Images Topics](https://docs.spring.io/spring-boot/reference/packaging/native-image/advanced-topics.html)
- [Spring Boot — Testing GraalVM Native Images](https://docs.spring.io/spring-boot/how-to/native-image/testing-native-applications.html)
- [Spring Data JDBC — JdbcDialect API](https://docs.spring.io/spring-data/relational/reference/api/java/org/springframework/data/jdbc/core/dialect/JdbcDialect.html)

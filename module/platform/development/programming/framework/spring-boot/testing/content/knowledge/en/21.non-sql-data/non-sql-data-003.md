# @DataElasticsearchTest and differences in support across versions

## 1. Framing the problem correctly

In **Spring Boot - testing**, under **Non-SQL Data**, `@DataElasticsearchTest` is the test slice annotation for **Spring Data Elasticsearch**. It initializes Elasticsearch-related components such as `@Document` entities, repositories, converters, and the appropriate client, instead of loading the entire application.

The annotation name looks identical across Spring Boot generations, yet **support varies across versions** on at least three layers:

1. **Annotation/import and test module:** Spring Boot 2.7/3.x uses the namespace `org.springframework.boot.test.autoconfigure.data.elasticsearch`, whereas Spring Boot 4.x moves to `org.springframework.boot.data.elasticsearch.test.autoconfigure`.
2. **Spring Data Elasticsearch/client:** legacy clients, the Java API client, templates, and auto-configuration modules change across Boot releases; you cannot arbitrarily copy `ElasticsearchRestTemplate` imports from older docs.
3. **Real cluster:** `@DataElasticsearchTest` does not create an H2-style embedded Elasticsearch. To prove queries/indexes/mappings actually run, a configured Elasticsearch server is required, typically via Testcontainers.

The primary example in this lesson uses **Java 17, Spring Boot 3.5.16, JUnit Jupiter, and Elasticsearch 8.17.2 in Testcontainers**. This is a consistent illustrative version set. Sections covering **Boot 2.7 and Boot 4.x** are separated to avoid mixing up packages/dependencies.

A good test does not just ask whether the repository is injected; it also checks **save/get by id, derived query, `Keyword` mapping, refresh so searches see the data, update, and delete**. Before writing tests, determine whether Docker/a cluster is available or whether you are trying to test Java logic without needing real Elasticsearch.

## 2. Elasticsearch is not a JPA database replaceable by H2

| Criterion | Spring Data JPA | Spring Data Elasticsearch |
| --- | --- | --- |
| Storage unit | Table/row | Index/document |
| Entity | `@Entity` | `@Document` |
| Repository | `JpaRepository` | `ElasticsearchRepository` |
| Query API | SQL/JPQL/JPA Criteria | Elasticsearch search/query DSL |
| Mapping | Column/relationship | Field type, analyzer, normalizer |
| Search sees writes immediately? | By isolation/transaction | Near-real-time search; may require refresh |
| Test infrastructure | H2 or real RDBMS | Real Elasticsearch cluster or test double depending on goal |
| Test rollback | `@DataJpaTest` is usually transactional and rolls back | `@DataElasticsearchTest` **does not** auto-rollback indexes like JPA |
| Client | JDBC/JPA provider | Version-appropriate Elasticsearch REST/Java client |

**Trap:** a test that saves a document via `repository.save(...)` and then calls `repository.findById(...)` may PASS while `findByCategory(...)` immediately after writing sees nothing because the Elasticsearch search index has not refreshed yet. Distinguish **GET by id** from **search query**.

A test that only mocks `ElasticsearchRepository` **does not prove real Elasticsearch queries/mappings work**. It can be useful for unit testing a service that consumes the repository, provided it is named and reported strictly within that scope.

## 3. Version matrix of imports and modules

| Spring Boot line | `DataElasticsearchTest` import | Related test artifact | Notable differences |
| --- | --- | --- | --- |
| **2.7.x** | `org.springframework.boot.test.autoconfigure.data.elasticsearch.DataElasticsearchTest` | `spring-boot-test-autoconfigure`, usually via `spring-boot-starter-test` | Older docs reference `ElasticsearchRestTemplate` |
| **3.0–3.5.x** | `org.springframework.boot.test.autoconfigure.data.elasticsearch.DataElasticsearchTest` | `spring-boot-test-autoconfigure`/`spring-boot-starter-test` | Java 17+, Spring Data Elasticsearch 5.x, and Elasticsearch Java API client |
| **4.0–4.1.x** | `org.springframework.boot.data.elasticsearch.test.autoconfigure.DataElasticsearchTest` | `spring-boot-data-elasticsearch-test` module and `spring-boot-starter-data-elasticsearch-test` starter | Dedicated test module, new namespace, and updated client stack |

This is a **matrix based on branches with official documentation/Javadoc**. The annotation was not completely removed in Boot 4.x; on the contrary, **Spring Boot 4.1** documentation still lists `@DataElasticsearchTest`. The crucial change is **package and dependency location**.

### Import in Boot 2.7/3.x

~~~java
import org.springframework.boot.test.autoconfigure.data.elasticsearch.DataElasticsearchTest;
~~~

### Import in Boot 4.x

~~~java
import org.springframework.boot.data.elasticsearch.test.autoconfigure.DataElasticsearchTest;
~~~

**Do not** place both imports in one class. If a Boot 3 project's IDE reports it cannot find the Boot 4 package, that is likely from reading docs for the wrong version, not because Spring Boot 3 lacks Elasticsearch testing. If a Boot 4 project uses the 3.x package, switch to the new test module/starter instead of pulling a Boot 3 jar into Boot 4.

### Do not mix Spring Boot major versions

Gradle plugins, BOM, `spring-boot-starter-data-elasticsearch`, `spring-boot-starter-test`, and dedicated test modules must align with the same branch. Forcing a `spring-boot-test-autoconfigure:3.x` jar into a Boot 4.x application just to bring back an annotation can cause Spring/auto-configuration runtime errors.

## 4. What does DataElasticsearchTest load, and what does it exclude?

In Spring Boot 3.5, the test slice enables only the auto-configurations related to **Elasticsearch data, sync/reactive repositories, and clients** when dependencies/conditions match. It focuses on components such as:

- `@Document` metadata/domain types.
- Spring Data Elasticsearch repository interfaces.
- Mapping converters and the appropriate `ElasticsearchOperations`/template.
- The Elasticsearch client configured from application properties or connection details.
- Spring TestContext, JUnit Jupiter, and certain JSON/cache infrastructure.

It generally **does not auto-scan** ordinary `@Service`, `@RestController`, `@Component` beans, or `@ConfigurationProperties`.

~~~text
@DataElasticsearchTest
     |
     +-- Repository beans + @Document metadata
     +-- ElasticsearchOperations / converter / client
     +-- Data slice auto-configurations
     |
     X-- Does NOT load @RestController by default
     X-- Does NOT load business services by default
     X-- Does NOT bind every @ConfigurationProperties bean by default
     X-- Does NOT start an embedded Elasticsearch server
~~~

As a result, a repository test is lighter than `@SpringBootTest`. However, **a smaller slice does not mean unit-test speed**: an Elasticsearch container still incurs image pull/startup and index setup costs.

If the goal is testing HTTP controller → service → real Elasticsearch, use a broader integration test. If the goal is a pure Java POJO mapper, do not load a Spring context at all.

### @Document differs from @Entity

`@Document` belongs to `org.springframework.data.elasticsearch.annotations.Document`. `@Id` in Elasticsearch examples belongs to `org.springframework.data.annotation.Id`. Do not use `jakarta.persistence.Entity`/`JpaRepository` expecting Elasticsearch auto-config to create the repository.

### Is reactive supported?

Spring Boot 3.5's slice auto-config list includes **reactive Elasticsearch repositories/clients**. However, whether reactive beans are created depends on classpath, Spring Data version, and configuration conditions. **Do not conclude every `@DataElasticsearchTest` automatically has `ReactiveElasticsearchOperations`**, and do not swap sync methods for `Flux` solely because the project uses WebFlux.

## 5. Choosing the right testing level

| Goal | Recommended scope | Reason |
| --- | --- | --- |
| Test document → Elasticsearch JSON mapping | `@DataElasticsearchTest` with real Elasticsearch | Verifies converter and mapping |
| Derived repository query `findByCategory` | Data slice + real cluster + refresh | Verifies query and search semantics |
| Index template/analyzer configuration | Data slice or integration with matching cluster version | Needs real Elasticsearch processing |
| Service logic picking keywords, pagination | Unit test service with mocked repository | Not a query engine test |
| HTTP status/body for search | `@WebMvcTest`/`@WebFluxTest` | Tests web boundary, mocks out-of-slice service |
| HTTP flow through to real Elasticsearch | `@SpringBootTest` + Testcontainers | Multi-layer test |
| TLS, auth, multi-node cluster, index lifecycle | Integration in an appropriate environment | Beyond simple repository scope |

The rule is **never mock the object under test**. If you want to test the real `CatalogItemRepository`, do not put `@MockitoBean` on the repository itself; doing so only tests Mockito.

## 6. Project setup for Java 17 / Spring Boot 3.5

Structure:

~~~text
build.gradle
src/main/java/com/example/esdemo/
    ElasticsearchDemoApplication.java
    CatalogItem.java
    CatalogItemRepository.java
    CatalogSearchService.java
src/test/java/com/example/esdemo/
    ElasticsearchContainerTestConfig.java
    CatalogElasticsearchSliceTest.java
~~~

**File `build.gradle` (Gradle Groovy DSL):**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-elasticsearch'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.boot:spring-boot-testcontainers'
    testImplementation 'org.testcontainers:elasticsearch'
    testImplementation 'org.testcontainers:junit-jupiter'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
~~~

- `spring-boot-starter-data-elasticsearch`: Spring Data Elasticsearch and the client compatible with the Boot 3.5 BOM.
- `spring-boot-starter-test`: JUnit Jupiter, AssertJ, Spring Boot test infrastructure.
- `spring-boot-testcontainers`: `@ServiceConnection` annotation and integration between Boot and Testcontainers.
- `org.testcontainers:elasticsearch`: `ElasticsearchContainer`. The `junit-jupiter` module supports JUnit-managed container fields, though it is not strictly required for the container-bean pattern in the primary example.
- Do not pin separate versions for Spring Data/Elasticsearch Java client/Testcontainers in dependencies because the **BOM** manages them.

Requires Gradle Wrapper, Docker daemon, and permission to pull container images. **Use Elasticsearch image 8.17.2 for the demo**, matching the official Testcontainers example in Spring Boot 3.5 docs. Do not swap the image to `latest` without re-running compatibility tests.

**`src/main/java/com/example/esdemo/ElasticsearchDemoApplication.java`:**

~~~java
package com.example.esdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ElasticsearchDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(ElasticsearchDemoApplication.class, args);
    }
}
~~~

The application class sits in the parent package of domain/repository/tests. `@DataElasticsearchTest` locates the root configuration while still restricting bean scanning; `main` is not invoked when running tests.

## 7. Document with explicit mapping

**`src/main/java/com/example/esdemo/CatalogItem.java`:**

~~~java
package com.example.esdemo;

import java.util.Objects;

import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "catalog_items_test", createIndex = false)
public class CatalogItem {

    @Id
    private String id;

    @Field(type = FieldType.Keyword)
    private String sku;

    @Field(type = FieldType.Keyword)
    private String category;

    @Field(type = FieldType.Text)
    private String title;

    @Field(type = FieldType.Integer)
    private Integer quantity;

    protected CatalogItem() {
    }

    public CatalogItem(
            String id,
            String sku,
            String category,
            String title,
            Integer quantity
    ) {
        this.id = Objects.requireNonNull(id, "id");
        this.sku = Objects.requireNonNull(sku, "sku");
        this.category = Objects.requireNonNull(category, "category");
        this.title = Objects.requireNonNull(title, "title");
        this.quantity = Objects.requireNonNull(quantity, "quantity");
    }

    public String getId() {
        return id;
    }

    public String getSku() {
        return sku;
    }

    public String getCategory() {
        return category;
    }

    public String getTitle() {
        return title;
    }

    public Integer getQuantity() {
        return quantity;
    }

    public void setQuantity(Integer quantity) {
        this.quantity = Objects.requireNonNull(quantity, "quantity");
    }
}
~~~

### Why choose Keyword and Text?

`FieldType.Keyword` stores values suited for exact matching and aggregations, such as `category="office"` or SKU. `FieldType.Text` is for content like `title`, typically processed by an analyzer; derived queries on `Text` can exhibit token matching behavior different from an exact keyword match.

Therefore, **do not write identical expected results for `keyword` and `text`** without verifying the mapping/analyzer.

### Why createIndex = false?

Some versions of Spring Data Elasticsearch **auto-create the index during repository initialization** when `@Document(createIndex=true)` (default). The example deliberately sets `createIndex=false` so test setup controls exactly when to delete/create the index and mapping via `IndexOperations`.

In production, index settings/mappings/aliases may be handled by dedicated migrations or provisioners; never let tests delete a production index. `createIndex=false` does not make Spring Data ignore document metadata.

## 8. Real repository and a service intentionally outside the slice

**`src/main/java/com/example/esdemo/CatalogItemRepository.java`:**

~~~java
package com.example.esdemo;

import java.util.List;

import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;

public interface CatalogItemRepository
        extends ElasticsearchRepository<CatalogItem, String> {

    List<CatalogItem> findByCategory(String category);
}
~~~

`ElasticsearchRepository` has its implementation generated by Spring Data. `findByCategory` is a **derived query** on a `Keyword`-mapped field. Tests will store real data in Elasticsearch and invoke this method, not mock results.

**`src/main/java/com/example/esdemo/CatalogSearchService.java`:**

~~~java
package com.example.esdemo;

import java.util.List;

import org.springframework.stereotype.Service;

@Service
public class CatalogSearchService {
    private final CatalogItemRepository repository;

    public CatalogSearchService(CatalogItemRepository repository) {
        this.repository = repository;
    }

    public List<CatalogItem> inCategory(String category) {
        return repository.findByCategory(category);
    }
}
~~~

This service demonstrates the **boundary of the data slice**: the real repository can be injected, whereas an ordinary `@Service` is not auto-scanned in `@DataElasticsearchTest`. To test service logic, use a unit test or deliberate `@Import(CatalogSearchService.class)`, rather than pulling controllers/schedulers into the Elasticsearch slice by accident.

## 9. Elasticsearch Testcontainers managed by the Spring context

**`src/test/java/com/example/esdemo/ElasticsearchContainerTestConfig.java`:**

~~~java
package com.example.esdemo;

import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.boot.testcontainers.service.connection.Ssl;
import org.springframework.context.annotation.Bean;

import org.testcontainers.elasticsearch.ElasticsearchContainer;

@TestConfiguration(proxyBeanMethods = false)
public class ElasticsearchContainerTestConfig {

    @Bean
    @ServiceConnection
    @Ssl
    ElasticsearchContainer elasticsearchContainer() {
        return new ElasticsearchContainer(
                "docker.elastic.co/elasticsearch/elasticsearch:8.17.2"
        );
    }
}
~~~

Why declare the container as a **Spring bean**?

1. Spring Boot manages the container bean's lifecycle: starting it before dependent client beans and stopping it when the context closes.
2. `@ServiceConnection` derives connection details from `ElasticsearchContainer`. Boot auto-config uses the right URL/TLS/credentials without hardcoding `http://localhost:9200`.
3. `@Ssl` supports container-side SSL detection and client configuration in Boot 3.5. It does not turn a non-TLS server into an HTTPS server.
4. When Spring TestContext caches contexts across multiple test classes, binding container lifecycle to the context avoids failures where client beans stay alive after a JUnit-managed container has stopped.
5. `@Import(ElasticsearchContainerTestConfig.class)` in tests clearly scopes the configuration to testing only.

This is a **test** environment; never embed production credentials or run destructive queries against a user's cluster.

### Alternative: static @Container

In Boot 3.5 you can also declare:

~~~java
@Testcontainers
@DataElasticsearchTest
class AlternativeContainerStyle {

    @Container
    @ServiceConnection
    @Ssl
    static ElasticsearchContainer elasticsearch =
            new ElasticsearchContainer(
                    "docker.elastic.co/elasticsearch/elasticsearch:8.17.2"
            );

    // @Autowired repository, then write appropriate @Test methods.
}
~~~

This is an **illustrative skeleton**, requiring imports and test methods. `@Testcontainers`/`@Container` puts JUnit in charge of lifecycle. If a Spring context is cached after the container stops, client beans pointing to that container can fail in another class; prefer a container bean when lifecycle should match the context. Do not declare both styles simultaneously unless you intend to run two servers.

## 10. Complete @DataElasticsearchTest suite

**`src/test/java/com/example/esdemo/CatalogElasticsearchSliceTest.java`:**

~~~java
package com.example.esdemo;

import java.util.List;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.elasticsearch.DataElasticsearchTest;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Import;
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.IndexOperations;

import static org.assertj.core.api.Assertions.assertThat;

@DataElasticsearchTest
@Import(ElasticsearchContainerTestConfig.class)
class CatalogElasticsearchSliceTest {

    @Autowired
    CatalogItemRepository repository;

    @Autowired
    ElasticsearchOperations operations;

    @Autowired
    ApplicationContext context;

    @BeforeEach
    void resetIndex() {
        IndexOperations index = operations.indexOps(CatalogItem.class);

        if (index.exists()) {
            assertThat(index.delete()).isTrue();
        }

        assertThat(index.createWithMapping()).isTrue();
        assertThat(index.exists()).isTrue();
    }

    @Test
    void onlyElasticsearchSliceBeansAreLoaded() {
        assertThat(repository).isNotNull();
        assertThat(operations).isNotNull();
        assertThat(context.getBeanNamesForType(
                CatalogSearchService.class
        )).isEmpty();
    }

    @Test
    void saveThenFindById_preservesMappedFields() {
        repository.save(new CatalogItem(
                "P-1", "SKU-7", "office", "Notebook", 4
        ));

        CatalogItem stored = repository.findById("P-1")
                .orElseThrow();

        assertThat(stored.getId()).isEqualTo("P-1");
        assertThat(stored.getSku()).isEqualTo("SKU-7");
        assertThat(stored.getCategory()).isEqualTo("office");
        assertThat(stored.getTitle()).isEqualTo("Notebook");
        assertThat(stored.getQuantity()).isEqualTo(4);
    }

    @Test
    void derivedQuery_usesKeywordCategoryAfterRefresh() {
        repository.save(new CatalogItem(
                "P-1", "SKU-7", "office", "Notebook", 4
        ));
        repository.save(new CatalogItem(
                "P-2", "SKU-8", "books", "Novel", 9
        ));

        operations.indexOps(CatalogItem.class).refresh();

        List<CatalogItem> found =
                repository.findByCategory("office");

        assertThat(found)
                .extracting(CatalogItem::getId)
                .containsExactly("P-1");

        assertThat(repository.findByCategory("missing"))
                .isEmpty();
    }

    @Test
    void updateThenGetById_returnsNewQuantity() {
        repository.save(new CatalogItem(
                "P-1", "SKU-7", "office", "Notebook", 4
        ));

        CatalogItem item = repository.findById("P-1")
                .orElseThrow();
        item.setQuantity(8);
        repository.save(item);

        assertThat(repository.findById("P-1").orElseThrow()
                .getQuantity()).isEqualTo(8);
    }

    @Test
    void deleteById_removesStoredDocument() {
        repository.save(new CatalogItem(
                "P-1", "SKU-7", "office", "Notebook", 4
        ));

        repository.deleteById("P-1");

        assertThat(repository.findById("P-1")).isEmpty();
    }
}
~~~

### What do these cases prove?

| Case | Expected outcome | Feature tested |
| --- | --- | --- |
| Bean scope | Repository and operations present; business service absent | Spring slice filtering |
| Save / findById | Document saved and fields read accurately | Mapping, converter, GET by id |
| Derived query | Only `office` category document returned | Query, Keyword mapping, refresh |
| Update | New quantity written and read back | Real document write |
| Delete | Document no longer found by id | Repository delete |

Each test resets the index before running. The example **does not run tests in parallel** on the same index; if enabling parallel JUnit/CI workers, isolate index names or containers. `index.delete()` is a real destructive operation: use only on a **dedicated test cluster**, never on shared Elasticsearch.

### Do not treat contextLoads as the final verdict

A test that only checks `assertThat(repository).isNotNull()` proves relatively narrow wiring, **not queries or mappings**. Tests that save and search force Elasticsearch to execute the operations under test.

### Why not mock the repository?

Because the lesson's goal is **Spring Data Elasticsearch**, replacing the repository with a mock only checks stubbed data. You can mock the repository when unit testing `CatalogSearchService` in plain Java, whereas testing `findByCategory` requires Spring Data's real implementation against a real server.

## 11. Refresh and search consistency

Elasticsearch features **near-real-time search**: right after writing a document, a search query may temporarily miss it even though GET by id already sees it.

Unreliable example:

~~~java
repository.save(new CatalogItem(
        "P-1", "SKU-7", "office", "Notebook", 4
));

assertThat(repository.findByCategory("office"))
        .hasSize(1);
~~~

When tests need search visibility immediately after writing, use:

~~~java
repository.save(new CatalogItem(
        "P-1", "SKU-7", "office", "Notebook", 4
));

operations.indexOps(CatalogItem.class).refresh();

assertThat(repository.findByCategory("office"))
        .extracting(CatalogItem::getId)
        .containsExactly("P-1");
~~~

`IndexOperations.refresh()` in Spring Data Elasticsearch is an index-level operation. It makes tests deterministic; **it is not advice to refresh after every production write**. Overly frequent refreshes increase indexing/search overhead.

Different repository paths and `ElasticsearchOperations` have differing refresh policies depending on version and configuration. Do not assume every method shares the same behavior; tests must explicitly define **when data is expected to become searchable**.

If production requires read-your-write immediately after updates, design an explicit refresh policy (e.g., wait for refresh as appropriate) and accept the performance trade-off.

## 12. Version differences also affect clients and templates

Some Spring Boot 2.7 docs use `ElasticsearchRestTemplate`. Boot 3.5 and Spring Data Elasticsearch 5.x focus on `ElasticsearchTemplate`/the modern Java API client. Boot 4.x further changes client organization and documents REST5.

| Component | Common in Boot 2.7 | Boot 3.x | Boot 4.x |
| --- | --- | --- | --- |
| Test annotation | `boot.test.autoconfigure` namespace | Same namespace as Boot 2.7 | `boot.data.elasticsearch.test.autoconfigure` namespace |
| Spring Data major | Older than 3.x line | Spring Data Elasticsearch 5.x | Newer Spring Data Elasticsearch per Boot 4.x BOM |
| Template | `ElasticsearchRestTemplate` in older docs | `ElasticsearchTemplate` or `ElasticsearchOperations` interface | Template/interface for new release |
| Client | Legacy REST client | Elasticsearch Java API client | Includes REST5 client and new client stack |
| Test packaging | `spring-boot-test-autoconfigure` | `spring-boot-test-autoconfigure` | `spring-boot-data-elasticsearch-test` |
| Testcontainers shortcut | Often `@DynamicPropertySource` or properties | `@ServiceConnection` in Boot 3.1+ | Per Boot 4.x API/module |

**Safe tip:** inject **`ElasticsearchOperations`** when tests do not need the concrete implementation. However, interfaces also evolve across Spring Data releases, so there is no promise a source file written for Boot 2.7 will compile unchanged on Boot 4.

**Core point:** choose the right Spring Boot BOM and let it select the compatible Spring Data Elasticsearch/client. Do not manually pin an Elasticsearch 9.x client in a Boot 2.7 project just to reach a newer server.

## 13. Spring Boot 4.x: imports and dependencies must change

**Boot 4.x import:**

~~~java
import org.springframework.boot.data.elasticsearch.test.autoconfigure.DataElasticsearchTest;
~~~

**Boot 4.x-specific dependency snippet (illustrative, DO NOT use in the Boot 3.5 `build.gradle` above):**

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-elasticsearch'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.boot:spring-boot-starter-data-elasticsearch-test'
}
~~~

Spring Boot 4 has the `spring-boot-data-elasticsearch-test` module and the `spring-boot-starter-data-elasticsearch-test` feature test starter. Never add test starters from two different Boot majors to the same project.

Several Elasticsearch auto-configuration package names also changed. If your tests contain `@ImportAutoConfiguration(Elasticsearch...AutoConfiguration.class)` or `excludeAutoConfiguration` pointing to Boot 3 classes, migration requires updating **those imports as well**.

### When a Boot 4 project reports annotation not found

In order:

1. Verify the Gradle plugin/BOM/parent is actually Boot **4.x**.
2. Check that the dedicated test-scope starter has been declared.
3. Switch imports to the `org.springframework.boot.data.elasticsearch.test.autoconfigure` namespace.
4. Inspect the dependency tree to eliminate stray Boot 3 jars.
5. Compile the test code before investigating Elasticsearch connection issues.

Do not blame Docker for `cannot find symbol`: compile errors relate to packages/classpath, whereas Docker typically causes **runtime** errors when containers/clusters need to start.

## 14. Boot 2.7/3.0: what cannot be copied verbatim?

In Boot 2.7, `@DataElasticsearchTest` already appeared in documentation using the same namespace as Boot 3.x. However, the `@ServiceConnection` code from Boot 3.5 **cannot be copied verbatim** to Boot 2.7: service connection integration was introduced in Boot 3.1.

An older Testcontainers setup can use `@DynamicPropertySource`:

~~~java
@DynamicPropertySource
static void elasticsearchProperties(DynamicPropertyRegistry registry) {
    registry.add(
            "spring.elasticsearch.uris",
            () -> elasticsearch.getHttpHostAddress()
    );
}
~~~

This is an **illustrative skeleton**, assuming a started static Elasticsearch container named `elasticsearch` and a Boot version supporting this property. Verify the exact URI scheme, TLS, credentials, and property names for your Boot branch; never combine `@ServiceConnection` with conflicting hardcoded properties.

With Boot 3.0 (prior to Boot 3.1 service connections), use the corresponding dynamic connection configuration as well, while keeping the **`@DataElasticsearchTest` import in the Boot 3.x namespace**.

### Why can template names fail after migration?

If legacy code injects `ElasticsearchRestTemplate`, newer Spring Data releases may no longer ship that class or constructor. Migrate according to your current branch's documentation, preferring `ElasticsearchOperations` for shared APIs. Do not force a Spring Data Elasticsearch 4.x artifact into Boot 3.5 just to keep an old class name.

## 15. Reactive Elasticsearch: same slice, different contract

An application might use:

~~~java
interface ReactiveCatalogRepository
        extends ReactiveElasticsearchRepository<CatalogItem, String> {
    Flux<CatalogItem> findByCategory(String category);
}
~~~

This is a **skeleton**, requiring Spring Data Reactive Elasticsearch/Reactor imports and proper configuration. When using reactive APIs, tests must **subscribe to the publisher**:

~~~java
StepVerifier.create(repository.findById("P-1"))
        .assertNext(item ->
                assertThat(item.getSku()).isEqualTo("SKU-7"))
        .verifyComplete();
~~~

This snippet is an illustrative test body; it requires a `ReactiveElasticsearchRepository` bean and a saved P-1 document.

For reactive index operations:

~~~java
StepVerifier.create(
        reactiveOperations.indexOps(CatalogItem.class).refresh()
).verifyComplete();
~~~

Here `reactiveOperations` must be **`ReactiveElasticsearchOperations`**, because `ReactiveIndexOperations.refresh()` returns `Mono<Void>`. In the primary example, `ElasticsearchOperations.indexOps(...).refresh()` returns `void`; do not pass that to `StepVerifier`.

Although Boot 3.5 lists reactive client/repository auto-configs in the data slice, that does not guarantee reactive beans are created if dependencies or conditions are missing. When testing production WebFlux controllers, use `@WebFluxTest`/`@SpringBootTest` as appropriate; data slice tests do not verify HTTP reactive routing.

## 16. When do you need @Import or @ConfigurationProperties?

If a repository test needs custom converters or a small mapping config:

~~~java
@DataElasticsearchTest
@Import(CustomElasticsearchConvertersConfig.class)
class CatalogWithConverterTest {
    // Test real mapping with the imported configuration.
}
~~~

This is a skeleton; `CustomElasticsearchConvertersConfig` must be a real class in your project. Do not pull the entire `@Service`/`@Configuration` graph into the data slice just to satisfy a single dependency.

If a test needs a specific properties bean:

~~~java
@DataElasticsearchTest(
        properties = "app.search.allow-synonyms=true"
)
@EnableConfigurationProperties(SearchFeatureProperties.class)
class CatalogWithPropertiesTest {
    // Test uses the registered SearchFeatureProperties bean.
}
~~~

`@DataElasticsearchTest(properties=...)` **supplies property values**, yet does not auto-register every `@ConfigurationProperties` class. Use `@EnableConfigurationProperties` when a real properties class needs binding. Both examples illustrate annotation setup, not standalone Java files; do not apply them if your project lacks those classes.

If a real business service is needed, import that service individually and mock out-of-scope dependencies. However, when the list of imported beans keeps growing, consider `@SpringBootTest` instead of breaking slice boundaries.

## 17. What if CI has no Docker?

Slice tests with an Elasticsearch client **do not strictly have to use Testcontainers**, yet they must have a suitable backend to test real behavior:

- An isolated Elasticsearch service provisioned by CI.
- A test cluster separate from production, with dedicated indexes and clear cleanup.
- Testcontainers with properly configured Docker/Colima/Podman.
- Unit tests using mocked repositories, **making no claims** about queries or mappings.

If tests run in a Docker-less environment, never report "Elasticsearch mapping PASS" when no server ran. Classify accurately as **test infrastructure unavailable**. If mapping does not need testing, use Mockito in unit tests and name those tests honestly within their scope.

### Do not use a production cluster as a fixture

Calls like `index.delete()`, `repository.deleteAll()`, or deleting index templates can destroy real data. The demo creates/deletes indexes **only** on an ephemeral container. Against a shared test cluster, scope index names by build/test namespace with restricted permissions.

### Test data and parallel execution

Running JUnit in parallel or having multiple CI workers point to the same index causes failures:

~~~text
Test A: delete index
Test B: save document
Test A: create index
Test B: search -> index missing / unexpected results
~~~

Separate containers/indexes per worker or enforce isolation. Never use `Thread.sleep` to mask races. Spring TestContext caching can also reuse contexts; manage container lifecycle so it outlives client beans.

## 18. Common errors and fixes

| Symptom | Possible cause | Fix |
| --- | --- | --- |
| `DataElasticsearchTest` import missing on Boot 4 | Using Boot 3 namespace | Switch to Boot 4 import, add feature test starter |
| Boot 4 namespace import missing on Boot 3 | Copied Boot 4 snippet into Boot 3 | Keep `boot.test.autoconfigure...` namespace |
| Missing `ElasticsearchRestTemplate` | Using legacy client/template | Follow Spring Data version, prefer `ElasticsearchOperations` |
| Context fails to start | Missing cluster/client/config/credentials | Check root cause and test server connection |
| Test defaults to calling localhost:9200 | Missing Testcontainers/properties | Use `@ServiceConnection` or proper connection config |
| TLS handshake/auth errors | TLS/client credentials mismatch server | Verify trust/cert/SSL properties |
| `NoSuchBeanDefinitionException` for `@Service` | Service outside slice | Separate unit test or explicit import |
| Repository not found | Wrong package scan/dependencies | Check repository interface, starter, and package |
| Index missing | `createIndex=false` and never created | Create index/mapping in setup |
| `findById` finds doc, search returns empty | Index not refreshed yet | `IndexOperations.refresh()` |
| Field search returns wrong hits | `Text` vs. `Keyword` or analyzer | Verify mapping/query on real cluster |
| Passes alone, fails in full suite | Parallel index deletion, container cache lifecycle | Isolation / context-managed container |
| Docker fails to start | Daemon/permissions/memory/image | Check CI resources and Docker logs |
| Reactive test complains method is `void` | Confused sync with reactive index ops | Use `ReactiveElasticsearchOperations` |
| Unit mock test used as integration verdict | Repository never called for real | Add real Elasticsearch tests |
| Boot 4 test has mixed-version classpath | Mixing 3.x/4.x test modules | Align BOM/versions and check dependency tree |

**Never wedge in a jar from another major version to silence a compile error.** Check the Spring Boot plugin, BOM, dependency tree, and imports first; only then investigate Elasticsearch runtime errors.

## 19. Step-by-step migration workflow

### Boot 2.7 to Boot 3.x

1. Upgrade JDK to meet Boot 3 requirements (Java 17+).
2. Align Boot plugin, BOM, Spring Data Elasticsearch, and Elasticsearch Java client.
3. Keep `@DataElasticsearchTest` under `org.springframework.boot.test.autoconfigure.data.elasticsearch` in 3.x.
4. Review `ElasticsearchRestTemplate`, legacy REST clients, repository query syntax, and mappings.
5. Verify compatible Elasticsearch server images; do not pick 7.x/8.x/9.x at random.
6. On Boot 3.1+, consider `@ServiceConnection`; on 3.0 continue configuring dynamically via supported tools.
7. Re-run save/find, search with refresh, update/delete, and TLS-enabled environment tests as expected.

### Boot 3.x to Boot 4.x

1. Change imports to `org.springframework.boot.data.elasticsearch.test.autoconfigure.DataElasticsearchTest`.
2. Add `spring-boot-starter-data-elasticsearch-test` to test scope per Boot 4's dependency model.
3. Audit auto-configuration class packages and REST5/Java API client usage.
4. Avoid leaving `spring-boot-test-autoconfigure:3.x` on a Boot 4 classpath.
5. Check Testcontainers/module versions, service connections/SSL, and server images.
6. Recompile and re-run **mapping/query** tests; `contextLoads` passing alone is not enough.
7. Separate production index schema/migration changes from Java import updates.

Do not treat a lesson written for Boot 3.5 as "universally runnable" on Boot 2.7 or Boot 4.x. Version-specific import lines and dependencies are part of the lesson's contract.

## 20. Running the suite, QA, and conclusion

From a directory with Gradle Wrapper, Java 17+, and Docker running:

~~~bash
./gradlew test --tests "com.example.esdemo.CatalogElasticsearchSliceTest"
~~~

On Windows PowerShell:

~~~powershell
.\gradlew.bat test --tests "com.example.esdemo.CatalogElasticsearchSliceTest"
~~~

The sample suite has **5 `@Test` methods**: slice boundaries, save/find by id, search by `Keyword`, update, and delete. Based on the APIs and example design, the expected result is all assertions PASSING **when matching dependencies, Docker image, and Elasticsearch server are present**. This is an assessment from reviewing the code logic, **not an actual JUnit/Docker execution log**. The code does not print `System.out.println`, so there is no fixed application stdout; Gradle/cluster logs depend on the environment.

Checklist:

- [ ] Identified the exact Spring Boot major/minor and `@DataElasticsearchTest` import?
- [ ] Boot 3.x uses the old namespace; Boot 4.x uses the new test namespace/module?
- [ ] Plugin/BOM/test starters do not mix major versions?
- [ ] Document uses Spring Data `@Document`/`@Id`, and the repository is not mocked?
- [ ] Real Elasticsearch server available, or explicitly noted as a mocked unit test?
- [ ] Docker image version pinned and runnable environment available?
- [ ] `@ServiceConnection`/properties match Boot version and TLS?
- [ ] Test index created in isolation without harming shared/production data?
- [ ] Search queries perform the required refresh step?
- [ ] `Keyword`/`Text` mappings tested with the right semantics?
- [ ] Tests assert query behavior, not just context startup?
- [ ] `@SpringBootTest` avoided when only the repository slice is needed?
- [ ] If reactive, methods actually return `Mono`/`Flux` and tests subscribe?
- [ ] Container lifecycle compatible with Spring TestContext caching?
- [ ] Migration test plan defined for each Boot major version?

**Conclusion:** `@DataElasticsearchTest` is the official choice for Spring Data Elasticsearch slice testing, yet **version-dependent support** affects namespaces/test modules, clients/templates, and Elasticsearch server connections. **Boot 2.7/3.x** and **Boot 4.x** do not share the same imports. When you need to test real queries, provide a test cluster, manage index/mapping setup and refresh; when you need full HTTP flows, elevate the scope to a separate integration test.

### Official references

- [Spring Boot 2.7 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/docs/2.7.15/reference/htmlsingle/)
- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html)
- [Spring Boot 3.5 — Test Slices](https://docs.spring.io/spring-boot/3.5/appendix/test-auto-configuration/slices.html)
- [Spring Boot 3.5 — Testcontainers and service connections](https://docs.spring.io/spring-boot/3.5/reference/testing/testcontainers.html)
- [Spring Boot 4.1 — Test Modules](https://docs.spring.io/spring-boot/reference/testing/test-modules.html)
- [Spring Boot 4.1 — DataElasticsearchTest Javadoc](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/data/elasticsearch/test/autoconfigure/DataElasticsearchTest.html)
- [Spring Data Elasticsearch — Object Mapping](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/object-mapping.html)
- [Spring Data Elasticsearch — Operations](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/template.html)
- [Spring Data Elasticsearch 5.5 — IndicesTemplate API](https://docs.spring.io/spring-data/elasticsearch/docs/5.5.x/api/org/springframework/data/elasticsearch/client/elc/IndicesTemplate.html)
# Launching Version-Compatible Elasticsearch with Testcontainers

Integration tests for Spring Data Elasticsearch need a real Elasticsearch server to verify mappings, query DSL, repositories, bulk operations, and client behavior. Mocking repositories or HTTP responses cannot confirm that the application is actually compatible with the running Elasticsearch server.

Testcontainers makes it possible to launch Elasticsearch in Docker within the test lifecycle. The key is choosing the right image version: the server version must fall within the compatibility range of the Spring Data Elasticsearch and Elasticsearch Java API Client versions used by the project. If you use a floating tag such as latest, tests may pass today and silently change behavior tomorrow when a new image is released.

This lesson explains how to check compatibility, pin image versions, configure the container, wire Spring Boot/Spring Data, write integration tests, and handle common issues in CI.

## 1. Why Use Testcontainers?

### 1.1. Unit Tests and Integration Tests Verify Two Different Things

Unit tests are suitable for testing application logic independently of Elasticsearch:

- Building queries from inputs.
- Converting between DTOs and entities.
- Calculating business values.
- Error handling and retries at the service layer.
- Testing mappers or callbacks using mocks.

Integration tests need to verify the real interaction between Spring Data, the client, and the Elasticsearch server:

- Mappings are created properly.
- Field types, analyzers, and nested mappings are accepted by the server.
- Repository save/find/search operations work.
- Query DSL actually executes.
- Bulk responses have the expected semantics.
- Sorting, aggregations, pagination, and highlighting are compatible.
- The server version does not cause errors with the application's client.

Mocks cannot verify behavior that depends on Elasticsearch's parser, mapping engine, query execution, or security.

### 1.2. Testcontainers Provides a Production-Like Environment

Testcontainers creates temporary containers from a Docker image, exposes dynamic ports for tests, and cleans up the container when the lifecycle ends.

~~~mermaid
flowchart TD
    A[JUnit test starts] --> B[Testcontainers starts Elasticsearch image]
    B --> C[Container waits until ready]
    C --> D[Spring context receives host and mapped port]
    D --> E[Spring Data client connects]
    E --> F[Integration tests run]
    F --> G[Container is stopped and removed]
~~~

This environment allows tests to run against a real Elasticsearch server without requiring developers to install Elasticsearch locally.

### 1.3. Testcontainers Does Not Guarantee Version Compatibility Automatically

Testcontainers simply starts whatever image the test requests. It does not automatically choose a server version compatible with Spring Data Elasticsearch.

An application can still start the container successfully and then fail during client creation, mapping, querying, or response conversion if versions are incompatible.

Therefore, compatibility must be determined before writing tests.

## 2. Identifying a Compatible Elasticsearch Version

### 2.1. Multiple Versions Participate in an Integration Test

A test typically involves at least three versioned components:

1. Spring Boot and Spring Data Elasticsearch.
2. The Elasticsearch Java API Client or transport client used by Spring Data.
3. The Elasticsearch server Docker image.

There are also the Testcontainers library and the JUnit integration module. These components must be compatible with the JDK, Docker runtime, and each other as well.

Do not pick an Elasticsearch image solely by looking at the Spring Boot version. Check the actual dependencies resolved by Maven/Gradle.

### 2.2. Checking the Spring Data Elasticsearch Release Train

Spring Data Elasticsearch publishes compatibility information for each release train. Identify:

- The Spring Boot version in use.
- The Spring Data Elasticsearch version managed by dependency management.
- The Elasticsearch server versions supported by that release train.
- The Elasticsearch Java API Client version used by Spring Data.

If using Spring Boot dependency management, keep Spring Data and the Elasticsearch client at the versions managed by Boot, unless the project has a clear reason to override them.

Do not independently upgrade only the client or only the server to the latest release and assume compatibility.

### 2.3. Inspecting the Dependency Tree

With Maven:

~~~bash
mvn dependency:tree -Dincludes=org.springframework.data:spring-data-elasticsearch,co.elastic.clients:elasticsearch-java,org.elasticsearch.client:*
~~~

With Gradle:

~~~bash
./gradlew dependencyInsight --dependency spring-data-elasticsearch --configuration testRuntimeClasspath
./gradlew dependencyInsight --dependency elasticsearch-java --configuration testRuntimeClasspath
~~~

These commands show the actual resolved versions, even when dependencies are pulled in transitively via the Spring Boot BOM.

If the dependency tree shows multiple clients or an unintended version override, fix dependency management before choosing an image.

### 2.4. Using the Compatibility Matrix of the Exact Release

Image selection process:

1. Read the Spring Data Elasticsearch version in the dependency tree.
2. Open the corresponding compatibility matrix or release documentation.
3. Identify the supported Elasticsearch server range.
4. Pick a specific patch version within that range.
5. Use the same version across local, CI, and related test profiles.
6. Store this version in a single property or constant.

Do not use a compatibility matrix from another release train. Spring Data Elasticsearch changes across major/minor releases, so a version suitable for an older project may not fit a newer one.

### 2.5. Pinning the Image to a Specific Version

Example of a specific image tag:

~~~text
docker.elastic.co/elasticsearch/elasticsearch:8.17.0
~~~

Version 8.17.0 is an illustrative example only. Replace it with a version verified to be compatible with your project's dependencies.

Avoid tags such as:

- latest.
- 8.
- 8.x.
- A tag that does not specify a patch version.
- An uncontrolled environment variable that can silently change versions between runs.

A specific tag makes test results repeatable. For higher reproducibility, you can also pin the image digest after verifying the official image.

### 2.6. Testcontainers Version and Elasticsearch Image Version Are Two Different Things

The version of the Testcontainers dependency is not the Elasticsearch server version.

For example:

- Testcontainers library: version managing the Java API and Docker integration.
- Elasticsearch image: server version pulled by Docker.
- Elasticsearch Java API Client: client version used by Spring Data.

Upgrading Testcontainers does not mean upgrading the Elasticsearch server. Conversely, upgrading the image does not automatically upgrade the client dependency.

Manage these three versions independently while checking compatibility.

## 3. Declaring Testcontainers Dependencies

### 3.1. Maven Dependencies

With Testcontainers Java 1.x, commonly used modules include the Elasticsearch module and JUnit Jupiter integration:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.testcontainers</groupId>
            <artifactId>testcontainers-bom</artifactId>
            <version>1.20.4</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>org.testcontainers</groupId>
        <artifactId>elasticsearch</artifactId>
        <scope>test</scope>
    </dependency>

    <dependency>
        <groupId>org.testcontainers</groupId>
        <artifactId>junit-jupiter</artifactId>
        <scope>test</scope>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Version 1.20.4 here only illustrates how to import the BOM. Your project must choose a Testcontainers version supported by its JDK, JUnit, and dependency policy.

New Testcontainers major releases may change module splits or artifact coordinates. When upgrading major versions, check the dependency guide for that exact version instead of mixing artifacts from two majors.

### 3.2. Gradle Dependencies

Gradle example using a version catalog or BOM:

~~~kotlin
dependencies {
    testImplementation(platform("org.testcontainers:testcontainers-bom:1.20.4"))
    testImplementation("org.testcontainers:elasticsearch")
    testImplementation("org.testcontainers:junit-jupiter")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
}
~~~

The version in the example should be replaced with your chosen Testcontainers version. If the project uses a Gradle version catalog, declare the version in one place to prevent Testcontainers modules from drifting out of sync.

### 3.3. Placing Dependencies in Test Scope

Testcontainers is for testing only. Do not put the Elasticsearch container module on the production application's runtime classpath.

Use Maven `test` scope or Gradle `testImplementation`. If test classes were accidentally placed in the production source set, fix the source layout rather than widening dependency scope.

### 3.4. Do Not Add an Elasticsearch Server Dependency to the Application

The Docker image already provides the Elasticsearch server. The test application only needs Spring Data/the client and the Testcontainers module.

Do not add a Java dependency just to "run an Elasticsearch server" in the same JVM unless the project has a dedicated use case. The Elasticsearch server runs as a separate process inside the container.

## 4. Creating ElasticsearchContainer

### 4.1. Initializing the Container with a Pinned Image

JUnit 5 example:

~~~java
import org.testcontainers.elasticsearch.ElasticsearchContainer;
import org.testcontainers.utility.DockerImageName;

ElasticsearchContainer elasticsearch =
    new ElasticsearchContainer(
        DockerImageName.parse(
            "docker.elastic.co/elasticsearch/elasticsearch:8.17.0"
        )
    );
~~~

The `ElasticsearchContainer` class belongs to Testcontainers' Elasticsearch module. The image name must be an image supported by the module.

Some Testcontainers versions validate image compatibility via `DockerImageName`. Do not use `asCompatibleSubstituteFor` to bypass warnings if the actual image is incompatible; only declare a substitute when you have verified that the replacement image shares the same contract.

### 4.2. Single-Node Configuration for Integration Tests

A test container typically runs a single node:

~~~java
static final ElasticsearchContainer ELASTICSEARCH =
    new ElasticsearchContainer(
        DockerImageName.parse(
            "docker.elastic.co/elasticsearch/elasticsearch:8.17.0"
        )
    )
    .withEnv("discovery.type", "single-node")
    .withEnv("xpack.security.enabled", "false")
    .withEnv("ES_JAVA_OPTS", "-Xms512m -Xmx512m");
~~~

This configuration suits basic functional tests in an isolated environment:

- Single node avoids requiring multi-node cluster discovery.
- Disabling security avoids provisioning credentials for simple CRUD examples.
- Limiting heap prevents the container from consuming too much memory on the test machine.

This is a test configuration, not a production configuration. If the production application requires TLS, API keys, or security enabled, write separate integration tests that verify those exact mechanisms.

### 4.3. Do Not Use a Test Container as a Substitute for a Production Cluster

A single-node container cannot adequately test:

- Replica allocation and failover.
- Multi-node discovery.
- Shard relocation.
- Cluster-wide availability.
- Rolling upgrades.
- Network partitions between nodes.
- Production-scale performance.

Testcontainers provides real Elasticsearch within test scope, but the topology must be expanded if a test aims to verify multi-node cluster behavior.

### 4.4. Setting a Reasonable Startup Timeout

You can increase the startup timeout when the image is large or CI pull speeds are slow:

~~~java
.withStartupTimeout(Duration.ofMinutes(2));
~~~

Do not raise the timeout excessively to mask image or Docker failures. If the container does not become ready, inspect logs, exit code, memory, and health checks.

### 4.5. Wait Strategy and Readiness

Elasticsearch needs time to start the JVM, load plugins, bootstrap, and open its HTTP endpoint. Tests should not begin immediately after Docker creates the container.

The Testcontainers module may already provide a suitable wait strategy. If configuring one manually, use a readiness condition that verifies the Elasticsearch endpoint responds—for example, HTTP GET `/` with the expected status when security is disabled.

Do not merely check that the container is running. The process can be alive before Elasticsearch is ready to accept requests.

## 5. Managing Container Lifecycle with JUnit Jupiter

### 5.1. Container Shared Within a Test Class

Example:

~~~java
import org.junit.jupiter.api.Test;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@Testcontainers
@SpringBootTest
class ProductRepositoryIntegrationTest {

    @Container
    static final ElasticsearchContainer ELASTICSEARCH =
        new ElasticsearchContainer(
            DockerImageName.parse(
                "docker.elastic.co/elasticsearch/elasticsearch:8.17.0"
            )
        )
        .withEnv("discovery.type", "single-node")
        .withEnv("xpack.security.enabled", "false")
        .withEnv("ES_JAVA_OPTS", "-Xms512m -Xmx512m");

}
~~~

A `static` container is shared across test methods within the same class. A non-static instance container is typically created and stopped per test method, making tests slower.

### 5.2. Using a Static Container to Reduce Test Time

Elasticsearch is a relatively heavy process. Starting a container per method is usually unnecessary if tests can isolate data using separate indices or cleanup.

You can use one container per class or per test suite. Choose the scope based on isolation requirements and how the Spring test context is cached.

### 5.3. Notes on Spring TestContext Caching

Spring can cache the `ApplicationContext` across test classes. If a static container belonging to one class stops after that class finishes while Spring retains a context using the same endpoint, the next class may reuse a context pointing to a stopped container.

Ways to handle this:

- Use a singleton container managed across the entire test suite.
- Separate contexts/test classes so a context is not reused after its container stops.
- Use `@DirtiesContext` when you need to force Spring to discard the context.
- Structure the test suite so the container lifecycle outlives the context lifecycle.

Do not sprinkle `@DirtiesContext` on every test indiscriminately, as it can slow down the suite significantly.

### 5.4. Singleton Container Across Multiple Test Classes

One pattern is creating a shared holder class:

~~~java
public final class ElasticsearchTestContainer {

    public static final ElasticsearchContainer INSTANCE =
        new ElasticsearchContainer(
            DockerImageName.parse(
                "docker.elastic.co/elasticsearch/elasticsearch:8.17.0"
            )
        )
        .withEnv("discovery.type", "single-node")
        .withEnv("xpack.security.enabled", "false");

    static {
        INSTANCE.start();
    }

    private ElasticsearchTestContainer() {
    }
}
~~~

Test classes reference the same `INSTANCE`. This pattern requires clear lifecycle management; do not also register the same container on multiple `@Container` fields.

If using a singleton, ensure the container is started only once and cleaned up when the test JVM exits. Testcontainers/Ryuk usually handles cleaning up containers created during the test session, though CI still needs to terminate processes properly.

### 5.5. Option to Skip Tests When Docker Is Unavailable

Testcontainers' JUnit integration provides an option to skip tests when Docker is unavailable in some versions:

~~~java
@Testcontainers(disabledWithoutDocker = true)
~~~

This option is convenient for developer environments without Docker. For CI pipelines where integration tests are mandatory, do not silently skip when a Docker agent is misconfigured. Let the pipeline fail clearly or keep an explicitly marked optional job.

## 6. Connecting Spring Boot to Dynamic Ports

### 6.1. Do Not Hardcode localhost:9200

Testcontainers typically maps the container port to a random host port to avoid colliding with a local Elasticsearch instance or other tests.

Do not assume the server is always at `localhost:9200`. Retrieve the host and mapped port from the container:

~~~java
String address = ELASTICSEARCH.getHttpHostAddress();
~~~

The returned value usually has the form `host:mappedPort`. Use this address to configure Spring.

### 6.2. Using DynamicPropertySource

For Spring Boot versions using the `spring.elasticsearch.uris` property, you can register the endpoint dynamically:

~~~java
@DynamicPropertySource
static void elasticsearchProperties(DynamicPropertyRegistry registry) {
    registry.add(
        "spring.elasticsearch.uris",
        ELASTICSEARCH::getHttpHostAddress
    );
}
~~~

Property names differ across Spring Boot generations. Some older versions use properties prefixed with `spring.elasticsearch.rest`. Check the configuration metadata and property reference for the Boot version in use.

If the project configures `ClientConfiguration` or an Elasticsearch client bean manually, pass the host/port from the container into the test configuration bean instead of assuming auto-configuration will read that property.

### 6.3. Using ServiceConnection When Spring Boot Supports It

Some Spring Boot versions provide `@ServiceConnection` to automatically create connection details from a Testcontainers container:

~~~java
@Container
@ServiceConnection
static final ElasticsearchContainer ELASTICSEARCH =
    new ElasticsearchContainer(
        DockerImageName.parse(
            "docker.elastic.co/elasticsearch/elasticsearch:8.17.0"
        )
    );
~~~

Only use this approach when your Spring Boot version and container type have a matching service connection factory. If not supported, use `@DynamicPropertySource` or a custom test configuration.

Do not combine both approaches arbitrarily if they supply conflicting connection details. Choose one clear configuration source.

### 6.4. Avoid Creating a Second Client in Tests

A common mistake is having the Spring Data repository use an auto-configured client while the test manually creates another Elasticsearch client for assertions. The test may then write to one container while the repository connects to a different endpoint.

Use the same Spring-managed client/template for the test operations you are verifying. If you have custom configuration, confirm that the repository and `ElasticsearchOperations` are injected with the intended beans.

## 7. Integration Test Example with Spring Data Elasticsearch

### 7.1. Entity and Repository

Simple entity example:

~~~java
@Document(indexName = "products-it")
public class ProductDocument {

    @Id
    private String id;

    @Field(type = FieldType.Keyword)
    private String sku;

    @Field(type = FieldType.Text)
    private String name;

    // Constructors, getters and setters.
}
~~~

Repository:

~~~java
public interface ProductRepository
        extends ElasticsearchRepository<ProductDocument, String> {
}
~~~

Index names in tests should be separated from developer indices or other environments. Never point tests at a production index.

### 7.2. Test Class Configuration

~~~java
@Testcontainers
@SpringBootTest
class ProductRepositoryIntegrationTest {

    @Container
    static final ElasticsearchContainer ELASTICSEARCH =
        new ElasticsearchContainer(
            DockerImageName.parse(
                "docker.elastic.co/elasticsearch/elasticsearch:8.17.0"
            )
        )
        .withEnv("discovery.type", "single-node")
        .withEnv("xpack.security.enabled", "false")
        .withEnv("ES_JAVA_OPTS", "-Xms512m -Xmx512m");

    @DynamicPropertySource
    static void elasticsearchProperties(
            DynamicPropertyRegistry registry) {
        registry.add(
            "spring.elasticsearch.uris",
            ELASTICSEARCH::getHttpHostAddress
        );
    }

    @Autowired
    ProductRepository repository;

    @Test
    void savesAndReadsProduct() {
        ProductDocument product = new ProductDocument();
        product.setId("p-100");
        product.setSku("SKU-100");
        product.setName("Wireless Keyboard");

        repository.save(product);

        Optional<ProductDocument> loaded =
            repository.findById("p-100");

        assertThat(loaded).isPresent();
        assertThat(loaded.get().getSku()).isEqualTo("SKU-100");
        assertThat(loaded.get().getName())
            .isEqualTo("Wireless Keyboard");
    }
}
~~~

This is a structural example. Imports, constructors, getters/setters, and properties must match your project's Spring Boot/Spring Data version.

### 7.3. Preparing the Index and Mapping

You can let Spring Data create the index automatically from entity configuration, or create it explicitly in the test:

~~~java
@Autowired
ElasticsearchOperations operations;

@BeforeEach
void prepareIndex() {
    IndexOperations indexOperations =
        operations.indexOps(ProductDocument.class);

    if (!indexOperations.exists()) {
        indexOperations.createWithMapping();
    }
}
~~~

If a test needs to verify automatic mapping creation, do not pre-create the mapping using the same API, as doing so stops testing auto-creation behavior.

Split tests into two clear groups:

- Mapping/provisioning tests: create the index via the application mechanism under test.
- Repository CRUD tests: prepare the index before running operations.

### 7.4. Cleaning Up Data Between Tests

Use a dedicated test index and delete documents after each test:

~~~java
@AfterEach
void cleanDocuments() {
    repository.deleteAll();
}
~~~

If a test changes mappings or index settings, deleting and recreating the index may be necessary. Do not share an index across tests running in parallel if data can overwrite each other.

### 7.5. Waiting for Refresh When Testing Search

An Elasticsearch refresh does not necessarily occur immediately after every write. If a test saves and searches immediately, results may not see the document yet even though the write succeeded.

You can:

- Use an appropriate refresh policy for tests.
- Call refresh via `IndexOperations` after writes.
- Use a test API with a refresh option if supported by your version.

Example:

~~~java
operations.indexOps(ProductDocument.class).refresh();
~~~

Only add refreshes in tests that need to verify search visibility. Do not refresh after every write by default in production because frequent refreshes carry overhead.

## 8. Verifying Real Mappings and Queries

### 8.1. Testing the Mapping After Index Creation

You can read the mapping back from Elasticsearch to verify field types:

~~~java
IndexOperations indexOperations =
    operations.indexOps(ProductDocument.class);

Map<String, Object> mapping =
    indexOperations.getMapping();

assertThat(mapping).isNotEmpty();
~~~

Depending on the API version, the mapping data type or access method may differ. What matters is that the test reads the mapping from a real server rather than only asserting annotations on the entity.

### 8.2. Testing Important Field Types

For entities with keyword, text, date, nested, or dense vector fields, verify the actual mapping. Bugs often appear only when querying or indexing data with complex types.

Nested test example:

- Verify the array field is mapped as `nested`.
- Index two child objects with different values.
- Run a nested query requiring conditions to match the same object.
- Verify there are no false positives.

### 8.3. Testing Query DSL Against a Real Server

Mocking a query builder only confirms the application constructs the query object as expected. Integration tests need to send the query to Elasticsearch to verify parsing and execution.

Tests should cover critical queries:

- Bool queries and filters.
- Nested queries.
- Sorting and pagination.
- Aggregations.
- Highlighting.
- Date ranges and timezones.
- Runtime fields or scripts if used by the application.

### 8.4. Testing Behavior Rather Than Over-Depending on Internal Responses

Assert key outcomes such as which documents are returned, which fields are mapped, and sort order. Avoid locking tests to internal metadata that might change between patch versions if it is not part of the application's contract.

## 9. Testing Security When Production Uses Authentication

### 9.1. A Security-Disabled Container Only Tests Data Functionality

Setting `xpack.security.enabled=false` makes CRUD tests easy to set up. However, it does not test:

- API key headers.
- Basic authentication.
- TLS certificate validation.
- Role/index privileges.
- 401 and 403 responses.
- Credential rotation or revocation.

If production enables security, maintain a separate test profile with security enabled to verify client configuration.

### 9.2. Do Not Conclude API Keys Work from a Security-Disabled Test

A CRUD test passing in a security-disabled container only proves the client connects and manipulates data. It does not prove the API key header is sent properly or that the role has the right privileges.

Separate the goals:

| Test profile | Security | Purpose |
|---|---|---|
| Fast integration | Can be disabled | Mapping, repository, query, and CRUD |
| Security integration | Enabled | TLS, credentials, API keys, roles, and 401/403 |
| Production smoke test | Matches production config | Verify connection settings after deployment |

### 9.3. Testing Least-Privilege Permissions

In a security-enabled test:

1. Create the index and role using a separate provisioning principal.
2. Create an API key with only the required permissions.
3. Initialize the Spring Data client using that key.
4. Attempt permitted operations.
5. Attempt out-of-scope operations and verify they are denied.
6. Revoke the key and verify the credential can no longer be used.

Do not put secrets in source code or logs. Use secrets generated during the test and destroy them when the test ends.

### 9.4. TLS and Certificates

If production uses HTTPS, add a test verifying trust chain and hostname validation. Using a trust-all configuration just to make tests pass hides certificate configuration bugs.

You can use a dedicated test certificate or controlled TLS fixture. Never use production private keys in repository tests.

## 10. Reactive Integration Tests

### 10.1. Using Reactive Template/Repository

For reactive applications, connect the same Testcontainers endpoint to `ReactiveElasticsearchOperations` or a reactive repository.

Example test using `StepVerifier`:

~~~java
@Test
void savesProductReactively() {
    ProductDocument product = new ProductDocument();
    product.setId("p-reactive-1");
    product.setSku("SKU-R1");
    product.setName("USB Hub");

    StepVerifier.create(repository.save(product))
        .assertNext(saved ->
            assertThat(saved.getId()).isEqualTo("p-reactive-1")
        )
        .verifyComplete();

    StepVerifier.create(repository.findById("p-reactive-1"))
        .assertNext(found ->
            assertThat(found.getName()).isEqualTo("USB Hub")
        )
        .verifyComplete();
}
~~~

Tests should use the project's actual reactive repository type and reactive dependencies. Do not call `block()` in production reactive code just to make tests easier to write; `StepVerifier` controls subscription and signals.

### 10.2. Cleaning Up Reactive Data

Cleanup can be composed within the test lifecycle or via a test fixture:

~~~java
@AfterEach
void cleanDocuments() {
    repository.deleteAll().block();
}
~~~

`block()` on the test thread can be acceptable to wait for cleanup to complete before the next test, but do not copy this pattern into a production application's event loop.

If the test framework supports asynchronous lifecycles, you can return a `Publisher` from setup/cleanup using an appropriate extension.

### 10.3. Verifying Cancellation and Timeouts Against a Real Server

Mocking a `Publisher` is useful for testing operators. However, if you need to verify cancellation at the transport layer, execute a real request against the container and observe the behavior.

Do not assume subscriber cancellation rolls back a write already received by Elasticsearch. For write tests, verify document state after cancellation or timeout if semantics matter.

## 11. Organizing Test Suites and Performance

### 11.1. Splitting Tests by Cost

You can organize tests into:

- Unit tests: run frequently, no Docker.
- Fast integration tests: one Elasticsearch container shared across a group of tests.
- Security integration tests: container with security/TLS.
- Compatibility tests: run against supported server versions.
- End-to-end tests: run in a larger integration environment.

There is no need to run a multi-version matrix on every commit if cost is high. Run one primary version on every pull request and run the compatibility matrix in a scheduled or release pipeline.

### 11.2. Sharing One Container Across Multiple Tests When Possible

Starting Elasticsearch consumes time and memory. Using one container per test class/suite saves time.

To maintain isolation:

- Use separate index names per test group.
- Delete data between tests.
- Do not share document IDs.
- Control test parallelism.
- Do not mutate cluster-wide settings in tests running in parallel.

### 11.3. Running Tests in Parallel Carefully

If multiple test classes share a cluster:

- Do not let two tests delete the same index.
- Avoid colliding fixed index names.
- Use unique prefixes or suffixes per test class/run.
- Be careful with cluster-wide aliases and templates.
- Cap concurrent test count based on memory and CPU.

A test that passes in isolation can fail in a parallel suite due to index race conditions.

### 11.4. Container Reuse

Testcontainers supports container reuse for local development in some versions. This is an optional optimization and should not be required for CI to run correctly.

A reusable container may retain data and settings across runs. Tests must still handle cleanup and not rely on stale state.

Do not enable reuse just to mask a test suite that spawns too many containers. Fix the lifecycle and share containers properly first.

## 12. Running Testcontainers in CI

### 12.1. CI Runners Need a Docker Runtime

Testcontainers needs access to a Docker daemon or a supported container runtime environment. The CI runner must have permissions to create containers, networks, volumes, and pull images.

If tests run inside nested containers, configure the Docker socket or DinD according to the CI platform. Do not assume every hosted runner has Docker access by default.

### 12.2. Caching Images to Reduce Time

Elasticsearch images are large. CI can cache Docker layers or use a runner image with the exact version pre-pulled.

Caching must rely on a pinned image tag/digest. Do not cache a floating tag and assume the image stays identical.

### 12.3. Memory Limits

Elasticsearch requires memory for the JVM and native processes. The test container should have a heap suited to the runner:

~~~java
.withEnv("ES_JAVA_OPTS", "-Xms512m -Xmx512m")
~~~

This value is an example for small tests. If the suite uses heavy analyzers/plugins or large datasets, higher heap may be needed. Also account for memory used by the Docker daemon, test JVM process, and other containers.

### 12.4. Handling Architecture

If developers run ARM64 while CI runs AMD64, verify the image provides manifests for both architectures.

Do not force a different platform arbitrarily, as running via emulation can slow tests down or cause native library failures. Specify the architecture explicitly if the project targets a fixed platform.

### 12.5. When Docker Is Unavailable

If tests are mandatory, CI should fail with a message stating the Docker daemon is unreachable. If tests are optional in developer environments, they can be skipped intentionally.

Do not turn every container startup error into an assumption that Docker is missing. Distinguish between Docker unavailable, image pull failure, container exit, and Elasticsearch readiness timeout.

## 13. Compatibility Testing Matrix

### 13.1. One Fixed Server Version per Main Build

In pull requests, typically pick one server version already verified as compatible for fast, stable testing.

Keep this version in one shared property—for example, in a test configuration or build property. Do not duplicate version strings across multiple classes where they can easily drift.

### 13.2. Multi-Version Matrix

If the application supports multiple server versions, you can run a matrix:

| Job | Spring Data/client | Elasticsearch image | Goal |
|---|---|---|---|
| Main integration | BOM-managed version | Primary server version | Gate for each pull request |
| Minimum supported | Same application dependencies | Lowest still-supported server | Verify minimum compatibility |
| Latest supported | Same application dependencies | Latest server supported by the release train | Catch issues before upgrading the server |
| Upgrade rehearsal | Candidate dependencies | Target upgrade server | Test intentional upgrades |

Do not test every patch version unless necessary. Pick meaningful milestones according to the project's compatibility policy.

### 13.3. Controlled Client and Server Upgrades

When upgrading Spring Boot/Spring Data:

1. Check release notes and the compatibility matrix.
2. Update dependency management.
3. Inspect the dependency tree for the new client version.
4. Pick a supported Elasticsearch image.
5. Run integration tests.
6. Check deprecations and API behavior.
7. Only then update versions in CI/releases.

Do not upgrade the server image independently and use test failures as the sole way to discover compatibility.

### 13.4. Do Not Let Test Versions Differ from Production Without Reason

If production runs Elasticsearch 8.x while integration tests run another major version, tests can miss differences in mapping, security, and API behavior.

Test versions should reflect the target production server or a version within the defined compatibility range.

## 14. Collecting Logs and Diagnosing Startup Failures

### 14.1. Inspecting Container Logs

When a container fails to become ready, check logs for:

- JVM bootstrap failures.
- Memory lock or heap issues.
- Bootstrap checks.
- Permission or file-system issues.
- Plugin load failures.
- Security auto-configuration.
- Cluster formation failures.

Do not merely increase the startup timeout if Elasticsearch has already exited due to misconfiguration.

### 14.2. Checking the Container Exit Code

If the container stops immediately after starting, inspect the exit code and logs. Common causes include insufficient Docker memory, failed bootstrap checks, or invalid env settings.

### 14.3. Verifying the Endpoint and Port

Print the host/mapped port in test logs if needed, but never log credentials. Check:

- The host returned by Testcontainers.
- The port mapping of the HTTP endpoint.
- That the HTTP scheme matches the security/TLS mode.
- That the client uses the right endpoint.
- That no other configuration overrides `DynamicPropertySource`.

### 14.4. Checking the Actual Server Version

You can call the root endpoint and read the version:

~~~http
GET /
~~~

The Elasticsearch response contains version information. Tests can assert that the server version matches the version pinned in the build.

This is useful when image tags or configuration variables might be overridden in CI.

## 15. Common Errors

| Symptom | Possible cause | Resolution |
|---|---|---|
| Container runs but client cannot connect | Hardcoded port 9200 instead of mapped port | Read endpoint from container |
| Flaky tests on startup | Tests start before Elasticsearch is ready | Use wait strategy and sensible startup timeout |
| Incompatible method/API errors | Spring Data, Java client, and server version mismatch | Check compatibility matrix and dependency tree |
| Mapping rejected | Unsupported server version or mapping type | Check mapping DSL and server version |
| Passes locally, fails in CI | Docker daemon, memory, architecture, or image pull | Inspect CI runtime, logs, and resource limits |
| Next test class cannot connect | Container stopped while Spring context cache kept endpoint | Use singleton container or align context lifecycle |
| Parallel tests fail | Multiple tests share an index or delete each other's data | Separate indices and control parallelism |
| Search right after save misses document | Index not refreshed yet | Refresh in test or use appropriate refresh policy |
| 401 when production uses API key | Test container disabled security or wrong header | Add dedicated security integration tests |
| 403 despite valid authentication | Role lacks index privileges | Check roles and actual API operations |
| Image tag changed unexpectedly | Using `latest` or tag without pinned patch | Pin exact version or digest |
| Container exits immediately | Low heap, bootstrap check, or invalid env | Read logs and adjust resources/config |
| Test suite too slow | Each method starts a new container | Share container per class/suite |
| Stale test data left behind | Missing cleanup or container reuse | Delete indices/documents and isolate test state |
| Tests skipped on CI | Using `disabledWithoutDocker` in mandatory job | Configure Docker runner and fail job clearly |

## 16. Setup Workflow from Scratch

When adding Testcontainers to a Spring Data Elasticsearch project:

1. Check Spring Boot and Spring Data Elasticsearch versions in the build.
2. Check the actual Elasticsearch Java API Client version.
3. Consult the compatibility matrix for the exact release train.
4. Pick an Elasticsearch image with a specific patch tag.
5. Add Elasticsearch and JUnit Testcontainers modules in test scope.
6. Create `ElasticsearchContainer` with single-node settings for basic tests.
7. Configure an appropriate readiness wait and startup timeout.
8. Inject host/mapped port into Spring using `DynamicPropertySource` or supported `ServiceConnection`.
9. Use the same Spring-managed client/template/repository in tests.
10. Create test indices and mappings according to what needs verification.
11. Write CRUD, mapping, and query tests against the real server.
12. Isolate indices and clean up between tests.
13. Add security-enabled tests if production uses authentication/TLS.
14. Run tests in CI with Docker access and sufficient memory.
15. Use matrix testing for server versions within the compatibility range.
16. When upgrading dependencies or server, update the pinned version and rerun the integration suite.

## 17. Key Takeaways

- Testcontainers runs a real Elasticsearch server in Docker to verify Spring Data integration.
- The Testcontainers version, Elasticsearch Java API Client version, and Elasticsearch server image version are separate versions.
- Choose the server image using the compatibility matrix for the exact Spring Data Elasticsearch release train.
- Pin a specific patch tag or digest; avoid `latest` and floating tags.
- Use official Elasticsearch images and verify `DockerImageName` compatibility.
- Configure single-node, heap, and security according to the test's goal.
- Wait for Elasticsearch readiness; a running container does not guarantee the HTTP endpoint is ready.
- Read host and mapped port from the container; never hardcode `localhost:9200`.
- Use `DynamicPropertySource` or `ServiceConnection` if supported by the Spring Boot version.
- Watch out for Spring TestContext caching when a container stops before the context is reused.
- Verify mappings and queries against a real server rather than only asserting entity annotations.
- Searches after writes may require a refresh in tests.
- A security-disabled container does not test API keys, TLS, or role privileges.
- Share containers sensibly and use dedicated indices and cleanup to keep the suite fast yet isolated.
- CI must have Docker runtime, memory, and compatible image architecture.
- When upgrading versions, inspect the dependency tree, compatibility matrix, and run integration tests before changing the production target.

Testcontainers makes Spring Data Elasticsearch integration tests closer to the real environment and repeatable across developer machines and CI. When you pin the server image properly to your project's dependencies, configure endpoints dynamically, and manage container lifecycles explicitly, tests detect mapping, query, client compatibility, and security bugs early before deployment.

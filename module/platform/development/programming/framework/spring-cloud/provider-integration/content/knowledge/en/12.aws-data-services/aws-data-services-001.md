# Integrating DynamoDB with the Starter and DynamoDbTemplate When Supported by Your Version

## 1. Context and Objectives

In a Spring Boot application, data can be stored on an AWS managed service instead of operating a dedicated database cluster. **Amazon DynamoDB** is a key–value/document NoSQL database managed by AWS, suitable for access flows with deterministic keys, low-latency requirements, and variable traffic. This lesson belongs to the **AWS Data Services** chapter and focuses on integrating Spring Boot with DynamoDB via **Spring Cloud AWS (AWSpring)**.

After this lesson, you will be able to:

- Choose the right library and identify when a Spring Cloud AWS version provides `DynamoDbTemplate`.
- Configure region, IAM identity, access permissions, and endpoint for an AWS environment or DynamoDB Local.
- Design a table using partition key/sort key, map a Java bean, and perform CRUD and `Query` operations with `DynamoDbTemplate`.
- Fall back to `DynamoDbEnhancedClient` from AWS SDK for Java v2 if the starter/template is not suitable.
- Write integration tests, troubleshoot common errors, and make operational decisions regarding security, cost, consistency, and performance.

**Running example:** a reservation management application storing `ReservationRecord` keyed by `tenantId` (tenant unit) and `reservationId` (reservation ID). The primary queries are fetching a single reservation or listing reservations for a tenant.

> Scope: DynamoDB is an AWS service; `DynamoDbTemplate` in this lesson is an abstraction from the `io.awspring.cloud` library, **not** `MongoTemplate`, `JdbcTemplate`, or Spring Data JPA. The starter provides auto-configuration and data operations; it does not automatically generate repositories from `JpaRepository`-style interfaces.

## 2. Choosing the Right Integration Mechanism and Version

There are three related API layers:

~~~mermaid
flowchart TD
    A["Spring MVC / Service"] --> B["ReservationRepository"]
    B --> C["DynamoDbTemplate / DynamoDbOperations<br/>(AWSpring, if supported by your version)"]
    C --> D["DynamoDbEnhancedClient<br/>(AWS SDK v2)"]
    D --> E["DynamoDbClient<br/>(AWS SDK v2)"]
    E --> F[("Amazon DynamoDB")]
    B -. "Alternative" .-> D
~~~

| Mechanism | When to use | Primary responsibilities |
| --- | --- | --- |
| `spring-cloud-aws-starter-dynamodb` + `DynamoDbTemplate` | The project uses a compatible AWSpring version and needs standard CRUD and queries | Spring auto-configures the client, template, and table name/schema resolver beans |
| `DynamoDbEnhancedClient` | You need control over conditional writes, the table API, or your project version lacks the template | Create `DynamoDbTable<T>`, map the schema, and call the Enhanced Client API |
| `DynamoDbClient` | You need low-level APIs such as table creation, batch/transactional operations, or features not exposed in higher abstractions | Build requests and handle responses directly |

**Check version support before writing code:**

1. Inspect the *dependency tree* to identify the actual `io.awspring.cloud` and Spring Boot versions in use. Choose an AWSpring BOM compatible with your project's Spring Boot version; do not arbitrarily mix different major lines.
2. In the API documentation for that exact version, verify the presence of `io.awspring.cloud.dynamodb.DynamoDbTemplate`, `DynamoDbOperations`, and the `spring-cloud-aws-starter-dynamodb` starter. For example, Spring Cloud AWS **3.4.0/3.4.2** documentation fully covers these components.
3. Verify that the template bean is auto-configured; a similarly named dependency from the legacy `org.springframework.cloud:spring-cloud-starter-aws` library cannot replace `io.awspring.cloud`.
4. If the template is missing or the API differs, use AWS SDK v2's Enhanced Client (Section 8); do not assume a method exists.

**Version note:** the Java code using the template below references the AWSpring 3.4.x API line. For the 4.x line or other lines, consult the documentation for the version pinned in your BOM. When using newer APIs such as conditional operations, always verify exact method signatures.

## 3. Designing the DynamoDB Table Around Queries

DynamoDB organizes data by **primary key**. For a table with a composite primary key:

- **Partition key** `tenantId` (String type): groups data per tenant.
- **Sort key** `reservationId` (String type): distinguishes reservations within a tenant.
- **Non-key attributes** `propertyId`, `state`, `createdAt`: do not need to be declared in `create-table` if they are not part of any key or index.

| Access requirement | How to satisfy | Notes |
| --- | --- | --- |
| Get an exact reservation | `GetItem` with both `tenantId` and `reservationId` | Knowing only `reservationId` is insufficient to look up by the current primary key |
| List reservations for a tenant | `Query` on partition key `tenantId` | Supports pagination and additional conditions on the sort key |
| Find all reservations by `propertyId` | Design an appropriate Global Secondary Index | Do not use a full-table `Scan` as the default solution |
| Filter by `state` | Choose a matching key/index if this is a frequent query flow | A `FilterExpression` still reads items before filtering and does not replace an index |

Partition key selection also affects load distribution: avoid funneling all writes into a single hot key value. Because the sort key is a **string**, sorting follows lexicographical string order; if you want chronological ordering, consider a composite sort key like `createdAt#reservationId` with a standardized UTC timestamp and unique ID guarantee. In the minimal example below, `reservationId` is used for simplicity.

## 4. Adding Dependencies to Spring Boot

### Maven

Assume the project runs a Spring Boot 3.x line compatible with AWSpring 3.4.2. Check the compatibility matrix before pinning versions:

~~~xml
<properties>
    <!-- Choose a version compatible with your project's Spring Boot version -->
    <spring-cloud-aws.version>3.4.2</spring-cloud-aws.version>
</properties>

<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>io.awspring.cloud</groupId>
            <artifactId>spring-cloud-aws-dependencies</artifactId>
            <version>${spring-cloud-aws.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>io.awspring.cloud</groupId>
        <artifactId>spring-cloud-aws-starter-dynamodb</artifactId>
    </dependency>
</dependencies>
~~~

In this example, the BOM reads its version from the Maven property `spring-cloud-aws.version` so you only have to update one place when upgrading. Your application's Spring Boot parent/BOM still needs to be configured as usual.

### Gradle (Groovy DSL)

~~~groovy
dependencies {
    implementation platform('io.awspring.cloud:spring-cloud-aws-dependencies:3.4.2')
    implementation 'io.awspring.cloud:spring-cloud-aws-starter-dynamodb'
}
~~~

Do not declare separate versions for individual starters when the BOM already manages them. If `NoClassDefFoundError` or `NoSuchMethodError` occurs after adding dependencies, check which AWS SDK v2 versions were pulled in or overridden. Do not mix AWS SDK v1 and v2 in ways that produce incompatible clients or configurations.

## 5. AWS Identity, Region, and Endpoint

### 5.1. Production: Using an IAM Role

In AWS, grant permissions to an **IAM role attached to the workload** (for example, an ECS task role, EC2 instance profile, or EKS workload identity mechanism). The AWS SDK and Spring Cloud AWS can resolve credentials from the provider chain; avoid placing static access keys or secret keys in `application.yml`, source code, or Git.

~~~yaml
# application.yml (AWS environment)
spring:
  cloud:
    aws:
      region:
        static: ap-southeast-1
      dynamodb:
        enabled: true
~~~

`spring.cloud.aws.region.static` is the default region used by auto-configured clients. If only DynamoDB needs a separate region, check the `spring.cloud.aws.dynamodb.region` property for your exact version.

An illustrative IAM policy for an application that only reads/writes the primary table:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "dynamodb:GetItem",
        "dynamodb:PutItem",
        "dynamodb:UpdateItem",
        "dynamodb:DeleteItem",
        "dynamodb:Query"
      ],
      "Resource": "arn:aws:dynamodb:ap-southeast-1:123456789012:table/reservation_record"
    }
  ]
}
~~~

Replace the region, account ID, and table name with your real resources; this is only a sample policy. If you run `Query` on a GSI, add the exact index ARN (for example `...:table/reservation_record/index/index_name`) with the required actions. Only grant `Scan`, `BatchWriteItem`, `TransactWriteItems`, or `DescribeTable` when the business logic genuinely requires them.

### 5.2. Local: DynamoDB Local

You can use a container to practice without creating data in an AWS account:

~~~bash
docker run --rm --name dynamodb-local -p 8000:8000 amazon/dynamodb-local:latest
~~~

Create a local-specific configuration:

~~~yaml
# application-local.yml
spring:
  cloud:
    aws:
      region:
        static: ap-southeast-1
      dynamodb:
        endpoint: http://localhost:8000
~~~

Start Spring Boot with the `local` profile. DynamoDB Local typically uses dummy credentials to sign requests; only set dummy credentials in the **local environment**, never store them in production configuration.

~~~bash
# Bash / shell for local development
export AWS_ACCESS_KEY_ID=local
export AWS_SECRET_ACCESS_KEY=local
~~~

On PowerShell, you can use `$env:AWS_ACCESS_KEY_ID="local"` and `$env:AWS_SECRET_ACCESS_KEY="local"` in the testing terminal session. The AWS CLI also requires syntactically valid credentials and a region even when the endpoint is localhost.

## 6. Creating a Table Matching the Entity

Create the `reservation_record` table with the two attributes participating in the key:

~~~bash
aws dynamodb create-table --endpoint-url http://localhost:8000 --region ap-southeast-1 --table-name reservation_record --attribute-definitions AttributeName=tenantId,AttributeType=S AttributeName=reservationId,AttributeType=S --key-schema AttributeName=tenantId,KeyType=HASH AttributeName=reservationId,KeyType=RANGE --billing-mode PAY_PER_REQUEST
~~~

Verify that the table exists:

~~~bash
aws dynamodb describe-table --endpoint-url http://localhost:8000 --region ap-southeast-1 --table-name reservation_record
~~~

In real AWS environments, create tables via IaC such as CloudFormation, CDK, or Terraform and use the default AWS endpoint. **The starter does not auto-create tables from entities** the way Hibernate can with relational databases.

### 6.1. Defining the Mapped Entity

~~~java
import software.amazon.awssdk.enhanced.dynamodb.mapper.annotations.DynamoDbBean;
import software.amazon.awssdk.enhanced.dynamodb.mapper.annotations.DynamoDbPartitionKey;
import software.amazon.awssdk.enhanced.dynamodb.mapper.annotations.DynamoDbSortKey;

@DynamoDbBean
public class ReservationRecord {
    private String tenantId;
    private String reservationId;
    private String propertyId;
    private String state;
    private String createdAt;  // ISO-8601 UTC, e.g. 2026-11-24T08:00:00Z

    public ReservationRecord() {
    }

    @DynamoDbPartitionKey
    public String getTenantId() {
        return tenantId;
    }

    public void setTenantId(String tenantId) {
        this.tenantId = tenantId;
    }

    @DynamoDbSortKey
    public String getReservationId() {
        return reservationId;
    }

    public void setReservationId(String reservationId) {
        this.reservationId = reservationId;
    }

    public String getPropertyId() {
        return propertyId;
    }

    public void setPropertyId(String propertyId) {
        this.propertyId = propertyId;
    }

    public String getState() {
        return state;
    }

    public void setState(String state) {
        this.state = state;
    }

    public String getCreatedAt() {
        return createdAt;
    }

    public void setCreatedAt(String createdAt) {
        this.createdAt = createdAt;
    }
}
~~~

Key points to remember:

- `@DynamoDbBean` belongs to the **AWS SDK Enhanced Client**, not JPA. The bean needs a no-arg constructor and public getters/setters for the mapper to work.
- Annotate the **getters** with `@DynamoDbPartitionKey` / `@DynamoDbSortKey`. Attribute types and names must match the actual table schema (`tenantId`, `reservationId`).
- `DynamoDbTemplate` resolves the table name via `DynamoDbTableNameResolver`. By default, the class name `ReservationRecord` is converted to `reservation_record`. You can configure `spring.cloud.aws.dynamodb.table-prefix`, `table-suffix`, or provide a custom resolver; when doing so, the table name created via CLI/IaC must match accordingly.
- Data missing a key or having a key type different from the table definition will fail on read/write. DynamoDB is schema-flexible for non-key attributes, but **primary keys and indexes still enforce a strict schema**.

## 7. CRUD and Query with DynamoDbTemplate

In library versions that provide a `DynamoDbTemplate` bean, Spring auto-configures the template based on `DynamoDbEnhancedClient`, `DynamoDbTableNameResolver`, and `DynamoDbTableSchemaResolver`. You can inject the template directly into an application-written repository:

~~~java
import io.awspring.cloud.dynamodb.DynamoDbTemplate;
import java.util.List;
import java.util.Optional;
import java.util.stream.StreamSupport;
import org.springframework.stereotype.Repository;
import software.amazon.awssdk.enhanced.dynamodb.Key;
import software.amazon.awssdk.enhanced.dynamodb.model.QueryConditional;
import software.amazon.awssdk.enhanced.dynamodb.model.QueryEnhancedRequest;

@Repository
public class ReservationRepository {
    private final DynamoDbTemplate template;

    public ReservationRepository(DynamoDbTemplate template) {
        this.template = template;
    }

    public ReservationRecord save(ReservationRecord item) {
        return template.save(item);
    }

    public Optional<ReservationRecord> findById(
            String tenantId, String reservationId) {
        Key key = Key.builder()
                .partitionValue(tenantId)
                .sortValue(reservationId)
                .build();

        return Optional.ofNullable(
                template.load(key, ReservationRecord.class));
    }

    public List<ReservationRecord> first25ForTenant(String tenantId) {
        QueryEnhancedRequest request = QueryEnhancedRequest.builder()
                .queryConditional(QueryConditional.keyEqualTo(
                        Key.builder().partitionValue(tenantId).build()))
                .limit(25)
                .build();

        return StreamSupport.stream(
                        template.query(request, ReservationRecord.class)
                                .items()
                                .spliterator(),
                        false)
                .limit(25)
                .toList();
    }

    public void deleteById(String tenantId, String reservationId) {
        Key key = Key.builder()
                .partitionValue(tenantId)
                .sortValue(reservationId)
                .build();

        template.delete(key, ReservationRecord.class);
    }
}
~~~

Invoking it from the service layer:

~~~java
ReservationRecord booking = new ReservationRecord();
booking.setTenantId("tenant-a");
booking.setReservationId("res-1001");
booking.setPropertyId("house-99");
booking.setState("PENDING");
booking.setCreatedAt("2026-11-24T08:00:00Z");

repository.save(booking);

ReservationRecord loaded = repository
        .findById("tenant-a", "res-1001")
        .orElseThrow();

List<ReservationRecord> recent = repository.first25ForTenant("tenant-a");

repository.deleteById("tenant-a", "res-1001");
~~~

**Accurate interpretation of operations:**

- `save(item)` writes data; **do not assume it is insert-only**. Writing with an existing key may replace/update the item depending on the operation semantics. To prevent duplicates or accidental overwrites, use a **conditional write**.
- `load(key, clazz)` returns `null` when the item does not exist; wrapping with `Optional.ofNullable` helps the service distinguish "not found".
- `Query` requires a condition on the partition key. `first25ForTenant` caps the items for demonstration; `limit(25)` on the request controls how many items DynamoDB evaluates per request call, not the total maximum across all pages of the query itself. The outer Java stream limit is what enforces the returned item count in this example.
- By default, DynamoDB may return **eventually consistent reads**. When business logic must read newly written data immediately, check the API for `consistentRead(true)` support (only applicable where DynamoDB allows it; strong consistency is not supported on GSIs).
- Result pages may still contain more data; in production applications, return a controlled `nextToken` / cursor, bound payload sizes, and avoid silently iterating through the entire dataset.

### 7.1. Query vs. Scan

`Query` retrieves items using a pre-designed key/index. `Scan` traverses data broadly and often consumes significant read capacity, especially on large tables. `ScanEnhancedRequest` and `template.scan(...)` are useful for administrative tasks or small datasets, but they do not replace an appropriate access pattern or secondary index.

If you need to filter by `state = "CONFIRMED"` at scale, design an index that mirrors the query—such as `tenantId + state#createdAt` or another GSI depending on requirements and load distribution. DynamoDB does not natively support arbitrary ad-hoc filtering across any column like SQL; key and index design should start from your **business access patterns**.

### 7.2. When Do You Need the Enhanced Client for Advanced Operations?

To create an item only if the key does not already exist, you can use `DynamoDbEnhancedClient` and `PutItemEnhancedRequest` with a condition expression `attribute_not_exists(tenantId)`. When two requests write concurrently, DynamoDB evaluates the condition atomically on the item; the request that fails the condition receives `ConditionalCheckFailedException`. You can also use `@DynamoDbVersionAttribute` on an appropriate entity to enable optimistic locking through the Enhanced Client. Check the specific API version because conditional operation support on the template varies across releases.

When multiple items must change atomically, look into DynamoDB transactional APIs along with their limits and costs; calling `template.save(...)` for each item **does not create a multi-item transaction**.

## 8. Fallback When DynamoDbTemplate Is Unavailable: AWS SDK v2 Enhanced Client

If your current library version does not provide `DynamoDbTemplate`, you can still use the entity model shown above. Once a `DynamoDbEnhancedClient` bean is available, write the repository as follows:

~~~java
import java.util.Optional;
import org.springframework.stereotype.Repository;
import software.amazon.awssdk.enhanced.dynamodb.DynamoDbEnhancedClient;
import software.amazon.awssdk.enhanced.dynamodb.DynamoDbTable;
import software.amazon.awssdk.enhanced.dynamodb.Key;
import software.amazon.awssdk.enhanced.dynamodb.TableSchema;

@Repository
public class ReservationEnhancedRepository {
    private final DynamoDbTable<ReservationRecord> table;

    public ReservationEnhancedRepository(DynamoDbEnhancedClient client) {
        this.table = client.table(
                "reservation_record",
                TableSchema.fromBean(ReservationRecord.class));
    }

    public void save(ReservationRecord item) {
        table.putItem(item);
    }

    public Optional<ReservationRecord> findById(
            String tenantId, String reservationId) {
        Key key = Key.builder()
                .partitionValue(tenantId)
                .sortValue(reservationId)
                .build();

        return Optional.ofNullable(table.getItem(key));
    }

    public void deleteById(String tenantId, String reservationId) {
        table.deleteItem(Key.builder()
                .partitionValue(tenantId)
                .sortValue(reservationId)
                .build());
    }
}
~~~

If the project **does not use the AWSpring starter**, declare the AWS SDK v2 dependencies `software.amazon.awssdk:dynamodb` and `software.amazon.awssdk:dynamodb-enhanced` and configure the two beans:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import software.amazon.awssdk.auth.credentials.DefaultCredentialsProvider;
import software.amazon.awssdk.enhanced.dynamodb.DynamoDbEnhancedClient;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.dynamodb.DynamoDbClient;

@Configuration
class DynamoDbSdkConfiguration {
    @Bean
    DynamoDbClient dynamoDbClient() {
        return DynamoDbClient.builder()
                .region(Region.AP_SOUTHEAST_1)
                .credentialsProvider(DefaultCredentialsProvider.create())
                .build();
    }

    @Bean
    DynamoDbEnhancedClient dynamoDbEnhancedClient(DynamoDbClient client) {
        return DynamoDbEnhancedClient.builder()
                .dynamoDbClient(client)
                .build();
    }
}
~~~

The plain SDK configuration above targets the real AWS endpoint. To run locally, configure `endpointOverride(URI.create("http://localhost:8000"))` and the corresponding local region/credentials; the `spring.cloud.aws.dynamodb.endpoint` property will not apply automatically if AWSpring auto-configuration is omitted completely. **Do not re-declare these client beans** if the starter already creates suitable beans, unless you intentionally want to override the default configuration.

## 9. Repeatable Integration Testing

A unit test with a mocked repository only tests service logic; to catch mismatches in table name, keys, mapper, endpoint configuration, and beans, you need an **integration test against DynamoDB Local or LocalStack**.

A straightforward workflow on a development machine:

1. Start the DynamoDB Local container and create the `reservation_record` table as shown in Sections 5–6.
2. Set dummy credential environment variables in the terminal running the tests and activate the `local` profile.
3. Run a Spring Boot test that writes an item using the real repository, reads it back, and verifies the fields.
4. Generate a random `tenantId` / `reservationId` per test or delete items during cleanup to avoid depending on leftover state.

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;

@SpringBootTest
@ActiveProfiles("local")
class ReservationRepositoryIT {

    @Autowired
    ReservationRepository repository;

    @Test
    void saveThenLoadFromRealDynamoDbEndpoint() {
        String tenant = "it-" + UUID.randomUUID();

        ReservationRecord item = new ReservationRecord();
        item.setTenantId(tenant);
        item.setReservationId("res-1");
        item.setPropertyId("property-1");
        item.setState("CONFIRMED");

        repository.save(item);

        ReservationRecord loaded = repository
                .findById(tenant, "res-1")
                .orElseThrow();

        assertEquals("CONFIRMED", loaded.getState());
        assertEquals("property-1", loaded.getPropertyId());

        repository.deleteById(tenant, "res-1");
    }
}
~~~

The test above assumes a Spring Boot app and JUnit 5/test starter are present, **DynamoDB Local is running, and the table has already been created**. For environment-independent CI, launch a container via Testcontainers, dynamically configure endpoint/region/credentials, and create the table in test setup. Some AWSpring versions support `spring-cloud-aws-testcontainers` with `@ServiceConnection` for LocalStack; check the documentation for your exact version since the syntax depends on both Spring Boot and Testcontainers.

Additional cases worth testing include: missing key, mismatched partition/sort key, multiple items under the same tenant, missing table, invalid credentials/region, insufficient IAM policy permissions, and concurrent conditional writes. A real test should only be considered PASSING after running against a test endpoint—not merely because example code looks plausible.

## 10. Common Errors and Diagnostics

| Symptom | Causes to check | Remediation |
| --- | --- | --- |
| `NoSuchBeanDefinitionException: DynamoDbTemplate` | Unsupported starter/version, auto-config disabled, bean not created | Check BOM, dependency tree, `spring.cloud.aws.dynamodb.enabled`, and auto-configuration conditions |
| `NoClassDefFoundError` / `NoSuchMethodError` | AWS SDK v2/AWSpring conflict or incompatible Spring Boot version | Use the matching BOM, align dependency versions; avoid arbitrary SDK overrides |
| `Unable to load credentials` | No suitable credential provider found or app running outside AWS | Check AWS profile, env vars, IAM role, workload identity; use dummy credentials locally |
| `ResourceNotFoundException` | Wrong table name, region, account, or endpoint | Check `describe-table`, the resolver-generated table name, and the active region |
| `ValidationException` on key access | Missing sort key, wrong data type, mismatched attribute name | Compare `@DynamoDbPartitionKey`, `@DynamoDbSortKey`, and `Key.builder()` against the table schema |
| `AccessDeniedException` | IAM policy denies the action on the table/index | Verify the effective role and resource ARNs in the policy |
| `ConditionalCheckFailedException` | Write/update condition no longer holds | Distinguish business conflict from system error; apply controlled retry if appropriate |
| Newly written data not visible immediately | Eventually consistent read or reading via GSI | Use consistent read on supported operations when needed; do not assume GSI strong consistency |
| Slow or expensive queries | Broad scan/filter, hot partition, unbounded pagination | Redesign key/index, bound returned data, and monitor consumed capacity |

You may enable AWS SDK/HTTP logs for diagnostics, but **mask sensitive data**—avoid logging credentials, tokens, full customer payloads, or personally identifiable information.

## 11. Production Decisions

### Permissions and Secret Protection

Use short-lived IAM roles following the principle of least privilege; separate roles across dev/staging/prod environments. If the application must store secrets outside configuration, consider AWS Secrets Manager or Parameter Store as appropriate for the data type. DynamoDB encrypts data at rest by default, but you still need TLS in transit, access policies, application-level sensitive data controls, and backup/recovery procedures.

### Cost, Latency, and Scalability

DynamoDB offers capacity modes such as on-demand and provisioned. Account for read/write throughput, item size, indexes, TTL, backups, request count, and access regions. Key-based `Query` is generally much better suited than `Scan` for large tables; GSIs expand query flexibility at the cost of extra storage and write capacity.

### Data Correctness

- `save` does not enforce business uniqueness by itself; use conditional writes whenever duplicate prevention is mandatory.
- DynamoDB transactions are not equivalent to placing JPA's `@Transactional` on repository methods; use the dedicated transaction API when multiple changes must be atomic.
- Retry `ThrottlingException` / network errors using the SDK backoff strategy and design idempotent writes; do not blindly retry every error, especially when the outcome of a prior write is uncertain.
- DynamoDB enforces a maximum item size limit; store large documents or images in S3 and keep only metadata/references in the table.
- If frequent multi-dimensional reads are needed, design additional GSIs upfront; note that index data may update asynchronously and GSI queries do not support strong consistency.

### Boundaries Between Cloud Providers

This example is specific to AWS DynamoDB, not a unified API for Azure Cosmos DB or Google Cloud Firestore. When building multi-cloud applications, define business repository interfaces at the application layer and let each AWS/Azure/GCP adapter implement them according to that provider's key/index model, consistency guarantees, transactions, and IAM model.

## 12. Extended Practice Exercises

1. Add a `GSI` to look up reservations by `propertyId` and timestamp; document which queries use the primary key, which use the index, and why `Scan` is avoided.
2. Add a "create only if not exists" operation using an Enhanced Client conditional write; issue two concurrent requests with the same key and handle `ConditionalCheckFailedException`.
3. Integrate Testcontainers in CI so the container and table are provisioned automatically; verify CRUD operations and access permissions in the test environment.
4. Measure the difference between a tenant-scoped `Query` and a full-table `Scan` as item count grows; observe page counts, consumed capacity, and result limits.
5. Compare application portability when migrating from DynamoDB to Azure Cosmos DB or Google Cloud Firestore: identity, data keys, SDKs, query models, and cost.

## References

- [Spring Cloud AWS 3.4.2 – DynamoDb Integration](https://docs.awspring.io/spring-cloud-aws/docs/3.4.2/reference/html/index.html): starter, credentials/region/endpoint configuration, template, and table naming.
- [DynamoDbTemplate API – Spring Cloud AWS 3.4.0](https://docs.awspring.io/spring-cloud-aws/docs/3.4.0/apidocs/io/awspring/cloud/dynamodb/DynamoDbTemplate.html): signatures for `save`, `load`, `query`, `delete`, and other operations.
- [Spring Cloud AWS 4.1.1 – Reference](https://docs.awspring.io/spring-cloud-aws/docs/4.1.1/reference/html/index.html): reference when using newer library versions.
- [AWS SDK for Java 2.x – DynamoDB Enhanced Client](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/dynamodb-enhanced-client.html): table schema, entity mapper, and advanced operations.
- [AWS DynamoDB Developer Guide](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/Introduction.html): keys, queries, indexes, consistency, IAM, capacity, and service limits.

# Managing Entities with Redis Repository and Secondary Indexes

Spring Data Redis does not only support accessing Redis via low-level commands like `GET`, `SET`, `HSET`, or `SADD`. With **Redis Repository**, a Java application can manage entities in the familiar Spring Data model: declare an entity, define a repository interface extending `CrudRepository`, and then use `save`, `findById`, `findAll`, and `deleteById`. When you need to look up entities by attributes rather than by ID, **secondary indexes** help Redis Repository find matching IDs without scanning the entire keyspace yourself.

This exercise builds a small **customer** management application. Each customer has an ID, full name, normalized email, status, city, and an optional TTL. We will create an entity using `@RedisHash` and `@Id`, index selected attributes with `@Indexed`, define a repository with derived queries, implement a CRUD service, and test against a real Redis instance.

Important: Redis Repository is a way of mapping entities onto Redis data structures, **not a relational database management system**. Spring Data Redis secondary indexes serve supported queries on indexed properties; they do not automatically provide unique constraints, JOINs, arbitrary SQL queries, full-text search, or ACID transactions across multi-key workflows.

## 1. Practice Objectives

After this lesson, learners will be able to:

1. Configure a Spring Boot application using Spring Data Redis Repositories.
2. Map a Java object to a Redis Hash with `@RedisHash` and `@Id`.
3. Declare secondary indexes using `@Indexed` for searchable fields.
4. Create a `CrudRepository<Customer, String>` interface and derived queries on indexed fields.
5. Perform create, read, update, and delete operations on entities without manually writing `HSET`/`SADD` in the service.
6. Observe how secondary indexes associate attribute values with entity IDs.
7. Experiment with updating indexed attributes and distinguish entity data from index data.
8. Use `@TimeToLive` deliberately, understanding the impact of expiration on index cleanup.
9. Identify limitations regarding uniqueness, consistency, querying, and operations.
10. Write integration tests against real Redis using Testcontainers.

### Application Context

Suppose the API needs these operations:

| Operation | Example | Access Method |
| --- | --- | --- |
| Add customer | Create a customer in Hanoi | `repository.save(customer)` |
| Get by ID | View customer `c-42` | `repository.findById(id)` |
| Find by status | List of `ACTIVE` customers | `findByStatus("ACTIVE")` |
| Find by city | List of `HANOI` customers | `findByCity("HANOI")` |
| Combine two conditions | `ACTIVE` customers in `HANOI` | `findByStatusAndCity(...)` |
| Find by normalized email | Find records with matching email | `findByEmailNormalized(...)` |
| Change city | `HANOI` to `DANANG` | Load entity, modify field, `save` |
| Delete customer | Delete `c-42` | `deleteById(id)` |

Status, city, and email values are query attributes. The ID is the primary key for direct entity access.

## 2. How Does Redis Repository Store Data?

For an entity annotated with `@RedisHash("customers")`, Spring Data Redis maps entity data to a **Redis Hash**, typically keyed by keyspace and ID:

~~~text
customers:<customerId>
   |
   +-- id               = <customerId>
   +-- fullName         = ...
   +-- emailNormalized  = ...
   +-- status           = ACTIVE
   +-- city             = HANOI
   +-- ttlSeconds       = ...
~~~

To query by `status` or `city`, Spring Data Redis can maintain **Sets containing IDs** per indexed attribute value:

~~~text
                         Redis database

Entity Hash:

customers:c-001 ──────> {status: ACTIVE, city: HANOI,  ...}
customers:c-002 ──────> {status: ACTIVE, city: DANANG, ...}
customers:c-003 ──────> {status: LOCKED, city: HANOI, ...}

Secondary index (conceptual model):

customers:status:ACTIVE  ──> {c-001, c-002}
customers:status:LOCKED  ──> {c-003}

customers:city:HANOI    ──> {c-001, c-003}
customers:city:DANANG   ──> {c-002}
~~~

The index key names in the diagram illustrate the mechanism; **do not treat them as a stable storage API for business code to modify directly with `SADD`/`SREM`**. Spring Data Redis also maintains metadata needed to track an entity's indexes; exact key details depend on the mapping and version.

Example query by a single attribute:

~~~text
findByStatus("ACTIVE")
        |
        v
Look up ACTIVE status index
        |
        v
Retrieve ID set {c-001, c-002}
        |
        v
Read corresponding Hashes
        |
        v
Return List<Customer>
~~~

For two supported conditions, the system can combine the ID sets corresponding to the indexes to find matching entities. For example, intersecting the `ACTIVE` set with the `HANOI` set yields `c-001`.

### Why Is Indexing Needed?

With only the Hash `customers:c-001`, Redis does not inherently know "which customers have `status=ACTIVE`". Accessing by ID is fast because the key is known. Searching by an arbitrary field requires an additional mapping structure or scanning the data.

The `@Indexed` annotation lets Spring Data Redis maintain a secondary index for the specified field, allowing supported derived queries to avoid having the service manually `SCAN` every entity and deserialize each record.

**In return**, each save/delete operation can incur index updates, additional memory usage, and extra Redis commands. Therefore, only index fields that genuinely serve queries.

## 3. Preparing the Spring Boot Application and Redis

The example uses Java 21, Spring Boot 3.x, Spring Data Redis, and Gradle Groovy DSL. Redis must be started in a separate test environment; you can use a local Redis installation, Docker, or a Redis development server.

### 3.1. Dependencies

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '<SPRING_BOOT_VERSION>'
    id 'io.spring.dependency-management' version '<DEPENDENCY_MANAGEMENT_VERSION>'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-validation'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.testcontainers:junit-jupiter'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

The version placeholders in the `plugins` block must be replaced with compatible Spring Boot/dependency-management versions used by your project. If the project already has the Spring Boot plugin and BOM, just add the missing dependencies; do not duplicate a second plugin block.

`spring-boot-starter-data-redis` brings Spring Data Redis and the necessary Redis client into the application; in typical Spring Boot configurations, Lettuce is the default client choice. `spring-boot-starter-web` is only needed if adding a REST API; the repository/service layer can run without a web server.

### 3.2. Starting Development Redis

An illustrative Docker command:

~~~bash
docker run --name redis-repository-lab \
  -p 127.0.0.1:6379:6379 \
  -d redis:7.2-alpine
~~~

This command binds the Redis port to the Docker host's loopback interface to avoid intentionally exposing an unauthenticated test Redis to external networks. Do not use this lab configuration in production. In shared environments or machines where port 6379 is already occupied, choose another port and update the application configuration accordingly.

Verify Redis:

~~~bash
redis-cli -h 127.0.0.1 -p 6379 PING
~~~

When connected successfully, the typical response is `PONG`.

### 3.3. `application.yml`

~~~yaml
spring:
  application:
    name: redis-repository-lab
  data:
    redis:
      host: 127.0.0.1
      port: 6379
      connect-timeout: 2s
      timeout: 3s
~~~

The example is standalone development Redis. For Redis with ACL/TLS, Sentinel, or Cluster, configure accordingly. **The repository does not handle authentication, network security, or topology discovery on its own**; it uses the `RedisConnectionFactory` configured by the application.

### 3.4. Enabling Redis Repositories

~~~java
package com.example.redis.repositorylab;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.data.redis.repository.configuration.EnableRedisRepositories;

@SpringBootApplication
@EnableRedisRepositories(
    basePackages = "com.example.redis.repositorylab.repository"
)
public class RedisRepositoryLabApplication {

    public static void main(String[] args) {
        SpringApplication.run(
            RedisRepositoryLabApplication.class, args
        );
    }
}
~~~

`@EnableRedisRepositories` specifies the package containing repository interfaces for which Spring Data Redis should generate implementations. When relying entirely on Spring Boot auto-configuration, this annotation may not be strictly necessary; the example includes it to clarify which repository type is enabled and its scan scope.

If the application simultaneously uses JPA, MongoDB, or multiple Spring Data stores, design repository scanning clearly to avoid ambiguity over which store owns which repository.

## 4. Declaring the `Customer` Entity

Create `src/main/java/com/example/redis/repositorylab/model/Customer.java`:

~~~java
package com.example.redis.repositorylab.model;

import org.springframework.data.annotation.Id;
import org.springframework.data.redis.core.RedisHash;
import org.springframework.data.redis.core.TimeToLive;
import org.springframework.data.redis.core.index.Indexed;

@RedisHash("customers")
public class Customer {

    @Id
    private String id;

    private String fullName;

    @Indexed
    private String emailNormalized;

    @Indexed
    private String status;

    @Indexed
    private String city;

    @TimeToLive
    private Long ttlSeconds;

    protected Customer() {
        // Constructor for object mapping.
    }

    public Customer(
            String id,
            String fullName,
            String emailNormalized,
            String status,
            String city,
            Long ttlSeconds) {
        this.id = id;
        this.fullName = fullName;
        this.emailNormalized = emailNormalized;
        this.status = status;
        this.city = city;
        this.ttlSeconds = ttlSeconds;
    }

    public String getId() {
        return id;
    }

    public void setId(String id) {
        this.id = id;
    }

    public String getFullName() {
        return fullName;
    }

    public void setFullName(String fullName) {
        this.fullName = fullName;
    }

    public String getEmailNormalized() {
        return emailNormalized;
    }

    public void setEmailNormalized(String emailNormalized) {
        this.emailNormalized = emailNormalized;
    }

    public String getStatus() {
        return status;
    }

    public void setStatus(String status) {
        this.status = status;
    }

    public String getCity() {
        return city;
    }

    public void setCity(String city) {
        this.city = city;
    }

    public Long getTtlSeconds() {
        return ttlSeconds;
    }

    public void setTtlSeconds(Long ttlSeconds) {
        this.ttlSeconds = ttlSeconds;
    }
}
~~~

### Annotation Meanings

| Annotation | Function | Notes |
| --- | --- | --- |
| `@RedisHash("customers")` | Marks the entity as mapped to a Redis Hash in the `customers` keyspace | Does not mean creating a SQL table |
| `@Id` | Marks the identifier property | Repository uses ID for `findById`/`deleteById` |
| `@Indexed` | Requests a secondary index for the field | Consumes extra memory and index update operations |
| `@TimeToLive` | Uses the property value to manage entity TTL | Default unit for numeric properties is seconds; needs a clear policy |

An entity does not have to have a TTL: when you do not want entities to auto-expire, omit `@TimeToLive` or design lifetimes per specific requirements. In this exercise, `ttlSeconds` is included to practice expiration behavior and its effects on indexes.

**Do not put `@Indexed` on every field.** Attributes like `fullName` may not need indexing if the application only displays by ID and does not query directly by name. Even when indexed, Redis Repository does not turn a String field into a fuzzy search, prefix matching, or full-text search tool.

### Why Normalize Data Before Saving?

Suppose successive saves use for the same status:

~~~text
ACTIVE
active
Active
 ACTIVE
~~~

If the application treats them as one status but stores different strings, they can create multiple distinct index values. Similarly, `Hanoi` and `HANOI` do not automatically match the same search condition.

Status, city, and email should be normalized in the service or a dedicated layer before calling `save`. Choose normalization rules that fit business requirements; do not arbitrarily transform internationalized emails or proper names in multilingual systems without defined rules.

## 5. Declaring the `CustomerRepository` Interface

Create `src/main/java/com/example/redis/repositorylab/repository/CustomerRepository.java`:

~~~java
package com.example.redis.repositorylab.repository;

import java.util.List;

import org.springframework.data.repository.CrudRepository;
import com.example.redis.repositorylab.model.Customer;

public interface CustomerRepository
        extends CrudRepository<Customer, String> {

    List<Customer> findByStatus(String status);

    List<Customer> findByCity(String city);

    List<Customer> findByEmailNormalized(
        String emailNormalized
    );

    List<Customer> findByStatusAndCity(
        String status, String city
    );
}
~~~

Spring Data generates the implementation for the repository interface at runtime. Methods inherited from `CrudRepository`:

~~~java
repository.save(customer);
repository.findById(customerId);
repository.existsById(customerId);
repository.findAll();
repository.count();
repository.deleteById(customerId);
repository.delete(customer);
~~~

Custom-declared methods `findByStatus`, `findByCity`, and `findByEmailNormalized` require Spring Data to recognize the field names and have appropriate secondary indexes. `findByStatusAndCity` demonstrates querying by two indexed properties; for more complex query expressions, verify the operators/conditions supported by your project's Spring Data Redis version rather than assuming all JPA derived query syntax is supported.

### Secondary Indexes Do Not Have Unique Constraints

`@Indexed` on `emailNormalized` only helps look up IDs by email; it **does not guarantee email uniqueness**:

~~~text
customers:emailNormalized:alice@example.com
  └── may contain both IDs c-101 and c-205
~~~

Therefore the repository uses `List<Customer> findByEmailNormalized(...)` rather than assuming there is always exactly one record. If business rules require unique emails, you need a dedicated atomic uniqueness allocation/enforcement mechanism, such as a table with a unique constraint or an appropriate conditional operation at the source of truth. Having a service call `findByEmailNormalized` then `save` is **not atomic** and suffers from race conditions when multiple instances create customers concurrently.

## 6. Practicing CRUD Through a Service

Define a service that handles data normalization, ID generation, repository calls, and input validation. Do not call `SADD` or `SREM` directly to modify indexes from business code; **Spring Data Redis repository must be the party managing indexes corresponding to the entity**.

Create `src/main/java/com/example/redis/repositorylab/service/CustomerService.java`:

~~~java
package com.example.redis.repositorylab.service;

import java.util.List;
import java.util.Locale;
import java.util.NoSuchElementException;
import java.util.Objects;
import java.util.UUID;

import org.springframework.stereotype.Service;

import com.example.redis.repositorylab.model.Customer;
import com.example.redis.repositorylab.repository.CustomerRepository;

@Service
public class CustomerService {

    private final CustomerRepository repository;

    public CustomerService(CustomerRepository repository) {
        this.repository = repository;
    }

    public Customer create(
            String fullName,
            String email,
            String city) {
        String id = UUID.randomUUID().toString();

        Customer customer = new Customer(
            id,
            requireText(fullName, "fullName"),
            normalizeEmail(email),
            "ACTIVE",
            normalizeToken(city, "city"),
            3600L
        );

        return repository.save(customer);
    }

    public Customer getRequired(String id) {
        Objects.requireNonNull(id, "id");
        return repository.findById(id)
            .orElseThrow(() ->
                new NoSuchElementException(
                    "Customer not found: " + id
                )
            );
    }

    public List<Customer> findActive() {
        return repository.findByStatus("ACTIVE");
    }

    public List<Customer> findByCity(String city) {
        return repository.findByCity(
            normalizeToken(city, "city")
        );
    }

    public List<Customer> findActiveByCity(String city) {
        return repository.findByStatusAndCity(
            "ACTIVE", normalizeToken(city, "city")
        );
    }

    public List<Customer> findByEmail(String email) {
        return repository.findByEmailNormalized(
            normalizeEmail(email)
        );
    }

    public Customer changeCity(String id, String newCity) {
        Customer customer = getRequired(id);
        customer.setCity(normalizeToken(newCity, "city"));
        return repository.save(customer);
    }

    public Customer changeStatus(String id, String newStatus) {
        Customer customer = getRequired(id);
        String status = normalizeToken(newStatus, "status");
        if (!status.equals("ACTIVE")
                && !status.equals("LOCKED")
                && !status.equals("INACTIVE")) {
            throw new IllegalArgumentException(
                "Unsupported customer status"
            );
        }
        customer.setStatus(status);
        return repository.save(customer);
    }

    public void delete(String id) {
        Objects.requireNonNull(id, "id");
        repository.deleteById(id);
    }

    private static String requireText(
            String value, String field) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(
                field + " must not be blank"
            );
        }
        String trimmed = value.trim();
        if (trimmed.length() > 200) {
            throw new IllegalArgumentException(
                field + " is too long"
            );
        }
        return trimmed;
    }

    private static String normalizeToken(
            String value, String field) {
        String token = requireText(value, field)
            .toUpperCase(Locale.ROOT);
        if (!token.matches("[A-Z0-9_-]{1,64}")) {
            throw new IllegalArgumentException(
                "Invalid " + field
            );
        }
        return token;
    }

    private static String normalizeEmail(String value) {
        String email = requireText(value, "email")
            .toLowerCase(Locale.ROOT);
        if (email.length() > 254
                || !email.contains("@")) {
            throw new IllegalArgumentException(
                "Invalid email"
            );
        }
        return email;
    }
}
~~~

The class above uses only a minimal email rule to illustrate normalization in the lesson. **Do not use `contains("@")` as full email validation or to guarantee email uniqueness in real production software.** For applications with internationalized emails, aliases, or case-sensitive local-parts, define normalization rules according to business contracts and the identity system.

Each created customer is assigned a UUID before calling the repository. Explicit ID assignment is convenient for tests and illustrating key paths; it does not mean Spring Data Redis lacks support for certain ID generation mechanisms.

### What Happens When Updating an Indexed Field?

Suppose customer `c-001` initially has:

~~~text
id: c-001
status: ACTIVE
city: HANOI
~~~

The service runs:

~~~java
Customer changed =
    customerService.changeCity("c-001", "DANANG");
~~~

Logically, the repository needs to maintain:

~~~text
Before:
  index city:HANOI  -> contains c-001
  index city:DANANG -> does not contain c-001

After:
  index city:HANOI  -> no longer contains c-001
  index city:DANANG -> contains c-001
~~~

Spring Data Redis maintains metadata/indexes for this update operation. Do not write `HSET customers:c-001 city DANANG` directly and expect indexes to update automatically as with `repository.save`: **bypassing repository mapping can make Hash data and secondary indexes inconsistent**.

## 7. Creating a REST API for Practice

If the application includes `spring-boot-starter-web`, you can add a small REST controller to invoke the service. The HTTP layer only receives input, invokes business logic, and converts entities to response DTOs; it does not directly manipulate Redis indexes.

Create `src/main/java/com/example/redis/repositorylab/api/CustomerController.java`:

~~~java
package com.example.redis.repositorylab.api;

import java.net.URI;
import java.util.List;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import com.example.redis.repositorylab.model.Customer;
import com.example.redis.repositorylab.service.CustomerService;

@RestController
@RequestMapping("/api/customers")
public class CustomerController {

    private final CustomerService service;

    public CustomerController(CustomerService service) {
        this.service = service;
    }

    public record CreateCustomerRequest(
        @NotBlank String fullName,
        @NotBlank String email,
        @NotBlank String city
    ) {
    }

    public record UpdateCityRequest(
        @NotBlank String city
    ) {
    }

    public record CustomerResponse(
        String id,
        String fullName,
        String status,
        String city
    ) {
        static CustomerResponse from(Customer customer) {
            return new CustomerResponse(
                customer.getId(),
                customer.getFullName(),
                customer.getStatus(),
                customer.getCity()
            );
        }
    }

    @PostMapping
    public ResponseEntity<CustomerResponse> create(
            @Valid @RequestBody CreateCustomerRequest request) {
        Customer created = service.create(
            request.fullName(),
            request.email(),
            request.city()
        );

        return ResponseEntity
            .created(URI.create("/api/customers/" + created.getId()))
            .body(CustomerResponse.from(created));
    }

    @GetMapping("/{id}")
    public CustomerResponse get(@PathVariable String id) {
        return CustomerResponse.from(service.getRequired(id));
    }

    @GetMapping("/active")
    public List<CustomerResponse> activeInCity(
            @RequestParam String city) {
        return service.findActiveByCity(city)
            .stream()
            .map(CustomerResponse::from)
            .toList();
    }

    @PatchMapping("/{id}/city")
    public CustomerResponse changeCity(
            @PathVariable String id,
            @Valid @RequestBody UpdateCityRequest request) {
        return CustomerResponse.from(
            service.changeCity(id, request.city())
        );
    }

    @DeleteMapping("/{id}")
    public ResponseEntity<Void> delete(@PathVariable String id) {
        service.delete(id);
        return ResponseEntity.noContent().build();
    }
}
~~~

The controller returns a DTO omitting email and TTL to illustrate the principle of **not automatically returning the entire Redis entity** to clients. In real systems, which fields may be returned depends on business requirements and authorization; the DTO here is just an example.

To give the API appropriate HTTP status codes when an ID is not found, you can add a `@RestControllerAdvice` mapping `NoSuchElementException` to 404 and `IllegalArgumentException` to 400. Do not let Redis connection errors or malformed schema data turn into 404 by default, as those are different situations from "customer does not exist".

### Testing via HTTP

Start the application, then send a create request:

~~~bash
curl -X POST http://localhost:8080/api/customers \
  -H "Content-Type: application/json" \
  -d '{
    "fullName": "Nguyen An",
    "email": "AN@example.com",
    "city": "hanoi"
  }'
~~~

Sample response:

~~~json
{
  "id": "c8c77cc9-7a66-4b88-8e9c-4790cb50efc1",
  "fullName": "Nguyen An",
  "status": "ACTIVE",
  "city": "HANOI"
}
~~~

Actual IDs are UUID-generated and differ between runs. Use the returned ID to test:

~~~bash
curl http://localhost:8080/api/customers/c8c77cc9-7a66-4b88-8e9c-4790cb50efc1

curl "http://localhost:8080/api/customers/active?city=HANOI"

curl -X PATCH \
  http://localhost:8080/api/customers/c8c77cc9-7a66-4b88-8e9c-4790cb50efc1/city \
  -H "Content-Type: application/json" \
  -d '{"city":"danang"}'

curl "http://localhost:8080/api/customers/active?city=DANANG"
~~~

After updating the city, querying `active?city=HANOI` no longer returns that customer, while querying `active?city=DANANG` returns the customer if the index was updated successfully by the repository.

These HTTP commands are solely for an unauthenticated test application. In production, customer management endpoints need authentication, authorization, rate limiting, and personal data protection. Do not put real emails or user tokens into logs/test scripts.

## 8. Inspecting Data with Redis CLI

Instead of guessing generated Redis keys, start from the entity ID returned by the API:

~~~bash
redis-cli -h 127.0.0.1 -p 6379 TYPE customers:<customer-id>
redis-cli -h 127.0.0.1 -p 6379 HGETALL customers:<customer-id>
redis-cli -h 127.0.0.1 -p 6379 TTL customers:<customer-id>
~~~

Replace `<customer-id>` with the actual ID. With the `@RedisHash("customers")` mapping, entity keys typically belong to this keyspace and use a Redis Hash to store mapped fields.

To explore related keys:

~~~bash
redis-cli -h 127.0.0.1 -p 6379 \
  --scan --pattern 'customers:*'
~~~

`--scan` uses the `SCAN` mechanism. On a large dataset, results may require multiple cursor iterations; it does not represent an immutable snapshot while the keyspace is changing.

Steps to observe indexes:

1. Create two customers with `status=ACTIVE` and `city=HANOI`.
2. Use `--scan --pattern 'customers:*'` to inspect keys created by the repository.
3. Identify keys of Redis Set type using `TYPE <key>`.
4. For the appropriate index key in the test environment, use `SMEMBERS <key>` to observe the IDs.
5. Update a customer's city via the service.
6. Observe changes in `findByCity(...)` results; if needed, compare the corresponding metadata/indexes.

**Do not depend on internal secondary index key names in application code**, as they are an implementation detail of Spring Data Redis. Use the repository API for CRUD/queries; the CLI is for observation and diagnostics.

### Example Difference Between Hash and Set

Redis Hash:

~~~text
HGETALL customers:c-001
    id         -> c-001
    fullName   -> Nguyen An
    status     -> ACTIVE
    city       -> HANOI
~~~

Redis Set for a secondary index, conceptually:

~~~text
SMEMBERS [status ACTIVE index key]
    c-001
    c-002
~~~

The Hash holds the entity data; the index Set is a structure for finding IDs. An index is **not a full copy of the object**, so an index query still needs to read the corresponding entities to materialize `Customer`.

If an index key holds the ID of an entity that expired without being cleaned up, the repository may have to handle that ID no longer having a Hash. This is why TTL management and events affect both accuracy and index maintenance cost.

## 9. Secondary Index Lifecycle on Save, Update, and Delete

When a repository saves an entity for the first time, it stores the Hash and maintains the declared indexes. When an entity is updated, old index associations must be adjusted; when deleted, old associations must also be removed.

| Repository Operation | Entity Hash | Secondary Index |
| --- | --- | --- |
| New `save` | Creates key/entity | Adds ID to indexes of marked field values |
| `save` after changing city | Updates data | Updates ID association from old city value to new |
| `save` after changing status | Updates data | Adjusts Sets for old/new status |
| `deleteById` | Deletes entity data | Repository cleans up related indexes/metadata |
| Entity TTL expires | Redis auto-deletes entity key | Requires proper expiration/cleanup handling |
| Direct `HSET` write | Hash changes without going through repository | **No guarantee indexes are updated properly** |

### Save Is Not a Single-Command Change

Writing the Hash and updating multiple index Sets may require **multiple Redis commands**. Do not assume the entire save sequence is protected like a relational database ACID transaction simply because you call one `repository.save(...)` method.

With two instances modifying the same entity concurrently:

~~~text
T0  App A reads customer c-001: city=HANOI
T1  App B reads customer c-001: city=HANOI
T2  App A sets city=DANANG and saves
T3  App B sets status=LOCKED and saves its stale entity copy
~~~

Without an appropriate coordination/versioning mechanism, App B can overwrite the old city back or create races in the corresponding indexes. Redis Repository **does not automatically turn every "read → modify object → save" block into safe optimistic locking across multiple workers**.

If business rules require concurrent updates to a critical entity, evaluate organizing atomic updates, compare-and-set/Lua, a data source with optimistic locking, or transactions in an appropriate system. For rebuildable cached data, accepting certain consistency limits is sometimes more practical.

### Why Not Update Indexes Manually?

An anti-pattern:

~~~java
// The Hash changes, but the repository's metadata/index Sets
// are not synchronized per Spring Data Redis's contract.
stringRedisTemplate.opsForHash()
    .put("customers:c-001", "city", "DANANG");
~~~

After this command, `repository.findByCity("HANOI")` may still rely on the old index, while the Hash says city is `DANANG`. The application may observe strange, missing, or extra IDs.

If you must interact directly with Redis keys managed by a repository, treat it as **intervening in internal structures** and have a clear plan to update/rebuild indexes; it is better to let a single primary write path maintain both data and indexes.

## 10. Entity TTL and the Risk of Indexes Referencing Expired Keys

The `@TimeToLive` property lets the Repository set an entity's lifetime. In the example, `ttlSeconds=3600L` represents a 3,600-second lifetime at save time.

~~~java
Customer customer = new Customer(
    "c-100",
    "Le Minh",
    "le.minh@example.com",
    "ACTIVE",
    "HANOI",
    3600L
);

repository.save(customer);
~~~

Redis manages expiration for the entity key. However, **an index Set is a separate structure**, and Redis expiring a Hash does not by default remove all corresponding IDs from Sets maintained by the application.

Spring Data Redis has mechanisms to listen for key expiration to support index cleanup and emit repository events; that mechanism involves **Redis keyspace notifications** and how repositories are configured.

### 10.1. What Are Keyspace Notifications?

Redis can emit events when keys expire. For example, a Redis configuration uses appropriate flags:

~~~text
notify-keyspace-events Ex
~~~

The example flags above enable **keyevent**-style notifications for **expired events**, depending on deployment requirements. A Spring Data Redis application can use repository listeners to react to key expiration events.

Important operational notes:

- Redis keyspace notifications may be **disabled by default** and must be configured appropriately.
- Some managed Redis services restrict `CONFIG SET`; configure via the provider's mechanism.
- Keyspace notifications work over Pub/Sub, **not a durable event log**.
- If the application stops receiving notifications while keys expire, events can be lost.
- If entities/metadata are not managed via the repository or the listener is inactive, index cleanup may be missed.

Therefore, do not look solely at a Hash's TTL and assume indexes will definitely have zero references to the entity after expiration in every scenario.

### 10.2. Configuring the Repository to Listen for Expiration

An optional configuration example:

~~~java
package com.example.redis.repositorylab;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.data.redis.core.RedisKeyValueAdapter.EnableKeyspaceEvents;
import org.springframework.data.redis.repository.configuration.EnableRedisRepositories;

@SpringBootApplication
@EnableRedisRepositories(
    basePackages = "com.example.redis.repositorylab.repository",
    enableKeyspaceEvents = EnableKeyspaceEvents.ON_STARTUP
)
public class RedisRepositoryLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(
            RedisRepositoryLabApplication.class, args
        );
    }
}
~~~

This is an **alternative variant** of the annotation in the application setup section, not a second `RedisRepositoryLabApplication` class to create side by side. In real configurations, ensure appropriate Redis keyspace notifications are enabled on the server and the listener has permission to subscribe.

Some repository configuration options attempt to configure notifications via Redis `CONFIG SET`; this is not always permitted on managed Redis services. If infrastructure manages `notify-keyspace-events` itself, check listener initialization options and configuration permissions in your Spring Data Redis version.

### 10.3. Shadow Copies When Entities Have TTL

Spring Data Redis Repository has options related to retaining a **copy for expiration events** for a period after the primary key expires. This is useful if the application needs expiration events containing entity contents, though it can increase key count and memory usage.

An application that only needs to know an ID expired and does not need full entity contents can consider disabling the shadow copy mechanism per the API of its Spring Data Redis version. However, changing that option **does not solve lost Pub/Sub events** when the listener is offline.

For workloads with many short-TTL entities, measure additional keys, memory, and event volume during expiration transitions. If you do not need expiring entities and only need caching, using `RedisTemplate` with simple TTLs may be less complex than repositories with secondary indexes.

### 10.4. Do Not Rely on `Thread.sleep` Right at the TTL Boundary

If you want to test an entity expiring after one second, the test should:

1. Save an entity with `ttlSeconds=1L`.
2. Poll `repository.findById(id)` until it returns empty or the test timeout expires.
3. For index cleanup, observe/verify separately and allow the event mechanism to process asynchronously.
4. Do not assume a notification will arrive at the exact millisecond TTL reaches 0.

Redis determines expiration according to server mechanics, while listener/index cleanup incurs additional event delivery latency. A fixed single sleep assertion can easily become flaky.

## 11. Differences Between Querying by ID and via Secondary Index

When the ID is known, the repository can access the entity by its corresponding key. When querying by status/city, the repository relies on the index to find IDs and then materializes objects. Both access paths have different costs and limits.

| Characteristic | `findById` | `findByStatus` / `findByCity` |
| --- | --- | --- |
| Input | Entity ID | Value of an indexed field |
| Lookup method | Directly via entity key | From index to IDs, then read entities |
| Needs `@Indexed`? | No, only `@Id` | Yes for searchable fields in the example |
| Result | `Optional<Customer>` | Collection/List of matching entities |
| Cost | Depends on one entity/key and network | Depends on matching ID count, entities to load, and index |
| Risk with large result sets | Lower | Can fetch thousands/millions of entities if unbounded |
| Uniqueness | ID identifies one key | Index is not unique by default |

### A Low-Selectivity Index

Suppose there are one million customers, of whom 950,000 have `status=ACTIVE`. The status index can become huge:

~~~text
status=ACTIVE   → 950,000 IDs
status=LOCKED   →  40,000 IDs
status=INACTIVE →  10,000 IDs
~~~

If an API calls `findByStatus("ACTIVE")` and returns every entity at once, the system risks:

- Reading and deserializing a massive number of entities.
- Allocating large Java objects and JSON responses, increasing heap/GC pressure.
- Consuming Redis–application and application–client network bandwidth.
- Causing high latency, timeouts, or pressure on other requests.

**Having an index does not mean every query is cheap.** If an attribute has only three values, the ID set per value can be massive. Evaluate selectivity, result limits, practical pagination, API response sizes, and SLOs.

### High-Cardinality Indexes

Emails typically have high cardinality: many distinct values, each with very few entities. An email index can increase the number of index keys/Sets and metadata. It is useful if the application genuinely needs lookup by email, but adds notable memory overhead if created across many similar fields.

Do not put `@Indexed` on every property just because "we might need to search by it someday". Index based on known queries and measure write/update/delete costs as well as Redis memory usage.

## 12. Query Limitations of Redis Repository

### 12.1. Redis Repository Is Not JPQL or SQL

Derived queries on indexed fields are a convenient feature, not equivalent to:

~~~sql
SELECT *
FROM customers c
JOIN orders o ON o.customer_id = c.id
WHERE LOWER(c.full_name) LIKE '%nguyen%'
ORDER BY c.created_at DESC
LIMIT 20 OFFSET 200;
~~~

Redis Repository does not automatically provide arbitrary JOINs across entities, full-text search on Strings, a SQL query planner, or full server-side sorting/pagination simply because an interface extends Spring Data Repository.

Simple operations like equality on `@Indexed` fields can be implemented with secondary indexes. For other needs, consider:

- Building a custom secondary index using Redis Sorted Sets when ordering/ranking is needed, with explicit synchronization logic.
- Using Redis Search/Query Engine if infrastructure includes the module and search requirements fit, via its corresponding API/library—**do not assume Redis Repository automatically enables full-text search**.
- Using a relational database or search engine as the query source when complex joins, predicates, sorting, and pagination are needed.
- Maintaining a read model tailored for queries instead of forcing the repository to handle every query pattern.

### 12.2. `findAll` Is Not a Pagination API

With a large customer set, calling:

~~~java
Iterable<Customer> all = repository.findAll();
~~~

and converting everything into a `List` returned over HTTP can consume a lot of memory. It is fine for small lab datasets, but should not be used as an unbounded production listing endpoint.

Do not assume adding `Pageable` to a derived query method will deliver index pagination efficiency equivalent to SQL `LIMIT/OFFSET`. Sorting, paging, and query operator capabilities depend on the Redis Repository implementation/version; verify against actual infrastructure and benchmark when designing large APIs.

### 12.3. Multi-Field Queries Only Work Well When Data Is Normalized

Suppose some entities store:

~~~text
status = ACTIVE
city   = HANOI
~~~

while other entities store:

~~~text
status = active
city   = Hanoi
~~~

`findByStatusAndCity("ACTIVE","HANOI")` may fail to find the second group. This is not a Redis secondary index bug; it is a **mismatch between data and normalization rules**. Therefore, the service must normalize input on both save and query paths, and have a migration plan for legacy data.

## 13. When Uniqueness, Transactions, and Concurrency Matter More Than Convenience

Redis Repository manages an entity as key/value data plus secondary indexes; it **does not automatically ensure one email can only be stored for a single customer**.

### 13.1. Race Condition When Checking Email

An error-prone implementation:

~~~java
if (repository.findByEmailNormalized(email).isEmpty()) {
    repository.save(newCustomer);
}
~~~

Across two instances:

~~~text
App A: findByEmailNormalized("a@example.com") → empty
App B: findByEmailNormalized("a@example.com") → empty
App A: save(customer-A) → succeeds
App B: save(customer-B) → succeeds

Result: the same email appears in two entities.
~~~

Reading an index and saving are two separate actions with no uniqueness guarantee. If strict uniqueness is required, prefer unique constraints at an appropriate data source; if building a uniqueness workflow in Redis, design an atomic allocation/check operation and handle partial failures during entity/index creation, TTL, failover, and recovery. A standalone `SET NX` for email **does not by itself make multi-key creation an atomic transaction**.

### 13.2. Partial Failure During Save

Suppose the repository is updating the Hash, index Sets, and related metadata. If Redis disconnects or the process is killed mid-sequence, partial changes may already have executed.

Actions to take:

1. Distinguish connection/timeout errors from validation/query errors.
2. Do not blindly retry a workflow that has side effects outside Redis.
3. If Redis is the primary data store, establish reconciliation and consistency-repair procedures between entities and indexes.
4. If Redis is only a read model/cache, rebuild from the authoritative data source.
5. Monitor index results containing IDs with missing Hashes and deserialization errors.

A `save` method does not promise distributed transactions across Redis, JDBC, and external HTTP services.

### 13.3. Redis Failover Can Leave Data/Metadata Out of Sync

Redis replication is asynchronous by default. A primary can acknowledge a write before replicas receive all updates. If failover happens right on that boundary, the new primary may lack the latest changes, including entities or index metadata.

Sentinel/Cluster address endpoint recovery and data availability to a degree, **without automatically providing zero-data-loss guarantees or transactions for Redis Repository**. Evaluate persistence, replication, and source-of-truth policies according to business criticality.

### 13.4. Which Data Fits Redis Repository?

Usually suitable when:

- Entities are relatively small and accessed mainly by ID.
- There are a few simple equality queries on indexed attributes.
- Redis serves as a read model/cache or datastore aligned with analyzed risks, durability, and semantics.
- No joins, full-text search, or complex aggregations are needed.
- Entity counts and query result sizes fit within RAM, network, and SLA limits.

Evaluate more carefully when:

- The entity is critical business data that must not be lost.
- Multiple writers update the same entity concurrently.
- Strict unique constraints or transactions are mandatory.
- Queries require complex sorting/pagination or fuzzy matching.
- Indexes contain massive ID sets with high update frequency.
- Short TTLs cause continuous expiration, especially when expiration events may be lost.

## 14. Integration Testing with Real Redis

Unit tests that merely mock `CustomerRepository` can check service logic, but **do not prove Spring Data Redis creates and maintains secondary indexes correctly**. To test mapping/indexes/TTL, use a real Redis server in an isolated test environment.

Example using JUnit 5, Spring Boot, and Testcontainers:

~~~java
package com.example.redis.repositorylab;

import java.time.Duration;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.GenericContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

import com.example.redis.repositorylab.model.Customer;
import com.example.redis.repositorylab.repository.CustomerRepository;
import com.example.redis.repositorylab.service.CustomerService;

import static org.assertj.core.api.Assertions.assertThat;

@Testcontainers
@SpringBootTest(classes = RedisRepositoryLabApplication.class)
class CustomerRepositoryIntegrationTest {

    @Container
    static final GenericContainer<?> REDIS =
        new GenericContainer<>(
            DockerImageName.parse("redis:7.2-alpine")
        ).withExposedPorts(6379);

    @DynamicPropertySource
    static void redisProps(DynamicPropertyRegistry registry) {
        registry.add(
            "spring.data.redis.host", REDIS::getHost
        );
        registry.add(
            "spring.data.redis.port",
            () -> REDIS.getMappedPort(6379)
        );
    }

    @Autowired
    CustomerRepository repository;

    @Autowired
    CustomerService service;

    @Autowired
    StringRedisTemplate redis;

    @Test
    void createAndReadByIdAndSecondaryIndexes() {
        Customer created = service.create(
            "Nguyen An", "AN@example.com", "hanoi"
        );
        String id = created.getId();

        try {
            Customer loaded = repository.findById(id)
                .orElseThrow();

            assertThat(loaded.getFullName())
                .isEqualTo("Nguyen An");
            assertThat(loaded.getStatus())
                .isEqualTo("ACTIVE");
            assertThat(loaded.getCity())
                .isEqualTo("HANOI");
            assertThat(loaded.getEmailNormalized())
                .isEqualTo("an@example.com");

            assertThat(service.findActiveByCity("hanoi"))
                .extracting(Customer::getId)
                .contains(id);

            assertThat(service.findByEmail("AN@example.com"))
                .extracting(Customer::getId)
                .contains(id);
        } finally {
            repository.deleteById(id);
        }
    }

    @Test
    void updatingIndexedFieldChangesQueryResult() {
        Customer created = service.create(
            "Le Binh", "le.binh@example.com", "hanoi"
        );
        String id = created.getId();

        try {
            assertThat(service.findByCity("hanoi"))
                .extracting(Customer::getId)
                .contains(id);

            service.changeCity(id, "danang");

            assertThat(service.findByCity("hanoi"))
                .extracting(Customer::getId)
                .doesNotContain(id);

            assertThat(service.findByCity("danang"))
                .extracting(Customer::getId)
                .contains(id);
        } finally {
            repository.deleteById(id);
        }
    }

    @Test
    void deletingEntityRemovesItsIndexMembership() {
        Customer created = service.create(
            "Do Ha", "do.ha@example.com", "hanoi"
        );
        String id = created.getId();

        repository.deleteById(id);

        assertThat(repository.findById(id)).isEmpty();
        assertThat(service.findByCity("hanoi"))
            .extracting(Customer::getId)
            .doesNotContain(id);
    }

    @Test
    void entityHasPositiveTimeToLive() {
        Customer created = service.create(
            "Tran Lan", "tran.lan@example.com", "hanoi"
        );
        String id = created.getId();

        try {
            Long ttl = redis.getExpire(
                "customers:" + id, TimeUnit.SECONDS
            );

            assertThat(ttl)
                .isNotNull()
                .isGreaterThan(0L)
                .isLessThanOrEqualTo(3600L);
        } finally {
            repository.deleteById(id);
        }
    }
}
~~~

### What the Integration Tests Verify

- `repository.save` creates an entity that `findById` can read back.
- Values are normalized by the service before indexing.
- `findByStatusAndCity` and `findByEmailNormalized` find the saved entity.
- After changing city and saving, queries for the old city no longer include the ID, while queries for the new city include it.
- `deleteById` makes the entity unfindable by ID and absent from the application's index query results.
- The `@TimeToLive` property results in a positive TTL on the entity key.

Each `create` call generates a distinct UUID, reducing collision risk when running tests concurrently. The `finally` block cleans up only the test's entity via the repository, avoiding calling `FLUSHALL` or `FLUSHDB` on a potentially shared Redis.

**Limitation of this test:** a single Redis container does not verify Sentinel failover, Cluster, keyspace notifications missed while listeners are offline, or state after concurrent writes. Those requirements need dedicated topology-specific tests.

### Tests Should Not Depend on an Internal Index Key Format

A good assertion:

~~~java
assertThat(repository.findByCity("DANANG"))
    .extracting(Customer::getId)
    .contains(id);
~~~

An overly implementation-coupled assertion:

~~~java
// Do not force internal indexes to always use this exact key name.
assertThat(redis.opsForSet()
    .members("customers:city:DANANG"))
    .contains(id);
~~~

Testing repository queries via their contract remains stable if framework versions change internal index structures. CLI and key layouts are still useful for debugging, without turning them into an application API.

## 15. Testing Expiration Without Equating It to Index Cleanup

To test actual TTL, you can save an entity with a short lifetime:

~~~java
Customer shortLived = new Customer(
    UUID.randomUUID().toString(),
    "Temporary Customer",
    "temporary@example.com",
    "ACTIVE",
    "HANOI",
    2L
);

Customer saved = repository.save(shortLived);
~~~

Then use bounded polling to wait until the entity no longer exists:

~~~java
import static org.awaitility.Awaitility.await;

await()
    .atMost(Duration.ofSeconds(10))
    .pollInterval(Duration.ofMillis(100))
    .untilAsserted(() ->
        assertThat(repository.findById(saved.getId()))
            .isEmpty()
    );
~~~

The example uses Awaitility in tests; if your project lacks that dependency, add an appropriate testing library or use another polling mechanism. Do not infer exact Redis expiration timing from a single `Thread.sleep(2000)`.

Verifying **entity expiration** is one goal; verifying **secondary index cleanup after expiration** is another. If the keyspace notification listener is not configured, disconnects, or the app shuts down when keys expire, some index references may remain. Cleanup tests must explicitly declare the required server and listener configuration as well as conditional wait timeouts, rather than assuming every environment behaves identically.

## 16. Extended Practice: Locking Status and Changing Email

To better understand the index lifecycle, add two operations:

**Exercise A — Lock a customer.**

1. Create a customer with `status=ACTIVE`, `city=HANOI`.
2. Verify the customer appears in `findByStatus("ACTIVE")`.
3. Call `service.changeStatus(id, "LOCKED")`.
4. Verify the ID disappears from `ACTIVE` results and appears in `LOCKED`.
5. Delete the customer and verify neither query returns the ID.

**Exercise B — Change normalized email.**

1. Create a customer with `emailNormalized=old@example.com`.
2. Add a service method to change email after validation.
3. Call `repository.save` after modifying the property.
4. Verify `findByEmailNormalized("old@example.com")` no longer contains the ID.
5. Verify `findByEmailNormalized("new@example.com")` contains the ID.
6. Create another customer with the new email and observe that the index can hold **two IDs**; this is not a Redis unique constraint bug, because `@Indexed` does not enforce uniqueness.

When updating multiple fields at once, write tests for queries on each individual field and field combinations to catch data/index inconsistencies.

### Exercise C — Observe Secondary Index Overhead

Create a moderately sized test dataset and measure:

- Redis key count before and after enabling one more `@Indexed`.
- Memory consumed by entity Hashes and related index Sets.
- `repository.save` latency when an entity has 1 index vs 3 indexes.
- `findByStatus` latency when 10, 1,000, or 10,000 IDs share the same status.
- Number of entities that must be deserialized to return one query result.
- Load increase when many entities change status continuously.

Do not extrapolate results from 10 entities to millions of entities; also do not enable new indexes in production without migration/backfill and memory assessment.

## 17. Common Pitfalls When Using Redis Repository

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| `findByStatus` finds no entities | `status` field missing `@Indexed`, unnormalized value, or data created before index deployment | Check annotations, data state, and reindex plan |
| `findById` works but `findByCity` fails | Hash exists but secondary index is missing or incorrect | Verify whether writes went through the repository; check index metadata |
| Updated field with `HSET` but query returns old result | Modifying Hash directly leaves index un-updated by repository | Route changes through repository or consistent index maintenance |
| Same email appears in two entities | `@Indexed` has no unique constraint | Enforce uniqueness at source of truth or via atomic allocation |
| Querying `hanoi` does not find `HANOI` | Case-normalization mismatch | Normalize on both write and query paths |
| Entity disappears after a while | `@TimeToLive` expired the key | Check `ttlSeconds`, Redis TTL, entity expiration policy |
| Hash expired by TTL but index still holds ID | Notification/cleanup missed or not enabled | Check Redis keyspace notifications, listener, repair process |
| `save` succeeds but other workflow steps fail | Redis write is not a transaction with DB or HTTP | Design idempotency/transaction/outbox per requirements |
| Complex derived query unsupported | Redis Repository lacks full JPA capabilities | Use indexed fields and supported query APIs; pick another datastore when fitting |
| Querying `ACTIVE` is very slow | Index has too many members, loading too many entities | Limit results, optimize read model, reconsider query structure |
| Redis memory grows after enabling indexes | Each index adds Sets/metadata, possibly shadow copies with TTL | Measure memory, cardinality, write cost, and TTL |
| After upgrading app version, query results differ | Mapping, schema, or normalization changes | Migrate and run integration tests with representative data |
| Repository bean not created | Wrong package scan or repository auto-configuration not enabled properly | Check `@EnableRedisRepositories` and Spring Boot configuration |
| `WRONGTYPE` on entity key | Key is being used as another Redis type | Check namespaces and writers; do not mix Redis String/Hash |
| Redis connection or timeout errors | Redis down, DNS/port/ACL/TLS, failover, or overloaded client | Diagnose connectivity and topology, retry per semantics, do not treat as not-found |
| API exposes fields that should not be returned | Returning domain entity directly with email/metadata | Use response DTOs per authorization policy |
| Stale data appears after failover | Asynchronous replication or replica read lag | Evaluate durability, consistency, and source-of-truth boundaries |
| Multiple apps write same keyspace with different rules | Two writers do not follow the same schema/index | Separate namespaces/ownership, use a single consistent write path |

### "Repository Not Found" Error vs "Customer Not Found"

If Spring reports it cannot inject `CustomerRepository`, that is a **wiring error** during application context startup. Check package scanning, annotations, and dependencies.

If `repository.findById(id)` returns `Optional.empty()`, that can be a **normal business outcome** because the ID does not exist or the key expired. If the method throws an exception because Redis cannot be reached, that is an **infrastructure error** and must not be turned into empty to return HTTP 404.

A system with good logging/metrics should distinguish these three cases right at the service/API layer.

## 18. Optimizing Queries and Operating Indexes

### 18.1. Monitoring Redis and the Application

Useful metrics:

| Category | Metrics to Observe | Explanation |
| --- | --- | --- |
| Redis memory | `used_memory`, key count, fragmentation | Are indexes and metadata increasing memory? |
| Redis keyspace | Expired/evicted keys | Are many entities removed due to TTL or eviction? |
| Queries | Latency p50/p95/p99 per derived query | Does field query latency grow with cardinality? |
| Save/delete | Throughput, error rate, latency | Index maintenance overhead on writes |
| Index results | Result count and IDs failing to load entities | Sign of indexes referencing missing Hashes |
| App/JVM | Heap, GC, allocations, request concurrency | Is deserializing large lists causing overload? |
| Listener | Pub/Sub key expiration connection status | Are cleanup/index events interrupted? |
| Failures | Redis timeouts, reconnects, schema errors | Distinguish infrastructure vs data errors |

Example Redis CLI commands for observation in authorized environments:

~~~bash
redis-cli -h 127.0.0.1 -p 6379 INFO keyspace
redis-cli -h 127.0.0.1 -p 6379 INFO memory
redis-cli -h 127.0.0.1 -p 6379 INFO stats
redis-cli -h 127.0.0.1 -p 6379 INFO commandstats
redis-cli -h 127.0.0.1 -p 6379 SLOWLOG GET 10
~~~

Do not run `KEYS customers:*` as a routine statistics operation on large production Redis instances. `SCAN` is less blocking and suitable for controlled administrative work, though it does not produce a strictly consistent snapshot if data changes during the scan.

### 18.2. Indexes Have Write Costs

Placing `@Indexed` on three entity fields enables equality queries, but saves must maintain the corresponding Sets. Under high update traffic, constantly changing indexed values increases Redis command counts, memory usage, and latency.

Evaluate based on actual workloads:

~~~text
Workload A: 95% read by ID, 5% search by status
  -> Is a status index needed? What is the actual query volume?

Workload B: 50% status updates, 50% findByStatus
  -> Is maintenance cost worth the query benefit?

Workload C: 90% findByEmailNormalized, very rare email updates
  -> Email index can be useful, but remember separate uniqueness requirements.
~~~

There is no universal rule saying "three fields is just right". Selectivity, cardinality, entity count, read/write ratio, TTL, and SLOs determine which indexes are worth keeping.

### 18.3. New Indexes Do Not Automatically Cover Previously Saved Data

Suppose the application already stored 100,000 customers before `city` had `@Indexed`. After deploying, adding the annotation to the field does not mean all old Hashes **immediately** have full secondary indexes as if they were saved under the new mapping.

For data that must be queried by the new index, plan a **backfill/reindex**:

1. Identify the managed entity set and reliable source of truth.
2. Normalize fields per the new schema.
3. In a test environment, build a mechanism to re-save through the repository or a well-designed migration process.
4. Throttle batch size/concurrency to avoid overloading Redis.
5. Measure additional index memory and query latency.
6. Reconcile a sample set: verify ID lookups and index queries return matching results.
7. Support rollback or namespace switching if the migration fails.

Do not assume a bulk `save` job in production is always safe: under concurrent updates, reindexing and business writes can contend. For critical data, plan downtime/versioning or proper write coordination.

### 18.4. Index Cleanup and Periodic Reconciliation

If repositories manage short-TTL entities, keyspace notifications can be lost during Redis/application disconnects. For large systems, proactively design observability policies:

- Count index members without corresponding entities on sampling checks.
- Measure expired entity rates and events received by listeners if metrics are available.
- Maintain a procedure to rebuild indexes from an authoritative data source when drift is detected.
- Do not repair all indexes using an ad-hoc unbounded, unthrottled script.
- For critical keys, consider not relying solely on non-durable expiration events for correctness.

If secondary indexes serve primary business search and stale references are unacceptable, assess whether Redis Repository plus keyspace Pub/Sub meets consistency needs. A relational or search index with transactional lifecycle management may be a better choice.

## 19. Separating Responsibilities Between Repository, Template, and Primary Data Source

In a Spring Data Redis application, both `RedisRepository` and `RedisTemplate` have distinct roles:

| Component | Best Used When | Notes |
| --- | --- | --- |
| `CrudRepository` with `@RedisHash` | Entity CRUD by ID, a few secondary index queries | Mapping/metadata/indexes managed by Spring Data Redis |
| `StringRedisTemplate` | Direct String commands, counters, simple caches | Does not auto-update Repository secondary indexes |
| `RedisTemplate<K,V>` | Redis structures like Hash/Set/List/ZSet, scripts, pipelines | Needs clear serializers, key conventions, and semantics |
| Reactive Redis APIs | Non-blocking flows using `Mono`/`Flux` | Not equivalent by default to blocking repositories |
| Database with transactions/unique constraints | Data source needing strong business invariants | Redis can hold read models/caches |
| Search engine/Redis Query Engine | Full-text search, advanced sorting/filtering | Does not appear automatically by adding `@Indexed` |

### Avoid Ambiguous Data Ownership

An error-prone architecture:

~~~text
Service A → CustomerRepository.save(...)
Service B → StringRedisTemplate.opsForHash().put(...)
Batch C   → RESTORE key with old payload
             |
             v
   Same keyspace customers:*
             |
             v
     Hashes and indexes drift
~~~

A more manageable architecture:

~~~text
                    Business service
                          |
                          v
                CustomerRepository
                          |
              +-----------+-----------+
              |                       |
              v                       v
        Entity Hash               Index metadata
              |                       |
              +-----------+-----------+
                          |
                          v
                    Redis storage
~~~

If there are multiple producers, they must share the same schema, namespace, serializer, and index maintenance conventions; otherwise, isolate keyspaces or designate a single responsible writer service.

## 20. Summary of Self-Practice Roadmap

To reproduce the lesson in sequence:

1. Create a Spring Boot project with `spring-boot-starter-data-redis` and a standalone development Redis.
2. Declare `Customer` with `@RedisHash("customers")`, `@Id`, three `@Indexed` fields, and `@TimeToLive`.
3. Define `CustomerRepository extends CrudRepository<Customer, String>`.
4. Enable Redis repository scanning, configure the connection, and start the application.
5. Call `CustomerService.create(...)` to save entities.
6. Read entities with `findById`; search using `findByStatus`, `findByCity`, and `findByStatusAndCity`.
7. Change city/status by updating the entity and calling `repository.save`; verify old/new index queries.
8. Delete an entity via the repository and verify it cannot be found by ID or index.
9. Inspect Hashes, index Sets, and TTLs using Redis CLI in the test environment.
10. Run integration tests with an isolated Redis, UUID keys, and proper cleanup.
11. Test a short-TTL entity, distinguishing Redis key expiration from notification-based index cleanup.
12. Evaluate overhead as cardinality, index count, entity count, and write concurrency grow.

### Observations to Confirm

| Action | Expected Observation |
| --- | --- |
| Save new customer | Entity readable by ID and index queries |
| Find `ACTIVE` in `HANOI` | Returns matching customers, not all customers |
| Change `city` | Old city query drops the ID; new city query includes the ID |
| Change `status` | Old/new status queries update accordingly |
| Delete entity | `findById` is empty and index queries do not include the ID |
| Positive TTL | Redis has an expiration time on the entity key |
| Entity expires | `findById` eventually returns empty; index cleanup depends on events/config |
| Two customers with same email | `@Indexed` can still return both entities; not a unique index |
| Direct Hash write | No guarantee indexes are updated by the repository |

## 21. Summary

**Redis Repository lets you manage entities in Redis using the familiar Spring Data model**, while **secondary indexes** help find entities by fields other than ID. In this exercise, the core pieces are:

- `@RedisHash` to map entities onto Redis Hashes.
- `@Id` for identification and key-based access.
- `@Indexed` to maintain secondary indexes for queryable attributes.
- `CrudRepository` to create, read, update, and delete entities.
- Derived queries such as `findByStatus`, `findByCity`, and `findByStatusAndCity`.
- `@TimeToLive` to apply expiration when business rules require it.
- Testcontainers to verify real Redis behavior rather than only mocking the repository.

Remember that **secondary indexes are auxiliary data structures with maintenance costs**, not unique constraints or general-purpose search engines. Direct Hash writes can desynchronize indexes; TTL expiration requires attention to keyspace notifications; save/update operations have atomicity and concurrency limits; and queries matching many IDs can still consume significant resources.

When used within its proper scope—small entities, primary access by ID, a few known equality queries, normalized data, and clear ownership—Spring Data Redis Repository is a convenient tool. When strict uniqueness, complex transactions, full-text search, or large-scale sorting/pagination are required, supplement or replace it with a specialized data model aligned with your application's consistency and performance requirements.

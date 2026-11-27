# Declaring spring-boot-starter-data-mongodb-reactive

## 1. Why Do You Need a Dedicated Starter for Reactive MongoDB?

An order service receives many concurrent requests to read order status, query order history, and update orders. If each query uses the synchronous MongoDB Java driver, the calling thread may have to wait for I/O. In a system designed end-to-end with Reactive Streams, Spring Data MongoDB provides an asynchronous data access path that represents results as `Mono<T>` or `Flux<T>`, using the **MongoDB Reactive Streams driver** instead of the synchronous blocking driver.

The dependency to declare is:

```text
org.springframework.boot:spring-boot-starter-data-mongodb-reactive
```

This starter is the **starting point** for reactive persistence on Spring Boot. It helps auto-configure the reactive MongoDB client, mapping, and repository/template beans when the corresponding conditions are met. It does **not** automatically make every piece of application code non-blocking, does not create a REST API on its own, and does not replace proper query and index design.

This lesson belongs to the **Reactive access** chapter of the **SPRING_DATA_MONGODB** module. The module teaches how to use Spring Data MongoDB to connect, map documents, and operate on MongoDB via `MongoTemplate` or repositories, as well as design queries, aggregations, indexes, transactions, reactive access, testing, and data performance diagnostics.

After this lesson, you will be able to:

1. Add `spring-boot-starter-data-mongodb-reactive` properly for **Maven**, **Gradle Groovy DSL**, and **Gradle Kotlin DSL**.
2. Understand the relationship between the starter, Spring Data MongoDB, the Reactive Streams driver, and Reactor.
3. Distinguish URI properties between **Spring Boot 3.x** and **Spring Boot 4.x**.
4. Create an entity, `ReactiveMongoRepository`, `ReactiveMongoOperations`, and a service using `Mono`/`Flux`.
5. Know when `spring-boot-starter-webflux` is needed and why you should not mix the synchronous driver into the reactive path.
6. Configure connections safely, and inspect the dependency tree, auto-configuration, and startup failures.
7. Test against real MongoDB, and understand versions, transactions, indexes, and backpressure limits.

> Examples target Java 17+ and Spring Boot 3.x/4.x syntax. APIs may vary by specific version, especially property names, test starters, and auto-configuration. Pick **one** Spring Boot version line managed by your project, and do not mix 3.x and 4.x configuration snippets in the same application.

## 2. Architecture Overview After Declaring the Starter

```mermaid
flowchart LR
    A["HTTP Controller WebFlux (optional)"] --> B["Application Service"]
    B --> C["ReactiveMongoRepository"]
    B --> D["ReactiveMongoOperations"]
    C --> E["Spring Data Mapping + Converter"]
    D --> E
    E --> F["MongoDB Reactive Streams Driver"]
    F --> G["MongoDB Server / Replica Set"]
    G --> F
    F --> H["Reactive Streams Publisher"]
    H --> C
    H --> D
```

Role of each component:

| Component | Purpose | Must declare manually? |
| --- | --- | --- |
| `spring-boot-starter-data-mongodb-reactive` | Bundles dependencies and triggers appropriate auto-configuration | **Yes**, in the build file |
| Spring Data MongoDB | Document mapping, query DSL, repository infrastructure | Usually managed by the starter |
| MongoDB Reactive Streams driver | MongoDB I/O over Reactive Streams | Usually pulled in by the starter |
| Project Reactor | `Mono`/`Flux` to represent and compose publishers | Usually included via transitive dependencies |
| `ReactiveMongoTemplate` | Template-style reactive operations | Boot can auto-configure when conditions match |
| `ReactiveMongoRepository` | Repository interface with dynamic proxy implementation | You define the interface |
| `spring-boot-starter-webflux` | Reactive HTTP endpoints and web runtime | **Add only when WebFlux HTTP is needed** |
| MongoDB Server | Stores documents and executes queries | **Must have** a real server/test instance |

**Note:** A Spring Boot starter is a dependency library, not a MongoDB server. Adding the dependency and running the app does not install a production database. During development you can use local MongoDB, Docker, or a provisioned dev environment.

## 3. Choosing One Spring Boot Version as the Dependency Management Source

### 3.1. Rules for Using a BOM or Parent

Spring Boot manages a compatible set of versions for Spring Data, the MongoDB driver, and related libraries via dependency management.

When a project already uses the Spring Boot parent/BOM or equivalent Gradle dependency management, **do not hardcode a separate version number for the reactive MongoDB starter**:

```text
Chosen Spring Boot version
       ↓
Spring Boot dependency management
       ↓
spring-boot-starter-data-mongodb-reactive
       ↓
Spring Data MongoDB + reactive driver + compatible dependencies
```

Forcing the latest standalone driver version into an older project risks `NoSuchMethodError`, `ClassNotFoundException`, or codec errors due to an untested combination.

### 3.2. Spring Boot 3.x and 4.x

The same starter artifact is listed in official documentation for **Spring Boot 3.x and 4.x**, but there are important configuration changes:

| Item | Spring Boot 3.x | Spring Boot 4.x |
| --- | --- | --- |
| Main starter | `spring-boot-starter-data-mongodb-reactive` | **Same artifact** |
| MongoDB connection URI property | `spring.data.mongodb.uri` | `spring.mongodb.uri` |
| Auto index creation | `spring.data.mongodb.auto-index-creation` | Remains under `spring.data.mongodb.*` |
| Reactive repository type | `ReactiveMongoRepository` | `ReactiveMongoRepository` |
| Bean abstraction | `ReactiveMongoOperations` | `ReactiveMongoOperations` |
| Test dependencies | `spring-boot-starter-test`, `reactor-test`, and suitable test tools | Adds dedicated starter `spring-boot-starter-data-mongodb-reactive-test` |

Do not infer from this table that **every API and every auto-configuration package stays identical**. Before upgrading from Boot 3 to Boot 4, read the migration guide and verify the application against the actual dependency tree.

## 4. Declaring in Maven

### 4.1. Project Already Using Spring Boot Parent

Essential snippet in `pom.xml`:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-mongodb-reactive</artifactId>
    </dependency>
</dependencies>
```

When the Spring Boot parent manages versions, there is no need to add:

```xml
<!-- No need to pin the Mongo reactive starter version
     when versions are already managed by Spring Boot. -->
```

A minimal Maven skeleton for Boot 3.x (the version is **an illustrative pick from the Boot 3 line**, not a recommendation for all environments):

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="
           http://maven.apache.org/POM/4.0.0
           https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>reactive-orders</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-data-mongodb-reactive</artifactId>
        </dependency>

        <!-- Only needed if the app exposes HTTP Reactive APIs. -->
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
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

**Important:** `3.5.0` illustrates a version from the Boot 3 line; real projects must choose an organization-supported version, keep security patches up to date, and stay compatible with the Java/MongoDB server runtime. Do not treat this example as the “latest” version at all times.

### 4.2. Using Spring Boot 4.x

Keep the primary dependency:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-mongodb-reactive</artifactId>
</dependency>
```

However, use the **Spring Boot 4 parent/BOM**, verify a compatible Java runtime, and use the updated property names. If using the dedicated Boot 4 test starter:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-mongodb-reactive-test</artifactId>
    <scope>test</scope>
</dependency>
```

Do not copy the 3.x dependency list verbatim assuming every Boot 4 module and test starter is structured identically.

### 4.3. When a Project Does Not Inherit from Parent

Use the Spring Boot BOM inside `dependencyManagement` instead of hardcoding a standalone starter version:

```xml
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
```

This only covers dependency management; the Maven project still needs appropriate Java compiler/plugin and build configuration. Choose **one** consistent version-management mechanism.

## 5. Declaring with Gradle Groovy DSL

### 5.1. build.gradle

A Gradle project using the appropriate Spring Boot plugin:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.0'
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
    implementation 'org.springframework.boot:spring-boot-starter-data-mongodb-reactive'

    // Only if reactive HTTP is needed.
    implementation 'org.springframework.boot:spring-boot-starter-webflux'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

If the Gradle project already has `plugins` and dependency management, only add the **implementation line for reactive MongoDB** instead of copying a new build file and overwriting project settings.

### 5.2. Gradle Without the dependency-management Plugin

Some projects use Gradle's native platform/BOM support:

```groovy
dependencies {
    implementation platform(
        'org.springframework.boot:spring-boot-dependencies:3.5.0'
    )
    implementation 'org.springframework.boot:spring-boot-starter-data-mongodb-reactive'
}
```

Choose one plugin/platform strategy managed by your project. Avoid applying multiple competing BOMs with untracked version overrides.

## 6. Declaring with Gradle Kotlin DSL

### 6.1. build.gradle.kts

```kotlin
plugins {
    java
    id("org.springframework.boot") version "3.5.0"
    id("io.spring.dependency-management") version "1.1.7"
}

group = "com.example"
version = "0.0.1-SNAPSHOT"

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation(
        "org.springframework.boot:spring-boot-starter-data-mongodb-reactive"
    )
    implementation("org.springframework.boot:spring-boot-starter-webflux")

    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("io.projectreactor:reactor-test")
}

tasks.test {
    useJUnitPlatform()
}
```

For Kotlin projects using `kotlin("jvm")`, `kotlin("plugin.spring")`, and Kotlin data classes, add the corresponding Kotlin plugins and dependencies chosen by the project. The example above is **Gradle Kotlin DSL for Java code**, not a complete guide for a full Kotlin-language project.

### 6.2. Avoid Pinning a Custom Driver Version

Do not hastily add:

```groovy
// Avoid pinning a version outside the Boot BOM without a technical reason.
// implementation 'org.mongodb:mongodb-driver-reactivestreams:<custom-version>'
```

The starter already includes the reactive driver under dependency management. Only override it for tested compatibility/security reasons, and inspect the full dependency graph rather than tweaking one artifact arbitrarily.

## 7. Verifying Dependencies Were Pulled In

### 7.1. Maven Dependency Tree

```bash
./mvnw dependency:tree -Dincludes=org.springframework.boot:spring-boot-starter-data-mongodb-reactive
./mvnw dependency:tree -Dincludes=org.mongodb
```

On Windows, you can use `mvnw.cmd`; on Linux/macOS, use `./mvnw`. In this lesson, these commands are **instructions to run in a suitable project**, not commands already executed on the current workspace.

### 7.2. Gradle Dependency Graph

```bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency mongodb-driver-reactivestreams --configuration runtimeClasspath
```

Read the output to verify:

- The reactive starter is actually on the classpath.
- The MongoDB Reactive Streams driver resolves cleanly.
- Which Spring Boot line manages Spring Data MongoDB.
- Whether two driver versions or multiple unexpected BOM overrides are present.
- Whether the blocking driver was accidentally pulled in by another starter.

### 7.3. Key Classes Conceptually Required

| Class/abstraction | Related package or artifact |
| --- | --- |
| `ReactiveMongoRepository` | `org.springframework.data.mongodb.repository` |
| `ReactiveMongoOperations` | `org.springframework.data.mongodb.core` |
| `ReactiveMongoTemplate` | `org.springframework.data.mongodb.core` |
| `Mono` and `Flux` | `reactor.core.publisher` |
| Reactive driver `MongoClient` | `com.mongodb.reactivestreams.client` |
| Blocking driver `MongoClient` | `com.mongodb.client` |

**These two `MongoClient` types are not the same type.** If your code configures a client manually, importing the wrong one can prevent reactive auto-configuration from picking up the intended bean or cause parts of the code to run synchronously.

## 8. Configuring MongoDB Connection for Spring Boot 3.x

### 8.1. application.yml (Boot 3.x)

```yaml
spring:
  data:
    mongodb:
      uri: "${MONGODB_URI:mongodb://localhost:27017/reactive_orders}"
```

If the `MONGODB_URI` environment variable is set, Spring uses it; otherwise, the local example URI is used. **Do not use a local fallback in production if connecting to the wrong database is risky**. Usually you should require the environment variable explicitly under the production profile.

### 8.2. application.properties (Boot 3.x)

```properties
spring.data.mongodb.uri=${MONGODB_URI:mongodb://localhost:27017/reactive_orders}
```

Choose either YAML or properties according to project conventions; do not declare two different URIs and rely on override precedence.

### 8.3. Test URI with Authentication Database

A URI can carry replica set, user, database, authSource, and TLS settings:

```text
mongodb://app-user:<password>@mongo-1:27017,mongo-2:27017/reactive_orders?replicaSet=rs0&authSource=admin&tls=true
```

The string above is a **structural pattern** with no real credentials. If the password contains special URI characters, percent-encode it properly. Use a secret manager or environment injection, and never commit credentials to Git.

## 9. Configuring MongoDB Connection for Spring Boot 4.x

Starting in Spring Boot 4, many MongoDB connection properties changed their prefix from `spring.data.mongodb.*` to **`spring.mongodb.*`**. Do not copy Boot 3 configuration without checking the migration guide.

### 9.1. application.yml (Boot 4.x)

```yaml
spring:
  mongodb:
    uri: "${MONGODB_URI:mongodb://localhost:27017/reactive_orders}"
```

### 9.2. application.properties (Boot 4.x)

```properties
spring.mongodb.uri=${MONGODB_URI:mongodb://localhost:27017/reactive_orders}
```

### 9.3. Some Properties Remain Under spring.data.mongodb

Not **every** MongoDB property changed prefix:

```properties
# For example, mapping/index policy remains under Spring Data:
spring.data.mongodb.auto-index-creation=false
```

In production, index creation normally requires a controlled migration/index management process. Do not enable auto-index-creation just because the starter dependency was added; building indexes on large collections has operational cost.

### 9.4. Check the Exact Boot Version Instead of Guessing

If the URI property is not being applied, the application may try to connect to the local default. You should:

1. Confirm the actual resolved Spring Boot version.
2. Inspect the configuration binding/condition report in development.
3. Check the effective URI while **masking username/password** in logs.
4. Cross-reference property names against that Boot version's reference documentation.
5. Avoid adding both properties “just in case” without understanding precedence.

## 10. Security: Credentials, TLS, Network, and Timeouts

### 10.1. Keep Secrets Out of Repositories

Avoid:

```java
// Anti-pattern:
// MongoClients.create("mongodb://admin:password@db-host:27017/prod");
```

Configuration must come from sources with proper access control and rotation. CI/CD pipelines should not print intact connection URIs. Application accounts should only hold permissions needed for their collections and workloads.

### 10.2. MongoDB Atlas / mongodb+srv

A URI like:

```text
mongodb+srv://<user>:<password>@cluster.example.mongodb.net/reactive_orders?retryWrites=true&w=majority
```

requires working DNS SRV resolution, authorized network access, and appropriate TLS/CA configuration. For managed deployments, follow the provider's guidance on certificates and driver compatibility; do not disable TLS verification to bypass connection errors.

### 10.3. Timeouts and Retries Must Be Intentional

Connection/server selection timeouts differ from write concern timeouts and HTTP request timeouts. A timeout error does **not by default** prove an update was not applied; for writes with side effects, you need CAS/idempotency and reconciliation mechanisms.

Do not configure infinite retries on write `Mono`/`Flux` pipelines just to “increase availability.”

### 10.4. Reactive TLS and Event Loop

Per the Spring Boot 4 reference, the reactive MongoDB driver requires **Netty** for the corresponding TLS path; auto-configuration supports this when Netty is on the classpath and the factory has not been misconfigured. When constructing `MongoClient`/settings manually, verify the SSL/TLS provider with your actual driver/version instead of copying settings from the blocking driver.

## 11. Which Beans Does Spring Boot Create Automatically?

With the starter and proper configuration, Spring Boot can create:

- Reactive MongoDB client/connection infrastructure.
- Reactive database factory.
- MongoDB converter/mapping context.
- `ReactiveMongoTemplate` injectable via `ReactiveMongoOperations`.
- Reactive repository factory and implementations for discovered interfaces.

These beans are **conditional**: if you define a custom `MongoClient`/Factory/Template, auto-configuration may back off or change how beans are built. Auto-configuration policies and classes may also move packages between Boot 3 and Boot 4.

### 11.1. Injecting Beans via Constructor Injection

```java
package com.example.orders.persistence;

import org.springframework.stereotype.Component;
import org.springframework.data.mongodb.core.ReactiveMongoOperations;

@Component
public final class ReactiveMongoProbe {
    private final ReactiveMongoOperations mongo;

    public ReactiveMongoProbe(ReactiveMongoOperations mongo) {
        this.mongo = mongo;
    }
}
```

If Spring cannot inject `ReactiveMongoOperations`, first check the starter, version, URI, classpath, and auto-configuration conditions—do not temporarily wire a blocking `MongoTemplate` just to “make it run.”

### 11.2. No Need to Write @EnableReactiveMongoRepositories by Default

When repository interfaces reside under Boot's scanned packages and auto-config conditions hold, Boot activates reactive repositories automatically.

Only add:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.repository.config.EnableReactiveMongoRepositories;

@Configuration
@EnableReactiveMongoRepositories(
    basePackages = "com.example.orders.persistence"
)
class ReactiveRepositoryConfig {}
```

when you need to restrict repository scanning explicitly or are not using default auto-configuration. When configuring manually, verify you do not scan blocking repositories twice or mistakenly.

## 12. Creating Application Packages and Source Layout

A reference layout:

```text
src/main/java/com/example/orders/
├── ReactiveOrdersApplication.java
├── persistence/
│   ├── OrderDocument.java
│   ├── ReactiveOrderRepository.java
│   └── OrderMongoGateway.java
├── service/
│   └── OrderQueryService.java
└── api/
    └── OrderController.java
```

The classes in subsequent sections belong in **separate Java files**; do not merge all public classes/interfaces into a single file.

### 12.1. Main Application

```java
package com.example.orders;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ReactiveOrdersApplication {
    public static void main(String[] args) {
        SpringApplication.run(
            ReactiveOrdersApplication.class, args
        );
    }
}
```

Placing the main class in the root package `com.example.orders` lets Boot scan components and repositories in sub-packages in this illustrative structure. In a monorepo or modularized codebase, align component/repository scanning with the real layout.

## 13. Declaring a Domain Document for Reactive MongoDB

### 13.1. OrderDocument.java

```java
package com.example.orders.persistence;

import java.time.Instant;
import org.springframework.data.annotation.Version;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;
import org.springframework.data.mongodb.core.mapping.FieldType;
import org.springframework.data.mongodb.core.mapping.MongoId;

@Document(collection = "orders")
public record OrderDocument(
    @MongoId(FieldType.STRING) String id,
    String tenantId,
    String status,
    @Field("amount_vnd") long amountVnd,
    Instant createdAt,
    @Version Long version
) {}
```

Entities still use **Spring Data MongoDB** mapping annotations. There is no separate `@ReactiveDocument` annotation. Reactivity lives in the **driver/operations/publisher** and repository infrastructure, not because the document itself is “reactive.”

### 13.2. Field Mapping

| Java property | MongoDB BSON field |
| --- | --- |
| `id` | `_id` |
| `tenantId` | `tenantId` |
| `status` | `status` |
| `amountVnd` | `amount_vnd` |
| `createdAt` | `createdAt` |
| `version` | `version` |

`@MongoId(FieldType.STRING)` stores `_id` as a String to match the fixture; if the collection uses BSON `ObjectId`, adjust the ID mapping and converters accordingly. `@Version` supports optimistic locking on suitable Spring Data write paths, but **does not automatically guard every raw update**.

### 13.3. BSON Fixture

```javascript
db.orders.insertMany([
  {
    _id: "ord-101",
    tenantId: "tenant-a",
    status: "PAID",
    amount_vnd: NumberLong("150000"),
    createdAt: ISODate("2026-11-18T08:00:00Z"),
    version: NumberLong("1")
  },
  {
    _id: "ord-102",
    tenantId: "tenant-a",
    status: "PAID",
    amount_vnd: NumberLong("250000"),
    createdAt: ISODate("2026-11-19T08:00:00Z"),
    version: NumberLong("1")
  },
  {
    _id: "ord-103",
    tenantId: "tenant-a",
    status: "NEW",
    amount_vnd: NumberLong("99000"),
    createdAt: ISODate("2026-11-20T08:00:00Z"),
    version: NumberLong("1")
  },
  {
    _id: "ord-201",
    tenantId: "tenant-b",
    status: "PAID",
    amount_vnd: NumberLong("900000"),
    createdAt: ISODate("2026-11-20T09:00:00Z"),
    version: NumberLong("1")
  }
]);
```

Run fixtures only in a **resettable practice database**, never verbatim in production. An order from another tenant is included to verify the repository does not accidentally leak cross-tenant data.

## 14. Declaring ReactiveMongoRepository

### 14.1. Interface

```java
package com.example.orders.persistence;

import org.springframework.data.mongodb.repository.ReactiveMongoRepository;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public interface ReactiveOrderRepository
        extends ReactiveMongoRepository<OrderDocument, String> {

    Mono<OrderDocument> findByTenantIdAndId(
        String tenantId, String id
    );

    Flux<OrderDocument> findByTenantIdAndStatusOrderByCreatedAtDesc(
        String tenantId, String status
    );

    Mono<Long> countByTenantIdAndStatus(
        String tenantId, String status
    );
}
```

Spring Data generates the implementation from method names, domain mapping, and repository infrastructure. You do not need to write a `ReactiveOrderRepositoryImpl` class for these simple derived query methods.

### 14.2. Mono and Flux Express Cardinality

| Method | Return type | Meaning |
| --- | --- | --- |
| `findByTenantIdAndId` | `Mono<OrderDocument>` | 0 or 1 document |
| `findByTenantIdAndStatus...` | `Flux<OrderDocument>` | 0 to many documents |
| `countByTenantIdAndStatus` | `Mono<Long>` | A count value on success |
| `save(entity)` | `Mono<OrderDocument>` | Write result when subscribed |
| `deleteById(id)` | `Mono<Void>` | Completion/error |

`Mono<T>` can complete **empty** instead of emitting a null value. `Flux<T>` can emit zero items. Both can also emit an **error signal**; never turn all connection errors into an empty result.

### 14.3. Do Not Confuse Reactive and Imperative Repositories

```java
// Imperative:
// interface Orders extends MongoRepository<OrderDocument, String>
// List<OrderDocument> findByStatus(String status);

// Reactive:
// interface Orders extends ReactiveMongoRepository<OrderDocument, String>
// Flux<OrderDocument> findByStatus(String status);
```

Returning `Flux` from an imperative repository does not turn blocking driver calls into reactive I/O. Conversely, a reactive repository requires the Reactive Streams driver and proper reactive MongoDB connection infrastructure.

## 15. Services Compose and Return Publishers Instead of Subscribing

### 15.1. OrderQueryService.java

```java
package com.example.orders.service;

import com.example.orders.persistence.OrderDocument;
import com.example.orders.persistence.ReactiveOrderRepository;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Service
public final class OrderQueryService {
    private final ReactiveOrderRepository repository;

    public OrderQueryService(ReactiveOrderRepository repository) {
        this.repository = repository;
    }

    public Mono<OrderDocument> findOne(
        String authenticatedTenantId, String orderId
    ) {
        return repository.findByTenantIdAndId(
            authenticatedTenantId, orderId
        );
    }

    public Flux<OrderDocument> paidOrders(
        String authenticatedTenantId
    ) {
        return repository
            .findByTenantIdAndStatusOrderByCreatedAtDesc(
                authenticatedTenantId, "PAID"
            );
    }
}
```

The service **returns the publisher** to the caller instead of calling `subscribe()`. In WebFlux, the framework subscribes when handling the response; in a batch job, the caller/runner must explicitly manage the lifecycle.

### 15.2. Why Not Subscribe Inside a Service?

```java
// Anti-pattern: detaching execution from the request lifecycle.
// public void create(OrderDocument order) {
//     repository.save(order).subscribe();
// }
```

When calling `subscribe()` internally:

- The controller may return success before the DB write completes.
- Exceptions may not reach the caller or be mapped properly.
- Cancellation, transaction context, tracing, and authentication context can be lost.
- Tests struggle to verify write completion.

Replace with:

```java
public Mono<OrderDocument> create(OrderDocument order) {
    return repository.save(order);
}
```

Assume this method belongs to a service with a `repository` field. The caller receives `Mono<OrderDocument>` and composes further rather than detaching side effects via `subscribe()`.

## 16. When Do You Need to Add spring-boot-starter-webflux?

The **MongoDB reactive starter** provides a reactive database access path. It **does not turn the application into an HTTP server**. If you want to build REST endpoints on the WebFlux stack, add:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-webflux</artifactId>
</dependency>
```

Or in Gradle:

```groovy
implementation 'org.springframework.boot:spring-boot-starter-webflux'
```

If the application is only a background worker or consumer running reactive MongoDB, WebFlux is **not strictly required**. `Mono`/`Flux` and the reactive driver work without an HTTP server.

### 16.1. A Simple WebFlux Controller

```java
package com.example.orders.api;

import com.example.orders.persistence.OrderDocument;
import com.example.orders.service.OrderQueryService;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/orders")
public final class OrderController {
    private final OrderQueryService service;

    public OrderController(OrderQueryService service) {
        this.service = service;
    }

    @GetMapping("/{id}")
    public Mono<OrderDocument> findById(
        @PathVariable String id
    ) {
        // In a real app, derive tenant from principal/authorization,
        // never accept an unverified client-claimed tenant.
        String authenticatedTenantId = "tenant-a"; // test only

        return service.findOne(authenticatedTenantId, id)
            .switchIfEmpty(Mono.error(
                new ResponseStatusException(
                    HttpStatus.NOT_FOUND, "Order not found"
                )
            ));
    }

    @GetMapping
    public Flux<OrderDocument> paidOrders() {
        String authenticatedTenantId = "tenant-a"; // test only
        return service.paidOrders(authenticatedTenantId);
    }
}
```

**Warning:** `"tenant-a"` is hardcoded for illustration, **not an authentication mechanism**. In production, use the security context and enforce tenant/owner checks on queries. Returning the full `OrderDocument` from an API is also not always appropriate; usually map to a response DTO with whitelisted fields.

### 16.2. Do Not Mix spring-boot-starter-web with WebFlux Just to Get Mono

`spring-boot-starter-web` serves Spring MVC/Servlet. When both Web and WebFlux starters are present, Spring Boot follows rules to pick the web application type; having `Mono` does not guarantee running a reactive web server.

If the goal is end-to-end WebFlux, configure the web stack cleanly and avoid blocking MVC/JDBC/JPA dependencies on the hot request path. If an MVC app wants to call reactive MongoDB, design an explicit bridging and execution model; do not assume the entire request runs non-blocking just because a repository returns `Mono`.

## 17. ReactiveMongoOperations and ReactiveMongoTemplate

Repository methods are convenient for CRUD and derived queries; when you need complex `Criteria`, sorting, projections, aggregations, or bulk-like operations, use `ReactiveMongoOperations`.

### 17.1. Find Example with Query/Criteria

```java
package com.example.orders.persistence;

import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.ReactiveMongoOperations;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Flux;

@Component
public final class OrderMongoGateway {
    private final ReactiveMongoOperations mongo;

    public OrderMongoGateway(ReactiveMongoOperations mongo) {
        this.mongo = mongo;
    }

    public Flux<OrderDocument> latestPaid(
        String authenticatedTenantId, int pageSize
    ) {
        if (authenticatedTenantId == null
                || authenticatedTenantId.isBlank()
                || pageSize < 1 || pageSize > 100) {
            return Flux.error(
                new IllegalArgumentException("Invalid query")
            );
        }

        Query query = Query.query(
            Criteria.where("tenantId").is(authenticatedTenantId)
                .and("status").is("PAID")
        )
        .with(Sort.by(
            Sort.Order.desc("createdAt"),
            Sort.Order.desc("id")
        ))
        .limit(pageSize);

        return mongo.find(query, OrderDocument.class);
    }
}
```

`ReactiveMongoOperations` maps the Java property `id` to BSON `_id` in the right entity context. In `mongosh` or the raw driver, however, use physical BSON names. With `@Field("amount_vnd")`, remember to check field aliases when writing raw JSON pipelines.

### 17.2. Updates Requiring Acknowledgment

```java
import com.mongodb.client.result.UpdateResult;
import org.springframework.data.mongodb.core.query.Update;
import reactor.core.publisher.Mono;

public Mono<Boolean> markShipped(
    String tenantId, String id, long expectedVersion
) {
    Query query = Query.query(
        Criteria.where("id").is(id)
            .and("tenantId").is(tenantId)
            .and("status").is("READY_TO_SHIP")
            .and("version").is(expectedVersion)
    );
    Update update = new Update()
        .set("status", "SHIPPED")
        .inc("version", 1);

    return mongo.updateFirst(
        query, update, OrderDocument.class
    ).map(result -> {
        if (!result.wasAcknowledged()) {
            throw new IllegalStateException(
                "Write has no reliable acknowledgment"
            );
        }
        return result.getMatchedCount() == 1;
    });
}
```

Place this method in a component that already has `ReactiveMongoOperations mongo` and imports `Criteria` and `Query`. With `@Version`, write integration tests to verify the version increments **exactly once** instead of guessing how your current Spring Data version performs version augmentation.

## 18. Mono/Flux: Understanding Cold Publishers and Subscription

### 18.1. A Publisher Represents Work, Not an Already-Computed Result

```java
Mono<OrderDocument> pending =
    repository.findByTenantIdAndId(
        "tenant-a", "ord-101"
    );

// When pending is declared, nothing guarantees the query has run yet.
```

Repository publishers are normally **cold**: I/O is triggered when a subscriber registers. Each independent subscription can trigger a new query:

```java
Mono<OrderDocument> pending =
    repository.findByTenantIdAndId("tenant-a", "ord-101");

// Two subscriptions can trigger two I/O calls:
pending.subscribe();
pending.subscribe();
```

This snippet only illustrates behavior; calling `subscribe()` directly inside a service is **not** recommended.

### 18.2. Use Operators Instead of Extracting Values Synchronously

```java
Mono<String> statusText = repository
    .findByTenantIdAndId("tenant-a", "ord-101")
    .map(order -> "status=" + order.status())
    .defaultIfEmpty("not found");
```

`map` handles short synchronous transformations on an element; `flatMap` is used when the function returns another publisher:

```java
Mono<Long> countAfterLookup = repository
    .findByTenantIdAndId("tenant-a", "ord-101")
    .flatMap(order ->
        repository.countByTenantIdAndStatus(
            order.tenantId(), order.status()
        )
    );
```

Do not use `map(order -> repository.save(order))` if you expect the save to run: that logically produces `Mono<Mono<OrderDocument>>`, not a pipeline awaiting the side effect. Use `flatMap`.

### 18.3. Empty Differs from Error

```java
Mono<OrderDocument> result = repository
    .findByTenantIdAndId("tenant-a", "missing-id");
```

Not finding a document yields a **completion with no value**. Network, authorization, or decoding failures produce an **error signal**. Do not use `onErrorResume(e -> Mono.empty())` across all errors, as it turns database outages into “not found.”

### 18.4. Do Not Call block() on a Reactive Request Thread

```java
// Do not do this inside a reactive controller or service:
// OrderDocument order = repository.findById(id).block();
```

`block()` waits for the result and can stall the event loop, degrading concurrent I/O capacity. If integration with a blocking library is unavoidable, isolate it on a dedicated scheduler with deliberate concurrency limits; preferably, stick to non-blocking APIs.

## 19. Backpressure, Pagination, and Memory Control

### 19.1. Reactive Does Not Allow Unbounded Loading

`Flux<OrderDocument>` does not make MongoDB queries free. The driver still fetches batches, decodes BSON, executes sorts/filters, and maintains cursor state.

The following is dangerous on large collections:

```java
// Reads the whole collection and collects into a single RAM list:
// Mono<List<OrderDocument>> all = repository.findAll().collectList();
```

If there are millions of documents, `collectList()` can blow up the heap. When callers need a page, apply **limits at MongoDB** before streaming, such as `Query.limit(50)` or repository queries accepting `Pageable` where supported.

### 19.2. Backpressure Coordinates Demand, Not Indexes

In Reactive Streams, downstream can request elements according to demand, and driver/cursor batching interacts with that request. Still:

- A `$sort` without an index can still be a blocking stage **inside the MongoDB server**.
- `$group` over a large dataset still consumes server CPU and RAM.
- A `flatMap` with high concurrency can issue many concurrent queries.
- Backpressure does **not** fix a missing tenant filter or an unindexed schema.

### 19.3. Limiting Concurrency

Suppose you need to look up status for a list of IDs:

```java
Flux<OrderDocument> loaded = Flux
    .fromIterable(orderIds)
    .flatMap(id ->
        repository.findByTenantIdAndId(
            authenticatedTenantId, id
        ),
        8
    );
```

`orderIds` and `authenticatedTenantId` are validated inputs from the caller. `8` is an **illustrative concurrency limit**, not a universal optimum. If input ordering must be preserved, consider `concatMap` or an appropriate batch query API.

### 19.4. Deep Offsets and Keyset Pagination

For long scrollable lists, offset pagination becomes expensive as `skip` grows. Consider keyset pagination on `createdAt` and `_id` with a stable sort and compound index. Reactive repositories do not magically turn `skip(100000)` into keyset pagination; query design must match real semantics.

## 20. Indexes and Reactive MongoDB Performance

### 20.1. Index for the Sample Query

```javascript
db.orders.createIndex(
  { tenantId: 1, status: 1, createdAt: -1, _id: -1 },
  { name: "ix_orders_tenant_status_recent" }
);
```

This index is a candidate for:

```javascript
db.orders.find({
  tenantId: "tenant-a",
  status: "PAID"
})
  .sort({ createdAt: -1, _id: -1 })
  .limit(20)
  .explain("executionStats");
```

Inspect the actual plan, `IXSCAN`/`COLLSCAN`, docs/keys examined, and blocking sorts. Switching from the blocking driver to the reactive driver does **not** make the server pick better indexes or reduce aggregation cost.

### 20.2. Index Creation Belongs to Administrative Lifecycle

Never run `createIndex` on every HTTP request. Depending on version, you can use Spring Data `IndexOperations`/reactive index APIs, or migration tools as the source of truth. Review `spring.data.mongodb.auto-index-creation` under project policy: production usually requires approving disk/CPU impact and index build duration.

### 20.3. End-to-End Observability

| Layer | Metrics |
| --- | --- |
| HTTP/WebFlux | p50/p95/p99, error rate, active requests |
| Reactor chain | Subscriptions, cancellations, timeouts, retries, queueing |
| MongoDB driver | Connection pool/command latency, timeouts |
| MongoDB server | Query plans, docs examined, CPU/I/O, replication lag |
| Heap/GC | Allocations and memory pressure during collect/buffering |

Never assume “fewer threads” automatically equals faster queries. Reactive uses threads efficiently while waiting on I/O, but will not guarantee high throughput if the database is the bottleneck.

## 21. Reactive Writes, @Version, and Transactions

### 21.1. Reactive Repository Save

```java
Mono<OrderDocument> saved =
    repository.save(new OrderDocument(
        "ord-301",
        "tenant-a",
        "NEW",
        150000L,
        java.time.Instant.now(),
        null
    ));
```

This is a publisher. The actual write happens upon subscription, and the returned entity can reflect ID/version values managed by persistence mapping. Do not assume an initial wrapper version always starts at a single hardcoded constant; test against your exact Spring Data version.

### 21.2. Acknowledged Writes Are Needed to Detect Conflicts

When using `@Version`, Spring Data can detect stale writes on supported save paths, provided write concern is strong enough to **receive acknowledgment**. With unacknowledged writes, conflicts cannot be observed reliably. For critical commands, configure write concern according to durability SLAs and test conflict handling.

### 21.3. Reactive Transactions Require a Reactive Transaction Manager

Example configuration:

```java
package com.example.orders.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.ReactiveMongoDatabaseFactory;
import org.springframework.data.mongodb.ReactiveMongoTransactionManager;

@Configuration
public class ReactiveMongoTxConfig {
    @Bean
    ReactiveMongoTransactionManager reactiveMongoTransactionManager(
        ReactiveMongoDatabaseFactory factory
    ) {
        return new ReactiveMongoTransactionManager(factory);
    }
}
```

Multi-document transactions require a MongoDB topology supporting sessions and transactions (typically a replica set or sharded cluster meeting prerequisites). Do not run transaction demos against standalone MongoDB and assume commit/session semantics match production.

### 21.4. TransactionalOperator

```java
import org.springframework.transaction.ReactiveTransactionManager;
import org.springframework.transaction.reactive.TransactionalOperator;
import reactor.core.publisher.Mono;

public final class AtomicWorkflow {
    private final ReactiveOrderRepository orders;
    private final TransactionalOperator tx;

    public AtomicWorkflow(
        ReactiveOrderRepository orders,
        ReactiveTransactionManager txManager
    ) {
        this.orders = orders;
        this.tx = TransactionalOperator.create(txManager);
    }

    public Mono<OrderDocument> saveWithinTransaction(
        OrderDocument order
    ) {
        return orders.save(order).as(tx::transactional);
    }
}
```

A single-document `save` normally **does not require** a transaction. This snippet uses `TransactionalOperator` purely to illustrate the operator, not to recommend wrapping every write in a transaction. In real multi-step workflows, make sure all publishers stay **inside the transaction chain** and never call detached `subscribe()`.

## 22. Can the Reactive Starter and Imperative Starter Coexist?

An application can include both:

```text
spring-boot-starter-data-mongodb
spring-boot-starter-data-mongodb-reactive
```

However, these bring in **two distinct drivers and connection infrastructures**, not one connection pool behind two wrapper APIs. One uses `com.mongodb.client.MongoClient`, while the other uses `com.mongodb.reactivestreams.client.MongoClient`.

### 22.1. Practical Risks

- Ambiguous repository scanning if imperative and reactive interfaces share packages.
- Two separate clients, connection pools, and metrics consuming extra resources.
- Accidental bean injection confusion between `MongoOperations` and `ReactiveMongoOperations`.
- A reactive service invoking the blocking template and stalling the event loop.
- Connection, auth, or TLS settings drifting out of sync between the two setups.

### 22.2. When Mixing Makes Sense

During a migration, a legacy blocking batch job and a new reactive API can coexist if:

1. Both are necessary and ownership boundaries are clear.
2. Package and repository scanning do not overlap.
3. Both drivers have dedicated configurations and metrics.
4. No blocking database API is called on the reactive request path.
5. There is a cleanup plan to remove the unused dependency after migration.

If you only need reactive access, prefer **the single reactive starter** and avoid pulling in the imperative starter out of habit.

### 22.3. @EnableMongoRepositories vs @EnableReactiveMongoRepositories

`@EnableMongoRepositories` configures imperative repositories; `@EnableReactiveMongoRepositories` configures reactive repositories. Use the right annotation when controlling scanning manually, and check Boot auto-configuration before adding manual configuration.

## 23. Testing Reactor with StepVerifier

### 23.1. Adding reactor-test

Maven:

```xml
<dependency>
    <groupId>io.projectreactor</groupId>
    <artifactId>reactor-test</artifactId>
    <scope>test</scope>
</dependency>
```

Gradle:

```groovy
testImplementation 'io.projectreactor:reactor-test'
```

`StepVerifier` subscribes to a publisher and verifies emitted signals, completion, and errors.

### 23.2. Testing a Mono Without MongoDB

```java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class MonoContractTest {
    @Test
    void monoEmitsOneValueThenCompletes() {
        Mono<Integer> answer = Mono.just(21).map(x -> x * 2);

        StepVerifier.create(answer)
            .expectNext(42)
            .verifyComplete();
    }

    @Test
    void emptyMonoDoesNotEmitNull() {
        StepVerifier.create(Mono.<String>empty())
            .verifyComplete();
    }
}
```

These tests only verify the **Reactor operator contract**; they do not prove the reactive MongoDB connection works.

### 23.3. Testing Error Semantics

```java
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

Mono<String> failure = Mono.error(
    new IllegalStateException("Simulated failure")
);

StepVerifier.create(failure)
    .expectErrorMatches(ex ->
        ex instanceof IllegalStateException
            && ex.getMessage().contains("Simulated")
    )
    .verify();
```

Do not turn every error into empty just to make tests “pass”; errors should be preserved or properly mapped, especially for unauthorized access or database unavailability.

## 24. Integration Testing with Real MongoDB

### 24.1. Why Mocking Is Not Enough

Mocking `ReactiveOrderRepository` can test service mapping and operators, but it does not prove:

- Connection URI/TLS/auth settings are valid.
- Spring Boot creates `ReactiveMongoTemplate` and repository proxies.
- `@MongoId`, `@Field`, and `@Version` map accurately to BSON.
- Derived queries by tenant/status actually run on MongoDB.
- Sorting, indexes, counts, and transactions work as expected.

You need integration tests against real MongoDB or Testcontainers MongoDB with a representative version and topology.

### 24.2. Testcontainers Skeleton

An option for Java/Boot 3.x (Testcontainers dependency versions managed by Boot BOM/test setup):

```java
package com.example.orders;

import com.example.orders.persistence.OrderDocument;
import com.example.orders.persistence.ReactiveOrderRepository;
import java.time.Instant;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.MongoDBContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import reactor.test.StepVerifier;

@Testcontainers
@SpringBootTest
class ReactiveMongoIntegrationTest {

    @Container
    static MongoDBContainer mongodb =
        new MongoDBContainer("mongo:7.0");

    @DynamicPropertySource
    static void mongoProperties(DynamicPropertyRegistry registry) {
        // Spring Boot 3.x:
        registry.add(
            "spring.data.mongodb.uri",
            mongodb::getReplicaSetUrl
        );
        // For Spring Boot 4.x: use "spring.mongodb.uri".
    }

    @Autowired ReactiveOrderRepository repository;

    @Test
    void savesAndFindsByTenant() {
        OrderDocument sample = new OrderDocument(
            "test-reactive-001", "tenant-a", "PAID",
            120000L, Instant.parse("2026-11-20T00:00:00Z"),
            null
        );

        StepVerifier.create(
            repository.save(sample)
                .flatMap(saved ->
                    repository.findByTenantIdAndId(
                        "tenant-a", saved.id()
                    )
                )
        )
        .expectNextMatches(found ->
            found.id().equals("test-reactive-001")
                && found.amountVnd() == 120000L
        )
        .verifyComplete();
    }
}
```

This is an **illustrative skeleton** missing full build/test dependencies and cleanup. You must add Testcontainers MongoDB/JUnit integration matching your managed versions. If the test class runs multiple times against the same collection with fixed IDs, clean up test data or generate unique IDs. For Boot 4, check the dedicated test starter, JUnit/Testcontainers APIs, and renamed properties.

### 24.3. Testcontainers Dependencies for Maven

```xml
<!-- Example for a Testcontainers release providing these artifacts;
     let the Boot BOM manage versions where appropriate. -->
<dependency>
    <groupId>org.testcontainers</groupId>
    <artifactId>mongodb</artifactId>
    <scope>test</scope>
</dependency>
<dependency>
    <groupId>org.testcontainers</groupId>
    <artifactId>junit-jupiter</artifactId>
    <scope>test</scope>
</dependency>
```

Testcontainers 2.x changed module/artifact naming in some integrations; when using newer versions, verify artifact coordinates and class APIs against your managed version instead of copying blindly.

### 24.4. Testing Tenant Isolation

Seed documents for both `tenant-a` and `tenant-b` with the same status, then query:

```java
Flux<OrderDocument> paidA =
    repository.findByTenantIdAndStatusOrderByCreatedAtDesc(
        "tenant-a", "PAID"
    );

StepVerifier.create(paidA)
    .thenConsumeWhile(order ->
        order.tenantId().equals("tenant-a")
    )
    .verifyComplete();
```

This test checks that no cross-tenant elements are emitted; even better, seed expected IDs and assert the **exact count and IDs** to catch cases where the repository incorrectly returns empty. In real code, add a tie-breaker to sorts when timestamps can collide.

### 24.5. Reactive Transaction Tests

To test `ReactiveMongoTransactionManager`, use a MongoDB topology that supports transactions and ensure the test runs through a reactive transaction operator. A test on standalone MongoDB or with mocks does not verify multi-document commit/rollback.

## 25. Boot Startup: Checking That the App Actually Uses Reactive

### 25.1. Having the Starter Does Not Guarantee Connection Success

Spring Boot auto-configuration can create the client/template at startup without necessarily executing a full query immediately. An application starting up cleanly does not prove authentication, DNS SRV, TLS, connection pooling, or collection permissions work.

To verify:

1. Check the dependency graph for the right starter and driver.
2. Confirm environment properties bind properly.
3. Boot against a running dev/test MongoDB server.
4. Inject `ReactiveMongoOperations` or a repository.
5. Run a smoke query **with subscription and timeout**.
6. Inspect results/exceptions; never treat a newly created `Mono<?>` as proof of success.

### 25.2. Smoke Query Using ReactiveMongoOperations

```java
package com.example.orders.diagnostics;

import org.springframework.data.mongodb.core.ReactiveMongoOperations;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Mono;

@Component
public final class MongoSmokeProbe {
    private final ReactiveMongoOperations mongo;

    public MongoSmokeProbe(ReactiveMongoOperations mongo) {
        this.mongo = mongo;
    }

    public Mono<Boolean> canReadOrders() {
        // Ignores actual count; for illustration only.
        return mongo.collectionExists("orders")
            .timeout(java.time.Duration.ofSeconds(3));
    }
}
```

`collectionExists("orders")` is a metadata operation and may require appropriate privileges; `false` can also simply mean the collection has not been created yet, not a connection failure. In real applications, use proper readiness/health indicators and a smoke query matching the service account's privileges.

### 25.3. Health Checks and Metrics

Add Spring Boot Actuator if you need health/metrics:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
```

Activation conditions for MongoDB health contributors and management property names can differ between Boot 3 and Boot 4. Never expose sensitive actuator endpoints to the public internet; configure readiness/liveness probes and authentication per security policy.

### 25.4. Debugging Auto-Configuration

In dev environments, enable the condition evaluation report (for example, start the app with `--debug`) to inspect why reactive MongoDB auto-configuration beans were or were not created. Never print full environment secrets or raw connection URIs to logs or share them publicly.

## 26. Common Errors When Adding the Starter

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| `ReactiveMongoRepository` does not compile | Starter unresolved or dependency conflict | Inspect Maven/Gradle dependency graph |
| `ReactiveMongoOperations` bean missing | Auto-configuration condition unmet, bad custom config | Check condition report and reactive driver imports |
| Boot 4 connects to localhost MongoDB | Still using Boot 3 `spring.data.mongodb.uri` | Switch to `spring.mongodb.uri` |
| Boot 3 ignores URI | Using Boot 4 `spring.mongodb.uri` | Switch to `spring.data.mongodb.uri` |
| `ClassNotFoundException`/`NoSuchMethodError` | Driver/Spring Data override out of sync with BOM | Remove manual pins and align versions |
| Wrong `MongoClient` import | Imported `com.mongodb.client` instead of reactive driver | Use `com.mongodb.reactivestreams.client` |
| Repository bean not found | Wrong package scanning, interface not scanned | Place under root package, verify repository enabling |
| Conflicting repository factories | Blocking and reactive starters mixed without scoping | Review dependencies and scanning |
| Controller returns `Mono` but blocks | Calls `.block()` or blocking JDBC/HTTP in chain | Use non-blocking APIs, isolate blocking work if needed |
| API returns before save finishes | Calls `subscribe()` inside service and returns `void` | Return `Mono`/compose up to controller |
| Test writes nothing | Publisher created without subscribing | Use `StepVerifier` |
| `Mono.empty()` treated as DB error | Confusing empty completion with error | Use `switchIfEmpty` for not-found, separate error mapping |
| Cross-tenant query results | Forgot tenant filter | Use authorization context and tenant-scoped queries |
| `collectList()` causes OOM | Loads huge collection into heap | Limit queries, stream, paginate |
| `Flux` stays slow despite reactive | Missing index, blocking sort, or DB bottleneck | Run `explain`/add indexes, measure DB metrics |
| No HTTP endpoints | Added MongoDB starter without WebFlux starter | Add WebFlux if HTTP is needed |
| TLS handshake fails | Trust/CA/hostname/proxy/Netty config | Verify TLS and driver/provider setup |
| Authentication failed | Wrong `authSource`/username/password | Check URI/secret injection and privileges |
| Timeout retry writes twice | Missing idempotency | CAS/operation ID and reconciliation |
| Transaction not supported | Standalone topology or wrong transaction manager | Replica set and reactive transaction setup |
| `@Version` fails to detect conflict | Unacknowledged write concern or raw update without filter | Use acknowledged writes and test write paths |
| Memory errors with `flatMap` | Excessive fan-out concurrency | Bound concurrency and batch size |

### 26.1. Step-by-Step Diagnostic Flow

```text
1. Confirm Boot version and the reactive starter.
                         ↓
2. Check dependency tree; avoid pinning driver versions outside the BOM.
                         ↓
3. Verify the right URI property for Boot 3 vs Boot 4.
                         ↓
4. Check DNS/auth/TLS/network connectivity to MongoDB.
                         ↓
5. Verify ReactiveMongoOperations + repository beans.
                         ↓
6. Use StepVerifier to execute a real query.
                         ↓
7. Verify tenant filters, BSON mapping, and results/errors.
                         ↓
8. Inspect explain/indexes and latency/connection pool metrics.
                         ↓
9. Ensure no blocking calls or detached subscribe() calls exist.
```

## 27. Worked Practice Exercises

### Exercise 1 — Minimal Maven Dependency

**Prompt:** Add reactive Spring Data MongoDB to a Maven project using the Spring Boot parent.

**Solution:**

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-mongodb-reactive</artifactId>
</dependency>
```

Do not specify a separate version when the parent/BOM manages dependencies.

### Exercise 2 — Gradle Groovy and Kotlin DSL

**Prompt:** Write the dependency declaration in both DSLs.

**Solution:**

```groovy
implementation 'org.springframework.boot:spring-boot-starter-data-mongodb-reactive'
```

```kotlin
implementation("org.springframework.boot:spring-boot-starter-data-mongodb-reactive")
```

### Exercise 3 — Right Property for Boot 3

**Prompt:** Spring Boot 3.4 connects to a dev MongoDB on port 27017, database `training`.

**Solution:**

```properties
spring.data.mongodb.uri=mongodb://localhost:27017/training
```

Do not use Boot 4's new `spring.mongodb.uri` property on Boot 3.x.

### Exercise 4 — Right Property for Boot 4

**Prompt:** You upgrade to Spring Boot 4 but keep `spring.data.mongodb.uri`. What needs fixing?

**Solution:**

```properties
spring.mongodb.uri=mongodb://localhost:27017/training
```

Also check any other migrated MongoDB properties in the migration guide, while keeping in mind that certain Spring Data mapping/index options remain under `spring.data.mongodb.*`.

### Exercise 5 — Should You Add WebFlux?

**Prompt:** A batch job only reads MongoDB and processes a `Flux`, with no HTTP endpoints. Is `spring-boot-starter-webflux` required?

**Solution:** Not strictly. The reactive MongoDB starter is sufficient for reactive data access when auto-configuration applies. Only add WebFlux when reactive HTTP endpoints or web-specific features are needed.

### Exercise 6 — Reactive Repository or Blocking Repository?

**Prompt:** A service needs `findByTenantIdAndId` to return `Mono<OrderDocument>` without blocking threads.

**Solution:**

```java
public interface Orders
    extends ReactiveMongoRepository<OrderDocument, String> {

    Mono<OrderDocument> findByTenantIdAndId(
        String tenantId, String id
    );
}
```

You must use the reactive starter/driver. Changing only the return type on an imperative `MongoRepository` is insufficient.

### Exercise 7 — Why Services Should Not Call subscribe

**Prompt:** A developer writes `repository.save(order).subscribe(); return Mono.empty();`. What is wrong?

**Solution:** The DB write runs detached from request completion, errors, and cancellation, and may return success before the write completes. Return `repository.save(order)` directly or compose with operators so the caller/framework owns subscription.

### Exercise 8 — StepVerifier for an Empty Query

**Prompt:** An ID is not found for the tenant. What is the right signal?

**Solution:** `Mono.empty()` / empty completion when no document exists, not `Mono.just(null)`. Test:

```java
StepVerifier.create(Mono.<OrderDocument>empty())
    .verifyComplete();
```

Network/authorization failures should emit error signals instead of being converted to not-found.

### Exercise 9 — Slow Query Despite Using Flux

**Prompt:** Fetching the 50 newest orders via a reactive repository is still slow. Did switching to `Flux` optimize the database?

**Solution:** No. Inspect filters, indexes, and sorting: an index `{tenantId:1,status:1,createdAt:-1,_id:-1}` is a candidate. Run `explain("executionStats")`, avoid blocking sorts/scans, limit page size, and compare latencies.

### Exercise 10 — Missing ReactiveMongoOperations Bean

**Prompt:** A project has `spring-boot-starter-data-mongodb` without the reactive starter; injecting `ReactiveMongoOperations` fails.

**Solution:** Add `spring-boot-starter-data-mongodb-reactive`, verify the reactive driver, auto-configuration, and URI/connection settings. Do not substitute `MongoTemplate` in a reactive service.

### Exercise 11 — Auto Index Creation in Production

**Prompt:** A developer enables `spring.data.mongodb.auto-index-creation=true` to create all indexes at startup. Should this be the default?

**Solution:** No. You need an index management process suited for large data, build duration, privileges, and rollouts. Production typically manages indexes via migrations/DBA policies; ensure annotations do not recreate intentionally removed indexes.

### Exercise 12 — Building a Complete Integration Test

**Prompt:** How do you prove the reactive starter actually works, rather than merely compiles?

**Solution:** Spin up a MongoDB test container; configure the URI according to the Boot version; boot a Spring context containing `ReactiveOrderRepository`; use `StepVerifier` to subscribe to `save(...).flatMap(findByTenantIdAndId(...))`; assert ID/tenant/field mappings; clean up; and test error paths, transactions, or optimistic locking if used. An unsubscribed `Mono` or a mocked repository does not prove real connectivity.

## 28. Pre-Deployment Completion Checklist

| Item | Criterion |
| --- | --- |
| Starter artifact | Correct `spring-boot-starter-data-mongodb-reactive` |
| Dependency management | Uses Boot parent/BOM; no arbitrary Mongo driver pins |
| Build DSL | Valid Maven/Groovy/Kotlin syntax |
| Boot version | Confirmed 3.x vs 4.x |
| MongoDB URI | Boot 3 `spring.data.mongodb.uri`; Boot 4 `spring.mongodb.uri` |
| Secrets | URI/credentials kept out of source, logs redacted |
| TLS/CA | Verified for driver and deployment |
| Reactive driver | Uses `com.mongodb.reactivestreams.client` |
| Repository | `ReactiveMongoRepository` inside scanned packages |
| Template | Inject `ReactiveMongoOperations`, not blocking template |
| HTTP stack | Add WebFlux only when needed; do not mix with MVC accidentally |
| Mapping | `@Document`, ID, `@Field`, converters/BSON types verified |
| Tenant isolation | Tenant comes from auth and is included in filters |
| Execution | Services return Publishers; no fire-and-forget `subscribe` |
| Blocking | No `block()` on the event loop |
| Backpressure | No unbounded `collectList()` over whole collections |
| Concurrency | `flatMap` fan-out properly bounded |
| Query performance | Indexes, `explain`, sorting, and pagination evaluated |
| Index lifecycle | Clear auto-index/migration policy |
| Write concern/version | Acknowledgment and CAS tested |
| Transactions | Suitable reactive transaction manager and topology |
| Retries | No unconditional retry on side effects |
| Unit tests | `reactor-test` and `StepVerifier` |
| Integration tests | Real MongoDB/Testcontainers, URI matching Boot version |
| Operations | Health/metrics/readiness/latency monitored |
| QA | Follow domain QA process after implementation |

## 29. Summary and Reference Documentation

### 29.1. Summary

1. Declaring **`org.springframework.boot:spring-boot-starter-data-mongodb-reactive`** in Maven/Gradle is the core step to enable reactive MongoDB integration in Spring Boot.
2. The starter **does not create a web server**; add `spring-boot-starter-webflux` when HTTP reactive endpoints are needed.
3. **Boot 3.x** uses `spring.data.mongodb.uri`; **Boot 4.x** uses `spring.mongodb.uri`. Some Spring Data properties such as auto-index-creation keep the older prefix.
4. The reactive driver and blocking driver are **two different client types**; `ReactiveMongoRepository`/`ReactiveMongoOperations` use the reactive path.
5. `Mono` and `Flux` represent publishers, not completed I/O; **there must be a subscription**, normally managed by the framework or caller.
6. **Never `block()` or detach `subscribe()` lifecycles inside reactive services**, never load unbounded collections with `collectList()`, and never retry writes blindly.
7. Having the right dependency is **not enough**: you also need accurate BSON mapping, tenant filters, indexes, write concerns, transaction policies, monitoring, and integration tests against real MongoDB.

### 29.2. Official Reference Documentation by Version

- Spring Boot 3.x — [NoSQL / MongoDB](https://docs.spring.io/spring-boot/3.4/reference/data/nosql.html).
- Spring Boot 4.x — [NoSQL / MongoDB](https://docs.spring.io/spring-boot/4.0/reference/data/nosql.html).
- Spring Boot 4.x — [Build systems and starter list](https://docs.spring.io/spring-boot/4.0/reference/using/build-systems.html).
- Spring Boot — [Migration guide 4.0](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.0-Migration-Guide).
- Spring Data MongoDB — [Reactive MongoDB support](https://docs.spring.io/spring-data/mongodb/reference/mongodb/reactive-mongodb.html).
- Spring Data MongoDB — [Reactive repositories](https://docs.spring.io/spring-data/mongodb/reference/mongodb/repositories/repositories.html).
- Spring Data MongoDB — [Sessions and transactions](https://docs.spring.io/spring-data/mongodb/reference/mongodb/client-session-transactions.html).
- Project Reactor — [Reference guide](https://projectreactor.io/docs/core/release/reference/).
- Testcontainers — [MongoDB module](https://java.testcontainers.org/modules/databases/mongodb/).

**Conclusion:** Declaring the reactive starter is a small change in the build file, yet it introduces a persistence layer with a different execution model. To adopt Spring Data MongoDB reactive effectively, manage the exact Spring Boot version, use the proper Reactive Streams driver, write services around the publisher lifecycle, and verify the full system with tests and metrics before concluding the application is truly non-blocking.

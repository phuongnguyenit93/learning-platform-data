# Designing Business Invariants When Users Can Write Directly to Entities

This is the applied section of the Domain Model topic in Spring Data REST: designing entities so that business rules are still preserved when clients can write directly to REST resources. In Spring Data REST, an exported repository can automatically expose endpoints for clients to read, create, update, and delete entities. While this speeds up API development, HTTP requests can update entity properties directly through Spring Data REST's binding mechanism. If business rules only live in a service or controller that the write endpoint never calls, clients can create invalid data states.

This lesson focuses on protecting domain model invariants when entities are written directly via REST. As an example, we manage products with stock quantity and reserved quantity. The core rules are:

- Product price must not be negative.
- Stock quantity and reserved quantity must not be negative.
- Reserved quantity must not exceed stock quantity.
- SKU is system-generated and cannot be modified by clients.
- Reserving or releasing stock must follow the entity's business behavior.

We will apply multiple layers of defense: behavior inside the entity, full-state validation before repository save, Bean Validation, and database constraints. For operations with complex workflows or state transitions, we will move to command APIs calling an application service instead of allowing clients to mutate the relevant properties directly.

## 1. What Is a Business Invariant?

A business invariant is a condition that must always hold true for an object or aggregate throughout its lifecycle. An operation is valid only when both the state before and the state after the operation satisfy those conditions.

Invariants can be grouped as follows:

| Invariant Type | Example | Appropriate Check Location |
|---|---|---|
| Single-attribute | Non-negative price, non-blank name | Value object, controlled setter, Bean Validation |
| Multi-attribute | Reserved quantity does not exceed stock quantity | Entity or aggregate after receiving full data |
| Identity invariant | SKU cannot change after creation | Entity, JSON configuration, and database |
| State transition rule | A shipped order cannot revert to draft status | Business methods and application service |
| Cross-aggregate rule | Cannot sell beyond total stock across multiple warehouses | Application service, transaction, and appropriate synchronization |

For example, if a product has 10 units in stock and 3 units reserved, the available quantity for sale is 7. A state with 12 reserved out of 10 in stock is invalid, even though each individual number is non-negative.

## 2. Why Direct Entity Writes via Spring Data REST Require Attention

When a repository is exported, Spring Data REST can provide endpoints such as:

- Collection and item GET to read entities.
- POST to create entities.
- PUT or PATCH to update entities.
- DELETE to remove entities.
- Search endpoints corresponding to exported query methods.

For example, with ProductRepository, clients can send JSON to /api/products or /api/products/1. Spring Data REST translates the request into operations on the entity and repository.

General write flow:

1. Client sends JSON.
2. Spring Data REST and Jackson map request fields onto writable entity properties.
3. Spring Data REST publishes events before creation or saving.
4. Repository persists the entity; JPA and the database run persistence-layer checks.
5. Server returns the resource representation or an error.

The key point is that a property-updating request does not necessarily call business methods such as reserve(), approve(), or ship(). If rules are written only inside those methods, clients can bypass the rules by directly writing exported properties.

For instance, the entity has a reserve(5) method that checks remaining stock before reserving. Yet if the API allows clients to send reservedQuantity = 100 directly, reserve() is never invoked. Thus, we must validate the final state along the REST write path and decide explicitly which properties are directly writable.

## 3. Creating a Sample Application

The example uses Java 17, Spring Boot 3.5.x, Spring Data JPA, Spring Data REST, H2, and Bean Validation. Source structure:

~~~text
src
├── main
│   ├── java/com/example/invariants
│   │   ├── InvariantsApplication.java
│   │   ├── Product.java
│   │   ├── ProductRepository.java
│   │   ├── ProductRestEventHandler.java
│   │   └── ProductDataInitializer.java
│   └── resources/application.properties
└── test
    └── java/com/example/invariants/ProductInvariantTest.java
~~~

### 3.1. Maven Dependencies

Create a Maven project with the following dependencies. The Spring Boot parent manages compatible versions for the starters:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>spring-data-rest-invariants</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-data-jpa</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-data-rest</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-validation</artifactId>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <scope>runtime</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
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
~~~

Key dependencies:

- Spring Data JPA provides repositories and ORM integration.
- Spring Data REST exports repositories as a REST API.
- Spring Boot Starter Validation provides Jakarta Bean Validation and its implementation.
- H2 provides an in-memory database for the example.
- Spring Boot Starter Test provides JUnit and AssertJ.

### 3.2. Startup Class

~~~java
package com.example.invariants;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class InvariantsApplication {

    public static void main(String[] args) {
        SpringApplication.run(InvariantsApplication.class, args);
    }
}
~~~

### 3.3. Product Entity Containing Domain Rules

~~~java
package com.example.invariants;

import com.fasterxml.jackson.annotation.JsonProperty;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.PrePersist;
import jakarta.persistence.PreUpdate;
import jakarta.persistence.Table;
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

import java.math.BigDecimal;
import java.util.UUID;

@Entity
@Table(name = "products")
public class Product {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    @JsonProperty(access = JsonProperty.Access.READ_ONLY)
    private Long id;

    @Column(nullable = false, unique = true, updatable = false, length = 40)
    @JsonProperty(access = JsonProperty.Access.READ_ONLY)
    private String sku;

    @NotBlank
    @Column(nullable = false, length = 120)
    private String name;

    @NotNull
    @DecimalMin("0.00")
    @Column(nullable = false, precision = 12, scale = 2)
    private BigDecimal unitPrice;

    @Min(0)
    @Column(nullable = false)
    private int stockQuantity;

    @Min(0)
    @Column(nullable = false)
    private int reservedQuantity;

    protected Product() {
        // JPA requires a no-arg constructor.
    }

    public Product(
            String name,
            BigDecimal unitPrice,
            int stockQuantity,
            int reservedQuantity) {
        this.name = name;
        this.unitPrice = unitPrice;
        this.stockQuantity = stockQuantity;
        this.reservedQuantity = reservedQuantity;
        validateInvariants();
    }

    public Long getId() {
        return id;
    }

    public String getSku() {
        return sku;
    }

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public BigDecimal getUnitPrice() {
        return unitPrice;
    }

    public void setUnitPrice(BigDecimal unitPrice) {
        this.unitPrice = unitPrice;
    }

    public int getStockQuantity() {
        return stockQuantity;
    }

    public void setStockQuantity(int stockQuantity) {
        this.stockQuantity = stockQuantity;
    }

    public int getReservedQuantity() {
        return reservedQuantity;
    }

    public void setReservedQuantity(int reservedQuantity) {
        this.reservedQuantity = reservedQuantity;
    }

    public int getAvailableQuantity() {
        return stockQuantity - reservedQuantity;
    }

    public void reserve(int quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException("Reservation quantity must be greater than 0.");
        }
        if (reservedQuantity + quantity > stockQuantity) {
            throw new IllegalArgumentException("Not enough available stock.");
        }
        reservedQuantity += quantity;
    }

    public void release(int quantity) {
        if (quantity <= 0 || quantity > reservedQuantity) {
            throw new IllegalArgumentException("Invalid release quantity.");
        }
        reservedQuantity -= quantity;
    }

    void validateInvariants() {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("Product name must not be blank.");
        }
        if (unitPrice == null || unitPrice.signum() < 0) {
            throw new IllegalArgumentException("Unit price must be greater than or equal to 0.");
        }
        if (stockQuantity < 0 || reservedQuantity < 0) {
            throw new IllegalArgumentException("Quantities must not be negative.");
        }
        if (reservedQuantity > stockQuantity) {
            throw new IllegalArgumentException(
                    "Reserved quantity must not exceed stock quantity.");
        }
    }

    @PrePersist
    private void beforeInsert() {
        validateInvariants();
        if (sku == null) {
            sku = "PRD-" + UUID.randomUUID();
        }
    }

    @PreUpdate
    private void beforeUpdate() {
        validateInvariants();
    }
}
~~~

Notable points:

- ID and SKU have only getters, no setters. Jackson is configured with READ_ONLY to include both properties in responses while ignoring client-submitted values.
- SKU is generated before insert. A UUID is used to avoid depending on database ID ordering.
- Price, stock quantity, and reserved quantity have Bean Validation constraints for single-field conditions.
- reserve() and release() express business behavior. Internal operations should invoke these methods to preserve proper state transition rules.
- validateInvariants() checks the complete state, particularly the relationship between reservedQuantity and stockQuantity.
- JPA callbacks execute before insert/update to provide a final safeguard at the persistence layer.

The setters for stock and reserved quantity do not validate cross-field invariants immediately. The reason is that JSON may bind properties in arbitrary order; an intermediate state between two property assignments could be invalid even though the final state is valid. We validate cross-field invariants after the request is fully bound, inside the event handler in the next section.

### 3.4. Exported Repository

~~~java
package com.example.invariants;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.rest.core.annotation.RepositoryRestResource;

@RepositoryRestResource(path = "products")
public interface ProductRepository extends JpaRepository<Product, Long> {
}
~~~

This repository causes Spring Data REST to create a collection resource at /api/products and item resources at /api/products/{id}. Clients can send requests directly to these resources.

### 3.5. Validating State After Request Binding

~~~java
package com.example.invariants;

import org.springframework.data.rest.core.annotation.HandleBeforeCreate;
import org.springframework.data.rest.core.annotation.HandleBeforeSave;
import org.springframework.data.rest.core.annotation.RepositoryEventHandler;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ResponseStatusException;

@Component
@RepositoryEventHandler(Product.class)
public class ProductRestEventHandler {

    @HandleBeforeCreate
    public void beforeCreate(Product product) {
        validate(product);
    }

    @HandleBeforeSave
    public void beforeSave(Product product) {
        validate(product);
    }

    private void validate(Product product) {
        try {
            product.validateInvariants();
        } catch (IllegalArgumentException ex) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST,
                    ex.getMessage(),
                    ex);
        }
    }
}
~~~

This event handler is invoked before Spring Data REST creates or saves a Product. At that moment, request properties have already been bound onto the entity, so the handler can inspect the final state instead of checking intermediate states while binding individual properties.

If a client sends a reservedQuantity greater than stockQuantity, the handler rejects it before the repository saves and returns HTTP 400. The handler only checks state validity. It does not replace an application service for workflows requiring permission checks, audit logging, event publishing, or coordination across multiple aggregates.

JPA callbacks continue protecting the entity when data is persisted from another flow that does not go through Spring Data REST. Do not use callbacks to call other repositories or perform I/O operations; keep callbacks focused on simple checks.

### 3.6. Loading Seed Data

~~~java
package com.example.invariants;

import org.springframework.boot.CommandLineRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import java.math.BigDecimal;
import java.util.List;

@Configuration
public class ProductDataInitializer {

    @Bean
    CommandLineRunner seedProducts(ProductRepository repository) {
        return args -> {
            if (repository.count() == 0) {
                repository.saveAll(List.of(
                    new Product("Keyboard", new BigDecimal("1290000.00"), 20, 4),
                    new Product("Mouse", new BigDecimal("450000.00"), 50, 10)
                ));
            }
        };
    }
}
~~~

Seed data also goes through the constructor and invariant checks. For real applications, versioned migrations or seeding processes are usually more appropriate than CommandLineRunner.

### 3.7. H2 and Spring Data REST Configuration

Create application.properties:

~~~properties
spring.application.name=spring-data-rest-invariants

spring.datasource.url=jdbc:h2:mem:invariantsdb
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=

spring.jpa.hibernate.ddl-auto=create-drop
spring.jpa.show-sql=true

spring.h2.console.enabled=true
spring.h2.console.path=/h2-console

spring.data.rest.base-path=/api
~~~

H2 runs in memory, so data is lost when the application stops. ddl-auto=create-drop fits demos, not retaining production data. In real deployments, use a durable database and a migration tool such as Flyway or Liquibase.

## 4. Testing Invariants in the Entity

Create ProductInvariantTest.java:

~~~java
package com.example.invariants;

import org.junit.jupiter.api.Test;

import java.math.BigDecimal;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class ProductInvariantTest {

    @Test
    void availableQuantityIsStockMinusReserved() {
        Product product = new Product(
                "Keyboard",
                new BigDecimal("100.00"),
                10,
                3);

        assertThat(product.getAvailableQuantity()).isEqualTo(7);
    }

    @Test
    void cannotReserveMoreThanAvailableStock() {
        Product product = new Product(
                "Keyboard",
                new BigDecimal("100.00"),
                10,
                3);

        assertThatThrownBy(() -> product.reserve(8))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("Not enough available stock");
    }

    @Test
    void rejectsInvalidStateAfterDirectPropertyBinding() {
        Product product = new Product(
                "Keyboard",
                new BigDecimal("100.00"),
                10,
                3);

        // Simulate a request directly updating a property.
        product.setStockQuantity(2);

        assertThatThrownBy(product::validateInvariants)
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("must not exceed stock quantity");
    }
}
~~~

The third test simulates a REST binder calling a setter instead of reserve(). When validating the full entity after binding, the invariant violation is still caught. The event handler from the previous section runs this exact check before the repository saves.

Run the tests:

~~~bash
./mvnw test
~~~

On Windows PowerShell:

~~~powershell
.\mvnw.cmd test
~~~

## 5. Trying Direct Entity Writes via REST

Start the application:

~~~bash
./mvnw spring-boot:run
~~~

On Windows PowerShell:

~~~powershell
.\mvnw.cmd spring-boot:run
~~~

Read the product list:

~~~bash
curl -i http://localhost:8080/api/products
~~~

Create a valid product:

~~~bash
curl -i -X POST http://localhost:8080/api/products \
  -H "Content-Type: application/json" \
  -d '{"name":"Headphones","unitPrice":850000,"stockQuantity":10,"reservedQuantity":3}'
~~~

The client does not need to send id or sku. The server generates ID and SKU. Responses can show SKU for client reference, while submitted JSON cannot overwrite these two properties.

Try creating an invalid state:

~~~bash
curl -i -X POST http://localhost:8080/api/products \
  -H "Content-Type: application/json" \
  -d '{"name":"Speaker","unitPrice":1500000,"stockQuantity":5,"reservedQuantity":8}'
~~~

This request violates the rule that reservedQuantity must not exceed stockQuantity. The event handler rejects it before saving and returns HTTP 400.

You can also try PATCHing an existing product to reduce stock below the reserved quantity:

~~~bash
curl -i -X PATCH http://localhost:8080/api/products/1 \
  -H "Content-Type: application/json" \
  -d '{"stockQuantity":2}'
~~~

If the product currently has reservedQuantity greater than 2, the final state is invalid and the request is rejected.

Note: the ID in the example only illustrates the URL path. Actual IDs are generated by the database; retrieve the ID from the response or collection resource before calling PATCH.

## 6. Choosing the Right Protection Layer for Each Type of Rule

No single annotation solves every invariant. Place checks in the layer closest to the rule's meaning and add guards on write paths that might bypass that layer.

| Mechanism | Suitable For | Limitations |
|---|---|---|
| Entity constructors and methods | Creation rules, state changes, domain behavior | REST binding can call setters without invoking business methods |
| Bean Validation | Single-field conditions like non-blank, non-negative | Cross-field rules require class-level validators or dedicated checks |
| Spring Data REST event handler | Validating entities after request binding, before create/save | Does not inherently model multi-step workflows or compare prior state without loading old state explicitly |
| JPA lifecycle callbacks | Guards before insert/update from persistence flows | Should not contain service calls, I/O, or workflow logic |
| Database constraints | NOT NULL, UNIQUE, CHECK, foreign keys | Error messages are often less user-friendly; does not replace permission checks or domain workflows |
| Application service | Transactions, permissions, state transitions, coordinating multiple entities | Requires a command endpoint calling the service rather than opening all direct write paths |

A useful guideline: validate single attributes where they are created or modified; validate cross-attribute relationships once the complete state is assembled; enforce state transition rules inside domain behaviors; enforce multi-step workflows inside application services.

## 7. Which Properties Should Clients Be Allowed to Write?

Do not treat every entity field as user input. Classify fields before exporting:

- **Directly writable:** display name or description if editing them requires no special workflow.
- **Read-only:** ID, system-generated SKU, creation timestamp, creator, derived state.
- **Changed only via business behavior:** reserved quantity, approval status, balance, limits, payment status.
- **Never exposed:** internal data, security info, implementation or audit-control fields.

@JsonProperty(access = JsonProperty.Access.READ_ONLY) keeps a property in responses while ignoring values written from JSON. @JsonIgnore hides a property from representations if clients do not need to see it. @Column(updatable = false) prevents JPA from including the column in UPDATE statements; by itself, that annotation is not a JSON binding control mechanism. Combine mechanisms according to their purpose.

Spring Data REST also allows disabling export for a repository or specific methods. For instance, if you do not want to expose direct CRUD on a repository:

~~~java
@RepositoryRestResource(exported = false)
public interface ProductRepository extends JpaRepository<Product, Long> {
}
~~~

Then, the application can provide custom endpoints accepting command DTOs and calling an application service. This works well when nearly all write operations require business workflows.

## 8. When Are an Application Service and Command Endpoint Needed?

Event handlers are helpful for validating final state, but should not be turned into the place that executes every use case.

For example, reserving inventory might need to:

1. Verify the user has permission to place orders.
2. Read the product and check available stock.
3. Reserve quantity within a transaction.
4. Create a reservation record.
5. Record change history or emit a domain event.
6. Return a reservation code to the client.

This is a use case, not merely updating the reservedQuantity field. It can be structured as follows:

~~~java
@Service
public class ProductService {

    private final ProductRepository repository;

    public ProductService(ProductRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public void reserve(Long productId, int quantity) {
        Product product = repository.findById(productId)
                .orElseThrow(() -> new IllegalArgumentException(
                        "Product not found: " + productId));

        product.reserve(quantity);
    }
}
~~~

In this design, the command endpoint accepts productId and quantity and calls ProductService.reserve(), while the entity enforces its own invariants. If you do not want clients to bypass the use case via the REST repository, disable automatic export as shown in the previous section.

For rules involving multiple aggregates or concurrent requests, also consider transaction isolation, optimistic locking with @Version, appropriate locking, and database constraints. Reading stock and then writing back can suffer race conditions if two requests reserve stock nearly simultaneously. Java-level checks are necessary, but not sufficient for all concurrency issues.

## 9. Common Pitfalls

**Validating only in controllers or services**

If a repository is exported and clients write directly, requests can bypass that controller or service. Place invariants inside the entity and re-check them in event handlers, or disable export to force requests through application services.

**Relying solely on setters**

Individual field setters are insufficient for rules spanning multiple fields. For instance, stock quantity and reserved quantity can be assigned in different orders. Validate the final state after binding.

**Letting clients modify identifiers or internal status**

Omitting a setter is not always a complete API policy. Explicitly mark properties as read-only or hide them in JSON; verify real requests with HTTP tests. Do not treat @Column(updatable = false) as a substitute for API write permissions.

**Using JPA callbacks to execute use cases**

Callbacks fit simple persistence checks. Do not call other repositories, send emails, or invoke external systems from callbacks; those tasks belong in application services with proper transactions/outbox patterns.

**Passing single-request checks but failing under concurrency**

Two requests can read the same stock level and both pass validation before saving. Consider @Version, atomic updates, or database locks depending on data model and load.

**Exposing all repositories to unauthenticated users**

Spring Data REST generates many write endpoints automatically. Configure Spring Security, authentication, resource-level authorization, and HTTP method controls before releasing an API to production.

## 10. Design Checklist

Before exporting an entity via Spring Data REST, answer:

1. Which fields are clients allowed to create or update?
2. Which fields are read-only or server-generated?
3. Which conditions span multiple attributes?
4. Which state changes must pass through business methods?
5. Do event handlers validate the final state before create/save?
6. Do JPA and the database have suitable guards for other write flows?
7. Could rules be violated by two concurrent requests?
8. Should the repository export full CRUD, or are custom command endpoints needed?
9. Are write endpoints authenticated and authorized?
10. Are there tests for both valid operations and requests intentionally sending invalid states?

## 11. Conclusion

When Spring Data REST allows clients to write directly to entities, any invariant not enforced on that write path risks being bypassed. Put domain behavior in the entity, use Bean Validation for single-field constraints, check cross-field relationships after request binding, and keep JPA/database checks as additional safeguards.

For workflows with state transitions, authorization, audit history, or multi-aggregate coordination, use command endpoints backed by application services and consider disabling direct CRUD export. The goal is to ensure every write path passes through the required rules, whether the request originates from a REST API, batch job, or another internal flow.
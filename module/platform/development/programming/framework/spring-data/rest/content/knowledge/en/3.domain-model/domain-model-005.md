# Basic Attributes, Embedded Objects, and Entity Relationships

## Learning Objectives

After this lesson, you will be able to:

- Distinguish basic attributes, embedded value objects, and relationships between entities.
- Choose the right JPA mapping for each kind of data.
- Explain which data appears inline in JSON and which data Spring Data REST represents using HAL links.
- Design one-to-one, one-to-many, many-to-one, and many-to-many relationships.
- Use association resources to read and modify relationships over HTTP.
- Avoid pitfalls involving owning side, cascade, JSON cycles, lazy loading, and data leaks.

## 1. Classifying Attributes in a Domain Model

An entity typically holds many kinds of information. For example, an order has an order number, creation date, status, shipping address, and the customer placing the order. Even though all of them appear as fields in Java, they do not share the same meaning in the domain model.

With Jakarta Persistence, entity state can be classified into:

| Attribute Type | Example | Meaning |
|---|---|---|
| BASIC (basic attribute) | orderNumber, status, createdAt, totalAmount | Value belonging directly to the entity |
| EMBEDDED (embedded object) | shippingAddress, money, contactInfo | Group of values describing part of the entity's state, with no separate identity |
| ELEMENT_COLLECTION | tags, phoneNumbers, list of secondary codes | Collection of basic or embeddable values, not a collection of entities |
| ENTITY RELATIONSHIP | customer, items, assignedEmployee | Reference to another entity with its own identity |

This classification determines how JPA stores the data and how Spring Data REST represents the domain model over HTTP.

For example:

- orderNumber is a basic value, returned as a property in JSON.
- shippingAddress is a value object, usually returned as a nested JSON object inside the order.
- customer is another entity, so Spring Data REST typically generates a HAL link for clients to access the customer resource.
- items can be a relationship to OrderItem entities or an element collection, depending on the identity and business meaning of each item.

Do not decide based solely on whether data looks like a JSON object. Ask: does this object have an independent identity and lifecycle? Can it be referenced from multiple entities? Can users access or update it as an independent resource?

## 2. Basic Attributes

Basic attributes are values belonging directly to an entity that do not require another entity to represent them.

Common Java types include:

- Strings: String.
- Integers: int, long, Integer, Long.
- Decimals: BigDecimal, usually suitable for money and numbers requiring exact precision.
- Booleans: boolean, Boolean.
- Date/time: LocalDate, LocalDateTime, Instant, OffsetDateTime.
- Enums: status, business types, categories.
- UUID and other basic types supported by Jakarta Persistence.

Example:

```java
@Entity
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, unique = true, length = 40)
    private String orderNumber;

    @Column(nullable = false, precision = 15, scale = 2)
    private BigDecimal totalAmount;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 20)
    private OrderStatus status;

    private Instant createdAt;

    protected PurchaseOrder() {
    }
}
```

A few important notes:

- @Column(nullable = false) describes a column constraint in the schema; also use Bean Validation annotations such as @NotBlank, @NotNull, or @Positive when input validation at the application layer is needed.
- For money, use BigDecimal instead of double to avoid floating-point representation errors. Declare precision and scale matching business rules.
- For enums, @Enumerated(EnumType.STRING) stores the enum name. This is more readable and stable than ORDINAL, because reordering enum constants will not alter the meaning of existing data.
- Use Instant for absolute points in time or OffsetDateTime when preserving an offset is needed. Use LocalDate for calendar dates without time or time zones.
- @Column(name = "...") renames the database column; it does not automatically rename the JSON property. The JSON contract is determined by property names and Jackson configuration.

In Spring Data REST representations, basic attributes usually appear directly in the document:

```json
{
  "orderNumber": "PO-1001",
  "totalAmount": 1250000.00,
  "status": "DRAFT",
  "createdAt": "2026-11-11T07:30:00Z"
}
```

These are values of the order itself. They do not generate separate collection endpoints or association links.

## 3. Nested Objects and Value Objects with @Embeddable

### 3.1. When Should You Use an Embedded Object?

A value object groups related values into a meaningful concept in the domain model without needing an independent identity.

For example:

- An address consisting of street, city, postal code, and country.
- A date range consisting of start and end timestamps.
- Money consisting of amount and currency unit.
- Coordinates consisting of latitude and longitude.

An order's shipping address is usually part of the order's state. If there is no business requirement to manage addresses as standalone resources, creating an Address entity solely to group four fields can add unnecessary complexity.

In JPA:

- Annotate the value object class with @Embeddable.
- Annotate the field holding it in the entity with @Embedded.
- Fields of the embeddable are mapped into the owning entity's table.
- An embeddable has no primary key and no separate persistent identity.
- An embeddable belongs to its owning entity; do not share the same instance as an independent entity across multiple entities.

### 3.2. Address Example

File Address.java:

```java
package com.example.orders.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Embeddable;

@Embeddable
public class Address {

    @Column(nullable = false, length = 180)
    private String street;

    @Column(nullable = false, length = 100)
    private String city;

    @Column(length = 20)
    private String postalCode;

    @Column(nullable = false, length = 2)
    private String countryCode;

    protected Address() {
    }

    public Address(
            String street,
            String city,
            String postalCode,
            String countryCode) {
        this.street = street;
        this.city = city;
        this.postalCode = postalCode;
        this.countryCode = countryCode;
    }

    public String getStreet() {
        return street;
    }

    public void setStreet(String street) {
        this.street = street;
    }

    public String getCity() {
        return city;
    }

    public void setCity(String city) {
        this.city = city;
    }

    public String getPostalCode() {
        return postalCode;
    }

    public void setPostalCode(String postalCode) {
        this.postalCode = postalCode;
    }

    public String getCountryCode() {
        return countryCode;
    }

    public void setCountryCode(String countryCode) {
        this.countryCode = countryCode;
    }
}
```

File Customer.java using Address:

```java
package com.example.orders.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Embedded;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "customers")
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 120)
    private String fullName;

    @Column(nullable = false, unique = true, length = 180)
    private String email;

    @Embedded
    private Address address;

    protected Customer() {
    }

    public Customer(String fullName, String email, Address address) {
        this.fullName = fullName;
        this.email = email;
        this.address = address;
    }

    public Long getId() {
        return id;
    }

    public String getFullName() {
        return fullName;
    }

    public void setFullName(String fullName) {
        this.fullName = fullName;
    }

    public String getEmail() {
        return email;
    }

    public void setEmail(String email) {
        this.email = email;
    }

    public Address getAddress() {
        return address;
    }

    public void setAddress(Address address) {
        this.address = address;
    }
}
```

The customers table has columns corresponding to fullName, email, street, city, postalCode, and countryCode. There is no addresses table just because the code has an Address class.

### 3.3. JSON Representation of Embedded Objects

When Spring Data REST returns a customer, address is a nested object:

```json
{
  "fullName": "Nguyen An",
  "email": "an@example.com",
  "address": {
    "street": "12 Le Loi",
    "city": "Ho Chi Minh City",
    "postalCode": "700000",
    "countryCode": "VN"
  }
}
```

Clients send a matching nested object when creating or updating a customer. This is part of the customer's data; there is no need to call an /addresses endpoint to create an address separately.

This differs from entity relationships: a related entity has its own identity and repository, so Spring Data REST can publish links for clients to navigate to that resource.

### 3.4. Reusing an Embeddable Type Multiple Times

An entity can contain multiple fields of the same Address type, such as billingAddress and shippingAddress. In that case, the embeddable's fields must map to different columns. Use @AttributeOverride to specify column names:

```java
@Embedded
@AttributeOverrides({
    @AttributeOverride(
        name = "street",
        column = @Column(name = "billing_street")
    ),
    @AttributeOverride(
        name = "city",
        column = @Column(name = "billing_city")
    ),
    @AttributeOverride(
        name = "postalCode",
        column = @Column(name = "billing_postal_code")
    ),
    @AttributeOverride(
        name = "countryCode",
        column = @Column(name = "billing_country_code")
    )
})
private Address billingAddress;

@Embedded
@AttributeOverrides({
    @AttributeOverride(
        name = "street",
        column = @Column(name = "shipping_street")
    ),
    @AttributeOverride(
        name = "city",
        column = @Column(name = "shipping_city")
    ),
    @AttributeOverride(
        name = "postalCode",
        column = @Column(name = "shipping_postal_code")
    ),
    @AttributeOverride(
        name = "countryCode",
        column = @Column(name = "shipping_country_code")
    )
})
private Address shippingAddress;
```

The fields still belong to the owning entity; billingAddress and shippingAddress do not become two entities with separate IDs.

### 3.5. Collections of Basic Values or Embeddables

If an entity has multiple basic values or value objects where individual elements do not need separate identity, consider @ElementCollection.

For example:

```java
@ElementCollection
@CollectionTable(
    name = "customer_tags",
    joinColumns = @JoinColumn(name = "customer_id")
)
@Column(name = "tag")
private Set<String> tags = new LinkedHashSet<>();
```

@ElementCollection maps the collection to a collection table. If each element needs to be referenced independently, have its own state, or have an independent lifecycle, consider an entity instead of an element collection.

## 4. Relationships Between Entities

### 4.1. When Should an Object Be an Entity?

An object should be an entity when it has its own identity and is managed as an independent business object.

For example:

- A PurchaseOrder has an order code and its own lifecycle.
- A Customer can be referenced by many orders.
- A Product can appear in many orders.
- An Employee can be assigned to many tasks.

In JPA, entity relationships have four main forms:

| Annotation | Meaning | Example |
|---|---|---|
| @OneToOne | One entity links to at most one other entity | User and UserProfile |
| @ManyToOne | Many entities reference one entity | Many orders belong to one customer |
| @OneToMany | One entity links to many other entities | One customer has many orders |
| @ManyToMany | Many entities on both sides link many-to-many | Student and Course |

Relationships in the object model are mapped to foreign keys or join tables. Spring Data REST recognizes these associations and provides links/association resources when the relevant repositories are exported.

### 4.2. Many-to-One and One-to-Many Example

Suppose each order belongs to one customer, and a customer can have many orders.

Business relationship:

```text
Customer 1 ─────────── * PurchaseOrder
           one-to-many

PurchaseOrder * ───── 1 Customer
              many-to-one
```

In the database, the foreign key customer_id typically resides in the purchase_orders table.

File PurchaseOrder.java:

```java
package com.example.orders.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.Table;

@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, unique = true, length = 40)
    private String orderNumber;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 20)
    private OrderStatus status;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "customer_id", nullable = false)
    private Customer customer;

    protected PurchaseOrder() {
    }

    public PurchaseOrder(
            String orderNumber,
            OrderStatus status,
            Customer customer) {
        this.orderNumber = orderNumber;
        this.status = status;
        this.customer = customer;
    }

    public Long getId() {
        return id;
    }

    public String getOrderNumber() {
        return orderNumber;
    }

    public void setOrderNumber(String orderNumber) {
        this.orderNumber = orderNumber;
    }

    public OrderStatus getStatus() {
        return status;
    }

    public void setStatus(OrderStatus status) {
        this.status = status;
    }

    public Customer getCustomer() {
        return customer;
    }

    public void setCustomer(Customer customer) {
        this.customer = customer;
    }
}
```

File OrderStatus.java:

```java
package com.example.orders.domain;

public enum OrderStatus {
    DRAFT,
    CONFIRMED,
    SHIPPED,
    CANCELLED
}
```

Add the inverse side to Customer.java:

```java
@OneToMany(mappedBy = "customer")
private List<PurchaseOrder> orders = new ArrayList<>();

public List<PurchaseOrder> getOrders() {
    return orders;
}

public void addOrder(PurchaseOrder order) {
    orders.add(order);
    order.setCustomer(this);
}
```

Remember to add imports:

```java
import java.util.ArrayList;
import java.util.List;
import jakarta.persistence.OneToMany;
```

Explanation:

- PurchaseOrder.customer uses @ManyToOne and is the owning side in this example because it holds the customer_id foreign key.
- Customer.orders uses @OneToMany(mappedBy = "customer"). mappedBy points to the field name on the owning side, not the database column name.
- When modifying a relationship in Java code, update both sides of the bidirectional relationship. addOrder does this by adding the order to the collection and assigning customer on the order.
- FetchType.LAZY avoids loading the customer along with all orders in queries that do not need that relationship. Design queries and transactions to match how the application uses data.

### 4.3. One-to-One

Use @OneToOne when each side links to at most one object on the other side. For example, a user has a separate profile. Typically the database requires a foreign key with a unique constraint or a shared primary key strategy.

Do not use One-to-One merely because two objects often appear side by side in JSON. If the data has no separate identity and is only part of the user's state, @Embedded may be more appropriate.

### 4.4. Many-to-Many

Use @ManyToMany when many entities on side A can link to many entities on side B, and the link itself requires no separate business attributes. JPA typically maps this relationship using a join table.

For example, Student and Course can have a many-to-many relationship. If enrollment requires attributes such as enrolledAt, grade, status, or attemptNumber, model an intermediate entity such as Enrollment rather than keeping a plain @ManyToMany.

### 4.5. When a Relationship Needs to Become a Separate Entity

Suppose an order has many products. If each order line needs a quantity, price at purchase time, discount, and fulfillment status, OrderItem is an entity or child entity with its own business data:

```text
PurchaseOrder 1 ───── * OrderItem * ───── 1 Product

OrderItem:
- quantity
- unitPriceAtPurchase
- discount
- fulfillmentStatus
```

The relationship between order and product is now represented through OrderItem. This lets you store price history and details for each line that a List<Product> field cannot adequately express.

## 5. How Does Spring Data REST Represent Embedded Objects and Entity Relationships?

Spring Data REST uses HAL by default for JSON representations. HAL places links under the _links property. Clients read links to discover and navigate to related resources.

### 5.1. Basic Values and Embeddables Appear Inline in the Representation

Basic fields and value objects are serialized into the entity's representation. For example, a customer might look like:

```json
{
  "fullName": "Nguyen An",
  "email": "an@example.com",
  "address": {
    "street": "12 Le Loi",
    "city": "Ho Chi Minh City",
    "postalCode": "700000",
    "countryCode": "VN"
  },
  "_links": {
    "self": {
      "href": "http://localhost:8080/api/customers/1"
    },
    "orders": {
      "href": "http://localhost:8080/api/customers/1/orders"
    }
  }
}
```

In this example:

- fullName and email are basic attributes.
- address is an embedded object.
- orders is a relationship to PurchaseOrder entities, so it appears as a link.
- The orders link points to the customer's association resource.

### 5.2. Entity Relationships Appear as Links

An order can be returned as follows:

```json
{
  "orderNumber": "PO-1001",
  "status": "DRAFT",
  "_links": {
    "self": {
      "href": "http://localhost:8080/api/orders/1"
    },
    "customer": {
      "href": "http://localhost:8080/api/orders/1/customer"
    }
  }
}
```

The customer property does not need to contain the full customer object. Clients follow /api/orders/1/customer to inspect the relationship state, then follow the returned link to access the customer resource.

This representation avoids serializing the entire object graph every time an entity is read. Clients only fetch related resources when needed.

Note: _embedded in HAL holds resources embedded according to representation/projection rules. Do not infer that every JPA @Embedded is placed inside HAL _embedded; a standard JPA embeddable is an object property in the JSON body, whereas HAL _links represents links to other resources.

### 5.3. Association Resources

For each item resource, Spring Data REST can generate sub-resources for the entity's associations. Default paths and relation names are derived from property names; they can be customized with @RestResource.

For PurchaseOrder.customer, the default association resource has the form:

/api/orders/{orderId}/customer

For Customer.orders, the default association resource has the form:

/api/customers/{customerId}/orders

Association resources support:

| HTTP method | Used for | Details |
|---|---|---|
| GET | To-one or collection association | Reads relationship state |
| PUT | Binds resource URI(s) to relationship | Uses text/uri-list; for to-one send only a single URI |
| POST | Collection association | Adds a resource to the collection |
| DELETE | Unlinkable association | Removes the relationship; does not delete the target entity |

Example changing order 1's customer to customer 2:

```bash
curl -i -X PUT \
  -H "Content-Type: text/uri-list" \
  --data "http://localhost:8080/api/customers/2" \
  http://localhost:8080/api/orders/1/customer
```

The body is the URI of the customer to link, not a customer JSON object. If the association is required (optional = false), a DELETE request to unlink it may be rejected because the relationship cannot be null.

For a collection association, POST adds an existing resource to the collection:

```bash
curl -i -X POST \
  -H "Content-Type: text/uri-list" \
  --data "http://localhost:8080/api/orders/1" \
  http://localhost:8080/api/customers/2/orders
```

These operations only modify relationships according to application mappings and rules. They do not by themselves imply cascade remove, cascade persist, or other business rules.

## 6. Runnable Example Application

The example below uses Spring Boot 4.1.2, Java 17+, Spring Data JPA, Spring Data REST, and H2. The two exported repositories are Customer and PurchaseOrder. Address is merely an embeddable, with no repository of its own.

### 6.1. Project Structure

```text
orders-api/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── com/example/orders/
        │       ├── OrdersApplication.java
        │       ├── domain/
        │       │   ├── Address.java
        │       │   ├── Customer.java
        │       │   ├── OrderStatus.java
        │       │   └── PurchaseOrder.java
        │       └── repository/
        │           ├── CustomerRepository.java
        │           └── PurchaseOrderRepository.java
        └── resources/
            └── application.properties
```

### 6.2. Maven Dependencies

File pom.xml:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.2</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>orders-api</artifactId>
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
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <scope>runtime</scope>
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

Do not declare explicit versions for the starters and H2 because Spring Boot dependency management manages compatible versions.

### 6.3. Repositories

File CustomerRepository.java:

```java
package com.example.orders.repository;

import com.example.orders.domain.Customer;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.rest.core.annotation.RepositoryRestResource;

@RepositoryRestResource(
    path = "customers",
    collectionResourceRel = "customers"
)
public interface CustomerRepository
        extends JpaRepository<Customer, Long> {
}
```

File PurchaseOrderRepository.java:

```java
package com.example.orders.repository;

import com.example.orders.domain.PurchaseOrder;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.rest.core.annotation.RepositoryRestResource;

@RepositoryRestResource(
    path = "orders",
    collectionResourceRel = "orders"
)
public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {
}
```

### 6.4. Main Application and Seed Data

File OrdersApplication.java:

```java
package com.example.orders;

import com.example.orders.domain.Address;
import com.example.orders.domain.Customer;
import com.example.orders.domain.OrderStatus;
import com.example.orders.domain.PurchaseOrder;
import com.example.orders.repository.CustomerRepository;
import com.example.orders.repository.PurchaseOrderRepository;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class OrdersApplication {

    public static void main(String[] args) {
        SpringApplication.run(OrdersApplication.class, args);
    }

    @Bean
    CommandLineRunner seedData(
            CustomerRepository customers,
            PurchaseOrderRepository orders) {

        return args -> {
            if (customers.count() == 0) {
                Customer first = customers.save(new Customer(
                    "Nguyen An",
                    "an@example.com",
                    new Address(
                        "12 Le Loi",
                        "Ho Chi Minh City",
                        "700000",
                        "VN"
                    )
                ));

                customers.save(new Customer(
                    "Tran Binh",
                    "binh@example.com",
                    new Address(
                        "25 Nguyen Hue",
                        "Ho Chi Minh City",
                        "700000",
                        "VN"
                    )
                ));

                orders.save(new PurchaseOrder(
                    "PO-1001",
                    OrderStatus.DRAFT,
                    first
                ));
            }
        };
    }
}
```

The seed data creates two customers and one order belonging to the first customer. Data is created once when the H2 database is empty.

### 6.5. H2 Configuration

File application.properties:

```properties
spring.datasource.url=jdbc:h2:mem:orders;DB_CLOSE_DELAY=-1
spring.datasource.username=sa
spring.datasource.password=

spring.jpa.hibernate.ddl-auto=create-drop
spring.data.rest.base-path=/api
```

create-drop is only suitable for examples and development environments. For real data, use a migration tool such as Flyway or Liquibase and do not let the application drop the schema on shutdown.

### 6.6. Running the Application

Requires Java 17+ and Maven 3.6.3+ per Spring Boot 4.1.2 configuration.

```bash
./mvnw spring-boot:run
```

On Windows:

```powershell
.\mvnw.cmd spring-boot:run
```

Verify JDK and Maven Wrapper before running:

```bash
java -version
./mvnw -version
```

### 6.7. Trying the Resources

Read the root resource to discover repositories:

```bash
curl -H "Accept: application/hal+json" http://localhost:8080/api
```

Read customer 1:

```bash
curl -H "Accept: application/hal+json" http://localhost:8080/api/customers/1
```

You will see basic properties, the nested address object, and a link to the orders collection.

Read order 1:

```bash
curl -H "Accept: application/hal+json" http://localhost:8080/api/orders/1
```

The representation contains orderNumber, status, and the customer link. Follow the association link to access the linked customer.

Read the relationship state:

```bash
curl -H "Accept: application/hal+json" http://localhost:8080/api/orders/1/customer
```

Change the relationship to customer 2:

```bash
curl -i -X PUT \
  -H "Content-Type: text/uri-list" \
  --data "http://localhost:8080/api/customers/2" \
  http://localhost:8080/api/orders/1/customer
```

Read the order or association resource again to confirm the customer has changed.

## 7. Safe Relationship Design Rules

### 7.1. Distinguish Owning Side and Inverse Side

In a bidirectional JPA relationship, one side owns the mapping and the other references it via mappedBy.

In the Customer and PurchaseOrder example:

- PurchaseOrder.customer is the owning side because it holds the foreign key.
- Customer.orders is the inverse side because of mappedBy = "customer".

If you only add an order to the Customer.orders collection without setting PurchaseOrder.customer, the relationship change may not be persisted as expected. Maintain both sides in a helper method or application service.

### 7.2. Choose Cascade According to Business Lifecycle

Cascade decides which persistence operations propagate to related entities. It is not a tool to make an object graph save everything automatically.

- Do not place CascadeType.REMOVE from PurchaseOrder to Customer if a customer can be shared by multiple orders.
- Only use cascade persist/merge when the child's lifecycle truly depends on the parent.
- orphanRemoval = true is only suitable when removing a child from the collection means the child must be deleted from the database.
- Do not use CascadeType.ALL blindly for every relationship.

In the example, the order references an existing customer, so do not cascade remove from order to customer.

### 7.3. Avoid Infinite Recursion During Serialization

Bidirectional relationships can create reference cycles in Java:

```text
Customer
  └── orders[]
        └── customer
              └── orders[]
                    └── ...
```

Spring Data REST handles entity associations using HAL links under its default export mechanism. If you write custom controllers and serialize an entity graph with Jackson, control cycles with DTOs or appropriate serialization settings. Do not return an unbounded object graph directly from an API.

### 7.4. Do Not Eagerly Load the Entire Object Graph by Default

FetchType.LAZY avoids loading relationships when not needed. However, clients following association links can generate many requests if iterating over hundreds of entities.

When a composite read representation is needed:

- Use projections to define the exact set of properties the client needs.
- Use excerpt projections for collection resources when appropriate.
- Create a dedicated endpoint/query if complex data aggregation is required.
- Inspect SQL and query counts to detect N+1 issues.
- Do not switch every association to EAGER just to make JSON responses look complete.

### 7.5. Do Not Turn Every Entity into a Public API

Exporting a repository means Spring Data REST can generate resources for that repository. Explicitly decide which aggregate roots are public.

If you do not want to export a repository:

```java
@RepositoryRestResource(exported = false)
public interface InternalAuditRepository
        extends JpaRepository<InternalAudit, Long> {
}
```

If you want to hide a specific association from the API:

```java
@ManyToOne(fetch = FetchType.LAZY)
@RestResource(exported = false)
private InternalAudit audit;
```

Place @RestResource(path = "...", rel = "...") on an association property if you need to customize its path or relation name. @JsonIgnore affects Jackson serialization; it is not a substitute for Spring Data REST export configuration when the goal is managing association resources.

### 7.6. Separate the Persistence Model from the API Contract

Spring Data REST helps build APIs rapidly from repositories, yet a domain entity is not always a suitable request/response contract.

Consider dedicated DTOs or controllers/services when:

- The API needs aggregated fields from multiple entities.
- Clients are only allowed to edit a small subset of an entity.
- There is a multi-step business workflow.
- Sensitive fields must be masked or representation structure must evolve independently of the database.
- You want API stability while renaming properties or refactoring the domain model.

Projections fit read representation tailoring. For complex writes, use command/request models and application services to enforce business rules.

## 8. Common Pitfalls

| Pitfall | Consequence | Fix |
|---|---|---|
| Using @Entity for a group of fields just to bundle data | Creates unnecessary identity, table, and repository | Use @Embeddable if the object is only part of the owning entity's state |
| Using @Embedded for an object with an independent lifecycle | Cannot manage the object as a standalone resource | Use an entity and appropriate JPA relationship |
| Assuming @Embedded creates its own endpoint | Looking for nonexistent endpoints | Only exported entity repositories create collection resources |
| Assuming @ManyToOne embeds the entire entity into JSON | Response may only include a HAL association link | Follow the association link to retrieve the related resource |
| Putting the wrong field name in mappedBy | Hibernate reports mapping errors or relationship fails | Use the exact property name on the owning side |
| Updating only the inverse side | Foreign key may remain unchanged | Update the owning side and keep both sides synchronized |
| Cascade REMOVE to a shared entity | Deleting one object may delete data referenced by others | Choose cascade based on ownership and lifecycle |
| Using CascadeType.ALL on every relationship | Unintended cascading saves/deletes | Enable only the required cascade operations |
| Serializing bidirectional relationships in custom controllers | JSON may loop infinitely or grow huge | Use DTOs, HAL links, or serialization controls |
| Renaming fields without checking the API contract | JSON properties and relation links can change | Use explicit mapping/custom relations or intentional API versioning |
| Exporting all repositories | Exposes sensitive data or unintended write operations | Restrict exported repositories/associations and apply Spring Security |

## 9. Domain Model Design Checklist

Before adding a field or relationship, answer:

1. Is this a basic value, value object, collection of values, or entity with identity?
2. Can the object exist and be referenced independently of the current entity?
3. If embeddable, does it truly belong to the owning entity's lifecycle?
4. If an association, is the cardinality one-to-one, one-to-many, or many-to-many?
5. Which side owns the foreign key? Is mappedBy accurate?
6. Do cascade and orphan removal match the business lifecycle?
7. Will Spring Data REST emit a JSON property or an association link?
8. Which repositories are permitted to be exported? Are clients allowed to read and write this relationship?
9. Does the response risk loading too much data or causing N+1 queries?
10. Are projections, DTOs, or dedicated business endpoints needed to keep the API stable?

## 10. Official References

- [Spring Data REST — Repository resources](https://docs.spring.io/spring-data/rest/reference/repository-resources.html): collection, item, association resources, HAL links, and HTTP methods.
- [Spring Data REST — Project](https://spring.io/projects/spring-data-rest/): how Spring Data REST analyzes domain models and exposes hypermedia resources.
- [Jakarta Persistence 3.2 — Specification](https://jakarta.ee/specifications/persistence/3.2/jakarta-persistence-spec-3.2.html): basic attributes, embeddable classes, element collections, and entity relationships.
- [Jakarta Persistence — Embeddable API](https://jakarta.ee/specifications/persistence/3.2/apidocs/jakarta.persistence/jakarta/persistence/embeddable): requirements and semantics of @Embeddable.
- [Spring Boot 4.1.2 — System Requirements](https://docs.spring.io/spring-boot/system-requirements.html): Java and build tool requirements for the example.
- [Spring Boot — SQL Databases](https://docs.spring.io/spring-boot/4.0/reference/data/sql.html): JPA and Spring Data JPA integration in Spring Boot.

Use the domain model to express business meaning accurately. Basic attributes hold single values, embeddables group values belonging to an owning entity, and associations connect entities with separate identities. Spring Data REST reflects those distinctions in JSON and HAL links; designing them properly from the start makes APIs easier to understand and maintain.
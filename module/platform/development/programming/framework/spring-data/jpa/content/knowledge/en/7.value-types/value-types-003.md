# Overriding Mappings with @AttributeOverride and @AssociationOverride

## Objectives

`@Embeddable` allows reusing a group of attributes across multiple entities; `@MappedSuperclass` allows multiple entities to inherit shared mappings. However, the same class may need different column names or relationship join definitions depending on where it is used. JPA provides two annotations to customize mappings at the inheritance or embedding site:

- `@AttributeOverride` changes the column mapping of a basic attribute, such as a `String`, `BigDecimal`, `LocalDate`, or an attribute inside an embeddable.
- `@AssociationOverride` changes the mapping of a relationship to an entity, such as the join column or join table of `@ManyToOne`, `@OneToOne`, `@OneToMany`, or `@ManyToMany`.

The key point is that an override changes how JPA maps an attribute in a specific context. It does not rename the Java field, does not alter the structure of the shared class, and does not automatically migrate a production schema.

## 1. Why Override Mappings?

Suppose an application has an address embeddable:

```java
@Embeddable
public class Address {
    private String street;
    private String city;
    private String postalCode;
}
```

One entity needs a billing address, another needs a shipping address. If the same embeddable is used twice in a single table, the default mapping can produce duplicate column names. The application needs distinct names such as `billing_street` and `shipping_street`.

Similarly, an embeddable with a relationship to `Agent` may be embedded into multiple entities. Each entity may need a different foreign key name, such as `assigned_agent_id` or `reviewer_id`.

Overrides allow keeping a single reusable class with a consistent meaning while defining appropriate column and join names in each entity.

## 2. @AttributeOverride: Overriding Column Mappings

`@AttributeOverride` has two parts:

- `name`: the Java attribute name to override.
- `column`: a `@Column` annotation describing the new column mapping.

Example:

```java
@Embedded
@AttributeOverride(
    name = "street",
    column = @Column(name = "billing_street", nullable = false, length = 150)
)
private Address billingAddress;
```

Here `name = "street"` refers to the `street` attribute in `Address`, not the SQL column name. `column` specifies the database column that the attribute uses in the entity embedding `Address`.

### Overriding multiple attributes

When you need to change multiple columns, use `@AttributeOverrides`:

```java
@Embedded
@AttributeOverrides({
    @AttributeOverride(
        name = "street",
        column = @Column(name = "billing_street", nullable = false, length = 150)
    ),
    @AttributeOverride(
        name = "city",
        column = @Column(name = "billing_city", nullable = false, length = 80)
    ),
    @AttributeOverride(
        name = "postalCode",
        column = @Column(name = "billing_postal_code", length = 16)
    )
})
private Address billingAddress;
```

For another `Address` instance, declare a separate set of overrides:

```java
@Embedded
@AttributeOverrides({
    @AttributeOverride(name = "street",
        column = @Column(name = "shipping_street", nullable = false, length = 150)),
    @AttributeOverride(name = "city",
        column = @Column(name = "shipping_city", nullable = false, length = 80)),
    @AttributeOverride(name = "postalCode",
        column = @Column(name = "shipping_postal_code", length = 16))
})
private Address shippingAddress;
```

As a result, both fields use the Java type `Address`, while storing into different columns in the same table.

### @Column attributes that can be overridden

You can customize column mapping details such as:

- `name`: column name.
- `nullable`: whether the column allows `NULL`.
- `length`: length for string columns.
- `precision` and `scale`: precision and decimal digits for appropriate numeric types.
- `unique`: declares a unique constraint in provider-generated schemas.
- `columnDefinition`: database-specific column type definition, if dialect-dependent SQL is truly needed.

Specifying only the column name may cause other attributes to revert to the defaults of the `@Column` annotation. If the schema requires `nullable=false`, a specific length, or specific precision, declare them explicitly in the override and verify the actual migration/schema.

## 3. Overriding Nested Attributes

An embeddable can contain another embeddable. When overriding an attribute nested deeper inside, use a dot-separated attribute path.

Example:

```java
@Embeddable
public class Coordinates {
    private Double latitude;
    private Double longitude;
}

@Embeddable
public class Address {
    private String street;

    @Embedded
    private Coordinates coordinates;
}
```

When embedding `Address`, `latitude` and `longitude` can be overridden as follows:

```java
@Embedded
@AttributeOverrides({
    @AttributeOverride(
        name = "coordinates.latitude",
        column = @Column(name = "delivery_latitude", precision = 10, scale = 7)
    ),
    @AttributeOverride(
        name = "coordinates.longitude",
        column = @Column(name = "delivery_longitude", precision = 10, scale = 7)
    )
})
private Address deliveryAddress;
```

The path must use Java attribute names matching the embeddable structure. Do not use SQL column names in `name`.

## 4. Overriding Mappings Inherited from @MappedSuperclass

`@AttributeOverride` is also used to change the mapping of basic attributes inherited from a `@MappedSuperclass`.

```java
@MappedSuperclass
public abstract class AuditedRecord {
    @Column(name = "created_at", nullable = false)
    protected Instant createdAt;
}

@Entity
@Table(name = "support_cases")
@AttributeOverride(
    name = "createdAt",
    column = @Column(name = "case_created_at", nullable = false)
)
public class SupportCase extends AuditedRecord {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;
}
```

`AuditedRecord` still defines a shared `createdAt` attribute. The `SupportCase` entity stores that attribute in the `case_created_at` column. Another entity can keep `created_at` or declare its own override.

If you need to override multiple inherited attributes, use `@AttributeOverrides` at the entity level. This overrides the mapping of inherited attributes; it does not create a separate table for `@MappedSuperclass`.

## 5. @AssociationOverride: Overriding Relationship Mappings

`@AssociationOverride` is used for entity relationship attributes declared in an embeddable or mapped superclass. This annotation does not replace `@AttributeOverride`: one adjusts associations, and the other adjusts basic attributes.

Important attributes:

- `name`: the name of the relationship attribute to override.
- `joinColumns`: one or more foreign keys placed in the table of the entity owning the relationship.
- `joinTable`: the join table mapping, including join columns pointing to the owning entity and inverse join columns pointing to the target entity.

### Overriding the join column of @ManyToOne

An embeddable with a relationship to `Agent`:

```java
@Embeddable
public class Assignment {
    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "agent_id")
    private Agent agent;

    private String note;
}
```

When `Assignment` is embedded in an entity, rename the foreign key:

```java
@Embedded
@AssociationOverride(
    name = "agent",
    joinColumns = @JoinColumn(name = "assigned_agent_id")
)
private Assignment assignment;
```

`name = "agent"` is the relationship attribute in `Assignment`. `joinColumns` places the foreign key column `assigned_agent_id` in the table of the entity embedding `Assignment`.

If the embeddable is embedded in another entity, that entity can override the same relationship to `reviewer_id`. The default mapping in `Assignment` remains useful when no override is present.

### Overriding a join table

For relationships that use a join table, declare `joinTable` instead of `joinColumns`. For example, an embeddable declaring a set of reviewers:

```java
@Embeddable
public class ReviewGroup {
    @ManyToMany
    private Set<Agent> reviewers = new HashSet<>();
}
```

The embedding entity can define a custom join table:

```java
@Embedded
@AssociationOverride(
    name = "reviewers",
    joinTable = @JoinTable(
        name = "case_reviewers",
        joinColumns = @JoinColumn(name = "case_id"),
        inverseJoinColumns = @JoinColumn(name = "reviewer_id")
    )
)
private ReviewGroup reviewGroup;
```

`joinColumns` in `@JoinTable` is the foreign key pointing to the owning entity; `inverseJoinColumns` points to the entity on the other side of the relationship. `joinTable` and `joinColumns` at the `@AssociationOverride` level are two different ways of describing a mapping; choose based on the association type and desired schema structure.

### Choosing joinColumns or joinTable?

| Relationship mapping | Common structure | Typical override choice |
| --- | --- | --- |
| `@ManyToOne` owning side | Foreign key in the owning entity's table | `joinColumns` |
| `@OneToOne` owning side | Foreign key in the owning entity's table or join table depending on mapping | `joinColumns` or `joinTable` |
| `@ManyToMany` | Join table | `joinTable` |
| Unidirectional `@OneToMany` | Usually uses a join table; can also be designed with a foreign key depending on mapping | `joinTable` or corresponding association configuration |

An inverse-side relationship using `mappedBy` does not own the join column. Place overrides where the mapping is allowed to control the association and verify the owning side; an override cannot be used to turn an inverse association into the owning side arbitrarily.

## 6. Overriding Associations Inherited from @MappedSuperclass

`@AssociationOverride` can also change the mapping of a relationship declared in a mapped superclass.

```java
@MappedSuperclass
public abstract class OwnedRecord {
    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "owner_id")
    protected Agent owner;
}

@Entity
@AssociationOverride(
    name = "owner",
    joinColumns = @JoinColumn(name = "reviewer_id")
)
public class Review extends OwnedRecord {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;
}
```

The `Review` entity inherits the `owner` relationship but stores the foreign key in the `reviewer_id` column. `@AssociationOverrides` can be used if multiple inherited relationships need to be changed.

## 7. Combining AttributeOverride and AssociationOverride

An embeddable can contain both basic attributes and associations. When embedding it, the entity may need to change both data columns and join columns. Both override types can be placed together on the embedded field or property.

```java
@Entity
@Table(name = "support_cases")
public class SupportCase {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Embedded
    @AttributeOverride(
        name = "note",
        column = @Column(name = "assignment_note", length = 200)
    )
    @AssociationOverride(
        name = "agent",
        joinColumns = @JoinColumn(name = "assigned_agent_id")
    )
    private Assignment assignment;
}
```

In this example:

- `note` is a basic attribute, so it is adjusted with `@AttributeOverride`.
- `agent` is a `@ManyToOne` relationship, so it is adjusted with `@AssociationOverride`.
- `assignment` remains a Java attribute of type `Assignment`; only the mapping in the `SupportCase` entity is changed.

This is how you keep an embeddable reusable without creating multiple nearly identical classes just because of different column names.

## 8. Runnable Example with Java 17+, Spring Boot, and H2

The example creates a `SupportCase` with a billing address, a shipping address, and an assignee. The two addresses use the same `Address` embeddable but have distinct column names. `Assignment` contains a `ManyToOne` relationship to `Agent`; the `SupportCase` entity overrides the foreign key name and the note column name.

### Directory structure

```text
mapping-overrides/
├── pom.xml
└── src/
    └── main/
        ├── java/com/example/mappingoverrides/
        │   ├── MappingOverridesApplication.java
        │   ├── Address.java
        │   ├── Assignment.java
        │   ├── Agent.java
        │   ├── SupportCase.java
        │   ├── AgentRepository.java
        │   ├── SupportCaseRepository.java
        │   └── SupportCaseService.java
        └── resources/
            └── application.properties
```

### `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.4.5</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>mapping-overrides</artifactId>
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

### `src/main/resources/application.properties`

```properties
spring.datasource.url=jdbc:h2:mem:overrides;DB_CLOSE_DELAY=-1
spring.datasource.username=sa
spring.datasource.password=
spring.jpa.hibernate.ddl-auto=create-drop
spring.jpa.open-in-view=false
logging.level.org.hibernate.SQL=DEBUG
```

`create-drop` is only for an in-memory test database. Production should manage schemas with Flyway or Liquibase.

### `Address.java`

```java
package com.example.mappingoverrides;

import jakarta.persistence.Column;
import jakarta.persistence.Embeddable;

@Embeddable
public class Address {
    @Column(length = 150)
    private String street;

    @Column(length = 80)
    private String city;

    @Column(length = 16)
    private String postalCode;

    protected Address() {
    }

    public Address(String street, String city, String postalCode) {
        this.street = street;
        this.city = city;
        this.postalCode = postalCode;
    }

    public String getStreet() {
        return street;
    }

    public String getCity() {
        return city;
    }

    public String getPostalCode() {
        return postalCode;
    }
}
```

### `Agent.java`

```java
package com.example.mappingoverrides;

import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "agents")
public class Agent {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String name;

    protected Agent() {
    }

    public Agent(String name) {
        this.name = name;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }
}
```

### `Assignment.java`

```java
package com.example.mappingoverrides;

import jakarta.persistence.Column;
import jakarta.persistence.Embeddable;
import jakarta.persistence.FetchType;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;

@Embeddable
public class Assignment {
    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "agent_id")
    private Agent agent;

    @Column(length = 200)
    private String note;

    protected Assignment() {
    }

    public Assignment(Agent agent, String note) {
        this.agent = agent;
        this.note = note;
    }

    public Agent getAgent() {
        return agent;
    }

    public String getNote() {
        return note;
    }
}
```

### `SupportCase.java`

```java
package com.example.mappingoverrides;

import jakarta.persistence.AttributeOverride;
import jakarta.persistence.AttributeOverrides;
import jakarta.persistence.AssociationOverride;
import jakarta.persistence.Column;
import jakarta.persistence.Embedded;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.Table;

@Entity
@Table(name = "support_cases")
public class SupportCase {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Embedded
    @AttributeOverrides({
        @AttributeOverride(name = "street",
            column = @Column(name = "billing_street", nullable = false, length = 150)),
        @AttributeOverride(name = "city",
            column = @Column(name = "billing_city", nullable = false, length = 80)),
        @AttributeOverride(name = "postalCode",
            column = @Column(name = "billing_postal_code", length = 16))
    })
    private Address billingAddress;

    @Embedded
    @AttributeOverrides({
        @AttributeOverride(name = "street",
            column = @Column(name = "shipping_street", nullable = false, length = 150)),
        @AttributeOverride(name = "city",
            column = @Column(name = "shipping_city", nullable = false, length = 80)),
        @AttributeOverride(name = "postalCode",
            column = @Column(name = "shipping_postal_code", length = 16))
    })
    private Address shippingAddress;

    @Embedded
    @AttributeOverride(name = "note",
        column = @Column(name = "assignment_note", length = 200))
    @AssociationOverride(name = "agent",
        joinColumns = @JoinColumn(name = "assigned_agent_id"))
    private Assignment assignment;

    protected SupportCase() {
    }

    public SupportCase(Address billingAddress, Address shippingAddress,
                       Assignment assignment) {
        this.billingAddress = billingAddress;
        this.shippingAddress = shippingAddress;
        this.assignment = assignment;
    }

    public Long getId() {
        return id;
    }

    public Address getBillingAddress() {
        return billingAddress;
    }

    public Address getShippingAddress() {
        return shippingAddress;
    }

    public Assignment getAssignment() {
        return assignment;
    }
}
```

### `AgentRepository.java`

```java
package com.example.mappingoverrides;

import org.springframework.data.jpa.repository.JpaRepository;

public interface AgentRepository extends JpaRepository<Agent, Long> {
}
```

### `SupportCaseRepository.java`

```java
package com.example.mappingoverrides;

import org.springframework.data.jpa.repository.JpaRepository;

public interface SupportCaseRepository extends JpaRepository<SupportCase, Long> {
}
```

### `SupportCaseService.java`

```java
package com.example.mappingoverrides;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class SupportCaseService {
    private final AgentRepository agentRepository;
    private final SupportCaseRepository caseRepository;

    public SupportCaseService(AgentRepository agentRepository,
                              SupportCaseRepository caseRepository) {
        this.agentRepository = agentRepository;
        this.caseRepository = caseRepository;
    }

    @Transactional
    public String createAndRead() {
        Agent agent = agentRepository.save(new Agent("Linh"));

        SupportCase supportCase = new SupportCase(
                new Address("12 Le Loi", "Ha Noi", "100000"),
                new Address("8 Tran Phu", "Da Nang", "550000"),
                new Assignment(agent, "Handle customer request"));

        SupportCase saved = caseRepository.save(supportCase);
        SupportCase loaded = caseRepository.findById(saved.getId()).orElseThrow();

        return "Billing city: " + loaded.getBillingAddress().getCity()
                + "\nShipping city: " + loaded.getShippingAddress().getCity()
                + "\nAssigned agent: " + loaded.getAssignment().getAgent().getName()
                + "\nAssignment note: " + loaded.getAssignment().getNote();
    }
}
```

### `MappingOverridesApplication.java`

```java
package com.example.mappingoverrides;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class MappingOverridesApplication {
    public static void main(String[] args) {
        SpringApplication.run(MappingOverridesApplication.class, args);
    }

    @Bean
    CommandLineRunner demo(SupportCaseService service) {
        return args -> System.out.println(service.createAndRead());
    }
}
```

### Running the program

```bash
mvn spring-boot:run
```

The output printed by the application:

```text
Billing city: Ha Noi
Shipping city: Da Nang
Assigned agent: Linh
Assignment note: Handle customer request
```

In the `support_cases` table, the columns are mapped according to the overridden names: `billing_street`, `billing_city`, `billing_postal_code`, `shipping_street`, `shipping_city`, `shipping_postal_code`, `assignment_note`, and `assigned_agent_id`. The `agents` table holds the `Agent` entity; `assigned_agent_id` is the foreign key pointing to `agents.id`.

The example uses `save()` and `findById()` within the same transaction to focus on the mapping. Hibernate may return the managed instance already in the persistence context; if you want to observe a fresh database read, flush and clear the EntityManager before finding again in an integration test.

## 9. Naming Rules and Limitations

- `name` in an override is the Java attribute name, which is case-sensitive; it is not the database column name.
- For nested attributes, use a dot-separated path, such as `location.coordinates.latitude`.
- When embedding the same embeddable multiple times in the same entity, override colliding columns so mappings do not conflict.
- `@AttributeOverride` is only for basic attributes; do not use it to change a relationship's join column.
- `@AssociationOverride` is for associations; do not use it to rename the column of an ordinary `String` or `BigDecimal`.
- `@AssociationOverride` must be applied to an association declared in an embeddable or mapped superclass; it is not a general tool for arbitrarily changing relationships anywhere.
- For associations, distinguish between the owning side and the inverse side. The join column is managed by the owning side.
- When partially overriding a mapping, declare all required schema attributes such as nullability, length, and constraints.

## 10. Changing Overrides and Database Migrations

Mapping annotations are descriptions for the JPA provider. Changing `@AttributeOverride` from `billing_city` to `invoice_city` does not automatically guarantee that the production column is renamed or that data is safely migrated. Similarly, changing `assigned_agent_id` may require renaming the foreign key column and constraint.

For a database with existing data:

1. Identify the current schema, foreign keys, indexes, constraints, data, and applications using the column.
2. Write a versioned migration to add the new column or rename the column according to the database's capabilities.
3. If a multi-version rollout is needed, use a compatibility phase: both old and new versions must be able to read/write without data loss.
4. Backfill data to the new column and verify row counts, null values, orphan foreign keys, and integrity.
5. Deploy the new mapping after the compatible schema is ready.
6. Only drop the old column once no application version reads or writes it anymore.

Do not rely on `spring.jpa.hibernate.ddl-auto=update` as a production migration mechanism. Use Flyway, Liquibase, or a controlled migration workflow to version schema changes.

## 11. Common Mistakes

1. **Using the wrong name in `name`:** writing the SQL column name instead of the Java field/property name. Check the attribute name in the embeddable or mapped superclass.
2. **Two embedded objects generate duplicate columns:** declare separate `@AttributeOverrides` for each embedded field.
3. **Using `@AttributeOverride` for `@ManyToOne`:** switch to `@AssociationOverride` with appropriate `joinColumns` or `joinTable`.
4. **Using `joinColumns` when the mapping requires a join table:** identify the association owner and link type before choosing the override attribute.
5. **Wrong nested override path:** check each property name in the chain, using dots for nested embeddables.
6. **Expecting annotations to fix the production schema automatically:** create migrations and verify the schema after deployment.
7. **Forgetting to override nullability or length:** check whether `@Column` in the override retains the desired constraints.
8. **Confusing the inverse association with the owning side:** check `mappedBy`; overrides must control the mapping on the owning side of the relationship.

## 12. How to Test Mappings

Mapping tests should verify both the schema and read/write behavior:

- Initialize the JPA context with a test database and let Hibernate validate the mapping.
- Save an entity with two embeddables of the same type, then query the table directly to confirm each field writes to the right column.
- Save an entity with an overridden association, verifying the foreign key resides in the right column and points to the right row.
- Reload the entity in a new persistence context to test bidirectional mapping.
- For nested paths or mapped superclasses, verify each overridden attribute.
- Run migrations on a data copy with a production-equivalent structure before release.

Integration test examples should run across separate transactions or clear the persistence context before reading back; if only reading the same managed instance, tests might miss incorrect database mappings.

## 13. Selection Summary

| Need | Annotation |
| --- | --- |
| Rename or change column attributes of a basic field in an embeddable | `@AttributeOverride` |
| Change multiple basic columns at once | `@AttributeOverrides` |
| Change basic columns inherited from a mapped superclass | `@AttributeOverride` or `@AttributeOverrides` on the child entity |
| Change the foreign key of an association in an embeddable | `@AssociationOverride(joinColumns = ...)` |
| Change the join table of an association | `@AssociationOverride(joinTable = ...)` |
| Change multiple associations at once | `@AssociationOverrides` |
| Keep the same embeddable with different column names per entity | Override at each `@Embedded` site |

Rule to remember: **AttributeOverride adjusts columns of data attributes; AssociationOverride adjusts how relationships join. `name` always refers to the Java attribute in the embedded or inherited mapping. Any change affecting the production schema requires migration and data testing.**

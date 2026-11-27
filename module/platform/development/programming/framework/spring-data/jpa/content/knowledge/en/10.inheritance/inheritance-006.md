# Configuring @Inheritance, @DiscriminatorColumn, and @DiscriminatorValue

## Objectives

Inheritance in Java allows a child class to receive attributes and behavior from a parent class. In JPA, when one entity class inherits from another entity class, we need to choose how to map that inheritance tree onto relational tables.

JPA provides three main strategies via `@Inheritance`:

- `SINGLE_TABLE`: the entire hierarchy is stored in a single table.
- `JOINED`: the parent class and each child class are stored in separate tables, linked by primary key/foreign key.
- `TABLE_PER_CLASS`: each concrete entity class has its own table, containing inherited attributes as well.

With `SINGLE_TABLE` and `JOINED`, a discriminator can help distinguish entity types within the hierarchy. We declare the discriminator column with `@DiscriminatorColumn` and each entity class's value with `@DiscriminatorValue`.

After this lesson, you can:

- Choose an inheritance strategy suited to the data model.
- Place `@Inheritance` properly on the root entity.
- Configure the discriminator's name, type, and values.
- Understand the schema generated for each strategy.
- Run polymorphic queries through the parent entity.
- Avoid mapping, nullability, migration, and provider-compatibility mistakes.

Examples use Java 17+, Spring Boot 3.x, Jakarta Persistence, and Spring Data JPA.

## 1. Entity Inheritance in JPA

Suppose an application supports multiple payment methods. All methods have a payment ID and an amount, while each type has its own information:

- Card payments have the card's last four digits.
- Bank transfers have the recipient bank account number.

In Java, this can be modeled with a parent class `Payment` and child classes `CardPayment`, `BankTransferPayment`:

```java
public abstract class Payment {
    private Long id;
    private BigDecimal amount;
}

public class CardPayment extends Payment {
    private String cardLastFour;
}

public class BankTransferPayment extends Payment {
    private String bankAccount;
}
```

If these classes are JPA entities, the database must store data so the right entity type can be reconstructed on read. JPA refers to this as entity inheritance mapping.

Key point: Java inheritance by itself does not determine table structure. The `@Inheritance` strategy dictates how the provider maps the hierarchy to a relational schema.

## 2. @Inheritance and Its Strategies

`@Inheritance` is placed on the root entity of the hierarchy—the highest parent entity in the inheritance tree managed by JPA. Child classes are annotated with `@Entity` and extend the parent entity.

If `@Inheritance` is omitted, JPA's default strategy is `SINGLE_TABLE`. Even so, declare it explicitly so readers understand the design intent.

### 2.1. SINGLE_TABLE

All entities in the hierarchy are stored in the same table. A discriminator column distinguishes the entity type of each row.

Conceptual schema example:

```sql
CREATE TABLE payments (
    id BIGINT PRIMARY KEY,
    amount DECIMAL(19, 2) NOT NULL,
    payment_type VARCHAR(24) NOT NULL,
    card_last_four VARCHAR(4),
    bank_account VARCHAR(40)
);
```

Data:

| id | amount | payment_type | card_last_four | bank_account |
|---:|---:|---|---|---|
| 1 | 120.00 | CARD | 1234 | NULL |
| 2 | 250.00 | BANK_TRANSFER | NULL | 00123456 |

Advantages:

- Querying the entire hierarchy is usually simple because only one table is read.
- No JOIN between parent and child tables is needed when reading entities.
- Easy to execute polymorphic queries.
- Fits well when the number of subclasses is moderate and shared attributes make up the majority.

Disadvantages:

- Columns specific to a subclass usually must allow null because rows of other subclasses do not use them.
- The table can develop many sparse columns when the hierarchy grows large.
- Per-subclass required constraints are difficult to express with a simple NOT NULL.
- Hierarchy changes can make the central table progressively wider.

With `SINGLE_TABLE`, the discriminator is the essential mechanism telling the provider which entity class each row belongs to.

### 2.2. JOINED

The parent entity is stored in one table; each subclass has its own table holding its specific attributes. Subclass tables use a primary key that also acts as a foreign key referencing the parent table.

Conceptual schema example:

```sql
CREATE TABLE payments (
    id BIGINT PRIMARY KEY,
    amount DECIMAL(19, 2) NOT NULL,
    payment_type VARCHAR(24)
);

CREATE TABLE card_payments (
    payment_id BIGINT PRIMARY KEY REFERENCES payments(id),
    card_last_four VARCHAR(4) NOT NULL
);

CREATE TABLE bank_transfer_payments (
    payment_id BIGINT PRIMARY KEY REFERENCES payments(id),
    bank_account VARCHAR(40) NOT NULL
);
```

A card payment requires one row in `payments` and a corresponding row in `card_payments`. The key `card_payments.payment_id` is the ID of the parent row.

Advantages:

- Shared data is stored only once in the parent table.
- Subclass-specific columns reside in their respective tables.
- NOT NULL and appropriate constraints can be enforced on subclass attributes.
- The schema is more normalized than SINGLE_TABLE.

Disadvantages:

- Querying a subclass entity usually requires JOINing the parent table with the subclass table.
- Polymorphic queries may require JOINing multiple tables.
- Saving or deleting an entity can touch multiple tables.
- The number of tables grows with the number of subclasses.

In `JOINED`, a discriminator column can be declared to distinguish entity types. JPA allows `@DiscriminatorColumn` on the root of a hierarchy using SINGLE_TABLE or JOINED. With JOINED, providers can identify subtypes via joined table structure even without a discriminator; declaring a discriminator explicitly is helpful when the mapping/provider needs that column.

### 2.3. TABLE_PER_CLASS

Each concrete entity class has its own table. Each table contains both attributes inherited from the parent class and attributes specific to that class.

Conceptual schema example:

```sql
CREATE TABLE card_payments (
    id BIGINT PRIMARY KEY,
    amount DECIMAL(19, 2) NOT NULL,
    card_last_four VARCHAR(4) NOT NULL
);

CREATE TABLE bank_transfer_payments (
    id BIGINT PRIMARY KEY,
    amount DECIMAL(19, 2) NOT NULL,
    bank_account VARCHAR(40) NOT NULL
);
```

There is no shared `payments` table in this model. The `amount` attribute is repeated in each concrete subclass table.

Advantages:

- Each concrete table contains the complete data for that entity type.
- Reading a specific subclass requires no JOIN with a parent table.
- Specialized attributes can naturally have NOT NULL in their respective tables.

Disadvantages:

- Inherited attributes are duplicated across multiple tables.
- Polymorphic queries on the parent class may require a UNION across child tables.
- Changing a shared attribute requires updating multiple tables.
- Generating unique IDs across the whole hierarchy and polymorphic operations can be more complex; some ID/provider strategies have limitations.

`TABLE_PER_CLASS` does not use a discriminator column in the standard model. Do not place `@DiscriminatorColumn` expecting the provider to classify rows under this strategy.

### 2.4. Quick Comparison

| Criterion | SINGLE_TABLE | JOINED | TABLE_PER_CLASS |
|---|---|---|---|
| Number of tables | One table for the hierarchy | Parent table and a table for each subclass | One table for each concrete class |
| Shared columns | Stored once | Stored in parent table | Repeated in each child table |
| Specialized attributes | Nullable columns in shared table | Reside in subclass table | Reside in concrete table |
| Reading a subclass | Usually no JOIN | Usually requires JOIN | No JOIN with parent table |
| Polymorphic query | Simple | May need multiple JOINs | May need UNION |
| Discriminator | Needed to distinguish row types | Optional to declare; not required in all mappings | Not used in the standard model |
| Suitability | Simple hierarchy, frequent polymorphic queries | Normalized schema, subclass attributes need constraints | Concrete classes rarely need polymorphic queries |

There is no single best strategy for every application. Consider the number of subclasses, data volume, frequency of polymorphic queries, constraints, and migration capabilities before choosing.

## 3. @DiscriminatorColumn and @DiscriminatorValue

A discriminator is metadata allowing JPA/the provider to determine which concrete entity class a row belongs to in the hierarchy.

With SINGLE_TABLE, the same table stores multiple entity types. A discriminator column records the value distinguishing that type.

Example:

| id | amount | payment_type |
|---:|---:|---|
| 1 | 120.00 | CARD |
| 2 | 250.00 | BANK_TRANSFER |

When loading row ID 1 through the root entity `Payment`, the provider reads `payment_type = CARD` and instantiates `CardPayment`.

### 3.1. @DiscriminatorColumn

`@DiscriminatorColumn` is placed on the root entity:

```java
@Entity
@Table(name = "payments")
@Inheritance(strategy = InheritanceType.SINGLE_TABLE)
@DiscriminatorColumn(
    name = "payment_type",
    discriminatorType = DiscriminatorType.STRING,
    length = 24
)
public abstract class Payment {
    // Shared attributes.
}
```

Common attributes:

| Attribute | Meaning |
|---|---|
| `name` | Name of the discriminator column |
| `discriminatorType` | Discriminator data type: STRING, CHAR, or INTEGER |
| `columnDefinition` | Optional SQL definition for the column |
| `length` | Column length; primarily relevant for STRING |

If `@DiscriminatorColumn` is omitted, JPA defaults to column name `DTYPE` and discriminator type STRING for strategies that require a discriminator. Explicit declaration makes schemas and code easier to understand.

Place `@DiscriminatorColumn` only on the root entity class of the hierarchy—do not repeat it on every subclass. This annotation is supported by JPA for hierarchies using SINGLE_TABLE or JOINED.

### 3.2. @DiscriminatorValue

`@DiscriminatorValue` specifies the discriminator value representing an entity class.

Example:

```java
@Entity
@DiscriminatorValue("CARD")
public class CardPayment extends Payment {
}

@Entity
@DiscriminatorValue("BANK_TRANSFER")
public class BankTransferPayment extends Payment {
}
```

When the provider saves a CardPayment, the `payment_type` column holds the value `CARD`. When reading a row with that value, the provider creates a CardPayment object.

If `@DiscriminatorValue` is omitted, JPA/the provider uses a default value based on the entity name for STRING-type discriminators. Using explicit values avoids coupling to class/entity names and makes the schema easier to read.

Discriminator values must be unique within the hierarchy and match the column type and length. If using STRING, choose a length sufficient for the longest value.

### 3.3. Discriminator Types

JPA supports:

- `DiscriminatorType.STRING`: string values, generally easy to read and manage.
- `DiscriminatorType.CHAR`: single character.
- `DiscriminatorType.INTEGER`: integer values.

INTEGER type example:

```java
@DiscriminatorColumn(
    name = "payment_kind",
    discriminatorType = DiscriminatorType.INTEGER
)
```

```java
@Entity
@DiscriminatorValue("1")
public class CardPayment extends Payment {
}
```

With INTEGER type, the annotation still takes the value as a string; the provider converts it according to the declared discriminator type. Human-readable strings like `CARD` are usually friendlier when inspecting data via SQL, though the final choice should align with the existing schema and system.

## 4. Complete Example with SINGLE_TABLE

### 4.1. Root Entity Payment

```java
package com.example.demo.payment;

import jakarta.persistence.*;
import java.math.BigDecimal;

@Entity
@Table(name = "payments")
@Inheritance(strategy = InheritanceType.SINGLE_TABLE)
@DiscriminatorColumn(
    name = "payment_type",
    discriminatorType = DiscriminatorType.STRING,
    length = 24
)
public abstract class Payment {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, precision = 19, scale = 2)
    private BigDecimal amount;

    protected Payment() {
    }

    protected Payment(BigDecimal amount) {
        this.amount = amount;
    }

    public Long getId() {
        return id;
    }

    public BigDecimal getAmount() {
        return amount;
    }
}
```

The root entity is annotated with `@Entity` even though it is an abstract class. JPA treats it as part of the hierarchy and can execute polymorphic queries via the Payment type. An abstract Payment instance cannot be instantiated directly.

### 4.2. Subclass CardPayment

```java
package com.example.demo.payment;

import jakarta.persistence.Column;
import jakarta.persistence.DiscriminatorValue;
import jakarta.persistence.Entity;

import java.math.BigDecimal;

@Entity
@DiscriminatorValue("CARD")
public class CardPayment extends Payment {

    @Column(name = "card_last_four", length = 4)
    private String cardLastFour;

    protected CardPayment() {
    }

    public CardPayment(BigDecimal amount, String cardLastFour) {
        super(amount);
        this.cardLastFour = cardLastFour;
    }

    public String getCardLastFour() {
        return cardLastFour;
    }
}
```

### 4.3. Subclass BankTransferPayment

```java
package com.example.demo.payment;

import jakarta.persistence.Column;
import jakarta.persistence.DiscriminatorValue;
import jakarta.persistence.Entity;

import java.math.BigDecimal;

@Entity
@DiscriminatorValue("BANK_TRANSFER")
public class BankTransferPayment extends Payment {

    @Column(name = "bank_account", length = 40)
    private String bankAccount;

    protected BankTransferPayment() {
    }

    public BankTransferPayment(BigDecimal amount, String bankAccount) {
        super(amount);
        this.bankAccount = bankAccount;
    }

    public String getBankAccount() {
        return bankAccount;
    }
}
```

All entity classes have a protected no-arg constructor for JPA to use. Each subclass declares its own discriminator value. Do not put `@DiscriminatorColumn` on subclasses.

### 4.4. Repository and Polymorphic Queries

```java
package com.example.demo.payment;

import org.springframework.data.jpa.repository.JpaRepository;

public interface PaymentRepository
        extends JpaRepository<Payment, Long> {
}
```

All payment types can be queried through the root repository:

```java
List<Payment> payments = paymentRepository.findAll();

for (Payment payment : payments) {
    if (payment instanceof CardPayment card) {
        System.out.println(card.getCardLastFour());
    } else if (payment instanceof BankTransferPayment transfer) {
        System.out.println(transfer.getBankAccount());
    }
}
```

With SINGLE_TABLE, the provider reads the discriminator to instantiate the right subclass. JPQL can also filter by entity type:

```java
@Query("select p from Payment p where type(p) = CardPayment")
List<Payment> findCardPayments();
```

In JPQL, `TYPE` checks the entity type. `TREAT` can be used when you need to access subclass attributes in a suitable query expression.

Do not rely on raw discriminator strings in business code. Use entity types, type-based queries, or clear domain modeling.

## 5. Schema and Constraints with SINGLE_TABLE

With SINGLE_TABLE, the schema has one shared table:

```sql
CREATE TABLE payments (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    amount DECIMAL(19, 2) NOT NULL,
    payment_type VARCHAR(24) NOT NULL,
    card_last_four VARCHAR(4),
    bank_account VARCHAR(40)
);
```

Subclass-specific columns typically allow null because a row of another type does not use them. For example, a CARD row has `bank_account = NULL`.

This creates a challenge: you cannot simply place `card_last_four NOT NULL` across the whole table, because BANK_TRANSFER rows must also live in the same table and have no card_last_four.

Data integrity can be protected with discriminator-based CHECK constraints on databases that support them:

```sql
ALTER TABLE payments
ADD CONSTRAINT ck_card_payment_details
CHECK (
    payment_type <> 'CARD'
    OR card_last_four IS NOT NULL
);

ALTER TABLE payments
ADD CONSTRAINT ck_bank_transfer_details
CHECK (
    payment_type <> 'BANK_TRANSFER'
    OR bank_account IS NOT NULL
);
```

These constraints illustrate how to enforce data rules per entity type. CHECK constraint syntax and capabilities vary by database. Manage schemas with Flyway/Liquibase when exact constraints are needed.

If a hierarchy has many subclasses and specialized columns, SINGLE_TABLE can create an overly wide table. That is one reason to consider JOINED.

## 6. JOINED Mapping and Discriminators

With JOINED, shared data resides in the root table and subclass attributes reside in child tables. Example:

```java
@Entity
@Table(name = "payments")
@Inheritance(strategy = InheritanceType.JOINED)
@DiscriminatorColumn(
    name = "payment_type",
    discriminatorType = DiscriminatorType.STRING,
    length = 24
)
public abstract class Payment {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, precision = 19, scale = 2)
    private BigDecimal amount;

    protected Payment() {
    }
}
```

Subclass:

```java
@Entity
@Table(name = "card_payments")
@PrimaryKeyJoinColumn(name = "payment_id")
@DiscriminatorValue("CARD")
public class CardPayment extends Payment {
    @Column(name = "card_last_four", nullable = false, length = 4)
    private String cardLastFour;

    protected CardPayment() {
    }
}
```

Conceptual schema:

```sql
CREATE TABLE payments (
    id BIGINT PRIMARY KEY,
    amount DECIMAL(19, 2) NOT NULL,
    payment_type VARCHAR(24)
);

CREATE TABLE card_payments (
    payment_id BIGINT PRIMARY KEY REFERENCES payments(id),
    card_last_four VARCHAR(4) NOT NULL
);
```

JPA allows a discriminator column on the root of a JOINED hierarchy. With JOINED, a discriminator is not required in all mappings; the provider can identify subtypes through the joined tables. If declaring a discriminator, verify that your provider and existing schema support the mapping as expected.

`@PrimaryKeyJoinColumn` explicitly specifies the primary key column in the subclass table that also references the primary key of the root table. If omitted, the provider applies default rules.

## 7. TABLE_PER_CLASS and Discriminators

With `TABLE_PER_CLASS`, each concrete subclass has its own table containing inherited attributes as well. For example, card_payments has id, amount, and card_last_four; bank_transfer_payments has id, amount, and bank_account.

`TABLE_PER_CLASS` does not use a discriminator column in the standard model. Do not declare `@DiscriminatorColumn` expecting to classify rows under this strategy. Polymorphic queries may require a UNION across concrete class tables.

This strategy can fit when concrete classes are few and polymorphic queries are rare, but you must weigh column duplication, unique ID generation, and performance. Certain ID strategies have limitations with TABLE_PER_CLASS; check your database/provider before choosing it.

## 8. When to Use @MappedSuperclass?

If a parent class is only meant to share attributes such as `id`, `createdAt`, and `updatedAt`, without needing polymorphic queries via the parent type, you can use `@MappedSuperclass` instead of entity inheritance.

Example:

```java
@MappedSuperclass
public abstract class AuditableEntity {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private Instant createdAt;
}
```

```java
@Entity
@Table(name = "customers")
public class Customer extends AuditableEntity {
    private String email;
}
```

`@MappedSuperclass` is not an entity and has no table of its own. Attribute mappings are inherited into the child entity's table. You cannot create a repository for AuditableEntity as a root entity, and there are no polymorphic queries through this class.

Choose entity inheritance when subclasses are genuinely entity types in the same hierarchy and need polymorphic behavior. Choose a mapped superclass when you only want to reuse attribute mappings.

## 9. Queries and Performance

Querying via the root entity in SINGLE_TABLE typically reads a single table. With JOINED, the provider may JOIN multiple tables to reconstruct the right subclass. With TABLE_PER_CLASS, querying via the root may use UNION.

Points to evaluate:

- Frequency of queries by root versus by subclass.
- Number of subclasses and specialized attributes.
- Table size and column sparsity.
- JOIN/UNION overhead.
- Constraints that can be enforced per entity type.
- How migrations work when adding or changing subclasses.

Add appropriate indexes for discriminator columns or frequently queried columns if actual metrics show they are needed. Do not add an index merely because a column exists; indexes increase write and storage costs.

## 10. Testing Inheritance Mappings

You can use `@DataJpaTest` to verify saving, reading, and polymorphic queries.

Example:

```java
@DataJpaTest
class PaymentRepositoryTest {

    @Autowired
    private PaymentRepository repository;

    @Autowired
    private TestEntityManager entityManager;

    @Test
    void loadsConcreteTypesThroughRootRepository() {
        CardPayment card = new CardPayment(
                new BigDecimal("120.00"),
                "1234"
        );

        BankTransferPayment transfer = new BankTransferPayment(
                new BigDecimal("250.00"),
                "00123456"
        );

        repository.save(card);
        repository.save(transfer);

        entityManager.flush();
        entityManager.clear();

        List<Payment> payments = repository.findAll();

        assertThat(payments).hasSize(2);
        assertThat(payments)
                .anyMatch(CardPayment.class::isInstance);
        assertThat(payments)
                .anyMatch(BankTransferPayment.class::isInstance);
    }
}
```

The test assumes the root Payment and subclasses are configured in a package scanned by Spring Boot, have constructors as shown, and import JUnit 5, AssertJ, and Spring Data JPA test support. `flush()` pushes data to the database; `clear()` clears the persistence context so the subsequent read must reconstruct entities from the database.

Beyond the test above, also verify:

- Discriminator values are saved accurately for each subclass.
- Reading rows via the root repository instantiates the right concrete class.
- Queries filtering by subtype return the right data.
- Subclass attributes are not lost on update.
- Constraints and migrations work on the target database.

## 11. Common Pitfalls

| Symptom | Common Cause | Resolution |
|---|---|---|
| Entity subclass not recognized | Subclass lacks @Entity or is not scanned | Mark as entity and check package scanning |
| Discriminator value mismatch | Annotation values and data/schema are out of sync | Set explicit values, migrate existing data |
| Subclass row missing required column | SINGLE_TABLE lacks type-specific constraints | Use CHECK constraints or consider JOINED |
| Slow root query | JOIN/UNION or overly large hierarchy | Inspect actual SQL and pick an appropriate strategy |
| Cannot create table after strategy change | Schema migration not updated | Write migrations to convert data and table structure |
| Using @DiscriminatorColumn with TABLE_PER_CLASS | Discriminator is not part of this strategy's standard model | Remove discriminator and use proper mapping |
| Subtype query returns wrong results | Wrong entity name or query type | Use TYPE/TREAT and verify entity names |
| Adding subclass breaks legacy data | New discriminator value or missing migration | Update schema, constraints, and data cleanly |

## 12. Entity Inheritance Design Checklist

- [ ] Mark root and subclasses with `@Entity` when they are entities.
- [ ] Place `@Inheritance` on the root entity.
- [ ] Choose SINGLE_TABLE, JOINED, or TABLE_PER_CLASS based on queries and schema.
- [ ] Place `@DiscriminatorColumn` on the root when the strategy uses a discriminator.
- [ ] Set an explicit `@DiscriminatorValue` on each subclass.
- [ ] Ensure discriminator values are unique and column length is sufficient.
- [ ] Verify nullability/constraints of subclass columns.
- [ ] Manage hierarchy changes via migrations.
- [ ] Test polymorphic saves and loads via the root repository.
- [ ] Inspect SQL and query performance across the hierarchy.

## Conclusion

JPA inheritance maps an entity inheritance tree onto a relational schema. `@Inheritance` selects how data is stored; `@DiscriminatorColumn` declares the column distinguishing entity types; and `@DiscriminatorValue` assigns the value for each type.

SINGLE_TABLE keeps polymorphic queries simple but produces nullable columns; JOINED normalizes data but requires JOINs; TABLE_PER_CLASS stores each concrete class separately and may require UNIONs. Choose a strategy based on data structure, queries, constraints, and operational needs. Explicit discriminator declarations, managed migrations, and testing polymorphic behavior keep the hierarchy stable as the application grows.
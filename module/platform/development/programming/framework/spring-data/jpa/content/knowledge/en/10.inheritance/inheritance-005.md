# TABLE_PER_CLASS Strategy and Polymorphic Queries

JPA supports three entity inheritance mapping strategies: **SINGLE_TABLE**, **JOINED**, and **TABLE_PER_CLASS**. With TABLE_PER_CLASS, each concrete entity class in the hierarchy has its own table. Attributes inherited from the superclass are repeated in each subclass's table.

The strength of this strategy is that reading a specific subclass does not require joining with a parent table. In return, querying on the parent type must aggregate data from multiple tables, usually via UNION or an equivalent polymorphic SQL query. Therefore, TABLE_PER_CLASS should be chosen based on query shapes, data integrity, and database capabilities, not simply out of a desire to split each type into its own table.

This lesson uses a Payment model consisting of CardPayment and BankTransferPayment to explain mapping, polymorphic queries, and practical limitations in Spring Data JPA with Hibernate.

## 1. The Three JPA Inheritance Strategies

An entity hierarchy has a superclass and subclasses. JPA needs to know how their data is stored as tables.

| Strategy | Storage | Characteristics |
|---|---|---|
| SINGLE_TABLE | Entire hierarchy resides in one table, distinguished by a discriminator | Simple polymorphic reads, few joins; subclass-specific columns usually must allow NULL |
| JOINED | Parent table stores shared attributes, each subclass has its own table linked by PK/FK | More normalized schema; reading subclasses usually requires joins |
| TABLE_PER_CLASS | Each concrete class has its own table, each containing inherited attributes as well | Reading one subclass needs no join; querying parent type must merge multiple tables |

Example hierarchy:

```text
                  Payment (abstract)
                       |
              +--------+--------+
              |                 |
         CardPayment      BankTransferPayment
```

With TABLE_PER_CLASS, the schema can be:

```text
card_payments
+----+------------+---------------+----------------+
| id | created_at | amount        | card_last_four |
+----+------------+---------------+----------------+

bank_transfer_payments
+----+------------+---------------+----------------+
| id | created_at | amount        | bank_reference |
+----+------------+---------------+----------------+
```

Both tables contain id, created_at, and amount because those are attributes inherited from Payment. Each table also contains its subclass's own attribute.

## 2. Declaring TABLE_PER_CLASS

The strategy is placed on the root entity using @Inheritance:

```java
import jakarta.persistence.*;
import java.math.BigDecimal;
import java.time.Instant;

@Entity
@Inheritance(strategy = InheritanceType.TABLE_PER_CLASS)
@SequenceGenerator(
    name = "payment_id_generator",
    sequenceName = "payment_id_seq",
    allocationSize = 50
)
public abstract class Payment {

    @Id
    @GeneratedValue(
        strategy = GenerationType.SEQUENCE,
        generator = "payment_id_generator"
    )
    private Long id;

    @Column(nullable = false, precision = 19, scale = 2)
    private BigDecimal amount;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    protected Payment() {
    }

    protected Payment(BigDecimal amount, Instant createdAt) {
        this.amount = amount;
        this.createdAt = createdAt;
    }

    public Long getId() {
        return id;
    }

    public BigDecimal getAmount() {
        return amount;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }
}
```

The root entity must be annotated with @Entity to participate in the hierarchy and support polymorphic queries. The root can be an abstract class so Payment instances cannot be created directly.

First subclass:

```java
@Entity
@Table(name = "card_payments")
public class CardPayment extends Payment {

    @Column(name = "card_last_four", nullable = false, length = 4)
    private String cardLastFour;

    protected CardPayment() {
    }

    public CardPayment(
            BigDecimal amount,
            Instant createdAt,
            String cardLastFour
    ) {
        super(amount, createdAt);
        this.cardLastFour = cardLastFour;
    }

    public String getCardLastFour() {
        return cardLastFour;
    }
}
```

Second subclass:

```java
@Entity
@Table(name = "bank_transfer_payments")
public class BankTransferPayment extends Payment {

    @Column(name = "bank_reference", nullable = false, length = 80)
    private String bankReference;

    protected BankTransferPayment() {
    }

    public BankTransferPayment(
            BigDecimal amount,
            Instant createdAt,
            String bankReference
    ) {
        super(amount, createdAt);
        this.bankReference = bankReference;
    }

    public String getBankReference() {
        return bankReference;
    }
}
```

Key points to note:

- @Inheritance(strategy = InheritanceType.TABLE_PER_CLASS) declares the strategy on the root entity.
- Each concrete subclass has @Entity and can use @Table to specify its own table name.
- The id, amount, and createdAt attributes are inherited and mapped into each child table.
- There is no need to create a payment table solely to hold shared attributes in this strategy.
- No discriminator column is needed as is typical with SINGLE_TABLE; the provider can determine the concrete type based on the source table in polymorphic queries.
- The root entity is still a JPA entity, even as an abstract class. You can query the root to receive instances of subclasses.

## 3. Why Must IDs Be Unique Across the Entire Hierarchy?

A polymorphic query on Payment can return both CardPayment and BankTransferPayment in the same result set. Therefore, entity identity must distinguish records across the entire hierarchy.

If card_payments has id = 100 and bank_transfer_payments also has id = 100, a polymorphic result could contain two different entity types sharing the same ID. This causes issues for the identity map/persistence context and entity management operations.

Hence, IDs must be unique across the entire hierarchy, not just within each table. Sharing a sequence generator on the root is an appropriate approach on databases that support sequences:

```sql
CREATE SEQUENCE payment_id_seq
    START WITH 1
    INCREMENT BY 50;
```

The DDL above illustrates the case where Hibernate uses a pooled allocation size of 50. The actual increment must match the optimizer and Hibernate configuration in use; if using allocationSize = 1, the sequence typically has increment 1. Check migrations and schema validation according to the exact provider/version.

**Do not use IDENTITY for TABLE_PER_CLASS with Hibernate.** IDENTITY allocates IDs independently per table; Hibernate requires a single unique ID space for a polymorphic hierarchy and does not support this identity generation mode in union-subclass mapping. Prefer SEQUENCE on databases that support sequences, or a TABLE generator when specific compatibility requires it. Always verify provider and database support.

## 4. Schema of Each Child Table

Condensed DDL example on PostgreSQL:

```sql
CREATE TABLE card_payments (
    id BIGINT PRIMARY KEY,
    amount NUMERIC(19, 2) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    card_last_four VARCHAR(4) NOT NULL
);

CREATE TABLE bank_transfer_payments (
    id BIGINT PRIMARY KEY,
    amount NUMERIC(19, 2) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    bank_reference VARCHAR(80) NOT NULL
);

CREATE SEQUENCE payment_id_seq
    START WITH 1
    INCREMENT BY 50;
```

Each table has its own primary key, yet ID values are issued from the same sequence. Shared attributes appear duplicated across both tables. Migrations must create the sequence and tables matching the provider configuration.

If using Flyway or Liquibase, make migrations the source of truth for the schema. @Table, @Column, and @SequenceGenerator describe mappings; they do not guarantee production has the right structure when the application runs with ddl-auto=validate.

## 5. Polymorphic Queries Through the Superclass

An important benefit of TABLE_PER_CLASS is the ability to query the root entity to retrieve all payment types:

```java
List<Payment> payments = entityManager
    .createQuery(
        "select p from Payment p order by p.createdAt desc",
        Payment.class
    )
    .getResultList();
```

Even though Payment is an abstract class, JPQL can still query Payment. The provider searches data in the concrete subclass tables and instantiates the right Java type for each result.

With Hibernate, this query is typically implemented via a derived table combining the subclass tables using UNION/UNION ALL or equivalent polymorphic SQL. The exact SQL depends on Hibernate version, dialect, mapping, and query. Columns that do not exist on a subclass may be represented as NULL values in the corresponding select branch.

Results can contain:

- CardPayment for rows fetched from card_payments.
- BankTransferPayment for rows fetched from bank_transfer_payments.

Code can check the actual runtime type:

```java
for (Payment payment : payments) {
    if (payment instanceof CardPayment card) {
        System.out.println(card.getCardLastFour());
    } else if (payment instanceof BankTransferPayment transfer) {
        System.out.println(transfer.getBankReference());
    }
}
```

There is no need to manually query each table and merge lists in Java when the business requirement is genuinely a polymorphic query. Let JPA manage the hierarchy and identity.

## 6. Spring Data Repositories for Root and Subclasses

You can create a repository for the root to perform polymorphic reads:

```java
public interface PaymentRepository
        extends JpaRepository<Payment, Long> {
}
```

Calling:

```java
List<Payment> payments = paymentRepository.findAll();
```

will query the concrete entities in the hierarchy. Because Payment is abstract, you cannot directly instantiate a Payment via new Payment(); saving must use an instance of a subclass.

You can create dedicated repositories for each type:

```java
public interface CardPaymentRepository
        extends JpaRepository<CardPayment, Long> {
}

public interface BankTransferPaymentRepository
        extends JpaRepository<BankTransferPayment, Long> {
}
```

Subclass repositories are usually well suited for creation and specialized queries. The root repository is well suited for use cases that read or process all types of Payment.

A repository method on the root can filter by shared attributes:

```java
List<Payment> findByAmountGreaterThan(BigDecimal amount);
```

The method uses the amount property declared on the root entity. The provider still has to locate matching records across the hierarchy.

## 7. Using TYPE to Filter Subclasses

JPQL provides the TYPE operator to check the actual entity type:

```java
@Query("""
    select p
    from Payment p
    where type(p) = CardPayment
    order by p.createdAt desc
    """)
List<Payment> findCardPayments();
```

The entity type literal CardPayment references the subclass's entity name, not the table name card_payments. You can pass an entity class as a parameter in suitable queries:

```java
TypedQuery<Payment> query = entityManager.createQuery("""
    select p
    from Payment p
    where type(p) = :paymentType
    """, Payment.class);

query.setParameter("paymentType", CardPayment.class);
```

TYPE is useful when a repository or service works with the root but needs to filter to a specific subtype. If a use case only operates on CardPayment, CardPaymentRepository is usually easier to read and can avoid a polymorphic query across the whole hierarchy.

## 8. Using TREAT to Access Subclass-Specific Attributes

The root Payment does not have cardLastFour. If JPQL needs to filter on an attribute present only on CardPayment, TREAT can be used to downcast:

```java
@Query("""
    select p
    from Payment p
    where treat(p as CardPayment).cardLast4 = :last4
    """)
List<Payment> findByCardLastFour(
    @Param("lastFour") String lastFour
);
```

TREAT expresses a condition on a subtype within a polymorphic query. Exact syntax and support for certain downcast forms depend on the JPA provider and version. For specialized queries targeting only CardPayment, querying CardPayment directly is usually simpler:

```java
List<CardPayment> findByCardLastFour(String lastFour);
```

Do not use table or column names inside TREAT; continue using entity types and Java properties.

## 9. Relationships with TABLE_PER_CLASS and Foreign Keys

TABLE_PER_CLASS has an important limitation regarding referential integrity in the database.

Suppose an invoice table wants to reference any Payment. That Payment might live in card_payments or bank_transfer_payments. A standard database only lets a foreign key reference one specific table; it cannot create a single FK pointing to "one of several subclass tables".

Hibernate may support some polymorphic associations using polymorphic query mechanisms, but the database cannot enforce a standard physical FK to a union of tables. This weakens referential protection at the database layer.

If an association targets a single concrete type—e.g., invoice always references CardPayment—you can create an FK to card_payments. If it must reference any Payment and you want clear database FKs, consider JOINED or SINGLE_TABLE to provide a single shared root table.

This is a major architectural trade-off, not just a mapping detail.

## 10. Unique Constraints and Indexes Across the Hierarchy

Each child table can have its own unique constraints, but two independent unique constraints cannot guarantee uniqueness of a value across the entire hierarchy.

For example, if both CardPayment and BankTransferPayment have externalReference, declaring UNIQUE on each table only prevents duplicates within that table. The same externalReference could still appear once in each table.

Similarly, indexes on individual tables speed up queries within that table, yet polymorphic queries still must merge results. The provider may use each branch's index, though UNION and sort/count overhead remain.

If business rules require hierarchy-wide uniqueness, you can:

- Use a shared registry/common table storing the unique externalReference and linking to the concrete record.
- Switch to SINGLE_TABLE or JOINED so there is a root table holding shared keys/attributes.
- Design a centralized code issuance/registration mechanism with proper transactions and constraints.

Do not rely on Java "check if it exists first, then insert" logic when concurrent transactions can run; database constraints or locking mechanisms are required.

## 11. Performance of Polymorphic Queries

Querying a subclass directly usually hits only its corresponding table:

```java
List<CardPayment> cards = cardPaymentRepository.findAll();
```

Querying the root may require merging multiple tables:

```java
List<Payment> all = paymentRepository.findAll();
```

When a hierarchy has many subclasses, polymorphic queries become more complex because the provider must:

1. Read each concrete table branch.
2. Align column counts and types across each branch.
3. Merge the results.
4. Apply filters, sorting, pagination, or counts over the merged result.

This can noticeably affect large lists and reporting queries. TABLE_PER_CLASS is generally suitable when subtype-specific queries dominate, shared attributes rarely change, and few polymorphic associations are needed.

When root queries are frequent, measure the actual SQL. Indexes must be created on each concrete table for important filter/sort attributes. Pagination over a union can also be expensive, especially when counting the entire hierarchy.

## 12. Comparison with SINGLE_TABLE and JOINED

| Criterion | SINGLE_TABLE | JOINED | TABLE_PER_CLASS |
|---|---|---|---|
| Table storing shared attributes | One table | Root table | Repeated in each concrete table |
| Separate tables for subtypes | No | Yes | Yes |
| Discriminator | Usually required | Optional per mapping | Not needed to distinguish source table |
| Reading a single subtype | No join needed | Usually requires join | No join needed |
| Reading the entire hierarchy | One table | Joins root and subtypes | Merges multiple tables |
| FK to root entity | Has root table | Has root table | Hard to enforce a single physical FK |
| Shared hierarchy-wide unique constraint | Can be placed on shared table | Can be placed on root table | Cannot rely solely on per-table unique constraints |
| Duplication of shared attributes | No | No | Yes |
| Polymorphic query complexity | Low | Medium | Can be high with many subtypes |

Do not pick TABLE_PER_CLASS just for "one table per class". If your data has many associations to the superclass, needs hierarchy-wide uniqueness, or frequently queries the root, JOINED or SINGLE_TABLE may fit better.

## 13. Bulk Operations and Polymorphic Updates

When running JPQL bulk update/delete on the root entity, the provider must process the relevant concrete tables. With TABLE_PER_CLASS, one operation on Payment may translate into multiple SQL statements or a complex query structure depending on the provider.

Bulk operations bypass per-entity dirty checking and can leave the persistence context holding stale state. After bulk update/delete, consider clearing or refreshing the EntityManager appropriately. Do not assume a JPQL bulk query on the root is always equivalent to calling setters on individual entities.

If the operation applies only to CardPayment, querying the subtype directly can be clearer and less expensive.

## 14. Testing Mappings and Queries

Write integration tests on the same database type as production to verify:

- Persisting each subclass writes to the right concrete table.
- Inherited fields are saved in each table.
- IDs are unique across the entire hierarchy.
- The root repository returns the right subclass types.
- TYPE filters subtypes accurately.
- TREAT accesses subtype-specific attributes accurately.
- Sorting, pagination, and count work on polymorphic queries.
- Native SQL uses the right physical table/column names.
- Associations to the root do not create false expectations around database FKs.

Polymorphic test example:

```java
@DataJpaTest
class PaymentRepositoryTest {

    @Autowired
    PaymentRepository paymentRepository;

    @Autowired
    CardPaymentRepository cardPaymentRepository;

    @Test
    void rootRepositoryReturnsConcreteSubtypes() {
        cardPaymentRepository.saveAndFlush(
            new CardPayment(
                new BigDecimal("120.00"),
                Instant.parse("2025-01-01T10:00:00Z"),
                "1234"
            )
        );

        List<Payment> payments = paymentRepository.findAll();

        assertThat(payments).hasSize(1);
        assertThat(payments.get(0)).isInstanceOf(CardPayment.class);
    }
}
```

This is an illustrative skeleton; constructors, ID generators, required fields, and test databases must match the actual mapping. If using sequence allocation, create the proper sequence in the test schema or let the test database generate the schema according to the verified configuration.

## 15. Common Pitfalls

| Symptom | Common Cause | Resolution |
|---|---|---|
| Root repository does not find subtype | Subclass lacks @Entity or is outside persistence unit | Check entity scan and inheritance mapping |
| Root query slow for large hierarchy | Provider merges multiple tables | Measure SQL, index each table, or consider another strategy |
| Duplicate IDs across two subclasses | Tables use independent generators | Use a shared generator guaranteeing hierarchy-wide uniqueness |
| Using IDENTITY fails with Hibernate | IDENTITY does not fit union-subclass because IDs must be unique hierarchy-wide | Prefer SEQUENCE/TABLE per provider and database |
| FK cannot reference all subtypes | No shared physical table for root | Consider JOINED/SINGLE_TABLE or a registry table |
| Unique constraint not unique hierarchy-wide | UNIQUE only applies per table | Use a shared/registry table or change inheritance strategy |
| JPQL uses table name | Confusing entity name with table name | JPQL uses entity names; native SQL uses table names |
| TYPE does not filter properly | Wrong entity name or wrong subtype queried | Verify @Entity name and provider query |
| Expensive polymorphic pagination | UNION and count across multiple tables | Measure, narrow subtype scope, or design specialized queries |

## 16. Practice Exercises

1. Create abstract Payment and two entities CardPayment, BankTransferPayment.
2. Place TABLE_PER_CLASS on the root and a separate @Table for each subclass.
3. Create a shared sequence and verify IDs do not collide across the two tables.
4. Create PaymentRepository and verify findAll returns the right subtypes.
5. Write JPQL using TYPE to retrieve only CardPayment.
6. Write a query using TREAT to filter on a subtype-specific attribute.
7. Compare SQL when calling the subtype repository versus the root repository.
8. Create separate unique constraints on both tables and demonstrate they do not enforce hierarchy-wide uniqueness.
9. Attempt to design an FK to the Payment root and explain the database limitation.
10. Measure pagination/count across a multi-table hierarchy and compare with SINGLE_TABLE or JOINED.

**Core principle:** TABLE_PER_CLASS creates a table per concrete entity and repeats inherited attributes. Root queries are polymorphic and usually have to merge multiple tables. Ensure hierarchy-wide unique IDs, account for FKs/unique constraints that cannot span a single shared table, and choose this strategy only when actual query patterns justify it.
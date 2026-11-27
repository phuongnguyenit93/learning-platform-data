# Querying by Parent Class and Handling Subclasses in Spring Data JPA

In an object-oriented model, multiple entities can share common attributes while still having distinct data and behavior. For example, Payment has subclasses CardPayment and BankTransfer. When querying Payment, an application often needs to retrieve all payment types; in other cases, it only wants card transactions or needs to filter on attributes present only in a subclass.

JPA supports entity inheritance and polymorphic queries. Spring Data JPA inherits that capability through repositories. This lesson presents how to model an inheritance hierarchy, query the parent class, filter by actual runtime type using TYPE, access subclass attributes using TREAT, create dedicated subtype repositories, and choose an inheritance strategy.

## 1. What Is Entity Inheritance?

Entity inheritance allows an entity to inherit attributes and mappings from a parent entity. Every entity class in the same hierarchy can be queried via the parent class type if the parent class is an entity.

Payment domain example:

- Payment stores common information: ID, amount, status, and creation timestamp.
- CardPayment adds the last four digits of the card and card network.
- BankTransfer adds the bank code and transfer reference code.

Class diagram:

~~~mermaid
classDiagram
    class Payment {
        Long id
        BigDecimal amount
        PaymentStatus status
        Instant createdAt
    }
    class CardPayment {
        String cardLast4
        String network
    }
    class BankTransfer {
        String bankCode
        String transferReference
    }
    Payment <|-- CardPayment
    Payment <|-- BankTransfer
~~~

Both CardPayment and BankTransfer are Payments, so they can be handled via the Payment type when only common information is needed. When subclass-specific fields are needed, you must access the concrete subtype or use a query with downcasting.

## 2. Declaring the Hierarchy in JPA

JPA places @Inheritance on the root entity. There are three primary strategies:

- SINGLE_TABLE: the entire hierarchy resides in one table, distinguished by a discriminator.
- JOINED: tables for the parent class and each subclass are joined by primary key.
- TABLE_PER_CLASS: each concrete class has its own table, repeating inherited columns.

If no strategy is specified, JPA defaults to SINGLE_TABLE.

### Example Using SINGLE_TABLE

This example clearly shows the discriminator and polymorphic queries:

~~~java
package com.example.payments;

import java.math.BigDecimal;
import java.time.Instant;

import jakarta.persistence.*;

@Entity
@Table(name = "payments")
@Inheritance(strategy = InheritanceType.SINGLE_TABLE)
@DiscriminatorColumn(name = "payment_type")
public abstract class Payment {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, precision = 19, scale = 2)
    private BigDecimal amount;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 20)
    private PaymentStatus status;

    @Column(nullable = false)
    private Instant createdAt;

    protected Payment() {
    }

    protected Payment(
            BigDecimal amount,
            PaymentStatus status,
            Instant createdAt) {
        this.amount = amount;
        this.status = status;
        this.createdAt = createdAt;
    }

    public Long getId() {
        return id;
    }

    public BigDecimal getAmount() {
        return amount;
    }

    public PaymentStatus getStatus() {
        return status;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }
}
~~~

Shared enum:

~~~java
package com.example.payments;

public enum PaymentStatus {
    PENDING,
    COMPLETED,
    FAILED
}
~~~

Subclass CardPayment:

~~~java
package com.example.payments;

import java.math.BigDecimal;
import java.time.Instant;

import jakarta.persistence.Column;
import jakarta.persistence.DiscriminatorValue;
import jakarta.persistence.Entity;

@Entity
@DiscriminatorValue("CARD")
public class CardPayment extends Payment {

    @Column(name = "card_last4", length = 4)
    private String cardLast4;

    @Column(name = "card_network", length = 30)
    private String network;

    protected CardPayment() {
    }

    public CardPayment(
            BigDecimal amount,
            PaymentStatus status,
            Instant createdAt,
            String cardLast4,
            String network) {
        super(amount, status, createdAt);
        this.cardLast4 = cardLast4;
        this.network = network;
    }

    public String getCardLast4() {
        return cardLast4;
    }

    public String getNetwork() {
        return network;
    }
}
~~~

Subclass BankTransfer:

~~~java
package com.example.payments;

import java.math.BigDecimal;
import java.time.Instant;

import jakarta.persistence.Column;
import jakarta.persistence.DiscriminatorValue;
import jakarta.persistence.Entity;

@Entity
@DiscriminatorValue("BANK")
public class BankTransfer extends Payment {

    @Column(name = "bank_code", length = 20)
    private String bankCode;

    @Column(name = "transfer_reference", length = 80)
    private String transferReference;

    protected BankTransfer() {
    }

    public BankTransfer(
            BigDecimal amount,
            PaymentStatus status,
            Instant createdAt,
            String bankCode,
            String transferReference) {
        super(amount, status, createdAt);
        this.bankCode = bankCode;
        this.transferReference = transferReference;
    }

    public String getBankCode() {
        return bankCode;
    }

    public String getTransferReference() {
        return transferReference;
    }
}
~~~

With SINGLE_TABLE, the database has only the payments table. Columns specific to CardPayment and BankTransfer share the same table; rows of one type do not use columns of the other, so those columns usually must allow NULL. The payment_type column determines the actual entity type when Hibernate reads data.

## 3. Distinguishing Parent Entities from @MappedSuperclass

Not every Java parent class is a parent entity.

A **parent entity** is annotated with @Entity and can serve as the root of a hierarchy. It can be queried directly with JPQL and used as the generic type for JpaRepository.

**@MappedSuperclass** only provides mapping attributes for child entities. The class itself is not an entity, has no entity table of its own, and cannot be queried as a root entity.

Example:

~~~java
@MappedSuperclass
public abstract class AuditableEntity {

    @Column(nullable = false, updatable = false)
    private Instant createdAt;

    private Instant updatedAt;
}

@Entity
public class Customer extends AuditableEntity {
    @Id
    @GeneratedValue
    private Long id;
}
~~~

Customer inherits the createdAt and updatedAt attributes, yet you cannot create `JpaRepository<AuditableEntity, Long>` to query all entities extending the mapped superclass. If you need polymorphic queries through the parent class, the parent class must be an @Entity and the hierarchy must be mapped with @Inheritance.

## 4. The Three Inheritance Strategies and Their Impact on Queries

### SINGLE_TABLE

The entire hierarchy is stored in one table, with a discriminator identifying the actual type.

Advantages:

- Parent-class queries are simple, usually requiring no joins.
- Polymorphic queries are typically fast and easy to paginate.
- Few physical tables.

Disadvantages:

- Many columns apply to only certain subclasses and must accept NULL.
- Difficult to enforce per-subtype NOT NULL constraints via standard mapping.
- The table can grow very wide if the hierarchy is large.

### JOINED

The parent class and each subclass have their own tables. Child tables use their primary key simultaneously as a foreign key to the parent table.

Declared on the root:

~~~java
@Entity
@Inheritance(strategy = InheritanceType.JOINED)
public abstract class Payment {
    // Shared attributes.
}
~~~

When querying Payment, the JPA provider must join the parent table with child tables to construct concrete types. Subtype queries may also require joins. This normalizes data better than SINGLE_TABLE, though polymorphic queries can incur multiple joins.

### TABLE_PER_CLASS

Each concrete entity has its own table and repeats inherited attributes:

~~~java
@Entity
@Inheritance(strategy = InheritanceType.TABLE_PER_CLASS)
public abstract class Payment {
    // Shared attributes.
}
~~~

Parent-class queries may require a UNION across child tables. Polymorphic operations, primary keys, and performance optimization must be checked carefully against the database and provider. This strategy is usually chosen less often when the application frequently needs polymorphic queries.

### Comparison

| Criterion | SINGLE_TABLE | JOINED | TABLE_PER_CLASS |
|---|---|---|---|
| Structure | One table for the entire hierarchy | Parent table and child tables | One table per concrete class |
| Discriminator | Commonly used | Optional, not required | No shared table needed |
| Parent-class query | Simple, no joins needed | Usually requires joins | May require UNION |
| Subtype columns | Many nullable columns | Located in child tables | Repeated in each table |
| Normalization | Lower | Better | Has duplication |
| Polymorphic pagination | Usually simple | Depends on joins | Can be complex |
| Suitability | Small hierarchy, frequent polymorphic reads | Want normalized schema | Rare polymorphic queries, more independent concrete classes |

There is no single best strategy for every system. Choose based on the number of subclasses, specialized columns, common query patterns, database capabilities, and performance benchmarks.

## 5. Creating a Repository for the Parent Class

When the root class is an @Entity, you can create a repository typed to Payment:

~~~java
package com.example.payments;

import java.util.List;

import org.springframework.data.jpa.repository.JpaRepository;

public interface PaymentRepository
        extends JpaRepository<Payment, Long> {

    List<Payment> findByStatus(PaymentStatus status);
}
~~~

Calling:

~~~java
List<Payment> payments =
        paymentRepository.findByStatus(PaymentStatus.COMPLETED);
~~~

The repository returns entities in the hierarchy with status COMPLETED, including both CardPayment and BankTransfer. Each element retains its actual runtime subclass type.

This is a polymorphic query: querying by the Payment type includes entities of the concrete subclasses.

You can save a subclass instance through the parent repository:

~~~java
Payment payment = new CardPayment(
        new BigDecimal("125.00"),
        PaymentStatus.PENDING,
        Instant.now(),
        "4242",
        "VISA"
);

Payment saved = paymentRepository.save(payment);
~~~

JPA persists the entity according to its runtime type CardPayment. The parent repository does not turn the object into a plain Payment; it merely defines a general access type.

## 6. Querying the Parent Class with JPQL and Filtering Actual Types with TYPE

JPQL queries using entity names and Java properties, not physical table/column names.

Example retrieving all payments:

~~~java
@Query("select p from Payment p")
List<Payment> findAllPayments();
~~~

If you want only exact CardPayment instances, use the TYPE operator:

~~~java
@Query("""
       select p
       from Payment p
       where type(p) = CardPayment
       """)
List<Payment> findCardPayments();
~~~

TYPE returns the actual entity type. `type(p) = CardPayment` filters specifically to the CardPayment type. If the hierarchy has deeper subclasses such as `CorporateCardPayment extends CardPayment`, that condition does not automatically mean "CardPayment and all its subtypes"; list the required types or structure the query to match the model.

Multiple types can be filtered:

~~~java
@Query("""
       select p
       from Payment p
       where type(p) in (CardPayment, BankTransfer)
       """)
List<Payment> findSupportedPaymentTypes();
~~~

The default entity name is the simple class name. If using `@Entity(name = "CardTxn")`, JPQL must reference CardTxn, not the table name or old Java class name.

TYPE is useful when:

- Fetching data from the parent repository while wanting only one subtype.
- Computing sums or statistics per entity type.
- Applying different business rules per subtype within a single query.
- Returning data into DTOs by entity type.

## 7. Using TREAT to Access Subclass Attributes

TYPE filters by entity type. TREAT downcasts a path expression to a subtype, allowing access to attributes present only on the subclass.

Example finding CardPayments by last four digits:

~~~java
@Query("""
       select p
       from Payment p
       where treat(p as CardPayment).cardLast4 = :last4
       """)
List<Payment> findCardPaymentsByLast4(
        @Param("last4") String last4);
~~~

TREAT interprets p as CardPayment within the expression. If an entity is not a compatible type, it does not satisfy that subtype condition. The query's result type remains Payment because the SELECT returns p.

TYPE can be combined with shared conditions:

~~~java
@Query("""
       select p
       from Payment p
       where type(p) = CardPayment
         and p.status = :status
       """)
List<Payment> findCardsByStatus(
        @Param("status") PaymentStatus status);
~~~

With JOINED, the provider may need to join the child table to read cardLast4. With SINGLE_TABLE, the attribute resides in the same table, yet a discriminator condition is still needed to fetch only the right type. Exact SQL details are generated by the provider.

## 8. Creating a Dedicated Repository for a Subclass

When many operations involve only a single subtype, a dedicated repository gives a cleaner API and more precise return types.

~~~java
package com.example.payments;

import java.util.List;

import org.springframework.data.jpa.repository.JpaRepository;

public interface CardPaymentRepository
        extends JpaRepository<CardPayment, Long> {

    List<CardPayment> findByCardLast4(String cardLast4);

    List<CardPayment> findByNetworkIgnoreCase(String network);
}
~~~

CardPaymentRepository queries only the CardPayment entity. The return type is `List<CardPayment>`, so callers can directly access specialized properties like cardLast4 and network.

Example:

~~~java
List<CardPayment> cards =
        cardPaymentRepository.findByCardLast4("4242");

for (CardPayment card : cards) {
    System.out.println(card.getNetwork());
}
~~~

Dedicated repositories fit well when a subtype has many query methods, services, and specialized use cases. There is no need to create a repository for every subclass if the application only interacts through PaymentRepository and has no subtype-specific queries.

## 9. Derived Queries and Inherited Attributes

Spring Data parses derived query method names against entity properties. The parent repository can use properties declared in Payment:

~~~java
List<Payment> findByStatusAndCreatedAtAfter(
        PaymentStatus status,
        Instant from);
~~~

The status and createdAt attributes are inherited by CardPayment and BankTransfer, so queries on PaymentRepository are valid.

Conversely, cardLast4 is declared only in CardPayment. You cannot arbitrarily add the following method to PaymentRepository:

~~~java
// Invalid if Payment does not declare cardLast4.
List<Payment> findByCardLast4(String cardLast4);
~~~

Spring Data will not find the cardLast4 property on the Payment domain type and typically fails when creating the repository.

There are two proper approaches:

1. Declare findByCardLast4 in CardPaymentRepository.
2. Keep the query on PaymentRepository and use `@Query` with TREAT to downcast.

Example derived query on a subclass:

~~~java
public interface CardPaymentRepository
        extends JpaRepository<CardPayment, Long> {

    List<CardPayment> findByCardLast4AndStatus(
            String cardLast4,
            PaymentStatus status);
}
~~~

Property names in derived queries are Java entity property names, not SQL column names.

## 10. Combining Parent-Class Queries with Pagination

If the payment table is large, avoid loading all Payments into memory. You can paginate on the parent repository:

~~~java
public interface PaymentRepository
        extends JpaRepository<Payment, Long> {

    Page<Payment> findByStatus(
            PaymentStatus status,
            Pageable pageable);
}
~~~

Calling:

~~~java
Pageable pageable = PageRequest.of(
        0,
        20,
        Sort.by(Sort.Direction.DESC, "createdAt")
);

Page<Payment> result =
        paymentRepository.findByStatus(
                PaymentStatus.COMPLETED,
                pageable
        );
~~~

Page includes the current page's data along with total record/page counts. Depending on the query, Spring Data may run an additional COUNT query. If you only need to know whether a next page exists, consider Slice to avoid computing total counts.

When paginating polymorphic queries, the inheritance strategy affects the SQL. JOINED may introduce joins; TABLE_PER_CLASS may use UNION. Inspect the SQL and measure performance on production-like data.

## 11. Querying Subtype DTOs

APIs generally should not return entities directly. You can project only the needed data into a DTO. For a concrete payment type, JPQL can use TREAT:

~~~java
public record CardPaymentSummary(
        Long id,
        BigDecimal amount,
        String cardLast4,
        String network
) {
}
~~~

Query example:

~~~java
@Query("""
       select new com.example.payments.CardPaymentSummary(
           p.id,
           p.amount,
           treat(p as CardPayment).cardLast4,
           treat(p as CardPayment).network
       )
       from Payment p
       where type(p) = CardPayment
       """)
List<CardPaymentSummary> findCardSummaries();
~~~

JPQL constructor expressions require the fully qualified DTO class name and parameters matching the constructor order and types. If a query returns multiple subtypes with different structures, consider a shared DTO with a type field or splitting queries per subtype rather than creating a DTO packed with nullable fields.

## 12. Entity Associations Pointing to the Parent Class

Another entity can reference Payment:

~~~java
@Entity
public class Refund {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(optional = false)
    private Payment originalPayment;

    @Column(nullable = false, precision = 19, scale = 2)
    private BigDecimal amount;

    protected Refund() {
    }
}
~~~

originalPayment can reference a CardPayment or a BankTransfer. When loading Refund, Hibernate can reconstruct the right Payment subtype according to the inheritance mapping. If specialized attributes are needed, check the type or use TREAT in queries.

Do not use instanceof as a database querying mechanism. instanceof only checks objects already in the JVM; it does not filter data in the database. Use TYPE/TREAT when you want to filter at the query layer.

## 13. Choosing a Strategy by Workload

Evaluate both structure and actual queries:

- Choose SINGLE_TABLE when the hierarchy is fairly compact, parent-class queries are frequent, and nullable subtype columns are acceptable.
- Choose JOINED when you want each subtype to have its own table/columns and a normalized schema; check join overhead for polymorphic queries.
- Choose TABLE_PER_CLASS when concrete classes rarely need shared queries via the root; evaluate UNIONs, keys, and provider support.
- If you only want to reuse audit or common attributes without needing polymorphic queries, consider @MappedSuperclass.
- If subclasses differ by only a few data values, consider an enum or composition instead of inheritance.
- If behavior varies independently of data structure, composition is usually more flexible than a deep hierarchy.

Do not pick a strategy solely based on having fewer or more tables. Measure critical queries, inspect execution plans, and check how the provider generates SQL.

## 14. Common Pitfalls

| Error | Cause | Fix |
|---|---|---|
| Cannot query parent class | Parent class is @MappedSuperclass | Use @Entity if polymorphic root queries are needed |
| Subclass property not found | Derived query declared on parent repository | Use subtype repository or JPQL TREAT |
| JPQL does not recognize entity name | Used table name or wrong @Entity(name) | Use the entity name in JPQL |
| Query returns unexpected multiple types | Queried root without subtype filtering | Use TYPE or a subclass repository |
| Subtype query is slow | JOINED has many joins or TABLE_PER_CLASS uses UNION | Check SQL, indexes, and execution plans |
| Subtype columns are NULL | SINGLE_TABLE shares one table | Design appropriate nullability/constraints or consider JOINED |
| Discriminator mismatch | @DiscriminatorValue inconsistent with data | Check mappings and migrations |
| Casting object throws ClassCastException | Result is not the assumed subtype | Use TYPE/TREAT or check type before casting |
| Cannot query shared parent class | Only used @MappedSuperclass | Create a root entity if polymorphic queries are genuinely needed |

## 15. Testing Polymorphic Queries

Use `@DataJpaTest` to verify the parent repository returns the right subtypes and subtype-filtering queries work.

Test example:

~~~java
package com.example.payments;

import static org.assertj.core.api.Assertions.assertThat;

import java.math.BigDecimal;
import java.time.Instant;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;

@DataJpaTest
class PaymentRepositoryTest {

    @Autowired
    private PaymentRepository paymentRepository;

    @Autowired
    private CardPaymentRepository cardPaymentRepository;

    @Test
    void baseRepositoryReturnsAllSubtypes() {
        paymentRepository.save(new CardPayment(
                new BigDecimal("100.00"),
                PaymentStatus.COMPLETED,
                Instant.parse("2026-01-01T10:00:00Z"),
                "4242",
                "VISA"
        ));

        paymentRepository.save(new BankTransfer(
                new BigDecimal("200.00"),
                PaymentStatus.COMPLETED,
                Instant.parse("2026-01-02T10:00:00Z"),
                "VCB",
                "REF-001"
        ));

        var payments = paymentRepository.findByStatus(
                PaymentStatus.COMPLETED);

        assertThat(payments).hasSize(2);
        assertThat(payments)
                .anyMatch(CardPayment.class::isInstance);
        assertThat(payments)
                .anyMatch(BankTransfer.class::isInstance);
    }

    @Test
    void subtypeRepositoryReturnsOnlyCardPayments() {
        paymentRepository.save(new CardPayment(
                new BigDecimal("100.00"),
                PaymentStatus.PENDING,
                Instant.parse("2026-01-01T10:00:00Z"),
                "4242",
                "VISA"
        ));

        var cards = cardPaymentRepository.findByCardLast4("4242");

        assertThat(cards).hasSize(1);
        assertThat(cards.get(0).getNetwork()).isEqualTo("VISA");
    }
}
~~~

The first test verifies that querying from the root returns both subtypes. The second confirms the child repository returns only CardPayment. You can add tests for TYPE/TREAT, pagination, discriminators, and queries on JOINED/TABLE_PER_CLASS if the project uses those strategies.

When testing with `@DataJpaTest`, an embedded database may differ from the production database. To verify inheritance strategy SQL or indexes, run integration tests against the same database engine used in deployment.

## 16. Self-Assessment Checklist

- [ ] Can explain entity inheritance and polymorphic queries.
- [ ] Distinguish an `@Entity` root from `@MappedSuperclass`.
- [ ] Know that `@Inheritance` is placed on the root entity.
- [ ] Distinguish SINGLE_TABLE, JOINED, and TABLE_PER_CLASS.
- [ ] Can create the Payment, CardPayment, and BankTransfer hierarchy.
- [ ] Can create a repository for the parent class and understand results include subclasses.
- [ ] Can query specific subtypes using TYPE.
- [ ] Can use TREAT to filter attributes present only on subclasses.
- [ ] Know why derived queries on the parent class cannot directly reference subclass-only fields.
- [ ] Can create dedicated subtype repositories when needed.
- [ ] Can use Page/Slice to paginate polymorphic queries.
- [ ] Know how to write DTO projections for a subtype.
- [ ] Can test polymorphic query behavior and the actual strategy.

## 17. Conclusion

When entities use inheritance, the parent class's repository can query polymorphically and return subclass instances. This is a convenient way to handle shared data without knowing every subtype in advance.

Use TYPE when you need to filter by actual entity type, TREAT when you need to access subclass attributes in JPQL, and dedicated repositories when a subtype has many specialized query methods. `@MappedSuperclass` only reuses mappings and is not a root entity for querying. Choose SINGLE_TABLE, JOINED, or TABLE_PER_CLASS based on data structure and workload, then verify actual SQL with tests and execution plans.
# Polymorphic Queries with TYPE and TREAT

## Objectives

When entities participate in an inheritance hierarchy, a query on the parent entity in JPA typically returns instances of subclasses as well. This is a **polymorphic query**. JPQL provides two important expressions for working with hierarchies:

- `TYPE(entity)` checks the actual entity type of a row and enables filtering by entity type.
- `TREAT(path AS Subtype)` downcasts an entity or association path to a subtype so you can access attributes defined only on the subclass.

For example, a payment system has a parent entity `Payment` and two child entities `CardPayment` and `BankTransferPayment`. The application can query all Payments, retrieve only `CardPayment`s, or search by `cardLastFour`, which exists only on `CardPayment`.

After this lesson, you will be able to:

- Understand polymorphic queries in JPQL.
- Use `TYPE` to filter by entity type.
- Use `TREAT` to access subtype attributes and relationships.
- Distinguish entity type from discriminator values in the database.
- Combine `TYPE`/`TREAT` with JOINs, predicates, and repository `@Query`.
- Understand how inheritance strategies affect generated SQL.
- Test subtype queries and resolve common errors.

Examples use Java 17+, Spring Boot 3.x, Jakarta Persistence, and Spring Data JPA.

## 1. What is a Polymorphic Query?

Suppose we have a hierarchy:

- `Payment`: parent entity containing ID, amount, and creation timestamp.
- `CardPayment`: card payment adding the last four card digits.
- `BankTransferPayment`: bank transfer adding the recipient bank account.

A JPQL query on `Payment` is polymorphic:

```java
select p
from Payment p
```

Results can include both `CardPayment` and `BankTransferPayment`. When the provider loads each row, it instantiates the concrete entity class matching the row data and inheritance mapping.

This is the default behavior when querying a parent entity in JPA. When you want only one subtype or need subclass-specific attributes, use `TYPE` or `TREAT`.

## 2. Example Entity Hierarchy

The example below uses the `SINGLE_TABLE` strategy to illustrate discriminators. Both `TYPE` and `TREAT` are JPQL features; their usage is not restricted to `SINGLE_TABLE`.

### 2.1. Parent Entity Payment

```java
package com.example.demo.payment;

import jakarta.persistence.*;
import java.math.BigDecimal;
import java.time.Instant;

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

    @Column(nullable = false)
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

### 2.2. Subclass CardPayment

```java
package com.example.demo.payment;

import jakarta.persistence.*;

import java.math.BigDecimal;
import java.time.Instant;

@Entity
@DiscriminatorValue("CARD")
public class CardPayment extends Payment {

    @Column(name = "card_last_four", length = 4)
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

### 2.3. Subclass BankTransferPayment

```java
package com.example.demo.payment;

import jakarta.persistence.*;

import java.math.BigDecimal;
import java.time.Instant;

@Entity
@DiscriminatorValue("BANK_TRANSFER")
public class BankTransferPayment extends Payment {

    @Column(name = "bank_account", length = 40)
    private String bankAccount;

    protected BankTransferPayment() {
    }

    public BankTransferPayment(
            BigDecimal amount,
            Instant createdAt,
            String bankAccount
    ) {
        super(amount, createdAt);
        this.bankAccount = bankAccount;
    }

    public String getBankAccount() {
        return bankAccount;
    }
}
```

Both the root entity and subclasses are annotated with `@Entity`. Each subclass has its own discriminator value so the provider can identify the entity type in the shared table.

Repository:

```java
package com.example.demo.payment;

import org.springframework.data.jpa.repository.JpaRepository;

public interface PaymentRepository
        extends JpaRepository<Payment, Long> {
}
```

## 3. TYPE: Checking the Actual Entity Type

`TYPE` is a JPQL type expression. It returns the actual entity type of the given entity expression. The result can be compared against an entity type literal in JPQL.

Example retrieving only card payments:

```java
@Query("""
       select p
       from Payment p
       where type(p) = CardPayment
       """)
List<Payment> findCardPayments();
```

In this query:

- `p` is the alias for the `Payment` entity.
- `TYPE(p)` resolves the actual entity type of each payment.
- `CardPayment` is an entity type literal corresponding to the entity name in the mapping.
- The return type remains `List<Payment>`; each element at runtime can be a `CardPayment` instance.

You can filter by multiple subtypes:

```java
@Query("""
       select p
       from Payment p
       where type(p) in (CardPayment, BankTransferPayment)
       """)
List<Payment> findSupportedPaymentTypes();
```

### 3.1. What is an Entity Type Literal?

In JPQL, `CardPayment` is an entity type literal—not a discriminator string and not Java syntax like `CardPayment.class`.

If an entity declares a custom entity name:

```java
@Entity(name = "CardTransaction")
public class CardPayment extends Payment {
    // ...
}
```

then JPQL uses the entity name `CardTransaction`:

```java
@Query("""
       select p
       from Payment p
       where type(p) = CardTransaction
       """)
List<Payment> findCardTransactions();
```

Table names in `@Table` and values in `@DiscriminatorValue` do not replace entity names in `TYPE` expressions.

### 3.2. TYPE and Discriminator Values Are Different

In the mapping example:

```java
@DiscriminatorValue("CARD")
public class CardPayment extends Payment {
}
```

The JPQL query still writes:

```java
where type(p) = CardPayment
```

Do not write:

```java
where type(p) = 'CARD'
```

`CARD` is the discriminator value used in the schema/provider mapping. `CardPayment` is the entity type literal used by JPQL. Keeping queries at the entity level decouples code from how discriminators are stored.

### 3.3. TYPE Compares Exact Types

`TYPE(p) = CardPayment` tests whether the entity has the exact entity type `CardPayment`. If the hierarchy has deeper subclasses, such as `PremiumCardPayment extends CardPayment`, `TYPE` returns the concrete type of that entity; comparing equal to `CardPayment` should not be assumed to mean "assignable to `CardPayment`."

When you want to narrow a path to a subtype and include its own subclasses, `TREAT` is more appropriate. Design conditions to match business intent: exact type vs. an inheritance branch.

## 4. TREAT: Downcasting an Entity Path in JPQL

In Java, you can use `instanceof` and cast an object to access subclass properties. In JPQL, `TREAT` downcasts an entity path to a subtype.

Syntax:

```text
TREAT(<entity_or_association_path> AS <Subtype>)
```

Example:

```java
@Query("""
       select p
       from Payment p
       where treat(p as CardPayment).cardLastFour = :lastFour
       """)
List<Payment> findByCardLastFour(
        @Param("lastFour") String lastFour
);
```

`TREAT(p AS CardPayment)` grants access to `cardLastFour`, which is declared only on `CardPayment`.

Semantically, the query matches only Payments that can be treated as `CardPayment` (including entities in that subtype branch). For entities not belonging to that subtype, the treated path has no matching value, so the WHERE comparison does not match.

### 4.1. TYPE and TREAT Solve Different Problems

| Expression | Purpose | Example |
|---|---|---|
| `TYPE(p)` | Retrieve actual entity type for comparison/filtering | `TYPE(p) = CardPayment` |
| `TREAT(p AS CardPayment)` | Narrow path to subtype to access subtype-specific attributes | `TREAT(p AS CardPayment).cardLastFour` |

Use `TYPE` when asking "which exact type is this entity?". Use `TREAT` when asking "along this subtype branch, access its specific attribute or association".

You can combine both expressions, though many queries only need `TREAT`:

```java
@Query("""
       select p
       from Payment p
       where type(p) = CardPayment
         and treat(p as CardPayment).cardLastFour = :lastFour
       """)
List<Payment> findExactCardTypeByLastFour(
        @Param("lastFour") String lastFour
);
```

The `TYPE` condition in this example restricts results strictly to `CardPayment`. To include classes extending `CardPayment`, consider using only `TREAT`.

## 5. TREAT on Association Paths

`TREAT` can be applied to entity-valued association paths. For example, an order references `Payment`, yet only some orders have a `CardPayment`.

Entity `PurchaseOrder`:

```java
@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "payment_id")
    private Payment payment;

    protected PurchaseOrder() {
    }

    public Long getId() {
        return id;
    }

    public Payment getPayment() {
        return payment;
    }
}
```

Query finding orders by last four card digits:

```java
@Query("""
       select o
       from PurchaseOrder o
       where treat(o.payment as CardPayment).cardLastFour = :lastFour
       """)
List<PurchaseOrder> findOrdersPaidByCard(
        @Param("lastFour") String lastFour
);
```

`o.payment` is an association declared with type `Payment`. `TREAT` downcasts that association to `CardPayment` to access `cardLastFour`.

This is useful when an association points to the root entity of a hierarchy, while a query needs an attribute available only on one subtype.

## 6. TREAT in JOIN over Collection Associations

Suppose `Customer` has a `payments` collection holding multiple `Payment`s:

```java
@OneToMany(mappedBy = "customer")
private List<Payment> payments = new ArrayList<>();
```

To JOIN only elements that are `CardPayment`, you can use `TREAT` on the collection path:

```java
@Query("""
       select distinct c
       from Customer c
       join treat(c.payments as CardPayment) p
       where p.cardLastFour = :lastFour
       """)
List<Customer> findCustomersByCardLastFour(
        @Param("lastFour") String lastFour
);
```

Here:

- `c.payments` is a collection association whose element type is declared as `Payment`.
- `TREAT(c.payments AS CardPayment)` narrows the collection elements to `CardPayment`.
- Alias `p` can access `cardLastFour`.
- `distinct` eliminates duplicate customers when a customer has multiple matching payments.

The property names and mappings in the example must exist in your actual entities. For a single-valued association, use `TREAT` on the single path as in the previous section; for collection associations, use the appropriate `JOIN TREAT` syntax.

## 7. TREAT in SELECT and Query Expressions

`TREAT` is a JPQL expression usable in path-allowed expression positions. When using it in `SELECT`, consider the return type and what happens when an entity does not belong to the specified subtype.

Conceptual example:

```java
@Query("""
       select treat(p as CardPayment)
       from Payment p
       where type(p) = CardPayment
       """)
List<CardPayment> findCardPaymentEntities();
```

The `TYPE` condition ensures results contain only entities of exact type `CardPayment` in this example. If `TREAT` is used without a filter, entities not belonging to the subtype may yield null for the treated path; define the return type and null handling clearly.

In most repository methods, the cleanest approach is selecting the root entity and using `TREAT` in `WHERE` or `JOIN` to filter by subclass attributes. Only select `TREAT` in `SELECT` when subtype results are truly required and tested against your mapping and provider.

## 8. Impact of Inheritance Strategy

JPQL `TYPE`/`TREAT` syntax keeps the same semantics across standard inheritance strategies, though the SQL generated by the provider differs.

### 8.1. SINGLE_TABLE

All subclasses reside in one table. The provider typically uses the discriminator column to identify entity types and generate subtype filters. `TYPE`/`TREAT` can usually execute without joining subclass tables.

The advantage is simpler polymorphic queries. On the downside, the table may have many nullable columns for subclass-specific attributes.

### 8.2. JOINED

Parent and child attributes reside in separate tables. When accessing subclass attributes via `TREAT`, the provider may need to JOIN subclass tables for filtering or reading data.

Polymorphic queries over the root may require multiple joins. Inspect SQL and execution plans when hierarchies are large or queries run frequently.

### 8.3. TABLE_PER_CLASS

Each concrete subclass has its own table. Polymorphic queries over the root may require `UNION`. `TYPE`/`TREAT` preserve their JPQL semantics, though generated SQL can become more complex and provider-dependent.

The inheritance strategy does not alter how `TYPE`/`TREAT` are written in JPQL. It changes the underlying schema layout and execution cost.

## 9. Complete Repository

Example repository combining these patterns:

```java
package com.example.demo.payment;

import java.util.List;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface PaymentRepository
        extends JpaRepository<Payment, Long> {

    // Polymorphic query: can return all concrete subtypes.
    @Query("""
           select p
           from Payment p
           order by p.createdAt desc
           """)
    List<Payment> findAllPayments();

    // Filter by exact entity type CardPayment.
    @Query("""
           select p
           from Payment p
           where type(p) = CardPayment
           """)
    List<Payment> findCardPayments();

    // Filter by a CardPayment-specific attribute.
    @Query("""
           select p
           from Payment p
           where treat(p as CardPayment).cardLastFour = :lastFour
           """)
    List<Payment> findByCardLastFour(
            @Param("lastFour") String lastFour
    );

    // Filter by multiple entity types.
    @Query("""
           select p
           from Payment p
           where type(p) in (CardPayment, BankTransferPayment)
           """)
    List<Payment> findKnownPaymentTypes();
}
```

Methods return `List<Payment>` because the query selects the root entity `Payment`. When reading each element, you can check subtypes with Java `instanceof` if application logic genuinely needs subtype-specific handling:

```java
for (Payment payment : paymentRepository.findCardPayments()) {
    if (payment instanceof CardPayment cardPayment) {
        System.out.println(cardPayment.getCardLastFour());
    }
}
```

In many cases, the service converts results into DTOs so the API does not depend on the entity hierarchy.

## 10. Testing TYPE and TREAT

Test both expressions across multiple subtypes. Example using `@DataJpaTest`:

```java
@DataJpaTest
class PaymentRepositoryTest {

    @Autowired
    private PaymentRepository repository;

    @Autowired
    private TestEntityManager entityManager;

    @Test
    void typeFiltersExactEntityType() {
        repository.save(new CardPayment(
                new BigDecimal("120.00"),
                Instant.parse("2026-01-01T00:00:00Z"),
                "1234"
        ));

        repository.save(new BankTransferPayment(
                new BigDecimal("250.00"),
                Instant.parse("2026-01-02T00:00:00Z"),
                "00123456"
        ));

        entityManager.flush();
        entityManager.clear();

        List<Payment> cards = repository.findCardPayments();

        assertThat(cards).hasSize(1);
        assertThat(cards.get(0)).isInstanceOf(CardPayment.class);
    }

    @Test
    void treatFiltersBySubtypeProperty() {
        repository.save(new CardPayment(
                new BigDecimal("120.00"),
                Instant.parse("2026-01-01T00:00:00Z"),
                "1234"
        ));

        repository.save(new BankTransferPayment(
                new BigDecimal("250.00"),
                Instant.parse("2026-01-02T00:00:00Z"),
                "00123456"
        ));

        entityManager.flush();
        entityManager.clear();

        List<Payment> result = repository.findByCardLastFour("1234");

        assertThat(result).hasSize(1);
        assertThat(result.get(0)).isInstanceOf(CardPayment.class);
    }
}
```

This test example assumes imports for JUnit 5, AssertJ, Spring Boot JPA test support, `BigDecimal`, `Instant`, and configured entities/repository. `flush()` sends changes to the database; `clear()` forces the query to read fresh from the database rather than returning instances already managed in the persistence context.

Consider adding tests for:

- No matching subtypes.
- `TYPE` with each subclass.
- `TREAT` on single-valued and collection associations if the application uses those queries.
- Multi-level inheritance hierarchies.
- Custom discriminator values and custom entity names.
- Every inheritance strategy used by the application.

When queries use `TREAT` on collections or involve multiple joins, test with the exact JPA provider and version deployed in production. Embedded databases validate JPQL syntax, but cannot substitute for performance testing on a production database.

## 11. Common Errors and Fixes

| Symptom | Cause | Solution |
|---|---|---|
| `TYPE` cannot find entity type | Using table name, class name mismatching entity name, or discriminator string | Use the entity name in JPQL |
| `TYPE` query returns fewer results than expected | Equality checks exact type | Use `TYPE` for exact type; use `TREAT` when a subtype branch is desired |
| Cannot access subclass attribute | Query uses only the parent entity alias | Wrap with `TREAT` before the subclass-specific property |
| `TREAT` matches no entities | Actual entity does not belong to the specified subtype | Verify mapping and subtype data |
| Subtype association query error | Invalid association path or `TREAT` syntax | Verify association type and JPQL path |
| Duplicate results after collection JOIN | One parent matches multiple collection elements | Use `DISTINCT` if semantics require unique parents |
| Overly complex SQL | `JOINED`/`TABLE_PER_CLASS` generates JOINs/UNIONs | Inspect SQL, indexes, and inheritance strategy |
| Provider reports `TREAT` unsupported | JPA/provider too old or wrong grammar version | Use JPA 2.1+ and check provider version |
| Query with discriminator literal fails | Confusing discriminator value with entity type literal | Use the entity name such as `CardPayment` |

## 12. Version and Compatibility Notes

`TYPE` is a JPQL expression for checking entity types in an inheritance hierarchy. `TREAT` was added in JPA 2.1 to support entity/path downcasting in queries. Spring Boot 3.x uses Jakarta Persistence; verify API/provider versions when maintaining older applications.

Points to check when upgrading:

- Import `jakarta.persistence.*` in Spring Boot 3.x; Spring Boot 2.x projects typically use `javax.persistence.*`.
- `TREAT` syntax on associations/collections must be supported by the specific provider and version.
- Entity names in queries must match `@Entity(name = ...)` if customized.
- Queries must use Java property names, not database column names.
- Re-test queries after changing inheritance strategies or discriminator mappings.

## 13. Pre-Production Checklist

- [ ] Does querying the root entity actually need to return all subtypes?
- [ ] Use `TYPE` when exact entity type comparison is needed.
- [ ] Use `TREAT` when accessing subtype-specific attributes/associations.
- [ ] Entity type literals match entity names, not discriminator values.
- [ ] Association paths and collection paths are properly declared on entities.
- [ ] Behavior when an entity is not of the treated subtype is well-defined.
- [ ] Use `DISTINCT` when collection JOINs can produce duplicate results.
- [ ] Inspect generated SQL against the actual inheritance strategy.
- [ ] Test on the JPA provider and version used in deployment.
- [ ] Never concatenate user input into JPQL; use bind parameters.

## Conclusion

`TYPE` and `TREAT` make querying inheritance hierarchies in JPQL explicit. `TYPE` inspects the actual entity type and fits filtering for an exact entity kind. `TREAT` narrows an entity or association path to a subtype so you can access subclass-specific attributes.

When writing queries, use entity names in `TYPE`, use `TREAT` for downcasting, and bind all parameters. Combining these expressions with JOINs, repository `@Query`, and provider-level tests keeps polymorphic queries readable, type-safe, and reliable.
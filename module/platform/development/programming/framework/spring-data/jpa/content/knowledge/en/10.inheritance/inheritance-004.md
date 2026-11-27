# JOINED Strategy and Table Join Costs in Spring Data JPA

JPA provides several ways to map inheritance between entity classes and relational tables. With the **JOINED** strategy, each entity class in the inheritance hierarchy has its own table; the subclass table uses its primary key simultaneously as a foreign key referencing the parent class's table. This normalizes data and keeps specialized columns in their proper tables, but queries that assemble an entity across multiple inheritance levels often require joining multiple tables.

Be sure to distinguish **JOINED inheritance** from an association join table. JOINED is a way to store *is-a* relationships between classes in a hierarchy. `@JoinTable` is typically used to store an association such as many-to-many or certain unidirectional relationships. The two mechanisms have different purposes and schema structures.

This document uses Jakarta Persistence (`jakarta.persistence`) and Spring Data JPA in Spring Boot 3 / Spring Framework 6 and later. Older Spring Boot 2 projects typically use the `javax.persistence` namespace.

## 1. The Three JPA Inheritance Strategies

JPA has three common strategies declared via `@Inheritance`:

| Strategy | Table Structure | How Attributes Are Stored | Query Characteristics |
|---|---|---|---|
| `SINGLE_TABLE` | One table for the entire hierarchy | Parent and all subclass columns reside in the same table | Fewer JOINs; subtype-specific columns usually must be nullable |
| `JOINED` | Each entity class in the hierarchy has its own table | Subclass table holds shared PK and FK to parent table | Good normalization; polymorphic queries may JOIN multiple tables |
| `TABLE_PER_CLASS` | Each concrete class has its own table containing inherited attributes too | Parent attributes may be repeated across child tables | Querying the parent class usually requires UNION or an equivalent mechanism |

`SINGLE_TABLE` typically reduces JOINs when reading, but the table has many nullable columns and can make per-subtype constraints difficult. `TABLE_PER_CLASS` avoids parent-child JOINs when querying individual subtypes, but duplicates shared data and polymorphic queries may need UNION. `JOINED` balances normalization with polymorphic querying, at the expense of table join costs.

JPA defaults to `SINGLE_TABLE` if no strategy is declared. Explicitly declare `@Inheritance(strategy = InheritanceType.JOINED)` when you want to use JOINED.

## 2. Data Structure of JOINED

Suppose a system has a general payment type and two concrete types:

- `Payment`: parent entity class containing ID, amount, and creation timestamp.
- `CardPayment`: card payment with last four digits and authorization reference.
- `BankTransferPayment`: bank transfer with bank code and destination account number.

With JOINED, the schema can be represented as follows:

```sql
create table payment (
    id bigint primary key,
    amount decimal(19, 2) not null,
    created_at timestamp not null
);

create table card_payment (
    id bigint primary key,
    card_last4 varchar(4) not null,
    authorization_code varchar(80),
    constraint fk_card_payment_payment
        foreign key (id) references payment(id)
);

create table bank_transfer_payment (
    id bigint primary key,
    bank_code varchar(20) not null,
    destination_account varchar(40) not null,
    constraint fk_bank_transfer_payment
        foreign key (id) references payment(id)
);
```

A CardPayment is stored across two rows with the same ID:

```text
payment
+----+--------+---------------------+
| id | amount | created_at          |
+----+--------+---------------------+
| 10 | 250.00 | 2026-11-09 10:00:00 |
+----+--------+---------------------+

card_payment
+----+-------------+-------------------+
| id | card_last4  | authorization_code|
+----+-------------+-------------------+
| 10 | 4242        | AUTH-001          |
+----+-------------+-------------------+
```

The `card_payment.id` column is both the primary key of the child table and a foreign key to `payment.id`. Because the primary key is unique, one CardPayment row corresponds to at most one Payment row. The child table does not generate a separate independent ID for the same entity.

If there is an intermediate entity class in the hierarchy, such as `OnlinePayment extends Payment`, a table for the intermediate class may also exist. An entity of a leaf class may require a row in each entity table along the inheritance chain.

## 3. Mapping JOINED with Annotations

### 3.1. Parent Entity Class

```java
import jakarta.persistence.*;
import java.math.BigDecimal;
import java.time.Instant;

@Entity
@Table(name = "payment")
@Inheritance(strategy = InheritanceType.JOINED)
public abstract class Payment {

    @Id
    @GeneratedValue(strategy = GenerationType.SEQUENCE,
                    generator = "payment_seq")
    @SequenceGenerator(
        name = "payment_seq",
        sequenceName = "payment_seq",
        allocationSize = 50
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

`@Inheritance(strategy = JOINED)` is placed on the root entity of the hierarchy. Subclasses are entities that extend the root. Attributes declared on the parent class are stored in the parent table; attributes declared on a subclass are stored in that subclass's table.

The example uses a sequence to illustrate allocating IDs before insert. The ID strategy depends on the database and provider. With `IDENTITY`, the provider may have to insert the parent row first to obtain the ID before inserting the child row; that can affect batching. There is no single optimal generator for every database.

### 3.2. Subclass CardPayment

```java
@Entity
@Table(name = "card_payment")
@PrimaryKeyJoinColumn(
    name = "id",
    referencedColumnName = "id"
)
public class CardPayment extends Payment {

    @Column(name = "card_last4", nullable = false, length = 4)
    private String cardLast4;

    @Column(name = "authorization_code", length = 80)
    private String authorizationCode;

    protected CardPayment() {
    }

    public CardPayment(
            BigDecimal amount,
            Instant createdAt,
            String cardLast4,
            String authorizationCode) {
        super(amount, createdAt);
        this.cardLast4 = cardLast4;
        this.authorizationCode = authorizationCode;
    }

    public String getCardLast4() {
        return cardLast4;
    }

    public String getAuthorizationCode() {
        return authorizationCode;
    }
}
```

### 3.3. Subclass BankTransferPayment

```java
@Entity
@Table(name = "bank_transfer_payment")
@PrimaryKeyJoinColumn(
    name = "id",
    referencedColumnName = "id"
)
public class BankTransferPayment extends Payment {

    @Column(name = "bank_code", nullable = false, length = 20)
    private String bankCode;

    @Column(name = "destination_account",
            nullable = false, length = 40)
    private String destinationAccount;

    protected BankTransferPayment() {
    }

    public BankTransferPayment(
            BigDecimal amount,
            Instant createdAt,
            String bankCode,
            String destinationAccount) {
        super(amount, createdAt);
        this.bankCode = bankCode;
        this.destinationAccount = destinationAccount;
    }

    public String getBankCode() {
        return bankCode;
    }

    public String getDestinationAccount() {
        return destinationAccount;
    }
}
```

`@PrimaryKeyJoinColumn` explicitly specifies the PK/FK column in the child table and the referenced column in the parent table. If omitted, the provider applies default names based on the mapping; declaring it explicitly makes schemas and migrations easier to read.

The code snippets above are entity fragments that require Jakarta Persistence dependencies, a provider (such as Hibernate), DataSource configuration, and corresponding imports in a Spring project. They are not standalone Java programs runnable simply with `javac`.

## 4. Discriminators in JOINED

A discriminator helps the provider identify the subtype of a row in the hierarchy. With JOINED, a discriminator column can be declared on the root entity:

```java
@Entity
@Table(name = "payment")
@Inheritance(strategy = InheritanceType.JOINED)
@DiscriminatorColumn(
    name = "payment_type",
    discriminatorType = DiscriminatorType.STRING,
    length = 30
)
public abstract class Payment {
    // id, amount, createdAt
}
```

Subtypes can specify their values:

```java
@Entity
@Table(name = "card_payment")
@DiscriminatorValue("CARD")
public class CardPayment extends Payment {
    // card-specific fields
}

@Entity
@Table(name = "bank_transfer_payment")
@DiscriminatorValue("BANK_TRANSFER")
public class BankTransferPayment extends Payment {
    // transfer-specific fields
}
```

A discriminator does not replace the child tables and linked PK/FK of JOINED. It is subtype identification metadata; exact usage, DDL, and SQL depend on the provider and configuration. Do not assume a discriminator automatically eliminates all JOINs needed to read subtype attributes.

If the schema is managed by migrations, ensure the migration creates the discriminator column and corresponding values if the mapping/provider requires it. Do not just add the annotation and assume the production schema has changed.

## 5. Repositories and Polymorphic Queries

Because Payment is the root entity, a repository can take the parent type:

```java
import org.springframework.data.jpa.repository.JpaRepository;

public interface PaymentRepository
        extends JpaRepository<Payment, Long> {
}
```

Finding by ID:

```java
Payment payment = paymentRepository.findById(id)
    .orElseThrow(() -> new EntityNotFoundException("Payment not found"));

if (payment instanceof CardPayment cardPayment) {
    String last4 = cardPayment.getCardLast4();
}
```

JPA executes polymorphic queries: querying by the parent entity can return instances of concrete subtypes. The provider must determine the actual type and load the corresponding attributes.

JPQL can filter by entity type:

```java
@Query("select p from Payment p where type(p) = CardPayment")
List<Payment> findCardPayments();
```

`TREAT` can be used to access subtype attributes in a query, if the syntax/provider supports it for that expression:

```java
@Query("""
    select p
    from Payment p
    where treat(p as CardPayment).cardLast4 = :last4
    """)
List<Payment> findByCardLast4(@Param("last4") String last4);
```

When querying a specific subtype:

```java
List<CardPayment> cards = entityManager
    .createQuery(
        "select c from CardPayment c where c.cardLast4 = :last4",
        CardPayment.class
    )
    .setParameter("last4", "4242")
    .getResultList();
```

Do not judge cost solely by looking at JPQL. Inspect the SQL generated by the provider, because a root query and a subtype query can produce different JOIN shapes.

## 6. Where Do JOINs Occur?

### 6.1. Loading a Specific Subtype

To build a complete CardPayment, the provider needs data from both the payment and card_payment tables. Illustrative SQL:

```sql
select
    p.id,
    p.amount,
    p.created_at,
    c.card_last4,
    c.authorization_code
from payment p
join card_payment c on c.id = p.id
where p.id = ?;
```

This is the JOIN required to combine inherited attributes from the parent table with specialized attributes from the child table.

### 6.2. Querying the Root Entity

Querying Payment can return CardPayment and BankTransferPayment. The provider needs to determine the subtype for each row. One illustrative SQL form uses LEFT JOINs to the child tables:

```sql
select
    p.id,
    p.amount,
    p.created_at,
    c.card_last4,
    c.authorization_code,
    b.bank_code,
    b.destination_account
from payment p
left join card_payment c on c.id = p.id
left join bank_transfer_payment b on b.id = p.id;
```

This is a conceptual diagram, not fixed SQL across every provider. Hibernate and other providers may use discriminators, CASE expressions, different joins, or optimizations based on the query, dialect, and version.

### 6.3. Multi-Level Inheritance JOINs

Suppose the hierarchy is:

```text
Payment
  └── OnlinePayment
        └── CardPayment
```

A CardPayment may require rows across all three tables. When reading the complete subtype, the provider must join the corresponding tables. The deeper the entity levels in the inheritance chain, the longer the JOIN path to fetch a complete entity.

Not every query necessarily has to JOIN every table in the hierarchy. If a query only needs attributes on the root, the provider may generate simpler SQL. Actual SQL should be observed on the provider and dialect in use.

## 7. Write Costs with JOINED

### 7.1. INSERT

Creating a CardPayment typically requires:

1. Allocating an ID.
2. INSERTing a row into the payment table.
3. INSERTing a row into the card_payment table with the same ID.
4. Committing within the same transaction.

Illustrative SQL example:

```sql
insert into payment(id, amount, created_at)
values (10, 250.00, current_timestamp);

insert into card_payment(id, card_last4, authorization_code)
values (10, '4242', 'AUTH-001');
```

One logical entity may require multiple INSERT statements. With multi-level hierarchies, the number of write statements can grow with the number of tables in the inheritance chain.

### 7.2. UPDATE

If only amount on the root changes, the provider may only need to update the payment table. If cardLast4 changes, the provider updates card_payment. If attributes on both parent and child change, UPDATEs may be issued on both tables.

```sql
update payment
set amount = 275.00
where id = 10;

update card_payment
set card_last4 = '1234'
where id = 10;
```

Exact SQL also depends on dirty checking, dynamic update, batching, and the provider. JOINED does not mean every update must always write to all tables.

### 7.3. DELETE

When deleting a subtype, the provider needs to delete child table rows first and then delete the row in the parent table, unless the schema/configuration supports another mechanism:

```sql
delete from card_payment where id = 10;
delete from payment where id = 10;
```

This ordering avoids violating the foreign key from the child table to the parent table. Polymorphic deletion of a parent entity must also properly handle subtype rows.

Do not confuse the provider deleting rows in an inheritance hierarchy with `CascadeType.REMOVE` between associated entities. An inheritance hierarchy and an association graph are two distinct relationships.

## 8. Sources of JOINED Overhead

| Source of Cost | Why It Occurs | Impact |
|---|---|---|
| JOIN when reading subtype | Must combine parent and child tables | Increases query and result-processing cost |
| JOIN when querying root | Must identify and load subtypes polymorphically | SQL may have many LEFT JOINs or classification logic |
| Multi-table INSERT | One entity is stored across multiple tables | Increases write statements and round trips without batching |
| Distributed UPDATE | Attributes reside in different tables | May issue multiple UPDATEs |
| Multi-table DELETE | Must delete child and parent rows in order | Increases number of write operations |
| Deep hierarchy | Each entity level adds a table | Number of JOINs can increase |
| Pagination and count | Polymorphic queries require JOINs or classification | Count queries can be heavy with complex execution plans |
| Indexes and FKs | Each child table needs keys linking to parent | Requires managing indexes, statistics, and JOIN plans |

The actual cost of a JOIN depends on row count, selectivity, indexes, caching, cardinality estimates, join type, network latency, and execution plans. You cannot judge performance merely by counting JOINs.

## 9. Indexes and Foreign Keys in the Hierarchy

In JOINED, the PK column in a child table is also the FK to the parent table's PK. PKs typically already have indexes, so joining by ID usually has an efficient access path. Still, verify your database's indexing rules and actual queries.

Recommendations:

- Ensure the parent table's PK has an index.
- Ensure the child table's PK is the exact column used as the FK.
- Name FKs clearly and verify the actual constraints in the schema.
- Index frequently filtered columns in subtype tables, such as card_last4 or bank_code, when appropriate queries exist.
- Avoid adding indexes indiscriminately since indexes increase INSERT/UPDATE/DELETE cost and storage.
- Run EXPLAIN/EXPLAIN ANALYZE on production-like data to inspect join order, scan types, row estimates, and actual row counts.

Example index for subtype filtering queries:

```sql
create index ix_card_payment_last4
on card_payment(card_last4);
```

This index helps when filtering by card_last4 is selective enough and the planner chooses it. It does not guarantee every query will be faster; check the execution plan.

## 10. Pagination, Projections, and Reporting Queries

Pagination on a root entity can be more complex when the provider has to JOIN subtypes to classify and hydrate entities. The count query may have a different structure from the data query. When hierarchies are large or data volume is high, inspect both.

Optimization approaches:

- If a use case only needs ID, payment type, and amount, consider a DTO projection or native query selecting only those columns.
- If a use case only works with CardPayment, query the subtype directly instead of querying the root and filtering in Java.
- If aggregated reporting data is needed, consider DTO queries/native SQL rather than hydrating full entity graphs.
- Avoid calling repositories repeatedly in a loop, causing N+1 issues on other associations.
- Check the count query when using `Page<T>`; consider `Slice<T>` if total page count is not needed.
- Ensure a deterministic ORDER BY when paginating, e.g., adding ID as a tie-breaker.
- Do not indiscriminately combine collection fetch joins with pagination; results may multiply rows and the provider may fall back to in-memory pagination or emit warnings.

DTO projection example:

```java
public record PaymentSummary(
    Long id,
    BigDecimal amount,
    Instant createdAt
) {}
```

JPQL projection query:

```java
@Query("""
    select new com.example.payment.PaymentSummary(
        p.id, p.amount, p.createdAt
    )
    from Payment p
    order by p.createdAt desc, p.id desc
    """)
Page<PaymentSummary> findSummaries(Pageable pageable);
```

This is a JPQL projection example requiring package names and data types matching the actual entity. The provider can avoid hydrating full entities, though you should still inspect the SQL and JOINs required by a root query on your specific provider.

## 11. Comparison with SINGLE_TABLE and TABLE_PER_CLASS

| Criterion | SINGLE_TABLE | JOINED | TABLE_PER_CLASS |
|---|---|---|---|
| Number of tables | One | One table per entity class in hierarchy | One table per concrete entity class |
| Shared columns | Single copy | Reside in parent table | May be repeated in concrete tables |
| Subtype columns | Nullable columns in shared table | Only in subtype table | Reside in concrete table |
| Reading subtype | Usually few JOINs | JOINs parent and subtype tables | Reads subtype table |
| Polymorphic root read | One table, needs subtype identification | May JOIN child tables | Usually requires UNION |
| NOT NULL for subtype columns | Hard to enforce per subtype in shared table | Can set NOT NULL on subtype table | Can set NOT NULL on each table |
| Writing entity | Usually one table | Multiple tables across hierarchy | One concrete table |
| Normalization | Less normalized subtype columns | More normalized | Shared attributes duplicated |

Choose JOINED when:

- Subtypes have many distinct attributes and you want a normalized schema.
- Appropriate constraints are needed per subtype table.
- Subtype or hierarchy queries are not overly sensitive to JOIN costs.
- The domain genuinely represents an *is-a* inheritance relationship.

Consider SINGLE_TABLE when polymorphic reads are frequent, the hierarchy is small, and nullable columns are acceptable. Consider TABLE_PER_CLASS when concrete-type queries dominate and the provider/database handles UNION well. Do not decide based solely on table count; benchmark with a realistic workload.

## 12. JOINED Inheritance Is Not an Association JoinTable

Two annotations have easily confused names:

- `@Inheritance(strategy = InheritanceType.JOINED)`: maps inheritance between a parent entity and child entities.
- `@JoinTable`: defines an intermediate table for an association between entities, commonly seen in many-to-many or unidirectional one-to-many relationships.

With JOINED, child tables use PK/FK pointing to the parent table. There is no need to create an independent link table just to represent a subtype.

If a Payment has many Tags, that is an association, which might need `@ManyToMany` and `@JoinTable`. However, CardPayment extending Payment is an is-a relationship, using an inheritance strategy.

When the domain is not a clear is-a relationship, composition/association is usually easier to understand and more flexible than inheritance. For example, Payment having a PaymentMethod can be an association to a separate entity rather than creating a hierarchy just to reuse a few fields.

## 13. Inspecting SQL and Measuring Performance

Do not optimize JOINED by guesswork. Measure on your database, provider, and production-like data.

With Hibernate, you can enable SQL logging in development:

```properties
spring.jpa.show-sql=false
spring.jpa.properties.hibernate.format_sql=true

logging.level.org.hibernate.SQL=DEBUG
logging.level.org.hibernate.orm.jdbc.bind=TRACE
```

Bind parameter logging can expose sensitive data; only enable it in safe environments and disable it when not needed. Logger names may vary across Hibernate versions.

Measure representative scenarios:

1. Create a subtype entity and count the number of INSERTs.
2. Update attributes on the root and on the subtype separately.
3. Load a subtype by ID.
4. Load a list of root entities containing multiple different subtypes.
5. Paginate the root and measure both the data query and the count query.
6. Filter by a subtype-specific column.
7. Delete a subtype entity.
8. Compare against a SINGLE_TABLE mapping on the same data and workload if considering switching strategies.

Record:

- Number of SQL statements and round trips.
- Total time in the application and database.
- Actual rows read and rows returned.
- Execution plans, index scans/table scans, and join algorithms.
- Connection pool waits, transaction duration, and CPU.
- Impact of caching and warm/cold runs.

Hibernate statistics can help inspect entity loads, query counts, second-level cache hits, and flushes. Enabling statistics carries overhead, so use it in the right environment and make controlled comparisons. Benchmark results require the same dataset, indexes, concurrency, cache state, and configuration.

## 14. Common Pitfalls

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Subtype table has no row after persist | Incorrect hierarchy mapping, transaction, or entity scan | Check `@Entity`, `@Inheritance`, SQL logs, and transactions |
| Subtype FK violation on insert | Parent row not created yet or wrong ID mapping | Check insert order, generator, PK join column, and provider |
| Root query abnormally slow | Polymorphic JOIN across many tables or large dataset | Inspect SQL/EXPLAIN, use projections, query subtype directly if fitting |
| Subtype query still JOINs multiple tables | Needs inherited attributes from root/ancestors | Check projections and which fields are actually needed |
| Deleting entity causes FK error | Child rows not deleted or another association references it | Check DELETE order and FK constraints |
| Schema lacks FK shown in annotations | Schema managed by migrations or DDL generation disabled | Create the FK in migrations and verify the real schema |
| Discriminator does not match subtype | Incorrect discriminator data or mapping configuration | Check discriminator values, migrations, and provider |
| Slow pagination | Complex JOINs and count query, missing indexes | Check both data/count queries, use Slice/DTO where suitable |
| Slow inserts with IDENTITY | Must obtain ID from insert before writing child table | Evaluate sequence generators suitable for the database and batching |
| Chose JOINED but hierarchy is too deep | Each level adds tables and join paths | Simplify hierarchy or consider another strategy |

## 15. Design and Review Checklist

- [ ] Is the relationship between parent and child genuinely *is-a*?
- [ ] Does the root entity declare `@Inheritance(strategy = JOINED)`?
- [ ] Is each subtype an entity with an appropriate table?
- [ ] Does the subtype table PK share the ID and act as an FK referencing the parent table PK?
- [ ] Are table names, PK join columns, and FK constraints consistent with migrations?
- [ ] Is the ID generator suitable for the database and multi-table insert workload?
- [ ] Is a discriminator used, and do values match the data and provider?
- [ ] Have polymorphic root queries and subtype queries been inspected via SQL?
- [ ] Do indexes support actual join/filter/order operations?
- [ ] Have pagination/count queries been measured?
- [ ] Does deleting a subtype/root avoid FK violations and avoid mistakenly relying on association cascades?
- [ ] Is there a benchmark comparison against SINGLE_TABLE or TABLE_PER_CLASS when needed?

## 16. Conclusion

JOINED stores shared attributes in the parent table and specialized ones in subtype tables. The child table's PK also serves as an FK to the parent table's PK. This normalizes the schema, preserves subtype-specific constraints, and supports polymorphic queries across the entity model. The cost is more write operations and queries assembling full entities potentially needing multi-table JOINs.

Use JOINED when data structure and constraint benefits outweigh query costs. Optimize by querying the right subtype directly, projecting only needed data, indexing based on real predicates, inspecting execution plans, and benchmarking realistic workloads. If JOINED becomes a bottleneck, re-evaluate against SINGLE_TABLE, TABLE_PER_CLASS, or composition based on the domain model rather than arbitrarily adding indexes.

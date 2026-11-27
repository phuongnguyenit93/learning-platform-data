# Passing Collections, Enums, Temporal Types, and Nullable Parameters

## 1. Objectives

Spring Data JPA allows passing many value types into derived queries and JPQL: lists of IDs, enum collections, timestamps, and parameters that may have no value. How parameter types are declared affects the generated SQL, how the database handles NULL, and the correctness of filter conditions.

After this lesson, you will be able to:
- Pass `Collection`, `List`, arrays, or varargs for `IN` and `NOT IN` conditions.
- Handle empty collections, null elements, and large lists intentionally.
- Map enums using `EnumType.STRING` or `EnumType.ORDINAL` and bind properly typed parameters.
- Query by `LocalDate`, `LocalDateTime`, and `OffsetDateTime` with clear time ranges.
- Distinguish between a null parameter meaning skip the filter, finding rows with a null column, and null-safe equality comparison.
- Test edge cases with Spring Data JPA.

## 2. Example data model

The examples use Java 17+, Maven, Spring Boot 3.5.0, Spring Data JPA, and H2. The `PurchaseOrder` entity stores the customer, order status, creation timestamp, expected delivery date, and an optional reference code.

### Enum OrderStatus

`src/main/java/com/example/orders/OrderStatus.java`:

```java
package com.example.orders;

public enum OrderStatus {
    NEW,
    PAID,
    SHIPPED,
    CANCELLED
}
```

### Entity PurchaseOrder

`src/main/java/com/example/orders/PurchaseOrder.java`:

```java
package com.example.orders;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.math.BigDecimal;
import java.time.LocalDate;
import java.time.OffsetDateTime;

@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "customer_id", nullable = false)
    private Long customerId;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 20)
    private OrderStatus status;

    @Column(name = "created_at", nullable = false)
    private OffsetDateTime createdAt;

    @Column(name = "delivery_date")
    private LocalDate deliveryDate;

    @Column(name = "reference_code", length = 40)
    private String referenceCode;

    @Column(name = "total_amount", nullable = false, precision = 14, scale = 2)
    private BigDecimal totalAmount;

    protected PurchaseOrder() {
        // JPA requires a no-arg constructor.
    }

    public PurchaseOrder(
            Long customerId, OrderStatus status, OffsetDateTime createdAt,
            LocalDate deliveryDate, String referenceCode, BigDecimal totalAmount) {
        if (customerId == null || customerId <= 0) {
            throw new IllegalArgumentException("Customer ID must be positive");
        }
        if (status == null) {
            throw new IllegalArgumentException("Status is required");
        }
        if (createdAt == null) {
            throw new IllegalArgumentException("Created time is required");
        }
        if (totalAmount == null || totalAmount.signum() < 0) {
            throw new IllegalArgumentException("Total amount cannot be negative");
        }
        if (referenceCode != null && referenceCode.length() > 40) {
            throw new IllegalArgumentException("Reference code is too long");
        }
        this.customerId = customerId;
        this.status = status;
        this.createdAt = createdAt;
        this.deliveryDate = deliveryDate;
        this.referenceCode = referenceCode;
        this.totalAmount = totalAmount;
    }

    public Long getId() { return id; }
    public Long getCustomerId() { return customerId; }
    public OrderStatus getStatus() { return status; }
    public OffsetDateTime getCreatedAt() { return createdAt; }
    public LocalDate getDeliveryDate() { return deliveryDate; }
    public String getReferenceCode() { return referenceCode; }
    public BigDecimal getTotalAmount() { return totalAmount; }
}
```

`@Enumerated(EnumType.STRING)` stores enum names like `PAID` or `SHIPPED`. `createdAt` is a point in time with an offset; `deliveryDate` is a calendar date without time or time zone. `referenceCode` is nullable to illustrate filtering with optional data.

## 3. Passing collections for IN and NOT IN

Spring Data supports derived queries with `In` and `NotIn`. Parameters can be `Collection`, `List`, arrays, or varargs matching the property type.

```java
List<PurchaseOrder> findByIdIn(Collection<Long> ids);

List<PurchaseOrder> findByStatusIn(Collection<OrderStatus> statuses);

List<PurchaseOrder> findByStatusNotIn(Collection<OrderStatus> statuses);
```

Example:

```java
List<PurchaseOrder> paidOrShipped = repository.findByStatusIn(
        List.of(OrderStatus.PAID, OrderStatus.SHIPPED));
```

The derived query above is equivalent to the JPQL condition `o.status in :statuses`. You can declare the query explicitly like this:

```java
@Query("select o from PurchaseOrder o where o.status in :statuses")
List<PurchaseOrder> findByStatuses(@Param("statuses") Collection<OrderStatus> statuses);
```

The JPA provider expands the collection parameter into appropriate SQL bind parameters. Never manually concatenate `IN (...)` strings or interpolate input values into SQL.

### 3.1. Handling null or empty collections

Do not rely on the database to handle `IN ()`. How providers translate empty lists to SQL varies; some databases reject empty lists altogether. Decide the intended meaning in the Service layer before calling the Repository.

For example, for a lookup by list of IDs, the chosen contract is: a null or empty list returns an empty list rather than dropping the condition and fetching all orders.

```java
package com.example.orders;

import java.util.Collection;
import java.util.List;
import java.util.Objects;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
@Transactional(readOnly = true)
public class PurchaseOrderQueryService {
    private final PurchaseOrderRepository repository;

    public PurchaseOrderQueryService(PurchaseOrderRepository repository) {
        this.repository = repository;
    }

    public List<PurchaseOrder> findByIds(Collection<Long> ids) {
        if (ids == null || ids.isEmpty()) {
            return List.of();
        }
        if (ids.stream().anyMatch(Objects::isNull)) {
            throw new IllegalArgumentException("ID collection must not contain null");
        }
        return repository.findByIdIn(ids);
    }

    public List<PurchaseOrder> findByStatuses(Collection<OrderStatus> statuses) {
        if (statuses == null || statuses.isEmpty()) {
            return List.of();
        }
        if (statuses.stream().anyMatch(Objects::isNull)) {
            throw new IllegalArgumentException("Status collection must not contain null");
        }
        return repository.findByStatusInOrderByIdAsc(statuses);
    }
}
```

This is a sample business policy. Another search screen might define a null collection as applying no filter; in that case, use a dedicated optional search method and make that meaning explicit.

### 3.2. Null elements in IN and NOT IN

Do not put null elements inside a collection used with `IN` or `NOT IN` unless the semantics are explicitly defined. SQL uses three-valued logic: TRUE, FALSE, and UNKNOWN. With `NOT IN`, even a single null element in the list can cause the comparison to evaluate to UNKNOWN and exclude rows you expected to keep.

Filter out or reject nulls before calling the Repository. If you need to match rows with a null column, use a separate `IS NULL` condition instead of putting null inside an `IN` list.

### 3.3. Large lists

Passing tens or hundreds of values usually works fine with `IN`. Very large lists can exceed the database's bind parameter limit or generate large, slow SQL statements.

For large lists, consider splitting into bounded batches, inserting IDs into a staging/temporary table and joining, or using array/table-valued parameters via a custom repository/JDBC. Do not assume all databases share the same parameter limit; measure and test on the real engine.

## 4. Passing enums as parameters

An enum is a Java type with a finite set of values. JPA can persist enums by ordinal or by name.

| Mapping | Stored value | Risk |
| --- | --- | --- |
| `EnumType.STRING` | Enum name, e.g., `PAID`. | Renaming an enum constant requires data migration. |
| `EnumType.ORDINAL` | Numeric position, e.g., `0`, `1`, `2`. | Adding or reordering enum constants can change the meaning of existing data. |

If `@Enumerated` is omitted, JPA defaults to ordinal. For long-lived business data, `EnumType.STRING` is usually easier to read and safer when adding new constants.

```java
@Enumerated(EnumType.STRING)
@Column(nullable = false, length = 20)
private OrderStatus status;
```

The repository should accept `OrderStatus` directly without converting the enum to a string before calling the query:

```java
List<PurchaseOrder> findByStatus(OrderStatus status);
List<PurchaseOrder> findByStatusIn(Collection<OrderStatus> statuses);
```

JPQL:

```java
@Query("select o from PurchaseOrder o where o.status = :status")
List<PurchaseOrder> findAllWithStatus(@Param("status") OrderStatus status);
```

The JPA provider knows the type of the `status` property and maps the enum parameter according to the Entity's mapping. With `EnumType.STRING`, the database stores the enum name. With native SQL, enum binding types may depend on the provider and schema; if you must write a native query, verify the stored representation and test against the target database.

Suppose `PAID` is already stored in the database and the constant is later renamed to `SETTLED`. Existing rows still contain `PAID`; when reading, the provider cannot guess the new name. Data migration must stay synchronized with source code changes. Do not switch from ORDINAL to STRING just by changing the annotation; you must migrate numeric values to their corresponding enum names.

## 5. Passing temporal parameters

JPA supports common `java.time` types. Choose the type based on the meaning of the data:

| Java type | Meaning |
| --- | --- |
| `LocalDate` | Calendar date, without time or time zone. |
| `LocalTime` | Time of day, without date or time zone. |
| `LocalDateTime` | Local date and time, without offset/time zone. |
| `OffsetDateTime` | Date and time with a UTC offset. |
| `Instant` | A point in time on the timeline; supported by Hibernate, though if strict JPA portability is required, verify mapping with your provider/version. |

Do not use `@Temporal` for `java.time`. `@Temporal` is for `java.util.Date` and `Calendar` in legacy mappings.

### 5.1. Querying by date

For a `LocalDate` property, you can use `Between`. In derived queries, `Between` includes both endpoints.

```java
List<PurchaseOrder> findByDeliveryDateBetweenOrderByDeliveryDateAsc(
        LocalDate fromInclusive, LocalDate toInclusive);
```

Example finding orders delivered from March 1 to March 31:

```java
List<PurchaseOrder> marchOrders = repository.findByDeliveryDateBetweenOrderByDeliveryDateAsc(
        LocalDate.of(2026, 3, 1),
        LocalDate.of(2026, 3, 31));
```

### 5.2. Querying by timestamp range

For timestamps with time components, prefer half-open intervals: inclusive of the start instant and exclusive of the end instant.

```java
List<PurchaseOrder> findByCreatedAtGreaterThanEqualAndCreatedAtLessThanOrderByCreatedAtAscIdAsc(
        OffsetDateTime fromInclusive,
        OffsetDateTime toExclusive);
```

Example fetching orders in March 2026 in UTC:

```java
OffsetDateTime from = OffsetDateTime.parse("2026-03-01T00:00:00Z");
OffsetDateTime to = OffsetDateTime.parse("2026-04-01T00:00:00Z");

List<PurchaseOrder> marchOrders = repository
        .findByCreatedAtGreaterThanEqualAndCreatedAtLessThanOrderByCreatedAtAscIdAsc(from, to);
```

The range `[from, to)` avoids constructing end-of-day timestamps like `23:59:59.999999`, which depend on database timestamp precision. Adjacent ranges also neither overlap nor miss rows at boundaries.

### 5.3. Offsets and time zones

`OffsetDateTime` carries both date-time and an offset. However, many databases, including PostgreSQL `TIMESTAMP WITH TIME ZONE`, store a normalized instant rather than preserving the original offset submitted by the user. If business logic needs to remember the original time zone such as `Asia/Ho_Chi_Minh`, store an additional `ZoneId` as a separate string.

`LocalDateTime` carries no time zone information. Do not use it to represent a global instant if machines or users operate across multiple time zones; the same local value could refer to different moments in time.

A good convention is to construct boundaries in an agreed-upon time zone (typically UTC for global instants), apply the same convention for both writes and queries, and test timestamp column precision on the target database.

## 6. Nullable parameters: three distinct meanings

NULL is often mistaken for a value that can be compared using `=`. In SQL/JPQL, `column = NULL` does not evaluate to TRUE; it evaluates to UNKNOWN. Therefore, you must define clearly what null means in each use case.

### 6.1. Null means skip the filter

For instance, a search screen allows filtering by customer and status. If `customerId` is null, do not filter by customer; if `status` is null, do not filter by status.

```java
@Query("""
       select o
       from PurchaseOrder o
       where (:customerId is null or o.customerId = :customerId)
         and (:status is null or o.status = :status)
       order by o.createdAt desc, o.id desc
       """)
List<PurchaseOrder> searchOptionalFilters(
        @Param("customerId") Long customerId,
        @Param("status") OrderStatus status);
```

Here `searchOptionalFilters(10L, PAID)` filters by both customer 10 and status PAID; `searchOptionalFilters(null, PAID)` filters only by status; `searchOptionalFilters(10L, null)` filters only by customer; `searchOptionalFilters(null, null)` applies neither filter and may return all orders.

These are optional filter semantics. Protect endpoints capable of returning all rows with pagination limits, access controls, and appropriate scope restrictions.

### 6.2. Null means find rows with a null column

If you need to find orders without a reference code, write an explicit condition:

```java
List<PurchaseOrder> findByReferenceCodeIsNull();
```

Or in JPQL:

```java
@Query("select o from PurchaseOrder o where o.referenceCode is null")
List<PurchaseOrder> findWithoutReferenceCode();
```

Do not write `o.referenceCode = null`; the valid syntax is `IS NULL`.

With equality derived queries, Spring Data can translate a null parameter into an IS NULL condition. However, if the business requirement is to find nulls, an explicit `IsNull` method name makes intent clearer and avoids confusion with optional filters.

### 6.3. Null means null-safe comparison

Sometimes you want to find records matching a parameter where null only matches a null column. You can express this explicitly:

```java
@Query("""
       select o
       from PurchaseOrder o
       where (:referenceCode is null and o.referenceCode is null)
          or o.referenceCode = :referenceCode
       """)
List<PurchaseOrder> findByReferenceCodeNullSafe(
        @Param("referenceCode") String referenceCode);
```

When the parameter is null, the query fetches orders with `referenceCode IS NULL`. When the parameter is non-null, it fetches orders whose reference code equals that value.

This differs from an optional filter: in an optional filter, null means no restriction on the column; in null-safe equality, null means matching only rows where the column is null.

## 7. Derived query vs. JPQL: choosing the right approach

| Need | Derived query | JPQL |
| --- | --- | --- |
| ID in a collection | `findByIdIn(ids)` | `where o.id in :ids` |
| Status in a set of enums | `findByStatusIn(statuses)` | `where o.status in :statuses` |
| Date in a closed range | `findByDeliveryDateBetween(from, to)` | `where o.deliveryDate between :from and :to` |
| Timestamp inclusive of start, exclusive of end | `findByCreatedAtGreaterThanEqualAndCreatedAtLessThan(from, to)` | `where o.createdAt >= :from and o.createdAt < :to` |
| Column is null | `findByReferenceCodeIsNull()` | `where o.referenceCode is null` |
| Skip filter when parameter is null | Do not assume an equality method skips the filter. | `(:param is null or field = :param)` |

Derived queries suit simple conditions. JPQL suits combining multiple optional filters, null expressions, or complex joins.

## 8. Complete repository

`src/main/java/com/example/orders/PurchaseOrderRepository.java`:

```java
package com.example.orders;

import java.time.LocalDate;
import java.time.OffsetDateTime;
import java.util.Collection;
import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface PurchaseOrderRepository extends JpaRepository<PurchaseOrder, Long> {
    List<PurchaseOrder> findByIdIn(Collection<Long> ids);

    List<PurchaseOrder> findByStatusInOrderByIdAsc(Collection<OrderStatus> statuses);

    List<PurchaseOrder> findByStatusNotIn(Collection<OrderStatus> statuses);

    List<PurchaseOrder> findByCreatedAtGreaterThanEqualAndCreatedAtLessThanOrderByCreatedAtAscIdAsc(
            OffsetDateTime fromInclusive, OffsetDateTime toExclusive);

    List<PurchaseOrder> findByDeliveryDateBetweenOrderByDeliveryDateAsc(
            LocalDate fromInclusive, LocalDate toInclusive);

    List<PurchaseOrder> findByReferenceCodeIsNull();

    @Query("""
           select o from PurchaseOrder o
           where (:customerId is null or o.customerId = :customerId)
             and (:status is null or o.status = :status)
           order by o.createdAt desc, o.id desc
           """)
    List<PurchaseOrder> searchOptionalFilters(
            @Param("customerId") Long customerId,
            @Param("status") OrderStatus status);
}
```

The repository uses `Long` as the generic ID type because the primary key of `PurchaseOrder` is `Long`. Filter parameter types are independent of the ID type: `Collection<OrderStatus>`, `OffsetDateTime`, `LocalDate`, or nullable values.

## 9. Integration testing with H2

This test example uses `@DataJpaTest` to verify collection parameters, enums, time ranges, and null semantics. H2 is suitable for checking basic JPA behavior; if production uses a database with specific time zone rules or data types, add integration tests on that exact engine.

`pom.xml` needs these dependencies:

```xml
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
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
```

`src/main/resources/application.properties`:

```properties
spring.datasource.url=jdbc:h2:mem:ordersdb;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=
spring.jpa.hibernate.ddl-auto=create-drop
spring.jpa.open-in-view=false
spring.jpa.show-sql=true
```

`src/test/java/com/example/orders/PurchaseOrderRepositoryTest.java`:

```java
package com.example.orders;

import static org.assertj.core.api.Assertions.assertThat;

import java.math.BigDecimal;
import java.time.LocalDate;
import java.time.OffsetDateTime;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;

@DataJpaTest
class PurchaseOrderRepositoryTest {
    @Autowired
    private PurchaseOrderRepository repository;

    private PurchaseOrder order(
            long customerId, OrderStatus status, String createdAt,
            LocalDate deliveryDate, String referenceCode) {
        return new PurchaseOrder(
                customerId, status, OffsetDateTime.parse(createdAt), deliveryDate,
                referenceCode, new BigDecimal("100.00"));
    }

    @Test
    void filtersByCollectionOfEnumValues() {
        repository.save(order(10L, OrderStatus.PAID,
                "2026-03-10T10:00:00Z", LocalDate.of(2026, 3, 12), "R-1"));
        repository.save(order(10L, OrderStatus.SHIPPED,
                "2026-03-11T10:00:00Z", LocalDate.of(2026, 3, 13), "R-2"));
        repository.save(order(20L, OrderStatus.CANCELLED,
                "2026-03-12T10:00:00Z", LocalDate.of(2026, 3, 14), null));
        repository.flush();

        List<PurchaseOrder> result = repository.findByStatusInOrderByIdAsc(
                List.of(OrderStatus.PAID, OrderStatus.SHIPPED));

        assertThat(result).hasSize(2);
        assertThat(result).extracting(PurchaseOrder::getStatus)
                .containsExactly(OrderStatus.PAID, OrderStatus.SHIPPED);
    }

    @Test
    void usesHalfOpenTimeRange() {
        repository.save(order(10L, OrderStatus.PAID,
                "2026-03-01T00:00:00Z", LocalDate.of(2026, 3, 1), "START"));
        repository.save(order(10L, OrderStatus.PAID,
                "2026-03-31T23:59:59Z", LocalDate.of(2026, 3, 31), "INSIDE"));
        repository.save(order(10L, OrderStatus.PAID,
                "2026-04-01T00:00:00Z", LocalDate.of(2026, 4, 1), "END"));
        repository.flush();

        List<PurchaseOrder> result = repository
                .findByCreatedAtGreaterThanEqualAndCreatedAtLessThanOrderByCreatedAtAscIdAsc(
                        OffsetDateTime.parse("2026-03-01T00:00:00Z"),
                        OffsetDateTime.parse("2026-04-01T00:00:00Z"));

        assertThat(result).extracting(PurchaseOrder::getReferenceCode)
                .containsExactly("START", "INSIDE");
    }

    @Test
    void findsRowsWithNullReferenceCode() {
        repository.save(order(10L, OrderStatus.PAID,
                "2026-03-01T00:00:00Z", LocalDate.of(2026, 3, 2), null));
        repository.save(order(10L, OrderStatus.PAID,
                "2026-03-02T00:00:00Z", LocalDate.of(2026, 3, 3), "R-2"));
        repository.flush();

        List<PurchaseOrder> result = repository.findByReferenceCodeIsNull();

        assertThat(result).hasSize(1);
        assertThat(result.get(0).getReferenceCode()).isNull();
    }

    @Test
    void nullOptionalFiltersAreIgnored() {
        repository.save(order(10L, OrderStatus.PAID,
                "2026-03-01T00:00:00Z", LocalDate.of(2026, 3, 2), "R-1"));
        repository.save(order(20L, OrderStatus.PAID,
                "2026-03-02T00:00:00Z", LocalDate.of(2026, 3, 3), "R-2"));
        repository.save(order(10L, OrderStatus.CANCELLED,
                "2026-03-03T00:00:00Z", LocalDate.of(2026, 3, 4), "R-3"));
        repository.flush();

        List<PurchaseOrder> byStatus = repository.searchOptionalFilters(null, OrderStatus.PAID);
        List<PurchaseOrder> byCustomer = repository.searchOptionalFilters(10L, null);
        List<PurchaseOrder> withoutFilters = repository.searchOptionalFilters(null, null);

        assertThat(byStatus).hasSize(2);
        assertThat(byCustomer).hasSize(2);
        assertThat(withoutFilters).hasSize(3);
    }

    @Test
    void dateBetweenIncludesBothEndpoints() {
        repository.save(order(10L, OrderStatus.PAID,
                "2026-03-01T10:00:00Z", LocalDate.of(2026, 3, 1), "FIRST"));
        repository.save(order(10L, OrderStatus.PAID,
                "2026-03-02T10:00:00Z", LocalDate.of(2026, 3, 15), "MIDDLE"));
        repository.save(order(10L, OrderStatus.PAID,
                "2026-03-03T10:00:00Z", LocalDate.of(2026, 4, 1), "LAST"));
        repository.flush();

        List<PurchaseOrder> result = repository.findByDeliveryDateBetweenOrderByDeliveryDateAsc(
                LocalDate.of(2026, 3, 1), LocalDate.of(2026, 4, 1));

        assertThat(result).extracting(PurchaseOrder::getReferenceCode)
                .containsExactly("FIRST", "MIDDLE", "LAST");
    }
}
```

Run tests from the directory containing `pom.xml`:

```bash
mvn test
```

The expected result is Maven finishing with `BUILD SUCCESS` and all five tests passing. The tests verify enum collections, half-open time ranges, dates with inclusive `Between`, null columns, and skipping filters when parameters are null. This is the expected output for the example; no actual build log is shown.

## 10. Common errors

| Symptom | Cause | Solution |
| --- | --- | --- |
| `IN` query fails with empty list | Generated SQL may contain `IN ()` or provider/database behavior differs. | Handle null/empty in Service before calling Repository. |
| `NOT IN` does not return expected results | Collection contains a null element, turning the expression into UNKNOWN. | Remove or reject nulls in the collection; handle null columns separately. |
| Enum query does not match data | Ordinal/string mapping differs from database representation. | Align `@Enumerated` with schema and data; bind Java enums properly in JPQL. |
| Renaming an enum breaks reading data | Database still stores the old enum name. | Migrate data at the same time constants are renamed. |
| Time query misses end-of-day records | Using `Between` with timestamps and manually creating end-of-day bounds lacking precision. | Use a `[start, nextStart)` interval with `>=` and `<`. |
| Timestamp results shifted by hours | Using LocalDateTime for global instants or inconsistent write/query time zones. | Choose appropriate `OffsetDateTime`/Instant, normalize boundaries, and test on real DB. |
| Null parameter does not skip filter | `field = :value` does not act as an optional filter when value is null. | Use `(:value is null or field = :value)` or build dynamic queries. |
| Trying to find null columns returns no match | Wrote `field = null`. | Use `field is null` or derived method `findByFieldIsNull()`. |
| Optional query is slow with many OR conditions | `(:param is null or field = :param)` can hinder the planner from using indexes effectively. | Use Specification/Criteria/custom repository to add only needed predicates. |
| Too many bind parameters | Very large IN list. | Batch, use a staging table, or use database array/table parameters. |

## 11. Design principles

1. Declare Java generics matching column types: `Collection<Long>`, `Collection<OrderStatus>`, `LocalDate`, or `OffsetDateTime`.
2. Explicitly define whether null/empty collections mean no results or skipping the filter; handle it in Service before invoking queries.
3. Never pass null elements into `IN`/`NOT IN` without explicitly defined semantics.
4. Use `EnumType.STRING` for business enums when appropriate, and manage constant renames with migrations.
5. Use `LocalDate` for calendar dates and offset/instant types for global instants; do not attach `@Temporal` to `java.time`.
6. Use half-open ranges for timestamps and use UTC or a consistent time zone to build boundaries.
7. Separate the three meanings of null clearly: skip filter, match null column, and null-safe equality.
8. For many optional filters or queries needing optimal index usage, consider Specification/Criteria to emit only selected predicates.
9. Test boundary data: empty collections, collections with null, new enums, exact boundary timestamps, and null parameters.
10. Test time zones and precision on the real database when they affect business logic.

## 12. Completion checklist

- [ ] Can pass `Collection` to `In` and `NotIn` derived queries.
- [ ] Intentionally handles null/empty collections and null elements.
- [ ] Understands why `NOT IN` with a null element can produce unexpected results.
- [ ] Maps enums with `EnumType.STRING` and binds Java enum parameters.
- [ ] Distinguishes `LocalDate`, `LocalDateTime`, and `OffsetDateTime`.
- [ ] Uses `Between` properly for date ranges and `[start, end)` for timestamps.
- [ ] Distinguishes a null parameter that skips a filter from an `IS NULL` condition.
- [ ] Can write JPQL with optional filters and understands its performance impact.
- [ ] Can run integration tests for collections, enums, temporal types, and nulls.

Once completed, you can pass strongly typed parameters into Spring Data JPA, properly handle null/empty cases, and build consistent date-time filters.
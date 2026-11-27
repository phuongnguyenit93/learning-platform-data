# Traversing Nested Properties and Resolving Names with Underscores

## 1. Objectives

Spring Data JPA can generate queries from repository method names. When a condition targets a property nested inside another Entity or an `@Embedded` object, Spring Data parses the method name into a property path.

Example:
- `findByAddressZipCode(...)` may be parsed as `addressZip.code`.
- `findByAddress_ZipCode(...)` uses an underscore to explicitly specify the path `address.zipCode`.

This lesson explains how the parser resolves names, when ambiguity arises, how to use `_` to mark traversal boundaries, and how to test queries with Spring Data JPA.

After this lesson, you will be able to:
- Write derived queries that traverse `@Embedded` properties and Entity relationships.
- Understand how Spring Data prioritizes property matches and splits camelCase.
- Handle property names with multiple possible interpretations using underscores.
- Combine nested properties with operators such as `IgnoreCase`, `Containing`, `And`, `Or`, and `OrderBy`.
- Identify errors caused by invalid property names, data types, relationships, or paths.

## 2. Derived queries and property paths

Spring Data repositories support declaring queries directly in method names. The framework parses the name, identifies the subject and predicate parts, and converts property expressions into query conditions.

Example:

```java
List<Customer> findByAddress_ZipCode(String zipCode);
```

This name can be read as:

- `findBy`: prefix indicating a search query.
- `Address_ZipCode`: property path `address.zipCode`.
- `String zipCode`: value compared against the final property.

Given a `Customer` Entity with property `address`, where `Address` has `zipCode`, Spring Data generates a condition equivalent to the JPQL:

```jpql
select c from Customer c where c.address.zipCode = ?1
```

JPQL uses Java property names, not SQL column names. Even if `zipCode` is mapped to column `postal_code`, the property path remains `address.zipCode`.

## 3. How Spring Data resolves property names

Spring Data attempts to match property names through these general steps:

1. First, try matching the entire expression against a direct property of the current type.
2. If no match is found, the parser splits the expression at camelCase boundaries, starting from the right, tries to find a property for the head part, and recursively parses the remaining tail on that property's type.
3. Once a resolution matches valid properties, the path is used to build the query.

For example, if `Customer` has `address` of type `Address`, and `Address` has `zipCode` of type String, the path `address.zipCode` can be written as `AddressZipCode` in the method name when there is no competing property.

However, if `Customer` also has an `addressZip` property of type `AddressZip`, and `AddressZip` also has a `code` property, then `AddressZipCode` can be resolved as `addressZip.code`. The parser may pick the longer direct property first, even if the author intended `address.zipCode`.

This is why underscores are needed to explicitly mark traversal points.

## 4. The underscore `_` to mark traversal boundaries

An underscore in a derived query name is reserved by Spring Data as a property path separator. It fixes the boundary where a nested property begins.

Examples:

| Method name | Property path |
| --- | --- |
| `findByAddressZipCode(...)` | May resolve to `addressZip.code` if that property exists. |
| `findByAddress_ZipCode(...)` | Explicitly specifies `address.zipCode`. |
| `findByCustomer_Address_ZipCode(...)` | Explicitly specifies `customer.address.zipCode`. |

In the ambiguous example, use:

```java
List<Customer> findByAddress_ZipCode(String zipCode);
```

The path is pinned to `address` and then `zipCode`. Spring Data does not have to guess whether `addressZip` is the first property.

**Convention:** use `_` at traversal points that carry ambiguity risk or when long nested property names make boundaries hard to see. There is no need to insert underscores into every method if the path is already unambiguous.

The `_` character is a syntax delimiter in property expressions. Therefore, avoid naming Java persistent properties with underscores. Use camelCase for field/property names; database column names can use snake_case via `@Column(name = "...")` without affecting how the parser reads property names.

## 5. Complete example: two different resolutions

Let us create a `Customer` with two embedded objects:

- `address.zipCode`: postal code of the current address.
- `addressZip.code`: another code stored from a legacy system.

Both paths can match parts of the name `AddressZipCode`. This scenario illustrates why writing explicit boundaries is necessary.

### 5.1. The Address class

`src/main/java/com/example/customer/Address.java`:

```java
package com.example.customer;

import jakarta.persistence.Column;
import jakarta.persistence.Embeddable;

@Embeddable
public class Address {
    @Column(name = "street", nullable = false, length = 160)
    private String street;

    @Column(name = "zip_code", nullable = false, length = 12)
    private String zipCode;

    protected Address() {
        // JPA requires a no-arg constructor.
    }

    public Address(String street, String zipCode) {
        if (street == null || street.isBlank() || street.length() > 160) {
            throw new IllegalArgumentException("Street is required");
        }
        if (zipCode == null || zipCode.isBlank() || zipCode.length() > 12) {
            throw new IllegalArgumentException("Zip code is required");
        }
        this.street = street.trim();
        this.zipCode = zipCode.trim();
    }

    public String getStreet() {
        return street;
    }

    public String getZipCode() {
        return zipCode;
    }
}
```

### 5.2. The AddressZip class

`src/main/java/com/example/customer/AddressZip.java`:

```java
package com.example.customer;

import jakarta.persistence.Embeddable;

@Embeddable
public class AddressZip {
    private String code;

    protected AddressZip() {
        // JPA requires a no-arg constructor.
    }

    public AddressZip(String code) {
        if (code == null || code.isBlank()) {
            throw new IllegalArgumentException("Address zip code is required");
        }
        this.code = code.trim();
    }

    public String getCode() {
        return code;
    }
}
```

### 5.3. The Customer Entity

`src/main/java/com/example/customer/Customer.java`:

```java
package com.example.customer;

import jakarta.persistence.AttributeOverride;
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
    private String name;

    @Embedded
    private Address address;

    @Embedded
    @AttributeOverride(
            name = "code",
            column = @Column(name = "legacy_address_code", nullable = false, length = 30))
    private AddressZip addressZip;

    protected Customer() {
        // JPA requires a no-arg constructor.
    }

    public Customer(String name, Address address, AddressZip addressZip) {
        if (name == null || name.isBlank() || name.length() > 120) {
            throw new IllegalArgumentException("Customer name is required");
        }
        this.name = name.trim();
        this.address = address;
        this.addressZip = addressZip;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public Address getAddress() {
        return address;
    }

    public AddressZip getAddressZip() {
        return addressZip;
    }
}
```

`@AttributeOverride` renames the column of `AddressZip.code` to avoid colliding with the `Address.zipCode` column. The Java property remains `addressZip.code`; only the physical column name is `legacy_address_code`.

### 5.4. Repository

`src/main/java/com/example/customer/CustomerRepository.java`:

```java
package com.example.customer;

import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;

public interface CustomerRepository extends JpaRepository<Customer, Long> {
    List<Customer> findByAddress_ZipCode(String zipCode);

    List<Customer> findByAddressZipCode(String code);

    List<Customer> findByAddress_ZipCodeAndAddress_StreetContainingIgnoreCase(
            String zipCode, String streetPart);
}
```

Meaning:
- `findByAddress_ZipCode`: queries `customer.address.zipCode` because the underscore fixes the split point.
- `findByAddressZipCode`: in this model, the parser can match `customer.addressZip.code`, since `addressZip` is a direct property and `AddressZip` has `code`.
- `findByAddress_ZipCodeAndAddress_StreetContainingIgnoreCase`: combines two conditions, with each path explicitly separated; the second condition uses `Containing` and `IgnoreCase`.

Do not rely on the parser's guesswork when two valid paths exist. Use `_` to express the exact property path you want.

## 6. Testing queries and property path resolution

The example uses Java 17+, Maven, Spring Boot 3.5.0, Spring Data JPA, and H2. Dependencies require `spring-boot-starter-data-jpa`, H2 runtime, and `spring-boot-starter-test` in test scope.

`src/main/resources/application.properties`:

```properties
spring.datasource.url=jdbc:h2:mem:customerdb;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=
spring.jpa.hibernate.ddl-auto=create-drop
spring.jpa.open-in-view=false
spring.jpa.show-sql=true
```

`src/test/java/com/example/customer/CustomerRepositoryTest.java`:

```java
package com.example.customer;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;

@DataJpaTest
class CustomerRepositoryTest {
    @Autowired
    private CustomerRepository customerRepository;

    @Test
    void underscoreForcesTraversalThroughAddress() {
        customerRepository.saveAll(List.of(
                new Customer(
                        "Lan",
                        new Address("12 Nguyen Trai", "700000"),
                        new AddressZip("LEGACY-700000")),
                new Customer(
                        "Minh",
                        new Address("25 Le Loi", "100000"),
                        new AddressZip("LEGACY-100000"))));
        customerRepository.flush();

        List<Customer> customers = customerRepository.findByAddress_ZipCode("700000");

        assertThat(customers)
                .extracting(Customer::getName)
                .containsExactly("Lan");
    }

    @Test
    void unseparatedNameResolvesAddressZipCodePath() {
        customerRepository.save(new Customer(
                "Lan",
                new Address("12 Nguyen Trai", "700000"),
                new AddressZip("LEGACY-700000")));
        customerRepository.flush();

        List<Customer> customers = customerRepository.findByAddressZipCode("LEGACY-700000");

        assertThat(customers)
                .extracting(Customer::getName)
                .containsExactly("Lan");
    }

    @Test
    void combinesNestedPredicates() {
        customerRepository.save(new Customer(
                "Lan",
                new Address("12 Nguyen Trai", "700000"),
                new AddressZip("LEGACY-700000")));
        customerRepository.save(new Customer(
                "An",
                new Address("12 Tran Hung Dao", "700000"),
                new AddressZip("LEGACY-700000")));
        customerRepository.flush();

        List<Customer> customers = customerRepository
                .findByAddress_ZipCodeAndAddress_StreetContainingIgnoreCase(
                        "700000", "nguyen");

        assertThat(customers)
                .extracting(Customer::getName)
                .containsExactly("Lan");
    }
}
```

Run tests in the directory containing `pom.xml`:

```bash
mvn test
```

The expected result is `BUILD SUCCESS` with all three tests passing. The first test confirms `_` forces the parser through `address.zipCode`; the second test confirms the unseparated name matches `addressZip.code`; the third test confirms multiple nested predicates combined with `And`. This is the expected output for the example, not an actual build log.

## 7. Traversing Entity relationships instead of @Embedded

Property paths are not limited to `@Embedded`. Spring Data can traverse Entity relationships such as `@ManyToOne` or `@OneToOne`.

Suppose `PurchaseOrder` has property `customer`, `Customer` has `address`, and `Address` has `zipCode`. You can declare:

```java
List<PurchaseOrder> findByCustomer_Address_ZipCode(String zipCode);
```

The corresponding path is `purchaseOrder.customer.address.zipCode`. Each underscore marks a clear traversal boundary.

Equivalent JPQL:

```java
@Query("select o from PurchaseOrder o where o.customer.address.zipCode = :zipCode")
List<PurchaseOrder> findOrdersByCustomerZipCode(@Param("zipCode") String zipCode);
```

In JPQL, use dots to traverse properties; underscores are only delimiter syntax in derived query method names.

## 8. Query keywords that can be combined with nested properties

Nested properties can be combined with many Spring Data keywords:

| Keyword | Meaning | Example |
| --- | --- | --- |
| `IgnoreCase` | Case-insensitive string comparison. | `findByAddress_ZipCodeIgnoreCase(...)` |
| `Containing` | String contains the search value. | `findByAddress_StreetContaining(...)` |
| `StartingWith` | Starts with string. | `findByAddress_StreetStartingWith(...)` |
| `Between` | Within a range. | `findByMetrics_ScoreBetween(...)` |
| `IsNull` | Null value. | `findByAddress_IsNull()` |
| `And`, `Or` | Combines conditions. | `findByAddress_ZipCodeAndName(...)` |
| `OrderBy` | Sorts results. | `findByAddress_ZipCodeOrderByNameAsc(...)` |

Keywords apply to the final property in the path. Check data types: `Containing` is typically used for strings or compatible collections; `Between` requires comparable types per provider semantics.

## 9. When should you use @Query?

Derived queries are suitable when method names stay short and clear. If paths become too deep or combine too many conditions, `@Query` can make the intent clearer.

```java
@Query("""
       select c
       from Customer c
       where c.address.zipCode = :zipCode
         and lower(c.address.street) like lower(concat('%', :streetPart, '%'))
       """)
List<Customer> searchByAddress(
        @Param("zipCode") String zipCode,
        @Param("streetPart") String streetPart);
```

JPQL uses Entity and Java property names, not physical table or column names. When a query needs complex joins, projections, or fetch plans, choose the most maintainable declaration style instead of forcing overly long method names.

## 10. Common errors

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Query traverses the wrong nested path | Parser selects a longer direct property before splitting camelCase. | Insert `_` at the traversal point, e.g. `Address_ZipCode`. |
| Spring reports property not found | Wrong property name or path navigates into a type lacking the next property. | Verify exact persistent field/getter names and the type at each step. |
| snake_case column name fails in method name | Derived queries use Java property names, not column names. | Use camelCase property names, e.g. `zipCode`, even if the column is `zip_code`. |
| Property name containing `_` confuses parser | `_` is reserved as a path delimiter. | Avoid underscores in Java persistent property names. |
| Nested query returns slowly | Traversal across associations may generate joins or extra queries. | Inspect SQL, indexes, and use appropriate projections/fetch plans. |
| `IgnoreCase` behaves unexpectedly | Database collation or data type has different comparison rules. | Check generated SQL and collation; normalize data if needed. |
| Method name is too long and hard to read | Derived query contains many branches and nested properties. | Switch to `@Query`, Specification, or a custom repository. |

## 11. Design principles

1. Name persistent properties in camelCase and use `_` only to separate nested paths in derived query method names.
2. When multiple paths could match, always mark the traversal point explicitly instead of relying on parser guesses.
3. Use Java property names in derived queries and JPQL; use column names only in native SQL or mapping annotations.
4. Keep method names short and meaningful; move overly complex queries to `@Query` or a custom repository.
5. Inspect generated SQL when queries involve multiple associations or nested conditions.
6. Add indexes on frequently filtered/joined columns and evaluate execution plans with realistic data.
7. Do not confuse `_` in method names with underscores in database column names.

## 12. Completion checklist

- [ ] Can explain how Spring Data resolves property paths.
- [ ] Can describe the rule of trying direct properties first before splitting camelCase.
- [ ] Can recognize when `addressZip.code` competes with `address.zipCode`.
- [ ] Use `findByAddress_ZipCode` to pin the desired path.
- [ ] Use nested properties across both `@Embedded` and Entity relationships.
- [ ] Combine nested paths with `IgnoreCase`, `Containing`, `And`, `Or`, and `OrderBy`.
- [ ] Choose between derived queries and `@Query` based on complexity.
- [ ] Verify queries with integration tests.

Once completed, you can write readable derived queries, precisely control how Spring Data traverses nested properties, and avoid bugs caused by property names with multiple resolutions.
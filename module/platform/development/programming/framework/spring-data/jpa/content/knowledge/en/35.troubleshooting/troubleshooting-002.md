# Diagnosing `PropertyReferenceException` and Invalid Property Names in Spring Data JPA

When creating a repository method such as `findByEmail(...)`, Spring Data JPA does not look for a column named `email` in the database first. It **parses the method name into a property path on the Java entity**. If a matching path cannot be found, the application may report `PropertyReferenceException`: a classic symptom of a property naming error in derived queries, sort declarations, or other components based on property paths.

This lesson helps you read the error in the right place, distinguish **Java properties from SQL column names**, understand how the parser handles camelCase and nested properties, and then fix and test Spring Data JPA methods properly. The examples use Java 17+, Spring Boot 3.x, Spring Data JPA 3.x, and `jakarta.persistence`; the Spring classes in the examples require Spring Boot/Spring Data dependencies and a database, rather than being plain Java programs compiled solely with `javac`.

## 1. What is `PropertyReferenceException`?

`PropertyReferenceException` occurs when Spring Data attempts to build a `PropertyPath` but cannot resolve a segment of the path on the **Java type being inspected**. It does not prove that a SQL table/column is missing and typically happens **before any SQL statement has a chance to run**.

Illustrative diagram:

```text
Repository method: findByEmail(String email)
                           |
                           v
           Parse part after "By": Email
                           |
                           v
   Does Java entity Customer have property "email"?
                           |
               NO: only has "emailAddress"
                           |
                           v
               PropertyReferenceException
```

An illustrative error message (wording and exception wrapping may vary by version):

```text
No property 'email' found for type 'Customer'
```

When creating a Spring repository proxy, the error may be buried inside a chain of `BeanCreationException` → `QueryCreationException` → `PropertyReferenceException`. Do not just fix the bean named at the top of the stack trace; go to the **deepest useful `Caused by`** and look for:

- **The missing property name**: e.g., `email`.
- **The Java type being inspected**: e.g., `Customer`, or `Address` if the error is inside a nested path.
- **The repository method** being created or executed: e.g., `findByEmail`.
- **The resolved path so far**: if present, helps show how far the parser successfully traversed.

In Spring Data Commons 3.x (typically bundled with Spring Boot 3.x), this class is at `org.springframework.data.mapping.PropertyReferenceException`. The Spring Data Commons 4.x API moves its package to `org.springframework.data.core.PropertyReferenceException`. Therefore, if you need to import it directly in tests or error-handling code, **check the API for your exact dependency version**; do not copy imports from a different version.

## 2. Derived Queries Match Entity Properties, Not Database Columns

Consider a `Customer` entity with the property:

```java
@Column(name = "email_address")
private String emailAddress;
```

Here there are **two names with two different purposes**:

| Name | Which layer does it belong to? | Where is it used? |
|---|---|---|
| `emailAddress` | Java entity property | `findByEmailAddress`, `Sort.by("emailAddress")`, JPQL `c.emailAddress` |
| `email_address` | Database column mapped by `@Column` | SQL/native queries; not used as part of a derived method name |
| `email` | Does not exist on the example entity | `findByEmail` is wrong if the parser must infer this property |

**Incorrect:**

```java
List<Customer> findByEmail(String email);       // No property email exists
List<Customer> findByEmail_address(String mail); // "_" does not mean joining into an SQL column name
```

**Correct:**

```java
List<Customer> findByEmailAddress(String emailAddress);
```

If the entity has a `lastName` property, the method name must accurately reflect camelCase as `findByLastName`. `findByLastname` is typically interpreted as the property `lastname`; that is a different name from `lastName`. Do not rely on the database using `last_name` or a naming strategy renaming the column to deduce the `By...` part.

For entities using **field access**, Spring Data/JPA looks at persistent attributes attached to fields; for **property access** via getters, the property model must match the getters/metadata recognized by JPA. Also check `@Access`, `@MappedSuperclass`, `@Embedded`, and getter names if the project uses non-standard mapping approaches. A field that only exists in an API response DTO/record, rather than on the domain entity managed by the repository, is **not** a valid property for creating a derived query on that entity.

## 3. How Are Method Names Parsed?

A typical derived method has the form:

```text
find...By<Property><Operator>And<Property>OrderBy<Property><Direction>
```

Here `find`/`read`/`get` is the subject prefix; `By` separates the prefix from the predicate; after `By` are property paths combined with query keywords such as `Containing`, `Between`, `IsNull`, `And`, `Or`, `IgnoreCase`, `OrderBy...Asc/Desc`. Supported keywords depend on the module, so check the documentation specific to Spring Data JPA.

Valid examples if `Customer` has `emailAddress` and `lastName`:

```java
List<Customer> findByEmailAddress(String emailAddress);
List<Customer> findByLastNameAndEmailAddress(String lastName, String emailAddress);
List<Customer> findByLastNameContainingIgnoreCase(String part);
List<Customer> findByLastNameOrderByEmailAddressAsc(String lastName);
```

Detailed breakdown:

- `findByLastNameAndEmailAddress` looks up properties `lastName` and `emailAddress`, combining them with an AND condition.
- `findByLastNameContainingIgnoreCase` looks up `lastName`; `Containing` and `IgnoreCase` are keywords, **not** fields named `containing` or `ignoreCase`.
- `findByLastNameOrderByEmailAddressAsc` uses `lastName` for filtering and `emailAddress` for sorting; `Asc` is the sort direction.

If the actual field name is `familyName`, changing keywords will not help: you must use `findByFamilyName...` or adjust the mapping/domain model appropriately. An error that suddenly appears right after renaming a property usually means **the repository was not refactored in sync**.

### When Does the Parser Validate Property Names?

By default, Spring Data JPA usually creates/validates derived queries when initializing repository beans during application bootstrap. Therefore, a single wrong method can prevent the entire `ApplicationContext` from starting even if no endpoint has been called. If repository bootstrap is configured as `LAZY` or deferred initialization is used, the error may only appear when the repository is first used; `DEFERRED` also shifts the validation timing. **When the error occurs does not determine its root cause**.

Errors in dynamic `Sort`/`Pageable` arguments passed when calling a repository can also appear only during request execution. Thus, always record the **method, domain type, and running operation**, rather than assuming every `PropertyReferenceException` occurs at startup.

## 4. Nested Properties and the Underscore `_`

Spring Data supports traversing relationships or embedded objects, for instance:

```text
Customer
  ├── emailAddress: String
  ├── lastName: String
  ├── address: Address
  │      └── zipCode: String
  └── addressZip: String
```

If you want to query by `customer.address.zipCode`, you can write:

```java
List<Customer> findByAddress_ZipCode(String zipCode);
```

The `_` character is the parser's **explicit path traversal delimiter**. It is helpful because camelCase can be ambiguous:

- When seeing `AddressZipCode`, the parser first looks for a direct property `addressZipCode`.
- If not found, it tries splitting camelCase segments from right to left, such as `AddressZip` + `Code`, then `Address` + `ZipCode`.
- If the entity already has an `addressZip` property of type `String`, the parser may pick `addressZip` and then attempt to resolve property `code` on `String`, causing an error even though `address.zipCode` exists.
- `findByAddress_ZipCode` forces the parser to traverse `address` and then `zipCode`, avoiding confusion with `addressZip`.

When there are no competing names, `findByAddressZipCode` can resolve correctly; `_` is a disambiguation tool for splitting points, not mandatory for every nested property.

**Do not use `_` to "mimic column names"**. For Java properties containing unusual underscores or starting with `_`, Spring Data has specific escaping/traversal rules (such as `__` in certain paths). The most maintainable approach is to name Java properties using standard camelCase and reserve `@Column(name = "...")` for SQL names.

### Wrong Target Class for a Nested Property

Suppose `address` is of type `Address` and only has `zipCode`, not `postalNumber`:

```java
List<Customer> findByAddress_PostalNumber(String postalNumber); // Incorrect
```

The message may mention **`Address`** instead of `Customer`, because Spring Data successfully found `address` and then failed on `postalNumber`. Open the `Address` class to check its actual properties; adding `@Column(name = "postal_number")` on another field **does not automatically create** a Java property named `postalNumber` if that field/getter does not exist.

## 5. Complete Example in Spring Boot 3.x

The following files belong to the same `com.example.demo` package of a Spring Boot 3.x project with `spring-boot-starter-data-jpa`, JDK 17+, and a datasource. These are per-file source listings that compile **inside a project with those dependencies**; they cannot be compiled standalone with `javac` without the Spring/Jakarta classpath.

**`src/main/java/com/example/demo/Address.java`**

```java
package com.example.demo;

import jakarta.persistence.Column;
import jakarta.persistence.Embeddable;

@Embeddable
public class Address {
    @Column(name = "zip_code")
    private String zipCode;

    protected Address() {
    }

    public Address(String zipCode) {
        this.zipCode = zipCode;
    }

    public String getZipCode() {
        return zipCode;
    }
}
```

**`src/main/java/com/example/demo/Customer.java`**

```java
package com.example.demo;

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

    @Column(name = "email_address", nullable = false, unique = true)
    private String emailAddress;

    @Column(nullable = false)
    private String lastName;

    @Embedded
    private Address address;

    // Another property with a prefix easily confused with address.zipCode.
    private String addressZip;

    protected Customer() {
    }

    public Customer(String emailAddress, String lastName, String zipCode) {
        this.emailAddress = emailAddress;
        this.lastName = lastName;
        this.address = new Address(zipCode);
    }

    public Long getId() {
        return id;
    }

    public String getEmailAddress() {
        return emailAddress;
    }

    public String getLastName() {
        return lastName;
    }
}
```

**`src/main/java/com/example/demo/CustomerRepository.java`**

```java
package com.example.demo;

import org.springframework.data.jpa.repository.JpaRepository;
import java.util.List;

public interface CustomerRepository
        extends JpaRepository<Customer, Long> {

    List<Customer> findByEmailAddress(String emailAddress);

    List<Customer> findByLastName(String lastName);

    // The "_" forces traversal through address.zipCode.
    List<Customer> findByAddress_ZipCode(String zipCode);

    List<Customer> findByLastNameOrderByEmailAddressAsc(String lastName);
}
```

**Error examples: adding these declarations to the repository would need to be fixed before starting the application:**

```java
// No field/getter "email" on Customer.
List<Customer> findByEmail(String email);

// No property "createdAt" on Customer.
List<Customer> findByLastNameOrderByCreatedAtDesc(String lastName);

// Parser may pick "addressZip" and then fail looking for "code".
List<Customer> findByAddressZipCode(String zipCode);
```

The three lines above are **illustrative snippets of invalid declarations**, not meant to be placed in the complete example's source file. For the third method, the outcome depends on the actual set of properties; specifically because `Customer` in the example has `addressZip`, `AddressZipCode` is ambiguous and `Address_ZipCode` is safer.

### Testing the Fixed Property Names

File `src/test/java/com/example/demo/CustomerRepositoryTest.java`. This test assumes `spring-boot-starter-test`, H2 (or an equivalent test database), and a `@SpringBootApplication` in an appropriate root package:

```java
package com.example.demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.data.domain.Sort;

import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;

@DataJpaTest
class CustomerRepositoryTest {
    @Autowired
    private CustomerRepository repository;

    @Test
    void derivedQueriesResolveJavaPropertyPaths() {
        repository.saveAllAndFlush(List.of(
            new Customer("an@example.test", "Nguyen", "700000"),
            new Customer("binh@example.test", "Tran", "100000")
        ));

        assertEquals(1,
            repository.findByEmailAddress("an@example.test").size());

        assertEquals(1,
            repository.findByLastName("Nguyen").size());

        assertEquals("an@example.test",
            repository.findByAddress_ZipCode("700000")
                      .get(0).getEmailAddress());

        assertEquals("an@example.test",
            repository.findAll(Sort.by("emailAddress"))
                      .get(0).getEmailAddress());
    }
}
```

Expected outcome: the test passes when the repository, entity, and schema are configured as above. There is no `System.out.println` or fixed stdout. For typical Maven projects, run with `./mvnw test` (Unix/macOS) or `mvnw.cmd test` (Windows); for Gradle, `./gradlew test` or `gradlew.bat test`. The exact command depends on your build tool and module configuration.

One benefit of `@DataJpaTest` is that it checks repository query parsing early, even before a query is called. If you intentionally add a wrong method like `findByEmail` to `CustomerRepository`, the test context may fail to start and the stack trace will point out the wrong property. After fixing the method, re-run to confirm the context builds and query results are accurate.

## 6. `Sort` and `Pageable` Also Use Java Property Names

Property name errors are not limited to what follows `By`. For example:

```java
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;

// Valid because Customer has property lastName:
var page = repository.findAll(
    PageRequest.of(0, 20, Sort.by("lastName"))
);

// Valid because the Java name is emailAddress:
var customers = repository.findAll(Sort.by("emailAddress"));
```

This is a **code snippet inside a method that already has a `repository` variable**, not a standalone runnable program.

Conversely, with the repository above:

```java
// Invalid: this is an SQL column name, not an entity property.
repository.findAll(Sort.by("email_address"));

// Invalid: Customer does not have property createdAt.
repository.findAll(
    PageRequest.of(0, 20, Sort.by("createdAt"))
);
```

The invalid lines may throw `PropertyReferenceException` or a related error when the query executes, depending on the version and sort processing path. For nested properties, Sort supports paths like `Sort.by("address.zipCode")` when the provider can resolve that path.

**When sort comes from an HTTP query string** (e.g., `?sort=createdAt,desc`), do not pass arbitrary raw strings directly as JPA properties. Validate/restrict against an allowlist of public properties supported by the API, map DTO names like `"email"` to the entity property `"emailAddress"`, and then build `Sort`. This avoids unnecessary 500 errors and limits exposing internal structure through exception messages.

## 7. Distinguishing Three Easily Confused Error Groups

| Symptom | Common cause category | Where to look |
|---|---|---|
| `No property 'email' found for type 'Customer'` | Parser cannot find Java property when building `PropertyPath` | Check entity, `By...`/`OrderBy...` clauses, and paths in `Sort` |
| JPQL `@Query` reports semantic/path error such as unrecognized `c.email` | Hand-written query references wrong attribute | Check JPQL string and Java property names; error is not necessarily `PropertyReferenceException` |
| SQL reports `column email_address does not exist` | Schema/migration or DB column mapping mismatch | Check tables, columns, migrations, `@Column`, and naming strategy |

**Key takeaway:** a `PropertyReferenceException` is a **Java property path** issue. Renaming a column in the database only helps if the real cause is actually in the schema. Do not mistakenly edit migrations when the log clearly says "No property found for type".

### When Using `@Query` Instead of Derived Queries

When a query name gets too long or hard to read, you can declare JPQL directly:

```java
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

// Add this method inside CustomerRepository.
@Query("""
       select c
       from Customer c
       where c.emailAddress = :value
       """)
List<Customer> searchEmailExplicitly(@Param("value") String value);
```

With `@Query`, Spring Data uses the declared query instead of deriving conditions from the method name; **in JPQL you must still use `c.emailAddress`**. If using native SQL (`nativeQuery = true`), SQL syntax uses the column name `email_address` per the actual schema. The two forms have different validators and errors; adding `@Query` merely to bypass a simple typo often makes the method harder to maintain.

## 8. A Subtle Trap: `findById` Can Be a Reserved Method

Certain CRUD methods like `findById`, `existsById`, and `deleteById` are handled by JPA identifier semantics, unlike regular queries. Suppose entity `User` has:

```java
@Id
private Long pk;  // Actual primary key

private Long id;  // Another business property, not the primary key
```

When a repository extends `CrudRepository`/`JpaRepository`, `findById(...)` targets `pk` annotated with `@Id`; it **does not automatically mean** querying by the business field `id`. To query by the non-primary-key field `id`, you can use a clearly named method such as `findUserById(Long id)` (when the signature avoids colliding with base methods) or an explicit query.

This example explains a scenario where a method **does not fail at startup yet queries with unintended semantics**; distinguish this from `PropertyReferenceException`. Do not use the name `findById` to assume the parser always picks the `id` property.

## 9. Quick Diagnostic Workflow When the Application Fails to Start

Suppose the log shows `Could not create query for ... CustomerRepository.findByEmail(...)`. Proceed in order:

1. **Read the root `Caused by`**, find `No property ... found for type ...`. Note the exact failing property and the class the parser is inspecting. If the class is a nested type, continue from that class.
2. **Identify the repository domain**: the generic `JpaRepository<Customer, Long>` must match the real entity. With repository inheritance, an inherited method might be parsed against a different domain than you expect.
3. **Cross-check Java attributes** (fields/getters, access type, `@Embedded`, `@MappedSuperclass`), including casing and camelCase segments. Do not inspect SQL columns as the source for method names.
4. **Break down the method name**: `find...By`, conditions, keywords like `Containing`/`Between`, then `OrderBy`. A typo in the static sort part can also cause initialization failure.
5. **Check nested paths**: if you have `address.zipCode` and a competing `addressZip` property, add `_` to mark the traversal boundary like `findByAddress_ZipCode`.
6. **If all query methods are correct**, look for dynamic `Sort`/`Pageable` passed from controllers/services. Change `"email_address"` to `"emailAddress"`, or map API input against a proper allowlist.
7. **If using `@Query` or named queries**, verify whether it runs JPQL or native SQL and inspect validator/provider errors. Do not attribute all query errors to the derived method parser.
8. **Run `@DataJpaTest` and a test with real data**. A test that only starts the context catches many method naming errors; execution tests verify filters, sorting, and nested paths.

Do not "fix" this by deleting all query methods, disabling repository validation, or catching the exception and returning an empty list. Those approaches hide configuration errors and cause queries to behave incorrectly in deployment.

## 10. Before-and-After Table for Common Mistakes

| Before (wrong or ambiguous) | After | Explanation |
|---|---|---|
| `findByEmail` when entity only has `emailAddress` | `findByEmailAddress` | Use the actual Java property name |
| `findByEmail_address` because SQL is `email_address` | `findByEmailAddress` | `_` is a traversal delimiter, not an SQL column naming syntax |
| `findByLastname` when field is `lastName` | `findByLastName` | Preserve exact camelCase segmentation |
| `findByAddressZipCode` when `addressZip` also exists | `findByAddress_ZipCode` | Force parser to traverse `address.zipCode` |
| `findByAddress_PostalNumber` when `Address` only has `zipCode` | `findByAddress_ZipCode` | Check the type of the nested path segment |
| `findByLastNameOrderByCreatedAtDesc` when `createdAt` does not exist | `findByLastNameOrderByEmailAddressAsc` | Even the static sort portion must use real properties |
| `Sort.by("email_address")` | `Sort.by("emailAddress")` | Dynamic sort also uses Java properties |
| JPQL `c.email_address` | JPQL `c.emailAddress` | JPQL operates on the JPA model; only native SQL uses SQL column names |
| Assuming `findById` queries business field `id` | `findUserById` or explicit query | `findById` has primary-key access semantics from base repository |

## 11. Self-Check Questions

**Question 1.** An entity has `@Column(name = "customer_name") private String displayName;`. Is the method `findByCustomerName(...)` valid?

**Answer:** No, if the entity has no Java property `customerName`. The correct method is `findByDisplayName(...)`; `customer_name` is an SQL column name, not a property.

**Question 2.** When `Customer.address` is `Address` and `Address` has `zipCode`, can `findByAddress_ZipCode` be used?

**Answer:** Yes. The `_` explicitly defines the traversal through `address` and then `zipCode`, which is especially helpful if a `addressZip` property also exists and makes the unseparated name ambiguous.

**Question 3.** Why does `findAll(Sort.by("lastUpdated"))` sometimes only fail when a user calls the endpoint, even though the application starts normally?

**Answer:** `Sort` is constructed/passed **at runtime**. If the entity lacks `lastUpdated`, resolving the sort property may fail during the request rather than during repository method initialization.

**Question 4.** Does a broken JPQL `select c from Customer c where c.email_address = :x` necessarily throw `PropertyReferenceException`?

**Answer:** No. Hand-written queries are parsed/validated through the JPQL/provider pipeline; the error typically falls under semantic/query validation. Fix it to `c.emailAddress` per the entity, or use column names when actually writing native SQL.

## 12. Key Takeaways

- `PropertyReferenceException` primarily reports **failure to construct a `PropertyPath` on a Java domain type**; read the `No property ... found for type ...` portion and the offending repository method.
- Derived queries, `OrderBy`, and `Sort` rely on **property names** like `emailAddress`, `lastName`, not `@Column(name = "...")`.
- For nested properties, `_` clarifies boundaries such as `Address_ZipCode` and avoids ambiguity.
- Errors can occur during repository bootstrap or when processing dynamic sorting; detection timing depends on configuration and usage.
- `@Query` replaces method name derivation, yet JPQL still requires exact entity property names.
- A concise `@DataJpaTest` is enough to verify repository initialization, followed by executing representative queries/sorts to lock down expected behavior.

## References

1. Spring Data JPA, *JPA Query Methods*: https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html
2. Spring Data Commons, *Defining Query Methods → Property Expressions and Reserved Method Names*: https://docs.spring.io/spring-data/jpa/reference/repositories/query-methods-details.html
3. Spring Data JPA, *Repository Query Keywords*: https://docs.spring.io/spring-data/jpa/reference/repositories/query-keywords-reference.html
4. Spring Data Commons 3.5 API, `PropertyReferenceException`: https://docs.spring.io/spring-data/commons/docs/3.5.x/api/org/springframework/data/mapping/PropertyReferenceException.html
5. Spring Data Commons 4.x API, `PropertyReferenceException`: https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/core/PropertyReferenceException.html
6. Spring Data JPA, *Sorting*: https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html#jpa.query-methods.sorting

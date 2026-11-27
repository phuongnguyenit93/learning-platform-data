# Composite Keys Using `@Id` with `@Embedded` in Supported Versions

Some tables do not have a single column sufficient to identify a row. Their primary key consists of multiple columns, such as an organization code combined with an employee number, a country code combined with a postal code, or a unit code combined with a document number. This kind of key is called a **composite key** (or composite primary key).

Starting from **Spring Data JDBC 4.0.0-M4**, Spring Data JDBC supports mapping a composite key to a Java object. This feature was officially released in the Spring Data Relational 4.0.0 line. Applications can annotate an identifier property with `@Id` combined with `@Embedded` to map that object's fields to multiple columns of the same table.

For example, Java represents an employee ID as `EmployeeId(organization, employeeNumber)`, while the database has two columns `ID_ORGANIZATION` and `ID_EMPLOYEE_NUMBER` forming the primary key together.

This lesson covers supported versions, how `@Id` and `@Embedded` map together, table structure, repositories typed with a value object ID, how Spring Data determines whether an entity is new or existing, generating IDs for new aggregates, and considerations when foreign keys reference a composite key.

## 1. What Is a Composite Key?

A typical primary key uses a single column:

~~~sql
CREATE TABLE employee (
    id BIGINT PRIMARY KEY,
    name VARCHAR(100) NOT NULL
);
~~~

Each row is identified by one `id` value. However, some data models use multiple columns combined for unique identification:

~~~sql
CREATE TABLE employee (
    organization VARCHAR(20) NOT NULL,
    employee_number BIGINT NOT NULL,
    name VARCHAR(100) NOT NULL,
    PRIMARY KEY (organization, employee_number)
);
~~~

Here, `organization` alone is not unique because each organization has many employees. `employee_number` alone is not necessarily unique system-wide because organizations may number employees independently. The pair of values forms the primary key.

Example:

| organization | employee_number | name |
| --- | ---: | --- |
| RND | 23 | Jens |
| SALES | 23 | Alex |
| RND | 24 | Linh |

Two rows with the same employee number 23 belong to different organizations and are therefore distinct rows.

### Composite Keys in Java

Instead of passing two separate arguments everywhere, group the key components into a value object:

~~~java
public record EmployeeId(
    Organization organization,
    Long employeeNumber
) {
}
~~~

The entity uses that object as its ID:

~~~java
public class Employee {
    private EmployeeId id;
    private String name;
}
~~~

Spring Data JDBC 4.0 and later can map the properties inside the ID object to columns of the aggregate root table.

## 2. Which Versions Support It?

Composite IDs are supported in Spring Data JDBC and Spring Data R2DBC starting from **4.0.0-M4**. The feature was included in the **4.0.0** stable release line.

| Spring Data Relational version | Composite ID support |
| --- | --- |
| 3.5.x and earlier | Direct composite ID mapping via this feature is not supported |
| 4.0.0-M4 | Available starting in this milestone |
| 4.0.0 GA and 4.0.x releases | Yes |
| 4.1.x | Yes |
| Newer lines | Yes, per current mapping reference |

If a project uses Spring Data Relational 3.5 or lower, simply adding `@Embedded` to a property does not create a composite primary key. You must upgrade to a supported version or keep a single surrogate key and handle the composite key with a separate approach.

When upgrading, use a Spring Data version compatible with the Spring Boot version or release train your project follows. Do not upgrade the `spring-data-jdbc` module alone while ignoring the application's dependency management.

## 3. How Do `@Id` and `@Embedded` Work Together?

`@Id` marks the identifier property of the aggregate root. `@Embedded` tells Spring Data that the object's properties map directly to columns of the entity's table rather than creating a separate table.

When combining the two annotations:

~~~java
@Id
@Embedded.Nullable
EmployeeId id;
~~~

Spring Data treats the entire `EmployeeId` as a single ID at the Java level, while flattening its components into multiple columns at the relational level.

Example:

~~~java
public record EmployeeId(
    Organization organization,
    Long employeeNumber
) {
}
~~~

Columns generated from `EmployeeId`'s properties:

| Java property | Default database column |
| --- | --- |
| `organization` | `ORGANIZATION` |
| `employeeNumber` | `EMPLOYEE_NUMBER` |

The table's primary key is that pair of columns:

~~~sql
PRIMARY KEY (ORGANIZATION, EMPLOYEE_NUMBER)
~~~

`@Embedded` does not create a new table for `EmployeeId`. It only flattens the value object's properties into the same row as the aggregate root.

### Is Writing `@Embedded` Mandatory?

When the ID is a complex type, Spring Data Relational 4.0 can automatically treat the ID's properties as embedded in straightforward mappings. For instance, `@Id EmployeeId id` can already represent a composite ID.

Explicitly writing `@Embedded` is useful when customizing the mapping, especially for adding a column name prefix or specifying behavior when all embedded components are null. This lesson uses `@Id` combined with `@Embedded.Nullable` to make both the identifier role and the nullability rule of the ID object explicit.

## 4. Using `@Embedded.Nullable` and Column Prefixes for Key Columns

The `@Embedded` annotation can take a prefix to prepend to the column names mapped from the object.

Example:

~~~java
@Id
@Embedded.Nullable(prefix = "id_")
EmployeeId id;
~~~

With `EmployeeId` containing `organization` and `employeeNumber`, column names receive the prefix:

| Property in ID | Mapped column |
| --- | --- |
| `organization` | `ID_ORGANIZATION` |
| `employeeNumber` | `ID_EMPLOYEE_NUMBER` |

Corresponding DDL:

~~~sql
CREATE TABLE employee (
    id_organization VARCHAR(20) NOT NULL,
    id_employee_number BIGINT NOT NULL,
    name VARCHAR(100) NOT NULL,
    PRIMARY KEY (id_organization, id_employee_number)
);
~~~

Actual column names also depend on `NamingStrategy` and database identifier rules. Prefixes help distinguish ID columns from regular properties with the same name or meaning.

### 4.1. Meaning of Nullable

`@Embedded.Nullable` is a shortcut for `@Embedded(onEmpty = USE_NULL)`. When Spring Data reads a row and all columns of the embedded object are null, the embedded property is restored as `null`.

This is useful for the ID of a new aggregate: if the ID has not been assigned yet, the ID property can be null. Spring Data can rely on that state to detect a new entity.

The primary key of a persisted row must have all values populated. DDL should declare key component columns as `NOT NULL`; databases likewise do not allow a valid primary key to contain null values.

### 4.2. Distinguishing Nullable and Empty

`@Embedded.Empty` is a shortcut for `@Embedded(onEmpty = USE_EMPTY)`. When all embedded columns are null, Spring Data attempts to instantiate the embedded object with potentially null property values.

| Annotation | When all embedded columns are null |
| --- | --- |
| `@Embedded.Nullable` | Embedded property becomes `null` |
| `@Embedded.Empty` | Attempts to instantiate the embedded object with null properties |

For composite IDs, `@Embedded.Nullable` is usually more appropriate because an empty ID object cannot identify a valid row. `@Embedded.Empty` could construct an ID object whose components are all null, blurring the line between an unassigned ID and an invalid ID.

## 5. Complete Example: `Employee` with a Composite Key

We use the `Organization` enum to represent the department and the `EmployeeId` record to group the two key components.

~~~java
public enum Organization {
    RND,
    SALES,
    MARKETING
}
~~~

~~~java
public record EmployeeId(
    Organization organization,
    Long employeeNumber
) {
}
~~~

Aggregate root:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.relational.core.mapping.Embedded;
import org.springframework.data.relational.core.mapping.Table;

@Table("employee")
public record Employee(

    @Id
    @Embedded.Nullable(prefix = "id_")
    EmployeeId id,

    String name,

    @Version
    Long version
) {
}
~~~

In this example:

- `Employee` is the aggregate root and is stored in the `employee` table.
- `EmployeeId` is the value object holding the key components.
- `@Id` marks the entire `EmployeeId` object as the identifier.
- `@Embedded.Nullable(prefix = "id_")` flattens the two ID components into two prefixed columns.
- `@Version` enables optimistic locking and assists new-entity detection when version is null.

The `Organization` enum is mapped by enum name; `employeeNumber` is a wrapper integer type and is stored using the database's corresponding numeric type.

### Schema

~~~sql
CREATE TABLE employee (
    id_organization VARCHAR(20) NOT NULL,
    id_employee_number BIGINT NOT NULL,
    name VARCHAR(100) NOT NULL,
    version BIGINT NOT NULL,
    CONSTRAINT pk_employee
        PRIMARY KEY (id_organization, id_employee_number)
);
~~~

When saving an employee in RND with number 23, the row contains:

| id_organization | id_employee_number | name | version |
| --- | ---: | --- | ---: |
| RND | 23 | Jens | 0 |

Both `id_organization` and `id_employee_number` together form the primary key.

## 6. Repositories Using the Composite ID as the Generic Type

For the repository, the second generic type parameter is the type of the entire ID, namely `EmployeeId`:

~~~java
import org.springframework.data.repository.CrudRepository;

public interface EmployeeRepository
        extends CrudRepository<Employee, EmployeeId> {
}
~~~

Do not declare `Long` or `String` when the actual ID is the `EmployeeId` object.

Inherited CRUD methods accept the ID object:

~~~java
EmployeeId id = new EmployeeId(Organization.RND, 23L);

Optional<Employee> result = repository.findById(id);

boolean exists = repository.existsById(id);

repository.deleteById(id);
~~~

`findById` accepts a composite ID object. Spring Data decomposes that object into column values to construct the query predicate across the full primary key.

### Do Not Pass Components Separately

Do not call repository methods by passing two arguments like:

~~~java
repository.findById(Organization.RND, 23L);
~~~

The repository contract still accepts a single ID value. Construct the object:

~~~java
EmployeeId id = new EmployeeId(Organization.RND, 23L);
repository.findById(id);
~~~

This keeps the composite key definition centralized in one Java type and ensures services share the same representation.

## 7. How Spring Data Determines Whether an Entity Is New or Existing

This is a critical point when using composite IDs.

Spring Data treats the **entire property annotated with `@Id`** as the identifier. With a composite ID, the `EmployeeId` object itself is the ID; Spring Data does not inspect individual components separately to decide whether an entity is new or existing.

Under the default strategy, Spring Data checks the ID property:

- If the ID is `null`, the entity is considered new and `save` performs an insert.
- If the ID already has a value, the entity is normally considered existing and `save` performs an update.
- If the entity has a `@Version` property, Spring Data uses the version to detect newness: null version or 0 for primitive types indicates a new entity.

Because a composite ID often must be fully populated before saving, the case where an ID is already assigned while the entity is still new must be handled explicitly.

### 7.1. Using `@Version` When the ID Is Pre-Assigned

In the example, `Employee` has a `@Version Long version` property. When creating a new entity, set version to null:

~~~java
Employee employee = new Employee(
    new EmployeeId(Organization.RND, 23L),
    "Jens",
    null
);

Employee saved = repository.save(employee);
~~~

Because version is null, Spring Data treats the aggregate as new and executes an insert even though the composite ID already has a value. The initial persisted version value is 0; subsequent updates increment the version and check the old version to detect concurrent modifications.

`@Version` both supports newness detection in this case and provides optimistic locking for subsequent updates.

### 7.2. Using `JdbcAggregateTemplate.insert` When You Know the Entity Is New

If you do not want optimistic locking, you can explicitly request an insert via `JdbcAggregateTemplate`:

~~~java
import org.springframework.data.jdbc.core.JdbcAggregateTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class EmployeeWriter {

    private final JdbcAggregateTemplate template;

    public EmployeeWriter(JdbcAggregateTemplate template) {
        this.template = template;
    }

    @Transactional
    public Employee create(Employee employee) {
        return template.insert(employee);
    }
}
~~~

`insert` skips new/existing detection and assumes the aggregate is new. If the composite key already exists, the database rejects the insert due to primary key violation. Use this approach only when the caller knows for certain this is a new record.

Alternatively, the entity can implement `Persistable` and provide custom `isNew()` logic. This is an option when the application wants to manage new/existing state itself.

## 8. Assigning Composite IDs via `BeforeConvertCallback`

A composite key generally cannot be auto-generated by a simple auto-increment column because it consists of multiple components. The application needs to supply values for each component, for instance from an organization code and an employee number generator.

Spring Data JDBC provides `BeforeConvertCallback` to assign the ID before the aggregate is converted into SQL operations.

Example using an immutable record:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.relational.core.mapping.event.BeforeConvertCallback;

@Configuration
public class EmployeeCallbackConfiguration {

    @Bean
    BeforeConvertCallback<Employee> employeeIdCallback(
            EmployeeNumberGenerator generator) {

        return employee -> {
            if (employee.id() != null) {
                return employee;
            }

            EmployeeId id = new EmployeeId(
                Organization.RND,
                generator.nextEmployeeNumber()
            );

            return new Employee(
                id,
                employee.name(),
                employee.version()
            );
        };
    }
}
~~~

The number generator can be defined via an interface:

~~~java
public interface EmployeeNumberGenerator {
    Long nextEmployeeNumber();
}
~~~

The application implements the generator using a database sequence or an ID service that guarantees uniqueness. Do not use an in-memory `AtomicLong` as a production ID source if multiple application instances may run or if the process may restart.

Save flow with the callback:

1. The application creates a new `Employee` with a null ID and null version.
2. Spring Data identifies the aggregate as new based on ID/version state.
3. `BeforeConvertCallback` creates an `EmployeeId` and returns the new record.
4. Spring Data maps the two ID components to two columns.
5. The database inserts the row with the composite primary key.
6. The repository returns the persisted aggregate.

The callback must return a new instance when the entity is a record or immutable object. With mutable entities, you can update the property and return the same instance.

### Do Not Assign IDs in `BeforeSaveCallback`

`BeforeSaveCallback` runs after Spring Data has already built the `AggregateChange`. If the ID determines the structure of insert/update operations, assign it in `BeforeConvertCallback` so mapping receives the right values from the start.

## 9. Composite Keys and Referencing Foreign Keys

When another table references an entity with a composite ID, the foreign key also requires multiple columns. The database must reference all components of the primary key.

For example, a `person` table has an ID composed of `firstName` and `lastName`:

~~~java
@Table("person")
public record Person(
    @Id
    @Embedded.Nullable
    Name id,

    String nickName
) {
}

public record Name(String firstName, String lastName) {
}
~~~

Root table:

~~~sql
CREATE TABLE person (
    first_name VARCHAR(100) NOT NULL,
    last_name VARCHAR(100) NOT NULL,
    nick_name VARCHAR(100),
    PRIMARY KEY (first_name, last_name)
);
~~~

If another entity within the aggregate references `Person`, the back-reference consists of multiple columns. Under Spring Data's documented default naming rules, these columns are formed from the referenced entity's table name and each ID component's name, such as `PERSON_FIRST_NAME` and `PERSON_LAST_NAME`.

Illustrative child table:

~~~sql
CREATE TABLE person_address (
    id BIGINT PRIMARY KEY,
    person_first_name VARCHAR(100) NOT NULL,
    person_last_name VARCHAR(100) NOT NULL,
    city VARCHAR(100) NOT NULL,
    FOREIGN KEY (person_first_name, person_last_name)
        REFERENCES person(first_name, last_name)
);
~~~

Actual back-reference names depend on table name, naming strategy, and mapping configuration. With composite IDs, ensure all foreign key columns are created and the constraint references all key components.

### Note on Aggregate Boundaries

Spring Data JDBC handles child entity relationships inside an aggregate root according to the aggregate model. If the referenced target belongs to an independent aggregate, treat it as a separate aggregate and model the relationship with an appropriate ID/reference. Do not nest entity objects merely to mimic a foreign key to another aggregate.

## 10. Querying and Working with Composite IDs

When using repositories, ID-based operations accept the value object:

~~~java
EmployeeId employeeId =
    new EmployeeId(Organization.SALES, 23L);

Optional<Employee> employee =
    employeeRepository.findById(employeeId);

boolean exists =
    employeeRepository.existsById(employeeId);

employeeRepository.deleteById(employeeId);
~~~

`findById` is a dedicated repository method for querying by the identifier property, regardless of whether the property in the entity is named `id` or `pk`. The parameter type remains the composite ID type.

When you need to search by part of the key or combine key components with other attributes, you can define query methods using property paths or use `@Query`. Check property path names and SQL syntax against the Spring Data JDBC version in use. Do not replace the repository's generic ID type with one of the key components.

### Using `JdbcAggregateTemplate`

The template also accepts the full ID object:

~~~java
Employee employee = template.findById(
    new EmployeeId(Organization.RND, 23L),
    Employee.class
);
~~~

`findById`, `deleteById`, `existsById`, and other CRUD operations work with the ID as a single value at the Java level. Spring Data handles decomposing it into multiple columns when generating SQL.

## 11. Immutability and `equals`/`hashCode` of the ID

A composite ID is a value object, so it should be designed as immutable. A Java record is a natural choice:

~~~java
public record EmployeeId(
    Organization organization,
    Long employeeNumber
) {
}
~~~

A record automatically provides `equals` and `hashCode` based on all components. This ensures two ID objects with the same component values are treated as the same key.

If using a regular class, implement `equals` and `hashCode` consistently across all ID components. Do not include mutable attributes such as display name, address, or employee status in the ID.

A composite key must remain stable throughout the row's lifetime. Changing a key component means changing the row's identity and may require updating related foreign keys. In most models, treat the ID as immutable and create a new record if business rules genuinely require a different identity.

## 12. How Composite IDs Differ from Regular `@Embedded`

`@Embedded` can be used for a non-ID value object. Both cases flatten the object's properties into columns of the same table, but their meanings differ:

| Declaration | Meaning |
| --- | --- |
| `@Embedded Address address` | `Address` columns are regular properties of the row |
| `@Id @Embedded Name id` | `Name` columns together form the primary key |
| `@Id Long id` | A single column is the primary key |

Example of an entity with a single key and an embedded address:

~~~java
@Table("customer")
public record Customer(
    @Id Long id,
    @Embedded(prefix = "address_") Address address,
    String name
) {
}

public record Address(String city, String postalCode) {
}
~~~

The table may contain `id`, `address_city`, `address_postal_code`, and `name`. Only the `id` column is the primary key.

In a composite ID, the component columns of the object annotated with `@Id` form the primary key. `@Embedded` governs how that object is flattened into columns.

## 13. Limitations and Design Considerations

- **Version:** requires Spring Data Relational 4.0.0-M4 or higher; stable support begins in 4.0.0.
- **Schema:** the database must have a primary key consisting of the exact component columns. Annotations do not alter schemas or generate migrations automatically.
- **Key values:** all key components must have valid non-null values on insert.
- **Newness detection:** if the ID is pre-assigned, Spring Data may treat the entity as existing by default. Use `@Version`, `Persistable`, or `JdbcAggregateTemplate.insert` depending on the use case.
- **ID generation:** do not expect a single auto-increment column to generate an entire composite key tuple. The application must supply key components using appropriate rules.
- **Component types:** prefer simple JDBC-supported types such as String, numbers, enums, or types with suitable converters.
- **Column names:** prefixes and naming strategies affect column names. Ensure migrations and mappings agree.
- **Foreign keys:** entities referencing a composite ID require multiple back-reference and foreign key columns.
- **Key changes:** changing ID components affects identity and referencing relationships. Treat composite IDs as immutable.

### Do Not Confuse with JPA's `@EmbeddedId`

Spring Data JDBC uses `org.springframework.data.annotation.Id` and `org.springframework.data.relational.core.mapping.Embedded`. Do not use JPA's `jakarta.persistence.EmbeddedId` annotation on Spring Data JDBC entities.

The two modules share the composite key concept, but their mapping APIs are different. Import annotations from the correct Spring Data Relational packages.

## 14. Testing Composite IDs

An integration test should confirm Spring Data writes both key columns and can reload the aggregate using the ID value object.

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.jdbc.DataJdbcTest;

@DataJdbcTest
class EmployeeRepositoryTest {

    @Autowired
    EmployeeRepository employees;

    @Test
    void savesAndFindsEmployeeByCompositeId() {
        EmployeeId id =
            new EmployeeId(Organization.RND, 23L);

        Employee draft = new Employee(id, "Jens", null);

        Employee saved = employees.save(draft);

        assertThat(saved.id()).isEqualTo(id);
        assertThat(saved.version()).isZero();

        Employee loaded = employees.findById(id).orElseThrow();

        assertThat(loaded.id()).isEqualTo(id);
        assertThat(loaded.name()).isEqualTo("Jens");
    }
}
~~~

This example assumes the test database ran a migration creating the `employee` table with a primary key over `id_organization` and `id_employee_number`, and the Spring context loaded the repository. Because the entity has a null `@Version`, Spring Data detects it as a new entity even though the ID is pre-assigned.

Additional cases to test:

1. Two employees with the same employee number in different organizations can coexist.
2. Two rows with all identical ID components are rejected by the database.
3. `findById` works with a fully populated ID object.
4. Saving a new entity with a null version executes an insert.
5. Updating a loaded entity preserves its ID and increments its version.
6. A callback assigning an ID for a new entity produces a complete ID object before persisting.
7. Foreign keys to an aggregate with a composite ID include all component columns.

## 15. Common Errors

| Symptom | Cause | How to handle |
| --- | --- | --- |
| Cannot map ID object to columns | Using a Spring Data JDBC version without composite ID support | Upgrade to Spring Data Relational 4.0 or higher |
| Repository rejects ID type | Generic repository still declares `Long` or `String` | Use the value object type, e.g., `EmployeeId` |
| Saving a new entity runs UPDATE | ID already has a value without a version/newness strategy | Use null `@Version`, `Persistable`, or explicit `insert` |
| Insert reports duplicate primary key | One or all ID components already exist as a tuple | Check the ID generator and constraints |
| ID object reads back as null | All embedded columns are null or mapping prefix mismatches | Check data, `@Embedded.Nullable`, and column names |
| Row not found by ID | Supplied components do not match the full key | Construct the ID object with all exact components |
| Foreign key column missing a component | Schema created only one reference column | Create all FK columns matching the composite ID |
| Enum inside ID fails to map | Stored value differs from enum name or converter missing | Check converters and enum data |
| Migration succeeds but repository fails | Schema column names differ from naming/prefix | Align `@Embedded` prefix, `@Column`, and migrations |
| Wrongly using JPA annotations | Imported `jakarta.persistence.EmbeddedId` or `Embedded` | Use Spring Data JDBC annotations from the right packages |

## 16. Composite Key Implementation Process

When a table requires a composite primary key, follow this sequence:

1. Identify the exact columns that together form the row's identity.
2. Confirm the project uses Spring Data Relational 4.0.0-M4 or higher.
3. Create an immutable value object holding the ID components.
4. Annotate the ID property with `@Id` and `@Embedded`; use a prefix if needed.
5. Choose `@Embedded.Nullable` when an all-null object represents an unassigned ID.
6. Write DDL with a composite primary key and `NOT NULL` on every component.
7. Declare the repository generic parameter with the value object ID type.
8. Choose a new-entity detection strategy: null ID, null version, `Persistable`, or explicit insert.
9. If needed, generate IDs via `BeforeConvertCallback` or an ID generation service.
10. Update referencing foreign keys to use multiple columns.
11. Test insert, find, update, delete, and constraints on the target database.

## 17. Self-Practice Exercises

### Exercise 1 — Creating `EmployeeId`

Create an `EmployeeId` record containing `Organization` and `employeeNumber`. Explain why each component alone is insufficient to identify an employee system-wide.

### Exercise 2 — Mapping with `@Id` and `@Embedded`

Create an `Employee` entity whose ID property is annotated with `@Id @Embedded.Nullable(prefix = "id_")`. Predict the column names and write the DDL with a composite primary key.

### Exercise 3 — Repository Generic Type

Create `EmployeeRepository extends CrudRepository<Employee, EmployeeId>`. Write operations to find, check existence, and delete by composite ID.

### Exercise 4 — Newness Detection

Create an entity with a pre-assigned composite ID and a null `@Version` property. Save the entity, observe the insert and initial version. Remove `@Version` on a test branch to compare how Spring Data detects new state.

### Exercise 5 — `BeforeConvertCallback`

Write a callback that creates `EmployeeId` when a new entity has no ID yet. Use a unique number generator and confirm the callback returns an instance with a complete ID.

### Exercise 6 — Composite Foreign Keys

Create a child table referencing `Person` whose ID has `firstName` and `lastName`. Write DDL containing two foreign key columns and a constraint referencing both primary key columns.

### Exercise 7 — Prefix

Try the same ID object with and without a prefix. Compare the schemas and SQL generated by Spring Data JDBC.

### Exercise 8 — Testing Duplicate Keys

Save two entities with the same composite ID and confirm the database rejects the second record. Then change one key component and confirm both rows can coexist.

## 18. Official References

- [Spring Data JDBC and R2DBC 4.0 will support Composite IDs](https://spring.io/blog/2025/07/22/spring-data-jdbc-composite-id/): announces composite IDs starting in Spring Data 4.0.0-M4, with ID object examples, prefixes, and ID generation for new entities.
- [Spring Data Relational — Mapping](https://docs.spring.io/spring-data/relational/reference/jdbc/mapping.html): Embedded IDs section, combining `@Id` and `@Embedded`, `onEmpty` rules, prefixes, and multi-column back-references.
- [Spring Data Relational — Core Concepts](https://docs.spring.io/spring-data/relational/reference/repositories/core-concepts.html): repository generic types and new-entity detection strategies via ID, version, or `Persistable`.
- [Spring Data Relational — Persisting Entities](https://docs.spring.io/spring-data/relational/reference/jdbc/entity-persistence.html): how `save`, `insert`, and `update` work and the role of `@Version`.

Composite keys in Spring Data JDBC starting in version 4.0 allow modeling multi-column primary keys as a single Java value object. Combining `@Id` with `@Embedded.Nullable` lets Spring Data map the entire ID object to key columns while repositories continue operating on a single ID type. Pay close attention to new-entity detection when the ID is pre-assigned, because the entire ID object is treated as the identifier and its state directly governs whether Spring Data chooses insert or update.

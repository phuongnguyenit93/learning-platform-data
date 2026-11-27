# optional, nullable, Foreign Keys, and Unique Constraints in Spring Data JPA

In singular JPA relationships, four concepts—**optional**, **nullable**, **foreign key**, and **unique constraint**—are related yet solve different problems. Understanding each concept accurately helps ensure the Java model reflects domain cardinality, the database protects data integrity, and the application handles both missing relationships and duplicate data properly.

This document uses Jakarta Persistence with the `jakarta.persistence` namespace (Spring Boot 3 / Spring Framework 6 and later). Older projects using JPA 2 and Spring Boot 2 typically use `javax.persistence`; do not mix the two namespaces in the same application.

## 1. Distinguishing the Four Concepts

| Concept | Where It Lives | Question It Answers | Example |
|---|---|---|---|
| `optional` | JPA relationship mapping | Is the relationship allowed to be absent? | An employee may not have a department yet |
| `nullable` | Database column mapped by `@JoinColumn` | Is the foreign key column allowed to hold SQL NULL? | `department_id` can be NULL |
| Foreign key | Database schema | Does the foreign key value reference a valid row? | `employee.department_id` must point to `department.id` |
| Unique constraint | Database schema | Can the foreign key value repeat across rows? | A profile can be linked to at most one employee |

You can remember it as:

- `optional` expresses whether the association is mandatory in the JPA model.
- `nullable` expresses whether SQL NULL can be stored in the join column.
- A foreign key prevents references to non-existent rows.
- A unique constraint prevents multiple rows from sharing the same foreign key value.

A relationship can be nullable yet still have a foreign key: the column is allowed to be NULL, and when a value is present, that value must reference an existing row. A one-to-one relationship typically requires an additional unique constraint so the database enforces uniqueness on the referenced end.

## 2. Singular Relationships and the Side Owning the Foreign Key

In a singular relationship, an entity references another entity via a single association. For example:

- An employee may belong to a department.
- An employee may have a personal profile.
- An account may have a manager.

In a relational database, the link is typically stored as a foreign key column in one table. The entity owning that column is the **owning side** of the association. With `@ManyToOne` and `@OneToOne` using `@JoinColumn`, the side with `@JoinColumn` is typically the owning side.

Table example:

```sql
create table department (
    id bigint primary key,
    name varchar(150) not null
);

create table employee (
    id bigint primary key,
    name varchar(150) not null,
    department_id bigint null,
    constraint fk_employee_department
        foreign key (department_id) references department(id)
);
```

The `employee.department_id` column lives in the `employee` table, so the `Employee` entity owns the relationship to `Department`. Multiple employees can share the same `department_id`; that is a many-to-one relationship. When `department_id` is NULL, the employee is not yet assigned to a department. When `department_id` has a value, the foreign key requires the corresponding department to exist.

## 3. optional in JPA

The `optional` attribute of `@ManyToOne` and `@OneToOne` describes whether the association is allowed to be absent.

- `optional = true`: the association does not have to be set; the reference value on the entity can be `null`.
- `optional = false`: the association is mandatory; the entity must have a valid related object.

The default value of `optional` on these relationship annotations is `true`.

Optional association example:

```java
@Entity
@Table(name = "employee")
public class Employee {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String name;

    @ManyToOne(fetch = FetchType.LAZY, optional = true)
    @JoinColumn(name = "department_id", nullable = true)
    private Department department;
}
```

An `Employee` can exist without a `Department`. In Java, `employee.getDepartment()` can return `null`. When saved to the database, `department_id` can accept SQL NULL.

Mandatory association example:

```java
@ManyToOne(fetch = FetchType.LAZY, optional = false)
@JoinColumn(name = "department_id", nullable = false)
private Department department;
```

With this mapping, an `Employee` must have a `Department`. If the application creates an `Employee` without setting `department`, the data does not satisfy the model. Depending on the provider and flush timing, an error may be detected before writing or when the database enforces the NOT NULL/foreign key constraint.

### 3.1. optional Is Not Cascade

`optional` does not determine whether the related entity is persisted, merged, or removed automatically. That is the role of cascade:

- `CascadeType.PERSIST`: propagates persist.
- `CascadeType.MERGE`: propagates merge.
- `CascadeType.REMOVE`: propagates remove.
- `CascadeType.ALL`: includes the corresponding cascade operations.

An association can be optional without cascading. For example, an `Employee` references an existing `Department`; saving the `Employee` should not automatically create or delete the `Department`.

### 3.2. optional Is Not Fetch Type

`optional` also does not determine whether the relationship is loaded lazily or eagerly:

- `optional` states whether the relationship is mandatory.
- `fetch` states the strategy for loading the association.

These two attributes are independent. For example, `@ManyToOne(fetch = FetchType.LAZY, optional = true)` is an optional relationship requested to load lazily. JPA specifies the default fetch for `ManyToOne` as EAGER, and `OneToOne` also defaults to EAGER. LAZY on certain relationship types is a request/hint whose execution depends on the provider, proxies, or bytecode enhancement.

## 4. nullable and @JoinColumn

`@JoinColumn` describes the column used to join to the related table. Commonly used attributes:

- `name`: the foreign key column name in the current table.
- `referencedColumnName`: the referenced column in the target table; if omitted, typically references the primary key.
- `nullable`: whether the column allows SQL NULL; defaults to `true`.
- `unique`: requests a single-column unique constraint during schema generation; defaults to `false`.
- `insertable`, `updatable`: whether the column participates in provider-generated INSERT/UPDATE statements.
- `foreignKey`: configures metadata for the foreign key created by schema generation.

Example:

```java
@ManyToOne(fetch = FetchType.LAZY, optional = true)
@JoinColumn(
    name = "department_id",
    nullable = true,
    foreignKey = @ForeignKey(name = "fk_employee_department")
)
private Department department;
```

Here `nullable = true` allows the `department_id` column to store NULL. It does not allow an arbitrary ID that does not exist in the `department` table. If `department_id` is 999 and no `department.id = 999` exists, the foreign key still rejects the write operation.

### 4.1. optional and nullable Should Be Synchronized

For a mandatory association, the common configuration is:

```java
@ManyToOne(optional = false)
@JoinColumn(name = "department_id", nullable = false)
private Department department;
```

For an optional association:

```java
@ManyToOne(optional = true)
@JoinColumn(name = "department_id", nullable = true)
private Department department;
```

Do not declare `optional = false` with `nullable = true`, or `optional = true` with `nullable = false`, unless there is a very specific reason. The two attributes express the same rule at two different layers; conflicting configurations can cause the provider, validation, and database to behave inconsistently.

### 4.2. nullable Is Not Synonymous with @NotNull

`nullable` is column metadata in mapping and schema generation. `@NotNull` is a Bean Validation constraint. Database NOT NULL is a constraint stored in the schema and enforced by the database.

```java
@NotNull
@ManyToOne(optional = false, fetch = FetchType.LAZY)
@JoinColumn(name = "department_id", nullable = false)
private Department department;
```

The three layers serve different purposes:

1. JPA mapping expresses a mandatory relationship.
2. Bean Validation can detect null values before database operations, if validation is enabled and the corresponding lifecycle event is triggered.
3. Database NOT NULL protects data regardless of which application writes to the database.

If you only use Bean Validation without database NOT NULL, another application or direct SQL statement can still store NULL. If you only have database NOT NULL, errors typically appear later at flush/commit. For critical data, keep mapping and database constraints consistent.

## 5. Foreign Keys: Protecting Referential Integrity

A foreign key guarantees that values in the referencing column must exist in the referenced column of the target table. It prevents orphan references such as an `Employee` pointing to a `Department` that has been deleted or never existed.

Example:

```sql
alter table employee
add constraint fk_employee_department
foreign key (department_id)
references department(id);
```

A foreign key can accompany a nullable column:

- `department_id = NULL`: no association; accepted if the column is nullable.
- `department_id = 10` and Department 10 exists: accepted.
- `department_id = 999` but Department 999 does not exist: rejected.
- Deleting a Department currently referenced by an Employee: rejected by default behavior unless an appropriate deletion policy is configured.

### 5.1. Declaring Foreign Keys in JPA

```java
@ManyToOne(fetch = FetchType.LAZY, optional = true)
@JoinColumn(
    name = "department_id",
    nullable = true,
    foreignKey = @ForeignKey(name = "fk_employee_department")
)
private Department department;
```

Naming constraints keeps the database schema readable and convenient for migrations. The `@ForeignKey` annotation describes the constraint for schema generation. If the schema is already created via Flyway/Liquibase or DBA tooling, create the actual foreign key in the database; annotations in code alone do not alter an already-running schema.

`ConstraintMode.NO_CONSTRAINT` can instruct the provider not to generate a foreign key in DDL. Do not use it to mask data errors or bypass referential integrity if the system needs referential integrity protection.

### 5.2. A Foreign Key Does Not Automatically Enforce Uniqueness

In a many-to-one relationship, multiple employee rows are allowed to point to the same department. The foreign key only guarantees that the referenced department exists.

If you want each employee to have their own badge and a badge never assigned to multiple employees, a foreign key alone is insufficient; a unique constraint on `badge_id` is required. This is an important distinction between many-to-one and one-to-one.

### 5.3. Policies When Deleting Referenced Rows

Databases support behaviors such as:

- `RESTRICT` or `NO ACTION`: prevents deleting the parent row while child rows still reference it.
- `ON DELETE CASCADE`: deletes referencing child rows.
- `ON DELETE SET NULL`: sets the foreign key column in child rows to NULL when the parent row is deleted; the column must be nullable.
- `ON DELETE SET DEFAULT`: sets to the default value if supported by the database and schema.

These behaviors belong to database constraints. They differ from JPA cascading:

- `CascadeType.REMOVE` tells JPA to propagate the remove operation through the object graph.
- `orphanRemoval = true` requests deleting a child when the child is removed from a managed relationship.
- `ON DELETE CASCADE` is database behavior when a referenced row is deleted.

Do not treat these three mechanisms as equivalent. If the database deletes child rows automatically, an open persistence context may retain stale entity state if the provider is unaware the deletion occurred. Choose one clear policy, test against the real database, and avoid conflicting ORM/database actions.

## 6. Unique Constraints and One-to-One Relationships

A unique constraint prevents multiple rows from having the same value in a column or set of columns. In a one-to-one relationship using a foreign key, a unique constraint on the FK ensures each target row is referenced by at most one source row.

For example, an `Employee` may have a `Profile`, and a `Profile` belongs to at most one `Employee`:

```sql
create table profile (
    id bigint primary key,
    display_name varchar(150) not null
);

create table employee_profile_link (
    id bigint primary key,
    profile_id bigint null,
    constraint fk_employee_profile
        foreign key (profile_id) references profile(id),
    constraint uk_employee_profile
        unique (profile_id)
);
```

In this example, `profile_id` is both a foreign key and has a unique constraint. The two constraints protect different rules:

- FK: the referenced profile must exist.
- UNIQUE: one profile cannot be linked to two `employee_profile_link` rows.

Without UNIQUE, the database can still accept multiple rows with the same `profile_id` even if the Java mapping declares `OneToOne`. In that case, the actual schema does not enforce one-to-one cardinality.

### 6.1. Declaring OneToOne with a Unique FK

```java
@Entity
@Table(name = "employee")
public class Employee {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @OneToOne(fetch = FetchType.LAZY, optional = true)
    @JoinColumn(
        name = "profile_id",
        nullable = true,
        unique = true,
        foreignKey = @ForeignKey(name = "fk_employee_profile")
    )
    private Profile profile;
}
```

`unique = true` on `@JoinColumn` is how you declare a single-column unique constraint in schema generation metadata. If you need a stable constraint name for migrations, declare it at the table level:

```java
@Entity
@Table(
    name = "employee",
    uniqueConstraints = {
        @UniqueConstraint(
            name = "uk_employee_profile",
            columnNames = "profile_id"
        )
    }
)
public class Employee {
    @Id
    private Long id;

    @OneToOne(fetch = FetchType.LAZY, optional = true)
    @JoinColumn(
        name = "profile_id",
        nullable = true,
        foreignKey = @ForeignKey(name = "fk_employee_profile")
    )
    private Profile profile;
}
```

In the second example, the unique constraint is declared on `@Table`, so there is no need to repeat `unique = true` on `@JoinColumn`.

### 6.2. Owning Side and mappedBy

In bidirectional one-to-one, only one side owns the foreign key. The other side declares `mappedBy` pointing to the owning side's association property:

```java
@Entity
public class Profile {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @OneToOne(mappedBy = "profile", fetch = FetchType.LAZY)
    private Employee employee;
}
```

Here `Employee` owns the `profile_id` column; `Profile` is the inverse side. Modifying only the inverse side without updating the owning side may not write the FK change as expected. When an association is bidirectional, helper methods should update both sides.

```java
public void assignProfile(Profile profile) {
    this.profile = profile;
    if (profile != null) {
        profile.setEmployee(this);
    }
}
```

When clearing the association, helper methods should also set both sides to null according to the model. If the association is mandatory, disassociation should be prevented or replaced by a valid business workflow.

### 6.3. Optional One-to-One and Multiple NULL Values

An optional one-to-one often needs to allow many `Employee` rows without a `Profile`. In that case, `profile_id` is nullable and has a unique constraint.

However, how databases handle multiple NULL values in a unique constraint varies by database engine and index type. Many databases allow multiple NULLs in a unique column; some configurations/engines behave differently. Never assume one database behaves like another. Verify via integration tests on the exact production engine.

If your database does not allow multiple NULLs in a unique index while business rules allow many employees without a profile, use a filtered/partial unique index applying only to non-NULL values if supported by the database. For example, PostgreSQL partial index syntax:

```sql
create unique index uk_employee_profile_not_null
on employee(profile_id)
where profile_id is not null;
```

This is database-specific DDL, not a portable JPA annotation.

## 7. ManyToOne, OneToOne, and Cardinality

| Mapping | Where FK Lives | Unique on FK? | Meaning |
|---|---|---|---|
| `@ManyToOne` | Source entity table | Usually no | Multiple source rows can reference one target row |
| `@OneToOne` with `@JoinColumn` | Owning-side table | Required | Each source row references at most one target row and vice versa via FK |
| `@OneToOne` with shared primary key | Secondary table's PK is also the FK | PK is already unique | One secondary row corresponds to at most one primary row |
| Bidirectional `@OneToMany` | Typically FK in child table | No | One parent has many children; a child typically belongs to one parent |

ManyToOne example:

```java
@ManyToOne(fetch = FetchType.LAZY, optional = true)
@JoinColumn(name = "manager_id", nullable = true)
private Employee manager;
```

Multiple employees can share the same manager. Placing a unique constraint on `manager_id` would restrict each manager to at most one employee, altering the actual cardinality and potentially rejecting valid data.

OneToOne with shared primary key example:

```java
@Entity
public class EmployeeDetails {
    @Id
    private Long id;

    @OneToOne(fetch = FetchType.LAZY, optional = false)
    @MapsId
    @JoinColumn(name = "id")
    private Employee employee;
}
```

In this model, `EmployeeDetails.id` is both the primary key and the foreign key to `Employee.id`. Because a primary key cannot be NULL and is inherently unique, the dependent relationship is mandatory for every `EmployeeDetails` row. If an `Employee` has no `EmployeeDetails` row, the absence is represented by having no row in the secondary table, not a row with a NULL id.

## 8. Unique Constraints for Single and Multiple Columns

Unique constraints do not apply only to foreign keys. They also protect business keys such as email, employee code, or a tenant/email pair.

Single-column unique:

```java
@Entity
@Table(
    name = "account",
    uniqueConstraints = @UniqueConstraint(
        name = "uk_account_email",
        columnNames = "email"
    )
)
public class Account {
    @Id
    private Long id;

    @Column(name = "email", nullable = false)
    private String email;
}
```

Multi-column unique:

```java
@Entity
@Table(
    name = "tenant_user",
    uniqueConstraints = @UniqueConstraint(
        name = "uk_tenant_user_email",
        columnNames = {"tenant_id", "email"}
    )
)
public class TenantUser {
    @Id
    private Long id;

    @Column(name = "tenant_id", nullable = false)
    private Long tenantId;

    @Column(nullable = false)
    private String email;
}
```

The composite constraint ensures the same email can appear in two different tenants, but cannot repeat within the same tenant. If emails must be unique system-wide, make `email` unique on its own. Choose constraints matching the exact uniqueness scope of the business domain.

`@Column(unique = true)` is shorthand for a single-column unique constraint during schema generation. `@Table(uniqueConstraints = ...)` is useful when you need an explicit name or multi-column constraints. For association FKs, you can use `@JoinColumn(unique = true)` or declare the unique constraint on `@Table`.

A unique constraint differs from checking existence before inserting. Two concurrent requests may both observe that an email does not exist yet and both attempt to insert. Only a database unique constraint provides a safe guard against race conditions.

## 9. JPA Mapping vs. Database Constraints: Who Enforces What?

| Mechanism | Role | Protects When Writing SQL Outside JPA? |
|---|---|---|
| `optional = false` | Mandatory relationship metadata in JPA | Not by itself; depends on actual schema constraints |
| `nullable = false` | Column metadata and DDL schema generation | Not by itself if schema lacks NOT NULL |
| `@NotNull` | Bean Validation at appropriate lifecycle validation | No |
| NOT NULL | Database constraint | Yes |
| `@ForeignKey` | Metadata for provider to generate FK | No if actual FK does not exist |
| FOREIGN KEY | Database referential integrity | Yes |
| `unique = true` / `@UniqueConstraint` | Metadata to generate unique constraint | No if actual constraint does not exist |
| UNIQUE | Database constraint | Yes |

Important point: annotations do not automatically modify a production schema if the application uses controlled migrations. When using `spring.jpa.hibernate.ddl-auto=validate`, Hibernate mainly verifies mapping compatibility with the schema within the provider's capabilities; do not treat it as a tool that creates or fixes every required constraint. Manage constraints with Flyway, Liquibase, or your database team's DDL workflow.

## 10. Complete Design Example

Suppose the system has `Department`, `Employee`, and `Profile`:

- `Employee` must have a name.
- `Employee` may not have a `Department` assigned yet.
- One `Department` can have many `Employee` records.
- `Employee` may not have a `Profile` yet.
- One `Profile` can be assigned to at most one `Employee`.

`Department` entity:

```java
@Entity
@Table(name = "department")
public class Department {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 150)
    private String name;

    protected Department() {}

    public Department(String name) {
        this.name = name;
    }
}
```

`Profile` entity:

```java
@Entity
@Table(name = "profile")
public class Profile {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 150)
    private String displayName;

    protected Profile() {}

    public Profile(String displayName) {
        this.displayName = displayName;
    }
}
```

`Employee` entity:

```java
@Entity
@Table(
    name = "employee",
    uniqueConstraints = @UniqueConstraint(
        name = "uk_employee_profile",
        columnNames = "profile_id"
    )
)
public class Employee {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 150)
    private String name;

    @ManyToOne(fetch = FetchType.LAZY, optional = true)
    @JoinColumn(
        name = "department_id",
        nullable = true,
        foreignKey = @ForeignKey(name = "fk_employee_department")
    )
    private Department department;

    @OneToOne(fetch = FetchType.LAZY, optional = true)
    @JoinColumn(
        name = "profile_id",
        nullable = true,
        foreignKey = @ForeignKey(name = "fk_employee_profile")
    )
    private Profile profile;

    protected Employee() {}

    public Employee(String name) {
        this.name = name;
    }

    public void assignDepartment(Department department) {
        this.department = department;
    }

    public void assignProfile(Profile profile) {
        this.profile = profile;
    }
}
```

In this mapping:

- `department_id` is nullable and has an FK, not unique. Multiple Employees may share the same Department; an Employee may not have a Department yet.
- `profile_id` is nullable, has an FK, and is unique. An Employee may not have a Profile yet; each Profile can be referenced by at most one Employee.
- `name` is NOT NULL. The database prevents saving an Employee without a name.
- Neither association cascades by default. The Department/Profile must exist before being referenced, unless the application intentionally configures appropriate cascading.

Conceptually equivalent DDL:

```sql
create table employee (
    id bigint generated by default as identity primary key,
    name varchar(150) not null,
    department_id bigint null,
    profile_id bigint null,
    constraint fk_employee_department
        foreign key (department_id) references department(id),
    constraint fk_employee_profile
        foreign key (profile_id) references profile(id),
    constraint uk_employee_profile
        unique (profile_id)
);
```

Identity syntax may vary across databases; this DDL is illustrative. Use migration syntax suited to your running database engine.

## 11. Assigning and Removing Associations Safely

For optional associations, business code may allow assigning or clearing the link:

```java
@Transactional
public void assignDepartment(Long employeeId, Long departmentId) {
    Employee employee = employeeRepository.findById(employeeId)
        .orElseThrow(() -> new EntityNotFoundException("Employee not found"));

    Department department = departmentRepository.findById(departmentId)
        .orElseThrow(() -> new EntityNotFoundException("Department not found"));

    employee.assignDepartment(department);
}
```

If `Employee` is managed within the transaction, dirty checking writes the FK on flush/commit. You do not necessarily need to call `save` again. If `Employee` is detached, handle its lifecycle accordingly.

Clearing an association:

```java
@Transactional
public void unassignDepartment(Long employeeId) {
    Employee employee = employeeRepository.findById(employeeId)
        .orElseThrow(() -> new EntityNotFoundException("Employee not found"));

    employee.assignDepartment(null);
}
```

This is only valid if the association is optional and the FK column allows NULL. If the mapping has `optional = false` and database NOT NULL, clearing the link violates the model or constraint. If business rules forbid removal, reject the operation in the service layer with a clear business error.

For a one-to-one unique FK, when changing an `Employee`'s `Profile`, verify that the new profile is not already assigned to another `Employee`. You can query to display a friendly error message, but still rely on the database unique constraint because two concurrent requests could both pass the application-level check.

## 12. Migrations When Changing Optionality or Constraints

Changing an association from optional to required is a data and schema change, not just editing annotations.

A safe workflow:

1. Audit how many rows currently have a NULL FK.
2. Decide how to handle each row missing a link: assign a valid value, create a related entity, or remove data per business rules.
3. Deploy code capable of handling the transitional state if multi-version deployment is needed.
4. Backfill NULL FKs.
5. Add or verify the foreign key constraint.
6. Confirm zero NULLs remain, then add NOT NULL.
7. Update the JPA mapping to `optional = false` and `nullable = false`.
8. Test reads/writes and migration rollback in a staging environment.

Example query to check data before making it mandatory:

```sql
select count(*) as missing_department
from employee
where department_id is null;
```

If the result is non-zero, you cannot apply NOT NULL until the data is handled.

When adding a unique constraint:

```sql
select profile_id, count(*) as usage_count
from employee
where profile_id is not null
group by profile_id
having count(*) > 1;
```

Before adding UNIQUE, resolve duplicate groups per business rules. Do not arbitrarily delete records or pick a winner without defining a data policy.

An illustrative PostgreSQL migration for an optional FK column with a unique constraint:

```sql
alter table employee
    add column profile_id bigint null;

alter table employee
    add constraint fk_employee_profile
    foreign key (profile_id) references profile(id);

create unique index uk_employee_profile_not_null
    on employee(profile_id)
    where profile_id is not null;
```

The partial index in this example uses PostgreSQL syntax. If using MySQL, SQL Server, Oracle, or another database, check your engine's syntax and NULL/UNIQUE rules. Migrations should be tested on the exact database type used in production.

## 13. Testing Association Rules

Unit tests verify service logic, while foreign keys, NOT NULL, and UNIQUE constraints should be tested against a real database or Testcontainers using the matching engine.

Repository example:

```java
public interface EmployeeRepository
        extends JpaRepository<Employee, Long> {
    boolean existsByProfileId(Long profileId);
}
```

Example test saving an Employee without Department and Profile:

```java
@DataJpaTest
class EmployeeAssociationTest {
    @Autowired
    private EmployeeRepository employeeRepository;

    @Test
    void allowsMissingOptionalAssociations() {
        Employee employee = new Employee("An");

        Employee saved = employeeRepository.saveAndFlush(employee);

        assertThat(saved.getId()).isNotNull();
        assertThat(saved.getDepartment()).isNull();
        assertThat(saved.getProfile()).isNull();
    }
}
```

A uniqueness test should create two Employees referencing the same Profile and assert that the second flush is rejected by the database. Skeleton example:

```java
@Test
void rejectsProfileAssignedToTwoEmployees() {
    Profile profile = profileRepository.saveAndFlush(
        new Profile("An")
    );

    employeeRepository.saveAndFlush(employee("Employee A", profile));

    assertThatThrownBy(() ->
        employeeRepository.saveAndFlush(employee("Employee B", profile))
    ).isInstanceOf(DataIntegrityViolationException.class);
}
```

This is an illustrative example; the test class needs the `employee(...)` factory method, repositories, and corresponding imports. After a transaction encounters a constraint violation, it may be marked rollback-only; isolate tests or manage transactions carefully to avoid reusing a failed transaction.

Scenarios to test:

- Saving an optional association with a NULL FK.
- Saving an association with a valid FK.
- Rejecting an FK pointing to a non-existent row.
- Rejecting NULL when the association is required.
- Rejecting two rows sharing the same unique value.
- Deleting a referenced row under the configured ON DELETE policy.
- Verifying multiple NULL values on a unique nullable FK against the real database.
- Testing race conditions when two requests concurrently assign the same Profile.

## 14. Common Errors

| Symptom | Cause | Solution |
|---|---|---|
| Can save entity with NULL relationship despite business requirement | Mapping is still optional or database lacks NOT NULL | Align `optional=false`, `nullable=false`, and NOT NULL migration |
| FK error on insert/update | Related ID does not exist or wrong persist order | Load target entity, check intentional cascade, and verify FK |
| OneToOne allows multiple rows with same FK | Database lacks a unique constraint | Add unique constraint/index and clean up duplicate data |
| Cannot save multiple rows without a one-to-one link | Database unique index handles NULLs incompatibly | Use a partial/filtered unique index if supported by the engine |
| Modified annotation but database did not change | Using migration/`ddl-auto validate` or schema already exists | Write separate DDL migrations and deploy in proper order |
| Clearing link causes constraint error | FK column is NOT NULL or association is required | Check business rules; only allow null when relationship is optional |
| Deleting target entity is rejected | Other rows still reference it via FK | Reassign links, delete child rows per business rules, or choose an ON DELETE policy |
| Unintended cascade deletions | Using `CascadeType.REMOVE`/`ALL` across ownership boundaries | Only cascade needed operations; distinguish JPA cascade from DB cascade |
| Two requests assign the same Profile | Only checking `exists` before saving, missing unique constraint | Let the database unique constraint be the final safeguard and handle violation errors |

## 15. Design Checklist

- [ ] Is the association genuinely optional according to business rules?
- [ ] Does `optional` on `@ManyToOne`/`@OneToOne` accurately reflect cardinality?
- [ ] Does `nullable` on `@JoinColumn` match optionality?
- [ ] Does the FK column have an actual foreign key constraint in the database?
- [ ] Does one-to-one have a unique constraint on the FK or a shared PK/FK key?
- [ ] Does many-to-one avoid an unintended unique constraint?
- [ ] Do unique constraints match the business key scope and have stable names?
- [ ] Does the production database handle multiple NULLs in unique indexes as expected?
- [ ] Does the deletion policy distinguish JPA cascade, `orphanRemoval`, and `ON DELETE`?
- [ ] Have migrations backfilled data before adding NOT NULL/UNIQUE?
- [ ] Do integration tests run against the exact database engine?
- [ ] Does the service translate constraint violation errors into appropriate business responses?

## 16. Conclusion

`optional` describes whether an association is mandatory in JPA. `nullable` describes whether an FK column can hold SQL NULL. A foreign key protects references to existing rows. A unique constraint protects the uniqueness of referenced values.

For an optional `ManyToOne`, the typical configuration is `optional = true`, `nullable = true`, with a foreign key and not unique. For an optional `OneToOne`, the typical configuration is `optional = true`, `nullable = true`, with a foreign key and a unique constraint. For mandatory relationships, synchronize `optional = false` and `nullable = false`, and ensure the database enforces NOT NULL and the FK.

Treat annotations as mapping descriptors and database constraints as the final line of data protection. Use migrations to create and alter constraints, test against real databases, and always define cardinality and deletion policies clearly before shipping mappings to production.
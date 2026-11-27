# When to Call a Stored Procedure from a JPA Application

A stored procedure is a program stored and executed inside the database. A Spring Data JPA application can invoke a procedure using Spring Data's `@Procedure`, Jakarta Persistence's `@NamedStoredProcedureQuery`, or the `StoredProcedureQuery` API via `EntityManager`.

You should call a stored procedure when the business requirement genuinely needs near-data processing capabilities, needs to reuse existing database logic, needs to perform a large set-based operation, or must integrate with a legacy system. For standard CRUD and relational queries that can be expressed well using JPQL, derived queries, or the Criteria API, JPA queries are generally easier to maintain and more portable across databases.

Stored procedures are not automatically faster than JPQL, nor do they replace the application's transaction boundaries. Before choosing one, you need to weigh portability, result mapping, transactions, security, testability, and ownership of business logic.

## 1. What is a stored procedure?

A stored procedure is a routine defined in the database, typically with a name, input/output parameters, and one or more SQL statements. A procedure can read data, update multiple tables, perform calculations, return a result set, or return output parameters.

Example of a procedure that recalculates a customer's total amount:

~~~sql
CREATE PROCEDURE recalculate_customer_total(
    IN p_customer_id BIGINT,
    OUT p_total DECIMAL(19, 2)
)
BEGIN
    SELECT COALESCE(SUM(total_amount), 0)
      INTO p_total
      FROM orders
     WHERE customer_id = p_customer_id;
END;
~~~

This is illustrative MySQL-style syntax. The syntax for parameter declarations, procedure body, variables, and returning results varies by database management system. Do not copy this example verbatim to PostgreSQL, SQL Server, or Oracle without adjustments.

Unlike a SQL statement sent by the application on each request, a stored procedure is defined and managed in the database schema. The application invokes the procedure by name and passes parameters.

## 2. Distinguishing stored procedures, functions, and JPQL

| Component | Primary purpose | Common invocation methods |
|---|---|---|
| JPQL | Querying Entities and relationships according to the JPA model | Repository method, `@Query`, EntityManager |
| Native SQL | Sending schema/database-dependent SQL | `@Query(nativeQuery = true)`, native query |
| Stored procedure | Running a routine stored in the database, capable of reading/writing multiple tables and having OUT parameters | `@Procedure`, `StoredProcedureQuery`, JDBC CallableStatement |
| Database function | Computing and returning a value or result set according to database rules | SQL expressions, native query, or provider APIs |

Procedures are typically used for multi-step operations or when OUT parameters are needed. Functions are usually designed to return a value and can be called inside SQL expressions, though exact rules depend on the database.

JPQL describes queries over Entities and Java properties; native SQL and stored procedures work closer to the database schema. A stored procedure is not a Repository query type that automatically shares the same semantics as a derived query.

## 3. When should you consider a stored procedure?

Commonly appropriate situations:

1. **Large set-based data processing:** updating or aggregating thousands or millions of rows directly in the database, avoiding loading each Entity into the application.
2. **Existing logic in the database:** a legacy system already has procedures used by multiple applications, and rewriting them would introduce risk.
3. **An operation requiring multiple SQL statements close to the data:** a procedure can execute multiple steps and return a consolidated result in a single call.
4. **Integrating with systems sharing a schema:** multiple clients need to call the same centrally managed database API.
5. **Operational or authorization requirements:** the DBA wants to grant EXECUTE privileges on a single routine rather than granting direct privileges on multiple tables, if the database's permission model supports it.
6. **Database-specific features:** needing engine-specific capabilities that JPQL cannot express.

For example, an end-of-day job might aggregate transactions, update a summary table, and record batch results in a single routine. If loading all transactions into the JVM and updating each Entity creates too many round trips, a procedure may be suitable.

## 4. When should you not call a stored procedure?

Do not choose a procedure merely because SQL can be written in the database. The following cases should generally remain in JPA/service:

- Simple CRUD such as finding by ID, saving an Entity, or updating a single property.
- Queries that can be concisely expressed using derived queries or JPQL.
- Logic that changes frequently with product requirements and needs to be reviewed/tested alongside application code.
- Projects that need to support multiple database management systems with a single codebase.
- Procedures that merely wrap a simple SELECT statement without providing a clear benefit.
- The application calling a procedure once per Entity inside a loop, creating thousands of round trips.
- Lack of processes for version management, migrations, access permissions, and procedure testing.

If the logic represents core business rules, changes frequently, and needs to coordinate multiple services, keeping the logic in the service/domain layer usually makes it easier for developers to understand and test. Procedures are better suited when the database has a genuine advantage in performing that work.

## 5. Decision comparison: JPQL or stored procedure?

| Criterion | JPQL/Repository | Stored procedure |
|---|---|---|
| Model | Entities and JPA relationships | Routine in the database |
| Portability | Generally higher under the JPA standard | Dependent on engine and dialect |
| Standard CRUD | Very suitable | Usually unnecessary |
| Large set-based processing | Possible, depending on the query | May be suitable when multiple steps near the data are needed |
| Business logic | Easy to place with service/domain and unit test | Logic resides in the database schema |
| Results | Entity, projection, DTO | Result set, OUT parameter, cursor, or multiple results |
| Versioning | Same lifecycle as the application | Requires database migration/version management |
| Security | Privileges on tables and queries | Can grant EXECUTE privileges per routine |
| Debugging | IDE, SQL logs, JPA provider | Requires database debugging tools and workflows |
| Performance | Depends on generated SQL and number of round trips | Not faster by default; requires actual measurement |

The decision should be based on a specific requirement, not on a preference that SQL in the database is always faster or Java is always easier to maintain.

## 6. Approach 1: Calling a procedure with @Procedure

Spring Data JPA provides the `@Procedure` annotation in the package:

~~~java
import org.springframework.data.jpa.repository.query.Procedure;
~~~

You can declare the procedure name directly on a Repository method:

~~~java
public interface CustomerRepository
        extends JpaRepository<Customer, Long> {

    @Procedure(procedureName = "recalculate_customer_total")
    BigDecimal recalculateCustomerTotal(
            @Param("p_customer_id") Long customerId
    );
}
~~~

This example illustrates a procedure with one IN parameter and one OUT parameter. The method accepts `customerId` and returns the OUT value of type `BigDecimal`. The procedure name and parameter names must match the actual definition in the database/provider.

In `@Procedure`:
- `procedureName` is the routine name in the database.
- `name` is the JPA named stored procedure name declared with `@NamedStoredProcedureQuery`.
- `value` is an alias for `procedureName` in the annotation.
- `outputParameterName` can be used to specify the output parameter to retrieve in appropriate configurations.

If a procedure returns only a single output parameter, the method return type is usually used to receive that value. If you need multiple OUT parameters or need to handle result sets alongside output parameters, check the mapping limitations of your Spring Data version and consider `EntityManager` for clearer control.

Do not confuse `@Procedure(name = "...")` with `@Procedure(procedureName = "...")`: one references the name declared in JPA metadata, while the other references the routine name in the database.

## 7. Approach 2: Declaring @NamedStoredProcedureQuery

Jakarta Persistence allows declaring a stored procedure in Entity metadata using `@NamedStoredProcedureQuery`.

Example:

~~~java
import jakarta.persistence.*;

@Entity
@Table(name = "customers")
@NamedStoredProcedureQuery(
    name = "Customer.recalculateTotal",
    procedureName = "recalculate_customer_total",
    parameters = {
        @StoredProcedureParameter(
            mode = ParameterMode.IN,
            name = "p_customer_id",
            type = Long.class
        ),
        @StoredProcedureParameter(
            mode = ParameterMode.OUT,
            name = "p_total",
            type = BigDecimal.class
        )
    }
)
public class Customer {

    @Id
    private Long id;

    private String name;

    protected Customer() {
    }
}
~~~

Key attributes:
- `name`: identifying name of the named procedure within the persistence unit.
- `procedureName`: actual procedure name in the database.
- `parameters`: list of parameters in the order/naming required by the procedure.
- `resultClasses`: Entity classes used to map the result set.
- `resultSetMappings`: names of `@SqlResultSetMapping` declarations used to map results.

The Repository can reference the named procedure:

~~~java
public interface CustomerRepository
        extends JpaRepository<Customer, Long> {

    @Procedure(name = "Customer.recalculateTotal")
    BigDecimal recalculateCustomerTotal(
            @Param("p_customer_id") Long customerId
    );
}
~~~

A named procedure decouples the routine name in the database from the name used in the application. It also centralizes parameter metadata and result mapping in one place. When a procedure has multiple results or complex mapping, you should verify how Spring Data maps the results to the actual method signature.

## 8. JPA ParameterMode options

JPA defines the following parameter modes for stored procedures:

| Mode | Data direction | Meaning |
|---|---|---|
| IN | Application → procedure | Input parameter |
| OUT | Procedure → application | Procedure returns a value |
| INOUT | Bidirectional | Application passes a value and procedure can modify it |
| REF_CURSOR | Procedure → application | Returns a cursor/result set depending on provider/database support |

Declaration examples:

~~~java
@StoredProcedureParameter(
    mode = ParameterMode.IN,
    name = "p_customer_id",
    type = Long.class
)
~~~

~~~java
@StoredProcedureParameter(
    mode = ParameterMode.OUT,
    name = "p_total",
    type = BigDecimal.class
)
~~~

~~~java
@StoredProcedureParameter(
    mode = ParameterMode.INOUT,
    name = "p_counter",
    type = Integer.class
)
~~~

Not every database/provider supports `REF_CURSOR` or every parameter-name binding approach. `REF_CURSOR` often differs between PostgreSQL, Oracle, and various providers. Check the documentation for your database, Hibernate, and Jakarta Persistence versions.

## 9. Approach 3: Calling StoredProcedureQuery via EntityManager

When you need multiple OUT parameters, result set handling, cursors, or control over execution order, `EntityManager` is usually more flexible than `@Procedure`.

Example:

~~~java
import java.math.BigDecimal;

import jakarta.persistence.EntityManager;
import jakarta.persistence.ParameterMode;
import jakarta.persistence.PersistenceContext;
import jakarta.persistence.StoredProcedureQuery;

import org.springframework.stereotype.Repository;
import org.springframework.transaction.annotation.Transactional;

@Repository
public class CustomerProcedureRepository {

    @PersistenceContext
    private EntityManager entityManager;

    @Transactional
    public BigDecimal recalculateTotal(Long customerId) {
        StoredProcedureQuery query =
                entityManager.createStoredProcedureQuery(
                        "recalculate_customer_total"
                );

        query.registerStoredProcedureParameter(
                "p_customer_id",
                Long.class,
                ParameterMode.IN
        );

        query.registerStoredProcedureParameter(
                "p_total",
                BigDecimal.class,
                ParameterMode.OUT
        );

        query.setParameter("p_customer_id", customerId);

        query.execute();

        return (BigDecimal) query.getOutputParameterValue("p_total");
    }
}
~~~

Sequence:
1. Create a `StoredProcedureQuery` with the procedure name.
2. Register each parameter with name/position, Java type, and `ParameterMode`.
3. Assign values for IN or INOUT parameters.
4. Call `execute()`.
5. Read OUT parameters using `getOutputParameterValue()`.
6. Map the result set if the procedure returns data.

Parameter names must match the procedure and the way the provider binds parameters. If the database/provider only supports positional binding, register and bind parameters by ordinal rather than relying on names.

The method is marked `@Transactional` because the example procedure may perform database work. If a procedure is read-only, an appropriate `readOnly` setting may be used, provided you verify that the procedure does not actually write data.

## 10. Passing parameters by name and by position

JPA `StoredProcedureQuery` supports registering parameters by name or by position depending on the provider and procedure.

By name:

~~~java
query.registerStoredProcedureParameter(
        "p_customer_id",
        Long.class,
        ParameterMode.IN
);
query.setParameter("p_customer_id", customerId);
~~~

By position:

~~~java
query.registerStoredProcedureParameter(
        1,
        Long.class,
        ParameterMode.IN
);
query.setParameter(1, customerId);
~~~

Parameter order is part of the procedure contract. When a procedure changes parameter order or names, you must update metadata/callers and the corresponding integration tests.

Do not concatenate user input into the procedure invocation statement. Use parameter binding to pass values. Procedure names and identifiers usually cannot be bound as value parameters; if you need to select a procedure dynamically, use a whitelisted list of names in code.

## 11. Procedures returning a result set

A procedure can return multiple rows instead of a single scalar OUT value. With `EntityManager`, you can create a query that maps results to an Entity:

~~~java
StoredProcedureQuery query =
        entityManager.createStoredProcedureQuery(
                "find_customers_by_status",
                Customer.class
        );

query.registerStoredProcedureParameter(
        "p_status",
        String.class,
        ParameterMode.IN
);

query.setParameter("p_status", "ACTIVE");

@SuppressWarnings("unchecked")
List<Customer> customers = query.getResultList();
~~~

The second argument of `createStoredProcedureQuery` specifies the result class to map rows to an Entity. The result set must contain columns and types compatible with the `Customer` mapping according to the provider/database.

If the procedure returns aggregated columns or a DTO rather than a full Entity, you can use `@SqlResultSetMapping` with `ConstructorResult`, `ColumnResult`, or `EntityResult`, depending on the result shape. Do not declare the result class as a full Entity if the procedure only SELECTs a subset of the columns required for the Entity.

Conceptual DTO mapping example:

~~~java
@SqlResultSetMapping(
    name = "CustomerTotalMapping",
    classes = @ConstructorResult(
        targetClass = CustomerTotalDto.class,
        columns = {
            @ColumnResult(name = "customer_id", type = Long.class),
            @ColumnResult(name = "total_amount", type = BigDecimal.class)
        }
    )
)
~~~

Then create the `StoredProcedureQuery` with the mapping name:

~~~java
StoredProcedureQuery query =
        entityManager.createStoredProcedureQuery(
                "customer_totals",
                "CustomerTotalMapping"
        );
~~~

The DTO needs a constructor matching the order and types of the columns. Aliases in the result set must match `ColumnResult`. Routine syntax for returning result sets and how the driver exposes results depend on the database.

## 12. Procedures returning multiple results

A procedure can return result sets, update counts, and OUT parameters. When there are multiple results, do not assume that calling `getResultList()` once consumes everything.

JPA `StoredProcedureQuery` provides operations such as:
- `execute()`: executes the procedure and indicates whether the first result is a result set.
- `hasMoreResults()`: advances to / checks for the next result.
- `getResultList()`: reads the current result set.
- `getUpdateCount()`: retrieves the current update count.
- `getOutputParameterValue()`: reads an output parameter.

The order and timing of reading results can be affected by the database, JDBC driver, and provider. For procedures returning multiple result sets, test how transitioning between result sets/update counts behaves on the actual production engine and driver.

If a method only needs a single simple OUT parameter, `@Procedure` is usually more concise. If you need to control multiple results, `EntityManager`/`StoredProcedureQuery` or JDBC `CallableStatement` may be more appropriate.

## 13. Transactions when calling stored procedures

Calling a procedure from JPA does not automatically create an independent transaction boundary in the business sense. A procedure typically runs on the connection/resource currently managed by the transaction manager.

If a procedure updates multiple tables and those changes must be atomic with other JPA operations, call it inside a service transaction:

~~~java
@Service
public class CustomerMaintenanceService {

    private final CustomerProcedureRepository procedureRepository;
    private final CustomerRepository customerRepository;

    public CustomerMaintenanceService(
            CustomerProcedureRepository procedureRepository,
            CustomerRepository customerRepository) {
        this.procedureRepository = procedureRepository;
        this.customerRepository = customerRepository;
    }

    @Transactional
    public void recalculateAndMark(Long customerId) {
        procedureRepository.recalculateTotal(customerId);

        Customer customer = customerRepository.findById(customerId)
                .orElseThrow();

        customer.markTotalRecalculated();
    }
}
~~~

If the operations use the same transaction manager and resource, the procedure and JPA updates can participate in the same transaction. If a later step fails and the transaction rolls back, the procedure's changes also roll back when the procedure/database honors the caller's transaction.

**Pay special attention:** some procedures may issue their own COMMIT, ROLLBACK, use an autonomous transaction, or invoke non-transactional operations specific to the database. When that happens, the procedure can break Spring's atomicity expectations. If a service requires full rollback, avoid internal transaction control inside the procedure unless explicitly designed and tested.

Do not assume a procedure running against a different database or an independent connection will participate in the current JPA transaction. Multiple datasources require a separate transaction manager or distributed transaction solution.

## 14. Flushing the persistence context before calling a procedure

JPA maintains a persistence context and may defer SQL until flush. If a procedure reads data that was just modified by a managed Entity, you must ensure those changes have been synchronized to the database before the procedure runs.

Example:

~~~java
@Transactional
public void updateAndRecalculate(Long customerId) {
    Customer customer = customerRepository.findById(customerId)
            .orElseThrow();

    customer.changePricingTier("GOLD");

    entityManager.flush();

    procedureRepository.recalculateTotal(customerId);
}
~~~

`flush()` pushes pending changes in the persistence context to the database within the current transaction. It does not commit the transaction; the changes can still be rolled back.

After a procedure directly updates rows corresponding to managed Entities, the persistence context may hold stale state. Consider:
- `refresh(Entity)` to reload a specific Entity.
- `clear()` to evict all Entities from the persistence context.
- Avoid continuing to use old objects if the procedure modified columns held by those objects.

Example:

~~~java
entityManager.refresh(customer);
~~~

Only refresh when the Entity is still managed and the procedure updated the corresponding data. If multiple Entities are affected, plan clearing/reloading carefully so you do not lose unflushed changes.

## 15. How stored procedures and @Modifying queries differ

`@Modifying` is typically used with JPQL/native DML declared via `@Query`, such as UPDATE or DELETE. It is not an annotation for calling stored procedures.

Example JPQL bulk update:

~~~java
@Modifying
@Query("""
    update Customer c
       set c.active = false
     where c.lastLoginAt < :cutoff
    """)
int deactivateInactiveCustomers(
        @Param("cutoff") Instant cutoff
);
~~~

Bulk updates execute as DML in the database and do not invoke lifecycle callbacks for individual Entities. After a bulk operation, the persistence context may need to be cleared or refreshed.

If an operation is encapsulated in a stored procedure, use `@Procedure`, `StoredProcedureQuery`, or the JDBC callable API. Do not try to attach `@Modifying` to a method just to turn it into a procedure call.

## 16. Security when calling procedures

Stored procedures are not automatically secure simply because the SQL resides in the database. You must protect inputs, execution permissions, and the routine body.

Best practices:
- Use parameter binding for all input values.
- Do not concatenate user strings into dynamic SQL inside a procedure.
- If a procedure must construct dynamic identifiers, use strict allowlisting and validation.
- Grant EXECUTE privileges only on the necessary procedures.
- Restrict direct table privileges if the database security model permits it.
- Review owner/definer vs. invoker execution rights according to database semantics.
- Avoid logging sensitive data or full SQL statements unnecessarily.
- Enforce tenant/user access control consistently at the database or application layer.

If a procedure executes with owner/definer rights, callers may be able to perform operations that the application account is not permitted to perform directly. This can be an intentional security design, but the routine must validate permissions and parameters carefully.

## 17. Performance: are procedures always faster?

No. Stored procedures can reduce round trips and process data close to the database, but the final outcome depends on execution plans, indexes, data volume, locking, and invocation count.

Procedures can be beneficial when:
- Performing multiple set-based operations in a single call.
- Avoiding loading a large number of Entities into the JVM just to update them.
- Computing or aggregating near where the data is stored.
- Using an appropriate execution plan and avoiding repeated round trips.

Procedures can be inefficient when:
- The application calls them once per record inside a loop.
- The routine contains multiple queries without proper indexes.
- The procedure returns an excessively large result set.
- The procedure holds locks for a long time or runs a long-lived transaction.
- Each call causes frequent context switches between the JVM and the database.
- Logic is duplicated between procedures and services, making the system hard to optimize.

Measure both database time and end-to-end time. Use the database's execution plan to inspect indexes, joins, sorts, scans, and actual row counts. Do not conclude a procedure is faster simply because it executes inside the database.

## 18. Procedure versioning and migrations

A procedure is part of the database schema contract. When changing its name, parameter order, data types, output parameters, or result sets, calling applications can be impacted.

Recommended practices:
1. Manage procedure DDL with Flyway or Liquibase.
2. Keep migrations ordered and reviewable.
3. Align procedure versions with application versions.
4. Avoid breaking contract changes without a rollout plan.
5. Test migrations from the previous schema version.
6. Verify EXECUTE privileges after creating or replacing a routine.
7. Have a rollback or forward-fix plan for production procedures.

If multiple applications call the same procedure, treat its name and signature as a shared API. You may need to create a new versioned procedure instead of altering the existing contract directly.

## 19. Portability across databases

Stored procedures are database-dependent in many areas:
- Procedural language and declaration syntax.
- Schema/naming conventions and routine overloading.
- Passing parameters by name versus position.
- Numeric, temporal, and null data types.
- Result sets, cursors, and `REF_CURSOR`.
- Transaction control and exception handling.
- How EXECUTE privileges are granted.
- How JDBC drivers expose multiple results.

JPA standardizes the stored procedure invocation API to a certain degree, but it does not make the procedure definition itself portable. An Oracle procedure will not run on PostgreSQL automatically just because the application uses `@Procedure`.

If you need to support multiple databases, you can:
- Keep core logic in JPQL/Criteria/services.
- Separate procedures by dialect/schema and use separate migrations.
- Create separate adapters/repositories per database.
- Use a shared service interface with different implementations per profile/configuration.
- Test on every database engine you actually support.

## 20. Testing stored procedures

Service unit tests can mock the repository/procedure caller to verify orchestration, but they do not prove the procedure works properly. Integration tests against a database containing the actual procedure are necessary.

What to verify:
1. The procedure exists after running migrations.
2. IN parameters are bound properly.
3. OUT/INOUT parameters return the expected types and values.
4. Result sets map properly to Entities/DTOs.
5. Empty data and boundary cases in the procedure.
6. Null values, precision/scale, and timestamps.
7. EXECUTE privileges of the application account.
8. Transaction rollback when a JPA step after the procedure fails.
9. Flushing before the procedure and refreshing after the procedure when needed.
10. Multiple result sets/update counts if supported by the procedure.
11. Behavior on the production database and JDBC driver.
12. Execution time, locks, and execution plan with sufficiently large data.

Conceptual integration test example:

~~~java
@SpringBootTest
class CustomerProcedureIntegrationTest {

    @Autowired
    private CustomerProcedureRepository procedureRepository;

    @Test
    void returnsCalculatedTotal() {
        // Create customer and order fixtures using the repository.
        BigDecimal total =
                procedureRepository.recalculateCustomerTotal(100L);

        assertEquals(new BigDecimal("150.00"), total);
    }
}
~~~

The fixture must create the appropriate data for customer ID 100 and the expected order total. Do not use H2 to conclude that a PostgreSQL/Oracle/MySQL procedure behaves like production when syntax and semantics are engine-dependent. Testcontainers with the exact database image is often helpful for integration testing.

## 21. Common pitfalls when calling procedures from JPA

**Confusing the named procedure name with the database procedure name**

`@Procedure(name = "...")` references the JPA named query; `procedureName` references the database routine name. Check the right attribute.

**Wrong parameter order or names**

Some drivers/providers require positional binding. Cross-check the procedure signature and how parameters are registered.

**Java type not matching the database type**

For example, DECIMAL having a different precision/scale than the expected `BigDecimal`, or timestamp differing from `Instant`. Verify the actual JDBC mapping.

**Single OUT parameter with an incompatible method return type**

Choose a compatible return type. With multiple OUT parameters or complex result sets, use `EntityManager` to read each result explicitly.

**Using an Entity as the result class when the procedure SELECTs missing columns**

Entity mapping requires complete compatible data. Use a DTO/result set mapping when the result is not a full Entity.

**Forgetting a transaction when the procedure modifies data**

Place the transaction boundary at the service/use case level and confirm the procedure participates in the caller's transaction.

**Procedure issuing its own COMMIT**

Can break Spring's rollback expectations. Avoid internal transaction control when atomicity with JPA operations is required.

**Persistence context holding stale data**

The procedure updates tables directly while Entities remain managed. Flushing before the procedure reads pending changes and refreshing/clearing after the procedure writes data may be necessary.

**Calling a procedure in a loop for each Entity**

Creates excessive round trips. Consider a single batch call or a set-based query.

**Not versioning DDL**

A new application version might call a routine that does not yet exist or whose signature changed. Use migrations and validate the schema before rollout.

**Assuming procedures are always fast and portable**

Measure execution plans and test on the target database. The JPA API does not standardize the language inside procedures.

## 22. Decision and implementation workflow

When a requirement might use a stored procedure, follow this sequence:

1. Determine whether the problem can be solved with a derived query, JPQL, Criteria, or simple native SQL.
2. Identify the specific benefit of a procedure: set-based processing, legacy logic, multiple operations close to data, authorization, or database-specific features.
3. Determine whether the routine is a shared API or serves only one application.
4. Finalize the signature: procedure name, schema, IN/OUT/INOUT/REF_CURSOR, parameter types and order, and result sets.
5. Choose `@Procedure` for simple cases; `@NamedStoredProcedureQuery` when JPA metadata is needed; `EntityManager`/JDBC when control over multiple results or binding is required.
6. Identify the transaction manager and ensure the procedure does not self-commit in violation of business invariants.
7. Determine necessary flush/refresh/clear steps for the persistence context.
8. Manage DDL and EXECUTE privileges via migrations.
9. Write integration tests against the target database/driver.
10. Measure execution plan, round trips, duration, locks, and returned data volume.
11. Plan versioning and rollout for all applications calling the procedure.

## 23. Conclusion

Call stored procedures from JPA when the database has a clear advantage: large set-based processing, integrating legacy logic, executing multiple operations close to data, or providing a centrally managed database API. Spring Data JPA supports `@Procedure`; Jakarta Persistence supports `@NamedStoredProcedureQuery` and `StoredProcedureQuery` via `EntityManager`. Choose the simple API for a single OUT parameter or basic result set, and use `EntityManager`/JDBC when you need multiple parameters, cursors, or multiple results. Keep transactions at the service/use case level, manage flushing and the persistence context, avoid self-committing procedures when shared rollback is needed, manage DDL with migrations, and test against a real database. Procedures are not faster or more portable than JPQL by default; only retain them when data, operational, or integration benefits justify the maintenance cost.
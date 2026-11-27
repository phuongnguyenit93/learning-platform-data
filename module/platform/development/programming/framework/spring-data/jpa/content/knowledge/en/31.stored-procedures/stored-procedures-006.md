# Calling Procedures with EntityManager for Fine-Grained Control

## Objectives

Spring Data JPA can invoke stored procedures using `@Procedure` on a repository method. This approach is concise when a procedure has a stable signature, simple parameters, and straightforward result mapping. When finer control is needed, JPA provides `EntityManager` along with `StoredProcedureQuery` to register parameters, choose `IN`/`OUT`/`INOUT`/`REF_CURSOR` modes, read outputs, handle result sets and update counts, set hints, or coordinate with the persistence context.

This topic focuses on calling procedures directly with `EntityManager`, while also indicating when `@Procedure` is sufficient and what to check to avoid stale entity data after a procedure updates the database.

Running example: PostgreSQL has an `adjust_inventory` procedure that accepts a SKU and delta, updates inventory in the database, and returns the remaining quantity via an `INOUT` parameter.

## 1. When should you call a stored procedure?

Stored procedures are suitable when logic must execute close to the database or is already managed at the database layer:

- Data rules need to be shared across multiple applications or systems.
- An operation consists of multiple SQL statements and needs to execute close to the data.
- Database-specific features such as PL/pgSQL, T-SQL, cursors, or custom optimization logic are needed.
- An existing procedure already resides in the schema and the application must integrate with it.
- Execution privileges on a procedure are preferred over granting direct privileges on certain tables.

Do not move every query into stored procedures. Derived queries, JPQL, and the Criteria API are generally easier to test, refactor, and migrate across databases. Procedures also add dependencies on dialects, schema migrations, database privileges, and result mapping.

## 2. How do @Procedure and EntityManager differ?

Spring Data JPA provides `@Procedure` to bind a repository method to a stored procedure. `EntityManager` provides the standard JPA `StoredProcedureQuery` API to control each invocation step.

| Criterion | `@Procedure` | `EntityManager` + `StoredProcedureQuery` |
| --- | --- | --- |
| Invocation style | Declare repository method and annotation | Create query, register parameters, then call `execute()` |
| Simple signatures | Very suitable | More code than necessary |
| Simple IN/OUT | Supported via method parameter/return mapping | Supported directly via `ParameterMode` |
| Multiple OUT parameters | May require `Map` return type and explicit mapping | Read each output by name or position |
| Multiple result sets/cursors | Depends on mapping and provider support | Has API to iterate result sets and update counts |
| Execution control | Less granular | Can flush, execute, read results, refresh entities, and handle step-by-step |
| When appropriate | Stable single procedure with clear method contract | Needs control over parameters, result mapping, cursors, persistence context, or execution flow |

For example, a simple repository method can use `@Procedure`. When you need to read multiple output parameters, iterate through multiple result sets, or coordinate with managed entities, `EntityManager` is usually easier to control.

## 3. What is StoredProcedureQuery?

`StoredProcedureQuery` is a Jakarta Persistence query object used to invoke a stored procedure in the database. You can create one using `EntityManager`:

```java
StoredProcedureQuery query = entityManager
        .createStoredProcedureQuery("adjust_inventory");
```

Or use an overload with a result class/result set mapping if the procedure returns data rows:

```java
StoredProcedureQuery query = entityManager
        .createStoredProcedureQuery("list_inventory", InventoryItem.class);
```

The procedure name is the object name in the database. It is neither JPQL nor an entity name. Procedure names cannot be bound as parameter values; if the application selects a procedure based on input, use a hardcoded allowlist of names.

### Calling a procedure directly by name

`createStoredProcedureQuery("adjust_inventory")` creates a query by database name. This is useful when a procedure is called in one place or the procedure name depends on deployment configuration.

### Calling a procedure declared with metadata

If a procedure is reused repeatedly with a fixed signature, you can declare `@NamedStoredProcedureQuery` on an entity:

```java
@NamedStoredProcedureQuery(
    name = "InventoryItem.adjustInventory",
    procedureName = "adjust_inventory",
    parameters = {
        @StoredProcedureParameter(name = "p_sku", type = String.class, mode = ParameterMode.IN),
        @StoredProcedureParameter(name = "p_delta", type = Integer.class, mode = ParameterMode.IN),
        @StoredProcedureParameter(name = "p_remaining", type = Integer.class, mode = ParameterMode.INOUT)
    }
)
```

Then invoke it with:

```java
StoredProcedureQuery query = entityManager
        .createNamedStoredProcedureQuery("InventoryItem.adjustInventory");
```

Named metadata centralizes procedure names and parameter signatures. If flexible per-call control is needed, creating the query directly remains suitable.

## 4. Registering parameters and ParameterMode

Before calling the procedure, register all parameters via `registerStoredProcedureParameter`. JPA defines four primary modes:

| Mode | Meaning |
| --- | --- |
| `ParameterMode.IN` | Input value for the procedure. |
| `ParameterMode.OUT` | Value returned by the procedure. |
| `ParameterMode.INOUT` | Caller supplies an initial value and the procedure updates that value. |
| `ParameterMode.REF_CURSOR` | Cursor parameter for reading a result set; support varies by database/provider. |

Example procedure accepting SKU, delta, and returning the remaining quantity via `INOUT`:

```java
query.registerStoredProcedureParameter(1, String.class, ParameterMode.IN);
query.registerStoredProcedureParameter(2, Integer.class, ParameterMode.IN);
query.registerStoredProcedureParameter(3, Integer.class, ParameterMode.INOUT);
```

Parameters can be registered by 1-based position or by name if the database/provider supports the corresponding mapping. Positional registration is easy to cross-check against the procedure signature and avoids parameter-naming differences across dialects.

After registration, assign `IN` values and initial values for `INOUT`:

```java
query.setParameter(1, "SKU-1");
query.setParameter(2, -2);
query.setParameter(3, 0);
```

With `INOUT`, the caller must supply an input value according to the procedure contract; after execution, read back the output value via `getOutputParameterValue`.

### Java types must match SQL types

Choose Java types matching database parameter types: `String` for VARCHAR, `Integer` for INTEGER, `Long` for BIGINT, `BigDecimal` for NUMERIC/DECIMAL, `LocalDate`/`LocalDateTime` or appropriate temporal types for DATE/TIMESTAMP. Some drivers return outputs as subclasses of `Number`; you can check and convert via `Number` instead of hard casting across differing drivers.

Do not concatenate input strings into procedure names or dynamic SQL. Input values must be bound via `setParameter` to prevent SQL injection and quoting errors.

## 5. Executing the procedure and reading OUT/INOUT

`execute()` runs the procedure and returns a boolean indicating whether the first result is a result set:

```java
boolean hasResultSet = query.execute();
Object output = query.getOutputParameterValue(3);
```

For procedures returning only `OUT`/`INOUT` without result sets, you can read outputs after `execute` according to the provider/database contract.

Example:

```java
Number remainingValue = (Number) query.getOutputParameterValue(3);
int remaining = remainingValue.intValue();
```

Output parameters must be registered before `execute`. Do not call `getOutputParameterValue` for unregistered parameters or parameters without mode `OUT`/`INOUT`/`REF_CURSOR`.

### When the procedure returns a result set

If the procedure returns a result set, read it using `getResultList()` or `getSingleResult()` according to the declared result type:

```java
boolean hasResultSet = query.execute();
if (hasResultSet) {
    List<?> rows = query.getResultList();
}
```

For result sets returning entities, create the query with the result class. For DTOs or multiple columns, use `@SqlResultSetMapping` and the corresponding mapping name.

## 6. Multiple result sets and update counts

A procedure can emit multiple result sets or update counts. The `StoredProcedureQuery` API lets you iterate through them sequentially:

```java
boolean hasResult = query.execute();

while (true) {
    if (hasResult) {
        List<?> rows = query.getResultList();
        // Map or process this result set.
    } else {
        int updateCount = query.getUpdateCount();
        if (updateCount == -1) {
            break;
        }
        // Record or inspect the update count.
    }

    hasResult = query.hasMoreResults();
}
```

Actual results and update count values depend on the database, JDBC driver, and provider. Some procedures return no result sets; some return multiple result sets; some providers require specific mapping configurations.

With multiple result sets, consume all results in the order provided by the driver/provider before fetching output parameters if required by the database. Test with the exact production engine and driver.

## 7. REF_CURSOR and result mapping

Some databases, notably PostgreSQL and Oracle, support returning data via `REF_CURSOR`. JPA provides `ParameterMode.REF_CURSOR`, though support and how cursors are retrieved depend on the database/provider.

Example registering a cursor:

```java
query.registerStoredProcedureParameter(
        1, void.class, ParameterMode.REF_CURSOR);
```

With cursors, use an appropriate mapping/result class and test reading the result set with the specific provider. Do not assume all databases support `REF_CURSOR` the same way.

### Entity mapping and DTO mapping

If the result set structurally matches an entity, you can pass the result class:

```java
StoredProcedureQuery query = entityManager.createStoredProcedureQuery(
        "list_inventory", InventoryItem.class);
```

If the result set consists of computed columns or a DTO, declare `@SqlResultSetMapping` and create the query with the mapping name:

```java
StoredProcedureQuery query = entityManager.createStoredProcedureQuery(
        "inventory_summary", "InventorySummaryMapping");
```

Mappings must match column names, aliases, data types, and result constructors/properties. Aliases in SQL should be stable to avoid errors when procedures change.

## 8. Transactions and flushing before calling a procedure

Procedures may read or write tables that JPA also manages. Therefore, you must understand the synchronization order between the persistence context and the database.

### Flushing before calling

`EntityManager` may hold pending changes not yet sent to the database. If the procedure needs to see those changes, call `entityManager.flush()` before executing:

```java
entityManager.flush();
query.execute();
```

Flushing synchronizes pending changes in the persistence context to the database without committing the transaction.

### Procedure writes and managed entities

Procedures run SQL directly and do not notify Hibernate that managed entities were modified. Entities in the persistence context may retain stale values.

There are two common approaches:

- Call `entityManager.refresh(entity)` for specific entities after the procedure.
- Call `entityManager.clear()` to detach all entities in the persistence context and reload them.

`clear()` has a broad scope and can discard unflushed changes. Therefore, if you need to preserve other managed entities, flush beforehand or refresh only the relevant entities.

Example:

```java
entityManager.flush();
query.execute();
entityManager.refresh(inventoryItem);
```

### Transaction boundaries

Procedures that write data should be called inside a Spring/JPA-managed transaction:

```java
@Transactional
public int adjustInventory(String sku, int delta) {
    // Register parameters, execute procedure and read output.
}
```

Do not let the procedure issue its own `COMMIT` or `ROLLBACK` when invoked within a JPA-managed transaction. Some databases forbid transaction control inside procedures running within a transaction block; furthermore, committing separately breaks the atomicity of the use case.

If the procedure fails, the exception must propagate out of the transactional method so the transaction rolls back. If you catch the exception and continue, the transaction may already be marked rollback-only.

## 9. When is @Procedure enough?

For simple procedures with stable inputs/outputs, a repository method can declare:

```java
public interface InventoryRepository extends JpaRepository<InventoryItem, Long> {
    @Procedure(procedureName = "adjust_inventory")
    Integer adjustInventory(
            @Param("p_sku") String sku,
            @Param("p_delta") Integer delta,
            @Param("p_remaining") Integer initialRemaining
    );
}
```

Exact signatures depend on how the procedure declares `OUT`/`INOUT` and on the database/provider. Check parameter mapping for the Spring Data JPA version you use. With multiple output parameters, Spring Data can use `Map<String, Object>` to return multiple values.

Use `EntityManager` when you need to:

- Explicitly register parameter modes by position or name.
- Retrieve multiple output parameters and control when they are read.
- Iterate multiple result sets or `REF_CURSOR`.
- Specify result classes or `@SqlResultSetMapping`.
- Flush beforehand, refresh/clear afterward, or coordinate multiple operations within a transaction.
- Control query hints, timeouts, or `StoredProcedureQuery` options.

## 10. Error handling and security

### Exceptions

Procedures can throw SQL errors, parameter errors, constraint violations, or business errors via `RAISE`/`THROW`. The JPA provider may throw `PersistenceException`; Spring exception translation can convert it to a corresponding `DataAccessException`.

Do not catch all exceptions and return default values. Distinguish input errors, business errors, and database errors. If a procedure runs in a transaction, let errors propagate when rollback is needed.

### Parameter binding

Always use `setParameter` for input values. Do not concatenate inputs into dynamic SQL inside Java. If the procedure itself builds dynamic SQL, use quoting/identifier validation and parameter binding according to database syntax.

### Execution privileges

The application's database user should only have the privileges needed to invoke the procedure and access related objects. Stored procedures are not automatically secure: inspect `SECURITY DEFINER`/`EXECUTE AS`, search paths, table privileges, and dynamic SQL per database.

### Timeouts and hints

`StoredProcedureQuery` inherits support for configuring certain query hints and timeouts per JPA/provider. Supported hint names and capabilities depend on the provider/database; verify them via integration tests. Do not assume JPA timeouts behave identically to socket timeouts or transaction timeouts.

## 11. Runnable example with Java 17+, Spring Boot 3.4.5, and PostgreSQL

The example uses the `adjust_inventory` procedure to add/subtract inventory and return the remaining quantity via an `INOUT` parameter. PostgreSQL is run using Docker Compose.

### Project structure

```text
entitymanager-procedure/
├── docker-compose.yml
├── pom.xml
└── src/
    └── main/
        ├── java/com/example/procedure/
        │   ├── ProcedureApplication.java
        │   ├── InventoryItem.java
        │   ├── InventoryRepository.java
        │   └── InventoryProcedureService.java
        └── resources/
            ├── application.properties
            ├── schema.sql
            └── data.sql
```

### `docker-compose.yml`

```yaml
services:
  db:
    image: postgres:16
    environment:
      POSTGRES_DB: procedures
      POSTGRES_USER: app
      POSTGRES_PASSWORD: app
    ports:
      - "5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U app -d procedures"]
      interval: 5s
      timeout: 3s
      retries: 20
```

### `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.4.5</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>entitymanager-procedure</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-data-jpa</artifactId>
        </dependency>
        <dependency>
            <groupId>org.postgresql</groupId>
            <artifactId>postgresql</artifactId>
            <scope>runtime</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

### `src/main/resources/application.properties`

```properties
spring.datasource.url=jdbc:postgresql://localhost:5432/procedures
spring.datasource.username=app
spring.datasource.password=app
spring.jpa.hibernate.ddl-auto=none
spring.sql.init.mode=always
spring.jpa.open-in-view=false
logging.level.org.hibernate.SQL=DEBUG
```

`ddl-auto=none` prevents Hibernate from recreating the schema. `schema.sql` and `data.sql` create the table, procedure, and sample data on application startup.

### `src/main/resources/schema.sql`

```sql
create table if not exists inventory_items (
    id bigint generated by default as identity primary key,
    sku varchar(60) not null unique,
    available integer not null check (available >= 0)
);

create or replace procedure adjust_inventory(
    in p_sku varchar(60),
    in p_delta integer,
    inout p_remaining integer
)
language plpgsql
as $$
begin
    update inventory_items
       set available = available + p_delta
     where sku = p_sku
       and available + p_delta >= 0
    returning available into p_remaining;

    if not found then
        if exists (select 1 from inventory_items where sku = p_sku) then
            raise exception 'Insufficient inventory for SKU %', p_sku
                using errcode = 'P0001';
        else
            raise exception 'Unknown SKU %', p_sku
                using errcode = 'P0002';
        end if;
    end if;
end;
$$;
```

The procedure updates inventory in a single conditional `UPDATE`. If the SKU does not exist or the resulting quantity would be negative, the procedure raises an exception and the transaction can roll back.

### `src/main/resources/data.sql`

```sql
insert into inventory_items(sku, available)
values ('SKU-1', 10)
on conflict (sku) do nothing;
```

### `InventoryItem.java`

```java
package com.example.procedure;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "inventory_items")
public class InventoryItem {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, unique = true, length = 60)
    private String sku;

    @Column(nullable = false)
    private int available;

    protected InventoryItem() {
    }

    public Long getId() {
        return id;
    }

    public String getSku() {
        return sku;
    }

    public int getAvailable() {
        return available;
    }
}
```

### `InventoryRepository.java`

```java
package com.example.procedure;

import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;

public interface InventoryRepository extends JpaRepository<InventoryItem, Long> {
    Optional<InventoryItem> findBySku(String sku);
}
```

### `InventoryProcedureService.java`

```java
package com.example.procedure;

import jakarta.persistence.EntityManager;
import jakarta.persistence.ParameterMode;
import jakarta.persistence.StoredProcedureQuery;
import java.util.Objects;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class InventoryProcedureService {
    private final EntityManager entityManager;
    private final InventoryRepository inventoryRepository;

    public InventoryProcedureService(
            EntityManager entityManager, InventoryRepository inventoryRepository) {
        this.entityManager = entityManager;
        this.inventoryRepository = inventoryRepository;
    }

    @Transactional
    public int adjust(String sku, int delta) {
        if (sku == null || sku.isBlank() || delta == 0) {
            throw new IllegalArgumentException("sku and non-zero delta are required");
        }

        InventoryItem item = inventoryRepository.findBySku(sku)
                .orElseThrow(() -> new IllegalArgumentException("Unknown SKU: " + sku));

        // Synchronize pending JPA changes before the procedure reads the table.
        entityManager.flush();

        StoredProcedureQuery procedure =
                entityManager.createStoredProcedureQuery("adjust_inventory");
        procedure.registerStoredProcedureParameter(1, String.class, ParameterMode.IN);
        procedure.registerStoredProcedureParameter(2, Integer.class, ParameterMode.IN);
        procedure.registerStoredProcedureParameter(3, Integer.class, ParameterMode.INOUT);

        procedure.setParameter(1, sku);
        procedure.setParameter(2, delta);
        procedure.setParameter(3, 0);

        boolean hasResultSet = procedure.execute();
        if (hasResultSet) {
            throw new IllegalStateException("Expected no result set from adjust_inventory");
        }

        Number output = (Number) procedure.getOutputParameterValue(3);
        int remaining = Objects.requireNonNull(output).intValue();

        // The procedure changed the row outside Hibernate's dirty checking.
        entityManager.refresh(item);
        if (item.getAvailable() != remaining) {
            throw new IllegalStateException("Procedure output does not match refreshed entity");
        }

        return remaining;
    }
}
```

`EntityManager` is constructor-injected. Spring supplies a shared proxy aligned with the current transaction. The service reads the entity before calling the procedure to demonstrate `refresh`; `flush()` ensures pending JPA changes are synchronized before the procedure runs.

Since the procedure updates the row directly, Hibernate does not automatically know that `available` changed. `refresh(item)` reloads the managed entity. If the procedure updates multiple entities or the caller does not need to keep managed objects, you can use `clear()` and requery; remember that `clear()` detaches every entity in the persistence context.

### `ProcedureApplication.java`

```java
package com.example.procedure;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class ProcedureApplication {
    public static void main(String[] args) {
        SpringApplication.run(ProcedureApplication.class, args);
    }

    @Bean
    CommandLineRunner demo(InventoryProcedureService service) {
        return args -> {
            int remaining = service.adjust("SKU-1", -2);
            System.out.println("Remaining inventory: " + remaining);
        };
    }
}
```

### Running the application

Start PostgreSQL:

```bash
docker compose up -d --wait
```

Run Spring Boot:

```bash
mvn spring-boot:run
```

Stdout:

```text
Remaining inventory: 8
```

Initial data has 10 items. The procedure receives `p_delta = -2`, updates inventory to 8, and returns that value via `p_remaining`. The service reads the `OUT`/`INOUT` parameter and refreshes the entity so the persistence context matches the database.

## 12. Testing stored procedures

Integration tests must run against the exact database engine because procedure syntax and parameter binding depend on the dialect. You can use Testcontainers PostgreSQL or a database container in CI.

Example service test:

```java
@SpringBootTest
class InventoryProcedureIntegrationTest {
    @Autowired
    private InventoryProcedureService service;

    @Autowired
    private InventoryRepository repository;

    @Test
    void readsInOutValueAndRefreshesManagedEntity() {
        repository.saveAndFlush(new InventoryItem("TEST-1", 5));

        int remaining = service.adjust("TEST-1", -2);

        assertThat(remaining).isEqualTo(3);
        assertThat(repository.findBySku("TEST-1").orElseThrow().getAvailable())
                .isEqualTo(3);
    }
}
```

This snippet illustrates the assertions; to run standalone, add a constructor `InventoryItem(String sku, int available)` alongside the sample entity's getters, add JUnit/AssertJ imports, and configure the test database. You should also test:

- Unknown SKU.
- Delta causing negative inventory.
- Positive delta to restock inventory.
- Procedure rollback when an exception is raised.
- `OUT`/`INOUT` parameters having the right types and values.
- Managed entities being refreshed after procedure writes.
- Multiple result sets or `REF_CURSOR` if the actual procedure returns them.

## 13. Common mistakes

1. **Using @Procedure for overly complex flows:** switch to `EntityManager` when control over multiple outputs, result sets, cursors, or the persistence context is required.
2. **Forgetting to register parameters:** register every parameter with the right position/name, type, and mode before `execute`.
3. **Confusing OUT with INOUT:** `INOUT` requires an initial input value and returns the modified value.
4. **Reading outputs before execute:** read outputs only after the procedure has run and the provider has finished processing any prerequisite results.
5. **Assuming a procedure always returns a result set:** `execute()` can return false; check the first result and iterate subsequent results if present.
6. **Hard-casting outputs:** drivers may return subclasses of `Number`; inspect types or convert safely.
7. **Not flushing before a procedure:** the procedure may fail to see JPA changes not yet sent to the database.
8. **Not refreshing entities after a procedure:** the persistence context can hold stale values because the procedure updates the database directly.
9. **Calling clear without flushing:** can detach entities and lose unsynchronized changes.
10. **Procedure self-committing inside a JPA transaction:** can break atomicity or be rejected by the database.
11. **Using H2 to verify PostgreSQL/Oracle cursors:** syntax, OUT parameters, and `REF_CURSOR` depend on engine/driver.
12. **Concatenating input into dynamic SQL:** bind values and validate identifiers via allowlist.
13. **Not managing schema migrations:** procedure versions should be deployed alongside the schema via Flyway/Liquibase or an equivalent migration tool.
14. **Granting overly broad database privileges:** grant only `EXECUTE` and required privileges per security design.

## 14. Checklist before calling procedures with EntityManager

- [ ] Procedure exists in the schema with the exact database name.
- [ ] Order or name, type, and mode of all parameters are clearly defined.
- [ ] `INOUT` receives an initial input value and output is read after `execute`.
- [ ] Result sets, update counts, and `REF_CURSOR` are handled properly if present.
- [ ] `EntityManager` flushes before the procedure when pending changes must be synchronized.
- [ ] Managed entities are refreshed/cleared after the procedure updates data.
- [ ] Procedure runs inside an appropriate transaction and does not commit/roll back outside the contract.
- [ ] Inputs use parameter binding; procedure names/identifiers are allowlisted.
- [ ] `EXECUTE` privileges and table permissions follow least privilege.
- [ ] Integration tests run against the target database engine and JDBC driver.

## 15. Practical guidelines

- Use `@Procedure` for simple, stable procedure signatures that map cleanly to repository methods.
- Use `EntityManager.createStoredProcedureQuery` when you need control over parameter modes, outputs, result sets, cursors, or the persistence context.
- Register all parameters completely before assigning values and executing.
- Use `IN`, `OUT`, `INOUT`, and `REF_CURSOR` according to the database contract.
- Use `execute()`, `getResultList()`, `hasMoreResults()`, `getUpdateCount()`, and `getOutputParameterValue()` according to the result types returned by the procedure.
- Flush before a procedure when it needs to observe unsynchronized JPA changes.
- Refresh entities or clear the persistence context after a procedure modifies data.
- Let Spring manage transactions; avoid transaction control inside procedures called from JPA.
- Test against the exact database/provider/driver since stored procedures are not completely portable.

Key takeaway: **`@Procedure` fits simple calls; `EntityManager` and `StoredProcedureQuery` fit cases needing granular control over parameters, outputs, result sets/cursors, and persistence context synchronization. Bind parameters with the right modes, flush before procedures need fresh data, refresh entities after procedure writes, and let Spring/JPA manage transactions.**
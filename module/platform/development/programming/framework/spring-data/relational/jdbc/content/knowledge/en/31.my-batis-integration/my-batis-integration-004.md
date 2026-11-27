# Step-by-Step CRUD Delegation and Generated Key Handling in Spring Data JDBC with MyBatis

## 1. Integration Concept: Spring Data JDBC Orchestrates, MyBatis Executes SQL

Spring Data JDBC provides aggregate-oriented repositories. When calling methods such as `save`, `saveAll`, `findById`, or `deleteById`, the framework analyzes the aggregate and produces a sequence of persistence operations. Saving a single aggregate can require multiple SQL statements: inserting or updating the aggregate root, then inserting/updating/deleting rows belonging to child collections.

MyBatis can take over running the SQL and mapping the results for each of those steps. Spring Data JDBC still manages the repository, decides which operations need to run, and supplies entity details; MyBatis receives the corresponding mapped statement to execute the SQL.

Example:

- The application calls `customerRepository.save(customer)`.
- Spring Data JDBC determines whether this is an insert or an update.
- When an insert is needed, the framework looks up the MyBatis statement matching the naming convention for the `Customer` entity.
- If the statement exists, MyBatis executes the SQL and maps the result.
- If no matching MyBatis statement exists, a combined strategy configuration can route that step back to `DefaultDataAccessStrategy`.
- Spring Data JDBC continues with the remaining steps of the aggregate.

Thus, this integration is **per-step data-access delegation**, not replacing the entire repository with a mapper interface. You can use MyBatis for specific statements that need custom SQL and let Spring Data JDBC handle the remaining steps with the default strategy.

## 2. Main Components

| Component | Role |
|---|---|
| `CrudRepository` | Repository API used by services |
| `JdbcAggregateTemplate` | Orchestrates operations on aggregates |
| `DataAccessStrategy` | Abstraction for individual SQL steps on an entity |
| `MyBatisDataAccessStrategy` | Executes steps through MyBatis |
| `MyBatisJdbcConfiguration` | Configures Spring Data JDBC for MyBatis integration |
| `SqlSessionFactory` | Creates MyBatis sessions and holds mapped statements |
| `SqlSessionTemplate` | Spring-managed `SqlSession` that participates in transactions |
| `MyBatisContext` | Parameter object Spring Data JDBC passes to mapped statements |

`DataAccessStrategy` handles operations at the single entity/statement level. `JdbcAggregateOperations` is the abstraction that orchestrates the entire aggregate. This separation explains why a single repository call can trigger multiple distinct mapped statements.

In Spring Data JDBC, key classes reside in the following packages:

~~~java
org.springframework.data.jdbc.repository.config.MyBatisJdbcConfiguration
org.springframework.data.jdbc.mybatis.MyBatisDataAccessStrategy
org.springframework.data.jdbc.mybatis.MyBatisContext
org.springframework.data.jdbc.core.convert.DataAccessStrategy
~~~

Package names and APIs can vary across Spring Data Relational versions. Use the documentation for the exact version managed by your project's Spring Boot or dependency management.

## 3. Configuring Spring Data JDBC and MyBatis

The recommended configuration approach in Spring Data JDBC is to import `MyBatisJdbcConfiguration` alongside repository configuration, then provide a `SqlSession` in the Spring context.

Java configuration example:

~~~java
import javax.sql.DataSource;

import org.apache.ibatis.session.SqlSessionFactory;
import org.mybatis.spring.SqlSessionFactoryBean;
import org.mybatis.spring.SqlSessionTemplate;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Import;
import org.springframework.core.io.support.PathMatchingResourcePatternResolver;
import org.springframework.data.jdbc.repository.config.EnableJdbcRepositories;
import org.springframework.data.jdbc.repository.config.MyBatisJdbcConfiguration;

@Configuration
@EnableJdbcRepositories(
        basePackages = "com.example.persistence"
)
@Import(MyBatisJdbcConfiguration.class)
public class JdbcPersistenceConfiguration {

    @Bean
    public SqlSessionFactory sqlSessionFactory(DataSource dataSource)
            throws Exception {

        SqlSessionFactoryBean factory = new SqlSessionFactoryBean();
        factory.setDataSource(dataSource);
        factory.setMapperLocations(
                new PathMatchingResourcePatternResolver()
                        .getResources("classpath*:mybatis/**/*.xml")
        );

        return factory.getObject();
    }

    @Bean
    public SqlSessionTemplate sqlSessionTemplate(
            SqlSessionFactory sqlSessionFactory
    ) {
        return new SqlSessionTemplate(sqlSessionFactory);
    }
}
~~~

`SqlSessionFactoryBean` creates `SqlSessionFactory` from the DataSource and XML mapper files. `SqlSessionTemplate` implements `SqlSession` and can be injected into Spring Data JDBC's configuration. If using the MyBatis Spring Boot starter, the starter usually auto-configures `SqlSessionFactory` and `SqlSessionTemplate`; do not declare duplicate beans if they already exist.

The configuration above illustrates explicit declarations. In real applications, ensure:

- XML mappers reside at the configured path.
- MyBatis's DataSource is the same DataSource used by Spring Data JDBC.
- The `SqlSession` bean can be discovered by `MyBatisJdbcConfiguration`.
- Repository scanning covers the exact packages containing repositories.
- MyBatis, MyBatis-Spring, Spring Data JDBC, and Spring Boot versions are compatible.

### 3.1. Dependencies

If not using a starter, the application needs the MyBatis and MyBatis-Spring libraries alongside Spring Data JDBC. With Gradle, the dependencies might look like:

~~~groovy
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-jdbc")
    implementation("org.mybatis:mybatis")
    implementation("org.mybatis:mybatis-spring")
}
~~~

If using the MyBatis Spring Boot starter, choose a version compatible with your project's Spring Boot version and let dependency management control related versions. Do not mix multiple versions of MyBatis-Spring or declare multiple starters with overlapping configuration.

## 4. Why Is SqlSessionTemplate Needed?

MyBatis can create sessions directly from `SqlSessionFactory`, but Spring Data JDBC needs MyBatis operations to participate properly in Spring transactions.

`SqlSessionTemplate` is a thread-safe implementation of `SqlSession`. It locates the session bound to the current transaction, manages session lifecycles, and performs commit/rollback according to Spring's transaction configuration.

Do not inject or hold a manually created `DefaultSqlSession` in repositories/services. Manually opened sessions can use a separate connection or transaction, preventing MyBatis operations from committing/rolling back together with Spring Data JDBC operations.

Configuration rules:

- `SqlSessionTemplate` must be created from the `SqlSessionFactory` used by the application.
- `SqlSessionFactoryBean` must use the same `DataSource` as the Spring transaction manager.
- Operations requiring atomicity should be invoked within the same service transaction.
- Do not manually call commit, rollback, or close on a Spring-managed `SqlSessionTemplate`.

If MyBatis and Spring Data JDBC use two different DataSources, a standard JDBC transaction will not automatically cover both resources. In that case, configure appropriate transaction handling or design a separate distributed workflow.

## 5. Namespace and Mapped Statement Naming Conventions

By default, the MyBatis namespace is formed from the entity class's fully qualified name plus the `Mapper` suffix. The statement ID then identifies the operation.

Example entity:

~~~java
package com.example.domain;

import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Table;

@Table("customers")
public class Customer {

    @Id
    private Long id;

    private String name;

    private String email;

    // constructors, getters and setters
}
~~~

Corresponding namespace:

~~~xml
<mapper namespace="com.example.domain.CustomerMapper">
    <insert id="insert">
        ...
    </insert>
</mapper>
~~~

For entity `com.example.domain.Customer`, Spring Data JDBC looks up the statement:

~~~text
com.example.domain.CustomerMapper.insert
~~~

Common statement IDs:

| Statement ID | Purpose |
|---|---|
| `insert` | Insert an entity |
| `update` | Update an entity |
| `delete` | Delete an entity by ID |
| `findById` | Read an aggregate root by ID |
| `findAll` | Read all aggregate roots |
| `findAllById` | Read aggregates by a list of IDs |
| `findAllByPath-<propertyPath>` | Read child entities by property path |
| `findAllSorted` | Read sorted aggregates |
| `findAllPaged` | Read paged aggregates |
| `count` | Count aggregate roots |
| `delete-<propertyPath>` | Delete child entities by aggregate property path |
| `deleteAll-<propertyPath>` | Delete child entities by property path |
| `deleteAll` | Delete all aggregate roots of the domain type |

Do not name the namespace after the repository interface. The default namespace is based on the domain entity type. If changing the naming convention, Spring Data JDBC offers `NamespaceStrategy` to customize namespace generation; configure it consistently with your XML mappers.

## 6. How Does Spring Data JDBC Delegate CRUD Step by Step?

A repository method does not necessarily map to a single SQL statement. Spring Data JDBC processes aggregates according to their mappings and may call the strategy multiple times for the root and child entities.

The following table describes statements commonly looked up by MyBatis conventions:

| Statement | Repository operations that may trigger it | Data in MyBatisContext |
|---|---|---|
| `insert` | `save`, `saveAll` | Instance to save, domain type, reference key from parent aggregate |
| `update` | `save`, `saveAll` | Instance to save, domain type |
| `delete` | `delete`, `deleteById` | ID and domain type |
| `delete-<propertyPath>` | `deleteById` | Aggregate root ID and child entity domain type |
| `deleteAll-<propertyPath>` | `deleteAll` | Child entity domain type |
| `deleteAll` | `deleteAll` | Aggregate root domain type |
| `findById` | `findById` | ID and domain type |
| `findAll` | `findAll` | Domain type |
| `findAllById` | `findAllById` | List of IDs and domain type |
| `findAllByPath-<propertyPath>` | Relation read operations | Aggregate identifier and property path |
| `findAllSorted` | `findAll(Sort)` | Sort |
| `findAllPaged` | `findAll(Pageable)` | Pageable |
| `count` | `count` | Domain type |

Statement names and context details can depend on the version. This table reflects the conventions in Spring Data JDBC's integration documentation; when upgrading, re-check the reference documentation and API of the version in use.

### 6.1. Aggregate Insert and Update

Suppose an `Order` aggregate has a `lines` collection. When saving a new `Order`, Spring Data JDBC may need to:

1. Insert a row into the `orders` table.
2. Retrieve the database-generated ID for the order.
3. Insert each `OrderLine` with the `order_id` foreign key.
4. Retrieve generated keys for children if children have their own IDs.

For an existing aggregate, the framework may update the root and synchronize child entities according to Spring Data JDBC's persistence strategy. Each entity requiring an operation is routed to the corresponding `DataAccessStrategy`.

Therefore, if you want MyBatis to handle both root and children, define insert/update statements for the proper entity types as well as any statements handling related property paths.

### 6.2. Deleting Aggregates and Child Entities

When deleting an aggregate root by ID, Spring Data JDBC may need to delete child entities by property path before deleting the root, depending on mapping and persistence strategy.

Example aggregate:

~~~java
@Table("orders")
public class Order {

    @Id
    private Long id;

    @MappedCollection(idColumn = "order_id")
    private List<OrderLine> lines;
}
~~~

If the property path is `lines`, the aggregate root's namespace may need the statement:

~~~xml
<delete id="delete-lines">
    DELETE FROM order_lines
    WHERE order_id = #{id}
</delete>
~~~

This statement belongs to the `Order` root namespace because it deletes entities referenced by the `Order` aggregate. It does not necessarily belong to the `OrderLineMapper` namespace.

For `deleteAll`, the collection statement can be named `deleteAll-lines`. Verify property paths, back-reference column names, and deletion order compatible with foreign keys in your schema.

## 7. MyBatisContext: The Statement Parameter Object

Mapped statements do not receive the entity directly like ordinary mapper methods. Spring Data JDBC passes a `MyBatisContext` to supply the data required for the operation.

Key accessors:

| Accessor | Meaning |
|---|---|
| `getInstance()` | Entity instance being inserted/updated; may be null for read operations |
| `getId()` | ID of the entity/aggregate being operated on |
| `getDomainType()` | Related domain type Class |
| `getIdentifier()` | Identifier describing the aggregate root and parts along the property path |
| `get(key)` | Additional value, such as parent aggregate ID or collection key/index |

In XML mappers, MyBatis can access the context's JavaBean properties. Example:

~~~xml
#{instance.name}
#{instance.email}
#{instance.id}
#{id}
~~~

`instance.name` retrieves the property from the entity wrapped inside the context. `id` is the ID supplied by the context for the operation. Do not confuse these two values: when inserting a new entity, the context's ID may not exist yet, while the database-generated ID will be written into the instance's property.

For child entities, the context also carries linking info for the parent aggregate. The provided key name depends on `NamingStrategy` and the property path. Use the exact back-reference key name provided by Spring Data JDBC instead of guessing column names in the mapper.

## 8. Example XML Mapper for Basic CRUD

For `Customer` with an auto-increment database ID, the XML mapper can declare:

~~~xml
<?xml version="1.0" encoding="UTF-8" ?>
<!DOCTYPE mapper
        PUBLIC "-//mybatis.org//DTD Mapper 3.0//EN"
        "http://mybatis.org/dtd/mybatis-3-mapper.dtd">

<mapper namespace="com.example.domain.CustomerMapper">

    <resultMap id="customerMap"
               type="com.example.domain.Customer">
        <id property="id" column="id"/>
        <result property="name" column="name"/>
        <result property="email" column="email"/>
    </resultMap>

    <insert id="insert"
            useGeneratedKeys="true"
            keyProperty="instance.id"
            keyColumn="id">
        INSERT INTO customers (name, email)
        VALUES (#{instance.name}, #{instance.email})
    </insert>

    <update id="update">
        UPDATE customers
        SET name = #{instance.name},
            email = #{instance.email}
        WHERE id = #{instance.id}
    </update>

    <delete id="delete">
        DELETE FROM customers
        WHERE id = #{id}
    </delete>

    <select id="findById" resultMap="customerMap">
        SELECT id, name, email
        FROM customers
        WHERE id = #{id}
    </select>

    <select id="findAll" resultMap="customerMap">
        SELECT id, name, email
        FROM customers
        ORDER BY id
    </select>

    <select id="findAllById" resultMap="customerMap">
        SELECT id, name, email
        FROM customers
        WHERE id IN
        <foreach collection="id"
                 item="customerId"
                 open="("
                 separator=","
                 close=")">
            #{customerId}
        </foreach>
    </select>

    <select id="count" resultType="long">
        SELECT COUNT(*)
        FROM customers
    </select>

</mapper>
~~~

This example illustrates basic statements. In real applications, adjust `resultMap`, ID types, SQL dialect, schema, and column names to match the entity. In particular, collections or child entities may require their own mappers and property-path statements.

Spring Data JDBC calls repository methods as usual:

~~~java
Customer saved = customerRepository.save(
        new Customer("An", "an@example.com")
);

Customer loaded = customerRepository.findById(saved.getId())
        .orElseThrow();
~~~

The service does not need to call `sqlSession.insert("...")` directly for CRUD operations delegated by Spring Data JDBC. The framework locates statements based on namespace and ID conventions.

## 9. Generated Keys: Database Creates the ID and MyBatis Returns It to the Entity

A generated key is a primary key value produced by the database during insert, typically with identity/auto-increment columns or sequences.

With MyBatis, there are two common ways:

1. JDBC generated keys via `useGeneratedKeys` and `keyProperty`.
2. Fetching the key with `selectKey` before or after the INSERT statement.

When integrating with Spring Data JDBC, remember that the mapped statement's parameter is `MyBatisContext`. The entity sits inside the `instance` property. Therefore, when you want MyBatis to write the generated key into the entity, `keyProperty` must point to the nested property inside the context.

### 9.1. JDBC Generated Keys with useGeneratedKeys

Example:

~~~xml
<insert id="insert"
        useGeneratedKeys="true"
        keyProperty="instance.id"
        keyColumn="id">
    INSERT INTO customers (name, email)
    VALUES (#{instance.name}, #{instance.email})
</insert>
~~~

Meaning:

- `useGeneratedKeys="true"` instructs MyBatis to use JDBC `getGeneratedKeys()` to retrieve the database-generated key.
- `keyProperty="instance.id"` indicates the property receiving the key value on the entity wrapped inside `MyBatisContext`.
- `keyColumn="id"` specifies the key column in the database; some databases/drivers require this setting.

**Why `instance.id`?** The parameter object of the mapped statement is `MyBatisContext`, not `Customer` directly. The context has the `getInstance()` accessor, so entity properties lie under the `instance` branch. If you only use `keyProperty="id"`, MyBatis will try to write the key into the context's `id` property instead of `Customer.id`.

After inserting, MyBatis writes the key into `instance.id`. Spring Data JDBC can then continue using that ID in subsequent aggregate steps, such as inserting `OrderLine` rows with foreign keys pointing to the newly created `Order`.

Generated-key retrieval capability depends on the JDBC driver and database. Verify that the driver supports `getGeneratedKeys` and configure `keyColumn` when required by the database engine.

### 9.2. Using selectKey with Sequences

Some databases or ID strategies need to fetch values from a sequence. You can use `selectKey` to fetch the ID before INSERT:

~~~xml
<insert id="insert">
    <selectKey keyProperty="instance.id"
               resultType="long"
               order="BEFORE">
        SELECT nextval('customer_id_seq')
    </selectKey>

    INSERT INTO customers (id, name, email)
    VALUES (
        #{instance.id},
        #{instance.name},
        #{instance.email}
    )
</insert>
~~~

In the PostgreSQL example, the SELECT fetches the next sequence value before inserting. MyBatis writes the value into `instance.id`, and then the INSERT uses that value.

On other databases, sequence syntax differs. For example, Oracle has its own sequence syntax. Do not copy PostgreSQL's SELECT verbatim to another database without adjustment.

You can use `selectKey order="AFTER"` if the database provides a way to retrieve the identity after inserting. Pick the key-retrieval approach that matches your database and ensure the key is assigned to the right property.

### 9.3. Generated Key vs. Update Count

Distinguish between two results:

- An insert statement normally returns the number of inserted rows, such as `1`.
- The generated key is the ID value written into the property specified by `keyProperty`.

`useGeneratedKeys` does not turn the return value of insert into the ID. It instructs MyBatis to fetch the key and assign it to the entity. Spring Data JDBC needs that ID value to continue persistence and return the saved entity to the caller.

### 9.4. Entities Need a Writable Property

MyBatis must be able to assign the generated key value into the designated property. For mutable POJOs, provide a setter or field accessible to MyBatis per its reflection configuration.

If using Java records or immutable entities, writing generated keys into a nested property may not fit how MyBatis populates keys. In this case, check the mapping capabilities of your version and consider generating the ID prior to insert via callbacks/sequences or choosing a strategy suitable for an immutable model.

## 10. Application-Assigned IDs vs. Database-Assigned IDs

Not every entity uses auto-increment. Two main cases can be distinguished:

| Strategy | How to insert |
|---|---|
| Database generates ID | Omit ID from insert column list; configure `useGeneratedKeys` or `selectKey` |
| Application already assigned ID | Pass ID from `instance` into the INSERT statement; no generated key retrieval needed |
| ID fetched from sequence before insert | Use `selectKey BEFORE` or an ID-generating callback |
| ID is an application-generated UUID | Assign UUID before `save` and write the value into the ID column |

Example with a pre-assigned ID:

~~~xml
<insert id="insert">
    INSERT INTO customers (id, name, email)
    VALUES (
        #{instance.id},
        #{instance.name},
        #{instance.email}
    )
</insert>
~~~

In this case, the ID is already present on the entity. Do not blindly enable generated keys because the database is not the source of ID generation.

Align the ID strategy across entity mapping, database schema, and MyBatis statements. If an entity is designed for database-generated IDs but the SQL manually passes null or omits key retrieval, the aggregate may fail to receive an ID after saving.

## 11. Generated Keys for Child Entities in an Aggregate

Suppose an `Order` has multiple `OrderLine` items, and each `OrderLine` also has its own ID:

~~~java
@Table("orders")
public class Order {

    @Id
    private Long id;

    @MappedCollection(idColumn = "order_id")
    private List<OrderLine> lines;
}
~~~

When saving a new `Order`, Spring Data JDBC needs the root's ID to write the child rows. Overview sequence:

~~~text
1. INSERT orders
2. MyBatis retrieves generated key and writes it into Order.id
3. Spring Data JDBC has Order's ID
4. INSERT order_lines with the corresponding order_id
5. If OrderLine has its own ID, MyBatis retrieves key and assigns it to OrderLine.id
~~~

The insert statement for `OrderLine` belongs to the `OrderLine` entity's namespace. The statement must use `instance` values for child properties and the parent reference value supplied by `MyBatisContext`.

If children also use auto-increment, the child mapper needs its own generated key configuration:

~~~xml
<insert id="insert"
        useGeneratedKeys="true"
        keyProperty="instance.id"
        keyColumn="id">
    INSERT INTO order_lines (order_id, sku, quantity)
    VALUES (
        #{orderId},
        #{instance.sku},
        #{instance.quantity}
    )
</insert>
~~~

In this example, `orderId` represents the back-reference key provided by the context. The actual key name depends on `NamingStrategy` and the application's mapping; determine the exact key supplied in `MyBatisContext` instead of assuming it is always `orderId`.

If the root ID is not retrieved or not written back onto the entity, child inserts may fail due to a NULL foreign key or point to the wrong parent. Therefore, test generated keys on both root and children when aggregates have multiple levels.

## 12. Update, Delete, and Optimistic Locking

For updates, the MyBatis statement receives the entity via `instance`. The SQL must use the current ID to identify the row:

~~~xml
<update id="update">
    UPDATE customers
    SET name = #{instance.name},
        email = #{instance.email}
    WHERE id = #{instance.id}
</update>
~~~

If the entity uses `@Version`, custom SQL updates must preserve optimistic locking semantics: comparing the old version in the WHERE clause and incrementing the version on a successful update. The `DataAccessStrategy.updateWithVersion(...)` API accepts `previousVersion` separately; `MyBatisDataAccessStrategy` also implements this operation and has a contract to throw an optimistic locking exception if no row is updated.

Do not assume `instance.version` is always the old version value the statement should compare against. How Spring Data JDBC passes `previousVersion` into `MyBatisContext` and statement mappings depends on the API version in use. Check `MyBatisContext`/the implementation for your exact version, use the previous version value passed to the operation, and ensure the SQL updates the version per contract. If the statement omits the version predicate or fails to report conflicts when zero rows are updated, optimistic locking will no longer protect data.

Delete root:

~~~xml
<delete id="delete">
    DELETE FROM customers
    WHERE id = #{id}
</delete>
~~~

Deleting child entities by property path requires separate statements in the aggregate root's namespace, such as `delete-lines`. A root DELETE statement does not automatically replace child deletion steps when the mapping requires the framework to handle them.

## 13. Partial Delegation and Fallback Strategy

An application does not have to write mappers for every operation. Spring Data JDBC's integration configuration can check for a mapped statement at each step. When a matching statement exists, MyBatis executes it. When none exists, the default strategy can handle the remaining steps if the application uses a combined access strategy.

The `MyBatisDataAccessStrategy.createCombinedAccessStrategy(...)` API is provided to create a strategy combining MyBatis and `DefaultDataAccessStrategy`. This is useful when you only want to delegate complex queries to MyBatis while still letting Spring Data JDBC generate SQL for simple CRUD.

Distinguish between two ways of instantiating it:

- Using the `MyBatisJdbcConfiguration` integration configuration as guided by Spring Data JDBC.
- Manually creating `new MyBatisDataAccessStrategy(sqlSession)`.

The `MyBatisDataAccessStrategy` Javadoc notes that an instance created directly via the constructor only handles MyBatis and does not include `DefaultDataAccessStrategy` functionality. If configuring manually and fallback is needed, use the appropriate combined strategy API for your version.

Do not assume operations fall back automatically if you manually replaced `DataAccessStrategy` with a MyBatis-only implementation. Check bean configuration and test statements that have no XML mapper.

## 14. Query Mapping and resultMap

For read operations, MyBatis is responsible for mapping result sets back into entities. Use `resultMap` when column names differ from property names or when explicit mapping is required.

Example:

~~~xml
<resultMap id="orderMap" type="com.example.domain.Order">
    <id property="id" column="order_id"/>
    <result property="status" column="order_status"/>
</resultMap>

<select id="findById" resultMap="orderMap">
    SELECT
        order_id,
        order_status
    FROM orders
    WHERE order_id = #{id}
</select>
~~~

If a query needs to build both the aggregate root and child collections, the `resultMap` may need `association`/`collection`, or Spring Data JDBC may call statements that fetch entities by property path. Pick a consistent mapping strategy so child rows are not dropped or duplicated during joins.

With large collections or complex relations, avoid assuming a single simple root SELECT will populate every property automatically. Check statements for `findAllByPath` and relation-reading conventions in your Spring Data JDBC version.

## 15. Transactions When Mixing MyBatis and Spring Data JDBC

A single use case may execute partly via MyBatis and partly via `DefaultDataAccessStrategy`. For these operations to commit/roll back together, they must share the appropriate transaction resource.

Example:

~~~java
@Service
public class CustomerService {

    private final CustomerRepository customers;
    private final AuditRepository audit;

    public CustomerService(
            CustomerRepository customers,
            AuditRepository audit
    ) {
        this.customers = customers;
        this.audit = audit;
    }

    @Transactional
    public Customer register(Customer customer) {
        Customer saved = customers.save(customer);
        audit.recordCreated(saved.getId());
        return saved;
    }
}
~~~

If MyBatis and Spring Data JDBC share the same DataSource and transaction manager, MyBatis operations through `SqlSessionTemplate` can participate in the transaction opened by the service.

Key points to remember:

- `SqlSessionTemplate` must be created from a `SqlSessionFactory` using the same DataSource.
- The transaction manager must manage that exact DataSource.
- Do not open raw `SqlSession` instances separately inside a use case.
- Do not manually commit or roll back `SqlSessionTemplate`.
- If multiple DataSources exist, explicitly designate transaction managers and resources for each persistence area.
- Do not assume two different transaction managers form a distributed transaction.

If a MyBatis operation fails midway while saving root and children, the transaction must roll back all related changes. This is why testing transactions under the real configuration is essential.

## 16. Testing CRUD Delegation and Generated Keys

Tests should go through Spring Data JDBC repositories rather than only calling MyBatis statements directly. The goal is to confirm that Spring Data JDBC finds the right statement, passes the right `MyBatisContext`, receives the generated key back, and continues processing the aggregate.

Example integration test:

~~~java
@DataJdbcTest
@Import(JdbcPersistenceConfiguration.class)
class CustomerMyBatisIntegrationTest {

    @Autowired
    CustomerRepository customers;

    @Test
    void insertsCustomerAndReceivesGeneratedId() {
        Customer saved = customers.save(
                new Customer("An", "an@example.com")
        );

        assertThat(saved.getId()).isNotNull();

        Customer loaded = customers.findById(saved.getId())
                .orElseThrow();

        assertThat(loaded.getName()).isEqualTo("An");
        assertThat(loaded.getEmail()).isEqualTo("an@example.com");
    }
}
~~~

This is an illustrative skeleton; test configuration, entity constructors, and repositories must match your application. If using a Spring Boot integration test instead of `@DataJdbcTest`, ensure XML mappers are loaded and the transaction manager uses the right DataSource.

Scenarios to test:

| Scenario | What to verify |
|---|---|
| Insert root with generated ID | `Customer.id` is populated after `save` |
| Insert root with pre-assigned ID | SQL writes the existing ID accurately |
| Insert aggregate with children | Parent ID is passed to child inserts |
| Child with generated ID | Child ID is populated properly |
| Update | Mapper uses the right instance and ID |
| Update versioned entity | Version predicate and conflict detection work |
| Delete root | Delete statement uses the right namespace |
| Delete root with children | Property path statement is invoked properly |
| Read by ID | `ResultMap` returns the right entity |
| Statement without mapper | Fallback works if using a combined strategy |
| Transaction rollback | MyBatis and Spring Data JDBC roll back together |
| Generated keys on real database | JDBC driver returns the expected key per config |

H2 is helpful for fast tests, but generated keys and SQL dialects can differ from production databases. For driver-dependent behavior, use Testcontainers or a test database matching the production engine.

## 17. Common Errors

| Symptom | Cause | Resolution |
|---|---|---|
| Mapped statement not found | Wrong namespace or statement ID | Use entity FQCN plus `Mapper` and exact operation name |
| Repository runs default SQL instead of MyBatis | Mapper XML not loaded or statement does not exist | Check `mapperLocations` and resource paths |
| `BindingException` for statement | Namespace does not match entity type | Check package and class names |
| MyBatis does not receive entity properties | Forgot `MyBatisContext` wrapper | Use `instance.property` for entity data |
| Generated ID remains NULL | `useGeneratedKeys` not enabled or driver unsupported | Check driver and key generation config |
| Generated ID not assigned to entity | `keyProperty` points to wrong property | For entities inside `MyBatisContext`, use `instance.id` |
| Insert succeeds but child insert fails | Parent ID not retrieved or wrong back-reference key | Check generated keys and `MyBatisContext.get(key)` |
| PostgreSQL does not return right key | Missing `keyColumn` or improper generated-key config | Declare key column and test the driver |
| Sequence insert fails | `selectKey` syntax incompatible with database | Use dialect-appropriate sequence expression |
| Update modifies no rows | WHERE uses wrong ID or property path | Check `instance.id` and SQL logs |
| Optimistic locking not working | Update mapper omits version | Add version predicate/increment per contract |
| Root delete rejected by foreign key | Missing child path delete statement | Declare `delete-propertyPath` or use intentional FK cascade |
| Some CRUD works, some fails | Only partial mapped statements exist and fallback is not configured | Check combined strategy |
| MyBatis operations do not roll back with repository | Inconsistent `SqlSessionTemplate`/DataSource/transaction manager | Use shared DataSource and Spring transactions |
| Tests pass but production keys fail | Driver/database differs from test environment | Test against the target database |

## 18. Implementation Workflow

1. Identify aggregates and CRUD steps to delegate to MyBatis.
2. Choose compatible Spring Data JDBC, MyBatis, and MyBatis-Spring versions.
3. Configure `SqlSessionFactory` from the application's DataSource.
4. Provide `SqlSessionTemplate` so MyBatis participates in Spring transactions.
5. Import `MyBatisJdbcConfiguration` and enable repository scanning.
6. Determine default namespaces using entity FQCN plus `Mapper`.
7. Write statements for `insert`, `update`, `delete`, and needed read operations.
8. For child entities, declare statements with the right namespace and property path.
9. Configure `useGeneratedKeys`/`keyProperty` or `selectKey` for each ID type.
10. Test that generated keys write to `instance.id` and parent keys pass to children.
11. Test updates, deletes, `resultMap`, transactions, and fallback strategy.
12. Run integration tests on a production-like database/driver.

## 19. Practice Exercises

### Exercise 1 — Configure MyBatis

Create a Spring Data JDBC configuration with `MyBatisJdbcConfiguration`, `SqlSessionFactory`, and `SqlSessionTemplate`. Verify repositories start up and XML mappers load.

### Exercise 2 — Namespace Convention

Create a `Customer` entity in package `com.example.domain`. Write an XML mapper with namespace `com.example.domain.CustomerMapper` and statement `findById`. Call `CustomerRepository.findById` to verify the statement is delegated.

### Exercise 3 — Insert and Generated Keys

Write an `insert` statement with `useGeneratedKeys=true` and `keyProperty=instance.id`. Call `save` with an entity lacking an ID and verify the returned entity has an ID.

### Exercise 4 — Sequences with selectKey

Switch the table to use a sequence. Use `selectKey BEFORE` to fetch the ID, assign it to `instance.id`, and use that ID in the INSERT.

### Exercise 5 — Aggregate with Child Collection

Create an `Order` with `List<OrderLine>`. Write insert statements for root and child. Verify the root ID is passed as the child's `order_id` foreign key.

### Exercise 6 — Update and Optimistic Locking

Write an `update` statement for an entity with `@Version`. Test normal updates and two transactions modifying the same version concurrently. Verify conflicts are detected per contract.

### Exercise 7 — Delete by Property Path

Write `delete-lines` and `deleteAll-lines` for the `Order` aggregate. Test `deleteById` and `deleteAll` with child data present.

### Exercise 8 — Partial Delegation

Provide mappers only for `findById` and `insert`, then verify whether other operations are handled by `DefaultDataAccessStrategy` in a combined strategy configuration.

### Exercise 9 — Transaction Rollback

In a transactional service, save a root via MyBatis and then trigger an error in a subsequent persistence operation. Verify all changes within the same DataSource roll back.

### Exercise 10 — Real Database

Run the generated-keys exercise on the target database using Testcontainers. Compare results with H2 and document any driver differences.

## 20. Key Takeaways

- Spring Data JDBC orchestrates aggregates; MyBatis can execute SQL for individual `DataAccessStrategy` steps.
- The repository API remains `CrudRepository`/`JdbcAggregateOperations`; services do not need to invoke mappers directly for delegated operations.
- The default namespace is the entity's fully qualified name plus the `Mapper` suffix; statement IDs denote operations like `insert`, `update`, `delete`, or `findById`.
- `MyBatisContext` wraps the entity and provides `instance`, `id`, `domainType`, `identifier`, and additional reference values.
- A single aggregate save can trigger multiple statements for root and children; do not assume one repository method maps to one SQL statement.
- When using generated keys, MyBatis must write the key into the wrapped entity's property; with this context, `keyProperty` is typically `instance.id`.
- `useGeneratedKeys` uses JDBC `getGeneratedKeys`; `selectKey` fits sequences or database-specific ID retrieval strategies.
- Generated keys differ from update counts: `insert` returns affected row count, whereas `keyProperty` receives the database-generated ID.
- Child entities must receive the parent key from `MyBatisContext` and have statements handling the proper property paths.
- Share `SqlSessionTemplate`, DataSource, and transaction manager with Spring Data JDBC so operations commit/roll back consistently.
- If instantiating `MyBatisDataAccessStrategy` manually, understand it only handles MyBatis; use a combined strategy if fallback to `DefaultDataAccessStrategy` is needed.
- Test through real repositories, verifying generated IDs, child mappings, transactions, and the JDBC driver on the target database.

## References

- [Spring Data JDBC Reference — MyBatis Integration](https://docs.spring.io/spring-data/jdbc/docs/current-SNAPSHOT/reference/html/)
- [MyBatisDataAccessStrategy API](https://docs.spring.io/spring-data/jdbc/docs/current/api/org/springframework/data/jdbc/mybatis/MyBatisDataAccessStrategy.html)
- [MyBatisContext API](https://docs.spring.io/spring-data/jdbc/docs/current/api/org/springframework/data/jdbc/mybatis/MyBatisContext.html)
- [MyBatisJdbcConfiguration API](https://docs.spring.io/spring-data/relational/reference/api/java/org/springframework/data/jdbc/repository/config/MyBatisJdbcConfiguration.html)
- [MyBatis Mapper XML — Insert, Update, Delete and Generated Keys](https://mybatis.org/mybatis-3/sqlmap-xml.html)
- [MyBatis-Spring — SqlSessionTemplate](https://mybatis.org/spring/sqlsession.html)
- [MyBatis-Spring — Transactions](https://mybatis.org/spring/transactions.html)

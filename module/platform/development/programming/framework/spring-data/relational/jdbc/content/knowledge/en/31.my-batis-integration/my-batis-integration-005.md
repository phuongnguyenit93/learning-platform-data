# Result Mapping and Relationship Handling with Custom Statements

## 1. When Are Custom MyBatis Statements Needed?

Spring Data JDBC provides a default strategy to generate SQL statements from aggregate metadata. This works well for most CRUD operations: the framework knows table names, columns, foreign keys, element positions in a List/Map, and how to convert data types.

A real-world system may require custom SQL:

- Tables designed with a legacy schema or non-default naming conventions.
- Queries requiring JOINs, CTEs, window functions, or database-specific expressions.
- An aggregate with multiple child tables needing optimized SELECT/INSERT/UPDATE statements.
- Query results that must map to DTOs or objects with nested structures.
- Fine-grained control over writing foreign keys, List element ordering, or generated values.
- Reusing SQL fragments across multiple statements.

Spring Data JDBC can delegate the execution of certain persistence steps to MyBatis. MyBatis provides mapped statements and ResultMaps to describe both the SQL and how to map a ResultSet into objects.

Crucially, this integration does not turn Spring Data JDBC into JPA, nor does it alter the aggregate model. Spring Data JDBC still decides which steps to execute when saving or loading an aggregate; MyBatis supplies the SQL and mapping for each step the application has customized.

This lesson walks through how Spring Data JDBC locates statements, the data passed via MyBatisContext, and how to map roots and relationships using custom statements. The final sections cover using association/collection for queries returning object graphs, managing transactions, and testing.

## 2. Two Layers of Responsibility When Integrating

Spring Data JDBC and MyBatis address two different concerns:

| Component | Responsibility |
| --- | --- |
| Spring Data JDBC | Managing repositories, aggregate boundaries, the sequence of persistence operations, and resolving relationships within an aggregate. |
| MyBatis | Executing mapped statements, binding parameters, mapping results via `resultType`/`resultMap`, and handling custom SQL. |

Example of a `PurchaseOrder` aggregate with order lines:

~~~text
PurchaseOrder
  id
  orderNumber
  status
  lines: List<PurchaseOrderLine>
    - sku
      quantity
      unitPrice
    - sku
      quantity
      unitPrice
~~~

When calling repository `save`, Spring Data JDBC builds a change plan for the aggregate. That plan may include:

1. Inserting or updating the `PurchaseOrder` row.
2. Deleting old child rows according to aggregate save semantics.
3. Inserting new `PurchaseOrderLine` rows along with foreign keys and List positions.

When calling `findById`, Spring Data JDBC must load the root and resolve relationship paths. MyBatis can provide a separate statement for the root and separate statements for each property path.

Therefore, do not assume that writing one large JOIN SQL query replaces the entire aggregate persistence mechanism. You need to know which statement Spring Data JDBC is requesting and what return type that statement must produce.

## 3. Configuring MyBatis for Spring Data JDBC

### 3.1. Importing MyBatisJdbcConfiguration

Spring Data Relational provides a dedicated MyBatis configuration:

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
@EnableJdbcRepositories
@Import(MyBatisJdbcConfiguration.class)
public class JdbcPersistenceConfiguration {

    @Bean
    SqlSessionFactoryBean sqlSessionFactoryBean(DataSource dataSource)
            throws Exception {

        SqlSessionFactoryBean factory = new SqlSessionFactoryBean();
        factory.setDataSource(dataSource);
        factory.setMapperLocations(
                new PathMatchingResourcePatternResolver()
                        .getResources("classpath*:mybatis/**/*.xml")
        );
        return factory;
    }

    @Bean
    SqlSessionTemplate sqlSessionTemplate(SqlSessionFactory factory) {
        return new SqlSessionTemplate(factory);
    }
}
~~~

This is a configuration skeleton. If the MyBatis Spring Boot starter has already created `SqlSessionFactory` or `SqlSessionTemplate` for your application, use the auto-configured beans and avoid duplicate declarations. What matters is that `ApplicationContext` has an appropriate `SqlSession` for `MyBatisJdbcConfiguration` to use.

`MyBatisJdbcConfiguration` replaces the default `DataAccessStrategy` with the MyBatis-integrated strategy. This configuration allows Spring Data JDBC to look up mapped statements at each persistence step. When a custom statement exists, it is used; uncustomized steps continue using the default mechanism per the integration configuration.

### 3.2. SqlSessionTemplate and Spring Transactions

Do not manually open a `DefaultSqlSession` inside repositories or services. With MyBatis-Spring, use `SqlSessionTemplate`:

- Thread-safe and shareable across beans.
- Uses the `SqlSession` bound to the current Spring transaction.
- Manages session lifecycle, including commit, rollback, and close.
- Translates MyBatis exceptions into Spring's `DataAccessException` hierarchy.

`SqlSessionTemplate` must use a `SqlSessionFactory` configured with the same `DataSource` that Spring Data JDBC uses if operations need to participate in the same transaction.

### 3.3. XML Mapper Locations

Example structure:

~~~text
src/main/resources/
  mybatis/
    orders/
      PurchaseOrderMapper.xml
      PurchaseOrderLineMapper.xml
    customers/
      CustomerMapper.xml
~~~

The `mapperLocations` property on `SqlSessionFactoryBean` loads XML files matching the pattern. Each XML mapper declares a namespace matching the domain type or the namespace strategy used by Spring Data JDBC.

## 4. Statement Naming Conventions Looked Up by Spring Data JDBC

By default, the namespace is derived from the entity's fully qualified class name plus the `Mapper` suffix. The statement name appends the operation.

For example, with class:

~~~java
package com.example.orders;

public class PurchaseOrder {
    // ...
}
~~~

Spring Data JDBC looks up the namespace:

~~~text
com.example.orders.PurchaseOrderMapper
~~~

Looked-up statements:

~~~text
com.example.orders.PurchaseOrderMapper.findById
com.example.orders.PurchaseOrderMapper.insert
com.example.orders.PurchaseOrderMapper.update
~~~

Certain operations include a property path in their name:

~~~text
com.example.orders.PurchaseOrderMapper.findAllByPath-lines
com.example.orders.PurchaseOrderMapper.delete-lines
com.example.orders.PurchaseOrderMapper.deleteAll-lines
~~~

The property path name must match the property path Spring Data JDBC uses in its mapping, not an arbitrary table name. If you change namespaces via `NamespaceStrategy`, namespaces in XML mappers must follow the new strategy.

### 4.1. Commonly Used Statements

| Statement ID | Purpose | Commonly triggered by |
| --- | --- | --- |
| insert | Inserts an entity, including referenced entities in an aggregate | save, saveAll |
| update | Updates an entity | save, saveAll |
| delete | Deletes an entity by ID | delete, deleteById |
| deleteAll | Deletes all aggregate roots of the corresponding type | deleteAll |
| delete-propertyPath | Deletes entities referenced via a property path | deleteById |
| deleteAll-propertyPath | Deletes entities referenced via a property path across roots | deleteAll |
| findById | Loads an aggregate root by ID | findById |
| findAll | Loads all aggregate roots | findAll |
| findAllById | Loads a group of aggregate roots by ID | findAllById |
| findAllByPath-propertyPath | Loads entities referenced via a property path | `find*` operations |
| findAllSorted | Loads sorted aggregate roots | findAll(Sort) |
| findAllPaged | Loads paged aggregate roots | Corresponding paging operations |
| count | Counts aggregate roots | count |

Spring Data JDBC does not require mappers for every statement. You can customize only the steps that need custom SQL and leave the remaining steps to the default strategy.

Older APIs had `findAllByProperty-propertyName`. Current documentation marks this deprecated and recommends using `findAllByPath-propertyPath`.

## 5. MyBatisContext: Parameters Passed by Spring Data JDBC to Statements

When running a mapped statement, Spring Data JDBC passes a `MyBatisContext`. This object supplies the information needed for SQL to operate on the right entity or relationship.

Key values:

| Property | Meaning |
| --- | --- |
| getInstance() | Entity being saved; for queries, this value is null because the object does not exist before running SELECT. |
| getDomainType() | Domain type of the entity the statement operates on. For relationship statements, this may be the entity type at the end of the property path. |
| getId() | ID of the entity being loaded or deleted; may be a list of IDs in multi-row operations. |
| getIdentifier() | Identifier describing the relationship path, including root ID and required keys/indexes. |
| get(key) | Retrieves the parent entity's ID by the back-reference column name determined by NamingStrategy. |

Do not assume every getter always has a value. For example, `getInstance()` is null in entity-loading queries. `MyBatisContext` is designed so a single parameter type can serve many operation types.

### 5.1. Inserting Child Entities

When inserting an entity referenced by an aggregate root, `MyBatisContext` contains the child entity instance and the parent entity's ID value. The key passed to `get(key)` is the back-reference column name determined by `NamingStrategy`.

Example where the child table has an `order_id` column:

~~~xml
<insert id="insert">
    INSERT INTO purchase_order_line (
        order_id,
        sku,
        quantity,
        unit_price
    )
    VALUES (
        #{_parameter.get('order_id')},
        #{instance.sku},
        #{instance.quantity},
        #{instance.unitPrice}
    )
</insert>
~~~

This illustrates a child entity with the `order_id` back-reference column. The key name must match the exact column name produced by `NamingStrategy` or `@MappedCollection`. For `List`/`Map`, the schema also has a column storing the index/key; the insert statement must write that value according to the relationship metadata.

### 5.2. Relationship Queries

For relationship queries, `MyBatisContext` provides `getIdentifier()`. `Identifier` can contain:

- The aggregate root's ID.
- IDs/keys of intermediate entities along the property path.
- `List` index or `Map` key.

This is why `findAllByPath` statements must handle `Identifier` instead of simply assuming a single plain root ID. If a path contains a composite ID, nested `List`/`Map`, or multiple relationship levels, bind the corresponding identifier parts properly.

## 6. Relationship Model to Understand Before Writing SQL

Spring Data JDBC treats objects directly referenced inside an aggregate as part of that aggregate. Relationships managed as part of an aggregate can be:

- One-to-one.
- One-to-many.

Many-to-one or many-to-many relationships between aggregates are typically represented by IDs or `AggregateReference`, because the two sides belong to independent aggregates.

Example:

~~~java
@Table("purchase_order")
public class PurchaseOrder {

    @Id
    private Long id;

    private String orderNumber;
    private OrderStatus status;

    @MappedCollection(idColumn = "order_id", keyColumn = "line_no")
    private List<PurchaseOrderLine> lines;

    // Constructor, getters, domain methods...
}
~~~

Child entity:

~~~java
public class PurchaseOrderLine {

    private String sku;
    private int quantity;
    private BigDecimal unitPrice;

    // Constructor, getters...
}
~~~

The corresponding schema might be:

~~~sql
CREATE TABLE purchase_order (
    id BIGINT PRIMARY KEY,
    order_number VARCHAR(40) NOT NULL,
    status VARCHAR(20) NOT NULL
);

CREATE TABLE purchase_order_line (
    order_id BIGINT NOT NULL,
    line_no INTEGER NOT NULL,
    sku VARCHAR(40) NOT NULL,
    quantity INTEGER NOT NULL,
    unit_price DECIMAL(19, 2) NOT NULL,
    PRIMARY KEY (order_id, line_no),
    FOREIGN KEY (order_id) REFERENCES purchase_order(id)
);
~~~

In this example:

- `order_id` is the back-reference from an order line to the aggregate root.
- `line_no` stores the element's position in the `List`.
- Spring Data JDBC uses `@MappedCollection` to know the names of those two columns.
- MyBatis SQL must write and read those corresponding columns accurately.

If custom names are not declared, Spring Data JDBC uses `NamingStrategy` to generate back-reference and key column names. When writing custom SQL, verify the actual naming strategy instead of guessing names.

## 7. Mapping the Aggregate Root with resultMap

`ResultMap` describes how MyBatis converts a `ResultSet` row into an object. For Spring Data JDBC's `findById` statement, `resultMap` typically maps the aggregate root's data.

Example:

~~~xml
<mapper namespace="com.example.orders.PurchaseOrderMapper">

    <resultMap id="purchaseOrderRow"
               type="com.example.orders.PurchaseOrder">
        <id property="id" column="id"/>
        <result property="orderNumber" column="order_number"/>
        <result property="status" column="status"/>
    </resultMap>

    <select id="findById"
            parameterType="org.springframework.data.jdbc.mybatis.MyBatisContext"
            resultMap="purchaseOrderRow">
        SELECT
            id,
            order_number,
            status
        FROM purchase_order
        WHERE id = #{id}
    </select>

</mapper>
~~~

The statement ID is `findById` in the `PurchaseOrderMapper` namespace. The `id` parameter is taken from `MyBatisContext.getId()`.

### 7.1. Why Declare id in resultMap?

The `id` element marks the object's identity column. When a result has a JOIN and repeats root information across multiple rows, MyBatis needs to know which rows belong to the same object. Declaring `id` explicitly helps MyBatis recognize object identity and handle nested results better.

### 7.2. Mapping Constructors or Immutable Objects

If a domain type uses a constructor or record, MyBatis can use the `constructor` section of `resultMap`:

~~~xml
<resultMap id="customerRow"
           type="com.example.customers.Customer">
    <constructor>
        <idArg name="id" column="id" javaType="long"/>
        <arg name="name" column="display_name" javaType="string"/>
        <arg name="email" column="email" javaType="string"/>
    </constructor>
</resultMap>
~~~

Parameter names and constructor order must match the actual Java type and MyBatis version in use. If using a mutable JavaBean, you can use property mapping as in the `PurchaseOrder` example.

## 8. Loading Collections via findAllByPath

In Spring Data JDBC integration, the statement that loads relationships is named:

~~~text
<AggregateRootFullyQualifiedName>Mapper.findAllByPath-<propertyPath>
~~~

For the `lines` property of `PurchaseOrder`:

~~~text
com.example.orders.PurchaseOrderMapper.findAllByPath-lines
~~~

This statement returns `PurchaseOrderLine` entities. Spring Data JDBC uses them to resolve the property path and assemble the aggregate.

Example mapper:

~~~xml
<mapper namespace="com.example.orders.PurchaseOrderMapper">

    <resultMap id="purchaseOrderLineRow"
               type="com.example.orders.PurchaseOrderLine">
        <result property="sku" column="sku"/>
        <result property="quantity" column="quantity"/>
        <result property="unitPrice" column="unit_price"/>
    </resultMap>

    <select id="findAllByPath-lines"
            parameterType="org.springframework.data.jdbc.mybatis.MyBatisContext"
            resultMap="purchaseOrderLineRow">
        SELECT
            sku,
            quantity,
            unit_price
        FROM purchase_order_line
        WHERE order_id = #{identifier.parts[0].value}
        ORDER BY line_no
    </select>

</mapper>
~~~

In this simple example, `Identifier` contains only one part—the aggregate root's ID. The expression `parts[0].value` illustrates reading the value from the first part of `Identifier`; do not treat index `0` as a universal rule for every aggregate. With composite IDs, multi-level property paths, or nested `List`/`Map` relationships, `Identifier` has multiple parts. Determine the exact part according to the actual column name and relationship path.

### 8.1. Why Is ORDER BY line_no Important?

A `List` preserves element order. The `keyColumn` in `@MappedCollection` holds the element's position. When loading the collection, the statement should return rows ordered by key/index so the result reflects the saved order.

For a `Set`, ordering does not carry the same meaning. For a `Map`, the key column stores the `Map` key rather than a sequential index.

### 8.2. Nested Property Paths

Suppose an aggregate has:

~~~text
PurchaseOrder
  shipments: List<Shipment>
    packages: List<Package>
~~~

A query resolving a deep property path may require statements:

~~~text
PurchaseOrderMapper.findAllByPath-shipments
PurchaseOrderMapper.findAllByPath-shipments.packages
~~~

The second statement receives an `Identifier` containing information about the root and the required intermediate element. The SQL must use those parts to restrict to the exact packages belonging to the shipment of the right purchase order. Do not filter only by a single root ID when the path has multiple levels and intermediate elements.

## 9. Inserting and Updating Referenced Entities

When Spring Data JDBC saves an aggregate, child entities are also inserted/updated according to aggregate semantics. MyBatis can provide statements for each entity type.

Example namespace for a child entity:

~~~xml
<mapper namespace="com.example.orders.PurchaseOrderLineMapper">

    <insert id="insert">
        INSERT INTO purchase_order_line (
            order_id,
            sku,
            quantity,
            unit_price
        )
        VALUES (
            #{_parameter.get('order_id')},
            #{instance.sku},
            #{instance.quantity},
            #{instance.unitPrice}
        )
    </insert>

</mapper>
~~~

Spring Data JDBC passes the entity instance being inserted and the parent ID via `MyBatisContext`. In the example, `get('order_id')` fetches the back-reference value per the naming strategy.

If the entity has its own ID, the insert statement must handle the ID according to the schema. If the database generates the ID, configure generated keys or a `selectKey` mechanism compatible with the database and how Spring Data JDBC receives IDs. If the child uses a composite key of parent ID and list index, the SQL must write all of those components.

### 9.1. Updates and Versioning

The update statement uses the current instance:

~~~xml
<update id="update">
    UPDATE purchase_order
    SET order_number = #{instance.orderNumber},
        status = #{instance.status}
    WHERE id = #{instance.id}
</update>
~~~

If the aggregate uses `@Version` or requires optimistic locking, custom SQL must preserve the expected version predicate and version increment semantics. Do not omit the version column just because the custom UPDATE statement executes successfully.

### 9.2. Deleting Relationships

When deleting an aggregate, child rows belonging to the aggregate must be handled in the proper order and consistent with foreign key constraints. Delete statements by property path can be named:

~~~text
PurchaseOrderMapper.delete-lines
PurchaseOrderMapper.deleteAll-lines
~~~

`delete-lines` typically deletes child rows belonging to a specific root. `deleteAll-lines` handles child rows within the scope of a `deleteAll` operation. The SQL must honor foreign key conditions and avoid accidentally deleting data belonging to other aggregates.

## 10. MyBatis association and collection

MyBatis can map a `ResultSet` into an object graph using these elements:

- `resultMap`: defines how columns map to objects.
- `association`: maps a one-to-one relationship.
- `collection`: maps a one-to-many relationship.
- `constructor`: instantiates objects via constructors.
- `id`/`result`: maps identifiers and properties.

These techniques are very useful for custom queries returning DTOs or mapper-managed object graphs.

### 10.1. Association for One-to-One Relationships

Example of a customer report including address:

~~~xml
<resultMap id="customerWithAddress"
           type="com.example.report.CustomerView">
    <id property="id" column="customer_id"/>
    <result property="name" column="customer_name"/>

    <association property="address"
                 javaType="com.example.report.AddressView">
        <id property="id" column="address_id"/>
        <result property="city" column="address_city"/>
        <result property="street" column="address_street"/>
    </association>
</resultMap>
~~~

SQL:

~~~xml
<select id="findCustomerView" resultMap="customerWithAddress">
    SELECT
        c.id AS customer_id,
        c.name AS customer_name,
        a.id AS address_id,
        a.city AS address_city,
        a.street AS address_street
    FROM customers c
    LEFT JOIN customer_address a ON a.customer_id = c.id
    WHERE c.id = #{id}
</select>
~~~

Column aliases prevent collisions between column names like `id` and `name` across tables.

### 10.2. Collection for One-to-Many Relationships

Example of a report view containing a list of order lines:

~~~xml
<resultMap id="orderReport"
           type="com.example.report.OrderReport">
    <id property="id" column="order_id"/>
    <result property="orderNumber" column="order_number"/>

    <collection property="lines"
                ofType="com.example.report.OrderLineView">
        <id property="id" column="line_id"/>
        <result property="sku" column="line_sku"/>
        <result property="quantity" column="line_quantity"/>
    </collection>
</resultMap>
~~~

SQL:

~~~xml
<select id="findOrderReport" resultMap="orderReport">
    SELECT
        o.id AS order_id,
        o.order_number,
        l.id AS line_id,
        l.sku AS line_sku,
        l.quantity AS line_quantity
    FROM purchase_order o
    LEFT JOIN purchase_order_line l ON l.order_id = o.id
    WHERE o.id = #{id}
    ORDER BY l.line_no
</select>
~~~

MyBatis collapses multiple `ResultSet` rows into a single `OrderReport` with its `lines` collection. The `id` tags on root and child help identify repeated rows belonging to the same object.

### 10.3. Nested Select vs. Nested Result

MyBatis offers two common ways to load `association`/`collection`:

| Approach | How it works | Pros | Risks |
| --- | --- | --- | --- |
| Nested select | Main statement invokes another statement to load the relation | Separate SQL per relation, easy to modularize | Can cause N+1 queries when loading many roots |
| Nested result | JOINs related data in one ResultSet and folds into objects | Can reduce round trips | Rows repeat; requires exact aliases/id mappings and may increase transferred data volume |

Nested select:

~~~xml
<resultMap id="orderWithLines"
           type="com.example.report.OrderReport">
    <id property="id" column="id"/>
    <result property="orderNumber" column="order_number"/>
    <collection property="lines"
                column="id"
                ofType="com.example.report.OrderLineView"
                select="findLinesByOrderId"/>
</resultMap>

<select id="findOrder" resultMap="orderWithLines">
    SELECT id, order_number
    FROM purchase_order
    WHERE id = #{id}
</select>

<select id="findLinesByOrderId" resultType="com.example.report.OrderLineView">
    SELECT sku, quantity
    FROM purchase_order_line
    WHERE order_id = #{id}
</select>
~~~

Nested result uses a JOIN and `collection` as in the earlier example. Choosing between them requires measuring the number of roots, children, round trips, and ResultSet size.

## 11. Do Not Confuse MyBatis Object Graphs with Aggregate Path Resolution

This is an architectural distinction to keep clear.

MyBatis on its own can use `association`/`collection` to build an object graph from a single query. However, Spring Data JDBC integration also has its own `RelationResolver` mechanism for loading entities within an aggregate by property path.

When customizing Spring Data JDBC CRUD repositories:

- `findById` loads the aggregate root using the `findById` statement.
- Relationships are resolved via `findAllByPath-propertyPath` statements.
- The path statement's result must map to the exact entity type at the end of the path.
- `Identifier` provides the root ID and required keys/indexes.
- Spring Data JDBC assembles the relationship elements onto the aggregate.

Therefore, if you want to change how Spring Data JDBC loads a collection inside an aggregate, implement `findAllByPath-...` per the integration contract. Do not assume that a collection populated via a MyBatis nested result map in `findById` automatically replaces all of Spring Data JDBC's relation resolution steps.

Conversely, if you are building a separate query returning a report DTO or read model, MyBatis `association`/`collection` is the right tool to map an entire object graph in a single statement.

Keep these two goals separate:

- Aggregate persistence: Spring Data JDBC orchestrates aggregates and property paths; MyBatis supplies SQL for each step.
- Read model/reporting: MyBatis can orchestrate the entire JOIN and object graph using its own `resultMap`.

## 12. AggregateReference and Inter-Aggregate Relationships

Spring Data JDBC does not treat every object reference as an arbitrarily cascadeable relationship. Entities referenced as part of an aggregate must obey aggregate boundaries.

For example, `PurchaseOrder` can contain `PurchaseOrderLine` items. However, the `Customer` referenced by an order is usually an independent aggregate. In that case, store a customer ID or `AggregateReference` rather than embedding a `Customer` object that Spring Data JDBC would treat as a child.

~~~java
@Table("purchase_order")
public class PurchaseOrder {

    @Id
    private Long id;

    private AggregateReference<Customer, Long> customer;
}
~~~

In MyBatis SQL, the reference field is stored as a simple foreign key value. Do not create a `findAllByPath-customer` statement intending to cascade-load another aggregate as if `Customer` were a child of `PurchaseOrder`.

If a use case needs customer information alongside the order, you can:

- Load `Customer` through a separate `CustomerRepository`.
- Use a reporting query with a JOIN mapped to a DTO.
- Coordinate the two aggregates in an application service.

This keeps the consistency boundaries of each aggregate clear.

## 13. SQL Parameters and Dynamic SQL

MyBatis supports dynamic SQL using tags such as:

- `if`
- `choose`/`when`/`otherwise`
- `where`
- `set`
- `foreach`
- `trim`

Example query filtering by optional status:

~~~xml
<select id="findOrders" resultMap="purchaseOrderRow">
    SELECT id, order_number, status
    FROM purchase_order
    <where>
        <if test="status != null">
            status = #{status}
        </if>
        <if test="orderNumber != null">
            AND order_number = #{orderNumber}
        </if>
    </where>
</select>
~~~

### 13.1. Use #{} for Values

`#{}` creates a `PreparedStatement` parameter and binds the value. This is the default choice for request data, IDs, statuses, and filter values.

Do not concatenate user data directly into SQL. If you need dynamic column names or `ORDER BY` clauses, map inputs to a whitelisted set of identifiers in code. Direct SQL string substitution can open SQL injection vulnerabilities because identifiers cannot be bound like ordinary parameter values.

### 13.2. Collection Parameters with foreach

Example finding multiple orders by a list of IDs:

~~~xml
<select id="findByIds" resultMap="purchaseOrderRow">
    SELECT id, order_number, status
    FROM purchase_order
    WHERE id IN
    <foreach collection="ids"
             item="id"
             open="("
             separator=","
             close=")">
        #{id}
    </foreach>
</select>
~~~

If a statement is invoked with `MyBatisContext`, collection names and parameter access paths must match the actual context structure. Do not copy standalone List parameter examples verbatim into statements receiving `MyBatisContext` without adjusting the property paths.

## 14. resultType or resultMap?

These two declarations serve different purposes:

| Approach | Use when |
| --- | --- |
| resultType | Simple results where column names can map directly to properties/constructors |
| resultMap | Complex aliases, constructor mapping, association, collection, discriminator, or multi-table mapping |

Use only one of the two on the same SELECT statement. If a query has a JOIN with multiple columns sharing names like `id`, `name`, `status`, use aliases and an explicit `resultMap`.

### 14.1. Beware of Auto-Mapping with JOINs

MyBatis has auto-mapping modes `NONE`, `PARTIAL`, and `FULL`. `FULL` can cause bugs when joining multiple tables that have overlapping column names. For instance, a child's `id` could accidentally receive the parent's `id` if aliases and mappings are not controlled.

For multi-table queries:

- Alias all columns that could collide.
- Declare `id` on both root and child.
- Use `columnPrefix` when reusing nested `resultMap` definitions.
- Disable `autoMapping` on a `resultMap` when you want explicit mapping.
- Only use `FULL` when you understand every column in the `ResultSet`.

## 15. Customizing Specific Statements While Keeping Defaults for the Rest

You do not need to move all operations to MyBatis at once.

Example:

| Operation | Handling |
| --- | --- |
| PurchaseOrder.findById | MyBatis because custom root SQL is needed |
| PurchaseOrder.findAllByPath-lines | MyBatis because the line table uses custom column names |
| PurchaseOrder.insert | Default Spring Data JDBC |
| PurchaseOrder.update | Default Spring Data JDBC |
| PurchaseOrder.delete | Default Spring Data JDBC |

Spring Data JDBC checks for mapped statements step by step. When a matching statement is found, it is used. Uncustomized steps continue going through the default strategy in the integrated configuration.

Lower-level API note: instantiating `new MyBatisDataAccessStrategy(sqlSession)` directly only provides the MyBatis strategy and does not automatically include `DefaultDataAccessStrategy` behavior. If constructing `DataAccessStrategy` manually instead of importing `MyBatisJdbcConfiguration`, use the `createCombinedAccessStrategy(...)` factory when you need fallback to the default strategy.

## 16. Transactions When Combining Spring Data JDBC and MyBatis

A single use case can call a Spring Data JDBC repository while also executing a MyBatis mapped statement. If both share the same DataSource and MyBatis-Spring manages `SqlSession` via `SqlSessionTemplate`, the statements can participate in the same Spring transaction.

Example:

~~~java
@Service
public class PurchaseOrderService {

    private final PurchaseOrderRepository orders;
    private final SqlSession sqlSession;

    public PurchaseOrderService(
            PurchaseOrderRepository orders,
            SqlSession sqlSession
    ) {
        this.orders = orders;
        this.sqlSession = sqlSession;
    }

    @Transactional
    public Long create(PurchaseOrder order) {
        PurchaseOrder saved = orders.save(order);

        sqlSession.insert(
                "com.example.audit.AuditMapper.insert",
                Map.of(
                        "aggregateId", saved.getId(),
                        "action", "ORDER_CREATED"
                )
        );

        return saved.getId();
    }
}
~~~

This illustrates coordinating a repository operation and an independent MyBatis statement. If both use the same transaction manager/DataSource, a failure in the audit insert can roll back saving the order.

Do not call `commit()` or `rollback()` manually on `SqlSessionTemplate` inside a Spring-managed transaction. Let the transaction interceptor and `SqlSessionTemplate` coordinate the transaction lifecycle.

If MyBatis and Spring Data JDBC use two different DataSources, a standard `@Transactional` does not automatically create a distributed transaction. Design a dedicated transaction manager or coordination mechanism.

## 17. Checkpoints When Customizing Aggregate Writes

When replacing `insert`/`update`/`delete` statements, the SQL must preserve the rules Spring Data JDBC expects:

1. **Back-reference:** child rows must write the proper foreign key pointing to the parent.
2. **List/Map key:** write the proper index/key column if required by the mapping.
3. **Generated ID:** return or assign IDs via the mechanism expected by `DataAccessStrategy`.
4. **Update semantics:** do not lose data or update the wrong rows.
5. **Delete order:** handle child rows before deleting the parent if required by foreign keys.
6. **Version:** preserve optimistic locking predicates and increment the version when needed.
7. **Affected rows:** check affected row counts if business logic depends on update/delete succeeding.
8. **Transaction:** statements belonging to a single aggregate save must participate in the same transaction.

If custom SQL omits a step in the sequence of operations, bugs may surface only when saving an aggregate with an empty collection, replacing a collection, or deleting an aggregate with multiple child levels. Test all of these cases thoroughly.

## 18. Performance When Mapping Relationships

Relationship mapping is not merely a correctness issue; how data is loaded directly affects SQL query count and data transfer volume.

### 18.1. N+1 Queries

Nested selects can trigger one query for the root plus one query per relation or per root. With large lists, round trips grow rapidly.

If the query is a report/read model, consider a JOIN and nested result map to fetch data in one query. If using an aggregate repository, weigh the number of path statements executed and load the aggregate only when the use case genuinely needs the full aggregate.

### 18.2. Duplicate JOIN Data

Joining a root with multiple collections can multiply row counts. For example, an order with 5 lines and 3 payments; joining both collections can produce up to 15 rows for a single order. MyBatis needs `id` mapping to deduplicate, while the database and network still process the expanded row count.

You can split queries by collection or use appropriate projections instead of constructing one huge JOIN.

### 18.3. Indexes and Ordering

For relationship statements, indexes are commonly needed on foreign key and key columns:

~~~sql
CREATE INDEX idx_order_line_order_id
    ON purchase_order_line(order_id);
~~~

If queries sort by `line_no`:

~~~sql
CREATE INDEX idx_order_line_order_line_no
    ON purchase_order_line(order_id, line_no);
~~~

Index creation syntax and online indexing capabilities depend on the database. Measure execution plans against realistic data before deciding.

## 19. Testing Custom Statements

Do not merely test that a statement runs. Verify that Spring Data JDBC invokes the statement at the right time and returns the right object graph.

### 19.1. Testing Root Loading

- Call `repository.findById`.
- Confirm the `findById` statement is executed by MyBatis.
- Check root ID, enums, nullable fields, and data types.

### 19.2. Testing Relationships

- Create an aggregate with multiple children.
- Call `findById`.
- Confirm the `findAllByPath-lines` statement is located.
- Check foreign key filtering.
- Check `List` ordering by the key column.
- Check empty collections and aggregates without children.

### 19.3. Testing Save

- Insert a new aggregate with children.
- Update the root.
- Modify a child.
- Remove a child from the collection.
- Clear the entire collection.
- Delete the aggregate root.

Verify parent ID, key/index, and foreign keys in the database after each operation.

### 19.4. Testing Fallback

Customize only one statement and leave the remaining statements on defaults. Verify the integrated configuration continues running properly. This is especially important when using a combined strategy or `MyBatisJdbcConfiguration`.

### 19.5. Testing Transactions

In a `@Transactional` service:

1. Save an aggregate.
2. Execute another mapped statement.
3. Intentionally fail the final step.
4. Verify all changes in the transaction roll back together.

Use a real database or Testcontainers with the same engine type as production when statements depend on SQL syntax, generated keys, or locking behavior.

## 20. Common Errors

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Spring Data JDBC cannot find statement | Namespace or statement ID does not follow convention | Check fully qualified domain type, `Mapper` suffix, and operation ID. |
| Root loads but collection is empty | Missing `findAllByPath-propertyPath` or WHERE uses wrong back-reference | Check path statement, `Identifier`, and FK column name. |
| Child attached to wrong parent | SQL does not bind parent ID from `MyBatisContext` properly | Use `get(key)` or `Identifier` matching the path; confirm `NamingStrategy`. |
| List ordering changes | Missing write or `ORDER BY` on key/index column | Use `@MappedCollection(keyColumn=...)` and sort by that column. |
| JOIN creates duplicate children | `ResultMap` missing `id` mapping or unclear column aliases | Declare `id` for root/child and alias colliding columns. |
| Constructor mapping fails | Constructor parameters, names, or types mismatch | Check `resultMap` constructor against actual Java types. |
| Custom SQL inserts root but children are not saved | Only root statement created, omitting required child or path statements | Identify all `DbAction`/statements emitted by aggregate save. |
| Deleting root fails with foreign key error | Delete statement does not handle children in proper order | Add `delete-propertyPath` or configure appropriate cascade/schema. |
| Part of operation commits even when use case fails | MyBatis session not participating in Spring transaction or different DataSource | Use `SqlSessionTemplate` and shared DataSource/transaction manager. |
| Lost default fallback | Manually instantiated plain `MyBatisDataAccessStrategy` | Use `MyBatisJdbcConfiguration` or `createCombinedAccessStrategy`. |
| Report query slow due to N+1 | Nested select runs repeatedly for many roots | Consider JOIN/nested result, batching, or appropriate projections. |

## 21. Process for Designing a Custom Statement

When an operation needs custom SQL, follow this sequence:

1. **Identify the operation:** are you customizing `insert`, `update`, `delete`, `findById`, or a relation path?
2. **Identify the domain type:** is the namespace based on the root or a child entity?
3. **Determine the statement ID:** does the operation include a property path?
4. **Inspect MyBatisContext:** do you need `instance`, `id`, `domainType`, `identifier`, or parent back-reference?
5. **Check the schema:** table names, FKs, list indexes, map keys, and generated IDs.
6. **Write resultMap:** explicitly specify IDs, properties, constructors, associations, and collections.
7. **Preserve aggregate boundaries:** which relations belong to the aggregate and which are merely `AggregateReference`?
8. **Verify fallback:** do uncustomized operations still use the default strategy?
9. **Test transactions:** do all involved statements commit/roll back together?
10. **Measure performance:** check query counts, execution plans, row counts, and payload size.

## 22. Self-Practice Exercises

**Exercise 1 — Configure MyBatis.** Import `MyBatisJdbcConfiguration`, configure `SqlSessionFactoryBean` and `SqlSessionTemplate`. Verify Spring Data JDBC can still create repositories.

**Exercise 2 — Statement findById.** Write an XML mapper for `PurchaseOrderMapper.findById`, use a `resultMap` to map the root, and call `repository.findById`.

**Exercise 3 — Relationship Statement.** Write `findAllByPath-lines` to load `PurchaseOrderLine` using `Identifier`. Verify FK filtering and `List` ordering.

**Exercise 4 — Insert Child.** Write `PurchaseOrderLineMapper.insert`, using `MyBatisContext.instance` and parent back-reference from `get(key)`. Verify foreign keys in the database.

**Exercise 5 — Delete Property Path.** Customize `delete-lines` and verify deleting an aggregate with multiple order lines does not violate foreign keys.

**Exercise 6 — Association and Collection.** Write a reporting query using JOIN, `association`, and `collection` to return an `OrderReport` DTO. Compare with how Spring Data JDBC loads aggregates via `findAllByPath`.

**Exercise 7 — Nested Select vs. Nested Result.** Implement the same report both ways and measure query counts and ResultSet row counts.

**Exercise 8 — Composite Path.** Create nested `List`/`Map` relationships and inspect how `Identifier` holds the required IDs, keys, and indexes. Write a statement filtering by the exact parent element.

**Exercise 9 — Fallback.** Customize only `findById`, leaving `insert`/`update`/`delete` on defaults. Confirm the remaining operations still work.

**Exercise 10 — Transactions.** Save an aggregate and write an audit record via MyBatis in the same service transaction. Force the audit statement to fail and confirm the aggregate rolls back.

## 23. Key Takeaways

Spring Data JDBC can delegate individual CRUD/query steps to MyBatis. Statements are looked up under a default namespace consisting of the fully qualified domain class plus `Mapper`, followed by the operation ID. For relationships, `findAllByPath-propertyPath` statements receive a `MyBatisContext` with an `Identifier` containing the root ID plus required keys/indexes to load the exact entities at the end of the path.

MyBatis `ResultMap` maps columns into objects; `association` describes one-to-one relationships and `collection` describes one-to-many relationships. Nested selects are easy to separate but can cause N+1 queries; nested results use JOINs to reduce round trips but require accurate aliases and `id` mappings. In Spring Data JDBC aggregate repositories, follow the property-path resolution mechanism; use `association`/`collection` to build independent object graphs for read models when appropriate.

When customizing `insert`/`update`/`delete`, SQL must preserve back-references, list/map keys, generated IDs, versions, and deletion order. Use `SqlSessionTemplate` with the same DataSource so MyBatis participates in Spring transactions. You can customize individual statements and leave the rest to the default strategy; if configuring `DataAccessStrategy` manually, use a combined strategy when you still want default fallback.

### References

- [Spring Data Relational – MyBatis Integration](https://docs.spring.io/spring-data/relational/reference/jdbc/mybatis.html)
- [Spring Data Relational – MyBatisContext API](https://docs.spring.io/spring-data/relational/reference/api/java/org/springframework/data/jdbc/mybatis/MyBatisContext.html)
- [Spring Data Relational – MyBatisDataAccessStrategy API](https://docs.spring.io/spring-data/relational/reference/api/java/org/springframework/data/jdbc/mybatis/MyBatisDataAccessStrategy.html)
- [Spring Data Relational – Mapping and Relationships](https://docs.spring.io/spring-data/relational/reference/jdbc/mapping.html)
- [MyBatis – Mapper XML Files and Result Maps](https://mybatis.org/mybatis-3/sqlmap-xml.html)
- [MyBatis-Spring – Using SqlSessionTemplate](https://mybatis.org/spring/sqlsession.html)

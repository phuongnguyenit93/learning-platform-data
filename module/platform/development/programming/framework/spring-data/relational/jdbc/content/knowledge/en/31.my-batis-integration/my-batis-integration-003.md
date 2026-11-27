# Namespace Conventions, Statements, and MyBatisContext

In **Spring Data Relational JDBC**, MyBatis can replace Spring Data JDBC's default SQL execution for persistence operations. This is useful when an application needs control over SQL statements, generated-key retrieval, result mapping, or how child tables within an aggregate are queried.

For Spring Data JDBC to locate the right MyBatis statement, the mapper must follow a specific naming convention. **The namespace is derived from the entity type, the statement ID is named after the operation, and `MyBatisContext` is the parameter object that Spring Data JDBC passes to the mapped statement.** If the namespace or statement ID is incorrect, Spring Data JDBC will not find the custom statement and may fall back to the default SQL strategy instead.

This lesson explains how to name namespaces, the list of statements Spring Data JDBC looks up, the data available in `MyBatisContext`, how to configure XML mappers, and how to test the contract between repositories, aggregate mappings, and MyBatis.

## 1. Where Does MyBatis Integrate with Spring Data JDBC?

Spring Data JDBC uses `DataAccessStrategy` to perform read/write operations on each entity in an aggregate. By default, `DefaultDataAccessStrategy` generates SQL from Spring Data Relational's mapping metadata.

When MyBatis is integrated, `MyBatisDataAccessStrategy` can take responsibility for executing certain statements. Spring Data JDBC looks up the mapped statement in `SqlSessionFactory`. If a statement with the exact name is found, that MyBatis statement is used along with the result mapping configured in MyBatis. If not found, the combined strategy can continue using `DefaultDataAccessStrategy`.

Overview flow:

~~~text
CrudRepository / JdbcAggregateTemplate
                |
                v
        Spring Data JDBC
                |
                v
        DataAccessStrategy
                |
                v
     Look up mapped statement in MyBatis
                |
         +------+------+
         |             |
  Statement found   Not found
         |             |
         v             v
      MyBatis SQL   DefaultDataAccessStrategy
         |             |
         +------+------+
                |
                v
             Database
~~~

This allows step-by-step customization. For instance, an application can let Spring Data JDBC handle `insert` and `update` by default while providing a custom MyBatis statement for `findById`. When a custom statement exists, it is responsible for the SQL and mapping of that operation.

### 1.1. MyBatis Mapper Conventions Do Not Cover Arbitrary Mapper Methods

The statement names in this lesson form the contract between `MyBatisDataAccessStrategy` and Spring Data JDBC's persistence operations. They do not automatically map every arbitrary method declared in a repository interface or every method in a MyBatis mapper interface.

If an application needs a custom business query, such as `findOrdersForDashboard`, you can use a dedicated MyBatis mapper interface/statement and call it from a custom repository fragment or service. To replace `CrudRepository.save`, `findById`, `deleteById`, and so on, you must follow the statement IDs that Spring Data JDBC looks up.

## 2. Default Namespace Convention

By default, the MyBatis namespace is constructed from **the entity class's fully qualified class name plus the `Mapper` suffix**.

Example entity:

~~~java
package com.example.orders;

public class PurchaseOrder {
    // ...
}
~~~

Default namespace:

~~~text
com.example.orders.PurchaseOrderMapper
~~~

The `findById` statement in that namespace has the full name:

~~~text
com.example.orders.PurchaseOrderMapper.findById
~~~

In the XML mapper:

~~~xml
<mapper namespace="com.example.orders.PurchaseOrderMapper">
    <select id="findById" resultMap="purchaseOrderMap">
        SELECT id, order_number, status
        FROM purchase_order
        WHERE id = #{id}
    </select>
</mapper>
~~~

MyBatis combines `namespace` with `id` to form the statement key. Therefore, the namespace and statement ID must match Spring Data JDBC's convention exactly.

### 2.1. Using the Fully Qualified Class Name

The default namespace includes the package:

| Entity class | Namespace |
| --- | --- |
| `com.example.orders.PurchaseOrder` | `com.example.orders.PurchaseOrderMapper` |
| `com.example.catalog.Product` | `com.example.catalog.ProductMapper` |
| `com.example.customer.Customer` | `com.example.customer.CustomerMapper` |

Do not shorten the namespace to `PurchaseOrderMapper` if the application uses the default strategy. Two entities in different packages can share the same class name; the fully qualified name distinguishes them.

### 2.2. Namespace for Child Entities

For `insert` or `update` operations on a child entity belonging to an aggregate, the default namespace is based on the type of the entity being processed. Example:

~~~java
package com.example.orders;

public class OrderLine {
    // ...
}
~~~

Child entity namespace:

~~~text
com.example.orders.OrderLineMapper
~~~

Thus, you can have:

- `PurchaseOrderMapper.insert` for the root `PurchaseOrder`.
- `OrderLineMapper.insert` for the child entity `OrderLine`.

Operations by property path are a different case: the statement prefix uses the aggregate root's type, followed by the path to be processed. The following section explains this rule clearly.

### 2.3. NamespaceStrategy

Spring Data JDBC has `NamespaceStrategy` to determine the namespace from a domain type. `NamespaceStrategy.DEFAULT_INSTANCE` uses the rule of entity class plus the `Mapper` suffix.

In advanced configurations, `MyBatisDataAccessStrategy` supports setting a different `NamespaceStrategy`. If you change the namespace rule, all XML mappers must use the new namespace names. This configuration depends on the Spring Data Relational version; check the API of the release in use before customizing it.

Do not change the namespace strategy just to shorten XML without a clear need. The default convention is easy to deduce, easy to search, and consistent across modules.

## 3. Statement ID Convention

The statement ID is the part after the dot in the full name of a mapped statement. With the namespace `com.example.orders.PurchaseOrderMapper`, Spring Data JDBC looks for IDs such as:

~~~text
insert
update
delete
deleteAll
findById
findAll
findAllById
findAllByPath-lines
findAllSorted
findAllPaged
count
~~~

Operations with a property path use a suffix representing the path inside the aggregate, such as `delete-lines` or `findAllByPath-lines`.

### 3.1. Statement Convention Table

The table below describes the statements used by Spring Data JDBC in MyBatis integration. A single repository operation can trigger multiple statements because reading/writing an aggregate may involve the root and referenced entities.

| Statement ID | Purpose | Repository operations that may trigger it |
| --- | --- | --- |
| `insert` | Inserts an entity; applies to root and entities referenced by root | `save`, `saveAll` |
| `update` | Updates an entity; applies to root and entities referenced by root | `save`, `saveAll` |
| `delete` | Deletes an entity by ID | `delete`, `deleteById` |
| `deleteAll` | Deletes all aggregate roots of the type used as the namespace prefix | `deleteAll` |
| `delete-<propertyPath>` | Deletes entities referenced by root via a property path for a root ID | `deleteById` |
| `deleteAll-<propertyPath>` | Deletes entities referenced via a property path from all aggregate roots | `deleteAll` |
| `findById` | Reads an aggregate root by ID | `findById` |
| `findAll` | Reads all aggregate roots | `findAll` |
| `findAllById` | Reads aggregate roots by a list of IDs | `findAllById` |
| `findAllByPath-<propertyPath>` | Reads entities referenced via a property path | `find*` operations when resolving relations |
| `findAllSorted` | Reads sorted aggregate roots | `findAll(Sort)` |
| `findAllPaged` | Reads a page of aggregate roots, optionally sorted | `findAll(Pageable)` |
| `count` | Counts aggregate roots of the type used as the namespace prefix | `count` |

`findAllByProperty-<propertyName>` is an older deprecated convention. For new mappers, use `findAllByPath-<propertyPath>`.

### 3.2. Property Path Names in Statement IDs

Suppose an aggregate root:

~~~java
@Table("purchase_order")
public class PurchaseOrder {

    @Id
    private Long id;

    private String orderNumber;

    @MappedCollection(idColumn = "purchase_order_id")
    private Set<OrderLine> lines;
}
~~~

The property path from root to child is `lines`. Some corresponding statements:

~~~text
com.example.orders.PurchaseOrderMapper.delete-lines
com.example.orders.PurchaseOrderMapper.deleteAll-lines
com.example.orders.PurchaseOrderMapper.findAllByPath-lines
~~~

Key point to remember: the namespace prefix in these path statements is the aggregate root type `PurchaseOrder`, not the child type `OrderLine`. For separate insert/update operations on the child entity, the namespace is based on the child type instead.

The property path is the path in the object mapping, not the SQL table name or foreign key column name. For nested paths, use the exact property path representation required by your Spring Data Relational version and verify the actual statement key in an integration test.

## 4. What Is MyBatisContext?

When Spring Data JDBC invokes a mapped statement, it passes an `org.springframework.data.jdbc.mybatis.MyBatisContext` object as the parameter object. `MyBatisContext` supplies data about the entity and the current operation so the mapper does not need to take a bare parameter such as an ID or entity directly.

Important accessors:

| Accessor | Meaning | When commonly needed |
| --- | --- | --- |
| `getInstance()` | Entity instance currently being processed | Insert/update |
| `getId()` | ID of the entity or root to process | Find/delete; `findAllById` may receive a list of IDs |
| `getDomainType()` | Class of the current entity/domain type | When distinguishing data types |
| `get(key)` | Additional value by key, typically the parent entity's ID | Inserting child entities with a back-reference |
| `getIdentifier()` | `Identifier` containing root ID and property path key/index parts | Resolving collections or relations by path |

Values may be null depending on the statement type. Do not assume every accessor is populated in every operation. For example, `getInstance()` is null for queries because the entity does not exist prior to querying.

### 4.1. instance: Entity Data Being Saved

For `insert` and `update`, `getInstance()` returns the entity being saved. MyBatis can access the entity's getters/properties via `instance` in parameter expressions.

Example entity:

~~~java
public class PurchaseOrder {
    private Long id;
    private String orderNumber;
    private String status;

    // getters/setters
}
~~~

Properties can be referenced in XML:

~~~xml
#{instance.id}
#{instance.orderNumber}
#{instance.status}
~~~

Do not confuse `instance` with an arbitrary client-supplied object. It is the entity instance Spring Data JDBC is processing in the persistence operation.

### 4.2. id: Identifier of the Entity to Read or Delete

For `findById`:

~~~xml
<select id="findById" resultMap="purchaseOrderMap">
    SELECT id, order_number, status
    FROM purchase_order
    WHERE id = #{id}
</select>
~~~

For `delete`:

~~~xml
<delete id="delete">
    DELETE FROM purchase_order
    WHERE id = #{id}
</delete>
~~~

For `findAllById`, `getId()` may be a collection of IDs rather than a single value. The mapper must handle a collection using MyBatis syntax, such as `<foreach>`, instead of always assuming the ID is a scalar.

Illustrative example:

~~~xml
<select id="findAllById" resultMap="purchaseOrderMap">
    SELECT id, order_number, status
    FROM purchase_order
    WHERE id IN
    <foreach collection="id" item="orderId"
             open="(" separator="," close=")">
        #{orderId}
    </foreach>
</select>
~~~

The property name `id` here is the `MyBatisContext` accessor. Check parameter binding for your MyBatis version if you change how mappers are configured.

### 4.3. domainType: Entity Type Being Operated On

`getDomainType()` returns the entity's Class. It is useful when a statement needs to know the domain type being processed, especially when the same SQL structure serves multiple entity types.

In mapper XML, the getter can be accessed as the `domainType` property. However, ordinary SQL should rely on pre-separated namespaces/statements rather than trying to use class names to dynamically concatenate table names.

Do not use `domainType.name` to build SQL identifiers. Table names should be determined by controlled mappers or specific mappings.

### 4.4. get(key): Parent Entity ID

When inserting a child entity, Spring Data JDBC needs to pass the aggregate root's ID to write the foreign key into the child row. This value can be retrieved with `get(key)`, where the key is the back-reference column name provided by `NamingStrategy`.

Example root declaration:

~~~java
@MappedCollection(idColumn = "purchase_order_id")
private Set<OrderLine> lines;
~~~

For the child `OrderLine`, the insert statement can use:

~~~xml
<mapper namespace="com.example.orders.OrderLineMapper">
    <insert id="insert">
        INSERT INTO order_line (
            purchase_order_id,
            product_code,
            quantity,
            unit_price
        )
        VALUES (
            #{get('purchase_order_id')},
            #{instance.productCode},
            #{instance.quantity},
            #{instance.unitPrice}
        )
    </insert>
</mapper>
~~~

In this example, `purchase_order_id` is the declared back-reference column name. If using the default naming strategy or a different `@MappedCollection`, the required key may differ. Check the actual column name in the schema and mapping metadata rather than guessing from the Java property name.

`get(key)` is designed for passing parent entity IDs. Do not treat it as an arbitrary map for general request parameters.

### 4.5. identifier: Relation Path and Keys

When Spring Data JDBC loads entities across a property path, a single ID may not be enough. For example, if the root has a `Map` or `List`, the path may require:

- The aggregate root's ID.
- The key of each entry in a `Map`.
- The element index in a `List`.
- Key components for nested paths.

`getIdentifier()` supplies an `Identifier` containing those parts. It differs from `getId()` by representing a composite path-based identifier rather than just a root ID.

In a `findAllByPath-<propertyPath>` statement, `MyBatisContext` provides this `Identifier` and the `domainType` corresponding to the entity type at the end of the path. When writing SQL for complex paths, map all ID/key/index components from `Identifier`; do not replace everything with a single `WHERE parent_id = #{id}` condition if the path also involves keys or indexes.

`Identifier` is a Spring Data JDBC API; its structure and SQL identifier names are affected by mapping. Confirm how to extract each part in your specific version instead of hardcoding assumptions about ordering.

### 4.6. Sort and Pageable

The `findAllSorted` and `findAllPaged` statements receive sorting or pagination information from the corresponding repository operations:

- `findAll(Sort)` provides a sort specification.
- `findAll(Pageable)` provides a pageable specification.

`MyBatisContext` provides the corresponding values to the statement. The mapper must translate them into `ORDER BY`, `LIMIT/OFFSET`, or equivalent database syntax.

Do not concatenate user-supplied sort strings directly into SQL. Only allow whitelisted sort properties and use appropriate database syntax.

## 5. Configuring MyBatisJdbcConfiguration

The standard integration approach is importing `MyBatisJdbcConfiguration` into your Spring Data JDBC configuration and providing a `SqlSessionFactoryBean`.

~~~java
import javax.sql.DataSource;

import org.mybatis.spring.SqlSessionFactoryBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Import;
import org.springframework.core.io.support.PathMatchingResourcePatternResolver;
import org.springframework.data.jdbc.repository.config.EnableJdbcRepositories;
import org.springframework.data.jdbc.repository.config.MyBatisJdbcConfiguration;

@Configuration
@EnableJdbcRepositories
@Import(MyBatisJdbcConfiguration.class)
public class JdbcConfiguration {

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
}
~~~

This is an illustrative configuration for an application using Spring Data JDBC and MyBatis-Spring. `MyBatisJdbcConfiguration` relies on the `SqlSession` present in the application context; `SqlSessionFactoryBean` creates `SqlSessionFactory` from the MyBatis configuration.

In a Spring Boot application, the MyBatis starter may auto-configure `SqlSessionFactory` and `SqlSessionTemplate`. In that case, check which beans are already auto-configured and avoid duplicate declarations. What is mandatory is that Spring Data JDBC sees the right `SqlSession`/`SqlSessionFactory` and that the XML mappers are loaded.

### 5.1. Sharing the Same DataSource

Spring Data JDBC and MyBatis usually need to use the same `DataSource` to participate in the same transaction. If MyBatis connects to a different datasource, a single aggregate save can split into two independent transactions.

Verify that:

- `SqlSessionFactoryBean` receives the correct datasource.
- `SqlSessionTemplate` uses the correct `SqlSessionFactory`.
- The Spring transaction manager manages that corresponding datasource.
- MyBatis-Spring manages sessions per transaction rather than opening independent sessions for each statement.

### 5.2. Placing XML Mappers in Clear Locations

Example:

~~~text
src/main/resources/
  mybatis/
    orders/
      PurchaseOrderMapper.xml
      OrderLineMapper.xml
    catalog/
      ProductMapper.xml
      CategoryMapper.xml
~~~

File names do not determine the statement namespace; the `namespace` attribute inside `<mapper>` is the key. Even when file names end with `Mapper.xml`, the namespace must still match `NamespaceStrategy`.

### 5.3. An XML Mapper Can Contain Multiple Statements

An XML mapper can declare multiple statements in the same namespace:

~~~xml
<mapper namespace="com.example.orders.PurchaseOrderMapper">
    <resultMap id="purchaseOrderMap" type="com.example.orders.PurchaseOrder">
        <!-- column/property mapping -->
    </resultMap>

    <insert id="insert">
        <!-- SQL insert -->
    </insert>

    <update id="update">
        <!-- SQL update -->
    </update>

    <select id="findById" resultMap="purchaseOrderMap">
        <!-- SQL select -->
    </select>

    <select id="findAll" resultMap="purchaseOrderMap">
        <!-- SQL select -->
    </select>
</mapper>
~~~

Do not declare two statements with the same ID in the same namespace. MyBatis cannot distinguish two mapped statements that have the same full name.

## 6. End-to-End Example: PurchaseOrder and OrderLine

Suppose the application has an aggregate:

~~~text
PurchaseOrder
  id
  orderNumber
  status
  lines: Set<OrderLine>

OrderLine
  productCode
  quantity
  unitPrice
~~~

Schema:

~~~sql
CREATE TABLE purchase_order (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    order_number VARCHAR(40) NOT NULL UNIQUE,
    status VARCHAR(24) NOT NULL
);

CREATE TABLE order_line (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    purchase_order_id BIGINT NOT NULL,
    product_code VARCHAR(80) NOT NULL,
    quantity INTEGER NOT NULL,
    unit_price DECIMAL(19, 2) NOT NULL,
    CONSTRAINT fk_order_line_order
        FOREIGN KEY (purchase_order_id)
        REFERENCES purchase_order(id)
);
~~~

Mapping:

~~~java
@Table("purchase_order")
public class PurchaseOrder {

    @Id
    private Long id;

    private String orderNumber;
    private String status;

    @MappedCollection(idColumn = "purchase_order_id")
    private Set<OrderLine> lines;
}
~~~

~~~java
@Table("order_line")
public class OrderLine {

    @Id
    private Long id;

    private String productCode;
    private Integer quantity;
    private BigDecimal unitPrice;
}
~~~

### 6.1. Insert Root

Mapper:

~~~xml
<mapper namespace="com.example.orders.PurchaseOrderMapper">
    <insert id="insert"
            useGeneratedKeys="true"
            keyProperty="instance.id"
            keyColumn="id">
        INSERT INTO purchase_order (order_number, status)
        VALUES (#{instance.orderNumber}, #{instance.status})
    </insert>
</mapper>
~~~

The statement receives `MyBatisContext`; `instance` is `PurchaseOrder`. Generated key configuration must be compatible with the database driver and the entity's ID strategy. If the ID is pre-assigned by the application, the SQL and mapping must persist that ID instead of waiting for the database to generate one.

### 6.2. Insert Child

Child mapper:

~~~xml
<mapper namespace="com.example.orders.OrderLineMapper">
    <insert id="insert"
            useGeneratedKeys="true"
            keyProperty="instance.id"
            keyColumn="id">
        INSERT INTO order_line (
            purchase_order_id,
            product_code,
            quantity,
            unit_price
        )
        VALUES (
            #{get('purchase_order_id')},
            #{instance.productCode},
            #{instance.quantity},
            #{instance.unitPrice}
        )
    </insert>
</mapper>
~~~

Here:

- `instance` is `OrderLine`.
- `get('purchase_order_id')` is the root ID passed under the back-reference column.
- The namespace is `OrderLineMapper` because the entity being inserted is `OrderLine`.

If the back-reference column is named differently, both the `@MappedCollection` mapping and the `get(...)` expression must change accordingly.

### 6.3. Update Root

~~~xml
<mapper namespace="com.example.orders.PurchaseOrderMapper">
    <update id="update">
        UPDATE purchase_order
        SET order_number = #{instance.orderNumber},
            status = #{instance.status}
        WHERE id = #{instance.id}
    </update>
</mapper>
~~~

This example only illustrates a basic update statement. If the entity uses `@Version`, custom statements must preserve the optimistic locking semantics of the Spring Data JDBC version in use: the version condition must be checked and the version must be updated properly. Do not omit versioning just because the SQL executes successfully.

### 6.4. Find Root by ID

~~~xml
<mapper namespace="com.example.orders.PurchaseOrderMapper">
    <resultMap id="purchaseOrderMap"
               type="com.example.orders.PurchaseOrder">
        <id property="id" column="id"/>
        <result property="orderNumber" column="order_number"/>
        <result property="status" column="status"/>
    </resultMap>

    <select id="findById" resultMap="purchaseOrderMap">
        SELECT id, order_number, status
        FROM purchase_order
        WHERE id = #{id}
    </select>
</mapper>
~~~

`findById` fetches the root data. Spring Data JDBC may execute additional statements to resolve child collections by property path; do not assume a single root select automatically populates collections if the mapping convention requires separate path statements.

### 6.5. Resolve Child Collection

For the `lines` property, the path statement is placed in the root's namespace:

~~~xml
<mapper namespace="com.example.orders.PurchaseOrderMapper">
    <resultMap id="orderLineMap"
               type="com.example.orders.OrderLine">
        <id property="id" column="id"/>
        <result property="productCode" column="product_code"/>
        <result property="quantity" column="quantity"/>
        <result property="unitPrice" column="unit_price"/>
    </resultMap>

    <select id="findAllByPath-lines" resultMap="orderLineMap">
        <!-- Query OrderLines using the key parts in MyBatisContext.identifier -->
        <!-- Binding Identifier parts must match the actual path mapping. -->
    </select>
</mapper>
~~~

The statement name `findAllByPath-lines` is derived from the aggregate root and the `lines` path. `MyBatisContext.getIdentifier()` carries the root ID and any keys/indexes needed for the path. The SQL WHERE clause must extract the exact Identifier components used by the schema. For `List` or `Map` collections, the path may also require position or key; test those cases separately.

## 7. Delete Operations by Property Path

Spring Data JDBC can delete child entities for a root ID or delete child rows belonging to all aggregate roots. These two operations use different statements.

### 7.1. Deleting Children of a Single Root

Example deleting the order lines of an order when deleting a single aggregate:

~~~xml
<mapper namespace="com.example.orders.PurchaseOrderMapper">
    <delete id="delete-lines">
        DELETE FROM order_line
        WHERE purchase_order_id = #{id}
    </delete>
</mapper>
~~~

Here `id` is the aggregate root's ID. The namespace uses `PurchaseOrderMapper` because the `lines` property path starts from `PurchaseOrder`.

### 7.2. Deleting Children of All Roots

~~~xml
<mapper namespace="com.example.orders.PurchaseOrderMapper">
    <delete id="deleteAll-lines">
        DELETE FROM order_line
    </delete>
</mapper>
~~~

The `deleteAll-lines` statement deletes all entities referenced via that path. This is a broad operation; understand precisely which repository operation triggers it and whether the schema/foreign keys permit it.

### 7.3. Deleting All Roots

~~~xml
<mapper namespace="com.example.orders.PurchaseOrderMapper">
    <delete id="deleteAll">
        DELETE FROM purchase_order
    </delete>
</mapper>
~~~

`deleteAll` deletes all aggregate roots of the type used as the prefix. Handling child rows must align with the mapping and aggregate deletion process. Do not replace path delete statements with a statement that only deletes the root if that violates foreign keys or leaves orphaned child data.

## 8. Result Mapping and the Responsibility of resultMap

When a MyBatis statement is selected, MyBatis is responsible for mapping results according to the statement's `resultType` or `resultMap` configuration.

A `resultMap` must specify:

- Which column maps to which property.
- Which ID column identifies the object.
- Which data types are converted.
- Whether nested relations are mapped within the same result or resolved by Spring Data JDBC via property paths.

### 8.1. Column Labels Must Match resultMap

Example:

~~~sql
SELECT
    id,
    order_number,
    status
FROM purchase_order
~~~

`resultMap`:

~~~xml
<resultMap id="purchaseOrderMap"
           type="com.example.orders.PurchaseOrder">
    <id property="id" column="id"/>
    <result property="orderNumber" column="order_number"/>
    <result property="status" column="status"/>
</resultMap>
~~~

If the SQL changes the alias to `order_no` while the `resultMap` still reads `order_number`, the property will not receive the right value. Keep aliases/column labels consistent with the `resultMap`.

### 8.2. Type Handlers

MyBatis uses `TypeHandler` to convert between JDBC types and Java types. When properties are enums, JSON, monetary types, UUIDs, or custom types, verify the appropriate `TypeHandler`.

Spring Data JDBC has its own conversion system for default mappings. When moving a statement to MyBatis, do not assume every Spring Converter is automatically used by MyBatis. SQL, JDBC types, and MyBatis TypeHandlers must be compatible.

### 8.3. Generated Keys

For database-generated IDs, the insert mapper must return the ID through MyBatis and JDBC driver mechanisms. If the ID is not assigned back onto the root entity, Spring Data JDBC cannot pass the right ID to subsequent child inserts.

Verify:

- `useGeneratedKeys` and `keyProperty` if supported by the driver.
- `selectKey` if the database requires a different way to fetch sequences/keys.
- Generated key column name.
- Whether the ID value is actually populated on the entity instance.
- Whether child inserts use the right root ID after the root insert completes.

Do not merely assert that insert returns the affected row count; read the entity back to confirm the generated ID and child relations were persisted properly.

## 9. Namespaces and Statements for Sorted/Paged Queries

Spring Data JDBC can call dedicated statements for sorting and pagination operations.

### 9.1. findAllSorted

`findAll(Sort)` can trigger the `findAllSorted` statement. `MyBatisContext` provides the sort specification. The mapper must translate the sort into a safe `ORDER BY`.

Do not use string substitution to concatenate sort expressions directly into SQL if `sort` can be controlled by a request. MyBatis has a dollar-brace direct string substitution syntax; that approach can inject raw content into SQL. Whitelist properties and directions, then use a fixed set of SQL expressions or a controlled mapping mechanism.

### 9.2. findAllPaged

`findAll(Pageable)` can trigger the `findAllPaged` statement. The context provides page, size, and sort details. The SQL statement must use the pagination syntax of the running database.

PostgreSQL/MySQL example:

~~~sql
SELECT id, order_number, status
FROM purchase_order
ORDER BY id
LIMIT #{pageable.pageSize}
OFFSET #{pageable.offset}
~~~

This is a conceptual example; how `Pageable` properties are accessed and pagination syntax must be verified for MyBatis expressions, database dialect, and Spring Data Relational version. On SQL Server/Oracle or other databases, syntax can differ.

## 10. Common Mistakes with Namespaces and Statements

| Mistake | Cause | Resolution |
| --- | --- | --- |
| Namespace missing package | Does not match fully qualified domain type | Use the full namespace per `NamespaceStrategy` |
| Missing `Mapper` suffix | Incorrect default namespace | Append `Mapper` after the entity class name |
| Wrong statement ID casing | MyBatis cannot find mapped statement | Use exact IDs such as `findById`, `findAllByPath-lines` |
| Placing path statement in child namespace | Confusing child entity type with aggregate root | For property path operations, use the root type as prefix |
| Using table name instead of property path | Statement key does not match mapping path | Use the property path name in the aggregate |
| Using `findAllByProperty` for new mappers | Deprecated convention | Use `findAllByPath` |
| Using `#{id}` in child insert for parent ID | Parent ID is in additional context values | Use `get(key)` with the back-reference column name |
| Assuming `getInstance()` is always non-null | Queries have no entity instance before reading | Choose accessors based on statement type |
| Assuming `getId()` is always a scalar | `findAllById` may pass a list of IDs | Handle collections |
| Forgetting `Identifier` for nested paths | Missing root ID/key/index of relation | Use `getIdentifier()` and map all parts |
| ResultMap has wrong column label | SQL alias does not match mapping | Synchronize SQL and `resultMap` |
| Generated ID not written back to entity | Child insert lacks root ID | Configure generated keys and test the driver |
| XML mapper not loaded | Wrong `mapperLocations` or resource path | Check `SqlSessionFactory` and classpath |
| MyBatis uses a different datasource | Does not participate in expected transaction | Share the same DataSource/transaction manager |
| Assuming every query method uses this convention | Confusing `DataAccessStrategy` statements with arbitrary mapper methods | Use custom fragments/mapper beans for custom queries |

## 11. Testing MyBatis Integration

Testing should verify not only that the XML is valid, but also that Spring Data JDBC finds the right statement and passes the right context.

### 11.1. Verifying Statements Are Loaded

After initializing `SqlSessionFactory`, check mapped statements by full name:

~~~java
String statementId =
        "com.example.orders.PurchaseOrderMapper.findById";

assertThat(sqlSessionFactory.getConfiguration()
        .hasStatement(statementId))
        .isTrue();
~~~

This catches wrong namespaces or statement IDs before calling repositories.

### 11.2. Testing Repository Operations

With `PurchaseOrderRepository`:

- `save` creates root and children.
- `save` updates root using the update statement.
- `findById` reads root and resolves child collections.
- `findAllById` handles lists of IDs.
- `deleteById` handles child paths and root per mapping.
- `deleteAll` handles required path statements.
- `count` returns the correct number of aggregate roots.

Do not only invoke MyBatis mappers directly. The goal is to verify `CrudRepository` calls actually route through the statement conventions.

### 11.3. Testing MyBatisContext for Children

Create an aggregate with multiple children, save via the repository, and verify:

- Child inserts receive the correct root ID via `get(key)`.
- Every child's foreign key column points to the right root.
- The root's generated ID is assigned before child inserts run.
- List/Map keys or indexes are persisted properly if the aggregate uses those structures.

### 11.4. Testing Rollback

Force a child insert to violate a constraint after the root has been inserted. Verify the repository/service transaction rolls back the entire aggregate. MyBatis and Spring Data JDBC must use compatible transaction managers/datasources.

### 11.5. Testing Fallback

If the combined strategy falls back to default SQL when a MyBatis statement does not exist, intentionally test an un-overridden operation. This confirms mappers only replace defined statements.

Do not let fallback hide misspelled statement names. For operations where the team expects MyBatis to be used, assert that `SqlSessionFactory` contains the corresponding statement.

## 12. Process for Adding a New Statement

When replacing a Spring Data JDBC operation with MyBatis:

1. **Identify the operation:** `insert`, `update`, `findById`, relation path, or another operation.
2. **Identify the domain type:** the entity being operated on or the aggregate root of the property path.
3. **Determine the namespace:** fully qualified entity class plus `Mapper`, unless using a custom `NamespaceStrategy`.
4. **Choose the statement ID:** use the exact name from the convention.
5. **Determine MyBatisContext usage:** do you need `instance`, `id`, `domainType`, parent ID, or `identifier`?
6. **Write SQL and mapping:** use appropriate `resultMap`/`resultType`, TypeHandlers, and generated keys.
7. **Place XML in the right mapper location:** ensure `SqlSessionFactory` loads the file.
8. **Verify datasource/transaction:** use configuration that participates in the same transaction as Spring Data JDBC.
9. **Test through the repository:** verify the statement is found and data is accurate.
10. **Test edge cases:** child collections, generated IDs, empty results, nulls, sort/page, and rollbacks.

## 13. Organizing Mappers by Aggregate

An easy-to-navigate structure:

~~~text
src/main/resources/
  mybatis/
    orders/
      PurchaseOrderMapper.xml
      OrderLineMapper.xml
    catalog/
      ProductMapper.xml
      CategoryMapper.xml
    customers/
      CustomerMapper.xml
~~~

Inside each XML:

- Root namespace uses fully qualified class name + `Mapper`.
- Statement IDs follow Spring Data JDBC conventions.
- SQL is grouped by operation for easy review.
- `ResultMap` elements have clear names.
- SQL fragments can use `<sql>` and `<include>` to avoid repetition.

Do not lump all entities into a shared namespace like `CommonMapper` when using the default namespace strategy. Doing so prevents Spring Data JDBC from finding statements by domain type.

### 13.1. Using Reusable SQL Fragments

MyBatis supports `<sql>`:

~~~xml
<mapper namespace="com.example.orders.PurchaseOrderMapper">
    <sql id="purchaseOrderColumns">
        id, order_number, status
    </sql>

    <select id="findById" resultMap="purchaseOrderMap">
        SELECT
        <include refid="purchaseOrderColumns"/>
        FROM purchase_order
        WHERE id = #{id}
    </select>
</mapper>
~~~

Keep fragments within the relevant namespace to avoid unnecessary cross-dependencies. If using `<include refid="...">` from another namespace, use a fully qualified reference per MyBatis syntax.

## Key Takeaways

In Spring Data JDBC's MyBatis integration, **the default namespace is the fully qualified domain type plus the `Mapper` suffix**, and the statement ID is the operation name such as `insert`, `update`, `findById`, or a path name such as `findAllByPath-lines`. Spring Data JDBC looks up each statement by convention; statements that are found use MyBatis SQL and mappings, while undefined statements can continue using the default strategy.

`MyBatisContext` is the parameter object providing `instance`, `id`, `domainType`, `get(key)`, and `identifier` depending on the operation. For child inserts, `get(key)` passes the parent ID under the back-reference column name; for nested paths, `identifier` carries the root ID along with required keys/indexes. Property-path statements use the aggregate root as the namespace prefix, whereas child entity inserts/updates use the child type's own namespace. `findAllByProperty` is deprecated; new mappers should use `findAllByPath`.

Configure `MyBatisJdbcConfiguration` alongside `SqlSessionFactory`, load XML mappers, use a matching datasource/transaction setup, and test through real repositories. A correct namespace with an incorrect context or `resultMap` can still result in incomplete aggregate saves/loads; therefore, verify statement lookups, generated IDs, child foreign keys, and rollbacks.

## References

- [Spring Data Relational — MyBatis Integration](https://docs.spring.io/spring-data/relational/reference/jdbc/mybatis.html)
- [MyBatisContext API](https://docs.spring.io/spring-data/data-jdbc/docs/current/api/org/springframework/data/jdbc/mybatis/MyBatisContext.html)
- [NamespaceStrategy API](https://docs.spring.io/spring-data/data-jdbc/docs/current/api/org/springframework/data/jdbc/mybatis/NamespaceStrategy.html)
- [MyBatisDataAccessStrategy API](https://docs.spring.io/spring-data/jdbc/docs/current/api/org/springframework/data/jdbc/mybatis/MyBatisDataAccessStrategy.html)

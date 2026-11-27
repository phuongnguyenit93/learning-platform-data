# Configuring MyBatisJdbcConfiguration and SqlSessionFactory

Spring Data JDBC can delegate the execution of certain CRUD operations and queries to **MyBatis**. This integration preserves Spring Data JDBC's repository and aggregate model while allowing detailed SQL and mappings to be written with MyBatis when default SQL generation does not meet requirements.

The two primary configuration components are:

- `MyBatisJdbcConfiguration`: replaces the default `DataAccessStrategy` with a strategy capable of locating and using MyBatis mapped statements.
- `SqlSessionFactory`: holds the MyBatis configuration and the statements loaded from XML mappers or annotations. In Spring, `SqlSessionFactoryBean` is the standard way to create this factory.

Crucially, this integration does not turn repositories into ordinary MyBatis mappers. Spring Data JDBC still orchestrates the aggregate lifecycle; at each persistence step, it checks whether MyBatis provides a statement matching the naming convention. If one exists, that statement is used to execute the corresponding operation.

## 1. When Do You Need MyBatis Integration?

Spring Data JDBC generates SQL automatically for standard aggregate operations. This works well for most CRUD. However, there are cases where lower-level control over SQL or mapping is needed:

- Using database-specific syntax.
- Optimizing INSERT/UPDATE statements or queries for execution plans.
- Using stored procedures, CTEs, hints, or specialized SQL expressions.
- Mapping complex query results using MyBatis structures.
- Keeping Spring Data JDBC repositories while replacing specific persistence statements with team-managed SQL.

For example, an application has `OrderRepository extends CrudRepository<Order, Long>`, but wants to customize the INSERT on the orders table and the SELECT by ID. You can define the corresponding mapped statements in MyBatis, then let Spring Data JDBC invoke them as the repository operates.

~~~mermaid
flowchart TD
    App["Application Service"]
    Repo["Spring Data JDBC Repository"]
    Strategy["MyBatisDataAccessStrategy"]
    Check{"Does SqlSessionFactory have<br/>a matching mapped statement?"}
    MB["MyBatis mapped statement"]
    Default["Default Spring Data JDBC strategy"]
    DB[("Database")]
    App --> Repo --> Strategy --> Check
    Check -->|Yes| MB --> DB
    Check -->|No| Default --> DB
~~~

MyBatis integration enables incremental replacement. You do not have to rewrite all CRUD in MyBatis; only define the statements that genuinely need customization.

## 2. Key Components to Understand

| Component | Role |
|---|---|
| `MyBatisJdbcConfiguration` | Configures Spring Data JDBC to use `MyBatisDataAccessStrategy` |
| `DataAccessStrategy` | Strategy interface that performs aggregate read/write operations |
| `SqlSessionFactoryBean` | Spring `FactoryBean` that creates `SqlSessionFactory` |
| `SqlSessionFactory` | Holds MyBatis configuration and loaded mapped statements |
| Mapper XML | Declares SQL, parameter mappings, and result mappings |
| `MyBatisContext` | Object that Spring Data JDBC passes to mapped statements |
| `CrudRepository` | Repository API that application services continue to call |

### SqlSessionFactoryBean vs. SqlSessionFactory

`SqlSessionFactoryBean` is the configuration/factory-creation object implementing Spring's `FactoryBean` mechanism. The bean that other components in the application context receive under the regular bean name is the factory's product: `SqlSessionFactory`.

`SqlSessionFactory` creates sessions for MyBatis to execute statements. The application should not hold a shared `SqlSession` in a field or manually open/close sessions for individual repository operations. MyBatis-Spring manages session lifecycles and ties them to Spring transactions.

## 3. Dependencies

You need Spring Data JDBC and MyBatis-Spring versions compatible with the Spring Framework/Spring Boot version in use. MyBatis-Spring bridges MyBatis core with the Spring container.

If the project uses Spring Boot, you can use a compatible MyBatis Spring Boot starter to manage dependencies:

~~~gradle
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-jdbc")
    implementation("org.mybatis.spring.boot:mybatis-spring-boot-starter")
}
~~~

The Gradle snippet above assumes the project manages versions via Spring Boot dependency management or a compatible version catalog/platform. If not using the starter, declare `org.mybatis:mybatis` and `org.mybatis:mybatis-spring` directly as a compatible version pair. The project still requires the Spring Data JDBC dependency as before.

Do not declare both the starter and duplicate direct dependencies if the starter already provides them. Check the dependency tree if incompatible class or method errors occur.

## 4. Importing MyBatisJdbcConfiguration

The configuration class resides in the package:

~~~java
import org.springframework.data.jdbc.repository.config.MyBatisJdbcConfiguration;
~~~

Configuration example:

~~~java
package com.example.config;

import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Import;
import org.springframework.data.jdbc.repository.config.EnableJdbcRepositories;
import org.springframework.data.jdbc.repository.config.MyBatisJdbcConfiguration;

@Configuration
@EnableJdbcRepositories(basePackages = "com.example.sales")
@Import(MyBatisJdbcConfiguration.class)
public class JdbcPersistenceConfiguration {
}
~~~

`@EnableJdbcRepositories` enables repository scanning for the specified package. `@Import(MyBatisJdbcConfiguration.class)` registers the configuration that replaces the default `DataAccessStrategy` so Spring Data JDBC can use MyBatis.

In Spring Boot, repository scanning may already be auto-configured based on the application class package. In that case, place `@Import(MyBatisJdbcConfiguration.class)` on a scanned configuration class and avoid duplicate repository scanning or unintended base packages.

Do not create another `DataAccessStrategy` manually if the goal is simply to use the built-in MyBatis integration. `MyBatisJdbcConfiguration` already provides the appropriate strategy bean.

## 5. Declaring SqlSessionFactoryBean

MyBatis needs a `SqlSessionFactory` in the application context. Explicit configuration with XML mappers:

~~~java
package com.example.config;

import java.io.IOException;
import javax.sql.DataSource;

import org.mybatis.spring.SqlSessionFactoryBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.support.PathMatchingResourcePatternResolver;

@Configuration
public class MyBatisConfiguration {

    @Bean
    public SqlSessionFactoryBean sqlSessionFactoryBean(
            DataSource dataSource) throws IOException {

        SqlSessionFactoryBean factoryBean = new SqlSessionFactoryBean();
        factoryBean.setDataSource(dataSource);
        factoryBean.setMapperLocations(
            new PathMatchingResourcePatternResolver()
                .getResources("classpath*:mybatis/**/*.xml")
        );

        return factoryBean;
    }
}
~~~

The `@Bean` method returns `SqlSessionFactoryBean`. Because it is a Spring `FactoryBean`, Spring produces the `SqlSessionFactory` product and exposes that factory in the application context. This is the configuration style illustrated in Spring Data JDBC's integration documentation.

### Sharing a DataSource

The `DataSource` parameter is injected from Spring Boot's configuration or the application's database configuration. Use the **same DataSource** for:

- Spring Data JDBC.
- MyBatis's `SqlSessionFactoryBean`.
- The application's JDBC transaction manager.

When both frameworks use the same DataSource and an appropriate transaction manager, SQL statements executed by Spring Data JDBC and MyBatis can participate in the same transaction. Creating two independent DataSources may prevent transactions from spanning both data-access paths.

### Configuring Mapper Locations

The path `classpath*:mybatis/**/*.xml` loads XML mappers under the `mybatis` directory on the classpath. The directory structure might look like:

~~~text
src/main/resources/
└── mybatis/
    └── com/
        └── example/
            └── sales/
                ├── CustomerMapper.xml
                └── OrderMapper.xml
~~~

If XML mappers are placed alongside mapper interfaces or annotations are used, loading configuration may differ. What matters is that the required mapped statements are present in `SqlSessionFactory` when the application starts.

## 6. Configuring MyBatis with a Configuration Object

You can set certain MyBatis options in Java instead of a mybatis-config.xml file. For example, enabling mapping of underscore column names to camelCase properties:

~~~java
import org.apache.ibatis.session.Configuration;
import org.mybatis.spring.SqlSessionFactoryBean;

@Bean
public SqlSessionFactoryBean sqlSessionFactoryBean(
        DataSource dataSource) throws IOException {

    SqlSessionFactoryBean factoryBean = new SqlSessionFactoryBean();
    factoryBean.setDataSource(dataSource);
    factoryBean.setMapperLocations(
        new PathMatchingResourcePatternResolver()
            .getResources("classpath*:mybatis/**/*.xml")
    );

    Configuration myBatisConfiguration = new Configuration();
    myBatisConfiguration.setMapUnderscoreToCamelCase(true);
    factoryBean.setConfiguration(myBatisConfiguration);

    return factoryBean;
}
~~~

With the configuration above, `customer_name` can map to `customerName` when using auto-mapping. You can add settings, type aliases, type handlers, or plugins as needed. If using explicit `resultMap` definitions, mappings are declared directly in XML and depend less on naming conventions.

Another option is using `configLocation` to load a MyBatis configuration file. Do not duplicate settings across multiple places; pick one clear configuration source. When using `SqlSessionFactoryBean` with Spring, DataSource and transactions are managed by Spring; do not copy a standalone environment block into MyBatis config and assume it participates in Spring transactions automatically.

## 7. Mapper Statement Naming Convention

Mapper XML has two key parts:

- `namespace`: identifies a group of mapped statements.
- `id`: the specific statement name.

Spring Data JDBC looks up statements using the convention:

~~~text
<fully-qualified-domain-type>Mapper.<operation>
~~~

For example, an entity with the fully qualified name `com.example.sales.Customer`. The insert statement must be named:

~~~text
com.example.sales.CustomerMapper.insert
~~~

Therefore, the mapper XML has namespace `com.example.sales.CustomerMapper` and statement id `insert`:

~~~xml
<?xml version="1.0" encoding="UTF-8" ?>
<!DOCTYPE mapper
  PUBLIC "-//mybatis.org//DTD Mapper 3.0//EN"
  "https://mybatis.org/dtd/mybatis-3-mapper.dtd">

<mapper namespace="com.example.sales.CustomerMapper">
    <!-- Mapped statements are declared here. -->
</mapper>
~~~

The namespace is the statement naming convention that Spring Data JDBC looks up. It does not necessarily have to be the name of a Java mapper interface annotated with `@Mapper`; in this integration, the entity's fully qualified name plus the `Mapper` suffix determines the namespace.

## 8. MyBatisContext Passed into Statements

When Spring Data JDBC finds a matching mapped statement and executes it, MyBatis receives a `MyBatisContext` as the parameter object. The class resides in the package:

~~~java
import org.springframework.data.jdbc.mybatis.MyBatisContext;
~~~

Key properties:

| Property | Meaning | Nullable? |
|---|---|---|
| `getInstance()` | Entity being inserted/updated/deleted | Yes, depending on statement type |
| `getId()` | ID of the entity to read/delete | Yes, depending on operation |
| `getDomainType()` | Domain type class being processed | Yes, depending on operation |
| `getIdentifier()` | Identifier describing the reference path to the entity | Yes, depending on operation |
| `get(key)` | Additional value, often used to retrieve the parent entity's ID by back-reference column name | Yes, depending on operation |

In MyBatis XML, getters can be accessed via property expressions. For example, `getInstance()` is referenced as `instance`; `getId()` as `id`. Do not assume every property is populated in every statement: the API documentation notes that values may be null depending on the operation type.

### Example Using instance

When inserting/updating, `instance` is the object being written:

~~~xml
#{instance.name}
#{instance.email}
~~~

### Example Using ID

When finding or deleting by ID:

~~~xml
#{id}
~~~

### Parent Entity ID

When inserting a child component belonging to an aggregate, Spring Data JDBC can supply the referencing entity's ID via `get(key)`. The key is the back-reference column name according to `NamingStrategy`. This allows the mapper to write the child's foreign key without re-querying the aggregate root.

## 9. Mapped Statements Looked Up by Spring Data JDBC

Spring Data JDBC executes multiple SQL statements for a single repository operation. MyBatis integration uses a naming convention to look up statements for each step. Common names are described in the table:

| Statement id | Purpose | Repository methods that may trigger it |
|---|---|---|
| `insert` | Inserts an entity; also applies to entities referenced by the aggregate root | `save`, `saveAll` |
| `update` | Updates an entity; also applies to entities referenced by the aggregate root | `save`, `saveAll` |
| `delete` | Deletes an entity by ID | `delete`, `deleteById` |
| `deleteAll-<propertyPath>` | Deletes entities referenced via a property path from the aggregate root | `deleteAll` |
| `deleteAll` | Deletes all aggregate roots of the type used as the prefix | `deleteAll` |
| `delete-<propertyPath>` | Deletes entities referenced via a property path when deleting the root by ID | `deleteById` |
| `findById` | Loads an aggregate root by ID | `findById` |
| `findAll` | Loads all aggregate roots | `findAll` |
| `findAllById` | Loads aggregate roots by a set of IDs | `findAllById` |
| `findAllByPath-<propertyPath>` | Loads entities referenced via a property path | `find*` methods |
| `findAllSorted` | Loads aggregate roots with sorting | `findAll(Sort)` |
| `findAllPaged` | Loads a page of aggregate roots | `findAll(Pageable)` |
| `count` | Counts aggregate roots of the type used as the prefix | `count` |

The full statement name always consists of the domain-type-based namespace and the statement id. For example, with `com.example.sales.Order`:

~~~text
com.example.sales.OrderMapper.insert
com.example.sales.OrderMapper.update
com.example.sales.OrderMapper.findById
com.example.sales.OrderMapper.count
~~~

The statement `findAllByProperty-<propertyName>` is an older deprecated convention; use `findAllByPath-<propertyPath>` for new cases per current documentation.

Not every repository method corresponds to a single SQL statement. When saving an aggregate with child collections, Spring Data JDBC may perform multiple insert/update/delete operations for its components. Therefore, when customizing aggregate persistence, review both root and child statements that the operation may require.

## 10. Example Entity and Insert/Update/Find Mapper

Simple Customer entity:

~~~java
package com.example.sales;

import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Table;

@Table("customers")
public class Customer {

    @Id
    private Long id;
    private String name;
    private String email;

    protected Customer() {
    }

    public Customer(String name, String email) {
        this.name = name;
        this.email = email;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public String getEmail() {
        return email;
    }
}
~~~

Mapper XML:

~~~xml
<?xml version="1.0" encoding="UTF-8" ?>
<!DOCTYPE mapper
  PUBLIC "-//mybatis.org//DTD Mapper 3.0//EN"
  "https://mybatis.org/dtd/mybatis-3-mapper.dtd">

<mapper namespace="com.example.sales.CustomerMapper">

    <resultMap id="customerResult"
               type="com.example.sales.Customer">
        <id column="id" property="id"/>
        <result column="name" property="name"/>
        <result column="email" property="email"/>
    </resultMap>

    <insert id="insert"
            parameterType="org.springframework.data.jdbc.mybatis.MyBatisContext"
            useGeneratedKeys="true"
            keyProperty="instance.id">
        INSERT INTO customers (name, email)
        VALUES (#{instance.name}, #{instance.email})
    </insert>

    <update id="update"
            parameterType="org.springframework.data.jdbc.mybatis.MyBatisContext">
        UPDATE customers
        SET name = #{instance.name},
            email = #{instance.email}
        WHERE id = #{instance.id}
    </update>

    <select id="findById"
            parameterType="org.springframework.data.jdbc.mybatis.MyBatisContext"
            resultMap="customerResult">
        SELECT id, name, email
        FROM customers
        WHERE id = #{id}
    </select>
</mapper>
~~~

The example uses MyBatis generated keys (`useGeneratedKeys`) and `keyProperty="instance.id"` to illustrate returning a database-generated key back to the object. Generated key support depends on the database/driver and the project's ID strategy. If using UUIDs or application-assigned IDs, omit generated key configuration and bind the ID according to your design.

Schema:

~~~sql
CREATE TABLE customers (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    name VARCHAR(120) NOT NULL,
    email VARCHAR(255) NOT NULL
);
~~~

The repository remains Spring Data JDBC:

~~~java
package com.example.sales;

import org.springframework.data.repository.CrudRepository;

public interface CustomerRepository
        extends CrudRepository<Customer, Long> {
}
~~~

Services continue calling the repository as usual:

~~~java
@Service
public class CustomerService {

    private final CustomerRepository customers;

    public CustomerService(CustomerRepository customers) {
        this.customers = customers;
    }

    public Customer create(String name, String email) {
        return customers.save(new Customer(name, email));
    }
}
~~~

When `save` runs, Spring Data JDBC checks `SqlSessionFactory` to see if `com.example.sales.CustomerMapper.insert` exists. If it does, MyBatis executes the defined SQL and applies the corresponding result/parameter mappings.

## 11. Customizing SQL for Child Entities

An aggregate can contain child collections:

~~~java
@Table("orders")
public class Order {

    @Id
    private Long id;

    private String status;

    @MappedCollection(idColumn = "order_id")
    private List<OrderLine> lines;
}
~~~

`OrderLine` is stored in a separate table, but its persistence lifecycle is managed by the aggregate root. When Spring Data JDBC inserts the root and lines, the `insert` statement can also be looked up for the referenced entity.

The mapper statement namespace for the child is based on the child entity's fully qualified class name. `MyBatisContext` provides the parent entity's ID under the key corresponding to the back-reference column generated by `NamingStrategy`.

Because the reference column name may depend on `NamingStrategy` or `@MappedCollection(idColumn = ...)`, the mapper must use the exact key name provided by the mapping. Do not hardcode the assumption that the column name is always `order_id` if the actual configuration differs.

## 12. Integrating Query Methods and Pagination

MyBatis integration supports the read steps performed by Spring Data JDBC. Certain statements follow specific conventions:

- `findById`: loads an aggregate root by ID.
- `findAll`: loads all aggregate roots.
- `findAllById`: loads roots by a list of IDs.
- `findAllSorted`: loads with `Sort`.
- `findAllPaged`: loads with `Pageable`.
- `count`: counts aggregate roots.

Example statement names:

~~~text
com.example.sales.OrderMapper.findAllPaged
com.example.sales.OrderMapper.findAllSorted
com.example.sales.OrderMapper.findAllById
com.example.sales.OrderMapper.count
~~~

For `findAllPaged`, `MyBatisContext` provides `getPageable()` so the statement can use page and sort information. For `findAllSorted`, the context provides `getSort()`. The SQL mapper must translate that information into `ORDER BY` and pagination using the database's dialect.

Do not concatenate sort strings from requests directly into XML SQL. Use properties/sorts controlled at the API layer and map them to fixed columns in the mapper. When using pagination, the count query and content query must share the same filter conditions so page metadata remains accurate.

## 13. SqlSessionFactory, SqlSession, and Transactions

`SqlSessionFactory` is a shared factory, while executing sessions must be bound to the appropriate transaction and thread.

In MyBatis-Spring:

- `SqlSessionFactoryBean` creates the factory.
- `SqlSessionTemplate` is a thread-safe `SqlSession` implementation commonly used when writing DAOs/mappers directly.
- MyBatis-Spring manages session lifecycle, commit/rollback, and closing sessions.
- If a Spring transaction is active on the same DataSource, MyBatis uses the connection bound to that transaction.

When integrating via `MyBatisJdbcConfiguration`, Spring Data JDBC uses the MyBatis data access strategy and configured `SqlSessionFactory`. There is no need to open sessions manually in repositories or callbacks.

Example application service:

~~~java
@Service
public class OrderApplicationService {

    private final OrderRepository orders;

    public OrderApplicationService(OrderRepository orders) {
        this.orders = orders;
    }

    @Transactional
    public Order place(Order order) {
        return orders.save(order);
    }
}
~~~

If saving an aggregate uses multiple MyBatis mapped statements for root and children, those statements should participate in the same transaction. Configuring the same DataSource and transaction manager is essential so a rollback does not leave a partially written aggregate behind.

Do not configure a standalone MyBatis transaction manager with a different DataSource and assume it will coordinate atomically with Spring Data JDBC transactions.

## 14. Common Configuration Errors

| Symptom | Possible Cause | Resolution |
|---|---|---|
| `SqlSessionFactory` not found | `SqlSessionFactoryBean` not declared or MyBatis starter did not create the factory | Check factory bean and dependencies |
| `MyBatisJdbcConfiguration` not applied | Forgot `@Import` or configuration class not scanned | Import configuration in the application context |
| Statement not found | Namespace or statement id violates convention | Use fully qualified entity name + `Mapper` + operation |
| Mapper XML not loaded | Incorrect `mapperLocations` or resource not on classpath | Check pattern and file location |
| MyBatis cannot bind `instance.name` | Wrong parameter object or property path | Use `MyBatisContext` and verify property names |
| `findById` does not return the right entity | `resultMap`/`resultType` does not match entity | Declare an explicit `resultMap` |
| Child insert missing foreign key | Not using parent reference from `MyBatisContext` or wrong key | Check back-reference column and `get(key)` |
| Generated ID remains null | Key generation configuration incompatible with driver/database | Check `useGeneratedKeys`, `keyProperty`, or ID strategy |
| Spring rolls back but MyBatis already committed | Different DataSource/transaction manager or improper session management | Use the same DataSource and MyBatis-Spring integration |
| Some operations run default SQL, others run MyBatis | Only some mapped statements exist | Check statement names for each step |
| Binding errors due to underscore/camelCase | Auto-mapping does not match column/property names | Use `resultMap` or configure naming explicitly |

## 15. Implementation Checklist

Before enabling MyBatis integration:

1. Choose MyBatis and MyBatis-Spring versions compatible with Spring Boot/Spring Data JDBC.
2. Verify dependencies include both MyBatis core and the MyBatis-Spring bridge.
3. Import `MyBatisJdbcConfiguration`.
4. Configure a `SqlSessionFactory` in the application context.
5. Share the same `DataSource` with Spring Data JDBC.
6. Configure mapper XML locations or the corresponding statement-loading mechanism.
7. Name namespaces using the fully qualified entity type plus the `Mapper` suffix.
8. Set statement ids to the exact operation names.
9. Use `MyBatisContext` to read instance, ID, domain type, and parent references.
10. Write explicit `resultMap` definitions for results needing custom mapping.
11. Verify generated IDs, version fields, and foreign keys when mappers customize aggregate inserts/updates.
12. Test transaction rollback on aggregates with roots and children.

## 16. Practice Exercises

1. Add compatible Spring Data JDBC and MyBatis-Spring dependencies to a sample application.
2. Import `MyBatisJdbcConfiguration` in the persistence configuration.
3. Create a `SqlSessionFactoryBean` sharing the `DataSource` and loading XML mappers from `classpath*:mybatis/**/*.xml`.
4. Create a `Customer` entity and `CustomerRepository extends CrudRepository<Customer, Long>`.
5. Create an XML mapper with namespace `com.example.sales.CustomerMapper`.
6. Write `insert`, `update`, and `findById` statements using `MyBatisContext`.
7. Call `repository.save` and `findById` and verify MyBatis statements are used when matching mappings exist.
8. Remove one mapped statement in a test environment and observe the default strategy handling the unmapped step.
9. Create an `Order` aggregate with `OrderLine`; write insert statements for both root and child.
10. Retrieve the parent ID in the child statement from `MyBatisContext` using the configured back-reference key.
11. Write `findAllPaged` and `count`; verify page content and total count share the same criteria.
12. Trigger an error midway through saving an aggregate and verify the transaction rolls back both MyBatis and Spring Data JDBC operations.

## 17. Key Takeaways

To integrate MyBatis with Spring Data JDBC, import `MyBatisJdbcConfiguration` and provide a `SqlSessionFactory` via `SqlSessionFactoryBean` or equivalent configuration. The factory must use the same `DataSource` as Spring Data JDBC so operations can participate in the same transaction.

Spring Data JDBC still orchestrates aggregates and repositories. For each CRUD/query step, it looks up a mapped statement by the convention `<fully-qualified-domain-type>Mapper.<operation>`. If a matching statement exists, MyBatis executes the configured SQL and mapping. `MyBatisContext` provides the entity instance, ID, domain type, and parent reference information so mappers can access the right data.

Start by customizing only the few statements that actually need it, keep namespace/statement names exact, configure XML mappers and transactions consistently, and then expand to child entities or pagination as needed.

## References

- [Spring Data Relational — MyBatis Integration](https://docs.spring.io/spring-data/relational/reference/jdbc/mybatis.html)
- [MyBatisJdbcConfiguration API](https://docs.spring.io/spring-data/relational/reference/api/java/org/springframework/data/jdbc/repository/config/MyBatisJdbcConfiguration.html)
- [MyBatisContext API](https://docs.spring.io/spring-data/relational/reference/api/java/org/springframework/data/jdbc/mybatis/MyBatisContext.html)
- [MyBatis-Spring — SqlSessionFactoryBean](https://mybatis.org/spring/factorybean.html)
- [MyBatis-Spring — Transactions](https://mybatis.org/spring/transactions.html)

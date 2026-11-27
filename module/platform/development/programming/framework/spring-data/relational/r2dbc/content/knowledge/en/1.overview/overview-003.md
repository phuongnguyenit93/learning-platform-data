# Distinguishing Spring Data Relational, Spring Data R2DBC, and Spring R2DBC

These three names are closely related but reside at different layers of the Spring ecosystem. The easiest point of confusion is that **Spring Data R2DBC** and **Spring R2DBC** both work with R2DBC, whereas **Spring Data Relational** provides the relational data model and mapping infrastructure shared by Spring Data JDBC and Spring Data R2DBC.

A quick way to remember:

- **Spring Data Relational**: shared relational data model and mapping infrastructure.
- **Spring Data R2DBC**: Spring Data layer providing repositories, entity mapping, and reactive relational data operations over R2DBC.
- **Spring R2DBC**: Spring Framework layer integrating the R2DBC SPI, providing lower-level SQL access and connection/transaction management APIs.

## 1. Placing the Three Components in the Right Layers

An application can access a relational database via JDBC or R2DBC. Spring separates responsibilities across multiple layers so that the data modeling layer and the database connectivity layer are not tightly coupled.

### Spring Data Relational

Spring Data Relational is a name used in two related scopes:

1. **The Spring Data Relational project/solution family**: encompasses relational data access modules such as Spring Data JDBC and Spring Data R2DBC.
2. **The spring-data-relational module**: the shared foundational infrastructure beneath those modules.

When comparing the three names in this lesson, the focus is on the shared foundational module. This module provides metadata models for tables and columns, rules for mapping objects to relational data, type conversion, naming strategies, relational query concepts, and related core mechanisms.

For example, annotations such as **@Table**, **@Column**, and **@Id** describe how a Java class corresponds to a table, columns, and an identifier. These mapping concepts can be used in both Spring Data JDBC and Spring Data R2DBC.

Spring Data Relational is not a database connection protocol, not a JDBC driver, and not an R2DBC driver. It does not determine whether an application uses synchronous or reactive connections. That belongs to the specific data access module.

### Spring Data R2DBC

Spring Data R2DBC is a Spring Data module that provides a way to work with relational databases over R2DBC using the Spring Data programming model.

It adds the data-layer utilities applications typically need:

- Repository abstractions, such as **ReactiveCrudRepository**.
- Entity-to-table and column mapping built on Spring Data Relational infrastructure.
- Query derivation from repository method names where supported.
- Support for declarative and custom queries.
- **R2dbcEntityTemplate** for entity operations without necessarily creating a repository.
- Callback, conversion, and transaction integration mechanisms tailored for reactive flows.

Spring Data R2DBC lets applications work with entities and repositories rather than manually managing every detail of SQL statements, **Row**, and **Connection**.

Its name contains R2DBC because this module uses R2DBC as its connectivity foundation. It is neither the R2DBC SPI itself nor Spring Framework's **spring-r2dbc** module.

### Spring R2DBC

Spring R2DBC is a **Spring Framework** module. It integrates the R2DBC SPI standard into the Spring ecosystem and provides infrastructure APIs for SQL execution, connection management, exception translation, and transaction coordination.

A representative API is **DatabaseClient**. Applications can use this API to send SQL and read results without writing the entire workflow of acquiring connections, executing statements, and releasing resources.

Common components include:

- **ConnectionFactory**: the entry point for creating connections according to the R2DBC SPI.
- **DatabaseClient**: the API for executing SQL and processing results.
- **R2dbcTransactionManager**: the transaction manager for a **ConnectionFactory**.
- **ConnectionFactoryUtils**: utilities for acquiring and managing connections bound to a Spring context.
- **TransactionalOperator**: a programmatic way to coordinate transactions in reactive flows.

Spring R2DBC provides lower-level data access infrastructure than Spring Data R2DBC. If an application only needs to run custom SQL and map results manually, it can use **DatabaseClient** directly without creating a Spring Data repository.

## 2. Relationships Between the Components

The diagram below illustrates how the layers typically work together when an application uses a reactive repository:

~~~mermaid
flowchart TB
    A["Application"]
    B["Spring Data R2DBC<br/>Repositories, entity mapping,<br/>R2dbcEntityTemplate"]
    C["Spring Data Relational<br/>Shared relational metadata and mapping"]
    D["Spring R2DBC<br/>DatabaseClient, transactions,<br/>connections"]
    E["R2DBC SPI"]
    F["R2DBC Driver"]
    G[("Relational database")]

    A --> B
    B --> C
    B --> D
    D --> E
    E --> F
    F --> G
~~~

In the diagram, Spring Data R2DBC uses shared relational mapping concepts and relies on Spring R2DBC infrastructure to communicate via the R2DBC SPI. A specific driver implements the SPI to connect to the database management system.

Spring Data Relational and Spring R2DBC do not replace each other: one focuses on the relational data model, while the other focuses on R2DBC connectivity and SQL execution.

You can place Spring Data JDBC alongside this architecture to see the role of the shared layer:

~~~mermaid
flowchart TB
    A["Application using Spring Data JDBC"]
    B["Spring Data JDBC<br/>Repositories and JdbcAggregateTemplate"]
    C["Spring Data Relational<br/>Shared relational mapping"]
    D["Spring JDBC<br/>JdbcTemplate and JDBC transactions"]
    E["JDBC API"]
    F["JDBC Driver"]
    G[("Relational database")]

    A --> B
    B --> C
    B --> D
    D --> E
    E --> F
    F --> G
~~~

Spring Data JDBC and Spring Data R2DBC can share many relational mapping concepts, but their connection paths and execution models differ:

- Spring Data JDBC goes through Spring JDBC and the JDBC API; operations are typically synchronous, blocking the calling thread while waiting on I/O.
- Spring Data R2DBC goes through Spring R2DBC and the R2DBC SPI; the API is designed for reactive processing without blocking threads during I/O when the driver implements this model properly.

## 3. Direct Comparison

| Criterion | Spring Data Relational | Spring Data R2DBC | Spring R2DBC |
|---|---|---|---|
| Position | Shared Spring Data infrastructure/model for relational data | Spring Data module | Spring Framework module |
| Primary responsibility | Shared metadata, mapping, conversion, and relational concepts | Reactive repositories and entity operations | Connectivity, SQL execution, and transactions over R2DBC |
| Representative APIs/concepts | **@Table**, **@Column**, **@Id**, relational mapping metadata | **ReactiveCrudRepository**, **R2dbcEntityTemplate** | **DatabaseClient**, **ConnectionFactory**, **R2dbcTransactionManager** |
| Has repository abstraction? | Not the role of the shared base layer | Yes | Does not provide Spring Data repositories |
| Has entity mapping? | Provides the shared relational mapping foundation | Uses that foundation to map entities when accessing via R2DBC | Not Spring Data's entity mapping layer |
| Execution style | Does not determine connection type on its own | Reactive | Reactive |
| Driver | Does not provide drivers | Requires an appropriate R2DBC driver | Works with drivers through the R2DBC SPI |

An important distinction is that the word "reactive" does not apply to everything named Spring Data Relational. It is the shared relational mapping foundation; Spring Data JDBC remains imperative, while Spring Data R2DBC is reactive.

## 4. Examples to Spot the API Boundaries

Suppose an application has a **customer** table with two columns: **id** and **full_name**.

### 4.1. Describing Relational Mapping

An entity can declare metadata as follows:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Column;
import org.springframework.data.relational.core.mapping.Table;

@Table("customer")
public record Customer(
    @Id Long id,
    @Column("full_name") String fullName
) {}
~~~

**@Table**, **@Column**, and **@Id** describe the relationship between the Java type and the table structure. This belongs to the relational mapping model provided by Spring Data Relational. Both Spring Data JDBC and Spring Data R2DBC can use this metadata when reading and writing data.

These annotations by themselves do not open connections or send SQL. To perform operations, the application needs a data access module such as Spring Data JDBC or Spring Data R2DBC.

### 4.2. Using Spring Data R2DBC with a Repository

A reactive repository can be declared as follows:

~~~java
import org.springframework.data.repository.reactive.ReactiveCrudRepository;
import reactor.core.publisher.Flux;

public interface CustomerRepository
        extends ReactiveCrudRepository<Customer, Long> {

    Flux<Customer> findByFullName(String fullName);
}
~~~

**ReactiveCrudRepository** belongs to Spring Data R2DBC. Spring Data provides implementations for CRUD operations and processes query methods according to conventions. Results are represented using reactive types such as **Mono** or **Flux**.

For example:

~~~java
customerRepository.findByFullName("An")
    .subscribe(customer -> System.out.println(customer.fullName()));
~~~

In real applications, controllers or services generally return and compose publishers rather than calling **subscribe()** arbitrarily across layers. That lets the framework coordinate execution flows and handle errors consistently.

### 4.3. Using Spring R2DBC Directly with DatabaseClient

If custom SQL is needed without a repository, **DatabaseClient** can be used:

~~~java
import org.springframework.r2dbc.core.DatabaseClient;
import reactor.core.publisher.Flux;

DatabaseClient databaseClient =
    DatabaseClient.create(connectionFactory);

Flux<Customer> customers =
    databaseClient.sql("""
            SELECT id, full_name
            FROM customer
            WHERE full_name = :name
            """)
        .bind("name", "An")
        .map((row, metadata) -> new Customer(
            row.get("id", Long.class),
            row.get("full_name", String.class)
        ))
        .all();
~~~

In this example, **DatabaseClient** belongs to Spring R2DBC. The application writes SQL, binds parameters, and manually specifies how to convert each result row into a **Customer**. No Spring Data repository is involved in this operation.

If you need entity operations with Spring Data mapping without creating a repository, consider **R2dbcEntityTemplate**, which belongs to Spring Data R2DBC.

### 4.4. Comparing Side-by-Side with Spring Data JDBC

With the same data model, a Spring Data JDBC imperative repository looks like:

~~~java
import org.springframework.data.repository.CrudRepository;

public interface CustomerRepository
        extends CrudRepository<Customer, Long> {
}
~~~

This repository uses **CrudRepository** and returns results imperatively, such as an entity, **Iterable**, or **Optional** depending on the method. It goes through the JDBC path, not R2DBC.

The two repositories may look nearly identical at declaration time, yet their return types, drivers, transaction managers, and I/O mechanics differ. You cannot turn JDBC into non-blocking I/O simply by wrapping JDBC calls in **Mono** or **Flux**.

## 5. Which Component Should You Choose for Your Application?

Start with how your application needs to perform database I/O:

| Need | Suitable Direction | Reason |
|---|---|---|
| Want CRUD repositories and query methods in an imperative style | Spring Data JDBC | Provides repositories and relational mapping using JDBC |
| Want CRUD repositories and query methods in a reactive flow | Spring Data R2DBC | Provides reactive repositories and uses R2DBC |
| Want to write reactive SQL directly with full control over result mapping | Spring R2DBC (**DatabaseClient**) | Provides a Spring Framework-level SQL API |
| Want to understand shared annotations, metadata, and mapping across JDBC/R2DBC | Spring Data Relational | Serves as the shared relational model and infrastructure layer |

Some practical guidelines:

1. **Choose based on driver and I/O model.** If the application uses a JDBC driver, choose the JDBC path. If reactive I/O is needed and the database has a suitable R2DBC driver, choose R2DBC.
2. **Choose the abstraction level based on need.** Use Spring Data R2DBC when repositories and entity mapping make application code cleaner. Use **DatabaseClient** when direct SQL control is required or repositories are unnecessary.
3. **Do not install Spring Data Relational as if it were a driver.** In an application, this module is normally brought in transitively via Spring Data JDBC or Spring Data R2DBC. Specific dependencies should be managed according to the Spring Data/Spring Boot version your project uses.
4. **Verify R2DBC driver capabilities.** Support for data types, SQL features, and transaction behavior depends on the driver and database management system.
5. **Keep reactive flows unblocked.** Once R2DBC is chosen, avoid calling blocking operations such as JDBC or other blocking I/O on reactive processing threads. Wrapping a blocking call in **Mono** does not make the call itself non-blocking.

## 6. Transactions and Reactivity

Spring R2DBC provides **R2dbcTransactionManager** to manage transactions for a **ConnectionFactory**. Spring Data R2DBC integrates with this transaction manager so repositories and entity operations participate in transactions.

In reactive applications, you can use **@Transactional** on methods returning publishers or use **TransactionalOperator** to coordinate transactions programmatically. Reactive transactions are bound to the reactive context; therefore, maintain the publisher chain and configure the proper transaction manager.

JDBC has its own transaction model, typically using **DataSourceTransactionManager** or a corresponding JDBC transaction mechanism. JDBC and R2DBC transactions use different connection types. Do not assume a JDBC transaction will automatically cover R2DBC operations, or vice versa.

## 7. Common Misconceptions

**"Spring Data R2DBC and Spring R2DBC are the same thing."**  
No. Spring Data R2DBC provides repositories and entity-oriented data access. Spring R2DBC provides connectivity and SQL execution infrastructure based on the R2DBC SPI. Spring Data R2DBC builds upon Spring R2DBC infrastructure.

**"Spring Data Relational is another way to connect to a database."**  
No. The **spring-data-relational** module provides shared relational mapping concepts and infrastructure. Actual database connectivity is handled by Spring Data JDBC or Spring Data R2DBC.

**"Using Spring Data Relational automatically makes an application reactive."**  
No. Shared relational mapping does not dictate whether I/O is blocking or non-blocking. Spring Data JDBC uses JDBC imperatively; Spring Data R2DBC uses R2DBC reactively.

**"Having Spring R2DBC means you already have repositories."**  
No. You can use **DatabaseClient** to execute SQL directly. To use the repository abstraction, you need Spring Data R2DBC.

**"R2DBC is just JDBC with Mono/Flux return types."**  
No. R2DBC is a separate SPI designed for reactive database access. It requires a driver implementing the R2DBC SPI. A JDBC driver does not become an R2DBC driver when invoked from reactive code.

**"Reactive is always faster than JDBC."**  
You cannot conclude that for every application. Reactive programming can help serve more concurrent I/O tasks with a limited number of threads, but actual performance depends on workload, driver, connection pool, application design, and database capacity. If an application is primarily imperative or load does not require a reactive model, JDBC may be simpler and more suitable.

## 8. One-Sentence Takeaways for Each Name

- **Spring Data Relational** answers: how is relational data described and mapped into the Spring Data object model?
- **Spring Data R2DBC** answers: how do you use Spring Data repositories and entity mapping with relational databases over R2DBC?
- **Spring R2DBC** answers: how does Spring execute SQL, manage connections, and handle transactions over the R2DBC SPI?

When inspecting a project's dependencies, packages, or code, look at the APIs being used: **@Table** and **@Column** indicate relational mapping; **ReactiveCrudRepository** or **R2dbcEntityTemplate** indicates the Spring Data R2DBC layer; **DatabaseClient** or **R2dbcTransactionManager** indicates the Spring R2DBC infrastructure. Identifying the exact API clarifies which layer owns each responsibility.

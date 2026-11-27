# Open Projections, Expressions, and Processing Costs

Projections allow a repository to return a **restricted view of an aggregate** instead of always returning the full domain object. With Spring Data JDBC, projections are useful for list screens, read APIs, and cases needing only a few properties. When you need to compute presentation values from multiple properties, Spring Data also supports **open projections**: an interface projection can use SpEL expressions via the `@Value` annotation.

Open projections are flexible, but expressions can read any property on the aggregate root. Consequently, Spring Data cannot determine the minimal property set in advance to optimize data retrieval. Beyond query and aggregate mapping costs, the application also pays the cost of proxy creation and expression evaluation. Understanding these costs is essential before using open projections on large lists.

This lesson uses a person profile example to cover:

- Interface projections and class-based projections (DTOs).
- Closed projections and open projections.
- SpEL expressions with `@Value`.
- `target`, `args`, and invoking Spring beans from expressions.
- Default methods as an option for simple calculations.
- Dynamic projections and nullable wrappers.
- Impact on SQL, object materialization, CPU, memory, and serialization.
- How to choose the right projection in Spring Data JDBC.

## 1. What Is a Projection?

A typical repository returns the aggregate root:

~~~java
public interface PersonRepository
        extends CrudRepository<Person, UUID> {

    List<Person> findByLastName(String lastName);
}
~~~

When calling `findByLastName("Nguyen")`, the application receives `Person` objects modeled for the domain. However, a directory screen may only need name and email; it does not need every property or child component of the aggregate.

A projection describes a **dedicated view** containing the properties required by a read use case.

Example:

~~~java
public interface PersonNameView {

    String getFirstName();

    String getLastName();
}
~~~

The repository can declare:

~~~java
public interface PersonRepository
        extends CrudRepository<Person, UUID> {

    List<PersonNameView> findByLastName(String lastName);
}
~~~

Spring Data generates a proxy for the interface projection at runtime. When the application calls `getFirstName()`, the proxy delegates the call to the corresponding property on the target object.

A projection type sits outside the entity's inheritance hierarchy. If the repository returns a superclass or interface already implemented by `Person`, Spring Data may return the fully materialized entity; declaring a supertype does not automatically create a projection.

### 1.1. A Projection Is Not a New Entity

`PersonNameView` only describes read data. It is not an aggregate root and has no repository of its own. Projection getters do not create a new record or alter the persistence lifecycle of `Person`.

| Result type | Meaning |
|---|---|
| `Person` | Domain-modeled aggregate root |
| Interface projection | View created via a proxy over properties of the target object |
| DTO projection | Value object constructed from selected properties |
| Custom read model | Query result specifically designed for a screen or report |

Projections fit when the application needs to read a subset of data. Write business operations should still load the aggregate root and invoke domain behavior to protect invariants.

## 2. Closed Projections

An interface projection is a **closed projection** when its declared accessors correspond directly to properties of the aggregate root.

~~~java
public interface PersonNameView {

    String getFirstName();

    String getLastName();
}
~~~

The getter methods map to `firstName` and `lastName` of `Person`. Spring Data knows exactly which properties the projection requires.

Closed projections enable Spring Data to optimize query execution because the required property set is known. The exact degree of optimization depends on the module and query execution path; do not assume every Spring Data JDBC method always generates a SELECT statement containing only the getter columns. When SQL optimization is a critical requirement, inspect the actual statements.

### 2.1. Using Default Methods to Compute Display Values

A closed projection can still include computed values if the logic relies solely on already-declared accessors:

~~~java
public interface PersonNameView {

    String getFirstName();

    String getLastName();

    default String getFullName() {
        return getFirstName() + " " + getLastName();
    }
}
~~~

`getFullName()` does not require a `fullName` property in the entity. The default method calls two known getters and concatenates the results.

This is usually a clean choice for simple calculations:

- Joining first and last names.
- Building a label from two properties.
- Formatting an existing value for display.
- Returning a default value based on a getter.

Because dependent properties are still explicitly declared, Spring Data can still determine the dataset needed for the projection.

## 3. Open Projections and `@Value` Expressions

An interface projection becomes an **open projection** when an accessor uses `@Value` to compute a value with SpEL.

~~~java
import org.springframework.beans.factory.annotation.Value;

public interface PersonDisplayView {

    @Value("#{target.firstName + ' ' + target.lastName}")
    String getDisplayName();
}
~~~

In the expression:

- `target` is the domain object backing the projection.
- `target.firstName` reads the `firstName` property.
- `target.lastName` reads the `lastName` property.
- The result is returned as the value of `getDisplayName()`.

`displayName` does not need to be a database column. It is computed when the projection accessor is called.

### 3.1. Why Can't Open Projections Optimize Properties Like Closed Projections?

With a closed projection, Spring Data knows the exact properties requested by getters.

With an open projection, an expression can access any property of `target`. Today the expression might read only `firstName` and `lastName`; later it might change to read `email`, `address`, or another property.

Because all dependencies cannot be statically determined upfront, Spring Data cannot apply query execution optimizations based on a narrow property set as it can with closed projections.

Consequences:

1. The application may have to read more properties than the screen actually needs.
2. The target object may be materialized with broader data than expected.
3. Mapped aggregate components may incur separate read costs under Spring Data JDBC mechanics.
4. SpEL is evaluated when the open projection accessor is invoked.

Therefore, open projections are usually suited for small presentation calculations over existing data, not as a replacement for SQL projections or DTO queries across large lists.

## 4. Using `target` and `args` in SpEL

`target` represents the backing object. In addition, arguments passed to the projection method can be accessed through the `args` array.

~~~java
public interface PersonGreetingView {

    String getFirstName();

    @Value("#{args[0] + ' ' + target.firstName + '!'}")
    String getGreeting(String prefix);
}
~~~

Calling it:

~~~java
PersonGreetingView view = ...;

String greeting = view.getGreeting("Hello");
~~~

Here `args[0]` is the string `"Hello"`, while `target.firstName` retrieves the name from the target object.

You can use arguments to vary presentation without creating multiple projection interfaces. However, keep expressions short and readable. If you need multiple branches, formatting rules, or complex business logic, move the logic to a Java method or a Spring bean.

## 5. Invoking a Spring Bean from an Open Projection

For more complex calculations, Spring Data lets an expression invoke a bean in the ApplicationContext.

Bean:

~~~java
import org.springframework.stereotype.Component;

@Component
public class PersonPresentation {

    public String displayName(Person person) {
        if (person.getFirstName() == null) {
            return person.getLastName();
        }

        if (person.getLastName() == null) {
            return person.getFirstName();
        }

        return person.getFirstName() + " " + person.getLastName();
    }
}
~~~

Projection:

~~~java
import org.springframework.beans.factory.annotation.Value;

public interface PersonDisplayView {

    @Value("#{@personPresentation.displayName(target)}")
    String getDisplayName();
}
~~~

`@personPresentation` references the bean named `personPresentation`; `target` is passed to the Java method.

This approach has several advantages:

- Logic is written in Java, making it directly refactorable and testable.
- The expression is reduced to a short call.
- Presentation logic can be reused.
- Null-handling or formatting rules can be applied cleanly.

The bean should perform lightweight, deterministic calculations without side effects. Avoid calling repositories, HTTP clients, or external services from methods invoked by a projection. If a list of 500 people calls a bean and each call queries the database, the application could issue 500 extra queries and turn a presentation calculation into an N+1 problem.

## 6. Default Method or SpEL?

Both default methods and SpEL can create computed properties. Choose based on complexity and dependency scope.

| Criterion | Default method | Open projection with SpEL |
|---|---|---|
| Input data | Declared projection getters | Can access all of `target` |
| Logic style | Java | String-based expression |
| Compile-time checking | Better | Properties/expressions are not fully checked by the Java compiler |
| Flexibility | Sufficient for simple logic | More flexible, supports `args` and beans |
| Property optimization | Can remain closed if using only declared getters | Cannot optimize like closed projections |
| Maintainability | Easy to read for short logic | Hard to read if expressions grow long |

For example, if only concatenating a name:

~~~java
public interface PersonNameView {

    String getFirstName();

    String getLastName();

    default String getDisplayName() {
        return getFirstName() + " " + getLastName();
    }
}
~~~

If logic needs a shared formatter, a bean can be used. If the expression is just a short concatenation with explicit dependencies, a default method is usually easier to maintain.

Do not put entire business rules inside SpEL. Projections are a read-presentation layer; domain rules belong in the appropriate domain/service layer.

## 7. DTO Projections: No Proxy Needed

Besides interface projections, Spring Data supports class-based projections, commonly implemented with DTOs or Java records.

~~~java
public record PersonCard(
        UUID id,
        String firstName,
        String lastName
) {
    public String displayName() {
        return firstName + " " + lastName;
    }
}
~~~

Repository:

~~~java
public interface PersonRepository
        extends CrudRepository<Person, UUID> {

    List<PersonCard> findByLastName(String lastName);
}
~~~

Unlike interface projections, Spring Data does not create a proxy for a DTO. It constructs the object via the DTO's constructor.

Key points to remember:

- The constructor must have parameters matching the projected properties.
- Java records fit well because of their canonical constructor and immutable properties.
- If a class has multiple constructors, use `@PersistenceCreator` to mark the constructor to use when needed.
- Class-based projections do not support nested projections in the same way interface projections do.
- Column reduction depends on the module's and query's optimization capabilities.

DTOs are often ideal when the returned data shape is stable, especially for API responses or read models. Simple calculations can live in record methods; if SQL-based calculations are needed, consider a custom query returning a DTO with appropriate aliases.

## 8. Dynamic Projections

You can choose the projection type at repository call time via a `Class<T>` parameter.

~~~java
public interface PersonRepository
        extends CrudRepository<Person, UUID> {

    <T> List<T> findByLastName(
            String lastName,
            Class<T> projectionType
    );
}
~~~

Usage:

~~~java
List<Person> entities =
        repository.findByLastName("Nguyen", Person.class);

List<PersonNameView> names =
        repository.findByLastName("Nguyen", PersonNameView.class);

List<PersonCard> cards =
        repository.findByLastName("Nguyen", PersonCard.class);
~~~

Dynamic projections are useful when multiple use cases need different views with the same search criteria.

Note one caveat: Spring Data inspects the `Class` parameter to determine whether it is a dynamic projection parameter. If the parameter's generic type matches the generic type in the return type, that `Class` parameter is used to select the projection and is no longer available as a regular query parameter or SpEL variable. If you need to pass a `Class` as query data, use a different generic type, such as `Class<?>`.

Avoid creating excessive projection types for tiny differences. Every new view adds another contract to maintain.

## 9. Nested Projections and Nullable Wrappers

Interface projections can be used recursively for nested properties. For example, a person has an address:

~~~java
public interface AddressView {

    String getCity();
}

public interface PersonAddressView {

    String getFirstName();

    AddressView getAddress();
}
~~~

When calling `getAddress()`, Spring Data retrieves the `address` property value from the target object and wraps it in the corresponding projection.

Using nested projections helps restrict the view at the property level. However, it does not mean an entity relationship is lazily loaded on demand as in some other ORMs. Spring Data JDBC reads aggregates according to its mapping; observe the actual SQL and data volume if a nested property is a collection or an entity stored in a separate table.

Projection getters can also use nullable wrappers such as `Optional<T>`:

~~~java
public interface PersonContactView {

    Optional<String> getEmail();
}
~~~

If the underlying value is `null`, the getter returns `Optional.empty()`; if a value is present, it returns `Optional.of(value)`.

Nullable wrappers help the read API express clearly that a property may be absent. They do not replace validation for required fields in the domain.

## 10. Projections Do Not Turn Expressions into SQL

Distinguish **SpEL in projections** from **SpEL in query strings**.

### 10.1. Projection Expressions

~~~java
@Value("#{target.firstName + ' ' + target.lastName}")
String getDisplayName();
~~~

This expression runs in the application when the projection accessor is invoked. It uses the `target` object and computes a display value. It is not sent to the database as an SQL expression.

### 10.2. SpEL Used as a Bind Parameter in `@Query`

~~~java
@Query("""
    SELECT *
    FROM people
    WHERE id = :#{#person.id}
    """)
Person findForPerson(PersonRef person);
~~~

Here `:#{#person.id}` is evaluated to obtain a bind parameter value. The SQL executes with that parameter.

Spring Data JDBC also supports expressions that substitute part of the query string, such as a dynamic table name:

~~~java
@Query("SELECT * FROM #{tableName} WHERE id = :id")
Person findByDynamicTable(Long id);
~~~

This SQL-substitution form of expression is evaluated before the first execution; it fits cases needing dynamic table names and requires strict control over permitted values.

These cases serve different purposes:

| Expression | When and where evaluated | Effect |
|---|---|---|
| `@Value("#{target...}")` on projection | When calling accessor in application | Produces a presentation value |
| `:#{...}` in `@Query` | When preparing query parameters | Produces a bind value |
| `#{tableName}` in SQL | Before first query execution | Substitutes part of the SQL string |

Do not use projection expressions to replace filtering, joining, grouping, or aggregation that the database can perform more efficiently.

## 11. Processing Costs of Open Projections

Open projections provide flexibility, but carry multiple layers of cost.

### 11.1. Cost of Reading Data from the Database

Because SpEL can access any property on `target`, Spring Data cannot restrict query execution based on a fixed getter list as it does with closed projections.

This can increase:

- The number of columns read.
- ResultSet payload size.
- Cost of converting JDBC values to Java objects.
- Cost of constructing the aggregate and mapped components.
- Memory required to hold the result list.

If the projection only needs two properties, an open projection may read more broadly than necessary. Closed projections or DTOs are better when data reduction is the main goal.

### 11.2. Proxy Creation Cost

Interface projections require a proxy to forward method calls to the target object or evaluate expressions. Proxies decouple the view contract from the entity, but still incur object allocation and method dispatch overhead.

For a few records, this cost is usually negligible. For very large lists, measure total materialization time, object count, and memory rather than looking only at SQL time.

DTO projections avoid proxies and construct objects directly via constructors. That does not guarantee DTOs are always faster in every scenario, but it makes the mapping path simpler and more transparent.

### 11.3. SpEL Evaluation Cost

When the application calls an accessor annotated with `@Value`, Spring evaluates the expression to produce the return value.

If a serializer or application code calls the same getter multiple times, do not assume the value is cached. The longer the expression, the deeper the property access, or the more bean calls it makes, the higher the cost.

A simple example:

~~~java
@Value("#{target.firstName + ' ' + target.lastName}")
String getDisplayName();
~~~

is typically lighter than an expression with multiple branches, method calls, and nested object traversals.

### 11.4. Bean Invocation Cost

Beans can make expressions more maintainable, but the called methods still consume CPU and can add I/O if written carelessly.

Avoid these patterns:

- Querying a repository on every getter call.
- Calling an HTTP service to enrich a property for each projection.
- Reading files or accessing external systems from an expression.
- Executing business logic with side effects inside a presentation method.
- Repeating the same heavy calculation for each getter.

If data from another table is needed, design a query/read model that fetches data in batches or with appropriate joins. If external services must be called, handle them in the application/service layer through a controlled workflow.

### 11.5. Cost from Aggregates with Collections

An open projection can reference properties on the root or child components. In Spring Data JDBC, do not assume accessing a nested getter triggers JPA-style lazy loading. Aggregate loading and SQL for loading collections depend on the mapping, query method, and Spring Data JDBC strategy.

If an expression reads a collection to compute a sum or build a string, the application may have to hold all of those elements in memory. For lists of many aggregates, collection loading cost can far exceed SpEL cost.

## 12. Comparing Three Ways to Build a Display Name

Suppose `Person` has `firstName`, `lastName`, and `email`.

### Approach A — Closed Projection with Default Method

~~~java
public interface PersonNameView {

    String getFirstName();

    String getLastName();

    default String getDisplayName() {
        return getFirstName() + " " + getLastName();
    }
}
~~~

Dependencies are explicitly declared. This is a good choice for small calculations.

### Approach B — Open Projection with SpEL

~~~java
public interface PersonDisplayView {

    @Value("#{target.firstName + ' ' + target.lastName}")
    String getDisplayName();

    @Value("#{target.email != null ? target.email : 'No email'}")
    String getEmailLabel();
}
~~~

Easy to write and flexible. However, the expression can access the entire target, so it lacks the query optimization capability of closed projections.

### Approach C — DTO

~~~java
public record PersonCard(
        UUID id,
        String firstName,
        String lastName,
        String email
) {
    public String displayName() {
        return firstName + " " + lastName;
    }
}
~~~

A DTO makes the data shape explicit and needs no proxy. Suitable for API responses or read models with a stable structure.

| Criterion | Closed + default | Open + SpEL | DTO |
|---|---|---|---|
| Computation | Java default method | SpEL | Java constructor/method |
| Target access | Through declared getters | Can read any property | No target proxy |
| Query optimization | Can restrict by getters when module supports | Cannot optimize on narrow getter set | Can optimize by constructor properties when store supports |
| Proxy | Yes | Yes | No |
| Complex logic | Move to bean/service | Move to bean | Move to mapper/service |
| Compile-time safety | Good | Expression is a string | Good |

## 13. Choosing a Projection by Purpose

| Need | Suitable Choice |
|---|---|
| Only a few existing properties needed | Closed interface projection |
| Combine a few declared properties | Closed projection with default method |
| Small, flexible expression based on target | Open projection with `@Value` |
| Multi-step yet lightweight presentation logic | Invoke a bean from SpEL or handle in service |
| Stable API response without proxies | DTO/record projection |
| Different views for the same search condition | Dynamic projection |
| Aggregation, joins, filtering, or heavy calculations | SQL/read model/DTO query |
| Modify data and protect invariants | Load aggregate root, call domain method, save repository |

An open projection is not always wrong. It is a reasonable tool when the expression is small and reading the target fits within the performance budget. Problems arise when expressions are used indiscriminately on large lists or when accessors become call sites for external services.

## 14. Limitations When Using Projections in Repositories

### 14.1. Do Not Turn Base CRUD Methods into Projections by Changing Return Type

Built-in methods of `CrudRepository`, such as `findById`, are still processed according to the base contract when overridden. Simply changing the return type to an interface projection does not guarantee Spring Data will create a new query method.

Declare a separate query method, for example:

~~~java
List<PersonNameView> findByLastName(String lastName);
~~~

### 14.2. Accessor Names Must Match Properties

With closed projections:

~~~java
String getFirstName();
String getLastName();
~~~

the properties must exist on the aggregate root with matching names. If a domain property is renamed, update the projection and related query methods.

### 14.3. Class-Based Projections Need an Unambiguous Constructor

DTO projections need a constructor so Spring Data can resolve the input properties. If a class has multiple constructors, mark the desired constructor with `@PersistenceCreator` when necessary.

### 14.4. Nested Projections Do Not Mean Nested SQL Projections

Nested projections describe how properties are wrapped into another view. They do not guarantee the database reads only part of a child table or generates a single JOIN. With Spring Data JDBC, examine separately how aggregate mapping and collection loading behave.

### 14.5. Verify the Query Path in Use

Derived queries, custom `@Query`, DTOs, and interface projections can go through different mapping paths. If you choose a projection to reduce columns or SQL, measure the exact repository method the application will call.

## 15. Measuring Costs with SQL Logs and Benchmarks

Do not conclude a projection is fast simply because its interface has few getters. Compare return strategies using the same dataset and query conditions.

You can enable logging in `application.yml`:

~~~yaml
logging:
  level:
    org.springframework.jdbc.core.JdbcTemplate: DEBUG
    org.springframework.jdbc.core.StatementCreatorUtils: TRACE
~~~

TRACE can reveal bind parameters; enable it only in test environments and avoid logging sensitive information in production.

### 15.1. Comparing Methods

Prepare repository methods:

~~~java
List<Person> findByLastName(String lastName);

List<PersonNameView> findNamesByLastName(String lastName);

List<PersonDisplayView> findDisplayByLastName(String lastName);

List<PersonCard> findCardsByLastName(String lastName);
~~~

Create fixtures with the same number of people, string lengths, and value distributions. Then measure:

- Number of SQL statements.
- Selected columns.
- ResultSet row count.
- Database execution time.
- Object/proxy construction time.
- Getter invocation and response serialization time.
- Heap allocation and garbage collection for large lists.

Method names are examples; the portion after `By` must still describe a valid property that Spring Data can parse.

### 15.2. Do Not Benchmark with Only a Single Getter

If you only measure the repository call and discard the unused projection, the measurement may miss expression evaluation costs. Conversely, calling the same getter dozens of times may measure an access pattern unlike real serialization.

A benchmark should simulate the real usage flow:

~~~text
Repository query
      |
      v
Receive projection result
      |
      v
Read getters actually used by API
      |
      v
Serialize response
      |
      v
Measure total time and allocation
~~~

Repeat with representative record counts, such as 10, 100, 1,000, and expected load. Measure multiple times after warm-up and compare medians/percentiles rather than relying on a single run.

## 16. Workflow for Choosing and Implementing Open Projections

When adding a computed presentation property via expression:

**Step 1 — Identify input data.** List the properties the new value needs.

**Step 2 — Check if a closed projection suffices.** If the calculation only uses declared getters, prefer a default method.

**Step 3 — Check if SpEL is truly needed.** If so, keep the expression short, pure, and free of side effects.

**Step 4 — Extract complex logic.** Use a Spring bean or service method to keep Java code testable; do not query the database from each getter.

**Step 5 — Consider data scale.** Open projections on large lists can increase property-reading, materialization, and evaluation costs.

**Step 6 — Choose DTO/read query when data optimization matters.** If the screen only needs certain columns, let the query select that exact data.

**Step 7 — Verify SQL and serialization.** Confirm columns, statements, query counts, and actual getters invoked.

**Step 8 — Test nulls and edge data.** Expressions must handle nullable properties; SpEL errors may surface only when the getter is called.

~~~text
Need to display a new value
          |
          v
Are input properties clear?
          |
          v
Uses only declared getters?
        /   \
      Yes    No
      |       |
      v       v
Closed +    Really need SpEL?
default       |
method       / \
           Yes  No
           |     |
           v     v
       Open @Value  DTO/mapper/service
           |
           v
    Short, pure expression?
           |
           v
    Measure SQL + proxy + evaluation
           |
           v
    Performant enough for data scale?
~~~

## 17. Self-Check Scenarios

**Scenario A — Concatenating Full Name**

A projection needs to join `firstName` and `lastName`. Is `@Value` required?

**Hint:** No. A closed projection with a default method is simpler and keeps dependencies explicit.

**Scenario B — Expression Reading Multiple Properties**

An open projection has `@Value("#{target.firstName + target.lastName + target.email}")`. Can Spring Data guarantee only these three columns are selected?

**Hint:** Query execution cannot be optimized around a narrow property set like a closed projection because the expression could access any property of `target`.

**Scenario C — Calling a Repository from a Bean**

A bean is invoked by a projection expression and queries the database again for each person. With 500 results, what can happen?

**Hint:** 500 bean calls can trigger 500 additional queries, causing an N+1 problem. Batch the data or design an appropriate read query.

**Scenario D — Stable API Response**

An endpoint always returns `id`, `firstName`, `lastName`, and `email`. Which option makes the data contract easiest to control?

**Hint:** A DTO/record projection is usually clearer because it needs no proxy and the constructor defines the fields.

**Scenario E — Projection with Nested Address**

A projection returns `AddressView getAddress()`. Can you assume Spring Data JDBC only loads the address when the getter is invoked?

**Hint:** Do not assume JPA-style lazy loading. Check how the property is mapped and inspect the actual SQL.

**Scenario F — Expression Using `args`**

A projection has `getGreeting(String prefix)` and the expression reads `args[0]`. Where does this value come from?

**Hint:** From the argument passed to the projection accessor call itself.

## 18. Key Takeaways

| Concept | Role |
|---|---|
| Projection | Restricted view over aggregate data |
| Interface projection | Proxy forwarding accessors to the target object |
| Closed projection | Getters matching known properties |
| Open projection | Uses `@Value` and SpEL to compute values |
| `target` | Domain object backing the projection |
| `args` | Arguments of the projection method call |
| Default method | Simple Java logic based on declared getters |
| Spring bean in SpEL | Decouples complex logic from expressions |
| DTO projection | Constructor-based object without proxy creation |
| Dynamic projection | Selects result type using `Class<T>` |
| Nullable wrapper | Represents properties that may be null |
| Query optimization | Closed projections can help restrict data when supported by module |
| Processing cost | SQL, mapping, proxy, expression, object graph, and serialization |

**Open projections should be used for small, pure, easy-to-understand presentation calculations.** When merely combining getters, prefer default methods in closed projections. When a stable data contract is needed, choose a DTO. When using SpEL, remember that `target` can access the entire aggregate, so Spring Data cannot optimize the query around a narrow property set. Measure SQL, object construction costs, and expression costs at realistic data scales.

## References

- [Spring Data Relational — Projections](https://docs.spring.io/spring-data/relational/reference/repositories/projections.html): interface projections, closed/open projections, `@Value`, default methods, nullable wrappers, DTOs, and dynamic projections.
- [Spring Data Relational — JDBC Query Methods](https://docs.spring.io/spring-data/relational/reference/jdbc/query-methods.html): query methods, SpEL in queries, named parameters, and mapping.
- [Spring Data Relational — JDBC Mapping](https://docs.spring.io/spring-data/relational/reference/jdbc/mapping.html): how Spring Data JDBC maps aggregates and related properties.

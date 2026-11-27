# Open Interface Projections with Expressions and Optimization Trade-offs

Spring Data JPA allows repositories to return interface projections so applications read only the required attributes of an entity. With an interface projection, Spring creates a proxy implementing the interface and provides values for the getters from the query data.

There are two important types of interface projections:

- **Closed projection**: the interface only declares getters corresponding to attributes of the aggregate/entity. Spring knows the exact attributes required and can optimize the query to fetch only that data.
- **Open projection**: the interface has **@Value** expressions using Spring Expression Language (SpEL), typically accessing the source object via the **target** variable. Because the expression can read any attribute of the source object, Spring cannot determine with certainty the minimal set of columns to fetch and cannot apply the same query optimization as a closed projection.

Open projections are flexible for building presentation values, but come with trade-offs in optimization, complexity, and potential association loading. This lesson explains how to use **target**, **args**, beans in SpEL, interface default methods, nested projections, and how to choose between projections and DTOs.

**Example prerequisites:** the code snippets use Spring Boot 3.x, Java 17 or later, and Spring Data JPA. The application requires **spring-boot-starter-data-jpa**, a JDBC driver, a DataSource, and a matching schema. The snippets are parts of a Spring Boot application, not standalone programs that can be run with **javac** alone.

## 1. What Is a Projection?

An entity typically describes the full persistent state of an object. However, a read use case may only need a subset of data. For example, a user list screen only needs the display name and email, not every attribute of the entity.

A projection is a result type representing the subset of data to read:

~~~text
Person entity
+ id
+ firstname
+ lastname
+ email
+ phone
+ address
+ createdAt
+ ...
       |
       | repository query
       v
PersonName projection
+ firstname
+ lastname
~~~

A repository can declare:

~~~java
public interface PersonRepository
        extends JpaRepository<Person, Long> {

    List<PersonName> findByLastname(String lastname);
}
~~~

Projection interface:

~~~java
public interface PersonName {
    String getFirstname();
    String getLastname();
}
~~~

When the repository is called, Spring Data creates a projection proxy for each result. Calling code uses the interface without writing an implementation class manually.

Projections are typically well suited for read models: lists, summary detail pages, small reports, or data serving an API. If you need to update an entity, load the appropriate entity inside a transaction and apply business rules to that entity.

## 2. Closed Interface Projections

A projection is considered closed when its accessors correspond directly to attributes of the aggregate root/entity and do not use open expressions to compute values from the source object.

Entity example:

~~~java
@Entity
@Table(name = "people")
public class Person {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String firstname;

    @Column(nullable = false)
    private String lastname;

    @Column(nullable = false)
    private String email;

    private String phone;

    protected Person() {
    }

    public Person(String firstname, String lastname, String email) {
        this.firstname = firstname;
        this.lastname = lastname;
        this.email = email;
    }

    public Long getId() {
        return id;
    }

    public String getFirstname() {
        return firstname;
    }

    public String getLastname() {
        return lastname;
    }

    public String getEmail() {
        return email;
    }

    public String getPhone() {
        return phone;
    }
}
~~~

Projection requiring only name and email:

~~~java
public interface PersonContact {

    String getFirstname();

    String getLastname();

    String getEmail();
}
~~~

Repository:

~~~java
public interface PersonRepository
        extends JpaRepository<Person, Long> {

    List<PersonContact> findByLastname(String lastname);
}
~~~

Spring Data knows the projection only needs the **firstname**, **lastname**, and **email** attributes. With a closed projection, Spring Data can optimize query execution by restricting the data fetched instead of loading the entire entity, depending on the query type, store module, and provider capabilities.

This can reduce data transferred from the database, entity materialization overhead, and unnecessary data. However, this is a framework optimization capability, not a guarantee that every query will always emit only those three columns in every scenario. Inspect the actual SQL.

## 3. Open Interface Projections and @Value

Open projections allow computing values using SpEL via **@Value**. The expression can access the source object using the **target** variable.

Example building a full name:

~~~java
import org.springframework.beans.factory.annotation.Value;

public interface PersonDisplay {

    @Value("#{target.firstname + ' ' + target.lastname}")
    String getFullName();

    String getEmail();
}
~~~

In the expression:

- **target** is the source object being used to create the projection.
- **target.firstname** accesses the `firstname` attribute of the source object.
- **target.lastname** accesses the `lastname` attribute.
- The expression result is returned through the **getFullName()** getter.

Repository:

~~~java
public interface PersonRepository
        extends JpaRepository<Person, Long> {

    List<PersonDisplay> findByLastname(String lastname);
}
~~~

Usage:

~~~java
List<PersonDisplay> people = repository.findByLastname("Nguyen");

for (PersonDisplay person : people) {
    System.out.println(person.getFullName());
    System.out.println(person.getEmail());
}
~~~

Because **getFullName()** uses SpEL on the source object, this is an open projection. Spring cannot know in advance which attributes of `target` the expression might access. Therefore, the framework cannot safely apply the same column-selection optimization as a closed projection.

Open projections are useful when the presentation expression is concise and genuinely needs to read the source object. If you only need to combine existing getters, an interface default method is usually a lighter choice.

## 4. The args Variable in SpEL

SpEL in an open projection can access arguments passed into the projection method via the **args** variable.

Example:

~~~java
import org.springframework.beans.factory.annotation.Value;

public interface PersonGreeting {

    @Value("#{args[0] + ' ' + target.firstname + '!'}")
    String getGreeting(String prefix);
}
~~~

Usage:

~~~java
PersonGreeting person = repository.findGreetingById(id);

String greeting = person.getGreeting("Hello");
~~~

If `firstname` is **An**, the result may be:

~~~text
Hello An!
~~~

**args[0]** is the first argument passed to the **getGreeting** getter. If the method has multiple parameters, you can access **args[1]**, **args[2]**, and corresponding positions.

Do not use `args` as a way to pass arbitrary data into the database query. These are parameters of the projection method, used inside the expression computing the return value. If you need to filter data, pass parameters to the repository query method.

## 5. Calling Spring Beans from SpEL Expressions

Open projections can also invoke a Spring bean by bean name. This is useful when formatting logic needs to be reused or has more rules than a short expression.

Formatting bean:

~~~java
@Component("personNameFormatter")
public class PersonNameFormatter {

    public String format(Person person) {
        return person.getLastname() + ", " + person.getFirstname();
    }
}
~~~

Projection:

~~~java
public interface PersonLabel {

    @Value("#{@personNameFormatter.format(target)}")
    String getLabel();

    String getEmail();
}
~~~

The expression **@personNameFormatter** references the bean with the matching name in the Spring `ApplicationContext`. **target** is passed into the `format` method.

This helps reuse formatters, but the projection remains an open projection. The expression can access the source object, so Spring cannot infer the exact set of attributes to fetch and optimize like a closed projection.

Keep formatters focused on data presentation. Do not put database queries, external service calls, or complex business rules in SpEL; that logic belongs in a service or a dedicated component.

## 6. Use Default Methods Instead of SpEL When Possible

If the computed value relies only on getters already declared in the projection, you can use a Java interface default method.

~~~java
public interface PersonName {

    String getFirstname();

    String getLastname();

    default String getFullName() {
        return getFirstname() + " " + getLastname();
    }
}
~~~

This remains a closed projection because the attributes to fetch are clearly defined by the two getters `firstname` and `lastname`. The **getFullName()** method only combines results from those accessors; it does not need arbitrary access to the source object.

Comparison:

| Approach | Example | Characteristics |
|---|---|---|
| Closed projection | Getters **getFirstname()**, **getLastname()** | Spring knows the required attributes |
| Default method | Combine two getters in the interface | Keeps the projection closed if only declared accessors are used |
| Open projection | **@Value("#{target.firstname + ...}")** | Can access target, restricting attribute selection optimization |
| Bean in SpEL | **@Value("#{@formatter.format(target)}")** | Reuses a bean, but is still an open projection |

If you only need string concatenation, simple labels, or derived values from a few getters, prefer a default method. Use SpEL when you deliberately need access to `target` or a bean.

## 7. Nested Interface Projections

A projection can nest another projection to represent a related attribute.

Suppose `Person` has a relationship to `Address`:

~~~java
@Entity
public class Address {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String city;

    private String country;

    protected Address() {
    }

    public String getCity() {
        return city;
    }

    public String getCountry() {
        return country;
    }
}
~~~

In `Person`:

~~~java
@ManyToOne(fetch = FetchType.LAZY)
@JoinColumn(name = "address_id")
private Address address;
~~~

Nested projection:

~~~java
public interface AddressSummary {

    String getCity();

    String getCountry();
}
~~~

~~~java
public interface PersonWithAddress {

    String getFirstname();

    String getLastname();

    AddressSummary getAddress();
}
~~~

Repository:

~~~java
List<PersonWithAddress> findByLastname(String lastname);
~~~

When **getAddress()** is called, Spring Data creates a projection for the `Address` attribute as supported by nested projections.

However, understand a trade-off: a nested property resolved through a join can cause the entire related attribute to be materialized. Do not assume a nested projection always generates SQL selecting only the `city` and `country` columns. Exact behavior depends on how the query is generated, the mapping, and the provider.

If the query requires exact column control across both tables, consider a JPQL DTO constructor expression or an explicit projection query. Check the SQL to see how the association is being joined/loaded.

## 8. How Do Open Projections Affect Query Optimization?

Closed projections tell the framework the exact set of attributes needed. Open projections do not provide that guarantee because SpEL can access any attribute of `target`.

Closed example:

~~~java
public interface PersonSummary {
    String getFirstname();
    String getLastname();
}
~~~

Open example:

~~~java
public interface PersonSummaryOpen {

    @Value("#{target.firstname + ' ' + target.lastname + ' (' + target.email + ')'}")
    String getLabel();
}
~~~

With the closed projection, Spring can limit the fetched data to `firstname` and `lastname`. With the open projection, the expression also reads `email` and, in principle, could read any other attribute. Therefore, Spring cannot apply the same column-selection optimization.

Potential consequences:

- More columns are fetched than needed for actual display.
- The entity or source object may be materialized.
- SpEL accessing a LAZY association can trigger additional queries.
- A simple expression can hide data-access cost.
- Changing an expression can alter the data that must be loaded without showing up in the getter signature.

Open projections are not inherently slow in every case. If row counts are small, expressions are simple, and the SQL is appropriate, the cost may be acceptable. However, for large list queries or APIs with strict performance requirements, measure and prefer closed projections or DTOs with explicit selects.

## 9. Avoiding N+1 When Expressions Access Associations

A SpEL expression can access a relationship:

~~~java
public interface PersonLocation {

    @Value("#{target.firstname + ' - ' + target.address.city}")
    String getLocationLabel();
}
~~~

If **address** is LAZY and the list contains many `Person` rows with different `Address` entities, evaluating the expression can trigger an additional query as each getter is called. This is a path that can lead to N+1 queries.

How to handle it depends on the use case:

- Use a closed projection if only known simple attributes are needed.
- Use a JPQL query with a join and a DTO projection to explicitly select the needed columns.
- Use **@EntityGraph** when you need the entity along with a specific association.
- If using an open projection, inspect the SQL and query count on a realistic dataset size.

Example DTO projection with JPQL:

~~~java
public record PersonLocationView(
    String firstname,
    String city
) {
}
~~~

~~~java
@Query("""
    select new com.example.people.PersonLocationView(
        p.firstname,
        a.city
    )
    from Person p
    left join p.address a
    where p.lastname = :lastname
    """)
List<PersonLocationView> findLocations(
    @Param("lastname") String lastname
);
~~~

A DTO constructor expression makes the fetched data and the join explicit. It is usually an easy-to-control choice when results are needed from multiple entities.

## 10. Interface Projections with @Query and Aliases

With custom JPQL, you can return an interface projection. Aliases in the `SELECT` clause should match the property names required by the projection getters.

Projection:

~~~java
public interface PersonContact {

    String getFirstname();

    String getEmail();
}
~~~

Repository:

~~~java
@Query("""
    select p.firstname as firstname,
           p.email as email
    from Person p
    where p.lastname = :lastname
    """)
List<PersonContact> findContactsByLastname(
    @Param("lastname") String lastname
);
~~~

The alias **firstname** maps to **getFirstname()**, and the alias **email** maps to **getEmail()**. If an alias is wrong or mismatched, the projection value may not map as expected.

With a JPQL constructor expression for a DTO, constructor parameter order and types must match the `SELECT` expressions. With an interface projection, specify explicit aliases to avoid relying on hard-to-read inferred names.

## 11. Dynamic Projections

Spring Data JPA supports dynamic projections: a single repository method can return different projection types depending on the class passed at call time.

~~~java
public interface PersonRepository
        extends JpaRepository<Person, Long> {

    <T> List<T> findByLastname(String lastname, Class<T> type);
}
~~~

You can call:

~~~java
List<PersonName> names =
    repository.findByLastname("Nguyen", PersonName.class);

List<PersonContact> contacts =
    repository.findByLastname("Nguyen", PersonContact.class);

List<Person> entities =
    repository.findByLastname("Nguyen", Person.class);
~~~

Dynamic projections help reuse query conditions while choosing the result shape per use case.

Note that the **Class<T>** signature must match the generic return type so Spring recognizes it as a projection parameter. If the parameter is **Class<?>** or does not match the generic type, it may be treated as a regular query parameter depending on the method signature.

Dynamic projections do not eliminate the trade-offs between open and closed projections. If you pass an open projection, the optimization limitations of open projections still apply.

## 12. Comparing Interface Projections with DTO Projections

| Criterion | Interface projection | DTO/class-based projection |
|---|---|---|
| Declaration | Interface getters | Class or record |
| Mechanism | Projection proxy | DTO object instantiation |
| Computed values | Default methods or SpEL | Constructor, factory, or service mapping |
| Open projection | Can use SpEL and target | No open interface projection via this mechanism |
| Query optimization | Closed projection can restrict attributes | Query/constructor expression explicitly shows fields to fetch |
| Nested data | Supports nested interface projections | Nested DTOs or constructor mapping |
| Best suited for | Small, flexible read views with minimal boilerplate | APIs/reports needing clear structure, immutability, or multi-source joins |

Record DTO example:

~~~java
public record PersonContactDto(
    String firstname,
    String email
) {
}
~~~

Repository:

~~~java
@Query("""
    select new com.example.people.PersonContactDto(
        p.firstname,
        p.email
    )
    from Person p
    where p.lastname = :lastname
    """)
List<PersonContactDto> findContactDtos(
    @Param("lastname") String lastname
);
~~~

DTOs are generally suitable when you need a stable result contract, an explicit constructor, and strict control over retrieved data. Interface projections are suitable when you want to quickly define a read view using getters.

## 13. Limitations and Considerations When Using Open Projections

Before choosing an open projection, consider the following points:

1. **No column optimization like closed projections:** SpEL can access any attribute of `target`.
2. **May trigger LAZY loading:** accessing associations in expressions can fire additional queries.
3. **Logic is less visible from the signature:** getters can run computations or call beans, forcing readers to inspect the expression to understand data dependencies.
4. **Hard to test performance by checking results alone:** you must measure SQL query count and loaded rows.
5. **Not suitable for large business logic:** long expressions, complex branching, or external service calls should move to a dedicated service/formatter.
6. **Do not use as an updatable entity:** a projection is a read view; load a managed entity if you need to modify and save data.

Open projections are a data presentation tool. Keep expressions short and readable; if they start orchestrating multiple rules or accessing multiple associations, switch to a DTO/service.

## 14. Testing Projections and SQL

A test can verify that a projection returns the expected data:

~~~java
@DataJpaTest
class PersonProjectionTest {

    @Autowired
    private PersonRepository repository;

    @Autowired
    private TestEntityManager entityManager;

    @Test
    void returnsClosedProjection() {
        entityManager.persist(
            new Person("An", "Nguyen", "an@example.test")
        );
        entityManager.flush();
        entityManager.clear();

        List<PersonContact> result =
            repository.findByLastname("Nguyen");

        assertThat(result).hasSize(1);
        assertThat(result.get(0).getFirstname()).isEqualTo("An");
        assertThat(result.get(0).getEmail()).isEqualTo("an@example.test");
    }
}
~~~

You can write a similar test for an open projection:

~~~java
@Test
void computesOpenProjectionValue() {
    PersonDisplay result =
        repository.findDisplayById(personId).orElseThrow();

    assertThat(result.getFullName()).isEqualTo("An Nguyen");
}
~~~

To verify optimization, enable SQL logging in the test environment:

~~~yaml
logging:
  level:
    org.hibernate.SQL: DEBUG
~~~

Compare the SQL of closed and open projections on the same dataset. Check the number of selected columns, the number of queries when getters are called, whether associations are loaded additionally, and behavior as data grows. Results depend on query shape, Spring Data version, Hibernate, and the database; do not draw performance conclusions from the projection name alone.

## 15. Common Pitfalls

| Symptom | Cause | How to fix |
|---|---|---|
| Projection getter returns null | Getter name does not match property or alias | Check property name and SELECT alias |
| Open projection loads many columns | SpEL accesses target so framework does not know minimal field set | Use a closed projection or DTO |
| Calling getter triggers many SQL queries | SpEL accesses a LAZY association | Use a join/DTO or appropriate fetch plan |
| Default method is not computed properly | Depends on wrong getter or property name mismatch | Check accessors and test the projection |
| SpEL bean not found | Wrong bean name or component configuration | Check bean name and `ApplicationContext` |
| Nested projection loads large data | Nested property is materialized via join | Inspect SQL and use a DTO when explicit column selection is needed |
| Dynamic projection not recognized | Generic `Class` signature does not match return type | Use **<T> List<T> ... Class<T>** |
| Using projection to update an entity | Confusing a read view with a managed entity | Load the entity in a transaction and update it |
| Query interface projection maps incorrectly | Alias does not match getter | Set alias matching projection property name |

## 16. Checklist for Choosing a Projection

- [ ] Determine whether the use case is read-only or needs to update an entity.
- [ ] Use a closed projection when getters map directly to the required attributes.
- [ ] Use a default method when you only need to combine declared getters.
- [ ] Use an open projection only when SpEL access to `target`, `args`, or beans is genuinely needed.
- [ ] Keep SpEL expressions short and free of complex business logic.
- [ ] Avoid accessing LAZY associations in open projections without checking the SQL count.
- [ ] Use nested projections deliberately and inspect join behavior.
- [ ] Declare explicit aliases when using interface projections with **@Query**.
- [ ] Use dynamic projections when multiple use cases need different result shapes.
- [ ] Use DTOs/records when explicit control over columns, joins, and result structure is needed.
- [ ] Test results and SQL on the actual database/provider.

## 17. Conclusion

Closed interface projections declare only the attributes to read, letting Spring Data know the required dataset and potentially optimize the query. Open interface projections use **@Value** with SpEL, allowing access to **target**, **args** parameters, or Spring beans to compute values, but because expressions can read any attribute, they do not provide the same column-selection optimization.

If you only need to combine getters, use default methods to keep the projection closed. If you need flexible expressions, use open projections while keeping logic brief and measuring SQL. When you need results from multiple associations or want exact control over returned data, DTO/record projections are usually clearer and easier to optimize.

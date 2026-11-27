# Computed Properties with @Value and SpEL Expressions

In Spring Data REST, projections let you define how an entity is presented to clients. Beyond selecting existing properties, a projection interface can also provide computed properties using the @Value annotation and SpEL (Spring Expression Language) expressions.

For example, a Customer entity stores firstName and lastName separately, but the API can additionally return a displayName combined from those two fields. displayName does not need to be a database column; Spring Data computes the value from the target object when creating the projection.

## 1. What is a computed property in a projection?

A projection interface describes the properties visible to clients in a representation. For standard getters, Spring Data reads the value from the corresponding property on the entity. For getters annotated with @Value, Spring evaluates the SpEL expression to produce the return value.

Example entity:

~~~java
@Entity
public class Customer {

    @Id
    @GeneratedValue
    private Long id;

    private String firstName;
    private String lastName;
    private Integer age;
    private boolean active;

    // getters and setters
}
~~~

Suppose we want the API to provide displayName and statusLabel even though the entity does not declare those two properties:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.data.rest.core.config.Projection;

@Projection(name = "customerSummary", types = Customer.class)
public interface CustomerSummary {

    String getFirstName();

    String getLastName();

    @Value("#{target.firstName + ' ' + (target.lastName ?: '')}")
    String getDisplayName();

    @Value("#{target.active ? 'Active' : 'Inactive'}")
    String getStatusLabel();
}
~~~

In this example:

- getFirstName() and getLastName() read existing properties on Customer.
- getDisplayName() concatenates the first and last name into a single string.
- getStatusLabel() converts the boolean active value into a human-readable label.
- target is the Customer object currently being presented by the projection.

Getters defined by @Value are computed properties. They are calculated from the target object when the projection is used; they do not create new columns and do not write computed values back to the database.

## 2. Understanding target in SpEL expressions

In a projection's SpEL expression, target refers to the source object wrapped by the projection. You can access entity properties using property syntax:

~~~java
@Value("#{target.firstName}")
String getFirstNameFromTarget();
~~~

This expression is equivalent to reading Customer's firstName getter. When combining multiple properties, you can use string concatenation operators:

~~~java
@Value("#{target.firstName + ' ' + target.lastName}")
String getFullName();
~~~

If lastName can be null, the expression should handle that case. SpEL supports the Elvis operator:

~~~java
@Value("#{target.firstName + ' ' + (target.lastName ?: '')}")
String getDisplayName();
~~~

The ?: operator uses the right-hand value when the left-hand expression is null. If your domain has more complex rules for handling empty strings or missing names, express those rules clearly or move the logic into a dedicated bean.

SpEL also supports conditional (ternary) operators:

~~~java
@Value("#{target.age >= 18 ? 'Adult' : 'Minor'}")
String getAgeGroup();
~~~

The expression reads age, compares it with 18, and returns one of the two labels. The returned value type must be compatible with the getter's return type; the example above returns a String, so the getter declares String.

## 3. Exposing projections in Spring Data REST

Spring Data REST can discover projections annotated with @Projection if the interface resides in the domain type's package or a sub-package according to the framework's projection lookup rules.

Example repository:

~~~java
@RepositoryRestResource(path = "customers")
public interface CustomerRepository
        extends JpaRepository<Customer, Long> {
}
~~~

Suppose CustomerSummary is placed in the appropriate package and has the projection name customerSummary. Clients can request the projection when reading a collection or item:

~~~http
GET /api/customers?projection=customerSummary
~~~

Or:

~~~http
GET /api/customers/42?projection=customerSummary
~~~

The response will use the projection structure instead of the entity's default representation. Illustrative example:

~~~json
{
  "firstName": "An",
  "lastName": "Nguyen",
  "displayName": "An Nguyen",
  "statusLabel": "Active",
  "_links": {
    "self": {
      "href": "http://localhost:8080/api/customers/42"
    }
  }
}
~~~

Specific links and HAL structure also depend on Spring Data REST configuration, but the displayName and statusLabel properties come from the SpEL expressions in the projection.

If the projection does not appear, check the name in @Projection, the package containing the interface, the domain types declared in types, and how the client passes the projection parameter.

## 4. Using excerptProjection as the default projection for collections

If you want a collection resource to use a projection as its default excerpt, you can declare excerptProjection on the repository:

~~~java
@RepositoryRestResource(
    path = "customers",
    excerptProjection = CustomerSummary.class
)
public interface CustomerRepository
        extends JpaRepository<Customer, Long> {
}
~~~

An excerpt projection is used to present embedded items in a collection resource. This helps the collection return a compact and consistent representation without clients having to pass projection every time.

Distinguish between an excerpt projection and explicitly selecting a projection via the projection parameter. excerptProjection sets the default representation for items embedded in a collection; clients can still request a different projection if that projection is exposed and allowed by configuration.

Avoid putting too much data or heavy computation into an excerpt projection for large collections, because expressions may be evaluated for every returned item.

## 5. Invoking Spring beans from SpEL expressions

In addition to reading target properties, SpEL can invoke Spring beans by bean name. This is useful when computation logic requires a formatter or specialized component.

Example bean:

~~~java
@Component("customerLabelFormatter")
public class CustomerLabelFormatter {

    public String format(Customer customer) {
        return customer.getFirstName() + " " + customer.getLastName();
    }
}
~~~

The projection can call that bean:

~~~java
@Value("#{@customerLabelFormatter.format(target)}")
String getDisplayName();
~~~

In this expression:

- @customerLabelFormatter references the bean by name in the Spring context.
- format(target) invokes the bean method and passes the source entity.
- The returned result is used as the value of getDisplayName().

This separates formatting logic from the projection interface and makes it reusable. However, because the bean is invoked while building the representation, the method should be deterministic, fast, and free of side effects. Avoid calling remote services, writing data, or performing expensive operations inside projection getters.

For complex business logic requiring transactions, permission checks, or additional data queries, the service layer is usually a better fit. Projections should focus on shaping output data.

## 6. Open projections and their impact on query optimization

Projections that use only regular accessors, such as getFirstName() and getLastName(), are commonly called closed projections. Spring Data knows exactly which properties are required and in some cases can optimize queries to fetch only the necessary fields.

When using @Value to compute a property, the projection becomes an open projection. SpEL can access any property on target, so Spring Data cannot always determine upfront all the data needed to compute the result. Opportunities to optimize by selecting only used columns may be limited.

Example:

~~~java
public interface CustomerNameView {

    String getFirstName();

    String getLastName();
}
~~~

This is a closed projection because it only requests two known properties.

Meanwhile:

~~~java
public interface CustomerDisplayView {

    @Value("#{target.firstName + ' ' + target.lastName}")
    String getDisplayName();
}
~~~

is an open projection because the SpEL expression is evaluated against target. When using JPA, do not assume the query selects only the two columns firstName and lastName; data retrieval depends on how Spring Data builds the query and how the projection is used.

If you need query optimization for large datasets, consider DTO/class-based projections or queries that return only the required columns. Use @Value when the benefit of computed properties in the representation outweighs query optimization limitations.

## 7. Accessing relationships and lazy loading issues

SpEL can access nested properties on target. For example, if Customer has a relationship with Address:

~~~java
@Value("#{target.address.city}")
String getCity();
~~~

This expression reads city from Address. However, if address is a lazy relationship, evaluating the getter may trigger an additional query when creating the representation.

If the projection is used for many customers in a collection, accessing a lazy relationship for each item can cause N+1 queries. With expressions that call beans or iterate over collections, the cost can be even higher if each evaluation triggers a separate query.

Some precautions:

- Only access relationships truly needed for the response.
- Define fetch strategies and queries suited to how the projection is used.
- Monitor SQL when returning large collections.
- Avoid repeatedly calling repositories from SpEL or formatters for each entity.
- For complex aggregated data, consider query projections or a service creating controlled DTOs.

SpEL makes expressions concise, but it does not make data access free. Every property or method invoked can still carry runtime cost.

## 8. Limitations and security of computed properties

A computed property is only a way to produce a representation. It is not an authorization mechanism and does not guarantee that other entity fields are protected across all endpoints.

If Customer contains sensitive information such as personal email, phone number, or internal data, define projections containing only the fields allowed to be exposed. At the same time, control other repository resources, other projections, and custom endpoints that can return the same entity.

Do not use SpEL to bypass permission checks in a service. If a value may only be shown to a specific group of users, enforce permission checks in the security or service layer and design representations appropriate for each role.

Also avoid expressions that directly access secret fields simply because they exist on target. A public projection can turn a computed property into data sent to clients.

## 9. Common errors

| Symptom | Possible cause | Resolution |
|---|---|---|
| Computed property is missing | Projection was not discovered or client did not select the right projection name. | Check @Projection, package, types, and the projection parameter. |
| SpEL throws an error during serialization | Property does not exist, getter name is wrong, or expression is incompatible with the return type. | Check the property on target and the getter type. |
| Displayed value is null or contains the word null | Source property can be null and the expression does not handle that case. | Use Elvis or conditionals in SpEL. |
| Slow response when fetching collections | Expression accesses lazy relationships or calls a bean causing per-entity queries. | Reduce relationship access, optimize queries, or use DTO projections. |
| Cannot optimize query columns | @Value creates an open projection and Spring Data does not know all properties to read upfront. | Consider closed projections or DTO/class-based projections. |
| Unwanted data is exposed | Another projection or endpoint still returns the sensitive property. | Clearly define public representations and configure access control. |

## 10. Verification workflow

After declaring a projection with @Value, you can verify it in sequence:

1. Start the application and confirm the Customer repository is exposed by Spring Data REST.
2. Call GET /api/customers to inspect the collection resource.
3. Call GET /api/customers/42?projection=customerSummary.
4. Confirm displayName is concatenated from firstName and lastName.
5. Test with a Customer that has a null lastName to verify the Elvis expression.
6. Change active and confirm statusLabel reflects the corresponding state.
7. Call the collection with projection or excerptProjection and inspect the SQL query count.
8. If SpEL accesses relationships, check lazy loading and additional queries.
9. Test the representation using accounts with different permissions to ensure computed properties do not leak data outside policy.

@Value and SpEL let you add computed properties to projection interfaces without storing those values as separate columns. Use target to read source data, handle null explicitly, and keep expressions lightweight. When calculations become complex or significantly affect queries, move the logic to a dedicated bean, service, or DTO projection to control performance and access permissions.

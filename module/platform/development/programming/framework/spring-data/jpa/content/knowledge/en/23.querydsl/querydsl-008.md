# Binding Web Filters with QuerydslBinderCustomizer

## 1. Why Customize Binding?

Spring Data Web supports converting HTTP request query parameters into a Querydsl `Predicate`. When a controller accepts `Predicate` annotated with `@QuerydslPredicate`, users can submit filters via URL parameters without creating a separate repository method for every condition combination.

However, clients should not be allowed to filter on every Entity property by default. An Entity may contain a password hash, internal statuses, tenant ID, private notes, or fields that must not be exposed publicly. Furthermore, default matching behavior may not match the API's search requirements.

`QuerydslBinderCustomizer` lets you explicitly define:

- Which properties are allowed to receive filters from requests.
- How matching works per property or across an entire data type.
- Whether a single value is processed individually or multiple values are combined into an `IN` condition.
- Which properties must be excluded from binding.

The binder is the boundary converting HTTP filters into a predicate. It does not replace user authentication, authorization, business validation, or pagination limits.

## 2. Processing Flow from HTTP to Repository

Overall flow:

```text
HTTP query parameters
        |
        v
@QuerydslPredicate argument resolver
        |
        v
QuerydslBindings + QuerydslBinderCustomizer
        |
        v
Querydsl Predicate
        |
        v
QuerydslPredicateExecutor.findAll(predicate, pageable)
        |
        v
JPA provider -> SQL -> database
```

Spring Data Web reads query parameters, converts values to matching Java types, and uses Querydsl bindings to build the predicate. A repository implementing `QuerydslPredicateExecutor<T>` can execute that predicate.

`QuerydslBinderCustomizer` is usually implemented directly on the repository interface. Spring Data Web can locate the customizer on the repository corresponding to the domain type when building the predicate for `@QuerydslPredicate`.

## 3. Prerequisites

To use this mechanism, the project requires:

- Spring Data JPA and Spring Data Web support.
- Querydsl JPA and an annotation processor compatible with the JPA/provider version.
- Q classes generated from Entities, such as `QCustomer`.
- Repository extending `QuerydslPredicateExecutor<Customer>`.
- Spring MVC configured with the Querydsl predicate argument resolver; in plain Spring configuration, enable `@EnableSpringDataWebSupport`. With Spring Boot, verify your version's web auto-configuration to avoid registering duplicate resolvers.

The examples below use Jakarta Persistence as in Spring Boot 3+ applications. Spring Boot 2 projects use the `javax.persistence` namespace and require the corresponding Querydsl artifacts and annotation processor. Do not mix Querydsl Jakarta and Querydsl javax in the same build.

Q types such as `QCustomer` are generated during the build by the annotation processor. If the IDE reports that a Q class cannot be found, check annotation processing configuration, the generated sources set, and whether a build has run the processor.

## 4. Repository Implementing QuerydslBinderCustomizer

Suppose the `Customer` Entity has properties `id`, `firstName`, `lastName`, `email`, `status`, `tenantId`, and `passwordHash`.

```java
public interface CustomerRepository extends
        JpaRepository<Customer, Long>,
        QuerydslPredicateExecutor<Customer>,
        QuerydslBinderCustomizer<QCustomer> {

    @Override
    default void customize(QuerydslBindings bindings, QCustomer root) {
        // Allow only the fields listed below.
        bindings.excludeUnlistedProperties(true);
        bindings.including(
            root.firstName,
            root.lastName,
            root.email,
            root.status
        );

        // Search names by case-insensitive substring.
        bindings.bind(String.class)
            .first((StringPath path, String value) ->
                path.containsIgnoreCase(value)
            );

        // Email must match exactly.
        bindings.bind(root.email)
            .first((path, value) -> path.eq(value));

        // Multiple statuses become an IN condition.
        bindings.bind(root.status)
            .all((path, values) -> Optional.of(path.in(values)));
    }
}
```

This shows the core declaration; import the generated `QCustomer`, `QuerydslBindings`, `QuerydslBinderCustomizer`, `QuerydslPredicateExecutor`, `StringPath`, and `Optional` accordingly.

`customize` receives `bindings` and the Q root representing the Entity. `bindings.including(...)` combined with `excludeUnlistedProperties(true)` forms an allow-list: only `firstName`, `lastName`, `email`, and `status` can be used to build predicates from requests.

Type-level binding on `String.class` applies string search rules to allowed String properties. Property-level binding on `root.email` sets a specific rule for email. For instance, email uses equality while names use case-insensitive substring matching.

## 5. Allow-List vs. Deny-List

For public endpoints, an allow-list is usually safer and easier to control:

```java
bindings.excludeUnlistedProperties(true);
bindings.including(root.firstName, root.lastName, root.status);
```

When `excludeUnlistedProperties(true)` is enabled, only properties added to `including` are bound. Any new property added to the Entity later will not automatically become an HTTP filter.

If a project intentionally allows most properties and only needs to exclude a few fields, a deny-list can be used:

```java
bindings.excluding(root.passwordHash, root.tenantId);
```

A deny-list easily misses new fields as Entities evolve. For external APIs or Entities holding sensitive data, an allow-list makes reviewing the filter surface clearer. Never put `passwordHash`, tokens, internal roles, audit fields, or tenant IDs on an allow-list merely because they exist in the Q type.

The fact that a parameter is not bound does not mean the request is authorized. Security rules must still be enforced at the service/query layer.

## 6. Type-Level Binding vs. Property-Level Binding

There are two main customization scopes:

- **By type:** `bindings.bind(String.class)` applies the same rule to all bindable properties of that type.
- **By property:** `bindings.bind(root.email)` applies a dedicated rule to one specific property.

For example, name and city use substring matching, whereas email must match exactly:

```java
bindings.bind(String.class)
    .first((StringPath path, String value) -> path.containsIgnoreCase(value));

bindings.bind(root.email)
    .first((path, value) -> path.eq(value));
```

Property-level binding is useful when one field has different semantics from the rest. Avoid applying `containsIgnoreCase` to every String if some fields require exact matches, identifiers, statuses, or strings with specific business rules.

## 7. first and all: Single Value or Multiple Values?

`first(...)` builds a binding from the first value sent for a parameter. `all(...)` receives the collection of parameter values to construct a predicate from all values.

Example:

```java
bindings.bind(root.status)
    .all((path, values) -> Optional.of(path.in(values)));
```

Request:

```http
GET /customers?status=ACTIVE&status=VIP
```

The binding above generates an equivalent predicate:

```text
status IN (ACTIVE, VIP)
```

With `first`, subsequent repeated values do not participate in that binding. With `all`, clearly define the meaning of multiple values: `IN`, a range, or another expression. Do not use `all` just to collect values if business logic has no clear semantics for it.

If an endpoint accepts only a single value yet a request sends multiple values, decide explicitly how to handle it and test that behavior; do not leave behavior implicitly dependent on query parameter order.

## 8. Controller Example Receiving a Predicate from a Request

```java
@RestController
@RequestMapping("/customers")
public class CustomerController {

    private final CustomerRepository repository;

    public CustomerController(CustomerRepository repository) {
        this.repository = repository;
    }

    @GetMapping
    public Page<Customer> search(
            @QuerydslPredicate(root = Customer.class) Predicate predicate,
            @PageableDefault(size = 20, sort = "id") Pageable pageable) {
        return repository.findAll(predicate, pageable);
    }
}
```

`@QuerydslPredicate(root = Customer.class)` instructs Spring Data to build a predicate for domain type `Customer`. The repository has `QuerydslBinderCustomizer<QCustomer>` defining the bindings. `Pageable` is resolved separately by Spring Data Web; `page`, `size`, and `sort` are not ordinary filter properties in the Querydsl predicate.

Example request:

```http
GET /customers?firstName=an&email=lan%40example.com&status=ACTIVE&status=VIP&page=0&size=20&sort=id,desc
```

With the repository above:

- `firstName=an` searches names containing `an`, case-insensitively.
- `email=lan@example.com` searches for an exact email match.
- Two `status` values are combined using `IN`.
- `page`, `size`, and `sort` are used for pagination and sorting.

In real APIs, map Entities to DTOs instead of serializing the whole Entity. This avoids accidentally returning internal fields or triggering LAZY associations during serialization.

## 9. Enabling Spring Data Web Support

In plain Spring configurations, you can enable argument resolver support with:

```java
@Configuration
@EnableSpringDataWebSupport
public class WebConfiguration {
}
```

With Spring Boot, Spring Data Web is normally configured via auto-configuration when the required dependencies are present. Check the specific configuration of your Spring Boot/Spring Data version; do not manually register a second resolver if auto-configuration already provides it.

If `@QuerydslPredicate` fails to resolve and the controller reports a missing argument resolver error, check Spring Data Web dependencies, the Querydsl classpath, and web support configuration before modifying the repository customizer.

## 10. Binding Nested Properties and Associations

Q types can express nested property paths. For example, if `Customer` has an `address` association and `Address` has `city`, you can bind the corresponding path:

```java
bindings.including(root.address.city);
bindings.bind(root.address.city)
    .first((path, value) -> path.containsIgnoreCase(value));
```

This snippet assumes `address` is a persistent path generated in QCustomer, such as an `@Embedded` or validly mapped association. For associations, the query may generate a JOIN; check SQL and indexes if the filter is used frequently.

Be cautious when exposing paths across to-many associations like `orders.items.productCode`. Collection joins can multiply root rows, complicate queries, and affect counts/pagination. Do not bind deeply across the entire object graph just because the Q type allows traversing the path. For existence checks on collections, an explicit EXISTS predicate built in the service or custom repository is usually easier to control.

## 11. Binding Does Not Replace Validation

Query parameters are untrusted input. The Conversion Service can convert strings into enums, numbers, UUIDs, or dates/times; if conversion fails, the request may be rejected during argument resolution. However, successful type conversion does not mean the value is valid according to business rules.

You must still define:

- Maximum length of search strings.
- How many elements are accepted in a status list.
- Whether date ranges are valid and within allowed bounds.
- Maximum page size.
- Which sort properties are permitted.
- Which filters require special permissions.

For example, `status=UNKNOWN` may fail enum conversion. `size=100000` can trigger an excessively heavy query if uncapped. Validate inputs and normalize values at the web/service layer; do not expect QuerydslBinderCustomizer to handle all validation.

## 12. Binding Does Not Replace Authorization

An allow-list only determines which properties clients can use to filter. It does not ensure users only see data they are authorized to access.

For example, a multi-tenant system must always enforce the current tenant from the security context rather than accepting a client-supplied tenant ID as a security boundary:

```java
QCustomer customer = QCustomer.customer;

BooleanBuilder secured = new BooleanBuilder();
secured.and(requestPredicate);
secured.and(customer.tenantId.eq(currentTenantId));

Page<Customer> page = repository.findAll(secured, pageable);
```

This illustrates the service layer; `currentTenantId` must come from an authenticated principal/security context. Even when there is no request filter, the tenant condition must still apply. Never allow clients to bypass or override authorization predicates by sending extra parameters.

Do not bind `tenantId`, `ownerId`, `role`, `isAdmin`, or internal statuses as public filters and treat that as a protection mechanism. Authorization must be enforced server-side and tested independently.

## 13. Sort Is a Separate Input Surface

`Pageable` is resolved separately from the Querydsl Predicate. Therefore, `QuerydslBinderCustomizer` does not automatically restrict which fields clients can submit in `sort`.

Example:

```http
GET /customers?sort=createdAt,desc&sort=lastName,asc
```

Allow sorting only on properties supported by the API. You can validate/allow-list Sort in the service or configure `SortHandlerMethodArgumentResolver` appropriately. Never concatenate sort strings from requests directly into JPQL/native SQL, and do not pass client input to `JpaSort.unsafe`.

Add a unique key as a tie-breaker if pagination requires deterministic ordering, such as `createdAt DESC, id DESC`. Verify that sort properties are Java property names or query-supported aliases, not physical column names.

## 14. When to Use QuerydslBinderCustomizer and When Not To

| Case | Approach |
| --- | --- |
| GET search endpoint with a few simple filters, each mapping cleanly to a property | `@QuerydslPredicate` + `QuerydslBinderCustomizer` |
| Want contains-ignore-case for Strings or exact match for one field | Type-level / property-level binding |
| Allow multiple enum values and want `IN` | `all(...)` binding |
| Nested AND/OR conditions based on business rules | Build predicates in the service using Querydsl |
| Filters depending on user permissions, tenant, or viewable data | Combine server-side predicates in the service |
| Collection joins, aggregates, subqueries, or complex projections | Explicit Querydsl query / custom repository |
| Complex request structure requiring multi-field validation | Search DTO converted into a Querydsl predicate |

Binders are great for key/value HTTP filters. When an API has interdependent conditions, a request DTO with explicit validation where the service builds the predicate can be easier to govern than automatically turning every query parameter into a condition.

## 15. Testing Bindings

Write web-layer integration tests to confirm requests actually translate into the intended predicates. Cases to include:

1. Request with `firstName=an` matches case-insensitive substrings.
2. Request with `email=...` uses exact match per property binding.
3. `status=ACTIVE&status=VIP` produces an `IN` condition.
4. Parameters outside the allow-list are not included in the predicate.
5. Sensitive fields like `passwordHash` cannot be filtered via the endpoint.
6. Malformed enum/number/date values are handled as appropriate request errors.
7. Filters never override fixed tenant/owner conditions.
8. `page`, `size`, and `sort` are processed separately and bounded.
9. Association filters do not produce duplicate roots or wrong counts.
10. Results are mapped to DTOs and omit internal fields.

Unit-testing `customize(...)` directly can verify binding setup, but it does not replace MockMvc/WebTestClient integration tests, which are needed to verify that the argument resolver, conversion, and repository work together properly.

## 16. Common Pitfalls and Resolutions

**`@QuerydslPredicate` is not resolved.** Check Spring Data Web support, Querydsl dependencies, and argument resolver configuration.

**Repository does not apply the customizer.** Check that the repository implements `QuerydslBinderCustomizer<QCustomer>` with the matching domain root and the controller uses the right `root = Customer.class`.

**QCustomer does not exist.** Check the annotation processor and generated sources; never write Q types manually instead of code generation.

**Property is rejected or not filtering.** Check the allow-list, Java property name, Q path type, and query string conversion.

**String filter matches exactly instead of contains.** Check whether type-level/property-level binding is active and the request uses the exact parameter name.

**Multiple values only pick up a single value.** Use `all(...)` if business logic needs all values; `first(...)` processes only the first value.

**A newly added field is accidentally exposed.** Use `excludeUnlistedProperties(true)` and `including(...)` rather than relying solely on a deny-list.

**Slow query or wrong Page count after binding an association.** Check to-many JOINs, duplicate roots, counts, indexes, and consider EXISTS/custom predicates.

**Users can read another tenant's data.** A binder is not authorization. Add server-side tenant/owner predicates and test cross-tenant access.

**Unsafe or invalid Sort.** Allow-list Sort independently from filter bindings; never concatenate arbitrary sort strings.

## 17. Endpoint Design Checklist

- Enable Querydsl web support and confirm `@QuerydslPredicate` resolves.
- Repository extends `QuerydslPredicateExecutor<T>` and implements `QuerydslBinderCustomizer<QT>`.
- Use an allow-list for web-filterable properties.
- Customize String, enum, number, and multi-value matching per business semantics.
- Use `first` for single values and `all` for all values.
- Expose nested paths only after evaluating joins and cardinality.
- Keep tenant/owner/permission predicates server-side.
- Cap page size and allow-list sorting separately.
- Validate query parameter lengths, counts, and value domains.
- Map Entities to DTOs and test HTTP-to-predicate execution against an appropriate database.

`QuerydslBinderCustomizer` turns query parameters into filters with explicit rules. An allow-list keeps the search surface small, property/type bindings enforce proper matching behavior, while authorization and sorting must still be governed independently. Pairing the binder with server-side predicates and integration tests keeps search endpoints flexible without unintentionally widening query privileges.
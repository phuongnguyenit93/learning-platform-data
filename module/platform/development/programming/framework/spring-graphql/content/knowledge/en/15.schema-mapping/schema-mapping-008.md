# Mapping interface fields in Spring for GraphQL

A GraphQL interface describes a shared set of fields that multiple object types provide. When a client queries a field through an interface, the server still must resolve that field on the concrete object being returned. In Spring for GraphQL, `@SchemaMapping` can be used to implement a shared field at the interface level, allowing object types that implement the interface to reuse the same resolver.

Interface field mapping is especially useful when multiple object types share a computed property or one fetched from another service, such as `displayLabel`, `createdBy`, `permissions`, or `category`. Instead of writing the same resolver for each object type, you place the mapping on the interface and accept the source object through a Java interface or an appropriate common supertype.

After this lesson, you will be able to:

- Declare an interface and shared fields in the GraphQL SDL.
- Understand how object types implement an interface and inherit the field contract.
- Write a shared resolver with `@SchemaMapping` using the interface as `typeName`.
- Receive the source object via a Java interface or an appropriate parent type.
- Distinguish field mapping from `TypeResolver`.
- Handle field arguments, type-specific mappings, and runtime errors.
- Avoid N+1 when a shared field needs to load data from a service/repository.
- Test interface field mappings with `GraphQlTester`.

## 1. What is an interface field?

A GraphQL interface is an abstract type defining a set of fields that implementing object types must provide. For example, a catalog system can return both books and authors. Both have an ID and a display label, while their type-specific fields differ.

```graphql
interface CatalogEntry {
    id: ID!
    label: String!
}

type Book implements CatalogEntry {
    id: ID!
    label: String!
    title: String!
}

type Author implements CatalogEntry {
    id: ID!
    label: String!
    name: String!
}

type Query {
    catalogEntries: [CatalogEntry!]!
}
```

`CatalogEntry` exposes two shared fields: `id` and `label`. `Book` and `Author` must declare these fields with compatible types, while adding their own fields such as `title` or `name`.

Clients can query shared fields directly on the interface:

```graphql
query {
    catalogEntries {
        __typename
        id
        label
    }
}
```

When type-specific fields are needed, clients use inline fragments:

```graphql
query {
    catalogEntries {
        __typename
        id
        label
        ... on Book {
            title
        }
        ... on Author {
            name
        }
    }
}
```

## 2. Interface field contract

An object type implementing an interface must provide every field declared by the interface. Field names, required arguments, and data types must be compatible with the interface contract. An object's return type can be more specific where GraphQL allows covariance; the object must not weaken the contract in a way that makes an operation valid on the interface invalid on the object.

Example of an interface with arguments:

```graphql
interface Searchable {
    summary(maxLength: Int = 80): String!
}

type Book implements Searchable {
    summary(maxLength: Int = 80): String!
    title: String!
}

type Author implements Searchable {
    summary(maxLength: Int = 80): String!
    name: String!
}
```

The `maxLength` argument is part of the field contract. Object types must implement the `summary` field compatibly with the interface. An object may add extra optional arguments of its own, but clients querying through the interface can only use arguments exposed on the interface.

## 3. When is an explicit mapping needed?

If an interface field corresponds directly to a property or accessor on the source object, GraphQL Java can read the value using the default property data fetcher. For example, if the source has `id()` or `getId()` and the schema has an `id` field, you normally do not need a separate resolver.

Explicit mapping is useful when the field:

- Is computed from multiple properties of the source object.
- Needs to call an application service or gateway.
- Involves transformation, formatting, or business logic.
- Has arguments that affect how the value is produced.
- Does not exist as a direct property on the Java source.

In the catalog example, `label` may be computed differently depending on the entry type: using the title for books and the display name for authors. You can implement a single shared resolver on the interface rather than duplicating logic for `Book` and `Author`.

## 4. Preparing a shared Java model

The Java model can declare an interface representing catalog items:

```java
public interface CatalogEntryView {
    String id();
}
```

Concrete types implement that interface:

```java
public record BookView(
        String id,
        String title) implements CatalogEntryView {
}

public record AuthorView(
        String id,
        String name) implements CatalogEntryView {
}
```

A Java interface and a GraphQL interface are two independent concepts. The Java interface lets the controller accept a common source type; the SDL must still declare `CatalogEntry`, `Book`, `Author`, and the `implements` relationships. The Java name `CatalogEntryView` does not have to match the GraphQL name `CatalogEntry`.

The root resolver returns objects implementing the Java interface:

```java
@Controller
public class CatalogController {

    private final CatalogService catalogService;

    public CatalogController(CatalogService catalogService) {
        this.catalogService = catalogService;
    }

    @QueryMapping
    public List<CatalogEntryView> catalogEntries() {
        return catalogService.findEntries();
    }
}
```

## 5. Mapping a shared field with `@SchemaMapping`

To handle `CatalogEntry.label`, declare `@SchemaMapping` with `typeName` set to the GraphQL interface name:

```java
@Controller
public class CatalogEntryController {

    private final CatalogLabelService catalogLabelService;

    public CatalogEntryController(CatalogLabelService catalogLabelService) {
        this.catalogLabelService = catalogLabelService;
    }

    @SchemaMapping(typeName = "CatalogEntry", field = "label")
    public String label(CatalogEntryView source) {
        return catalogLabelService.labelFor(source);
    }
}
```

The method is mapped to the `label` field on the `CatalogEntry` interface. The source object is a concrete instance such as `BookView` or `AuthorView`, while the Java parameter accepts the common `CatalogEntryView` type. Spring for GraphQL applies the interface mapping to the object types implementing that interface, so shared field logic can be reused.

You can omit `field` if the method name matches the field name while keeping `typeName` explicit:

```java
@SchemaMapping(typeName = "CatalogEntry")
public String label(CatalogEntryView source) {
    return catalogLabelService.labelFor(source);
}
```

In the first example, declaring both `typeName` and `field` helps readers see clearly which interface field the mapping targets. When mapping at the interface level, specify the GraphQL interface name explicitly so the framework does not infer from a Java interface name that differs from the SDL.

## 6. Placing source-type logic in a service

The resolver can pass the source object to a service to apply display rules:

```java
@Service
public class CatalogLabelService {

    public String labelFor(CatalogEntryView source) {
        if (source instanceof BookView book) {
            return book.title();
        }

        if (source instanceof AuthorView author) {
            return author.name();
        }

        throw new IllegalArgumentException(
                "Unsupported catalog entry: " + source.getClass().getName());
    }
}
```

For a small example, the service can use `instanceof` to distinguish the two types. As the number of entry types grows or logic becomes more complex, consider domain model polymorphism, per-type strategies, dedicated mappers, or an orchestrating application service. Avoid keeping multiple business branches inside controllers if those rules can be reused elsewhere.

If the `label` field simply returns a property already available on each source object, consider removing the resolver and relying on the default property fetcher. A shared mapping is only worthwhile when there is actual logic to execute.

## 7. Field arguments on interface mappings

An interface field can accept arguments just like an object type field. Example:

```graphql
interface CatalogEntry {
    id: ID!
    label(maxLength: Int = 80): String!
}

type Book implements CatalogEntry {
    id: ID!
    label(maxLength: Int = 80): String!
    title: String!
}

type Author implements CatalogEntry {
    id: ID!
    label(maxLength: Int = 80): String!
    name: String!
}
```

Resolver receiving the source object and argument:

```java
@SchemaMapping(typeName = "CatalogEntry", field = "label")
public String label(
        CatalogEntryView source,
        @Argument("maxLength") Integer maxLength) {

    String value = catalogLabelService.labelFor(source);
    int limit = maxLength != null ? maxLength : 80;

    return value.length() <= limit
            ? value
            : value.substring(0, limit);
}
```

Clients can pass the argument when selecting the field through the interface:

```graphql
query {
    catalogEntries {
        id
        label(maxLength: 24)
    }
}
```

The default value in the SDL is applied by GraphQL when the argument is omitted. If you need to distinguish an omitted argument from an explicitly passed `null`, you can use `ArgumentValue<T>` via Spring for GraphQL's argument binding mechanism. In this example, both cases can use the default limit if that is the desired semantics.

The code should also validate `maxLength`, such as ensuring it is non-negative and does not exceed a maximum threshold. A schema default value does not replace business validation.

## 8. Type-specific mapping for an object type

Sometimes most object types share common logic, while one type needs custom behavior. For example, `Book.label` needs to include the book ID, while `Author.label` only uses the author's name.

You can create a specific mapping for the object type's field:

```java
@Controller
public class BookController {

    @SchemaMapping(typeName = "Book", field = "label")
    public String bookLabel(BookView book) {
        return book.title() + " (" + book.id() + ")";
    }
}
```

When designing both an interface mapping and a specific mapping, ensure every field/object coordinate has one clear resolver and verify actual behavior with schema integration tests. A type-specific mapping is appropriate when a field needs per-object-type logic; do not register multiple handlers for duplicate coordinates and rely on controller scan order.

Another organization option is having the interface resolver delegate to a strategy by source type. That keeps a single mapping and centralizes behavior selection in the service. Choose the approach that matches the degree of divergence and logic reusability.

## 9. Interface field mapping vs. `TypeResolver`

These two components often appear together when a query returns an interface, but they solve two different problems:

| Component | Purpose | Example |
| --- | --- | --- |
| `TypeResolver` | Determines which GraphQL object type a Java object belongs to | `BookView` → `Book`, `AuthorView` → `Author` |
| `@SchemaMapping` on interface | Computes or fetches the value of a shared interface field | Compute `CatalogEntry.label` |

Example operation:

```graphql
query {
    catalogEntries {
        __typename
        id
        label
        ... on Book {
            title
        }
        ... on Author {
            name
        }
    }
}
```

Execution involves two distinct steps:

1. `TypeResolver` identifies `BookView` as the GraphQL type `Book` or `AuthorView` as `Author`, so GraphQL knows the concrete type and processes inline fragments.
2. The field resolver for `CatalogEntry.label` supplies the `label` value on each concrete object.

Field mapping does not replace `TypeResolver`. Conversely, `TypeResolver` only selects the concrete type and does not compute the value for the `label` field. If the runtime already has a suitable default type resolver, you do not need to register an extra one just because you have an interface field mapping; otherwise, configure an explicit resolver via `RuntimeWiringConfigurer`.

## 10. Multiple interfaces and shared fields

An object type can implement multiple interfaces:

```graphql
interface Node {
    id: ID!
}

interface Auditable {
    createdAt: String!
}

type Book implements Node & Auditable {
    id: ID!
    createdAt: String!
    title: String!
}
```

You can organize separate resolvers for each interface:

```java
@Controller
public class NodeController {

    @SchemaMapping(typeName = "Node", field = "id")
    public String id(NodeView source) {
        return source.id();
    }
}
```

```java
@Controller
public class AuditableController {

    @SchemaMapping(typeName = "Auditable", field = "createdAt")
    public Instant createdAt(AuditableView source) {
        return source.createdAt();
    }
}
```

These examples assume Java source types implement the corresponding interfaces. If object types do not share a common Java abstraction, you can use a broader common source type or write specific resolvers for each object type.

There is no need to write a resolver for a field just to forward a getter. The default property fetcher is usually sufficient for `id` or `createdAt` if matching accessors already exist. Explicit mappings are better suited for fields requiring computation, conversion, or service calls.

## 11. Field mapping and batch loading

An interface field may need to access an external service or repository. For example, every `CatalogEntry` has an `owner` field, and the owner must be loaded from a service by `ownerId`.

Single-item resolver:

```java
@SchemaMapping(typeName = "CatalogEntry", field = "owner")
public OwnerView owner(CatalogEntryView source) {
    return ownerService.findByEntryId(source.id()).orElse(null);
}
```

If a query returns many catalog entries, this approach can trigger N+1 calls. In that case, use `DataLoader` or an appropriate batching mechanism to combine IDs into a single query. You can organize a batch loader by source interface if all entry types share the same owner-fetching rule; if different types have different relationships, register separate loaders or per-type mappings.

A key principle is never to let a shared resolver hide individual repository calls per source object. Measure service call counts, database queries, and latency before and after adding batching. If the service already provides an API accepting a list of IDs, `@BatchMapping` or `DataLoader` can connect directly to that API.

## 12. Validation, authorization, and errors for interface fields

A field declared on an interface is still part of the public API. Authorization rules must apply whether a client queries the field through the interface or through a concrete object type. Never assume that because a client only queries a shared field, the data is insensitive.

If `label` is built from data that some users are not allowed to see, the service called by the resolver must verify permissions based on the security context and specific resource. Do not rely on `__typename`, fragments, or which fields the client selects as an access control condition.

If a resolver throws an exception, GraphQL handles the error at the field being resolved. Nullability of the interface field and its parent fields determines the scope of null propagation. For example, `label: String!` cannot return `null`; if the resolver returns `null` or errors, GraphQL emits an execution error and `null` propagates up to the nearest nullable parent field.

Keep error messages returned to clients at an appropriate level of detail, while logging full details on the server. If a field can legitimately lack a value according to business rules, declare it nullable instead of forcing non-null and repeatedly returning `null`.

## 13. Testing interface field mapping

`GraphQlTester` can verify the same shared field across multiple concrete types. Example:

```java
graphQlTester.document("""
        query {
            catalogEntries {
                __typename
                id
                label
            }
        }
        """)
    .execute()
    .path("catalogEntries[0].label")
    .entity(String.class)
    .isEqualTo("Spring GraphQL in Practice");
```

You should also test an `Author` item to confirm the shared mapping works across all object types implementing the interface:

```java
graphQlTester.document("""
        query {
            catalogEntries {
                __typename
                label
            }
        }
        """)
    .execute()
    .path("catalogEntries[1].label")
    .entity(String.class)
    .isEqualTo("Nguyen An");
```

Important test cases:

1. Every concrete type receives the expected shared field value.
2. Inline fragments still fetch the specific fields of each object type.
3. `__typename` reflects the expected concrete type.
4. Interface field arguments bind properly and default values work.
5. Type-specific mappings do not conflict with interface mappings.
6. Unsupported source objects produce diagnosable errors.
7. Nullable/non-null fields adhere to the contract when the service returns `null` or throws an error.
8. Authorization is checked on each appropriate source type.
9. Batch loaders reduce service/repository calls when multiple objects are present.

Write integration tests that initialize the real schema to verify interface mappings. Unit tests calling Java methods directly are insufficient to confirm that annotations are wired properly to interface fields in the GraphQL schema.

## 14. Common issues

- **Confusing Java interfaces with GraphQL interfaces:** A Java interface is only a source type; the SDL must declare the interface and `implements` on object types.
- **Forgetting fields on implementing object types:** Every object implementing an interface must define the shared fields with compatible types.
- **Using the wrong `typeName`:** `typeName` must be the GraphQL interface name in the SDL, not the Java class name.
- **Using `@SchemaMapping` with an incompatible source parameter:** The source parameter must accept the actual object returned by the root/parent resolver.
- **Assuming interface mapping acts as `TypeResolver`:** Field mapping resolves a field's value; `TypeResolver` determines the concrete object type.
- **Writing resolvers for trivial fields:** If the property fetcher can already read the accessor, an explicit mapping may be unnecessary.
- **Registering duplicate mappings for the same coordinate:** This creates unpredictable configuration. Each field/object coordinate should have one clear handler.
- **Calling a service once per source:** Can cause N+1. Use a batch API or `DataLoader`.
- **Skipping authorization on interface fields:** Every exposed field must still be protected on the server.
- **Failing to test every concrete type:** A resolver might work for `Book` yet fail for `Author` due to differing source models or type resolution.

## 15. Workflow for implementing interface field mapping

When adding a shared field across multiple object types, follow these steps:

1. Identify the object types sharing the same field semantics and declare the appropriate GraphQL interface.
2. Ensure every implementing object type defines the field with compatible types and arguments.
3. Create a Java source interface or common supertype that the returned objects can implement.
4. Use the default property fetcher if the field simply reads directly from the source; if logic is needed, write `@SchemaMapping(typeName = "InterfaceName", field = "fieldName")`.
5. Accept the source object using the common Java type and delegate business logic to a service when needed.
6. Verify `TypeResolver` separately so GraphQL identifies the concrete object types properly.
7. If the field loads data for multiple objects, use a batch service, `@BatchMapping`, or `DataLoader` to avoid N+1.
8. Protect the field with authorization and define nullability/error semantics.
9. Test the same field across all concrete types, including fragments, arguments, and `__typename`.

Interface field mapping lets you implement a shared field across multiple object types without duplicating resolvers. In Spring for GraphQL, `@SchemaMapping` with `typeName` set to the interface name enables controllers to provide shared logic based on the source object. By keeping field mapping separate from `TypeResolver`, keeping the SDL contract consistent, and testing each concrete type, your API can add new object types while keeping shared field behavior clear.

## References

- [GraphQL Specification — Interfaces](https://spec.graphql.org/October2021/#sec-Interfaces)
- [Spring for GraphQL — Annotated Controllers](https://docs.spring.io/spring-graphql/reference/controllers.html)
- [Spring for GraphQL — Schema Mapping](https://docs.spring.io/spring-graphql/reference/controllers.html#controllers.schema-mapping)
- [GraphQL Java — TypeResolver](https://javadoc.io/doc/com.graphql-java/graphql-java/latest/graphql/schema/TypeResolver.html)
- [Spring for GraphQL — GraphQlTester](https://docs.spring.io/spring-graphql/reference/testing.html)

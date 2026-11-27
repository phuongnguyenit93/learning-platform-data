# Resource Identifiers with Long, UUID, and Custom ID Types in Spring Data REST

## 1. Database Identifiers vs. URI Identifiers

Spring Data REST exports repositories as HTTP resources. With a collection path `/orders`, a single resource can be accessed via `/orders/42` or `/orders/550e8400-e29b-41d4-a716-446655440000`. By default, the trailing segment of the URI is the entity's ID in the datastore. The repository's ID type must be compatible with the ID type declared on the entity:

```java
interface LongOrderRepository extends CrudRepository<LongOrder, Long> {
}

interface UuidOrderRepository extends CrudRepository<UuidOrder, UUID> {
}

interface CustomOrderRepository extends CrudRepository<CustomOrder, OrderId> {
}
```

When designing an API, distinguish three concepts:

- **Database identifier:** the key used by the persistence layer to identify a row/entity, typically marked with `@Id` or `@EmbeddedId`.
- **Domain identifier:** the identifier type and rules used by the domain model. It may be `Long`, `UUID`, or a value object such as `OrderId`.
- **Public resource identifier:** the value placed in the URI that clients use to access the resource. By default, Spring Data REST derives this from the entity's ID, though it can be customized via `EntityLookup`.

These three values may be identical, but they do not have to be. A database can use Long for efficient joins while the API exposes a UUID or an immutable public code. Clearly determine which value is internal, which appears in URIs, and which clients are allowed to submit.

A good identifier must be unique within a defined scope, stable throughout the resource lifecycle, and never reused in a way that makes old URIs point to a different resource. Technical IDs should also not be confused with mutable business codes, such as display invoice numbers, emails, or usernames.

## 2. Using Long as an Identifier

With Spring Data JPA, 64-bit integer keys are commonly declared with `Long`:

```java
import jakarta.persistence.*;

@Entity
class Order {

    @Id
    @GeneratedValue(
        strategy = GenerationType.SEQUENCE,
        generator = "order_seq"
    )
    @SequenceGenerator(
        name = "order_seq",
        sequenceName = "order_seq",
        allocationSize = 50
    )
    private Long id;

    protected Order() {
    }
}

interface OrderRepository extends JpaRepository<Order, Long> {
}
```

If supported by the database and provider, `GenerationType.IDENTITY` can also use an identity/auto-increment column. `SEQUENCE` uses a database sequence; `allocationSize` lets the provider pre-allocate a batch of values to reduce sequence calls. `GenerationType.AUTO` leaves the strategy choice to the provider, so behavior may vary by provider and database.

When an entity has ID `42L`, the default item URI has the form:

```http
GET /orders/42
```

**Advantages of Long**

- Small values, easy to read and debug.
- Occupies only 8 bytes as a 64-bit integer; indexes and foreign keys are compact.
- Sequences/identities are well supported by many database management systems.
- Convenient in logs, SQL queries, and administration tools.

**Limitations to Consider**

- Sequential IDs can leak information about record volume or creation rate.
- Clients can try sequential IDs to enumerate resources. This is not a vulnerability if authorization is properly enforced, nor is an unpredictable ID a security layer.
- ID generation typically depends on the database or a central number generator, making it harder to generate independently across multiple nodes before writing data.
- Sequences can have gaps due to rollbacks, caching, or node restarts. Do not assume IDs are contiguous and do not use IDs to count records.

Long fits well when the database acts as the centralized ID generator, index and join size matter, and predictable IDs are not a product concern. If you prefer not to expose sequential keys in the API, keep Long in the persistence layer and expose a separate public ID.

## 3. Using UUID as an Identifier

A UUID is 128 bits long and is commonly represented as a hyphenated hex string. For example:

```text
550e8400-e29b-41d4-a716-446655440000
```

With Jakarta Persistence 3.1 or later and a supporting provider, the UUID generation strategy can be used:

```java
import jakarta.persistence.*;
import java.util.UUID;

@Entity
class UuidOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.UUID)
    private UUID id;

    protected UuidOrder() {
    }
}

interface UuidOrderRepository extends JpaRepository<UuidOrder, UUID> {
}
```

`GenerationType.UUID` is part of Jakarta Persistence 3.1. For older JPA versions or providers, check how your provider supports UUIDs; some providers have their own annotations or generators. Do not copy Hibernate-specific annotations into another project without confirming compatibility.

The item URI takes the form:

```http
GET /orders/550e8400-e29b-41d4-a716-446655440000
```

**Advantages of UUID**

- IDs can be generated across multiple services or nodes without requesting the next number from a central sequence.
- Extremely low collision probability when using a standards-compliant generator.
- URIs reveal less about creation order and are harder to enumerate sequentially than Long IDs.
- Useful when data is created offline, synchronized, or merged from multiple sources.

**Costs and Limitations**

- UUIDs take more bytes than Long; indexes and foreign keys are larger.
- Random UUIDs such as version 4 can result in non-sequential inserts, affecting locality/caching and index performance in some databases.
- URIs are longer, harder to read, and harder to type manually.
- A UUID is not a secret and does not replace authorization. Anyone possessing a UUID must still pass permission checks just like with any other ID.
- Time-ordered UUIDs such as version 7 can improve write ordering in some workloads, though you should verify that your library, database, and provider support the exact format.

Use the Java `UUID` type rather than storing and manipulating arbitrary strings if your persistence provider supports appropriate mapping. The physical storage type may be native UUID, binary, or character depending on the database/dialect. Verify the actual schema and indexes before deciding.

## 4. Custom ID Types: Strongly Typed Value Objects

In large domain models, using raw `Long` or `UUID` everywhere can easily lead to passing the wrong ID. A method taking two UUID parameters might accidentally receive `customerId` in the `orderId` position; the compiler cannot distinguish their meanings.

A value object such as `OrderId` creates a distinct type, encapsulates parse/format rules, and clarifies parameter meaning. With JPA, a value object can be mapped as `@EmbeddedId`:

```java
import jakarta.persistence.Column;
import jakarta.persistence.Embeddable;
import java.io.Serializable;
import java.util.Objects;
import java.util.UUID;

@Embeddable
public class OrderId implements Serializable {

    @Column(name = "value", nullable = false)
    private UUID value;

    protected OrderId() {
        // JPA requires a no-arg constructor.
    }

    public OrderId(UUID value) {
        this.value = Objects.requireNonNull(value);
    }

    public static OrderId from(String text) {
        return new OrderId(UUID.fromString(text));
    }

    public UUID value() {
        return value;
    }

    @Override
    public String toString() {
        return value.toString();
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) return true;
        if (!(other instanceof OrderId that)) return false;
        return value.equals(that.value);
    }

    @Override
    public int hashCode() {
        return value.hashCode();
    }
}
```

Entity and repository using this ID type:

```java
import jakarta.persistence.EmbeddedId;
import jakarta.persistence.Entity;

@Entity
class CustomOrder {

    @EmbeddedId
    private OrderId id;

    protected CustomOrder() {
    }

    CustomOrder(OrderId id) {
        this.id = id;
    }

    public OrderId getId() {
        return id;
    }
}

interface CustomOrderRepository
        extends JpaRepository<CustomOrder, OrderId> {
}
```

An embedded ID must have stable `equals` and `hashCode` rules; attributes participating in identity must not change after the entity is saved. The example above wraps a UUID internally so the stored value remains a scalar identifier. For true composite IDs consisting of multiple fields, carefully evaluate how to represent them as a single path segment.

### Converting IDs in URIs

Item URIs contain text, whereas the repository may expect an `OrderId` object. Spring Data REST allows registering converters via `RepositoryRestConfigurer.configureConversionService`:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.core.convert.support.ConfigurableConversionService;
import org.springframework.data.rest.webmvc.config.RepositoryRestConfigurer;

@Configuration
class RestIdConfiguration implements RepositoryRestConfigurer {

    @Override
    public void configureConversionService(
            ConfigurableConversionService conversionService) {

        conversionService.addConverter(
            String.class,
            OrderId.class,
            OrderId::from
        );

        conversionService.addConverter(
            OrderId.class,
            String.class,
            OrderId::toString
        );
    }
}
```

The two conversion directions serve two roles:

- `String → OrderId`: parses the request path segment to look up the entity.
- `OrderId → String`: produces the identifier value when Spring Data REST constructs URIs for item resources.

If only one direction is registered, some read flows might work while link generation or URI construction fails with a conversion error. If the input string is malformed, the converter should reject it explicitly; do not silently convert an invalid string into a default or empty ID.

Spring converters do not replace persistence mappings. In the example above, `@EmbeddedId` determines how JPA stores the key; Spring Data REST converters handle ID representation across the URI boundary. If you also want to include a custom ID in the JSON body, Jackson has its own serializer/deserializer rules. These are separate boundaries.

If you only need strong typing in code without changing the persistence ID type, you can keep the database ID as Long/UUID and create value objects in the application/domain layer. Only add custom mapping to JPA when the type-safety benefit outweighs the mapping, querying, and maintenance cost.

## 5. Using a Public ID or Slug Instead of Database Keys

An entity may use a Long database ID while the API prefers readable or stable URIs based on another public key. For example, a customer is accessed via `/customers/acme-vn` instead of `/customers/73`. This changes how public resources are identified; it is distinct from changing the database primary key type.

Spring Data REST provides `EntityLookup` and the `withEntityLookup()` API to map URI values to entities. Suppose `Customer` has a unique `publicId` and the repository has `Optional<Customer> findByPublicId(String publicId)`:

```java
@Component
class CustomerResourceLookup implements RepositoryRestConfigurer {

    @Override
    public void configureRepositoryRestConfiguration(
            RepositoryRestConfiguration config,
            CorsRegistry cors) {

        config.withEntityLookup()
            .forRepository(CustomerRepository.class)
            .withIdMapping(Customer::getPublicId)
            .withLookup(CustomerRepository::findByPublicId);
    }
}
```

In this configuration:

- `withIdMapping` extracts the public ID from the entity to build item URIs.
- `withLookup` uses the URI value to find the entity through the repository.
- The database can still use Long for primary and foreign keys.
- The lookup repository method must resolve to at most one unique entity; the public ID needs a database unique constraint.

You can use a username, slug, or a dedicated generated public code. However, the value used in URIs should be stable and not change arbitrarily. If a username can change, using it as URI identity can invalidate old URLs and break bookmarks, caches, or saved links. For long-lived APIs, an immutable public ID is generally safer than a mutable business attribute.

`EntityLookup` does not automatically enforce uniqueness or create indexes. Declare unique constraints/indexes, handle creation conflicts, and decide on a migration strategy if a public ID ever changes. If old URIs must continue working, design aliases/redirects or compatibility endpoints separately.

## 6. Does the ID Appear in JSON?

Spring Data REST typically hides the ID property from the default JSON representation. Clients still receive the self link in HAL, for example:

```json
{
  "orderNumber": "SO-2026-001",
  "_links": {
    "self": {
      "href": "https://api.example.com/orders/42"
    }
  }
}
```

The self link URI is the resource identifier that clients should store and follow. There is no need to repeat the ID in the body solely for the client to identify the item.

If the ID is genuinely needed as a JSON property, you can explicitly configure which domain types are allowed to expose their IDs:

```java
@Configuration
class RestConfiguration implements RepositoryRestConfigurer {

    @Override
    public void configureRepositoryRestConfiguration(
            RepositoryRestConfiguration config,
            CorsRegistry cors) {

        config.exposeIdsFor(Order.class);
    }
}
```

`exposeIdsFor(Order.class)` makes the ID appear as a regular property in representations of that type. This is a representation decision, not a requirement for item URIs to work. Enable it only for domain types that need it; avoid enabling it globally out of habit.

If responses use DTOs or projections, explicitly decide which ID fields are returned and why. Do not let persistence IDs appear in the public contract merely because the entity has that field.

## 7. URI Design and Security Rules

Because IDs become part of the path, pay attention to how they are represented:

- Use a single canonical format. UUIDs should use standard formatting; slugs should have clear casing and Unicode normalization rules.
- Avoid IDs containing slashes `/`, question marks `?`, hashes `#`, or control characters. These characters have special meaning in URIs and can cause path-splitting or encoding bugs.
- If using strings with special characters, let the framework URI-encode/decode properly; do not manually concatenate paths via string addition.
- Do not extract IDs by manually slicing URL strings. Clients should follow the self link and relation links returned by the server.
- Keep IDs immutable. Do not reuse deleted IDs for another resource.
- Check access permissions on every request. Neither sequential Long IDs nor random UUIDs replace authentication/authorization.
- If a secret shareable link is required, generate a dedicated token with sufficient entropy, scoped permissions, and expiration; do not treat a database ID or resource UUID as a bearer secret.

An unpredictable URI can reduce sequential guessing, but it will not stop a low-privilege user from accessing another user's resource if the server lacks permission checks. Test valid IDs where the caller lacks permission, not just nonexistent IDs.

## 8. Testing and Choosing an ID Type

When implementing IDs for an exported repository, verify at least the following cases:

1. Create an entity and verify the server returns a properly formatted item URI; if the response has a `Location` header, it must point to the newly created resource.
2. Read collections and items; verify that the self link uses the right ID and can be followed.
3. Read an item with a malformed ID, a nonexistent ID, and an existing ID where the caller lacks permission. These three cases have distinct meanings and need consistent responses.
4. For UUID/custom IDs, test bidirectional conversion between path segments and Java types.
5. With `EntityLookup`, verify URIs are generated from the public key and lookups resolve to exactly one entity.
6. Verify whether IDs are hidden or exposed in JSON as configured.
7. Verify that association links, repository query methods, and related endpoints continue working after changing the ID type.
8. Verify the database schema, unique constraints, indexes, foreign keys, and migrations against the actual database used in deployment.

| Requirement | Commonly Suitable Choice | Things to Verify |
| --- | --- | --- |
| Centralized DB number generation, compact keys needed | `Long` | Do not rely on contiguity; authorization must be independent. |
| ID generation across multiple nodes or data sync | `UUID` | Index size, storage format, and provider generator. |
| Wanting distinct ID types in domain code | Value object such as `OrderId` | JPA mapping, equals/hashCode, and URI converters. |
| Wanting URIs to use public codes instead of DB keys | `EntityLookup` with public ID/slug | Uniqueness, immutability, indexing, and legacy URL compatibility. |
| Having composite multi-part keys | `@EmbeddedId` or scalar public ID | Clear encoding as a single URI segment; avoid leaking internal key structure. |

There is no single best ID type for every application. Choose based on how data is created, storage requirements, domain boundaries, API stability, and integration needs. Spring Data REST can expose Long, UUID, or custom ID types, as long as the repository, persistence mapping, conversion service, and URI rules agree on a single representation.

## References

- [Spring Data REST — Repository resources](https://docs.spring.io/spring-data/rest/reference/repository-resources.html)
- [Spring Data REST — Customizing item resource URIs and EntityLookup](https://docs.spring.io/spring-data/rest/reference/customizing-sdr.html)
- [Spring Data REST — RepositoryRestConfigurer API](https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/webmvc/config/RepositoryRestConfigurer.html)
- [Spring Data REST — RepositoryRestConfiguration API](https://docs.spring.io/spring-data/rest/docs/current/api/org/springframework/data/rest/core/config/RepositoryRestConfiguration.html)
- [Spring Data Commons — Custom conversions](https://docs.spring.io/spring-data/commons/reference/custom-conversions.html)
- [Jakarta Persistence — Specification](https://jakarta.ee/specifications/persistence/)

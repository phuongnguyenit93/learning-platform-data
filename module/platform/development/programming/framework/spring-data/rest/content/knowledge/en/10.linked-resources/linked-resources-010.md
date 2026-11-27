# Required Relationships, Non-Existent URIs, and Reference Cardinality Errors in Spring Data REST

Spring Data REST exposes repositories as HTTP resources and represents entity relationships using hypermedia links. When reading a resource, clients typically receive links under `_links`; when updating a relationship, clients send URIs of related resources to the association endpoint. Consequently, a linking error can originate from three different layers: relationship rules in the data model, the URI sent by the client, and the number of elements permitted by the relationship type.

This lesson uses the example of an `Order` with a required `Customer` and an `Article` with multiple `Tag`s. The paths use the `/api` prefix for illustration; actual paths depend on the base path, repository names, and `@RestResource` configuration.

## 1. Identifying the Association Resource and Reference URI

Suppose the client reads:

    GET /api/orders/42
    Accept: application/hal+json

The HAL response may contain links to the order and the customer association:

    {
      "_links": {
        "self": {
          "href": "http://localhost:8080/api/orders/42"
        },
        "customer": {
          "href": "http://localhost:8080/api/orders/42/customer"
        }
      }
    }

The two URIs have different roles:

- The entity URI, such as `/api/customers/7`, identifies the referenced `Customer` resource.
- The association URI, such as `/api/orders/42/customer`, is the endpoint used to read or modify Order 42's `customer` relationship.

Clients should extract links from the HAL response rather than concatenating relation names or guessing paths. Relation names and paths can be customized with `@RestResource`; associations can also remain unexported if repository or association configuration disallows access.

When submitting a reference, Spring Data REST typically accepts the URI via the `text/uri-list` media type. The content is the full URI of the target resource, not a numeric ID and not JSON describing the entity.

## 2. Declaring Required Relationships Correctly Across Multiple Layers

For example, an order must belong to exactly one customer:

    @Entity
    public class Order {
        @Id
        @GeneratedValue
        private Long id;

        @NotNull
        @ManyToOne(fetch = FetchType.LAZY, optional = false)
        @JoinColumn(name = "customer_id", nullable = false)
        private Customer customer;

        // getters and setters
    }

The three declarations in the example protect different layers:

- `@NotNull` is a Bean Validation constraint. It helps catch an entity missing a customer before the save operation completes, provided the validator runs in the repository flow.
- `optional = false` expresses a required relationship in the JPA model.
- `nullable = false` requires the foreign key column not to accept `NULL` when the schema is generated from the mapping. If the database is managed by migrations, the migration must also create the `NOT NULL` column and corresponding foreign key.

Do not rely on `optional = false` alone to produce a friendly API error message. JPA mappings and database constraints protect data integrity, while Bean Validation helps return earlier, clearer errors. Ensure all three layers align with business rules.

With Spring Boot 3, use Jakarta Bean Validation, typically via the `spring-boot-starter-validation` dependency. Spring Data REST can invoke the validator on repository events such as `beforeCreate` and `beforeSave`:

    @Configuration
    public class RepositoryValidationConfiguration {
        @Bean
        ValidatingRepositoryEventListener validatingRepositoryEventListener(
                jakarta.validation.Validator validator) {
            var listener = new ValidatingRepositoryEventListener();
            listener.addValidator("beforeCreate", validator);
            listener.addValidator("beforeSave", validator);
            return listener;
        }
    }

If the project already has an equivalent listener configuration, add validators to the existing configuration instead of registering duplicate listeners. For associations updated via dedicated endpoints, test that the update flow actually triggers validation on the entity being protected.

### Setting and removing a to-one relationship

Assign Customer 7 to Order 42:

    PUT /api/orders/42/customer
    Content-Type: text/uri-list

    http://localhost:8080/api/customers/7

The client must use the URI of a `Customer` exported by the repository. If the relationship is required, a request to delete the link:

    DELETE /api/orders/42/customer

must be rejected by validation rules or persistence constraints. If you rely solely on database `NOT NULL`, the error may surface late during flush and the message is often harder to interpret.

## 3. Non-Existent or Unresolvable URIs

A syntactically valid URI does not guarantee it points to an existing resource. For example:

    PUT /api/orders/42/customer
    Content-Type: text/uri-list

    http://localhost:8080/api/customers/999999

If Customer 999999 does not exist, Spring Data REST cannot establish the reference to the target entity. This case is different from sending a non-URI string or an invalid body format.

When encountering a reference error, check in order:

1. Does the URI have valid syntax and the correct API host/base path?
2. Is the target repository exported and does the endpoint have the right name?
3. Does the target entity exist with that ID?
4. Does the client have permission to read or link the target resource under the security configuration?
5. Does the URI point to the exact resource type expected by the association property?

Common scenarios:

| Scenario | Typical result | Resolution |
|---|---|---|
| Body is not a valid URI or wrong media type | `400 Bad Request` | Send a valid URI and `Content-Type: text/uri-list` |
| URI is syntactically valid but target entity does not exist | `404 Not Found` | Check the ID and read the target resource before linking |
| Repository or association is not exported | `404 Not Found` or endpoint missing from HAL | Check repository configuration and `@RestResource` |
| Caller is not authorized | `401 Unauthorized` or `403 Forbidden` | Check authentication and permissions |
| Entity violates a required constraint | Usually a `400` validation error; database errors depend on exception mapping | Add validation and keep database constraints |

Exact HTTP status codes can be influenced by the Spring Data REST version, exception handlers, and security configuration. When designing clients, rely on the response body and actual error codes of the running API; do not translate every linking error into an "ID not found" message.

## 4. Matching Reference Counts to Cardinality

The number of URIs submitted must match the association property type. JPA relationship cardinality determines how many other entities one entity can reference; it does not automatically enforce every business limit such as "at least two tags" or "no more than five order lines."

| JPA mapping | Meaning on the current entity side | Reference count |
|---|---|---|
| `@OneToOne` | One entity links to at most one target entity | One URI, or none if the relationship is optional |
| `@ManyToOne` | Multiple source entities can point to the same target entity | One URI per source entity |
| `@OneToMany` | One source entity can have multiple child entities | A URI collection |
| `@ManyToMany` | One entity can link to multiple entities on the other side | A URI collection |

For example, an `Article` can have multiple `Tag`s:

    @Entity
    public class Article {
        @Id
        @GeneratedValue
        private Long id;

        @ManyToMany
        private Set<Tag> tags = new HashSet<>();

        // getters and setters
    }

To add one or more tags to the collection association, the client sends a list of URIs:

    POST /api/articles/42/tags
    Content-Type: text/uri-list

    http://localhost:8080/api/tags/3
    http://localhost:8080/api/tags/8

For collection associations, `POST` is typically used to add references; `DELETE` with URIs in the body is used to unbind the specified references:

    DELETE /api/articles/42/tags
    Content-Type: text/uri-list

    http://localhost:8080/api/tags/8

Conversely, a to-one association like `Order.customer` accepts only one URI. Sending multiple URI lines for a single-valued property violates cardinality; do not turn a single relationship into a collection just by sending multiple IDs.

JPA note: in bidirectional relationships, the owning side controls updates to the foreign key or join table. For example, `mappedBy` marks the inverse side; modifying only the collection on the inverse side without updating the owning side can prevent the relationship from being saved as expected. Check the mapping and test the association endpoint by reading the resource back.

## 5. Minimum, Maximum, and Uniqueness Constraints

Relationship annotations describe link structure, but often do not express full business count limits:

- `@OneToMany` does not mean the collection must contain at least one element.
- `@ManyToMany` does not automatically impose a maximum number of links.
- `@ManyToOne` allows multiple source entities to reference the same target entity; if business rules allow only one source, an appropriate unique constraint is needed.
- `@OneToOne` should be backed by a unique constraint in the database so uniqueness is enforced even under concurrent requests.

If an `Article` must have between one and five `Tag`s, you can express validation intent on the collection:

    @NotEmpty
    @Size(max = 5)
    @ManyToMany
    private Set<Tag> tags = new HashSet<>();

Ensure the validator runs after operations that mutate the association. If the association endpoint does not trigger validation on the aggregate in your current configuration, perform checks at the service/domain boundary or use appropriate repository events. Do not rely solely on client-side browser validation.

For more complex rules, such as reference counts depending on order status or customer tier, use a context-aware business validator. Database constraints remain necessary for uniqueness, foreign keys, and `NOT NULL`; the Validation API does not replace those constraints.

## 6. Distinguishing Cardinality Errors from URI Errors

When an association request fails, identify the exact error category before fixing data:

- **Non-existent URI:** the number of references may be right, but one URI cannot be resolved to a target entity.
- **Wrong cardinality:** all URIs may exist, but the client sent multiple URIs for a single-valued property or sent a malformed body.
- **Business limit violation:** the number of references exceeds the maximum or falls below the minimum defined by the domain.
- **Integrity violation:** the reference causes a unique, foreign key, or `NOT NULL` conflict in the database.

For example, `Order` has one required customer and `Article` has at most five tags:

- Order sends one existing customer URI: valid cardinality.
- Order sends two customer URIs: wrong cardinality for a single-valued property.
- Order sends one non-existent customer URI: URI resolution error.
- Article sends six valid tag URIs: business limit error, not a URI error.
- Article sends a sixth tag URI where that tag does not exist: first and foremost a target resource resolution error.

Distinguishing these cases helps the client know whether to fix the payload, pick another target resource, or inform the user about a business rule.

## 7. Verification and Troubleshooting Workflow

When implementing or debugging associations in Spring Data REST, proceed in this order:

1. Call `GET` on the parent resource and read the exact association link in `_links`.
2. Call `GET` on the target entity URI to confirm the repository exposes the endpoint and the resource exists.
3. Determine from the JPA mapping whether the property is a single-valued or collection relationship.
4. Send the request with the right HTTP method and media type; use full URIs in `text/uri-list`.
5. Check validation for required relationships and count limits.
6. Re-read the parent resource or association after updating to confirm the link changed.
7. Check the database when errors involve `NOT NULL`, foreign key, or unique constraints.

A minimal integration test suite should cover these cases:

- Creating an entity without a required relationship.
- Binding an existing target entity URI.
- Binding a syntactically valid URI with no existing target entity.
- Sending multiple URIs for a to-one association.
- Adding and removing an item in a collection association.
- Submitting a collection below the minimum or above the maximum count.
- Sending two competing requests that could violate uniqueness.

In tests, assert the HTTP status, response body, and relationship state after the request. If the system customizes exception handlers, lock the error contract against the application's actual responses.

## 8. Principles to Remember

Required relationships must be protected at the validation, JPA mapping, and database layers. Reference URIs must point to real, exported, and accessible resources. The number of URIs must match the cardinality; minimum/maximum limits are business rules that need to be declared and enforced explicitly.

When clients use the exact association links from HAL, send properly formatted URI lists, and the server validates both existence and reference counts, linking errors in Spring Data REST become much easier to classify and resolve.
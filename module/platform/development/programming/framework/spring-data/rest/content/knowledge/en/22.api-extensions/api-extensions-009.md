# Receiving Resource References with AggregateReference When Supported by Your Version

## Objectives

When an API receives data referencing another resource, clients often send the URI of the related resource rather than sending an entire nested object. For example, when creating a Scanner, a client may send the URI of a Producer already exported by Spring Data REST.

Spring Data REST provides the `org.springframework.data.rest.core.AggregateReference<T, ID>` abstraction so custom controllers can accept a URI reference and resolve it into an identifier or aggregate. Support for this parameter type was introduced in Spring Data REST 4.1.

This abstraction must be distinguished from Spring Data JDBC's `org.springframework.data.jdbc.core.mapping.AggregateReference<T, ID>`. The two types share the same name, but differ in package and purpose:

- Spring Data REST AggregateReference represents an HTTP URI pointing to an exported aggregate.
- Spring Data JDBC AggregateReference wraps the identifier of another aggregate in the domain model so Spring Data JDBC can map cross-aggregate relationships.

This lesson covers accepting URI references in custom controllers, using URIs in request body DTOs, handling identifiers and aggregates, as well as compatibility limitations and access control.

## 1. Why Use URIs to Reference Resources?

Suppose an API has two independent aggregates:

- Producer is the aggregate managing producer details.
- Scanner is the aggregate storing scan configuration and referencing a Producer.

A client creating a Scanner needs to specify an existing Producer. Instead of sending the entire Producer object, the client sends a URI:

    {
      "name": "nightly-scanner",
      "producer": "http://localhost:8080/producers/42"
    }

The URI represents the resource identity published by the server. This approach offers several benefits:

- Clients do not resend all data of the related aggregate.
- The API preserves boundaries between aggregates.
- The server can resolve the URI into an identifier or object using Spring Data REST's mappings.
- Hypermedia URIs allow clients to follow links from earlier responses rather than constructing paths manually.

A URI is not proof that the caller has permission to use the resource. After resolving the reference, the application must still check authorization and business rules.

## 2. Distinguishing the Two AggregateReference Types with the Same Name

These two types are not interchangeable:

| Type | Package | Purpose |
|---|---|---|
| Spring Data REST AggregateReference | `org.springframework.data.rest.core.AggregateReference` | Accepts a resource URI in a custom REST handler and resolves the ID/aggregate |
| Spring Data JDBC AggregateReference | `org.springframework.data.jdbc.core.mapping.AggregateReference` | Stores an ID referencing another aggregate in a Spring Data JDBC model |

When working with a Spring Data REST custom controller, import:

    import org.springframework.data.rest.core.AggregateReference;

When modeling a property in a Spring Data JDBC entity, import:

    import org.springframework.data.jdbc.core.mapping.AggregateReference;

Do not pick an import based solely on class name. Determine whether you are handling an HTTP URI at the REST layer or an identifier at the persistence layer.

## 3. AggregateReference in Spring Data REST

Spring Data REST 4.1 added `AggregateReference<T, ID>` in package `org.springframework.data.rest.core`. This type represents a reference constructed from a URI following the item resource scheme exported by Spring Data REST.

A reference can be resolved into:

- The source URI via `getUri()`.
- The aggregate's identifier via `resolveId()`.
- The full aggregate via `resolveAggregate()`.
- A required identifier via `resolveRequiredId()`.
- A required aggregate via `resolveRequiredAggregate()`.

The two methods containing Required are appropriate when the handler cannot proceed if the URI fails to resolve to a value. The non-Required methods can return null per the API contract.

Example:

    import org.springframework.data.rest.core.AggregateReference;

    AggregateReference<Producer, Long> producerReference;

    Long producerId = producerReference.resolveRequiredId();

    Producer producer = producerReference.resolveRequiredAggregate();

Here:

- `Producer` is the referenced aggregate type.
- `Long` is Producer's identifier type.
- The input reference value is a resource URI, not an arbitrary JSON object.

## 4. Accepting References in @RepositoryRestController

Spring Data REST documentation guides declaring `AggregateReference` as a handler method parameter type. For GET requests, the URI reference is passed as a request parameter.

Controller example:

    import org.springframework.data.rest.core.AggregateReference;
    import org.springframework.data.rest.webmvc.RepositoryRestController;
    import org.springframework.web.bind.annotation.GetMapping;
    import org.springframework.web.bind.annotation.RequestParam;

    @RepositoryRestController
    class ScannerController {

        @GetMapping("/scanners")
        ResponseEntity<?> getScanners(
                @RequestParam
                AggregateReference<Producer, Long> producer) {

            Long producerId = producer.resolveRequiredId();

            Producer resolvedProducer =
                producer.resolveRequiredAggregate();

            // Use producerId or resolvedProducer in application logic.
            return ResponseEntity.ok(
                scannerService.findByProducer(producerId)
            );
        }
    }

The example above focuses on binding the reference. Repository names, services, return types, and response construction must be replaced with your actual domain model.

The client passes the Producer URI in a query parameter:

    curl --get       --data-urlencode "producer=http://localhost:8080/producers/42"       -H "Accept: application/hal+json"       http://localhost:8080/scanners

Use `--data-urlencode` to encode the URI properly in the query string. In a real application, clients should obtain the URI from the Producer's HAL link instead of hardcoding the path.

### 4.1. Choosing Between Resolving the ID and Resolving the Aggregate

Use `resolveRequiredId()` when the logic only needs the identifier:

    Long producerId = producer.resolveRequiredId();

For example, a service has a query method that only requires the producer ID:

    return scannerRepository.findAllByProducerId(producerId);

Use `resolveRequiredAggregate()` when the logic needs the Producer object:

    Producer producerEntity =
        producer.resolveRequiredAggregate();

For example, the service needs to read Producer's state or properties before creating a Scanner.

Do not resolve the full aggregate if you only need the ID. Loading the aggregate can issue extra queries and increase processing cost. Conversely, if you need to verify Producer's business state, merely extracting the ID and saving the association without checking state may be insufficient.

### 4.2. The URI Must Follow Spring Data REST Resource Mappings

References are resolved against the URI scheme Spring Data REST uses to export item resources. For example:

    http://localhost:8080/producers/42

If a repository has a base path, custom item URI, or EntityLookup that alters how resources are identified, clients must send the exact URI published by the server.

Do not guess URIs from class names or table names. Use the link returned in HAL:

    {
      "_links": {
        "producer": {
          "href": "http://localhost:8080/producers/42"
        }
      }
    }

If the URI does not match a recognizable resource mapping, reference conversion can fail.

## 5. Customizing Identifier Extraction with withIdSource

By default, Spring Data REST extracts the identifier from a URI using item resource conventions. If an API uses URIs with a custom identifier structure, you can use `withIdSource(...)` to supply a function extracting the value from `UriComponents`.

Conceptual example:

    AggregateReference<Producer, Long> reference =
        producer.withIdSource(uriComponents -> {
            // Extract the identifier from the URI structure
            // used by this application.
            return extractProducerId(uriComponents);
        });

    Long producerId = reference.resolveRequiredId();

The extractor function receives `UriComponents` and returns an identifier value that Spring Data REST can convert to the required ID type.

Only use this customization when the application's URI mapping genuinely differs from default conventions. If item resource URIs use standard IDs, the default mechanism is simpler and less error-prone.

Do not use the extractor to bypass resource mapping checks or turn an arbitrary string into resource access. The extracted identifier must still be checked for existence and authorization.

## 6. AssociationAggregateReference and jMolecules

If your domain model uses jMolecules, Spring Data REST provides `AssociationAggregateReference<T, ID>`, a subinterface of `AggregateReference`. It can resolve a reference into a jMolecules `Association` type.

Example:

    @GetMapping("/scanners")
    ResponseEntity<?> getScanners(
            @RequestParam
            AssociationAggregateReference<
                Producer,
                ProducerIdentifier
            > producer) {

        var association = producer.resolveRequiredAssociation();

        return ResponseEntity.ok(
            scannerService.findByProducer(association)
        );
    }

This type is only suitable when aggregates and identifiers follow the corresponding jMolecules abstractions. If the application does not use jMolecules, standard `AggregateReference<T, ID>` is the right choice.

Do not declare `AssociationAggregateReference` merely to wrap a simple identifier. It carries jMolecules Association semantics and requires the corresponding dependencies/type model.

## 7. Receiving URI References in a POST or PUT Request Body

For custom controllers accepting POST or PUT, the body is often a JSON document containing URIs to represent references to other resources.

Spring Data REST provides Jackson support to deserialize URIs of Spring Data REST-managed aggregates into aggregate instances inside DTOs. `AggregateReferenceResolvingModule` is documented as the module enabling URIs to be mapped to aggregate roots in payload-mapping DTOs.

DTO example:

    public record CreateScannerRequest(
        String name,
        List<Producer> producers
    ) {
    }

Request body:

    {
      "name": "nightly-scanner",
      "producers": [
        "http://localhost:8080/producers/42",
        "http://localhost:8080/producers/43"
      ]
    }

Controller example:

    @BasePathAwareController
    class ScannerCommandController {

        @PostMapping("/scanners")
        ResponseEntity<?> create(
                @RequestBody CreateScannerRequest request) {

            Scanner scanner = scannerService.create(
                request.name(),
                request.producers()
            );

            return ResponseEntity.ok(scanner);
        }
    }

In an environment with appropriate Spring Data REST Jackson integration, URIs in the DTO can be resolved into the corresponding aggregate instances. This capability was introduced in the Spring Data REST 3.5 line via `AggregateReferenceResolvingModule`.

If the application creates or replaces its own ObjectMapper/message converter, confirm that the URI-to-aggregate conversion module remains registered in the converter handling the request. A custom ObjectMapper does not automatically inherit every module and converter configured by Spring Data REST.

### 7.1. DTO Body References vs. AggregateReference Handler Parameters

The two ways of receiving references serve different roles:

| Flow | Declaration | Data Sent by Client |
|---|---|---|
| GET custom handler | `@RequestParam AggregateReference<T, ID>` | URI in query parameter |
| POST/PUT DTO body | DTO with property of aggregate type or collection of aggregates, using SDR Jackson URI resolution | URI string in JSON body |
| Spring Data JDBC domain model | Property of type `org.springframework.data.jdbc.core.mapping.AggregateReference<T, ID>` | Identifier mapped into persistence model |

Do not assume that `@RequestParam AggregateReference` automatically means every JSON body property must use the same wrapper type. For DTO bodies, Jackson URI deserialization can bind URIs into aggregate properties on the DTO.

### 7.2. Only Accept Exported and Resolvable Aggregates

URIs in a DTO must point to resources recognizable by Spring Data REST. If the URI is invalid, the repository is not exported, or the target cannot be resolved, binding can fail.

After binding succeeds, the service must still enforce business rules such as:

- The related aggregate is in a state that allows usage.
- The caller has permission to reference that aggregate.
- The aggregates belong to the same tenant if business rules require it.
- The reference does not create circular relationships or invalid state.
- The relationships are permitted across aggregate boundaries.

Do not treat Jackson URI resolution as validation or authorization.

## 8. AggregateReference in Spring Data JDBC

Spring Data JDBC has a different type with the same name:

    import org.springframework.data.jdbc.core.mapping.AggregateReference;

This type is used in domain models to represent a reference to another aggregate root. It wraps the target aggregate's ID and expresses the aggregate type via generic parameters.

Example:

    import org.springframework.data.annotation.Id;
    import org.springframework.data.jdbc.core.mapping.AggregateReference;
    import org.springframework.data.relational.core.mapping.Table;

    @Table("purchase_order")
    public class PurchaseOrder {

        @Id
        private Long id;

        private AggregateReference<Customer, Long> customer;
    }

Creating a reference:

    PurchaseOrder order = new PurchaseOrder();

    order.setCustomer(AggregateReference.to(customerId));

Getting the ID:

    Long customerId = order.getCustomer().getId();

This is persistence-layer mapping in Spring Data JDBC. `AggregateReference.to(id)` constructs a wrapper from an ID; it does not accept or parse HTTP URIs.

### 8.1. Why Does Spring Data JDBC Use AggregateReference?

Spring Data JDBC organizes data around aggregate boundaries:

- Entities inside the same aggregate are managed along with the aggregate root's lifecycle.
- References to other aggregates should be represented by an ID or AggregateReference.
- Spring Data JDBC does not automatically load the entire related aggregate simply because a property holds a reference.

Spring Data Relational documentation explains that n-1 or n-m relationships often represent two independent aggregates; `AggregateReference` is a wrapper around the ID whose type parameter records the target aggregate.

For example, `PurchaseOrder` referencing `Customer` involves two independent aggregates. Deleting or saving PurchaseOrder does not mean Spring Data JDBC manages the entire Customer lifecycle as a nested entity.

### 8.2. When to Use a Simple ID vs. AggregateReference?

| Representation | When Appropriate |
|---|---|
| `Long customerId` | Only need to store the ID and do not need a type-safe aggregate target |
| JDBC `AggregateReference<Customer, Long>` | Want to explicitly express a reference to the Customer aggregate in the domain model |
| Nested `Customer` object inside aggregate | Customer truly belongs to the same aggregate and its lifecycle is managed with the root |
| SDR `AggregateReference<Customer, Long>` | Custom REST handler accepts a resource URI and needs to resolve ID/aggregate |

Do not use JDBC AggregateReference in a DTO just because its name resembles Spring Data REST AggregateReference. Choose the type based on the layer you are working in.

## 9. Checking Existence and Handling Invalid References

A reference URI can be syntactically valid while the target resource does not exist or cannot be resolved.

For handlers accepting AggregateReference:

    Long producerId = producer.resolveRequiredId();

    Producer producerEntity =
        producer.resolveRequiredAggregate();

If only the ID is needed, the service can verify existence:

    if (!producerRepository.existsById(producerId)) {
        throw new ProducerNotFoundException(producerId);
    }

If the aggregate is resolved, check for null or use the Required methods according to the API contract. Choose consistent error handling for malformed URIs, missing resources, and forbidden resources.

Cases to distinguish:

- Malformed URI syntax.
- URI does not match a resource mapping.
- Identifier cannot be extracted.
- Identifier cannot be converted to the expected type.
- Target resource does not exist.
- Resource exists, but caller lacks permission.
- Resource exists, but violates business rules.

Do not return stack traces or internal converter/repository details to clients.

## 10. Authorization When Resolving References

Resolving a URI to an aggregate only answers which resource is being referenced. It does not decide whether the caller is allowed to use that resource.

For example, a user may be allowed to read a Producer, but lack permission to attach that Producer to a Scanner. The service needs to check permissions by action and by tenant/ownership:

    Producer producer =
        producerReference.resolveRequiredAggregate();

    authorizationService.assertCanUseProducer(
        currentUser,
        producer
    );

    scannerService.createForProducer(producer);

In a multi-tenant application, verify that Producer belongs to the current tenant before saving the association. Do not rely on the URI or ID sent by the client as proof of tenant ownership.

For custom controllers, apply Spring Security method/request authorization per application policy. When needed, place checks in the service so other call paths enforce the same rules.

## 11. Choosing the Right Custom Controller Type

Spring Data REST provides two commonly used annotations:

### 11.1. @RepositoryRestController

Use when the custom handler belongs to a repository resource's URI space and wants to leverage Spring Data REST configuration such as:

- API base path.
- Message converters.
- Exception handling.
- Repository-related CORS configuration.
- Support for lazy property access when JPA is used.

Example:

    @RepositoryRestController
    class ScannerController {
        // Repository-related custom operations.
    }

This controller should be used for custom operations inside the repository's URI space.

### 11.2. @BasePathAwareController

Use when you need custom operations under the API base path that are not necessarily operations on a specific repository resource.

Example:

    @BasePathAwareController
    class ScannerCommandController {
        // Application-specific endpoints under the SDR base path.
    }

With request DTOs containing URI references, ensure the handler uses message converters with Spring Data REST URI-to-aggregate support. If configuring converters manually, verify the corresponding module is included.

If you use a standard `@Controller` or `@RestController`, the handler sits outside Spring Data REST integration scope; message converters and exception handling may differ.

## 12. Version Compatibility

Verify your Spring Data release train and actual dependencies before using these APIs.

| Feature | Version Milestone Documented by Spring |
|---|---|
| Jackson URI-to-aggregate mapping for DTO payloads | Spring Data REST 3.5 |
| `org.springframework.data.rest.core.AggregateReference<T, ID>` for handler method parameters | Spring Data REST 4.1 |
| `AssociationAggregateReference` for jMolecules Association | Spring Data REST 4.1 |
| `org.springframework.data.jdbc.core.mapping.AggregateReference<T, ID>` in Spring Data JDBC | Available since Spring Data JDBC 1.0 |

These milestones mark API introduction and do not guarantee that arbitrary Spring Boot or Spring Data module versions are mutually compatible. Spring Boot manages Spring Data versions through a release train; do not upgrade Spring Data REST/JDBC individually without checking the compatibility matrix.

If a project uses Spring Data REST earlier than 4.1, the `org.springframework.data.rest.core.AggregateReference` handler parameter type may not exist yet. In that case, accept `URI` or `String` and resolve it via services/repositories and appropriate mappings, or upgrade to a compatible release train.

## 13. Testing Examples

Test URI binding, resolution, and authorization separately.

### 13.1. GET Handler Receiving URI Reference

- Send the URI of an existing Producer and verify the handler receives the expected ID.
- Verify `resolveRequiredAggregate()` returns the expected Producer.
- Send a URI not matching any resource mapping and verify the error matches the API contract.
- Send a URI to a non-existent Producer and verify the appropriate error.
- Test URIs with custom identifier mappings if the application uses EntityLookup.

### 13.2. POST/PUT DTO Body

- Send a valid Producer URI in the JSON body.
- Send a list of multiple URIs if the DTO supports a collection.
- Send a malformed URI.
- Send a URI for an unexported or unresolvable resource.
- Verify a custom ObjectMapper does not drop the SDR URI deserializer.
- Verify response statuses and error bodies do not leak internal details.

### 13.3. Authorization and Domain Rules

- Users permitted to reference Producer can create Scanner.
- Users lacking permission to use Producer are rejected.
- Cross-tenant references are rejected when the domain requires the same tenant.
- Archived/disabled Producers cannot be used if business rules forbid it.
- Failed requests do not create partial Scanners or associations.

### 13.4. Spring Data JDBC Mapping

If using JDBC AggregateReference:

- Save PurchaseOrder with a valid Customer ID.
- Reload PurchaseOrder and check `getCustomer().getId()`.
- Verify the wrapper maps to the foreign-key value per schema.
- Check database foreign keys if needed to ensure reference targets exist.
- Do not assume loading PurchaseOrder automatically loads the entire Customer.

## 14. Common Pitfalls

| Symptom | Causes to Check |
|---|---|
| Cannot inject AggregateReference into handler | Spring Data REST version older than 4.1 or wrong package imported |
| URI parameter fails to resolve | URI does not match item resource mapping |
| resolveRequiredId fails | Cannot extract ID or URI is invalid |
| resolveRequiredAggregate fails | Target aggregate cannot be resolved |
| DTO receives URI string instead of object | SDR Jackson URI deserializer missing from active converter |
| Custom ObjectMapper breaks binding | Custom converter does not register SDR Jackson support |
| Wrong AggregateReference used | Confused org.springframework.data.rest.core with org.springframework.data.jdbc.core.mapping |
| AssociationAggregateReference fails to compile | Missing Spring Data REST 4.1+ or appropriate jMolecules types/dependencies |
| Resource resolves successfully but user still shouldn't use it | Missing authorization/business rule checks |
| Manually constructed URI fails | Resource path or EntityLookup differs from client assumptions |
| Stored only ID but target state needed checking | Need to resolve aggregate or load from repository/service |
| JDBC reference does not auto-load target aggregate | JDBC AggregateReference only wraps an ID, not an eagerly fetched object relationship |

## 15. Implementation Checklist

1. Determine whether you need a Spring Data REST URI reference or a Spring Data JDBC persistence reference.
2. Use the right package and dependency for AggregateReference.
3. Verify that your Spring Data REST version supports the 4.1+ handler parameter API.
4. For GET custom handlers, declare `@RequestParam AggregateReference<T, ID>`.
5. Use `resolveRequiredId()` if only the ID is needed.
6. Use `resolveRequiredAggregate()` if the full object is needed.
7. Use `withIdSource(...)` only when URIs have custom identifier mappings.
8. Use `AssociationAggregateReference` when the domain model actually uses jMolecules Association.
9. For POST/PUT DTOs, send resource URIs in JSON and ensure SDR Jackson URI resolution is configured.
10. Choose `@RepositoryRestController` or `@BasePathAwareController` based on URI space and integration needs.
11. Verify resource existence, tenant, ownership, and authorization after resolution.
12. Do not treat a URI/ID as proof of access permission.
13. With Spring Data JDBC, use `AggregateReference.to(id)` for cross-aggregate references.
14. Test valid URIs, malformed URIs, missing targets, access permissions, and custom ObjectMappers.
15. Check the Spring Data version against the Spring Boot release train before adopting the API.

## References

- [Spring Data REST — Obtaining Aggregate References in custom controllers](https://docs.spring.io/spring-data/rest/reference/customizing/overriding-sdr-response-handlers.html)
- [Spring Data REST — AggregateReference API](https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/core/AggregateReference.html)
- [Spring Data REST — AggregateReferenceResolvingModule API](https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/webmvc/json/AggregateReferenceResolvingModule.html)
- [Spring Data REST — AssociationAggregateReference API](https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/core/AssociationAggregateReference.html)
- [Spring Data Relational — Referenced entities and AggregateReference](https://docs.spring.io/spring-data/relational/reference/jdbc/mapping.html)
- [Spring Data JDBC — AggregateReference API](https://docs.spring.io/spring-data/relational/reference/api/java/org/springframework/data/jdbc/core/mapping/AggregateReference.html)
- [Spring blog — Spring Data REST aggregate reference mapping for DTOs](https://spring.io/blog/2021/04/20/what-s-new-in-spring-data-2021-0/)
- [Spring Data REST — Overriding response handlers and controller integration](https://docs.spring.io/spring-data/rest/reference/customizing/overriding-sdr-response-handlers.html)

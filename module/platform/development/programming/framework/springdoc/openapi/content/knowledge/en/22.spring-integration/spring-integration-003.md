# Spring HATEOAS and Link Wrapper Classes

A REST API often returns data together with links so clients know which next steps they can perform. For example, a customer response can include a link to the customer itself, the customer's order list, or an update operation. This design follows the Hypermedia as the Engine of Application State (HATEOAS) principle: clients discover follow-up actions from links provided by the server instead of manually assembling every URL.

Spring HATEOAS provides representation classes such as `EntityModel`, `CollectionModel`, and `PagedModel` to wrap content alongside links. `springdoc-openapi` integrates with these HATEOAS types to describe responses in OpenAPI. When declaring specific return types, accurate media types, and appropriate operation metadata, the documentation can represent both the data and the hypermedia structure clients receive.

## 1. What Does HATEOAS Add to a REST Response?

A conventional REST response might contain only data:

```json
{
  "id": "c-100",
  "name": "Nguyen An"
}
```

A client wanting to view the customer's orders might have to know the URL `/api/customers/c-100/orders` in advance. When the API uses hypermedia, the server can return that link in the response:

```json
{
  "id": "c-100",
  "name": "Nguyen An",
  "_links": {
    "self": {
      "href": "https://api.example.com/api/customers/c-100"
    },
    "orders": {
      "href": "https://api.example.com/api/customers/c-100/orders"
    }
  }
}
```

The client reads the `orders` relation to discover the link to orders. The server can change internal URL structures without forcing clients to construct URLs themselves, provided the relations and link contract remain stable.

HATEOAS does not require every API to embed every action in the response. Provide links that are meaningful for the resource's state and permissions. For example, a `cancel` link should appear only when the order can still be canceled; clients must still handle errors if state changes between reading and invoking the action.

## 2. Setting Up Spring HATEOAS with Springdoc

For a Spring Boot MVC application using Spring HATEOAS and Swagger UI, dependencies typically include:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-hateoas</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springdoc</groupId>
        <artifactId>springdoc-openapi-starter-webmvc-ui</artifactId>
        <version>${springdoc.version}</version>
    </dependency>

    <dependency>
        <groupId>org.springdoc</groupId>
        <artifactId>springdoc-openapi-hateoas</artifactId>
        <version>${springdoc.version}</version>
    </dependency>
</dependencies>
```

`spring-boot-starter-hateoas` provides Spring's models, link builders, and hypermedia support. `springdoc-openapi-hateoas` adds HATEOAS integration to OpenAPI generation; the springdoc MVC UI starter provides the documentation endpoints and Swagger UI interface. If only JSON/YAML is needed, use `springdoc-openapi-starter-webmvc-api` together with the HATEOAS module. Springdoc 2.x documentation for the HATEOAS module covers WebMVC starters; if the application uses WebFlux, check the support matrix for your exact version before assuming the same module applies. Spring HATEOAS has a dedicated link builder for WebFlux, but that alone does not confirm springdoc HATEOAS integration for WebFlux.

Keep versions aligned with Spring Boot dependency management and the compatible springdoc branch. Do not add both WebMVC and WebFlux starters just to get HATEOAS; choose the web stack the application actually uses.

## 3. `RepresentationModel` as the Base Class for Hypermedia

`RepresentationModel<T>` is the base class in Spring HATEOAS for representations with links. It provides the API to add and read `Link`s:

```java
public class CustomerRepresentation extends RepresentationModel<CustomerRepresentation> {

    private String id;
    private String name;

    // Constructor, getters and setters.
}
```

Links can be added directly:

```java
CustomerRepresentation model = new CustomerRepresentation();
model.add(Link.of("https://api.example.com/api/customers/c-100", "self"));
```

In many applications, creating a custom subclass is unnecessary. Specialized wrappers `EntityModel`, `CollectionModel`, and `PagedModel` already provide more common representations. `RepresentationModel` is useful when you want to define a dedicated representation type and control its data structure.

## 4. `EntityModel<T>` Wraps a Single Resource

`EntityModel<T>` represents a single resource along with links. The generic `T` is the content type the API intends to return:

```java
EntityModel<CustomerResponse> model = EntityModel.of(
    new CustomerResponse(customer.getId(), customer.getName()),
    Link.of("https://api.example.com/api/customers/c-100", "self")
);
```

When serialized as HAL, the contents of `CustomerResponse` typically sit at the top level alongside `_links`:

```json
{
  "id": "c-100",
  "name": "Nguyen An",
  "_links": {
    "self": {
      "href": "https://api.example.com/api/customers/c-100"
    }
  }
}
```

Do not think of `EntityModel<T>` as a JSON object with a `content` property wrapping the data. The wrapper is a Java type supporting hypermedia serialization; the final JSON shape depends on the media type and configured hypermedia module.

Keep the generic concrete, such as `EntityModel<CustomerResponse>`, rather than raw `EntityModel`. Type information helps Jackson serialize the contents properly and enables springdoc to infer the schema of the inner resource.

## 5. `CollectionModel<T>` Wraps a Collection of Resources

`CollectionModel<T>` represents a collection of items together with collection links:

```java
List<EntityModel<CustomerResponse>> customers = customerService.findAll()
    .stream()
    .map(customerAssembler::toModel)
    .toList();

CollectionModel<EntityModel<CustomerResponse>> collection =
    CollectionModel.of(customers);
```

With HAL, a collection is typically represented using `_embedded` and `_links`:

```json
{
  "_embedded": {
    "customers": [
      {
        "id": "c-100",
        "name": "Nguyen An",
        "_links": {
          "self": {
            "href": "https://api.example.com/api/customers/c-100"
          }
        }
      },
      {
        "id": "c-101",
        "name": "Tran Binh",
        "_links": {
          "self": {
            "href": "https://api.example.com/api/customers/c-101"
          }
        }
      }
    ]
  },
  "_links": {
    "self": {
      "href": "https://api.example.com/api/customers"
    }
  }
}
```

The name `customers` inside `_embedded` is the collection relation. Spring HATEOAS can infer the relation from the type name or relation provider configuration; you can declare it explicitly with `@Relation` to keep the name stable.

## 6. Naming Relations with `@Relation`

A relation is a meaningful name clients use to understand a link or embedded group of items. For a representation, you can declare both the item relation and collection relation:

```java
import org.springframework.hateoas.server.core.Relation;

@Relation(itemRelation = "customer", collectionRelation = "customers")
public record CustomerResponse(String id, String name) {}
```

`itemRelation = "customer"` sets the relation name for a single item; `collectionRelation = "customers"` sets the name for the list of items in `_embedded`. This name is part of the hypermedia contract clients may rely on, so choose names that are stable, clear, and consistent.

Do not change relations arbitrarily once clients depend on them. Changing `customers` to `clients` can prevent clients from finding the list in `_embedded`, even if the endpoint URL and data remain unchanged.

## 7. Building Links from Mappings with `WebMvcLinkBuilder`

Spring HATEOAS provides `WebMvcLinkBuilder` to build links based on controller mappings. This avoids hard-coding paths inside assemblers:

```java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

@Component
class CustomerModelAssembler
        implements RepresentationModelAssembler<Customer, EntityModel<CustomerResponse>> {

    @Override
    public EntityModel<CustomerResponse> toModel(Customer customer) {
        CustomerResponse content = new CustomerResponse(
            customer.getId(),
            customer.getName()
        );

        return EntityModel.of(
            content,
            linkTo(methodOn(CustomerController.class).getById(customer.getId()))
                .withSelfRel()
        );
    }
}
```

`methodOn(...)` creates a mock controller invocation so Spring HATEOAS can inspect the method mapping; the method is not actually executed to fetch data. `linkTo(...)` builds the URL from the mapping, and `withSelfRel()` attaches the standard `self` relation.

If the controller has base mapping `/api/customers` and method `@GetMapping("/{id}")`, the link is generated from the current mapping. When mappings change, the link builder follows those changes without editing URL strings in the assembler.

For Spring WebFlux applications, use the WebFlux link builder instead of `WebMvcLinkBuilder`. The two APIs handle request context differently; do not mix MVC builders into reactive applications.

## 8. Using `RepresentationModelAssembler` to Separate Representation Creation

`RepresentationModelAssembler<T, D>` converts a domain object into a representation model. It centralizes DTO conversion and link creation in one place instead of repeating them across controllers:

```java
@RestController
@RequestMapping("/api/customers")
class CustomerController {

    private final CustomerService customerService;
    private final CustomerModelAssembler assembler;

    CustomerController(CustomerService customerService,
                       CustomerModelAssembler assembler) {
        this.customerService = customerService;
        this.assembler = assembler;
    }

    @GetMapping(value = "/{id}", produces = MediaTypes.HAL_JSON_VALUE)
    @Operation(summary = "Get customer by ID")
    EntityModel<CustomerResponse> getById(@PathVariable String id) {
        Customer customer = customerService.getById(id);
        return assembler.toModel(customer);
    }

    @GetMapping(produces = MediaTypes.HAL_JSON_VALUE)
    @Operation(summary = "List customers")
    CollectionModel<EntityModel<CustomerResponse>> findAll() {
        List<EntityModel<CustomerResponse>> items = customerService.findAll()
            .stream()
            .map(assembler::toModel)
            .toList();

        return CollectionModel.of(
            items,
            linkTo(methodOn(CustomerController.class).findAll()).withSelfRel()
        );
    }
}
```

The controller returns concrete wrapper types. Spring HATEOAS serializes the content and links; springdoc reads the return types to generate response schemas. When adding a new endpoint, you can reuse the assembler to ensure every item has a consistent structure and self link.

Do not expose JPA entities directly just because `EntityModel` can wrap them. Use DTO/representation models to control public fields, avoid leaking internal attributes, and prevent serialization from traversing unwanted lazy relationships.

## 9. `PagedModel<T>` Represents Paginated Collections

`PagedModel<T>` extends the collection concept with pagination metadata. When using Spring Data, `PagedResourcesAssembler<T>` can convert a `Page<T>` into a `PagedModel` and attach navigation links:

```java
@GetMapping(value = "/paged", produces = MediaTypes.HAL_JSON_VALUE)
@Operation(summary = "List customers with pagination")
PagedModel<EntityModel<CustomerResponse>> findPage(
    Pageable pageable,
    PagedResourcesAssembler<Customer> pagedAssembler
) {
    Page<Customer> page = customerService.findAll(pageable);
    return pagedAssembler.toModel(page, assembler);
}
```

The HAL response for a page can include `_embedded`, `_links`, and `page` metadata:

```json
{
  "_embedded": {
    "customers": [
      {
        "id": "c-100",
        "name": "Nguyen An",
        "_links": {
          "self": {
            "href": "https://api.example.com/api/customers/c-100"
          }
        }
      }
    ]
  },
  "_links": {
    "self": {
      "href": "https://api.example.com/api/customers/paged?page=0&size=20"
    },
    "next": {
      "href": "https://api.example.com/api/customers/paged?page=1&size=20"
    },
    "last": {
      "href": "https://api.example.com/api/customers/paged?page=4&size=20"
    }
  },
  "page": {
    "size": 20,
    "totalElements": 85,
    "totalPages": 5,
    "number": 0
  }
}
```

The `first`, `prev`, `next`, and `last` links appear depending on the current page position and assembler policy. `page.number` metadata in Spring Data is typically zero-based. Clients should follow links returned by the server rather than calculating the next page URL themselves.

`Page<T>` and `PagedModel<T>` are not the same response type. `Page<T>` is a pagination data abstraction at the Spring Data layer; `PagedModel<T>` is a hypermedia representation that can include links and metadata in HATEOAS format. If the API commits to HAL, return `PagedModel` instead of exposing `Page` directly and assuming navigation links will appear automatically.

## 10. HAL Media Type and Response Structure

HAL (Hypertext Application Language) is a common hypermedia format in Spring HATEOAS. The standard media type is `application/hal+json`, provided by Spring HATEOAS via the constant `MediaTypes.HAL_JSON_VALUE`.

Declaring `produces = MediaTypes.HAL_JSON_VALUE` on a mapping helps Spring MVC advertise the response type produced by the endpoint. Clients can send `Accept: application/hal+json` to request a HAL representation.

Example request:

```http
GET /api/customers/c-100 HTTP/1.1
Accept: application/hal+json
```

Response:

```http
HTTP/1.1 200 OK
Content-Type: application/hal+json
```

If the API also supports plain JSON, clearly define what payload shape each media type has and configure `produces`/content negotiation accordingly. Do not advertise `application/json` if the actual response is always HAL where clients need to read `_links`.

## 11. How Springdoc Describes HATEOAS Wrappers

Springdoc integrates with Spring HATEOAS to analyze model types and generate OpenAPI schemas. Declaring return types with concrete generics is critical to preserving content type information:

```java
EntityModel<CustomerResponse>
CollectionModel<EntityModel<CustomerResponse>>
PagedModel<EntityModel<CustomerResponse>>
```

In springdoc 2.x, this integration is provided via the separate module `springdoc-openapi-hateoas`; add that module alongside the corresponding WebMVC API/UI starter. The `springdoc.enable-hateoas` property controls HATEOAS support and is enabled by default. If the module is missing from the classpath or the property is disabled, do not expect wrappers to be processed through HATEOAS integration.

When a method returns `EntityModel<CustomerResponse>`, springdoc can describe the customer representation along with the links section. For collections and pages, the schema also reflects the wrapper structure and hypermedia metadata. Exact component structures and schema names can vary across springdoc versions, Swagger Core, and HAL configurations; inspect the actual output in `/v3/api-docs` rather than relying on auto-generated component names.

Example operation declaration:

```java
@GetMapping(value = "/{id}", produces = MediaTypes.HAL_JSON_VALUE)
@Operation(
    operationId = "getCustomerById",
    summary = "Get customer by ID",
    description = "Returns customer data along with hypermedia links."
)
EntityModel<CustomerResponse> getById(@PathVariable String id) {
    return assembler.toModel(customerService.getById(id));
}
```

Return type information from Java tells springdoc the wrapper and generic content; `@Operation` adds operation meaning. If you need to specify response codes or descriptions, use `@ApiResponse`. Only set `@Schema(implementation = ...)` when overriding inference is genuinely needed; an incorrect `implementation` annotation can erase the wrapper/generic structure that springdoc would otherwise recognize.

## 12. Distinguishing HAL `_links` from OpenAPI `links`

Two concepts share the same name but belong to two different layers:

| Component | Where it appears | Purpose |
| --- | --- | --- |
| HAL `_links` | Runtime JSON response | Provides URLs and relations for clients to navigate to resources or follow-up actions. |
| OpenAPI Response Object `links` | OpenAPI specification | Describes relationships from one operation's response to another operation, helping tools understand how to pass data between operations. |

`EntityModel` and `CollectionModel` produce `_links` in the HAL payload. OpenAPI's `links` field is metadata in the document and does not automatically inject `_links` into runtime responses. Conversely, a server returning `_links` does not automatically generate every OpenAPI Link Object describing workflows between operations.

If an API uses HATEOAS, describe the response schema and media type in OpenAPI. Only add OpenAPI `links` when you want to explicitly publish actionable relationships between operations for tooling or workflows.

## 13. Verifying HAL Responses and the OpenAPI Document

Verify both runtime serialization and generated schemas:

1. Call the endpoint with `Accept: application/hal+json` and confirm `Content-Type` is `application/hal+json`.
2. For a single resource, inspect content fields alongside `_links.self.href`.
3. For a collection, check that `_embedded` uses the expected collection relation and each item has the required links.
4. For a page, check navigation `_links` alongside `page` metadata.
5. Open `/v3/api-docs`, locate the operation, and confirm the response content includes the HAL media type.
6. Inspect generated schemas for wrappers and generic content; confirm every `$ref` points to an existing component.
7. Open Swagger UI and confirm the response schema/example is readable.
8. Test a client following relations rather than constructing URLs manually to verify links lead to valid operations.

Example testing a single endpoint with MockMvc:

```java
@SpringBootTest
@AutoConfigureMockMvc
class CustomerHateoasTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void returnsCustomerWithSelfLink() throws Exception {
        mockMvc.perform(get("/api/customers/{id}", "c-100")
                .accept(MediaTypes.HAL_JSON))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(MediaTypes.HAL_JSON))
            .andExpect(jsonPath("$.id").value("c-100"))
            .andExpect(jsonPath("$._links.self.href").exists());
    }
}
```

This test checks the runtime response. Have a separate test for `/v3/api-docs` to verify the published operation and media type; the two checks do not replace each other.

## 14. Common Mistakes

| Symptom | Possible cause | Fix |
| --- | --- | --- |
| Response has data but no `_links` | Returning DTO directly instead of representation model, or not adding links | Use `EntityModel`/`RepresentationModel` and create links explicitly. |
| Collection lacks expected `_embedded` | Relation name inferred differently or wrapper is not `CollectionModel` | Use `CollectionModel` and declare `@Relation(collectionRelation = ...)` if needed. |
| Links have wrong host or prefix URL | Hard-coded URLs or misconfigured proxy/forwarded headers | Use mapping-based link builders and check forwarded headers. |
| `EntityModel` described as an incorrect Java object | Raw generics, wrong schema override, or HATEOAS integration inactive | Keep concrete generics, check dependencies and `/v3/api-docs`. |
| Response returns `application/json` while client expects HAL | Mapping does not declare HAL or content negotiation is wrong | Declare `produces = MediaTypes.HAL_JSON_VALUE` and check `Accept`. |
| Swagger UI does not display `_links` clearly | Generated component schema differs from expectations or media type undocumented | Inspect raw schema and declare proper response content if needed. |
| Paged response missing `next`/`last` links | Current page is the last one, empty data, or not using `PagedResourcesAssembler` | Check page metadata and how `Page` is converted to `PagedModel`. |
| Changing relation breaks clients | Clients depend on old `_embedded` key or relation name | Keep relations stable or manage changes as contract changes. |
| Swagger shows OpenAPI `links` but JSON lacks `_links` | Confusing OpenAPI Link Objects with runtime HAL links | Create `Link` in the representation model; OpenAPI links only document workflows. |

## 15. Application Guidelines

- Use `EntityModel<T>` for a single resource, `CollectionModel<T>` for collections, and `PagedModel<T>` for paginated collections.
- Keep generics concrete so Jackson and springdoc recognize the content inside wrappers.
- Use `RepresentationModelAssembler` to separate DTO conversion and link creation from controllers.
- Build links from controller mappings using `WebMvcLinkBuilder` in MVC or the corresponding builder in WebFlux.
- Use `@Relation` to fix item/collection relations when clients depend on those names.
- Advertise the proper media type, usually `application/hal+json` when using HAL.
- Do not return persistence entities directly when DTOs provide better control over public data.
- Distinguish HAL `_links` in responses from OpenAPI `links` in documentation.
- Check runtime responses, `/v3/api-docs`, and Swagger UI after changing wrappers or relations.

Spring HATEOAS provides wrappers to represent resources, collections, and pages of data together with hypermedia links. When controllers return `EntityModel`, `CollectionModel`, or `PagedModel` with concrete generics, springdoc can describe the response structure in OpenAPI; HAL media types and relation names help clients understand how to read `_links` and `_embedded`. Verify both runtime JSON and generated documentation together to keep schemas, links, and the API contract consistent.

## References

- [Spring HATEOAS – Reference Documentation](https://docs.spring.io/spring-hateoas/docs/current/reference/html/)
- [Spring HATEOAS – `EntityModel`](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/EntityModel.html)
- [Spring HATEOAS – `CollectionModel` and `PagedModel`](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/CollectionModel.html)
- [Springdoc OpenAPI – Official Documentation](https://springdoc.org/)
- [Springdoc OpenAPI v2 – Modules and Spring HATEOAS Support](https://springdoc.org/v2/modules.html)
- [HAL Specification](https://stateless.group/hal_specification.html)

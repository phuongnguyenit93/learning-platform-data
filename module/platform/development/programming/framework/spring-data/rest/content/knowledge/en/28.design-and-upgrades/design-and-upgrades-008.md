# Distinguishing Legacy Examples Using Resource and PagedResources from the RepresentationModel API

## Objectives

Older Spring Data REST and Spring HATEOAS examples commonly use types such as `Resource`, `Resources`, `PagedResources`, and `ResourceSupport`. Starting in Spring HATEOAS 1.0, the API was redesigned around `RepresentationModel`, `EntityModel`, `CollectionModel`, and `PagedModel`.

When reading or upgrading legacy code, distinguish three tasks:

- **Renaming Java APIs:** replacing legacy wrappers, assemblers, and link builders with the new API.
- **Preserving representation semantics:** items, collections, and pages can still be rendered as HAL with `_links`, `_embedded`, and pagination metadata.
- **Preserving the HTTP contract:** media types, relation names, URIs, and status codes must remain compatible with clients.

Changing Java types does not mean changing the entire JSON contract. Still, verify actual runtime responses after upgrading because serializer, projection, assembler, and library version configurations can affect representations.

## 1. Why Did Spring HATEOAS Change Its API?

The legacy types used names like `Resource` and `Resources` to describe a resource or a collection resource. They were typically paired with `ResourceSupport`, `ResourceAssembler`, and `ControllerLinkBuilder`.

The new API introduces a clearer naming scheme:

- `RepresentationModel`: base class for representations carrying hypermedia links.
- `EntityModel<T>`: representation of a single object.
- `CollectionModel<T>`: representation of a collection.
- `PagedModel<T>`: representation of a collection with pagination metadata.

The new naming makes single, collection, and paged representations explicit in Java signatures while sharing the `RepresentationModel` abstraction for links and processors.

## 2. Legacy-to-New API Mapping Table

| Legacy API | New API | Meaning |
|---|---|---|
| `Resource<T>` | `EntityModel<T>` | Single entity with hypermedia links |
| `Resources<T>` | `CollectionModel<T>` | Collection representation |
| `PagedResources<T>` | `PagedModel<T>` | Collection with pagination metadata |
| `ResourceSupport` | `RepresentationModel<T>` | Base class for link-bearing representations |
| `ResourceAssembler<T, D>` | `RepresentationModelAssembler<T, D>` | Converts a domain object into a representation |
| `ResourceAssemblerSupport<T, D>` | `RepresentationModelAssemblerSupport<T, D>` | Base support class for writing assemblers |
| `ResourceProcessor<T>` | `RepresentationModelProcessor<T>` | Modifies a representation after creation |
| `ControllerLinkBuilder` | `WebMvcLinkBuilder` | Builds links from Spring MVC controller methods |
| `Resource.getContent()` | `EntityModel.getContent()` | Retrieves the wrapped entity from the model |
| `ResourceAssembler.toResource(...)` | `RepresentationModelAssembler.toModel(...)` | Creates a representation for an entity |
| `PagedResources.PageMetadata` | `PagedModel.PageMetadata` | Page metadata |

Package names also changed for several APIs. When updating imports, use the packages from the Spring HATEOAS version managed by Spring Boot rather than only substituting class names from the table.

## 3. Resource<T> Becomes EntityModel<T>

Legacy code typically created a resource wrapper:

    Resource<Order> resource =
        new Resource<>(order);

    resource.add(linkTo(
        methodOn(OrderController.class).getOrder(order.getId())
    ).withSelfRel());

With the new API:

    EntityModel<Order> model =
        EntityModel.of(order);

    model.add(linkTo(
        methodOn(OrderController.class).getOrder(order.getId())
    ).withSelfRel());

Key imports:

    import org.springframework.hateoas.EntityModel;
    import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
    import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

`EntityModel.of(order)` creates a representation wrapper for a single entity. One or more links can be added:

    model.add(
        linkTo(methodOn(OrderController.class)
            .getOrder(order.getId()))
            .withSelfRel()
    );

    model.add(
        linkTo(methodOn(OrderController.class)
            .getCustomer(order.getId()))
            .withRel("customer")
    );

The `self` link relation typically identifies the URI of the resource itself. The `customer` relation is an API-defined relation and must remain consistent with the client's hypermedia contract.

You do not need `EntityModel` if a controller returns a plain DTO without hypermedia. Choose the representation based on the contract the endpoint needs to provide.

## 4. Resources<T> Becomes CollectionModel<T>

Legacy code might wrap a list:

    Resources<Order> resources =
        new Resources<>(orders);

    resources.add(
        linkTo(methodOn(OrderController.class).getOrders())
            .withSelfRel()
    );

New code:

    CollectionModel<Order> model =
        CollectionModel.of(orders);

    model.add(
        linkTo(methodOn(OrderController.class).getOrders())
            .withSelfRel()
    );

If each item also needs links, use a collection of `EntityModel<Order>`:

    List<EntityModel<Order>> items = orders.stream()
        .map(order -> EntityModel.of(order))
        .toList();

    CollectionModel<EntityModel<Order>> model =
        CollectionModel.of(items);

You can add links to the collection:

    model.add(
        linkTo(methodOn(OrderController.class).getOrders())
            .withSelfRel()
    );

`CollectionModel<T>` represents a collection and collection-level links. Each inner `EntityModel<T>` can have its own links. Do not confuse collection links with item self links.

## 5. PagedResources<T> Becomes PagedModel<T>

For paginated data, the new API uses `PagedModel<T>`. This type carries content, navigation links, and page metadata.

Example manual creation:

    PagedModel.PageMetadata metadata =
        new PagedModel.PageMetadata(
            page.getSize(),
            page.getNumber(),
            page.getTotalElements(),
            page.getTotalPages()
        );

    PagedModel<EntityModel<Order>> model =
        PagedModel.of(orderModels, metadata);

The parameter order for `PageMetadata` is size, number, totalElements, and totalPages. Use metadata from the `Page` object to avoid miscalculating page counts manually.

In Spring MVC/Spring Data applications, you typically use `PagedResourcesAssembler` to convert `Page<T>` into `PagedModel` and generate pagination links:

    @RestController
    @RequestMapping("/orders")
    class OrderController {

        private final OrderRepository orders;
        private final OrderModelAssembler assembler;

        OrderController(
                OrderRepository orders,
                OrderModelAssembler assembler) {
            this.orders = orders;
            this.assembler = assembler;
        }

        @GetMapping
        PagedModel<EntityModel<Order>> getOrders(
                Pageable pageable,
                PagedResourcesAssembler<Order> pagedAssembler) {

            Page<Order> page = orders.findAll(pageable);

            return pagedAssembler.toModel(page, assembler);
        }
    }

`PagedResourcesAssembler` still contains the word Resources in its name in several Spring Data versions. It is a helper/adapter name; the representation type it produces under the new API is `PagedModel`.

Do not mechanically rename this helper if your current Spring Data version still provides it. Check the actual API signature of your dependency.

## 6. HAL JSON and the HTTP Contract

The new Java types can still serialize to HAL. For instance, an `EntityModel<Order>` can produce a response like:

    {
      "id": 501,
      "status": "PAID",
      "_links": {
        "self": {
          "href": "http://localhost:8080/orders/501"
        },
        "customer": {
          "href": "http://localhost:8080/orders/501/customer"
        }
      }
    }

A `CollectionModel<EntityModel<Order>>` can produce a collection representation:

    {
      "_embedded": {
        "orders": [
          {
            "id": 501,
            "status": "PAID",
            "_links": {
              "self": {
                "href": "http://localhost:8080/orders/501"
              }
            }
          }
        ]
      },
      "_links": {
        "self": {
          "href": "http://localhost:8080/orders"
        }
      }
    }

A `PagedModel` also includes page metadata:

    {
      "_embedded": {
        "orders": [
          { "id": 501, "status": "PAID" }
        ]
      },
      "_links": {
        "self": { "href": "http://localhost:8080/orders?page=0&size=20" },
        "next": { "href": "http://localhost:8080/orders?page=1&size=20" }
      },
      "page": {
        "size": 20,
        "totalElements": 41,
        "totalPages": 3,
        "number": 0
      }
    }

The responses above are illustrative examples. Actual relation names in `_embedded`, URIs, page counts, and links depend on API configuration and data.

When upgrading, verify:

- `Content-Type` remains the media type clients expect, such as `application/hal+json`.
- Relation names in `_embedded` remain unchanged.
- Link relations and hrefs remain unchanged.
- `page` metadata has accurate size, number, totalElements, and totalPages.
- Custom serializers or projections do not alter fields in the body.

Do not treat successful compilation as proof that the JSON contract did not change.

## 7. RepresentationModel Is the New Base Class

If an older class extended `ResourceSupport` to hold links, migrate it to `RepresentationModel`.

Legacy code:

    public class OrderModel extends ResourceSupport {
        private Long id;
        private String status;
    }

New code:

    public class OrderModel
            extends RepresentationModel<OrderModel> {

        private Long id;
        private String status;
    }

Links can be added with `add(...)`:

    model.add(
        linkTo(methodOn(OrderController.class)
            .getOrder(model.getId()))
            .withSelfRel()
    );

`RepresentationModel` is the base class for representations carrying hypermedia links. If you only need a plain DTO without links, inheriting from this class is not required.

## 8. ResourceAssembler Becomes RepresentationModelAssembler

Assemblers separate domain-to-representation conversion logic from controllers.

Legacy code:

    public class OrderResourceAssembler
            implements ResourceAssembler<Order, Resource<Order>> {

        @Override
        public Resource<Order> toResource(Order order) {
            Resource<Order> resource =
                new Resource<>(order);

            resource.add(
                linkTo(methodOn(OrderController.class)
                    .getOrder(order.getId()))
                    .withSelfRel()
            );

            return resource;
        }
    }

New code:

    @Component
    public class OrderModelAssembler
            implements RepresentationModelAssembler<
                Order,
                EntityModel<Order>
            > {

        @Override
        public EntityModel<Order> toModel(Order order) {
            return EntityModel.of(
                order,
                linkTo(methodOn(OrderController.class)
                    .getOrder(order.getId()))
                    .withSelfRel()
            );
        }
    }

Key changes:

- The interface is `RepresentationModelAssembler`.
- The method is `toModel(...)`, replacing `toResource(...)`.
- The output type is `EntityModel<Order>`.
- Links are added to the new representation.

The controller can use the assembler:

    @GetMapping("/{id}")
    EntityModel<Order> getOrder(@PathVariable Long id) {
        Order order = orders.findById(id)
            .orElseThrow(OrderNotFoundException::new);

        return assembler.toModel(order);
    }

This keeps controllers focused on fetching data and orchestration, while assemblers handle representation building.

## 9. ResourceAssemblerSupport Becomes RepresentationModelAssemblerSupport

If legacy code extended `ResourceAssemblerSupport`, the new API provides `RepresentationModelAssemblerSupport`.

Example:

    @Component
    public class OrderModelAssembler
            extends RepresentationModelAssemblerSupport<
                Order,
                EntityModel<Order>
            > {

        public OrderModelAssembler() {
            super(OrderController.class, EntityModel.class);
        }

        @Override
        public EntityModel<Order> toModel(Order order) {
            return EntityModel.of(
                order,
                linkTo(methodOn(OrderController.class)
                    .getOrder(order.getId()))
                    .withSelfRel()
            );
        }
    }

This base class assists in creating representations and linking to the corresponding controller. Adjust constructors, model types, and overridden methods according to the Spring HATEOAS version in use.

For simple assemblers, implementing `RepresentationModelAssembler` directly is often easier to read with less base-class coupling.

## 10. ResourceProcessor Becomes RepresentationModelProcessor

The legacy `ResourceProcessor` added or adjusted links after a representation was built. The new API is `RepresentationModelProcessor`.

Example:

    @Component
    public class OrderModelProcessor
            implements RepresentationModelProcessor<
                EntityModel<Order>
            > {

        @Override
        public EntityModel<Order> process(
                EntityModel<Order> model) {

            model.add(
                Link.of("/help/orders")
                    .withRel("help")
            );

            return model;
        }
    }

Processors are suitable for cross-cutting representation modifications. If a link depends on specific data or principal permissions, inspect the context and avoid adding links the caller is not permitted to invoke.

Do not use processors as a replacement for endpoint authorization. Hiding links from representations is not a security barrier; the server must still check permissions when requests are called directly.

## 11. ControllerLinkBuilder Becomes WebMvcLinkBuilder

Legacy code typically imported:

    import static org.springframework.hateoas.mvc.ControllerLinkBuilder.linkTo;
    import static org.springframework.hateoas.mvc.ControllerLinkBuilder.methodOn;

The new API uses:

    import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
    import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

Example:

    Link self = linkTo(
        methodOn(OrderController.class).getOrder(501L)
    ).withSelfRel();

    Link collection = linkTo(
        methodOn(OrderController.class).getOrders(
            Pageable.unpaged()
        )
    ).withRel("orders");

Using `methodOn(...)` builds links from the controller method's mapping, including path variables and request mapping metadata. Avoid constructing links from manual URL strings when controller mappings can be used.

For non-Spring MVC applications, other link builders may exist in the Spring HATEOAS server API. Choose the builder matching your active web stack and module.

## 12. Imports and Packages After Upgrading

Common new packages include:

    import org.springframework.hateoas.RepresentationModel;
    import org.springframework.hateoas.EntityModel;
    import org.springframework.hateoas.CollectionModel;
    import org.springframework.hateoas.PagedModel;
    import org.springframework.hateoas.Link;

    import org.springframework.hateoas.server.RepresentationModelAssembler;
    import org.springframework.hateoas.server.RepresentationModelProcessor;
    import org.springframework.hateoas.server.mvc.RepresentationModelAssemblerSupport;
    import org.springframework.hateoas.server.mvc.WebMvcLinkBuilder;

Legacy classes could reside in packages like `org.springframework.hateoas.mvc` or `org.springframework.hateoas` depending on the API. When upgrading, use your IDE's organize imports or compiler to locate exact missing imports.

Do not bulk-replace import names via plain text substitution if the same class name appears in another package or in application-defined classes.

## 13. Integration with Spring Data REST

Spring Data REST builds representations for repository resources automatically. Most applications do not need to wrap each entity manually in `EntityModel` when using the default repository exporter.

The new Spring HATEOAS types typically appear when:

- Writing custom controllers or custom repository handlers.
- Using Spring HATEOAS assemblers to construct representations.
- Building custom endpoints returning collections or pages.
- Customizing links and model processors.
- Combining repository data with DTOs or view models.

Example custom controller under the base path:

    @RepositoryRestController
    class OrderSearchController {

        private final OrderService orders;
        private final OrderModelAssembler assembler;

        @GetMapping("/orders/recent")
        ResponseEntity<CollectionModel<EntityModel<Order>>> recent() {
            List<EntityModel<Order>> models =
                orders.findRecent().stream()
                    .map(assembler::toModel)
                    .toList();

            CollectionModel<EntityModel<Order>> result =
                CollectionModel.of(models);

            result.add(
                linkTo(methodOn(OrderSearchController.class)
                    .recent())
                    .withSelfRel()
            );

            return ResponseEntity.ok(result);
        }
    }

This is an illustrative custom operation example. Verify base path, controller annotations, repository mappings, and message converters in your application. Do not manually add wrappers to default exporter endpoints if the framework already produces the desired HAL representation.

## 14. Step-by-Step Upgrade

When migrating a legacy codebase to the new API:

1. Identify the Spring Boot, Spring Data, and Spring HATEOAS versions selected by dependency management.
2. Locate imports and signatures using `Resource`, `Resources`, `PagedResources`, and `ResourceSupport`.
3. Replace item wrappers with `EntityModel`.
4. Replace collection wrappers with `CollectionModel`.
5. Replace paged wrappers with `PagedModel`.
6. Replace the base class with `RepresentationModel` when a class actually needs to hold links.
7. Migrate assemblers to `RepresentationModelAssembler` and change `toResource` to `toModel`.
8. Migrate processors to `RepresentationModelProcessor`.
9. Migrate controller link builders to `WebMvcLinkBuilder` when using Spring MVC.
10. Check pagination helpers like `PagedResourcesAssembler` against your version; do not rename them if the library still provides that class.
11. Compile to uncover remaining legacy imports and generic types.
12. Run integration tests and compare HAL responses, links, relations, page metadata, and media types.

Do not upgrade Spring HATEOAS independently to an arbitrary version if the Spring Boot BOM manages compatibility. Use the release train matching your application's Spring Boot version.

## 15. Post-Migration Testing

Verify both Java types and HTTP representations.

### 15.1. Assembler Unit Tests

- `toModel(entity)` returns the expected content.
- The self link points to the correct item URI.
- Related links use the expected relation names.
- Links do not appear if policy forbids the caller from performing that action.

### 15.2. Controller Integration Tests

MockMvc example:

    mockMvc.perform(get("/orders/501")
            .accept(MediaTypes.HAL_JSON))
        .andExpect(status().isOk())
        .andExpect(content().contentTypeCompatibleWith(
            MediaTypes.HAL_JSON
        ))
        .andExpect(jsonPath("$._links.self.href").exists());

For collections/pages:

- Verify relations in `_embedded`.
- Verify self, next, and prev links.
- Verify `page.size`, `page.number`, `page.totalElements`, and `page.totalPages`.
- Verify sort and pagination parameters are preserved in links.

### 15.3. Client Contract Tests

If clients already depend on HAL responses:

- Compare relation names before and after migration.
- Compare hrefs and URI templates.
- Compare JSON fields within entities.
- Compare media types.
- Compare page metadata and navigation links.
- Check projections/excerpts if endpoints use them.

The goal is ensuring Java migration does not inadvertently break the HTTP contract clients rely on.

## 16. Common Pitfalls

| Symptom | Causes to Check |
|---|---|
| `Resource` or `Resources` no longer compiles | Migrate to `EntityModel` or `CollectionModel` |
| `PagedResources` no longer compiles | Use `PagedModel` |
| `ResourceSupport` no longer compiles | Use `RepresentationModel` |
| `toResource()` no longer exists in assembler | Rename to `toModel()` |
| ControllerLinkBuilder import error | Use `WebMvcLinkBuilder` in Spring MVC |
| Assembler generic types mismatch | Update output type to EntityModel or corresponding RepresentationModel |
| Page loses next/prev links | Verify proper use of PagedResourcesAssembler/PagedModel and Pageable |
| `_embedded` relation renamed | Check relation naming, collection model, and HAL configuration |
| JSON body changed after upgrade | Inspect serializers, wrapper types, projections, and media types |
| Compiles cleanly yet clients fail | Contract tests did not verify links, media types, or page metadata |
| Dependency version conflict | Spring HATEOAS upgraded independently of Spring Boot/Spring Data release train |
| Incorrect link URLs | Check controller mappings, base path, proxies, and WebMvcLinkBuilder |

## 17. Checklist

1. Identify the active Spring Boot and Spring HATEOAS versions.
2. Map `Resource` to `EntityModel`.
3. Map `Resources` to `CollectionModel`.
4. Map `PagedResources` to `PagedModel`.
5. Map `ResourceSupport` to `RepresentationModel`.
6. Migrate assemblers to `RepresentationModelAssembler` and `toModel`.
7. Migrate processors to `RepresentationModelProcessor`.
8. Migrate ControllerLinkBuilder to WebMvcLinkBuilder in Spring MVC.
9. Check PagedResourcesAssembler against dependency version; this helper may keep its legacy name.
10. Update package imports and generic types.
11. Compile and run assembler/controller tests.
12. Compare HAL links, relations, embedded content, and page metadata.
13. Verify media types and client contracts.
14. Use Spring Boot dependency management to maintain Spring Data/HATEOAS compatibility.
15. Update custom representations only where the application explicitly constructs models; do not unnecessarily re-wrap default repository exporter outputs.

## References

- [Spring HATEOAS — Migration Guide](https://docs.spring.io/spring-hateoas/docs/current/reference/html/)
- [Spring HATEOAS — Representation Models](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#fundamentals)
- [Spring HATEOAS — Building Links](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#server.link-builder)
- [Spring HATEOAS — Representation Model Assemblers](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#server.assemblers)
- [Spring Data REST — Configuring the REST representation](https://docs.spring.io/spring-data/rest/reference/representations.html)
- [Spring Data REST — Repository resources](https://docs.spring.io/spring-data/rest/reference/repository-resources.html)
- [Spring Boot — Spring HATEOAS support](https://docs.spring.io/spring-boot/reference/web/spring-hateoas.html)
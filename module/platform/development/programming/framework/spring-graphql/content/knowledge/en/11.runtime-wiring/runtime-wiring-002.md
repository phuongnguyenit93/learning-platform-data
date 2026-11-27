# DataFetcher registration in Spring for GraphQL

In GraphQL Java, a **DataFetcher** is the component that provides a value for a field when GraphQL executes an operation. The SDL schema describes what a field is named, what arguments it takes, and what type it returns; the DataFetcher performs the data retrieval or invokes business logic to produce that value.

Spring for GraphQL supports multiple ways to register a DataFetcher. With controllers, annotations such as `@QueryMapping`, `@MutationMapping`, and `@SchemaMapping` allow Spring to automatically detect methods and register the corresponding handlers. When GraphQL Java-level configuration is needed, `RuntimeWiringConfigurer` can be used to attach a DataFetcher directly to a type and field in the schema.

## What does a DataFetcher do?

Every field executed by GraphQL needs a way to obtain its value. For a root field like `Query.product`, the DataFetcher might call a service to look up a product by ID. For a nested field like `Product.seller`, the DataFetcher can use the parent object to find the associated seller.

Example SDL:

```graphql
type Query {
  product(id: ID!): Product
  products: [Product!]!
}

type Product {
  id: ID!
  name: String!
  seller: Seller
}

type Seller {
  id: ID!
  name: String!
}
```

In this schema, the `product`, `products`, and `seller` fields all need values when selected by the client. A DataFetcher can be explicitly registered for all three fields, or GraphQL Java can use its default mechanism to read properties from the source object when no dedicated DataFetcher is registered.

A DataFetcher is not where all business logic must live. Keep DataFetchers thin: read arguments or the source object, call the appropriate service, and return a result matching the type declared in the SDL.

## Registering a DataFetcher with RuntimeWiringConfigurer

`RuntimeWiringConfigurer` is Spring for GraphQL's extension point for customizing GraphQL Java runtime wiring. You can declare this bean in a `@Configuration` class and then register DataFetchers by type name and field name in the schema.

```java
import graphql.schema.DataFetcher;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.graphql.execution.RuntimeWiringConfigurer;

import java.util.List;

@Configuration
public class GraphQlRuntimeConfiguration {

    @Bean
    RuntimeWiringConfigurer productDataFetchers(
            ProductService productService,
            SellerService sellerService) {

        DataFetcher<Product> productById = environment -> {
            String id = environment.getArgument("id");
            return productService.findById(id).orElse(null);
        };

        DataFetcher<List<Product>> products = environment ->
                productService.findAll();

        DataFetcher<Seller> seller = environment -> {
            Product product = environment.getSource();
            return sellerService.findById(product.getSellerId()).orElse(null);
        };

        return builder -> builder
                .type("Query", type -> type
                        .dataFetcher("product", productById)
                        .dataFetcher("products", products))
                .type("Product", type -> type
                        .dataFetcher("seller", seller));
    }
}
```

In this example:

- `type("Query", ...)` selects the `Query` object type in the SDL.
- `dataFetcher("product", productById)` registers a DataFetcher for the `Query.product` field.
- `dataFetcher("products", products)` registers a DataFetcher for the `Query.products` field.
- `type("Product", ...)` selects the `Product` object type; the `seller` DataFetcher handles the `Product.seller` field.
- `ProductService` and `SellerService` are injected from the Spring container, allowing the DataFetchers to invoke business logic without managing dependency lifecycles manually.

Type and field names must match the SDL. If the schema renames `product` to `findProduct` while runtime wiring still registers `product`, the configuration no longer accurately reflects the contract. You should let the application validate the schema at startup and write tests confirming that key fields are registered.

## What data does DataFetchingEnvironment provide?

When GraphQL invokes a DataFetcher, it passes in a `DataFetchingEnvironment`. This object contains information about the field currently being executed and the context of the operation.

| Method | Description |
| --- | --- |
| `getSource()` | The source value provided by the parent field. For root fields, this value depends on the root object passed to execution and is typically `null` unless the application configures it otherwise. |
| `getArgument("name")` | Retrieves the value of an argument by name. |
| `getArguments()` | Retrieves all arguments of the field as a map. |
| `getGraphQlContext()` | Retrieves the shared GraphQL context for the request execution. |
| `getLocalContext()` | Retrieves the local context passed down from the parent execution step to the child field. |
| `getSelectionSet()` | Inspects the child fields selected by the client. |
| `getDataLoader("name")` | Retrieves a DataLoader registered with the request's registry. |
| `getExecutionStepInfo()` | Retrieves information about the field's position and type in the execution tree. |

### Reading arguments

For a field with arguments:

```graphql
type Query {
  product(id: ID!): Product
}
```

The DataFetcher reads the argument by name:

```java
DataFetcher<Product> productById = environment -> {
    String id = environment.getArgument("id");
    return productService.findById(id).orElse(null);
};
```

The argument name in `getArgument("id")` must match the name declared in the SDL. For complex input objects, you can retrieve the entire value with `getArgument("input")`; depending on mapping configuration, the value may be represented as a map or converted into an appropriate Java type.

### Reading the source for nested fields

For the `Product.seller` field, the source is the `Product` object resolved in the parent step. The DataFetcher uses the source to look up related data:

```java
DataFetcher<Seller> sellerFetcher = environment -> {
    Product product = environment.getSource();
    return sellerService.findById(product.getSellerId()).orElse(null);
};
```

This distinguishes two cases: `getArgument()` reads data sent by the client to the field, whereas `getSource()` reads the source passed by GraphQL from the parent step. Do not assume every field has the same kind of source; root fields usually have no parent domain object and may receive a `null` source.

### Reading the GraphQL context

The context is used to share per-request information such as the authenticated principal, tenant, or correlation ID. This information is typically added by an interceptor or request-handling component before the DataFetcher runs.

```java
DataFetcher<List<Product>> productsFetcher = environment -> {
    String tenantId = environment.getGraphQlContext().get("tenantId");
    return productService.findAllForTenant(tenantId);
};
```

Context must be populated from trusted server-side sources. Never use a role or tenant value self-reported by the client in an argument as a substitute for authentication. For data that varies per request, avoid storing it in mutable fields of a singleton DataFetcher or singleton service.

## Default PropertyDataFetcher

Not every field requires an explicit DataFetcher registration. GraphQL Java provides `PropertyDataFetcher` as the default mechanism for object fields when no dedicated fetcher exists. It looks up values from the source object via properties, getters, or map keys following GraphQL Java's property access rules.

Java example:

```java
public class Product {
    private String id;
    private String name;

    public String getId() {
        return id;
    }

    public String getName() {
        return name;
    }
}
```

When the DataFetcher for `Query.product` returns a `Product`, GraphQL can automatically extract `id` and `name` from the corresponding getters without registering a separate fetcher for each field.

`PropertyDataFetcher` is suitable when a field directly reflects data already present in the source object. Register a dedicated DataFetcher when you need to call a service/repository, apply business rules, transform data, check permissions, or compute a value.

## Synchronous and asynchronous DataFetchers

A DataFetcher can return a synchronous value or an asynchronous result. For a simple in-memory lookup, returning the object directly is sufficient. When calling asynchronous I/O services, you can return a `CompletionStage` or `CompletableFuture` so GraphQL continues processing once the result is ready.

Example when a service already provides an asynchronous method:

```java
DataFetcher<CompletableFuture<Product>> productFetcher = environment -> {
    String id = environment.getArgument("id");
    return productService.findByIdAsync(id);
};
```

`CompletableFuture` allows GraphQL to coordinate results without the DataFetcher blocking a thread while waiting on I/O. If you create a future yourself with `supplyAsync`, use a managed executor with appropriate bounds instead of pushing all work onto the common pool by default.

For applications using Reactor, Spring for GraphQL also supports reactive types at the corresponding integration points. Keep return types consistent with the stack in use and avoid switching back and forth between blocking and reactive styles without clear boundaries.

## Returning errors and partial data

When a DataFetcher throws an exception, GraphQL records an execution error at the field being executed. Spring for GraphQL lets you map exceptions to GraphQL errors through mechanisms such as `DataFetcherExceptionResolver`, giving you control over the message, error code, and details exposed to the client.

In some scenarios, a DataFetcher can return a `DataFetcherResult` to combine data and errors in the same result:

```java
import graphql.GraphqlErrorBuilder;
import graphql.execution.DataFetcherResult;

DataFetcherResult<Product> result = DataFetcherResult.<Product>newResult()
        .data(product)
        .error(GraphqlErrorBuilder.newError(environment)
                .message("Some additional information could not be loaded")
                .build())
        .build();
```

`DataFetcherResult` is useful when a field can return primary data while also reporting supplementary errors or metadata. Design nullability in the SDL carefully, because an error on a Non-Null field can propagate null up to parent fields. Never include stack traces, SQL statements, tokens, or infrastructure details in errors returned to clients.

## DataFetchers for nested fields and the N+1 problem

GraphQL executes fields according to the selection set. If a client requests a list of many Products and each Product includes the `seller` field, the `Product.seller` DataFetcher may be invoked once per Product.

Example query:

```graphql
query ProductsWithSellers {
  products {
    id
    name
    seller {
      id
      name
    }
  }
}
```

If `products` returns 100 products and every execution of `seller` triggers a separate database query, the system can generate 1 query for products plus 100 queries for sellers. This is the N+1 problem.

Registering a DataFetcher properly does not by itself solve N+1. You can use a DataLoader or `@BatchMapping` in Spring for GraphQL to batch seller loads together. DataLoaders are typically registered per request so that keys within the same operation are coalesced and results are mapped back to the right source objects.

When possible, use `@BatchMapping` for relationship fields that fit Spring's controller model. If using a low-level DataFetcher, obtain the DataLoader from `DataFetchingEnvironment` and call `load(key)` rather than calling the repository directly for each parent.

## Choosing RuntimeWiringConfigurer or annotation mapping?

Spring for GraphQL offers two common styles for registering field-handling logic:

| Approach | When Suitable |
| --- | --- |
| `@QueryMapping`, `@MutationMapping`, `@SubscriptionMapping` | Root operations implemented in a Spring controller; you want dependency injection and method-style handlers. |
| `@SchemaMapping` | Object type fields needing a custom resolver, especially relationships or computed fields. |
| `RuntimeWiringConfigurer` + `DataFetcher` | Direct customization of runtime wiring, GraphQL Java integration, or programmatic fetcher registration. |

Annotation mapping example:

```java
@Controller
public class ProductController {

    private final ProductService productService;

    public ProductController(ProductService productService) {
        this.productService = productService;
    }

    @QueryMapping
    public Product product(@Argument String id) {
        return productService.findById(id).orElse(null);
    }
}
```

Spring for GraphQL automatically detects the controller and registers the method as the DataFetcher for the corresponding field. If you already use annotation mapping for `Query.product`, do not simultaneously register another DataFetcher for that same field in `RuntimeWiringConfigurer`; having two mechanisms configure the same field can make the active handler depend on wiring order and complicate maintenance.

Both approaches can coexist in the same application as long as they serve different fields. For instance, a controller can handle `Query.product` while `RuntimeWiringConfigurer` registers a custom scalar or a DataFetcher for a dedicated field without an annotation handler.

## Testing DataFetcher registration

Tests should verify that schema fields actually invoke the expected logic and return responses with the right structure. With Spring for GraphQL, `GraphQlTester` lets you send operations and assert on the returned data:

```java
@Test
void productQueryUsesRegisteredFetcher() {
    graphQlTester.document("""
        query {
          product(id: "p-100") {
            id
            name
          }
        }
        """)
        .execute()
        .path("product.id")
        .entity(String.class)
        .isEqualTo("p-100");
}
```

Beyond successful outcomes, verify that:

- Field names in the SDL match the names used in `.dataFetcher(...)`.
- Arguments are read properly and handled when missing or invalid.
- Nested fields receive the expected source object.
- Not-found values conform to the declared nullability.
- Exceptions are mapped to appropriate public errors.
- Asynchronous DataFetchers complete properly and handle future failures.
- Context and access permissions are enforced correctly per request.
- DataLoaders or batch fetchers reduce repository calls when returning lists.

When testing a `RuntimeWiringConfigurer` bean, initialize `GraphQlSource` or the Spring application context to confirm the configuration is actually loaded. Unit-testing a DataFetcher lambda in isolation does not prove it was registered into the running schema.

## Common issues

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Field returns `null` even though the service has data | DataFetcher registered on the wrong type/field or wrong source | Cross-check the SDL, mapping names, and `getSource()`. |
| `getArgument()` returns null | Wrong argument name, nullable input, or client omitted the value | Check the SDL, operation, and variables. |
| DataFetcher is never called | Controller mapping or wiring not registered, or the operation did not select the field | Check startup configuration, schema, and query. |
| Nested field fails to resolve | Parent object lacks the matching property and has no dedicated DataFetcher | Use `@SchemaMapping` or register a DataFetcher for that field. |
| Field is handled by an unexpected handler | Annotation mapping and `RuntimeWiringConfigurer` both register the same field | Choose a single mechanism as the sole handler for the field. |
| List query triggers many database queries | Relationship resolver calls the repository individually per object | Use DataLoader or `@BatchMapping`. |
| Internal errors appear in the response | Exception is not mapped according to API policy | Configure `DataFetcherExceptionResolver` and control error details. |

## Key takeaways

A DataFetcher is the component that supplies the value for each field during GraphQL execution. It receives a `DataFetchingEnvironment`, from which it reads arguments, the source object, the GraphQL context, and selection information. GraphQL Java can use the default `PropertyDataFetcher` for fields that directly reflect properties of the source object.

In Spring for GraphQL, use `RuntimeWiringConfigurer` to register DataFetchers directly by type and field; use `@QueryMapping`, `@MutationMapping`, or `@SchemaMapping` when implementing handlers with controller annotations. Pick one mechanism per field, keep DataFetchers thin, handle errors safely, and use DataLoader or `@BatchMapping` when nested fields carry an N+1 risk.

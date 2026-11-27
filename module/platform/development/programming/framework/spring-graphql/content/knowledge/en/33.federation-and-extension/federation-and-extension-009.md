# Gateway and subgraph in GraphQL Federation

GraphQL Federation allows multiple independent GraphQL services to contribute to a single unified API. Each service is called a **subgraph** and owns a portion of the schema and its domain data. A **gateway/router** sits in front of the subgraphs, composes their schemas into a supergraph, plans query execution, calls the required subgraphs, and merges results for the client.

Spring for GraphQL integrates with the `federation-jvm` library to build a Spring GraphQL service that acts as a subgraph. This integration provides `FederationSchemaFactory` and `@EntityMapping` to handle entity representations sent by the gateway. The gateway is a separate process, which can be Apollo Router, GraphOS Router, or another Federation-compatible router.

## 1. Why do we need a gateway and subgraphs?

In an e-commerce system, data may be managed by multiple teams:

- Product service manages products, pricing, and catalogs.
- Review service manages product reviews.
- Account service manages customers and profiles.
- Order service manages orders and transaction statuses.

If each service only exposes its own GraphQL endpoint, the client has to know which endpoint holds which data, make multiple calls itself, and merge the results manually. Federation places a router in front so clients only call one GraphQL endpoint.

For example, a client wants to fetch products along with their reviews:

```graphql
query ProductDetails {
    products {
        id
        name
        price
        reviews {
            id
            rating
            comment
        }
    }
}
```

Fields `products`, `name`, and `price` may be owned by the Products subgraph. The `reviews` field is owned by the Reviews subgraph. The gateway understands the relationship between the two schemas and calls both services to produce a single response.

## 2. Distinguishing gateway, subgraph, and supergraph

| Component | Role | Primary responsibility |
|---|---|---|
| Subgraph | GraphQL service for a domain | Owns part of the schema, resolvers, and data. |
| Gateway/router | Unified GraphQL entry point | Composition, query planning, routing, and response merging. |
| Supergraph | Linked schema of the entire system | Describes types, fields, entities, and responsible subgraphs. |
| Subgraph schema | Schema published by a single service | Describes the portion of the graph contributed by that service. |

The supergraph is not a separate server or database. It is the composed schema along with routing metadata so the router knows which subgraph handles which field.

A Federation gateway also differs from a typical HTTP reverse proxy. A reverse proxy forwards requests to services by URL/path. A Federation router understands GraphQL schemas and selection sets, can split one operation into multiple sub-GraphQL requests, and merges results according to entity relationships.

## 3. Overall architecture

```text
                         GraphQL client
                               |
                               v
                     Gateway / Graph Router
                     - supergraph schema
                     - query planner
                     - subgraph routing
                     - response merge
                        /          \
                       /            \
                      v              v
             Products subgraph   Reviews subgraph
             Spring GraphQL      Spring GraphQL
             Product fields      Product.reviews
                  |                   |
                  v                   v
             Product DB           Review DB
```

Services can be deployed, scaled, and released independently. The gateway provides a unified API for clients, while each subgraph retains ownership of its own data and domain logic.

## 4. What does the gateway do?

A gateway/router typically performs the following tasks:

1. Loads the composed supergraph schema.
2. Receives GraphQL operations from clients.
3. Validates operations against the supergraph schema.
4. Builds a query plan determining which fields require calling which subgraphs.
5. Sends sub-requests to subgraphs, running in parallel where data dependencies allow.
6. Passes entity representations so other subgraphs can resolve the fields they own.
7. Merges results and errors into a GraphQL response.
8. Enforces router-layer policies such as request limits, tracing, timeouts, and routing configuration.

The gateway should not become a home for business rules of Product, Order, or Review. Domain rules belong to the subgraph that owns the data.

## 5. What is a subgraph responsible for?

A subgraph must:

- Publish an SDL describing the types and fields owned by the service.
- Declare entity keys if types need to be referenced by other subgraphs.
- Provide resolvers for fields owned by the service.
- Be able to load entities from representations sent by the gateway.
- Return data and errors according to the GraphQL contract.
- Protect data with authorization, tenant isolation, and service-to-service security.
- Maintain schema compatibility so the supergraph can compose.

A subgraph does not need to know what the client's original query looked like. It receives a sub-GraphQL request from the gateway and carries out its assigned portion of work.

## 6. Entities as the bridge between subgraphs

In Federation, an object type to which multiple subgraphs contribute fields is typically modeled as an **entity**. An entity has one or more keys that uniquely identify an instance.

For example, the Product entity has key `id`:

```graphql
type Product @key(fields: "id") {
    id: ID!
    name: String!
    price: Float!
}
```

`@key(fields: "id")` informs the gateway that a Product can be identified by the `id` field. Other subgraphs can define additional fields on the same Product entity; the gateway uses this key to ask the owning subgraph to resolve data.

An entity's representation takes a JSON form:

```json
{
  "__typename": "Product",
  "id": "product-101"
}
```

- `__typename` identifies the entity type.
- `id` is the key field declared in `@key`.

For a composite key, the representation must contain every field in the key's field set.

## 7. `@key` and field ownership

A supergraph may have multiple subgraphs defining the Product entity, but every field must have a clear owner.

For example:

| Subgraph | Entity | Owned fields |
|---|---|---|
| Products | `Product @key(fields: "id")` | `id`, `name`, `price`. |
| Reviews | `Product @key(fields: "id")` | `id`, `reviews`. |

Key fields serve as shared identification. Business fields like `name`, `price`, and `reviews` are assigned to their respective subgraphs.

In Federation 2, subgraphs can declare the same entity type with the same key. There is no need to use `@extends`/`@external` syntax just to indicate extending an entity as was common in Federation 1. `@extends` primarily serves Federation 1-style schemas; `@external` is still used in Federation 2 for fields referenced by `@requires` or `@provides` that are not owned by the current subgraph.

In Federation 2, fields included in `@key` are automatically considered shareable, so `id` in this example does not need `@shareable` added. If multiple subgraphs share responsibility for resolving another non-key field, use `@shareable` in every subgraph defining that field and ensure resolvers have compatible semantics. Do not mark a field `@shareable` merely to bypass composition errors.

## 8. Composition produces the supergraph schema

Composition is the step that combines subgraph schemas and checks compatibility. The result is a supergraph schema containing metadata telling the router how to resolve fields.

Basic workflow:

```text
Products schema -----+
                     |
Reviews schema ------+----> Composition ----> supergraph.graphql
                     |                            |
Accounts schema -----+                            v
                                             Gateway/router
```

Composition can run through the Apollo GraphOS build pipeline or with the Rover CLI. In a CI/CD workflow, validate composition before deploying a new schema. In production, generate and verify the supergraph artifact in the build/release pipeline; do not rely on the router dynamically introspecting and composing all subgraphs on every startup.

Some common composition errors:

- Two subgraphs define the same field without proper shareable declarations.
- Return types or argument types of a shared field are incompatible.
- Entity keys are inconsistent across subgraphs.
- A field cannot be resolved in some valid query plans.
- A subgraph uses a directive not supported by the selected Federation version.

## 9. Federation 2 and the `@link` directive

Federation 2 requires schemas to declare `@link` to opt in to the Federation specification and import the directives used.

Example:

```graphql
extend schema
    @link(
        url: "https://specs.apollo.dev/federation/v2.0"
        import: ["@key"]
    )
```

If the schema also uses `@shareable`, `@requires`, or other directives, include them in the `import` list or use their corresponding namespaces per Federation rules.

`@link` indicates the schema uses Federation 2. The version in the URL must be compatible with the composition and router versions. Do not pick a Federation version newer than what the router or subgraph library supports.

## 10. Example with two subgraphs: Products and Reviews

The Products subgraph owns product details:

```graphql
extend schema
    @link(
        url: "https://specs.apollo.dev/federation/v2.0"
        import: ["@key"]
    )

type Query {
    products: [Product!]!
    product(id: ID!): Product
}

type Product @key(fields: "id") {
    id: ID!
    name: String!
    description: String
    price: Float!
}
```

The Reviews subgraph contributes the `reviews` field to the same Product entity:

```graphql
extend schema
    @link(
        url: "https://specs.apollo.dev/federation/v2.0"
        import: ["@key"]
    )

type Query {
    reviewsByProduct(productId: ID!): [Review!]!
}

type Product @key(fields: "id") {
    id: ID!
    reviews: [Review!]!
}

type Review {
    id: ID!
    rating: Int!
    comment: String
}
```

`Product.id` is the key for the Reviews subgraph to identify the entity. The Products subgraph owns `name`, `description`, and `price`; the Reviews subgraph owns `reviews`.

In a real schema, subgraphs must have valid SDL with GraphQL root operations and supported directives. A subgraph may primarily serve entity resolution without its own business queries; inspect the final schema generated by the federation library via `_service` and `_entities`.

Resolvers in the Products subgraph can expose root queries and load Product by entity key:

```java
import java.util.List;
import java.util.Optional;

import org.springframework.graphql.data.federation.EntityMapping;
import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.stereotype.Controller;

@Controller
class ProductsController {

    private final ProductCatalog products;

    ProductsController(ProductCatalog products) {
        this.products = products;
    }

    @QueryMapping
    List<Product> products() {
        return products.findAll();
    }

    @EntityMapping(name = "Product")
    Product productEntity(@Argument("id") String id) {
        return products.findById(id).orElse(null);
    }
}
```

`ProductCatalog` is the service/repository adapter for the Products domain. When the router needs fields owned by the Products subgraph from a representation, `productEntity` loads the real Product from the service's data store.

Types used in the example:

```java
import java.util.List;
import java.util.Optional;

public record Product(String id, String name, String description, double price) {}

public interface ProductCatalog {
    List<Product> findAll();
    Optional<Product> findById(String id);
}
```

## 11. How does Spring for GraphQL support subgraphs?

Spring for GraphQL integrates with the `federation-jvm` library, built on GraphQL Java. This library turns a regular GraphQL schema into a Federation-compatible schema by adding required Federation components, including directives, the `_Any` scalar, the `_Entity` union, and entity resolvers. Apollo's compatibility table currently lists Spring GraphQL alongside `federation-jvm` and marks Federation 1/2 components such as `_service`, `@key`, `@link`, `@shareable`, `@requires`, `@provides`, and extension directives as supported. When using newer directives, still check the library and router versions you are deploying.

Spring provides two key components:

| Component | Role |
|---|---|
| `FederationSchemaFactory` | Creates a federated `GraphQLSchema`, registers the `_entities` resolver and type resolver. |
| `@EntityMapping` | Maps a Java method to load an entity from a representation sent by the gateway. |

Remaining fields can still use `@QueryMapping`, `@SchemaMapping`, `@BatchMapping`, and DataLoader like a standard Spring GraphQL service.

Spring for GraphQL supports implementing subgraphs. The gateway/router is deployed separately and can use Apollo Router or a Federation-compatible implementation.

## 12. Adding the Federation JVM dependency

In addition to the Spring GraphQL starter, add the Federation JVM library to any service that needs to run as a subgraph:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-graphql'
    implementation 'com.apollographql.federation:federation-graphql-java-support:<compatible-version>'
}
```

Replace `<compatible-version>` with a published version compatible with the GraphQL Java version used by Spring for GraphQL. Do not upgrade GraphQL Java independently if Spring Boot dependency management already manages that version.

The `federation-graphql-java-support` artifact provides Federation integration for GraphQL Java. Spring for GraphQL uses this library via `FederationSchemaFactory`.

## 13. Configuring `FederationSchemaFactory`

With Spring Boot, declare a `FederationSchemaFactory` bean and a `GraphQlSourceBuilderCustomizer` to use the factory when creating the schema:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.boot.autoconfigure.graphql.GraphQlSourceBuilderCustomizer;
import org.springframework.graphql.data.federation.FederationSchemaFactory;

@Configuration(proxyBeanMethods = false)
class FederationConfiguration {

    @Bean
    FederationSchemaFactory federationSchemaFactory() {
        return new FederationSchemaFactory();
    }

    @Bean
    GraphQlSourceBuilderCustomizer federationSchemaCustomizer(
            FederationSchemaFactory factory) {

        return builder -> builder.schemaFactory(factory::createGraphQLSchema);
    }
}
```

The `GraphQlSourceBuilderCustomizer` import above is for Spring Boot 3.x. With Spring Boot 4.x, the corresponding package is `org.springframework.boot.graphql.autoconfigure.GraphQlSourceBuilderCustomizer`. `FederationSchemaFactory` remains in package `org.springframework.graphql.data.federation`.

Once configured, Spring Boot uses the factory to create the Federation schema. `FederationSchemaFactory` detects `@EntityMapping` methods in annotated controllers and registers the entity resolution logic.

## 14. `@EntityMapping` handles entity representations

When the gateway calls `_entities`, it sends a list of representations. Each representation contains `__typename` and key fields. `@EntityMapping` maps a Java method to locate or construct the corresponding entity.

Example in the Reviews subgraph:

```java
import org.springframework.graphql.data.federation.EntityMapping;
import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.stereotype.Controller;

public record Product(String id) {}

@Controller
class ProductEntityController {

    @EntityMapping
    Product product(@Argument("id") String id) {
        return new Product(id);
    }
}
```

The method name `product` is converted into the `Product` entity type by default convention. You can specify the entity name explicitly with `@EntityMapping(name = "Product")` if the method does not follow the naming convention.

In this example, the Reviews subgraph does not own the entire Product. It only needs a reference with `id` so the subgraph's field resolvers can resolve Review data. In a real system, entity mapping should enforce access policies and verify existence when required by business logic.

## 15. Resolving fields owned by the subgraph

Once the Product entity is constructed from a representation, `@SchemaMapping` can handle the `reviews` field:

```java
import java.util.List;

import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.graphql.data.method.annotation.SchemaMapping;
import org.springframework.stereotype.Controller;

@Controller
class ProductReviewController {

    private final ReviewQueryService reviews;

    ProductReviewController(ReviewQueryService reviews) {
        this.reviews = reviews;
    }

    @QueryMapping
    List<Review> reviewsByProduct(@Argument String productId) {
        return reviews.findByProductId(productId);
    }

    @SchemaMapping(typeName = "Product", field = "reviews")
    List<Review> reviews(Product product) {
        return reviews.findByProductId(product.id());
    }
}
```

`@EntityMapping` answers the question "which entity does this representation correspond to?". `@SchemaMapping` answers the question "what is the value of the field owned by the Reviews subgraph?". Both methods have distinct responsibilities and collaborate so the gateway can fetch the data.

Model and service used by the controller:

```java
import java.util.List;

public record Review(String id, int rating, String comment) {}

public interface ReviewQueryService {
    List<Review> findByProductId(String productId);
}
```

## 16. Entity mapping can accept the full representation

If an entity uses a composite key or needs multiple details from the representation, the method can accept `Map<String, Object>`:

In this example, `Product` is an alternative model adding `region`; the `region` field must also appear in the SDL and in the subgraph's `@key`.

The corresponding SDL declares both fields in the key:

```graphql
type Product @key(fields: "id region") {
    id: ID!
    region: String!
}
```

```java
import java.util.Map;

import org.springframework.graphql.data.federation.EntityMapping;

public record Product(String id, String region) {}

@EntityMapping(name = "Product")
Product product(Map<String, Object> representation) {
    String id = (String) representation.get("id");
    String region = (String) representation.get("region");

    return new Product(id, region);
}
```

`@EntityMapping` methods can accept parameters such as:

- `@Argument` to extract a bound and type-converted key field.
- `Map<String, Object>` to read the entire representation.
- `List<Map<String, Object>>` when handling multiple representations in one method.
- `@ContextValue`, `@LocalContextValue`, `GraphQLContext`.
- `Principal` or `@AuthenticationPrincipal` if a Spring Security context is available.
- `DataLoader<I, E>` to load entities asynchronously or in batches.
- `DataFetchingFieldSelectionSet` and `DataFetchingEnvironment` when execution info is needed.

Methods can return the entity directly, `Mono`, `CompletableFuture`, or `Callable` depending on the appropriate processing model.

If `@EntityMapping` throws an exception, you can use `@GraphQlExceptionHandler` in the same controller or `@ControllerAdvice` to map the exception to a `GraphQLError`. That error is included in the `_entities` response so the gateway can handle it as a GraphQL error from the subgraph.

## 17. Batch loading multiple entities

The gateway can send multiple representations of the same entity type in a single `_entities` request. Spring for GraphQL allows an `@EntityMapping` method to accept a list of IDs and return a `List` or `Flux` of entities in the exact representation order.

Example:

```java
import java.util.List;

import org.springframework.graphql.data.federation.EntityMapping;
import org.springframework.graphql.data.method.annotation.Argument;

@EntityMapping
List<Product> product(@Argument List<String> idList) {
    return productService.findAllInOrder(idList);
}
```

The parameter name `idList` conventionally tells Spring this is a list of values for the `id` key. You can declare the argument name explicitly with `@Argument`.

Crucially, results must maintain the same order as the corresponding representation list. If the service returns results in an arbitrary database order, re-align them by ID before returning.

## 18. Combining `@EntityMapping` with DataLoader

When entity resolution needs to batch multiple keys or load data asynchronously, you can use a DataLoader registered via `BatchLoaderRegistry`:

This is an alternative to calling the service directly inside `@EntityMapping`; choose one entity loader registration approach suited to the subgraph.

```java
import java.util.Set;

import org.springframework.context.annotation.Configuration;
import org.springframework.graphql.execution.BatchLoaderRegistry;
import reactor.core.publisher.Mono;

@Configuration
class ProductBatchLoaderConfiguration {

    ProductBatchLoaderConfiguration(
            BatchLoaderRegistry registry,
            ProductService products) {

        registry.forTypePair(String.class, Product.class)
            .registerMappedBatchLoader((ids, environment) ->
                products.findAllByIds(ids)
            );
    }
}
```

The service is assumed to return a map keyed by ID:

```java
import java.util.Map;
import java.util.Set;

import reactor.core.publisher.Mono;

public interface ProductService {
    Mono<Map<String, Product>> findAllByIds(Set<String> ids);
}
```

Entity mapping using DataLoader:

```java
import java.util.concurrent.CompletableFuture;

import org.dataloader.DataLoader;
import org.springframework.graphql.data.federation.EntityMapping;
import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.stereotype.Controller;

@Controller
class ProductEntityDataLoaderController {

    @EntityMapping
    CompletableFuture<Product> product(
            @Argument String id,
            DataLoader<String, Product> productLoader) {

        return productLoader.load(id);
    }
}
```

DataLoader batches keys within the same GraphQL execution and caches per request. This can reduce database calls when the router sends multiple representations. The DataLoader cache is not a cache shared across requests.

## 19. What are `_service` and `_entities`?

A Federation subgraph requires two special fields integrated into its schema:

| Field | Purpose |
|---|---|
| `Query._service { sdl }` | Returns the subgraph's SDL, including Federation directives, for the router/composition tool to read the schema. |
| `Query._entities(representations)` | Allows the router to send entity representations so the subgraph returns the corresponding entities. |

`FederationSchemaFactory` together with federation-jvm configures the required Federation components, including the `_entities` resolver and the `_Entity` type resolver.

`_service` primarily serves schema discovery/composition. It is not a business field meant for end clients and does not appear in the composed supergraph API. Access to subgraph endpoints should be controlled, and internal endpoints should not be exposed to the public Internet without good reason.

## 20. How does the gateway pass entity representations?

Suppose a client sends the query:

```graphql
query {
    products {
        id
        name
        reviews {
            rating
            comment
        }
    }
}
```

The gateway knows `products` and `name` belong to the Products subgraph, while `reviews` belongs to the Reviews subgraph. High-level query plan:

1. Call the Products subgraph to fetch `id`, `name`, and required keys.
2. From each Product, build a representation containing `__typename` and `id`.
3. Call the Reviews subgraph using `_entities(representations: ...)`.
4. The Reviews subgraph uses `@EntityMapping` to identify the Product and `@SchemaMapping` to fetch reviews.
5. The gateway merges reviews onto the right Product and returns a single response to the client.

The internal request to the Reviews subgraph looks like:

```graphql
query ResolveProductReviews($representations: [_Any!]!) {
    _entities(representations: $representations) {
        ... on Product {
            reviews {
                rating
                comment
            }
        }
    }
}
```

A corresponding representation:

```json
{
  "__typename": "Product",
  "id": "product-101"
}
```

`_Entity` is a union, so the router uses an inline fragment `... on Product` to request fields for the specific entity type.

## 21. Running subgraphs and gateway locally

A simple local setup can run two Spring Boot services:

| Service | Example endpoint | Port |
|---|---|---|
| Products subgraph | `http://localhost:8080/graphql` | 8080 |
| Reviews subgraph | `http://localhost:8081/graphql` | 8081 |
| Apollo Router | `http://localhost:4000/graphql` | 4000 |

Each subgraph must configure `FederationSchemaFactory`, have valid Federation SDL, and provide the required controllers. Start both Spring Boot applications before starting the router.

## 22. Declaring supergraph composition with Rover

Create a `supergraph.yaml` file:

```yaml
federation_version: =2.11.0
subgraphs:
  products:
    routing_url: http://localhost:8080/graphql
    schema:
      file: ./products-schema.graphql
  reviews:
    routing_url: http://localhost:8081/graphql
    schema:
      file: ./reviews-schema.graphql
```

This file points to each subgraph's schema file and routing URL. Choose a Federation version compatible with the router version and the directives used by the subgraphs. `2.11.0` here is an illustrative version; check the compatibility matrix when upgrading versions.

After installing Rover CLI, compose the supergraph:

```bash
rover supergraph compose \
  --config ./supergraph.yaml \
  --output ./supergraph.graphql
```

The command generates `supergraph.graphql` from the subgraph schemas. If composition fails, inspect the errors to fix schema conflicts before starting the gateway.

## 23. Running Apollo Router

Create a minimal `router.yaml` file:

```yaml
supergraph:
  listen: 127.0.0.1:4000
  path: /graphql
```

Start the router with the composed supergraph:

```bash
./router --config ./router.yaml --supergraph ./supergraph.graphql
```

The router reads subgraph routing URLs from the supergraph schema. You can override URLs in router configuration when deployment environments change service addresses.

## 24. Sending queries through the gateway

Clients only need to send queries to the router's endpoint:

```bash
curl http://localhost:4000/graphql \
  -H 'Content-Type: application/json' \
  -d '{"query":"query { products { id name reviews { rating comment } } }"}'
```

Clients do not need to know which ports Products and Reviews run on. The gateway coordinates the subgraphs and returns a single unified GraphQL response.

## 25. Testing subgraphs directly

Before testing the entire supergraph, verify that each subgraph works independently.

Check the Federation SDL:

```graphql
query FederationServiceInfo {
    _service {
        sdl
    }
}
```

The response must contain the SDL along with directives such as `@key`. If `_service` does not exist or the SDL lacks Federation metadata, the schema factory/dependency is misconfigured.

Test entity resolution directly:

```graphql
query ResolveEntity {
    _entities(representations: [
        { __typename: "Product", id: "product-101" }
    ]) {
        ... on Product {
            id
            reviews {
                rating
            }
        }
    }
}
```

If `_entities` does not return the expected Product or the `reviews` field errors, inspect `@EntityMapping`, key names, type names, and field resolvers before investigating the gateway.

## 26. Security between gateway and subgraphs

The gateway is the client entry point, yet subgraphs are still services holding data and need independent protection.

Principles to apply:

- Authenticate clients at the gateway and pass identity/claims over a trusted service-to-service channel.
- Subgraphs verify tokens or credentials according to system policy, rather than trusting arbitrary client-sent headers.
- Authorize at the subgraph level for the data owned by the service.
- Check tenant and ownership inside `@EntityMapping` or application services when loading entities.
- Do not expose subgraphs directly to public networks if only the gateway is allowed to call them.
- Use appropriate TLS, service identity, network policies, and secret rotation.
- Enforce query depth/complexity limits, request size limits, timeouts, and rate limits at both the gateway and services.

The gateway cannot replace authorization inside each subgraph. Requests might reach a subgraph via the router, internal jobs, or another client service; the subgraph must protect its own data.

## 27. Error handling and availability

Federated queries depend on multiple subgraphs. If a subgraph times out or returns an error, the router can return partial data alongside GraphQL errors depending on the execution plan and the router's error-handling behavior.

Subgraph design should pay attention to:

- Timeouts for database and outbound calls.
- Concurrency and connection pool limits.
- Retries only for safe operations and transient errors.
- Never blindly retrying non-idempotent mutations.
- Dedicated health checks and readiness probes for each service.
- Logs/traces with correlation IDs to link requests from the router to subgraphs.
- Error messages that do not leak stack traces or internal details.

The gateway also needs an overall timeout and per-subgraph timeouts. One slow subgraph can prolong the entire GraphQL request even if other subgraphs have already finished.

## 28. Schema ownership and change workflow

Each subgraph should have a clear team/domain owner. Before modifying a schema:

1. Identify which subgraph owns the field.
2. Check whether the field is used by clients or other subgraphs.
3. Add fields in a backward-compatible manner whenever possible.
4. Mark fields deprecated before removing fields currently in use.
5. Run schema composition in CI.
6. Inspect query plans and run integration tests through the router.
7. Deploy compatible subgraphs before the gateway begins sending the new field to them.

Successful composition does not prove runtime resolvers are correct. Test entity lookups, authorization, response mapping, and errors at runtime.

## 29. Testing Federation in Spring GraphQL

Testing can be split into multiple layers:

| Test type | Goal |
|---|---|
| Unit test `@EntityMapping` | Verify how representations are converted into entities/references. |
| GraphQL subgraph test | Verify `_service`, `_entities`, resolvers, and error mapping. |
| Schema composition test | Verify that SDLs can compose into a supergraph. |
| Router integration test | Verify queries spanning multiple subgraphs and accurate response merging. |
| Contract/security test | Verify keys, auth context, tenant isolation, and schema compatibility. |

With `GraphQlTester`, you can send `_entities` queries directly to a subgraph configured with the federation factory. When testing the gateway, start the router alongside test subgraphs or use a dedicated integration environment.

## 30. Testing entity mapping with representations

A subgraph test can send representations just as the gateway does:

Illustrative test dependencies with Gradle:

```groovy
dependencies {
    testImplementation 'org.springframework.graphql:spring-graphql-test'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

```java
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.graphql.GraphQlTest;
import org.springframework.context.annotation.Import;
import org.springframework.graphql.test.tester.GraphQlTester;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

import static org.mockito.BDDMockito.given;

@GraphQlTest({ProductEntityController.class, ProductReviewController.class})
@Import(FederationConfiguration.class)
class ProductEntityMappingTests {

    @Autowired
    GraphQlTester graphQlTester;

    @MockitoBean
    ReviewQueryService reviewQueryService;

    @Test
    void resolvesReviewsForFederatedProduct() {
        given(reviewQueryService.findByProductId("product-101"))
            .willReturn(List.of(new Review("review-1", 5, "Great")));

        graphQlTester.document("""
                query {
                    _entities(representations: [
                        { __typename: "Product", id: "product-101" }
                    ]) {
                        ... on Product {
                            reviews {
                                id
                                rating
                            }
                        }
                    }
                }
                """)
            .execute()
            .path("_entities[0].reviews[0].id")
            .entity(String.class)
            .isEqualTo("review-1");
    }
}
```

This example assumes the Federation schema, `FederationSchemaFactory`, `ProductEntityController`, `ProductReviewController`, and `ReviewQueryService` are configured. In a test slice, import the necessary federation configuration or use an integration test if auto-configuration does not create the schema factory automatically.

The `@GraphQlTest` import here is for Spring Boot 3.x. With Spring Boot 4.x, use package `org.springframework.boot.graphql.test.autoconfigure.GraphQlTest`. `@MockitoBean` requires Spring Framework 6.2 or later; older Spring Boot versions can use `@MockBean`.

## 31. Testing composition and gateway

CI can execute these steps:

```bash
# Compose schemas from all subgraphs
rover supergraph compose --config ./supergraph.yaml --output ./supergraph.graphql

# Start the router with the composed artifact in the integration environment
./router --config ./router.yaml --supergraph ./supergraph.graphql
```

Then run GraphQL integration queries through the gateway endpoint and verify data from multiple subgraphs. Do not test each subgraph only in isolation; include at least one test verifying real entity handoff and response merging.

With GraphOS, you can publish each subgraph schema and let the build pipeline handle composition, schema checks, and supergraph updates according to your organization's schema management process.

## 32. Common mistakes

**Assuming Spring GraphQL provides a gateway itself.** Spring for GraphQL provides integration so a service runs as a subgraph. The gateway/router must be deployed separately, such as Apollo Router.

**Forgetting to configure `FederationSchemaFactory`.** The schema has `@key` but lacks `_entities` or entity type resolvers. Register the factory via `GraphQlSourceBuilderCustomizer`.

**Missing the Federation JVM dependency.** `FederationSchemaFactory` requires a compatible `federation-graphql-java-support` library.

**Entity representation missing `__typename` or key fields.** The gateway must know the type and key for the subgraph to load the entity. Check `@key` and `@EntityMapping` methods.

**Entity mapping name does not match the GraphQL type.** Method names default to the type name with the first letter capitalized. Use `@EntityMapping(name = "...")` when explicit specification is needed.

**Batch entity resolver returns results out of order.** When accepting a list of representations, results must match the exact input order.

**Each subgraph defines the same field independently.** Composition can fail if fields have overlapping ownership without proper shareable declarations.

**Using an unstable key.** Entity keys should be unique, immutable, and retrievable by participating subgraphs.

**Assuming successful composition means runtime is correct.** Composition only checks the schema; test `_entities`, query plans, and actual resolvers.

**Letting subgraphs trust any client-sent header.** Only accept identity/claims from trusted sources and still enforce permissions in the subgraph.

**Placing multi-domain business logic in the gateway.** The gateway should orchestrate GraphQL; business rules belong in the domain-owning subgraphs.

## Conclusion

In GraphQL Federation, a subgraph is a service owning part of the schema and data; the gateway/router composes schemas into a supergraph, builds query plans, and merges results for clients. Spring for GraphQL supports building subgraphs through `federation-jvm`, `FederationSchemaFactory`, and `@EntityMapping`. The `@key` entity key lets the router identify entities, `_service` publishes the SDL, and `_entities` passes representations to subgraphs to load entities and resolve service-owned fields. The gateway should be deployed separately, composition should be verified in CI, and each subgraph remains responsible for authorization, tenant isolation, error handling, and availability.

## References

- [Spring for GraphQL — Federation](https://docs.spring.io/spring-graphql/reference/federation.html)
- [Spring for GraphQL API — `FederationSchemaFactory`](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/data/federation/FederationSchemaFactory.html)
- [Spring Boot — Testing Spring GraphQL Applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html)
- [Apollo Federation — Introduction](https://www.apollographql.com/docs/graphos/schema-design/federated-schemas/federation)
- [Apollo Federation — Subgraph Specification](https://www.apollographql.com/docs/graphos/schema-design/federated-schemas/reference/subgraph-spec)
- [Apollo Federation — Schema Composition](https://www.apollographql.com/docs/graphos/schema-design/federated-schemas/composition)
- [Apollo Federation — Compatible Subgraph Implementations](https://www.apollographql.com/docs/graphos/schema-design/federated-schemas/reference/compatible-subgraphs)
- [Apollo Rover — Supergraph Commands](https://www.apollographql.com/docs/rover/commands/supergraphs)
- [Apollo Router — Configuration](https://www.apollographql.com/docs/graphos/routing/configuration/yaml)
- [Apollo Federation JVM — Spring GraphQL Example](https://github.com/apollographql/federation-jvm-spring-example)

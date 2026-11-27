# Federated type

## Objectives

After this lesson, you will be able to:

- Explain federated types and entities in Apollo Federation.
- Distinguish entities from ordinary value types.
- Use the @key directive to define an entity's identity.
- Understand the role of @extends and @external when a subgraph adds fields to an entity.
- Describe entity representations and the Query._entities call flow from the router.
- Configure Spring for GraphQL with FederationSchemaFactory.
- Write @EntityMapping to restore entities from keys.
- Use @SchemaMapping, @BatchMapping, and DataLoader for an entity's fields.
- Distinguish Federation 1 and Federation 2 syntax to the extent needed when designing schemas.
- Test entity resolution and handle errors when an entity does not exist.

## What is a federated type?

In a monolithic GraphQL application, one schema is typically served by a single server. As a system grows, multiple teams may need to own different parts of the data. For example:

- The Catalog team manages Product, names, and prices.
- The Reviews team manages Product ratings and comments.
- The Inventory team manages Product stock levels.

Apollo Federation allows independent GraphQL services, called subgraphs, to contribute fields into a single unified graph. An object type can appear across multiple subgraphs; each subgraph owns and resolves the fields within its scope.

A federated type is typically called an entity. An entity is an object type with one or more stable keys so the router can recognize the same object across subgraphs. For example, Product can have its name and price defined by the Catalog subgraph, while the Reviews subgraph adds reviews.

Subgraphs do not need to share a database or Java models. They only need to agree on the schema contract and how entities are identified. The router uses keys to move from one subgraph to another, then merges the fields into the client response.

Spring for GraphQL provides integration with the federation-jvm library to build a subgraph's schema and handle requests to resolve federated entities. The Spring application acts as a subgraph; composition and orchestration of multiple subgraphs are handled by a federation gateway/router. [Spring for GraphQL – Federation](https://docs.spring.io/spring-graphql/reference/federation.html)

## How is an entity different from a value type?

Not every object type used across multiple subgraphs needs to become an entity.

| Characteristic | Entity | Value type |
| --- | --- | --- |
| Identity | Has a key identifying an instance | Does not need independent identity |
| Typical directive | @key | Can use @shareable in Federation 2 when multiple subgraphs resolve the field |
| How the router links it | Uses representations and entity resolution | Merged according to schema composition rules |
| Examples | Product, User, Order | Money, Address, Dimensions |

A Product can be looked up independently by ID, making it suitable as an entity. Money is usually just a value containing amount and currency; it does not need a key for the router to go back and fetch the Money object itself from another subgraph.

An entity in Federation is a distributed schema concept. It does not have to correspond to a JPA entity or a database table. A subgraph can return a DTO, a projection, or an object reference containing only the keys needed to resolve subsequent fields.

## Identifying an entity with @key

The @key directive marks an object type as an entity and declares the field set used to identify that entity:

~~~graphql
type Product @key(fields: "id") {
  id: ID!
  name: String!
  price: Int
}
~~~

In this example, Product is identified by id. The router can use id to ask another subgraph to resolve additional fields of the same Product.

A key can consist of multiple fields:

~~~graphql
type Product @key(fields: "tenantId sku") {
  tenantId: ID!
  sku: String!
  name: String!
}
~~~

This is a compound key. A Product is only identified when both tenantId and sku are present. Compound keys are often useful when IDs are only unique within a tenant or a namespace.

A key field set can also include nested selections:

~~~graphql
type Product @key(fields: "id organization { id }") {
  id: ID!
  organization: Organization!
  name: String!
}
~~~

An entity can have multiple keys if the subgraph implementation supports repeatable @key:

~~~graphql
type Product
  @key(fields: "id")
  @key(fields: "sku") {
  id: ID!
  sku: String!
  name: String!
}
~~~

The router can use whichever key fits its query plan and available data. When choosing keys, keep in mind:

- Fields must uniquely identify a single instance within the graph.
- Prefer stable keys that do not change over time.
- Key fields should generally be non-null so the router can always identify the entity.
- Keys must be obtainable by the subgraph that needs to resolve the entity.
- A key field set must not contain fields with arguments or fields returning a union/interface.
- If using multiple keys, check whether your Federation version and subgraph library support repeatable @key.

Do not pick a display name, mutable email, or non-unique value as a key when a more stable identifier exists.

## Entities shared across subgraphs

Suppose a bookstore system has two subgraphs.

The **Catalog subgraph** owns Product, id, name, and price:

~~~graphql
type Query {
  product(id: ID!): Product
}

type Product @key(fields: "id") {
  id: ID!
  name: String!
  price: Int!
}
~~~

The **Reviews subgraph** adds the reviews field to the same Product:

~~~graphql
type Product @key(fields: "id") @extends {
  id: ID! @external
  reviews: [Review!]!
}

type Review {
  id: ID!
  text: String!
  rating: Int!
}
~~~

This is the extension declaration style used by the Spring for GraphQL documentation in its federation-jvm examples. @key tells the router the two Product definitions share the same identity; @extends indicates this subgraph is extending an entity defined elsewhere; @external declares that id is referenced from another subgraph and is not resolved by the Reviews subgraph.

The Reviews subgraph only needs to provide reviews. It does not need to own name or price and does not need to reload the entire Product from Catalog. Upon receiving a representation with id, it can create a small Product reference and use id to load reviews from its own data store.

After composition, the router sees a single Product with name, price, and reviews fields. Clients do not need to know which subgraph holds which field.

### Syntax differences between Federation 1 and Federation 2

The @extends example above reflects the declaration style used in the Spring for GraphQL and federation-jvm integration documentation. When working with Federation 2, the schema must declare @link to bind the Federation version and import the directives in use. Federation 2 does not require @extends for entity extensions.

Federation 2 example:

~~~graphql
extend schema
  @link(
    url: "https://specs.apollo.dev/federation/v2.3"
    import: ["@key", "@external"]
  )

type Product @key(fields: "id") {
  id: ID! @external
  reviews: [Review!]!
}

type Review {
  id: ID!
  text: String!
  rating: Int!
}
~~~

In Federation 2, each subgraph can define the entity with @key and composition merges the fields. Do not add @extends out of habit from Federation 1 if the schema follows Federation 2.

Check the Federation version supported by your router composition and the federation-jvm version compatible with your Spring GraphQL version. New Federation 2 directives are not automatically supported just because the application has FederationSchemaFactory. Current Spring documentation illustrates integration with federation-jvm; support for individual directives depends on the library version and composition tooling. [Apollo Federation Directives](https://www.apollographql.com/docs/graphos/schema-design/federated-schemas/reference/directives)

## Entity representation

When the router needs to call a subgraph to fetch fields of an entity, it sends a representation. A representation is an object containing:

- __typename: the GraphQL object type name.
- Fields belonging to a valid @key of the entity.

Example representation of Product:

~~~json
{
  "__typename": "Product",
  "id": "product-101"
}
~~~

If Product uses a compound key:

~~~json
{
  "__typename": "Product",
  "tenantId": "tenant-7",
  "sku": "BOOK-101"
}
~~~

A representation is not the entire Product object. It contains only enough information for the subgraph to identify the instance to resolve. The subgraph can use the key to load data from a database, call an internal service, or create a reference object and let nested resolvers load fields.

A key is an identifier, not proof of authorization. The subgraph still needs to verify that the user has permission to access the corresponding entity and fields. Do not trust tenant or owner values in a representation unless they are bound to an authenticated identity.

## Federation components added to the schema

A Federation-compatible subgraph needs special components so the router can discover the schema and request entities:

| Component | Role |
| --- | --- |
| _Any | Scalar representing an entity representation |
| _Entity | Union consisting of the entity object types in the subgraph |
| Query._entities | Accepts a list of representations and returns the corresponding entities |
| Query._service | Returns schema information of the subgraph |
| _Service.sdl | SDL string used for schema discovery/composition |

In a subgraph, _Entity is generated from object types carrying @key. Query._entities takes a list of representations. The router uses this field to start resolving the fields owned by the current subgraph.

Query._service returns the subgraph's SDL, including the Federation metadata needed for composition. This field serves integration between the router and subgraph; it is not a business field that regular clients need to call.
Internal Federation fields such as _service and _entities belong to the subgraph's schema; they do not appear as business fields in the composed API schema exposed to clients.

When using Spring's FederationSchemaFactory, the definitions and data fetchers needed for Federation are generated while building the GraphQL schema. Do not manually declare a fixed _Entity union if the factory needs to generate the union from actual entities in the schema.

## Configuring FederationSchemaFactory in Spring Boot

Spring for GraphQL integrates with federation-jvm. You need the Spring Boot GraphQL starter and a federation-graphql-java-support dependency compatible with your application's Spring GraphQL/GraphQL Java version.

Gradle Groovy example; replace the placeholder with a federation-jvm version verified to be compatible with the GraphQL Java version managed by Spring Boot:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-graphql'
    implementation 'com.apollographql.federation:federation-graphql-java-support:<compatible-version>'
}
~~~

Declare the factory and attach it to the GraphQlSource builder:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.boot.graphql.autoconfigure.GraphQlSourceBuilderCustomizer;
import org.springframework.graphql.data.federation.FederationSchemaFactory;

@Configuration
public class FederationConfig {

    @Bean
    FederationSchemaFactory federationSchemaFactory() {
        return new FederationSchemaFactory();
    }

    @Bean
    GraphQlSourceBuilderCustomizer federationSchemaCustomizer(
            FederationSchemaFactory factory) {
        return builder ->
                builder.schemaFactory(factory::createGraphQLSchema);
    }
}
~~~

The import of GraphQlSourceBuilderCustomizer depends on the Spring Boot release line. Spring Boot 4 uses package org.springframework.boot.graphql.autoconfigure; Spring Boot 3 uses package org.springframework.boot.autoconfigure.graphql. The rest of the configuration follows the same idea. Do not force a newer federation-jvm version into the project if it pulls in a GraphQL Java version different from what Spring for GraphQL supports.

The factory detects controller methods annotated with @EntityMapping, creates a Federation-compatible schema, and sets up entity data fetchers along with the type resolver for _Entity. If the subgraph has a resolvable entity without a matching mapping, configuration can fail at startup. This is an error best caught early rather than waiting for the router to call _entities in production.

The Spring application still needs schema SDL files on the classpath, for example src/main/resources/graphql. The factory adds Federation support to the schema built from those resources; it does not auto-generate the Product domain type or business resolvers for reviews.

## Resolving entities with @EntityMapping

Spring for GraphQL uses @EntityMapping to map loading an entity from a representation sent by the router via Query._entities.

Example Reviews subgraph:

~~~java
public record Product(String id) {
}

public record Review(
        String id,
        String text,
        int rating) {
}
~~~

Controller:

~~~java
import java.util.List;

import org.springframework.graphql.data.federation.EntityMapping;
import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.SchemaMapping;
import org.springframework.stereotype.Controller;

@Controller
public class ProductReviewsController {

    private final ReviewService reviewService;

    public ProductReviewsController(ReviewService reviewService) {
        this.reviewService = reviewService;
    }

    @EntityMapping
    public Product product(@Argument("id") String id) {
        return new Product(id);
    }

    @SchemaMapping(typeName = "Product", field = "reviews")
    public List<Review> reviews(Product product) {
        return reviewService.findByProductId(product.id());
    }
}
~~~

When the router sends a Product representation containing id, the product method receives id via @Argument and returns a Product reference. GraphQL then continues resolving the reviews field with @SchemaMapping. The resolver uses id from the Product reference to load Reviews in the Reviews subgraph.

It is not necessary to load the entire Product inside @EntityMapping. If the subgraph only needs the key to resolve its own fields, a minimal reference object is enough. This avoids calling back to the entity-owning service just to fetch fields the current subgraph does not use.

### Arguments and representation map

@Argument reads a field from the representation and converts it to a Java type:

~~~java
@EntityMapping
public Product product(@Argument("id") String id) {
    return new Product(id);
}
~~~

If the key consists of multiple fields, the method can accept multiple arguments:

~~~java
@EntityMapping
public Product product(
        @Argument("tenantId") String tenantId,
        @Argument("sku") String sku) {
    return productService.reference(tenantId, sku);
}
~~~

When you need to handle the full representation, you can accept Map<String, Object>:

~~~java
import java.util.Map;

@EntityMapping
public Product product(Map<String, Object> representation) {
    String id = (String) representation.get("id");
    return productService.reference(id);
}
~~~

Spring for GraphQL also supports List<Map<String, Object>> when a method processes multiple representations of the same type. In addition, the method can accept GraphQLContext, @ContextValue, Principal, @AuthenticationPrincipal, DataFetchingEnvironment, or DataLoader depending on the use case.

### Batch entity resolution

If the router sends multiple Product representations in the same _entities request, Spring supports an @EntityMapping method that accepts a list of keys and returns a list of entities in the exact order:

~~~java
@EntityMapping
public List<Product> product(@Argument("id") List<String> idList) {
    return productService.findReferencesInOrder(idList);
}
~~~

The naming convention idList helps Spring infer a list of values for the id argument. You can specify the name explicitly with @Argument("id") if you want a different parameter name.

Results must preserve the exact order corresponding to the input representation list. If the repository returns results in a different order, reorder them by key before returning. Otherwise, the router may attach fields of one Product to another Product's representation.

When you need to load entities asynchronously or batch multiple loads by key, you can use DataLoader:

~~~java
import java.util.concurrent.CompletableFuture;

import org.dataloader.DataLoader;

@EntityMapping
public CompletableFuture<Product> product(
        @Argument("id") String id,
        DataLoader<String, Product> productLoader) {
    return productLoader.load(id);
}
~~~

Besides synchronous entity objects, @EntityMapping also supports asynchronous return types such as Mono, CompletableFuture, and Callable. BatchLoaderRegistry can register a loader for Product and batch keys within the same request. This approach is helpful when the resolver is called multiple times or entity resolution needs to share batching mechanisms with other fields.

## Entity mapping and remaining fields

@EntityMapping only solves the step of finding an entity from a representation. Other fields of the entity still use standard data fetching mechanisms:

- @SchemaMapping for nested fields requiring custom logic.
- @BatchMapping to load fields for multiple parent objects.
- DataLoader to batch queries by key.
- Default property data fetcher for properties already present on the object.

For example, the Reviews subgraph can return a Product reference containing only id. The reviews field is handled by @SchemaMapping; an internal productId field does not necessarily appear in the schema.

An entity can be extended by multiple subgraphs. Each subgraph needs an entity mapping if the router can route to that subgraph to resolve the entity. A subgraph that owns no fields of an entity may simply reference the entity in a manner compatible with the directives and capabilities of the Federation version; check the resolvable option of @key and support in your library.

## Handling non-existent entities and mapping errors

Entity mapping can encounter situations such as:

- Representation missing __typename.
- Representation missing required key fields.
- Invalid key or entity not found.
- Service/repository encountering an error while loading the entity.
- User not permitted to access the entity.

Spring for GraphQL provides exception handling for @EntityMapping. You can use @GraphQlExceptionHandler in a controller or @ControllerAdvice to turn exceptions into GraphQLError. These errors are included in the response of the _entities query.

Example:

~~~java
import java.util.Map;

import graphql.GraphQLError;
import graphql.GraphqlErrorBuilder;
import org.springframework.graphql.data.method.annotation.GraphQlExceptionHandler;

@GraphQlExceptionHandler
public GraphQLError handleProductNotFound(ProductNotFoundException exception) {
    return GraphqlErrorBuilder.newError()
            .message("Requested Product not found")
            .extensions(Map.of("code", "PRODUCT_NOT_FOUND"))
            .build();
}
~~~

In production, decide clearly whether a missing entity should return null, return an error, or conceal the entity's existence. For sensitive data, do not let error messages expose keys or internal information. Also enforce authorization at the subgraph; gateway authentication does not replace permission checks where data is actually read.

## Router call flow for entities across subgraphs

A client sends a normal query to the router:

~~~graphql
query ProductDetails($id: ID!) {
  product(id: $id) {
    id
    name
    price
    reviews {
      rating
      text
    }
  }
}
~~~

The router can execute these steps:

~~~mermaid
sequenceDiagram
    participant C as GraphQL Client
    participant R as Federation Router
    participant P as Catalog Subgraph
    participant V as Reviews Subgraph
    C->>R: product(id)
    R->>P: Query Product fields
    P-->>R: id, name, price
    R->>V: Query._entities([{__typename, id}])
    V->>V: @EntityMapping Product reference
    V->>V: @SchemaMapping Product.reviews
    V-->>R: reviews
    R-->>C: Merged Product response
~~~

The router uses the id key from Catalog's result to build a representation for Reviews. The Reviews subgraph does not receive the client's full query again; it receives an entity resolution request and the selection set the router needs from that subgraph.

A single query can traverse multiple subgraphs, and the same entity may be referenced multiple times. Therefore, entity resolution should support batching, avoid N+1 queries, and bound the number of downstream calls.

## Testing _entities directly in development

Normally clients call the supergraph endpoint rather than calling _entities directly. However, when developing or debugging a subgraph, you can send an operation to the subgraph to verify entity mapping:

~~~graphql
query ResolveProduct {
  _entities(
    representations: [
      {
        __typename: "Product"
        id: "product-101"
      }
    ]
  ) {
    ... on Product {
      id
      reviews {
        id
        rating
        text
      }
    }
  }
}
~~~

This operation verifies:

1. The Federation schema generated _entities and _Entity.
2. The representation has a valid __typename and key.
3. @EntityMapping returns the proper Product reference.
4. @SchemaMapping resolves reviews.
5. The response contains accurate data for the requested entity.

If the subgraph has multiple entity types, the _Entity union will contain the corresponding object types. Queries must use inline fragments to select fields of each concrete type.

## Testing entity mapping with GraphQlTester

You can use GraphQlTester with a GraphQL execution configured with FederationSchemaFactory:

The following test snippet assumes GraphQlTester is configured to execute the Reviews subgraph schema:

~~~java
@Test
void resolvesProductRepresentation() {
    graphQlTester.document("""
            query {
                _entities(representations: [
                    { __typename: "Product", id: "product-101" }
                ]) {
                    ... on Product {
                        id
                        reviews {
                            rating
                            text
                        }
                    }
                }
            }
            """)
            .execute()
            .path("_entities[0].id")
            .entity(String.class)
            .isEqualTo("product-101");
}
~~~

Tests should cover:

- Valid representation with a single key.
- Compound keys and argument type conversion.
- Multiple representations in the same request with results in the exact order.
- Non-existent entity.
- Entity mapping returning errors and GraphQL error extensions.
- Nested @SchemaMapping or @BatchMapping being invoked properly.
- Authorization by principal and tenant.
- DataLoader batching keys instead of calling the repository individually.

Testing _entities verifies the subgraph. It does not prove router composition succeeds or that the query plan across subgraphs is right. A separate integration test with the federation router or composition tool is needed when verifying the full supergraph.

## Common pitfalls

| Symptom | Possible cause | Solution |
| --- | --- | --- |
| Router cannot merge two Product definitions | Keys do not match or are unstable across subgraphs | Choose a shared key and verify composition |
| Subgraph lacks _entities | FederationSchemaFactory not configured | Attach the factory to the GraphQlSource builder |
| Entity type missing from _Entity | Missing @key or schema not transformed for Federation | Check SDL and schema factory |
| @EntityMapping not invoked | Representation missing __typename/key or wrong method mapping | Check type name, @Argument, and entity mapping registration |
| Startup reports unmapped entity type | Entity is resolvable but has no @EntityMapping | Write a resolver for the entity or configure resolvable properly if supported |
| Entity mapping returns wrong object | Key bound incorrectly or method misreads representation | Check arguments and full representation map |
| Extended field returns null | Missing @SchemaMapping or source object lacks needed key | Add resolver and keep the key on the reference object |
| Multiple entities get mismatched data | Batch resolver returns List out of order | Return results in representation order or use a properly keyed Map |
| One _entities request triggers multiple queries | Entity resolver loads each key individually | Use batch entity mapping or DataLoader |
| Federation 2 composition directive error | Missing @link or incorrect directive import | Declare Federation 2 link and check version support |
| Subgraph returns error leaking data | Error message contains keys or internal details | Use stable error codes and safe messages |
| _entities works but supergraph query fails | Router composition or query plan not verified | Test through the integrated gateway/router |

## Hands-on synthesis exercise

Build two subgraphs, Catalog and Reviews:

1. In Catalog, declare Product with @key(fields: "id"), id, name, and price.
2. In Reviews, declare an extended Product with the same key and the reviews field.
3. Choose the Federation syntax compatible with your router and federation-jvm version.
4. Add the compatible federation-graphql-java-support dependency.
5. Configure FederationSchemaFactory and GraphQlSourceBuilderCustomizer.
6. Create a Product reference containing only id.
7. Write @EntityMapping to extract id from the representation.
8. Write @SchemaMapping for Product.reviews.
9. Send an _entities query directly to the Reviews subgraph to verify entity resolution.
10. Send a ProductDetails query to the router and verify fields from both subgraphs are merged.
11. Try a compound key or multiple representations and verify result ordering.
12. Add DataLoader or batch entity mapping to reduce queries when the router sends multiple entities.
13. Test non-existent entities, resolver errors, and tenant-based authorization.

Once completed, explain why @key only identifies an entity without loading data, the role of @EntityMapping in _entities, and the difference between testing a single subgraph versus testing the entire supergraph.

## Takeaways

A federated type is an object type to which multiple subgraphs can contribute fields. Entities are identified by @key; representations carry __typename along with key fields so the router can ask another subgraph to resolve entities via Query._entities. @extends and @external appear in Federation 1 declarations; Federation 2 uses @link and does not require @extends. In Spring for GraphQL, FederationSchemaFactory builds the Federation schema and registers the entity resolution mechanism; @EntityMapping retrieves entities from representations, while @SchemaMapping/@BatchMapping handle remaining fields. Keys must be stable and unique, batch results must align with representations, and authorization must still be enforced in the subgraph. Testing _entities verifies a subgraph; router composition tests verify the full supergraph.

## References

- [Spring for GraphQL – Federation](https://docs.spring.io/spring-graphql/reference/federation.html)
- [Spring for GraphQL – FederationSchemaFactory API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/data/federation/FederationSchemaFactory.html)
- [Apollo Federation – Introduction to Entities](https://www.apollographql.com/docs/graphos/schema-design/federated-schemas/entities/intro)
- [Apollo Federation – Subgraph Specification](https://www.apollographql.com/docs/graphos/schema-design/federated-schemas/reference/subgraph-spec)
- [Apollo Federation – Directives](https://www.apollographql.com/docs/graphos/schema-design/federated-schemas/reference/directives)
- [Apollo Federation JVM – GraphQL Java Support](https://github.com/apollographql/federation-jvm/tree/main/graphql-java-support)

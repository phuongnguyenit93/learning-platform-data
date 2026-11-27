# Schema composition

When a GraphQL system is split into multiple services by domain, each service can own its own slice of the schema and data. For example, Catalog manages products, Inventory manages stock levels, and Shipping calculates delivery fees. Clients still want to query all of this information through a single unified GraphQL API.

**Schema composition** is the process of combining subgraph schemas into a supergraph schema. The supergraph contains types and fields contributed by multiple subgraphs along with metadata so the router knows which service resolves which field and in what order to call those services.

In Spring for GraphQL, each application typically implements one subgraph. Spring integrates with the federation-jvm library to generate schemas and handle entity requests. Composition itself is usually performed by Apollo GraphOS or the Rover CLI; Spring for GraphQL does not replace the router or composition engine.

This lesson covers the subgraph, supergraph, and API schema model; how types are merged; entity and field ownership; important Federation directives; Federation 1 and 2 differences; composing with Rover; integrating a Spring for GraphQL subgraph; checking changes in CI; and handling composition errors.

## 1. What is schema composition?

In standard GraphQL, one server typically provides one complete schema. In a federated architecture, the schema is divided into independent parts:

- Subgraph schema: a schema owned by a service or team. It defines the types and fields that service can resolve.
- Supergraph schema: the composition result of all subgraphs. Beyond types and fields, it holds federation metadata so the router can plan subgraph calls.
- API schema: the public schema visible to clients. It strips internal router-only details such as federation machinery and fields marked non-public.

~~~mermaid
flowchart TD
    A[Catalog subgraph SDL] --> D[Schema composition]
    B[Inventory subgraph SDL] --> D
    C[Shipping subgraph SDL] --> D
    D --> E[Supergraph schema]
    E --> F[GraphQL Router]
    F --> G[API schema exposed to clients]
    H[Client operation] --> F
    F --> A
    F --> B
    F --> C
~~~

Composition is not simply concatenating SDL files together. It must verify whether definitions can be merged safely, which fields are resolved by multiple subgraphs, which entities can be referenced, and which data must be fetched before calling dependent resolvers.

If two subgraphs define the same field with incompatible return types, or the supergraph contains a field that cannot be resolved across all valid query paths, composition fails.

## 2. Example domain with multiple subgraphs

Suppose an e-commerce system has three subgraphs:

| Subgraph | Responsibility | Fields contributed to Product |
|---|---|---|
| Catalog | Product information | id, name, price, weight |
| Inventory | Stock levels | inStock |
| Shipping | Delivery estimates | shippingEstimate |

A client wants to send one operation:

~~~graphql
query {
  product(id: "p-100") {
    id
    name
    price
    inStock
    shippingEstimate
  }
}
~~~

Catalog finds the product. Inventory supplies the inStock field for the same Product entity. Shipping calculates shippingEstimate based on weight provided by Catalog.

The router reads supergraph metadata to know:

1. Call Catalog to fetch Product and its base fields.
2. Pass Product's representation to Inventory to fetch inStock.
3. Obtain weight if not yet in the response and pass the representation to Shipping to calculate shippingEstimate.
4. Merge the results into a single GraphQL response.

The client does not need to know the fields came from three different services.

## 3. Entities and value types during composition

Composition must distinguish between two important type kinds.

### Entity

An entity is an object with a stable identifier that can be referenced across multiple subgraphs. The @key directive declares the set of fields used to identify an entity.

For example, Catalog owns Product:

~~~graphql
type Product @key(fields: "id") {
  id: ID!
  name: String!
  price: Int!
  weight: Int!
}
~~~

Inventory also defines Product with the same key, contributing only the stock field:

~~~graphql
type Product @key(fields: "id") {
  id: ID!
  inStock: Boolean!
}
~~~

The two subgraphs do not need to define all fields of Product identically. Because Product is an entity, each subgraph can contribute different fields as long as keys are declared compatibly and fields can be resolved properly under federation rules.

At runtime, the router can send an entity representation containing typename and key to another subgraph. Spring for GraphQL uses @EntityMapping to load the corresponding entity from the representation.

### Value type

A value type is an object without independent identity in federation. For example, Address might simply be a group of values embedded inside Customer:

~~~graphql
type Address {
  street: String!
  city: String!
  postalCode: String!
}
~~~

If multiple subgraphs define the same value type, composition must ensure every field in the type can be resolved along every valid query path. One subgraph cannot contribute a new field to a value type and leave another subgraph returning the same type without being able to resolve that field.

If a type corresponds to a data record with a stable ID and domains need to add fields independently, consider making it an entity.

## 4. Federation 2 and the @link directive

Federation 2 requires subgraphs to declare the federation specification using the @link directive. The import list specifies which directives are used in the SDL.

Example:

~~~graphql
extend schema
  @link(
    url: "https://specs.apollo.dev/federation/v2.3"
    import: ["@key", "@external", "@requires"]
  )
~~~

If a directive is not imported, it can still be used in its namespaced form, such as federation__shareable. Explicit imports generally make schemas easier to read.

Notable differences:

| Federation 1 | Federation 2 |
|---|---|
| Does not use @link to opt in | Each subgraph uses @link to select the Federation spec |
| Type extensions and @extends are widely used | GraphQL extend keyword is supported directly; @extends is not required |
| Value types are considered shareable under Federation 1 rules | Object fields default to being resolved by one subgraph; sharing requires declaring @shareable |
| Fewer tools for incremental field rollout | Provides @inaccessible and @override to support incremental changes |

Federation 2 does not require @extends when the SDL supports GraphQL's extend keyword. The @extends directive is primarily intended for code-first schema libraries that do not support the extend keyword.

Keep the federation spec version aligned between subgraphs and the composition engine version. Do not copy directives introduced only in Federation 2.7 or 2.9 into a subgraph using an older spec without verifying compatibility.

## 5. Directives that affect composition

Federation directives describe entity identity, field resolution ownership, and dependencies between subgraphs.

| Directive | Version | Meaning |
|---|---|---|
| @link | Federation 2 | Declares the Federation spec and imports directives |
| @key | Federation 1+ | Declares fields used to identify an entity |
| @external | Federation 1+ | Declares a field referenced here that the current subgraph does not own resolving |
| @requires | Federation 1+ | Declares fields from another subgraph that must be fetched before resolving the current field |
| @provides | Federation 1+ | Declares entity fields a subgraph can resolve along a specific query path |
| @shareable | Federation 2 | Allows multiple subgraphs to resolve the same field |
| @inaccessible | Federation 2 | Keeps definitions in the supergraph while hiding them from the client API schema |
| @override | Federation 2 | Transfers field resolution ownership from an old subgraph to a new one |
| @extends | Federation 1+ | Compatibility directive for libraries not supporting GraphQL type extensions |

### 5.1. @key: identifying an entity

An entity can have one or more keys. For example, Product can be identified by id or sku:

~~~graphql
type Product
  @key(fields: "id")
  @key(fields: "sku") {
  id: ID!
  sku: String!
  name: String!
}
~~~

Keys must uniquely identify a single entity instance. A key can contain multiple fields or nested fields:

~~~graphql
type Product @key(fields: "sku region { code }") {
  sku: String!
  region: Region!
}
~~~

Only declare a key when the subgraph can genuinely identify the entity by those fields. A key is not an arbitrary field for the router to pass data around; it is an identification contract between subgraphs.

### 5.2. @external and @requires

Shipping needs Product's weight owned by Catalog to calculate shippingEstimate. In Shipping's SDL:

~~~graphql
extend schema
  @link(
    url: "https://specs.apollo.dev/federation/v2.3"
    import: ["@key", "@external", "@requires"]
  )

type Product @key(fields: "id") {
  id: ID!
  weight: Int! @external
  shippingEstimate: Int!
    @requires(fields: "weight")
}
~~~

@external indicates Shipping does not own resolving weight. @requires tells the router to fetch weight from a subgraph capable of resolving it before invoking the shippingEstimate resolver.

The resolver in Shipping can receive the weight value placed into the representation by the router:

~~~java
@Controller
public class ShippingController {

    @SchemaMapping
    public Integer shippingEstimate(Product product) {
        return calculateShipping(product.weight());
    }

    private Integer calculateShipping(Integer weight) {
        return weight * 2;
    }
}
~~~

The Java snippet only illustrates business logic. Mapping representations and entities needs to be configured according to Spring for GraphQL federation integration as shown later.

Fields listed in @requires must be declared in the current subgraph and marked @external. If missing, composition reports an error because the router cannot determine the field's dependencies.

### 5.3. @provides: optimizing along a specific query path

Inventory does not usually own Product.name, but when querying the list of out-of-stock products, Inventory can obtain name from its local data source. @provides declares that capability on that exact field path:

In Catalog, the name field must be marked @shareable to indicate at least one other subgraph can also resolve this field:

~~~graphql
type Product @key(fields: "id") {
  id: ID!
  name: String! @shareable
}
~~~

~~~graphql
extend schema
  @link(
    url: "https://specs.apollo.dev/federation/v2.3"
    import: ["@key", "@external", "@provides"]
  )

type Product @key(fields: "id") {
  id: ID!
  name: String! @external
  inStock: Boolean!
}

type Query {
  outOfStockProducts: [Product!]!
    @provides(fields: "name")
}
~~~

Inventory can resolve name for Products returned from outOfStockProducts, though it cannot necessarily resolve name along every other Product query path.

@provides is an optional optimization. It can help the router avoid an extra call to Catalog for the provided field on that query path. Declare it only when the resolver truly guarantees the field can be returned at that path.

### 5.4. @shareable: allowing multiple subgraphs to resolve a field

In Federation 2, an object field is resolved by one subgraph by default. If multiple subgraphs can return the same field with the same semantics, mark it @shareable:

~~~graphql
extend schema
  @link(
    url: "https://specs.apollo.dev/federation/v2.3"
    import: ["@shareable"]
  )

type CurrencyInfo @shareable {
  code: String!
  symbol: String!
}
~~~

You can place @shareable on a type to apply it to all fields in that definition, or place it on individual fields. If a field is marked @shareable in one subgraph, other Federation 2 subgraphs defining that field must mark it @shareable or @external accordingly.

Only share a field when resolvers have equivalent semantics. If two subgraphs return different values for the same field, the router may choose different execution paths and clients will receive inconsistent results.

### 5.5. @inaccessible: rolling out fields incrementally

When adding a field to a value type defined by multiple subgraphs, updating one subgraph first can break composition because the other subgraph cannot yet resolve the new field.

You can mark the new field @inaccessible during the rollout phase:

~~~graphql
type Address @shareable {
  city: String!
  postalCode: String!
  deliveryZone: String! @inaccessible
}
~~~

The router still knows about the deliveryZone field in the supergraph, yet the field does not appear in the public API schema so clients cannot request it yet. Once all required subgraphs are updated and able to resolve the field, @inaccessible can be removed to expose the field.

@inaccessible is also useful when an internal field is used in @key but should not appear in the API schema. This directive is not a substitute for authorization; it only controls whether the field is included in the API schema.

### 5.6. @override: migrating a field to another subgraph

When moving a field from an old subgraph to a new subgraph, @override declares that the new subgraph takes over resolution responsibility:

~~~graphql
type Product @key(fields: "id") {
  id: ID!
  inStock: Boolean! @override(from: "Catalog")
}
~~~

Suppose Catalog previously resolved Product.inStock. After deploying Inventory with an equivalent resolver, Inventory declares @override(from: "Catalog"). The supergraph shifts routing for that field to Inventory.

The name in `from` must match the exact subgraph name declared in the supergraph configuration or GraphOS. Only one subgraph may override a field at a time; declaring multiple overrides for the same field causes a composition error.

Federation 2.7 and above also support progressive @override with traffic percentage labels, allowing gradual traffic shifting and monitoring before completing migration. Check your Federation spec and router version before using this feature.

## 6. Composition rules to remember

The composition engine enforces many rules. The most common errors involve field ownership, field signatures, and resolvability.

### 6.1. Do not duplicate field definitions unless shareable

In Federation 2, multiple subgraphs cannot define the same object field unless the field is marked @shareable. If a field is resolved by only one subgraph, another subgraph can declare it @external when it needs to reference it in @requires or @provides.

### 6.2. Shared fields must have compatible signatures

Subgraphs resolving the same field must have compatible return types and argument types. The following example fails to compose:

~~~graphql
# Catalog
type Event @shareable {
  timestamp: String!
}

# Analytics
type Event @shareable {
  timestamp: Int!
}
~~~

One subgraph returns String while the other returns Int. Composition cannot choose a single definition for the supergraph and therefore fails.

### 6.3. Fields must be resolvable along every valid query path

Suppose two subgraphs both define the value type Position:

~~~graphql
# Subgraph A
type Query {
  positionA: Position!
}

type Position @shareable {
  x: Int!
  y: Int!
}

# Subgraph B
type Query {
  positionB: Position!
}

type Position @shareable {
  x: Int!
  y: Int!
  z: Int!
}
~~~

The two schemas are valid individually, yet composition can fail. The supergraph merges Position with field z. A client could request positionA.z, but Subgraph A cannot resolve z and Subgraph B cannot identify the Position instance returned from positionA if this type is not an entity.

There are three common ways to handle this:

1. Define and resolve field z in every subgraph that defines Position. Subgraphs without data can return null if the schema allows it.
2. Mark the new field @inaccessible during rollout, then remove the directive once all subgraphs are ready.
3. Turn Position into an entity with @key if it truly has a stable identifier, allowing the router to hop to another subgraph.

Do not use @shareable merely to silence composition errors. @shareable asserts that every marked subgraph can resolve that field consistently.

### 6.4. Union and intersection when merging types

Composition uses two strategies:

- Union: takes all components contributed by the subgraphs.
- Intersection: takes only components defined in every participating subgraph.

| Schema element | Typical strategy |
|---|---|
| Object type | Union of fields |
| Union type | Union of member types |
| Interface type | Union of fields |
| Input object | Intersection of input fields |
| Field arguments | Intersection of arguments |

Example of two subgraphs defining User:

~~~graphql
# Accounts
type User @key(fields: "id") {
  id: ID!
  name: String!
}

# Profiles
type User @key(fields: "id") {
  id: ID!
  avatarUrl: String
}
~~~

The supergraph can contain both name and avatarUrl because object types are merged by union. The router uses the entity key to transfer User from Accounts to Profiles when avatarUrl is needed.

Conversely, input objects and field arguments use intersection so the router does not send an argument a subgraph does not understand. If intersection drops a non-null input field or argument required by a subgraph, composition fails.

Enums have rules depending on usage. If an enum is output-only, values can be merged by union. If an enum is used as an input or argument, values must be intersected so the router does not send a value unsupported by a subgraph. If an enum is used as both output and input, the definitions must match.

## 7. Performing schema composition with Rover CLI

Apollo provides two common ways to perform composition:

- GraphOS managed composition: publish subgraph schemas to GraphOS. GraphOS automatically composes the latest schemas and updates the supergraph if composition succeeds.
- Local composition with Rover CLI: suited for local development, pre-publish verification, and CI pipelines.

### 7.1. Creating supergraph.yaml

The configuration file describes the Federation version, routing URL, and SDL source of each subgraph:

~~~yaml
federation_version: =2.3.2
subgraphs:
  catalog:
    routing_url: http://localhost:8081/graphql
    schema:
      file: ./schemas/catalog.graphql
  inventory:
    routing_url: http://localhost:8082/graphql
    schema:
      file: ./schemas/inventory.graphql
  shipping:
    routing_url: http://localhost:8083/graphql
    schema:
      file: ./schemas/shipping.graphql
~~~

In this example, schema.file points to each subgraph's exported SDL. Rover also supports fetching SDL via introspection or from a GraphOS graph reference. The routing URL is the address the router will use to send operations to the respective service.

The Federation version in the configuration file must be compatible with the directives used by the SDL. Do not choose a version lower than required for newer directives.

### 7.2. Running composition

Run the command:

~~~bash
rover supergraph compose --config ./supergraph.yaml
~~~

To save the output as an artifact:

~~~bash
rover supergraph compose \
  --config ./supergraph.yaml \
  --output ./build/supergraph.graphql
~~~

The supergraph.graphql file is an internal schema meant for the router/gateway. Do not use this file as the public schema for GraphQL clients and do not edit it manually to fix composition errors. Fix the subgraph SDL or directives and re-run composition.

If composition fails, Rover returns an error and does not produce a valid new supergraph. Treat this as a build step akin to compilation: the router should not be deployed with a broken schema composition.

### 7.3. Automated composition with GraphOS

In managed federation, after publishing a subgraph's schema, GraphOS composes the latest versions of all subgraphs. If successful, the router can receive the new supergraph via the configured schema distribution mechanism.

A composition failure does not mean the newly published schema must be deleted from the registry. The registry can reflect the running subgraph schema while the supergraph/router retains the previous successful composition. Inspect the composition status in GraphOS and resolve conflicts before proceeding with deployment.

## 8. Integrating a Federation subgraph in Spring for GraphQL

Spring for GraphQL integrates with the federation-jvm library to build a GraphQL schema for a subgraph. When using Spring Boot, declare FederationSchemaFactory and configure GraphQlSourceBuilderCustomizer:

~~~java
@Configuration
public class FederationConfig {

    @Bean
    GraphQlSourceBuilderCustomizer federationCustomizer(
            FederationSchemaFactory factory) {
        return builder -> builder.schemaFactory(factory::createGraphQLSchema);
    }

    @Bean
    FederationSchemaFactory federationSchemaFactory() {
        return new FederationSchemaFactory();
    }
}
~~~

FederationSchemaFactory creates a schema with the required federation components such as _service and _entities. When configuring with Spring Boot, GraphQlSourceBuilderCustomizer lets you swap the schema factory while preserving Boot's GraphQlSource creation mechanism.

This is subgraph-side configuration. It does not compose multiple services and does not run a router. The supergraph is still produced by GraphOS or the Rover CLI as described earlier.

### 8.1. Inspecting the SDL published by a subgraph

A subgraph exposes the _service field so the router or federation tools can fetch its SDL:

~~~graphql
query {
  _service {
    sdl
  }
}
~~~

The returned SDL must include the Federation directives and type extensions required by the composition engine. When debugging composition, inspect the actual SDL published by the running service instead of only reading schema files in source code, because runtime wiring or the schema factory can alter the final schema.

### 8.2. Resolving entities in Spring

The router calls the _entities field with a list of representations. Spring for GraphQL maps each representation to an @EntityMapping method:

~~~java
@Controller
public class ProductController {

    private final ProductService productService;

    public ProductController(ProductService productService) {
        this.productService = productService;
    }

    @EntityMapping
    public Product product(@Argument String id) {
        return productService.findById(id);
    }
}
~~~

The @Argument parameter is extracted from the representation map. The method can also accept the entire Map<String, Object>, a list of representations when batch loading, GraphQLContext, or DataLoader as needed.

Other fields of Product continue to be resolved via @SchemaMapping. If multiple entities need to be loaded at once, you can accept a list of keys and return a list of entities in the exact order, or use @BatchMapping and DataLoader to reduce data access calls.

Successful composition does not guarantee entity resolvers work properly. Test the schema contract, entity lookups, and contributed fields separately.

## 9. Checking schema changes in CI

Composition should be a mandatory check before publishing schemas. You can combine two levels of validation:

1. Local composition checks that subgraph SDLs can form a valid supergraph.
2. GraphOS schema checks verify whether changes break operations currently used by clients.

Example checking a subgraph registered in GraphOS:

~~~bash
rover subgraph check commerce@current \
  --name catalog \
  --schema ./schemas/catalog.graphql
~~~

The command requires the graph reference, subgraph name, and new SDL. The build check verifies the schema can compose with the remaining subgraphs. The operations check compares changes against collected operation metrics to catch fields or types in active client use that are removed or changed incompatibly.

Linter checks can detect convention and best-practice issues. If GraphOS has no operation metrics to compare against, potentially breaking changes may be flagged as unsafe. Configure operation metrics reporting before relying on operations checks.

### Suggested pipeline

~~~mermaid
flowchart TD
    A[Pull request modifies subgraph SDL] --> B[Validate GraphQL SDL]
    B --> C[rover subgraph check]
    C --> D{Composition and checks pass?}
    D -- No --> E[Fail pull request]
    D -- Yes --> F[Build and test subgraph]
    F --> G[Deploy subgraph]
    G --> H[Wait for replicas ready]
    H --> I[Publish subgraph SDL]
    I --> J[GraphOS composes supergraph]
    J --> K[Router receives new schema]
~~~

Publish the schema only after subgraph replicas are already running the corresponding code version. If you publish new SDL before deploying new resolvers, the router may send operations to a subgraph that does not yet have the required field or entity resolver.

A passing schema check does not completely eliminate race conditions. Another subgraph might change while the pipeline is running. Therefore, GraphOS still runs composition upon publishing, and the pipeline must handle composition failures.

## 10. Common composition errors

| Symptom | Possible cause | Solution |
|---|---|---|
| Field defined in multiple subgraphs | Missing @shareable or unclear ownership | Pick one owner or declare shareable if resolvers are truly equivalent |
| Shared field has different return types | Incompatible subgraph SDLs | Align scalar, nullability, list shape, and arguments |
| Value type field cannot be resolved | One subgraph contributes a field another subgraph cannot resolve | Use an entity, implement the field everywhere, or roll out with @inaccessible |
| @requires reports invalid field | Dependency field not declared or not marked @external | Declare the field external and check the FieldSet |
| @provides fails composition | Field not external, not shareable in another subgraph, or unresolvable on that path | Check ownership and the query path providing the field |
| Federation 2 directives unrecognized | Missing @link or directive omitted from import | Add @link and import the required directives |
| @override cannot find source | `from` value does not match subgraph name | Match the name in supergraph.yaml or GraphOS |
| Entity not routed to subgraph by router | Missing @key or incompatible keys | Declare a stable key and an entity resolver |
| Input field or argument disappears after composition | Subgraphs define them differently; composition uses intersection | Synchronize input fields and arguments, especially non-null ones |
| Supergraph composes successfully but requests fail | Resolver, entity mapping, or service runtime not properly implemented | Test _entities and queries through the router |
| GraphOS does not update router | New composition failed or launch incomplete | Check composition result and launch status |

## 11. Schema composition testing checklist

Before accepting a schema change:

1. Each subgraph has valid SDL matching the right Federation version.
2. Federation 2 subgraphs have @link and import all directives in use.
3. Each entity has a stable @key and participating subgraphs can identify the key.
4. Fields have clear owners; duplicate fields are shared only with appropriate @shareable.
5. @requires fields declare @external and dependency data is genuinely available.
6. @provides fields appear only on paths where the subgraph can resolve them.
7. Input types and arguments are compatible across subgraphs.
8. New fields on value types are rolled out safely.
9. @override points to the exact source subgraph name and only one subgraph overrides.
10. Rover supergraph compose or GraphOS build check succeeds.
11. Operations checks detect no unexpected broken client operations.
12. Subgraph returns the right SDL via _service.sdl.
13. Entity lookup via _entities works with realistic representations.
14. End-to-end queries through the router return fields from all subgraphs.
15. Resolver code is deployed before the new schema is published.

Composition confirms that schemas can combine structurally. It does not replace integration tests, authorization tests, performance tests, or verifying real subgraph data.

## 12. Schema design and rollout workflow

When adding or moving fields in a federated graph:

1. Identify which domain owns the field's data and resolver.
2. Decide whether the field belongs to an entity or a value type.
3. If an entity, define a stable key and entity resolvers in each subgraph.
4. If resolved by multiple subgraphs, evaluate semantics before using @shareable.
5. If dependent on data from another subgraph, describe dependencies with @external and @requires.
6. Only use @provides when the subgraph can supply the field along a specific query path.
7. Use @inaccessible to roll out new fields incrementally if needed.
8. Use @override when transferring field resolution ownership and monitor the migration.
9. Run composition and schema checks in CI.
10. Deploy code and resolvers first, then publish the corresponding SDL.
11. Inspect query plans and traces on the router to verify reasonable subgraph call counts.
12. Remove temporary directives after rollout completes and re-run composition.

Schema composition is the step that merges and validates contracts across subgraphs. Apollo Federation uses directives to describe entity identity, field ownership, shared fields, and dependencies; the composition engine produces the supergraph for the router to route operations. Spring for GraphQL implements the subgraph side with FederationSchemaFactory, @EntityMapping, and standard resolvers. Combining composition with schema checks, integration tests, and controlled rollouts enables teams to evolve schemas independently while maintaining one unified GraphQL API.

## References

- Spring for GraphQL — Federation: https://docs.spring.io/spring-graphql/reference/federation.html
- Apollo Federation — Schema Composition: https://www.apollographql.com/docs/graphos/schema-design/federated-schemas/composition
- Apollo Federation — Composition Rules: https://www.apollographql.com/docs/graphos/schema-design/federated-schemas/reference/composition-rules
- Apollo Federation — Directives: https://www.apollographql.com/docs/graphos/schema-design/federated-schemas/reference/directives
- Apollo Rover — Supergraph Commands: https://www.apollographql.com/docs/rover/commands/supergraphs
- Apollo GraphOS — Schema Checks: https://www.apollographql.com/docs/graphos/platform/schema-management/checks

# Deploying multi-module schemas

As a Spring for GraphQL application grows, the SDL schema typically expands alongside the number of domains and development teams. Placing every type, query, mutation, and input into a single file makes code reviews harder, increases merge conflicts when multiple teams edit simultaneously, and blurs data ownership boundaries.

You can split the schema across multiple files and multiple Java modules, then merge them at application startup. Each module owns the SDL and resolvers for its domain; Spring Boot discovers resources on the runtime classpath, Spring for GraphQL combines them into one schema, and GraphQL Java validates the merged schema.

This lesson explains how to organize SDL by feature/domain, extend root types with type extensions, configure Spring Boot to scan schemas inside dependency JARs, coordinate DataFetchers and annotated controllers across modules, and validate the schema during build and deployment. The examples use a modular monolith application: Catalog, Orders, and Inventory run together inside one Spring Boot application and expose a single GraphQL endpoint.

## 1. Understanding multi-module schemas

A multi-module schema has two organizational layers:

- **Multiple SDL files:** splitting a single logical schema into smaller files by domain or feature.
- **Multiple build modules:** each Gradle/Maven module can package its domain's SDL and Java code into a separate JAR. The GraphQL application depends on these modules at runtime.

When the application starts up, discovered SDL resources are parsed and merged into a single `GraphQLSchema`. Clients still see a unified GraphQL API. SDL folder names or Gradle module names do not create separate GraphQL namespaces.

~~~mermaid
flowchart TD
    A[Catalog module] --> D[Runtime classpath]
    B[Orders module] --> D
    C[Inventory module] --> D
    D --> E[Spring Boot schema resource scanning]
    E --> F[Merge SDL definitions and extensions]
    F --> G[GraphQLSchema]
    H[RuntimeWiringConfigurer beans] --> I[RuntimeWiring]
    J[Annotated controllers] --> I
    I --> K[Executable schema]
    G --> K
    K --> L[GraphQL endpoint]
~~~

This differs from Apollo Federation. The modules in this lesson are loaded into the same process and composed into a single schema at startup. If Catalog, Orders, and Inventory are independently deployed services, each owning its own endpoint, classpath scanning cannot merge schemas from remote services; in that case, you need a gateway/federation architecture or an appropriate schema registry mechanism.

## 2. Splitting SDL by domain and feature

Choose file boundaries around business capabilities that a single team can own and evolve independently. For example:

~~~text
src/main/resources/
└── graphql/
    ├── common/
    │   ├── scalars.graphqls
    │   └── pagination.graphqls
    ├── catalog/
    │   ├── catalog.graphqls
    │   └── product-search.graphqls
    ├── orders/
    │   └── orders.graphqls
    └── inventory/
        └── inventory.graphqls
~~~

In a Gradle multi-project build, resources can live inside each module:

~~~text
catalog/
└── src/main/
    ├── java/com/acme/catalog/...
    └── resources/graphql/catalog/catalog.graphqls

orders/
└── src/main/
    ├── java/com/acme/orders/...
    └── resources/graphql/orders/orders.graphqls

inventory/
└── src/main/
    ├── java/com/acme/inventory/...
    └── resources/graphql/inventory/inventory.graphqls

app/
└── src/main/resources/application.yml
~~~

Directory names help readers recognize which domain owns a file. All types still belong to the same GraphQL type system after merging; therefore, type, field, enum, input, and directive names must be unique in the final schema.

### 2.1. One module owns the base definition

For example, Catalog owns the `Product` definition and the root `Query` type:

~~~graphql
type Query {
  product(id: ID!): Product
  products: [Product!]!
}

type Product {
  id: ID!
  name: String!
  price: Float!
}
~~~

Orders owns `Order` and the root `Mutation` type. This module can also contribute a query field to the `Query` already defined by Catalog:

~~~graphql
extend type Query {
  order(id: ID!): Order
}

type Mutation {
  placeOrder(input: PlaceOrderInput!): Order!
}

input PlaceOrderInput {
  productId: ID!
  quantity: Int!
}

type Order {
  id: ID!
  status: String!
  quantity: Int!
}
~~~

Inventory adds fields belonging to inventory responsibilities:

~~~graphql
extend type Query {
  lowStockProducts: [Product!]!
}

extend type Product {
  inventory: InventorySummary!
}

type InventorySummary {
  available: Int!
  reserved: Int!
}
~~~

The merged result has one `Query` type containing `product`, `products`, `order`, and `lowStockProducts`; one `Mutation` type containing `placeOrder`; and one `Product` type with an added `inventory` field. Each module defines the base types it owns exactly once. Other modules use `extend type` to contribute fields to existing types.

In the example above, the schema uses the default root convention names `Query` and `Mutation`, so no separate `schema` definition is needed. If an application uses custom root type names, declare the `schema` definition once in a foundational file and ensure every referenced root type is defined in the merged SDL set.

### 2.2. Using type extensions properly

GraphQL SDL supports:

- `extend type Query` to add query fields.
- `extend type Mutation` to add mutation fields.
- `extend type Subscription` to add subscription fields.
- `extend type Product` to add fields to an object type owned by another domain.
- `extend interface` or `union` when extending abstract types according to GraphQL rules.

The extended type must have a base definition in the schema set. For example, `extend type Product` will fail if the Catalog module is missing from the runtime classpath or does not provide type `Product`.

Do not create multiple base `type Query`, `type Product`, or `type Mutation` definitions across standalone files. Choose one module to own the base definition; remaining modules contribute via extensions. Avoid re-declaring an already existing field inside an extension, because each field should have a single unambiguous definition of its return type, arguments, and nullability.

## 3. Packaging schemas in a Gradle multi-module build

Every standard Java module can package SDL inside its JAR using the default `resources` source set. No dedicated GraphQL plugin is needed just to include `.graphqls` files in a JAR.

Example dependency configuration for the application:

~~~gradle
// app/build.gradle
dependencies {
    implementation(project(":catalog"))
    implementation(project(":orders"))
    implementation(project(":inventory"))

    implementation("org.springframework.boot:spring-boot-starter-graphql")
}
~~~

If a module contains only SDL and no Java types referenced at compile time, it can be declared as a runtime dependency:

~~~gradle
dependencies {
    runtimeOnly(project(":shared-graphql-schema"))
}
~~~

What matters is that the JAR containing the schema is present on the GraphQL application's runtime classpath. If a module is omitted from the dependency graph, Spring Boot will not discover its resources.

Verify that resources were packaged into the module JAR:

~~~bash
./gradlew :catalog:jar
jar tf catalog/build/libs/catalog-1.0.0.jar | grep graphql/
~~~

On PowerShell, you can filter the output with:

~~~powershell
jar tf catalog/build/libs/catalog-1.0.0.jar | Select-String 'graphql/'
~~~

In a Spring Boot executable JAR, dependency modules typically live under `BOOT-INF/lib` as nested JARs. Inspect each module's JAR and test the packaged application to confirm resources are discovered on the runtime classpath.

## 4. Configuring Spring Boot to scan schemas across modules

By default, Spring Boot searches for files with extensions `.graphqls` or `.gqls` under `classpath:graphql/**`. When schemas live across multiple dependency JARs, use the `classpath*` prefix to search for matching resources across all classpath locations.

~~~yaml
spring:
  graphql:
    schema:
      locations: classpath*:graphql/**/
      file-extensions: .graphqls,.gqls
~~~

Property meanings:

| Property | Meaning |
|---|---|
| `spring.graphql.schema.locations` | Locations where Spring Boot searches for SDL resources |
| `classpath*:graphql/**/` | Search `graphql` directories across multiple classpath locations, including dependency JARs |
| `spring.graphql.schema.file-extensions` | File extensions recognized as schema files |

In Spring Boot versions that support schema mapping inspection, you can also enable:

~~~yaml
spring:
  graphql:
    schema:
      inspection:
        enabled: true
~~~

Check the application properties of the exact Spring Boot version in use before adding this optional property.

Crucial distinction:

- `classpath:` typically resolves resources in a single classpath location.
- `classpath*:` enables Spring's `ResourcePatternResolver` to locate matching resources across multiple classpath locations.

If it only works when SDL lives in `app/src/main/resources` yet types disappear when moving SDL into a module dependency, check the `classpath*:` prefix. Also verify the module dependency is on the runtime classpath and the JAR contains the expected `graphql/` path.

Spring Boot discovers resources based on the configured pattern and file extensions. Folder names like `catalog`, `orders`, or `inventory` are purely organizational; they do not automatically create separate schemas or scope types.

## 5. Spring for GraphQL merges resources and runtime wiring

`GraphQlSource` is Spring for GraphQL's abstraction for supplying the `GraphQL` instance. The default builder accepts one or more Spring `Resource` instances, parses them, and merges them into a logical schema before creating the executable `GraphQLSchema`.

When using the Spring Boot starter, auto-configuration creates the `GraphQlSource` builder, loads schema resources per configuration, detects `RuntimeWiringConfigurer` and `Instrumentation` beans, and builds the schema. Consequently, typical applications only need to configure `locations` and declare module dependencies.

If you need to build `GraphQlSource` manually in a custom setup, the builder accepts multiple resources:

~~~java
GraphQlSource.Builder builder = GraphQlSource.schemaResourceBuilder()
        .schemaResources(catalogSchema, ordersSchema, inventorySchema)
        .configureRuntimeWiring(runtimeWiringConfigurer);
~~~

This illustrates the builder API when you already have the corresponding `Resource` instances. In a Spring Boot application, prefer letting Boot discover resources via classpath patterns. Replace `GraphQlSource` yourself only when you genuinely need control over schema sources or schema creation; if you declare your own `GraphQlSource` bean, you become responsible for all configuration previously supplied by auto-configuration.

### 5.1. Merging mechanism in GraphQL Java

GraphQL Java parses each SDL into a `TypeDefinitionRegistry`. Multiple registries can be merged into one registry before `SchemaGenerator` builds the `GraphQLSchema`:

~~~java
SchemaParser parser = new SchemaParser();
TypeDefinitionRegistry registry = new TypeDefinitionRegistry();

for (Resource resource : schemaResources) {
    try (InputStream input = resource.getInputStream()) {
        registry.merge(parser.parse(input));
    }
}

GraphQLSchema schema = new SchemaGenerator()
        .makeExecutableSchema(registry, runtimeWiring);
~~~

This snippet illustrates merging at the GraphQL Java level. In a Spring for GraphQL application, `GraphQlSource.Builder.schemaResources(...)` handles loading and merging resources; you do not need to parse each file manually unless you have custom requirements.

Merging does not turn files into isolated schemas. GraphQL Java validates all type references, root operations, fields, arguments, directives, and scalars across the shared registry. A type referenced in the Inventory module must have a valid definition somewhere in the entire SDL set loaded by the application.

## 6. Each module manages its own domain resolvers

SDL only describes the contract. It does not automatically connect fields to services or repositories. Each module must register its corresponding `DataFetcher`s via annotated controllers or `RuntimeWiringConfigurer`.

Catalog can use a controller for the `product` query:

~~~java
@Controller
public class CatalogGraphQlController {

    private final CatalogService catalogService;

    public CatalogGraphQlController(CatalogService catalogService) {
        this.catalogService = catalogService;
    }

    @QueryMapping
    public Product product(@Argument String id) {
        return catalogService.findById(id);
    }
}
~~~

Inventory owns the resolver for the `inventory` field added to `Product`:

~~~java
@Controller
public class InventoryGraphQlController {

    private final InventoryService inventoryService;

    public InventoryGraphQlController(InventoryService inventoryService) {
        this.inventoryService = inventoryService;
    }

    @SchemaMapping(typeName = "Product", field = "inventory")
    public InventorySummary inventory(Product product) {
        return inventoryService.getSummary(product.id());
    }
}
~~~

Orders can register mutations:

~~~java
@Controller
public class OrdersGraphQlController {

    private final OrderService orderService;

    public OrdersGraphQlController(OrderService orderService) {
        this.orderService = orderService;
    }

    @MutationMapping
    public Order placeOrder(@Argument PlaceOrderInput input) {
        return orderService.place(input);
    }
}
~~~

Spring for GraphQL detects controllers and registers annotated methods as `DataFetcher`s. When modules are packaged as dependency JARs, ensure their controller packages fall under component scanning or are explicitly imported. SDL resources can load successfully while a controller bean has not been created by Spring; verify both steps separately.

In this example, `Product` is a Java type shared between Catalog and Inventory. Place this projection/contract in a shared API module, such as `catalog-api` or `graphql-contract`, so Inventory depends only on the type needed by its resolver. If `Product` lives directly inside the Catalog module, Inventory needs a compile dependency on the module containing `Product`; avoid pulling in Catalog's entire persistence implementation just to receive the source object.

### 6.1. RuntimeWiringConfigurer from multiple modules

Modules can also contribute `RuntimeWiringConfigurer` beans to register custom scalars, directives, `TypeResolver`s, or low-level `DataFetcher`s:

~~~java
@Configuration(proxyBeanMethods = false)
public class CatalogGraphQlConfiguration {

    @Bean
    RuntimeWiringConfigurer catalogRuntimeWiring() {
        return builder -> builder.scalar(CatalogScalars.money());
    }
}
~~~

Spring Boot discovers `RuntimeWiringConfigurer` beans and applies them to the `GraphQlSource` builder. Each module can register its own configurer, provided the module's configuration class is component-scanned or imported into the application context.

In general, use `@QueryMapping`, `@MutationMapping`, `@SchemaMapping`, and `@BatchMapping` for business resolvers. `RuntimeWiringConfigurer` is suited for shared components or cases requiring low-level GraphQL Java APIs.

Do not let two modules register `DataFetcher`s for the same type/field coordinate unless intentional and explicit. When multiple modules contribute to the same object type, divide fields via SDL extensions and assign each field to a single resolver owner.

## 7. Design rules to prevent schema conflicts

| Rule | Reason |
|---|---|
| Each object/input/enum/scalar has one base definition | Avoid duplicate type names during merge |
| Only one module defines the base `Query`, `Mutation`, and `Subscription` roots | Keep root type ownership clear |
| Other modules use `extend type` to add fields | Avoid redefining root or object types |
| Do not redefine existing fields | Avoid conflicts in return types, arguments, and nullability |
| Use consistent, domain-meaningful type names | Prevent two modules from accidentally creating types with the same name |
| Place shared scalars, enums, and input contracts in a shared module | Avoid diverging duplicate definitions |
| Keep module dependency graphs directed | Avoid circular dependencies between domains |
| Test the merged schema inside the application context | Verify resources and resolvers load together |

### 7.1. Be careful with type extensions

An extension can reference a type defined in another resource. However, the base type must be present in the final registry. For example:

- `inventory.graphqls` extends `Product`.
- `Product` must be defined in a resource that the application actually loads.
- If the `catalog` module is dropped from runtime dependencies, schema creation fails because `Product` does not exist.

Similarly, if a `payments` module extends `Mutation`, a base `type Mutation` must exist somewhere. Without it, a schema extension cannot conjure a root mutation type out of thin air.

### 7.2. Shared contracts and cross-domain dependencies

Not every data relationship should be modeled by extending another module's type. When a field is genuinely part of the API object, type extension is appropriate. If one domain only needs to reference another domain, you can use an ID or an explicit object reference to avoid deep coupling.

For instance, Inventory extending `Product` with an inventory summary makes sense if the API wants clients to query stock directly under `Product`. Yet Catalog should not have to depend on `InventoryService`'s implementation. Inventory's resolver is responsible for fetching stock data, while Catalog owns only the `Product` contract.

## 8. Common pitfalls when deploying multi-module schemas

| Symptom | Common cause | Diagnosis and resolution |
|---|---|---|
| Only schemas in the `app` module are loaded | Using `classpath:` instead of `classpath*:` | Change `locations` to `classpath*:graphql/**/` and check dependencies |
| Type referenced by another module is not found | Module is missing from runtime classpath or JAR lacks resources | Check Gradle dependencies and JAR contents |
| Duplicate type definition error | Multiple files define the same base type | Pick one owner; remaining files use `extend type` |
| Unknown type error in extension | Base type not loaded or misspelled | Check the resource containing the base type and spelling |
| Mutation root does not exist | No base `type Mutation` or schema definition omits mutation root | Add the base root definition exactly once |
| Query field appears in introspection yet always returns null | SDL loaded, yet matching resolver/property is missing | Check controllers, DataFetchers, and source objects |
| Module controller not detected | Package outside component scan scope or missing `@Import` | Adjust component scan or import module configuration |
| Two modules compete for the same resolver | Duplicate DataFetcher mapping for the same type/field | Designate one owner and remove duplicate registration |
| Works locally yet packaged JAR misses schemas | Resources excluded from artifact or dependency only in test/wrong runtime scope | Inspect module JARs and app runtime dependencies |
| Added new file yet schema unchanged | Wrong file extension or outside `locations` pattern | Check `.graphqls`/`.gqls` and `schema.locations` |

## 9. Testing the schema after merging

Testing each resolver in isolation is not enough. You need at least one integration test that boots the application context with all module dependencies to verify Spring Boot finds every SDL resource and builds the GraphQL schema successfully.

Add the test library:

~~~gradle
dependencies {
    testImplementation("org.springframework.graphql:spring-graphql-test")
}
~~~

You can use `ExecutionGraphQlServiceTester` to test server-side execution directly without opening an HTTP port:

~~~java
@SpringBootTest
class ModularSchemaIntegrationTests {

    @Autowired
    ExecutionGraphQlService executionGraphQlService;

    private ExecutionGraphQlServiceTester tester;

    @BeforeEach
    void setUp() {
        tester = ExecutionGraphQlServiceTester.create(executionGraphQlService);
    }

    @Test
    void shouldResolveFieldsContributedByDifferentModules() {
        tester.document("""
                query {
                  product(id: "p-100") {
                    id
                    inventory {
                      available
                    }
                  }
                }
                """)
                .execute()
                .path("product", product -> product
                        .path("id").entity(String.class).isEqualTo("p-100")
                        .path("inventory.available").entity(Integer.class).isEqualTo(12));
    }
}
~~~

This test verifies an operation spanning a `Query` field owned by Catalog and the `inventory` field with which Inventory extends `Product`. It also confirms that SDL files and controllers from different modules participate in the same runtime schema.

Additional checks to include:

1. The application context starts up when all module dependencies are present.
2. Query fields from each domain work.
3. Fields added via `extend type` have matching resolvers.
4. Mutation root and mutation fields from owning modules work.
5. Shared interfaces/unions, scalars, and directives are wired properly.
6. Schema inspection finds no unexpected missing mappings.
7. Test against the executable JAR to confirm resources from dependency JARs are present at runtime.

If you also need to test HTTP transport, use `HttpGraphQlTester` with `WebTestClient`. `ExecutionGraphQlServiceTester` tests server-side execution; it does not verify HTTP routing, headers, or `WebGraphQlInterceptor`.

## 10. Schema validation in CI and during deployment

A multi-module schema must be verified at both compile/build time and application startup:

~~~mermaid
flowchart TD
    A[Change SDL or resolver in a module] --> B[Build module JAR]
    B --> C[Verify resources inside JAR]
    C --> D[Build app with full dependency graph]
    D --> E[Boot Spring context and merge schema]
    E --> F{Schema and mappings valid?}
    F -- No --> G[Fail CI and fix SDL or wiring]
    F -- Yes --> H[Run GraphQlTester integration tests]
    H --> I[Build executable JAR or image]
    I --> J[Deploy application]
    J --> K[Verify startup health and GraphQL smoke query]
~~~

Steps to include in the pipeline:

- Build all modules contributing SDL and confirm resources are packaged.
- Build the GraphQL application with the proper runtime dependencies.
- Boot the application context to catch parse, merge, and schema generation errors.
- Run integration tests via `GraphQlTester` covering fields contributed across multiple modules.
- Run schema compatibility checks if the API has external clients or consumers.
- Build and verify the executable JAR/container image before deploying.

Spring for GraphQL builds the schema when the application starts. If a module resource is missing, schema creation can fail immediately at startup; if the resource exists yet the controller is not discovered, mappings may be missing. Never treat individual module build success as proof that the whole application's schema is valid.

SDL schemas packaged inside JARs are static resources. Changing a schema in a module requires building a new artifact and deploying the application version containing that artifact. If you need to update schemas dynamically at runtime without redeploying the application, you need a dedicated resource/schema registry architecture and refresh mechanism; default classpath configuration does not watch for changes inside JARs.

## 11. Pre-release checklist

- [ ] Every base type has one clear owning module.
- [ ] `Query`, `Mutation`, and `Subscription` roots are defined exactly once.
- [ ] Other modules extend root/object types via `extend type`.
- [ ] There are no unintentional duplicate field or type names.
- [ ] All SDL resources use configured `.graphqls` or `.gqls` extensions.
- [ ] Spring Boot uses `classpath*:` when scanning dependency JARs.
- [ ] Schema modules are included in the runtime dependency graph.
- [ ] Module JARs actually contain the `graphql/` directory.
- [ ] Module controllers/configurations are component-scanned or imported.
- [ ] `RuntimeWiringConfigurer` beans do not register conflicting `DataFetcher`s.
- [ ] Schema inspection and integration tests report no unexpected errors.
- [ ] Tests run against the full application context and executable artifact.
- [ ] Modules are released with compatible versions within the same deployment.

Deploying multi-module schemas is a way to split a GraphQL contract by domain while maintaining a single unified API. Let each module own its SDL and resolvers, use type extensions to contribute fields to base types, configure Spring Boot to scan resources across the entire runtime classpath, and test the merged schema. When domains become independently deployed services, transition to a gateway/federation model rather than trying to use classpath resource scanning to stitch remote schemas together.

## References

- Spring Boot — Spring for GraphQL: https://docs.spring.io/spring-boot/reference/web/spring-graphql.html
- Spring Boot — Application Properties (`spring.graphql.schema`): https://docs.spring.io/spring-boot/appendix/application-properties/
- Spring for GraphQL — Request Execution and Schema Resources: https://docs.spring.io/spring-graphql/reference/request-execution.html
- Spring for GraphQL — Testing: https://docs.spring.io/spring-graphql/reference/testing.html
- GraphQL Java — Schema and Modularising the Schema SDL: https://graphql-java.com/documentation/schema/

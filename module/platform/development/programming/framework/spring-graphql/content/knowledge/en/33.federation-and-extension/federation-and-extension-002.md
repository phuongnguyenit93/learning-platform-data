# FederationSchemaFactory

Apollo Federation enables multiple GraphQL subgraphs to each publish a part of a data graph. A gateway combines the schemas of the subgraphs into a supergraph, then breaks down client queries into requests sent to the appropriate services.

In Spring for GraphQL, FederationSchemaFactory is the component that integrates with the federation-jvm library to build a GraphQL schema following the subgraph protocol. The factory transforms TypeDefinitionRegistry and RuntimeWiring into a GraphQLSchema with the required federation components, while also detecting controller methods annotated with @EntityMapping to resolve entities when the gateway calls _entities.

An important point is that FederationSchemaFactory is neither a gateway nor does it write business data queries on its own. It prepares the federation schema and connects gateway entity representations to controller methods inside the subgraph. The application still has to declare the SDL, implement entity lookups, secure the data, and test the protocol.

## 1. What problem does FederationSchemaFactory solve?

A regular GraphQL service can handle queries starting from root fields such as books or authors. In Federation, the gateway might need to fetch an entity from another subgraph and then ask the current subgraph to supply fields that belong to its responsibility.

For example:

- The Catalog subgraph owns Book with id, title, and price.
- The Review subgraph extends Book with reviews and rating.
- The gateway receives a query containing both title and reviews.
- The gateway calls Catalog to fetch Book, then calls Review to resolve the Book entities based on their key.

The Review subgraph needs to understand the Book representation, look up the corresponding data or context, and return the fields it owns. Apollo Federation standardizes this step through entity keys and the _entities field.

FederationSchemaFactory helps Spring for GraphQL prepare the schema and entity data fetcher for that flow. The application only needs to declare entity mappings using @EntityMapping instead of manually writing a DataFetcher for the _entities field and a type resolver for each entity.

## 2. Related concepts

| Concept | Role |
| --- | --- |
| Supergraph | The combined schema that clients use |
| Subgraph | A GraphQL service that owns or extends a portion of the schema |
| Federation gateway/router | The component that receives client queries and builds a query plan to call subgraphs |
| Entity | An object that can be identified across subgraphs by a key |
| @key | Directive declaring the set of fields used to identify an entity |
| Representation | An object the gateway sends to a subgraph, typically containing __typename and key fields |
| _entities | Root field used to resolve a list of entity representations |
| _service | Root field providing the subgraph's SDL for composition |
| FederationSchemaFactory | Factory that creates the federation schema and wires entity mappings in Spring |
| @EntityMapping | Annotation marking a method that loads an entity from a representation |

A subgraph can own an entity or only extend an entity owned by another subgraph. Field ownership and entity keys must be clearly designed in the Federation SDL.

## 3. Role of FederationSchemaFactory in the architecture

The initialization and execution flow can be visualized as:

~~~mermaid
flowchart TD
    A[SDL resources] --> C[GraphQlSource.Builder]
    B[RuntimeWiringConfigurer] --> C
    D[FederationSchemaFactory] --> C
    C --> E[Subgraph GraphQLSchema]
    E --> F[_service and _entities]
    E --> G[EntityMapping DataFetchers]
    H[Federation Gateway] --> I[Query plan]
    I --> J[Subgraph endpoint]
    J --> K[_entities representations]
    K --> G
    G --> L[Entity instances]
    L --> M[SchemaMapping and BatchMapping]
    M --> N[Entity fields in response]
~~~

The factory participates when GraphQlSource builds the GraphQLSchema. When requests arrive, GraphQL execution uses the generated schema to execute normal queries or entity resolution from the gateway.

FederationSchemaFactory does not route requests between services, does not replace the gateway, and does not compose schemas into a supergraph on its own. Those responsibilities belong to the federation router/gateway and the composition tool.

## 4. Configuring FederationSchemaFactory

In Spring Boot configuration, declare FederationSchemaFactory as a bean and register the schema factory callback on GraphQlSourceBuilderCustomizer:

~~~java
import org.springframework.boot.autoconfigure.graphql.GraphQlSourceBuilderCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
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

In this configuration:

1. Spring creates FederationSchemaFactory as a bean.
2. The factory is managed by the Spring application context and detects controller methods annotated with @EntityMapping.
3. GraphQlSourceBuilderCustomizer instructs GraphQlSource.Builder to use factory::createGraphQLSchema.
4. When the schema is built, the factory uses federation-jvm to transform the schema registry/runtime wiring into a federation schema.

Do not instantiate the factory with `new` inside the callback if you want the factory to detect controllers in the Spring application context. Declaring it as a bean ensures lifecycle management and controller detection are properly set up.

GraphQlSourceBuilderCustomizer belongs to Spring Boot GraphQL auto-configuration. If you are not using Spring Boot, configure GraphQlSource.Builder manually and pass the schema factory callback to the corresponding builder.

## 5. FederationSchemaFactory operates during schema creation

By default, GraphQlSource uses GraphQL Java's SchemaGenerator to create a GraphQLSchema from type definitions and RuntimeWiring. When integrating federation, the schema needs extra processing to understand federation directives and entity resolution.

FederationSchemaFactory provides two notable methods:

| Method | Purpose |
| --- | --- |
| createGraphQLSchema(registry, wiring) | Creates a complete GraphQLSchema for the subgraph |
| createSchemaTransformer(registry, wiring) | Creates a SchemaTransformer so the application can further configure it before building the schema |

createGraphQLSchema sets up the _entities DataFetcher and TypeResolver for federated types via SchemaTransformer. Federation schema transformation also provides the required subgraph protocol components such as _service so the gateway can fetch the SDL.

In most applications, the factory::createGraphQLSchema callback is sufficient. Only use createSchemaTransformer when you need to call additional APIs on the federation SchemaTransformer before finalizing the schema.

## 6. Federation SDL and entity keys

An entity needs a key so the gateway can reference it across subgraphs. For example, Book is identified by id:

~~~graphql
type Book @key(fields: "id") {
    id: ID!
    title: String!
    price: Float
}
~~~

If another subgraph extends Book, that subgraph's schema can declare the extension:

~~~graphql
type Book @key(fields: "id") @extends {
    id: ID! @external
    author: Author
}

type Author {
    id: ID!
    name: String!
}
~~~

The example above illustrates Federation syntax with @extends and @external. The exact syntax depends on the Apollo Federation version used by the subgraph. Federation 2 has the @link mechanism and different directive declarations; do not arbitrarily mix Federation 1 SDL with Federation 2.

@key(fields: "id") indicates that the gateway can identify Book by the id field. @external indicates that the field is declared in another subgraph and referenced in the extending subgraph. The current subgraph can add the author field without re-owning title or price.

An entity can have multiple keys or a composite key made of multiple fields. With a composite key, the representation will contain all fields needed to resolve the entity. The entity mapping must read those exact fields.

## 7. Federation directives and the factory's role

Federation SDL can use directives such as:

| Directive | General meaning |
| --- | --- |
| @key | Declares the field set identifying an entity |
| @extends | Marks a type extended from another subgraph in the corresponding Federation syntax |
| @external | A field defined by another subgraph |
| @requires | The current field needs additional fields from the entity representation |
| @provides | Declares fields provided through a specific relationship |
| @shareable | Allows multiple subgraphs to resolve the same field under Federation 2 rules |
| @override | Transfers field resolution ownership from one subgraph to another under Federation 2 |

FederationSchemaFactory does not decide field ownership on behalf of the application. The factory uses the schema and federation directives to create the subgraph schema; gateway composition must still verify whether the directives are valid and whether the subgraphs are consistent.

Declaring directives without implementing an appropriate entity resolver is not enough for the gateway to access the entity. Conversely, having @EntityMapping without matching entity keys in the schema prevents the gateway from constructing valid representations.

## 8. _service and _entities

A federation subgraph has protocol-specific fields:

- _service { sdl }: returns the subgraph's SDL for the gateway or composition tool to read.
- _entities(representations: ...): accepts representations and returns the corresponding entities.

Example query to fetch SDL:

~~~graphql
query {
    _service {
        sdl
    }
}
~~~

Example entity query:

~~~graphql
query ResolveBook {
    _entities(
        representations: [
            { __typename: "Book", id: "book-01" }
        ]
    ) {
        ... on Book {
            id
            title
            author {
                id
                name
            }
        }
    }
}
~~~

Each representation contains __typename to identify the GraphQL entity type and the key fields. The gateway can send multiple representations in a single _entities call, including multiple entity types if the schema defines multiple entities.

_entities returns a list of entities corresponding to the representations. Because the result can contain multiple entity types, GraphQL clients typically use inline fragments to select fields per type.

## 9. @EntityMapping connects representations to Java objects

@EntityMapping marks a controller method used to load an entity from a representation:

~~~java
@Controller
public class BookFederationController {

    private final BookService bookService;

    public BookFederationController(BookService bookService) {
        this.bookService = bookService;
    }

    @EntityMapping
    public Book book(@Argument String id) {
        return bookService.findById(id);
    }

    @SchemaMapping
    public Author author(Book book) {
        return bookService.findAuthor(book);
    }
}
~~~

With the method name book, the entity name defaults to Book. You can declare the name explicitly when the method name does not match the entity type:

~~~java
@EntityMapping(name = "Book")
public Book resolveBook(@Argument String id) {
    return bookService.findById(id);
}
~~~

@EntityMapping does not replace @SchemaMapping. It handles the step of restoring the entity from the representation; the remaining fields of the entity can still use @SchemaMapping, @BatchMapping, or DataLoader like standard GraphQL.

## 10. @Argument is extracted from the representation

When the gateway sends:

~~~json
{
  "__typename": "Book",
  "id": "book-01"
}
~~~

Spring for GraphQL reads the representation map and binds the id field to the parameter:

~~~java
@EntityMapping
public Book book(@Argument("id") String bookId) {
    return bookService.findById(bookId);
}
~~~

The name in @Argument is the key in the representation. The value is converted to the Java type using Spring for GraphQL's argument binding mechanism.

If an entity uses a composite key or needs to inspect additional metadata, the method can accept the entire Map:

~~~java
@EntityMapping(name = "Book")
public Book book(Map<String, Object> representation) {
    String tenantCode = (String) representation.get("tenantCode");
    String isbn = (String) representation.get("isbn");
    return bookService.findByTenantAndIsbn(tenantCode, isbn);
}
~~~

The representation map can contain __typename and key fields. Do not trust those values as authentication credentials; they only identify the object for the resolver to look up. Authorization must still rely on the service's principal and policies.

## 11. Supported parameter types

An entity mapping method supports many parameter types:

| Parameter | Purpose |
| --- | --- |
| @Argument | Reads a named value from the representation and binds it to a Java type |
| Map<String, Object> | Reads the entire representation of a single entity |
| List<Map<String, Object>> | Reads multiple representations in a single entity mapping method |
| @ContextValue | Retrieves a value from GraphQLContext |
| @LocalContextValue | Retrieves a value from the local GraphQLContext |
| GraphQLContext | Accesses the context of DataFetchingEnvironment |
| Principal or @AuthenticationPrincipal | Accesses the authenticated principal if Spring Security is integrated |
| DataFetchingEnvironment | Low-level access to the execution context |
| DataFetchingFieldSelectionSet | Inspects the selection set of the entity query |
| DataLoader<I, E> | Loads entities through a DataLoader |
| Locale | Retrieves the request locale |

The method can return the entity directly or a supported async/reactive type such as Mono, CompletableFuture, or Callable. Choose a return type compatible with the application's execution model; do not block the event loop when using a reactive transport.

## 12. EntityMapping for multiple representations

The gateway can send multiple Book representations at once. Spring for GraphQL supports entity mapping accepting a list of IDs and returning a list of entities:

~~~java
@Controller
public class BookFederationController {

    private final BookService bookService;

    public BookFederationController(BookService bookService) {
        this.bookService = bookService;
    }

    @EntityMapping
    public List<Book> book(@Argument List<String> idList) {
        return bookService.findAllInOrder(idList);
    }
}
~~~

The parameter name idList helps Spring recognize this as a list of id values from multiple representations. The de-pluralization convention strips the List suffix to find the corresponding key name. You can declare the argument name explicitly if needed.

When returning a List or Flux for batch entity mapping, the order of entities must match the order of input representations. Do not return an unordered collection; if the repository returns results in a different order, reorder them according to the original ID list.

If you need to process complex representations individually, you can accept List<Map<String, Object>> and return results in the exact same order. This approach is useful for composite keys or when representations include additional metadata.

## 13. Combining DataLoader to load federated entities

If each representation contains only a single ID and you want to batch entity loads, you can use DataLoader:

~~~java
@Controller
public class BookFederationController {

    @EntityMapping
    public CompletableFuture<Book> book(
            @Argument String id,
            DataLoader<String, Book> bookLoader) {

        return bookLoader.load(id);
    }
}
~~~

Register the batch loader via BatchLoaderRegistry:

~~~java
@Component
public class BookBatchLoader {

    public BookBatchLoader(
            BatchLoaderRegistry registry,
            BookService bookService) {

        registry.forTypePair(String.class, Book.class)
            .registerMappedBatchLoader((ids, environment) ->
                Mono.fromCallable(() -> bookService.findMapped(ids)));
    }
}
~~~

In this example, bookService.findMapped(ids) returns a Map from ID to Book. DataLoader batches loads within the same GraphQL execution and dispatches the batch according to GraphQL Java's lifecycle.

DataLoader caches must be isolated per execution/request. Do not share entity caches across users or tenants if results depend on access permissions. If a batch loader uses blocking JPA in WebFlux, run it on an appropriate scheduler and place transactions on the service executing the batch.

## 14. Combining @BatchMapping for extended fields

After entities are restored, nested fields can use @BatchMapping:

~~~java
@Controller
public class BookFieldController {

    private final AuthorService authorService;

    public BookFieldController(AuthorService authorService) {
        this.authorService = authorService;
    }

    @BatchMapping(typeName = "Book", field = "author")
    public Map<Book, Author> author(List<Book> books) {
        return authorService.findByBooks(books);
    }
}
~~~

This flow separates two responsibilities:

1. @EntityMapping finds the Books based on representations from the gateway.
2. @BatchMapping loads Authors for multiple Books in a single batch.

Combining entity resolution and batch field mapping helps the subgraph handle multiple entities more efficiently, avoiding one query per representation and one query per nested field.

## 15. TypeResolver and Java class names

FederationSchemaFactory needs to map Java entity objects to GraphQL entity types. By default, the factory uses ClassNameTypeResolver.

If the Java class is named Book and the GraphQL type is also Book, the default mapping is usually suitable. If the Java class is named CatalogBook while the GraphQL type is Book, or if there is a hierarchy of multiple entity types, configure an explicit TypeResolver:

~~~java
@Bean
FederationSchemaFactory federationSchemaFactory() {
    FederationSchemaFactory factory = new FederationSchemaFactory();
    factory.setTypeResolver(environment -> {
        Object object = environment.getObject();
        if (object instanceof CatalogBook) {
            return environment.getSchema().getObjectType("Book");
        }
        return null;
    });
    return factory;
}
~~~

TypeResolver needs to return the GraphQL object type matching the entity instance. The example above illustrates the idea for a specific class; in a real application, handle all entity types managed by the factory and provide a clear fallback.

Do not configure a custom resolver if ClassNameTypeResolver already suffices. Misconfiguration can cause _entities to fail to determine the type of a returned object or fail when serializing the entity response.

The setTypeResolver method may vary across Spring for GraphQL versions. If you are on an older branch without this method, check the API for your exact version or customize SchemaTransformer according to available capabilities; do not copy configuration verbatim from another version's documentation.

## 16. Error handling in @EntityMapping

Entity mapping can encounter errors such as:

- Representation missing __typename.
- Representation missing required keys.
- Entity does not exist.
- Caller lacks permission to access the entity.
- Service/repository infrastructure errors.

Spring for GraphQL provides RepresentationException for cases where a representation is missing required information and RepresentationNotResolvedException when a resolver returns null or completes empty in situations where an entity cannot be resolved.

You can use @GraphQlExceptionHandler to turn exceptions from @EntityMapping into GraphQLError:

~~~java
@Controller
public class BookFederationController {

    @EntityMapping
    public Book book(@Argument String id) {
        return bookService.findById(id);
    }

    @GraphQlExceptionHandler
    public GraphQLError handleNotFound(
            BookNotFoundException exception,
            GraphqlErrorBuilder<?> builder) {

        return builder
            .errorType(ErrorType.NOT_FOUND)
            .message("Book not found")
            .build();
    }
}
~~~

The exception handler can be placed in the same controller or in @ControllerAdvice. The error will appear in the response of the _entities query. Messages sent to clients should not contain SQL, stack traces, tokens, or internal details.

## 17. Securing entity resolution

A representation sent by the gateway is not proof that the caller is allowed to access the entity. Each subgraph still needs to enforce authorization:

- Authenticate incoming requests to the subgraph according to the trust mechanism between the gateway and service.
- Obtain the principal/tenant from the security context or GraphQLContext.
- Check whether the caller has permission to read the requested entity.
- Do not trust tenantId, ownerId, or role merely because the representation contains them.
- Do not return data for fields belonging to another service if the caller lacks permission.
- Apply authorization inside batch loaders as well, not only in single-item resolvers.

For example:

~~~java
@EntityMapping
public Book book(
        @Argument String id,
        Principal principal) {

    return bookService.findVisibleTo(id, principal.getName());
}
~~~

If the gateway uses shared service credentials, the subgraph must know how to propagate end-user identity or authorization context according to the chosen architecture. Authenticating the gateway alone does not automatically prove the end user has access to every entity.

## 18. Verifying the federation schema after initialization

After configuring the factory, you can inspect _service.sdl:

~~~graphql
query {
    _service {
        sdl
    }
}
~~~

The returned SDL should contain the entity types and corresponding federation directives. This is a quick way to verify that the subgraph schema was created with federation support.

You can test _entities:

~~~graphql
query {
    _entities(
        representations: [
            { __typename: "Book", id: "book-01" }
        ]
    ) {
        ... on Book {
            id
            title
        }
    }
}
~~~

If _service or _entities does not exist, check whether the schemaFactory callback is attached to GraphQlSource.Builder. If _entities exists but the entity does not resolve, check @EntityMapping, key fields, and the representation.

## 19. Testing with GraphQlTester

Testing _entities at the GraphQL execution level can use GraphQlTester:

~~~java
@SpringBootTest
class FederationGraphQlTests {

    @Autowired
    GraphQlService graphQlService;

    GraphQlTester graphQlTester;

    @BeforeEach
    void setUp() {
        graphQlTester =
            ExecutionGraphQlServiceTester.create(graphQlService);
    }

    @Test
    void resolvesBookRepresentation() {
        var response = graphQlTester.document("""
                query ResolveBook($representations: [_Any!]!) {
                    _entities(representations: $representations) {
                        ... on Book {
                            id
                            title
                        }
                    }
                }
                """)
            .variable("representations", List.of(
                Map.of(
                    "__typename", "Book",
                    "id", "book-01")))
            .execute();

        response.errors().verify();
        response.path("_entities[0].id")
            .entity(String.class)
            .isEqualTo("book-01");
    }
}
~~~

Testing _service:

~~~java
var response = graphQlTester.document("""
        query {
            _service {
                sdl
            }
        }
        """)
    .execute();

response.errors().verify();
response.path("_service.sdl")
    .entity(String.class)
    .satisfies(sdl -> {
        assertThat(sdl).contains("@key");
        assertThat(sdl).contains("type Book");
    });
~~~

These tests verify that the GraphQL service exposes federation fields and that entity mapping works. To test full Federation composition, add tests or a pipeline running the composition tool with the SDL of all subgraphs; GraphQlTester alone cannot verify the supergraph.

## 20. Common pitfalls

| Symptom | Cause | Solution |
| --- | --- | --- |
| Missing _entities | FederationSchemaFactory not configured as schema factory | Check the bean and GraphQlSourceBuilderCustomizer |
| Missing _service | Schema not created through federation transformation or misconfigured | Check the factory callback and federation SDL |
| @EntityMapping not invoked | Controller not detected or type name mismatch | Register the factory as a bean, check method and entity name |
| Cannot bind id | Representation missing key or wrong @Argument name | Compare @key with fields in the representation |
| Resolver returns entity but GraphQL reports unknown type | Java object cannot map to GraphQL entity type | Check ClassNameTypeResolver or setTypeResolver |
| Some representations missing results | Batch result does not preserve order or is missing entities | Return results in representation order or use an appropriate mapped result |
| _entities returns error for entity | Resolver throws an exception or entity not found | Check GraphQlExceptionHandler and error contract |
| Gateway composition fails | Directives/keys inconsistent across subgraphs | Check Federation version, @key, @external, @extends, and ownership |
| Works locally but gateway cannot call it | Wrong endpoint, auth, or subgraph registration | Check router config, network, and service authentication |
| Batch loader leaks data across tenants | Cache or batch query lacks authorization scope | Isolate DataLoader per request and apply tenant predicates |

## 21. Version compatibility notes

FederationSchemaFactory has been provided by Spring for GraphQL since version 1.3.0. The current API resides in the org.springframework.graphql.data.federation package. When using Spring Boot, let Spring Boot dependency management manage compatible versions of Spring for GraphQL and GraphQL Java.

FederationSchemaFactory integrates with federation-jvm. Do not upgrade federation-jvm or GraphQL Java independently without checking compatibility with your Spring for GraphQL version.

Directives and SDL depend on the Apollo Federation version. Federation 1 commonly uses @extends and @external; Federation 2 uses schema @link to import federation directives and adds directives such as @shareable or @override. Ensure the gateway, composition tool, and federation-jvm all support the chosen SDL version.

If deeper schema transformation customization is needed, check the createSchemaTransformer API for your exact version. Do not copy constructors or methods from documentation of a different version when your project's dependencies have not been verified.

## 22. Guidelines for using FederationSchemaFactory

Declare FederationSchemaFactory as a Spring bean and attach factory::createGraphQLSchema to GraphQlSource.Builder via GraphQlSourceBuilderCustomizer. This allows the factory to detect @EntityMapping controller methods and configure entity resolvers for the federation schema.

Declare @key matching the entity identity shared by subgraphs. Use @EntityMapping to read representations and load entities; use @SchemaMapping, @BatchMapping, or DataLoader for remaining fields. When batching entity resolution, preserve representation order and avoid per-entity queries when they can be batched.

Verify _service.sdl and _entities with GraphQlTester, then test composition with the actual gateway/router. Protect entities by principal/tenant in each subgraph, and never treat representations as credentials. FederationSchemaFactory handles the federation schema and Spring's entity mapping wiring; ownership, authorization, query efficiency, and supergraph composition remain system design responsibilities.

## References

- [Spring for GraphQL — Federation](https://docs.spring.io/spring-graphql/reference/federation.html)
- [FederationSchemaFactory API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/data/federation/FederationSchemaFactory.html)
- [EntityMapping API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/data/federation/EntityMapping.html)
- [Apollo Federation — Subgraph Specification](https://www.apollographql.com/docs/federation/subgraph-spec)
- [Apollo Federation — Entities](https://www.apollographql.com/docs/federation/entities)

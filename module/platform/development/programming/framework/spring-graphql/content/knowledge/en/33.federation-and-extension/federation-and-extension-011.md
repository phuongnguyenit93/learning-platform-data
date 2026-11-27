# Authorization across subgraphs

In an Apollo Federation architecture, a GraphQL API is composed from multiple subgraphs. The Router receives an operation from a client, plans execution, and calls one or more subgraphs to fetch data. Each subgraph can own its own data, schema, and access mechanisms. Therefore, authorization must be designed end-to-end from the Router through to each subgraph.

An important principle is: the Router can authenticate and reject requests early, yet each subgraph must still protect the data it owns. The `@key` directive only describes how to identify an entity; it does not grant permission to read that entity.

## Objectives

After this lesson, you will be able to:

- Explain security boundaries between clients, the Federation Router, and subgraphs.
- Distinguish authentication at the Router from authorization in subgraphs.
- Understand how the Router calls entity resolvers via the `_entities` field.
- Configure Federation support using `FederationSchemaFactory` in Spring for GraphQL.
- Protect `@EntityMapping` and resolved fields in a subgraph.
- Obtain `Principal`, JWT, and GraphQLContext in resolvers.
- Use Spring Security method authorization for entities and fields.
- Propagate identity or claims reliably from the Router to subgraphs.
- Distinguish user permissions from service-to-service identity.
- Check tenant, ownership, and scopes when loading federated entities.
- Handle GraphQL errors safely when entity access is denied.
- Test `_entities`, field-level authorization, and Router policies directly.

## 1. Why does Federation require multi-layer authorization?

A supergraph typically has multiple subgraphs, for example:

- **Catalog subgraph** owns Product, Category, and product descriptions.
- **Inventory subgraph** owns stock quantities and warehouse statuses.
- **Pricing subgraph** owns prices, discounts, and pricing policies.
- **Order subgraph** owns orders and purchase history.

A single client query may need data from all four subgraphs. The Router orchestrates the calls and merges results into a single GraphQL response.

Example:

~~~graphql
query ProductDetails($id: ID!) {
  product(id: $id) {
    id
    name
    inventory {
      available
    }
    price {
      amount
      currency
    }
  }
}
~~~

The client sends one request to the Router. The Router can call Catalog to fetch Product, then call Inventory and Pricing with Product entity representations.

Each subgraph must protect the data it supplies. A user allowed to view a product's name may not be permitted to view internal warehouse stock levels or partner-specific pricing.

If only the root Query in Catalog is protected, requests entering Inventory via entity resolution can still access data if Inventory does not check permissions. Therefore, inspect every access path to data, including root fields, `_entities`, nested fields, and batch loaders.

## 2. Distinguishing authentication and authorization

The two concepts serve different roles:

| Concept | Question | Example |
|---|---|---|
| Authentication | Who is sending the request? | JWT identifies user and issuer |
| Authorization | What is that actor allowed to do? | User has scope `inventory:read` |
| Tenant isolation | Within which data scope may the user act? | Only read Products belonging to the current tenant |
| Service authentication | Which backend component is calling? | Router authenticated via mTLS |

A request may already be successfully authenticated and still lack permission to read a specific field.

For example, a JWT might contain:

~~~json
{
  "sub": "user-42",
  "tenant_id": "tenant-a",
  "scope": "catalog:read"
}
~~~

The token identifies the user and tenant. However, it lacks the `inventory:read` scope, so the user can view catalog information but cannot view inventory.

Do not infer permissions solely because a request passed through the Router. Authentication and authorization must be enforced at the appropriate security boundaries.

## 3. Role of the Federation Router

The Router is the entry point of the supergraph. It is typically responsible for:

- Authenticating client credentials.
- Checking certain permissions at the graph or field level.
- Planning queries and choosing which subgraphs to call.
- Propagating necessary identity or authorization info to subgraphs.
- Aggregating data and errors from multiple subgraphs.

Apollo Router supports multiple authentication and authorization strategies that can be combined:

1. Validating JWTs at the Router.
2. Using authorization directives to reject fields before calling subgraphs.
3. Forwarding verified JWTs or claims to subgraphs.
4. Using coprocessors or policy plugins for complex rules.

The Router helps reject requests early and reduce backend calls. However, the Router does not replace authorization inside subgraphs. A subgraph could be called by another Router, an internal service, or a direct client if the network allows it.

## 4. Subgraphs must protect the data they own

Suppose the Inventory subgraph provides the `Product.inventory` field. If only the Router checks scopes, a caller hitting Inventory's endpoint directly could bypass the Router policy.

The subgraph should authenticate requests itself and enforce permissions at the service method performing data access.

Layers of protection typically include:

- HTTP security to require valid credentials.
- Method security to check scopes or authorities.
- Object-level authorization to check tenant and ownership.
- Field-level authorization to protect sensitive data.
- Repository queries filtered by tenant or owner.

Do not check permissions solely in the UI, the Router, or a single root resolver. Every path reaching the data must pass through the appropriate policy.

## 5. Federation entities and the _entities field

Apollo Federation adds an entity resolution mechanism so the Router can ask a subgraph to load entities based on keys.

For example, Product is identified by id:

~~~graphql
type Product @key(fields: "id") {
  id: ID!
  name: String!
}
~~~

Another subgraph can extend Product:

~~~graphql
extend type Product @key(fields: "id") {
  id: ID! @external
  inventory: Inventory
}
~~~

The Router can send an internal operation to the `_entities` field with a representation:

~~~json
{
  "__typename": "Product",
  "id": "p-100"
}
~~~

The subgraph receives the representation and invokes the corresponding entity resolver. In Spring for GraphQL, methods annotated with `@EntityMapping` handle loading federated entities.

Important security considerations:

- Representations provide only entity-identifying data.
- A key does not prove the sender has permission to read the entity.
- A client or service might try altering an ID to access another entity.
- A tenant ID in a representation is likewise not trustworthy proof of the current tenant.
- Entity resolvers must check identity and policy before returning an entity.

Do not treat `@key`, `@external`, `@requires`, or `@shareable` as directives that grant access rights.

## 6. Configuring Federation in Spring for GraphQL

Spring for GraphQL integrates with the `federation-jvm` library to build subgraph schemas. To enable Federation, declare `FederationSchemaFactory` and wire it into `GraphQlSource`.

Example configuration:

~~~java
@Configuration
public class FederationConfiguration {

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

With Spring Boot, the builder customizer is applied when constructing the GraphQL runtime. If the application creates `GraphQlSource` manually, ensure this schema factory is actually attached to the builder.

Example SDL for the Inventory subgraph with Federation 2:

~~~graphql
extend schema
  @link(
    url: "https://specs.apollo.dev/federation/v2.6",
    import: ["@key", "@external", "@requiresScopes"]
  )

extend type Product @key(fields: "id") {
  id: ID! @external
  inventory: Inventory
    @requiresScopes(scopes: [["inventory:read"]])
}

type Inventory {
  available: Int!
  warehouseCode: String
}
~~~

In this example, `Product` is owned by another subgraph. The Inventory subgraph declares the extension and provides the inventory field.

`@requiresScopes` is an authorization directive supported by the Federation Router when configured with the right version and features. It does not automatically translate into Spring Security method security. Services in the Inventory subgraph still need to enforce permissions to protect data when requests arrive through other paths.

## 7. Enabling HTTP authentication in each subgraph

A Spring Boot subgraph can use Spring Security OAuth2 Resource Server to validate JWTs.

Gradle dependencies:

~~~groovy
implementation("org.springframework.boot:spring-boot-starter-security")
implementation("org.springframework.boot:spring-boot-starter-oauth2-resource-server")
~~~

Issuer configuration:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://identity.example.com/issuer
~~~

Security filter chain:

~~~java
@Configuration
@EnableMethodSecurity
public class InventorySecurityConfiguration {

    @Bean
    SecurityFilterChain inventorySecurityFilterChain(
            HttpSecurity http) throws Exception {

        return http
                .authorizeHttpRequests(authorize -> authorize
                        .requestMatchers("/actuator/health").permitAll()
                        .requestMatchers("/graphql").authenticated()
                        .anyRequest().denyAll())
                .oauth2ResourceServer(oauth2 ->
                        oauth2.jwt(Customizer.withDefaults()))
                .build();
    }
}
~~~

This configuration requires a valid JWT for the GraphQL endpoint. Spring Security validates signatures and claims per the resource server configuration, including the issuer. In production, ensure token audiences also match the subgraph or API resource receiving the token.

If using cookie/session authentication instead of bearer tokens, keep CSRF protection enabled and test CSRF tokens. Only configure stateless/disable CSRF when the credential mechanism and client architecture genuinely fit.

## 8. Retrieving Principal or JWT in @EntityMapping

Spring for GraphQL supports passing authentication details into `@EntityMapping` methods. Supported parameters include:

- `java.security.Principal`.
- `@AuthenticationPrincipal` to retrieve the principal from Spring Security.
- `GraphQLContext` or `@ContextValue`.
- `DataLoader` to load entities in batches.

Example entity resolver:

~~~java
@Controller
public class InventoryFederationController {

    private final ProductAccessService productAccessService;

    public InventoryFederationController(
            ProductAccessService productAccessService) {
        this.productAccessService = productAccessService;
    }

    @EntityMapping
    public Product product(
            @Argument String id,
            @AuthenticationPrincipal Jwt jwt) {

        productAccessService.assertVisible(id, jwt);
        return new Product(id);
    }
}
~~~

Entity DTO:

~~~java
public record Product(String id) {
}
~~~

The `assertVisible` method verifies the current user may reference that Product within their tenant. Only after the policy check passes does the resolver return the entity reference for GraphQL to continue resolving fields.

Do not take a tenant ID from a client-supplied argument to make authorization decisions. Obtain the tenant from a verified claim or a trusted security context.

## 9. Checking tenant in entity resolvers

Entity keys often contain only an ID. To prevent IDOR (Insecure Direct Object Reference), the service must combine the ID with the tenant or owner derived from the authenticated identity.

Example service:

~~~java
@Service
public class ProductAccessService {

    private final ProductRepository repository;

    public ProductAccessService(ProductRepository repository) {
        this.repository = repository;
    }

    @PreAuthorize("isAuthenticated()")
    public void assertVisible(String productId, Jwt jwt) {
        String tenantId = jwt.getClaimAsString("tenant_id");

        boolean visible =
                repository.existsByIdAndTenantId(productId, tenantId);

        if (!visible) {
            throw new EntityNotVisibleException();
        }
    }
}
~~~

The repository checks both conditions:

~~~java
public interface ProductRepository
        extends JpaRepository<ProductEntity, String> {

    boolean existsByIdAndTenantId(
            String productId,
            String tenantId);
}
~~~

This query avoids loading an entity by ID alone and checking the tenant afterward in Java. The database simply confirms whether the entity belongs to the allowed tenant.

If the application needs to avoid leaking whether an entity exists in another tenant, return the same business outcome for both non-existent and unauthorized cases, such as `EntityNotVisibleException` with a generic message.

## 10. Protecting sensitive fields in a subgraph

After the entity is resolved, the entity's fields still need their own policies.

For example, the Inventory subgraph only lets users with the `inventory:read` scope view stock quantities:

~~~java
@Controller
public class InventoryFieldController {

    private final InventoryService inventoryService;

    public InventoryFieldController(
            InventoryService inventoryService) {
        this.inventoryService = inventoryService;
    }

    @SchemaMapping(typeName = "Product", field = "inventory")
    public Inventory inventory(
            Product product,
            @AuthenticationPrincipal Jwt jwt) {

        return inventoryService.findForProduct(product.id(), jwt);
    }
}
~~~

Service:

~~~java
@Service
public class InventoryService {

    private final InventoryRepository repository;

    public InventoryService(InventoryRepository repository) {
        this.repository = repository;
    }

    @PreAuthorize("hasAuthority('SCOPE_inventory:read')")
    public Inventory findForProduct(String productId, Jwt jwt) {
        String tenantId = jwt.getClaimAsString("tenant_id");

        return repository.findByProductIdAndTenantId(
                        productId, tenantId)
                .map(entity -> new Inventory(
                        entity.getAvailable(),
                        entity.getWarehouseCode()))
                .orElseThrow(EntityNotVisibleException::new);
    }
}
~~~

Spring Security Resource Server maps OAuth2 scopes by default to authorities prefixed with `SCOPE_`. Thus, scope `inventory:read` corresponds to authority `SCOPE_inventory:read`.

There are two separate checks:

1. `@EntityMapping` verifies the Product representation can be referenced within the current tenant.
2. The inventory field's service verifies the user has the scope to view stock data and still filters by tenant.

If a user has permission to read catalog data but lacks permission to read inventory, the Router can reject the field early via directive; the subgraph also denies it when the service method is invoked.

## 11. @key is not an authorization policy

Federation directives describe structure and relationships across subgraphs. They do not replace access control.

| Directive | Role in Federation | Grants access rights? |
|---|---|---|
| `@key` | Declares fields used to identify an entity | No |
| `@external` | Marks fields owned by another subgraph | No |
| `@requires` | Declares fields needed to resolve another field | No |
| `@provides` | Declares fields provided along a branch | No |
| `@shareable` | Allows multiple subgraphs to resolve a field | No |
| `@authenticated` | Router authorization directive requiring an authenticated request | Yes at the Router if supported/configured |
| `@requiresScopes` | Router checks required scopes | Yes at the Router if supported/configured |

For example, Product has:

~~~graphql
type Product @key(fields: "id") {
  id: ID!
}
~~~

That only states Product can be identified by id. It does not mean every user who knows an ID is permitted to load that Product.

Similarly, `@requires(fields: "size weight")` describes data needed by a resolver. It does not verify the user is allowed to read size or weight.

## 12. Authorization directives at the Router

Apollo Federation 2 supports authorization directives such as `@authenticated` and `@requiresScopes`. The Router can check them before planning or sending requests to subgraphs.

Example SDL:

~~~graphql
extend schema
  @link(
    url: "https://specs.apollo.dev/federation/v2.6",
    import: ["@authenticated", "@requiresScopes"]
  )

type Query {
  currentUser: User @authenticated
}

type User {
  id: ID!
  email: String @requiresScopes(scopes: [["user:email:read"]])
}
~~~

Meaning:

- Requests must be authenticated to call currentUser.
- The email field requires scope `user:email:read`.
- The Router can omit or reject query parts that fail policy according to the Router version's behavior.

`@policy` can be used for more complex rules, but requires a supergraph plugin or coprocessor to enforce the policy. Declaring a directive in SDL does not create a policy engine by itself.

These directives are a Router mechanism. Spring subgraphs still need permission checks inside service methods, especially when subgraphs can be called directly or via another integration path.

## 13. Forwarding the Authorization header from the Router

A straightforward approach is for the Router to forward the client's JWT to subgraphs. Example Apollo Router configuration:

~~~yaml
headers:
  all:
    request:
      - propagate:
          named: authorization
~~~

With this configuration, the Authorization header from the client request is forwarded to subgraphs. Each subgraph can use OAuth2 Resource Server to validate the token and map scopes to authorities.

Benefits:

- Subgraphs reuse Spring Security.
- Each service checks permissions on the data it owns.
- Avoids trusting a Router-injected user ID header without a verification mechanism.

Notes:

- Forward only necessary headers.
- Tokens must have audiences matching subgraphs or use a token exchange strategy.
- Do not log raw bearer tokens.
- Do not forward unrelated cookies or credentials.
- Protect Router-to-subgraph connections with private networking and appropriate TLS/mTLS.

Header propagation only forwards credentials; it does not validate tokens or create authorization policies on its own.

## 14. Do not trust client-sent identity headers

A dangerous design is having subgraphs accept headers such as:

~~~http
X-User-Id: admin
X-Tenant-Id: tenant-a
X-Roles: ADMIN
~~~

If the Router forwards these headers verbatim without stripping client-sent values, an attacker can forge another identity or tenant.

If the Router must validate the JWT and pass verified claims:

1. The Router must strip any identity headers supplied by the client.
2. The Router recreates headers from verified claims.
3. The Router-to-subgraph connection must be protected, typically via mTLS or service authentication.
4. Subgraphs only trust those headers from an authenticated Router.
5. Subgraphs still enforce policies by tenant, scope, and object.

Conceptual configuration example:

~~~yaml
headers:
  all:
    request:
      - remove:
          named: x-authenticated-user
      - remove:
          named: x-authenticated-tenant
      - propagate:
          named: authorization
~~~

Exact rules depend on the Router version and authentication setup. If the Router uses a coprocessor or plugin to inject claims, verify the remove/insert order is right and that subgraphs cannot be reached from untrusted sources.

Never use an `X-User-Id` header as an identity source if the subgraph cannot prove that header was generated by a trusted Router.

## 15. Distinguishing user identity and service identity

In a multi-subgraph environment, a request has at least two identities to consider:

- **User identity**: the end user performing the action.
- **Service identity**: the Router or a subgraph calling another service.

Service identity proves the request comes from an authorized backend component. It does not prove the end user has permission to read data.

For example:

- The Router holds a valid mTLS certificate to call Inventory.
- The user holds a JWT with scope `catalog:read` but without `inventory:read`.
- The Router is permitted to connect to Inventory, yet the user's request still cannot read inventory.

Do not use a broad-privilege service account to bypass user authorization. When a subgraph calls another service, clearly define whether the action is authorized on behalf of the user or the service:

| Purpose | Appropriate credential |
|---|---|
| Verify Router is allowed to call subgraph | mTLS or service credential |
| Identify the end user | JWT or delegated token |
| Check user scopes | Verified user claims |
| Internal call independent of user | Least-privilege service token |
| Internal call on behalf of user | Policy-compliant token exchange/delegation |

When using token exchange, preserve actor/caller information if business requirements need to audit who made the call on the user's behalf.

## 16. Protecting against direct subgraph calls

In production, subgraphs are usually exposed only on private networks and receive traffic solely from the Router. However, network restrictions are an additional layer of defense, not a substitute for authorization.

Considerations:

- Do not expose public ingress directly to subgraphs unless required.
- Use mTLS or workload identity between Router and subgraphs.
- Verify JWTs or trusted identity inside subgraphs.
- Restrict GraphQL and management endpoints.
- Protect `_entities` just like other fields.
- Do not let a debug endpoint or alternate transport bypass SecurityFilterChain.
- Apply authorization to service methods called from GraphQL.

If a subgraph must allow direct calls from internal services, explicitly define the service principal and its permissions. Never assume every request from the internal network is trustworthy.

## 17. Using GraphQLContext for verified tenant or metadata

Some policies need request metadata such as tenant ID, correlation ID, or verified data from an interceptor.

Spring for GraphQL supports GraphQLContext and annotations such as `@ContextValue`. `@EntityMapping` can also accept GraphQLContext, Principal, or `@AuthenticationPrincipal`.

A WebGraphQlInterceptor or security integration can place the verified tenant into GraphQLContext before executing the operation. How you obtain Authentication depends on whether the app uses Spring MVC or WebFlux; with WebFlux, read the security context from Reactor Context rather than assuming ThreadLocal. Never read tenant from GraphQL variables or untrusted headers.

In the resolver:

~~~java
@EntityMapping
public Product product(
        @Argument String id,
        @ContextValue("tenantId") String tenantId) {

    return productAccessService.requireVisible(id, tenantId);
}
~~~

If `@AuthenticationPrincipal Jwt` is already available, you can read the tenant directly from the verified JWT claim. Pick one consistent identity source and avoid maintaining two tenant values that could conflict.

## 18. DataLoader must preserve authorization context

DataLoaders are typically created per GraphQL request through BatchLoaderRegistry. A batch loader can receive GraphQLContext or BatchLoaderEnvironment to enforce tenant and authorization checks.

Example:

~~~java
@Configuration
public class ProductLoaderConfiguration {

    public ProductLoaderConfiguration(
            BatchLoaderRegistry registry,
            ProductReadService productReadService) {

        registry.forTypePair(String.class, Product.class)
                .registerMappedBatchLoader((productIds, environment) -> {
                    String tenantId =
                            environment.getGraphQlContext()
                                    .get("tenantId");

                    return productReadService.findVisibleProducts(
                            tenantId, productIds);
                });
    }
}
~~~

The batch loader must query by both tenant and IDs:

~~~java
public Map<String, Product> findVisibleProducts(
        String tenantId,
        Set<String> productIds) {

    return repository.findAllByTenantIdAndIdIn(
                    tenantId, productIds)
            .stream()
            .collect(Collectors.toMap(
                    ProductEntity::getId,
                    this::toProduct));
}
~~~

Do not filter data only in the resolver before calling DataLoader. The batch loader itself must apply the tenant filter at the data query site, because it loads entities directly.

DataLoader caches should be scoped per request. Do not share loaders across requests or tenants. If results also depend on scopes or user, ensure cache keys and loader lifecycles never allow one principal's data to be served to another principal.

## 19. Handling unauthorized entity access

When an entity resolver does not find an entity or the user lacks permission, the application must choose a consistent policy.

Two common options:

- Return a not-found result if the API wants to hide whether the entity exists in another tenant.
- Return access denied if business rules permit revealing that the entity exists while the user lacks permission.

For sensitive data, generally avoid distinguishing the two cases in public responses if doing so enables IDOR enumeration.

Example exception:

~~~java
public class EntityNotVisibleException
        extends RuntimeException {
}
~~~

The entity resolver can throw this exception when the entity is not found in the current tenant or when policy rejects access.

Do not return raw SQL statements, tenant IDs, internal product IDs, or system details in GraphQL errors.

## 20. Standardizing GraphQL errors from @EntityMapping

Spring for GraphQL supports `@GraphQlExceptionHandler` to map exceptions from `@EntityMapping` into GraphQL errors. Exception handlers can be placed in a controller or `@ControllerAdvice`.

Example:

~~~java
@ControllerAdvice
public class FederationExceptionHandler {

    @GraphQlExceptionHandler
    public GraphQLError handleEntityNotVisible(
            EntityNotVisibleException exception) {

        return GraphqlErrorBuilder.newError()
                .message("Entity is not available")
                .extensions(Map.of(
                        "code", "ENTITY_NOT_AVAILABLE"))
                .build();
    }

    @GraphQlExceptionHandler
    public GraphQLError handleAccessDenied(
            AccessDeniedException exception) {

        return GraphqlErrorBuilder.newError()
                .message("Access denied")
                .extensions(Map.of(
                        "code", "FORBIDDEN"))
                .build();
    }
}
~~~

Errors from entity resolvers are included in the response of the `_entities` operation. The Router can aggregate these errors into the supergraph response.

Keep messages stable and avoid leaking original exception messages. Clients can rely on error codes to display appropriate messages; internal logs can record richer detail while avoiding tokens and personal data.

## 21. Security note on exception handling in Federation

Entity resolvers are a critical boundary because they process representations from the Router. If an unhandled exception has its original message placed into the response, internal information may be leaked.

At the time of writing this lesson, Spring published CVE-2026-59356 regarding default Federation controllers potentially including full exception messages in responses when exceptions from `@EntityMapping` are not handled by an exception handler. Affected branches include:

- Spring for GraphQL 2.0.0 to 2.0.5.
- Spring for GraphQL 1.4.0 to 1.4.7.
- Spring for GraphQL 1.3.0 to 1.3.10.

The corresponding patched versions are 2.0.6, 1.4.8, and 1.3.11. Use the patched release matching your deployed branch and still standardize errors within your application.

Do not rely on hiding stack traces at the Router as a substitute for safe exception handling inside subgraphs.

## 22. Testing service method authorization

Policies can be verified independently using Spring Security Test.

Add the test dependency:

~~~groovy
testImplementation("org.springframework.security:spring-security-test")
~~~

Example service method:

~~~java
@Service
public class InventoryService {

    @PreAuthorize("hasAuthority('SCOPE_inventory:read')")
    public Inventory readInventory(String productId) {
        // Load inventory.
        return new Inventory(12, "WH-01");
    }
}
~~~

Test user with scope:

~~~java
@SpringBootTest
class InventoryServiceSecurityTests {

    @Autowired
    InventoryService inventoryService;

    @Test
    @WithMockUser(authorities = "SCOPE_inventory:read")
    void userWithInventoryScopeCanRead() {
        Inventory inventory =
                inventoryService.readInventory("p-100");

        assertThat(inventory.available()).isEqualTo(12);
    }

    @Test
    @WithMockUser(authorities = "SCOPE_catalog:read")
    void userWithoutInventoryScopeIsDenied() {
        assertThatThrownBy(() ->
                inventoryService.readInventory("p-100"))
                .isInstanceOf(AccessDeniedException.class);
    }
}
~~~

Tests must call the real Spring-managed bean so the method-security proxy executes. If InventoryService is replaced with a Mockito mock, the test no longer verifies `@PreAuthorize`.

## 23. Testing _entities over HTTP

Include integration tests for the Federation entity resolution path, not just root Query tests.

Example operation:

~~~graphql
query ProductEntity($representations: [_Any!]!) {
  _entities(representations: $representations) {
    ... on Product {
      id
      inventory {
        available
      }
    }
  }
}
~~~

Variables:

~~~json
{
  "representations": [
    {
      "__typename": "Product",
      "id": "p-100"
    }
  ]
}
~~~

Tests can use `HttpGraphQlTester` and send a valid bearer token:

~~~java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureHttpGraphQlTester
class InventoryFederationAuthorizationTests {

    @Autowired
    HttpGraphQlTester graphQlTester;

    @Test
    void userWithInventoryScopeCanResolveEntity() {
        HttpGraphQlTester authorizedTester = graphQlTester.mutate()
                .headers(headers ->
                        headers.setBearerAuth(validInventoryToken()))
                .build();

        authorizedTester.documentName("productEntity")
                .variable("representations", List.of(
                        Map.of(
                                "__typename", "Product",
                                "id", "p-100")))
                .execute()
                .path("_entities[0].inventory.available")
                .entity(Integer.class)
                .isEqualTo(12);
    }
}
~~~

This example assumes the test has a valid token produced by a test identity provider or JWT test fixture, the `productEntity.graphql` file resides in the test document source, and the Product data belongs to the user's tenant.

Test user without scope:

~~~java
@Test
void userWithoutInventoryScopeCannotReadInventory() {
    HttpGraphQlTester viewerTester = graphQlTester.mutate()
            .headers(headers ->
                    headers.setBearerAuth(validCatalogOnlyToken()))
            .build();

    viewerTester.documentName("productEntity")
            .variable("representations", List.of(
                    Map.of(
                            "__typename", "Product",
                            "id", "p-100")))
            .execute()
            .errors()
            .satisfy(errors ->
                    assertThat(errors)
                            .anyMatch(error ->
                                    error.getMessage()
                                            .contains("Access denied")));
}
~~~

In real tests, also verify error paths and field data according to schema nullability. Do not merely check that the response contains errors; verify that the inventory field returns no data.

If a test runs against an HTTP server on a separate port, `@WithMockUser` on the test thread does not automatically become the request's credential. Send a bearer token or use a test web client with mock security appropriate for in-process testing.

## 24. Testing tenant isolation

A user holding the `inventory:read` scope must still be prevented from reading another tenant's inventory.

Test matrix:

| User | Scope | Tenant | Entity tenant | Result |
|---|---|---|---|---|
| Alice | inventory:read | tenant-a | tenant-a | Allowed |
| Alice | inventory:read | tenant-a | tenant-b | Denied or not found |
| Bob | catalog:read | tenant-b | tenant-b | Denied reading inventory |
| Anonymous | None | — | tenant-a | Rejected at HTTP authentication |

Tests should try swapping entity IDs in representations to verify users cannot access entities outside their tenant merely by knowing an ID.

In particular, never take tenant from the representation:

~~~json
{
  "__typename": "Product",
  "id": "p-100",
  "tenantId": "tenant-b"
}
~~~

Unless tenantId is a schema-trusted key permitted by policy, this value remains untrusted input. Use the verified tenant claim from Authentication or GraphQLContext.

## 25. Testing Router policy and subgraph policy separately

A Federation system needs testing at least across two layers:

**Router tests**

- Invalid JWTs are rejected.
- Requests lacking required scopes are rejected before calling subgraphs when Router policy is enabled.
- Client-supplied identity headers are stripped.
- Verified headers or claims are propagated accurately to subgraphs.
- Fields guarded by `@requiresScopes` do not appear in results when scopes are missing.

**Subgraph tests**

- Direct requests to a subgraph without a token are rejected.
- JWTs with wrong issuer or audience are rejected.
- `@EntityMapping` checks tenant/entity visibility.
- `@SchemaMapping` invokes services protected with method security.
- DataLoader batch queries apply tenant filters.
- Sensitive fields do not appear when permissions are lacking.
- Exceptions are mapped into safe error messages.

Both Router policy and subgraph policy may reject the same request. This is defense in depth, not redundant duplication: the Router optimizes and rejects early; the subgraph protects data where the data is owned.

## 26. Testing errors and partial data

GraphQL can return data and errors together. For example, a user is permitted to read Product but not Inventory.

Illustrative response:

~~~json
{
  "data": {
    "_entities": [
      {
        "id": "p-100",
        "inventory": null
      }
    ]
  },
  "errors": [
    {
      "message": "Access denied",
      "path": ["_entities", 0, "inventory"],
      "extensions": {
        "code": "FORBIDDEN"
      }
    }
  ]
}
~~~

This is an illustrative example; actual responses depend on SDL nullability and how the Router aggregates errors.

Tests should verify:

- Public Product fields still contain data if permitted by policy.
- Inventory is null or omitted from data per the schema.
- Error paths point to the exact field or entity resolver.
- Error codes are stable.
- No tokens, tenant IDs, or internal exception messages appear in the response.

If a field is declared non-null, GraphQL may bubble nulls up to parent fields according to nullability rules. Design your SDL to match expected behavior when authorization fails.

## 27. Common pitfalls

| Symptom | Possible cause | Solution |
|---|---|---|
| User reads field when calling subgraph directly | Protected only at the Router | Add method/object authorization inside the subgraph |
| Entity resolver returns another tenant's data | Queries solely by entity ID | Filter using the verified tenant claim |
| `@key` mistaken for access rights | Confusing identity with authorization | Check policy inside @EntityMapping/service |
| Router authenticated user but subgraph has no Principal | Credentials or context not propagated | Configure header propagation/token exchange |
| Subgraph trusts X-User-Id from client | Router failed to strip forged headers | Strip headers and inject verified claims |
| Service token holds overly broad permissions | Using service identity instead of user policy | Combine service authentication with user authorization |
| Field resolver bypasses policy | Protected only root Query | Protect service methods called from all access paths |
| DataLoader returns another tenant's data | Loader cache wrong scope or batch query missing tenant filter | Per-request loaders and tenant-filtered queries |
| _entities left unprotected | Tested only root Query | Test entity representations directly |
| GraphQL error leaks exception message | Entity mapping exception unstandardized | Use @GraphQlExceptionHandler and apply security patches |
| @requiresScopes has no effect | Router unsupported or authorization not enabled | Check Router version and configuration |
| @WithMockUser fails over live HTTP | SecurityContext lives only on the test thread | Send real JWTs in HttpGraphQlTester |
| Router rejects yet subgraph still accepts other requests | Direct access path exists | Apply network policies and subgraph security |

## 28. Checklist for implementing authorization across subgraphs

Before promoting a Federation supergraph to production:

- [ ] Router authenticates client credentials.
- [ ] Router policies are enabled for required directives.
- [ ] Each subgraph authenticates requests according to the chosen trust model.
- [ ] Router-to-subgraph connections are protected with TLS/mTLS or suitable service identity.
- [ ] Subgraphs are not exposed publicly unless required.
- [ ] `@EntityMapping` checks entity visibility and tenant.
- [ ] Sensitive fields have authorization at the service or resolver layer.
- [ ] `@key` is used solely for entity identification, never as an access grant.
- [ ] Tenant is obtained from verified identity, never from representations.
- [ ] Client-supplied identity headers are stripped before the Router injects claims.
- [ ] User identity is distinguished from service identity.
- [ ] DataLoaders are created per request and batch queries apply tenant filters.
- [ ] GraphQL errors do not leak exception messages or internal data.
- [ ] Spring for GraphQL is on a version patched for relevant security advisories.
- [ ] Direct `_entities` tests exist for both authorized and unauthorized users.
- [ ] Tenant isolation and object ownership tests exist.
- [ ] Separate tests exist for Router policies and subgraph policies.
- [ ] Partial data and error path tests match schema nullability.

## Conclusion

Authorization across subgraphs must be designed in multiple layers. The Router authenticates requests and can enforce authorization directives to reject fields early. Each subgraph must still protect the data it owns, especially inside `@EntityMapping`, `@SchemaMapping`, service methods, and batch loaders.

In Spring for GraphQL, FederationSchemaFactory integrates the Federation schema, while `@EntityMapping` handles entity representations from `_entities`. These methods can accept Principal, `@AuthenticationPrincipal`, or GraphQLContext to enforce policies. `@PreAuthorize` protects service methods, while repository queries must filter by tenant or owner.

Never treat entity keys, client-sent headers, or service identities as proof that a user is authorized to access data. Authenticate credentials, propagate identity over trusted channels, enforce scopes and tenants in subgraphs, standardize GraphQL errors, and test both the Router and every subgraph. This approach ensures the supergraph preserves security boundaries even when entities are reached through different execution paths.

## References

- [Spring for GraphQL — Federation](https://docs.spring.io/spring-graphql/reference/federation.html)
- [Spring for GraphQL — Security](https://docs.spring.io/spring-graphql/reference/security.html)
- [Spring for GraphQL — Annotated Controllers](https://docs.spring.io/spring-graphql/reference/controllers.html)
- [Apollo — Authenticating Requests with the GraphOS Router](https://www.apollographql.com/docs/graphos/routing/v3/security/router-authentication)
- [Apollo — Authorization in the GraphOS Router](https://www.apollographql.com/docs/graphos/routing/security/authorization)
- [Apollo — Header Propagation](https://www.apollographql.com/docs/graphos/routing/header-propagation)
- [Apollo — Federation Subgraph Specification](https://www.apollographql.com/docs/graphos/schema-design/federated-schemas/reference/subgraph-spec)
- [Spring Security — OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
- [Spring Advisory — CVE-2026-59356](https://spring.io/security/cve-2026-59356)

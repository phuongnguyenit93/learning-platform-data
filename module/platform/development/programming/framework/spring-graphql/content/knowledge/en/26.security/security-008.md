# Tenant context in Spring for GraphQL

In multi-tenant applications, multiple organizations or customers share a single GraphQL API while their data must remain isolated. Tenant context is the information identifying which tenant the current request belongs to, used throughout field resolution, service calls, repository queries, batch loading, and subscription event emission.

Spring for GraphQL provides `GraphQLContext`, `@ContextValue`, `Principal`, and `@AuthenticationPrincipal` to propagate information per GraphQL execution. However, having a tenant context does not automatically guarantee data isolation. The application must still verify identity, determine the tenant from a trusted source, and apply tenant filters at the service/repository layer for all read, write, and delete operations.

## 1. What are tenants and tenant context?

A tenant is a customer or organization unit with its own data scope within the same system. For example, a project management platform can serve multiple companies:

- Company A has its own projects, members, and invoices.
- Company B has similar data but must not see Company A's data.
- A single user may belong to one or more tenants with different roles.

`TenantContext` is an object describing the request's tenant scope, typically containing:

| Component | Purpose |
|---|---|
| `tenantId` | Identifier of the current tenant. |
| `subject` | Authenticated user or service. |
| `authorities` or roles | Verified permissions if the application needs them. |
| `correlationId` | Request tracking ID, if needed for logging/tracing. |

Example immutable model:

```java
public record TenantContext(
    String tenantId,
    String subject
) {}
```

Do not confuse tenant context with a global variable or a mutable field on a singleton service. Tenant context must belong strictly to the current request or execution so one tenant's data never leaks into another tenant's request.

## 2. Multi-tenant storage models

Before implementing GraphQL context, determine how data is partitioned:

| Model | Organization | Characteristics |
|---|---|---|
| Shared database, shared schema | All tenants share tables; each row has `tenant_id`. | Easy to operate and optimize resources; every query must filter tenant accurately. |
| Shared database, schema per tenant | Each tenant has its own database schema. | Structural separation at schema level; must select the right schema per request. |
| Database per tenant | Each tenant has its own database. | Stronger isolation; connection management, migrations, and operations are more complex. |
| Hybrid | Combines the models above. | Suits systems with large and small tenants having different requirements. |

In the shared-schema model, for example, the `project` table might look like:

```sql
CREATE TABLE project (
    id UUID PRIMARY KEY,
    tenant_id VARCHAR(80) NOT NULL,
    name VARCHAR(200) NOT NULL
);

CREATE INDEX idx_project_tenant_id_id
    ON project (tenant_id, id);
```

Every operation must specify both `tenant_id` and the resource ID. Querying solely by `WHERE id = :id` is insufficient if IDs are not guaranteed globally unique or if the application requires defense-in-depth.

## 3. How does tenant context flow through a GraphQL request?

The processing flow should have clear boundaries:

```text
Client request
      |
      v
Spring Security authentication
      |
      v
Principal / verified JWT claims
      |
      v
Resolve active TenantContext
      |
      v
GraphQL execution
      |
      +---- @QueryMapping / @MutationMapping
      |
      +---- @SchemaMapping / @BatchMapping
      |
      v
Tenant-aware service
      |
      v
Tenant-filtered repository / database
```

Principles:

1. Authenticate the user before trusting their identity.
2. Determine the tenant from the verified principal/claims or another trusted source.
3. Propagate tenant context per request or pass the tenant ID explicitly into services.
4. Apply tenant filters at the data access layer.
5. Check the user's permissions on the resource within that tenant.

A GraphQL argument like `tenantId` may be a business parameter in a specialized admin API, but must never be treated as proof of the caller's tenant. Users must not be able to switch tenants by altering arbitrary arguments or headers.

## 4. Extracting the tenant from the authenticated identity

With OAuth2 Resource Server, Spring Security validates the JWT and can supply `Jwt` as the principal to annotated controllers via `@AuthenticationPrincipal`.

Example factory creating tenant context from verified claims:

```java
@Component
class TenantContextFactory {

    private final TenantMembershipService membershipService;

    TenantContextFactory(TenantMembershipService membershipService) {
        this.membershipService = membershipService;
    }

    TenantContext from(Jwt jwt) {
        String tenantId = jwt.getClaimAsString("tenant_id");
        if (tenantId == null || tenantId.isBlank()) {
            throw new AccessDeniedException("Tenant claim is required");
        }

        return new TenantContext(tenantId, jwt.getSubject());
    }

    TenantContext from(Principal principal) {
        return membershipService.findActiveTenantFor(principal.getName())
            .orElseThrow(() -> new AccessDeniedException("No active tenant"));
    }
}
```

```java
interface TenantMembershipService {
    Optional<TenantContext> findActiveTenantFor(String subject);
}
```

In this example, `membershipService` is a dependency of the factory and returns the active tenant membership of the subject. This membership lookup can be used when a user is allowed to belong to multiple tenants and the active tenant is selected according to application policy.

`tenant_id` is trustworthy only after the JWT's signature, issuer, audience, and expiration have been verified per Spring Security configuration. If a user is permitted to choose among multiple tenants, claims may only contain a list of tenants or the token may omit the active tenant; in that case, the application must verify membership and select the tenant through a controlled flow.

If the application uses session authentication or a custom principal, it can accept `Principal`/`Authentication` and use a service to look up tenant membership. Spring for GraphQL supports `Principal` and `@AuthenticationPrincipal` as method arguments in annotated controllers.

## 5. Passing the tenant to services from resolvers

A direct and easy-to-control approach is for the resolver to extract the tenant from the principal and pass the tenant ID to the service:

```graphql
type Query {
    projects: [Project!]!
    project(id: ID!): Project
}

type Project {
    id: ID!
    name: String!
}
```

```java
public record Project(UUID id, String name, String tenantId) {
    public Project withName(String newName) {
        return new Project(id, newName, tenantId);
    }
}

@Controller
class ProjectController {

    private final TenantContextFactory tenantContextFactory;
    private final ProjectService projectService;

    ProjectController(
            TenantContextFactory tenantContextFactory,
            ProjectService projectService) {
        this.tenantContextFactory = tenantContextFactory;
        this.projectService = projectService;
    }

    @QueryMapping
    Flux<Project> projects(Principal principal) {
        TenantContext tenant = tenantContextFactory.from(principal);
        return projectService.findAllForTenant(tenant.tenantId());
    }

    @QueryMapping
    Mono<Project> project(
            @Argument UUID id,
            Principal principal) {
        TenantContext tenant = tenantContextFactory.from(principal);
        return projectService.findByTenantAndId(tenant.tenantId(), id);
    }
}
```

The tenant ID does not appear in the GraphQL query. The server derives the tenant from the principal and passes it into the service. This fits well when the resolver only needs the tenant for a single operation and does not need to share extensive metadata across fields.

If using `Principal` instead of `Jwt`, `TenantContextFactory` can look up membership by `principal.getName()`. Never take a username or tenant ID from a client-sent argument and treat it as the authenticated principal.

## 6. Using `GraphQLContext` for shared information within an execution

`GraphQLContext` is an execution-scoped context that can pass information across multiple data fetchers within the same GraphQL operation. It is useful when multiple nested fields need the tenant context.

Example of a root resolver determining the tenant from a JWT and storing it in context before returning parent objects:

```java
@Controller
class ProjectController {

    private final TenantContextFactory tenantContextFactory;
    private final ProjectService projectService;

    ProjectController(
            TenantContextFactory tenantContextFactory,
            ProjectService projectService) {
        this.tenantContextFactory = tenantContextFactory;
        this.projectService = projectService;
    }

    @QueryMapping
    Flux<Project> projects(
            @AuthenticationPrincipal Jwt jwt,
            GraphQLContext graphQLContext) {

        TenantContext tenant = tenantContextFactory.from(jwt);
        graphQLContext.put("tenantContext", tenant);

        return projectService.findAllForTenant(tenant.tenantId());
    }
}
```

Child fields can read the context via `@ContextValue`:

```java
@SchemaMapping(typeName = "Project", field = "billingSummary")
Mono<BillingSummary> billingSummary(
        Project project,
        @ContextValue("tenantContext") TenantContext tenant) {

    return billingService.summaryForTenantAndProject(
        tenant.tenantId(), project.id()
    );
}
```

`GraphQLContext` is shared across one execution, while `@ContextValue` binds a specific value from the context to a method argument. Set the context once at a well-defined boundary and treat `TenantContext` as immutable.

The root-resolver example above works when the operation fetches a project list as its root and then resolves its child fields. If an operation has multiple independent root fields, do not rely on one resolver's execution order to set context for another resolver. Resolve the tenant from the principal in each root resolver, or initialize the context prior to execution using an interceptor/integration that has access to the verified tenant source.

## 7. Using HTTP headers only when they come from a trusted source

Spring for GraphQL provides `HttpRequestHeaderInterceptor` to copy selected HTTP headers into `GraphQLContext`:

```java
@Configuration
class GraphQlTenantHeaderConfiguration {

    @Bean
    HttpRequestHeaderInterceptor tenantHeaderInterceptor() {
        return HttpRequestHeaderInterceptor.builder()
            .mapHeader("X-Verified-Tenant")
            .build();
    }
}
```

Import for the built-in interceptor:

```java
import org.springframework.graphql.server.support.HttpRequestHeaderInterceptor;
```

The controller can read the value:

```java
@QueryMapping
Flux<Project> projects(
        @ContextValue("X-Verified-Tenant") String tenantId) {
    return projectService.findAllForTenant(tenantId);
}
```

Only use this approach when a trusted API gateway or reverse proxy has authenticated the user, verified membership, stripped any client-sent header of the same name, and set `X-Verified-Tenant` itself. The backend must be protected so clients cannot call it directly and spoof the header.

If browsers or clients call the GraphQL endpoint directly, never use an arbitrary header such as `X-Tenant-Id` as the source of truth for tenant identification. Use the authenticated principal or an authorization-checked tenant selection flow.

## 8. Tenant-aware services and repositories

Making the tenant ID a mandatory parameter on data-accessing service methods makes the isolation policy explicit and easy to test.

Service:

```java
@Service
class ProjectService {

    private final ProjectRepository repository;

    ProjectService(ProjectRepository repository) {
        this.repository = repository;
    }

    Flux<Project> findAllForTenant(String tenantId) {
        return repository.findAllByTenantId(tenantId);
    }

    Mono<Project> findByTenantAndId(String tenantId, UUID projectId) {
        return repository.findByTenantIdAndId(tenantId, projectId);
    }
}
```

Reactive repository:

```java
interface ProjectRepository extends ReactiveCrudRepository<Project, UUID> {

    Flux<Project> findAllByTenantId(String tenantId);

    Mono<Project> findByTenantIdAndId(String tenantId, UUID id);
}
```

With JPA, you can use similar derived queries or declare `@Query` with a `tenantId` predicate. What matters is that the tenant is present in the predicate of the data access operation.

Do not load a project by ID alone and check the tenant only after passing the object across multiple layers. Querying with a tenant predicate from the start reduces data-leak risk and helps the database leverage appropriate indexes.

## 9. Protecting mutations and write/delete operations

Mutations should not accept `tenantId` as data deciding which tenant owns a record. The server must assign the tenant from the verified context.

SDL:

```graphql
input CreateProjectInput {
    name: String!
}

type Mutation {
    createProject(input: CreateProjectInput!): Project!
    renameProject(id: ID!, name: String!): Project!
    deleteProject(id: ID!): Boolean!
}
```

Resolver:

```java
@MutationMapping
Mono<Project> createProject(
        @Argument CreateProjectInput input,
        @AuthenticationPrincipal Jwt jwt) {

    TenantContext tenant = tenantContextFactory.from(jwt);
    return projectService.createForTenant(tenant.tenantId(), input.name());
}
```

The service must ensure both update and delete include a tenant predicate:

```java
Mono<Project> renameProject(String tenantId, UUID id, String name) {
    return repository.findByTenantIdAndId(tenantId, id)
        .switchIfEmpty(Mono.error(new ProjectNotFoundException(id)))
        .flatMap(project -> repository.save(project.withName(name)));
}

Mono<Boolean> deleteProject(String tenantId, UUID id) {
    return repository.deleteByTenantIdAndId(tenantId, id)
        .thenReturn(true);
}
```

The repository method `deleteByTenantIdAndId` and model method `withName` are examples to implement using your application's persistence technology. Never use `deleteById(id)` if that operation does not check tenant ownership.

## 10. Combining tenant context with `@BatchMapping`

Nested fields must also preserve the tenant boundary. Suppose each project has a list of members:

```graphql
type Project {
    id: ID!
    name: String!
    members: [Member!]!
}

type Member {
    id: ID!
    name: String!
}
```

Illustrative Java model:

```java
public record Member(UUID id, UUID projectId, String name, String tenantId) {}
```

`@BatchMapping` supports `@ContextValue`, `GraphQLContext`, and `Principal` as method arguments. It can use the tenant context established in the root resolver:

```java
@BatchMapping(typeName = "Project", field = "members")
Mono<Map<Project, List<Member>>> members(
        List<Project> projects,
        @ContextValue("tenantContext") TenantContext tenant) {

    Set<UUID> projectIds = projects.stream()
        .map(Project::id)
        .collect(Collectors.toSet());

    return memberService.findForTenantAndProjectIds(
            tenant.tenantId(), projectIds)
        .collectMultimap(Member::projectId)
        .map(membersByProject -> {
            Map<Project, List<Member>> result = new LinkedHashMap<>();
            for (Project project : projects) {
                Collection<Member> members = membersByProject.getOrDefault(
                    project.id(), List.of());
                result.put(project, List.copyOf(members));
            }
            return result;
        });
}
```

The service queries by both tenant and the set of project IDs:

```java
Flux<Member> findForTenantAndProjectIds(
        String tenantId,
        Set<UUID> projectIds) {
    return memberRepository.findAllByTenantIdAndProjectIdIn(tenantId, projectIds);
}
```

The batch query must apply the tenant predicate right in the repository. Never load members solely by a list of project IDs and assume every project belongs to the current tenant.

If a batch field lacks context from a root resolver, it can accept `Principal` directly in `@BatchMapping` and resolve the tenant from the principal. This is a good option when you do not want to depend on context populated by a specific root field.

## 11. Propagating tenant context into DataLoader

When using `BatchLoaderRegistry`, batch loading functions can also access `GraphQLContext` via `BatchLoaderEnvironment`. Spring for GraphQL ensures the batch loader's context is the same context provided to data fetchers and `@BatchMapping`.

Example registering a mapped batch loader:

```java
@Configuration
class MemberDataLoaderConfiguration {

    MemberDataLoaderConfiguration(
            BatchLoaderRegistry registry,
            MemberService memberService) {

        registry.forTypePair(UUID.class, Member.class)
            .registerMappedBatchLoader((memberIds, environment) -> {
                GraphQLContext context = (GraphQLContext) environment.getContext();
                TenantContext tenant = context.get("tenantContext");

                return memberService.findByTenantAndIds(
                    tenant.tenantId(), memberIds
                ).collectMap(Member::id);
            });
    }
}
```

Here the key is `UUID` and the value is `Member`; the batch loader retrieves the tenant context from the GraphQL execution and loads data by both tenant ID and member IDs. Register DataLoaders through `BatchLoaderRegistry` to benefit from Spring for GraphQL's context propagation.

If an application uses multiple tenants within a single GraphQL execution (a special case requiring explicit design), do not assume a single `tenantContext` suffices for every key. In that case, the tenant must become part of the key or per-`load` local context, and the batch loader must group by tenant before querying.

## 12. Tenant isolation in DataLoader and caches

By default, DataLoader caches by key within the scope of a single GraphQL request. If an execution has one immutable tenant context, keying by resource ID can suffice to distinguish data within that request, provided the batch loader always filters by tenant.

Greater risk usually lies in caches shared across multiple requests:

- A cache key containing only `projectId` can return tenant A's data to tenant B if IDs are not globally unique.
- Application-wide caches must never rely on a mutable `TenantContext` or `ThreadLocal` to implicitly identify the tenant.
- Caches must be namespaced by tenant, e.g., `(tenantId, projectId)`.
- When membership or permissions change, caches must have appropriate invalidation.

Example key value object:

```java
public record TenantProjectKey(String tenantId, UUID projectId) {}
```

With Caffeine/Redis or a cache service, including the tenant ID in the key prevents collisions between tenants. Do not merely add the tenant to the cache key; still authenticate and verify permissions before returning data.

## 13. Combining tenant context with authorization

Tenant isolation and authorization are two distinct layers:

- Tenant isolation ensures requests only access data belonging to the selected tenant.
- Authorization checks whether the user is permitted to perform an action on a resource within that tenant.

For example, a user in tenant A may only be allowed to read projects managed by their group. The service can use method security:

```java
@Service
class ProjectAuthorizationService {

    private final ProjectRepository repository;

    ProjectAuthorizationService(ProjectRepository repository) {
        this.repository = repository;
    }

    @PreAuthorize("hasAuthority('project:read')")
    public Mono<Project> findByTenantAndId(String tenantId, UUID projectId) {
        return repository.findByTenantIdAndId(tenantId, projectId);
    }
}
```

The application must enable method security, for example with `@EnableMethodSecurity` in the Spring Security configuration.

`@PreAuthorize` checks general authorities; ownership/tenant conditions must still be enforced in the service or query. Do not rely solely on a `USER` or `ADMIN` role while omitting the tenant predicate.

For sensitive operations, you can return the same `NOT_FOUND` outcome for both non-existent resources and resources belonging to another tenant to avoid disclosing out-of-scope data existence. Keep this policy consistent across the API and internal logs.

## 14. Tenant context with Subscriptions

Subscriptions have a longer lifecycle than normal queries. Tenant context must be resolved when the client opens the subscription and used to filter every emitted event.

Example:

```java
@SubscriptionMapping
Flux<ProjectEvent> projectEvents(
        @Argument UUID projectId,
        @AuthenticationPrincipal Jwt jwt) {

    TenantContext tenant = tenantContextFactory.from(jwt);

    return projectService.verifyCanRead(tenant, projectId)
        .thenMany(eventPublisher.eventsForTenantProject(
            tenant.tenantId(), projectId));
}
```

The event source must filter by both tenant ID and project ID. Never take `tenantId` from a subscription argument and broadcast every event matching `projectId`.

With WebSocket, authentication can be established via `AuthenticationWebSocketInterceptor` from the `connection_init` payload. Long-lived connections need policies for expired tokens, revoked memberships, or users changing tenants. You can close the stream, require reconnection, or re-check permissions periodically or per event depending on security requirements.

## 15. Context propagation and lifetime scope

`GraphQLContext` is bound to a single GraphQL execution. `BatchLoaderRegistry` ensures context propagates to batch loading functions; annotated controllers can read it via `GraphQLContext` or `@ContextValue`.

Never store tenant context in:

- Mutable fields of `@Controller`, `@Service`, or singleton components.
- Static variables shared across requests.
- Self-managed `ThreadLocal` without an appropriate context propagation mechanism.
- Global caches keyed solely by resource ID.

In Spring WebFlux, requests can execute across multiple threads; do not assume `ThreadLocal` always retains the right tenant. Use `GraphQLContext`, `@ContextValue`, `Principal`, or supported Reactor/Spring Security context mechanisms.

If using custom asynchronous data fetchers or schedulers, verify context propagation to child tasks. When passing the tenant into services, passing the value explicitly is usually clearer and safer than relying on thread-local state.

## 16. Defense in depth at the database

Applications should enforce tenant predicates in services/repositories, while systems with strict isolation requirements can add database-level protections:

- Row-Level Security (RLS) so the database restricts rows automatically by tenant session/context.
- Dedicated database roles or schemas per tenant.
- Connection pools or connection routing with tenant-aware configuration.
- Composite foreign keys or constraints ensuring table relationships cannot join across tenants.

If using RLS, ensure tenant session variables are set safely per transaction/connection and reset before the connection returns to the pool. Never leave a tenant ID from a previous request on a connection reused for another request.

Database isolation is an additional safeguard; it does not replace authentication and authorization in the application. Test both when queries are called directly through repositories and when invoked through GraphQL.

## 17. Testing tenant context and isolation

Tests should focus on proving cross-tenant access is impossible, including through nested fields and batch loading.

| Scenario | Expectation |
|---|---|
| JWT for tenant A queries project list | Returns only tenant A's projects. |
| JWT for tenant A queries ID of project B | Does not return B's data; response follows not-found/forbidden policy. |
| Client sends `tenantId=B` in a GraphQL argument | Does not alter the tenant determined from the principal. |
| Tenant A queries `Project.members` | Batch query loads only tenant A's members. |
| Two requests A and B run concurrently | Context and caches do not mix data. |
| Mutation creates a project | Server assigns tenant from context. |
| Mutation updates/deletes an ID of another tenant | Does not alter the other tenant's data. |
| Subscription watches a project | Emits only events belonging to the verified tenant. |
| Token/membership is revoked | Subscription stops or permissions are re-evaluated per policy. |

Example testing a resolver/service with a mock principal:

```java
@GraphQlTest(ProjectController.class)
@Import(TenantContextFactory.class)
class ProjectTenantTests {

    @Autowired
    GraphQlTester graphQlTester;

    @MockitoBean
    ProjectService projectService;

    @MockitoBean
    TenantMembershipService tenantMembershipService;

    @Test
    @WithMockUser(username = "alice")
    void loadsProjectsForResolvedTenant() {
        given(tenantMembershipService.findActiveTenantFor("alice"))
            .willReturn(Optional.of(new TenantContext("tenant-a", "alice")));
        given(projectService.findAllForTenant("tenant-a"))
            .willReturn(Flux.just(new Project(
                UUID.randomUUID(), "Project A", "tenant-a")));

        graphQlTester.document("""
                query {
                    projects { name }
                }
                """)
            .execute()
            .path("projects[0].name")
            .entity(String.class)
            .isEqualTo("Project A");

        then(projectService).should().findAllForTenant("tenant-a");
    }
}
```

This is an illustrative example; `tenantMembershipService`, models, resolvers, and JWT/principal configuration must be supplied in the test context. `@WithMockUser` creates a Spring Security test principal; if the resolver accepts `Jwt`, use a test security context or appropriate mock JWT principal instead of assuming `@WithMockUser` creates a `Jwt`.

Beyond unit/slice tests, write integration tests against a real database or Testcontainers to verify tenant predicates, transactions, and RLS if the application uses those mechanisms.

## 18. Common issues

**Trusting client-sent `tenantId`.** Clients can alter arguments or headers. Determine the tenant from the authenticated principal or a trusted gateway source.

**Filtering by tenant only at the root query.** Nested fields, DataLoaders, mutations, and subscriptions must also apply their own tenant filters.

**Putting tenant context in a mutable singleton field.** Concurrent requests can overwrite each other's tenant. Use execution-scoped context or pass the tenant explicitly.

**Using `GraphQLContext` as an application-wide cache.** Context belongs strictly to an execution; never keep references to it in singleton services.

**Forgetting the tenant predicate in batch queries.** Batch loading can fetch many IDs at once; always filter by tenant inside the batch repository call itself.

**Global caches keyed solely by resource ID.** Use composite keys containing the tenant ID and check permissions before returning cache hits.

**Using `@PreAuthorize` instead of tenant filtering.** Roles/authorities do not automatically add a tenant predicate to SQL. Check both permissions and ownership.

**Ignoring long-lived subscriptions.** Tokens or memberships can change after subscribing. Build revocation and re-authorization policies.

**Relying on ThreadLocal in WebFlux.** Reactive execution can switch threads. Use `GraphQLContext`, `@ContextValue`, and appropriate context propagation mechanisms.

## Conclusion

Tenant context in Spring for GraphQL is execution-scoped information used to define the data boundary of a tenant. Derive the tenant from a verified principal/claim or protected gateway source, then pass it via `GraphQLContext`, `@ContextValue`, `Principal`, or service arguments. Enforce tenant predicates across every query, mutation, batch loader, and subscription; namespace caches by tenant; check authorization per resource; and test concurrently across multiple tenants to catch data leaks. `GraphQLContext` carries the information, while true tenant isolation must be guaranteed in services, repositories, and—when needed—the database.

## References

- [Spring for GraphQL — Annotated Controllers and `GraphQLContext`](https://docs.spring.io/spring-graphql/reference/controllers.html)
- [Spring for GraphQL — Web Interception](https://docs.spring.io/spring-graphql/reference/transports.html)
- [Spring for GraphQL — Batch Loading and `BatchLoaderRegistry`](https://docs.spring.io/spring-graphql/reference/request-execution.html)
- [Spring Security — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
